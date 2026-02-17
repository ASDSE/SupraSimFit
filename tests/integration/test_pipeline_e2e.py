"""P6: End-to-end integration tests for the fitting pipeline.

Exercises the full pipeline: assay construction → fit_assay() / fit_linear_assay()
→ FitResult validation.  Complements P1 (parameter recovery) by testing:

- FitResult structure, metadata, and serialization
- FitConfig customization (bounds overrides, log-scale overrides, n_trials)
- Chained workflow: dye-alone calibration → bounds derivation → downstream fit
- Failure modes (unknown params, wrong bounds)

Tolerance:
- Clean data:  10% for Ka, R² > 0.999
- Noisy data (5% Gaussian): 25% for Ka
"""

import numpy as np
import pytest

from core.assays.dba import DBAAssay
from core.assays.dye_alone import DyeAloneAssay
from core.assays.gda import GDAAssay
from core.assays.ida import IDAAssay
from core.pipeline.fit_pipeline import (
    FitConfig,
    FitResult,
    bounds_from_dye_alone,
    fit_assay,
    fit_linear_assay,
)
from tests.conftest import (
    DBA_RECOVERY_BOUNDS,
    GDA_IDA_RECOVERY_BOUNDS,
    assert_within_tolerance,
)

CLEAN_TOL = 0.10
NOISY_TOL = 0.25
N_TRIALS = 200

# Dye-alone ground truth CONSISTENT with binding assay signal coefficients.
# The dye-alone slope = I_dye_free and intercept = I0 from the binding model.
# (The conftest DYE_ALONE_TRUE uses different values, so we define our own.)
_CHAIN_DYE_ALONE_TRUE = {
    'slope': 5e7,   # matches DBA_TRUE['I_dye_free']
    'intercept': 0.0,  # matches DBA_TRUE['I0']
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dba_assay(fixture_data):
    x, y, true = fixture_data
    return DBAAssay(x_data=x, y_data=y, fixed_conc=true['fixed_conc'], mode='DtoH'), true


def _gda_assay(fixture_data):
    x, y, true = fixture_data
    return GDAAssay(x_data=x, y_data=y, Ka_dye=true['Ka_dye'], h0=true['h0'], g0=true['g0']), true


def _ida_assay(fixture_data):
    x, y, true = fixture_data
    return IDAAssay(x_data=x, y_data=y, Ka_dye=true['Ka_dye'], h0=true['h0'], d0=true['d0']), true


def _dye_alone_assay(fixture_data):
    x, y, true = fixture_data
    return DyeAloneAssay(x_data=x, y_data=y), true


# ---------------------------------------------------------------------------
# DBA end-to-end
# ---------------------------------------------------------------------------


class TestDBAEndToEnd:

    def test_clean_round_trip(self, dba_clean):
        assay, true = _dba_assay(dba_clean)
        result = fit_assay(assay, FitConfig(n_trials=N_TRIALS, custom_bounds=DBA_RECOVERY_BOUNDS))

        assert result.success
        assert result.r_squared > 0.999
        assert_within_tolerance(result.parameters['Ka_dye'], true['Ka_dye'], CLEAN_TOL, 'Ka_dye')

    def test_noisy_round_trip(self, dba_noisy):
        assay, true = _dba_assay(dba_noisy)
        result = fit_assay(assay, FitConfig(n_trials=N_TRIALS, custom_bounds=DBA_RECOVERY_BOUNDS))

        assert result.success
        assert_within_tolerance(result.parameters['Ka_dye'], true['Ka_dye'], NOISY_TOL, 'Ka_dye')

    def test_fit_result_structure(self, dba_clean):
        assay, true = _dba_assay(dba_clean)
        result = fit_assay(assay, FitConfig(n_trials=N_TRIALS, custom_bounds=DBA_RECOVERY_BOUNDS))

        # Type and model
        assert result.assay_type == 'DBA_DtoH'
        assert result.model_name == 'equilibrium_4param'

        # Parameters populated
        for key in ('Ka_dye', 'I0', 'I_dye_free', 'I_dye_bound'):
            assert key in result.parameters
            assert key in result.uncertainties

        # Arrays match shape
        assert result.x_fit.shape == result.y_fit.shape

        # Counts
        assert result.n_passing > 0
        assert result.n_total >= result.n_passing

        # Conditions
        assert 'fixed_conc' in result.conditions

        # FitConfig snapshot
        assert 'n_trials' in result.fit_config

        # UUID and timestamp populated
        assert len(result.id) > 0
        assert len(result.timestamp) > 0


# ---------------------------------------------------------------------------
# GDA end-to-end
# ---------------------------------------------------------------------------


class TestGDAEndToEnd:

    def test_clean_round_trip(self, gda_clean):
        assay, true = _gda_assay(gda_clean)
        result = fit_assay(assay, FitConfig(n_trials=N_TRIALS, custom_bounds=GDA_IDA_RECOVERY_BOUNDS))

        assert result.success
        assert result.r_squared > 0.999
        assert_within_tolerance(result.parameters['Ka_guest'], true['Ka_guest'], CLEAN_TOL, 'Ka_guest')

    def test_noisy_round_trip(self, gda_noisy):
        assay, true = _gda_assay(gda_noisy)
        result = fit_assay(assay, FitConfig(n_trials=N_TRIALS, custom_bounds=GDA_IDA_RECOVERY_BOUNDS))

        assert result.success
        assert_within_tolerance(result.parameters['Ka_guest'], true['Ka_guest'], NOISY_TOL, 'Ka_guest')


# ---------------------------------------------------------------------------
# IDA end-to-end
# ---------------------------------------------------------------------------


class TestIDAEndToEnd:

    def test_clean_round_trip(self, ida_clean):
        assay, true = _ida_assay(ida_clean)
        result = fit_assay(assay, FitConfig(n_trials=N_TRIALS, custom_bounds=GDA_IDA_RECOVERY_BOUNDS))

        assert result.success
        assert result.r_squared > 0.999
        assert_within_tolerance(result.parameters['Ka_guest'], true['Ka_guest'], CLEAN_TOL, 'Ka_guest')

    def test_noisy_round_trip(self, ida_noisy):
        assay, true = _ida_assay(ida_noisy)
        result = fit_assay(assay, FitConfig(n_trials=N_TRIALS, custom_bounds=GDA_IDA_RECOVERY_BOUNDS))

        assert result.success
        assert_within_tolerance(result.parameters['Ka_guest'], true['Ka_guest'], NOISY_TOL, 'Ka_guest')


# ---------------------------------------------------------------------------
# DyeAlone end-to-end
# ---------------------------------------------------------------------------


class TestDyeAloneEndToEnd:

    def test_linear_fit_round_trip(self, dye_alone_clean):
        assay, true = _dye_alone_assay(dye_alone_clean)
        result = fit_linear_assay(assay)

        assert result.success
        assert result.r_squared > 0.999
        assert_within_tolerance(result.parameters['slope'], true['slope'], CLEAN_TOL, 'slope')
        assert_within_tolerance(result.parameters['intercept'], true['intercept'], CLEAN_TOL, 'intercept')

    def test_metadata(self, dye_alone_clean):
        assay, _ = _dye_alone_assay(dye_alone_clean)
        result = fit_linear_assay(assay)

        assert result.assay_type == 'DYE_ALONE'
        assert result.model_name == 'linear'
        assert result.metadata.get('method') == 'linear_regression'
        assert result.n_passing == 1
        assert result.n_total == 1


# ---------------------------------------------------------------------------
# FitConfig customization
# ---------------------------------------------------------------------------


class TestFitConfigCustomization:

    def test_custom_bounds_override(self, dba_clean):
        """Tight Ka bounds around truth still converge."""
        assay, true = _dba_assay(dba_clean)
        tight_bounds = {
            **DBA_RECOVERY_BOUNDS,
            'Ka_dye': (true['Ka_dye'] * 0.5, true['Ka_dye'] * 2.0),
        }
        result = fit_assay(assay, FitConfig(n_trials=N_TRIALS, custom_bounds=tight_bounds))

        assert result.success
        assert_within_tolerance(result.parameters['Ka_dye'], true['Ka_dye'], CLEAN_TOL, 'Ka_dye')

    def test_log_scale_override_empty(self, dba_clean):
        """Forcing linear sampling (log_scale_params=[]) still succeeds with tight bounds."""
        assay, true = _dba_assay(dba_clean)
        tight_ka = {
            **DBA_RECOVERY_BOUNDS,
            'Ka_dye': (true['Ka_dye'] * 0.5, true['Ka_dye'] * 2.0),
        }
        result = fit_assay(assay, FitConfig(
            n_trials=N_TRIALS,
            custom_bounds=tight_ka,
            log_scale_params=[],
        ))

        assert result.success

    def test_relaxed_min_r_squared_passes_more(self, dba_clean):
        """Relaxing min_r_squared allows more fits to pass filtering."""
        assay, _ = _dba_assay(dba_clean)
        config_strict = FitConfig(n_trials=50, custom_bounds=DBA_RECOVERY_BOUNDS, min_r_squared=0.999)
        config_relaxed = FitConfig(n_trials=50, custom_bounds=DBA_RECOVERY_BOUNDS, min_r_squared=0.0)

        result_strict = fit_assay(assay, config_strict)
        result_relaxed = fit_assay(assay, config_relaxed)

        assert result_relaxed.n_passing >= result_strict.n_passing


# ---------------------------------------------------------------------------
# Chained workflow: dye-alone → downstream fit
# ---------------------------------------------------------------------------


class TestChainedWorkflow:
    """Test the calibration chain: dye-alone → derive signal bounds → downstream fit.

    Uses dye-alone ground truth consistent with binding assay I_dye_free/I0,
    since the conftest DYE_ALONE_TRUE uses different (unrelated) values.
    """

    def _consistent_dye_alone_assay(self):
        """Build a dye-alone assay with signal params matching binding assays."""
        from core.models.linear import linear_signal
        x = np.linspace(0, 20e-6, 15)
        y = linear_signal(_CHAIN_DYE_ALONE_TRUE['slope'], _CHAIN_DYE_ALONE_TRUE['intercept'], x)
        return DyeAloneAssay(x_data=x, y_data=y)

    def _dye_alone_bounds(self):
        """Fit consistent dye-alone and derive signal bounds."""
        assay = self._consistent_dye_alone_assay()
        dye_result = fit_linear_assay(assay)
        assert dye_result.success
        return bounds_from_dye_alone(dye_result, margin=0.2)

    def test_dye_alone_to_dba(self, dba_clean):
        signal_bounds = self._dye_alone_bounds()
        assay, true = _dba_assay(dba_clean)

        # Dye-alone constrains I_dye_free and I0; I_dye_bound still needs
        # separate bounds (not observable in dye-alone experiment).
        config = FitConfig(
            n_trials=N_TRIALS,
            custom_bounds={
                **DBA_RECOVERY_BOUNDS,       # I_dye_bound + Ka_dye defaults
                **signal_bounds,              # override I_dye_free and I0
            },
        )
        result = fit_assay(assay, config)

        assert result.success
        assert_within_tolerance(result.parameters['Ka_dye'], true['Ka_dye'], CLEAN_TOL, 'Ka_dye')

    def test_dye_alone_to_gda(self, gda_clean):
        signal_bounds = self._dye_alone_bounds()
        assay, true = _gda_assay(gda_clean)

        config = FitConfig(
            n_trials=N_TRIALS,
            custom_bounds={
                **GDA_IDA_RECOVERY_BOUNDS,
                **signal_bounds,
            },
        )
        result = fit_assay(assay, config)

        assert result.success
        assert_within_tolerance(result.parameters['Ka_guest'], true['Ka_guest'], CLEAN_TOL, 'Ka_guest')

    def test_dye_alone_to_ida(self, ida_clean):
        signal_bounds = self._dye_alone_bounds()
        assay, true = _ida_assay(ida_clean)

        config = FitConfig(
            n_trials=N_TRIALS,
            custom_bounds={
                **GDA_IDA_RECOVERY_BOUNDS,
                **signal_bounds,
            },
        )
        result = fit_assay(assay, config)

        assert result.success
        assert_within_tolerance(result.parameters['Ka_guest'], true['Ka_guest'], CLEAN_TOL, 'Ka_guest')

    def test_bounds_from_dye_alone_values(self, dye_alone_clean):
        """Verify derived bounds bracket the known truth."""
        assay, true = _dye_alone_assay(dye_alone_clean)
        dye_result = fit_linear_assay(assay)
        bounds = bounds_from_dye_alone(dye_result, margin=0.2)

        # I_dye_free bounds should bracket the true slope (≈ I_dye_free)
        lo, hi = bounds['I_dye_free']
        assert lo > 0
        assert lo < true['slope'] < hi

        # I0 bounds should bracket the true intercept
        lo, hi = bounds['I0']
        assert lo <= true['intercept'] <= hi


# ---------------------------------------------------------------------------
# FitResult serialization
# ---------------------------------------------------------------------------


class TestFitResultSerialization:

    def test_to_dict_round_trip(self, dba_clean):
        assay, _ = _dba_assay(dba_clean)
        result = fit_assay(assay, FitConfig(n_trials=50, custom_bounds=DBA_RECOVERY_BOUNDS))

        d = result.to_dict()
        restored = FitResult.from_dict(d)

        assert restored.parameters == result.parameters
        assert restored.uncertainties == result.uncertainties
        assert restored.rmse == pytest.approx(result.rmse)
        assert restored.r_squared == pytest.approx(result.r_squared)
        assert restored.n_passing == result.n_passing
        assert restored.n_total == result.n_total
        assert restored.assay_type == result.assay_type
        assert restored.model_name == result.model_name
        assert restored.id == result.id
        np.testing.assert_array_almost_equal(restored.x_fit, result.x_fit)
        np.testing.assert_array_almost_equal(restored.y_fit, result.y_fit)

    def test_success_property(self):
        """success is True iff n_passing > 0."""
        r1 = FitResult(
            parameters={}, uncertainties={}, rmse=0.0, r_squared=1.0,
            n_passing=5, n_total=10, x_fit=np.array([]), y_fit=np.array([]),
            assay_type='test', model_name='test',
        )
        assert r1.success is True

        r2 = FitResult(
            parameters={}, uncertainties={}, rmse=np.inf, r_squared=0.0,
            n_passing=0, n_total=10, x_fit=np.array([]), y_fit=np.array([]),
            assay_type='test', model_name='test',
        )
        assert r2.success is False


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


class TestFailureModes:

    def test_unknown_custom_bounds_key_raises(self, dba_clean):
        assay, _ = _dba_assay(dba_clean)
        config = FitConfig(custom_bounds={'bogus_param': (0, 1)})
        with pytest.raises(ValueError, match='Unknown parameter'):
            fit_assay(assay, config)

    def test_unknown_log_scale_param_raises(self, dba_clean):
        assay, _ = _dba_assay(dba_clean)
        config = FitConfig(
            custom_bounds=DBA_RECOVERY_BOUNDS,
            log_scale_params=['nonexistent'],
        )
        with pytest.raises(ValueError, match='Unknown log-scale parameter'):
            fit_assay(assay, config)

    def test_very_wrong_bounds_no_crash(self, dba_clean):
        """Extremely wrong Ka bounds produce a result (no exception)."""
        assay, true = _dba_assay(dba_clean)
        wrong_bounds = {
            **DBA_RECOVERY_BOUNDS,
            'Ka_dye': (1e-15, 1e-14),  # far from truth
        }
        result = fit_assay(assay, FitConfig(n_trials=20, custom_bounds=wrong_bounds))

        # Should return a FitResult (no crash), but Ka will be wrong
        assert isinstance(result, FitResult)

    def test_bounds_from_dye_alone_rejects_nonlinear(self, dba_clean):
        """bounds_from_dye_alone raises on non-linear FitResult."""
        assay, _ = _dba_assay(dba_clean)
        result = fit_assay(assay, FitConfig(n_trials=50, custom_bounds=DBA_RECOVERY_BOUNDS))
        with pytest.raises(ValueError, match='linear'):
            bounds_from_dye_alone(result)
