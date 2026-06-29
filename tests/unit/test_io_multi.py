"""Tests for batch-loading several files as replicas (``load_measurements_multi``).

Covers the data-integrity round-trip (N files → N replica rows, each preserved),
the fail-fast contract on a genuine concentration-grid mismatch, provenance
labelling (replica IDs from file stems, duplicates disambiguated), and the
refusal of multi-channel files. See issue #35.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import core.io as io
from core.data_processing.measurement_set import MeasurementSet
from core.io import load_measurements_multi
from core.io.formats.bmg_reader import BMG_PLACEHOLDER_KEY


def _jasco(concs_umol: list[float], signals: list[float]) -> str:
    """Minimal JASCO-shaped CSV: concentrations in µmol/L, given signals."""
    rows = '\n'.join(f'{c:.4f},{s:.4f}' for c, s in zip(concs_umol, signals))
    return (
        'TITLE,t\n'
        'DATA TYPE,FLUORESCENCE SPECTRUM\n'
        'ORIGIN,JASCO\n'
        'XUNITS,Concentration [umol/L]\n'
        'YUNITS,INTENSITY\n'
        f'NPOINTS,{len(concs_umol)}\n'
        'XYDATA\n' + rows + '\n'
    )


def _write(path, concs_umol: list[float], signals: list[float]) -> str:
    path.write_text(_jasco(concs_umol, signals))
    return str(path)


def test_three_files_stack_as_replicas(tmp_path):
    """Three same-grid JASCO files load as three replicas, each round-tripped."""
    concs = [0.0, 1.0, 2.0]  # µmol/L → 0, 1e-6, 2e-6 M
    files = {
        'repA': [10.0, 20.0, 30.0],
        'repB': [11.0, 21.0, 31.0],
        'repC': [12.0, 22.0, 32.0],
    }
    paths = [_write(tmp_path / f'{stem}.csv', concs, sig) for stem, sig in files.items()]

    ms = MeasurementSet.from_dataframe(load_measurements_multi(paths))

    assert ms.n_replicas == 3
    assert set(ms.replica_ids) == set(files)
    np.testing.assert_allclose(ms.concentrations, [0.0, 1e-6, 2e-6])
    # Each replica row preserves its own file's signals (data integrity).
    for stem, sig in files.items():
        np.testing.assert_allclose(ms.get_replica_signal(stem), sig)


def test_mismatched_grid_rejected(tmp_path):
    """Files with different concentration grids must fail fast at build time."""
    a = _write(tmp_path / 'a.csv', [0.0, 1.0, 2.0], [1.0, 2.0, 3.0])
    b = _write(tmp_path / 'b.csv', [0.0, 1.0, 3.0], [1.0, 2.0, 3.0])  # last point differs
    combined = load_measurements_multi([a, b])
    with pytest.raises(ValueError, match='different concentration grid'):
        MeasurementSet.from_dataframe(combined)


def test_duplicate_stems_disambiguated(tmp_path):
    """Same file name in different folders → distinct replica IDs, no collision."""
    (tmp_path / 'one').mkdir()
    (tmp_path / 'two').mkdir()
    p1 = _write(tmp_path / 'one' / 'rep.csv', [0.0, 1.0], [1.0, 2.0])
    p2 = _write(tmp_path / 'two' / 'rep.csv', [0.0, 1.0], [3.0, 4.0])

    ms = MeasurementSet.from_dataframe(load_measurements_multi([p1, p2]))
    assert ms.n_replicas == 2
    assert set(ms.replica_ids) == {'rep', 'rep (2)'}


def test_empty_paths_raises():
    with pytest.raises(ValueError, match='No files'):
        load_measurements_multi([])


def test_channel_file_rejected(tmp_path, monkeypatch):
    """A file that parses to a multi-channel frame is refused (single-curve only)."""
    channel_df = pd.DataFrame(
        {
            'concentration': [0.0, 1e-6],
            'signal': [1.0, 2.0],
            'replica': [0, 0],
            'channel': ['A', 'A'],
        }
    )
    monkeypatch.setattr(io, 'load_measurements', lambda _p: channel_df)
    with pytest.raises(ValueError, match='channel'):
        load_measurements_multi([tmp_path / 'x.csv'])


def test_placeholder_concentration_file_rejected(tmp_path, monkeypatch):
    """A file with placeholder concentrations is refused — never fit silently."""
    placeholder_df = pd.DataFrame({'concentration': [1.0, 2.0], 'signal': [1.0, 2.0], 'replica': [0, 0]})
    placeholder_df.attrs[BMG_PLACEHOLDER_KEY] = True
    monkeypatch.setattr(io, 'load_measurements', lambda _p: placeholder_df)
    with pytest.raises(ValueError, match='placeholder concentrations'):
        load_measurements_multi([tmp_path / 'plate.xlsx'])
