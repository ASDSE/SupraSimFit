"""Assay-level tests for the stepwise 1:2 / 2:1 binding assays (HG2, H2G).

Covers the fail-fast contract on the fixed host concentration, the wiring
from the registry parameter order into the forward model, and end-to-end
parameter recovery on clean synthetic data.

Recovery uses tight (±20 %) signal-coefficient bounds — the realistic regime
where those coefficients come from a prior calibration.  As with DBA/IDA, the
signal coefficients are otherwise degenerate; with them constrained, the
stepwise association constants are recovered.
"""

import numpy as np
import pytest

from core.assays.h2g import H2GAssay
from core.assays.hg2 import HG2Assay
from core.pipeline.fit_pipeline import FitConfig, fit_assay
from core.units import Q_
from tests.conftest import (
    H2G_RECOVERY_BOUNDS,
    H2G_TRUE,
    HG2_RECOVERY_BOUNDS,
    HG2_TRUE,
    _make_h2g_data,
    _make_hg2_data,
    assert_within_tolerance,
)

N_TRIALS = 80
CLEAN_TOL = 0.10


class TestStepwiseAssayContracts:
    """Fixed host concentration is required, positive, and unit-bearing."""

    @pytest.mark.parametrize('assay_cls', [HG2Assay, H2GAssay])
    def test_missing_h0_raises(self, assay_cls):
        x = Q_(np.linspace(1e-6, 1e-3, 10), 'M')
        y = Q_(np.ones(10), 'au')
        with pytest.raises(ValueError, match='h0 is required'):
            assay_cls(x_data=x, y_data=y)

    @pytest.mark.parametrize('assay_cls', [HG2Assay, H2GAssay])
    def test_nonpositive_h0_raises(self, assay_cls):
        x = Q_(np.linspace(1e-6, 1e-3, 10), 'M')
        y = Q_(np.ones(10), 'au')
        with pytest.raises(ValueError, match='h0 must be positive'):
            assay_cls(x_data=x, y_data=y, h0=Q_(0.0, 'M'))

    @pytest.mark.parametrize('assay_cls', [HG2Assay, H2GAssay])
    def test_non_quantity_h0_raises(self, assay_cls):
        x = Q_(np.linspace(1e-6, 1e-3, 10), 'M')
        y = Q_(np.ones(10), 'au')
        with pytest.raises(TypeError, match='h0 must be a pint Quantity'):
            assay_cls(x_data=x, y_data=y, h0=3e-4)


class TestForwardModelWiring:
    """The assay must feed parameters into the forward model in the exact
    order declared by the registry.  Feeding the ground-truth parameters
    through the assay must reproduce the independently generated clean curve;
    a mis-ordered unpack (e.g. swapping two signal coefficients) would not.
    """

    def test_hg2_matches_named_signal(self):
        x, y_clean = _make_hg2_data(HG2_TRUE)
        assay = HG2Assay(x_data=Q_(x, 'M'), y_data=Q_(y_clean, 'au'), h0=Q_(HG2_TRUE['h0'], 'M'))
        params = assay.params_from_dict(HG2_TRUE)  # ordered by parameter_keys
        np.testing.assert_allclose(assay.forward_model(params).magnitude, y_clean, rtol=1e-12)

    def test_h2g_matches_named_signal(self):
        x, y_clean = _make_h2g_data(H2G_TRUE)
        assay = H2GAssay(x_data=Q_(x, 'M'), y_data=Q_(y_clean, 'au'), h0=Q_(H2G_TRUE['h0'], 'M'))
        params = assay.params_from_dict(H2G_TRUE)
        np.testing.assert_allclose(assay.forward_model(params).magnitude, y_clean, rtol=1e-12)


class TestStepwiseRecovery:
    """Clean-data recovery of both stepwise constants under calibrated signal
    bounds."""

    def test_hg2_recovers_both_constants(self):
        x, y = _make_hg2_data(HG2_TRUE)
        assay = HG2Assay(x_data=Q_(x, 'M'), y_data=Q_(y, 'au'), h0=Q_(HG2_TRUE['h0'], 'M'))
        result = fit_assay(assay, FitConfig(n_trials=N_TRIALS, custom_bounds=HG2_RECOVERY_BOUNDS, per_replica=False))

        assert result.success
        assert_within_tolerance(result.parameters['Ka_HG'], HG2_TRUE['Ka_HG'], CLEAN_TOL, 'Ka_HG')
        assert_within_tolerance(result.parameters['Ka_HG2'], HG2_TRUE['Ka_HG2'], CLEAN_TOL, 'Ka_HG2')

    def test_h2g_recovers_both_constants(self):
        x, y = _make_h2g_data(H2G_TRUE)
        assay = H2GAssay(x_data=Q_(x, 'M'), y_data=Q_(y, 'au'), h0=Q_(H2G_TRUE['h0'], 'M'))
        result = fit_assay(assay, FitConfig(n_trials=N_TRIALS, custom_bounds=H2G_RECOVERY_BOUNDS, per_replica=False))

        assert result.success
        assert_within_tolerance(result.parameters['Ka_HG'], H2G_TRUE['Ka_HG'], CLEAN_TOL, 'Ka_HG')
        assert_within_tolerance(result.parameters['Ka_H2G'], H2G_TRUE['Ka_H2G'], CLEAN_TOL, 'Ka_H2G')
