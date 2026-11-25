"""The noise law the replicates show, and the point weights a fit reads from it.

Two replicates of one titration differ by two things: the noise of each
measurement, and an affine image ``alpha + beta·signal`` of the whole curve — a
lamp, gain or path-length difference between runs. The second is not noise
about the fitted model. An affine image of any registered forward model is a
member of the same model, because the offset and the signal coefficients absorb
it (``Signal = I0 + I_dye_free·[D_free] + I_dye_bound·[HD]`` maps to
``alpha + beta·Signal`` by moving those three coefficients), so a whole
replicate lying 3 % high says nothing about how precise its points are. The
scatter that carries the noise is therefore the scatter of each replicate about
its OWN line in the mean curve (:func:`replicate_scatter`); the raw per-point
variance of the replicates is not it. The replicated datasets in ``data/`` show
why: their replicates differ by scale factors of 0.97 to 1.03, and a scale
factor alone makes the raw spread grow with the signal. The raw spread of
``data/DBA_system_host_to_dye.txt`` reads a proportional share of 0.97 (0.94
once the default outlier removal has run) where the scatter about each
replicate's own line reads 0.20 (0.37).

:func:`noise_law` reads one shape parameter of the two-component law
``var(y) = a² + (b·y)²`` off that scatter — a constant floor plus a part
proportional to the signal, the standard analytical-chemistry model (Rocke and
Lorenzato 1995). It contains constant, proportional and mixed noise exactly, its
share of the two parts is bounded by construction because both variances are
non-negative, and it uses ``y²``, so a point below zero is read like one
above it.

Only the SHAPE of the variance reaches the fit. The confidence interval's
threshold is a residual-variance F threshold, which profiles the noise level
out, so the level is reported, as the floor ``a`` in au and the proportional
part ``b`` as a fraction of the signal, and is otherwise used only to draw the
simulated replicates of the lack-of-fit test. What the fit gets is one vector
of point weights, ``NoiseLaw.weights``, read off the curve the caller passes,
which :class:`~core.pipeline.varpro.Projection` whitens its signal rows and
design with; and the range of shares the scatter is consistent with,
``NoiseLaw.share_set``, over which the interval allows for the share being
an estimate. A single titration cannot show how the noise varies with the
signal, and is fitted with weights of exactly one — the arithmetic of a fit
without a noise law, to the last bit.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import digamma
from scipy.stats import chi2

#: Replicates needed to read a noise law: a variance needs two values.
MIN_REPLICATES = 2

# Titration points that must show scatter before a law is read off them. The
# scatter gives two numbers, a level and a share, and the third point is the
# one left to judge them by.
_MIN_SCATTER_POINTS = 3

# Nodes of the share grid on [0, 1]. The objective need not be unimodal with
# few replicates, so the minimum is found on a grid before it is refined; 101
# nodes put them 0.01 apart, the last digit the law is reported to, and the
# bounded refinement closes the rest. The whole search costs about 4 ms on
# the replicated datasets in ``data/``, once per fit.
_SHARE_NODES = 101

# Absolute tolerance of the bounded refinement of the share: three digits
# beyond the two the law is reported to, and far below what the scatter of a
# handful of replicates resolves.
_SHARE_XATOL = 1e-5

_SHARE_GRID = np.linspace(0.0, 1.0, _SHARE_NODES)

# Confidence level of the share set. The interval takes the worst case of its
# design effect over this set, the device of Berger and Boos (1994, JASA
# 89:1012) for a nuisance parameter that is only estimated: the set misses the
# true share with probability 0.01, and the interval's level is kept as it is.
_SHARE_SET_LEVEL = 0.99


class NoiseBasis(Enum):
    """What a noise law was read from. The values are the tokens in results files."""

    REPLICATES = 'replicates'
    SINGLE_TITRATION = 'single_titration'
    TOO_FEW_POINTS = 'too_few_points'


@dataclass(frozen=True)
class NoiseLaw:
    """The law ``var(y) = floor² + (proportional·y)²`` the replicates show.

    Attributes
    ----------
    basis : NoiseBasis
        What the law was read from. Only ``REPLICATES`` carries an estimate;
        the other two state why the noise is taken as constant instead.
    share : float
        The share of the variance, at the rms signal, that grows with the
        signal squared: ``0`` constant noise, ``1`` proportional noise. It is
        the only number of the law that reaches the fit.
    floor : float
        ``a``, in au: the standard deviation of the constant part of one
        replicate's noise.
    proportional : float
        ``b``: the standard deviation of the proportional part, as a fraction
        of the signal.
    reference : float
        The rms of the mean signal, in au. It is where the law's variance is
        ``floor² + (proportional·reference)²`` and the weight is 1.
    n_replicates : int
        How many replicates the law was read from.
    u_floor : float
        The smallest ``u = ybar²/reference²`` among the titration points the
        law was read on. A point below it takes the weight of a point at it:
        the law is not extrapolated beneath the signals that showed it. ``0``
        where a point the law was read on has a mean of zero.
    share_set : tuple[float, float]
        The shares the scatter is consistent with at 99 %, ``(low, high)``,
        always containing *share* (:func:`noise_law`). ``(0.0, 0.0)`` where no
        law was read.
    """

    basis: NoiseBasis
    share: float = 0.0
    floor: float = 0.0
    proportional: float = 0.0
    reference: float = 0.0
    n_replicates: int = 1
    u_floor: float = 0.0
    share_set: tuple[float, float] = (0.0, 0.0)

    @property
    def estimated(self) -> bool:
        """Whether the replicates showed the law, rather than the noise being taken as constant."""
        return self.basis is NoiseBasis.REPLICATES

    @property
    def level(self) -> float:
        """The variance of one replicate's noise at the rms signal, ``floor² + (proportional·reference)²``, in au².

        A point of weight ``w`` has the variance ``level / w``.
        """
        return self.floor**2 + (self.proportional * self.reference) ** 2

    def relative_variance(self, signal: np.ndarray, share: float | None = None) -> np.ndarray:
        """The law's variance at *signal* over its variance at the rms signal, ``(1 - s) + s·max(u, u_floor)``.

        ``u = signal²/reference²`` and ``s`` is *share*, the law's own share
        when omitted; a point's variance is ``level`` times this. Another
        share is the variance the same scatter states under that share, which
        is how the interval reads the law over its :attr:`share_set`.

        Where no law was read, and where ``s`` is exactly zero, this is
        ``np.ones`` — exactly.

        Parameters
        ----------
        signal : np.ndarray
            The signal at each titration point, in au.
        share : float or None
            The share to read the variance at; the law's own when omitted.
        """
        signal = np.asarray(signal, dtype=float)
        s = self.share if share is None else share
        if not self.estimated or s == 0.0:
            return np.ones(signal.shape)
        return (1.0 - s) + s * np.maximum(signal**2 / self.reference**2, self.u_floor)

    def weights(self, signal: np.ndarray) -> np.ndarray:
        """Weight of every titration point, ``1 / relative_variance(signal)``.

        The weights are the inverse of the law's variance, scaled to 1 at the
        rms signal, so a point the replicates show to be twice as precise
        counts four times. The caller passes the curve the weights are read
        off. Where the share is above zero that is the fitted curve of a first
        fit, made with the weights at the means of the replicates: two-stage
        generalised least squares with a variance that depends on the mean
        (Carroll and Ruppert 1988, *Transformation and Weighting in
        Regression*, ch. 2-3; Davidian and Carroll 1987, JASA 82:1079). The
        curve, and not the means, because a mean that its own noise pushed
        near zero would otherwise get a weight set by that same noise: a few
        replicates of constant noise give weight ratios of 1e5 to 1e9 there
        and land the binding constant many decades off. The weights are then
        fixed: the conditional fit, the input-aware fit, every profile point
        and every sensitivity sample see the same ones.

        Where no law was read, and where the share came out exactly zero, this
        is ``np.ones`` — exactly, so that whitening by its square root multiplies
        by 1.0 and the fit is the unweighted fit to the last bit.

        Size: ``max(w)/min(w) <= max(u) / u_floor``, reached only at
        ``share == 1``; below that every weight is under ``1 / (1 - share)``.
        The bound is the range of ``u`` over the points the law was read on,
        and it is large when one of them has a mean near zero: a point whose
        mean is 1 % of the largest can carry 1e4 times the weight of the top
        point. That is the right weight when the noise really is proportional
        down to that point.

        Parameters
        ----------
        signal : np.ndarray
            The curve to read the weights off at each titration point, in au.
        """
        return 1.0 / self.relative_variance(signal)

    def describe(self) -> str:
        """The law in one plain sentence, for the summary, the report and the CSV.

        The law is reported to two digits: what the scatter of a handful of
        replicates shows, and no more.
        """
        if self.basis is NoiseBasis.SINGLE_TITRATION:
            return 'taken as constant — one titration cannot show how the noise varies with the signal.'
        if self.basis is NoiseBasis.TOO_FEW_POINTS:
            return 'taken as constant — the replicates scatter at too few titration points to show how it varies.'
        scatter = f'(scatter of {self.n_replicates} replicates about the curve)'
        if self.share == 0.0:
            return f'constant, about {_two_digits(self.floor)} a.u. {scatter}'
        percent = f'{100.0 * self.proportional:.1f} %'
        if self.share == 1.0:
            return f'proportional to the signal, about {percent} of it {scatter}'
        return f'about {percent} of the signal plus {_two_digits(self.floor)} a.u. {scatter}'

    def to_dict(self) -> dict:
        """Every field, as written to a results file: the basis token and finite numbers."""
        return {**asdict(self), 'basis': self.basis.value, 'share_set': list(self.share_set)}

    @classmethod
    def from_dict(cls, d: dict) -> 'NoiseLaw':
        """The law a results file holds.

        A file without ``u_floor`` holds no floor on ``u``, and one without
        ``share_set`` holds the share alone, ``(share, share)``.
        """
        share_set = d.get('share_set', (d.get('share', 0.0),) * 2)
        return cls(**{**d, 'basis': NoiseBasis(d['basis']), 'share_set': (float(share_set[0]), float(share_set[1]))})


def _two_digits(value: float) -> str:
    """*value* to two significant digits, written out in full rather than as a power of ten."""
    return np.format_float_positional(float(f'{value:.2g}'), trim='-')


def replicate_scatter(signals: np.ndarray, weights: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Scatter of every replicate about its own affine image of the mean curve.

    Each replicate is regressed on the columns ``[1, ybar]`` — one intercept
    and one scale in the mean signal, the affine freedom every registered model
    already has — with the points weighted by *weights*, and what is left is the
    noise. The columns are the same for all replicates, and :func:`_scatter`
    projects every replicate off them at once. The noise law and the
    lack-of-fit test, observed and simulated, all read the scatter there.

    The returned residuals are whitened, ``sqrt(w)·(y - alpha - beta·ybar)``,
    and the leverage ``h_i`` is how much of the fitted line one point carries:
    ``sum_r e_ri² / (1 - h_i)`` estimates ``(m - 1)`` times the whitened
    variance at that point, the leverage correction undoing what the line
    removed and the missing replicate being the one the mean costs.

    Parameters
    ----------
    signals : np.ndarray
        The replicates, shape ``(m, n)`` with ``m >= 2`` and ``n >= 3``.
    weights : np.ndarray or None
        Weight of each titration point; equal weights when omitted.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        The whitened residuals, shape ``(m, n)``, and the leverages, shape ``(n,)``.

    Raises
    ------
    ValueError
        With fewer than two replicates, fewer than three points, a mean signal
        that does not vary (the two columns are then the same direction), or
        weights of the wrong shape.
    """
    y = np.asarray(signals, dtype=float)
    if y.ndim != 2 or y.shape[0] < MIN_REPLICATES:
        raise ValueError(
            f'The replicate scatter needs {MIN_REPLICATES} or more replicates; the signals have shape {y.shape}.'
        )
    m, n = y.shape
    if n < _MIN_SCATTER_POINTS:
        raise ValueError(
            f'The replicate scatter needs {_MIN_SCATTER_POINTS} or more titration points; the signals have {n}.'
        )
    mean = y.mean(axis=0)
    if np.ptp(mean) == 0.0:
        raise ValueError('The mean signal is the same at every titration point, so there is no curve to scatter about.')
    w = np.ones(n) if weights is None else np.asarray(weights, dtype=float)
    if w.shape != (n,):
        raise ValueError(f'The weights must hold one value per titration point ({n}); they have shape {w.shape}.')
    residuals, leverage = _scatter(y, w[np.newaxis])
    return residuals[0], leverage[0]


def noise_law(signals: np.ndarray | None) -> NoiseLaw:
    """The noise law the replicates show, or why they cannot show one.

    With ``ybar`` the mean signal and ``u_i = ybar_i² / mean(ybar²)``, a
    candidate share ``lam`` states the relative variance
    ``g_i(lam) = (1 - lam) + lam·max(u_i, u_floor)``, which is 1 at the rms
    signal. Under the right share, the scatter of :func:`replicate_scatter`
    whitened by ``1 / sqrt(g)`` is flat along the titration, so the estimate is
    the share that makes it flattest:

    ``J(lam) = sum_i (log t_i - mean log t)²``, ``t_i = sum_r e_ri² / (1 - h_i)``

    over the points that scatter — those where the replicates differ at all,
    and whose ``t_i`` stands above the rounding error of the projection that
    produced it, decided once with equal weights so that every share is judged
    on the same points. On a log scale because the spread of ``log t_i`` does
    not depend on the noise level. The detrending is weighted by the same share
    it is judged at, so there is one objective and no fixed-point iteration.

    One wild value of one replicate moves the share: it enters that
    replicate's detrending line and the mean curve as well as its own ``t_i``.
    A replicate carrying it differs from the others, which is what the
    replicate test of the fit judges (:func:`~core.pipeline.varpro.replicate_outliers`);
    the law is read from whatever replicates it is handed.

    ``u_floor`` is the smallest ``u_i`` among the points that scatter, and
    every ``u_i`` below it is read as ``u_floor``: a point that judges nothing,
    such as a blank-subtracted point that is zero in every replicate, is given
    the variance of the smallest signal the law was read on, and the law is not
    extrapolated beneath it. ``J`` is infinite where a share makes a variance
    zero, which only a point that scatters with a mean of exactly zero can do,
    at a share of 1.

    The minimum is taken on ``linspace(0, 1, 101)`` and then refined by bounded
    Brent between the best node's neighbours, kept only if it is lower — the
    grid because ``J`` need not be unimodal with few replicates. A refinement
    that ends within its own tolerance of 0 is 0, so a share of zero is exactly
    zero; one that ends within it of 1 is 1 where ``J(1)`` is finite. Nothing
    here draws a random number.

    The level ``c`` follows from the same scatter, as the mean of ``log t_i``
    corrected for the bias of a log chi-square on ``m - 1`` degrees of freedom;
    ``floor = sqrt(c(1 - lam))`` and ``proportional = sqrt(c·lam)/reference``.
    It is reported and never fitted against: the F threshold profiles the noise
    level out.

    No degrees of freedom are charged for the share. It comes from the scatter
    of the replicates about their own line, which under normal noise is
    independent of the mean the fit sees.

    The share set is the range of shares the same scatter is consistent with,
    read from the scatter at equal weights that the grid search computes at its
    first node. Detrending a replicate is a fixed linear map ``I - H`` (``H`` the
    projector on ``[1, ybar]``), so under the share ``lam`` the scatter at point
    ``i`` is ``c·d_i(lam)`` times a chi-square on ``m - 1`` degrees of freedom,
    ``d_i(lam) = sum_j (I - H)_ij² g_j(lam)``. With ``S`` the ``N`` points that
    scatter and ``s_i`` their summed squared scatter, the gamma pseudo-likelihood
    with the level ``c`` profiled out is

    ``l(lam) = -(m - 1)/2 · [sum_S log d_i(lam) + N log(sum_S (s_i / d_i(lam)) / (N (m - 1)))]``

    and the set is the hull of the 101 grid shares with
    ``((n - 2)/n) · 2 (max l - l(lam)) <= chi2_1(0.99)``, together with the
    estimate. The factor ``(n - 2)/n`` counts the scatter's dimensions: the
    affine detrending leaves ``(m - 1)(n - 2)`` of the ``(m - 1) n``, and a
    likelihood that treats every point's scatter as a chi-square of its own
    counts ``n / (n - 2)`` times the evidence there is. The detrending is held
    at equal weights because a detrending weighted by ``1/g(lam)`` passes
    through any point that ``lam`` gives most of the weight: that point's
    scatter then stays put while its ``g`` shrinks, and the likelihood climbs
    without bound toward every share that gives one point most of the weight —
    the set collapses onto such a share whatever the noise. On simulated
    constant, proportional and mixed noise (m = 2 to 8, n = 8 to 30, lowest
    signal 0.4 % to 30 % of the highest) the set holds the true share in 0.97
    to 1.00 of datasets.

    Parameters
    ----------
    signals : np.ndarray or None
        The replicates, shape ``(m, n)``; ``None`` or one row for a single
        titration.

    Returns
    -------
    NoiseLaw
        Basis ``REPLICATES`` with the estimate; ``SINGLE_TITRATION`` where
        there is one signal, and ``TOO_FEW_POINTS`` where two or more
        replicates scatter at fewer than three titration points. The last two
        give weights of one, and say so in :meth:`NoiseLaw.describe`.
    """
    if signals is None:
        return NoiseLaw(NoiseBasis.SINGLE_TITRATION)
    y = np.atleast_2d(np.asarray(signals, dtype=float))
    m, n = y.shape
    if m < MIN_REPLICATES:
        return NoiseLaw(NoiseBasis.SINGLE_TITRATION)
    too_few = NoiseLaw(NoiseBasis.TOO_FEW_POINTS, n_replicates=m)
    if n < _MIN_SCATTER_POINTS:
        return too_few
    mean = y.mean(axis=0)
    if np.ptp(mean) == 0.0:
        return too_few
    reference = float(np.sqrt(np.mean(mean**2)))
    u = mean**2 / reference**2
    scatters = _scattering_points(y)
    if scatters.sum() < _MIN_SCATTER_POINTS:
        return too_few
    u_floor = float(u[scatters].min())
    relative = np.maximum(u, u_floor)
    grid = _scatter_sums(y, relative, _SHARE_GRID)
    found = _read_share(y, relative, scatters, refine=True, grid=grid)
    if found is None:
        return too_few
    share, sums, leverage = found

    dof = m - 1
    scatter = sums[scatters] / (1.0 - leverage[scatters])
    level = float(np.exp(np.mean(np.log(scatter / dof)) - digamma(dof / 2) + np.log(dof / 2)))
    return NoiseLaw(
        NoiseBasis.REPLICATES,
        share=share,
        floor=float(np.sqrt(level * (1.0 - share))),
        proportional=float(np.sqrt(level * share) / reference),
        reference=reference,
        n_replicates=m,
        u_floor=u_floor,
        share_set=_share_set(share, grid[0][0], mean, relative, scatters, m),
    )


def _share_set(
    share: float, scatter: np.ndarray, mean: np.ndarray, relative: np.ndarray, scatters: np.ndarray, m: int
) -> tuple[float, float]:
    """The hull of the grid shares the scatter is consistent with at 99 %, and *share* (see :func:`noise_law`).

    *scatter* is ``sum_r e_ri²`` at equal weights for ``m`` replicates of mean
    *mean*. The likelihood ratio is ``(m - 1)·(A(lam) - min A)`` with
    ``A = sum_S log d_i + N log sum_S s_i / d_i``: ``2 (max l - l)`` once the
    constants of ``l`` cancel. A share that makes a variance zero is outside
    the set.
    """
    n = mean.size
    centred = mean - mean.mean()
    kept = (np.eye(n) - 1.0 / n - np.outer(centred, centred) / (centred @ centred)) ** 2
    g = (1.0 - _SHARE_GRID)[:, np.newaxis] + _SHARE_GRID[:, np.newaxis] * relative
    d = (g @ kept.T)[:, scatters]
    with np.errstate(divide='ignore', invalid='ignore'):
        a = np.sum(np.log(d), axis=-1) + int(scatters.sum()) * np.log(np.sum(scatter[scatters] / d, axis=-1))
    a = np.where(np.isfinite(a), a, np.inf)
    ratio = (m - 1) * (a - a.min())
    accepted = _SHARE_GRID[(n - 2) / n * ratio <= chi2.ppf(_SHARE_SET_LEVEL, 1)]
    return float(min(accepted.min(), share)), float(max(accepted.max(), share))


def _scattering_points(signals: np.ndarray) -> np.ndarray:
    """Which titration points the replicates scatter at, the points a noise law is read on.

    A point scatters where the replicates differ at all and their scatter
    about their own lines, at equal weights, stands above the rounding error of
    the projection that produced it. Replicates that agree to the last bit leave
    that rounding error, not zero: the residuals are accurate to about eps
    times the norm of the data, so a scatter below that square says the point
    did not scatter — the eps·norm rule a matrix rank is decided by. A point the
    line reproduces exactly (leverage 1) leaves no finite ratio and judges
    nothing either.

    Parameters
    ----------
    signals : np.ndarray
        The replicates, shape ``(m, n)``.

    Returns
    -------
    np.ndarray
        One boolean per titration point.
    """
    y = np.asarray(signals, dtype=float)
    sums, leverage = _scatter_sums(y, np.ones(y.shape[-1]), np.zeros(1))
    with np.errstate(divide='ignore', invalid='ignore'):
        t = sums[0] / (1.0 - leverage[0])
    rounding = (np.finfo(float).eps * float(np.linalg.norm(y))) ** 2
    return (np.ptp(y, axis=0) > 0.0) & np.isfinite(t) & (t > rounding)


def _read_share(
    signals: np.ndarray,
    relative: np.ndarray,
    scatters: np.ndarray,
    *,
    refine: bool,
    grid: tuple[np.ndarray, np.ndarray] | None = None,
) -> tuple[float | np.ndarray, np.ndarray, np.ndarray] | None:
    """The share that makes the whitened scatter flattest, with the scatter it leaves.

    The estimator of :func:`noise_law`, on one set of replicates or on a stack
    of them: ``J`` (see there) on ``linspace(0, 1, 101)``, and with *refine*
    the bounded Brent refinement between the best node's neighbours and the
    snap to an end. *relative* and *scatters* are held as given, so every set
    in a stack is judged on the same points and the same ``u``.

    Parameters
    ----------
    signals : np.ndarray
        Replicates, shape ``(m, n)``, or a stack of them, shape ``(..., m, n)``
        (grid only).
    relative : np.ndarray
        ``max(u, u_floor)`` at every titration point, shape ``(n,)``.
    scatters : np.ndarray
        The points ``J`` sums over (:func:`_scattering_points`).
    refine : bool
        Refine the best node by bounded Brent; one set of replicates only.
    grid : tuple[np.ndarray, np.ndarray] or None
        The scatter of :func:`_scatter_sums` on the share grid, where the
        caller has it already; computed here when omitted.

    Returns
    -------
    tuple or None
        The share, shape ``(...)``, and at it the sum over the replicates of
        each point's squared whitened scatter, ``sum_r e_ri²``, and the
        leverages, shape ``(..., n)`` each. ``None`` where ``J`` is infinite at
        every node of a refined search.
    """
    sums, leverage = _scatter_sums(signals, relative, _SHARE_GRID) if grid is None else grid
    values = _flatness(sums, leverage, scatters)
    best = values.argmin(axis=-1)
    if not refine:
        pick = best[..., np.newaxis, np.newaxis]
        return (
            _SHARE_GRID[best],
            np.take_along_axis(sums, pick, axis=-2)[..., 0, :],
            np.take_along_axis(leverage, pick, axis=-2)[..., 0, :],
        )
    best = int(best)
    if not np.isfinite(values[best]):
        return None

    def objective(share: float) -> float:
        return float(_flatness(*_scatter_sums(signals, relative, np.array([share])), scatters)[0])

    refined = minimize_scalar(
        objective,
        bounds=(_SHARE_GRID[max(best - 1, 0)], _SHARE_GRID[min(best + 1, _SHARE_NODES - 1)]),
        method='bounded',
        options={'xatol': _SHARE_XATOL},
    )
    share = float(refined.x) if refined.fun < values[best] else float(_SHARE_GRID[best])
    # Bounded Brent never evaluates an end of its bracket, so a minimum at 0 or
    # 1 comes back a tolerance short of it. Within that tolerance the share is
    # the end: exactly 0, where the weights are exactly one, or exactly 1 where
    # J is finite there.
    if share < _SHARE_XATOL:
        share = 0.0
    elif share > 1.0 - _SHARE_XATOL and np.isfinite(values[-1]):
        share = 1.0
    sums, leverage = _scatter_sums(signals, relative, np.array([share]))
    return share, sums[0], leverage[0]


def _scatter_sums(signals: np.ndarray, relative: np.ndarray, shares: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """``sum_r e_ri²`` and the leverages of :func:`replicate_scatter`, at the weights ``1/g(share)`` of every share.

    Returns arrays of shape ``(..., len(shares), n)``; a share that makes a
    variance zero gives NaN.
    """
    g = (1.0 - shares)[:, np.newaxis] + shares[:, np.newaxis] * relative
    with np.errstate(divide='ignore'):
        residuals, leverage = _scatter(signals, 1.0 / g)
    return np.sum(residuals**2, axis=-2), leverage


def _scatter(signals: np.ndarray, weights: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The scatter of :func:`replicate_scatter`, for a stack of replicate sets and several weight vectors at once.

    The columns ``[1, ybar]`` whitened by ``sqrt(w)`` are made orthonormal by
    centring ``ybar`` on its weighted mean, and each replicate's deviation from
    the mean curve is projected off them. The deviation, and not the
    replicate, because the mean curve lies in the span and leaves nothing:
    projecting the deviation does not subtract two numbers the size of the
    signal to leave one the size of the noise.

    Parameters
    ----------
    signals : np.ndarray
        Replicates, shape ``(..., m, n)``.
    weights : np.ndarray
        Weight vectors, shape ``(k, n)``.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        The whitened residuals, shape ``(..., k, m, n)``, and the leverages,
        shape ``(..., k, n)``; NaN where a weight is infinite.
    """
    y = np.asarray(signals, dtype=float)
    mean = y.mean(axis=-2)
    deviations = (y - mean[..., np.newaxis, :])[..., np.newaxis, :, :]
    with np.errstate(divide='ignore', invalid='ignore'):
        root = np.sqrt(weights)
        first = root / np.linalg.norm(root, axis=-1, keepdims=True)
        centred = mean[..., np.newaxis, :] - np.sum(
            root**2 * mean[..., np.newaxis, :], axis=-1, keepdims=True
        ) / np.sum(root**2, axis=-1, keepdims=True)
        second = root * centred
        second = second / np.linalg.norm(second, axis=-1, keepdims=True)
        whitened = deviations * root[:, np.newaxis, :]
        residuals = (
            whitened
            - np.sum(whitened * first[:, np.newaxis, :], axis=-1, keepdims=True) * first[:, np.newaxis, :]
            - np.sum(whitened * second[..., np.newaxis, :], axis=-1, keepdims=True) * second[..., np.newaxis, :]
        )
    return residuals, first**2 + second**2


def _flatness(sums: np.ndarray, leverage: np.ndarray, scatters: np.ndarray) -> np.ndarray:
    """``J`` of :func:`noise_law` over the last-but-one axis; infinite where it is not finite."""
    with np.errstate(divide='ignore', invalid='ignore'):
        logs = np.log(sums[..., scatters] / (1.0 - leverage[..., scatters]))
        values = np.sum((logs - logs.mean(axis=-1, keepdims=True)) ** 2, axis=-1)
    return np.where(np.isfinite(values), values, np.inf)
