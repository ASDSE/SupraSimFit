"""Thin wrapper around :class:`QSettings` for persistent user preferences.

The codebase previously had no persistent preferences mechanism; this
module introduces one in a deliberately small, opinionated way.

``QSettings`` stores values per-user in the platform-appropriate
location (``~/Library/Preferences`` on macOS, the registry on Windows,
``~/.config`` on Linux). The organisation and application names are
set by :func:`gui.main_window.launch` before the ``QApplication`` is
created, so reading or writing a preference anywhere after that is a
one-liner.
"""

from __future__ import annotations

from PyQt6.QtCore import QCoreApplication, QSettings

ORG_NAME = 'SupraSimFit'
APP_NAME = 'fitting_app'


def _settings() -> QSettings:
    """Return a QSettings bound to the currently running application.

    Uses ``QSettings()`` with no arguments so it picks up the org /
    application name set via :meth:`QCoreApplication.setOrganizationName`
    and :meth:`QCoreApplication.setApplicationName`. This means tests
    can redirect preferences into an isolated location simply by
    setting a different application name + storage path before import.
    """
    # Fall back to the built-in names if nothing has set them yet —
    # covers unit-test contexts that touch preferences before calling
    # ``launch()``.
    if not QCoreApplication.organizationName():
        QCoreApplication.setOrganizationName(ORG_NAME)
    if not QCoreApplication.applicationName():
        QCoreApplication.setApplicationName(APP_NAME)
    return QSettings()


def get_bool(key: str, default: bool = False) -> bool:
    """Return a boolean preference, falling back to *default*."""
    value = _settings().value(key, default)
    # QSettings may return 'true' / 'false' strings on some backends
    if isinstance(value, str):
        return value.strip().lower() in {'true', '1', 'yes', 'on'}
    return bool(value)


def set_bool(key: str, value: bool) -> None:
    """Persist a boolean preference."""
    _settings().setValue(key, bool(value))
