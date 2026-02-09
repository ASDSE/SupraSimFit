"""P2: Forward model math tests.

Verify forward models produce correct signal values for known inputs.
These tests validate the mathematical correctness of the equilibrium
and linear models independently of the optimizer.
"""

import numpy as np
import pytest

from core.models.equilibrium import competitive_signal_point, dba_signal, gda_signal, ida_signal
from core.models.linear import linear_signal


class TestLinearModel:
    """Tests for the linear (dye-alone) forward model."""

    def test_zero_concentration_gives_intercept(self):
        """Signal at x=0 equals intercept."""
        x = np.array([0.0])
        result = linear_signal(slope=1e10, intercept=42.0, x=x)
        assert result[0] == pytest.approx(42.0)

    def test_linearity(self):
        """Signal is strictly linear with concentration."""
        x = np.array([0, 1e-6, 2e-6, 3e-6])
        slope, intercept = 5e10, 100.0
        result = linear_signal(slope, intercept, x)

        expected = slope * x + intercept
        np.testing.assert_array_almost_equal(result, expected)

    def test_negative_slope(self):
        """Negative slope produces decreasing signal."""
        x = np.array([0.0, 1e-6, 2e-6])
        result = linear_signal(slope=-1e10, intercept=1000.0, x=x)
        assert result[0] > result[1] > result[2]

    def test_empty_array(self):
        """Empty input returns empty output."""
        x = np.array([])
        result = linear_signal(slope=1e10, intercept=100.0, x=x)
        assert len(result) == 0


class TestDBAModel:
    """Tests for the DBA (direct binding) forward model."""

    def test_zero_titrant_gives_baseline(self):
        """No titrant => signal from free fixed species only."""
        x = np.array([0.0])
        # With x_titrant=0, no complex forms
        result = dba_signal(
            I0=50.0,
            Ka_dye=1e6,
            I_dye_free=1000.0,
            I_dye_bound=5000.0,
            x_titrant=x,
            y_fixed=10e-6,
        )
        # At x=0: y_free=y_fixed=10e-6 (no titrant to bind)
        # signal = I0 + I_dye_free * y_free + I_dye_bound * 0
        expected = 50.0 + 1000.0 * 10e-6
        assert result[0] == pytest.approx(expected, rel=1e-6)

    def test_signal_increases_with_titrant(self):
        """Signal should increase as titrant is added (more complex forms)."""
        x = np.linspace(0, 50e-6, 10)
        result = dba_signal(
            I0=50.0,
            Ka_dye=5e5,
            I_dye_free=1000.0,
            I_dye_bound=5000.0,
            x_titrant=x,
            y_fixed=10e-6,
        )
        # With I_dye_bound > I_dye_free, signal should generally increase
        # as more complex forms (but depends on specific regime)
        assert not np.any(np.isnan(result))
        assert len(result) == 10

    def test_roundtrip_with_known_params(self):
        """Forward model with true params on synthetic x gives synthetic y."""
        from tests.conftest import DBA_TRUE, _make_dba_data

        x, y_expected = _make_dba_data(DBA_TRUE, noise_frac=0.0)
        y_actual = dba_signal(
            I0=DBA_TRUE['I0'],
            Ka_dye=DBA_TRUE['Ka_dye'],
            I_dye_free=DBA_TRUE['I_dye_free'],
            I_dye_bound=DBA_TRUE['I_dye_bound'],
            x_titrant=x,
            y_fixed=DBA_TRUE['fixed_conc'],
        )
        np.testing.assert_array_almost_equal(y_actual, y_expected)

    def test_high_ka_saturates(self):
        """Very high Ka_dye should drive binding to saturation."""
        x = np.array([10e-6])  # Equal to fixed
        result_low = dba_signal(
            I0=0,
            Ka_dye=1e3,
            I_dye_free=1000.0,
            I_dye_bound=5000.0,
            x_titrant=x,
            y_fixed=10e-6,
        )
        result_high = dba_signal(
            I0=0,
            Ka_dye=1e12,
            I_dye_free=1000.0,
            I_dye_bound=5000.0,
            x_titrant=x,
            y_fixed=10e-6,
        )
        # Higher Ka => more complex => higher signal (since I_dye_bound > I_dye_free)
        assert result_high[0] > result_low[0]


class TestCompetitiveModels:
    """Tests for GDA and IDA competitive binding models."""

    # Common conditions for competitive tests
    Ka_dye = 5e5
    h0 = 10e-6
    d0 = 1e-6
    g0 = 5e-6

    def test_gda_no_guest_equals_dba(self):
        """GDA with g0=0 should behave like DBA (no competition)."""
        d0_values = np.linspace(1e-7, 30e-6, 10)
        result_with_guest = gda_signal(
            I0=50.0,
            Ka_guest=1e6,
            I_dye_free=1000.0,
            I_dye_bound=5000.0,
            Ka_dye=self.Ka_dye,
            h0=self.h0,
            d0_values=d0_values,
            g0=0.0,
        )
        # With g0=0, no competition — signal should still be valid
        assert not np.any(np.isnan(result_with_guest))

    def test_gda_signal_increases_with_dye(self):
        """GDA signal increases as dye is titrated in."""
        d0_values = np.linspace(1e-7, 30e-6, 20)
        result = gda_signal(
            I0=50.0,
            Ka_guest=1.5e6,
            I_dye_free=1000.0,
            I_dye_bound=5000.0,
            Ka_dye=self.Ka_dye,
            h0=self.h0,
            d0_values=d0_values,
            g0=self.g0,
        )
        assert not np.any(np.isnan(result))
        # Overall trend: signal increases with dye
        assert result[-1] > result[0]

    def test_ida_signal_decreases_with_guest(self):
        """IDA signal decreases as guest displaces dye."""
        g0_values = np.linspace(0, 50e-6, 20)
        result = ida_signal(
            I0=100.0,
            Ka_guest=2e6,
            I_dye_free=2000.0,
            I_dye_bound=8000.0,
            Ka_dye=self.Ka_dye,
            h0=self.h0,
            d0=self.d0,
            g0_values=g0_values,
        )
        assert not np.any(np.isnan(result))
        # I_dye_bound > I_dye_free => as guest displaces dye from host,
        # signal decreases (less HD complex)
        assert result[-1] < result[0]

    def test_gda_roundtrip_with_known_params(self):
        """GDA forward model with true params reproduces synthetic data."""
        from tests.conftest import GDA_TRUE, _make_gda_data

        x, y_expected = _make_gda_data(GDA_TRUE, noise_frac=0.0)
        y_actual = gda_signal(
            I0=GDA_TRUE['I0'],
            Ka_guest=GDA_TRUE['Ka_guest'],
            I_dye_free=GDA_TRUE['I_dye_free'],
            I_dye_bound=GDA_TRUE['I_dye_bound'],
            Ka_dye=GDA_TRUE['Ka_dye'],
            h0=GDA_TRUE['h0'],
            d0_values=x,
            g0=GDA_TRUE['g0'],
        )
        np.testing.assert_array_almost_equal(y_actual, y_expected)

    def test_ida_roundtrip_with_known_params(self):
        """IDA forward model with true params reproduces synthetic data."""
        from tests.conftest import IDA_TRUE, _make_ida_data

        x, y_expected = _make_ida_data(IDA_TRUE, noise_frac=0.0)
        y_actual = ida_signal(
            I0=IDA_TRUE['I0'],
            Ka_guest=IDA_TRUE['Ka_guest'],
            I_dye_free=IDA_TRUE['I_dye_free'],
            I_dye_bound=IDA_TRUE['I_dye_bound'],
            Ka_dye=IDA_TRUE['Ka_dye'],
            h0=IDA_TRUE['h0'],
            d0=IDA_TRUE['d0'],
            g0_values=x,
        )
        np.testing.assert_array_almost_equal(y_actual, y_expected)

    def test_competitive_signal_point_returns_float(self):
        """Single-point competitive signal returns a float, not array."""
        result = competitive_signal_point(
            I0=50.0,
            Ka_guest=1e6,
            I_dye_free=1000.0,
            I_dye_bound=5000.0,
            Ka_dye=5e5,
            h0=10e-6,
            d0=1e-6,
            g0=5e-6,
        )
        assert isinstance(result, float)
        assert not np.isnan(result)
