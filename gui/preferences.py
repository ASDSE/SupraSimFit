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

from gui.design.appearance import MODES
from gui.plot_appearance import BUILT_IN, PlotAppearance
from gui.widgets.assay_conditions import UNIT_CHOICES

#: The concentration units a session can be shown in, and the one it starts in by default.
UNITS, DEFAULT_UNIT = UNIT_CHOICES['concentration']

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


#: The window's appearance, one of :data:`gui.design.appearance.MODES`.
APPEARANCE_KEY = 'general/appearance'
#: Whether the app looks for a newer release when it starts.
CHECK_FOR_UPDATES_KEY = 'general/check_for_updates'
#: The concentration unit a new session shows and takes entries in, one of :data:`UNITS`.
CONCENTRATION_UNIT_KEY = 'new_sessions/concentration_unit'
#: Worker processes for long analyses. ``0`` means choose automatically.
WORKER_COUNT_KEY = 'analysis/worker_count'


#: Each stored choice: its key, the choices this version reads, its default as shown, and its name for the user.
_CHOICES = {
    APPEARANCE_KEY: (MODES, 'system', 'System', 'appearance'),
    CONCENTRATION_UNIT_KEY: (UNITS, DEFAULT_UNIT, DEFAULT_UNIT, 'concentration unit for new sessions'),
}


def _choice(key: str) -> str:
    """The choice stored under *key*, else its default; ``ValueError`` for one this version cannot read."""
    choices, default, _shown, name = _CHOICES[key]
    value = str(_settings().value(key, default))
    if value not in choices:
        raise ValueError(f'The stored {name} cannot be read.')
    return value


def reset_unreadable() -> list[str]:
    """Reset each stored choice this version cannot read to its default, and say so, one sentence each.

    Run once as the app starts, so a choice stored by another version is said once
    and never again, and every session after it starts from what is stored.
    """
    said = []
    for key, (_choices, _default, shown, name) in _CHOICES.items():
        try:
            _choice(key)
        except ValueError:
            _settings().remove(key)
            said.append(f'The saved {name} is not available in this version and is now {shown}.')
    appearance, repaired = _stored_plot_appearance()
    if repaired:
        if appearance == BUILT_IN:
            reset_plot_appearance_default()
        else:
            set_plot_appearance_default(appearance)
        said += repaired
    return said


def appearance_mode() -> str:
    """The appearance the app opens in: ``'system'`` unless another was chosen."""
    return _choice(APPEARANCE_KEY)


def set_appearance_mode(mode: str) -> None:
    """Open the app in *mode* from now on."""
    if mode not in MODES:
        raise ValueError(f'unknown appearance mode {mode!r}')
    _settings().setValue(APPEARANCE_KEY, mode)


def check_for_updates() -> bool:
    """Whether the app looks for a newer release when it starts; on unless switched off."""
    return get_bool(CHECK_FOR_UPDATES_KEY, True)


def concentration_unit() -> str:
    """The concentration unit a new session starts in: µM unless another was chosen."""
    return _choice(CONCENTRATION_UNIT_KEY)


def set_concentration_unit(unit: str) -> None:
    """Start every new session in *unit*."""
    if unit not in UNITS:
        raise ValueError(f'unknown concentration unit {unit!r}')
    _settings().setValue(CONCENTRATION_UNIT_KEY, unit)


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


def worker_choices() -> list[int]:
    """The processor-core counts offered: ``0`` (automatic), then one up to the machine's cores.

    A count stored beyond the machine's cores stays among them, so it is shown as it is.
    """
    import os

    top = max(os.cpu_count() or 1, get_int(WORKER_COUNT_KEY, 0))
    return list(range(top + 1))


#: The plot appearance new sessions start from, as a JSON record of :class:`~gui.plot_appearance.PlotAppearance`.
PLOT_APPEARANCE_KEY = 'new_sessions/plot_appearance'


def plot_appearance_default() -> PlotAppearance:
    """The plot appearance new sessions start from: the one stored, else the built-in one.

    A choice this version does not offer is the built-in one; :func:`reset_unreadable`
    stores that repair and says so as the app starts.
    """
    return _stored_plot_appearance()[0]


def _stored_plot_appearance() -> tuple[PlotAppearance, list[str]]:
    """The stored plot appearance, each choice this version does not offer put back to the built-in
    one, and one sentence for the user per choice put back."""
    stored = _settings().value(PLOT_APPEARANCE_KEY, None)
    if stored is None:
        return BUILT_IN, []
    try:
        record = json.loads(str(stored))
    except json.JSONDecodeError:
        record = None
    if not isinstance(record, dict):
        return BUILT_IN, ['The saved plot appearance for new sessions could not be read and is now the built-in one.']
    appearance, put_back = PlotAppearance.salvage(record)
    return appearance, [
        f'The {what.removeprefix("the ")} saved for new sessions is not available in this version and is now {shown}.'
        for what, shown in put_back
    ]


def set_plot_appearance_default(appearance: PlotAppearance) -> None:
    """Store *appearance* as the one new sessions start from."""
    _settings().setValue(PLOT_APPEARANCE_KEY, json.dumps(appearance.to_dict()))


def reset_plot_appearance_default() -> None:
    """Let new sessions start from the built-in plot appearance again."""
    _settings().remove(PLOT_APPEARANCE_KEY)
