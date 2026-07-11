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


def _txt(path, concs: list[float], signals: list[float], *, unit: str | None = None) -> str:
    """Minimal TXT measurement file, optionally self-describing its unit via a
    ``# units: concentration=<unit>`` header (values are face values in that unit)."""
    header = f'# units: concentration={unit}\n' if unit else ''
    rows = '\n'.join(f'{c}\t{s}' for c, s in zip(concs, signals))
    path.write_text(header + 'var\tsignal\n' + rows + '\n')
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


def test_heterogeneous_declared_units_converted_before_stack(tmp_path):
    """A µM-declared file and an M-declared file describing the SAME physical grid
    stack correctly: each is converted to molar via its own declared unit before
    the concat drops per-file attrs (H2 — no silent 1e6 error on a mixed batch)."""
    a = _txt(tmp_path / 'a.txt', [1.0, 2.0, 5.0], [10, 20, 30], unit='uM')  # µM face values
    b = _txt(tmp_path / 'b.txt', [1e-6, 2e-6, 5e-6], [11, 21, 31], unit='M')  # M face values

    ms = MeasurementSet.from_dataframe(load_measurements_multi([a, b]))

    assert ms.n_replicas == 2
    # Both replicas describe the one molar grid; the µM file was NOT read as M.
    np.testing.assert_allclose(ms.concentrations, [1e-6, 2e-6, 5e-6])


def test_mismatched_grid_rejected(tmp_path):
    """Files with different concentration grids must fail fast at build time."""
    a = _write(tmp_path / 'a.csv', [0.0, 1.0, 2.0], [1.0, 2.0, 3.0])
    b = _write(tmp_path / 'b.csv', [0.0, 1.0, 3.0], [1.0, 2.0, 3.0])  # last point differs
    combined = load_measurements_multi([a, b])
    with pytest.raises(ValueError, match='different concentration grid'):
        MeasurementSet.from_dataframe(combined)


def test_mismatched_point_counts_rejected(tmp_path):
    """Different numbers of titration points are rejected with a plain-language,
    file-named message — not a raw numpy broadcast error (issue: batch import)."""
    a = _write(tmp_path / 'run_a.csv', [0.0, 1.0, 2.0], [10.0, 20.0, 30.0])  # 3 points
    b = _write(tmp_path / 'run_b.csv', [0.0, 1.0, 2.0, 3.0], [10.0, 20.0, 30.0, 40.0])  # 4 points
    with pytest.raises(ValueError) as excinfo:
        load_measurements_multi([a, b])
    msg = str(excinfo.value)
    assert 'titration points' in msg
    assert 'run_a.csv' in msg and 'run_b.csv' in msg
    assert '3' in msg and '4' in msg
    assert 'broadcast' not in msg  # the cryptic numpy error must not leak through


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
