"""The limits a rate is judged by, the rule that reads them, and what that rule can decide.

Every pass and fail in the package's tables comes from these functions. Wrong
limits would call a broken coverage rate acceptable; a wrong ladder rule would
publish a failure the draws do not support, or stop a case before its answer
is decided.
"""

from __future__ import annotations

import pytest
from scipy.stats import binom

from validation.criteria import (
    AGREEMENT,
    COVERAGE,
    FALSE_ALARM,
    NULL_RATE,
    clopper_pearson,
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
    """The verdict's false alarms are claimed at most 0.15, so there is nothing to call conservative."""
    assert FALSE_ALARM.verdict(20, 400) == 'pass'
    assert FALSE_ALARM.verdict(80, 400) == 'fail'
    assert FALSE_ALARM.verdict(0, 400) == 'pass'
    assert FALSE_ALARM.verdict(60, 400) == 'undecided'


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


@pytest.mark.parametrize(
    ('rate', 'expected_pass', 'expected_fail'),
    [(0.90, 0.000, 0.964), (0.925, 0.018, 0.527), (0.95, 0.468, 0.019), (0.97, 0.980, 0.000)],
)
def test_the_operating_characteristic_is_the_one_the_documents_state(rate, expected_pass, expected_fail):
    """What the rule can decide at the end of the ladder, against an independent binomial sum.

    These four lines are the table in ``validation/README.md`` and in
    ``validation.criteria``; a change of the thresholds has to move them.
    """
    n = 400
    passed, failed = operating_characteristic(COVERAGE, n, rate)
    verdicts = [COVERAGE.verdict(hits, n) for hits in range(n + 1)]
    by_hand_pass = sum(binom.pmf(h, n, rate) for h, v in enumerate(verdicts) if v in ('pass', 'conservative'))
    by_hand_fail = sum(binom.pmf(h, n, rate) for h, v in enumerate(verdicts) if v == 'fail')
    assert passed == pytest.approx(by_hand_pass, abs=1e-12)
    assert failed == pytest.approx(by_hand_fail, abs=1e-12)
    assert passed == pytest.approx(expected_pass, abs=5e-4)
    assert failed == pytest.approx(expected_fail, abs=5e-4)


def test_a_case_that_is_exactly_nominal_is_failed_about_one_time_in_fifty():
    """The ladder looks three times but fails only at the end, so the rate is the limits' own 2 %."""
    _, failed = operating_characteristic(COVERAGE, 400, 0.95)
    assert failed < 0.025
    _, null_failed = operating_characteristic(NULL_RATE, 400, 0.05)
    assert null_failed < 0.025
