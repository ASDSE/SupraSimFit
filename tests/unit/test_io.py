"""P4: I/O round-trip tests.

Verify that measurement data survives write→read cycles and that
the reader/writer handle edge cases correctly.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core.io import load_measurements, save_results
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
