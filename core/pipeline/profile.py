"""Exact Ka profile for assays with one binding constant.

When an assay has exactly one binding constant and every other parameter is a
signal offset or coefficient, the model signal is linear in those other
parameters once Ka is fixed. The best fit at a fixed Ka is then a bounded
linear least-squares solve, so the best achievable R² at every Ka is exact.
That curve is the profile: it bounds every fit the optimizer can find, a grid
search along it with a bounded refinement between the best grid point's
neighbours locates the best fit without a multi-start search, and an F test on
it gives a profile-likelihood confidence interval for Ka.

The displacement assays' equilibrium solver does not reach a solution at every
Ka: above roughly 1e19 to 1e20 1/M, depending on the concentrations, and at a
total concentration of zero, its species are not a number. Such a Ka has no fit
at all, so its residual sum of squares is infinite, it never enters the interval
and no curve is drawn across it.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Any, Callable, Type

import numpy as np
from scipy.optimize import brentq, lsq_linear, minimize_scalar
from scipy.stats import f as f_dist

from core.assays.base import BaseAssay
from core.assays.registry import ASSAY_REGISTRY, AssayType, ParamKind
from core.data_processing.measurement_set import MeasurementSet
from core.optimizer.multistart import FitCancelled
from core.pipeline.fit_pipeline import FitConfig, _resolve_bounds
from core.units import Quantity

# Ka grid densities, in points per decade across the Ka bounds. The search grid
# only has to land next to the optimum (a bounded refinement finds it between
# the neighbouring points); the profile grid is where the plotted curve starts.
_SEARCH_PER_DECADE = 4
_PROFILE_PER_DECADE = 20

# The plotted curve joins exact points with straight lines. A stretch of it is
# split while the exact R² at its midpoint misses the line by more than half of
# its allowance, _CURVE_R2_TOL + _CURVE_DEPTH_TOL × (the curve's best R² − the
# stretch's highest R²); a stretch that bends one way then stays within the
# allowance of the exact curve. At the peak that is 1e-6 R². Below it, the
# allowance is 0.1 % of the depth, so in any view that shows a stretch together
# with the peak the line is off by less than 0.1 % of the view's height. Where
# a species barely forms, rounding makes the curve jitter, so the stretches with
# the worst miss for their allowance are split first, _CURVE_MAX_EXTRA extra
# evaluations bound the work, and _CURVE_MIN_STEP, in decades of Ka, stops the
# splitting at a sharp corner or a jump.
_CURVE_R2_TOL = 1e-6
_CURVE_DEPTH_TOL = 1e-3
_CURVE_MAX_EXTRA = 2000
_CURVE_MIN_STEP = 1e-6

# Tolerance of the refinement and of the interval edges, in decades of Ka.
_LOG_KA_XTOL = 1e-7

# Relative singular-value cut-off for the rank of the norm-scaled coefficient
# design. The equilibrium solve is iterative, so an exact linear dependence
# between species columns (free plus bound dye summing to a fixed total, say)
# leaves a singular value of order 1e-11 rather than zero, while independent
# columns stay above 1e-6 across the Ka range.
_RANK_RTOL = 1e-8

# Excess SSR above the interval's threshold that a Ka the model cannot solve
# enters the edge search with. Root finding needs a finite value on each side of
# an edge and only the sign of the excess decides which side of the interval a
# Ka is on, so any positive value places such a Ka outside.
_UNSOLVABLE_EXCESS = 1.0

_LINEAR_KINDS = (ParamKind.SIGNAL_OFFSET, ParamKind.SIGNAL_COEFFICIENT)


@dataclass
class ProfileResult:
    """Best achievable R² across Ka and the confidence interval it implies.

    Attributes
    ----------
    ka_key : str
        The binding-constant parameter key (e.g. ``"Ka_guest"``).
    grid : np.ndarray
        Ka values in 1/M across the Ka bounds in force, ascending: a log-spaced
        grid plus the best fit, the interval's closed edges and extra points
        where the curves bend, so straight lines between them follow the exact
        curves (see ``_CURVE_R2_TOL``).
    r2 : np.ndarray
        Best R² of the averaged signal at each grid Ka; ``nan`` at a Ka the
        equilibrium model cannot solve, which has no fit to draw.
    replica_r2 : dict[str, np.ndarray] | None
        Each active replicate's own best-R² curve on ``grid``; ``None`` unless
        the fit ran per replicate.
    best_ka : float
        Ka (1/M) of the best fit of the averaged signal.
    best_r2 : float
        R² at ``best_ka``.
    level : float
        Confidence level of ``ci``.
    ci : tuple[float, float]
        ``(low, high)`` Ka in 1/M: the envelope of the Ka values whose residual
        sum of squares stays within the F-test threshold. ``(best_ka, best_ka)``
        when Ka is pinned.
    ci_open : tuple[bool, bool]
        ``True`` on a side where the interval reaches as far as the profile
        goes, so the data do not limit Ka there.
    ci_unsolvable : tuple[bool, bool]
        ``True`` on an open side where the profile stops because the
        equilibrium model cannot be solved past the edge, rather than because
        the Ka bound is reached. The edge is then the last Ka the model could
        be evaluated at, which is below the bound in force.
    ci_split : bool
        ``True`` when the Ka values within the threshold do not form one
        connected stretch of the grid, so ``ci`` spans a gap of Ka values the
        data reject.
    ka_pinned : bool
        ``True`` when the Ka bounds are equal, which fixes Ka and leaves no
        interval to estimate.
    r2_threshold : float
        R² at which the interval is cut. With ``ka_pinned`` there is no interval
        and the cut is the R² a one-parameter improvement would have to beat.
    n_points : int
        Number of points in the averaged signal.
    n_params : int
        Parameter count ``p`` of the F test: the numerical rank of the
        coefficient design at the optimum, plus one for Ka unless Ka is pinned.
    per_replica : bool
        Whether the fit this profile belongs to ran each replicate separately.
    """

    ka_key: str
    grid: np.ndarray
    r2: np.ndarray
    replica_r2: dict[str, np.ndarray] | None
    best_ka: float
    best_r2: float
    level: float
    ci: tuple[float, float]
    ci_open: tuple[bool, bool]
    r2_threshold: float
    n_points: int
    n_params: int
    per_replica: bool
    ka_pinned: bool = False
    ci_split: bool = False
    ci_unsolvable: tuple[bool, bool] = (False, False)


def profile_supported(assay_type: AssayType) -> bool:
    """Whether the assay's signal is linear in every parameter but one Ka.

    True when the registry declares exactly one ``BINDING_CONSTANT`` and every
    other parameter a ``SIGNAL_OFFSET`` or ``SIGNAL_COEFFICIENT``.
    """
    meta = ASSAY_REGISTRY[assay_type]
    kinds = [meta.param_kinds[k] for k in meta.parameter_keys]
    others = [k for k in kinds if k is not ParamKind.BINDING_CONSTANT]
    return len(kinds) - len(others) == 1 and all(k in _LINEAR_KINDS for k in others)


def best_fit_by_profile(assay: BaseAssay, bounds: dict[str, tuple[Quantity, Quantity]]) -> tuple[float, float]:
    """Best fit of one signal, searched along its exact Ka profile.

    The profile is evaluated on a log-spaced grid across the Ka bounds and
    refined between the best grid point's neighbours, so the result is the
    profile's best point to within ``_LOG_KA_XTOL`` decades of Ka. A Ka the
    equilibrium model cannot solve has no fit and is passed over; when that is
    every Ka in the bounds, the R² is ``-inf``.

    Parameters
    ----------
    assay : BaseAssay
        Assay of a type for which :func:`profile_supported` is true.
    bounds : dict[str, tuple[Quantity, Quantity]]
        Resolved bounds for every parameter (registry defaults merged with any
        custom bounds).

    Returns
    -------
    tuple[float, float]
        ``(best Ka in 1/M, its R²)``.
    """
    _require_supported(assay.assay_type)
    y = assay.y_data.magnitude[np.newaxis, :]
    _, (lo, hi), ssr_at = _profile_function(assay, bounds, y)
    grid = _ka_grid(lo, hi, _SEARCH_PER_DECADE)
    best_ka, best_ssr = _refine_best(lambda ka: ssr_at(ka).sum(), grid, np.array([ssr_at(ka).sum() for ka in grid]))
    return best_ka, float(1.0 - best_ssr / _ss_tot(y).sum())


def best_params_by_profile(assay: BaseAssay, bounds: dict[str, tuple[Quantity, Quantity]]) -> np.ndarray:
    """Parameter vector of the best fit of one signal.

    The Ka of :func:`best_fit_by_profile` together with the bounded
    least-squares coefficients at that Ka, in ``assay.parameter_keys`` order
    and each parameter's canonical unit, ready for ``assay.forward_model``.

    Parameters
    ----------
    assay : BaseAssay
        Assay of a type for which :func:`profile_supported` is true.
    bounds : dict[str, tuple[Quantity, Quantity]]
        Resolved bounds for every parameter.

    Returns
    -------
    np.ndarray
        The best-fit parameters.
    """
    ka, _ = best_fit_by_profile(assay, bounds)
    ka_key, coef_keys = _split_keys(assay)
    lb, ub = _coefficient_bounds(_float_bounds(assay, bounds), coef_keys)
    _, coef = _solve(_design(assay, ka_key, coef_keys, ka), lb, ub, assay.y_data.magnitude[np.newaxis, :])
    values = {ka_key: ka, **dict(zip(coef_keys, coef[0]))}
    return np.array([values[k] for k in assay.parameter_keys])


def fit_profile(
    ms: MeasurementSet,
    assay_cls: Type[BaseAssay],
    conditions: dict[str, Any],
    fit_config: FitConfig,
    *,
    level: float = 0.95,
    should_cancel: Callable[[], bool] | None = None,
) -> ProfileResult:
    """Exact Ka profile of the averaged signal and its confidence interval.

    The curve, the best fit and the interval describe the average of the active
    replicates, whose systematic departure from the model repeats in every
    replicate: counting each replicate's points as separate evidence would
    overstate how precisely the data pin Ka down. ``fit_config.per_replica``
    adds each replicate's own curve in ``replica_r2``; ``fit_config.custom_bounds``
    applies throughout. The interval keeps every Ka whose residual sum of squares
    stays within ``SSR_min * (1 + F(level; 1, n - p) / (n - p))``.

    Parameters
    ----------
    ms : MeasurementSet
        Source data; only active replicates are used. To profile the data a fit
        was made on, pass ``ms.with_active(fit_replica_ids(result))``.
    assay_cls : Type[BaseAssay]
        Concrete assay class.
    conditions : dict[str, Any]
        Assay conditions as Quantity values.
    fit_config : FitConfig
        Fitting configuration whose replicate handling and bounds apply.
    level : float
        Confidence level of the interval, between 0 and 1.
    should_cancel : Callable[[], bool], optional
        Asked before every Ka the profile evaluates whether to stop.

    Returns
    -------
    ProfileResult

    Raises
    ------
    ValueError
        For an assay without a single binding constant, a level outside
        (0, 1), invalid Ka bounds, Ka bounds the equilibrium model cannot be
        solved anywhere within, or too few data points to leave any degrees of
        freedom.
    FitCancelled
        If *should_cancel* returns True.
    """
    if not 0.0 < level < 1.0:
        raise ValueError(f'The confidence level must lie between 0 and 1, got {level}.')
    assay = ms.to_assay(assay_cls, conditions=conditions, use_average=True)
    _require_supported(assay.assay_type)

    bounds = _resolve_bounds(assay, fit_config.custom_bounds)
    y_avg = ms.average_signal(active_only=True)[np.newaxis, :]
    ka_key, (lo, hi), ssr_at = _profile_function(assay, bounds, y_avg)
    ssr_at = _cancellable(ssr_at, should_cancel)
    ss_tot = float(_ss_tot(y_avg)[0])

    # Every plotted curve: the average first, then each active replicate's own.
    replica_ids = list(ms.active_replica_ids) if fit_config.per_replica else []
    y_curves = np.vstack([y_avg, *(ms.get_replica_signal(rid) for rid in replica_ids)])
    _, _, curves_ssr_at = _profile_function(assay, bounds, y_curves)
    curves_ssr_at = _cancellable(curves_ssr_at, should_cancel)
    curves_ss_tot = _ss_tot(y_curves)
    grid = _ka_grid(lo, hi, _PROFILE_PER_DECADE)
    curves_ssr = np.array([curves_ssr_at(ka) for ka in grid])
    ssr = curves_ssr[:, 0]
    best_ka, best_ssr = _refine_best(lambda ka: ssr_at(ka)[0], grid, ssr)
    if not np.isfinite(best_ssr):
        raise ValueError(
            f'The binding model has no solution at any association constant between {lo:g} and '
            f'{hi:g} M⁻¹, so there is no curve to show. Lower its upper bound under Parameter '
            'Bounds and fit again.'
        )

    # Equal Ka bounds fix Ka: nothing is estimated but the coefficients, and
    # there is no interval for a value the fit was not free to move.
    ka_pinned = lo == hi
    n_points = y_avg.size
    n_params = _design_rank(assay, bounds, best_ka) + (0 if ka_pinned else 1)
    dof = n_points - n_params
    if dof < 1:
        raise ValueError(
            f'The data have {n_points} points, too few to judge {n_params} fitted parameters. '
            'Add titration points to get a confidence interval for Ka.'
        )
    ssr_threshold = best_ssr * (1.0 + f_dist.ppf(level, 1, dof) / dof)
    if ka_pinned:
        ci, ci_open, ci_split, ci_unsolvable = (best_ka, best_ka), (False, False), False, (False, False)
    else:
        ci, ci_open, ci_split, ci_unsolvable = _interval(
            lambda ka: ssr_at(ka)[0] - ssr_threshold, grid, ssr - ssr_threshold, best_ka
        )

    # The curves as drawn: the best fit, the interval and the cut-off come from the
    # regular grid alone, whatever points drawing adds. The drawn curve peaks at
    # the best fit and crosses the cut-off where the interval ends.
    grid, curves_ssr = _follow_curves(curves_ssr_at, curves_ss_tot, grid, curves_ssr)
    marks = [best_ka] + [edge for edge, is_open in zip(ci, ci_open) if not is_open]
    grid, curves_ssr = _with_points(curves_ssr_at, grid, curves_ssr, marks)
    curves_r2 = np.where(np.isfinite(curves_ssr), 1.0 - curves_ssr / curves_ss_tot, np.nan)
    replica_r2 = None
    if fit_config.per_replica:
        replica_r2 = {rid: curves_r2[:, i] for i, rid in enumerate(replica_ids, start=1)}

    return ProfileResult(
        ka_key=ka_key,
        grid=grid,
        r2=curves_r2[:, 0],
        replica_r2=replica_r2,
        best_ka=best_ka,
        best_r2=float(1.0 - best_ssr / ss_tot),
        level=level,
        ci=ci,
        ci_open=ci_open,
        r2_threshold=float(1.0 - ssr_threshold / ss_tot),
        n_points=n_points,
        n_params=n_params,
        per_replica=fit_config.per_replica,
        ka_pinned=ka_pinned,
        ci_split=ci_split,
        ci_unsolvable=ci_unsolvable,
    )


def _cancellable(ssr_at: Callable, should_cancel: Callable[[], bool] | None) -> Callable:
    """*ssr_at* asking *should_cancel* first, so a profile stops at its next Ka.

    Every Ka the profile evaluates — the grid, the drawn curves, the refinement
    and the interval's root finding — goes through one of these functions, so
    this is the only check the profile needs.
    """
    if should_cancel is None:
        return ssr_at

    def checked(ka: float):
        if should_cancel():
            raise FitCancelled('The Ka profile was stopped.')
        return ssr_at(ka)

    return checked


def _require_supported(assay_type: AssayType) -> None:
    if not profile_supported(assay_type):
        raise ValueError(
            f'The {assay_type.name} model does not have exactly one binding constant with every other '
            'parameter a signal offset or coefficient, so it has no exact Ka profile.'
        )


def _ss_tot(y: np.ndarray) -> np.ndarray:
    """Total sum of squares of each signal row about its own mean."""
    return np.sum((y - y.mean(axis=1, keepdims=True)) ** 2, axis=1)


def _ka_grid(lo: float, hi: float, per_decade: int) -> np.ndarray:
    """Log-spaced Ka grid with at least *per_decade* points per decade; one point when Ka is pinned."""
    if lo == hi:
        return np.array([lo])
    return np.geomspace(lo, hi, int(np.ceil(np.log10(hi / lo) * per_decade)) + 1)


def _follow_curves(
    ssr_at: Callable[[float], np.ndarray], ss_tot: np.ndarray, grid: np.ndarray, ssr: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """*grid* with exact points added until straight lines between them follow every curve.

    *ssr_at* gives each curve's best SSR at a Ka, *ss_tot* each curve's total
    sum of squares and *ssr* each curve's SSR on *grid*. Every stretch between neighbouring points is checked at its
    midpoint in log Ka, which becomes a point. A stretch whose midpoint misses
    the line by more than half its allowance (see ``_CURVE_R2_TOL``) on any curve
    at R² 0 or above is split, the worst first, until none is left or the
    evaluations reach ``_CURVE_MAX_EXTRA``. Curves below R² 0 across a stretch
    are off every plot and do not split it, and neither does a curve the model
    cannot solve somewhere on the stretch, which is not drawn across it.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        ``(Ka values, SSR per curve)`` in ascending Ka, shapes ``(n,)`` and ``(n, n_curves)``.
    """
    kas, ssrs = list(grid), list(ssr)
    peak = np.max(1.0 - ssr / ss_tot, axis=0)
    # Stretches to split, worst first: (-worst miss over allowance, tie-breaker, Ka and SSR at start, middle, end).
    to_split: list[tuple] = []

    def check(ka_a: float, ssr_a: np.ndarray, ka_b: float, ssr_b: np.ndarray) -> None:
        log_a, log_b = np.log10(ka_a), np.log10(ka_b)
        if log_b - log_a <= _CURVE_MIN_STEP:
            return
        ka_m = 10.0 ** (0.5 * (log_a + log_b))
        ssr_m = ssr_at(ka_m)
        kas.append(ka_m)
        ssrs.append(ssr_m)
        drawn = np.isfinite(ssr_a) & np.isfinite(ssr_m) & np.isfinite(ssr_b)
        if not drawn.any():
            return
        r2_a, r2_m, r2_b = (1.0 - s[drawn] / ss_tot[drawn] for s in (ssr_a, ssr_m, ssr_b))
        top = np.maximum(np.maximum(r2_a, r2_b), r2_m)
        allowance = _CURVE_R2_TOL + _CURVE_DEPTH_TOL * (peak[drawn] - top)
        miss = np.where(top >= 0.0, np.abs(r2_m - 0.5 * (r2_a + r2_b)) / (0.5 * allowance), 0.0)
        if miss.max() > 1.0:
            heapq.heappush(to_split, (-float(miss.max()), len(kas), ka_a, ssr_a, ka_m, ssr_m, ka_b, ssr_b))

    for i in range(grid.size - 1):
        check(grid[i], ssrs[i], grid[i + 1], ssrs[i + 1])
    while to_split and len(kas) - grid.size + 2 <= _CURVE_MAX_EXTRA:
        _, _, ka_a, ssr_a, ka_m, ssr_m, ka_b, ssr_b = heapq.heappop(to_split)
        check(ka_a, ssr_a, ka_m, ssr_m)
        check(ka_m, ssr_m, ka_b, ssr_b)
    order = np.argsort(kas)
    return np.array(kas)[order], np.array(ssrs)[order]


def _with_points(
    ssr_at: Callable[[float], np.ndarray], grid: np.ndarray, ssr: np.ndarray, kas: list[float]
) -> tuple[np.ndarray, np.ndarray]:
    """*grid* and its per-curve *ssr* with the Ka values *kas* added in order, each evaluated by *ssr_at*."""
    new = [ka for ka in kas if not np.any(np.isclose(grid, ka, rtol=1e-12, atol=0.0))]
    if not new:
        return grid, ssr
    all_ka = np.concatenate([grid, new])
    all_ssr = np.vstack([ssr, [ssr_at(ka) for ka in new]])
    order = np.argsort(all_ka, kind='stable')
    return all_ka[order], all_ssr[order]


def _split_keys(assay: BaseAssay) -> tuple[str, list[str]]:
    """(binding-constant key, coefficient keys in parameter order)."""
    kinds = assay.registry_metadata.param_kinds
    ka_key = next(k for k in assay.parameter_keys if kinds[k] is ParamKind.BINDING_CONSTANT)
    return ka_key, [k for k in assay.parameter_keys if k != ka_key]


def _float_bounds(assay: BaseAssay, bounds: dict[str, tuple[Quantity, Quantity]]) -> dict[str, tuple[float, float]]:
    """Bounds as floats in each parameter's canonical unit."""
    units = ASSAY_REGISTRY[assay.assay_type].units
    return {k: (float(lo.to(units[k]).magnitude), float(hi.to(units[k]).magnitude)) for k, (lo, hi) in bounds.items()}


def _design(assay: BaseAssay, ka_key: str, coef_keys: list[str], ka: float) -> np.ndarray:
    """Signal columns at fixed Ka: one per coefficient, set to one with the others zero."""
    keys = assay.parameter_keys
    columns = []
    for key in coef_keys:
        params = np.zeros(len(keys))
        params[keys.index(ka_key)] = ka
        params[keys.index(key)] = 1.0
        columns.append(assay.forward_model(params).magnitude)
    return np.column_stack(columns)


def _profile_function(
    assay: BaseAssay, bounds: dict[str, tuple[Quantity, Quantity]], y: np.ndarray
) -> tuple[str, tuple[float, float], Callable[[float], np.ndarray]]:
    """Ka key, Ka bounds, and a function giving each signal row's best SSR at a Ka."""
    ka_key, coef_keys = _split_keys(assay)
    fb = _float_bounds(assay, bounds)
    lo, hi = fb[ka_key]
    if not 0.0 < lo <= hi:
        raise ValueError(
            f'The bounds of {ka_key} must be positive, with the lower one not above the upper one; '
            f'they are {lo:g} to {hi:g} 1/M.'
        )
    lb, ub = _coefficient_bounds(fb, coef_keys)

    def ssr_at(ka: float) -> np.ndarray:
        return _solve(_design(assay, ka_key, coef_keys, ka), lb, ub, y)[0]

    return ka_key, (lo, hi), ssr_at


def _coefficient_bounds(fb: dict[str, tuple[float, float]], coef_keys: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Lower and upper coefficient bounds, in *coef_keys* order."""
    return np.array([fb[k][0] for k in coef_keys]), np.array([fb[k][1] for k in coef_keys])


def _solve(design: np.ndarray, lb: np.ndarray, ub: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Each signal row's best SSR and coefficients on one design.

    A pinned coefficient (equal lower and upper bound) contributes a fixed
    signal and leaves the solve; the others are solved by bounded least squares
    on norm-scaled columns, which keeps coefficients spanning many orders of
    magnitude well conditioned. The solver can return a coefficient a rounding
    step beyond its bound, so each is clipped to its bounds after unscaling and
    the SSR is that of the clipped coefficients.

    A design the equilibrium model could not fill in is not a model signal at
    all, so it fits nothing: its SSR is infinite and its coefficients stay at
    their lower bounds.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        ``(SSR per row, coefficients per row)``, shapes ``(n_rows,)`` and
        ``(n_rows, n_coefficients)``.
    """
    coef = np.tile(lb, (y.shape[0], 1))
    if not np.isfinite(design).all():
        return np.full(y.shape[0], np.inf), coef
    pinned = lb == ub
    target = y - design[:, pinned] @ lb[pinned]
    free = design[:, ~pinned]
    if free.shape[1] == 0:
        return np.sum(target**2, axis=1), coef
    scale = np.linalg.norm(free, axis=0)
    scale[scale == 0] = 1.0
    scaled = free / scale
    ssr = np.empty(y.shape[0])
    for i, row in enumerate(target):
        sol = lsq_linear(scaled, row, bounds=(lb[~pinned] * scale, ub[~pinned] * scale), method='bvls')
        coef[i, ~pinned] = np.clip(sol.x / scale, lb[~pinned], ub[~pinned])
        ssr[i] = np.sum((free @ coef[i, ~pinned] - row) ** 2)
    return ssr, coef


def _design_rank(assay: BaseAssay, bounds: dict[str, tuple[Quantity, Quantity]], ka: float) -> int:
    """Numerical rank of the free (unpinned) coefficient columns at *ka*."""
    ka_key, coef_keys = _split_keys(assay)
    fb = _float_bounds(assay, bounds)
    free = [i for i, k in enumerate(coef_keys) if fb[k][0] != fb[k][1]]
    if not free:
        return 0
    design = _design(assay, ka_key, coef_keys, ka)[:, free]
    scale = np.linalg.norm(design, axis=0)
    scale[scale == 0] = 1.0
    return int(np.linalg.matrix_rank(design / scale, rtol=_RANK_RTOL))


def _refine_best(ssr_fn: Callable[[float], float], grid: np.ndarray, ssr_grid: np.ndarray) -> tuple[float, float]:
    """Minimum of *ssr_fn*, refined in log Ka between the best grid point's neighbours.

    A neighbour the model cannot solve (infinite SSR) is no bracket, so the
    refinement stops at the grid point on that side.
    """
    i = int(np.argmin(ssr_grid))
    lo_i = i - 1 if i > 0 and np.isfinite(ssr_grid[i - 1]) else i
    hi_i = i + 1 if i + 1 < grid.size and np.isfinite(ssr_grid[i + 1]) else i
    if lo_i == hi_i:
        return float(grid[i]), float(ssr_grid[i])
    a = np.log10(grid[lo_i])
    b = np.log10(grid[hi_i])
    res = minimize_scalar(lambda t: ssr_fn(10.0**t), bounds=(a, b), method='bounded', options={'xatol': _LOG_KA_XTOL})
    if res.fun < ssr_grid[i]:
        return float(10.0**res.x), float(res.fun)
    return float(grid[i]), float(ssr_grid[i])


def _interval(
    excess_fn: Callable[[float], float], grid: np.ndarray, excess_grid: np.ndarray, best_ka: float
) -> tuple[tuple[float, float], tuple[bool, bool], bool, tuple[bool, bool]]:
    """Envelope of the Ka values with non-positive excess, edges refined by root finding.

    *excess_fn* is the combined SSR minus the threshold, which *best_ka* always
    clears. An edge with no grid point beyond it is open at the Ka bound. So is
    an edge whose next grid point is a Ka the model cannot be solved at: the
    data reject nothing there, the profile simply stops, and the edge is the
    last Ka it could be evaluated at. A grid point inside the envelope that the
    excess rejects means the accepted Ka values are not one connected stretch;
    the envelope then spans a gap.

    Returns
    -------
    tuple[tuple[float, float], tuple[bool, bool], bool, tuple[bool, bool]]
        ``((low, high), (low open, high open), split, (low unsolvable, high unsolvable))``.
    """
    accepted = excess_grid <= 0
    inside = np.append(grid[accepted], best_ka)
    low_in, high_in = float(inside.min()), float(inside.max())
    below_of, above_of = grid < low_in, grid > high_in
    below, above = grid[below_of], grid[above_of]
    low_unsolvable = bool(below.size and not np.isfinite(excess_grid[below_of][-1]))
    high_unsolvable = bool(above.size and not np.isfinite(excess_grid[above_of][0]))

    def edge(outside: float, within: float) -> float:
        def excess(s: float) -> float:
            value = excess_fn(10.0**s)
            return float(value) if np.isfinite(value) else _UNSOLVABLE_EXCESS

        t = brentq(excess, np.log10(outside), np.log10(within), xtol=_LOG_KA_XTOL)
        return float(10.0**t)

    if not below.size:
        low = float(grid[0])
    elif low_unsolvable:
        low = low_in
    else:
        low = edge(below[-1], low_in)
    if not above.size:
        high = float(grid[-1])
    elif high_unsolvable:
        high = high_in
    else:
        high = edge(above[0], high_in)
    split = bool(np.any(~accepted & (grid >= low_in) & (grid <= high_in)))
    open_at = (below.size == 0 or low_unsolvable, above.size == 0 or high_unsolvable)
    return (low, high), open_at, split, (low_unsolvable, high_unsolvable)
