"""Fit quality measured against a signal."""

from typing import Tuple

import numpy as np


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
