"""A scenario's id is its identity, and a check's cases are addressable by it.

The store keys every row by ``(case id, seed)``. If two different scenarios
could ever produce one id, rows of one would be read as rows of the other and a
coverage rate would silently mix two different titrations.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from validation import scenarios
from validation.checks import CHECKS, case_by_id
from validation.scenarios import Scenario, SpecEntry, all_scenarios, owner_grid, stated_specs


def test_an_id_names_exactly_one_scenario():
    """Across every named grid, two scenarios with the same id are the same scenario."""
    seen: dict[str, Scenario] = {}
    for scenario in all_scenarios():
        other = seen.setdefault(scenario.id, scenario)
        assert other == scenario, f'{scenario.id} names both {other} and {scenario}'


def test_every_case_of_a_check_has_its_own_id():
    """Within a check the ids are the store's primary key, so no case may repeat one."""
    for name, check in CHECKS.items():
        ids = [case.id for case in check.cases]
        assert len(ids) == len(set(ids)), f'{name} has repeated case ids'
        assert len(case_by_id(check)) == len(check.cases)


def test_a_field_that_changes_the_data_changes_the_id():
    """Every field a dataset depends on reaches the id, so two families cannot share a key."""
    base = owner_grid()[0]
    for field, value in (
        ('regime', 3.0),
        ('n_points', 7),
        ('noise', 0.02),
        ('proportional', True),
        ('replicates', 4),
        ('ratio', 10.0),
        ('titrant_span', 4.0),
        ('i0', True),
        ('dark_free_dye', True),
        ('misfit_sine', 0.02),
        ('titrant_error', 0.15),
    ):
        changed = replace(base, **{field: value})
        assert changed.id != base.id, f'{field} does not reach the id'


def test_the_stated_specs_and_an_entry_multiple_reach_the_id():
    """A grid run at several entry multiples keeps one family of rows per multiple."""
    base = owner_grid()[0]
    stated = replace(base, specs=stated_specs(base.assay))
    assert stated.id != base.id
    assert replace(stated, entry_multiple=3.0).id != stated.id
    other = replace(base, specs=(SpecEntry('h0', sigma=1.0),))
    assert other.id != stated.id


def test_the_conflict_rates_are_measured_on_one_grid():
    """A power curve whose null rate comes from another population of titrations is not a curve."""
    null = {case.id for case in CHECKS['conflict-null'].cases}
    designs = {case.data_id for case in CHECKS['conflict-power'].cases}
    assert null, 'conflict-null names no cases'
    assert {case.data_id for case in CHECKS['conflict-null'].cases} == designs


def test_a_scenario_refuses_an_input_its_assay_does_not_have():
    """A spec on an input the assay never receives would be silently ignored by the fit."""
    with pytest.raises(ValueError, match='has no input'):
        Scenario(assay='DBA_HtoD', specs=(SpecEntry('h0', sigma=3.0),))


def test_every_check_either_runs_cases_or_reads_another_checks_rows():
    """A check with neither would render an empty table for a claim nobody computes.

    A check that reads another's rows may name the cases of that grid its claim
    is about; naming a case the other check never runs would leave the claim
    resting on rows that never arrive.
    """
    for name, check in CHECKS.items():
        if check.derived_from is None:
            assert check.cases and check.row is not None, f'{name} has no cases to run'
        else:
            assert check.derived_from in CHECKS, f'{name} reads an unknown check'
            assert check.row is None, f'{name} reads {check.derived_from} and would also compute rows'
            parent = {case.id for case in CHECKS[check.derived_from].cases}
            named = {case.id for case in check.cases}
            assert named <= parent, f'{name} names cases {check.derived_from} never runs: {sorted(named - parent)}'
        if check.criterion is not None:
            assert check.criterion_reason, f'{name} states a criterion with no justification'


#: How many scenarios each named grid holds and the id of its first, as the
#: store already keys its rows. A scenario that starts writing a field into an
#: id it was not in before orphans every row of that grid, and the rows of a
#: coverage rate are hours of fits.
GRID_IDS: dict[str, tuple[int, str]] = {
    'owner_grid': (180, 'GDA,K=0.1,n=5,noise=0.005'),
    'two_ka_weak_grid': (108, 'DBA_HG2,K=0.3,n=12,noise=0.005,kr=10'),
    'input_aware_grid': (144, 'GDA,K=0.1,n=8,noise=0.005,sig'),
    'range_spec_grid': (36, 'GDA,K=0.1,n=12,noise=0.01,spec(Ka_dye=-20:20/h0=-5:5)'),
    'lof_null_grid': (72, 'GDA,K=0.1,n=8,noise=0.01,m=2,sig'),
    'runs_null_grid': (48, 'GDA,K=0.1,n=8,noise=0.01,sig'),
    'misfit_power_grid': (84, 'GDA,K=0.1,n=12,noise=0.01,m=4,sine=0.02,sig'),
    'robustness_grid': (66, 'GDA,K=0.1,n=12,noise=0.005,sig,ent=0.5'),
    'robustness_strained_grid': (72, 'GDA,K=0.1,n=12,noise=0.005,sig,ent=2'),
    'reference_grid': (36, 'GDA,K=0.1,n=8,noise=0.01'),
    'pooling_grid': (36, 'GDA,K=0.1,n=12,noise=0.02,m=4'),
    'joint_grid': (48, 'DBA_HG2,K=0.3,n=12,noise=0.01,kr=10'),
    'before_after_grid': (72, 'GDA,K=0.1,n=8,noise=0.005'),
}


def test_every_named_grid_keeps_the_ids_its_rows_are_stored_under():
    """A grid's rows are addressed by these strings; a scenario field that leaked into one loses them."""
    for name, (size, first) in GRID_IDS.items():
        grid = getattr(scenarios, name)()
        assert len(grid) == size, f'{name} holds {len(grid)} scenarios'
        assert grid[0].id == first, f'{name} now starts at {grid[0].id}'
    assert scenarios.conflict_grid((1.0,))[0].id == 'GDA,K=0.1,n=8,noise=0.005,sig'
    assert scenarios.conflict_grid((2.0,))[0].id == 'GDA,K=0.1,n=8,noise=0.005,sig,ent=2'


def test_the_dilution_of_a_titration_reaches_the_key_its_measurements_hang_on():
    """The stock changes what was measured, so two dilutions may not share a dataset."""
    base = scenarios.Scenario(assay='IDA')
    diluted = replace(base, dilution=(0.02, 0.2))
    assert diluted.data_id != base.data_id
    assert replace(diluted, dilution=(0.05, 0.1)).data_id != diluted.data_id
    assert replace(diluted, stock_contains=('d0',)).data_id != diluted.data_id


def test_leaving_the_stock_undeclared_keeps_the_titration_and_changes_the_fit():
    """The ignored-dilution rows are the declared rows' own measurements, fitted differently."""
    diluted = scenarios.Scenario(assay='IDA', dilution=(0.02, 0.2))
    ignored = replace(diluted, declare_stock=False)
    assert ignored.data_id == diluted.data_id
    assert ignored.entry_id == diluted.entry_id
    assert ignored.id != diluted.id
    assert ignored.id.endswith('nostock')


def test_a_shared_source_reaches_the_entry_stream_and_the_row_key():
    """A source drawn into the entries is part of what was entered, not only of what was stated."""
    stated = scenarios.Scenario(assay='IDA', specs=stated_specs('IDA'))
    shared = replace(stated, shared_sources=(scenarios.SharedEntry('Stock', 4.0, ('h0', 'd0')),))
    assert shared.data_id == stated.data_id
    assert shared.entry_id != stated.entry_id
    assert shared.id != stated.id
    assert replace(shared, shared_sources=(scenarios.SharedEntry('Stock', 5.0, ('h0', 'd0')),)).id != shared.id


def test_the_error_model_carries_the_specs_and_the_shared_sources_the_scenario_states():
    """The fit and the sensitivity analysis are told exactly the model the entries were drawn from."""
    scenario = scenarios.Scenario(
        assay='IDA',
        specs=(SpecEntry('h0', sigma=3.0),),
        shared_sources=(scenarios.SharedEntry('Stock', 4.0, ('h0', 'd0')),),
    )
    errors = scenario.error_model
    assert set(errors.specs) == {'h0'}
    assert [(s.name, s.sigma_pct, s.inputs) for s in errors.shared] == [('Stock', 4.0, ('h0', 'd0'))]
    assert errors.loaded('shared:Stock') == ('h0', 'd0')


def test_a_scenario_refuses_a_shared_source_it_cannot_carry():
    """A source on an input the assay never receives, or on one input, would be silently dropped by the fit."""
    with pytest.raises(ValueError, match='does not have'):
        scenarios.Scenario(assay='DBA_HtoD', shared_sources=(scenarios.SharedEntry('S', 4.0, ('h0', 'd0')),))
    with pytest.raises(ValueError, match='fewer than two inputs'):
        scenarios.Scenario(assay='DBA_HtoD', shared_sources=(scenarios.SharedEntry('S', 4.0, ('fixed_conc',)),))


def test_a_scenario_refuses_a_stock_that_says_nothing():
    """A stock carrying every fixed total, or one with no dilution behind it, is the constant case spelled oddly."""
    with pytest.raises(ValueError, match='dilutes nothing'):
        scenarios.Scenario(assay='IDA', dilution=(0.02, 0.2), stock_contains=('h0', 'd0'))
    with pytest.raises(ValueError, match='states a dilution'):
        scenarios.Scenario(assay='IDA', stock_contains=('d0',))
    with pytest.raises(ValueError, match='between 0 and 1'):
        scenarios.Scenario(assay='IDA', dilution=(0.02, 2.0))


def test_the_ignored_dilution_grid_fits_the_titrations_the_declared_grid_measures():
    """The cost of leaving the stock out is only readable off the same measurements."""
    declared = {case.data_id for case in scenarios.dilution_grid()}
    ignored = {case.data_id for case in scenarios.dilution_ignored_grid()}
    assert ignored
    assert ignored <= declared
    assert all(not case.declare_stock for case in scenarios.dilution_ignored_grid())


def test_every_shared_source_case_states_the_same_model_the_entries_come_from():
    """The claim is about a fit told the truth about its inputs; a grid that stated less would test nothing."""
    for case in scenarios.shared_source_grid():
        source = case.shared_sources[0]
        assert source.keys == scenarios.concentration_inputs(case.assay)
        assert len(source.keys) >= 2
        assert case.specs == stated_specs(case.assay)


def test_the_independent_reference_refuses_a_scenario_it_cannot_answer_for():
    """The reference moves each input on its own, so a source two inputs share is outside the model it solves.

    Every grid it runs on states none. One that did would stop the run, rather
    than report a disagreement that is a gap in the reference and not in the
    engine.
    """
    from core.pipeline.inputs import ErrorModel, SharedSource
    from validation.reference import reference_intervals

    assert all(not case.shared_sources for case in scenarios.reference_grid() + scenarios.pooling_grid())

    shared = ErrorModel(shared=(SharedSource('Host and dye stock', 4.0, ('h0', 'd0')),))
    with pytest.raises(ValueError, match='shared error source'):
        reference_intervals(None, None, shared, 0, 'reference-agreement')
