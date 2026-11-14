"""Help ▸ Reading the plots: a non-modal guide with one section per view that has a plot.

The sections are listed as navigation items on the sidebar surface, each with the icon of
its view; the section chosen is shown on the canvas surface, its title in ``title`` and its
text in ``body`` at a reading measure. Everything is drawn from the theme, so the guide
follows a change of appearance like every other window.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QButtonGroup, QDialog, QScrollArea, QWidget

from gui.design import components as C
from gui.design.appearance import theme
from gui.design.tokens import SIZE, space
from gui.plot_guide import PLOT_GUIDE

#: The icon of the Simulation window's section; the session's views take their sidebar icons.
SIMULATION_ICON = 'scatter'


class PlotGuideDialog(QDialog):
    """The guide's sections listed on the left, the chosen one on the right.

    Non-modal, so the plot it describes stays in view and usable beside it.
    :func:`show_plot_guide` keeps one guide per window.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from gui.fitting_session import NAVIGATION  # the session imports this module

        self.setWindowTitle('Reading the plots')
        self.setModal(False)
        t = theme()
        view_icons = {view: icon for _group, items in NAVIGATION for view, icon in items}

        self._items: dict[str, C.NavItem] = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        nav = C.vbox(spacing=1, margins=(4, 5, 4, 4))
        for title in PLOT_GUIDE:
            item = C.NavItem(t, title, view_icons.get(title, SIMULATION_ICON))
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
        self._current = ''
        self.show_section(next(iter(PLOT_GUIDE)))

    def current_section(self) -> str:
        """The section on show, a key of :data:`gui.plot_guide.PLOT_GUIDE`."""
        return self._current

    def show_section(self, key: str) -> None:
        """Show the section *key* of :data:`gui.plot_guide.PLOT_GUIDE`."""
        self._current = key
        self._items[key].setChecked(True)
        self._title.setText(key)
        self._text.setText(PLOT_GUIDE[key])
        self._scroll.verticalScrollBar().setValue(0)


def show_plot_guide(parent: QWidget, view: str | None = None) -> PlotGuideDialog:
    """Bring up the guide of *parent*'s window, at the section of *view* where it has one, and return it.

    The window keeps one guide: a second call raises the open one rather than opening another.
    """
    window = parent.window()
    guide = window.findChild(PlotGuideDialog)
    if guide is None:
        guide = PlotGuideDialog(window)
    if view in PLOT_GUIDE:
        guide.show_section(view)
    guide.show()
    guide.raise_()
    guide.activateWindow()
    return guide
