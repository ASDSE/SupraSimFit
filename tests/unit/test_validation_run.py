"""What a run does: which cases it takes, which it stops, and what a dying worker costs it.

A full run is hours of fitting. A job that raises has to cost its own row and
no other, and a worker process that dies — the operating system reaping it, a
segmentation fault in a library call — has to cost the rows in flight and not
the run. The ladder has to stop a case that has passed and carry on with every
case that has not, because a published failure rests on the last stage.
"""

from __future__ import annotations

import pytest

from validation import run as runner
from validation import store
from validation.checks import CHECKS, Check, conditional_coverage, matching_cases
from validation.criteria import COVERAGE
from validation.scenarios import Scenario


@pytest.fixture
def results(tmp_path, monkeypatch):
    """A results directory of this test's own."""
    monkeypatch.setattr(store, 'RESULTS_DIR', tmp_path)
    return tmp_path


def jobs(count: int) -> list:
    """*count* jobs of one case."""
    return [('demo', 'A', seed, 'abc') for seed in range(count)]


def test_the_jobs_a_dead_pool_left_unanswered_go_on_a_new_one(results, monkeypatch):
    """A job is a pure function of its key, so resubmitting it is free — and losing it is not."""
    pools = []

    def one_pool(pending, check, deadline, workers, total):
        pools.append(list(pending))
        if len(pools) == 1:
            store.append(check, [{'case': job[1], 'seed': job[2], 'code': job[3]} for job in pending[:2]])
            return pending[2:], 2
        store.append(check, [{'case': job[1], 'seed': job[2], 'code': job[3]} for job in pending])
        return [], len(pending)

    monkeypatch.setattr(runner, '_one_pool', one_pool)
    assert runner._execute(jobs(5), 'demo', None, 4) == 5
    assert [len(pending) for pending in pools] == [5, 3]
    assert set(store.load('demo', 'abc')) == {('A', seed) for seed in range(5)}


def test_a_pool_that_never_finishes_a_row_ends_the_run_rather_than_looping(results, monkeypatch):
    """Resubmitting for ever would hide jobs that are themselves killing the workers."""
    monkeypatch.setattr(runner, '_one_pool', lambda pending, *args: (list(pending), 0))
    with pytest.raises(RuntimeError, match='without finishing a row'):
        runner._execute(jobs(3), 'demo', None, 4)


def test_a_job_that_dies_is_stored_as_an_error_under_its_own_key():
    """An error row keeps the count honest; a lost row would quietly shrink the denominator."""
    row = runner._error_row(('demo', 'A', 7, 'abc'), MemoryError('the worker was killed'))
    assert store.row_key(row) == ('A', 7)
    assert row['code'] == 'abc'
    assert row['error'] == 'MemoryError: the worker was killed'
    assert row['refused'] is None


CASES = (Scenario(assay='IDA', regime=10.0), Scenario(assay='GDA', regime=10.0))

LADDER = Check(
    name='demo',
    claim='A demonstration.',
    metrics=conditional_coverage,
    cases=CASES,
    criterion=COVERAGE,
)


def coverage_rows(covers: list[bool]) -> list[dict]:
    """Rows of one case whose closed intervals cover as given."""
    return [
        {'cond': {'Ka_guest': {'covers': c, 'open': False, 'split': False, 'limited': False, 'width': 1.0}}}
        for c in covers
    ]


def test_a_case_whose_rate_has_passed_stops_where_it_is():
    """A case whose every judged rate has passed spends no more fits; the pooled rows read its first seeds."""
    assert runner._case_passed(LADDER, CASES[0].id, coverage_rows([True] * 100), [])


def test_a_case_that_fails_at_the_first_stage_goes_on_to_the_next():
    """Every published failure rests on the last stage, so a fail decides nothing before it."""
    rows = coverage_rows([True] * 80 + [False] * 20)
    assert not runner._case_passed(LADDER, CASES[0].id, rows, [])


def test_an_undecided_case_goes_on_and_a_case_with_nothing_judged_yet_goes_on_too():
    """More seeds are exactly what an undecided rate is waiting for, and a refused case has no rate at all."""
    assert not runner._case_passed(LADDER, CASES[0].id, coverage_rows([True] * 19 + [False]), [])
    assert not runner._case_passed(LADDER, CASES[0].id, [{'cond': {}}] * 100, [])


def test_a_case_stops_only_once_every_check_reading_it_has_passed_as_well():
    """A derived check states a claim of its own on the same rows, and its rate has to pass too."""
    view = Check(name='view', claim='.', metrics=lambda row: {'reject': False}, criterion=COVERAGE, derived_from='demo')
    assert not runner._case_passed(LADDER, CASES[0].id, coverage_rows([True] * 100), [view])


def test_a_run_takes_the_cases_whose_id_one_expression_matches():
    """A fix round re-runs the cells it touched; any of several expressions selects, and none selects all."""
    assert matching_cases(LADDER, ['GDA']) == (CASES[1],)
    assert matching_cases(LADDER, ['GDA', 'IDA']) == CASES
    assert matching_cases(LADDER, None) == CASES
    assert matching_cases(LADDER, ['DBA_HG2']) == ()


def test_a_one_step_null_case_can_fail_alone_and_pass_only_in_its_pooled_row():
    """No closure in 400 draws still leaves an exact upper limit above 0.0075; the eight cases of a model pool 3200."""
    check = CHECKS['one-step-null']
    case = check.cases[0].id
    key = 'Ka_HG2' if check.cases[0].assay == 'DBA_HG2' else 'Ka_H2G'
    facts = {
        'covers': True,
        'open': True,
        'open_low': True,
        'split': False,
        'limited': False,
        'width': 9.0,
        'one_step_p': 0.5,
    }
    assert check.stages == (400,)
    assert not runner._case_passed(check, case, [{'aware': {key: facts}}] * 400, [])
    per_model = sum(1 for other in check.cases if other.assay == check.cases[0].assay)
    assert per_model == 8
    # A rate of 0.15 %, as the F reference gives on one-step data, passes the pool.
    assert check.criterion.verdict(5, per_model * 400) == 'pass'
