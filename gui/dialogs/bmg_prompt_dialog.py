"""Dialog shown whenever a BMG plate-reader export is loaded.

BMG XLSX files do not carry concentration values — the reader assigns
placeholder positions ``1..N`` and flags the MeasurementSet. This dialog
surfaces that fact and offers two choices:

* **Enter concentrations now** — opens
  :class:`~gui.dialogs.concentration_dialog.ConcentrationDialog` immediately.
* **Later** — closes; the user can open the concentration dialog later
  via the Data panel, and :meth:`FittingSession.run_fit` will gate the
  fit with an error if they forget.

The dialog is shown on every BMG import; there is no opt-out. The
notification is important enough (and the corresponding fit-time block
severe enough) that hiding it would trade clarity for a minor
convenience.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
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
        The user chose **Later** (or dismissed the dialog).
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
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        intro = QLabel(
            f'<p><b>Loaded {n_replicas} replicas × {n_points} '
            f'measurement points</b> from<br>'
            f'<code>{filename}</code>.</p>'
            f'<p>BMG plate exports do <b>not</b> contain concentration '
            f'values. The reader has assigned placeholder positions '
            f'<b>1 through {n_points}</b> so each column is distinguishable.</p>'
            f'<p>You must enter the real concentration vector before a '
            f'fit can run — <b>fits are blocked</b> while placeholders '
            f'are in place. Click <i>Enter concentrations…</i> to open '
            f'the editor now, or dismiss this dialog and use '
            f'<i>Data → Concentration Vector</i> later.</p>'
        )
        intro.setTextFormat(Qt.TextFormat.RichText)
        intro.setWordWrap(True)
        layout.addWidget(intro)

        buttons = QDialogButtonBox(self)
        self._enter_btn = QPushButton('Enter concentrations…', self)
        self._enter_btn.setDefault(True)
        self._later_btn = QPushButton('Later', self)
        buttons.addButton(self._enter_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(self._later_btn, QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
