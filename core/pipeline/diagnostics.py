"""Does the model describe the data, and do the entered inputs agree with it.

Pure functions on arrays, for a fit whose entered inputs may move within their
stated uncertainties (:mod:`core.pipeline.input_aware`).

Misfit tests, run at the fit with the inputs as entered and at the fit with the
inputs free to move:

- :func:`lack_of_fit` when two or more replicates were measured: the scatter of
  each replicate about its own affine image of the mean curve is a model-free
  estimate of the noise, and the F ratio compares the misfit of the averaged
  signal with it, judged against the F distribution or, when the point weights
  come from a noise law read off the same replicates or a random error is
  stated for each titrant addition, against a parametric bootstrap of the
  whole reading that draws that error too (:class:`AdditionDraws`);
- :func:`runs_test` otherwise: a systematic deviation leaves long runs of
  residuals of one sign along the titration, fewer runs than the fitted model
  leaves of pure noise — noise that carries the stated addition errors where
  they are stated, beside a noise variance read off the part of the residual
  the fit leaves (:func:`addition_noise_covariance`).

The conflict statistic measures how far the fit moved the inputs, in units of
their stated standard deviations, along the directions the data inform.
:func:`conflict_reference` finds those directions and :func:`conflict_p_value`
gives the distribution of the statistic when the entered inputs are consistent
with their stated uncertainties. It judges the inputs together: the data
usually inform one or two combinations of them (the host concentration and the
titrant scale move the curve almost alike), so the shift of a single input says
where the fit put the correction and not which stock is wrong.

:func:`verdict` names what the tests found together — the model, the entered
inputs, both, or nothing — holding the chance of a false finding among the tests
it judges at the level of one test (Holm).

A test is not run where the data cannot carry it; :attr:`FitDiagnostics.skipped`
says which one and why, so that "nothing found" is never read as "tested and
passed".
"""

from __future__ import annotations

import zlib
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Sequence

import numpy as np
from scipy.stats import f as f_dist

from core.pipeline.inflation import paule_mandel, residual_space
from core.pipeline.noise import _SHARE_NODES, NoiseLaw, _read_share, _scatter, _scattering_points, replicate_scatter
from core.pipeline.varpro import _R2_RESOLUTION, _RANK_RTOL, LEVEL, _norms

#: Level of every test here: the 5 % convention of the confidence intervals
#: read from the other side, rounded because ``1 - 0.95`` is not 0.05 in floating point.
DIAGNOSTIC_LEVEL = round(1 - LEVEL, 12)

# Smallest weight of an input direction that enters the conflict statistic. A
# direction of weight w moves by sqrt(w) standard deviations when the entered
# inputs are consistent, so below 0.01 its whole range is under 0.1 — the last
# digit a shift is reported to — and what the fit shows along it is the
# curvature of the model and the stopping point of the solver, which the
# linearised reference does not describe: taken into the statistic, such
# directions reject 21 to 37 % of consistent fits (stoichiometric DBA, the
# stepwise models). The data say nothing about them, for or against the inputs.
_INFORMED_WEIGHT = 0.01

#: Draws of the parametric bootstrap that is the lack-of-fit test's reference
#: when the noise law was read off the replicates. The Monte-Carlo p-value
#: ``(1 + #{F* >= F}) / (B + 1)`` takes the values ``k / (B + 1)``, and a test
#: that rejects at ``p <= alpha`` — the rule :func:`verdict` applies — is exact
#: at ``alpha`` whenever ``(B + 1)·alpha`` is an integer and the reference is
#: right (Davison and Hinkley 1997, ch. 4). At 199 that holds at 5 % and at the
#: 2.5 % of the first step of Holm's procedure; the p-value moves in steps of
#: 0.005, and 0.005 is the smallest it can be.
LOF_BOOTSTRAP_DRAWS = 199

# Numbers the bootstrap's share search holds at a time: it reads every draw at
# all 101 shares of the grid at once, which takes memory in proportion to
# draws x shares x replicates x points (300 MB for 199 draws of 8 replicates
# at 100 points). In chunks of draws it stays near 8 MB per array; every draw
# is read on its own, so the chunking changes no number.
_LOF_CHUNK = 1 << 20

# Standard normal numbers the runs test's reference draws at a time: 8 MB of
# them, however many residuals and parameters the fit has, where one draw of the
# whole reference takes memory in proportion to the number of points (1.3 GB at
# 500 points). The generator yields the same stream in chunks as in one call, so
# the p-value does not depend on this number.
_RUNS_CHUNK = 1 << 20


class Verdict(Enum):
    """What the misfit tests and the conflict statistic say together. The values are the tokens in results files."""

    CONSISTENT = 'consistent'
    INPUTS_EXPLAIN = 'inputs_explain'
    INPUTS_CONFLICT = 'inputs_conflict'
    MODEL_INADEQUATE = 'model_inadequate'
    MODEL_AND_INPUTS = 'model_and_inputs'


@dataclass(frozen=True)
class MisfitTest:
    """One test of whether a fitted curve describes the data.

    Attributes
    ----------
    kind : str
        ``'lack_of_fit'`` or ``'runs'``.
    statistic : float
        The F ratio, or the number of runs.
    p_value : float
        Probability of a statistic at least this adverse when the model holds.
    dof : tuple[int, int] or None
        Degrees of freedom of the F ratio; ``None`` for the runs test.
    expected : float or None
        Expected number of runs; ``None`` for the F test.
    reference : str
        What the p-value is read from: for the F ratio ``'F'``, the F
        distribution on *dof*, or ``'bootstrap'``, the parametric bootstrap of
        :func:`lack_of_fit` for weights read off the same replicates; for the
        runs test ``'simulated'``, the runs the linearised fit leaves of
        simulated pure noise (:func:`runs_test`).
    """

    kind: str
    statistic: float
    p_value: float
    dof: tuple[int, int] | None = None
    expected: float | None = None
    reference: str = 'F'

    def to_dict(self) -> dict:
        """Every field, as written to a results file; every number is finite."""
        return {**asdict(self), 'dof': None if self.dof is None else list(self.dof)}

    @classmethod
    def from_dict(cls, d: dict) -> 'MisfitTest':
        """The test a results file holds; a file without ``reference`` holds each test's only reference then.

        That is the F distribution for the lack-of-fit test and the simulated
        runs for the runs test.
        """
        reference = d.get('reference', 'F' if d['kind'] == 'lack_of_fit' else 'simulated')
        return cls(**{**d, 'dof': None if d.get('dof') is None else tuple(d['dof']), 'reference': reference})


@dataclass(frozen=True)
class AdditionDraws:
    """The random error of each titrant addition, as the lack-of-fit test's reference draws it.

    Attributes
    ----------
    loading : np.ndarray
        ``H``, shape ``(n, n)``: the change of the fitted signal at point ``i``,
        in signal units and unwhitened, per unit relative error of addition
        ``j``. Additions into one cuvette move every later point, so ``H`` is
        lower triangular for sequential additions and diagonal for separate
        samples.
    sigma : float
        The relative standard deviation of one addition: ``0.01`` for 1 %.
    shared : bool
        Whether the replicates are repeated reads of one titration, so that
        every replicate carries the same addition errors; ``False`` when each
        replicate is a titration of its own with its own errors.
    """

    loading: np.ndarray
    sigma: float
    shared: bool


def no_scatter(variance: float, ss_tot: float, n_points: int) -> bool:
    """Whether a noise variance per titration point is below what a fit can resolve, so there is nothing to test against.

    The floor is ``_R2_RESOLUTION`` of the signal's own variance per point
    (*ss_tot*, its sum of squares about its mean, over *n_points*): the
    resolution the engine reads every residual at, below which a residual sum
    of squares is floored because it is arithmetic and not data (a scatter
    under 1e-5 of the signal's spread, finer than any instrument records). A
    floor at machine precision does not separate the two: a noise-free
    titration leaves a residual of 1e-12 to 1e-8 of its spread, set by how
    finely the search resolves Ka (``_LOG_KA_XTOL``) and not by rounding, and
    the runs test then rejects on the signs of the solver's stopping point.
    Replicates that agree to the last bit, or are exact affine images of one
    another, leave a scatter at rounding, many decades below the floor.
    """
    return variance <= _R2_RESOLUTION * ss_tot / n_points


def lack_of_fit(
    signals: np.ndarray,
    fitted: np.ndarray,
    n_params: int,
    weights: np.ndarray | None = None,
    *,
    law: NoiseLaw | None = None,
    design: np.ndarray | None = None,
    additions: AdditionDraws | None = None,
) -> MisfitTest | None:
    """Replicate lack-of-fit test of a curve fitted to the mean of the replicates; ``None`` without scatter.

    ``F = [m Σ_i w_i (ybar_i - fitted_i)² / (n - p)] / [Σ_ri e_ri² / ((m - 1)(n - 2))]``
    on ``(n - p, (m - 1)(n - 2))`` degrees of freedom, with ``ybar`` the mean of
    the replicates, ``w`` the point weights the fit was run with, and ``e`` the
    whitened scatter of each replicate about its OWN affine image of the mean
    curve (:func:`~core.pipeline.noise.replicate_scatter`).

    That scatter, and not the raw spread ``y_ri - ybar_i``, is the noise the
    curve is judged against. An affine image ``alpha + beta·signal`` of any
    registered forward model is a member of the same model — the offset and the
    signal coefficients absorb it — so a replicate run at a slightly different
    lamp intensity or background has not measured any less precisely, and the
    model follows it wherever it went. Taken for noise, that difference
    inflates the denominator until the test cannot fire: with a replicate scale
    factor of 3 %, the size of the ones the replicated datasets in ``data/``
    show, the raw pure error rejects 1.3 % (m = 2) to 0.1 % (m = 8) of
    consistent fits at the 5 % level, where the scatter used here rejects 4.7
    to 5.6 % (4 000 linearised draws per cell, 12 points, three parameters,
    the weights known). ``e`` is the deviations of the replicates from their
    mean projected off the two columns ``[1, ybar]``, which leaves ``n - 2``
    dimensions per replicate, less the one replicate the mean costs — the
    mean's own residual about the line is zero, so the ``e`` sum to zero across
    replicates. The weights enter both sums, so only their ratios matter:
    scaling them all by the same factor leaves the statistic where it was, and
    omitting them is the unweighted test.

    The reference the ratio is judged against depends on where the weights
    came from and on whether the titrant additions carry a stated random
    error:

    - weights fixed beforehand, or none (*law* ``None`` or not estimated), and
      no *additions*: the ratio is exactly F under normal noise of the
      variance the weights state, and the p-value is the F tail,
      ``reference = 'F'``;
    - otherwise the p-value is that of a parametric bootstrap of the whole
      reading, ``reference = 'bootstrap'``. With weights of a noise law read
      off these same replicates (:func:`~core.pipeline.noise.noise_law`),
      numerator and denominator share a share chosen to make the scatter
      flattest, and the F tail rejects consistent fits too often (up to 11 %
      at the 5 % level with two replicates). With a random error in each
      addition, the error moves the mean curve in a way no fitted parameter
      follows, and where the replicates are repeated reads of one titration it
      moves all of them alike and leaves their scatter untouched, so the F
      tail rejects most consistent fits (64 to 85 % at three replicates and
      3 % sequential additions). :data:`LOF_BOOTSTRAP_DRAWS` sets of replicates
      are drawn about *fitted*: with an estimated law at the variance it
      states at the fitted curve, ``level·relative_variance(fitted)``,
      otherwise at the constant whitened variance of the pure error,
      ``pure_error / w_i``; and with *additions*, every replicate shifted by
      ``H·delta``, ``delta`` normal with the stated relative standard
      deviation, one draw for all replicates when they share their additions
      and one per replicate otherwise. Where each replicate is a titration
      of its own, its addition errors move it apart from the others, so the
      scatter holds the additions beside the noise; the variance is then
      scaled to the part of the scatter the additions leave, its Paule-Mandel
      root on the scatter's own space (:func:`_noise_fraction`), since drawn
      at the whole scatter the additions would be counted twice. With an
      estimated law the share is read again in each draw by the same
      estimator on its grid, with ``u``, ``u_floor`` and the points that
      scatter held at the data's, and the weights follow from it; otherwise
      the weights are *weights*. The mean
      of the draw is refitted by weighted least squares, linearised at the
      fit, on the columns of *design*, and the ratio is formed by the same
      formula on the same degrees of freedom. The p-value is
      ``(1 + #{F* >= F}) / (B + 1)`` (Davison and Hinkley 1997, ch. 4). The
      random numbers are seeded from the signals, so the same data give the
      same p-value.

    *n_params* is what the fit fitted
    (:attr:`~core.pipeline.input_aware.AwareFit.n_params`): a parameter held on
    a bound takes no dimension from the residual.

    Replicates whose scatter is below the resolution of the fit
    (:func:`no_scatter`) — noise-free or identical replicates — carry no noise
    to judge the curve against, and the test is not run.

    Parameters
    ----------
    signals : np.ndarray
        The replicates, shape ``(m, n)`` with ``m >= 2``.
    fitted : np.ndarray
        The fitted signal at the ``n`` titration points, in signal units.
    n_params : int
        Parameter count ``p`` of the fit.
    weights : np.ndarray or None
        Weight of every titration point, from the noise law the replicates
        showed (:meth:`~core.pipeline.noise.NoiseLaw.weights`); equal weights
        when omitted.
    law : NoiseLaw or None
        The noise law *weights* come from, read off *signals*. Only an
        estimated law changes the reference.
    design : np.ndarray or None
        Required with an estimated law or *additions*: the derivatives of the
        fitted signal, in signal units and unwhitened, with respect to the
        *n_params* parameters the fit fitted, shape ``(n, k)``. Its column space has
        dimension *n_params*; ``k`` may exceed it where columns are tied, and
        the refit projects off the *n_params* leading singular directions of
        the whitened design with every column scaled to unit length.
    additions : AdditionDraws or None
        The stated random error of each titrant addition and how the
        replicates share it; ``None`` where none is stated.

    Raises
    ------
    ValueError
        With fewer than two replicates, with fewer than three titration points
        (the scatter has no dimension left once the line is removed), or when
        ``n - p < 1``; with an estimated law or *additions* and no *design*,
        or a design that is not one row per titration point with at least
        *n_params* columns; with an addition loading that is not ``(n, n)``;
        and, from :func:`~core.pipeline.noise.replicate_scatter`, with weights
        of the wrong shape or a mean signal that does not vary.
    """
    y = np.asarray(signals, dtype=float)
    if y.ndim != 2 or y.shape[0] < 2:
        raise ValueError(f'The lack-of-fit test needs two or more replicates; the signals have shape {y.shape}.')
    m, n = y.shape
    dof = (n - n_params, (m - 1) * (n - 2))
    if dof[0] < 1:
        raise ValueError(f'The lack-of-fit test needs more points ({n}) than fitted parameters ({n_params}).')
    if dof[1] < 1:
        raise ValueError(f'The lack-of-fit test needs three or more titration points; the signals have {n}.')
    estimated = law is not None and law.estimated
    if (estimated or additions is not None) and (
        design is None or np.ndim(design) != 2 or np.shape(design)[0] != n or np.shape(design)[1] < n_params
    ):
        raise ValueError(
            f'The simulated reference of the lack-of-fit test needs the design of the fit, one row per '
            f'titration point ({n}) and a column per fitted parameter ({n_params}); it got '
            f'{None if design is None else np.shape(design)}.'
        )
    if additions is not None and np.shape(additions.loading) != (n, n):
        raise ValueError(
            f'The addition loading needs one row per titration point and one column per addition ({n} x {n}); '
            f'it has shape {np.shape(additions.loading)}.'
        )
    scatter, _ = replicate_scatter(y, weights)
    # Ones multiply exactly, so the numerator without weights is the plain sum
    # of the squared deviations and needs no branch of its own.
    w = np.ones(n) if weights is None else np.asarray(weights, dtype=float)
    mean = y.mean(axis=0)
    pure_error = float(np.sum(scatter**2)) / dof[1]
    if no_scatter(pure_error, float(np.sum(w * (mean - np.average(mean, weights=w)) ** 2)), n):
        return None
    misfit = m * float(np.sum(w * (mean - np.asarray(fitted, dtype=float)) ** 2)) / dof[0]
    ratio = misfit / pure_error
    if not estimated and additions is None:
        return MisfitTest('lack_of_fit', ratio, float(f_dist.sf(ratio, *dof)), dof=dof)
    # Separate titrations scatter by their own addition errors as well, which
    # the reference draws on top of its noise.
    own = additions is not None and not additions.shared and additions.sigma > 0
    drawn = _bootstrap_ratios(
        y,
        np.asarray(fitted, dtype=float),
        w,
        pure_error,
        law if estimated else None,
        np.asarray(design, dtype=float),
        dof,
        additions,
        _noise_fraction(scatter, mean, w, additions, pure_error, dof[1]) if own else None,
    )
    p_value = (1 + int(np.sum(drawn >= ratio))) / (LOF_BOOTSTRAP_DRAWS + 1)
    return MisfitTest('lack_of_fit', ratio, p_value, dof=dof, reference='bootstrap')


def _bootstrap_ratios(
    signals: np.ndarray,
    fitted: np.ndarray,
    weights: np.ndarray,
    pure_error: float,
    law: NoiseLaw | None,
    design: np.ndarray,
    dof: tuple[int, int],
    additions: AdditionDraws | None,
    noise_fraction: float | None = None,
) -> np.ndarray:
    """The lack-of-fit ratio of :data:`LOF_BOOTSTRAP_DRAWS` replicate sets drawn about *fitted* (see :func:`lack_of_fit`).

    Every draw is read the way the data were. With an estimated *law*: the
    share by the noise law's estimator on its grid, at the data's ``u``,
    ``u_floor`` and points that scatter; the weights from that share; the pure
    error from the scatter at those weights. Without one: the pure error from
    the scatter at *weights*. Then the misfit of the mean after the weighted
    least-squares refit, linearised at the fit, on the leading
    ``n - dof[0]`` directions of the whitened design. The addition offsets
    are drawn after the noise, from the same stream, so a draw with an
    addition error of zero is the draw with none stated. *noise_fraction*,
    where given, scales the variance the noise is drawn at.
    """
    m, n = signals.shape
    n_params = n - dof[0]
    seed = np.random.SeedSequence(zlib.crc32(np.ascontiguousarray(signals, dtype=float).tobytes()))
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal((LOF_BOOTSTRAP_DRAWS, m, n))
    variance = pure_error / weights if law is None else law.level * law.relative_variance(fitted)
    if noise_fraction is not None:
        variance = noise_fraction * variance
    draws = fitted + np.sqrt(variance) * noise
    if additions is not None:
        delta = additions.sigma * rng.standard_normal((LOF_BOOTSTRAP_DRAWS, 1 if additions.shared else m, n))
        draws = draws + delta @ np.asarray(additions.loading, dtype=float).T
    if law is None:
        shares = np.zeros(LOF_BOOTSTRAP_DRAWS)
        residuals, _ = _scatter(draws, weights[np.newaxis])
        sums = np.sum(residuals[:, 0] ** 2, axis=-2)
    else:
        mean = signals.mean(axis=0)
        relative = np.maximum(mean**2 / law.reference**2, law.u_floor)
        scatters = _scattering_points(signals)
        chunk = max(1, _LOF_CHUNK // (_SHARE_NODES * m * n))
        shares, sums = np.empty(LOF_BOOTSTRAP_DRAWS), np.empty((LOF_BOOTSTRAP_DRAWS, n))
        for start in range(0, LOF_BOOTSTRAP_DRAWS, chunk):
            part = slice(start, start + chunk)
            shares[part], sums[part], _ = _read_share(draws[part], relative, scatters, refine=False)
    pure = np.sum(sums, axis=-1) / dof[1]
    misfit = np.empty(LOF_BOOTSTRAP_DRAWS)
    for share in np.unique(shares):
        drawn = shares == share
        root = np.sqrt(weights if law is None else 1.0 / ((1.0 - share) + share * relative))
        whitened = design * root[:, np.newaxis]
        norms = np.linalg.norm(whitened, axis=0)
        basis = np.linalg.svd(whitened / np.where(norms > 0.0, norms, 1.0), full_matrices=False)[0][:, :n_params]
        deviation = (draws[drawn].mean(axis=-2) - fitted) * root
        residual = deviation - (deviation @ basis) @ basis.T
        misfit[drawn] = m * np.sum(residual**2, axis=-1) / dof[0]
    return misfit / pure


def _noise_fraction(
    scatter: np.ndarray, mean: np.ndarray, weights: np.ndarray, additions: AdditionDraws, pure_error: float, dof: int
) -> float:
    """The part of the replicate scatter that is noise, where every replicate carries addition errors of its own.

    The scatter ``e_r`` of :func:`~core.pipeline.noise.replicate_scatter` lies
    in the complement of the whitened columns ``[1, ybar]``; on an orthonormal
    basis ``Q`` of it, the deviations of the replicates from their mean carry
    the noise and their own addition offsets, of covariance ``σ² I + Q'G Q``
    with ``G = s² W^½ H H' W^½``, and ``sum_r (Q'e_r)' (σ² I + Q'G Q)⁻¹ (Q'e_r)``
    is chi-squared on the ``(m - 1)(n - 2)`` degrees of freedom of the scatter
    (the deviations from the mean are ``m - 1`` independent contrasts). Its
    root ``σ²`` (:func:`~core.pipeline.inflation.paule_mandel`), between
    ``1e-12`` and 1 of the pure error, over the pure error is the fraction.
    """
    root = np.sqrt(weights)
    columns = root[:, np.newaxis] * np.column_stack([np.ones(mean.size), mean])
    loading = root[:, np.newaxis] * np.asarray(additions.loading, dtype=float)
    added = additions.sigma**2 * (loading @ loading.T)
    beside, _ = paule_mandel([(scatter, residual_space(columns, 2), added)], dof, pure_error)
    return beside / pure_error


def runs_test(
    residuals: np.ndarray,
    x: np.ndarray,
    jacobian: np.ndarray,
    draws: int = 100_000,
    seed: int = 0,
    *,
    covariance: np.ndarray | None = None,
) -> MisfitTest:
    """Runs test on the signs of the residuals along the titration, against the fitted model's own reference.

    The residuals are ordered by *x* and residuals of exactly zero are left
    out. A systematic deviation makes long runs of one sign, so few runs speak
    against the model. Residuals of a fitted curve are not exchangeable: the
    fit removes what its parameters can follow, which makes the signs
    alternate more often than independent ones, and the distribution of the
    number of runs over all orderings of the signs then almost never rejects
    (0.0 to 1.5 % of consistent fits at the 5 % level for 8 to 30 points,
    against 2.3 to 5.6 % with this reference; 4 800 random one-Ka titrations).
    The reference here is the number of runs of ``(I - J J⁺) e`` for standard
    normal ``e``: the residuals the linearised fit leaves of pure noise.

    Noise that is correlated along the titration makes long runs of its own.
    A random error in each titrant addition is such noise: the error of one
    addition moves every later point of the same cuvette, and with 3 %
    sequential additions the reference of independent noise rejects 13 to
    29 % of consistent fits at the 5 % level. *covariance* states that noise
    (:func:`addition_noise_covariance`), and ``e`` is then drawn from
    ``N(0, covariance)`` on the residual rows, the penalty rows staying
    standard normal and independent of them.

    The p-value is the mid-p, ``P(fewer runs) + P(as many) / 2``: the number
    of runs takes few values, and with all of ``P(as many)`` counted a test
    at the 5 % level rejects 0.7 % at 8 points.

    Parameters
    ----------
    residuals, x : np.ndarray
        Residuals of the fit and the titrant concentrations, ``n`` each.
    jacobian : np.ndarray
        Derivatives of the ``n`` residuals with respect to every parameter the
        fit was free to move, signal parameters included. When the fit also
        holds inputs by their stated standard deviation, the residual rows
        are in units of the noise scale and one penalty row per such input
        follows them (:func:`core.pipeline.input_aware.fit_jacobian`).
    draws, seed : int
        Size and seed of the quadrature; the fixed seed makes the p-value a
        function of the other arguments, with a Monte Carlo error of 7e-4 at
        ``p = 0.05`` for 100 000 draws.
    covariance : np.ndarray or None
        Covariance of the noise in the ``n`` residuals, shape ``(n, n)`` in the
        order of *residuals*, in the units of the residual rows of *jacobian*
        (only its shape matters where *jacobian* has no penalty rows, since
        only signs are counted); ``None`` for independent noise of equal
        variance.

    Raises
    ------
    ValueError
        With a Jacobian of fewer rows than residuals, or a covariance that is
        not a finite symmetric ``(n, n)`` matrix.
    """
    order = np.argsort(np.asarray(x, dtype=float), kind='stable')
    r = np.asarray(residuals, dtype=float)[order]
    n = r.size
    j = np.array(jacobian, dtype=float)
    if j.ndim != 2 or j.shape[0] < n:
        raise ValueError(f'The Jacobian of {n} residuals needs {n} or more rows and one column per parameter.')
    root = None if covariance is None else _covariance_root(covariance, order)
    j[:n] = j[:n][order]
    norms = np.linalg.norm(j, axis=0)
    u, s, _ = np.linalg.svd(j / np.where(norms > 0, norms, 1.0), full_matrices=False)
    u = u[:, s > _RANK_RTOL * s.max()] if s.size else u
    runs = int(_count_runs(np.sign(r[r != 0])))
    rng = np.random.default_rng(seed)
    chunk = max(1, _RUNS_CHUNK // j.shape[0])
    fewer = same = total = 0
    for start in range(0, draws, chunk):
        e = rng.standard_normal((min(chunk, draws - start), j.shape[0]))
        if root is not None:
            e[:, :n] = e[:, :n] @ root.T
        null = _count_runs(np.sign((e - (e @ u) @ u.T)[:, :n]))
        fewer += int(np.sum(null < runs))
        same += int(np.sum(null == runs))
        total += int(np.sum(null))
    return MisfitTest(
        'runs', float(runs), fewer / draws + 0.5 * (same / draws), expected=total / draws, reference='simulated'
    )


def addition_noise_covariance(
    residual: np.ndarray, design: np.ndarray, n_params: int, loading: np.ndarray, sigma: float
) -> np.ndarray:
    """Covariance ``σ² I + s² H H'`` of the noise in the residual of one titration whose additions carry a random error.

    *loading* ``H`` is the change of the signal at every point per unit
    relative error of every addition and *sigma* ``s`` the relative standard
    deviation of one addition; ``G = s² H H'`` is what the additions add.
    ``σ²`` is the noise beside them, the Paule-Mandel root on the residual
    space (:func:`~core.pipeline.inflation.paule_mandel`, the one estimate the
    interval's design effect and Cochran's test read as well): with ``Q`` an
    orthonormal basis of the complement of the *n_params* leading directions
    of *design*, every column scaled to unit length, the root of

        (Q'r)' (σ² I + Q'G Q)⁻¹ (Q'r) = n - p,

    between ``1e-12 σ̂²`` and ``σ̂² = r'r / (n - p)``. A root read on the whole
    residual would count the part of the additions' effect the fit leaves as
    noise, and the runs reference drawn with it would be close to independent
    noise and reject 8 to 11 % of consistent fits at the 5 % level (3 %
    additions, noise 0.2 % of the signal range, 12 points).

    Parameters
    ----------
    residual : np.ndarray
        The residual of the fit, ``n`` values.
    design : np.ndarray
        The derivatives of the fitted signal with respect to the parameters
        the fit fitted, shape ``(n, k)`` with ``k >= n_params``, in the units
        of *residual*.
    n_params : int
        The parameter count ``p`` of the fit, the rank of *design*.
    loading : np.ndarray
        ``H``, shape ``(n, n)``, in the units of *residual*.
    sigma : float
        ``s``: ``0.01`` for 1 %.

    Raises
    ------
    ValueError
        With a design or a loading that is not one row per point, or no
        residual degree of freedom.
    """
    r = np.asarray(residual, dtype=float)
    n = r.size
    columns, h = np.asarray(design, dtype=float), np.asarray(loading, dtype=float)
    if columns.ndim != 2 or columns.shape[0] != n or columns.shape[1] < n_params or h.shape != (n, n):
        raise ValueError(
            f'The noise beside the additions needs a design of {n} rows and {n_params} or more columns and an '
            f'addition loading of {n} x {n}; they have shapes {columns.shape} and {h.shape}.'
        )
    dof = n - n_params
    if dof < 1:
        raise ValueError(f'The noise beside the additions needs more points ({n}) than fitted parameters ({n_params}).')
    added = sigma**2 * (h @ h.T)
    norms = np.linalg.norm(columns, axis=0)
    rest = residual_space(columns / np.where(norms > 0.0, norms, 1.0), n_params)
    beside, _ = paule_mandel([(r, rest, added)], dof, float(r @ r) / dof)
    return beside * np.eye(n) + added


def _covariance_root(covariance: np.ndarray, order: np.ndarray) -> np.ndarray:
    """A square root ``L`` of *covariance* reordered by *order*, ``L L' = C``, from its eigendecomposition.

    The eigendecomposition and not a Cholesky factor, because a covariance of
    additions that dominate the noise is close to singular; eigenvalues below
    zero by rounding are read as zero.
    """
    n = order.size
    c = np.asarray(covariance, dtype=float)
    if c.shape != (n, n) or not np.all(np.isfinite(c)) or not np.allclose(c, c.T):
        raise ValueError(f'The covariance of {n} residuals must be a finite symmetric {n} x {n} matrix.')
    values, vectors = np.linalg.eigh(c[np.ix_(order, order)])
    return vectors * np.sqrt(np.clip(values, 0.0, None))


def _count_runs(signs: np.ndarray) -> np.ndarray:
    """Number of runs of equal sign along the last axis."""
    return 1 + np.sum(signs[..., 1:] != signs[..., :-1], axis=-1)


@dataclass(frozen=True)
class InputShift:
    """Where the fit put one varying input.

    Attributes
    ----------
    key : str
        Input key.
    fraction : float
        Fitted offset from the entered value, as a fraction of it.
    z : float or None
        The offset in units of the stated standard deviation; ``None`` for an
        input stated as a range.
    at_edge : bool
        Whether an input stated as a range rests on an end of it.
    """

    key: str
    fraction: float
    z: float | None
    at_edge: bool

    def to_dict(self) -> dict:
        """Every field, as written to a results file."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'InputShift':
        """The shift a results file holds."""
        return cls(**d)


@dataclass(frozen=True)
class Conflict:
    """The conflict statistic of the inputs stated with a standard deviation.

    Attributes
    ----------
    q : float
        Sum of the squared shifts along the input directions the data inform,
        each in units of its standard deviation.
    k : int
        Number of those directions.
    p_value : float
        ``P(q_null >= q)`` of :func:`conflict_p_value` for the weights below
        and, where a random error of each addition is stated, the covariance
        it adds to the shifts (:func:`conflict_added`).
    weights : tuple[float, ...]
        Weight of every direction in the sum (:func:`conflict_reference`),
        ascending.
    """

    q: float
    k: int
    p_value: float
    weights: tuple[float, ...]

    def to_dict(self) -> dict:
        """Every field, as written to a results file; every number is finite."""
        return {**asdict(self), 'weights': list(self.weights)}

    @classmethod
    def from_dict(cls, d: dict) -> 'Conflict':
        """The statistic a results file holds."""
        return cls(**{**d, 'weights': tuple(d['weights'])})


def conflict_reference(
    jacobian: np.ndarray, n_free_ka: int, sigma_mask: Sequence[bool], scale: float
) -> tuple[np.ndarray, np.ndarray]:
    """Input directions and the weight ``w_i`` the data give each of them.

    When the entered inputs are consistent with their stated uncertainties, the
    linearised fit gives the standardised shifts ``z ~ N(0, V)`` with
    ``V = I - [H⁻¹]_zz``, ``H = J'J`` the Gauss-Newton Hessian of the stacked
    residual ``[r / scale ; z]`` over the free binding constants and the varying
    inputs. The eigenvalues of ``V`` are ``g / (1 + g)`` for the information
    ``g`` the data hold about each input direction: 1 where the data determine
    an input, 0 along a direction the data cannot see, such as a common scale
    of every concentration. Their sum is the number of residual degrees of
    freedom the inputs take up, the effective degrees of freedom of a
    penalised fit.

    ``[H⁻¹]_zz`` is read off the singular value decomposition of the stacked
    Jacobian with every column scaled to unit length, ``J D⁻¹ = U S Vᵀ``, as
    ``D_z⁻¹ V_z S⁻² V_zᵀ D_z⁻¹``: the column scaling makes the result
    independent of the units a parameter is measured in — a binding constant
    in decades or in nepers, whatever its derivative's size — and the
    decomposition of J itself, rather than an inverse of ``J'J``, keeps the
    condition number unsquared. A direction of the scaled J below
    ``_RANK_RTOL`` of the largest is taken as one the columns do not
    separate, the reading of a rank used throughout the engine.

    Parameters
    ----------
    jacobian : np.ndarray
        Jacobian at the optimum of the residual rows in signal units, followed
        by one penalty row per input stated with a standard deviation. Columns:
        the *n_free_ka* binding constants the fit left inside their box, then
        every varying input the fit was free to move at the optimum. A
        binding constant on a bound of its box, and an input stated as a range
        that rests on an end of it, is held there and has no column: left in,
        it would absorb what the data say about the other inputs.
    n_free_ka : int
        Number of leading binding-constant columns.
    sigma_mask : Sequence[bool]
        Per input column, whether it is stated with a standard deviation (and
        so has a penalty row and a shift in standard deviations).
    scale : float
        Noise scale the residual rows are divided by: ``sqrt(S_min / n)``.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        The eigenvalues of ``V`` on the inputs stated with a standard
        deviation, ascending and clipped to ``[0, 1]``, and the matching
        eigenvectors as columns.
    """
    root, _ = _shift_operator(jacobian, n_free_ka, sigma_mask, scale)
    weights, directions = np.linalg.eigh(np.eye(root.shape[0]) - root @ root.T)
    return np.clip(weights, 0.0, 1.0), directions


def conflict_added(
    jacobian: np.ndarray, n_free_ka: int, sigma_mask: Sequence[bool], scale: float, added: np.ndarray
) -> np.ndarray:
    """Covariance a random error of each addition adds to the standardised shifts ``z`` of a consistent fit.

    The linearised fit turns the stacked residual into the shifts by
    ``z = A [r / scale ; 0]`` with ``A`` the rows of ``H⁻¹ J'`` that belong to
    the inputs stated with a standard deviation (the notation of
    :func:`conflict_reference`, whose ``[H⁻¹]_zz`` is ``A A'`` over every row).
    Noise of covariance ``G`` on the residual rows beyond the noise the fit
    reads from its own residual therefore adds ``A_r G A_r' / scale²`` to the
    covariance of ``z``, ``A_r`` the columns of ``A`` on the residual rows.
    The additions move the curve much as an input does — a scale error of the
    titrant above all — so most of what they add lies along the very
    directions the data inform, where the inputs would otherwise be blamed for
    it.

    Parameters
    ----------
    jacobian, n_free_ka, sigma_mask, scale
        As in :func:`conflict_reference`.
    added : np.ndarray
        Covariance ``G`` of the residual rows in signal units, shape
        ``(n, n)`` for the ``n`` residual rows of *jacobian*.

    Returns
    -------
    np.ndarray
        Shape ``(k, k)`` over the inputs stated with a standard deviation, in
        the order of their columns.
    """
    root, left = _shift_operator(jacobian, n_free_ka, sigma_mask, scale)
    shifts = root @ left.T
    return shifts @ (np.asarray(added, dtype=float) / scale**2) @ shifts.T


def _shift_operator(
    jacobian: np.ndarray, n_free_ka: int, sigma_mask: Sequence[bool], scale: float
) -> tuple[np.ndarray, np.ndarray]:
    """``D_z⁻¹ V_z S⁻¹`` and the residual rows of ``U`` of the column-scaled stacked Jacobian ``J D⁻¹ = U S Vᵀ``.

    Their product is ``A_r``, the map of :func:`conflict_added`, and the first
    times its transpose is ``[H⁻¹]_zz`` of :func:`conflict_reference`. Only the
    singular directions above ``_RANK_RTOL`` of the largest are kept.
    """
    mask = np.asarray(sigma_mask, dtype=bool)
    k = int(mask.sum())
    j = np.array(jacobian, dtype=float)
    residual_rows = j.shape[0] - k
    j[:residual_rows] /= scale
    norms = _norms(j)
    u, s, vt = np.linalg.svd(j / norms, full_matrices=False)
    kept = s > _RANK_RTOL * s.max()
    columns = n_free_ka + np.flatnonzero(mask)
    return vt[kept][:, columns].T / s[kept] / norms[columns, np.newaxis], u[:residual_rows, kept]


def conflict_test(
    z: Sequence[float],
    weights: np.ndarray,
    directions: np.ndarray,
    n_points: int,
    n_params: int,
    added: np.ndarray | None = None,
) -> Conflict | None:
    """The conflict statistic of the shifts *z* on the directions the data inform; ``None`` when there is none.

    A direction enters with a weight of ``_INFORMED_WEIGHT`` or more; of those,
    at most the ``n - p`` heaviest, since the residual has no more dimensions
    for the inputs to show in. ``q`` is the squared length of *z* along them,
    so a direction the data cannot see adds nothing to either side of the
    comparison. *added* is :func:`conflict_added` where a random error of each
    addition is stated: the statistic stays the same and its reference carries
    that covariance along the directions it reads.
    """
    dof = n_points - n_params
    informed = np.flatnonzero(np.asarray(weights) >= _INFORMED_WEIGHT)
    if dof < 1 or not informed.size:
        return None
    informed = informed[-dof:]
    w = np.asarray(weights, dtype=float)[informed]
    along = np.asarray(directions, dtype=float)[:, informed]
    q = float(np.sum((along.T @ np.asarray(z, dtype=float)) ** 2))
    extra = None if added is None else along.T @ np.asarray(added, dtype=float) @ along
    return Conflict(
        q=q, k=int(w.size), p_value=conflict_p_value(q, w, n_points, n_params, added=extra), weights=tuple(w.tolist())
    )


def conflict_p_value(
    q: float,
    weights: Sequence[float],
    n_points: int | None = None,
    n_params: int | None = None,
    draws: int = 200_000,
    seed: int = 0,
    added: np.ndarray | None = None,
) -> float:
    """``P(q_null >= q)`` for a fit consistent with its stated input uncertainties, from *draws* draws.

    With the noise scale known, ``q_null = sum_i w_i e_i²`` with standard
    normal ``e_i``. A fit estimates the scale from its own residual,
    ``s² = S / n``, and that matters most where the data say little about an
    input. In the linearised model, along eigen-direction i the fit sees the
    information ``g_i = w_i / (1 - w_i)`` at its own scale, the data hold
    ``u_i = sqrt(1 + g_i / c) e_i`` with ``c = sigma² / s²``, and

        z_i = sqrt(g_i c) u_i / (1 + g_i),    S / sigma² = R + sum_i u_i² / (1 + g_i)²,

    ``R ~ chi²`` on the ``n - p`` residual degrees of freedom less one per
    input direction. Solving ``c = n sigma² / S`` for c gives, per draw,

        c = (n - sum_i w_i (1 - w_i) e_i²) / (R + sum_i (1 - w_i)² e_i²)
        q_null = sum_i [w_i² + c w_i (1 - w_i)] e_i²

    which is ``sum_i w_i e_i²`` at ``c = 1``, ``sum_i e_i²`` where the data
    determine every input (``w_i -> 1``), and ``n`` times a weighted beta
    variable where they determine none (``w_i -> 0``) — bounded, with a
    longer tail than ``w_i chi²_1`` at few points.

    Where a random error of each addition is stated, the shifts carry it too:
    each draw adds ``a ~ N(0, added)`` to the shifts ``z_i = sqrt(w_i² + c w_i
    (1 - w_i)) e_i`` along the directions, and ``q_null = |z + a|²``. *added*
    is linearised at the fit's own noise scale (:func:`conflict_added`), as
    the weights are.

    The rate at which a fit whose inputs were entered within their stated
    uncertainties is rejected, and how often an entry error is detected, are
    what the validation checks ``conflict-null``, ``noise-law-conflict-null``,
    ``addition-verdict-null`` and ``conflict-power`` measure. The data inform
    one or two directions of the inputs, and only a conflict along those can
    show.

    Parameters
    ----------
    q : float
        The conflict statistic.
    weights : Sequence[float]
        Weight of every direction in *q*; no more of them than ``n - p``.
    n_points, n_params : int, optional
        Titration points and parameter count ``p`` of the fit. When omitted the
        scale is taken as known, the limit of many points.
    draws, seed : int
        Size and seed of the quadrature. The fixed seed makes it deterministic:
        the same arguments give the same p-value, with a Monte Carlo error of
        5e-4 at ``p = 0.05`` for 200 000 draws.
    added : np.ndarray, optional
        Covariance the stated addition errors add to the shifts along the
        directions of *weights*, shape ``(k, k)`` in their order. ``None``
        where no addition error is stated, and the p-value is then the one of
        the shifts alone, draw for draw.
    """
    rng = np.random.default_rng(seed)
    w = np.clip(np.asarray(weights, dtype=float), 0.0, 1.0)
    e = rng.standard_normal((draws, w.size))
    e2 = e**2
    if n_points is None or n_params is None:
        if added is None:
            return float(np.mean(e2 @ w >= q))
        return float(np.mean(np.sum((np.sqrt(w) * e + _draw_added(rng, added, draws)) ** 2, axis=1) >= q))
    left = n_points - n_params - w.size
    if left < 0:
        raise ValueError(f'{w.size} input directions cannot show in {n_points - n_params} residual degrees of freedom.')
    rest = rng.chisquare(left, draws) if left > 0 else np.zeros(draws)
    with np.errstate(divide='ignore', invalid='ignore'):
        c = np.maximum(n_points - e2 @ (w * (1.0 - w)), 0.0) / (rest + e2 @ (1.0 - w) ** 2)
        if added is None:
            q_null = e2 @ w**2 + np.nan_to_num(c * (e2 @ (w * (1.0 - w))), nan=0.0)
        else:
            gain = w**2 + np.nan_to_num(c[:, np.newaxis] * (w * (1.0 - w)), nan=0.0)
            q_null = np.sum((np.sqrt(gain) * e + _draw_added(rng, added, draws)) ** 2, axis=1)
    return float(np.mean(q_null >= q))


def _draw_added(rng: np.random.Generator, added: np.ndarray, draws: int) -> np.ndarray:
    """*draws* normal vectors of covariance *added*, through its eigenvalues clipped at zero."""
    values, vectors = np.linalg.eigh(np.asarray(added, dtype=float))
    root = vectors * np.sqrt(np.maximum(values, 0.0))
    return rng.standard_normal((draws, root.shape[0])) @ root.T


#: Why a test was not run: the tokens :attr:`FitDiagnostics.skipped` holds, as
#: written to a results file.
#:
#: - ``no_scatter``: the replicates, or the residual of a single signal, carry
#:   no scatter above the resolution of the fit (:func:`no_scatter`);
#: - ``too_few_dof``: the residual has too few degrees of freedom for the test;
#: - ``no_uncertainty``: no input is stated with a standard deviation (conflict);
#: - ``no_informed_direction``: the data inform no direction of the inputs
#:   stated with one (conflict).
SKIP_REASONS = ('no_scatter', 'too_few_dof', 'no_uncertainty', 'no_informed_direction')


@dataclass(frozen=True)
class FitDiagnostics:
    """The tests of one fit and what they say together.

    Attributes
    ----------
    conditional_misfit : MisfitTest or None
        Misfit test at the fit with the inputs as entered; ``None`` when the
        data allow no test.
    misfit : MisfitTest or None
        Misfit test at the fit with the inputs free to move; equal to
        *conditional_misfit* when no input varies.
    conflict : Conflict or None
        ``None`` when the conflict statistic could not be formed.
    verdict : Verdict
    skipped : dict[str, str]
        Every test of the verdict that was not run, ``'misfit'`` or
        ``'conflict'``, with the reason, one of :data:`SKIP_REASONS`.
    """

    conditional_misfit: MisfitTest | None
    misfit: MisfitTest | None
    conflict: Conflict | None
    verdict: Verdict
    skipped: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Every field, as written to a results file; ``skipped`` only where a test was not run.

        ``skipped`` is written only when a test was not run, and a record
        without it reads as nothing skipped, so importing and exporting a
        record leaves it as it was.
        """
        return {
            'conditional_misfit': None if self.conditional_misfit is None else self.conditional_misfit.to_dict(),
            'misfit': None if self.misfit is None else self.misfit.to_dict(),
            'conflict': None if self.conflict is None else self.conflict.to_dict(),
            'verdict': self.verdict.value,
            **({'skipped': dict(self.skipped)} if self.skipped else {}),
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'FitDiagnostics':
        """The diagnostics a results file holds; a file without ``skipped`` names no skipped test.

        A misfit record whose statistic is null holds the F ratio of replicates
        that agree exactly, over a pure error of zero: data with no scatter to
        test the curve against. It is read as that test not run for
        ``'no_scatter'``, and the verdict is judged again from the tests that
        remain, since the one the file states rests on that ratio.
        """
        records = {key: d[key] for key in ('conditional_misfit', 'misfit')}
        no_scatter = any(r is not None and r.get('statistic') is None for r in records.values())
        tests = {
            key: None if r is None or r.get('statistic') is None else MisfitTest.from_dict(r)
            for key, r in records.items()
        }
        conflict = None if d['conflict'] is None else Conflict.from_dict(d['conflict'])
        skipped = dict(d.get('skipped') or {})
        if no_scatter:
            skipped.setdefault('misfit', 'no_scatter')
            judged = verdict(tests['conditional_misfit'], tests['misfit'], conflict)
        else:
            judged = Verdict(d['verdict'])
        return cls(**tests, conflict=conflict, verdict=judged, skipped=skipped)


def verdict(
    conditional_misfit: MisfitTest | None,
    misfit: MisfitTest | None,
    conflict: Conflict | None,
    level: float = DIAGNOSTIC_LEVEL,
) -> Verdict:
    """What the tests found together.

    The misfit test at the fit with the inputs free to move and the conflict
    statistic are judged together by Holm's step-down procedure at *level*,
    over those of the two that ran: the smaller p-value against ``level / 2``
    and, if it rejects, the other against *level* (one test alone is judged
    against *level*). A test rejects when its p-value is at or below its
    threshold, the rule under which the Monte-Carlo p-value of the bootstrap
    (:data:`LOF_BOOTSTRAP_DRAWS`) holds both thresholds exactly. Where each
    test holds its own level, the chance that either names a cause although
    the model holds and the inputs are as stated is then at most *level*,
    where two tests at *level* each reach up to twice that; the validation
    check ``verdict-false-alarm`` measures the rate the verdict reaches. The
    p-values stored on the tests stay the raw ones.

    1. ``MODEL_AND_INPUTS``: both reject. The data fit only with the inputs
       further from their entered values than stated, and even then the model
       misses them. An input error can itself produce the misfit, so the
       inputs are the first thing to check.
    2. ``INPUTS_CONFLICT``: the conflict statistic rejects — the data fit only
       with the inputs, taken together, further from their entered values than
       their stated uncertainties allow.
    3. ``MODEL_INADEQUATE``: the misfit test rejects at the fit with the inputs
       free to move, so no allowed shift of the inputs rescues the model.
    4. ``INPUTS_EXPLAIN``: neither rejects, and the misfit test at the inputs
       as entered fails at the threshold the misfit test faced in the
       procedure — the data fit once the inputs move within what was stated
       for them. It is the same test at other inputs, so it is judged as
       strictly: a miss the shifted inputs left as it was is no miss they
       explain.
    5. ``CONSISTENT`` otherwise: no test that ran found evidence against the
       model or the inputs. A test that could not be run finds nothing.
    """
    tests = {'misfit': misfit, 'conflict': conflict}
    ran = sorted((test.p_value, name) for name, test in tests.items() if test is not None)
    threshold = {name: level / (len(ran) - i) for i, (_, name) in enumerate(ran)}
    rejected = set()
    for p_value, name in ran:
        if p_value > threshold[name]:
            break
        rejected.add(name)
    if rejected == {'misfit', 'conflict'}:
        return Verdict.MODEL_AND_INPUTS
    if 'conflict' in rejected:
        return Verdict.INPUTS_CONFLICT
    if 'misfit' in rejected:
        return Verdict.MODEL_INADEQUATE
    if conditional_misfit is not None and conditional_misfit.p_value <= threshold.get('misfit', level):
        return Verdict.INPUTS_EXPLAIN
    return Verdict.CONSISTENT
