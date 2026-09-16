"""Tests for prepare_plot_data() — the MeasurementSet → plot dict bridge."""

import numpy as np
import pytest

from core.data_processing.measurement_set import MeasurementSet
from core.data_processing.plotting import prepare_plot_data
from core.pipeline.fit_pipeline import FitResult
from core.units import Q_


def _simple_ms(n_replicas=3, n_points=5):
    conc = np.array([1.0, 2.0, 3.0, 4.0, 5.0][:n_points])
    signals = np.stack([conc * (i + 1) for i in range(n_replicas)])
    return MeasurementSet(
        concentrations=conc,
        signals=signals,
        replica_ids=tuple(f'r{i}' for i in range(n_replicas)),
    )


def _simple_fit_result(metadata=None):
    x = np.linspace(0, 5, 20)
    return FitResult(
        parameters={'slope': Q_(1.0, 'au/M')},
        rmse=0.01,
        r_squared=0.99,
        n_passing=1,
        n_total=1,
        x_fit=Q_(x, 'M'),
        y_fit=Q_(x * 1.05, 'au'),
        assay_type='DYE_ALONE',
        model_name='linear',
        metadata={'active_replica_ids': ['r0', 'r1', 'r2']} if metadata is None else metadata,
    )


def _per_replicate_record(given, used):
    """Metadata of a per-replicate fit given *given* replicates that used *used*."""
    return {
        'active_replica_ids': list(given),
        'replica_ids_fit': list(used),
        'replica_failures': {
            rid: 'None of its fit attempts reached the minimum R².' for rid in given if rid not in used
        },
    }


def _noisy_ms(n_replicas=5, n_points=6, seed=3):
    """Replicates whose means differ, so a mean over a subset is distinguishable from the full mean."""
    rng = np.random.default_rng(seed)
    conc = np.linspace(1e-6, 6e-6, n_points)
    signals = np.stack([1e4 * (1 + 0.3 * i) + rng.normal(0, 50, n_points) for i in range(n_replicas)])
    return MeasurementSet(concentrations=conc, signals=signals, replica_ids=tuple(str(i) for i in range(n_replicas)))


class TestPrepPlotDataReplicas:
    def test_active_replicas_only(self):
        ms = _simple_ms()
        ms.set_active('r1', False)
        data = prepare_plot_data(ms)

        ids = [rid for rid, _ in data['active_replicas']]
        assert len(ids) == 2
        assert 'r0' in ids and 'r2' in ids
        assert 'r1' not in ids
        assert data['dropped_replicas'] == []
        assert data['left_out_replicas'] == []

    def test_show_dropped_includes_inactive(self):
        ms = _simple_ms()
        ms.set_active('r1', False)
        data = prepare_plot_data(ms, show_dropped=True)

        assert len(data['dropped_replicas']) == 1
        assert data['dropped_replicas'][0][0] == 'r1'

    def test_average_matches_active(self):
        ms = _simple_ms()
        ms.set_active('r2', False)
        data = prepare_plot_data(ms)

        expected_avg = ms.average_signal(active_only=True)
        np.testing.assert_allclose(data['average'], expected_avg)

    def test_concentrations_match_ms(self):
        ms = _simple_ms()
        data = prepare_plot_data(ms)
        np.testing.assert_array_equal(data['concentrations'], ms.concentrations)


class TestPrepPlotDataFits:
    def test_fit_results_included(self):
        ms = _simple_ms()
        fr = _simple_fit_result()
        data = prepare_plot_data(ms, fit_results=[fr])

        assert len(data['fits']) == 1
        assert data['fits'][0]['label'] == 'Fit'
        np.testing.assert_array_equal(data['fits'][0]['x'], fr.x_fit.magnitude)
        assert data['fits'][0]['id'] == fr.id
        assert data['fits'][0]['replica_ids'] == ('r0', 'r1', 'r2')

    def test_no_fit_results_none(self):
        ms = _simple_ms()
        data = prepare_plot_data(ms, fit_results=None)
        assert data['fits'] == []


class TestMeanFollowsTheFittedReplicates:
    """G7: the Fit Curve's mean is the average the shown fit's RMSE and R² are measured against."""

    def test_mean_is_over_the_replicates_the_fit_used_and_left_out_ones_are_listed(self):
        """Catches a mean over every active replicate, which includes a replicate the fit left out."""
        ms = _noisy_ms()
        fit = _simple_fit_result(_per_replicate_record(ms.replica_ids, ['1', '2', '3', '4']))

        data = prepare_plot_data(ms, [fit], show_dropped=True)

        used_mean = ms.signals[1:].mean(axis=0)
        np.testing.assert_allclose(data['average'], used_mean, rtol=1e-15)
        assert not np.allclose(data['average'], ms.signals.mean(axis=0))
        assert [rid for rid, _ in data['active_replicas']] == ['1', '2', '3', '4']
        assert [rid for rid, _ in data['left_out_replicas']] == ['0']
        np.testing.assert_array_equal(data['left_out_replicas'][0][1], ms.signals[0])
        assert data['dropped_replicas'] == []
        assert data['all_replica_ids'] == ms.replica_ids

    def test_replicate_switched_off_before_the_fit_stays_dropped(self):
        ms = _noisy_ms()
        ms.set_active('1', False)
        fit = _simple_fit_result(_per_replicate_record(ms.active_replica_ids, ['2', '3', '4']))

        data = prepare_plot_data(ms, [fit], show_dropped=True)

        np.testing.assert_allclose(data['average'], ms.signals[2:].mean(axis=0), rtol=1e-15)
        assert [rid for rid, _ in data['left_out_replicas']] == ['0']
        assert [rid for rid, _ in data['dropped_replicas']] == ['1']

    def test_without_a_fit_the_mean_covers_every_active_replicate(self):
        ms = _noisy_ms()
        data = prepare_plot_data(ms, [], show_dropped=True)

        np.testing.assert_allclose(data['average'], ms.signals.mean(axis=0), rtol=1e-15)
        assert data['left_out_replicas'] == []

    def test_the_last_fit_sets_the_mean_and_each_fit_names_its_replicates(self):
        """With overlaid fits, the mean follows the one the summary panel reports (the last)."""
        ms = _noisy_ms()
        every = _simple_fit_result({'active_replica_ids': list(ms.replica_ids)})
        some = _simple_fit_result(_per_replicate_record(ms.replica_ids, ['0', '2', '3', '4']))

        data = prepare_plot_data(ms, [every, some])

        np.testing.assert_allclose(data['average'], ms.signals[[0, 2, 3, 4]].mean(axis=0), rtol=1e-15)
        assert [fit['replica_ids'] for fit in data['fits']] == [tuple(ms.replica_ids), ('0', '2', '3', '4')]
        assert [rid for rid, _ in data['left_out_replicas']] == ['1']

    def test_a_fit_on_a_replicate_that_is_off_now_is_refused(self):
        ms = _noisy_ms()
        fit = _simple_fit_result(_per_replicate_record(ms.replica_ids, ['1', '2', '3', '4']))
        ms.set_active('2', False)

        with pytest.raises(ValueError, match='not active'):
            prepare_plot_data(ms, [fit])

    def test_a_fit_without_a_replicate_record_is_refused(self):
        ms = _noisy_ms()
        with pytest.raises(ValueError, match='does not record'):
            prepare_plot_data(ms, [_simple_fit_result({})])
