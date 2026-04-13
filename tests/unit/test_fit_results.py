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
    )
    defaults.update(overrides)
    return FitResult(**defaults)


# ---------------------------------------------------------------------------
# Basic properties
# ---------------------------------------------------------------------------


class TestFitResultProperties:
    """Core properties and defaults."""

    def test_success_true(self):
        r = _sample_fit_result(n_passing=5)
        assert r.success is True

    def test_success_false(self):
        r = _sample_fit_result(n_passing=0)
        assert r.success is False

    def test_auto_id(self):
        r = _sample_fit_result()
        assert isinstance(r.id, str)
        assert len(r.id) == 32

    def test_auto_timestamp(self):
        r = _sample_fit_result()
        assert isinstance(r.timestamp, str)
        assert 'T' in r.timestamp  # ISO-8601

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
        # Conditions are serialized as magnitudes (not Quantity round-trip)
        assert restored.fit_config == original.fit_config
        assert restored.measurement_set_id == original.measurement_set_id
        assert restored.source_file == original.source_file
        assert restored.id == original.id
        assert restored.timestamp == original.timestamp
        np.testing.assert_array_almost_equal(restored.x_fit.magnitude, original.x_fit.magnitude)
        np.testing.assert_array_almost_equal(restored.y_fit.magnitude, original.y_fit.magnitude)

    def test_round_trip_preserves_success(self):
        for n in (0, 5):
            r = _sample_fit_result(n_passing=n)
            restored = FitResult.from_dict(r.to_dict())
            assert restored.success == r.success

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
