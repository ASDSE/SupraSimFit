"""Identifiability view: how well each Ka value explains the data (pyqtgraph).

Section 1, after a fit: every multistart attempt as a dot at its Ka and R², the
exact profile (the best R² reachable at each Ka) as a line, the Min R² line,
the profile confidence interval as a band with its R² cut-off as a dotted line,
and marginal Ka and R² histograms of the attempts. Section 2, after a
sensitivity run: the best fit of every Sobol sample as a translucent cloud
behind the attempts and lines, optionally coloured by one input's offset.

The R² axis is linear: for one signal the squared misfit is linear in R², so
equal R² gaps are equal misfit gaps. The peak, the cut-off and the floor sit
close together near 1, so the default view frames them and View All shows the
full range. A Min R² far from the peak and the cut-off is left out of the
default view, with a note, so it never squeezes them together.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QEvent, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from core.assays.registry import ASSAY_REGISTRY, AssayType, ParamKind
from core.pipeline.fit_pipeline import FitResult, fit_replica_ids, input_replica_ids
from core.pipeline.profile import ProfileResult, profile_supported
from core.pipeline.sensitivity import TITRANT, ReplicateMode, SensitivityResult
from gui.plotting.colors import BELOW_FLOOR, INK, INK_2, INK_3, SERIES, SURFACE
from gui.plotting.labels import fmt_param, fmt_param_plain, fmt_r2, fmt_sci, fmt_unit_html, plain_label
from gui.plotting.plot_style import DEFAULT_STYLE
from gui.plotting.sensitivity_widget import _LogKaAxis
from gui.widgets.assay_conditions import condition_fields
from gui.widgets.replica_panel import describe_replicates

_BAND = (82, 81, 78, 28)
_GRID_ALPHA = 0.18
# Diverging scale for colouring samples by an input's offset: lower, zero, higher.
# The mid-grey centre stays visible on the surface.
_OFFSET_CMAP = pg.ColorMap(pos=[0.0, 0.5, 1.0], color=[(42, 120, 214), (137, 135, 129), (227, 73, 72)])

_DOT_SIZE = 10
_RING_WIDTH = 2
# The sensitivity samples are a background density layer of up to thousands of
# dots: translucent and without rings, which would form a lattice over the
# attempts and lines drawn on top.
_SAMPLE_SIZE = 8
_SAMPLE_ALPHA = 77  # of 255: about 30 %
# Coloured samples are more opaque, so an offset's hue stays readable.
_COLOURED_SAMPLE_ALPHA = 153  # about 60 %
_SAMPLE_Z = 1  # above the band (-10), below the attempts (2, 2.5) and every line (2.8 and up)

# Bins of each marginal histogram across the part of its axis in view.
_HIST_BINS = 40
_TOP_HIST_HEIGHT = 100
# Shortest the Ka histogram is squeezed to on a short window. It reads as a
# shape rather than a count, so it gives its room up before the main plot does.
_TOP_HIST_MIN_HEIGHT = 44
_RIGHT_HIST_WIDTH = 140
# Narrowest and shortest the main R² plot's data area may be squeezed, by the
# sidebar or a short window say. Below these the page scrolls instead.
_MAIN_MIN_WIDTH = 240
_MAIN_MIN_HEIGHT = 96
# Smallest R² span the default view separates its levels by, so tick labels
# stay at six decimals or fewer.
_MIN_R2_SPAN = 1e-5
# How many peak-to-cut-off gaps beyond the peak and the cut-off the default view
# reaches to include the Min R² line. At two, the peak and the cut-off keep at
# least an eighth of the view's height between them, unless sensitivity samples
# reach above the peak.
_FLOOR_REACH = 2.0
# How far the view can be zoomed out: every drawn dot has an R² from 0 to 1.
_R2_LIMITS = (-0.05, 1.05)
# Below this height a chart without marginal histograms stops shrinking and the
# page scrolls; one with them stops at the height its own cells need.
_CANVAS_MIN_HEIGHT = 320

_PLACEHOLDER = 'Run a fit to see how well each Ka value can explain your data.'
_PROFILE_PENDING = 'Working out how well each Ka value can explain the data of this fit…'
_READING_POINTER = 'How to read this plot: the ? button above.'


def _pct(ratio: float) -> str:
    """Signed percent change for a ratio to the best fit, with a real minus sign.

    Whole percent, with as many decimals as it takes for a drop to stay short of
    −100 %, which would read as a Ka of zero.
    """
    change = 100.0 * (ratio - 1.0)
    decimals = 0
    while decimals < 4 and round(change, decimals) <= -100.0 < change:
        decimals += 1
    return f'{change:+.{decimals}f}%'.replace('-', '−')


def _count(n: int, noun: str) -> str:
    """``1 data point``, ``12 data points``."""
    return f'{n} {noun}' if n == 1 else f'{n} {noun}s'


def _on_surface(colour: str, alpha: int) -> str:
    """The solid colour *colour* shows at *alpha* (of 255) over the surface, for a legend glyph."""
    top, base = QColor(colour), QColor(SURFACE)
    a = alpha / 255.0
    return QColor(*(round(a * t + (1.0 - a) * b) for t, b in zip(top.getRgb()[:3], base.getRgb()[:3]))).name()


def _plain_input_label(assay_type: AssayType, key: str) -> str:
    """Plain-text name of a perturbable input, for the colour-by combo box."""
    if key == TITRANT:
        return f'{ASSAY_REGISTRY[assay_type].x_label} (titrant)'
    for field in condition_fields(assay_type):
        if field.key == key:
            return plain_label(field.label)
    return fmt_param_plain(key)


def _default_r2_range(
    values: np.ndarray, peak: float | None, cut: float | None, floor: float | None
) -> tuple[float, float] | None:
    """Default R² span of the view, from the reference levels and the R² *values* inside the default Ka span.

    With a confidence cut-off or a floor, the levels that decide the reading are
    the peak (the profile's best R², else the best of *values*), the cut-off and
    the floor. A floor more than ``_FLOOR_REACH`` peak-to-cut-off gaps beyond
    them is left out, so it cannot squeeze the peak and the cut-off together.
    The view runs from one level span below the lowest level kept to 0.6 spans
    above the highest of them and *values*, never more than 0.1 span above
    R² = 1. Values far below the levels stay out of the default view, so a few
    poor attempts cannot squeeze the levels into a few pixels. Without a cut-off
    or a floor, the view frames *values*. ``None`` when there is nothing to frame.
    """
    values = values[np.isfinite(values)]
    if cut is None and floor is None:
        if not values.size:
            return None
        lo, hi = float(values.min()), float(values.max())
        pad = max(0.08 * (hi - lo), _MIN_R2_SPAN)
        return lo - pad, hi + pad
    best = peak if peak is not None else (float(values.max()) if values.size else None)
    levels = [v for v in (cut, best) if v is not None]
    if floor is not None:
        if cut is not None and best is not None:
            reach = _FLOOR_REACH * max(best - cut, _MIN_R2_SPAN)
            if min(cut, best) - reach <= floor <= max(cut, best) + reach:
                levels.append(floor)
        else:
            levels.append(floor)
    low, high = min(levels), max(levels)
    span = max(high - low, _MIN_R2_SPAN)
    top = max(high, float(values.max())) if values.size else high
    return low - span, min(top + 0.6 * span, 1.0 + 0.1 * span)


def _fill_histogram(
    bars: tuple[pg.BarGraphItem, pg.BarGraphItem],
    values: np.ndarray,
    passing: np.ndarray,
    view_range: Sequence[float],
    vertical: bool,
) -> None:
    """Recount *values* in view into ``_HIST_BINS`` bins across *view_range*, stacked: below the floor, then passing.

    Bin edges sit on multiples of the bin width, so panning without zooming
    keeps every bin in place.
    """
    lo, hi = sorted(view_range)
    width = (hi - lo) / _HIST_BINS
    if not width > 0:
        return
    edges = np.floor(lo / width) * width + width * np.arange(_HIST_BINS + 2)
    below = np.histogram(values[~passing], bins=edges)[0]
    stacked = below + np.histogram(values[passing], bins=edges)[0]
    for bar, start, end in zip(bars, (np.zeros_like(below), below), (below, stacked)):
        if vertical:
            bar.setOpts(x0=edges[:-1], x1=edges[1:], y0=start, y1=end)
        else:
            bar.setOpts(x0=start, x1=end, y0=edges[:-1], y1=edges[1:])


class _CountAxis(pg.AxisItem):
    """Count axis of a histogram: major ticks and gridlines only, at whole numbers."""

    def tickValues(self, minVal, maxVal, size):
        levels = super().tickValues(minVal, maxVal, size)
        if not levels:
            return levels
        spacing, values = levels[0]
        return [(spacing, [v for v in values if abs(v - round(v)) < 1e-9])]

    def tickStrings(self, values, scale, spacing):
        return [f'{v:.0f}' for v in values]


class _LevelAxis(pg.AxisItem):
    """Right-hand axis naming the horizontal reference lines at their heights, outside the data.

    Its ticks are set with :meth:`setTicks`. Where two names would overlap,
    they are moved apart symmetrically about their levels.
    """

    def generateDrawSpecs(self, p):
        specs = super().generateDrawSpecs(p)
        if specs is None:
            return None
        axis_spec, tick_specs, text_specs = specs
        text_specs = sorted(text_specs, key=lambda spec: spec[0].center().y())
        for upper, lower in zip(text_specs, text_specs[1:]):
            overlap = upper[0].bottom() - lower[0].top()
            if overlap > 0:
                upper[0].translate(0, -overlap / 2)
                lower[0].translate(0, overlap / 2)
        return axis_spec, tick_specs, text_specs


class _Canvas(pg.GraphicsLayoutWidget):
    """Chart canvas that prefers its minimum height, which :meth:`IdentifiabilityWidget._fit_canvas` sets.

    The scrolling page sizes its word-wrapped content from preferred heights,
    so the canvas takes the height it is given and the text below moves down.
    """

    def sizeHint(self) -> QSize:
        return QSize(super().sizeHint().width(), self.minimumHeight())


class IdentifiabilityWidget(QWidget):
    """Fit attempts, the exact Ka profile and sensitivity samples on one R²-vs-Ka chart.

    :meth:`update_fit` shows a fit and its :class:`ProfileResult`;
    :meth:`update_sensitivity` overlays a :class:`SensitivityResult`;
    :meth:`clear` returns to the placeholder and :meth:`apply_style` restyles.
    :meth:`show_mismatch` hides the fit, or only the sensitivity overlay, behind
    a note while it no longer matches the loaded selection; both are kept and
    drawn again once the note is removed.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setToolTip(
            '<qt>Each dot is one fit attempt: its K<sub>a</sub> across, how well it fits up.<br>'
            'The line is the best R² any fit can reach at each K<sub>a</sub>; the shaded band is '
            'the range of K<sub>a</sub> the data support.<br>Scroll to zoom, drag to pan, '
            'right-click for the full view.</qt>'
        )
        self._style: dict = dict(DEFAULT_STYLE)
        self._fit: FitResult | None = None
        self._profile: ProfileResult | None = None
        self._profile_pending = False  # the fit's profile is still being computed
        self._assay_type_name = ''
        self._sensitivity: SensitivityResult | None = None
        self._fit_note: str | None = None  # why the fit is hidden
        self._sensitivity_note: str | None = None  # why the sensitivity overlay is hidden
        self._replica_ids: list[str] | None = None
        self._colour_key: str | None = None
        # Drawn items per Ka key, for tests and restyling: main plot, curves, scatters.
        self._items: dict[str, dict] = {}
        self._legend_entries: dict[str, tuple[str, str]] = {}
        # The last render's notes: about the chart, and about the drawn sensitivity samples.
        self._note_lists: tuple[list[str], list[str]] = ([], [])

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._stack_host = QWidget()
        self._stack = QStackedLayout(self._stack_host)

        self._message = QLabel(_PLACEHOLDER)
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setWordWrap(True)
        self._message.setStyleSheet(f'color: {INK_3}; font-size: 14px;')
        self._stack.addWidget(self._message)

        # The page scrolls: the chart fills the tab's height (see _fit_canvas)
        # and the text below it moves down instead of running over its axis.
        self._content = QScrollArea()
        self._content.setWidgetResizable(True)
        self._content.setFrameShape(QFrame.Shape.NoFrame)
        self._content.viewport().installEventFilter(self)
        page = QWidget()
        page.setObjectName('identifiabilityContent')
        page.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        page.setStyleSheet(f'#identifiabilityContent {{ background: {SURFACE}; }}')
        content = QVBoxLayout(page)
        content.setContentsMargins(10, 6, 10, 6)
        content.setSpacing(4)

        self._summary = QLabel()
        self._summary.setTextFormat(Qt.TextFormat.RichText)
        self._summary.setWordWrap(True)
        self._summary.setStyleSheet(f'color: {INK}; font-size: 14px;')
        content.addWidget(self._summary)

        self._controls = QWidget()
        controls = QHBoxLayout(self._controls)
        controls.setContentsMargins(0, 0, 0, 0)
        self._show_samples = QCheckBox('Show sensitivity samples')
        self._show_samples.setChecked(True)
        self._show_samples.setToolTip('Show or hide the best fits of the sensitivity run. The view stays as it is.')
        self._show_samples.toggled.connect(self._on_show_samples)
        controls.addWidget(self._show_samples)
        controls.addSpacing(16)
        self._colour_label = QLabel('Colour by:')
        self._colour_label.setStyleSheet(f'color: {INK_2};')
        controls.addWidget(self._colour_label)
        self._colour_combo = QComboBox()
        self._colour_combo.setToolTip('Colour each sample by how far that input was moved from what you entered.')
        self._colour_combo.currentIndexChanged.connect(self._on_colour_changed)
        controls.addWidget(self._colour_combo)
        controls.addStretch(1)
        self._controls.setVisible(False)
        content.addWidget(self._controls)

        self._glw = _Canvas()
        self._glw.setBackground(SURFACE)
        self._glw.setMinimumHeight(_CANVAS_MIN_HEIGHT)
        content.addWidget(self._glw, stretch=1)

        self._legend = QLabel()
        self._legend.setTextFormat(Qt.TextFormat.RichText)
        self._legend.setWordWrap(True)
        self._legend.setStyleSheet(f'color: {INK_2}; font-size: 13px;')
        content.addWidget(self._legend)

        self._notes = QLabel()
        self._notes.setTextFormat(Qt.TextFormat.RichText)
        self._notes.setWordWrap(True)
        self._notes.setStyleSheet(f'color: {INK_2}; font-size: 13px;')
        content.addWidget(self._notes)

        self._content.setWidget(page)
        self._stack.addWidget(self._content)
        self._stack.setCurrentWidget(self._message)
        outer.addWidget(self._stack_host)

    # ------------------------------------------------------------------
    # Size
    # ------------------------------------------------------------------

    def minimumSizeHint(self) -> QSize:
        """Wide enough for the chart with its main plot at ``_MAIN_MIN_WIDTH``, so a splitter cannot squeeze it."""
        hint = super().minimumSizeHint()
        if self._stack.currentWidget() is not self._content:
            return hint
        margins = self._content.widget().layout().contentsMargins()
        chart = self._glw.ci.effectiveSizeHint(Qt.SizeHint.MinimumSize).width()
        scrollbar = self._content.verticalScrollBar().sizeHint().width()
        width = int(np.ceil(chart)) + margins.left() + margins.right() + scrollbar
        return QSize(max(hint.width(), width), hint.height())

    def eventFilter(self, watched, event) -> bool:
        if watched is self._content.viewport() and event.type() == QEvent.Type.Resize:
            self._fit_canvas()
        return super().eventFilter(watched, event)

    def _fit_canvas(self) -> None:
        """Give the chart the tab's height less the text above it and the legend, or the whole of it when short.

        The chart with its Ka axis is what the tab is for, so it comes first and
        the text gives way in turn. Where the legend would leave the chart less
        than ``_CANVAS_MIN_HEIGHT``, the legend moves below the fold and the
        chart takes the height left over; where even that is short, the chart
        shrinks with it, down to the height its own cells need — the main plot
        keeps ``_MAIN_MIN_HEIGHT`` of data area under its Ka axis and the Ka
        histogram gives up its height first. Only below that does the page
        scroll. The notes are always below the chart.
        """
        viewport = self._content.viewport()
        layout = self._content.widget().layout()
        margins = layout.contentsMargins()
        scrollbar = self._content.verticalScrollBar()
        width = viewport.width() - margins.left() - margins.right()
        if not scrollbar.isVisible():
            # The text is measured at the width it has once the page scrolls,
            # which is what this is about to decide. Measured at the wider
            # viewport it wraps to one line fewer, and the chart it then sizes
            # runs a line past the bottom of the tab.
            width -= scrollbar.sizeHint().width()
        above = margins.top() + self._summary.heightForWidth(width) + layout.spacing()
        if not self._controls.isHidden():
            above += self._controls.sizeHint().height() + layout.spacing()
        room = viewport.height() - above
        needed = int(np.ceil(self._glw.ci.effectiveSizeHint(Qt.SizeHint.MinimumSize).height()))
        roomy = max(_CANVAS_MIN_HEIGHT, needed)
        with_legend = room - self._legend.heightForWidth(width) - layout.spacing()
        height = with_legend if with_legend >= roomy else min(max(room, needed), roomy)
        if height != self._glw.minimumHeight():
            self._glw.setMinimumHeight(height)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_fit(self, fit_result: FitResult, profile: ProfileResult | None, assay_type_name: str) -> None:
        """Show *fit_result*'s attempts and, when given, its Ka *profile*.

        *profile* is ``None`` for an assay without a single binding constant,
        or when the profile has not been computed.
        """
        self._fit = fit_result
        self._profile = profile
        self._profile_pending = False
        self._assay_type_name = assay_type_name
        self._render()

    def show_profile_pending(self, fit_result: FitResult, assay_type_name: str) -> None:
        """Hold *fit_result* and say its Ka profile is being computed, until :meth:`update_fit` brings it.

        The page never shows a previous fit meanwhile; a note hiding the fit
        still takes precedence.
        """
        self._fit = fit_result
        self._profile = None
        self._profile_pending = True
        self._assay_type_name = assay_type_name
        self._render()

    def update_sensitivity(self, result: SensitivityResult | None) -> None:
        """Overlay the sample best fits of a sensitivity *result* (``None`` removes them)."""
        self._sensitivity = result
        self._sync_colour_combo()
        self._render()

    def show_mismatch(self, fit_note: str | None, sensitivity_note: str | None = None) -> None:
        """Hide the fit behind *fit_note* and the sensitivity overlay behind *sensitivity_note*; ``None`` shows it.

        Unchanged notes leave the page as it is.
        """
        if (fit_note, sensitivity_note) == (self._fit_note, self._sensitivity_note):
            return
        self._fit_note = fit_note
        self._sensitivity_note = sensitivity_note
        self._render()

    def set_replica_ids(self, replica_ids: Sequence[str] | None) -> None:
        """The loaded data's replicate ids in order, so notes name replicates as the Replicates panel does."""
        self._replica_ids = None if replica_ids is None else list(replica_ids)
        self._render()

    def clear(self) -> None:
        """Drop the fit, profile and sensitivity overlay and show the placeholder."""
        self._fit = None
        self._profile = None
        self._profile_pending = False
        self._assay_type_name = ''
        self._sensitivity = None
        self._sync_colour_combo()
        self._render()

    def apply_style(self, style: dict) -> None:
        """Adopt a new style dict (fonts) and re-render."""
        self._style = style
        self._render()

    def has_chart(self) -> bool:
        """Whether the tab is showing a chart rather than a placeholder or a note."""
        return self._stack.currentWidget() is self._content

    def export_image(self, path: str) -> None:
        """Save the tab's heading, chart, legend and notes as a picture.

        The sample controls stay out of it: they change what the chart shows and
        there is nothing to change in a saved picture.

        Parameters
        ----------
        path : str
            Where to write it, ending in ``.png``. A whole tab is saved as one
            picture; :func:`~gui.plotting.export.export_widget` says why it is
            not offered as a drawing.

        Raises
        ------
        ValueError
            When there is no chart on screen to save, or the suffix is not
            ``.png``.
        """
        from gui.plotting.export import export_widget

        if not self.has_chart():
            raise ValueError('There is no identifiability chart to save yet. Run a fit, then save it.')
        # The pointer to the guide button means nothing in a picture read on its own.
        notes = self._notes.text()
        self._notes.setText(notes.removesuffix(_READING_POINTER).removesuffix('<br>'))
        try:
            export_widget(self._content.widget(), path, without=(self._controls,))
        finally:
            self._notes.setText(notes)

    # ------------------------------------------------------------------
    # Sample controls
    # ------------------------------------------------------------------

    def _sample_inputs(self) -> list[str]:
        result = self._sensitivity
        if result is None or result.sample_offsets_pct is None:
            return []
        return list(result.sample_offsets_pct)

    def _sync_colour_combo(self) -> None:
        """Offer None plus each varied input of the current run; keep the choice if still offered."""
        keys = self._sample_inputs()
        if self._colour_key not in keys:
            self._colour_key = None
        self._colour_combo.blockSignals(True)
        self._colour_combo.clear()
        self._colour_combo.addItem('None', None)
        if keys:
            assay_type = AssayType[self._sensitivity.assay_type]
            for key in keys:
                self._colour_combo.addItem(_plain_input_label(assay_type, key), key)
        self._colour_combo.setCurrentIndex(0 if self._colour_key is None else keys.index(self._colour_key) + 1)
        self._colour_combo.blockSignals(False)

    def _on_colour_changed(self, index: int) -> None:
        self._colour_key = self._colour_combo.itemData(index)
        self._render()

    def _on_show_samples(self, shown: bool) -> None:
        """Show or hide the sample cloud with its colour bar, colour control and legend entries; the view stays."""
        for items in self._items.values():
            for key in ('samples', 'colour_bar'):
                if items.get(key) is not None:
                    items[key].setVisible(shown)
        self._sync_colour_control()
        self._set_legend()
        self._set_notes()
        self._fit_canvas()

    def _sync_colour_control(self) -> None:
        """Offer the colour choice only while the samples it colours are shown."""
        offered = self._show_samples.isChecked() and bool(self._sample_inputs())
        self._colour_label.setVisible(offered)
        self._colour_combo.setVisible(offered)

    def _set_legend(self) -> None:
        """Write the legend, leaving out the sample entries while the samples are hidden."""
        hidden = () if self._show_samples.isChecked() else ('samples', 'colour')
        entries = [entry for key, entry in self._legend_entries.items() if key not in hidden]
        # Non-breaking spaces inside each entry, so the legend only wraps between entries.
        self._legend.setText('&emsp; '.join(f'{glyph}&nbsp;{text.replace(" ", "&nbsp;")}' for glyph, text in entries))

    def _set_notes(self) -> None:
        """Write the notes, leaving out those about the sensitivity samples while the samples are hidden."""
        notes, sample_notes = self._note_lists
        shown = [*notes, *(sample_notes if self._show_samples.isChecked() else ()), _READING_POINTER]
        self._notes.setText('<br>'.join(shown))

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _show_message(self, text: str) -> None:
        self._message.setText(text)
        self._stack.setCurrentWidget(self._message)
        self.updateGeometry()

    def _render(self) -> None:
        """Rebuild the page from the stored fit, profile and sensitivity result."""
        self._glw.clear()
        self._items = {}
        self._legend_entries = {}
        # The sample controls are offered only while there are sensitivity samples to draw.
        self._controls.setVisible(False)
        if self._fit is None:
            self._show_message(_PLACEHOLDER)
            return
        if self._fit_note:
            self._show_message(self._fit_note)
            return
        assay_type = AssayType[self._assay_type_name]
        meta = ASSAY_REGISTRY[assay_type]
        ka_keys = [k for k in meta.parameter_keys if meta.param_kinds[k] is ParamKind.BINDING_CONSTANT]
        if not ka_keys:
            self._show_message(f'Not applicable: a {meta.subtype_label} fit has no binding constant to examine.')
            return
        if self._profile_pending:
            self._show_message(_PROFILE_PENDING)
            return

        fit = self._fit
        floor = fit.fit_config.get('min_r_squared')
        profile = self._profile
        notes: list[str] = []
        # Notes about the drawn sensitivity samples, shown only while the samples are.
        sample_notes: list[str] = []
        if not profile_supported(assay_type):
            notes.append(
                'The best R² reachable at each K<sub>a</sub> can only be computed for assays with a single '
                'binding constant, so only the fit attempts are shown.'
            )
        elif profile is None:
            notes.append('The best-R² line and the confidence interval are not available for this fit.')
        if floor is None:
            notes.append('This fit does not record its Min R², so no Min R² line is drawn.')

        attempts = self._attempts(fit, notes)
        samples = self._samples(floor, notes, sample_notes)
        self._controls.setVisible(samples is not None)
        self._sync_colour_control()
        self._replicate_notes(fit, samples is not None, notes, sample_notes)

        summary = []
        for col, ka_key in enumerate(ka_keys):
            key_profile = profile if profile is not None and profile.ka_key == ka_key else None
            unit_html = fmt_unit_html(meta.units.get(ka_key, ''))
            self._render_key(3 * col, ka_key, unit_html, floor, key_profile, attempts, samples, notes, sample_notes)
            summary.append(self._summary_line(ka_key, unit_html, key_profile, floor))

        self._summary.setText('<br>'.join(summary))
        self._set_legend()
        self._note_lists = (notes, sample_notes)
        self._set_notes()
        self._stack.setCurrentWidget(self._content)
        self._fit_canvas()
        self.updateGeometry()

    def _replicate_notes(self, fit: FitResult, drawn: bool, notes: list[str], sample_notes: list[str]) -> None:
        """Name the replicates the fit left out in *notes*, and in *sample_notes* a run whose samples describe others.

        *drawn* says whether the sensitivity samples are drawn.
        """
        used = fit_replica_ids(fit)
        if used is None:
            skipped = list(fit.metadata.get('replica_failures') or {})
        else:
            skipped = [rid for rid in input_replica_ids(fit) or () if rid not in used]
        run_used = None
        if drawn and self._sensitivity.baseline_fit is not None:
            run_used = fit_replica_ids(self._sensitivity.baseline_fit)
        same_run = drawn and run_used is not None and used is not None and set(run_used) == set(used)
        if skipped:
            names = describe_replicates(skipped, self._replica_ids)
            many = len(skipped) > 1
            where = 'of the line, the attempts and the sensitivity samples' if same_run else 'here'
            notes.append(
                f'{names[0].upper()}{names[1:]} {"are" if many else "is"} left out {where}, '
                f'as {"they were" if many else "it was"} from the fit.'
            )
        if run_used is not None and used is not None and set(run_used) != set(used):
            sample_notes.append(
                f'The sensitivity run used {describe_replicates(run_used, self._replica_ids)}, but this fit used '
                f'{describe_replicates(used, self._replica_ids)}, so the samples describe other replicates than '
                'the line and the attempts.'
            )

    def _attempts(self, fit: FitResult, notes: list[str]) -> dict | None:
        """The fit's attempts with R² ≥ 0, noting how many were hidden and why."""
        if fit.attempt_samples is None or fit.attempt_quality is None:
            notes.append('This fit has no record of its individual attempts, so no dots are shown.')
            return None
        r2 = np.asarray(fit.attempt_quality['r_squared'], dtype=float)
        n_negative = int(np.sum(r2 < 0))
        if n_negative:
            notes.append(f'{n_negative} of {r2.size} attempts not shown: they fit worse than a flat line (R² &lt; 0).')
        return {'samples': fit.attempt_samples, 'r2': r2}

    def _samples(self, floor: float | None, notes: list[str], sample_notes: list[str]) -> dict | None:
        """The sensitivity run's sample best fits, when they can be compared with this fit of Min R² *floor*.

        Why no samples are drawn goes in *notes*; what to know about the drawn samples in *sample_notes*.
        """
        result = self._sensitivity
        if result is None:
            return None
        if self._sensitivity_note:
            notes.append(f'The sensitivity samples are not shown. {self._sensitivity_note}')
            return None
        if result.assay_type != self._assay_type_name:
            notes.append('The last sensitivity run was for another assay type; run it again to compare it here.')
            return None
        if result.sample_ka is None:
            notes.append(
                'Heatmap runs are shown on the Ka Sensitivity tab only; run the sensitivity-index analysis '
                'to see its fits here.'
            )
            return None
        r2 = np.asarray(result.sample_r2, dtype=float)
        hidden = int(np.sum(~(r2 >= 0)))
        if hidden:
            sample_notes.append(
                f'{hidden} of {r2.size} sensitivity samples not shown: no fit could be made, or it fit worse '
                'than a flat line (R² &lt; 0).'
            )
        if result.floor is not None and floor is not None and result.floor != floor:
            sample_notes.append(
                f'The sensitivity run flagged its samples against a Min R² of {result.floor:g}; '
                f"the dashed line is this fit's Min R² of {floor:g}."
            )
        mode = result.config.replicate_mode
        fit_per_replica = self._fit.uncertainty_source == 'replicate'
        if mode is not ReplicateMode.FOLLOW and (mode is ReplicateMode.PER_REPLICA) != fit_per_replica:
            run_way, fit_way = (
                ('each replicate separately', 'their average')
                if mode is ReplicateMode.PER_REPLICA
                else ('the average of the replicates', 'each replicate separately')
            )
            sample_notes.append(
                f'The sensitivity run fitted {run_way} but this fit used {fit_way}, so the samples and the '
                'attempts measure R² against different signals.'
            )
        offsets = result.sample_offsets_pct.get(self._colour_key) if self._colour_key is not None else None
        return {'ka': result.sample_ka, 'r2': r2, 'offsets': offsets}

    def _summary_line(self, ka_key: str, unit_html: str, profile: ProfileResult | None, floor: float | None) -> str:
        """One line per Ka key: best fit, the confidence interval, how far it reaches and what it rests on.

        The second line names the two numbers the cut-off is worked out from —
        how many data points and how many fitted parameters — and says the
        interval reaches no further than the bounds the fit was given. An open
        side names what it stops at: the bound, or the Ka the binding model
        cannot be solved past, which lies below it.
        """
        label = fmt_param(ka_key)
        if profile is None:
            return f'{label}: fit attempts'
        best = profile.best_ka
        best_txt = f'{fmt_sci(best, 3)} {unit_html}'.strip()
        head = (
            f'{label}: best fit{" of the replicates' average" if profile.per_replica else ""} '
            f'{best_txt} (R² {fmt_r2(profile.best_r2, floor)})'
        )
        if profile.ka_pinned:
            return (
                f'{head}<br><span style="color:{INK_2}">{label} is fixed at {best_txt} by its bounds, '
                'so there is no interval.</span>'
            )
        lo, hi = profile.ci
        lo_open, hi_open = profile.ci_open
        if lo_open or hi_open:
            # The unit follows each number, never the word "open".
            ends = [
                ('open' if is_open else f'{fmt_sci(v)} {unit_html}'.strip())
                for v, is_open in ((lo, lo_open), (hi, hi_open))
            ]
            ci_txt = ' – '.join(ends)
        else:
            ci_txt = f'{fmt_sci(lo)} – {fmt_sci(hi)} {unit_html}'.strip()
        lo_pct, hi_pct = ('open' if lo_open else _pct(lo / best)), ('open' if hi_open else _pct(hi / best))
        line = f'{head} · {profile.level:.0%} CI {ci_txt} ({lo_pct} / {hi_pct})'
        line += (
            f'<br><span style="color:{INK_2}">The interval is worked out from '
            f'{_count(profile.n_points, "data point")} and {_count(profile.n_params, "fitted parameter")}, '
            'and reaches no further than the parameter bounds this fit was given.</span>'
        )
        if profile.ci_split:
            line += (
                f'<br><span style="color:{INK_2}">Not every K<sub>a</sub> inside the band explains the data well '
                'enough: the ones that do come in separate stretches, and the band spans all of them. The line '
                'shows where they are.</span>'
            )
        for is_open, unsolvable, side, edge in (
            (lo_open, profile.ci_unsolvable[0], 'lower', lo),
            (hi_open, profile.ci_unsolvable[1], 'higher', hi),
        ):
            if not is_open:
                continue
            where = f'{fmt_sci(edge)} {unit_html}'.strip()
            if unsolvable:
                line += (
                    f'<br><span style="color:{INK_2}">Open: the data cannot rule out a {side} '
                    f'K<sub>a</sub>. The binding model cannot be solved past {where}, so the curve stops '
                    'there, short of the bound this fit was given.</span>'
                )
            else:
                line += (
                    f'<br><span style="color:{INK_2}">Open: the data cannot rule out a {side} '
                    f'K<sub>a</sub>, up to the bound of {where}.</span>'
                )
        return line

    def _render_key(
        self,
        col: int,
        ka_key: str,
        unit_html: str,
        floor: float | None,
        profile: ProfileResult | None,
        attempts: dict | None,
        samples: dict | None,
        notes: list[str],
        sample_notes: list[str],
    ) -> None:
        """Draw one Ka key's chart: marginal histograms, main plot and, when colouring, a colour bar."""
        legend = self._legend_entries
        tick_font, label_font = self._fonts()
        tick_fm, label_fm = QFontMetrics(tick_font), QFontMetrics(label_font)
        left_width = tick_fm.horizontalAdvance('0.999999') + label_fm.height() + 16
        bottom_height = tick_fm.height() + label_fm.height() + 16

        main = self._glw.addPlot(
            row=1, col=col, axisItems={'bottom': _LogKaAxis('bottom'), 'right': _LevelAxis('right')}
        )
        main.getAxis('bottom').setLogMode(True)
        for name in ('left', 'bottom'):
            main.getAxis(name).enableAutoSIPrefix(False)
        main.getViewBox().setMinimumSize(_MAIN_MIN_WIDTH, _MAIN_MIN_HEIGHT)
        main.setLabel('left', 'R²')
        main.setLabel('bottom', f'{fmt_param(ka_key)} [{unit_html}]' if unit_html else fmt_param(ka_key))
        main.showGrid(x=True, y=True, alpha=_GRID_ALPHA)
        self._style_axes(main, tick_font, label_font)
        main.getAxis('left').setWidth(left_width)
        main.getAxis('bottom').setHeight(bottom_height)
        items: dict = {
            'main': main,
            'average': None,
            'replicas': [],
            'cut': None,
            'floor': None,
            'samples': None,
            'colour_bar': None,
        }
        self._items[ka_key] = items
        xs: list[np.ndarray] = []
        attempt_x = attempt_y = sample_x = sample_y = np.empty(0)
        passing = np.empty(0, dtype=bool)
        levels: list[tuple[float, str]] = []  # reference lines named on the right-hand axis

        if profile is not None:
            log_grid = np.log10(profile.grid)
            lo, hi = np.log10(profile.ci)
            # Equal bounds hold Ka at one value, so there is no interval to draw
            # and the cut-off is not one: it is the R² a one-parameter
            # improvement would have to beat. The heading says so instead.
            if not profile.ka_pinned:
                band = pg.LinearRegionItem(values=(lo, hi), movable=False, brush=pg.mkBrush(*_BAND), pen=pg.mkPen(None))
                band.setZValue(-10)
                main.addItem(band)
                legend['band'] = (
                    '<span style="color:#dddcd7">&#9608;</span>',
                    f'{profile.level:.0%} confidence interval',
                )
            for r2 in (profile.replica_r2 or {}).values():
                curve = main.plot(log_grid, r2, pen=pg.mkPen(INK_3, width=1), connect='finite', antialias=True)
                curve.setZValue(2.8)
                items['replicas'].append(curve)
            if profile.replica_r2:
                legend['replicas'] = (f'<span style="color:{INK_3}">&#9472;</span>', 'each replicate on its own')
            # A Ka the binding model cannot be solved at carries nan: the line
            # breaks there instead of stepping across the gap.
            items['average'] = main.plot(
                log_grid, profile.r2, pen=pg.mkPen(INK, width=2), connect='finite', antialias=True
            )
            items['average'].setZValue(3)
            legend['profile'] = (
                f'<span style="color:{INK}">&#9473;</span>',
                'best R² reachable at each K<sub>a</sub>'
                + (" on the replicates' average" if profile.per_replica else ''),
            )
            if not profile.ka_pinned:
                # The band spans the Ka values where the line is above this cut-off.
                items['cut'] = self._level_line(main, profile.r2_threshold, Qt.PenStyle.DotLine, INK)
                levels.append((profile.r2_threshold, f'cut-off {fmt_r2(profile.r2_threshold, floor)}'))
                legend['cut'] = (f'<span style="color:{INK}">&#8943;</span>', f'{profile.level:.0%} CI cut-off')
            xs.append(np.array([lo, hi, np.log10(profile.best_ka)]))

        if floor is not None:
            items['floor'] = self._level_line(main, floor, Qt.PenStyle.DashLine, INK_2)
            levels.append((floor, f'Min R² {floor:g}'))
            legend['floor'] = (f'<span style="color:{INK_2}">&#8211;&nbsp;&#8211;</span>', 'Min R²')

        if attempts is not None:
            ka = np.asarray(attempts['samples'][ka_key], dtype=float)
            r2 = attempts['r2']
            positive = np.isfinite(ka) & (ka > 0)
            if (~positive).any():
                notes.append(f'{int((~positive).sum())} attempts without a positive {fmt_param(ka_key)} not shown.')
            shown = positive & (r2 >= 0)
            attempt_x, attempt_y = np.log10(ka[shown]), r2[shown]
            passing = attempt_y >= floor if floor is not None else np.ones(attempt_x.size, dtype=bool)
            for key, mask, colour, z in (('below', ~passing, BELOW_FLOOR, 2), ('passing', passing, INK_2, 2.5)):
                scatter = pg.ScatterPlotItem(
                    x=attempt_x[mask],
                    y=attempt_y[mask],
                    size=_DOT_SIZE,
                    brush=pg.mkBrush(colour),
                    pen=pg.mkPen(SURFACE, width=_RING_WIDTH),
                )
                scatter.setZValue(z)
                main.addItem(scatter)
                items[f'attempts_{key}'] = scatter
            legend['passing'] = (f'<span style="color:{INK_2}">&#9679;</span>', 'fit attempt meeting Min R²')
            if (~passing).any():
                legend['below'] = (f'<span style="color:{BELOW_FLOOR}">&#9679;</span>', 'fit attempt below Min R²')
            # An attempt below the floor far from the rest (at a Ka bound, say)
            # would squeeze the interval to a sliver, so the view frames the
            # passing attempts across.
            xs.append(attempt_x[passing])

        if samples is not None and ka_key in samples['ka']:
            sample_x, sample_y = self._add_samples(col, main, ka_key, samples)
            xs.append(sample_x)

        right_width = 0
        if levels:
            axis = main.getAxis('right')
            axis.setTicks([levels])
            axis.setTickFont(tick_font)
            axis.setPen(pg.mkPen(INK_3, width=1))
            axis.setTextPen(pg.mkPen(INK_2))
            right_width = max(tick_fm.horizontalAdvance(text) for _, text in levels) + 14
            axis.setWidth(right_width)
            main.showAxis('right')

        if not any(x.size for x in xs):
            xs = [attempt_x]
        view = self._frame(main, profile, floor, xs, (attempt_x, attempt_y), (sample_x, sample_y))
        if attempt_x.size:
            self._add_marginals(col, items, attempt_x, attempt_y, passing, (left_width, bottom_height, right_width))
        if view is None:
            return
        if floor is not None and not view[1][0] <= floor <= view[1][1]:
            notes.append(f'The Min R² line ({floor:g}) lies outside the default view; zoom out to see it.')
        for x, y, what in ((attempt_x, attempt_y, 'attempts'), (sample_x, sample_y, 'sensitivity samples')):
            outside = (x < view[0][0]) | (x > view[0][1]) | (y < view[1][0]) | (y > view[1][1])
            if not outside.any():
                continue
            all_below = what == 'attempts' and floor is not None and not passing[outside].any()
            (notes if what == 'attempts' else sample_notes).append(
                f'{int(outside.sum())} of {x.size} {what} at {fmt_param(ka_key)}'
                f'{", all below Min R²," if all_below else ""} '
                'lie outside the default view; zoom out to see them.'
            )

    @staticmethod
    def _level_line(main: pg.PlotItem, r2: float, style: Qt.PenStyle, colour: str) -> pg.InfiniteLine:
        """Add a horizontal reference line at *r2* to *main*; its name is on the right-hand axis."""
        line = pg.InfiniteLine(pos=r2, angle=0, pen=pg.mkPen(colour, width=1.5, style=style))
        # Above the sample cloud, below the attempts and the lines.
        line.setZValue(1.5)
        main.addItem(line, ignoreBounds=True)
        return line

    def _add_samples(self, col: int, main: pg.PlotItem, ka_key: str, samples: dict) -> tuple[np.ndarray, np.ndarray]:
        """Draw the sensitivity samples' best fits as a translucent cloud behind the attempts and lines.

        Coloured by the chosen input's offset, with a colour bar; hidden while
        "Show sensitivity samples" is off. Returns the drawn log10 Ka and R².
        """
        legend = self._legend_entries
        ka = np.asarray(samples['ka'][ka_key], dtype=float)
        r2 = samples['r2']
        shown = np.isfinite(ka) & (ka > 0) & (r2 >= 0)
        x, y = np.log10(ka[shown]), r2[shown]
        offsets = samples['offsets']
        visible = self._show_samples.isChecked()
        if offsets is None:
            fill = QColor(SERIES)
            fill.setAlpha(_SAMPLE_ALPHA)
            brushes = pg.mkBrush(fill)
            glyph = f'<span style="color:{_on_surface(SERIES, _SAMPLE_ALPHA)}">&#9679;</span>'
        else:
            off = np.asarray(offsets, dtype=float)[shown]
            reach = float(np.max(np.abs(off))) if off.size else 0.0
            reach = reach or 1.0
            position = (off + reach) / (2.0 * reach)
            brushes = [
                pg.mkBrush(QColor(int(r), int(g), int(b), _COLOURED_SAMPLE_ALPHA))
                for r, g, b, _ in _OFFSET_CMAP.map(position, mode='byte')
            ]
            name = self._colour_combo.currentText()
            cbar = pg.ColorBarItem(
                values=(-reach, reach), colorMap=_OFFSET_CMAP, interactive=False, width=14, pen=INK_3
            )
            tick_font, label_font = self._fonts()
            cbar.axis.setTickFont(tick_font)
            cbar.axis.setTextPen(pg.mkPen(INK_2))
            cbar.axis.setLabel(f'{name} offset [%]', color=INK_2, **{'font-size': f'{label_font.pointSize()}pt'})
            cbar.setVisible(visible)
            ends = ''.join(
                f'<span style="color:{_on_surface(c, _COLOURED_SAMPLE_ALPHA)}">&#9679;</span>'
                for c in (SERIES, '#e34948')
            )
            legend['colour'] = (ends, f'{name} set lower (blue) or higher (red) than entered')
            self._glw.addItem(cbar, row=1, col=col + 2)
            self._items[ka_key]['colour_bar'] = cbar
            glyph = f'<span style="color:{_on_surface(INK_3, _COLOURED_SAMPLE_ALPHA)}">&#9679;</span>'
        scatter = pg.ScatterPlotItem(x=x, y=y, size=_SAMPLE_SIZE, brush=brushes, pen=pg.mkPen(None))
        scatter.setZValue(_SAMPLE_Z)
        scatter.setVisible(visible)
        main.addItem(scatter)
        self._items[ka_key]['samples'] = scatter
        legend['samples'] = (glyph, 'sensitivity sample best fit')
        return x, y

    def _add_marginals(
        self,
        col: int,
        items: dict,
        x: np.ndarray,
        y: np.ndarray,
        passing: np.ndarray,
        axis_sizes: tuple[int, int, int],
    ) -> None:
        """Stacked Ka histogram above and R² histogram to the right of the main plot in *items*, linked to its axes.

        Each counts the attempts in view, in ``_HIST_BINS`` bins across its
        linked axis, recounted whenever that axis's range changes. *axis_sizes*
        are the main plot's left axis width, bottom axis height and right axis
        width (0 when it has none).
        """
        main = items['main']
        left_width, bottom_height, right_width = axis_sizes
        tick_font, _ = self._fonts()
        top = self._glw.addPlot(row=0, col=col, axisItems={'left': _CountAxis('left')})
        right = self._glw.addPlot(row=1, col=col + 1, axisItems={'bottom': _CountAxis('bottom')})
        top.setMinimumHeight(_TOP_HIST_MIN_HEIGHT)
        top.setPreferredHeight(_TOP_HIST_HEIGHT)
        top.setMaximumHeight(_TOP_HIST_HEIGHT)
        right.setMinimumWidth(_RIGHT_HIST_WIDTH)
        right.setMaximumWidth(_RIGHT_HIST_WIDTH)
        top.setXLink(main)
        right.setYLink(main)
        items['marginals'] = (top, right)
        top.hideAxis('bottom')
        right.hideAxis('left')
        # Axes of the main plot's sizes keep the histograms aligned with it.
        top.getAxis('left').setWidth(left_width)
        right.getAxis('bottom').setHeight(bottom_height)
        if right_width:
            top.showAxis('right')
            top.getAxis('right').setStyle(showValues=False)
            top.getAxis('right').setPen(pg.mkPen(None))
            top.getAxis('right').setWidth(right_width)
        # The main plot takes every spare pixel; the marginal cells keep their fixed sizes.
        grid = self._glw.ci.layout
        grid.setRowStretchFactor(1, 1)
        grid.setColumnStretchFactor(col, 1)
        for plot, axis_name, values, vertical, changed in (
            (top, 'left', x, True, top.sigXRangeChanged),
            (right, 'bottom', y, False, right.sigYRangeChanged),
        ):
            count_axis = 'y' if vertical else 'x'
            plot.hideButtons()
            plot.setMenuEnabled(False)
            plot.setMouseEnabled(x=vertical, y=not vertical)
            plot.enableAutoRange(axis=count_axis)
            plot.setAutoVisible(**{count_axis: True})
            plot.showGrid(**{count_axis: True}, alpha=_GRID_ALPHA)
            axis = plot.getAxis(axis_name)
            axis.enableAutoSIPrefix(False)
            axis.setTickFont(tick_font)
            axis.setPen(pg.mkPen(INK_3, width=1))
            axis.setTextPen(pg.mkPen(INK_2))
            axis.setLabel('attempts', color=INK_2, **{'font-size': f'{tick_font.pointSize()}pt'})
            bars = tuple(
                pg.BarGraphItem(x0=[0.0], x1=[0.0], y0=[0.0], y1=[0.0], brush=colour, pen=pg.mkPen(None))
                for colour in (BELOW_FLOOR, INK_2)
            )
            for bar in bars:
                plot.addItem(bar)
            view_range = main.viewRange()[0 if vertical else 1]
            _fill_histogram(bars, values, passing, view_range, vertical)
            # The linked axis follows the main plot's, so its range changes are the main plot's.
            changed.connect(
                lambda _view, rng, bars=bars, values=values, vertical=vertical: _fill_histogram(
                    bars, values, passing, rng, vertical
                )
            )
            items['hist_ka' if vertical else 'hist_r2'] = bars

    def _frame(
        self,
        main: pg.PlotItem,
        profile: ProfileResult | None,
        floor: float | None,
        xs: list[np.ndarray],
        attempts: tuple[np.ndarray, np.ndarray],
        samples: tuple[np.ndarray, np.ndarray],
    ) -> tuple[tuple[float, float], tuple[float, float]] | None:
        """Set the default view and return its (Ka, R²) ranges, Ka in log10 units; ``None`` if nothing to frame.

        Across: the Ka values in *xs*, at least a decade wide. Up and down:
        :func:`_default_r2_range` of the attempts and samples inside that Ka span
        only, with the profile's peak and cut-off and the *floor*.
        """
        x_all = np.concatenate(xs) if xs else np.empty(0)
        if not x_all.size:
            return None
        x_lo, x_hi = float(x_all.min()), float(x_all.max())
        if x_hi - x_lo < 1.0:
            mid = 0.5 * (x_lo + x_hi)
            x_lo, x_hi = mid - 0.5, mid + 0.5
        pad = 0.05 * (x_hi - x_lo)
        x_lo, x_hi = x_lo - pad, x_hi + pad
        in_view = np.concatenate([y[(x >= x_lo) & (x <= x_hi)] for x, y in (attempts, samples)])
        peak, cut = (profile.best_r2, profile.r2_threshold) if profile is not None else (None, None)
        y_lo, y_hi = _default_r2_range(in_view, peak, cut, floor) or (0.0, 1.0)
        main.setLimits(yMin=min(_R2_LIMITS[0], y_lo), yMax=max(_R2_LIMITS[1], y_hi))
        main.setRange(xRange=(x_lo, x_hi), yRange=(y_lo, y_hi), padding=0)
        return (x_lo, x_hi), (y_lo, y_hi)

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------

    def _fonts(self) -> tuple[QFont, QFont]:
        dist = self._style.get('distribution', {})
        tick_font = QFont()
        tick_font.setPointSize(dist.get('tick_font_size', 12))
        label_font = QFont()
        label_font.setPointSize(dist.get('label_font_size', 14))
        return tick_font, label_font

    @staticmethod
    def _style_axes(plot: pg.PlotItem, tick_font: QFont, label_font: QFont) -> None:
        for name in ('left', 'bottom'):
            axis = plot.getAxis(name)
            axis.setTickFont(tick_font)
            axis.label.setFont(label_font)
            axis.setPen(pg.mkPen(INK_3, width=1))
            axis.setTextPen(pg.mkPen(INK_2))
