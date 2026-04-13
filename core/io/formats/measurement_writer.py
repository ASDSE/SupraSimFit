"""Writers that serialise a :class:`MeasurementSet` back to disk.

These produce files that round-trip cleanly through the existing
:class:`TxtReader` and :class:`CsvReader`:

* TXT: tab-separated repeated-header blocks (one block per replica),
  matching ``core/io/formats/txt.py``.
* CSV: long-format with ``concentration,signal,replica`` columns,
  matching ``core/io/formats/csv_reader.py``.

Both writers operate on *all* replicas — active and dropped — so the
export is a faithful copy of the raw data; outlier filtering is
applied only at fit time.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Iterator, Tuple

if TYPE_CHECKING:
    from core.data_processing.measurement_set import MeasurementSet


def _header_comment(ms: 'MeasurementSet') -> list[str]:
    lines = [
        f'# Raw measurement data exported from fitting_app on {datetime.now().isoformat(timespec="seconds")}',
    ]
    source = ms.metadata.get('source_file') if ms.metadata else None
    if source:
        lines.append(f'# Source: {source}')
    lines.append(f'# Replicas: {ms.n_replicas}  Points: {ms.n_points}')
    return lines


def _iter_points(ms: 'MeasurementSet') -> Iterator[Tuple[int, float, float]]:
    """Yield ``(replica_idx, concentration, signal)`` tuples for every point.

    Includes dropped replicas: raw-data export is a faithful copy of what
    was loaded; outlier filtering only applies at fit time.
    """
    for replica_idx, (_rid, signal) in enumerate(ms.iter_replicas(active_only=False)):
        for conc, value in zip(ms.concentrations, signal):
            yield replica_idx, conc, value


def write_measurements_txt(ms: 'MeasurementSet', path: str | Path) -> None:
    """Write *ms* to a tab-separated ``.txt`` file with repeated headers.

    Output round-trips exactly through :class:`TxtReader`.
    """
    path = Path(path)
    lines: list[str] = _header_comment(ms)
    current_replica = -1
    for replica_idx, conc, value in _iter_points(ms):
        if replica_idx != current_replica:
            lines.append('var\tsignal')
            current_replica = replica_idx
        lines.append(f'{conc:.6e}\t{value:.6e}')
    path.write_text('\n'.join(lines) + '\n')


def write_measurements_csv(ms: 'MeasurementSet', path: str | Path) -> None:
    """Write *ms* to a long-format ``.csv`` file.

    Output round-trips through :class:`CsvReader` as long-format CSV.
    No ``#``-style comments are emitted because ``CsvReader`` relies on
    :func:`pandas.read_csv` without a comment character.
    """
    path = Path(path)
    lines: list[str] = ['concentration,signal,replica']
    lines.extend(
        f'{conc:.6e},{value:.6e},{replica_idx}'
        for replica_idx, conc, value in _iter_points(ms)
    )
    path.write_text('\n'.join(lines) + '\n')
