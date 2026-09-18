"""Read-only summary of a fit, or of a sensitivity run's samples, under the plot tabs."""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np
from PyQt6.QtCore import QSize, Qt
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
from core.pipeline.fit_pipeline import (
    FitResult,
    ParameterSummary,
    fit_replica_ids,
    input_replica_ids,
    parameters_on_bound,
    summarize_parameters,
)
from core.pipeline.sensitivity import SensitivityMode, SensitivityResult
from core.pipeline.varpro import LEVEL
from core.units import Q_
from gui.plotting.colors import INK_2
from gui.plotting.labels import (
    SPLIT_MARK,
    SPLIT_NOTE,
    UNSOLVABLE_NOTE,
    fmt_bound_note,
    fmt_interval_html,
    fmt_log10,
    fmt_param,
    fmt_r2,
    fmt_unit_html,
    plain_label,
)
from gui.widgets.info_button import InfoGroupBox
from gui.widgets.replica_panel import _display_label, describe_replicates

_LEVEL_TEXT = f'{LEVEL * 100:g} %'

_PARAMS_TITLE = 'Fitted Parameters'
_PARAMS_HELP_HTML = f"""
<h3>Fitted Parameters &mdash; columns</h3>

<p><b>Estimate</b> &mdash; the least-squares fit: the parameter values that
bring the model closest to the data you fitted, and the ones the curve on the
plot is drawn from. For a fit of several replicates, that is the fit of the
average of the replicates it used.</p>

<p><b>{_LEVEL_TEXT} interval</b> &mdash; for each association constant, the
K<sub>a</sub> values that still describe your data. Every K<sub>a</sub> in the
interval is refitted with all other parameters free, and kept when the resulting
misfit is not significantly worse than the best fit&rsquo;s (an F test at
{_LEVEL_TEXT}). It is a statement about K<sub>a</sub> given this model and the
inputs you entered &mdash; the <b>Ka Sensitivity</b> tab shows how far errors in
those inputs move it. The signal parameters get no interval: only K<sub>a</sub>
is being tested.</p>

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

<p><b>log<sub>10</sub>(K<sub>a</sub>) row</b> &mdash; each association constant
is repeated as its log<sub>10</sub>. Its estimate and interval are the row above
read on a log scale, which is exact.</p>

<p><b>Replicates: median</b> and <b>Replicates: min - max</b> &mdash; shown when
each replicate was fitted separately and at least two entered the fit: the
middle, lowest and highest value across those replicates&rsquo; <i>own</i> fits.
They say how far the replicates disagree, which is a different question from the
interval: the interval says how well the fitted data pin K<sub>a</sub> down.
Replicates left out of the fit are not counted here; the Replicates table below
lists every replicate.</p>

<p><b>Rows marked *</b> &mdash; at the fitted K<sub>a</sub>, the data fix only a
combination of these signal parameters, not each one on its own: many different
sets of their values draw exactly the same curve. The value shown is one member
of that family. It reconstructs the curve correctly and must not be read as a
measurement of that one coefficient.</p>
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

<p><b>Replicates used</b> &mdash; how many of the replicates you switched on
entered the fit. A replicate is left out when its own best fit needs a
K<sub>a</sub> the others do not share; the tooltip names each one and why. The
test can only notice a replicate whose own data pin K<sub>a</sub> down &mdash;
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


#: The summary table's columns in the fit view. The two replicate columns are
#: dropped when no row has replicate statistics — a fit of one signal, or a
#: per-replicate fit that used a single replicate.
_FIT_HEADERS = ('Parameter', 'Estimate', f'{_LEVEL_TEXT} interval', 'Units')
_REPLICATE_HEADERS = ('Replicates: median', 'Replicates: min - max')
#: Where the interval sits in a fit table row; the replicate columns follow it.
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


def _fmt(magnitude: float, unit_str: str) -> str:
    """Pint HTML value with the trailing unit stripped (units have a column)."""
    if unit_str:
        return f'{Q_(magnitude, unit_str):.3g~H}'.rsplit(' ', 1)[0]
    return f'{magnitude:.3g}'


def _row_formatter(spec: ParameterSummary, stats: dict | None) -> Callable[[float], str]:
    """How every number of one row is written: a log₁₀ reading, or a value in the row's unit."""
    if spec.is_log:
        return lambda value: fmt_log10(value, stats)
    return lambda value: _fmt(value, spec.unit)


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


def _sentence(note: str) -> str:
    """One of the shared notes as a sentence of its own; they are written to follow a parameter name."""
    return f'{note[0].upper()}{note[1:]}'


#: What the mark on a split interval means, wherever that mark is shown.
_SPLIT_FOOTNOTE = f'{SPLIT_MARK} {_sentence(SPLIT_NOTE)}'


def _interval_tooltip(spec: ParameterSummary) -> str:
    """What the bracket of one row does not show: separate stretches, and an open side no data can close."""
    notes = []
    if spec.interval_split:
        notes.append(_SPLIT_FOOTNOTE)
    if any(spec.interval_unsolvable):
        notes.append(_sentence(UNSOLVABLE_NOTE))
    return ' '.join(notes)


def _fit_table(rows: list[ParameterSummary], ka_keys: set[str], reported: bool) -> tuple[list[str], list[list[str]]]:
    """Headers and cell texts of the fit view's table.

    The replicate columns appear only where a row fills them, so a fit of one
    signal is not shown two empty columns.
    """
    with_replicates = any(spec.replicates is not None for spec in rows)
    headers = [*_FIT_HEADERS[:-1]]
    if with_replicates:
        headers += list(_REPLICATE_HEADERS)
    headers.append(_FIT_HEADERS[-1])

    cells = []
    for spec in rows:
        fmt = _row_formatter(spec, spec.replicates)
        row = [_row_label(spec), fmt(spec.estimate), _interval_cell(spec, fmt, ka_keys, reported)]
        if with_replicates:
            d = spec.replicates
            row += [_NO_VALUE, _NO_VALUE] if d is None else [fmt(d['median']), _fmt_range(d['min'], d['max'], fmt)]
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


class ParameterTable(QTableWidget):
    """Read-only table of HTML cells, sized to its contents.

    The headers come with the rows, so the same table renders the fit view, the
    samples view and the per-replicate Replicates table.

    The table is as tall as its header and all of its rows, and the pane around
    it scrolls: a table that scrolled inside a scrolling pane would put a row
    behind a scrollbar of its own.
    """

    def __init__(self, parent=None):
        super().__init__(0, 0, parent)
        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Panning by pixel, not by column: a column wider than the table can
        # still be read from end to end.
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
        """Put *html* in one cell, as a centred rich-text label."""
        lbl = QLabel(html)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        self.setCellWidget(row, col, lbl)

    def autosize_columns(self) -> None:
        """Give each column the width its own widest cell needs, and share out any width left over.

        A column is never narrower than its contents. A number cut off mid-digit
        still reads as a number, and the horizontal scrollbar pans between whole
        columns rather than widening one, so there would be no way back to the
        rest of the value. Where the columns together outgrow the table, that
        scrollbar reaches them.

        The spare width is measured against the width the table has now, so it
        is shared out again whenever the table is resized.
        """
        # resizeColumnsToContents() ignores widgets set via setCellWidget(),
        # so we measure each QLabel's sizeHint() directly.
        n_cols = self.columnCount()
        n_rows = self.rowCount()
        if not n_cols:
            return
        fm = self.horizontalHeader().fontMetrics()
        widths = []
        for col in range(n_cols):
            item = self.horizontalHeaderItem(col)
            w = fm.horizontalAdvance(item.text() if item is not None else '') + 24
            for row in range(n_rows):
                widget = self.cellWidget(row, col)
                if widget is not None:
                    w = max(w, widget.sizeHint().width() + 16)
            widths.append(w)

        spare = max((self.viewport().width() - sum(widths)) // n_cols, 0)
        for col, w in enumerate(widths):
            self.setColumnWidth(col, w + spare)
        self.updateGeometry()


def and_join(items: list[str]) -> str:
    """``a``, ``a and b``, ``a, b and c``."""
    return items[0] if len(items) == 1 else f'{", ".join(items[:-1])} and {items[-1]}'


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
        return f'{n} of {total} {noun} could not be fitted and {are} left out.'
    if result.n_success == result.n_total:
        return f'{n} of {total} {noun} {"was" if n == 1 else "were"} not fitted before the analysis was stopped and {are} left out.'
    return (
        f'{n} of {total} {noun} have no fit, either because the analysis was stopped before reaching them or '
        f'because they could not be fitted, and {are} left out.'
    )


def same_inputs(a: dict, b: dict) -> bool:
    """Whether two assay-condition dicts hold the same inputs, compared in base units."""
    if a.keys() != b.keys():
        return False
    for key, x in a.items():
        y = b[key]
        if hasattr(x, 'dimensionality') and hasattr(y, 'dimensionality'):
            if x.dimensionality != y.dimensionality:
                return False
            if not np.isclose(x.to_base_units().magnitude, y.to_base_units().magnitude, rtol=1e-9, atol=0.0):
                return False
        elif x != y:
            return False
    return True


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
    own = 'its own fit needs' if len(left_out[1]) == 1 else 'their own fits need'
    failed = all(set(left_out[1]) <= set(r.metadata.get('replica_failures') or {}) for r in (baseline, fit))
    why = f', as {own} a different Ka than the other replicates share' if failed else ''
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


def _relation(rows: list[ParameterSummary], baseline: FitResult, fit: FitResult, starred: list[str]) -> str:
    """Whether the samples table's estimates match *fit*, or why they can differ."""
    reasons = _differences(baseline, fit)
    if reasons:
        return f'It can differ from the fit on the Fit Curve tab because {and_join(reasons)}.'
    theirs = {spec.key: _fmt(spec.estimate, spec.unit) for spec in summarize_parameters(fit) if not spec.is_log}
    differing = [
        fmt_param(spec.key)
        for spec in rows
        if not spec.is_log and spec.key not in starred and _fmt(spec.estimate, spec.unit) != theirs.get(spec.key)
    ]
    which = 'unstarred estimates' if starred else 'estimates'
    if not differing:
        return f'Its {which} match the fit on the Fit Curve tab to the digits shown.'
    return (
        f'Its estimate of {and_join(differing)} differs from the fit on the Fit Curve tab although the two use the '
        'same data, inputs, bounds and replicate handling.'
    )


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
    - ``InfoGroupBox`` with a caption, a :class:`ParameterTable`, a footnote and
      — for a per-replicate fit — a Replicates table.
    - ``InfoGroupBox("Fit Quality")``.

    Both sit on a page that scrolls. The pane shares the height of the window
    with the plot tabs above it, and a nine-row table with its footnote is
    taller than the share it gets: the page scrolls so every row and the whole
    footnote can be read, at any height the pane is dragged to.

    Two views share the layout. The *fit view* shows the fit: its estimate per
    parameter, the confidence interval of every binding constant it was free to
    move, the spread of the replicates' own fits where there are several, and
    Fit Quality gives RMSE, R² and the replicates used. The *samples view*
    (:meth:`show_samples` on, with a SOBOL result from :meth:`set_sensitivity`
    that holds fitted samples) shows the fitted parameters across that run's
    samples: ``Estimate`` is the run's own fit with the inputs as entered, the
    other columns summarise every fitted sample, the rows of ``degenerate_keys``
    are starred as marginal summaries, and Fit Quality describes the samples.
    With the samples view requested but nothing to summarise (no run, a run
    still going, a heatmap, or no fitted samples), the fit view shows with a
    caption saying why. Rows always come from
    :func:`~core.pipeline.fit_pipeline.summarize_parameters`, shared with the
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

        self._caption = QLabel()
        self._caption.setWordWrap(True)
        self._caption.setTextFormat(Qt.TextFormat.RichText)
        self._table = ParameterTable()
        self._footnote = QLabel()
        self._footnote.setWordWrap(True)
        self._footnote.setTextFormat(Qt.TextFormat.RichText)
        self._replicates_heading = QLabel('Replicates')
        self._replicates_table = ParameterTable()
        for label in (self._caption, self._footnote, self._replicates_heading):
            label.setStyleSheet(f'color: {INK_2}; font-size: 13px;')
        params_layout = QVBoxLayout(self._params_group)
        for widget in (
            self._caption,
            self._table,
            self._footnote,
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
        for text, label in zip(
            ('RMSE:', 'R²:', 'Replicates used:', 'Samples with a fit:', 'Median R²:', 'R² range:'),
            self._fit_rows + self._sample_rows,
        ):
            self._quality_form.addRow(text, label)

        page = QWidget()
        page_layout = QHBoxLayout(page)
        # The groups keep the inset they had beside the pane's edges, and give up
        # the one above and below: the splitter shares the window's height by
        # what each pane prefers, and the plot tabs above have none to spare.
        inset = page_layout.contentsMargins().left()
        page_layout.setContentsMargins(inset, 0, inset, 0)
        page_layout.addWidget(self._params_group, stretch=3)
        page_layout.addWidget(self._quality_group, stretch=1)
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
        for label in self._sample_rows:
            self._quality_form.setRowVisible(label, samples)

    def _render_fit(self, note: str) -> None:
        """The fit view; any note on the fit itself leads the caption, followed by *note* (possibly empty)."""
        self._set_view(_PARAMS_TITLE, ('Fitted Parameters — columns', _PARAMS_HELP_HTML), _FIT_QUALITY_HELP_HTML, False)
        result = self._fit
        hidden = self._fit_note if result is not None else None
        block = hidden or (self._unchecked if result is not None else None)
        self._footnote.hide()
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
            return

        rows = summarize_parameters(result)
        # summarize_parameters gives every binding constant a log₁₀ twin, and
        # only a binding constant: the twins name the keys an interval is
        # reported for.
        ka_keys = {spec.key for spec in rows if spec.is_log}
        headers, cells = _fit_table(rows, ka_keys, result.intervals is not None)
        self._table.show_rows(headers, cells)
        self._set_footnote(
            self._star_rows(
                rows, [spec.key for spec in rows if spec.degenerate and not spec.is_log], _FIT_DEGENERATE_TAIL
            ),
            self._note_intervals(rows),
        )

        legacy = _LEGACY_NOTE if ka_keys and result.intervals is None else ''
        on_bound = fmt_bound_note(parameters_on_bound(result))
        caption = ' '.join(part for part in (block, legacy, on_bound, note) if part)
        self._caption.setText(caption)
        self._caption.setVisible(bool(caption))

        self._rmse_label.setText(f'{Q_(result.rmse, "au"):.3g~H}')
        self._r2_label.setText(fmt_r2(result.r_squared))
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
        for row, spec in enumerate(rows):
            tooltip = _interval_tooltip(spec)
            if tooltip:
                self._table.cellWidget(row, _INTERVAL_COLUMN).setToolTip(tooltip)
            split = split or spec.interval_split
        return _SPLIT_FOOTNOTE if split else ''

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

    def _hide_replicates_table(self) -> None:
        self._replicates_heading.hide()
        self._replicates_table.hide()

    def _show_replicates_table(self, result: FitResult) -> None:
        """One row per replicate the fit was given: its own fit's binding constants, R², p-value and whether it was used.

        The p-value is the replicate's own share of the test that decides
        whether every replicate needs the same binding constants; a set too
        small to test shows none.
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
            row += [_fmt_own(rf, key, unit) for key, unit in ka]
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
        self._hide_replicates_table()
        self._caption.setText(self._sensitivity_note)
        self._caption.show()
        for label in self._sample_rows:
            label.setText(_NO_VALUE)

    def _render_samples(self, result: SensitivityResult, values: dict[str, np.ndarray], fitted: np.ndarray) -> None:
        """The samples view of *result*, over the samples *fitted* marks."""
        self._set_view(_REPORT_TITLE, (_REPORT_TITLE, _REPORT_HELP_HTML), _SAMPLES_QUALITY_HELP_HTML, True)
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


def _fmt_own(result: FitResult, key: str, unit: str) -> str:
    """One replicate's own value of a parameter, with the unit stripped (the header names it)."""
    value = result.parameters.get(key)
    if value is None:
        return _NO_VALUE
    magnitude = float(value.magnitude) if hasattr(value, 'magnitude') else float(value)
    return _fmt(magnitude, unit)
