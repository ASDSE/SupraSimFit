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

3. **European style**: ``;`` delimiter and ``,`` decimal separator are
   auto-detected.

4. **Arbitrary or missing headers**: if no recognized column names are
   found, the concentration column is inferred as the (leftmost)
   monotonic numeric column; remaining numeric columns are treated as
   signal (single → long-format, multiple → wide-format replicates).

Name-based fast path tokens: ``concentration``, ``conc``, ``titrant``,
``x`` (concentration); ``signal``, ``intensity``, ``int``,
``fluorescence``, ``emission``, ``y`` (signal). Match is token
start-with on alphanumeric word tokens.
"""

import re
from pathlib import Path

import pandas as pd

from core.io.registry import register_reader

_CONC_TOKENS = ("conc", "titrant", "x")
_SIGNAL_TOKENS = ("signal", "int", "fluorescence", "emission", "y")

_PARSE_OPTIONS = (
    {},
    {"sep": ";", "decimal": ","},
    {"sep": ";"},
    {"sep": "\t"},
)


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
            If the file cannot be parsed or columns cannot be identified.
        """
        df, kwargs = self._parse(path)

        if self._header_is_numeric(df):
            df = pd.read_csv(path, header=None, **kwargs)

        conc_col, signal_cols, replica_col = self._identify_columns(df)

        if conc_col is None or not signal_cols:
            raise ValueError(
                f"Cannot identify concentration/signal columns in {path}. "
                f"Found columns: {list(df.columns)}"
            )

        if len(signal_cols) == 1:
            return self._long_format(df, conc_col, signal_cols[0], replica_col)
        return self._wide_format(df, conc_col, signal_cols)

    # ------------------------------------------------------------------
    # Parsing: try delimiter/decimal combos, pick first that yields
    # ≥ 2 numeric-convertible columns.
    # ------------------------------------------------------------------
    def _parse(self, path: Path) -> tuple[pd.DataFrame, dict]:
        last_df, last_kwargs = None, {}
        for kwargs in _PARSE_OPTIONS:
            try:
                df = pd.read_csv(path, **kwargs)
            except Exception:
                continue
            if len(self._numeric_columns(df)) >= 2:
                return df, kwargs
            last_df, last_kwargs = df, kwargs
        if last_df is None:
            raise ValueError(f"Cannot parse {path}: all delimiter/decimal combos failed")
        return last_df, last_kwargs

    @staticmethod
    def _numeric_columns(df: pd.DataFrame) -> list:
        return [
            c for c in df.columns
            if pd.to_numeric(df[c], errors="coerce").notna().mean() >= 0.8
        ]

    @staticmethod
    def _header_is_numeric(df: pd.DataFrame) -> bool:
        """True if every column name parses as a number (suggesting no header row)."""
        for c in df.columns:
            s = str(c).replace(",", ".").strip()
            try:
                float(s)
            except ValueError:
                return False
        return True

    # ------------------------------------------------------------------
    # Column identification: name-based fast path, then content-based
    # fallback (monotonic = concentration).
    # ------------------------------------------------------------------
    @staticmethod
    def _tokenize(name) -> list[str]:
        return re.findall(r"[a-z]+", str(name).lower())

    def _find_named(self, columns, tokens) -> str | None:
        for c in columns:
            for col_tok in self._tokenize(c):
                for tok in tokens:
                    if col_tok.startswith(tok):
                        return c
        return None

    @staticmethod
    def _is_monotonic(series: pd.Series) -> bool:
        s = pd.to_numeric(series, errors="coerce").dropna()
        if len(s) < 3:
            return False
        diffs = s.diff().dropna()
        return bool((diffs >= 0).all() or (diffs <= 0).all())

    def _identify_columns(self, df: pd.DataFrame):
        cols = list(df.columns)
        numeric = self._numeric_columns(df)

        replica_col = None
        for c in cols:
            if "replica" in self._tokenize(c):
                replica_col = c
                break

        signal_candidates = [c for c in numeric if c != replica_col]
        conc_col = self._find_named(signal_candidates, _CONC_TOKENS)
        signal_col = self._find_named(
            [c for c in signal_candidates if c != conc_col], _SIGNAL_TOKENS
        )

        if conc_col and signal_col:
            other_signals = [c for c in signal_candidates if c != conc_col]
            return conc_col, other_signals, replica_col

        if conc_col is None:
            monotonic = [c for c in signal_candidates if self._is_monotonic(df[c])]
            if not monotonic:
                return None, [], replica_col
            conc_col = monotonic[0]

        remaining = [c for c in signal_candidates if c != conc_col]
        return conc_col, remaining, replica_col

    # ------------------------------------------------------------------
    @staticmethod
    def _long_format(df, conc_col, signal_col, replica_col) -> pd.DataFrame:
        result = pd.DataFrame(
            {
                "concentration": pd.to_numeric(df[conc_col], errors="coerce"),
                "signal": pd.to_numeric(df[signal_col], errors="coerce"),
                "replica": (
                    df[replica_col].astype(int) if replica_col is not None else 0
                ),
            }
        )
        return result.dropna(subset=["concentration", "signal"]).reset_index(drop=True)

    @staticmethod
    def _wide_format(df, conc_col, signal_cols) -> pd.DataFrame:
        frames = []
        for i, col in enumerate(signal_cols):
            frames.append(
                pd.DataFrame(
                    {
                        "concentration": pd.to_numeric(df[conc_col], errors="coerce"),
                        "signal": pd.to_numeric(df[col], errors="coerce"),
                        "replica": i,
                    }
                )
            )
        result = pd.concat(frames, ignore_index=True)
        return result.dropna(subset=["concentration", "signal"]).reset_index(drop=True)


register_reader(CsvReader)
