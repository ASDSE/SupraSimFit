"""JASCO Spectra Manager titration export reader.

JASCO instruments (FP-8300 spectrofluorometer + ATS-827 titrator and
relatives) emit a self-describing CSV with three regions::

    KEY,VALUE                 ← header block (TITLE, NPOINTS, XUNITS, ...)
    ...
    XYDATA                    ← literal marker
    <x>,<y>                   ← two-column data, length = NPOINTS
    <x>,<y>
    ...
    (blank line)
    [Section]                 ← extended info: bracketed INI sections
    KEY,VALUE
    ...

Parsing anchors are structural — the ``XYDATA`` token opens the data
block, the first blank line closes it. No row offsets are hard-coded;
files with different ``NPOINTS`` or stage counts parse the same way.

Concentrations are converted to the app's base unit (M) via Pint, using
the unit token written by JASCO inside ``XUNITS`` (e.g.
``Concentration [umol/L]``). Unrecognised units raise ``ValueError``.

Extended-info metadata (instrument, Ex/Em wavelengths, syringe stocks,
…) lands on ``df.attrs['jasco_metadata']`` for downstream GUI use.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
import pint

from core.io.registry import register_reader
from core.units import Q_

#: Key under which parsed JASCO header + extended-info dicts are attached to
#: ``df.attrs`` and forwarded to ``MeasurementSet.metadata`` by the GUI loader.
JASCO_METADATA_KEY = 'jasco_metadata'

_SIGNATURE_PROBE_LINES = 30
_XYDATA_MARKER = 'XYDATA'
_UNIT_BRACKET_RE = re.compile(r'\[([^\]]+)\]')
_SECTION_RE = re.compile(r'^\[(?P<name>[^\]]+)\]\s*$')


class JascoReader:
    """Reader for JASCO Spectra Manager titration CSV exports."""

    extensions = ('.csv',)

    @classmethod
    def can_read(cls, path: Path) -> bool:
        """Return True if ``path`` looks like a JASCO export.

        Sniffs the first ~30 lines for either ``ORIGIN,JASCO`` (the
        canonical originator tag) or the standalone ``XYDATA`` marker.
        Tolerates BOMs and Windows line endings.
        """
        try:
            with open(path, 'r', encoding='utf-8-sig', errors='replace') as f:
                for _ in range(_SIGNATURE_PROBE_LINES):
                    line = f.readline()
                    if not line:
                        break
                    stripped = line.strip()
                    if stripped == _XYDATA_MARKER:
                        return True
                    if stripped.upper().startswith('ORIGIN,JASCO'):
                        return True
        except OSError:
            return False
        return False

    def read(self, path: Path) -> pd.DataFrame:
        """Parse a JASCO export into the standard long-format DataFrame.

        The returned frame has columns ``concentration`` (in M),
        ``signal``, and ``replica`` (always 0 — JASCO files are
        single-curve). Parsed header and extended-info dictionaries are
        attached via ``df.attrs['jasco_metadata']``.
        """
        with open(path, 'r', encoding='utf-8-sig', errors='replace') as f:
            lines = [line.rstrip('\r\n') for line in f]

        header, data_lines, extended = self._partition(lines, path)
        x_raw, y_raw = self._parse_data_block(data_lines, header, path)
        x_M = self._convert_x_to_M(x_raw, header, path)

        df = pd.DataFrame(
            {
                'concentration': x_M,
                'signal': y_raw,
                'replica': 0,
            }
        )
        df.attrs[JASCO_METADATA_KEY] = {'header': header, 'sections': extended}
        return df

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _partition(self, lines: List[str], path: Path) -> Tuple[Dict[str, str], List[str], Dict[str, Dict[str, str]]]:
        """Split file into (header dict, data lines, extended-info sections)."""
        try:
            xy_idx = next(i for i, ln in enumerate(lines) if ln.strip() == _XYDATA_MARKER)
        except StopIteration as exc:
            raise ValueError(
                f"{path.name}: missing '{_XYDATA_MARKER}' marker — file does not look like a JASCO export."
            ) from exc

        header: Dict[str, str] = {}
        for ln in lines[:xy_idx]:
            if ',' not in ln:
                continue
            key, _, value = ln.partition(',')
            key = key.strip()
            if key:
                header[key] = value.strip()

        data_lines: List[str] = []
        i = xy_idx + 1
        while i < len(lines) and lines[i].strip():
            data_lines.append(lines[i])
            i += 1

        extended = self._parse_extended(lines[i:])
        return header, data_lines, extended

    @staticmethod
    def _parse_extended(
        lines: List[str],
    ) -> Dict[str, Dict[str, str | List[str]]]:
        """Parse the bracketed-INI extended-info block into nested dicts.

        Real JASCO exports may repeat a key within a section (e.g. two
        ``Accessory`` lines for two stacked accessories). Single
        occurrences are stored as plain strings; the second and later
        occurrences promote the value to a list so no data is lost.
        """
        sections: Dict[str, Dict[str, str | List[str]]] = {}
        current: str | None = None
        for ln in lines:
            stripped = ln.strip()
            if not stripped:
                continue
            section_match = _SECTION_RE.match(stripped)
            if section_match:
                current = section_match.group('name').strip()
                sections.setdefault(current, {})
                continue
            if current is None or ',' not in ln:
                continue
            key, _, value = ln.partition(',')
            key = key.strip()
            if not key:
                continue
            value = value.strip()
            bucket = sections[current]
            if key in bucket:
                existing = bucket[key]
                if isinstance(existing, list):
                    existing.append(value)
                else:
                    bucket[key] = [existing, value]
            else:
                bucket[key] = value
        return sections

    @staticmethod
    def _parse_data_block(data_lines: List[str], header: Dict[str, Any], path: Path) -> Tuple[np.ndarray, np.ndarray]:
        """Parse two-column numeric data and cross-check against ``NPOINTS``."""
        xs: List[float] = []
        ys: List[float] = []
        for ln in data_lines:
            parts = [p.strip() for p in ln.split(',') if p.strip() != '']
            if len(parts) < 2:
                raise ValueError(f"{path.name}: malformed JASCO data row {ln!r} (expected '<x>,<y>').")
            try:
                xs.append(float(parts[0]))
                ys.append(float(parts[1]))
            except ValueError as exc:
                raise ValueError(f'{path.name}: non-numeric JASCO data row {ln!r}: {exc}') from exc

        npoints_raw = header.get('NPOINTS')
        if npoints_raw is not None:
            try:
                expected = int(npoints_raw)
            except (TypeError, ValueError):
                expected = None
            if expected is not None and expected != len(xs):
                raise ValueError(
                    f'{path.name}: header NPOINTS={expected} disagrees with '
                    f'{len(xs)} parsed data rows. The file may be truncated '
                    'or the NPOINTS value is wrong.'
                )

        if not xs:
            raise ValueError(f'{path.name}: no data rows between XYDATA and blank line.')

        return np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)

    @staticmethod
    def _convert_x_to_M(x_raw: np.ndarray, header: Dict[str, str], path: Path) -> np.ndarray:
        """Convert the x column to M using the unit token in ``XUNITS``.

        JASCO writes ``XUNITS`` as e.g. ``Concentration [umol/L]``. The
        bracketed token is the unit Pint understands. Falls back to the
        whole string if no brackets are present.
        """
        xunits = header.get('XUNITS', '').strip()
        if not xunits:
            raise ValueError(f'{path.name}: JASCO header has no XUNITS entry — cannot determine concentration unit.')
        match = _UNIT_BRACKET_RE.search(xunits)
        token = match.group(1).strip() if match else xunits
        try:
            return Q_(x_raw, token).to('M').magnitude
        except (
            pint.errors.UndefinedUnitError,
            pint.errors.DimensionalityError,
        ) as exc:
            raise ValueError(
                f'{path.name}: cannot interpret JASCO XUNITS {xunits!r} '
                f'(token {token!r}) as a concentration: {exc}. '
                "Supported tokens include 'umol/L', 'µmol/L', 'mmol/L', "
                "'mol/L', 'nmol/L'."
            ) from exc


register_reader(JascoReader)
