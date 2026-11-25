"""Titrations whose every addition carries a random error, and the checks that read them.

A coverage rate for the addition error is only worth quoting if the data carry
exactly the error the scenario names: each replicate measured on its own true
titrant series, one error per addition, shared between replicates only where
they are repeated reads of one titration — and if what the fit is told is
independent of what was drawn, so an overstated or understated error is a
statement about the same measurements.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from validation import checks, scenarios
from validation.checks import CHECKS
from validation.criteria import COVERAGE, NULL_RATE
from validation.generate import dataset, stream_seed
from validation.scenarios import Scenario
from validation.score import score

#: A direct-binding titration without noise, so its signals are the model on
#: each replicate's own titrant series and nothing else.
SILENT = dict(assay='DBA_HtoD', regime=10.0, n_points=12, noise=0.0, replicates=3)


def dba_signal(data, x: np.ndarray, host: np.ndarray | float) -> np.ndarray:
    """The four-parameter signal of a host-to-dye titration at host totals *x* and dye total *host*.

    ``[HD]`` from the mass-balance quadratic, written so that no digits are
    lost where the binding is strong — a computation of its own, sharing
    nothing with the model code the generator calls.
    """
    ka = data.truth['Ka_dye']
    dye = np.broadcast_to(host, x.shape)
    b = ka * (x + dye) + 1.0
    bound = 2 * ka * x * dye / (b + np.sqrt(b**2 - 4 * ka**2 * x * dye))
    return data.truth['I0'] + data.truth['I_dye_free'] * (dye - bound) + data.truth['I_dye_bound'] * bound


def moved_series(x: np.ndarray, deltas: np.ndarray, sequential: bool, stock: float | None) -> np.ndarray:
    """The titrant series an error per addition leaves, written out from the volumes.

    Point i holds the cumulative stock volume ``w_i`` per sample volume —
    ``x_i`` itself when the titrant does not dilute, ``x_i / (c_T - x_i)``
    when it does. Added one after another, the volume of addition j comes out
    ``(w_j - w_{j-1})(1 + delta_j)`` and point i holds their sum up to i; a
    sample prepared on its own holds ``w_i (1 + delta_i)``.
    """
    w = x if stock is None else x / (stock - x)
    if sequential:
        moved = np.cumsum(np.diff(w, prepend=0.0) * (1.0 + deltas))
    else:
        moved = w * (1.0 + deltas)
    return moved if stock is None else stock * moved / (1.0 + moved)


@pytest.mark.parametrize('sequential', [True, False])
def test_each_replicate_is_measured_on_its_own_series_of_additions(sequential):
    """Separate titrations: every replicate its own errors, and its signal the model on the series they leave."""
    scenario = Scenario(additions=3.0, stated_additions=3.0, sequential=sequential, **SILENT)
    data = dataset(scenario, 4)
    assert not np.allclose(data.deltas[0], data.deltas[1]), 'separate titrations draw their own errors'
    for row in range(scenario.replicates):
        expected = moved_series(data.x, data.deltas[row], sequential, None)
        assert np.allclose(data.titrant[row], expected, rtol=1e-12, atol=0)
        assert np.allclose(data.signals[row], dba_signal(data, expected, data.fixed_conc), rtol=1e-10, atol=0)
    assert not np.allclose(data.signals[0], data.clean), 'an addition in error moves the signal off the plan'


def test_repeated_reads_of_one_titration_share_its_additions():
    """One titration read three times carries one set of errors, so its three signals are one curve."""
    scenario = Scenario(additions=3.0, repeated_reads=True, stated_additions=3.0, stated_repeated_reads=True, **SILENT)
    data = dataset(scenario, 4)
    assert np.array_equal(data.deltas, np.tile(data.deltas[0], (3, 1)))
    assert np.array_equal(data.signals, np.tile(data.signals[0], (3, 1)))
    assert np.allclose(data.titrant[0], moved_series(data.x, data.deltas[0], True, None), rtol=1e-12, atol=0)


def test_a_diluting_titrant_moves_the_series_and_dilutes_the_sample_by_the_volume_added():
    """With a stock, the error is in the volume added: the series and the dilution of the host both follow it."""
    scenario = Scenario(
        assay='DBA_DtoH', regime=10.0, n_points=12, noise=0.0, dilution=(0.02, 0.2), additions=3.0, stated_additions=3.0
    )
    data = dataset(scenario, 2)
    stock = float(data.conditions['titrant_stock'].to('M').magnitude)
    titrant = moved_series(data.x, data.deltas[0], True, stock)
    assert np.allclose(data.titrant[0], titrant, rtol=1e-12, atol=0)
    host = data.fixed_conc * (1.0 - titrant / stock)
    ka = data.truth['Ka_dye']
    b = ka * (titrant + host) + 1.0
    bound = 2 * ka * titrant * host / (b + np.sqrt(b**2 - 4 * ka**2 * titrant * host))
    expected = data.truth['I0'] + data.truth['I_dye_free'] * (titrant - bound) + data.truth['I_dye_bound'] * bound
    assert np.allclose(data.signals[0], expected, rtol=1e-10, atol=0)


def test_the_addition_errors_are_drawn_at_the_size_the_scenario_names():
    """Over many additions the errors scatter with the stated standard deviation, about zero."""
    scenario = Scenario(assay='GDA', n_points=30, replicates=8, additions=2.0, stated_additions=2.0)
    deltas = np.concatenate([dataset(scenario, seed).deltas.ravel() for seed in range(10)])
    assert deltas.size == 2400
    assert np.std(deltas) == pytest.approx(0.02, rel=0.06)
    assert abs(np.mean(deltas)) < 4 * 0.02 / np.sqrt(deltas.size)


def test_a_titration_without_addition_error_is_drawn_from_its_noise_stream_alone():
    """No addition error: every replicate on the planned series, the noise exactly its own stream's draws."""
    scenario = Scenario(assay='IDA', regime=10.0, n_points=12, noise=0.01, replicates=3)
    data = dataset(scenario, 5)
    assert not data.deltas.any()
    assert np.array_equal(data.titrant, np.tile(data.x, (3, 1)))
    noise = np.random.default_rng(stream_seed(scenario.data_id, 5).spawn(3)[1])
    expected = np.vstack([data.clean + data.noise_sigma * noise.standard_normal(12) for _ in range(3)])
    assert np.array_equal(data.signals, expected)


def test_what_the_fit_is_told_leaves_the_measurement_alone():
    """An understated error is a statement about the measurements a correctly stated twin was fitted to."""
    told = Scenario(assay='IDA', regime=10.0, n_points=12, noise=0.002, additions=3.0, stated_additions=3.0)
    understated = replace(told, stated_additions=1.0)
    assert understated.id != told.id and understated.data_id == told.data_id
    first, second = dataset(told, 3), dataset(understated, 3)
    assert np.array_equal(first.signals, second.signals)
    assert np.array_equal(first.deltas, second.deltas)


def test_what_is_drawn_keys_the_measurement_and_what_is_stated_keys_the_case():
    """Two titrations with different additions are different data; two statements of one are one measurement."""
    base = Scenario(assay='GDA', replicates=3, additions=3.0, stated_additions=3.0)
    for field, value in (('additions', 1.0), ('sequential', False), ('repeated_reads', True)):
        changed = replace(base, **{field: value})
        assert changed.data_id != base.data_id, f'{field} does not reach the key of the measurement'
    for field, value in (('stated_additions', 1.0), ('stated_repeated_reads', True)):
        changed = replace(base, **{field: value})
        assert changed.data_id == base.data_id and changed.id != base.id, field


def test_the_fit_is_told_the_addition_error_the_scenario_states_and_no_other():
    """What reaches the fit configuration is the statement, whatever the data carry."""
    stated = Scenario(
        assay='GDA',
        replicates=3,
        additions=3.0,
        repeated_reads=True,
        stated_additions=1.0,
        sequential=False,
    ).error_model.additions
    assert (stated.sigma_pct, stated.sequential, stated.separate_titrations) == (1.0, False, True)
    reads = Scenario(assay='GDA', replicates=3, stated_additions=3.0, stated_repeated_reads=True).error_model.additions
    assert reads.separate_titrations is False
    assert Scenario(assay='GDA', replicates=3, additions=3.0).error_model.additions is None


@pytest.mark.parametrize(
    'fields, message',
    [
        ({'additions': -1.0}, 'cannot be negative'),
        ({'sequential': False}, 'says nothing'),
        ({'additions': 3.0, 'repeated_reads': True}, 'two or more'),
        ({'replicates': 3, 'stated_repeated_reads': True}, 'two or more replicates'),
    ],
)
def test_an_addition_error_a_scenario_cannot_carry_is_refused(fields, message):
    """A field that would change nothing, or describe nothing, would give two ids one measurement."""
    with pytest.raises(ValueError, match=message):
        Scenario(assay='GDA', **fields)


def test_the_addition_checks_run_the_grid_their_claims_name():
    """Every assay, both ways of adding, both sizes, the designs, the dilution and the repeated reads it states."""
    check = CHECKS['addition-coverage']
    assert check.row is not None and check.criterion is COVERAGE
    grid = check.cases
    assert len(grid) <= 120
    one_ka = [case for case in grid if case.assay in scenarios.ONE_KA]
    assert {case.assay for case in one_ka} == {'GDA', 'IDA', 'DBA_HtoD', 'DBA_DtoH'}
    assert all(case.stated_additions == case.additions > 0 for case in grid), 'the null states what it draws'
    assert {(case.sequential, case.additions) for case in one_ka} == {(s, a) for s in (True, False) for a in (1, 3)}
    assert {case.n_points for case in one_ka} == {8, 12, 30}
    assert {case.replicates for case in one_ka} == {1, 3}
    assert {case.regime for case in one_ka} == {10.0, 1000.0}
    assert {(case.noise, case.proportional) for case in one_ka} == {(0.002, False), (0.005, False), (0.01, True)}
    assert {case.assay for case in one_ka if case.dilution is not None} == {'GDA', 'IDA', 'DBA_HtoD', 'DBA_DtoH'}
    reads = [case for case in grid if case.repeated_reads]
    assert reads and all(case.stated_repeated_reads and case.replicates == 3 for case in reads)
    assert {(case.assay, case.sequential, case.additions) for case in grid if case.assay in scenarios.TWO_KA} == {
        ('DBA_HG2', True, 3.0),
        ('DBA_H2G', True, 3.0),
    }

    misfit = CHECKS['addition-misfit-null']
    assert misfit.derived_from == 'addition-coverage' and misfit.criterion is NULL_RATE

    misstated = CHECKS['addition-misstated']
    assert misstated.criterion is None and misstated.row is not None
    kinds = {
        (case.additions, case.stated_additions, case.repeated_reads, case.stated_repeated_reads)
        for case in misstated.cases
    }
    assert kinds == {(0.0, 3.0, False, False), (3.0, 1.0, False, False), (3.0, 3.0, True, False)}
    paired = {case.data_id for case in grid}
    for case in misstated.cases:
        if case.additions:
            assert case.data_id in paired, f'{case.id} has no correctly stated twin on the same measurements'


def test_a_row_of_stated_additions_carries_the_factor_each_interval_was_widened_by():
    """The reported interval is widened by the stated additions and the one at the inputs as entered is not.

    One titration of eight points with additions of 3 % under noise of 0.2 %:
    the additions move the curve far more than the noise does, so the
    reported interval is wider than the conditional one and contains it.
    """
    scenario = Scenario(assay='DBA_HtoD', regime=10.0, n_points=8, noise=0.002, additions=3.0, stated_additions=3.0)
    row = score(scenario, 0)
    assert row['refused'] is None and row['error'] is None
    reported, entered = row['aware']['Ka_dye'], row['cond']['Ka_dye']
    assert entered['inflation'] == 1.0, 'one titration, no law: nothing widens the interval at the inputs as entered'
    assert reported['inflation'] > 1.0
    assert reported['low'] <= entered['low'] and reported['high'] >= entered['high']
    assert row['misfit_kind'] == 'runs'
    assert row['refit'] is False and row['share_set'] == [0.0, 0.0]


def facts(covers: bool, width: float, open_: bool = False, inflation: float = 1.0) -> dict:
    """The fields of one interval a metric reads."""
    return {
        'covers': covers,
        'width': width,
        'open': open_,
        'open_low': False,
        'split': False,
        'limited': False,
        'inflation': inflation,
    }


def test_the_reported_interval_is_judged_and_its_cost_reported_beside_it():
    """The widened interval is the claim; its factor and its width over the unwidened one say what it cost."""
    row = {
        'aware': {'Ka_dye': facts(True, 1.5, inflation=4.0)},
        'cond': {'Ka_dye': facts(False, 0.5)},
        'bound_active': False,
        'z': {},
    }
    metrics = checks.addition_coverage(row)
    assert metrics['cov.Ka_dye'] is True
    assert metrics['~cond_cov.Ka_dye'] is False
    assert metrics['~inflation.Ka_dye'] == 4.0
    assert metrics['~cond_inflation.Ka_dye'] == 1.0
    assert metrics['~width_ratio.Ka_dye'] == pytest.approx(3.0)
    # An open interval's width is the distance to the Ka bound, so no ratio is read from it.
    row['aware']['Ka_dye'] = facts(True, 6.0, open_=True, inflation=4.0)
    assert checks.addition_coverage(row)['~width_ratio.Ka_dye'] is None


def test_the_misfit_rate_is_named_by_the_test_that_ran():
    """A pooled row of the runs test and the lack-of-fit test together would be the rate of neither."""
    assert checks.addition_misfit({'misfit_kind': 'runs', 'misfit_p': 0.01}) == {'reject.runs': True}
    assert checks.addition_misfit({'misfit_kind': 'lack_of_fit', 'misfit_p': 0.5}) == {'reject.lack_of_fit': False}
    assert checks.addition_misfit({'misfit_kind': None}) == {}


def test_a_weighted_fit_reports_the_law_it_was_weighted_by():
    """The share range, the refit and both weight spreads stand beside the coverage of a weighted fit."""
    row = {
        'cond': {'Ka_dye': facts(True, 1.0, inflation=1.3)},
        'noise_share': 0.6,
        'share_set': [0.2, 0.9],
        'weight_ratio': 2e4,
        'fit_weight_ratio': 50.0,
        'refit': True,
    }
    metrics = checks.noise_law_conditional(row)
    assert metrics['~share_set_width'] == pytest.approx(0.7)
    assert metrics['~refit'] is True
    assert metrics['~inflation.Ka_dye'] == 1.3
    assert metrics['~fit_weight_ratio'] == 50.0
    # The bins are read at the means, where the law was read and the tail lies.
    assert metrics['~cov_wratio_gt1e3.Ka_dye'] is True
