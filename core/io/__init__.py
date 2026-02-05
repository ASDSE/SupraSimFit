"""Minimal I/O module for measurement data and fit results.

Public API
----------
load_measurements(path) -> pd.DataFrame
    Load measurement data from file. Returns long-format DataFrame
    with columns: concentration, signal, replica.

save_results(results, path) -> None
    Save fit results dict to file.

Supported formats: .txt (tab-separated, multi-replica)
"""

from pathlib import Path

import pandas as pd

# Auto-register built-in formats
from core.io.formats import txt  # noqa: F401
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


__all__ = ['load_measurements', 'save_results']
