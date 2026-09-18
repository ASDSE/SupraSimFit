"""Closing a tab or the window stops the work the session started.

Destroying a running ``QThread`` aborts the process, and a sensitivity run left
going holds its worker processes, so a session cancels its fit, its Ka profile
and its sensitivity run, waits for each thread and deletes each worker before
its widgets go. The long runs are stood in for by functions that do nothing but
watch their cancel flag: what these tests pin is the stopping, not the science.

One analysis at a time is checked here too.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

pytest.importorskip('PyQt6')

from PyQt6.QtCore import QEvent, QThread  # noqa: E402

from core.assays.registry import AssayType  # noqa: E402
from core.pipeline.fit_pipeline import FitConfig  # noqa: E402
from core.pipeline.varpro import FitCancelled  # noqa: E402
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


def _session(dialogs):
    """A session on the bundled IDA dataset, ready to fit and to analyse."""
    from gui.fitting_session import FittingSession

    session = FittingSession()
    session._assay_panel.set_assay_type(AssayType.IDA)
    session._fit_panel.set_config(FitConfig(per_replica=False))
    session._data_panel.load_file(str(_IDA_DATA))
    return session


def _window(monkeypatch):
    """A main window with the startup update check switched off."""
    from gui.main_window import FittingMainWindow

    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    return FittingMainWindow()


def _load(session) -> None:
    session._assay_panel.set_assay_type(AssayType.IDA)
    session._data_panel.load_file(str(_IDA_DATA))


def test_closing_a_tab_mid_fit_stops_the_fit_and_leaves_no_thread_running(qapp, monkeypatch, dialogs, watchful_fit):
    window = _window(monkeypatch)
    window._new_session()
    session = window.active_session()
    _load(session)
    session.run_fit()
    worker = session._fit_worker
    _wait_until(qapp, lambda: worker.isRunning() and watchful_fit)

    window._close_tab(window._tabs.indexOf(session))

    assert worker.cancelled  # the fit was told to stop, not merely dropped
    assert not worker.isRunning()  # and the tab waited for it
    assert session.findChildren(QThread) == [] or all(not t.isRunning() for t in session.findChildren(QThread))


def test_closing_a_tab_mid_sensitivity_stops_the_run_and_its_worker_processes(
    qapp, monkeypatch, dialogs, watchful_sensitivity
):
    import multiprocessing

    window = _window(monkeypatch)
    window._new_session()
    session = window.active_session()
    _load(session)
    session.run_sensitivity()
    worker = session._sensitivity_worker
    _wait_until(qapp, worker.isRunning)

    window._close_tab(window._tabs.indexOf(session))

    assert worker.cancelled
    assert not worker.isRunning()
    # The analysis owns its process pool and shuts it down as it returns, so a
    # run that has ended leaves no worker process behind.
    assert multiprocessing.active_children() == []
    assert dialogs == []


def test_closing_the_window_stops_the_work_in_every_session(qapp, monkeypatch, dialogs, watchful_fit):
    window = _window(monkeypatch)
    first = window.active_session()
    _load(first)
    window._new_session()
    second = window.active_session()
    _load(second)
    first.run_fit()
    second.run_fit()
    workers = [first._fit_worker, second._fit_worker]
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
    from gui import fitting_session, workers

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
        first._state.measurement_set,
        first._assay_panel.get_assay_class(),
        first._assay_panel.current_conditions(),
        first._fit_panel.current_config(),
        parent=first,
    )
    first._profile_worker = profile
    profile.start()
    running = [first._fit_worker, profile, second._fit_worker]
    _wait_until(qapp, lambda: all(worker.isRunning() for worker in running))

    asked: list[list[bool]] = []
    real_retire = fitting_session.retire
    monkeypatch.setattr(
        fitting_session, 'retire', lambda worker: (asked.append([w.cancelled for w in running]), real_retire(worker))
    )
    window.close()

    assert asked[0] == [True, True, True]  # every run had been asked to stop before the first wait
    assert all(not worker.isRunning() for worker in running)


def test_loading_other_data_stops_the_running_fit_instead_of_abandoning_it(qapp, dialogs, watchful_fit):
    session = _session(dialogs)
    session.run_fit()
    worker = session._fit_worker
    _wait_until(qapp, worker.isRunning)

    session._data_panel.load_file(str(_IDA_DATA))

    assert worker.cancelled and not worker.isRunning()
    assert not session.fit_running()
    assert session.findChildren(QThread) == [] or all(not t.isRunning() for t in session.findChildren(QThread))
    session.shutdown()


def test_a_fit_and_an_analysis_never_run_at_the_same_time(qapp, dialogs, watchful_fit, watchful_sensitivity):
    session = _session(dialogs)
    session.run_sensitivity()
    _wait_until(qapp, session._sensitivity_worker.isRunning)

    session.run_fit()

    assert not session.fit_running()
    assert dialogs[-1][1] == 'Already Running'
    assert 'sensitivity analysis is running' in dialogs[-1][2]
    session._cancel_sensitivity()
    _wait_until(qapp, lambda: not session.sensitivity_running())

    session.run_fit()
    _wait_until(qapp, session._fit_worker.isRunning)
    session.run_sensitivity()

    assert not session.sensitivity_running()
    assert 'fit is running' in dialogs[-1][2]
    session.shutdown()


def test_a_finished_fit_leaves_neither_its_worker_nor_its_profile_worker_behind(qapp, dialogs):
    """The fit and the Ka profile it starts are deleted once they end, not kept until the tab closes."""
    session = _session(dialogs)

    session.run_fit()
    fit_worker = session._fit_worker
    _wait_until(qapp, lambda: session._profile_worker is not None)
    profile_worker = session._profile_worker
    _wait_until(qapp, lambda: session._state.profile_result is not None)
    _settle(qapp)

    assert dialogs == []
    assert not session.fit_running()
    assert session._profile_worker is None
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
    assert session._profile_worker is started[1]
    session.shutdown()
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
    worker = session._fit_worker
    _wait_until(qapp, lambda: not session.fit_running())
    _settle(qapp)

    assert dialogs[-1][1] == 'Fit Error'
    with pytest.raises(RuntimeError):
        worker.isRunning()


def test_a_second_analysis_is_refused_while_one_is_running(qapp, dialogs, watchful_sensitivity):
    """The session enforces one analysis at a time itself; a second would orphan the first with its worker pool."""
    session = _session(dialogs)
    session.run_sensitivity()
    _wait_until(qapp, session._sensitivity_worker.isRunning)
    first = session._sensitivity_worker

    session.run_sensitivity()

    assert session._sensitivity_worker is first
    assert dialogs[-1][1] == 'Already Running'
    assert 'sensitivity analysis is already running' in dialogs[-1][2]
    session.shutdown()


def test_loading_data_says_that_it_stopped_the_running_fit(qapp, dialogs, watchful_fit):
    """Minutes of work must not end without a word — the no-silent-fallbacks rule."""
    session = _session(dialogs)
    messages: list[str] = []
    session.status_message.connect(messages.append)

    session.run_fit()
    _wait_until(qapp, lambda: len(watchful_fit) == 1)
    _load(session)

    assert messages[-1].startswith('Loaded:')
    assert messages[-1].endswith('the running fit was stopped')
    session.shutdown()


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
    _wait_until(qapp, lambda: session._state.sensitivity_result is not None)

    assert seen == [session._sensitivity_panel.input_labels()]
    assert seen[0], 'the panel names every input it offers'


def test_a_finished_analysis_leaves_no_worker_behind(qapp, monkeypatch, dialogs):
    from gui import workers

    monkeypatch.setattr(workers, 'run_sensitivity', _fake_run(3))
    session = _session(dialogs)

    session.run_sensitivity()
    worker = session._sensitivity_worker
    _wait_until(qapp, lambda: session._state.sensitivity_result is not None)
    _settle(qapp)

    assert not session.sensitivity_running()
    with pytest.raises(RuntimeError):
        worker.isRunning()


def test_save_plot_saves_the_tab_on_screen(qapp, monkeypatch, dialogs, tmp_path):
    saved: list[tuple[str, str]] = []
    session = _session(dialogs)
    ms = session._state.measurement_set
    session._on_sensitivity_complete(_made_on(_sobol_result(), ms, session._assay_panel.current_conditions()))
    monkeypatch.setattr(
        'gui.fitting_session.QFileDialog.getSaveFileName',
        lambda *args, **kwargs: (str(tmp_path / 'out.png'), ''),
    )
    monkeypatch.setattr(type(session._plot_widget), 'export_image', lambda self, path: saved.append(('fit', path)))
    monkeypatch.setattr(
        type(session._sensitivity_widget), 'export_image', lambda self, path: saved.append(('sensitivity', path))
    )

    session._plot_tabs.setCurrentWidget(session._sensitivity_widget)
    session.export_plot()
    session._plot_tabs.setCurrentWidget(session._plot_widget)
    session.export_plot()

    assert [where for where, _path in saved] == ['sensitivity', 'fit']
    assert dialogs == []


def test_the_save_plot_dialog_offers_only_what_the_tab_can_write(qapp, monkeypatch, dialogs):
    """A tab saved whole as one picture offers PNG alone; the Fit Curve tab still offers a drawing.

    Offering SVG where the tab cannot write it sends the user to a message box
    instead of a file.
    """
    asked: list[tuple[str, str]] = []
    session = _session(dialogs)
    ms = session._state.measurement_set
    session._on_sensitivity_complete(_made_on(_sobol_result(), ms, session._assay_panel.current_conditions()))
    monkeypatch.setattr(type(session._identifiability_widget), 'has_chart', lambda self: True)
    monkeypatch.setattr(
        'gui.fitting_session.QFileDialog.getSaveFileName',
        lambda _parent, _title, name, filters: asked.append((name, filters)) or ('', ''),
    )

    for widget in (session._plot_widget, session._identifiability_widget, session._sensitivity_widget):
        session._plot_tabs.setCurrentWidget(widget)
        session.export_plot()

    assert [filters for _name, filters in asked] == [
        'PNG image (*.png);;SVG vector (*.svg)',
        'PNG image (*.png)',
        'PNG image (*.png)',
    ]
    assert [name.endswith('.png') for name, _filters in asked] == [True, True, True]
    assert dialogs == []


def test_save_plot_says_what_the_tab_on_screen_has_to_save(qapp, dialogs):
    from gui.fitting_session import FittingSession

    session = FittingSession()

    session._plot_tabs.setCurrentWidget(session._identifiability_widget)
    assert session.plot_export_note() == 'There is no identifiability chart to save yet. Run a fit, then save it.'
    session._plot_tabs.setCurrentWidget(session._sensitivity_widget)
    assert session.plot_export_note() == 'There is no sensitivity analysis to save yet. Run one, then save it.'
    session._plot_tabs.setCurrentWidget(session._plot_widget)
    assert session.plot_export_note().startswith('There is nothing on the Fit Curve tab yet.')

    session.export_plot()
    assert dialogs[-1][1] == 'Save Plot'


def test_save_plot_follows_the_identifiability_tab_not_the_held_fit(qapp, dialogs):
    """Importing results holds a fit but clears that tab, and Save Plot must not offer an empty page."""
    from gui.fitting_session import FittingSession
    from gui.session import build_artefacts

    session = FittingSession()
    session._state.held_fit_results = [_sobol_result().baseline_fit]
    session._plot_tabs.setCurrentWidget(session._identifiability_widget)

    assert not session._identifiability_widget.has_chart()
    assert session.plot_export_note() == 'There is no identifiability chart to save yet. Run a fit, then save it.'
    (artefact,) = [a for a in build_artefacts(session) if a.key == 'identifiability_png']
    assert not artefact.available
