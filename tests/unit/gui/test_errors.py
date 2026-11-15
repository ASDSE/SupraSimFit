"""The interface's exception boundary: an error no slot catches is logged and said to the user once."""

from __future__ import annotations

import logging
import sys

import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMessageBox, QWidget


class _Emitter(QObject):
    poked = pyqtSignal()


@pytest.fixture
def boundary(qapp, monkeypatch, tmp_path):
    """The hook installed on a window, with a log folder of the test's own; the process's own hook and logging come back after."""
    from gui import errors

    monkeypatch.setattr(sys, 'excepthook', sys.excepthook)
    monkeypatch.setattr(errors, '_log_file', None)
    root = logging.getLogger()
    handlers = list(root.handlers)
    said: list[tuple[str, str]] = []

    def warning(_parent, title, text, *args, **kwargs):
        said.append((title, text))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, 'warning', warning)
    window = QWidget()
    log_file = errors.install_exception_hook(window, tmp_path / 'logs')
    yield log_file, said
    for handler in root.handlers[:]:
        if handler not in handlers:
            root.removeHandler(handler)
            handler.close()
    window.deleteLater()


def test_a_slot_that_raises_is_said_once_and_logged(qapp, boundary):
    """A burst of the same error is one warning in plain words naming the log, and every one of them is in the log."""
    log_file, said = boundary
    emitter = _Emitter()

    def refresh():
        raise RuntimeError('operands could not be broadcast in refresh')

    emitter.poked.connect(refresh)
    for _ in range(3):
        emitter.poked.emit()
    qapp.processEvents()

    assert len(said) == 1
    _title, text = said[0]
    assert str(log_file) in text
    assert 'broadcast' not in text and 'Traceback' not in text and 'RuntimeError' not in text
    logged = log_file.read_text(encoding='utf-8')
    assert logged.count('RuntimeError: operands could not be broadcast in refresh') == 3
    assert 'in refresh' in logged and 'Traceback' in logged

    # The session stays usable: a later error is said again.
    emitter.poked.emit()
    qapp.processEvents()
    assert len(said) == 2


def test_an_error_while_the_warning_is_open_is_logged_without_a_second_dialog(qapp, monkeypatch, boundary):
    """Errors raised while the warning waits for the user (its own event loop runs) do not stack dialogs."""
    log_file, said = boundary
    emitter = _Emitter()

    def refresh():
        raise ValueError('stale fit')

    emitter.poked.connect(refresh)
    shown = QMessageBox.warning

    def warning_that_lets_events_run(parent, title, text, *args, **kwargs):
        emitter.poked.emit()  # a repaint behind the open dialog raises again
        qapp.processEvents()
        return shown(parent, title, text)

    monkeypatch.setattr(QMessageBox, 'warning', warning_that_lets_events_run)
    emitter.poked.emit()
    qapp.processEvents()
    qapp.processEvents()

    assert len(said) == 1
    assert log_file.read_text(encoding='utf-8').count('ValueError: stale fit') == 2


def test_a_worker_failure_names_the_step_and_the_log(qapp, monkeypatch, boundary):
    """An unexpected fit failure says the fit stopped and where its details are, without the exception text."""
    from core.assays import IDAAssay
    from core.pipeline.fit_pipeline import FitConfig
    from gui import workers

    log_file, _said = boundary

    def fail(*args, **kwargs):
        raise ZeroDivisionError('float division by zero in _solve')

    monkeypatch.setattr(workers, 'fit_measurement_set', fail)
    worker = workers.FitWorker(None, IDAAssay, {}, FitConfig())
    messages: list[str] = []
    worker.error.connect(messages.append)
    worker.run()

    (message,) = messages
    assert message.startswith('The fit stopped on an unexpected error')
    assert str(log_file) in message and '_solve' not in message
    assert 'ZeroDivisionError: float division by zero in _solve' in log_file.read_text(encoding='utf-8')
