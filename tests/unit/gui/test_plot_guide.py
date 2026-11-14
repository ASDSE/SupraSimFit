"""Help ▸ Reading the plots: each entry point opens the window's one non-modal guide at the right section,
and the guide describes the views and columns the app draws."""

from __future__ import annotations

import re

import pytest

pytest.importorskip('PyQt6')


@pytest.fixture
def guide_off_screen(monkeypatch):
    """Guides created during the test lay out and count as shown, but never appear on screen."""
    from PyQt6.QtCore import Qt

    from gui.dialogs.plot_guide_dialog import PlotGuideDialog

    create = PlotGuideDialog.__init__

    def create_off_screen(self, *args, **kwargs):
        create(self, *args, **kwargs)
        self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)

    monkeypatch.setattr(PlotGuideDialog, '__init__', create_off_screen)
    return PlotGuideDialog


@pytest.fixture
def window(qapp, monkeypatch):
    from PyQt6.QtCore import Qt

    from gui.main_window import FittingMainWindow

    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    w = FittingMainWindow()
    w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    w.show()
    qapp.processEvents()
    yield w
    w.close()


def test_the_guide_has_a_section_for_each_view_with_a_plot_and_the_simulation_window():
    from gui.fitting_session import VIEWS
    from gui.plot_guide import PLOT_GUIDE

    assert list(PLOT_GUIDE) == [v for v in VIEWS if v not in ('Binding model', 'Input uncertainty')] + ['Simulation']


def test_help_menu_opens_one_non_modal_guide(qapp, window, guide_off_screen):
    """Help ▸ Reading the plots… shows the guide beside the window; choosing it again raises the same one."""
    from PyQt6.QtCore import Qt

    (help_menu,) = [action.menu() for action in window.menuBar().actions() if action.text() == '&Help']
    (reading,) = [action for action in help_menu.actions() if action.text() == 'Reading the plots…']

    reading.trigger()
    reading.trigger()
    qapp.processEvents()

    (guide,) = window.findChildren(guide_off_screen)
    assert guide.isVisible()
    assert guide.windowModality() is Qt.WindowModality.NonModal


def test_toolbar_help_opens_the_section_of_the_view_on_screen(qapp, window, guide_off_screen):
    """A view with a plot opens its own section; a view without one leaves the guide where it was."""
    from gui.fitting_session import VIEWS
    from gui.plot_guide import PLOT_GUIDE

    for view in VIEWS:
        window.show_view(view)
        window._toolbar.help.click()
        qapp.processEvents()
        (guide,) = window.findChildren(guide_off_screen)
        if view in PLOT_GUIDE:
            assert guide.current_section() == view
            assert guide._title.text() == view and guide._text.text() == PLOT_GUIDE[view]
            assert guide._items[view].isChecked()
        else:
            assert guide.current_section() in PLOT_GUIDE


def test_the_sensitivity_section_names_every_column_and_closing_row_of_the_budget():
    """The reader looks a number up by the name on screen; a column renamed in the view fails here."""
    from gui.plot_guide import PLOT_GUIDE
    from gui.sensitivity import ALL_SOURCES, BUDGET_COLUMNS, INTERACTIONS

    text = re.sub(r'\s+', ' ', PLOT_GUIDE['Sensitivity'])
    for name in [*BUDGET_COLUMNS[1:], INTERACTIONS, ALL_SOURCES]:
        assert f'<i>{name.split(" (")[0]}</i>' in text, name
