"""pyqtgraph styled from the same tokens as the window, so a plot reads as part of it."""

from __future__ import annotations

import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import QApplication

from gui.design.tokens import SIZE, TYPE, Theme, family, font, space

#: The opacity of a replicate's points and of the × of one not used, in the plot and in its legend, in
#: both themes. Points of one replicate that overlap another's still show its edge, and each replicate's
#: colour keeps the contrast and the distance from the others its tokens are checked for at this opacity;
#: much lighter, twelve colours cannot both stand out from the plot by 3 : 1 and be told apart.
REPLICATE_ALPHA = 0.8


def px(n: float) -> float:
    """A pen width of *n* logical px; pyqtgraph's cosmetic pens count device pixels."""
    return n * QApplication.instance().devicePixelRatio()


def apply_plot_theme(
    pw: pg.PlotWidget,
    t: Theme,
    x_title: str,
    y_title: str,
    y_grid: list[float] | None = None,
    tick_role: str = 'small-number',
    title_role: str = 'label',
) -> pg.PlotItem:
    """Style *pw* for theme *t*: surface background, left and bottom axes only, no y tick
    marks — horizontal grid lines carry the scale — 4-px outward x ticks, tick labels in
    *tick_role* and axis titles in *title_role*.

    The axes are :data:`SIZE` ``axis-left`` wide and ``axis-bottom`` tall in the standard
    roles, and grow by what larger roles add to a four-figure tick label and a title line.
    The grid follows the y axis's own ticks as the range changes. *y_grid* pins the ticks
    and their grid lines instead, for a plot whose range is fixed.
    """
    pw.setBackground(t['bg-surface'])
    pi = pw.getPlotItem()
    pi.hideButtons()
    pi.setMenuEnabled(False)
    pi.layout.setContentsMargins(0, 0, space(3), 0)
    tick_font = font(tick_role)
    for side in ('top', 'right'):
        pi.showAxis(side, False)
    for side in ('left', 'bottom'):
        ax = pi.getAxis(side)
        ax.setPen(pg.mkPen(t['border-strong'], width=px(1)))
        ax.setTextPen(pg.mkPen(t['text-secondary']))
        ax.setTickFont(tick_font)
        ax.enableAutoSIPrefix(False)
    left, bottom = pi.getAxis('left'), pi.getAxis('bottom')
    left.setStyle(tickLength=0, tickTextOffset=8, autoExpandTextSpace=True)
    bottom.setStyle(tickLength=4, tickTextOffset=6)
    size, weight, _ = TYPE[title_role]
    label_style = {
        'color': t['text-secondary'],
        'font-size': f'{size}px',
        'font-weight': str(int(weight.value)),
        'font-family': family(),
    }
    left.setLabel(y_title, **label_style)
    bottom.setLabel(x_title, **label_style)
    ticks, standard_ticks = QFontMetrics(tick_font), QFontMetrics(font('small-number'))
    title_grows = QFontMetrics(font(title_role)).height() - QFontMetrics(font('label')).height()
    left.setWidth(
        SIZE['axis-left'] + ticks.horizontalAdvance('0000') - standard_ticks.horizontalAdvance('0000') + title_grows
    )
    bottom.setHeight(SIZE['axis-bottom'] + ticks.height() - standard_ticks.height() + title_grows)
    grid_pen = pg.mkPen(t['grid'], width=1)
    if y_grid is None:
        _follow_ticks_with_grid(pi, grid_pen)
    else:
        left.setTicks([[(v, f'{v:g}') for v in y_grid]])
        for v in y_grid:
            _add_grid_line(pi, v, grid_pen)
    pi.getViewBox().setBorder(None)
    pi.getViewBox().setDefaultPadding(0.02)
    return pi


def _add_grid_line(pi: pg.PlotItem, y: float, pen) -> pg.InfiniteLine:
    line = pg.InfiniteLine(pos=y, angle=0, pen=pen, movable=False)
    line.setZValue(-100)
    pi.addItem(line, ignoreBounds=True)
    return line


def _follow_ticks_with_grid(pi: pg.PlotItem, pen) -> None:
    """Keep one grid line in the ``grid`` colour at every major tick of the y axis."""
    left, vb = pi.getAxis('left'), pi.getViewBox()
    lines: list[pg.InfiniteLine] = []

    def update(*_):
        lo, hi = vb.viewRange()[1]
        size = vb.height() or 1.0
        levels = left.tickValues(lo, hi, size)
        major = levels[0][1] if levels else []
        while len(lines) < len(major):
            lines.append(_add_grid_line(pi, 0.0, pen))
        for line, value in zip(lines, major, strict=False):
            line.setPos(value)
            line.show()
        for line in lines[len(major) :]:
            line.hide()

    vb.sigYRangeChanged.connect(update)
    vb.sigResized.connect(update)
    update()


def scatter(t: Theme, x, y, color: str, alpha: float, size: float, symbol: str = 'o', hollow: bool = False):
    """Data points in token *color*: filled, or hollow (and every 'x') drawn as a 1.3-px outline.

    *symbol* is pyqtgraph's: ``o`` circle, ``s`` square, ``t1`` triangle pointing up, ``x`` cross.
    """
    c = t.q(color, alpha)
    if hollow or symbol == 'x':
        return pg.ScatterPlotItem(x, y, symbol=symbol, size=size, pen=pg.mkPen(c, width=px(1.3)), brush=None)
    return pg.ScatterPlotItem(x, y, symbol=symbol, size=size, pen=pg.mkPen(None), brush=pg.mkBrush(c))


def fit_line(t: Theme, x, y, other: bool = False, width: float = SIZE['stroke-medium'], color: str = 'accent'):
    """The fitted curve: *width* px in colour token *color* (2 px in ``accent`` unless a plot appearance
    says otherwise), round caps; *other*, a fit shown beside the reported one, 1.5 px dashed in ``text-tertiary``."""
    if other:
        pen = pg.mkPen(t['text-tertiary'], width=px(1.5), style=Qt.PenStyle.DashLine)
    else:
        pen = pg.mkPen(t[color], width=px(width))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    return pg.PlotDataItem(x, y, pen=pen, antialias=True)
