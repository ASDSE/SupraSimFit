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
from core.optimizer.ensemble import ENSEMBLE_STATISTICS, summarize
from core.pipeline.fit_pipeline import FitResult
from core.units import Q_, Quantity
from gui.plotting.labels import fmt_param, fmt_unit_html
from gui.widgets.info_button import InfoGroupBox

_PARAMS_HELP_HTML = """
<h3>Fitted Parameters &mdash; columns</h3>

<p><b>Value</b> &mdash; the single best real fit (highest R&sup2;). This is
the fit drawn on the plot and the trustworthy number to report; it always
corresponds to an actual fit, never a synthetic average.</p>

<p><b>Median / MAD</b> and <b>Mean / STDEV</b> &mdash; the centre and spread
of each parameter across <i>all</i> valid fits.
Median&nbsp;&plusmn;&nbsp;MAD is robust to outlier fits;
Mean&nbsp;&plusmn;&nbsp;STDEV is the ordinary average. The
<b>Statistics</b> selector picks which pair is reported as the &plusmn; in
the plot annotation and the export &mdash; it does not change the Value or
the curve.</p>

<p><b>Large spread on signal coefficients is expected.</b> Only
K<sub>a</sub> is uniquely determined; I<sub>0</sub>, I<sub>D</sub>,
I<sub>HD</sub> trade off along a degenerate manifold, so their Median/Mean
differ from the best-fit Value and their spread is wide. That is
informative, not an error.</p>
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


# Stat columns: (header, key in ensemble.summarize() output). The active
# (central, spread) pair is bold-emphasised per the selected statistics mode.
_STAT_COLUMNS = (('Median', 'median'), ('MAD', 'mad'), ('Mean', 'mean'), ('STDEV', 'std'))
_COLUMN_HEADERS = ('Parameter', 'Value') + tuple(h for h, _ in _STAT_COLUMNS) + ('Units',)
# Header-column indices bolded for each mode's (central, spread) pair.
_ACTIVE_COLUMNS = {'median': (2, 3), 'mean': (4, 5)}
# Cap the Representative selector list (pools can hold hundreds of fits).
_MAX_REP_CHOICES = 15


class FitSummaryWidget(QWidget):
    """Read-only display of ``FitResult`` statistics.

    Layout
    ------
    - ``QGroupBox("Fitted Parameters")`` with a Statistics selector and
      columns: Parameter | Value | Median | MAD | Mean | STDEV | Units.
      ``Value`` is the representative (best) fit; Median/MAD/Mean/STDEV are
      the spread across all valid fits. The selector chooses which
      central+spread pair is the reported \u00b1 (annotation + export).
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

        ``Value`` is the representative (best) fit; Median/MAD/Mean/STDEV are
        computed from the valid-fit pool via
        :func:`core.optimizer.ensemble.summarize`. Units are resolved from
        ``ASSAY_REGISTRY`` using ``result.assay_type``.
        """
        assay_type = _lookup_assay_type(result.assay_type)
        units: dict[str, str] = {}
        if assay_type is not None:
            units = ASSAY_REGISTRY[assay_type].units

        self._set_combo_mode(result.statistics_mode)
        self._populate_rep_combo(result)

        params = result.parameters
        samples = result.parameter_samples
        stats = summarize(samples) if samples else {}
        pool_missing = not samples

        self._table.setRowCount(len(params))
        for row, (key, value) in enumerate(params.items()):
            unit_str = units.get(key, '')
            self._set_cell(row, 0, fmt_param(key))

            val_mag = float(value.magnitude) if isinstance(value, Quantity) else float(value)
            self._set_cell(row, 1, self._fmt(val_mag, unit_str))

            s = stats.get(key)
            for col, skey in ((2, 'median'), (3, 'mad'), (4, 'mean'), (5, 'std')):
                if s is None:
                    self._set_cell(
                        row,
                        col,
                        '—',
                        tooltip='No fit pool stored for this result (e.g. a legacy import).',
                    )
                else:
                    self._set_cell(row, col, self._fmt(s[skey], unit_str))

            self._set_cell(row, 6, fmt_unit_html(unit_str))

        self._emphasize_active_pair(result.statistics_mode)

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
        """List valid fits (best first by R²) so the user can pick which is reported."""
        self._rep_combo.blockSignals(True)
        self._rep_combo.clear()
        quality = result.quality_samples
        if quality and 'r_squared' in quality and 'rmse' in quality:
            r2 = np.asarray(quality['r_squared'], dtype=float)
            rmse = np.asarray(quality['rmse'], dtype=float)
            order = [int(i) for i in np.argsort(rmse)]  # best (lowest RMSE = highest R²) first
            shown = order[:_MAX_REP_CHOICES]
            cur = result.representative_index
            if cur is not None and cur not in shown:
                shown.append(int(cur))
            for rank, idx in enumerate(shown):
                prefix = 'Best · ' if rank == 0 else ''
                self._rep_combo.addItem(f'{prefix}R²={r2[idx]:.4f} · RMSE={rmse[idx]:.3g}', idx)
            if cur is not None:
                pos = self._rep_combo.findData(int(cur))
                if pos >= 0:
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
