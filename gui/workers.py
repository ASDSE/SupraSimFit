"""Background worker threads for long-running operations."""

from __future__ import annotations

import logging
import time
from typing import Any

from numpy.linalg import LinAlgError
from PyQt6.QtCore import QThread, pyqtSignal

from core.assays.base import BaseAssay
from core.data_processing.measurement_set import MeasurementSet
from core.optimizer.multistart import FitCancelled
from core.pipeline.fit_pipeline import FitConfig, PerReplicaFitError, fit_measurement_set
from core.pipeline.profile import fit_profile
from core.pipeline.sensitivity import SensitivityConfig, SensitivityRunError, run_sensitivity
from gui.widgets.replica_panel import describe_replicates

logger = logging.getLogger(__name__)

# Seconds between progress signals, about ten a second: a parallel run finishes
# hundreds of fits a second, and each signal repaints the progress bar and the
# status bar on the interface thread.
_PROGRESS_INTERVAL = 0.1

#: Shown when the Ka profile fails for a reason the pipeline does not state itself.
_PROFILE_FAILED = 'The range of Kₐ your data support could not be worked out for this fit.'

#: Shown when the sensitivity analysis fails for a reason the pipeline does not state itself.
_SENSITIVITY_FAILED = (
    'The sensitivity analysis could not be completed. Check the data, the assay conditions and the '
    'input uncertainties, then run it again.'
)


#: The signals a caller listens to on its workers; a retired worker's are cut.
_WORKER_SIGNALS = ('finished', 'error', 'progress', 'stopped')

#: How long the interface waits for a dropped worker. A worker that was asked
#: to stop ends at its next cancel check, which is well inside this; a run that
#: cannot answer that fast finishes on its own instead of holding the window.
_RETIRE_WAIT_MS = 2000

#: Workers that outlasted that wait. Their signals reach nothing, so they only
#: run out their work; they are held here so that neither Python nor a closing
#: tab destroys a thread that is still running, and each drops itself when its
#: thread ends.
_RUNNING_ON: set[QThread] = set()


def _release(worker: QThread) -> None:
    """Let go of a worker whose thread has ended."""
    _RUNNING_ON.discard(worker)
    worker.deleteLater()


def retire(worker: QThread | None) -> None:
    """Cut *worker* loose: its signals reach nothing, and its object is deleted once its thread ends.

    Every path that drops a background worker goes through here. A ``QThread``
    destroyed while its thread still runs aborts the process, and a sensitivity
    run left going holds its worker processes, so seeing the thread out is what
    makes closing a tab or the window safe. Past ``_RETIRE_WAIT_MS`` the worker
    is seen out in the background rather than on the interface thread, so the
    window never stops repainting for a run that takes its time stopping.
    """
    if worker is None:
        return
    for name in _WORKER_SIGNALS:
        signal = getattr(worker, name, None)
        if signal is None:
            continue
        try:
            signal.disconnect()
        except TypeError:
            pass  # nothing was connected to it
    if worker.wait(_RETIRE_WAIT_MS):
        worker.deleteLater()
        return
    worker.setParent(None)  # the session may close before it ends
    _RUNNING_ON.add(worker)
    # QThread.finished, which the workers' own finished signal shadows.
    QThread.finished.__get__(worker, QThread).connect(lambda: _release(worker))
    # A thread that ended between the wait and the connect has emitted
    # finished already and will not emit it again.
    if worker.isFinished():
        _release(worker)


def _per_replicate_failure_text(exc: PerReplicaFitError, replica_ids) -> str:
    """The exception's own sentence, each replicate's reason under it, and what to change."""
    names = {rid: describe_replicates([rid], replica_ids) for rid in exc.failures}
    details = '\n'.join(
        f'  • {names[rid][0].upper()}{names[rid][1:]}: {reason}' for rid, reason in exc.failures.items()
    )
    return f'{exc}\n\n{details}\n\nTry lowering Min R², increasing Trials, or widening the parameter bounds.'


class FitWorker(QThread):
    """Run :func:`fit_measurement_set` in a background thread.

    Prevents the GUI from freezing during multi-start L-BFGS-B optimization.
    The inputs stay readable as ``ms``, ``assay_cls``, ``conditions`` and
    ``config``, so the fit's Ka profile can be computed on the same inputs.
    :meth:`cancel` stops the fit between optimizer runs; a cancelled fit ends
    quietly, emitting neither signal, because it has no result to report.

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
        self._cancelled = False

    def cancel(self) -> None:
        """Ask the fit to stop at the next optimizer run."""
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        """Whether :meth:`cancel` was called."""
        return self._cancelled

    def run(self) -> None:
        try:
            result = fit_measurement_set(
                self.ms, self.assay_cls, self.conditions, self.config, should_cancel=lambda: self._cancelled
            )
            self.finished.emit(result)
        except FitCancelled:
            return
        except PerReplicaFitError as exc:
            self.error.emit(_per_replicate_failure_text(exc, self.ms.replica_ids))
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
        Emitted if the profile cannot be computed: the pipeline's own message
        for a reason it states itself, and one plain sentence for anything
        else, which is logged with its traceback.

    :meth:`cancel` stops the profile at the next Ka it evaluates; a cancelled
    profile ends quietly, emitting neither signal, because it has nothing to
    report.
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
        self._cancelled = False

    def cancel(self) -> None:
        """Request early termination; surfaced to the profile via ``should_cancel``."""
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        """Whether :meth:`cancel` was called."""
        return self._cancelled

    def run(self) -> None:
        try:
            self.finished.emit(
                fit_profile(
                    self._ms,
                    self._assay_cls,
                    self._conditions,
                    self._config,
                    should_cancel=lambda: self._cancelled,
                )
            )
        except FitCancelled:
            return
        except LinAlgError:
            # A linear-algebra failure is a ValueError, but its text is library
            # jargon: it is reported like any other unexpected failure.
            logger.exception('Ka profile failed')
            self.error.emit(_PROFILE_FAILED)
        except ValueError as exc:
            self.error.emit(f'The range of Kₐ your data support could not be worked out:\n{exc}')
        except Exception:
            logger.exception('Ka profile failed')
            self.error.emit(_PROFILE_FAILED)


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
    max_workers : int, optional
        Worker processes the analysis may use.
    input_labels : dict[str, str], optional
        Input key to the plain name the panel shows for it, so the analysis
        names an input the way the user sees it.

    Signals
    -------
    progress(int, int)
        Emitted as ``(done, total)`` at most every ``_PROGRESS_INTERVAL``
        seconds; the latest count is always emitted once a cancel is seen and
        before ``finished``.
    finished(SensitivityResult)
        Emitted on successful completion.
    stopped()
        Emitted instead of ``finished`` when a cancel arrives before the run
        has anything to report, so there is no partial result to show.
    error(str)
        Emitted if the analysis cannot be completed: the pipeline's own message
        for a reason it states itself, and one plain sentence for anything
        else, which is logged with its traceback.
    """

    progress = pyqtSignal(int, int)  # (done, total)
    finished = pyqtSignal(object)  # SensitivityResult
    stopped = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(
        self,
        ms: MeasurementSet,
        assay_cls: type[BaseAssay],
        conditions: dict[str, Any],
        fit_config: FitConfig,
        sens_config: SensitivityConfig,
        max_workers: int | None = None,
        input_labels: dict[str, str] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._ms = ms
        self._assay_cls = assay_cls
        self._conditions = conditions
        self._fit_config = fit_config
        self._sens_config = sens_config
        self._max_workers = max_workers
        self._input_labels = input_labels
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
                input_labels=self._input_labels,
            )
            self._flush_progress()
            self.finished.emit(result)
        except FitCancelled:
            # Cancelled before there was a baseline fit, so there is no partial
            # result to show: the run reports only that it stopped.
            self._flush_progress()
            self.stopped.emit()
        except PerReplicaFitError as exc:
            # The baseline fit is an ordinary fit, and its per-replicate reasons
            # are reported here exactly as the Fit Curve tab reports them.
            self.error.emit(_per_replicate_failure_text(exc, self._ms.replica_ids))
        except SensitivityRunError as exc:
            # The analysis stopped on a re-fit it could not work around and says
            # so in words the user can act on.
            logger.exception('Sensitivity analysis stopped on a failed re-fit')
            self.error.emit(str(exc))
        except LinAlgError:
            # A linear-algebra failure is a ValueError, but its text is library
            # jargon: it is reported like any other unexpected failure.
            logger.exception('Sensitivity analysis failed')
            self.error.emit(_SENSITIVITY_FAILED)
        except ValueError as exc:
            self.error.emit(f'The sensitivity analysis could not run:\n{exc}')
        except Exception:
            logger.exception('Sensitivity analysis failed')
            self.error.emit(_SENSITIVITY_FAILED)
