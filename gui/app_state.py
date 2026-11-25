"""Per-session application state for the unified fitting GUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.data_processing.measurement_set import MeasurementSet
from core.pipeline.fit_pipeline import FitResult
from core.pipeline.sensitivity import SensitivityResult


@dataclass
class SessionState:
    """Mutable state for one fitting session (one tab).

    All widgets within a FittingSession share this state via the
    FittingSession coordinator — widgets never hold references to each other.
    The settings the panels show (assay type, conditions, bounds, replicate
    mode, input uncertainties) are read from the panels themselves and not
    copied here.
    """

    # Data
    measurement_set: Optional[MeasurementSet] = None
    source_file: Optional[str] = None

    # Results. A result is held until the data change or a new result replaces
    # it. It is shown while the loaded selection and the settings (data, active
    # replicates, conditions, assay type, bounds, replicate mode, uncertainties)
    # match its record, and hidden otherwise, with a note saying why; a hidden
    # result comes back unchanged once they match.
    held_fit_results: list[FitResult] = field(default_factory=list)
    hidden_fit_notes: dict[str, str] = field(default_factory=dict)  # FitResult.id -> why it is hidden
    sensitivity_result: Optional[SensitivityResult] = None
    sensitivity_note: Optional[str] = None  # why the sensitivity result is hidden, None while it is shown

    # Plot display unit (concentration unit used for the x-axis). Lives in
    # session state so it survives style-widget reconstructions and is the
    # source of truth for the value that ends up in style['axes']['x_unit'].
    display_unit: str = 'µM'

    @property
    def fit_results(self) -> list[FitResult]:
        """The held fit results that are shown: every number, curve and export uses these."""
        return [result for result in self.held_fit_results if result.id not in self.hidden_fit_notes]
