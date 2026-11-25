"""Application preferences: settings that apply beyond a single session."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)

from core.pipeline.sensitivity import default_worker_count
from gui import preferences
from gui.widgets.numeric_inputs import NoScrollSpinBox

_AUTOMATIC = 0


class PreferencesDialog(QDialog):
    """Edit the preferences that persist between sessions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Preferences')

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._workers = NoScrollSpinBox()
        self._workers.setRange(_AUTOMATIC, 256)
        self._workers.setSpecialValueText(f'Automatic ({default_worker_count()})')
        self._workers.setValue(preferences.get_int(preferences.WORKER_COUNT_KEY, _AUTOMATIC))
        self._workers.setToolTip('How many analyses run side by side. 1 runs them one at a time.')
        form.addRow('Processor cores to use:', self._workers)
        layout.addLayout(form)

        note = QLabel(
            'A sensitivity analysis re-fits your data many times. Using more cores finishes '
            'sooner; leaving one free keeps the window responsive while it runs. The result is '
            'the same either way.'
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:
        """Persist the edited preferences."""
        preferences.set_int(preferences.WORKER_COUNT_KEY, self._workers.value())
        super().accept()
