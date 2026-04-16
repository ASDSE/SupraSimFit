"""Box-whisker distribution plots for fitted parameters (pyqtgraph)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

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
        self._y_base_labels: dict[int, str] = {}

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

    def update_result(self, result: FitResult) -> None:
        """Redraw all subplots from a FitResult's parameter_samples."""
        self._result = result

        if result.parameter_samples is None or not result.parameters:
            self._stack.setCurrentWidget(self._placeholder)
            return

        assay_type = self._lookup_assay_type(result.assay_type)
        log_keys: set[str] = set()
        units: dict[str, str] = {}
        if assay_type is not None:
            meta = ASSAY_REGISTRY[assay_type]
            log_keys = set(meta.log_scale_keys)
            units = dict(meta.units)

        param_keys = list(result.parameter_samples.keys())
        replica_samples = self._extract_replica_samples(result)
        n_replicas = len(replica_samples) if replica_samples else 0

        self._rebuild_subplots(len(param_keys))

        palette_name = self._style['data_points'].get('palette', 'Default (Tab10)')
        palette = PALETTES.get(palette_name, REPLICA_PALETTE)

        # X-axis layout
        if n_replicas > 0:
            x_positions = list(range(n_replicas))
            x_tick_labels = [_display_label(i) for i in range(n_replicas)]
            x_axis_label = 'Replica'
        else:
            x_positions = [0]
            x_tick_labels = []
            x_axis_label = 'Pool of Fits'

        self._y_base_labels.clear()
        for i, key in enumerate(param_keys):
            pw = self._plots[i]
            self._clear_subplot(pw)

            pool = result.parameter_samples[key]
            use_log = key in log_keys
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
                    self._draw_box(pw, r_stats, float(x_positions[r_idx]), color)
            else:
                self._draw_box(pw, pool_stats, 0.0)

            self._draw_strip(pw, values, replica_samples, key, i, palette, use_log, x_positions)
            self._draw_median_line(pw, pool_stats['median'], x_positions)

            if replica_samples:
                self._draw_replica_medians(pw, replica_samples, key, palette, use_log, x_positions)

            # Y-axis label
            unit_str = units.get(key, '')
            label = fmt_param(key)
            if use_log:
                base_label = f'log\u2081\u2080({label})'
            else:
                base_label = f'{label} [{fmt_unit_html(unit_str)}]' if unit_str else label
            self._y_base_labels[i] = base_label
            pw.setLabel('left', base_label)

            # X-axis ticks and label
            bottom_ax = pw.getPlotItem().getAxis('bottom')
            bottom_ax.setTicks([[(pos, lbl) for pos, lbl in zip(x_positions, x_tick_labels)]])
            pw.setLabel('bottom', x_axis_label)

            pw.setTitle(label)
            self._apply_axis_style(pw)

            x_pad = 0.8
            pw.setXRange(min(x_positions) - x_pad, max(x_positions) + x_pad, padding=0)
            pw.enableAutoRange(axis='y')

        if self._plots:
            self._add_legend(self._plots[0], replica_samples is not None)

        self._stack.setCurrentWidget(self._plot_container)

    def apply_style(self, style: dict) -> None:
        """Update visual style (fonts, palette) from PlotStyleWidget."""
        self._style = style
        if self._result is not None:
            self.update_result(self._result)

    def clear(self) -> None:
        """Reset to empty placeholder."""
        self._result = None
        for pw in self._plots:
            self._clear_subplot(pw)
        self._stack.setCurrentWidget(self._placeholder)

    @staticmethod
    def _clear_subplot(pw: pg.PlotWidget) -> None:
        """Remove all data items AND the legend from a subplot."""
        pw.clear()
        legend = pw.getPlotItem().legend
        if legend is not None:
            if legend.scene() is not None:
                legend.scene().removeItem(legend)
            pw.getPlotItem().legend = None

    def _rebuild_subplots(self, n: int) -> None:
        """Ensure we have exactly *n* PlotWidget instances with ScientificAxisItem."""
        while len(self._plots) > n:
            pw = self._plots.pop()
            self._plot_layout.removeWidget(pw)
            pw.deleteLater()
        while len(self._plots) < n:
            idx = len(self._plots)
            left_axis = ScientificAxisItem(orientation='left')
            left_axis.enableAutoSIPrefix(False)

            pw = pg.PlotWidget(
                background=BACKGROUND_COLOR,
                axisItems={'left': left_axis},
            )
            pw.getPlotItem().getViewBox().setDefaultPadding(0.05)
            pw.getPlotItem().getAxis('bottom').enableAutoSIPrefix(False)

            def _make_callback(plot_idx: int):
                def _on_exp(exp: int | None):
                    self._on_y_exponent_changed(plot_idx, exp)
                return _on_exp

            left_axis.on_exponent_changed = _make_callback(idx)

            self._plots.append(pw)
            self._plot_layout.addWidget(pw)

    def _on_y_exponent_changed(self, plot_idx: int, exp: int | None) -> None:
        """Update y-axis label with ×10ⁿ suffix when exponent changes."""
        base = self._y_base_labels.get(plot_idx, '')
        if not base:
            return
        if exp is not None:
            exp_str = _format_exponent_unicode(exp)
            label = f'{base}  (\u00d710{exp_str})'
        else:
            label = base
        if plot_idx < len(self._plots):
            self._plots[plot_idx].setLabel('left', label)

    def _draw_box(
        self,
        pw: pg.PlotWidget,
        stats: Dict[str, float],
        x_center: float,
        color: Tuple[int, int, int] | None = None,
    ) -> None:
        """Draw the box (Q1–Q3), whiskers, and caps at x_center."""
        q1, q3 = stats['q1'], stats['q3']
        wlo, whi = stats['whisker_lo'], stats['whisker_hi']

        if color is not None:
            box_pen = pg.mkPen(rgba(color, 200), width=1.5)
            box_brush = pg.mkBrush(rgba(color, 40))
            line_pen = pg.mkPen(rgba(color, 180), width=1.2)
        else:
            box_pen = pg.mkPen(FOREGROUND_COLOR, width=1.5)
            box_brush = pg.mkBrush(200, 200, 200, 80)
            line_pen = pg.mkPen(FOREGROUND_COLOR, width=1.2)

        box = pg.BarGraphItem(
            x0=[x_center - _BOX_HALF], y0=[q1],
            x1=[x_center + _BOX_HALF], y1=[q3],
            pen=box_pen, brush=box_brush,
        )
        pw.addItem(box)

        for wy in (wlo, whi):
            whisker = pg.PlotCurveItem(
                x=[x_center, x_center], y=[q1 if wy == wlo else q3, wy],
                pen=line_pen,
            )
            pw.addItem(whisker)
            cap = pg.PlotCurveItem(
                x=[x_center - _CAP_HALF, x_center + _CAP_HALF], y=[wy, wy],
                pen=line_pen,
            )
            pw.addItem(cap)

    def _draw_strip(
        self,
        pw: pg.PlotWidget,
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
                    x=np.full(n, x_base) + jitter, y=display,
                    size=5, pen=pg.mkPen(None),
                    brush=pg.mkBrush(rgba(color, 120)),
                )
                pw.addItem(scatter)
        else:
            jitter = rng.uniform(-_JITTER_HALF, _JITTER_HALF, size=len(values))
            scatter = pg.ScatterPlotItem(
                x=np.zeros(len(values)) + jitter, y=values,
                size=5, pen=pg.mkPen(None),
                brush=pg.mkBrush(100, 100, 100, 100),
            )
            pw.addItem(scatter)

    def _draw_median_line(self, pw: pg.PlotWidget, median: float, x_positions: list[int]) -> None:
        """Solid horizontal red line at the pool median, spanning all positions."""
        x_lo = min(x_positions) - 0.5
        x_hi = max(x_positions) + 0.5
        line = pg.PlotCurveItem(
            x=[x_lo, x_hi], y=[median, median],
            pen=pg.mkPen('r', width=2.5),
        )
        pw.addItem(line)

    def _draw_replica_medians(
        self,
        pw: pg.PlotWidget,
        replica_samples: List[Dict[str, np.ndarray]],
        key: str,
        palette: list,
        use_log: bool,
        x_positions: list[int],
    ) -> None:
        """Diamond markers at each replica's median value, at that replica's x."""
        for r_idx, r_samp in enumerate(replica_samples):
            r_vals = r_samp.get(key)
            if r_vals is None or len(r_vals) == 0:
                continue
            med = float(np.median(np.log10(r_vals) if use_log else r_vals))
            x_pos = x_positions[r_idx] if r_idx < len(x_positions) else r_idx
            color = palette[r_idx % len(palette)]
            marker = pg.ScatterPlotItem(
                x=[float(x_pos)], y=[med],
                symbol='d', size=10,
                pen=pg.mkPen(FOREGROUND_COLOR, width=1),
                brush=pg.mkBrush(rgba(color, 220)),
            )
            pw.addItem(marker)

    def _add_legend(self, pw: pg.PlotWidget, has_replicas: bool) -> None:
        """Add a legend to the first subplot explaining visual elements."""
        legend = pw.addLegend(offset=(10, 10))
        legend.setLabelTextSize('10pt')

        median_item = pg.PlotCurveItem(pen=pg.mkPen('r', width=2.5))
        legend.addItem(median_item, 'Pool median')

        if has_replicas:
            diamond_item = pg.ScatterPlotItem(
                symbol='d', size=10,
                pen=pg.mkPen(FOREGROUND_COLOR, width=1),
                brush=pg.mkBrush(150, 150, 150, 220),
            )
            legend.addItem(diamond_item, 'Replica median')

    def _apply_axis_style(self, pw: pg.PlotWidget) -> None:
        """Match fonts and axis styling to the main curve plot."""
        label_size = self._style['axes'].get('label_font_size', 18)
        tick_size = self._style['axes'].get('tick_font_size', 16)

        label_font = QFont()
        label_font.setPointSize(label_size)
        tick_font = QFont()
        tick_font.setPointSize(tick_size)

        for axis_name in ('left', 'bottom'):
            axis = pw.getPlotItem().getAxis(axis_name)
            axis.label.setFont(label_font)
            axis.setTickFont(tick_font)
            axis.setPen(pg.mkPen(FOREGROUND_COLOR, width=1))
            axis.setTextPen(pg.mkPen(FOREGROUND_COLOR))

        title_font = QFont()
        title_font.setPointSize(label_size)
        title_font.setBold(True)
        pw.getPlotItem().titleLabel.item.setFont(title_font)

    def _extract_replica_samples(
        self, result: FitResult,
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
