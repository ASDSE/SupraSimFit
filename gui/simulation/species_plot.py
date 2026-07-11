"""Live speciation plot for the simulation applet.

Shows the internal model species ([H], [D], [HD], [HG], …) as a function of the
titrant, one line per species, updating in real time alongside the signal plot.
A hover crosshair reads out every species' concentration at the nearest titration
point.

Kept deliberately separate from :class:`gui.plotting.plot_widget.PlotWidget` (which
is signal-specific: replicas, error bars, fit annotations, an ``au`` y-axis).  This
widget reuses the shared pieces — :class:`ScientificAxisItem`, the replica colour
palette, and Pint for the M→display scaling — so it stays visually consistent
without inheriting the fitting machinery.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from core.units import Q_
from gui.plotting.colors import REPLICA_PALETTE
from gui.plotting.labels import fmt_species
from gui.plotting.plot_widget import ScientificAxisItem

# Species are Molar internally; shown in the same concentration unit as the signal
# plot's x-axis (passed to update_species) so the two linked plots stay aligned even
# if that unit changes.  µM is the sensible default for these assays.
_DEFAULT_UNIT = 'µM'

# --- Legend appearance — tweak these to taste ---
_LEGEND_FONT_SIZE = '8pt'  # label text size; smaller = more compact
_LEGEND_VER_SPACING = -4  # vertical gap between rows (px); more negative = tighter
_LEGEND_HOR_SPACING = 6  # gap between a line's colour swatch and its label (px)
_LEGEND_BRACKETS = False  # True → show [H], [HD]; False → show H, HD


def _m_to(unit: str) -> float:
    """Pint-derived M→display multiplier for a concentration unit (single source of truth)."""
    return float(Q_(1, 'M').to(unit).magnitude)


class SpeciesPlotWidget(QWidget):
    """A live, hover-readable equilibrium-speciation plot."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._x: np.ndarray | None = None  # displayed titrant (in self._unit)
        self._x_name = 'Titrant'
        self._unit = _DEFAULT_UNIT
        self._series: dict[str, tuple[pg.PlotCurveItem, tuple[int, int, int]]] = {}
        self._species_disp: dict[str, np.ndarray] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._readout = QLabel(self._hint())
        self._readout.setTextFormat(Qt.TextFormat.RichText)
        self._readout.setWordWrap(True)
        layout.addWidget(self._readout)

        self._pg = pg.PlotWidget(
            axisItems={
                'left': ScientificAxisItem(orientation='left'),
                'bottom': ScientificAxisItem(orientation='bottom', use_exponent=False),
            }
        )
        self._pg.setBackground('w')
        self._item = self._pg.getPlotItem()
        self._item.showGrid(x=False, y=False)
        self._item.setLabel('left', f'Species [{self._unit}]', **{'font-size': '12pt', 'color': 'k'})
        self._legend = self._item.addLegend(
            labelTextSize=_LEGEND_FONT_SIZE,
            verSpacing=_LEGEND_VER_SPACING,
            horSpacing=_LEGEND_HOR_SPACING,
            offset=(-8, 8),
        )
        layout.addWidget(self._pg, 1)

        self._vline = pg.InfiniteLine(
            angle=90, movable=False, pen=pg.mkPen((120, 120, 120), width=1, style=Qt.PenStyle.DashLine)
        )
        self._vline.setVisible(False)
        self._item.addItem(self._vline, ignoreBounds=True)

        # rateLimit keeps the readout smooth without recomputing on every pixel.
        self._proxy = pg.SignalProxy(self._pg.scene().sigMouseMoved, rateLimit=60, slot=self._on_mouse_moved)

        self._set_x_label(self._x_name)

    # -- public API ----------------------------------------------------------

    def link_x(self, plot_item: pg.PlotItem) -> None:
        """Tie this plot's x-axis to another plot (the signal plot) so they pan/zoom together."""
        self._item.setXLink(plot_item)

    def update_species(
        self, concentrations_m: np.ndarray, species: dict[str, np.ndarray], x_name: str, unit: str = _DEFAULT_UNIT
    ) -> None:
        """Redraw one line per species (concentrations in M) versus the titrant, shown in *unit*."""
        self._clear()
        self._x_name = x_name
        self._unit = unit
        scale = _m_to(unit)
        self._x = np.asarray(concentrations_m, dtype=float) * scale
        for i, (key, arr) in enumerate(species.items()):
            color = REPLICA_PALETTE[i % len(REPLICA_PALETTE)]
            disp = np.asarray(arr, dtype=float) * scale
            self._species_disp[key] = disp
            curve = pg.PlotCurveItem(
                x=self._x,
                y=disp,
                pen=pg.mkPen(color=color, width=2),
                connect='finite',
                name=fmt_species(key, brackets=_LEGEND_BRACKETS),
            )
            self._item.addItem(curve)
            self._series[key] = (curve, color)
        self._item.setLabel('left', f'Species [{unit}]', **{'font-size': '12pt', 'color': 'k'})
        self._set_x_label(x_name)
        self._readout.setText(self._hint())

    def show_empty(self, message: str) -> None:
        """Clear the plot and show *message* (e.g. dye-alone has no speciation)."""
        self._clear()
        self._readout.setText(message)

    # -- internals -----------------------------------------------------------

    def _hint(self) -> str:
        return '<span style="color:gray">Hover the plot to read species concentrations.</span>'

    def _set_x_label(self, x_name: str) -> None:
        self._item.setLabel('bottom', f'{x_name} [{self._unit}]', **{'font-size': '12pt', 'color': 'k'})

    def _clear(self) -> None:
        for curve, _ in self._series.values():
            self._item.removeItem(curve)
        self._series.clear()
        self._species_disp.clear()
        self._legend.clear()
        self._x = None
        self._vline.setVisible(False)

    def _on_mouse_moved(self, evt) -> None:
        pos = evt[0]
        if self._x is None or self._x.size == 0 or not self._item.sceneBoundingRect().contains(pos):
            self._vline.setVisible(False)
            return
        x_view = self._item.vb.mapSceneToView(pos).x()
        idx = int(np.argmin(np.abs(self._x - x_view)))
        self._vline.setPos(self._x[idx])
        self._vline.setVisible(True)
        self._readout.setText(self._readout_html(idx))

    def _readout_html(self, idx: int) -> str:
        parts = [
            f'<b>{self._x_name}</b> = {_fmt(self._x[idx])} {self._unit}',
        ]
        for key, (_, color) in self._series.items():
            val = self._species_disp[key][idx]
            hexc = '#{:02x}{:02x}{:02x}'.format(*color)
            shown = '—' if not np.isfinite(val) else _fmt(val)
            parts.append(f'<span style="color:{hexc}">{fmt_species(key)} {shown}</span>')
        return '&nbsp;&nbsp;'.join(parts) + f' <span style="color:gray">({self._unit})</span>'


def _fmt(value: float) -> str:
    """Compact concentration readout: 3 significant figures, no exponent clutter."""
    return f'{value:.3g}'
