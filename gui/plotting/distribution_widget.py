"""Box-whisker distribution plots for fitted parameters (pyqtgraph)."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QStackedLayout, QWidget

from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.pipeline.fit_pipeline import FitResult
from gui.plotting.colors import BACKGROUND_COLOR, FOREGROUND_COLOR, PALETTES, REPLICA_PALETTE, rgba
from gui.plotting.labels import fmt_param, fmt_unit_html
from gui.plotting.plot_style import DEFAULT_STYLE
from gui.plotting.plot_widget import ScientificAxisItem, _format_exponent_unicode
from gui.widgets.replica_panel import _display_label

_BOX_HALF = 0.3
_CAP_HALF = 0.2
_JITTER_HALF = 0.25

# Fallback per-cell logical pixel size when the live widget hasn't
# been shown yet (e.g. headless tests, dialog opened before the
# distributions tab was visible). The export then renders at this
# default; the user can resize the live widget and re-export to get
# different proportions.
_FALLBACK_CELL_W = 320
_FALLBACK_CELL_H = 380


def _box_stats(data: np.ndarray) -> Dict[str, float]:
    """Compute box-whisker statistics for a 1-D array."""
    q1, median, q3 = np.percentile(data, [25, 50, 75])
    iqr = q3 - q1
    whisker_lo = max(data.min(), q1 - 1.5 * iqr)
    whisker_hi = min(data.max(), q3 + 1.5 * iqr)
    return {
        'q1': float(q1),
        'median': float(median),
        'q3': float(q3),
        'whisker_lo': float(whisker_lo),
        'whisker_hi': float(whisker_hi),
    }


def _refresh_axis_label_with_exponent(plot_item: pg.PlotItem, exp: int | None) -> None:
    """Re-apply the y-axis label, appending ×10ⁿ when an exponent is set.

    The base label (without the exponent suffix) is stored on the
    PlotItem as ``_y_base_label`` by :meth:`DistributionWidget._populate_subplot`.
    ``ScientificAxisItem`` fires its ``on_exponent_changed`` callback on
    every tickStrings() pass; that callback funnels through this
    helper, so live and export PlotItems share one reactive update
    path.
    """
    base = getattr(plot_item, '_y_base_label', None)
    if not base:
        return
    if exp is not None:
        exp_str = _format_exponent_unicode(exp)
        plot_item.setLabel('left', f'{base}  (×10{exp_str})')
    else:
        plot_item.setLabel('left', base)


def _wire_exponent_callback(plot_item: pg.PlotItem, axis: ScientificAxisItem) -> None:
    """Wire *axis* to update *plot_item*'s y-label when its exponent changes."""

    def _on_exp(exp: int | None) -> None:
        _refresh_axis_label_with_exponent(plot_item, exp)

    axis.on_exponent_changed = _on_exp


class DistributionWidget(QWidget):
    """Side-by-side box-whisker plots of fitted parameter distributions.

    One pyqtgraph subplot per parameter, arranged horizontally.

    **Per-replica mode**: x-axis = replica ID (A, B, C, …).  Each replica
    gets its own box-whisker at its x position.  A red pooled-median line
    spans all positions.

    **Average mode**: x-axis labeled "Pool of Fits" with no tick marks.
    One box-whisker at x=0 for the single optimizer pool.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._style: dict = dict(DEFAULT_STYLE)
        self._plots: list[pg.PlotWidget] = []
        self._result: FitResult | None = None
        self._param_keys: list[str] = []

        self._stack = QStackedLayout(self)

        self._placeholder = QLabel('Run a fit to see parameter distributions.')
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet('color: rgba(0,0,0,0.35); font-size: 14px;')
        self._stack.addWidget(self._placeholder)

        self._plot_container = QWidget()
        self._plot_layout = QHBoxLayout(self._plot_container)
        self._plot_layout.setContentsMargins(0, 0, 0, 0)
        self._plot_layout.setSpacing(4)
        self._stack.addWidget(self._plot_container)

        self._stack.setCurrentWidget(self._placeholder)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_result(self, result: FitResult) -> None:
        """Redraw all subplots from a FitResult's parameter_samples."""
        self._result = result

        if result.parameter_samples is None or not result.parameters:
            self._stack.setCurrentWidget(self._placeholder)
            return

        param_keys = list(result.parameter_samples.keys())
        self._param_keys = list(param_keys)

        self._rebuild_subplots(len(param_keys))

        for i, key in enumerate(param_keys):
            plot_item = self._plots[i].getPlotItem()
            self._clear_subplot(plot_item)
            self._populate_subplot(plot_item, key=key, param_idx=i, add_legend=(i == 0))

        self._stack.setCurrentWidget(self._plot_container)

    def apply_style(self, style: dict) -> None:
        """Update visual style (fonts, palette) from PlotStyleWidget."""
        self._style = style
        if self._result is not None:
            self.update_result(self._result)

    def clear(self) -> None:
        """Reset to empty placeholder."""
        self._result = None
        self._param_keys = []
        for pw in self._plots:
            self._clear_subplot(pw.getPlotItem())
        self._stack.setCurrentWidget(self._placeholder)

    def param_keys(self) -> list[str]:
        """Parameter keys of the currently displayed subplots, in order."""
        return list(self._param_keys)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def live_per_cell_size(self) -> tuple[int, int]:
        """Pixel size of a single live distribution subplot.

        This is the source of truth for export rendering: the transient
        export layout uses cells of exactly this size so the
        font:cell, line-width:cell, and marker:cell ratios all match
        the GUI by construction. Falls back to a sensible default when
        the live widget hasn't been laid out yet (headless tests,
        hidden tab).
        """
        if self._plots:
            w = self._plots[0].width()
            h = self._plots[0].height()
            if w >= 50 and h >= 50:
                return w, h
        return _FALLBACK_CELL_W, _FALLBACK_CELL_H

    def derive_height_in(self, *, width_in: float, rows: int, cols: int) -> float:
        """Height in inches that preserves live cell aspect for the chosen layout.

        With the export figure rendered at ``cell_w × cols`` wide and
        ``cell_h × rows`` tall (where ``cell_*`` come from
        :meth:`live_per_cell_size`), the figure aspect is fixed. Given
        a user-chosen ``width_in``, the matching ``height_in`` is the
        only choice that keeps each export cell at the same aspect as
        the live GUI cell.
        """
        cw, ch = self.live_per_cell_size()
        return width_in * (rows * ch) / max(cols * cw, 1)

    def build_composite_layout(
        self,
        keys: list[str],
        rows: int,
        cols: int,
    ) -> pg.GraphicsLayoutWidget:
        """Build a transient ``GraphicsLayoutWidget`` whose cells match the live GUI.

        Each cell is sized to the live distribution subplot's pixel
        dimensions, so when the caller hands the resulting scene to
        :func:`gui.plotting.export.export_scene` the painter scales
        every element uniformly. Font:cell, line:cell, and marker:cell
        ratios are preserved by construction — no per-element scaling.

        Raises
        ------
        ValueError
            If no distributions are loaded, no keys match, or
            ``rows * cols`` is less than the number of selected keys.
        """
        if not self._param_keys:
            raise ValueError('No distributions to render. Run a fit first.')

        indices = [self._param_keys.index(k) for k in keys if k in self._param_keys]
        if not indices:
            raise ValueError('No matching distributions selected.')
        if rows * cols < len(indices):
            raise ValueError(f'Layout {rows}x{cols} cannot fit {len(indices)} subplots.')

        glw = pg.GraphicsLayoutWidget()
        glw.setBackground(BACKGROUND_COLOR)

        for i, key_idx in enumerate(indices):
            r, c = divmod(i, cols)
            left_axis = ScientificAxisItem(orientation='left')
            left_axis.enableAutoSIPrefix(False)
            plot_item = glw.addPlot(row=r, col=c, axisItems={'left': left_axis})
            _wire_exponent_callback(plot_item, left_axis)
            plot_item.getViewBox().setDefaultPadding(0.05)
            plot_item.getAxis('bottom').enableAutoSIPrefix(False)

            key = self._param_keys[key_idx]
            self._populate_subplot(plot_item, key=key, param_idx=key_idx, add_legend=(i == 0))

        return glw

    def save_plot(
        self,
        *,
        keys: list[str],
        rows: int,
        cols: int,
        width_in: float,
        dpi: int,
        path: str,
        format: str = 'png',
    ) -> None:
        """Save the distributions composite as PNG or SVG.

        The export figure's aspect is fixed by ``rows × cols`` of live
        cells, so the user picks only ``width_in``; the output height
        in pixels is the painter-scaled live cell height × rows.

        PyQtGraph's ``ImageExporter`` / ``SVGExporter`` render the
        transient scene at this fixed aspect into the requested output
        width — font:cell ratios match the GUI exactly.
        """
        from gui.plotting.export import (
            export_scene,
            prepare_widget_for_offscreen_render,
        )

        fmt = format.lower()
        if fmt not in ('png', 'svg'):
            raise ValueError(f"Unsupported format: '{format}'. Use 'png' or 'svg'.")

        cell_w, cell_h = self.live_per_cell_size()
        glw = self.build_composite_layout(keys, rows, cols)
        try:
            logical_w = cell_w * cols
            logical_h = cell_h * rows
            prepare_widget_for_offscreen_render(glw, logical_w, logical_h)
            if fmt == 'png':
                target_w = round(width_in * dpi)
                export_scene(glw.scene(), path, width_px=target_w)
            else:
                # SVG is vector; native scene size suffices.
                export_scene(glw.scene(), path)
        finally:
            glw.deleteLater()

    @staticmethod
    def auto_layout(n: int) -> tuple[int, int]:
        """Default rows×cols for *n* subplots (matches legacy Auto behaviour)."""
        import math

        if n <= 1:
            return 1, max(1, n)
        if n == 2:
            return 1, 2
        if n == 3:
            return 1, 3
        if n == 4:
            return 2, 2
        cols = 2
        return math.ceil(n / cols), cols

    # ------------------------------------------------------------------
    # Subplot construction
    # ------------------------------------------------------------------

    @staticmethod
    def _clear_subplot(plot_item: pg.PlotItem) -> None:
        """Remove all data items AND the legend from a PlotItem."""
        plot_item.clear()
        legend = plot_item.legend
        if legend is not None:
            if legend.scene() is not None:
                legend.scene().removeItem(legend)
            plot_item.legend = None

    def _rebuild_subplots(self, n: int) -> None:
        """Ensure we have exactly *n* PlotWidget instances with ScientificAxisItem."""
        while len(self._plots) > n:
            pw = self._plots.pop()
            self._plot_layout.removeWidget(pw)
            pw.deleteLater()
        while len(self._plots) < n:
            left_axis = ScientificAxisItem(orientation='left')
            left_axis.enableAutoSIPrefix(False)

            pw = pg.PlotWidget(
                background=BACKGROUND_COLOR,
                axisItems={'left': left_axis},
            )
            plot_item = pw.getPlotItem()
            plot_item.getViewBox().setDefaultPadding(0.05)
            plot_item.getAxis('bottom').enableAutoSIPrefix(False)

            _wire_exponent_callback(plot_item, left_axis)

            self._plots.append(pw)
            self._plot_layout.addWidget(pw)

    def _populate_subplot(
        self,
        plot_item: pg.PlotItem,
        *,
        key: str,
        param_idx: int,
        add_legend: bool = False,
    ) -> None:
        """Populate one PlotItem with the box-whisker distribution for *key*.

        Single source of truth for distribution subplot rendering: used
        both by :meth:`update_result` on the live widget and by
        :meth:`build_composite_layout` on the export-time transient
        ``GraphicsLayoutWidget``. The PlotItem's y-axis base label is
        stored on the item itself (``_y_base_label``) so
        :func:`_refresh_axis_label_with_exponent` can reactively
        re-apply it when ``ScientificAxisItem`` factors out an
        exponent.
        """
        result = self._result
        if result is None or result.parameter_samples is None or not result.parameters:
            return

        assay_type = self._lookup_assay_type(result.assay_type)
        log_keys: set[str] = set()
        units: dict[str, str] = {}
        if assay_type is not None:
            meta = ASSAY_REGISTRY[assay_type]
            log_keys = set(meta.log_scale_keys)
            units = dict(meta.units)

        ka_scale = self._style.get('distribution', {}).get('ka_scale', 'log₁₀')
        palette_name = self._style['data_points'].get('palette', 'Default (Tab10)')
        palette = PALETTES.get(palette_name, REPLICA_PALETTE)

        replica_samples = self._extract_replica_samples(result)
        n_replicas = len(replica_samples) if replica_samples else 0

        if n_replicas > 0:
            x_positions = list(range(n_replicas))
            x_tick_labels = [_display_label(i) for i in range(n_replicas)]
            x_axis_label = 'Replica'
        else:
            x_positions = [0]
            x_tick_labels = []
            x_axis_label = 'Pool of Fits'

        pool = result.parameter_samples[key]
        use_log = (key in log_keys) and ka_scale == 'log₁₀'
        values = np.log10(pool) if use_log else pool
        pool_stats = _box_stats(values)

        # Boxes: one per replica in per-replica mode, one pooled in average mode
        if replica_samples:
            for r_idx, r_samp in enumerate(replica_samples):
                r_vals = r_samp.get(key)
                if r_vals is None:
                    continue
                r_display = np.log10(r_vals) if use_log else r_vals
                r_stats = _box_stats(r_display)
                color = palette[r_idx % len(palette)]
                self._draw_box(plot_item, r_stats, float(x_positions[r_idx]), color)
        else:
            self._draw_box(plot_item, pool_stats, 0.0)

        self._draw_strip(plot_item, values, replica_samples, key, param_idx, palette, use_log, x_positions)
        self._draw_median_line(plot_item, pool_stats['median'], x_positions)

        if replica_samples:
            self._draw_replica_medians(plot_item, replica_samples, key, palette, use_log, x_positions)

        # Y-axis label — base form; ScientificAxisItem appends ×10ⁿ via callback.
        unit_str = units.get(key, '')
        label = fmt_param(key)
        if use_log:
            base_label = f'log₁₀({label})'
        else:
            base_label = f'{label} [{fmt_unit_html(unit_str)}]' if unit_str else label
        plot_item._y_base_label = base_label
        # Reset cached exponent so the next tickStrings() pass re-fires the callback.
        left_axis = plot_item.getAxis('left')
        if hasattr(left_axis, 'exponent'):
            left_axis.exponent = None
        plot_item.setLabel('left', base_label)

        # X-axis ticks and label
        bottom_ax = plot_item.getAxis('bottom')
        bottom_ax.setTicks([[(pos, lbl) for pos, lbl in zip(x_positions, x_tick_labels)]])
        plot_item.setLabel('bottom', x_axis_label)

        # Title — mirror the log-wrap so title + axis stay consistent
        title_size = self._style.get('distribution', {}).get('title_font_size', 16)
        title_text = f'log₁₀({label})' if use_log else label
        plot_item.setTitle(title_text, size=f'{title_size}pt', bold=True)

        self._apply_axis_style(plot_item)

        x_pad = 0.8
        plot_item.setXRange(min(x_positions) - x_pad, max(x_positions) + x_pad, padding=0)
        plot_item.enableAutoRange(axis='y')

        if add_legend:
            self._add_legend(plot_item, replica_samples is not None)

    # ------------------------------------------------------------------
    # Drawing primitives (PlotItem-based)
    # ------------------------------------------------------------------

    def _draw_box(
        self,
        plot_item: pg.PlotItem,
        stats: Dict[str, float],
        x_center: float,
        color: Tuple[int, int, int] | None = None,
    ) -> None:
        """Draw the box (Q1–Q3), whiskers, and caps at x_center."""
        q1, q3 = stats['q1'], stats['q3']
        wlo, whi = stats['whisker_lo'], stats['whisker_hi']

        dist = self._style.get('distribution', {})
        box_w = dist.get('box_border_width', 1.5)
        wh_w = dist.get('whisker_width', 1.2)

        if color is not None:
            box_pen = pg.mkPen(rgba(color, 200), width=box_w)
            box_brush = pg.mkBrush(rgba(color, 40))
            line_pen = pg.mkPen(rgba(color, 180), width=wh_w)
        else:
            box_pen = pg.mkPen(FOREGROUND_COLOR, width=box_w)
            box_brush = pg.mkBrush(200, 200, 200, 80)
            line_pen = pg.mkPen(FOREGROUND_COLOR, width=wh_w)

        box = pg.BarGraphItem(
            x0=[x_center - _BOX_HALF],
            y0=[q1],
            x1=[x_center + _BOX_HALF],
            y1=[q3],
            pen=box_pen,
            brush=box_brush,
        )
        plot_item.addItem(box)

        for wy in (wlo, whi):
            whisker = pg.PlotCurveItem(
                x=[x_center, x_center],
                y=[q1 if wy == wlo else q3, wy],
                pen=line_pen,
            )
            plot_item.addItem(whisker)
            cap = pg.PlotCurveItem(
                x=[x_center - _CAP_HALF, x_center + _CAP_HALF],
                y=[wy, wy],
                pen=line_pen,
            )
            plot_item.addItem(cap)

    def _draw_strip(
        self,
        plot_item: pg.PlotItem,
        values: np.ndarray,
        replica_samples: Optional[List[Dict[str, np.ndarray]]],
        key: str,
        param_idx: int,
        palette: list,
        use_log: bool,
        x_positions: list[int],
    ) -> None:
        """Jittered strip plot with each replica at its own x position."""
        rng = np.random.default_rng(42 + param_idx)

        if replica_samples:
            for r_idx, r_samp in enumerate(replica_samples):
                r_vals = r_samp.get(key)
                if r_vals is None:
                    continue
                display = np.log10(r_vals) if use_log else r_vals
                n = len(display)
                x_base = x_positions[r_idx] if r_idx < len(x_positions) else r_idx
                jitter = rng.uniform(-_JITTER_HALF, _JITTER_HALF, size=n)
                color = palette[r_idx % len(palette)]
                scatter = pg.ScatterPlotItem(
                    x=np.full(n, x_base) + jitter,
                    y=display,
                    size=5,
                    pen=pg.mkPen(None),
                    brush=pg.mkBrush(rgba(color, 120)),
                )
                plot_item.addItem(scatter)
        else:
            jitter = rng.uniform(-_JITTER_HALF, _JITTER_HALF, size=len(values))
            scatter = pg.ScatterPlotItem(
                x=np.zeros(len(values)) + jitter,
                y=values,
                size=5,
                pen=pg.mkPen(None),
                brush=pg.mkBrush(100, 100, 100, 100),
            )
            plot_item.addItem(scatter)

    def _draw_median_line(self, plot_item: pg.PlotItem, median: float, x_positions: list[int]) -> None:
        """Solid horizontal line at the pool median, spanning all positions."""
        x_lo = min(x_positions) - 0.5
        x_hi = max(x_positions) + 0.5
        dist = self._style.get('distribution', {})
        width = dist.get('median_line_width', 2.5)
        color = dist.get('median_line_color', (220, 0, 0, 255))
        line = pg.PlotCurveItem(
            x=[x_lo, x_hi],
            y=[median, median],
            pen=pg.mkPen(color, width=width),
        )
        plot_item.addItem(line)

    def _draw_replica_medians(
        self,
        plot_item: pg.PlotItem,
        replica_samples: List[Dict[str, np.ndarray]],
        key: str,
        palette: list,
        use_log: bool,
        x_positions: list[int],
    ) -> None:
        """Diamond markers at each replica's median value, at that replica's x."""
        marker_size = self._style.get('distribution', {}).get('replica_median_size', 10)
        for r_idx, r_samp in enumerate(replica_samples):
            r_vals = r_samp.get(key)
            if r_vals is None or len(r_vals) == 0:
                continue
            med = float(np.median(np.log10(r_vals) if use_log else r_vals))
            x_pos = x_positions[r_idx] if r_idx < len(x_positions) else r_idx
            color = palette[r_idx % len(palette)]
            marker = pg.ScatterPlotItem(
                x=[float(x_pos)],
                y=[med],
                symbol='d',
                size=marker_size,
                pen=pg.mkPen(FOREGROUND_COLOR, width=1),
                brush=pg.mkBrush(rgba(color, 220)),
            )
            plot_item.addItem(marker)

    def _add_legend(self, plot_item: pg.PlotItem, has_replicas: bool) -> None:
        """Add a legend to *plot_item* explaining visual elements."""
        dist = self._style.get('distribution', {})
        label_size = dist.get('label_font_size', 14)
        median_w = dist.get('median_line_width', 2.5)
        median_c = dist.get('median_line_color', (220, 0, 0, 255))
        marker_size = dist.get('replica_median_size', 10)

        legend = plot_item.addLegend(offset=(10, 10))
        legend.setLabelTextSize(f'{label_size}pt')

        median_item = pg.PlotCurveItem(pen=pg.mkPen(median_c, width=median_w))
        legend.addItem(median_item, 'Pool median')

        if has_replicas:
            diamond_item = pg.ScatterPlotItem(
                symbol='d',
                size=marker_size,
                pen=pg.mkPen(FOREGROUND_COLOR, width=1),
                brush=pg.mkBrush(150, 150, 150, 220),
            )
            legend.addItem(diamond_item, 'Replica median')

    def _apply_axis_style(self, plot_item: pg.PlotItem) -> None:
        """Apply distribution fonts to axes. Title is handled at setTitle()."""
        dist = self._style.get('distribution', {})
        label_size = dist.get('label_font_size', 14)
        tick_size = dist.get('tick_font_size', 12)

        label_font = QFont()
        label_font.setPointSize(label_size)
        tick_font = QFont()
        tick_font.setPointSize(tick_size)

        for axis_name in ('left', 'bottom'):
            axis = plot_item.getAxis(axis_name)
            axis.label.setFont(label_font)
            axis.setTickFont(tick_font)
            axis.setPen(pg.mkPen(FOREGROUND_COLOR, width=1))
            axis.setTextPen(pg.mkPen(FOREGROUND_COLOR))

    def _extract_replica_samples(
        self,
        result: FitResult,
    ) -> Optional[List[Dict[str, np.ndarray]]]:
        """Return per-replica parameter_samples if available."""
        if result.replica_fits is None:
            return None
        out = []
        for rf in result.replica_fits:
            if rf.parameter_samples is not None:
                out.append(rf.parameter_samples)
        return out or None

    @staticmethod
    def _lookup_assay_type(name: str) -> Optional[AssayType]:
        try:
            return AssayType[name]
        except KeyError:
            return None
