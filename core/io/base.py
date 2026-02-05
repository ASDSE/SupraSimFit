"""Protocol definitions for I/O readers and writers.

This module defines the interfaces that format-specific implementations
must follow. Using Protocol (structural subtyping) allows duck-typing
without requiring explicit inheritance.
"""

from pathlib import Path
from typing import Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class MeasurementReader(Protocol):
    """Protocol for reading measurement data files.

    Implementations must define:
    - extensions: tuple of supported file extensions (e.g., ('.txt',))
    - read(path) -> pd.DataFrame
    """

    extensions: tuple[str, ...]

    def read(self, path: Path) -> pd.DataFrame:
        """Read measurement data from file.

        Parameters
        ----------
        path : Path
            Path to input file.

        Returns
        -------
        pd.DataFrame
            Long-format DataFrame with columns:
            - concentration: titrant concentration (M)
            - signal: measured signal value
            - replica: replica index (0, 1, 2, ...)
        """
        ...


@runtime_checkable
class ResultWriter(Protocol):
    """Protocol for writing fit results.

    Implementations must define:
    - extensions: tuple of supported file extensions (e.g., ('.txt',))
    - write(results, path) -> None
    """

    extensions: tuple[str, ...]

    def write(self, results: dict, path: Path) -> None:
        """Write fit results to file.

        Parameters
        ----------
        results : dict
            Fit results dictionary.
        path : Path
            Output file path.
        """
        ...


__all__ = ['MeasurementReader', 'ResultWriter']
