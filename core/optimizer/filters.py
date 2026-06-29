"""Filtering utilities for fit results.

Filter multi-start fit attempts down to the *valid pool* by quality
metrics (R², RMSE). Collapsing that pool to a reported result lives in
:mod:`core.optimizer.ensemble`, not here.
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


def select_valid_fits(
    results: List[FitAttempt],
    min_r_squared: float = 0.9,
    rmse_threshold_factor: Optional[float] = None,
) -> List[FitAttempt]:
    """Select the valid-fit pool kept for aggregation.

    The absolute R² floor is the primary quality gate — it is an absolute
    RMSE gate too, since R² and RMSE are monotonically related on a fixed
    dataset. The relative RMSE trim is an *optional* extra tightening
    (off by default): when ``rmse_threshold_factor`` is given, fits with
    ``RMSE > best_valid_RMSE * factor`` are also dropped.

    No convergence (``success``) gate: an attempt reaching ``R² >= floor``
    is a good fit regardless of the optimizer's status flag, and gating on
    ``success`` would risk discarding good fits.

    Parameters
    ----------
    results : List[FitAttempt]
        All fit attempts.
    min_r_squared : float
        Minimum acceptable R² value (primary gate).
    rmse_threshold_factor : float, optional
        If set, additionally keep only fits with RMSE within this multiple
        of the best valid fit's RMSE. ``None`` disables the trim.

    Returns
    -------
    List[FitAttempt]
        Fit attempts forming the valid pool.
    """
    valid = filter_by_r_squared(results, min_r_squared)
    if rmse_threshold_factor is not None:
        valid = filter_by_rmse(valid, rmse_threshold_factor)
    return valid


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
