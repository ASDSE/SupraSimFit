"""An interval for the same data, computed by machinery the engine shares nothing with.

The engine projects the signal parameters out, searches the binding constants
on a log grid and cuts the interval where the profile crosses an F threshold.
The reference here writes all of that itself: the design comes from the model's
species at each Ka, the coefficients from bounded linear least squares on
norm-scaled columns, the search from a denser grid refined by bounded Brent,
and the edges from root finding on the profile. Where an input may move, the
profile is minimised by Nelder-Mead, which needs no derivative of an objective
that has a kink wherever a signal parameter reaches a bound.

The two agreeing to a fraction of a decade is what says the engine's interval
is the interval its definition names, rather than an artefact of how it
searches.
"""

from __future__ import annotations

import time
from typing import Any, Callable

import numpy as np
from scipy.optimize import brentq, lsq_linear, minimize, minimize_scalar
from scipy.stats import f as f_dist

from core.assays.base import BaseAssay
from core.pipeline.inputs import InputSpec, SpecKind
from core.pipeline.varpro import LEVEL, Projection
from validation.generate import dataset, stream_seed
from validation.scenarios import Scenario
from validation.score import guard

__all__ = ['reference_intervals', 'row']

#: Ka grid density of the reference profile, in points per decade: twice the
#: engine's search density, so the reference shares none of its choices, and
#: refined between neighbouring nodes so the best fit and the edges are exact.
_PER_DECADE = 8

#: The reference profile with uncertain inputs: every profile value is the
#: lowest of three Nelder-Mead runs, each restarted where it stopped until it
#: gains less than _RESTART_GAIN, eight orders below the acceptance excess (3
#: to 6 at 12 to 30 points).
_STARTS = 3
_NELDER_MEAD = {'xatol': 1e-8, 'fatol': 1e-10, 'maxiter': 4000, 'maxfev': 4000, 'adaptive': True}
_RESTART_GAIN = 1e-8

#: Central-difference step of the reference's Jacobian, in decades of Ka and in
#: stated standard deviations of an input: the cube root of machine precision,
#: the step that balances the truncation and rounding errors of a central
#: difference.
_JACOBIAN_STEP = 6e-6

#: Relative singular-value cut-off for the rank of the norm-scaled coefficient
#: design, the same as the engine's: the columns a mass balance ties together
#: carry relative singular values of 2e-17 to 2e-15, a direction the signal
#: separates stays above 7e-7, and 1e-8 sits in the gap.
_RANK_RTOL = 1e-8

#: How far apart, in decades of Ka, an edge of the two intervals may lie and
#: still count as the same edge. The two agree to about 1e-6 decades where they
#: were measured, so this is a wide margin on a difference that should be
#: numerical noise.
AGREEMENT_DECADES = 1e-4


def float_bounds(assay: BaseAssay) -> dict[str, tuple[float, float]]:
    """The app's default bounds of every parameter, in canonical units."""
    units = assay.registry_metadata.units
    return {
        k: (float(lo.to(units[k]).magnitude), float(hi.to(units[k]).magnitude))
        for k, (lo, hi) in assay.get_default_bounds().items()
    }


def _refine(fn: Callable[[float], float], grid: np.ndarray, on_grid: np.ndarray) -> tuple[float, float]:
    """Minimum of *fn* in log Ka between the neighbours of the best grid node, as ``(Ka, value)``."""
    i = int(np.argmin(on_grid))
    lo, hi = np.log10(grid[max(i - 1, 0)]), np.log10(grid[min(i + 1, grid.size - 1)])
    res = minimize_scalar(lambda t: fn(10.0**t), bounds=(lo, hi), method='bounded')
    return (float(10.0**res.x), float(res.fun)) if res.fun < on_grid[i] else (float(grid[i]), float(on_grid[i]))


def reference_intervals(
    assay: BaseAssay, signals: np.ndarray, specs: dict[str, InputSpec], seed: int, stream: str
) -> dict[str, tuple[float, float]] | None:
    """95 % interval per free Ka that treats every replicate's point as an independent observation.

    One coefficient set is fitted to all ``N = m·n`` points at each Ka; the app
    averages the replicates instead, and this is the alternative the averaging
    is measured against. On one replicate the two describe the same data, and
    the intervals are then comparable edge by edge.

    The profile is ``P(k) = min [N log S + z'z]``, the minimum over the other
    free Ka and over the offsets of the inputs in *specs*, ``z`` the offsets
    stated with a standard deviation in units of it, and the interval holds the
    Ka with ``P(k) - P_min <= N log(1 + F(0.95; 1, nu) / nu)``. With no
    uncertain input the minimum over a second Ka is a scan of the SSR grid
    refined by Brent and ``nu = N - p``: the F test on the SSR. With uncertain
    inputs it is Nelder-Mead over (the other Ka, the offsets) from ``_STARTS``
    start points drawn from *stream* and the seed, each run restarted where it
    stopped until it gains nothing, and ``nu = N - p - sum w``, ``p`` counting
    every input stated as a range and ``w`` the eigenvalues of
    ``I - [H⁻¹]_zz`` from a central-difference Jacobian of ``[r / s ; z]`` at
    the optimum, ``s² = S / N``.

    Parameters
    ----------
    assay : BaseAssay
        The assay the interval is computed for, built from the entered inputs.
    signals : np.ndarray
        Measured signals, shape ``(replicates, points)``.
    specs : dict[str, InputSpec]
        Stated uncertainty of every input the profile may move.
    seed : int
        The dataset's seed.
    stream : str
        Key of the start-point stream, the scenario's id, so that the
        reference's draws are per (scenario, seed) like every other stream in
        the package and a start pattern that suits one scenario is not shared
        by all of them.

    Returns
    -------
    dict[str, tuple[float, float]] | None
        Interval per free binding constant, or ``None`` when less than one
        degree of freedom is left.
    """
    meta = assay.registry_metadata
    keys = assay.parameter_keys
    bounds = float_bounds(assay)
    ka_keys = [k for k in keys if k.startswith('Ka')]
    coef_keys = [k for k in keys if k not in ka_keys]
    lb = np.array([bounds[k][0] for k in coef_keys])
    ub = np.array([bounds[k][1] for k in coef_keys])
    pinned = lb == ub
    m, n_points = signals.shape
    n = m * n_points
    stacked = signals.ravel()
    free_ka = [k for k in ka_keys if bounds[k][0] != bounds[k][1]]
    axes = {
        k: np.geomspace(*bounds[k], int(np.ceil(np.log10(bounds[k][1] / bounds[k][0]) * _PER_DECADE)) + 1)
        for k in free_ka
    }
    # Input offsets are searched in units of the stated standard deviation or half range.
    input_keys = list(specs)
    is_sigma = np.array([s.kind is SpecKind.SIGMA for s in specs.values()], dtype=bool)
    unit = np.array([s.sigma / 100 if s.kind is SpecKind.SIGMA else (s.hi - s.lo) / 200 for s in specs.values()])
    box_lo = np.array([-1 + 1e-6 if s.kind is SpecKind.SIGMA else s.lo / 100 for s in specs.values()]) / unit
    box_hi = np.array([np.inf if s.kind is SpecKind.SIGMA else s.hi / 100 for s in specs.values()]) / unit
    entered_coords = np.clip(np.zeros(len(specs)), box_lo, box_hi)

    def design(ka: dict[str, float], coords: np.ndarray) -> np.ndarray:
        moved = assay.with_inputs(dict(zip(input_keys, coords * unit))) if input_keys else assay
        species = moved.species(np.array([ka.get(k, bounds[k][0]) for k in keys]))
        columns = [
            np.ones(n_points) if k not in meta.signal_species else species[meta.signal_species[k]] for k in coef_keys
        ]
        return np.column_stack(columns)

    def residual(ka: dict[str, float], coords: np.ndarray) -> np.ndarray | None:
        d = design(ka, coords)
        if not np.isfinite(d).all():
            return None
        d = np.tile(d, (m, 1))
        target = stacked - d[:, pinned] @ lb[pinned]
        free = d[:, ~pinned]
        scale = np.linalg.norm(free, axis=0)
        scale[scale == 0] = 1.0
        sol = lsq_linear(free / scale, target, bounds=(lb[~pinned] * scale, ub[~pinned] * scale), method='bvls')
        return free @ np.clip(sol.x / scale, lb[~pinned], ub[~pinned]) - target

    def objective(ka: dict[str, float], coords: np.ndarray = entered_coords) -> float:
        r = residual(ka, coords)
        return np.inf if r is None else n * float(np.log(r @ r)) + float(np.sum(coords[is_sigma] ** 2))

    # With two free Ka: the objective at the entered inputs on the full grid. The profile of one
    # Ka at a node starts from the minimum of its row.
    grid = np.empty(tuple(axes[k].size for k in free_ka)) if len(free_ka) == 2 else None
    for index in np.ndindex(grid.shape) if grid is not None else ():
        grid[index] = objective({k: axes[k][i] for k, i in zip(free_ka, index)})
    rng = np.random.default_rng(stream_seed(f'{stream}|reference', seed))
    # Start points: the entered inputs with the other Ka at the minimum of its grid row, then draws
    # of the inputs from what was stated (a range is two units wide) with that Ka moved by a
    # standard normal number of decades.
    shape = (_STARTS - 1, len(specs))
    draws = np.where(is_sigma, rng.standard_normal(shape), np.where(is_sigma, 0.0, box_lo) + 2 * rng.random(shape))
    coord_starts = np.clip(np.vstack([entered_coords, draws]), box_lo, box_hi)
    jitter = np.append(0.0, rng.standard_normal(_STARTS - 1))

    def profile(key: str, value: float) -> tuple[float, dict[str, float], np.ndarray]:
        """Lowest objective at ``key = value``, the Ka pair and the input coordinates reaching it."""
        others = [k for k in free_ka if k != key]
        if not others and not input_keys:
            return objective({key: value}), {key: value}, entered_coords
        start_other = []
        if others:
            other = others[0]
            i = int(np.argmin(np.abs(np.log10(axes[key]) - np.log10(value))))
            on_node = axes[key][i] == value
            scan = (
                np.take(grid, i, axis=free_ka.index(key))
                if on_node or input_keys
                else np.array([objective({key: value, other: k}) for k in axes[other]])
            )
            if not input_keys:
                best_other, best = _refine(lambda k: objective({key: value, other: k}), axes[other], scan)
                return best, {key: value, other: best_other}, entered_coords
            start_other = [np.log10(axes[other][int(np.argmin(scan))])]
            other_box = np.log10(bounds[other])

        def fun(v: np.ndarray) -> float:
            ka = {key: value, **({other: 10.0 ** v[0]} if others else {})}
            return objective(ka, v[len(others) :])

        box = [*([tuple(other_box)] if others else []), *zip(box_lo, box_hi)]
        found = (np.inf, np.array([*start_other, *entered_coords]))
        for decades, coords in zip(jitter, coord_starts):
            v = np.array([*(np.clip(t + decades, *other_box) for t in start_other), *coords])
            lowest = np.inf
            while True:
                res = minimize(fun, v, method='Nelder-Mead', bounds=box, options=_NELDER_MEAD)
                if not res.fun < lowest - _RESTART_GAIN:
                    break
                v, lowest = res.x, float(res.fun)
            if lowest < found[0]:
                found = (lowest, v)
        v = found[1]
        return found[0], {key: value, **({other: float(10.0 ** v[0])} if others else {})}, v[len(others) :]

    # Best fit: the profile of the first free Ka, minimised along its axis.
    first = free_ka[0]
    node_profile = {first: np.array([profile(first, v)[0] for v in axes[first]])}
    best_ka1, p_min = _refine(lambda k: profile(first, k)[0], axes[first], node_profile[first])
    _, best_ka, best_coords = profile(first, best_ka1)
    scaled = design(best_ka, best_coords)[:, ~pinned]
    scaled = scaled / np.where(np.linalg.norm(scaled, axis=0) == 0, 1.0, np.linalg.norm(scaled, axis=0))
    rank = int(np.linalg.matrix_rank(scaled, tol=_RANK_RTOL * np.linalg.norm(scaled, 2)))
    dof = n - len(free_ka) - rank - int(np.sum(~is_sigma))
    if is_sigma.any() and dof >= 1:
        # What the data, and not the penalty, determine of each input stated with a standard deviation.
        at = np.array([*(np.log10(best_ka[k]) for k in free_ka), *best_coords])
        s = np.sqrt(np.exp((p_min - np.sum(best_coords[is_sigma] ** 2)) / n) / n)

        def stacked_residual(v: np.ndarray) -> np.ndarray:
            ka = {k: 10.0 ** v[i] for i, k in enumerate(free_ka)}
            return np.concatenate([residual(ka, v[len(free_ka) :]) / s, v[len(free_ka) :][is_sigma]])

        steps = _JACOBIAN_STEP * np.eye(at.size)
        jac = np.column_stack(
            [(stacked_residual(at + h) - stacked_residual(at - h)) / (2 * _JACOBIAN_STEP) for h in steps]
        )
        z_columns = len(free_ka) + np.flatnonzero(is_sigma)
        covariance = np.linalg.pinv(jac.T @ jac)[np.ix_(z_columns, z_columns)]
        dof -= float(np.clip(np.linalg.eigvalsh(np.eye(z_columns.size) - covariance), 0.0, 1.0).sum())
    if dof < 1:
        return None
    threshold = p_min + n * float(np.log1p(f_dist.ppf(LEVEL, 1, dof) / dof))

    intervals = {}
    for key in free_ka:
        nodes = axes[key]
        on_nodes = node_profile.get(key)
        if on_nodes is None:
            on_nodes = np.array([profile(key, v)[0] for v in nodes])
        inside = np.append(nodes[on_nodes <= threshold], best_ka[key])
        low_in, high_in = float(inside.min()), float(inside.max())
        below, above = nodes[nodes < low_in], nodes[nodes > high_in]

        def edge(outside: float, within: float, key: str = key) -> float:
            return float(
                10 ** brentq(lambda t: profile(key, 10**t)[0] - threshold, np.log10(outside), np.log10(within))
            )

        low = edge(below[-1], low_in) if below.size else float(nodes[0])
        high = edge(above[0], high_in) if above.size else float(nodes[-1])
        intervals[key] = (low, high)
    return intervals


def row(scenario: Scenario, seed: int) -> dict[str, Any]:
    """Both intervals of one dataset, and how far apart their edges lie.

    Returns
    -------
    dict
        Per binding constant: whether the two edges agree to
        :data:`AGREEMENT_DECADES`, how far apart the further edge is in decades
        of Ka, and whether each interval holds the truth.
    """
    started = time.perf_counter()
    data = dataset(scenario, seed)

    def work() -> dict[str, Any]:
        projection = Projection(data.assay, data.assay.get_default_bounds())
        fit = projection.fit()
        engine = {key: projection.interval(key, fit) for key in projection.free_ka}
        found = reference_intervals(data.assay, data.signals, scenario.input_specs, seed, scenario.id)
        if found is None:
            return {'agrees': {}, 'apart': {}, 'no_reference': True}
        out: dict[str, Any] = {
            'agrees': {},
            'apart': {},
            'ref_covers': {},
            'engine_covers': {},
            'ref_width': {},
            'engine_width': {},
            'no_reference': False,
        }
        for key, (low, high) in found.items():
            interval = engine[key]
            apart = max(abs(np.log10(low / interval.low)), abs(np.log10(high / interval.high)))
            out['apart'][key] = float(apart)
            out['agrees'][key] = bool(apart <= AGREEMENT_DECADES)
            out['ref_covers'][key] = bool(low <= data.truth[key] <= high)
            out['engine_covers'][key] = bool(interval.low <= data.truth[key] <= interval.high)
            out['ref_width'][key] = float(np.log10(high / low))
            out['engine_width'][key] = float(np.log10(interval.high / interval.low))
        return out

    result = guard(work)
    result['t_total'] = time.perf_counter() - started
    return result
