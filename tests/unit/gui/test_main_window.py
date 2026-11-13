"""The window's shell: sessions reached through the switcher, the views through the sidebar, and the theme.

What the window shows of a session comes from its model (tested in
``test_session_model.py``); these tests pin what the shell does with it —
which session and view are on screen, what the commands act on, and that a
command that cannot act says why.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip('PyQt6')

_IDA_DATA = Path(__file__).resolve().parents[3] / 'data' / 'IDA_system.txt'


@pytest.fixture
def window(qapp, monkeypatch):
    from PyQt6.QtCore import Qt

    from gui.main_window import FittingMainWindow

    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    win = FittingMainWindow()
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    win.show()
    qapp.processEvents()
    yield win
    win.close()


@pytest.fixture
def messages(monkeypatch):
    shown: list[tuple] = []
    monkeypatch.setattr('gui.main_window.QMessageBox.information', lambda *args: shown.append(args))
    return shown


def test_the_switcher_lists_every_session_and_choosing_one_puts_it_on_screen(qapp, window):
    from gui.design.components import SessionPopover

    first = window.active_session()
    window._new_session()
    second = window.active_session()
    first.model.set_custom_name('Titration A')

    window._open_switcher()
    (popover,) = window.findChildren(SessionPopover)
    assert [row['name'] for row in popover.sessions] == ['Titration A', 'New session']
    assert popover.current == 1

    popover.session_chosen.emit(0)
    assert window.active_session() is first
    assert window._sidebar.switcher._name == 'Titration A'

    popover.renamed.emit(1, 'Titration B')
    assert second.model.name() == 'Titration B'


def test_the_number_shortcuts_reach_the_sessions_in_order(qapp, window):
    first = window.active_session()
    window._new_session()

    for action in window.actions():
        if action.text() == 'Session 1':
            action.trigger()

    assert window.active_session() is first


def test_the_view_on_screen_is_kept_across_sessions_and_its_selection_holds(qapp, window):
    window.show_view('Ka confidence')
    window._new_session()

    assert window.active_session().current_view() == 'Ka confidence'
    item = window._sidebar.nav['Ka confidence']
    item.click()  # clicking the selected item keeps it selected
    assert item.isChecked() and window.current_view() == 'Ka confidence'
    assert window._toolbar.title.text() == 'Ka confidence'


def test_adding_files_to_a_session_with_data_says_what_to_do_instead(qapp, window, messages, monkeypatch):
    session = window.active_session()
    session._data_panel.load_file(str(_IDA_DATA))
    asked: list = []
    monkeypatch.setattr(type(session), 'load_data', lambda self: asked.append(self))

    window._act_add.trigger()

    assert asked == []
    ((_, title, text),) = messages
    assert title == 'Add files' and 'Replace data…' in text and 'Load data into a new session…' in text


def test_loading_into_a_new_session_and_choosing_no_file_leaves_the_sessions_as_they_were(qapp, window, monkeypatch):
    from gui.fitting_session import FittingSession

    before = window.active_session()
    monkeypatch.setattr(FittingSession, 'load_data', lambda self: None)  # the file dialog was cancelled

    window._act_load_new.trigger()

    assert window.sessions() == [before] and window.active_session() is before


def test_the_side_panel_toggle_hides_the_side_panel_of_every_view(qapp, window):
    window.show_view('Measurements')
    window._new_session()
    assert window._toolbar.side.isEnabled() and window._toolbar.side.isChecked()

    window._toolbar.side.click()

    for session in window.sessions():
        assert all(view.side is None or view.side.isHidden() for view in session._views.values())
    window.show_view('Input uncertainty')  # a view with no side panel offers no toggle
    assert not window._toolbar.side.isEnabled()


def test_the_appearance_resolves_the_one_theme_every_window_holds(qapp):
    from gui.design.appearance import appearance, theme
    from gui.design.tokens import DARK, LIGHT

    source = appearance()
    held = theme()
    try:
        source.set_mode('dark')
        assert held is theme() and held.dark
        assert qapp.palette().window().color().name().lower() == DARK['bg-window'].lower()
        source.set_mode('light')
        assert not held.dark
        assert qapp.palette().window().color().name().lower() == LIGHT['bg-window'].lower()
        with pytest.raises(ValueError):
            source.set_mode('sepia')
    finally:
        source.set_mode('light')
