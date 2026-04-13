"""Tests for MeasurementSet construction and behaviour."""

import numpy as np
import pandas as pd
import pytest

from core.data_processing.measurement_set import MeasurementSet
from core.units import Q_

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sample_dataframe(n_replicas: int = 3, n_points: int = 10) -> pd.DataFrame:
    """Build a simple long-form DataFrame with known values."""
    conc = np.linspace(1e-7, 50e-6, n_points)
    rows = []
    for r in range(n_replicas):
        for c in conc:
            rows.append({'concentration': c, 'signal': c * (r + 1) * 1e6, 'replica': r})
    return pd.DataFrame(rows)


def _sample_measurement_set(**kwargs) -> MeasurementSet:
    """Shortcut to create a MeasurementSet from a sample DataFrame."""
    df = _sample_dataframe(**kwargs)
    return MeasurementSet.from_dataframe(df)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    """MeasurementSet construction and validation."""

    def test_from_dataframe_basic(self):
        """Happy-path construction from a long-form DataFrame."""
        ms = _sample_measurement_set(n_replicas=3, n_points=10)
        assert ms.n_replicas == 3
        assert ms.n_points == 10
        assert ms.n_active == 3
        assert len(ms.replica_ids) == 3

    def test_from_dataframe_sorted(self):
        """Concentrations are sorted ascending after construction."""
        ms = _sample_measurement_set()
        assert np.all(np.diff(ms.concentrations) >= 0)

    def test_missing_column_raises(self):
        """Missing required column raises ValueError."""
        df = pd.DataFrame({'x': [1], 'y': [2]})
        with pytest.raises(ValueError, match='Missing required column'):
            MeasurementSet.from_dataframe(df)

    def test_mismatched_grids_raises(self):
        """Replicas with different concentration grids raise ValueError."""
        df = pd.DataFrame(
            {
                'concentration': [1.0, 2.0, 1.0, 3.0],
                'signal': [10, 20, 10, 30],
                'replica': [0, 0, 1, 1],
            }
        )
        with pytest.raises(ValueError, match='different concentration grid'):
            MeasurementSet.from_dataframe(df)

    def test_shape_validation_1d_concentrations(self):
        """concentrations must be 1-D."""
        with pytest.raises(ValueError, match='1-D'):
            MeasurementSet(
                concentrations=np.ones((2, 3)),
                signals=np.ones((2, 3)),
                replica_ids=('a', 'b'),
            )

    def test_shape_validation_2d_signals(self):
        """signals must be 2-D."""
        with pytest.raises(ValueError, match='2-D'):
            MeasurementSet(
                concentrations=np.ones(3),
                signals=np.ones(3),
                replica_ids=('a',),
            )

    def test_shape_validation_columns_match(self):
        """signals columns must match concentrations length."""
        with pytest.raises(ValueError, match='signals columns'):
            MeasurementSet(
                concentrations=np.ones(3),
                signals=np.ones((2, 5)),
                replica_ids=('a', 'b'),
            )

    def test_shape_validation_replica_ids_match(self):
        """replica_ids length must match signals rows."""
        with pytest.raises(ValueError, match='replica_ids length'):
            MeasurementSet(
                concentrations=np.ones(3),
                signals=np.ones((2, 3)),
                replica_ids=('only_one',),
            )


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


class TestImmutability:
    """Raw data arrays are read-only after construction."""

    def test_concentrations_readonly(self):
        ms = _sample_measurement_set()
        assert ms.concentrations.flags.writeable is False

    def test_signals_readonly(self):
        ms = _sample_measurement_set()
        assert ms.signals.flags.writeable is False


# ---------------------------------------------------------------------------
# UUID
# ---------------------------------------------------------------------------


class TestUUID:
    """Auto-generated IDs are unique."""

    def test_unique_ids(self):
        ms1 = _sample_measurement_set()
        ms2 = _sample_measurement_set()
        assert ms1.id != ms2.id

    def test_id_is_hex_string(self):
        ms = _sample_measurement_set()
        assert isinstance(ms.id, str)
        assert len(ms.id) == 32
        int(ms.id, 16)  # must be valid hex


# ---------------------------------------------------------------------------
# Replica management
# ---------------------------------------------------------------------------


class TestReplicaManagement:
    """Active mask management."""

    def test_all_active_initially(self):
        ms = _sample_measurement_set(n_replicas=4)
        assert ms.n_active == 4
        assert ms.dropped_replica_ids == []

    def test_set_active_false(self):
        ms = _sample_measurement_set(n_replicas=3)
        rid = ms.replica_ids[1]
        ms.set_active(rid, False)
        assert ms.n_active == 2
        assert rid in ms.dropped_replica_ids
        assert rid not in ms.active_replica_ids

    def test_set_active_true_reactivates(self):
        ms = _sample_measurement_set(n_replicas=3)
        rid = ms.replica_ids[0]
        ms.set_active(rid, False)
        ms.set_active(rid, True)
        assert ms.n_active == 3

    def test_unknown_replica_raises(self):
        ms = _sample_measurement_set()
        with pytest.raises(ValueError, match='Unknown replica_id'):
            ms.set_active('nonexistent', False)

    def test_is_active(self):
        ms = _sample_measurement_set()
        rid = ms.replica_ids[0]
        assert ms.is_active(rid) is True
        ms.set_active(rid, False)
        assert ms.is_active(rid) is False

    def test_reset_active(self):
        ms = _sample_measurement_set(n_replicas=3)
        ms.set_active(ms.replica_ids[0], False)
        ms.set_active(ms.replica_ids[1], False)
        assert ms.n_active == 1
        ms.reset_active()
        assert ms.n_active == 3


# ---------------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------------


class TestDataAccess:
    """iter_replicas, get_replica_signal, average_signal."""

    def test_iter_replicas_active_only(self):
        ms = _sample_measurement_set(n_replicas=3)
        ms.set_active(ms.replica_ids[1], False)
        ids = [rid for rid, _ in ms.iter_replicas(active_only=True)]
        assert len(ids) == 2
        assert ms.replica_ids[1] not in ids

    def test_iter_replicas_all(self):
        ms = _sample_measurement_set(n_replicas=3)
        ms.set_active(ms.replica_ids[1], False)
        ids = [rid for rid, _ in ms.iter_replicas(active_only=False)]
        assert len(ids) == 3

    def test_iter_replicas_returns_views(self):
        """Yielded signals are views (not copies) into the underlying array."""
        ms = _sample_measurement_set()
        for _, sig in ms.iter_replicas():
            assert sig.base is ms.signals or sig.base is not None

    def test_get_replica_signal(self):
        ms = _sample_measurement_set(n_replicas=2, n_points=5)
        rid = ms.replica_ids[0]
        sig = ms.get_replica_signal(rid)
        assert sig.shape == (5,)
        np.testing.assert_array_equal(sig, ms.signals[0])

    def test_average_signal_all(self):
        ms = _sample_measurement_set(n_replicas=3, n_points=5)
        avg = ms.average_signal(active_only=False)
        expected = ms.signals.mean(axis=0)
        np.testing.assert_allclose(avg, expected)

    def test_average_signal_active_only(self):
        ms = _sample_measurement_set(n_replicas=3, n_points=5)
        ms.set_active(ms.replica_ids[2], False)
        avg = ms.average_signal(active_only=True)
        expected = ms.signals[:2].mean(axis=0)
        np.testing.assert_allclose(avg, expected)

    def test_average_signal_no_replicas_raises(self):
        ms = _sample_measurement_set(n_replicas=1)
        ms.set_active(ms.replica_ids[0], False)
        with pytest.raises(ValueError, match='No replicas selected'):
            ms.average_signal()


# ---------------------------------------------------------------------------
# Bridge to assay objects
# ---------------------------------------------------------------------------


class TestToAssay:
    """to_assay construction of BaseAssay subclasses."""

    def test_to_assay_average(self):
        from core.assays.gda import GDAAssay

        ms = _sample_measurement_set(n_replicas=3, n_points=10)
        conditions = {'Ka_dye': Q_(5e5, '1/M'), 'h0': Q_(10e-6, 'M'), 'g0': Q_(20e-6, 'M')}
        assay = ms.to_assay(GDAAssay, conditions=conditions, use_average=True)
        assert isinstance(assay, GDAAssay)
        assert assay.x_data.shape == (10,)
        np.testing.assert_allclose(assay.x_data.magnitude, ms.concentrations)

    def test_to_assay_specific_replica(self):
        from core.assays.gda import GDAAssay

        ms = _sample_measurement_set(n_replicas=3, n_points=10)
        conditions = {'Ka_dye': Q_(5e5, '1/M'), 'h0': Q_(10e-6, 'M'), 'g0': Q_(20e-6, 'M')}
        rid = ms.replica_ids[1]
        assay = ms.to_assay(GDAAssay, conditions=conditions, replica_id=rid)
        expected_y = ms.get_replica_signal(rid)
        np.testing.assert_allclose(assay.y_data.magnitude, expected_y)

    def test_to_assay_inactive_replica_raises(self):
        from core.assays.gda import GDAAssay

        ms = _sample_measurement_set(n_replicas=3)
        rid = ms.replica_ids[0]
        ms.set_active(rid, False)
        with pytest.raises(ValueError, match='inactive'):
            ms.to_assay(GDAAssay, conditions={'Ka_dye': Q_(5e5, '1/M'), 'h0': Q_(10e-6, 'M'), 'g0': Q_(20e-6, 'M')}, replica_id=rid)

    def test_to_assay_no_average_no_replica_raises(self):
        from core.assays.gda import GDAAssay

        ms = _sample_measurement_set()
        with pytest.raises(ValueError, match='use_average'):
            ms.to_assay(GDAAssay, conditions={'Ka_dye': Q_(5e5, '1/M'), 'h0': Q_(10e-6, 'M'), 'g0': Q_(20e-6, 'M')}, use_average=False)

