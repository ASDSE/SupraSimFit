"""Round-trip tests for the example data template (#24).

The template's whole job is to demonstrate a *reader-accepted* format, so
the meaningful check is that it loads back through the real loader with the
expected shape and values — not that any specific bytes were written.
"""

from __future__ import annotations

import pytest

from core.io import load_measurements
from core.io.template import write_data_template

_N_REPLICAS = 3
_N_POINTS = 6


class TestDataTemplateRoundTrip:
    """The emitted template parses through the app's existing readers."""

    def test_txt_template_round_trips(self, tmp_path):
        path = write_data_template(tmp_path / 'template.txt')

        df = load_measurements(path)
        assert list(df.columns) == ['concentration', 'signal', 'replica']
        assert df['replica'].nunique() == _N_REPLICAS
        assert len(df) == _N_REPLICAS * _N_POINTS

    def test_csv_template_round_trips(self, tmp_path):
        path = write_data_template(tmp_path / 'template.csv')

        df = load_measurements(path)
        assert {'concentration', 'signal', 'replica'}.issubset(df.columns)
        assert df['replica'].nunique() == _N_REPLICAS
        assert len(df) == _N_REPLICAS * _N_POINTS

    def test_extension_selects_format(self, tmp_path):
        """A .txt file uses repeated 'var\\tsignal' headers; .csv does not."""
        txt = (write_data_template(tmp_path / 't.txt')).read_text()
        csv = (write_data_template(tmp_path / 't.csv')).read_text()
        assert 'var\tsignal' in txt and '\t' in txt
        assert 'concentration,signal,replica' in csv and '\t' not in csv

    def test_values_survive_load(self, tmp_path):
        """Independently pin the first replica's concentration grid endpoints."""
        df = load_measurements(write_data_template(tmp_path / 't.txt'))
        r0 = df[df['replica'] == 0].sort_values('concentration')
        assert r0['concentration'].iloc[0] == pytest.approx(0.0)
        assert r0['concentration'].iloc[-1] == pytest.approx(2e-5)
        # Signal is strictly increasing in the example (a plausible titration).
        assert r0['signal'].is_monotonic_increasing
