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

logger = logging.getLogger(__name__)


@dataclass
class FitResult:
    """Serializable container for fitting results.

    Designed for persistence and traceability.  Links back to its source
    ``MeasurementSet`` by ID (loose coupling, no object reference).

    Attributes
    ----------
    parameters : dict[str, float]
        Best-fit parameter name → value.
    uncertainties : dict[str, float]
        Parameter name → uncertainty (MAD of filtered fits).
    rmse : float
        Root mean squared error of the fit.
    r_squared : float
        Coefficient of determination.
    n_passing : int
        Number of fits that passed filtering criteria.
    n_total : int
        Total number of fit attempts.
    x_fit : np.ndarray
        Concentration grid used for fitting (for plotting the curve).
    y_fit : np.ndarray
        Model prediction at ``x_fit``.
    assay_type : str
        Assay type name (e.g. ``"GDA"``, ``"IDA"``).
    model_name : str
        Model identifier (e.g. ``"equilibrium_4param"``, ``"linear"``).
    conditions : dict[str, float]
        Assay conditions used (``Ka_dye``, ``h0``, etc.).
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

    parameters: Dict[str, float]
    uncertainties: Dict[str, float]
    rmse: float
    r_squared: float
    n_passing: int
    n_total: int
    x_fit: np.ndarray
    y_fit: np.ndarray
    assay_type: str
    model_name: str
    conditions: Dict[str, float] = field(default_factory=dict)
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

        ``np.ndarray`` fields are converted to plain Python lists.

        Returns
        -------
        dict[str, Any]
        """
        return {
            'id': self.id,
            'timestamp': self.timestamp,
            'measurement_set_id': self.measurement_set_id,
            'source_file': self.source_file,
            'assay_type': self.assay_type,
            'model_name': self.model_name,
            'conditions': self.conditions,
            'fit_config': self.fit_config,
            'parameters': self.parameters,
            'uncertainties': self.uncertainties,
            'rmse': self.rmse,
            'r_squared': self.r_squared,
            'n_passing': self.n_passing,
            'n_total': self.n_total,
            'x_fit': self.x_fit.tolist(),
            'y_fit': self.y_fit.tolist(),
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
        return cls(
            parameters=d['parameters'],
            uncertainties=d['uncertainties'],
            rmse=d['rmse'],
            r_squared=d['r_squared'],
            n_passing=d['n_passing'],
            n_total=d['n_total'],
            x_fit=np.asarray(d['x_fit']),
            y_fit=np.asarray(d['y_fit']),
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
    """Configuration for the fitting pipeline.

    Attributes
    ----------
    n_trials : int
        Number of multi-start optimisation trials (default 100).
    rmse_threshold_factor : float
        Multiplier applied to the best RMSE to define the acceptance
        window for ``aggregate_fits`` (default 1.5).
    min_r_squared : float
        Minimum R² for a fit attempt to be accepted (default 0.9).
    log_scale_params : list[str] or None
        Parameter **names** that should be sampled in log₁₀ space during
        multi-start initialisation.  Useful for association constants
        that span many orders of magnitude.

        * ``None`` (default) — use the assay-level default defined in
          ``AssayMetadata.log_scale_keys``.
        * ``[]`` — force *all* parameters to be sampled linearly.
        * ``['Ka_guest']`` — override to a specific set of names.
    custom_bounds : dict[str, tuple[float, float]] or None
        Named, *partial* bound overrides.  Only the parameters you
        specify are changed; all others keep their registry defaults.
        Keys must match entries in the assay’s ``parameter_keys``.

        Examples
        --------
        >>> # Tighten Ka only; I0/I_dye_free/I_dye_bound keep defaults
        >>> FitConfig(custom_bounds={'Ka_guest': (1e4, 1e8)})

        >>> # Inform signal bounds from a prior dye-alone fit
        >>> priors = bounds_from_dye_alone(dye_result, margin=0.2)
        >>> FitConfig(custom_bounds={**priors, 'Ka_guest': (1e4, 1e8)})
    """

    n_trials: int = 100
    rmse_threshold_factor: float = 1.5
    min_r_squared: float = 0.9
    log_scale_params: Optional[List[str]] = None
    custom_bounds: Optional[Dict[str, Tuple[float, float]]] = None


def _model_name_for_assay(assay: BaseAssay) -> str:
    """Derive a model name string from an assay instance."""
    if isinstance(assay, DyeAloneAssay):
        return 'linear'
    return 'equilibrium_4param'


def _config_to_dict(config: FitConfig) -> Dict[str, Any]:
    """Serialize a FitConfig to a plain dict."""
    return {
        'n_trials': config.n_trials,
        'rmse_threshold_factor': config.rmse_threshold_factor,
        'min_r_squared': config.min_r_squared,
        'log_scale_params': config.log_scale_params,
        'custom_bounds': ({k: list(v) for k, v in config.custom_bounds.items()} if config.custom_bounds is not None else None),
    }


def _resolve_bounds(
    assay: BaseAssay,
    custom_bounds: Optional[Dict[str, Tuple[float, float]]],
) -> List[Tuple[float, float]]:
    """Merge user overrides with registry defaults → positional bounds list.

    Parameters
    ----------
    assay : BaseAssay
        Assay whose registry defaults to start from.
    custom_bounds : dict or None
        Named partial overrides.  ``None`` means “use registry defaults”.

    Returns
    -------
    List[Tuple[float, float]]
        Positional bounds in ``parameter_keys`` order, ready for the
        optimizer.

    Raises
    ------
    ValueError
        If *custom_bounds* contains a key not in ``parameter_keys``.
    """
    bounds_dict = assay.get_default_bounds()
    if custom_bounds is not None:
        unknown = set(custom_bounds) - set(assay.parameter_keys)
        if unknown:
            raise ValueError(f'Unknown parameter(s) in custom_bounds: {sorted(unknown)}. Valid keys: {list(assay.parameter_keys)}')
        bounds_dict.update(custom_bounds)
    return [bounds_dict[k] for k in assay.parameter_keys]


def _resolve_log_scale(
    assay: BaseAssay,
    log_scale_params: Optional[List[str]],
) -> List[int]:
    """Convert parameter names → positional indices for the optimizer.

    Parameters
    ----------
    assay : BaseAssay
        The assay being fitted.
    log_scale_params : list[str] or None
        * ``None`` — use assay default (``AssayMetadata.log_scale_keys``).
        * ``[]`` — force linear sampling for every parameter.
        * ``['Ka_guest', ...]`` — user-specified names.

    Returns
    -------
    List[int]
        Positional indices into the parameter array.

    Raises
    ------
    ValueError
        If any name is not in ``parameter_keys``.
    """
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


def fit_assay(
    assay: BaseAssay,
    config: Optional[FitConfig] = None,
    *,
    measurement_set_id: Optional[str] = None,
    source_file: Optional[str] = None,
) -> FitResult:
    """Fit an assay using multi-start optimisation.

    This is the main entry point for non-linear fitting.  It:

    1. Resolves parameter bounds (registry defaults merged with any
       user overrides from ``config.custom_bounds``).
    2. Determines which parameters to sample in log space.
    3. Runs multi-start L-BFGS-B optimisation.
    4. Filters and aggregates results via median + MAD.

    Parameters
    ----------
    assay : BaseAssay
        The assay data to fit.
    config : FitConfig, optional
        Fitting configuration.  Uses ``FitConfig()`` defaults when
        omitted.
    measurement_set_id : str, optional
        UUID of the source ``MeasurementSet`` for traceability.
    source_file : str, optional
        Original filename, if known.

    Returns
    -------
    FitResult
        Serializable container with fitted parameters, uncertainties,
        and diagnostics.  Check ``result.success`` to see whether any
        fits passed the quality filter.
    """
    if config is None:
        config = FitConfig()

    # Merge user overrides with registry defaults
    bounds = _resolve_bounds(assay, config.custom_bounds)

    # Resolve log-scale parameters (names → indices)
    log_scale = _resolve_log_scale(assay, config.log_scale_params)

    # Define objective function
    def objective(params: np.ndarray) -> float:
        return assay.sum_squared_residuals(params)

    # Define metrics function
    def compute_metrics(params: np.ndarray) -> Tuple[float, float]:
        y_pred = assay.forward_model(params)
        return calculate_fit_metrics(assay.y_data, y_pred)

    # Run multi-start optimization
    all_attempts = multistart_minimize(
        objective=objective,
        bounds=bounds,
        n_trials=config.n_trials,
        log_scale_params=log_scale,
        compute_metrics=compute_metrics,
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
                'No fits passed filtering (n_trials=%d, rmse_factor=%.1f, min_r²=%.2f). Best attempt: RMSE=%.4e, R²=%.4f. Consider relaxing filtering thresholds or adjusting bounds.',
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
            x_fit=assay.x_data.copy(),
            y_fit=np.full_like(assay.x_data, np.nan),
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
    rmse, r_squared = calculate_fit_metrics(assay.y_data, y_pred)

    # Build named dicts
    params_dict = assay.params_to_dict(median_params)
    unc_dict = assay.params_to_dict(mad)
    y_fit = assay.forward_model(median_params)

    return FitResult(
        parameters=params_dict,
        uncertainties=unc_dict,
        rmse=rmse,
        r_squared=r_squared,
        n_passing=n_passing,
        n_total=len(all_attempts),
        x_fit=assay.x_data.copy(),
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

    This is a specialized function for the linear dye-alone case,
    which doesn't need multi-start optimization.

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
        Container with fitted slope, intercept, and diagnostics.
    """
    slope, intercept, r_squared, rmse = assay.fit_linear()
    y_fit = assay.forward_model(np.array([slope, intercept]))

    return FitResult(
        parameters={'slope': slope, 'intercept': intercept},
        uncertainties={'slope': np.nan, 'intercept': np.nan},
        rmse=rmse,
        r_squared=r_squared,
        n_passing=1,
        n_total=1,
        x_fit=assay.x_data.copy(),
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
) -> Dict[str, Tuple[float, float]]:
    """Derive signal-coefficient bounds from a dye-alone calibration.

    A dye-alone (linear) fit yields ``slope`` and ``intercept``.
    Physically:

    * **slope** = ΔSignal / Δ[Dye] ≈ ``I_dye_free`` (signal per unit
      free-dye concentration).
    * **intercept** = Signal at [Dye]=0 ≈ ``I0`` (background signal).

    This function converts those fitted values into named bound overrides
    that can be merged directly into :attr:`FitConfig.custom_bounds` for
    a downstream DBA / GDA / IDA fit, constraining the otherwise
    degenerate signal coefficients.

    Parameters
    ----------
    result : FitResult
        A *successful* dye-alone fit (``model_name == "linear"``).
    margin : float
        Fractional margin applied symmetrically around each value
        (default 0.2 → ±20 %).  The resulting window is
        ``[max(0, value * (1 - margin)),  value * (1 + margin)]``.
        Lower bounds are clamped to zero because signal intensities
        and association constants are non-negative physical quantities.

    Returns
    -------
    Dict[str, Tuple[float, float]]
        Partial bounds dict, e.g.
        ``{'I_dye_free': (4e7, 6e7), 'I0': (80, 120)}``.
        Lower bounds are clamped to zero (signal intensities are
        non-negative physical quantities).
        Merge with other overrides via ``{**bounds_from_dye_alone(r), ...}``.

    Raises
    ------
    ValueError
        If *result* is not a successful linear (dye-alone) fit.

    Examples
    --------
    >>> dye_result = fit_linear_assay(dye_assay)
    >>> priors = bounds_from_dye_alone(dye_result, margin=0.2)
    >>> config = FitConfig(custom_bounds={**priors, 'Ka_guest': (1e4, 1e8)})
    """
    if result.model_name != 'linear':
        raise ValueError(f"Expected a dye-alone (linear) FitResult, got model_name='{result.model_name}'")
    if not result.success:
        raise ValueError('Cannot derive bounds from a failed fit')

    slope = result.parameters['slope']
    intercept = result.parameters['intercept']

    def _window(value: float) -> Tuple[float, float]:
        half = abs(value) * margin if abs(value) > 0 else margin
        lo = max(0.0, value - half)
        hi = max(0.0, value + half)
        return (lo, hi)

    return {
        'I_dye_free': _window(slope),
        'I0': _window(intercept),
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
        Assay-specific conditions (``Ka_dye``, ``h0``, etc.).
    config : FitConfig, optional
        Fitting configuration.
    use_average : bool
        Use the averaged active-replica signal (default ``True``).
    replica_id : str, optional
        Fit a specific replica instead of the average.

    Returns
    -------
    FitResult
        With ``measurement_set_id`` automatically populated.
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
