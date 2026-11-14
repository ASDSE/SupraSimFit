"""The Settings window stores each choice as it is made, and the app reads it from there."""

from __future__ import annotations

import pytest

pytest.importorskip('PyQt6')

from PyQt6.QtCore import QSettings, Qt  # noqa: E402
from PyQt6.QtGui import QAction  # noqa: E402

from gui import preferences  # noqa: E402
from gui.design.appearance import appearance  # noqa: E402


@pytest.fixture
def window(qapp):
    from gui.dialogs.settings_window import SettingsWindow

    QSettings().clear()
    mode = appearance().mode
    action = QAction('Check for updates…')
    w = SettingsWindow(action)
    w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    w.show()
    yield w, action
    w.close()
    appearance().set_mode(mode)
    QSettings().clear()


def test_an_appearance_chosen_reaches_the_app_and_is_kept_for_the_next_start(window):
    w, _ = window
    w.mode._choose(2)  # Dark
    assert appearance().mode == 'dark'
    assert appearance().theme.dark
    assert preferences.appearance_mode() == 'dark'
    # The page is drawn again in the new theme; its controls still answer.
    w.mode._choose(1)
    assert appearance().mode == 'light' and preferences.appearance_mode() == 'light'


def test_a_concentration_unit_chosen_is_where_a_new_session_starts(window):
    from gui.session_model import SessionModel

    w, _ = window
    w.unit._choose(2)  # mM
    assert preferences.concentration_unit() == 'mM'
    model = SessionModel()
    assert model.settings.display_unit == 'mM'
    units = model.binding.condition_units()
    assert {units[k] for k in model.binding.concentration_keys()} == {'mM'}


def test_the_processor_cores_chosen_are_what_an_analysis_runs_on(window):
    w, _ = window
    w.cores.chosen.emit(w.worker_counts.index(1))
    assert preferences.worker_count() == 1
    w.cores.chosen.emit(0)
    assert preferences.get_int(preferences.WORKER_COUNT_KEY, -1) == 0
    assert preferences.worker_count() >= 1  # automatic: the machine decides


def test_use_built_in_style_clears_the_stored_plot_appearance(window):
    from dataclasses import replace

    from gui.plot_appearance import BUILT_IN

    w, _ = window
    assert not w.use_built_in.isEnabled()  # nothing stored: already the built-in style
    preferences.set_plot_appearance_default(replace(BUILT_IN, text_size='large'))
    w.hide()
    w.show()  # the window reads the stored appearance again as it opens
    assert w.use_built_in.isEnabled()
    w.use_built_in.click()
    assert QSettings().value(preferences.PLOT_APPEARANCE_KEY) is None
    assert preferences.plot_appearance_default() == BUILT_IN
    assert not w.use_built_in.isEnabled()


def test_an_unreadable_stored_appearance_can_be_cleared(window):
    w, _ = window
    QSettings().setValue(preferences.PLOT_APPEARANCE_KEY, '{not json')
    w.hide()
    w.show()
    assert 'cannot be read' in w.appearance_note.text()
    w.use_built_in.click()
    assert QSettings().value(preferences.PLOT_APPEARANCE_KEY) is None


def test_check_now_runs_the_apps_update_check_and_follows_it(window):
    w, action = window
    fired = []
    action.triggered.connect(lambda: fired.append(True))
    w.check_now.click()
    assert fired == [True]
    action.setEnabled(False)  # a check is running
    assert not w.check_now.isEnabled()
    action.setEnabled(True)
    assert w.check_now.isEnabled()


def test_the_startup_check_runs_only_while_switched_on(qapp, monkeypatch):
    """The toggle is what the main window reads as it opens; the network is stood in for."""
    from gui.update_check import UpdateCheckWorker

    started = []

    class _Check(UpdateCheckWorker):
        def start(self, *args):
            started.append(self)

    monkeypatch.setattr('gui.main_window.UpdateCheckWorker', _Check)
    from gui.main_window import FittingMainWindow

    QSettings().clear()
    FittingMainWindow().close()
    assert len(started) == 1
    preferences.set_bool(preferences.CHECK_FOR_UPDATES_KEY, False)
    FittingMainWindow().close()
    assert len(started) == 1
    QSettings().clear()


def test_a_stored_choice_this_version_cannot_read_is_reset_and_said(qapp):
    QSettings().clear()
    QSettings().setValue(preferences.APPEARANCE_KEY, 'sepia')
    QSettings().setValue(preferences.CONCENTRATION_UNIT_KEY, 'pM')
    with pytest.raises(ValueError, match='appearance'):
        preferences.appearance_mode()
    said = preferences.reset_unreadable()
    assert said == [
        'The stored appearance could not be read and was reset to System.',
        'The stored concentration unit for new sessions could not be read and was reset to µM.',
    ]
    assert (preferences.appearance_mode(), preferences.concentration_unit()) == ('system', 'µM')
    assert preferences.reset_unreadable() == []
    QSettings().clear()
