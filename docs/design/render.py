"""Render a view of the running app: the real :class:`FittingMainWindow`, drawn off screen.

A visual check looks at what the app itself draws, opened menus included. The
application is set up as the app ships it (:func:`gui.main_window.start_application`:
locale, Fusion style, icon) on the platform's own plugin (on macOS, real font metrics);
the window is never shown on screen, and the update check is off; Demo IDA supplies the
data. Every render starts from a new window, so one render never sees another's state.

Run from the repository root::

    uv run python -m docs.design.render Measurements out.png
    uv run python -m docs.design.render "Fit results" out.png --theme dark --state demo-loaded
    uv run python -m docs.design.render Measurements out.png --menu "Display unit of the titration plot"
    uv run python -m docs.design.render "Ka confidence" out.png --pointer 0.65,0.5

The command line reads and writes a settings store of its own that starts empty, so a
render shows the built-in preferences whatever the user's are. The states:

- ``empty`` — a new session;
- ``demo-loaded`` — Demo IDA's data and settings, before the fit;
- ``demo-fitted`` — Demo IDA's fit finished, and the Ka profile the session works out
  after every fit finished too;
- ``demo-heatmap`` — that, and a heatmap of the sensitivity analysis over the first two
  inputs Demo IDA states uncertain, on the coarsest grid.

*open_menu* names the control whose menu is opened, by its accessible name; the menu
is a child of the window, so it is in the image. *pointer* puts the pointer over the
first plot on screen, the topmost then leftmost: ``(across, down)`` as fractions of its
plot area from the top-left corner, so a readout reads the values under it.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from unittest import mock

import pyqtgraph as pg
from PyQt6.QtCore import QCoreApplication, QEvent, QEventLoop, QPoint, QPointF, QSettings, Qt, QThread
from PyQt6.QtGui import QImage, QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget

from core.pipeline.sensitivity import SensitivityMode
from gui.design.appearance import appearance
from gui.fitting_session import VIEWS
from gui.main_window import FittingMainWindow, start_application

STATES = ('empty', 'demo-loaded', 'demo-fitted', 'demo-heatmap')
THEMES = ('light', 'dark')
#: The longest a render waits for the demo's fit, its Ka profile and a heatmap, in seconds.
TIMEOUT = 600


def render(
    view: str,
    *,
    theme: str = 'light',
    state: str = 'demo-fitted',
    open_menu: str | None = None,
    pointer: tuple[float, float] | None = None,
    size: tuple[int, int] = (1440, 900),
) -> QImage:
    """The image of *view* in a new main window of *size*, in *theme*, at *state*, with *open_menu* open
    and the pointer at *pointer* over the first plot on screen.

    The running application is set up as the app ships it first. A message box the
    app raises on the way is not shown; what it says is raised as a :class:`RuntimeError`.
    """
    if view not in VIEWS:
        raise ValueError(f'unknown view {view!r}; the views are {", ".join(VIEWS)}')
    if state not in STATES:
        raise ValueError(f'unknown state {state!r}; the states are {", ".join(STATES)}')
    if theme not in THEMES:
        raise ValueError(f'unknown theme {theme!r}; the themes are {", ".join(THEMES)}')
    app = start_application(sys.argv[:1])

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
            elif state in ('demo-fitted', 'demo-heatmap'):
                window.active_session().load_demo_ida()
                check()
                _wait(app, model)
                if state == 'demo-heatmap':
                    model.analysis.mode = SensitivityMode.HEATMAP
                    model.analysis_edited()
                    refusal = model.run_sensitivity(model.analysis_config())
                    if refusal is not None:
                        raise RuntimeError(f'The heatmap could not start: {refusal.message}')
                    _wait(app, model)
            check()
            window.show_view(view)
            _settle(app)
            if open_menu is not None:
                _open_menu(app, window, open_menu)
            if pointer is not None:
                _point_at(app, window, *pointer)
            check()
            return window.grab().toImage()
        finally:
            window.close()
            window.deleteLater()
            QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
            appearance().set_mode(previous)


def _wait(app: QApplication, model) -> None:
    """Deliver events until the session's running work is done."""
    deadline = time.monotonic() + TIMEOUT
    while model.running():
        if time.monotonic() > deadline:
            raise TimeoutError(f"The demo's {model.running_work() or 'work'} did not finish within {TIMEOUT} s")
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        QThread.msleep(10)


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


def _point_at(app: QApplication, window: QWidget, across: float, down: float) -> None:
    """Move the pointer to (*across*, *down*) of the plot area of the first plot on screen, as a mouse move does."""
    plots = [w for w in window.findChildren(pg.PlotWidget) if w.isVisible()]
    if not plots:
        raise ValueError('no plot is on screen to point at')
    plot = min(plots, key=lambda w: (w.mapTo(window, QPoint(0, 0)).y(), w.mapTo(window, QPoint(0, 0)).x()))
    area = plot.getPlotItem().getViewBox().sceneBoundingRect()
    at = plot.mapFromScene(QPointF(area.left() + across * area.width(), area.top() + down * area.height()))
    viewport = plot.viewport()
    move = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(at),
        QPointF(viewport.mapToGlobal(at)),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(viewport, move)
    deadline = time.monotonic() + 0.5  # a plot's readout follows the pointer through a short-delayed signal proxy
    while time.monotonic() < deadline:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)


def _pointer(text: str) -> tuple[float, float]:
    try:
        across, down = (float(part) for part in text.split(','))
    except ValueError:
        raise argparse.ArgumentTypeError(f'{text!r} is not two fractions such as 0.65,0.5') from None
    if not (0 <= across <= 1 and 0 <= down <= 1):
        raise argparse.ArgumentTypeError(f'{text!r} is not inside the plot area: both fractions run from 0 to 1')
    return across, down


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('view', choices=VIEWS)
    parser.add_argument('out', help='the image file to write (.png)')
    parser.add_argument('--theme', choices=THEMES, default='light')
    parser.add_argument('--state', choices=STATES, default='demo-fitted')
    parser.add_argument('--menu', help='the accessible name of the control whose menu to open')
    parser.add_argument(
        '--pointer', type=_pointer, help='across,down: where over the first plot on screen the pointer rests (0 to 1)'
    )
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as store:
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, store)
        QCoreApplication.setOrganizationName('SupraSimFit-Render')
        QCoreApplication.setApplicationName('render')
        _app = start_application(sys.argv[:1])  # held for the whole render
        image = render(args.view, theme=args.theme, state=args.state, open_menu=args.menu, pointer=args.pointer)
        if not image.save(args.out):
            sys.exit(f'Could not write {args.out}.')


if __name__ == '__main__':
    main()
