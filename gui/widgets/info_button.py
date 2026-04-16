"""Reusable round info button that opens a dialog with rich HTML content."""

from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QStyleOptionGroupBox,
    QToolButton,
    QVBoxLayout,
)

_INFO_BUTTON_SIZE = 13


def _info_button_qss(size: int) -> str:
    radius = size // 2
    return f"""
QToolButton {{
    border: 1px solid rgba(0, 0, 0, 0.45);
    border-radius: {radius}px;
    background: rgba(255, 255, 255, 0.92);
    color: rgba(0, 0, 0, 0.75);
    font-family: "Times New Roman", serif;
    font-style: italic;
    font-weight: bold;
    font-size: 11px;
    padding: 0;
    margin: 0;
    min-width: {size}px;
    max-width: {size}px;
    min-height: {size}px;
    max-height: {size}px;
}}
QToolButton:hover {{
    background: rgba(210, 225, 255, 0.95);
    border-color: rgba(0, 50, 150, 0.6);
    color: rgba(0, 30, 120, 0.95);
}}
QToolButton:pressed {{
    background: rgba(180, 200, 240, 0.95);
}}
"""


class InfoButton(QToolButton):
    """Small round info button; click opens a QDialog showing rich HTML."""

    def __init__(self, title: str, html_body: str, parent=None, *, always_enabled: bool = False) -> None:
        super().__init__(parent)
        self._always_enabled = always_enabled
        self.setText('i')
        self.setAutoRaise(False)
        self.setFixedSize(_INFO_BUTTON_SIZE, _INFO_BUTTON_SIZE)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.WhatsThisCursor)
        self.setStyleSheet(_info_button_qss(_INFO_BUTTON_SIZE))
        self._title = title
        self._html = html_body
        self.setToolTip(title or 'Info')
        self.clicked.connect(self._show)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if self._always_enabled and event.type() == QEvent.Type.EnabledChange and not self.isEnabled():
            self.setAttribute(Qt.WidgetAttribute.WA_ForceDisabled, False)
            self.setAttribute(Qt.WidgetAttribute.WA_Disabled, False)
            self.update()

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
    """QGroupBox with an :class:`InfoButton` inline after the title text.

    The button is an absolute child of the group box — not a row in the
    content layout — so it never steals a row.  It repositions itself on
    every resize via :meth:`resizeEvent`, querying the style engine for
    the title text rect so it adapts to font size, text length, and
    platform style.
    """

    def __init__(
        self,
        title: str,
        info_title: str,
        info_html: str,
        parent=None,
    ) -> None:
        super().__init__(title, parent)
        self._info_btn = InfoButton(info_title, info_html, parent=self, always_enabled=True)
        self._info_btn.raise_()
        self._place_info_button()

    def set_info(self, info_title: str, info_html: str) -> None:
        self._info_btn.set_content(info_title, info_html)

    def resizeEvent(self, event) -> None:  # Qt override
        super().resizeEvent(event)
        self._place_info_button()

    def _place_info_button(self) -> None:
        opt = QStyleOptionGroupBox()
        self.initStyleOption(opt)
        title_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_GroupBox,
            opt,
            QStyle.SubControl.SC_GroupBoxLabel,
            self,
        )
        btn = self._info_btn
        x = title_rect.right() + 10
        y = title_rect.center().y() - btn.height() // 2
        btn.move(max(0, x), max(0, y))
