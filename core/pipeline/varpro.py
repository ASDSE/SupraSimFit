"""Variable projection: the fit engine for every binding model.

Every registered binding model is ``y = A(K) c + e``. K holds the binding
constants (one for GDA, IDA and both DBA directions, two for the stepwise
1:2 and 2:1 models), the columns of ``A(K)`` are a column of ones for the
signal offset and the species concentrations of the equilibrium solve at K for
the signal coefficients, and ``c`` are those signal parameters inside their
bounds. The projected functional

    S(K) = min over lb <= c <= ub of ||y - A(K) c||²

is an exact bounded linear least-squares solve, so the least-squares fit of the
whole model is the minimum of S over the Ka box, found by a search in one or
two dimensions of log Ka. For several signal rows with row weights ``w_r``
(replicates) the objective is ``Q(K) = sum_r w_r S_r(K)``: one shared K, each
row its own coefficients.

The profile ``P_j(k) = min over the other binding constants of Q`` bounds every
fit at that value of one Ka, so an F test on it gives a profile-likelihood
confidence interval per Ka, and the same test on the rows of a replicate set
decides whether every replicate shares K.

The F test of a tested Ka compares two fits, and its numerator counts the
parameters the best fit has and the fit at the tested Ka has not. That is the
tested Ka, and every signal parameter the bounded solve holds on a bound there
while the best fit leaves it free: a coefficient on its bound is not fitted.
With ``r(K)`` the rank of the columns whose coefficient lies inside its bounds
at K (:meth:`Projection.fitted_rank`) and ``K_hat`` the best fit,

    m(K)   = constrained Ka + max(0, r(K_hat) - r(K))
    cut(K) = S_min (1 + m(K) F(level; m(K), n - p) / (n - p))

and the interval is ``{k : P_j(k) <= cut}`` at the profile point of k, the other
binding constant where it minimises Q. ``n - p`` is that of the best fit
throughout. Wherever the tested Ka pins nothing the best fit leaves free,
``m`` is the number of constrained Ka and the cut-off is the constant one of the
plain F test; where it does, the cut-off steps up, which is conservative against
the exact mixture of F distributions a bounded parameter follows.

The equilibrium models report a K they have no speciation for as species that
are not a number, rather than by raising. Such a K has no fit at all, so its
residual sum of squares is infinite, it never enters an interval and no curve
crosses it. Inside the default Ka box every registered model has a solution at
every K; the sentinel is reached only far outside it, where a free
concentration falls below the smallest normal double or an intermediate product
passes the range of a double.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable, Mapping, Sequence

import numpy as np
from scipy.optimize import brentq, least_squares, lsq_linear, minimize_scalar
from scipy.stats import f as f_dist

from core.assays.base import BaseAssay
from core.assays.registry import ASSAY_REGISTRY, AssayType, ParamKind
from core.units import Quantity


class FitCancelled(Exception):
    """Raised when a fit stops because its caller asked it to.

    Carried up from the engine through every pipeline entry point, so the
    caller that owns the cancellation flag decides what to show.
    """


class FitRefused(ValueError):
    """Raised where the pipeline refuses to answer, with a message written for the user.

    The message names what in the data, the conditions or the bounds stands in
    the way and what to change, so the interface shows it as it is. Every other
    exception the pipeline lets through — a library's own ``ValueError``, a
    contract broken between two modules — is not written for anyone to read and
    is reported as an unexpected failure instead.
    """


#: Confidence level of every reported interval: the conventional 95 %.
LEVEL = 0.95

#: Family-wise level of the replicate test: the ISO 5725-2 outlier level. A
#: replicate significant at 5 % but not at 1 % is a "straggler" and is kept.
REPLICATE_TEST_LEVEL = 0.01

# Ka grid densities, in points per decade across the Ka bounds. The search grid
# only has to land in the basin of the optimum: the refinement finds it from
# there. Against a 16/decade brute force on 84 random HG2/H2G designs (K 1e1 to
# 1e9, h0 10^-6.5 to 10^-3 M, 8 to 30 points, noise 0.2 to 8 %) the 4/decade
# search was never beaten by more than 1.2e-6 relative SSR. The profile grid is
# where a one-Ka interval scans and a drawn curve starts.
_SEARCH_PER_DECADE = 4
_PROFILE_PER_DECADE = 20

# Density of the scan over the other Ka wherever a two-Ka interval is decided:
# its edges, and the search cells read at the profile density. Cut at a fixed
# value of one constant, the K₁·K₂ valley of the stepwise models can lie on the
# slope of a broader valley and then leaves no local minimum on a 4/decade scan,
# so the profile reads too high over a stretch of up to 0.1 decade; next to an
# edge that ends the interval up to 0.08 decade short of Ka the test accepts, and
# on a search node it reports a gap that is not there (4 of 10 800 HG2/H2G
# intervals). At 16/decade the edges of those four lie on the threshold of an
# independent 16/decade profile that reads the same at 64/decade. It costs a
# two-Ka interval about a second.
_INNER_PER_DECADE = 16

# Share of the residual rise the F test allows (threshold minus the best
# residual) by which, at a closed edge of a two-Ka interval, the residual must
# rise over the last search-grid step of the other Ka before its bound for the
# edge to be put down to that bound (see ``Projection._bound_behind``). On 120
# random HG2/H2G designs with 169 closed edges, the 93 edges that move when both
# Ka bounds are widened by three decades show a rise of 0.016 or more of the
# allowed one, and the 76 that stay show 1.6e-4 or less — the other Ka sits on
# its bound at 8 of those, on a residual that no longer changes towards it. 1e-3
# is in the gap; by the curvature of the profile, a bound that owes an edge less
# than that moves it by under 0.05 % of the interval's half-width.
_BOUND_RISE = 1e-3

# Grid local minima refined in a two-Ka search. On the same 84 designs the worst
# relative SSR miss against the brute force is 3.4e-5 with one start, 3.8e-6
# with two, 2.5e-6 with three, 1.2e-6 with five and 5e-9 with eight; every one
# of these is far below the interval threshold (relative F/(n - p) of 0.1 or
# more), and five starts cost under 0.3 s.
_N_REFINE = 5

# Tolerance of the one-dimensional refinement and of the interval edges, in
# decades of Ka.
_LOG_KA_XTOL = 1e-7

# Settings of the two-Ka refinement (trust-region reflective least squares on
# the projected residual in log Ka): it stops at steps of 1e-10 decades or at
# relative cost changes and gradients of 1e-14, so at the arithmetic of the
# residual and not before, with a characteristic step of 0.1 decades, well
# inside the 0.25-decade grid cell a start is in. These are the settings the
# 84-design validation of the grid density and the number of starts ran with.
_TRF_OPTIONS = dict(x_scale=0.1, xtol=1e-10, ftol=1e-14, gtol=1e-14)

# Relative singular-value cut-off for the rank of the norm-scaled coefficient
# design. Columns the mass balance ties together — free plus bound dye summing
# to a fixed total in IDA and in DBA host-to-dye, bound dye proportional to free
# dye wherever binding is too weak to deplete the host, every column constant
# where the titrant changes no species — carry a relative singular value of
# 2e-17 to 2e-15, while a direction the signal does separate stays above 7e-7
# anywhere in the default Ka bounds and above 2e-2 at the best fit. Nothing
# measured falls between the two (synthetic GDA, IDA and DBA titrations, host
# 1e-7 to 1e-4 M, Ka·h0 0.1 to 1e5, Ka swept over 1e-8 to 1e12 1/M), and 1e-8
# sits in the gap.
_RANK_RTOL = 1e-8

# Largest part of a design column that the other columns leave unexplained,
# relative to the largest species column, for its signal parameter to be named
# degenerate (see ``Projection.degenerate_keys``). It is the resolution the
# design is read at, the same as ``_RANK_RTOL``. Over 2400 random designs (every
# binding model, the 1:2 and 2:1 models also with the free-host coefficient
# fitted, Ka·c 1e-2 to 1e5, the two constants up to 1e3 apart, 8 to 30 points,
# host 1e-9 to 1e-2 M, titrations to 0.5 to 100 equivalents) 48 % of the fitted
# signal parameters leave 1e-12 or less — a mass balance reproduces their column
# to rounding — and 51 % leave 1e-8 or more. The 1.2 % in between are species
# the fit populates below 1e-4 of the host, whose short column the others nearly
# reproduce, and the offset at a binding constant so large that no free host is
# left; a coefficient of physical size on such a column changes the curve by
# under 1e-8 of it on one side of the line and by little more on the other, so
# the star, not the value, is what the line decides there.
_UNEXPLAINED_RTOL = 1e-8

# Resolution of R²: the smallest residual sum of squares, as a fraction of the
# total sum of squares, that an F test is cut from. An R² above 1 - 1e-10 is
# arithmetic, not data (a scatter below 1e-5 of the signal range, under any
# instrument); without the floor noise-free data give a zero-width interval
# whose edges are rounding. The replicate test floors each replicate's own
# residual the same way.
_R2_RESOLUTION = 1e-10

# Excess SSR above the interval's threshold that a Ka the model cannot solve
# enters the edge search with. Root finding needs a finite value on each side of
# an edge and only the sign of the excess decides which side of the interval a
# Ka is on, so any positive value places such a Ka outside.
_UNSOLVABLE_EXCESS = 1.0


def projectable(assay_type: AssayType) -> bool:
    """Whether the assay's signal is linear in every parameter but one or two Ka.

    True when the registry declares one or two ``BINDING_CONSTANT`` parameters
    and every other parameter is a ``SIGNAL_OFFSET`` or a
    ``SIGNAL_COEFFICIENT`` with a ``signal_species`` entry.
    """
    meta = ASSAY_REGISTRY[assay_type]
    kinds = {k: meta.param_kinds[k] for k in meta.parameter_keys}
    n_ka = sum(kind is ParamKind.BINDING_CONSTANT for kind in kinds.values())
    others_linear = all(
        kind is ParamKind.SIGNAL_OFFSET or (kind is ParamKind.SIGNAL_COEFFICIENT and k in meta.signal_species)
        for k, kind in kinds.items()
        if kind is not ParamKind.BINDING_CONSTANT
    )
    return n_ka in (1, 2) and others_linear


@dataclass(frozen=True)
class KaInterval:
    """Profile-likelihood confidence interval of one binding constant.

    Attributes
    ----------
    low, high : float
        Ka in 1/M: the envelope of the Ka values whose profiled residual sum
        of squares stays within the F-test threshold.
    open_low, open_high : bool
        ``True`` on a side where the interval reaches as far as the profile
        goes, so the data do not limit Ka there.
    level : float
        Confidence level of the interval.
    dof : int
        Degrees of freedom ``n - p`` of the F test.
    split : bool
        ``True`` when the accepted Ka values do not form one connected stretch
        of the scan grid, so the interval spans a gap of Ka values the data
        reject.
    unsolvable_low, unsolvable_high : bool
        ``True`` on an open side where the profile stops because the
        equilibrium model cannot be solved past the edge, rather than because
        the Ka bound is reached. The edge is then the last Ka the model could
        be evaluated at, which is inside the bound in force.
    limited_by_low, limited_by_high : str
        On an open side of a two-Ka interval, the other binding constant when
        the profile does cross the threshold there only because that constant
        has reached its own bound: the data would accept Ka further out if the
        other constant could follow. The edge is then where that crossing is.
        Empty otherwise.
    """

    low: float
    high: float
    open_low: bool
    open_high: bool
    level: float
    dof: int
    split: bool = False
    unsolvable_low: bool = False
    unsolvable_high: bool = False
    limited_by_low: str = ''
    limited_by_high: str = ''

    def to_dict(self) -> dict:
        """Every field, as written to a results file."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'KaInterval':
        """The interval a results file holds; a field the file leaves out takes its default."""
        return cls(**d)


@dataclass(frozen=True)
class ProjectedFit:
    """Least-squares fit of one or more signal rows sharing their binding constants.

    Attributes
    ----------
    ka : dict[str, float]
        Every binding constant of the model in 1/M, pinned ones at their value.
    coefficients : np.ndarray
        Signal parameters per row, shape ``(rows, n_coefficients)`` in
        ``Projection.coef_keys`` order: the bounded least-squares member at
        ``ka``. Where the design is rank deficient this is one member of a
        family that reconstructs the same signal.
    row_ssr : np.ndarray
        Residual sum of squares of every row at ``ka``, shape ``(rows,)``.
    objective : float
        ``sum_r w_r row_ssr[r]`` for the weights the fit was made with.
    rank : int
        Numerical rank of the free coefficient columns of the design at ``ka``.
    n_free_ka : int
        Number of binding constants the search was free to move.
    """

    ka: dict[str, float]
    coefficients: np.ndarray
    row_ssr: np.ndarray
    objective: float
    rank: int
    n_free_ka: int


@dataclass(frozen=True)
class ReplicateTest:
    """Outcome of the shared-Ka test over the rows of a projection.

    Attributes
    ----------
    excluded : tuple[int, ...]
        Row indices found to need another Ka than the others share, in the
        order they were removed.
    p_values : dict[int, float]
        The p-value of every row from the last round it was judged in.
    level : float
        Family-wise level; each row is judged against ``level / rows``.
    tested : bool
        ``False`` when the rows were not judged at all: fewer than three rows,
        or no residual degree of freedom.
    """

    excluded: tuple[int, ...]
    p_values: dict[int, float]
    level: float
    tested: bool


class Projection:
    """Projected least-squares problem of one assay on one or more signal rows.

    Holds the assay (titrant grid and conditions), the bounds of every
    parameter and the signal rows; solves the coefficients exactly at any set
    of binding constants, searches the Ka box for the shared optimum, profiles
    each Ka and cuts its interval. The per-row residuals on the search grid are
    cached, so any row weighting of a search costs one dot product per node.

    Parameters
    ----------
    assay : BaseAssay
        Assay of a type for which :func:`projectable` is true.
    bounds : dict[str, tuple[Quantity, Quantity]]
        Resolved bounds of every parameter. Equal bounds pin a parameter: a
        pinned coefficient contributes a fixed signal and a pinned Ka takes its
        axis out of the search.
    signals : np.ndarray, optional
        Signal rows, shape ``(rows, n_points)`` in au on the assay's titrant
        grid; the assay's own ``y_data`` as one row when omitted.
    should_cancel : Callable[[], bool], optional
        Asked before every equilibrium solve whether to stop; a ``True`` raises
        :class:`FitCancelled` there.

    Raises
    ------
    ValueError
        For an assay that is not projectable, Ka bounds that are not positive
        or are inverted, signal rows of another length than the titrant grid,
        or a signal row that is the same at every titration point.
    """

    def __init__(
        self,
        assay: BaseAssay,
        bounds: dict[str, tuple[Quantity, Quantity]],
        signals: np.ndarray | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ):
        if not projectable(assay.assay_type):
            raise ValueError(
                f'The {assay.assay_type.name} model does not have one or two binding constants with every '
                'other parameter a signal offset or coefficient, so it cannot be fitted by variable projection.'
            )
        meta = assay.registry_metadata
        keys = assay.parameter_keys
        self.assay = assay
        self.ka_keys = tuple(k for k in keys if meta.param_kinds[k] is ParamKind.BINDING_CONSTANT)
        self.coef_keys = tuple(k for k in keys if k not in self.ka_keys)
        fb = {
            k: (float(lo.to(meta.units[k]).magnitude), float(hi.to(meta.units[k]).magnitude))
            for k, (lo, hi) in bounds.items()
        }
        self.ka_bounds = {k: fb[k] for k in self.ka_keys}
        for key, (lo, hi) in self.ka_bounds.items():
            if not 0.0 < lo <= hi:
                raise FitRefused(
                    f'The bounds of {key} must be positive, with the lower one not above the upper one; '
                    f'they are {lo:g} to {hi:g} 1/M.'
                )
        self.free_ka = tuple(k for k, (lo, hi) in self.ka_bounds.items() if lo != hi)
        self._pinned_ka = {k: lo for k, (lo, hi) in self.ka_bounds.items() if lo == hi}
        self._lb = np.array([fb[k][0] for k in self.coef_keys])
        self._ub = np.array([fb[k][1] for k in self.coef_keys])
        self._species_of = tuple(meta.signal_species.get(k) for k in self.coef_keys)
        self._ka_index = {k: keys.index(k) for k in self.ka_keys}
        self._should_cancel = should_cancel

        rows = assay.y_data.magnitude[np.newaxis, :] if signals is None else np.asarray(signals, dtype=float)
        if rows.ndim != 2 or rows.shape[1] != assay.n_points:
            raise ValueError(
                f'Each signal row must hold one value per titration point ({assay.n_points}); '
                f'the rows given have shape {rows.shape}.'
            )
        self.signals = rows
        self.ss_tot = np.sum((rows - rows.mean(axis=1, keepdims=True)) ** 2, axis=1)
        # A signal that never changes says nothing about Ka: every binding
        # constant reproduces it equally well, its total sum of squares is zero
        # and every quantity measured as a fraction of it — R², the F test's
        # floor on the smallest residual — is then built on rounding. Refusing
        # here is what makes every entry point answer such data the same way.
        flat = np.flatnonzero(self.ss_tot == 0.0)
        if flat.size:
            which = '' if rows.shape[0] == 1 else f' of row(s) {", ".join(str(i + 1) for i in flat)}'
            raise FitRefused(
                f'The signal{which} is the same at every titration point, so nothing in it tells what Ka is. '
                'Check the data file and which replicates are switched on, then fit again.'
            )
        self.n_points = rows.shape[1]
        self._grid_cache: tuple[tuple[np.ndarray, ...], np.ndarray] | None = None

    # ------------------------------------------------------------------
    # Design and inner solve
    # ------------------------------------------------------------------

    def _full_ka(self, ka: Mapping[str, float]) -> dict[str, float]:
        """Every binding constant: the ones given, pinned ones at their value otherwise."""
        return {k: float(ka[k]) if k in ka else self._pinned_ka[k] for k in self.ka_keys}

    def _design(self, ka: Mapping[str, float], assay: BaseAssay | None = None) -> np.ndarray:
        """Signal columns at the binding constants *ka*, one per coefficient, from one species solve.

        The species are those of *assay*, a copy of the projection's assay with
        moved inputs, and of the projection's own assay when it is omitted.
        """
        if self._should_cancel is not None and self._should_cancel():
            raise FitCancelled('The fit was stopped.')
        params = np.zeros(len(self.assay.parameter_keys))
        for key, value in self._full_ka(ka).items():
            params[self._ka_index[key]] = value
        species = (self.assay if assay is None else assay).species(params)
        ones = np.ones(self.n_points)
        return np.column_stack(
            [ones if name is None else np.asarray(species[name], dtype=float) for name in self._species_of]
        )

    def _solve(self, design: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Each signal row's best SSR and coefficients on one design.

        A pinned coefficient (equal lower and upper bound) contributes a fixed
        signal and leaves the solve; the others are solved by bounded least
        squares on norm-scaled columns, which keeps coefficients spanning many
        orders of magnitude well conditioned. The solver can return a
        coefficient a rounding step beyond its bound, so each is clipped to its
        bounds after unscaling and the SSR is that of the clipped coefficients.

        A design the equilibrium model could not fill in is not a model signal
        at all, so it fits nothing: its SSR is infinite and its coefficients
        stay at their lower bounds.

        Returns
        -------
        tuple[np.ndarray, np.ndarray]
            ``(SSR per row, coefficients per row)``, shapes ``(rows,)`` and
            ``(rows, n_coefficients)``.
        """
        y = self.signals
        lb, ub = self._lb, self._ub
        coef = np.tile(lb, (y.shape[0], 1))
        if not np.isfinite(design).all():
            return np.full(y.shape[0], np.inf), coef
        pinned = lb == ub
        target = y - design[:, pinned] @ lb[pinned]
        free, scale = self._free_columns(design)
        if free.shape[1] == 0:
            return np.sum(target**2, axis=1), coef
        scaled = free / scale
        ssr = np.empty(y.shape[0])
        for i, row in enumerate(target):
            sol = lsq_linear(scaled, row, bounds=(lb[~pinned] * scale, ub[~pinned] * scale), method='bvls')
            coef[i, ~pinned] = np.clip(sol.x / scale, lb[~pinned], ub[~pinned])
            ssr[i] = np.sum((free @ coef[i, ~pinned] - row) ** 2)
        return ssr, coef

    def _free_columns(self, design: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Columns of the coefficients that are not pinned, and each column's norm (one for a zero column)."""
        free = design[:, self._lb != self._ub]
        return free, _norms(free)

    def row_ssr(self, ka: Mapping[str, float]) -> np.ndarray:
        """Best residual sum of squares of every row at the binding constants *ka*.

        Infinite where the equilibrium model has no solution at *ka*. A pinned
        Ka may be left out of *ka*.
        """
        return self._solve(self._design(ka))[0]

    def _solve_at(
        self, ka: Mapping[str, float], offsets: Mapping[str, float] | None
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Design, each row's SSR and each row's coefficients at *ka* with the entered inputs moved by *offsets*."""
        design = self._design(ka, self.assay.with_inputs(offsets) if offsets else None)
        return (design, *self._solve(design))

    def residual(self, ka: Mapping[str, float], row: int = 0, offsets: Mapping[str, float] | None = None) -> np.ndarray:
        """Projected residual ``y - A c`` of *row* at the binding constants *ka*.

        The design is that of ``assay.with_inputs(offsets)`` — the entered
        inputs when *offsets* is ``None`` or empty — and ``c`` the bounded
        least-squares coefficients of :meth:`row_ssr` on it. Every entry is
        infinite where the equilibrium model has no solution.
        """
        design, ssr, coef = self._solve_at(ka, offsets)
        if not np.isfinite(ssr[row]):
            return np.full(self.n_points, np.inf)
        return self.signals[row] - design @ coef[row]

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _weights(self, weights: np.ndarray | None) -> np.ndarray:
        rows = self.signals.shape[0]
        w = np.ones(rows) if weights is None else np.asarray(weights, dtype=float)
        if w.shape != (rows,) or (w < 0).any() or not (w > 0).any():
            raise ValueError(
                f'The row weights must be one non-negative number per signal row ({rows}), at least one of them '
                f'positive; got {w!r}.'
            )
        return w

    def _grid(self) -> tuple[tuple[np.ndarray, ...], np.ndarray]:
        """Search-grid axes (Ka values per free Ka) and every row's SSR on the grid, shape ``(*axes, rows)``."""
        if self._grid_cache is None:
            axes = tuple(_ka_grid(*self.ka_bounds[k], _SEARCH_PER_DECADE) for k in self.free_ka)
            ssr = np.empty(tuple(axis.size for axis in axes) + (self.signals.shape[0],))
            for index in np.ndindex(ssr.shape[:-1]):
                ssr[index] = self.row_ssr({k: axes[j][index[j]] for j, k in enumerate(self.free_ka)})
            self._grid_cache = (axes, ssr)
        return self._grid_cache

    def _objective(self, w: np.ndarray) -> Callable[[Mapping[str, float]], float]:
        """``sum_r w_r S_r(K)`` over the rows with positive weight, as a function of the free Ka."""
        used = w > 0
        w_used = w[used]

        def q(ka: Mapping[str, float]) -> float:
            return float(self.row_ssr(ka)[used] @ w_used)

        return q

    def _weighted_grid(self, w: np.ndarray) -> np.ndarray:
        used = w > 0
        return self._grid()[1][..., used] @ w[used]

    def fit(self, weights: np.ndarray | None = None) -> ProjectedFit:
        """Least-squares fit of every row with one shared set of binding constants.

        One free Ka: the search grid, then bounded Brent refinement between the
        neighbours of the best node. Two free Ka: the search grid, then
        trust-region least squares on the projected residual from the
        ``_N_REFINE`` best grid local minima over the whole box, keeping a node
        that its refinement does not beat; the best of the refinements wins. A
        pinned Ka takes its axis out of the search.

        Parameters
        ----------
        weights : np.ndarray, optional
            Weight per row, non-negative, at least one positive; ones when
            omitted. A row of weight zero does not steer the shared Ka but is
            still solved at the optimum.

        Raises
        ------
        ValueError
            When the equilibrium model has no solution at any Ka in the box.
        FitCancelled
            When *should_cancel* asked the fit to stop.
        """
        w = self._weights(weights)
        objective = self._objective(w)
        if not self.free_ka:
            ka, q = dict(self._pinned_ka), objective({})
        elif len(self.free_ka) == 1:
            (key,), (axis,) = self.free_ka, self._grid()[0]
            best_ka, q = _refine_best(lambda k: objective({key: k}), axis, self._weighted_grid(w))
            ka = self._full_ka({key: best_ka})
        else:
            ka, q = self._search_two(w)
        if not np.isfinite(q):
            ranges = ' or '.join(f'between {lo:g} and {hi:g} M⁻¹' for lo, hi in self.ka_bounds.values())
            which = 'its upper bound' if len(self.ka_bounds) == 1 else 'their upper bounds'
            raise FitRefused(
                f'The binding model has no solution at any association constant {ranges}, so there is no fit. '
                f'Lower {which} under Parameter Bounds and fit again.'
            )
        design = self._design(ka)
        row_ssr, coef = self._solve(design)
        free, scale = self._free_columns(design)
        return ProjectedFit(
            ka=ka,
            coefficients=coef,
            row_ssr=row_ssr,
            objective=q,
            rank=_rank(free / scale),
            n_free_ka=len(self.free_ka),
        )

    @staticmethod
    def _grid_minima(q_grid: np.ndarray) -> list[tuple[int, int]]:
        """Indices of the ``_N_REFINE`` lowest local minima of a two-Ka objective grid, lowest first."""
        padded = np.pad(q_grid, 1, constant_values=np.inf)
        n1, n2 = q_grid.shape
        neighbours = np.min(
            [
                padded[1 + a : n1 + 1 + a, 1 + b : n2 + 1 + b]
                for a in (-1, 0, 1)
                for b in (-1, 0, 1)
                if (a, b) != (0, 0)
            ],
            axis=0,
        )
        ii, jj = np.nonzero((q_grid <= neighbours) & np.isfinite(q_grid))
        order = np.argsort(q_grid[ii, jj], kind='stable')[:_N_REFINE]
        return [(int(ii[k]), int(jj[k])) for k in order]

    def two_ka_starts(self) -> list[dict[str, float]]:
        """The grid local minima a two-Ka search refines, lowest first, as binding constants."""
        axes, _ = self._grid()
        return [
            {self.free_ka[0]: float(axes[0][i]), self.free_ka[1]: float(axes[1][j])}
            for i, j in self._grid_minima(self._weighted_grid(self._weights(None)))
        ]

    def _search_two(self, w: np.ndarray) -> tuple[dict[str, float], float]:
        """Two-Ka search: the best of ``_N_REFINE`` refined grid local minima."""
        axes, _ = self._grid()
        q_grid = self._weighted_grid(w)
        starts = self._grid_minima(q_grid)
        if not starts:
            return self._full_ka({k: axes[j][0] for j, k in enumerate(self.free_ka)}), np.inf

        used = w > 0
        sqrt_w = np.sqrt(w[used])
        y_used = self.signals[used]
        lo = np.array([np.log10(self.ka_bounds[k][0]) for k in self.free_ka])
        hi = np.array([np.log10(self.ka_bounds[k][1]) for k in self.free_ka])

        def residual(t: np.ndarray) -> np.ndarray:
            design = self._design({k: 10.0 ** t[j] for j, k in enumerate(self.free_ka)})
            _, coef = self._solve(design)
            return (((design @ coef[used].T).T - y_used) * sqrt_w[:, None]).ravel()

        best: tuple[float, dict[str, float]] | None = None
        for i, j in starts:
            node = (float(q_grid[i, j]), {self.free_ka[0]: float(axes[0][i]), self.free_ka[1]: float(axes[1][j])})
            start = np.array([np.log10(axes[0][i]), np.log10(axes[1][j])])
            res = least_squares(residual, start, bounds=(lo, hi), **_TRF_OPTIONS)
            s = float(res.fun @ res.fun)
            candidate = (s, {key: 10.0 ** res.x[m] for m, key in enumerate(self.free_ka)}) if s < node[0] else node
            if best is None or candidate[0] < best[0]:
                best = candidate
        return self._full_ka(best[1]), best[0]

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def params(self, fit: ProjectedFit, row: int = 0) -> np.ndarray:
        """Parameter vector of *row* in ``parameter_keys`` order, ready for ``assay.forward_model``."""
        values = {**fit.ka, **dict(zip(self.coef_keys, fit.coefficients[row]))}
        return np.array([values[k] for k in self.assay.parameter_keys])

    def n_params(self, fit: ProjectedFit) -> int:
        """Parameter count ``p`` of the F test: the free binding constants plus the design rank."""
        return fit.n_free_ka + fit.rank

    def fitted_columns(self, ka: Mapping[str, float], offsets: Mapping[str, float] | None = None) -> np.ndarray:
        """Design columns of the signal parameters the bounded solve of the first row fits at *ka*.

        The columns, with the inputs moved by *offsets*, of the free
        coefficients that lie inside their bounds; a coefficient held on a
        bound is not fitted. None where the model has no solution.

        A coefficient is on a bound when moving it there changes the curve by
        less than ``_RANK_RTOL`` of the signal's variation about its mean, the
        scale ``_R2_RESOLUTION`` reads a residual on, so a constant background
        under the signal leaves the count as it is. The change is the
        coefficient's distance from the bound times the norm of its column,
        which is the coefficient in the norm-scaled variables the solve works
        in. The solver puts a bounded
        coefficient exactly on its bound in those variables, and unscaling,
        like the solve of the free ones, is good to rounding times the
        condition of a design whose rank is read at the same ``_RANK_RTOL``;
        a fitted coefficient, which scatters by at least the noise of one
        point in those variables, lands that close to a bound by chance in
        under 1e-5 of fits at a noise of 0.1 % of the signal.
        """
        return self._fitted(*self._solve_at(ka, offsets))

    def _fitted(self, design: np.ndarray, ssr: np.ndarray, coef: np.ndarray) -> np.ndarray:
        """:meth:`fitted_columns` of a solve :meth:`_solve_at` has made."""
        free, scale = self._free_columns(design)
        if not np.isfinite(ssr[0]):
            return free[:, :0]
        fitted = self._lb != self._ub
        margin = np.minimum(coef[0] - self._lb, self._ub - coef[0])[fitted] * scale
        return free[:, margin > _RANK_RTOL * np.sqrt(self.ss_tot[0])]

    def solved(self, ka: Mapping[str, float], offsets: Mapping[str, float] | None = None) -> tuple[np.ndarray, int]:
        """Each row's SSR at *ka* and the fitted rank of the first row, both from one bounded solve.

        The fitted rank is the rank of :meth:`fitted_columns`, the count
        :meth:`cut_off` takes. A rank and not a count of columns, because a
        mass balance ties columns together and the solve then returns one
        member of a family in which any of the tied coefficients may be the
        one inside its bounds.
        """
        design, ssr, coef = self._solve_at(ka, offsets)
        columns = self._fitted(design, ssr, coef)
        return ssr, _rank(columns / _norms(columns))

    def fitted_rank(self, ka: Mapping[str, float], offsets: Mapping[str, float] | None = None) -> int:
        """Signal parameters the bounded solve of the first row fits at *ka* (see :meth:`solved`)."""
        return self.solved(ka, offsets)[1]

    def degenerate_keys(self, fit: ProjectedFit) -> tuple[str, ...]:
        """Signal parameters the data do not determine on their own at the fitted binding constants.

        With every binding constant held fixed, a signal made of offsets and
        coefficients is linear in them, one design column each. What the data
        can say about one of them is carried by the part of its column that
        the other columns do not reproduce — the residual of the column after
        its least-squares fit on the others. A parameter is degenerate when
        that part is below ``_UNEXPLAINED_RTOL`` of the largest species column
        (for the offset, of its own column): a signal coefficient of the size
        that produces the whole signal on the most populated species then
        changes the curve by less than that fraction of it, and the fit can
        trade the parameter against the others at no cost.

        Two things put a column there. A mass balance writes it exactly as a
        combination of the others — ``D + HD = d0`` makes the free-dye column
        ``d0`` times the offset column minus the complex column — however
        sparsely its species is populated, because the residual is measured
        in concentration and not relative to the column's own length. And a
        species the fit leaves unpopulated has no column to speak of, so its
        coefficient is not determined at any physical size. The parameters a
        relation ties are all named, whatever their columns' lengths: the
        judgement is per column against the others, so no basis choice and no
        short column can hide a member. Pinned parameters (equal lower and
        upper bound) are not fitted and stay out.

        Returns
        -------
        tuple[str, ...]
            The degenerate keys in parameter order; empty when every fitted
            signal parameter is determined on its own.
        """
        fitted = self._lb != self._ub
        free, scale = self._free_columns(self._design(fit.ka))
        is_offset = np.array([name is None for name in self._species_of])[fitted]
        scaled = free / scale
        free_keys = [key for key, is_fitted in zip(self.coef_keys, fitted) if is_fitted]
        degenerate = []
        for j, key in enumerate(free_keys):
            others = np.delete(scaled, j, axis=1)
            unexplained = free[:, j]
            if others.shape[1]:
                # Solved to machine precision: a column a mass balance writes as
                # the difference of two long columns lies in a direction of the
                # others that is as short as itself, and cutting that direction
                # off would leave the column unexplained.
                unexplained = unexplained - others @ np.linalg.lstsq(others, unexplained, rcond=None)[0]
            reference = scale[j] if is_offset[j] else scale[~is_offset].max()
            if np.linalg.norm(unexplained) < _UNEXPLAINED_RTOL * reference:
                degenerate.append(key)
        return tuple(degenerate)

    # ------------------------------------------------------------------
    # Profile and interval
    # ------------------------------------------------------------------

    def _require_one_row(self, what: str) -> None:
        if self.signals.shape[0] != 1:
            raise ValueError(f'{what} describes one signal; this projection holds {self.signals.shape[0]} rows.')

    def threshold(self, fit: ProjectedFit, level: float = LEVEL, n_constrained: int = 1, released: int = 0) -> float:
        """Objective cut-off of the F test on a single-row projection.

        ``S_min (1 + m F(level; m, n - p) / (n - p))`` with ``m`` the number of
        constrained binding constants (one for an interval, two for the joint
        region) plus *released*, the signal parameters the best fit fits and
        the fit at the tested Ka holds on a bound; ``p`` the free binding
        constants plus the design rank, and ``S_min`` floored at
        ``_R2_RESOLUTION`` of the total sum of squares.

        Raises
        ------
        ValueError
            When ``n - p < 1``, so the data leave nothing to judge the fit by.
        """
        self._require_one_row('A confidence threshold')
        dof = _require_dof(self.n_points, self.n_params(fit))
        m = n_constrained + released
        return self._floored(fit) * (1.0 + m * f_dist.ppf(level, m, dof) / dof)

    def cut_off(self, fit: ProjectedFit, level: float = LEVEL, n_constrained: int = 1) -> Callable[[int], float]:
        """:meth:`threshold` by fitted rank: the cut-off a fit of that :meth:`fitted_rank` is judged against.

        *released* is how far the rank falls short of the best fit's, so along
        the binding constants the cut-off is a step function that takes one
        value per count. The rank comes from the solve that gave the judged
        residual (:meth:`solved`, :meth:`profile_point`).
        """
        fitted = self.fitted_rank(fit.ka)
        cuts: dict[int, float] = {}

        def at(rank: int) -> float:
            released = max(0, fitted - rank)
            if released not in cuts:
                cuts[released] = self.threshold(fit, level, n_constrained, released)
            return cuts[released]

        return at

    def _floored(self, fit: ProjectedFit) -> float:
        """The best residual of a single-row fit, no smaller than ``_R2_RESOLUTION`` of the total sum of squares."""
        return max(fit.objective, _R2_RESOLUTION * float(self.ss_tot[0]))

    def profile(
        self, ka_key: str, weights: np.ndarray | None = None, inner_per_decade: int = _SEARCH_PER_DECADE
    ) -> Callable[[float], float]:
        """The objective at a value of *ka_key*, minimised over the other free Ka.

        With no other free Ka this is the objective itself. Otherwise the other
        axis is scanned at *inner_per_decade* and refined from the best few
        local minima of that scan, because a valley too narrow for the grid
        step shows there only as a raised local minimum; at the search-grid
        density a search-grid node of *ka_key* reads the scan from the cached
        grid, so only the refinements are solved.
        """
        w = self._weights(weights)
        return lambda ka: self._inner_minimum(ka_key, ka, w, inner_per_decade)[1]

    def profile_point(
        self, ka_key: str, ka: float, inner_per_decade: int = _SEARCH_PER_DECADE
    ) -> tuple[dict[str, float], float, int]:
        """The profile at ``ka_key = ka``: its free binding constants, the objective of all rows, the fitted rank.

        The other free Ka is where :meth:`profile` finds its minimum. It is the
        point whose fit the F test judges, so its fitted rank is the one
        :meth:`cut_off` takes. With *ka_key* the only free Ka the objective
        and the rank are one solve (:meth:`solved`).
        """
        point = {ka_key: ka}
        others = [k for k in self.free_ka if k != ka_key]
        if not others:
            ssr, rank = self.solved(point)
            return point, float(ssr @ self._weights(None)), rank
        point[others[0]], value = self._inner_minimum(ka_key, ka, self._weights(None), inner_per_decade)
        return point, value, self.fitted_rank(point)

    def inner_start(self, ka_key: str, ka: float) -> dict[str, float]:
        """Where the other free Ka minimises the objective at ``ka_key = ka``; empty without another free Ka.

        The minimiser :meth:`profile` finds at the search-grid density: on a
        search-grid node of *ka_key* the cached grid row refined from its best
        local minima, a fresh scan of the other Ka refined the same way
        anywhere else. It is where a search over the other Ka that also moves
        the entered inputs starts from.
        """
        point = self.profile_point(ka_key, ka)[0]
        return {k: v for k, v in point.items() if k != ka_key}

    def _inner_minimum(self, ka_key: str, ka: float, w: np.ndarray, per_decade: int) -> tuple[float | None, float]:
        """The other free Ka that minimises the objective at ``ka_key = ka`` (``None`` without one), and that minimum."""
        objective = self._objective(w)
        others = [k for k in self.free_ka if k != ka_key]
        if not others:
            return None, objective({ka_key: ka})
        other = others[0]
        axes, _ = self._grid()
        own_axis = axes[self.free_ka.index(ka_key)] if ka_key in self.free_ka else np.array([])
        nodes = np.flatnonzero(own_axis == ka)
        if per_decade == _SEARCH_PER_DECADE and nodes.size:
            other_axis = axes[self.free_ka.index(other)]
            scan = np.take(self._weighted_grid(w), nodes[0], axis=self.free_ka.index(ka_key))
        else:
            other_axis = _ka_grid(*self.ka_bounds[other], per_decade)
            scan = np.array([objective({ka_key: ka, other: k}) for k in other_axis])
        return _refine_minima(lambda k: objective({ka_key: ka, other: k}), other_axis, scan)

    def _two_ka_scan(
        self,
        ka_key: str,
        node_excess: Callable[[float], float],
        excess_at: Callable[[float], float],
        fit: ProjectedFit,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Ka values a two-Ka interval is cut from, and the profiled excess at each.

        A profile point of a two-Ka model costs a minimisation over the other
        Ka, so the whole Ka box cannot be scanned at the profile density. The
        search-grid nodes are scanned first with *node_excess*, whose inner
        scan is a row of the cached grid so that only the refinements are
        solved; they say roughly which Ka the test accepts. Every cell read
        again is read with *excess_at*, its nodes included, which scans the
        other Ka at ``_INNER_PER_DECADE``. What the interval then depends on is where
        that verdict turns over, so exactly those cells are scanned again at
        ``_PROFILE_PER_DECADE``, the density a one-Ka interval uses everywhere:
        every cell whose two nodes disagree, and then cell by cell outward past
        the accepted ones until a whole cell holds nothing the test accepts, or
        a Ka bound is reached. An edge is therefore closed only where a full
        search cell, read five times finer, rejects every Ka in it, while a
        stretch the nodes accept throughout — an interval the data leave open
        spans the whole box — costs nothing further.

        The stepwise models need that resolution at the turning points: their
        profile is a minimum that moves from one K₁·K₂ valley to another, so the
        accepted Ka can break into stretches narrower than a search cell. Read
        from the nodes alone the envelope stops short of Ka the test accepts and
        the gap inside it goes unreported.
        """
        nodes = self._grid()[0][self.free_ka.index(ka_key)]
        excess = {float(ka): node_excess(ka) for ka in nodes.tolist()}
        dense: set[float] = set()
        logs = np.log10(nodes)
        lo, hi = float(logs[0]), float(logs[-1])
        cell = (hi - lo) / max(nodes.size - 1, 1)

        def scan(a: float, b: float) -> bool:
            """Profile from ``10**a`` to ``10**b`` at the profile density; whether any Ka there is accepted."""
            accepts = False
            for ka in _ka_grid(10.0**a, 10.0**b, _PROFILE_PER_DECADE).tolist():
                if ka not in dense:
                    dense.add(ka)
                    excess[ka] = excess_at(ka)
                accepts = accepts or excess[ka] <= 0
            return accepts

        accepted = np.array([excess[ka] <= 0 for ka in nodes.tolist()])
        turns = np.flatnonzero(accepted[:-1] != accepted[1:])
        for i in turns:
            scan(float(logs[i]), float(logs[i + 1]))
        if not turns.size and not accepted.any():
            # The fit's own Ka is the only one the test is known to accept, and
            # it lies between two nodes: that cell is where the interval is.
            i = int(np.clip(np.searchsorted(logs, np.log10(fit.ka[ka_key])) - 1, 0, max(nodes.size - 2, 0)))
            scan(float(logs[i]), float(logs[min(i + 1, nodes.size - 1)]))
        reached = [ka for ka, e in excess.items() if e <= 0] + [fit.ka[ka_key]]
        left = max(float(np.log10(min(reached))), lo)
        right = min(float(np.log10(max(reached))), hi)
        while left > lo and scan(max(left - cell, lo), left):
            left = max(left - cell, lo)
        while right < hi and scan(right, min(right + cell, hi)):
            right = min(right + cell, hi)
        grid = np.array(sorted(excess))
        return grid, np.array([excess[ka] for ka in grid.tolist()])

    def interval(self, ka_key: str, fit: ProjectedFit, level: float = LEVEL) -> KaInterval | None:
        """Profile-likelihood interval of *ka_key* on a single-row projection; ``None`` when it is pinned.

        Wherever the interval is, the profile is scanned at
        ``_PROFILE_PER_DECADE`` — across the Ka bounds when *ka_key* is the only
        free Ka, and around the accepted search-grid nodes when the profile is a
        minimisation over another Ka (see :meth:`_two_ka_scan`). The envelope of
        the accepted points is then closed by root finding to ``_LOG_KA_XTOL``
        decades. A Ka is accepted where its profile is at or below
        :meth:`cut_off` at its :meth:`profile_point`; where the cut-off steps
        at an edge, root finding closes the edge on the step. A closed edge of
        a two-Ka interval that only the bound of the other Ka produces is
        reported open and names that Ka (see :meth:`_bound_behind`).
        """
        self._require_one_row('A confidence interval')
        if ka_key not in self.free_ka:
            return None
        cut = self.cut_off(fit, level)

        def excess(inner_per_decade: int) -> Callable[[float], float]:
            def at(ka: float) -> float:
                _, value, rank = self.profile_point(ka_key, ka, inner_per_decade)
                return value - cut(rank)

            return at

        two_ka = len(self.free_ka) == 2
        excess_at = excess(_INNER_PER_DECADE if two_ka else _SEARCH_PER_DECADE)
        if two_ka:
            grid, excess_grid = self._two_ka_scan(ka_key, excess(_SEARCH_PER_DECADE), excess_at, fit)
        else:
            grid = _ka_grid(*self.ka_bounds[ka_key], _PROFILE_PER_DECADE)
            excess_grid = np.array([excess_at(ka) for ka in grid])
        (low, high), (open_low, open_high), split, (unsolvable_low, unsolvable_high) = _interval(
            excess_at, grid, excess_grid, fit.ka[ka_key]
        )
        floor = self._floored(fit)
        limited_by_low = '' if open_low or not two_ka else self._bound_behind(ka_key, low, cut, floor)
        limited_by_high = '' if open_high or not two_ka else self._bound_behind(ka_key, high, cut, floor)
        return KaInterval(
            low=low,
            high=high,
            open_low=open_low or bool(limited_by_low),
            open_high=open_high or bool(limited_by_high),
            level=level,
            dof=self.n_points - self.n_params(fit),
            split=split,
            unsolvable_low=unsolvable_low,
            unsolvable_high=unsolvable_high,
            limited_by_low=limited_by_low,
            limited_by_high=limited_by_high,
        )

    def _bound_behind(self, ka_key: str, edge: float, cut: Callable[[int], float], floor: float) -> str:
        """The other free Ka when its bound, and not the data, is what closes the profile of *ka_key* at *edge*.

        Along the profile of one constant of a stepwise model the other one
        compensates, until it reaches its bound; from there the residual rises
        and crosses the threshold although the data would accept the pair
        further out. Such a crossing moves with the bound. It shows at the
        edge itself: the minimum over the other Ka lies on its bound, and the
        residual still falls towards that bound — by more than ``_BOUND_RISE``
        of the allowed rise over the last search-grid step, the allowed rise
        being the edge's own *cut* above *floor*, the best residual. Where the
        data do set the edge, the other Ka is either inside its bounds or on a
        bound the residual no longer changes towards.
        """
        (other,) = (k for k in self.free_ka if k != ka_key)
        objective = self._objective(self._weights(None))
        point, at_edge, rank = self.profile_point(ka_key, edge, _INNER_PER_DECADE)
        other_ka = point[other]
        lo, hi = self.ka_bounds[other]
        if other_ka not in (lo, hi):
            return ''
        step = 10.0 ** (1.0 / _SEARCH_PER_DECADE)
        inside = min(other_ka * step, hi) if other_ka == lo else max(other_ka / step, lo)
        return other if objective({ka_key: edge, other: inside}) - at_edge > _BOUND_RISE * (cut(rank) - floor) else ''


def replicate_outliers(
    projection: Projection,
    own_fits: Sequence[ProjectedFit] | None = None,
    level: float = REPLICATE_TEST_LEVEL,
) -> ReplicateTest:
    """Rows of *projection* whose own best fit needs another Ka than the others share.

    Each row r is fitted on its own, giving its own residual ``S_r`` and, with
    ``q`` the design rank at the shared optimum, ``k`` the free Ka and
    ``nu = n - q - k``, its own variance ``s_r² = S_r / nu``. Rows are weighted
    ``w_r = 1 / s_r²``, so each row's misfit is measured in units of its own
    scatter and a noisier row is not penalised for being noisy. For a set A,
    ``Qmin(A) = min_K sum_{r in A} w_r S_r(K)``; the leave-one-out statistic
    ``T_r = Qmin(A) - Qmin(A \\ r) - nu`` is compared with ``F(k, nu)`` through
    ``p_r = sf(T_r / k)``. While at least three rows remain, every row is
    judged and the row with the smallest ``p_r`` is removed if
    ``p_r < level / R`` (Bonferroni over the R rows given) and fewer than half
    of the rows given would then be removed, else the test stops; the p-value
    reported for a row is the one of the round it was last judged in.
    Removal is sequential because a single pass lets one real
    outlier drag the shared Ka of the others (measured: eight replicates with
    one at three times the Ka give 12 % wrong exclusions in a single pass and
    none sequentially; with four replicates the power rises from 10 % to
    100 %). Fewer than three rows, or ``nu < 1``, cannot be judged.

    Each own residual is floored at ``_R2_RESOLUTION`` of the row's total sum
    of squares, so a row the model reproduces to rounding gets a finite weight.

    Parameters
    ----------
    projection : Projection
        The projection over every row given.
    own_fits : Sequence[ProjectedFit], optional
        Row *r*'s own fit — ``projection.fit`` weighting row *r* alone — for
        every row, when the caller has already made them. The searches are
        otherwise repeated here, which is the slowest part of a two-Ka
        per-replicate fit.
    level : float
        Family-wise level of the test.

    Returns
    -------
    ReplicateTest
    """
    rows = projection.signals.shape[0]
    if rows < 3:
        return ReplicateTest(excluded=(), p_values={}, level=level, tested=False)
    if own_fits is None:
        own_fits = [projection.fit(np.eye(rows)[r]) for r in range(rows)]
    own_ssr = np.array([own_fits[r].row_ssr[r] for r in range(rows)])
    own_ssr = np.maximum(own_ssr, _R2_RESOLUTION * projection.ss_tot)
    # Weights up to the common factor nu, which does not move any shared optimum.
    w = 1.0 / own_ssr
    shared = projection.fit(w)
    k = shared.n_free_ka
    nu = projection.n_points - shared.rank - k
    if nu < 1 or k < 1:
        return ReplicateTest(excluded=(), p_values={}, level=level, tested=False)

    def q_min(keep: list[int]) -> float:
        mask = np.zeros(rows)
        mask[keep] = w[keep]
        return nu * projection.fit(mask).objective

    keep = list(range(rows))
    excluded: list[int] = []
    p_values: dict[int, float] = {}
    while len(keep) >= 3:
        q_all = q_min(keep)
        p_round = {}
        for r in keep:
            t = max(q_all - q_min([s for s in keep if s != r]) - nu, 0.0)
            p_round[r] = float(f_dist.sf(t / k, k, nu))
        p_values.update(p_round)
        worst = min(p_round, key=p_round.get)
        if p_round[worst] >= level / rows or len(excluded) + 1 >= rows / 2:
            break
        excluded.append(worst)
        keep.remove(worst)
    return ReplicateTest(excluded=tuple(excluded), p_values=p_values, level=level, tested=True)


# ----------------------------------------------------------------------
# Helpers other modules may import
# ----------------------------------------------------------------------


def _require_dof(n_points: int, n_params: int) -> int:
    """Degrees of freedom ``n - p`` of the F test; refused in plain language when there is none."""
    dof = n_points - n_params
    if dof < 1:
        raise FitRefused(
            f'The data have {n_points} titration points, too few to judge the {n_params} parameters this '
            'model fits, so no fit can be reported. Add titration points, or hold a parameter at one value '
            'by giving it the same lower and upper bound under Parameter Bounds, and fit again.'
        )
    return dof


def _ka_grid(lo: float, hi: float, per_decade: int) -> np.ndarray:
    """Log-spaced Ka grid with at least *per_decade* points per decade; one point when Ka is pinned."""
    if lo == hi:
        return np.array([lo])
    # Decades as a difference of logarithms: a bound far above the other overflows their ratio.
    return np.geomspace(lo, hi, int(np.ceil((np.log10(hi) - np.log10(lo)) * per_decade)) + 1)


def _norms(columns: np.ndarray) -> np.ndarray:
    """Norm of every column, one for a zero column."""
    scale = np.linalg.norm(columns, axis=0)
    scale[scale == 0] = 1.0
    return scale


def _rank(columns: np.ndarray) -> int:
    """Numerical rank of norm-scaled *columns* at the ``_RANK_RTOL`` cut-off."""
    if columns.shape[1] == 0:
        return 0
    singular = np.linalg.svd(columns, compute_uv=False)
    return int(np.sum(singular > _RANK_RTOL * singular.max()))


def _refine_best(ssr_fn: Callable[[float], float], grid: np.ndarray, ssr_grid: np.ndarray) -> tuple[float, float]:
    """Minimum of *ssr_fn*, refined in log Ka between the best grid point's neighbours."""
    return _refine_at(ssr_fn, grid, ssr_grid, int(np.argmin(ssr_grid)))


def _refine_minima(ssr_fn: Callable[[float], float], grid: np.ndarray, ssr_grid: np.ndarray) -> tuple[float, float]:
    """Minimum of *ssr_fn*, refined from the ``_N_REFINE`` best local minima of *ssr_grid*: ``(Ka, value)``.

    A valley narrower than the grid step shows on the grid as a local minimum
    whose own value is high — the stepwise models' K₁·K₂ valley is that narrow
    where one of the two constants is held fixed — so refining the lowest grid
    point alone can return a minimum that belongs to another valley and lies
    well above the true one.
    """
    pad = np.pad(ssr_grid, 1, constant_values=np.inf)
    minima = np.flatnonzero((ssr_grid <= np.minimum(pad[:-2], pad[2:])) & np.isfinite(ssr_grid))
    lowest = int(np.argmin(ssr_grid))
    best = (float(grid[lowest]), float(ssr_grid[lowest]))
    for i in minima[np.argsort(ssr_grid[minima], kind='stable')][:_N_REFINE]:
        best = min(best, _refine_at(ssr_fn, grid, ssr_grid, int(i)), key=lambda found: found[1])
    return best


def _refine_at(ssr_fn: Callable[[float], float], grid: np.ndarray, ssr_grid: np.ndarray, i: int) -> tuple[float, float]:
    """Minimum of *ssr_fn* between the neighbours of grid point *i*, never worse than that point.

    A neighbour the model cannot solve (infinite SSR) is no bracket, so the
    refinement stops at the grid point on that side.
    """
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

    *excess_fn* is the profiled objective minus the cut-off of its own profile
    point, which *best_ka* always clears. An edge with no grid point beyond it is open at the Ka
    bound. So is an edge whose next grid point is a Ka the model cannot be
    solved at: the data reject nothing there, the profile simply stops, and
    the edge is the last Ka it could be evaluated at. A grid point inside the
    envelope that the excess rejects means the accepted Ka values are not one
    connected stretch; the envelope then spans a gap.

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
