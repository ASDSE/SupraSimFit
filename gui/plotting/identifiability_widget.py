"""Identifiability view: how well each Ka value explains the data (pyqtgraph).

One panel per binding constant of the fitted model: the profile — the best R²
the model can reach at that Ka with every other parameter free — as a line, the
confidence interval as a band with its R² cut-off as a dotted line, the best fit
marked, and, where the fit ran each replicate separately, every replicate's own
curve. A model with two binding constants adds a third panel: the joint
confidence region of the pair over the two log₁₀ Ka axes, with the best fit
marked and the two single-Ka intervals as faint bands. After a sensitivity run
the best fit of every Sobol' sample joins each Ka panel as a translucent cloud,
optionally coloured by one input's offset.

Where the fit was given an uncertainty for an input, each Ka panel carries a
second curve: what the model reaches at that Ka with every input free to move
within its stated uncertainty. It lies above the first one everywhere — leaving
the inputs as entered is one of the fits it may choose — and the band and the
cut-off drawn are its own, because the interval it implies is the one the fit
reports. The interval at the inputs exactly as entered stays underneath, and
the summary quotes both. The joint region of a pair of binding constants is
drawn at the inputs as entered and is titled that way; a stated random error of
each addition and a noise law the replicates leave uncertain widen it, and its
two bands, as they widen the reported intervals.

The R² axis is linear: for one signal the squared misfit is linear in R², so
equal R² gaps are equal misfit gaps. The peak and the cut-off sit close together
near 1, so the default view frames every peak and cut-off drawn and View All
shows the full range.

Where the replicates showed a noise law (:attr:`~core.pipeline.profile.ProfileSet.weighted`),
that axis is ``1 - S_w / SS_tot,w`` — every titration point counted by the law
the fit was weighted by — which is a different number from the unweighted R² the
fit reports as its quality. The page then calls it ``weighted R²`` everywhere it
names it (:meth:`IdentifiabilityWidget._r2_name`) and says once, in plain words,
what the two names mean.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QEvent, QRectF, QSize, Qt
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
from core.pipeline.fit_pipeline import FitResult
from core.pipeline.input_aware import AwareProfile
from core.pipeline.inputs import TITRANT, ErrorModel
from core.pipeline.profile import JointRegion, ProfileResult, ProfileSet
from core.pipeline.reporting import fit_replica_ids, input_replica_ids, summarize_parameters
from core.pipeline.sensitivity import SensitivityResult
from core.pipeline.varpro import SECOND_STEP_LEVEL, KaInterval
from gui.plotting.colors import INK, INK_2, INK_3, SERIES, SERIES_TOTAL, SURFACE
from gui.plotting.labels import (
    describe_replicates,
    fmt_estimate,
    fmt_interval_html,
    fmt_param,
    fmt_param_plain,
    fmt_r2,
    fmt_unit_html,
    fmt_value,
    one_step_sentence,
    plain_label,
    region_sentence,
    verdict_sentence,
    widening_sentences,
)
from gui.plotting.plot_style import DEFAULT_STYLE
from gui.plotting.sensitivity_widget import _LogKaAxis
from gui.widgets.assay_conditions import condition_fields, result_input_labels

_BAND = (82, 81, 78, 28)
# The input-aware curve, its band, its cut-off and its estimate: one colour for
# the whole reading, so a line, a band and a marker are read together. Orange
# against the ink of the curve at the entered inputs, and never the blue of the
# sensitivity samples underneath.
_AWARE = SERIES_TOTAL
_BAND_AWARE = (235, 104, 52, 34)
# The interval at the entered inputs, where an input-aware one is drawn over it:
# the same ink as _BAND, fainter, so the headline band stays the one that reads.
_BAND_CONDITIONAL = (82, 81, 78, 16)
# A band lies under the curves and is painted faint enough for them to read
# through it; a legend swatch is a character wide and would be invisible at that
# alpha, so it is painted at one the eye resolves in its own colour.
_LEGEND_FILL_ALPHA = 110
# The joint region is drawn over the two single-Ka bands, so it is the same ink
# at an alpha that still reads where a band lies underneath it.
_REGION_FILL = (82, 81, 78, 70)
_GRID_ALPHA = 0.18
# Diverging scale for colouring samples by an input's offset: lower, zero, higher.
# The mid-grey centre stays visible on the surface.
_OFFSET_CMAP = pg.ColorMap(pos=[0.0, 0.5, 1.0], color=[(42, 120, 214), (137, 135, 129), (227, 73, 72)])

_DOT_SIZE = 10
_RING_WIDTH = 2
# The sensitivity samples are a background density layer of up to thousands of
# dots: translucent and without rings, which would form a lattice over the
# lines and markers drawn on top.
_SAMPLE_SIZE = 8
_SAMPLE_ALPHA = 77  # of 255: about 30 %
# Coloured samples are more opaque, so an offset's hue stays readable.
_COLOURED_SAMPLE_ALPHA = 153  # about 60 %
_SAMPLE_Z = 1  # above the band (-10), below every line and marker (2.8 and up)

# Narrowest and shortest a plot's data area may be squeezed, by the sidebar or a
# short window say. Below these the page scrolls instead.
_MAIN_MIN_WIDTH = 240
_MAIN_MIN_HEIGHT = 96
# Smallest R² span the default view separates its levels by, so tick labels
# stay at six decimals or fewer.
_MIN_R2_SPAN = 1e-5
# Share of the Ka span the default view adds on either side. Framed on the
# interval alone the band fills the panel and reads as the background; a fifth
# of its width on each side shows the curve falling below the cut-off outside
# it, which is what makes the band an interval.
_X_PAD = 0.2
# How far the view can be zoomed out: every drawn dot has an R² from 0 to 1.
_R2_LIMITS = (-0.05, 1.05)
# Below this height the chart stops shrinking and the page scrolls.
_CANVAS_MIN_HEIGHT = 320
# Height each row of panels keeps where the panels stand on more than one row:
# a panel with its title, ticks and axis label over a readable data area.
_ROW_MIN_HEIGHT = 220
#: How the panels of a model with two binding constants can stand, widest
#: first: all in one row; the pair on a row of its own below the Ka panels;
#: every panel on a row of its own. :meth:`IdentifiabilityWidget._fit_canvas`
#: takes the first that fits the tab.
_ARRANGEMENTS = ('row', 'pair_below', 'column')
# Qt's "no limit" for a widget dimension (``QWIDGETSIZE_MAX``), which PyQt does
# not export: what a maximum width or height is set back to.
_UNBOUNDED = (1 << 24) - 1

_PLACEHOLDER = 'Run a fit to see how well each Ka value can explain your data.'
_PROFILE_PENDING = 'Working out how well each Ka value can explain the data of this fit…'
_NO_PROFILE = (
    'How well each Ka value can explain the data was not worked out for this fit. Run the fit again to see it.'
)
_READING_POINTER = 'How to read this plot: the ? button above.'

#: What the dotted cut-off is, for the hover text of the axis that names its level.
_CUT_NOTE = 'The dotted line is the cut-off: every Ka whose curve lies above it is inside the interval.'

#: The same, where the line steps down: a fit that holds a signal parameter on
#: its bound gives up that parameter as well as Ka, so the test allows it a
#: larger drop.
_CUT_STEP_NOTE = (
    f'{_CUT_NOTE} Where the fit at a Ka has to hold a signal parameter at its bound, it gives up that '
    'parameter as well as Ka, so the test allows it a larger drop and the line steps down. The level named '
    'here is the one where every signal parameter is free.'
)

#: What the page's own scale is, said once where the replicates showed a noise
#: law. Both numbers are honest and they differ, so the reader is told which
#: question each of them answers rather than left to reconcile them.
_WEIGHTED_R2_NOTE = (
    'Weighted R² counts each titration point by how precise the replicates show it to be; the R² under '
    'Fit Quality counts every point equally.'
)


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


def _default_r2_range(values: np.ndarray, levels: Sequence[float]) -> tuple[float, float]:
    """Default R² span of the view: every level drawn, plus the *values* inside the default Ka span.

    The levels that decide the reading are each drawn profile's best R² and the
    R² an interval is cut at, every step of it inside the default Ka span. The view runs from one level span below the lowest
    of them to 0.6 spans above the highest of them and *values*, never more than
    0.1 span above R² = 1. Values far below the levels stay out of the default
    view, so a few poor sensitivity samples cannot squeeze the levels into a few
    pixels.
    """
    values = values[np.isfinite(values)]
    low, high = min(levels), max(levels)
    span = max(high - low, _MIN_R2_SPAN)
    top = max(high, float(values.max())) if values.size else high
    return low - span, min(top + 0.6 * span, 1.0 + 0.1 * span)


def _same_curve(aware: AwareProfile) -> bool:
    """Whether *aware* is the profile at the entered inputs itself: no input moves, only its cut-off is wider."""
    return aware.offsets.shape[1] == 0


def _aware_peak(aware: AwareProfile) -> tuple[float, float]:
    """The Ka the input-aware profile is best at, and its R² there.

    The curve holds the estimate itself as one of its points, so its highest
    drawn point is the fit's own: no interpolation stands between the marker
    and the reported number.
    """
    index = int(np.nanargmax(aware.r2))
    return float(aware.grid[index]), float(aware.r2[index])


def _log_extent(values: np.ndarray) -> tuple[float, float]:
    """Outer edges, in log₁₀, of the cells a log-spaced grid of *values* stands for.

    The grid holds cell centres, so the drawn map reaches half a cell past the
    first and the last of them.
    """
    logs = np.log10(values)
    half = 0.5 * float(logs[1] - logs[0]) if logs.size > 1 else 0.5
    return float(logs[0]) - half, float(logs[-1]) + half


class _Canvas(pg.GraphicsLayoutWidget):
    """Chart canvas that prefers its minimum height, which :meth:`IdentifiabilityWidget._fit_canvas` sets.

    The scrolling page sizes its word-wrapped content from preferred heights,
    so the canvas takes the height it is given and the text below moves down.
    """

    def sizeHint(self) -> QSize:
        return QSize(super().sizeHint().width(), self.minimumHeight())


class IdentifiabilityWidget(QWidget):
    """The Ka profiles of a fit, their joint region and sensitivity samples on one page.

    :meth:`update_fit` shows a fit and its :class:`ProfileSet`;
    :meth:`update_sensitivity` overlays a :class:`SensitivityResult`;
    :meth:`clear` returns to the placeholder and :meth:`apply_style` restyles.
    :meth:`show_mismatch` hides the fit, or only the sensitivity overlay, behind
    a note while it no longer matches the loaded selection; both are kept and
    drawn again once the note is removed.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._style: dict = dict(DEFAULT_STYLE)
        self._fit: FitResult | None = None
        self._profile: ProfileSet | None = None
        self._profile_pending = False  # the fit's profiles are still being computed
        self._assay_type_name = ''
        self._sensitivity: SensitivityResult | None = None
        self._fit_note: str | None = None  # why the fit is hidden
        self._sensitivity_note: str | None = None  # why the sensitivity overlay is hidden
        self._replica_ids: list[str] | None = None
        self._set_tooltip()
        self._colour_key: str | None = None
        # Drawn items per Ka key, for tests and restyling: main plot, curves, scatters.
        self._items: dict[str, dict] = {}
        # Drawn items of the joint-region panel, empty for a model with one binding constant.
        self._region_items: dict = {}
        # How the panels stand (one of _ARRANGEMENTS; :meth:`_arrange`), and the
        # width the chart needs in each arrangement, measured once per render.
        self._arrangement = 'row'
        self._arrangement_widths: dict[str, int] = {}
        # Width the chart needs with every panel in one row.
        self._row_width = 0
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

    def _panel_widths(self) -> list[float]:
        """Minimum width of each panel of the chart, a colour bar counted with the panel it annotates."""
        widths = []
        for items in self._items.values():
            width = items['main'].effectiveSizeHint(Qt.SizeHint.MinimumSize).width()
            bar = items['colour_bar']
            if bar is not None:
                width += bar.effectiveSizeHint(Qt.SizeHint.MinimumSize).width()
            widths.append(width)
        if self._region_items:
            widths.append(self._region_items['main'].effectiveSizeHint(Qt.SizeHint.MinimumSize).width())
        return widths

    def _chart_width(self) -> int:
        """Width the whole chart needs, every plot's data area at ``_MAIN_MIN_WIDTH``."""
        return int(np.ceil(self._glw.ci.effectiveSizeHint(Qt.SizeHint.MinimumSize).width()))

    def minimumSizeHint(self) -> QSize:
        """Wide enough for the chart's widest single panel; a chart of several panels scrolls sideways.

        This minimum reaches the main window as a floor under its width. A model
        with two binding constants draws three panels, together wider than a
        laptop screen, and asking for all three would grow the window past the
        edge of the screen with no way to shrink it back. So the tab asks for one
        panel with its data area at ``_MAIN_MIN_WIDTH``; :meth:`_fit_canvas`
        stands the panels on more rows where they do not fit side by side, and
        lets the page scroll over whatever is still too wide.
        """
        hint = super().minimumSizeHint()
        if self._stack.currentWidget() is not self._content:
            return hint
        widths = self._panel_widths()
        # What the chart needs beyond the panels themselves — its own margins and
        # the spacing between them — is needed for a single panel just as much.
        around = self._row_width - sum(widths)
        margins = self._content.widget().layout().contentsMargins()
        scrollbar = self._content.verticalScrollBar().sizeHint().width()
        width = int(np.ceil(max(widths, default=0.0) + around)) + margins.left() + margins.right() + scrollbar
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
        shrinks with it, down to the height its own cells need — every plot
        keeps ``_MAIN_MIN_HEIGHT`` of data area under its Ka axis. Only below
        that does the page scroll. The notes are always below the chart. A
        chart on several rows keeps ``_ROW_MIN_HEIGHT`` for each.

        The chart also keeps the width it needs. The panels of a pair of
        binding constants stand in the widest of :data:`_ARRANGEMENTS` that
        fits the tab — the pair below the Ka panels, or every panel on a row of
        its own — so the joint region is in view without scrolling sideways;
        only where even one panel is wider than the tab does the page scroll
        sideways over it rather than squeezing it. The text is held to the
        width of the tab even then: a reader should never have to scroll
        sideways to finish a sentence.
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
        if self._region_items:
            if not self._arrangement_widths:
                for arrangement in _ARRANGEMENTS:
                    self._arrange(arrangement)
                    self._arrangement_widths[arrangement] = self._chart_width()
            widths = self._arrangement_widths
            self._arrange(next((a for a in _ARRANGEMENTS if widths[a] <= width), _ARRANGEMENTS[-1]))
            self._row_width = widths['row']
        else:
            self._row_width = self._chart_width()
        chart_width = self._chart_width()
        if chart_width != self._glw.minimumWidth():
            self._glw.setMinimumWidth(chart_width)
        self._hold_text_to(width if chart_width > width else None)
        above = margins.top() + self._summary.heightForWidth(width) + layout.spacing()
        if not self._controls.isHidden():
            above += self._controls.sizeHint().height() + layout.spacing()
        room = viewport.height() - above
        needed = int(np.ceil(self._glw.ci.effectiveSizeHint(Qt.SizeHint.MinimumSize).height()))
        rows = self._glw.ci.layout.rowCount()
        roomy = max(_CANVAS_MIN_HEIGHT, needed, _ROW_MIN_HEIGHT * rows if rows > 1 else 0)
        with_legend = room - self._legend.heightForWidth(width) - layout.spacing()
        height = with_legend if with_legend >= roomy else min(max(room, needed), roomy)
        if rows > 1:
            height = max(height, _ROW_MIN_HEIGHT * rows)
        if height != self._glw.minimumHeight():
            self._glw.setMinimumHeight(height)

    def _arrange(self, arrangement: str) -> None:
        """Stand the panels of a pair of binding constants as *arrangement* of :data:`_ARRANGEMENTS` says.

        Three panels side by side are wider than a laptop screen, and the one
        that falls off the edge is the pair — the last column, and the one a
        reader is least likely to go looking for behind a scrollbar. On a row
        of its own below the Ka panels it is in view at the full width of the
        page; where even the two Ka panels do not fit side by side, each panel
        takes a row of its own. The page grows downwards, which it scrolls in
        anyway. A Ka panel keeps its colour bar beside it.

        Every panel keeps every curve, band and view range it was drawn with:
        it is moved between cells of the chart's grid, not drawn again.
        """
        if not self._region_items or arrangement == self._arrangement:
            return
        ci = self._glw.ci
        panels = [(items['main'], items['colour_bar']) for items in self._items.values()]
        region = self._region_items['main']
        for main, bar in panels:
            ci.removeItem(main)
            if bar is not None:
                ci.removeItem(bar)
        ci.removeItem(region)
        # A column left behind takes no share of the width, or it would hold an
        # empty gap as wide as a panel.
        for col in range(2 * len(panels) + 1):
            ci.layout.setColumnStretchFactor(col, 0)
        if arrangement == 'column':
            for row, (main, bar) in enumerate(panels):
                ci.addItem(main, row=row, col=0)
                if bar is not None:
                    ci.addItem(bar, row=row, col=1)
            ci.addItem(region, row=len(panels), col=0)
            ci.layout.setColumnStretchFactor(0, 1)
        else:
            for index, (main, bar) in enumerate(panels):
                ci.addItem(main, row=0, col=2 * index)
                ci.layout.setColumnStretchFactor(2 * index, 1)
                if bar is not None:
                    ci.addItem(bar, row=0, col=2 * index + 1)
            if arrangement == 'row':
                ci.addItem(region, row=0, col=2 * len(panels))
                ci.layout.setColumnStretchFactor(2 * len(panels), 1)
            else:
                ci.addItem(region, row=1, col=0, colspan=2 * len(panels))
        self._arrangement = arrangement

    def _hold_text_to(self, width: int | None) -> None:
        """Hold the page's text to *width*; ``None`` lets it take the width the page gives it.

        A chart wider than the tab widens the page under it, and a sentence that
        ran the width of that page could not be read without scrolling sideways.
        A layout asks a label how tall it is at the width of the page, not at the
        width the label is held to, so a held label is given the height its own
        width needs as well.
        """
        for label in (self._summary, self._legend, self._notes):
            if width is None:
                label.setMinimumSize(0, 0)
                label.setMaximumSize(_UNBOUNDED, _UNBOUNDED)
            else:
                label.setFixedWidth(width)
                label.setFixedHeight(label.heightForWidth(width))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_fit(self, fit_result: FitResult, profile: ProfileSet | None, assay_type_name: str) -> None:
        """Show *fit_result* with the *profile* of every binding constant it fitted.

        *profile* is ``None`` for an assay without a binding constant, or when
        the profiles could not be computed.
        """
        self._fit = fit_result
        self._profile = profile
        self._profile_pending = False
        self._assay_type_name = assay_type_name
        self._render()

    def show_profile_pending(self, fit_result: FitResult, assay_type_name: str) -> None:
        """Hold *fit_result* and say its Ka profiles are being computed, until :meth:`update_fit` brings them.

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
        """Drop the fit, profiles and sensitivity overlay and show the placeholder."""
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

    def _r2_name(self) -> str:
        """What this page calls its vertical scale, wherever it names it.

        Where the replicates showed a noise law, every curve, cut-off and level
        here is ``1 - S_w / SS_tot,w``: each titration point counted by that
        law. That is a different number from the unweighted R² the fit reports
        as its quality, so the page never calls the two by one name.
        """
        return 'weighted R²' if self._profile is not None and self._profile.weighted else 'R²'

    def _set_tooltip(self) -> None:
        """The hover text of the page, which names the scale the line and the band are read on."""
        name = self._r2_name()
        self.setToolTip(
            f'<qt>The line is the best {name} any fit can reach at each K<sub>a</sub>; the shaded band is '
            'the range of K<sub>a</sub> the data support.<br>Where you stated an uncertainty for an input, '
            'a second line and band show what the data support once the inputs may move within it.'
            '<br>With two binding constants the last panel shows which pairs of them the data support '
            'together, at the inputs as entered.<br>Scroll to zoom, drag to pan, right-click for the '
            'full view.</qt>'
        )

    def _show_message(self, text: str) -> None:
        self._message.setText(text)
        self._stack.setCurrentWidget(self._message)
        self.updateGeometry()

    def _render(self) -> None:
        """Rebuild the page from the stored fit, profiles and sensitivity result."""
        self._set_tooltip()
        self._glw.clear()
        self._items = {}
        self._region_items = {}
        self._arrangement = 'row'
        self._arrangement_widths = {}
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
        if self._profile is None:
            self._show_message(_NO_PROFILE)
            return

        profiles = self._profile.profiles
        notes: list[str] = []
        # Notes about the drawn sensitivity samples, shown only while the samples are.
        sample_notes: list[str] = []
        samples = self._samples(notes, sample_notes)
        self._controls.setVisible(samples is not None)
        self._sync_colour_control()
        self._replicate_notes(self._fit, samples is not None, notes, sample_notes)

        summary = []
        # Which end of its search box each estimate sits on, if any: the
        # headline's, and the one at the entered inputs where the two differ.
        at_bound = {
            spec.key: (spec.estimate_at_bound, spec.conditional_at_bound)
            for spec in summarize_parameters(self._fit)
            if not spec.is_log
        }
        for index, ka_key in enumerate(ka_keys):
            profile = profiles[ka_key]
            unit_html = fmt_unit_html(meta.units.get(ka_key, ''))
            self._render_key(2 * index, ka_key, unit_html, profile, samples, notes, sample_notes)
            summary.append(self._summary_line(ka_key, unit_html, profile, *at_bound.get(ka_key, ('', ''))))
        drawn = [profiles[key] for key in ka_keys]
        if any(profile.interval is not None for profile in drawn):
            summary.append(self._interval_note(drawn))
        if self._profile.weighted:
            # The page says once which of the two R² the reader is looking at:
            # the panels name it, this says what the name means.
            summary.append(f'<span style="color:{INK_2}">{_WEIGHTED_R2_NOTE}</span>')
        if self._profile.region is not None:
            self._render_region(2 * len(ka_keys), meta, self._profile.region, profiles)
            if any(profile.aware is not None and not _same_curve(profile.aware) for profile in profiles.values()):
                notes.append(
                    'The panel of the pair takes the entered inputs as exact. The uncertainties you stated for '
                    "them widen each binding constant's own interval, in the panels beside it."
                )
            widened = None if self._fit is None else region_sentence(self._fit)
            if widened:
                notes.append(f'{widened} Its two bands are the intervals at the entered inputs, widened alike.')
        # What the fit found out about the model and the entered inputs, in the
        # words the summary table and the report use.
        verdict = self._verdict_html()
        if verdict:
            summary.append(verdict)

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
            where = 'of the curves and the sensitivity samples' if same_run else 'here'
            notes.append(
                f'{names[0].upper()}{names[1:]} {"are" if many else "is"} left out {where}, '
                f'as {"they were" if many else "it was"} from the fit.'
            )
        if run_used is not None and used is not None and set(run_used) != set(used):
            sample_notes.append(
                f'The sensitivity run used {describe_replicates(run_used, self._replica_ids)}, but this fit used '
                f'{describe_replicates(used, self._replica_ids)}, so the samples describe other replicates than '
                'the curves.'
            )

    def _samples(self, notes: list[str], sample_notes: list[str]) -> dict | None:
        """The sensitivity run's sample best fits, when they can be compared with this fit.

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
        # The samples are drawn against the profiles, so they are read on the
        # profiles' own scale, not on the unweighted R² the fit reports.
        r2 = np.asarray(result.sample_profile_r2, dtype=float)
        hidden = int(np.sum(~(r2 >= 0)))
        if hidden:
            sample_notes.append(
                f'{hidden} of {r2.size} sensitivity samples not shown: no fit could be made, or it fit worse '
                f'than a flat line ({self._r2_name()} &lt; 0).'
            )
        offsets = result.sample_offsets_pct.get(self._colour_key) if self._colour_key is not None else None
        return {'ka': result.sample_ka, 'r2': r2, 'offsets': offsets}

    def _verdict_html(self) -> str:
        """What the fit found out about the model and the entered inputs, or nothing where it tested neither.

        The inputs are named from the fit's own assay, so this tab and the
        exported report name the same fit's inputs alike.
        """
        diagnostics = self._fit.diagnostics
        if diagnostics is None:
            return ''
        labels = result_input_labels(self._fit.assay_type, self._fit.fit_config)
        return verdict_sentence(diagnostics, self._fit.input_shifts, labels, html=True)

    def _interval_note(self, profiles: list[ProfileResult]) -> str:
        """The grey line under the per-Ka blocks: what every interval of this fit rests on.

        The point and parameter counts are the fit's own projection's and the
        bounds are the fit's, so they hold for every binding constant alike and
        are said once for the fit. Where a design effect widens a cut-off — a
        noise law the replicates leave uncertain, a stated random error of each
        addition — the counts alone no longer give it, and the sentences of
        :func:`~gui.plotting.labels.widening_sentences` say by how much. A
        stated error of the additions is said to be allowed for, not to widen
        the interval: where the noise law widens it already, the interval that
        allows for both need not be the wider of the two.
        """
        counts = f'{_count(profiles[0].n_points, "data point")} and {_count(profiles[0].n_params, "fitted parameter")}'
        moved = any(profile.aware is not None and not _same_curve(profile.aware) for profile in profiles)
        additions = ErrorModel.from_dict(self._fit.fit_config or {}).additions if self._fit is not None else None
        allowed = 'the reported interval allows for the random error of each addition you stated'
        if moved:
            text = (
                'Each input with a stated uncertainty was free to move within the uncertainty you stated for it, '
                'which usually widens the interval'
                + (f', and {allowed}' if additions else '')
                + f'. Each interval at the entered inputs is worked out from {counts}, and no '
                'interval reaches further than the parameter bounds this fit was given.'
            )
        elif any(profile.aware is not None for profile in profiles):
            # No input moved: what the reported interval adds is the stated error of each addition.
            text = (
                f'{allowed[0].upper()}{allowed[1:]}, on the same curve; the interval without it is given beside it. '
                f'Each interval is worked out from {counts}, and no interval reaches further than the parameter '
                'bounds this fit was given.'
            )
        else:
            text = (
                f'Each interval is worked out from {counts}, and reaches no further than the parameter bounds '
                'this fit was given.'
            )
        if self._fit is not None:
            rows = summarize_parameters(self._fit)
            text = ' '.join([text, *widening_sentences(rows, self._fit, fmt_param)])
        return f'<span style="color:{INK_2}">{text}</span>'

    def _summary_line(
        self, ka_key: str, unit_html: str, profile: ProfileResult, headline_bound: str, conditional_bound: str
    ) -> str:
        """One block per Ka key: the reported estimate and interval, and how far it reaches.

        Where the fit was given an uncertainty for an input, the block leads
        with the interval that allows for them — the one the fit reports — and
        the reading at the inputs exactly as entered follows it. What both rest
        on is in :meth:`_interval_note`, once for the fit. An open side names
        what it stops at — the bound, the Ka the binding model cannot be solved
        past, or the Ka beyond which only the bound of the other binding
        constant rejects the fit — and says what would pin it down.

        *headline_bound* and *conditional_bound* say which end of its search box
        the reported and the conditional estimate sit on (``''`` for neither,
        ``'low'`` or ``'high'``): such an estimate is the box, not a measurement,
        and reads as the limit the data do set.
        """
        label = fmt_param(ka_key)
        average = " of the replicates' average" if profile.per_replica else ''
        interval = profile.interval
        conditional_bound = conditional_bound if profile.aware is not None else headline_bound
        best_txt = self._estimate_html(profile.best_ka, interval, unit_html, conditional_bound)
        fit_txt = f'best fit{average} {best_txt} ({self._r2_name()} {fmt_r2(profile.best_r2)})'
        if interval is None:
            return (
                f'{label}: {fit_txt}<br><span style="color:{INK_2}">{label} is fixed at {best_txt} by its '
                'bounds, so there is no interval.</span>'
            )
        conditional = self._ci_html(interval, profile.best_ka, unit_html, bool(conditional_bound))
        if profile.aware is None:
            return f'{label}: {fit_txt} · {conditional}{self._reach_html(interval, unit_html, label)}'
        estimate, _ = _aware_peak(profile.aware)
        aware = profile.aware.interval
        estimate_txt = self._estimate_html(estimate, aware, unit_html, headline_bound)
        # No input moved where the aware reading is the same curve: only the
        # stated error of the additions sets the two intervals apart.
        beside = (
            'Without the error of the additions' if _same_curve(profile.aware) else 'Conditional on the entered inputs'
        )
        # The joint region is drawn at the entered inputs, so the one-step test
        # at them is said beside their interval as well as the headline's.
        entered_step = (
            ''
            if interval.one_step_p is None
            else f'<br><span style="color:{INK_2}">At the entered inputs, '
            f'{one_step_sentence(label, interval.one_step_p)}</span>'
        )
        return (
            f'{label}: best fit{average} {estimate_txt} · {self._ci_html(aware, estimate, unit_html, bool(headline_bound))}'
            f'{self._reach_html(aware, unit_html, label)}'
            f'<br>{beside}: {fit_txt} · {conditional}{entered_step}'
        )

    @staticmethod
    def _estimate_html(estimate: float, interval: KaInterval | None, unit_html: str, at_bound: str) -> str:
        """``1.71×10⁸ M⁻¹``, or in words where the estimate sits on an end of its search box."""
        bounds = None if interval is None else (interval.low, interval.high)
        opens = (False, False) if interval is None else (interval.open_low, interval.open_high)
        text = fmt_estimate(estimate, at_bound, bounds, opens, html=True)
        # The unit follows a number; words with no number hold none.
        return text if at_bound and (interval is None or all(opens)) else f'{text} {unit_html}'.strip()

    @staticmethod
    def _ci_html(interval: KaInterval, estimate: float, unit_html: str, at_bound: bool = False) -> str:
        """``95% CI [1.30×10⁸, 1.90×10⁸] M⁻¹ (−31% / +52%)``: the interval and how far each closed end lies.

        The ends are written by :func:`~gui.plotting.labels.fmt_value`, as the
        summary table, the plot annotation and the report write them. How far
        an end lies is a percentage of the estimate, which an estimate on an
        end of its search box (*at_bound*) is not: there it is left out.
        """
        lo, hi = interval.low, interval.high
        lo_open, hi_open = interval.open_low, interval.open_high
        # The unit follows the bracket, and is left off one holding no number.
        ci_txt = fmt_interval_html(fmt_value(lo), fmt_value(hi), lo_open, hi_open)
        if not (lo_open and hi_open):
            ci_txt = f'{ci_txt} {unit_html}'.strip()
        # How far from the estimate each end the data close lies. An open end is
        # no distance from it, so the end that is closed is named instead.
        closed = [
            (side, _pct(edge / estimate))
            for edge, is_open, side in ((lo, lo_open, 'lower end'), (hi, hi_open, 'upper end'))
            if not is_open and not at_bound
        ]
        if len(closed) == 2:
            change = f' ({closed[0][1]} / {closed[1][1]})'
        else:
            change = f' ({closed[0][0]} {closed[0][1]})' if closed else ''
        return f'{interval.level:.0%} CI {ci_txt}{change}'

    @staticmethod
    def _reach_html(interval: KaInterval, unit_html: str, label: str) -> str:
        """What an interval spans, what each open side stops at, and what the one-step test of *label* found.

        The span is said where the interval is not one connected stretch, and
        the one-step test only for the second constant of a two-step model,
        the one interval that carries it. A lower side the one-step test opened
        is said by the test's sentence, which names why it is open: the bound
        it then runs to is not a reach of the data.
        """
        line = ''
        step_unshown = interval.one_step_p is not None and interval.one_step_p > SECOND_STEP_LEVEL
        if interval.split:
            line += (
                f'<br><span style="color:{INK_2}">Not every K<sub>a</sub> inside the band explains the data well '
                'enough: the ones that do come in separate stretches, and the band spans all of them. The line '
                'shows where they are.</span>'
            )
        lo, hi = interval.low, interval.high
        for is_open, unsolvable, limited_by, side, edge, advice in (
            (
                interval.open_low,
                interval.unsolvable_low,
                interval.limited_by_low,
                'lower',
                lo,
                'Points at a higher titrant concentration would pin it down.',
            ),
            (
                interval.open_high,
                interval.unsolvable_high,
                interval.limited_by_high,
                'higher',
                hi,
                'Points taken before the signal levels off, or a lower fixed concentration, would pin it down.',
            ),
        ):
            if not is_open or (side == 'lower' and step_unshown):
                continue
            where = f'{fmt_value(edge)} {unit_html}'.strip()
            if limited_by:
                # The crossing is a property of the other constant's bound, so
                # it is named with its value and not given as a limit.
                other = fmt_param(limited_by)
                tail = (
                    f'The fit is rejected beyond {where} only because {other} cannot go past its bound there. If you '
                    f'know {other}, hold it at that value under Parameter Bounds (equal lower and upper bound); '
                    'otherwise only data that determine it close this side.'
                )
            elif unsolvable:
                # The edge is where the arithmetic stops, not where the data do,
                # so more measurements cannot move it and the advice would be wrong.
                tail = (
                    f'The binding model cannot be solved past {where}, so the curve stops there, short of the '
                    'bound this fit was given. More measurements cannot close this side.'
                )
            else:
                tail = f'It reaches the bound of {where}. {advice}'
            line += (
                f'<br><span style="color:{INK_2}">Open: the data cannot rule out a {side} K<sub>a</sub>. {tail}</span>'
            )
        if interval.one_step_p is not None:
            line += f'<br><span style="color:{INK_2}">{one_step_sentence(label, interval.one_step_p)}</span>'
        return line

    def _render_key(
        self,
        col: int,
        ka_key: str,
        unit_html: str,
        profile: ProfileResult,
        samples: dict | None,
        notes: list[str],
        sample_notes: list[str],
    ) -> None:
        """Draw one binding constant's panel: its profile, interval band, cut-off, best fit and sample cloud."""
        legend = self._legend_entries
        tick_font, label_font = self._fonts()
        tick_fm, label_fm = QFontMetrics(tick_font), QFontMetrics(label_font)
        left_width = tick_fm.horizontalAdvance('0.999999') + label_fm.height() + 16
        bottom_height = tick_fm.height() + label_fm.height() + 16

        main = self._glw.addPlot(row=0, col=col, axisItems={'bottom': _LogKaAxis('bottom')})
        main.getAxis('bottom').setLogMode(True)
        for name in ('left', 'bottom'):
            main.getAxis(name).enableAutoSIPrefix(False)
        main.getViewBox().setMinimumSize(_MAIN_MIN_WIDTH, _MAIN_MIN_HEIGHT)
        main.setLabel('left', self._r2_name())
        main.setLabel('bottom', f'{fmt_param(ka_key)} [{unit_html}]' if unit_html else fmt_param(ka_key))
        main.showGrid(x=True, y=True, alpha=_GRID_ALPHA)
        self._style_axes(main, tick_font, label_font)
        main.getAxis('left').setWidth(left_width)
        main.getAxis('bottom').setHeight(bottom_height)
        # The plots share every spare pixel; a colour bar keeps its own width.
        self._glw.ci.layout.setColumnStretchFactor(col, 1)
        items: dict = {
            'main': main,
            'average': None,
            'aware': None,
            'replicas': [],
            'band': None,
            'aware_band': None,
            'cut': None,
            'aware_cut': None,
            'best': None,
            'aware_best': None,
            'samples': None,
            'colour_bar': None,
        }
        self._items[ka_key] = items
        aware = profile.aware
        # The reported reading on this same curve, under the wider cut-off the
        # stated error of the additions implies: one curve and one best fit.
        same_curve = aware is not None and _same_curve(aware)
        log_best = float(np.log10(profile.best_ka))
        xs: list[np.ndarray] = [np.array([log_best])]
        sample_x = sample_y = np.empty(0)

        log_grid = np.log10(profile.grid)
        interval = profile.interval
        if interval is not None:
            lo, hi = np.log10([interval.low, interval.high])
            # With an input-aware interval over it, this one is the reading at
            # the inputs as entered: fainter, and underneath.
            fill = _BAND if aware is None else _BAND_CONDITIONAL
            band = pg.LinearRegionItem(values=(lo, hi), movable=False, brush=pg.mkBrush(*fill), pen=pg.mkPen(None))
            band.setZValue(-10 if aware is None else -11)
            main.addItem(band)
            items['band'] = band
            legend['band'] = (
                f'<span style="color:{_on_surface(INK_2, _LEGEND_FILL_ALPHA)}">&#9608;</span>',
                f'{interval.level:.0%} confidence interval'
                if aware is None
                else f'{interval.level:.0%} CI '
                + ('without the error of the additions' if same_curve else 'at the entered inputs'),
            )
            xs.append(np.array([lo, hi]))
        if aware is not None:
            lo, hi = np.log10([aware.interval.low, aware.interval.high])
            band = pg.LinearRegionItem(
                values=(lo, hi), movable=False, brush=pg.mkBrush(*_BAND_AWARE), pen=pg.mkPen(None)
            )
            band.setZValue(-10)
            main.addItem(band)
            items['aware_band'] = band
            legend['aware_band'] = (
                f'<span style="color:{_on_surface(_AWARE, _LEGEND_FILL_ALPHA)}">&#9608;</span>',
                f'{aware.interval.level:.0%} confidence interval'
                + (' with the error of the additions' if same_curve else ''),
            )
            xs.append(np.array([lo, hi]))
        for r2 in (profile.replica_r2 or {}).values():
            curve = main.plot(log_grid, r2, pen=pg.mkPen(INK_3, width=1), connect='finite', antialias=True)
            curve.setZValue(2.8)
            items['replicas'].append(curve)
        if profile.replica_r2:
            legend['replicas'] = (f'<span style="color:{INK_3}">&#9472;</span>', 'each replicate on its own')
        # A Ka the binding model cannot be solved at carries nan: the line
        # breaks there instead of stepping across the gap.
        items['average'] = main.plot(log_grid, profile.r2, pen=pg.mkPen(INK, width=2), connect='finite', antialias=True)
        items['average'].setZValue(3)
        entered = ' with the inputs as entered' if aware is not None and not same_curve else ''
        legend['profile'] = (
            f'<span style="color:{INK}">&#9473;</span>',
            f'best {self._r2_name()} reachable at each K<sub>a</sub>'
            + (" on the replicates' average" if profile.per_replica else '')
            + entered,
        )
        if aware is not None and not same_curve:
            items['aware'] = main.plot(
                np.log10(aware.grid), aware.r2, pen=pg.mkPen(_AWARE, width=2), connect='finite', antialias=True
            )
            # Over the curve at the entered inputs, which it never falls below.
            items['aware'].setZValue(3.2)
            legend['aware'] = (
                f'<span style="color:{_AWARE}">&#9473;</span>',
                'the same with input uncertainties',
            )
        # The band spans the Ka values where its own line is above this cut-off;
        # the reading the fit reports is the input-aware one where there is one.
        cut_profile = aware if aware is not None else profile
        if aware is not None or interval is not None:
            key = 'aware_cut' if aware is not None else 'cut'
            colour = _AWARE if aware is not None else INK
            items[key] = self._cut_line(main, np.log10(cut_profile.grid), cut_profile.r2_cut, colour)
            # The axis names the level the line sits at wherever the fit holds
            # every signal parameter free. Where the line steps down too — the
            # fit pins a signal parameter at its bound there — the legend and
            # the axis's hover text say what the step is.
            cuts = np.asarray(cut_profile.r2_cut, dtype=float)
            stepped = np.unique(cuts[np.isfinite(cuts)]).size > 1
            label = f'cut-off {fmt_r2(cut_profile.r2_threshold)}'
            axis = main.getAxis('right')
            axis.setTicks([[(cut_profile.r2_threshold, label)]])
            axis.setTickFont(tick_font)
            axis.setPen(pg.mkPen(INK_3, width=1))
            axis.setTextPen(pg.mkPen(INK_2))
            axis.setWidth(tick_fm.horizontalAdvance(label) + 14)
            axis.setToolTip(_CUT_STEP_NOTE if stepped else _CUT_NOTE)
            main.showAxis('right')
            level = (aware.interval if aware is not None else interval).level
            text = f'{level:.0%} CI cut-off' + ('; lower where a signal parameter sits on its bound' if stepped else '')
            legend[key] = (f'<span style="color:{colour}">&#8943;</span>', text)
        items['best'] = self._best_marker(main, log_best, profile.best_r2)
        legend['best'] = (
            f'<span style="color:{INK}">&#9670;</span>',
            'best fit' if aware is None or same_curve else 'best fit at the entered inputs',
        )
        if aware is not None and not same_curve:
            estimate, estimate_r2 = _aware_peak(aware)
            log_estimate = float(np.log10(estimate))
            items['aware_best'] = self._best_marker(main, log_estimate, estimate_r2, _AWARE)
            xs.append(np.array([log_estimate]))
            legend['aware_best'] = (f'<span style="color:{_AWARE}">&#9670;</span>', 'best fit reported')

        if samples is not None and ka_key in samples['ka']:
            sample_x, sample_y = self._add_samples(col, main, ka_key, samples)
            xs.append(sample_x)

        view = self._frame(main, profile, log_grid, xs, (sample_x, sample_y))
        outside = (sample_x < view[0][0]) | (sample_x > view[0][1]) | (sample_y < view[1][0]) | (sample_y > view[1][1])
        if outside.any():
            sample_notes.append(
                f'{int(outside.sum())} of {sample_x.size} sensitivity samples at {fmt_param(ka_key)} '
                'lie outside the default view; zoom out to see them.'
            )
        # A replicate whose own profile peaks well below the cut-off is drawn
        # off the default view, which frames the peak and the cut-off. The
        # legend names its curve, so the note says where it went.
        replica_r2 = profile.replica_r2 or {}
        if replica_r2:
            (y_lo, y_hi), inside_x = view[1], (log_grid >= view[0][0]) & (log_grid <= view[0][1])
            hidden = sum(not np.any((r2 >= y_lo) & (r2 <= y_hi) & inside_x) for r2 in replica_r2.values())
            if hidden:
                notes.append(
                    f'{hidden} of {len(replica_r2)} replicate curves at {fmt_param(ka_key)} lie outside the '
                    'default view; zoom out to see them.'
                )

    def _render_region(self, col: int, meta, region: JointRegion, profiles: dict[str, ProfileResult]) -> None:
        """Draw the joint confidence region of the two binding constants, with the best fit and the two intervals."""
        legend = self._legend_entries
        tick_font, label_font = self._fonts()
        k1, k2 = region.ka_keys
        plot = self._glw.addPlot(row=0, col=col, axisItems={n: _LogKaAxis(n) for n in ('bottom', 'left')})
        for name in ('left', 'bottom'):
            axis = plot.getAxis(name)
            axis.setLogMode(True)
            axis.enableAutoSIPrefix(False)
        plot.getViewBox().setMinimumSize(_MAIN_MIN_WIDTH, _MAIN_MIN_HEIGHT)
        for name, key in (('bottom', k1), ('left', k2)):
            unit_html = fmt_unit_html(meta.units.get(key, ''))
            plot.setLabel(name, f'{fmt_param(key)} [{unit_html}]' if unit_html else fmt_param(key))
        plot.showGrid(x=True, y=True, alpha=_GRID_ALPHA)
        self._style_axes(plot, tick_font, label_font)
        # Room for the widest tick and the axis title, as the Ka panels have, so
        # neither is cut off whichever row the panel stands on.
        tick_fm, label_fm = QFontMetrics(tick_font), QFontMetrics(label_font)
        # The widest tick a log Ka axis writes is a mantissa over a negative exponent.
        plot.getAxis('left').setWidth(tick_fm.horizontalAdvance('8×10⁻¹²') + label_fm.height() + 16)
        plot.getAxis('bottom').setHeight(tick_fm.height() + label_fm.height() + 16)
        self._glw.ci.layout.setColumnStretchFactor(col, 1)
        if any(profile.aware is not None for profile in profiles.values()):
            # The panels beside this one carry two readings each; this one is
            # the pair at the inputs as entered, and is named that way.
            plot.setTitle('At the entered inputs', color=INK_2, size=f'{label_font.pointSize()}pt')

        # The two single-Ka intervals at the region's own footing, behind the
        # region and in the same grey as the bands of the panels beside it: each
        # of them is what that Ka alone is held to while the other one is free.
        bands = []
        for key, orientation in ((k1, 'vertical'), (k2, 'horizontal')):
            interval = region.intervals.get(key, profiles[key].interval)
            if interval is None:
                continue
            band = pg.LinearRegionItem(
                values=np.log10([interval.low, interval.high]),
                orientation=orientation,
                movable=False,
                brush=pg.mkBrush(*_BAND),
                pen=pg.mkPen(None),
            )
            band.setZValue(-10)
            plot.addItem(band)
            bands.append(band)

        inside = np.isfinite(region.r2) & (region.r2 >= region.r2_cut)
        rgba = np.zeros(inside.shape + (4,), dtype=np.ubyte)
        rgba[inside] = _REGION_FILL
        # Explicit levels: left to scale itself, an image whose largest byte is
        # the fill's alpha is stretched to full brightness and the region paints
        # white instead of grey.
        image = pg.ImageItem(rgba, axisOrder='col-major', levels=(0, 255))
        x_lo, x_hi = _log_extent(region.x)
        y_lo, y_hi = _log_extent(region.y)
        image.setRect(QRectF(x_lo, y_lo, x_hi - x_lo, y_hi - y_lo))
        image.setZValue(-5)
        plot.addItem(image)
        legend['region'] = (
            f'<span style="color:{_on_surface(INK_2, _REGION_FILL[3])}">&#9608;</span>',
            f'{region.level:.0%} region for the pair',
        )

        best = self._best_marker(plot, float(np.log10(region.best[0])), float(np.log10(region.best[1])))
        plot.setRange(xRange=(x_lo, x_hi), yRange=(y_lo, y_hi), padding=0.02)
        self._region_items = {'main': plot, 'region': image, 'best': best, 'bands': bands}

    @staticmethod
    def _cut_line(main: pg.PlotItem, log_grid: np.ndarray, r2_cut: np.ndarray, colour: str = INK) -> pg.PlotDataItem:
        """Add the dotted cut-off line to *main* in *colour*; its name is on the right-hand axis.

        The cut-off holds one level per profile point and steps, midway between
        two points, where the fit starts to hold a signal parameter on its bound.
        """
        steps = np.concatenate([log_grid[:1], 0.5 * (log_grid[:-1] + log_grid[1:]), log_grid[-1:]])
        line = pg.PlotDataItem(
            steps, r2_cut, stepMode='center', pen=pg.mkPen(colour, width=1.5, style=Qt.PenStyle.DotLine)
        )
        # Above the sample cloud, below the curves and the best-fit marker.
        line.setZValue(1.5)
        main.addItem(line, ignoreBounds=True)
        return line

    @staticmethod
    def _best_marker(plot: pg.PlotItem, x: float, y: float, colour: str = INK) -> pg.ScatterPlotItem:
        """Mark the best fit at *(x, y)* in *colour*, above every curve and cloud."""
        marker = pg.ScatterPlotItem(
            x=[x],
            y=[y],
            symbol='d',
            size=_DOT_SIZE,
            brush=pg.mkBrush(colour),
            pen=pg.mkPen(SURFACE, width=_RING_WIDTH),
        )
        marker.setZValue(4)
        plot.addItem(marker)
        return marker

    def _add_samples(self, col: int, main: pg.PlotItem, ka_key: str, samples: dict) -> tuple[np.ndarray, np.ndarray]:
        """Draw the sensitivity samples' best fits as a translucent cloud behind the curves and markers.

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
            self._glw.addItem(cbar, row=0, col=col + 1)
            self._items[ka_key]['colour_bar'] = cbar
            glyph = f'<span style="color:{_on_surface(INK_3, _COLOURED_SAMPLE_ALPHA)}">&#9679;</span>'
        scatter = pg.ScatterPlotItem(x=x, y=y, size=_SAMPLE_SIZE, brush=brushes, pen=pg.mkPen(None))
        scatter.setZValue(_SAMPLE_Z)
        scatter.setVisible(visible)
        main.addItem(scatter)
        self._items[ka_key]['samples'] = scatter
        legend['samples'] = (glyph, 'sensitivity sample best fit')
        return x, y

    def _frame(
        self,
        main: pg.PlotItem,
        profile: ProfileResult,
        log_grid: np.ndarray,
        xs: list[np.ndarray],
        samples: tuple[np.ndarray, np.ndarray],
    ) -> tuple[tuple[float, float], tuple[float, float]]:
        """Set the default view and return its (Ka, R²) ranges, Ka in log10 units.

        Across: the Ka values in *xs* — every estimate and interval drawn, and
        the sensitivity samples — at least a decade wide, with ``_X_PAD`` of
        that span on either side so an interval reads as a band with the curve
        falling away outside it. The padding stops at the ends of *log_grid*,
        the drawn curve, which leaves no empty margin where the interval
        already spans the Ka bounds. Up and down: :func:`_default_r2_range` of
        every peak and cut-off drawn with the sample R² inside that Ka span.
        """
        x_all = np.concatenate(xs)
        x_lo, x_hi = float(x_all.min()), float(x_all.max())
        if x_hi - x_lo < 1.0:
            mid = 0.5 * (x_lo + x_hi)
            x_lo, x_hi = mid - 0.5, mid + 0.5
        pad = _X_PAD * (x_hi - x_lo)
        # Never past the drawn curve, and never inside anything xs asked for.
        x_lo = max(x_lo - pad, min(float(log_grid[0]), x_lo))
        x_hi = min(x_hi + pad, max(float(log_grid[-1]), x_hi))
        sample_x, sample_y = samples
        in_view = sample_y[(sample_x >= x_lo) & (sample_x <= x_hi)]
        levels = [profile.best_r2, profile.r2_threshold]
        if profile.aware is not None:
            levels += [_aware_peak(profile.aware)[1], profile.aware.r2_threshold]
        # The cut-off steps down where the fit pins a signal parameter; the view holds every step inside its Ka span.
        for curve in (profile, profile.aware):
            if curve is not None:
                logs = np.log10(curve.grid)
                levels += curve.r2_cut[(logs >= x_lo) & (logs <= x_hi)].tolist()
        y_lo, y_hi = _default_r2_range(in_view, levels)
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
