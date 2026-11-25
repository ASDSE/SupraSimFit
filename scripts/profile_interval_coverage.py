#!/usr/bin/env python3
"""Coverage of the 95 % profile-likelihood interval for Ka.

The Identifiability tab reports the Ka values whose residual sum of squares
stays within ``SSR_min * (1 + F(0.95; 1, n - p) / (n - p))``. That threshold is
derived for scatter that is independent from point to point and of equal size
across the titration. This script generates synthetic IDA data under four kinds
of scatter, fits each set with the application's own
:func:`core.pipeline.profile.fit_profile`, and counts how often the interval
holds the Ka the data were generated from.

Scenarios
---------
homoscedastic
    One replicate, Gaussian noise of constant size (2 % of the largest signal).
    The assumption behind the F test, met.
proportional
    One replicate, Gaussian noise of 2 % of each point's own signal. The
    assumption broken mildly.
replicates
    Four replicates, each with independent constant-size noise.
shared-misfit
    Four replicates with the same noise plus a smooth systematic deviation of
    2 % of the largest signal, common to all four — a model that misses the
    data the same way in every replicate.

The two replicate scenarios are also measured with the replicates' points
pooled as if they were independent observations, the alternative to the
averaging the app does, which is what the last column reports.

Run from the repository root::

    uv run scripts/profile_interval_coverage.py                 # a few minutes
    uv run scripts/profile_interval_coverage.py --designs 200   # the table in scripts/README.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import brentq, lsq_linear, minimize_scalar
from scipy.stats import beta
from scipy.stats import f as f_dist

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.assays.ida import IDAAssay  # noqa: E402  (path set up above)
from core.data_processing.measurement_set import MeasurementSet  # noqa: E402
from core.models.equilibrium import ida_signal  # noqa: E402
from core.pipeline import profile as profile_module  # noqa: E402
from core.pipeline.fit_pipeline import FitConfig, _resolve_bounds  # noqa: E402
from core.pipeline.profile import fit_profile  # noqa: E402
from core.units import Q_  # noqa: E402

#: Ground truth of the synthetic IDA titration, matching ``IDA_TRUE`` in
#: ``tests/conftest.py`` so the scripts and the test suite describe one system.
TRUTH = {
    'Ka_guest': 2e6,
    'I0': 0.0,
    'I_dye_free': 5e7,
    'I_dye_bound': 3e8,
    'Ka_dye': 5e5,
    'h0': 10e-6,
    'd0': 5e-6,
}

#: Conditions as the fit receives them: everything but the fitted Ka_guest.
CONDITIONS = {
    'Ka_dye': Q_(TRUTH['Ka_dye'], '1/M'),
    'h0': Q_(TRUTH['h0'], 'M'),
    'd0': Q_(TRUTH['d0'], 'M'),
}

#: Ka bounds in force, seven decades around the true value.
KA_BOUNDS = {'Ka_guest': (Q_(1e3, '1/M'), Q_(1e10, '1/M'))}

#: Noise and misfit size, as a fraction of the largest clean signal.
NOISE_FRACTION = 0.02

N_POINTS = 12
N_REPLICATES = 4


def clean_data() -> tuple[np.ndarray, np.ndarray]:
    """Guest concentrations and the noise-free IDA signal at :data:`TRUTH`."""
    g0 = np.linspace(0, 50e-6, N_POINTS)
    y = ida_signal(
        I0=TRUTH['I0'],
        Ka_guest=TRUTH['Ka_guest'],
        I_dye_free=TRUTH['I_dye_free'],
        I_dye_bound=TRUTH['I_dye_bound'],
        Ka_dye=TRUTH['Ka_dye'],
        h0=TRUTH['h0'],
        d0=TRUTH['d0'],
        g0_values=g0,
    )
    return g0, y


def clopper_pearson(hits: int, n: int) -> tuple[float, float]:
    """Exact 95 % interval for a coverage proportion."""
    low = beta.ppf(0.025, hits, n - hits + 1) if hits > 0 else 0.0
    high = beta.ppf(0.975, hits + 1, n - hits) if hits < n else 1.0
    return low, high


def make_signals(scenario: str, x: np.ndarray, y: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """One dataset for *scenario*, shaped ``(replicates, points)``."""
    scale = NOISE_FRACTION * np.abs(y).max()
    if scenario == 'proportional':
        return (y + rng.normal(0, NOISE_FRACTION * np.abs(y), y.size))[np.newaxis, :]
    if scenario == 'homoscedastic':
        return (y + rng.normal(0, scale, y.size))[np.newaxis, :]
    misfit = scale * np.sin(np.pi * x / x.max()) if scenario == 'shared-misfit' else 0.0
    return np.vstack([y + misfit + rng.normal(0, scale, y.size) for _ in range(N_REPLICATES)])


def pooled_interval(x: np.ndarray, signals: np.ndarray) -> tuple[float, float]:
    """95 % F-test interval that treats every replicate's points as independent.

    One coefficient set is fitted to all ``m * n`` points at each Ka, and the
    threshold uses ``n = m * n_points``. The app averages the replicates
    instead; this is the alternative the averaging is measured against.
    """
    ms = MeasurementSet(
        concentrations=x,
        signals=signals,
        replica_ids=tuple(str(i) for i in range(signals.shape[0])),
    )
    assay = ms.to_assay(IDAAssay, conditions=CONDITIONS, use_average=True)
    ka_key, coef_keys = profile_module._split_keys(assay)
    float_bounds = profile_module._float_bounds(assay, _resolve_bounds(assay, KA_BOUNDS))
    lb, ub = profile_module._coefficient_bounds(float_bounds, coef_keys)
    stacked = signals.ravel()
    m = signals.shape[0]

    def ssr(ka: float) -> float:
        design = np.tile(profile_module._design(assay, ka_key, coef_keys, ka), (m, 1))
        scale = np.linalg.norm(design, axis=0)
        solution = lsq_linear(design / scale, stacked, bounds=(lb * scale, ub * scale), method='bvls')
        coefficients = np.clip(solution.x / scale, lb, ub)
        return float(np.sum((design @ coefficients - stacked) ** 2))

    grid = np.geomspace(*float_bounds[ka_key], 141)
    on_grid = np.array([ssr(ka) for ka in grid])
    i = int(np.argmin(on_grid))
    refined = minimize_scalar(
        lambda t: ssr(10**t),
        bounds=(np.log10(grid[max(i - 1, 0)]), np.log10(grid[min(i + 1, grid.size - 1)])),
        method='bounded',
    )
    best_ssr = min(refined.fun, on_grid[i])
    best_ka = 10**refined.x if refined.fun < on_grid[i] else grid[i]
    n, p = m * signals.shape[1], 3
    threshold = best_ssr * (1 + f_dist.ppf(0.95, 1, n - p) / (n - p))

    inside = np.append(grid[on_grid <= threshold], best_ka)
    low_in, high_in = float(inside.min()), float(inside.max())
    below, above = grid[grid < low_in], grid[grid > high_in]

    def edge(outside: float, within: float) -> float:
        return float(10 ** brentq(lambda t: ssr(10**t) - threshold, np.log10(outside), np.log10(within)))

    low = edge(below[-1], low_in) if below.size else float(grid[0])
    high = edge(above[0], high_in) if above.size else float(grid[-1])
    return low, high


def run_scenario(scenario: str, n_designs: int, seed: int) -> None:
    """Fit *n_designs* synthetic datasets and print one row of coverage."""
    x, y = clean_data()
    true_ka = TRUTH['Ka_guest']
    # per_replica=False keeps the run to the averaged curve the interval comes
    # from; the per-replicate curves are drawn in the tab but do not enter it.
    config = FitConfig(per_replica=False, custom_bounds=KA_BOUNDS)
    pooled = scenario in ('replicates', 'shared-misfit')

    hits, widths = 0, []
    pooled_hits, pooled_widths = 0, []
    for offset in range(n_designs):
        signals = make_signals(scenario, x, y, np.random.default_rng(seed + offset))
        ms = MeasurementSet(
            concentrations=x,
            signals=signals,
            replica_ids=tuple(f'r{i}' for i in range(signals.shape[0])),
        )
        result = fit_profile(ms, IDAAssay, CONDITIONS, config)
        hits += result.ci[0] <= true_ka <= result.ci[1]
        widths.append(np.log10(result.ci[1] / result.ci[0]))
        if pooled:
            low, high = pooled_interval(x, signals)
            pooled_hits += low <= true_ka <= high
            pooled_widths.append(np.log10(high / low))

    low, high = clopper_pearson(hits, n_designs)
    row = f'{scenario:15s} {hits / n_designs:8.3f}  [{low:.3f}, {high:.3f}]  {np.median(widths):13.3f}'
    if pooled:
        p_low, p_high = clopper_pearson(pooled_hits, n_designs)
        row += f'  {pooled_hits / n_designs:8.3f}  [{p_low:.3f}, {p_high:.3f}]  {np.median(pooled_widths):13.3f}'
    print(row, flush=True)


def main() -> None:
    """Run every scenario and print the coverage table."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--designs', type=int, default=50, help='synthetic datasets per scenario (default 50)')
    parser.add_argument('--seed', type=int, default=1000, help='first dataset seed; datasets use consecutive seeds')
    args = parser.parse_args()

    print(
        f'Nominal 95 % interval, {args.designs} datasets per scenario, true Ka '
        f'{TRUTH["Ka_guest"]:.3g} 1/M, {N_POINTS} titration points.\n'
        'Width is the median interval width in decades of Ka. "pooled" treats every replicate point '
        'as independent\ninstead of averaging the replicates.'
    )
    print(
        f'\n{"scenario":15s} {"coverage":>8s}  {"95% exact":>16s}  {"width (dec)":>13s}'
        f'  {"pooled":>8s}  {"95% exact":>16s}  {"width (dec)":>13s}'
    )
    for scenario in ('homoscedastic', 'proportional', 'replicates', 'shared-misfit'):
        run_scenario(scenario, args.designs, args.seed)


if __name__ == '__main__':
    main()
