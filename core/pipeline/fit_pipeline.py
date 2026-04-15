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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

import numpy as np

from core.assays.base import BaseAssay
from core.assays.dye_alone import DyeAloneAssay
from core.data_processing.measurement_set import MeasurementSet
from core.optimizer.filters import aggregate_fits, calculate_fit_metrics
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

    # Aggregate results
    median_params, mad, n_passing = aggregate_fits(
        all_attempts,
        rmse_threshold_factor=config.rmse_threshold_factor,
        min_r_squared=config.min_r_squared,
    )

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
