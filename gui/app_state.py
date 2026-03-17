"""Per-session application state for the unified fitting GUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from core.assays.registry import AssayType
from core.data_processing.measurement_set import MeasurementSet
from core.pipeline.fit_pipeline import FitConfig, FitResult


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
    conditions: dict[str, Any] = field(default_factory=dict)

    # Fit configuration
    fit_config: FitConfig = field(default_factory=FitConfig)
    custom_bounds: Optional[dict[str, tuple[float, float]]] = None

    # Preprocessing steps spec — passed to apply_preprocessing()
    preprocessing_steps: list[dict] = field(default_factory=list)

    # Results
    fit_results: list[FitResult] = field(default_factory=list)
    dye_alone_result: Optional[FitResult] = None

    def has_data(self) -> bool:
        return self.measurement_set is not None

    def clear_results(self) -> None:
        self.fit_results.clear()
        self.dye_alone_result = None
