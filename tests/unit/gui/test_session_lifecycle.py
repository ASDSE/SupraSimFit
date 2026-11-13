"""Closing a tab or the window stops the work the session started.

Destroying a running ``QThread`` aborts the process, and a sensitivity run left
going holds its worker processes, so a session cancels its fit, its Ka profile
and its sensitivity run, waits for each thread and deletes each worker before
its widgets go. The long runs are stood in for by functions that do nothing but
watch their cancel flag: what these tests pin is the stopping, not the science.

One analysis at a time is checked here too, and so is what the two runs are
given: both read the error sources from the one Input Uncertainty panel and
the dilution by the titrant from the Assay Configuration panel, and neither
starts while what a panel states cannot be used as set.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

pytest.importorskip('PyQt6')

from PyQt6.QtCore import QEvent, QThread  # noqa: E402

from core.assays.registry import AssayType  # noqa: E402
from core.pipeline.fit_pipeline import FitConfig  # noqa: E402
from core.pipeline.inputs import ErrorModel, InputSpec, SharedSource  # noqa: E402
from core.pipeline.varpro import FitCancelled  # noqa: E402
from core.units import Q_  # noqa: E402
from tests.unit.gui.test_sensitivity_gui import _fake_run, _made_on, _sobol_result  # noqa: E402

_IDA_DATA = Path(__file__).resolve().parents[3] / 'data' / 'IDA_system.txt'


def _wait_until(qapp, condition, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, 'timed out waiting for a background worker'
        qapp.processEvents()
        time.sleep(0.01)


def _settle(qapp) -> None:
    """Deliver what is queued, including the deferred deletions a finished worker asks for.

    Qt holds a ``deleteLater`` until the event loop it was called from returns,
    and there is none in a test, so the deletions are sent by their own type.
    """
    for _ in range(3):
        qapp.processEvents()
        qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture
def dialogs(monkeypatch):
    """Record the dialogs instead of blocking on them; a question is always answered Yes."""
    from PyQt6.QtWidgets import QMessageBox

    shown: list[tuple] = []
    monkeypatch.setattr('gui.fitting_session.QMessageBox.warning', lambda *args: shown.append(args))
    monkeypatch.setattr('gui.fitting_session.QMessageBox.question', lambda *args: QMessageBox.StandardButton.Yes)
    return shown


@pytest.fixture
def watchful_fit(monkeypatch):
    """Stand in for the fit with a run that only watches its cancel flag; returns the configs it was given."""
    from gui import workers

    configs: list[FitConfig] = []

    def run(ms, assay_cls, conditions, config, should_cancel=None, **kwargs):
        configs.append(config)
        while should_cancel is None or not should_cancel():
            time.sleep(0.005)
        raise FitCancelled('The fit was cancelled.')

    monkeypatch.setattr(workers, 'fit_measurement_set', run)
    return configs


@pytest.fixture
def watchful_sensitivity(monkeypatch):
    """Stand in for the analysis with a run that only watches its cancel flag."""
    from gui import workers

    def run(*args, progress, should_cancel, **kwargs):
        while not should_cancel():
            time.sleep(0.005)
        raise FitCancelled('The analysis was cancelled before its baseline fit.')

    monkeypatch.setattr(workers, 'run_sensitivity', run)


def _state_an_uncertainty(session, spec: InputSpec | None = None) -> None:
    """State an uncertainty on the host concentration, which the analysis needs to have anything to vary.

    Every row opens fixed, so without this the analysis is refused before a
    worker is ever started.
    """
    session._input_panel._rows['h0'].set_spec(spec or InputSpec.sigma_pct(5.0))


def _state_dilution(session, stock: float, contains: tuple[str, ...] = ()) -> None:
    """Say on the panel that the additions dilute the sample, from a stock of *stock* M.

    The stock is set first and the choice last, so the session sees one
    finished edit with the whole answer in it, as it does when a user picks
    the entry and then fills the field.
    """
    panel = session._assay_panel
    panel._stock_widget.setValue(stock)
    for key, box in panel._contains_boxes.items():
        box.setChecked(key in contains)
    panel._dilution_combo.setCurrentIndex(1)


def _state_shared_source(session, source: SharedSource) -> None:
    """State *source* on the Input Uncertainty panel, as adding a row and filling it in does."""
    session._input_panel._add_shared_row(source)
    session._input_panel.specs_changed.emit()


def _session(dialogs):
    """A session on the bundled IDA dataset, ready to fit and to analyse."""
    from gui.fitting_session import FittingSession

    session = FittingSession()
    session._assay_panel.set_assay_type(AssayType.IDA)
    session._fit_panel.set_config(FitConfig(per_replica=False))
    session.model.load_files([str(_IDA_DATA)])
    _state_an_uncertainty(session)
    return session


def _window(monkeypatch):
    """A main window with the startup update check switched off."""
    from gui.main_window import FittingMainWindow

    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    return FittingMainWindow()


def _load(session) -> None:
    session._assay_panel.set_assay_type(AssayType.IDA)
    session.model.load_files([str(_IDA_DATA)])
    _state_an_uncertainty(session)


def test_closing_a_session_mid_fit_stops_the_fit_and_leaves_no_thread_running(qapp, monkeypatch, dialogs, watchful_fit):
    window = _window(monkeypatch)
    window._new_session()
    session = window.active_session()
    _load(session)
    session.run_fit()
    worker = session.model._fit_worker
    _wait_until(qapp, lambda: worker.isRunning() and watchful_fit)

    window._close_session(session)

    assert worker.cancelled  # the fit was told to stop, not merely dropped
    assert not worker.isRunning()  # and the session waited for it
    assert session.findChildren(QThread) == [] or all(not t.isRunning() for t in session.findChildren(QThread))


def test_closing_a_session_mid_sensitivity_stops_the_run_and_its_worker_processes(
    qapp, monkeypatch, dialogs, watchful_sensitivity
):
    import multiprocessing

    window = _window(monkeypatch)
    window._new_session()
    session = window.active_session()
    _load(session)
    session.run_sensitivity()
    worker = session.model._sensitivity_worker
    _wait_until(qapp, worker.isRunning)

    window._close_session(session)

    assert worker.cancelled
    assert not worker.isRunning()
    # The analysis owns its process pool and shuts it down as it returns, so a
    # run that has ended leaves no worker process behind.
    assert multiprocessing.active_children() == []
    assert dialogs == []


def test_closing_a_session_mid_run_takes_its_work_off_the_status_bar(qapp, monkeypatch, dialogs, watchful_sensitivity):
    """The status bar lists every running session: a closed one left standing reads as a run still going."""
    window = _window(monkeypatch)
    window._new_session()
    session = window.active_session()
    _load(session)
    session.run_sensitivity()
    _wait_until(qapp, session.model._sensitivity_worker.isRunning)
    session.model._on_sensitivity_progress(12207, 16393)
    name = session.model.name()
    assert f'{name} Sensitivity 74' in window._status._full_text

    window._close_session(session)
    _settle(qapp)

    assert name not in window._status._full_text
    assert window._status._full_text.startswith('Ready')


def test_closing_the_last_session_leaves_an_empty_new_session(qapp, monkeypatch, dialogs):
    window = _window(monkeypatch)
    (only,) = window.sessions()
    _load(only)

    window._close_session(only)

    (fresh,) = window.sessions()
    assert fresh is not only and fresh is window.active_session()
    assert fresh.model.name() == 'New session' and fresh.model.measurement_set is None


def test_closing_the_window_stops_the_work_in_every_session(qapp, monkeypatch, dialogs, watchful_fit):
    window = _window(monkeypatch)
    first = window.active_session()
    _load(first)
    window._new_session()
    second = window.active_session()
    _load(second)
    first.run_fit()
    second.run_fit()
    workers = [first.model._fit_worker, second.model._fit_worker]
    _wait_until(qapp, lambda: all(worker.isRunning() for worker in workers))

    window.close()

    assert all(worker.cancelled and not worker.isRunning() for worker in workers)


def test_a_worker_whose_thread_ends_as_the_wait_runs_out_is_let_go_of(qapp):
    """``finished`` has already been emitted then, and is never emitted again.

    A worker left waiting for it would be held for the life of the process,
    with the data its run copied, and its object never deleted.
    """
    from gui import workers

    class _EndedAsItTimedOut(QThread):
        """A thread that has ended although its wait reports a timeout — the window this closes."""

        def run(self) -> None:
            return

        def wait(self, msecs=None) -> bool:  # type: ignore[override]
            return False

    worker = _EndedAsItTimedOut()
    worker.start()
    _wait_until(qapp, worker.isFinished)

    workers.retire(worker)

    assert worker not in workers._RUNNING_ON
    _settle(qapp)
    with pytest.raises(RuntimeError):
        worker.isRunning()  # its object is gone


def test_every_run_is_asked_to_stop_before_any_of_them_is_waited_for(qapp, monkeypatch, dialogs, watchful_fit):
    """Each run ends at its next cancel check, so asking them all first lets their stopping overlap.

    Waiting for one run before asking the next to stop adds their stopping
    times up on the interface thread, and the window stops repainting for as
    long as that takes.
    """
    from gui import session_model, workers

    def watchful_profile(*args, should_cancel=None, **kwargs):
        while should_cancel is None or not should_cancel():
            time.sleep(0.005)
        raise FitCancelled('The Ka profile was stopped.')

    monkeypatch.setattr(workers, 'fit_profile', watchful_profile)
    window = _window(monkeypatch)
    first = window.active_session()
    _load(first)
    window._new_session()
    second = window.active_session()
    _load(second)
    first.run_fit()
    second.run_fit()
    profile = workers.ProfileWorker(
        first.model.measurement_set,
        first._assay_panel.get_assay_class(),
        first._assay_panel.current_conditions(),
        first._fit_panel.current_config(),
        parent=first,
    )
    first.model._profile_worker = profile
    profile.start()
    running = [first.model._fit_worker, profile, second.model._fit_worker]
    _wait_until(qapp, lambda: all(worker.isRunning() for worker in running))

    asked: list[list[bool]] = []
    real_retire = session_model.retire
    monkeypatch.setattr(
        session_model, 'retire', lambda worker: (asked.append([w.cancelled for w in running]), real_retire(worker))
    )
    window.close()

    assert asked[0] == [True, True, True]  # every run had been asked to stop before the first wait
    assert all(not worker.isRunning() for worker in running)


def test_loading_other_data_stops_the_running_fit_instead_of_abandoning_it(qapp, dialogs, watchful_fit):
    session = _session(dialogs)
    session.run_fit()
    worker = session.model._fit_worker
    _wait_until(qapp, worker.isRunning)

    session.model.load_files([str(_IDA_DATA)])

    assert worker.cancelled and not worker.isRunning()
    assert not session.model.fit_running()
    assert session.findChildren(QThread) == [] or all(not t.isRunning() for t in session.findChildren(QThread))
    session.model.shutdown()


def test_stopping_a_fit_leaves_the_session_as_it_was_and_lets_the_next_fit_start(qapp, dialogs, monkeypatch):
    """A cancelled fit reports nothing: the result already on the tab stands, and a new fit starts straight away."""
    from gui import workers

    session = _session(dialogs)
    session._input_panel.set_specs({})  # every input exact, so this first fit is the quick one
    session.run_fit()
    _wait_until(qapp, lambda: session.model.fit_results)
    _wait_until(qapp, lambda: session._identifiability_widget._profile is not None)
    shown = [result.id for result in session.model.fit_results]
    profile = session._identifiability_widget._profile

    def watchful(ms, assay_cls, conditions, config, should_cancel=None, **kwargs):
        while should_cancel is None or not should_cancel():
            time.sleep(0.005)
        raise FitCancelled('The fit was cancelled.')

    monkeypatch.setattr(workers, 'fit_measurement_set', watchful)
    session.run_fit()
    worker = session.model._fit_worker
    _wait_until(qapp, worker.isRunning)
    said: list[str] = []
    session.model.status_changed.connect(said.append)

    session.model.cancel_fit()

    assert worker.cancelled and not worker.isRunning()  # asked to stop, and its thread seen out
    assert not session.model.fit_running()
    assert said[-1].startswith('Fit stopped')
    assert dialogs == []  # a cancel the user asked for is not a failure to warn about
    assert [result.id for result in session.model.fit_results] == shown
    assert session._identifiability_widget._profile is profile

    session.run_fit()  # the next fit starts at once, with nothing left to wait for

    assert session.model.fit_running() and dialogs == []
    session.model.shutdown()
    _settle(qapp)
    with pytest.raises(RuntimeError):
        worker.isRunning()  # the cancelled fit's worker was retired, not left for the tab to destroy


def test_the_primary_action_stops_the_running_fit_and_follows_the_session_on_screen(
    qapp, monkeypatch, dialogs, watchful_fit
):
    """The toolbar's primary action belongs to the session on screen: it runs that session's fit, and stops it."""
    window = _window(monkeypatch)
    running = window.active_session()
    _load(running)
    running.run_fit()
    worker = running.model._fit_worker
    _wait_until(qapp, worker.isRunning)

    assert window._act_run.text() == 'Stop' and window._act_run.isEnabled()

    window._new_session()  # an idle session: the fit of another one is not offered here

    assert window._act_run.text() == 'Run fit'
    assert window._status._full_text == f'{running.model.name()} fitting'

    window._switch_to(running)

    assert window._act_run.text() == 'Stop'

    window._act_run.trigger()
    _wait_until(qapp, lambda: not running.model.running())

    assert worker.cancelled and not running.model.fit_running()
    assert window._act_run.text() == 'Run fit' and window._act_run.isEnabled()
    assert dialogs == []
    window.close()


def test_the_primary_action_runs_the_analysis_in_sensitivity(qapp, monkeypatch, dialogs, watchful_sensitivity):
    window = _window(monkeypatch)
    session = window.active_session()
    _load(session)
    window.show_view('Sensitivity')
    assert window._act_run.text() == 'Run analysis'

    window._act_run.trigger()

    assert session.model.sensitivity_running() and not session.model.fit_running()
    window.close()


def test_the_demo_states_typical_input_uncertainties_and_says_so(qapp, dialogs, watchful_fit):
    """Demo IDA runs from its own settings whatever the session held, and its first fit shows an input-aware interval."""
    from core.pipeline.inputs import TITRANT

    session = _session(dialogs)
    _state_shared_source(session, SharedSource('Host and dye stock', 4.0, ('h0', 'd0')))
    session._bounds_panel._rows['Ka_guest']._hi.setText('1e9')
    messages: list[str] = []
    session.model.status_changed.connect(messages.append)

    session.load_demo_ida()

    stated = ErrorModel(
        specs={
            'Ka_dye': InputSpec.sigma_pct(10.0),
            'h0': InputSpec.sigma_pct(3.0),
            'd0': InputSpec.sigma_pct(3.0),
            TITRANT: InputSpec.sigma_pct(3.0),
        }
    )
    assert session._input_panel.current_errors() == stated
    assert session._bounds_panel.current_bounds() is None
    assert session.model.fit_running()
    assert session.model._fit_worker.config.errors == stated
    assert messages[-1].startswith('Demo settings: ')
    assert 'σ 10 %' in messages[-1] and 'σ 3 %' in messages[-1]
    assert messages[-1].endswith('— fitting…')
    session.model.shutdown()


def test_the_analysis_is_refused_while_a_bound_cannot_be_used(qapp, dialogs, watchful_sensitivity):
    """The fit refuses such a bound; the analysis refuses it too rather than searching the default there."""
    session = _session(dialogs)
    session._bounds_panel._rows['Ka_guest']._lo.setText('abc')

    session.run_sensitivity()

    assert not session.model.sensitivity_running()
    assert dialogs[-1][1] == 'Parameter Bounds'
    assert dialogs[-1][2] == (
        'The analysis cannot start:\n\n• Ka(G): the lower bound “abc” is not a number. Enter a number, such as 1e3.'
    )


def test_a_fit_and_an_analysis_never_run_at_the_same_time(qapp, dialogs, watchful_fit, watchful_sensitivity):
    session = _session(dialogs)
    session.run_sensitivity()
    _wait_until(qapp, session.model._sensitivity_worker.isRunning)

    session.run_fit()

    assert not session.model.fit_running()
    assert dialogs[-1][1] == 'Already Running'
    assert 'sensitivity analysis is running' in dialogs[-1][2]
    session.model.cancel_sensitivity()
    _wait_until(qapp, lambda: not session.model.sensitivity_running())

    session.run_fit()
    _wait_until(qapp, session.model._fit_worker.isRunning)
    session.run_sensitivity()

    assert not session.model.sensitivity_running()
    assert 'fit is running' in dialogs[-1][2]
    session.model.shutdown()


def test_a_finished_fit_leaves_neither_its_worker_nor_its_profile_worker_behind(qapp, dialogs):
    """The fit and the Ka profile it starts are deleted once they end, not kept until the tab closes."""
    session = _session(dialogs)

    session.run_fit()
    fit_worker = session.model._fit_worker
    _wait_until(qapp, lambda: session.model._profile_worker is not None)
    profile_worker = session.model._profile_worker
    _wait_until(qapp, lambda: session._identifiability_widget._profile is not None)
    _settle(qapp)

    assert dialogs == []
    assert not session.model.fit_running()
    assert session.model._profile_worker is None
    for worker in (fit_worker, profile_worker):
        with pytest.raises(RuntimeError):
            worker.isRunning()  # its object is gone: nothing is kept for the session's lifetime


def test_a_second_fit_does_not_leave_the_first_fits_profile_running(qapp, dialogs, monkeypatch):
    """A profile left behind is a running thread nothing can reach, and the tab closing destroys it."""
    from gui import workers

    started: list[workers.ProfileWorker] = []

    def watch(self):
        started.append(self)
        while not self._cancelled:
            time.sleep(0.005)

    monkeypatch.setattr(workers.ProfileWorker, 'run', watch)
    session = _session(dialogs)

    session.run_fit()
    _wait_until(qapp, lambda: len(started) == 1)
    first = started[0]
    session.run_fit()
    _wait_until(qapp, lambda: len(started) == 2)

    assert first.cancelled and not first.isRunning()  # stopped when the fit it described was replaced
    assert session.model._profile_worker is started[1]
    session.model.shutdown()
    _settle(qapp)

    assert dialogs == []
    with pytest.raises(RuntimeError):
        first.isRunning()  # its object is gone, so closing the tab cannot destroy a running thread


def test_a_fit_that_fails_leaves_no_worker_behind(qapp, dialogs, monkeypatch):
    """A failed fit drops its worker like a finished one: they would otherwise pile up for the tab's lifetime."""
    from gui import workers

    def boom(*args, **kwargs):
        raise RuntimeError('synthetic fit failure')

    monkeypatch.setattr(workers, 'fit_measurement_set', boom)
    session = _session(dialogs)

    session.run_fit()
    worker = session.model._fit_worker
    _wait_until(qapp, lambda: not session.model.fit_running())
    _settle(qapp)

    assert dialogs[-1][1] == 'Fit Error'
    with pytest.raises(RuntimeError):
        worker.isRunning()


def test_a_second_analysis_is_refused_while_one_is_running(qapp, dialogs, watchful_sensitivity):
    """The session enforces one analysis at a time itself; a second would orphan the first with its worker pool."""
    session = _session(dialogs)
    session.run_sensitivity()
    _wait_until(qapp, session.model._sensitivity_worker.isRunning)
    first = session.model._sensitivity_worker

    session.run_sensitivity()

    assert session.model._sensitivity_worker is first
    assert dialogs[-1][1] == 'Already Running'
    assert 'sensitivity analysis is already running' in dialogs[-1][2]
    session.model.shutdown()


def test_loading_data_says_that_it_stopped_the_running_fit(qapp, dialogs, watchful_fit):
    """Minutes of work must not end without a word — the no-silent-fallbacks rule."""
    session = _session(dialogs)
    messages: list[str] = []
    session.model.status_changed.connect(messages.append)

    session.run_fit()
    _wait_until(qapp, lambda: len(watchful_fit) == 1)
    _load(session)

    assert messages[-1].startswith('Loaded:')
    assert messages[-1].endswith('the running fit was stopped')
    session.model.shutdown()


def test_the_analysis_is_told_what_the_panel_calls_each_input(qapp, monkeypatch, dialogs):
    """So a problem the analysis reports names an input the way the sidebar does."""
    from gui import workers

    seen: list[dict] = []
    run = _fake_run(2)

    def record(*args, **kwargs):
        seen.append(kwargs.get('input_labels'))
        return run(*args, **kwargs)

    monkeypatch.setattr(workers, 'run_sensitivity', record)
    session = _session(dialogs)

    session.run_sensitivity()
    _wait_until(qapp, lambda: session.model.sensitivity_result is not None)

    assert seen == [session._input_panel.input_labels()]
    assert seen[0], 'the panel names every input it offers'


def test_the_fit_is_given_the_uncertainties_stated_in_the_panel(qapp, dialogs, watchful_fit):
    """The interval the fit reports covers these, so the fit has to be told exactly what the panel holds."""
    session = _session(dialogs)
    session._input_panel._rows['d0'].set_spec(InputSpec.interval_pct(-6.0, 6.0))

    session.run_fit()
    _wait_until(qapp, session.model._fit_worker.isRunning)
    _wait_until(qapp, lambda: bool(watchful_fit))
    session.model.shutdown()

    (config,) = watchful_fit
    assert config.errors == ErrorModel(specs={'h0': InputSpec.sigma_pct(5.0), 'd0': InputSpec.interval_pct(-6.0, 6.0)})
    # A refusal has to name an input the way the sidebar names it.
    assert config.input_labels == session._input_panel.input_labels()
    assert dialogs == []


def test_the_fit_is_refused_while_an_uncertainty_cannot_be_used_as_set(qapp, dialogs, watchful_fit):
    """A range down to zero leaves the model nothing to fit: the fit says so and starts nothing."""
    session = _session(dialogs)
    _state_an_uncertainty(session, InputSpec.interval_pct(-100.0, 5.0))

    session.run_fit()

    assert not session.model.fit_running()
    assert watchful_fit == []
    assert dialogs[-1][1] == 'Input Uncertainty'
    assert 'would be taken down to zero' in dialogs[-1][2]
    assert '[Host]₀' in dialogs[-1][2]


def test_a_session_that_states_nothing_fits_exactly_as_the_core_does(qapp, dialogs):
    """With no titrant stock and no shared source, the session must ask the engine exactly what it asked before.

    The run goes through the session: its panels, its worker and the data as
    the session loaded them. What comes back is compared with a direct call
    to the pipeline on the same data, number for number.
    """
    from copy import deepcopy

    from core.assays.ida import IDAAssay
    from core.pipeline.fit_pipeline import fit_measurement_set
    from gui.fitting_session import FittingSession

    session = FittingSession()
    session._assay_panel.set_assay_type(AssayType.IDA)
    session._fit_panel.set_config(FitConfig(per_replica=False))
    session.model.load_files([str(_IDA_DATA)])
    ms = session.model.measurement_set
    conditions = session._assay_panel.current_conditions()
    assert 'titrant_stock' not in conditions and 'stock_contains' not in conditions

    session.run_fit()
    _wait_until(qapp, lambda: session.model.fit_results)
    (ours,) = session.model.fit_results
    session.model.shutdown()

    theirs = fit_measurement_set(deepcopy(ms), IDAAssay, conditions, FitConfig(per_replica=False))

    assert {key: float(value.magnitude) for key, value in ours.parameters.items()} == {
        key: float(value.magnitude) for key, value in theirs.parameters.items()
    }
    assert ours.intervals and ours.intervals == theirs.intervals
    assert dialogs == []


def test_the_fit_is_refused_until_the_titrant_stock_is_entered(qapp, dialogs, watchful_fit):
    """Choosing dilution without a stock says nothing about how much each addition dilutes."""
    session = _session(dialogs)
    _state_dilution(session, 0.0)

    session.run_fit()

    assert not session.model.fit_running()
    assert watchful_fit == []
    assert dialogs[-1][1] == 'Assay Configuration'
    assert "Enter the titrant stock concentration, or choose 'stay constant'." in dialogs[-1][2]


def test_the_fit_is_refused_while_the_titrant_stock_is_below_the_data(qapp, dialogs, watchful_fit):
    """A sample cannot hold more titrant than the stock it was made from, and the note gives both numbers."""
    session = _session(dialogs)
    highest = float(session.model.measurement_set.concentrations.max())
    _state_dilution(session, highest / 2)

    session.run_fit()

    assert not session.model.fit_running()
    assert watchful_fit == []
    assert dialogs[-1][1] == 'Assay Configuration'
    message = dialogs[-1][2]
    panel = session._assay_panel
    assert panel.format_condition('titrant_stock', Q_(highest / 2, 'M')) in message
    assert panel.format_condition('titrant_stock', Q_(highest, 'M')) in message
    assert 'Check the stock concentration and its unit.' in message


def test_the_analysis_is_refused_while_a_shared_source_applies_to_one_input(qapp, dialogs):
    """A source one input has alone is that input's own uncertainty, and the message says where to put it."""
    session = _session(dialogs)
    _state_shared_source(session, SharedSource('Host stock', 4.0, ('h0',)))

    session.run_sensitivity()

    assert not session.model.sensitivity_running()
    assert dialogs[-1][1] == 'Input Uncertainty'
    assert "'Host stock' applies to one" in dialogs[-1][2]
    assert 'tick a second input' in dialogs[-1][2]


def test_the_fit_is_given_the_dilution_and_the_sources_the_panels_state(qapp, dialogs, watchful_fit):
    """Both reach the engine as stated: the stock is part of the assay, the shared source part of the model."""
    session = _session(dialogs)
    _state_dilution(session, 1e-3, contains=('d0',))
    _state_shared_source(session, SharedSource('Host and dye stock', 4.0, ('h0', 'd0')))

    session.run_fit()
    _wait_until(qapp, session.model._fit_worker.isRunning)
    _wait_until(qapp, lambda: bool(watchful_fit))
    conditions = session.model._fit_worker.conditions
    session.model.shutdown()

    assert float(conditions['titrant_stock'].to('M').magnitude) == 1e-3
    assert conditions['stock_contains'] == ('d0',)
    (config,) = watchful_fit
    assert config.errors.shared == (SharedSource('Host and dye stock', 4.0, ('h0', 'd0')),)
    assert dialogs == []


def test_the_analysis_varies_the_inputs_the_shared_panel_states(qapp, monkeypatch, dialogs):
    """One panel states the uncertainties; the analysis draws from those, not from a set of its own."""
    from gui import workers

    seen: list = []
    run = _fake_run(2)

    def record(ms, assay_cls, conditions, fit_config, sens_config, **kwargs):
        seen.append((fit_config, sens_config))
        return run(ms, assay_cls, conditions, fit_config, sens_config, **kwargs)

    monkeypatch.setattr(workers, 'run_sensitivity', record)
    session = _session(dialogs)
    session._input_panel._rows['Ka_dye'].set_spec(InputSpec.sigma_pct(2.0))

    session.run_sensitivity()
    _wait_until(qapp, lambda: session.model.sensitivity_result is not None)

    (fit_config, sens_config) = seen[0]
    assert sens_config.errors == session._input_panel.current_errors()
    assert set(sens_config.errors.specs) == {'h0', 'Ka_dye'}  # the rows left fixed are not drawn
    # The analysis perturbs the inputs itself, so every one of its fits takes them as given.
    assert fit_config.errors == ErrorModel()
    assert dialogs == []


def test_the_uncertainty_rows_are_locked_while_a_run_reads_them(qapp, dialogs, watchful_fit):
    """A run is reported against the uncertainties it was given, so they cannot be edited under it."""
    session = _session(dialogs)
    row = session._input_panel._rows['h0']
    assert row.isEnabled()

    session.run_fit()
    _wait_until(qapp, session.model._fit_worker.isRunning)

    assert not row.isEnabled()

    session.model.shutdown()

    assert row.isEnabled()


def test_the_analysis_is_refused_while_every_input_is_fixed(qapp, dialogs):
    """With nothing to vary there is no spread to split, and the message says where to state one."""
    session = _session(dialogs)
    session._input_panel._rows['h0'].set_spec(None)

    session.run_sensitivity()

    assert not session.model.sensitivity_running()
    assert dialogs[-1][1] == 'Sensitivity Analysis'
    assert 'Every input is set to fixed under Input Uncertainty' in dialogs[-1][2]


def test_a_finished_analysis_leaves_no_worker_behind(qapp, monkeypatch, dialogs):
    from gui import workers

    monkeypatch.setattr(workers, 'run_sensitivity', _fake_run(3))
    session = _session(dialogs)

    session.run_sensitivity()
    worker = session.model._sensitivity_worker
    _wait_until(qapp, lambda: session.model.sensitivity_result is not None)
    _settle(qapp)

    assert not session.model.sensitivity_running()
    with pytest.raises(RuntimeError):
        worker.isRunning()


def _deliver_sensitivity(session):
    """Hand *session* a Sobol' run, with the uncertainties it was drawn from stated on the panel.

    The panel is what a held run is checked against, so a run delivered here
    states its own specs on it, as the analysis the user starts does.
    """
    run = _made_on(_sobol_result(), session.model.measurement_set, session._assay_panel.current_conditions())
    for key, spec in run.config.errors.specs.items():
        session._input_panel._rows[key].set_spec(spec)
    session.model._on_sensitivity_complete(run)
    return run


def test_save_plot_saves_the_plot_of_the_view(qapp, monkeypatch, dialogs, tmp_path):
    saved: list[tuple[str, str]] = []
    session = _session(dialogs)
    _deliver_sensitivity(session)
    monkeypatch.setattr(
        'gui.fitting_session.QFileDialog.getSaveFileName',
        lambda *args, **kwargs: (str(tmp_path / 'out.png'), ''),
    )
    monkeypatch.setattr(type(session._plot_widget), 'export_image', lambda self, path: saved.append(('fit', path)))
    monkeypatch.setattr(
        type(session._sensitivity_widget), 'export_image', lambda self, path: saved.append(('sensitivity', path))
    )

    session.export_plot('Sensitivity')
    session.export_plot('Fit results')

    assert [where for where, _path in saved] == ['sensitivity', 'fit']
    assert dialogs == []


def test_the_save_plot_dialog_offers_only_what_the_view_can_write(qapp, monkeypatch, dialogs):
    """A view saved whole as one picture offers PNG alone; the titration plot still offers a drawing.

    Offering SVG where the view cannot write it sends the user to a message box
    instead of a file.
    """
    asked: list[tuple[str, str]] = []
    session = _session(dialogs)
    _deliver_sensitivity(session)
    monkeypatch.setattr(type(session._identifiability_widget), 'has_chart', lambda self: True)
    monkeypatch.setattr(
        'gui.fitting_session.QFileDialog.getSaveFileName',
        lambda _parent, _title, name, filters: asked.append((name, filters)) or ('', ''),
    )

    for view in ('Fit results', 'Ka confidence', 'Sensitivity'):
        session.export_plot(view)

    assert [filters for _name, filters in asked] == [
        'PNG image (*.png);;SVG vector (*.svg)',
        'PNG image (*.png)',
        'PNG image (*.png)',
    ]
    assert [name.endswith('.png') for name, _filters in asked] == [True, True, True]
    assert dialogs == []


def test_save_plot_says_what_the_view_has_to_save(qapp, dialogs):
    from gui.fitting_session import FittingSession

    session = FittingSession()

    assert session.plot_export_note('Ka confidence') == (
        'There is no Ka confidence chart to save yet. Run a fit, then save it.'
    )
    assert session.plot_export_note('Sensitivity') == (
        'There is no sensitivity analysis to save yet. Run one, then save it.'
    )
    assert session.plot_export_note('Fit results').startswith('There is no titration plot yet.')
    assert session.plot_export_note('Binding model').startswith('This view has no plot to save.')

    session.export_plot('Fit results')
    assert dialogs[-1][1] == 'Save Plot'


def test_save_plot_follows_the_ka_confidence_chart_not_the_held_fit(qapp, dialogs):
    """Importing results holds a fit but clears Ka confidence, and Save Plot must not offer an empty page."""
    from gui.fitting_session import FittingSession
    from gui.session import build_artefacts

    session = FittingSession()
    session.model.show_imported([_sobol_result().baseline_fit], 'results.json')

    assert not session._identifiability_widget.has_chart()
    assert session.plot_export_note('Ka confidence') == (
        'There is no Ka confidence chart to save yet. Run a fit, then save it.'
    )
    (artefact,) = [a for a in build_artefacts(session) if a.key == 'identifiability_png']
    assert not artefact.available


def test_the_refusal_names_one_number_where_the_stock_reads_as_the_highest_point(qapp, dialogs, watchful_fit):
    """A stock equal to the highest point would otherwise read as having to be more concentrated than itself."""
    session = _session(dialogs)
    highest = float(session.model.measurement_set.concentrations.max())
    _state_dilution(session, highest)

    session.run_fit()

    assert not session.model.fit_running()
    message = dialogs[-1][2]
    shown = session._assay_panel.format_condition('titrant_stock', Q_(highest, 'M'))
    assert message.count(shown) == 1
    assert 'The titrant stock is no more concentrated than the highest titrant concentration' in message
    assert 'Check the stock concentration and its unit.' in message


def test_the_status_bar_says_a_constant_on_an_end_of_its_search_box_is_not_limited_there():
    """An estimate at the box is the box, not a measurement; a clean "Fit complete" would report it as one."""
    from gui.session_model import _open_note, _verdict_note
    from tests.unit.test_fit_results import _sample_fit_result

    fitted = _sample_fit_result()
    assert _open_note(fitted) == ''
    at_floor = _sample_fit_result(parameters={**fitted.parameters, 'Ka_guest': Q_(1e-8, '1/M')})
    assert _open_note(at_floor) == 'Ka(G) not limited below by the data'
    # A fit with no diagnostics has no verdict to report.
    assert _verdict_note(fitted) == ''
