"""The titration plot: replicates against the titrant, with the mean ± SD and the fitted curves when given.

One plot draws the raw data in Measurements and the fit in Fit results. It is drawn
from the theme on screen and redrawn when the theme changes; a saved image is drawn
again in the light theme on white (DESIGN.md §7).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from html import escape

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import QApplication, QFrame, QWidget

from core.units import Q_
from gui.design import components as C
from gui.design.appearance import appearance, theme
from gui.design.plot_theme import apply_plot_theme, fit_line, px, replicate_alpha, scatter
from gui.design.tokens import TYPE, Theme, font, space
from gui.plotting.export import export_plot_item
from gui.plotting.labels import superscript

#: Size of a saved titration image, in logical px.
EXPORT_SIZE = (900, 600)

#: Width of the caps of the mean ± SD error bars, as a fraction of the x span drawn.
ERROR_CAP = 0.01


@dataclass
class TitrationData:
    """What the plot shows: concentrations (M), one signal row per replicate, which are used, and curves.

    A replicate not used is drawn as ×; *mean_sd* adds the mean ± SD of the used ones, and
    *replicates* ``False`` leaves every replicate's own points out. *curves* are drawn
    solid, *other_curves* — fits shown beside the reported one — dashed. *caption* is what
    a saved image states above the plot, one line each; the view on screen states it
    elsewhere.
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
    caption: list[str] = field(default_factory=list)


def wrap_caption(line: str, fm: QFontMetrics, width: int) -> list[str]:
    """*line* broken into lines no wider than *width* in *fm*: between its clauses (``; ``), and
    between the words of a clause too long for a line of its own."""
    pieces: list[tuple[str, str]] = []  # (what joins it to the text before, the text)
    for k, clause in enumerate(line.split('; ')):
        words = [clause] if fm.horizontalAdvance(clause) <= width else clause.split(' ')
        pieces += [('; ' if k and i == 0 else ' ', word) for i, word in enumerate(words)]
    lines: list[str] = []
    current = ''
    for joiner, text in pieces:
        if current and fm.horizontalAdvance(current + joiner + text) <= width:
            current += joiner + text
        else:
            if current:
                lines.append(current + joiner.rstrip())
            current = text
    return [*lines, current]


def power_of_ten(values: np.ndarray) -> int:
    """The power of ten an axis states its values in: that of the largest magnitude, 0 for none."""
    finite = np.abs(values[np.isfinite(values)])
    top = float(finite.max()) if finite.size else 0.0
    return math.floor(math.log10(top)) if top > 0 else 0


class TitrationPlot(QWidget):
    """The titration of :class:`TitrationData` in the display unit; empty until data are shown."""

    def __init__(self, t: Theme | None = None):
        super().__init__()
        self.t = t or theme()
        self.unit = 'µM'
        self.data: TitrationData | None = None
        self.pw: pg.PlotWidget | None = None
        self._items: list = []
        self.setLayout(C.vbox(spacing=0))
        if t is None:
            appearance().changed.connect(self._restyle)
        self._restyle()

    def _restyle(self) -> None:
        """Build the plot in the theme as it is now: axes and grid are styled once per theme."""
        if self.pw is not None:
            self.layout().removeWidget(self.pw)
            self.pw.deleteLater()
        self.pw = pg.PlotWidget()
        self.pw.setFrameShape(QFrame.Shape.NoFrame)
        pi = apply_plot_theme(self.pw, self.t, '', '')
        # A tick on an edge of the range, such as the 0 and 1 of the empty plot's 0–1, has its
        # label centred on that edge. Half a label of room above the axes and right of them
        # keeps such labels whole, and the x axis draws its end labels into that half label —
        # on the left into the y axis's room — where it would otherwise leave them out. The
        # widest a concentration tick reads is four characters (1000, 12.5); a wider one at
        # the right edge is left out, never cut.
        fm = QFontMetrics(font('small-number'))
        half_label = math.ceil(fm.horizontalAdvance('0000') / 2)
        left, _top, right, bottom = pi.layout.getContentsMargins()
        pi.layout.setContentsMargins(left, math.ceil(fm.height() / 2), max(right, half_label), bottom)
        pi.getAxis('bottom').setStyle(hideOverlappingLabels=half_label)
        self._items = []
        self.layout().addWidget(self.pw)
        self.redraw()

    def show_data(self, data: TitrationData | None, unit: str) -> None:
        """Show *data* with the concentrations in *unit*."""
        self.data, self.unit = data, unit
        self.redraw()

    def _add(self, item) -> None:
        self.pw.getPlotItem().addItem(item)
        self._items.append(item)

    def redraw(self) -> None:
        t, data = self.t, self.data
        pi = self.pw.getPlotItem()
        for item in self._items:
            pi.removeItem(item)
        self._items = []
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
        dark = t.dark
        for row, on in zip(data.signals, data.active, strict=True):
            if not data.replicates:
                break
            y = row * y_scale
            if on:
                self._add(scatter(t, x, y, 'replicate', replicate_alpha(t), 6))
            else:
                self._add(scatter(t, x, y, 'text-secondary' if dark else 'replicate-off', 0.8, 7, symbol='x'))
        used = data.signals[np.asarray(data.active, dtype=bool)] * y_scale
        if data.mean_sd and len(used):
            mean, sd = used.mean(axis=0), used.std(axis=0, ddof=1) if len(used) > 1 else np.zeros(len(x))
            pen = pg.mkPen(t['text-primary'], width=px(1))
            # Caps a hundredth of the x span wide, so they read the same at any range of the data.
            beam = ERROR_CAP * float(np.ptp(x)) if x.size else 0.0
            self._add(pg.ErrorBarItem(x=x, y=mean, height=2 * sd, beam=beam, pen=pen))
            self._add(scatter(t, x, mean, 'text-primary', 1.0, 6))
        for cx, cy in data.other_curves:
            self._add(fit_line(t, cx * scale, cy * y_scale, other=True))
        for cx, cy in data.curves:
            self._add(fit_line(t, cx * scale, cy * y_scale))

    def figure(self) -> TitrationPlot:
        """The plot as a saved image draws it, off screen: the light theme on white, at
        :data:`EXPORT_SIZE`, its caption above the axes in a row as tall as its lines.

        The caller closes it.
        """
        light = Theme(dark=False)
        copy = TitrationPlot(light)
        copy.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        copy.resize(*EXPORT_SIZE)
        copy.show_data(self.data, self.unit)
        if self.data is not None and self.data.caption:
            # Wrapped to the figure, so a long caption never widens the image past EXPORT_SIZE.
            fm, room = QFontMetrics(font('small')), EXPORT_SIZE[0] - 2 * space(8)  # the axes take the rest
            lines = [part for line in self.data.caption for part in wrap_caption(line, fm, room)]
            pi = copy.pw.getPlotItem()
            pi.setTitle(
                '<br>'.join(escape(line) for line in lines),
                color=light['text-secondary'],
                size=f'{TYPE["small"][0]}px',
                justify='left',
            )
            height = math.ceil(pi.titleLabel.item.boundingRect().height())
            pi.titleLabel.setMaximumHeight(height)
            pi.layout.setRowFixedHeight(0, height)
        copy.show()
        QApplication.processEvents()
        return copy

    def export_image(self, path: str) -> None:
        """Save the plot to *path* (PNG or SVG) as :meth:`figure` draws it."""
        copy = self.figure()
        try:
            export_plot_item(copy.pw.getPlotItem(), path)
        finally:
            copy.close()
            copy.deleteLater()
