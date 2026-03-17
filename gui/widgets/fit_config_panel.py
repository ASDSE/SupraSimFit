"""FitConfigPanel — optimizer configuration (n_trials, RMSE factor, min R²)."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QSpinBox,
)

from core.pipeline.fit_pipeline import FitConfig


class FitConfigPanel(QGroupBox):
    """Editor for :class:`~core.pipeline.fit_pipeline.FitConfig` parameters.

    Signals
    -------
    config_changed()
        Emitted whenever any field value changes.
    """

    config_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Fit Configuration", parent)
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def current_config(self) -> FitConfig:
        return FitConfig(
            n_trials=self._trials_spin.value(),
            rmse_threshold_factor=self._rmse_spin.value(),
            min_r_squared=self._r2_spin.value(),
        )

    def set_config(self, config: FitConfig) -> None:
        self._trials_spin.setValue(config.n_trials)
        self._rmse_spin.setValue(config.rmse_threshold_factor)
        self._r2_spin.setValue(config.min_r_squared)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        form = QFormLayout(self)

        self._trials_spin = QSpinBox()
        self._trials_spin.setRange(10, 10_000)
        self._trials_spin.setSingleStep(10)
        self._trials_spin.setValue(100)
        self._trials_spin.setToolTip("Number of multi-start L-BFGS-B optimization trials.")
        self._trials_spin.valueChanged.connect(self.config_changed)
        form.addRow("Trials:", self._trials_spin)

        self._rmse_spin = QDoubleSpinBox()
        self._rmse_spin.setRange(1.0, 10.0)
        self._rmse_spin.setSingleStep(0.1)
        self._rmse_spin.setDecimals(2)
        self._rmse_spin.setValue(1.5)
        self._rmse_spin.setToolTip(
            "Trials with RMSE > (best_RMSE × factor) are discarded before aggregation."
        )
        self._rmse_spin.valueChanged.connect(self.config_changed)
        form.addRow("RMSE factor:", self._rmse_spin)

        self._r2_spin = QDoubleSpinBox()
        self._r2_spin.setRange(0.0, 1.0)
        self._r2_spin.setSingleStep(0.01)
        self._r2_spin.setDecimals(2)
        self._r2_spin.setValue(0.90)
        self._r2_spin.setToolTip("Minimum R² for a trial to pass the acceptance filter.")
        self._r2_spin.valueChanged.connect(self.config_changed)
        form.addRow("Min R²:", self._r2_spin)
