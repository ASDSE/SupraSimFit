"""The help dialog the views open from their help links."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QScrollArea, QVBoxLayout

from gui.design.tokens import SIZE, space


def show_help(parent, title: str, html_body: str) -> None:
    """Show *html_body* in a modal dialog titled *title* over *parent*, scrolled, with a Close button."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setMinimumSize(SIZE['help-width'], SIZE['help-height'])

    layout = QVBoxLayout(dlg)

    label = QLabel(html_body)
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setOpenExternalLinks(True)
    label.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse
    )
    label.setMargin(space(3))
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
