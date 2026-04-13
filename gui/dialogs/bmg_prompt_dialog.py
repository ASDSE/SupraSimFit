"""Dialog shown the first time a BMG plate-reader export is loaded.

BMG XLSX files do not carry concentration values — the reader assigns
placeholder positions ``1..N`` and sets a flag on the MeasurementSet.
This dialog surfaces that fact and gives the user three choices:

* **Enter concentrations now** &mdash; opens
  :class:`~gui.dialogs.concentration_dialog.ConcentrationDialog` immediately.
* **Skip for now** &mdash; closes; the user can open the concentration
  dialog later via the Data panel, and :meth:`FittingSession.run_fit`
  will gate the fit with an error if they forget.
* **Don't show this again** checkbox &mdash; persists via
  :mod:`gui.preferences` so the prompt stays out of the way on
  subsequent BMG imports. (The fit-time guard still runs regardless.)
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class BMGConcentrationPromptDialog(QDialog):
    """Notification dialog for BMG imports with placeholder concentrations.

    Result codes
    ------------
    :class:`QDialog.DialogCode.Accepted`
        The user chose **Enter concentrations now** — the caller should
        open :class:`~gui.dialogs.concentration_dialog.ConcentrationDialog`.
    :class:`QDialog.DialogCode.Rejected`
        The user chose **Skip for now** (or closed the dialog).
    """

    def __init__(
        self,
        *,
        filename: str,
        n_replicas: int,
        n_points: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle('BMG Plate Reader Import')
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        intro = QLabel(
            f'<p>Loaded <b>{n_replicas} replicas &times; {n_points} '
            f'measurement points</b> from<br><code>{filename}</code>.</p>'
            '<p>BMG plate exports do not include concentration values. '
            'Placeholder positions <b>1&hellip;{n}</b> have been assigned.</p>'
            '<p>Enter the real concentration vector before running a fit.</p>'
            .format(n=n_points)
        )
        intro.setTextFormat(Qt.TextFormat.RichText)
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._skip_again_cb = QCheckBox("Don't show this again")
        self._skip_again_cb.setToolTip(
            'Hide this dialog on future BMG imports. The fit will still '
            'refuse to run until real concentrations are supplied.'
        )
        layout.addWidget(self._skip_again_cb)

        buttons = QDialogButtonBox(self)
        self._enter_btn = QPushButton('Enter concentrations\u2026', self)
        self._enter_btn.setDefault(True)
        self._skip_btn = QPushButton('Skip for now', self)
        buttons.addButton(self._enter_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(self._skip_btn, QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def skip_future_prompts(self) -> bool:
        """Return True if the user ticked *Don't show this again*."""
        return self._skip_again_cb.isChecked()
