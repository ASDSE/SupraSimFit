"""BoundsPanel — registry-driven parameter bounds editor with dye-alone priors."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QFileDialog,
)

from core.assays.registry import ASSAY_REGISTRY, AssayType
from gui.plotting.labels import fmt_param


def _parse_sci(text: str) -> float | None:
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


class _BoundRow(QWidget):
    """A single row: label | lower QLineEdit | '—' | upper QLineEdit."""

    def __init__(self, key: str, lo: float, hi: float, parent=None):
        super().__init__(parent)
        self.key = key
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self._lo = QLineEdit(f"{lo:.3e}")
        self._lo.setFixedWidth(90)
        self._hi = QLineEdit(f"{hi:.3e}")
        self._hi.setFixedWidth(90)
        row.addWidget(self._lo)
        row.addWidget(QLabel("—"))
        row.addWidget(self._hi)

    def values(self) -> tuple[float, float] | None:
        lo = _parse_sci(self._lo.text())
        hi = _parse_sci(self._hi.text())
        if lo is None or hi is None:
            return None
        return lo, hi

    def set_values(self, lo: float, hi: float) -> None:
        self._lo.setText(f"{lo:.3e}")
        self._hi.setText(f"{hi:.3e}")

    def default_lo(self) -> float:
        return _parse_sci(self._lo.text()) or 0.0

    def default_hi(self) -> float:
        return _parse_sci(self._hi.text()) or 1.0


class BoundsPanel(QGroupBox):
    """Registry-driven parameter bounds editor.

    Auto-populates from ``ASSAY_REGISTRY[assay_type].default_bounds`` when the
    assay type changes.  Supports loading dye-alone priors to constrain the
    signal coefficient parameters.

    Signals
    -------
    bounds_changed()
        Emitted when any bound field is edited.
    dye_alone_requested()
        Emitted when the user clicks 'Load Dye-Alone…'.
    """

    bounds_changed = pyqtSignal()
    dye_alone_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Parameter Bounds", parent)
        self._rows: dict[str, _BoundRow] = {}
        self._defaults: dict[str, tuple[float, float]] = {}
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_assay_type(self, assay_type: AssayType) -> None:
        meta = ASSAY_REGISTRY[assay_type]
        self._defaults = dict(meta.default_bounds)
        self._rebuild_form(meta.default_bounds)

    def current_bounds(self) -> dict[str, tuple[float, float]] | None:
        """Return custom bounds or None if all match defaults."""
        result = {}
        for key, row in self._rows.items():
            vals = row.values()
            if vals is None:
                continue
            result[key] = vals
        # If all values equal defaults, return None (use registry defaults)
        if result == self._defaults:
            return None
        return result or None

    def apply_dye_alone_bounds(self, bounds: dict[str, tuple[float, float]]) -> None:
        """Apply dye-alone–derived bounds to I0 and I_dye_free rows."""
        for key, (lo, hi) in bounds.items():
            if key in self._rows:
                self._rows[key].set_values(lo, hi)
        self.bounds_changed.emit()

    def reset_to_defaults(self) -> None:
        for key, (lo, hi) in self._defaults.items():
            if key in self._rows:
                self._rows[key].set_values(lo, hi)
        self.bounds_changed.emit()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Form area
        self._form_widget = QWidget()
        self._form_layout = QFormLayout(self._form_widget)
        self._form_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._form_widget)

        # Reset defaults button
        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self.reset_to_defaults)
        layout.addWidget(reset_btn)

        # Dye-alone section
        self._dye_alone_cb = QCheckBox("Use dye-alone priors for signal bounds")
        self._dye_alone_cb.toggled.connect(self._on_dye_alone_toggled)
        layout.addWidget(self._dye_alone_cb)

        self._dye_alone_btn = QPushButton("Load Dye-Alone…")
        self._dye_alone_btn.setEnabled(False)
        self._dye_alone_btn.clicked.connect(self._on_load_dye_alone)
        layout.addWidget(self._dye_alone_btn)

    def _rebuild_form(self, default_bounds: dict) -> None:
        self._rows.clear()
        while self._form_layout.rowCount():
            self._form_layout.removeRow(0)

        for key, (lo, hi) in default_bounds.items():
            row = _BoundRow(key, lo, hi)
            row._lo.textChanged.connect(self.bounds_changed)
            row._hi.textChanged.connect(self.bounds_changed)
            self._form_layout.addRow(fmt_param(key) + ":", row)
            self._rows[key] = row

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_dye_alone_toggled(self, checked: bool) -> None:
        self._dye_alone_btn.setEnabled(checked)

    def _on_load_dye_alone(self) -> None:
        from core.io.registry import READERS
        exts = " ".join(f"*{e}" for e in sorted(READERS.keys()))
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Dye-Alone Data", "", f"Measurement files ({exts});;All files (*)"
        )
        if not path:
            return
        try:
            from core.io import load_measurements
            from core.data_processing.measurement_set import MeasurementSet
            from core.assays import DyeAloneAssay
            from core.pipeline.fit_pipeline import fit_linear_assay, bounds_from_dye_alone

            df = load_measurements(path)
            ms = MeasurementSet.from_dataframe(df)
            assay = ms.to_assay(DyeAloneAssay, conditions={})
            result = fit_linear_assay(assay)
            bounds = bounds_from_dye_alone(result, margin=0.2)
            self.apply_dye_alone_bounds(bounds)
            QMessageBox.information(
                self,
                "Dye-Alone Loaded",
                "Signal coefficient bounds updated from dye-alone fit.",
            )
        except Exception as exc:
            QMessageBox.warning(self, "Dye-Alone Error", str(exc))
