"""Main plot widget wrapping a PyQtGraph PlotWidget."""

from __future__ import annotations

from typing import Any

import numpy as np
import pyqtgraph as pg
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from gui.plotting.colors import (
    AVERAGE_LINE_COLOR,
    BACKGROUND_COLOR,
    DROPPED_REPLICA_COLOR,
    ERROR_BAR_COLOR,
    FIT_PALETTE,
    FOREGROUND_COLOR,
    REPLICA_PALETTE,
    rgba,
)
from gui.plotting.labels import _fmt_value, fmt_param, fmt_unit
from gui.plotting.plot_style import DEFAULT_STYLE, line_style_to_qt

_X_UNIT_SCALES: dict[str, float] = {"nM": 1e9, "µM": 1e6, "mM": 1e3, "M": 1.0}


def _to_superscript(n: int) -> str:
    """Convert an integer to a Unicode superscript string."""
    table = {
        '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
        '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
        '-': '⁻', '+': '⁺',
    }
    return ''.join(table.get(c, c) for c in str(n))


class ScientificAxisItem(pg.AxisItem):
    """AxisItem that formats tick labels in scientific notation.

    Values in the range [0.01, 10 000] are displayed as plain numbers.
    Values outside that range use Unicode superscript notation, e.g.
    ``10⁻⁶`` or ``2.5×10⁻⁷``.  SI prefix auto-scaling is disabled so
    that concentrations are shown in their native units.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.enableAutoSIPrefix(False)

    def tickStrings(self, values, scale, spacing):
        strings = []
        for v in values:
            v_scaled = v * scale
            if v_scaled == 0:
                strings.append('0')
            elif abs(v_scaled) >= 1e4 or (0 < abs(v_scaled) < 1e-2):
                exp = int(np.floor(np.log10(abs(v_scaled))))
                mantissa = v_scaled / 10 ** exp
                exp_str = _to_superscript(exp)
                if abs(mantissa - 1.0) < 1e-9:
                    strings.append(f'10{exp_str}')
                elif abs(mantissa + 1.0) < 1e-9:
                    strings.append(f'\u221210{exp_str}')
                else:
                    strings.append(f'{mantissa:.2g}\xd710{exp_str}')
            else:
                strings.append(f'{v_scaled:g}')
        return strings


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
        pg.setConfigOptions(antialias=True)

        axis_items = {
            'bottom': ScientificAxisItem(orientation='bottom'),
            'left': ScientificAxisItem(orientation='left'),
        }
        self._pg_widget = pg.PlotWidget(title=title, axisItems=axis_items)
        self._pg_widget.setLabel('bottom', x_label)
        self._pg_widget.setLabel('left', y_label)
        self._legend = self._pg_widget.addLegend(labelTextSize='10pt')

        # Style axes: bold pen + tick/label fonts from DEFAULT_STYLE
        _axes_style = DEFAULT_STYLE['axes']
        _tick_font = QFont()
        _tick_font.setPointSize(_axes_style['tick_font_size'])
        _label_font = QFont()
        _label_font.setPointSize(_axes_style['label_font_size'])
        _label_font.setBold(True)
        for axis_name in ('bottom', 'left'):
            ax = self._pg_widget.getAxis(axis_name)
            ax.setPen(pg.mkPen(color='k', width=1.5))
            ax.setTextPen(pg.mkPen('k'))
            ax.setStyle(tickLength=-8, tickFont=_tick_font)
            ax.label.setFont(_label_font)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._pg_widget)

        self._style: dict = DEFAULT_STYLE

        self._replica_items: list[pg.ScatterPlotItem] = []
        self._dropped_item: pg.ScatterPlotItem | None = None
        self._average_item: pg.PlotCurveItem | None = None
        self._error_bar_item: pg.ErrorBarItem | None = None
        self._error_cap_items: list[pg.PlotCurveItem] = []
        self._fit_items: list[pg.PlotCurveItem] = []
        self._annotation_item: pg.TextItem | None = None
        self._annotation_pos: pg.Point | None = None

        self._replica_ids: list[str] = []
        self._fit_labels: list[str] = []
        self._fit_results: list[Any] = []

        self._last_plot_data: dict[str, Any] = {}
        self._last_error_bar_data: tuple | None = None
        self._last_x_label_base: str | None = None
        self._last_y_label: str | None = None

    def update_plot(
        self,
        plot_data: dict[str, Any],
        *,
        x_label: str | None = None,
        y_label: str | None = None,
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

        style = self._style
        x_unit = style['axes'].get('x_unit', 'µM')
        x_scale = _X_UNIT_SCALES.get(x_unit, 1e6)

        if x_label is not None:
            self._last_x_label_base = x_label
        if y_label is not None:
            self._last_y_label = y_label
        if self._last_x_label_base is not None:
            self._pg_widget.setLabel('bottom', f'{self._last_x_label_base} [{x_unit}]')
        if self._last_y_label is not None:
            self._pg_widget.setLabel('left', self._last_y_label)

        x = np.asarray(plot_data.get('concentrations', [])) * x_scale

        # Active replicas — outlined markers for matplotlib-like look
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
                    pen=pg.mkPen(color=rgba(color, 220), width=0.8),
                    brush=pg.mkBrush(rgba(color, style['data_points']['alpha'])),
                    name=None,
                )
                self._pg_widget.addItem(item)
                self._replica_items.append(item)
                self._replica_ids.append(str(rid))

        # Dropped replicas
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

        # Average line + error bars — always create items when data permits so
        # that apply_style() can toggle visibility without requiring a full redraw.
        avg = plot_data.get('average')
        if avg is not None and len(active) > 0:
            avg_arr = np.asarray(avg)
            show_avg = style['visibility']['show_average']
            pen = pg.mkPen(
                color=AVERAGE_LINE_COLOR,
                width=style['average_line']['width'],
                style=line_style_to_qt(style['average_line']['style']),
            )
            self._average_item = pg.PlotCurveItem(x=x, y=avg_arr, pen=pen, name=None)
            self._average_item.setVisible(show_avg)
            self._pg_widget.addItem(self._average_item)

            if len(active) > 1:
                signals = np.stack([np.asarray(sig) for _, sig in active])
                std = signals.std(axis=0)
                eb_color = style['error_bars'].get('color', ERROR_BAR_COLOR)
                eb_width = style['error_bars'].get('width', 1)
                show_eb = style['visibility']['show_error_bars']
                self._error_bar_item = pg.ErrorBarItem(
                    x=x,
                    y=avg_arr,
                    height=2 * std,
                    pen=pg.mkPen(color=eb_color, width=eb_width),
                )
                self._pg_widget.addItem(self._error_bar_item)
                cap_size = style['error_bars'].get('cap_size', 5)
                if show_eb:
                    if cap_size > 0:
                        self._draw_error_caps(x, avg_arr, std, eb_color, eb_width, cap_size)
                else:
                    # Hide by setting empty data (ErrorBarItem doesn't support setVisible reliably)
                    self._error_bar_item.setData(
                        x=np.array([]), y=np.array([]), height=np.array([])
                    )
                self._last_error_bar_data = (x, avg_arr, std)

        # Fit curves
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
                    x=np.asarray(fit['x']) * x_scale,
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
        old_x_unit = self._style['axes'].get('x_unit', 'µM')
        new_x_unit = style['axes'].get('x_unit', 'µM')
        if old_x_unit != new_x_unit and self._last_plot_data:
            # x-unit change requires rescaling all data — do a full redraw
            fit_results_backup = list(self._fit_results)
            self._style = style
            self.update_plot(
                self._last_plot_data,
                x_label=self._last_x_label_base,
                y_label=self._last_y_label,
            )
            self._fit_results = fit_results_backup
            self._rebuild_annotation()
            return

        self._style = style

        dp = style['data_points']
        for i, item in enumerate(self._replica_items):
            color = REPLICA_PALETTE[i % len(REPLICA_PALETTE)]
            item.setSymbol(dp['symbol'])
            item.setSize(dp['size'])
            item.setPen(pg.mkPen(color=rgba(color, 220), width=0.8))
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
            self._average_item.setVisible(style['visibility']['show_average'])

        # Error bars: use setData with empty arrays to reliably hide/show
        if self._error_bar_item is not None:
            visible = style['visibility']['show_error_bars']
            eb_color = style['error_bars'].get('color', ERROR_BAR_COLOR)
            eb_width = style['error_bars'].get('width', 1)

            # Remove existing caps
            for cap in self._error_cap_items:
                self._pg_widget.removeItem(cap)
            self._error_cap_items.clear()

            if visible and self._last_error_bar_data is not None:
                x_eb, avg_eb, std_eb = self._last_error_bar_data
                self._error_bar_item.setData(
                    x=x_eb, y=avg_eb, height=2 * std_eb,
                    pen=pg.mkPen(color=eb_color, width=eb_width),
                )
                cap_size = style['error_bars'].get('cap_size', 5)
                if cap_size > 0:
                    self._draw_error_caps(x_eb, avg_eb, std_eb, eb_color, eb_width, cap_size)
            else:
                # Clear by setting empty data
                self._error_bar_item.setData(
                    x=np.array([]), y=np.array([]), height=np.array([])
                )

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

        self._legend.setLabelTextSize(f'{style["legend"]["font_size"]}pt')

        # Apply axis font sizes
        axes_style = style.get('axes', DEFAULT_STYLE['axes'])
        _tick_font = QFont()
        _tick_font.setPointSize(axes_style['tick_font_size'])
        _label_font = QFont()
        _label_font.setPointSize(axes_style['label_font_size'])
        _label_font.setBold(True)
        for axis_name in ('bottom', 'left'):
            ax = self._pg_widget.getAxis(axis_name)
            ax.setStyle(tickFont=_tick_font)
            ax.label.setFont(_label_font)

        self._rebuild_legend()
        self._rebuild_annotation()

    def set_axis_labels(self, x_label: str, y_label: str) -> None:
        """Update axis labels.

        Parameters
        ----------
        x_label : str
        y_label : str
        """
        self._last_x_label_base = x_label
        self._last_y_label = y_label
        x_unit = self._style['axes'].get('x_unit', 'µM')
        self._pg_widget.setLabel('bottom', f'{x_label} [{x_unit}]')
        self._pg_widget.setLabel('left', y_label)

    def set_fit_results(self, results: list[Any]) -> None:
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

    def export_image(self, path: str) -> None:
        """Export the current plot to a PNG or SVG file.

        Parameters
        ----------
        path : str
            Output file path.  Extension determines format:
            ``.png`` → rasterized PNG, ``.svg`` → vector SVG.

        Raises
        ------
        ValueError
            If the file extension is not ``.png`` or ``.svg``.
        """
        from pathlib import Path as _Path
        ext = _Path(path).suffix.lower()
        if ext == ".png":
            exporter = pg.exporters.ImageExporter(self._pg_widget.getPlotItem())
            exporter.export(path)
        elif ext == ".svg":
            exporter = pg.exporters.SVGExporter(self._pg_widget.getPlotItem())
            exporter.export(path)
        else:
            raise ValueError(f"Unsupported export format: '{ext}'. Use .png or .svg")

    def _draw_error_caps(
        self,
        x: np.ndarray,
        avg: np.ndarray,
        std: np.ndarray,
        color,
        width: int,
        cap_size: int,
    ) -> None:
        """Draw horizontal cap lines at ±1σ above/below error bars.

        Cap width is computed as a fraction of the x data span, so caps
        remain sensible regardless of when this is called relative to
        the view auto-range.  ``cap_size`` acts as a percentage-like scale
        (default 5 → ~2.5% of the x span per side).
        """
        if len(x) == 0:
            return
        x_min, x_max = float(x.min()), float(x.max())
        x_span = x_max - x_min if x_max != x_min else (abs(x_min) or 1.0)
        cap_half = x_span * cap_size / 200.0

        pen = pg.mkPen(color=color, width=width)
        for xi, yi, si in zip(x, avg, std):
            for sign in (+1, -1):
                cap_y = yi + sign * si
                cap_item = pg.PlotCurveItem(
                    x=[xi - cap_half, xi + cap_half],
                    y=[cap_y, cap_y],
                    pen=pen,
                )
                self._pg_widget.addItem(cap_item)
                self._error_cap_items.append(cap_item)

    def _rebuild_legend(self) -> None:
        """Rebuild legend entries from current style and stored item metadata.

        Legend entries are only added when the corresponding item is both
        configured to appear in the legend AND is currently visible.
        """
        leg = self._style['legend']
        vis = self._style['visibility']
        self._legend.clear()
        if leg['show_replicas'] and vis['show_data_points']:
            for item, rid in zip(self._replica_items, self._replica_ids):
                self._legend.addItem(item, rid)
        if leg['show_average'] and vis['show_average'] and self._average_item is not None:
            self._legend.addItem(self._average_item, 'average')
        if leg['show_fit'] and vis['show_fit']:
            for item, label in zip(self._fit_items, self._fit_labels):
                self._legend.addItem(item, label)

    def _clear_items(self) -> None:
        """Remove all data items and reset the legend."""
        all_items = [
            self._annotation_item,
            self._dropped_item,
            self._average_item,
            self._error_bar_item,
            *self._replica_items,
            *self._fit_items,
            *self._error_cap_items,
        ]
        for item in all_items:
            if item is not None:
                self._pg_widget.removeItem(item)

        self._replica_items = []
        self._dropped_item = None
        self._average_item = None
        self._error_bar_item = None
        self._error_cap_items = []
        self._fit_items = []
        self._annotation_item = None
        self._annotation_pos = None
        self._last_error_bar_data = None

        self._replica_ids = []
        self._fit_labels = []
        self._fit_results = []

        plot_item = self._pg_widget.getPlotItem()
        if plot_item.legend is not None:
            plot_item.legend.clear()

    def _rebuild_annotation(self) -> None:
        """Add or remove a draggable TextItem showing fit results."""
        if self._annotation_item is not None:
            self._annotation_pos = self._annotation_item.pos()
            self._pg_widget.removeItem(self._annotation_item)
            self._annotation_item = None

        if not self._style['annotations']['show_fit_results']:
            return
        if not self._fit_results:
            return

        font_pt = self._style['annotations']['font_size']
        lines: list[str] = []

        from core.assays.registry import ASSAY_REGISTRY, AssayType

        for idx, result in enumerate(self._fit_results):
            if len(self._fit_results) > 1:
                label = self._fit_labels[idx] if idx < len(self._fit_labels) else f'fit {idx}'
                lines.append(f'<b>{label}</b>')
            else:
                lines.append('<b>Fit Summary</b>')

            try:
                meta = ASSAY_REGISTRY[AssayType[result.assay_type]]
                units_dict = meta.units
            except KeyError:
                units_dict = {}

            for key, val in result.parameters.items():
                unc = result.uncertainties.get(key, float('nan'))
                unit = units_dict.get(key, '')
                unit_html = f' {fmt_unit(unit)}' if unit else ''
                lines.append(
                    f'{fmt_param(key)} = {_fmt_value(val)} &plusmn; {_fmt_value(unc)}{unit_html}'
                )

            lines.append(f'<b>R\u00b2:</b> {_fmt_value(result.r_squared, decimals=2)}')
            lines.append(f'<b>RMSE:</b> {_fmt_value(result.rmse, decimals=2)}')

            if idx < len(self._fit_results) - 1:
                lines.append('')

        body = '<br>'.join(lines)
        html = (
            f'<div style="font-size:{font_pt}pt; background-color:'
            f' rgba(255,255,255,200); padding:4px; border:1px solid #aaa;">'
            f'{body}</div>'
        )
        self._annotation_item = pg.TextItem(html=html, anchor=(0, 0))
        self._annotation_item.setFlag(self._annotation_item.GraphicsItemFlag.ItemIsMovable)
        self._pg_widget.addItem(self._annotation_item)
        if self._annotation_pos is not None:
            self._annotation_item.setPos(self._annotation_pos)
        else:
            vr = self._pg_widget.getViewBox().viewRect()
            self._annotation_item.setPos(vr.left(), vr.top() + vr.height())
