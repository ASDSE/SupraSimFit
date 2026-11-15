"""pyqtgraph styled from the same tokens as the window, so a plot reads as part of it."""

from __future__ import annotations

import math

import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import QApplication

from gui.design.tokens import SIZE, Theme, family, plot_font, space

#: The opacity of a replicate's points and of the × of one not used, in the plot and in its legend, in
#: both themes. Points of one replicate that overlap another's still show its edge, and each replicate's
#: colour keeps the contrast and the distance from the others its tokens are checked for at this opacity;
#: much lighter, twelve colours cannot both stand out from the plot by 3 : 1 and be told apart.
REPLICATE_ALPHA = 0.8


def px(n: float) -> float:
    """A pen width of *n* logical px; pyqtgraph's cosmetic pens count device pixels."""
    return n * QApplication.instance().devicePixelRatio()


#: The room pyqtgraph sets between an axis and its tick labels: beside the left axis, and under the bottom
#: axis past its outward ticks.
TICK_OFFSET = {'left': 8, 'bottom': 6}
TICK_LENGTH = 4


def axis_box(step: str, widest: str = '0000') -> tuple[int, int]:
    """The width of the left axis and the height of the bottom one at plot text *step*, from the fonts' metrics.

    Each holds its tick labels — the left one as wide as *widest*, four figures unless the
    plot names wider ticks — their offset from the axis, a step of ``space(2)`` and a line
    of axis title, so the axes grow as the text does and a title never meets a tick label.
    """
    ticks = QFontMetrics(plot_font(step, 'tick'))
    title = QFontMetrics(plot_font(step, 'title')).lineSpacing()
    left = TICK_OFFSET['left'] + ticks.horizontalAdvance(widest) + space(2) + title
    bottom = TICK_LENGTH + TICK_OFFSET['bottom'] + ticks.height() + space(2) + title
    return left, bottom


def apply_plot_theme(
    pw: pg.PlotWidget,
    t: Theme,
    x_title: str,
    y_title: str,
    step: str,
    y_ticks: list[tuple[float, str]] | None = None,
) -> pg.PlotItem:
    """Style *pw* for theme *t*: surface background, left and bottom axes only, no y tick
    marks — horizontal grid lines carry the scale — 4-px outward x ticks, tick labels and
    axis titles at *step* of :data:`~gui.design.tokens.PLOT_TEXT`, the step the session's
    Plot appearance chooses, on axes sized for it (:func:`axis_box`).

    The grid follows the y axis's own ticks as the range changes. *y_ticks* — (value,
    label) pairs — pins the ticks and their grid lines instead, for a plot whose range is
    fixed, and the left axis is as wide as its widest label. A pixel of room left of and
    under the axes holds the axis titles whole where pyqtgraph sets them, a pixel past them,
    and a title set later is placed again at once.
    """
    pw.setBackground(t['bg-surface'])
    pi = pw.getPlotItem()
    pi.hideButtons()
    pi.setMenuEnabled(False)
    pi.layout.setContentsMargins(space(1), 0, space(3), space(1))
    tick_font, title_font = plot_font(step, 'tick'), plot_font(step, 'title')
    for side in ('top', 'right'):
        pi.showAxis(side, False)
    for side in ('left', 'bottom'):
        ax = pi.getAxis(side)
        ax.setPen(pg.mkPen(t['border-strong'], width=px(1)))
        ax.setTextPen(pg.mkPen(t['text-secondary']))
        ax.setTickFont(tick_font)
        ax.enableAutoSIPrefix(False)
    left, bottom = pi.getAxis('left'), pi.getAxis('bottom')
    left.setStyle(tickLength=0, tickTextOffset=TICK_OFFSET['left'], autoExpandTextSpace=True)
    bottom.setStyle(tickLength=TICK_LENGTH, tickTextOffset=TICK_OFFSET['bottom'])
    label_style = {
        'color': t['text-secondary'],
        'font-size': f'{title_font.pixelSize()}px',
        'font-weight': str(int(title_font.weight())),
        'font-family': family(),
    }
    left.setLabel(y_title, **label_style)
    bottom.setLabel(x_title, **label_style)
    for ax in (left, bottom):
        # pyqtgraph places an axis title only as the axis is resized; one set later on an axis of fixed size
        # would stay where the last title's size put it, cut off or off centre.
        ax.label.document().contentsChanged.connect(lambda ax=ax: ax.resizeEvent())
    fm = QFontMetrics(tick_font)
    widest = max(['0000', *(text for _v, text in y_ticks or ())], key=fm.horizontalAdvance)
    width, height = axis_box(step, widest)
    left.setWidth(width)
    bottom.setHeight(height)
    grid_pen = pg.mkPen(t['grid'], width=1)
    if y_ticks is None:
        _follow_ticks_with_grid(pi, grid_pen)
    else:
        left.setTicks([list(y_ticks)])
        for v, _text in y_ticks:
            _add_grid_line(pi, v, grid_pen)
    pi.getViewBox().setBorder(None)
    pi.getViewBox().setDefaultPadding(0.02)
    return pi


def least_height(pi: pg.PlotItem) -> int:
    """The least height of plot *pi* that holds its left axis title whole: the title along the axis, the bottom
    axis under it and the room above the axes."""
    title = pi.getAxis('left').label.boundingRect().width()
    return math.ceil(title + pi.getAxis('bottom').height() + pi.layout.getContentsMargins()[1])


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
