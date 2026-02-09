"""P1: Parameter recovery tests.

Fit synthetic data generated from known parameters and verify the optimizer
recovers the ground truth within tolerance.

What we test:
- Ka (association constant) recovery: Ka controls the SHAPE of the binding
  curve and is always identifiable.
- Fit quality (R²): verifies the optimizer found a good fit.
- Signal reconstruction: predicted signal should match observed data.

What we do NOT test:
- Individual signal coefficient recovery (I0, I_dye_free, I_dye_bound).
  These have structural degeneracies in DBA and IDA because
  sum([D_free] + [HD]) = const for the fixed species.  Different (I0,
  I_dye_free, I_dye_bound) triplets produce identical signals.

Tolerance:
- Clean data:  10% for Ka, R² > 0.999
- Noisy data (5% Gaussian): 20% for Ka
"""

import numpy as np
import pytest

from core.assays.dba import DBAAssay
from core.assays.dye_alone import DyeAloneAssay
from core.assays.gda import GDAAssay
from core.assays.ida import IDAAssay
from core.pipeline.fit_pipeline import FitConfig, fit_assay, fit_linear_assay
from tests.conftest import RECOVERY_BOUNDS, assert_within_tolerance

CLEAN_TOL = 0.10  # 10% for clean synthetic data
NOISY_TOL = 0.20  # 20% for 5% Gaussian noise
N_TRIALS = 200  # More trials for reliable convergence
N_TRIALS_GDA = 200  # GDA needs more trials (competitive model is harder to fit)


def _fit_config(n_trials: int = N_TRIALS) -> FitConfig:
    """Standard FitConfig for recovery tests."""
    return FitConfig(
        n_trials=n_trials,
        log_scale_params=[0],
        custom_bounds=RECOVERY_BOUNDS,
    )


# ---------------------------------------------------------------------------
# DBA recovery
# ---------------------------------------------------------------------------


class TestDBARecovery:
    """DBA: recover Ka_dye from synthetic direct binding data."""

    def test_dba_recovers_ka_dye_clean(self, dba_clean):
        """Ka_dye recovered within 10% on clean data."""
        x, y, true = dba_clean
        assay = DBAAssay(x_data=x, y_data=y, fixed_conc=true['fixed_conc'], mode='DtoH')
        result = fit_assay(assay, _fit_config())

        assert result.success
        assert result.r_squared > 0.999
        assert_within_tolerance(result.params_dict['Ka_dye'], true['Ka_dye'], CLEAN_TOL, 'Ka_dye')

    def test_dba_signal_reconstruction_clean(self, dba_clean):
        """Fitted model reconstructs the observed signal within 1%."""
        x, y, true = dba_clean
        assay = DBAAssay(x_data=x, y_data=y, fixed_conc=true['fixed_conc'], mode='DtoH')
        result = fit_assay(assay, _fit_config())

        y_pred = assay.forward_model(result.params)
        max_rel_err = np.max(np.abs(y_pred - y) / np.abs(y))
        assert max_rel_err < 0.01, f'Max point-wise relative error {max_rel_err:.2%} > 1%'

    def test_dba_recovers_ka_dye_noisy(self, dba_noisy):
        """Ka_dye recovered within 20% on noisy data."""
        x, y, true = dba_noisy
        assay = DBAAssay(x_data=x, y_data=y, fixed_conc=true['fixed_conc'], mode='DtoH')
        result = fit_assay(assay, _fit_config())

        assert result.success
        assert_within_tolerance(result.params_dict['Ka_dye'], true['Ka_dye'], NOISY_TOL, 'Ka_dye')


# ---------------------------------------------------------------------------
# GDA recovery
# ---------------------------------------------------------------------------


class TestGDARecovery:
    """GDA: recover Ka_guest from synthetic competitive binding data."""

    def test_gda_recovers_ka_guest_clean(self, gda_clean):
        """Ka_guest recovered within 10% on clean data."""
        x, y, true = gda_clean
        assay = GDAAssay(x_data=x, y_data=y, Ka_dye=true['Ka_dye'], h0=true['h0'], g0=true['g0'])
        result = fit_assay(assay, _fit_config(n_trials=N_TRIALS_GDA))

        assert result.success
        assert result.r_squared > 0.999
        assert_within_tolerance(result.params_dict['Ka_guest'], true['Ka_guest'], CLEAN_TOL, 'Ka_guest')

    def test_gda_signal_reconstruction_clean(self, gda_clean):
        """Fitted model reconstructs the observed signal within 5%."""
        x, y, true = gda_clean
        assay = GDAAssay(x_data=x, y_data=y, Ka_dye=true['Ka_dye'], h0=true['h0'], g0=true['g0'])
        result = fit_assay(assay, _fit_config(n_trials=N_TRIALS_GDA))

        y_pred = assay.forward_model(result.params)
        # GDA has weaker identifiability than DBA/IDA so we allow 5% reconstruction error
        max_rel_err = np.max(np.abs(y_pred - y) / np.abs(y))
        assert max_rel_err < 0.05, f'Max point-wise relative error {max_rel_err:.2%} > 5%'

    def test_gda_recovers_ka_guest_noisy(self, gda_noisy):
        """Ka_guest recovered within 20% on noisy data."""
        x, y, true = gda_noisy
        assay = GDAAssay(x_data=x, y_data=y, Ka_dye=true['Ka_dye'], h0=true['h0'], g0=true['g0'])
        result = fit_assay(assay, _fit_config(n_trials=N_TRIALS_GDA))

        assert result.success
        assert_within_tolerance(result.params_dict['Ka_guest'], true['Ka_guest'], NOISY_TOL, 'Ka_guest')


# ---------------------------------------------------------------------------
# IDA recovery
# ---------------------------------------------------------------------------


class TestIDARecovery:
    """IDA: recover Ka_guest from synthetic indicator displacement data."""

    def test_ida_recovers_ka_guest_clean(self, ida_clean):
        """Ka_guest recovered within 10% on clean data."""
        x, y, true = ida_clean
        assay = IDAAssay(x_data=x, y_data=y, Ka_dye=true['Ka_dye'], h0=true['h0'], d0=true['d0'])
        result = fit_assay(assay, _fit_config())

        assert result.success
        assert result.r_squared > 0.999
        assert_within_tolerance(result.params_dict['Ka_guest'], true['Ka_guest'], CLEAN_TOL, 'Ka_guest')

    def test_ida_signal_reconstruction_clean(self, ida_clean):
        """Fitted model reconstructs the observed signal within 1%."""
        x, y, true = ida_clean
        assay = IDAAssay(x_data=x, y_data=y, Ka_dye=true['Ka_dye'], h0=true['h0'], d0=true['d0'])
        result = fit_assay(assay, _fit_config())

        y_pred = assay.forward_model(result.params)
        max_rel_err = np.max(np.abs(y_pred - y) / np.abs(y))
        assert max_rel_err < 0.01, f'Max point-wise relative error {max_rel_err:.2%} > 1%'

    def test_ida_recovers_ka_guest_noisy(self, ida_noisy):
        """Ka_guest recovered within 20% on noisy data."""
        x, y, true = ida_noisy
        assay = IDAAssay(x_data=x, y_data=y, Ka_dye=true['Ka_dye'], h0=true['h0'], d0=true['d0'])
        result = fit_assay(assay, _fit_config())

        assert result.success
        assert_within_tolerance(result.params_dict['Ka_guest'], true['Ka_guest'], NOISY_TOL, 'Ka_guest')


# ---------------------------------------------------------------------------
# DyeAlone recovery
# ---------------------------------------------------------------------------


class TestDyeAloneRecovery:
    """DyeAlone: recover slope and intercept from linear data."""

    def test_dye_alone_recovers_slope_clean(self, dye_alone_clean):
        """Slope recovered within 10% on clean data."""
        x, y, true = dye_alone_clean
        assay = DyeAloneAssay(x_data=x, y_data=y)
        result = fit_linear_assay(assay)

        assert result.success
        assert result.r_squared > 0.999
        assert_within_tolerance(result.params_dict['slope'], true['slope'], CLEAN_TOL, 'slope')

    def test_dye_alone_recovers_intercept_clean(self, dye_alone_clean):
        """Intercept recovered within 10% on clean data."""
        x, y, true = dye_alone_clean
        assay = DyeAloneAssay(x_data=x, y_data=y)
        result = fit_linear_assay(assay)

        assert result.success
        assert_within_tolerance(result.params_dict['intercept'], true['intercept'], CLEAN_TOL, 'intercept')
