"""The batch-export dialog's remembered file prefix."""

from __future__ import annotations

from PyQt6.QtCore import QSettings

from gui.dialogs import export_multiple_dialog as module
from gui.fitting_session import FittingSession


def test_export_prefix_is_reused_only_for_the_same_dataset(qapp, monkeypatch, tmp_path):
    """A new experiment must not inherit another experiment's custom export name."""
    monkeypatch.setattr(
        module, '_settings', lambda: QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    )
    first = FittingSession()
    first._state.source_file = str(tmp_path / 'host_A.csv')
    dialog = module.ExportMultipleDialog(first)
    dialog._base_edit.setText('host_A_reviewed')
    dialog._save_settings()
    assert module.ExportMultipleDialog(first)._base_edit.text() == 'host_A_reviewed'
    second = FittingSession()
    second._state.source_file = str(tmp_path / 'host_B.csv')
    assert module.ExportMultipleDialog(second)._base_edit.text() == 'host_B'
    first.close()
    second.close()
