"""Ka profiles and the joint region drawn on the Identifiability tab.

The engine in :mod:`core.pipeline.varpro` gives, at any value of one binding
constant, the best residual the model can reach with every other parameter
free: the coefficients by an exact bounded linear least-squares solve, another
binding constant by a search along its axis. That curve is the profile. This
module draws it across the Ka bounds in force for every binding constant of the
fitted model, adding points wherever straight lines between them would miss the
exact curve, and for a model with two free binding constants also maps the
joint confidence region of the pair. The best fit, the intervals and the cut-offs are
the engine's own numbers for the averaged signal, computed by the same calls
the fit makes, so the tab shows the fit it belongs to and nothing else.

Where the inputs were stated with an uncertainty, the fit's penalised profile
comes with it (:class:`~core.pipeline.input_aware.AwareProfile`): the second
curve, its own interval and its own cut-off, drawn beside the one above. It is
the fit's own working, handed over rather than computed again.

The equilibrium models report a Ka they have no speciation for as species that
are not a number, rather than by raising. Such a Ka has no fit at all, so its
residual sum of squares is infinite, it never enters the interval and no curve
is drawn across it. Every model profiled here has a solution at every
association constant and every set of totals the app's bounds allow and far
beyond them; they report no number where the free concentration they solve for
falls below the smallest normal double, which takes a constant near 1e300 1/M
against a binding partner in large excess, where a constant times a total
passes the range of a double, which no sub-molar total reaches, or, in the
stepwise models, where the product of both constants with the square of the
free ligand does, near 1e155 1/M each at micromolar totals. This is a contract
the profile keeps with the models, not a range of Ka it runs into.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Any, Callable, Type

import numpy as np

from core.assays.base import BaseAssay
from core.data_processing.measurement_set import MeasurementSet
from core.pipeline.fit_pipeline import FitConfig, _resolve_bounds
from core.pipeline.input_aware import AwareProfile, AwareResult, input_aware
from core.pipeline.inputs import constraints
from core.pipeline.varpro import (
    _PROFILE_PER_DECADE,
    _SEARCH_PER_DECADE,
    LEVEL,
    KaInterval,
    Projection,
    _interval,
    _ka_grid,
)

# The plotted curve joins exact points with straight lines. A stretch of it is
# split while the exact R² at its midpoint misses the line by more than half of
# its allowance, _CURVE_R2_TOL + _CURVE_DEPTH_TOL × (the curve's best R² − the
# stretch's highest R²); a stretch that bends one way then stays within the
# allowance of the exact curve. At the peak that is 1e-6 R². Below it, the
# allowance is 0.1 % of the depth, so in any view that shows a stretch together
# with the peak the line is off by less than 0.1 % of the view's height. The
# curve has corners where a coefficient reaches its bound and jumps where a Ka
# the model has no speciation for interrupts it, so the stretches with the worst
# miss for their allowance are split first, a budget of extra evaluations bounds
# the work, and _CURVE_MIN_STEP, in decades of Ka, stops the splitting at a
# corner or a jump.
#
# _CURVE_MAX_EXTRA bounds a curve of a model with one free binding constant,
# which starts from _PROFILE_PER_DECADE points and costs one solve per point. It
# is a bound on the work, not a limit the curves meet: over 96 profiles of
# synthetic GDA, IDA and DBA titrations (host 1e-7 to 1e-4 M, Ka·h0 0.1 to 1e5,
# 8 to 30 points, noise 0.1 to 5 %, across the default Ka bounds and across 1e2
# to 1e16 1/M) the largest number of extra evaluations is 796, the median 510.
#
# _CURVE_MAX_EXTRA_TWO_KA bounds each curve of a model with two free binding
# constants, which starts from the _SEARCH_PER_DECADE nodes of the search grid.
# There a point costs a minimisation over the other Ka: at a node the scan of
# the other axis is read from the engine's cached grid and only its refinements
# are solved; anywhere else the axis is scanned as well, about a hundred
# equilibrium solves on the default box (1e-8 to 1e12 1/M, 81 nodes per curve).
# Measured on HG2 and H2G titrations of 30 points on that box at noise 0.5 to
# 5 % of the range, the drawn curve stays within its allowance everywhere at
# this budget (worst miss 0.7 of the allowance, 6e-6 R²), while a budget of 100
# leaves misses of 4 allowances (2.5e-5 R²); left unbounded the curves ask for
# 300 to 450 extra points each, at twice the cost, for misses of 0.1 to 0.3 of
# the allowance.
#
# What a caller waits for is the whole fit_profile call, which is the two
# curves, the _REGION_POINTS² exact solves of the joint region and the marks on
# top of the engine's own fit and intervals: 15 s (HG2) and 17 s (H2G) on one
# idle core at 30 points on the default box, against 0.3 s for a model with one
# free binding constant.
_CURVE_R2_TOL = 1e-6
_CURVE_DEPTH_TOL = 1e-3
_CURVE_MAX_EXTRA = 2000
_CURVE_MAX_EXTRA_TWO_KA = 200
_CURVE_MIN_STEP = 1e-6

# Points per axis of the joint region's grid. The region panel is a few hundred
# pixels wide, so 64 cells across it are about 5 px each, below what the eye
# resolves in a filled map; each cell is one exact solve.
_REGION_POINTS = 64


@dataclass
class ProfileResult:
    """Best achievable R² across one binding constant and the interval it implies.

    Attributes
    ----------
    ka_key : str
        The binding-constant parameter key (e.g. ``"Ka_guest"``).
    grid : np.ndarray
        Ka values in 1/M across the Ka bounds in force, ascending: a log-spaced
        grid plus the best fit, the interval's closed edges and extra points
        where the curves bend, so straight lines between them follow the exact
        curves (see ``_CURVE_R2_TOL``). One point when Ka is pinned.
    r2 : np.ndarray
        Best R² of the averaged signal at each grid Ka, minimised over every
        other parameter; ``nan`` at a Ka the equilibrium model cannot solve,
        which has no fit to draw.
    replica_r2 : dict[str, np.ndarray] | None
        Each active replicate's own best-R² curve on ``grid``; ``None`` unless
        the fit ran per replicate and this is the model's only free binding
        constant.
    best_ka : float
        Ka (1/M) of the best fit of the averaged signal.
    best_r2 : float
        R² at ``best_ka``.
    interval : KaInterval | None
        The confidence interval of this Ka; ``None`` when Ka is pinned by equal
        bounds, which leaves no interval to estimate.
    r2_threshold : float
        R² at which the interval is cut wherever the fit at the tested Ka pins
        no signal parameter the best fit leaves free: the plain F test of one
        constrained Ka. With a pinned Ka there is no interval and the cut is
        the R² a one-parameter improvement would have to beat.
    n_points : int
        Number of points in the averaged signal.
    n_params : int
        Parameter count ``p`` of the F test: the numerical rank of the
        coefficient design at the optimum plus the free binding constants.
    per_replica : bool
        Whether the fit this profile belongs to ran each replicate separately.
    aware : AwareProfile | None
        The same profile with the inputs free to move within the uncertainties
        stated for them: its own grid, R² curve, cut-off and interval.
        ``None`` when no input was free to move, where it would be this curve
        again.
    r2_cut : np.ndarray
        R² the fit at each grid Ka is judged against
        (:meth:`~core.pipeline.varpro.Projection.cut_off`): ``r2_threshold``,
        and lower over every stretch where the fit holds a signal parameter on
        a bound that the best fit leaves free, by one numerator degree of
        freedom of the F test per such parameter. ``r2_threshold`` at every
        point when left out.
    """

    ka_key: str
    grid: np.ndarray
    r2: np.ndarray
    replica_r2: dict[str, np.ndarray] | None
    best_ka: float
    best_r2: float
    interval: KaInterval | None
    r2_threshold: float
    n_points: int
    n_params: int
    per_replica: bool
    aware: AwareProfile | None = None
    r2_cut: np.ndarray | None = None

    def __post_init__(self) -> None:
        if self.r2_cut is None:
            self.r2_cut = np.full(self.grid.shape, self.r2_threshold)


@dataclass
class JointRegion:
    """Joint confidence region of a model's two binding constants.

    Attributes
    ----------
    ka_keys : tuple[str, str]
        The two binding-constant keys, in parameter order.
    x, y : np.ndarray
        Ka values in 1/M of the first and the second key, ascending and
        log-spaced over the region's bounding box: the two one-dimensional
        intervals cut at the joint cut-off of each profile point (``r2_cut``
        along the profile), clipped to the Ka bounds.
    r2 : np.ndarray
        Best R² of the averaged signal at every ``(x[i], y[j])``, shape
        ``(len(x), len(y))``; ``nan`` where the equilibrium model has no
        solution.
    r2_threshold : float
        R² at which the region is cut wherever the fit at a pair pins no signal
        parameter the best fit leaves free: the joint F test with two
        constrained binding constants.
    level : float
        Confidence level of the region.
    best : tuple[float, float]
        The best fit's Ka pair, in ``ka_keys`` order.
    r2_cut : np.ndarray
        R² the fit at every ``(x[i], y[j])`` is judged against, shape of
        ``r2``: ``r2_threshold``, and lower where the fit holds a signal
        parameter on a bound that the best fit leaves free. The region is
        ``r2 >= r2_cut``. ``r2_threshold`` at every pair when left out.
    """

    ka_keys: tuple[str, str]
    x: np.ndarray
    y: np.ndarray
    r2: np.ndarray
    r2_threshold: float
    level: float
    best: tuple[float, float]
    r2_cut: np.ndarray | None = None

    def __post_init__(self) -> None:
        if self.r2_cut is None:
            self.r2_cut = np.full(self.r2.shape, self.r2_threshold)


@dataclass
class ProfileSet:
    """Every profile of one fit and, for two free binding constants, their joint region.

    Attributes
    ----------
    profiles : dict[str, ProfileResult]
        One profile per binding constant of the model, in parameter order.
    region : JointRegion | None
        The joint region of the pair; ``None`` unless the model has two free
        binding constants.
    """

    profiles: dict[str, ProfileResult]
    region: JointRegion | None


def fit_profile(
    ms: MeasurementSet,
    assay_cls: Type[BaseAssay],
    conditions: dict[str, Any],
    fit_config: FitConfig,
    *,
    level: float = LEVEL,
    should_cancel: Callable[[], bool] | None = None,
    aware: AwareResult | None = None,
) -> ProfileSet:
    """Profiles of the averaged signal, their intervals and, for two free Ka, the joint region.

    The curves, the best fit and the intervals describe the average of the
    active replicates, whose systematic departure from the model repeats in
    every replicate: counting each replicate's points as separate evidence
    would overstate how precisely the data pin Ka down. The best fit and the
    intervals come from the same engine calls a fit of the same replicates
    makes, so they equal the fit's exactly. ``fit_config.custom_bounds``
    applies throughout; with ``fit_config.per_replica`` a model with one free
    binding constant also carries each replicate's own curve in
    ``replica_r2``.

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
        Confidence level of the intervals and the region, between 0 and 1.
    should_cancel : Callable[[], bool], optional
        Asked before every equilibrium solve whether to stop.
    aware : AwareResult, optional
        The penalised profiles of the fit being profiled
        (:attr:`~core.pipeline.fit_pipeline.FitResult.aware`), made at this
        *level* on these data with this configuration. They are carried
        through as they are, which is what makes the tab show the fit's own
        interval; left out, they are computed here whenever
        ``fit_config.errors`` lets an input move.

    Returns
    -------
    ProfileSet

    Raises
    ------
    ValueError
        For an assay the engine cannot project, a level outside (0, 1),
        invalid Ka bounds, Ka bounds the equilibrium model cannot be solved
        anywhere within, or too few data points to leave any degrees of
        freedom.
    FitCancelled
        If *should_cancel* returns True.
    """
    if not 0.0 < level < 1.0:
        raise ValueError(f'The confidence level must lie between 0 and 1, got {level}.')
    assay = ms.to_assay(assay_cls, conditions=conditions, use_average=True)
    bounds = _resolve_bounds(assay, fit_config.custom_bounds)

    # The fit itself: the calls a fit of the averaged signal makes, in the same order.
    projection = Projection(assay, bounds, should_cancel=should_cancel)
    fit = projection.fit()
    threshold = projection.threshold(fit, level)
    intervals = {key: projection.interval(key, fit, level) for key in projection.ka_keys}
    ss_tot = float(projection.ss_tot[0])
    errors = fit_config.errors.for_fit()
    if aware is None and (errors.specs or errors.shared):
        aware = input_aware(
            projection,
            fit,
            constraints(errors, assay.get_conditions(), fit_config.input_labels),
            loading=errors.input_offsets if errors.shared else None,
            level=level,
            should_cancel=should_cancel,
            conditional={k: ci for k, ci in intervals.items() if ci is not None},
        )
    # With nothing free to move the penalised profile is this one, so there is
    # no second curve to draw.
    penalised = aware.profiles if aware is not None and aware.constraints else {}
    common = dict(
        best_r2=float(1.0 - fit.objective / ss_tot),
        r2_threshold=float(1.0 - threshold / ss_tot),
        n_points=projection.n_points,
        n_params=projection.n_params(fit),
        per_replica=fit_config.per_replica,
    )

    cut = projection.cut_off(fit, level)

    def result(key: str, grid: np.ndarray, r2: np.ndarray, cuts: dict[float, float], replica_r2=None) -> ProfileResult:
        return ProfileResult(
            ka_key=key,
            grid=grid,
            r2=r2,
            replica_r2=replica_r2,
            best_ka=fit.ka[key],
            interval=intervals[key],
            aware=penalised.get(key),
            r2_cut=1.0 - np.array([cuts[ka] for ka in grid.tolist()]) / ss_tot,
            **common,
        )

    def marks(key: str) -> list[float]:
        """Ka values every drawn curve passes through: the best fit and the interval's closed edges."""
        interval = intervals[key]
        edges = [] if interval is None else [(interval.low, interval.open_low), (interval.high, interval.open_high)]
        return [fit.ka[key]] + [edge for edge, is_open in edges if not is_open]

    profiles: dict[str, ProfileResult] = {}
    region = None
    if len(projection.free_ka) == 2:
        # Each curve is the objective minimised over the other Ka. Its regular
        # points are the search-grid nodes, where the engine reads the scan of
        # the other axis from its cache; the same node values, each against the
        # joint cut-off of its own profile point, cut the joint region's
        # bounding box, the way an interval is cut.
        joint_cut = projection.cut_off(fit, level, n_constrained=2)
        box = {}
        for key in projection.ka_keys:
            cuts: dict[float, float] = {}
            joint_cuts: dict[float, float] = {}

            def profile(ka: float, key: str = key, cuts: dict = cuts, joint_cuts: dict = joint_cuts) -> float:
                _, value, rank = projection.profile_point(key, ka)
                cuts[ka], joint_cuts[ka] = cut(rank), joint_cut(rank)
                return value

            def joint_excess(ka: float, profile=profile, joint_cuts: dict = joint_cuts) -> float:
                return profile(ka) - joint_cuts[ka]

            nodes = _ka_grid(*projection.ka_bounds[key], _SEARCH_PER_DECADE)
            node_ssr = np.array([profile(ka) for ka in nodes.tolist()])
            node_excess = node_ssr - np.array([joint_cuts[ka] for ka in nodes.tolist()])
            box[key] = _interval(joint_excess, nodes, node_excess, fit.ka[key])[0]
            grid, r2 = _draw(
                lambda ka: np.array([profile(ka)]),
                projection.ss_tot,
                nodes,
                node_ssr[:, np.newaxis],
                _CURVE_MAX_EXTRA_TWO_KA,
                marks(key),
            )
            profiles[key] = result(key, grid, r2[:, 0], cuts)
        k1, k2 = projection.ka_keys
        x, y = (np.geomspace(*box[k], _REGION_POINTS) for k in (k1, k2))
        # One solve per pair gives its residual and the rank its cut-off is read at.
        solved = [[projection.solved({k1: a, k2: b}) for b in y] for a in x]
        ssr = np.array([[cell_ssr[0] for cell_ssr, _ in row] for row in solved])
        region = JointRegion(
            ka_keys=(k1, k2),
            x=x,
            y=y,
            r2=np.where(np.isfinite(ssr), 1.0 - ssr / ss_tot, np.nan),
            r2_threshold=float(1.0 - projection.threshold(fit, level, n_constrained=2) / ss_tot),
            level=level,
            best=(fit.ka[k1], fit.ka[k2]),
            r2_cut=1.0 - np.array([[joint_cut(rank) for _, rank in row] for row in solved]) / ss_tot,
        )
    else:
        # Every drawn curve: the average first, then each active replicate's own.
        replica_ids = list(ms.active_replica_ids) if fit_config.per_replica else []
        rows = np.vstack([assay.y_data.magnitude, *(ms.get_replica_signal(rid) for rid in replica_ids)])
        curves = Projection(assay, bounds, signals=rows, should_cancel=should_cancel)
        for key in projection.ka_keys:
            if key not in projection.free_ka:
                # Equal Ka bounds fix Ka: the fit was not free to move it, so
                # its profile is the one point the fit reached.
                profiles[key] = result(
                    key, np.array([fit.ka[key]]), np.array([common['best_r2']]), {fit.ka[key]: threshold}
                )
                continue
            cuts = {}

            def rows(ka: float, key: str = key, cuts: dict[float, float] = cuts) -> np.ndarray:
                # The first row is the averaged signal, whose solve also gives the rank its cut-off is read at.
                ssr, rank = curves.solved({key: ka})
                cuts[ka] = cut(rank)
                return ssr

            nodes = _ka_grid(*projection.ka_bounds[key], _PROFILE_PER_DECADE)
            node_ssr = np.array([rows(ka) for ka in nodes.tolist()])
            grid, r2 = _draw(rows, curves.ss_tot, nodes, node_ssr, _CURVE_MAX_EXTRA, marks(key))
            replica_r2 = (
                {rid: r2[:, i] for i, rid in enumerate(replica_ids, start=1)} if fit_config.per_replica else None
            )
            profiles[key] = result(key, grid, r2[:, 0], cuts, replica_r2)
    return ProfileSet(profiles=profiles, region=region)


def _draw(
    ssr_at: Callable[[float], np.ndarray],
    ss_tot: np.ndarray,
    grid: np.ndarray,
    ssr: np.ndarray,
    max_extra: int,
    marks: list[float],
) -> tuple[np.ndarray, np.ndarray]:
    """The curves as drawn: *grid* with the points *ssr_at* adds, as ``(Ka values, R² per curve)``.

    The best fit, the intervals and the cut-offs come from the regular grid
    alone, whatever points drawing adds; *marks* makes every curve pass
    through the best fit and cross the cut-off where the interval ends.
    """
    grid, ssr = _follow_curves(ssr_at, ss_tot, grid, ssr, max_extra)
    grid, ssr = _with_points(ssr_at, grid, ssr, marks)
    return grid, np.where(np.isfinite(ssr), 1.0 - ssr / ss_tot, np.nan)


def _follow_curves(
    ssr_at: Callable[[float], np.ndarray], ss_tot: np.ndarray, grid: np.ndarray, ssr: np.ndarray, max_extra: int
) -> tuple[np.ndarray, np.ndarray]:
    """*grid* with exact points added until straight lines between them follow every curve.

    *ssr_at* gives each curve's best SSR at a Ka, *ss_tot* each curve's total
    sum of squares and *ssr* each curve's SSR on *grid*. Every stretch between
    neighbouring points is checked at its midpoint in log Ka, which becomes a
    point. A stretch whose midpoint misses the line by more than half its
    allowance (see ``_CURVE_R2_TOL``) on any curve at R² 0 or above is split,
    the worst first, until none is left or the evaluations reach *max_extra*.
    Curves below R² 0 across a stretch are off every plot and do not split it,
    and neither does a curve the model cannot solve somewhere on the stretch,
    which is not drawn across it.

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
    while to_split and len(kas) - grid.size + 2 <= max_extra:
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
