"""The interface's exception boundary: an error nothing caught is logged and said to the user once.

PyQt hands an exception no slot caught to :data:`sys.excepthook`. The hook
installed here writes its traceback to the app's log file and shows one warning
in plain words that names that file; the window stays open and usable. The
workers write the failures they cannot name to the same log
(:func:`unexpected`), so every message that points to the log is true.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PyQt6.QtCore import QObject, QStandardPaths, Qt, pyqtSignal
from PyQt6.QtWidgets import QMessageBox, QWidget

from gui.preferences import APP_NAME

logger = logging.getLogger(__name__)

LOG_NAME = f'{APP_NAME}.log'
#: The log is kept to two files of this size: the present one and the one before it.
_LOG_BYTES = 1_000_000

#: The log file the hook writes to, once it is installed.
_log_file: Path | None = None


def log_dir() -> Path:
    """Where the platform keeps the app's logs: ``~/Library/Logs/<app>`` on macOS, the app's data folder elsewhere."""
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Logs' / APP_NAME
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)) / 'logs'


def unexpected(what: str) -> str:
    """*what* stopped on an unexpected error, in a message that says where its details are and what to do."""
    where = (
        f'The details are in the log file {_log_file}.'
        if _log_file is not None
        else 'The details were written to the terminal.'
    )
    return f'{what} {where} If it happens again, send that file to the developer with your data.'


class _Boundary(QObject):
    """Logs every error it is handed, and says them on the interface thread, one warning per burst."""

    raised = pyqtSignal()

    def __init__(self, window: QWidget):
        super().__init__()
        self._window = window
        self._pending = False
        # Queued, so the warning opens on the interface thread once the slot that raised has
        # returned, and the errors of one burst — or of the repaints behind the open
        # warning — make one dialog.
        self.raised.connect(self._say, Qt.ConnectionType.QueuedConnection)

    def hook(self, kind, value, tb) -> None:
        logger.error('Unexpected error', exc_info=(kind, value, tb))
        if not self._pending:
            self._pending = True
            self.raised.emit()

    def _say(self) -> None:
        try:
            QMessageBox.warning(
                self._window,
                'Something went wrong',
                unexpected(
                    'An action stopped on an unexpected error, so part of the window may not show your last change.'
                    ' The session stays open and you can carry on.'
                ),
            )
        finally:
            self._pending = False


def install_exception_hook(window: QWidget, log_dir: Path) -> Path:
    """Log every error nothing caught to a file in *log_dir* and say it over *window*; returns the log file.

    Installed after pyqtgraph is imported, which puts a hook of its own in
    :data:`sys.excepthook` that only prints.
    """
    global _log_file
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / LOG_NAME
    handler = RotatingFileHandler(path, maxBytes=_LOG_BYTES, backupCount=1, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(name)s %(levelname)s %(message)s'))
    root = logging.getLogger()
    root.addHandler(handler)
    if sys.stderr is not None:  # a packaged app has no terminal
        root.addHandler(logging.StreamHandler())
    _log_file = path
    sys.excepthook = _Boundary(window).hook
    return path
