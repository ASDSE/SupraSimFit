"""Ensemble collapse: turn a pool of valid fits into one reported result.

This module is the **single source of operation** for collapsing the
multi-start (or per-replica) pool of valid fits into the values the app
reports. It does three things, each in one place:

1. **Select the representative** — :func:`select_representative_index`
   picks the single real fit that drives the plotted curve and the
   reported value/RMSE/R² (default: highest R², which is identical to
   lowest RMSE on a fixed dataset).
2. **Collapse the pool** — :func:`collapse` bundles the per-parameter
   sample pool, the per-trial quality pool, and the representative index
   into an :class:`EnsembleResult`.
3. **Summarise the spread** — the :data:`ENSEMBLE_STATISTICS` registry
   defines each aggregation mode (central tendency + dispersion) once;
   :func:`central_spread` and :func:`summarize` read from it.

The module is pure ``numpy`` — it operates on arrays, not assays, so both
pipeline paths and the GUI reuse it. To experiment with a new aggregation
add one entry to :data:`ENSEMBLE_STATISTICS`; to change which fit is
reported edit :func:`select_representative_index`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

# ---------------------------------------------------------------------------
# Primitive per-parameter statistics — defined once, reused everywhere.
# ---------------------------------------------------------------------------


def _median(samples: np.ndarray) -> float:
    return float(np.median(samples))


def _mad(samples: np.ndarray) -> float:
    """Median absolute deviation — robust dispersion around the median."""
    med = np.median(samples)
    return float(np.median(np.abs(samples - med)))


def _mean(samples: np.ndarray) -> float:
    return float(np.mean(samples))


def _std(samples: np.ndarray) -> float:
    """Sample standard deviation; 0 for a single sample (no spread defined)."""
    return float(np.std(samples, ddof=1)) if samples.size > 1 else 0.0


@dataclass(frozen=True)
class EnsembleStatistic:
    """One named way to summarise a 1-D pool of per-parameter samples.

    Attributes
    ----------
    label : str
        Human-readable label (e.g. ``'Median ± MAD'``) — drives the GUI
        toggle option text.
    central : Callable[[np.ndarray], float]
        Central-tendency estimator (e.g. median or mean).
    spread : Callable[[np.ndarray], float]
        Dispersion estimator (e.g. MAD or standard deviation).
    """

    label: str
    central: Callable[[np.ndarray], float]
    spread: Callable[[np.ndarray], float]


#: The extension point — add a key here to offer a new aggregation mode
#: across the pipeline, the table, the annotation, and the export.
ENSEMBLE_STATISTICS: dict[str, EnsembleStatistic] = {
    'median': EnsembleStatistic('Median ± MAD', _median, _mad),
    'mean': EnsembleStatistic('Mean ± STDEV', _mean, _std),
}

#: Default reported aggregation (robust).
DEFAULT_STATISTICS_MODE = 'median'


@dataclass
class EnsembleResult:
    """Mode-independent structural collapse of a valid-fit pool.

    Attributes
    ----------
    representative_index : int
        Index (into every ``parameter_samples`` / ``quality_samples``
        array) of the representative fit — the real fit that drives the
        curve and the reported value/RMSE/R².
    parameter_samples : dict[str, np.ndarray]
        One flat array per parameter key holding every valid trial's
        value, aligned by index.
    quality_samples : dict[str, np.ndarray]
        ``{'rmse': ..., 'r_squared': ...}`` — per-trial fit quality,
        aligned to ``parameter_samples`` by index.
    """

    representative_index: int
    parameter_samples: dict[str, np.ndarray]
    quality_samples: dict[str, np.ndarray]

    @property
    def representative_params(self) -> np.ndarray:
        """Representative parameter vector, ordered as ``parameter_samples``."""
        i = self.representative_index
        return np.array([arr[i] for arr in self.parameter_samples.values()], dtype=float)


def select_representative_index(quality: dict[str, np.ndarray]) -> int:
    """Index of the representative fit — the one place this criterion lives.

    Selects the highest R², which is identical to the lowest RMSE on a
    fixed dataset (``R² = 1 − SS_res/SS_tot``, ``RMSE = √(SS_res/n)`` are
    both monotone in ``SS_res``). R² is the more intuitive label.

    Parameters
    ----------
    quality : dict[str, np.ndarray]
        Must contain ``'r_squared'`` and ``'rmse'``, one value per valid
        trial (RMSE breaks R² ties).

    Returns
    -------
    int
        Index of the representative trial.
    """
    # Highest R², ties broken by lowest RMSE. On a fixed dataset R² and RMSE
    # are monotone (argmax R² == argmin RMSE); the tiebreak only matters when
    # R² collapses (e.g. constant y → ss_tot == 0 → every R² == 0), where RMSE
    # still identifies the genuinely best fit.
    r2 = np.asarray(quality['r_squared'], dtype=float)
    rmse = np.asarray(quality['rmse'], dtype=float)
    return int(np.lexsort((rmse, -r2))[0])


def collapse(
    param_matrix: np.ndarray,
    rmse: np.ndarray,
    r_squared: np.ndarray,
    parameter_keys: list[str],
) -> EnsembleResult:
    """Bundle a valid-fit pool into an :class:`EnsembleResult`.

    Parameters
    ----------
    param_matrix : np.ndarray
        ``(n_valid, n_params)`` array of valid-trial parameter vectors.
    rmse, r_squared : np.ndarray
        ``(n_valid,)`` per-trial quality, aligned to ``param_matrix`` rows.
    parameter_keys : list[str]
        Parameter names, ordered to match ``param_matrix`` columns.

    Returns
    -------
    EnsembleResult
        Pool, quality, and representative index.
    """
    param_matrix = np.asarray(param_matrix, dtype=float)
    quality = {
        'rmse': np.asarray(rmse, dtype=float),
        'r_squared': np.asarray(r_squared, dtype=float),
    }
    parameter_samples = {key: param_matrix[:, i].copy() for i, key in enumerate(parameter_keys)}
    return EnsembleResult(
        representative_index=select_representative_index(quality),
        parameter_samples=parameter_samples,
        quality_samples=quality,
    )


def central_spread(samples: np.ndarray, mode: str) -> tuple[float, float]:
    """Return ``(central, spread)`` for *samples* under aggregation *mode*.

    Parameters
    ----------
    samples : np.ndarray
        One parameter's pool of valid-trial values.
    mode : str
        A key of :data:`ENSEMBLE_STATISTICS` (e.g. ``'median'`` or ``'mean'``).
    """
    stat = ENSEMBLE_STATISTICS[mode]
    samples = np.asarray(samples, dtype=float)
    return stat.central(samples), stat.spread(samples)


def summarize(parameter_samples: dict[str, np.ndarray]) -> dict[str, dict[str, float]]:
    """Per-parameter descriptive statistics for the Fitted Parameters table.

    Returns ``{param_key: {'median', 'mad', 'mean', 'std'}}``, all drawn
    from the :data:`ENSEMBLE_STATISTICS` primitives so the table and the
    reported ± never diverge.
    """
    median = ENSEMBLE_STATISTICS['median']
    mean = ENSEMBLE_STATISTICS['mean']
    out: dict[str, dict[str, float]] = {}
    for key, raw in parameter_samples.items():
        samples = np.asarray(raw, dtype=float)
        out[key] = {
            'median': median.central(samples),
            'mad': median.spread(samples),
            'mean': mean.central(samples),
            'std': mean.spread(samples),
        }
    return out
