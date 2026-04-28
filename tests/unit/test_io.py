"""P4: I/O round-trip tests.

Verify that measurement data survives write→read cycles and that
the reader/writer handle edge cases correctly.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core.io import load_measurements, save_results
from core.io.formats.csv_reader import CsvReader
from core.io.formats.txt import TxtReader, TxtWriter
from core.io.registry import get_reader, get_writer


class TestTxtReader:
    """TxtReader correctly parses measurement files."""

    def test_single_replica(self, tmp_path):
        """Single replica file loads correctly."""
        data = 'var\tsignal\n0.0\t100.0\n1e-6\t200.0\n2e-6\t300.0\n'
        p = tmp_path / 'single.txt'
        p.write_text(data)

        reader = TxtReader()
        df = reader.read(p)

        assert len(df) == 3
        assert list(df.columns) == ['concentration', 'signal', 'replica']
        assert (df['replica'] == 0).all()
        assert df['concentration'].iloc[0] == pytest.approx(0.0)
        assert df['signal'].iloc[-1] == pytest.approx(300.0)

    def test_multi_replica(self, tmp_path):
        """Multi-replica file with repeated headers is parsed correctly."""
        data = 'var\tsignal\n0.0\t100.0\n1e-6\t200.0\nvar\tsignal\n0.0\t110.0\n1e-6\t210.0\nvar\tsignal\n0.0\t105.0\n1e-6\t205.0\n'
        p = tmp_path / 'multi.txt'
        p.write_text(data)

        reader = TxtReader()
        df = reader.read(p)

        assert len(df) == 6
        assert set(df['replica'].unique()) == {0, 1, 2}
        # 2 rows per replica
        for r in range(3):
            assert len(df[df['replica'] == r]) == 2

    def test_skips_comment_lines(self, tmp_path):
        """Lines starting with # are ignored."""
        data = '# comment\nvar\tsignal\n0.0\t100.0\n# another comment\n1e-6\t200.0\n'
        p = tmp_path / 'comments.txt'
        p.write_text(data)

        reader = TxtReader()
        df = reader.read(p)

        assert len(df) == 2

    def test_empty_file_raises(self, tmp_path):
        """Empty file raises ValueError."""
        p = tmp_path / 'empty.txt'
        p.write_text('')

        reader = TxtReader()
        with pytest.raises(ValueError, match='No data found'):
            reader.read(p)

    def test_loads_real_gda_data(self):
        """Load the actual GDA data file from the data/ directory."""
        gda_path = Path('data/GDA_system.txt')
        if not gda_path.exists():
            pytest.skip('GDA_system.txt not found in data/')

        df = load_measurements(gda_path)
        assert len(df) > 0
        assert 'concentration' in df.columns
        assert 'signal' in df.columns
        assert 'replica' in df.columns

    def test_concentration_header_variant(self, tmp_path):
        """Accepts 'concentration' as header name."""
        data = 'concentration\tsignal\n0.0\t100.0\n1e-6\t200.0\n'
        p = tmp_path / 'conc_header.txt'
        p.write_text(data)

        reader = TxtReader()
        df = reader.read(p)
        assert len(df) == 2


class TestCsvReader:
    """CsvReader handles varied CSV dialects and headers."""

    def test_standard_comma_dot(self, tmp_path):
        """Comma-separated, dot-decimal CSV with canonical headers."""
        data = 'concentration,signal\n0.0,100.0\n1e-6,200.0\n2e-6,300.0\n'
        p = tmp_path / 'std.csv'
        p.write_text(data)

        df = CsvReader().read(p)
        assert len(df) == 3
        assert df['concentration'].iloc[1] == pytest.approx(1e-6)
        assert df['signal'].iloc[-1] == pytest.approx(300.0)
        assert (df['replica'] == 0).all()

    def test_european_semicolon_comma(self, tmp_path):
        """Semicolon-delimited, comma-decimal CSV (Patrick-style)."""
        data = 'conc CB;Int (455 nm) cut 513\n0;29,29\n10,61;234,95\n20,97;416,78\n'
        p = tmp_path / 'euro.csv'
        p.write_text(data)

        df = CsvReader().read(p)
        assert len(df) == 3
        assert df['concentration'].iloc[1] == pytest.approx(10.61)
        assert df['signal'].iloc[2] == pytest.approx(416.78)

    def test_fuzzy_headers_via_name_match(self, tmp_path):
        """'conc CB' and 'Int (...)' are detected via token-startswith."""
        data = 'conc CB,Int (455 nm) cut 513\n0.0,29.29\n1.0,234.95\n2.0,416.78\n'
        p = tmp_path / 'fuzzy.csv'
        p.write_text(data)

        df = CsvReader().read(p)
        assert len(df) == 3
        assert df['signal'].iloc[0] == pytest.approx(29.29)

    def test_headerless_inferred_by_monotonicity(self, tmp_path):
        """CSV without a header row: concentration inferred as monotonic column."""
        data = '0.0,100.0\n1.0,250.0\n2.0,380.0\n3.0,470.0\n4.0,540.0\n'
        p = tmp_path / 'headerless.csv'
        p.write_text(data)

        df = CsvReader().read(p)
        assert len(df) == 5
        assert df['concentration'].iloc[0] == pytest.approx(0.0)
        assert df['signal'].iloc[-1] == pytest.approx(540.0)

    def test_foreign_headers_fall_through_to_content(self, tmp_path):
        """Unrecognized header names still parse via content inference."""
        data = 'menge;messwert\n0;29,29\n1;234,95\n2;416,78\n3;540,12\n'
        p = tmp_path / 'foreign.csv'
        p.write_text(data)

        df = CsvReader().read(p)
        assert len(df) == 4
        assert df['concentration'].iloc[2] == pytest.approx(2.0)

    def test_wide_format_replicates(self, tmp_path):
        """Wide format: one conc column + multiple signal columns → replicas."""
        data = 'concentration,rep0,rep1,rep2\n0.0,100.0,105.0,98.0\n1e-6,200.0,210.0,195.0\n'
        p = tmp_path / 'wide.csv'
        p.write_text(data)

        df = CsvReader().read(p)
        assert set(df['replica'].unique()) == {0, 1, 2}
        assert len(df) == 6

    def test_unparseable_raises(self, tmp_path):
        """Non-numeric content raises ValueError."""
        data = 'name,color\nalice,red\nbob,blue\n'
        p = tmp_path / 'bad.csv'
        p.write_text(data)

        with pytest.raises(ValueError, match='Cannot'):
            CsvReader().read(p)

    def test_loads_patrick_file(self):
        """Real-world European CSV from data/patrick_data_origin_exp/ loads."""
        path = Path('data/patrick_data_origin_exp/CB7 azo 1 I 455 nm cut 513.csv')
        if not path.exists():
            pytest.skip(f'{path} not found')

        df = CsvReader().read(path)
        assert len(df) == 15
        assert df['concentration'].is_monotonic_increasing
        assert df['concentration'].iloc[0] == pytest.approx(0.0)
        assert df['concentration'].iloc[-1] == pytest.approx(128.08511)
        assert df['signal'].iloc[-1] == pytest.approx(1291.17225)


class TestTxtWriter:
    """TxtWriter correctly serializes fit results."""

    def test_write_and_read_back(self, tmp_path):
        """Written results can be read back as text."""
        results = {
            'Ka_guest': 1.5e6,
            'Ka_guest_uncertainty': 0.2e6,
            'I0': 50.0,
            'I0_uncertainty': 5.0,
            'RMSE': 25.3,
            'R2': 0.998,
        }
        p = tmp_path / 'results.txt'
        writer = TxtWriter()
        writer.write(results, p)

        content = p.read_text()
        assert 'Ka_guest' in content
        assert '1.500000e+06' in content
        assert 'RMSE' in content

    def test_write_results_via_public_api(self, tmp_path):
        """save_results() public API works end-to-end."""
        results = {'Ka_dye': 5e5, 'Ka_dye_uncertainty': 1e4}
        p = tmp_path / 'api_results.txt'
        save_results(results, p)

        assert p.exists()
        content = p.read_text()
        assert 'Ka_dye' in content


class TestRegistryDispatch:
    """Format registry dispatches to correct reader/writer."""

    def test_txt_reader_dispatch(self):
        reader = get_reader(Path('test.txt'))
        assert isinstance(reader, TxtReader)

    def test_csv_reader_dispatch(self):
        reader = get_reader(Path('test.csv'))
        assert isinstance(reader, CsvReader)

    def test_txt_writer_dispatch(self):
        writer = get_writer(Path('test.txt'))
        assert isinstance(writer, TxtWriter)

    def test_unsupported_format_raises(self):
        with pytest.raises(ValueError, match='No reader'):
            get_reader(Path('test.xyz'))

    def test_unsupported_writer_raises(self):
        with pytest.raises(ValueError, match='No writer'):
            get_writer(Path('test.json'))


class TestIODataIntegrity:
    """Measurement data survives load with correct types and values."""

    def test_roundtrip_preserves_values(self, tmp_path):
        """Write a measurement file, read it back, values match."""
        # Create a synthetic measurement file
        data = 'var\tsignal\n'
        values = [(0.0, 100.0), (1e-6, 200.5), (2.5e-6, 350.75)]
        for conc, sig in values:
            data += f'{conc}\t{sig}\n'

        p = tmp_path / 'roundtrip.txt'
        p.write_text(data)

        df = load_measurements(p)
        for i, (conc, sig) in enumerate(values):
            assert df['concentration'].iloc[i] == pytest.approx(conc)
            assert df['signal'].iloc[i] == pytest.approx(sig)

    def test_dtypes_are_numeric(self, tmp_path):
        """Loaded data has numeric dtypes, not strings."""
        data = 'var\tsignal\n0.0\t100.0\n1e-6\t200.0\n'
        p = tmp_path / 'types.txt'
        p.write_text(data)

        df = load_measurements(p)
        assert pd.api.types.is_numeric_dtype(df['concentration'])
        assert pd.api.types.is_numeric_dtype(df['signal'])
        assert pd.api.types.is_integer_dtype(df['replica'])
