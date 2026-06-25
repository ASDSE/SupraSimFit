"""Read-only display widget for FitResult statistics."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.optimizer.filters import compute_mean_params, compute_std_params
from core.pipeline.fit_pipeline import FitResult
from core.units import Q_, Quantity
from gui.plotting.labels import fmt_param, fmt_unit_html
from gui.widgets.info_button import InfoGroupBox

_HEADERS = ['Parameter', 'Median \u00b1 MAD', 'Mean \u00b1 STDEV', 'Units']

_UNCERTAINTY_HELP_HTML = """
<h3>The two &plusmn; summaries &mdash; what they mean</h3>

<p>Each parameter is summarised across <b>all accepted fits</b> the fitter
found (no re-fitting). Two pairs are shown so you can judge both the typical
value and how much it varies:</p>

<ul>
<li><b>Median &plusmn; MAD</b> &mdash; the <i>robust</i> summary. The median is
the middle value; the MAD (median absolute deviation) is the spread around it.
Both shrug off a few stray fits, so this pair stays stable even when the pool
has outliers or is skewed. The <i>Median Fit</i> curve drawn on the plot uses
these median values.</li>
<li><b>Mean &plusmn; STDEV</b> &mdash; the <i>classical</i> summary. The mean is
the arithmetic average; the STDEV (standard deviation) is the textbook spread.
Both weight every fit equally, so they are the familiar numbers &mdash; but a
single outlying fit pulls them noticeably.</li>
</ul>

<h4>MAD is not the same as STDEV</h4>
<p>They measure spread in different ways. For a clean, bell-shaped (Gaussian)
pool they agree after a fixed scaling: <b>STDEV &asymp; 1.48 &times; MAD</b>.
When the two pairs roughly satisfy that, the accepted fits are well behaved and
either summary is fine.</p>
<p>When they <i>disagree</i> &mdash; typically STDEV much larger than
1.48&nbsp;&times;&nbsp;MAD, or the mean sitting far from the median &mdash; a
few outlying or skewed fits are inflating the classical numbers. Trust the
robust <b>Median &plusmn; MAD</b> in that case, and inspect the spread in the
distribution (box-and-whisker) plot.</p>

<h4>Average mode</h4>
<p>Your replicas are averaged into one curve, which is then fit many times from
different starting points. The spread reflects how precisely the fitter can pin
down the parameter on that averaged curve &mdash; a measure of <b>numerical
precision</b>. It does not capture replica-to-replica variation.</p>

<h4>Per-replica mode</h4>
<p>Each replica is fit independently and every acceptable fit from every
replica is pooled together. The spread now includes differences between
replicas &mdash; a measure of <b>experimental reproducibility</b>, typically
the number you would report in a publication.</p>

<h4>Which mode am I using?</h4>
<p>The caption under the table says so &mdash; <i>average mode</i> or
<i>per-replica mode</i> &mdash; along with how many accepted fits (N) the
statistics were computed from. Switch modes in Fit Configuration &rarr;
&ldquo;Fit per replica&rdquo;.</p>
"""


_FIT_QUALITY_HELP_HTML = """
<h3>Fit Quality</h3>

<p><b>RMSE</b> (root mean squared error) &mdash; average distance between
the fitted curve and the data points, in signal units. Lower is better.
Compare it to the noise level in your data: if RMSE is similar to the
noise floor, the fit is explaining the data about as well as possible.</p>

<p><b>R&sup2;</b> (coefficient of determination) &mdash; fraction of the
data variance explained by the fit, from 0 to 1. Values above 0.99 are
typical for clean fluorescence titrations; below 0.90 suggests the model
does not capture the data shape well.</p>

<p><b>Fits passing</b> &mdash; how many of the multi-start trials produced
acceptable results (passing both the RMSE factor and minimum R&sup2;
thresholds). A low ratio (e.g. 5/100) means most starting points led the
optimiser to poor solutions &mdash; consider widening bounds or increasing
the trial budget.</p>
"""


def _magnitude(value) -> float:
    """Return the float magnitude of a Quantity or plain number."""
    return float(value.magnitude) if isinstance(value, Quantity) else float(value)


def _fmt_mag(magnitude: float, unit_str: str) -> str:
    """Format a magnitude for display, stripping any unit (shown separately)."""
    if unit_str:
        return f'{Q_(magnitude, unit_str):.3g~H}'.rsplit(' ', 1)[0]
    return f'{magnitude:.3g}'


def _make_cell(html: str) -> QLabel:
    """Build a centred rich-text cell label for the parameters table."""
    lbl = QLabel(html)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setTextFormat(Qt.TextFormat.RichText)
    return lbl


class FitSummaryWidget(QWidget):
    """Read-only display of ``FitResult`` statistics.

    Layout
    ------
    - ``QGroupBox("Fitted Parameters")`` with columns:
      Parameter | Median +/- MAD | Mean +/- STDEV | Units, plus a caption
      noting the fit mode and accepted-fit count.
    - ``QGroupBox("Fit Quality")`` with RMSE, R-squared, Fits passing.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._params_group = InfoGroupBox(
            'Fitted Parameters',
            'Median \u00b1 MAD vs Mean \u00b1 STDEV',
            _UNCERTAINTY_HELP_HTML,
        )
        self._table = QTableWidget(0, len(_HEADERS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        header = self._table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._caption = QLabel()
        self._caption.setWordWrap(True)
        self._caption.setStyleSheet('color: gray;')
        params_layout = QVBoxLayout(self._params_group)
        params_layout.addWidget(self._table)
        params_layout.addWidget(self._caption)

        self._quality_group = InfoGroupBox('Fit Quality', 'Fit Quality', _FIT_QUALITY_HELP_HTML)
        quality_layout = QFormLayout(self._quality_group)
        self._rmse_label = QLabel('\u2014')
        self._r2_label = QLabel('\u2014')
        self._passing_label = QLabel('\u2014')
        quality_layout.addRow('RMSE:', self._rmse_label)
        quality_layout.addRow('R\u00b2:', self._r2_label)
        quality_layout.addRow('Fits passing:', self._passing_label)

        main_layout = QHBoxLayout(self)
        main_layout.addWidget(self._params_group, stretch=3)
        main_layout.addWidget(self._quality_group, stretch=1)

    def update_result(self, result: FitResult) -> None:
        """Populate the widget from a ``FitResult``.

        Resolves units from ``ASSAY_REGISTRY`` using ``result.assay_type``.
        Shows two stat pairs per parameter: the robust median/MAD (reusing the
        stored values) and the classical mean/STDEV (computed from
        ``result.parameter_samples``; no re-fit).

        Parameters
        ----------
        result : FitResult
        """
        assay_type = _lookup_assay_type(result.assay_type)
        units: dict[str, str] = {}
        if assay_type is not None:
            units = ASSAY_REGISTRY[assay_type].units

        # The fit mode and pool size used to live in the uncertainty-column
        # header; with two stat pairs that context moves to a caption.
        if result.uncertainty_source == 'replicate':  # JSON-compat magic value
            pool_size = result.metadata.get('pool_size', result.n_passing)
            n_reps = result.metadata.get('n_replicas_fit', '?')
            self._caption.setText(
                f'Statistics across N = {pool_size} accepted fits pooled from {n_reps} replicas (per-replica mode).'
            )
        else:
            self._caption.setText(f'Statistics across N = {result.n_passing} accepted fits (average mode).')

        params = result.parameters
        uncertainties = result.uncertainties
        samples = result.parameter_samples
        means = compute_mean_params(samples) if samples else None
        stds = compute_std_params(samples) if samples else None

        self._table.setRowCount(len(params))
        for row, key in enumerate(params):
            unit_str = units.get(key, '')
            median_mag = _magnitude(params[key])
            mad_mag = _magnitude(uncertainties.get(key, float('nan')))

            self._table.setCellWidget(row, 0, _make_cell(fmt_param(key)))
            self._table.setCellWidget(
                row,
                1,
                _make_cell(f'{_fmt_mag(median_mag, unit_str)} \u00b1 {_fmt_mag(mad_mag, unit_str)}'),
            )

            if means is not None and key in means:
                mean_cell = _make_cell(f'{_fmt_mag(means[key], unit_str)} \u00b1 {_fmt_mag(stds[key], unit_str)}')
            else:
                mean_cell = _make_cell('\u2014')
                mean_cell.setToolTip(
                    'Mean \u00b1 STDEV needs the accepted-fit pool, which is '
                    'unavailable for this result (e.g. imported from an older file).'
                )
            self._table.setCellWidget(row, 2, mean_cell)

            self._table.setCellWidget(row, 3, _make_cell(fmt_unit_html(unit_str)))

        rmse_html = f'{Q_(result.rmse, "au"):.3g~H}'
        self._rmse_label.setTextFormat(Qt.TextFormat.RichText)
        self._rmse_label.setText(rmse_html)
        self._r2_label.setText(f'{result.r_squared:.4f}')
        self._passing_label.setText(f'{result.n_passing} / {result.n_total}')
        self._autosize_columns()

    def _autosize_columns(self) -> None:
        # resizeColumnsToContents() ignores widgets set via setCellWidget(),
        # so we measure each QLabel's sizeHint() directly, then spread any
        # leftover viewport width evenly across columns.
        n_cols = self._table.columnCount()
        n_rows = self._table.rowCount()
        fm = self._table.horizontalHeader().fontMetrics()
        widths = []
        for col in range(n_cols):
            item = self._table.horizontalHeaderItem(col)
            header_text = item.text() if item is not None else ''
            w = fm.horizontalAdvance(header_text) + 24
            for row in range(n_rows):
                widget = self._table.cellWidget(row, col)
                if widget is not None:
                    w = max(w, widget.sizeHint().width() + 16)
            widths.append(w)

        extra = max(0, (self._table.viewport().width() - sum(widths)) // n_cols)
        for col, w in enumerate(widths):
            self._table.setColumnWidth(col, w + extra)

    def clear(self) -> None:
        """Reset all fields to their empty state."""
        self._table.setRowCount(0)
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._caption.clear()
        self._rmse_label.setText('\u2014')
        self._r2_label.setText('\u2014')
        self._passing_label.setText('\u2014')


def _lookup_assay_type(assay_type_str: str) -> AssayType | None:
    """Reverse-lookup AssayType by its ``.name`` string.

    Parameters
    ----------
    assay_type_str : str
        E.g. ``"GDA"``, ``"IDA"``, ``"DBA_HtoD"``.

    Returns
    -------
    AssayType | None
        ``None`` if not found.
    """
    try:
        return AssayType[assay_type_str]
    except KeyError:
        return None
