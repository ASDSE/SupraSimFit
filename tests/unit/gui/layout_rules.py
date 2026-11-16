"""The rules every laid-out window keeps (DESIGN.md §6, *Every component meets these rules*, and §7, *Plot header row*).

:func:`check` looks at one window as it stands, and :func:`tests.unit.gui.menus.sweep`
with it walks every view of the main window, every section open, and the Settings and
Simulation windows:

- every painted component on screen — a class of the app that paints itself — reports the
  size its content needs, as a minimum size hint or a size it fixes, and its layout gives it
  at least that;
- no plot header cuts its text short;
- no plain one-line label is narrower than its text, which it would cut with no ellipsis;
- every axis title of a plot on screen stands whole inside its plot, clear of the tick labels;
- no two interactive controls on screen share an accessible name, which is all a screen
  reader says of a control.
"""

from __future__ import annotations

import pyqtgraph as pg
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtWidgets import QAbstractScrollArea, QApplication, QLabel, QWidget

from gui.design import components as C


def painted(window: QWidget) -> list[QWidget]:
    """Every painted component on screen in *window*: a widget of a class of the app that paints itself."""
    found = []
    for w in window.findChildren(QWidget):
        if not w.isVisible() or w.isWindow() or w.window() is not window:
            continue
        own = [cls for cls in type(w).__mro__ if cls.__module__.startswith('gui.')]
        if any('paintEvent' in cls.__dict__ for cls in own):
            found.append(w)
    return found


def _name(w: QWidget) -> str:
    return f'{type(w).__name__} {w.accessibleName()!r}' if w.accessibleName() else type(w).__name__


def undersized(window: QWidget) -> list[str]:
    """The painted components of *window* that report no size, or are given less than they report."""
    found = []
    for w in painted(window):
        hint, least = w.minimumSizeHint(), w.minimumSize()
        for axis, given, hinted, fixed in (
            ('width', w.width(), hint.width(), least.width()),
            ('height', w.height(), hint.height(), least.height()),
        ):
            if hinted < 0 and fixed <= 0:
                found.append(f'{_name(w)} reports no {axis} its content needs')
            elif given < hinted:
                found.append(f'{_name(w)} is {given} px in {axis}, its content needs {hinted}')
    return found


def cut_headers(window: QWidget) -> list[str]:
    """The text a plot header on screen in *window* cuts short: every line that gives way, the status bar's aside."""
    found = []
    for e in window.findChildren(C.ElidedLabel):
        if not e.isVisible() or e.window() is not window:
            continue
        parent, in_status = e.parentWidget(), False
        while parent is not None:
            in_status = in_status or parent.objectName() == 'StatusBar'
            parent = parent.parentWidget()
        if not in_status and e.text() != e.full_text:
            found.append(f'{e.full_text!r} is cut to {e.text()!r} in {e.width()} px')
    return found


def cut_labels(window: QWidget) -> list[str]:
    """The plain one-line labels on screen in *window* narrower than their text: they cut it with no ellipsis."""
    found = []
    for lbl in window.findChildren(QLabel):
        if not lbl.isVisible() or lbl.window() is not window or isinstance(lbl, C.ElidedLabel):
            continue
        if lbl.wordWrap() or lbl.textFormat() == Qt.TextFormat.RichText or not lbl.text() or '\n' in lbl.text():
            continue
        margins = lbl.contentsMargins()
        need = lbl.fontMetrics().horizontalAdvance(lbl.text())
        if lbl.width() - margins.left() - margins.right() < need:
            found.append(f'{lbl.text()!r} is cut in {lbl.width()} px, its text needs {need}')
    return found


def title_rect(axis: pg.AxisItem) -> QRectF:
    """Where *axis* draws its title's text, in scene coordinates: its label's box less the document's own margin."""
    margin = axis.label.document().documentMargin()
    return axis.label.sceneBoundingRect().adjusted(margin, margin, -margin, -margin)


def _tick_band(axis: pg.AxisItem) -> QRectF:
    """Where *axis* draws its tick labels, in scene coordinates, as wide (left) or tall (bottom) as the widest drawn."""
    offset = axis.style['tickTextOffset'][0 if axis.orientation == 'left' else 1]
    start = max(0, axis.style['tickLength']) + offset
    w, h = axis.width(), axis.height()
    if axis.orientation == 'left':
        band = QRectF(w - start - axis.textWidth, 0, axis.textWidth, h)
    else:
        band = QRectF(0, start, w, axis.textHeight)
    return axis.mapRectToScene(band)


def axis_text_problems(pw: pg.PlotWidget) -> list[str]:
    """How the axis text of *pw* is cut: a title reaching past the plot's edge, or drawn over its tick labels."""
    pw.grab()  # the axes measure the tick labels they draw as they paint
    found = []
    inside = pw.mapToScene(pw.viewport().rect()).boundingRect()
    for side in ('left', 'bottom'):
        axis = pw.getPlotItem().getAxis(side)
        if not axis.isVisible() or not axis.label.isVisible() or not axis.labelText:
            continue
        title = title_rect(axis)
        if not inside.adjusted(-0.5, -0.5, 0.5, 0.5).contains(title):
            found.append(f'the {side} axis title {axis.labelText!r} reaches past the plot')
        if axis.style['showValues'] and title.intersects(_tick_band(axis)):
            found.append(f'the {side} axis title {axis.labelText!r} runs over its tick labels')
    return found


def cut_axis_text(window: QWidget) -> list[str]:
    """The axis text cut in the plots on screen in *window*, each plot named by its accessible name or class."""
    found = []
    for pw in window.findChildren(pg.PlotWidget):
        if pw.isVisible() and pw.window() is window:
            name = _name(pw.parentWidget()) if pw.parentWidget() is not None else 'a plot'
            found += [f'{name}: {problem}' for problem in axis_text_problems(pw)]
    return found


def interactive(window: QWidget) -> list[QWidget]:
    """Every control on screen in *window*: a widget that takes focus, scroll areas and selectable text aside."""
    return [
        w
        for w in window.findChildren(QWidget)
        if w.isVisible()
        and w.window() is window
        and w.focusPolicy() != Qt.FocusPolicy.NoFocus
        and not isinstance(w, (QAbstractScrollArea, pg.GraphicsView, QLabel))
        and not isinstance(w.parentWidget(), QAbstractScrollArea)
    ]


def clashing_names(window: QWidget) -> list[str]:
    """The accessible names two or more interactive controls on screen in *window* share."""
    named: dict[str, list[str]] = {}
    for w in interactive(window):
        text = getattr(w, 'text', '')
        name = w.accessibleName() or (text() if callable(text) else text)
        named.setdefault(name, []).append(f'{type(w).__name__} in {type(w.parentWidget()).__name__}')
    return [
        f'{name!r} names {len(kinds)} controls: {", ".join(kinds)}' for name, kinds in named.items() if len(kinds) > 1
    ]


def check(_app: QApplication, window: QWidget, where: str, seen: dict[str, list[str]]) -> None:
    """Record under *where* in *seen* what in *window* breaks the rules of this module."""
    seen[where] = (
        undersized(window) + cut_headers(window) + cut_labels(window) + cut_axis_text(window) + clashing_names(window)
    )
