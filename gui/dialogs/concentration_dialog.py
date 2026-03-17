"""ConcentrationDialog — view, save, load, and import concentration vectors."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
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


def _data_file_filter() -> str:
    parts = [f"*{ext}" for ext in sorted(READERS.keys())]
    return f"Measurement files ({' '.join(parts)});;All files (*)"


class ConcentrationDialog(QDialog):
    """Modal dialog for viewing, saving, and loading concentration vectors.

    Parameters
    ----------
    concentrations : np.ndarray
        Current concentration vector (read from loaded MeasurementSet).
    parent : QWidget, optional
        Parent widget.
    """

    def __init__(self, concentrations: np.ndarray, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Concentration Vector")
        self.setMinimumWidth(380)
        self._concentrations = concentrations.copy()
        self._result: np.ndarray | None = None
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def result_concentrations(self) -> np.ndarray | None:
        """Return the new concentration vector if the user loaded/imported one."""
        return self._result

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"<b>{len(self._concentrations)} concentration points</b>"))

        # Table — read-only display
        self._table = QTableWidget(len(self._concentrations), 2)
        self._table.setHorizontalHeaderLabels(["#", "Concentration (M)"])
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._populate_table(self._concentrations)
        layout.addWidget(self._table)

        # Action buttons
        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save As…")
        save_btn.clicked.connect(self._on_save)
        load_btn = QPushButton("Load…")
        load_btn.clicked.connect(self._on_load)
        import_btn = QPushButton("Import from Data File…")
        import_btn.clicked.connect(self._on_import)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(load_btn)
        btn_row.addWidget(import_btn)
        layout.addLayout(btn_row)

        # Dialog buttons
        bbox = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bbox.rejected.connect(self.reject)
        layout.addWidget(bbox)

    def _populate_table(self, conc: np.ndarray) -> None:
        self._table.setRowCount(len(conc))
        for i, val in enumerate(conc):
            idx_item = QTableWidgetItem(str(i))
            idx_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            val_item = QTableWidgetItem(f"{val:.6e}")
            val_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(i, 0, idx_item)
            self._table.setItem(i, 1, val_item)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Concentration Vector", "concentrations.json", "JSON (*.json)"
        )
        if not path:
            return
        try:
            save_concentration_vector(self._concentrations, path, label="")
            QMessageBox.information(self, "Saved", f"Saved to:\n{path}")
        except Exception as exc:
            QMessageBox.warning(self, "Save Error", str(exc))

    def _on_load(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Concentration Vector", "", "JSON (*.json);;All files (*)"
        )
        if not path:
            return
        try:
            conc, unit, label = load_concentration_vector(path)
            self._apply_new_concentrations(conc, source=Path(path).name)
        except Exception as exc:
            QMessageBox.warning(self, "Load Error", str(exc))

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Concentrations from Data File", "", _data_file_filter()
        )
        if not path:
            return
        try:
            conc = extract_concentrations_from_file(path)
            self._apply_new_concentrations(conc, source=Path(path).name)
        except Exception as exc:
            QMessageBox.warning(self, "Import Error", str(exc))

    def _apply_new_concentrations(self, conc: np.ndarray, source: str) -> None:
        self._concentrations = conc
        self._result = conc
        self._populate_table(conc)
        QMessageBox.information(
            self,
            "Loaded",
            f"Loaded {len(conc)} concentration points from '{source}'.\n"
            "Click Close to apply to the current session.",
        )
        self.accept()
