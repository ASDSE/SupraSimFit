"""The entered inputs of a fit and how their uncertainty is stated.

A fitted Ka rests on inputs the user entered: every concentration and binding
constant among the assay conditions, and the titrant series, which moves as one
scale factor under the key ``TITRANT``. :class:`InputSpec` states one input's
uncertainty the way the interface collects it — a standard deviation or a
range, in percent of the entered value or in the input's own unit. The
error an input has alone is its own source, under the input's key. An error
several inputs have in common, because they come from one stock, balance or
pipette, is a :class:`SharedSource`. The sources are independent and multiply:

    input_i = entered_i * prod over the sources s that move i of (1 + e_s)

:class:`ErrorModel` holds them all, with the random error of each titrant
addition (:class:`AdditionError`, :func:`perturb_titrant`). The sensitivity
analysis samples the sources; the input-aware interval reads them through
:func:`constraints`, which turns every varying source into an
:class:`InputConstraint` on its relative offset ``e``.

Layering: this module must not import from ``gui.*``. Inputs are classified by
pint dimensionality of the passed condition Quantities (``M`` → concentration,
``1/M`` → binding constant); display labels are derived in the GUI layer and
passed in wherever a message names an input.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Mapping, Optional

import numpy as np
from scipy.stats import truncnorm

from core.assays.base import TITRANT, TITRANT_STOCK
from core.pipeline.varpro import FitRefused
from core.units import Quantity

__all__ = [
    'ADDITIONS',
    'TITRANT',
    'TITRANT_STOCK',
    'AdditionError',
    'ErrorModel',
    'InputConstraint',
    'InputSpec',
    'SpecKind',
    'axis_reaches_zero',
    'constraints',
    'input_name',
    'is_shared',
    'nominal_value',
    'perturb_titrant',
    'perturbable_inputs',
    'shared_key',
    'source_name',
    'spec_bounds',
    'spec_fraction',
    'specs_from_dict',
    'specs_to_dict',
    'validate',
]

#: Key under which the sensitivity analysis reports the random errors of the
#: titrant additions, all of them as one item.
ADDITIONS = '__additions__'

_SHARED_PREFIX = 'shared:'


def shared_key(name: str) -> str:
    """Source key of the shared source called *name*; no input key starts the same way."""
    return _SHARED_PREFIX + name


def is_shared(key: str) -> bool:
    """Whether *key* names a shared error source rather than an input's own uncertainty."""
    return key.startswith(_SHARED_PREFIX)


class SpecKind(Enum):
    """How an input's uncertainty is stated."""

    SIGMA = 'sigma'
    INTERVAL = 'interval'


@dataclass(frozen=True)
class InputSpec:
    """The uncertainty of one input.

    ``SIGMA`` is a precision figure — an instrument's pipetting tolerance, say —
    read as one standard deviation of a Gaussian and truncated so the perturbed
    value stays positive. ``INTERVAL`` is a plain range, sampled uniformly and
    free to be asymmetric; a binding constant carried over from an earlier fit
    arrives in that form, as an estimate with a low and a high bound.

    A relative spec is stated in percent of the input's nominal value. An
    absolute one is in the input's own unit: for ``SIGMA`` the spread itself,
    and for ``INTERVAL`` the low and high values the input may take. The titrant
    has no single nominal value, so it accepts relative specs only.
    """

    kind: SpecKind
    sigma: float = 0.0
    lo: float = 0.0
    hi: float = 0.0
    relative: bool = True

    @classmethod
    def sigma_pct(cls, sigma: float) -> 'InputSpec':
        """Gaussian with a standard deviation of *sigma* percent."""
        return cls(SpecKind.SIGMA, sigma=sigma, relative=True)

    @classmethod
    def sigma_abs(cls, sigma: float) -> 'InputSpec':
        """Gaussian with a standard deviation of *sigma* in the input's unit."""
        return cls(SpecKind.SIGMA, sigma=sigma, relative=False)

    @classmethod
    def interval_pct(cls, lo: float, hi: float) -> 'InputSpec':
        """Uniform between *lo* and *hi* percent of nominal."""
        return cls(SpecKind.INTERVAL, lo=lo, hi=hi, relative=True)

    @classmethod
    def interval_abs(cls, lo: float, hi: float) -> 'InputSpec':
        """Uniform between the values *lo* and *hi*, in the input's unit."""
        return cls(SpecKind.INTERVAL, lo=lo, hi=hi, relative=False)

    @property
    def varies(self) -> bool:
        """Whether this spec actually moves the input."""
        if self.kind is SpecKind.SIGMA:
            return self.sigma > 0
        return self.hi > self.lo


@dataclass(frozen=True)
class SharedSource:
    """An error several inputs have in common: one stock, balance or pipette behind all of them.

    A precision figure of one physical thing, so a Gaussian standard deviation
    of *sigma_pct* percent; it moves every input of *inputs* (input keys, two or
    more) by the same relative offset.
    """

    name: str
    sigma_pct: float
    inputs: tuple[str, ...]


@dataclass(frozen=True)
class AdditionError:
    """Random relative error of each titrant addition, one standard deviation of *sigma_pct* percent.

    *sequential* says the additions went into one cuvette one after another, so
    every later point carries the errors of the earlier ones; otherwise every
    point is a sample prepared on its own (:func:`perturb_titrant`).
    """

    sigma_pct: float
    sequential: bool


@dataclass(frozen=True)
class ErrorModel:
    """Every stated error source of a titration's inputs; the sources are independent.

    Attributes
    ----------
    specs : Mapping[str, InputSpec]
        The error each input has alone, per input key. An input without a spec,
        or with one that does not vary, has none.
    shared : tuple[SharedSource, ...]
        The errors several inputs have in common.
    additions : AdditionError or None
        The random error of each titrant addition. The sensitivity analysis
        samples it; a fit's residual scatter already contains it, so the fit
        reads :meth:`for_fit`.
    """

    specs: Mapping[str, InputSpec] = field(default_factory=dict)
    shared: tuple[SharedSource, ...] = ()
    additions: AdditionError | None = None

    @property
    def varies(self) -> bool:
        """Whether any source moves anything."""
        return any(spec.varies for spec in self.specs.values()) or bool(self.shared) or self.additions is not None

    def source_specs(self) -> dict[str, InputSpec]:
        """The distribution of every source with an offset of its own, by source key.

        The inputs' own varying specs in the order of *specs*, then the shared
        sources in theirs, each under :func:`shared_key` of its name.
        """
        own = {key: spec for key, spec in self.specs.items() if spec.varies}
        return own | {shared_key(s.name): InputSpec.sigma_pct(s.sigma_pct) for s in self.shared}

    def loaded(self, source: str) -> tuple[str, ...]:
        """The input keys *source* moves: a shared source's inputs, the titrant for ``ADDITIONS``, else the input itself."""
        if source == ADDITIONS:
            return (TITRANT,)
        for s in self.shared:
            if source == shared_key(s.name):
                return s.inputs
        return (source,)

    def input_offsets(self, e: Mapping[str, float]) -> dict[str, float]:
        """Relative offset of every input moved by the source offsets *e* (own and shared source keys).

        An input one source moves takes that source's offset as it is, so with
        no shared source the inputs' offsets are *e* itself, float for float;
        an input several sources move takes ``prod(1 + e) - 1``.
        """
        if not self.shared:
            return dict(e)
        moved: dict[str, list[float]] = {}
        for source, offset in e.items():
            for key in self.loaded(source):
                moved.setdefault(key, []).append(offset)
        return {
            key: found[0] if len(found) == 1 else math.prod(1.0 + offset for offset in found) - 1.0
            for key, found in moved.items()
        }

    def for_fit(self) -> 'ErrorModel':
        """The sources a fit's interval reads: every one but the random error of the additions."""
        return replace(self, additions=None)

    def to_dict(self) -> dict[str, Any]:
        """The entries of a results file's ``fit_config``.

        ``input_uncertainty`` always; ``shared_sources`` when there is one and
        ``titrant_additions`` when stated.
        """
        d: dict[str, Any] = {'input_uncertainty': specs_to_dict(self.specs)}
        if self.shared:
            d['shared_sources'] = [
                {'name': s.name, 'sigma_pct': s.sigma_pct, 'inputs': list(s.inputs)} for s in self.shared
            ]
        if self.additions is not None:
            d['titrant_additions'] = {'sigma_pct': self.additions.sigma_pct, 'sequential': self.additions.sequential}
        return d

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> 'ErrorModel':
        """The model :meth:`to_dict` wrote, read from it or from a whole ``fit_config``; an absent entry states nothing."""
        additions = d.get('titrant_additions')
        return cls(
            specs=specs_from_dict(d.get('input_uncertainty') or {}),
            shared=tuple(
                SharedSource(s['name'], s['sigma_pct'], tuple(s['inputs'])) for s in d.get('shared_sources') or ()
            ),
            additions=None if additions is None else AdditionError(additions['sigma_pct'], additions['sequential']),
        )


#: Half-width of the deterministic heatmap sweep for a SIGMA spec, in standard
#: deviations. Two covers ~95% of the distribution.
_SIGMA_GRID_SPAN = 2.0


def _to_fraction(value: float, relative: bool, nominal: Optional[float], name: str) -> float:
    """Express *value* as a fraction of the input's nominal value.

    *name* names the input in the messages a user reads, so it is a display
    label, never a dict key.
    """
    if relative:
        return value / 100.0
    if nominal is None:
        raise FitRefused(
            'The titrant is a series of concentrations with no single value to measure against, '
            'so its uncertainty has to be given as a percentage.'
        )
    if nominal == 0:
        raise FitRefused(f'{name} is set to zero, so an uncertainty in its own unit says nothing about it.')
    return value / nominal


def spec_bounds(spec: InputSpec, nominal: Optional[float], name: str) -> tuple[float, float]:
    """Relative-offset range a spec spans, as fractions of nominal.

    A SIGMA spec has no hard edges, so its sweep is taken at
    ``±_SIGMA_GRID_SPAN`` standard deviations. *name* names the input in the
    messages a user reads, so it is a display label, never a dict key.
    """
    if spec.kind is SpecKind.SIGMA:
        s = _to_fraction(spec.sigma, spec.relative, nominal, name)
        return -_SIGMA_GRID_SPAN * s, _SIGMA_GRID_SPAN * s
    if spec.relative:
        return spec.lo / 100.0, spec.hi / 100.0
    # An absolute interval states the input's own low and high values, the form a
    # binding constant carried over from an earlier fit already comes in.
    if nominal is None:
        raise FitRefused(
            'The titrant is a series of concentrations with no single value to measure against, '
            'so its range has to be given as percentages.'
        )
    if nominal == 0:
        raise FitRefused(f'{name} is set to zero, so a range in its own unit says nothing about it.')
    return (spec.lo - nominal) / nominal, (spec.hi - nominal) / nominal


def axis_reaches_zero(spec: InputSpec, nominal: Optional[float], name: str) -> bool:
    """Whether a heatmap axis swept over :func:`spec_bounds` would take the input to zero or below.

    The sweep includes both ends, so a lower end at -100 % of the nominal value, to
    rounding, would fit the model with the input at zero.
    """
    return spec_bounds(spec, nominal, name)[0] <= -1.0 + 1e-9


def spec_fraction(spec: InputSpec, nominal: Optional[float], name: str, quantile):
    """Map uniform draws in (0, 1) to relative offsets.

    Going through the inverse CDF keeps the draw independent of how the
    quantile was produced, so plain random sampling and a low-discrepancy
    sequence share one definition of an input's distribution.

    One quantile gives one float; an array of quantiles gives an array of the
    same shape, which is how a whole column of a sampling design is mapped in a
    single call.
    """
    quantiles = np.asarray(quantile, dtype=float)
    if spec.kind is SpecKind.SIGMA:
        s = _to_fraction(spec.sigma, spec.relative, nominal, name)
        if s <= 0:
            offsets = np.zeros_like(quantiles)
        else:
            # Truncated at -1 so the perturbed value never reaches zero or below.
            offsets = truncnorm.ppf(quantiles, a=-1.0 / s, b=np.inf, loc=0.0, scale=s)
    else:
        lo, hi = spec_bounds(spec, nominal, name)
        offsets = lo + quantiles * (hi - lo)
    return offsets if quantiles.ndim else float(offsets)


def nominal_value(key: str, base_conditions: dict) -> Optional[float]:
    """Magnitude of an input's nominal value; ``None`` for the titrant."""
    if key == TITRANT:
        return None
    return float(base_conditions[key].magnitude)


def input_name(key: str, input_labels: Optional[dict[str, str]]) -> str:
    """Name an input the way a message shown to the user should name it.

    Parameters
    ----------
    key : str
        Input key: ``TITRANT`` or a condition key.
    input_labels : dict[str, str] or None
        Display label per input key, as the interface writes it.

    Returns
    -------
    str
        The label when one is given. Otherwise 'the titrant' for the titrant and
        a neutral phrase for a condition, so a message never shows a dict key.
    """
    label = (input_labels or {}).get(key)
    if label:
        return label
    return 'the titrant' if key == TITRANT else 'this input'


def source_name(key: str, input_labels: Optional[Mapping[str, str]] = None) -> str:
    """Name an error source the way a message shown to the user should name it.

    A shared source goes by the name it was given, the additions by what they
    are, and an input's own error by the input (:func:`input_name`).
    """
    if is_shared(key):
        return key[len(_SHARED_PREFIX) :]
    if key == ADDITIONS:
        return 'the random error of each addition'
    return input_name(key, dict(input_labels or {}))


def perturbable_inputs(base_conditions: Mapping[str, Any]) -> list[tuple[str, str]]:
    """List the inputs of an assay that can be perturbed.

    Parameters
    ----------
    base_conditions : Mapping[str, Any]
        Assay conditions as passed to the assay constructor. Values that are
        :class:`pint.Quantity` are classified by dimensionality; non-Quantity
        values (e.g. the ``mode`` string) are skipped, and so is
        ``TITRANT_STOCK``, which moves with the titrant.

    Returns
    -------
    list[tuple[str, str]]
        Ordered ``(key, kind)`` pairs: each Quantity condition, in the order
        the conditions are declared in, as ``'concentration'`` (``M``) or
        ``'binding_constant'`` (``1/M``), then ``TITRANT`` with kind
        ``'titrant'``.
    """
    inputs: list[tuple[str, str]] = []
    for key, value in base_conditions.items():
        if key == TITRANT_STOCK or not isinstance(value, Quantity):
            continue
        if value.is_compatible_with('M'):
            inputs.append((key, 'concentration'))
        elif value.is_compatible_with('1/M'):
            inputs.append((key, 'binding_constant'))
    inputs.append((TITRANT, 'titrant'))
    return inputs


# Lowest fraction of its entered value an input may take in a fit that moves
# it. The equilibrium solve needs positive totals and constants, so an offset
# stops just short of -100 %. A sigma input pays a penalty of (1/sigma)² >= 4 to
# get there even at a stated 50 %, so the floor is never active on data the
# model describes, and a fit that needs it is reported by the conflict
# diagnostics.
_INPUT_FLOOR = 1e-6


@dataclass(frozen=True)
class InputConstraint:
    """What a fit may do with one varying input, on its relative offset from the entered value.

    Attributes
    ----------
    key : str
        Condition key, or ``TITRANT``.
    sigma : float or None
        Standard deviation of the offset as a fraction of the entered value:
        the fit pays ``(offset / sigma)²`` for moving the input. ``None`` for a
        range, inside which every offset is free and outside which none is
        allowed.
    lo, hi : float
        Feasible offsets, as fractions. A sigma input may go from
        ``-1 + _INPUT_FLOOR`` to infinity.
    nominal : float or None
        The entered value in its base unit; ``None`` for the titrant.
    name : str
        What a message shown to the user calls the input (:func:`input_name`).
    """

    key: str
    sigma: float | None
    lo: float
    hi: float
    nominal: float | None
    name: str


def source_problems(
    errors: ErrorModel,
    base_conditions: Mapping[str, Any],
    input_labels: Mapping[str, str] | None = None,
) -> list[str]:
    """Every shared source and additions entry that states no error a titration can have, one sentence each.

    One sentence per fault, every fault of every source, in the order the
    sources were stated and within a source in the order above: a panel reports
    them all at once instead of handing back one per attempt, and a source with
    three things wrong with it takes one round to fix rather than three. Empty
    when the model can be used as stated.

    Parameters
    ----------
    errors : ErrorModel
        The stated sources.
    base_conditions : Mapping[str, Any]
        The entered assay conditions, which say what the inputs are.
    input_labels : Mapping[str, str], optional
        Display label per input key, for the messages.
    """
    inputs = [key for key, _ in perturbable_inputs(base_conditions)]
    found: list[str] = []
    names: set[str] = set()
    for source in errors.shared:
        name = source.name.strip()
        if not name:
            found.append('A shared error source has no name. Give it a name, or remove it.')
        elif name in names:
            found.append(f"Two shared error sources are named '{name}'. Give each its own name.")
        names.add(name)
        if not source.sigma_pct > 0:
            found.append(
                f"The uncertainty of the shared error source '{name}' has to be above zero. "
                'Enter it in percent, or remove the source.'
            )
        unknown = [key for key in source.inputs if key not in inputs]
        if unknown:
            labels = [(input_labels or {}).get(key) for key in unknown]
            found.append(
                f"The shared error source '{name}' applies to {', '.join(labels) if all(labels) else 'an input'}, "
                'which this assay does not have as an input. Choose the assay again and restate the shared error '
                'sources.'
            )
        if len(set(source.inputs)) < 2:
            found.append(
                f"A shared error source has to apply to at least two inputs. '{name}' applies to "
                f'{"one" if source.inputs else "none"}: tick a second input, or remove it and enter the '
                'uncertainty on the input itself.'
            )
    if errors.additions is not None and not errors.additions.sigma_pct > 0:
        found.append(
            "The random error of each addition has to be above zero. Enter it in percent, or set it to 'none'."
        )
    return found


def validate(
    errors: ErrorModel,
    base_conditions: Mapping[str, Any],
    input_labels: Mapping[str, str] | None = None,
) -> None:
    """Refuse a shared source or an additions entry that states no error a titration can have.

    Raises
    ------
    FitRefused
        A ``ValueError`` written for the user, carrying the first sentence
        :func:`source_problems` finds: a shared source without a name, with a
        name another one has, with an uncertainty that is not above zero,
        applied to fewer than two inputs or to an input the assay does not
        have; an error of the additions that is not above zero. The panel that
        states the sources shows every sentence, so a run is refused over what
        is still unfixed rather than over something new.
    """
    found = source_problems(errors, base_conditions, input_labels)
    if found:
        raise FitRefused(found[0])


def constraints(
    errors: ErrorModel,
    base_conditions: Mapping[str, Any],
    input_labels: Mapping[str, str] | None = None,
) -> tuple[InputConstraint, ...]:
    """The constraint of every varying source of *errors* on its relative offset.

    The inputs' own sources come first, in :func:`perturbable_inputs` order,
    each under its input key; then one per shared source, under
    :func:`shared_key` of its name and with no entered value of its own.
    ``ErrorModel.input_offsets`` turns the offsets of these sources into the
    offsets of the inputs.

    Parameters
    ----------
    errors : ErrorModel
        The stated sources. An input without a spec, or with one that does not
        vary, has no error of its own.
    base_conditions : Mapping[str, Any]
        The entered assay conditions.
    input_labels : Mapping[str, str], optional
        Display label per input key, for the messages.

    Raises
    ------
    FitRefused
        A ``ValueError`` written for the user, naming the input: a spec for an
        input the assay does not have, an uncertainty of the titrant given in a
        unit, a negative standard deviation, a range whose upper end is below
        its lower end, a range that takes the input to zero, or what
        :func:`validate` refuses.
    """
    validate(errors, base_conditions, input_labels)
    specs = errors.specs
    order = [key for key, _ in perturbable_inputs(base_conditions)]
    unknown = [key for key in specs if key not in order]
    if unknown:
        names = [(input_labels or {}).get(key) for key in unknown]
        raise FitRefused(
            f'An uncertainty is stated for {", ".join(names) if all(names) else "an input"}, which this assay does '
            'not have as an input. Choose the assay again and restate the input uncertainties.'
        )
    found = []
    for key in order:
        spec = specs.get(key)
        if spec is None:
            continue
        name = input_name(key, dict(input_labels or {}))
        nominal = nominal_value(key, dict(base_conditions))
        if spec.kind is SpecKind.SIGMA:
            if spec.sigma < 0:
                raise FitRefused(f'The uncertainty of {name} is negative. Enter zero or a positive value.')
            sigma = _to_fraction(spec.sigma, spec.relative, nominal, name)
            if sigma > 0:
                found.append(InputConstraint(key, sigma, -1.0 + _INPUT_FLOOR, np.inf, nominal, name))
            continue
        if spec.hi < spec.lo:
            raise FitRefused(f'The range of {name} ends below where it starts. Enter the lower end first.')
        lo, hi = spec_bounds(spec, nominal, name)
        if hi > lo:
            if lo < -1.0 + _INPUT_FLOOR:
                raise FitRefused(
                    f'The range of {name} reaches zero, where the binding model has no fit at its lower end. '
                    'Raise the lower end of the range.'
                )
            found.append(InputConstraint(key, None, lo, hi, nominal, name))
    for source in errors.shared:
        found.append(
            InputConstraint(
                shared_key(source.name), source.sigma_pct / 100.0, -1.0 + _INPUT_FLOOR, np.inf, None, source.name
            )
        )
    return tuple(found)


def specs_to_dict(specs: Mapping[str, InputSpec]) -> dict[str, dict]:
    """The specs as written to a results file: ``{key: {kind, sigma, lo, hi, relative}}``."""
    return {
        key: {'kind': s.kind.value, 'sigma': s.sigma, 'lo': s.lo, 'hi': s.hi, 'relative': s.relative}
        for key, s in specs.items()
    }


def specs_from_dict(d: Mapping[str, Mapping]) -> dict[str, InputSpec]:
    """The specs a results file holds."""
    return {
        key: InputSpec(SpecKind(v['kind']), sigma=v['sigma'], lo=v['lo'], hi=v['hi'], relative=v['relative'])
        for key, v in d.items()
    }


def perturb_titrant(x: np.ndarray, deltas: np.ndarray, sequential: bool, titrant_stock: Optional[float]) -> np.ndarray:
    """The titrant series with a relative error on the volume of every addition.

    Point i holds the cumulative stock volume ``w_i = W_i / V0 = x_i / (c_T - x_i)``
    per sample volume, ``c_T`` the stock concentration; with no stock declared
    the additions do not dilute and ``w_i = x_i``. Added one after another into
    one cuvette, addition j comes out as ``(w_j - w_{j-1}) (1 + delta_j)`` and
    point i carries every error up to its own,
    ``w'_i = w_i + sum_{j<=i} (w_j - w_{j-1}) delta_j``; prepared separately,
    ``w'_i = w_i (1 + delta_i)``. The concentration follows as
    ``x'_i = c_T w'_i / (1 + w'_i)``, evaluated as the change from ``x_i``,

        x'_i - x_i = c_T (w'_i - w_i) / ((1 + w_i) (1 + w'_i)),

    which is exact and returns *x* itself where no addition is in error.

    Parameters
    ----------
    x : np.ndarray
        Titrant concentrations in the cuvette, in file order.
    deltas : np.ndarray
        Relative volume error per point: of the addition that made it
        (*sequential*), or of the one addition of its sample.
    sequential : bool
        Whether the additions went into one cuvette one after another.
    titrant_stock : float or None
        Stock concentration in the unit of *x*; ``None`` when no dilution is declared.

    Raises
    ------
    FitRefused
        When *sequential* and the series falls somewhere: additions into one
        cuvette only raise the concentration.
    """
    x = np.asarray(x, dtype=float)
    deltas = np.asarray(deltas, dtype=float)
    w = x if titrant_stock is None else x / (titrant_stock - x)
    if sequential:
        falls = np.flatnonzero(np.diff(x) < 0)
        if falls.size:
            i = int(falls[0]) + 1
            raise FitRefused(
                f'The titrant concentration falls at point {i + 1} of the data '
                f'({Quantity(x[i], "M"):.4g~P} after {Quantity(x[i - 1], "M"):.4g~P}), '
                'which additions into one cuvette cannot do. '
                "Choose 'separately prepared samples' or check the order of the data."
            )
        shift = np.cumsum(np.diff(w, prepend=0.0) * deltas)
    else:
        shift = w * deltas
    if titrant_stock is None:
        return x + shift
    return x + titrant_stock * shift / ((1.0 + w) * (1.0 + w + shift))
