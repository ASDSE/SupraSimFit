"""DataPanel — file loading and concentration vector management."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.data_processing.measurement_set import MeasurementSet
from core.io import load_measurements
from core.io.registry import READERS


def _build_file_filter() -> str:
    """Build QFileDialog filter string from registered I/O readers."""
    parts = []
    for ext, cls in sorted(READERS.items()):
        parts.append(f"*{ext}")
    all_exts = " ".join(parts)
    return f"Measurement files ({all_exts});;All files (*)"


class DataPanel(QGroupBox):
    """Load measurement data files and manage concentration vectors.

    Signals
    -------
    data_loaded(MeasurementSet)
        Emitted after a file is successfully loaded and parsed.
    data_cleared()
        Emitted when data is removed.
    """

    data_loaded = pyqtSignal(object)   # MeasurementSet
    data_cleared = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Data", parent)
        self._ms: MeasurementSet | None = None
        self._source_path: str | None = None
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Info labels
        self._file_label = QLabel("No file loaded")
        self._file_label.setWordWrap(True)
        self._info_label = QLabel("")
        layout.addWidget(self._file_label)
        layout.addWidget(self._info_label)

        # Concentration vector button (enabled after data is loaded)
        self._conc_btn = QPushButton("Conc. Vector…")
        self._conc_btn.setEnabled(False)
        self._conc_btn.clicked.connect(self._on_conc_vector)
        layout.addWidget(self._conc_btn)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_file(self, path: str | None = None) -> None:
        """Load a measurement file, optionally bypassing the dialog."""
        if path is None:
            path, _ = QFileDialog.getOpenFileName(
                self, "Load Measurement File", "", _build_file_filter()
            )
        if not path:
            return
        try:
            df = load_measurements(path)
            ms = MeasurementSet.from_dataframe(df, source_file=str(path))
            self._ms = ms
            self._source_path = path
            self._update_info()
            self._conc_btn.setEnabled(True)
            self.data_loaded.emit(ms)
        except Exception as exc:
            QMessageBox.warning(self, "Load Error", f"Could not load file:\n{exc}")

    def clear(self) -> None:
        self._ms = None
        self._source_path = None
        self._file_label.setText("No file loaded")
        self._info_label.setText("")
        self._conc_btn.setEnabled(False)
        self.data_cleared.emit()

    def current_path(self) -> str | None:
        return self._source_path

    def measurement_set(self) -> MeasurementSet | None:
        return self._ms

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _on_conc_vector(self) -> None:
        if self._ms is None:
            return
        from gui.dialogs.concentration_dialog import ConcentrationDialog

        dlg = ConcentrationDialog(self._ms.concentrations, parent=self)
        if dlg.exec():
            new_conc = dlg.result_concentrations()
            if new_conc is not None:
                self._rebuild_ms_with_concentrations(new_conc)

    def _update_info(self) -> None:
        if self._ms is None:
            return
        name = Path(self._source_path).name if self._source_path else "?"
        self._file_label.setText(name)
        self._info_label.setText(
            f"{self._ms.n_points} points × {self._ms.n_replicas} replicas"
        )

    def _rebuild_ms_with_concentrations(self, new_conc) -> None:
        """Rebuild MeasurementSet with a new concentration vector."""
        import numpy as np

        ms = self._ms
        if len(new_conc) != ms.n_points:
            QMessageBox.warning(
                self,
                "Mismatch",
                f"Concentration vector has {len(new_conc)} points but data has "
                f"{ms.n_points}. They must match.",
            )
            return
        try:
            rows = []
            for i, (rid, sig) in enumerate(ms.iter_replicas(active_only=False)):
                for j, (c, s) in enumerate(zip(new_conc, sig)):
                    rows.append({"concentration": c, "signal": float(s), "replica": i})
            df = pd.DataFrame(rows)
            new_ms = MeasurementSet.from_dataframe(df, source_file=self._source_path)
            self._ms = new_ms
            self._update_info()
            self.data_loaded.emit(new_ms)
        except Exception as exc:
            QMessageBox.warning(self, "Error", f"Failed to apply concentration vector:\n{exc}")
