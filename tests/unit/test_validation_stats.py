"""The limits a rate is judged by, the rule that reads them, and what that rule can decide.

Every pass and fail in the package's tables comes from these functions. Wrong
limits would call a broken coverage rate acceptable; a wrong ladder rule would
publish a failure the draws do not support, or stop a case before its answer
is decided.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.stats import binom

from validation.criteria import (
    AGREEMENT,
    COVERAGE,
    FALSE_EXCLUSION,
    NULL_RATE,
    clopper_pearson,
    ladder_operating_characteristic,
    operating_characteristic,
    stops_early,
)


@pytest.mark.parametrize(('hits', 'n'), [(3, 10), (47, 50), (950, 1000)])
def test_the_limits_are_the_proportions_the_count_is_on_the_edge_of(hits, n):
    """Clopper-Pearson is defined by the binomial tails, which is a different formula from the beta one used.

    At the lower limit a binomial with that success probability produces this
    many successes or more with probability 2.5 %, and at the upper limit this
    many or fewer.
    """
    low, high = clopper_pearson(hits, n)
    assert binom.sf(hits - 1, n, low) == pytest.approx(0.025, rel=1e-6)
    assert binom.cdf(hits, n, high) == pytest.approx(0.025, rel=1e-6)


def test_the_ends_have_no_limit_on_the_side_they_cannot_reach():
    """All or nothing observed says nothing about how far the truth lies on that side."""
    assert clopper_pearson(0, 20)[0] == 0.0
    assert clopper_pearson(20, 20)[1] == 1.0
    assert clopper_pearson(0, 20)[1] < 0.2
    assert clopper_pearson(20, 20)[0] > 0.8


def test_a_coverage_rate_fails_only_when_the_draws_put_it_below_the_level():
    """Bradley's liberal criterion: 0.925 is acceptable, and only the anti-conservative side can fail."""
    assert COVERAGE.verdict(95, 100) == 'undecided'
    assert COVERAGE.verdict(384, 400) == 'pass'
    assert COVERAGE.verdict(360, 400) == 'fail'
    assert COVERAGE.verdict(0, 0) == 'undecided'


def test_a_coverage_rate_the_data_put_above_bradley_s_far_end_is_a_pass_called_conservative():
    """An interval wider than the level requires is safe, and a reader still wants to be told."""
    assert COVERAGE.verdict(400, 400) == 'conservative'
    assert stops_early(COVERAGE.verdict(400, 400))


def test_a_test_at_the_5_per_cent_level_fails_only_when_it_rejects_too_often():
    """A quiet test errs on the safe side; a loud one warns a user off data the model does describe."""
    assert NULL_RATE.verdict(19, 400) == 'pass'
    assert NULL_RATE.verdict(40, 400) == 'fail'
    assert NULL_RATE.verdict(28, 400) == 'undecided'
    assert NULL_RATE.verdict(0, 400) == 'conservative'


def test_an_upper_limit_claim_is_read_against_the_limit_itself():
    """A replicate that agrees with the rest is claimed to be left out of at most one fit in twenty.

    The claim is the threshold, so there is nothing to call conservative.
    """
    assert FALSE_EXCLUSION.verdict(8, 400) == 'pass'
    assert FALSE_EXCLUSION.verdict(40, 400) == 'fail'
    assert FALSE_EXCLUSION.verdict(0, 400) == 'pass'
    assert FALSE_EXCLUSION.verdict(15, 400) == 'undecided'


def test_a_lower_limit_claim_is_the_same_rule_the_other_way_round():
    """Two computations of one definition are claimed to agree on all but one dataset in a hundred."""
    assert AGREEMENT.verdict(400, 400) == 'pass'
    assert AGREEMENT.verdict(390, 400) == 'fail'
    assert AGREEMENT.verdict(100, 100) == 'undecided'


def test_only_a_pass_stops_a_case_before_the_end_of_the_ladder():
    """A fail at 100 seeds goes on to 400, so every published failure rests on the full draw."""
    assert stops_early('pass') and stops_early('conservative')
    assert not stops_early('fail')
    assert not stops_early('undecided')
    assert COVERAGE.verdict(80, 100) == 'fail'
    assert COVERAGE.verdict(98, 100) == 'pass'


def _count_thresholds(n: int) -> tuple[int, int]:
    """The fewest hits a coverage rate passes with at *n* draws, and the most it fails with.

    Read off the binomial tails that define the exact limits, not off the beta
    quantiles the package computes them with: a pass needs the lower limit at
    or above 0.925, which is ``P(X >= hits | 0.925) <= 0.025``; a fail needs
    the upper limit below 0.95, which is ``P(X <= hits | 0.95) < 0.025``.
    """
    passing = min(h for h in range(n + 1) if binom.sf(h - 1, n, 0.925) <= 0.025)
    failing = max(h for h in range(n + 1) if binom.cdf(h, n, 0.95) < 0.025)
    return passing, failing


@pytest.mark.parametrize(
    ('rate', 'expected_pass', 'expected_fail'),
    [(0.90, 0.000, 0.964), (0.925, 0.018, 0.527), (0.95, 0.468, 0.019), (0.97, 0.980, 0.000)],
)
def test_the_operating_characteristic_of_one_look_is_the_one_the_documents_state(rate, expected_pass, expected_fail):
    """What the rule decides at 400 draws, against binomial tails at the counts that decide it.

    These four lines are the table in ``validation/README.md`` and in
    ``validation.criteria``; a change of the thresholds has to move them.
    """
    passing, failing = _count_thresholds(400)
    passed, failed = operating_characteristic(COVERAGE, 400, rate)
    assert passed == pytest.approx(binom.sf(passing - 1, 400, rate), abs=1e-12)
    assert failed == pytest.approx(binom.cdf(failing, 400, rate), abs=1e-12)
    assert passed == pytest.approx(expected_pass, abs=5e-4)
    assert failed == pytest.approx(expected_fail, abs=5e-4)


def _ladder_by_paths(rate: float) -> tuple[float, float]:
    """The ladder 100 -> 200 -> 400 with a stop on a pass, summed over the counts of its three increments."""
    (p100, _), (p200, _), (p400, f400) = (_count_thresholds(n) for n in (100, 200, 400))
    first, second, third = (
        binom.pmf(np.arange(101), 100, rate),
        binom.pmf(np.arange(101), 100, rate),
        binom.pmf(np.arange(201), 200, rate),
    )
    passed = failed = 0.0
    for a, pa in enumerate(first):
        if a >= p100:
            passed += pa
            continue
        for b, pb in enumerate(second):
            if a + b >= p200:
                passed += pa * pb
                continue
            hits = a + b + np.arange(201)
            passed += pa * pb * third[hits >= p400].sum()
            failed += pa * pb * third[hits <= f400].sum()
    return passed, failed


@pytest.mark.parametrize(
    ('rate', 'ladder_pass', 'single_pass'),
    [(0.925, 0.040, 0.018), (0.93, 0.073, 0.042), (0.95, 0.515, 0.468)],
)
def test_stopping_on_a_pass_raises_the_chance_of_passing_and_leaves_the_chance_of_failing(
    rate, ladder_pass, single_pass
):
    """Three looks at a pass are three chances at one; a fail is read once, at the end.

    The numbers are the ones ``validation/README.md`` states: a procedure
    whose true coverage is 0.93 passes 7.3 % of the time on the ladder against
    4.2 % on one look at 400 draws, and fails equally often either way.
    """
    passed, failed = ladder_operating_characteristic(COVERAGE, (100, 200, 400), rate)
    by_paths = _ladder_by_paths(rate)
    assert (passed, failed) == pytest.approx(by_paths, abs=1e-10)
    assert passed == pytest.approx(ladder_pass, abs=5e-4)
    assert operating_characteristic(COVERAGE, 400, rate)[0] == pytest.approx(single_pass, abs=5e-4)
    assert failed == pytest.approx(operating_characteristic(COVERAGE, 400, rate)[1], abs=5e-3)


def test_a_ladder_of_one_stage_is_one_look():
    """With nothing to stop early on, the ladder and the single look are the same rule."""
    assert ladder_operating_characteristic(NULL_RATE, (400,), 0.06) == pytest.approx(
        operating_characteristic(NULL_RATE, 400, 0.06), abs=1e-12
    )


def test_a_case_that_is_exactly_nominal_is_failed_about_one_time_in_fifty():
    """A fail is read only at the end of the ladder, so its rate is the limits' own 2 %.

    Across the hundreds of cases a full run judges, that is the number of case
    fails chance alone produces, which ``validation/README.md`` states.
    """
    _, failed = operating_characteristic(COVERAGE, 400, 0.95)
    assert failed < 0.025
    _, null_failed = operating_characteristic(NULL_RATE, 400, 0.05)
    assert null_failed < 0.025
