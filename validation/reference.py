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

Where the replicates show a noise law, both computations carry it: the
reference whitens its own target and design with the same point weights the
engine is given, so what the agreement tests is still the definition and not
the weighting. :func:`agreement_row` answers the engine's own question — the
average of the replicates, weighted — and :func:`pooling_row` the alternative
it is measured against, every replicate's point kept as an observation of its
own.
"""

from __future__ import annotations

import time
from typing import Any, Callable

import numpy as np
from scipy.optimize import brentq, lsq_linear, minimize, minimize_scalar
from scipy.stats import f as f_dist

from core.assays.base import BaseAssay
from core.pipeline.inputs import ErrorModel, SpecKind
from core.pipeline.noise import noise_law
from core.pipeline.varpro import LEVEL, Projection
from validation.generate import dataset, stream_seed
from validation.scenarios import Scenario
from validation.score import guard

__all__ = ['agreement_row', 'pooling_row', 'reference_intervals']

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

#: Distance from a bound, as a fraction of the length of the target, below which
#: a coefficient counts as held on that bound rather than fitted. Read in the
#: norm-scaled variables the bounded solve works in, so it is the change the
#: coefficient could still make to the fitted curve. The solve puts a held
#: coefficient exactly on its bound, so the reading only has to separate zero
#: from the scatter a fitted coefficient keeps.
_ON_BOUND_RTOL = 1e-8

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


def _column_rank(columns: np.ndarray) -> int:
    """Numerical rank of *columns* norm-scaled, at the ``_RANK_RTOL`` cut-off."""
    if columns.shape[1] == 0:
        return 0
    norms = np.linalg.norm(columns, axis=0)
    scaled = columns / np.where(norms == 0, 1.0, norms)
    return int(np.linalg.matrix_rank(scaled, tol=_RANK_RTOL * np.linalg.norm(scaled, 2)))


def _refine(fn: Callable[[float], float], grid: np.ndarray, on_grid: np.ndarray) -> tuple[float, float]:
    """Minimum of *fn* in log Ka between the neighbours of the best grid node, as ``(Ka, value)``."""
    i = int(np.argmin(on_grid))
    lo, hi = np.log10(grid[max(i - 1, 0)]), np.log10(grid[min(i + 1, grid.size - 1)])
    res = minimize_scalar(lambda t: fn(10.0**t), bounds=(lo, hi), method='bounded')
    return (float(10.0**res.x), float(res.fun)) if res.fun < on_grid[i] else (float(grid[i]), float(on_grid[i]))


def reference_intervals(
    assay: BaseAssay,
    signals: np.ndarray,
    errors: ErrorModel,
    seed: int,
    stream: str,
    weights: np.ndarray | None = None,
) -> dict[str, tuple[float, float]] | None:
    """95 % interval per free Ka, computed from the model's species by machinery of its own.

    Every row of *signals* is an observation: one coefficient set is fitted to
    all ``N = m·n`` points at each Ka. Handed the average of the replicates it
    answers the engine's own question, and handed every replicate's points it
    answers the alternative the averaging is measured against.

    The profile is ``P(k) = min [N log S_w + z'z]``, the minimum over the other
    free Ka and over the offsets of the inputs *errors* states, ``z`` the offsets
    stated with a standard deviation in units of it, and the interval holds the
    Ka with ``P(k) - P_min <= N log(1 + m F(0.95; m, nu) / nu)``.

    The numerator counts the parameters the best fit has and the fit at ``k``
    has not: the tested Ka, and every signal parameter the best fit fits while
    the bounded solve at ``k`` holds it on a bound, since a coefficient on a
    bound is not fitted. With ``r(k)`` the rank of the columns whose
    coefficient the reference's own solve leaves strictly inside its bounds at
    ``k``, and ``k_hat`` the best fit,

        m = 1 + max(0, r(k_hat) - r(k))

    so the cut-off is a step function of ``k``: the constant cut-off of the
    plain F test wherever the profile gives no signal parameter up, one step
    higher wherever it gives one up. Every edge and every accepted node is
    judged against the cut-off its own fitted rank names.

    ``S_w`` is the weighted residual sum of squares ``sum w_i (y_i - f_i)²``:
    the target and the free columns are multiplied by ``sqrt(w)`` before the
    columns are norm-scaled and the coefficients solved, so the objective, the
    threshold and ``nu`` keep their form — the ``sum log w`` term of the log
    likelihood is the same at every Ka.

    With no uncertain input the minimum over a second Ka is a scan of the SSR
    grid refined by Brent and ``nu = N - p``: the F test on the SSR. With
    uncertain inputs it is Nelder-Mead over (the other Ka, the offsets) from
    ``_STARTS`` start points drawn from *stream* and the seed, each run
    restarted where it stopped until it gains nothing, and
    ``nu = N - p - sum w``, ``p`` counting every input stated as a range and
    ``w`` the eigenvalues of ``I - [H⁻¹]_zz`` from a central-difference
    Jacobian of ``[r / s ; z]`` at the optimum, ``s² = S_w / N``.

    Parameters
    ----------
    assay : BaseAssay
        The assay the interval is computed for, built from the entered inputs.
    signals : np.ndarray
        Measured signals, shape ``(replicates, points)``.
    errors : ErrorModel
        The stated error sources. Only an input's own uncertainty is a
        direction this profile searches, so a model carrying a shared source or
        a per-addition error is refused rather than answered for a model it
        does not describe.
    seed : int
        The dataset's seed.
    stream : str
        Key of the start-point stream, the scenario's id, so that the
        reference's draws are per (scenario, seed) like every other stream in
        the package and a start pattern that suits one scenario is not shared
        by all of them.
    weights : np.ndarray, optional
        Weight of each titration point, tiled over the rows of *signals*.
        Equal weights when omitted, which is the fit of a titration whose
        replicates show no noise law.

    Returns
    -------
    dict[str, tuple[float, float]] | None
        Interval per free binding constant, or ``None`` when less than one
        degree of freedom is left.
    """
    if errors.shared or errors.additions is not None:
        raise ValueError(
            'The independent reference moves each input on its own, so it cannot compute an interval under a '
            'shared error source or a per-addition error. Compare the engine against it on a scenario that '
            'states neither.'
        )
    specs = errors.specs
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
    root = None if weights is None else np.sqrt(np.tile(np.asarray(weights, dtype=float), m))
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

    def bounded(ka: dict[str, float], coords: np.ndarray) -> tuple[np.ndarray, ...] | None:
        """One bounded solve of the coefficients at *ka* with the inputs at *coords*.

        Returns the model's own design columns, the free ones tiled over the
        rows and weighted, their norm scale, the solution in those norm-scaled
        variables and the target it was fitted to; ``None`` where the model has
        no solution.
        """
        columns = design(ka, coords)
        if not np.isfinite(columns).all():
            return None
        d = np.tile(columns, (m, 1))
        target = stacked - d[:, pinned] @ lb[pinned]
        free = d[:, ~pinned]
        if root is not None:
            target = target * root
            free = free * root[:, np.newaxis]
        scale = np.linalg.norm(free, axis=0)
        scale[scale == 0] = 1.0
        sol = lsq_linear(free / scale, target, bounds=(lb[~pinned] * scale, ub[~pinned] * scale), method='bvls')
        return columns, free, scale, sol.x, target

    def residual(ka: dict[str, float], coords: np.ndarray) -> np.ndarray | None:
        solved = bounded(ka, coords)
        if solved is None:
            return None
        _, free, scale, x, target = solved
        return free @ np.clip(x / scale, lb[~pinned], ub[~pinned]) - target

    def fitted_rank(ka: dict[str, float], coords: np.ndarray) -> int:
        """Rank of the columns whose coefficient the bounded solve leaves strictly inside its bounds.

        The solve works in norm-scaled variables, so a coefficient's distance
        from its bound there is the change it could still make to the fitted
        curve; a coefficient the active set holds sits exactly on its bound and
        a fitted one lies a real distance away, which ``_ON_BOUND_RTOL`` of the
        target's length separates. A rank of those columns and not a count of
        them, because a mass balance ties columns together and the solve then
        holds one member of a family any member of which could have been the
        one left free.
        """
        solved = bounded(ka, coords)
        if solved is None:
            return 0
        columns, _, scale, x, target = solved
        margin = np.minimum(x - lb[~pinned] * scale, ub[~pinned] * scale - x)
        inside = margin > _ON_BOUND_RTOL * float(np.linalg.norm(target))
        return _column_rank(columns[:, ~pinned][:, inside])

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
    node_points = {first: [profile(first, v) for v in axes[first]]}
    on_first = np.array([point[0] for point in node_points[first]])
    best_ka1, p_min = _refine(lambda k: profile(first, k)[0], axes[first], on_first)
    _, best_ka, best_coords = profile(first, best_ka1)
    rank = _column_rank(design(best_ka, best_coords)[:, ~pinned])
    best_fitted = fitted_rank(best_ka, best_coords)
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
    cuts: dict[int, float] = {}

    def cut_off(rank_here: int) -> float:
        """Objective a fit of fitted rank *rank_here* is accepted below."""
        released = max(0, best_fitted - rank_here)
        if released not in cuts:
            # m: the tested Ka plus the signal parameters a fit of this rank gives up.
            tested = 1 + released
            cuts[released] = p_min + n * float(np.log1p(tested * f_dist.ppf(LEVEL, tested, dof) / dof))
        return cuts[released]

    def excess(key: str, value: float) -> float:
        """How far the profile at ``key = value`` stands above the cut-off its own fitted rank names."""
        found, ka, coords = profile(key, value)
        return found - cut_off(fitted_rank(ka, coords))

    intervals = {}
    for key in free_ka:
        nodes = axes[key]
        points = node_points.get(key) or [profile(key, v) for v in nodes]
        above_cut = np.array([found - cut_off(fitted_rank(ka, coords)) for found, ka, coords in points])
        inside = np.append(nodes[above_cut <= 0.0], best_ka[key])
        low_in, high_in = float(inside.min()), float(inside.max())
        below, above = nodes[nodes < low_in], nodes[nodes > high_in]

        def edge(outside: float, within: float, key: str = key) -> float:
            return float(10 ** brentq(lambda t: excess(key, 10**t), np.log10(outside), np.log10(within)))

        low = edge(below[-1], low_in) if below.size else float(nodes[0])
        high = edge(above[0], high_in) if above.size else float(nodes[-1])
        intervals[key] = (low, high)
    return intervals


def _row(scenario: Scenario, seed: int, pooled: bool) -> dict[str, Any]:
    """One dataset through both computations, with the law its replicates show carried by both.

    The engine fits the average of the replicates, weighted by that law. The
    reference is handed the same average when *pooled* is false and every
    replicate's points when it is true, weighted the same way either way, so
    what a pooled row compares is the pooling and not the weighting. A pooled
    row carries a third interval beside them: the engine's own fit of the same
    average with every point counted equally.
    """
    started = time.perf_counter()
    data = dataset(scenario, seed)

    def work() -> dict[str, Any]:
        mean = data.signals.mean(axis=0)
        weights = noise_law(data.signals).weights(mean)
        bounds = data.assay.get_default_bounds()
        projection = Projection(data.assay, bounds, point_weights=weights)
        fit = projection.fit()
        engine = {key: projection.interval(key, fit) for key in projection.free_ka}
        found = reference_intervals(
            data.assay,
            data.signals if pooled else mean[np.newaxis, :],
            scenario.error_model,
            seed,
            scenario.id,
            weights=weights,
        )
        if found is None:
            # The keys of the question that was asked, empty: a metric reads
            # the same fields whether or not the reference converged.
            asked = (
                ('ref_covers', 'engine_covers', 'equal_covers', 'ref_width', 'engine_width', 'equal_width')
                if pooled
                else ('agrees', 'apart')
            )
            return {**{name: {} for name in asked}, 'no_reference': True}
        out: dict[str, Any] = {
            'ref_covers': {},
            'engine_covers': {},
            'ref_width': {},
            'engine_width': {},
            'no_reference': False,
        }
        if pooled:
            equal = Projection(data.assay, bounds)
            equal_fit = equal.fit()
            out.update({'equal_covers': {}, 'equal_width': {}})
        else:
            out.update({'agrees': {}, 'apart': {}})
        for key, (low, high) in found.items():
            interval = engine[key]
            out['ref_covers'][key] = bool(low <= data.truth[key] <= high)
            out['engine_covers'][key] = bool(interval.low <= data.truth[key] <= interval.high)
            out['ref_width'][key] = float(np.log10(high / low))
            out['engine_width'][key] = float(np.log10(interval.high / interval.low))
            if pooled:
                unweighted = equal.interval(key, equal_fit)
                out['equal_covers'][key] = bool(unweighted.low <= data.truth[key] <= unweighted.high)
                out['equal_width'][key] = float(np.log10(unweighted.high / unweighted.low))
            else:
                apart = max(abs(np.log10(low / interval.low)), abs(np.log10(high / interval.high)))
                out['apart'][key] = float(apart)
                out['agrees'][key] = bool(apart <= AGREEMENT_DECADES)
        return out

    result = guard(work)
    result['t_total'] = time.perf_counter() - started
    return result


def agreement_row(scenario: Scenario, seed: int) -> dict[str, Any]:
    """The engine's interval and the independent one on the same data, and how far apart their edges lie.

    Both are computed from the average of the replicates, weighted by the law
    they show, which is the fit the application reports.

    Returns
    -------
    dict
        Per binding constant: whether the two edges agree to
        :data:`AGREEMENT_DECADES`, how far apart the further edge is in decades
        of Ka, and whether each interval holds the truth.
    """
    return _row(scenario, seed, pooled=False)


def pooling_row(scenario: Scenario, seed: int) -> dict[str, Any]:
    """The interval of the replicates averaged, the interval of their points pooled, and the unweighted one.

    Returns
    -------
    dict
        Per binding constant: whether each of the three intervals holds the
        truth and how wide it is. ``engine`` is the weighted fit of the
        average the application performs, ``ref`` the same law applied to
        every replicate's points, and ``equal`` the same average with every
        point counted equally.
    """
    return _row(scenario, seed, pooled=True)
