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

The ladder is 100 -> 200 -> 400 draws. A pass stops a case; a fail and an
undecided go on, so every published fail rests on the full 400. That keeps the
chance of failing a case whose procedure is exactly nominal at the one-sided
2 % the limits carry, rather than accumulating it over the three looks.

What the rule can decide at the end of the ladder, exactly from the binomial
(:func:`operating_characteristic`, N = 400):

=================  =========  =========
true coverage      P(pass)    P(fail)
=================  =========  =========
0.90               0.000      0.964
0.925              0.018      0.527
0.95               0.468      0.019
0.97               0.980      0.000
=================  =========  =========

A procedure that is exactly nominal passes about half the time and is
otherwise left undecided; one that is a full Bradley step anti-conservative
fails almost always.
"""

from __future__ import annotations

from dataclasses import dataclass

from scipy.stats import beta, binom

__all__ = [
    'AGREEMENT',
    'COVERAGE',
    'FALSE_ALARM',
    'NULL_RATE',
    'PASSING',
    'Criterion',
    'clopper_pearson',
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

#: How often a test run at the 5 % level rejects data its model does describe.
#: Bradley's range is [0.025, 0.075].
NULL_RATE = Criterion(text='5 % test', safe_high=False, nominal=0.05, acceptable=0.075, conservative=0.025)

#: An upper-limit claim: the verdict blames good data on the model or on the
#: inputs in at most one fit in seven. The claim is the threshold, so there is
#: no Bradley step around it and nothing to call conservative.
FALSE_ALARM = Criterion(text='<= 0.15', safe_high=False, nominal=0.15, acceptable=0.15)

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
