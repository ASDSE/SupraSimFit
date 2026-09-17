"""Export Raw Data is an exact copy of the measured values.

:meth:`MeasurementSet.fingerprint` hashes the concentration and signal bytes,
and an imported fit result is accepted only on data carrying the fingerprint it
was made on. An exported file must therefore read back as the same float64,
down to the last digit, or the app refuses the user's own results on the data
it has just written for them.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.data_processing.measurement_set import MeasurementSet
from core.io import load_measurements
from core.io.formats.measurement_writer import write_measurements_csv, write_measurements_txt

_WRITERS = {'txt': write_measurements_txt, 'csv': write_measurements_csv}

_DATA_DIR = Path(__file__).resolve().parents[2] / 'data'

#: A titration whose concentrations need 17 significant digits, as plate-reader
#: exports of a serial dilution routinely do (``data/GDA_system.txt`` carries
#: 5.9409999999999995e-05).
_LONG_DIGITS = (
    'var\tsignal\n'
    '0.0\t506.24600000000004\n'
    '5.9409999999999995e-05\t1914.7199999999998\n'
    '0.00011765\t3421.9899999999998\n'
    '0.00028571000000000002\t6475.1599999999999\n'
)


def _round_trip(ms: MeasurementSet, fmt: str, tmp_path: Path) -> MeasurementSet:
    path = tmp_path / f'export.{fmt}'
    _WRITERS[fmt](ms, path)
    return MeasurementSet.from_dataframe(load_measurements(path))


@pytest.mark.parametrize('fmt', list(_WRITERS))
def test_seventeen_digit_values_survive_export_and_reload(fmt, tmp_path):
    """Every measured value comes back as the same float64, so the data keep their fingerprint."""
    source = tmp_path / 'long_digits.txt'
    source.write_text(_LONG_DIGITS)
    ms = MeasurementSet.from_dataframe(load_measurements(source), source_file=str(source))
    assert repr(float(ms.concentrations[1])) == '5.9409999999999995e-05', 'the reader must keep the long value'

    reloaded = _round_trip(ms, fmt, tmp_path)

    np.testing.assert_array_equal(reloaded.concentrations, ms.concentrations)
    np.testing.assert_array_equal(reloaded.signals, ms.signals)
    assert reloaded.fingerprint() == ms.fingerprint()


@pytest.mark.parametrize('fmt', list(_WRITERS))
@pytest.mark.parametrize('name', ['GDA_system.txt', 'IDA_system.txt', 'DBA_system_host_to_dye.txt', 'Dye_alone.txt'])
def test_shipped_datasets_keep_their_fingerprint_through_an_export(name, fmt, tmp_path):
    """Results made on a shipped dataset stay importable after the user exports its raw data."""
    source = _DATA_DIR / name
    ms = MeasurementSet.from_dataframe(load_measurements(source), source_file=str(source))

    reloaded = _round_trip(ms, fmt, tmp_path)

    assert reloaded.fingerprint() == ms.fingerprint()
    assert reloaded.n_replicas == ms.n_replicas


def test_dropped_replicates_are_exported_too(tmp_path):
    """The export is the raw data: leaving a replicate out of the fit does not remove it from the file."""
    ms = MeasurementSet(
        concentrations=np.array([0.0, 1e-6, 2e-6]),
        signals=np.array([[1.0, 2.0, 3.0], [1.5, 2.5, 3.5]]),
        replica_ids=('a', 'b'),
    )
    ms.set_active('b', False)

    reloaded = _round_trip(ms, 'txt', tmp_path)

    assert reloaded.n_replicas == 2
    np.testing.assert_array_equal(reloaded.signals, ms.signals)
