"""The rule that turns a count into a pass, a fail or an undecided, and what that rule can decide.

Every verdict in the package's tables comes from here. The criterion is
Bradley's liberal criterion of robustness (J. V. Bradley, *Robustness?*, Br. J.
Math. Stat. Psychol. **31**, 144-152, 1978): a procedure with nominal error
rate alpha is acceptable when its true error rate lies in
``[0.5 alpha, 1.5 alpha]``. For a 95 % confidence interval that is coverage in
``[0.925, 0.975]``; for a test run at the 5 % level, a rejection rate on the
null in ``[0.025, 0.075]``.

A confidence interval and a test both err on the safe side when they are
conservative, so only the anti-conservative side can fail. Reading the exact
95 % Clopper-Pearson limits of the observed rate against the two thresholds
gives four verdicts:

``fail``
    The limits put the rate past the nominal one on the anti-conservative
    side: an interval that covers less than 95 % of the time, a test that
    rejects more than 5 % of the time.
``pass``
    The limits put the rate on the acceptable side of Bradley's threshold.
``conservative``
    A pass that the limits also put past the far end of Bradley's range - the
    interval is wider, or the test quieter, than the level requires.
``undecided``
    Neither, and the answer needs more draws. At the end of the ladder it is
    printed as it stands, with its limits.

``fail`` is read first. The two conditions can both hold only when the exact
limits are narrower than the gap between the thresholds, which needs some two
thousand draws - five times what the ladder reaches.

What the rule can decide on one look at 400 draws, exactly from the binomial
(:func:`operating_characteristic`):

=================  =========  =========
true coverage      P(pass)    P(fail)
=================  =========  =========
0.90               0.000      0.964
0.925              0.018      0.527
0.95               0.468      0.019
0.97               0.980      0.000
=================  =========  =========

A procedure that is exactly nominal passes about half the time, fails about
one time in fifty and is otherwise left undecided; one that is a full Bradley
step anti-conservative fails almost always.

The ladder is 100 -> 200 -> 400 draws. A pass stops a case; a fail and an
undecided go on, so every fail rests on the full 400 and the chance of failing
a case whose procedure is exactly nominal stays at the 2 % above. Stopping on a
pass is three looks at a pass, though, and that raises the chance of passing a
case that is anti-conservative (:func:`ladder_operating_characteristic`): a
true coverage of 0.93 passes 7.3 % of the time on the ladder against 4.2 % on
one look, 0.925 passes 4.0 % against 1.8 %. A case-level pass therefore says
less than a pass on one look would, and the rates a document quotes are the
pooled family rows, which read the same seeds of every case of a family.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import beta, binom

__all__ = [
    'AGREEMENT',
    'COVERAGE',
    'FALSE_EXCLUSION',
    'NULL_RATE',
    'ONE_STEP_NULL',
    'PASSING',
    'Criterion',
    'clopper_pearson',
    'ladder_operating_characteristic',
    'operating_characteristic',
    'stops_early',
]

#: The verdicts that end a case: more draws cannot take a pass away.
PASSING = ('pass', 'conservative')


def clopper_pearson(hits: int, n: int, level: float = 0.95) -> tuple[float, float]:
    """Exact confidence limits of a proportion - the beta quantiles the interval is defined as.

    Parameters
    ----------
    hits : int
        Successes observed.
    n : int
        Trials.
    level : float
        Confidence level of the limits.

    Returns
    -------
    tuple[float, float]
        Lower and upper limit. ``(0, 1)`` for no trials.
    """
    if n <= 0:
        return 0.0, 1.0
    alpha = 1 - level
    low = float(beta.ppf(alpha / 2, hits, n - hits + 1)) if hits > 0 else 0.0
    high = float(beta.ppf(1 - alpha / 2, hits + 1, n - hits)) if hits < n else 1.0
    return low, high


@dataclass(frozen=True)
class Criterion:
    """One claim's thresholds and the side of them that is safe.

    Attributes
    ----------
    text : str
        How a table names it in its criterion column.
    safe_high : bool
        Whether a rate above the thresholds is the conservative one. True for
        a coverage rate, false for the rate at which a test or a warning
        fires.
    nominal : float
        What the procedure promises: the level of an interval, the level of a
        test, the limit an upper-limit claim states. Exact limits past it on
        the anti-conservative side are a fail.
    acceptable : float
        Bradley's threshold, ``1.5 alpha`` from the nominal rate on the
        anti-conservative side. Exact limits on the safe side of it are a
        pass. Equal to *nominal* where the claim is the threshold itself.
    conservative : float | None
        Beyond which a pass is also labelled conservative - Bradley's other
        threshold, ``0.5 alpha`` from the nominal rate. ``None`` where the
        claim asks for nothing on that side.
    """

    text: str
    safe_high: bool
    nominal: float
    acceptable: float
    conservative: float | None = None

    def verdict(self, hits: int, n: int) -> str:
        """What the exact limits of ``hits / n`` say: pass, conservative, fail or undecided."""
        if n <= 0:
            return 'undecided'
        low, high = clopper_pearson(hits, n)
        if self.safe_high:
            if high < self.nominal:
                return 'fail'
            if low >= self.acceptable:
                return 'conservative' if self.conservative is not None and low > self.conservative else 'pass'
            return 'undecided'
        if low > self.nominal:
            return 'fail'
        if high <= self.acceptable:
            return 'conservative' if self.conservative is not None and high < self.conservative else 'pass'
        return 'undecided'


#: A 95 % interval's coverage over every draw. Bradley's range is
#: [0.925, 0.975]; limits below 0.95 are a fail, limits at or above 0.925 a
#: pass, and a pass above 0.975 is conservative.
COVERAGE = Criterion(text='95 % interval', safe_high=True, nominal=0.95, acceptable=0.925, conservative=0.975)

#: A 95 % joint confidence region's coverage of the true pair of constants,
#: judged as :data:`COVERAGE` judges an interval.
REGION = Criterion(text='95 % region', safe_high=True, nominal=0.95, acceptable=0.925, conservative=0.975)

#: How often a test run at the 5 % level rejects data its model does describe.
#: Bradley's range is [0.025, 0.075].
NULL_RATE = Criterion(text='5 % test', safe_high=False, nominal=0.05, acceptable=0.075, conservative=0.025)

#: An upper-limit claim: a replicate that agrees with the others is left out
#: of the average in at most one fit in twenty. The claim is the threshold, so
#: there is no Bradley step around it and nothing to call conservative.
FALSE_EXCLUSION = Criterion(text='<= 0.05', safe_high=False, nominal=0.05, acceptable=0.05)

#: An upper-limit claim: on titrations with no second step, the second
#: constant of a two-step model is closed below in at most 0.75 % of fits -
#: Bradley's liberal limit, 1.5 times the 0.5 % level the one-step test runs
#: at (``core.pipeline.varpro.SECOND_STEP_LEVEL``). The limit is the claim, so
#: there is nothing to call conservative; a pass needs some 490 draws, since no
#: closure in fewer still leaves an exact upper limit above it, so at 400
#: draws a case can fail and only a pooled row can pass.
ONE_STEP_NULL = Criterion(text='<= 0.0075', safe_high=False, nominal=0.0075, acceptable=0.0075)

#: A lower-limit claim: two computations of the same definition agree on all
#: but one dataset in a hundred.
AGREEMENT = Criterion(text='>= 0.99', safe_high=True, nominal=0.99, acceptable=0.99)


def stops_early(verdict: str) -> bool:
    """Whether *verdict* ends a case before the ladder does.

    Only a pass does. A fail goes on to the last stage so that every published
    fail rests on the full number of draws, and an undecided goes on because
    that is what it is waiting for.
    """
    return verdict in PASSING


def operating_characteristic(criterion: Criterion, n: int, rate: float) -> tuple[float, float]:
    """The chance *criterion* passes and fails a procedure whose true rate is *rate*, over *n* draws.

    Exact: every possible count is judged and its binomial probability added
    to the verdict it gets. A pass counts a conservative pass with it.

    Returns
    -------
    tuple[float, float]
        ``P(pass)`` and ``P(fail)``. What is left over is undecided.
    """
    weights = binom.pmf(range(n + 1), n, rate)
    verdicts = [criterion.verdict(hits, n) for hits in range(n + 1)]
    passed = float(sum(w for w, v in zip(weights, verdicts) if v in PASSING))
    failed = float(sum(w for w, v in zip(weights, verdicts) if v == 'fail'))
    return passed, failed


def ladder_operating_characteristic(criterion: Criterion, stages: tuple[int, ...], rate: float) -> tuple[float, float]:
    """The chance *criterion* passes and fails a procedure of true rate *rate* on the ladder *stages*.

    A case stops at the first stage whose count passes; every other case draws
    the next stage's seeds on top of the ones it has, and at the last stage it
    is passed, failed or left undecided. Exact: the distribution of the count
    among the cases still running is carried from stage to stage.

    Returns
    -------
    tuple[float, float]
        ``P(pass)`` at any stage and ``P(fail)`` at the last. What is left
        over is undecided.
    """
    running = np.array([1.0])
    drawn = 0
    passed = 0.0
    for stage in stages:
        running = np.convolve(running, binom.pmf(np.arange(stage - drawn + 1), stage - drawn, rate))
        drawn = stage
        verdicts = [criterion.verdict(hits, stage) for hits in range(stage + 1)]
        stops = np.array([verdict in PASSING for verdict in verdicts])
        passed += float(running[stops].sum())
        running = np.where(stops, 0.0, running)
    failed = float(sum(w for w, verdict in zip(running, verdicts) if verdict == 'fail'))
    return passed, failed
