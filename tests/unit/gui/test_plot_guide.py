"""Help ▸ Reading the plots: each entry point opens the window's one non-modal guide at the right section."""

from __future__ import annotations

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


def _show(qapp, widget):
    from PyQt6.QtCore import Qt

    widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    widget.show()
    qapp.processEvents()
    return widget


def test_the_guide_lists_a_section_named_after_each_plot_tab_and_the_summary_panel(qapp, guide_off_screen):
    """Section titles follow the tab labels, so a renamed tab cannot leave its guide section behind."""
    from gui.fitting_session import FittingSession
    from gui.plot_guide import PLOT_GUIDE

    tabs = FittingSession()._plot_tabs
    guide = guide_off_screen()
    listed = [guide._nav.item(row).text() for row in range(guide._nav.count())]

    assert listed == [tabs.tabText(i) for i in range(tabs.count())] + ['Summary panel']
    for row, key in enumerate(PLOT_GUIDE):
        guide._nav.setCurrentRow(row)
        assert guide.current_section() == key
        assert guide._text.toPlainText().startswith(listed[row])


def test_help_menu_opens_one_non_modal_guide(qapp, monkeypatch, guide_off_screen):
    """Help ▸ Reading the plots… shows the guide beside the window; choosing it again raises the same one."""
    from PyQt6.QtCore import Qt

    from gui.main_window import FittingMainWindow

    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    window = _show(qapp, FittingMainWindow())
    (help_menu,) = [action.menu() for action in window.menuBar().actions() if action.text() == '&Help']
    (reading,) = [action for action in help_menu.actions() if action.text() == 'Reading the plots…']

    reading.trigger()
    reading.trigger()
    qapp.processEvents()

    (guide,) = window.findChildren(guide_off_screen)
    assert guide.isVisible()
    assert guide.windowModality() is Qt.WindowModality.NonModal


def test_tab_bar_button_opens_the_section_of_the_tab_on_screen(qapp, guide_off_screen):
    """The "?" on the plot tab bar opens the guide at the current tab's section, for every tab."""
    from PyQt6.QtCore import Qt

    from gui import plot_guide
    from gui.fitting_session import FittingSession

    session = FittingSession()
    session.resize(1200, 800)
    _show(qapp, session)
    tabs = session._plot_tabs
    button = tabs.cornerWidget(Qt.Corner.TopRightCorner)
    assert button.isVisible() and '?' in button.text()

    expected = {
        session._sensitivity_widget: plot_guide.SENSITIVITY,
        session._plot_widget: plot_guide.FIT_CURVE,
        session._identifiability_widget: plot_guide.IDENTIFIABILITY,
        session._distribution_widget: plot_guide.DISTRIBUTIONS,
    }
    for page, key in expected.items():
        tabs.setCurrentWidget(page)
        button.click()
        qapp.processEvents()
        (guide,) = session.findChildren(guide_off_screen)
        assert guide.isVisible()
        assert guide.current_section() == key
        assert guide._text.toPlainText().startswith(plot_guide.PLOT_GUIDE[key][0])
