"""The titration plot: replicates against the titrant, with the mean ± SD and the fitted curves when given.

One plot draws the raw data in Measurements and the fit in Fit results and Plot
appearance, with the session's :class:`~gui.plot_appearance.PlotAppearance`. It is drawn
from the theme on screen and redrawn when the theme changes. It zooms and pans, and
frames itself again on other data or another unit (:class:`~gui.design.components.PlotNavigation`,
whose *Reset view* tool its view puts in the plot header); a saved figure draws it
again in the light theme on white, with the same appearance, under the head the view
states beside it: title, description and legend, and the summary of a fit (DESIGN.md §7).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field, fields

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import QApplication, QFrame, QWidget

from core.units import Q_
from gui.design import components as C
from gui.design.appearance import appearance, theme
from gui.design.plot_theme import REPLICATE_ALPHA, apply_plot_theme, fit_line, px, scatter
from gui.design.tokens import SIZE, Theme, font
from gui.plot_appearance import BUILT_IN, PlotAppearance
from gui.plotting.export import export_stacked, figure_head
from gui.plotting.labels import superscript

#: Size of the plot of a saved titration figure, in logical px; its head sets the figure's height above it.
EXPORT_SIZE = (SIZE['export-width'], SIZE['export-titration'])

#: Width of the caps of the mean ± SD error bars, as a fraction of the x span drawn.
ERROR_CAP = 0.01


@dataclass(eq=False)
class TitrationData:
    """What the plot shows: concentrations (M), one signal row per replicate, which are used, and curves.

    *replicate_ids* name the rows, in the order the app names the replicates A, B, …
    (:func:`~core.pipeline.reporting.replica_order`); a row's place there picks its colour
    and mark (:meth:`~gui.plot_appearance.PlotAppearance.replicate_mark`), so a replicate
    keeps them in every view and when others are switched off. A replicate not used is
    drawn as × in its colour; *mean_sd* adds the mean ± SD of the used ones, and
    *replicates* ``False`` leaves every replicate's own points out. *curves* are drawn
    solid, *other_curves* — fits shown beside the reported one — dashed. Two are equal
    where every field holds the same values, a missing point (NaN) at the same place.
    """

    x_molar: np.ndarray
    signals: np.ndarray
    active: list[bool]
    x_name: str
    y_unit: str = 'a.u.'
    mean_sd: bool = False
    curves: list[tuple[np.ndarray, np.ndarray]] = field(default_factory=list)
    replicates: bool = True
    other_curves: list[tuple[np.ndarray, np.ndarray]] = field(default_factory=list)
    replicate_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.replicate_ids) != len(self.signals):
            raise ValueError(f'{len(self.signals)} signal rows are named by {len(self.replicate_ids)} replicate ids.')

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TitrationData):
            return NotImplemented
        return all(_equal(getattr(self, f.name), getattr(other, f.name)) for f in fields(self))


def _equal(a, b) -> bool:
    """Whether *a* and *b* hold the same values: arrays element by element, NaN equal to NaN; sequences item by item."""
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        return bool(np.array_equal(a, b, equal_nan=True))
    if isinstance(a, list | tuple) and isinstance(b, list | tuple):
        return len(a) == len(b) and all(map(_equal, a, b))
    return a == b


def legend_marks(legend: C.LegendRow, plot_appearance: PlotAppearance) -> None:
    """Draw the replicates and the fitted curve in *legend* as *plot_appearance* draws them in the plot."""
    look = plot_appearance
    legend.set_marks(look.replicate_mark, look.fit_px, look.fit_token)


def power_of_ten(values: np.ndarray) -> int:
    """The power of ten an axis states its values in: that of the largest magnitude, 0 for none."""
    finite = np.abs(values[np.isfinite(values)])
    top = float(finite.max()) if finite.size else 0.0
    return math.floor(math.log10(top)) if top > 0 else 0


class TitrationPlot(QWidget):
    """The titration of :class:`TitrationData` in the display unit, drawn with *plot_appearance*; empty until data are shown."""

    def __init__(self, t: Theme | None = None, plot_appearance: PlotAppearance = BUILT_IN):
        super().__init__()
        self.t = t or theme()
        self.plot_appearance = plot_appearance
        self.unit = 'µM'
        self.data: TitrationData | None = None
        self.pw: pg.PlotWidget | None = None
        self._items: list = []
        #: Each replicate's points (or its ×) as drawn, by replicate id.
        self.replicate_items: dict[str, pg.ScatterPlotItem] = {}
        self.navigation = C.PlotNavigation(self.t, 'Reset the view of the titration plot')
        self.setLayout(C.vbox(spacing=0))
        if t is None:
            appearance().changed.connect(self._restyle)
        self._restyle()

    def _restyle(self) -> None:
        """Build the plot in the theme as it is now: axes and grid are styled once per theme; the view stays where it was."""
        if self.pw is not None:
            self.layout().removeWidget(self.pw)
            self.pw.deleteLater()
        self.pw = pg.PlotWidget()
        self.pw.setFrameShape(QFrame.Shape.NoFrame)
        look = self.plot_appearance
        pi = apply_plot_theme(self.pw, self.t, '', '', tick_role=look.tick_role, title_role=look.title_role)
        # A tick on an edge of the range, such as the 0 and 1 of the empty plot's 0–1, has its
        # label centred on that edge. Half a label of room above the axes and right of them
        # keeps such labels whole, and the x axis draws its end labels into that half label —
        # on the left into the y axis's room — where it would otherwise leave them out. The
        # widest a concentration tick reads is four characters (1000, 12.5); a wider one at
        # the right edge is left out, never cut.
        fm = QFontMetrics(font(look.tick_role))
        half_label = math.ceil(fm.horizontalAdvance('0000') / 2)
        left, _top, right, bottom = pi.layout.getContentsMargins()
        pi.layout.setContentsMargins(left, math.ceil(fm.height() / 2), max(right, half_label), bottom)
        pi.getAxis('bottom').setStyle(hideOverlappingLabels=half_label)
        self._items = []
        self.layout().addWidget(self.pw)
        self.navigation.set_plots([(self.pw, None)])
        self.redraw()

    def set_plot_appearance(self, plot_appearance: PlotAppearance) -> None:
        """Draw the plot with *plot_appearance* from now on; another text size styles the axes afresh."""
        old, new = self.plot_appearance, plot_appearance
        self.plot_appearance = new
        if (old.tick_role, old.title_role) != (new.tick_role, new.title_role):
            self._restyle()
        else:
            self.redraw()

    def show_data(self, data: TitrationData | None, unit: str) -> None:
        """Show *data* with the concentrations in *unit*: other data or another unit put the plot back on
        auto-range, so they are in view; the same ones keep the view the user chose."""
        if (data, unit) != (self.data, self.unit):
            self.navigation.reset()
        self.data, self.unit = data, unit
        self.redraw()

    def _add(self, item) -> None:
        self.pw.getPlotItem().addItem(item)
        self._items.append(item)

    def redraw(self) -> None:
        t, data, look = self.t, self.data, self.plot_appearance
        pi = self.pw.getPlotItem()
        for item in self._items:
            pi.removeItem(item)
        self._items = []
        self.replicate_items = {}
        scale = Q_(1.0, 'M').to(self.unit).magnitude
        if data is None:
            pi.getAxis('bottom').setLabel(f'Concentration ({self.unit})')
            pi.getAxis('left').setLabel('Signal (a.u.)')
            return
        curves = [*data.curves, *data.other_curves]
        e = power_of_ten(np.concatenate([data.signals.ravel(), *(cy for _cx, cy in curves)]))
        y_scale = 10.0**-e
        pi.getAxis('left').setLabel(f'Signal ({"" if e == 0 else f"10{superscript(e)} "}{data.y_unit})')
        pi.getAxis('bottom').setLabel(f'{data.x_name} ({self.unit})')
        x = data.x_molar * scale
        rows = zip(data.replicate_ids, data.signals, data.active, strict=True) if data.replicates else ()
        for index, (rid, row, on) in enumerate(rows):
            colour, symbol = look.replicate_mark(index)
            size = look.replicate_px if on else look.cross_px
            item = scatter(t, x, row * y_scale, colour, REPLICATE_ALPHA, size, symbol if on else 'x')
            self.replicate_items[rid] = item
            self._add(item)
        used = data.signals[np.asarray(data.active, dtype=bool)] * y_scale
        if data.mean_sd and len(used):
            mean, sd = used.mean(axis=0), used.std(axis=0, ddof=1) if len(used) > 1 else np.zeros(len(x))
            pen = pg.mkPen(t['text-primary'], width=px(look.error_bar_px))
            # Caps a hundredth of the x span wide, so they read the same at any range of the data.
            beam = ERROR_CAP * float(np.ptp(x)) if x.size else 0.0
            self._add(pg.ErrorBarItem(x=x, y=mean, height=2 * sd, beam=beam, pen=pen))
            self._add(scatter(t, x, mean, 'text-primary', 1.0, look.mean_px))
        for cx, cy in data.other_curves:
            self._add(fit_line(t, cx * scale, cy * y_scale, other=True))
        for cx, cy in data.curves:
            self._add(fit_line(t, cx * scale, cy * y_scale, width=look.fit_px, color=look.fit_token))

    def figure(self) -> TitrationPlot:
        """The plot as a saved figure draws it, off screen: the light theme on white with the
        plot's appearance, at :data:`EXPORT_SIZE`.

        The caller closes it.
        """
        copy = TitrationPlot(Theme(dark=False), self.plot_appearance)
        copy.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        copy.resize(*EXPORT_SIZE)
        copy.show_data(self.data, self.unit)
        copy.show()
        QApplication.processEvents()
        return copy

    def export_image(self, path: str, legend: list[tuple], description: str = '', summary: Sequence[str] = ()) -> None:
        """Save the plot to *path* (PNG or SVG) as one figure: the head the view states beside it above :meth:`figure`.

        The head is the title *Titration* with the view's *description* and its *legend* — drawn with
        the plot's appearance — then the lines of *summary*, a fit's numbers where the view draws one.
        """
        light = Theme(dark=False)
        key = C.LegendRow(light, legend, removable=False)
        legend_marks(key, self.plot_appearance)
        head = figure_head(light, 'Titration', description, key, EXPORT_SIZE[0], summary)
        head.show()
        copy = self.figure()
        try:
            export_stacked([head, copy.pw.getPlotItem()], path, width_px=2 * EXPORT_SIZE[0])
        finally:
            for w in (head, copy):
                w.close()
                w.deleteLater()
