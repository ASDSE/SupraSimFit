"""Box-whisker and histogram distribution plots for fitted parameters (pyqtgraph)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Dict, List, Optional, Tuple

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QSpinBox,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.pipeline.fit_pipeline import FitResult, fit_replica_ids, input_replica_ids
from gui.plotting.colors import (
    BACKGROUND_COLOR,
    FOREGROUND_COLOR,
    INK_2,
    PALETTES,
    REPLICA_PALETTE,
    SERIES,
    rgba,
)
from gui.plotting.labels import fmt_param, fmt_param_plain, fmt_unit_html
from gui.plotting.plot_style import DEFAULT_STYLE
from gui.plotting.plot_widget import ScientificAxisItem, _format_exponent_unicode
from gui.widgets.replica_panel import _display_label, describe_replicates

_BOX_HALF = 0.3
_CAP_HALF = 0.2
_JITTER_HALF = 0.25

_MIN_BINS = 5
_MAX_BINS = 200
_BAR_GAP_PX = 2
_MIN_BAR_PX = 3
_FLAT_BAR_PX = 8

# Fit-quality metrics shown as extra distribution subplots.
# key -> (title, uses_signal_unit): RMSE carries the assay's signal (y) unit,
# sourced from the registry at render time; R² is dimensionless.
_QUALITY_METRICS = {'rmse': ('RMSE', True), 'r_squared': ('R²', False)}

#: Subplots that start hidden, until the user ticks one on.
_HIDDEN_BY_DEFAULT = frozenset({'rmse'})

# Fallback per-cell logical pixel size when the live widget hasn't
# been shown yet (e.g. headless tests, dialog opened before the
# distributions tab was visible). The export then renders at this
# default; the user can resize the live widget and re-export to get
# different proportions.
_FALLBACK_CELL_W = 320
_FALLBACK_CELL_H = 380


def _log10_positive(values: np.ndarray) -> np.ndarray:
    """``log10`` of a strictly-positive pool, matching ``ensemble.describe_log10``.

    A log-scale parameter (Ka) is bounded > 0; a non-positive sample is a real
    defect, so raise rather than emit a silent ``-inf``/``nan`` point that would
    show as a gap in the distribution plot (the summary table's ``describe_log10``
    already raises on the same condition — keep the two consistent).
    """
    arr = np.asarray(values, dtype=float)
    if arr.size and np.min(arr) <= 0:
        raise ValueError(
            'This fit holds a value of zero or below, which cannot be shown on a log₁₀ scale. '
            'Set Plot Style ▸ Distribution ▸ Ka scale to linear, or run the fit again with bounds above zero.'
        )
    return np.log10(arr)


def _default_bins(pool_size: int) -> int:
    """Square-root rule for the histogram bin count, clamped to the Bins control's range."""
    return int(np.clip(round(np.sqrt(pool_size)), _MIN_BINS, _MAX_BINS))


def robust_range(values: np.ndarray) -> tuple[float, float]:
    """The range the bulk of *values* occupies: the Tukey fences, kept inside the data.

    A few fits far from the rest would otherwise set the whole range and press
    the rest into one or two bars. The fences are the quartiles widened by 1.5
    inter-quartile ranges, which for a normal pool keeps about 99 in 100 values.
    A pool whose middle half is a single value has no such scale, so its full
    range is returned.

    Parameters
    ----------
    values : numpy.ndarray
        The pool to range, as it is drawn (already on the log scale where one is used).

    Returns
    -------
    tuple[float, float]
        Lowest and highest value of the range to bin over.
    """
    lo, hi = float(np.min(values)), float(np.max(values))
    q1, q3 = (float(v) for v in np.percentile(values, [25, 75]))
    iqr = q3 - q1
    if iqr <= 0:
        return lo, hi
    return max(lo, q1 - 1.5 * iqr), min(hi, q3 + 1.5 * iqr)


def _outside_note(values: np.ndarray, lo: float, hi: float) -> str:
    """How many of *values* fall outside ``lo``–``hi``, on which side, and how far out.

    A count alone cannot be read: a handful of stragglers just past the edge and
    a second cluster of fits a hundredfold away — the multi-start outcome this
    tab exists to expose — look the same. Naming the farthest value says which
    it is, and where the box view of the same pool will show them.
    """
    parts = []
    for group, side, edge, farthest in (
        (values[values < lo], 'below', lo, np.min),
        (values[values > hi], 'above', hi, np.max),
    ):
        if group.size:
            fits = 'fit' if group.size == 1 else 'fits'
            parts.append(f'{group.size} {fits} {side} {edge:.4g}, out to {float(farthest(group)):.4g}')
    return '; '.join(parts)


def _count_tick_step(span: float) -> int:
    """Smallest 1-2-5 step that puts at most three labelled ticks on a count axis spanning *span*.

    Distribution subplots can be as narrow as 170 px, so the count axis keeps
    its labels sparse and integer.
    """
    target = max(span / 3, 1.0)
    magnitude = 10 ** int(np.floor(np.log10(target)))
    return next(m * magnitude for m in (1, 2, 5, 10) if m * magnitude >= target)


def draw_histogram(
    plot_item: pg.PlotItem,
    values: np.ndarray,
    bins: int,
    *,
    color: str,
    gap_color: str,
    horizontal: bool,
    value_range: tuple[float, float] | None = None,
) -> int:
    """Draw a histogram of *values* in *bins* bins on *plot_item* and return its tallest count.

    The bins span *value_range* when it is given, and the full spread of *values*
    otherwise; a value outside the range is left out of every bin, so the caller
    says how many fell outside.

    Bars grow from a count of zero, to the right when *horizontal* and upwards
    otherwise; the caller starts the count axis exactly at zero. Neighbouring
    bars touch, split by a ``_BAR_GAP_PX`` line in *gap_color* along each inner
    bin edge, so the gap never shortens a bar. Every non-empty bin is drawn at
    least ``_MIN_BAR_PX`` long, so a bin holding one value stays visible however
    many the tallest bin holds: that stroke is centred on the zero line, and the
    plot clips the half below it. Values that are all equal have no spread to
    bin, so they are drawn as one bar ``_FLAT_BAR_PX`` thick at that value.
    """
    values = np.asarray(values, dtype=float)

    def lines(count_pairs, value_pairs, width: float, pen_color: str) -> None:
        # One straight line per (start, end) pair; the pen width is in pixels.
        counts_xy, values_xy = np.ravel(count_pairs), np.ravel(value_pairs)
        x, y = (counts_xy, values_xy) if horizontal else (values_xy, counts_xy)
        pen = pg.mkPen(pen_color, width=width)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        plot_item.addItem(pg.PlotCurveItem(x=x, y=y, pen=pen, connect='pairs'))

    if np.ptp(values) == 0:
        lines([0, values.size], [values[0], values[0]], _FLAT_BAR_PX, color)
        return int(values.size)

    counts, edges = np.histogram(values, bins=bins, range=value_range)
    lo, hi = edges[:-1], edges[1:]
    zeros = np.zeros(len(counts))
    if horizontal:
        bars = pg.BarGraphItem(x0=zeros, y0=lo, width=counts, height=hi - lo)
    else:
        bars = pg.BarGraphItem(x0=lo, y0=zeros, width=hi - lo, height=counts)
    bars.setOpts(brush=pg.mkBrush(color), pen=pg.mkPen(None))
    plot_item.addItem(bars)

    filled = counts > 0
    lines(np.zeros((filled.sum(), 2)), np.column_stack([lo[filled], hi[filled]]), 2 * _MIN_BAR_PX, color)
    tallest = int(counts.max())
    inner = edges[1:-1]
    lines(np.tile([0, tallest], (inner.size, 1)), np.column_stack([inner, inner]), _BAR_GAP_PX, gap_color)
    return tallest


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
    """Side-by-side box-whisker plots or histograms of fitted parameter distributions.

    One pyqtgraph subplot per parameter, arranged horizontally. A control row
    above the plots switches every subplot between the box view (default) and
    the histogram view, and sets one bin count shared by every histogram.

    **Per-replica mode**: one box-whisker per replicate the fit used, labelled
    and coloured by the replicate's position in the loaded data (A, B, C, …),
    as on the Fit Curve and in the Replicates panel.  A red pooled-median line
    spans all positions.

    **Average mode**: x-axis labeled "Pool of Fits" with no tick marks.
    One box-whisker at x=0 for the single optimizer pool.

    **Histogram view**: the value axis stays vertical, as in the box view, and
    bars grow to the right with the number of fits per bin. Each histogram is of
    the pooled values the box view summarises, with the pool-median line. Its
    legend sits on a line under the controls, which in per-replica mode also
    says the replicates are pooled.

    While :meth:`show_mismatch` hides the fit, a note takes the place of the
    plots.

    Two extra subplots show the **RMSE** and **R²** distributions across the
    valid fits. In the box view a gold ring marks the current representative in
    every subplot; clicking any point (parameter or quality) reports that fit as
    the representative (emits :attr:`representative_selected`). Each subplot can
    be shown/hidden via the checkbox row beneath the plots, in either view.

    Signals
    -------
    representative_selected(int)
        Emitted with a pool index when the user clicks a fit-quality point.
    """

    representative_selected = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setToolTip(
            '<qt>Distribution of each parameter and of fit quality (RMSE, R²) '
            'across all valid fits, as box plots or histograms.<br>In the box plot '
            'view, click any point to report that fit as the representative; the gold '
            'ring marks the current one.<br>Show or hide each plot with the '
            'checkboxes below.</qt>'
        )
        self._style: dict = dict(DEFAULT_STYLE)
        self._plots: list[pg.PlotWidget] = []
        self._result: FitResult | None = None
        # The loaded data's replicate order, which gives each replicate its label and colour.
        self._replica_ids: tuple[str, ...] | None = None
        # Set by show_mismatch(): while not None the fit is hidden and this note says why.
        self._mismatch_note: str | None = None
        # Set while the fit on hand cannot be drawn: the sentence saying why.
        self._problem: str | None = None
        self._param_keys: list[str] = []
        # Visibility toggles (issue 7): ordered keys = param keys then quality keys.
        self._all_keys: list[str] = []
        # RMSE starts hidden: it is monotone in R², which is already shown, so it
        # adds a panel without adding information. Re-enable via its checkbox.
        self._hidden_keys: set[str] = set(_HIDDEN_BY_DEFAULT)
        # Keys the user ticked on, which stay shown through a result that lacks them.
        self._shown_by_user: set[str] = set()
        self._plot_by_key: dict[str, pg.PlotWidget] = {}
        self._checkboxes: dict[str, QCheckBox] = {}
        self._histogram = False
        # The user's bin count; while None, the Bins control follows each result's pool size.
        self._bins: int | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        # View controls above the plots: box plot | histogram, and the shared bin count.
        self._view_bar_host = QWidget()
        view_rows = QVBoxLayout(self._view_bar_host)
        view_rows.setContentsMargins(4, 0, 4, 0)
        view_rows.setSpacing(2)
        view_bar = QHBoxLayout()
        view_bar.setSpacing(10)
        view_rows.addLayout(view_bar)
        view_bar.addWidget(QLabel('Show as:'))
        self._box_radio = QRadioButton('Box plot')
        self._box_radio.setChecked(True)
        self._hist_radio = QRadioButton('Histogram')
        view_group = QButtonGroup(self)
        view_group.addButton(self._box_radio)
        view_group.addButton(self._hist_radio)
        self._hist_radio.toggled.connect(self._on_view_toggled)
        view_bar.addWidget(self._box_radio)
        view_bar.addWidget(self._hist_radio)
        view_bar.addSpacing(16)
        self._bins_label = QLabel('Bins:')
        self._bins_spin = QSpinBox()
        self._bins_spin.setRange(_MIN_BINS, _MAX_BINS)
        self._bins_spin.setKeyboardTracking(False)
        self._bins_spin.setToolTip('Number of bars in every histogram.')
        self._bins_spin.valueChanged.connect(self._on_bins_changed)
        view_bar.addWidget(self._bins_label)
        view_bar.addWidget(self._bins_spin)
        view_bar.addStretch(1)
        # Histogram legend: a wrapping line under the controls, so it never
        # covers bars, clips in a narrow subplot, or sets the widget's minimum width.
        self._hist_note = QLabel()
        self._hist_note.setTextFormat(Qt.TextFormat.RichText)
        self._hist_note.setWordWrap(True)
        self._hist_note.setStyleSheet(f'color: {INK_2};')
        view_rows.addWidget(self._hist_note)
        self._set_bins_enabled(False)
        self._view_bar_host.setVisible(False)
        outer.addWidget(self._view_bar_host)

        self._stack_host = QWidget()
        self._stack = QStackedLayout(self._stack_host)

        self._placeholder = QLabel('Run a fit to see parameter and fit-quality distributions.')
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet('color: rgba(0,0,0,0.35); font-size: 14px;')
        self._stack.addWidget(self._placeholder)

        self._plot_container = QWidget()
        self._plot_layout = QHBoxLayout(self._plot_container)
        self._plot_layout.setContentsMargins(0, 0, 0, 0)
        self._plot_layout.setSpacing(4)
        # Trailing stretch absorbs leftover width so a few plots left-align at
        # their max width instead of over-stretching across the whole pane.
        self._plot_layout.addStretch(1)
        self._stack.addWidget(self._plot_container)

        self._all_hidden = QLabel('All distributions hidden — re-enable a checkbox below.')
        self._all_hidden.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._all_hidden.setStyleSheet('color: rgba(0,0,0,0.35); font-size: 14px;')
        self._stack.addWidget(self._all_hidden)

        self._mismatch_label = QLabel()
        self._mismatch_label.setTextFormat(Qt.TextFormat.PlainText)
        self._mismatch_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mismatch_label.setWordWrap(True)
        self._mismatch_label.setStyleSheet(f'color: {INK_2}; font-size: 14px; padding: 16px;')
        self._stack.addWidget(self._mismatch_label)

        # Shown in place of the plots when the fit on hand cannot be drawn.
        self._problem_label = QLabel()
        self._problem_label.setTextFormat(Qt.TextFormat.PlainText)
        self._problem_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._problem_label.setWordWrap(True)
        self._problem_label.setStyleSheet('color: #b42318; font-size: 14px; padding: 16px;')
        self._stack.addWidget(self._problem_label)

        self._stack.setCurrentWidget(self._placeholder)
        outer.addWidget(self._stack_host, stretch=1)

        # Row of show/hide checkboxes beneath the plots (issue 7).
        self._toggle_bar_host = QWidget()
        self._toggle_bar = QHBoxLayout(self._toggle_bar_host)
        self._toggle_bar.setContentsMargins(4, 0, 4, 0)
        self._toggle_bar.setSpacing(10)
        self._toggle_bar_host.setVisible(False)
        outer.addWidget(self._toggle_bar_host)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_result(self, result: FitResult, replica_ids: Sequence[str] | None = None) -> None:
        """Redraw all subplots from a FitResult's parameter_samples.

        One subplot per parameter, then RMSE and R² fit-quality subplots
        (when ``quality_samples`` is present). Only the parameter subplots are
        reported by :meth:`param_keys` / exported; the quality subplots are a
        live, clickable diagnostic for picking a representative fit.

        Parameters
        ----------
        result : FitResult
            The fit to show.
        replica_ids : sequence of str, optional
            The loaded data's replicate ids in order
            (``MeasurementSet.replica_ids``). A per-replicate fit's boxes take
            the display label and colour of each replicate's position here.
            Without it (no data loaded) they are labelled by the replicate ids
            the fit records.
        """
        self._result = result
        self._replica_ids = None if replica_ids is None else tuple(replica_ids)
        self._render()

    def show_mismatch(self, note: str | None) -> None:
        """Show *note* in place of the plots while the fit does not match the loaded data; ``None`` shows them again.

        The note stays through later :meth:`update_result`, style and view
        changes, so a hidden fit's distributions are never shown by accident;
        :meth:`clear` removes it together with the result. The plots are kept
        while hidden, so ``None`` shows them exactly as they were.

        Parameters
        ----------
        note : str or None
            Short plain text naming what differs from the fit's record, or
            ``None`` when the fit matches the loaded data.
        """
        self._mismatch_note = note
        self._mismatch_label.setText(note or '')
        self._update_stack_page()

    def _render(self) -> None:
        """Draw every subplot from the stored result, or say why it cannot be drawn.

        The fit on hand can be one the plots cannot show — a per-replicate fit
        without its replicate record, a log-scale value at or below zero. Rendering
        runs from Qt slots, so the reason is shown in place of the plots rather than
        left to the console.
        """
        self._problem = None
        try:
            self._draw()
        except ValueError as problem:
            self._problem = str(problem)
            self._problem_label.setText(self._problem)
            self._update_stack_page()

    def _draw(self) -> None:
        """Draw every subplot from the stored result."""
        result = self._result
        if result is None:
            return

        if result.parameter_samples is None or not result.parameters:
            self._param_keys = []
            self._all_keys = []
            self._update_stack_page()
            return

        param_keys = list(result.parameter_samples.keys())
        self._param_keys = list(param_keys)

        if self._bins is None:
            self._bins_spin.blockSignals(True)
            self._bins_spin.setValue(_default_bins(len(result.parameter_samples[param_keys[0]])))
            self._bins_spin.blockSignals(False)
        self._update_hist_note(pooled_replicas=self._replicate_pools(result) is not None)

        quality_keys = []
        if result.quality_samples:
            quality_keys = [k for k in ('rmse', 'r_squared') if k in result.quality_samples]

        all_keys = param_keys + quality_keys
        self._all_keys = all_keys

        self._rebuild_subplots(len(all_keys))
        self._plot_by_key = {}

        for i, key in enumerate(param_keys):
            pw = self._plots[i]
            plot_item = pw.getPlotItem()
            self._clear_subplot(plot_item)
            self._populate_subplot(plot_item, key=key, param_idx=i, add_legend=(i == 0))
            self._plot_by_key[key] = pw

        for j, metric_key in enumerate(quality_keys):
            pw = self._plots[len(param_keys) + j]
            plot_item = pw.getPlotItem()
            self._clear_subplot(plot_item)
            self._populate_quality_subplot(plot_item, metric_key=metric_key)
            self._plot_by_key[metric_key] = pw

        # Drop stale hidden keys (e.g. assay switch) so a new key-set is all-visible,
        # keeping the default-hidden keys hidden until the user ticks them on, then
        # apply visibility and rebuild the toggle bar.
        self._hidden_keys = (self._hidden_keys & set(all_keys)) | (_HIDDEN_BY_DEFAULT - self._shown_by_user)
        for key, pw in self._plot_by_key.items():
            pw.setVisible(key not in self._hidden_keys)
        self._sync_toggle_bar(all_keys)
        self._update_stack_page()

    # ------------------------------------------------------------------
    # Visibility toggles (issue 7)
    # ------------------------------------------------------------------

    def _checkbox_label(self, key: str) -> str:
        """Plain-text label for a subplot's toggle checkbox."""
        if key in _QUALITY_METRICS:
            return _QUALITY_METRICS[key][0]
        return fmt_param_plain(key)

    def _sync_toggle_bar(self, keys: list[str]) -> None:
        """Rebuild the checkbox row when the key-set changes; else reflect state."""
        if list(self._checkboxes.keys()) != list(keys):
            while self._toggle_bar.count():
                item = self._toggle_bar.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.deleteLater()
            self._checkboxes = {}
            self._toggle_bar.addWidget(QLabel('Show:'))
            for key in keys:
                cb = QCheckBox(self._checkbox_label(key))
                cb.setChecked(key not in self._hidden_keys)
                cb.toggled.connect(lambda on, k=key: self._on_toggle(k, on))
                self._toggle_bar.addWidget(cb)
                self._checkboxes[key] = cb
            self._toggle_bar.addStretch(1)
        else:
            for key, cb in self._checkboxes.items():
                cb.blockSignals(True)
                cb.setChecked(key not in self._hidden_keys)
                cb.blockSignals(False)

    def _on_toggle(self, key: str, checked: bool) -> None:
        """Show/hide one subplot without re-rendering (no jitter/stat recompute)."""
        if checked:
            self._hidden_keys.discard(key)
            self._shown_by_user.add(key)
        else:
            self._hidden_keys.add(key)
            self._shown_by_user.discard(key)
        pw = self._plot_by_key.get(key)
        if pw is not None:
            pw.setVisible(checked)
        self._update_stack_page()

    # ------------------------------------------------------------------
    # View controls
    # ------------------------------------------------------------------

    def _set_bins_enabled(self, enabled: bool) -> None:
        self._bins_label.setEnabled(enabled)
        self._bins_spin.setEnabled(enabled)

    def _update_hist_note(self, *, pooled_replicas: bool) -> None:
        """Show the histogram legend: the pool-median swatch, and the pooling note per replica."""
        self._hist_note.setVisible(self._histogram)
        r, g, b, *_ = self._style.get('distribution', {}).get('median_line_color', (220, 0, 0, 255))
        text = f'<span style="color: rgb({r}, {g}, {b}); font-weight: bold;">━━</span> Pool median'
        if pooled_replicas:
            text += ' &nbsp;·&nbsp; Each histogram pools the fits from all replicates.'
        self._hist_note.setText(text)

    def _on_view_toggled(self, histogram: bool) -> None:
        """Switch every subplot between the box view and the histogram view."""
        self._histogram = histogram
        self._set_bins_enabled(histogram)
        self._render()

    def _on_bins_changed(self, bins: int) -> None:
        """Apply the shared bin count to every histogram."""
        self._bins = bins
        if self._histogram:
            self._render()

    def _update_stack_page(self) -> None:
        """Pick the stacked page: the hidden-fit note, placeholder, all-hidden notice, or the plots.

        The view controls and the show/hide checkboxes appear only with the plots they act on.
        """
        has_plots = self._result is not None and bool(self._all_keys)
        hidden_fit = self._mismatch_note is not None
        usable = has_plots and not hidden_fit and self._problem is None
        self._view_bar_host.setVisible(usable)
        self._toggle_bar_host.setVisible(usable)
        if hidden_fit:
            self._stack.setCurrentWidget(self._mismatch_label)
        elif self._problem is not None:
            self._stack.setCurrentWidget(self._problem_label)
        elif not has_plots:
            self._stack.setCurrentWidget(self._placeholder)
        elif all(k in self._hidden_keys for k in self._all_keys):
            self._stack.setCurrentWidget(self._all_hidden)
        else:
            self._stack.setCurrentWidget(self._plot_container)

    def apply_style(self, style: dict) -> None:
        """Update visual style (fonts, palette) from PlotStyleWidget."""
        self._style = style
        self._render()

    def clear(self) -> None:
        """Reset to empty placeholder, removing any hidden-fit note."""
        self._result = None
        self._replica_ids = None
        self._mismatch_note = None
        self._problem = None
        self._param_keys = []
        self._all_keys = []
        for pw in self._plots:
            self._clear_subplot(pw.getPlotItem())
        self._update_stack_page()

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
            self._populate_subplot(plot_item, key=key, param_idx=key_idx, add_legend=(i == 0), interactive=False)

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
            raise ValueError(
                f"A plot is saved as a picture or a drawing, so '{format}' cannot be written. Use png or svg."
            )

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
            # Share width equally (large stretch beats the trailing stretch when
            # there is room to share) but cap each so few plots don't over-stretch.
            pw.setMinimumWidth(170)
            pw.setMaximumWidth(380)
            plot_item = pw.getPlotItem()
            plot_item.getViewBox().setDefaultPadding(0.05)
            plot_item.getAxis('bottom').enableAutoSIPrefix(False)

            _wire_exponent_callback(plot_item, left_axis)

            self._plots.append(pw)
            self._plot_layout.insertWidget(self._plot_layout.count() - 1, pw, 1000)

    def _populate_subplot(
        self,
        plot_item: pg.PlotItem,
        *,
        key: str,
        param_idx: int,
        add_legend: bool = False,
        interactive: bool = True,
    ) -> None:
        """Populate one PlotItem with the box-whisker or histogram distribution for *key*.

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

        pools = self._replicate_pools(result)
        replica_samples = [samples for _, samples in pools] if pools else None

        if replica_samples:
            x_positions = list(range(len(replica_samples)))
            x_tick_labels, colors = self._replicate_labels_and_colors(result, pools, palette)
            x_axis_label = 'Replicate'
        else:
            x_positions = [0]
            x_tick_labels, colors = [], []
            x_axis_label = 'Pool of Fits'

        pool = result.parameter_samples[key]
        use_log = (key in log_keys) and ka_scale == 'log₁₀'
        values = _log10_positive(pool) if use_log else pool

        if self._histogram:
            self._draw_histogram(plot_item, values)
        else:
            pool_stats = _box_stats(values)
            # Boxes: one per replica in per-replica mode, one pooled in average mode
            if replica_samples:
                for r_idx, r_samp in enumerate(replica_samples):
                    r_vals = r_samp.get(key)
                    if r_vals is None:
                        continue
                    r_display = _log10_positive(r_vals) if use_log else r_vals
                    r_stats = _box_stats(r_display)
                    self._draw_box(plot_item, r_stats, float(x_positions[r_idx]), colors[r_idx])
            else:
                self._draw_box(plot_item, pool_stats, 0.0)

            coords = self._draw_strip(
                plot_item,
                values,
                replica_samples,
                key,
                param_idx,
                colors,
                use_log,
                x_positions,
                interactive=interactive,
            )
            self._draw_median_line(plot_item, pool_stats['median'], min(x_positions) - 0.5, max(x_positions) + 0.5)

            if replica_samples:
                self._draw_replica_medians(plot_item, replica_samples, key, colors, use_log, x_positions)

            self._draw_selection_highlight(plot_item, coords)

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

        # Title — mirror the log-wrap so title + axis stay consistent
        title_size = self._style.get('distribution', {}).get('title_font_size', 16)
        title_text = f'log₁₀({label})' if use_log else label
        plot_item.setTitle(title_text, size=f'{title_size}pt', bold=True)

        self._apply_axis_style(plot_item)

        if not self._histogram:
            plot_item.getAxis('bottom').setTicks([[(pos, lbl) for pos, lbl in zip(x_positions, x_tick_labels)]])
            plot_item.setLabel('bottom', x_axis_label)
            x_pad = 0.8
            plot_item.setXRange(min(x_positions) - x_pad, max(x_positions) + x_pad, padding=0)
            plot_item.enableAutoRange(axis='y')

        if add_legend and not self._histogram:
            self._add_legend(plot_item, replica_samples is not None)

    def _populate_quality_subplot(self, plot_item: pg.PlotItem, *, metric_key: str) -> None:
        """Populate one subplot with the RMSE or R² distribution over the pool.

        The strip plot is clickable: clicking a point emits
        :attr:`representative_selected` with that fit's pool index.
        """
        result = self._result
        if result is None or result.quality_samples is None or metric_key not in result.quality_samples:
            return

        values = np.asarray(result.quality_samples[metric_key], dtype=float)
        if values.size == 0:
            return

        if self._histogram:
            self._draw_histogram(plot_item, values)
        else:
            stats = _box_stats(values)
            self._draw_box(plot_item, stats, 0.0)
            coords = self._draw_quality_strip(plot_item, values)
            self._draw_median_line(plot_item, stats['median'], -0.5, 0.5)
            self._draw_selection_highlight(plot_item, coords)

        # RMSE label unit = the assay's signal unit from the registry (the same
        # 'a.u.' string the main plot uses). Pass it plainly — Pint's HTML
        # formatter mis-parses the dotted 'a.u.' alias (renders 'u a').
        title, uses_signal_unit = _QUALITY_METRICS.get(metric_key, (metric_key, False))
        unit = ''
        if uses_signal_unit:
            assay_type = self._lookup_assay_type(result.assay_type)
            if assay_type is not None:
                unit = ASSAY_REGISTRY[assay_type].y_unit
        base_label = f'{title} [{unit}]' if unit else title
        plot_item._y_base_label = base_label
        left_axis = plot_item.getAxis('left')
        if hasattr(left_axis, 'exponent'):
            left_axis.exponent = None
        plot_item.setLabel('left', base_label)

        title_size = self._style.get('distribution', {}).get('title_font_size', 16)
        plot_item.setTitle(title, size=f'{title_size}pt', bold=True)

        self._apply_axis_style(plot_item)
        if not self._histogram:
            plot_item.getAxis('bottom').setTicks([[]])
            plot_item.setLabel('bottom', 'Pool of Fits')
            plot_item.setXRange(-0.8, 0.8, padding=0)
            plot_item.enableAutoRange(axis='y')

    def _draw_quality_strip(self, plot_item: pg.PlotItem, values: np.ndarray) -> dict[int, tuple[float, float]]:
        """Jittered, clickable strip — clicking a point selects that fit.

        Returns the pool-index → ``(x, y)`` coordinate map so the selection
        ring is drawn on the exact dot it points to.
        """
        rng = np.random.default_rng(7)
        n = values.size
        jitter = rng.uniform(-_JITTER_HALF, _JITTER_HALF, size=n)
        scatter = pg.ScatterPlotItem(
            x=jitter,
            y=values,
            size=7,
            pen=pg.mkPen(None),
            brush=pg.mkBrush(100, 100, 100, 130),
            data=list(range(n)),
        )
        scatter.setToolTip('Click a point to report that fit as the representative.')
        scatter.sigClicked.connect(self._on_point_clicked)
        plot_item.addItem(scatter)
        return {g: (float(jitter[g]), float(values[g])) for g in range(n)}

    def _on_point_clicked(self, _scatter, points, *_args) -> None:
        """Emit representative_selected with the front-most clicked fit's index.

        ``sigClicked`` hands us a NumPy array of ``SpotItem`` (front-most
        first). Use an explicit length check — ``if not points`` on an
        ndarray raises the ambiguous-truth ``ValueError``.
        """
        if len(points) == 0:
            return
        idx = points[0].data()
        if idx is None:
            return
        self.representative_selected.emit(int(idx))

    def _draw_selection_highlight(self, plot_item: pg.PlotItem, coords: dict[int, tuple[float, float]]) -> None:
        """Ring the current representative fit at its exact drawn coordinate.

        ``coords`` maps a pool index to the same ``(x, y)`` handed to that
        subplot's scatter, so the ring lands on the selected dot for free —
        correct across raw/log axes, per-replica columns, and jitter.
        """
        result = self._result
        if result is None or result.representative_index is None:
            return
        xy = coords.get(result.representative_index)
        if xy is None:
            return
        ring = pg.ScatterPlotItem(
            x=[xy[0]],
            y=[xy[1]],
            symbol='o',
            size=16,
            pen=pg.mkPen(255, 215, 0, 255, width=2.5),
            brush=None,
        )
        ring.setZValue(1000)  # above strips, boxes, and the median line
        plot_item.addItem(ring)

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
        colors: list,
        use_log: bool,
        x_positions: list[int],
        *,
        interactive: bool = True,
    ) -> dict[int, tuple[float, float]]:
        """Jittered strip plot with each replica at its own x position, in its colour from *colors*.

        Returns the pool-index → ``(x, y)`` coordinate map (the exact numbers
        handed to the scatter) so the selection ring lands on the right dot,
        correct across raw/log axes, per-replica columns, and jitter. Points
        carry their global pool index as ``data``; when *interactive*,
        clicking one reports that fit as the representative.
        """
        rng = np.random.default_rng(42 + param_idx)
        coords: dict[int, tuple[float, float]] = {}

        if replica_samples:
            offset = 0
            for r_idx, r_samp in enumerate(replica_samples):
                # Unlike the box/median loops, the strip cannot tolerate a
                # missing key by skipping: that would desync the pooled index
                # from the drawn points and misplace the selection ring. Fail
                # loudly with a clear message instead of a bare KeyError.
                r_vals = r_samp.get(key)
                if r_vals is None:
                    raise ValueError(
                        f'This fit records no {fmt_param_plain(key)} for one of its replicates, so its '
                        f'distributions cannot be drawn. Run the fit again on the loaded data.'
                    )
                display = _log10_positive(r_vals) if use_log else r_vals
                n = len(display)
                x_base = x_positions[r_idx] if r_idx < len(x_positions) else r_idx
                jitter = rng.uniform(-_JITTER_HALF, _JITTER_HALF, size=n)
                xs = np.full(n, x_base) + jitter
                gidx = list(range(offset, offset + n))
                for g, x, y in zip(gidx, xs, display):
                    coords[g] = (float(x), float(y))
                scatter = pg.ScatterPlotItem(
                    x=xs,
                    y=display,
                    size=5,
                    pen=pg.mkPen(None),
                    brush=pg.mkBrush(rgba(colors[r_idx], 120)),
                    data=gidx,
                )
                if interactive:
                    scatter.sigClicked.connect(self._on_point_clicked)
                plot_item.addItem(scatter)
                offset += n
            if offset != len(values):
                raise ValueError(
                    f'This fit records {offset} {fmt_param_plain(key)} values across its replicates but '
                    f'{len(values)} in its pool, so its distributions cannot be drawn. Run the fit again.'
                )
        else:
            n = len(values)
            jitter = rng.uniform(-_JITTER_HALF, _JITTER_HALF, size=n)
            xs = np.zeros(n) + jitter
            for g in range(n):
                coords[g] = (float(xs[g]), float(values[g]))
            scatter = pg.ScatterPlotItem(
                x=xs,
                y=values,
                size=5,
                pen=pg.mkPen(None),
                brush=pg.mkBrush(100, 100, 100, 100),
                data=list(range(n)),
            )
            if interactive:
                scatter.sigClicked.connect(self._on_point_clicked)
            plot_item.addItem(scatter)
        return coords

    def _draw_histogram(self, plot_item: pg.PlotItem, values: np.ndarray) -> None:
        """Histogram of *values* with the shared bin count, plus the pool-median line.

        The bins span :func:`robust_range`, so a few fits far from the rest cannot
        press the pool into one bar; a note in the corner says how many fits fall
        outside the range shown and how far out they lie, which the box view of
        the same pool draws in place. Bars run horizontally so the value axis
        stays vertical, as in the box view: the y-axis label, ×10ⁿ exponent and
        log₁₀ transform are shared by both views, the range shown is not. Sets the
        count axis (bottom) and both ranges. See :func:`draw_histogram` for how
        bars are drawn.
        """
        values = np.asarray(values, dtype=float)
        lo, hi = robust_range(values)
        outside = int(np.count_nonzero((values < lo) | (values > hi)))
        tallest = draw_histogram(
            plot_item,
            values,
            self._bins_spin.value(),
            color=SERIES,
            gap_color=BACKGROUND_COLOR,
            horizontal=True,
            value_range=(lo, hi),
        )
        x_hi = tallest * 1.08
        self._draw_median_line(plot_item, float(np.median(values)), 0.0, x_hi)

        step = _count_tick_step(x_hi)
        plot_item.getAxis('bottom').setTicks([[(v, str(v)) for v in range(step, int(x_hi) + 1, step)], []])
        plot_item.setLabel('bottom', 'Fits')
        plot_item.setXRange(0.0, x_hi, padding=0)
        if lo == hi:
            # One value: the same ±0.5 range around it that the box view shows.
            lo, hi = lo - 0.5, hi + 0.5
        plot_item.setYRange(lo, hi, padding=0.05)
        if outside:
            note = pg.TextItem(_outside_note(values, *robust_range(values)), color=INK_2, anchor=(1, 0))
            note.setPos(x_hi, hi)
            plot_item.addItem(note)

    def _draw_median_line(self, plot_item: pg.PlotItem, median: float, x_lo: float, x_hi: float) -> None:
        """Solid horizontal line at the pool median, spanning ``x_lo`` to ``x_hi``."""
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
        colors: list,
        use_log: bool,
        x_positions: list[int],
    ) -> None:
        """Diamond markers at each replica's median value, at that replica's x, in its colour from *colors*."""
        marker_size = self._style.get('distribution', {}).get('replica_median_size', 10)
        for r_idx, r_samp in enumerate(replica_samples):
            r_vals = r_samp.get(key)
            if r_vals is None or len(r_vals) == 0:
                continue
            med = float(np.median(_log10_positive(r_vals) if use_log else r_vals))
            x_pos = x_positions[r_idx] if r_idx < len(x_positions) else r_idx
            marker = pg.ScatterPlotItem(
                x=[float(x_pos)],
                y=[med],
                symbol='d',
                size=marker_size,
                pen=pg.mkPen(FOREGROUND_COLOR, width=1),
                brush=pg.mkBrush(rgba(colors[r_idx], 220)),
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
            legend.addItem(diamond_item, 'Replicate median')

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

    @staticmethod
    def _replicate_pools(result: FitResult) -> Optional[List[Tuple[str, Dict[str, np.ndarray]]]]:
        """Each replicate's accepted fits with that replicate's id, in pool order; None for a fit of the average.

        Raises
        ------
        ValueError
            If a per-replicate fit does not record which replicate each of its
            fits belongs to, so no box could be named truthfully.
        """
        if result.replica_fits is None:
            return None
        ids = fit_replica_ids(result)
        if ids is None or len(ids) != len(result.replica_fits):
            raise ValueError(
                'This per-replicate fit does not record which replicate each of its fits belongs to, '
                'so its distributions cannot be named. Run the fit again on the loaded data.'
            )
        pools = [
            (rid, rf.parameter_samples) for rid, rf in zip(ids, result.replica_fits) if rf.parameter_samples is not None
        ]
        return pools or None

    def _replicate_labels_and_colors(
        self, result: FitResult, pools: List[Tuple[str, Dict[str, np.ndarray]]], palette: list
    ) -> tuple[list[str], list[Tuple[int, int, int]]]:
        """Tick label and colour of each replicate in *pools*.

        With the loaded data's replicate order, each replicate is named and
        coloured by its position there, so a replicate reads the same on every
        tab whichever replicates are active. Without it, replicates are named
        by id and coloured by their position among the replicates the fit was
        given.
        """
        ids = [rid for rid, _ in pools]
        if self._replica_ids is not None:
            missing = [rid for rid in ids if rid not in self._replica_ids]
            if missing:
                raise ValueError(
                    f'The loaded data has no {describe_replicates(missing)}, which this fit used. '
                    f'Load the data the fit was run on, or run the fit again on this data.'
                )
            positions = [self._replica_ids.index(rid) for rid in ids]
            labels = [_display_label(position) for position in positions]
        else:
            given = input_replica_ids(result) or ids
            positions = [given.index(rid) for rid in ids]
            labels = list(ids)
        return labels, [palette[position % len(palette)] for position in positions]

    @staticmethod
    def _lookup_assay_type(name: str) -> Optional[AssayType]:
        try:
            return AssayType[name]
        except KeyError:
            return None
