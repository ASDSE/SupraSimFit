"""Summary statistics of a set of values, in a parameter's own scale and in log₁₀.

:func:`summarize_parameters` reports what the replicates of a per-replicate fit
give one parameter through :func:`describe`, and a binding constant's log₁₀ twin
row through :func:`describe_log10`. The module is pure ``numpy`` — it operates
on arrays, not assays, so the pipeline and the GUI reuse it. To report a new
statistic add a key to :func:`describe`.
"""

from __future__ import annotations

import numpy as np


def describe(samples: np.ndarray) -> dict[str, float]:
    """Full summary of a 1-D set of values: center, spread, and range.

    Returns ``{'median', 'mad', 'mean', 'std', 'p16', 'p84', 'min', 'max'}``
    — the median/MAD and mean/SD pairs, the central-68% interval (16th and
    84th percentiles, the distribution-free analog of ±1 SD), and the observed
    range, all computed directly from *samples*. The sample standard deviation
    (``ddof=1``) is 0 for a single value, which has no spread.
    """
    s = np.asarray(samples, dtype=float)
    median = float(np.median(s))
    p16, p84 = np.percentile(s, [16, 84])
    return {
        'median': median,
        # Median absolute deviation — dispersion around the median that a
        # single far-off value does not carry away.
        'mad': float(np.median(np.abs(s - median))),
        'mean': float(np.mean(s)),
        'std': float(np.std(s, ddof=1)) if s.size > 1 else 0.0,
        'p16': float(p16),
        'p84': float(p84),
        'min': float(np.min(s)),
        'max': float(np.max(s)),
    }


def describe_log10(samples: np.ndarray) -> dict[str, float]:
    """Summary of ``log10(samples)`` — transform FIRST, then aggregate.

    The statistics of ``log10(Ka)`` must be computed from the per-fit log10
    values: ``log10`` of a Ka spread statistic is meaningless (``log10(MAD_Ka)``
    is not a spread in log space) and ``log10(mean Ka)`` is Jensen-biased.
    Requires strictly positive samples (Ka > 0) — raises rather than emit a
    silent ``-inf`` / ``nan``.
    """
    s = np.asarray(samples, dtype=float)
    if s.size == 0 or float(np.min(s)) <= 0.0:
        raise ValueError('describe_log10 requires strictly positive samples (Ka > 0).')
    return describe(np.log10(s))
