"""Helpers for saving, loading, and extracting concentration vectors.

Concentration vectors are reusable across sessions.  The JSON format is:

    {"concentrations": [1e-7, 2e-7, 5e-7], "unit": "M", "label": "GDA standard"}

These helpers have no Qt dependency and can be used from tests or scripts.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from core.units import Q_, Quantity


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


def read_raw_concentrations(path: str | Path) -> Quantity:
    """Read a concentration vector as a self-describing ``pint.Quantity``.

    Dispatches by file extension:

    - ``.json`` — reads the ``{"concentrations": [...], "unit": ...}`` schema
      and wraps the values in their declared unit (default ``M``). The values
      are returned *at face value* in that unit (not pre-converted), so a caller
      can both display them in the declared unit and convert with ``.to('M')``.
    - Anything else — delegates to :func:`extract_concentrations_from_file`,
      which wraps the file's concentration grid in its reader-declared unit
      (e.g. the TXT ``# units:`` header), falling back to ``M`` only when the
      reader declares none.

    Returning a ``Quantity`` keeps magnitude and unit together, so no bare-float
    vector with a separately-remembered unit token can drift apart.

    Parameters
    ----------
    path : str or Path
        File path.

    Returns
    -------
    pint.Quantity
        Concentration vector carrying its unit.
    """
    path = Path(path)
    if path.suffix.lower() == '.json':
        data = json.loads(path.read_text())
        if 'concentrations' not in data:
            raise ValueError(f"'concentrations' key missing from {path}")
        raw = data['concentrations']
        if not isinstance(raw, list) or len(raw) == 0:
            raise ValueError(f"'concentrations' must be a non-empty list in {path}")
        return Q_(np.asarray(raw, dtype=float), data.get('unit', 'M'))
    return extract_concentrations_from_file(path)


def extract_concentrations_from_file(path: str | Path) -> Quantity:
    """Load a data file via the I/O registry and extract its concentration grid.

    This imports the reader lazily so that the core module has no hard
    dependency on the full I/O stack at import time.

    Returns a self-describing ``Quantity``: the unique, sorted concentration
    values wrapped in the reader-declared unit (``df.attrs['concentration_unit']``,
    e.g. the TXT ``# units:`` header), or ``M`` when the reader declares none.
    Honouring the declared unit here is what stops a µM file from being read as
    molar — a silent 1e6 error — by a caller that only ``.to('M')`` the result.

    Parameters
    ----------
    path : str or Path
        Path to a measurement file (any format with a registered reader).

    Returns
    -------
    pint.Quantity
        Unique, sorted concentrations in their reader-declared unit.
    """
    from core.io import load_measurements  # lazy import

    path = Path(path)
    df = load_measurements(path)
    unit = df.attrs.get('concentration_unit', 'M')
    values = np.sort(df['concentration'].unique()).astype(float)
    return Q_(values, unit)
