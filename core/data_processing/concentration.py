"""Helpers for saving, loading, and extracting concentration vectors.

Concentration vectors are reusable across sessions.  The JSON format is:

    {"concentrations": [1e-7, 2e-7, 5e-7], "unit": "M", "label": "GDA standard"}

These helpers have no Qt dependency and can be used from tests or scripts.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from core.units import Q_


def save_concentration_vector(
    concentrations: np.ndarray,
    path: str | Path,
    *,
    unit: str = 'M',
    label: str = '',
) -> None:
    """Save a concentration vector to a JSON file.

    Parameters
    ----------
    concentrations : np.ndarray
        1-D array of concentration values (in the given unit).
    path : str or Path
        Output file path.
    unit : str
        Unit string for display (default ``"M"``).
    label : str
        Optional human-readable description of the titration series.
    """
    path = Path(path)
    data = {
        'concentrations': concentrations.tolist(),
        'unit': unit,
        'label': label,
    }
    path.write_text(json.dumps(data, indent=2))


def load_concentration_vector(path: str | Path) -> tuple[np.ndarray, str, str]:
    """Load a concentration vector from a JSON file.

    Parameters
    ----------
    path : str or Path
        Path to the JSON file written by :func:`save_concentration_vector`.

    Returns
    -------
    tuple[np.ndarray, str, str]
        ``(concentrations, unit, label)`` where *unit* and *label* may be
        empty strings if absent from the file.

    Raises
    ------
    ValueError
        If the file does not contain a ``"concentrations"`` key or the value
        is not a non-empty list of numbers.
    """
    path = Path(path)
    data = json.loads(path.read_text())
    if 'concentrations' not in data:
        raise ValueError(f"'concentrations' key missing from {path}")
    raw = data['concentrations']
    if not isinstance(raw, list) or len(raw) == 0:
        raise ValueError(f"'concentrations' must be a non-empty list in {path}")
    unit = data.get('unit', 'M')
    label = data.get('label', '')
    # Convert to M using pint so values saved in non-M units are correct
    concentrations = Q_(np.asarray(raw, dtype=float), unit).to('M').magnitude
    return concentrations, unit, label


def read_raw_concentrations(path: str | Path) -> tuple[np.ndarray, str | None]:
    """Read a concentration vector as face-value numbers plus a declared unit.

    Dispatches by file extension:

    - ``.json`` — reads via :func:`load_concentration_vector`-style schema and
      returns ``(raw_values, declared_unit)``. **Unlike**
      :func:`load_concentration_vector`, the values are *not* converted to
      molar; the caller is responsible for the conversion via Pint.
    - Anything else — delegates to :func:`extract_concentrations_from_file`
      and returns ``(values, None)`` (no unit declaration is available in
      raw measurement files).

    Parameters
    ----------
    path : str or Path
        File path.

    Returns
    -------
    tuple[np.ndarray, str | None]
        ``(face_values, declared_unit)``. ``declared_unit`` is ``None`` when
        the source file format does not carry unit metadata.
    """
    path = Path(path)
    if path.suffix.lower() == '.json':
        data = json.loads(path.read_text())
        if 'concentrations' not in data:
            raise ValueError(f"'concentrations' key missing from {path}")
        raw = data['concentrations']
        if not isinstance(raw, list) or len(raw) == 0:
            raise ValueError(f"'concentrations' must be a non-empty list in {path}")
        return np.asarray(raw, dtype=float), data.get('unit')
    return extract_concentrations_from_file(path), None


def extract_concentrations_from_file(path: str | Path) -> np.ndarray:
    """Load a data file via the I/O registry and extract its concentration column.

    This imports the reader lazily so that the core module has no hard
    dependency on the full I/O stack at import time.

    Parameters
    ----------
    path : str or Path
        Path to a measurement file (any format with a registered reader).

    Returns
    -------
    np.ndarray
        Unique, sorted concentration values found in the file.
    """
    from core.io import load_measurements  # lazy import

    path = Path(path)
    df = load_measurements(path)
    return np.sort(df['concentration'].unique()).astype(float)
