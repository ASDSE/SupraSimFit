"""Sensitivity: how far the stated inputs spread each Ka, which source the spread comes from, and the heatmap (DESIGN.md §8).

Canvas, for a run of sensitivity indices: one block per binding constant — the spread
of Kₐ from the stated inputs (×/÷ factor, 1 SD in decades, the value it is read around)
beside the sample histogram with both readings of the fit marked and *Plot against each
source →*, any callout, **Share of the variance, by source** (S₁ and S_T per source with
their 95 % whiskers), the **Variance budget** and **What if one source were known
better**. A constant whose indices the run withholds shows a callout in their place. For
a heatmap: one map of Kₐ per binding constant over the two inputs swept, on the heat
scale, with its colour bar, the entered point and the value under the pointer. Side panel
*Analysis settings*: Run, Error sources (*Edit in Input uncertainty →*), This run,
Display.

Everything is read from the session model — the run it holds, the fit it reports, the
analysis settings (:class:`~gui.sensitivity.AnalysisForm`) — and redrawn when the model
says one changed; the text and numbers come from :mod:`gui.sensitivity`.
"""

from __future__ import annotations

import math
from functools import partial
from html import escape

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QMargins, QObject, QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFontMetrics, QKeySequence, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QApplication, QFrame, QGridLayout, QLayout, QScrollArea, QSizePolicy, QWidget

from core.pipeline.inputs import TITRANT, ErrorModel
from core.pipeline.sensitivity import SensitivityMode
from core.pipeline.varpro import projectable
from gui import sensitivity as S
from gui.design import components as C
from gui.design.appearance import appearance, theme
from gui.design.plot_theme import apply_plot_theme, axis_box, least_height, px, scatter
from gui.design.tokens import HEAT_STOPS, RADIUS, SIZE, Theme, font, plot_font, space
from gui.plotting.export import export_widget, figure_head
from gui.plotting.labels import plain_label
from gui.session_model import Change, SessionModel
from gui.widgets.assay_conditions import condition_field


def _clear(layout: QLayout) -> None:
    """Take every widget and nested layout out of *layout*."""
    while layout.count():
        item = layout.takeAt(0)
        if item.widget() is not None:
            C.drop(item.widget())
        elif item.layout() is not None:
            _clear(item.layout())


def _widget(layout: QLayout) -> QWidget:
    w = QWidget()
    w.setLayout(layout)
    return w


# ── Painted marks (tokens only) ────────────────────────────────────────────────────


def _sample_fill(t: Theme, inside: bool):
    """A sample bar: solid inside the middle 90 % of samples, faded in the tails."""
    return t.q('text-secondary', 0.62 if inside else 0.22)


def paint_index_bar(p: QPainter, t: Theme, rect: QRectF, total: bool) -> None:
    """One index bar: S₁ solid in ``series-1``, S_T a tint of ``series-2`` inside an edge of it."""
    path = QPainterPath()
    if total:
        path.addRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), RADIUS['bar'], RADIUS['bar'])
        p.fillPath(path, t.q('series-2', 0.24 if t.dark else 0.16))
        p.strokePath(path, QPen(t.q('series-2', 0.9), 1))
    else:
        path.addRoundedRect(rect, RADIUS['bar'], RADIUS['bar'])
        p.fillPath(path, t.q('series-1'))


def paint_whisker(p: QPainter, t: Theme, a: float, b: float, y: float) -> None:
    """A 95 % whisker from *a* to *b* at height *y*, 1.25 px with 6-px caps (DESIGN.md §7)."""
    p.setPen(QPen(t.q('text-primary'), SIZE['whisker']))
    p.drawLine(QPointF(a, y), QPointF(b, y))
    cap = SIZE['whisker-cap'] / 2
    for x in (a, b):
        p.drawLine(QPointF(x, y - cap), QPointF(x, y + cap))


class SampleHistogram(QWidget):
    """Every sample's Kₐ on its axis: the middle 90 % solid, the tails faded, both readings of the fit marked.

    Input-aware is an accent line with its interval as the accent tint behind the bars;
    Inputs as entered a dashed line with its interval as a bracket across the top of the
    bars. Each is labelled at its top end, a second row taking a label the first cannot. Its
    labels and ticks are at the tick labels' size of plot text *step*, and it is as tall as
    its bars (``histogram``), a row of labels above them and its axis below.
    """

    def __init__(self, t: Theme, hist: S.Histogram, step: str):
        super().__init__()
        self.t, self.hist = t, hist
        self.tick_font = plot_font(step, 'tick')
        fm = QFontMetrics(self.tick_font)
        self.label_h = fm.height()
        self.axis_h = fm.height() + space(3)
        self.setMinimumHeight(self.label_h + space(2) + SIZE['histogram'] + self.axis_h)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(f'Samples of Kₐ. {hist.fold}' if hist.fold else 'Samples of Kₐ')

    def minimumSizeHint(self) -> QSize:
        # Each reading's label whole, on a row of its own where two do not fit side by side, and the axis unit.
        fm = QFontMetrics(self.tick_font)
        labels = [fm.horizontalAdvance(m.label) + 1 for m in self.hist.markers]
        unit = fm.horizontalAdvance(self.hist.unit) + space(1)
        return QSize(math.ceil(max([unit, *labels])) + 2, self.minimumHeight())

    def sizeHint(self) -> QSize:
        return self.minimumSizeHint()

    def _x(self, v: float) -> float:
        lo, hi = self.hist.x_range
        return (v - lo) / (hi - lo) * (self.width() - 2.0)

    def _label_rows(self) -> list[tuple[S.Marker, QRectF]]:
        """Each marker's label box: centred on its line and kept inside the plot; one that would run into a label
        already placed moves beside it, and onto a row of its own only where there is no room beside it."""
        fm = QFontMetrics(self.tick_font)
        w = self.width() - 2.0
        gap = space(4)
        placed: list[tuple[S.Marker, QRectF]] = []
        for marker in self.hist.markers:
            x = self._x(marker.x) if marker.x is not None else self._x(sum(marker.span or self.hist.x_range) / 2)
            tw = fm.horizontalAdvance(marker.label) + 1
            left = min(max(x - tw / 2, 0.0), max(w - tw, 0.0))
            box = QRectF(left, 0, tw, self.label_h)
            for _m, other in placed:
                if box.adjusted(-gap, 0, gap, 0).intersects(other):
                    beside = other.right() + gap if x >= other.center().x() else other.left() - gap - tw
                    box.moveLeft(beside)
            if box.left() < 0 or box.right() > w or any(box.intersects(r) for _m, r in placed):
                box = QRectF(left, len({r.top() for _m, r in placed}) * self.label_h, tw, self.label_h)
            placed.append((marker, box))
        return placed

    def paintEvent(self, _):
        t, hist = self.t, self.hist
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width() - 2.0
        labels = self._label_rows()
        rows = 1 + max((int(r.top() // self.label_h) for _m, r in labels), default=0)
        top = rows * self.label_h + space(2)
        base = self.height() - self.axis_h
        aware = [m for m in hist.markers if m.kind == 'aware']
        for marker in aware:
            if marker.span is not None:
                a, b = (self._x(v) for v in marker.span)
                p.fillRect(
                    QRectF(a, top - space(1), b - a, base - top + space(1)), t.q('accent', 0.07 if t.dark else 0.08)
                )
        p.setPen(QPen(t.q('grid'), 1))
        for value, _text in hist.ticks:
            x = self._x(value)
            p.drawLine(QPointF(x, top), QPointF(x, base))
        peak = max(int(hist.counts.max()), 1)
        p.setPen(Qt.PenStyle.NoPen)
        for i, count in enumerate(hist.counts):
            if not count:
                continue
            a, b = self._x(hist.edges[i]), self._x(hist.edges[i + 1])
            h = max(count / peak * (base - top - space(1)), 1.5)
            path = QPainterPath()
            path.addRoundedRect(QRectF(a + 0.75, base - h, max(b - a - 1.5, 1.0), h), 1.5, 1.5)
            p.fillPath(path, _sample_fill(t, bool(hist.inside[i])))
        p.setPen(QPen(t.q('border-strong'), 1))
        p.drawLine(QPointF(0, base + 0.5), QPointF(w, base + 0.5))
        fm = QFontMetrics(self.tick_font)
        p.setFont(self.tick_font)
        unit_w = fm.horizontalAdvance(hist.unit) + space(1)
        for value, _text in hist.ticks:
            x = self._x(value)
            p.setPen(QPen(t.q('border-strong'), 1))
            p.drawLine(QPointF(x, base), QPointF(x, base + space(2)))
        ticks = [((10.0**v) if hist.log else v, text) for v, text in hist.ticks]

        def x_of(value: float) -> float:
            return self._x(math.log10(value)) if hist.log else self._x(value)

        p.setPen(t.q('text-secondary'))
        for text, box in C.spaced_ticks(ticks, x_of, fm, 0.0, w - unit_w - space(2)):
            p.drawText(box.translated(0, base + space(2)), Qt.AlignmentFlag.AlignHCenter, text)
        p.drawText(QRectF(w - unit_w, base + space(2), unit_w, fm.height()), Qt.AlignmentFlag.AlignRight, hist.unit)
        y0 = top - space(1)
        for marker in hist.markers:
            if marker.kind == 'entered' and marker.span is not None:
                a, b = (self._x(v) for v in marker.span)
                p.setPen(QPen(t.q('text-secondary'), 1.25))
                p.drawLine(QPointF(a, y0), QPointF(b, y0))
                for x in (a, b):
                    p.drawLine(QPointF(x, y0), QPointF(x, y0 + space(2)))
        for marker in hist.markers:
            if marker.x is None:
                continue
            x = self._x(marker.x)
            p.setPen(QPen(t.q('bg-surface'), 4.5))
            p.drawLine(QPointF(x, y0), QPointF(x, base))
            if marker.kind == 'aware':
                p.setPen(QPen(t.q('accent'), 2))
            else:
                dash = QPen(t.q('text-primary'), 1.5)
                dash.setDashPattern([3, 2.5])
                p.setPen(dash)
            p.drawLine(QPointF(x, y0), QPointF(x, base))
        for marker, box in labels:
            p.setPen(t.q('accent' if marker.kind == 'aware' else 'text-secondary'))
            p.drawText(box, Qt.AlignmentFlag.AlignVCenter, marker.label)
        p.end()


class BarChip(QWidget):
    """The legend key of the solid sample bars."""

    def __init__(self, t: Theme):
        super().__init__()
        self.t = t
        self.setFixedSize(space(4), space(5))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(1, space(1) + 1, space(3), space(4) - space(1)), 1.5, 1.5)
        p.fillPath(path, _sample_fill(self.t, True))
        p.end()


class IndexChartView(QWidget):
    """Sobol' indices per source as a pair of bars from zero, S₁ above S_T, each with its 95 % whisker, the values on
    the right. The name column is *name_w* wide, the width of the budget table's Source column below, so the bars start
    where its Stated column does."""

    def __init__(self, t: Theme, chart: S.IndexChart, name_w: int):
        super().__init__()
        self.t, self.chart, self.name_w = t, chart, name_w
        self.head_h = space(6)
        self.row_h = SIZE['control'] + space(1)
        self.axis_h = space(6)
        self.bar_h = space(3)
        self.num_w = QFontMetrics(font('number')).horizontalAdvance('−0.000') + space(2)
        self.setFixedHeight(self.head_h + len(chart.rows) * self.row_h + self.axis_h)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.bars_min = len(chart.ticks) * 2 * space(6)  # each tick label's box, side by side
        self.setToolTip(
            'Each whisker is a 95 % confidence interval: in about 95 of every 100 analyses it holds the index '
            'unlimited samples would give for the uncertainties you stated. It is worked out from 8 independent '
            'sample blocks; more samples narrow it. It does not cover errors in what you stated or in the model.'
        )
        self.setAccessibleName(
            'Share of the variance by source: '
            + '; '.join(f'{plain_label(r.name)} S₁ {S.share(r.s1)}, S_T {S.share(r.st)}' for r in chart.rows)
        )

    def minimumSizeHint(self) -> QSize:
        # The name column, the bars with room for every tick label, and the two columns of numbers.
        return QSize(self.name_w + self.bars_min + space(6) + 2 * self.num_w + space(5), self.minimumHeight())

    def sizeHint(self) -> QSize:
        return self.minimumSizeHint()

    def paintEvent(self, _):
        t, chart = self.t, self.chart
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W = float(self.width())
        st_right = W
        s1_right = W - self.num_w - space(5)
        x0 = float(self.name_w)
        width = max(s1_right - self.num_w - space(6) - x0, 1.0)
        lo, hi = chart.lo, chart.hi

        def X(v: float) -> float:
            return x0 + (min(max(v, lo), hi) - lo) / (hi - lo) * width

        n = len(chart.rows)
        top = float(self.head_h)
        bottom = top + n * self.row_h
        ter = t.q('text-tertiary')
        C.paint_rich(p, QRectF(0, 0, self.name_w, self.head_h), 'Source', 'label', ter)
        C.paint_rich(
            p, QRectF(s1_right - self.num_w, 0, self.num_w, self.head_h), 'S<sub>1</sub>', 'label', ter, right=True
        )
        C.paint_rich(
            p, QRectF(st_right - self.num_w, 0, self.num_w, self.head_h), 'S<sub>T</sub>', 'label', ter, right=True
        )
        p.setPen(QPen(t.q('border'), 1))
        p.drawLine(QPointF(0, top - 0.5), QPointF(W, top - 0.5))
        p.setFont(font('small-number'))
        for tick in chart.ticks:
            x = X(tick)
            p.setPen(QPen(t.q('border-strong' if tick == 0 else 'grid'), 1))
            p.drawLine(QPointF(x, top), QPointF(x, bottom))
            p.setPen(t.q('text-secondary'))
            p.drawText(
                QRectF(x - space(6), bottom + space(2), 2 * space(6), space(5)),
                Qt.AlignmentFlag.AlignHCenter,
                S._minus(f'{tick:g}'),
            )
        right = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        for i, row in enumerate(chart.rows):
            cy = top + i * self.row_h + self.row_h / 2
            C.paint_rich(
                p,
                QRectF(0, cy - space(5) / 2 - space(1), self.name_w - space(3), space(5) + space(2)),
                row.name,
                'body',
                t.q('text-primary'),
            )
            pair = (
                (row.s1, row.s1_ci, cy - space(1) - self.bar_h / 2, False),
                (row.st, row.st_ci, cy + space(1) + self.bar_h / 2, True),
            )
            for value, (a, b), y, total in pair:
                if not math.isfinite(value):
                    continue
                start, end = X(min(0.0, value)), X(max(0.0, value))
                paint_index_bar(p, t, QRectF(start, y - self.bar_h / 2, max(end - start, 2.0), self.bar_h), total)
                if math.isfinite(a) and math.isfinite(b):
                    paint_whisker(p, t, X(a), X(b), y)
                for edge, beyond in (
                    (hi, max(value, b if math.isfinite(b) else value) > hi),
                    (lo, min(value, a if math.isfinite(a) else value) < lo),
                ):
                    if beyond:
                        self._arrow(p, X(edge), y, edge == hi)
            p.setFont(font('number'))
            for value, x_right in ((row.s1, s1_right), (row.st, st_right)):
                p.setPen(t.q('text-primary' if math.isfinite(value) else 'text-tertiary'))
                p.drawText(QRectF(x_right - self.num_w, cy - space(5) / 2, self.num_w, space(5)), right, S.share(value))
        p.end()

    def _arrow(self, p: QPainter, x: float, y: float, up: bool) -> None:
        """A small triangle at the edge of the axis: the bar or whisker runs on past it."""
        d = space(2)
        path = QPainterPath()
        path.moveTo(x + (d if up else -d), y)
        path.lineTo(x, y - d)
        path.lineTo(x, y + d)
        path.closeSubpath()
        p.fillPath(path, self.t.q('text-primary'))


class IndexLegend(QWidget):
    """The chart's legend, each entry drawn with the chart's own mark."""

    ITEMS = (('first', 'S<sub>1</sub> first order'), ('total', 'S<sub>T</sub> total'), ('whisker', '95 % interval'))

    def __init__(self, t: Theme):
        super().__init__()
        self.t = t
        self.chip = space(5) + space(2)
        widths = [self.chip + C.rich_width(text, 'small') for _kind, text in self.ITEMS]
        self.setFixedSize(math.ceil(sum(widths) + space(5) * (len(widths) - 1)), space(5) + space(1))

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        x, cy = 0.0, self.height() / 2
        bar_h = space(3)
        for kind, text in self.ITEMS:
            if kind == 'whisker':
                paint_whisker(p, t, x + 1, x + space(5) - 1, cy)
            else:
                paint_index_bar(p, t, QRectF(x, cy - bar_h / 2, space(5), bar_h), kind == 'total')
            tw = C.paint_rich(p, QRectF(x + self.chip, 0, 400, self.height()), text, 'small', t.q('text-secondary'))
            x += self.chip + tw + space(5)
        p.end()


# ── Heatmap ────────────────────────────────────────────────────────────────────────


def heat_map(t: Theme) -> pg.ColorMap:
    """The heat scale of theme *t*, low to high, from its tokens."""
    stops = [t.q(f'heat-{i}') for i in range(HEAT_STOPS)]
    return pg.ColorMap(pos=np.linspace(0.0, 1.0, HEAT_STOPS), color=[(c.red(), c.green(), c.blue()) for c in stops])


class HeatBar(QWidget):
    """The colour bar beside a heatmap: the heat scale from low (bottom) to high, its ticks and its title above, at
    plot text *step*, its foot level with the heatmap's x axis."""

    def __init__(self, t: Theme, hm: S.Heatmap, step: str):
        super().__init__()
        self.t, self.hm, self.step = t, hm, step
        self.tick_font, self.title_font = plot_font(step, 'tick'), plot_font(step, 'title')
        fm = QFontMetrics(self.tick_font)
        tick_w = max((fm.horizontalAdvance(text) for _v, text in hm.ticks), default=0)
        self.bar_w = space(4)
        title_w = QFontMetrics(self.title_font).horizontalAdvance(hm.bar_title)
        self.setFixedWidth(max(self.bar_w + space(2) + tick_w, title_w))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

    def paintEvent(self, _):
        t, hm = self.t, self.hm
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        title_h = QFontMetrics(self.title_font).height() + space(2)
        top, bottom = title_h + space(2), self.height() - axis_box(self.step)[1]
        p.setFont(self.title_font)
        p.setPen(t.q('text-secondary'))
        p.drawText(
            QRectF(0, 0, self.width(), title_h),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            hm.bar_title,
        )
        h = max(bottom - top, 1.0)
        for i in range(int(h)):
            share = 1.0 - i / h
            color = heat_map(t).map(share, mode='qcolor')
            p.fillRect(QRectF(0, top + i, self.bar_w, 1.0), color)
        p.setPen(QPen(t.q('border-strong'), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(0.5, top + 0.5, self.bar_w - 1, h - 1))
        p.setFont(self.tick_font)
        fm = QFontMetrics(self.tick_font)
        for value, text in hm.ticks:
            y = bottom - (value - hm.lo) / (hm.hi - hm.lo) * h
            p.setPen(QPen(t.q('border-strong'), 1))
            p.drawLine(QPointF(self.bar_w, y), QPointF(self.bar_w + space(1), y))
            p.setPen(t.q('text-secondary'))
            p.drawText(
                QRectF(self.bar_w + space(2), y - fm.height() / 2, self.width(), fm.height()),
                Qt.AlignmentFlag.AlignVCenter,
                text,
            )
        p.end()


class HeatmapFigure(QWidget):
    """Kₐ over two swept inputs on the heat scale, the entered point marked, the colour bar beside it and the value
    under the pointer as a readout card at the plot's top-right corner (the entered cell without a pointer), its
    text at plot text *step*."""

    def __init__(self, t: Theme, hm: S.Heatmap, step: str, interactive: bool = True):
        super().__init__()
        self.t, self.hm = t, hm
        self.main = pg.PlotWidget()
        self.main.setFrameShape(QFrame.Shape.NoFrame)
        pi = apply_plot_theme(self.main, t, hm.x_title, hm.y_title, step)
        pi.getViewBox().setMouseEnabled(x=False, y=False)
        values = np.asarray(hm.values, dtype=float)
        shown = np.isfinite(values)
        share = np.where(shown, (values - hm.lo) / (hm.hi - hm.lo), 0.0)
        rgba = heat_map(t).map(np.clip(share, 0.0, 1.0), mode='byte')
        rgba[~shown] = 0
        self.image = pg.ImageItem()
        self.image.setImage(rgba, axisOrder='row-major')
        x0, xw, self.step_x = _extent(hm.x)
        y0, yh, self.step_y = _extent(hm.y)
        self.image.setRect(QRectF(x0, y0, xw, yh))
        pi.addItem(self.image)
        entered = pg.ScatterPlotItem(
            x=[hm.entered[0]],
            y=[hm.entered[1]],
            symbol=C.diamond(QPointF(0, 0), 1.0),
            size=SIZE['diamond'],
            brush=pg.mkBrush(t.q('bg-surface')),
            pen=pg.mkPen(t.q('text-primary'), width=px(1.5)),
        )
        entered.setZValue(4)
        pi.addItem(entered)
        self.cell = pg.QtWidgets.QGraphicsRectItem()
        self.cell.setPen(pg.mkPen(t.q('text-primary'), width=px(1.5)))
        self.cell.setZValue(3)
        self.cell.hide()
        pi.addItem(self.cell)
        pi.setRange(xRange=(x0, x0 + xw), yRange=(y0, y0 + yh), padding=0)
        self.bar = HeatBar(t, hm, step)
        self.card = C.ReadoutCard(t, self.main)
        self.default = (int(np.argmin(np.abs(hm.x - hm.entered[0]))), int(np.argmin(np.abs(hm.y - hm.entered[1]))))
        self.show_cell(*self.default, pointer=False)
        pi.getViewBox().sigResized.connect(self._place)
        if interactive:
            self._proxy = pg.SignalProxy(self.main.scene().sigMouseMoved, rateLimit=60, slot=self._moved)
        else:
            self.card.hide()
        self.setLayout(C.hbox(self.main, 3, self.bar, spacing=0))
        self.setAccessibleName(f'Heatmap of {hm.name} over {hm.x_label} and {hm.y_label}')

    def show_cell(self, ix: int, iy: int, pointer: bool = True) -> None:
        """Read cell (*ix*, *iy*) in the card; with *pointer* outline it as well."""
        title, rows = S.heatmap_readout(self.hm, ix, iy)
        self.card.set_values(title, [('text-tertiary', name, value, '', False) for name, value in rows])
        self.cell.setVisible(pointer)
        if pointer:
            self.cell.setRect(
                QRectF(self.hm.x[ix] - self.step_x / 2, self.hm.y[iy] - self.step_y / 2, self.step_x, self.step_y)
            )
        self._place()

    def _moved(self, event) -> None:
        vb = self.main.getPlotItem().getViewBox()
        pos = event[0]
        if vb.sceneBoundingRect().contains(pos):
            point = vb.mapSceneToView(pos)
            ix = int(np.clip(round((point.x() - self.hm.x[0]) / (self.step_x or 1.0)), 0, self.hm.x.size - 1))
            iy = int(np.clip(round((point.y() - self.hm.y[0]) / (self.step_y or 1.0)), 0, self.hm.y.size - 1))
            self.show_cell(ix, iy)
        elif self.cell.isVisible():
            self.show_cell(*self.default, pointer=False)

    def leaveEvent(self, event) -> None:
        if self.cell.isVisible():
            self.show_cell(*self.default, pointer=False)
        super().leaveEvent(event)

    def _place(self, *_) -> None:
        vb = self.main.getPlotItem().getViewBox()
        rect = self.main.mapFromScene(vb.sceneBoundingRect()).boundingRect()
        self.card.move(rect.right() - self.card.width() - space(3), rect.top() + space(3))
        self.card.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place()

    def minimumSizeHint(self) -> QSize:
        # An analysis plot's least height, or more where its title along the y axis needs it.
        return QSize(super().minimumSizeHint().width(), max(SIZE['plot-min'], least_height(self.main.getPlotItem())))

    def sizeHint(self) -> QSize:
        return QSize(super().sizeHint().width(), self.minimumSizeHint().height())


def _extent(values: np.ndarray) -> tuple[float, float, float]:
    """``(origin, length, step)`` that centres each cell on its value."""
    step = float(values[1] - values[0]) if values.size >= 2 else 1.0
    return float(values[0]) - step / 2, float(values[-1] - values[0]) + step, step


# ── Kₐ against each source ─────────────────────────────────────────────────────────


class SourcePlotsWindow(QWidget):
    """A window of small plots, one per error source: each sample's Kₐ against that source's draw.

    A source that matters shows as a trend. The Kₐ axis follows Display (log₁₀ or linear);
    each draw axis opens on its source's range (:attr:`~gui.sensitivity.SourcePlot.x_range`)
    with :data:`MARGIN` of it at each end, and labels its ticks, a range's ends among them.
    The plots zoom and pan (:class:`~gui.design.components.PlotNavigation`); *Reset view*,
    or a double-click, frames them as they opened. Their text is at plot text *step*. The
    window draws its plots again when the theme or the step changes.
    """

    COLUMNS = 3
    #: The share of a draw axis left free at each end, so a sample on an end of a range stays clear of the frame.
    MARGIN = 0.03

    def __init__(self, t: Theme, plots: list[S.SourcePlot], note: str, ka_name: str, log: bool, step: str, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.t, self.source_plots, self.note, self.ka_name, self.log = t, plots, note, ka_name, log
        self.step = step
        self.setWindowTitle(f'{ka_name} against each source')
        self.plots: list[pg.PlotWidget] = []
        self.navigation = C.PlotNavigation(t, 'Reset the view of every plot')
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QFrame.Shape.NoFrame)
        self.setLayout(C.vbox(self.area, spacing=0))
        self._draw()
        appearance().changed.connect(self._draw)
        rows = max(1, math.ceil(len(plots) / self.COLUMNS))
        self.resize(self.COLUMNS * SIZE['plot-min'] + 2 * space(7), min(rows, 2) * SIZE['plot-min'] + 2 * space(7))

    def set_step(self, step: str) -> None:
        """Draw the plots at plot text *step* from now on."""
        if step != self.step:
            self.step = step
            self._draw()

    def _draw(self) -> None:
        """Build the plots in the theme as it is now."""
        t, ka_name = self.t, self.ka_name
        old = self.area.takeWidget()
        if old is not None:
            old.deleteLater()
        body = QWidget()
        body.setObjectName('Canvas')
        body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        grid = QGridLayout()
        grid.setContentsMargins(space(6), space(5), space(6), space(5))
        grid.setHorizontalSpacing(space(5))
        grid.setVerticalSpacing(space(5))
        # A tick on an end of the draw axis has its label centred there, wider than the margin
        # the axis leaves: the axis draws its labels up to half the widest one past its own
        # edges — on the right into room kept beside the plot, on the left into the Kₐ axis's.
        fm = QFontMetrics(plot_font(self.step, 'tick'))
        widest = max((fm.horizontalAdvance(text) for p in self.source_plots for _v, text in p.x_ticks), default=0)
        half_label = math.ceil(widest / 2)
        self.plots, homes = [], []
        for i, plot in enumerate(self.source_plots):
            pw = pg.PlotWidget()
            pw.setFrameShape(QFrame.Shape.NoFrame)
            axis = S.ka_axis(list(plot.y), self.log) if plot.y.size else None
            y_title = ''
            if i % self.COLUMNS == 0:
                y_title = ka_name if axis is None else f'{ka_name} ({axis[2].lstrip("×").strip()})'
            pi = apply_plot_theme(pw, t, plot.x_title, y_title, self.step, list(axis[1]) if axis else None)
            if axis is not None:
                pi.addItem(scatter(t, plot.x, np.log10(plot.y) if self.log else plot.y, 'text-secondary', 0.45, 5))
            bottom = pi.getAxis('bottom')
            bottom.setTicks([plot.x_ticks])
            bottom.setStyle(hideOverlappingLabels=half_label)
            left, top, right, below = pi.layout.getContentsMargins()
            pi.layout.setContentsMargins(left, top, max(right, half_label), below)
            pw.setMinimumSize(SIZE['plot-min'] - space(7), max(SIZE['plot-min'] - space(7), least_height(pi)))
            pw.setAccessibleName(f'{ka_name} against {plain_label(plot.name)}')
            grid.addWidget(pw, i // self.COLUMNS, i % self.COLUMNS)
            self.plots.append(pw)
            homes.append(partial(self._frame, pi, plot.x_range, axis[0] if axis is not None else None))
        self.navigation.set_plots(list(zip(self.plots, homes, strict=True)))
        items = [C.hbox(None, self.navigation.tool, margins=(0, 3, 6, 0)), grid]
        if self.note:
            items.append(C.wrapped(self.note, 'small', 'tertiary'))
        if not self.source_plots:
            items.append(C.wrapped('No source has a draw of its own to plot against.', 'body', 'secondary'))
        body.setLayout(C.vbox(*items, None, spacing=4))
        self.area.setWidget(body)

    def _frame(self, pi: pg.PlotItem, x_range: tuple[float, float], y_range: tuple[float, float] | None) -> None:
        """Frame plot *pi* as it opened: its draw axis on the source's range, its Kₐ axis on the samples."""
        pi.setXRange(*x_range, padding=self.MARGIN)
        if y_range is not None:
            pi.setYRange(*y_range, padding=0)


# ── The view ───────────────────────────────────────────────────────────────────────


class SensitivityView(QObject):
    """The canvas and side panel of Sensitivity over *model*; *parent* is the session.

    :attr:`view_requested` asks for another view (Input uncertainty, Fit results, Ka
    confidence) where a link points there; the session answers it.
    """

    view_requested = pyqtSignal(str)

    def __init__(self, model: SessionModel, parent: QWidget):
        super().__init__(parent)
        self.model, self.parent, self.t = model, parent, theme()
        self.callouts: list = []
        self.blocks: list[S.KaBlock] = []
        self.histograms: list[SampleHistogram] = []
        self.charts: list[IndexChartView] = []
        self.tables: list[C.Table] = []
        self.heatmap_figures: list[HeatmapFigure] = []
        self.what_ifs: dict[str, tuple[C.Dropdown, C.Dropdown, QWidget, QWidget, list]] = {}
        # The source and reduction chosen in each what-if, kept while the same run is on show.
        self.what_if_choices: dict[str, list[int]] = {}
        self.windows: list[SourcePlotsWindow] = []
        # What the blocks on the canvas were drawn from; they are drawn again only when it changes.
        self.drawn: tuple | None = None
        self.locked = False
        self.canvas = self._build_canvas()
        self.side = self._build_side()
        model.changed.connect(self._on_changed)
        appearance().changed.connect(self._restyle)
        self.refresh()

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    def _build_canvas(self) -> QWidget:
        content = QWidget()
        content.setObjectName('Canvas')
        content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.empty = C.wrapped('', 'body', 'secondary')
        # The first block's headline stands above the callouts (DESIGN.md §3); the rest of it, under them.
        self.head_host = QWidget()
        self.head_box = C.vbox(spacing=0)
        self.head_host.setLayout(self.head_box)
        self.callout_host = QWidget()
        self.callout_box = C.vbox(spacing=3)
        self.callout_host.setLayout(self.callout_box)
        self.blocks_host = QWidget()
        self.blocks_box = C.vbox(spacing=0)
        self.blocks_host.setLayout(self.blocks_box)
        lay = C.vbox(
            self.empty, self.head_host, self.callout_host, self.blocks_host, None, spacing=5, margins=(6, 5, 6, 4)
        )
        content.setLayout(lay)
        self.content = content
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setWidget(content)
        self.area = area
        return area

    def _build_side(self) -> QWidget:
        t = self.t
        form = self.model.analysis
        # Run
        self.mode = C.Segmented(t, list(S.MODES), 0 if form.mode is SensitivityMode.SOBOL else 1)
        self.mode.setAccessibleName('Analysis mode')
        self.mode.changed.connect(self._set_mode)
        self.size = C.Segmented(t, [str(n) for n in S.SAMPLE_SIZES], S.SAMPLE_SIZES.index(form.n_samples))
        self.size.setAccessibleName('Sample size N')
        self.size.changed.connect(self._set_size)
        self.size_note = C.wrapped('', 'small', 'tertiary')
        self.seed_check = C.Checkbox(t, 'Fixed seed', form.fixed_seed)
        self.seed_check.setAccessibleName('Fix the seed of the analysis')
        self.seed_check.toggled.connect(self._set_fixed_seed)
        self.seed = C.Field(t, form.seed_text, width=C.Field.width_for('2147483647'), editable=True)
        self.seed.setAccessibleName('Fixed seed')
        # Taken as typed, so a run started from the field, or a redraw while it is typed in, keeps it.
        self.seed.typed.connect(self._set_seed)
        self.seed_note = C.wrapped('', 'small', 'tertiary')
        self.indices_part = _widget(
            C.vbox(
                C.label('Sample size (N)', 'label', 'secondary'),
                self.size,
                self.size_note,
                4,
                C.hbox(self.seed_check, None, self.seed, spacing=3),
                self.seed_note,
                spacing=2,
            )
        )
        self.x_axis = C.Dropdown(t)
        self.x_axis.setAccessibleName('X axis of the heatmap')
        self.x_axis.chosen.connect(lambda i: self._set_axis('x', i))
        self.y_axis = C.Dropdown(t)
        self.y_axis.setAccessibleName('Y axis of the heatmap')
        self.y_axis.chosen.connect(lambda i: self._set_axis('y', i))
        spans = [S.span_label(v) for v in S.SPANS]
        self.x_span = C.Dropdown(t, spans)
        self.x_span.setAccessibleName('Span of the X axis, in σ either side of the entered value')
        self.x_span.chosen.connect(lambda i: self._set_span('x', i))
        self.y_span = C.Dropdown(t, spans)
        self.y_span.setAccessibleName('Span of the Y axis, in σ either side of the entered value')
        self.y_span.chosen.connect(lambda i: self._set_span('y', i))
        self.grid = C.Dropdown(t, [S.grid_label(n) for n in S.GRIDS])
        self.grid.setAccessibleName('Grid of the heatmap, cells per axis')
        self.grid.chosen.connect(self._set_grid)
        self.heatmap_part = _widget(
            C.vbox(
                C.label('X axis', 'label', 'secondary'),
                C.hbox(self.x_axis, None, self.x_span, spacing=2),
                4,
                C.label('Y axis', 'label', 'secondary'),
                C.hbox(self.y_axis, None, self.y_span, spacing=2),
                4,
                C.label('Grid', 'label', 'secondary'),
                C.hbox(self.grid, None),
                C.wrapped(
                    'A σ axis spans the σ chosen either side of the entered value; a range axis spans its range.',
                    'small',
                    'tertiary',
                ),
                spacing=2,
            )
        )
        self.problem = C.Problem(t)
        run = _widget(
            C.vbox(
                C.label('Mode', 'label', 'secondary'),
                self.mode,
                4,
                self.indices_part,
                self.heatmap_part,
                self.problem,
                spacing=2,
            )
        )
        # Error sources
        self.sources_box = C.vbox(spacing=1)
        self.edit_inputs = C.link_button('Edit in Input uncertainty  →')
        self.edit_inputs.clicked.connect(lambda: self.view_requested.emit('Input uncertainty'))
        sources = _widget(C.vbox(_widget(self.sources_box), 2, C.hbox(self.edit_inputs, None), spacing=0))
        # This run
        self.run_box = C.vbox(spacing=0)
        this_run = _widget(self.run_box)
        # Display
        self.axis = C.Segmented(t, ['Log₁₀', 'Linear'], 0 if form.log_axis else 1)
        self.axis.setAccessibleName('Kₐ axis of the plots: log₁₀ or linear')
        self.axis.changed.connect(self._set_axis_scale)
        display = _widget(C.vbox(C.label('Kₐ axis', 'label', 'secondary'), self.axis, spacing=2))

        self.sections = {
            'run': C.section(t, 'Run', run, first=True),
            'sources': C.section(t, 'Error sources', sources),
            'this run': C.section(t, 'This run', this_run),
            'display': C.section(t, 'Display', display, open_=False),
        }
        self.unavailable = C.wrapped('', 'small', 'tertiary')
        content = QWidget()
        content.setLayout(C.vbox(self.unavailable, *self.sections.values(), spacing=0))
        return content

    # ------------------------------------------------------------------
    # The settings, edited
    # ------------------------------------------------------------------

    def _edited(self) -> None:
        self.model.analysis_edited()

    def _set_mode(self, index: int) -> None:
        self.model.analysis.mode = SensitivityMode.SOBOL if index == 0 else SensitivityMode.HEATMAP
        self._edited()

    def _set_size(self, index: int) -> None:
        self.model.analysis.n_samples = S.SAMPLE_SIZES[index]
        self._edited()

    def _set_fixed_seed(self, on: bool) -> None:
        self.model.analysis.fixed_seed = on
        self._edited()

    def _set_seed(self, text: str) -> None:
        self.model.analysis.seed_text = text
        self._edited()

    def _set_axis(self, which: str, index: int) -> None:
        key = list(self.model.settings.input_labels)[index]
        setattr(self.model.analysis, f'{which}_key', key)
        self._edited()

    def _set_span(self, which: str, index: int) -> None:
        setattr(self.model.analysis, f'{which}_span', S.SPANS[index])
        self._edited()

    def _set_grid(self, index: int) -> None:
        self.model.analysis.grid = S.GRIDS[index]
        self._edited()

    def _set_axis_scale(self, index: int) -> None:
        self.model.analysis.log_axis = index == 0
        self._edited()

    def set_locked(self, locked: bool) -> None:
        """Lock the settings that feed a run while one goes (*locked*); Display stays free."""
        self.locked = locked
        for control in (
            self.mode,
            self.size,
            self.seed_check,
            self.x_axis,
            self.y_axis,
            self.x_span,
            self.y_span,
            self.grid,
        ):
            control.setEnabled(not locked)
        self.seed.setEnabled(not locked and self.model.analysis.fixed_seed)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def badge(self) -> str | None:
        """The summary beside the title: what the run on show was made with, else what the next one will be."""
        model = self.model
        if not projectable(model.settings.assay_type):
            return None
        shown = model.sensitivity_result if model.sensitivity_note is None else None
        return S.badge(shown, model.analysis)

    def has_plot(self) -> bool:
        return bool(self.histograms or self.charts or self.heatmap_figures)

    def open_source_plots(self, ka_key: str) -> None:
        """Open the window of Kₐ against each source for *ka_key*."""
        result = self.model.sensitivity_result
        plots, note = S.source_plots(result, ka_key)
        window = SourcePlotsWindow(
            self.t,
            plots,
            note,
            plain_label(S.ka_name(ka_key)),
            self.model.analysis.log_axis,
            self.model.plot_appearance.text_step,
            self.parent,
        )
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        window.destroyed.connect(lambda *_: self.windows.remove(window) if window in self.windows else None)
        self.windows.append(window)
        window.show()

    def export_figure(self) -> QWidget:
        """The figure :meth:`export_image` saves, laid out and shown off screen; the caller closes it.

        Drawn again in the light theme on white, at the session's plot text: the run's callouts
        as notes; per binding constant its spread, the samples with both readings, the share of
        the variance by source and the notes that qualify them; for a heatmap, each map with its
        colour bar. Each part stands under a head as a saved plot's is (:func:`figure_head`).
        """
        model = self.model
        result = model.sensitivity_result
        step = model.plot_appearance.text_step
        light = Theme(dark=False)
        figure = C.Figure(light)
        lay = C.vbox(spacing=0)
        fit = self._fit()
        log = model.analysis.log_axis
        width = SIZE['export-width']

        def notes(texts: list[str]) -> None:
            for text in texts:
                if lay.count():
                    lay.addSpacing(space(2))
                lay.addWidget(C.PaintedNote(light, text, 'small', width, plot_font(step, 'tick')))

        notes([f'{escape(c.title)}. {escape(c.body)}' for c in S.callouts(result, fit, None)])
        first = not lay.count()
        if result.mode is SensitivityMode.HEATMAP:
            for hm in S.heatmaps(result, model.settings.condition_units, log):
                if not first:
                    lay.addSpacing(space(7))
                first = False
                title = f'{hm.name} over {hm.x_label} and {hm.y_label}'
                lay.addWidget(figure_head(light, title, '', None, width, (), step))
                fig = HeatmapFigure(light, hm, step, interactive=False)
                fig.setFixedHeight(SIZE['export-width'] // 2)
                lay.addWidget(fig)
        else:
            for block in S.ka_blocks(result, fit, log):
                if not first:
                    lay.addSpacing(space(7))
                first = False
                lines = [S.figure_caption(result, block)]
                if block.histogram is not None and block.histogram.fold:
                    lines.append(block.histogram.fold)
                lay.addWidget(figure_head(light, plain_label(block.name), '', None, width, lines, step))
                if block.histogram is not None:
                    lay.addWidget(SampleHistogram(light, block.histogram, step))
                if block.chart is not None and block.chart.rows:
                    lay.addSpacing(space(5))
                    head = 'Share of the variance, by source'
                    lay.addWidget(figure_head(light, head, '', IndexLegend(light), width, (), step))
                    lay.addWidget(IndexChartView(light, block.chart, self._name_width(block)))
                notes(S.figure_notes(block))
        figure.setLayout(lay)
        figure.setFixedWidth(SIZE['export-width'])
        figure.adjustSize()
        figure.show()
        QApplication.processEvents()
        return figure

    def export_image(self, path: str) -> None:
        """Save the plots of the run on show to *path* (PNG), in the light theme on white."""
        figure = self.export_figure()
        try:
            export_widget(figure, path, width_px=2 * SIZE['export-width'])
        finally:
            figure.close()
            figure.deleteLater()

    # ------------------------------------------------------------------
    # Drawing from the model
    # ------------------------------------------------------------------

    def _fit(self):
        fit, note = self.model.fit_view()
        return fit if note is None else None

    def _restyle(self) -> None:
        bar = self.area.verticalScrollBar()
        position = bar.value()
        self.refresh()
        QTimer.singleShot(0, lambda: bar.setValue(position))

    def _on_changed(self, what: Change) -> None:
        drawn_from = (
            Change.DATA
            | Change.RESULTS
            | Change.SENSITIVITY
            | Change.RUN
            | Change.BINDING
            | Change.UNCERTAINTY
            | Change.ANALYSIS
            | Change.APPEARANCE
        )
        if what & drawn_from:
            self.refresh()

    def refresh(self) -> None:
        model = self.model
        settings = model.settings
        result = model.sensitivity_result
        note = model.sensitivity_note
        running = model.sensitivity_running()
        has_ka = projectable(settings.assay_type)
        has_data = model.measurement_set is not None
        shown = result if note is None else None
        shortcut = QKeySequence(S.RUN_ANALYSIS_KEY).toString(QKeySequence.SequenceFormat.NativeText)
        if not has_ka:
            empty = S.NO_KA
        elif result is None:
            empty = S.RUNNING if running else S.empty_sentence(has_data, settings.errors.varies, shortcut)
        else:
            empty = ''
        self.empty.setText(empty)
        self.empty.setVisible(bool(empty))
        nothing = has_ka and has_data and not settings.errors.varies
        specs = S.callouts(
            result, self._fit(), note, running=running, error=model.sensitivity_error, nothing_varies=nothing
        )
        self._refresh_callouts(specs if has_ka else [])
        self._refresh_blocks(shown if has_ka else None)
        self._refresh_side(has_ka)

    def _refresh_callouts(self, specs) -> None:
        _clear(self.callout_box)
        self.callouts = list(specs)
        for spec in specs:
            callout = C.Callout(self.t, spec.tone, spec.title, spec.body, spec.action or None)
            target = {
                S.EDIT_INPUTS: 'Input uncertainty',
                S.COMPARE: 'Fit results',
                'Review in Ka confidence': 'Ka confidence',
            }.get(spec.action)
            if target is not None:
                callout.action.clicked.connect(lambda _=False, v=target: self.view_requested.emit(v))
            self.callout_box.addWidget(callout)
        self.callout_host.setVisible(bool(specs))

    def _refresh_blocks(self, result) -> None:
        """Draw the blocks of *result*, the run on show, unless they are drawn from it already as they would be now.

        A redraw of the same run — a fit starting, a note, Display, a theme — keeps the
        what-if chosen and any window of Kₐ against each source; another run starts both
        afresh.
        """
        fit = self._fit() if result is not None else None
        units = tuple(sorted(self.model.settings.condition_units.items()))
        step = self.model.plot_appearance.text_step
        key = (result, fit, self.model.analysis.log_axis, self.t.dark, units, step)
        drawn, self.drawn = self.drawn, key
        if drawn is not None and drawn[0] is result and drawn[1] is fit and drawn[2:] == key[2:]:
            return
        if drawn is None or drawn[0] is not result:
            self.what_if_choices = {}
            for window in self.windows:
                window.close()
            self.windows = []
        for window in self.windows:
            window.set_step(step)
        _clear(self.blocks_box)
        _clear(self.head_box)
        self.head_host.hide()
        self.blocks, self.histograms, self.charts, self.tables, self.heatmap_figures = [], [], [], [], []
        self.what_ifs = {}
        self.blocks_host.setVisible(result is not None)
        if result is None:
            return
        log = self.model.analysis.log_axis
        if result.mode is SensitivityMode.HEATMAP:
            maps = S.heatmaps(result, self.model.settings.condition_units, log)
            for i, hm in enumerate(maps):
                if i:
                    self.blocks_box.addSpacing(space(6))
                title = f'{hm.name} over {hm.x_label} and {hm.y_label}'
                self.blocks_box.addWidget(C.label(title, 'body-strong'))
                self.blocks_box.addSpacing(space(2))
                figure = HeatmapFigure(self.t, hm, step)
                self.heatmap_figures.append(figure)
                self.blocks_box.addWidget(figure)
            self.blocks_box.addSpacing(space(2))
            self.blocks_box.addWidget(
                C.wrapped(
                    'Each cell is one fit with the two inputs held at its values; the diamond marks the inputs as '
                    'entered. A cell left empty has no fit.',
                    'small',
                    'tertiary',
                )
            )
            return
        self.blocks = S.ka_blocks(result, fit, log)
        many = len(self.blocks) > 1
        for i, block in enumerate(self.blocks):
            if i:
                self.blocks_box.addSpacing(space(7))
                self.blocks_box.addWidget(C.hairline())
                self.blocks_box.addSpacing(space(5))
            # One constant's headline stands above the run's callouts (DESIGN.md §3); with two,
            # the callouts are about both, so they stand above both blocks.
            head = self.blocks_box if many else self.head_box
            if many:
                head.addWidget(C.label(block.name, 'body-strong', rich=True))
                head.addSpacing(space(3))
            head.addLayout(self._hero(block))
            self._add_block(result, block, first=i == 0 and not many)
        self.head_host.setVisible(not many)

    def _name_width(self, block: S.KaBlock) -> int:
        """The width of the Source column: the widest source name and a gap, shared by the chart and the table."""
        names = [r.name for r in block.chart.rows] if block.chart is not None else []
        names += [S.INTERACTIONS, S.ALL_SOURCES, 'Source']
        return math.ceil(max(C.rich_width(n, 'body') for n in names)) + space(5)

    def _add_block(self, result, block: S.KaBlock, first: bool) -> None:
        """Everything of *block* under its headline; the *first* one's follows the run's callouts."""
        t, box = self.t, self.blocks_box
        for i, spec in enumerate(block.callouts):
            if i or not first:
                box.addSpacing(space(4))
            box.addWidget(C.Callout(t, spec.tone, spec.title, spec.body))
        name_w = self._name_width(block)
        if block.chart is not None:
            if box.count():
                box.addSpacing(space(6))
            head = C.hbox(C.label('Share of the variance, by source', 'body-strong'), None, IndexLegend(t), spacing=3)
            box.addLayout(head)
            box.addSpacing(space(2))
            chart = IndexChartView(t, block.chart, name_w)
            self.charts.append(chart)
            box.addWidget(chart)
            for text in block.chart.notes:
                box.addSpacing(space(1))
                box.addWidget(C.copyable(C.wrapped(text, 'small', 'tertiary', rich=True)))
        if block.budget is not None:
            box.addSpacing(space(6))
            box.addLayout(
                C.hbox(
                    C.label('Variance budget', 'body-strong'),
                    None,
                    C.label(block.budget.caption, 'small', 'tertiary'),
                    spacing=3,
                )
            )
            box.addSpacing(space(2))
            box.addWidget(self._budget(block.budget, name_w))
            for text in block.budget.notes:
                box.addSpacing(space(1))
                box.addWidget(C.wrapped(text, 'small', 'tertiary'))
        if block.what_if:
            box.addSpacing(space(6))
            box.addWidget(C.label('What if one source were known better', 'body-strong'))
            box.addSpacing(space(3))
            box.addWidget(self._what_if(result, block))

    def _hero(self, block: S.KaBlock) -> QLayout:
        t, spread = self.t, block.spread
        sec = t['text-secondary']
        title = C.label(spread.title, 'label', 'secondary', rich=True)
        factor = C.copyable(C.label(spread.factor, 'title'))
        decades = C.copyable(C.label(spread.decades, 'body', 'secondary'))
        value_row = C.hbox(factor, decades, None, spacing=3)
        value_row.setAlignment(factor, Qt.AlignmentFlag.AlignBottom)
        value_row.setAlignment(decades, Qt.AlignmentFlag.AlignBottom)
        # Hidden, never shown, before they have a parent: a parentless widget shown is a window of its own.
        for widget in (factor, decades):
            widget.setToolTip(spread.tooltip)
            if not spread.factor:
                widget.hide()
        missing = C.wrapped(spread.missing, 'body', 'secondary')
        if not spread.missing:
            missing.hide()
        centre = C.copyable(
            C.wrapped(
                f'<span style="color:{sec}">Centred on</span> <b>{spread.centre}</b>'
                f'<span style="color:{sec}">, the fit at the inputs as entered</span>',
                'number',
                None,
                rich=True,
            )
        )
        left = _widget(C.vbox(title, value_row, missing, 1, centre, None, spacing=1))
        left.setFixedWidth(SIZE['headline'])
        right_items = []
        if block.histogram is not None:
            link = C.link_button('Plot against each source  →')
            link.setAccessibleName(f'Plot {plain_label(block.name)} against each source')
            link.clicked.connect(lambda _=False, key=block.key: self.open_source_plots(key))
            # A withheld constant's samples carry no fold, so its key names none.
            key = [BarChip(t), C.label(block.histogram.fold, 'small', 'secondary')] if block.histogram.fold else []
            key_row = C.hbox(*key, None, link, spacing=2)
            histogram = SampleHistogram(t, block.histogram, self.model.plot_appearance.text_step)
            self.histograms.append(histogram)
            right_items = [key_row, histogram]
        right = _widget(C.vbox(*right_items, None, spacing=2))
        right.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        return C.hbox(left, right, spacing=7)

    def _budget(self, budget: S.BudgetTable, name_w: int) -> QWidget:
        t = self.t
        roles = [('body', None), ('body', 'secondary'), ('number', None), ('number', None), ('number', None)]
        table = C.Table(t, [(head, role, tone) for head, (role, tone) in zip(budget.headers, roles)], gap=5)

        def html(cell: S.Cell, strong: bool = False) -> str:
            text = f'<b>{cell.value}</b>' if strong and cell.value != S.NONE else cell.value
            if cell.quiet:
                text = f'<span style="color:{t["text-secondary"]}">{text}</span>'
            if cell.interval:
                text += f' <span style="color:{t["text-tertiary"]}">{cell.interval}</span>'
            return text

        rows = [[html(cell) for cell in row] for row in budget.rows]
        rows.append([html(cell, strong=True) for cell in budget.total])
        table.set_rows(rows)
        table.grid.setColumnStretch(0, 0)
        table.grid.setColumnMinimumWidth(0, name_w - space(5))
        table.grid.setColumnStretch(2, 1)
        self.tables.append(table)
        return table

    def _what_if(self, result, block: S.KaBlock) -> QWidget:
        t = self.t
        sources = block.what_if
        names = [S.source_label(S._assay(result), key) for key in sources]
        pick = C.Dropdown(t, names)
        pick.setAccessibleName(f'Source to reduce, for {plain_label(block.name)}')
        to = C.Dropdown(t)
        to.setAccessibleName(f'Uncertainty to reduce it to, for {plain_label(block.name)}')
        sentence = C.copyable(C.label('', 'number', rich=True))
        detail = C.copyable(C.wrapped('', 'small', 'tertiary', rich=True))
        state = self.what_if_choices.setdefault(block.key, [0, S.WHAT_IF_RATIOS.index(S.WHAT_IF_START)])
        self.what_ifs[block.key] = (pick, to, sentence, detail, state)

        def update() -> None:
            source = sources[state[0]]
            options = S.what_if_targets(result, source)
            ratio, text = options[state[1]]
            pick.set_current(state[0])
            to.set_options([o for _r, o in options], state[1])
            answer = S.what_if_answer(result, block.key, source, ratio)
            quiet = f'<span style="color:{t["text-secondary"]}">'
            if answer.after:
                sentence.setText(f'{quiet}{answer.lead}</span> {answer.before} {quiet}to</span> {answer.after}')
            else:
                sentence.setText('')
            detail.setText(answer.detail)

        def choose_source(i: int) -> None:
            state[0] = i
            update()

        def choose_target(i: int) -> None:
            state[1] = i
            update()

        pick.chosen.connect(choose_source)
        to.chosen.connect(choose_target)
        update()
        controls = C.hbox(
            C.label('Reduce', 'body', 'secondary'),
            pick,
            C.label('to', 'body', 'secondary'),
            to,
            3,
            sentence,
            None,
            spacing=3,
        )
        return _widget(C.vbox(controls, 2, detail, spacing=0))

    # ------------------------------------------------------------------
    # Side panel
    # ------------------------------------------------------------------

    def _refresh_side(self, has_ka: bool) -> None:
        model = self.model
        form = model.analysis
        settings = model.settings
        self.unavailable.setText(S.NO_KA)
        self.unavailable.setVisible(not has_ka)
        for section in self.sections.values():
            section.setVisible(has_ka)
        if not has_ka:
            return
        heatmap = form.mode is SensitivityMode.HEATMAP
        self.mode.set_current(1 if heatmap else 0)
        self.size.set_current(S.SAMPLE_SIZES.index(form.n_samples))
        self.indices_part.setVisible(not heatmap)
        self.heatmap_part.setVisible(heatmap)
        errors = settings.errors
        labels = dict(settings.input_labels)
        if TITRANT in labels:  # named as the chart, the budget and the source plots name it
            labels[TITRANT] = S.source_label(settings.assay_type, TITRANT)
        n_sources = len(errors.source_specs()) + (errors.additions is not None)
        n_inputs = len(labels)
        self.size_note.setText(S.sample_size_note(form.n_samples, n_sources, n_inputs))
        self.seed_check.set_checked(form.fixed_seed)
        self.seed.set_text(form.seed_text)
        self.seed.setEnabled(form.fixed_seed and not self.locked)
        self.seed_note.setText('On: the same draws every run.' if form.fixed_seed else 'Off: fresh draws each run.')
        keys = list(labels)
        names = [labels[k] for k in keys]
        for dropdown, key in ((self.x_axis, form.x_key), (self.y_axis, form.y_key)):
            dropdown.set_options(names, keys.index(key) if key in labels else -1)
        x_shown, y_shown = form.spans_shown(errors)
        self.x_span.set_current(S.SPANS.index(form.x_span))
        self.y_span.set_current(S.SPANS.index(form.y_span))
        self.x_span.setVisible(x_shown)
        self.y_span.setVisible(y_shown)
        self.grid.set_current(S.GRIDS.index(form.grid))
        self.problem.show_problems(model.analysis_problems())
        # Error sources
        _clear(self.sources_box)
        units = {key: f.unit for key in labels if (f := condition_field(settings.assay_type, key)) is not None}
        if heatmap:
            # A heatmap sweeps its two axes and holds every other input at its entered value.
            axes = {key: spec for key, spec in errors.specs.items() if key in (form.x_key, form.y_key)}
            stated = S.stated_sources(ErrorModel(specs=axes), labels, units)
        else:
            stated = S.stated_sources(errors, labels, units)
        if stated:
            grid = QGridLayout()
            grid.setContentsMargins(QMargins())
            grid.setHorizontalSpacing(space(3))
            grid.setVerticalSpacing(space(1))
            for i, source in enumerate(stated):
                value = C.label(source.stated, 'small-number', 'secondary')
                value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
                grid.addWidget(C.BreakingLabel(source.name, 'body'), i, 0)
                grid.addWidget(value, i, 1, Qt.AlignmentFlag.AlignTop)
            grid.setColumnStretch(0, 1)
            self.sources_box.addWidget(_widget(grid))
        if not stated:
            self.sources_box.addWidget(
                C.wrapped('Every input is fixed: the analysis has nothing to vary.', 'small', 'tertiary')
            )
        self.sections['sources'].header.set_trailing(f'{len(stated)} varying')
        # This run
        _clear(self.run_box)
        result = model.sensitivity_result
        if result is None:
            self.run_box.addWidget(C.wrapped('No run yet.', 'small', 'tertiary'))
        elif model.sensitivity_note is not None:
            # A run that no longer describes the data gives none of its facts, as on the canvas.
            self.run_box.addWidget(
                C.wrapped('Hidden with its results: see the note on the canvas.', 'small', 'tertiary')
            )
        else:
            grid = QGridLayout()
            grid.setContentsMargins(QMargins())
            grid.setHorizontalSpacing(space(5))
            grid.setVerticalSpacing(space(4))
            for i, stat in enumerate(S.this_run(result, model.sensitivity_seconds, model.sensitivity_workers)):
                grid.addWidget(self._stat(stat), i // 2, i % 2, Qt.AlignmentFlag.AlignTop)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            self.run_box.addWidget(_widget(grid))
            seed = S.seed_stat(result)
            if seed is not None:
                self.run_box.addSpacing(space(4))
                self.run_box.addWidget(self._stat(seed))
        self.sections['display'].header.set_trailing('Log₁₀ axis' if form.log_axis else 'Linear axis')
        self.axis.set_current(0 if form.log_axis else 1)
        self.set_locked(model.sensitivity_running() or model.fit_running())

    def _stat(self, stat: S.Stat) -> QWidget:
        items = [C.label(stat.name, 'small', 'secondary'), C.copyable(C.label(stat.value, 'number-strong'))]
        if stat.note:
            items.append(C.wrapped(stat.note, 'small', 'tertiary'))
        return _widget(C.vbox(*items, spacing=1))
