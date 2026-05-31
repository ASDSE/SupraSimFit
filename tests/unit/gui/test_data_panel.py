"""Tests for the inline DataPanel concentration controls."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("PyQt6")

ENSIGHT_FIXTURE = (
    Path(__file__).parent.parent.parent / "data" / "ensight" / "tryptamine.csv"
)
JASCO_FIXTURE = (
    Path(__file__).parent.parent.parent / "data" / "jasco" / "cb7in30umbc_1-1.csv"
)


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


def _multi_channel_frame():
    """Two-channel placeholder frame: chA signals 0.., chB signals 1000..."""
    rows = []
    for ch, base in [("chA", 0.0), ("chB", 1000.0)]:
        for r in range(2):
            for i in range(3):
                rows.append(
                    {
                        "concentration": float(i + 1),  # placeholders 1..3
                        "signal": base + r * 10 + i,
                        "replica": r,
                        "channel": ch,
                    }
                )
    df = pd.DataFrame(rows)
    df.attrs["bmg_placeholder_concentrations"] = True
    df.attrs["ensight_metadata"] = {"channels": {"chA": {}, "chB": {}}}
    return df


@pytest.fixture
def multi_channel_panel(qapp):
    """A DataPanel set up as ``load_file`` would leave it for a 2-channel file."""
    from gui.widgets.data_panel import DataPanel

    panel = DataPanel()
    df = _multi_channel_frame()
    panel._multi_channel_df = df
    panel._channels = ["chA", "chB"]
    panel._source_path = "fake_ensight.csv"
    ms0 = panel._make_ms(panel._slice_channel(df, "chA"), "fake_ensight.csv")
    panel._ms = ms0
    panel._face_values = np.asarray(ms0.concentrations, dtype=np.float64).copy()
    panel._imported_unit = "M"
    panel._populate_channel_combo(df)
    panel._refresh_after_load()
    return panel


class TestChannelCombo:
    """The Channel combo is enabled only for multi-channel data."""

    def test_single_channel_combo_disabled(self, loaded_panel):
        # loaded_panel comes from a plain (no `channel` column) frame.
        assert not loaded_panel._channel_combo.isEnabled()
        assert loaded_panel._channels == []

    def test_multi_channel_combo_enabled_and_lists_channels(self, multi_channel_panel):
        combo = multi_channel_panel._channel_combo
        assert combo.isEnabled()
        assert combo.count() == 2
        assert [combo.itemData(i) for i in range(combo.count())] == ["chA", "chB"]

    def test_switch_channel_adopts_new_signals(self, multi_channel_panel):
        emissions = []
        multi_channel_panel.data_loaded.connect(lambda ms: emissions.append(ms))

        before = multi_channel_panel.measurement_set().signals.copy()
        multi_channel_panel._channel_combo.setCurrentIndex(1)  # → chB

        after = multi_channel_panel.measurement_set().signals
        assert emissions, "switching channel must emit data_loaded"
        assert not np.array_equal(before, after)
        # chB signals are offset by 1000 from chA.
        np.testing.assert_allclose(after, before + 1000.0)

    def test_switch_preserves_entered_concentrations(self, multi_channel_panel):
        # Enter real concentrations on chA (drops the placeholder flag).
        real = np.array([1e-6, 2e-6, 3e-6])
        multi_channel_panel._face_values = real.copy()
        multi_channel_panel._imported_unit = "M"
        multi_channel_panel._push_buffer_to_ms()
        assert not multi_channel_panel.measurement_set().metadata.get(
            "bmg_placeholder_concentrations"
        )

        # Switch to chB — concentrations must carry over, signals must change.
        multi_channel_panel._channel_combo.setCurrentIndex(1)
        ms = multi_channel_panel.measurement_set()
        np.testing.assert_allclose(ms.concentrations, real)
        np.testing.assert_allclose(ms.signals, [[1000, 1001, 1002], [1010, 1011, 1012]])

    def test_switch_while_placeholder_adopts_new_placeholders(self, multi_channel_panel):
        # No real concentrations entered → placeholders persist across switch.
        multi_channel_panel._channel_combo.setCurrentIndex(1)
        ms = multi_channel_panel.measurement_set()
        assert ms.metadata.get("bmg_placeholder_concentrations")
        np.testing.assert_allclose(ms.concentrations, [1.0, 2.0, 3.0])

    def test_combo_tooltip_tracks_selected_channel(self, multi_channel_panel):
        # The full channel label is mirrored into the tooltip so it stays
        # readable when the combo elides at narrow sidebar widths.
        combo = multi_channel_panel._channel_combo
        assert combo.toolTip() == combo.currentText()
        combo.setCurrentIndex(1)
        assert combo.toolTip() == combo.currentText()


class TestEnsightLoadIntegration:
    """End-to-end load of the real EnSight fixture through ``load_file``."""

    def test_load_real_ensight_no_modal_multichannel(self, qapp, qtbot=None):
        if not ENSIGHT_FIXTURE.exists():
            pytest.skip("EnSight fixture missing")
        from gui.widgets.data_panel import DataPanel

        panel = DataPanel()
        emissions = []
        panel.data_loaded.connect(lambda ms: emissions.append(ms))

        # load_file must return without any modal interaction.
        panel.load_file(str(ENSIGHT_FIXTURE))

        assert panel.measurement_set() is not None
        assert len(emissions) == 1
        # tryptamine.csv has three optical channels.
        assert panel._channel_combo.isEnabled()
        assert panel._channel_combo.count() == 3
        # 8 replicas × 12 points per channel.
        ms = panel.measurement_set()
        assert ms.n_replicas == 8
        assert ms.n_points == 12

    def test_switch_channel_resets_via_emit(self, qapp):
        if not ENSIGHT_FIXTURE.exists():
            pytest.skip("EnSight fixture missing")
        from gui.widgets.data_panel import DataPanel

        panel = DataPanel()
        panel.load_file(str(ENSIGHT_FIXTURE))
        emissions = []
        panel.data_loaded.connect(lambda ms: emissions.append(ms))

        first = panel.measurement_set().signals.copy()
        panel._channel_combo.setCurrentIndex(2)  # Fluorescence intensity 1
        assert emissions, "channel switch must re-emit data_loaded"
        assert not np.array_equal(first, panel.measurement_set().signals)


class TestJascoLoadIntegration:
    """JASCO reader metadata must survive the load into MeasurementSet."""

    def test_jasco_metadata_forwarded_to_measurement_set(self, qapp):
        if not JASCO_FIXTURE.exists():
            pytest.skip("JASCO fixture missing")
        from gui.widgets.data_panel import DataPanel

        panel = DataPanel()
        panel.load_file(str(JASCO_FIXTURE))
        ms = panel.measurement_set()
        assert ms is not None
        # The reader attaches jasco_metadata to df.attrs; load_file must
        # forward it into ms.metadata (instrument / Ex-Em / titrant info).
        assert "jasco_metadata" in ms.metadata
        sections = ms.metadata["jasco_metadata"]["sections"]
        assert sections["Measurement Information"]["Ex wavelength"] == "415.0 nm"
