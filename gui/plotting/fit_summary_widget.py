"""Read-only display widget for FitResult statistics."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.pipeline.fit_pipeline import FitResult
from gui.plotting.labels import _fmt_value, fmt_param, fmt_unit


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

        self._params_group = QGroupBox("Fitted Parameters")
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Parameter", "Value", "\u00b1 Uncertainty", "Units"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        params_layout = QVBoxLayout(self._params_group)
        params_layout.addWidget(self._table)

        self._quality_group = QGroupBox("Fit Quality")
        quality_layout = QFormLayout(self._quality_group)
        self._rmse_label = QLabel("\u2014")
        self._r2_label = QLabel("\u2014")
        self._passing_label = QLabel("\u2014")
        quality_layout.addRow("RMSE:", self._rmse_label)
        quality_layout.addRow("R\u00b2:", self._r2_label)
        quality_layout.addRow("Fits passing:", self._passing_label)

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
            unc = uncertainties.get(key, float("nan"))
            unit = units.get(key, "")

            lbl_name = QLabel(fmt_param(key))
            lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setCellWidget(row, 0, lbl_name)

            self._table.setItem(row, 1, QTableWidgetItem(_fmt_value(value)))
            self._table.setItem(row, 2, QTableWidgetItem(_fmt_value(unc)))

            lbl_unit = QLabel(fmt_unit(unit))
            lbl_unit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setCellWidget(row, 3, lbl_unit)

        self._rmse_label.setText(_fmt_value(result.rmse))
        self._r2_label.setText(f"{result.r_squared:.4f}")
        self._passing_label.setText(f"{result.n_passing} / {result.n_total}")

    def clear(self) -> None:
        """Reset all fields to their empty state."""
        self._table.setRowCount(0)
        self._rmse_label.setText("\u2014")
        self._r2_label.setText("\u2014")
        self._passing_label.setText("\u2014")


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
