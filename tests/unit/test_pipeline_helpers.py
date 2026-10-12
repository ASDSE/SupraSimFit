"""Pipeline helpers: resolving bounds, scoring a fit at moved inputs, counting the parameters a fit fitted, which fit a dataset is dispatched to, and stopping a running fit."""

import numpy as np
import pytest

from core.assays.base import BaseAssay
from core.assays.dye_alone import DyeAloneAssay
from core.assays.gda import GDAAssay
from core.assays.ida import IDAAssay
from core.data_processing.measurement_set import MeasurementSet
from core.models.equilibrium import ida_signal
from core.pipeline.diagnostics import lack_of_fit
from core.pipeline.fit_pipeline import (
    FitConfig,
    _misfit,
    _resolve_bounds,
    fit_assay,
    fit_measurement_set,
    fit_view,
)
from core.pipeline.input_aware import input_aware
from core.pipeline.inputs import TITRANT
from core.pipeline.noise import NoiseBasis, noise_law
from core.pipeline.varpro import FitCancelled, Projection
from core.units import Q_
from tests.conftest import (
    DYE_ALONE_TRUE,
    GDA_IDA_RECOVERY_BOUNDS,
    GDA_TRUE,
    IDA_TRUE,
    _make_dye_alone_data,
    _make_gda_data,
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


class TestFitViewAtMovedInputs:
    """What a fit is scored on, and where its curve is drawn, once it has moved the entered inputs."""

    @staticmethod
    def _assay(h0: float = IDA_TRUE['h0']) -> IDAAssay:
        x, y = _make_ida_data(IDA_TRUE, n_points=12)
        return IDAAssay(
            x_data=Q_(x, 'M'),
            y_data=Q_(y, 'au'),
            Ka_dye=Q_(IDA_TRUE['Ka_dye'], '1/M'),
            h0=Q_(h0, 'M'),
            d0=Q_(IDA_TRUE['d0'], 'M'),
        )

    @staticmethod
    def _params() -> np.ndarray:
        return np.array(
            [IDA_TRUE['Ka_guest'], IDA_TRUE['I0'], IDA_TRUE['I_dye_free'], IDA_TRUE['I_dye_bound']], dtype=float
        )

    def test_the_model_is_asked_at_the_moved_inputs_and_the_moved_titrant(self):
        """An offset on the titrant scales every concentration the model is asked at, the drawn ones included."""
        assay = self._assay()
        offsets = {'h0': 0.1, TITRANT: 0.05}

        rmse, r_squared, x_fit, y_fit = fit_view(assay, self._params(), offsets)

        def signal(concentrations: np.ndarray) -> np.ndarray:
            return ida_signal(
                I0=IDA_TRUE['I0'],
                Ka_guest=IDA_TRUE['Ka_guest'],
                I_dye_free=IDA_TRUE['I_dye_free'],
                I_dye_bound=IDA_TRUE['I_dye_bound'],
                Ka_dye=IDA_TRUE['Ka_dye'],
                h0=IDA_TRUE['h0'] * 1.1,
                d0=IDA_TRUE['d0'],
                g0_values=concentrations * 1.05,
            )

        measured = assay.x_data.magnitude
        residuals = assay.y_data.magnitude - signal(measured)
        assert rmse == pytest.approx(float(np.sqrt(np.mean(residuals**2))), rel=1e-12)
        observed = assay.y_data.magnitude
        expected_r2 = 1 - np.sum(residuals**2) / np.sum((observed - observed.mean()) ** 2)
        assert r_squared == pytest.approx(float(expected_r2), rel=1e-12)
        # The curve is drawn against the concentrations as entered — the axis the data sit on.
        assert (x_fit.magnitude.min(), x_fit.magnitude.max()) == (measured.min(), measured.max())
        np.testing.assert_allclose(y_fit.magnitude, signal(x_fit.magnitude), rtol=1e-12)

    def test_moving_an_input_is_the_same_as_having_entered_the_moved_value(self):
        entered = fit_view(self._assay(h0=IDA_TRUE['h0'] * 1.1), self._params())
        moved = fit_view(self._assay(), self._params(), {'h0': 0.1})

        assert moved[:2] == pytest.approx(entered[:2], rel=1e-12)
        np.testing.assert_allclose(moved[3].magnitude, entered[3].magnitude, rtol=1e-12)

    def test_no_offsets_scores_the_fit_at_the_inputs_as_entered(self):
        assay = self._assay()
        scored = fit_view(assay, self._params())

        assert scored[:2] == fit_view(assay, self._params(), {})[:2]
        np.testing.assert_array_equal(
            scored[3].magnitude, assay.forward_model(self._params(), x=scored[2].magnitude).magnitude
        )


# Bounds no fit below runs into by accident: the binding constant spans twenty
# decades and every signal coefficient has room on both sides of where the data
# put it. What a test pins, it pins on purpose.
_OPEN_KA = {'Ka_guest': (Q_(1e-8, '1/M'), Q_(1e12, '1/M'))}
_OPEN_SIGNAL = {
    'I0': (Q_(-1000, 'au'), Q_(1000, 'au')),
    'I_dye_free': (Q_(0, 'au/M'), Q_(1e9, 'au/M')),
    'I_dye_bound': (Q_(0, 'au/M'), Q_(1e9, 'au/M')),
}


class TestTheParametersTheLackOfFitTestCounts:
    """``p`` of the replicate F test is what the fit moved, not what it was free to move.

    The bounded solve holds a signal coefficient on its bound and the search
    holds a Ka estimate on its bound. Neither is fitted, so the residual keeps
    the dimension each would have taken; counting them shrinks ``n - p`` and
    inflates the ratio.
    """

    @staticmethod
    def _replicates(y: np.ndarray, seed: int, noise: float = 0.01, rows: int = 3) -> np.ndarray:
        """*rows* replicates of the clean signal *y*, each with its own Gaussian noise."""
        rng = np.random.default_rng(seed)
        return np.vstack([y + rng.normal(0.0, noise * np.ptp(y), y.size) for _ in range(rows)])

    @staticmethod
    def _fit(assay: BaseAssay, bounds: dict) -> tuple[Projection, object]:
        """The projection of *assay* under *bounds* and its fit, with every input held as entered."""
        projection = Projection(assay, _resolve_bounds(assay, bounds))
        return projection, input_aware(projection, projection.fit(), ())

    @classmethod
    def _ida(cls, seed: int) -> tuple[IDAAssay, np.ndarray]:
        x, y = _make_ida_data(IDA_TRUE, n_points=12)
        replicates = cls._replicates(y, seed)
        assay = IDAAssay(
            x_data=Q_(x, 'M'),
            y_data=Q_(replicates.mean(axis=0), 'au'),
            Ka_dye=Q_(IDA_TRUE['Ka_dye'], '1/M'),
            h0=Q_(IDA_TRUE['h0'], 'M'),
            d0=Q_(IDA_TRUE['d0'], 'M'),
        )
        return assay, replicates

    @classmethod
    def _gda(cls, seed: int) -> tuple[GDAAssay, np.ndarray]:
        # A GDA design has an offset column and two species columns no mass
        # balance ties, so pinning one coefficient lowers the rank of what is
        # left by one — the count moves where a tied design would hide it.
        x, y = _make_gda_data(GDA_TRUE, n_points=12)
        replicates = cls._replicates(y, seed)
        assay = GDAAssay(
            x_data=Q_(x, 'M'),
            y_data=Q_(replicates.mean(axis=0), 'au'),
            Ka_dye=Q_(GDA_TRUE['Ka_dye'], '1/M'),
            h0=Q_(GDA_TRUE['h0'], 'M'),
            g0=Q_(GDA_TRUE['g0'], 'M'),
        )
        return assay, replicates

    def test_a_fit_that_placed_every_parameter_itself_counts_every_free_one(self):
        """Nothing on a bound: the count is the free-parameter count, and the ratio is that count's."""
        assay, replicates = self._ida(seed=0)
        projection, aware = self._fit(assay, {**_OPEN_KA, **_OPEN_SIGNAL})

        i0, dye_free, dye_bound = aware.fit.coefficients
        assert -1000.0 < i0 < 1000.0 and 0.0 < dye_free < 1e9 and 0.0 < dye_bound < 1e9
        assert 1e-8 < aware.fit.ka['Ka_guest'] < 1e12
        # Ka and the three signal columns, of which a mass balance ties two
        # (free and bound dye add up to the dye total) to the offset: rank two.
        assert aware.fit.n_params == 1 + 2

        # The projection weighs every point alike, the weights of a law taken as constant.
        found, skipped = _misfit(projection, aware, replicates, noise_law(None))
        assert skipped == ''
        curve = projection.signals[0] - projection.residual(aware.fit.ka, 0, aware.fit.offsets)
        every_free = lack_of_fit(replicates, curve, aware.fit.n_params)
        # The scatter of three replicates about their own line in the mean
        # curve, at 12 points: two of the twelve dimensions go to the line and
        # one of the three replicates to the mean.
        assert found.dof == (12 - aware.fit.n_params, 2 * 10)
        assert (found.statistic, found.p_value) == (every_free.statistic, every_free.p_value)
        # No law was read, so the reference is the F distribution itself.
        assert found.reference == 'F'

    def test_a_coefficient_the_solve_holds_on_its_bound_is_not_counted(self):
        """The GDA truth has no offset, so a floor of zero under I0 pins it wherever the noise asks for less.

        The ratio is then the lack-of-fit mean square on the degrees of freedom
        that count leaves, over the pure-error mean square of the replicates.
        """
        assay, replicates = self._gda(seed=5)
        projection, aware = self._fit(assay, {**_OPEN_KA, **_OPEN_SIGNAL, 'I0': (Q_(0, 'au'), Q_(1000, 'au'))})

        i0, dye_free, dye_bound = aware.fit.coefficients
        assert i0 == 0.0, 'the bounded solve holds the offset on its floor'
        assert 0.0 < dye_free < 1e9 and 0.0 < dye_bound < 1e9
        assert 1e-8 < aware.fit.ka['Ka_guest'] < 1e12
        # Ka and the two species coefficients; the offset on its floor is held there.
        count = aware.fit.n_params
        assert count == 1 + 2

        # The same data with the floor lifted: the offset goes free, and is counted.
        lifted, lifted_aware = self._fit(assay, {**_OPEN_KA, **_OPEN_SIGNAL})
        assert lifted_aware.fit.coefficients[0] < 0.0
        assert lifted_aware.fit.n_params == count + 1

        # The projection weighs every point alike, the weights of a law taken as constant.
        found, skipped = _misfit(projection, aware, replicates, noise_law(None))
        assert skipped == ''
        rows, points = replicates.shape
        mean = replicates.mean(axis=0)
        curve = projection.signals[0] - projection.residual(aware.fit.ka, 0, aware.fit.offsets)
        misfit_mean_square = rows * float(np.sum((mean - curve) ** 2)) / (points - count)
        # The noise the curve is judged against: what is left of each replicate
        # once its own straight line in the mean curve is taken out, solved
        # here by a plain least-squares fit of that line.
        line = np.column_stack([np.ones(points), mean])
        scatter = replicates - (np.linalg.lstsq(line, replicates.T, rcond=None)[0].T @ line.T)
        pure_error_mean_square = float(np.sum(scatter**2)) / ((rows - 1) * (points - 2))
        assert found.dof == (points - count, (rows - 1) * (points - 2))
        assert found.statistic == pytest.approx(misfit_mean_square / pure_error_mean_square, rel=1e-9)

    def test_a_ka_estimate_on_its_bound_is_not_counted(self):
        """Bounds that stop below where the data put Ka leave the estimate on the upper one, held there."""
        assay, _ = self._gda(seed=0)
        capped = {**_OPEN_SIGNAL, 'Ka_guest': (Q_(1e-8, '1/M'), Q_(1.2e6, '1/M'))}
        _, aware = self._fit(assay, capped)

        assert aware.fit.ka['Ka_guest'] == pytest.approx(1.2e6, rel=1e-12)
        i0, dye_free, dye_bound = aware.fit.coefficients
        assert -1000.0 < i0 < 1000.0 and 0.0 < dye_free < 1e9 and 0.0 < dye_bound < 1e9
        # The three GDA signal columns, which no mass balance ties; Ka on its bound is held there.
        assert aware.fit.n_params == 3

        # The same data over bounds the estimate lies inside: the constant is counted.
        _, inside_aware = self._fit(assay, {**_OPEN_KA, **_OPEN_SIGNAL})
        assert inside_aware.fit.ka['Ka_guest'] > 1.2e6
        assert inside_aware.fit.n_params == aware.fit.n_params + 1


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


class TestTheNoiseLawTheFitCarries:
    """What the replicates behind a fit say about its noise, and what that does to the numbers."""

    @staticmethod
    def _ida_assay(signal: np.ndarray, x: np.ndarray) -> IDAAssay:
        return IDAAssay(x_data=Q_(x, 'M'), y_data=Q_(signal, 'au'), **_IDA_CONDITIONS)

    def test_a_single_titration_is_fitted_with_no_weights_and_records_why(self):
        """One signal cannot show how the noise varies, so the fit is the unweighted one, to the last bit."""
        x, y = _make_ida_data(IDA_TRUE, n_points=15)
        assay = self._ida_assay(y + np.random.default_rng(2).normal(0.0, 0.01 * np.ptp(y), y.size), x)

        result = fit_assay(assay, FitConfig(custom_bounds=GDA_IDA_RECOVERY_BOUNDS))

        assert result.noise.basis is NoiseBasis.SINGLE_TITRATION
        assert not result.noise.estimated
        np.testing.assert_array_equal(result.noise.weights(assay.y_data.magnitude), np.ones(15))
        # The same assay through the engine with no weights at all: the same
        # numbers, exactly, not to a tolerance.
        projection = Projection(assay, _resolve_bounds(assay, GDA_IDA_RECOVERY_BOUNDS))
        params = projection.params(projection.fit())
        assert [result.parameters[k].magnitude for k in assay.parameter_keys] == list(params)

    def test_a_fit_of_replicates_that_scatter_with_the_signal_is_weighted_by_their_law(self):
        """The law the replicates show is recorded, and it is what the fit was made with.

        Replicates whose noise grows with the signal make the low end of the
        titration the precise end, and the fit that counts it so is a different
        fit from the one that counts every point equally.
        """
        x, y = _make_ida_data(IDA_TRUE, n_points=15)
        rng = np.random.default_rng(5)
        signals = np.vstack([y * (1.0 + rng.normal(0.0, 0.03, y.size)) for _ in range(4)])
        ms = MeasurementSet(concentrations=x, signals=signals, replica_ids=('a', 'b', 'c', 'd'))
        config = FitConfig(custom_bounds=GDA_IDA_RECOVERY_BOUNDS, per_replica=False)

        result = fit_measurement_set(ms, IDAAssay, _IDA_CONDITIONS, config)

        assert result.noise.estimated and result.noise.n_replicates == 4
        assert 0.0 < result.noise.share <= 1.0
        assay = self._ida_assay(ms.average_signal(), x)
        bounds = _resolve_bounds(assay, GDA_IDA_RECOVERY_BOUNDS)
        weights = result.noise.weights(assay.y_data.magnitude)
        assert weights.max() > 2 * weights.min(), 'the law has to weight the points differently to be tested'
        weighted = Projection(assay, bounds, point_weights=weights)
        equal = Projection(assay, bounds)
        reported = result.parameters['Ka_guest'].magnitude
        assert reported == weighted.fit().ka['Ka_guest']
        assert reported != equal.fit().ka['Ka_guest']

    def test_the_misfit_test_of_a_weighted_fit_keeps_its_ratio_and_reads_its_p_value_from_a_simulation(self):
        """Weights read from the replicates' own scatter make F only approximate, so the reference is simulated.

        The ratio itself is the weighted lack-of-fit F ratio, worked out here by
        hand: the misfit of the fitted curve against the mean of the replicates
        over the scatter of each replicate about its own weighted line in the
        mean, both counted by the law's weights.
        """
        x, y = _make_ida_data(IDA_TRUE, n_points=15)
        rng = np.random.default_rng(5)
        signals = np.vstack([y * (1.0 + rng.normal(0.0, 0.03, y.size)) for _ in range(4)])
        ms = MeasurementSet(concentrations=x, signals=signals, replica_ids=('a', 'b', 'c', 'd'))
        config = FitConfig(custom_bounds=GDA_IDA_RECOVERY_BOUNDS, per_replica=False)

        result = fit_measurement_set(ms, IDAAssay, _IDA_CONDITIONS, config)
        test = result.diagnostics.misfit

        assert result.noise.estimated and test.kind == 'lack_of_fit'
        assert test.reference == 'bootstrap'
        assert result.diagnostics.conditional_misfit == test, 'with no input free to move the two tests are one'
        rows, points = signals.shape
        mean = signals.mean(axis=0)
        root = np.sqrt(result.noise.weights(mean))
        assay = self._ida_assay(mean, x)
        curve = assay.forward_model(np.array([result.parameters[k].magnitude for k in assay.parameter_keys])).magnitude
        line = np.column_stack([np.ones(points), mean]) * root[:, None]
        whitened = signals * root
        scatter = whitened - (line @ np.linalg.lstsq(line, whitened.T, rcond=None)[0]).T
        # The parameter count behind dof[0] is pinned by TestTheParametersTheLackOfFitTestCounts.
        misfit_mean_square = rows * float(np.sum((root * (mean - curve)) ** 2)) / test.dof[0]
        pure_error_mean_square = float(np.sum(scatter**2)) / ((rows - 1) * (points - 2))
        assert test.dof[1] == (rows - 1) * (points - 2)
        assert test.statistic == pytest.approx(misfit_mean_square / pure_error_mean_square, rel=1e-6)
        # A Monte-Carlo p-value over 199 draws: (1 + exceedances) / 200.
        assert round(test.p_value * 200, 9) == int(round(test.p_value * 200)) and 0.0 < test.p_value <= 1.0


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
            # A calibration line is a linear regression, not a projection: it
            # reads no noise law off its replicates and needs none.
            assert result.noise is None

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
