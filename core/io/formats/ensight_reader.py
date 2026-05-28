"""PerkinElmer EnSight plate-reader CSV export parser.

EnSight (Kaleido 3.x) exports in ``CSV_PLATE / Standard`` format hold
**one plate measured under multiple optical operations** in a single file.
Each operation produces a ``Result for <Name>`` block followed by a
plate-grid:

    Result for Time-resolved Fluorescence 1
    Barcode,Repeat,Loop no,...
    <one well-scan info row>
    (blank)
    ,1,2,3,...,12,                        ← plate-grid column header
    A,<v>,<v>,...,<v>,
    B,<v>,<v>,...,<v>,
    ...

Multiple operations on the same plate are different optical *channels*
(e.g. TRF @ 615 nm, prompt FL @ 424 nm) — not replicates. Plate rows
(A..H on a 96-well, A..P on a 384-well) are the replicates; plate
columns are titration points whose real concentrations live in the
pipetting protocol, not the file. Behaviour and convention follow
the existing BMG plate-reader path: placeholder concentrations
``1..N`` and ``BMG_PLACEHOLDER_KEY`` flag, so the existing GUI guards
and the user's editing flow stay reused.

Multi-channel files return a long-format DataFrame with an extra
``channel`` column; ``data_panel.load_file`` filters down to one channel
via a picker after the reader returns.
"""

from __future__ import annotations

import re
import string
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from core.io.formats.bmg_reader import BMG_PLACEHOLDER_KEY
from core.io.registry import register_reader

ENSIGHT_METADATA_KEY = "ensight_metadata"
ENSIGHT_CHANNEL_COLUMN = "channel"

_SIGNATURE = "EnSight Results from"
_RESULT_RE = re.compile(r"^Result for (.+?),*\s*$")
_GRID_HEADER_RE = re.compile(r"^,(?:\d+,)+\s*$")
_GRID_ROW_RE = re.compile(r"^([A-P]),")
_DETAILS_SECTION = "Details of Measurement Sequence"
_PLATE_INFO_SECTION = "Plate Type Information"


class EnsightReader:
    """Reader for PerkinElmer EnSight CSV_PLATE exports."""

    extensions = (".csv",)

    @classmethod
    def can_read(cls, path: Path) -> bool:
        """Return True if the first non-empty line is the EnSight signature."""
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                for _ in range(5):
                    line = f.readline()
                    if not line:
                        return False
                    stripped = line.strip().rstrip(",")
                    if stripped == _SIGNATURE:
                        return True
                    if stripped:
                        return False
        except OSError:
            return False
        return False

    def read(self, path: Path) -> pd.DataFrame:
        """Parse an EnSight CSV into a long-format DataFrame.

        Returned columns: ``concentration`` (placeholder 1..N),
        ``signal``, ``replica``, ``channel``. ``df.attrs`` carries
        ``BMG_PLACEHOLDER_KEY`` (reuses the existing fit guard) and
        ``ENSIGHT_METADATA_KEY`` with protocol, plate, and per-channel
        instrument parameters.
        """
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            lines = [line.rstrip("\r\n") for line in f]

        protocol = self._parse_top_header(lines)
        blocks = self._find_result_blocks(lines)
        if not blocks:
            raise ValueError(
                f"{path.name}: no 'Result for ...' blocks found — "
                "file does not look like an EnSight CSV export."
            )

        details = self._parse_key_value_section(lines, _DETAILS_SECTION)
        plate_info = self._parse_key_value_section(lines, _PLATE_INFO_SECTION)
        expected_dims = self._expected_plate_dims(plate_info)

        rows: List[Dict[str, Any]] = []
        for name, start in blocks:
            grid = self._parse_grid(lines, start, path, name, expected_dims)
            n_rows, n_cols = grid.shape
            for r in range(n_rows):
                for c in range(n_cols):
                    rows.append(
                        {
                            "concentration": float(c + 1),
                            "signal": float(grid[r, c]),
                            "replica": r,
                            ENSIGHT_CHANNEL_COLUMN: name,
                        }
                    )

        df = pd.DataFrame(rows).dropna(subset=["signal"]).reset_index(drop=True)
        df.attrs[BMG_PLACEHOLDER_KEY] = True
        df.attrs[ENSIGHT_METADATA_KEY] = {
            "protocol": protocol,
            "channels": {name: self._block_details(name, details) for name, _ in blocks},
            "plate": plate_info,
        }
        return df

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_top_header(lines: List[str]) -> Dict[str, str]:
        """Capture the few lines above the first 'Result for ...' block."""
        info: Dict[str, str] = {}
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.rstrip(",") == _SIGNATURE:
                continue
            if _RESULT_RE.match(stripped):
                break
            if "," in line:
                key, _, value = line.partition(",")
                key = key.strip()
                value = value.strip().rstrip(",").strip()
                if key:
                    info[key] = value
        return info

    @staticmethod
    def _find_result_blocks(lines: List[str]) -> List[Tuple[str, int]]:
        """Return list of (block name, line index) for every 'Result for' line."""
        out: List[Tuple[str, int]] = []
        for i, line in enumerate(lines):
            match = _RESULT_RE.match(line.strip())
            if match:
                out.append((match.group(1).strip(), i))
        return out

    @staticmethod
    def _parse_grid(
        lines: List[str],
        start: int,
        path: Path,
        name: str,
        expected_dims: Tuple[int | None, int | None],
    ) -> np.ndarray:
        """Locate and parse the plate grid that follows a 'Result for' line."""
        header_idx = None
        for j in range(start + 1, len(lines)):
            if _GRID_HEADER_RE.match(lines[j]):
                header_idx = j
                break
            # If we hit the next block before finding a grid, bail.
            if _RESULT_RE.match(lines[j].strip()):
                break
        if header_idx is None:
            raise ValueError(
                f"{path.name}: block 'Result for {name}' has no plate grid "
                "(expected a ',1,2,…,N,' header line)."
            )

        col_tokens = [
            tok for tok in lines[header_idx].split(",") if tok.strip() != ""
        ]
        try:
            col_numbers = [int(tok) for tok in col_tokens]
        except ValueError as exc:
            raise ValueError(
                f"{path.name}: block '{name}' grid header has non-integer "
                f"column labels: {col_tokens!r}"
            ) from exc
        if col_numbers != list(range(1, len(col_numbers) + 1)):
            raise ValueError(
                f"{path.name}: block '{name}' grid header is not sequential "
                f"1..N: {col_numbers}"
            )
        n_cols = len(col_numbers)

        grid: List[List[float]] = []
        expected_letters = string.ascii_uppercase  # A..Z is plenty
        for j in range(header_idx + 1, len(lines)):
            line = lines[j]
            match = _GRID_ROW_RE.match(line)
            if not match:
                break
            letter = match.group(1)
            expected = expected_letters[len(grid)]
            if letter != expected:
                raise ValueError(
                    f"{path.name}: block '{name}' row letter {letter!r} out of "
                    f"sequence (expected {expected!r})."
                )
            parts = line.split(",")[1 : 1 + n_cols]
            row_vals: List[float] = []
            for p in parts:
                stripped = p.strip()
                row_vals.append(float(stripped) if stripped else float("nan"))
            while len(row_vals) < n_cols:
                row_vals.append(float("nan"))
            grid.append(row_vals)

        if not grid:
            raise ValueError(
                f"{path.name}: block '{name}' grid header had no following data rows."
            )

        n_rows_expected, n_cols_expected = expected_dims
        # Plate info reports rows ↔ cols flipped vs the well grid in the file:
        # `Number of Rows = 12, Number of Columns = 8` for a 96-well plate read
        # as A..H × 1..12. Accept either orientation when cross-checking.
        if n_rows_expected is not None and n_cols_expected is not None:
            actual = {len(grid), n_cols}
            expected = {n_rows_expected, n_cols_expected}
            if actual != expected:
                raise ValueError(
                    f"{path.name}: block '{name}' parsed grid is "
                    f"{len(grid)}×{n_cols} but Plate Type Information reports "
                    f"{n_rows_expected}×{n_cols_expected}."
                )

        return np.asarray(grid, dtype=float)

    @staticmethod
    def _parse_key_value_section(
        lines: List[str], heading: str
    ) -> Dict[str, str]:
        """Extract a flat key/value dict from one of the trailing sections.

        Sections in EnSight CSVs look like::

            Plate Type Information
            Plate Type Name,,96 OptiPlate
            Plate Type Owner,,PKI
            Number of Rows,,12
            ...

        Values are in column 3 (extra empty cells from CSV padding). The
        section ends at the next blank line *followed by* a non-key line,
        or at end-of-file. ``Details of Measurement Sequence`` uses the
        same shape but its keys repeat (one per Operation), so callers
        post-process via :meth:`_block_details`.
        """
        out: Dict[str, str] = {}
        try:
            start = next(i for i, ln in enumerate(lines) if ln.strip() == heading)
        except StopIteration:
            return out

        for j in range(start + 1, len(lines)):
            line = lines[j]
            if "," not in line:
                continue
            stripped = line.strip()
            if not stripped:
                continue
            # A new top-level section is a non-comma-separated heading. Stop.
            if "," not in stripped and stripped != heading:
                break
            key, _, rest = line.partition(",")
            key = key.strip()
            if not key:
                continue
            # value is the first non-empty cell after the key
            value = next(
                (cell.strip() for cell in rest.split(",") if cell.strip()),
                "",
            )
            # For Details of Measurement Sequence, preserve all 'Operation' rows
            # by suffixing duplicates with an index. Other sections just overwrite.
            if key in out and heading == _DETAILS_SECTION:
                k = 2
                while f"{key}#{k}" in out:
                    k += 1
                out[f"{key}#{k}"] = value
            else:
                out[key] = value
        return out

    @staticmethod
    def _block_details(
        block_name: str, details: Dict[str, str]
    ) -> Dict[str, str]:
        """Return the subset of details belonging to one Operation block.

        Walks ``details`` in insertion order, grouping each ``Operation``
        token with the keys that follow it.
        """
        groups: List[Tuple[str, Dict[str, str]]] = []
        current_name: str | None = None
        current_kvs: Dict[str, str] = {}
        for key, value in details.items():
            base = key.split("#", 1)[0]
            if base == "Operation":
                if current_name is not None:
                    groups.append((current_name, current_kvs))
                current_name = value
                current_kvs = {}
            else:
                if current_name is None:
                    continue
                current_kvs[base] = value
        if current_name is not None:
            groups.append((current_name, current_kvs))

        for name, kvs in groups:
            if name == block_name:
                return kvs
        return {}

    @staticmethod
    def _expected_plate_dims(
        plate_info: Dict[str, str],
    ) -> Tuple[int | None, int | None]:
        def _as_int(v: str | None) -> int | None:
            if not v:
                return None
            try:
                return int(float(v))
            except (TypeError, ValueError):
                return None

        return _as_int(plate_info.get("Number of Rows")), _as_int(
            plate_info.get("Number of Columns")
        )


def format_channel_label(
    channel: str, ensight_metadata: Dict[str, Any]
) -> str:
    """Build a human label for an EnSight channel: name + Ex/Em hints.

    Used by the GUI channel picker. Pure function so it's easy to unit
    test in isolation.
    """
    info = ensight_metadata.get("channels", {}).get(channel, {}) if ensight_metadata else {}
    em = info.get("Emission Wavelength [nm]") or info.get("Em wavelength")
    ex = info.get("Excitation Wavelength [nm]") or info.get("Ex wavelength")
    bits: List[str] = []
    if ex:
        bits.append(f"Ex {ex}")
    if em:
        bits.append(f"Em {em}")
    if bits:
        return f"{channel} ({', '.join(bits)})"
    return channel


register_reader(EnsightReader)
