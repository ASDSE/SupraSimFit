"""Background worker threads for long-running operations."""

from __future__ import annotations

import logging
import time
from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal

from core.assays.base import BaseAssay
from core.data_processing.measurement_set import MeasurementSet
from core.pipeline.fit_pipeline import FitConfig, fit_measurement_set
from core.pipeline.input_aware import AwareResult
from core.pipeline.profile import fit_profile
from core.pipeline.sensitivity import SensitivityConfig, SensitivityRunError, run_sensitivity
from core.pipeline.varpro import FitCancelled, FitRefused

logger = logging.getLogger(__name__)

# Seconds between progress signals, about ten a second: a parallel run finishes
# hundreds of fits a second, and each signal repaints the progress bar and the
# status bar on the interface thread.
_PROGRESS_INTERVAL = 0.1

#: Shown when the fit fails for a reason the pipeline does not state itself.
_FIT_FAILED = (
    'The fit could not be completed. Check the assay conditions, the parameter bounds and the '
    'input uncertainties, then run it again.'
)

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


class FitWorker(QThread):
    """Run :func:`fit_measurement_set` in a background thread.

    Keeps the interface responsive while the fit searches the Ka bounds and,
    where an input may move within a stated uncertainty, works out the interval
    that lets it (seconds on most data, longer on a model with two binding
    constants). The inputs stay readable as ``ms``, ``assay_cls``,
    ``conditions`` and ``config``, so the fit's Ka profiles can be computed on
    the same inputs. :meth:`cancel` stops the fit at its next equilibrium
    solve, which every part of it asks before; a cancelled fit ends quietly,
    emitting neither signal, because it has no result to report.

    Parameters
    ----------
    ms : MeasurementSet
        Measurement data, the worker's own copy: its active replicates are fitted.
    assay_cls : type[BaseAssay]
        Assay class to fit.
    conditions : dict
        Assay conditions (Ka_dye, h0, etc.).
    config : FitConfig
        Fitting configuration.
    source_file : str, optional
        Original filename, stored in FitResult metadata.

    Signals
    -------
    finished(FitResult)
        Emitted on successful completion.
    error(str)
        Emitted when the fit cannot be made: the pipeline's own message for a
        reason it states itself, and one plain sentence for anything else,
        which is logged with its traceback.
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
        """Ask the fit to stop at the next equilibrium solve."""
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
        except FitRefused as exc:
            # The pipeline refuses a fit it cannot make in words the user can
            # act on — which replicate, which bound, what to change.
            self.error.emit(str(exc))
        except Exception:
            # Anything else, a library's own ValueError included, carries text
            # written for a developer: it is logged and reported in one sentence.
            logger.exception('Fit failed')
            self.error.emit(_FIT_FAILED)


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
    aware : AwareResult or None
        The penalised profiles the fit itself made
        (:attr:`~core.pipeline.fit_pipeline.FitResult.aware`), passed straight
        through so the tab draws the fit's own curves and interval rather than
        a second computation of them. ``None`` for a fit that took every input
        as entered, which has none.

    Signals
    -------
    finished(ProfileSet)
        Emitted on successful completion: one profile per binding constant and,
        for a model with two free ones, their joint region.
    error(str)
        Emitted if the profile cannot be computed: the pipeline's own message
        for a reason it states itself, and one plain sentence for anything
        else, which is logged with its traceback.

    :meth:`cancel` stops the profile at the next Ka it evaluates; a cancelled
    profile ends quietly, emitting neither signal, because it has nothing to
    report.
    """

    finished = pyqtSignal(object)  # ProfileSet
    error = pyqtSignal(str)

    def __init__(
        self,
        ms: MeasurementSet,
        assay_cls: type[BaseAssay],
        conditions: dict[str, Any],
        config: FitConfig,
        aware: AwareResult | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._ms = ms
        self._assay_cls = assay_cls
        self._conditions = conditions
        self._config = config
        self._aware = aware
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
                    aware=self._aware,
                )
            )
        except FitCancelled:
            return
        except FitRefused as exc:
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
        Configuration every re-fit runs with.
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
        except SensitivityRunError as exc:
            # The analysis stopped on a re-fit it could not work around and says
            # so in words the user can act on.
            logger.exception('Sensitivity analysis stopped on a failed re-fit')
            self.error.emit(str(exc))
        except FitRefused as exc:
            self.error.emit(f'The sensitivity analysis could not run:\n{exc}')
        except Exception:
            logger.exception('Sensitivity analysis failed')
            self.error.emit(_SENSITIVITY_FAILED)
