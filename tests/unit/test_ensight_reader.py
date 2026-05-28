"""Tests for the PerkinElmer EnSight CSV plate-reader.

Real fixtures come from Panos's europium-zeolite assay (the same files
that produced the legacy ``Normal tryptamine 424.txt`` after Panos's
colleague's pre-treatment script). Golden assertions cross-check the
reader output against that hand-flattened file row-for-row.
"""

from pathlib import Path
from textwrap import dedent

import numpy as np
import pytest

from core.io import load_measurements
from core.io.formats.bmg_reader import BMG_PLACEHOLDER_KEY
from core.io.formats.ensight_reader import (
    ENSIGHT_CHANNEL_COLUMN,
    ENSIGHT_METADATA_KEY,
    EnsightReader,
    format_channel_label,
)
from core.io.registry import get_reader

DATA_DIR = Path(__file__).parent.parent / "data" / "ensight"
TRYPTAMINE_CSV = DATA_DIR / "tryptamine.csv"
DYEALONE_CSV = DATA_DIR / "dyealone.csv"
TRYPTAMINE_FL_TXT = DATA_DIR / "tryptamine_expected_FL.txt"

_FL_CHANNEL = "Fluorescence intensity 1"


def _read_legacy_var_signal(path: Path) -> np.ndarray:
    """Parse the legacy var/signal txt into an n_replicas × n_points array."""
    blocks: list[list[float]] = []
    current: list[float] = []
    for line in path.read_text().splitlines():
        parts = line.strip().split("\t")
        if len(parts) < 2:
            continue
        head = parts[0].strip().lower()
        if head in {"var", "concentration", "conc"}:
            if current:
                blocks.append(current)
                current = []
            continue
        try:
            current.append(float(parts[1]))
        except ValueError:
            continue
    if current:
        blocks.append(current)
    return np.asarray(blocks, dtype=float)


def _minimal_ensight(
    n_channels: int = 1, n_rows: int = 4, n_cols: int = 6
) -> str:
    """Build a minimal EnSight-shaped CSV with `n_channels` Result blocks."""
    header = dedent(
        """\
        EnSight Results from
        Protocol Name,minimal
        Measurement Date,2026-01-01 00:00:00

        """
    )
    blocks: list[str] = []
    for ch in range(n_channels):
        col_header = "," + ",".join(str(i + 1) for i in range(n_cols)) + ","
        rows = []
        for r in range(n_rows):
            letter = chr(ord("A") + r)
            values = ",".join(str(ch * 1000 + r * 100 + c + 1) for c in range(n_cols))
            rows.append(f"{letter},{values},")
        blocks.append(
            f"Result for Channel {ch + 1}\n"
            "Barcode,Repeat,Loop no,Well scan x,Well scan y,Exc wl / filter,Ems wl,TRF Window,Analysis Parameter,Label-free Parameter,\n"
            "V-2026-01-01,1,,,,,,,,,,\n"
            "\n"
            + col_header
            + "\n"
            + "\n".join(rows)
            + "\n"
        )

    plate_info = dedent(
        f"""

        Plate Type Information
        Plate Type Name,,test plate
        Number of Rows,,{n_cols}
        Number of Columns,,{n_rows}
        """
    )
    details = ["\n", "Details of Measurement Sequence\n", "\n"]
    for ch in range(n_channels):
        details.extend(
            [
                f"Operation,,,Channel {ch + 1}\n",
                "Excitation Wavelength [nm],,,371\n",
                "Emission Wavelength [nm],,,424\n",
                "\n",
            ]
        )
    return header + "\n".join(blocks) + plate_info + "".join(details)


class TestSniffing:
    def test_can_read_real_files(self):
        if not TRYPTAMINE_CSV.exists():
            pytest.skip("Real EnSight fixture missing")
        assert EnsightReader.can_read(TRYPTAMINE_CSV)
        assert EnsightReader.can_read(DYEALONE_CSV)

    def test_can_read_with_bom(self, tmp_path):
        p = tmp_path / "ensight_bom.csv"
        p.write_bytes(b"\xef\xbb\xbf" + _minimal_ensight().encode())
        assert EnsightReader.can_read(p)

    def test_rejects_jasco_csv(self, tmp_path):
        p = tmp_path / "jasco.csv"
        p.write_text("TITLE,foo\nORIGIN,JASCO\nXYDATA\n0,1\n")
        assert not EnsightReader.can_read(p)

    def test_rejects_plain_csv(self, tmp_path):
        p = tmp_path / "plain.csv"
        p.write_text("concentration,signal\n0,100\n")
        assert not EnsightReader.can_read(p)


class TestParsing:
    def test_real_file_golden_row_match(self):
        """Row A of the FL channel must match the legacy txt row-for-row."""
        if not TRYPTAMINE_CSV.exists() or not TRYPTAMINE_FL_TXT.exists():
            pytest.skip("Real EnSight fixture missing")
        df = EnsightReader().read(TRYPTAMINE_CSV)
        legacy = _read_legacy_var_signal(TRYPTAMINE_FL_TXT)
        assert legacy.shape == (8, 12)
        fl = df[df[ENSIGHT_CHANNEL_COLUMN] == _FL_CHANNEL]
        for r in range(8):
            row_signals = fl[fl["replica"] == r].sort_values("concentration")["signal"].to_numpy()
            np.testing.assert_allclose(row_signals, legacy[r], rtol=0, atol=0)

    def test_three_channels_detected(self):
        if not TRYPTAMINE_CSV.exists():
            pytest.skip("Real EnSight fixture missing")
        df = EnsightReader().read(TRYPTAMINE_CSV)
        channels = list(df[ENSIGHT_CHANNEL_COLUMN].unique())
        assert channels == [
            "Time-resolved Fluorescence 1",
            "Time-resolved Fluorescence 2",
            "Fluorescence intensity 1",
        ]

    def test_placeholder_concentrations_and_flag(self):
        if not TRYPTAMINE_CSV.exists():
            pytest.skip("Real EnSight fixture missing")
        df = EnsightReader().read(TRYPTAMINE_CSV)
        # Concentrations are bare 1..12
        fl = df[df[ENSIGHT_CHANNEL_COLUMN] == _FL_CHANNEL]
        unique_concs = sorted(fl["concentration"].unique().tolist())
        assert unique_concs == [float(i) for i in range(1, 13)]
        assert df.attrs[BMG_PLACEHOLDER_KEY] is True

    def test_metadata_carries_ex_em_per_channel(self):
        if not TRYPTAMINE_CSV.exists():
            pytest.skip("Real EnSight fixture missing")
        df = EnsightReader().read(TRYPTAMINE_CSV)
        meta = df.attrs[ENSIGHT_METADATA_KEY]
        fl_details = meta["channels"][_FL_CHANNEL]
        # Real file has Excitation Wavelength 371 and Emission 424 for FL1
        assert fl_details.get("Excitation Wavelength [nm]") == "371"
        assert fl_details.get("Emission Wavelength [nm]") == "424"
        assert meta["protocol"]["Protocol Name"] == "Euzeolite@MDAP endpoint"

    def test_minimal_single_channel(self, tmp_path):
        p = tmp_path / "min.csv"
        p.write_text(_minimal_ensight(n_channels=1, n_rows=3, n_cols=4))
        df = EnsightReader().read(p)
        # 1 channel × 3 rows × 4 cols = 12 rows in long format
        assert len(df) == 12
        assert sorted(df["concentration"].unique().tolist()) == [1.0, 2.0, 3.0, 4.0]
        assert sorted(df["replica"].unique().tolist()) == [0, 1, 2]
        assert list(df[ENSIGHT_CHANNEL_COLUMN].unique()) == ["Channel 1"]

    def test_minimal_multi_channel(self, tmp_path):
        p = tmp_path / "multi.csv"
        p.write_text(_minimal_ensight(n_channels=3, n_rows=4, n_cols=6))
        df = EnsightReader().read(p)
        assert list(df[ENSIGHT_CHANNEL_COLUMN].unique()) == [
            "Channel 1",
            "Channel 2",
            "Channel 3",
        ]

    def test_no_result_blocks_raises(self, tmp_path):
        p = tmp_path / "empty.csv"
        p.write_text("EnSight Results from\nProtocol Name,foo\n\n")
        with pytest.raises(ValueError, match="no 'Result for"):
            EnsightReader().read(p)

    def test_non_sequential_columns_raises(self, tmp_path):
        broken = _minimal_ensight().replace(",1,2,3,4,5,6,", ",1,3,2,4,5,6,")
        p = tmp_path / "broken.csv"
        p.write_text(broken)
        with pytest.raises(ValueError, match="not sequential"):
            EnsightReader().read(p)

    def test_out_of_sequence_rows_raises(self, tmp_path):
        broken = _minimal_ensight().replace("B,", "C,", 1)
        p = tmp_path / "broken.csv"
        p.write_text(broken)
        with pytest.raises(ValueError, match="out of sequence"):
            EnsightReader().read(p)


class TestChannelLabelHelper:
    def test_label_combines_ex_em(self):
        meta = {
            "channels": {
                "FL1": {
                    "Excitation Wavelength [nm]": "371",
                    "Emission Wavelength [nm]": "424",
                }
            }
        }
        assert format_channel_label("FL1", meta) == "FL1 (Ex 371, Em 424)"

    def test_label_falls_back_to_name_when_no_metadata(self):
        assert format_channel_label("FooBar", {}) == "FooBar"


class TestDispatch:
    def test_registry_routes_real_ensight_to_ensight_reader(self):
        if not TRYPTAMINE_CSV.exists():
            pytest.skip("Real EnSight fixture missing")
        reader = get_reader(TRYPTAMINE_CSV)
        assert isinstance(reader, EnsightReader)

    def test_load_measurements_returns_channel_column(self):
        if not TRYPTAMINE_CSV.exists():
            pytest.skip("Real EnSight fixture missing")
        df = load_measurements(TRYPTAMINE_CSV)
        assert ENSIGHT_CHANNEL_COLUMN in df.columns
        assert df.attrs[BMG_PLACEHOLDER_KEY] is True
