"""Main plot widget wrapping a PyQtGraph PlotWidget."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QPainter, QPicture
from PyQt6.QtWidgets import QVBoxLayout, QWidget
from pyqtgraph import functions as fn

from gui.plotting.colors import AVERAGE_LINE_COLOR, BACKGROUND_COLOR, DROPPED_REPLICA_COLOR, ERROR_BAR_COLOR, FIT_PALETTE, FOREGROUND_COLOR, REPLICA_PALETTE, rgba
from gui.plotting.labels import _fmt_value, fmt_param
from gui.plotting.plot_style import DEFAULT_STYLE, line_style_to_qt

# ---------------------------------------------------------------------------
# Dual-shade grid item
# ---------------------------------------------------------------------------


class DualGridItem(pg.GridItem):
    """Grid with separate pens for major and minor grid lines.

    The base ``pg.GridItem.generatePicture`` uses a single pen for all levels.
    This subclass assigns a darker grey to the coarsest (major) level and a
    lighter grey to finer (minor) levels, while preserving the auto-fading
    alpha that hides lines when they would be too dense.
    """

    def __init__(self):
        super().__init__(textPen=None)
        self._major_color = QColor(140, 140, 140)
        self._minor_color = QColor(210, 210, 210)
        # 2 levels: index 0 = major, index 1 = minor
        self.setTickSpacing(x=[None, None], y=[None, None])

    def update_grid_style(self, style: dict) -> None:
        """Apply grid section of the style dict."""
        g = style['grid']
        self._major_color.setAlpha(g['major_opacity'] if g['show_major'] else 0)
        self._minor_color.setAlpha(g['minor_opacity'] if g['show_minor'] else 0)
        self.picture = None
        self.update()

    def generatePicture(self):
        """Override to draw major and minor levels with different base colours.

        Adapted from ``pg.GridItem.generatePicture`` (pyqtgraph 0.14.0).
        The only change is per-level colour selection before the inner draw loop.
        """
        lvr = self.boundingRect()
        device_transform = self.deviceTransform_()
        if lvr.isNull() or device_transform is None:
            return

        self.picture = QPicture()
        p = QPainter()
        p.begin(self.picture)

        vr = self.getViewWidget().rect()
        dim = [vr.width(), vr.height()]
        ul = np.array([lvr.left(), lvr.top()])
        br = np.array([lvr.right(), lvr.bottom()])

        if ul[1] > br[1]:
            ul[1], br[1] = br[1], ul[1]

        lastd = [None, None]
        # Loop from finest (grid_depth-1) to coarsest (0)
        # i=0 → coarsest = MAJOR; i>0 → finer = MINOR
        for i in range(self.grid_depth - 1, -1, -1):
            is_major = i == 0
            base_color = QColor(self._major_color if is_major else self._minor_color)

            dist = br - ul
            nlTarget = 10.0**i
            d = 10.0 ** np.floor(np.log10(np.abs(dist / nlTarget)) + 0.5)

            for ax in range(0, 2):
                ts = self.opts['tickSpacing'][ax]
                try:
                    if ts[i] is not None:
                        d[ax] = ts[i]
                except IndexError:
                    pass
                lastd[ax] = d[ax]

            ul1 = np.floor(ul / d) * d
            br1 = np.ceil(br / d) * d
            dist = br1 - ul1
            nl = (dist / d) + 0.5

            for ax in range(0, 2):
                if i >= len(self.opts['tickSpacing'][ax]):
                    continue
                if lastd[ax] is not None and d[ax] < lastd[ax]:
                    continue

                ppl = dim[ax] / nl[ax]
                # Auto-fade: lines disappear when too dense (< 3 px apart)
                c = int(fn.clip_scalar(5 * (ppl - 3), 0, 50))

                color = QColor(base_color)
                # Blend auto-fade with the configured base alpha
                blended_alpha = int(color.alpha() * c / 50) if c > 0 else 0
                color.setAlpha(blended_alpha)

                pen = pg.mkPen(color)
                pen.setCosmetic(True)

                bx = (ax + 1) % 2
                for x in range(0, int(nl[ax])):
                    p1 = np.array([0.0, 0.0])
                    p2 = np.array([0.0, 0.0])
                    p1[ax] = ul1[ax] + x * d[ax]
                    p2[ax] = p1[ax]
                    p1[bx] = ul[bx]
                    p2[bx] = br[bx]
                    if p1[ax] < min(ul[ax], br[ax]) or p1[ax] > max(ul[ax], br[ax]):
                        continue
                    p.setPen(pen)
                    p.drawLine(QPointF(p1[0], p1[1]), QPointF(p2[0], p2[1]))

        p.end()


# ---------------------------------------------------------------------------
# Plot widget
# ---------------------------------------------------------------------------


class PlotWidget(QWidget):
    """Qt widget that renders ``prepare_plot_data()`` output via PyQtGraph.

    Parameters
    ----------
    x_label : str
        Initial x-axis label.
    y_label : str
        Initial y-axis label.
    title : str
        Plot title.
    parent : QWidget, optional
    """

    def __init__(
        self,
        x_label: str = '',
        y_label: str = '',
        title: str = '',
        parent=None,
    ):
        super().__init__(parent)
        pg.setConfigOption('background', BACKGROUND_COLOR)
        pg.setConfigOption('foreground', FOREGROUND_COLOR)

        self._pg_widget = pg.PlotWidget(title=title)
        self._pg_widget.setLabel('bottom', x_label)
        self._pg_widget.setLabel('left', y_label)
        self._legend = self._pg_widget.addLegend(labelTextSize='10pt')

        # Dual-shade grid
        self._grid = DualGridItem()
        self._pg_widget.getPlotItem().addItem(self._grid)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._pg_widget)

        self._style: dict = DEFAULT_STYLE

        # Item lists for in-place style mutation
        self._replica_items: List[pg.ScatterPlotItem] = []
        self._dropped_item: Optional[pg.ScatterPlotItem] = None
        self._average_item: Optional[pg.PlotCurveItem] = None
        self._error_bar_item: Optional[pg.ErrorBarItem] = None
        self._fit_items: List[pg.PlotCurveItem] = []
        self._annotation_item: Optional[pg.TextItem] = None

        # Metadata for legend rebuilding
        self._replica_ids: List[str] = []
        self._fit_labels: List[str] = []

        # FitResult objects stored for annotation display
        self._fit_results: List[Any] = []

        # Saved annotation position (data coords) — persists across style changes
        self._annotation_pos: Optional[QPointF] = None

        # Last plot data stored for annotation rebuilding
        self._last_plot_data: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_plot(
        self,
        plot_data: Dict[str, Any],
        *,
        x_label: Optional[str] = None,
        y_label: Optional[str] = None,
    ) -> None:
        """Clear and redraw from a ``prepare_plot_data()`` dict.

        Parameters
        ----------
        plot_data : dict
            As returned by ``core.data_processing.plotting.prepare_plot_data()``.
        x_label : str, optional
            Override x-axis label.
        y_label : str, optional
            Override y-axis label.
        """
        self._last_plot_data = plot_data
        self._clear_items()
        if x_label is not None:
            self._pg_widget.setLabel('bottom', x_label)
        if y_label is not None:
            self._pg_widget.setLabel('left', y_label)

        x = np.asarray(plot_data.get('concentrations', []))
        style = self._style
        leg = style['legend']

        # --- Active replicas ---
        active = plot_data.get('active_replicas', [])
        self._replica_ids = []
        if style['visibility']['show_data_points']:
            for i, (rid, sig) in enumerate(active):
                color = REPLICA_PALETTE[i % len(REPLICA_PALETTE)]
                item = pg.ScatterPlotItem(
                    x=x,
                    y=np.asarray(sig),
                    symbol=style['data_points']['symbol'],
                    size=style['data_points']['size'],
                    pen=pg.mkPen(None),
                    brush=pg.mkBrush(rgba(color, style['data_points']['alpha'])),
                    name=None,
                )
                self._pg_widget.addItem(item)
                self._replica_items.append(item)
                self._replica_ids.append(str(rid))

        # --- Dropped replicas ---
        dropped = plot_data.get('dropped_replicas', [])
        if dropped and style['visibility']['show_dropped']:
            all_x = np.concatenate([x] * len(dropped))
            all_y = np.concatenate([np.asarray(sig) for _, sig in dropped])
            self._dropped_item = pg.ScatterPlotItem(
                x=all_x,
                y=all_y,
                symbol=style['dropped_replicas']['symbol'],
                size=style['dropped_replicas']['size'],
                pen=pg.mkPen(None),
                brush=pg.mkBrush(rgba(DROPPED_REPLICA_COLOR, style['dropped_replicas']['alpha'])),
                name='dropped',
            )
            self._pg_widget.addItem(self._dropped_item)

        # --- Average line + error bars ---
        avg = plot_data.get('average')
        if avg is not None and len(active) > 0 and style['visibility']['show_average']:
            avg_arr = np.asarray(avg)
            pen = pg.mkPen(
                color=AVERAGE_LINE_COLOR,
                width=style['average_line']['width'],
                style=line_style_to_qt(style['average_line']['style']),
            )
            self._average_item = pg.PlotCurveItem(x=x, y=avg_arr, pen=pen, name=None)
            self._pg_widget.addItem(self._average_item)

            if len(active) > 1 and style['visibility']['show_error_bars']:
                signals = np.stack([np.asarray(sig) for _, sig in active])
                std = signals.std(axis=0)
                self._error_bar_item = pg.ErrorBarItem(
                    x=x,
                    y=avg_arr,
                    height=2 * std,
                    pen=pg.mkPen(
                        color=ERROR_BAR_COLOR,
                        width=style['error_bars']['width'],
                    ),
                )
                self._pg_widget.addItem(self._error_bar_item)

        # --- Fit curves ---
        fits = plot_data.get('fits', [])
        self._fit_labels = []
        if style['visibility']['show_fit']:
            for i, fit in enumerate(fits):
                color = FIT_PALETTE[i % len(FIT_PALETTE)]
                pen = pg.mkPen(
                    color=color,
                    width=style['fit_curves']['width'],
                    style=line_style_to_qt(style['fit_curves']['style']),
                )
                item = pg.PlotCurveItem(
                    x=np.asarray(fit['x']),
                    y=np.asarray(fit['y']),
                    pen=pen,
                    name=None,
                )
                self._pg_widget.addItem(item)
                self._fit_items.append(item)
                self._fit_labels.append(fit.get('label', f'fit {i}'))

        self._rebuild_legend()
        self._rebuild_annotation()

    def apply_style(self, style: dict) -> None:
        """Mutate existing plot items in-place with new style settings.

        Wired to ``PlotStyleWidget.style_changed``.

        Parameters
        ----------
        style : dict
            Full style dict as returned by ``PlotStyleWidget.current_style()``.
        """
        self._style = style

        dp = style['data_points']
        for i, item in enumerate(self._replica_items):
            color = REPLICA_PALETTE[i % len(REPLICA_PALETTE)]
            item.setSymbol(dp['symbol'])
            item.setSize(dp['size'])
            item.setBrush(pg.mkBrush(rgba(color, dp['alpha'])))
            item.setVisible(style['visibility']['show_data_points'])

        dr = style['dropped_replicas']
        if self._dropped_item is not None:
            self._dropped_item.setSymbol(dr['symbol'])
            self._dropped_item.setSize(dr['size'])
            self._dropped_item.setBrush(pg.mkBrush(rgba(DROPPED_REPLICA_COLOR, dr['alpha'])))
            self._dropped_item.setVisible(style['visibility']['show_dropped'])

        al = style['average_line']
        if self._average_item is not None:
            self._average_item.setPen(
                pg.mkPen(
                    color=AVERAGE_LINE_COLOR,
                    width=al['width'],
                    style=line_style_to_qt(al['style']),
                )
            )
            self._average_item.setVisible(al['visible'])

        if self._error_bar_item is not None:
            self._error_bar_item.setVisible(style['visibility']['show_error_bars'])

        fc = style['fit_curves']
        for i, item in enumerate(self._fit_items):
            color = FIT_PALETTE[i % len(FIT_PALETTE)]
            item.setPen(
                pg.mkPen(
                    color=color,
                    width=fc['width'],
                    style=line_style_to_qt(fc['style']),
                )
            )
            item.setVisible(style['visibility']['show_fit'])

        # Grid
        self._grid.update_grid_style(style)

        # Legend — font size then rebuild entries
        self._legend.setLabelTextSize(f'{style["legend"]["font_size"]}pt')
        self._rebuild_legend()

        # Annotation
        self._rebuild_annotation()

    def set_axis_labels(self, x_label: str, y_label: str) -> None:
        """Update axis labels.

        Parameters
        ----------
        x_label : str
        y_label : str
        """
        self._pg_widget.setLabel('bottom', x_label)
        self._pg_widget.setLabel('left', y_label)

    def set_fit_results(self, results: List[Any]) -> None:
        """Store FitResult objects used to populate the annotation.

        Call this after ``update_plot()`` whenever fit results are available.
        Pass an empty list to clear the annotation.

        Parameters
        ----------
        results : list[FitResult]
            One entry per fit curve shown in the plot.
        """
        self._fit_results = list(results)
        self._rebuild_annotation()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _rebuild_legend(self) -> None:
        """Rebuild legend entries from current style and stored item metadata."""
        leg = self._style['legend']
        self._legend.clear()
        if leg['show_replicas']:
            for item, rid in zip(self._replica_items, self._replica_ids):
                self._legend.addItem(item, rid)
        if leg['show_average'] and self._average_item is not None:
            self._legend.addItem(self._average_item, 'average')
        if leg['show_fit']:
            for item, label in zip(self._fit_items, self._fit_labels):
                self._legend.addItem(item, label)

    def _clear_items(self) -> None:
        """Remove all data items and rebuild the legend."""
        # Remove annotation first
        if self._annotation_item is not None:
            self._pg_widget.removeItem(self._annotation_item)
            self._annotation_item = None

        for item in self._replica_items:
            self._pg_widget.removeItem(item)
        if self._dropped_item is not None:
            self._pg_widget.removeItem(self._dropped_item)
        if self._average_item is not None:
            self._pg_widget.removeItem(self._average_item)
        if self._error_bar_item is not None:
            self._pg_widget.removeItem(self._error_bar_item)
        for item in self._fit_items:
            self._pg_widget.removeItem(item)

        self._replica_items = []
        self._dropped_item = None
        self._average_item = None
        self._error_bar_item = None
        self._fit_items = []

        self._replica_ids = []
        self._fit_labels = []
        self._fit_results = []
        self._annotation_pos = None

        # Rebuild legend to avoid ghost entries
        plot_item = self._pg_widget.getPlotItem()
        if plot_item.legend is not None:
            plot_item.legend.clear()

    def _rebuild_annotation(self) -> None:
        """Add or remove a draggable TextItem showing fit results.

        Saves and restores the annotation position across rebuilds so that
        a user-dragged annotation keeps its location when style changes.
        """
        if self._annotation_item is not None:
            self._annotation_pos = QPointF(self._annotation_item.pos())
            self._pg_widget.removeItem(self._annotation_item)
            self._annotation_item = None

        if not self._style['annotations']['show_fit_results']:
            return
        if not self._fit_results:
            return

        font_pt = self._style['annotations']['font_size']
        lines: List[str] = []

        for idx, result in enumerate(self._fit_results):
            if len(self._fit_results) > 1:
                label = self._fit_labels[idx] if idx < len(self._fit_labels) else f'fit {idx}'
                lines.append(f'<b>{label}</b>')
            else:
                lines.append('<b>Fit Results</b>')

            for key, val in result.parameters.items():
                unc = result.uncertainties.get(key, float('nan'))
                lines.append(f'{fmt_param(key)}: {_fmt_value(val)} &plusmn; {_fmt_value(unc)}')

            lines.append(f'R\u00b2: {result.r_squared:.4f}')
            lines.append(f'RMSE: {_fmt_value(result.rmse)}')
            lines.append(f'Fits: {result.n_passing}/{result.n_total}')

            if idx < len(self._fit_results) - 1:
                lines.append('')  # blank separator between multiple fits

        html = f'<div style="font-size:{font_pt}pt; background-color: rgba(255,255,255,200); padding:4px; border:1px solid #aaa;">' + '<br>'.join(lines) + '</div>'
        self._annotation_item = pg.TextItem(html=html, anchor=(0, 0))
        self._annotation_item.setFlag(self._annotation_item.GraphicsItemFlag.ItemIsMovable)
        self._pg_widget.addItem(self._annotation_item)

        if self._annotation_pos is not None:
            self._annotation_item.setPos(self._annotation_pos)
        else:
            vr = self._pg_widget.getViewBox().viewRect()
            self._annotation_item.setPos(vr.left(), vr.top() + vr.height())
