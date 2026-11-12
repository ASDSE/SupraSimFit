"""Render the reference screens of the design (``docs/design/screens``) from the prototype.

The prototype is the approved interface drawn with the real design system
(``gui.design``: tokens, stylesheet, components, plot theme, icons) and the numbers the
app's own engine computed (``data/``). Each ``view_<name>.py`` builds one screen;
``shell.py`` is the main window around it.

Run from the repository root::

    uv run python -m docs.design.prototype.render --all
    uv run python -m docs.design.prototype.render --view fit --dark [--out fit.png] [--scroll-end]

``--all`` renders every reference view in both themes and writes
``docs/design/screens/<view>_<light|dark>.jpg``. One view goes to the same place unless
``--out`` names another file (``.png`` or ``.jpg``). Every render is at 1.5 × the
window's logical size (``--scale``). ``--scroll-end`` scrolls the inspector to its end
first, for the parts of a long panel below the fold.

A view module exposes ``build(t)`` returning the window spec documented in
``shell.py``, or, for a window of its own such as Simulation, ``{'root': QWidget,
'size': (w, h)}``; ``overlay`` (a callable run on the laid-out window, to float
popovers) applies to both.
"""

from __future__ import annotations

import argparse
import importlib
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication, QScrollArea

from gui.design.stylesheet import stylesheet
from gui.design.tokens import Theme, font

from . import shell

SCREENS = Path(__file__).resolve().parents[1] / 'screens'
VIEWS = (
    'fit',
    'switcher',
    'measurements',
    'measurements_load',
    'uncertainty',
    'confidence',
    'confidence_shared',
    'sensitivity',
    'simulation',
    'simulation_scrolled',
    'simulation_overlay',
    'preferences',
)
SCALE = 1.5
JPEG_QUALITY = 72


def screen_path(view: str, dark: bool) -> Path:
    """Where the reference screen of *view* in that theme lives."""
    return SCREENS / f'{view}_{"dark" if dark else "light"}.jpg'


def render(view: str, dark: bool, out: Path, scale: float, scroll_end: bool, keep_open: bool) -> None:
    """Build *view* in one theme, lay it out on screen, and save it to *out* at *scale*."""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    t = Theme(dark=dark)
    app.setPalette(t.palette())
    app.setFont(font('body'))
    app.setStyleSheet(stylesheet(t))
    pg.setConfigOptions(antialias=True)

    spec = importlib.import_module(f'.view_{view}', __package__).build(t)
    if 'root' in spec:  # a window of its own, without the session sidebar
        w, size = spec['root'], spec['size']
    else:
        w, size = shell.window(t, spec), (shell.WIDTH, shell.HEIGHT)
    w.setWindowTitle('SupraSimFit')
    w.setWindowFlag(Qt.WindowType.FramelessWindowHint)  # the title bar is drawn in the window
    w.resize(*size)
    w.show()

    def place():
        if spec.get('overlay'):
            spec['overlay'](w)
        if scroll_end:
            for area in w.findChildren(QScrollArea, 'InspectorScroll'):
                area.verticalScrollBar().setValue(area.verticalScrollBar().maximum())

    def snap():
        pm = QPixmap(w.size() * scale)
        pm.setDevicePixelRatio(scale)
        pm.fill(t.q('bg-window'))
        w.render(pm)
        image = pm.toImage()
        out.parent.mkdir(parents=True, exist_ok=True)
        jpeg = out.suffix.lower() in ('.jpg', '.jpeg')
        if not image.save(str(out), 'JPG' if jpeg else 'PNG', JPEG_QUALITY if jpeg else -1):
            raise SystemExit(f'could not write {out}')
        print('saved', out, image.width(), '×', image.height())
        if not keep_open:
            app.quit()

    QTimer.singleShot(300, place)
    QTimer.singleShot(1200, snap)
    app.exec()


def render_all(scale: float) -> None:
    """Every reference view in both themes, each in a process of its own, four at a time."""

    def one(job: tuple[str, bool]) -> int:
        view, dark = job
        cmd = [sys.executable, '-m', __spec__.name, '--view', view, '--scale', str(scale)]
        return subprocess.run(cmd + (['--dark'] if dark else []), check=False).returncode

    jobs = [(view, dark) for view in VIEWS for dark in (False, True)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        failed = [job for job, code in zip(jobs, pool.map(one, jobs), strict=True) if code]
    if failed:
        raise SystemExit(f'failed: {failed}')


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--view', default='fit', help='the view_<name>.py to render')
    ap.add_argument('--dark', action='store_true')
    ap.add_argument('--all', action='store_true', help='render every reference view in both themes')
    ap.add_argument('--out', type=Path, help='file to write (.png or .jpg); default: its reference screen')
    ap.add_argument('--scale', type=float, default=SCALE, help='device pixels per logical pixel')
    ap.add_argument('--scroll-end', action='store_true', help='scroll the inspector to its end first')
    ap.add_argument('--keep-open', action='store_true')
    args = ap.parse_args()
    if args.all:
        render_all(args.scale)
    else:
        out = args.out or screen_path(args.view, args.dark)
        render(args.view, args.dark, out, args.scale, args.scroll_end, args.keep_open)


if __name__ == '__main__':
    main()
