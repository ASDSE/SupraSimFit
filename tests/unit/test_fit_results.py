"""What a results file holds, and the rows every display renders from."""

import json
import math
from dataclasses import replace

import numpy as np
import pytest

from core.pipeline.diagnostics import Conflict, FitDiagnostics, InputShift, MisfitTest, Verdict
from core.pipeline.fit_pipeline import (
    RESULT_FORMAT,
    ConditionalFit,
    FitConfig,
    FitResult,
    _config_to_dict,
    summarize_parameters,
)
from core.pipeline.inputs import TITRANT, AdditionError, ErrorModel, InputSpec, SharedSource, specs_to_dict
from core.pipeline.varpro import LEVEL, KaInterval
from core.units import Q_, Quantity

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _interval(low=1.4e6, high=1.6e6, **overrides) -> KaInterval:
    fields = dict(
        low=low, high=high, open_low=False, open_high=False, level=LEVEL, dof=26, split=False, unsolvable_low=False
    )
    fields.update(overrides)
    return KaInterval(**fields)


def _sample_fit_result(**overrides) -> FitResult:
    """A GDA fit as the pipeline builds one, with its interval and its degenerate rows."""
    defaults = dict(
        parameters={
            'Ka_guest': Q_(1.5e6, '1/M'),
            'I0': Q_(0.0, 'au'),
            'I_dye_free': Q_(5e7, 'au/M'),
            'I_dye_bound': Q_(3e8, 'au/M'),
        },
        rmse=42.0,
        r_squared=0.998,
        x_fit=Q_(np.linspace(0, 50e-6, 30), 'M'),
        y_fit=Q_(np.linspace(100, 3000, 30), 'au'),
        assay_type='GDA',
        model_name='equilibrium_4param',
        conditions={'Ka_dye': Q_(5e5, '1/M'), 'h0': Q_(10e-6, 'M'), 'g0': Q_(20e-6, 'M')},
        fit_config=_config_to_dict(FitConfig(per_replica=False)),
        measurement_set_id='abc123',
        source_file='data/GDA_system.txt',
        intervals={'Ka_guest': _interval()},
        degenerate_keys=('I0', 'I_dye_free', 'I_dye_bound'),
    )
    defaults.update(overrides)
    return FitResult(**defaults)


def _with_moved_inputs(**overrides) -> FitResult:
    """A fit whose inputs were free to move: its headline, the fit at the entered inputs, and the tests.

    The entered host concentration was too high, so the fit moved it down by
    5 % (half the 10 % stated for it) and reports a lower Ka than the entered
    inputs alone allow.
    """
    conditional = ConditionalFit(
        parameters={**_sample_fit_result().parameters, 'Ka_guest': Q_(1.5e6, '1/M')},
        intervals={'Ka_guest': _interval(1.4e6, 1.6e6)},
        rmse=51.0,
        r_squared=0.995,
    )
    defaults = dict(
        parameters={**_sample_fit_result().parameters, 'Ka_guest': Q_(1.2e6, '1/M')},
        intervals={'Ka_guest': _interval(1.0e6, 1.45e6, dof=25.4)},
        fit_config=_config_to_dict(
            FitConfig(
                per_replica=False,
                errors=ErrorModel(specs={'h0': InputSpec.sigma_pct(10), TITRANT: InputSpec.sigma_pct(3)}),
            )
        ),
        conditional=conditional,
        input_shifts={
            'h0': InputShift('h0', -0.05, -0.5, False),
            TITRANT: InputShift(TITRANT, 0.004, 0.13, False),
        },
        diagnostics=FitDiagnostics(
            conditional_misfit=MisfitTest('lack_of_fit', 14.9, 7.9e-08, dof=(9, 24)),
            misfit=MisfitTest('lack_of_fit', 0.8, 0.62, dof=(9, 24)),
            conflict=Conflict(0.74, 2, 0.52, (0.17, 0.99)),
            verdict=Verdict.INPUTS_EXPLAIN,
        ),
    )
    defaults.update(overrides)
    return _sample_fit_result(**defaults)


def _replica(replica_id: str, ka: float) -> FitResult:
    """One replicate's own fit, as a per-replicate result carries it."""
    base = _sample_fit_result(intervals=None, degenerate_keys=())
    return replace(
        base,
        parameters={**base.parameters, 'Ka_guest': Q_(ka, '1/M')},
        metadata={'replica_id': replica_id, 'active_replica_ids': [replica_id]},
    )


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


class TestSerialization:
    """to_dict / from_dict round-trip."""

    def test_to_dict_json_safe(self):
        """All values must be JSON-serializable."""
        d = _sample_fit_result().to_dict()
        json.dumps(d)  # must not raise

    def test_round_trip(self):
        """from_dict(to_dict(r)) reproduces r faithfully."""
        original = _sample_fit_result(
            replica_fits=[_replica('a', 1.4e6), _replica('b', 1.6e6)],
            metadata={'active_replica_ids': ['a', 'b'], 'replica_ids_fit': ['a', 'b']},
        )
        restored = FitResult.from_dict(json.loads(json.dumps(original.to_dict())))

        # Parameters round-trip as Quantities
        for k in original.parameters:
            assert restored.parameters[k].magnitude == pytest.approx(original.parameters[k].magnitude)
        assert restored.rmse == original.rmse
        assert restored.r_squared == original.r_squared
        assert restored.assay_type == original.assay_type
        assert restored.model_name == original.model_name
        # Conditions round-trip as Quantities with their units preserved.
        for k, v in original.conditions.items():
            rv = restored.conditions[k]
            assert isinstance(rv, Quantity), f'condition {k!r} lost its Quantity type'
            assert rv.magnitude == pytest.approx(v.magnitude)
            assert rv.units == v.units
        assert restored.fit_config == original.fit_config
        assert restored.measurement_set_id == original.measurement_set_id
        assert restored.source_file == original.source_file
        assert restored.id == original.id
        assert restored.timestamp == original.timestamp
        np.testing.assert_array_almost_equal(restored.x_fit.magnitude, original.x_fit.magnitude)
        np.testing.assert_array_almost_equal(restored.y_fit.magnitude, original.y_fit.magnitude)
        # The interval, the degenerate rows and every replicate's own fit come back too.
        assert restored.intervals == original.intervals
        assert restored.degenerate_keys == original.degenerate_keys
        assert [rf.metadata['replica_id'] for rf in restored.replica_fits] == ['a', 'b']
        assert [float(rf.parameters['Ka_guest'].magnitude) for rf in restored.replica_fits] == [1.4e6, 1.6e6]

    def test_the_file_names_its_layout(self):
        assert _sample_fit_result().to_dict()['format'] == RESULT_FORMAT

    def test_a_file_written_by_a_newer_version_is_refused_by_name(self):
        """Its layout is one this version cannot read, so it says so instead of guessing."""
        newer = _sample_fit_result().to_dict()
        newer['format'] = RESULT_FORMAT + 1

        with pytest.raises(ValueError, match='newer version'):
            FitResult.from_dict(newer)

    def test_every_interval_flag_survives_the_file(self):
        """An open, split or unsolvable side must read back as it was written."""
        original = _sample_fit_result(
            intervals={
                'Ka_guest': _interval(open_low=True, open_high=True, split=True, unsolvable_high=True, dof=7),
            }
        )
        restored = FitResult.from_dict(json.loads(json.dumps(original.to_dict())))

        assert restored.intervals['Ka_guest'] == original.intervals['Ka_guest']

    def test_a_file_written_before_intervals_keeps_its_fit_and_carries_none(self):
        """The multi-start pool, its attempts and the mode it was summarised through are read past."""
        legacy = _sample_fit_result().to_dict()
        del legacy['format'], legacy['intervals'], legacy['degenerate_keys']
        legacy.update(
            n_passing=80,
            n_total=100,
            uncertainty_source='replicate',
            statistics_mode='median',
            representative_index=1,
            parameter_samples={'Ka_guest': [1.4e6, 1.5e6, 1.6e6]},
            quality_samples={'rmse': [45.0, 42.0, 48.0]},
            attempt_samples={'Ka_guest': [1.4e6, 2.0e2]},
        )

        restored = FitResult.from_dict(json.loads(json.dumps(legacy)))

        assert restored.intervals is None
        assert restored.degenerate_keys == ()
        assert restored.replica_fits is None
        assert restored.parameters['Ka_guest'].magnitude == pytest.approx(1.5e6)
        assert (restored.rmse, restored.r_squared) == (42.0, 0.998)
        np.testing.assert_array_equal(restored.y_fit.magnitude, _sample_fit_result().y_fit.magnitude)

    def test_what_the_fit_did_with_the_inputs_survives_the_file(self):
        """The fit at the entered inputs, the shift of every input and the tests are all on the record."""
        original = _with_moved_inputs()

        restored = FitResult.from_dict(json.loads(json.dumps(original.to_dict())))

        assert restored.intervals == original.intervals
        assert restored.conditional.intervals == original.conditional.intervals
        assert restored.conditional.parameters['Ka_guest'].magnitude == pytest.approx(1.5e6)
        assert restored.conditional.parameters['Ka_guest'].units == Q_(1, '1/M').units
        assert (restored.conditional.rmse, restored.conditional.r_squared) == (51.0, 0.995)
        assert restored.input_shifts == original.input_shifts
        assert restored.diagnostics == original.diagnostics
        # The uncertainties the fit was made under are part of its configuration snapshot.
        assert restored.fit_config['input_uncertainty'] == {
            'h0': {'kind': 'sigma', 'sigma': 10.0, 'lo': 0.0, 'hi': 0.0, 'relative': True},
            TITRANT: {'kind': 'sigma', 'sigma': 3.0, 'lo': 0.0, 'hi': 0.0, 'relative': True},
        }

    def test_the_penalised_profiles_are_working_and_stay_out_of_the_file(self):
        """They are megabytes of curve the tab redraws from the fit, not a record of it."""
        assert 'aware' not in _with_moved_inputs().to_dict()
        assert FitResult.from_dict(json.loads(json.dumps(_with_moved_inputs().to_dict()))).aware is None

    def test_a_file_from_a_fit_whose_inputs_were_all_entered_reads_with_none_of_them(self):
        """Such a file holds no conditional fit — the fit it reports is that one."""
        d = _sample_fit_result().to_dict()
        assert (d['conditional'], d['input_shifts'], d['diagnostics']) == (None, {}, None)

        del d['conditional'], d['input_shifts'], d['diagnostics']
        restored = FitResult.from_dict(json.loads(json.dumps(d)))

        assert restored.conditional is None
        assert restored.input_shifts == {}
        assert restored.diagnostics is None
        assert restored.intervals == _sample_fit_result().intervals

    def test_a_condition_that_lists_keys_comes_back_from_json_as_the_tuple_it_was(self):
        """JSON has no tuple; the assay holds ``stock_contains`` as one, and a comparison of conditions needs it back."""
        conditions = {
            **_sample_fit_result().conditions,
            'titrant_stock': Q_(1e-3, 'M'),
            'stock_contains': ('h0',),
        }
        written = json.loads(json.dumps(_sample_fit_result(conditions=conditions).to_dict()))
        assert written['conditions']['stock_contains'] == ['h0']
        restored = FitResult.from_dict(written).conditions
        assert restored['stock_contains'] == ('h0',) and isinstance(restored['stock_contains'], tuple)
        assert restored['titrant_stock'].to('M').magnitude == pytest.approx(1e-3)
        assert restored == conditions

    def test_a_fit_without_shared_sources_records_the_entries_it_always_has(self):
        """``shared_sources`` and ``titrant_additions`` appear only when stated, and the additions never in a fit's record."""
        specs = {'h0': InputSpec.sigma_pct(10)}
        plain = _config_to_dict(FitConfig(errors=ErrorModel(specs=specs, additions=AdditionError(1.0, True))))
        assert list(plain) == ['custom_bounds', 'per_replicate', 'level', 'input_uncertainty']
        assert plain['input_uncertainty'] == specs_to_dict(specs)

        shared = SharedSource('Stock', 4.0, ('h0', 'g0'))
        with_shared = _config_to_dict(FitConfig(errors=ErrorModel(specs=specs, shared=(shared,))))
        assert list(with_shared) == [*plain, 'shared_sources']
        assert ErrorModel.from_dict(json.loads(json.dumps(with_shared))) == ErrorModel(specs=specs, shared=(shared,))

    def test_from_dict_missing_optional_fields(self):
        """A file holding only what a fit must have loads, with no interval."""
        minimal = {
            'parameters': {'slope': 1.0},
            'rmse': 0.5,
            'r_squared': 0.99,
            'x_fit': [0, 1, 2],
            'y_fit': [0, 1, 2],
            'assay_type': 'DYE_ALONE',
            'model_name': 'linear',
        }
        r = FitResult.from_dict(minimal)
        assert r.conditions == {}
        assert r.measurement_set_id is None
        assert r.source_file is None
        assert r.intervals is None
        assert isinstance(r.id, str)

    def test_x_y_fit_units_round_trip(self):
        """x_fit/y_fit carry their own unit tokens; older files without them fall
        back to the M/au convention."""
        r = _sample_fit_result()
        restored = FitResult.from_dict(r.to_dict())
        assert restored.x_fit.units == r.x_fit.units
        assert restored.y_fit.units == r.y_fit.units

        bare = r.to_dict()
        bare.pop('x_fit_unit')
        bare.pop('y_fit_unit')
        loaded = FitResult.from_dict(bare)
        assert loaded.x_fit.units == Q_(1, 'M').units
        assert loaded.y_fit.units == Q_(1, 'au').units

    def test_unknown_assay_round_trips_via_quantity_units(self):
        """to_dict emits unit tokens from the parameter Quantities (not a registry
        lookup), so a result whose assay_type is unknown to the registry still
        round-trips with units — the write side is self-describing."""
        r = _sample_fit_result(assay_type='LEGACY_UNKNOWN')
        d = r.to_dict()
        assert d['parameter_units']['Ka_guest'] == str(Q_(1, '1/M').units)
        restored = FitResult.from_dict(d)
        assert restored.parameters['Ka_guest'].units == Q_(1, '1/M').units
        assert restored.parameters['I_dye_free'].units == Q_(1, 'au/M').units

    def test_config_custom_bounds_keep_unit_token(self):
        """Serialized custom_bounds provenance keeps its unit token so a bound in
        1/M isn't stored as a unit-ambiguous bare number."""
        cfg = FitConfig(custom_bounds={'Ka_guest': (Q_(1e5, '1/M'), Q_(1e9, '1/M'))})
        stored = _config_to_dict(cfg)
        lo, hi, unit = stored['custom_bounds']['Ka_guest']
        assert (lo, hi) == (1e5, 1e9)
        assert unit == str(Q_(1, '1/M').units)
        assert stored['level'] == LEVEL

    def test_from_dict_raises_on_missing_units_unknown_assay(self):
        """A file with no parameter_units AND an unknown assay type must fail loud,
        not silently load a real unit (1/M) as dimensionless."""
        d = _sample_fit_result().to_dict()
        d.pop('parameter_units', None)
        d['assay_type'] = 'LEGACY_UNKNOWN'  # not resolvable via the registry
        with pytest.raises(ValueError, match='no unit for parameter'):
            FitResult.from_dict(d)


# ---------------------------------------------------------------------------
# The reported rows
# ---------------------------------------------------------------------------


class TestSummarizeParameters:
    """The single source every reported number is derived from.

    The table, the plot annotation and the TXT/CSV exports all render from
    ``summarize_parameters``, so its contract is pinned here directly rather
    than only through those three surfaces.
    """

    def test_log_twin_appears_exactly_for_the_binding_constants(self):
        from core.assays.registry import ASSAY_REGISTRY, AssayType, ParamKind

        rows = summarize_parameters(_sample_fit_result())  # GDA

        kinds = ASSAY_REGISTRY[AssayType.GDA].param_kinds
        assert {r.key for r in rows if r.is_log} == {
            k for k, kind in kinds.items() if kind is ParamKind.BINDING_CONSTANT
        }
        # Every fitted parameter still gets its own plain row.
        assert {r.key for r in rows if not r.is_log} == set(_sample_fit_result().parameters)

    def test_unit_comes_from_the_parameter_quantity_not_the_registry(self):
        """An assay the registry has never heard of still reports real units.

        Re-deriving units from the registry yields ``dimensionless`` for an
        unknown assay, silently turning a Ka in 1/M into a bare number.
        """
        rows = {r.key: r for r in summarize_parameters(_sample_fit_result(assay_type='LEGACY_UNKNOWN'))}

        assert rows['Ka_guest'].unit == str(Q_(1, '1/M').units)
        assert rows['I_dye_free'].unit == str(Q_(1, 'au/M').units)
        assert rows['I0'].unit == str(Q_(1, 'au').units)

    def test_the_log_twin_interval_is_the_parameter_interval_transformed(self):
        """log₁₀ is monotone, so the endpoints map one to one — the twin quotes no
        other interval and no back-transformed spread."""
        rows = {(r.key, r.is_log): r for r in summarize_parameters(_sample_fit_result())}
        plain, twin = rows[('Ka_guest', False)], rows[('Ka_guest', True)]

        assert 10**twin.estimate == pytest.approx(plain.estimate, rel=1e-15)
        assert 10 ** twin.interval[0] == pytest.approx(plain.interval[0], rel=1e-15)
        assert 10 ** twin.interval[1] == pytest.approx(plain.interval[1], rel=1e-15)
        assert twin.interval[0] < twin.estimate < twin.interval[1]
        assert twin.level == plain.level == LEVEL

    def test_an_open_side_is_carried_to_both_rows(self):
        result = _sample_fit_result(intervals={'Ka_guest': _interval(open_high=True)})

        for row in (r for r in summarize_parameters(result) if r.key == 'Ka_guest'):
            assert row.interval_open == (False, True)

    def test_a_result_without_intervals_reports_estimates_alone(self):
        """An imported file written before intervals were reported invents none."""
        rows = summarize_parameters(_sample_fit_result(intervals=None, degenerate_keys=()))

        assert rows, 'estimates must still be reported'
        assert all(r.interval is None and r.level is None for r in rows)
        assert all(not r.degenerate for r in rows)
        # The binding constant still gets its log₁₀ twin: it needs no interval.
        assert any(r.is_log for r in rows)

    def test_degenerate_rows_are_the_ones_the_fit_named(self):
        rows = {(r.key, r.is_log): r for r in summarize_parameters(_sample_fit_result())}

        assert {k for (k, _), r in rows.items() if r.degenerate} == {'I0', 'I_dye_free', 'I_dye_bound'}

    def test_replicate_columns_describe_the_replicates_the_fit_used(self):
        """A replicate left out of the average describes data the fit does not, so it stays out.

        Used replicates give Ka 1e5 and 1e7; a left-out one gives 1e9. The
        median of the two used values is 5.05e6 and their maximum 1e7, and in
        log₁₀ the median is 6 — which log₁₀ of the Ka median (6.70) is not.
        """
        result = _sample_fit_result(
            metadata={'active_replica_ids': ['a', 'b', 'c'], 'replica_ids_fit': ['a', 'b']},
            replica_fits=[_replica('a', 1e5), _replica('b', 1e7), _replica('c', 1e9)],
        )
        rows = {(r.key, r.is_log): r for r in summarize_parameters(result)}

        plain = rows[('Ka_guest', False)].replicates
        assert plain['median'] == pytest.approx(5.05e6)
        assert (plain['min'], plain['max']) == (1e5, 1e7)
        twin = rows[('Ka_guest', True)].replicates
        assert twin['median'] == pytest.approx(6.0)
        assert (twin['min'], twin['max']) == (5.0, 7.0)

    def test_one_used_replicate_reports_no_replicate_spread(self):
        """A single replicate is the fit seen again, not a spread between replicates."""
        result = _sample_fit_result(
            metadata={'active_replica_ids': ['a', 'b'], 'replica_ids_fit': ['a']},
            replica_fits=[_replica('a', 1e6), _replica('b', 1e9)],
        )

        assert all(r.replicates is None for r in summarize_parameters(result))

    def test_a_fit_of_the_average_reports_no_replicate_spread(self):
        assert all(r.replicates is None for r in summarize_parameters(_sample_fit_result()))

    def test_a_binding_constant_carries_what_the_entered_inputs_alone_say(self):
        """Two claims side by side: the interval that lets the inputs move, and the one that does not."""
        rows = {(r.key, r.is_log): r for r in summarize_parameters(_with_moved_inputs())}
        plain, twin = rows[('Ka_guest', False)], rows[('Ka_guest', True)]

        assert plain.estimate == pytest.approx(1.2e6) and plain.interval == (1.0e6, 1.45e6)
        assert plain.conditional_estimate == pytest.approx(1.5e6)
        assert plain.conditional_interval == (1.4e6, 1.6e6)
        # The log twin transforms the same endpoints, as it does its own.
        assert 10**twin.conditional_estimate == pytest.approx(plain.conditional_estimate, rel=1e-15)
        assert 10 ** twin.conditional_interval[0] == pytest.approx(1.4e6, rel=1e-15)
        assert 10 ** twin.conditional_interval[1] == pytest.approx(1.6e6, rel=1e-15)
        # A signal parameter has no interval of either kind.
        assert rows[('I_dye_free', False)].conditional_estimate is None
        assert rows[('I_dye_free', False)].conditional_interval is None

    def test_an_open_side_of_the_conditional_interval_is_reported_as_open(self):
        result = _with_moved_inputs(
            conditional=replace(_with_moved_inputs().conditional, intervals={'Ka_guest': _interval(open_high=True)})
        )

        assert {r.conditional_open for r in summarize_parameters(result) if r.key == 'Ka_guest'} == {(False, True)}

    def test_a_fit_that_moved_no_input_reports_no_second_column(self):
        """Its headline already is the fit at the entered inputs; repeating it would read as two estimates."""
        result = _with_moved_inputs(input_shifts={})

        rows = summarize_parameters(result)
        assert all(r.conditional_estimate is None and r.conditional_interval is None for r in rows)
        assert all(r.conditional_open == (False, False) for r in rows)


# ---------------------------------------------------------------------------
# A signal parameter held on an entered bound
# ---------------------------------------------------------------------------


def test_a_signal_parameter_the_fit_ended_on_an_entered_bound_is_named_with_that_bound():
    """A bound below what the data need holds the curve away from them; the result has to say which one did."""
    from core.assays.gda import GDAAssay
    from core.pipeline.fit_pipeline import fit_assay, parameters_on_bound
    from tests.conftest import GDA_TRUE, _make_gda_data

    x, y = _make_gda_data(GDA_TRUE, n_points=15)
    y = y + np.random.default_rng(2).normal(0.0, 0.01 * np.ptp(y), y.size)
    assay = GDAAssay(
        x_data=Q_(x, 'M'),
        y_data=Q_(y, 'au'),
        Ka_dye=Q_(GDA_TRUE['Ka_dye'], '1/M'),
        h0=Q_(GDA_TRUE['h0'], 'M'),
        g0=Q_(GDA_TRUE['g0'], 'M'),
    )
    free = fit_assay(assay)
    ceiling = 0.5 * free.parameters['I_dye_bound']
    held = fit_assay(assay, FitConfig(custom_bounds={'I_dye_bound': (Q_(0, 'au/M'), ceiling)}))

    # Nothing is on an entered bound in the free fit, and a parameter on zero — the physical limit, here the
    # offset of a signal that has none — is not a finding.
    assert any(v.magnitude == 0.0 for v in free.parameters.values())
    assert parameters_on_bound(free) == {}
    assert parameters_on_bound(held) == {'I_dye_bound': ceiling}
    assert held.r_squared < free.r_squared
    # Read from what the file holds, so an imported result says it too.
    assert parameters_on_bound(FitResult.from_dict(json.loads(json.dumps(held.to_dict())))) == {'I_dye_bound': ceiling}


def test_an_infinite_misfit_ratio_is_written_as_strict_json_and_read_back_as_infinite():
    """Replicates that agree exactly leave no pure error, so the lack-of-fit ratio is infinite.

    A results file is read by other programs too, and JSON has no token for
    an infinite number, so the file holds null and the reader restores it.
    """
    exact = MisfitTest('lack_of_fit', math.inf, 0.0, dof=(9, 24))
    result = _with_moved_inputs(
        diagnostics=FitDiagnostics(
            conditional_misfit=exact,
            misfit=exact,
            conflict=Conflict(math.inf, 2, 0.0, (0.17, 0.99)),
            verdict=Verdict.MODEL_INADEQUATE,
        )
    )
    text = json.dumps(result.to_dict(), allow_nan=False)  # refuses any value JSON cannot hold
    assert '"statistic": null' in text and '"q": null' in text

    back = FitResult.from_dict(json.loads(text))
    assert back.diagnostics.misfit == back.diagnostics.conditional_misfit == exact
    assert back.diagnostics.conflict.q == math.inf


def test_a_bound_with_no_limit_is_written_as_strict_json_and_read_back_as_no_limit():
    """A results file is read by other programs too, and JSON has no token for an infinite number."""
    from core.pipeline.fit_pipeline import parameters_on_bound

    floor = Q_(1.0, 'au')
    result = _sample_fit_result(
        parameters={**_sample_fit_result().parameters, 'I0': floor},
        fit_config=_config_to_dict(FitConfig(custom_bounds={'I0': (floor, Q_(math.inf, 'au'))})),
    )
    text = json.dumps(result.to_dict(), allow_nan=False)  # refuses any value JSON cannot hold
    back = FitResult.from_dict(json.loads(text))
    assert back.fit_config['custom_bounds'] == {'I0': [1.0, None, 'au']}
    # The entered side is still read; the side with no limit is not a bound the fit can end on.
    assert parameters_on_bound(back) == {'I0': floor}
