"""Read-only display widget for FitResult statistics."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFormLayout, QGroupBox, QHBoxLayout, QLabel, QTableWidget, QVBoxLayout, QWidget

from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.pipeline.fit_pipeline import FitResult
from core.units import Q_, Quantity, ureg
from gui.plotting.labels import fmt_param, fmt_unit_html
from gui.widgets.info_button import InfoGroupBox


_UNCERTAINTY_HELP_HTML = """
<h3>Uncertainty &mdash; what the &plusmn; value means</h3>

<p>The &plusmn; value next to each fitted parameter tells you <b>how
much that parameter varies</b> across all the acceptable fits the
fitter found. A small &plusmn; means the fitter consistently lands on
the same value; a large one means there is real spread.</p>

<p>Technically, the reported value is the <i>median</i> of the
acceptable fits, and the &plusmn; is their <i>median absolute
deviation</i> &mdash; a robust measure of spread that is not thrown off
by a few outliers.</p>

<h4>Average mode</h4>
<p>Your replicates are averaged into one curve, which is then fit many
times from different starting points. The &plusmn; reflects how
precisely the fitter can pin down the parameter on that averaged curve.
This is a measure of <b>numerical precision</b> &mdash; it does not
capture replicate-to-replicate variation.</p>

<h4>Per-replicate mode</h4>
<p>Each replicate is fit independently, and every acceptable fit from
every replicate is collected together. The &plusmn; now reflects the
full spread &mdash; including differences between replicates. This is a
measure of <b>experimental reproducibility</b>, which is typically the
number you would report in a publication.</p>

<h4>The Median Fit curve</h4>
<p>The curve drawn on the plot uses the median parameter values from all
acceptable fits. It is labelled <i>Median Fit</i> because it
represents the middle of the distribution, not the single &ldquo;best&rdquo;
attempt.</p>

<h4>Which mode am I using?</h4>
<p>The column header tells you: <i>&plusmn;&nbsp;Uncertainty
(optimiser)</i> in average mode, or <i>&plusmn;&nbsp;Uncertainty
(pool&nbsp;N=&hellip;, &hellip;&nbsp;replicas)</i> in per-replicate
mode. Switch between modes in Fit Configuration &rarr; &ldquo;Fit per
replicate&rdquo;.</p>
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


class FitSummaryWidget(QWidget):
    """Read-only display of ``FitResult`` statistics.

    Layout
    ------
    - ``QGroupBox("Fitted Parameters")`` with columns:
      Parameter | Value | +/- Uncertainty | Units
    - ``QGroupBox("Fit Quality")`` with RMSE, R-squared, Fits passing.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._params_group = InfoGroupBox(
            'Fitted Parameters',
            'Uncertainty: what the \u00b1 value means',
            _UNCERTAINTY_HELP_HTML,
        )
        self._table = QTableWidget(0, 4)
        self._uncertainty_header_default = '\u00b1 Uncertainty (optimiser)'
        self._table.setHorizontalHeaderLabels(
            ['Parameter', 'Value', self._uncertainty_header_default, 'Units']
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        params_layout = QVBoxLayout(self._params_group)
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

        Resolves units from ``ASSAY_REGISTRY`` using ``result.assay_type``.

        Parameters
        ----------
        result : FitResult
        """
        assay_type = _lookup_assay_type(result.assay_type)
        units: dict[str, str] = {}
        if assay_type is not None:
            units = ASSAY_REGISTRY[assay_type].units

        if result.uncertainty_source == 'replicate':
            pool_size = result.metadata.get('pool_size', result.n_passing)
            n_reps = result.metadata.get('n_replicas_fit', '?')
            header = f'\u00b1 Uncertainty (pool N={pool_size}, {n_reps} replicas)'
        else:
            header = self._uncertainty_header_default
        self._table.setHorizontalHeaderLabels(['Parameter', 'Value', header, 'Units'])

        params = result.parameters
        uncertainties = result.uncertainties

        self._table.setRowCount(len(params))
        for row, (key, value) in enumerate(params.items()):
            unc = uncertainties.get(key, float('nan'))
            unit_str = units.get(key, '')

            lbl_name = QLabel(fmt_param(key))
            lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setCellWidget(row, 0, lbl_name)

            val_mag = float(value.magnitude) if isinstance(value, Quantity) else float(value)
            unc_mag = float(unc.magnitude) if isinstance(unc, Quantity) else float(unc)

            # Use Pint HTML formatter for proper superscript notation
            if unit_str:
                val_html = f'{Q_(val_mag, unit_str):.3g~H}'
                unc_html = f'{Q_(unc_mag, unit_str):.3g~H}'
            else:
                val_html = f'{val_mag:.3g}'
                unc_html = f'{unc_mag:.3g}'
            # Strip unit from the HTML — units shown in separate column
            val_display = val_html.rsplit(' ', 1)[0] if unit_str else val_html
            unc_display = unc_html.rsplit(' ', 1)[0] if unit_str else unc_html

            lbl_val = QLabel(val_display)
            lbl_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_val.setTextFormat(Qt.TextFormat.RichText)
            self._table.setCellWidget(row, 1, lbl_val)

            lbl_unc = QLabel(unc_display)
            lbl_unc.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_unc.setTextFormat(Qt.TextFormat.RichText)
            self._table.setCellWidget(row, 2, lbl_unc)

            unit_html = fmt_unit_html(unit_str)
            lbl_unit = QLabel(unit_html)
            lbl_unit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setCellWidget(row, 3, lbl_unit)

        rmse_html = f'{Q_(result.rmse, "au"):.3g~H}'
        self._rmse_label.setTextFormat(Qt.TextFormat.RichText)
        self._rmse_label.setText(rmse_html)
        self._r2_label.setText(f'{result.r_squared:.4f}')
        self._passing_label.setText(f'{result.n_passing} / {result.n_total}')

    def clear(self) -> None:
        """Reset all fields to their empty state."""
        self._table.setRowCount(0)
        self._table.setHorizontalHeaderLabels(
            ['Parameter', 'Value', self._uncertainty_header_default, 'Units']
        )
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
