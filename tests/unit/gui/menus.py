"""Opening every menu a window offers, and the rules each one keeps (DESIGN.md §6, *Menu* and *Choice menu*).

A control declares that it opens a menu (``opens_menu``): every dropdown with options,
every menu button and the session switcher. :func:`sweep` clicks each one on screen in
every view of the main window, every side-panel section open, and in the Settings and
Simulation windows, and :func:`problems` says what is wrong with the menu it opened:

- a row's label gets less room than its text takes;
- the card reaches past the window it opens in;
- a choice menu (every row a choice) does not mark exactly one row, the dropdown's
  current one, draws its check mark on another row than that one, or does not open on it.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QEvent, QRectF, Qt
from PyQt6.QtGui import QColor, QFontMetricsF
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QScrollArea, QWidget

from gui.design import components as C
from gui.design.tokens import font


def settle(app: QApplication) -> None:
    """Deliver what the last change posted, and free the widgets it let go."""
    for _ in range(3):
        app.processEvents()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


def openers(window: QWidget) -> list[QWidget]:
    """Every enabled control on screen in *window* that opens a menu."""
    return [
        w
        for w in window.findChildren(QWidget)
        if w.isVisible() and w.isEnabled() and getattr(w, 'opens_menu', False) and w.window() is window
    ]


def _name(opener: QWidget) -> str:
    return opener.accessibleName() or type(opener).__name__


def _accent_pixels(image, rect: QRectF, accent: QColor, tolerance: int = 48) -> int:
    count = 0
    r = rect.toAlignedRect().intersected(image.rect())
    for x in range(r.left(), r.right() + 1):
        for y in range(r.top(), r.bottom() + 1):
            c = QColor(image.pixel(x, y))
            if (
                max(abs(c.red() - accent.red()), abs(c.green() - accent.green()), abs(c.blue() - accent.blue()))
                < tolerance
            ):
                count += 1
    return count


def problems(opener: QWidget, popover: C._Popover) -> list[str]:
    """What is wrong with *popover*, the menu *opener* opened; empty when it keeps every rule."""
    name = _name(opener)
    found: list[str] = []
    window = popover.parentWidget()
    card = popover._card()
    on_window = card.translated(popover.pos().x(), popover.pos().y())
    if not QRectF(window.rect()).contains(on_window):
        found.append(f'{name}: the card {on_window.getRect()} reaches past its window {window.rect().getRect()}')
    rows = popover.menu_rows()
    metrics = QFontMetricsF(font(popover.columns.role))
    for row in rows:
        text = row.action.text()
        need = metrics.horizontalAdvance(text)
        if row.label.width() + 0.5 < need:
            found.append(f'{name}: the row {text!r} gets {row.label.width():.0f} of the {need:.0f} px its label takes')
        if row.label.left() < row.rect.left() or row.label.right() > row.rect.right() + 0.5:
            found.append(f'{name}: the label of {text!r} lies outside its row')
    if rows and all(row.action.isCheckable() for row in rows):
        checked = [i for i, row in enumerate(rows) if row.action.isChecked()]
        current = getattr(opener, 'current', None)
        if len(checked) != 1 or (current is not None and checked != [current]):
            found.append(f'{name}: the choice menu marks rows {checked}, the current choice is {current}')
        elif popover.hover != checked[0]:
            found.append(f'{name}: the choice menu opens on row {popover.hover}, not on its choice {checked[0]}')
        image = popover.grab().toImage()
        accent = popover.t.q('accent')
        for i, row in enumerate(rows):
            if not card.contains(row.check):
                continue  # scrolled out of the card
            marked = _accent_pixels(image, row.check, accent) > 0
            if marked != (i in checked):
                found.append(f'{name}: the row {row.action.text()!r} is {"" if marked else "not "}drawn checked')
    return found


def open_menu(app: QApplication, opener: QWidget) -> C._Popover:
    """Click *opener*, scrolled into view first, and return the menu it opened."""
    area = opener.parentWidget()
    while area is not None and not isinstance(area, QScrollArea):
        area = area.parentWidget()
    if area is not None:
        area.ensureWidgetVisible(opener, 0, 0)
        settle(app)
    before = set(opener.window().findChildren(C._Popover))
    QTest.mouseClick(opener, Qt.MouseButton.LeftButton)
    settle(app)
    opened = [p for p in opener.window().findChildren(C._Popover) if p.isVisible() and p not in before]
    assert len(opened) == 1, f'clicking {_name(opener)} opened {len(opened)} menus'
    return opened[0]


def check_window(app: QApplication, window: QWidget, where: str, seen: dict[str, list[str]]) -> None:
    """Open every menu on screen in *window*, recording what is wrong with each under *where* in *seen*."""
    for opener in openers(window):
        popover = open_menu(app, opener)
        seen[f'{where}: {_name(opener)}'] = problems(opener, popover)
        popover.close_popover()
        settle(app)


def open_sections(window: QWidget) -> None:
    """Open every collapsed side-panel and canvas section in *window*."""
    for header in window.findChildren(C.SectionHeader):
        if header.isVisible() and not header._open:
            header.click()


def sweep(
    app: QApplication, window, seen: dict[str, list[str]] | None = None, check: Callable = check_window
) -> dict[str, list[str]]:
    """Open every menu of every view of the main window *window*, and of its Settings and Simulation windows.

    Returns what is wrong with each menu, keyed by where it opened and by its opener's name.
    *check* ``(app, window, where, seen)`` is what is looked at in each view and window, every
    section open: by default its menus (:func:`check_window`).
    """
    from gui.fitting_session import VIEWS

    seen = {} if seen is None else seen
    window._set_side_visible(True)
    for view in VIEWS:
        window.show_view(view)
        settle(app)
        open_sections(window)
        settle(app)
        check(app, window, view, seen)
    from gui.dialogs.settings_window import SettingsWindow
    from gui.views.simulation import SimulationWindow

    # The windows the main window opens, made off screen first so that opening them shows nothing.
    window._settings_window = SettingsWindow(window._act_check_updates, window)
    window._sim_window = SimulationWindow(window)
    for other in (window._settings_window, window._sim_window):
        other.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    window._open_settings()
    settle(app)
    check(app, window._settings_window, 'Settings', seen)
    window._settings_window.close()
    window._on_simulate()
    settle(app)
    simulation = window._sim_window
    open_sections(simulation)
    settle(app)
    check(app, simulation, 'Simulation', seen)
    simulation.close()
    return seen
