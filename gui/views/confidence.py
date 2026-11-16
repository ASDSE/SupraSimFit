"""Ka confidence: the two readings of each binding constant, their profiles and the joint region (DESIGN.md §8).

Canvas: the two readings side by side — Input-aware (accent badge) and Inputs as entered,
with *Split* where its interval has a gap; the one reading where every input is exact —
then any callout, and **one profile plot per binding constant** holding both profiles on
the scaled-drop axis, so both cross one cut-off line at 1 where their intervals end. Each
plot carries the best fit of each reading, its readout card (the scaled drop of each curve
under the pointer, and whether that Ka is accepted), the enlarge tool and the image export,
and under it a strip of the Ka each reading accepts. With two binding constants the plots
stack, one per constant, with the joint region below them. Side panel *Notes*, headed by
*Reading this plot →*: the input shifts, how to read the curves, a split interval, open
sides, the one-step test of a second constant, what the intervals rest on and what widened
them.

Everything is read from the session model — the fit it reports and the Ka profile of that
fit — and redrawn when the model says either changed; the text and numbers come from
:mod:`gui.confidence`.
"""

from __future__ import annotations

import math

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QMargins, QObject, QPointF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QFontMetrics
from PyQt6.QtWidgets import QApplication, QFrame, QGridLayout, QLayout, QScrollArea, QSizePolicy, QWidget

from gui import confidence as CF
from gui import results as R
from gui.design import components as C
from gui.design.appearance import appearance, theme
from gui.design.plot_theme import apply_plot_theme, axis_box, least_height, px
from gui.design.tokens import SIZE, Theme, font, plot_font, space
from gui.plotting.export import export_widget, figure_head
from gui.plotting.labels import THIN, fmt_param_plain
from gui.session_model import Change, SessionModel

#: The legend row of a profile plot: both readings, their accepted Ka and the best fit.
LEGEND = [
    ('line', R.INPUT_AWARE),
    ('line-secondary', R.AS_ENTERED),
    ('bars', 'Accepted Kₐ'),
    ('diamond', 'Best fit'),
]
LEGEND_ONE = [('line-secondary', R.AS_ENTERED), ('bar', 'Accepted Kₐ'), ('diamond', 'Best fit')]


def _clear(layout: QLayout) -> None:
    """Take every widget and nested layout out of *layout*."""
    while layout.count():
        item = layout.takeAt(0)
        if item.widget() is not None:
            C.drop(item.widget())
        elif item.layout() is not None:
            _clear(item.layout())


def _diamond_symbol():
    """The best-fit diamond as a pyqtgraph symbol: a unit path, scaled by the item's size."""
    return C.diamond(QPointF(0, 0), 1.0)


def _dotted(t: Theme, color: str):
    pen = pg.mkPen(t.q(color), width=px(1.25), style=Qt.PenStyle.DashLine)
    pen.setDashPattern([2, 3])
    return pen


def _tag(t: Theme, text: str, anchor, step: str, filled: bool = False) -> pg.TextItem:
    """An in-plot label in ``text-secondary`` at the tick labels' size of plot text *step*; *filled* backs it with
    the plot surface, for marks running up to it."""
    item = pg.TextItem(text, color=t.q('text-secondary'), anchor=anchor, fill=t.q('bg-surface') if filled else None)
    item.setFont(plot_font(step, 'tick'))
    item.setZValue(5)
    return item


class ProfileFigure(QWidget):
    """One binding constant's profile plot over the strip of the Ka each reading accepts.

    The plot reads each curve's scaled drop against one cut-off line at 1; the strip shares
    its log-Ka axis. Its text is at plot text *step*. With *interactive* the pointer draws a
    hairline with its Ka at the top and the readout card reads every curve there; elsewhere
    the card reads the reported estimate.
    """

    def __init__(self, t: Theme, plot: CF.ProfilePlot, step: str, interactive: bool = True):
        super().__init__()
        self.t, self.plot, self.step = t, plot, step
        self.main = pg.PlotWidget()
        self.main.setFrameShape(QFrame.Shape.NoFrame)
        pi = apply_plot_theme(self.main, t, '', CF.Y_TITLE, step, [(v, f'{v:g}') for v in CF.Y_TICKS])
        bottom = pi.getAxis('bottom')
        bottom.setTicks([plot.ticks])
        bottom.setStyle(showValues=False, tickLength=space(2))
        bottom.showLabel(False)
        bottom.setHeight(space(2) + space(1))
        pi.setXRange(*plot.x_range, padding=0)
        pi.setYRange(*CF.Y_RANGE, padding=0)
        pi.getViewBox().setMouseEnabled(x=False, y=False)
        self.curves: dict[str, pg.PlotDataItem] = {}
        self.markers: dict[str, pg.ScatterPlotItem] = {}
        self.risers: list[pg.PlotDataItem] = []
        self._draw(pi)
        self.strip = self._strip()

        self.card = C.ReadoutCard(t, self.main)
        self.tag = C.ValueTag(t, self.main)
        self.tag.hide()
        self.hair = pg.InfiniteLine(angle=90, pen=_dotted(t, 'text-tertiary'), movable=False)
        self.hair.setZValue(4.5)
        self.hair.hide()
        pi.addItem(self.hair, ignoreBounds=True)
        self.dots = [
            pg.ScatterPlotItem(
                size=SIZE['pointer-dot'], brush=pg.mkBrush(t.q(c.color)), pen=pg.mkPen(t['bg-surface'], width=px(2))
            )
            for c in plot.curves
        ]
        for dot in self.dots:
            dot.setZValue(5)
            pi.addItem(dot, ignoreBounds=True)
        reported = plot.curves[-1]
        self.default_x = reported.estimate[0] if reported.estimate is not None else sum(plot.x_range) / 2
        self.show_at(self.default_x, pointer=False)
        pi.getViewBox().sigResized.connect(self._place)
        if interactive:
            self._proxy = pg.SignalProxy(self.main.scene().sigMouseMoved, rateLimit=60, slot=self._moved)
        else:
            self.card.hide()

        self.setLayout(C.vbox(self.main, 2, self.strip, spacing=0))
        self.setAccessibleName(f'Profile plot of {plot.name}')

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw(self, pi: pg.PlotItem) -> None:
        t, plot = self.t, self.plot
        if plot.band is not None:
            band = pg.LinearRegionItem(
                values=plot.band,
                movable=False,
                brush=pg.mkBrush(t.q('accent', 0.07 if t.dark else 0.08)),
                pen=pg.mkPen(None),
            )
            for line in band.lines:
                line.setPen(pg.mkPen(None))
            band.setZValue(-11)
            pi.addItem(band, ignoreBounds=True)
            self.band = band
        cut = pg.InfiniteLine(pos=CF.CUT, angle=0, pen=_dotted(t, 'text-secondary'), movable=False)
        cut.setZValue(1.5)
        pi.addItem(cut, ignoreBounds=True)
        self.cut_line = cut
        label = _tag(t, plot.cut_label, (1, 1.05), self.step)
        label.setPos(plot.x_range[1], CF.CUT)
        pi.addItem(label, ignoreBounds=True)
        self.cut_label = label
        for curve in plot.curves:
            accent = curve.color == 'accent'
            pen = pg.mkPen(t.q(curve.color), width=px(2.25 if accent else 1.75))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            item = pg.PlotDataItem(curve.x, curve.y, pen=pen, antialias=True, connect='finite')
            item.setZValue(3.2 if accent else 3)
            pi.addItem(item, ignoreBounds=True)
            self.curves[curve.label] = item
            # The jump where the cut-off steps, dotted so it reads as a step of the test, not as the curve.
            for x, y0, y1 in curve.risers:
                riser = pg.PlotDataItem([x, x], [y0, y1], pen=_dotted(t, curve.color))
                riser.setZValue(2.9)
                pi.addItem(riser, ignoreBounds=True)
                self.risers.append(riser)
            if curve.estimate is not None:
                marker = pg.ScatterPlotItem(
                    x=[curve.estimate[0]],
                    y=[curve.estimate[1]],
                    symbol=_diamond_symbol(),
                    size=SIZE['diamond'],
                    brush=pg.mkBrush(t.q(curve.color)),
                    pen=pg.mkPen(t['bg-surface'], width=px(2)),
                )
                marker.setZValue(4)
                pi.addItem(marker, ignoreBounds=True)
                self.markers[curve.label] = marker

    def _strip(self) -> pg.PlotWidget:
        """The accepted Ka of each reading as a lane under the plot, on its x axis; the reported reading on top.

        Each lane's name sits at its left end and its track starts after the name, so no
        line runs through the text; where a name would reach the lane's first bar, the axis
        it shares with the profile opens further left, just far enough for every name to clear it.
        """
        t, plot = self.t, self.plot
        pw = pg.PlotWidget()
        pw.setFrameShape(QFrame.Shape.NoFrame)
        pi = apply_plot_theme(pw, t, plot.x_title, '', self.step, [])
        left = pi.getAxis('left')
        left.showLabel(False)
        left.setPen(pg.mkPen(None))
        pi.getAxis('bottom').setTicks([plot.ticks])
        pi.setXLink(self.main.getPlotItem())
        lanes = list(reversed(plot.curves))
        # A lane is a control tall, or as tall as its name and a step either side where the text is larger.
        pitch = max(SIZE['control'], QFontMetrics(plot_font(self.step, 'tick')).height() + 2 * space(1))
        pi.setYRange(-0.75, len(lanes) - 0.5, padding=0)
        vb = pi.getViewBox()
        vb.setMouseEnabled(x=False, y=False)
        self.bars: dict[str, list[pg.PlotDataItem]] = {}
        placed = []
        for i, curve in enumerate(lanes):
            y = len(lanes) - 1 - i
            track = pg.PlotDataItem(list(plot.x_range), [y, y], pen=pg.mkPen(t['border'], width=px(1)))
            track.setZValue(-5)
            pi.addItem(track, ignoreBounds=True)
            bars = []
            for lo, hi in curve.stretches:
                pen = pg.mkPen(t.q(curve.color), width=px(6))
                pen.setCapStyle(Qt.PenCapStyle.FlatCap)
                bar = pg.PlotDataItem([math.log10(lo), math.log10(hi)], [y, y], pen=pen)
                bar.setZValue(2)
                pi.addItem(bar, ignoreBounds=True)
                bars.append(bar)
            self.bars[curve.label] = bars
            name = _tag(t, curve.label, (0, 0.5), self.step, filled=True)
            pi.addItem(name, ignoreBounds=True)
            first = math.log10(curve.stretches[0][0]) if curve.stretches else plot.x_range[1]
            placed.append((y, name, track, first))

        def clear_names():
            width = vb.width()
            if width <= 0:
                return
            # The left edge at which every name, *room* px from it, ends before its lane's first bar: x0 + room·(x1 − x0)/w
            # ≤ first. It is set on the profile above, whose axis the strip follows, so the two stay on one axis.
            home, x1 = plot.x_range
            x0 = home
            for _y, name, _track, first in placed:
                room = space(1) + name.boundingRect().width() + space(2)
                if room < width:
                    x0 = min(x0, (first - room * x1 / width) / (1 - room / width))
            main = self.main.getPlotItem().getViewBox()
            if abs(main.viewRange()[0][0] - x0) > 1e-9 * (x1 - x0):
                main.setXRange(x0, x1, padding=0)
                return  # the range change runs this again
            dx = (x1 - x0) / width
            for y, name, track, _first in placed:
                name.setPos(x0 + space(1) * dx, y)
                track.setData([x0 + (space(1) + name.boundingRect().width() + space(2)) * dx, x1], [y, y])

        vb.sigResized.connect(clear_names)
        vb.sigXRangeChanged.connect(clear_names)
        clear_names()
        pw.setFixedHeight(axis_box(self.step)[1] + round((len(lanes) + 0.25) * pitch))
        return pw

    # ------------------------------------------------------------------
    # The pointer
    # ------------------------------------------------------------------

    def show_at(self, x: float, pointer: bool = True) -> None:
        """Read every curve at *x* (log₁₀ Ka) in the card; with *pointer* also draw the hairline, its Ka and the dots."""
        rows = CF.readout(self.plot, x)
        self.card.set_values(
            self.plot.readout_title(x),
            [(r.color, r.label, r.value, r.verdict, r.verdict == 'rejected') for r in rows],
        )
        self.hair.setVisible(pointer)
        self.tag.setVisible(pointer)
        for dot, curve in zip(self.dots, self.plot.curves):
            y = curve.at(x)
            shown = pointer and math.isfinite(y)
            dot.setData([x] if shown else [], [y] if shown else [])
        if pointer:
            self.hair.setPos(x)
            self.tag.set_text(self.plot.chip(x))
        self.pointer_x = x
        self._place()

    def _moved(self, event) -> None:
        vb = self.main.getPlotItem().getViewBox()
        pos = event[0]
        if vb.sceneBoundingRect().contains(pos):
            self.show_at(vb.mapSceneToView(pos).x())
        elif self.hair.isVisible():
            self.show_at(self.default_x, pointer=False)

    def leaveEvent(self, event) -> None:
        if self.hair.isVisible():
            self.show_at(self.default_x, pointer=False)
        super().leaveEvent(event)

    def _place(self, *_) -> None:
        """Put the card at the plot's top-right corner and the Ka tag at the top of the hairline."""
        vb = self.main.getPlotItem().getViewBox()
        rect = self.main.mapFromScene(vb.sceneBoundingRect()).boundingRect()
        self.card.move(rect.right() - self.card.width() - space(3), rect.top() + space(3))
        self.card.raise_()
        if self.tag.isVisible():
            top = self.main.mapFromScene(vb.mapViewToScene(QPointF(self.pointer_x, CF.Y_RANGE[1])))
            self.tag.move(round(top.x() - self.tag.width() / 2), rect.top())
            self.tag.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place()

    def minimumSizeHint(self) -> QSize:
        # An analysis plot's least height, or more where the plot's title along its axis needs it.
        held = least_height(self.main.getPlotItem()) + space(2) + self.strip.height()
        return QSize(super().minimumSizeHint().width(), max(SIZE['plot-min'], held))

    def sizeHint(self) -> QSize:
        # Its least height: the canvas lays out its height for its width from preferred heights,
        # and the plot takes whatever height the canvas has left over.
        return QSize(super().sizeHint().width(), self.minimumSizeHint().height())


class RegionFigure(QWidget):
    """The joint region of two binding constants: the accepted pairs, the best fit and each constant's own interval,
    its text at plot text *step*."""

    def __init__(self, t: Theme, region: CF.Region, step: str):
        super().__init__()
        self.t, self.region = t, region
        self.main = pg.PlotWidget()
        self.main.setFrameShape(QFrame.Shape.NoFrame)
        pi = apply_plot_theme(self.main, t, region.x_title, region.y_title, step, list(region.y_ticks))
        pi.getAxis('bottom').setTicks([region.x_ticks])
        x_lo, x_hi, y_lo, y_hi = region.extent
        rgba = np.zeros(region.accepted.shape + (4,), dtype=np.ubyte)
        fill = t.q('text-secondary', 0.34 if t.dark else 0.28)
        rgba[region.accepted] = fill.getRgb()
        self.image = pg.ImageItem(rgba, axisOrder='col-major', levels=(0, 255))
        self.image.setRect(x_lo, y_lo, x_hi - x_lo, y_hi - y_lo)
        self.image.setZValue(-5)
        pi.addItem(self.image)
        self.bands = []
        for axis, lo, hi in region.bands:
            band = pg.LinearRegionItem(
                values=(lo, hi),
                orientation='vertical' if axis == 'x' else 'horizontal',
                movable=False,
                brush=pg.mkBrush(t.q('text-secondary', 0.08)),
                pen=pg.mkPen(None),
            )
            for line in band.lines:
                line.setPen(pg.mkPen(None))
            band.setZValue(-10)
            pi.addItem(band)
            self.bands.append(band)
        self.best = pg.ScatterPlotItem(
            x=[region.best[0]],
            y=[region.best[1]],
            symbol=_diamond_symbol(),
            size=SIZE['diamond'],
            brush=pg.mkBrush(t.q('text-secondary')),
            pen=pg.mkPen(t['bg-surface'], width=px(2)),
        )
        self.best.setZValue(4)
        pi.addItem(self.best)
        pi.setRange(xRange=(x_lo, x_hi), yRange=(y_lo, y_hi), padding=0.02)
        pi.getViewBox().setMouseEnabled(x=False, y=False)
        self.setLayout(C.vbox(self.main, spacing=0))
        self.setAccessibleName('Joint region of the two binding constants')

    def minimumSizeHint(self) -> QSize:
        # An analysis plot's least height, or more where its title along the y axis needs it.
        return QSize(super().minimumSizeHint().width(), max(SIZE['plot-min'], least_height(self.main.getPlotItem())))

    def sizeHint(self) -> QSize:
        return QSize(super().sizeHint().width(), self.minimumSizeHint().height())


class ConfidenceView(QObject):
    """The canvas and side panel of Ka confidence over *model*; *parent* is the session.

    :attr:`reveal_requested` asks for the :class:`~gui.results.Place` a callout's action names
    (the conflict callout's the input shifts in *Notes*), :attr:`save_requested` for the plot
    image; the session answers each, and opens the Help window at Ka confidence from
    :attr:`guide_link`.
    """

    reveal_requested = pyqtSignal(object)
    save_requested = pyqtSignal()

    def __init__(self, model: SessionModel, parent: QWidget):
        super().__init__(parent)
        self.model, self.parent, self.t = model, parent, theme()
        self.callouts: list[R.CalloutSpec] = []
        self.figures: list[ProfileFigure] = []
        self.region_figure: RegionFigure | None = None
        self.sections: dict[str, QWidget] = {}
        self.canvas = self._build_canvas()
        self.side = self._build_side()
        self.guide_link = C.link_button('Reading this plot  →')
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
        self.empty_state = C.EmptyState(self.t)
        self.header_host = QWidget()
        self.header_box = C.vbox(spacing=5)
        self.header_host.setLayout(self.header_box)
        self.callout_host = QWidget()
        self.callout_box = C.vbox(spacing=3, margins=(0, 5, 0, 0))
        self.callout_host.setLayout(self.callout_box)
        self.message = C.wrapped('', 'body', 'secondary')
        self.plots_host = QWidget()
        # Each plot's header sits tight above its plot; the plots stand further apart (_refresh_plots).
        self.plots_box = C.vbox(spacing=0)
        self.plots_host.setLayout(self.plots_box)
        lay = C.vbox(
            self.header_host, self.callout_host, self.empty_state, self.message, spacing=0, margins=(6, 5, 6, 4)
        )
        lay.setStretchFactor(self.empty_state, 1)
        lay.addSpacing(space(6))
        lay.addWidget(self.plots_host, 1)
        # With no plot to fill the canvas, its spare height goes below the last part shown (_show_parts).
        lay.addStretch(0)
        content.setLayout(lay)
        self.content, self.canvas_box = content, lay
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setWidget(content)
        self.area = area
        self.enlarged = False
        return area

    def _build_side(self) -> QWidget:
        self.no_fit = C.wrapped('', 'small', 'tertiary')
        self.notes_box = C.vbox(spacing=0)
        content = QWidget()
        content.setLayout(C.vbox(self.no_fit, self.notes_box, spacing=0))
        return content

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def set_enlarged(self, on: bool) -> None:
        """Give the plots the whole canvas (*on*), the readings and callouts set aside, or put them back."""
        self.enlarged = on
        for tool in self.enlarge_tools:
            tool.setChecked(on)
        self._show_parts()

    def has_plot(self) -> bool:
        """Whether a profile plot is on the canvas, which the image export saves."""
        return bool(self.figures)

    def export_figure(self) -> QWidget:
        """The figure :meth:`export_image` saves, laid out and shown off screen; the caller closes it.

        Drawn again in the light theme on white, at the session's plot text, on the same
        scaled-drop axis, each plot under its title and legend and its readings in one line,
        set apart from the plot above it; the readout card is left out, a saved figure having
        no pointer.
        """
        fit = self._fit()
        profile = self.model.profile
        step = self.model.plot_appearance.text_step
        light = Theme(dark=False)
        figure = C.Figure(light)
        lay = C.vbox(spacing=0)
        width = SIZE['export-width']
        plots = [CF.profile_plot(fit, p) for p in profile.profiles.values()]
        headers = {h.key: h for h in CF.headers(fit)}

        def gap() -> None:
            if lay.count():
                lay.addSpacing(space(8))

        for plot in [p for p in plots if p is not None]:
            line = '; '.join(
                f'{r.label}: {" ".join(x for x in (r.qualifier.lower(), r.value, r.unit) if x)}, {r.level} {r.interval}'
                for r in headers[plot.key].readings
            )
            gap()
            lay.addWidget(figure_head(light, plot.name, '', C.LegendRow(light, _legend(plot)), width, [line], step))
            fig = ProfileFigure(light, plot, step, interactive=False)
            fig.setFixedHeight(SIZE['export-plot'])
            lay.addWidget(fig)
        region = CF.joint_region(fit, profile)
        if region is not None:
            gap()
            lay.addWidget(figure_head(light, 'Joint region', region.description, None, width, (), step))
            reg = RegionFigure(light, region, step)
            reg.setFixedHeight(SIZE['export-plot'])
            lay.addWidget(reg)
        figure.setLayout(lay)
        figure.setFixedWidth(SIZE['export-width'])
        figure.adjustSize()
        figure.show()
        QApplication.processEvents()
        return figure

    def export_image(self, path: str) -> None:
        """Save the profile plots — and the joint region of two binding constants — to *path* (PNG)."""
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
        """Draw the plots again in the theme now on screen, the canvas kept where it was scrolled to."""
        bar = self.area.verticalScrollBar()
        position = bar.value()
        self.refresh()
        QTimer.singleShot(0, lambda: bar.setValue(position))

    def badge(self) -> str | None:
        """The summary beside the title: ``Profile likelihood · 95 %`` while a fit of a binding constant is shown."""
        return CF.badge(self._fit())

    def _on_changed(self, what: Change) -> None:
        if what & (Change.DATA | Change.RESULTS | Change.PROFILE | Change.RUN | Change.APPEARANCE):
            self.refresh()

    def refresh(self) -> None:
        model = self.model
        fit, note = model.fit_view()
        shown = fit if note is None else None
        empty = model.empty_view('Ka confidence')
        has_ka = shown is not None and empty is None
        ours = shown is not None and model.profiled_fit is shown
        profile = model.profile if ours else None
        pending = ours and model.profile_running()
        self.empty_state.show_empty(empty)
        self._refresh_headers(shown if has_ka else None, drawn=profile is not None)
        self._refresh_callouts(model.callouts('Ka confidence'))
        message = ''
        if has_ka and profile is None and not pending:
            error = model.profile_error if ours else None
            message = CF.failed_sentence(error) if error else CF.no_profile_sentence(model.measurement_set is not None)
        self.message.setText(message)
        self._refresh_plots(shown if has_ka else None, profile)
        if not self.figures:
            self.enlarged = False  # nothing left to enlarge, and no tool to put the readings back with
        self._refresh_side(shown, note, profile if has_ka else None, empty)
        self._show_parts()

    def _show_parts(self) -> None:
        self.header_host.setVisible(bool(self.header_box.count()) and not self.enlarged)
        self.callout_host.setVisible(bool(self.callouts) and not self.enlarged)
        self.message.setVisible(bool(self.message.text()))
        self.plots_host.setVisible(bool(self.figures))
        # With no plot to fill the canvas, its spare height goes to the empty state, else below the last part shown.
        self.canvas_box.setStretch(
            self.canvas_box.count() - 1, 0 if self.figures or self.empty_state.isVisibleTo(self.content) else 1
        )

    def _refresh_headers(self, fit, *, drawn: bool) -> None:
        """The readings of *fit*; *drawn* says whether its profile plots are drawn, which *Split* then points to."""
        _clear(self.header_box)
        if fit is None:
            return
        for header in CF.headers(fit):
            self.header_box.addWidget(self._header(header, drawn))

    def _header(self, header: CF.Header, drawn: bool) -> QWidget:
        """One binding constant's readings side by side, one grid so their rows share baselines."""
        grid = QGridLayout()
        grid.setContentsMargins(QMargins())
        grid.setHorizontalSpacing(space(6))
        grid.setVerticalSpacing(space(1))
        columns = [self._reading(header, r, drawn) for r in header.readings]
        for col, rows in zip(range(0, 2 * len(columns), 2), columns):
            for r, widget in enumerate(rows):
                widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
                grid.addWidget(widget, r, col)
            grid.setColumnStretch(col, 1)
        if len(columns) > 1:
            grid.addWidget(C.hairline(vertical=True), 0, 1, max(map(len, columns)), 1)
        else:
            grid.setColumnStretch(2, 1)
        w = QWidget()
        w.setLayout(grid)
        return w

    def _reading(self, header: CF.Header, reading: CF.Reading, drawn: bool) -> list[QWidget]:
        """The rows of one reading: name and badge, value, interval (with *Split*), and its reach."""
        role = 'metric' if reading.reported else 'title-number'
        name = C.hbox(C.label(header.name, 'label', 'secondary', rich=True), C.badge(reading.label, reading.tone), None)
        head = QWidget()
        head.setLayout(name)
        value = C.copyable(C.label(reading.value, role))
        unit_font = font('title')
        unit_font.setWeight(QFont.Weight.Normal)
        unit = C.label(reading.unit, 'title', 'secondary')
        unit.setFont(unit_font)
        value.setVisible(bool(reading.value))
        unit.setVisible(bool(reading.value))
        qualifier = C.label(reading.qualifier, 'title' if reading.reported else 'body', 'secondary')
        qualifier.setVisible(bool(reading.qualifier))
        row = C.hbox(qualifier, value, unit, None, spacing=2)
        for widget in (qualifier, value, unit):
            row.setAlignment(widget, Qt.AlignmentFlag.AlignBottom)
        values = QWidget()
        values.setLayout(row)
        # Two sizes of value share a baseline once the smaller is lifted by the difference in descent.
        if not reading.reported:
            lift = QFontMetrics(font('metric')).descent() - QFontMetrics(font(role)).descent()
            row.setContentsMargins(QMargins(0, 0, 0, max(0, lift)))
            values.setMinimumHeight(QFontMetrics(font('metric')).height())
        interval = C.copyable(C.label(reading.interval, 'number'))
        level = C.label(reading.level, 'number', 'secondary')
        parts = [level, interval]
        if reading.split:
            split = C.badge(R.SPLIT, 'neutral')
            split.setToolTip(CF.split_explained(drawn))
            parts.append(split)
        for widget in (level, interval):
            widget.setToolTip(reading.tooltip)
        line = QWidget()
        line.setLayout(C.hbox(*parts, None, spacing=3))
        rows = [head, values, line]
        if reading.reach:
            rows.append(C.copyable(C.label(reading.reach, 'small-number', 'tertiary')))
        return rows

    def _refresh_callouts(self, specs: list[R.CalloutSpec]) -> None:
        _clear(self.callout_box)
        self.callouts = list(specs)
        for spec in specs:
            callout = C.Callout(self.t, spec.tone, spec.title, spec.body, spec.action or None)
            if spec.place is not None:
                callout.action.clicked.connect(lambda _=False, place=spec.place: self.reveal_requested.emit(place))
            self.callout_box.addWidget(callout)

    def _refresh_plots(self, fit, profile) -> None:
        _clear(self.plots_box)
        self.figures, self.region_figure, self.enlarge_tools = [], None, []
        if fit is None or profile is None:
            return
        plots = [CF.profile_plot(fit, p) for p in profile.profiles.values()]
        many = len(plots) > 1
        box = self.plots_box
        step = self.model.plot_appearance.text_step

        def gap() -> None:
            if box.count():
                box.addSpacing(space(6))

        for key, plot in zip(profile.profiles, plots):
            gap()
            if plot is None:
                fixed = C.wrapped(
                    f'{fmt_param_plain(key)} is fixed by its bounds, so it has no profile.', 'body', 'secondary'
                )
                box.addWidget(fixed)
                continue
            figure = ProfileFigure(self.t, plot, step)
            self.figures.append(figure)
            box.addWidget(self._plot_header(plot.name if many else 'Profile', _legend(plot)))
            box.addSpacing(space(2))
            box.addWidget(figure, 1)
        region = CF.joint_region(fit, profile)
        if region is not None:
            self.region_figure = RegionFigure(self.t, region, step)
            title = C.hbox(C.label('Joint region', 'body-strong'), 3, C.label(region.description, 'small', 'tertiary'))
            title.addStretch(1)
            gap()
            box.addLayout(title)
            box.addSpacing(space(2))
            box.addWidget(self.region_figure, 1)

    def _plot_header(self, title: str, legend: list[tuple[str, str]]) -> C.PlotHeader:
        enlarge = C.tool_button(self.t, None, 'maximize')
        enlarge.setCheckable(True)
        enlarge.setChecked(self.enlarged)
        enlarge.setToolTip('Give the plots the whole canvas')
        enlarge.setAccessibleName('Enlarge the Ka confidence plots')
        enlarge.toggled.connect(self.set_enlarged)
        self.enlarge_tools.append(enlarge)
        save = C.tool_button(self.t, None, 'image')
        save.setToolTip('Save the plot as an image')
        save.setAccessibleName('Save the Ka confidence plots as an image')
        save.clicked.connect(self.save_requested)
        return C.PlotHeader(self.t, title, C.LegendRow(self.t, legend), [enlarge, 1, save])

    # ------------------------------------------------------------------
    # Notes
    # ------------------------------------------------------------------

    def _refresh_side(self, fit, note: str | None, profile, empty) -> None:
        _clear(self.notes_box)
        self.sections = {}
        self.no_fit.setVisible(fit is None or empty is not None)
        if note:
            self.no_fit.setText(f'The last fit is not shown. {note}')
        elif empty is not None:
            self.no_fit.setText(empty.sentence if fit is not None else f'{empty.title}.')
        if fit is None or empty is not None:
            return
        ms = self.model.measurement_set
        order = None if ms is None else list(ms.replica_ids)
        for i, section in enumerate(CF.notes(fit, profile, order)):
            widget = C.section(
                self.t,
                section.title,
                self._note_content(section),
                first=i == 0,
                trailing=section.trailing,
                flag='warning' if section.flag else '',
            )
            self.sections[section.key] = widget
            self.notes_box.addWidget(widget)

    def _note_content(self, section: CF.NoteSection) -> QWidget:
        paragraphs = section.paragraphs
        quiet_from = len(paragraphs) - section.quiet
        lay = C.vbox(spacing=2)
        for i, text in enumerate(paragraphs):
            lay.addWidget(C.copyable(C.wrapped(text, 'small', 'tertiary' if i >= quiet_from else 'secondary')))
            if i == 0 and section.shifts:
                lay.addWidget(self._shift_grid(section.shifts))
        w = QWidget()
        w.setLayout(lay)
        return w

    def _shift_grid(self, shifts) -> QWidget:
        """The input shifts as rows: name, bar in σ, the shift in % and in σ."""
        grid = QGridLayout()
        grid.setContentsMargins(QMargins())
        grid.setHorizontalSpacing(space(3))
        grid.setVerticalSpacing(0)
        for i, shift in enumerate(shifts):
            name = C.BreakingLabel(shift.name, 'body')
            name.setMinimumHeight(SIZE['control'])
            bar = C.ShiftBar(self.t, shift.z)
            bar.setToolTip(shift.tooltip)
            bar.setAccessibleName(f'Shift of {shift.name}: {shift.percent}, {shift.tooltip}')
            percent = C.copyable(C.label(shift.percent, 'number'))
            percent.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            sigma = '' if shift.z is None else f'{abs(shift.z):.1f}{THIN}σ'
            sig = C.copyable(C.label(sigma, 'small-number', 'tertiary'))
            sig.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            sig.setToolTip(shift.note or shift.tooltip)
            for col, widget in enumerate((name, bar, percent, sig)):
                grid.addWidget(widget, i, col)
        grid.setColumnStretch(0, 1)
        w = QWidget()
        w.setLayout(grid)
        return w


def _legend(plot: CF.ProfilePlot) -> list[tuple[str, str]]:
    """The legend of *plot*: the reported reading's chip carries the tint of the shaded interval behind it."""
    items = list(LEGEND if len(plot.curves) > 1 else LEGEND_ONE)
    if plot.band is not None:
        kind, text = items[0]
        items[0] = (f'{kind}+band', text)
    return items
