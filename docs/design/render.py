"""Render a view of the running app: the real :class:`FittingMainWindow`, drawn off screen.

A visual check looks at what the app itself draws, opened menus included. The window
runs under the platform's own style and platform plugin (on macOS, real font metrics),
never shown on screen, with the update check off; Demo IDA supplies the data. Every
render starts from a new window, so one render never sees another's state.

Run from the repository root::

    uv run python -m docs.design.render Measurements out.png
    uv run python -m docs.design.render "Fit results" out.png --theme dark --state demo-loaded
    uv run python -m docs.design.render Measurements out.png --menu "Display unit of the titration plot"

The command line reads and writes a settings store of its own that starts empty, so a
render shows the built-in preferences whatever the user's are. The states:

- ``empty`` — a new session;
- ``demo-loaded`` — Demo IDA's data and settings, before the fit;
- ``demo-fitted`` — Demo IDA's fit finished, and the Ka profile the session works out
  after every fit finished too.

*open_menu* names the control whose menu is opened, by its accessible name; the menu
is a child of the window, so it is in the image.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from unittest import mock

from PyQt6.QtCore import QCoreApplication, QEvent, QEventLoop, QLocale, QSettings, Qt, QThread
from PyQt6.QtGui import QImage
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget

from gui.design.appearance import appearance
from gui.fitting_session import VIEWS
from gui.main_window import FittingMainWindow

STATES = ('empty', 'demo-loaded', 'demo-fitted')
THEMES = ('light', 'dark')
#: The longest a render waits for the demo's fit and Ka profile, in seconds.
TIMEOUT = 600


def render(
    view: str,
    *,
    theme: str = 'light',
    state: str = 'demo-fitted',
    open_menu: str | None = None,
    size: tuple[int, int] = (1440, 900),
) -> QImage:
    """The image of *view* in a new main window of *size*, in *theme*, at *state*, with *open_menu* open.

    Needs a running :class:`QApplication`. A message box the app raises on the way
    is not shown; what it says is raised as a :class:`RuntimeError`.
    """
    if view not in VIEWS:
        raise ValueError(f'unknown view {view!r}; the views are {", ".join(VIEWS)}')
    if state not in STATES:
        raise ValueError(f'unknown state {state!r}; the states are {", ".join(STATES)}')
    if theme not in THEMES:
        raise ValueError(f'unknown theme {theme!r}; the themes are {", ".join(THEMES)}')
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        raise RuntimeError('render() needs a running QApplication')

    said: list[str] = []

    def say(_parent, title, text, *_args, **_kwargs):
        said.append(f'{title}: {text}')
        return QMessageBox.StandardButton.Ok

    def check() -> None:
        if said:
            raise RuntimeError('The app said: ' + ' | '.join(said))

    previous = appearance().mode
    appearance().set_mode(theme)
    with (
        mock.patch.object(FittingMainWindow, '_run_update_check', lambda self, silent: None),
        mock.patch.multiple(QMessageBox, warning=say, information=say, critical=say, question=say),
    ):
        window = FittingMainWindow()
        try:
            window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
            window.resize(*size)
            window.show()
            _settle(app)
            check()
            model = window.active_session().model
            if state == 'demo-loaded':
                window.active_session().set_up_demo_ida()
            elif state == 'demo-fitted':
                window.active_session().load_demo_ida()
                check()
                deadline = time.monotonic() + TIMEOUT
                while model.running():
                    if time.monotonic() > deadline:
                        raise TimeoutError(f'The demo fit and its Ka profile did not finish within {TIMEOUT} s')
                    app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
                    QThread.msleep(10)
            check()
            window.show_view(view)
            _settle(app)
            if open_menu is not None:
                _open_menu(app, window, open_menu)
            check()
            return window.grab().toImage()
        finally:
            window.close()
            window.deleteLater()
            QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
            appearance().set_mode(previous)


def _settle(app: QApplication) -> None:
    """Deliver the events a change posted, so layouts and plots are drawn as they settle."""
    deadline = time.monotonic() + 0.1
    while time.monotonic() < deadline:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)


def _open_menu(app: QApplication, window: QWidget, name: str) -> None:
    """Click the one control on screen named *name*, and check that a menu opened over the window."""
    shown = [w for w in window.findChildren(QWidget) if w.isVisible() and w.accessibleName()]
    matches = [w for w in shown if w.accessibleName() == name]
    if len(matches) != 1:
        names = '; '.join(sorted({w.accessibleName() for w in shown}))
        raise ValueError(f'{len(matches)} controls on screen are named {name!r}; the named ones are: {names}')
    before = {w for w in window.children() if isinstance(w, QWidget) and w.isVisible()}
    QTest.mouseClick(matches[0], Qt.MouseButton.LeftButton)
    _settle(app)
    if not any(isinstance(w, QWidget) and w.isVisible() and w not in before for w in window.children()):
        raise ValueError(f'clicking {name!r} opened no menu')


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('view', choices=VIEWS)
    parser.add_argument('out', help='the image file to write (.png)')
    parser.add_argument('--theme', choices=THEMES, default='light')
    parser.add_argument('--state', choices=STATES, default='demo-fitted')
    parser.add_argument('--menu', help='the accessible name of the control whose menu to open')
    args = parser.parse_args(argv)

    QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
    with tempfile.TemporaryDirectory() as store:
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, store)
        QCoreApplication.setOrganizationName('SupraSimFit-Render')
        QCoreApplication.setApplicationName('render')
        _app = QApplication(sys.argv[:1])  # held for the whole render
        image = render(args.view, theme=args.theme, state=args.state, open_menu=args.menu)
        if not image.save(args.out):
            sys.exit(f'Could not write {args.out}.')


if __name__ == '__main__':
    main()
