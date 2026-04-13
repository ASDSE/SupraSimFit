"""Main plot widget wrapping a PyQtGraph PlotWidget."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from core.units import Q_, Quantity, ureg
from gui.plotting.colors import AVERAGE_LINE_COLOR, BACKGROUND_COLOR, DROPPED_REPLICA_COLOR, ERROR_BAR_COLOR, FIT_PALETTE, FOREGROUND_COLOR, PALETTES, REPLICA_PALETTE, rgba
from gui.plotting.labels import fmt_param, fmt_unit_html
from gui.plotting.plot_style import DEFAULT_STYLE, line_style_to_qt
from gui.widgets.replica_panel import _display_label

_X_UNIT_SCALES: dict[str, float] = {label: float(Q_(1, label).to('M').magnitude) for label in ('nM', 'µM', 'mM', 'M')}
# Invert: we need M→display, i.e. multiply M value to get display value
_X_UNIT_SCALES = {k: 1.0 / v for k, v in _X_UNIT_SCALES.items()}

_SUPERSCRIPT_DIGITS = str.maketrans('0123456789-', '⁰¹²³⁴⁵⁶⁷⁸⁹⁻')


def _format_exponent_unicode(exp: int) -> str:
    """Convert an integer exponent to Unicode superscript, e.g. 5 → '⁵', -3 → '⁻³'."""
    return str(exp).translate(_SUPERSCRIPT_DIGITS)


class _ErrorBarSample(pg.ItemSample):
    """Legend sample that renders an error-bar glyph instead of a line.

    pyqtgraph's default :class:`ItemSample` only knows how to paint
    curves, scatter markers, and bar graphs. Passing a plain
    ``PlotCurveItem`` for the error-bar legend entry therefore draws a
    plain horizontal line, which is visually indistinguishable from the
    mean line. Subclassing and overriding ``paint`` lets us draw a
    ``┬ ┴`` glyph (vertical stem with two caps) that matches the on-plot
    error bars.
    """

    _WIDTH = 20
    _HEIGHT = 20

    def paint(self, p, *args):  # type: ignore[override]
        pen = self.item.opts.get('pen') if hasattr(self.item, 'opts') else None
        if pen is None:
            return
        p.setPen(pen)
        # Vertical stem
        p.drawLine(QPointF(10.0, 3.0), QPointF(10.0, 17.0))
        # Top cap
        p.drawLine(QPointF(5.0, 3.0), QPointF(15.0, 3.0))
        # Bottom cap
        p.drawLine(QPointF(5.0, 17.0), QPointF(15.0, 17.0))

    def boundingRect(self):  # type: ignore[override]
        return QRectF(0.0, 0.0, float(self._WIDTH), float(self._HEIGHT))


class ScientificAxisItem(pg.AxisItem):
    """AxisItem that formats tick labels with a shared exponent.

    When all tick values share a common order of magnitude (outside the
    [0.01, 10 000] range), the exponent is factored out and stored in
    :attr:`exponent`.  Tick labels then show plain mantissa values (e.g.
    "2", "4", "6") and the caller appends "×10ⁿ" once to the axis label.

    Values in [0.01, 10 000] are displayed as plain numbers with no
    exponent factored out.  SI prefix auto-scaling is disabled.

    Parameters
    ----------
    use_exponent : bool
        If ``False``, tick labels are always plain ``:g``-formatted values
        and no exponent is factored out.  Useful for axes where the caller
        already handles unit scaling (e.g. concentration with a user-selected
        unit).
    """

    def __init__(self, *args, use_exponent: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.enableAutoSIPrefix(False)
        self.exponent: int | None = None
        self._use_exponent = use_exponent
        self.on_exponent_changed: Callable[[int | None], None] | None = None

    def _set_exponent(self, exp: int | None) -> None:
        """Update exponent, firing callback only on change.

        The callback guard (``exp != self.exponent``) prevents infinite
        recursion: ``setLabel`` → ``update()`` → ``tickStrings`` →
        same exponent → no callback.
        """
        if exp != self.exponent:
            self.exponent = exp
            if self.on_exponent_changed is not None:
                self.on_exponent_changed(exp)

    def tickStrings(self, values, scale, spacing):
        if not values:
            self._set_exponent(None)
            return []

        if not self._use_exponent:
            self._set_exponent(None)
            return [f'{v * scale:g}' for v in values]

        # Compute common exponent from the maximum absolute value
        abs_vals = [abs(v * scale) for v in values if v * scale != 0]
        if not abs_vals:
            self._set_exponent(None)
            return ['0'] * len(values)

        max_abs = max(abs_vals)

        # Only factor out exponent for values outside the "plain" range
        if 1e-2 <= max_abs <= 1e4:
            self._set_exponent(None)
            return [f'{v * scale:g}' for v in values]

        exp = int(np.floor(np.log10(max_abs)))
        self._set_exponent(exp)
        divisor = 10**exp

        strings = []
        for v in values:
            v_scaled = v * scale
            if v_scaled == 0:
                strings.append('0')
            else:
                mantissa = v_scaled / divisor
                strings.append(f'{mantissa:g}')
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

        # Wire exponent callbacks so axis labels update reactively after paint
        left_ax: ScientificAxisItem = self._pg_widget.getAxis('left')
        left_ax.on_exponent_changed = self._on_y_exponent_changed
        bottom_ax: ScientificAxisItem = self._pg_widget.getAxis('bottom')
        bottom_ax.on_exponent_changed = self._on_x_exponent_changed

        self._style: dict = DEFAULT_STYLE

        self._replica_items: list[pg.ScatterPlotItem] = []
        self._dropped_item: pg.ScatterPlotItem | None = None
        self._dropped_items: list[pg.ScatterPlotItem] = []
        self._average_item: pg.PlotCurveItem | None = None
        self._error_bar_item: pg.ErrorBarItem | None = None
        self._error_cap_items: list[pg.PlotCurveItem] = []
        self._fit_items: list[pg.PlotCurveItem] = []
        self._annotation_item: pg.TextItem | None = None
        self._annotation_pos: pg.Point | None = None
        self._legend_corner: str | None = None

        self._replica_ids: list[str] = []
        self._all_replica_ids: tuple[str, ...] = ()
        self._dropped_replica_ids: list[str] = []
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
        preserve_positions: bool = False,
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
        preserve_positions : bool
            If False (the default), reset the remembered legend corner
            and annotation position so overlays are re-placed on the
            uncovered quadrant of the new data. Set to True when the
            caller is redrawing the *same* data (e.g. an x-axis unit
            rescale) and wants user-dragged positions to survive.
        """
        self._last_plot_data = plot_data
        if not preserve_positions:
            self._legend_corner = None
            self._annotation_pos = None
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

        # Resolve the active palette
        palette_name = style['data_points'].get('palette', 'Default (Tab10)')
        palette = PALETTES.get(palette_name, REPLICA_PALETTE)

        # Store full replica id list for correct legend labels
        self._all_replica_ids = tuple(plot_data.get('all_replica_ids', ()))

        # Active replicas — outlined markers for matplotlib-like look
        active = plot_data.get('active_replicas', [])
        self._replica_ids = []
        if style['visibility']['show_data_points']:
            for i, (rid, sig) in enumerate(active):
                color = palette[i % len(palette)]
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

        # Dropped replicas — individual items so each gets its own legend entry
        dropped = plot_data.get('dropped_replicas', [])
        self._dropped_replica_ids = []
        if dropped and style['visibility']['show_dropped']:
            self._dropped_items = []
            for rid, sig in dropped:
                item = pg.ScatterPlotItem(
                    x=x,
                    y=np.asarray(sig),
                    symbol=style['dropped_replicas']['symbol'],
                    size=style['dropped_replicas']['size'],
                    pen=pg.mkPen(None),
                    brush=pg.mkBrush(rgba(DROPPED_REPLICA_COLOR, style['dropped_replicas']['alpha'])),
                    name=None,
                )
                self._pg_widget.addItem(item)
                self._dropped_items.append(item)
                self._dropped_replica_ids.append(str(rid))

        # Average line + error bars — always create items when data permits so
        # that apply_style() can toggle visibility without requiring a full redraw.
        avg = plot_data.get('average')
        if avg is not None and len(active) > 0:
            avg_arr = np.asarray(avg)
            show_avg = style['visibility']['show_average']
            avg_color = style['average_line'].get('color', AVERAGE_LINE_COLOR)
            pen = pg.mkPen(
                color=avg_color,
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
                    self._error_bar_item.setData(x=np.array([]), y=np.array([]), height=np.array([]))
                self._last_error_bar_data = (x, avg_arr, std)

        # Fit curves
        fits = plot_data.get('fits', [])
        self._fit_labels = []
        if style['visibility']['show_fit']:
            for i, fit in enumerate(fits):
                color = style['fit_curves'].get('color', FIT_PALETTE[i % len(FIT_PALETTE)])
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

        # Auto-range first so _find_least_occupied_corner sees the new
        # view rect; otherwise it'd pick the corner from the previous
        # data range and the legend could end up over the data points.
        self._pg_widget.getViewBox().autoRange()
        self._rebuild_legend()
        self._rebuild_annotation()
        self._update_axis_labels_with_exponents()

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
            # but keep legend/annotation exactly where the user left them.
            fit_results_backup = list(self._fit_results)
            self._style = style
            self.update_plot(
                self._last_plot_data,
                x_label=self._last_x_label_base,
                y_label=self._last_y_label,
                preserve_positions=True,
            )
            self._fit_results = fit_results_backup
            self._rebuild_annotation()
            return

        self._style = style

        # Resolve palette
        palette_name = style['data_points'].get('palette', 'Default (Tab10)')
        palette = PALETTES.get(palette_name, REPLICA_PALETTE)

        dp = style['data_points']
        for i, item in enumerate(self._replica_items):
            color = palette[i % len(palette)]
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
        for item in getattr(self, '_dropped_items', []):
            item.setSymbol(dr['symbol'])
            item.setSize(dr['size'])
            item.setBrush(pg.mkBrush(rgba(DROPPED_REPLICA_COLOR, dr['alpha'])))
            item.setVisible(style['visibility']['show_dropped'])

        al = style['average_line']
        if self._average_item is not None:
            avg_color = al.get('color', AVERAGE_LINE_COLOR)
            pen = pg.mkPen(
                color=avg_color,
                width=al['width'],
                style=line_style_to_qt(al['style']),
            )
            # Reset opts['pen'] directly before setPen: pyqtgraph short-circuits
            # ``setPen`` when the stored pen compares equal, which happens when a
            # QColor is mutated in-place by the ParameterTree color picker.
            self._average_item.opts['pen'] = None
            self._average_item.setPen(pen)
            self._average_item.update()
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
                    x=x_eb,
                    y=avg_eb,
                    height=2 * std_eb,
                    pen=pg.mkPen(color=eb_color, width=eb_width),
                )
                cap_size = style['error_bars'].get('cap_size', 5)
                if cap_size > 0:
                    self._draw_error_caps(x_eb, avg_eb, std_eb, eb_color, eb_width, cap_size)
            else:
                # Clear by setting empty data
                self._error_bar_item.setData(x=np.array([]), y=np.array([]), height=np.array([]))

        fc = style['fit_curves']
        for i, item in enumerate(self._fit_items):
            color = fc.get('color', FIT_PALETTE[i % len(FIT_PALETTE)])
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
        self._update_axis_labels_with_exponents()

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

        import pyqtgraph.exporters

        ext = _Path(path).suffix.lower()
        if ext == '.png':
            exporter = pg.exporters.ImageExporter(self._pg_widget.getPlotItem())
            exporter.export(path)
        elif ext == '.svg':
            exporter = pg.exporters.SVGExporter(self._pg_widget.getPlotItem())
            exporter.export(path)
        else:
            raise ValueError(f"Unsupported export format: '{ext}'. Use .png or .svg")

    def _set_axis_label(self, axis: str, base_label: str, exp: int | None) -> None:
        """Set an axis label, appending ×10ⁿ if *exp* is not None."""
        if exp is not None:
            exp_str = _format_exponent_unicode(exp)
            self._pg_widget.setLabel(axis, f'{base_label}  (×10{exp_str})')
        else:
            self._pg_widget.setLabel(axis, base_label)

    def _on_y_exponent_changed(self, exp: int | None) -> None:
        """Update y-axis label reactively when the exponent changes during paint."""
        self._set_axis_label('left', self._last_y_label or '', exp)

    def _on_x_exponent_changed(self, exp: int | None) -> None:
        """Update x-axis label reactively when the exponent changes during paint."""
        x_unit = self._style['axes'].get('x_unit', 'µM')
        self._set_axis_label('bottom', f'{self._last_x_label_base or ""} [{x_unit}]', exp)

    def _update_axis_labels_with_exponents(self) -> None:
        """Set axis labels with exponent suffix if known.

        Exponents may be stale on the first call (before the initial
        paint); the ``on_exponent_changed`` callbacks on each
        :class:`ScientificAxisItem` correct them reactively once
        ``tickStrings`` runs during paint.
        """
        self._on_y_exponent_changed(self._pg_widget.getAxis('left').exponent)
        self._on_x_exponent_changed(self._pg_widget.getAxis('bottom').exponent)

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
        The legend is placed in the least-occupied corner of the plot.
        """
        leg = self._style['legend']
        vis = self._style['visibility']
        self._legend.clear()
        entry_count = 0
        if leg['show_replicas'] and vis['show_data_points']:
            for item, rid in zip(self._replica_items, self._replica_ids):
                # Use original replica index from full id list for correct label
                if self._all_replica_ids and rid in self._all_replica_ids:
                    idx = self._all_replica_ids.index(rid)
                else:
                    idx = self._replica_ids.index(rid)
                self._legend.addItem(item, _display_label(idx))
                entry_count += 1
        if leg.get('show_dropped', True) and vis['show_dropped']:
            for item, rid in zip(getattr(self, '_dropped_items', []), self._dropped_replica_ids):
                if self._all_replica_ids and rid in self._all_replica_ids:
                    idx = self._all_replica_ids.index(rid)
                else:
                    idx = 0
                self._legend.addItem(item, f'{_display_label(idx)} (dropped)')
                entry_count += 1
        if leg['show_average'] and vis['show_average'] and self._average_item is not None:
            self._legend.addItem(self._average_item, 'Mean')
            entry_count += 1
        if leg.get('show_error_bars', True) and vis['show_error_bars'] and self._error_bar_item is not None:
            # Custom sample draws a ┬ ┴ glyph so the legend entry is
            # visually distinct from the average line.
            eb_color = self._style['error_bars'].get('color', ERROR_BAR_COLOR)
            eb_pen = pg.mkPen(color=eb_color, width=self._style['error_bars'].get('width', 1))
            eb_stub = pg.PlotCurveItem(pen=eb_pen)
            self._legend.addItem(_ErrorBarSample(eb_stub), 'Mean \u00b1 SD')
            entry_count += 1
        if leg['show_fit'] and vis['show_fit']:
            for item, label in zip(self._fit_items, self._fit_labels):
                self._legend.addItem(item, label)
                entry_count += 1

        # Background brush — applied on every rebuild so the colour
        # picker updates live. Falls back to the legacy inline default.
        bg = self._style['legend'].get('background_color', (255, 255, 255, 200))
        brush = pg.mkBrush(color=tuple(bg))
        if hasattr(self._legend, 'setBrush'):
            self._legend.setBrush(brush)
        else:
            self._legend.opts['brush'] = brush
            self._legend.update()

        # Position legend once per data load. On later rebuilds (style
        # changes, x-unit rescales, visibility toggles) leave the anchor
        # alone: pyqtgraph's GraphicsWidgetAnchor already tracks the
        # legend's current position, including any user drag, so
        # touching it would clobber those.
        if entry_count == 0:
            self._legend_corner = None
        elif self._legend_corner is None:
            corner = self._find_least_occupied_corner()
            offsets = {
                'top-right': (10, 10),
                'top-left': (10, 10),
                'bottom-right': (10, 10),
                'bottom-left': (10, 10),
            }
            anchors = {
                'top-right': (1, 0),
                'top-left': (0, 0),
                'bottom-right': (1, 1),
                'bottom-left': (0, 1),
            }
            parent_anchor = anchors[corner]
            self._legend.anchor(
                itemPos=parent_anchor,
                parentPos=parent_anchor,
                offset=offsets[corner],
            )
            self._legend_corner = corner

    def _clear_items(self) -> None:
        """Remove all data items and reset the legend."""
        # Preserve annotation position before clearing
        if self._annotation_item is not None:
            self._annotation_pos = self._annotation_item.pos()
        all_items = [
            self._annotation_item,
            self._dropped_item,
            self._average_item,
            self._error_bar_item,
            *self._replica_items,
            *self._fit_items,
            *self._error_cap_items,
            *getattr(self, '_dropped_items', []),
        ]
        for item in all_items:
            if item is not None:
                self._pg_widget.removeItem(item)

        self._replica_items = []
        self._dropped_item = None
        self._dropped_items = []
        self._average_item = None
        self._error_bar_item = None
        self._error_cap_items = []
        self._fit_items = []
        self._annotation_item = None
        self._last_error_bar_data = None

        self._replica_ids = []
        self._dropped_replica_ids = []
        self._fit_labels = []
        self._fit_results = []

        plot_item = self._pg_widget.getPlotItem()
        if plot_item.legend is not None:
            plot_item.legend.clear()

    def _find_least_occupied_corner(self, exclude: str | None = None) -> str:
        """Determine which corner of the view has the fewest data points.

        Parameters
        ----------
        exclude : str, optional
            Corner to exclude (e.g. already used by legend).

        Returns
        -------
        str
            One of 'top-left', 'top-right', 'bottom-left', 'bottom-right'.
        """
        vr = self._pg_widget.getViewBox().viewRect()
        cx = vr.center().x()
        cy = vr.center().y()

        # Collect all visible data points
        all_x: list[float] = []
        all_y: list[float] = []
        for item in self._replica_items:
            if item.isVisible():
                data = item.getData()
                if data[0] is not None:
                    all_x.extend(data[0].tolist())
                    all_y.extend(data[1].tolist())
        if self._dropped_item is not None and self._dropped_item.isVisible():
            data = self._dropped_item.getData()
            if data[0] is not None:
                all_x.extend(data[0].tolist())
                all_y.extend(data[1].tolist())
        for item in getattr(self, '_dropped_items', []):
            if item.isVisible():
                data = item.getData()
                if data[0] is not None:
                    all_x.extend(data[0].tolist())
                    all_y.extend(data[1].tolist())

        counts = {'top-left': 0, 'top-right': 0, 'bottom-left': 0, 'bottom-right': 0}
        for px, py in zip(all_x, all_y):
            h = 'left' if px < cx else 'right'
            v = 'bottom' if py < cy else 'top'
            counts[f'{v}-{h}'] += 1

        if exclude:
            counts.pop(exclude, None)

        return min(counts, key=counts.get)

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
                unit_str = units_dict.get(key, '')
                unit_html = f' {fmt_unit_html(unit_str)}' if unit_str else ''
                val_mag = float(val.magnitude) if isinstance(val, Quantity) else float(val)
                unc_mag = float(unc.magnitude) if isinstance(unc, Quantity) else float(unc)
                # Format with Pint HTML for proper superscripts, then strip unit
                if unit_str:
                    val_html = f'{Q_(val_mag, unit_str):.3g~H}'.rsplit(' ', 1)[0]
                    unc_html = f'{Q_(unc_mag, unit_str):.3g~H}'.rsplit(' ', 1)[0]
                else:
                    val_html = f'{val_mag:.3g}'
                    unc_html = f'{unc_mag:.3g}'
                lines.append(f'{fmt_param(key)} = {val_html} &plusmn; {unc_html}{unit_html}')

            lines.append(f'<b>R\u00b2:</b> {result.r_squared:.4f}')
            lines.append(f'<b>RMSE:</b> {Q_(result.rmse, "au"):.3g~H}')

            if idx < len(self._fit_results) - 1:
                lines.append('')

        body = '<br>'.join(lines)
        bg_rgba = self._style['annotations'].get('background_color', (255, 255, 255, 200))
        r, g, b = int(bg_rgba[0]), int(bg_rgba[1]), int(bg_rgba[2])
        a_frac = (bg_rgba[3] if len(bg_rgba) >= 4 else 255) / 255.0
        bg_css = f'rgba({r},{g},{b},{a_frac:.3f})'
        html = f'<div style="font-size:{font_pt}pt; background-color: {bg_css}; padding:4px; border:1px solid #aaa;">{body}</div>'
        # Choose annotation corner, excluding the one occupied by the legend
        # so the fit-results overlay never covers the legend on a fresh build.
        corner = self._find_least_occupied_corner(exclude=self._legend_corner)
        anchor_map = {
            'top-right': (1, 0),
            'top-left': (0, 0),
            'bottom-right': (1, 1),
            'bottom-left': (0, 1),
        }
        anchor = anchor_map[corner]
        self._annotation_item = pg.TextItem(html=html, anchor=anchor)
        self._annotation_item.setFlag(self._annotation_item.GraphicsItemFlag.ItemIsMovable)
        self._pg_widget.addItem(self._annotation_item)
        # Sticky: once a position is remembered (either the initial
        # auto-placed one or a user drag), re-use it on every rebuild.
        if self._annotation_pos is not None:
            self._annotation_item.setPos(self._annotation_pos)
        else:
            vr = self._pg_widget.getViewBox().viewRect()
            pos_map = {
                'top-right': (vr.right(), vr.top() + vr.height()),
                'top-left': (vr.left(), vr.top() + vr.height()),
                'bottom-right': (vr.right(), vr.top()),
                'bottom-left': (vr.left(), vr.top()),
            }
            px, py = pos_map[corner]
            self._annotation_item.setPos(px, py)
