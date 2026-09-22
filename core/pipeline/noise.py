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
non-negative, and it uses ``y²``, so a blank-subtracted point at or below zero
is harmless.

Only the SHAPE of the variance reaches the fit. The confidence interval's
threshold is a residual-variance F threshold, which profiles the noise level
out, so the level enters no inference; it is reported, as the floor ``a`` in au
and the proportional part ``b`` as a fraction of the signal. What the fit gets
is one vector of point weights, ``NoiseLaw.weights``, which
:class:`~core.pipeline.varpro.Projection` whitens its signal rows and design
with. A single titration cannot show how the noise varies with the signal, and
is fitted with weights of exactly one — the arithmetic of a fit without a noise
law, to the last bit.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import digamma

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
    """

    basis: NoiseBasis
    share: float = 0.0
    floor: float = 0.0
    proportional: float = 0.0
    reference: float = 0.0
    n_replicates: int = 1

    @property
    def estimated(self) -> bool:
        """Whether the replicates showed the law, rather than the noise being taken as constant."""
        return self.basis is NoiseBasis.REPLICATES

    def weights(self, mean_signal: np.ndarray) -> np.ndarray:
        """Weight of every titration point, ``1 / ((1 - share) + share·ybar²/reference²)``.

        The weights are the inverse of the law's variance, scaled to 1 at the
        rms signal, so a point the replicates show to be twice as precise
        counts four times. They are read off the measured means rather than the
        fitted curve, and are computed once, before the fit: there is no
        reweighting loop, and the conditional fit, the input-aware fit, every
        profile point and every sensitivity sample see the same weights.

        Where no law was read, and where the share came out exactly zero, this
        is ``np.ones`` — exactly, so that whitening by its square root multiplies
        by 1.0 and the fit is the unweighted fit to the last bit.

        Size: ``max(w)/min(w) <= (max|ybar| / min|ybar|)²``, reached only at
        ``share == 1``; below that every weight is under ``1 / (1 - share)``. A
        point whose mean is 1 % of the largest can therefore carry 1e4 times the
        weight of the top point, and that is the right weight when the noise
        really is proportional down to that point. It is not reached by
        accident, so no floor on the weights is needed: constant noise at such a
        point makes its whitened scatter at ``share = 1`` larger than the other
        points' by that same factor, which the estimator charges as a squared
        log and so leaves the share short of 1 — exactly where a floor would
        have acted.

        Parameters
        ----------
        mean_signal : np.ndarray
            The mean of the replicates at each titration point, in au — the
            signal the fit is run against.
        """
        mean = np.asarray(mean_signal, dtype=float)
        if not self.estimated or self.share == 0.0:
            return np.ones(mean.shape)
        return 1.0 / ((1.0 - self.share) + self.share * mean**2 / self.reference**2)

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
        return {**asdict(self), 'basis': self.basis.value}

    @classmethod
    def from_dict(cls, d: dict) -> 'NoiseLaw':
        """The law a results file holds."""
        return cls(**{**d, 'basis': NoiseBasis(d['basis'])})


def _two_digits(value: float) -> str:
    """*value* to two significant digits, written out in full rather than as a power of ten."""
    return np.format_float_positional(float(f'{value:.2g}'), trim='-')


def replicate_scatter(signals: np.ndarray, weights: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Scatter of every replicate about its own affine image of the mean curve.

    Each replicate is regressed on the columns ``[1, ybar]`` — one intercept
    and one scale in the mean signal, the affine freedom every registered model
    already has — with the points weighted by *weights*, and what is left is the
    noise. The columns are the same for all replicates, so one thin QR serves
    them all.

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
    root = np.sqrt(w)
    q, _ = np.linalg.qr(np.column_stack([np.ones(n), mean]) * root[:, np.newaxis])
    whitened = (y * root).T
    residuals = (whitened - q @ (q.T @ whitened)).T
    leverage = np.sum(q**2, axis=1)
    return residuals, leverage


def noise_law(signals: np.ndarray | None) -> NoiseLaw:
    """The noise law the replicates show, or why they cannot show one.

    With ``ybar`` the mean signal and ``u_i = ybar_i² / mean(ybar²)``, a
    candidate share ``lam`` states the relative variance
    ``g_i(lam) = (1 - lam) + lam·u_i``, which is 1 at the rms signal. Under the
    right share, the scatter of :func:`replicate_scatter` whitened by
    ``1 / sqrt(g)`` is flat along the titration, so the estimate is the share
    that makes it flattest:

    ``J(lam) = sum_i (log t_i - mean log t)²``, ``t_i = sum_r e_ri² / (1 - h_i)``

    over the points that scatter — those whose ``t_i`` stands above the
    rounding error of the projection that produced it, decided once with equal
    weights so that every share is judged on the same points. On a log scale
    because the spread of ``log t_i`` does not depend on the noise level, and
    because it is robust to one wild value of one replicate at one point, which
    real titrations have. A whole replicate that runs apart from the others is
    a different matter: it raises the scatter at every point it touches, and
    the law is read from whatever replicates it is handed, so removing such a
    replicate is the business of the outlier step before the fit. The detrending is
    weighted by the same share it is judged at, so there is one objective and no
    fixed-point iteration. ``J`` is infinite where a share would make a variance
    non-positive.

    The minimum is taken on ``linspace(0, 1, 101)`` and then refined by bounded
    Brent between the best node's neighbours, kept only if it is lower — the
    grid because ``J`` need not be unimodal with few replicates. A refinement
    that ends within its own tolerance of 0 or 1 is that end, so a share of
    zero is exactly zero. Nothing here draws a random number.

    The level ``c`` follows from the same scatter, as the mean of ``log t_i``
    corrected for the bias of a log chi-square on ``m - 1`` degrees of freedom;
    ``floor = sqrt(c(1 - lam))`` and ``proportional = sqrt(c·lam)/reference``.
    It is reported and never fitted against: the F threshold profiles the noise
    level out.

    No degrees of freedom are charged for the share. It comes from the scatter
    of the replicates about their own line, which under normal noise is
    independent of the mean the fit sees.

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
    relative = mean**2 / reference**2

    def whitened_scatter(share: float) -> tuple[np.ndarray, np.ndarray] | None:
        """``t_i`` at every point and the rounding error squared, or None where the share is not usable."""
        g = (1.0 - share) + share * relative
        if (g <= 0.0).any():
            return None
        residuals, leverage = replicate_scatter(y, 1.0 / g)
        with np.errstate(divide='ignore', invalid='ignore'):
            t = np.sum(residuals**2, axis=0) / (1.0 - leverage)
        return t, (np.finfo(float).eps * float(np.linalg.norm(y / np.sqrt(g)))) ** 2

    # The points that scatter are decided once, with equal weights, and every
    # candidate share is judged on those same points: J sums one term per
    # point, so a set that moved with the share would compare sums of different
    # lengths. Replicates that agree to the last bit leave the rounding error
    # of the projection, not zero: its residuals are accurate to about eps
    # times the norm of the data, so a scatter below that square says the point
    # did not scatter — the eps·norm rule a matrix rank is decided by. A point
    # the line reproduces exactly (leverage 1) leaves no scatter and no finite
    # ratio either; both judge nothing and are left out.
    unweighted, rounding = whitened_scatter(0.0)
    scatters = np.isfinite(unweighted) & (unweighted > rounding)
    if scatters.sum() < _MIN_SCATTER_POINTS:
        return too_few

    def objective(share: float) -> float:
        found = whitened_scatter(share)
        if found is None:
            return np.inf
        with np.errstate(divide='ignore'):
            logs = np.log(found[0][scatters])
        value = float(np.sum((logs - logs.mean()) ** 2))
        return value if np.isfinite(value) else np.inf

    nodes = np.linspace(0.0, 1.0, _SHARE_NODES)
    values = np.array([objective(node) for node in nodes])
    best = int(values.argmin())
    if not np.isfinite(values[best]):
        return too_few
    refined = minimize_scalar(
        objective,
        bounds=(nodes[max(best - 1, 0)], nodes[min(best + 1, _SHARE_NODES - 1)]),
        method='bounded',
        options={'xatol': _SHARE_XATOL},
    )
    share = float(refined.x) if refined.fun < values[best] else float(nodes[best])
    # Bounded Brent never evaluates an end of its bracket, so a minimum at 0 or
    # 1 comes back a tolerance short of it. Within that tolerance the share is
    # the end: exactly 0, where the weights are exactly one, or exactly 1.
    if share < _SHARE_XATOL:
        share = 0.0
    elif share > 1.0 - _SHARE_XATOL:
        share = 1.0

    dof = m - 1
    scatter = whitened_scatter(share)[0][scatters]
    level = float(np.exp(np.mean(np.log(scatter / dof)) - digamma(dof / 2) + np.log(dof / 2)))
    return NoiseLaw(
        NoiseBasis.REPLICATES,
        share=share,
        floor=float(np.sqrt(level * (1.0 - share))),
        proportional=float(np.sqrt(level * share) / reference),
        reference=reference,
        n_replicates=m,
    )
