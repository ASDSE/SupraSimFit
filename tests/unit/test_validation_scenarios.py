"""A scenario's id is its identity, and a check's cases are addressable by it.

The store keys every row by ``(case id, seed)``. If two different scenarios
could ever produce one id, rows of one would be read as rows of the other and a
coverage rate would silently mix two different titrations.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

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
