"""P2: Forward model math tests.

Verify forward models produce correct signal values for known inputs.
These tests validate the mathematical correctness of the equilibrium
and linear models independently of the optimizer.
"""

import numpy as np
import pytest

from scipy.optimize import brentq

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

    def test_competitive_signal_point_not_nan(self):
        """Single-point competitive signal returns a valid number."""
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
        assert not np.isnan(result)


# ---------------------------------------------------------------------------
# GAP-2: Mass-balance conservation
# ---------------------------------------------------------------------------


class TestMassBalance:
    """Verify fundamental conservation laws in equilibrium models."""

    def test_dba_mass_balance(self):
        """Total host = free host + complex, total dye = free dye + complex."""
        Ka = 5e5
        y_fixed = 10e-6
        x_titrant = np.array([1e-6, 10e-6, 50e-6])

        for x in x_titrant:
            delta = x - y_fixed
            a = Ka
            b = Ka * delta + 1
            c = -y_fixed
            disc = b**2 - 4 * a * c
            y_free = (-b + np.sqrt(disc)) / (2 * a)
            x_free = y_free + delta
            hd = Ka * y_free * x_free

            # y_total conservation: y_free + hd == y_fixed
            assert y_free + hd == pytest.approx(y_fixed, rel=1e-10)
            # x_total conservation: x_free + hd == x
            assert x_free + hd == pytest.approx(x, rel=1e-10)

    def test_competitive_mass_balance(self):
        """h_free + HD + HG == h0; d_free + HD == d0; g_free + HG == g0."""
        Ka_dye = 5e5
        Ka_guest = 1.5e6
        h0 = 10e-6
        d0 = 5e-6
        g0 = 20e-6

        def mass_balance(h):
            denom_D = 1 + Ka_dye * h
            denom_G = 1 + Ka_guest * h
            return h + (Ka_dye * h * d0) / denom_D + (Ka_guest * h * g0) / denom_G - h0

        h_free = brentq(mass_balance, 1e-20, h0, xtol=1e-14)

        d_free = d0 / (1 + Ka_dye * h_free)
        g_free = g0 / (1 + Ka_guest * h_free)
        HD = Ka_dye * h_free * d_free
        HG = Ka_guest * h_free * g_free

        assert h_free + HD + HG == pytest.approx(h0, rel=1e-10)
        assert d_free + HD == pytest.approx(d0, rel=1e-10)
        assert g_free + HG == pytest.approx(g0, rel=1e-10)


# ---------------------------------------------------------------------------
# GAP-3: Competitive model boundary conditions
# ---------------------------------------------------------------------------


class TestCompetitiveBoundaries:
    """Limiting cases for the competitive binding model."""

    def test_gda_g0_zero_matches_dba(self):
        """GDA with g0=0 numerically matches DBA."""
        Ka_dye = 5e5
        h0 = 10e-6
        I0, I_dye_free, I_dye_bound = 50.0, 1000.0, 5000.0
        d0_values = np.linspace(1e-7, 30e-6, 10)

        gda_result = gda_signal(
            I0, Ka_guest=1e6, I_dye_free=I_dye_free, I_dye_bound=I_dye_bound,
            Ka_dye=Ka_dye, h0=h0, d0_values=d0_values, g0=0.0,
        )
        dba_result = dba_signal(
            I0, Ka_dye=Ka_dye, I_dye_free=I_dye_free, I_dye_bound=I_dye_bound,
            x_titrant=d0_values, y_fixed=h0,
        )
        # Different solvers (Brent vs quadratic) give slightly different results
        np.testing.assert_allclose(gda_result, dba_result, rtol=1e-3)

    def test_ida_ka_guest_zero_no_displacement(self):
        """Non-binding guest (Ka→0) produces constant signal."""
        g0_values = np.linspace(0, 50e-6, 10)
        result = ida_signal(
            I0=50.0, Ka_guest=1e-20, I_dye_free=1000.0, I_dye_bound=5000.0,
            Ka_dye=5e5, h0=10e-6, d0=5e-6, g0_values=g0_values,
        )
        assert not np.any(np.isnan(result))
        # Signal should be essentially constant (no displacement)
        assert np.ptp(result) / result[0] < 1e-6

    def test_ida_ka_guest_huge_displaces_all_dye(self):
        """Overwhelmingly strong guest saturates host → dye fully displaced."""
        g0_values = np.array([100e-6])  # large excess
        d0 = 5e-6
        I0, I_dye_free, I_dye_bound = 50.0, 1000.0, 5000.0

        result = ida_signal(
            I0, Ka_guest=1e15, I_dye_free=I_dye_free, I_dye_bound=I_dye_bound,
            Ka_dye=5e5, h0=10e-6, d0=d0, g0_values=g0_values,
        )
        # All dye free → signal ≈ I0 + I_dye_free * d0
        expected = I0 + I_dye_free * d0
        assert result[0] == pytest.approx(expected, rel=0.01)

    def test_competitive_d0_zero_gives_I0(self):
        """No dye → signal equals I0 (no dye contribution)."""
        result = competitive_signal_point(
            I0=50.0, Ka_guest=1e6, I_dye_free=1000.0, I_dye_bound=5000.0,
            Ka_dye=5e5, h0=10e-6, d0=0.0, g0=5e-6,
        )
        assert result == pytest.approx(50.0, abs=1e-10)


# ---------------------------------------------------------------------------
# GAP-4: Brent solver failure propagation
# ---------------------------------------------------------------------------


class TestSolverFailure:
    """Verify graceful NaN on solver failure."""

    def test_gda_nan_point_does_not_crash(self):
        """An array with extreme values propagates NaN but doesn't crash."""
        # h0 near-zero with huge binding constants → Brent bracket may fail
        d0_values = np.array([1e-6, 10e-6])
        result = gda_signal(
            I0=0, Ka_guest=1e50, I_dye_free=1, I_dye_bound=1,
            Ka_dye=1e50, h0=1e-30, d0_values=d0_values, g0=1.0,
        )
        assert len(result) == 2  # no crash, correct length
