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

The titration points carry weights ``omega_i``, the inverse relative variance of
the signal at each point and one at every point unless the caller hands some in.
Written out, the objective is

    Q(K) = sum_r w_r sum_i omega_i (y_ri - (A(K) c_r)_i)²

and the engine reaches it by whitening: the inner solve multiplies the signal
rows and the design by ``sqrt(omega)``, so every residual sum of squares, the
total sum of squares they are measured against and every residual vector the
engine hands out are those of the whitened problem, whose noise has one variance
at every point. The F tests below are functions of those sums alone. Ranks are
read on the design as the model gives it; a positive scaling of its rows leaves
them as they are.

The profile ``P_j(k) = min over the other binding constants of Q`` bounds every
fit at that value of one Ka, so an F test on it gives a profile-likelihood
confidence interval per Ka, and the same test on the rows of a replicate set
decides whether every replicate shares K.

A parameter held on a bound is not fitted: it takes no dimension from the
residual. What a fit at K fitted (:meth:`Projection.fitted_parameters`) is the
free binding constants strictly inside their box and the rank ``r(K)`` of the
design columns whose coefficient lies strictly inside its bounds; their count
at the best fit ``K_hat`` is the ``p`` of every test here. The F test of a
tested Ka compares two fits, and its numerator counts the parameters the best
fit has and the fit at the tested Ka has not: the tested Ka, and every signal
parameter the bounded solve holds on a bound there while the best fit leaves it
free,

    m(K)   = constrained Ka + max(0, r(K_hat) - r(K))
    cut(K) = S_min (1 + kappa m(K) F(level; m(K), n - p) / (n - p))

and the interval is ``{k : P_j(k) <= cut}`` at the profile point of k, the other
binding constant where it minimises Q. ``n - p`` is that of the best fit
throughout. Wherever the tested Ka pins nothing the best fit leaves free,
``m`` is the number of constrained Ka and the cut-off is the constant one of the
plain F test; where it does, the cut-off steps up, which is conservative against
the exact mixture of F distributions a bounded parameter follows.

``kappa >= 1`` is the design effect of the tested Ka, one unless the caller
hands in another (:mod:`core.pipeline.inflation`): how much more the estimate
of that Ka varies than the residual scatter alone implies, where the point
weights were read off the replicates or a random error of each titrant
addition is stated. Under a misspecified variance the likelihood-ratio
statistic of one parameter is ``kappa`` times a chi-squared variable to first
order (Kent 1982, Biometrika 69:19), so the F quantile is scaled by it; at
``kappa = 1`` the cut-off is the plain F test's.

The equilibrium models report a K they have no speciation for as species that
are not a number, rather than by raising. Such a K has no fit at all, so its
residual sum of squares is infinite, it never enters an interval and no curve
crosses it. Inside the default Ka box every registered model has a solution at
every K; the sentinel is reached only far outside it, where a free
concentration falls below the smallest normal double or an intermediate product
passes the range of a double.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Callable, Mapping, Sequence

import numpy as np
from scipy.optimize import brentq, least_squares, lsq_linear, minimize_scalar
from scipy.stats import f as f_dist

from core.assays.base import BaseAssay
from core.assays.registry import ASSAY_REGISTRY, AssayType, ParamKind
from core.units import Q_, Quantity


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

#: The fewest replicates the replicate test judges: with two, nothing says which
#: of them is the odd one.
REPLICATE_TEST_MIN = 3

#: Level at which the data must reject the model without the second binding step
#: before an interval of the second constant of a stepwise model claims a lower
#: limit (see :meth:`Projection.interval`). It is the level proposed for claims
#: of a new effect (Benjamin et al. 2018, Nat. Hum. Behav. 2:6), and the loosest
#: of the levels tried whose closed intervals of the second constant cover at
#: Bradley's band on held-out weak-regime titrations: 0.927 [0.890, 0.954].
SECOND_STEP_LEVEL = 0.005

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


def on_ka_bound(ka: float, bounds: tuple[float, float]) -> bool:
    """Whether a fitted binding constant rests on a bound of its box instead of inside it.

    The search works on log10(Ka) and resolves it to ``_LOG_KA_XTOL``, so an
    estimate within that of either end is one it could not move off: the data do
    not limit Ka on that side and the fit reports the bound. The single reading
    of "on its bound", wherever a fit is asked whether it ran to the edge of the
    box — a parameter held there is not one the residual paid for. A constant
    at or beyond an end of the box is not inside it either, such as the zero
    :meth:`Projection.one_step_p` sets the second constant of a stepwise model
    to.

    Parameters
    ----------
    ka : float
        The constant, in the unit *bounds* is given in; zero or more.
    bounds : tuple[float, float]
        The lower and the upper bound of the Ka box, both positive.
    """
    if not bounds[0] < ka < bounds[1]:
        return True
    low, high = np.log10(bounds)
    estimate = np.log10(ka)
    return not min(estimate - low, high - estimate) > _LOG_KA_XTOL


def _ka_text(value: float) -> str:
    """A binding constant as a message shown to the user writes it, e.g. ``1×10⁻⁸ M⁻¹``."""
    return f'{Q_(value, ""):.3g~P} M⁻¹'


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
    one_step_p : float or None
        For the second constant of a stepwise model, whether the first is
        fitted or held at one value, the p-value at which the data reject the
        model without the second binding step (that constant at zero) against
        the fit. Above
        :data:`SECOND_STEP_LEVEL` the interval claims no lower limit: it is
        open below, at the constant's lower bound. ``None`` for every other
        interval.
    inflation : float
        The design effect ``kappa`` the cut-off was widened by
        (:mod:`core.pipeline.inflation`); one for the plain F test.
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
    one_step_p: float | None = None
    inflation: float = 1.0

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
        Residual sum of squares of every row at ``ka``, shape ``(rows,)``,
        each titration point counted with its weight.
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
    """Outcome of the test of whether the rows of a projection share their binding constants.

    Attributes
    ----------
    excluded : tuple[int, ...]
        Rows left out: first those that need another Ka than the rows kept
        share, in row order, then those whose scatter is too large, in the
        order Cochran's test removed them (the keys of ``scatter``).
    p_values : dict[int, float]
        The shared-Ka p-value of every row but those left out for their
        scatter, against the rows kept: a kept row's for leaving it out of
        them, a row left out for its Ka's for adding it to them.
    level : float
        Family-wise level: each row's p-value is judged against
        ``level / rows``, and Cochran's test runs at ``level``.
    tested : bool
        ``False`` when the rows were not judged at all: fewer than
        :data:`REPLICATE_TEST_MIN` rows, or no residual degree of freedom.
    scatter : dict[int, tuple[float, float]]
        Every row left out for its scatter: Cochran's C when it was removed and
        the limit that C exceeded.
    """

    excluded: tuple[int, ...]
    p_values: dict[int, float]
    level: float
    tested: bool
    scatter: dict[int, tuple[float, float]]


@dataclass(frozen=True)
class FittedParameters:
    """What one solve fitted: the parameters it placed itself rather than held on a bound.

    The one reading of "fitted" behind every count of parameters: the residual
    degrees of freedom of an interval, the numerator of its F test, the
    lack-of-fit test, the columns of the conflict reference and of the runs
    test's reference, and the degrees of freedom of the input-aware interval.
    A parameter held on a bound takes no dimension from the residual, so
    counting it would make ``n - p`` smaller than the residual's own
    dimension.

    Attributes
    ----------
    ka : tuple[str, ...]
        The free binding constants strictly inside their box
        (:func:`on_ka_bound`), in ``Projection.free_ka`` order.
    columns : np.ndarray
        The whitened design columns of the signal parameters the bounded solve
        left strictly inside their bounds: the derivatives of minus the
        whitened residual with respect to those parameters.
    rank : int
        Numerical rank of those columns, read on the design as the model gives
        it. A rank and not a count of columns, because a mass balance ties
        columns together and the solve then returns one member of a family in
        which any of the tied coefficients may be the one inside its bounds.
    """

    ka: tuple[str, ...]
    columns: np.ndarray
    rank: int

    @property
    def count(self) -> int:
        """Parameters fitted: the ``p`` of a test."""
        return len(self.ka) + self.rank


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
    point_weights : np.ndarray, optional
        Weight of every titration point, shape ``(n_points,)``, shared by all
        rows: the inverse of the signal's relative variance there. Only their
        ratios matter. Ones when omitted.

    Attributes
    ----------
    point_weights : np.ndarray
        The weights ``omega`` of the titration points, shape ``(n_points,)``.
    ss_tot : np.ndarray
        Each row's weighted total sum of squares about its weighted mean,
        ``sum_i omega_i (y_i - ybar_omega)²``: the scale every residual sum of
        squares of the projection is a fraction of.
    second_step : str or None
        The binding constant of the second step of a stepwise model, the
        second of its two constants in the registry (``Ka_HG2``, ``Ka_H2G``),
        which the one-step test judges (:meth:`one_step_p`); ``None`` for a
        model with one binding constant.

    Raises
    ------
    ValueError
        For an assay that is not projectable, Ka bounds that are not positive
        or are inverted, signal rows of another length than the titrant grid,
        a signal row that is the same at every titration point, or point
        weights that are not one positive finite number per titration point.
    """

    def __init__(
        self,
        assay: BaseAssay,
        bounds: dict[str, tuple[Quantity, Quantity]],
        signals: np.ndarray | None = None,
        should_cancel: Callable[[], bool] | None = None,
        point_weights: np.ndarray | None = None,
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
        for lo, hi in self.ka_bounds.values():
            if not 0.0 < lo:
                raise FitRefused(
                    f'An association constant has the lower bound {_ka_text(lo)} under Parameter Bounds. Association '
                    'constants are searched on a logarithmic scale, so both of their bounds must be above zero. '
                    f'Enter a positive lower bound, such as the default of {_ka_text(1e-8)}, and fit again.'
                )
            if not lo <= hi:
                raise FitRefused(
                    f'An association constant has a lower bound of {_ka_text(lo)} above its upper bound of '
                    f'{_ka_text(hi)} under Parameter Bounds. Swap the two bounds and fit again.'
                )
        self.free_ka = tuple(k for k, (lo, hi) in self.ka_bounds.items() if lo != hi)
        # A model with two binding constants is stepwise, and the registry lists them in the order of the steps.
        self.second_step = self.ka_keys[1] if len(self.ka_keys) == 2 else None
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
        omega = np.ones(assay.n_points) if point_weights is None else np.asarray(point_weights, dtype=float)
        if omega.shape != (assay.n_points,) or not np.isfinite(omega).all() or (omega <= 0).any():
            raise ValueError(
                f'The point weights must be one positive, finite number per titration point ({assay.n_points}); '
                f'got {omega!r}.'
            )
        self.point_weights = omega
        self._whiten = np.sqrt(omega)
        centre = np.average(rows, axis=1, weights=omega)[:, np.newaxis]
        self.ss_tot = np.sum(omega * (rows - centre) ** 2, axis=1)
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
        """Each signal row's best weighted SSR and coefficients on one design.

        The signal rows and the design are whitened, every titration point
        multiplied by the square root of its weight, so the SSR is
        ``sum_i omega_i (y_i - (A c)_i)²`` and the coefficients are those that
        minimise it. A pinned coefficient (equal lower and upper bound)
        contributes a fixed signal and leaves the solve; the others are solved
        by bounded least squares on norm-scaled columns, which keeps
        coefficients spanning many orders of magnitude well conditioned. The
        solver can return a coefficient a rounding step beyond its bound, so
        each is clipped to its bounds after unscaling and the SSR is that of
        the clipped coefficients.

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
        target = (y - design[:, pinned] @ lb[pinned]) * self._whiten
        free, scale = self._free_columns(design * self._whiten[:, np.newaxis])
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
        """Columns of *design* whose coefficient is not pinned, and each column's norm (one for a zero column).

        Of the design it is handed: the whitened one where a solve or a
        distance from a bound is read, the model's own where a rank is.
        """
        free = design[:, self._lb != self._ub]
        return free, _norms(free)

    def row_ssr(self, ka: Mapping[str, float]) -> np.ndarray:
        """Best weighted residual sum of squares of every row at the binding constants *ka*.

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
        """Whitened projected residual ``sqrt(omega) (y - A c)`` of *row* at the binding constants *ka*.

        Its sum of squares is the row's :meth:`row_ssr`, and under the noise
        law the point weights state, every entry has the same variance. The
        design is that of ``assay.with_inputs(offsets)`` — the entered inputs
        when *offsets* is ``None`` or empty — and ``c`` the bounded
        least-squares coefficients of :meth:`row_ssr` on it. Every entry is
        infinite where the equilibrium model has no solution.
        """
        design, ssr, coef = self._solve_at(ka, offsets)
        if not np.isfinite(ssr[row]):
            return np.full(self.n_points, np.inf)
        return (self.signals[row] - design @ coef[row]) * self._whiten

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
            ranges = ' or '.join(f'between {_ka_text(lo)} and {_ka_text(hi)}' for lo, hi in self.ka_bounds.values())
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
            return (((design @ coef[used].T).T - y_used) * sqrt_w[:, None] * self._whiten[None, :]).ravel()

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
        """Parameter count ``p`` of the F test: what the best fit fitted (:meth:`fitted_parameters`)."""
        return self.fitted_parameters(fit.ka).count

    def fitted_parameters(
        self, ka: Mapping[str, float], offsets: Mapping[str, float] | None = None
    ) -> FittedParameters:
        """What the fit of the first row at *ka*, the inputs moved by *offsets*, fitted (see :meth:`solved`)."""
        return self.solved(ka, offsets)[1]

    def solved(
        self, ka: Mapping[str, float], offsets: Mapping[str, float] | None = None
    ) -> tuple[np.ndarray, FittedParameters]:
        """Each row's weighted SSR at *ka* and what the first row's fit there fitted, both from one bounded solve.

        A free binding constant is fitted when it lies strictly inside its box
        (:func:`on_ka_bound`), and a pinned one never is. A signal parameter is fitted when the bounded solve leaves it strictly
        inside its bounds, read as follows. None is fitted where the model has
        no solution.

        A coefficient is on a bound when moving it there changes the whitened
        curve by less than ``_RANK_RTOL`` of the signal's weighted variation
        about its weighted mean, the scale ``_R2_RESOLUTION`` reads a residual
        on, so a constant background under the signal leaves the count as it
        is. The change is the coefficient's distance from the bound times the
        norm of its whitened column, which is the coefficient in the
        norm-scaled variables the solve works in. The solver puts a bounded
        coefficient exactly on its bound in those variables, and unscaling,
        like the solve of the free ones, is good to rounding times the
        condition of a design whose rank is read at the same ``_RANK_RTOL``;
        a fitted coefficient, which scatters by at least the noise of one
        point in those variables, lands that close to a bound by chance in
        under 1e-5 of fits at a noise of 0.1 % of the signal.

        The rank of the fitted columns is read on the columns as the model
        gives them, the design ``_RANK_RTOL`` is measured on; whitening scales
        the rows by positive factors, which leaves a rank as it is.
        """
        design, ssr, coef = self._solve_at(ka, offsets)
        free = self._lb != self._ub
        whitened, scale = self._free_columns(design * self._whiten[:, np.newaxis])
        if np.isfinite(ssr[0]):
            margin = np.minimum(coef[0] - self._lb, self._ub - coef[0])[free] * scale
            inside = margin > _RANK_RTOL * np.sqrt(self.ss_tot[0])
        else:
            inside = np.zeros(np.count_nonzero(free), dtype=bool)
        columns = self._free_columns(design)[0][:, inside]
        ka_inside = tuple(key for key in self.free_ka if not on_ka_bound(ka[key], self.ka_bounds[key]))
        return ssr, FittedParameters(ka=ka_inside, columns=whitened[:, inside], rank=_rank(columns / _norms(columns)))

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

    def threshold(
        self,
        fit: ProjectedFit,
        level: float = LEVEL,
        n_constrained: int = 1,
        released: int = 0,
        inflation: float = 1.0,
    ) -> float:
        """Objective cut-off of the F test on a single-row projection.

        ``S_min (1 + kappa m F(level; m, n - p) / (n - p))`` with ``m`` the
        number of constrained binding constants (one for an interval, two for
        the joint region) plus *released*, the parameters the best fit fits and
        the fit at the tested Ka holds on a bound; ``p`` what the best fit
        fitted (:meth:`n_params`), ``S_min`` floored at ``_R2_RESOLUTION`` of
        the total sum of squares, and ``kappa`` the *inflation*, the design
        effect of :mod:`core.pipeline.inflation` (one: the plain F test).

        Raises
        ------
        FitRefused
            When the titration points are no more than the parameters the
            model has free — the free binding constants and the rank of the
            free signal columns, wherever the fit put them — so the data leave
            nothing to judge a fit by.
        ValueError
            For an *inflation* that is not a finite number of one or more.
        """
        self._require_one_row('A confidence threshold')
        _require_inflation(inflation)
        _require_dof(self.n_points, fit.n_free_ka + fit.rank)
        dof = self.n_points - self.n_params(fit)
        return self._floored(fit) * (1.0 + _allowed_rise(level, n_constrained + released, dof, inflation))

    def cut_off(
        self, fit: ProjectedFit, level: float = LEVEL, n_constrained: int = 1, inflation: float = 1.0
    ) -> Callable[[FittedParameters], float]:
        """:meth:`threshold` by what the fit at a tested Ka fitted: the cut-off that fit is judged against.

        Every step is widened by the same *inflation*.

        *released* is how far the rank of the signal columns that fit left
        inside their bounds falls short of the best fit's, so along the binding
        constants the cut-off is a step function that takes one value per
        rank. What was fitted comes from the solve that gave the judged
        residual (:meth:`solved`, :meth:`profile_point`).

        The other binding constant of a two-Ka model is not counted among what
        a tested value gives up when it rests on its bound there. Where it
        does, the objective is flat towards that bound — the data no longer
        tell the constant's value — and whether the inner search lands on the
        bound or a millionth of a decade inside it is arbitrary: on a stepwise
        titration of the weak regime the reading flips from one profile point
        to the next and the cut-off with it, by a third of the rise the test
        allows. Whether that bound, and not the data, closes the interval is
        what :meth:`_bound_behind` decides.
        """
        fitted = self.fitted_parameters(fit.ka).rank
        cuts: dict[int, float] = {}

        def at(point: FittedParameters) -> float:
            released = max(0, fitted - point.rank)
            if released not in cuts:
                cuts[released] = self.threshold(fit, level, n_constrained, released, inflation)
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
    ) -> tuple[dict[str, float], float, FittedParameters]:
        """The profile at ``ka_key = ka``: its free binding constants, the objective of all rows, what it fitted.

        The other free Ka is where :meth:`profile` finds its minimum. It is the
        point whose fit the F test judges, so what it fitted is what
        :meth:`cut_off` takes. With *ka_key* the only free Ka the objective
        and what was fitted are one solve (:meth:`solved`).
        """
        point = {ka_key: ka}
        others = [k for k in self.free_ka if k != ka_key]
        if not others:
            ssr, fitted = self.solved(point)
            return point, float(ssr @ self._weights(None)), fitted
        point[others[0]], value = self._inner_minimum(ka_key, ka, self._weights(None), inner_per_decade)
        return point, value, self.fitted_parameters(point)

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

    def interval(
        self, ka_key: str, fit: ProjectedFit, level: float = LEVEL, inflation: float = 1.0
    ) -> KaInterval | None:
        """Profile-likelihood interval of *ka_key* on a single-row projection; ``None`` when it is pinned.

        *inflation* is the design effect ``kappa`` of *ka_key*
        (:mod:`core.pipeline.inflation`) that widens the cut-off and the
        one-step test alike; one gives the plain F test.

        A Ka is accepted where its profile is at or below :meth:`cut_off` at
        its :meth:`profile_point`, and :func:`_cut_interval` cuts the interval
        from the profile. With *ka_key* the only free Ka the profile is read at
        ``_PROFILE_PER_DECADE`` across the Ka bounds. When it is a minimisation
        over another Ka, a point costs a search over that Ka, so the
        search-grid nodes are read first, their scan of the other Ka a row of
        the cached grid, and the profile is read again at
        ``_PROFILE_PER_DECADE``, the other Ka scanned at ``_INNER_PER_DECADE``,
        wherever its verdict turns (:func:`_scan_turns`). A closed edge of a
        two-Ka interval that only the bound of the other Ka produces is
        reported open and names that Ka (:meth:`_bound_behind`).

        The second constant of a stepwise model is also judged by a one-step
        test. A lower limit on it claims that the second binding step exists,
        so the data must first reject the model without that step
        (:meth:`one_step_p`) at :data:`SECOND_STEP_LEVEL`; where they do not,
        the interval is open below, at the constant's lower bound, and
        carries the p-value either way. Where the step is weakly identified the
        profile is shallow towards zero, and closed lower edges found there
        miss the true constant far more often than the level allows. The
        construction — a pretest of identification strength, then the
        least-favourable answer when it fails — follows Andrews & Cheng (2012,
        Econometrica 80:2153, sec. 5.2) in spirit only: their pretest level
        shrinks with the sample size, and a fixed level carries no guarantee
        of theirs; the coverage of the result is what the validation measures.
        The fits that pass the test at that level on data without a second
        step remain a recognisable subset (Buehler 1959, Ann. Math. Statist.
        30:845) over which the closed intervals miss.
        """
        self._require_one_row('A confidence interval')
        if ka_key not in self.free_ka:
            return None
        cut = self.cut_off(fit, level, inflation=inflation)

        def excess(inner_per_decade: int) -> Callable[[float], float]:
            def at(ka: float) -> float:
                _, value, fitted = self.profile_point(ka_key, ka, inner_per_decade)
                return value - cut(fitted)

            return at

        dof = self.n_points - self.n_params(fit)
        if len(self.free_ka) == 1:
            excess_at = excess(_SEARCH_PER_DECADE)
            points = {ka: excess_at(ka) for ka in _ka_grid(*self.ka_bounds[ka_key], _PROFILE_PER_DECADE)}
            interval, _ = _cut_interval(excess_at, points, fit.ka[ka_key], level, dof, inflation)
        else:
            (other,) = (k for k in self.free_ka if k != ka_key)
            objective = self._objective(self._weights(None))
            floor = self._floored(fit)

            def limited_by(edge: float) -> str:
                point, at_edge, fitted = self.profile_point(ka_key, edge, _INNER_PER_DECADE)
                return self._bound_behind(
                    ka_key,
                    point[other],
                    lambda inside: objective({ka_key: edge, other: inside}) - at_edge,
                    cut(fitted) - floor,
                )

            nodes = self._grid()[0][self.free_ka.index(ka_key)]
            node_excess = excess(_SEARCH_PER_DECADE)
            points = {float(ka): node_excess(ka) for ka in nodes.tolist()}
            interval, _ = _cut_interval(
                excess(_INNER_PER_DECADE), points, fit.ka[ka_key], level, dof, inflation, limited_by, nodes
            )
        if ka_key == self.second_step:
            return _with_one_step_test(interval, self.one_step_p(fit, inflation), self.ka_bounds[ka_key][0])
        return interval

    def one_step_p(self, fit: ProjectedFit, inflation: float = 1.0) -> float | None:
        """p-value of the model without the second binding step against *fit*; ``None`` unless that constant is free.

        The second step's constant is :attr:`second_step`, the second binding
        constant of a stepwise model; the test runs whenever it is free, the
        first constant fitted or held at one value. The model without the
        second step is that constant at zero exactly, not at its lower bound:
        the bound is the user's to move, and a signal coefficient without an
        upper bound can keep the second complex in the fit at any positive
        constant, however small, by growing as the constant shrinks. The test is the F test of the
        interval (:meth:`cut_off`) at that one profile point: ``m`` is the
        constant plus every signal parameter the fit fits and the solve at
        zero holds on a bound, among them the coefficient of the complex that
        no longer forms, and ``p = sf((P(0) / S_min - 1) (n - p) / (kappa m);
        m, n - p)`` with ``kappa`` the *inflation* of the interval's cut-off,
        so the test rejects exactly where ``P(0)`` passes that cut-off.
        """
        self._require_one_row('A one-step test')
        _require_inflation(inflation)
        if self.second_step not in self.free_ka:
            return None
        _, value, fitted = self.profile_point(self.second_step, 0.0, _INNER_PER_DECADE)
        m = 1 + max(0, self.fitted_parameters(fit.ka).rank - fitted.rank)
        return _rise_p(value / self._floored(fit) - 1.0, m, self.n_points - self.n_params(fit), inflation)

    def _bound_behind(self, ka_key: str, other_ka: float, rise: Callable[[float], float], allowed: float) -> str:
        """The other free Ka when its bound, and not the data, is what closes the profile of *ka_key* at an edge.

        The rule both interval engines apply at a closed edge of a two-Ka
        interval, each on its own objective. Along the profile of one constant
        of a stepwise model the other one compensates, until it reaches its
        bound; from there the objective rises and crosses the cut-off although
        the data would accept the pair further out. Such a crossing moves with
        the bound. It shows at the edge itself: the minimum over the other Ka,
        *other_ka*, lies on its bound (:func:`on_ka_bound`), and the objective
        still falls towards that bound — *rise*, the objective one search-grid
        step inside the bound less the objective at the edge, exceeds
        ``_BOUND_RISE`` of *allowed*, the rise the edge's own cut-off allows
        above the best objective. Where the data do set the edge, the other Ka
        is either inside its bounds or on a bound the objective no longer
        changes towards.

        Parameters
        ----------
        ka_key : str
            The binding constant whose profile has the edge.
        other_ka : float
            The other free binding constant at the edge's profile point.
        rise : Callable[[float], float]
            The objective at the edge with the other binding constant held at
            the value it is given, less the objective at the edge.
        allowed : float
            The edge's cut-off less the best objective.
        """
        (other,) = (k for k in self.free_ka if k != ka_key)
        lo, hi = self.ka_bounds[other]
        if not on_ka_bound(other_ka, (lo, hi)):
            return ''
        step = 10.0 ** (1.0 / _SEARCH_PER_DECADE)
        on_low = abs(np.log10(other_ka) - np.log10(lo)) <= abs(np.log10(hi) - np.log10(other_ka))
        inside = min(lo * step, hi) if on_low else max(hi / step, lo)
        return other if rise(inside) > _BOUND_RISE * allowed else ''


def replicate_outliers(
    projection: Projection,
    own_fits: Sequence[ProjectedFit] | None = None,
    level: float = REPLICATE_TEST_LEVEL,
    inflation: Sequence[float] | None = None,
    scatter_ssr: Sequence[float] | None = None,
) -> ReplicateTest:
    """Rows of *projection* that scatter far more than the others, or need another Ka than the others share.

    Each row r is fitted on its own, giving its own residual ``S_r`` and, with
    ``q`` the design rank at the shared optimum, ``k`` the free Ka and
    ``nu = n - q - k``, its own variance ``s_r² = S_r / nu``. Of the R rows
    given, fewer than half are ever left out — a majority is what defines the
    consensus — and the two steps below share that allowance in their order: a
    row that needs another Ka biases the average, while a noisy one only adds
    to its scatter.

    1. **Binding constants** — a clean-start forward search (Hadi & Simonoff
       1993, JASA 88:1264; Atkinson & Riani 2000, *Robust Diagnostic
       Regression Analysis*). Rows are weighted ``w_r = 1 / s_r²``, so each
       row's misfit is measured in units of its own scatter. For a set A,
       ``Qmin(A) = min_K sum_{r in A} w_r S_r(K)``, and a row r outside A is
       judged by ``T_r = Qmin(A + r) - Qmin(A) - nu`` against ``F(k, nu)``
       through ``p_r = sf(T_r / k)``. A starts as the smallest majority of the
       R rows — those whose own log10 Ka lie nearest the median of the rows'
       own fits, each Ka's distance scaled by its median absolute deviation.
       Rows join A one per round: of those outside with ``p_r > level / R``
       (Bonferroni over the R rows given), the one that raises ``Qmin`` least,
       so each is judged against every row that joined before it and the order
       of the rows does not matter. When none can join and fewer than the
       allowance are out, the row of A whose leave-one-out ``p_r`` (the same
       statistic, for A without r) is smallest leaves if it is at or below
       ``level / R`` and does not rejoin, as in Hadi & Simonoff's re-selection
       of the subset; the search then resumes. The rows outside A at the end
       are left out.
    2. **Scatter** — Cochran's test (Cochran 1941, Ann. Eugen. 11:47;
       ISO 5725-2:2019, 7.3.3) on the own variances of the rows kept: the
       largest is left out when ``C = s_max² / sum_r s_r²`` exceeds
       ``1 / (1 + (p - 1) / F⁻¹(1 - level/p; nu, (p - 1) nu))`` for the ``p``
       rows still in — the Bonferroni bound, which reproduces Cochran's tables
       to four decimals — and the test repeats on the rows left while at
       least :data:`REPLICATE_TEST_MIN` remain.

    Starting from the majority nearest the median is what keeps a minority
    that shares another Ka from steering the test: a start from every row fits
    the first shared Ka between the two groups, where a good row can look
    worse than the shifted ones and be left out in their place. The level is
    the ISO 5725-2 outlier level: a row significant at 5 % but not at 1 % is a
    "straggler" and is kept.

    Each own residual is floored at ``_R2_RESOLUTION`` of the row's total sum
    of squares, so a row the model reproduces to rounding gets a finite weight.

    Rows that are titrations of their own each carry their own errors of the
    titrant additions where those are stated, which move a row's own Ka by
    far more than its scatter does while its residual shows little of it.
    The binding-constant step then judges row r by ``T_r / (k kappa_r)``, with
    ``kappa_r`` the design effect of those errors on row r's own Ka
    (:func:`core.pipeline.inflation.inflation`, its joint form for two Ka):
    the first-order Rao-Scott correction of an F statistic whose numerator
    carries more variance than its reference (Rao & Scott 1984, Ann. Stat.
    12:46), the correction the interval's cut-off makes for the same errors.
    The same errors leave a residue in each row's residual that differs from
    row to row and is not scatter, so Cochran's test then compares the rows'
    residuals with that residue taken out (*scatter_ssr*).

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
        Family-wise level of each step.
    inflation : Sequence[float], optional
        ``kappa_r`` of every row, each at least one; ones when omitted, and
        the test is then the one of rows whose binding constants carry their
        scatter alone.
    scatter_ssr : Sequence[float], optional
        What Cochran's test compares for every row, in the units of its own
        residual ``S_r``; the own residuals themselves when omitted. Floored
        as they are.

    Returns
    -------
    ReplicateTest
    """
    rows = projection.signals.shape[0]
    untested = ReplicateTest(excluded=(), p_values={}, level=level, tested=False, scatter={})
    if rows < REPLICATE_TEST_MIN:
        return untested
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
        return untested
    allowance = (rows - 1) // 2  # the most rows that are fewer than half

    def q_min(members: list[int]) -> float:
        mask = np.zeros(rows)
        mask[members] = w[members]
        return nu * projection.fit(mask).objective

    kappa = np.ones(rows) if inflation is None else np.asarray(inflation, dtype=float)

    def p_value(extra: float, r: int) -> float:
        return float(f_dist.sf(max(extra - nu, 0.0) / (k * kappa[r]), k, nu))

    own_log_ka = np.log10([[fit.ka[key] for key in projection.free_ka] for fit in own_fits])
    deviation = np.abs(own_log_ka - np.median(own_log_ka, axis=0))
    spread = np.median(deviation, axis=0)
    distance = np.linalg.norm(deviation / np.where(spread > 0.0, spread, 1.0), axis=1)
    clean = sorted(np.argsort(distance, kind='stable')[: rows - allowance].tolist())
    left: set[int] = set()
    while True:
        q_clean = q_min(clean)
        rise = {r: q_min(clean + [r]) - q_clean for r in range(rows) if r not in clean}
        p_values = {r: p_value(extra, r) for r, extra in rise.items()}
        joining = [r for r in rise if r not in left and p_values[r] > level / rows]
        if joining:
            clean = sorted(clean + [min(joining, key=rise.get)])
            continue
        if len(rise) >= allowance:
            break
        drop = {r: q_clean - q_min([s for s in clean if s != r]) for r in clean}
        worst = max(drop, key=drop.get if inflation is None else lambda r: (drop[r] - nu) / kappa[r])
        if p_value(drop[worst], worst) > level / rows:
            break
        clean.remove(worst)
        left.add(worst)
    shifted = list(p_values)

    compared = own_ssr if scatter_ssr is None else np.maximum(scatter_ssr, _R2_RESOLUTION * projection.ss_tot)
    scatter: dict[int, tuple[float, float]] = {}
    while len(clean) >= REPLICATE_TEST_MIN and len(shifted) + len(scatter) < allowance:
        variances = compared[clean]
        c = float(variances.max() / variances.sum())
        limit = _cochran_limit(level, len(clean), nu)
        if c <= limit:
            break
        worst = clean[int(np.argmax(variances))]
        scatter[worst] = (c, limit)
        clean.remove(worst)
    if scatter:
        q_clean = q_min(clean)
        p_values = {r: p_value(q_min(clean + [r]) - q_clean, r) for r in shifted}
    p_values.update({r: p_value(q_clean - q_min([s for s in clean if s != r]), r) for r in clean})
    return ReplicateTest(excluded=(*shifted, *scatter), p_values=p_values, level=level, tested=True, scatter=scatter)


def _cochran_limit(level: float, groups: int, dof: int) -> float:
    """Critical value of Cochran's C at *level* for *groups* variances of *dof* degrees of freedom each.

    ``C_i = s_i² / sum s²`` exceeds ``c`` exactly when ``s_i²`` over the mean
    of the others exceeds ``(groups - 1) c / (1 - c)``, an ``F(dof, (groups -
    1) dof)`` variable; the Bonferroni bound over the groups gives
    ``1 / (1 + (groups - 1) / F⁻¹(1 - level / groups))``.
    """
    return 1.0 / (1.0 + (groups - 1) / f_dist.isf(level / groups, dof, (groups - 1) * dof))


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


def _require_inflation(inflation: float) -> None:
    """Refuse a design effect that would narrow a cut-off or is not a number."""
    if not (np.isfinite(inflation) and inflation >= 1.0):
        raise ValueError(f'The inflation of a cut-off must be a finite number of one or more; got {inflation!r}.')


def _allowed_rise(level: float, m: int, dof: float, inflation: float) -> float:
    """Relative rise of the residual sum of squares the F test of *m* parameters given up allows at *level*.

    ``kappa m F(level; m, dof) / dof`` with ``kappa`` the design effect
    *inflation*: the cut-off is ``S_min (1 + rise)``, and on the log scale of
    the penalised profile ``n log(1 + rise)`` above its minimum.
    """
    return inflation * m * f_dist.ppf(level, m, dof) / dof


def _rise_p(rise: float, m: int, dof: float, inflation: float) -> float:
    """p-value of a relative rise of the residual sum of squares by the F test of :func:`_allowed_rise`.

    ``sf(rise dof / (kappa m); m, dof)``: ``1 - level`` or less exactly where
    *rise* reaches the rise :func:`_allowed_rise` allows at *level*.
    """
    return float(f_dist.sf(rise * dof / (inflation * m), m, dof))


def _with_one_step_test(interval: KaInterval, one_step_p: float, lower_bound: float) -> KaInterval:
    """*interval* of the second constant of a stepwise model, judged by the one-step test at *one_step_p*.

    A closed lower side claims that the second binding step exists. Where the
    data do not reject the model without it at :data:`SECOND_STEP_LEVEL`, the
    lower side is open at *lower_bound*, the constant's lower bound.
    """
    if one_step_p > SECOND_STEP_LEVEL and not interval.open_low:
        return replace(interval, low=lower_bound, open_low=True, limited_by_low='', one_step_p=one_step_p)
    return replace(interval, one_step_p=one_step_p)


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


def _cut_interval(
    excess_at: Callable[[float], float],
    points: dict[float, float],
    best_ka: float,
    level: float,
    dof: float,
    inflation: float,
    limited_by: Callable[[float], str] | None = None,
    nodes: np.ndarray | None = None,
) -> tuple[KaInterval, np.ndarray]:
    """The interval of one binding constant cut from its profile: the one routine of both interval engines.

    Each engine hands in its own objective through *excess_at*, the profile
    at a Ka minus the cut-off of that profile point's own fit, and the Ka it
    has read the profile at with their excess, *points*; *best_ka*, the
    estimate, is always accepted. The fixed-input profile is the residual sum
    of squares against :meth:`Projection.cut_off`, the penalised one ``n log S
    + z'z`` against its own step cut-off (:mod:`core.pipeline.input_aware`).

    With the search-grid *nodes* of the constant given, *points* are a coarse
    reading, and the profile is read again at ``_PROFILE_PER_DECADE`` wherever
    its verdict turns (:func:`_scan_turns`); without them *points* are the
    whole profile. :func:`_interval` then closes the envelope of the accepted
    points by root finding, and *limited_by*, called at each closed edge, low
    then high, names the binding constant whose bound and not the data closes
    it (:meth:`Projection._bound_behind`), which opens that side.

    Returns
    -------
    tuple[KaInterval, np.ndarray]
        The interval at *level*, *dof* and *inflation*, and the Ka it was cut
        from, ascending.
    """
    if nodes is not None:
        _scan_turns(points, excess_at, best_ka, nodes)
    grid = np.array(sorted(points))
    excess_grid = np.array([points[ka] for ka in grid.tolist()])
    (low, high), (open_low, open_high), split, (unsolvable_low, unsolvable_high) = _interval(
        excess_at, grid, excess_grid, best_ka
    )
    limited_by_low = '' if open_low or limited_by is None else limited_by(low)
    limited_by_high = '' if open_high or limited_by is None else limited_by(high)
    interval = KaInterval(
        low=low,
        high=high,
        open_low=open_low or bool(limited_by_low),
        open_high=open_high or bool(limited_by_high),
        level=level,
        dof=dof,
        split=split,
        unsolvable_low=unsolvable_low,
        unsolvable_high=unsolvable_high,
        limited_by_low=limited_by_low,
        limited_by_high=limited_by_high,
        inflation=inflation,
    )
    return interval, grid


def _scan_turns(
    points: dict[float, float], excess_at: Callable[[float], float], best_ka: float, nodes: np.ndarray
) -> None:
    """Read a coarse profile again at ``_PROFILE_PER_DECADE`` wherever its verdict turns, adding to *points*.

    *points* holds the excess of the profile at the Ka read so far, at most
    one per search-grid node of *nodes*. What the interval depends on is
    where the verdict of the test turns over, so exactly those stretches are
    read again at the density a one-Ka fixed-input interval uses everywhere:
    every stretch between two neighbouring points that disagree, and then
    search cell by search cell outward past the accepted points until a whole
    cell holds nothing the test accepts, or a Ka bound is reached. An edge is
    therefore closed only where a full search cell, read five times finer,
    rejects every Ka in it, while a stretch the coarse points accept
    throughout costs nothing further. When no coarse point is accepted, the
    stretch around the estimate is read.

    The stepwise models need that resolution at the turning points: their
    profile is a minimum that moves from one K₁·K₂ valley to another, and the
    cut-off steps where a signal parameter reaches its bound, so the accepted
    Ka can break into stretches narrower than a search cell. Read from the
    nodes alone the envelope stops short of Ka the test accepts and the gap
    inside it goes unreported.
    """
    coarse = np.array(sorted(points))
    logs = np.log10(coarse)
    node_logs = np.log10(nodes)
    lo, hi = float(node_logs[0]), float(node_logs[-1])
    cell = (hi - lo) / max(nodes.size - 1, 1)
    dense: set[float] = set()

    def scan(a: float, b: float) -> bool:
        """Profile from ``10**a`` to ``10**b`` at the profile density; whether any Ka there is accepted."""
        accepts = False
        for ka in _ka_grid(10.0**a, 10.0**b, _PROFILE_PER_DECADE).tolist():
            if ka not in dense:
                dense.add(ka)
                points[ka] = excess_at(ka)
            accepts = accepts or points[ka] <= 0
        return accepts

    accepted = np.array([points[ka] <= 0 for ka in coarse.tolist()])
    turns = np.flatnonzero(accepted[:-1] != accepted[1:])
    for i in turns:
        scan(float(logs[i]), float(logs[i + 1]))
    if not turns.size and not accepted.any():
        # The estimate is the only Ka the test is known to accept, and it lies
        # between two coarse points: that stretch is where the interval is.
        i = int(np.clip(np.searchsorted(logs, np.log10(best_ka)) - 1, 0, max(coarse.size - 2, 0)))
        scan(float(logs[i]), float(logs[min(i + 1, coarse.size - 1)]))
    reached = [ka for ka, e in points.items() if e <= 0] + [best_ka]
    left = max(float(np.log10(min(reached))), lo)
    right = min(float(np.log10(max(reached))), hi)
    while left > lo and scan(max(left - cell, lo), left):
        left = max(left - cell, lo)
    while right < hi and scan(right, min(right + cell, hi)):
        right = min(right + cell, hi)


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
