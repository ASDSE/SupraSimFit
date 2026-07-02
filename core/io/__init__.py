"""Minimal I/O module for measurement data and fit results.

Public API
----------
load_measurements(path) -> pd.DataFrame
    Load measurement data from file. Returns long-format DataFrame
    with columns: concentration, signal, replica.

load_measurements_multi(paths) -> pd.DataFrame
    Load several files and stack them as replicas in one long-format
    DataFrame (replica labels derived from file stems).

save_results(results, path) -> None
    Save fit results dict to file.

Supported formats: .txt (tab-separated, multi-replica)
"""

from collections.abc import Sequence
from pathlib import Path

import pandas as pd

# Auto-register built-in formats. Register instrument-specific .csv sniffers
# *before* the generic csv_reader fallback so they get first claim on dispatch.
# Order is load-bearing — get_reader() walks readers in registration order — so
# isort must not alphabetise this block:
# isort: off
from core.io.formats import txt  # noqa: F401
from core.io.formats import jasco_reader  # noqa: F401
from core.io.formats import ensight_reader  # noqa: F401
from core.io.formats import csv_reader  # noqa: F401
from core.io.formats import xlsx_reader  # noqa: F401

# isort: on
from core.io.formats.bmg_reader import BMG_PLACEHOLDER_KEY
from core.io.formats.ensight_reader import ENSIGHT_CHANNEL_COLUMN
from core.io.registry import get_reader, get_writer


def load_measurements(path: str | Path) -> pd.DataFrame:
    """Load measurement data from file.

    Parameters
    ----------
    path : str or Path
        Path to measurement file.

    Returns
    -------
    pd.DataFrame
        Long-format DataFrame with columns:
        - concentration: titrant concentration (M)
        - signal: measured signal value
        - replica: replica index (0, 1, 2, ...)
    """
    path = Path(path)
    reader = get_reader(path)
    return reader.read(path)


def load_measurements_multi(paths: Sequence[str | Path]) -> pd.DataFrame:
    """Load several measurement files and stack them as replicas.

    Each file is read with :func:`load_measurements` and contributes its
    replica(s) to a combined long-format frame. Replica labels are made
    globally unique from the file stem, so the source of each replicate stays
    visible downstream. Files must share one concentration grid: a differing
    number of titration points is rejected here with a plain-language,
    file-named message, and any remaining value mismatch is caught by
    :meth:`MeasurementSet.from_dataframe`.

    Parameters
    ----------
    paths : sequence of str or Path
        Files to load. Each must be a single-curve file carrying its own
        concentrations; a file with multiple channels (e.g. an EnSight export)
        or placeholder concentrations (e.g. a plate export) is rejected —
        import those one at a time.

    Returns
    -------
    pd.DataFrame
        Long-format frame with columns ``concentration``, ``signal`` and
        ``replica`` (string labels derived from the file stems).

    Raises
    ------
    ValueError
        If *paths* is empty; a file carries a ``channel`` column or placeholder
        concentrations; or the files do not all have the same number of
        titration points.
    """
    if not paths:
        raise ValueError('No files provided')

    frames: list[pd.DataFrame] = []
    stem_counts: dict[str, int] = {}
    point_counts: list[tuple[str, int]] = []
    for raw in paths:
        path = Path(raw)
        df = load_measurements(path)
        if ENSIGHT_CHANNEL_COLUMN in df.columns:
            raise ValueError(
                f"'{path.name}' carries multiple channels; batch import handles "
                'single-curve files only. Import multi-channel files individually.'
            )
        if df.attrs.get(BMG_PLACEHOLDER_KEY):
            raise ValueError(
                f"'{path.name}' has placeholder concentrations (no real concentration "
                'column); batch replica import expects files that carry their own '
                'concentrations. Import it individually and enter concentrations.'
            )
        point_counts.append((path.name, len(df) // max(int(df['replica'].nunique()), 1)))

        # Provenance-carrying, globally unique replica label per file.
        seen = stem_counts.get(path.stem, 0)
        stem_counts[path.stem] = seen + 1
        label = path.stem if seen == 0 else f'{path.stem} ({seen + 1})'

        out = df[['concentration', 'signal']].copy()
        replicas = df['replica']
        if replicas.nunique() > 1:
            out['replica'] = label + '#' + replicas.astype(str)
        else:
            out['replica'] = label
        frames.append(out)

    # Replicate files must describe the same titration — i.e. share one
    # concentration grid. Catch a differing number of titration points here,
    # with a plain-language, file-named message, rather than letting the raw
    # array-shape mismatch surface from downstream numpy code.
    if len({n for _, n in point_counts}) > 1:
        listing = '\n'.join(f'• {name} — {n} points' for name, n in point_counts)
        raise ValueError(
            'These files have different numbers of titration points, so they '
            f'cannot be loaded as replicates of one measurement:\n\n{listing}\n\n'
            'Replicates must share the same titration points. Select files from '
            'the same measurement, or files with matching point counts.'
        )

    return pd.concat(frames, ignore_index=True)


def save_results(results: dict, path: str | Path) -> None:
    """Save fit results to file.

    Parameters
    ----------
    results : dict
        Fit results dictionary with parameter values, uncertainties, etc.
    path : str or Path
        Output file path.
    """
    path = Path(path)
    writer = get_writer(path)
    writer.write(results, path)


__all__ = ['load_measurements', 'load_measurements_multi', 'save_results']
