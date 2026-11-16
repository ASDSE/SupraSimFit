"""What a scored row says about an interval and about a joint region.

A coverage rate is a count of these two answers. Scoring a split interval on
its outer edges would count a Ka the fit rejects as covered, and reading a
joint region anywhere but off the surface Ka confidence draws would
let the tab go wrong while the check stayed green.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from scipy.optimize import lsq_linear, minimize_scalar
from scipy.stats import f as f_dist

from core.assays import ASSAY_CLASSES
from core.assays.registry import AssayType
from core.pipeline.fit_pipeline import FitConfig, fit_measurement_set
from core.pipeline.inputs import TITRANT
from core.pipeline.noise import noise_law
from core.pipeline.profile import JointRegion
from core.pipeline.varpro import KaInterval, Projection
from validation import checks, reference
from validation.generate import dataset
from validation.reference import agreement_row, pooling_row, reference_intervals
from validation.scenarios import Scenario, SharedEntry, SpecEntry
from validation.score import (
    _entered_accepts,
    _profile_accepts,
    interval_facts,
    measurement_set,
    region_excess,
    score,
    score_replicates,
)


def interval(low: float, high: float, split: bool = False) -> KaInterval:
    """A closed interval of the given edges."""
    return KaInterval(low=low, high=high, open_low=False, open_high=False, level=0.95, dof=8, split=split)


def test_a_connected_interval_covers_what_lies_between_its_edges():
    """The plain case: the accepted Ka are one stretch, so the edges answer it."""
    facts = interval_facts(interval(1e5, 1e7), truth=1e6, estimate=2e6)
    assert facts['covers'] is True
    assert facts['split'] is False
    assert facts['width'] == 2.0
    assert interval_facts(interval(1e5, 1e7), truth=1e8, estimate=2e6)['covers'] is False


def test_a_truth_in_a_split_interval_s_rejected_gap_is_not_covered():
    """The edges of a split interval span Ka the fit rejects; counting them would inflate coverage."""
    rejected = interval_facts(interval(1e5, 1e7, split=True), 1e6, 2e6, accepts=lambda ka: ka > 5e6)
    accepted = interval_facts(interval(1e5, 1e7, split=True), 1e6, 2e6, accepts=lambda ka: ka < 5e6)
    assert rejected['covers'] is False
    assert accepted['covers'] is True
    assert rejected['split'] is True


def test_a_truth_outside_a_split_interval_stays_outside_it():
    """The gap test refines what the edges enclose; it cannot pull in a Ka they never reached."""
    facts = interval_facts(interval(1e5, 1e7, split=True), 1e9, 2e6, accepts=lambda ka: True)
    assert facts['covers'] is False


def test_the_profile_decides_between_its_nodes_and_not_only_on_them():
    """A Ka between two nodes is accepted when the line joining them stays under the threshold."""
    profile = SimpleNamespace(
        grid=np.array([1e4, 1e6, 1e8]),
        objective=np.array([10.0, 0.0, 10.0]),
        threshold=5.0,
    )
    accepts = _profile_accepts(profile)
    assert accepts(1e6) is True
    assert accepts(10**5.0) is True  # halfway in log Ka: the interpolated value is 5.0
    assert accepts(10**4.5) is False
    assert accepts(1e2) is False, 'a Ka past the grid is not something the profile accepted'


def test_a_ka_the_model_could_not_be_solved_at_is_not_accepted():
    """An infinite profile value is the model failing, which is no evidence that the Ka fits."""
    profile = SimpleNamespace(grid=np.array([1e4, 1e6]), objective=np.array([np.inf, 0.0]), threshold=5.0)
    assert _profile_accepts(profile)(10**5.0) is False


#: A two-step titration whose conditional interval of the second binding
#: constant is split: the fit at some Ka inside it holds a signal coefficient on
#: its bound that the best fit leaves free, so the cut-off steps up there and the
#: interval accepts Ka the flat cut-off of the best fit would reject. Only a model
#: with two binding constants counts such a coefficient, so only its cut-off steps.
SPLIT = Scenario(assay='DBA_H2G', regime=1000.0, n_points=12, noise=0.005)
SPLIT_SEED = 6
SPLIT_KEY = 'Ka_H2G'


def test_a_split_conditional_interval_is_scored_against_the_cut_off_it_was_cut_with():
    """A Ka inside a split interval is covered exactly where the engine's own test accepts it.

    The engine judges each Ka against the cut-off of its own profile point's
    fit, which in a model with two binding constants steps up wherever that
    fit holds a coefficient on a bound the best fit leaves free. A
    scorer judging every Ka against the best fit's flat cut-off would count a
    truth the interval accepts as missed.
    """
    data = dataset(SPLIT, SPLIT_SEED)
    result = fit_measurement_set(
        measurement_set(data),
        ASSAY_CLASSES[AssayType[SPLIT.assay]],
        dict(data.conditions),
        FitConfig(per_replica=False, errors=SPLIT.error_model),
    )
    interval = result.conditional.intervals[SPLIT_KEY]
    assert interval.split, 'the case has to be split for this to say anything'
    projection = Projection(data.assay, data.assay.get_default_bounds(), point_weights=result.point_weights)
    fit = projection.fit()
    cut = projection.cut_off(fit, inflation=interval.inflation)
    flat = projection.threshold(fit, inflation=interval.inflation)
    accepts = _entered_accepts(data, result)(SPLIT_KEY)
    stepped = 0
    for ka in np.geomspace(interval.low, interval.high, 60):
        _, value, fitted = projection.profile_point(SPLIT_KEY, float(ka))
        engine = bool(value <= cut(fitted))
        stepped += engine and value > flat
        assert accepts(float(ka)) is engine, ka
    assert stepped, 'some Ka has to be accepted only past a step of the cut-off for this to say anything'


def region(threshold: float) -> JointRegion:
    """A region whose surface falls off from a ridge along the first axis."""
    x = np.geomspace(1e4, 1e8, 5)
    y = np.geomspace(1e4, 1e8, 5)
    r2 = np.array([[1.0 - abs(i - j) / 10 for j in range(5)] for i in range(5)])
    return JointRegion(
        ka_keys=('Ka_HG', 'Ka_HG2'), x=x, y=y, r2=r2, r2_threshold=threshold, level=0.95, best=(1e6, 1e6)
    )


def test_a_pair_is_read_off_the_surface_the_region_is_drawn_from():
    """The check has to answer the question the tab's region answers: residual over cut-off, cell by cell."""
    drawn = region(0.95)
    assert region_excess(drawn, (1e6, 1e6)) == 0.0
    assert region_excess(drawn, (1e8, 1e4)) == pytest.approx((4 / 10) / 0.05)
    # Halfway between two nodes in each direction, bilinearly.
    assert region_excess(drawn, (10**5.0, 10**5.0)) == 0.0


def test_a_cell_is_judged_against_its_own_cut_off():
    """Where a signal parameter is given up the cut-off steps down in R²; the same residual is then inside."""
    drawn = region(0.95)
    assert region_excess(drawn, (1e7, 1e6)) == pytest.approx(0.1 / 0.05)
    drawn.r2_cut[:] = 0.8
    assert region_excess(drawn, (1e7, 1e6)) == pytest.approx(0.1 / 0.2)


def test_a_pair_outside_the_region_s_box_is_outside_the_region():
    """The box is the two intervals clipped to the Ka bounds; the tab draws nothing past it."""
    drawn = region(0.95)
    assert np.isnan(region_excess(drawn, (1e9, 1e6)))
    assert np.isnan(region_excess(drawn, (1e6, 1e2)))


def test_a_cell_the_model_could_not_be_solved_in_is_outside_the_region():
    """The tab draws no contour through a hole in the surface, so neither may the check."""
    drawn = region(0.95)
    drawn.r2[2, 2] = np.nan
    assert np.isnan(region_excess(drawn, (1e6, 1e6)))


#: The smallest design of each new kind of scenario: a titration whose totals
#: the titrant dilutes with the stock declared, the same one fitted without it,
#: and a titration whose concentrations share one stock error. Eight points is
#: the shortest design any grid runs, which keeps the three fits of this test
#: inside the fast layer.
NEW_SCENARIOS = {
    'declared': Scenario(assay='DBA_DtoH', regime=10.0, n_points=8, noise=0.005, dilution=(0.02, 0.2)),
    'ignored': Scenario(
        assay='DBA_DtoH', regime=10.0, n_points=8, noise=0.005, dilution=(0.02, 0.2), declare_stock=False
    ),
    'shared': Scenario(
        assay='DBA_DtoH',
        regime=10.0,
        n_points=8,
        noise=0.005,
        specs=(SpecEntry('fixed_conc', sigma=3.0), SpecEntry(TITRANT, sigma=3.0)),
        shared_sources=(SharedEntry('Stock', 4.0, ('fixed_conc', TITRANT)),),
    ),
}


@pytest.mark.parametrize('kind', sorted(NEW_SCENARIOS))
def test_a_row_of_each_new_scenario_carries_what_its_check_reads(kind):
    """A check renders nothing from a row whose fields are missing, and stores the failure as a fit that broke."""
    row = score(NEW_SCENARIOS[kind], 0)
    assert row['refused'] is None and row['error'] is None
    assert set(row['aware']) == {'Ka_dye'} == set(row['cond']) == set(row['err'])
    assert row['aware']['Ka_dye']['covers'] in (True, False)
    assert np.isfinite(row['err']['Ka_dye'])
    assert row['t_fit'] > 0


def test_a_scenario_of_an_older_grid_stores_the_fields_its_rows_already_hold():
    """A field added to every row would differ from the rows the guard compares against."""
    row = score(Scenario(assay='DBA_DtoH', regime=10.0, n_points=8, noise=0.005), 0)
    assert 'err' not in row
    assert row['refused'] is None and row['error'] is None


def test_declaring_the_stock_is_what_puts_the_estimate_on_the_truth():
    """The dilution-ignored rows are only worth reading if the declared fit is the one that recovers Ka."""
    declared = score(NEW_SCENARIOS['declared'], 0)
    ignored = score(NEW_SCENARIOS['ignored'], 0)
    assert abs(declared['err']['Ka_dye']) < 0.05
    assert abs(ignored['err']['Ka_dye']) > 5 * abs(declared['err']['Ka_dye'])


#: A replicated titration whose noise grows with the signal, and the same
#: design measured once. Eight points keeps both fits in the fast layer.
REPLICATED = Scenario(assay='GDA', regime=10.0, n_points=8, noise=0.02, proportional=True, replicates=4)


def test_a_row_says_what_the_replicates_showed_about_the_noise():
    """Every rate the noise-law checks report is read beside this share; a row without it says nothing."""
    replicated = score(REPLICATED, 0)
    assert replicated['refused'] is None and replicated['error'] is None
    assert replicated['noise_basis'] == 'replicates'
    assert 0.0 <= replicated['noise_share'] <= 1.0
    # The scenario's noise grows with the signal, so the law should not read it
    # as flat; the share is what the weights are built from, and the weights
    # then differ along the titration.
    assert replicated['noise_share'] > 0.0
    assert replicated['weight_ratio'] > 1.0
    # A share above zero is read again at the fitted curve of a first fit, and
    # the interval allows for every share the replicates leave possible.
    assert replicated['refit'] is True
    assert replicated['fit_weight_ratio'] > 1.0
    low, high = replicated['share_set']
    assert 0.0 <= low <= replicated['noise_share'] <= high <= 1.0
    assert replicated['cond']['Ka_guest']['inflation'] >= 1.0
    # A law read off the replicates is a law the F distribution does not
    # describe, so the misfit test's reference is the bootstrap.
    assert replicated['misfit_reference'] == 'bootstrap'


def test_a_single_titration_reports_that_its_noise_was_taken_as_constant():
    """One curve cannot show how the noise varies, and the row has to say so rather than leave it open."""
    row = score(replace_replicates(REPLICATED, 1), 0)
    assert row['refused'] is None and row['error'] is None
    assert row['noise_basis'] == 'single_titration'
    assert row['noise_share'] == 0.0
    assert row['weight_ratio'] == 1.0, 'weights of one are no weights, and their ratio is exactly one'
    assert row['fit_weight_ratio'] == 1.0 and row['refit'] is False
    assert row['share_set'] == [0.0, 0.0]
    # Nothing to widen for: no law, no stated addition, so the interval is today's.
    assert row['cond']['Ka_guest']['inflation'] == 1.0 == row['aware']['Ka_guest']['inflation']


def replace_replicates(scenario: Scenario, m: int) -> Scenario:
    """*scenario* measured *m* times."""
    from dataclasses import replace

    return replace(scenario, replicates=m)


#: One single titration, the kind every stored agreement row was computed from.
SINGLE = Scenario(assay='GDA', regime=10.0, n_points=8, noise=0.01)


def test_a_single_titration_agreement_row_is_the_unweighted_comparison():
    """A titration with no law behind it is fitted with weights of one, which is arithmetic unchanged.

    The row is computed against a projection and a reference that are handed no
    weights at all; equality has to be exact, since multiplying by one is the
    only thing the weighted path does more.
    """
    row = agreement_row(SINGLE, 0)
    data = dataset(SINGLE, 0)
    assert noise_law(data.signals).weights(data.signals[0]).tolist() == [1.0] * data.x.size
    projection = Projection(data.assay, data.assay.get_default_bounds())
    fit = projection.fit()
    key = projection.free_ka[0]
    interval = projection.interval(key, fit)
    low, high = reference_intervals(data.assay, data.signals, SINGLE.error_model, 0, SINGLE.id)[key]
    apart = max(abs(np.log10(low / interval.low)), abs(np.log10(high / interval.high)))
    assert row['apart'][key] == apart
    assert row['engine_width'][key] == float(np.log10(interval.high / interval.low))
    assert row['ref_width'][key] == float(np.log10(high / low))


#: A replicated titration whose law the reference and the engine both carry, and
#: along whose profile no signal parameter runs to a bound, so the cut-off is
#: the constant one on both sides and the weights are all the case asks about.
WEIGHTED = Scenario(assay='IDA', regime=1000.0, n_points=12, noise=0.02, proportional=True, replicates=4)
WEIGHTED_SEED = 2


def test_the_weighted_reference_places_the_weighted_engine_s_edges():
    """Both carry the weights and the widening of the app's fit, so an edge that moved would be a defect in one of them."""
    data = dataset(WEIGHTED, WEIGHTED_SEED)
    result = fit_measurement_set(
        measurement_set(data), ASSAY_CLASSES[AssayType[WEIGHTED.assay]], dict(data.conditions), FitConfig()
    )
    weights = result.point_weights
    assert result.noise.estimated and result.noise.share > 0.0
    assert weights.max() / weights.min() > 3.0, 'the weights have to vary for this to say anything'
    projection = Projection(data.assay, data.assay.get_default_bounds(), point_weights=weights)
    fit = projection.fit()
    key = projection.free_ka[0]
    interval = result.conditional.intervals[key]
    ranks = {projection.fitted_parameters({key: ka}).rank for ka in (fit.ka[key], interval.low, interval.high)}
    assert len(ranks) == 1, 'the weights, and not a stepping cut-off, are what this case is about'
    row = agreement_row(WEIGHTED, WEIGHTED_SEED)
    assert row['agrees'] == {key: True}, row['apart']


#: A single GDA titration whose bounded solve gives one signal coefficient up
#: on the way to the high edge, and not on the way to the low one: I_dye_bound
#: reaches its lower bound of zero there.
STEPPED = Scenario(assay='GDA', regime=10.0, n_points=12, noise=0.01)
STEPPED_SEED = 1


def _bounded_solve(assay, y: np.ndarray, ka: float) -> tuple[float, np.ndarray, np.ndarray]:
    """The signal coefficients at one Ka by a hand-written bounded least squares.

    One column per signal parameter — a constant for the offset, the species it
    multiplies for the others — fitted inside the app's own bounds of ``0`` to
    infinity. Returns the residual sum of squares, the design and the mask of
    the coefficients the solve left strictly inside those bounds: a coefficient
    is on its bound when the curve it still contributes is a vanishing fraction
    of the signal.
    """
    species = assay.species(np.array([ka, 0.0, 0.0, 0.0]))
    design = np.column_stack([np.ones(y.size), species['D'], species['HD']])
    coefficients = lsq_linear(design, y, bounds=(0.0, np.inf)).x
    residual = design @ coefficients - y
    contribution = coefficients * np.linalg.norm(design, axis=0)
    return float(residual @ residual), design, contribution > 1e-8 * float(np.linalg.norm(y))


def _rank(columns: np.ndarray) -> int:
    """Rank of *columns* scaled to unit length, so a short column counts like a long one."""
    return int(np.linalg.matrix_rank(columns / np.linalg.norm(columns, axis=0)))


def test_the_reference_cuts_a_one_ka_profile_at_the_plain_f_test_where_its_fit_pins_a_coefficient():
    """Both edges are where the SSR crosses ``S_min (1 + F(1, nu)/nu)``.

    The fit at the high edge holds a signal parameter the best fit fits on its
    bound, and the low edge holds none; a model with one binding constant
    counts neither, so both edges lie on the one cut-off of the plain F test.
    """
    data = dataset(STEPPED, STEPPED_SEED)
    y = data.signals[0]
    best = minimize_scalar(lambda t: _bounded_solve(data.assay, y, 10.0**t)[0], bounds=(-8.0, 12.0), method='bounded')
    ssr_min, design, fitted = _bounded_solve(data.assay, y, 10.0**best.x)
    at_best = _rank(design[:, fitted])
    nu = y.size - 1 - at_best  # the free Ka and the rank of what the best fit fitted

    low, high = reference_intervals(data.assay, data.signals, STEPPED.error_model, STEPPED_SEED, STEPPED.id)['Ka_guest']
    given_up = {}
    for edge in (low, high):
        ssr, columns, fitted = _bounded_solve(data.assay, y, edge)
        given_up[edge] = at_best - _rank(columns[:, fitted])
        assert ssr / ssr_min == pytest.approx(1 + f_dist.ppf(0.95, 1, nu) / nu, rel=1e-9)
    assert (given_up[low], given_up[high]) == (0, 1), 'the case has to pin a coefficient at one edge only'


#: A GDA titration of the reference grid whose best fit holds the offset on its
#: bound of zero: the best fit fits two signal parameters of three.
HELD = Scenario(assay='GDA', regime=10.0, n_points=8, noise=0.01)
HELD_SEED = 2


def test_the_reference_counts_in_n_minus_p_only_what_its_best_fit_fitted():
    """A coefficient the best fit holds on its bound takes no dimension from the residual, so ``p`` leaves it out.

    ``nu = n - 1 - r(k_hat)`` with ``r`` the rank of the columns the best fit
    leaves strictly inside their bounds; counting the held offset would take
    one more degree of freedom than the residual gives up, and the cut-off of
    the eight-point titration would be read at ``nu = 4`` instead of 5.
    """
    data = dataset(HELD, HELD_SEED)
    y = data.signals[0]
    best = minimize_scalar(lambda t: _bounded_solve(data.assay, y, 10.0**t)[0], bounds=(-8.0, 12.0), method='bounded')
    ssr_min, design, fitted = _bounded_solve(data.assay, y, 10.0**best.x)
    assert not fitted.all(), 'the case has to hold a coefficient on its bound for this to say anything'
    at_best = _rank(design[:, fitted])
    assert at_best < _rank(design)
    nu = y.size - 1 - at_best

    high = reference_intervals(data.assay, data.signals, HELD.error_model, HELD_SEED, HELD.id)['Ka_guest'][1]
    assert high < reference.float_bounds(data.assay)['Ka_guest'][1], 'the high edge has to be closed'
    ssr = _bounded_solve(data.assay, y, high)[0]
    # Two minimisers of one SSR agree to about 1e-9; the two readings of nu are a third apart.
    assert ssr / ssr_min == pytest.approx(1 + f_dist.ppf(0.95, 1, nu) / nu, rel=1e-7)


#: A GDA titration of the reference grid whose best fit runs to the lower bound
#: of the Ka box while the data still close the interval above it.
AT_BOX = Scenario(assay='GDA', regime=0.1, n_points=8, noise=0.01)
AT_BOX_SEED = 30


def test_the_reference_counts_no_binding_constant_its_best_fit_left_on_a_bound_of_the_box():
    """A binding constant on the edge of its box is held there, like a coefficient on its bound.

    The fit does not place it, so ``nu = n - r(k_hat)`` with no binding
    constant in ``p``, while ``m`` still counts the tested one: the closed high
    edge is where the SSR crosses ``S_min (1 + F(1, nu) / nu)`` for that ``nu``.
    """
    data = dataset(AT_BOX, AT_BOX_SEED)
    y = data.signals[0]
    box = reference.float_bounds(data.assay)['Ka_guest']
    ssr_min, design, fitted = _bounded_solve(data.assay, y, box[0])
    at_best = _rank(design[:, fitted])
    nu = y.size - at_best

    low, high = reference_intervals(data.assay, data.signals, AT_BOX.error_model, AT_BOX_SEED, AT_BOX.id)['Ka_guest']
    assert low == box[0] and high < box[1], 'the case has to be open below and closed above for this to say anything'
    ssr = _bounded_solve(data.assay, y, high)[0]
    # Two minimisers of one SSR agree to about 1e-9; the two readings of nu are a third apart.
    assert ssr / ssr_min == pytest.approx(1 + f_dist.ppf(0.95, 1, nu) / nu, rel=1e-7)


def test_a_row_without_a_reference_carries_the_keys_of_the_question_it_was_asked(monkeypatch):
    """The metric of each row reads the same fields whether or not the reference converged."""
    monkeypatch.setattr(reference, 'reference_intervals', lambda *args, **kwargs: None)
    pooled = pooling_row(REPLICATED, 0)
    assert pooled['no_reference'] is True and pooled['error'] is None
    assert {'ref_covers', 'engine_covers', 'equal_covers', 'ref_width', 'engine_width', 'equal_width'} <= set(pooled)
    assert 'agrees' not in pooled
    assert checks.pooling({**pooled, 'case': REPLICATED.id}) == {'~no_reference': True}
    agreement = agreement_row(SINGLE, 0)
    assert agreement['no_reference'] is True and agreement['agrees'] == agreement['apart'] == {}
    assert 'equal_covers' not in agreement


def test_a_pooling_row_carries_the_three_intervals_its_table_reads():
    """The table sets pooling against averaging and weighting against equal weights, all on one dataset."""
    row = pooling_row(REPLICATED, 0)
    assert row['refused'] is None and row['error'] is None
    assert set(row['engine_covers']) == set(row['ref_covers']) == set(row['equal_covers'])
    for key, width in row['engine_width'].items():
        assert width > 0 and row['ref_width'][key] > 0 and row['equal_width'][key] > 0
        assert isinstance(row['equal_covers'][key], bool)
    # The weighted fit of the average and the unweighted one are different
    # fits wherever the replicates showed a law.
    assert noise_law(dataset(REPLICATED, 0).signals).share > 0.0
    assert row['engine_width'] != row['equal_width']


def test_a_row_of_stated_inputs_carries_the_standard_score_each_entry_was_drawn_at():
    """Coverage read by how far the entries were off needs the true entry errors on the row, not the fitted shifts."""
    scenario = Scenario(
        assay='DBA_DtoH',
        regime=10.0,
        n_points=8,
        noise=0.005,
        specs=(SpecEntry('fixed_conc', sigma=3.0), SpecEntry(TITRANT, sigma=3.0)),
    )
    row = score(scenario, 0)
    assert row['z_true'] == pytest.approx(dataset(scenario, 0).entry_z)
    assert set(row['z_true']) == {'fixed_conc', TITRANT}
    assert 'z_true' not in score(Scenario(assay='DBA_DtoH', regime=10.0, n_points=8, noise=0.005), 0)


def test_the_reported_coverage_is_read_by_the_largest_entry_error_and_never_judged():
    """The level is an average over the entry errors; how it varies with them is described beside it."""
    facts = {'covers': False, 'open': False, 'split': False, 'limited': False, 'width': 0.3}
    metrics = checks.coverage_by_entry_error({'aware': {'Ka_dye': facts}, 'z_true': {'fixed_conc': -2.7, 'x': 0.4}})
    assert metrics == {'~cov_zmax_2.5+.Ka_dye': False}
    near = checks.coverage_by_entry_error({'aware': {'Ka_dye': {**facts, 'covers': True}}, 'z_true': {'a': 0.3}})
    assert near == {'~cov_zmax_0-1.Ka_dye': True}
    assert checks.coverage_by_entry_error({'aware': {'Ka_dye': facts}}) == {}


#: Five replicates of a strong direct binding, the last two measured at three
#: times the true Ka, twelve points: the smallest set the replicate test can
#: hold a minority against, kept in the fast layer.
SHIFTED = Scenario(
    assay='DBA_HtoD', regime=1000.0, n_points=12, noise=0.01, replicates=5, shifted_replicates=2, replicate_shift=3.0
)


def test_a_replicate_row_names_the_replicates_the_fit_left_out_and_the_ones_that_departed():
    """The exclusion rates are counts of these two lists, so both have to come from the fit and the scenario."""
    row = score_replicates(SHIFTED, 0)
    assert row['refused'] is None and row['error'] is None
    assert row['departed'] == ['r3', 'r4']
    assert set(row['excluded']) <= {'r0', 'r1', 'r2', 'r3', 'r4'}
    assert set(row['aware']) == {'Ka_dye'}
    assert row['replicates'] == 5


def test_the_replicate_metrics_count_a_fit_that_lost_a_clean_replicate_once():
    """The judged rate is per fit, so a fit that lost two clean replicates is one false exclusion, not two."""
    facts = {'covers': True, 'open': False, 'split': False, 'limited': False, 'width': 0.3}
    row = {'replicates': 5, 'departed': ['r4'], 'excluded': ['r0', 'r1'], 'aware': {'Ka_dye': facts}}
    metrics = checks.replicate_exclusion(row)
    assert metrics['clean_excluded'] is True
    assert metrics['~clean_excluded_share'] == pytest.approx(0.5)
    assert metrics['~departed_excluded'] is False
    assert metrics['~departed_excluded_share'] == 0.0
    assert metrics['~cov.Ka_dye'] is True
    clean = checks.replicate_exclusion({**row, 'departed': [], 'excluded': []})
    assert clean['clean_excluded'] is False and clean['~departed_excluded'] is None


def test_a_verdict_that_blames_the_model_the_inputs_or_both_is_a_false_alarm_on_good_data():
    """The judged rate is the family-wise error of the verdict's tests, so every verdict that blames counts.

    Blaming both at once is the outcome where both tests reject; leaving it out
    would hide exactly the draws in which the two errors coincide. The inputs
    explaining a misfit is a finding about the entries, not an alarm.
    """
    blamed = {'model_inadequate', 'inputs_conflict', 'model_and_inputs'}
    for verdict in (*blamed, 'consistent', 'inputs_explain'):
        assert checks.false_alarm({'verdict': verdict})['alarm'] is (verdict in blamed)
    assert checks.false_alarm({'verdict': None}) == {'alarm': None}
    assert checks.CHECKS['verdict-false-alarm'].criterion is checks.NULL_RATE


def test_an_interval_s_facts_carry_its_one_step_p_value_and_whether_its_lower_side_is_open():
    """The one-step rule opens the lower side of a second constant; a row that lost either fact cannot show it."""
    second = SimpleNamespace(
        low=1e-8,
        high=1e3,
        open_low=True,
        open_high=False,
        split=False,
        limited_by_low='',
        limited_by_high='',
        one_step_p=0.3,
        inflation=1.0,
    )
    facts = interval_facts(second, truth=1.0, estimate=10.0)
    assert facts['one_step_p'] == 0.3
    assert facts['open_low'] is True and facts['open'] is True
    closed = interval_facts(interval(1e5, 1e7), truth=1e6, estimate=2e6)
    assert closed['open_low'] is False and closed['one_step_p'] is None
    missing = interval_facts(None, truth=1.0, estimate=10.0)
    assert missing['open_low'] is None and missing['one_step_p'] is None


def test_an_interval_s_facts_carry_the_factor_its_cut_off_was_widened_by():
    """What a widened interval costs is read off this factor; a row without it cannot say why an interval is wide."""
    widened = KaInterval(low=1e5, high=1e7, open_low=False, open_high=False, level=0.95, dof=8, inflation=2.5)
    assert interval_facts(widened, truth=1e6, estimate=2e6)['inflation'] == 2.5
    assert interval_facts(interval(1e5, 1e7), truth=1e6, estimate=2e6)['inflation'] == 1.0
    assert interval_facts(None, truth=1.0, estimate=10.0)['inflation'] is None


#: A two-step titration whose second step is absent: the second constant is a
#: millionth of the first. Twelve points of one titration keeps it in the fast
#: layer.
ONE_STEP = Scenario(assay='DBA_HG2', regime=1.0, n_points=12, noise=0.01, k_ratio=1e6)


def test_a_two_step_row_carries_the_one_step_p_value_of_the_second_constant_alone():
    """The pretest is of the second step; the first constant has none, on either interval."""
    row = score(ONE_STEP, 0)
    assert row['refused'] is None and row['error'] is None
    for field in ('cond', 'aware'):
        assert row[field]['Ka_HG']['one_step_p'] is None
        p = row[field]['Ka_HG2']['one_step_p']
        assert 0.0 <= p <= 1.0
    metrics = checks.CHECKS['one-step-null'].metrics(row)
    assert set(metrics) >= {'closed_low.Ka_HG2'}
    assert not any(series.endswith('.Ka_HG') for series in metrics)


def facts(
    covers: bool, open_: bool, open_low: bool | None = None, one_step_p: float | None = None, low: float = 1.0
) -> dict:
    """The facts of one interval as a row stores them."""
    return {
        'covers': covers,
        'open': open_,
        'open_low': open_ if open_low is None else open_low,
        'split': False,
        'limited': False,
        'width': 1.0,
        'low': low,
        'one_step_p': one_step_p,
    }


def test_a_closed_interval_that_misses_the_truth_is_counted_over_every_fit():
    """The false-closure rate is per fit: closed and wrong, over all draws, beside the coverage of the closed ones."""
    truth = {'Ka_HG2': 1.0}
    metrics = [
        checks.closed_coverage({'truth': truth, 'cond': {'Ka_HG2': facts(covers, open_)}})['~false_closed.Ka_HG2']
        for covers, open_ in ((False, False), (True, False), (False, True), (True, True))
    ]
    assert metrics == [True, False, False, False]
    none = {'truth': truth, 'cond': {'Ka_HG2': {**facts(False, False), 'covers': None}}}
    assert checks.closed_coverage(none)['~false_closed.Ka_HG2'] is None


def test_a_closed_lower_edge_of_the_second_constant_above_the_truth_is_counted_whatever_the_upper_side_does():
    """Open above and closed below a decade over the truth claims a second step that strong: a false closure too."""
    truth = {'Ka_HG': 1e5, 'Ka_HG2': 10.0}
    cases = (
        ({'open_low': False, 'low': 100.0}, True),  # runs to the upper bound, lower edge a decade too high
        ({'open_low': False, 'low': 1.0}, False),  # lower edge below the truth
        ({'open_low': True, 'low': 1e-8}, False),  # open below: no claim
    )
    for lower, expected in cases:
        row = {
            'truth': truth,
            'cond': {'Ka_HG': facts(True, False), 'Ka_HG2': {**facts(lower['low'] <= 10.0, True), **lower}},
        }
        metrics = checks.closed_coverage(row)
        assert metrics['~false_closed_low.Ka_HG2'] is expected
        assert metrics['~false_closed.Ka_HG2'] is False, 'open above, so the two-sided series does not count it'
        assert '~false_closed_low.Ka_HG' not in metrics, 'the first constant makes no claim about a second step'


def test_the_one_step_null_judges_a_second_constant_closed_below():
    """On data with no second step, a lower edge is a claim that the step is there; the first constant is not asked."""
    row = {
        'aware': {
            'Ka_HG': facts(True, False),
            'Ka_H2G': facts(True, True, open_low=False, one_step_p=0.001),
        }
    }
    metrics = checks.CHECKS['one-step-null'].metrics(row)
    assert metrics['closed_low.Ka_H2G'] is True
    assert metrics['~one_step_p.Ka_H2G'] == 0.001
    assert not any(series.endswith('.Ka_HG') for series in metrics)
    opened = {'aware': {'Ka_H2G': facts(True, True, open_low=True, one_step_p=0.4)}}
    assert checks.CHECKS['one-step-null'].metrics(opened)['closed_low.Ka_H2G'] is False


def test_the_one_step_null_is_held_to_bradley_s_upper_limit_of_the_test_s_level():
    """Half a percent is the level; 1.5 times it is the limit, judged with the exact limits of the observed rate."""
    from core.pipeline.varpro import SECOND_STEP_LEVEL

    criterion = checks.CHECKS['one-step-null'].criterion
    assert criterion.nominal == pytest.approx(1.5 * SECOND_STEP_LEVEL)
    assert criterion.verdict(0, 1000) == 'pass'
    # No closure in 400 draws still leaves an exact upper limit of 0.0092.
    assert criterion.verdict(0, 400) == 'undecided'
    # 2 % of fits closed: the exact lower limit, 0.012, is past the limit.
    assert criterion.verdict(20, 1000) == 'fail'


def test_the_coverage_of_a_weighted_fit_is_split_by_how_far_its_weights_spread():
    """An estimated law that weights some points a thousand times others is where the interval undercovers."""
    for ratio, label in ((1.0, 'le10'), (10.0, 'le10'), (11.0, '10-1e3'), (1e3, '10-1e3'), (2e3, 'gt1e3')):
        row = {'cond': {'Ka_dye': facts(True, False)}, 'weight_ratio': ratio, 'noise_share': 0.5}
        metrics = checks.noise_law_conditional(row)
        split = {series for series in metrics if series.startswith('~cov_wratio_')}
        assert split == {f'~cov_wratio_{label}.Ka_dye'}, ratio
        assert metrics['~weight_ratio'] == ratio
