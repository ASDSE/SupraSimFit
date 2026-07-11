"""Tests for FitResult serialization and traceability."""

import json

import numpy as np
import pytest

from core.pipeline.fit_pipeline import FitResult
from core.units import Q_, Quantity

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
        uncertainties={
            'Ka_guest': Q_(1e4, '1/M'),
            'I0': Q_(5.0, 'au'),
            'I_dye_free': Q_(1e5, 'au/M'),
            'I_dye_bound': Q_(2e5, 'au/M'),
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
        statistics_mode='median',
    )
    defaults.update(overrides)
    return FitResult(**defaults)


# ---------------------------------------------------------------------------
# Basic properties
# ---------------------------------------------------------------------------


class TestFitResultProperties:
    """Core properties and defaults."""

    def test_unique_ids(self):
        r1 = _sample_fit_result()
        r2 = _sample_fit_result()
        assert r1.id != r2.id


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

        # Parameters and uncertainties round-trip as Quantities
        for k in original.parameters:
            assert restored.parameters[k].magnitude == pytest.approx(original.parameters[k].magnitude)
        for k in original.uncertainties:
            assert restored.uncertainties[k].magnitude == pytest.approx(original.uncertainties[k].magnitude)
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
        assert restored.statistics_mode == original.statistics_mode

    def test_from_dict_missing_optional_fields(self):
        """from_dict handles missing optional keys gracefully."""
        minimal = {
            'parameters': {'slope': 1.0},
            'uncertainties': {'slope': 0.1},
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

    def test_x_fit_y_fit_are_ndarray_after_from_dict(self):
        d = _sample_fit_result().to_dict()
        r = FitResult.from_dict(d)
        assert isinstance(r.x_fit, Quantity)
        assert isinstance(r.y_fit, Quantity)

    def test_round_trip_nan_uncertainty(self):
        """NaN uncertainties survive round-trip."""
        r = _sample_fit_result(
            uncertainties={
                'Ka_guest': Q_(np.nan, '1/M'),
                'I0': Q_(np.nan, 'au'),
                'I_dye_free': Q_(np.nan, 'au/M'),
                'I_dye_bound': Q_(np.nan, 'au/M'),
            }
        )
        d = r.to_dict()
        restored = FitResult.from_dict(d)
        assert np.isnan(restored.uncertainties['Ka_guest'].magnitude)


class TestEnsembleMutators:
    """Fail-fast contracts on the public pipeline mutation helpers."""

    def test_apply_statistics_mode_rejects_unknown_mode(self):
        from core.pipeline.fit_pipeline import apply_statistics_mode

        r = _sample_fit_result()
        before = dict(r.uncertainties)
        with pytest.raises(ValueError, match='Unknown statistics mode'):
            apply_statistics_mode(r, 'bogus')
        # Rejected up front — no partial mutation.
        assert r.statistics_mode == 'median'
        assert r.uncertainties == before

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


class TestFromDictNormalisation:
    """Malformed/legacy imports are sanitised so they can't crash the GUI later."""

    def test_unknown_statistics_mode_falls_back_to_default(self):
        from core.optimizer.ensemble import DEFAULT_STATISTICS_MODE

        d = _sample_fit_result().to_dict()
        d['statistics_mode'] = 'bogus'
        assert FitResult.from_dict(d).statistics_mode == DEFAULT_STATISTICS_MODE

    def test_out_of_range_representative_index_dropped(self):
        d = _sample_fit_result().to_dict()  # pool size 3
        d['representative_index'] = 999
        assert FitResult.from_dict(d).representative_index is None
