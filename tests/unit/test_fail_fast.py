"""P3: Fail-fast contract tests.

Verify that assay constructors and core functions reject invalid inputs
immediately with clear error messages, rather than silently corrupting.
"""

import numpy as np
import pytest

from core.assays.dba import DBAAssay
from core.assays.dye_alone import DyeAloneAssay
from core.assays.gda import GDAAssay
from core.assays.ida import IDAAssay
from core.assays.registry import AssayType
from core.units import Q_


class TestGDAFailFast:
    """GDA constructor rejects invalid inputs."""

    def _valid_kwargs(self):
        return dict(
            x_data=Q_(np.linspace(0, 10e-6, 5), 'M'),
            y_data=Q_(np.ones(5), 'au'),
            Ka_dye=Q_(1e6, '1/M'),
            h0=Q_(10e-6, 'M'),
            g0=Q_(5e-6, 'M'),
        )

    def test_missing_ka_dye_raises(self):
        kw = self._valid_kwargs()
        del kw['Ka_dye']
        with pytest.raises(ValueError, match='Ka_dye is required'):
            GDAAssay(**kw)

    def test_missing_h0_raises(self):
        kw = self._valid_kwargs()
        del kw['h0']
        with pytest.raises(ValueError, match='h0 is required'):
            GDAAssay(**kw)

    def test_missing_g0_raises(self):
        kw = self._valid_kwargs()
        del kw['g0']
        with pytest.raises(ValueError, match='g0 is required'):
            GDAAssay(**kw)

    def test_negative_ka_dye_raises(self):
        kw = self._valid_kwargs()
        kw['Ka_dye'] = Q_(-1e6, '1/M')
        with pytest.raises(ValueError, match='Ka_dye must be positive'):
            GDAAssay(**kw)

    def test_zero_h0_raises(self):
        kw = self._valid_kwargs()
        kw['h0'] = Q_(0.0, 'M')
        with pytest.raises(ValueError, match='h0.*must be positive'):
            GDAAssay(**kw)

    def test_negative_g0_raises(self):
        kw = self._valid_kwargs()
        kw['g0'] = Q_(-1e-6, 'M')
        with pytest.raises(ValueError, match='g0.*must be positive'):
            GDAAssay(**kw)

    def test_mismatched_data_shapes_raises(self):
        kw = self._valid_kwargs()
        kw['y_data'] = Q_(np.ones(3), 'au')  # Different length than x_data
        with pytest.raises(ValueError, match='same shape'):
            GDAAssay(**kw)


class TestIDAFailFast:
    """IDA constructor rejects invalid inputs."""

    def _valid_kwargs(self):
        return dict(
            x_data=Q_(np.linspace(0, 10e-6, 5), 'M'),
            y_data=Q_(np.ones(5), 'au'),
            Ka_dye=Q_(1e6, '1/M'),
            h0=Q_(10e-6, 'M'),
            d0=Q_(1e-6, 'M'),
        )

    def test_missing_ka_dye_raises(self):
        kw = self._valid_kwargs()
        del kw['Ka_dye']
        with pytest.raises(ValueError, match='Ka_dye is required'):
            IDAAssay(**kw)

    def test_missing_h0_raises(self):
        kw = self._valid_kwargs()
        del kw['h0']
        with pytest.raises(ValueError, match='h0 is required'):
            IDAAssay(**kw)

    def test_missing_d0_raises(self):
        kw = self._valid_kwargs()
        del kw['d0']
        with pytest.raises(ValueError, match='d0 is required'):
            IDAAssay(**kw)

    def test_negative_ka_dye_raises(self):
        kw = self._valid_kwargs()
        kw['Ka_dye'] = Q_(-1.0, '1/M')
        with pytest.raises(ValueError, match='Ka_dye must be positive'):
            IDAAssay(**kw)

    def test_zero_d0_raises(self):
        kw = self._valid_kwargs()
        kw['d0'] = Q_(0.0, 'M')
        with pytest.raises(ValueError, match='d0.*must be positive'):
            IDAAssay(**kw)


class TestDBAFailFast:
    """DBA constructor rejects invalid inputs."""

    def _valid_kwargs(self):
        return dict(
            x_data=Q_(np.linspace(0, 10e-6, 5), 'M'),
            y_data=Q_(np.ones(5), 'au'),
            fixed_conc=Q_(10e-6, 'M'),
            mode='DtoH',
        )

    def test_missing_fixed_conc_raises(self):
        kw = self._valid_kwargs()
        del kw['fixed_conc']
        with pytest.raises(ValueError, match='fixed_conc is required'):
            DBAAssay(**kw)

    def test_negative_fixed_conc_raises(self):
        kw = self._valid_kwargs()
        kw['fixed_conc'] = Q_(-1e-6, 'M')
        with pytest.raises(ValueError, match='fixed_conc must be positive'):
            DBAAssay(**kw)

    def test_invalid_mode_raises(self):
        kw = self._valid_kwargs()
        kw['mode'] = 'invalid'
        with pytest.raises(ValueError, match='mode must be'):
            DBAAssay(**kw)

    def test_htod_mode_sets_correct_assay_type(self):
        kw = self._valid_kwargs()
        kw['mode'] = 'HtoD'
        assay = DBAAssay(**kw)
        assert assay.assay_type == AssayType.DBA_HtoD

    def test_dtoh_mode_sets_correct_assay_type(self):
        kw = self._valid_kwargs()
        assay = DBAAssay(**kw)
        assert assay.assay_type == AssayType.DBA_DtoH


class TestDyeAloneFailFast:
    """DyeAlone constructor rejects invalid inputs."""

    def test_mismatched_shapes_raises(self):
        with pytest.raises(ValueError, match='same shape'):
            DyeAloneAssay(
                x_data=Q_(np.array([1, 2, 3]), 'M'),
                y_data=Q_(np.array([1, 2]), 'au'),
            )

    def test_valid_construction(self):
        assay = DyeAloneAssay(
            x_data=Q_(np.array([0, 1e-6, 2e-6]), 'M'),
            y_data=Q_(np.array([100, 200, 300]), 'au'),
        )
        assert assay.assay_type == AssayType.DYE_ALONE
        assert assay.n_points == 3
        assert assay.n_params == 2


class TestBaseAssayContracts:
    """Base assay properties and methods work correctly."""

    def test_parameter_keys_from_registry(self):
        """Assay exposes correct parameter_keys from registry."""
        assay = GDAAssay(
            x_data=Q_(np.array([1e-6]), 'M'),
            y_data=Q_(np.array([100.0]), 'au'),
            Ka_dye=Q_(1e6, '1/M'),
            h0=Q_(10e-6, 'M'),
            g0=Q_(5e-6, 'M'),
        )
        assert assay.parameter_keys == ('Ka_guest', 'I0', 'I_dye_free', 'I_dye_bound')

    def test_params_to_dict(self):
        """params_to_dict maps array values to parameter names."""
        assay = GDAAssay(
            x_data=Q_(np.array([1e-6]), 'M'),
            y_data=Q_(np.array([100.0]), 'au'),
            Ka_dye=Q_(1e6, '1/M'),
            h0=Q_(10e-6, 'M'),
            g0=Q_(5e-6, 'M'),
        )
        params = np.array([1.5e6, 50.0, 1000.0, 5000.0])
        d = assay.params_to_dict(params)
        assert d == {
            'Ka_guest': 1.5e6,
            'I0': 50.0,
            'I_dye_free': 1000.0,
            'I_dye_bound': 5000.0,
        }

    def test_residuals_correct(self):
        """Residuals = observed - predicted."""
        assay = DyeAloneAssay(
            x_data=Q_(np.array([0, 1e-6, 2e-6]), 'M'),
            y_data=Q_(np.array([100.0, 200.0, 300.0]), 'au'),
        )
        params = np.array([1e8, 100.0])  # slope, intercept
        resid = assay.residuals(params)
        expected = assay.y_data - assay.forward_model(params)
        np.testing.assert_array_equal(resid.magnitude, expected.magnitude)

    def test_sum_squared_residuals(self):
        """SSR is sum of squared residuals."""
        assay = DyeAloneAssay(
            x_data=Q_(np.array([0, 1e-6, 2e-6]), 'M'),
            y_data=Q_(np.array([100.0, 200.0, 300.0]), 'au'),
        )
        params = np.array([1e8, 100.0])
        ssr = assay.sum_squared_residuals(params)
        expected = float(np.sum(assay.residuals(params).magnitude ** 2))
        assert ssr == pytest.approx(expected)
