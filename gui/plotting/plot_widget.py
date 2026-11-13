"""The Simulation window's live plot: a PyQtGraph plot of replicates, their mean and model curves, and the shared axis item."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from core.units import Q_
from gui.plotting.colors import (
    AVERAGE_LINE_COLOR,
    BACKGROUND_COLOR,
    DROPPED_REPLICA_COLOR,
    ERROR_BAR_COLOR,
    FIT_PALETTE,
    FOREGROUND_COLOR,
    PALETTES,
    REPLICA_PALETTE,
    rgba,
)
from gui.plotting.labels import (
    _display_label,
    _format_exponent_unicode,
)
from gui.plotting.plot_style import DEFAULT_STYLE, line_style_to_qt

# Legend auto-placement. PyQtGraph has no equivalent of matplotlib's legend
# loc='best' — upstream issue #2769 asking for one is still open — so the
# candidate-and-score search lives here.
_OVERLAY_PAD_PX = 8
#: Candidate slots as (x, y) fractions of the free space inside the ViewBox,
#: in preference order: ties fall to the conventional top-right.
_OVERLAY_SLOTS: tuple[tuple[float, float], ...] = (
    (1.0, 0.0),
    (0.0, 0.0),
    (1.0, 1.0),
    (0.0, 1.0),
    (0.5, 0.0),
    (0.5, 1.0),
)


_X_UNIT_SCALES: dict[str, float] = {label: float(Q_(1, label).to('M').magnitude) for label in ('nM', 'µM', 'mM', 'M')}
# Invert: we need M→display, i.e. multiply M value to get display value
_X_UNIT_SCALES = {k: 1.0 / v for k, v in _X_UNIT_SCALES.items()}


def _x_unit_scale(x_unit: str) -> float:
    """Return the M→display multiplier for an x-axis concentration unit.

    Fast path uses the precomputed table; any other valid concentration unit is
    derived from Pint. An unknown/invalid token raises instead of silently
    falling back to a fixed scale (which would mis-scale the axis while the
    label showed a different unit).
    """
    scale = _X_UNIT_SCALES.get(x_unit)
    if scale is not None:
        return scale
    try:
        return 1.0 / float(Q_(1, x_unit).to('M').magnitude)
    except Exception as err:
        raise ValueError(
            f'Invalid x-axis concentration unit {x_unit!r} in plot style; expected e.g. nM, µM, mM, M.'
        ) from err


def _replica_order(plot_data: dict[str, Any]) -> tuple[str, ...]:
    """Every replicate id in the data's order, which fixes each replicate's label and colour.

    ``all_replica_ids`` when the data carries it (``prepare_plot_data`` always
    does); otherwise the order the replicates are listed in.
    """
    listed = plot_data.get('all_replica_ids')
    if listed:
        return tuple(str(rid) for rid in listed)
    groups = ('active_replicas', 'left_out_replicas', 'dropped_replicas')
    return tuple(str(rid) for group in groups for rid, _ in plot_data.get(group, []))


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

    One exponent holds for every tick level of a draw, and it is read from the
    major level: pyqtgraph formats each level on its own, and a minor tick past
    10 000 under major ticks that end at 10 000 would otherwise set an exponent
    the major labels, written plain, do not carry.

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
        # The major tick values of the draw in progress, which every level's
        # labels take their exponent from; None until the axis draws ticks of
        # its own choosing.
        self._major_values: list[float] | None = None

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

    def tickValues(self, minVal, maxVal, size):
        """The ticks of one draw; the first level holding any is the major one, which sets the exponent."""
        levels = super().tickValues(minVal, maxVal, size)
        self._major_values = next((list(values) for _, values in levels if len(values)), [])
        return levels

    @staticmethod
    def _exponent_of(values, scale) -> int | None:
        """The exponent factored out of *values*: none where the largest lies in [0.01, 10 000] or all are 0."""
        abs_vals = [abs(v * scale) for v in values if v * scale != 0]
        if not abs_vals:
            return None
        max_abs = max(abs_vals)
        if 1e-2 <= max_abs <= 1e4:
            return None
        return int(np.floor(np.log10(max_abs)))

    def tickStrings(self, values, scale, spacing):
        if not values:
            # An empty minor level leaves the major level's exponent standing;
            # an axis with no tick at all has none.
            if not self._major_values:
                self._set_exponent(None)
            return []

        if not self._use_exponent:
            self._set_exponent(None)
            return [f'{v * scale:g}' for v in values]

        # Every level of a draw takes the major level's exponent; values given
        # outside a draw (no major level known) set their own.
        exp = self._exponent_of(self._major_values or values, scale)
        self._set_exponent(exp)
        if exp is None:
            return [f'{v * scale:g}' for v in values]
        divisor = 10**exp
        return ['0' if v * scale == 0 else f'{v * scale / divisor:g}' for v in values]


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
        axis_items = {
            'bottom': ScientificAxisItem(orientation='bottom'),
            'left': ScientificAxisItem(orientation='left'),
        }
        # Colours and antialiasing are set on this view and on the curves drawn
        # in it, never on pyqtgraph's process-wide defaults: those reach every
        # other plot in the application, so a tab would draw differently
        # depending on which other plot had been built first. A curve
        # carries its own antialiasing setting, taken when it is built, and
        # paints by that rather than by the view's, so each says so itself.
        self._pg_widget = pg.PlotWidget(axisItems=axis_items, background=BACKGROUND_COLOR)
        self._pg_widget.setAntialiasing(True)
        self._pg_widget.setTitle(title, color=FOREGROUND_COLOR)
        self._pg_widget.setLabel('bottom', x_label)
        self._pg_widget.setLabel('left', y_label)
        self._legend = self._pg_widget.addLegend(labelTextSize='10pt', labelTextColor=FOREGROUND_COLOR)

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
        layout.setSpacing(0)
        layout.addWidget(self._pg_widget)

        # Wire exponent callbacks so axis labels update reactively after paint
        left_ax: ScientificAxisItem = self._pg_widget.getAxis('left')
        left_ax.on_exponent_changed = self._on_y_exponent_changed
        bottom_ax: ScientificAxisItem = self._pg_widget.getAxis('bottom')
        bottom_ax.on_exponent_changed = self._on_x_exponent_changed

        self._style: dict = DEFAULT_STYLE

        self._replica_items: list[pg.ScatterPlotItem] = []
        self._dropped_items: list[pg.ScatterPlotItem] = []
        self._left_out_items: list[pg.ScatterPlotItem] = []
        self._average_item: pg.PlotCurveItem | None = None
        self._error_bar_item: pg.ErrorBarItem | None = None
        self._error_cap_items: list[pg.PlotCurveItem] = []
        self._fit_items: list[pg.PlotCurveItem] = []
        self._legend_placed = False

        self._replica_ids: list[str] = []
        self._all_replica_ids: tuple[str, ...] = ()
        self._dropped_replica_ids: list[str] = []
        self._left_out_replica_ids: list[str] = []
        self._fit_labels: list[str] = []

        self._last_x_label_base: str | None = None
        self._last_y_label: str | None = None
        self._last_y_unit: str = 'a.u.'

    @property
    def plot_item(self) -> pg.PlotItem:
        """The underlying pyqtgraph PlotItem — used to x-link a second plot to this one."""
        return self._pg_widget.getPlotItem()

    @property
    def x_unit(self) -> str:
        """Current x-axis concentration unit (e.g. ``'µM'``) — for a linked plot to match."""
        return self._style['axes'].get('x_unit', 'µM')

    def update_plot(
        self,
        plot_data: dict[str, Any],
        *,
        x_label: str | None = None,
        y_label: str | None = None,
        y_unit: str | None = None,
    ) -> None:
        """Clear and redraw from a ``prepare_plot_data()`` dict.

        Parameters
        ----------
        plot_data : dict
            As returned by ``core.data_processing.plotting.prepare_plot_data()``.
        x_label : str, optional
            X-axis name (registry value), composed with the unit from
            ``style['axes']['x_unit']``.
        y_label : str, optional
            Y-axis name (registry value).
        y_unit : str, optional
            Y-axis unit suffix (e.g. ``"a.u."``). Auto-managed; not editable
            in the GUI.

        Notes
        -----
        Each replicate's colour and label come from its position in
        ``all_replica_ids``, so they stay the same whichever replicates are
        active and whether or not a fit is shown. Replicates the fit left out
        are drawn in the dropped style.
        """
        self._legend_placed = False
        self._clear_items()

        style = self._style
        x_unit = style['axes'].get('x_unit', 'µM')
        x_scale = _x_unit_scale(x_unit)

        if x_label is not None:
            self._last_x_label_base = x_label
        if y_label is not None:
            self._last_y_label = y_label
        if y_unit is not None:
            self._last_y_unit = y_unit

        x = np.asarray(plot_data.get('concentrations', [])) * x_scale

        # Resolve the active palette
        palette_name = style['data_points'].get('palette', 'Default (Tab10)')
        palette = PALETTES.get(palette_name, REPLICA_PALETTE)

        self._all_replica_ids = _replica_order(plot_data)

        # Active replicas — outlined markers for matplotlib-like look
        active = plot_data.get('active_replicas', [])
        self._replica_ids = []
        if style['visibility']['show_data_points']:
            for rid, sig in active:
                color = palette[self._all_replica_ids.index(str(rid)) % len(palette)]
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

        # Replicates the fit left out, then inactive ones, in the dropped style:
        # individual items so each gets its own legend entry.
        self._left_out_items, self._left_out_replica_ids = self._add_greyed(x, plot_data.get('left_out_replicas', []))
        self._dropped_items, self._dropped_replica_ids = self._add_greyed(x, plot_data.get('dropped_replicas', []))

        # Average line + error bars.
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
            self._average_item = pg.PlotCurveItem(x=x, y=avg_arr, pen=pen, name=None, antialias=True)
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
                    antialias=True,
                )
                self._pg_widget.addItem(item)
                self._fit_items.append(item)
                self._fit_labels.append(fit.get('label', f'fit {i}'))

        # Auto-range first so overlay placement scores against the new view
        # rect; otherwise it would score the previous data range and drop the
        # legend onto the data.
        self._pg_widget.getViewBox().autoRange()
        self._rebuild_legend()
        self._update_axis_labels_with_exponents()

    def set_axis_labels(self, x_label: str, y_label: str, y_unit: str | None = None) -> None:
        """Update the axis names (and optionally the y-unit).

        Parameters
        ----------
        x_label : str
            X-axis name.
        y_label : str
            Y-axis name.
        y_unit : str, optional
            Y-axis unit suffix. If ``None``, the previous value is kept.
        """
        self._last_x_label_base = x_label
        self._last_y_label = y_label
        if y_unit is not None:
            self._last_y_unit = y_unit
        self._update_axis_labels_with_exponents()

    def export_image(self, path: str, width_px: int = 2100) -> None:
        """Export the current plot to a PNG or SVG file.

        Parameters
        ----------
        path : str
            Output file path. Extension determines format: ``.png`` →
            rasterised PNG, ``.svg`` → vector SVG.
        width_px : int
            Output width in pixels for PNG (default 2100, ~7 in @ 300
            DPI). Height is derived from the plot's aspect ratio.
            Ignored for SVG output.

        Raises
        ------
        ValueError
            If the file extension is not ``.png`` or ``.svg``.
        """
        from gui.plotting.export import export_plot_item

        export_plot_item(self._pg_widget.getPlotItem(), path, width_px=width_px)

    def _set_axis_label(self, axis: str, base_label: str, exp: int | None) -> None:
        """Set an axis label, appending ×10ⁿ if *exp* is not None."""
        if exp is not None:
            exp_str = _format_exponent_unicode(exp)
            self._pg_widget.setLabel(axis, f'{base_label}  (×10{exp_str})')
        else:
            self._pg_widget.setLabel(axis, base_label)

    @staticmethod
    def _compose_axis_label(name: str, unit: str) -> str:
        """Compose ``"<name> [<unit>]"``, or the name alone without a unit."""
        return f'{name} [{unit}]' if unit else name

    def _on_y_exponent_changed(self, exp: int | None) -> None:
        """Update y-axis label reactively when the exponent changes during paint."""
        self._set_axis_label('left', self._compose_axis_label(self._last_y_label or '', self._last_y_unit), exp)

    def _on_x_exponent_changed(self, exp: int | None) -> None:
        """Update x-axis label reactively when the exponent changes during paint."""
        x_unit = self._style['axes'].get('x_unit', 'µM')
        self._set_axis_label('bottom', self._compose_axis_label(self._last_x_label_base or '', x_unit), exp)

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
                    antialias=True,
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
                self._legend.addItem(item, _display_label(self._all_replica_ids.index(rid)))
                entry_count += 1
        if leg.get('show_dropped', True) and vis['show_dropped']:
            greyed = (
                (self._left_out_items, self._left_out_replica_ids, 'left out of fit'),
                (self._dropped_items, self._dropped_replica_ids, 'dropped'),
            )
            for items, ids, reason in greyed:
                for item, rid in zip(items, ids):
                    self._legend.addItem(item, f'{_display_label(self._all_replica_ids.index(rid))} ({reason})')
                    entry_count += 1
        if leg['show_average'] and vis['show_average'] and self._average_item is not None:
            self._legend.addItem(self._average_item, 'Mean')
            entry_count += 1
        if leg.get('show_error_bars', True) and vis['show_error_bars'] and self._error_bar_item is not None:
            # Custom sample draws a ┬ ┴ glyph so the legend entry is
            # visually distinct from the average line.
            eb_color = self._style['error_bars'].get('color', ERROR_BAR_COLOR)
            eb_pen = pg.mkPen(color=eb_color, width=self._style['error_bars'].get('width', 1))
            eb_stub = pg.PlotCurveItem(pen=eb_pen, antialias=True)
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

        # Position the legend once per data load. On later rebuilds (style
        # changes, x-unit rescales, visibility toggles) leave the anchor
        # alone: pyqtgraph's GraphicsWidgetAnchor already tracks the
        # legend's current position, including any user drag, so
        # touching it would clobber those.
        if entry_count == 0:
            self._legend_placed = False
        elif not self._legend_placed:
            rect = self._legend.boundingRect()
            slot = self._best_overlay_slot((rect.width(), rect.height()))
            if slot is not None:
                (fx, fy), _ = slot
                # Anchoring (rather than setPos) keeps the legend pinned to the
                # same relative corner when the widget is resized.
                pad = _OVERLAY_PAD_PX
                self._legend.anchor(
                    itemPos=(fx, fy),
                    parentPos=(fx, fy),
                    offset=(pad * (1 - 2 * fx), pad * (1 - 2 * fy)),
                )
                self._legend_placed = True

    def _clear_items(self) -> None:
        """Remove all data items and reset the legend."""
        all_items = [
            self._average_item,
            self._error_bar_item,
            *self._replica_items,
            *self._fit_items,
            *self._error_cap_items,
            *self._dropped_items,
            *self._left_out_items,
        ]
        for item in all_items:
            if item is not None:
                self._pg_widget.removeItem(item)

        self._replica_items = []
        self._dropped_items = []
        self._left_out_items = []
        self._average_item = None
        self._error_bar_item = None
        self._error_cap_items = []
        self._fit_items = []

        self._replica_ids = []
        self._dropped_replica_ids = []
        self._left_out_replica_ids = []
        self._fit_labels = []

        plot_item = self._pg_widget.getPlotItem()
        if plot_item.legend is not None:
            plot_item.legend.clear()

    def _add_greyed(self, x: np.ndarray, replicas: list) -> tuple[list[pg.ScatterPlotItem], list[str]]:
        """Scatter each ``(replica_id, signal)`` of *replicas* in the dropped style; return the items and ids."""
        style = self._style['dropped_replicas']
        items: list[pg.ScatterPlotItem] = []
        ids: list[str] = []
        if not self._style['visibility']['show_dropped']:
            return items, ids
        for rid, sig in replicas:
            item = pg.ScatterPlotItem(
                x=x,
                y=np.asarray(sig),
                symbol=style['symbol'],
                size=style['size'],
                pen=pg.mkPen(None),
                brush=pg.mkBrush(rgba(DROPPED_REPLICA_COLOR, style['alpha'])),
                name=None,
            )
            self._pg_widget.addItem(item)
            items.append(item)
            ids.append(str(rid))
        return items, ids

    def _obstacle_points_px(self) -> np.ndarray:
        """Every plotted vertex, in ViewBox-local pixel coordinates.

        Includes the fitted curves and the mean line, not just the scatter
        points — the curve is what an overlay most often lands on. Fit curves
        are already sampled densely (``_FIT_CURVE_POINTS``), so counting
        vertices stands in for testing segment/rectangle intersection.
        """
        vb = self._pg_widget.getViewBox()
        (x0, x1), (y0, y1) = vb.viewRange()
        width, height = vb.width(), vb.height()
        if x1 <= x0 or y1 <= y0 or width <= 0 or height <= 0:
            return np.empty((0, 2))

        xs: list[np.ndarray] = []
        ys: list[np.ndarray] = []
        items = [
            *self._replica_items,
            *self._dropped_items,
            *self._left_out_items,
            *self._fit_items,
            *self._error_cap_items,
            self._average_item,
        ]
        for item in items:
            if item is None or not item.isVisible():
                continue
            data_x, data_y = item.getData()
            if data_x is None or len(data_x) == 0:
                continue
            xs.append(np.asarray(data_x, dtype=float))
            ys.append(np.asarray(data_y, dtype=float))
        if not xs:
            return np.empty((0, 2))

        data_x = np.concatenate(xs)
        data_y = np.concatenate(ys)
        # y grows upward in data space but downward in pixels.
        px = (data_x - x0) / (x1 - x0) * width
        py = (1.0 - (data_y - y0) / (y1 - y0)) * height
        return np.column_stack((px, py))

    def _best_overlay_slot(self, size: tuple[float, float]) -> tuple[tuple[float, float], QRectF] | None:
        """Emptiest slot for a *size* box: ``(anchor_fractions, rect)`` in pixels.

        A compact port of matplotlib's ``Legend._find_best_position``, which
        PyQtGraph has no equivalent of (upstream issue #2769 is still open):
        score each candidate slot by how many plotted vertices it would cover,
        and keep the lowest. Candidates are ordered so ties fall to the conventional
        top-right. Returns ``None`` while the ViewBox has no usable geometry.
        """
        vb = self._pg_widget.getViewBox()
        width, height = vb.width(), vb.height()
        box_w, box_h = size
        if width <= 0 or height <= 0 or box_w <= 0 or box_h <= 0:
            return None

        pad = _OVERLAY_PAD_PX
        free_w = max(0.0, width - box_w - 2 * pad)
        free_h = max(0.0, height - box_h - 2 * pad)
        points = self._obstacle_points_px()

        best: tuple[tuple[float, float], QRectF] | None = None
        best_badness = None
        for fx, fy in _OVERLAY_SLOTS:
            rect = QRectF(pad + fx * free_w, pad + fy * free_h, box_w, box_h)
            badness = 0.0
            if points.size:
                inside = (
                    (points[:, 0] >= rect.left())
                    & (points[:, 0] <= rect.right())
                    & (points[:, 1] >= rect.top())
                    & (points[:, 1] <= rect.bottom())
                )
                badness = float(np.count_nonzero(inside))
            if best_badness is None or badness < best_badness:
                best, best_badness = ((fx, fy), rect), badness
            if badness == 0:
                break
        return best
