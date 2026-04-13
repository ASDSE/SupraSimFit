"""ConcentrationDialog — edit, save, load, and import concentration vectors."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.data_processing.concentration import (
    extract_concentrations_from_file,
    load_concentration_vector,
    save_concentration_vector,
)
from core.io.registry import READERS

# Mapping of display unit → multiplier (converts display value to base unit M).
_UNIT_FACTORS: dict[str, float] = {
    'nM': 1e-9,
    'µM': 1e-6,
    'mM': 1e-3,
    'M': 1.0,
}
_DEFAULT_UNIT = 'µM'


def _load_file_filter() -> str:
    """Return a combined file filter covering JSON and all data readers."""
    data_exts = sorted(READERS.keys())
    data_parts = ' '.join(f'*{ext}' for ext in data_exts)
    return (
        f"All supported (*.json {data_parts});;"
        f"JSON concentration vector (*.json);;"
        f"Measurement files ({data_parts});;"
        f"All files (*)"
    )


class ConcentrationDialog(QDialog):
    """Modal dialog for editing, saving, loading, and importing concentration vectors.

    The dialog stores values internally in base units (molar, M) and lets the
    user view/edit them in any of the common unit prefixes. Switching units
    preserves any in-progress edits by converting them back to M first.

    Parameters
    ----------
    concentrations : np.ndarray
        Current concentration vector in **molar (M)**.
    parent : QWidget, optional
        Parent widget.
    """

    def __init__(self, concentrations: np.ndarray, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Concentration Vector")
        self.setMinimumWidth(420)
        self._values_M = np.asarray(concentrations, dtype=float).copy()
        self._result: np.ndarray | None = None
        self._current_unit = _DEFAULT_UNIT
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def result_concentrations(self) -> np.ndarray | None:
        """Return the accepted concentration vector in M (or None on cancel)."""
        return self._result

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        layout.addWidget(
            QLabel(f"<b>{len(self._values_M)} concentration points</b>")
        )

        # Unit selector row
        unit_row = QHBoxLayout()
        unit_row.addWidget(QLabel("Unit:"))
        self._unit_combo = QComboBox()
        self._unit_combo.addItems(list(_UNIT_FACTORS.keys()))
        self._unit_combo.setCurrentText(self._current_unit)
        self._unit_combo.currentTextChanged.connect(self._on_unit_changed)
        unit_row.addWidget(self._unit_combo)
        unit_row.addStretch(1)
        layout.addLayout(unit_row)

        # Editable table
        self._table = QTableWidget(len(self._values_M), 2)
        self._table.setHorizontalHeaderLabels(
            ["#", f"Concentration ({self._current_unit})"]
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._refresh_table()
        layout.addWidget(self._table)

        # File action buttons
        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save As…")
        save_btn.clicked.connect(self._on_save)
        load_btn = QPushButton("Load from File…")
        load_btn.setToolTip(
            "Load concentrations from a JSON vector or extract them from a "
            "measurement file (.txt, .csv, .xlsx, …)."
        )
        load_btn.clicked.connect(self._on_load_from_file)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(load_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        # Dialog buttons (OK applies edits; Cancel discards)
        bbox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bbox.accepted.connect(self._on_accept)
        bbox.rejected.connect(self.reject)
        layout.addWidget(bbox)

    def _refresh_table(self) -> None:
        """Populate the table with ``self._values_M`` shown in the current unit."""
        factor = _UNIT_FACTORS[self._current_unit]
        self._table.setRowCount(len(self._values_M))
        self._table.setHorizontalHeaderLabels(
            ["#", f"Concentration ({self._current_unit})"]
        )
        for i, val_M in enumerate(self._values_M):
            idx_item = QTableWidgetItem(str(i))
            idx_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            idx_item.setFlags(Qt.ItemFlag.ItemIsEnabled)  # read-only index column
            self._table.setItem(i, 0, idx_item)

            display = float(val_M) / factor
            val_item = QTableWidgetItem(f"{display:.6g}")
            val_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self._table.setItem(i, 1, val_item)

    # ------------------------------------------------------------------
    # Internal: read table in current unit → M
    # ------------------------------------------------------------------

    def _read_table_as_M(self) -> np.ndarray | None:
        """Parse the visible table and return values in M (None on parse error)."""
        factor = _UNIT_FACTORS[self._current_unit]
        out = np.empty(self._table.rowCount(), dtype=float)
        for i in range(self._table.rowCount()):
            item = self._table.item(i, 1)
            text = item.text().strip() if item is not None else ''
            try:
                out[i] = float(text) * factor
            except ValueError:
                QMessageBox.warning(
                    self,
                    "Invalid value",
                    f"Row {i} is not a valid number: {text!r}",
                )
                return None
        return out

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_unit_changed(self, new_unit: str) -> None:
        """Switch display unit, preserving any in-progress edits."""
        # Absorb any edits the user made in the *old* unit into ``_values_M``
        # so switching units doesn't lose them.
        edited = self._read_table_as_M()
        if edited is None:
            # Revert the combo to the previous unit on parse failure
            self._unit_combo.blockSignals(True)
            self._unit_combo.setCurrentText(self._current_unit)
            self._unit_combo.blockSignals(False)
            return
        self._values_M = edited
        self._current_unit = new_unit
        self._refresh_table()

    def _on_accept(self) -> None:
        values = self._read_table_as_M()
        if values is None:
            return
        self._values_M = values
        self._result = values
        self.accept()

    def _on_save(self) -> None:
        # Commit any edits before saving
        current = self._read_table_as_M()
        if current is None:
            return
        self._values_M = current

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Concentration Vector", "concentrations.json", "JSON (*.json)"
        )
        if not path:
            return
        try:
            save_concentration_vector(self._values_M, path, label="")
            QMessageBox.information(self, "Saved", f"Saved to:\n{path}")
        except Exception as exc:
            QMessageBox.warning(self, "Save Error", str(exc))

    def _on_load_from_file(self) -> None:
        """Dispatch on the chosen file's extension.

        ``.json`` paths are treated as serialized concentration vectors;
        any other extension is parsed as a measurement file and the
        concentrations are extracted from its first column.
        """
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Concentrations",
            "",
            _load_file_filter(),
        )
        if not path:
            return
        suffix = Path(path).suffix.lower()
        try:
            if suffix == '.json':
                conc, _unit, _label = load_concentration_vector(path)
            else:
                conc = extract_concentrations_from_file(path)
            self._apply_new_concentrations(
                np.asarray(conc, dtype=float), source=Path(path).name
            )
        except Exception as exc:
            QMessageBox.warning(self, "Load Error", str(exc))

    def _apply_new_concentrations(self, conc: np.ndarray, source: str) -> None:
        self._values_M = conc.copy()
        self._result = conc
        self._refresh_table()
        QMessageBox.information(
            self,
            "Loaded",
            f"Loaded {len(conc)} concentration points from '{source}'.\n"
            "Click OK to apply them to the current session.",
        )
