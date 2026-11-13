"""The summary of a sensitivity run's samples, under the plots of Sensitivity.

Each sample of a Sobol' run refits the data with the inputs moved within their stated
uncertainty; this table summarises the fitted parameters across the samples that have a
fit, around the run's own fit with the inputs as entered, and says how that fit relates
to the one Fit results reports. Rows come from
:func:`~core.pipeline.reporting.summarize_parameters`, as every report's do.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import numpy as np
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QTextDocument
from PyQt6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from core.optimizer.ensemble import describe, describe_log10
from core.pipeline.fit_pipeline import FitResult
from core.pipeline.reporting import ParameterSummary, fit_replica_ids, input_replica_ids, summarize_parameters
from core.pipeline.sensitivity import SensitivityMode, SensitivityResult
from gui.plotting.colors import INK_2
from gui.plotting.labels import (
    and_join,
    describe_replicates,
    fmt_log10,
    fmt_param,
    fmt_r2,
    fmt_unit_html,
    fmt_value,
)
from gui.results import degenerate_note
from gui.widgets.assay_conditions import same_inputs
from gui.widgets.info_button import InfoGroupBox

_SAMPLES_QUALITY_HELP_HTML = """
<h3>Fit Quality &mdash; across the samples</h3>

<p><b>Samples with a fit</b> &mdash; how many of the analysis&rsquo;s samples
produced a fit. Only these enter the table.</p>

<p><b>Median R&sup2;</b> and <b>R&sup2; range</b> &mdash; the middle value and the
lowest and highest R&sup2; of the samples&rsquo; fits.</p>
"""


_REPORT_TITLE = 'Fitted Parameters Across the Samples'
_REPORT_HELP_HTML = """
<h3>Fitted Parameters Across the Samples</h3>

<p><b>Estimate</b> &mdash; the fit the sensitivity analysis makes with the inputs
exactly as you entered them, the same way it fits each sample. The text above the
table says whether it matches the fit in Fit results, and why not when it
can differ.</p>

<p>The other columns summarise the fit of every sample in the analysis. Each
sample refits your data with the inputs moved within the uncertainty you set, so
these columns show how far each parameter moves when the inputs are uncertain.
<b>Median &plusmn; MAD</b> is the median and the median absolute deviation
around it, a spread a single far-off sample does not carry away;
<b>Mean &plusmn; SD</b> is the ordinary mean and sample standard deviation;
<b>68% Range</b> is the interval [P16, P84] holding the central 68 % of the
samples; <b>Min-Max Range</b> is their full extent.</p>

<p><b>Rows marked *</b> &mdash; the data fix only a combination of these signal
parameters, not each one on its own: many different sets of their values draw
the same curve. Each such row is a <i>marginal summary</i>. It shows how that one
value spread across the samples, not how precisely the data determine it. Where
many fits are equally good, each fit settles on one of them, so a narrow spread
here, even 0&nbsp;&plusmn;&nbsp;0, does not mean the value is well determined.</p>
"""


# Merged stat columns of the samples view: (header, (central_key, spread_key))
# from ensemble.describe(). Rendered as a single "central ± spread" cell.
_STAT_COLUMNS = (('Median ± MAD', ('median', 'mad')), ('Mean ± SD', ('mean', 'std')))
_P68_HEADER = '68% Range'  # central 68% interval [P16, P84]
_RANGE_HEADER = 'Min-Max Range'
_SAMPLE_HEADERS = ('Parameter', 'Estimate') + tuple(h for h, _ in _STAT_COLUMNS) + (_P68_HEADER, _RANGE_HEADER, 'Units')

_NO_VALUE = '—'


def _row_formatter(spec: ParameterSummary, stats: dict | None) -> Callable[[float], str]:
    """How every number of one row is written: a log₁₀ reading, or a value (its unit has a column)."""
    if spec.is_log:
        return lambda value: fmt_log10(value, stats)
    return fmt_value


def _row_label(spec: ParameterSummary) -> str:
    """The row's name: the parameter, or its log₁₀ twin labelled with the unit it is a log of."""
    if not spec.is_log:
        return fmt_param(spec.key)
    unit_html = fmt_unit_html(spec.unit) if spec.unit else ''
    return f'log₁₀({fmt_param(spec.key)} / {unit_html})' if unit_html else f'log₁₀({fmt_param(spec.key)})'


def _fmt_pair(central: float, spread: float, fmt: Callable[[float], str]) -> str:
    """Merged 'central ± spread' cell (units stripped; shown in the Units column)."""
    return f'{fmt(central)} ± {fmt(spread)}'


def _fmt_range(lo: float, hi: float, fmt: Callable[[float], str]) -> str:
    """Merged '[min, max]' range cell."""
    return f'[{fmt(lo)}, {fmt(hi)}]'


def _sample_table(rows: list[ParameterSummary], samples: dict[str, np.ndarray]) -> list[list[str]]:
    """Cell texts of the samples view's table: each row's statistics over the fitted samples.

    A log₁₀ row is summarised through :func:`~core.optimizer.ensemble.describe_log10`,
    which transforms every sample first — statistics of log₁₀(Ka) must come from
    the per-sample log values, because log₁₀ of a Ka spread is meaningless.
    """
    cells = []
    for spec in rows:
        values = samples.get(spec.key)
        d = None if values is None else (describe_log10(values) if spec.is_log else describe(values))
        fmt = _row_formatter(spec, d)
        row = [_row_label(spec), fmt(spec.estimate)]
        if d is None:
            row += [_NO_VALUE] * (len(_STAT_COLUMNS) + 2)
        else:
            row += [_fmt_pair(d[ck], d[sk], fmt) for _, (ck, sk) in _STAT_COLUMNS]
            row += [_fmt_range(d['p16'], d['p84'], fmt), _fmt_range(d['min'], d['max'], fmt)]
        row.append(fmt_unit_html(spec.unit) if spec.unit and not spec.is_log else _NO_VALUE)
        cells.append(row)
    return cells


#: Room a cell leaves around its text, across and up and down.
_CELL_PAD_X = 16
_CELL_PAD_Y = 8


def _text_widths(label: QLabel) -> tuple[int, int]:
    """Width *label*'s text needs on one line, and the width of its widest word: the least it can wrap to."""
    doc = QTextDocument()
    doc.setDefaultFont(label.font())
    doc.setDocumentMargin(0)
    doc.setHtml(label.text())
    natural = math.ceil(doc.idealWidth())
    doc.setTextWidth(1)
    return natural, math.ceil(doc.idealWidth())


def _share_widths(natural: list[int], least: list[int], room: int) -> list[int]:
    """Column widths for *room* pixels: every column its one-line width and a share of what is left, or less.

    Where the one-line widths do not fit, each column gives up width in
    proportion to how much it can wrap — down to its widest word, never below
    — so the columns meet the width of the table and the text wraps instead of
    running behind a scrollbar. Only where even the widest words do not fit do
    the columns stay wider than the table.
    """
    total = sum(natural)
    if total <= room:
        spare = (room - total) // len(natural)
        return [width + spare for width in natural]
    widths = list(natural)
    # A column that reaches its widest word stops giving; the others share
    # what is still over, so the pass repeats at most once per column.
    for _ in natural:
        excess = sum(widths) - room
        slack = [w - m for w, m in zip(widths, least)]
        if excess <= 0 or not sum(slack):
            break
        widths = [max(w - math.ceil(excess * s / sum(slack)), m) for w, s, m in zip(widths, slack, least)]
    return widths


class ParameterTable(QTableWidget):
    """Read-only table of HTML cells, sized to its contents.

    The headers come with the rows, so the same table renders the fit view, the
    samples view and the per-replicate Replicates table.

    The table is as tall as its header and all of its rows, and the pane around
    it scrolls: a table that scrolled inside a scrolling pane would put a row
    behind a scrollbar of its own. It is as wide as the pane gives it: where
    the cells do not fit on one line they wrap between words, so every value
    can be read whole without scrolling sideways.
    """

    def __init__(self, parent=None):
        super().__init__(0, 0, parent)
        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Panning by pixel, not by column, where even the widest words of the
        # cells are wider than the table: a column can still be read end to end.
        self.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        """The header and every row, plus a horizontal scrollbar where the columns need one."""
        frame = 2 * self.frameWidth()
        columns = sum(self.columnWidth(col) for col in range(self.columnCount()))
        height = frame + self.horizontalHeader().height()
        height += sum(self.rowHeight(row) for row in range(self.rowCount()))
        if columns > self.viewport().width():
            height += self.horizontalScrollBar().sizeHint().height()
        return QSize(columns + frame + self.verticalHeader().width(), height)

    def resizeEvent(self, event) -> None:
        """Share the columns out again over the width the table now has."""
        super().resizeEvent(event)
        self.autosize_columns()

    def show_rows(self, headers: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
        """Render *rows* under *headers*, one table row each, and size the columns to their contents."""
        # Removing the rows hides their cell widgets at once; a replaced cell
        # widget would stay on screen until its deferred deletion.
        self.setRowCount(0)
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(list(headers))
        self.setRowCount(len(rows))
        for row, texts in enumerate(rows):
            for col, text in enumerate(texts):
                self.set_cell(row, col, text)
        self.autosize_columns()

    def set_cell(self, row: int, col: int, html: str) -> None:
        """Put *html* in one cell, as a centred rich-text label that wraps between words."""
        lbl = QLabel(html)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setWordWrap(True)
        self.setCellWidget(row, col, lbl)

    def autosize_columns(self) -> None:
        """Fit the columns to the width the table has, wrapping cells between words where they must.

        Each column wants the width its widest cell needs on one line; with
        room to spare it gets that and a share of the rest, and without, the
        columns give up width by :func:`_share_widths` and each row grows as
        tall as its wrapped cells. A column is never narrower than its widest
        word: a number cut off mid-digit still reads as a number.

        The widths are measured against the width the table has now, so they
        are shared out again whenever the table is resized.
        """
        n_cols = self.columnCount()
        if not n_cols:
            return
        fm = self.horizontalHeader().fontMetrics()
        natural, least = [], []
        for col in range(n_cols):
            item = self.horizontalHeaderItem(col)
            head = fm.horizontalAdvance(item.text() if item is not None else '') + 24
            wide = narrow = head
            for row in range(self.rowCount()):
                widget = self.cellWidget(row, col)
                if widget is not None:
                    one_line, word = _text_widths(widget)
                    wide = max(wide, one_line + _CELL_PAD_X)
                    narrow = max(narrow, word + _CELL_PAD_X)
            natural.append(wide)
            least.append(narrow)
        widths = _share_widths(natural, least, self.viewport().width())
        for col, width in enumerate(widths):
            self.setColumnWidth(col, width)
        default = self.verticalHeader().defaultSectionSize()
        for row in range(self.rowCount()):
            needed = max(
                (
                    self.cellWidget(row, col).heightForWidth(widths[col]) + _CELL_PAD_Y
                    for col in range(n_cols)
                    if self.cellWidget(row, col) is not None
                ),
                default=default,
            )
            self.setRowHeight(row, max(default, needed))
        self.updateGeometry()


_SAMPLES_DEGENERATE_TAIL = (
    'Each starred row is a marginal summary: it shows how that one value spread across the samples, not how '
    'precisely the data determine it, so even a spread of 0 ± 0 does not mean the value is well determined, and '
    'its estimate can differ widely from the fit in Fit results.'
)


_HEATMAP_WHY = (
    'A heatmap refits a grid of input changes you chose, not a spread of likely input values, so a summary of its '
    'fits would not show how uncertain the parameters are.'
)


def _sample_fits(
    result: SensitivityResult | None, running: SensitivityMode | None = None
) -> tuple[dict[str, np.ndarray], np.ndarray] | str:
    """*result*'s per-sample parameter values and the mask of fitted samples, or why there are none to summarise.

    *running* is the mode of an analysis still going, which has no result yet.
    """
    if running is SensitivityMode.HEATMAP:
        return f'The analysis now running is a heatmap. {_HEATMAP_WHY}'
    if running is not None:
        return (
            'The sensitivity analysis is still running. When it finishes, this table shows the fitted parameters '
            'across its samples.'
        )
    if result is None:
        return (
            'Run a sensitivity analysis with Sensitivity indices to see the fitted parameters across its samples here.'
        )
    if result.mode is SensitivityMode.HEATMAP:
        return f'The last analysis is a heatmap. {_HEATMAP_WHY}'
    if result.baseline_fit is None or not result.sample_params:
        return (
            'The last analysis does not include the fitted parameters of each sample. Run it again to see them '
            'summarised here.'
        )
    values = {key: np.asarray(v, dtype=float) for key, v in result.sample_params.items()}
    fitted = np.all(np.isfinite(np.vstack(list(values.values()))), axis=0)
    if not fitted.any():
        return 'None of the samples in the last analysis has a fit, so there is nothing to summarise.'
    return values, fitted


def unfitted_sentence(result: SensitivityResult, n: int, total: int, noun: str) -> str:
    """Why *n* of *total* samples (or grid cells, per *noun*) of *result* have no fit."""
    are = 'is' if n == 1 else 'are'
    if not result.stopped:
        return f'{n:,} of {total:,} {noun} could not be fitted and {are} left out.'
    if result.n_success == result.n_total:
        return (
            f'{n:,} of {total:,} {noun} {"was" if n == 1 else "were"} not fitted before the analysis was stopped '
            f'and {are} left out.'
        )
    return (
        f'{n:,} of {total:,} {noun} have no fit, either because the analysis was stopped before reaching them or '
        f'because they could not be fitted, and {are} left out.'
    )


def _differences(baseline: FitResult, fit: FitResult) -> list[str]:
    """What sets the analysis's own fit with the inputs as entered apart from *fit*, as plain-language clauses."""
    if baseline.assay_type != fit.assay_type:
        return ['the two are for different assay types']
    reasons = []
    if baseline.per_replica != fit.per_replica:
        ways = ('each replicate separately', 'the average of the replicates')
        ours, theirs = ways if baseline.per_replica else ways[::-1]
        reasons.append(f'this analysis fits {ours}, while that fit uses {theirs}')
    if baseline.metadata.get('data_fingerprint') != fit.metadata.get('data_fingerprint'):
        reasons.append('that fit was not made on the data as loaded now')
    else:
        ours, theirs = fit_replica_ids(baseline), fit_replica_ids(fit)
        if ours is not None and theirs is not None and set(ours) != set(theirs):
            reasons.append('the two use different replicates')
    if not same_inputs(baseline.conditions, fit.conditions):
        reasons.append('the two use different inputs')
    if baseline.fit_config.get('custom_bounds') != fit.fit_config.get('custom_bounds'):
        reasons.append('the two use different parameter bounds')
    return reasons


def _shared_left_out(baseline: FitResult, fit: FitResult, replica_ids: Sequence[str] | None) -> str:
    """A sentence naming the replicates both results leave out, when they use and leave out the same ones."""
    ours, theirs = fit_replica_ids(baseline), fit_replica_ids(fit)
    if ours is None or theirs is None or set(ours) != set(theirs):
        return ''
    left_out = [
        [rid for rid in input_replica_ids(result) or () if rid not in used]
        for result, used in ((baseline, ours), (fit, theirs))
    ]
    if not left_out[1] or set(left_out[0]) != set(left_out[1]):
        return ''
    names = describe_replicates(left_out[1], replica_ids)
    failed = all(set(left_out[1]) <= set(r.metadata.get('replica_failures') or {}) for r in (baseline, fit))
    grounds = (fit.metadata.get('replicate_test') or {}).get('reasons') or {}
    kinds = {grounds.get(rid, 'ka') for rid in left_out[1]}
    one = len(left_out[1]) == 1
    if not failed:
        why = ''
    elif kinds == {'ka'}:
        why = f', as {"its own fit needs" if one else "their own fits need"} a different Ka than the other replicates share'
    elif kinds == {'scatter'}:
        why = f", as {'its' if one else 'their'} points scatter far more than the other replicates' do"
    else:
        why = ', as each needs a different Ka than the other replicates share or scatters far more than they do'
    return f'Both leave out {names}{why}.'


def _comparison(
    rows: list[ParameterSummary],
    baseline: FitResult,
    fit: FitResult | None,
    starred: list[str],
    replica_ids: Sequence[str] | None = None,
) -> str:
    """How the samples table's estimates relate to *fit*, the fit shown on the other tabs."""
    if fit is None:
        return ''
    shared = _shared_left_out(baseline, fit, replica_ids)
    return ' '.join(part for part in (_relation(rows, baseline, fit, starred), shared) if part)


#: Why the headline in Fit results is not the analysis's own fit: that
#: fit is made with the inputs as entered, and the headline let them move.
_HEADLINE_MOVED = (
    'The headline there differs because it lets the inputs move within the uncertainties you stated; its '
    'Inputs as entered reading is the fit at the entered inputs.'
)


def _relation(rows: list[ParameterSummary], baseline: FitResult, fit: FitResult, starred: list[str]) -> str:
    """Whether the samples table's estimates match *fit* at the entered inputs, or why they can differ.

    The analysis's own fit takes every input as entered, so it is compared
    with the fit that Fit results made at the entered inputs — its
    conditional fit, wherever that fit let an input move.
    """
    reasons = _differences(baseline, fit)
    if reasons:
        return f'It can differ from the fit in Fit results because {and_join(reasons)}.'
    moved = bool(fit.input_shifts) and fit.conditional is not None
    theirs = fit.conditional.parameters if moved else fit.parameters
    differing = [
        fmt_param(spec.key)
        for spec in rows
        if not spec.is_log
        and spec.key not in starred
        and spec.key in theirs
        and fmt_value(spec.estimate) != fmt_value(float(theirs[spec.key].magnitude))
    ]
    which = 'unstarred estimates' if starred else 'estimates'
    where = 'the fit at the entered inputs in Fit results' if moved else 'the fit in Fit results'
    if not differing:
        text = f'Its {which} match {where} to the digits shown.'
    else:
        text = f'Its estimate of {and_join(differing)} differs from {where} in the digits shown.'
    return f'{text} {_HEADLINE_MOVED}' if moved else text


def _report_caption(
    result: SensitivityResult,
    fitted: np.ndarray,
    rows: list[ParameterSummary],
    fit,
    starred,
    replica_ids: Sequence[str] | None = None,
) -> str:
    """Plain-language account of what the samples table's columns cover; *fitted* marks the samples used."""
    n, total = int(fitted.sum()), fitted.size
    if n == 1:
        spread = 'The other columns cover the one sample' + ('.' if n == total else ' that has a fit.')
    else:
        spread = f'The other columns cover {f"all {n}" if n == total else f"the {n}"} samples'
        spread += '.' if n == total else ' that have a fit.'
    parts = [
        'The estimate is the fit this analysis makes with the inputs as you entered them, the same way it fits '
        'each sample.',
        _comparison(rows, result.baseline_fit, fit, starred, replica_ids),
        spread,
    ]
    if n < total:
        parts.append(unfitted_sentence(result, total - n, total, 'samples'))
    return ' '.join(part for part in parts if part)


class SamplesSummary(QWidget):
    """Read-only summary of a Sobol' run's samples: the fitted parameters across them, and their fit quality.

    Layout
    ------
    - ``InfoGroupBox`` with a caption, a :class:`ParameterTable` and a footnote.
    - ``InfoGroupBox("Fit Quality")``: how many samples have a fit, their median R² and its range.

    ``Estimate`` is the run's own fit with the inputs as entered; the other columns
    summarise every fitted sample, and the rows of ``degenerate_keys`` are starred as
    marginal summaries. Where there is nothing to summarise (no run, a run still going, a
    heatmap, no fitted samples) the caption says why. A run that no longer matches the
    loaded selection is hidden with :meth:`show_mismatch`: its note stands in place of
    its numbers, and the run is shown again, unchanged, once the note is removed.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fit: FitResult | None = None
        self._sensitivity: SensitivityResult | None = None
        self._running: SensitivityMode | None = None
        self._fit_note: str | None = None  # why the fit that Fit results reports is hidden
        self._sensitivity_note: str | None = None  # why the sensitivity run is hidden
        self._replica_ids: Sequence[str] | None = None

        self._params_group = InfoGroupBox(_REPORT_TITLE, _REPORT_TITLE, _REPORT_HELP_HTML)
        self._caption = QLabel()
        self._caption.setWordWrap(True)
        self._caption.setTextFormat(Qt.TextFormat.RichText)
        self._table = ParameterTable()
        self._footnote = QLabel()
        self._footnote.setWordWrap(True)
        self._footnote.setTextFormat(Qt.TextFormat.RichText)
        for label in (self._caption, self._footnote):
            label.setStyleSheet(f'color: {INK_2}; font-size: 13px;')
        params_layout = QVBoxLayout(self._params_group)
        for widget in (self._caption, self._table, self._footnote):
            params_layout.addWidget(widget)

        self._quality_group = InfoGroupBox('Fit Quality', 'Fit Quality', _SAMPLES_QUALITY_HELP_HTML)
        quality_form = QFormLayout(self._quality_group)
        self._fitted_label = QLabel(_NO_VALUE)
        self._median_r2_label = QLabel(_NO_VALUE)
        self._r2_range_label = QLabel(_NO_VALUE)
        self._sample_rows = (self._fitted_label, self._median_r2_label, self._r2_range_label)
        for text, label in zip(('Samples with a fit:', 'Median R²:', 'R² range:'), self._sample_rows):
            quality_form.addRow(text, label)

        page = QWidget()
        page_layout = QHBoxLayout(page)
        inset = page_layout.contentsMargins().left()
        page_layout.setContentsMargins(inset, 0, inset, 0)
        page_layout.addWidget(self._params_group, stretch=5)
        page_layout.addWidget(self._quality_group, stretch=2)
        self._page = QScrollArea()
        self._page.setWidgetResizable(True)
        self._page.setFrameShape(QFrame.Shape.NoFrame)
        self._page.setWidget(page)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self._page)
        self._render()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_result(self, result: FitResult | None) -> None:
        """Compare the samples with *result*, the fit that Fit results reports; ``None`` for none."""
        self._fit = result
        self._render()

    def show_mismatch(self, fit_note: str | None, sensitivity_note: str | None = None) -> None:
        """Hide the reported fit behind *fit_note* and the run behind *sensitivity_note*; ``None`` shows it.

        Unchanged notes leave the view as it is.
        """
        if (fit_note, sensitivity_note) == (self._fit_note, self._sensitivity_note):
            return
        self._fit_note = fit_note
        self._sensitivity_note = sensitivity_note
        self._render()

    def set_replica_ids(self, replica_ids: Sequence[str] | None) -> None:
        """The loaded data's replicate ids in order, so replicates are named as Measurements names them."""
        self._replica_ids = None if replica_ids is None else list(replica_ids)
        self._render()

    def set_sensitivity(self, result: SensitivityResult | None) -> None:
        """Summarise *result*'s samples; ``None`` leaves nothing to summarise."""
        self._sensitivity = result
        self._running = None
        self._render()

    def show_running(self, mode: SensitivityMode) -> None:
        """Drop the summarised result while an analysis in *mode* runs, and say so."""
        self._sensitivity = None
        self._running = mode
        self._render()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(self) -> None:
        if self._sensitivity is not None and self._sensitivity_note:
            self._show_note(self._sensitivity_note)
            return
        samples = _sample_fits(self._sensitivity, self._running)
        if isinstance(samples, str):
            self._show_note(samples)
            return
        self._render_samples(self._sensitivity, *samples)

    def _show_note(self, note: str) -> None:
        """*note* in place of the table and the readings."""
        self._table.setRowCount(0)
        self._table.setColumnCount(0)
        self._footnote.hide()
        self._caption.setText(note)
        self._caption.show()
        for label in self._sample_rows:
            label.setText(_NO_VALUE)

    def _star_rows(self, rows: list[ParameterSummary], keys: Sequence[str]) -> str:
        """Star every row of *keys* as a marginal summary, and say what the star means."""
        keys = list(dict.fromkeys(keys))
        if not keys:
            return ''
        explanation = degenerate_note([fmt_param(k) for k in keys], _SAMPLES_DEGENERATE_TAIL)
        for row, spec in enumerate(rows):
            if spec.key in keys:
                cell = self._table.cellWidget(row, 0)
                cell.setText(f'{cell.text()}*')
                cell.setToolTip(explanation)
        return f'* {explanation}'

    def _render_samples(self, result: SensitivityResult, values: dict[str, np.ndarray], fitted: np.ndarray) -> None:
        """The summary of *result* over the samples *fitted* marks."""
        samples = {key: v[fitted] for key, v in values.items()}
        rows = summarize_parameters(result.baseline_fit)
        self._table.show_rows(_SAMPLE_HEADERS, _sample_table(rows, samples))
        starred = [key for key in result.degenerate_keys if key in samples]
        footnote = self._star_rows(rows, starred)
        self._footnote.setText(footnote)
        self._footnote.setVisible(bool(footnote))
        fit = None if self._fit_note else self._fit
        self._caption.setText(_report_caption(result, fitted, rows, fit, starred, self._replica_ids))
        self._caption.show()

        n = int(fitted.sum())
        self._fitted_label.setText(f'{n:,} / {fitted.size:,}')
        r2 = None if result.sample_r2 is None else np.asarray(result.sample_r2, dtype=float)[fitted]
        if r2 is None:
            for label in self._sample_rows[1:]:
                label.setText('not recorded')
            return
        self._median_r2_label.setText(fmt_r2(float(np.median(r2))))
        self._r2_range_label.setText(f'[{fmt_r2(r2.min())}, {fmt_r2(r2.max())}]')
