"""Fitting pipeline orchestration.

This module provides the main entry point for fitting assay data. The
pipeline orchestrates:
1. Loading/preparing data
2. Running multi-start optimization
3. Filtering results by quality metrics
4. Aggregating to robust median estimates
5. Computing final fit metrics
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

import numpy as np

from core.assays.base import BaseAssay
from core.assays.dye_alone import DyeAloneAssay
from core.data_processing.measurement_set import MeasurementSet
from core.optimizer.filters import calculate_fit_metrics, filter_fits
from core.optimizer.multistart import FitAttempt, multistart_minimize
from core.optimizer.scaling import ParamScaler
from core.units import Q_, Quantity

logger = logging.getLogger(__name__)


@dataclass
class FitResult:
    """Serializable container for fitting results.

    All fitted parameter values and uncertainties are stored as
    ``pint.Quantity`` objects with proper units.

    Attributes
    ----------
    parameters : dict[str, Quantity]
        Best-fit parameter name → Quantity value.
    uncertainties : dict[str, Quantity]
        Parameter name → uncertainty (MAD of filtered fits) as Quantity.
    rmse : float
        Root mean squared error of the fit.
    r_squared : float
        Coefficient of determination.
    n_passing : int
        Number of fits that passed filtering criteria.
    n_total : int
        Total number of fit attempts.
    x_fit : Quantity
        Concentration grid used for fitting (for plotting the curve).
    y_fit : Quantity
        Model prediction at ``x_fit``.
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
        Additional metadata about the fit.
    uncertainty_source : str
        ``"optimizer"`` (default): uncertainties are the spread of the
        multistart passing-trial pool on a single signal.  ``"replicate"``:
        uncertainties are the spread of the pooled passing trials across
        every active replicate (populated by
        :func:`fit_measurement_set_per_replicate`).
    replica_fits : list[FitResult] | None
        Per-replicate fit results when this is an aggregate from
        :func:`fit_measurement_set_per_replicate`; ``None`` for single-signal
        fits.  Retained for diagnostic inspection only — the reported
        ``parameters`` and ``uncertainties`` are computed directly from
        the pooled ``parameter_samples``, not from these.
    parameter_samples : dict[str, np.ndarray] | None
        One flat array per parameter key holding every passing trial's
        parameter value (length == ``n_passing``).  In average mode this
        is the multistart pool on the single averaged signal; in
        per-replicate mode it is the concatenation of passing trials
        across every active replicate (the pool downstream box-and-whisker
        plots consume).  Both ``parameters`` (median) and
        ``uncertainties`` (MAD) are computed directly from this pool.
    """

    parameters: Dict[str, Quantity]
    uncertainties: Dict[str, Quantity]
    rmse: float
    r_squared: float
    n_passing: int
    n_total: int
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
    uncertainty_source: str = 'optimizer'
    replica_fits: Optional[List['FitResult']] = None
    parameter_samples: Optional[Dict[str, np.ndarray]] = None

    @property
    def success(self) -> bool:
        """Whether the fit was successful (at least one passing fit)."""
        return self.n_passing > 0

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
        from core.assays.registry import ASSAY_REGISTRY, AssayType

        # Look up units from registry
        try:
            at = AssayType[self.assay_type]
            units = dict(ASSAY_REGISTRY[at].units)
        except KeyError:
            units = {}

        # Serialize parameters as magnitudes
        params_serial = {}
        for k, v in self.parameters.items():
            params_serial[k] = float(v.magnitude)

        unc_serial = {}
        for k, v in self.uncertainties.items():
            unc_serial[k] = float(v.magnitude)

        # Serialize conditions
        cond_serial = {}
        for k, v in self.conditions.items():
            if isinstance(v, Quantity):
                cond_serial[k] = float(v.magnitude)
            else:
                cond_serial[k] = v

        # Serialize x_fit / y_fit
        x_list = self.x_fit.magnitude.tolist()
        y_list = self.y_fit.magnitude.tolist()

        replica_fits_serial: Optional[List[Dict[str, Any]]] = None
        if self.replica_fits is not None:
            replica_fits_serial = [rf.to_dict() for rf in self.replica_fits]

        parameter_samples_serial: Optional[Dict[str, List[float]]] = None
        if self.parameter_samples is not None:
            parameter_samples_serial = {
                k: [float(v) for v in arr]
                for k, arr in self.parameter_samples.items()
            }

        return {
            'id': self.id,
            'timestamp': self.timestamp,
            'measurement_set_id': self.measurement_set_id,
            'source_file': self.source_file,
            'assay_type': self.assay_type,
            'model_name': self.model_name,
            'conditions': cond_serial,
            'fit_config': self.fit_config,
            'parameters': params_serial,
            'uncertainties': unc_serial,
            'parameter_units': units,
            'rmse': self.rmse,
            'r_squared': self.r_squared,
            'n_passing': self.n_passing,
            'n_total': self.n_total,
            'x_fit': x_list,
            'y_fit': y_list,
            'metadata': self.metadata,
            'uncertainty_source': self.uncertainty_source,
            'replica_fits': replica_fits_serial,
            'parameter_samples': parameter_samples_serial,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'FitResult':
        """Reconstruct a ``FitResult`` from a dictionary.

        Parameters
        ----------
        d : dict
            As produced by :meth:`to_dict`.

        Returns
        -------
        FitResult
        """
        from core.assays.registry import ASSAY_REGISTRY, AssayType

        # Look up units from registry or dict
        param_units = d.get('parameter_units', {})
        if not param_units:
            try:
                at = AssayType[d['assay_type']]
                param_units = dict(ASSAY_REGISTRY[at].units)
            except KeyError:
                param_units = {}

        # Reconstruct Quantity parameters
        parameters = {}
        for k, v in d['parameters'].items():
            unit = param_units.get(k)
            parameters[k] = Q_(v, unit) if unit else Q_(v, 'dimensionless')

        uncertainties = {}
        for k, v in d['uncertainties'].items():
            unit = param_units.get(k)
            uncertainties[k] = Q_(v, unit) if unit else Q_(v, 'dimensionless')

        # Reconstruct x_fit / y_fit as Quantities
        x_fit = Q_(np.asarray(d['x_fit']), 'M')
        y_fit = Q_(np.asarray(d['y_fit']), 'au')

        replica_fits_data = d.get('replica_fits')
        replica_fits: Optional[List['FitResult']] = None
        if replica_fits_data is not None:
            replica_fits = [cls.from_dict(rf) for rf in replica_fits_data]

        parameter_samples_data = d.get('parameter_samples')
        parameter_samples: Optional[Dict[str, np.ndarray]] = None
        if parameter_samples_data is not None:
            parameter_samples = {
                k: np.asarray(v, dtype=float)
                for k, v in parameter_samples_data.items()
            }

        return cls(
            parameters=parameters,
            uncertainties=uncertainties,
            rmse=d['rmse'],
            r_squared=d['r_squared'],
            n_passing=d['n_passing'],
            n_total=d['n_total'],
            x_fit=x_fit,
            y_fit=y_fit,
            assay_type=d['assay_type'],
            model_name=d['model_name'],
            conditions=d.get('conditions', {}),
            fit_config=d.get('fit_config', {}),
            measurement_set_id=d.get('measurement_set_id'),
            source_file=d.get('source_file'),
            id=d.get('id', uuid.uuid4().hex),
            timestamp=d.get('timestamp', datetime.now(timezone.utc).isoformat()),
            metadata=d.get('metadata', {}),
            uncertainty_source=d.get('uncertainty_source', 'optimizer'),
            replica_fits=replica_fits,
            parameter_samples=parameter_samples,
        )


@dataclass
class FitConfig:
    """Configuration for the fitting pipeline."""

    n_trials: int = 100
    rmse_threshold_factor: float = 1.5
    min_r_squared: float = 0.9
    log_scale_params: Optional[List[str]] = None
    custom_bounds: Optional[Dict[str, Tuple[Quantity, Quantity]]] = None
    rescale_parameters: bool = True
    per_replicate: bool = False


def _model_name_for_assay(assay: BaseAssay) -> str:
    """Derive a model name string from an assay instance."""
    if isinstance(assay, DyeAloneAssay):
        return 'linear'
    return 'equilibrium_4param'


def _config_to_dict(config: FitConfig) -> Dict[str, Any]:
    """Serialize a FitConfig to a plain dict."""
    custom_bounds: Optional[Dict[str, List[float]]] = None
    if config.custom_bounds is not None:
        custom_bounds = {}
        for key, (lo, hi) in config.custom_bounds.items():
            custom_bounds[key] = [float(lo.magnitude), float(hi.magnitude)]
    return {
        'n_trials': config.n_trials,
        'rmse_threshold_factor': config.rmse_threshold_factor,
        'min_r_squared': config.min_r_squared,
        'log_scale_params': config.log_scale_params,
        'custom_bounds': custom_bounds,
        'rescale_parameters': config.rescale_parameters,
        'per_replicate': config.per_replicate,
    }


def _resolve_bounds(
    assay: BaseAssay,
    custom_bounds: Optional[Dict[str, Tuple[Quantity, Quantity]]],
) -> Dict[str, Tuple[Quantity, Quantity]]:
    """Merge user overrides with registry defaults -> named bounds dict."""
    bounds_dict = assay.get_default_bounds()
    if custom_bounds is not None:
        unknown = set(custom_bounds) - set(assay.parameter_keys)
        if unknown:
            raise ValueError(f'Unknown parameter(s) in custom_bounds: {sorted(unknown)}. Valid keys: {list(assay.parameter_keys)}')
        bounds_dict.update(custom_bounds)
    return bounds_dict


def _resolve_log_scale(
    assay: BaseAssay,
    log_scale_params: Optional[List[str]],
) -> List[int]:
    """Convert parameter names -> positional indices for the optimizer."""
    if log_scale_params is None:
        names = list(assay.registry_metadata.log_scale_keys)
    else:
        names = list(log_scale_params)

    keys = assay.parameter_keys
    indices: List[int] = []
    for name in names:
        if name not in keys:
            raise ValueError(f"Unknown log-scale parameter '{name}'. Valid keys: {list(keys)}")
        indices.append(keys.index(name))
    return indices


def _wrap_params_as_quantities(
    params: np.ndarray,
    assay: BaseAssay,
) -> Dict[str, Quantity]:
    """Wrap optimizer float params into named Quantity dict."""
    from core.assays.registry import ASSAY_REGISTRY

    units = ASSAY_REGISTRY[assay.assay_type].units
    result = {}
    for key, value in zip(assay.parameter_keys, params):
        unit = units.get(key, 'dimensionless')
        result[key] = Q_(float(value), unit)
    return result


def fit_assay(
    assay: BaseAssay,
    config: Optional[FitConfig] = None,
    *,
    measurement_set_id: Optional[str] = None,
    source_file: Optional[str] = None,
) -> FitResult:
    """Fit an assay using multi-start optimisation.

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

    Returns
    -------
    FitResult
        With Quantity parameters, uncertainties, x_fit, y_fit.
    """
    if config is None:
        config = FitConfig()

    # Resolve bounds (Quantity dicts)
    bounds_dict = _resolve_bounds(assay, config.custom_bounds)

    # Extract float bounds for scipy
    float_bounds = [(float(bounds_dict[k][0].magnitude), float(bounds_dict[k][1].magnitude)) for k in assay.parameter_keys]

    # Resolve log-scale parameters (names -> indices)
    log_scale = _resolve_log_scale(assay, config.log_scale_params)

    # y_data magnitude for metrics
    y_data_mag = assay.y_data.magnitude

    # Define objective function
    def objective(params: np.ndarray) -> float:
        return assay.sum_squared_residuals(params)

    # Define metrics function
    def compute_metrics(params: np.ndarray) -> Tuple[float, float]:
        y_pred = assay.forward_model(params)
        return calculate_fit_metrics(y_data_mag, y_pred.magnitude)

    scaler: Optional[ParamScaler] = None
    if config.rescale_parameters:
        scaler = ParamScaler.from_assay(assay)

    # Run multi-start optimization
    all_attempts = multistart_minimize(
        objective=objective,
        bounds=float_bounds,
        n_trials=config.n_trials,
        log_scale_params=log_scale,
        compute_metrics=compute_metrics,
        scaler=scaler,
    )

    # Keep the filtered pool around so parameter_samples can be populated —
    # this is the full distribution of passing trials, not just their median.
    passing_attempts = filter_fits(
        all_attempts,
        rmse_threshold_factor=config.rmse_threshold_factor,
        min_r_squared=config.min_r_squared,
    )

    if passing_attempts:
        param_matrix = np.array([a.params for a in passing_attempts], dtype=float)
        median_params = np.median(param_matrix, axis=0)
        mad = np.median(np.abs(param_matrix - median_params), axis=0)
        n_passing = len(passing_attempts)
    else:
        median_params = None
        mad = None
        n_passing = 0

    # Handle case where no fits pass
    if median_params is None:
        if all_attempts:
            best = all_attempts[0]
            logger.warning(
                'No fits passed filtering (n_trials=%d, rmse_factor=%.1f, min_r2=%.2f). Best attempt: RMSE=%.4e, R2=%.4f.',
                config.n_trials,
                config.rmse_threshold_factor,
                config.min_r_squared,
                best.rmse,
                best.r_squared,
            )
            diag = {
                'error': 'No fits passed filtering criteria',
                'best_attempt_rmse': best.rmse,
                'best_attempt_r_squared': best.r_squared,
                'best_attempt_params': assay.params_to_dict(best.params),
                'hint': ('All fit attempts were rejected by the quality filter. Try: (1) increasing rmse_threshold_factor, (2) lowering min_r_squared, (3) increasing n_trials, or (4) reviewing parameter bounds.'),
            }
        else:
            logger.warning(
                'All %d fit attempts failed (optimizer did not converge).',
                config.n_trials,
            )
            diag = {'error': 'All fit attempts failed to converge'}

        return FitResult(
            parameters={},
            uncertainties={},
            rmse=np.inf,
            r_squared=0.0,
            n_passing=0,
            n_total=len(all_attempts) if all_attempts else config.n_trials,
            x_fit=assay.x_data,
            y_fit=Q_(np.full(len(assay.x_data), np.nan), 'au'),
            assay_type=assay.assay_type.name,
            model_name=_model_name_for_assay(assay),
            conditions=assay.get_conditions(),
            fit_config=_config_to_dict(config),
            measurement_set_id=measurement_set_id,
            source_file=source_file,
            metadata=diag,
        )

    # Calculate metrics for median parameters
    y_pred = assay.forward_model(median_params)
    rmse, r_squared = calculate_fit_metrics(y_data_mag, y_pred.magnitude)

    # Build Quantity parameter dicts
    params_q = _wrap_params_as_quantities(median_params, assay)
    unc_q = _wrap_params_as_quantities(mad, assay)
    y_fit = assay.forward_model(median_params)

    parameter_samples = {
        k: param_matrix[:, i].copy()
        for i, k in enumerate(assay.parameter_keys)
    }

    return FitResult(
        parameters=params_q,
        uncertainties=unc_q,
        rmse=rmse,
        r_squared=r_squared,
        n_passing=n_passing,
        n_total=len(all_attempts),
        x_fit=assay.x_data,
        y_fit=y_fit,
        assay_type=assay.assay_type.name,
        model_name=_model_name_for_assay(assay),
        conditions=assay.get_conditions(),
        fit_config=_config_to_dict(config),
        measurement_set_id=measurement_set_id,
        source_file=source_file,
        parameter_samples=parameter_samples,
    )


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
        uncertainties={
            'slope': Q_(np.nan, slope.units),
            'intercept': Q_(np.nan, intercept.units),
        },
        rmse=float(rmse.magnitude),
        r_squared=r_squared,
        n_passing=1,
        n_total=1,
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
        A *successful* dye-alone fit (``model_name == "linear"``).
    margin : float
        Fractional margin (default 0.2 = +/-20%).

    Returns
    -------
    Dict[str, Tuple[Quantity, Quantity]]
    """
    if result.model_name != 'linear':
        raise ValueError(f"Expected a dye-alone (linear) FitResult, got model_name='{result.model_name}'")
    if not result.success:
        raise ValueError('Cannot derive bounds from a failed fit')

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
) -> FitResult:
    """Convenience: build an assay from a MeasurementSet and fit it.

    When ``config.per_replicate`` is ``True`` and neither ``use_average=False``
    nor an explicit ``replica_id`` is provided, dispatches to
    :func:`fit_measurement_set_per_replicate`, which fits each active replica
    independently and aggregates parameters across replicates.

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

    Returns
    -------
    FitResult
    """
    if config is not None and config.per_replicate and replica_id is None and use_average:
        return fit_measurement_set_per_replicate(ms, assay_cls, conditions, config)

    assay = ms.to_assay(
        assay_cls,
        conditions=conditions,
        use_average=use_average,
        replica_id=replica_id,
    )

    if isinstance(assay, DyeAloneAssay):
        return fit_linear_assay(
            assay,
            measurement_set_id=ms.id,
            source_file=ms.metadata.get('source_file'),
        )

    return fit_assay(
        assay,
        config=config,
        measurement_set_id=ms.id,
        source_file=ms.metadata.get('source_file'),
    )


class PerReplicateFitError(RuntimeError):
    """Raised when per-replicate fitting cannot produce any surviving fit.

    Carries a ``failures`` mapping of ``replica_id -> reason`` so the GUI
    layer can surface a no-silent-fallbacks warning listing every failed
    replicate.
    """

    def __init__(self, message: str, failures: Dict[str, str]):
        super().__init__(message)
        self.failures = dict(failures)


def fit_measurement_set_per_replicate(
    ms: MeasurementSet,
    assay_cls: Type[BaseAssay],
    conditions: Dict[str, Any],
    config: Optional[FitConfig] = None,
) -> FitResult:
    """Fit every active replica independently and pool passing trials.

    Each active replica is fit with its own multistart run (the same
    ``config`` — including ``rescale_parameters`` — is forwarded unchanged
    to every per-replica call).  Because the parameter rescaler is an
    exact affine bijection [core/optimizer/scaling.py:20-23], every
    per-replica ``FitResult`` emerges in physical units regardless of
    its per-replica scaler, so parameter values from every replicate
    live in the same raw-unit space.

    **Aggregation semantics (approach (b), pooled):** every replicate's
    passing trials — not its pre-collapsed median — are concatenated
    into a single flat pool (per parameter key) stored on the returned
    ``FitResult.parameter_samples``.  The reported ``parameters`` are
    the **median of that pool** and ``uncertainties`` are the MAD of
    that pool.  A replicate with more passing trials therefore
    contributes proportionally more samples to the pool; this matches
    the user-requested design (every acceptable fit counts equally).

    This is strictly richer than the earlier median-of-medians approach:
    with N replicas × ~80 passing trials each, the pool has ~80N
    samples; the previous aggregator collapsed the same data to N
    points before computing MAD.

    The reported ``x_fit``/``y_fit`` is the forward model evaluated at
    the pooled median parameters on the shared concentration grid — this
    is the "Median Fit" curve drawn in the plot.  RMSE and R² on the
    aggregate are computed against the averaged active-replica signal.

    Failure handling: a replica that raises (degenerate scaler input,
    convergence failure, …) is skipped and recorded in the returned
    FitResult's metadata.  If no replica survives, a
    :class:`PerReplicateFitError` is raised with the full failure map so
    the GUI can report every bad replica.

    Parameters
    ----------
    ms : MeasurementSet
        Source data with one or more active replicas.
    assay_cls : Type[BaseAssay]
        Concrete assay class.
    conditions : dict
        Assay-specific conditions as Quantity values.
    config : FitConfig, optional
        Fitting configuration.  ``per_replicate`` is ignored (this function
        *is* the per-replicate path) but every other field — including
        ``rescale_parameters`` — is forwarded to each per-replica fit.

    Returns
    -------
    FitResult
        Aggregate result whose ``parameters`` and ``uncertainties`` are
        the pooled median and MAD across every passing trial from every
        successful replica, ``uncertainty_source == "replicate"``,
        ``parameter_samples`` holds the pool, and ``replica_fits`` holds
        the per-replica successful fits for diagnostic inspection.
    """
    if config is None:
        config = FitConfig()

    active_ids = ms.active_replica_ids
    if not active_ids:
        raise ValueError('No active replicas to fit.')

    per_call_config = replace(config, per_replicate=False)

    replica_fits: List[FitResult] = []
    succeeded_ids: List[str] = []
    failures: Dict[str, str] = {}
    for rid in active_ids:
        try:
            rr = fit_measurement_set(
                ms,
                assay_cls,
                conditions,
                per_call_config,
                use_average=False,
                replica_id=rid,
            )
        except Exception as exc:
            failures[rid] = f'{type(exc).__name__}: {exc}'
            logger.warning('Per-replicate fit failed for replica %s: %s', rid, exc)
            continue

        if not rr.success:
            failures[rid] = 'No trials passed the quality filter.'
            continue

        if rr.parameter_samples is None:
            failures[rid] = 'Per-replica fit returned no parameter_samples pool to aggregate.'
            continue

        rr.metadata.setdefault('replica_id', rid)
        replica_fits.append(rr)
        succeeded_ids.append(rid)

    if not replica_fits:
        raise PerReplicateFitError(
            f'Per-replicate fitting failed on all {len(active_ids)} active replica(s).',
            failures,
        )

    # Pool: concatenate every replica's passing-trial samples per parameter.
    param_keys = tuple(replica_fits[0].parameter_samples.keys())
    for rr in replica_fits[1:]:
        if tuple(rr.parameter_samples.keys()) != param_keys:
            raise ValueError(
                f'Replicate parameter keys differ: {param_keys} vs {tuple(rr.parameter_samples.keys())}.'
            )
    pool: Dict[str, np.ndarray] = {
        k: np.concatenate([rr.parameter_samples[k] for rr in replica_fits])
        for k in param_keys
    }
    pool_size = len(next(iter(pool.values())))

    any_fit = replica_fits[0]
    param_units = {k: v.units for k, v in any_fit.parameters.items()}
    params_q: Dict[str, Any] = {}
    unc_q: Dict[str, Any] = {}
    for k in param_keys:
        samples = pool[k]
        median = float(np.median(samples))
        mad = float(np.median(np.abs(samples - median)))
        params_q[k] = Q_(median, param_units[k])
        unc_q[k] = Q_(mad, param_units[k])

    template_assay = ms.to_assay(
        assay_cls,
        conditions=conditions,
        use_average=True,
    )
    median_vec = np.array(
        [float(params_q[k].magnitude) for k in template_assay.parameter_keys],
        dtype=float,
    )
    y_avg = template_assay.y_data.magnitude
    y_pred = template_assay.forward_model(median_vec)
    rmse, r_squared = calculate_fit_metrics(y_avg, y_pred.magnitude)

    n_total_pool = sum(rr.n_total for rr in replica_fits)

    metadata: Dict[str, Any] = {
        'n_replicas_total': len(active_ids),
        'n_replicas_fit': len(replica_fits),
        'replica_ids_fit': list(succeeded_ids),
        'pool_size': pool_size,
        'per_replica_n_passing': {rid: rf.n_passing for rid, rf in zip(succeeded_ids, replica_fits)},
    }
    if failures:
        metadata['replica_failures'] = failures

    return FitResult(
        parameters=params_q,
        uncertainties=unc_q,
        rmse=rmse,
        r_squared=r_squared,
        n_passing=pool_size,
        n_total=n_total_pool,
        x_fit=template_assay.x_data,
        y_fit=y_pred,
        assay_type=template_assay.assay_type.name,
        model_name=_model_name_for_assay(template_assay),
        conditions=template_assay.get_conditions(),
        fit_config=_config_to_dict(config),
        measurement_set_id=ms.id,
        source_file=ms.metadata.get('source_file'),
        metadata=metadata,
        uncertainty_source='replicate',
        replica_fits=replica_fits,
        parameter_samples=pool,
    )
