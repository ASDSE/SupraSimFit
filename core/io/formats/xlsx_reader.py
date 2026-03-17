"""Excel (.xlsx/.xls) format reader for measurement data.

Sheet conventions
-----------------
**Multi-sheet** (preferred): each sheet is one replica.
The sheet name becomes the replica ID.  Each sheet must have columns
``concentration`` and ``signal`` (case-insensitive, same aliases as
:mod:`csv_reader`).

**Single-sheet with replica column**: a ``replica`` column selects the
sub-groups, identical to the CSV long-format.

**Single-sheet wide-format**: concentration in the first column,
remaining columns are replicas (like CSV wide-format).

Dependencies: ``openpyxl`` (already required by ``FittingApp.spec``).
"""

from pathlib import Path

import pandas as pd

from core.io.registry import register_reader

_CONC_NAMES = {"concentration", "conc", "x", "[conc]", "titrant"}
_SIGNAL_NAMES = {"signal", "y", "fluorescence", "intensity", "emission"}


class XlsxReader:
    """Reader for Excel measurement files."""

    extensions = (".xlsx", ".xls")

    def read(self, path: Path) -> pd.DataFrame:
        """Read an Excel measurement file.

        Parameters
        ----------
        path : Path
            Path to the ``.xlsx`` or ``.xls`` file.

        Returns
        -------
        pd.DataFrame
            Long-format DataFrame with columns:
            ``concentration``, ``signal``, ``replica``.

        Raises
        ------
        ValueError
            If columns cannot be identified or no data is found.
        """
        xl = pd.ExcelFile(path, engine="openpyxl")
        sheet_names = xl.sheet_names

        if len(sheet_names) > 1:
            return self._parse_multi_sheet(xl, sheet_names)

        # Single sheet — delegate to column-based detection
        df = xl.parse(sheet_names[0])
        return self._parse_single_sheet(df, path)

    # ------------------------------------------------------------------

    def _parse_multi_sheet(self, xl: pd.ExcelFile, sheets: list[str]) -> pd.DataFrame:
        frames = []
        for i, name in enumerate(sheets):
            df = xl.parse(name)
            cols_lower = {c.lower(): c for c in df.columns}
            conc_col = self._find_col(cols_lower, _CONC_NAMES)
            signal_col = self._find_col(cols_lower, _SIGNAL_NAMES)
            if not conc_col or not signal_col:
                continue
            frame = pd.DataFrame(
                {
                    "concentration": pd.to_numeric(df[conc_col], errors="coerce"),
                    "signal": pd.to_numeric(df[signal_col], errors="coerce"),
                    "replica": i,
                }
            )
            frames.append(frame.dropna(subset=["concentration", "signal"]))
        if not frames:
            raise ValueError("No readable replica sheets found in Excel file.")
        return pd.concat(frames, ignore_index=True)

    def _parse_single_sheet(self, df: pd.DataFrame, path: Path) -> pd.DataFrame:
        cols_lower = {c.lower(): c for c in df.columns}
        conc_col = self._find_col(cols_lower, _CONC_NAMES)
        signal_col = self._find_col(cols_lower, _SIGNAL_NAMES)

        if conc_col and signal_col:
            replica_col = cols_lower.get("replica")
            result = pd.DataFrame(
                {
                    "concentration": pd.to_numeric(df[conc_col], errors="coerce"),
                    "signal": pd.to_numeric(df[signal_col], errors="coerce"),
                    "replica": df[replica_col].astype(int) if replica_col else 0,
                }
            )
            return result.dropna(subset=["concentration", "signal"]).reset_index(drop=True)

        if conc_col and len(df.columns) >= 2:
            return self._parse_wide(df, conc_col)

        raise ValueError(
            f"Cannot identify concentration/signal columns in {path}. "
            f"Found: {list(df.columns)}"
        )

    def _parse_wide(self, df: pd.DataFrame, conc_col: str) -> pd.DataFrame:
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

    def _find_col(self, cols_lower: dict, names: set) -> str | None:
        for name in names:
            if name in cols_lower:
                return cols_lower[name]
        return None


# Register on import
register_reader(XlsxReader)
