"""Flat/minimal tab widget behaviour (``gui/widgets/flat_tabs.py``).

Behavioural contracts for the shared ``FlatTabWidget``: the inline "+" lives
after the last tab (not in a corner) and invokes its callback, and the bar can
never be emptied. Visual fidelity (colours, underline) is checked by eye against
the spec, not asserted here.
"""

import pytest

pytest.importorskip('PyQt6')

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTabBar, QWidget

from gui.widgets.flat_tabs import FlatTabBar, FlatTabWidget


def test_flat_config(qapp):
    tabs = FlatTabWidget()
    assert tabs.objectName() == 'flatTabs'
    assert tabs.documentMode()
    assert isinstance(tabs.tabBar(), FlatTabBar)
    assert not tabs.tabBar().expanding()  # left-aligned, not stretched
    assert not tabs.tabBar().drawBase()  # no platform base line


def test_inline_add_button_after_last_tab_and_calls_back(qapp):
    calls = []
    tabs = FlatTabWidget(add_callback=lambda: calls.append(1))
    tabs.addTab(QWidget(), 'A')
    tabs.addTab(QWidget(), 'B')
    tabs.resize(400, 80)
    tabs.show()
    qapp.processEvents()
    try:
        # Inline, not a corner widget (spec §5.1): the "+" is a child of the bar.
        assert tabs.cornerWidget(Qt.Corner.TopRightCorner) is None
        btn = tabs.tabBar()._add_button
        assert btn is not None and btn.parent() is tabs.tabBar()
        # Glued to the right of the last tab.
        assert btn.x() >= tabs.tabBar().tabRect(tabs.count() - 1).right()
        # Clicking runs the callback (the app wires this to "new session").
        btn.click()
        assert calls == [1]
    finally:
        tabs.close()


def _close_button(bar, i):
    for side in (QTabBar.ButtonPosition.LeftSide, QTabBar.ButtonPosition.RightSide):
        b = bar.tabButton(i, side)
        if b is not None:
            return b
    return None


def test_never_zero_tabs_hides_the_sole_close_button(qapp):
    tabs = FlatTabWidget(closable=True)
    tabs.addTab(QWidget(), 'only')
    tabs.show()
    qapp.processEvents()
    try:
        bar = tabs.tabBar()
        # Sole tab: its close control is hidden so it cannot be closed to empty.
        assert not _close_button(bar, 0).isVisible()
        # With a second tab, both close controls are shown again.
        tabs.addTab(QWidget(), 'second')
        qapp.processEvents()
        assert _close_button(bar, 0).isVisible()
        assert _close_button(bar, 1).isVisible()
    finally:
        tabs.close()


def test_plot_style_widget_has_no_add_button_and_is_fixed(qapp):
    # The plot tabs (Fit Curve / Distributions) are fixed: no "+", not closable,
    # not movable.
    tabs = FlatTabWidget(white_pane=True)
    tabs.addTab(QWidget(), 'Fit Curve')
    tabs.addTab(QWidget(), 'Distributions')
    assert tabs.tabBar()._add_button is None
    assert not tabs.tabsClosable()
    assert not tabs.isMovable()
