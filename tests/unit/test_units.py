"""Tests for pint unit validation helpers in core.units."""

import numpy as np
import pint
import pytest

from core.units import AU, MOLAR, PER_MOLAR, Q_, ensure_quantity, strip_units, to_base_units, validate_association_constant, validate_concentration

# ---------------------------------------------------------------------------
# validate_concentration
# ---------------------------------------------------------------------------


class TestValidateConcentration:
    """Tests for validate_concentration()."""

    def test_bare_float_passthrough(self):
        assert validate_concentration(1e-6) == 1e-6

    def test_quantity_molar(self):
        assert validate_concentration(Q_(1e-6, 'M')) == pytest.approx(1e-6)

    def test_quantity_micromolar(self):
        assert validate_concentration(Q_(10, 'µM')) == pytest.approx(10e-6)

    def test_quantity_nanomolar(self):
        assert validate_concentration(Q_(500, 'nM')) == pytest.approx(500e-9)

    def test_wrong_dimensionality_raises(self):
        with pytest.raises(pint.DimensionalityError):
            validate_concentration(Q_(1e6, '1/M'))

    def test_dimensionless_raises(self):
        with pytest.raises(pint.DimensionalityError):
            validate_concentration(Q_(1.0, ''))


# ---------------------------------------------------------------------------
# validate_association_constant
# ---------------------------------------------------------------------------


class TestValidateAssociationConstant:
    """Tests for validate_association_constant()."""

    def test_bare_float_passthrough(self):
        assert validate_association_constant(5e5) == 5e5

    def test_quantity_per_molar(self):
        assert validate_association_constant(Q_(5e5, '1/M')) == pytest.approx(5e5)

    def test_quantity_per_molar_caret(self):
        assert validate_association_constant(Q_(5e5, 'M^-1')) == pytest.approx(5e5)

    def test_quantity_per_micromolar(self):
        """1 µM⁻¹ = 1e6 M⁻¹"""
        assert validate_association_constant(Q_(1, 'µM**-1')) == pytest.approx(1e6)

    def test_wrong_dimensionality_raises(self):
        with pytest.raises(pint.DimensionalityError):
            validate_association_constant(Q_(10, 'µM'))

    def test_dimensionless_raises(self):
        with pytest.raises(pint.DimensionalityError):
            validate_association_constant(Q_(1.0, ''))


# ---------------------------------------------------------------------------
# to_base_units
# ---------------------------------------------------------------------------


class TestToBaseUnits:
    """Tests for to_base_units()."""

    def test_float_passthrough(self):
        assert to_base_units(1e-6, 'M') == 1e-6

    def test_quantity_converted(self):
        assert to_base_units(Q_(10, 'µM'), 'M') == pytest.approx(10e-6)

    def test_array_passthrough(self):
        arr = np.array([1e-6, 2e-6])
        result = to_base_units(arr, 'M')
        np.testing.assert_array_equal(result, arr)

    def test_quantity_array(self):
        arr = Q_(np.array([10, 20]), 'µM')
        result = to_base_units(arr, 'M')
        np.testing.assert_allclose(result, [10e-6, 20e-6])

    def test_incompatible_raises(self):
        with pytest.raises(pint.DimensionalityError):
            to_base_units(Q_(1, 'M'), '1/M')


# ---------------------------------------------------------------------------
# strip_units / ensure_quantity
# ---------------------------------------------------------------------------


class TestStripAndEnsure:
    """Tests for strip_units() and ensure_quantity()."""

    def test_strip_units_converts(self):
        assert strip_units(Q_(10, 'µM')) == pytest.approx(10e-6)

    def test_strip_units_custom_target(self):
        assert strip_units(Q_(1e-6, 'M'), 'µM') == pytest.approx(1.0)

    def test_ensure_quantity_float(self):
        q = ensure_quantity(1e-6)
        assert q.magnitude == 1e-6
        assert str(q.units) == 'molar'

    def test_ensure_quantity_already_quantity(self):
        q = ensure_quantity(Q_(10, 'µM'))
        assert q.magnitude == 10
        assert 'micromolar' in str(q.units)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Verify canonical unit string constants."""

    def test_molar_parseable(self):
        q = Q_(1, MOLAR)
        assert q.dimensionality == {'[length]': -3, '[substance]': 1}

    def test_per_molar_parseable(self):
        q = Q_(1, PER_MOLAR)
        assert q.dimensionality == {'[length]': 3, '[substance]': -1}

    def test_au_parseable(self):
        q = Q_(1, AU)
        assert q.dimensionless
