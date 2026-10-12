"""Fitting pipeline orchestration.

One fit of one dataset: build the assay, project out the signal parameters and
search the Ka box (:mod:`core.pipeline.varpro`), cut a profile-likelihood
interval per binding constant, and record what the fit was made on. A dataset
of several replicates is fitted through their average, with an explicit test of
the assumption that average rests on — that every replicate shares its binding
constants — deciding which of them enter it.

Every interval rests on the inputs the user entered. An input given an
uncertainty (:mod:`core.pipeline.inputs`) is free to move within it while Ka is
profiled (:mod:`core.pipeline.input_aware`), and the headline interval is the
one that lets them; the fit at the entered inputs and its own interval stay
beside it as :class:`ConditionalFit`. :attr:`FitResult.diagnostics` holds what
the tests of :mod:`core.pipeline.diagnostics` say about the model and the
inputs.

:func:`summarize_parameters` is the single source of every reported row: the
estimate, its interval and, in per-replicate mode, the spread of the
replicates' own fits.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Literal, Mapping, Optional, Tuple, Type

import numpy as np

from core.assays import ASSAY_CLASSES
from core.assays.base import BaseAssay
from core.assays.dye_alone import DyeAloneAssay
from core.assays.registry import ASSAY_REGISTRY, AssayType, ParamKind
from core.data_processing.measurement_set import MeasurementSet
from core.models.equilibrium import MODEL_ARITHMETIC, legacy_arithmetic
from core.optimizer.ensemble import describe, describe_log10
from core.optimizer.filters import calculate_fit_metrics
from core.pipeline.diagnostics import (
    FitDiagnostics,
    InputShift,
    MisfitTest,
    lack_of_fit,
    no_scatter,
    runs_test,
    verdict,
)
from core.pipeline.input_aware import (
    AwareFit,
    AwareResult,
    conflict,
    fit_jacobian,
    input_aware,
    input_shifts,
    misfit_design,
)
from core.pipeline.inputs import TITRANT, ErrorModel, constraints
from core.pipeline.noise import NoiseLaw, noise_law
from core.pipeline.varpro import (
    LEVEL,
    FitRefused,
    KaInterval,
    ProjectedFit,
    Projection,
    ReplicateTest,
    on_ka_bound,
    replicate_outliers,
)
from core.units import Q_, Quantity

# The fit uses the measured concentrations; the plotted/exported curve is
# evaluated on this denser grid so the line is smooth between data points.
_FIT_CURVE_POINTS = 300

# Residual degrees of freedom a fit needs before the signs of its residuals are
# tested for runs. Below three, what the fit could not follow is carried by one
# or two numbers and the number of runs says nothing about the model.
_RUNS_TEST_DOF = 3

#: Version of the results-file layout :meth:`FitResult.to_dict` writes. A file
#: without the entry was written before intervals were reported and is read by
#: :meth:`FitResult._from_legacy_dict`; a larger number is a file this version
#: cannot read.
RESULT_FORMAT = 2

#: Unit of each condition a results file stores as a bare number, with no
#: ``condition_units`` entry: the unit its assay holds that condition in.
_BARE_CONDITION_UNITS = {'Ka_dye': '1/M', 'h0': 'M', 'g0': 'M', 'd0': 'M', 'fixed_conc': 'M'}


@dataclass(frozen=True)
class ConditionalFit:
    """The same fit with every entered input taken as exact.

    What a fit reports beside its headline whenever the headline lets the
    inputs move: the least-squares fit at the entered inputs, and the interval
    the data leave for each binding constant when no input may shift.

    Attributes
    ----------
    parameters : dict[str, Quantity]
        Parameter name → its value at the entered inputs.
    intervals : dict[str, KaInterval]
        Interval of every binding constant the fit was free to move.
    rmse, r_squared : float
        Measured against the signal the fit was made on.
    """

    parameters: Dict[str, Quantity]
    intervals: Dict[str, KaInterval]
    rmse: float
    r_squared: float

    def to_dict(self) -> Dict[str, Any]:
        """Every field, as written to a results file."""
        return {
            'parameters': {k: float(v.magnitude) for k, v in self.parameters.items()},
            'parameter_units': {k: str(v.units) for k, v in self.parameters.items()},
            'intervals': {k: v.to_dict() for k, v in self.intervals.items()},
            'rmse': self.rmse,
            'r_squared': self.r_squared,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'ConditionalFit':
        """The conditional fit a results file holds."""
        units = d['parameter_units']
        return cls(
            parameters={k: Q_(v, units[k]) for k, v in d['parameters'].items()},
            intervals={k: KaInterval.from_dict(v) for k, v in d['intervals'].items()},
            rmse=d['rmse'],
            r_squared=d['r_squared'],
        )


@dataclass
class FitResult:
    """Serializable container for one fit.

    All fitted parameter values are stored as ``pint.Quantity`` objects with
    proper units.

    Attributes
    ----------
    parameters : dict[str, Quantity]
        Parameter name → the least-squares fit's value, at the inputs where
        the fit put them (``input_shifts``).
    rmse : float
        RMSE of the fit against the signal it was fitted to.
    r_squared : float
        R² of the fit against the signal it was fitted to.
    x_fit : Quantity
        Dense concentration grid spanning the data range, for plotting a
        smooth fit curve (not the fitting grid).
    y_fit : Quantity
        Model prediction at ``x_fit`` (the smooth curve).
    assay_type : str
        Assay type name (e.g. ``"GDA"``, ``"IDA"``).
    model_name : str
        Model identifier (e.g. ``"equilibrium_4param"``, ``"linear"``).
    conditions : dict[str, Any]
        Assay conditions used (Quantity values for ``Ka_dye``, ``h0``, etc.).
    fit_config : dict[str, Any]
        Snapshot of the fitting configuration.
    measurement_set_id : str | None
        UUID of the source MeasurementSet (``None`` when fitted directly).
    source_file : str | None
        Original filename, if known.
    id : str
        Auto-generated UUID (hex).
    timestamp : str
        ISO-8601 creation timestamp.
    metadata : dict[str, Any]
        Additional metadata about the fit. A fit made from a
        :class:`MeasurementSet` records what it was made on:
        ``active_replica_ids`` (the replicates it was given),
        ``replica_ids_fit`` and ``replica_failures`` for a per-replicate fit
        (the replicates it used and those it left out, with the reason),
        ``replicate_test`` (the level, each replicate's p-value in the
        shared-Ka test and, for each replicate left out, whether for its
        binding constants — ``'ka'`` — or its scatter — ``'scatter'`` — when
        the replicates were tested),
        ``data_fingerprint`` (:meth:`MeasurementSet.fingerprint`),
        ``quality_scored_on`` (``'fitted_replicates'``: every RMSE and R² was
        measured against the replicates the fit used) and ``model_arithmetic``
        (:data:`~core.models.equilibrium.MODEL_ARITHMETIC`, the equilibrium
        arithmetic that reproduces every score to within ``_REPRODUCE_RTOL`` —
        the arithmetic that computed them for a fit made here, and the present
        one for a checked copy of a file that records none). Read the
        replicates through :func:`fit_replica_ids` and
        :func:`input_replica_ids`.
    intervals : dict[str, KaInterval] | None
        Profile-likelihood confidence interval of every binding constant the
        fit was free to move, with every input as free as its stated
        uncertainty allows. ``None`` when the result carries no interval: a
        dye-alone calibration, or a result imported from a file written before
        intervals were reported.
    degenerate_keys : tuple[str, ...]
        Signal parameters the data determine only in combination at the fitted
        binding constants, so each of their values is one member of a family
        that reconstructs the same curve.
    replica_fits : list[FitResult] | None
        In per-replicate mode, the fit of every replicate the fit was given on
        its own, each recording its replicate in ``metadata['replica_id']`` and
        carrying no interval. ``None`` for a fit of one signal.
    conditional : ConditionalFit | None
        The same fit with the entered inputs held exactly where they were
        entered. ``None`` for a dye-alone calibration and for a result imported
        from a file written before the inputs could move. With no input given
        an uncertainty the fit above is that fit: same numbers, and the very
        same :class:`~core.pipeline.varpro.KaInterval` objects.
    input_shifts : dict[str, InputShift]
        Where the fit put every error source that was free to move, by source
        key (an input's own key, or
        :func:`~core.pipeline.inputs.shared_key` of a shared source): as a
        fraction of the entered value and in units of the uncertainty stated
        for it. Empty when nothing was free to move, which is also what says that the
        headline above is the conditional fit.
    diagnostics : FitDiagnostics | None
        What the misfit tests and the conflict statistic say about the model
        and the entered inputs (:mod:`core.pipeline.diagnostics`).
    aware : AwareResult | None
        The penalised profiles the headline interval was cut from, for the
        Identifiability tab. It is the fit's own working, not part of what a
        results file holds, so it is ``None`` after an import.
    noise : NoiseLaw | None
        The noise law the replicates behind the fitted signal showed
        (:mod:`core.pipeline.noise`), which is what weighted the fit's
        titration points; where they could not show one, the statement that
        the noise was taken as constant. ``None`` on a dye-alone calibration,
        which estimates no law, on a replicate's own fit inside
        ``replica_fits``, where the sentence belongs to the reported fit, and
        on a result imported from a file written before the law was recorded.
    """

    parameters: Dict[str, Quantity]
    rmse: float
    r_squared: float
    x_fit: Quantity
    y_fit: Quantity
    assay_type: str
    model_name: str
    conditions: Dict[str, Any] = field(default_factory=dict)
    fit_config: Dict[str, Any] = field(default_factory=dict)
    measurement_set_id: Optional[str] = None
    source_file: Optional[str] = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    intervals: Optional[Dict[str, KaInterval]] = None
    degenerate_keys: Tuple[str, ...] = ()
    replica_fits: Optional[List['FitResult']] = None
    conditional: Optional[ConditionalFit] = None
    input_shifts: Dict[str, InputShift] = field(default_factory=dict)
    diagnostics: Optional[FitDiagnostics] = None
    aware: Optional[AwareResult] = None
    noise: Optional[NoiseLaw] = None

    @property
    def per_replica(self) -> bool:
        """Whether the fit tested its replicates and reports their own fits."""
        return bool(self.fit_config.get('per_replicate'))

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a JSON-safe dictionary.

        ``Quantity`` fields are converted to ``{value, unit}`` pairs.
        ``np.ndarray`` / Quantity array fields are converted to plain
        Python lists.

        Returns
        -------
        dict[str, Any]
        """
        # Serialize parameter magnitudes, emitting each unit token from the
        # Quantity itself (not a registry lookup) so the JSON is self-describing
        # and correct even when assay_type is unknown to the registry — the
        # parameters already carry authoritative units.
        params_serial = {}
        units = {}
        for k, v in self.parameters.items():
            params_serial[k] = float(v.magnitude)
            units[k] = str(v.units)

        # Serialize conditions, keeping each Quantity's unit token so the
        # conditions survive a round-trip as Quantities (not bare floats).
        cond_serial = {}
        cond_units = {}
        for k, v in self.conditions.items():
            if isinstance(v, Quantity):
                cond_serial[k] = float(v.magnitude)
                cond_units[k] = str(v.units)
            else:
                cond_serial[k] = v

        return {
            'format': RESULT_FORMAT,
            'id': self.id,
            'timestamp': self.timestamp,
            'measurement_set_id': self.measurement_set_id,
            'source_file': self.source_file,
            'assay_type': self.assay_type,
            'model_name': self.model_name,
            'conditions': cond_serial,
            'fit_config': self.fit_config,
            'parameters': params_serial,
            'parameter_units': units,
            'condition_units': cond_units,
            'rmse': self.rmse,
            'r_squared': self.r_squared,
            'x_fit': self.x_fit.magnitude.tolist(),
            'y_fit': self.y_fit.magnitude.tolist(),
            'x_fit_unit': str(self.x_fit.units),
            'y_fit_unit': str(self.y_fit.units),
            'metadata': self.metadata,
            'intervals': None if self.intervals is None else {k: v.to_dict() for k, v in self.intervals.items()},
            'degenerate_keys': list(self.degenerate_keys),
            'replica_fits': None if self.replica_fits is None else [rf.to_dict() for rf in self.replica_fits],
            'conditional': None if self.conditional is None else self.conditional.to_dict(),
            'input_shifts': {k: v.to_dict() for k, v in self.input_shifts.items()},
            'diagnostics': None if self.diagnostics is None else self.diagnostics.to_dict(),
            'noise': None if self.noise is None else self.noise.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'FitResult':
        """Reconstruct a ``FitResult`` from a results file's dictionary.

        The ``format`` entry decides how it is read: the current layout, or —
        with no entry at all — a file written before intervals were reported.
        A file of the current layout that holds no conditional fit, no input
        shifts and no diagnostics was written by a fit whose inputs could not
        move, and reads with those fields empty. One that names no noise law,
        either because it holds ``null`` there or because it was written
        before the law was recorded, reads with :attr:`FitResult.noise`
        ``None``.

        Raises
        ------
        ValueError
            When the file names a layout this version does not know.
        """
        fmt = d.get('format')
        if fmt is None:
            return cls._from_legacy_dict(d)
        if fmt != RESULT_FORMAT:
            raise ValueError(
                f'This results file was written by a newer version of SupraSimFit (file layout {fmt}; this '
                f'version reads {RESULT_FORMAT}). Update SupraSimFit and open the file again.'
            )
        intervals = d.get('intervals')
        replica_fits = d.get('replica_fits')
        conditional = d.get('conditional')
        diagnostics = d.get('diagnostics')
        noise = d.get('noise')
        return cls(
            **_common_fields(d),
            intervals=None if intervals is None else {k: KaInterval.from_dict(v) for k, v in intervals.items()},
            degenerate_keys=tuple(d.get('degenerate_keys') or ()),
            replica_fits=None if replica_fits is None else [cls.from_dict(rf) for rf in replica_fits],
            conditional=None if conditional is None else ConditionalFit.from_dict(conditional),
            input_shifts={k: InputShift.from_dict(v) for k, v in (d.get('input_shifts') or {}).items()},
            diagnostics=None if diagnostics is None else FitDiagnostics.from_dict(diagnostics),
            noise=None if noise is None else NoiseLaw.from_dict(noise),
        )

    @classmethod
    def _from_legacy_dict(cls, d: Dict[str, Any]) -> 'FitResult':
        """A results file written before intervals were reported.

        Such a file holds a multi-start estimate: the fit it reports, and the
        pool of accepted attempts, the attempt record and the statistics mode
        that estimate was summarised through. The fit is kept — its parameters,
        RMSE, R², curve, conditions, replicate record and configuration
        snapshot — and the rest is read past. The result carries no interval,
        and :func:`verify_imported_result` checks its numbers against the data
        as it does for any other file.
        """
        return cls(**_common_fields(d))


def _common_fields(d: Dict[str, Any]) -> Dict[str, Any]:
    """The fields every results file holds, as :class:`FitResult` keyword arguments."""
    # Look up units from the file's own tokens first, then the registry.
    param_units = d.get('parameter_units') or {}
    if not param_units:
        try:
            at = AssayType[d['assay_type']]
            param_units = dict(ASSAY_REGISTRY[at].units)
        except KeyError:
            param_units = {}

    def _unit_for(key: str) -> str:
        unit = param_units.get(key)
        if unit is None:
            # Fail loud rather than silently loading a real unit (e.g. 1/M)
            # as dimensionless, which would drop it from the result with no
            # signal. The GUI import path turns this into a user warning.
            raise ValueError(
                f"FitResult.from_dict: no unit for parameter '{key}' "
                f'(assay_type={d.get("assay_type")!r}). The file predates '
                'parameter_units or uses an unknown assay type, so it cannot '
                'be loaded without corrupting units.'
            )
        return unit

    # Re-wrap conditions into Quantities from the file's unit tokens. A file
    # without them stores each numeric condition as its magnitude in the
    # unit the assay holds it in; other values (the DBA ``mode``) stay as
    # they are.
    condition_units = d.get('condition_units') or {}
    conditions = {}
    for k, v in d.get('conditions', {}).items():
        unit = condition_units.get(k)
        if unit is None and isinstance(v, (int, float)) and not isinstance(v, bool):
            unit = _BARE_CONDITION_UNITS.get(k)
            if unit is None:
                raise ValueError(
                    f"FitResult.from_dict: no unit for condition '{k}' "
                    f'(assay_type={d.get("assay_type")!r}), so it cannot be loaded without corrupting units.'
                )
        if unit is not None:
            conditions[k] = Q_(v, unit)
        else:
            # JSON has no tuple: a condition that lists keys (``stock_contains``) is held as one.
            conditions[k] = tuple(v) if isinstance(v, list) else v

    return dict(
        parameters={k: Q_(v, _unit_for(k)) for k, v in d['parameters'].items()},
        rmse=d['rmse'],
        r_squared=d['r_squared'],
        # x_fit / y_fit carry their own unit tokens; a file without them holds
        # the M / au the app has always stored them in.
        x_fit=Q_(np.asarray(d['x_fit']), d.get('x_fit_unit', 'M')),
        y_fit=Q_(np.asarray(d['y_fit']), d.get('y_fit_unit', 'au')),
        assay_type=d['assay_type'],
        model_name=d['model_name'],
        conditions=conditions,
        fit_config=d.get('fit_config', {}),
        measurement_set_id=d.get('measurement_set_id'),
        source_file=d.get('source_file'),
        id=d.get('id', uuid.uuid4().hex),
        timestamp=d.get('timestamp', datetime.now(timezone.utc).isoformat()),
        metadata=d.get('metadata', {}),
    )


@dataclass
class FitConfig:
    """Configuration for the fitting pipeline.

    ``custom_bounds`` overrides the registry's default bounds per parameter;
    ``per_replica`` decides whether the replicates are fitted and tested
    individually beside the fit of their average; ``errors`` states how well
    the entered inputs are known (:class:`core.pipeline.inputs.ErrorModel`), of
    which a fit reads ``errors.for_fit()``. An input no source moves is taken
    as exact, and with no source at all the reported interval is the one
    conditional on every entered input.

    ``input_labels`` is how the interface writes each input's name. A fit that
    cannot be made with the inputs as free as they were stated to be says so by
    naming them, and it has to name them the way the panel does; without the
    labels such a message can only call an input an input.
    """

    custom_bounds: Optional[Dict[str, Tuple[Quantity, Quantity]]] = None
    per_replica: bool = True
    errors: ErrorModel = field(default_factory=ErrorModel)
    input_labels: Dict[str, str] = field(default_factory=dict)


def _config_to_dict(config: FitConfig) -> Dict[str, Any]:
    """Serialize a FitConfig to a plain dict.

    ``per_replicate`` records what the fit did, not what the configuration
    asked for: it is written ``False`` here and set to ``True`` by
    :func:`fit_measurement_set_per_replica`, the one path that fits and tests
    the replicates individually. A fit of one signal therefore never reports
    replicate fits it does not hold.
    """
    # Provenance only (never deserialized back): keep the unit token so a bound
    # entered in µM / MM⁻¹ is not stored as a unit-ambiguous bare number. A
    # bound with no limit — the empty upper box of a signal parameter — is
    # written as null, which is what JSON has for it; a results file is read by
    # other programs too, and none of them accepts a float outside the format.
    custom_bounds: Optional[Dict[str, list]] = None
    if config.custom_bounds is not None:
        custom_bounds = {}
        for key, (lo, hi) in config.custom_bounds.items():
            custom_bounds[key] = [_finite_or_none(lo), _finite_or_none(hi), str(lo.units)]
    return {
        'custom_bounds': custom_bounds,
        # The on-disk key of the per-replicate mode in exported results files.
        'per_replicate': False,
        'level': LEVEL,
        **config.errors.for_fit().to_dict(),
    }


def _finite_or_none(bound: Quantity) -> Optional[float]:
    """The magnitude of *bound* as a results file holds it: the number, or ``None`` for no limit."""
    value = float(bound.magnitude)
    return value if math.isfinite(value) else None


def _resolve_bounds(
    assay: BaseAssay,
    custom_bounds: Optional[Dict[str, Tuple[Quantity, Quantity]]],
) -> Dict[str, Tuple[Quantity, Quantity]]:
    """Merge user overrides with registry defaults -> named bounds dict."""
    bounds_dict = assay.get_default_bounds()
    if custom_bounds is not None:
        unknown = set(custom_bounds) - set(assay.parameter_keys)
        if unknown:
            raise ValueError(
                f'Unknown parameter(s) in custom_bounds: {sorted(unknown)}. Valid keys: {list(assay.parameter_keys)}'
            )
        bounds_dict.update(custom_bounds)
    return bounds_dict


def _wrap_params_as_quantities(
    params: np.ndarray,
    assay: BaseAssay,
) -> Dict[str, Quantity]:
    """Wrap the fit's float params into a named Quantity dict."""
    units = ASSAY_REGISTRY[assay.assay_type].units
    result = {}
    for key, value in zip(assay.parameter_keys, params):
        unit = units.get(key)
        if unit is None:
            raise KeyError(
                f"No registry unit declared for parameter '{key}' of {assay.assay_type.name}; "
                'cannot attach units to the fit result.'
            )
        result[key] = Q_(float(value), unit)
    return result


def fit_view(
    assay: BaseAssay,
    params: np.ndarray,
    offsets: Optional[Mapping[str, float]] = None,
) -> Tuple[float, float, Quantity, Quantity]:
    """Reported fields of one parameter vector against *assay*'s signal.

    The single source for "a parameter vector → its RMSE/R² and plotted
    curve", used both when a fit is made and when an imported fit is measured
    again on the data loaded now.

    Parameters
    ----------
    assay : BaseAssay
        The data and the inputs as entered.
    params : np.ndarray
        Parameter vector in ``assay.parameter_keys`` order.
    offsets : Mapping[str, float], optional
        Where a fit put the entered inputs, as a fraction of each and by input
        key (``AwareFit.input_offsets``). The model is then
        evaluated on the moved inputs, the titrant included, while the curve
        stays drawn against the concentrations as entered — the axis the
        measured points sit on.

    Returns
    -------
    tuple[float, float, Quantity, Quantity]
        ``(rmse, r_squared, x_fit, y_fit)``.
    """
    moved = assay.with_inputs(offsets) if offsets else assay
    titrant = 1.0 + (offsets or {}).get(TITRANT, 0.0)
    x_mag = assay.x_data.magnitude
    y_pred = moved.forward_model(params, x=x_mag * titrant)
    rmse, r_squared = calculate_fit_metrics(assay.y_data.magnitude, y_pred.magnitude)
    x_dense = np.linspace(float(x_mag.min()), float(x_mag.max()), _FIT_CURVE_POINTS)
    return rmse, r_squared, Q_(x_dense, 'M'), moved.forward_model(params, x=x_dense * titrant)


@dataclass(frozen=True)
class ParameterSummary:
    """One reported row: a fitted parameter, or its log₁₀ twin.

    Attributes
    ----------
    key : str
        Parameter key (e.g. ``"Ka_dye"``). A log twin repeats its source key.
    is_log : bool
        ``True`` for a log₁₀ twin row. ``estimate``, ``interval`` and
        ``replicates`` are then in log₁₀ of the parameter and carry no unit —
        but ``unit`` still names the underlying parameter's unit, so a label
        can read ``log₁₀(Ka / M⁻¹)``.
    estimate : float
        The fit's value for this row. Where *estimate_at_bound* is set this is
        the edge of the Ka box the search stopped on, not an estimate: the
        curves are drawn from it, and no view or export prints it as one.
    estimate_at_bound : str
        ``'low'`` or ``'high'`` when the fit's value of this binding constant
        sits on the lower or the upper edge of its box
        (:func:`~core.pipeline.varpro.on_ka_bound`): the data do not limit it
        on that side, so there is no estimate, only the interval. ``''``
        otherwise, on every signal parameter and on a binding constant held
        fixed by equal bounds.
    unit : str
        Unit of the underlying parameter (``""`` when it has none).
    interval : tuple[float, float] | None
        Confidence interval of this row, in the row's own scale: the interval
        of a log twin is the endpoints of the parameter's interval
        transformed, which is exact because log₁₀ is monotone. ``None`` for a
        parameter with no interval — every signal parameter, a binding
        constant held fixed, and every row of an imported result written
        before intervals were reported.
    interval_open : tuple[bool, bool]
        Per endpoint, whether the interval reaches as far as the profile goes
        rather than being closed by the data.
    interval_unsolvable : tuple[bool, bool]
        Per endpoint, whether an open side is open because the equilibrium
        model cannot be solved past it, rather than because the data leave it
        open. More data cannot close such a side.
    interval_limited_by : tuple[str, str]
        Per endpoint, the other binding constant whose bound — rather than the
        data — is what ends the profile on an open side (``''`` otherwise):
        the data would accept values further out if that constant could go
        past its bound.
    interval_split : bool
        Whether the values the data accept come in separate stretches, so the
        interval spans a gap of values they reject.
    level : float | None
        Confidence level of ``interval``; ``None`` when there is none.
    degenerate : bool
        Whether the data determine this parameter only in combination with
        others.
    replicates : dict[str, float] | None
        :func:`~core.optimizer.ensemble.describe` (or ``describe_log10`` for a
        log twin) over the values the replicates the fit used give this
        parameter in their own fits, leaving out each replicate whose own fit
        of this binding constant is on an edge of its box: a bound is not an
        estimate. A signal parameter leaves out every replicate whose own fit
        put any binding constant on an edge, since its value is then that of
        a curve pushed against the bound. ``None`` below two values.
    replicates_at_bound : int
        How many of the replicates the fit used were left out of *replicates*
        for that reason.
    conditional_estimate : float | None
        This binding constant at the entered inputs, in the row's own scale.
        ``None`` on a row that is not a binding constant and on every row of a
        fit whose inputs were all taken as entered, where the estimate above
        is already that one.
    conditional_interval : tuple[float, float] | None
        Its interval with the inputs held as entered, in the row's own scale;
        ``None`` on the same rows as *conditional_estimate*.
    conditional_open : tuple[bool, bool]
        Per endpoint of *conditional_interval*, whether it reaches as far as
        the profile goes rather than being closed by the data.
    conditional_split : bool
        Whether the values *conditional_interval* spans come in separate
        stretches, so it spans a gap of values the data reject.
    conditional_at_bound : str
        *estimate_at_bound* of *conditional_estimate*.
    one_step_p : float | None
        On the second binding constant of a two-step model, the p-value of the
        test of *interval* against the model without that step
        (:attr:`~core.pipeline.varpro.KaInterval.one_step_p`): above
        :data:`~core.pipeline.varpro.SECOND_STEP_LEVEL` the data do not show
        the second step, and the interval is open below. ``None`` on every
        other row.
    """

    key: str
    is_log: bool
    estimate: float
    estimate_at_bound: str
    unit: str
    interval: Optional[Tuple[float, float]]
    interval_open: Tuple[bool, bool]
    interval_unsolvable: Tuple[bool, bool]
    interval_limited_by: Tuple[str, str]
    interval_split: bool
    level: Optional[float]
    degenerate: bool
    replicates: Optional[Dict[str, float]]
    replicates_at_bound: int = 0
    conditional_estimate: Optional[float] = None
    conditional_interval: Optional[Tuple[float, float]] = None
    conditional_open: Tuple[bool, bool] = (False, False)
    conditional_split: bool = False
    conditional_at_bound: str = ''
    one_step_p: Optional[float] = None


def _binding_constant_keys(result: FitResult) -> set[str]:
    """The binding constants of the result's assay; none for an assay type the registry does not know."""
    try:
        kinds = ASSAY_REGISTRY[AssayType[result.assay_type]].param_kinds
    except KeyError:
        return set()
    return {k for k, kind in kinds.items() if kind is ParamKind.BINDING_CONSTANT}


def parameters_on_bound(result: FitResult) -> Dict[str, Quantity]:
    """Signal parameters the fit ended on a bound the user entered, each with that bound.

    A signal parameter is solved inside its bounds, so one that ends on a
    bound may be held there against the data and the curve with it. Zero, the
    physical lower limit of every signal parameter, is not reported, and
    neither is a parameter held fixed by equal bounds. A binding constant on a
    bound shows as an open side of its interval instead. Read from the
    parameters and the bounds the result records — a number, or ``None`` for
    a bound with no limit — so it holds for an imported result too.
    """
    ka_keys = _binding_constant_keys(result)
    hits: Dict[str, Quantity] = {}
    for key, (lo, hi, unit) in (result.fit_config.get('custom_bounds') or {}).items():
        if key in ka_keys or key not in result.parameters or lo == hi:
            continue
        value = float(result.parameters[key].to(unit).magnitude)
        for bound in (lo, hi):
            if bound is not None and bound != 0.0 and np.isclose(value, bound, rtol=1e-12, atol=0.0):
                hits[key] = Q_(bound, unit)
    return hits


def offsets_held_at_zero(result: FitResult) -> List[str]:
    """Signal offsets the fit left on a lower bound of zero, the registry's floor for an offset.

    A zero floor is right for a signal that includes its blank, and holds the
    offset against the data when the blank was subtracted before the fit. The
    bound is the one the fit was given where the result records it, the
    registry's default otherwise; an offset pinned by equal bounds is held on
    purpose and not reported. The bounded solve clips a coefficient to its
    bound, so an offset held there is exactly zero.
    """
    try:
        meta = ASSAY_REGISTRY[AssayType[result.assay_type]]
    except KeyError:
        return []
    recorded = result.fit_config.get('custom_bounds') or {}
    held = []
    for key, kind in meta.param_kinds.items():
        if kind is not ParamKind.SIGNAL_OFFSET or key not in result.parameters:
            continue
        if key in recorded:
            lo, hi, unit = recorded[key]
        else:
            low, high = meta.default_bounds[key]
            lo, hi, unit = float(low.magnitude), float(high.magnitude), str(low.units)
        if lo == 0.0 and hi != lo and float(result.parameters[key].to(unit).magnitude) <= 0.0:
            held.append(key)
    return held


def summarize_parameters(result: FitResult) -> List[ParameterSummary]:
    """Reported rows for *result* — the single source for every display.

    The fit summary table, the plot annotation and the TXT/CSV exports all
    render from this, so they cannot drift apart. A log₁₀ twin row follows each
    binding constant; its interval is the parameter's interval transformed, and
    its replicate statistics come from
    :func:`~core.optimizer.ensemble.describe_log10`, which transforms the
    replicates' values *first* — statistics of log₁₀(Ka) must come from the
    per-fit log values, because log₁₀ of a Ka spread is meaningless.

    A binding constant the fit left on an edge of its box is flagged
    (``estimate_at_bound``): the data do not limit it on that side, so the
    value is the edge and not an estimate. For the same reason the replicate
    statistics of a binding constant leave out each replicate whose own fit
    of that constant ran to an edge, and say how many they left out.

    The conditional columns are filled only where they say something the
    estimate does not: on a binding constant of a fit that let its inputs
    move. With every input as entered the fit above is the conditional one.

    Each unit comes from the parameter's own ``Quantity``, which stays correct
    even when the assay type is missing from the registry; only which
    parameters are binding constants is registry metadata.
    """
    ka_keys = _binding_constant_keys(result)
    boxes = _ka_boxes(result)
    replicates = _replicate_values(result, boxes)
    intervals = result.intervals or {}
    conditional = result.conditional if result.input_shifts else None
    rows: List[ParameterSummary] = []
    for key, value in result.parameters.items():
        unit = str(value.units) if isinstance(value, Quantity) else ''
        magnitude = float(value.magnitude) if isinstance(value, Quantity) else float(value)
        ci = intervals.get(key)
        pool, replicates_at_bound = replicates.get(key, (None, 0))
        entered = None if conditional is None or key not in ka_keys else conditional.parameters.get(key)
        entered_ci = None if conditional is None or key not in ka_keys else conditional.intervals.get(key)
        shared = dict(
            key=key,
            unit=unit,
            estimate_at_bound=_at_bound(value, boxes.get(key)),
            interval_open=(False, False) if ci is None else (ci.open_low, ci.open_high),
            interval_unsolvable=(False, False) if ci is None else (ci.unsolvable_low, ci.unsolvable_high),
            interval_limited_by=('', '') if ci is None else (ci.limited_by_low, ci.limited_by_high),
            interval_split=False if ci is None else ci.split,
            level=None if ci is None else ci.level,
            degenerate=key in result.degenerate_keys,
            replicates_at_bound=replicates_at_bound,
            conditional_open=(False, False) if entered_ci is None else (entered_ci.open_low, entered_ci.open_high),
            conditional_split=False if entered_ci is None else entered_ci.split,
            conditional_at_bound='' if entered is None else _at_bound(entered, boxes.get(key)),
            one_step_p=None if ci is None else ci.one_step_p,
        )
        rows.append(
            ParameterSummary(
                is_log=False,
                estimate=magnitude,
                interval=None if ci is None else (ci.low, ci.high),
                replicates=None if pool is None else describe(pool),
                conditional_estimate=None if entered is None else float(entered.magnitude),
                conditional_interval=None if entered_ci is None else (entered_ci.low, entered_ci.high),
                **shared,
            )
        )
        if key in ka_keys:
            rows.append(
                ParameterSummary(
                    is_log=True,
                    estimate=float(np.log10(magnitude)),
                    interval=None if ci is None else (float(np.log10(ci.low)), float(np.log10(ci.high))),
                    replicates=None if pool is None else describe_log10(pool),
                    conditional_estimate=None if entered is None else float(np.log10(entered.magnitude)),
                    conditional_interval=None
                    if entered_ci is None
                    else (float(np.log10(entered_ci.low)), float(np.log10(entered_ci.high))),
                    **shared,
                )
            )
    return rows


def _ka_boxes(result: FitResult) -> Dict[str, Tuple[Quantity, Quantity]]:
    """The box every binding constant of *result* was searched in, as the result records it.

    The bounds the fit was given where it records them, the registry's
    defaults otherwise; a binding constant held fixed by equal bounds, and one
    whose recorded box has no limit on a side, has no box to reach an edge of.
    """
    try:
        defaults = ASSAY_REGISTRY[AssayType[result.assay_type]].default_bounds
    except KeyError:
        return {}
    recorded = result.fit_config.get('custom_bounds') or {}
    boxes = {}
    for key in _binding_constant_keys(result):
        lo, hi = defaults[key]
        if key in recorded:
            low, high, unit = recorded[key]
            if low is None or high is None:
                continue
            lo, hi = Q_(low, unit), Q_(high, unit)
        if lo != hi:
            boxes[key] = (lo, hi)
    return boxes


def _at_bound(value: Quantity, box: Optional[Tuple[Quantity, Quantity]]) -> str:
    """``'low'`` or ``'high'`` when *value* sits on that edge of the Ka *box* (:func:`on_ka_bound`), else ``''``."""
    if box is None:
        return ''
    unit = value.units
    ka = float(value.magnitude)
    lo, hi = (float(bound.to(unit).magnitude) for bound in box)
    if not on_ka_bound(ka, (lo, hi)):
        return ''
    return 'low' if np.log10(ka) - np.log10(lo) <= np.log10(hi) - np.log10(ka) else 'high'


def _replicate_values(
    result: FitResult, boxes: Dict[str, Tuple[Quantity, Quantity]]
) -> Dict[str, Tuple[Optional[np.ndarray], int]]:
    """Each parameter's values across the own fits of the replicates *result* used, and how many were left out.

    A replicate whose own fit put a binding constant on an edge of its box
    (*boxes*) is left out of that constant's values: a bound is not an
    estimate. The replicate's fit of another binding constant still counts:
    it is a value of that constant. A signal parameter's values leave out a
    replicate with any binding constant on an edge, since they are those of a
    curve pushed against it. The values are ``None`` unless at least two
    remain, and there are none at all unless at least two of the replicates
    the fit was given entered its average: one value is
    the fit itself seen again, and a replicate the fit left out describes data
    the fit does not.
    """
    used = set(result.metadata.get('replica_ids_fit') or ())
    fits = [rf for rf in result.replica_fits or () if rf.metadata.get('replica_id') in used]
    if len(fits) < 2:
        return {}
    on_edge = [
        {k for k, box in boxes.items() if k in rf.parameters and _at_bound(rf.parameters[k], box)} for rf in fits
    ]
    ka_keys = _binding_constant_keys(result)
    pooled = {}
    for key in result.parameters:
        if not all(key in rf.parameters for rf in fits):
            continue
        keep = [rf for rf, edges in zip(fits, on_edge) if not (key in edges if key in ka_keys else edges)]
        values = np.array([float(rf.parameters[key].magnitude) for rf in keep]) if len(keep) >= 2 else None
        pooled[key] = (values, len(fits) - len(keep))
    return pooled


def fit_replica_ids(result: FitResult) -> Optional[List[str]]:
    """Replicates *result* was fitted on, whose average its quality is measured against.

    A per-replicate fit's ``replica_ids_fit`` (the replicates that entered the
    average), otherwise the ``active_replica_ids`` a fit of the average was
    given.

    Returns
    -------
    list[str] | None
        The replicate ids, or None when the result does not record them.
    """
    used = result.metadata.get('replica_ids_fit', result.metadata.get('active_replica_ids'))
    return None if used is None else list(used)


def input_replica_ids(result: FitResult) -> Optional[List[str]]:
    """Replicates *result* was given: the ones it used and the ones it left out.

    ``active_replica_ids`` when recorded; otherwise, for a per-replicate fit,
    the replicates it used followed by those in ``replica_failures``.

    Returns
    -------
    list[str] | None
        The replicate ids, or None when the result does not record them.
    """
    given = result.metadata.get('active_replica_ids')
    if given is not None:
        return list(given)
    used = result.metadata.get('replica_ids_fit')
    if used is None:
        return None
    return list(used) + [rid for rid in result.metadata.get('replica_failures') or {} if rid not in used]


def _record_assay(ms: MeasurementSet, result: FitResult, replica_ids: List[str]) -> BaseAssay:
    """Average of *replica_ids* in *ms*, with *result*'s conditions and assay type."""
    assay_cls = ASSAY_CLASSES[AssayType[result.assay_type]]
    return ms.with_active(replica_ids).to_assay(assay_cls, conditions=result.conditions, use_average=True)


def fit_assay(
    assay: BaseAssay,
    config: Optional[FitConfig] = None,
    *,
    measurement_set_id: Optional[str] = None,
    source_file: Optional[str] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    replicate_signals: Optional[np.ndarray] = None,
) -> FitResult:
    """Fit an assay by variable projection, with the entered inputs as free as they were stated to be.

    The signal parameters are solved exactly inside their bounds at every set
    of binding constants, so the search runs over the one or two binding
    constants alone and its minimum is the least-squares fit of the whole
    model. That fit, at the inputs as entered, and the profile-likelihood
    interval of every binding constant it was free to move are the result's
    :attr:`~FitResult.conditional` fit.

    An input ``config.errors`` gives an uncertainty, its own or one it shares
    with other inputs, is then free to move within it while each binding
    constant is profiled again
    (:func:`~core.pipeline.input_aware.input_aware`): what comes back is the
    reported fit and the reported interval, which answers what the data say
    about Ka when the inputs are known no better than stated. With no such
    input the two are one fit, down to the interval objects. Either way the
    misfit tests and the conflict statistic of
    :mod:`core.pipeline.diagnostics` are run and recorded.

    How precisely each titration point was measured is read off the replicates
    behind the fitted signal (:func:`~core.pipeline.noise.noise_law`) and
    carried through every projection here as point weights, so the fit, its
    profiles, both intervals and the lack-of-fit test count each point by the
    precision the replicates show it to have. The law is recorded on the
    result. One signal cannot show how the noise varies with the signal, and is
    fitted with weights of exactly one: every number is then that of a fit made
    without a law.

    Parameters
    ----------
    assay : BaseAssay
        The assay data to fit (with Quantity x_data/y_data).
    config : FitConfig, optional
        Fitting configuration.
    measurement_set_id : str, optional
        UUID of the source ``MeasurementSet`` for traceability.
    source_file : str, optional
        Original filename, if known.
    should_cancel : Callable[[], bool], optional
        Asked before every equilibrium solve whether to stop.
    replicate_signals : np.ndarray, optional
        The replicates the fitted signal is the average of, shape ``(m, n)``.
        They are what the noise law is read from, and with two or more of them
        the misfit test is the replicate lack-of-fit F test, which measures the
        fit against the scatter of the data themselves; otherwise it is the
        runs test on the residuals.

    Returns
    -------
    FitResult
        The fit, its intervals, where it put the inputs it was free to move,
        what the diagnostics say and the signal parameters the data determine
        only in combination.

    Raises
    ------
    ValueError
        When the binding model has no solution anywhere in the Ka bounds, when
        the Ka bounds are not positive, when a signal the fit is measured
        against does not change across the titration, when the data hold too
        few points to judge the fitted parameters and the inputs that may
        move, or when an input uncertainty cannot be read as one.
    FitCancelled
        If *should_cancel* returns True.
    """
    if config is None:
        config = FitConfig()
    law = noise_law(replicate_signals)
    projection = Projection(
        assay,
        _resolve_bounds(assay, config.custom_bounds),
        should_cancel=should_cancel,
        point_weights=law.weights(assay.y_data.magnitude),
    )
    fit = projection.fit()
    params = projection.params(fit)
    rmse, r_squared, x_fit, y_fit = fit_view(assay, params)
    found = {key: projection.interval(key, fit) for key in projection.ka_keys}
    intervals = {key: ci for key, ci in found.items() if ci is not None}
    conditional = ConditionalFit(
        parameters=_wrap_params_as_quantities(params, assay),
        intervals=intervals,
        rmse=rmse,
        r_squared=r_squared,
    )

    errors = config.errors.for_fit()
    free_inputs = constraints(errors, assay.get_conditions(), config.input_labels)
    aware = input_aware(
        projection,
        fit,
        free_inputs,
        loading=errors.loading(assay.get_conditions()),
        should_cancel=should_cancel,
        conditional=intervals,
    )
    shifts = input_shifts(aware)
    if shifts:
        params = _aware_params(projection, aware.fit)
        rmse, r_squared, x_fit, y_fit = fit_view(assay, params, aware.fit.input_offsets)
        # The profiles carry the same interval objects as ``conditional`` where
        # nothing moved, so an unchanged interval stays the one object.
        intervals = {key: profile.interval for key, profile in aware.profiles.items()}
    return FitResult(
        parameters=_wrap_params_as_quantities(params, assay),
        rmse=rmse,
        r_squared=r_squared,
        x_fit=x_fit,
        y_fit=y_fit,
        assay_type=assay.assay_type.name,
        model_name=assay.model_name,
        conditions=assay.get_conditions(),
        fit_config=_config_to_dict(config),
        measurement_set_id=measurement_set_id,
        source_file=source_file,
        metadata={'method': 'variable_projection'},
        intervals=intervals,
        degenerate_keys=projection.degenerate_keys(fit),
        conditional=conditional,
        input_shifts=shifts,
        diagnostics=_diagnose(projection, fit, aware, replicate_signals, law, conditional.intervals, should_cancel),
        aware=aware,
        noise=law,
    )


def _aware_params(projection: Projection, fit: AwareFit) -> np.ndarray:
    """The input-aware fit's parameters in ``parameter_keys`` order, ready for ``assay.forward_model``."""
    values = {**fit.ka, **dict(zip(projection.coef_keys, fit.coefficients))}
    return np.array([values[k] for k in projection.assay.parameter_keys])


def _diagnose(
    projection: Projection,
    fit: ProjectedFit,
    aware: AwareResult,
    replicate_signals: Optional[np.ndarray],
    law: NoiseLaw,
    conditional_intervals: Dict[str, KaInterval],
    should_cancel: Optional[Callable[[], bool]],
) -> FitDiagnostics:
    """Test the model at both fits, test the inputs against what was stated, and name what they say together.

    The test at the fit with the inputs as entered needs that fit's own
    Jacobian, which is the input-aware result with nothing free to move; where
    no input moves anyway it is the one result, and both tests are the one
    test. Every test of the verdict that could not be run is recorded with
    the reason. *law* is the noise law the projection's point weights come
    from, which the lack-of-fit test reads its reference from.
    """
    entered = (
        aware
        if not aware.constraints
        else input_aware(projection, fit, (), should_cancel=should_cancel, conditional=conditional_intervals)
    )
    conditional_misfit, entered_why = _misfit(projection, entered, replicate_signals, law)
    misfit, why = (
        (conditional_misfit, entered_why) if entered is aware else _misfit(projection, aware, replicate_signals, law)
    )
    inputs = conflict(aware)
    skipped = {} if misfit is not None else {'misfit': why}
    if not any(c.sigma is not None for c in aware.constraints):
        skipped['conflict'] = 'no_uncertainty'
    elif inputs is None:
        skipped['conflict'] = 'no_informed_direction'
    return FitDiagnostics(
        conditional_misfit=conditional_misfit,
        misfit=misfit,
        conflict=inputs,
        verdict=verdict(conditional_misfit, misfit, inputs),
        skipped=skipped,
    )


def _misfit(
    projection: Projection, aware: AwareResult, replicate_signals: Optional[np.ndarray], law: NoiseLaw
) -> Tuple[Optional[MisfitTest], str]:
    """Whether the fitted curve misses the data by more than the data's own scatter allows; why not, if untested.

    With two or more replicates behind the fitted signal the test is theirs:
    the misfit of the curve against their average, judged against the scatter
    between them. The p-value is read against one of two references, named
    on the test (``MisfitTest.reference``). Where *law* was not read from the
    replicates — the weights are then exactly one — the ratio is exactly F
    under normal noise, and the p-value is F's. Where the replicates showed
    the law, the weights are estimated from the same scatter the ratio is
    judged against, so the ratio is F only approximately; the p-value is then
    simulated: replicates drawn about the fitted curve at the law's own level,
    the law read again from every draw and the curve refitted on the columns
    of the parameters the fit counts (:func:`misfit_design`). With one signal
    there is no such scatter, and what is left to
    look at is whether the residuals change sign as often as a fit of this
    model to noise would — a test with little power, which says nothing at all
    below ``_RUNS_TEST_DOF`` residual degrees of freedom. Neither is run when
    the scatter it would judge the curve against is below the resolution of
    the fit (:func:`~core.pipeline.diagnostics.no_scatter`): noise-free or
    identical data leave nothing to test the model with.

    Both tests count what the fit fitted, ``AwareFit.n_params``, and the runs
    test takes its own reference from the Jacobian of those same parameters
    (:func:`fit_jacobian`). Both tests are run in the whitened space the
    projection's point weights define: the F test weights the misfit of the
    curve and the scatter it is judged against by the same weights, and the
    runs test reads the signs of the whitened residual, which are the signs of
    the residual itself. The projection hands out the whitened residual, so
    the fitted curve the F test takes is read back from it in signal units.

    Returns
    -------
    tuple[MisfitTest | None, str]
        The test, or ``None`` with the reason it was not run
        (:data:`~core.pipeline.diagnostics.SKIP_REASONS`); the reason is
        ``''`` when the test ran.
    """
    fit, n = aware.fit, projection.n_points
    residual = projection.residual(fit.ka, 0, fit.input_offsets)
    if replicate_signals is not None and np.shape(replicate_signals)[0] >= 2:
        fitted = projection.signals[0] - residual / np.sqrt(projection.point_weights)
        # The simulated reference needs the columns of the counted parameters;
        # the exact F reference needs none, so they are worked out only for it.
        design = misfit_design(projection, aware) if law.estimated else None
        found = lack_of_fit(replicate_signals, fitted, fit.n_params, projection.point_weights, law=law, design=design)
        return found, '' if found is not None else 'no_scatter'
    if n - fit.n_params < _RUNS_TEST_DOF:
        return None, 'too_few_dof'
    if no_scatter(fit.ssr / n, aware.ss_tot, n):
        return None, 'no_scatter'
    return runs_test(residual, projection.assay.x_data.magnitude, fit_jacobian(projection, aware)), ''


def fit_linear_assay(
    assay: DyeAloneAssay,
    *,
    measurement_set_id: Optional[str] = None,
    source_file: Optional[str] = None,
) -> FitResult:
    """Fit a dye-alone assay using simple linear regression.

    Parameters
    ----------
    assay : DyeAloneAssay
        The dye-alone calibration data.
    measurement_set_id : str, optional
        UUID of the source ``MeasurementSet`` for traceability.
    source_file : str, optional
        Original filename, if known.

    Returns
    -------
    FitResult
    """
    slope, intercept, r_squared, rmse = assay.fit_linear()
    y_fit = assay.forward_model(np.array([slope.magnitude, intercept.magnitude]))

    return FitResult(
        parameters={
            'slope': slope,
            'intercept': intercept,
        },
        rmse=float(rmse.magnitude),
        r_squared=r_squared,
        x_fit=assay.x_data,
        y_fit=y_fit,
        assay_type=assay.assay_type.name,
        model_name='linear',
        conditions=assay.get_conditions(),
        fit_config={},
        measurement_set_id=measurement_set_id,
        source_file=source_file,
        metadata={'method': 'linear_regression'},
    )


def bounds_from_dye_alone(
    result: FitResult,
    margin: float = 0.2,
) -> Dict[str, Tuple[Quantity, Quantity]]:
    """Derive signal-coefficient bounds from a dye-alone calibration.

    Returns Quantity bound tuples suitable for ``FitConfig.custom_bounds``.

    Parameters
    ----------
    result : FitResult
        A dye-alone fit (``model_name == "linear"``).
    margin : float
        Fractional margin (default 0.2 = +/-20%).

    Returns
    -------
    Dict[str, Tuple[Quantity, Quantity]]
    """
    if result.model_name != 'linear':
        raise ValueError(f"Expected a dye-alone (linear) FitResult, got model_name='{result.model_name}'")

    slope_q = result.parameters['slope']
    intercept_q = result.parameters['intercept']

    def _window(value: Quantity, margin_frac: float) -> Tuple[Quantity, Quantity]:
        mag = float(value.magnitude)
        half = abs(mag) * margin_frac if abs(mag) > 0 else margin_frac
        lo = max(0.0, mag - half)
        hi = max(0.0, mag + half)
        return (Q_(lo, value.units), Q_(hi, value.units))

    return {
        'I_dye_free': _window(slope_q, margin),
        'I0': _window(intercept_q, margin),
    }


def fit_measurement_set(
    ms: MeasurementSet,
    assay_cls: Type[BaseAssay],
    conditions: Dict[str, Any],
    config: Optional[FitConfig] = None,
    *,
    use_average: bool = True,
    replica_id: Optional[str] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> FitResult:
    """Build an assay from a MeasurementSet and fit it.

    When ``config.per_replica`` is ``True`` and neither ``use_average=False``
    nor an explicit ``replica_id`` is provided, dispatches to
    :func:`fit_measurement_set_per_replica`, which fits every active replicate
    on its own and tests whether they share their binding constants before
    averaging. A dye-alone calibration carries no binding constant for that test
    to judge and goes to :func:`fit_linear_assay` in either replicate mode.

    Parameters
    ----------
    ms : MeasurementSet
        Source data.
    assay_cls : Type[BaseAssay]
        Concrete assay class.
    conditions : dict
        Assay-specific conditions as Quantity values.
    config : FitConfig, optional
        Fitting configuration.
    use_average : bool
        Use the averaged active-replica signal (default ``True``).
    replica_id : str, optional
        Fit a specific replica instead of the average.
    should_cancel : Callable[[], bool], optional
        Asked before every equilibrium solve whether to stop; a linear
        dye-alone fit is a single solve and never asks.

    Returns
    -------
    FitResult
        Recording in ``metadata['active_replica_ids']`` the replicates its
        RMSE and R² are measured against — the active ones for a fit of their
        average, the named one for a fit of a single replicate. The mask of
        *ms* changes in place, so ``measurement_set_id`` alone does not say
        which replicates a fit used. Every fit also records the data it was
        made on (see :attr:`FitResult.metadata`).

    Raises
    ------
    FitCancelled
        If *should_cancel* returns True.
    """
    # A dye-alone calibration is a straight line with no binding constant, so the
    # shared-Ka test has nothing to judge: it is fitted from the average of the
    # active replicates whichever replicate mode is set.
    linear = issubclass(assay_cls, DyeAloneAssay)
    if not linear and config is not None and config.per_replica and replica_id is None and use_average:
        return fit_measurement_set_per_replica(ms, assay_cls, conditions, config, should_cancel=should_cancel)

    assay = ms.to_assay(
        assay_cls,
        conditions=conditions,
        use_average=use_average,
        replica_id=replica_id,
    )

    if linear:
        result = fit_linear_assay(
            assay,
            measurement_set_id=ms.id,
            source_file=ms.metadata.get('source_file'),
        )
    else:
        used = ms.active_replica_ids if replica_id is None else [replica_id]
        result = fit_assay(
            assay,
            config=config,
            measurement_set_id=ms.id,
            source_file=ms.metadata.get('source_file'),
            should_cancel=should_cancel,
            replicate_signals=_replicate_rows(ms, used) if use_average and replica_id is None else None,
        )
    result.metadata['active_replica_ids'] = ms.active_replica_ids if replica_id is None else [replica_id]
    _record_data(result, ms)
    return result


def _replicate_rows(ms: MeasurementSet, replica_ids: List[str]) -> np.ndarray:
    """The measured signals of *replica_ids*, one row each, in the order given."""
    return np.vstack([ms.get_replica_signal(rid) for rid in replica_ids])


def _record_data(result: FitResult, ms: MeasurementSet) -> None:
    """Record on *result* the data it was made on and what its quality was measured against.

    ``data_fingerprint`` identifies the measured values of *ms*, so an imported
    result can be matched to loaded data. ``quality_scored_on`` states that
    every RMSE and R² was measured against the replicates the fit used; a
    per-replicate file without it may have scored against every replicate it
    was given, which :func:`verify_imported_result` checks.
    ``model_arithmetic`` names the equilibrium arithmetic every score was
    computed with, which the same function needs to reproduce them.
    """
    result.metadata['data_fingerprint'] = ms.fingerprint()
    result.metadata['quality_scored_on'] = 'fitted_replicates'
    result.metadata['model_arithmetic'] = MODEL_ARITHMETIC


def fit_measurement_set_per_replica(
    ms: MeasurementSet,
    assay_cls: Type[BaseAssay],
    conditions: Dict[str, Any],
    config: Optional[FitConfig] = None,
    *,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> FitResult:
    """Fit every active replicate on its own, leave out the ones that disagree, and fit the rest together.

    For replicates of equal scatter the joint least-squares fit of every
    replicate is the fit of their average, and the average of replicates that
    share their binding constants is itself a model signal. The reported fit is
    therefore the fit of the average of the replicates used, and what this
    function adds is the evidence behind it: every replicate's own fit, and an
    explicit test of the two assumptions the average rests on
    (:func:`~core.pipeline.varpro.replicate_outliers`). A replicate whose own
    signal needs a different binding constant than the others share, or whose
    scatter about its own fit is far larger than theirs, is left out of the
    average and reported by name, with the reason.

    The replicates' own fits and the rounds of the test are searches over one
    :class:`~core.pipeline.varpro.Projection`, whose per-row residuals on the
    search grid are cached, so each of them costs only its refinement and not
    another grid, and each replicate's own fit is searched once and used twice —
    as that replicate's reported fit and as the residual the test weights it by.
    Measured at 30 points on the default Ka box with four replicates, they add
    0.05 s to a one-Ka fit and 3 s to a two-Ka fit, on top of the reported fit
    and its intervals.

    Parameters
    ----------
    ms : MeasurementSet
        Source data with one or more active replicates.
    assay_cls : Type[BaseAssay]
        Concrete assay class.
    conditions : dict
        Assay-specific conditions as Quantity values.
    config : FitConfig, optional
        Fitting configuration.
    should_cancel : Callable[[], bool], optional
        Asked before every equilibrium solve whether to stop.

    Returns
    -------
    FitResult
        The fit of the average of the replicates used, with ``replica_fits``
        holding every given replicate's own fit and the metadata recording the
        replicates given (``active_replica_ids``), used (``replica_ids_fit``),
        left out (``replica_failures``) and the test that decided
        (``replicate_test``). The reported fit carries the interval, the input
        shifts, the diagnostics and the noise law, read there from the
        replicates it kept; a replicate's own fit is the search over its own
        signal at the inputs as entered and carries none of them — a law read
        from the scatter of several replicates describes the set, not the one
        row — though the rows are fitted with the weights of the law of the
        replicates given.

    Raises
    ------
    ValueError
        When no replicate is active, when a replicate's signal does not change
        across the titration, or when the fit itself cannot be made.
    FitCancelled
        If *should_cancel* returns True.
    """
    if config is None:
        config = FitConfig()
    given = ms.active_replica_ids
    if not given:
        raise FitRefused('No replicate is switched on, so there is nothing to fit. Switch at least one on.')

    rows = [ms.replica_ids.index(rid) for rid in given]

    # Each replicate's misfit is weighted by its own scatter, so a replicate
    # that has no scatter because it has no signal at all would outweigh every
    # other one. Such a row also says nothing about Ka — every binding constant
    # reproduces a constant signal equally well. The engine refuses it too; here
    # the replicates are known by name, so the refusal names them.
    flat = [rid for row, rid in zip(rows, given) if np.ptp(ms.signals[row]) == 0.0]
    if flat:
        raise FitRefused(
            f'The signal of replicate(s) {", ".join(flat)} is the same at every titration point, so nothing in '
            'them tells what Ka is. Switch them off under Replicates and fit again.'
        )

    grid_assay = ms.to_assay(assay_cls, conditions=conditions, use_average=True)
    # One noise law for the replicates given, so every row of the shared
    # projection — each replicate's own fit and the test between them — counts
    # a titration point by the same precision.
    given_signals = ms.signals[rows]
    law = noise_law(given_signals)
    projection = Projection(
        grid_assay,
        _resolve_bounds(grid_assay, config.custom_bounds),
        signals=given_signals,
        should_cancel=should_cancel,
        point_weights=law.weights(given_signals.mean(axis=0)),
    )
    # Each row's own fit is both the replicate's reported fit and the residual
    # the shared-Ka test weights it by, so it is searched once and used twice.
    own_fits = [projection.fit(np.eye(len(given))[row]) for row in range(len(given))]
    replica_fits = [
        _replica_fit(ms, assay_cls, conditions, projection, config, rid, row, own_fits[row])
        for row, rid in enumerate(given)
    ]
    test = replicate_outliers(projection, own_fits)
    excluded = {given[row] for row in test.excluded}
    used = [rid for rid in given if rid not in excluded]

    result = fit_assay(
        ms.with_active(used).to_assay(assay_cls, conditions=conditions, use_average=True),
        config=config,
        measurement_set_id=ms.id,
        source_file=ms.metadata.get('source_file'),
        should_cancel=should_cancel,
        replicate_signals=_replicate_rows(ms, used),
    )
    result.replica_fits = replica_fits
    result.fit_config['per_replicate'] = True
    result.metadata['active_replica_ids'] = list(given)
    result.metadata['replica_ids_fit'] = used
    if excluded:
        result.metadata['replica_failures'] = {
            given[row]: _excluded_reason(test, row, len(given)) for row in sorted(test.excluded)
        }
    if test.tested:
        result.metadata['replicate_test'] = {
            'level': test.level,
            'p_values': {given[row]: p for row, p in test.p_values.items()},
            'reasons': {given[row]: 'scatter' if row in test.scatter else 'ka' for row in sorted(test.excluded)},
        }
    _record_data(result, ms)
    return result


def _replica_fit(
    ms: MeasurementSet,
    assay_cls: Type[BaseAssay],
    conditions: Dict[str, Any],
    projection: Projection,
    config: FitConfig,
    replica_id: str,
    row: int,
    fit: ProjectedFit,
) -> FitResult:
    """The fit of one replicate's own signal, at the binding constants that signal alone asks for.

    *fit* is ``projection.fit`` weighting *row* alone, so the search is steered
    by that replicate's signal, while its signal parameters are solved exactly
    as in any other fit.
    """
    params = projection.params(fit, row=row)
    assay = ms.with_active([replica_id]).to_assay(assay_cls, conditions=conditions, use_average=True)
    rmse, r_squared, x_fit, y_fit = fit_view(assay, params)
    result = FitResult(
        parameters=_wrap_params_as_quantities(params, assay),
        rmse=rmse,
        r_squared=r_squared,
        x_fit=x_fit,
        y_fit=y_fit,
        assay_type=assay.assay_type.name,
        model_name=assay.model_name,
        conditions=assay.get_conditions(),
        fit_config=_config_to_dict(config),
        measurement_set_id=ms.id,
        source_file=ms.metadata.get('source_file'),
        metadata={
            'method': 'variable_projection',
            'replica_id': replica_id,
            'active_replica_ids': [replica_id],
        },
    )
    _record_data(result, ms)
    return result


def _excluded_reason(test: ReplicateTest, row: int, n_replicates: int) -> str:
    """Why replicate *row* was left out of the average, in plain words."""
    if row in test.scatter:
        c, limit = test.scatter[row]
        return (
            f"Its points scatter about its own best fit far more than the other replicates' do "
            f"(Cochran's C = {c:.2f}, above the limit of {limit:.2f} at the {test.level:g} level)."
        )
    return (
        f'Its own best fit needs a different Ka than the other replicates share '
        f'(p = {test.p_values[row]:.2g}; limit {test.level:g} shared across {n_replicates} replicates).'
    )


#: Relative tolerance within which a stored score counts as reproduced. The gate
#: tells the data a fit was made on from other data, which move every RMSE and
#: R² by 1e-3 or more. Scoring the same fit on the same data twice with the
#: arithmetic that wrote it reproduces every number exactly, and an equivalent
#: evaluation of the same model — the same equilibrium root found by a bracketing
#: method at the same relative tolerance — moves them by at most 5e-15. A file
#: that stores the scores of the earlier absolute-tolerance arithmetic moves them
#: as far as its binding is tight: 1e-14 or less wherever Ka·c is of order one,
#: and, over a sweep of GDA, IDA, DBA and the stepwise models at sub-micromolar
#: totals with fits reaching 1e12 M⁻¹, up to 2e-2 (GDA), 2e-3 (IDA) and 6e-5
#: (stepwise). Such a file is checked with the arithmetic that wrote it, and what
#: moves by more than this tolerance is re-scored and shown, not refused. 1e-6
#: sits far above the spread of one model evaluated two ways and far below the
#: distance between datasets.
_REPRODUCE_RTOL = 1e-6

ImportStatus = Literal['verified', 'rescored_legacy', 'rescored_precision', 'different_data', 'unverifiable']


def verify_imported_result(result: FitResult, ms: Optional[MeasurementSet]) -> Tuple[ImportStatus, FitResult]:
    """Check an imported *result* against the loaded data *ms* before it is shown.

    Every number shown under a fit's name must describe the data the fit was
    made on. With data loaded, the result's stored quality is measured again on
    its own record: the replicates it used, its conditions, its assay type and
    the shifts it reports for the inputs it was free to move — the fit is
    scored where it was made, not at the entered inputs it moved away from.

    ``model_arithmetic`` names the equilibrium arithmetic a file's scores were
    computed with. A file that records none stores the scores of the earlier
    arithmetic (:func:`~core.models.equilibrium.legacy_arithmetic`), so it is
    checked with that one and then re-scored with the present one; the gate
    below is the same either way. A file that names an arithmetic this version
    does not have cannot be checked at all.

    ``'verified'``
        The data carry the fit's fingerprint, or the file records none, and
        every stored RMSE and R² is reproduced (relative 1e-6). The returned
        copy records the loaded data's fingerprint, the ``quality_scored_on``
        and ``model_arithmetic`` markers. A fit of the average whose file does
        not record its replicates is scored on the replicates active in *ms*
        now, and the copy records them.
    ``'rescored_precision'``
        A file without a ``model_arithmetic`` entry whose stored numbers
        reproduce under the arithmetic that wrote them but move by more than
        1e-6 under the present one — its scores or its curve. The copy keeps
        the fit's parameters and shows the RMSE, the R² and the curve of the
        present arithmetic.
    ``'rescored_legacy'``
        A per-replicate file without the ``quality_scored_on`` marker whose
        reported RMSE and R² reproduce when scored against every replicate it
        was given, left-out ones included. The copy keeps its parameters and
        measures RMSE, R² and curve again on the replicates the fit used.
    ``'different_data'``
        The fingerprints differ, the data lack a replicate the fit names, or
        the stored quality reproduces neither way. *result* is returned
        unchanged. A recorded ``data_fingerprint`` equal to the data's tells
        numbers that do not reproduce on these data from a fit made on other
        data.
    ``'unverifiable'``
        No data are loaded, the result holds no fitted parameters to score, or
        it names an equilibrium arithmetic this version cannot compute with, so
        its stored scores cannot be reproduced either way. *result* is returned
        unchanged.

    *ms* itself, including which replicates are active, is never changed.

    Parameters
    ----------
    result : FitResult
        A result read from a results file.
    ms : MeasurementSet or None
        The data loaded now.

    Returns
    -------
    tuple[str, FitResult]
        The status and the result to show: a checked copy for ``'verified'``
        and the ``'rescored_*'`` statuses, *result* otherwise.
    """
    recorded_arithmetic = result.metadata.get('model_arithmetic')
    if recorded_arithmetic == MODEL_ARITHMETIC:
        return _verify(result, ms)
    if recorded_arithmetic is not None:  # an arithmetic this version cannot compute with
        return 'unverifiable', result
    with legacy_arithmetic():
        status, checked = _verify(result, ms)
    if status in ('different_data', 'unverifiable'):
        return status, checked
    return _rescore_with_present_arithmetic(status, checked, ms)


def _rescore_with_present_arithmetic(
    status: ImportStatus,
    checked: FitResult,
    ms: MeasurementSet,
) -> Tuple[ImportStatus, FitResult]:
    """Numbers of the present arithmetic for a file that stores an earlier one's.

    The fit stays the file's — its parameters are untouched — and only what is
    measured from them is computed again. A ``'verified'`` file whose every
    number the present arithmetic reproduces within ``_REPRODUCE_RTOL`` keeps
    the numbers it stores, so importing it twice shows the same values; the
    ``model_arithmetic`` marker on the copy then says of them what the gate
    asked, that the present arithmetic reproduces them to within that
    tolerance. A ``'rescored_legacy'`` file's reported numbers are rebuilt in
    any case, and are rebuilt here.
    """
    shown, moved = _present_numbers(checked, _record_assay(ms, checked, fit_replica_ids(checked)))
    if status == 'verified' and not moved:
        return status, checked
    return status if status == 'rescored_legacy' else 'rescored_precision', shown


def _fitted_offsets(result: FitResult) -> Dict[str, float]:
    """Where *result* put each input its fit moved, as a fraction of the entered value.

    ``input_shifts`` holds the offset of every error source; the error model
    the fit recorded turns them into the offsets of the inputs.
    """
    fractions = {key: shift.fraction for key, shift in result.input_shifts.items()}
    return ErrorModel.from_dict(result.fit_config).input_offsets(fractions, result.conditions)


def _present_numbers(result: FitResult, assay: BaseAssay) -> Tuple[FitResult, bool]:
    """*result* with what the present arithmetic measures from its fit, and whether that moved.

    The fit itself is untouched: its parameters stay the file's, and the RMSE,
    the R² and the curve are measured again from them. The flag says whether
    any of those numbers moved by more than ``_REPRODUCE_RTOL``, the same gate
    the check itself applies — the curve included, so a copy that keeps stored
    numbers keeps a curve the present arithmetic draws the same way.
    """
    rmse, r_squared, x_fit, y_fit = fit_view(assay, _parameter_vector(result, assay), _fitted_offsets(result))
    # Early releases drew the curve on the measured points; such a curve stands on another
    # grid than the one drawn now and there is nothing in it to compare, so it is left alone.
    stored_x, stored_y = result.x_fit.to('M').magnitude, result.y_fit.to('au').magnitude
    on_same_grid = np.shape(stored_y) == np.shape(y_fit.magnitude)
    moved = not (
        _reproduces((result.rmse, result.r_squared), (rmse, r_squared))
        and (not on_same_grid or (_reproduces(stored_x, x_fit.magnitude) and _reproduces(stored_y, y_fit.magnitude)))
    )
    metadata = dict(result.metadata)
    metadata['model_arithmetic'] = MODEL_ARITHMETIC
    rebuilt = replace(result, rmse=rmse, r_squared=r_squared, x_fit=x_fit, y_fit=y_fit, metadata=metadata)
    return rebuilt, moved


def _verify(result: FitResult, ms: Optional[MeasurementSet]) -> Tuple[ImportStatus, FitResult]:
    """Check *result* against *ms* with the arithmetic in force; see :func:`verify_imported_result`."""
    if ms is None or not result.parameters:
        return 'unverifiable', result
    fingerprint = ms.fingerprint()
    recorded = result.metadata.get('data_fingerprint')
    if recorded is not None and recorded != fingerprint:
        return 'different_data', result

    used = fit_replica_ids(result)
    metadata = dict(result.metadata)
    if used is None:
        used = ms.active_replica_ids
        metadata['active_replica_ids'] = list(used)
    if not set(used) <= set(ms.replica_ids):
        return 'different_data', result
    metadata['data_fingerprint'] = fingerprint
    metadata['quality_scored_on'] = 'fitted_replicates'
    metadata['model_arithmetic'] = MODEL_ARITHMETIC
    assay = _record_assay(ms, result, used)

    vector = _parameter_vector(result, assay)
    offsets = _fitted_offsets(result)
    stored = (result.rmse, result.r_squared)
    if _reproduces(_score(assay, vector, offsets), stored):
        return 'verified', replace(result, metadata=metadata)

    given = _legacy_input_ids(result, used, ms)
    if given is None or not _reproduces(_score(_record_assay(ms, result, given), vector, offsets), stored):
        return 'different_data', result
    rmse, r_squared, x_fit, y_fit = fit_view(assay, vector, offsets)
    return 'rescored_legacy', replace(
        result, rmse=rmse, r_squared=r_squared, x_fit=x_fit, y_fit=y_fit, metadata=metadata
    )


def _legacy_input_ids(result: FitResult, used: List[str], ms: MeasurementSet) -> Optional[List[str]]:
    """The replicates a per-replicate file without the ``quality_scored_on`` marker may have scored against.

    Every replicate it was given, left-out ones included, when that differs
    from the replicates it used and *ms* holds them all; otherwise None.
    """
    if not result.per_replica or 'quality_scored_on' in result.metadata:
        return None
    given = input_replica_ids(result)
    if given is None or set(given) == set(used) or not set(given) <= set(ms.replica_ids):
        return None
    return given


def _score(assay: BaseAssay, vector: np.ndarray, offsets: Optional[Mapping[str, float]] = None) -> Tuple[float, float]:
    """RMSE and R² of the fit with parameters *vector*, at the inputs *offsets* put them, against *assay*'s signal."""
    rmse, r_squared, _, _ = fit_view(assay, vector, offsets)
    return rmse, r_squared


def _parameter_vector(result: FitResult, assay: BaseAssay) -> np.ndarray:
    """*result*'s reported parameters in *assay*'s order and canonical units."""
    units = ASSAY_REGISTRY[assay.assay_type].units
    return np.array([result.parameters[k].to(units[k]).magnitude for k in assay.parameter_keys], dtype=float)


def _reproduces(values, stored) -> bool:
    """Whether *values* equal *stored* in shape and within ``_REPRODUCE_RTOL``."""
    values, stored = np.asarray(values, dtype=float), np.asarray(stored, dtype=float)
    return values.shape == stored.shape and bool(np.allclose(values, stored, rtol=_REPRODUCE_RTOL, atol=0.0))
