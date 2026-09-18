"""Pipeline helpers: resolving bounds, which fit a dataset is dispatched to, and stopping a running fit."""

import numpy as np
import pytest

from core.assays.dye_alone import DyeAloneAssay
from core.assays.gda import GDAAssay
from core.assays.ida import IDAAssay
from core.data_processing.measurement_set import MeasurementSet
from core.pipeline.fit_pipeline import (
    FitConfig,
    _resolve_bounds,
    fit_assay,
    fit_measurement_set,
)
from core.pipeline.varpro import FitCancelled
from core.units import Q_
from tests.conftest import (
    DYE_ALONE_TRUE,
    GDA_IDA_RECOVERY_BOUNDS,
    IDA_TRUE,
    _make_dye_alone_data,
    _make_ida_data,
)


def _gda_assay():
    return GDAAssay(
        x_data=Q_(np.linspace(1e-7, 50e-6, 5), 'M'),
        # A projection needs a signal that changes; what it is does not matter here.
        y_data=Q_(np.linspace(1.0, 2.0, 5), 'au'),
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


class TestDispatch:
    """Which fit :func:`fit_measurement_set` runs for the data and the configuration it is given."""

    def test_a_dye_alone_calibration_is_a_linear_fit_in_either_replicate_mode(self):
        # A calibration line has no binding constant, so the shared-Ka test has
        # nothing to judge and the per-replicate path cannot fit it at all: both
        # modes have to reach the linear regression, and neither reports an
        # interval for a parameter the model does not have.
        x, y = _make_dye_alone_data(DYE_ALONE_TRUE)
        rng = np.random.default_rng(3)
        signals = np.vstack([y + rng.normal(0.0, 0.5, y.size) for _ in range(3)])
        ms = MeasurementSet(concentrations=x, signals=signals, replica_ids=('a', 'b', 'c'))

        for config in (FitConfig(), FitConfig(per_replica=False)):
            result = fit_measurement_set(ms, DyeAloneAssay, {}, config)
            assert result.model_name == 'linear'
            assert result.intervals is None
            assert result.parameters['slope'].to('au/M').magnitude == pytest.approx(DYE_ALONE_TRUE['slope'], rel=0.05)

    def test_a_fit_of_one_signal_does_not_claim_to_have_tested_replicates(self):
        # ``per_replica`` on a result says what the fit did, and the panels read
        # it to decide whether to show replicate columns. A fit of one averaged
        # signal holds no replicate fits, whatever the configuration asked for.
        ms = _ida_measurement_set()
        config = FitConfig(custom_bounds=GDA_IDA_RECOVERY_BOUNDS, per_replica=True)

        averaged = fit_measurement_set(ms, IDAAssay, _IDA_CONDITIONS, config, replica_id='a')
        assert averaged.replica_fits is None
        assert not averaged.per_replica

        tested = fit_measurement_set(ms, IDAAssay, _IDA_CONDITIONS, config)
        assert tested.per_replica
        assert tested.replica_fits is not None


class TestCancellation:
    """A cancelled fit stops at the next equilibrium solve and produces no result."""

    def test_fit_assay_stops_at_the_next_model_solve(self):
        polls: list[bool] = []

        def should_cancel() -> bool:
            polls.append(len(polls) >= 2)
            return polls[-1]

        with pytest.raises(FitCancelled):
            fit_assay(_gda_assay(), FitConfig(), should_cancel=should_cancel)

        assert len(polls) == 3, 'two search nodes were solved, and the third was refused'

    def test_a_cancelled_per_replicate_fit_raises_rather_than_leaving_a_replicate_out(self):
        """Cancellation is the caller's decision, so it is raised rather than recorded as a bad replicate."""
        ms = _ida_measurement_set()
        polls: list[bool] = []

        def should_cancel() -> bool:
            polls.append(len(polls) >= 5)
            return polls[-1]

        config = FitConfig(custom_bounds=GDA_IDA_RECOVERY_BOUNDS, per_replica=True)
        with pytest.raises(FitCancelled):
            fit_measurement_set(ms, IDAAssay, _IDA_CONDITIONS, config, should_cancel=should_cancel)

        assert len(polls) == 6, 'the search stopped at the sixth node rather than running the whole grid'
