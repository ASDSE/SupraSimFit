"""End-to-end tests of the fitting pipeline on synthetic data with known truth.

Exercises assay construction → fit → FitResult, for every binding model the app
registers: parameter recovery, what the reported interval covers, the chained
dye-alone calibration, and the refusals.

Tolerance:
- Clean data:  10% for Ka, R² > 0.999
- Noisy data (5% Gaussian): 25% for Ka
"""

import numpy as np
import pytest

from core.assays.dba import DBAAssay
from core.assays.dye_alone import DyeAloneAssay
from core.assays.gda import GDAAssay
from core.assays.h2g import H2GAssay
from core.assays.hg2 import HG2Assay
from core.assays.ida import IDAAssay
from core.data_processing.measurement_set import MeasurementSet
from core.models.equilibrium import dba_signal
from core.pipeline.diagnostics import Verdict
from core.pipeline.fit_pipeline import (
    FitConfig,
    FitResult,
    bounds_from_dye_alone,
    fit_assay,
    fit_linear_assay,
    fit_measurement_set,
    summarize_parameters,
)
from core.pipeline.inputs import TITRANT, ErrorModel, InputSpec
from core.units import Q_
from tests.conftest import (
    DBA_RECOVERY_BOUNDS,
    DBA_TRUE,
    DYE_ALONE_TRUE,
    GDA_IDA_RECOVERY_BOUNDS,
    H2G_RECOVERY_BOUNDS,
    H2G_TRUE,
    HG2_RECOVERY_BOUNDS,
    HG2_TRUE,
    IDA_TRUE,
    _make_dba_data,
    _make_h2g_data,
    _make_hg2_data,
    _make_ida_data,
    assert_within_tolerance,
)

CLEAN_TOL = 0.10
NOISY_TOL = 0.25

# Dye-alone ground truth CONSISTENT with binding assay signal coefficients.
# The dye-alone slope = I_dye_free and intercept = I0 from the binding model.
# (The conftest DYE_ALONE_TRUE uses different values, so we define our own.)
_CHAIN_DYE_ALONE_TRUE = {
    'slope': 5e7,  # matches DBA_TRUE['I_dye_free']
    'intercept': 0.0,  # matches DBA_TRUE['I0']
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dba_assay(fixture_data):
    x, y, true = fixture_data
    return DBAAssay(x_data=x, y_data=y, fixed_conc=Q_(true['fixed_conc'], 'M'), mode='DtoH'), true


def _gda_assay(fixture_data):
    x, y, true = fixture_data
    return GDAAssay(
        x_data=x, y_data=y, Ka_dye=Q_(true['Ka_dye'], '1/M'), h0=Q_(true['h0'], 'M'), g0=Q_(true['g0'], 'M')
    ), true


def _ida_assay(fixture_data):
    x, y, true = fixture_data
    return IDAAssay(
        x_data=x, y_data=y, Ka_dye=Q_(true['Ka_dye'], '1/M'), h0=Q_(true['h0'], 'M'), d0=Q_(true['d0'], 'M')
    ), true


def _dye_alone_assay(fixture_data):
    x, y, true = fixture_data
    return DyeAloneAssay(x_data=x, y_data=y), true


def _max_rel_err(assay, result, y):
    """Max point-wise relative error of the fitted model at the data points.

    Recomputes the model on the data grid, since ``x_fit``/``y_fit`` are a
    denser display curve not aligned 1:1 with the measured points.
    """
    params = np.array([result.parameters[k].magnitude for k in assay.parameter_keys])
    y_at_data = assay.forward_model(params)
    return np.max(np.abs((y_at_data - y).magnitude) / np.abs(y.magnitude))


def _interval_of(result: FitResult, key: str) -> tuple[float, float]:
    row = next(r for r in summarize_parameters(result) if r.key == key and not r.is_log)
    assert row.interval is not None, f'{key} must carry an interval'
    return row.interval


# ---------------------------------------------------------------------------
# DBA end-to-end
# ---------------------------------------------------------------------------


@pytest.fixture(scope='module')
def dba_clean_result():
    """One shared clean DBA fit, reused by the round-trip and structure tests."""
    x, y = _make_dba_data(DBA_TRUE)
    assay = DBAAssay(
        x_data=Q_(x, 'M'),
        y_data=Q_(y, 'au'),
        fixed_conc=Q_(DBA_TRUE['fixed_conc'], 'M'),
        mode='DtoH',
    )
    return fit_assay(assay, FitConfig(custom_bounds=DBA_RECOVERY_BOUNDS)), Q_(y, 'au'), assay


class TestDBAEndToEnd:
    def test_clean_round_trip(self, dba_clean_result):
        result, y, assay = dba_clean_result

        assert result.r_squared > 0.999
        assert_within_tolerance(result.parameters['Ka_dye'], DBA_TRUE['Ka_dye'], CLEAN_TOL, 'Ka_dye')
        # Signal reconstruction: fitted model matches the data point-wise.
        max_rel_err = _max_rel_err(assay, result, y)
        assert max_rel_err < 0.03, f'Max point-wise relative error {max_rel_err:.2%} > 3%'

    def test_fit_result_structure(self, dba_clean_result):
        result, _, assay = dba_clean_result

        # Type and model
        assert result.assay_type == 'DBA_DtoH'
        assert result.model_name == 'equilibrium_4param'

        # Every parameter reported; the binding constant carries an interval
        # around its estimate and the signal coefficients carry none.
        rows = {r.key: r for r in summarize_parameters(result) if not r.is_log}
        assert set(rows) == set(assay.parameter_keys)
        low, high = _interval_of(result, 'Ka_dye')
        assert low < float(result.parameters['Ka_dye'].magnitude) < high
        assert all(rows[k].interval is None for k in ('I0', 'I_dye_free', 'I_dye_bound'))

        # Fit curve is a dense, sorted grid spanning the data range (smooth display curve)
        assert result.x_fit.shape == result.y_fit.shape
        assert len(result.x_fit) > len(assay.x_data)
        x_mag = result.x_fit.magnitude
        assert np.all(np.diff(x_mag) > 0)
        assert x_mag[0] == pytest.approx(assay.x_data.magnitude.min())
        assert x_mag[-1] == pytest.approx(assay.x_data.magnitude.max())

        # Conditions and the configuration snapshot
        assert 'fixed_conc' in result.conditions
        assert result.fit_config['level'] == 0.95

        # UUID and timestamp populated
        assert len(result.id) > 0
        assert len(result.timestamp) > 0

    def test_htod_mode_clean_round_trip(self):
        """Ka_dye recovered in HtoD mode (host titrated, dye fixed)."""
        x = np.linspace(1e-7, 50e-6, 30)
        y = dba_signal(
            I0=DBA_TRUE['I0'],
            Ka_dye=DBA_TRUE['Ka_dye'],
            I_dye_free=DBA_TRUE['I_dye_free'],
            I_dye_bound=DBA_TRUE['I_dye_bound'],
            x_titrant=x,
            y_fixed=DBA_TRUE['fixed_conc'],
            mode='HtoD',
        )
        assay = DBAAssay(
            x_data=Q_(x, 'M'),
            y_data=Q_(y, 'au'),
            fixed_conc=Q_(DBA_TRUE['fixed_conc'], 'M'),
            mode='HtoD',
        )
        result = fit_assay(assay, FitConfig(custom_bounds=DBA_RECOVERY_BOUNDS))

        assert result.assay_type == 'DBA_HtoD'
        assert_within_tolerance(result.parameters['Ka_dye'], DBA_TRUE['Ka_dye'], CLEAN_TOL, 'Ka_dye')


# ---------------------------------------------------------------------------
# GDA / IDA end-to-end
# ---------------------------------------------------------------------------


class TestGDAEndToEnd:
    def test_clean_round_trip(self, gda_clean):
        assay, true = _gda_assay(gda_clean)
        x, y, _ = gda_clean
        result = fit_assay(assay, FitConfig(custom_bounds=GDA_IDA_RECOVERY_BOUNDS))

        assert result.r_squared > 0.999
        assert_within_tolerance(result.parameters['Ka_guest'], true['Ka_guest'], CLEAN_TOL, 'Ka_guest')
        # Reconstruction tolerance is looser for GDA (weaker identifiability).
        max_rel_err = _max_rel_err(assay, result, y)
        assert max_rel_err < 0.10, f'Max point-wise relative error {max_rel_err:.2%} > 10%'


@pytest.fixture(scope='module')
def ida_clean_result():
    """One shared clean IDA fit, reused by the round-trip and interval tests."""
    x, y = _make_ida_data(IDA_TRUE)
    assay = IDAAssay(
        x_data=Q_(x, 'M'),
        y_data=Q_(y, 'au'),
        Ka_dye=Q_(IDA_TRUE['Ka_dye'], '1/M'),
        h0=Q_(IDA_TRUE['h0'], 'M'),
        d0=Q_(IDA_TRUE['d0'], 'M'),
    )
    return fit_assay(assay, FitConfig(custom_bounds=GDA_IDA_RECOVERY_BOUNDS)), Q_(y, 'au'), assay


class TestIDAEndToEnd:
    def test_clean_round_trip(self, ida_clean_result):
        result, y, assay = ida_clean_result

        assert result.r_squared > 0.999
        assert_within_tolerance(result.parameters['Ka_guest'], IDA_TRUE['Ka_guest'], CLEAN_TOL, 'Ka_guest')
        max_rel_err = _max_rel_err(assay, result, y)
        assert max_rel_err < 0.01, f'Max point-wise relative error {max_rel_err:.2%} > 1%'

    def test_noisy_round_trip(self, ida_noisy):
        assay, true = _ida_assay(ida_noisy)
        result = fit_assay(assay, FitConfig(custom_bounds=GDA_IDA_RECOVERY_BOUNDS))

        assert_within_tolerance(result.parameters['Ka_guest'], true['Ka_guest'], NOISY_TOL, 'Ka_guest')

    def test_the_interval_covers_the_truth_and_widens_with_the_noise(self, ida_clean_result, ida_noisy):
        """The interval states what the data leave open, so noisier data must leave more open."""
        clean_result, _, _ = ida_clean_result
        noisy_result = fit_assay(_ida_assay(ida_noisy)[0], FitConfig(custom_bounds=GDA_IDA_RECOVERY_BOUNDS))

        low, high = _interval_of(noisy_result, 'Ka_guest')
        assert low < IDA_TRUE['Ka_guest'] < high
        clean_low, clean_high = _interval_of(clean_result, 'Ka_guest')
        assert clean_low < IDA_TRUE['Ka_guest'] < clean_high
        assert (high - low) > 100 * (clean_high - clean_low)


# ---------------------------------------------------------------------------
# Stepwise 1:2 and 2:1 end-to-end
# ---------------------------------------------------------------------------


class TestStepwiseRecovery:
    """Clean-data recovery of both stepwise constants under calibrated signal bounds.

    Both constants are searched at once, so each interval is the profile of one
    with the other minimised over — the spread the trade-off between the two
    steps leaves.
    """

    def test_hg2_recovers_both_constants(self):
        x, y = _make_hg2_data(HG2_TRUE)
        assay = HG2Assay(x_data=Q_(x, 'M'), y_data=Q_(y, 'au'), h0=Q_(HG2_TRUE['h0'], 'M'))
        result = fit_assay(assay, FitConfig(custom_bounds=HG2_RECOVERY_BOUNDS, per_replica=False))

        assert_within_tolerance(result.parameters['Ka_HG'], HG2_TRUE['Ka_HG'], CLEAN_TOL, 'Ka_HG')
        assert_within_tolerance(result.parameters['Ka_HG2'], HG2_TRUE['Ka_HG2'], CLEAN_TOL, 'Ka_HG2')
        for key in ('Ka_HG', 'Ka_HG2'):
            low, high = _interval_of(result, key)
            assert low <= HG2_TRUE[key] <= high

    def test_h2g_recovers_both_constants(self):
        x, y = _make_h2g_data(H2G_TRUE)
        assay = H2GAssay(x_data=Q_(x, 'M'), y_data=Q_(y, 'au'), h0=Q_(H2G_TRUE['h0'], 'M'))
        result = fit_assay(assay, FitConfig(custom_bounds=H2G_RECOVERY_BOUNDS, per_replica=False))

        assert_within_tolerance(result.parameters['Ka_HG'], H2G_TRUE['Ka_HG'], CLEAN_TOL, 'Ka_HG')
        assert_within_tolerance(result.parameters['Ka_H2G'], H2G_TRUE['Ka_H2G'], CLEAN_TOL, 'Ka_H2G')
        for key in ('Ka_HG', 'Ka_H2G'):
            low, high = _interval_of(result, key)
            assert low <= H2G_TRUE[key] <= high


# ---------------------------------------------------------------------------
# DyeAlone end-to-end
# ---------------------------------------------------------------------------


class TestDyeAloneEndToEnd:
    def test_linear_fit_round_trip(self, dye_alone_clean):
        assay, true = _dye_alone_assay(dye_alone_clean)
        result = fit_linear_assay(assay)

        assert result.r_squared > 0.999
        assert_within_tolerance(result.parameters['slope'], true['slope'], CLEAN_TOL, 'slope')
        assert_within_tolerance(result.parameters['intercept'], true['intercept'], CLEAN_TOL, 'intercept')

    def test_metadata(self, dye_alone_clean):
        assay, _ = _dye_alone_assay(dye_alone_clean)
        result = fit_linear_assay(assay)

        assert result.assay_type == 'DYE_ALONE'
        assert result.model_name == 'linear'
        assert result.metadata.get('method') == 'linear_regression'
        # A calibration line has no binding constant, so it states no interval.
        assert result.intervals is None
        assert all(r.interval is None for r in summarize_parameters(result))

    def test_noisy_linear_fit(self):
        from tests.conftest import _make_dye_alone_data

        x, y = _make_dye_alone_data(DYE_ALONE_TRUE, noise_frac=0.05)
        assay = DyeAloneAssay(x_data=Q_(x, 'M'), y_data=Q_(y, 'au'))
        result = fit_linear_assay(assay)

        assert_within_tolerance(result.parameters['slope'], DYE_ALONE_TRUE['slope'], NOISY_TOL, 'slope')


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
        return DyeAloneAssay(x_data=Q_(x, 'M'), y_data=Q_(y, 'au'))

    def _dye_alone_bounds(self):
        """Fit consistent dye-alone and derive signal bounds."""
        return bounds_from_dye_alone(fit_linear_assay(self._consistent_dye_alone_assay()), margin=0.2)

    def test_dye_alone_to_dba(self, dba_clean):
        signal_bounds = self._dye_alone_bounds()
        assay, true = _dba_assay(dba_clean)

        # Dye-alone constrains I_dye_free and I0; I_dye_bound still needs
        # separate bounds (not observable in dye-alone experiment).
        config = FitConfig(
            custom_bounds={
                **DBA_RECOVERY_BOUNDS,  # I_dye_bound + Ka_dye defaults
                **signal_bounds,  # override I_dye_free and I0
            },
        )
        result = fit_assay(assay, config)

        assert_within_tolerance(result.parameters['Ka_dye'], true['Ka_dye'], CLEAN_TOL, 'Ka_dye')

    def test_bounds_from_dye_alone_values(self, dye_alone_clean):
        """Verify derived bounds bracket the known truth."""
        assay, true = _dye_alone_assay(dye_alone_clean)
        bounds = bounds_from_dye_alone(fit_linear_assay(assay), margin=0.2)

        # I_dye_free bounds should bracket the true slope (≈ I_dye_free)
        lo, hi = bounds['I_dye_free']
        assert lo.magnitude > 0
        assert lo.magnitude < true['slope'] < hi.magnitude

        # I0 bounds should bracket the true intercept
        lo, hi = bounds['I0']
        assert lo.magnitude <= true['intercept'] <= hi.magnitude

    def test_margin_zero_collapses_to_point(self, dye_alone_clean):
        assay, _ = _dye_alone_assay(dye_alone_clean)
        bounds = bounds_from_dye_alone(fit_linear_assay(assay), margin=0.0)

        lo, hi = bounds['I_dye_free']
        assert lo.magnitude == pytest.approx(hi.magnitude)

    def test_bounds_from_dye_alone_rejects_nonlinear(self):
        """bounds_from_dye_alone raises on a result that is not a calibration line."""
        result = FitResult(
            parameters={'Ka_dye': Q_(5e5, '1/M'), 'I0': Q_(0.0, 'au')},
            rmse=0.01,
            r_squared=0.999,
            x_fit=Q_(np.array([1e-6]), 'M'),
            y_fit=Q_(np.array([100.0]), 'au'),
            assay_type='DBA_DtoH',
            model_name='equilibrium_4param',
        )
        with pytest.raises(ValueError, match='linear'):
            bounds_from_dye_alone(result)


# ---------------------------------------------------------------------------
# Bounds that hold no fit
# ---------------------------------------------------------------------------


class TestBoundsFarFromTheTruth:
    def test_unknown_custom_bounds_key_raises(self, dba_clean):
        assay, _ = _dba_assay(dba_clean)
        config = FitConfig(custom_bounds={'bogus_param': (Q_(0, 'au'), Q_(1, 'au'))})
        with pytest.raises(ValueError, match='Unknown parameter'):
            fit_assay(assay, config)

    def test_a_ka_box_far_from_the_truth_fits_its_edge_and_says_the_data_reject_it(self, dba_clean):
        """The box is the user's claim about Ka; the fit stays inside it and the interval shows it fails."""
        assay, _ = _dba_assay(dba_clean)
        wrong_bounds = {**DBA_RECOVERY_BOUNDS, 'Ka_dye': (Q_(1e-15, '1/M'), Q_(1e-14, '1/M'))}

        result = fit_assay(assay, FitConfig(custom_bounds=wrong_bounds))

        assert 1e-15 <= float(result.parameters['Ka_dye'].magnitude) <= 1e-14
        assert result.r_squared < 0.9  # no binding constant in that box describes the titration
        low, high = _interval_of(result, 'Ka_dye')
        # Nothing in the box is rejected relative to the (equally bad) best fit,
        # so the interval is the whole box and open on both sides.
        row = next(r for r in summarize_parameters(result) if r.key == 'Ka_dye' and not r.is_log)
        assert (low, high) == (1e-15, 1e-14)
        assert row.interval_open == (True, True)


# ---------------------------------------------------------------------------
# fit_measurement_set dispatch
# ---------------------------------------------------------------------------


class TestFitMeasurementSet:
    def test_fit_measurement_set_dye_alone(self, dye_alone_clean):
        """fit_measurement_set dispatches to fit_linear_assay for DyeAlone."""
        x, y, true = dye_alone_clean
        ms = MeasurementSet(
            concentrations=x.magnitude,
            signals=y.magnitude.reshape(1, -1),
            replica_ids=('r0',),
        )
        result = fit_measurement_set(ms, DyeAloneAssay, {})

        assert result.model_name == 'linear'
        assert result.measurement_set_id == ms.id

    def test_fit_measurement_set_gda(self, gda_clean):
        """fit_measurement_set dispatches to fit_assay for GDA."""
        x, y, true = gda_clean
        ms = MeasurementSet(
            concentrations=x.magnitude,
            signals=y.magnitude.reshape(1, -1),
            replica_ids=('r0',),
        )
        conditions = {
            'Ka_dye': Q_(true['Ka_dye'], '1/M'),
            'h0': Q_(true['h0'], 'M'),
            'g0': Q_(true['g0'], 'M'),
        }
        result = fit_measurement_set(
            ms,
            GDAAssay,
            conditions,
            config=FitConfig(custom_bounds=GDA_IDA_RECOVERY_BOUNDS),
        )

        assert result.measurement_set_id == ms.id
        assert_within_tolerance(result.parameters['Ka_guest'], true['Ka_guest'], CLEAN_TOL, 'Ka_guest')


# ---------------------------------------------------------------------------
# The entered inputs as constrained nuisance parameters
# ---------------------------------------------------------------------------


def _ida_replicates(h0_factor: float, n_points: int = 12, noise: float = 0.005, seed: int = 5):
    """Three IDA replicates of the ground truth, with the host concentration entered *h0_factor* times too high."""
    x, y = _make_ida_data(IDA_TRUE, n_points=n_points)
    rng = np.random.default_rng(seed)
    signals = np.vstack([y + rng.normal(0.0, noise * np.ptp(y), y.size) for _ in range(3)])
    ms = MeasurementSet(concentrations=x, signals=signals, replica_ids=('a', 'b', 'c'))
    conditions = {
        'Ka_dye': Q_(IDA_TRUE['Ka_dye'], '1/M'),
        'h0': Q_(IDA_TRUE['h0'] * h0_factor, 'M'),
        'd0': Q_(IDA_TRUE['d0'], 'M'),
    }
    return ms, conditions


class TestInputsFreeWithinTheirUncertainty:
    """What the reported interval covers once the entered inputs are only as exact as they were stated to be.

    The host concentration is entered 8 % too high, which the fit can only
    absorb by raising Ka: the data are then described by a Ka that is not the
    true one, and an interval that takes the entered inputs as exact misses the
    truth. Stating how well the inputs are known is what puts it back inside.
    """

    @pytest.fixture(scope='class')
    def wrong_h0(self):
        return _ida_replicates(h0_factor=1.08)

    @pytest.fixture(scope='class')
    def uncertain(self, wrong_h0):
        """That data fitted with the host stock stated to 10 % and the titrant to 3 %."""
        ms, conditions = wrong_h0
        specs = {'h0': InputSpec.sigma_pct(10), TITRANT: InputSpec.sigma_pct(3)}
        config = FitConfig(custom_bounds=GDA_IDA_RECOVERY_BOUNDS, per_replica=False, errors=ErrorModel(specs=specs))
        return fit_measurement_set(ms, IDAAssay, conditions, config)

    def test_an_input_entered_wrong_shows_as_misfit_and_is_absorbed_within_its_uncertainty(self, uncertain):
        result = uncertain

        low, high = _interval_of(result, 'Ka_guest')
        assert low < IDA_TRUE['Ka_guest'] < high
        # The interval that holds the entered host concentration exact does not reach the truth.
        conditional = result.conditional.intervals['Ka_guest']
        assert conditional.low > IDA_TRUE['Ka_guest']
        assert float(result.conditional.parameters['Ka_guest'].magnitude) > float(
            result.parameters['Ka_guest'].magnitude
        )
        # The fit put the correction on the host concentration, downward and well inside what was stated.
        shift = result.input_shifts['h0']
        assert -0.09 < shift.fraction < -0.02
        assert abs(shift.z) < 1.0
        assert not shift.at_edge

    def test_the_replicates_say_the_model_misses_at_the_entered_inputs_and_fits_once_they_move(self, uncertain):
        """Three replicates give the scatter the misfit is judged against, at both fits."""
        diagnostics = uncertain.diagnostics
        assert diagnostics.conditional_misfit.kind == 'lack_of_fit'
        # n - p against n (m - 1): 12 points, 3 parameters the data determine, three replicates.
        assert diagnostics.conditional_misfit.dof == (12 - 3, 12 * 2)
        assert diagnostics.conditional_misfit.p_value < 0.001
        assert diagnostics.misfit.p_value > 0.05
        assert diagnostics.conflict.p_value > 0.05, 'the shift stays within what was stated, so nothing conflicts'
        assert diagnostics.verdict is Verdict.INPUTS_EXPLAIN

    def test_with_the_inputs_entered_as_exact_the_misfit_is_the_models_own(self, wrong_h0):
        """Nothing may move, so the same misfit is reported and no shift can explain it."""
        ms, conditions = wrong_h0
        result = fit_measurement_set(
            ms, IDAAssay, conditions, FitConfig(custom_bounds=GDA_IDA_RECOVERY_BOUNDS, per_replica=False)
        )

        assert result.input_shifts == {}
        assert result.diagnostics.misfit is result.diagnostics.conditional_misfit
        assert result.diagnostics.conflict is None
        assert result.diagnostics.verdict is Verdict.MODEL_INADEQUATE

    def test_a_fit_that_moved_no_input_reports_one_interval_twice_over(self, ida_clean):
        """With nothing free to move the two fits are one fit, down to the interval object."""
        assay, _ = _ida_assay(ida_clean)
        result = fit_assay(assay, FitConfig(custom_bounds=GDA_IDA_RECOVERY_BOUNDS))

        assert result.intervals['Ka_guest'] is result.conditional.intervals['Ka_guest']
        assert result.parameters == result.conditional.parameters
        assert (result.rmse, result.r_squared) == (result.conditional.rmse, result.conditional.r_squared)
        # One signal and no replicates: the residuals are all there is to test the model with.
        assert result.diagnostics.conditional_misfit.kind == 'runs'

    def test_the_inputs_are_whichever_ones_the_assay_has(self, gda_clean):
        """Nothing here knows an assay by name: a GDA states a guest stock, and that is what moves.

        The guest stock is entered 10 % too high and stated to 10 %. Its
        uncertainty leaves more room for Ka than holding it exact does, which
        is what a wider interval around the same truth says.
        """
        x, y, true = gda_clean
        noisy = Q_(y.magnitude + np.random.default_rng(3).normal(0.0, 0.005 * np.ptp(y.magnitude), y.size), 'au')
        assay = GDAAssay(
            x_data=x,
            y_data=noisy,
            Ka_dye=Q_(true['Ka_dye'], '1/M'),
            h0=Q_(true['h0'], 'M'),
            g0=Q_(true['g0'] * 1.1, 'M'),
        )
        config = FitConfig(
            custom_bounds=GDA_IDA_RECOVERY_BOUNDS,
            per_replica=False,
            errors=ErrorModel(specs={'g0': InputSpec.sigma_pct(10)}),
        )

        result = fit_assay(assay, config)

        assert set(result.input_shifts) == {'g0'}
        low, high = _interval_of(result, 'Ka_guest')
        assert low < true['Ka_guest'] < high
        conditional = result.conditional.intervals['Ka_guest']
        assert (low, high) != (conditional.low, conditional.high)
        assert np.log10(high / low) > np.log10(conditional.high / conditional.low)
