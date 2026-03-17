"""OutlierRemovalPanel — Z-Score filter configuration and execution."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)
from PyQt6.QtCore import QLocale, pyqtSignal

from core.data_processing.measurement_set import MeasurementSet
from core.data_processing.preprocessing import apply_preprocessing

_LOCALE_EN = QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)


class PreprocessingPanel(QGroupBox):
    """Configure and apply outlier removal to a MeasurementSet.

    Exposes the Z-Score replica filter.  If the configured minimum replica
    count cannot be met, the user is notified via a dialog — the filter is
    never silently skipped.

    Signals
    -------
    preprocessing_applied()
        Emitted after a step is applied (MeasurementSet modified in-place).
    preprocessing_reset()
        Emitted after ``ms.reset_active()`` is called.
    """

    preprocessing_applied = pyqtSignal()
    preprocessing_reset = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Outlier Removal", parent)
        self._ms: MeasurementSet | None = None
        self._setup_ui()
        self.setEnabled(False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_measurement_set(self, ms: MeasurementSet) -> None:
        self._ms = ms
        self.setEnabled(True)
        self._status_label.setText("")

    def current_steps(self) -> list[dict]:
        """Return preprocessing step configuration list for :func:`apply_preprocessing`."""
        return [
            {
                "name": "zscore_replica_filter",
                "params": {
                    "threshold": self._threshold_spin.value(),
                    "min_replicas": self._min_rep_spin.value(),
                },
            }
        ]

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        form = QFormLayout()

        # Z-Score threshold
        self._threshold_spin = QDoubleSpinBox()
        self._threshold_spin.setLocale(_LOCALE_EN)
        self._threshold_spin.setRange(0.5, 10.0)
        self._threshold_spin.setSingleStep(0.5)
        self._threshold_spin.setValue(3.5)
        self._threshold_spin.setDecimals(1)
        self._threshold_spin.setToolTip(
            "Modified z-score threshold.  Replicas where any point exceeds this "
            "threshold are deactivated.  Typical range: 2.5–4.0."
        )
        form.addRow("Z-score threshold:", self._threshold_spin)

        # Min replicas
        self._min_rep_spin = QSpinBox()
        self._min_rep_spin.setLocale(_LOCALE_EN)
        self._min_rep_spin.setRange(2, 20)
        self._min_rep_spin.setValue(3)
        self._min_rep_spin.setToolTip(
            "Minimum number of active replicas required to apply the filter."
        )
        form.addRow("Min replicas:", self._min_rep_spin)

        layout.addLayout(form)

        # Buttons
        btn_row = QHBoxLayout()
        apply_btn = QPushButton("Apply")
        apply_btn.setToolTip("Apply Z-score outlier filter to active replicas")
        apply_btn.clicked.connect(self._on_apply)
        reset_btn = QPushButton("Reset")
        reset_btn.setToolTip("Re-activate all replicas")
        reset_btn.clicked.connect(self._on_reset)
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(reset_btn)
        layout.addLayout(btn_row)

        # Status line
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_apply(self) -> None:
        if self._ms is None:
            return

        n_active = self._ms.n_active
        min_rep = self._min_rep_spin.value()
        if n_active < min_rep:
            QMessageBox.warning(
                self,
                "Cannot Apply Outlier Filter",
                f"Outlier removal requires at least <b>{min_rep}</b> active replicas, "
                f"but only <b>{n_active}</b> are currently active.<br><br>"
                f"To resolve this: lower <i>Min replicas</i> to {n_active} "
                f"or re-activate replicas using <i>Reset</i>.",
            )
            return

        apply_preprocessing(self._ms, self.current_steps())

        log = self._ms.processing_log
        if log:
            entry = log[-1]
            status = entry.get("status")
            if status == "applied":
                dropped = entry.get("dropped", [])
                if dropped:
                    self._status_label.setText(f"Dropped: {', '.join(dropped)}")
                else:
                    self._status_label.setText("No replicas dropped.")
            else:
                # Unexpected state — surface it to the user
                reason = entry.get("reason", "unknown reason")
                QMessageBox.warning(
                    self,
                    "Outlier Filter Not Applied",
                    f"The filter was not applied: {reason}\n\n"
                    f"Check your configuration and try again.",
                )
                return
        self.preprocessing_applied.emit()

    def _on_reset(self) -> None:
        if self._ms is None:
            return
        self._ms.reset_active()
        self._status_label.setText("All replicas activated.")
        self.preprocessing_reset.emit()
