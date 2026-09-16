"""Tests for FitResult serialization and traceability."""

import json

import numpy as np
import pytest

from core.assays.gda import GDAAssay
from core.pipeline.fit_pipeline import FitConfig, FitResult, fit_assay
from core.units import Q_, Quantity
from tests.conftest import GDA_IDA_RECOVERY_BOUNDS, GDA_TRUE, _make_gda_data

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sample_fit_result(**overrides) -> FitResult:
    """Build a minimal FitResult for testing."""
    defaults = dict(
        parameters={
            'Ka_guest': Q_(1.5e6, '1/M'),
            'I0': Q_(0.0, 'au'),
            'I_dye_free': Q_(5e7, 'au/M'),
            'I_dye_bound': Q_(3e8, 'au/M'),
        },
        rmse=42.0,
        r_squared=0.998,
        n_passing=80,
        n_total=100,
        x_fit=Q_(np.linspace(0, 50e-6, 30), 'M'),
        y_fit=Q_(np.linspace(100, 3000, 30), 'au'),
        assay_type='GDA',
        model_name='equilibrium_4param',
        conditions={'Ka_dye': Q_(5e5, '1/M'), 'h0': Q_(10e-6, 'M'), 'g0': Q_(20e-6, 'M')},
        fit_config={'n_trials': 100, 'rmse_threshold_factor': 1.5},
        measurement_set_id='abc123',
        source_file='data/GDA_system.txt',
        parameter_samples={
            'Ka_guest': np.array([1.4e6, 1.5e6, 1.6e6]),
            'I0': np.array([-1.0, 0.0, 1.0]),
            'I_dye_free': np.array([4.9e7, 5.0e7, 5.1e7]),
            'I_dye_bound': np.array([2.9e8, 3.0e8, 3.1e8]),
        },
        quality_samples={
            'rmse': np.array([45.0, 42.0, 48.0]),
            'r_squared': np.array([0.997, 0.998, 0.996]),
        },
        representative_index=1,
        # Every attempt: the three accepted trials above, then two the R² floor rejected.
        attempt_samples={
            'Ka_guest': np.array([1.4e6, 1.5e6, 1.6e6, 2.0e2, 8.0e9]),
            'I0': np.array([-1.0, 0.0, 1.0, 60.0, -80.0]),
            'I_dye_free': np.array([4.9e7, 5.0e7, 5.1e7, 4.1e7, 5.9e7]),
            'I_dye_bound': np.array([2.9e8, 3.0e8, 3.1e8, 2.6e8, 3.4e8]),
        },
        attempt_quality={
            'rmse': np.array([45.0, 42.0, 48.0, 910.0, 640.0]),
            'r_squared': np.array([0.997, 0.998, 0.996, 0.41, 0.63]),
        },
    )
    defaults.update(overrides)
    return FitResult(**defaults)


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
        original = _sample_fit_result()
        d = original.to_dict()
        restored = FitResult.from_dict(d)

        # Parameters round-trip as Quantities
        for k in original.parameters:
            assert restored.parameters[k].magnitude == pytest.approx(original.parameters[k].magnitude)
        assert restored.rmse == original.rmse
        assert restored.r_squared == original.r_squared
        assert restored.n_passing == original.n_passing
        assert restored.n_total == original.n_total
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
        # Ensemble fields round-trip too
        for k in original.parameter_samples:
            np.testing.assert_array_almost_equal(restored.parameter_samples[k], original.parameter_samples[k])
        for k in original.quality_samples:
            np.testing.assert_array_almost_equal(restored.quality_samples[k], original.quality_samples[k])
        assert restored.representative_index == original.representative_index

    def test_from_dict_missing_optional_fields(self):
        """from_dict handles missing optional keys gracefully."""
        minimal = {
            'parameters': {'slope': 1.0},
            'rmse': 0.5,
            'r_squared': 0.99,
            'n_passing': 1,
            'n_total': 1,
            'x_fit': [0, 1, 2],
            'y_fit': [0, 1, 2],
            'assay_type': 'DYE_ALONE',
            'model_name': 'linear',
        }
        r = FitResult.from_dict(minimal)
        assert r.conditions == {}
        assert r.measurement_set_id is None
        assert r.source_file is None
        assert isinstance(r.id, str)

    def test_attempt_record_survives_json(self):
        """Every attempt and its quality come back from a JSON file value for value."""
        original = _sample_fit_result()
        restored = FitResult.from_dict(json.loads(json.dumps(original.to_dict())))

        for field in ('attempt_samples', 'attempt_quality'):
            written, read = getattr(original, field), getattr(restored, field)
            assert read.keys() == written.keys()
            for k in written:
                np.testing.assert_array_equal(read[k], written[k])

    def test_json_without_an_attempt_record_loads(self):
        """Fit-result files already on disk carry no attempt record; they load with both fields ``None``."""
        original = _sample_fit_result()
        d = original.to_dict()
        del d['attempt_samples'], d['attempt_quality']
        restored = FitResult.from_dict(json.loads(json.dumps(d)))

        assert restored.attempt_samples is None
        assert restored.attempt_quality is None
        np.testing.assert_array_equal(restored.parameter_samples['Ka_guest'], original.parameter_samples['Ka_guest'])

    def test_x_y_fit_units_round_trip(self):
        """x_fit/y_fit carry their own unit tokens; older files without them fall
        back to the M/au convention (L10)."""
        r = _sample_fit_result()
        restored = FitResult.from_dict(r.to_dict())
        assert restored.x_fit.units == r.x_fit.units
        assert restored.y_fit.units == r.y_fit.units

        legacy = r.to_dict()
        legacy.pop('x_fit_unit')
        legacy.pop('y_fit_unit')
        loaded = FitResult.from_dict(legacy)
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
        1/M isn't stored as a unit-ambiguous bare number (L9)."""
        from core.pipeline.fit_pipeline import FitConfig, _config_to_dict

        cfg = FitConfig(custom_bounds={'Ka_guest': (Q_(1e5, '1/M'), Q_(1e9, '1/M'))})
        lo, hi, unit = _config_to_dict(cfg)['custom_bounds']['Ka_guest']
        assert (lo, hi) == (1e5, 1e9)
        assert unit == str(Q_(1, '1/M').units)


class TestEnsembleMutators:
    """Fail-fast contracts on the public pipeline mutation helpers."""

    def test_select_representative_rejects_out_of_range_index(self):
        from core.pipeline.fit_pipeline import select_representative

        r = _sample_fit_result()  # pool size 3
        with pytest.raises(ValueError, match='out of range'):
            select_representative(r, None, 99)  # index validated before the assay is used

    def test_select_representative_rejects_empty_pool(self):
        from dataclasses import replace

        from core.pipeline.fit_pipeline import select_representative

        r = replace(_sample_fit_result(), parameter_samples={})
        with pytest.raises(ValueError, match='no parameter_samples'):
            select_representative(r, None, 0)  # empty dict -> clear error, not StopIteration


class TestSummarizeParameters:
    """The single source every reported number is derived from.

    The table, the plot annotation and the TXT/CSV exports all render from
    ``summarize_parameters``, so its contract is pinned here directly rather
    than only through those three surfaces.
    """

    def test_log_twin_appears_exactly_for_log_scale_keys(self):
        from core.assays.registry import ASSAY_REGISTRY, AssayType
        from core.pipeline.fit_pipeline import summarize_parameters

        rows = summarize_parameters(_sample_fit_result())  # GDA

        logged = {r.key for r in rows if r.is_log}
        assert logged == set(ASSAY_REGISTRY[AssayType.GDA].log_scale_keys)
        # Every fitted parameter still gets its own plain row.
        assert {r.key for r in rows if not r.is_log} == set(_sample_fit_result().parameters)

    def test_unit_comes_from_the_parameter_quantity_not_the_registry(self):
        """An assay the registry has never heard of still reports real units.

        Re-deriving units from the registry yields ``dimensionless`` for an
        unknown assay, silently turning a Ka in 1/M into a bare number.
        """
        from core.pipeline.fit_pipeline import summarize_parameters

        rows = {r.key: r for r in summarize_parameters(_sample_fit_result(assay_type='LEGACY_UNKNOWN'))}

        assert rows['Ka_guest'].unit == str(Q_(1, '1/M').units)
        assert rows['I_dye_free'].unit == str(Q_(1, 'au/M').units)
        assert rows['I0'].unit == str(Q_(1, 'au').units)

    def test_no_pool_means_no_stats_and_no_log_rows(self):
        """A result without a stored pool reports estimates only — no invented
        interval, and no log twin (whose statistics would have nothing to come
        from)."""
        from core.pipeline.fit_pipeline import summarize_parameters

        rows = summarize_parameters(_sample_fit_result(parameter_samples=None))

        assert rows, 'estimates must still be reported'
        assert all(r.stats is None for r in rows)
        assert not any(r.is_log for r in rows)

    def test_log_row_statistics_are_computed_in_log_space(self):
        """log₁₀ statistics come from log₁₀(pool), never log₁₀ of a Ka spread.

        Pool [1e5, 1e6, 1e7] → log₁₀ pool [5, 6, 7]: median 6, MAD 1, and the
        estimate is log₁₀ of the representative Ka. Taking log₁₀ of the Ka-space
        MAD (4.5e6) would give ≈6.65, which these values exclude.
        """
        import numpy as np

        from core.pipeline.fit_pipeline import summarize_parameters

        r = _sample_fit_result(
            parameters={**_sample_fit_result().parameters, 'Ka_guest': Q_(1e6, '1/M')},
            parameter_samples={
                'Ka_guest': np.array([1e5, 1e6, 1e7]),
                'I0': np.array([-1.0, 0.0, 1.0]),
                'I_dye_free': np.array([4.9e7, 5.0e7, 5.1e7]),
                'I_dye_bound': np.array([2.9e8, 3.0e8, 3.1e8]),
            },
        )
        log_row = next(s for s in summarize_parameters(r) if s.is_log and s.key == 'Ka_guest')

        assert log_row.estimate == pytest.approx(6.0)
        assert log_row.stats['median'] == pytest.approx(6.0)
        assert log_row.stats['mad'] == pytest.approx(1.0)
        assert log_row.stats['min'] == pytest.approx(5.0)
        assert log_row.stats['max'] == pytest.approx(7.0)


class TestFromDictNormalisation:
    """Malformed/legacy imports are sanitised so they can't crash the GUI later."""

    def test_out_of_range_representative_index_dropped(self):
        d = _sample_fit_result().to_dict()  # pool size 3
        d['representative_index'] = 999
        assert FitResult.from_dict(d).representative_index is None

    def test_from_dict_raises_on_missing_units_unknown_assay(self):
        """A legacy dict with no parameter_units AND an unknown assay type must
        fail loud, not silently load a real unit (1/M) as dimensionless (L1)."""
        d = _sample_fit_result().to_dict()
        d.pop('parameter_units', None)
        d['assay_type'] = 'LEGACY_UNKNOWN'  # not resolvable via the registry
        with pytest.raises(ValueError, match='no unit for parameter'):
            FitResult.from_dict(d)


# ---------------------------------------------------------------------------
# Attempt record on a real fit
# ---------------------------------------------------------------------------

# Seeded so the pool is reproducible. On the 5 %-noise GDA data this search
# leaves some attempts stuck far from the minimum (R² ≈ 0.75, below the app's
# default floor) beside the accepted ones (R² ≈ 0.996).
_ATTEMPT_CONFIG = FitConfig(n_trials=12, seed=1, custom_bounds=GDA_IDA_RECOVERY_BOUNDS)


def _noisy_gda_assay() -> GDAAssay:
    x, y = _make_gda_data(GDA_TRUE, noise_frac=0.05)
    return GDAAssay(
        x_data=Q_(x, 'M'),
        y_data=Q_(y, 'au'),
        Ka_dye=Q_(GDA_TRUE['Ka_dye'], '1/M'),
        h0=Q_(GDA_TRUE['h0'], 'M'),
        g0=Q_(GDA_TRUE['g0'], 'M'),
    )


@pytest.fixture(scope='module')
def noisy_gda_fit() -> FitResult:
    """One seeded fit that accepts some attempts and rejects others."""
    return fit_assay(_noisy_gda_assay(), _ATTEMPT_CONFIG)


class TestAttemptRecord:
    """A fit carries every completed attempt, accepted or rejected.

    The Identifiability view plots each attempt's Ka against its R² with the
    quality floor drawn as a line, so the record must hold the rejected
    attempts too, while every reported number comes from the accepted pool
    alone.
    """

    def test_every_accepted_trial_is_among_the_attempts(self, noisy_gda_fit):
        keys = list(noisy_gda_fit.parameter_samples)
        attempts = np.column_stack([noisy_gda_fit.attempt_samples[k] for k in keys])
        accepted = np.column_stack([noisy_gda_fit.parameter_samples[k] for k in keys])

        for row in accepted:
            assert np.isclose(attempts, row, rtol=1e-12, atol=0.0).all(axis=1).any(), f'accepted {row} not recorded'

    def test_one_entry_per_completed_attempt_split_by_the_floor(self, noisy_gda_fit):
        r2 = noisy_gda_fit.attempt_quality['r_squared']
        lengths = {len(a) for a in (*noisy_gda_fit.attempt_samples.values(), noisy_gda_fit.attempt_quality['rmse'])}

        assert lengths == {len(r2)}, 'attempt arrays must be index-aligned'
        assert len(r2) == noisy_gda_fit.n_total  # n_total counts the completed attempts
        assert len(r2) >= noisy_gda_fit.n_passing
        # No RMSE trim is set, so the floor alone decides: exactly the accepted trials sit on or above it.
        assert np.count_nonzero(r2 >= _ATTEMPT_CONFIG.min_r_squared) == noisy_gda_fit.n_passing

    def test_attempts_are_kept_when_no_trial_passes(self):
        from dataclasses import replace

        floor = 0.999999  # unreachable on 5 % noise
        result = fit_assay(_noisy_gda_assay(), replace(_ATTEMPT_CONFIG, min_r_squared=floor))

        assert result.n_passing == 0
        r2 = result.attempt_quality['r_squared']
        assert r2.size > 0
        assert np.all(r2 < floor)
        assert all(len(a) == r2.size for a in result.attempt_samples.values())

    def test_rejected_attempts_never_reach_the_reported_summary(self, noisy_gda_fit):
        from dataclasses import replace

        from core.pipeline.fit_pipeline import summarize_parameters

        # Guard: rejected attempts reach past the pool, so summarising them would change the reported range.
        assert noisy_gda_fit.attempt_samples['Ka_guest'].max() > noisy_gda_fit.parameter_samples['Ka_guest'].max()

        without_attempts = replace(noisy_gda_fit, attempt_samples=None, attempt_quality=None)
        assert summarize_parameters(noisy_gda_fit) == summarize_parameters(without_attempts)
