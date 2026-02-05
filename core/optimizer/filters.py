"""Filtering and aggregation utilities for fit results.

This module provides functions to filter fit attempts by quality metrics
(RMSE, R²) and aggregate passing fits using robust statistics (median, MAD).
"""

from typing import List, Optional, Tuple

import numpy as np

from core.optimizer.multistart import FitAttempt


def filter_by_rmse(
    results: List[FitAttempt],
    threshold_factor: float = 1.5,
    reference_rmse: Optional[float] = None,
) -> List[FitAttempt]:
    """Filter fit attempts by RMSE threshold.

    Parameters
    ----------
    results : List[FitAttempt]
        Fit attempts to filter.
    threshold_factor : float
        Multiplier applied to reference RMSE to set threshold.
    reference_rmse : float, optional
        Reference RMSE for threshold. If None, uses minimum RMSE from results.

    Returns
    -------
    List[FitAttempt]
        Fit attempts with RMSE <= threshold.
    """
    if not results:
        return []

    if reference_rmse is None:
        reference_rmse = min(r.rmse for r in results)

    threshold = reference_rmse * threshold_factor
    return [r for r in results if r.rmse <= threshold]


def filter_by_r_squared(
    results: List[FitAttempt],
    min_r_squared: float = 0.9,
) -> List[FitAttempt]:
    """Filter fit attempts by minimum R² value.

    Parameters
    ----------
    results : List[FitAttempt]
        Fit attempts to filter.
    min_r_squared : float
        Minimum acceptable R² value.

    Returns
    -------
    List[FitAttempt]
        Fit attempts with R² >= min_r_squared.
    """
    return [r for r in results if r.r_squared >= min_r_squared]


def filter_fits(
    results: List[FitAttempt],
    rmse_threshold_factor: float = 1.5,
    min_r_squared: float = 0.9,
) -> List[FitAttempt]:
    """Filter fit attempts by both RMSE and R² criteria.

    Parameters
    ----------
    results : List[FitAttempt]
        Fit attempts to filter.
    rmse_threshold_factor : float
        Multiplier for best RMSE to set threshold.
    min_r_squared : float
        Minimum acceptable R² value.

    Returns
    -------
    List[FitAttempt]
        Fit attempts passing both criteria.
    """
    filtered = filter_by_rmse(results, rmse_threshold_factor)
    filtered = filter_by_r_squared(filtered, min_r_squared)
    return filtered


def compute_median_params(results: List[FitAttempt]) -> Optional[np.ndarray]:
    """Compute median parameters from filtered fit attempts.

    Parameters
    ----------
    results : List[FitAttempt]
        Fit attempts to aggregate.

    Returns
    -------
    np.ndarray or None
        Median parameter values, or None if no results.
    """
    if not results:
        return None

    param_matrix = np.array([r.params for r in results])
    return np.median(param_matrix, axis=0)


def compute_mad(results: List[FitAttempt]) -> Optional[np.ndarray]:
    """Compute median absolute deviation of parameters.

    MAD is a robust measure of spread, less sensitive to outliers than
    standard deviation.

    Parameters
    ----------
    results : List[FitAttempt]
        Fit attempts to analyze.

    Returns
    -------
    np.ndarray or None
        MAD for each parameter, or None if no results.
    """
    if not results:
        return None

    param_matrix = np.array([r.params for r in results])
    median_params = np.median(param_matrix, axis=0)
    mad = np.median(np.abs(param_matrix - median_params), axis=0)
    return mad


def aggregate_fits(
    results: List[FitAttempt],
    rmse_threshold_factor: float = 1.5,
    min_r_squared: float = 0.9,
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], int]:
    """Filter and aggregate fit results to median parameters.

    Parameters
    ----------
    results : List[FitAttempt]
        All fit attempts.
    rmse_threshold_factor : float
        Multiplier for best RMSE to set threshold.
    min_r_squared : float
        Minimum acceptable R² value.

    Returns
    -------
    Tuple[np.ndarray, np.ndarray, int]
        (median_params, mad, n_passing). All are None/0 if no fits pass.
    """
    filtered = filter_fits(results, rmse_threshold_factor, min_r_squared)

    if not filtered:
        return None, None, 0

    median_params = compute_median_params(filtered)
    mad = compute_mad(filtered)

    return median_params, mad, len(filtered)


def calculate_fit_metrics(
    y_observed: np.ndarray,
    y_predicted: np.ndarray,
) -> Tuple[float, float]:
    """Calculate RMSE and R² for a fit.

    Parameters
    ----------
    y_observed : np.ndarray
        Observed signal values.
    y_predicted : np.ndarray
        Predicted signal values.

    Returns
    -------
    Tuple[float, float]
        (rmse, r_squared)
    """
    residuals = y_observed - y_predicted
    ss_res = np.sum(residuals**2)
    ss_tot = np.sum((y_observed - np.mean(y_observed)) ** 2)

    rmse = np.sqrt(np.mean(residuals**2))
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    return rmse, r_squared
