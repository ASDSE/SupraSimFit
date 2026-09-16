"""Background worker threads for long-running operations."""

from __future__ import annotations

import logging
import time
from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal

from core.assays.base import BaseAssay
from core.data_processing.measurement_set import MeasurementSet
from core.pipeline.fit_pipeline import FitConfig, PerReplicaFitError, fit_measurement_set
from core.pipeline.profile import fit_profile
from core.pipeline.sensitivity import SensitivityConfig, run_sensitivity
from gui.widgets.replica_panel import describe_replicates

logger = logging.getLogger(__name__)

# Seconds between progress signals, about ten a second: a parallel run finishes
# hundreds of fits a second, and each signal repaints the progress bar and the
# status bar on the interface thread.
_PROGRESS_INTERVAL = 0.1


class FitWorker(QThread):
    """Run :func:`fit_measurement_set` in a background thread.

    Prevents the GUI from freezing during multi-start L-BFGS-B optimization.
    The inputs stay readable as ``ms``, ``assay_cls``, ``conditions`` and
    ``config``, so the fit's Ka profile can be computed on the same inputs.

    Parameters
    ----------
    ms : MeasurementSet
        Measurement data, the worker's own copy: its active replicates are fitted.
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

    finished = pyqtSignal(object)  # FitResult
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
        self.ms = ms
        self.assay_cls = assay_cls
        self.conditions = conditions
        self.config = config
        self._source_file = source_file

    def run(self) -> None:
        try:
            result = fit_measurement_set(self.ms, self.assay_cls, self.conditions, self.config)
            self.finished.emit(result)
        except PerReplicaFitError as exc:
            names = {rid: describe_replicates([rid], self.ms.replica_ids) for rid in exc.failures}
            details = '\n'.join(
                f'  • {names[rid][0].upper()}{names[rid][1:]}: {reason}' for rid, reason in exc.failures.items()
            )
            self.error.emit(
                f'{exc}\n\n{details}\n\nTry lowering Min R², increasing Trials, or widening the parameter bounds.'
            )
        except Exception:
            logger.exception('Fit failed')
            self.error.emit(
                'The fit could not be completed. Check the assay conditions and the parameter bounds, then run it again.'
            )


class ProfileWorker(QThread):
    """Run :func:`fit_profile` in a background thread.

    Parameters
    ----------
    ms : MeasurementSet
        Measurement data the fit used.
    assay_cls : type[BaseAssay]
        Assay class the fit used.
    conditions : dict
        Assay conditions the fit used.
    config : FitConfig
        Configuration the fit used; its replicate handling and bounds apply.

    Signals
    -------
    finished(ProfileResult)
        Emitted on successful completion.
    error(str)
        Emitted if the profile cannot be computed.
    """

    finished = pyqtSignal(object)  # ProfileResult
    error = pyqtSignal(str)

    def __init__(
        self,
        ms: MeasurementSet,
        assay_cls: type[BaseAssay],
        conditions: dict[str, Any],
        config: FitConfig,
        parent=None,
    ):
        super().__init__(parent)
        self._ms = ms
        self._assay_cls = assay_cls
        self._conditions = conditions
        self._config = config

    def run(self) -> None:
        try:
            self.finished.emit(fit_profile(self._ms, self._assay_cls, self._conditions, self._config))
        except ValueError as exc:
            self.error.emit(f'The range of Kₐ your data support could not be worked out:\n{exc}')
        except Exception:
            self.error.emit('The range of Kₐ your data support could not be worked out for this fit.')


class SensitivityWorker(QThread):
    """Run :func:`run_sensitivity` in a background thread.

    Keeps the GUI responsive while the sensitivity analysis re-runs the fit
    many times over perturbed inputs.

    Parameters
    ----------
    ms : MeasurementSet
        Measurement data (its averaged active signal is used).
    assay_cls : type[BaseAssay]
        Assay class to build each perturbed fit with.
    conditions : dict
        Baseline assay conditions (Ka_dye, h0, etc.) as pint Quantities.
    fit_config : FitConfig
        Per-fit optimizer configuration.
    sens_config : SensitivityConfig
        What to perturb and how.

    Signals
    -------
    progress(int, int)
        Emitted as ``(done, total)`` at most every ``_PROGRESS_INTERVAL``
        seconds; the latest count is always emitted once a cancel is seen and
        before ``finished``.
    finished(SensitivityResult)
        Emitted on successful completion.
    error(str)
        Emitted if the analysis cannot be completed.
    """

    progress = pyqtSignal(int, int)  # (done, total)
    finished = pyqtSignal(object)  # SensitivityResult
    error = pyqtSignal(str)

    def __init__(
        self,
        ms: MeasurementSet,
        assay_cls: type[BaseAssay],
        conditions: dict[str, Any],
        fit_config: FitConfig,
        sens_config: SensitivityConfig,
        max_workers: int | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._ms = ms
        self._assay_cls = assay_cls
        self._conditions = conditions
        self._fit_config = fit_config
        self._sens_config = sens_config
        self._max_workers = max_workers
        self._cancelled = False
        self._last_progress = float('-inf')
        self._pending_progress: tuple[int, int] | None = None

    def cancel(self) -> None:
        """Request early termination; surfaced to the driver via ``should_cancel``."""
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        """Whether :meth:`cancel` was called."""
        return self._cancelled

    def _should_cancel(self) -> bool:
        """Answer the driver's cancel check, first emitting a held-back count on a cancel.

        After a cancel the driver waits for the fits still running before it
        returns, so a count held until then would reach the bar late.
        """
        if self._cancelled:
            self._flush_progress()
        return self._cancelled

    def _flush_progress(self) -> None:
        """Emit the held-back count, if any."""
        if self._pending_progress is not None:
            self.progress.emit(*self._pending_progress)
            self._pending_progress = None

    def _report_progress(self, done: int, total: int) -> None:
        """Emit a count once per interval, holding back the latest one in between."""
        now = time.monotonic()
        if now - self._last_progress < _PROGRESS_INTERVAL:
            self._pending_progress = (done, total)
            return
        self._last_progress = now
        self._pending_progress = None
        self.progress.emit(done, total)

    def run(self) -> None:
        try:
            result = run_sensitivity(
                self._ms,
                self._assay_cls,
                self._conditions,
                self._fit_config,
                self._sens_config,
                progress=self._report_progress,
                should_cancel=self._should_cancel,
                max_workers=self._max_workers,
            )
            self._flush_progress()
            self.finished.emit(result)
        except ValueError as exc:
            self.error.emit(f'The sensitivity analysis could not run:\n{exc}')
        except Exception as exc:
            self.error.emit(f'The sensitivity analysis could not be completed:\n{exc}')
