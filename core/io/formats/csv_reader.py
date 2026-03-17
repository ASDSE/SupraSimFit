"""CSV format reader for comma-separated measurement data.

Supported formats
-----------------
1. **Long-format** (preferred): columns ``concentration``, ``signal``,
   and optionally ``replica``::

       concentration,signal,replica
       1e-7,506.246,0
       2e-7,612.3,0
       1e-7,503.1,1
       ...

2. **Wide-format** (auto-detected): each column after the first is one
   replica, first column is concentration::

       concentration,rep0,rep1,rep2
       1e-7,506.246,503.1,508.2
       2e-7,612.3,610.0,614.5
       ...

3. **Repeated-header** (like the TXT format): multiple blocks separated
   by repeated header rows — handled by falling back to the TXT-style
   block parser.

Column detection is case-insensitive; accepted names for concentration:
``concentration``, ``conc``, ``x``, ``[conc]``, ``titrant``.
Accepted names for signal: ``signal``, ``y``, ``fluorescence``,
``intensity``, ``emission``.
"""

from pathlib import Path

import pandas as pd

from core.io.registry import register_reader

_CONC_NAMES = {"concentration", "conc", "x", "[conc]", "titrant"}
_SIGNAL_NAMES = {"signal", "y", "fluorescence", "intensity", "emission"}


class CsvReader:
    """Reader for CSV measurement files."""

    extensions = (".csv",)

    def read(self, path: Path) -> pd.DataFrame:
        """Read a CSV measurement file.

        Parameters
        ----------
        path : Path
            Path to input CSV file.

        Returns
        -------
        pd.DataFrame
            Long-format DataFrame with columns:
            ``concentration``, ``signal``, ``replica``.

        Raises
        ------
        ValueError
            If the file cannot be parsed or required columns are missing.
        """
        df = pd.read_csv(path)
        cols_lower = {c.lower(): c for c in df.columns}

        conc_col = self._find_col(cols_lower, _CONC_NAMES)
        signal_col = self._find_col(cols_lower, _SIGNAL_NAMES)

        if conc_col and signal_col:
            # Long-format (with optional replica column)
            replica_col = cols_lower.get("replica")
            result = pd.DataFrame(
                {
                    "concentration": pd.to_numeric(df[conc_col], errors="coerce"),
                    "signal": pd.to_numeric(df[signal_col], errors="coerce"),
                    "replica": (
                        df[replica_col].astype(int)
                        if replica_col
                        else 0
                    ),
                }
            )
            return result.dropna(subset=["concentration", "signal"]).reset_index(drop=True)

        if conc_col and len(df.columns) >= 2:
            # Wide-format: first detected col = concentration, rest = replicas
            return self._parse_wide(df, conc_col)

        raise ValueError(
            f"Cannot identify concentration/signal columns in {path}. "
            f"Found columns: {list(df.columns)}"
        )

    # ------------------------------------------------------------------
    def _find_col(self, cols_lower: dict, names: set) -> str | None:
        for name in names:
            if name in cols_lower:
                return cols_lower[name]
        return None

    def _parse_wide(self, df: pd.DataFrame, conc_col: str) -> pd.DataFrame:
        """Convert wide-format (one column per replica) to long-format."""
        replica_cols = [c for c in df.columns if c != conc_col]
        frames = []
        for i, col in enumerate(replica_cols):
            frame = pd.DataFrame(
                {
                    "concentration": pd.to_numeric(df[conc_col], errors="coerce"),
                    "signal": pd.to_numeric(df[col], errors="coerce"),
                    "replica": i,
                }
            )
            frames.append(frame)
        result = pd.concat(frames, ignore_index=True)
        return result.dropna(subset=["concentration", "signal"]).reset_index(drop=True)


# Register on import
register_reader(CsvReader)
