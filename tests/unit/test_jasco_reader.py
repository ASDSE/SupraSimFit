"""Tests for the JASCO Spectra Manager CSV reader.

Covers the parts of the format that vary file-to-file (NPOINTS, x-axis
unit, presence/absence of extended-info sections) and the structural
anchors the reader leans on (``XYDATA`` marker, blank-line data
terminator). Includes a golden-file check against the bundled
``cb7in30umbc_1-1.csv`` titration fixture.
"""

from pathlib import Path
from textwrap import dedent

import pytest

from core.io import load_measurements
from core.io.formats.jasco_reader import JascoReader
from core.io.registry import get_reader

REAL_FIXTURE = Path(__file__).parent.parent / 'data' / 'jasco' / 'cb7in30umbc_1-1.csv'


def _minimal_jasco(
    n_points: int = 3,
    x_unit: str = 'umol/L',
    extra_extended: str = '',
    npoints_header: int | None = None,
) -> str:
    """Build a minimal JASCO-shaped CSV. n_points = real data rows; header
    NPOINTS defaults to n_points unless ``npoints_header`` overrides it."""
    declared = n_points if npoints_header is None else npoints_header
    body = '\n'.join(f'{i:.4f},{(i + 1) * 10:.4f}' for i in range(n_points))
    return (
        dedent(
            f"""\
        TITLE,minimal
        DATA TYPE,FLUORESCENCE SPECTRUM
        ORIGIN,JASCO
        XUNITS,Concentration [{x_unit}]
        YUNITS,INTENSITY
        NPOINTS,{declared}
        XYDATA
        """
        )
        + body
        + ('\n' if not body.endswith('\n') else '')
        + extra_extended
    )


class TestSniffing:
    def test_can_read_minimal(self, tmp_path):
        p = tmp_path / 'jasco.csv'
        p.write_text(_minimal_jasco())
        assert JascoReader.can_read(p)

    def test_can_read_with_bom(self, tmp_path):
        p = tmp_path / 'jasco_bom.csv'
        p.write_bytes(b'\xef\xbb\xbf' + _minimal_jasco().encode())
        assert JascoReader.can_read(p)

    def test_rejects_non_jasco_csv(self, tmp_path):
        p = tmp_path / 'plain.csv'
        p.write_text('concentration,signal\n0,100\n1e-6,200\n')
        assert not JascoReader.can_read(p)


class TestParsing:
    def test_real_file_golden(self):
        """Real titration fixture via the public API — exercises sniffer +
        registry dispatch end-to-end, with known counts and golden values."""
        if not REAL_FIXTURE.exists():
            pytest.skip('Real JASCO fixture missing')
        df = load_measurements(REAL_FIXTURE)
        assert 'jasco_metadata' in df.attrs
        assert list(df.columns) == ['concentration', 'signal', 'replica']
        assert len(df) == 31
        assert (df['replica'] == 0).all()
        # First row: x=0 µM → 0 M
        assert df['concentration'].iloc[0] == pytest.approx(0.0, abs=1e-12)
        # Last row: x=46.1739 µM → 4.61739e-5 M
        assert df['concentration'].iloc[-1] == pytest.approx(46.1739e-6, rel=1e-6)
        assert df['signal'].iloc[0] == pytest.approx(11.4842)
        assert df['signal'].iloc[-1] == pytest.approx(1594.92)

    def test_metadata_round_trips(self):
        if not REAL_FIXTURE.exists():
            pytest.skip('Real JASCO fixture missing')
        df = JascoReader().read(REAL_FIXTURE)
        meta = df.attrs['jasco_metadata']
        assert meta['header']['ORIGIN'] == 'JASCO'
        assert meta['header']['NPOINTS'] == '31'
        # Titrant stock — should be present in [Measurement Information]
        titrant = meta['sections']['Measurement Information']['Titrant conc.']
        assert '354' in titrant and 'umol/L' in titrant
        # Ex/Em wavelengths
        meas = meta['sections']['Measurement Information']
        assert meas['Ex wavelength'] == '415.0 nm'
        assert meas['Em wavelength'] == '555.0 nm'

    def test_variable_npoints(self, tmp_path):
        p = tmp_path / 'many.csv'
        p.write_text(_minimal_jasco(n_points=7))
        df = JascoReader().read(p)
        assert len(df) == 7

    @pytest.mark.parametrize(
        'unit,expected_first_step_M',
        [
            ('umol/L', 1e-6),
            ('µmol/L', 1e-6),
            ('mmol/L', 1e-3),
            ('nmol/L', 1e-9),
            ('mol/L', 1.0),
        ],
    )
    def test_unit_conversion(self, tmp_path, unit, expected_first_step_M):
        p = tmp_path / f'{unit.replace("/", "_")}.csv'
        p.write_text(_minimal_jasco(n_points=3, x_unit=unit))
        df = JascoReader().read(p)
        # Row index 1 has x=1.0 in declared unit → expected_first_step_M in M
        assert df['concentration'].iloc[1] == pytest.approx(expected_first_step_M)

    def test_missing_xydata_marker_raises(self, tmp_path):
        p = tmp_path / 'no_marker.csv'
        p.write_text('ORIGIN,JASCO\nNPOINTS,3\n0,1\n1,2\n2,3\n')
        with pytest.raises(ValueError, match='XYDATA'):
            JascoReader().read(p)

    def test_npoints_mismatch_raises(self, tmp_path):
        p = tmp_path / 'mismatch.csv'
        # header claims 5 rows but body has 3
        p.write_text(_minimal_jasco(n_points=3, npoints_header=5))
        with pytest.raises(ValueError, match='NPOINTS=5'):
            JascoReader().read(p)

    def test_unknown_unit_raises(self, tmp_path):
        p = tmp_path / 'weird_unit.csv'
        p.write_text(_minimal_jasco(x_unit='floops'))
        with pytest.raises(ValueError, match='floops'):
            JascoReader().read(p)

    def test_repeated_keys_preserved_as_list(self):
        """Real JASCO exports stack accessories — both must survive."""
        if not REAL_FIXTURE.exists():
            pytest.skip('Real JASCO fixture missing')
        df = JascoReader().read(REAL_FIXTURE)
        meas = df.attrs['jasco_metadata']['sections']['Measurement Information']
        accessory = meas['Accessory']
        accessory_sn = meas['Accessory S/N']
        assert isinstance(accessory, list)
        assert isinstance(accessory_sn, list)
        # The bundled file lists STR-812 + ATS-827; both must be retained.
        assert 'STR-812' in accessory
        assert 'ATS-827' in accessory
        # And serial numbers should be paired, not collapsed.
        assert len(accessory) == len(accessory_sn) == 2

    def test_single_key_still_returns_string(self, tmp_path):
        """Non-duplicate keys keep the plain-string value type."""
        p = tmp_path / 'single.csv'
        extra = dedent(
            """
            [Measurement Information]
            Instrument name,FP-8300
            """
        )
        p.write_text(_minimal_jasco(extra_extended=extra))
        df = JascoReader().read(p)
        section = df.attrs['jasco_metadata']['sections']['Measurement Information']
        assert section['Instrument name'] == 'FP-8300'
        assert isinstance(section['Instrument name'], str)

    def test_extended_info_parsed(self, tmp_path):
        extra = dedent(
            """
            ##### Extended Information
            [Comments]
            Sample name,foo

            [Measurement Information]
            Ex wavelength,415.0 nm
            Em wavelength,555.0 nm
            """
        )
        p = tmp_path / 'ext.csv'
        p.write_text(_minimal_jasco(extra_extended=extra))
        df = JascoReader().read(p)
        sections = df.attrs['jasco_metadata']['sections']
        assert sections['Comments']['Sample name'] == 'foo'
        assert sections['Measurement Information']['Ex wavelength'] == '415.0 nm'


class TestDispatch:
    def test_plain_csv_still_uses_generic_reader(self, tmp_path):
        p = tmp_path / 'plain.csv'
        p.write_text('concentration,signal\n0,100\n1e-6,200\n')
        reader = get_reader(p)
        assert type(reader).__name__ == 'CsvReader'
