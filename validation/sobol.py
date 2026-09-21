"""What the Sobol' index intervals of the Ka sensitivity analysis deliver.

The Ka Sensitivity tab reports first- and total-order Sobol' indices with a
95 % interval from a delete-one-block jackknife over the independently
scrambled blocks of its design. Two functions whose indices are known in closed
form — the Ishigami function and a six-input g-function — say how often that
interval holds the true index, and what splitting one budget into blocks costs
in accuracy. Both rows call the application's own estimators, so they describe
what ships.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from core.pipeline.sensitivity import (
    _SOBOL_BLOCKS,
    sobol_design,
    sobol_indices_from_outputs,
    sobol_indices_with_ci,
)

__all__ = ['SobolCase', 'blocking_row', 'coverage_row', 'index_labels']

#: Coefficients of the g-function: two influential inputs, two weak ones and
#: two all but inert, so the rows span indices from 0.59 down to 1e-4.
G_COEFFICIENTS = np.array([0.0, 0.5, 3.0, 9.0, 99.0, 99.0])


def ishigami(u: np.ndarray, a: float = 7.0, b: float = 0.1) -> np.ndarray:
    """Ishigami function on unit-cube samples *u* of shape ``(..., 3)``."""
    x = -np.pi + 2 * np.pi * np.asarray(u)
    return np.sin(x[..., 0]) + a * np.sin(x[..., 1]) ** 2 + b * x[..., 2] ** 4 * np.sin(x[..., 0])


def ishigami_truth(a: float = 7.0, b: float = 0.1) -> tuple[np.ndarray, np.ndarray]:
    """Analytic ``(S1, S_total)`` of :func:`ishigami`."""
    v1 = 0.5 * (1 + b * np.pi**4 / 5) ** 2
    v2 = a**2 / 8
    v13 = b**2 * np.pi**8 * (1 / 18 - 1 / 50)
    v = v1 + v2 + v13
    return np.array([v1, v2, 0.0]) / v, np.array([v1 + v13, v2, v13]) / v


def gfunction(u: np.ndarray, a: np.ndarray = G_COEFFICIENTS) -> np.ndarray:
    """Sobol' g-function on unit-cube samples *u* of shape ``(..., len(a))``."""
    return np.prod((np.abs(4 * np.asarray(u) - 2) + a) / (1 + a), axis=-1)


def gfunction_truth(a: np.ndarray = G_COEFFICIENTS) -> tuple[np.ndarray, np.ndarray]:
    """Analytic ``(S1, S_total)`` of :func:`gfunction`."""
    vi = 1 / (3 * (1 + a) ** 2)
    v = np.prod(1 + vi) - 1
    st = np.array([vi[i] * np.prod(1 + np.delete(vi, i)) for i in range(len(a))])
    return vi / v, st / v


#: The test functions, their input count and their known indices.
FUNCTIONS: dict[str, tuple[Callable[[np.ndarray], np.ndarray], int, Callable[[], tuple[np.ndarray, np.ndarray]]]] = {
    'ishigami': (ishigami, 3, ishigami_truth),
    'gfunction': (gfunction, 6, gfunction_truth),
}


@dataclass(frozen=True)
class SobolCase:
    """One test function measured at one design size and block count.

    Attributes
    ----------
    function : str
        Key into :data:`FUNCTIONS`.
    n_base : int
        Base sample size of the design; the analysis offers 1024 upwards.
    n_blocks : int
        Independently scrambled blocks the design is split into. The
        application uses :data:`~core.pipeline.sensitivity._SOBOL_BLOCKS`; one
        block is the undivided scramble the blocking price is measured against.
    """

    function: str
    n_base: int
    n_blocks: int = _SOBOL_BLOCKS

    @property
    def id(self) -> str:
        """Stable key of this case — the key its rows are stored under."""
        return f'{self.function},N={self.n_base},blocks={self.n_blocks}'


def index_labels(k: int) -> list[str]:
    """Row labels ``S1_1 … ST_k`` for *k* inputs, in the order the estimators return."""
    return [f'S1_{i + 1}' for i in range(k)] + [f'ST_{i + 1}' for i in range(k)]


def _outputs(case: SobolCase, seed: int) -> tuple[np.ndarray, np.ndarray, list[np.ndarray], np.ndarray, int]:
    """One design of *case* at *seed*: the outputs of A, B and every mixed matrix, with the truth."""
    f, k, truth = FUNCTIONS[case.function]
    a_points, b_points = sobol_design(case.n_base, k, case.n_blocks, seed=seed)
    f_ab = []
    for i in range(k):
        mixed = a_points.copy()
        mixed[:, i] = b_points[:, i]
        f_ab.append(f(mixed))
    return f(a_points), f(b_points), f_ab, np.concatenate(truth()), k


def coverage_row(case: SobolCase, seed: int) -> dict[str, Any]:
    """Whether the jackknife interval of each index holds the analytic truth, on one design.

    Returns
    -------
    dict
        ``cov`` per index label, with the estimate, the interval's half width
        and the error against the truth beside it.
    """
    f_a, f_b, f_ab, truth, k = _outputs(case, seed)
    s1, s1_ci, st, st_ci = sobol_indices_with_ci(f_a, f_b, f_ab, case.n_blocks)
    estimates = np.concatenate([s1, st])
    low = np.concatenate([s1_ci[:, 0], st_ci[:, 0]])
    high = np.concatenate([s1_ci[:, 1], st_ci[:, 1]])
    labels = index_labels(k)
    return {
        'cov': {label: bool(low[i] <= truth[i] <= high[i]) for i, label in enumerate(labels)},
        'halfwidth': {label: float((high[i] - low[i]) / 2) for i, label in enumerate(labels)},
        'err': {label: float(estimates[i] - truth[i]) for i, label in enumerate(labels)},
        'truth': {label: float(truth[i]) for i, label in enumerate(labels)},
        'refused': None,
        'error': None,
    }


def blocking_row(case: SobolCase, seed: int) -> dict[str, Any]:
    """The error of each index on one design, for the root-mean-square the blocking price is read from.

    Returns
    -------
    dict
        ``err`` per index label: the estimate minus the analytic truth.
    """
    f_a, f_b, f_ab, truth, k = _outputs(case, seed)
    estimates = np.concatenate(sobol_indices_from_outputs(f_a, f_b, f_ab))
    labels = index_labels(k)
    return {
        'err': {label: float(estimates[i] - truth[i]) for i, label in enumerate(labels)},
        'refused': None,
        'error': None,
    }


def coverage_cases() -> list[SobolCase]:
    """Both functions at the design sizes the analysis offers."""
    return [SobolCase(name, n_base) for name in FUNCTIONS for n_base in (1024, 4096)]


def blocking_cases() -> list[SobolCase]:
    """One budget split every way the price of blocking is read from."""
    return [
        SobolCase(name, n_base, blocks)
        for name in FUNCTIONS
        for n_base, blocks in ((1024, 1), (1024, _SOBOL_BLOCKS), (1024, 32), (4096, 1), (4096, _SOBOL_BLOCKS))
    ]
