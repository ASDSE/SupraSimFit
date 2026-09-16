"""Read-only summary of a fit, or of a sensitivity run's samples, under the plot tabs."""

from __future__ import annotations

from dataclasses import replace
from typing import Sequence

import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from core.pipeline.fit_pipeline import (
    FitResult,
    ParameterSummary,
    fit_replica_ids,
    fitted_representative_index,
    input_replica_ids,
    summarize_parameters,
)
from core.pipeline.sensitivity import SensitivityMode, SensitivityResult
from core.units import Q_
from gui.plotting.labels import fmt_param, fmt_unit_html
from gui.widgets.info_button import InfoGroupBox
from gui.widgets.replica_panel import describe_replicates

_PARAMS_TITLE = 'Fitted Parameters'
_PARAMS_HELP_HTML = """
<h3>Fitted Parameters &mdash; columns</h3>

<p><b>Estimate</b> &mdash; the representative fit: one actual fit from the
valid pool, the one drawn on the plot and named in the Representative selector.
A fit of the averaged signal chooses its highest-R&sup2; attempt; a
per-replicate fit chooses, among each replicate&rsquo;s best attempt, the one
with the highest R&sup2; against the average of the replicates it used.
Replicates left out of the fit play no part in its R&sup2; or RMSE. It is a
point estimate among a distribution, not a proven optimum.</p>

<p><b>Median &plusmn; MAD</b> and <b>Mean &plusmn; SD</b> &mdash; the centre and
spread of each parameter across <i>all</i> valid fits. <b>MAD</b> is the median
absolute deviation, median(|x<sub>i</sub> &minus; median|): a robust spread that
ignores outlier fits (reported unscaled). <b>SD</b> is the sample standard
deviation (N&minus;1) &mdash; the ordinary spread, pulled by outliers and
assuming a roughly symmetric distribution. (The <i>median</i> absolute deviation
is not the <i>mean</i> absolute deviation mean(|x<sub>i</sub> &minus; mean|); we
use the median form because it pairs with the robust median.) None of these
change the Estimate or the curve.</p>

<p><b>68% Range</b> &mdash; the interval [P16, P84] holding the central 68% of
the fits. For a bell-shaped distribution this equals mean&nbsp;&plusmn;&nbsp;1
SD, but it is read straight from the fits, so it stays correct &mdash; and
reveals any skew &mdash; even when they are not bell-shaped. <b>Min-Max Range</b>
is the full extent of the fitted values &mdash; this is the range quoted beside
the Estimate in the plot annotation and the exported reports.</p>

<p><b>log<sub>10</sub>(K<sub>a</sub>) row</b> &mdash; for each association
constant, a second row reports log<sub>10</sub>(K<sub>a</sub>). Its statistics
come from the per-fit log<sub>10</sub> values directly &mdash; never from the
log of a K<sub>a</sub> spread, which would be meaningless.</p>

<p><b>What the spread means (and doesn&rsquo;t).</b> These numbers describe how
<i>reproducibly the optimiser converges</i> across its many starting points on
the same data &mdash; not the experimental uncertainty of your measurement. A
tight spread means the fit reliably lands on the same value; it does <b>not</b>
by itself mean the parameter is known to that precision. With per-replica
fitting the pool holds each replicate&rsquo;s own fits, so the spread also
reflects how far the replicates&rsquo; fits differ; it is still not a confidence
interval. The wide spread on the signal coefficients (I<sub>0</sub>,
I<sub>D</sub>, I<sub>HD</sub>) is the clearest case: it is not uncertainty, it
is the model telling you those coefficients are not individually determined
&mdash; only K<sub>a</sub> is.</p>

<p><b>How precisely K<sub>a</sub> is known.</b> The <b>Identifiability</b> tab
gives the 95% confidence interval: the K<sub>a</sub> values whose best fit to
your data is not significantly worse than the best one. On the demo data the
68% Range lies within 0.1% of the estimate, while that interval reaches &minus;44%
to +182%. The
interval assumes the model and the inputs you entered are right; the <b>Ka
Sensitivity</b> tab shows how far errors in those inputs move K<sub>a</sub>.
Help &#9656; Reading the plots explains both tabs.</p>
"""


_FIT_QUALITY_HELP_HTML = """
<h3>Fit Quality</h3>

<p><b>RMSE</b> (root mean squared error) &mdash; average distance between
the fitted curve and the data points, in signal units. Lower is better.
Compare it to the noise level in your data: if RMSE is similar to the
noise floor, the fit is explaining the data about as well as possible.</p>

<p><b>R&sup2;</b> (coefficient of determination) &mdash; fraction of the
data variance explained by the fit, from 0 to 1. Close to 1, small
differences still matter: on the demo data the 95% confidence interval for
K<sub>a</sub> on the Identifiability tab ends where the best R&sup2; drops from
0.9941 to 0.9908. A high R&sup2; does not show that the model describes the
data: check the Fit Curve for runs of points on one side of the curve.</p>

<p><b>Fits passing</b> &mdash; how many of the multi-start trials cleared
the minimum&nbsp;R&sup2; floor (plus the optional RMSE trim, if enabled) and
form the valid pool. A low ratio (e.g. 5/100) means most starting points led
the optimiser to poor solutions &mdash; consider widening bounds or
increasing the trial budget.</p>
"""


_SAMPLES_QUALITY_HELP_HTML = """
<h3>Fit Quality &mdash; across the samples</h3>

<p><b>Samples with a fit</b> &mdash; how many of the analysis&rsquo;s samples
produced a fit, out of all its samples. Only these enter the table.</p>

<p><b>Below Min&nbsp;R&sup2;</b> &mdash; how many of those samples have a best fit
below the Min&nbsp;R&sup2; the analysis used: the one set in the Fit panel when it
started. They stay in every column of the table.</p>

<p><b>Median R&sup2;</b> and <b>R&sup2; range</b> &mdash; the middle value and the
lowest and highest R&sup2; of the samples&rsquo; best fits.</p>
"""


_REPORT_TITLE = 'Fitted Parameters Across the Samples'
_REPORT_HELP_HTML = """
<h3>Fitted Parameters Across the Samples</h3>

<p><b>Estimate</b> &mdash; the fit the sensitivity analysis makes with the inputs
exactly as you entered them, the same way it fits each sample. The text above the
table says whether it matches the fit on the Fit Curve tab, and why not when it
can differ.</p>

<p>The other columns summarise the best fit of every sample in the analysis,
including fits below the Min&nbsp;R&sup2;. Each sample refits your data with the
inputs moved within the uncertainty you set, so these columns show how far each
parameter moves when the inputs are uncertain. <b>Median &plusmn; MAD</b>,
<b>Mean &plusmn; SD</b>, <b>68% Range</b> and <b>Min-Max Range</b> are the same
statistics as in the fit&rsquo;s own table on the other tabs.</p>

<p><b>Rows marked *</b> &mdash; the data fix only a combination of these signal
parameters, not each one on its own: many different sets of their values draw
the same curve. Each such row is a <i>marginal summary</i>. It shows how that one
value spread across the samples, not how precisely the data determine it. Where
many fits are equally good, each fit settles on one of them, so a narrow spread
here, even 0&nbsp;&plusmn;&nbsp;0, does not mean the value is well determined.</p>
"""


# Merged stat columns: (header, (central_key, spread_key)) from ensemble.describe().
# Rendered as a single "central ± spread" cell; the active pair is bold-emphasised.
_STAT_COLUMNS = (('Median ± MAD', ('median', 'mad')), ('Mean ± SD', ('mean', 'std')))
_P68_HEADER = '68% Range'  # central 68% interval [P16, P84]
_RANGE_HEADER = 'Min-Max Range'
_COLUMN_HEADERS = ('Parameter', 'Estimate') + tuple(h for h, _ in _STAT_COLUMNS) + (_P68_HEADER, _RANGE_HEADER, 'Units')
# Columns: 0 Parameter | 1 Estimate | 2 Median±MAD | 3 Mean±SD | 4 68% Range | 5 Min-Max Range | 6 Units.
_STAT_COL0 = 2
_P68_COL = _STAT_COL0 + len(_STAT_COLUMNS)
_RANGE_COL = _P68_COL + 1
_UNITS_COL = _RANGE_COL + 1


def _fmt(magnitude: float, unit_str: str) -> str:
    """Pint HTML value with the trailing unit stripped (units have a column)."""
    if unit_str:
        return f'{Q_(magnitude, unit_str):.3g~H}'.rsplit(' ', 1)[0]
    return f'{magnitude:.3g}'


def _fmt_r2(value: float, floor: float | None = None) -> str:
    """R² to four decimals, with more where four would round it up to 1 or across *floor*.

    A value below 1 or below *floor* then always reads below it, so a shown R²
    never appears to meet a mark it misses.
    """
    for digits in range(4, 13):
        text = f'{value:.{digits}f}'
        shown = float(text)
        if (value >= 1.0 or shown < 1.0) and (floor is None or (value < floor) == (shown < floor)):
            break
    return text


def _distinct_r2_texts(indices: list[int], values: list[float]) -> list[str]:
    """R² texts for the attempts *indices*, with the fewest decimals (four to six) that tell them apart.

    Attempts whose R² differs at the sixth decimal read differently, so an item
    does not look identical to another attempt it would switch to. Attempts
    closer than that fit the data equally well for any practical purpose and
    read the same.
    """
    for digits in range(4, 7):
        texts = [f'{v:.{digits}f}' for v in values]
        if all(
            texts[i] != texts[j]
            for i in range(len(values))
            for j in range(i)
            if indices[i] != indices[j] and values[i] != values[j]
        ):
            break
    return texts


def _fmt_pair(central: float, spread: float, unit_str: str) -> str:
    """Merged 'central ± spread' cell (units stripped; shown in the Units column)."""
    return f'{_fmt(central, unit_str)} ± {_fmt(spread, unit_str)}'


def _fmt_range(lo: float, hi: float, unit_str: str) -> str:
    """Merged '[min, max]' range cell."""
    return f'[{_fmt(lo, unit_str)}, {_fmt(hi, unit_str)}]'


class ParameterTable(QTableWidget):
    """Read-only table of :func:`~core.pipeline.fit_pipeline.summarize_parameters` rows.

    Columns: Parameter | Estimate | Median \u00b1 MAD | Mean \u00b1 SD | 68% Range |
    Min-Max Range | Units.
    """

    def __init__(self, parent=None):
        super().__init__(0, len(_COLUMN_HEADERS), parent)
        self.setHorizontalHeaderLabels(list(_COLUMN_HEADERS))
        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

    def show_rows(self, rows: list[ParameterSummary]) -> None:
        """Render *rows*, one table row each, and size the columns to their contents."""
        # Removing the rows hides their cell widgets at once; a replaced cell
        # widget would stay on screen until its deferred deletion.
        self.setRowCount(0)
        self.setRowCount(len(rows))
        for row, spec in enumerate(rows):
            # Log rows are dimensionless; their source unit only labels them.
            unit_html = fmt_unit_html(spec.unit) if spec.unit else ''
            if spec.is_log:
                label = f'log₁₀({fmt_param(spec.key)} / {unit_html})' if unit_html else f'log₁₀({fmt_param(spec.key)})'
            else:
                label = fmt_param(spec.key)
            value_unit = '' if spec.is_log else spec.unit

            self._set_cell(row, 0, label)
            self._set_cell(row, 1, _fmt(spec.estimate, value_unit))
            d = spec.stats
            if d is None:
                for col in range(_STAT_COL0, _RANGE_COL + 1):
                    self._set_cell(row, col, '—', tooltip='No fit pool stored for this result (e.g. a legacy import).')
            else:
                for offset, (_, (ck, sk)) in enumerate(_STAT_COLUMNS):
                    self._set_cell(row, _STAT_COL0 + offset, _fmt_pair(d[ck], d[sk], value_unit))
                self._set_cell(row, _P68_COL, _fmt_range(d['p16'], d['p84'], value_unit))
                self._set_cell(row, _RANGE_COL, _fmt_range(d['min'], d['max'], value_unit))
            self._set_cell(row, _UNITS_COL, unit_html if value_unit else '—')
        self.autosize_columns()

    def _set_cell(self, row: int, col: int, html: str, *, tooltip: str | None = None) -> None:
        lbl = QLabel(html)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        if tooltip:
            lbl.setToolTip(tooltip)
        self.setCellWidget(row, col, lbl)

    def autosize_columns(self) -> None:
        """Size each column to its widest cell, then spread any spare width evenly across the columns."""
        # resizeColumnsToContents() ignores widgets set via setCellWidget(),
        # so we measure each QLabel's sizeHint() directly, then spread any
        # leftover viewport width evenly across columns.
        n_cols = self.columnCount()
        n_rows = self.rowCount()
        fm = self.horizontalHeader().fontMetrics()
        widths = []
        for col in range(n_cols):
            item = self.horizontalHeaderItem(col)
            header_text = item.text() if item is not None else ''
            w = fm.horizontalAdvance(header_text) + 24
            for row in range(n_rows):
                widget = self.cellWidget(row, col)
                if widget is not None:
                    w = max(w, widget.sizeHint().width() + 16)
            widths.append(w)

        extra = max(0, (self.viewport().width() - sum(widths)) // n_cols)
        for col, w in enumerate(widths):
            self.setColumnWidth(col, w + extra)


def and_join(items: list[str]) -> str:
    """``a``, ``a and b``, ``a, b and c``."""
    return items[0] if len(items) == 1 else f'{", ".join(items[:-1])} and {items[-1]}'


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
    per_replica = baseline.uncertainty_source == 'replicate'
    if per_replica != (fit.uncertainty_source == 'replicate'):
        ways = ('each replicate separately', 'the average of the replicates')
        ours, theirs = ways if per_replica else ways[::-1]
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
    fitted_index = fitted_representative_index(fit)
    if fitted_index is not None and fitted_index != fit.representative_index:
        reasons.append('that fit shows an attempt you picked instead of the one the fit chose')
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
    why = f', as neither found an acceptable fit for {"it" if len(left_out[1]) == 1 else "them"}' if failed else ''
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
        'same data, inputs, bounds and replicate handling: each is its own search for the best fit.'
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
    spread = f'The other columns cover {f"all {n}" if n == total else f"the {n}"} samples'
    spread += '' if n == total else ' that have a fit'
    if result.sample_r2 is not None and result.floor is not None and np.isfinite(result.floor):
        below = int(np.sum(np.asarray(result.sample_r2, dtype=float)[fitted] < result.floor))
        threshold = f'the Min R² this analysis used ({result.floor:g})'
        if below:
            spread += f', including the {below} whose best fit falls below {threshold}.'
        else:
            spread += f', and the best fit of every one meets {threshold}.'
    else:
        spread += '.'
    parts = [
        'The estimate is the fit this analysis makes with the inputs as you entered them, the same way it fits '
        'each sample.',
        _comparison(rows, result.baseline_fit, fit, starred, replica_ids),
        spread,
    ]
    if n < total:
        parts.append(unfitted_sentence(result, total - n, total, 'samples'))
    return ' '.join(part for part in parts if part)


_REP_TOOLTIP = (
    "<qt>Which valid fit is reported and drawn. Starts at the fit's own choice.<br>"
    'Pick another, or click a point in the Distributions tab.</qt>'
)


class FitSummaryWidget(QWidget):
    """Read-only summary under the plot tabs: the fitted parameters and their quality.

    Layout
    ------
    - ``InfoGroupBox`` with a Representative selector, a caption, a
      :class:`ParameterTable` and a footnote.
    - ``InfoGroupBox("Fit Quality")``.

    Two views share the layout. The *fit view* shows the fit: ``Estimate`` is
    its representative, the other columns summarise its valid-fit pool, and
    Fit Quality gives RMSE, R² and the passing count. The *samples view*
    (:meth:`show_samples` on, with a SOBOL result from :meth:`set_sensitivity`
    that holds fitted samples) shows the fitted parameters across that run's
    samples: ``Estimate`` is the run's own fit with the inputs as entered, the
    other columns cover every fitted sample (those below the R² floor
    included), the rows of ``degenerate_keys`` are starred as marginal
    summaries, and Fit Quality describes the samples. The selector chooses
    among one fit's attempts, so it is hidden there. With the samples view
    requested but nothing to summarise (no run, a run still going, a heatmap,
    or no fitted samples), the fit view shows with a caption saying why. Rows always come from
    :func:`~core.pipeline.fit_pipeline.summarize_parameters`, shared with the
    plot annotation and the exports.

    A fit or a sensitivity run that no longer matches the loaded selection is
    hidden with :meth:`show_mismatch`: its view shows the note in place of its
    numbers, and the selector is disabled. The result is kept and shown again,
    unchanged, once the note is removed.
    """

    representative_selected = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Sticky "Selected" representative: the last fit picked from a
        # distribution-plot click, kept across Best/Median/Worst switches so the
        # user can compare and switch back. Reset when a new fit is displayed.
        self._plot_selected_index: int | None = None
        self._last_result_id: str | None = None
        self._fit: FitResult | None = None
        self._sensitivity: SensitivityResult | None = None
        self._running: SensitivityMode | None = None
        self._samples_view = False
        self._fit_note: str | None = None  # why the fit is hidden
        self._sensitivity_note: str | None = None  # why the sensitivity run is hidden
        self._unchecked: str | None = None  # why the fit's numbers could not be checked against data
        self._replica_ids: Sequence[str] | None = None

        self._params_group = InfoGroupBox(_PARAMS_TITLE, 'Fitted Parameters — columns', _PARAMS_HELP_HTML)

        # Representative selector: which actual fit is reported (drives the curve).
        self._rep_combo = QComboBox()
        # Size to the widest item so no label is ever truncated.
        self._rep_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._rep_combo.setMinimumContentsLength(14)
        self._rep_combo.setToolTip(_REP_TOOLTIP)
        self._rep_combo.currentIndexChanged.connect(self._on_rep_combo_changed)

        self._rep_row = QWidget()
        stats_row = QHBoxLayout(self._rep_row)
        stats_row.setContentsMargins(0, 0, 0, 0)
        stats_row.addWidget(QLabel('Representative:'))
        stats_row.addWidget(self._rep_combo)
        stats_row.addStretch(1)

        self._caption = QLabel()
        self._caption.setWordWrap(True)
        self._caption.setTextFormat(Qt.TextFormat.RichText)
        self._table = ParameterTable()
        self._footnote = QLabel()
        self._footnote.setWordWrap(True)
        self._footnote.setTextFormat(Qt.TextFormat.RichText)
        for label in (self._caption, self._footnote):
            label.setStyleSheet('color: #52514e; font-size: 13px;')
        params_layout = QVBoxLayout(self._params_group)
        for widget in (self._rep_row, self._caption, self._table, self._footnote):
            params_layout.addWidget(widget)

        self._quality_group = InfoGroupBox('Fit Quality', 'Fit Quality', _FIT_QUALITY_HELP_HTML)
        self._quality_form = QFormLayout(self._quality_group)
        self._rmse_label = QLabel('—')
        self._rmse_label.setTextFormat(Qt.TextFormat.RichText)
        self._r2_label = QLabel('—')
        self._passing_label = QLabel('—')
        self._fitted_label = QLabel()
        self._below_label = QLabel()
        self._median_r2_label = QLabel()
        self._r2_range_label = QLabel()
        self._fit_rows = (self._rmse_label, self._r2_label, self._passing_label)
        self._sample_rows = (self._fitted_label, self._below_label, self._median_r2_label, self._r2_range_label)
        for text, label in zip(
            ('RMSE:', 'R²:', 'Fits passing:', 'Samples with a fit:', 'Below Min R²:', 'Median R²:', 'R² range:'),
            self._fit_rows + self._sample_rows,
        ):
            self._quality_form.addRow(text, label)

        main_layout = QHBoxLayout(self)
        main_layout.addWidget(self._params_group, stretch=3)
        main_layout.addWidget(self._quality_group, stretch=1)
        self._render()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_result(self, result: FitResult, *, unchecked: str | None = None) -> None:
        """Show *result* as the fit, in the fit view and in the samples view's comparison.

        *unchecked* says why its numbers could not be checked against data: it
        is shown with them, and the selector is disabled.
        """
        # A new fit clears the sticky plot-selection; refreshes of the same
        # result (e.g. a re-selection) keep it.
        if result.id != self._last_result_id:
            self._plot_selected_index = None
            self._last_result_id = result.id
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
        """The loaded data's replicate ids in order, so captions name replicates as the Replicas panel does."""
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
        self._last_result_id = None
        self._plot_selected_index = None
        self._render()

    def note_plot_selection(self, index: int) -> None:
        """Remember *index* as the sticky 'Selected' representative.

        Called when the user clicks a fit in the distribution plots, so the
        choice survives Best/Median/Worst switches until the next fit.
        """
        self._plot_selected_index = int(index)

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
        self._rep_row.setVisible(not samples)
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
        caption = ' '.join(part for part in (block, note) if part)
        self._caption.setText(caption)
        self._caption.setVisible(bool(caption))
        self._footnote.hide()
        self._populate_rep_combo(None if hidden else result)
        if block:
            self._rep_combo.setEnabled(False)
        self._rep_combo.setToolTip(block or _REP_TOOLTIP)
        if result is None or hidden:
            self._table.setRowCount(0)
            for label in self._fit_rows:
                label.setText('—')
            return
        self._table.show_rows(summarize_parameters(result))
        self._rmse_label.setText(f'{Q_(result.rmse, "au"):.3g~H}')
        self._r2_label.setText(_fmt_r2(result.r_squared))
        passing = f'{result.n_passing} / {result.n_total}'
        if not result.parameter_samples:
            passing += '  (pool unavailable)'
        self._passing_label.setText(passing)

    def _render_hidden_samples(self) -> None:
        """The samples view of a sensitivity run that no longer matches: its note instead of its numbers."""
        self._set_view(_REPORT_TITLE, (_REPORT_TITLE, _REPORT_HELP_HTML), _SAMPLES_QUALITY_HELP_HTML, True)
        self._table.setRowCount(0)
        self._footnote.hide()
        self._caption.setText(self._sensitivity_note)
        self._caption.show()
        for label in self._sample_rows:
            label.setText('—')

    def _render_samples(self, result: SensitivityResult, values: dict[str, np.ndarray], fitted: np.ndarray) -> None:
        """The samples view of *result*, over the samples *fitted* marks."""
        self._set_view(_REPORT_TITLE, (_REPORT_TITLE, _REPORT_HELP_HTML), _SAMPLES_QUALITY_HELP_HTML, True)
        samples = {key: v[fitted] for key, v in values.items()}
        rows = summarize_parameters(replace(result.baseline_fit, parameter_samples=samples))
        self._table.show_rows(rows)
        starred = [key for key in result.degenerate_keys if key in samples]
        if starred:
            explanation = (
                f'Marginal summary. The data fix only a combination of {and_join([fmt_param(k) for k in starred])}, '
                'not each one on its own: many different sets of their values draw the same curve. Each starred '
                'row shows how that one value spread across the samples, not how precisely the data determine it, '
                'so even a spread of 0 ± 0 does not mean the value is well determined, and its estimate can differ '
                'widely from the fit on the Fit Curve tab.'
            )
            for row, spec in enumerate(rows):
                if spec.key in starred:
                    cell = self._table.cellWidget(row, 0)
                    cell.setText(f'{cell.text()}*')
                    cell.setToolTip(explanation)
            self._footnote.setText(f'* {explanation}')
        self._footnote.setVisible(bool(starred))
        fit = None if self._fit_note else self._fit
        self._caption.setText(_report_caption(result, fitted, rows, fit, starred, self._replica_ids))
        self._caption.show()

        n = int(fitted.sum())
        self._fitted_label.setText(f'{n} / {fitted.size}')
        r2 = None if result.sample_r2 is None else np.asarray(result.sample_r2, dtype=float)[fitted]
        if r2 is None:
            for label in self._sample_rows[1:]:
                label.setText('not recorded')
            return
        floor = result.floor if result.floor is not None and np.isfinite(result.floor) else None
        if floor is None:
            self._below_label.setText('no Min R² set')
        else:
            self._below_label.setText(f'{int(np.sum(r2 < floor))} of {n}  (Min R² used: {floor:g})')
        self._median_r2_label.setText(_fmt_r2(float(np.median(r2)), floor))
        self._r2_range_label.setText(f'[{_fmt_r2(r2.min(), floor)}, {_fmt_r2(r2.max(), floor)}]')

    # ------------------------------------------------------------------
    # Selector helpers
    # ------------------------------------------------------------------

    def _populate_rep_combo(self, result: FitResult | None) -> None:
        """Offer the fit's own choice, Best, Median, Worst, and the sticky Selected attempt.

        *Fit's choice* is the attempt the fit itself reported
        (:func:`fitted_representative_index`). A per-replicate fit reports one
        replicate's best attempt, which need not be the pool's highest R², so it
        comes first; when it is the top-R² attempt it appears once, as Best.
        Best/Worst are the highest/lowest R² attempts; Median is the attempt
        nearest the pool's median R². Selected is the last attempt clicked in
        the distribution plots, kept across switches so the user can compare and
        switch back to it. Each R² carries as many decimals as it takes to tell
        the listed attempts apart.

        The current item always names the attempt shown
        (``representative_index``). When no listed item does, a *Picked* item
        naming it is added, or a *Shown fit* item when the result does not say
        which attempt it shows or which attempt the fit chose. Without a fit or
        its pool the selector is empty and disabled.
        """
        self._rep_combo.blockSignals(True)
        self._rep_combo.clear()
        quality = None if result is None else result.quality_samples
        if quality and 'r_squared' in quality:
            r2 = np.asarray(quality['r_squared'], dtype=float)

            def in_pool(idx: int | None) -> bool:
                return idx is not None and 0 <= idx < r2.size

            cur = result.representative_index
            own = fitted_representative_index(result)
            best = int(np.argmax(r2))
            items = [] if not in_pool(own) or own == best else [("Fit's choice", int(own))]
            items += [
                ('Best', best),
                ('Median', int(np.argmin(np.abs(r2 - np.median(r2))))),
                ('Worst', int(np.argmin(r2))),
            ]
            sel = self._plot_selected_index
            if in_pool(sel):
                items.append(('Selected', int(sel)))
            if not in_pool(cur):
                items.insert(0, ('Shown fit', -1))
            elif all(idx != cur for _, idx in items):
                items.append(('Picked' if own is not None else 'Shown fit', int(cur)))
            values = [result.r_squared if idx < 0 else float(r2[idx]) for _, idx in items]
            for (label, idx), text in zip(items, _distinct_r2_texts([idx for _, idx in items], values)):
                self._rep_combo.addItem(f'{label} · R²={text}', idx)
            shown = cur if in_pool(cur) else -1
            self._rep_combo.setCurrentIndex(next(i for i, (_, idx) in enumerate(items) if idx == shown))
            self._rep_combo.setEnabled(True)
        else:
            self._rep_combo.addItem('—', -1)
            self._rep_combo.setEnabled(False)
        self._rep_combo.blockSignals(False)

    def _on_rep_combo_changed(self, _index: int) -> None:
        idx = self._rep_combo.currentData()
        if idx is not None and idx >= 0:
            self.representative_selected.emit(int(idx))
