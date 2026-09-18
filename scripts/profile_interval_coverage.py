#!/usr/bin/env python3
"""Coverage of the 95 % profile-likelihood intervals for Ka.

For every binding constant a fit reports the Ka values whose profiled residual
sum of squares stays within ``SSR_min (1 + F(0.95; 1, n - p) / (n - p))``, and
a model with two binding constants also reports the joint region within
``SSR_min (1 + 2 F(0.95; 2, n - p) / (n - p))``. Both thresholds are derived
for scatter that is independent from point to point and of equal size across
the titration. This script generates synthetic titrations of one assay under
four kinds of scatter, fits each with the application's own engine
(:class:`core.pipeline.varpro.Projection`, the calls a fit makes) and counts
how often each interval and the joint region hold the values the data were
generated from. It also counts how often an interval is open on a side, so
the data do not limit Ka there, and how often the best fit has a signal
parameter the data determine sitting on a bound, a case the F test's
derivation does not foresee: the offset is zero in every system here, on its
lower bound.

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
    2 % of the largest signal, common to all four: a model that misses the
    data the same way in every replicate.

The two replicate scenarios are also measured with the replicates' points
pooled as if they were independent observations, the alternative to the
averaging the app does. That interval comes from a profile written in this
script, independent of the engine.

Assay and regime
----------------
``--assay`` chooses the model. ``--regime`` is Ka·c, the product of the model's
first binding constant and the fixed concentration of the titration (the host
for GDA, IDA, HG2 and H2G; the fixed partner for DBA): the number that places
a titration between weak binding, where the isotherm bends little over the
titration, and stoichiometric binding, where it breaks at equivalence. It
moves only the true binding constants (a second one keeps its ratio to the
first); the titrant range, the noise and the other conditions stay those of
the assay's system in :data:`SYSTEMS`. Without it the truth is the one the
test suite uses for that assay. Ka and signal-parameter bounds are the app's
defaults.

Run from the repository root::

    uv run scripts/profile_interval_coverage.py --assay IDA                          # seconds on a few cores
    uv run scripts/profile_interval_coverage.py --assay HG2 --designs 200 --points 30  # a README table; 10 min on 16 cores
"""

from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Callable

import numpy as np
from scipy.optimize import brentq, lsq_linear, minimize_scalar
from scipy.stats import beta
from scipy.stats import f as f_dist

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.assays import DBAAssay, GDAAssay, H2GAssay, HG2Assay, IDAAssay  # noqa: E402  (path set up above)
from core.assays.base import BaseAssay  # noqa: E402
from core.assays.registry import ParamKind  # noqa: E402
from core.data_processing.measurement_set import MeasurementSet  # noqa: E402
from core.pipeline.varpro import LEVEL, Projection  # noqa: E402
from core.units import Q_  # noqa: E402


@dataclass(frozen=True)
class System:
    """One synthetic titration: the model, its truth and its design.

    Attributes
    ----------
    assay_cls : type[BaseAssay]
        The assay class the fit receives.
    truth : dict[str, float]
        Every model parameter in canonical units (1/M, au, au/M).
    conditions : dict[str, Any]
        Conditions as the fit receives them.
    titrant : tuple[float, float]
        First and last titrant concentration (M); the points are equally spaced.
    regime_conc : str
        The condition whose product with the first binding constant is the regime.
    """

    assay_cls: type[BaseAssay]
    truth: dict[str, float]
    conditions: dict[str, Any]
    titrant: tuple[float, float]
    regime_conc: str


_COMPETITIVE = {'I0': 0.0, 'I_dye_free': 5e7, 'I_dye_bound': 3e8}
_STEPWISE = {'I0': 0.0, 'I_G': 1e6, 'I_H': 0.0, 'I_HG': 1e7}

#: Ground truth and design per assay, matching the ``*_TRUE`` systems and data
#: makers of ``tests/conftest.py`` so this script and the test suite describe
#: the same titrations.
SYSTEMS: dict[str, System] = {
    'GDA': System(
        GDAAssay,
        {'Ka_guest': 1.5e6, **_COMPETITIVE},
        {'Ka_dye': Q_(5e5, '1/M'), 'h0': Q_(10e-6, 'M'), 'g0': Q_(20e-6, 'M')},
        (1e-7, 30e-6),
        'h0',
    ),
    'IDA': System(
        IDAAssay,
        {'Ka_guest': 2e6, **_COMPETITIVE},
        {'Ka_dye': Q_(5e5, '1/M'), 'h0': Q_(10e-6, 'M'), 'd0': Q_(5e-6, 'M')},
        (0.0, 50e-6),
        'h0',
    ),
    'DBA_HtoD': System(
        DBAAssay,
        {'Ka_dye': 5e5, **_COMPETITIVE},
        {'fixed_conc': Q_(10e-6, 'M'), 'mode': 'HtoD'},
        (1e-7, 50e-6),
        'fixed_conc',
    ),
    'DBA_DtoH': System(
        DBAAssay,
        {'Ka_dye': 5e5, **_COMPETITIVE},
        {'fixed_conc': Q_(10e-6, 'M'), 'mode': 'DtoH'},
        (1e-7, 50e-6),
        'fixed_conc',
    ),
    'HG2': System(
        HG2Assay, {'Ka_HG': 1e6, 'Ka_HG2': 2e5, **_STEPWISE, 'I_HG2': 5e6}, {'h0': Q_(3e-4, 'M')}, (0.0, 1.2e-3), 'h0'
    ),
    'H2G': System(
        H2GAssay, {'Ka_HG': 1e6, 'Ka_H2G': 2e5, **_STEPWISE, 'I_H2G': 5e6}, {'h0': Q_(3e-4, 'M')}, (0.0, 6e-4), 'h0'
    ),
}

SCENARIOS = ('homoscedastic', 'proportional', 'replicates', 'shared-misfit')

#: Noise and misfit size, as a fraction of the largest clean signal.
NOISE_FRACTION = 0.02

N_REPLICATES = 4

# Ka grid density of the reference profile, in points per decade: twice the
# engine's search density, so the reference shares none of its choices, and
# refined between neighbouring nodes so the best fit and the edges are exact.
# On one replicate the pooled interval is the app's interval; there the two
# agree to within 2e-8 decades at every edge of every assay's system (three
# datasets each, 12 points, 2 % noise).
_REFERENCE_PER_DECADE = 8

# Relative singular-value cut-off for the rank of the norm-scaled coefficient
# design, the same as the engine's: the columns a mass balance ties together
# carry relative singular values of 2e-17 to 2e-15, a direction the signal
# separates stays above 7e-7, and 1e-8 sits in the gap.
_RANK_RTOL = 1e-8


def make_assay(system: System, x: np.ndarray, y: np.ndarray) -> BaseAssay:
    """The assay on titrant grid *x* with signal *y*."""
    return system.assay_cls(x_data=Q_(x, 'M'), y_data=Q_(y, 'au'), **system.conditions)


def ka_keys_of(assay: BaseAssay) -> list[str]:
    """The binding-constant keys of *assay*, in parameter order."""
    kinds = assay.registry_metadata.param_kinds
    return [k for k in assay.parameter_keys if kinds[k] is ParamKind.BINDING_CONSTANT]


def float_bounds(assay: BaseAssay) -> dict[str, tuple[float, float]]:
    """The app's default bounds of every parameter, in canonical units."""
    units = assay.registry_metadata.units
    return {
        k: (float(lo.to(units[k]).magnitude), float(hi.to(units[k]).magnitude))
        for k, (lo, hi) in assay.get_default_bounds().items()
    }


def regime_conc(system: System) -> float:
    """The fixed concentration (M) the regime refers to."""
    return float(system.conditions[system.regime_conc].to('M').magnitude)


def clean_data(system: System, n_points: int, regime: float | None) -> tuple[BaseAssay, dict[str, float]]:
    """The noise-free titration of *n_points* and the truth it was generated from.

    With a *regime* the binding constants are moved so that the first one
    times the fixed concentration equals it; without one they are the system's.
    """
    x = np.linspace(*system.titrant, n_points)
    assay = make_assay(system, x, np.zeros(n_points))
    truth = dict(system.truth)
    if regime is not None:
        keys = ka_keys_of(assay)
        factor = regime / (truth[keys[0]] * regime_conc(system))
        truth = {k: v * factor if k in keys else v for k, v in truth.items()}
    y = assay.forward_model(np.array([truth[k] for k in assay.parameter_keys])).magnitude
    return make_assay(system, x, y), truth


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


def _refine(ssr_fn: Callable[[float], float], grid: np.ndarray, ssr_grid: np.ndarray) -> tuple[float, float]:
    """Minimum of *ssr_fn* in log Ka between the neighbours of the best grid node, as ``(Ka, SSR)``."""
    i = int(np.argmin(ssr_grid))
    lo, hi = np.log10(grid[max(i - 1, 0)]), np.log10(grid[min(i + 1, grid.size - 1)])
    res = minimize_scalar(lambda t: ssr_fn(10.0**t), bounds=(lo, hi), method='bounded')
    return (float(10.0**res.x), float(res.fun)) if res.fun < ssr_grid[i] else (float(grid[i]), float(ssr_grid[i]))


def pooled_intervals(assay: BaseAssay, signals: np.ndarray) -> dict[str, tuple[float, float]]:
    """95 % F-test interval per free Ka that treats every replicate's point as an independent observation.

    One coefficient set is fitted to all ``m·n`` points at each Ka and the
    threshold uses ``n = m·n_points``; the app averages the replicates
    instead, and this is the alternative the averaging is measured against.
    The profile, its search and its edges are written here: the design comes
    from the model's species at each Ka, the coefficients from bounded linear
    least squares on norm-scaled columns, the search from a grid at
    ``_REFERENCE_PER_DECADE`` refined by bounded Brent, and the edges from
    root finding on the profile. With two binding constants the profile of
    one is the minimum over the other, found the same way on the other axis.
    """
    meta = assay.registry_metadata
    keys = assay.parameter_keys
    bounds = float_bounds(assay)
    ka_keys = ka_keys_of(assay)
    coef_keys = [k for k in keys if k not in ka_keys]
    lb = np.array([bounds[k][0] for k in coef_keys])
    ub = np.array([bounds[k][1] for k in coef_keys])
    pinned = lb == ub
    m, n_points = signals.shape
    stacked = signals.ravel()
    free_ka = [k for k in ka_keys if bounds[k][0] != bounds[k][1]]
    axes = {
        k: np.geomspace(*bounds[k], int(np.ceil(np.log10(bounds[k][1] / bounds[k][0]) * _REFERENCE_PER_DECADE)) + 1)
        for k in free_ka
    }

    def design(ka: dict[str, float]) -> np.ndarray:
        params = np.array([ka.get(k, bounds[k][0]) for k in keys])
        species = assay.species(params)
        columns = [
            np.ones(n_points) if k not in meta.signal_species else species[meta.signal_species[k]] for k in coef_keys
        ]
        return np.column_stack(columns)

    def ssr(ka: dict[str, float]) -> float:
        d = design(ka)
        if not np.isfinite(d).all():
            return np.inf
        d = np.tile(d, (m, 1))
        target = stacked - d[:, pinned] @ lb[pinned]
        free = d[:, ~pinned]
        scale = np.linalg.norm(free, axis=0)
        scale[scale == 0] = 1.0
        sol = lsq_linear(free / scale, target, bounds=(lb[~pinned] * scale, ub[~pinned] * scale), method='bvls')
        return float(np.sum((free @ np.clip(sol.x / scale, lb[~pinned], ub[~pinned]) - target) ** 2))

    # The SSR on the full grid; the profile of one Ka at a node is the minimum of a row, refined.
    grid = np.empty(tuple(axes[k].size for k in free_ka))
    for index in np.ndindex(grid.shape):
        grid[index] = ssr({k: axes[k][i] for k, i in zip(free_ka, index)})

    def profile(key: str, value: float) -> tuple[float, dict[str, float]]:
        """Best SSR at ``key = value`` over the other free Ka, and the Ka pair reaching it."""
        others = [k for k in free_ka if k != key]
        if not others:
            return ssr({key: value}), {key: value}
        other = others[0]
        hits = np.flatnonzero(axes[key] == value)
        scan = (
            np.take(grid, hits[0], axis=free_ka.index(key))
            if hits.size
            else np.array([ssr({key: value, other: k}) for k in axes[other]])
        )
        best_other, best = _refine(lambda k: ssr({key: value, other: k}), axes[other], scan)
        return best, {key: value, other: best_other}

    # Best fit: the profile of the first free Ka, minimised along its axis.
    first = free_ka[0]
    node_profile = {first: np.array([profile(first, v)[0] for v in axes[first]])}
    best_ka1, s_min = _refine(lambda k: profile(first, k)[0], axes[first], node_profile[first])
    best_ka = profile(first, best_ka1)[1]
    scaled = design(best_ka)[:, ~pinned]
    scaled = scaled / np.where(np.linalg.norm(scaled, axis=0) == 0, 1.0, np.linalg.norm(scaled, axis=0))
    rank = int(np.linalg.matrix_rank(scaled, tol=_RANK_RTOL * np.linalg.norm(scaled, 2)))
    n, p = m * n_points, len(free_ka) + rank
    threshold = s_min * (1 + f_dist.ppf(LEVEL, 1, n - p) / (n - p))

    intervals = {}
    for key in free_ka:
        nodes = axes[key]
        on_nodes = node_profile.get(key)
        if on_nodes is None:
            on_nodes = np.array([profile(key, v)[0] for v in nodes])
        inside = np.append(nodes[on_nodes <= threshold], best_ka[key])
        low_in, high_in = float(inside.min()), float(inside.max())
        below, above = nodes[nodes < low_in], nodes[nodes > high_in]

        def edge(outside: float, within: float) -> float:
            return float(
                10 ** brentq(lambda t: profile(key, 10**t)[0] - threshold, np.log10(outside), np.log10(within))
            )

        low = edge(below[-1], low_in) if below.size else float(nodes[0])
        high = edge(above[0], high_in) if above.size else float(nodes[-1])
        intervals[key] = (low, high)
    return intervals


def one_dataset(assay_name: str, scenario: str, n_points: int, regime: float | None, seed: int) -> dict[str, Any]:
    """Fit one synthetic dataset and say what its intervals and region delivered."""
    system = SYSTEMS[assay_name]
    clean, truth = clean_data(system, n_points, regime)
    x = clean.x_data.magnitude
    signals = make_signals(scenario, x, clean.y_data.magnitude, np.random.default_rng(seed))
    ms = MeasurementSet(concentrations=x, signals=signals, replica_ids=tuple(f'r{i}' for i in range(signals.shape[0])))
    assay = ms.to_assay(system.assay_cls, conditions=system.conditions, use_average=True)

    # The fit and its intervals, by the engine calls a fit of the averaged signal makes.
    projection = Projection(assay, assay.get_default_bounds())
    fit = projection.fit()
    out: dict[str, Any] = {'ka': {}, 'joint': None, 'pooled': {}}
    for key in projection.free_ka:
        ci = projection.interval(key, fit)
        out['ka'][key] = {
            'covered': ci.low <= truth[key] <= ci.high,
            'width': np.log10(ci.high / ci.low),
            'open': ci.open_low or ci.open_high,
        }
    if len(projection.free_ka) == 2:
        at_truth = projection.row_ssr({k: truth[k] for k in projection.free_ka})[0]
        out['joint'] = at_truth <= projection.threshold(fit, n_constrained=2)
    # A signal parameter on a bound, among those the data determine: a
    # degenerate one sits wherever the solver put its family's member.
    coefficients = fit.coefficients[0]
    bounds = float_bounds(assay)
    lb, ub = (np.array([bounds[k][i] for k in projection.coef_keys]) for i in (0, 1))
    determined = (lb != ub) & ~np.isin(projection.coef_keys, projection.degenerate_keys(fit))
    out['bound_active'] = bool(
        np.any((coefficients[determined] <= lb[determined]) | (coefficients[determined] >= ub[determined]))
    )

    if scenario in ('replicates', 'shared-misfit'):
        for key, (low, high) in pooled_intervals(assay, signals).items():
            out['pooled'][key] = {'covered': low <= truth[key] <= high, 'width': np.log10(high / low)}
    return out


def _fraction(flags: list[bool]) -> str:
    """A proportion with its exact 95 % limits, formatted for the table."""
    hits, n = sum(flags), len(flags)
    low, high = clopper_pearson(hits, n)
    return f'{hits / n:8.3f}  [{low:.3f}, {high:.3f}]'


def run_scenario(
    scenario: str, assay_name: str, n_points: int, regime: float | None, n_designs: int, seed: int, jobs: int
) -> None:
    """Fit *n_designs* synthetic datasets and print the scenario's rows."""
    work = partial(one_dataset, assay_name, scenario, n_points, regime)
    seeds = range(seed, seed + n_designs)
    if jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            results = list(pool.map(work, seeds))
    else:
        results = [work(s) for s in seeds]

    label = scenario
    for key in results[0]['ka']:
        rows = [r['ka'][key] for r in results]
        line = (
            f'{label:14s} {key:13s} {_fraction([r["covered"] for r in rows])}'
            f'  {np.median([r["width"] for r in rows]):11.3f}  {np.mean([r["open"] for r in rows]):5.3f}'
        )
        if results[0]['pooled']:
            pooled = [r['pooled'][key] for r in results]
            line += f'  {_fraction([r["covered"] for r in pooled])}  {np.median([r["width"] for r in pooled]):11.3f}'
        print(line, flush=True)
        label = ''
    if results[0]['joint'] is not None:
        print(f'{label:14s} {"joint region":13s} {_fraction([r["joint"] for r in results])}', flush=True)
    print(f'{label:14s} {"bound active":13s} {np.mean([r["bound_active"] for r in results]):8.3f}', flush=True)


def main() -> None:
    """Run every scenario for one assay and print the coverage table."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--assay', choices=list(SYSTEMS), default='IDA', help='the model to fit (default IDA)')
    parser.add_argument(
        '--regime', type=float, default=None, help="Ka·c of the truth (default: the test suite's ground truth)"
    )
    parser.add_argument('--points', type=int, default=12, help='titration points per dataset (default 12)')
    parser.add_argument('--designs', type=int, default=50, help='synthetic datasets per scenario (default 50)')
    parser.add_argument('--seed', type=int, default=1000, help='first dataset seed; datasets use consecutive seeds')
    parser.add_argument('--jobs', type=int, default=os.cpu_count() or 1, help='worker processes (default: every core)')
    args = parser.parse_args()

    system = SYSTEMS[args.assay]
    assay, truth = clean_data(system, args.points, args.regime)
    keys = ka_keys_of(assay)
    truths = ', '.join(f'{k} {truth[k]:.3g} 1/M' for k in keys)
    print(
        f'{args.assay}: nominal {LEVEL:.0%} intervals, {args.designs} datasets per scenario from seed {args.seed}, '
        f'{args.points} titration points,\ntrue {truths} '
        f'({keys[0]}·{system.regime_conc} = {truth[keys[0]] * regime_conc(system):.3g}).\n'
        'Width is the median interval width in decades of Ka; "open" is the fraction of intervals reaching a Ka bound;\n'
        '"bound active" the fraction of fits with a signal parameter the data determine on a bound. "pooled" treats\n'
        'every replicate point as independent instead of averaging the replicates.'
    )
    print(
        f'\n{"scenario":14s} {"":13s} {"coverage":>8s}  {"95% exact":>16s}  {"width (dec)":>11s}  {"open":>5s}'
        f'  {"pooled":>8s}  {"95% exact":>16s}  {"width (dec)":>11s}'
    )
    for scenario in SCENARIOS:
        run_scenario(scenario, args.assay, args.points, args.regime, args.designs, args.seed, args.jobs)


if __name__ == '__main__':
    main()
