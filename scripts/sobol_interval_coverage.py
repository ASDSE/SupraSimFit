#!/usr/bin/env python3
"""Calibration of the Sobol' index intervals used by the Ka sensitivity analysis.

The Ka Sensitivity tab reports first- and total-order Sobol' indices with a 95 %
interval from a delete-one-block jackknife over the independently scrambled
blocks of its design. This script measures what that interval delivers, on two
functions whose indices are known in closed form: the Ishigami function and a
six-input g-function.

Two tables
----------
Coverage
    Over many independent designs: how often the nominal 95 % interval holds
    the true index, the estimator's bias against its own scatter, and the mean
    half-width against ``t * SD``, which is the half-width an interval built
    from the true scatter would have.
Price of blocking
    The root-mean-square error of each index when one budget is split into
    independently scrambled blocks, against one undivided scramble of the same
    size. Blocking is what makes the jackknife possible; this is what it costs.

Both tables call the application's own :mod:`core.pipeline.sensitivity`
functions, so the numbers describe the estimators the app ships.

Run from the repository root::

    uv run scripts/sobol_interval_coverage.py                                     # a few minutes
    uv run scripts/sobol_interval_coverage.py --designs 1000 --n-base 1024 4096   # the tables in scripts/README.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from scipy.stats import t as student_t

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.pipeline.sensitivity import (  # noqa: E402  (path set up above)
    _SOBOL_BLOCKS,
    sobol_design,
    sobol_indices_from_outputs,
    sobol_indices_with_ci,
)

#: Coefficients of the g-function: two influential inputs, two weak ones and
#: two all but inert, so the tables span indices from 0.59 down to 1e-4.
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


def evaluate(f, a_points: np.ndarray, b_points: np.ndarray) -> tuple[np.ndarray, np.ndarray, list[np.ndarray]]:
    """Outputs ``(f_A, f_B, [f_AB_i])`` of *f* on one design."""
    f_ab = []
    for i in range(a_points.shape[-1]):
        mixed = a_points.copy()
        mixed[..., i] = b_points[..., i]
        f_ab.append(f(mixed))
    return f(a_points), f(b_points), f_ab


def wilson(hits: float, n: int, z: float = 1.959964) -> tuple[float, float]:
    """Wilson 95 % interval for a proportion, which stays inside 0 … 1 near the ends."""
    p = hits / n
    denominator = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denominator
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denominator
    return centre - half, centre + half


def index_labels(k: int) -> list[str]:
    """Row labels ``S1_1 … ST_k`` for *k* inputs, in the order the estimators return."""
    return [f'S1_{i + 1}' for i in range(k)] + [f'ST_{i + 1}' for i in range(k)]


def coverage_table(name, f, k, truth, n_designs: int, n_base: int, n_blocks: int, seed: int) -> None:
    """Print the coverage of the jackknife interval over *n_designs* independent designs."""
    true = np.concatenate(truth)
    estimates, low, high = [], [], []
    for offset in range(n_designs):
        a, b = sobol_design(n_base, k, n_blocks, seed=seed + offset)
        f_a, f_b, f_ab = evaluate(f, a, b)
        s1, s1_ci, st, st_ci = sobol_indices_with_ci(f_a, f_b, f_ab, n_blocks)
        estimates.append(np.concatenate([s1, st]))
        low.append(np.concatenate([s1_ci[:, 0], st_ci[:, 0]]))
        high.append(np.concatenate([s1_ci[:, 1], st_ci[:, 1]]))
    estimates, low, high = map(np.array, (estimates, low, high))
    t_quantile = student_t.ppf(0.975, n_blocks - 1)

    print(f'\n=== {name}: {n_designs} designs, N={n_base}, {n_blocks} blocks, t={t_quantile:.3f} ===')
    print(
        f'{"index":6s} {"truth":>8s} {"mean est":>9s} {"bias":>8s} {"emp SD":>8s} {"bias/SD":>8s} '
        f'{"mean hw":>8s} {"hw/(t*SD)":>9s} {"cover":>6s} {"wilson 95%":>16s}'
    )
    for i, label in enumerate(index_labels(k)):
        covered = np.mean((low[:, i] <= true[i]) & (true[i] <= high[:, i]))
        w_low, w_high = wilson(covered * n_designs, n_designs)
        sd = estimates[:, i].std(ddof=1)
        bias = estimates[:, i].mean() - true[i]
        half_width = ((high[:, i] - low[:, i]) / 2).mean()
        print(
            f'{label:6s} {true[i]:8.4f} {estimates[:, i].mean():9.4f} {bias:8.4f} {sd:8.4f} '
            f'{bias / sd:8.2f} {half_width:8.4f} {half_width / (t_quantile * sd):9.2f} '
            f'{covered:6.3f} [{w_low:.3f}, {w_high:.3f}]'
        )


def blocking_table(name, f, k, truth, n_designs: int, seed: int, rows: list[tuple[int, int]]) -> None:
    """Print the RMSE of the indices for each ``(N, blocks)`` split, against one scramble of N = 1024."""
    true = np.concatenate(truth)

    def rmse(n_base: int, n_blocks: int) -> np.ndarray:
        errors = []
        for offset in range(n_designs):
            a, b = sobol_design(n_base, k, n_blocks, seed=seed + offset)
            f_a, f_b, f_ab = evaluate(f, a, b)
            errors.append(np.concatenate(sobol_indices_from_outputs(f_a, f_b, f_ab)) - true)
        return np.sqrt((np.array(errors) ** 2).mean(axis=0))

    print(f'\n=== {name}: RMSE per index over {n_designs} designs, relative to 1 block at N=1024 ===')
    print(f'{"design":22s} {"  ".join(f"{label:>7s}" for label in index_labels(k))}')
    reference = None
    for n_base, n_blocks in rows:
        value = rmse(n_base, n_blocks)
        if reference is None:
            reference = value
        ratio = value / reference
        tag = f'{n_blocks} x {n_base // n_blocks} (N={n_base})'
        print(f'{tag:22s} {"  ".join(f"{r:7.2f}" for r in ratio)}')
    print('1.00 = the RMSE of one undivided scramble at N=1024; above 1.00 is the price of blocking.')


def main() -> None:
    """Run both tables for both test functions."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--designs', type=int, default=200, help='independent designs per table (default 200)')
    parser.add_argument('--seed', type=int, default=0, help='first design seed; designs use consecutive seeds')
    parser.add_argument(
        '--n-base',
        type=int,
        default=[1024],
        nargs='+',
        help='base sample size(s) of the coverage tables (default 1024)',
    )
    args = parser.parse_args()

    functions = [
        ('Ishigami', ishigami, 3, ishigami_truth()),
        (f'g-function a={G_COEFFICIENTS.tolist()}', gfunction, 6, gfunction_truth()),
    ]
    for name, f, k, truth in functions:
        for n_base in args.n_base:
            coverage_table(name, f, k, truth, args.designs, n_base, _SOBOL_BLOCKS, args.seed)
    for name, f, k, truth in functions:
        rows = [(1024, 1), (1024, _SOBOL_BLOCKS), (1024, 32), (128, 1), (4096, 1), (4096, _SOBOL_BLOCKS)]
        blocking_table(name, f, k, truth, args.designs, args.seed, rows)


if __name__ == '__main__':
    main()
