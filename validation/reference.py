"""An interval for the same data, computed by machinery the engine shares nothing with.

The engine projects the signal parameters out, searches the binding constants
on a log grid and cuts the interval where the profile crosses an F threshold.
The reference here writes all of that itself: the design comes from the model's
species at each Ka, the coefficients from bounded linear least squares on
norm-scaled columns, the search from a denser grid with bounded Brent run from
every local minimum of it and, for two free Ka, Nelder-Mead in both from the
lowest minima of the joint grid, and the edges from root finding on the
profile, every step of the fitted rank located by bisection. Where an input
may move, the profile is minimised by Nelder-Mead, which needs no derivative
of an objective that has a kink wherever a signal parameter reaches a bound.

The two agreeing to a fraction of a decade is what says the engine's interval
is the interval its definition names, rather than an artefact of how it
searches.

The definition the reference computes carries every rule of the reported
interval, each written here again in the reference's own terms:

- **Fitted parameters** (decision D-A2). A free Ka counts as fitted only off
  the ends of its box, a signal coefficient only where moving it to its bound
  changes the curve by more than ``_ON_BOUND_RTOL`` of the signal's weighted
  variation about its weighted mean, and an input stated as a range only off
  the ends of that range. A Ka rests on the end of its box nearer it wherever
  the profile there is no higher than the lowest objective found, to the
  resolution of R² (the rule of both fit engines,
  :func:`core.pipeline.varpro._rest_on_bounds`), and a coefficient lies on its
  bound at the minimum wherever the minimum with it held there is no higher,
  to the same resolution, and fits fewer columns (their rule
  :func:`core.pipeline.varpro._rest_coefficients`). What the best fit fitted
  is the ``p`` of ``n - p``;
  the numerator ``m`` of a tested Ka counts it and every coefficient the best
  fit fits and the fit at that Ka holds on a bound, so the cut-off is a step
  function of the fitted rank.
- **One-step pretest of the second constant** (decision D-Q2). A closed lower
  edge of the second constant of a stepwise model claims the second binding
  step exists, so it stands only where the data reject the model without that
  step: the profile at that constant equal to zero exactly, its ``m`` the
  constant plus the coefficients it releases, its F test at
  :data:`~core.pipeline.varpro.SECOND_STEP_LEVEL`. Where they do not, the
  interval is open below, at the constant's lower bound.
- **An edge the other constant's bound sets** (the interval's
  ``limited_by_low``). A lower edge of a two-Ka interval at which the other
  constant rests on its bound while the profile still falls towards that bound
  is open already, so the one-step pretest leaves it where it is.

Where the replicates show a noise law, both computations carry it: the
reference whitens its own target and design with the point weights the
application's fit ran with and widens its cut-off by the factor the
application's interval carries, so what the agreement tests is still the
definition and not the weighting. :func:`agreement_row` answers the engine's own question — the
average of the replicates, weighted — and :func:`pooling_row` the alternative
it is measured against, every replicate's point kept as an observation of its
own.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping

import numpy as np
from scipy.optimize import brentq, least_squares, lsq_linear, minimize, minimize_scalar
from scipy.stats import f as f_dist

from core.assays import ASSAY_CLASSES
from core.assays.base import BaseAssay
from core.assays.registry import AssayType
from core.pipeline.fit_pipeline import FitConfig, fit_measurement_set
from core.pipeline.inputs import ErrorModel, SpecKind
from core.pipeline.varpro import LEVEL, SECOND_STEP_LEVEL, Projection
from validation.generate import dataset, stream_seed
from validation.scenarios import Scenario
from validation.score import guard, measurement_set

__all__ = ['agreement_row', 'pooling_row', 'reference_intervals']

#: Ka grid density of the reference profile, in points per decade: twice the
#: engine's search density, so the reference shares none of its choices, and
#: refined between neighbouring nodes so the best fit and the edges are exact.
_PER_DECADE = 8

#: Tolerance of the bounded Brent refinement, in decades of Ka from the node
#: it refines around. The refinement runs in that offset rather than in
#: log10(Ka) itself, whose size would scale the solver's own relative
#: tolerance to 1e-7 decades: where a coefficient reaches its bound a few
#: tenths of a microdecade from the optimum, the fitted parameters are read on
#: the side of that step the optimum lies on only at this precision.
_REFINE_XATOL = 1e-10

#: Units in the last place within which two neighbouring grid values are the
#: same value when local minima are picked for refinement: where the objective
#: is flat towards an end of the box its grid values wiggle by a few units of
#: rounding, and those wiggles are no valleys.
_TIE_ULPS = 64

#: Density, in points per decade, at which a grid cell outside the accepted
#: Ka is profiled again where the fitted rank can differ inside it from the
#: rank its nodes read. The cut-off steps with the rank, so a stretch the test
#: accepts can begin and end between two rejected nodes; the dense reading
#: finds the rank steps a cell holds, a dip of the rank a thirtieth of a
#: decade wide included, and each step is then located to ``_STEP_DECADES``.
#: Off the nodes the other Ka of a two-Ka profile is scanned at this density
#: too: next to a rank step its objective can hold two shallow valleys a tenth
#: of a decade apart within a cell of the node axis, and the lower one is then
#: no local minimum of that axis.
_DENSE_PER_DECADE = 32

#: Width, in decades of Ka, to which a step of the fitted rank between two Ka
#: read is located by bisection before the profile is judged on both sides of
#: it: a stretch the step opens begins at the step, and is read however narrow
#: it is. Three orders below the agreement margin, the engine's edge
#: tolerance, and above the width within which the rank the inner minimum of a
#: two-Ka profile reads at a step can differ between two Ka a rounding error
#: apart (seen at 7e-9 decades).
_STEP_DECADES = 1e-7

#: The rule that names the other constant's bound as what closes an edge: the
#: profile, at the other constant one step of a quarter decade inside its
#: bound, stands above the profile at the edge by more than ``_BOUND_RISE`` of
#: the rise the test allows there. Both numbers are the rule's definition.
_BOUND_STEP_DECADES = 0.25
_BOUND_RISE = 1e-3

#: The reference profile with uncertain inputs: every profile value is the
#: lowest of three Nelder-Mead runs, each restarted where it stopped until it
#: gains less than _RESTART_GAIN, eight orders below the acceptance excess (3
#: to 6 at 12 to 30 points).
_STARTS = 3
_NELDER_MEAD = {'xatol': 1e-8, 'fatol': 1e-10, 'maxiter': 4000, 'maxfev': 4000, 'adaptive': True}
_RESTART_GAIN = 1e-8

#: Local minima of the full two-Ka grid the best fit of a model with two free
#: Ka is polished from in both constants at once, by the same restarted
#: Nelder-Mead: the lowest eight. From these the polish reached the minimum an
#: exhaustive 20/decade search finds on every stepwise titration where the
#: refined profile of one Ka stopped in a higher basin.
_PAIR_STARTS = 8

#: Distance, in decades of Ka, within which a coefficient the best fit leaves
#: inside its bounds must reach one along a Ka off an end for the minimum to be
#: tried with it held there: the reach of the rule of both fit engines,
#: :data:`core.pipeline.varpro._FACE_REACH`.
_FACE_REACH = 1e-3

#: Settings of the least-squares polish of a minimum with a coefficient held on
#: its bound: steps of 1e-12 decades and relative changes of 1e-15, the
#: arithmetic of the residual, with a characteristic step of a tenth of a decade.
_POLISH = dict(x_scale=0.1, xtol=1e-12, ftol=1e-15, gtol=1e-15)

#: Residual of every point where the model has no solution, for the polish:
#: any value far above the signal places such a Ka outside the minimum.
_UNSOLVED_RESIDUAL = 1e100

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

#: Distance from a bound, as a fraction of the signal's weighted variation about
#: its weighted mean, below which a coefficient counts as held on that bound
#: rather than fitted. Read in the norm-scaled variables the bounded solve works
#: in, so it is the change the coefficient could still make to the fitted curve,
#: and measured against the variation rather than the length of the signal, so
#: a constant background under it leaves the reading as it is. The solve puts a
#: held coefficient exactly on its bound, so the reading only has to separate
#: zero from the scatter a fitted coefficient keeps.
_ON_BOUND_RTOL = 1e-8

#: Resolution of R²: a residual sum of squares higher by less than this fraction of
#: the signal's weighted variation is the same fit. A Ka rests on the end of its box
#: wherever the profile there is no higher than at the best fit by more than that.
_R2_RESOLUTION = 1e-10

#: Distance from an end of the Ka box, in decades, within which the reference's
#: best fit counts as resting on that end. An end node the refinement cannot
#: beat is kept exactly, and the bounded Brent refinement comes to within
#: about 3e-9 decades of an end it runs to (``_REFINE_XATOL`` plus the
#: solver's relative tolerance on an offset of at most one node spacing);
#: 1e-4 decades is a margin of over four orders on that, for an objective
#: that is flat towards the end, and far below any distance an optimum inside
#: a box of twenty decades is found at.
_ON_BOX_DECADES = 1e-4

#: Distance from an end of its range, as a fraction of the range's width,
#: within which an input stated as a range counts as resting on that end:
#: a hundred times the Nelder-Mead tolerance on the coordinate, whose range is
#: two units wide, and the bounded simplex puts an input it runs to an end
#: exactly on it.
_ON_EDGE = 1e-6

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


def _axis(ends: tuple[float, float], per_decade: int) -> np.ndarray:
    """Log-spaced Ka from one end to the other, at least *per_decade* points per decade."""
    return np.geomspace(*ends, int(np.ceil(np.log10(ends[1] / ends[0]) * per_decade)) + 1)


def _to_end(ka: float, bounds: tuple[float, float]) -> tuple[float, float]:
    """The end of the Ka box nearer *ka* in decades, and how many decades from it *ka* lies."""
    below, above = np.log10(ka / bounds[0]), np.log10(bounds[1] / ka)
    return (bounds[0], below) if below <= above else (bounds[1], above)


def _on_box(ka: float, bounds: tuple[float, float]) -> bool:
    """Whether *ka* rests on an end of its box, to ``_ON_BOX_DECADES``."""
    return bool(min(np.log10(ka / bounds[0]), np.log10(bounds[1] / ka)) <= _ON_BOX_DECADES)


def _refine(fn: Callable[[float], float], grid: np.ndarray, on_grid: np.ndarray) -> tuple[float, float]:
    """Minimum of *fn* in log Ka, refined between the neighbours of every local minimum of the grid: ``(Ka, value)``.

    A valley narrower than a grid cell reads high at its nearest node and can
    lose the lowest node to a broader valley decades away, so each local
    minimum is refined and the lowest result kept, never worse than the best
    node. A node is a local minimum where it lies below its left neighbour and
    not above its right one by more than ``_TIE_ULPS`` units in its last
    place, so a flat stretch, wiggles of rounding included, is refined once,
    from its left end; the lowest node is always refined.
    """
    pad = np.pad(on_grid, 1, constant_values=np.inf)
    tie = _TIE_ULPS * np.spacing(np.abs(on_grid))
    lowest = int(np.argmin(on_grid))
    best = (float(grid[lowest]), float(on_grid[lowest]))
    minima = np.flatnonzero((on_grid < pad[:-2] - tie) & (on_grid <= pad[2:] + tie))
    for i in np.union1d(minima, [lowest]):
        centre = np.log10(grid[i])
        lo, hi = np.log10(grid[max(i - 1, 0)]) - centre, np.log10(grid[min(i + 1, grid.size - 1)]) - centre
        res = minimize_scalar(
            lambda u: fn(10.0 ** (centre + u)), bounds=(lo, hi), method='bounded', options={'xatol': _REFINE_XATOL}
        )
        if res.fun < best[1]:
            best = (float(10.0 ** (centre + res.x)), float(res.fun))
    return best


def reference_intervals(
    assay: BaseAssay,
    signals: np.ndarray,
    errors: ErrorModel,
    seed: int,
    stream: str,
    weights: np.ndarray | None = None,
    inflation: Mapping[str, float] | None = None,
) -> dict[str, tuple[float, float]] | None:
    """95 % interval per free Ka, computed from the model's species by machinery of its own.

    Every row of *signals* is an observation: one coefficient set is fitted to
    all ``N = m·n`` points at each Ka. Handed the average of the replicates it
    answers the engine's own question, and handed every replicate's points it
    answers the alternative the averaging is measured against.

    The profile is ``P(k) = min [N log S_w + z'z]``, the minimum over the other
    free Ka and over the offsets of the inputs *errors* states, ``z`` the offsets
    stated with a standard deviation in units of it, and the interval holds the
    Ka with ``P(k) - P_min <= N log(1 + kappa m F(0.95; m, nu) / nu)``,
    ``kappa`` the factor *inflation* names for that Ka.

    The numerator of a model with one binding constant is the tested Ka:
    ``m = 1``, the plain F test. The numerator of a model with two counts the
    parameters the best fit has and the fit at ``k`` has not: the tested Ka,
    and every signal parameter the best fit fits while the bounded solve at
    ``k`` holds it on a bound, since a coefficient on a bound is not fitted.
    With ``r(k)`` the rank of the columns whose coefficient the reference's own
    solve leaves strictly inside its bounds at ``k``, and ``k_hat`` the best
    fit,

        m = 1 + max(0, r(k_hat) - r(k))

    so the cut-off of a two-Ka profile is a step function of ``k``: the
    constant cut-off of the plain F test wherever the profile gives no signal
    parameter up, one step higher wherever it gives one up. Every edge and every accepted point is
    judged against the cut-off its own fitted rank names. The step can open a
    stretch the test accepts between two nodes it rejects, so every grid cell
    outside the accepted nodes is profiled again at ``_DENSE_PER_DECADE``
    where its two nodes differ in fitted rank, or where the profile at a node
    is at or below the cut-off of one rank less than the nodes': there a rank
    that dips between the nodes would accept a Ka. Every rank step between two
    neighbouring Ka read outside the accepted ones is then located by
    bisection to ``_STEP_DECADES`` and the profile judged on both sides of it,
    so a stretch that begins at the step is read however narrow it is. The
    interval is the envelope of every Ka read that the test accepts, its edges
    root-found between the outermost of them and the nearest Ka read beyond.

    The second constant of a stepwise model, the second binding constant in
    the registry's order, is open below at its lower bound unless the data
    reject the model without the second step: with ``P(0)`` the profile at
    that constant equal to zero and ``m₀`` the constant plus the coefficients
    the fit there holds on a bound and the best fit does not,
    ``sf((exp((P(0) - P_min) / N) - 1) nu / (kappa m₀); m₀, nu)`` at or below
    :data:`~core.pipeline.varpro.SECOND_STEP_LEVEL`. A lower edge the other
    constant's bound sets is open already and stays where it is.

    ``S_w`` is the weighted residual sum of squares ``sum w_i (y_i - f_i)²``:
    the target and the free columns are multiplied by ``sqrt(w)`` before the
    columns are norm-scaled and the coefficients solved, so the objective, the
    threshold and ``nu`` keep their form — the ``sum log w`` term of the log
    likelihood is the same at every Ka.

    ``p`` counts what the best fit placed itself: the free Ka it leaves off
    the ends of the box (``_ON_BOX_DECADES``), ``r(k_hat)``, and every input
    stated as a range it leaves off the ends of that range (``_ON_EDGE``). A
    parameter held on an end takes no dimension from the residual. A Ka is
    first put on the end of its box nearer it wherever the profile there, a Ka
    put on an end before it held there, exceeds the lowest objective found,
    ``P_min`` or a lower one a Ka put on an end reached, by no more than
    ``N log(1 + _R2_RESOLUTION variation² / S_w)``: a residual higher by less
    than the resolution of R² is the same fit.

    With no uncertain input the minimum over a second Ka is a scan of it — its
    row of the SSR grid at a node, at ``_DENSE_PER_DECADE`` anywhere else —
    refined by Brent from every local minimum of the scan, the best fit
    of two free Ka is then polished in both by Nelder-Mead from the lowest
    ``_PAIR_STARTS`` local minima of the full grid, and ``nu = N - p``: the F
    test on the SSR. With
    uncertain inputs it is Nelder-Mead over (the other Ka, the offsets) from
    ``_STARTS`` start points drawn from *stream* and the seed, each run
    restarted where it stopped until it gains nothing, and
    ``nu = N - p - sum w``, ``w`` the eigenvalues of ``I - [H⁻¹]_zz`` from a
    central-difference Jacobian of ``[r / s ; z]`` at the optimum,
    ``s² = S_w / N``, over the Ka and the inputs ``p`` counts.

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
    inflation : Mapping[str, float], optional
        Factor the cut-off of each free Ka is widened by; 1 for a Ka it does
        not name, and for every Ka when omitted.

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
    point_weights = np.ones(n) if weights is None else np.tile(np.asarray(weights, dtype=float), m)
    root = None if weights is None else np.sqrt(point_weights)
    # The signal's weighted variation about its weighted mean: the scale a coefficient's distance from its bound
    # is read on.
    variation = float(np.sqrt(np.sum(point_weights * (stacked - np.average(stacked, weights=point_weights)) ** 2)))
    free_ka = [k for k in ka_keys if bounds[k][0] != bounds[k][1]]
    axes = {k: _axis(bounds[k], _PER_DECADE) for k in free_ka}
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
        signal's weighted variation separates. A rank of those columns and not a count of
        them, because a mass balance ties columns together and the solve then
        holds one member of a family any member of which could have been the
        one left free.
        """
        solved = bounded(ka, coords)
        if solved is None:
            return 0
        columns, _, scale, x, _ = solved
        margin = np.minimum(x - lb[~pinned] * scale, ub[~pinned] * scale - x)
        inside = margin > _ON_BOUND_RTOL * variation
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

    def profile(
        key: str, value: float, held: Mapping[str, float] | None = None
    ) -> tuple[float, dict[str, float], np.ndarray]:
        """Lowest objective at ``key = value``, the Ka pair and the input coordinates reaching it.

        A free Ka in *held* is held at the value it names as well.
        """
        fixed = {key: value, **(held or {})}
        others = [k for k in free_ka if k not in fixed]
        if not others and not input_keys:
            return objective(fixed), fixed, entered_coords
        start_other = []
        if others:
            other = others[0]
            # The nearest node, the lower bound's for the zero the one-step pretest profiles at.
            i = int(np.argmin(np.abs(np.log10(axes[key]) - np.log10(np.clip(value, *bounds[key])))))
            on_node = axes[key][i] == value
            if on_node or input_keys:
                inner_axis = axes[other]
                scan = np.take(grid, i, axis=free_ka.index(key))
            else:
                inner_axis = _axis(bounds[other], _DENSE_PER_DECADE)
                scan = np.array([objective({key: value, other: k}) for k in inner_axis])
            if not input_keys:
                best_other, best = _refine(lambda k: objective({key: value, other: k}), inner_axis, scan)
                return best, {key: value, other: best_other}, entered_coords
            start_other = [np.log10(axes[other][int(np.argmin(scan))])]
            other_box = np.log10(bounds[other])

        def fun(v: np.ndarray) -> float:
            ka = {**fixed, **({other: 10.0 ** v[0]} if others else {})}
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
        return found[0], {**fixed, **({other: float(10.0 ** v[0])} if others else {})}, v[len(others) :]

    # Best fit: the profile of the first free Ka, minimised along its axis.
    first = free_ka[0]
    node_points = {first: [profile(first, v) for v in axes[first]]}
    on_first = np.array([point[0] for point in node_points[first]])
    best_ka1, p_min = _refine(lambda k: profile(first, k)[0], axes[first], on_first)
    _, best_ka, best_coords = profile(first, best_ka1)
    if grid is not None and not input_keys:
        # Both Ka at once from the lowest local minima of the full grid: the stepwise models' K1·K2 valley runs
        # across the axes, and along it the profile of one Ka can dip inside a grid cell whose nodes both read high.
        padded = np.pad(grid, 1, constant_values=np.inf)
        rows, cols = grid.shape
        around = np.min(
            [padded[1 + a : rows + 1 + a, 1 + b : cols + 1 + b] for a in (-1, 0, 1) for b in (-1, 0, 1) if a or b],
            axis=0,
        )
        starts = np.argwhere((grid <= around) & np.isfinite(grid))
        box = [tuple(np.log10(bounds[k])) for k in free_ka]

        def pair(v: np.ndarray) -> float:
            return objective({k: 10.0 ** v[j] for j, k in enumerate(free_ka)})

        for index in starts[np.argsort(grid[tuple(starts.T)], kind='stable')[:_PAIR_STARTS]]:
            v = np.log10([axes[k][i] for k, i in zip(free_ka, index)])
            lowest = float(grid[tuple(index)])
            while True:
                res = minimize(pair, v, method='Nelder-Mead', bounds=box, options=_NELDER_MEAD)
                if not res.fun < lowest - _RESTART_GAIN:
                    break
                v, lowest = res.x, float(res.fun)
            if lowest < p_min:
                p_min, best_ka = lowest, {k: float(10.0 ** v[j]) for j, k in enumerate(free_ka)}
    # A Ka rests on the end of its box nearer it wherever the profile there, the Ka put on an end before it held
    # there, is no higher than the lowest objective found, to the resolution of R²: the residual sum of squares at
    # most _R2_RESOLUTION of the signal's variation higher. The nearest first, at any distance from the end.
    lowest = p_min
    resolution = n * float(
        np.log1p(_R2_RESOLUTION * variation**2 / np.exp((lowest - best_coords[is_sigma] @ best_coords[is_sigma]) / n))
    )
    ends: dict[str, float] = {}
    for key in sorted(free_ka, key=lambda k: _to_end(best_ka[k], bounds[k])[1]):
        end = _to_end(best_ka[key], bounds[key])[0]
        if best_ka[key] != end:
            found, ka, coords = profile(key, end, ends)
            if found > lowest + resolution:
                continue
            p_min, best_ka, best_coords = found, ka, coords
            lowest = min(lowest, found)
        ends[key] = end
    best_fitted = fitted_rank(best_ka, best_coords)
    # What the minimum itself holds on a bound. Next to the minimiser the bounded solve can leave a coefficient
    # inside its bounds on one side and on its bound on the other while the objective changes by rounding, so the
    # rank read where the search stopped is a matter of which side it stopped on. A coefficient the solve leaves
    # inside its bounds there, and holds on its nearer bound within _FACE_REACH decades along a Ka off an end, lies
    # on that bound at the minimum wherever the minimum with it held there, every Ka off an end and every input
    # moved again, is no higher than the lowest objective found, to the resolution of R², and the solve with it
    # free holds it there of itself, fitting fewer columns.
    moving = [k for k in free_ka if k not in ends]

    def held_minimum(j: int, value: float) -> tuple[float, dict[str, float], np.ndarray]:
        """Minimum with coefficient *j* held at *value*, from the best fit: objective, Ka and inputs."""
        saved = lb[j], ub[j], pinned[j]
        lb[j] = ub[j] = value
        pinned[j] = True
        try:
            box = [*(tuple(np.log10(bounds[k])) for k in moving), *zip(box_lo, box_hi)]

            def fun(v: np.ndarray) -> float:
                return objective({**best_ka, **{k: 10.0 ** v[i] for i, k in enumerate(moving)}}, v[len(moving) :])

            v = np.array([*np.log10([best_ka[k] for k in moving]), *best_coords])
            lowest_held = fun(v)
            while True:
                res = minimize(fun, v, method='Nelder-Mead', bounds=box, options=_NELDER_MEAD)
                if not res.fun < lowest_held - _RESTART_GAIN:
                    break
                v, lowest_held = res.x, float(res.fun)
            if not input_keys:
                # Located to the arithmetic of the residual: the solve with the coefficient free then reads at the
                # minimiser itself whether it holds the coefficient on its bound.
                low, high = (np.log10([bounds[k][end] for k in moving]) for end in (0, 1))

                def misfit(t: np.ndarray) -> np.ndarray:
                    r = residual({**best_ka, **{k: 10.0 ** t[i] for i, k in enumerate(moving)}}, entered_coords)
                    return np.full(n, _UNSOLVED_RESIDUAL) if r is None else r

                polished = least_squares(misfit, np.clip(v, low, high), bounds=(low, high), **_POLISH).x
                if fun(polished) <= lowest_held:
                    v, lowest_held = polished, fun(polished)
        finally:
            lb[j], ub[j], pinned[j] = saved
        return lowest_held, {**best_ka, **{k: float(10.0 ** v[i]) for i, k in enumerate(moving)}}, v[len(moving) :]

    while moving:
        solved = bounded(best_ka, best_coords)
        if solved is None:
            break
        _, _, scale, x, _ = solved
        free_index = np.flatnonzero(~pinned)
        to_low, to_high = x - lb[~pinned] * scale, ub[~pinned] * scale - x
        margin = np.minimum(to_low, to_high)
        reached = np.zeros(margin.size, dtype=bool)
        for key in moving:
            for factor in (10.0**-_FACE_REACH, 10.0**_FACE_REACH):
                near = bounded({**best_ka, key: float(np.clip(best_ka[key] * factor, *bounds[key]))}, best_coords)
                if near is not None:
                    _, _, near_scale, near_x, _ = near
                    near_margin = np.minimum(near_x - lb[~pinned] * near_scale, ub[~pinned] * near_scale - near_x)
                    reached |= near_margin <= _ON_BOUND_RTOL * variation
        for i in np.argsort(margin, kind='stable'):
            j = int(free_index[i])
            bound = lb[j] if to_low[i] <= to_high[i] else ub[j]
            if not (margin[i] > _ON_BOUND_RTOL * variation and reached[i] and np.isfinite(bound)):
                continue
            found, ka, coords = held_minimum(j, float(bound))
            rank = fitted_rank(ka, coords)
            if found <= lowest + resolution and rank < best_fitted:
                p_min, best_ka, best_coords, best_fitted = found, ka, coords, rank
                lowest = min(lowest, found)
                break
        else:
            break
    # What the best fit placed itself: a Ka off the ends of its box and an input stated as a range off
    # the ends of its range. One held on an end, like a coefficient on its bound, takes no dimension
    # from the residual and moves nothing the Jacobian could read.
    ka_placed = np.array([not _on_box(best_ka[k], bounds[k]) for k in free_ka], dtype=bool)
    input_placed = is_sigma | (np.minimum(best_coords - box_lo, box_hi - best_coords) > _ON_EDGE * (box_hi - box_lo))
    dof = n - int(ka_placed.sum()) - best_fitted - int(np.sum(input_placed & ~is_sigma))
    if is_sigma.any() and dof >= 1:
        # What the data, and not the penalty, determine of each input stated with a standard deviation.
        at = np.array([*(np.log10(best_ka[k]) for k in free_ka), *best_coords])
        s = np.sqrt(np.exp((p_min - np.sum(best_coords[is_sigma] ** 2)) / n) / n)

        def stacked_residual(v: np.ndarray) -> np.ndarray:
            ka = {k: 10.0 ** v[i] for i, k in enumerate(free_ka)}
            return np.concatenate([residual(ka, v[len(free_ka) :]) / s, v[len(free_ka) :][is_sigma]])

        steps = _JACOBIAN_STEP * np.eye(at.size)[np.concatenate([ka_placed, input_placed])]
        jac = np.column_stack(
            [(stacked_residual(at + h) - stacked_residual(at - h)) / (2 * _JACOBIAN_STEP) for h in steps]
        )
        z_columns = int(ka_placed.sum()) + np.flatnonzero(is_sigma[input_placed])
        # (J'J)⁻¹ from the pseudo-inverse of J with unit-length columns: the units of a column do not
        # decide which directions count, and the condition number of J is not squared.
        norms = np.linalg.norm(jac, axis=0)
        norms[norms == 0] = 1.0
        inverse = np.linalg.pinv(jac / norms) / norms[:, np.newaxis]
        covariance = (inverse @ inverse.T)[np.ix_(z_columns, z_columns)]
        dof -= float(np.clip(np.linalg.eigvalsh(np.eye(z_columns.size) - covariance), 0.0, 1.0).sum())
    if dof < 1:
        return None
    cuts: dict[tuple[str, int], float] = {}
    factors = dict(inflation or {})

    def given_up(rank_here: int) -> int:
        """Signal parameters a fit of fitted rank *rank_here* gives up: counted for a model with two Ka only."""
        return max(0, best_fitted - rank_here) if len(ka_keys) == 2 else 0

    def cut_off(key: str, rank_here: int) -> float:
        """Objective a fit of fitted rank *rank_here* is accepted below on the profile of *key*."""
        released = given_up(rank_here)
        if (key, released) not in cuts:
            # m: the tested Ka plus the signal parameters a fit of this rank gives up.
            tested = 1 + released
            kappa = factors.get(key, 1.0)
            cuts[key, released] = p_min + n * float(np.log1p(kappa * tested * f_dist.ppf(LEVEL, tested, dof) / dof))
        return cuts[key, released]

    def judged(key: str, value: float) -> tuple[float, int]:
        """How far the profile at ``key = value`` stands above the cut-off its own fitted rank names, and that rank."""
        found, ka, coords = profile(key, value)
        rank = fitted_rank(ka, coords)
        return found - cut_off(key, rank), rank

    def one_step_rejected() -> bool:
        """Whether the data reject the model without the second binding step at ``SECOND_STEP_LEVEL``."""
        found, ka, coords = profile(second, 0.0)
        tested = 1 + given_up(fitted_rank(ka, coords))
        ratio = float(np.expm1((found - p_min) / n)) * dof / (factors.get(second, 1.0) * tested)
        return bool(f_dist.sf(ratio, tested, dof) <= SECOND_STEP_LEVEL)

    def bound_closes(key: str, edge: float) -> bool:
        """Whether the other free Ka's bound, and not the data, closes the profile of *key* at *edge*."""
        others = [k for k in free_ka if k != key]
        if not others:
            return False
        (other,) = others
        found, ka, coords = profile(key, edge)
        lo, hi = bounds[other]
        if not _on_box(ka[other], (lo, hi)):
            return False
        step = 10.0**_BOUND_STEP_DECADES
        inward = min(lo * step, hi) if np.log10(ka[other] / lo) <= np.log10(hi / ka[other]) else max(hi / step, lo)
        rise = objective({key: edge, other: inward}, coords) - found
        return bool(rise > _BOUND_RISE * (cut_off(key, fitted_rank(ka, coords)) - p_min))

    second = ka_keys[1] if len(ka_keys) == 2 and ka_keys[1] in free_ka else None
    intervals = {}
    for key in free_ka:
        nodes = axes[key]
        points = node_points.get(key) or [profile(key, v) for v in nodes]
        ranks = [fitted_rank(ka, coords) for _, ka, coords in points]
        on_nodes = [point[0] for point in points]
        # Every Ka the profile was read at: its excess over the cut-off of its own fitted rank, and that rank.
        read = {float(v): (value - cut_off(key, rank), rank) for v, value, rank in zip(nodes, on_nodes, ranks)}

        def envelope(key: str = key) -> tuple[float, float]:
            inside = [v for v, (excess, _) in read.items() if excess <= 0.0] + [best_ka[key]]
            return min(inside), max(inside)

        # A cell inside the envelope cannot move it. Outside it, a cell is read again densely where its nodes
        # differ in rank, and where the profile at either node is at or below the cut-off of one rank less than
        # theirs: a rank lower between the nodes would accept a Ka there.
        low_in, high_in = envelope()
        for i in range(nodes.size - 1):
            if low_in <= nodes[i] and nodes[i + 1] <= high_in:
                continue
            lower = min(ranks[i], ranks[i + 1]) - 1
            if ranks[i] != ranks[i + 1] or (lower >= 0 and min(on_nodes[i], on_nodes[i + 1]) <= cut_off(key, lower)):
                for value in _axis((nodes[i], nodes[i + 1]), _DENSE_PER_DECADE)[1:-1]:
                    read[float(value)] = judged(key, value)
        # Every rank step between two neighbouring Ka read outside the envelope is located by bisection to
        # _STEP_DECADES and judged on both sides, so a stretch the step opens is read however narrow it is.
        low_in, high_in = envelope()
        ordered = sorted(read)
        steps = [
            (a, b)
            for a, b in zip(ordered[:-1], ordered[1:])
            if read[a][1] != read[b][1] and not (low_in <= a and b <= high_in)
        ]
        while steps:
            a, b = steps.pop()
            if np.log10(b / a) <= _STEP_DECADES:
                continue
            middle = float(np.sqrt(a * b))
            read[middle] = judged(key, middle)
            steps += [(a, middle)] if read[middle][1] != read[a][1] else []
            steps += [(middle, b)] if read[middle][1] != read[b][1] else []
        values = np.array(sorted(read))
        excesses = np.array([read[v][0] for v in values])
        inside = np.append(values[excesses <= 0.0], best_ka[key])
        low_in, high_in = float(inside.min()), float(inside.max())
        below, above = values[values < low_in], values[values > high_in]

        def edge(outside: float, within: float, key: str = key) -> float:
            # The ends keep the excess they were read with, so the bracket is the one the reading found: next to a
            # rank step, the rank the inner minimum reads can differ between two Ka a rounding error apart.
            ends = {
                t: read[v][0] if v in read else judged(key, v)[0]
                for t, v in zip(np.log10([outside, within]), [outside, within])
            }
            return float(10 ** brentq(lambda t: ends[t] if t in ends else judged(key, 10**t)[0], *ends))

        low = edge(below[-1], low_in) if below.size else float(nodes[0])
        high = edge(above[0], high_in) if above.size else float(nodes[-1])
        if key == second and below.size and not bound_closes(key, low) and not one_step_rejected():
            low = float(nodes[0])
        intervals[key] = (low, high)
    return intervals


def _row(scenario: Scenario, seed: int, pooled: bool) -> dict[str, Any]:
    """One dataset through both computations, with the law its replicates show carried by both.

    The engine's interval is the one the application reports at the entered
    inputs: its fit of the average of the replicates, weighted by that law and
    widened by the factor the law's uncertainty asks for. The reference is
    handed the same average when *pooled* is false and every replicate's
    points when it is true, with the same point weights and the same factor
    either way, so what a pooled row compares is the pooling and not the
    weighting. A pooled row carries a third interval beside them: the engine's
    own fit of the same average with every point counted equally.
    """
    started = time.perf_counter()
    data = dataset(scenario, seed)

    def work() -> dict[str, Any]:
        result = fit_measurement_set(
            measurement_set(data),
            ASSAY_CLASSES[AssayType[scenario.assay]],
            dict(data.conditions),
            FitConfig(per_replica=False, errors=scenario.error_model),
        )
        engine = result.conditional.intervals
        bounds = data.assay.get_default_bounds()
        found = reference_intervals(
            data.assay,
            data.signals if pooled else data.signals.mean(axis=0)[np.newaxis, :],
            scenario.error_model,
            seed,
            scenario.id,
            weights=result.point_weights,
            inflation={key: interval.inflation for key, interval in engine.items()},
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

    Both are computed from the average of the replicates, with the point
    weights and the widening of the fit the application reports.

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
