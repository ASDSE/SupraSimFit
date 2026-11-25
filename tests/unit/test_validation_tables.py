"""A store of known rows renders to a known table.

The tables are what a reader and the paper quote. This pins the arithmetic
behind a printed line — the count, the rate, the exact limits and the verdict —
what is judged when an interval reaches a Ka bound, the case filter, and the
ways a table says it is reading less than the whole check.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from validation.checks import Check, closed_coverage, conditional_coverage
from validation.criteria import COVERAGE, operating_characteristic
from validation.scenarios import Scenario
from validation.tables import render, summarise

CASES = (Scenario(assay='IDA', regime=10.0), Scenario(assay='IDA', regime=0.1))

CHECK = Check(
    name='demo',
    claim='A demonstration.',
    metrics=conditional_coverage,
    cases=CASES,
    criterion=COVERAGE,
    criterion_reason='Because this is a test.',
)


def rows(covers: list[bool], open_flags: list[bool], case: str = CASES[0].id) -> dict:
    """A store of one case whose intervals cover and reach a bound as given."""
    return {
        (case, seed): {
            'case': case,
            'seed': seed,
            'cond': {
                'Ka_guest': {'covers': c, 'open': o, 'split': False, 'limited': False, 'width': 1.0 + seed},
            },
        }
        for seed, (c, o) in enumerate(zip(covers, open_flags))
    }


def test_a_rate_its_limits_and_its_verdict_are_printed_as_computed():
    """One line of the table, end to end: 19 of 20 intervals covered, still undecided."""
    table = render(summarise(CHECK, rows([True] * 19 + [False], [False] * 20)), 'c0ffee')
    assert (
        '| IDA,K=10,n=12,noise=0.01 | cov.Ka_guest | 20 | 0.950 | [0.751, 0.999] | 95 % interval | undecided |' in table
    )
    assert '| IDA,K=10,n=12,noise=0.01 | open.Ka_guest | 20 | 0.000 | [0.000, 0.168] |  |  |' in table
    assert '| IDA,K=10,n=12,noise=0.01 | width.Ka_guest | 20 | 10.5 | 19.81 | 20 | 11.98 |' in table
    assert '_Code c0ffee, rendered' in table


def test_the_judged_rate_counts_every_draw_including_the_open_ones():
    """The level promises coverage over every draw, and an open interval covers by saying Ka is not limited."""
    summary = summarise(CHECK, rows([True] * 200, [True] * 200))
    (judged,) = [rate for rate in summary.rates if rate.series == 'cov.Ka_guest']
    (closed,) = [rate for rate in summary.rates if rate.series == 'closed_cov.Ka_guest'] or [None]
    (open_rate,) = [rate for rate in summary.rates if rate.series == 'open.Ka_guest']
    assert (judged.criterion, judged.verdict) == (COVERAGE, 'conservative')
    assert closed is None
    assert open_rate.rate == 1.0 and open_rate.criterion is None


def test_the_coverage_over_the_closed_draws_is_reported_beside_a_verdict_that_is_about_every_draw():
    """Where the claim is the coverage over every draw, the closed draws are described beside it."""
    summary = summarise(CHECK, rows([True] * 80 + [False] * 20, [False] * 50 + [True] * 50))
    judged = {rate.series: rate for rate in summary.rates}
    assert judged['cov.Ka_guest'].n == 100
    assert judged['cov.Ka_guest'].verdict == 'fail'
    assert judged['closed_cov.Ka_guest'].n == 50
    assert judged['closed_cov.Ka_guest'].criterion is None
    assert judged['closed_cov.Ka_guest'].verdict == ''


def test_a_refused_and_a_failed_row_are_counted_and_shown():
    """A row that never produced a fit must not vanish into a rate that looks fine."""
    store = rows([True] * 4, [False] * 4)
    case = CASES[0].id
    store[(case, 4)] = {'case': case, 'seed': 4, 'refused': 'FitRefused: the bounds hold no solution'}
    store[(case, 5)] = {'case': case, 'seed': 5, 'error': 'KeyError: Ka_guest'}
    summary = summarise(CHECK, store)
    assert (summary.refused, summary.errors) == (1, 1)
    table = render(summary, 'c0ffee')
    assert '1 refused, 1 errors' in table
    assert 'FitRefused: the bounds hold no solution' in table
    (rate,) = [r for r in summary.rates if r.series == 'cov.Ka_guest']
    assert rate.n == 4


def test_cases_of_one_assay_are_pooled_under_its_name():
    """The pooled row is the family's rate, not an average of its cases' rates."""
    store = {**rows([True] * 10, [False] * 10, CASES[0].id), **rows([False] * 10, [False] * 10, CASES[1].id)}
    summary = summarise(CHECK, store)
    (pooled,) = [r for r in summary.pooled_rates if r.series == 'cov.Ka_guest']
    assert (pooled.case, pooled.n, pooled.hits) == ('IDA', 20, 10)
    assert pooled.verdict == 'fail'


def test_a_family_is_pooled_over_the_seeds_every_one_of_its_cases_reached():
    """A case the ladder carried further must not weigh more in the family's rate than one it stopped early.

    Case one reached ten seeds and case two four, so the family is read over
    seeds 0 to 3 of each: eight draws, four of them covered, and judged.
    """
    store = {**rows([True] * 10, [False] * 10, CASES[0].id), **rows([False] * 4, [False] * 4, CASES[1].id)}
    summary = summarise(CHECK, store)
    (pooled,) = [r for r in summary.pooled_rates if r.series == 'cov.Ka_guest']
    assert (pooled.n, pooled.hits) == (8, 4)
    assert pooled.criterion == COVERAGE
    assert pooled.verdict == COVERAGE.verdict(4, 8)
    assert summary.pooled_seeds == {'IDA': (2, 4)}
    table = render(summary, 'c0ffee')
    assert '| IDA | 2 x 4 | cov.Ka_guest | 8 | 0.500 |' in table


def test_a_gap_in_a_case_s_seeds_ends_the_prefix_the_family_is_pooled_over():
    """Seeds past a missing one are not the same seeds in every case, so they stay out of the pool."""
    store = {**rows([True] * 10, [False] * 10, CASES[0].id), **rows([True] * 6, [False] * 6, CASES[1].id)}
    del store[(CASES[1].id, 3)]
    summary = summarise(CHECK, store)
    assert summary.pooled_seeds == {'IDA': (2, 3)}
    (pooled,) = [r for r in summary.pooled_rates if r.series == 'cov.Ka_guest']
    assert pooled.n == 6


def test_a_family_one_of_whose_cases_has_no_rows_is_not_published_as_the_family_s_rate():
    """A pool over the cases that happened to run is the rate of those cases, not of the family."""
    view = replace(CHECK, cases=CASES + (Scenario(assay='IDA', regime=1000.0),))
    store = {**rows([True] * 10, [False] * 10, CASES[0].id), **rows([False] * 4, [False] * 4, CASES[1].id)}
    (pooled,) = [r for r in summarise(view, store).pooled_rates if r.series == 'cov.Ka_guest']
    assert (pooled.verdict, pooled.criterion) == ('partial', None)
    assert pooled.n == 8


def test_a_table_says_how_many_case_fails_chance_alone_would_give():
    """Hundreds of judged cases fail a few by chance; the table has to say how many before any is read.

    Two coverage rates at 400 draws, each failed by an exactly nominal
    procedure with probability 0.019, expect 0.04 fails between them.
    """
    store = {**rows([True] * 400, [False] * 400, CASES[0].id), **rows([True] * 400, [False] * 400, CASES[1].id)}
    summary = summarise(CHECK, store)
    table = render(summary, 'c0ffee')
    _, nominal_fail = operating_characteristic(COVERAGE, 400, 0.95)
    assert summary.chance_fails == pytest.approx(2 * nominal_fail)
    assert '2 case rates judged: 0 failing and 0 undecided' in table
    assert f'about {2 * nominal_fail:.2f} of them would fail by chance' in table


def test_where_the_claim_is_about_closed_intervals_their_coverage_is_judged_as_well():
    """A finite interval is what a user reads as a guarantee, so where it undercovers the check has to fail."""
    check = replace(CHECK, metrics=closed_coverage)
    summary = summarise(check, rows([True] * 80 + [False] * 20, [True] * 80 + [False] * 20))
    judged = {rate.series: rate for rate in summary.rates}
    assert judged['cov.Ka_guest'].n == 100
    assert judged['closed_cov.Ka_guest'].n == 20
    assert judged['closed_cov.Ka_guest'].criterion == COVERAGE
    assert judged['closed_cov.Ka_guest'].verdict == 'fail'


def test_a_table_says_how_many_of_the_check_s_cases_it_read():
    """A run stopped early must not render as a finished table."""
    summary = summarise(CHECK, rows([True] * 10, [False] * 10))
    assert (len(summary.seeds), summary.declared, summary.complete) == (1, 2, False)
    table = render(summary, 'c0ffee')
    assert '1 of 2 cases have rows' in table
    assert '> **Partial.** 1 of the 2 cases this check defines have no rows yet.' in table


def test_a_check_reads_only_the_cases_it_names():
    """A derived check states a claim about its own grid, not about every row its parent holds."""
    view = replace(CHECK, cases=(CASES[0],), derived_from='demo')
    store = {**rows([True] * 10, [False] * 10, CASES[0].id), **rows([False] * 10, [False] * 10, CASES[1].id)}
    summary = summarise(view, store)
    assert set(summary.seeds) == {CASES[0].id}
    (rate,) = [r for r in summary.rates if r.series == 'cov.Ka_guest']
    assert (rate.n, rate.hits) == (10, 10)


def test_a_signed_series_reports_the_size_of_its_worst_value():
    """A large negative error printed under 'max' as a small positive one would read as accuracy."""
    case = CASES[0].id
    store = {
        (case, seed): {'case': case, 'seed': seed, 'cond': {}, 'err': value}
        for seed, value in enumerate((0.001, -0.5, 0.002, 0.003))
    }
    check = replace(CHECK, metrics=lambda row: {'~err': row.get('err')})
    (spread,) = summarise(check, store).spreads
    assert spread.largest == 0.5
    assert spread.p99 > 0.4


def test_a_filter_prints_the_matching_cases_and_says_that_it_did():
    """A fix round prints the cells it touched; the cases left out did not fail, they were not asked."""
    store = {**rows([True] * 10, [False] * 10, CASES[0].id), **rows([False] * 10, [False] * 10, CASES[1].id)}
    summary = summarise(CHECK, store, ['K=10'])
    assert set(summary.seeds) == {CASES[0].id}
    assert summary.declared == 1
    table = render(summary, 'c0ffee')
    assert '> **Filtered.** Only the cases matching `K=10` are shown; the check defines 2 cases in all.' in table
    assert CASES[1].id not in table


def test_a_filter_that_matches_nothing_reads_no_rows_at_all():
    """An expression nobody's case matches must print an empty table, never the whole check."""
    store = rows([True] * 10, [False] * 10)
    assert summarise(CHECK, store, ['DBA_HG2']).seeds == {}


def test_a_filtered_check_that_reads_its_parent_whole_says_so_rather_than_naming_no_cases():
    """A derived check with no cases of its own reads every case of its parent; 'defines 0 cases' would misread."""
    view = replace(CHECK, cases=(), derived_from='demo')
    table = render(summarise(view, rows([True] * 10, [False] * 10), ['K=10']), 'c0ffee')
    assert 'the check reads every case of `demo`.' in table
