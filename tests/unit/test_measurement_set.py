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

    def test_raw_arrays_are_readonly(self):
        ms = _sample_measurement_set()
        assert ms.concentrations.flags.writeable is False
        assert ms.signals.flags.writeable is False


# ---------------------------------------------------------------------------
# Replica management
# ---------------------------------------------------------------------------


class TestReplicaManagement:
    """Active mask management."""

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

    def test_reset_active(self):
        ms = _sample_measurement_set(n_replicas=3)
        ms.set_active(ms.replica_ids[0], False)
        ms.set_active(ms.replica_ids[1], False)
        assert ms.n_active == 1
        ms.reset_active()
        assert ms.n_active == 3


class TestWithActive:
    """A copy fixed to a replicate selection, which later changes to the original never reach."""

    def test_copy_has_exactly_the_given_replicates_active_and_keeps_the_id(self):
        ms = _sample_measurement_set(n_replicas=3)
        ms.set_active('0', False)

        copy = ms.with_active(['0', '2'])

        assert copy.active_replica_ids == ['0', '2']
        assert copy.id == ms.id
        assert ms.active_replica_ids == ['1', '2']

    def test_later_changes_to_the_original_do_not_reach_the_copy(self):
        ms = _sample_measurement_set(n_replicas=3)
        copy = ms.with_active(ms.active_replica_ids)
        average = copy.average_signal()

        ms.set_active('1', False)
        ms.set_concentrations(Q_(ms.concentrations * 2, 'M'))

        np.testing.assert_array_equal(copy.average_signal(), average)
        assert copy.concentrations[-1] == pytest.approx(50e-6)
        assert copy.active_replica_ids == ['0', '1', '2']

    def test_unknown_replicate_raises(self):
        with pytest.raises(ValueError, match="no replicate '7'"):
            _sample_measurement_set(n_replicas=3).with_active(['0', '7'])


class TestFingerprint:
    """The data identity a fit records: blind to the selection and the uuid, not to the values."""

    def test_same_values_give_the_same_fingerprint_whatever_is_active(self):
        first, second = _sample_measurement_set(), _sample_measurement_set()
        second.set_active('1', False)

        assert first.id != second.id
        assert first.fingerprint() == second.fingerprint()

    def test_a_changed_value_changes_the_fingerprint(self):
        ms = _sample_measurement_set()
        signals = np.array(ms.signals)
        signals[2, 4] *= 1 + 1e-12
        edited = MeasurementSet(concentrations=ms.concentrations, signals=signals, replica_ids=ms.replica_ids)
        rescaled = _sample_measurement_set()
        rescaled.set_concentrations(Q_(rescaled.concentrations, 'µM'))

        assert edited.fingerprint() != ms.fingerprint()
        assert rescaled.fingerprint() != ms.fingerprint()


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
            assert sig.base is ms.signals

    def test_average_signal_active_only(self):
        """Dropping a replica must exclude it from the mean.

        _sample_dataframe gives replica r the signal conc * (r+1) * 1e6,
        so with r0/r1 active the mean is conc * 1.5e6 — hand-computed, not
        re-derived from ms.signals.
        """
        ms = _sample_measurement_set(n_replicas=3, n_points=5)
        ms.set_active(ms.replica_ids[2], False)
        avg = ms.average_signal(active_only=True)
        np.testing.assert_allclose(avg, ms.concentrations * 1.5e6)

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
            ms.to_assay(
                GDAAssay,
                conditions={'Ka_dye': Q_(5e5, '1/M'), 'h0': Q_(10e-6, 'M'), 'g0': Q_(20e-6, 'M')},
                replica_id=rid,
            )

    def test_to_assay_no_average_no_replica_raises(self):
        from core.assays.gda import GDAAssay

        ms = _sample_measurement_set()
        with pytest.raises(ValueError, match='use_average'):
            ms.to_assay(
                GDAAssay,
                conditions={'Ka_dye': Q_(5e5, '1/M'), 'h0': Q_(10e-6, 'M'), 'g0': Q_(20e-6, 'M')},
                use_average=False,
            )


class TestSetConcentrations:
    """``set_concentrations`` mutates the grid in place via a Pint Quantity."""

    def test_micromolar_quantity_stored_as_molar(self):
        ms = _sample_measurement_set(n_replicas=2, n_points=3)
        ms.set_concentrations(Q_(np.array([1.0, 2.0, 3.0]), 'µM'))
        np.testing.assert_allclose(ms.concentrations, [1e-6, 2e-6, 3e-6])

    def test_preserves_signals_and_replica_ids(self):
        ms = _sample_measurement_set(n_replicas=3, n_points=5)
        original_signals = ms.signals.copy()
        original_ids = ms.replica_ids
        ms.set_concentrations(Q_(np.linspace(1, 5, 5), 'mM'))
        np.testing.assert_array_equal(ms.signals, original_signals)
        assert ms.replica_ids == original_ids

    def test_preserves_active_mask(self):
        ms = _sample_measurement_set(n_replicas=3, n_points=4)
        ms.set_active(ms.replica_ids[0], False)
        active_before = list(ms.active_replica_ids)
        dropped_before = list(ms.dropped_replica_ids)
        ms.set_concentrations(Q_(np.array([1, 2, 3, 4]), 'µM'))
        assert ms.active_replica_ids == active_before
        assert ms.dropped_replica_ids == dropped_before

    def test_drop_metadata_keys(self):
        ms = _sample_measurement_set(n_replicas=2, n_points=3)
        ms.metadata['bmg_placeholder'] = True
        ms.metadata['source_file'] = 'plate.xlsx'
        ms.set_concentrations(
            Q_(np.array([1, 2, 3]), 'µM'),
            drop_metadata_keys=('bmg_placeholder',),
        )
        assert 'bmg_placeholder' not in ms.metadata
        assert ms.metadata['source_file'] == 'plate.xlsx'

    def test_rejects_non_quantity(self):
        ms = _sample_measurement_set(n_points=3)
        with pytest.raises(TypeError, match='Quantity'):
            ms.set_concentrations(np.array([1.0, 2.0, 3.0]))

    def test_rejects_wrong_dimensionality(self):
        ms = _sample_measurement_set(n_points=3)
        with pytest.raises(ValueError, match='dimensionality'):
            ms.set_concentrations(Q_(np.array([1.0, 2.0, 3.0]), 'm'))

    def test_rejects_length_mismatch(self):
        ms = _sample_measurement_set(n_points=5)
        with pytest.raises(ValueError, match='n_points'):
            ms.set_concentrations(Q_(np.array([1.0, 2.0]), 'µM'))

    def test_id_is_stable(self):
        ms = _sample_measurement_set(n_points=3)
        id_before = ms.id
        ms.set_concentrations(Q_(np.array([1, 2, 3]), 'µM'))
        assert ms.id == id_before

    def test_array_remains_read_only_after_set(self):
        ms = _sample_measurement_set(n_points=3)
        ms.set_concentrations(Q_(np.array([1, 2, 3]), 'µM'))
        with pytest.raises(ValueError, match='read-only'):
            ms.concentrations[0] = 0.0


# ---------------------------------------------------------------------------
# Data no fit can use are refused where they enter
# ---------------------------------------------------------------------------


def _grid(n: int = 6) -> np.ndarray:
    """Titrant series 0, 2, ..., 2(n-1) µM, written out in M."""
    return np.arange(n) * 2e-6


class TestRefusedData:
    """Non-finite or negative concentrations, missing or infinite signals and too-short titrations.

    Each is refused with an :class:`InvalidData` whose message names the point
    (by its position and concentration), the replicate and the file, so that a
    fit is never run on them.
    """

    @pytest.mark.parametrize(
        'value, shown',
        [(-1e-6, '-1 µM'), (np.nan, 'no concentration'), (np.inf, 'infinite')],
    )
    def test_a_concentration_that_is_not_zero_or_more_names_its_point(self, value, shown):
        from core.data_processing.measurement_set import InvalidData

        x = _grid()
        x[3] = value
        with pytest.raises(InvalidData) as excinfo:
            MeasurementSet(
                concentrations=x,
                signals=np.ones((1, x.size)),
                replica_ids=('r0',),
                metadata={'source_file': '/some/where/run1.csv'},
            )
        message = str(excinfo.value)
        assert 'point 4 of 6' in message
        assert shown in message
        assert 'run1.csv' in message and '/some/where' not in message

    def test_zero_concentrations_and_negative_signals_are_data(self):
        """A blank at zero titrant and a blank-subtracted (negative) signal are ordinary measurements."""
        ms = MeasurementSet(
            concentrations=_grid(),
            signals=-np.arange(6.0).reshape(1, -1),
            replica_ids=('r0',),
        )
        assert ms.concentrations[0] == 0.0

    @pytest.mark.parametrize('value, shown', [(np.nan, 'no signal'), (np.inf, 'an infinite signal')])
    def test_a_bad_signal_of_a_single_titration_names_its_point(self, value, shown):
        from core.data_processing.measurement_set import InvalidData

        y = np.arange(6.0)
        y[2] = value
        with pytest.raises(InvalidData) as excinfo:
            MeasurementSet(concentrations=_grid(), signals=y.reshape(1, -1), replica_ids=('r0',))
        message = str(excinfo.value)
        assert shown in message
        assert '4 µM (point 3 of 6)' in message

    def test_a_missing_value_in_one_replicate_names_the_replicate_and_suggests_removing_it(self):
        from core.data_processing.measurement_set import InvalidData

        signals = np.tile(np.arange(6.0), (3, 1))
        signals[1, 4] = np.nan
        with pytest.raises(InvalidData) as excinfo:
            MeasurementSet(
                concentrations=_grid(),
                signals=signals,
                replica_ids=('a', 'b', 'c'),
                metadata={'source_file': 'plate.csv'},
            )
        message = str(excinfo.value)
        assert "replicate 'b'" in message
        assert '8 µM (point 5 of 6)' in message
        assert 'plate.csv' in message
        assert "remove replicate 'b'" in message

    def test_a_point_no_replicate_has_is_to_be_deleted_not_a_replicate(self):
        """Removing a replicate only moves the refusal to the next one, so the advice is to delete the point."""
        from core.data_processing.measurement_set import InvalidData

        signals = np.tile(np.arange(6.0), (2, 1))
        signals[:, 5] = np.nan
        with pytest.raises(InvalidData) as excinfo:
            MeasurementSet(concentrations=_grid(), signals=signals, replica_ids=('a', 'b'))
        message = str(excinfo.value)
        assert message.startswith('No replicate has a signal at')
        assert 'delete that titration point' in message and 'remove replicate' not in message

    def test_a_titration_shorter_than_any_model_needs_is_refused(self):
        from core.assays.registry import ASSAY_REGISTRY
        from core.data_processing.measurement_set import InvalidData

        # The smallest model of the registry fits two parameters; a fit of it needs a third point.
        fewest = min(len(meta.parameter_keys) for meta in ASSAY_REGISTRY.values())
        assert fewest == 2
        with pytest.raises(InvalidData, match='only 2 titration points'):
            MeasurementSet(concentrations=_grid(2), signals=np.ones((1, 2)), replica_ids=('r0',))
        assert MeasurementSet(concentrations=_grid(3), signals=np.ones((1, 3)), replica_ids=('r0',)).n_points == 3

    def test_data_with_no_measurement_are_refused(self):
        from core.data_processing.measurement_set import InvalidData

        with pytest.raises(InvalidData, match='no measurements'):
            MeasurementSet(concentrations=_grid(), signals=np.ones((0, 6)), replica_ids=())
        empty = pd.DataFrame({'concentration': [], 'signal': [], 'replica': []})
        with pytest.raises(InvalidData, match='empty.csv contain no measurements'):
            MeasurementSet.from_dataframe(empty, source_file='empty.csv')

    def test_a_replicate_missing_a_point_is_named_with_the_concentration_it_lacks(self):
        """The readers drop a blank cell, so a replicate with a missing value arrives one point short."""
        from core.data_processing.measurement_set import InvalidData

        rows = [
            {'concentration': c, 'signal': 10.0 + r, 'replica': r}
            for r in range(3)
            for c in _grid()
            if not (r == 2 and c == _grid()[1])
        ]
        with pytest.raises(InvalidData) as excinfo:
            MeasurementSet.from_dataframe(pd.DataFrame(rows), source_file='titration.csv')
        message = str(excinfo.value)
        assert "replicate '2'" in message
        assert 'no signal at 2 µM' in message
        assert 'titration.csv' in message
        assert "remove replicate '2'" in message

    def test_a_missing_well_of_a_plate_is_named_by_its_column(self):
        rows = [
            {'concentration': float(col), 'signal': 5.0, 'replica': r}
            for r in range(2)
            for col in range(1, 7)
            if not (r == 0 and col == 4)
        ]
        df = pd.DataFrame(rows)
        df.attrs['bmg_placeholder_concentrations'] = True
        with pytest.raises(ValueError, match="Replicate '0' .*plate column 4"):
            MeasurementSet.from_dataframe(df)

    def test_a_row_with_no_concentration_is_refused_as_such(self):
        """Not as two replicates on different grids, which is what the comparison alone would say."""
        from core.data_processing.measurement_set import InvalidData

        conc = list(_grid())
        rows = [{'concentration': c, 'signal': 1.0, 'replica': r} for r in range(2) for c in conc]
        rows[8]['concentration'] = np.nan
        with pytest.raises(InvalidData, match="Replicate '1' .*no concentration.*signal is 1"):
            MeasurementSet.from_dataframe(pd.DataFrame(rows))

    def test_a_negative_concentration_in_a_file_is_refused_at_load(self, tmp_path):
        from core.data_processing.measurement_set import InvalidData
        from core.io import load_measurements

        path = tmp_path / 'negative.csv'
        path.write_text('concentration,signal\n0,10\n1e-6,12\n-2e-6,14\n3e-6,15\n4e-6,16\n')
        with pytest.raises(InvalidData) as excinfo:
            MeasurementSet.from_dataframe(load_measurements(path), source_file=str(path))
        assert '-2 µM' in str(excinfo.value)
        assert 'negative.csv' in str(excinfo.value)

    def test_a_blank_cell_in_one_replicate_column_is_refused_at_load(self, tmp_path):
        from core.data_processing.measurement_set import InvalidData
        from core.io import load_measurements

        path = tmp_path / 'blank.csv'
        path.write_text('concentration,rep1,rep2\n0,10,11\n1e-6,12,\n2e-6,14,15\n3e-6,15,16\n4e-6,16,17\n')
        with pytest.raises(InvalidData) as excinfo:
            MeasurementSet.from_dataframe(load_measurements(path), source_file=str(path))
        message = str(excinfo.value)
        assert 'no signal at 1 µM' in message
        assert 'blank.csv' in message

    @pytest.mark.parametrize(
        'name, text',
        [
            ('single.csv', 'concentration,signal\n0,10\n1e-6,12\n2e-6,\n3e-6,15\n4e-6,16\n'),
            ('single.txt', 'var\tsignal\n0\t10\n1e-6\t12\n2e-6\t\n3e-6\t15\n4e-6\t16\n'),
        ],
    )
    def test_a_blank_signal_in_a_single_titration_is_refused_not_dropped(self, tmp_path, name, text):
        """One titration has no other replicate to compare with, so a dropped cell would go unnoticed."""
        from core.data_processing.measurement_set import InvalidData
        from core.io import load_measurements

        path = tmp_path / name
        path.write_text(text)
        with pytest.raises(InvalidData) as excinfo:
            MeasurementSet.from_dataframe(load_measurements(path), source_file=str(path))
        message = str(excinfo.value)
        assert '2 µM' in message and 'point 3 of 5' in message
        assert name in message

    def test_rows_with_neither_number_are_not_measurements(self, tmp_path):
        """A trailing empty row is skipped; only a half-filled row is a titration point."""
        from core.io import load_measurements

        path = tmp_path / 'trailing.csv'
        path.write_text('concentration,signal\n0,10\n1e-6,12\n2e-6,14\n3e-6,15\n,\n')
        ms = MeasurementSet.from_dataframe(load_measurements(path), source_file=str(path))
        assert ms.signals.shape == (1, 4)

    def test_set_concentrations_refuses_a_negative_value_and_keeps_the_grid(self):
        from core.data_processing.measurement_set import InvalidData

        ms = _sample_measurement_set(n_replicas=2, n_points=4)
        before = ms.concentrations.copy()
        with pytest.raises(InvalidData, match='point 2 of 4 .*-3 µM'):
            ms.set_concentrations(Q_(np.array([1.0, -3.0, 5.0, 7.0]), 'µM'))
        np.testing.assert_array_equal(ms.concentrations, before)

    def test_replicates_loaded_from_several_files_name_every_file(self):
        from core.data_processing.measurement_set import InvalidData

        signals = np.ones((2, 6))
        signals[1, 0] = np.inf
        with pytest.raises(InvalidData, match="Replicate 'run_b' in run_a.csv, run_b.csv has an infinite signal"):
            MeasurementSet(
                concentrations=_grid(),
                signals=signals,
                replica_ids=('run_a', 'run_b'),
                metadata={'source_file': 'x/run_a.csv', 'source_files': ['x/run_a.csv', 'x/run_b.csv']},
            )
