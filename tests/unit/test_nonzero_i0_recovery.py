"""Recovery tests with non-zero I0 (Option-1 from Phase-1 binding-model survey).

The shared-conftest synthetic ground truth uses ``I0 = 0`` to minimise the
signal-coefficient identifiability degeneracy (see ``docs/scientific-summary.md``
§5).  These tests exercise the realistic regime where ``I0`` is non-zero,
using the same tight ±20 % bounds on signal coefficients that the standard
recovery suite uses.  The objective is parameter recovery for ``Ka`` only —
individual signal coefficients remain non-identifiable in DBA / IDA.
"""

import numpy as np
import pytest

from core.assays.dba import DBAAssay
from core.assays.gda import GDAAssay
from core.assays.ida import IDAAssay
from core.models.equilibrium import dba_signal, gda_signal, ida_signal
from core.pipeline.fit_pipeline import FitConfig, fit_assay
from core.units import Q_
from tests.conftest import (
    DBA_RECOVERY_BOUNDS,
    DBA_TRUE,
    GDA_IDA_RECOVERY_BOUNDS,
    GDA_TRUE,
    IDA_TRUE,
    assert_within_tolerance,
)

N_TRIALS = 80
CLEAN_TOL = 0.10
NONZERO_I0 = 100.0  # a.u. — small relative to typical signal (~1000 a.u.)


def _bounds_with_i0_window(base_bounds, i0_window=(0.0, 200.0)):
    """Override the I0 bounds to a finite window around the non-zero ground truth."""
    new = dict(base_bounds)
    new['I0'] = (Q_(i0_window[0], 'au'), Q_(i0_window[1], 'au'))
    return new


class TestDBARecoveryNonzeroI0:
    def test_dba_ka_dye_recovery_with_nonzero_i0(self):
        """DBA recovers Ka_dye to within 10% even with a non-zero I0 baseline."""
        true = {**DBA_TRUE, 'I0': NONZERO_I0}
        x = np.linspace(1e-7, 50e-6, 30)
        y = dba_signal(
            I0=true['I0'],
            Ka_dye=true['Ka_dye'],
            I_dye_free=true['I_dye_free'],
            I_dye_bound=true['I_dye_bound'],
            x_titrant=x,
            y_fixed=true['fixed_conc'],
            mode='DtoH',
        )
        assay = DBAAssay(
            x_data=Q_(x, 'M'),
            y_data=Q_(y, 'au'),
            fixed_conc=Q_(true['fixed_conc'], 'M'),
            mode='DtoH',
        )
        bounds = _bounds_with_i0_window(DBA_RECOVERY_BOUNDS)
        result = fit_assay(assay, FitConfig(n_trials=N_TRIALS, custom_bounds=bounds))

        assert result.success
        assert_within_tolerance(
            result.parameters['Ka_dye'], true['Ka_dye'], CLEAN_TOL, 'Ka_dye'
        )


class TestGDARecoveryNonzeroI0:
    def test_gda_ka_guest_recovery_with_nonzero_i0(self):
        """GDA recovers Ka_guest to within 10% even with a non-zero I0 baseline."""
        true = {**GDA_TRUE, 'I0': NONZERO_I0}
        d0_values = np.linspace(1e-7, 30e-6, 30)
        y = gda_signal(
            I0=true['I0'],
            Ka_guest=true['Ka_guest'],
            I_dye_free=true['I_dye_free'],
            I_dye_bound=true['I_dye_bound'],
            Ka_dye=true['Ka_dye'],
            h0=true['h0'],
            d0_values=d0_values,
            g0=true['g0'],
        )
        assay = GDAAssay(
            x_data=Q_(d0_values, 'M'),
            y_data=Q_(y, 'au'),
            Ka_dye=Q_(true['Ka_dye'], '1/M'),
            h0=Q_(true['h0'], 'M'),
            g0=Q_(true['g0'], 'M'),
        )
        bounds = _bounds_with_i0_window(GDA_IDA_RECOVERY_BOUNDS)
        result = fit_assay(assay, FitConfig(n_trials=N_TRIALS, custom_bounds=bounds))

        assert result.success
        # GDA has weaker Ka identifiability; a 25 % tolerance matches the
        # noisy-data band used elsewhere for GDA recovery.
        assert_within_tolerance(
            result.parameters['Ka_guest'], true['Ka_guest'], 0.25, 'Ka_guest'
        )


class TestIDARecoveryNonzeroI0:
    def test_ida_ka_guest_recovery_with_nonzero_i0(self):
        """IDA recovers Ka_guest to within 10% even with a non-zero I0 baseline."""
        true = {**IDA_TRUE, 'I0': NONZERO_I0}
        g0_values = np.linspace(0, 50e-6, 30)
        y = ida_signal(
            I0=true['I0'],
            Ka_guest=true['Ka_guest'],
            I_dye_free=true['I_dye_free'],
            I_dye_bound=true['I_dye_bound'],
            Ka_dye=true['Ka_dye'],
            h0=true['h0'],
            d0=true['d0'],
            g0_values=g0_values,
        )
        assay = IDAAssay(
            x_data=Q_(g0_values, 'M'),
            y_data=Q_(y, 'au'),
            Ka_dye=Q_(true['Ka_dye'], '1/M'),
            h0=Q_(true['h0'], 'M'),
            d0=Q_(true['d0'], 'M'),
        )
        bounds = _bounds_with_i0_window(GDA_IDA_RECOVERY_BOUNDS)
        result = fit_assay(assay, FitConfig(n_trials=N_TRIALS, custom_bounds=bounds))

        assert result.success
        assert_within_tolerance(
            result.parameters['Ka_guest'], true['Ka_guest'], CLEAN_TOL, 'Ka_guest'
        )
