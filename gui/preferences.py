"""Thin wrapper around :class:`QSettings` for persistent user preferences.

``QSettings`` stores values per-user in the platform-appropriate
location (``~/Library/Preferences`` on macOS, the registry on Windows,
``~/.config`` on Linux). The organisation and application names are
set by :func:`gui.main_window.launch` before the ``QApplication`` is
created, so reading or writing a preference anywhere after that is a
one-liner.
"""

from __future__ import annotations

import json

from PyQt6.QtCore import QCoreApplication, QSettings

from gui.plot_appearance import BUILT_IN, PlotAppearance

ORG_NAME = 'SupraSimFit'
APP_NAME = 'SupraSimFit'


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


#: Worker processes for long analyses. ``0`` means choose automatically.
WORKER_COUNT_KEY = 'analysis/worker_count'


def get_int(key: str, default: int = 0) -> int:
    """Return an integer preference, falling back to *default*."""
    value = _settings().value(key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def set_int(key: str, value: int) -> None:
    """Persist an integer preference."""
    _settings().setValue(key, int(value))


def worker_count() -> int:
    """Worker processes to run an analysis with.

    A stored value of ``0`` — the default — means let the machine decide, which
    leaves one core free for the interface. ``1`` runs everything in the
    application process.
    """
    from core.pipeline.sensitivity import default_worker_count

    stored = get_int(WORKER_COUNT_KEY, 0)
    return stored if stored >= 1 else default_worker_count()


#: The plot appearance new sessions start from, as a JSON record of :class:`~gui.plot_appearance.PlotAppearance`.
PLOT_APPEARANCE_KEY = 'new_sessions/plot_appearance'


def plot_appearance_default() -> PlotAppearance:
    """The plot appearance new sessions start from: the one stored, else the built-in one.

    Raises ``ValueError``, in words for the user, when the stored record cannot be read.
    """
    stored = _settings().value(PLOT_APPEARANCE_KEY, None)
    if stored is None:
        return BUILT_IN
    unreadable = 'The plot appearance stored for new sessions cannot be read.'
    try:
        return PlotAppearance.from_dict(json.loads(str(stored)))
    except json.JSONDecodeError:
        raise ValueError(unreadable) from None
    except ValueError as exc:
        raise ValueError(f'{unreadable} {exc}') from None


def set_plot_appearance_default(appearance: PlotAppearance) -> None:
    """Store *appearance* as the one new sessions start from."""
    _settings().setValue(PLOT_APPEARANCE_KEY, json.dumps(appearance.to_dict()))


def reset_plot_appearance_default() -> None:
    """Let new sessions start from the built-in plot appearance again."""
    _settings().remove(PLOT_APPEARANCE_KEY)
