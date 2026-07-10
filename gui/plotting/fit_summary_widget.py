"""Read-only display widget for FitResult statistics."""

from __future__ import annotations

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

from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.optimizer.ensemble import ENSEMBLE_STATISTICS, describe, describe_log10
from core.pipeline.fit_pipeline import FitResult
from core.units import Q_, Quantity
from gui.plotting.labels import fmt_param, fmt_unit_html
from gui.widgets.info_button import InfoGroupBox

_PARAMS_HELP_HTML = """
<h3>Fitted Parameters &mdash; columns</h3>

<p><b>Estimate</b> &mdash; the representative fit: one actual fit from the
valid pool (highest R&sup2;), the one drawn on the plot. It is a point
estimate among a distribution, not a proven optimum.</p>

<p><b>Median &plusmn; MAD</b> and <b>Mean &plusmn; SD</b> &mdash; the centre
and spread of each parameter across <i>all</i> valid fits.
Median&nbsp;/&nbsp;MAD is robust to outlier fits; Mean&nbsp;/&nbsp;SD is the
ordinary average. The <b>Statistics</b> selector bolds whichever pair is the
reported &plusmn; in the plot annotation and export &mdash; it does not change
the Estimate or the curve.</p>

<p><b>Range [min, max]</b> &mdash; the smallest and largest fitted value in
the pool, an intuitive sense of the spread alongside the statistics.</p>

<p><b>log<sub>10</sub>(K<sub>a</sub>) row</b> &mdash; for each association
constant, a second row reports log<sub>10</sub>(K<sub>a</sub>). Its statistics
come from the per-fit log<sub>10</sub> values directly &mdash; never from the
log of a K<sub>a</sub> spread, which would be meaningless.</p>

<p><b>Large spread on signal coefficients is expected.</b> Only
K<sub>a</sub> is uniquely determined; I<sub>0</sub>, I<sub>D</sub>,
I<sub>HD</sub> trade off along a degenerate manifold, so their Median/Mean
differ from the Estimate and their spread is wide. That is informative,
not an error.</p>
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

<p><b>Fits passing</b> &mdash; how many of the multi-start trials cleared
the minimum&nbsp;R&sup2; floor (plus the optional RMSE trim, if enabled) and
form the valid pool. A low ratio (e.g. 5/100) means most starting points led
the optimiser to poor solutions &mdash; consider widening bounds or
increasing the trial budget.</p>
"""


# Merged stat columns: (header, (central_key, spread_key)) from ensemble.describe().
# Rendered as a single "central ± spread" cell; the active pair is bold-emphasised.
_STAT_COLUMNS = (('Median ± MAD', ('median', 'mad')), ('Mean ± SD', ('mean', 'std')))
_RANGE_HEADER = 'Range [min, max]'
_COLUMN_HEADERS = ('Parameter', 'Estimate') + tuple(h for h, _ in _STAT_COLUMNS) + (_RANGE_HEADER, 'Units')
# Column indices: 0 Parameter | 1 Estimate | 2 Median±MAD | 3 Mean±SD | 4 Range | 5 Units.
_STAT_COL0 = 2
_RANGE_COL = _STAT_COL0 + len(_STAT_COLUMNS)
_UNITS_COL = _RANGE_COL + 1
# Column bolded for each mode's merged (central ± spread) cell.
_ACTIVE_COLUMNS = {'median': (_STAT_COL0,), 'mean': (_STAT_COL0 + 1,)}


class FitSummaryWidget(QWidget):
    """Read-only display of ``FitResult`` statistics.

    Layout
    ------
    - ``QGroupBox("Fitted Parameters")`` with Statistics and Representative
      selectors and columns: Parameter | Estimate | Median \u00b1 MAD | Mean \u00b1 SD |
      Range [min, max] | Units, plus a log\u2081\u2080 row for each association constant.
      ``Estimate`` is the representative fit; the stat columns summarise the
      spread across all valid fits. The Statistics selector bolds the reported
      pair (annotation + export).
    - ``QGroupBox("Fit Quality")`` with RMSE, R-squared, Fits passing.

    Signals
    -------
    statistics_mode_changed(str)
        Emitted when the user picks a different aggregation (``"median"`` /
        ``"mean"``). The owner recomputes the reported \u00b1 and refreshes the
        annotation; the value, curve, and RMSE/R\u00b2 never change.
    """

    statistics_mode_changed = pyqtSignal(str)
    representative_selected = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._params_group = InfoGroupBox(
            'Fitted Parameters',
            'Fitted Parameters \u2014 columns',
            _PARAMS_HELP_HTML,
        )

        # Statistics selector: which (central \u00b1 spread) is the reported \u00b1.
        self._stats_combo = QComboBox()
        for key, stat in ENSEMBLE_STATISTICS.items():
            self._stats_combo.addItem(stat.label, key)
        self._stats_combo.setToolTip(
            'Reported \u00b1 across the valid fits: \u00b1 MAD (robust) or \u00b1 STDEV. '
            'Changes the annotation and export only \u2014 not the value or curve.'
        )
        self._stats_combo.currentIndexChanged.connect(self._on_stats_combo_changed)

        # Representative selector: which actual fit is reported (drives the curve).
        self._rep_combo = QComboBox()
        # Size to the widest item so no label is ever truncated.
        self._rep_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._rep_combo.setMinimumContentsLength(24)
        self._rep_combo.setToolTip(
            'Which valid fit is reported and drawn. Defaults to the best (highest R\u00b2); '
            'pick another, or click a point in the Distributions tab.'
        )
        self._rep_combo.currentIndexChanged.connect(self._on_rep_combo_changed)

        stats_row = QHBoxLayout()
        stats_row.addWidget(QLabel('Statistics:'))
        stats_row.addWidget(self._stats_combo)
        stats_row.addSpacing(16)
        stats_row.addWidget(QLabel('Representative:'))
        stats_row.addWidget(self._rep_combo)
        stats_row.addStretch(1)

        self._table = QTableWidget(0, len(_COLUMN_HEADERS))
        self._table.setHorizontalHeaderLabels(list(_COLUMN_HEADERS))
        header = self._table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        params_layout = QVBoxLayout(self._params_group)
        params_layout.addLayout(stats_row)
        params_layout.addWidget(self._table)

        # Caption naming the active reported spread (issue 9): Median ± MAD / Mean ± SD.
        self._spread_caption = QLabel()
        self._spread_caption.setTextFormat(Qt.TextFormat.RichText)
        self._spread_caption.setStyleSheet('color: rgba(0,0,0,0.55); font-style: italic;')
        params_layout.addWidget(self._spread_caption)

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

        ``Estimate`` is the representative fit; the Median ± MAD, Mean ± SD, and
        Range columns summarise the valid-fit pool via
        :func:`core.optimizer.ensemble.describe`. Each association constant gets
        a second log₁₀ row whose statistics come from the per-fit log₁₀ values
        (:func:`~core.optimizer.ensemble.describe_log10`), never from the log of
        a Ka spread. Units are resolved from ``ASSAY_REGISTRY``.
        """
        assay_type = _lookup_assay_type(result.assay_type)
        units: dict[str, str] = {}
        log_keys: set[str] = set()
        if assay_type is not None:
            meta = ASSAY_REGISTRY[assay_type]
            units = dict(meta.units)
            log_keys = set(meta.log_scale_keys)

        self._set_combo_mode(result.statistics_mode)
        self._populate_rep_combo(result)

        samples = result.parameter_samples
        pool_missing = not samples

        # Row specs: (label_html, estimate_html, describe_dict|None, unit_str).
        # A log₁₀ twin row follows each association constant (log-scale key).
        specs: list[tuple[str, str, dict | None, str]] = []
        for key, value in result.parameters.items():
            unit_str = units.get(key, '')
            val_mag = float(value.magnitude) if isinstance(value, Quantity) else float(value)
            pool = np.asarray(samples[key], dtype=float) if samples else None
            specs.append(
                (fmt_param(key), self._fmt(val_mag, unit_str), describe(pool) if pool is not None else None, unit_str)
            )
            if key in log_keys and pool is not None:
                unit_html = fmt_unit_html(unit_str)
                log_label = f'log₁₀({fmt_param(key)} / {unit_html})' if unit_html else f'log₁₀({fmt_param(key)})'
                specs.append((log_label, self._fmt(float(np.log10(val_mag)), ''), describe_log10(pool), ''))

        self._table.setRowCount(len(specs))
        for row, (label, est, d, unit_str) in enumerate(specs):
            self._set_cell(row, 0, label)
            self._set_cell(row, 1, est)
            if d is None:
                for col in range(_STAT_COL0, _RANGE_COL + 1):
                    self._set_cell(row, col, '—', tooltip='No fit pool stored for this result (e.g. a legacy import).')
            else:
                for offset, (_, (ck, sk)) in enumerate(_STAT_COLUMNS):
                    self._set_cell(row, _STAT_COL0 + offset, self._fmt_pair(d[ck], d[sk], unit_str))
                self._set_cell(row, _RANGE_COL, self._fmt_range(d['min'], d['max'], unit_str))
            self._set_cell(row, _UNITS_COL, fmt_unit_html(unit_str) if unit_str else '—')

        self._emphasize_active_pair(result.statistics_mode)
        self._spread_caption.setText(f'Reported spread: {ENSEMBLE_STATISTICS[result.statistics_mode].label}')

        rmse_html = f'{Q_(result.rmse, "au"):.3g~H}'
        self._rmse_label.setTextFormat(Qt.TextFormat.RichText)
        self._rmse_label.setText(rmse_html)
        self._r2_label.setText(f'{result.r_squared:.4f}')
        passing = f'{result.n_passing} / {result.n_total}'
        if pool_missing:
            passing += '  (pool unavailable)'
        self._passing_label.setText(passing)
        self._autosize_columns()

    # ------------------------------------------------------------------
    # Cell / selector helpers
    # ------------------------------------------------------------------

    def _fmt(self, magnitude: float, unit_str: str) -> str:
        """Pint HTML value with the trailing unit stripped (units have a column)."""
        if unit_str:
            return f'{Q_(magnitude, unit_str):.3g~H}'.rsplit(' ', 1)[0]
        return f'{magnitude:.3g}'

    def _fmt_pair(self, central: float, spread: float, unit_str: str) -> str:
        """Merged 'central ± spread' cell (units stripped; shown in the Units column)."""
        return f'{self._fmt(central, unit_str)} ± {self._fmt(spread, unit_str)}'

    def _fmt_range(self, lo: float, hi: float, unit_str: str) -> str:
        """Merged '[min, max]' range cell."""
        return f'[{self._fmt(lo, unit_str)}, {self._fmt(hi, unit_str)}]'

    def _set_cell(self, row: int, col: int, html: str, *, tooltip: str | None = None) -> None:
        lbl = QLabel(html)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        if tooltip:
            lbl.setToolTip(tooltip)
        self._table.setCellWidget(row, col, lbl)

    def _set_combo_mode(self, mode: str) -> None:
        """Reflect *mode* in the selector without re-emitting the change."""
        idx = self._stats_combo.findData(mode)
        if idx < 0:
            return
        self._stats_combo.blockSignals(True)
        self._stats_combo.setCurrentIndex(idx)
        self._stats_combo.blockSignals(False)

    def _on_stats_combo_changed(self, _index: int) -> None:
        mode = self._stats_combo.currentData()
        if mode is not None:
            self.statistics_mode_changed.emit(mode)

    def _populate_rep_combo(self, result: FitResult) -> None:
        """Offer four representative choices: Best, Median, Worst, Selected.

        Best/Worst are the highest/lowest R² fits; Median is the fit nearest
        the pool's median R²; Selected is the current ``representative_index``
        (e.g. set by a distribution-plot click). Ranking uses R² throughout.
        """
        self._rep_combo.blockSignals(True)
        self._rep_combo.clear()
        quality = result.quality_samples
        if quality and 'r_squared' in quality and 'rmse' in quality:
            r2 = np.asarray(quality['r_squared'], dtype=float)
            rmse = np.asarray(quality['rmse'], dtype=float)
            cur = result.representative_index
            items = [
                ('Best', int(np.argmax(r2))),
                ('Median', int(np.argmin(np.abs(r2 - np.median(r2))))),
                ('Worst', int(np.argmin(r2))),
            ]
            if cur is not None:
                items.append(('Selected (from plot)', int(cur)))
            for label, idx in items:
                self._rep_combo.addItem(f'{label} · R²={r2[idx]:.4f} · RMSE={rmse[idx]:.3g}', idx)
            # Reflect the current representative: first named item that matches
            # it, else the explicit "Selected" item.
            if cur is not None:
                pos = next((i for i, (_, idx) in enumerate(items) if idx == cur), len(items) - 1)
                self._rep_combo.setCurrentIndex(pos)
            self._rep_combo.setEnabled(True)
        else:
            self._rep_combo.addItem('—', -1)
            self._rep_combo.setEnabled(False)
        self._rep_combo.blockSignals(False)

    def _on_rep_combo_changed(self, _index: int) -> None:
        idx = self._rep_combo.currentData()
        if idx is not None and idx >= 0:
            self.representative_selected.emit(int(idx))

    def _emphasize_active_pair(self, mode: str) -> None:
        """Bold the header of the active (central, spread) pair."""
        active = _ACTIVE_COLUMNS.get(mode, ())
        for col in range(self._table.columnCount()):
            item = self._table.horizontalHeaderItem(col)
            if item is None:
                continue
            font = item.font()
            font.setBold(col in active)
            item.setFont(font)

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
        self._table.setHorizontalHeaderLabels(list(_COLUMN_HEADERS))
        self._rmse_label.setText('\u2014')
        self._r2_label.setText('\u2014')
        self._passing_label.setText('\u2014')
        self._spread_caption.setText('')


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
