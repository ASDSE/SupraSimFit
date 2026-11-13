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
one that lets them. A stated random error of each titrant addition, and a
noise law the replicates leave uncertain, widen the cut-off of an interval by
the design effect they imply (:mod:`core.pipeline.inflation`). The fit at the
entered inputs and its own interval stay beside the headline as
:class:`ConditionalFit`. :attr:`FitResult.diagnostics` holds what
the tests of :mod:`core.pipeline.diagnostics` say about the model and the
inputs.

What a fit reports is read off its :class:`FitResult` by
:mod:`core.pipeline.reporting`, and a results file read back is checked
against the loaded data by :mod:`core.pipeline.results_io`.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple, Type

import numpy as np

from core.assays.base import BaseAssay
from core.assays.dye_alone import DyeAloneAssay
from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.data_processing.measurement_set import MeasurementSet
from core.models.equilibrium import MODEL_ARITHMETIC
from core.optimizer.filters import calculate_fit_metrics
from core.pipeline.diagnostics import (
    AdditionDraws,
    FitDiagnostics,
    InputShift,
    MisfitTest,
    addition_noise_covariance,
    lack_of_fit,
    no_scatter,
    runs_test,
    verdict,
)
from core.pipeline.inflation import (
    addition_signal_loading,
    inflation,
    joint_inflation,
    replicate_scatter_ssr,
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
from core.pipeline.inputs import TITRANT, AdditionError, ErrorModel, constraints
from core.pipeline.noise import NoiseLaw, noise_law
from core.pipeline.varpro import (
    _R2_RESOLUTION,
    LEVEL,
    FitRefused,
    KaInterval,
    ProjectedFit,
    Projection,
    ReplicateTest,
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
        ``loaded_replica_ids`` (every replicate of the data, switched off or
        not, in the order the app names them A, B, …),
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
        arithmetic that computed every score). Read the replicates through
        :func:`~core.pipeline.reporting.fit_replica_ids` and
        :func:`~core.pipeline.reporting.input_replica_ids`.
    intervals : dict[str, KaInterval] | None
        Profile-likelihood confidence interval of every binding constant the
        fit was free to move, with every input as free as its stated
        uncertainty allows and the cut-off widened by everything the stated
        errors and the replicates add to the spread of the estimate
        (``KaInterval.inflation``, :mod:`core.pipeline.inflation`). ``None``
        when the result carries no interval: a dye-alone calibration, or a
        result imported from a file written before intervals were reported.
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
        entered and no error of the additions. ``None`` for a dye-alone
        calibration and for a result imported from a file written before the
        inputs could move. With no input given an uncertainty and no error of
        the additions stated
        (:func:`~core.pipeline.reporting.reports_conditional`) the fit above
        is that fit: same numbers, and the very same
        :class:`~core.pipeline.varpro.KaInterval` objects.
    input_shifts : dict[str, InputShift]
        Where the fit put every error source that was free to move, by source
        key (an input's own key, or
        :func:`~core.pipeline.inputs.shared_key` of a shared source): as a
        fraction of the entered value and in units of the uncertainty stated
        for it. Empty when nothing was free to move.
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
    point_weights : np.ndarray | None
        The weight of every titration point the fit ran with, shape
        ``(n_points,)``: the law's weights read off the fitted curve
        (:func:`fit_assay`). ``None`` where every weight is one — no law, a
        constant one, a dye-alone calibration — and on a result imported from
        a file written before the weights were recorded. Every later
        computation on the fit (its Ka profile, the sensitivity analysis)
        runs with these weights rather than reading the law again.
    joint_inflation : float
        The design effect of the pair of binding constants of a two-step model
        (:func:`~core.pipeline.inflation.joint_inflation`), which widens the
        cut-off of their joint region at the entered inputs: the noise law's
        share of it and, where one is stated, the random error of each
        addition's. One for a model with one free binding constant, wherever
        neither applies, and on a result imported from a file written before
        it was recorded.
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
    point_weights: Optional[np.ndarray] = None
    joint_inflation: float = 1.0

    @property
    def per_replica(self) -> bool:
        """Whether the fit tested its replicates and reports their own fits."""
        return bool(self.fit_config.get('per_replicate'))

    def profile_arguments(self) -> Dict[str, Any]:
        """The keyword arguments that make :func:`~core.pipeline.profile.fit_profile` profile this fit as it was made.

        Its penalised profiles, the point weights it ran with, and the design
        effects of its conditional intervals, of its reported ones and of their
        joint region: with them the curves, the intervals and the region are the
        fit's own rather than those of a fit with weights of one and plain
        cut-offs, after an import as well, which holds no penalised profiles.
        """
        conditional = self.conditional
        return {
            'aware': self.aware,
            'point_weights': self.point_weights,
            'inflation': None
            if conditional is None
            else {key: interval.inflation for key, interval in conditional.intervals.items()},
            'reported_inflation': None
            if self.intervals is None
            else {key: interval.inflation for key, interval in self.intervals.items()},
            'joint_inflation': self.joint_inflation,
        }

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
            'point_weights': None if self.point_weights is None else self.point_weights.tolist(),
            'joint_inflation': self.joint_inflation,
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
        ``None``, one without ``point_weights`` with
        :attr:`FitResult.point_weights` ``None``, and one without
        ``joint_inflation`` with the plain joint region, a factor of one.

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
        point_weights = d.get('point_weights')
        return cls(
            **_common_fields(d),
            intervals=None if intervals is None else {k: KaInterval.from_dict(v) for k, v in intervals.items()},
            degenerate_keys=tuple(d.get('degenerate_keys') or ()),
            replica_fits=None if replica_fits is None else [cls.from_dict(rf) for rf in replica_fits],
            conditional=None if conditional is None else ConditionalFit.from_dict(conditional),
            input_shifts={k: InputShift.from_dict(v) for k, v in (d.get('input_shifts') or {}).items()},
            diagnostics=None if diagnostics is None else FitDiagnostics.from_dict(diagnostics),
            noise=None if noise is None else NoiseLaw.from_dict(noise),
            point_weights=None if point_weights is None else np.asarray(point_weights, dtype=float),
            joint_inflation=d.get('joint_inflation', 1.0),
        )

    @classmethod
    def _from_legacy_dict(cls, d: Dict[str, Any]) -> 'FitResult':
        """A results file written before intervals were reported.

        Such a file holds a multi-start estimate: the fit it reports, and the
        pool of accepted attempts, the attempt record and the statistics mode
        that estimate was summarised through. The fit is kept — its parameters,
        RMSE, R², curve, conditions, replicate record and configuration
        snapshot — and the rest is read past. The result carries no interval,
        and :func:`~core.pipeline.results_io.verify_imported_result` checks
        its numbers against the data as it does for any other file.
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
    the entered inputs are known (:class:`core.pipeline.inputs.ErrorModel`), the
    random error of each titrant addition included. An input no source moves
    is taken as exact, and with no source and no error of the additions the
    reported interval is the one conditional on every entered input.

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
        **config.errors.to_dict(),
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
    about Ka when the inputs are known no better than stated. A stated random
    error of each titrant addition reaches the reported interval too: it moves
    every point along the titrant axis, which the residuals show only in part,
    and the cut-off is widened by the design effect it implies
    (:func:`~core.pipeline.inflation.inflation`). With no such input and no
    error of the additions the two are one fit, down to the interval objects.
    Either way the misfit tests and the conflict statistic of
    :mod:`core.pipeline.diagnostics` are run and recorded, the misfit tests
    against a reference that carries the stated error of the additions.

    How precisely each titration point was measured is read off the replicates
    behind the fitted signal (:func:`~core.pipeline.noise.noise_law`) and
    carried through every projection here as point weights, so the fit, its
    profiles, both intervals and the lack-of-fit test count each point by the
    precision the replicates show it to have. Where the law has a share of
    proportional noise the weights are a function of the signal, and they are
    read off the fitted curve rather than the measured means, by two-stage
    generalised least squares with a mean-dependent variance (Carroll and
    Ruppert 1988, *Transformation and Weighting in Regression*, ch. 2–3;
    Davidian and Carroll 1987, JASA 82:1079): a first fit with the weights at
    the means, then one refit with the weights at its curve, and no further
    iteration. A mean pushed near zero by its own noise would otherwise get a
    weight set by that same noise. The few replicates the share is read from
    leave it uncertain, and each interval is widened to hold for every share
    they allow (``NoiseLaw.share_set``). The law and the weights are recorded
    on the result. One signal cannot show how the noise varies with the
    signal, and neither can replicates whose share comes out zero: they are
    fitted with weights of exactly one and no refit, and every number is then
    that of a fit made without a law.

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
        move, when an input uncertainty cannot be read as one, or when
        sequential additions are stated for a titrant series that falls.
    FitCancelled
        If *should_cancel* returns True.
    """
    if config is None:
        config = FitConfig()
    law = noise_law(replicate_signals)
    bounds = _resolve_bounds(assay, config.custom_bounds)
    weights, curve = _point_weights(assay, bounds, law, should_cancel)
    return _fit_weighted(
        assay,
        config,
        bounds,
        law,
        weights,
        curve,
        measurement_set_id=measurement_set_id,
        source_file=source_file,
        should_cancel=should_cancel,
        replicate_signals=replicate_signals,
    )


def _fit_weighted(
    assay: BaseAssay,
    config: FitConfig,
    bounds: Dict[str, Tuple[Quantity, Quantity]],
    law: NoiseLaw,
    weights: np.ndarray,
    curve: Optional[np.ndarray],
    *,
    measurement_set_id: Optional[str],
    source_file: Optional[str],
    should_cancel: Optional[Callable[[], bool]],
    replicate_signals: Optional[np.ndarray],
) -> FitResult:
    """:func:`fit_assay` with the noise law of *replicate_signals*, the point weights and their curve in hand.

    *weights* and *curve* are what :func:`_point_weights` returns for *assay*
    within *bounds* under *law*.
    """
    errors = config.errors
    projection = Projection(assay, bounds, should_cancel=should_cancel, point_weights=weights)
    fit = projection.fit()
    params = projection.params(fit)
    rmse, r_squared, x_fit, y_fit = fit_view(assay, params)
    # The design effect of the law alone widens the conditional intervals; the
    # reported ones also carry the stated error of the additions.
    by_law = inflation(projection, fit, law=law, curve=curve)
    found = {key: projection.interval(key, fit, inflation=by_law.get(key, 1.0)) for key in projection.ka_keys}
    intervals = {key: ci for key, ci in found.items() if ci is not None}
    conditional = ConditionalFit(
        parameters=_wrap_params_as_quantities(params, assay),
        intervals=intervals,
        rmse=rmse,
        r_squared=r_squared,
    )

    n_replicates = 1 if replicate_signals is None else int(np.shape(replicate_signals)[0])
    stated = dict(
        law=law,
        curve=curve,
        additions=errors.additions,
        n_replicates=n_replicates,
        titrant_stock=_titrant_stock(assay),
    )
    reported = by_law if errors.additions is None else inflation(projection, fit, **stated)
    # The joint region is drawn at the entered inputs and carries everything
    # else the reported intervals carry: the law and the stated additions.
    pair = joint_inflation(projection, fit, **stated)
    free_inputs = constraints(errors, assay.get_conditions(), config.input_labels)
    aware = input_aware(
        projection,
        fit,
        free_inputs,
        loading=errors.loading(assay.get_conditions()),
        should_cancel=should_cancel,
        conditional=intervals,
        inflation=reported,
    )
    shifts = input_shifts(aware)
    if shifts:
        params = _aware_params(projection, aware.fit)
        rmse, r_squared, x_fit, y_fit = fit_view(assay, params, aware.fit.input_offsets)
    if shifts or errors.additions is not None:
        # The profiles carry the same interval objects as ``conditional`` where
        # nothing moved and nothing widened, so an unchanged interval stays the one object.
        intervals = {key: profile.interval for key, profile in aware.profiles.items()}
    diagnostics = _diagnose(
        projection,
        fit,
        aware,
        replicate_signals,
        law,
        conditional.intervals,
        should_cancel,
        additions=errors.additions,
    )
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
        diagnostics=diagnostics,
        aware=aware,
        noise=law,
        point_weights=None if np.all(weights == 1.0) else weights,
        joint_inflation=pair,
    )


def _point_weights(
    assay: BaseAssay,
    bounds: Dict[str, Tuple[Quantity, Quantity]],
    law: NoiseLaw,
    should_cancel: Optional[Callable[[], bool]],
) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """The weights a fit of *assay*'s signal runs with under *law*, and the curve they were read off.

    Where the law has a share of proportional noise, the weights at the
    measured means steer a first fit, and the weights are read again off its
    fitted curve: two-stage generalised least squares, one refit and no loop
    (see :func:`fit_assay`). The curve is returned with them, since the design
    effect of the law is measured at the same curve. Otherwise the weights are
    the law's at the means — ``np.ones``, exactly, where it states no share —
    and no curve was needed.
    """
    weights = law.weights(assay.y_data.magnitude)
    if not (law.estimated and law.share > 0.0):
        return weights, None
    first = Projection(assay, bounds, should_cancel=should_cancel, point_weights=weights)
    curve = assay.forward_model(first.params(first.fit())).magnitude
    return law.weights(curve), curve


def _titrant_stock(assay: BaseAssay) -> Optional[float]:
    """The declared titrant stock in M, the unit of the titrant grid; ``None`` when the additions do not dilute."""
    return None if assay.titrant_stock is None else float(assay.titrant_stock.to('M').magnitude)


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
    additions: Optional[AdditionError] = None,
) -> FitDiagnostics:
    """Test the model at both fits, test the inputs against what was stated, and name what they say together.

    The test at the fit with the inputs as entered needs that fit's own
    Jacobian, which is the input-aware result with nothing free to move; where
    no input moves anyway it is the one result, and both tests are the one
    test. Every test of the verdict that could not be run is recorded with
    the reason. *law* is the noise law the projection's point weights come
    from, which the lack-of-fit test reads its reference from, and *additions*
    the stated random error of each titrant addition, which both misfit tests
    count as part of the noise and the conflict statistic as part of what
    moves the inputs: the additions shift the curve much as a titrant scale or
    a concentration does, so a fit free to move those inputs puts some of the
    addition errors into them, and the statistic's reference carries that
    share (:func:`~core.pipeline.diagnostics.conflict_added`).
    """
    entered = (
        aware
        if not aware.constraints
        else input_aware(
            projection,
            fit,
            (),
            should_cancel=should_cancel,
            conditional=conditional_intervals,
            inflation={key: ci.inflation for key, ci in conditional_intervals.items()},
        )
    )
    conditional_misfit, entered_why = _misfit(projection, entered, replicate_signals, law, additions)
    misfit, why = (
        (conditional_misfit, entered_why)
        if entered is aware
        else _misfit(projection, aware, replicate_signals, law, additions)
    )
    added = None
    if additions is not None and aware.constraints:
        # The fitted signal is the mean of the replicates: separate titrations
        # average their own addition errors down, repeated reads share one set.
        divisor = 1 if replicate_signals is None or not additions.separate_titrations else len(replicate_signals)
        whitened = np.sqrt(projection.point_weights)[:, np.newaxis] * _addition_loading(projection, aware, additions)
        added = (additions.sigma_pct / 100.0) ** 2 / divisor * (whitened @ whitened.T)
    inputs = conflict(aware, added)
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
    projection: Projection,
    aware: AwareResult,
    replicate_signals: Optional[np.ndarray],
    law: NoiseLaw,
    additions: Optional[AdditionError] = None,
) -> Tuple[Optional[MisfitTest], str]:
    """Whether the fitted curve misses the data by more than the data's own scatter allows; why not, if untested.

    With two or more replicates behind the fitted signal the test is theirs:
    the misfit of the curve against their average, judged against the scatter
    between them. The p-value is read against one of two references, named
    on the test (``MisfitTest.reference``). Where *law* was not read from the
    replicates — the weights are then exactly one — and no error of the
    additions is stated, the ratio is exactly F under normal noise, and the
    p-value is F's. Where the replicates showed the law, the weights are
    estimated from the same scatter the ratio is judged against, so the ratio
    is F only approximately; and a random error of each addition moves the
    mean curve in a way no fitted parameter follows, and moves replicates
    that are repeated reads of one titration all alike. The p-value is then
    simulated: replicates drawn about the fitted curve at the law's own level,
    each shifted by addition errors drawn at the stated σ — one set per
    replicate for separate titrations, one set for all of them for repeated
    reads — the law read again from every draw and the curve refitted on the
    columns of the parameters the fit counts (:func:`misfit_design`). With one
    signal there is no such scatter, and what is left to look at is whether
    the residuals change sign as often as a fit of this model to noise would —
    a test with little power, which says nothing at all below
    ``_RUNS_TEST_DOF`` residual degrees of freedom. A stated error of the
    additions is noise correlated along the titration, which makes long runs
    of its own, so the reference is then drawn with that covariance
    (:func:`_runs_covariance`). Neither test is run when the scatter it would
    judge the curve against is below the resolution of the fit
    (:func:`~core.pipeline.diagnostics.no_scatter`): noise-free or identical
    data leave nothing to test the model with.

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
    loading = None if additions is None else _addition_loading(projection, aware, additions)
    if replicate_signals is not None and np.shape(replicate_signals)[0] >= 2:
        fitted = projection.signals[0] - residual / np.sqrt(projection.point_weights)
        # The simulated reference needs the columns of the counted parameters;
        # the exact F reference needs none, so they are worked out only for it.
        design = misfit_design(projection, aware) if law.estimated or additions is not None else None
        draws = (
            None
            if additions is None
            else AdditionDraws(loading, additions.sigma_pct / 100.0, shared=not additions.separate_titrations)
        )
        found = lack_of_fit(
            replicate_signals,
            fitted,
            fit.n_params,
            projection.point_weights,
            law=law,
            design=design,
            additions=draws,
        )
        return found, '' if found is not None else 'no_scatter'
    if n - fit.n_params < _RUNS_TEST_DOF:
        return None, 'too_few_dof'
    if no_scatter(fit.ssr / n, aware.ss_tot, n):
        return None, 'no_scatter'
    covariance = None if additions is None else _runs_covariance(projection, aware, residual, loading, additions)
    return runs_test(
        residual, projection.assay.x_data.magnitude, fit_jacobian(projection, aware), covariance=covariance
    ), ''


def _addition_loading(projection: Projection, aware: AwareResult, additions: AdditionError) -> np.ndarray:
    """``H`` of :func:`~core.pipeline.inflation.addition_signal_loading` at the fit *aware* holds, at its inputs."""
    fit = aware.fit
    moved = projection.assay.with_inputs(fit.input_offsets) if fit.input_offsets else projection.assay
    return addition_signal_loading(projection, fit.ka, fit.input_offsets, additions, _titrant_stock(moved))


def _runs_covariance(
    projection: Projection, aware: AwareResult, residual: np.ndarray, loading: np.ndarray, additions: AdditionError
) -> np.ndarray:
    """Covariance of the noise in the whitened residual of one titration whose additions carry a random error.

    :func:`~core.pipeline.diagnostics.addition_noise_covariance` of the
    whitened residual, the whitened columns of the parameters the fit counts
    (:func:`misfit_design`) and the whitened *loading* ``H``: ``sigma2 I + G_w``
    with ``G_w = s² W½ H H' W½``, ``s`` the stated relative σ of one addition
    and ``sigma2`` the noise beside the additions, read on the residual space.
    It is in the units of the residual rows of :func:`fit_jacobian`, the noise
    scale ``sqrt(S / n)``, so it sits beside the penalty rows the inputs held
    by a standard deviation add, whose noise is standard.
    """
    fit, n = aware.fit, projection.n_points
    root = np.sqrt(projection.point_weights)[:, np.newaxis]
    covariance = addition_noise_covariance(
        residual, root * misfit_design(projection, aware), fit.n_params, root * loading, additions.sigma_pct / 100.0
    )
    scale = max(fit.ssr, _R2_RESOLUTION * aware.ss_tot) / n
    return covariance / scale


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
    was given, which :func:`~core.pipeline.results_io.verify_imported_result`
    checks. ``model_arithmetic`` names the equilibrium arithmetic every score
    was computed with, which tells that function how precisely they reproduce.
    ``loaded_replica_ids`` is every replicate of *ms* in its order, which names
    each replicate by its letter where the data are not loaded.
    """
    result.metadata['loaded_replica_ids'] = list(ms.replica_ids)
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
    average and reported by name, with the reason. Replicates stated as
    separate titrations with a random error of each addition each carry their
    own addition errors, and the test allows for them
    (:func:`_replicate_additions`).

    The replicates' own fits and the rounds of the test are searches over one
    :class:`~core.pipeline.varpro.Projection`, whose per-row residuals on the
    search grid are cached, so each of them costs only its refinement and not
    another grid, and each replicate's own fit is searched once and used twice —
    as that replicate's reported fit and as the residual the test weights it by.
    Measured at 30 points on the default Ka box with four replicates, they add
    0.05 s to a one-Ka fit and 3 s to a two-Ka fit, on top of the reported fit
    and its intervals. The shared projection runs with the weights a fit of the
    average of the replicates given runs with (:func:`fit_assay`): where the
    law has a share of proportional noise they are read off the curve of a
    first fit of that average. Where no replicate is left out, the reported fit
    is a fit of that same average, and it runs with those same weights.

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
        row — though the rows are fitted with the weights a fit of the average
        of the replicates given runs with under their law. Those fits are
        conditional: no input moves, and no error of the additions widens
        anything of theirs.

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
    bounds = _resolve_bounds(grid_assay, config.custom_bounds)
    # One noise law for the replicates given, and the weights a fit of their
    # average runs with under it, so every row of the shared projection — each
    # replicate's own fit and the test between them — counts a titration point
    # by the same precision.
    given_signals = ms.signals[rows]
    law = noise_law(given_signals)
    weights, curve = _point_weights(grid_assay, bounds, law, should_cancel)
    projection = Projection(
        grid_assay,
        bounds,
        signals=given_signals,
        should_cancel=should_cancel,
        point_weights=weights,
    )
    # Each row's own fit is both the replicate's reported fit and the residual
    # the shared-Ka test weights it by, so it is searched once and used twice.
    own_fits = [projection.fit(np.eye(len(given))[row]) for row in range(len(given))]
    replica_fits = [
        _replica_fit(ms, assay_cls, conditions, projection, config, rid, row, own_fits[row])
        for row, rid in enumerate(given)
    ]
    kappa, scatter = _replicate_additions(projection, bounds, own_fits, config.errors.additions, should_cancel)
    test = replicate_outliers(projection, own_fits, inflation=kappa, scatter_ssr=scatter)
    excluded = {given[row] for row in test.excluded}
    used = [rid for rid in given if rid not in excluded]

    record = dict(
        measurement_set_id=ms.id,
        source_file=ms.metadata.get('source_file'),
        should_cancel=should_cancel,
        replicate_signals=_replicate_rows(ms, used),
    )
    if excluded:
        result = fit_assay(
            ms.with_active(used).to_assay(assay_cls, conditions=conditions, use_average=True), config=config, **record
        )
    else:
        # The replicates used are the ones given: their average, its noise law
        # and the weights a fit of it runs with are those of the shared projection.
        result = _fit_weighted(grid_assay, config, bounds, law, weights, curve, **record)
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


def _replicate_additions(
    projection: Projection,
    bounds: Dict[str, Tuple[Quantity, Quantity]],
    own_fits: List[ProjectedFit],
    additions: Optional[AdditionError],
    should_cancel: Optional[Callable[[], bool]],
) -> Tuple[Optional[List[float]], Optional[List[float]]]:
    """What the stated addition errors do to every replicate's own fit, for the replicate test.

    Replicates stated as separate titrations each carry their own addition
    errors. Row *r* of *projection*, within *bounds* and fitted alone
    (*own_fits*), gets the design effect of its errors on its own Ka
    (:func:`~core.pipeline.inflation.inflation`, or its joint form for two
    free Ka), which the shared-Ka step divides its statistic by, and its
    residual with the residue of its own additions taken out
    (:func:`~core.pipeline.inflation.replicate_scatter_ssr`), which is what
    Cochran's test compares: that residue differs from one titration to the
    next and is not scatter. Where it cannot be read for every row, Cochran's
    test compares the residuals as they are. ``(None, None)`` where no addition error
    is stated, and where the replicates are repeated reads of one titration:
    they share its additions, which then move every replicate alike and none
    of them apart.
    """
    if additions is None or not additions.separate_titrations:
        return None, None
    stock = _titrant_stock(projection.assay)
    factors, alone_fits = [], []
    for row, own in enumerate(own_fits):
        alone = Projection(
            projection.assay,
            bounds,
            signals=projection.signals[row : row + 1],
            should_cancel=should_cancel,
            point_weights=projection.point_weights,
        )
        fit = replace(
            own,
            coefficients=own.coefficients[row : row + 1],
            row_ssr=own.row_ssr[row : row + 1],
            objective=float(own.row_ssr[row]),
        )
        if len(alone.free_ka) == 2:
            factors.append(joint_inflation(alone, fit, additions=additions, titrant_stock=stock))
        else:
            factors.append(max([1.0, *inflation(alone, fit, additions=additions, titrant_stock=stock).values()]))
        alone_fits.append((alone, fit))
    return factors, replicate_scatter_ssr(alone_fits, additions, stock)


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
