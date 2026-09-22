"""Does the model describe the data, and do the entered inputs agree with it.

Pure functions on arrays, for a fit whose entered inputs may move within their
stated uncertainties (:mod:`core.pipeline.input_aware`).

Misfit tests, run at the fit with the inputs as entered and at the fit with the
inputs free to move:

- :func:`lack_of_fit` when two or more replicates were measured: the scatter of
  each replicate about its own affine image of the mean curve is a model-free
  estimate of the noise, and the F test compares the misfit of the averaged
  signal with it;
- :func:`runs_test` otherwise: a systematic deviation leaves long runs of
  residuals of one sign along the titration, fewer runs than the fitted model
  leaves of pure noise.

The conflict statistic measures how far the fit moved the inputs, in units of
their stated standard deviations, along the directions the data inform.
:func:`conflict_reference` finds those directions and :func:`conflict_p_value`
gives the distribution of the statistic when the entered inputs are consistent
with their stated uncertainties. It judges the inputs together: the data
usually inform one or two combinations of them (the host concentration and the
titrant scale move the curve almost alike), so the shift of a single input says
where the fit put the correction and not which stock is wrong.

:func:`verdict` reads the three results in a fixed order and names the cause of
a misfit: the model, the entered inputs, or neither.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Sequence

import numpy as np
from scipy.stats import f as f_dist

from core.pipeline.noise import replicate_scatter
from core.pipeline.varpro import _RANK_RTOL, LEVEL

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


class Verdict(Enum):
    """What the misfit tests and the conflict statistic say together. The values are the tokens in results files."""

    CONSISTENT = 'consistent'
    INPUTS_EXPLAIN = 'inputs_explain'
    INPUTS_CONFLICT = 'inputs_conflict'
    MODEL_INADEQUATE = 'model_inadequate'


def _finite_or_none(value: float) -> float | None:
    """*value* as a results file holds it: the number, or null where it is infinite.

    Infinity is what a ratio over a zero denominator comes to, and null is
    what JSON has for it; a results file is read by other programs too, and
    none of them accepts a float outside the format. The reader turns null
    back into the infinity it stands for.
    """
    return value if math.isfinite(value) else None


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
    """

    kind: str
    statistic: float
    p_value: float
    dof: tuple[int, int] | None = None
    expected: float | None = None

    def to_dict(self) -> dict:
        """Every field, as written to a results file.

        The F ratio is infinite where the replicates leave no scatter at
        all, and that is written as null (see :func:`_finite_or_none`); the
        p-value, the degrees of freedom and the expected number of runs are
        always finite.
        """
        return {
            **asdict(self),
            'statistic': _finite_or_none(self.statistic),
            'dof': None if self.dof is None else list(self.dof),
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'MisfitTest':
        """The test a results file holds."""
        return cls(
            **{
                **d,
                'statistic': math.inf if d['statistic'] is None else d['statistic'],
                'dof': None if d.get('dof') is None else tuple(d['dof']),
            }
        )


def lack_of_fit(
    signals: np.ndarray, fitted: np.ndarray, n_params: int, weights: np.ndarray | None = None
) -> MisfitTest:
    """Replicate lack-of-fit F test of a curve fitted to the mean of the replicates.

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
    the weights known).

    The ratio is exactly F under normal noise of the variance the weights
    state, for weights fixed beforehand. A fit passes the weights of the law
    read from these same replicates (:func:`~core.pipeline.noise.noise_law`),
    so numerator and denominator share one estimated share and the ratio is F
    only approximately: in the same linearised construction, under constant
    noise, proportional noise and a 3 % replicate scale factor, it rejects 4.7
    to 7.5 % of consistent fits at the 5 % level, the most at two replicates
    (3 000 draws per cell, m = 2, 4, 8). The rate through the whole fit is what
    the validation check ``noise-law-lof-null`` measures. The deviations of the replicates from their mean are independent of
    the mean, so numerator and denominator are independent; ``e`` is those
    deviations projected off the two columns ``[1, ybar]``, which leaves
    ``n - 2`` dimensions per replicate, less the one replicate the mean costs
    — the mean's own residual about the line is zero, so the ``e`` sum to zero
    across replicates. The weights enter both sums, so only their ratios
    matter: scaling them all by the same factor leaves the statistic where it
    was, and omitting them is the unweighted test.

    Inputs a fit determines from the data are not counted in *p*, so at such a
    fit the test is slightly lenient and never falsely alarming.

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

    Raises
    ------
    ValueError
        With fewer than two replicates, with fewer than three titration points
        (the scatter has no dimension left once the line is removed), or when
        ``n - p < 1``; and, from
        :func:`~core.pipeline.noise.replicate_scatter`, with weights of the
        wrong shape or a mean signal that does not vary.
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
    scatter, _ = replicate_scatter(y, weights)
    # Ones multiply exactly, so the numerator without weights is the plain sum
    # of the squared deviations and needs no branch of its own.
    w = np.ones(n) if weights is None else np.asarray(weights, dtype=float)
    misfit = m * float(np.sum(w * (y.mean(axis=0) - np.asarray(fitted, dtype=float)) ** 2)) / dof[0]
    # Replicates that agree to the last bit leave the rounding error of the
    # projection, not zero. Each of its m·n residuals is accurate to about eps
    # times the norm of the whitened data, so a scatter whose norm is below
    # m·n times that is no scatter at all, and the ratio over it is infinite:
    # the same verdict, and a statistic that is not a rounding artefact.
    # Replicates that are exact affine images of one another leave at most
    # 0.5 of that bound (20 000 random designs, 2 to 9 replicates of 3 to 39
    # points); measured scatter stands many decades above it.
    rounding = m * n * np.finfo(float).eps * float(np.linalg.norm(y * np.sqrt(w)))
    pure_error = float(np.sum(scatter**2)) / dof[1]
    if np.linalg.norm(scatter) > rounding:
        ratio = misfit / pure_error
    else:
        ratio = math.inf if misfit > 0 else 0.0
    return MisfitTest('lack_of_fit', ratio, float(f_dist.sf(ratio, *dof)), dof=dof)


def runs_test(
    residuals: np.ndarray, x: np.ndarray, jacobian: np.ndarray, draws: int = 100_000, seed: int = 0
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
    """
    order = np.argsort(np.asarray(x, dtype=float), kind='stable')
    r = np.asarray(residuals, dtype=float)[order]
    n = r.size
    j = np.array(jacobian, dtype=float)
    if j.ndim != 2 or j.shape[0] < n:
        raise ValueError(f'The Jacobian of {n} residuals needs {n} or more rows and one column per parameter.')
    j[:n] = j[:n][order]
    norms = np.linalg.norm(j, axis=0)
    u, s, _ = np.linalg.svd(j / np.where(norms > 0, norms, 1.0), full_matrices=False)
    u = u[:, s > _RANK_RTOL * s.max()] if s.size else u
    e = np.random.default_rng(seed).standard_normal((draws, j.shape[0]))
    null = _count_runs(np.sign((e - (e @ u) @ u.T)[:, :n]))
    runs = int(_count_runs(np.sign(r[r != 0])))
    p_value = float(np.mean(null < runs) + 0.5 * np.mean(null == runs))
    return MisfitTest('runs', float(runs), p_value, expected=float(null.mean()))


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
        ``P(q_null >= q)`` of :func:`conflict_p_value` for the weights below.
    weights : tuple[float, ...]
        Weight of every direction in the sum (:func:`conflict_reference`),
        ascending.
    """

    q: float
    k: int
    p_value: float
    weights: tuple[float, ...]

    def to_dict(self) -> dict:
        """Every field, as written to a results file.

        ``q`` is written through :func:`_finite_or_none`; the p-value is a
        proportion and every weight lies in ``[0, 1]``, so both are finite.
        """
        return {**asdict(self), 'q': _finite_or_none(self.q), 'weights': list(self.weights)}

    @classmethod
    def from_dict(cls, d: dict) -> 'Conflict':
        """The statistic a results file holds."""
        return cls(**{**d, 'q': math.inf if d['q'] is None else d['q'], 'weights': tuple(d['weights'])})


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

    Parameters
    ----------
    jacobian : np.ndarray
        Jacobian at the optimum of the residual rows in signal units, followed
        by one penalty row per input stated with a standard deviation. Columns:
        the *n_free_ka* binding constants, then every varying input the fit
        was free to move at the optimum. An input stated as a range that rests
        on an end of it is held there and has no column: left in, it would
        absorb what the data say about the other inputs.
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
    mask = np.asarray(sigma_mask, dtype=bool)
    k = int(mask.sum())
    j = np.array(jacobian, dtype=float)
    j[: j.shape[0] - k] /= scale
    columns = n_free_ka + np.flatnonzero(mask)
    covariance = np.linalg.pinv(j.T @ j)[np.ix_(columns, columns)]
    weights, directions = np.linalg.eigh(np.eye(k) - covariance)
    return np.clip(weights, 0.0, 1.0), directions


def conflict_test(
    z: Sequence[float], weights: np.ndarray, directions: np.ndarray, n_points: int, n_params: int
) -> Conflict | None:
    """The conflict statistic of the shifts *z* on the directions the data inform; ``None`` when there is none.

    A direction enters with a weight of ``_INFORMED_WEIGHT`` or more; of those,
    at most the ``n - p`` heaviest, since the residual has no more dimensions
    for the inputs to show in. ``q`` is the squared length of *z* along them,
    so a direction the data cannot see adds nothing to either side of the
    comparison.
    """
    dof = n_points - n_params
    informed = np.flatnonzero(np.asarray(weights) >= _INFORMED_WEIGHT)
    if dof < 1 or not informed.size:
        return None
    informed = informed[-dof:]
    w = np.asarray(weights, dtype=float)[informed]
    q = float(np.sum((np.asarray(directions, dtype=float)[:, informed].T @ np.asarray(z, dtype=float)) ** 2))
    return Conflict(q=q, k=int(w.size), p_value=conflict_p_value(q, w, n_points, n_params), weights=tuple(w.tolist()))


def conflict_p_value(
    q: float,
    weights: Sequence[float],
    n_points: int | None = None,
    n_params: int | None = None,
    draws: int = 200_000,
    seed: int = 0,
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

    Measured on random titrations with every input entered at its stated sigma
    (8 to 30 points, noise 0.5 to 3 %, Ka·c from 0.1 to 1000), among the fits
    that have a direction to test (44 to 57 % of the one-Ka fits, 38 and 61 %
    of the stepwise ones), the rejection rate at the 5 % level is 3.1 % (GDA),
    4.9 % (IDA), 5.6 and 3.2 % (DBA host-to-dye and dye-to-host; 6 468 fits)
    and 6.4 and 7.8 % (DBA_HG2, DBA_H2G; 1 080 fits); at the 1 % level 0.6 to
    1.5 % and 2.1 to 2.9 %. With inputs entered at three times their stated
    sigma it rejects 7 to 34 % of the fits (21 % for IDA with 12 points and
    0.5 % noise, 34 % with 30 points): the data inform one or two directions
    of the inputs, and only a conflict along those can show.

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
    """
    rng = np.random.default_rng(seed)
    w = np.clip(np.asarray(weights, dtype=float), 0.0, 1.0)
    e2 = rng.standard_normal((draws, w.size)) ** 2
    if n_points is None or n_params is None:
        return float(np.mean(e2 @ w >= q))
    left = n_points - n_params - w.size
    if left < 0:
        raise ValueError(f'{w.size} input directions cannot show in {n_points - n_params} residual degrees of freedom.')
    rest = rng.chisquare(left, draws) if left > 0 else np.zeros(draws)
    with np.errstate(divide='ignore', invalid='ignore'):
        c = np.maximum(n_points - e2 @ (w * (1.0 - w)), 0.0) / (rest + e2 @ (1.0 - w) ** 2)
        q_null = e2 @ w**2 + np.nan_to_num(c * (e2 @ (w * (1.0 - w))), nan=0.0)
    return float(np.mean(q_null >= q))


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
        ``None`` when no input is stated with a standard deviation.
    verdict : Verdict
    """

    conditional_misfit: MisfitTest | None
    misfit: MisfitTest | None
    conflict: Conflict | None
    verdict: Verdict

    def to_dict(self) -> dict:
        """Every field, as written to a results file."""
        return {
            'conditional_misfit': None if self.conditional_misfit is None else self.conditional_misfit.to_dict(),
            'misfit': None if self.misfit is None else self.misfit.to_dict(),
            'conflict': None if self.conflict is None else self.conflict.to_dict(),
            'verdict': self.verdict.value,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'FitDiagnostics':
        """The diagnostics a results file holds."""
        return cls(
            conditional_misfit=None
            if d['conditional_misfit'] is None
            else MisfitTest.from_dict(d['conditional_misfit']),
            misfit=None if d['misfit'] is None else MisfitTest.from_dict(d['misfit']),
            conflict=None if d['conflict'] is None else Conflict.from_dict(d['conflict']),
            verdict=Verdict(d['verdict']),
        )


def verdict(
    conditional_misfit: MisfitTest | None,
    misfit: MisfitTest | None,
    conflict: Conflict | None,
    level: float = DIAGNOSTIC_LEVEL,
) -> Verdict:
    """Name the cause of a misfit, the first of these that applies.

    1. ``MODEL_INADEQUATE``: the misfit test fails at the fit with the inputs
       free to move, so no allowed shift of the inputs rescues the model.
    2. ``INPUTS_CONFLICT``: the conflict statistic is significant — the data
       fit only with the inputs, taken together, further from their entered
       values than their stated uncertainties allow.
    3. ``INPUTS_EXPLAIN``: the misfit test fails with the inputs as entered and
       passes once they move.
    4. ``CONSISTENT`` otherwise. A test that could not be run fails nothing.
    """

    def fails(test: MisfitTest | Conflict | None) -> bool:
        return test is not None and test.p_value < level

    if fails(misfit):
        return Verdict.MODEL_INADEQUATE
    if fails(conflict):
        return Verdict.INPUTS_CONFLICT
    if fails(conditional_misfit):
        return Verdict.INPUTS_EXPLAIN
    return Verdict.CONSISTENT
