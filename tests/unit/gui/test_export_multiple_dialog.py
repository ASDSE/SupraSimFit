"""The batch-export dialog's remembered file prefix."""

from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QSettings

from core.data_processing.measurement_set import MeasurementSet
from gui.dialogs import export_multiple_dialog as module
from gui.fitting_session import FittingSession


def _data() -> MeasurementSet:
    return MeasurementSet(concentrations=np.arange(1.0, 4.0), signals=np.ones((1, 3)), replica_ids=('a',))


def test_export_prefix_is_reused_only_for_the_same_dataset(qapp, monkeypatch, tmp_path):
    """A new experiment must not inherit another experiment's custom export name."""
    monkeypatch.setattr(
        module, '_settings', lambda: QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    )
    first = FittingSession()
    first.model.load(_data(), str(tmp_path / 'host_A.csv'))
    dialog = module.ExportMultipleDialog(first)
    dialog.base.set_text('host_A_reviewed')
    dialog._save_settings()
    assert module.ExportMultipleDialog(first).base.editor.text() == 'host_A_reviewed'
    second = FittingSession()
    second.model.load(_data(), str(tmp_path / 'host_B.csv'))
    assert module.ExportMultipleDialog(second).base.editor.text() == 'host_B'
    first.close()
    second.close()
