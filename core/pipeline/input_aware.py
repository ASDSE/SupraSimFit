"""Confidence interval of Ka with the entered inputs as constrained nuisance parameters.

Every projectable model is ``y = A(K, theta) c + e``: K the binding constants,
theta the entered inputs — the concentrations and binding constants among the
assay conditions and the titrant series as one scale factor. Input j is
``theta_j = entered_j (1 + e_j)``, and the user states per input
(:mod:`core.pipeline.inputs`) a standard deviation ``s_j`` of ``e_j``, a range
``e_j`` must stay in, or nothing, which holds the input at its entered value.
An error several inputs have in common is one more such offset, stated with a
standard deviation, and the *loading* of the sources
(:meth:`core.pipeline.inputs.ErrorModel.input_offsets`) gives each input the
product of the ``1 + e`` of the sources that move it. Everything below counts
sources: with no shared one, a source is an input.

With the projected residual sum of squares
``S(K, e) = min over lb <= c <= ub of ||y - A(K, theta(e)) c||²``, Gaussian
noise of unknown variance and the inputs stated with a standard deviation as
pseudo-observations ``z_j = e_j / s_j ~ N(0, 1)``, minus twice the log
likelihood profiled over the noise variance is ``n log S + z'z`` up to a
constant. The penalised profile of one binding constant and its interval are

    P(K_j = k) = min over the other free Ka and e in its box of [n log S(K, e) + z'z]
    interval_j = {k : P(k) - P_min <= n log(1 + kappa_j m F(level; m, nu) / nu)},  nu = n - p - sum_i w_i
    p = what the optimum fitted: the free Ka inside their box, the rank of the signal
        columns inside their bounds (Projection.fitted_parameters) and the inputs
        stated as a range that it left off the ends of theirs
    m = 1 + the signal parameters the optimum fits and the solution at k holds on a bound

``m`` is the numerator of :meth:`core.pipeline.varpro.Projection.cut_off`, read
at each profile point's own solution — its binding constants and its moved
inputs — against the optimum's: a signal parameter on its bound is not fitted,
so a rise to a Ka that pins one gives up that parameter as well as the Ka.
``kappa_j >= 1`` is the design effect of K_j that widens the fixed-input
cut-off as well (:mod:`core.pipeline.inflation`): it accounts for point weights
read off the replicates and for a stated random error of each titrant addition,
which no input offset here represents. It is one unless the caller hands one in.

An input with a range is one more parameter wherever the fit leaves it inside
the range; on an end of it the input is held there. An input with a standard
deviation is a parameter the penalty holds back: it takes up the fraction
``w_i`` of a residual degree of freedom that the data, and not the penalty,
determine (:func:`core.pipeline.diagnostics.conflict_reference`; the sum is the
effective number of parameters of a penalised fit). The noise variance is
profiled from ``S`` alone, so ``nu`` is what is left to judge it by. With no
varying input ``P(k) - P_min`` is ``n log(S(k) / S_min)``, ``nu = n - p``, and
the rule is the F test of :meth:`core.pipeline.varpro.Projection.interval` on
the log scale, with the same ``kappa_j``, so that interval is returned as it
is. Over 2 400 random titrations of 5, 6, 8 and 12 points with unit weights
and no addition error, so ``kappa_j = 1`` (GDA, IDA, both DBA directions, every
input entered at its stated sigma) the 95 % interval holds the true Ka in
98.3, 98.0, 97.5 and 96.3 %; with ``n - p`` in place of ``nu`` it is 85 to 93 %
wherever the data determine an input direction.

The second constant of a stepwise model is judged, as in
:meth:`core.pipeline.varpro.Projection.interval`, by a one-step test before its
interval claims a lower limit: ``P(0)`` with that constant at zero, minimised
over the other one and the inputs, against ``P_min`` by the rule above with
that constant's ``kappa``, so the input-aware interval and the fixed-input one
agree on what the data say about the second binding step.

``exp(P(k) / n)`` is a residual sum of squares inflated by the input penalty,
so ``1 - exp(P(k) / n) / SS_tot`` draws on the R² axis of the fixed-input
profile, never below it wherever the entered inputs are allowed.

The interval is cut from the penalised profile by the routine that cuts the
fixed-input one (:func:`core.pipeline.varpro._cut_interval`), the objective and
its cut-off by rank handed in: the same reading of the profile wherever the
test can accept Ka between the points read and on both sides of every step of
its cut-off, the same root finding of the edges, split and open sides, and the
same rule for an edge that only the bound of the other binding constant closes
(:meth:`core.pipeline.varpro.Projection._bound_behind`). What differs follows
from the objective: a point of the penalised profile is a bounded optimisation
over the inputs, so the search-grid nodes are traced outward from the estimate
rather than all solved, and each point is solved from its neighbours.

Every profile value is a pure function of the Ka it is asked at and of the
start points it is solved from, and the start points come only from the table
of solved search-grid nodes, the estimate and, with two free Ka, where the other
one minimises the fixed-input objective — never from the previous evaluation —
so root finding cannot change a value by the order it asks in.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Callable, Mapping, Sequence

import numpy as np
from scipy.optimize import least_squares

from core.pipeline.diagnostics import Conflict, InputShift, conflict_added, conflict_reference, conflict_test
from core.pipeline.inputs import InputConstraint
from core.pipeline.varpro import (
    _INNER_PER_DECADE,
    _PROFILE_PER_DECADE,
    _R2_RESOLUTION,
    _SEARCH_PER_DECADE,
    LEVEL,
    FitCancelled,
    FitRefused,
    FittedParameters,
    KaInterval,
    ProjectedFit,
    Projection,
    _allowed_rise,
    _cut_interval,
    _ka_grid,
    _refine_at,
    _require_dof,
    _require_inflation,
    _rest_coefficients,
    _rest_on_bounds,
    _rise_p,
    _with_one_step_test,
    on_ka_bound,
)

__all__ = [
    'LEVEL',
    'AwareFit',
    'AwareProfile',
    'AwareResult',
    'conflict',
    'fit_jacobian',
    'input_aware',
    'input_shifts',
    'misfit_design',
]

# Cost, one process per core with the default Ka bounds: a residual evaluation
# is one moved copy of the assay (30 us), one species solve (65 us) and one
# bounded linear solve (16 to 400 us), and an interval takes thousands of them.
# Over 60 random titrations with every input at 3 %, the input-aware part takes
# median / 90th percentile / maximum 0.8 / 1.5 / 1.8 s with one Ka (20
# titrations) and 5.2 / 7.4 / 24 s with two Ka and two inputs (40), beside 0.05 s
# and 3 to 5 s for the fixed-input fit and intervals. By assay, the one-Ka median
# is about 2.5 s for IDA (four inputs), 1.3 s for GDA (four) and 0.6 to 0.7 s for
# DBA (two); the hardest designs with few points take about 25 s with one Ka and
# 50 s with two.
# The slowest fits are those whose profile edge lies where a signal parameter
# reaches its bound: the objective has a kink there, along which the
# least-squares solver creeps to a value good to 1e-4 instead of 1e-9.

# The inner problem at a fixed noise scale s is least squares on [r / s ; z];
# its minimum is the profile value only at the fixed point s² = S / n, found by
# iterating on u = log s² until g(u) = log(S / n) - u is below _SCALE_TOL. The
# profile value is stationary in the solution, so an error d in the scale moves
# it by O(d²): it is converged to 1e-9 at |g| = 1e-6, and a tighter tolerance
# only chases the least-squares solver's own stopping noise (3e-7 in g). The
# iteration takes 2 to 6 steps (maximum 8 over 300 random IDA datasets);
# _SCALE_MAXITER is a cap far above that.
_SCALE_TOL = 1e-6
_SCALE_MAXITER = 30

# Stopping rules of the inner least-squares solve: steps of 1e-9 of a coordinate
# of size one, relative cost changes of 1e-10 and gradients of 1e-9, the settings
# the agreement of the trace with a full scan (3.5e-11 decades on every edge of
# 60 random IDA designs) was measured with.
_LS_TOL = {'xtol': 1e-9, 'ftol': 1e-10, 'gtol': 1e-9}

# Characteristic step of a coordinate in the inner solve: 0.1 decade for a
# binding constant, the value of the two-Ka search; an input coordinate is its
# offset in units of its standard deviation (or of half its range) and has
# scale one.
_KA_XSCALE = 0.1

# Multiples of the acceptance excess n log(1 + kappa F / nu) above the running
# minimum at which the node-by-node trace of a profile stops. A node that far
# out re-enters the interval only if a lower minimum lies beyond it, which the
# coarse sweep looks for.
_STOP_EXCESS = 2

# Step of the coarse sweep from the end of the traced stretch to the Ka bound,
# in search-grid nodes: one node per decade at the search density of 4 per
# decade. A second accepted stretch of Ka narrower than one decade and more
# than _STOP_EXCESS acceptance excesses beyond the traced stretch is not
# detected; the fixed-input profile, scanned at 20 per decade, still reports a
# split of its own.
_COARSE_STEP = 4

# Distance from an end of its range, as a fraction of the range's width, within
# which an input stated as a range is reported as resting on that end: three
# orders above the solver's step tolerance on the scaled coordinate, three below
# anything a percentage display shows.
_EDGE_TOL = 1e-6

# Resolution of the objective: the scale iteration converges a profile value to
# 1e-9, so a point lower than the optimum by less than that is the same optimum.
_P_RESOLUTION = 1e-9

# Passes over the edges and the drawn curve. A pass that finds a point below
# the optimum moves the estimate there and lowers the threshold, so the edges
# are closed again; every value is a pure function of its Ka and the node
# table, so the pass after that finds nothing new.
_MAX_PASSES = 4


@dataclass(frozen=True)
class AwareFit:
    """The fit with the varying inputs free to move within their stated uncertainties.

    Attributes
    ----------
    ka : dict[str, float]
        Every binding constant in 1/M, pinned ones at their value.
    offsets : dict[str, float]
        Fitted relative offset of every varying source, by constraint key;
        empty when nothing varies.
    input_offsets : dict[str, float]
        Where those offsets put the inputs, as a fraction of each entered
        value and by input key: what ``Projection`` and
        ``BaseAssay.with_inputs`` take. The same floats as *offsets* when no
        source is shared.
    coefficients : np.ndarray
        Signal parameters at ``(ka, input_offsets)`` in ``Projection.coef_keys`` order.
    ssr : float
        Residual sum of squares at ``(ka, input_offsets)``.
    objective : float
        ``P_min = n log(ssr) + z'z``, the residual floored at the resolution of R².
    n_params : int
        ``p`` of every test of this fit: what it fitted — the free binding
        constants strictly inside their box, the rank of the signal columns
        strictly inside their bounds
        (:meth:`~core.pipeline.varpro.Projection.fitted_parameters`) and the
        inputs stated as a range that it left off the ends of theirs
        (:func:`at_edge`). A parameter held on a bound takes no dimension from
        the residual.
    jacobian : np.ndarray
        Jacobian at the optimum of the residual (signal units) followed by the
        penalty rows, over *ka_free* (log10) then *constraint_keys* (the offset
        in units of its standard deviation, or of half its range).
    ka_free : tuple[str, ...]
        The binding constants the fit was free to move.
    constraint_keys : tuple[str, ...]
        The varying inputs.
    ka_fitted : tuple[str, ...]
        Those of *ka_free* the fit left strictly inside their box; one on a
        bound of it is held there and not fitted.
    """

    ka: dict[str, float]
    offsets: dict[str, float]
    input_offsets: dict[str, float]
    coefficients: np.ndarray
    ssr: float
    objective: float
    n_params: int
    jacobian: np.ndarray
    ka_free: tuple[str, ...]
    constraint_keys: tuple[str, ...]
    ka_fitted: tuple[str, ...]


@dataclass(frozen=True)
class AwareProfile:
    """Penalised profile of one binding constant and the interval cut from it.

    Attributes
    ----------
    ka_key : str
    grid : np.ndarray
        Ka in 1/M, ascending: the solved search-grid nodes, the points read at
        ``_PROFILE_PER_DECADE`` where the verdict of the test turns, the
        estimate, the closed edges and a fill at that density through the
        search cells of the estimate and of each closed edge.
    objective : np.ndarray
        ``P`` on *grid*; infinite where the model has no solution.
    r2 : np.ndarray
        ``1 - exp(P / n) / SS_tot`` on *grid*; not a number where unsolvable.
    offsets : np.ndarray
        Fitted offset of every constraint per grid point, shape ``(len(grid), constraints)``.
    threshold : float
        ``P_min`` plus the acceptance excess of a solution that holds no
        parameter on a bound that the optimum fits (``m = 1``), widened by
        the interval's design effect (``KaInterval.inflation``).
    r2_threshold : float
        *threshold* on the R² axis.
    interval : KaInterval
    other_ka : np.ndarray or None
        The other free binding constant per grid point, where the model has two.
    cut : np.ndarray
        ``P_min`` plus the acceptance excess of each grid point's own solution:
        *threshold*, and higher over every stretch where that solution holds
        a parameter on a bound that the optimum leaves free.
        *threshold* at every point when left out.
    r2_cut : np.ndarray
        *cut* on the R² axis.
    """

    ka_key: str
    grid: np.ndarray
    objective: np.ndarray
    r2: np.ndarray
    offsets: np.ndarray
    threshold: float
    r2_threshold: float
    interval: KaInterval
    other_ka: np.ndarray | None = None
    cut: np.ndarray | None = None
    r2_cut: np.ndarray | None = None

    def __post_init__(self) -> None:
        if self.cut is None:
            object.__setattr__(self, 'cut', np.full(self.grid.shape, self.threshold))
        if self.r2_cut is None:
            object.__setattr__(self, 'r2_cut', np.full(self.grid.shape, self.r2_threshold))


@dataclass(frozen=True)
class AwareResult:
    """The input-aware fit, the profile of every free binding constant and what they were computed from."""

    fit: AwareFit
    profiles: dict[str, AwareProfile]
    constraints: tuple[InputConstraint, ...]
    n_points: int
    ss_tot: float


@dataclass(frozen=True)
class _Point:
    """One solved inner problem: the objective, where it lies, its residual sum of squares and what it fitted."""

    value: float
    ka: dict[str, float]  # every free Ka
    coords: np.ndarray  # input offsets in units of their standard deviation or half range
    ssr: float
    fitted: FittedParameters | None = None  # Projection.fitted_parameters at (ka, coords); None for a start

    @property
    def rank(self) -> int:
        """Rank of the signal columns the solve here leaves inside their bounds; zero for a start."""
        return 0 if self.fitted is None else self.fitted.rank


class _Problem:
    """The penalised objective of one single-row projection and its inner solve."""

    def __init__(
        self,
        projection: Projection,
        constraints: Sequence[InputConstraint],
        should_cancel: Callable[[], bool] | None = None,
        loading: Callable[[Mapping[str, float]], dict[str, float]] | None = None,
    ):
        projection._require_one_row('An interval with uncertain inputs')
        self.projection = projection
        self.constraints = tuple(constraints)
        self._loading = loading
        self.n = projection.n_points
        self.keys = tuple(c.key for c in self.constraints)
        self.is_sigma = np.array([c.sigma is not None for c in self.constraints], dtype=bool)
        self.unit = np.array([c.sigma if c.sigma is not None else 0.5 * (c.hi - c.lo) for c in self.constraints])
        self.lo = np.array([c.lo for c in self.constraints]) / self.unit
        self.hi = np.array([c.hi for c in self.constraints]) / self.unit
        self.floor = _R2_RESOLUTION * float(projection.ss_tot[0])
        # Residual the least-squares solver is given where the model has no solution: that of a
        # fit by the mean alone, finite so that the solver's differences stay finite and as poor
        # as a fit without a binding model, so that a step into such a region is turned down. A
        # solve that ends there is reported unsolvable. It is whitened like every other residual
        # the projection hands out, by the point weights and about the mean they weight.
        weights = projection.point_weights
        signal = projection.signals[0]
        self._no_model = np.sqrt(weights) * (signal - np.average(signal, weights=weights))
        self._should_cancel = should_cancel

    def start_coords(self) -> np.ndarray:
        """The entered inputs, or the nearest point of a range that leaves them out."""
        return np.clip(np.zeros(len(self.constraints)), self.lo, self.hi)

    def offsets(self, coords: np.ndarray) -> dict[str, float]:
        """Relative offset per constraint key."""
        return {key: float(e) for key, e in zip(self.keys, coords * self.unit)}

    def input_offsets(self, coords: np.ndarray) -> dict[str, float]:
        """Relative offset per input key, which is what the projection takes."""
        offsets = self.offsets(coords)
        return offsets if self._loading is None else self._loading(offsets)

    def unsolvable(self, ka: Mapping[str, float]) -> _Point:
        return _Point(np.inf, dict(ka), self.start_coords(), np.inf)

    def _stacked(self, fixed: Mapping[str, float], moving: Sequence[str]) -> Callable[[np.ndarray, float], np.ndarray]:
        """``[r / s ; z]`` as a function of (log10 of the *moving* Ka, the input coordinates) and the scale ``s``."""
        m = len(moving)

        def stacked(v: np.ndarray, s: float) -> np.ndarray:
            r = self._residual(fixed, moving, v)
            if not np.isfinite(r[0]):
                stacked.left_the_model = True
                r = self._no_model
            return np.concatenate([r / s, v[m:][self.is_sigma]])

        stacked.left_the_model = False
        return stacked

    def _residual(self, fixed: Mapping[str, float], moving: Sequence[str], v: np.ndarray) -> np.ndarray:
        ka = {**fixed, **{key: 10.0 ** v[i] for i, key in enumerate(moving)}}
        return self.projection.residual(ka, 0, self.input_offsets(v[len(moving) :]))

    def _box(self, moving: Sequence[str]) -> tuple[tuple[np.ndarray, np.ndarray], np.ndarray]:
        ka_box = np.log10([self.projection.ka_bounds[key] for key in moving]).reshape(len(moving), 2)
        bounds = (np.concatenate([ka_box[:, 0], self.lo]), np.concatenate([ka_box[:, 1], self.hi]))
        return bounds, np.concatenate([np.full(len(moving), _KA_XSCALE), np.ones(len(self.constraints))])

    def solve(self, fixed: Mapping[str, float], start: _Point) -> _Point:
        """Minimum of ``n log S + z'z`` at the *fixed* binding constants, from one start.

        The other free binding constants and the inputs move (:meth:`_minimum`),
        and a moving binding constant rests on its bound where the objective
        there is no higher (:meth:`rest`).
        """
        point = self._minimum(fixed, start)
        return self.rest(point, [key for key in self.projection.free_ka if key not in fixed], fixed)

    def rest(self, point: _Point, moving: Sequence[str], fixed: Mapping[str, float] | None = None) -> _Point:
        """*point*, or its solution with constants of *moving* on their bounds where the objective there is no higher.

        The rule of the fixed-input fit (:func:`~core.pipeline.varpro._rest_on_bounds`)
        on the penalised objective: a constant is held on its nearer bound —
        every other moving constant and the inputs left where they are or
        solved again from the point tried — and the move stands where
        ``n log S + z'z`` is no higher than at *point* plus
        ``n log(1 + floor / S)``, the rise of a residual sum of squares by the
        resolution of R², ``floor``.
        """
        fixed = fixed or {}

        def held(start: _Point, pinned: dict[str, float], again: bool) -> tuple[_Point, dict[str, float], float]:
            solved = self._minimum({**fixed, **pinned}, start) if again else self._at({**start.ka, **pinned}, start)
            return solved, solved.ka, solved.value

        resolution = self.n * float(np.log1p(self.floor / max(point.ssr, self.floor)))
        return _rest_on_bounds(point, point.ka, point.value, moving, self.projection.ka_bounds, held, resolution)

    def rest_coefficients(self, point: _Point) -> _Point:
        """*point*, or the minimiser next to it where that holds a signal coefficient on its bound.

        The rule of the fixed-input fit (:func:`~core.pipeline.varpro._rest_coefficients`)
        on the penalised objective: a coefficient is held on its bound, the
        binding constants inside their box and the inputs solved again from
        *point*, and the solution stands where ``n log S + z'z`` is no higher
        than at *point* plus the resolution :meth:`rest` allows and the
        bounded solve there, at its own inputs, fits fewer columns.
        """
        projection = self.projection

        def held(start: _Point, k: int, bound: float) -> tuple[_Point, float, int]:
            holding = _Problem(projection._holding(k, bound), self.constraints, self._should_cancel, self._loading)
            on_bound = {key: value for key, value in start.ka.items() if on_ka_bound(value, projection.ka_bounds[key])}
            moved = holding._minimum(on_bound, start)
            if not np.isfinite(moved.value):
                return moved, np.inf, 0
            solved = self._at(moved.ka, moved)
            return solved, solved.value, solved.rank

        resolution = self.n * float(np.log1p(self.floor / max(point.ssr, self.floor)))
        return _rest_coefficients(
            point,
            point.value,
            lambda found: projection._coefficient_trials(found.ka, self.input_offsets(found.coords)),
            held,
            resolution,
        )

    def _at(self, ka: Mapping[str, float], start: _Point) -> _Point:
        """The objective at the free binding constants *ka* with the inputs where *start* has them, from one solve."""
        ssr, fitted = self.projection.solved(ka, self.input_offsets(start.coords))
        if not np.isfinite(ssr[0]):
            return self.unsolvable(ka)
        value = self.n * float(np.log(max(ssr[0], self.floor))) + float(np.sum(start.coords[self.is_sigma] ** 2))
        return _Point(value, dict(ka), start.coords, float(ssr[0]), fitted)

    def _minimum(self, fixed: Mapping[str, float], start: _Point) -> _Point:
        """Minimum of ``n log S + z'z`` at the *fixed* binding constants from one start, wherever the solver stops.

        The other free binding constants and the inputs move. Trust-region
        least squares on ``[r / s ; z]`` minimises ``S / s² + z'z``, which has
        the minimiser of the objective exactly where ``s² = S / n``. That fixed
        point is found on ``g(u) = log(S / n) - u``, ``u = log s²``, each step
        one solve started from the last. ``g`` falls in ``u`` with a slope
        between -1 and -0.5 (log S rises at most half as fast as u), so the sign
        of g brackets the root, and a secant step is taken only inside the
        bracket and clipped to between one and two Picard steps ``u + g``; the
        Picard step otherwise, or the bracket's midpoint when that would leave
        it. An unclipped secant on a one-sided bracket ran the scale to 1e-160
        on 1 dataset in 300. The scale starts at the start point's own
        ``S / n``: a scale taken over from a better-fitting neighbour starts
        the solve far from its fixed point and lands it in another basin
        (objective 3 to 25 higher at every node on the far side of the optimum).
        """
        if self._should_cancel is not None and self._should_cancel():
            raise FitCancelled('The fit was stopped.')
        moving = [key for key in self.projection.free_ka if key not in fixed]
        stacked = self._stacked(fixed, moving)
        bounds, x_scale = self._box(moving)
        m = len(moving)
        x = np.clip(np.concatenate([np.log10([start.ka[key] for key in moving]), start.coords]), *bounds)
        r = self._residual(fixed, moving, x)
        if not np.isfinite(r[0]):
            return self.unsolvable({**fixed, **{key: start.ka[key] for key in moving}})
        ssr = float(r @ r)
        u = float(np.log(max(ssr, self.floor) / self.n))
        low, high = -np.inf, np.inf  # g(low) > 0 > g(high)
        u_last = g_last = None
        for _ in range(_SCALE_MAXITER):
            s = float(np.exp(0.5 * u))
            if x.size:
                solved = least_squares(stacked, x, args=(s,), bounds=bounds, x_scale=x_scale, method='trf', **_LS_TOL)
                x, r = solved.x, solved.fun[: self.n] * s
                ssr = float(r @ r)
            g = float(np.log(max(ssr, self.floor) / self.n)) - u
            if abs(g) <= _SCALE_TOL:
                break
            low, high = (max(low, u), high) if g > 0 else (low, min(high, u))
            if high - low <= _SCALE_TOL:
                break
            step = None
            if u_last is not None and g != g_last:
                secant = -g * (u - u_last) / (g - g_last)
                candidate = u + g * float(np.clip(secant / g, 1.0, 2.0))
                step = candidate if low < candidate < high else None
            if step is None:
                step = u + g if low < u + g < high else 0.5 * (low + high)
            u_last, g_last, u = u, g, step
        if stacked.left_the_model and not np.isfinite(self._residual(fixed, moving, x)[0]):
            return self.unsolvable({**fixed, **{key: start.ka[key] for key in moving}})
        coords = x[m:]
        value = self.n * float(np.log(max(ssr, self.floor))) + float(np.sum(coords[self.is_sigma] ** 2))
        ka = {**fixed, **{key: float(10.0 ** x[i]) for i, key in enumerate(moving)}}
        fitted = self.projection.fitted_parameters(ka, self.input_offsets(coords))
        return _Point(value, {key: ka[key] for key in self.projection.free_ka}, coords, ssr, fitted)

    def count(self, point: _Point) -> int:
        """Parameters *point* fitted: its ``p``.

        What its signal solve fitted (:attr:`FittedParameters.count`) and every
        input stated as a range that it left off the ends of that range
        (:func:`at_edge`).
        """
        offsets = self.offsets(point.coords)
        ranges = sum(c.sigma is None and not at_edge(c, offsets[c.key]) for c in self.constraints)
        return point.fitted.count + ranges

    def jacobian(self, point: _Point) -> np.ndarray:
        """Jacobian of ``[r ; z]`` at *point* over every free Ka (log10) and every input coordinate.

        The two-point differences of the least-squares solver, which keep
        their steps inside the bounds, read off a solve that is allowed its
        first evaluation only.
        """
        moving = list(self.projection.free_ka)
        bounds, x_scale = self._box(moving)
        x = np.clip(np.concatenate([np.log10([point.ka[key] for key in moving]), point.coords]), *bounds)
        if not x.size:
            return np.empty((self.n, 0))
        return least_squares(
            self._stacked({}, moving), x, args=(1.0,), bounds=bounds, x_scale=x_scale, method='trf', max_nfev=1
        ).jac


class _Trace:
    """Penalised profile of one binding constant on the search-grid nodes of its bounds."""

    def __init__(self, problem: _Problem, ka_key: str, consider: Callable[[_Point], _Point]):
        self.problem = problem
        self.key = ka_key
        projection = problem.projection
        self.nodes = projection._grid()[0][projection.free_ka.index(ka_key)]
        self.two_ka = len(projection.free_ka) == 2
        self.table: dict[int, _Point] = {}
        self._consider = consider

    def at(self, ka: float, starts: Sequence[_Point]) -> _Point:
        """The lowest solve at ``ka_key = ka`` over *starts*."""
        found = [self.problem.solve({self.key: ka}, start) for start in starts]
        return self._consider(min(found, key=lambda point: point.value))

    def entered(self, ka: float, coords: np.ndarray | None = None) -> _Point:
        """A start at *coords* (the entered inputs when omitted), the other Ka where the fixed-input objective is lowest."""
        other = self.problem.projection.inner_start(self.key, ka)
        return _Point(
            np.nan, {self.key: ka, **other}, self.problem.start_coords() if coords is None else coords, np.nan
        )

    def _node(self, i: int, starts: Sequence[_Point]) -> None:
        """Solve node *i* from *starts* and keep the lower of that and what the table holds.

        With two free Ka a node is also started where the other Ka minimises
        the fixed-input objective there, at the first start's inputs: the
        profile of a stepwise model moves from one K₁·K₂ valley to another, and
        a solve continued from the neighbouring node stays in the valley it
        came from.
        """
        ka = float(self.nodes[i])
        if self.two_ka:
            starts = [*starts, self.entered(ka, starts[0].coords)]
        point = self.at(ka, starts)
        if i not in self.table or point.value < self.table[i].value:
            self.table[i] = point

    def lowest(self) -> float:
        return min(point.value for point in self.table.values())

    def trace(self, i0: int, starts: Sequence[_Point], excess: float) -> None:
        """Solve node *i0* from *starts* (none: it is solved already), then outward node by node.

        Each node starts from its inner neighbour's solution, until one lies
        ``_STOP_EXCESS * excess`` above the lowest node, cannot be solved, or
        is the last before the Ka bound.
        """
        if starts:
            self._node(i0, starts)
        for d in (1, -1):
            i = i0 + d
            while 0 <= i < self.nodes.size and np.isfinite(self.table[i - d].value):
                self._node(i, [self.table[i - d]])
                if self.table[i].value - self.lowest() > _STOP_EXCESS * excess:
                    break
                i += d

    def refine(self) -> None:
        """Bounded Brent between the neighbours of the lowest node, every value from that node's solution."""
        values = np.full(self.nodes.size, np.inf)
        for i, point in self.table.items():
            values[i] = point.value
        best = int(np.argmin(values))
        _refine_at(lambda ka: self.at(ka, [self.table[best]]).value, self.nodes, values, best)

    def sweep(self, accepts: Callable[[_Point], bool], excess: float) -> None:
        """From each end of the traced stretch to the Ka bound, one node in ``_COARSE_STEP``.

        Each coarse node starts from the last one. One that *accepts* finds at
        or below its cut-off is traced like the first node, which fills in the nodes
        around it and lets the interval report the gap; one below the optimum
        is a better basin, and the trace from it finds the new optimum. A node
        the model cannot be solved at ends the sweep on its side.
        """
        last_node = self.nodes.size - 1
        for end, outermost in ((last_node, max), (0, min)):
            while (last := outermost(self.table)) != end and np.isfinite(self.table[last].value):
                i = int(np.clip(last + np.sign(end - last) * _COARSE_STEP, 0, last_node))
                self._node(i, [self.table[last]])
                if accepts(self.table[i]):
                    self.trace(i, [], excess)

    # -- edges and the drawn curve ------------------------------------------------

    def _close(self, hat: _Point, cut: Callable[[int], float], d: int) -> None:
        """Solve the nodes beyond the accepted point furthest out on side *d* until one is rejected or unsolvable.

        A point is accepted at or below *cut* at the rank of its own solution.
        The node beyond the accepted stretch is solved again from the accepted
        point's solution, because a basin can be reachable from one side only;
        if that brings it under its cut-off it joins the stretch and the next
        node out is solved.
        """
        key, nodes = self.key, self.nodes
        while True:
            accepted = [hat, *(point for point in self.table.values() if point.value <= cut(point.rank))]
            inner = (max if d > 0 else min)(accepted, key=lambda point: point.ka[key])
            beyond = np.flatnonzero(nodes > inner.ka[key]) if d > 0 else np.flatnonzero(nodes < inner.ka[key])[::-1]
            if not beyond.size:
                return
            i = int(beyond[0])
            if i not in self.table or np.isfinite(self.table[i].value):
                self._node(i, [inner])
            if not np.isfinite(self.table[i].value) or self.table[i].value > cut(self.table[i].rank):
                return

    def profile(
        self, hat: _Point, cut: Callable[[int], float], floor: float, level: float, dof: float, inflation: float
    ) -> tuple[KaInterval, list[_Point]]:
        """Interval of this Ka under *cut* and the points its curve is drawn through, ascending in Ka.

        *cut* gives the cut-off of a solution of each rank, a point judged at
        the rank of its own, widened by the design effect *inflation* that the
        interval records, and *floor* is the optimum's objective, which every
        cut-off stands above. The accepted stretch is first extended node by
        node (:meth:`_close`), and the interval is then cut from the solved
        nodes by the routine of the fixed-input interval
        (:func:`~core.pipeline.varpro._cut_interval`): the profile is read
        again at ``_PROFILE_PER_DECADE`` wherever the test can accept Ka between
        the nodes and on both sides of every step of the cut-off between the
        points read, the edges are roots of the profile minus that cut-off — where
        the cut-off steps, the step itself — and a closed edge of a two-Ka
        interval that only the bound of the other Ka produces opens that side
        (:meth:`~core.pipeline.varpro.Projection._bound_behind`), the rise
        inside that bound minimised over the inputs. A solved node keeps the
        value it was solved to; every other point is solved from the nearest
        solved node or estimate on each side and, with two free Ka, also where
        the other Ka minimises the fixed-input objective there, as a node is.
        The curve runs through the points the interval was cut from, the
        estimate *hat*, the closed edges, and at ``_PROFILE_PER_DECADE``
        through the search-grid cell of the estimate and of each closed edge,
        where the curve turns; each of those last points is solved from the
        nearest of the others. Between those cells the minimum over the inputs
        leaves a smooth curve, which the nodes carry.
        """
        for d in (-1, 1):
            self._close(hat, cut, d)
        while True:
            interval, grid, value, edges = self._cut(hat, cut, floor, level, dof, inflation)
            if not (interval.split and self._fill_gaps(interval, grid, value, cut)):
                break
        key = self.key
        drawn = {**{ka: value(ka) for ka in grid.tolist()}, hat.ka[key]: hat, **edges}
        anchors = list(drawn.values())
        anchor_logs = np.log10([point.ka[key] for point in anchors])
        for at in [hat.ka[key], *edges]:
            cell = self.nodes[self.nodes <= at][-1:].tolist() + self.nodes[self.nodes >= at][:1].tolist()
            for ka in _ka_grid(min(cell), max(cell), _PROFILE_PER_DECADE * (len(cell) > 1)).tolist():
                if ka not in drawn:
                    drawn[ka] = self.at(ka, [anchors[int(np.argmin(np.abs(anchor_logs - np.log10(ka))))]])
        return interval, [drawn[ka] for ka in sorted(drawn)]

    def _cut(
        self, hat: _Point, cut: Callable[[int], float], floor: float, level: float, dof: float, inflation: float
    ) -> tuple[KaInterval, np.ndarray, Callable[[float], _Point], dict[float, _Point]]:
        """The interval cut from the table as it stands, the Ka it was cut from, the profile there and its closed edges."""
        key, projection = self.key, self.problem.projection
        anchors = sorted([*self.table.values(), hat], key=lambda point: point.ka[key])
        anchors = [point for point in anchors if np.isfinite(point.value)]
        anchor_ka = np.array([point.ka[key] for point in anchors])
        known = {point.ka[key]: point for point in [*self.table.values(), hat]}
        read: dict[float, _Point] = {}

        def value(ka: float) -> _Point:
            if ka in known:
                return known[ka]
            if ka not in read:
                i = int(np.searchsorted(anchor_ka, ka))
                starts = anchors[max(i - 1, 0) : i + 1]
                if self.two_ka:
                    starts = [*starts, self.entered(ka, starts[0].coords)]
                read[ka] = self.at(ka, starts)
            return read[ka]

        def judged(point: _Point) -> tuple[float, int]:
            return point.value - cut(point.rank), point.rank

        edges: dict[float, _Point] = {}

        def limited_by(edge: float) -> str:
            point = edges[edge] = value(edge)
            if not self.two_ka:
                return ''
            (other,) = (k for k in projection.free_ka if k != key)
            return projection._bound_behind(
                key,
                point.ka[other],
                lambda inside: self.problem.solve({key: edge, other: inside}, point).value - point.value,
                cut(point.rank) - floor,
            )

        interval, grid = _cut_interval(
            lambda ka: judged(value(ka)),
            {point.ka[key]: judged(point) for point in self.table.values()},
            hat.ka[key],
            cut,
            level,
            dof,
            inflation,
            limited_by,
            self.nodes,
        )
        return interval, grid, value, edges

    def _fill_gaps(
        self, interval: KaInterval, grid: np.ndarray, value: Callable[[float], _Point], cut: Callable[[int], float]
    ) -> bool:
        """Solve every node the test rejects inside *interval* again from its neighbours on *grid*; whether one fell.

        A node is solved from its neighbour on one side only, and a basin of
        the inputs can be reachable from the other, so a rejected node between
        accepted points is a gap only where the solutions of the points beside
        it do not bring it lower.
        """
        key, fell = self.key, False
        for i, point in list(self.table.items()):
            ka = point.ka[key]
            if not (interval.low < ka < interval.high and point.value > cut(point.rank)):
                continue
            j = int(np.searchsorted(grid, ka))
            beside = [value(float(grid[k])) for k in (j - 1, j + 1) if 0 <= k < grid.size]
            starts = [start for start in beside if np.isfinite(start.value)]
            if not starts:
                continue
            again = self.at(ka, starts)
            if again.value < point.value - _P_RESOLUTION:
                self.table[i], fell = again, True
        return fell


@lru_cache(maxsize=None)
def _excess(n: int, dof: float, level: float, m: int = 1, inflation: float = 1.0) -> float:
    """Acceptance excess of the penalised profile: the F test of *m* parameters given up, on the log scale.

    ``n log(1 + kappa m F(level; m, dof) / dof)`` with ``kappa`` the design
    effect *inflation* (:mod:`core.pipeline.inflation`).
    """
    return n * float(np.log1p(_allowed_rise(level, m, dof, inflation)))


def at_edge(constraint: InputConstraint, offset: float) -> bool:
    """Whether *offset* rests on an end of the range *constraint* states, to ``_EDGE_TOL`` of its width.

    An input stated with a standard deviation has no range to rest on.
    """
    if constraint.sigma is not None:
        return False
    margin = _EDGE_TOL * (constraint.hi - constraint.lo)
    return bool(offset - constraint.lo <= margin or constraint.hi - offset <= margin)


def _input_directions(
    jacobian: np.ndarray,
    ka_fitted: Sequence[bool],
    constraints: Sequence[InputConstraint],
    offsets: Mapping[str, float],
    ssr: float,
    n: int,
    ss_tot: float,
) -> tuple[np.ndarray, np.ndarray]:
    """:func:`conflict_reference` of a fit, at the noise scale ``sqrt(S / n)`` of its own residual.

    *ka_fitted* says, per leading binding-constant column of *jacobian*,
    whether the fit left that constant strictly inside its box. A binding
    constant on a bound of its box and an input stated as a range that the
    fit left on an end of it are held there and not fitted, like a signal
    parameter on its bound, so their Jacobian columns stay out: left in, such
    a column absorbs what the data say about the inputs along whatever
    direction it happens to point, although the fit did not move it.
    """
    return conflict_reference(*_reference_arguments(jacobian, ka_fitted, constraints, offsets, ssr, n, ss_tot))


def _reference_arguments(
    jacobian: np.ndarray,
    ka_fitted: Sequence[bool],
    constraints: Sequence[InputConstraint],
    offsets: Mapping[str, float],
    ssr: float,
    n: int,
    ss_tot: float,
) -> tuple[np.ndarray, int, np.ndarray, float]:
    """The columns of the fitted parameters, their Ka count, the σ mask and the noise scale of :func:`_input_directions`."""
    scale = float(np.sqrt(max(ssr, _R2_RESOLUTION * ss_tot) / n))
    moved = np.array([not at_edge(c, offsets[c.key]) for c in constraints], dtype=bool)
    is_sigma = np.array([c.sigma is not None for c in constraints], dtype=bool)
    columns = np.concatenate([np.asarray(ka_fitted, dtype=bool), moved])
    return jacobian[:, columns], int(np.sum(ka_fitted)), is_sigma[moved], scale


def _require_aware_dof(n: int, n_model: int, constraints: Sequence[InputConstraint], taken: float = 0.0) -> float:
    """``nu = n - p - sum w``; refused in plain language, naming the inputs, when less than one is left.

    *n_model* counts the binding constants and the signal parameters,
    *constraints* are the sources that count as parameters — every one before
    the search, and at the optimum those it did not leave on an end of their
    range — and *taken* is the sum of the weights of the inputs stated with a
    standard deviation. One degree of freedom is what the fixed-input interval asks
    for (``n - p >= 1``); below it the F quantile grows without bound and
    the interval says nothing.
    """
    _require_dof(n, n_model)
    ranges = [c.name for c in constraints if c.sigma is None]
    dof = n - n_model - len(ranges)
    names, how, remedy = ranges, ' within a range', 'State an input as a standard deviation instead, hold it'
    if dof >= 1:
        dof -= taken
        names, how, remedy = [c.name for c in constraints], '', 'Hold an input'
    if dof < 1:
        raise FitRefused(
            f'The data have {n} titration points, too few to fit this model and also let '
            f'{", ".join(dict.fromkeys(names))} move{how}. {remedy} at its entered value under Input Uncertainty, '
            'or add titration points, and fit again.'
        )
    return dof


def input_aware(
    projection: Projection,
    fixed: ProjectedFit,
    constraints: Sequence[InputConstraint],
    *,
    loading: Callable[[Mapping[str, float]], dict[str, float]] | None = None,
    level: float = LEVEL,
    should_cancel: Callable[[], bool] | None = None,
    conditional: Mapping[str, KaInterval] | None = None,
    inflation: Mapping[str, float] | None = None,
) -> AwareResult:
    """Fit and Ka intervals of a single-row projection with its varying inputs free within their constraints.

    Per free Ka, on the search-grid nodes of its bounds: the node nearest the
    fixed-input fit is solved from the entered inputs and the profile is traced
    outward from it, each node from its neighbour's solution, until it lies
    ``_STOP_EXCESS`` acceptance excesses above the lowest node; bounded Brent
    between the neighbours of the lowest node gives the optimum; a sweep of one
    node per decade over the rest of the bounds looks for a second accepted
    stretch or a better basin. With two free Ka the joint optimum is first
    sought by one least-squares solve over both constants and the inputs from
    each grid local minimum the fixed-input search refines and from the
    fixed-input fit itself. The estimate is the lowest point found anywhere,
    put on a Ka bound where the objective there is no higher, to the resolution
    of R², as the fixed-input fit is (:meth:`_Problem.rest`), and moved onto the
    minimiser next to it where that holds a signal coefficient on its bound
    (:meth:`_Problem.rest_coefficients`); ``P_min`` is its objective, so every
    profile is cut above the same minimum.
    The accepted stretch is extended node by node, and the interval is cut by
    the routine of the fixed-input interval
    (:func:`~core.pipeline.varpro._cut_interval`), every point off the node
    table the lowest of the solves from the nearest solved points on either
    side; a node the test rejects inside the interval is solved again from the
    points beside it before it counts as a gap. The interval of the second
    constant of a stepwise model carries the one-step test of
    :func:`_one_step_p` and is open below
    where the test does not reject the model without the second step. Every
    cut-off of one binding constant — of the trace, the edges, the drawn cut
    and the one-step test — is widened by that constant's *inflation*.

    Parameters
    ----------
    projection : Projection
        Single-row projection of the fitted signal.
    fixed : ProjectedFit
        Its fit at the entered inputs.
    constraints : Sequence[InputConstraint]
        The varying sources (:func:`core.pipeline.inputs.constraints`). When
        empty, the result is the fixed-input fit with the intervals of
        :meth:`Projection.interval`.
    loading : Callable[[Mapping[str, float]], dict[str, float]], optional
        Maps the offsets of the constraints, by constraint key, to the offsets
        of the inputs, by input key
        (:meth:`core.pipeline.inputs.ErrorModel.input_offsets`). Without it
        every constraint key is an input key and the offsets pass as they are.
    level : float
        Confidence level.
    should_cancel : Callable[[], bool], optional
        Asked before every inner solve whether to stop.
    conditional : Mapping[str, KaInterval], optional
        Fixed-input intervals the caller has already computed for *fixed* at
        *level*; with no varying input each one widened by that constant's
        *inflation* is the interval returned, and nothing is computed twice.
    inflation : Mapping[str, float], optional
        The design effect ``kappa >= 1`` of each free binding constant
        (:func:`core.pipeline.inflation.inflation`) by which its acceptance
        excess is widened to ``n log(1 + kappa m F / nu)``; a constant left
        out, and every one when it is omitted, takes one.

    Raises
    ------
    FitRefused
        When the titration points leave no degree of freedom beside the model
        and the varying inputs.
    FitCancelled
        When *should_cancel* or the projection's own flag asked to stop.
    ValueError
        For an *inflation* that is not a finite number of one or more.
    """
    constraints = tuple(constraints)
    n, ss_tot = projection.n_points, float(projection.ss_tot[0])
    kappa = {key: float((inflation or {}).get(key, 1.0)) for key in projection.free_ka}
    for factor in kappa.values():
        _require_inflation(factor)
    if not constraints:
        return _fixed_inputs(projection, fixed, level, conditional, kappa)

    problem = _Problem(projection, constraints, should_cancel, loading)
    best: list[_Point] = []

    def consider(point: _Point) -> _Point:
        if not best or point.value < best[0].value - _P_RESOLUTION:
            best[:] = [point]
        return point

    def cut(optimum: _Point, dof: float, key: str) -> Callable[[int], float]:
        """Cut-off on *key*'s profile of a solution of each rank: one more parameter per signal parameter it pins.

        As in :meth:`Projection.cut_off`, only the signal parameters: the other
        binding constant and an input stated as a range reach a bound where the
        objective is flat towards it, and whether a solve lands on that bound
        or just inside it is arbitrary. Widened by the design effect of *key*.
        """
        fitted = optimum.fitted.rank
        return lambda rank: optimum.value + _excess(n, dof, level, 1 + max(0, fitted - rank), kappa[key])

    # Refused on what the model has free, wherever a fit puts it, so that whether a fit is made does
    # not depend on where the data happen to put its parameters.
    search_dof = _require_aware_dof(n, fixed.n_free_ka + fixed.rank, constraints)
    entered = problem.start_coords()
    # The entered inputs at the fixed-input fit are allowed, so the fit from there is never worse
    # than the fixed-input one; it is also the whole fit when every binding constant is pinned.
    at_fixed = {key: fixed.ka[key] for key in projection.free_ka}
    if len(projection.free_ka) == 2:
        for ka in [*projection.two_ka_starts(), at_fixed]:
            consider(problem.solve({}, _Point(np.nan, ka, entered, np.nan)))
    else:
        consider(problem.solve(at_fixed, _Point(np.nan, at_fixed, entered, np.nan)))
    traces = {key: _Trace(problem, key, consider) for key in projection.free_ka}
    for key, trace in traces.items():
        excess = _excess(n, search_dof, level, 1, kappa[key])
        centre = best[0] if best and np.isfinite(best[0].value) else None
        nearest = np.abs(np.log10(trace.nodes) - np.log10(centre.ka[key] if centre else fixed.ka[key]))
        i0 = int(np.argmin(nearest))
        trace.trace(i0, [trace.entered(float(trace.nodes[i0])), *([centre] if centre else [])], excess)
        lowest = None
        while lowest != trace.lowest():
            lowest = trace.lowest()
            trace.refine()
            trace.sweep(lambda point: point.value <= cut(best[0], search_dof, key)(point.rank), excess)

    profiles: dict[str, AwareProfile] = {}
    for _ in range(_MAX_PASSES):
        # The search ends at the lowest point found, which rests on a Ka bound as the fixed-input fit does.
        optimum = problem.rest_coefficients(problem.rest(best[0], projection.free_ka))
        consider(optimum)
        found = best[0]
        jacobian = problem.jacobian(optimum)
        ka_fitted = [key in optimum.fitted.ka for key in projection.free_ka]
        offsets = problem.offsets(optimum.coords)
        weights, _ = _input_directions(jacobian, ka_fitted, constraints, offsets, optimum.ssr, n, ss_tot)
        p = problem.count(optimum)
        moved = [c for c in constraints if not at_edge(c, offsets[c.key])]
        dof = _require_aware_dof(n, optimum.fitted.count, moved, float(weights.sum()))
        for key, trace in traces.items():
            excess = _excess(n, dof, level, 1, kappa[key])
            threshold = optimum.value + excess
            hat = optimum if len(traces) == 1 else trace.at(optimum.ka[key], [optimum])
            interval, drawn = trace.profile(hat, cut(optimum, dof, key), optimum.value, level, dof, kappa[key])
            objective = np.array([point.value for point in drawn])
            cuts = np.array([cut(optimum, dof, key)(point.rank) for point in drawn])
            with np.errstate(over='ignore'):
                r2 = np.where(np.isfinite(objective), 1.0 - np.exp(objective / n) / ss_tot, np.nan)
            other = [k for k in projection.free_ka if k != key]
            profiles[key] = AwareProfile(
                ka_key=key,
                grid=np.array([point.ka[key] for point in drawn]),
                objective=objective,
                r2=r2,
                offsets=np.array([point.coords * problem.unit for point in drawn]).reshape(len(drawn), -1),
                threshold=threshold,
                r2_threshold=1.0 - float(np.exp(threshold / n)) / ss_tot,
                interval=interval,
                other_ka=np.array([point.ka[other[0]] for point in drawn]) if other else None,
                cut=cuts,
                r2_cut=1.0 - np.exp(cuts / n) / ss_tot,
            )
        if best[0] is found:
            break
    else:
        raise FitRefused(
            'The interval did not settle: every attempt to close it found a better fit somewhere else. '
            'Narrow the bounds of the binding constants under Parameter Bounds and fit again.'
        )

    if projection.second_step in traces:
        key = projection.second_step
        one_step_p = _one_step_p(problem, traces[key], optimum, dof, kappa[key])
        interval = _with_one_step_test(profiles[key].interval, one_step_p, projection.ka_bounds[key][0])
        profiles[key] = replace(profiles[key], interval=interval)

    offsets = problem.offsets(optimum.coords)
    input_offsets = problem.input_offsets(optimum.coords)
    _, _, coefficients = projection._solve_at(optimum.ka, input_offsets)
    fit = AwareFit(
        ka=projection._full_ka(optimum.ka),
        offsets=offsets,
        input_offsets=input_offsets,
        coefficients=coefficients[0],
        ssr=optimum.ssr,
        objective=optimum.value,
        n_params=p,
        jacobian=jacobian,
        ka_free=projection.free_ka,
        constraint_keys=problem.keys,
        ka_fitted=optimum.fitted.ka,
    )
    return AwareResult(fit=fit, profiles=profiles, constraints=constraints, n_points=n, ss_tot=ss_tot)


def _one_step_p(problem: _Problem, trace: _Trace, optimum: _Point, dof: float, inflation: float) -> float:
    """:meth:`Projection.one_step_p` on the penalised profile of the second constant, which *trace* follows.

    The objective with that constant at zero, minimised over the other
    binding constant and the inputs, against the optimum: the test that cuts
    the interval, ``P(0) - P_min`` against ``n log(1 + kappa m F(m, nu) /
    nu)`` with ``kappa`` its *inflation*, turned into its p-value
    ``sf((exp((P(0) - P_min) / n) - 1) nu / (kappa m); m, nu)``. The solve
    starts from the optimum, from the outermost node the trace solved below it
    and from where the other constant minimises the fixed-input objective at
    zero, and the lowest of the three counts.
    """
    zero = {trace.key: 0.0}
    starts = [optimum, trace.table[min(trace.table)], trace.entered(0.0, optimum.coords)]
    point = min((problem.solve(zero, start) for start in starts), key=lambda solved: solved.value)
    m = 1 + max(0, optimum.fitted.rank - point.rank)
    return _rise_p(np.expm1((point.value - optimum.value) / problem.n), m, dof, inflation)


def _fixed_inputs(
    projection: Projection,
    fixed: ProjectedFit,
    level: float,
    conditional: Mapping[str, KaInterval] | None,
    kappa: Mapping[str, float],
) -> AwareResult:
    """The result with no varying input: the fixed-input fit and its own intervals at the design effects *kappa*.

    With nothing to minimise over, the penalised profile is the fixed-input
    one, ``n log S(k)``, which :mod:`core.pipeline.profile` draws. Each profile
    here holds the points that say what the interval is: the estimate at
    ``P_min`` and every closed edge, each with the cut-off of its own fit.
    A *conditional* interval is the one returned where it was cut at the
    same design effect, and computed again at that one otherwise.
    """
    n, ss_tot = projection.n_points, float(projection.ss_tot[0])
    inner_per_decade = _INNER_PER_DECADE if len(projection.free_ka) == 2 else _SEARCH_PER_DECADE
    profiles = {}
    for key in projection.free_ka:
        threshold = projection.threshold(fixed, level, inflation=kappa[key])
        cut = projection.cut_off(fixed, level, inflation=kappa[key])
        given = (conditional or {}).get(key)
        interval = (
            given
            if given is not None and given.inflation == kappa[key]
            else projection.interval(key, fixed, level, kappa[key])
        )
        points = {fixed.ka[key]: (projection._floored(fixed), threshold)}
        for edge, is_open in _edges(interval):
            if not is_open:
                _, ssr, fitted = projection.profile_point(key, edge, inner_per_decade)
                points[edge] = (ssr, cut(fitted))
        grid = np.array(sorted(points))
        ssr, cuts = np.array([points[ka] for ka in grid.tolist()]).T
        profiles[key] = AwareProfile(
            ka_key=key,
            grid=grid,
            objective=n * np.log(ssr),
            r2=1.0 - ssr / ss_tot,
            offsets=np.empty((grid.size, 0)),
            threshold=n * float(np.log(threshold)),
            r2_threshold=1.0 - threshold / ss_tot,
            interval=interval,
            cut=n * np.log(cuts),
            r2_cut=1.0 - cuts / ss_tot,
        )
    fitted = projection.fitted_parameters(fixed.ka)
    fit = AwareFit(
        ka=dict(fixed.ka),
        offsets={},
        input_offsets={},
        coefficients=fixed.coefficients[0],
        ssr=float(fixed.row_ssr[0]),
        objective=n * float(np.log(projection._floored(fixed))),
        n_params=fitted.count,
        jacobian=_Problem(projection, ()).jacobian(_Point(np.nan, dict(fixed.ka), np.empty(0), np.nan)),
        ka_free=projection.free_ka,
        constraint_keys=(),
        ka_fitted=fitted.ka,
    )
    return AwareResult(fit=fit, profiles=profiles, constraints=(), n_points=n, ss_tot=ss_tot)


def fit_jacobian(projection: Projection, result: AwareResult) -> np.ndarray:
    """Jacobian of the whole fit for :func:`core.pipeline.diagnostics.runs_test`.

    The columns of the parameters the fit fitted: the signal parameters it
    left inside their bounds, then those of ``AwareFit.jacobian`` that it
    moved — every free binding constant inside its box and every input but
    one resting on an end of its range. A parameter on a bound is held there
    and has no column. The residual rows are in units of the noise scale
    ``sqrt(S / n)``, the penalty rows as they are.
    """
    fit, n = result.fit, result.n_points
    fitted = projection.fitted_parameters(fit.ka, fit.input_offsets).columns
    scale = float(np.sqrt(max(fit.ssr, _R2_RESOLUTION * result.ss_tot) / n))
    columns = np.zeros((fit.jacobian.shape[0], fitted.shape[1]))
    columns[:n] = fitted
    moved = [key in fit.ka_fitted for key in fit.ka_free]
    moved += [not at_edge(c, fit.offsets[c.key]) for c in result.constraints]
    stacked = np.hstack([columns, fit.jacobian[:, moved]])
    stacked[:n] /= scale
    return stacked


def misfit_design(projection: Projection, result: AwareResult) -> np.ndarray:
    """Design of the whole fit for :func:`core.pipeline.diagnostics.lack_of_fit`: one column per parameter of its ``p``.

    The derivatives of the fitted signal, in signal units and unweighted, with
    respect to the parameters counted in ``AwareFit.n_params``: the signal
    parameters the fit left inside their bounds (their species columns), every
    free binding constant inside its box (per decade of it) and every input
    stated as a range that the fit left off the ends of it (per half range).
    An input stated with a standard deviation is held back by its penalty and
    is not one of them. Columns that a mass balance ties count once, so the
    numerical rank of the design is ``n_params`` while its columns may be more.
    """
    fit = result.fit
    whiten = np.sqrt(projection.point_weights)[:, np.newaxis]
    signal = projection.fitted_parameters(fit.ka, fit.input_offsets).columns / whiten
    moved = [key in fit.ka_fitted for key in fit.ka_free]
    moved += [c.sigma is None and not at_edge(c, fit.offsets[c.key]) for c in result.constraints]
    # The Jacobian is that of the whitened residual y - f: minus the whitened derivatives of f.
    return np.hstack([signal, -fit.jacobian[: result.n_points, moved] / whiten])


def _edges(interval: KaInterval) -> tuple[tuple[float, bool], tuple[float, bool]]:
    return (interval.low, interval.open_low), (interval.high, interval.open_high)


def penalised_objective(
    projection: Projection,
    ka: Mapping[str, float],
    constraints: Sequence[InputConstraint],
    start: Mapping[str, float],
    *,
    other_ka: Mapping[str, float] | None,
    loading: Callable[[Mapping[str, float]], dict[str, float]] | None = None,
) -> tuple[float, dict[str, float], dict[str, float], float]:
    """``n log S + z'z`` minimised at the binding constants *ka* from one start.

    Parameters
    ----------
    ka : Mapping[str, float]
        The binding constants held fixed.
    start : Mapping[str, float]
        Starting offset per constraint key, as fractions; one left out starts
        at zero.
    other_ka : Mapping[str, float] or None
        Starting value of every free binding constant not in *ka*.
    loading : Callable[[Mapping[str, float]], dict[str, float]], optional
        As in :func:`input_aware`.

    Returns
    -------
    tuple[float, dict[str, float], dict[str, float], float]
        The objective, the fitted offsets, the fitted other binding constants
        and the residual sum of squares.
    """
    problem = _Problem(projection, constraints, loading=loading)
    coords = np.array([start.get(key, 0.0) for key in problem.keys]) / problem.unit
    point = problem.solve(dict(ka), _Point(np.nan, {**ka, **(other_ka or {})}, coords, np.nan))
    others = {key: value for key, value in point.ka.items() if key not in ka}
    return point.value, problem.offsets(point.coords), others, point.ssr


def input_shifts(result: AwareResult) -> dict[str, InputShift]:
    """Where the fit put every varying input: its offset, in standard deviations or against the ends of its range."""
    shifts = {}
    for constraint in result.constraints:
        e = result.fit.offsets[constraint.key]
        z = None if constraint.sigma is None else e / constraint.sigma
        shifts[constraint.key] = InputShift(constraint.key, e, z, at_edge(constraint, e))
    return shifts


def conflict(result: AwareResult, added: np.ndarray | None = None) -> Conflict | None:
    """Conflict statistic of the inputs stated with a standard deviation; ``None`` when the data inform none of them.

    *added* is the covariance a stated random error of each addition puts on
    the whitened residual of the fitted signal, in signal units: the
    reference of the statistic then carries it (:func:`conflict_added`).
    """
    fit = result.fit
    sigma = [c for c in result.constraints if c.sigma is not None]
    if not sigma:
        return None
    ka_fitted = [key in fit.ka_fitted for key in fit.ka_free]
    reference = _reference_arguments(
        fit.jacobian, ka_fitted, result.constraints, fit.offsets, fit.ssr, result.n_points, result.ss_tot
    )
    extra = None if added is None else conflict_added(*reference, added)
    return conflict_test(
        [fit.offsets[c.key] / c.sigma for c in sigma],
        *conflict_reference(*reference),
        result.n_points,
        fit.n_params,
        added=extra,
    )
