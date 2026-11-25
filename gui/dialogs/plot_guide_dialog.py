"""Help ▸ Reading the plots: a non-modal guide with one section per plot tab and one for the summary panel."""

from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QHBoxLayout, QListWidget, QTextBrowser, QWidget

from gui.plot_guide import DEMO_NOTE, PLOT_GUIDE
from gui.plotting.colors import HAIRLINE, INK, INK_2, SERIES, SURFACE

_NAV_QSS = f"""
QListWidget {{ border: none; outline: 0; background: {SURFACE}; color: {INK}; font-size: 14px; }}
QListWidget::item {{ padding: 7px 10px; border-left: 3px solid transparent; }}
QListWidget::item:selected {{ background: #e8eef7; color: {INK}; border-left: 3px solid {SERIES}; }}
"""
_TEXT_QSS = f'QTextBrowser {{ border: none; border-left: 1px solid {HAIRLINE}; background: {SURFACE}; }}'
_DOCUMENT_CSS = f"""
body {{ color: {INK}; font-size: 14px; }}
h2 {{ color: {INK}; }}
p.demo {{ color: {INK_2}; }}
"""


class PlotGuideDialog(QDialog):
    """The guide's sections listed on the left, the selected one on the right.

    Non-modal, so the plot it describes stays in view and usable beside it.
    :func:`show_plot_guide` keeps one guide per window.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle('Reading the plots')
        self.setModal(False)
        self.setStyleSheet(f'QDialog {{ background: {SURFACE}; }}')
        self.resize(900, 720)
        self._keys = list(PLOT_GUIDE)

        self._nav = QListWidget()
        self._nav.setStyleSheet(_NAV_QSS)
        self._nav.addItems([title for title, _ in PLOT_GUIDE.values()])
        self._nav.setFixedWidth(self._nav.sizeHintForColumn(0) + 40)

        self._text = QTextBrowser()
        self._text.setStyleSheet(_TEXT_QSS)
        self._text.document().setDefaultStyleSheet(_DOCUMENT_CSS)
        self._text.document().setDocumentMargin(16)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._nav)
        layout.addWidget(self._text, stretch=1)

        self._nav.currentRowChanged.connect(self._show_row)
        self._nav.setCurrentRow(0)

    def current_section(self) -> str:
        """Key of the section on show, a key of :data:`gui.plot_guide.PLOT_GUIDE`."""
        return self._keys[self._nav.currentRow()]

    def show_section(self, key: str) -> None:
        """Show the section *key* of :data:`gui.plot_guide.PLOT_GUIDE`."""
        self._nav.setCurrentRow(self._keys.index(key))

    def _show_row(self, row: int) -> None:
        title, body = PLOT_GUIDE[self._keys[row]]
        self._text.setHtml(f'<h2>{title}</h2><p class="demo">{DEMO_NOTE}</p>{body}')


def show_plot_guide(parent: QWidget, section: str | None = None) -> PlotGuideDialog:
    """Bring up the guide of *parent*'s window, at *section* when given, and return it.

    The window keeps one guide: a second call raises the open one rather than
    opening another.
    """
    window = parent.window()
    guide = window.findChild(PlotGuideDialog)
    if guide is None:
        guide = PlotGuideDialog(window)
    if section is not None:
        guide.show_section(section)
    guide.show()
    guide.raise_()
    guide.activateWindow()
    return guide
