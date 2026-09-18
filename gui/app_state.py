"""Per-session application state for the unified fitting GUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.assays.registry import AssayType
from core.data_processing.measurement_set import MeasurementSet
from core.pipeline.fit_pipeline import FitConfig, FitResult
from core.pipeline.profile import ProfileSet
from core.pipeline.sensitivity import SensitivityResult
from core.units import Quantity


@dataclass
class SessionState:
    """Mutable state for one fitting session (one tab).

    All widgets within a FittingSession share this state via the
    FittingSession coordinator — widgets never hold references to each other.
    """

    # Data
    measurement_set: Optional[MeasurementSet] = None
    source_file: Optional[str] = None

    # Assay configuration
    assay_type: AssayType = AssayType.GDA

    # Fit configuration
    fit_config: FitConfig = field(default_factory=FitConfig)
    custom_bounds: Optional[dict[str, tuple[Quantity, Quantity]]] = None

    # Preprocessing steps spec — passed to apply_preprocessing()
    preprocessing_steps: list[dict] = field(default_factory=list)

    # Results. A result is held until the data change or a new result replaces
    # it. It is shown while the loaded selection (data, active replicates,
    # conditions, assay type) matches its record, and hidden otherwise, with a
    # note saying why; a hidden result comes back unchanged once they match.
    held_fit_results: list[FitResult] = field(default_factory=list)
    hidden_fit_notes: dict[str, str] = field(default_factory=dict)  # FitResult.id -> why it is hidden
    dye_alone_result: Optional[FitResult] = None
    profile_result: Optional[ProfileSet] = None  # Ka profiles of the fit run in this session
    sensitivity_result: Optional[SensitivityResult] = None
    sensitivity_note: Optional[str] = None  # why the sensitivity result is hidden, None while it is shown

    # Plot display unit (concentration unit used for the x-axis). Lives in
    # session state so it survives style-widget reconstructions and is the
    # source of truth for the value that ends up in style['axes']['x_unit'].
    display_unit: str = 'µM'

    def has_data(self) -> bool:
        return self.measurement_set is not None

    @property
    def fit_results(self) -> list[FitResult]:
        """The held fit results that are shown: every number, curve and export uses these."""
        return [result for result in self.held_fit_results if result.id not in self.hidden_fit_notes]
