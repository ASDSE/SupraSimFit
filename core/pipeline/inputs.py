"""The entered inputs of a fit and how their uncertainty is stated.

A fitted Ka rests on inputs the user entered: every concentration and binding
constant among the assay conditions, and the titrant series, which moves as one
scale factor under the key ``TITRANT``. :class:`InputSpec` states one input's
uncertainty the way the interface collects it — a standard deviation or a
range, in percent of the entered value or in the input's own unit. The
sensitivity analysis samples these specs; the input-aware interval reads them
through :func:`constraints`, which turns every varying spec into an
:class:`InputConstraint` on the input's relative offset ``e`` from its entered
value, ``input = entered * (1 + e)``.

Layering: this module must not import from ``gui.*``. Inputs are classified by
pint dimensionality of the passed condition Quantities (``M`` → concentration,
``1/M`` → binding constant); display labels are derived in the GUI layer and
passed in wherever a message names an input.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional

import numpy as np
from scipy.stats import truncnorm

from core.assays.base import TITRANT
from core.pipeline.varpro import FitRefused
from core.units import Quantity

__all__ = [
    'TITRANT',
    'InputConstraint',
    'InputSpec',
    'SpecKind',
    'axis_reaches_zero',
    'constraints',
    'input_name',
    'nominal_value',
    'perturbable_inputs',
    'spec_bounds',
    'spec_fraction',
    'specs_from_dict',
    'specs_to_dict',
]


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


def perturbable_inputs(base_conditions: Mapping[str, Any]) -> list[tuple[str, str]]:
    """List the inputs of an assay that can be perturbed.

    Parameters
    ----------
    base_conditions : Mapping[str, Any]
        Assay conditions as passed to the assay constructor. Values that are
        :class:`pint.Quantity` are classified by dimensionality; non-Quantity
        values (e.g. the ``mode`` string) are skipped.

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
        if not isinstance(value, Quantity):
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


def constraints(
    specs: Mapping[str, InputSpec],
    base_conditions: Mapping[str, Any],
    input_labels: Mapping[str, str] | None = None,
) -> tuple[InputConstraint, ...]:
    """The constraint of every input whose spec varies, in :func:`perturbable_inputs` order.

    Parameters
    ----------
    specs : Mapping[str, InputSpec]
        Stated uncertainty per input key. An input without a spec, or with one
        that does not vary, is taken as entered.
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
        its lower end, or a range that takes the input to zero.
    """
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
