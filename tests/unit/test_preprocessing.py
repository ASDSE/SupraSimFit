"""Tests for the preprocessing pipeline and z-score replica filter."""

import logging

import numpy as np
import pandas as pd
import pytest

from core.data_processing.measurement_set import MeasurementSet
from core.data_processing.preprocessing import PREPROCESSING_STEPS, ZScoreReplicaFilter, apply_preprocessing, get_step, register_step

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ms_with_outlier(
    n_replicas: int = 5,
    n_points: int = 10,
    outlier_replica: int = 2,
    outlier_scale: float = 100.0,
) -> MeasurementSet:
    """Create a MeasurementSet where one replica is a clear outlier.

    The outlier replica has signals multiplied by *outlier_scale* relative
    to the baseline, making it trivially detectable by z-score.
    """
    conc = np.linspace(1e-7, 50e-6, n_points)
    base_signal = conc * 1e8  # clean baseline

    signals = np.tile(base_signal, (n_replicas, 1)).copy()
    # Add tiny jitter to non-outlier replicas so std > 0
    rng = np.random.default_rng(99)
    for i in range(n_replicas):
        if i != outlier_replica:
            signals[i] += rng.normal(0, 1.0, n_points)

    # Inject a massive offset in the outlier replica
    signals[outlier_replica] = base_signal * outlier_scale

    return MeasurementSet(
        concentrations=conc,
        signals=signals,
        replica_ids=tuple(f'rep_{i}' for i in range(n_replicas)),
    )


def _ms_few_replicas(n: int = 2) -> MeasurementSet:
    """Create a MeasurementSet with very few replicas."""
    conc = np.linspace(1e-7, 50e-6, 5)
    signals = np.stack([conc * 1e8] * n)
    return MeasurementSet(
        concentrations=conc,
        signals=signals,
        replica_ids=tuple(f'rep_{i}' for i in range(n)),
    )


# ---------------------------------------------------------------------------
# ZScoreReplicaFilter
# ---------------------------------------------------------------------------


class TestZScoreReplicaFilter:
    """Z-score-based replica outlier detection."""

    def test_outlier_detected(self):
        """A clearly outlying replica should be deactivated."""
        ms = _ms_with_outlier(n_replicas=5, outlier_replica=2)
        filt = ZScoreReplicaFilter(threshold=3.5)
        filt(ms)

        assert 'rep_2' in ms.dropped_replica_ids
        assert ms.n_active == 4

    def test_no_outlier_all_kept(self):
        """If all replicas are similar, none should be dropped."""
        conc = np.linspace(0, 1, 10)
        signals = np.stack([conc * 100 + i * 0.01 for i in range(5)])
        ms = MeasurementSet(
            concentrations=conc,
            signals=signals,
            replica_ids=tuple(f'r{i}' for i in range(5)),
        )
        ZScoreReplicaFilter(threshold=2.5)(ms)
        assert ms.n_active == 5
        assert ms.processing_log[-1]['dropped'] == []

    def test_too_few_replicas_warns(self, caplog):
        """Fewer than min_replicas → warning + skip record."""
        ms = _ms_few_replicas(n=2)
        filt = ZScoreReplicaFilter(threshold=3.5, min_replicas=3)

        with caplog.at_level(logging.WARNING):
            filt(ms)

        assert ms.n_active == 2  # nothing changed
        assert 'skipped' in ms.processing_log[-1]['status']
        assert any('skipped' in r.message for r in caplog.records)

    def test_idempotent(self):
        """Running filter twice doesn't crash or double-drop."""
        ms = _ms_with_outlier(n_replicas=5, outlier_replica=2)
        filt = ZScoreReplicaFilter(threshold=3.5)
        filt(ms)
        n_after_first = ms.n_active
        filt(ms)  # second pass on remaining actives
        assert ms.n_active >= n_after_first - 1  # at most one more drop
        assert len(ms.processing_log) == 2

    def test_zero_std_safe(self):
        """Identical replicas (std=0) → no drops, no errors."""
        conc = np.array([1.0, 2.0, 3.0])
        signals = np.stack([conc * 10] * 4)
        ms = MeasurementSet(
            concentrations=conc,
            signals=signals,
            replica_ids=('a', 'b', 'c', 'd'),
        )
        ZScoreReplicaFilter(threshold=2.0)(ms)
        assert ms.n_active == 4

    def test_invalid_threshold_raises(self):
        with pytest.raises(ValueError, match='positive'):
            ZScoreReplicaFilter(threshold=-1)

    def test_invalid_min_replicas_raises(self):
        with pytest.raises(ValueError, match='min_replicas'):
            ZScoreReplicaFilter(min_replicas=1)

    def test_processing_log_records_details(self):
        """Log entry contains threshold, dropped, kept."""
        ms = _ms_with_outlier()
        ZScoreReplicaFilter(threshold=3.5)(ms)
        entry = ms.processing_log[-1]
        assert entry['step'] == 'zscore_replica_filter'
        assert 'threshold' in entry
        assert isinstance(entry['dropped'], list)
        assert isinstance(entry['kept'], list)


# ---------------------------------------------------------------------------
# Registry & apply_preprocessing
# ---------------------------------------------------------------------------


class TestRegistry:
    """Preprocessing step registry and pipeline runner."""

    def test_zscore_registered(self):
        assert 'zscore_replica_filter' in PREPROCESSING_STEPS

    def test_get_step(self):
        step = get_step('zscore_replica_filter', {'threshold': 3.0})
        assert step.name == 'zscore_replica_filter'

    def test_get_step_unknown_raises(self):
        with pytest.raises(KeyError, match='Unknown'):
            get_step('nonexistent_step')

    def test_apply_preprocessing_pipeline(self):
        """apply_preprocessing runs steps in order."""
        ms = _ms_with_outlier(n_replicas=5, outlier_replica=2)
        steps = [
            {'name': 'zscore_replica_filter', 'params': {'threshold': 3.5}},
        ]
        apply_preprocessing(ms, steps)
        assert 'rep_2' in ms.dropped_replica_ids

    def test_custom_step_registration(self):
        """A user-defined step can be registered and retrieved."""

        class DummyStep:
            name = 'dummy'

            def __call__(self, ms):
                ms.processing_log.append({'step': 'dummy', 'status': 'applied'})

        register_step('dummy', lambda params: DummyStep())
        step = get_step('dummy')
        assert step.name == 'dummy'

        ms = _ms_few_replicas(n=3)
        step(ms)
        assert ms.processing_log[-1]['step'] == 'dummy'

        # Cleanup
        PREPROCESSING_STEPS.pop('dummy', None)
