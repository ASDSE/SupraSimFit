"""Tests for concentration vector save/load with unit handling."""

import numpy as np
import pytest

from core.data_processing.concentration import extract_concentrations_from_file, load_concentration_vector, save_concentration_vector


class TestConcentrationRoundTrip:
    """Verify save → load preserves values regardless of stored unit."""

    def test_save_M_load_M(self, tmp_path):
        """Values saved in M come back as M."""
        conc = np.array([1e-7, 5e-7, 1e-6, 5e-6])
        path = tmp_path / 'conc.json'
        save_concentration_vector(conc, path, unit='M')
        loaded, unit, label = load_concentration_vector(path)
        np.testing.assert_allclose(loaded, conc)

    def test_save_uM_load_M(self, tmp_path):
        """Values saved in µM are converted to M on load (the bug fix)."""
        conc_uM = np.array([0.1, 0.5, 1.0, 5.0])  # µM
        expected_M = conc_uM * 1e-6
        path = tmp_path / 'conc.json'
        save_concentration_vector(conc_uM, path, unit='µM')
        loaded, unit, label = load_concentration_vector(path)
        np.testing.assert_allclose(loaded, expected_M, rtol=1e-12)

    def test_save_nM_load_M(self, tmp_path):
        """Values saved in nM are converted to M on load."""
        conc_nM = np.array([100, 500, 1000])  # nM
        expected_M = conc_nM * 1e-9
        path = tmp_path / 'conc.json'
        save_concentration_vector(conc_nM, path, unit='nM')
        loaded, unit, label = load_concentration_vector(path)
        np.testing.assert_allclose(loaded, expected_M, rtol=1e-12)

    def test_label_preserved(self, tmp_path):
        """Label string round-trips correctly."""
        path = tmp_path / 'conc.json'
        save_concentration_vector(np.array([1e-6]), path, label='GDA standard')
        _, _, label = load_concentration_vector(path)
        assert label == 'GDA standard'

    def test_unit_string_preserved(self, tmp_path):
        """The original unit string is returned for display purposes."""
        path = tmp_path / 'conc.json'
        save_concentration_vector(np.array([10.0]), path, unit='µM')
        _, unit, _ = load_concentration_vector(path)
        assert unit == 'µM'

    def test_missing_concentrations_raises(self, tmp_path):
        path = tmp_path / 'bad.json'
        path.write_text('{"unit": "M"}')
        with pytest.raises(ValueError, match='concentrations'):
            load_concentration_vector(path)

    def test_empty_list_raises(self, tmp_path):
        path = tmp_path / 'bad.json'
        path.write_text('{"concentrations": [], "unit": "M"}')
        with pytest.raises(ValueError, match='non-empty'):
            load_concentration_vector(path)


class TestExtractConcentrations:
    def test_extract_from_txt_file(self, tmp_path):
        """Extracts unique sorted concentrations from a measurement file."""
        data = 'var\tsignal\n0.0\t100\n1e-6\t200\n2e-6\t300\nvar\tsignal\n0.0\t110\n1e-6\t210\n2e-6\t310\n'
        p = tmp_path / 'extract.txt'
        p.write_text(data)

        conc = extract_concentrations_from_file(p)

        assert len(conc) == 3
        np.testing.assert_allclose(conc, [0.0, 1e-6, 2e-6])
