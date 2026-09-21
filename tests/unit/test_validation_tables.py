"""A store of known rows renders to a known table.

The tables are what a reader and the paper quote. This pins the arithmetic
behind a printed line — the count, the rate, the exact limits and the verdict —
what is judged when an interval reaches a Ka bound, the case filter, and the
ways a table says it is reading less than the whole check.
"""

from __future__ import annotations

from dataclasses import replace

from validation.checks import Check, conditional_coverage
from validation.criteria import COVERAGE
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


def test_the_coverage_over_the_closed_draws_is_reported_beside_the_verdict_and_never_judged():
    """Conditioning on closure keeps the draws whose noise made the profile steep, a different population."""
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


def test_an_unevenly_sampled_family_is_not_published_as_the_family_s_rate():
    """Pooling whichever cases happened to finish would print one case's rate under the family's name."""
    store = {**rows([True] * 10, [False] * 10, CASES[0].id), **rows([False] * 4, [False] * 4, CASES[1].id)}
    (pooled,) = [r for r in summarise(CHECK, store).pooled_rates if r.series == 'cov.Ka_guest']
    assert (pooled.verdict, pooled.criterion) == ('partial', None)


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
