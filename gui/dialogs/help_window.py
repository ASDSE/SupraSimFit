"""The Help window: one non-modal window per main window, a section per view.

The sections are listed as navigation items on the sidebar surface, each with the icon of
its view; the section chosen is shown on the canvas surface, its title in ``title`` and its
text in ``body`` at a reading measure, a topic of it in ``body-strong`` with room above it.
The Binding model section describes the model of the session on screen
(:meth:`HelpWindow.set_assay`). Everything is drawn from the theme, so the window follows a
change of appearance like every other window.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QButtonGroup, QDialog, QScrollArea, QWidget

from core.assays.registry import AssayType
from gui.design import components as C
from gui.design.appearance import theme
from gui.design.tokens import SIZE, TYPE, space
from gui.help import SECTIONS, section_html


def _topic_style() -> str:
    """The style of a topic paragraph: the ``body-strong`` role, with a step of room above it."""
    px, weight, _tabular = TYPE['body-strong']
    return f'<style>p.topic {{ font-size: {px}px; font-weight: {weight.value}; margin-top: {space(6)}px; }}</style>'


class HelpWindow(QDialog):
    """The sections listed on the left, the chosen one on the right.

    Non-modal, so the view it describes stays in view and usable beside it. The main
    window keeps one and raises it at a section (:meth:`gui.main_window.FittingMainWindow.open_help`).
    """

    def __init__(self, assay_type: AssayType, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from gui.fitting_session import NAVIGATION  # the session's module imports the main window's

        self.setWindowTitle('Help')
        self.setModal(False)
        t = theme()
        view_icons = {view: icon for _group, items in NAVIGATION for view, icon in items}

        self._items: dict[str, C.NavItem] = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        nav = C.vbox(spacing=1, margins=(4, 5, 4, 4))
        for title in SECTIONS:
            item = C.NavItem(t, title, view_icons[title])
            item.clicked.connect(lambda _checked=False, key=title: self.show_section(key))
            group.addButton(item)
            nav.addWidget(item)
            self._items[title] = item
        nav.addStretch(1)
        sidebar = QWidget()
        sidebar.setObjectName('Sidebar')
        sidebar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        sidebar.setFixedWidth(SIZE['sidebar'])
        sidebar.setLayout(nav)

        self._title = C.label('', 'title')
        self._text = C.wrapped('', 'body', None, rich=True)
        self._text.setMaximumWidth(SIZE['measure'])
        self._text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        page = QWidget()
        page.setObjectName('Canvas')
        page.setLayout(C.vbox(self._title, 3, self._text, None, spacing=0, margins=(7, 6, 7, 7)))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        self._scroll = scroll
        canvas = QWidget()
        canvas.setObjectName('Canvas')
        canvas.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        canvas.setLayout(C.vbox(scroll, spacing=0))

        self.setLayout(C.hbox(sidebar, C.hairline(vertical=True), canvas, spacing=0))
        self.resize(SIZE['sidebar'] + SIZE['measure'] + 2 * space(7) + space(4), SIZE['measure'] + SIZE['toolbar'])
        self._assay_type = assay_type
        self._current = ''
        self.show_section(SECTIONS[0])

    def current_section(self) -> str:
        """The section on show, a name in :data:`gui.help.SECTIONS`."""
        return self._current

    def show_section(self, section: str) -> None:
        """Show *section*, a name in :data:`gui.help.SECTIONS`, from its top."""
        self._current = section
        self._items[section].setChecked(True)
        self._title.setText(section)
        self._text.setText(_topic_style() + section_html(section, self._assay_type))
        self._scroll.verticalScrollBar().setValue(0)

    def set_assay(self, assay_type: AssayType) -> None:
        """Describe *assay_type* in the Binding model section, at once where that section is on show."""
        if assay_type is not self._assay_type:
            self._assay_type = assay_type
            if self._current == 'Binding model':
                self._text.setText(_topic_style() + section_html(self._current, assay_type))
