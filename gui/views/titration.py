"""The titration plot: replicates against the titrant, with the mean ± SD and the fitted curves when given.

One plot draws the raw data in Measurements and the fit in Fit results. It is drawn
from the theme on screen and redrawn when the theme changes; a saved image is drawn
again in the light theme on white (DESIGN.md §7).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QFrame, QWidget

from core.units import Q_
from gui.design import components as C
from gui.design.appearance import appearance, theme
from gui.design.plot_theme import apply_plot_theme, fit_line, px, scatter
from gui.design.tokens import Theme
from gui.plotting.export import export_plot_item

_SUPERSCRIPT = str.maketrans('0123456789-', '⁰¹²³⁴⁵⁶⁷⁸⁹⁻')

#: Size of a saved titration image, in logical px.
EXPORT_SIZE = (900, 600)


@dataclass
class TitrationData:
    """What the plot shows: concentrations (M), one signal row per replicate, which are used, and curves."""

    x_molar: np.ndarray
    signals: np.ndarray
    active: list[bool]
    x_name: str
    y_unit: str = 'a.u.'
    mean_sd: bool = False
    curves: list[tuple[np.ndarray, np.ndarray]] = field(default_factory=list)


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
        apply_plot_theme(self.pw, self.t, '', '')
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
        e = power_of_ten(data.signals)
        y_scale = 10.0**-e
        pi.getAxis('left').setLabel(f'Signal ({"" if e == 0 else f"10{str(e).translate(_SUPERSCRIPT)} "}{data.y_unit})')
        pi.getAxis('bottom').setLabel(f'{data.x_name} ({self.unit})')
        x = data.x_molar * scale
        dark = t.dark
        for row, on in zip(data.signals, data.active, strict=True):
            y = row * y_scale
            if on:
                self._add(scatter(t, x, y, 'replicate', 0.8 if dark else 0.55, 6))
            else:
                self._add(scatter(t, x, y, 'text-secondary' if dark else 'replicate-off', 0.8, 7, symbol='x'))
        used = data.signals[np.asarray(data.active, dtype=bool)] * y_scale
        if data.mean_sd and len(used):
            mean, sd = used.mean(axis=0), used.std(axis=0, ddof=1) if len(used) > 1 else np.zeros(len(x))
            pen = pg.mkPen(t['text-primary'], width=px(1))
            self._add(pg.ErrorBarItem(x=x, y=mean, height=2 * sd, beam=0, pen=pen))
            self._add(scatter(t, x, mean, 'text-primary', 1.0, 6))
        for cx, cy in data.curves:
            self._add(fit_line(t, cx * scale, cy * y_scale))

    def export_image(self, path: str) -> None:
        """Save the plot to *path* (PNG or SVG) in the light theme on white."""
        copy = TitrationPlot(Theme(dark=False))
        copy.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        copy.resize(*EXPORT_SIZE)
        copy.show_data(self.data, self.unit)
        copy.show()
        QApplication.processEvents()
        try:
            export_plot_item(copy.pw.getPlotItem(), path)
        finally:
            copy.close()
            copy.deleteLater()
