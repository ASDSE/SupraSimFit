"""Ka input-sensitivity visualisation (pyqtgraph).

Renders the output of :func:`core.pipeline.sensitivity.run_sensitivity`:

- **SOBOL** — per Ka key, a Ka histogram over the sampled input space (titled
  with the median Ka and the fold range the middle 90 % of samples spans, with a
  marker line at the unperturbed baseline Ka) beside a grouped bar chart of the
  S₁ (first order) and S_T (total) Sobol indices of every varied input, each bar
  carrying its 95 % confidence interval as a whisker (a delete-one-block
  jackknife over the independent Sobol' sample blocks). The chart shows indices
  from -0.5 to 1.5; one beyond that is drawn to the edge and marked with an
  arrow. Below them, one "Ka vs input" panel per varied input plots every
  sample's best Ka against that input's offset. Each panel opens on the input's
  range as entered, or for a σ input symmetric about zero out to the farthest
  sampled offset.
- **HEATMAP** — an image per Ka key over the two swept input offsets,
  coloured by the statistic chosen above the maps: the Ka change from the
  baseline fit (the default, on a diverging scale symmetric in
  log₁₀(Ka / Ka_baseline), so halving and doubling sit equally far from zero,
  with ticks in percent), Ka itself (on the Plot Style's Ka scale) or R². Each
  map has a labelled colour bar and a hover crosshair naming the cell's two
  input offsets and reading out its Ka, Ka change and R²; cells where no fit
  could be produced are transparent.

A model with two binding constants gets one row of panels, and one map, per
constant: the widget draws whatever keys the run reports.

The fitted parameters across a SOBOL run's samples are tabled under the plot
tabs, by :class:`gui.plotting.fit_summary_widget.FitSummaryWidget`, while this
tab is the current one.

The page is a :class:`QStackedLayout` with a placeholder page, a progress page,
and a scrollable results page; ``apply_style`` stores the style dict and
re-renders (honouring ``style['distribution']['ka_scale']`` for the histogram's
Ka axis and the heatmap's Ka colours, and ``style['sensitivity']`` for the
baseline line).
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPalette
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.pipeline.sensitivity import (
    _SOBOL_BLOCKS,
    TITRANT,
    SensitivityMode,
    SensitivityResult,
    SpecKind,
    nominal_value,
    spec_bounds,
)
from gui.plotting.colors import INK, INK_2, INK_3, SERIES, SERIES_TOTAL, SURFACE
from gui.plotting.fit_summary_widget import unfitted_sentence
from gui.plotting.labels import fmt_param, fmt_r2, fmt_sci, fmt_unit_html, plain_label
from gui.plotting.plot_style import DEFAULT_STYLE
from gui.plotting.plot_widget import ScientificAxisItem, _format_exponent_unicode
from gui.widgets.assay_conditions import ASSAY_CONDITIONS

# Share of a "Ka vs input" panel's default Δ-input range left clear at each end,
# the same at every panel width, so the outermost dots sit off the axis line.
_OFFSET_VIEW_MARGIN = 0.03
# Grouped-bar geometry, in tick units: each series sits this far off the input's
# tick centre, and every bar spans twice this half-width.
_GROUP_OFFSET = 0.2
_BAR_HALF_WIDTH = 0.18
_MARKER_SIZE = 8
# Histogram bar geometry, in pixels: the line drawn along each inner bin edge to
# part neighbouring bars, the shortest stroke a non-empty bin gets so a bin
# holding one sample stays visible beside a tall one, and the width of the single
# bar drawn for samples that are all equal.
_BAR_GAP_PX = 2
_MIN_BAR_PX = 3
_FLAT_BAR_PX = 8
# Index range the bar chart shows. Sobol' indices lie between 0 and 1; estimates
# from few samples stray outside, and past these limits they are drawn to the
# edge with an arrow rather than stretching the axis until every bar is flat.
_INDEX_LIMITS = (-0.5, 1.5)
# Width, in pixels, the reason for an index panel with no bars in it wraps to.
# Narrower than the panel's own minimum width, so it stays clear of the axes.
_NO_INDEX_TEXT_WIDTH = 210
# Least clear space between neighbouring tick labels, in pixels.
_LABEL_GAP = 6
# Heatmap colour scales: diverging for a change about the baseline (lower blue,
# none grey, higher red), sequential in one hue from light to dark for a value.
_DIVERGING_CMAP = pg.ColorMap(pos=[0.0, 0.5, 1.0], color=[(42, 120, 214), (240, 239, 236), (227, 73, 72)])
_SEQUENTIAL_CMAP = pg.ColorMap(pos=[0.0, 0.5, 1.0], color=[(205, 226, 251), (42, 120, 214), (13, 54, 107)])
# Heatmap colour statistics: selector text, key, and the caption beside the selector.
_COLOUR_STATS = (
    ('Ka change', 'change', "Each cell's Ka compared with the Ka fitted to the inputs as you entered them."),
    ('Ka', 'ka', "Each cell's fitted Ka."),
    ('R²', 'r2', "How closely each cell's best fit follows the data."),
)
# On each side of zero, Ka-change ticks keep this share of the half-bar clear of
# zero and of each other.
_CHANGE_TICK_GAP = 0.2
# Smallest Ka ratio a percent Ka-change tick marks (−99.9 %); closer to −100 % a
# percent label stops telling ticks apart, so deeper ticks mark powers of ten and
# read as the ratio, ``×10⁻⁶``.
_MIN_CHANGE_TICK_RATIO = 1e-3
# Shown on the progress page until the first fit count arrives.
_RUNNING_TEXT = 'Running…'
#: What a stopping run says. The progress page and the status bar show it at the
#: same time, so they read as one message rather than two answers.
STOPPING_TEXT = 'Stopping — finishing the fits already running…'
# Most tick labels a heatmap axis carries; with more offsets than this it labels
# every second, third … one, so the labels stay apart.
_MAX_HEATMAP_TICKS = 9


def _wire_x_exponent(plot_item: pg.PlotItem, axis: ScientificAxisItem, base_label: str) -> None:
    """Re-apply *plot_item*'s x-label with a ``×10ⁿ`` suffix when *axis* factors one out.

    ``ScientificAxisItem`` fires ``on_exponent_changed`` on every deferred
    ``tickStrings`` pass; funnelling the label update through that callback is
    the only reliable way to append the exponent (reading ``axis.exponent``
    synchronously after a range change is a documented no-no).
    """
    plot_item.setLabel('bottom', base_label)

    def _on_exp(exp: Optional[int]) -> None:
        if exp is not None:
            plot_item.setLabel('bottom', f'{base_label}  (×10{_format_exponent_unicode(exp)})')
        else:
            plot_item.setLabel('bottom', base_label)

    axis.on_exponent_changed = _on_exp


def _draw_histogram(plot_item: pg.PlotItem, values: np.ndarray, bins: int) -> int:
    """Draw a histogram of *values* in *bins* bins on *plot_item* and return its tallest count.

    Bars grow upwards from a count of zero, which the caller starts the count
    axis at. Neighbouring bars touch, parted by a ``_BAR_GAP_PX`` line in the
    surface colour along each inner bin edge, so the gap never shortens a bar.
    Every non-empty bin is drawn at least ``_MIN_BAR_PX`` tall, so a bin holding
    one sample stays visible however many the tallest bin holds: that stroke is
    centred on the zero line, and the plot clips the half below it. Values that
    are all equal have no spread to bin, so they are drawn as one bar
    ``_FLAT_BAR_PX`` wide at that value.
    """
    values = np.asarray(values, dtype=float)

    def lines(counts, positions, width: float, pen_color: str) -> None:
        # One straight line per (start, end) pair; the pen width is in pixels.
        pen = pg.mkPen(pen_color, width=width)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        plot_item.addItem(pg.PlotCurveItem(x=np.ravel(positions), y=np.ravel(counts), pen=pen, connect='pairs'))

    if np.ptp(values) == 0:
        lines([0, values.size], [values[0], values[0]], _FLAT_BAR_PX, SERIES)
        return int(values.size)

    counts, edges = np.histogram(values, bins=bins)
    lo, hi = edges[:-1], edges[1:]
    bars = pg.BarGraphItem(x0=lo, y0=np.zeros(len(counts)), width=hi - lo, height=counts)
    bars.setOpts(brush=pg.mkBrush(SERIES), pen=pg.mkPen(None))
    plot_item.addItem(bars)

    filled = counts > 0
    lines(np.zeros((filled.sum(), 2)), np.column_stack([lo[filled], hi[filled]]), 2 * _MIN_BAR_PX, SERIES)
    tallest = int(counts.max())
    inner = edges[1:-1]
    lines(np.tile([0, tallest], (inner.size, 1)), np.column_stack([inner, inner]), _BAR_GAP_PX, SURFACE)
    return tallest


def _nice_steps(start: float):
    """Steps of 1, 2 and 5 times a power of ten, from the first one at or above *start* upwards."""
    magnitude = 10.0 ** np.floor(np.log10(start))
    while True:
        for m in (1, 2, 5):
            if m * magnitude >= start:
                yield m * magnitude
        magnitude *= 10.0


def _log_tick_candidates(lo: float, hi: float):
    """Tick sets for a log axis from ``10**lo`` to ``10**hi``, densest first, ending with one tick or none.

    Across a decade or more: 1, 2 and 5 times each power of ten, then every
    power, then every second, fifth, tenth … power. Below a decade: evenly
    spaced round values, each set a coarser step of 1, 2 or 5 times a power of
    ten, starting from about five ticks. Values are log10 of the tick positions.
    """
    if hi - lo >= 1.0:
        near = np.arange(np.floor(lo), np.ceil(hi) + 1)
        values = np.sort(np.concatenate([near + np.log10(m) for m in (1, 2, 5)]))
        yield values[(values >= lo) & (values <= hi)]
        decades = np.arange(np.ceil(lo), np.floor(hi) + 1)
        for step in _nice_steps(1.0):
            values = decades[np.mod(decades, step) == 0]
            yield values
            if values.size <= 1:
                return
    else:
        a, b = 10.0**lo, 10.0**hi
        for step in _nice_steps((b - a) / 6):
            values = np.log10(np.arange(np.ceil(a / step), np.floor(b / step) + 1) * step)
            yield values
            if values.size <= 1:
                return


class _LogKaAxis(pg.AxisItem):
    """Log-scaled Ka axis whose tick labels never overlap.

    pyqtgraph's log axis labels every multiple of each decade, so a few decades
    run the labels into each other, and a spread of less than a factor of two
    gets one label or none. This axis takes the densest tick set from
    :func:`_log_tick_candidates` whose labels, measured in the tick font, keep
    ``_LABEL_GAP`` pixels clear of their neighbours. Labels read ``2.5×10⁸``,
    the notation :func:`gui.plotting.labels.fmt_sci` uses across the app.
    """

    def logTickValues(self, minVal, maxVal, size, stdTicks):
        for values in _log_tick_candidates(minVal, maxVal):
            if self._labels_fit(values, minVal, maxVal, size):
                break
        return [(None, list(values))]

    def logTickStrings(self, values, scale, spacing):
        return [_tick_label(value) for value in 10.0 ** np.asarray(values, dtype=float) * scale]

    def _labels_fit(self, values: np.ndarray, lo: float, hi: float, size: float) -> bool:
        """Whether labels at *values* keep ``_LABEL_GAP`` pixels between neighbours on an axis *size* pixels long."""
        if len(values) <= 1 or hi <= lo:
            return True
        font = self.style['tickFont'] if self.style['tickFont'] is not None else self.font()
        metrics = QFontMetrics(font)
        strings = self.logTickStrings(values, 1.0, None)
        if self.orientation in ('top', 'bottom'):
            extents = np.array([metrics.horizontalAdvance(text) for text in strings], dtype=float)
        else:
            extents = np.full(len(strings), float(metrics.height()))
        centres = (np.asarray(values, dtype=float) - lo) / (hi - lo) * size
        return bool(np.all(np.diff(centres) - (extents[:-1] + extents[1:]) / 2 >= _LABEL_GAP))


def _end_label(value: float) -> str:
    """Tick label of a range end, to three significant figures: ``-6``, ``8.33``."""
    return f'{float(f"{value:.3g}"):g}'


class _OffsetAxis(pg.AxisItem):
    """Δ-input axis of a "Ka vs input" panel that always labels the ends of an entered range.

    The *ends* join the major ticks, labelled by :func:`_end_label`, and their
    labels may reach past the ends of the axis. A regular tick whose label would
    come within ``_LABEL_GAP`` pixels of an end's label is left out.
    """

    def __init__(self, ends: tuple[float, ...] = (), **kwargs):
        super().__init__('bottom', **kwargs)
        self._ends = tuple(float(end) for end in ends)

    def _metrics(self) -> QFontMetrics:
        return QFontMetrics(self.style['tickFont'] if self.style['tickFont'] is not None else self.font())

    def tickValues(self, minVal, maxVal, size):
        levels = super().tickValues(minVal, maxVal, size)
        ends = [end for end in self._ends if minVal <= end <= maxVal]
        if not ends or maxVal <= minVal:
            return levels
        metrics = self._metrics()
        per_unit = size / (maxVal - minVal)
        end_widths = [metrics.horizontalAdvance(_end_label(end)) for end in ends]
        kept_levels = []
        for i, (spacing, values) in enumerate(levels):
            texts = super().tickStrings(values, self.autoSIPrefixScale * self.scale, spacing)
            kept = [
                value
                for value, text in zip(values, texts)
                if all(
                    abs(value - end) * per_unit >= (metrics.horizontalAdvance(text) + width) / 2 + _LABEL_GAP
                    for end, width in zip(ends, end_widths)
                )
            ]
            kept_levels.append((spacing, sorted(kept + ends) if i == 0 else kept))
        return kept_levels

    def tickStrings(self, values, scale, spacing):
        texts = super().tickStrings(values, scale, spacing)
        return [_end_label(value) if value in self._ends else text for value, text in zip(values, texts)]

    def boundingRect(self):
        rect = super().boundingRect()
        if not self._ends:
            return rect
        metrics = self._metrics()
        overhang = max(metrics.horizontalAdvance(_end_label(end)) for end in self._ends) / 2
        return rect.adjusted(-overhang, 0, overhang, 0)


def _offset_view(result: SensitivityResult, key: str) -> tuple[float, float]:
    """The Δ-input range, in percent, that input *key*'s "Ka vs input" panel opens on.

    A range input opens on exactly the range entered; an absolute range is
    restated in percent of the value the analysis started from, which is how the
    samples are placed. A σ input has no edge, so it opens symmetric about zero
    out to the farthest sampled offset, which keeps every sample in view.
    """
    spec = result.config.input_specs[key]
    if spec.kind is SpecKind.INTERVAL:
        if spec.relative:
            return spec.lo, spec.hi
        lo, hi = spec_bounds(spec, nominal_value(key, result.baseline_fit.conditions), key)
        return 100.0 * lo, 100.0 * hi
    offsets = np.asarray(result.sample_offsets_pct[key], dtype=float)
    reach = float(np.max(np.abs(offsets[np.isfinite(offsets)]), initial=0.0))
    return -reach, reach


def _signed_pct(value: float, digits: int = 3) -> str:
    """*value* percent to *digits* significant figures, signed with a real minus: ``+12.3%``, ``−5%``, ``+1.20×10⁴%``."""
    if value == 0:
        return '0%'
    size = abs(value)
    text = fmt_sci(size, digits) if size >= 1e4 else f'{float(f"{size:.{digits}g}"):g}'
    return f'{"+" if value > 0 else "−"}{text}%'


def _exact_digits(value: float) -> int:
    """The fewest significant figures that state the round tick *value* exactly."""
    return next((d for d in range(1, 7) if np.isclose(float(f'{value:.{d}g}'), value, rtol=1e-9, atol=0)), 6)


def _tick_label(value: float) -> str:
    """The shortest :func:`fmt_sci` label that states the round tick *value* exactly."""
    return fmt_sci(value, _exact_digits(value))


def _linear_ticks(lo: float, hi: float) -> np.ndarray:
    """Round values from *lo* to *hi*, 1, 2 or 5 times a power of ten apart, three to seven of them."""
    step = next(_nice_steps((hi - lo) / 6))
    return np.arange(np.ceil(lo / step), np.floor(hi / step) + 1) * step


def _change_ticks(reach: float) -> list[tuple[float, str]]:
    """Ticks for a Ka-change colour bar spanning ``±reach`` in log₁₀(Ka / Ka_baseline), labelled in percent.

    Candidates are round changes: up by 1, 2 or 5 times a power of ten percent;
    down by the same to −50 %, then to ratios of 1, 2 or 5 times a power of ten
    (−80 %, −90 %, −95 %, …) down to ``_MIN_CHANGE_TICK_RATIO``, and below it to
    every power of ten, labelled as that ratio (``×10⁻⁶``). Each side takes them
    from the bar's end inwards, keeping ``_CHANGE_TICK_GAP`` of the half-bar
    clear of zero and of the ticks already kept.
    """
    ratios = []
    for m in _nice_steps(0.1):
        if np.log10(1 + m / 100) > reach:
            break
        ratios.append(1 + m / 100)
    for m in _nice_steps(0.1):
        if m > 50 or np.log10(1 - m / 100) < -reach:
            break
        ratios.append(1 - m / 100)
    for ratio in _nice_steps(max(10.0**-reach, _MIN_CHANGE_TICK_RATIO)):
        if ratio > 0.2:
            break
        ratios.append(ratio)
    deepest = int(np.floor(reach))
    ratios += [10.0**-n for n in range(round(-np.log10(_MIN_CHANGE_TICK_RATIO)) + 1, deepest + 1)]
    ticks = [(0.0, '0')]
    for side in (1.0, -1.0):
        kept: list[float] = []
        for ratio in sorted((r for r in ratios if np.sign(np.log10(r)) == side), key=lambda r: -abs(np.log10(r))):
            share = abs(np.log10(ratio)) / reach
            if share >= _CHANGE_TICK_GAP and all(abs(share - k) >= _CHANGE_TICK_GAP for k in kept):
                kept.append(share)
                pct = 100.0 * (ratio - 1.0)
                if ratio >= _MIN_CHANGE_TICK_RATIO:
                    label = _signed_pct(pct, _exact_digits(abs(pct)))
                else:
                    label = f'×10{_format_exponent_unicode(round(np.log10(ratio)))}'
                ticks.append((float(np.log10(ratio)), label))
    return sorted(ticks)


def _colour_scale(
    stat: str, ka: np.ndarray, r2: Optional[np.ndarray], baseline: float, use_log: bool
) -> tuple[np.ndarray, tuple[float, float], list[tuple[float, str]]]:
    """Per-cell colour values, their colour-bar range and its ticks for heatmap statistic *stat*.

    ``'change'`` colours log₁₀(Ka / *baseline*) on a range symmetric about zero,
    so halving and doubling sit equally far from it; ``'ka'`` colours Ka, as
    log₁₀(Ka) when *use_log*; ``'r2'`` colours R². Cells without a value are
    ``NaN``. Ticks are ``(position, label)`` pairs in colour-value units.
    """
    if stat == 'change':
        values = np.log10(ka / baseline)
    elif stat == 'ka':
        values = np.log10(ka) if use_log else ka
    else:
        values = np.asarray(r2, dtype=float)
    finite = values[np.isfinite(values)]
    if stat == 'change':
        reach = max(float(np.max(np.abs(finite), initial=0.0)), float(np.log10(1.001)))
        return values, (-reach, reach), _change_ticks(reach)
    lo, hi = (float(finite.min()), float(finite.max())) if finite.size else (0.0, 1.0)
    if hi <= lo:
        pad = 0.01 * abs(lo) or 1.0
        lo, hi = lo - pad, hi + pad
    if stat == 'ka' and use_log:
        positions = next(v for v in _log_tick_candidates(lo, hi) if len(v) <= 6)
        return values, (lo, hi), [(float(p), _tick_label(10.0**p)) for p in positions]
    return values, (lo, hi), [(float(p), _tick_label(p)) for p in _linear_ticks(lo, hi)]


def _cell_ticks(offsets: np.ndarray) -> list[tuple[float, str]]:
    """Ticks at the centres of a heatmap axis's cells, at most ``_MAX_HEATMAP_TICKS`` of them.

    With more cells than that, every second, third … one is labelled, at an even
    spacing across the axis.
    """
    values = np.asarray(offsets, dtype=float)
    if not values.size:
        return []
    step = max(1, int(np.ceil(values.size / _MAX_HEATMAP_TICKS)))
    return [(float(values[i]), _end_label(values[i])) for i in range(0, values.size, step)]


def _label_cells_in_view(plot, x_offsets: np.ndarray, y_offsets: np.ndarray) -> None:
    """Name the cell centres on *plot*'s axes, and keep them named as the view changes.

    A tick per cell reads the map's own steps, but the cells are fixed while the
    view is not: zoomed in past them, none may fall inside the view and the axis
    would carry no label at all. Whenever the view no longer holds the whole
    grid, pyqtgraph's own ticks take over.
    """
    axes = (('bottom', np.asarray(x_offsets, dtype=float)), ('left', np.asarray(y_offsets, dtype=float)))
    for name, offsets in axes:
        plot.getAxis(name).setTicks([_cell_ticks(offsets)])

    def on_range_changed(_view_box, ranges) -> None:
        for (name, offsets), (lo, hi) in zip(axes, ranges):
            whole_grid = offsets.size and lo <= offsets.min() and hi >= offsets.max()
            plot.getAxis(name).setTicks([_cell_ticks(offsets)] if whole_grid else None)

    plot.getViewBox().sigRangeChanged.connect(on_range_changed)


def _fitted_mask(kas) -> np.ndarray | None:
    """Which of the rows in *kas* — a run's Ka values per key — come from a fit; ``None`` when it holds none."""
    rows = [np.ravel(ka) for ka in kas]
    return np.all(np.isfinite(np.vstack(rows)), axis=0) if rows else None


def _quality_note(result: SensitivityResult) -> str:
    """The notes under the plots: what the run could not fit, and the seed that repeats it.

    Counts the samples with no fit and the design rows the indices leave out,
    then names the run's root seed.
    """
    if result.mode is SensitivityMode.HEATMAP:
        kas, noun = (result.ka_grid or {}).values(), 'grid cells'
    else:
        kas, noun = (result.sample_ka or {}).values(), 'samples'
    parts = []
    if _indices_off_scale(result):
        lo, hi = _INDEX_LIMITS
        parts.append(
            f'An arrow on the index chart marks an index or whisker beyond {lo:g} to {hi:g}: '
            'too few samples to pin it down. More samples bring it back in range.'
        )
    inverted = _total_below_first_order(result)
    if inverted is not None:
        parts.append(inverted)
    # The counts describe the fits there are, which after a cancelled or partly
    # failed run is fewer than the run planned, so they agree with Fit Quality.
    fitted = _fitted_mask(kas)
    if fitted is not None and not fitted.all():
        parts.append(unfitted_sentence(result, int((~fitted).sum()), fitted.size, noun))
    counts = result.sobol_rows_left_out or {}
    if len(set(counts.values())) == 1:
        counts = {None: next(iter(counts.values()))}
    for key, n in counts.items():
        if n:
            indices = 'The Sobol indices' if key is None else f'The Sobol indices for {plain_label(fmt_param(key))}'
            parts.append(
                f'{indices} leave out {n:,} of the {result.config.n_samples:,} sample groups set by the sample size: '
                f'at least one fit in {"that group" if n == 1 else "each of those groups"} '
                f'{"is missing" if result.stopped else "could not be made"}.'
            )
    # The seed is what repeats the run, so it belongs on the tab — and, through
    # the tab's picture, in what the user keeps of the analysis.
    parts.append(f'Seed {result.seed_used}: enter it under Fixed seed to repeat this analysis exactly.')
    return ' '.join(parts)


def _total_below_first_order(result: SensitivityResult) -> str | None:
    """The note for an input whose S_T bar is drawn below its own S_1 bar, or ``None``.

    A true total order is never below its first order, so the order of the bars
    comes from the estimates. It happens when the interaction share S_T − S_1 is
    near zero — whatever the size of the share itself — and then either estimate
    can come out on top in any run, at any sample size. Where the two intervals
    do not overlap, that is more than the whiskers account for, and the note says
    so instead.
    """
    inverted = separated = False
    for ka_key, s1 in (result.sobol_s1 or {}).items():
        st = (result.sobol_st or {}).get(ka_key, {})
        s1_ci = (result.sobol_s1_ci or {}).get(ka_key, {})
        st_ci = (result.sobol_st_ci or {}).get(ka_key, {})
        for key, first in s1.items():
            total = st.get(key, np.nan)
            if not (np.isfinite(first) and np.isfinite(total) and total < first):
                continue
            inverted = True
            first_lo = s1_ci.get(key, (first, first))[0]
            total_hi = st_ci.get(key, (total, total))[1]
            if np.isfinite(first_lo) and np.isfinite(total_hi) and total_hi < first_lo:
                separated = True
    if not inverted:
        return None
    bars = 'An input has its S<sub>T</sub> (total) bar drawn below its S<sub>1</sub> (first order) bar. '
    if separated:
        return bars + (
            'The gap is wider than the two whiskers span, which a total order below a first order cannot be: '
            "take that input's two indices as unreliable and run the analysis again at a larger sample size."
        )
    return bars + (
        'The two are equal to within their whiskers, which means the input acts almost entirely on its own — '
        'either estimate can come out on top in any run.'
    )


def _no_index_reason(result: SensitivityResult) -> str:
    """Why an index panel has no bars in it, and what to do about it.

    The indices need every fit of a sample group; a group missing one is left
    out, and with every group left out there is nothing to rank the inputs by.
    A run stopped before the first group finished is the common way there.

    Samples and sample groups are counted together here. A run can hold a fit
    for every sample these plots and Fit Quality count and still have no
    finished group, and the two counts read as contradicting each other unless
    they are given side by side.
    """
    groups = result.config.n_samples
    left_out = max((result.sobol_rows_left_out or {}).values(), default=groups)
    mask = _fitted_mask((result.sample_ka or {}).values())
    fitted = 0 if mask is None else int(mask.sum())
    counts = f'{groups - left_out:,} of {groups:,} sample groups finished'
    if fitted:
        counts += f', although {fitted:,} sample{"" if fitted == 1 else "s"} {"was" if fitted == 1 else "were"} fitted'
    if result.stopped:
        return (
            f'No index: {counts}. A group needs all of its fits, and the analysis was stopped before any group '
            'had them, so there is nothing yet to rank the inputs by. Run it again and let it finish, or set a '
            'smaller sample size.'
        )
    return (
        f'No index: {counts}. A group needs all of its fits, and none has them, so there is nothing to rank the '
        'inputs by. Narrow the uncertainties under Input Uncertainty, or widen the bounds under Parameter '
        'Bounds, and run it again.'
    )


def _indices_off_scale(result: SensitivityResult) -> bool:
    """Whether any Sobol' index or interval end lies beyond ``_INDEX_LIMITS``."""
    values = [
        value
        for by_ka in (result.sobol_s1, result.sobol_st, result.sobol_s1_ci, result.sobol_st_ci)
        for by_input in (by_ka or {}).values()
        for entry in by_input.values()
        for value in np.ravel(entry)
    ]
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    return bool(np.any((finite < _INDEX_LIMITS[0]) | (finite > _INDEX_LIMITS[1])))


class SensitivityWidget(QWidget):
    """Visualise a :class:`SensitivityResult` (Sobol analysis or a Ka heatmap).

    :meth:`update_result` dispatches on the result mode, :meth:`apply_style`
    restyles in place, :meth:`clear` resets to the placeholder, and
    :meth:`show_running` / :meth:`set_progress` drive the progress page during a
    run. :meth:`show_mismatch` hides the result behind a note while it no longer
    matches the loaded selection; the result is kept and drawn again once the
    note is removed. :meth:`export_image` saves the whole tab as a picture.

    While a run goes, the progress page counts the fits made and carries the
    Cancel button that stops it, so the count and the control sit where the
    user is looking. Pressing it emits :attr:`cancel_requested`.
    """

    #: Emitted when the user presses Cancel on the progress page.
    cancel_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setToolTip(
            '<qt>Spread of the fitted association constant when the input '
            'concentrations (and any known K<sub>a</sub>) are perturbed within '
            'the uncertainty you set.<br>Sobol indices rank each input by how much '
            'of that spread it explains; the heatmap maps Ka over two swept '
            'inputs.<br>Every sample is one exact fit of the averaged signal of the '
            'replicates the fit used, so the spread comes from the inputs alone.</qt>'
        )
        self._style: dict = dict(DEFAULT_STYLE)
        self._result: SensitivityResult | None = None
        self._mismatch: str | None = None
        # References kept alive for the heatmap hover handler.
        self._heatmap_glw: pg.GraphicsLayoutWidget | None = None
        self._hover_targets: list[dict] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        self._stack_host = QWidget()
        self._stack = QStackedLayout(self._stack_host)

        self._placeholder = QLabel(
            'Set how uncertain each input is under Input Uncertainty, then press Run Sensitivity Analysis.'
        )
        self._placeholder.setWordWrap(True)
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet('color: rgba(0,0,0,0.35); font-size: 14px;')
        self._stack.addWidget(self._placeholder)

        self._mismatch_label = QLabel()
        self._mismatch_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mismatch_label.setWordWrap(True)
        self._mismatch_label.setStyleSheet(f'color: {INK_2}; font-size: 14px; padding: 12px;')
        self._stack.addWidget(self._mismatch_label)

        self._stopping = False  # the run was asked to stop and the page says so
        self._progress_page = QWidget()
        prog_layout = QVBoxLayout(self._progress_page)
        prog_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prog_layout.setSpacing(10)
        self._progress_bar = QProgressBar()
        self._progress_bar.setMinimumWidth(240)
        self._progress_bar.setMaximumWidth(360)
        self._progress_bar.setTextVisible(False)
        self._progress_label = QLabel(_RUNNING_TEXT)
        self._progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._progress_label.setStyleSheet(f'color: {INK_2}; font-size: 13px;')
        self._cancel_button = QPushButton('Cancel')
        self._cancel_button.setToolTip('Stop the analysis. The fits made so far are shown.')
        self._cancel_button.clicked.connect(self._on_cancel_clicked)
        prog_layout.addWidget(self._progress_label)
        prog_layout.addWidget(self._progress_bar, alignment=Qt.AlignmentFlag.AlignCenter)
        prog_layout.addWidget(self._cancel_button, alignment=Qt.AlignmentFlag.AlignCenter)
        self._stack.addWidget(self._progress_page)

        # The results scroll: a Sobol run stacks several rows of panels, more
        # than a small plot tab holds at a readable size.
        self._results_host = QScrollArea()
        self._results_host.setWidgetResizable(True)
        self._results_host.setFrameShape(QFrame.Shape.NoFrame)
        results_inner = QWidget()
        palette = results_inner.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(SURFACE))
        results_inner.setPalette(palette)
        results_inner.setAutoFillBackground(True)
        self._results_layout = QVBoxLayout(results_inner)
        # The same inset the Identifiability page uses. Without it the rightmost
        # plot's frame — and the bar standing against it — ends on the last pixel
        # of the tab and of the picture saved from it.
        self._results_layout.setContentsMargins(10, 6, 10, 6)
        self._results_layout.setSpacing(4)
        self._results_host.setWidget(results_inner)
        self._stack.addWidget(self._results_host)

        self._note = QLabel()
        self._note.setTextFormat(Qt.TextFormat.RichText)
        self._note.setWordWrap(True)
        self._note.setStyleSheet(f'color: {INK_2}; font-size: 13px; padding: 2px 6px;')

        # Heatmap colour selector, above the maps; its choice holds across new results and restyles.
        self._colour_controls = QWidget()
        controls = QHBoxLayout(self._colour_controls)
        controls.setContentsMargins(6, 4, 6, 0)
        colour_label = QLabel('Colour by:')
        colour_label.setStyleSheet(f'color: {INK_2};')
        controls.addWidget(colour_label)
        self._colour_combo = QComboBox()
        for text, key, _ in _COLOUR_STATS:
            self._colour_combo.addItem(text, key)
        self._colour_combo.setToolTip('Choose what the colour of each map cell shows.')
        self._colour_combo.currentIndexChanged.connect(lambda _: self._render())
        controls.addWidget(self._colour_combo)
        self._colour_caption = QLabel()
        self._colour_caption.setStyleSheet(f'color: {INK_3}; font-size: 13px;')
        controls.addWidget(self._colour_caption, stretch=1)

        self._stack.setCurrentWidget(self._placeholder)
        outer.addWidget(self._stack_host, stretch=1)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_result(self, result: SensitivityResult) -> None:
        """Store *result* and render it (dispatch on ``result.mode``)."""
        self._result = result
        self._render()

    def apply_style(self, style: dict) -> None:
        """Adopt a new style dict and re-render the current result if any."""
        self._style = style
        if self._result is not None:
            self._render()

    def show_mismatch(self, note: str | None) -> None:
        """Hide the result behind *note*, or draw it again with ``None``; a run in progress keeps its page.

        An unchanged note leaves the page as it is.
        """
        if note == self._mismatch:
            return
        self._mismatch = note
        if self._stack.currentWidget() is not self._progress_page:
            self._render()

    def clear(self) -> None:
        """Reset to the empty placeholder page."""
        self._result = None
        self._clear_results()
        self._stack.setCurrentWidget(self._placeholder)

    def show_running(self) -> None:
        """Switch to the progress page (indeterminate until the first update)."""
        self._stopping = False
        self._progress_label.setText(_RUNNING_TEXT)
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setValue(0)
        self._cancel_button.setEnabled(True)
        self._stack.setCurrentWidget(self._progress_page)

    def _on_cancel_clicked(self) -> None:
        """Take the request on the page the user is looking at, then pass it on.

        The fits already running finish before the analysis returns, so the page
        says what it is waiting for instead of leaving the button live.
        """
        self._cancel_button.setEnabled(False)
        self._stopping = True
        self._progress_label.setText(STOPPING_TEXT)
        self.cancel_requested.emit()

    def set_progress(self, done: int, total: int) -> None:
        """Count *done* of *total* fits on the progress page and advance its bar."""
        if self._stopping:
            return  # the page says it is stopping; a rising count would read as progress
        if total > 0:
            self._progress_label.setText(f'{done:,} of {total:,} fits')
            self._progress_bar.setRange(0, total)
            self._progress_bar.setValue(done)
        else:
            self._progress_label.setText(_RUNNING_TEXT)
            self._progress_bar.setRange(0, 0)

    def export_image(self, path: str) -> None:
        """Save the tab's headings, plots, key and notes as a picture.

        The colour selector stays out of it: it chooses what a heatmap's colour
        shows, which each colour bar then names, and there is nothing to choose
        in a saved picture.

        Parameters
        ----------
        path : str
            Where to write it, ending in ``.png``. A whole tab is saved as one
            picture; :func:`~gui.plotting.export.export_widget` says why it is
            not offered as a drawing.

        Raises
        ------
        ValueError
            When there are no results on screen to save, or the suffix is not
            ``.png``.
        """
        from gui.plotting.export import export_widget

        if self._stack.currentWidget() is not self._results_host:
            raise ValueError('There is no sensitivity analysis to save yet. Run one, then save it.')
        export_widget(self._results_host.widget(), path, without=(self._colour_controls,))

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _clear_results(self) -> None:
        """Tear down the results page (plots + heatmap hover wiring); the note and selector are kept."""
        if self._heatmap_glw is not None:
            scene = self._heatmap_glw.scene()
            if scene is not None:
                try:
                    scene.sigMouseMoved.disconnect()
                except (TypeError, RuntimeError):
                    pass
        self._heatmap_glw = None
        self._hover_targets = []
        while self._results_layout.count():
            w = self._results_layout.takeAt(0).widget()
            if w is not None and not any(w is kept for kept in (self._note, self._colour_controls)):
                w.deleteLater()
        self._note.clear()
        self._colour_controls.hide()

    def _render(self) -> None:
        """Rebuild the results page from ``self._result``."""
        self._clear_results()
        result = self._result
        if result is None:
            self._stack.setCurrentWidget(self._placeholder)
            return
        if self._mismatch:
            self._mismatch_label.setText(self._mismatch)
            self._stack.setCurrentWidget(self._mismatch_label)
            return
        self._results_layout.addWidget(self._colour_controls)
        if result.mode is SensitivityMode.HEATMAP:
            self._colour_controls.show()
            self._render_heatmap(result)
        else:
            self._render_sobol(result)
        self._note.setText(_quality_note(result))
        self._note.setVisible(bool(self._note.text()))
        self._results_layout.addWidget(self._note)
        self._stack.setCurrentWidget(self._results_host)

    def _assay_type(self, result: SensitivityResult) -> Optional[AssayType]:
        try:
            return AssayType[result.assay_type]
        except KeyError:
            return None

    def _ka_unit_html(self, assay_type: Optional[AssayType], ka_key: str) -> str:
        """HTML unit for a Ka key (e.g. ``M⁻¹``), empty when unknown."""
        if assay_type is None:
            return ''
        return fmt_unit_html(ASSAY_REGISTRY[assay_type].units.get(ka_key, ''))

    def _input_label(self, assay_type: Optional[AssayType], key: str) -> str:
        """HTML display label for a perturbable input key.

        ``TITRANT`` → the assay's titrant species (registry ``x_label``); a
        condition key → its :class:`ConditionField` label; otherwise a
        parameter label (``fmt_param`` falls back to the raw key).
        """
        if key == TITRANT:
            return ASSAY_REGISTRY[assay_type].x_label if assay_type is not None else 'Titrant'
        if assay_type is not None:
            for field in ASSAY_CONDITIONS[assay_type]:
                if field.key == key:
                    return field.label
        return fmt_param(key)

    def _new_plot(self, min_width: int, min_height: int, **kwargs) -> tuple[pg.PlotWidget, pg.PlotItem]:
        """A plot on the chart surface with the given minimum size."""
        pw = pg.PlotWidget(background=SURFACE, **kwargs)
        pw.setMinimumSize(min_width, min_height)
        return pw, pw.getPlotItem()

    # ---- SOBOL ----------------------------------------------------------

    def _render_sobol(self, result: SensitivityResult) -> None:
        """Histogram + index bars per Ka key, then the Ka vs input panels."""
        assay_type = self._assay_type(result)
        use_log = self._style.get('distribution', {}).get('ka_scale', 'log₁₀') == 'log₁₀'
        samples_by_ka = {
            key: values[np.isfinite(values)]
            for key, values in ((k, np.asarray(v, dtype=float)) for k, v in (result.sample_ka or {}).items())
        }
        s1_by_ka = result.sobol_s1 or {}
        st_by_ka = result.sobol_st or {}
        input_keys: list[str] = []
        for per_input in (*s1_by_ka.values(), *st_by_ka.values()):
            for key in per_input:
                if key not in input_keys:
                    input_keys.append(key)

        top = QWidget()
        grid = QGridLayout(top)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        for r, ka_key in enumerate(result.ka_keys):
            hist = self._make_histogram(
                samples=samples_by_ka.get(ka_key),
                baseline=result.baseline_ka.get(ka_key),
                ka_key=ka_key,
                use_log=use_log,
                unit_html=self._ka_unit_html(assay_type, ka_key),
            )
            grid.addWidget(hist, r, 0)
            if input_keys:
                bars = self._make_index_bars(
                    ka_key=ka_key,
                    input_keys=input_keys,
                    s1=s1_by_ka.get(ka_key, {}),
                    st=st_by_ka.get(ka_key, {}),
                    s1_ci=(result.sobol_s1_ci or {}).get(ka_key, {}),
                    st_ci=(result.sobol_st_ci or {}).get(ka_key, {}),
                    assay_type=assay_type,
                    no_index_reason=_no_index_reason(result),
                )
                grid.addWidget(bars, r, 1)
        for c in range(grid.columnCount()):
            grid.setColumnStretch(c, 1)
        self._results_layout.addWidget(top)

        offsets_by_input = result.sample_offsets_pct or {}
        ka_by_key = result.sample_ka or {}
        if not offsets_by_input or not ka_by_key:
            return
        panels = QWidget()
        grid = QGridLayout(panels)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        for r, ka_key in enumerate(result.ka_keys):
            heading = QLabel(f'{fmt_param(ka_key)} vs each input')
            heading.setTextFormat(Qt.TextFormat.RichText)
            heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
            heading.setStyleSheet(f'color: {INK}; font-weight: bold; font-size: {self._title_size()}pt;')
            grid.addWidget(heading, 2 * r, 0, 1, len(offsets_by_input))
            first: pg.PlotWidget | None = None
            for c, input_key in enumerate(offsets_by_input):
                x_view = _offset_view(result, input_key)
                ranged = result.config.input_specs[input_key].kind is SpecKind.INTERVAL
                pw = self._make_ka_vs_input(
                    ka_key=ka_key,
                    input_label=self._input_label(assay_type, input_key),
                    offsets=np.asarray(offsets_by_input[input_key], dtype=float),
                    x_view=x_view,
                    range_ends=x_view if ranged else (),
                    ka=np.asarray(ka_by_key[ka_key], dtype=float),
                    unit_html=self._ka_unit_html(assay_type, ka_key),
                    show_y_label=c == 0,
                )
                if first is None:
                    first = pw
                else:
                    pw.setYLink(first)
                grid.addWidget(pw, 2 * r + 1, c)
                grid.setColumnStretch(c, 1)
        self._results_layout.addWidget(panels)

    def _make_histogram(
        self,
        *,
        samples: Optional[np.ndarray],
        baseline: Optional[float],
        ka_key: str,
        use_log: bool,
        unit_html: str,
    ) -> pg.PlotWidget:
        bottom_axis = ScientificAxisItem(orientation='bottom', use_exponent=not use_log)
        bottom_axis.enableAutoSIPrefix(False)
        pw, plot = self._new_plot(260, 220, axisItems={'bottom': bottom_axis})
        plot.getViewBox().setDefaultPadding(0.05)
        plot.showGrid(y=True, alpha=0.25)

        ka_label = fmt_param(ka_key)
        if use_log:
            x_base_label = f'log₁₀({ka_label})'
        else:
            x_base_label = f'{ka_label} [{unit_html}]' if unit_html else ka_label
        plot.setLabel('left', 'Count')
        _wire_x_exponent(plot, bottom_axis, x_base_label)

        arr = None if samples is None else np.asarray(samples, dtype=float)
        if arr is None or arr.size == 0:
            self._set_title(plot, f'{ka_label} — no fit could be produced')
            self._apply_axis_style(plot)
            return pw

        median = float(np.median(arr))
        p5, p95 = np.percentile(arr, [5, 95])

        positive = arr[arr > 0] if use_log else arr
        disp = np.log10(positive) if use_log else positive
        if disp.size:
            nbins = int(np.clip(round(np.sqrt(disp.size)), 10, 40))
            tallest = _draw_histogram(plot, disp, nbins)
            plot.setYRange(0.0, tallest * 1.08, padding=0)

        if baseline is not None and (not use_log or baseline > 0):
            base_x = float(np.log10(baseline)) if use_log else float(baseline)
            baseline_c = self._style.get('sensitivity', {}).get('baseline_line_color', (220, 0, 0, 255))
            baseline_w = self._style.get('sensitivity', {}).get('baseline_line_width', 2.5)
            line = pg.InfiniteLine(
                pos=base_x,
                angle=90,
                pen=pg.mkPen(baseline_c, width=baseline_w, style=Qt.PenStyle.DashLine),
                label='baseline',
                labelOpts={'position': 0.92, 'color': INK_2, 'fill': pg.mkBrush(SURFACE)},
            )
            plot.addItem(line)

        val_html = f'{fmt_sci(median, 3)} {unit_html}'.strip()
        spread = f' · middle 90% within {fmt_sci(p95 / p5)}-fold' if p5 > 0 else ''
        tick_size = self._style.get('distribution', {}).get('tick_font_size', 12)
        self._set_title(
            plot,
            f'{ka_label}<br><span style="font-weight: normal; font-size: {tick_size}pt; color: {INK_2};">'
            f'median {val_html}{spread}</span>',
        )
        self._apply_axis_style(plot)
        plot.enableAutoRange(axis='x')
        return pw

    def _make_index_bars(
        self,
        *,
        ka_key: str,
        input_keys: list[str],
        s1: dict[str, float],
        st: dict[str, float],
        s1_ci: dict[str, tuple[float, float]],
        st_ci: dict[str, tuple[float, float]],
        assay_type: Optional[AssayType],
        no_index_reason: str,
    ) -> pg.PlotWidget:
        """Build the paired S₁ (first order) / S_T (total) index panel for one Ka key.

        A bar is drawn only where the index is finite, with a whisker spanning
        its 95 % confidence interval where that interval is finite; an index
        that came back ``NaN`` — too few fits to estimate it — is marked
        ``n/a`` at its slot instead of being flattened to a zero bar. The
        y-range spans at least ``[0, 1]`` and widens to cover indices and
        intervals up to ``_INDEX_LIMITS``; a bar or whisker running past those
        is cut at the edge and marked with an arrow there. Where no index at all
        could be worked out, *no_index_reason* stands where the bars would be.
        """
        pw, plot = self._new_plot(260, 220)
        pw.setToolTip(
            'Each whisker is a 95% confidence interval. It is built so that in about 95 of every 100 '
            'analyses it contains the index you would get with unlimited samples for the uncertainties you '
            'set. A repeat run with fresh samples usually lands inside it, but not always. It is worked out '
            f'from {_SOBOL_BLOCKS} independent sample sets, and more samples narrow it. It does not account '
            'for errors in the input settings or in the model.'
        )
        self._set_title(plot, f'{fmt_param(ka_key)} — Sobol indices')
        plot.setLabel('left', 'Sensitivity index')
        plot.showGrid(y=True, alpha=0.25)

        tick_size = self._style.get('distribution', {}).get('tick_font_size', 12)
        legend = plot.addLegend(offset=(-10, 10), labelTextSize=f'{tick_size}pt', labelTextColor=INK)
        legend.setBrush(pg.mkBrush(SURFACE))
        centres = np.arange(len(input_keys), dtype=float)
        series = []
        for indices, intervals, shift, colour, name in (
            (s1, s1_ci, -_GROUP_OFFSET, SERIES, 'S<sub>1</sub> (first order)'),
            (st, st_ci, +_GROUP_OFFSET, SERIES_TOTAL, 'S<sub>T</sub> (total)'),
        ):
            values = np.array([indices.get(key, np.nan) for key in input_keys], dtype=float)
            ci = np.array([intervals.get(key, (np.nan, np.nan)) for key in input_keys], dtype=float)
            series.append((values, ci, shift, colour, name))
        everything = np.concatenate([np.concatenate([values, ci.ravel()]) for values, ci, *_ in series])
        everything = everything[np.isfinite(everything)]
        lo = max(float(everything.min(initial=0.0)), _INDEX_LIMITS[0])
        hi = min(float(everything.max(initial=1.0)), _INDEX_LIMITS[1])
        if not everything.size:
            # A panel of nothing but axes says only that the indices are missing,
            # never why, so the reason stands in the middle of the empty chart.
            note = pg.TextItem(
                html=(
                    f'<div style="color: {INK_2}; font-size: {tick_size}pt; text-align: center;">'
                    f'{no_index_reason}</div>'
                ),
                anchor=(0.5, 0.5),
            )
            note.textItem.setTextWidth(_NO_INDEX_TEXT_WIDTH)
            note.setPos(float(centres.mean()) if centres.size else 0.0, 0.5 * (lo + hi))
            plot.addItem(note, ignoreBounds=True)

        whisker_pen = pg.mkPen(INK, width=1.5)
        whiskers = None
        for values, ci, shift, colour, name in series:
            finite = np.isfinite(values)
            xs = centres[finite] + shift
            bars = pg.BarGraphItem(
                x0=xs - _BAR_HALF_WIDTH,
                x1=xs + _BAR_HALF_WIDTH,
                y0=0,
                y1=np.clip(values[finite], lo, hi),
                brush=pg.mkBrush(colour),
                pen=pg.mkPen(SURFACE, width=1),
            )
            plot.addItem(bars)
            legend.addItem(bars, name)

            has_ci = finite & np.all(np.isfinite(ci), axis=1)
            if has_ci.any():
                ci_lo, ci_hi = np.clip(ci[has_ci, 0], lo, hi), np.clip(ci[has_ci, 1], lo, hi)
                whiskers = pg.ErrorBarItem(
                    x=centres[has_ci] + shift, y=(ci_lo + ci_hi) / 2, height=ci_hi - ci_lo, beam=0.12, pen=whisker_pen
                )
                plot.addItem(whiskers)
            for i in np.flatnonzero(finite):
                ends = np.array([values[i], *ci[i]])
                ends = ends[np.isfinite(ends)]
                for off_scale, edge, glyph, anchor in (
                    (ends > hi, hi, '▲', (0.5, 0.0)),
                    (ends < lo, lo, '▼', (0.5, 1.0)),
                ):
                    if off_scale.any():
                        arrow = pg.TextItem(
                            html=f'<span style="color: {INK_2}; font-size: {tick_size}pt;">{glyph}</span>',
                            anchor=anchor,
                        )
                        arrow.setPos(float(centres[i] + shift), edge)
                        plot.addItem(arrow, ignoreBounds=True)
            for x in centres[~finite] + shift:
                marker = pg.TextItem(
                    html=f'<span style="color: {INK_3}; font-size: {tick_size}pt;">n/a</span>',
                    anchor=(0.5, 1.0),
                )
                marker.setPos(float(x), 0.0)
                plot.addItem(marker, ignoreBounds=True)
        if whiskers is not None:
            legend.addItem(whiskers, '95% confidence interval')

        if lo < 0:
            plot.addItem(pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen(INK_3, width=1)), ignoreBounds=True)
        pad = 0.08 * (hi - lo)
        # Extra headroom keeps the legend clear of the tallest bars.
        plot.setYRange(lo - pad, hi + 4 * pad, padding=0)
        plot.setXRange(-0.5, len(input_keys) - 0.5)
        plot.getAxis('bottom').setTicks(
            [[(float(i), plain_label(self._input_label(assay_type, key))) for i, key in enumerate(input_keys)]]
        )
        self._apply_axis_style(plot)
        return pw

    def _make_ka_vs_input(
        self,
        *,
        ka_key: str,
        input_label: str,
        offsets: np.ndarray,
        x_view: tuple[float, float],
        range_ends: tuple[float, ...],
        ka: np.ndarray,
        unit_html: str,
        show_y_label: bool,
    ) -> pg.PlotWidget:
        """Each sample's best Ka against one input's offset, on a log Ka axis.

        The panel has no title: the heading above its row names the Ka and the
        x-axis label names the input. Samples without a fit have no Ka to place
        and are left out. The panel opens on the offsets *x_view* with a margin
        of ``_OFFSET_VIEW_MARGIN`` at each end; zoom, pan and View All work from
        there. The x axis labels *range_ends*, the ends of an entered range,
        wherever they are in view.
        """
        left_axis = _LogKaAxis(orientation='left')
        left_axis.enableAutoSIPrefix(False)
        pw, plot = self._new_plot(170, 220, axisItems={'left': left_axis, 'bottom': _OffsetAxis(range_ends)})
        plot.setLogMode(y=True)
        plot.showGrid(x=True, y=True, alpha=0.25)
        ka_label = fmt_param(ka_key)
        plot.setLabel('bottom', f'Δ {input_label} [%]')
        if show_y_label:
            plot.setLabel('left', f'{ka_label} [{unit_html}]' if unit_html else ka_label)

        placed = np.isfinite(ka) & (ka > 0) & np.isfinite(offsets)
        plot.addItem(
            pg.PlotDataItem(
                offsets[placed],
                ka[placed],
                pen=None,
                symbol='o',
                symbolSize=_MARKER_SIZE + 2,
                symbolBrush=pg.mkBrush(SERIES),
                symbolPen=pg.mkPen(SURFACE, width=2),
                name='fitted sample',
            )
        )
        plot.setXRange(*x_view, padding=_OFFSET_VIEW_MARGIN)
        self._apply_axis_style(plot)
        # pyqtgraph sizes tick text at paint time, too late for y-linked panels, which then
        # drop their labels; a fixed width that holds the widest label keeps every one in view.
        widest = QFontMetrics(self._tick_font()).horizontalAdvance('8.88×10⁻¹⁰')
        left_axis.setStyle(autoExpandTextSpace=False, tickTextWidth=widest)
        return pw

    # ---- HEATMAP ------------------------------------------------------

    def _render_heatmap(self, result: SensitivityResult) -> None:
        """One map per Ka key, coloured by the statistic chosen in the selector, each with its colour bar."""
        assay_type = self._assay_type(result)
        cfg = result.config
        stat = self._colour_combo.currentData()
        self._colour_caption.setText(next(caption for _, key, caption in _COLOUR_STATS if key == stat))
        use_log = self._style.get('distribution', {}).get('ka_scale', 'log₁₀') == 'log₁₀'
        cmap = _DIVERGING_CMAP if stat == 'change' else _SEQUENTIAL_CMAP
        x_offsets = np.asarray(result.x_offsets_pct, dtype=float)
        y_offsets = np.asarray(result.y_offsets_pct, dtype=float)

        glw = pg.GraphicsLayoutWidget()
        glw.setBackground(SURFACE)
        glw.setMinimumHeight(320)
        self._heatmap_glw = glw
        self._hover_targets = []

        x0, x_w, step_x = self._axis_extent(x_offsets)
        y0, y_h, step_y = self._axis_extent(y_offsets)
        x_input = self._input_label(assay_type, cfg.x_key)
        y_input = self._input_label(assay_type, cfg.y_key)
        r2_grid = None if result.r2_grid is None else np.asarray(result.r2_grid, dtype=float)
        tick_font = self._tick_font()
        label_size = self._style.get('distribution', {}).get('label_font_size', 14)

        for i, ka_key in enumerate(result.ka_keys):
            grid = np.asarray(result.ka_grid[ka_key], dtype=float)
            baseline = result.baseline_ka[ka_key]
            ka_label = fmt_param(ka_key)
            unit_html = self._ka_unit_html(assay_type, ka_key)
            values, (lo, hi), ticks = _colour_scale(stat, grid, r2_grid, baseline, use_log)
            shown = np.isfinite(values)
            rgba = cmap.map(np.where(shown, (values - lo) / (hi - lo), 0.0), mode='byte')
            rgba[~shown] = (0, 0, 0, 0)

            plot = glw.addPlot(row=0, col=2 * i)
            plot.setLabel('bottom', f'Δ {x_input} [%]')
            plot.setLabel('left', f'Δ {y_input} [%]')
            self._set_title(plot, ka_label)
            plot.getViewBox().setDefaultPadding(0.02)
            # Each tick names a cell, so it sits at that cell's centre.
            _label_cells_in_view(plot, x_offsets, y_offsets)

            img = pg.ImageItem()
            img.setImage(rgba, axisOrder='row-major')
            img.setRect(QRectF(x0, y0, x_w, y_h))
            plot.addItem(img)
            self._apply_axis_style(plot)

            if stat == 'change':
                # Every percent tick carries its own sign; the deepest ticks read as a ratio.
                bar_label = f'Change in {ka_label}'
            elif stat == 'ka':
                bar_label = f'{ka_label} [{unit_html}]' if unit_html else ka_label
                bar_label += ' (log scale)' if use_log else ''
            else:
                bar_label = 'R²'
            cbar = pg.ColorBarItem(values=(lo, hi), colorMap=cmap, interactive=False, width=14)
            for side in ('left', 'top', 'right', 'bottom'):
                cbar.getAxis(side).setPen(pg.mkPen(INK_3, width=1))
            cbar.axis.enableAutoSIPrefix(False)
            cbar.axis.setTicks([ticks])
            cbar.axis.setTickFont(tick_font)
            cbar.axis.setTextPen(pg.mkPen(INK_2))
            # Text space sized to the widest tick label, so none is cut off.
            widest = max(QFontMetrics(tick_font).horizontalAdvance(text) for _, text in ticks)
            cbar.axis.setStyle(autoExpandTextSpace=False, tickTextWidth=widest)
            cbar.axis.setLabel(bar_label, color=INK_2, **{'font-size': f'{label_size}pt'})
            cbar.axis.setWidth()
            # A label on an end tick overhangs the bar by half its height; margins that size keep it in view.
            overhang = QFontMetrics(tick_font).height() / 2
            cbar.layout.setContentsMargins(0, overhang, 0, overhang)
            glw.addItem(cbar, row=0, col=2 * i + 1)

            pen = pg.mkPen(INK, width=1, style=Qt.PenStyle.DashLine)
            vline = pg.InfiniteLine(angle=90, movable=False, pen=pen)
            hline = pg.InfiniteLine(angle=0, movable=False, pen=pen)
            vline.setVisible(False)
            hline.setVisible(False)
            plot.addItem(vline, ignoreBounds=True)
            plot.addItem(hline, ignoreBounds=True)
            readout = pg.TextItem(anchor=(0, 1), color=INK, fill=pg.mkBrush(252, 252, 251, 220))
            readout.setVisible(False)
            plot.addItem(readout, ignoreBounds=True)

            self._hover_targets.append(
                {
                    'plot': plot,
                    'vb': plot.getViewBox(),
                    'grid': grid,
                    'r2_grid': r2_grid,
                    'values': values,
                    'colour_bar': cbar,
                    'baseline': baseline,
                    'x_label': x_input,
                    'y_label': y_input,
                    'x_offsets': x_offsets,
                    'y_offsets': y_offsets,
                    'step_x': step_x,
                    'step_y': step_y,
                    'vline': vline,
                    'hline': hline,
                    'readout': readout,
                    'ka_key': ka_key,
                    'unit_html': unit_html,
                }
            )

        glw.scene().sigMouseMoved.connect(self._on_heatmap_hover)
        self._results_layout.addWidget(glw, stretch=1)

    @staticmethod
    def _axis_extent(offsets: np.ndarray) -> tuple[float, float, float]:
        """Return ``(origin, length, step)`` mapping cell centres to *offsets*.

        ``setRect`` maps the pixel grid ``[0..n]`` onto ``[origin, origin+length]``;
        extending half a step past each end centres each cell on its offset.
        """
        if offsets.size >= 2:
            step = float(offsets[1] - offsets[0])
        else:
            step = 1.0
        origin = float(offsets[0]) - step / 2 if offsets.size else -0.5
        length = float(offsets[-1] - offsets[0]) + step if offsets.size else 1.0
        return origin, length, step

    def _on_heatmap_hover(self, scene_pos) -> None:
        """Update the crosshair and readout for the heatmap cell under the cursor."""
        for target in self._hover_targets:
            plot = target['plot']
            if not plot.sceneBoundingRect().contains(scene_pos):
                target['vline'].setVisible(False)
                target['hline'].setVisible(False)
                target['readout'].setVisible(False)
                continue
            view_pt = target['vb'].mapSceneToView(scene_pos)
            x_offsets = target['x_offsets']
            y_offsets = target['y_offsets']
            step_x = target['step_x'] or 1.0
            step_y = target['step_y'] or 1.0
            ix = int(np.clip(round((view_pt.x() - x_offsets[0]) / step_x), 0, x_offsets.size - 1))
            iy = int(np.clip(round((view_pt.y() - y_offsets[0]) / step_y), 0, y_offsets.size - 1))
            cx, cy = float(x_offsets[ix]), float(y_offsets[iy])
            target['vline'].setPos(cx)
            target['hline'].setPos(cy)
            target['vline'].setVisible(True)
            target['hline'].setVisible(True)
            readout = target['readout']
            readout.setHtml(self._readout_html(target, ix, iy))
            # The text opens towards the middle of the map, so it stays inside the plot.
            readout.setAnchor(
                (0.0 if ix <= (x_offsets.size - 1) / 2 else 1.0, 1.0 if iy <= (y_offsets.size - 1) / 2 else 0.0)
            )
            readout.setPos(cx, cy)
            readout.setVisible(True)

    @staticmethod
    def _readout_html(target: dict, ix: int, iy: int) -> str:
        """Hover text for heatmap cell (*ix*, *iy*): its two input offsets, then its Ka, Ka change and R²."""
        where = (
            f'{target["x_label"]} {_signed_pct(target["x_offsets"][ix])}, '
            f'{target["y_label"]} {_signed_pct(target["y_offsets"][iy])}'
        )
        ka = target['grid'][iy, ix]
        if not np.isfinite(ka):
            return f'{where}<br>no fit could be produced'
        ka_label = fmt_param(target['ka_key'])
        lines = [
            where,
            f'{ka_label} = {fmt_sci(ka, 3)} {target["unit_html"]}'.strip(),
            f'{ka_label} change: {_signed_pct(100.0 * (ka / target["baseline"] - 1.0))}',
        ]
        if target['r2_grid'] is not None:
            lines.append(f'R² = {fmt_r2(target["r2_grid"][iy, ix])}')
        return '<br>'.join(lines)

    # ------------------------------------------------------------------
    # Styling helpers
    # ------------------------------------------------------------------

    def _title_size(self) -> int:
        return self._style.get('distribution', {}).get('title_font_size', 16)

    def _set_title(self, plot_item: pg.PlotItem, html: str) -> None:
        """Set a bold ink title; the title row grows to fit a two-line one."""
        plot_item.setTitle(html, size=f'{self._title_size()}pt', bold=True, color=INK)
        height = max(30.0, plot_item.titleLabel.itemRect().height())
        plot_item.titleLabel.setMaximumHeight(height)
        plot_item.layout.setRowFixedHeight(0, height)

    def _tick_font(self) -> QFont:
        font = QFont()
        font.setPointSize(self._style.get('distribution', {}).get('tick_font_size', 12))
        return font

    def _apply_axis_style(self, plot_item: pg.PlotItem) -> None:
        """Apply distribution fonts and ink pens to a subplot's axes."""
        label_font = QFont()
        label_font.setPointSize(self._style.get('distribution', {}).get('label_font_size', 14))
        tick_font = self._tick_font()
        for axis_name in ('left', 'bottom'):
            axis = plot_item.getAxis(axis_name)
            axis.label.setFont(label_font)
            axis.setTickFont(tick_font)
            axis.setPen(pg.mkPen(INK_3, width=1))
            axis.setTextPen(pg.mkPen(INK_2))
