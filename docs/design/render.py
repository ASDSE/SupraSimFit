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
    uv run python -m docs.design.render Simulation out.png
    uv run python -m docs.design.render Help out.png --section "Binding model"
    uv run python -m docs.design.render --all docs/design/screens
    uv run python -m docs.design.render --all docs/design/screens --only switcher --theme dark

*view* is a view of the main window, or one of the windows it opens (``Settings``,
``Simulation``, ``Help``), drawn at its own size; *section* is the Help window's section
on show, by default the one of the view on screen. ``--all`` writes the reference screens of the
design (:data:`SCREENS`) as ``<name>_<light|dark>.jpg`` at :data:`SCALE` × the window's
size, each in a process of its own; ``--only`` and ``--theme`` narrow it.

The command line reads and writes a settings store of its own that starts empty, so a
render shows the built-in preferences whatever the user's are, with the analysis pinned to
:data:`WORKERS` processor cores. A sensitivity analysis runs at Fixed seed :data:`SEED`, so
every render of a state draws the same samples. The states:

- ``empty`` — a new session;
- ``demo-loaded`` — Demo IDA's data and settings, before the fit;
- ``demo-fitted`` — Demo IDA's fit finished, and the Ka profile the session works out
  after every fit finished too;
- ``demo-sensitivity`` — that, and the sensitivity analysis the session opens on (Sobol'
  indices, the smallest sample size) at Fixed seed :data:`SEED`;
- ``demo-heatmap`` — that fit, and a heatmap of the sensitivity analysis over the first
  two inputs Demo IDA states uncertain, on the coarsest grid, at Fixed seed :data:`SEED`.

*open_menu* names the control whose menu is opened, by its accessible name; the menu
is a child of the window, so it is in the image. *pointer* puts the pointer over the
first plot on screen, the topmost then leftmost: ``(across, down)`` as fractions of its
plot area from the top-left corner, so a readout reads the values under it.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

import pyqtgraph as pg
from PyQt6.QtCore import QCoreApplication, QEvent, QEventLoop, QPoint, QPointF, QSettings, Qt, QThread
from PyQt6.QtGui import QImage, QMouseEvent, QPixmap
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox, QScrollArea, QWidget

from core.pipeline.sensitivity import SensitivityMode
from gui import preferences
from gui.design import components as C
from gui.design.appearance import appearance
from gui.fitting_session import _DEMO_IDA_PATH, VIEWS
from gui.help import SECTIONS
from gui.main_window import FittingMainWindow, start_application

#: The windows the main window opens, drawn at their own size.
WINDOWS = ('Settings', 'Simulation', 'Help')
STATES = ('empty', 'demo-loaded', 'demo-fitted', 'demo-sensitivity', 'demo-heatmap')
THEMES = ('light', 'dark')
#: The longest a render waits for the demo's fit, its Ka profile and a sensitivity analysis, in seconds.
TIMEOUT = 600
#: Device pixels per logical pixel of a reference screen.
SCALE = 1.5
JPEG_QUALITY = 80
#: How many reference screens are rendered at once, each in a process of its own.
PROCESSES = 4
#: The Fixed seed of every sensitivity analysis a render runs: the seed of the Help window's example.
SEED = 0
#: The processor cores the command line's analyses run on, whatever the machine has.
WORKERS = 2


def render(
    view: str,
    *,
    theme: str = 'light',
    state: str = 'demo-fitted',
    open_menu: str | None = None,
    pointer: tuple[float, float] | None = None,
    prepare: Callable[[QWidget], None] | None = None,
    section: str | None = None,
    size: tuple[int, int] = (1440, 900),
    scale: float = 1.0,
) -> QImage:
    """The image of *view* in a new main window of *size*, in *theme*, at *state*, with *open_menu* open
    and the pointer at *pointer* over the first plot on screen, at *scale* device pixels per logical pixel.

    *view* is a view of the main window or one of :data:`WINDOWS`, opened by the main
    window's own command and drawn at its own size; the Help window opens at *section*, or
    else at the view on screen. *prepare* is called with the window drawn once it shows
    *view*, before the menu opens. The running application is set up
    as the app ships it first. A message box the app raises on the way is not shown; what
    it says is raised as a :class:`RuntimeError`.
    """
    if view not in VIEWS + WINDOWS:
        raise ValueError(f'unknown view {view!r}; the views are {", ".join(VIEWS + WINDOWS)}')
    if state not in STATES:
        raise ValueError(f'unknown state {state!r}; the states are {", ".join(STATES)}')
    if theme not in THEMES:
        raise ValueError(f'unknown theme {theme!r}; the themes are {", ".join(THEMES)}')
    if section is not None and (view != 'Help' or section not in SECTIONS):
        raise ValueError(f'a section is one of {", ".join(SECTIONS)}, and only the Help window shows one')
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
            elif state in ('demo-fitted', 'demo-sensitivity', 'demo-heatmap'):
                window.active_session().load_demo_ida()
                check()
                _wait(app, model)
                if state != 'demo-fitted':
                    model.analysis.fixed_seed, model.analysis.seed_text = True, str(SEED)
                    if state == 'demo-heatmap':
                        model.analysis.mode = SensitivityMode.HEATMAP
                    model.analysis_edited()
                    refusal = model.run_sensitivity(model.analysis_config())
                    if refusal is not None:
                        raise RuntimeError(f'The sensitivity analysis could not start: {refusal.message}')
                    _wait(app, model)
            check()
            target = window
            if view in WINDOWS:
                target = _open_window(window, view, section)
            else:
                window.show_view(view)
            _settle(app)
            if prepare is not None:
                prepare(target)
                _settle(app)
            if open_menu is not None:
                _open_menu(app, target, open_menu)
            if pointer is not None:
                _point_at(app, target, *pointer)
            check()
            return _snapshot(target, scale)
        finally:
            for other in (window._settings_window, window._sim_window, window._help):
                if other is not None:
                    other.close()
            window.close()
            window.deleteLater()
            QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
            appearance().set_mode(previous)


def _open_window(window: FittingMainWindow, name: str, section: str | None = None) -> QWidget:
    """Open the window *name* with the main window's own command, made off screen first so that nothing shows;
    the Help window at *section*, else at the view on screen."""
    from gui.dialogs.settings_window import SettingsWindow

    if name == 'Settings':
        window._settings_window = other = SettingsWindow(window._act_check_updates, window)
        command = window._act_settings
    elif name == 'Simulation':
        other = window._simulation_window()
        command = window._act_simulate
    else:
        other = window._help_window()
        command = window._act_help
    other.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    command.trigger()
    if section is not None:
        window.open_help(section)
    return other


def _snapshot(widget: QWidget, scale: float) -> QImage:
    """*widget* and the children over it, drawn at *scale* device pixels per logical pixel."""
    pixmap = QPixmap(widget.size() * scale)
    pixmap.setDevicePixelRatio(scale)
    pixmap.fill(widget.palette().window().color())
    widget.render(pixmap)
    return pixmap.toImage()


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


# ----------------------------------------------------------------------
# The reference screens
# ----------------------------------------------------------------------


def _more_sessions(window: FittingMainWindow) -> None:
    """Open a copy of the session on screen (its data, not fitted) and a new session, then show the first again."""
    window._act_duplicate.trigger()
    window._act_new.trigger()
    window._switch_to(window.sessions()[0])


def _overlay_demo(simulation: QWidget) -> None:
    """Lay Demo IDA's file over the simulation through *Overlay data…*, its file dialog answered with that file."""
    with mock.patch('gui.views.simulation.QFileDialog.getOpenFileName', return_value=(str(_DEMO_IDA_PATH), '')):
        simulation.overlay_data()


def _settings_at_end(window: QWidget) -> None:
    """Open every section of the side panel and scroll it to its end."""
    for header in window.findChildren(C.SectionHeader):
        if header.isVisible():
            header.set_open(True)
    QApplication.processEvents()
    for area in window.findChildren(QScrollArea, 'InspectorScroll'):
        area.verticalScrollBar().setValue(area.verticalScrollBar().maximum())


@dataclass(frozen=True)
class Screen:
    """One reference screen: what :func:`render` is given to draw it."""

    view: str
    state: str = 'demo-fitted'
    open_menu: str | None = None
    pointer: tuple[float, float] | None = None
    prepare: Callable[[QWidget], None] | None = None
    section: str | None = None


#: The reference screens of the design (``docs/design/screens/<name>_<light|dark>.jpg``), by name.
SCREENS: dict[str, Screen] = {
    'empty': Screen('Measurements', state='empty'),
    'measurements': Screen('Measurements'),
    'measurements_load': Screen('Measurements', open_menu='Load data'),
    'measurements_unit': Screen('Measurements', open_menu='Display unit of the titration plot'),
    'switcher': Screen('Fit results', open_menu='Open sessions', prepare=_more_sessions),
    'binding': Screen('Binding model'),
    'uncertainty': Screen('Input uncertainty'),
    'fit': Screen('Fit results'),
    'fit_replicates': Screen('Fit results', open_menu='Replicate display of the titration plot'),
    'confidence': Screen('Ka confidence'),
    'confidence_readout': Screen('Ka confidence', pointer=(0.65, 0.5)),
    'sensitivity': Screen('Sensitivity', state='demo-sensitivity'),
    'sensitivity_whatif': Screen('Sensitivity', state='demo-sensitivity', open_menu='Source to reduce, for Kₐ guest'),
    'sensitivity_heatmap': Screen('Sensitivity', state='demo-heatmap', pointer=(0.3, 0.7)),
    'appearance': Screen('Plot appearance'),
    'appearance_colour': Screen('Plot appearance', open_menu='Colour of the replicate points'),
    'simulation': Screen('Simulation', state='empty'),
    'simulation_scrolled': Screen('Simulation', state='empty', open_menu='Settings menu', prepare=_settings_at_end),
    'simulation_overlay': Screen('Simulation', state='empty', prepare=_overlay_demo),
    'preferences': Screen('Settings', state='empty'),
    'help': Screen('Help', state='empty', section='Measurements'),
}


def render_screen(name: str, theme: str, directory: Path) -> Path:
    """Write the reference screen *name* in *theme* to *directory*, and say where."""
    screen = SCREENS[name]
    image = render(
        screen.view,
        theme=theme,
        state=screen.state,
        open_menu=screen.open_menu,
        pointer=screen.pointer,
        prepare=screen.prepare,
        section=screen.section,
        scale=SCALE,
    )
    out = directory / f'{name}_{theme}.jpg'
    if not image.save(str(out), 'JPG', JPEG_QUALITY):
        raise OSError(f'Could not write {out}.')
    return out


def render_all(directory: Path, names: list[str], themes: list[str]) -> None:
    """Write the reference screens *names* in *themes* to *directory*, each in a process of its own."""

    def one(job: tuple[str, str]) -> str | None:
        name, theme = job
        command = [sys.executable, '-m', __spec__.name, '--all', str(directory), '--only', name, '--theme', theme]
        done = subprocess.run(command, capture_output=True, text=True, check=False)
        print(done.stdout, end='', flush=True)
        return None if done.returncode == 0 else f'{name}_{theme}: {done.stderr.strip()[-800:]}'

    jobs = [(name, theme) for name in names for theme in themes]
    with ThreadPoolExecutor(max_workers=PROCESSES) as pool:
        failed = [error for error in pool.map(one, jobs) if error]
    if failed:
        sys.exit('These screens could not be rendered:\n' + '\n'.join(failed))


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
    parser.add_argument('view', nargs='?', choices=VIEWS + WINDOWS)
    parser.add_argument('out', nargs='?', help='the image file to write (.png)')
    parser.add_argument('--theme', choices=THEMES, help='light for a view; both for --all')
    parser.add_argument('--state', choices=STATES, default='demo-fitted')
    parser.add_argument('--menu', help='the accessible name of the control whose menu to open')
    parser.add_argument(
        '--pointer', type=_pointer, help='across,down: where over the first plot on screen the pointer rests (0 to 1)'
    )
    parser.add_argument('--section', choices=SECTIONS, help='with Help: the section on show')
    parser.add_argument('--all', type=Path, metavar='DIR', help='write every reference screen to DIR')
    parser.add_argument('--only', nargs='+', choices=list(SCREENS), metavar='NAME', help='with --all: these screens')
    args = parser.parse_args(argv)
    if args.all is None and (args.view is None or args.out is None):
        parser.error('name a view and the file to write, or --all and a folder')
    if args.all is not None and args.view is not None:
        parser.error('--all renders the reference screens; it takes no view')
    if args.only and args.all is None:
        parser.error('--only narrows --all')

    if args.all is not None:
        args.all.mkdir(parents=True, exist_ok=True)
        names = args.only or list(SCREENS)
        themes = [args.theme] if args.theme else list(THEMES)
        if len(names) * len(themes) > 1:
            render_all(args.all, names, themes)
            return
    with tempfile.TemporaryDirectory() as store:
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, store)
        QCoreApplication.setOrganizationName('SupraSimFit-Render')
        QCoreApplication.setApplicationName('render')
        _app = start_application(sys.argv[:1])  # held for the whole render
        preferences.set_int(preferences.WORKER_COUNT_KEY, WORKERS)
        if args.all is not None:
            print(render_screen(names[0], themes[0], args.all), flush=True)
            return
        image = render(
            args.view,
            theme=args.theme or 'light',
            state=args.state,
            open_menu=args.menu,
            pointer=args.pointer,
            section=args.section,
        )
        if not image.save(args.out):
            sys.exit(f'Could not write {args.out}.')


if __name__ == '__main__':
    main()
