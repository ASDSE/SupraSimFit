"""Optimization utilities for fitting binding assay models."""

from core.optimizer.ensemble import (
    DEFAULT_STATISTICS_MODE,
    ENSEMBLE_STATISTICS,
    EnsembleResult,
    EnsembleStatistic,
    central_spread,
    collapse,
    select_representative_index,
    summarize,
)
from core.optimizer.filters import (
    calculate_fit_metrics,
    filter_by_r_squared,
    filter_by_rmse,
    select_valid_fits,
)
from core.optimizer.linear_fit import linear_regression
from core.optimizer.multistart import FitAttempt, generate_initial_guesses, multistart_minimize

__all__ = [
    # multistart.py
    'FitAttempt',
    'generate_initial_guesses',
    'multistart_minimize',
    # filters.py
    'filter_by_rmse',
    'filter_by_r_squared',
    'select_valid_fits',
    'calculate_fit_metrics',
    # ensemble.py
    'ENSEMBLE_STATISTICS',
    'DEFAULT_STATISTICS_MODE',
    'EnsembleStatistic',
    'EnsembleResult',
    'collapse',
    'select_representative_index',
    'central_spread',
    'summarize',
    # linear_fit.py
    'linear_regression',
]
