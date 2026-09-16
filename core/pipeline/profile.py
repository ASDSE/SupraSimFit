"""Exact Ka profile for assays with one binding constant.

When an assay has exactly one binding constant and every other parameter is a
signal offset or coefficient, the model signal is linear in those other
parameters once Ka is fixed. The best fit at a fixed Ka is then a bounded
linear least-squares solve, so the best achievable R² at every Ka is exact.
That curve is the profile: it bounds every fit the optimizer can find, locates
the global best fit without a multi-start search, and gives a
profile-likelihood confidence interval for Ka from an F test.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Type

import numpy as np
from scipy.optimize import brentq, lsq_linear, minimize_scalar
from scipy.stats import f as f_dist

from core.assays.base import BaseAssay
from core.assays.registry import ASSAY_REGISTRY, AssayType, ParamKind
from core.data_processing.measurement_set import MeasurementSet
from core.pipeline.fit_pipeline import FitConfig, _resolve_bounds
from core.units import Quantity

# Ka grid densities, in points per decade across the Ka bounds. The search grid
# only has to land next to the optimum (a bounded refinement finds it between
# the neighbouring points); the profile grid is the plotted curve.
_SEARCH_PER_DECADE = 4
_PROFILE_PER_DECADE = 20

# Tolerance of the refinement and of the interval edges, in decades of Ka.
_LOG_KA_XTOL = 1e-7

# Relative singular-value cut-off for the rank of the norm-scaled coefficient
# design. The equilibrium solve is iterative, so an exact linear dependence
# between species columns (free plus bound dye summing to a fixed total, say)
# leaves a singular value of order 1e-11 rather than zero, while independent
# columns stay above 1e-6 across the Ka range.
_RANK_RTOL = 1e-8

_LINEAR_KINDS = (ParamKind.SIGNAL_OFFSET, ParamKind.SIGNAL_COEFFICIENT)


@dataclass
class ProfileResult:
    """Best achievable R² across Ka and the confidence interval it implies.

    Attributes
    ----------
    ka_key : str
        The binding-constant parameter key (e.g. ``"Ka_guest"``).
    grid : np.ndarray
        Ka values in 1/M, log-spaced across the Ka bounds in force.
    r2 : np.ndarray
        Best R² of the averaged signal at each grid Ka.
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
        ``(low, high)`` Ka in 1/M: the range of Ka whose residual sum of
        squares stays within the F-test threshold.
    ci_open : tuple[bool, bool]
        ``True`` on a side where the interval runs into the Ka bound, so the
        data do not limit Ka there.
    r2_threshold : float
        R² at which the interval is cut.
    n_points : int
        Number of points in the averaged signal.
    n_params : int
        Parameter count ``p`` of the F test: one for Ka plus the numerical rank
        of the coefficient design at the optimum.
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
    """Global best fit of one signal, found through its exact Ka profile.

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
    """Parameter vector of the global best fit of one signal.

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

    Returns
    -------
    ProfileResult

    Raises
    ------
    ValueError
        For an assay without a single binding constant, a level outside
        (0, 1), invalid Ka bounds, or too few data points to leave any
        degrees of freedom.
    """
    if not 0.0 < level < 1.0:
        raise ValueError(f'The confidence level must lie between 0 and 1, got {level}.')
    assay = ms.to_assay(assay_cls, conditions=conditions, use_average=True)
    _require_supported(assay.assay_type)

    bounds = _resolve_bounds(assay, fit_config.custom_bounds)
    y_avg = ms.average_signal(active_only=True)[np.newaxis, :]
    ka_key, (lo, hi), ssr_at = _profile_function(assay, bounds, y_avg)
    ss_tot = float(_ss_tot(y_avg)[0])

    grid = _ka_grid(lo, hi, _PROFILE_PER_DECADE)
    ssr = np.array([ssr_at(ka)[0] for ka in grid])
    best_ka, best_ssr = _refine_best(lambda ka: ssr_at(ka)[0], grid, ssr)

    n_points = y_avg.size
    n_params = 1 + _design_rank(assay, bounds, best_ka)
    dof = n_points - n_params
    if dof < 1:
        raise ValueError(
            f'The data have {n_points} points, too few to judge {n_params} fitted parameters. '
            'Add titration points to get a confidence interval for Ka.'
        )
    ssr_threshold = best_ssr * (1.0 + f_dist.ppf(level, 1, dof) / dof)
    ci, ci_open = _interval(lambda ka: ssr_at(ka)[0] - ssr_threshold, grid, ssr - ssr_threshold, best_ka)

    replica_r2 = None
    if fit_config.per_replica:
        replica_ids = list(ms.active_replica_ids)
        y_reps = np.vstack([ms.get_replica_signal(rid) for rid in replica_ids])
        _, _, replica_ssr_at = _profile_function(assay, bounds, y_reps)
        replica_ssr = np.array([replica_ssr_at(ka) for ka in grid])  # (n_grid, n_replicas)
        replica_ss_tot = _ss_tot(y_reps)
        replica_r2 = {rid: 1.0 - replica_ssr[:, i] / replica_ss_tot[i] for i, rid in enumerate(replica_ids)}

    return ProfileResult(
        ka_key=ka_key,
        grid=grid,
        r2=1.0 - ssr / ss_tot,
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
    )


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

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        ``(SSR per row, coefficients per row)``, shapes ``(n_rows,)`` and
        ``(n_rows, n_coefficients)``.
    """
    pinned = lb == ub
    target = y - design[:, pinned] @ lb[pinned]
    coef = np.tile(lb, (y.shape[0], 1))
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
    """Minimum of *ssr_fn*, refined in log Ka between the best grid point's neighbours."""
    i = int(np.argmin(ssr_grid))
    if grid.size == 1:
        return float(grid[0]), float(ssr_grid[0])
    a = np.log10(grid[max(i - 1, 0)])
    b = np.log10(grid[min(i + 1, grid.size - 1)])
    res = minimize_scalar(lambda t: ssr_fn(10.0**t), bounds=(a, b), method='bounded', options={'xatol': _LOG_KA_XTOL})
    if res.fun < ssr_grid[i]:
        return float(10.0**res.x), float(res.fun)
    return float(grid[i]), float(ssr_grid[i])


def _interval(
    excess_fn: Callable[[float], float], grid: np.ndarray, excess_grid: np.ndarray, best_ka: float
) -> tuple[tuple[float, float], tuple[bool, bool]]:
    """Envelope of the Ka values with non-positive excess, edges refined by root finding.

    *excess_fn* is the combined SSR minus the threshold, which *best_ka* always
    clears. An edge with no grid point beyond it is open at the Ka bound.
    """
    inside = np.append(grid[excess_grid <= 0], best_ka)
    low_in, high_in = float(inside.min()), float(inside.max())
    below, above = grid[grid < low_in], grid[grid > high_in]

    def edge(outside: float, within: float) -> float:
        t = brentq(lambda s: excess_fn(10.0**s), np.log10(outside), np.log10(within), xtol=_LOG_KA_XTOL)
        return float(10.0**t)

    low = edge(below[-1], low_in) if below.size else float(grid[0])
    high = edge(above[0], high_in) if above.size else float(grid[-1])
    return (low, high), (below.size == 0, above.size == 0)
