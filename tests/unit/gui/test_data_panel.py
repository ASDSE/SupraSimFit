"""Tests for the inline DataPanel concentration controls."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("PyQt6")


@pytest.fixture(scope="module")
def qapp():
    import sys

    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    return app


@pytest.fixture
def loaded_panel(qapp, tmp_path):
    """A DataPanel populated with a tiny three-point dataset (face values in M)."""
    from core.data_processing.measurement_set import MeasurementSet
    from gui.widgets.data_panel import DataPanel

    panel = DataPanel()
    conc = np.array([1e-6, 2e-6, 3e-6])
    df = pd.DataFrame(
        [
            {"concentration": c, "signal": (i + 1) * 100.0, "replica": r}
            for r in range(2)
            for i, c in enumerate(conc)
        ]
    )
    ms = MeasurementSet.from_dataframe(df, source_file=str(tmp_path / "fake.txt"))
    panel._ms = ms
    panel._source_path = str(tmp_path / "fake.txt")
    panel._face_values = np.asarray(ms.concentrations, dtype=np.float64).copy()
    panel._imported_unit = "M"
    panel._refresh_after_load()
    return panel


class TestImportedUnitReinterpret:
    """Changing the Imported Unit must reinterpret face values via Pint."""

    def test_unit_change_rescales_underlying_molar(self, loaded_panel, qtbot=None):
        ms_before = loaded_panel.measurement_set()
        np.testing.assert_allclose(ms_before.concentrations, [1e-6, 2e-6, 3e-6])

        # Reinterpret face-values [1e-6, 2e-6, 3e-6] as µM → 1e-12 .. 3e-12 M
        loaded_panel._imported_unit_combo.setCurrentText("µM")

        ms_after = loaded_panel.measurement_set()
        np.testing.assert_allclose(ms_after.concentrations, [1e-12, 2e-12, 3e-12])

    def test_unit_change_does_not_rewrite_table_values(self, loaded_panel):
        before = [
            loaded_panel._conc_table.item(r, 0).text()
            for r in range(loaded_panel._conc_table.rowCount())
        ]
        loaded_panel._imported_unit_combo.setCurrentText("µM")
        after = [
            loaded_panel._conc_table.item(r, 0).text()
            for r in range(loaded_panel._conc_table.rowCount())
        ]
        assert before == after


class TestLiveCommit:
    """Every committed cell edit immediately rebuilds the MeasurementSet."""

    def test_single_cell_edit_emits_and_rebuilds(self, loaded_panel):
        emissions = []
        loaded_panel.data_loaded.connect(lambda ms: emissions.append(ms))

        loaded_panel._conc_table.item(0, 0).setText("5e-6")

        assert len(emissions) == 1
        np.testing.assert_allclose(emissions[-1].concentrations, [5e-6, 2e-6, 3e-6])

    def test_consecutive_cell_edits_each_emit(self, loaded_panel):
        emissions = []
        loaded_panel.data_loaded.connect(lambda ms: emissions.append(ms))

        loaded_panel._conc_table.item(0, 0).setText("5e-6")
        loaded_panel._conc_table.item(2, 0).setText("9e-6")

        assert len(emissions) == 2
        np.testing.assert_allclose(emissions[-1].concentrations, [5e-6, 2e-6, 9e-6])

    def test_no_apply_button_attribute(self, loaded_panel):
        """The Apply button is gone — live commit replaces it."""
        assert not hasattr(loaded_panel, "_apply_btn")


class TestDisplayUnitSignal:
    """The Display Unit combo emits ``display_unit_changed`` independently."""

    def test_display_unit_combo_emits(self, loaded_panel):
        received: list[str] = []
        loaded_panel.display_unit_changed.connect(received.append)

        loaded_panel._display_unit_combo.setCurrentText("nM")

        assert received == ["nM"]

    def test_display_unit_does_not_emit_data_loaded(self, loaded_panel):
        emissions = []
        loaded_panel.data_loaded.connect(lambda ms: emissions.append(ms))
        loaded_panel._display_unit_combo.setCurrentText("nM")
        # Display unit is plot-only state — concentrations are untouched,
        # so no data_loaded cascade should fire.
        assert emissions == []
