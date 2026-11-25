"""The closed forms the uncertainty budget is judged against, and the cases that ask for them.

``budget-coverage`` compares the application's variance, per-source variance,
spread-if-exact and group indices against closed forms of two test functions;
``source-variance-exact`` compares a shared source's variance against a
quadrature. Neither check means anything if the value it calls the truth is
wrong, so the formulas are checked here against Monte Carlo — a computation
that shares no algebra with them — and the case ids against the keys their rows
are stored under.

The quadrature is the truth only where every fit of the analysis stayed inside
the Ka box, so the two checks that read these rows are also asked here, on rows
built by hand, what they judge and what they only report when one did not.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from scipy.stats import truncnorm

from core.pipeline.inputs import InputSpec, SpecKind
from validation import budget, sobol
from validation.checks import CHECKS
from validation.scenarios import Scenario, concentration_inputs

#: Outer draws of the conditioned columns and inner draws of the rest. Their
#: product is a million evaluations; the between-group variance of 20 000
#: groups carries a relative standard error of sqrt(2/20000) ≈ 1.4 %, which is
#: what the tolerances below are built on.
OUTER, INNER = 20000, 50


def conditional_variance(f, k: int, columns: list[int], rng: np.random.Generator) -> float:
    """``Var(E[Y | u_columns])`` by nested sampling, with the inner noise taken back out.

    Each of :data:`OUTER` draws of the conditioned columns is held while the
    remaining columns are drawn :data:`INNER` times. The variance of the group
    means carries the inner sampling noise as ``E[Var(Y | ·)] / INNER``, which
    the group variances estimate and which is subtracted, so the result is
    unbiased for the conditional variance itself.
    """
    u = rng.random((OUTER, INNER, k))
    u[:, :, columns] = rng.random((OUTER, 1, k))[:, :, columns]
    y = f(u)
    return float(np.var(y.mean(axis=1)) - y.var(axis=1).mean() / INNER)


@pytest.mark.parametrize('name', sorted(sobol.BUDGET_TRUTH))
def test_the_closed_budget_of_a_test_function_is_the_one_sampling_it_finds(name):
    """A wrong closed form would make the check judge the application against the wrong number."""
    f, k, _ = sobol.FUNCTIONS[name]
    variance, vi, group_s1, group_st = sobol.BUDGET_TRUTH[name]()
    rng = np.random.default_rng(20250921)

    drawn = f(rng.random((1000000, k)))
    assert float(np.var(drawn)) == pytest.approx(variance, rel=0.01)

    for i in range(k):
        measured = conditional_variance(f, k, [i], rng)
        if vi[i] > 0.01 * variance:
            assert measured == pytest.approx(vi[i], rel=0.08), f'{name} V_{i + 1}'
        else:
            # Below a percent of the total variance the nested estimator's own
            # scatter is larger than the quantity, so only its size is checked.
            assert abs(measured - vi[i]) < 0.02 * variance, f'{name} V_{i + 1}'

    columns = list(sobol.BUDGET_GROUPS[name])
    rest = [j for j in range(k) if j not in columns]
    assert conditional_variance(f, k, columns, rng) / variance == pytest.approx(group_s1, rel=0.05)
    assert 1 - conditional_variance(f, k, rest, rng) / variance == pytest.approx(group_st, rel=0.05)


def test_the_budget_row_names_every_quantity_the_application_prints():
    """A label the check does not carry is a quantity nobody measured the interval of."""
    case = sobol.SobolCase('ishigami', 1024)
    row = sobol.budget_row(case, 0)
    assert list(row['cov']) == ['V', 'V_1', 'V_2', 'V_3', 'SD_-1', 'SD_-2', 'SD_-3', 'S1_group', 'ST_group']
    assert set(row['cov']) == set(row['err']) == set(row['halfwidth']) == set(row['truth'])
    variance, vi, group_s1, group_st = sobol.ishigami_budget()
    assert row['truth']['V'] == pytest.approx(variance)
    assert row['truth']['V_2'] == pytest.approx(vi[1])
    assert row['truth']['SD_-2'] == pytest.approx(np.sqrt(variance - vi[1]))
    assert row['truth']['S1_group'] == pytest.approx(group_s1)
    assert row['truth']['ST_group'] == pytest.approx(group_st)
    assert row['refused'] is None and row['error'] is None


def test_the_budget_row_estimates_the_quantities_it_labels():
    """A row that paired an estimate with another quantity's truth would report an error that is a mix-up."""
    row = sobol.budget_row(sobol.SobolCase('gfunction', 4096), 3)
    variance, vi, group_s1, _ = sobol.gfunction_budget()
    assert row['err']['V'] + variance == pytest.approx(variance, rel=0.1)
    assert row['err']['V_1'] + vi[0] == pytest.approx(vi[0], rel=0.15)
    assert row['err']['S1_group'] + group_s1 == pytest.approx(group_s1, rel=0.1)


def test_the_spread_left_without_a_source_is_read_off_the_first_order_index():
    """``SD_-i`` is what the law of total variance gives, not the total index's complement."""
    variance, vi, _, _ = sobol.gfunction_budget()
    row = sobol.budget_row(sobol.SobolCase('gfunction', 1024), 1)
    for i, value in enumerate(vi):
        assert row['truth'][f'SD_-{i + 1}'] == pytest.approx(np.sqrt(variance - value))


def test_the_variance_of_a_shared_source_is_the_integral_of_the_law_it_is_drawn_from():
    """The claim of ``source-variance-exact`` is this number; a wrong quadrature would judge the app against it."""
    for sigma_pct in (4.0, 20.0):
        law = truncnorm(a=-100.0 / sigma_pct, b=np.inf, loc=0.0, scale=sigma_pct / 100)
        drawn = np.log10(1 + law.rvs(400000, random_state=np.random.default_rng(7)))
        assert budget.log_variance(sigma_pct) == pytest.approx(float(np.var(drawn)), rel=0.02)


def test_a_small_shared_source_is_its_own_percent_in_decades():
    """For a source far from the truncation, log10(1 + e) is e / ln 10, which fixes the scale of the answer."""
    assert budget.log_variance(1.0) == pytest.approx((0.01 / np.log(10)) ** 2, rel=1e-3)


def test_a_budget_case_is_addressed_by_what_it_runs():
    """Two cases that differ in the design or the reduction may not write into one another's rows."""
    scenario = Scenario(assay='DBA_DtoH', regime=10.0, n_points=12, noise=0.005)
    case = budget.BudgetCase(scenario=scenario)
    assert case.id == f'{scenario.id},N=1024'
    assert budget.BudgetCase(scenario=scenario, n_samples=4096).id != case.id
    assert budget.BudgetCase(scenario=scenario, reduce_to=0.4).id.endswith(',r=0.4')
    ids = [c.id for c in budget.exact_cases() + budget.whatif_cases()]
    assert len(ids) == len(set(ids))


def test_every_exact_case_carries_the_source_its_claim_is_about():
    """The claim names one source shared by every concentration; a case without it measures nothing."""
    for case in budget.exact_cases():
        assert case.scenario.assay in ('DBA_HtoD', 'DBA_DtoH')
        source = case.scenario.shared_sources[0]
        assert source.keys == concentration_inputs(case.scenario.assay)
        assert len(source.keys) >= 2


def test_every_what_if_case_asks_for_an_improvement_of_a_source_it_states():
    """A what-if of a source nothing was stated for, or of a wider one, has no answer to compare."""
    for case in budget.whatif_cases():
        assert 0 < case.reduce_to < 1
        assert case.scenario.specs
        assert all(entry.sigma == 5.0 for entry in case.scenario.specs)


def test_the_second_analysis_samples_the_distribution_the_what_if_re_weights_towards():
    """A reduced spec shrunk about anything but its own centre would answer a different question."""
    narrowed = budget._narrowed(InputSpec.sigma_pct(5.0), 0.4)
    assert narrowed.kind is SpecKind.SIGMA
    assert narrowed.sigma == pytest.approx(2.0)
    range_spec = budget._narrowed(InputSpec.interval_pct(-10.0, 30.0), 0.5)
    assert (range_spec.lo, range_spec.hi) == pytest.approx((0.0, 20.0))

    case = budget.whatif_cases()[0]
    errors = case.scenario.error_model
    source = next(iter(errors.source_specs()))
    reduced = budget._reduced(errors, source, 0.4)
    assert reduced.specs[source].sigma == pytest.approx(errors.specs[source].sigma * 0.4)
    assert {k: v for k, v in reduced.specs.items() if k != source} == {
        k: v for k, v in errors.specs.items() if k != source
    }


def test_reducing_a_shared_source_leaves_the_inputs_it_loads_alone():
    """A source is one number; improving it may not quietly re-state the inputs beside it."""
    scenario = budget.exact_cases()[0].scenario
    errors = scenario.error_model
    source = f'shared:{scenario.shared_sources[0].name}'
    reduced = budget._reduced(errors, source, 0.5)
    assert reduced.shared[0].sigma_pct == pytest.approx(scenario.shared_sources[0].sigma * 0.5)
    assert reduced.shared[0].inputs == scenario.shared_sources[0].keys
    assert reduced.specs == errors.specs
    assert budget._reduced(errors, source, 1.0) == replace(errors)


# -- rows whose fits ran to a bound of the Ka box ----------------------------------


def _exact_row(**facts) -> dict:
    """One stored ``source-variance-exact`` row for one binding constant."""
    return {
        'truth': 1.2e-4,
        'ka': {
            'Ka_guest': {
                'covers': True,
                'variance': 1.3e-4,
                'low': 1.0e-4,
                'high': 1.6e-4,
                'st_minus_s1': 0.01,
                'sum_rule': 0.0,
                'on_bound': False,
                'n_on_bound': 0,
                **facts,
            }
        },
    }


def test_a_row_whose_fits_stayed_inside_the_ka_box_is_the_one_the_quadrature_judges():
    """The identity the truth rests on holds there, so the row answers the claim."""
    metrics = CHECKS['source-variance-exact'].metrics(_exact_row())

    assert metrics['cov.Ka_guest'] is True
    assert metrics['~on_bound.Ka_guest'] is False
    assert metrics['~variance.Ka_guest'] == 1.3e-4


@pytest.mark.parametrize('facts', [{'on_bound': True}, {'n_on_bound': 1}], ids=['baseline', 'one sample'])
def test_a_row_with_a_fit_on_a_ka_bound_says_nothing_about_the_source_variance(facts):
    """On a bound the output is constant, so the variance the source carries is not the quadrature.

    Judging such a row would count a mismatch the claim never made as a failure
    of the interval. It is left out of the rate — ``None``, the package's "this
    row says nothing" — and counted beside it instead.
    """
    metrics = CHECKS['source-variance-exact'].metrics(_exact_row(**facts))

    assert metrics['cov.Ka_guest'] is None
    assert metrics['~on_bound.Ka_guest'] is True
    # What the row does measure is still reported: it is the truth that does not apply, not the fit.
    assert metrics['~variance.Ka_guest'] == 1.3e-4
    assert metrics['~sum_rule.Ka_guest'] == 0.0


def _whatif_row(**facts) -> dict:
    """One stored ``what-if-accuracy`` row for one binding constant."""
    return {
        'source': 'h0',
        'ka': {
            'Ka_guest': {
                'formula_err': 0.02,
                'reweighted_err': -0.03,
                'effective': 540.0,
                'on_bound': False,
                'n_on_bound': 0,
                **facts,
            }
        },
    }


def test_the_what_if_errors_are_reported_again_over_the_rows_with_no_fit_on_a_bound():
    """A jump of decades is in both spreads the error compares, so the two populations are read apart."""
    clean = CHECKS['what-if-accuracy'].metrics(_whatif_row())
    on_bound = CHECKS['what-if-accuracy'].metrics(_whatif_row(n_on_bound=12))

    assert clean['~formula_err.Ka_guest'] == clean['~formula_err_clean.Ka_guest'] == 0.02
    assert clean['~reweighted_err.Ka_guest'] == clean['~reweighted_err_clean.Ka_guest'] == -0.03
    assert clean['~on_bound.Ka_guest'] is False
    # The row stays in the series over every draw and leaves the clean one.
    assert on_bound['~formula_err.Ka_guest'] == 0.02
    assert on_bound['~formula_err_clean.Ka_guest'] is None
    assert on_bound['~reweighted_err_clean.Ka_guest'] is None
    assert on_bound['~on_bound.Ka_guest'] is True
