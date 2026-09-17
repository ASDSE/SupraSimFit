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

Every value is written as the shortest decimal that reads back as the same
float64 (:func:`repr`), so an exported file carries the measured values
exactly: it loads with the same :meth:`MeasurementSet.fingerprint`, and a fit
result made on the original data is accepted on the export.
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
    # Self-describing unit declaration: MeasurementSet always stores M / au, so
    # the file is unambiguous and TxtReader can convert if a future writer emits
    # a non-M unit here.
    lines.append('# units: concentration=M, signal=au')
    lines.append(f'# Replicas: {ms.n_replicas}  Points: {ms.n_points}')
    return lines


def _iter_points(ms: 'MeasurementSet') -> Iterator[Tuple[int, float, float]]:
    """Yield ``(replica_idx, concentration, signal)`` tuples for every point.

    Includes dropped replicas: raw-data export is a faithful copy of what
    was loaded; outlier filtering only applies at fit time.
    """
    for replica_idx, (_rid, signal) in enumerate(ms.iter_replicas(active_only=False)):
        for conc, value in zip(ms.concentrations, signal):
            yield replica_idx, float(conc), float(value)


def write_measurements_txt(ms: 'MeasurementSet', path: str | Path) -> None:
    """Write *ms* to a tab-separated ``.txt`` file with repeated headers.

    Every value round-trips through :class:`TxtReader` as the same float64.
    """
    path = Path(path)
    lines: list[str] = _header_comment(ms)
    current_replica = -1
    for replica_idx, conc, value in _iter_points(ms):
        if replica_idx != current_replica:
            lines.append('var\tsignal')
            current_replica = replica_idx
        lines.append(f'{conc!r}\t{value!r}')
    path.write_text('\n'.join(lines) + '\n')


def write_measurements_csv(ms: 'MeasurementSet', path: str | Path) -> None:
    """Write *ms* to a long-format ``.csv`` file.

    Every value round-trips through :class:`CsvReader` as the same float64.
    No ``#``-style comments are emitted because ``CsvReader`` relies on
    :func:`pandas.read_csv` without a comment character.
    """
    path = Path(path)
    lines: list[str] = ['concentration,signal,replica']
    lines.extend(f'{conc!r},{value!r},{replica_idx}' for replica_idx, conc, value in _iter_points(ms))
    path.write_text('\n'.join(lines) + '\n')
