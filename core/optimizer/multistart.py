"""Multi-start optimization for nonlinear fitting.

This module provides a robust multi-start L-BFGS-B optimizer for fitting
binding assay models. The multi-start approach helps avoid local minima
by running the optimizer from multiple random initial points.
"""

from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import numpy as np
from scipy.optimize import minimize


@dataclass
class FitAttempt:
    """Result from a single optimization attempt.

    Attributes
    ----------
    params : np.ndarray
        Fitted parameter values.
    cost : float
        Final cost function value (sum of squared residuals).
    rmse : float
        Root mean squared error.
    r_squared : float
        Coefficient of determination (R²).
    success : bool
        Whether the optimizer converged.
    """

    params: np.ndarray
    cost: float
    rmse: float
    r_squared: float
    success: bool


def generate_initial_guesses(
    n_trials: int,
    bounds: List[Tuple[float, float]],
    log_scale_params: Optional[List[int]] = None,
) -> List[np.ndarray]:
    """Generate random initial parameter guesses within bounds.

    Parameters
    ----------
    n_trials : int
        Number of initial guesses to generate.
    bounds : List[Tuple[float, float]]
        (lower, upper) bounds for each parameter.
    log_scale_params : List[int], optional
        Indices of parameters that should be sampled in log space.
        This is useful for parameters like Ka that span many orders of magnitude.

    Returns
    -------
    List[np.ndarray]
        List of initial parameter arrays.
    """
    if log_scale_params is None:
        log_scale_params = []

    initial_guesses = []
    for _ in range(n_trials):
        guess = np.empty(len(bounds))
        for i, (lower, upper) in enumerate(bounds):
            if i in log_scale_params and lower > 0 and upper > 0:
                # Sample in log space for parameters spanning orders of magnitude
                log_lower = np.log10(lower)
                log_upper = np.log10(upper)
                guess[i] = 10 ** np.random.uniform(log_lower, log_upper)
            else:
                guess[i] = np.random.uniform(lower, upper)
        initial_guesses.append(guess)

    return initial_guesses


def multistart_minimize(
    objective: Callable[[np.ndarray], float],
    bounds: List[Tuple[float, float]],
    n_trials: int = 100,
    initial_guesses: Optional[List[np.ndarray]] = None,
    log_scale_params: Optional[List[int]] = None,
    compute_metrics: Optional[Callable[[np.ndarray], Tuple[float, float]]] = None,
) -> List[FitAttempt]:
    """Run L-BFGS-B optimizer from multiple starting points.

    Parameters
    ----------
    objective : Callable[[np.ndarray], float]
        Objective function to minimize. Should return sum of squared residuals.
    bounds : List[Tuple[float, float]]
        (lower, upper) bounds for each parameter.
    n_trials : int
        Number of optimization runs.
    initial_guesses : List[np.ndarray], optional
        Pre-computed initial guesses. If None, generated randomly.
    log_scale_params : List[int], optional
        Indices of parameters to sample in log space for random initialization.
    compute_metrics : Callable, optional
        Function that takes params and returns (rmse, r_squared).
        If None, RMSE is computed from cost, R² is set to NaN.

    Returns
    -------
    List[FitAttempt]
        Results from all optimization attempts, sorted by cost (ascending).
    """
    if initial_guesses is None:
        initial_guesses = generate_initial_guesses(n_trials, bounds, log_scale_params)

    results = []
    for guess in initial_guesses:
        try:
            result = minimize(
                objective,
                guess,
                method='L-BFGS-B',
                bounds=bounds,
            )

            if compute_metrics is not None:
                rmse, r_squared = compute_metrics(result.x)
            else:
                # Approximate RMSE from cost if n_points not available
                rmse = np.sqrt(result.fun)
                r_squared = np.nan

            results.append(
                FitAttempt(
                    params=result.x,
                    cost=result.fun,
                    rmse=rmse,
                    r_squared=r_squared,
                    success=result.success,
                )
            )
        except Exception:
            # Skip failed optimizations
            continue

    # Sort by cost (best first)
    results.sort(key=lambda x: x.cost)
    return results


def fit_with_multistart(
    objective: Callable[[np.ndarray], float],
    bounds: List[Tuple[float, float]],
    n_trials: int = 100,
    log_scale_params: Optional[List[int]] = None,
    compute_metrics: Optional[Callable[[np.ndarray], Tuple[float, float]]] = None,
) -> Tuple[Optional[FitAttempt], List[FitAttempt]]:
    """Convenience function for multi-start fitting with best result.

    Parameters
    ----------
    objective : Callable[[np.ndarray], float]
        Objective function to minimize.
    bounds : List[Tuple[float, float]]
        Parameter bounds.
    n_trials : int
        Number of optimization runs.
    log_scale_params : List[int], optional
        Parameters to sample in log space.
    compute_metrics : Callable, optional
        Function to compute (rmse, r_squared) from params.

    Returns
    -------
    Tuple[Optional[FitAttempt], List[FitAttempt]]
        (best_result, all_results). best_result is None if all attempts failed.
    """
    all_results = multistart_minimize(
        objective=objective,
        bounds=bounds,
        n_trials=n_trials,
        log_scale_params=log_scale_params,
        compute_metrics=compute_metrics,
    )

    best = all_results[0] if all_results else None
    return best, all_results
