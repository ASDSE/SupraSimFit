"""End-to-end tests of per-replicate fitting.

Verifies, on synthetic IDA replicates with known ground truth:
- Ka recovery from clean and from noisy replicates;
- that a replicate needing another binding constant — or two sharing one — is
  left out and named, that a replicate of pure noise is left out for its
  scatter, and that the remaining replicates still recover the truth;
- what the replicate columns report and what they are measured on;
- the refusals a replicate set can run into.

A closing check runs the whole path on the measured demo dataset, where the
expected numbers are computed from the replicate rows directly rather than
through the pipeline's masking.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import numpy as np
import pytest

from core.assays.ida import IDAAssay
from core.data_processing.measurement_set import MeasurementSet
from core.io import load_measurements
from core.optimizer.filters import calculate_fit_metrics
from core.pipeline.fit_pipeline import (
    FitConfig,
    FitResult,
    fit_assay,
    fit_measurement_set,
    fit_measurement_set_per_replica,
    fit_replica_ids,
    summarize_parameters,
)
from core.pipeline.inputs import TITRANT, ErrorModel, InputSpec
from core.units import Q_
from tests.conftest import GDA_IDA_RECOVERY_BOUNDS, IDA_TRUE, _make_ida_data, assert_within_tolerance

N_REPLICAS = 5
CLEAN_TOL = 0.10
NOISY_TOL = 0.25

_DEMO_PATH = Path(__file__).resolve().parents[2] / 'data' / 'IDA_system.txt'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ida_conditions() -> Dict[str, Any]:
    return {
        'Ka_dye': Q_(IDA_TRUE['Ka_dye'], '1/M'),
        'h0': Q_(IDA_TRUE['h0'], 'M'),
        'd0': Q_(IDA_TRUE['d0'], 'M'),
    }


def _ida_ms(n_replicas: int = N_REPLICAS, noise_frac: float = 0.05, seed: int = 2026) -> MeasurementSet:
    """A MeasurementSet with N independent noisy IDA replicates."""
    rng = np.random.default_rng(seed)
    x_ref, _ = _make_ida_data(IDA_TRUE, noise_frac=0.0)
    signals = np.stack(
        [
            _make_ida_data(IDA_TRUE, noise_frac=noise_frac, rng=np.random.default_rng(rng.integers(1 << 31)))[1]
            for _ in range(n_replicas)
        ]
    )
    return MeasurementSet(
        concentrations=x_ref,
        signals=signals,
        replica_ids=tuple(f'r{i}' for i in range(n_replicas)),
        metadata={'source_file': 'synthetic_per_replica_test'},
    )


def _config() -> FitConfig:
    return FitConfig(custom_bounds=GDA_IDA_RECOVERY_BOUNDS, per_replica=True)


def _replaced(ms: MeasurementSet, row: int, signal: np.ndarray) -> MeasurementSet:
    """*ms* with one replicate's signal replaced."""
    signals = np.array(ms.signals, dtype=np.float64)
    signals[row] = signal
    return MeasurementSet(
        concentrations=ms.concentrations,
        signals=signals,
        replica_ids=ms.replica_ids,
        metadata=dict(ms.metadata),
    )


@pytest.fixture(scope='module')
def clean_pr_result() -> FitResult:
    """Per-replicate fit of 5 noise-free replicates."""
    return fit_measurement_set_per_replica(_ida_ms(noise_frac=0.0, seed=1), IDAAssay, _ida_conditions(), _config())


@pytest.fixture(scope='module')
def noisy_pr_result() -> tuple[MeasurementSet, FitResult]:
    """Per-replicate fit of 5 replicates with 5 % Gaussian noise."""
    ms = _ida_ms(noise_frac=0.05, seed=7)
    return ms, fit_measurement_set_per_replica(ms, IDAAssay, _ida_conditions(), _config())


# ---------------------------------------------------------------------------
# Recovery
# ---------------------------------------------------------------------------


class TestPerReplicateRecovery:
    def test_ka_recovered_from_clean_replicas(self, clean_pr_result):
        result = clean_pr_result

        assert len(result.replica_fits) == N_REPLICAS
        assert fit_replica_ids(result) == list(result.metadata['active_replica_ids'])
        assert_within_tolerance(result.parameters['Ka_guest'], IDA_TRUE['Ka_guest'], CLEAN_TOL, 'Ka_guest')

    def test_ka_recovered_from_noisy_replicas(self, noisy_pr_result):
        _, result = noisy_pr_result

        assert len(result.replica_fits) == N_REPLICAS
        assert_within_tolerance(result.parameters['Ka_guest'], IDA_TRUE['Ka_guest'], NOISY_TOL, 'Ka_guest')

    def test_every_replicate_fit_is_in_physical_units_and_names_its_replicate(self, clean_pr_result):
        for rid, rf in zip(clean_pr_result.metadata['active_replica_ids'], clean_pr_result.replica_fits):
            assert str(rf.parameters['Ka_guest'].units) == '1 / molar'
            assert rf.metadata['replica_id'] == rid
            assert rf.intervals is None  # a single replicate's own fit states no interval

    def test_dispatch_via_fit_measurement_set(self):
        """fit_measurement_set honors config.per_replica and dispatches."""
        ms = _ida_ms(n_replicas=3, noise_frac=0.0, seed=3)

        result = fit_measurement_set(ms, IDAAssay, _ida_conditions(), _config())

        assert result.replica_fits is not None
        assert result.metadata['replicate_test']['p_values'].keys() == set(ms.replica_ids)


# ---------------------------------------------------------------------------
# What the replicate columns report
# ---------------------------------------------------------------------------


class TestReplicateColumns:
    def test_the_replicate_spread_is_the_replicates_own_fits(self, noisy_pr_result):
        """The columns describe real between-replicate variation, computed here from the sub-fits."""
        _, result = noisy_pr_result
        used = fit_replica_ids(result)
        own = np.array(
            [
                float(rf.parameters['Ka_guest'].magnitude)
                for rf in result.replica_fits
                if rf.metadata['replica_id'] in used
            ]
        )
        stats = next(s.replicates for s in summarize_parameters(result) if s.key == 'Ka_guest' and not s.is_log)

        assert stats['median'] == pytest.approx(float(np.median(own)))
        assert (stats['min'], stats['max']) == (float(own.min()), float(own.max()))
        assert stats['max'] > stats['min'], 'noisy replicates must not give one and the same Ka'
        # Each replicate is a measurement of the same system, so the reported fit
        # of their average lies within the spread of their own fits.
        assert stats['min'] <= float(result.parameters['Ka_guest'].magnitude) <= stats['max']

    def test_the_interval_and_the_spread_are_two_different_statements(self, noisy_pr_result):
        """The interval is what the averaged data leave open for Ka; the spread is what the
        replicates each measured. Both bracket the truth, and neither is derived from the other."""
        _, result = noisy_pr_result
        row = next(s for s in summarize_parameters(result) if s.key == 'Ka_guest' and not s.is_log)

        assert row.interval[0] < IDA_TRUE['Ka_guest'] < row.interval[1]
        assert row.replicates['min'] < IDA_TRUE['Ka_guest'] < row.replicates['max']
        assert row.level == 0.95


class TestReportedFitWithUncertainInputs:
    """What the reported fit is when the inputs may move: still the fit of the average of the replicates used.

    The replicates decide which of them are averaged and what the spread
    between them is; the uncertainty of the entered inputs then acts on that
    one averaged signal. A replicate's own fit stays a search over its own
    signal at the inputs as entered.
    """

    @staticmethod
    def _specs() -> dict:
        return {'h0': InputSpec.sigma_pct(10), TITRANT: InputSpec.sigma_pct(3)}

    def test_the_reported_fit_is_the_fit_of_the_average_of_the_replicates_used(self):
        ms = _ida_ms(n_replicas=3, noise_frac=0.01, seed=31)
        conditions = _ida_conditions()
        config = FitConfig(
            custom_bounds=GDA_IDA_RECOVERY_BOUNDS, per_replica=True, errors=ErrorModel(specs=self._specs())
        )

        result = fit_measurement_set_per_replica(ms, IDAAssay, conditions, config)

        used = fit_replica_ids(result)
        direct = fit_assay(
            ms.with_active(used).to_assay(IDAAssay, conditions=conditions, use_average=True),
            config,
            replicate_signals=np.vstack([ms.get_replica_signal(rid) for rid in used]),
        )
        assert result.parameters['Ka_guest'].magnitude == direct.parameters['Ka_guest'].magnitude
        assert result.intervals['Ka_guest'] == direct.intervals['Ka_guest']
        assert result.conditional.intervals['Ka_guest'] == direct.conditional.intervals['Ka_guest']
        assert result.input_shifts == direct.input_shifts
        assert result.diagnostics == direct.diagnostics
        # The uncertain inputs moved the reported fit away from the one that holds them exact.
        assert result.parameters['Ka_guest'].magnitude != result.conditional.parameters['Ka_guest'].magnitude

    def test_a_replicates_own_fit_holds_the_inputs_as_entered(self):
        """It answers what that replicate alone says about Ka, which is what the spread is made of."""
        ms = _ida_ms(n_replicas=3, noise_frac=0.01, seed=31)
        config = FitConfig(
            custom_bounds=GDA_IDA_RECOVERY_BOUNDS, per_replica=True, errors=ErrorModel(specs=self._specs())
        )

        result = fit_measurement_set_per_replica(ms, IDAAssay, _ida_conditions(), config)

        for own in result.replica_fits:
            assert own.input_shifts == {}
            assert own.conditional is None
            assert own.diagnostics is None
            assert own.intervals is None
            # A noise law is read from the scatter between replicates, so it
            # describes the set and belongs to the fit of their average.
            assert own.noise is None
        assert result.noise.n_replicates == len(result.replica_fits)


# ---------------------------------------------------------------------------
# A replicate that does not share the binding constant
# ---------------------------------------------------------------------------


class TestReplicateExclusion:
    def test_a_replicate_of_another_ka_is_left_out_and_the_rest_recover_the_truth(self):
        """Replicate 'r2' is a titration of a guest binding three times as tightly."""
        ms = _ida_ms(noise_frac=0.01, seed=101)
        _, odd = _make_ida_data({**IDA_TRUE, 'Ka_guest': 3 * IDA_TRUE['Ka_guest']}, noise_frac=0.01)
        ms = _replaced(ms, 2, odd)

        result = fit_measurement_set_per_replica(ms, IDAAssay, _ida_conditions(), _config())

        assert fit_replica_ids(result) == ['r0', 'r1', 'r3', 'r4']
        assert list(result.metadata['replica_failures']) == ['r2']
        # The reported fit is the fit of the four that agree, and its noise law
        # is read from those four alone.
        assert result.noise.n_replicates == 4
        assert_within_tolerance(result.parameters['Ka_guest'], IDA_TRUE['Ka_guest'], CLEAN_TOL, 'Ka_guest')
        # The replicate columns follow the exclusion: the odd replicate's own Ka
        # is outside the range they report.
        stats = next(s.replicates for s in summarize_parameters(result) if s.key == 'Ka_guest' and not s.is_log)
        odd_ka = float(
            next(rf for rf in result.replica_fits if rf.metadata['replica_id'] == 'r2').parameters['Ka_guest'].magnitude
        )
        assert odd_ka > stats['max']

    def test_two_replicates_of_another_ka_are_both_left_out_and_the_rest_recover_the_truth(self):
        """'r0' and 'r1' are titrations of a guest binding three times as tightly: a minority sharing one Ka."""
        ms = _ida_ms(noise_frac=0.01, seed=101)
        for row in (0, 1):
            rng = np.random.default_rng(500 + row)
            _, odd = _make_ida_data({**IDA_TRUE, 'Ka_guest': 3 * IDA_TRUE['Ka_guest']}, noise_frac=0.01, rng=rng)
            ms = _replaced(ms, row, odd)

        result = fit_measurement_set_per_replica(ms, IDAAssay, _ida_conditions(), _config())

        assert fit_replica_ids(result) == ['r2', 'r3', 'r4']
        assert result.metadata['replicate_test']['reasons'] == {'r0': 'ka', 'r1': 'ka'}
        assert all('Ka' in reason for reason in result.metadata['replica_failures'].values())
        assert_within_tolerance(result.parameters['Ka_guest'], IDA_TRUE['Ka_guest'], CLEAN_TOL, 'Ka_guest')

    def test_a_replicate_of_pure_noise_is_left_out_for_its_scatter(self):
        """A replicate of pure noise says nothing about Ka, and at full weight in the average it moves the fit.

        Its misfit, measured in units of its own scatter, contradicts no binding
        constant; what sets it apart is that scatter, 25 times the others', and
        Cochran's test on the replicates' own residual variances leaves it out
        and says so.
        """
        ms = _ida_ms(noise_frac=0.02, seed=37)
        rng = np.random.default_rng(999)
        peak = float(np.max(np.abs(ms.signals)))
        ms = _replaced(ms, 1, rng.normal(0.0, peak * 0.5, ms.signals.shape[1]))

        result = fit_measurement_set_per_replica(ms, IDAAssay, _ida_conditions(), _config())

        assert fit_replica_ids(result) == ['r0', 'r2', 'r3', 'r4']
        assert result.metadata['replicate_test']['reasons'] == {'r1': 'scatter'}
        assert 'scatter' in result.metadata['replica_failures']['r1']
        # Its own fit is still reported: an R² near zero in the Replicates table.
        noise_fit = next(rf for rf in result.replica_fits if rf.metadata['replica_id'] == 'r1')
        assert noise_fit.r_squared < 0.1
        assert_within_tolerance(result.parameters['Ka_guest'], IDA_TRUE['Ka_guest'], NOISY_TOL, 'Ka_guest')

    def test_a_majority_is_never_removed(self):
        """Three of five replicates disagree with the other two: the test cannot call the majority wrong."""
        ms = _ida_ms(noise_frac=0.01, seed=55)
        _, odd = _make_ida_data({**IDA_TRUE, 'Ka_guest': 5 * IDA_TRUE['Ka_guest']}, noise_frac=0.01)
        for row in (0, 1):
            ms = _replaced(ms, row, odd)

        result = fit_measurement_set_per_replica(ms, IDAAssay, _ida_conditions(), _config())

        assert len(fit_replica_ids(result)) >= 3

    def test_a_replicate_with_no_signal_variation_is_refused_by_name(self):
        """It says nothing about Ka, and its scatter is the weight of every other replicate."""
        ms = _replaced(_ida_ms(n_replicas=3, noise_frac=0.02, seed=41), 1, np.zeros(30))

        with pytest.raises(ValueError, match='r1'):
            fit_measurement_set_per_replica(ms, IDAAssay, _ida_conditions(), _config())

    def test_no_active_replicate_is_refused(self):
        ms = _ida_ms(n_replicas=2, noise_frac=0.0, seed=5)
        for rid in ms.replica_ids:
            ms.set_active(rid, False)

        with pytest.raises(ValueError, match='Switch at least one on'):
            fit_measurement_set_per_replica(ms, IDAAssay, _ida_conditions(), _config())


# ---------------------------------------------------------------------------
# Measured data
# ---------------------------------------------------------------------------


class TestDemoQualityOnFittedReplicates:
    """The whole path on the app's demo IDA dataset: eight measured replicates.

    Whatever the replicate test decides there, every reported quality number
    must describe the average of the replicates the fit used — computed here
    from the replicate rows directly.
    """

    def test_every_quality_number_is_scored_against_the_used_replicates(self):
        ms = MeasurementSet.from_dataframe(load_measurements(_DEMO_PATH))
        conditions = {'Ka_dye': Q_(16.8e6, '1/M'), 'h0': Q_(4.3e-6, 'M'), 'd0': Q_(6e-6, 'M')}

        result = fit_measurement_set(ms, IDAAssay, conditions, FitConfig(per_replica=True))

        used = fit_replica_ids(result)
        assert set(used) <= set(ms.replica_ids) and used
        assay = ms.to_assay(IDAAssay, conditions=conditions)
        vector = np.array([result.parameters[k].magnitude for k in assay.parameter_keys], dtype=float)
        model = assay.forward_model(vector).magnitude
        rows = [ms.replica_ids.index(rid) for rid in used]
        rmse, r_squared = calculate_fit_metrics(ms.signals[rows].mean(axis=0), model)

        assert result.rmse == pytest.approx(rmse, rel=1e-12)
        assert result.r_squared == pytest.approx(r_squared, rel=1e-12)
        low, high = next(s.interval for s in summarize_parameters(result) if s.key == 'Ka_guest' and not s.is_log)
        assert low < float(result.parameters['Ka_guest'].magnitude) < high
