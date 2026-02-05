"""Optimization utilities for fitting binding assay models."""

from core.optimizer.filters import aggregate_fits, calculate_fit_metrics, compute_mad, compute_median_params, filter_by_r_squared, filter_by_rmse, filter_fits
from core.optimizer.linear_fit import linear_regression
from core.optimizer.multistart import FitAttempt, fit_with_multistart, generate_initial_guesses, multistart_minimize

__all__ = [
    # multistart.py
    'FitAttempt',
    'generate_initial_guesses',
    'multistart_minimize',
    'fit_with_multistart',
    # filters.py
    'filter_by_rmse',
    'filter_by_r_squared',
    'filter_fits',
    'compute_median_params',
    'compute_mad',
    'aggregate_fits',
    'calculate_fit_metrics',
    # linear_fit.py
    'linear_regression',
]
