"""Read-only display widget for FitResult statistics."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFormLayout, QGroupBox, QHBoxLayout, QLabel, QTableWidget, QVBoxLayout, QWidget

from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.pipeline.fit_pipeline import FitResult
from core.units import Q_, Quantity, ureg
from gui.plotting.labels import fmt_param, fmt_unit_html


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

        self._params_group = QGroupBox('Fitted Parameters')
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(['Parameter', 'Value', '\u00b1 Uncertainty', 'Units'])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        params_layout = QVBoxLayout(self._params_group)
        params_layout.addWidget(self._table)

        self._quality_group = QGroupBox('Fit Quality')
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
