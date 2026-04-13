"""Reusable round info button that opens a dialog with rich HTML content."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
)

_INFO_BUTTON_SIZE = 18

_INFO_BUTTON_QSS = """
QToolButton {
    border: 1px solid rgba(0, 0, 0, 0.45);
    border-radius: 9px;
    background: rgba(255, 255, 255, 0.92);
    color: rgba(0, 0, 0, 0.75);
    font-family: "Times New Roman", serif;
    font-style: italic;
    font-weight: bold;
    font-size: 11px;
    padding: 0;
    margin: 0;
    min-width: 18px;
    max-width: 18px;
    min-height: 18px;
    max-height: 18px;
}
QToolButton:hover {
    background: rgba(210, 225, 255, 0.95);
    border-color: rgba(0, 50, 150, 0.6);
    color: rgba(0, 30, 120, 0.95);
}
QToolButton:pressed {
    background: rgba(180, 200, 240, 0.95);
}
"""


class InfoButton(QToolButton):
    """Small round info button; click opens a QDialog showing rich HTML."""

    def __init__(self, title: str, html_body: str, parent=None) -> None:
        super().__init__(parent)
        self.setText('i')
        self.setAutoRaise(False)
        self.setFixedSize(_INFO_BUTTON_SIZE, _INFO_BUTTON_SIZE)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.WhatsThisCursor)
        self.setStyleSheet(_INFO_BUTTON_QSS)
        self._title = title
        self._html = html_body
        self.setToolTip(title or 'Info')
        self.clicked.connect(self._show)

    def set_content(self, title: str, html_body: str) -> None:
        self._title = title
        self._html = html_body
        self.setToolTip(title or 'Info')

    def _show(self) -> None:
        dlg = QDialog(self.window())
        dlg.setWindowTitle(self._title or 'Info')
        dlg.setMinimumSize(560, 420)

        layout = QVBoxLayout(dlg)

        label = QLabel(self._html)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setOpenExternalLinks(True)
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        label.setMargin(8)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        scroll = QScrollArea()
        scroll.setWidget(label)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dlg.reject)
        buttons.accepted.connect(dlg.accept)
        layout.addWidget(buttons)

        dlg.exec()


class InfoGroupBox(QGroupBox):
    """QGroupBox whose title bar hosts an :class:`InfoButton` on the right.

    The button is an absolute child of the group box — not a row in the
    content layout — so it never steals a row and repositions itself on
    every resize via :meth:`resizeEvent`.
    """

    _RIGHT_MARGIN = 8
    _TOP_MARGIN = 2

    def __init__(
        self,
        title: str,
        info_title: str,
        info_html: str,
        parent=None,
    ) -> None:
        super().__init__(title, parent)
        self._info_btn = InfoButton(info_title, info_html, parent=self)
        self._info_btn.raise_()
        self._place_info_button()

    def set_info(self, info_title: str, info_html: str) -> None:
        self._info_btn.set_content(info_title, info_html)

    def resizeEvent(self, event) -> None:  # Qt override
        super().resizeEvent(event)
        self._place_info_button()

    def _place_info_button(self) -> None:
        btn = self._info_btn
        x = self.width() - btn.width() - self._RIGHT_MARGIN
        btn.move(max(0, x), self._TOP_MARGIN)
