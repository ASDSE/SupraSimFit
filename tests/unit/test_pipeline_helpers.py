"""Pipeline helpers: resolving bounds and log-scale keys, and stopping a running fit."""

import numpy as np
import pytest

from core.assays.gda import GDAAssay
from core.assays.ida import IDAAssay
from core.data_processing.measurement_set import MeasurementSet
from core.optimizer.multistart import FitCancelled
from core.pipeline.fit_pipeline import (
    FitConfig,
    _resolve_bounds,
    _resolve_log_scale,
    fit_assay,
    fit_measurement_set,
)
from core.units import Q_
from tests.conftest import GDA_IDA_RECOVERY_BOUNDS, IDA_TRUE, _make_ida_data


def _gda_assay():
    return GDAAssay(
        x_data=Q_(np.linspace(1e-7, 50e-6, 5), 'M'),
        y_data=Q_(np.ones(5), 'au'),
        Ka_dye=Q_(5e5, '1/M'),
        h0=Q_(10e-6, 'M'),
        g0=Q_(20e-6, 'M'),
    )


class TestResolveBounds:
    def test_custom_overrides_one_param(self):
        assay = _gda_assay()
        custom = {'Ka_guest': (Q_(1.0, '1/M'), Q_(2.0, '1/M'))}
        merged = _resolve_bounds(assay, custom)

        # Ka_guest should be overridden
        lo, hi = merged['Ka_guest']
        assert lo.magnitude == pytest.approx(1.0)
        assert hi.magnitude == pytest.approx(2.0)

        # Other params should keep registry defaults
        assert 'I0' in merged
        assert 'I_dye_free' in merged
        assert 'I_dye_bound' in merged

    def test_unknown_key_raises(self):
        assay = _gda_assay()
        custom = {'bogus': (Q_(0, 'au'), Q_(1, 'au'))}
        with pytest.raises(ValueError, match='Unknown parameter'):
            _resolve_bounds(assay, custom)

    def test_none_custom_returns_defaults(self):
        assay = _gda_assay()
        merged = _resolve_bounds(assay, None)
        assert set(merged.keys()) == set(assay.parameter_keys)


class TestResolveLogScale:
    def test_none_uses_registry(self):
        assay = _gda_assay()
        indices = _resolve_log_scale(assay, None)
        # Ka_guest is index 0 in GDA parameter_keys and is in log_scale_keys
        assert 0 in indices

    def test_empty_list_overrides(self):
        assay = _gda_assay()
        indices = _resolve_log_scale(assay, [])
        assert indices == []

    def test_unknown_raises(self):
        assay = _gda_assay()
        with pytest.raises(ValueError, match='Unknown log-scale parameter'):
            _resolve_log_scale(assay, ['nonexistent'])

    def test_a_bound_at_zero_on_a_log_scale_parameter_is_refused_by_name(self):
        """Log space cannot hold zero, and linear starts would search only the top decade."""
        config = FitConfig(n_trials=2, custom_bounds={'Ka_guest': (Q_(0.0, '1/M'), Q_(1e12, '1/M'))})

        with pytest.raises(ValueError, match='Ka_guest'):
            fit_assay(_gda_assay(), config)

    def test_the_same_bound_is_refused_by_name_on_the_per_replicate_path(self):
        """The bound is a setting, not one replicate's data, so it is named rather than
        recorded as every replicate failing to fit — which would send the user to Min R²."""
        config = FitConfig(
            n_trials=2,
            per_replica=True,
            custom_bounds={'Ka_guest': (Q_(0.0, '1/M'), Q_(1e12, '1/M'))},
        )

        with pytest.raises(ValueError, match='Ka_guest'):
            fit_measurement_set(_ida_measurement_set(), IDAAssay, _IDA_CONDITIONS, config)


def _ida_measurement_set() -> MeasurementSet:
    """Three replicates of the IDA ground truth, each with slight noise."""
    x, y = _make_ida_data(IDA_TRUE, n_points=15)
    rng = np.random.default_rng(11)
    signals = np.vstack([y + rng.normal(0.0, 0.002 * np.ptp(y), y.size) for _ in range(3)])
    return MeasurementSet(concentrations=x, signals=signals, replica_ids=('a', 'b', 'c'))


_IDA_CONDITIONS = {
    'Ka_dye': Q_(IDA_TRUE['Ka_dye'], '1/M'),
    'h0': Q_(IDA_TRUE['h0'], 'M'),
    'd0': Q_(IDA_TRUE['d0'], 'M'),
}


class TestCancellation:
    """A cancelled fit stops within one optimizer run and produces no result."""

    def test_fit_assay_stops_at_the_next_optimizer_run(self):
        polls: list[bool] = []

        def should_cancel() -> bool:
            polls.append(len(polls) >= 2)
            return polls[-1]

        with pytest.raises(FitCancelled):
            fit_assay(_gda_assay(), FitConfig(n_trials=500), should_cancel=should_cancel)

        assert len(polls) == 3, 'two runs were made, and the third was refused'

    def test_a_cancelled_per_replicate_fit_is_not_reported_as_a_failed_replicate(self):
        """Cancellation is the caller's decision, so it is raised rather than recorded as a bad replicate."""
        ms = _ida_measurement_set()
        polls: list[bool] = []

        def should_cancel() -> bool:
            polls.append(len(polls) >= 5)
            return polls[-1]

        config = FitConfig(n_trials=4, custom_bounds=GDA_IDA_RECOVERY_BOUNDS, per_replica=True, seed=5)
        with pytest.raises(FitCancelled):
            fit_measurement_set(ms, IDAAssay, _IDA_CONDITIONS, config, should_cancel=should_cancel)

        assert len(polls) == 6, 'the second replicate stopped rather than running its four trials'
