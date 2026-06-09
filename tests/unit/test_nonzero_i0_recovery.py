"""Recovery test with non-zero I0 (Option-1 from Phase-1 binding-model survey).

The shared-conftest synthetic ground truth uses ``I0 = 0`` to minimise the
signal-coefficient identifiability degeneracy (see ``docs/scientific-summary.md``
§5).  This test exercises the realistic regime where ``I0`` is non-zero,
using the same tight ±20 % bounds on signal coefficients that the standard
recovery suite uses.  The objective is parameter recovery for ``Ka`` only —
individual signal coefficients remain non-identifiable.

IDA is the single representative: I0 enters every model as the same additive
baseline term and the fit machinery is shared, so one assay family suffices
to guard the non-zero-I0 degeneracy regime.
"""

import numpy as np

from core.assays.ida import IDAAssay
from core.models.equilibrium import ida_signal
from core.pipeline.fit_pipeline import FitConfig, fit_assay
from core.units import Q_
from tests.conftest import (
    GDA_IDA_RECOVERY_BOUNDS,
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
