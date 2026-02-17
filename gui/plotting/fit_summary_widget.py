"""Read-only display widget for FitResult statistics."""

from __future__ import annotations

import math
from typing import Optional

from PyQt6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.pipeline.fit_pipeline import FitResult


class FitSummaryWidget(QWidget):
    """Read-only display of ``FitResult`` statistics.

    Layout
    ------
    - ``QGroupBox("Fitted Parameters")`` → ``QTableWidget`` with columns:
      Parameter | Value | ± Uncertainty | Units
    - ``QGroupBox("Fit Quality")`` → ``QFormLayout`` with RMSE, R²,
      Fits passing.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # --- Parameters table ---
        self._params_group = QGroupBox("Fitted Parameters")
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Parameter", "Value", "± Uncertainty", "Units"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        params_layout = QVBoxLayout(self._params_group)
        params_layout.addWidget(self._table)

        # --- Quality metrics ---
        self._quality_group = QGroupBox("Fit Quality")
        quality_layout = QFormLayout(self._quality_group)
        self._rmse_label = QLabel("—")
        self._r2_label = QLabel("—")
        self._passing_label = QLabel("—")
        quality_layout.addRow("RMSE:", self._rmse_label)
        quality_layout.addRow("R²:", self._r2_label)
        quality_layout.addRow("Fits passing:", self._passing_label)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self._params_group)
        main_layout.addWidget(self._quality_group)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
            self._table.setItem(row, 0, QTableWidgetItem(key))
            self._table.setItem(row, 1, QTableWidgetItem(_fmt_value(value)))
            self._table.setItem(row, 2, QTableWidgetItem(_fmt_value(unc)))
            self._table.setItem(row, 3, QTableWidgetItem(unit))

        self._rmse_label.setText(_fmt_value(result.rmse))
        self._r2_label.setText(f"{result.r_squared:.4f}")
        self._passing_label.setText(f"{result.n_passing} / {result.n_total}")

    def clear(self) -> None:
        """Reset all fields to their empty state."""
        self._table.setRowCount(0)
        self._rmse_label.setText("—")
        self._r2_label.setText("—")
        self._passing_label.setText("—")


# ------------------------------------------------------------------
# Module-level helpers (accessible for testing)
# ------------------------------------------------------------------

def _lookup_assay_type(assay_type_str: str) -> Optional[AssayType]:
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
    for at in AssayType:
        if at.name == assay_type_str:
            return at
    return None


def _fmt_value(value: float) -> str:
    """Format a float for display.

    Uses scientific notation for |v| >= 1e5 or |v| < 1e-3 (and v != 0).
    Returns ``"NaN"`` / ``"Inf"`` for special values.

    Parameters
    ----------
    value : float

    Returns
    -------
    str
    """
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "Inf" if value > 0 else "-Inf"
    if value == 0.0:
        return "0.0"
    abs_v = abs(value)
    if abs_v >= 1e5 or abs_v < 1e-3:
        return f"{value:.4e}"
    return f"{value:.6g}"
