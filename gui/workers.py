"""Background worker threads for long-running operations."""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal

from core.assays.base import BaseAssay
from core.data_processing.measurement_set import MeasurementSet
from core.pipeline.fit_pipeline import FitConfig, FitResult, PerReplicateFitError, fit_measurement_set


class FitWorker(QThread):
    """Run :func:`fit_measurement_set` in a background thread.

    Prevents the GUI from freezing during multi-start L-BFGS-B optimization.

    Parameters
    ----------
    ms : MeasurementSet
        Measurement data (will use average signal).
    assay_cls : type[BaseAssay]
        Assay class to fit.
    conditions : dict
        Assay conditions (Ka_dye, h0, etc.).
    config : FitConfig
        Optimizer configuration.
    source_file : str, optional
        Original filename, stored in FitResult metadata.

    Signals
    -------
    finished(FitResult)
        Emitted on successful completion.
    error(str)
        Emitted if an exception is raised.
    """

    finished = pyqtSignal(object)   # FitResult
    error = pyqtSignal(str)

    def __init__(
        self,
        ms: MeasurementSet,
        assay_cls: type[BaseAssay],
        conditions: dict[str, Any],
        config: FitConfig,
        source_file: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._ms = ms
        self._assay_cls = assay_cls
        self._conditions = conditions
        self._config = config
        self._source_file = source_file

    def run(self) -> None:
        try:
            result = fit_measurement_set(
                self._ms,
                self._assay_cls,
                self._conditions,
                self._config,
            )
            self.finished.emit(result)
        except PerReplicateFitError as exc:
            details = '\n'.join(f'  - {rid}: {reason}' for rid, reason in exc.failures.items())
            self.error.emit(f'{exc}\n\nFailures per replica:\n{details}')
        except Exception as exc:
            self.error.emit(str(exc))
