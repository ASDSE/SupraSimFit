"""Fitting pipeline orchestration.

This module provides the main entry point for fitting assay data. The
FitPipeline class orchestrates:
1. Loading/preparing data
2. Running multi-start optimization
3. Filtering results by quality metrics
4. Aggregating to robust median estimates
5. Computing final fit metrics
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from core.assays.base import BaseAssay
from core.assays.dye_alone import DyeAloneAssay
from core.optimizer.filters import aggregate_fits, calculate_fit_metrics
from core.optimizer.multistart import FitAttempt, multistart_minimize


@dataclass
class FitResult:
    """Container for fitting results.

    Attributes
    ----------
    params : np.ndarray
        Best-fit parameter values (median of filtered fits).
    params_dict : Dict[str, float]
        Parameter names mapped to values.
    uncertainties : np.ndarray
        Parameter uncertainties (MAD of filtered fits).
    rmse : float
        Root mean squared error of the fit.
    r_squared : float
        Coefficient of determination.
    n_passing : int
        Number of fits that passed filtering criteria.
    n_total : int
        Total number of fit attempts.
    all_attempts : List[FitAttempt]
        All individual fit attempts.
    assay : BaseAssay
        The assay that was fitted.
    metadata : Dict[str, Any]
        Additional metadata about the fit.
    """

    params: np.ndarray
    params_dict: Dict[str, float]
    uncertainties: np.ndarray
    rmse: float
    r_squared: float
    n_passing: int
    n_total: int
    all_attempts: List[FitAttempt]
    assay: BaseAssay
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """Whether the fit was successful (at least one passing fit)."""
        return self.n_passing > 0


@dataclass
class FitConfig:
    """Configuration for fitting pipeline.

    Attributes
    ----------
    n_trials : int
        Number of multi-start optimization trials.
    rmse_threshold_factor : float
        Multiplier for best RMSE to set acceptance threshold.
    min_r_squared : float
        Minimum R² for accepting a fit.
    log_scale_params : List[int]
        Indices of parameters to sample in log space.
    custom_bounds : Optional[List[Tuple[float, float]]]
        Custom parameter bounds (overrides registry defaults).
    """

    n_trials: int = 100
    rmse_threshold_factor: float = 1.5
    min_r_squared: float = 0.9
    log_scale_params: Optional[List[int]] = None
    custom_bounds: Optional[List[Tuple[float, float]]] = None


def fit_assay(
    assay: BaseAssay,
    config: Optional[FitConfig] = None,
) -> FitResult:
    """Fit an assay using multi-start optimization.

    This is the main entry point for fitting. It runs multi-start optimization,
    filters results by quality, and returns robust median estimates.

    Parameters
    ----------
    assay : BaseAssay
        The assay data to fit.
    config : FitConfig, optional
        Fitting configuration. Uses defaults if not provided.

    Returns
    -------
    FitResult
        Container with fitted parameters, uncertainties, and diagnostics.

    Example
    -------
    >>> from core.assays import GDAAssay
    >>> from core.pipeline import fit_assay
    >>>
    >>> assay = GDAAssay(
    ...     x_data=guest_conc,
    ...     y_data=signal,
    ...     K_D=1e-6,
    ...     h0=10e-6,
    ...     d0=1e-6,
    ... )
    >>> result = fit_assay(assay)
    >>> print(f"K_G = {result.params_dict['K_D']:.2e} M")
    """
    if config is None:
        config = FitConfig()

    # Get bounds from registry or custom
    if config.custom_bounds is not None:
        bounds = config.custom_bounds
    else:
        lower, upper = assay.get_default_bounds()
        bounds = list(zip(lower, upper))

    # Determine log-scale parameters (typically dissociation constants)
    log_scale = config.log_scale_params
    if log_scale is None:
        # Default: first parameter is usually K_D (log-scale)
        log_scale = [0]

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
        # Fall back to best single fit
        if all_attempts:
            best = all_attempts[0]
            median_params = best.params
            mad = np.zeros_like(median_params)
            rmse, r_squared = best.rmse, best.r_squared
        else:
            # Complete failure
            return FitResult(
                params=np.array([]),
                params_dict={},
                uncertainties=np.array([]),
                rmse=np.inf,
                r_squared=0.0,
                n_passing=0,
                n_total=config.n_trials,
                all_attempts=all_attempts,
                assay=assay,
                metadata={'error': 'All fit attempts failed'},
            )
    else:
        # Calculate metrics for median parameters
        y_pred = assay.forward_model(median_params)
        rmse, r_squared = calculate_fit_metrics(assay.y_data, y_pred)

    return FitResult(
        params=median_params,
        params_dict=assay.params_to_dict(median_params),
        uncertainties=mad,
        rmse=rmse,
        r_squared=r_squared,
        n_passing=n_passing,
        n_total=len(all_attempts),
        all_attempts=all_attempts,
        assay=assay,
        metadata={
            'config': {
                'n_trials': config.n_trials,
                'rmse_threshold_factor': config.rmse_threshold_factor,
                'min_r_squared': config.min_r_squared,
            },
            'conditions': assay.get_conditions(),
        },
    )


def fit_linear_assay(assay: DyeAloneAssay) -> FitResult:
    """Fit a dye-alone assay using simple linear regression.

    This is a specialized function for the linear dye-alone case,
    which doesn't need multi-start optimization.

    Parameters
    ----------
    assay : DyeAloneAssay
        The dye-alone calibration data.

    Returns
    -------
    FitResult
        Container with fitted slope, intercept, and diagnostics.
    """
    slope, intercept, r_squared, rmse = assay.fit_linear()

    params = np.array([slope, intercept])

    return FitResult(
        params=params,
        params_dict={'slope': slope, 'intercept': intercept},
        uncertainties=np.array([np.nan, np.nan]),  # No uncertainty from single fit
        rmse=rmse,
        r_squared=r_squared,
        n_passing=1,
        n_total=1,
        all_attempts=[],
        assay=assay,
        metadata={'method': 'linear_regression'},
    )
