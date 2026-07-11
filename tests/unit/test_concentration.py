"""Tests for concentration vector save/load with unit handling."""

import numpy as np
import pytest

from core.data_processing.concentration import (
    extract_concentrations_from_file,
    read_raw_concentrations,
    save_concentration_vector,
)
from core.units import Q_


class TestConcentrationRoundTrip:
    """save_concentration_vector → read_raw_concentrations preserves the physical
    quantity as a self-describing Quantity in the saved unit."""

    def test_save_M_read_back(self, tmp_path):
        """Values saved in M read back as a molar Quantity."""
        conc = np.array([1e-7, 5e-7, 1e-6, 5e-6])
        path = tmp_path / 'conc.json'
        save_concentration_vector(conc, path, unit='M')
        q = read_raw_concentrations(path)
        assert q.units == Q_(1, 'M').units
        np.testing.assert_allclose(q.to('M').magnitude, conc)

    def test_save_uM_read_back_converts(self, tmp_path):
        """µM saved → read back as a µM Quantity → correct molar (the bug fix)."""
        conc_uM = np.array([0.1, 0.5, 1.0, 5.0])
        path = tmp_path / 'conc.json'
        save_concentration_vector(conc_uM, path, unit='µM', label='GDA standard')
        q = read_raw_concentrations(path)
        assert q.units == Q_(1, 'µM').units
        np.testing.assert_allclose(q.magnitude, conc_uM)
        np.testing.assert_allclose(q.to('M').magnitude, conc_uM * 1e-6, rtol=1e-12)

    def test_missing_concentrations_raises(self, tmp_path):
        path = tmp_path / 'bad.json'
        path.write_text('{"unit": "M"}')
        with pytest.raises(ValueError, match='concentrations'):
            read_raw_concentrations(path)

    def test_empty_list_raises(self, tmp_path):
        path = tmp_path / 'bad.json'
        path.write_text('{"concentrations": [], "unit": "M"}')
        with pytest.raises(ValueError, match='non-empty'):
            read_raw_concentrations(path)


class TestExtractConcentrations:
    def test_extract_from_txt_file(self, tmp_path):
        """Extracts unique sorted concentrations as a Quantity, molar by default."""
        data = 'var\tsignal\n0.0\t100\n1e-6\t200\n2e-6\t300\nvar\tsignal\n0.0\t110\n1e-6\t210\n2e-6\t310\n'
        p = tmp_path / 'extract.txt'
        p.write_text(data)

        conc = extract_concentrations_from_file(p)

        assert conc.units == Q_(1, 'M').units
        np.testing.assert_allclose(conc.to('M').magnitude, [0.0, 1e-6, 2e-6])

    def test_extract_honors_declared_uM_unit(self, tmp_path):
        """A '# units: concentration=uM' header is honored: face values stay µM and
        convert to the correct molar grid — no silent 1e6 error (H1)."""
        data = '# units: concentration=uM\nvar\tsignal\n1\t100\n2\t200\n5\t500\n'
        p = tmp_path / 'um.txt'
        p.write_text(data)

        conc = extract_concentrations_from_file(p)

        assert conc.units == Q_(1, 'µM').units
        np.testing.assert_allclose(conc.magnitude, [1.0, 2.0, 5.0])
        np.testing.assert_allclose(conc.to('M').magnitude, [1e-6, 2e-6, 5e-6])
