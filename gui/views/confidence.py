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
from PyQt6.QtCore import QMargins, QObject, QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QFontMetrics, QKeySequence, QPainter
from PyQt6.QtWidgets import QApplication, QFrame, QGridLayout, QLayout, QScrollArea, QSizePolicy, QWidget

from gui import confidence as CF
from gui import results as R
from gui.design import components as C
from gui.design.appearance import appearance, theme
from gui.design.plot_theme import apply_plot_theme, px
from gui.design.tokens import SIZE, Theme, font, space
from gui.plotting.export import export_widget
from gui.plotting.labels import THIN, fmt_param_plain
from gui.session_model import SessionModel

#: Width of the image a saved Ka confidence figure is drawn at, in logical px, and the
#: height of each profile plot and of the joint region in it.
EXPORT_WIDTH = 900
EXPORT_PLOT_HEIGHT = 420

#: Size of the best-fit diamond, and of the dots where the pointer meets a curve, in px.
DIAMOND = 14
POINTER_DOT = 9

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


def _tag(t: Theme, text: str, anchor, role: str = 'small-number', filled: bool = False) -> pg.TextItem:
    """An in-plot label in ``text-secondary``; *filled* backs it with the plot surface, for marks running up to it."""
    item = pg.TextItem(text, color=t.q('text-secondary'), anchor=anchor, fill=t.q('bg-surface') if filled else None)
    item.setFont(font(role))
    item.setZValue(5)
    return item


class ProfileFigure(QWidget):
    """One binding constant's profile plot over the strip of the Ka each reading accepts.

    The plot reads each curve's scaled drop against one cut-off line at 1; the strip shares
    its log-Ka axis. With *interactive* the pointer draws a hairline with its Ka at the top
    and the readout card reads every curve there; elsewhere the card reads the reported
    estimate.
    """

    def __init__(self, t: Theme, plot: CF.ProfilePlot, interactive: bool = True):
        super().__init__()
        self.t, self.plot = t, plot
        self.main = pg.PlotWidget()
        self.main.setFrameShape(QFrame.Shape.NoFrame)
        pi = apply_plot_theme(self.main, t, '', CF.Y_TITLE, list(CF.Y_TICKS))
        pi.getAxis('left').setWidth(SIZE['axis-left'])
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
        self.main.setMinimumHeight(SIZE['plot-min'] - self.strip.height())

        self.card = C.ReadoutCard(t, self.main)
        self.tag = C.ValueTag(t, self.main)
        self.tag.hide()
        self.hair = pg.InfiniteLine(angle=90, pen=_dotted(t, 'text-tertiary'), movable=False)
        self.hair.setZValue(4.5)
        self.hair.hide()
        pi.addItem(self.hair, ignoreBounds=True)
        self.dots = [
            pg.ScatterPlotItem(
                size=POINTER_DOT, brush=pg.mkBrush(t.q(c.color)), pen=pg.mkPen(t['bg-surface'], width=px(2))
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
        self.setMinimumHeight(SIZE['plot-min'])
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
        label = _tag(t, plot.cut_label, anchor=(1, 1.05))
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
                    size=DIAMOND,
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
        opens further left until it clears it.
        """
        t, plot = self.t, self.plot
        pw = pg.PlotWidget()
        pw.setFrameShape(QFrame.Shape.NoFrame)
        pi = apply_plot_theme(pw, t, plot.x_title, '', [])
        left = pi.getAxis('left')
        left.setTicks([[]])
        left.showLabel(False)
        left.setPen(pg.mkPen(None))
        left.setWidth(SIZE['axis-left'])
        pi.getAxis('bottom').setTicks([plot.ticks])
        pi.setXLink(self.main.getPlotItem())
        lanes = list(reversed(plot.curves))
        pi.setYRange(-0.75, len(lanes) - 0.25, padding=0)
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
            name = _tag(t, curve.label, anchor=(0, 0.5), role='small', filled=True)
            pi.addItem(name, ignoreBounds=True)
            first = math.log10(curve.stretches[0][0]) if curve.stretches else plot.x_range[1]
            placed.append((y, name, track, first))

        def clear_names():
            (x0, x1), width = vb.viewRange()[0], vb.width()
            if width <= 0:
                return
            dx = (x1 - x0) / width
            for y, name, track, first in placed:
                name.setPos(x0 + space(1) * dx, y)
                end = x0 + (space(1) + name.boundingRect().width() + space(2)) * dx
                if end > first > x0:
                    vb.setXRange(x0 - 1.1 * (end - first), x1, padding=0)
                    return  # the range change runs this again
                track.setData([end, x1], [y, y])

        vb.sigResized.connect(clear_names)
        vb.sigXRangeChanged.connect(clear_names)
        clear_names()
        pw.setFixedHeight(SIZE['axis-bottom'] + len(lanes) * SIZE['control'])
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
        self.card.adjustSize()
        self.card.move(rect.right() - self.card.width() - space(3), rect.top() + space(3))
        self.card.raise_()
        if self.tag.isVisible():
            top = self.main.mapFromScene(vb.mapViewToScene(QPointF(self.pointer_x, CF.Y_RANGE[1])))
            self.tag.move(round(top.x() - self.tag.width() / 2), rect.top())
            self.tag.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place()

    def sizeHint(self) -> QSize:
        # Its least height: the canvas lays out its height for its width from preferred heights,
        # and the plot takes whatever height the canvas has left over.
        return QSize(super().sizeHint().width(), self.minimumHeight())


class RegionFigure(QWidget):
    """The joint region of two binding constants: the accepted pairs, the best fit and each constant's own interval."""

    def __init__(self, t: Theme, region: CF.Region):
        super().__init__()
        self.t, self.region = t, region
        self.main = pg.PlotWidget()
        self.main.setFrameShape(QFrame.Shape.NoFrame)
        pi = apply_plot_theme(self.main, t, region.x_title, region.y_title, [v for v, _ in region.y_ticks])
        pi.getAxis('left').setTicks([region.y_ticks])
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
            size=DIAMOND,
            brush=pg.mkBrush(t.q('text-secondary')),
            pen=pg.mkPen(t['bg-surface'], width=px(2)),
        )
        self.best.setZValue(4)
        pi.addItem(self.best)
        pi.setRange(xRange=(x_lo, x_hi), yRange=(y_lo, y_hi), padding=0.02)
        pi.getViewBox().setMouseEnabled(x=False, y=False)
        self.setLayout(C.vbox(self.main, spacing=0))
        self.setMinimumHeight(SIZE['plot-min'])
        self.setAccessibleName('Joint region of the two binding constants')

    def sizeHint(self) -> QSize:
        return QSize(super().sizeHint().width(), self.minimumHeight())


class _Figure(QWidget):
    """A saved Ka confidence figure: its plots on a white surface, in the light theme (DESIGN.md §7)."""

    def __init__(self, t: Theme):
        super().__init__()
        self.t = t
        self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), self.t.q('bg-surface'))
        p.end()


class ConfidenceView(QObject):
    """The canvas and side panel of Ka confidence over *model*; *parent* is the session.

    :attr:`shifts_requested` asks for *Notes* with the input shifts in view (the conflict
    callout's action), :attr:`save_requested` for the plot image, :attr:`guide_requested`
    for the plot guide at Ka confidence; the session answers each.
    """

    shifts_requested = pyqtSignal()
    save_requested = pyqtSignal()
    guide_requested = pyqtSignal()

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
        self.guide_link.clicked.connect(self.guide_requested)
        model.results_changed.connect(lambda _scope: self.refresh())
        model.profile_changed.connect(self.refresh)
        model.data_changed.connect(self.refresh)
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
        lay = C.vbox(self.empty, self.header_host, self.callout_host, self.message, spacing=0, margins=(6, 5, 6, 4))
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

    def show_shifts(self, area: QScrollArea) -> None:
        """Open the section of the input shifts and scroll *area*, the side panel's, to it."""
        section = self.sections.get('conflict')
        if section is not None:
            section.header.set_open(True)
            area.ensureWidgetVisible(section, 0, 0)

    def has_plot(self) -> bool:
        """Whether a profile plot is on the canvas, which the image export saves."""
        return bool(self.figures)

    def export_figure(self) -> QWidget:
        """The figure :meth:`export_image` saves, laid out and shown off screen; the caller closes it.

        Drawn again in the light theme on white, on the same scaled-drop axis, each plot
        under its title and legend and its readings in one line, set apart from the plot
        above it; the readout card is left out, a saved figure having no pointer.
        """
        fit = self._fit()
        profile = self.model.profile
        light = Theme(dark=False)
        figure = _Figure(light)
        lay = C.vbox(spacing=0, margins=(6, 5, 6, 5))
        plots = [CF.profile_plot(fit, p) for p in profile.profiles.values()]
        headers = {h.key: h for h in CF.headers(fit)}

        def gap() -> None:
            if lay.count():
                lay.addSpacing(space(7))

        for plot in [p for p in plots if p is not None]:
            line = '; '.join(
                f'{r.label}: {" ".join(x for x in (r.qualifier.lower(), r.value, r.unit) if x)}, {r.level} {r.interval}'
                for r in headers[plot.key].readings
            )
            gap()
            lay.addLayout(
                C.hbox(_PaintedText(light, plot.name, 'body-strong'), None, C.LegendRow(light, _legend(plot)))
            )
            lay.addWidget(_PaintedText(light, line, 'small'))
            lay.addSpacing(space(2))
            fig = ProfileFigure(light, plot, interactive=False)
            fig.setFixedHeight(EXPORT_PLOT_HEIGHT)
            lay.addWidget(fig)
        region = CF.joint_region(fit, profile)
        if region is not None:
            title = 'Joint region' + (f' · {region.description}' if region.description else '')
            gap()
            lay.addWidget(_PaintedText(light, title, 'body-strong'))
            lay.addSpacing(space(2))
            reg = RegionFigure(light, region)
            reg.setFixedHeight(EXPORT_PLOT_HEIGHT)
            lay.addWidget(reg)
        figure.setLayout(lay)
        figure.setFixedWidth(EXPORT_WIDTH)
        figure.adjustSize()
        figure.show()
        QApplication.processEvents()
        return figure

    def export_image(self, path: str) -> None:
        """Save the profile plots — and the joint region of two binding constants — to *path* (PNG)."""
        figure = self.export_figure()
        try:
            export_widget(figure, path, width_px=2 * EXPORT_WIDTH)
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

    def refresh(self) -> None:
        model = self.model
        fit, note = model.fit_view()
        shown = fit if note is None else None
        has_ka = shown is not None and bool(CF.headers(shown))
        ours = shown is not None and model.profiled_fit is shown
        profile = model.profile if ours else None
        pending = ours and model.profile_running()
        shortcut = QKeySequence(R.RUN_FIT_KEY).toString(QKeySequence.SequenceFormat.NativeText)
        if fit is None:
            self.empty.setText(R.empty_sentence(model.measurement_set is not None, shortcut))
        elif shown is not None and not has_ka:
            self.empty.setText(CF.NO_KA)
        self.empty.setVisible(fit is None or (shown is not None and not has_ka))
        self._refresh_headers(shown if has_ka else None, drawn=profile is not None)
        self._refresh_callouts(
            CF.callouts(
                shown if has_ka or note else None,
                note,
                pending=pending,
                unchecked=has_ka and model.measurement_set is None,
                others_hidden=model.other_hidden_note() if has_ka else None,
            )
        )
        message = ''
        if has_ka and profile is None and not pending:
            error = model.profile_error if ours else None
            message = CF.failed_sentence(error) if error else CF.no_profile_sentence(model.measurement_set is not None)
        self.message.setText(message)
        self._refresh_plots(shown if has_ka else None, profile)
        if not self.figures:
            self.enlarged = False  # nothing left to enlarge, and no tool to put the readings back with
        self._refresh_side(shown, note, profile if has_ka else None, has_ka)
        self._show_parts()

    def _show_parts(self) -> None:
        self.header_host.setVisible(bool(self.header_box.count()) and not self.enlarged)
        self.callout_host.setVisible(bool(self.callouts) and not self.enlarged)
        self.message.setVisible(bool(self.message.text()))
        self.plots_host.setVisible(bool(self.figures))
        self.canvas_box.setStretch(self.canvas_box.count() - 1, 0 if self.figures else 1)

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
        role = 'metric' if reading.reported else 'title'
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
            if spec.action == CF.SHOW_SHIFTS:
                callout.action.clicked.connect(self.shifts_requested)
            self.callout_box.addWidget(callout)

    def _refresh_plots(self, fit, profile) -> None:
        _clear(self.plots_box)
        self.figures, self.region_figure, self.enlarge_tools = [], None, []
        if fit is None or profile is None:
            return
        plots = [CF.profile_plot(fit, p) for p in profile.profiles.values()]
        many = len(plots) > 1
        box = self.plots_box

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
            figure = ProfileFigure(self.t, plot)
            self.figures.append(figure)
            box.addLayout(self._plot_header(plot.name if many else 'Profile', _legend(plot)))
            box.addSpacing(space(2))
            box.addWidget(figure, 1)
        region = CF.joint_region(fit, profile)
        if region is not None:
            self.region_figure = RegionFigure(self.t, region)
            title = C.hbox(C.label('Joint region', 'body-strong'), 3, C.label(region.description, 'small', 'tertiary'))
            title.addStretch(1)
            gap()
            box.addLayout(title)
            box.addSpacing(space(2))
            box.addWidget(self.region_figure, 1)

    def _plot_header(self, title: str, legend: list[tuple[str, str]]):
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
        return C.hbox(C.label(title, 'body-strong'), None, C.LegendRow(self.t, legend), 5, enlarge, 1, save, spacing=0)

    # ------------------------------------------------------------------
    # Notes
    # ------------------------------------------------------------------

    def _refresh_side(self, fit, note: str | None, profile, has_ka: bool) -> None:
        _clear(self.notes_box)
        self.sections = {}
        self.no_fit.setVisible(fit is None or not has_ka)
        if note:
            self.no_fit.setText(f'The last fit is not shown. {note}')
        elif fit is None:
            self.no_fit.setText('No fit yet. Run a fit to see its notes here.')
        elif not has_ka:
            self.no_fit.setText(CF.NO_KA)
        if fit is None or not has_ka:
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


class _PaintedText(QWidget):
    """One line of text painted in a given theme, for a saved figure whatever the window's palette."""

    def __init__(self, t: Theme, text: str, role: str):
        super().__init__()
        self.t, self.text, self.role = t, text, role
        metrics = QFontMetrics(font(role))
        self.setFixedHeight(metrics.height() + space(2))
        self.setMinimumWidth(metrics.horizontalAdvance(text))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setFont(font(self.role))
        p.setPen(self.t.q('text-primary' if self.role == 'body-strong' else 'text-secondary'))
        p.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text)
        p.end()
