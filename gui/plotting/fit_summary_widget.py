"""Read-only summary of a fit, or of a sensitivity run's samples, under the plot tabs."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from html import escape

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

from core.assays.registry import AssayType
from core.optimizer.ensemble import describe, describe_log10
from core.pipeline.diagnostics import LOF_BOOTSTRAP_DRAWS
from core.pipeline.fit_pipeline import FitResult
from core.pipeline.inputs import TITRANT_STOCK, ErrorModel, InputSpec, input_name, shared_key
from core.pipeline.reporting import (
    ParameterSummary,
    fit_replica_ids,
    input_replica_ids,
    parameters_on_bound,
    summarize_parameters,
)
from core.pipeline.sensitivity import SensitivityMode, SensitivityResult
from core.pipeline.varpro import LEVEL, SECOND_STEP_LEVEL
from core.units import Quantity
from gui.plotting.colors import INK_2
from gui.plotting.labels import (
    NO_UNCERTAINTY,
    RANGES_ONLY,
    SPLIT_MARK,
    SPLIT_NOTE,
    UNSOLVABLE_NOTE,
    VERDICT_TONES,
    _display_label,
    and_join,
    describe_replicates,
    fmt_bound_note,
    fmt_concentration,
    fmt_estimate,
    fmt_interval_html,
    fmt_log10,
    fmt_misfit,
    fmt_p,
    fmt_param,
    fmt_r2,
    fmt_shifts,
    fmt_stat,
    fmt_unit_html,
    fmt_value,
    not_run_reason,
    offset_note,
    one_step_sentence,
    own_estimates,
    plain_label,
    region_sentence,
    replicate_summary,
    stated_additions,
    stated_uncertainty,
    verdict_headline,
    verdict_sentence,
    widening_sentences,
)
from gui.widgets.assay_conditions import result_input_labels, same_inputs
from gui.widgets.info_button import InfoGroupBox

_LEVEL_TEXT = f'{LEVEL * 100:g} %'

#: Heading of the block under the table: does the model describe the data, and
#: do the entered inputs agree with it.
_DIAGNOSTICS_TITLE = 'Model and inputs'

#: Column holding the same binding constant with every entered input taken as
#: exact and no error of the additions. Shown only where at least one input was
#: free to move or an error of the additions was stated; otherwise the estimate
#: beside it is already that fit and the column would repeat it.
_CONDITIONAL_HEADER = 'Conditional on entered inputs'

_PARAMS_TITLE = 'Fitted Parameters'
_PARAMS_HELP_HTML = f"""
<h3>Fitted Parameters &mdash; columns</h3>

<p><b>Estimate</b> &mdash; the least-squares fit: the parameter values that
bring the model closest to the data you fitted, and the ones the curve on the
plot is drawn from. For a fit of several replicates, that is the fit of the
average of the replicates it used. Where you stated an uncertainty for an input
under <b>Input Uncertainty</b>, the fit was free to move that input inside it,
and the estimate is the fit that follows.</p>

<p><b>{_LEVEL_TEXT} interval</b> &mdash; for each association constant, the
K<sub>a</sub> values that still describe your data. Every K<sub>a</sub> in the
interval is refitted with all other parameters free &mdash; and with each input
free to move within the uncertainty you stated for it &mdash; and kept when the
resulting misfit is not significantly worse than the best fit&rsquo;s (an F test
at {_LEVEL_TEXT}). So it answers what the data say about K<sub>a</sub> when the
inputs are known no better than you stated. With no uncertainty stated, every
input counts as exact and the interval is conditional on it. A random error of
each addition you state under <b>Input Uncertainty</b>, and a noise law the
replicates leave uncertain, are allowed for as well: the test then allows for a
larger spread of the estimate than the scatter of the data alone implies, by the
factor the line under the table names. The signal parameters get no
interval: only K<sub>a</sub> is being tested.</p>

<p><b>{_CONDITIONAL_HEADER}</b> &mdash; the same fit and interval with every
input held exactly where you entered it and no error of the additions. The
column appears when at least one input was free to move or you stated a random
error of each addition, and comparing it with the columns before it shows what
those uncertainties cost you. Where you stated only the error of the additions,
no input moves: the estimate is the same and only the interval differs. It is
usually the narrower of the two; it can be the wider one where moving an input
explains misfit the entered values could not.</p>

<p><b>A marked interval</b> &mdash; {SPLIT_MARK} means the K<sub>a</sub> the test
keeps come in separate stretches, and the bracket spans all of them, so values
inside it are rejected. The <b>Identifiability</b> tab draws where the accepted
stretches are.</p>

<p><b>An open side</b> &mdash; <i>no upper limit</i> means the data stay
consistent with every larger K<sub>a</sub> up to the bound you set: the
titration saturates too early to tell them apart. Add points below saturation,
or lower the fixed concentration, and fit again. <i>No lower limit</i> means the
same downwards: add points at higher titrant concentration. <i>Not limited by
the data</i> means neither end is closed, so the fit does not determine
K<sub>a</sub> at all. A K<sub>a</sub> you held fixed reads <i>fixed</i> and has
no interval, because it was not fitted.</p>

<p><b>The second constant of a two-step model</b> &mdash; a closed lower end on
K<sub>a(HG₂)</sub> or K<sub>a(H₂G)</sub> claims that the second binding step
happens at all. It is closed only where the data reject the model without that
step (the <i>one-step test</i>, at p&nbsp;&le;&nbsp;{SECOND_STEP_LEVEL:g});
otherwise it reads <i>no lower limit</i>, and the line under the table says that
a model without the second step fits nearly as well. Where the step is supported, the same line says
at what p the one-step model was rejected. Where the second constant is a hundred times or more below
the first, a closed interval of it misses the true value more often than 1 in 20 even after the
test: read it together with the joint region on the <b>Identifiability</b> tab.</p>

<p><b>An estimate in words</b> &mdash; <i>not limited below 2.41&times;10<sup>3</sup></i>
means the best fit ran onto the lower bound of the K<sub>a</sub> search: the
data do not limit K<sub>a</sub> from below, so the value the search stopped at is
the bound, not a measurement, and is not shown. What the data do say is the
closed end of the interval: K<sub>a</sub> lies below it. <i>Not limited above</i>
is the same upwards. The curve on the plot is still drawn from that fit.</p>

<p><b>log<sub>10</sub>(K<sub>a</sub>) row</b> &mdash; each association constant
is repeated as its log<sub>10</sub>. Its estimate and interval are the row above
read on a log scale, which is exact.</p>

<p><b>Single-replicate fits</b> &mdash; the line under the table, shown when
each replicate was fitted separately and at least two entered the fit: the
middle, lowest and highest K<sub>a</sub> across those replicates&rsquo;
<i>own</i> fits, each made with the inputs as entered. They say how far the
replicates disagree, which is a different question from the interval: the
interval says how precisely the fit of their average pins K<sub>a</sub> down, so
a single replicate&rsquo;s value can fall outside it. A replicate whose own fit
ran to a bound of the K<sub>a</sub> search has no value to count and is counted
separately. Replicates left out of the fit are not counted here; the Replicates
table below lists every replicate.</p>

<p><b>Rows marked *</b> &mdash; at the fitted K<sub>a</sub>, the data fix only a
combination of these signal parameters, not each one on its own: many different
sets of their values draw exactly the same curve. The value shown is one member
of that family. It reconstructs the curve correctly and must not be read as a
measurement of that one coefficient.</p>

<h3>{_DIAGNOSTICS_TITLE}</h3>

<p>Whether the curve actually describes your data, and whether the inputs you
entered agree with it. The line above the table says it in a few words, in grey
when there is nothing to act on, amber when something is worth checking, and red
when the result rests on something the data reject.</p>

<p><b>The misfit test</b> &mdash; with two or more replicates, the scatter
between them measures your noise directly, and the <i>lack-of-fit F test</i>
asks whether the curve misses their average by more than that scatter allows.
Where a noise law was read off the replicates &mdash; constant, or growing with
the signal &mdash; the fit weights its points by that law, and the test&rsquo;s
p-value is simulated from the fitted curve and the law, in {LOF_BOOTSTRAP_DRAWS} draws, each
carrying the random error of each addition where you stated one: where none of
them misses the data as far as the curve does, it reads
p&nbsp;&le;&nbsp;{1 / (LOF_BOOTSTRAP_DRAWS + 1):g}, the smallest value the simulation can show. With a single signal there is no such measure, and
the <i>runs test</i> asks instead whether the residuals change sign as often as
a fit of this model to pure noise would &mdash; noise that carries the error of
each addition where you stated one; a curve that misses systematically leaves
long runs on one side. The test is reported at the fit with the inputs as
entered and, where an input was free to move, at the fit that moved them.</p>

<p><b>The inputs, taken together</b> &mdash; <i>q</i> measures how far the fit
had to move your inputs, in units of the uncertainties you stated, along the
combinations of them the data can actually see. The data usually see only one or
two such combinations &mdash; the host concentration and the titrant scale move
the curve almost alike &mdash; so a large shift on one input says where the fit
put the correction, <b>not</b> which stock is wrong. A stated random error of
each addition moves the inputs a little as well, and the test allows for that.
Where the data see no combination at all, they cannot check your inputs and the
line says so.</p>

<p><b>What the verdict means</b></p>
<ul>
<li><i>No test found evidence against the model or the entered inputs</i>
&mdash; the curve fits within the noise and the inputs needed no correction
beyond what you allowed. This is the absence of evidence against the fit, not
proof of it: a test sees only as far as the noise and the number of points let
it. A test that could not be run is named, with the reason.</li>
<li><i>The data fit once the inputs move within their uncertainties</i> &mdash;
at the entered values the curve misses the data, and a shift inside the
uncertainties you stated brings it back.
The reported interval already covers those shifts. Worth checking your stock
concentrations, but the fit stands.</li>
<li><i>The inputs together are further from their entered values than you
stated</i> &mdash; the data fit only with the inputs further from the entered
values than you said they could be. Re-check the
stocks and the instrument settings, or state a larger uncertainty if the entered
values are less certain than you first said. The interval assumes the shifts are
real.</li>
<li><i>The curve misses the data by more than their scatter allows</i> &mdash;
no allowed shift of the inputs rescues the curve, so the model does not describe
the data. Try another binding model, or look at the data for a
bad point or a drifting baseline. The interval still assumes this model.</li>
<li><i>The inputs together are further from their entered values than you
stated, and the curve misses the data by more than their scatter allows</i>
&mdash; both at once. Check the inputs first: an input that is off
can by itself make the curve miss. If they are right, try another binding
model.</li>
</ul>

<p>Where the fit moved an input, the curve on the Fit Curve tab is drawn at the
inputs where the fit put them, and the plot says so.</p>

<p><b>Input uncertainties used</b> &mdash; what the fit was told, so the numbers
above can be read against it. Uncertainties are entered in the <b>Input
Uncertainty</b> panel; with none stated, every input counts as exact.</p>
"""


_FIT_QUALITY_HELP_HTML = """
<h3>Fit Quality</h3>

<p><b>RMSE</b> (root mean squared error) &mdash; average distance between
the fitted curve and the data points, in signal units. Lower is better.
Compare it to the noise level in your data: if RMSE is similar to the
noise floor, the fit is explaining the data about as well as possible.</p>

<p><b>R&sup2;</b> (coefficient of determination) &mdash; fraction of the
data variance explained by the fit, from 0 to 1. A high R&sup2; does not show
that the model describes the data: check the Fit Curve for runs of points on one
side of the curve. How precisely K<sub>a</sub> is determined is the interval in
the table, not R&sup2;.</p>

<p>Both are measured for the fit shown above, at the inputs where that fit put
them &mdash; which are the values you entered unless you gave an input an
uncertainty under <b>Input Uncertainty</b>.</p>

<p><b>Noise</b> &mdash; how large the scatter of your measurements is and how it
grows with the signal, read from how far your replicates fall from the curve
each of them traces. The fit uses it to weight the titration points, read at the
fitted curve: a point the replicates show to be twice as precise counts four
times as much. One titration
cannot show how the noise varies, so it is fitted with the noise taken as
constant, which the row says.</p>

<p><b>Replicates used</b> &mdash; how many of the replicates you switched on
entered the fit. A replicate is left out when its own best fit needs a
K<sub>a</sub> the others do not share, or when its points scatter about its own
fit far more than the others&rsquo; do; the tooltip names each one and why.
Where you stated a random error of each addition and the replicates are separate
titrations, both checks allow for each replicate&rsquo;s own additions. The
K<sub>a</sub> test can only notice a replicate whose own data pin K<sub>a</sub> down &mdash;
if the replicates&rsquo; own K<sub>a</sub> values spread over decades, one that
disagrees will not stand out.</p>
"""


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
table says whether it matches the fit on the Fit Curve tab, and why not when it
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


#: The summary table's columns in the fit view; the conditional column joins
#: them before the units where an input was free to move.
_FIT_HEADERS = ('Parameter', 'Estimate', f'{_LEVEL_TEXT} interval', 'Units')
#: Where the interval sits in a fit table row.
_INTERVAL_COLUMN = _FIT_HEADERS.index(f'{_LEVEL_TEXT} interval')

# Merged stat columns of the samples view: (header, (central_key, spread_key))
# from ensemble.describe(). Rendered as a single "central ± spread" cell.
_STAT_COLUMNS = (('Median ± MAD', ('median', 'mad')), ('Mean ± SD', ('mean', 'std')))
_P68_HEADER = '68% Range'  # central 68% interval [P16, P84]
_RANGE_HEADER = 'Min-Max Range'
_SAMPLE_HEADERS = ('Parameter', 'Estimate') + tuple(h for h, _ in _STAT_COLUMNS) + (_P68_HEADER, _RANGE_HEADER, 'Units')

#: Columns of the Replicates table, before the one column each binding constant
#: adds after "Replicate".
_REPLICATE_TABLE_HEADERS = ('Replicate', 'R²', 'p-value', 'In the fit')

_LEGACY_NOTE = (
    'Imported from a file written by an earlier version: a multi-start estimate without a confidence interval. '
    'Fit the data again to get the interval.'
)

_NO_VALUE = '—'

#: The Noise row of a result that names no law: a file written before the law
#: was recorded. Saying so is not the same as saying the noise was constant.
_NO_NOISE = 'not recorded in this result'


def _noise_row(law: str) -> str:
    """The Noise row's text: the row spans the box, so it carries its own name."""
    return f'Noise: {law}'


def _row_formatter(spec: ParameterSummary, stats: dict | None) -> Callable[[float], str]:
    """How every number of one row is written: a log₁₀ reading, or a value (its unit has a column)."""
    if spec.is_log:
        return lambda value: fmt_log10(value, stats)
    return fmt_value


def _estimate_cell(spec: ParameterSummary, fmt: Callable[[float], str]) -> str:
    """The estimate of one row: its value, or in words where the fit ran onto an end of its Ka search box."""
    return fmt_estimate(spec.estimate, spec.estimate_at_bound, spec.interval, spec.interval_open, fmt, html=True)


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


def _interval_cell(spec: ParameterSummary, fmt: Callable[[float], str], ka_keys: set[str], reported: bool) -> str:
    """What the interval column says for one row.

    A binding constant the fit was free to move carries its interval; one held
    fixed says so, because it was not fitted; a signal parameter has none to
    report, and neither has any row of a result that carries no interval at all.

    An interval whose accepted values come in separate stretches is marked, so
    the bracket is not read as one connected range of values the data accept.
    """
    if spec.interval is not None:
        low, high = spec.interval
        text = fmt_interval_html(fmt(low), fmt(high), *spec.interval_open)
        return f'{text} {SPLIT_MARK}' if spec.interval_split else text
    if spec.key in ka_keys and reported:
        return '<i>fixed</i>'
    return _NO_VALUE


def _conditional_cell(spec: ParameterSummary, fmt: Callable[[float], str]) -> str:
    """The same binding constant with every input held where it was entered: ``estimate [low, high]``.

    Only a binding constant of a fit that let an input move has such a reading;
    every other row says so with a dash rather than repeating the estimate
    beside it. Separate stretches are marked here as in the interval column:
    the bracket means the same thing in both.
    """
    if spec.conditional_estimate is None:
        return _NO_VALUE
    text = fmt_estimate(
        spec.conditional_estimate,
        spec.conditional_at_bound,
        spec.conditional_interval,
        spec.conditional_open,
        fmt,
        html=True,
    )
    if spec.conditional_interval is not None:
        low, high = spec.conditional_interval
        text += f' {fmt_interval_html(fmt(low), fmt(high), *spec.conditional_open)}'
        if spec.conditional_split:
            text += f' {SPLIT_MARK}'
    return text


def _sentence(note: str) -> str:
    """One of the shared notes as a sentence of its own; they are written to follow a parameter name."""
    return f'{note[0].upper()}{note[1:]}'


#: What the mark on a split interval means, wherever that mark is shown.
_SPLIT_FOOTNOTE = f'{SPLIT_MARK} {_sentence(SPLIT_NOTE)}'


def _interval_tooltip(spec: ParameterSummary, *, split: bool) -> str:
    """What the bracket of one cell does not show: separate stretches, and an open side no data can close."""
    notes = []
    if split:
        notes.append(_SPLIT_FOOTNOTE)
    if any(spec.interval_unsolvable):
        notes.append(_sentence(UNSOLVABLE_NOTE))
    return ' '.join(notes)


def _fit_table(rows: list[ParameterSummary], ka_keys: set[str], reported: bool) -> tuple[list[str], list[list[str]]]:
    """Headers and cell texts of the fit view's table.

    The conditional column appears only where a row fills it, so a fit that
    took every input as entered is not shown a column repeating its own
    numbers. The replicates' own fits are a line under the table
    (:func:`~gui.plotting.labels.replicate_summary`): they are fits at the
    inputs as entered and answer another question than the headline beside
    them.
    """
    with_conditional = any(spec.conditional_estimate is not None for spec in rows)
    headers = [*_FIT_HEADERS[:-1]]
    if with_conditional:
        headers.append(_CONDITIONAL_HEADER)
    headers.append(_FIT_HEADERS[-1])

    cells = []
    for spec in rows:
        fmt = _row_formatter(spec, spec.replicates)
        row = [_row_label(spec), _estimate_cell(spec, fmt), _interval_cell(spec, fmt, ka_keys, reported)]
        if with_conditional:
            row.append(_conditional_cell(spec, fmt))
        # A log₁₀ row is dimensionless; its source unit only labels it.
        row.append(fmt_unit_html(spec.unit) if spec.unit and not spec.is_log else _NO_VALUE)
        cells.append(row)
    return headers, cells


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


def _degenerate_note(keys: list[str], tail: str) -> str:
    """Why the starred rows are starred: the shared fact, then what it means for this view."""
    return (
        f'The data fix only a combination of {and_join([fmt_param(k) for k in keys])}, not each one on its own: '
        f'many different sets of their values draw the same curve. {tail}'
    )


_FIT_DEGENERATE_TAIL = (
    'Each starred value is one member of that family. It reconstructs the fitted curve correctly and is not a '
    'measurement of that one coefficient.'
)

_SAMPLES_DEGENERATE_TAIL = (
    'Each starred row is a marginal summary: it shows how that one value spread across the samples, not how '
    'precisely the data determine it, so even a spread of 0 ± 0 does not mean the value is well determined, and '
    'its estimate can differ widely from the fit on the Fit Curve tab.'
)


_HEATMAP_WHY = (
    'A heatmap refits a grid of input changes you chose, not a spread of likely input values, so a summary of its '
    'fits would not show how uncertain the parameters are.'
)


# ---------------------------------------------------------------------------
# Model and inputs: what the diagnostics of a fit say
# ---------------------------------------------------------------------------


def _test_text(diagnostics, test) -> str:
    """One misfit test, ready for a rich-text label; a test that was not run says why, rather than being left blank."""
    if test is None:
        return f'not tested: {escape(not_run_reason(diagnostics, "misfit"), quote=False)}.'
    return escape(fmt_misfit(test), quote=False)


def _misfit_lines(diagnostics, moved: bool) -> list[str]:
    """The misfit test at each fit: one line where every input was entered as exact, two where one could move."""
    if not moved:
        return [f'Fit at the entered inputs — {_test_text(diagnostics, diagnostics.conditional_misfit)}']
    return [
        f'Fit with the inputs as entered — {_test_text(diagnostics, diagnostics.conditional_misfit)}',
        f'Fit with the inputs free to move — {_test_text(diagnostics, diagnostics.misfit)}',
    ]


def _inputs_line(diagnostics, shifts: dict, labels: dict[str, str]) -> str:
    """Where the fit put the inputs, and what the conflict statistic says about them together.

    The statistic needs a direction of the inputs the data inform; with none —
    which happens whenever the data cannot tell the entered values apart from
    their neighbours — there is no statistic and the line says the inputs went
    unchecked rather than implying they passed. Where every stated uncertainty
    is a range there is no statistic either, and the line says why: whether the
    fit took one to an end of its range is what there is to see.
    """
    if not shifts:
        return ''
    if diagnostics.conflict is not None:
        k = diagnostics.conflict.k
        head = (
            f'Inputs, taken together: q = {fmt_stat(diagnostics.conflict.q)} across {k} '
            f'direction{"" if k == 1 else "s"} the data inform, '
            f'{escape(fmt_p(diagnostics.conflict.p_value), quote=False)}. '
        )
    elif any(shift.z is not None for shift in shifts.values()):
        head = (
            'Inputs, taken together: the data do not determine any combination of the inputs you gave an '
            'uncertainty, so they cannot check the entered values. '
        )
    else:
        head = f'Inputs, taken together: {RANGES_ONLY}. '
    return f'{head}Shifts: {fmt_shifts(shifts, labels, html=True)}.'


def _uncertainty_line(result: FitResult, labels: dict[str, str]) -> str:
    """What the fit was told about its inputs and about the sources they share, read back from the fit's own record."""
    errors = ErrorModel.from_dict(result.fit_config or {})
    if not errors.specs and not errors.shared and errors.additions is None:
        return f'Input uncertainties used: {NO_UNCERTAINTY}.'
    conditions = result.conditions or {}

    def unit(key: str) -> str:
        value = conditions.get(key)
        return fmt_unit_html(str(value.units)) if isinstance(value, Quantity) else ''

    stated = [f'{input_name(key, labels)} {stated_uncertainty(spec, unit(key))}' for key, spec in errors.specs.items()]
    # A shared source is a precision figure of one stock, balance or pipette,
    # so it is a standard deviation in percent and nothing else.
    stated += [
        f'{labels.get(shared_key(source.name), source.name)} {stated_uncertainty(InputSpec.sigma_pct(source.sigma_pct), "")}'
        for source in errors.shared
    ]
    if errors.additions is not None:
        n_replicates = 1 if result.noise is None else result.noise.n_replicates
        stated.append(f'each addition σ {stated_additions(errors.additions, n_replicates)}')
    return f'Input uncertainties used: {", ".join(stated)}.'


def _dilution_line(result: FitResult, labels: dict[str, str]) -> str:
    """How the titrant diluted the sample this fit was made on; ``''`` where the totals stayed constant."""
    conditions = result.conditions or {}
    stock = conditions.get(TITRANT_STOCK)
    if not isinstance(stock, Quantity):
        return ''
    line = (
        f'Dilution: the titrant was added from a stock of {fmt_concentration(stock)}, so every fixed '
        'concentration falls with each addition'
    )
    contains = tuple(conditions.get('stock_contains') or ())
    if contains:
        held = ', '.join(labels.get(key, key) for key in contains)
        line += f', except {held}, which the stock holds at the sample’s own concentration'
    return f'{line}.'


def _diagnostics_lines(result: FitResult) -> list[str]:
    """The Model and inputs block of one fit, one line each; empty for a result that carries no diagnostics.

    The sources are named from the fit's own assay and its own record of what
    the inputs share, so the block and the exported report name the same fit's
    sources alike.
    """
    diagnostics = result.diagnostics
    if diagnostics is None:
        return []
    labels = result_input_labels(result.assay_type, result.fit_config)
    shifts = result.input_shifts or {}
    lines = [verdict_sentence(diagnostics, shifts, labels, html=True)]
    lines += _misfit_lines(diagnostics, bool(shifts))
    inputs = _inputs_line(diagnostics, shifts, labels)
    if inputs:
        lines.append(inputs)
    lines.append(_uncertainty_line(result, labels))
    dilution = _dilution_line(result, labels)
    if dilution:
        lines.append(dilution)
    return lines


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


#: Why the headline on the Fit Curve tab is not the analysis's own fit: that
#: fit is made with the inputs as entered, and the headline let them move.
_HEADLINE_MOVED = (
    'The headline there differs because it lets the inputs move within the uncertainties you stated; its '
    'Conditional column is the fit at the entered inputs.'
)


def _relation(rows: list[ParameterSummary], baseline: FitResult, fit: FitResult, starred: list[str]) -> str:
    """Whether the samples table's estimates match *fit* at the entered inputs, or why they can differ.

    The analysis's own fit takes every input as entered, so it is compared
    with the fit the Fit Curve tab made at the entered inputs — its
    conditional fit, wherever that fit let an input move.
    """
    reasons = _differences(baseline, fit)
    if reasons:
        return f'It can differ from the fit on the Fit Curve tab because {and_join(reasons)}.'
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
    where = 'the fit at the entered inputs on the Fit Curve tab' if moved else 'the fit on the Fit Curve tab'
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


class FitSummaryWidget(QWidget):
    """Read-only summary under the plot tabs: the fitted parameters and their quality.

    Layout
    ------
    - ``InfoGroupBox`` with the verdict in a few words, a caption, a
      :class:`ParameterTable`, a footnote and — for a per-replicate fit — a
      Replicates table.
    - ``InfoGroupBox("Fit Quality")``.

    Both sit on a page that scrolls. The pane shares the height of the window
    with the plot tabs above it, and a nine-row table with its footnote is
    taller than the share it gets: the page scrolls so every row and the whole
    footnote can be read, at any height the pane is dragged to.

    Two views share the layout. The *fit view* shows the fit: the verdict of its
    diagnostics on a strip coloured by what it asks of the reader, its estimate
    per parameter, the confidence interval of every binding constant it was
    free to move, the same pair with every input held where it was entered
    (where the fit was allowed to move one), a line under the table with the
    replicates' own fits where there are several, and a *Model and inputs*
    block saying whether the model and the entered inputs describe the data
    and where the fit put the inputs it could move. Fit Quality gives RMSE, R²
    and the replicates used. The *samples view*
    (:meth:`show_samples` on, with a SOBOL result from :meth:`set_sensitivity`
    that holds fitted samples) shows the fitted parameters across that run's
    samples: ``Estimate`` is the run's own fit with the inputs as entered, the
    other columns summarise every fitted sample, the rows of ``degenerate_keys``
    are starred as marginal summaries, and Fit Quality describes the samples.
    With the samples view requested but nothing to summarise (no run, a run
    still going, a heatmap, or no fitted samples), the fit view shows with a
    caption saying why. Rows always come from
    :func:`~core.pipeline.reporting.summarize_parameters`, shared with the
    plot annotation and the exports.

    A fit or a sensitivity run that no longer matches the loaded selection is
    hidden with :meth:`show_mismatch`: its view shows the note in place of its
    numbers. The result is kept and shown again, unchanged, once the note is
    removed.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._fit: FitResult | None = None
        self._sensitivity: SensitivityResult | None = None
        self._running: SensitivityMode | None = None
        self._samples_view = False
        self._fit_note: str | None = None  # why the fit is hidden
        self._sensitivity_note: str | None = None  # why the sensitivity run is hidden
        self._unchecked: str | None = None  # why the fit's numbers could not be checked against data
        self._replica_ids: Sequence[str] | None = None

        self._params_group = InfoGroupBox(_PARAMS_TITLE, 'Fitted Parameters — columns', _PARAMS_HELP_HTML)

        # The verdict in a few words, first in the box: whether the result can
        # be taken as it stands is the first thing to read, above the numbers.
        self._verdict = QLabel()
        self._verdict.setWordWrap(True)
        self._verdict.setTextFormat(Qt.TextFormat.PlainText)
        self._caption = QLabel()
        self._caption.setWordWrap(True)
        self._caption.setTextFormat(Qt.TextFormat.RichText)
        self._table = ParameterTable()
        self._footnote = QLabel()
        self._footnote.setWordWrap(True)
        self._footnote.setTextFormat(Qt.TextFormat.RichText)
        self._diagnostics_heading = QLabel(_DIAGNOSTICS_TITLE)
        self._diagnostics_label = QLabel()
        self._diagnostics_label.setWordWrap(True)
        self._diagnostics_label.setTextFormat(Qt.TextFormat.RichText)
        self._replicates_heading = QLabel('Replicates')
        self._replicates_table = ParameterTable()
        for label in (self._caption, self._footnote, self._diagnostics_heading, self._diagnostics_label):
            label.setStyleSheet(f'color: {INK_2}; font-size: 13px;')
        self._replicates_heading.setStyleSheet(f'color: {INK_2}; font-size: 13px;')
        params_layout = QVBoxLayout(self._params_group)
        for widget in (
            self._verdict,
            self._caption,
            self._table,
            self._footnote,
            self._diagnostics_heading,
            self._diagnostics_label,
            self._replicates_heading,
            self._replicates_table,
        ):
            params_layout.addWidget(widget)

        self._quality_group = InfoGroupBox('Fit Quality', 'Fit Quality', _FIT_QUALITY_HELP_HTML)
        self._quality_form = QFormLayout(self._quality_group)
        self._rmse_label = QLabel(_NO_VALUE)
        self._rmse_label.setTextFormat(Qt.TextFormat.RichText)
        self._r2_label = QLabel(_NO_VALUE)
        self._replicates_label = QLabel(_NO_VALUE)
        self._fitted_label = QLabel()
        self._median_r2_label = QLabel()
        self._r2_range_label = QLabel()
        self._fit_rows = (self._rmse_label, self._r2_label, self._replicates_label)
        self._sample_rows = (self._fitted_label, self._median_r2_label, self._r2_range_label)
        for text, label in zip(('RMSE:', 'R²:', 'Replicates used:'), self._fit_rows):
            self._quality_form.addRow(text, label)
        # The law is a sentence, so it takes a row of its own across the whole
        # box, under the readings, and carries its own name. The value column
        # beside the readings holds a number's width, which a sentence wraps
        # into some seven lines — more than the box is tall.
        self._noise_label = QLabel(_noise_row(_NO_VALUE))
        self._noise_label.setWordWrap(True)
        self._noise_label.setTextFormat(Qt.TextFormat.PlainText)
        self._quality_form.addRow(self._noise_label)
        for text, label in zip(('Samples with a fit:', 'Median R²:', 'R² range:'), self._sample_rows):
            self._quality_form.addRow(text, label)

        page = QWidget()
        page_layout = QHBoxLayout(page)
        # The groups keep the inset they had beside the pane's edges, and give up
        # the one above and below: the splitter shares the window's height by
        # what each pane prefers, and the plot tabs above have none to spare.
        inset = page_layout.contentsMargins().left()
        page_layout.setContentsMargins(inset, 0, inset, 0)
        # The quality box takes two parts to the table's five: its readings are
        # short, but the noise law under them is a sentence, and two parts is
        # the width that keeps that sentence to three lines in the pane.
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
        # That first render hides the rows that only a fit fills. Hiding a
        # widget that has never been shown does not reach the layout, which
        # would go on reserving their height and take it from the plot above,
        # so ask the layout to measure itself again against what it shows.
        params_layout.invalidate()
        params_layout.activate()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_result(self, result: FitResult, *, unchecked: str | None = None) -> None:
        """Show *result* as the fit, in the fit view and in the samples view's comparison.

        *unchecked* says why its numbers could not be checked against data: it
        is shown with them.
        """
        self._fit = result
        self._unchecked = unchecked
        self._render()

    def show_mismatch(self, fit_note: str | None, sensitivity_note: str | None = None) -> None:
        """Hide the fit behind *fit_note* and the sensitivity run behind *sensitivity_note*; ``None`` shows it.

        Unchanged notes leave the view as it is.
        """
        if (fit_note, sensitivity_note) == (self._fit_note, self._sensitivity_note):
            return
        self._fit_note = fit_note
        self._sensitivity_note = sensitivity_note
        self._render()

    def set_replica_ids(self, replica_ids: Sequence[str] | None) -> None:
        """The loaded data's replicate ids in order, so replicates are named as the Replicates panel names them."""
        self._replica_ids = None if replica_ids is None else list(replica_ids)
        self._render()

    def set_sensitivity(self, result: SensitivityResult | None) -> None:
        """Summarise *result*'s samples in the samples view; ``None`` leaves nothing to summarise."""
        self._sensitivity = result
        self._running = None
        self._render()

    def show_running(self, mode: SensitivityMode) -> None:
        """Drop the summarised result while an analysis in *mode* runs, and say so in the samples view."""
        self._sensitivity = None
        self._running = mode
        self._render()

    def show_samples(self, on: bool) -> None:
        """Switch to the samples view (*on*, while Ka Sensitivity is the current tab) or back to the fit view."""
        self._samples_view = on
        self._render()

    def clear(self) -> None:
        """Drop the fit; the fit view then shows empty fields."""
        self._fit = None
        self._unchecked = None
        self._render()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(self) -> None:
        if self._samples_view and self._sensitivity is not None and self._sensitivity_note:
            self._render_hidden_samples()
            return
        samples = _sample_fits(self._sensitivity, self._running) if self._samples_view else None
        if isinstance(samples, tuple):
            self._render_samples(self._sensitivity, *samples)
            return
        note = ''
        if isinstance(samples, str):
            instead = (
                'The table shows the fit from the Fit Curve tab instead.' if self._fit and not self._fit_note else ''
            )
            note = f'{samples} {instead}'.strip()
        self._render_fit(note)

    def _set_view(self, title: str, info: tuple[str, str], quality_help: str, samples: bool) -> None:
        self._params_group.setTitle(title)
        self._params_group.set_info(*info)
        self._quality_group.set_info('Fit Quality', quality_help)
        for label in self._fit_rows:
            self._quality_form.setRowVisible(label, not samples)
        self._quality_form.setRowVisible(self._noise_label, not samples)
        for label in self._sample_rows:
            self._quality_form.setRowVisible(label, samples)

    def _render_fit(self, note: str) -> None:
        """The fit view; any note on the fit itself leads the caption, followed by *note* (possibly empty)."""
        self._set_view(_PARAMS_TITLE, ('Fitted Parameters — columns', _PARAMS_HELP_HTML), _FIT_QUALITY_HELP_HTML, False)
        result = self._fit
        # A dye-alone calibration is a line fitted by fit_linear_assay, which
        # reads no noise law and needs none: the row has nothing to say.
        self._quality_form.setRowVisible(
            self._noise_label, result is None or result.assay_type != AssayType.DYE_ALONE.name
        )
        hidden = self._fit_note if result is not None else None
        block = hidden or (self._unchecked if result is not None else None)
        self._footnote.hide()
        self._hide_diagnostics()
        self._hide_replicates_table()
        if result is None or hidden:
            # With no numbers to show, *note* is the only thing that says why
            # the samples view is not the one on screen.
            caption = ' '.join(part for part in (block, note) if part)
            self._caption.setText(caption)
            self._caption.setVisible(bool(caption))
            self._table.setRowCount(0)
            self._table.setColumnCount(0)
            for label in self._fit_rows:
                label.setText(_NO_VALUE)
            self._noise_label.setText(_noise_row(_NO_VALUE))
            return

        rows = summarize_parameters(result)
        # summarize_parameters gives every binding constant a log₁₀ twin, and
        # only a binding constant: the twins name the keys an interval is
        # reported for.
        ka_keys = {spec.key for spec in rows if spec.is_log}
        headers, cells = _fit_table(rows, ka_keys, result.intervals is not None)
        self._table.show_rows(headers, cells)
        self._set_footnote(
            replicate_summary(
                [spec for spec in rows if spec.key in ka_keys and not spec.is_log],
                len(fit_replica_ids(result) or ()),
                lambda spec: fmt_param(spec.key),
                lambda spec: fmt_unit_html(spec.unit),
            ),
            self._star_rows(
                rows, [spec.key for spec in rows if spec.degenerate and not spec.is_log], _FIT_DEGENERATE_TAIL
            ),
            self._note_intervals(rows),
            *(
                one_step_sentence(fmt_param(spec.key), spec.one_step_p)
                for spec in rows
                if not spec.is_log and spec.one_step_p is not None
            ),
            *widening_sentences(rows, result, fmt_param),
            region_sentence(result) or '',
        )

        legacy = _LEGACY_NOTE if ka_keys and result.intervals is None else ''
        on_bound = fmt_bound_note(parameters_on_bound(result))
        caption = ' '.join(part for part in (block, legacy, on_bound, offset_note(result), note) if part)
        self._caption.setText(caption)
        self._caption.setVisible(bool(caption))

        self._show_diagnostics(result)
        self._rmse_label.setText(f'{fmt_value(result.rmse)} {fmt_unit_html("au")}')
        self._r2_label.setText(fmt_r2(result.r_squared))
        self._noise_label.setText(_noise_row(_NO_NOISE if result.noise is None else result.noise.describe()))
        self._show_replicates_used(result)
        self._show_replicates_table(result)

    def _star_rows(self, rows: list[ParameterSummary], keys: Sequence[str], tail: str) -> str:
        """Star every row of *keys* — the parameters the data determine only in combination — and say what the star means."""
        keys = list(dict.fromkeys(keys))
        if not keys:
            return ''
        explanation = _degenerate_note(keys, tail)
        for row, spec in enumerate(rows):
            if spec.key in keys:
                cell = self._table.cellWidget(row, 0)
                cell.setText(f'{cell.text()}*')
                cell.setToolTip(explanation)
        return f'* {explanation}'

    def _note_intervals(self, rows: list[ParameterSummary]) -> str:
        """Put what a bracket does not show in its own cell's tooltip, and say what the split mark means."""
        split = False
        conditional = self._column_of(_CONDITIONAL_HEADER)
        for row, spec in enumerate(rows):
            tooltip = _interval_tooltip(spec, split=spec.interval_split)
            if tooltip:
                self._table.cellWidget(row, _INTERVAL_COLUMN).setToolTip(tooltip)
            if conditional is not None and spec.conditional_split:
                self._table.cellWidget(row, conditional).setToolTip(_SPLIT_FOOTNOTE)
            split = split or spec.interval_split or spec.conditional_split
        return _SPLIT_FOOTNOTE if split else ''

    def _column_of(self, header: str) -> int | None:
        """Which column carries *header*, or ``None`` where the table is not showing it."""
        for col in range(self._table.columnCount()):
            item = self._table.horizontalHeaderItem(col)
            if item is not None and item.text() == header:
                return col
        return None

    def _set_footnote(self, *parts: str) -> None:
        """Show the notes the table's marks need, one per line, or hide the footnote when there are none."""
        text = '<br>'.join(part for part in parts if part)
        self._footnote.setText(text)
        self._footnote.setVisible(bool(text))

    def _show_replicates_used(self, result: FitResult) -> None:
        """ "n of m", with the replicates left out and why named in the tooltip."""
        used, given = fit_replica_ids(result), input_replica_ids(result)
        if used is None or given is None:
            self._replicates_label.setText(_NO_VALUE)
            self._replicates_label.setToolTip('')
            return
        self._replicates_label.setText(f'{len(used)} of {len(given)}')
        left_out = [rid for rid in given if rid not in used]
        failures = result.metadata.get('replica_failures') or {}
        self._replicates_label.setToolTip(
            ''
            if not left_out
            else 'Left out: '
            + ' '.join(
                f'{_replica_name(rid, self._replica_ids)} — {failures.get(rid, "left out of the fit.")}'
                for rid in left_out
            )
        )

    def _hide_diagnostics(self) -> None:
        self._verdict.hide()
        self._diagnostics_heading.hide()
        self._diagnostics_label.hide()

    def _show_diagnostics(self, result: FitResult) -> None:
        """What the misfit tests and the conflict statistic say about *result*; hidden for a result with no tests.

        The verdict leads the box on a strip coloured by what it asks of the
        reader (:data:`~gui.plotting.labels.VERDICT_TONES`); the block under
        the table says the rest.
        """
        lines = _diagnostics_lines(result)
        self._diagnostics_label.setText('<br>'.join(lines))
        self._diagnostics_heading.setVisible(bool(lines))
        self._diagnostics_label.setVisible(bool(lines))
        if result.diagnostics is None:
            self._verdict.hide()
            return
        text, tone = verdict_headline(result.diagnostics)
        ink, strip = VERDICT_TONES[tone]
        self._verdict.setText(text)
        self._verdict.setProperty('tone', tone)
        self._verdict.setStyleSheet(
            f'color: {ink}; background: {strip}; font-size: 13px; font-weight: bold; padding: 4px 8px;'
        )
        self._verdict.show()

    def _hide_replicates_table(self) -> None:
        self._replicates_heading.hide()
        self._replicates_table.hide()

    def _show_replicates_table(self, result: FitResult) -> None:
        """One row per replicate the fit was given: its own fit's binding constants, R², p-value and whether it was used.

        The p-value is the replicate's own share of the test that decides
        whether every replicate needs the same binding constants; a set too
        small to test, and a replicate left out for its scatter, show none.
        """
        fits = result.replica_fits
        if not fits:
            self._hide_replicates_table()
            return
        used = set(fit_replica_ids(result) or ())
        p_values = (result.metadata.get('replicate_test') or {}).get('p_values') or {}
        failures = result.metadata.get('replica_failures') or {}
        # The log₁₀ twins name the binding constants and the unit each is held in.
        ka = [(spec.key, spec.unit) for spec in summarize_parameters(result) if spec.is_log]

        headers = [_REPLICATE_TABLE_HEADERS[0]]
        # A header is painted as plain text, so the display labels are flattened.
        headers += [
            plain_label(f'{fmt_param(key)} [{fmt_unit_html(unit)}]' if unit else fmt_param(key)) for key, unit in ka
        ]
        headers += list(_REPLICATE_TABLE_HEADERS[1:])
        rows, tooltips = [], []
        for rf in fits:
            rid = rf.metadata.get('replica_id')
            p = p_values.get(rid)
            row = [_replica_name(rid, self._replica_ids)]
            row += own_estimates(rf, [key for key, _ in ka], html=True)
            row += [
                fmt_r2(rf.r_squared),
                _NO_VALUE if p is None else f'{p:.2g}',
                'used' if rid in used else 'left out',
            ]
            rows.append(row)
            tooltips.append(None if rid in used else failures.get(rid))
        self._replicates_table.show_rows(headers, rows)
        for row, tooltip in enumerate(tooltips):
            if tooltip:
                self._replicates_table.cellWidget(row, len(headers) - 1).setToolTip(tooltip)
        self._replicates_heading.show()
        self._replicates_table.show()

    def _render_hidden_samples(self) -> None:
        """The samples view of a sensitivity run that no longer matches: its note instead of its numbers."""
        self._set_view(_REPORT_TITLE, (_REPORT_TITLE, _REPORT_HELP_HTML), _SAMPLES_QUALITY_HELP_HTML, True)
        self._table.setRowCount(0)
        self._footnote.hide()
        self._hide_diagnostics()
        self._hide_replicates_table()
        self._caption.setText(self._sensitivity_note)
        self._caption.show()
        for label in self._sample_rows:
            label.setText(_NO_VALUE)

    def _render_samples(self, result: SensitivityResult, values: dict[str, np.ndarray], fitted: np.ndarray) -> None:
        """The samples view of *result*, over the samples *fitted* marks."""
        self._set_view(_REPORT_TITLE, (_REPORT_TITLE, _REPORT_HELP_HTML), _SAMPLES_QUALITY_HELP_HTML, True)
        self._hide_diagnostics()
        self._hide_replicates_table()
        samples = {key: v[fitted] for key, v in values.items()}
        rows = summarize_parameters(result.baseline_fit)
        self._table.show_rows(_SAMPLE_HEADERS, _sample_table(rows, samples))
        starred = [key for key in result.degenerate_keys if key in samples]
        self._set_footnote(self._star_rows(rows, starred, _SAMPLES_DEGENERATE_TAIL))
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


def _replica_name(replica_id: str | None, order: Sequence[str] | None) -> str:
    """One replicate's display label — its letter in the Replicates panel, or its id when unknown."""
    order = list(order or ())
    if replica_id in order:
        return _display_label(order.index(replica_id))
    return _NO_VALUE if replica_id is None else str(replica_id)
