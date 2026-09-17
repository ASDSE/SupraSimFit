"""The update check is started, reported and seen out without losing the session.

The check runs on its own thread and reports on the interface thread, which can
be busy long enough for a second check to start first. Destroying a running
``QThread`` aborts the process, so what these tests pin is which worker each
report lets go of, that quitting never waits on the check without a limit, and
that the menu item says what it is doing. The network is stood in for by a
worker that reports when the test lets it.
"""

from __future__ import annotations

import time

import pytest

pytest.importorskip('PyQt6')

from PyQt6.QtCore import QEvent  # noqa: E402

from gui.update_check import UpdateCheckWorker  # noqa: E402


class _ScriptedCheck(UpdateCheckWorker):
    """An update check that reports an error when the test releases it."""

    #: Every check built, in the order they were started.
    made: list['_ScriptedCheck'] = []

    def __init__(self, parent=None):
        super().__init__(parent)
        self.released = False
        _ScriptedCheck.made.append(self)

    def run(self) -> None:
        while not self.released:
            time.sleep(0.005)
        self.error.emit('offline')


@pytest.fixture
def checks(monkeypatch):
    """Replace the real check with the scripted one and hand back the list it fills."""
    _ScriptedCheck.made = []
    monkeypatch.setattr('gui.main_window.UpdateCheckWorker', _ScriptedCheck)
    return _ScriptedCheck.made


@pytest.fixture
def dialogs(monkeypatch):
    """Record the window's dialogs instead of blocking on them."""
    shown: list[tuple] = []
    monkeypatch.setattr('gui.main_window.QMessageBox.information', lambda *args: shown.append(args))
    monkeypatch.setattr('gui.main_window.QMessageBox.warning', lambda *args: shown.append(args))
    return shown


def _settle(qapp) -> None:
    for _ in range(3):
        qapp.processEvents()
        qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _window():
    from gui.main_window import FittingMainWindow

    return FittingMainWindow()


def test_a_finished_check_lets_go_of_itself_and_not_of_the_check_that_replaced_it(qapp, checks, dialogs):
    """The startup check reports after a second check has started: deleting that one would abort the app."""
    window = _window()
    startup = checks[0]
    startup.released = True
    startup.wait()  # its report is queued behind whatever the interface thread is doing

    window._act_check_updates.trigger()  # the user asks for a check in that moment
    second = checks[1]
    qapp.processEvents()  # the startup check's report arrives now

    assert window._update_worker is second
    assert second.isRunning()  # the running check was left alone
    _settle(qapp)
    with pytest.raises(RuntimeError):
        startup.isRunning()  # the check that reported is the one that was deleted

    second.released = True
    window.close()
    _settle(qapp)


def test_asking_for_a_check_while_one_is_running_says_so(qapp, checks, dialogs):
    """The startup check leaves the menu item enabled, and an unmet precondition is never passed over in silence."""
    window = _window()
    startup = checks[0]

    window._act_check_updates.trigger()

    assert len(checks) == 1  # no second check was started
    assert window._update_worker is startup
    assert dialogs[-1][1] == 'Already checking'
    assert 'already running' in dialogs[-1][2]

    startup.released = True
    window.close()
    _settle(qapp)


def test_quitting_does_not_wait_on_the_check_without_a_limit(qapp, monkeypatch, checks, dialogs):
    """A name lookup the socket timeout does not cover would otherwise freeze the window on quit."""
    from gui import workers

    monkeypatch.setattr(workers, '_RETIRE_WAIT_MS', 200)
    window = _window()
    check = checks[0]  # never released: it stands for a check that hangs

    started = time.monotonic()
    window.close()
    blocked = time.monotonic() - started

    assert blocked < 2.0
    assert check.isRunning()  # held, not destroyed: destroying it would abort the app
    assert check in workers._RUNNING_ON

    check.released = True
    check.wait()
    _settle(qapp)
    assert check not in workers._RUNNING_ON
