"""A fit is shown only while the loaded selection matches the record it was made on.

The session holds each result with its record: the replicates it used and was
given, its conditions, its assay type and a fingerprint of the data. A change
to the replicates, the conditions or the assay type that breaks the match hides
the result on every tab behind a note naming what changed, and disables picks
and result exports; undoing the change shows it again with identical numbers.
Imports are checked against the loaded data, and work still running never
reaches data it was not given.

The data hold two replicates that follow the IDA ground truth and one of pure
noise, which the per-replicate fit leaves out. One fit is made per module and
handed to each session the way the fit worker hands over its result.
"""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip('PyQt6')

from PyQt6.QtCore import Qt, QThread  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402

from core.assays.ida import IDAAssay  # noqa: E402
from core.assays.registry import AssayType  # noqa: E402
from core.data_processing.measurement_set import MeasurementSet  # noqa: E402
from core.io import load_measurements  # noqa: E402
from core.optimizer.filters import calculate_fit_metrics  # noqa: E402
from core.optimizer.multistart import FitCancelled  # noqa: E402
from core.pipeline.fit_pipeline import FitConfig, FitResult, PerReplicaFitError, fit_measurement_set  # noqa: E402
from core.units import Q_  # noqa: E402
from tests.conftest import GDA_IDA_RECOVERY_BOUNDS, IDA_TRUE, _make_ida_data  # noqa: E402
from tests.unit.gui.test_sensitivity_gui import _cell_texts, _made_on, _sobol_result  # noqa: E402

_CONDITIONS = {
    'Ka_dye': Q_(IDA_TRUE['Ka_dye'], '1/M'),
    'h0': Q_(IDA_TRUE['h0'], 'M'),
    'd0': Q_(IDA_TRUE['d0'], 'M'),
}
_KEYS = ('Ka_guest', 'I0', 'I_dye_free', 'I_dye_bound')


def _data() -> MeasurementSet:
    """'a' and 'b' carry 1% noise around the IDA ground truth; 'c' holds no titration curve."""
    rng = np.random.default_rng(0)
    x, y = _make_ida_data(IDA_TRUE, n_points=20)
    signals = np.vstack([y * (1 + 0.01 * rng.standard_normal(y.size)) for _ in range(3)])
    signals[2] = np.random.default_rng(1).normal(signals[2].mean(), signals[2].std(), signals[2].size)
    return MeasurementSet(concentrations=x, signals=signals, replica_ids=('a', 'b', 'c'))


@pytest.fixture(scope='module')
def fitted() -> FitResult:
    config = FitConfig(n_trials=8, per_replica=True, seed=11, custom_bounds=GDA_IDA_RECOVERY_BOUNDS)
    result = fit_measurement_set(_data(), IDAAssay, _CONDITIONS, config)
    assert result.metadata['replica_ids_fit'] == ['a', 'b']
    assert list(result.metadata['replica_failures']) == ['c']
    return result


@pytest.fixture
def fit(fitted) -> FitResult:
    """A fresh copy of the module's fit: picks change the result they are made on."""
    return copy.deepcopy(fitted)


@pytest.fixture(scope='module')
def average_fit() -> FitResult:
    """A fit of the average of every replicate, 'c' included, with a floor its noise lets it reach."""
    config = FitConfig(n_trials=6, per_replica=False, seed=11, min_r_squared=0.5, custom_bounds=GDA_IDA_RECOVERY_BOUNDS)
    result = fit_measurement_set(_data(), IDAAssay, _CONDITIONS, config)
    assert result.success and result.uncertainty_source == 'optimizer'
    assert result.metadata['active_replica_ids'] == ['a', 'b', 'c']
    return result


@pytest.fixture
def dialogs(monkeypatch):
    """Record warning and information dialogs instead of blocking on them."""
    shown: dict[str, list] = {'warning': [], 'information': []}
    for kind in shown:
        monkeypatch.setattr(
            f'gui.fitting_session.QMessageBox.{kind}', lambda *args, kind=kind: shown[kind].append(args)
        )
    return shown


@pytest.fixture
def make_session(qapp):
    """Build IDA sessions with the fit's conditions entered; on teardown wait for their worker threads."""
    from gui.fitting_session import FittingSession

    sessions = []

    def build(ms: MeasurementSet | None = None):
        session = FittingSession()
        session._assay_panel.set_assay_type(AssayType.IDA)
        for key, value in _CONDITIONS.items():
            session._assay_panel._field_widgets[key].setValue(value.magnitude)
        if ms is not None:
            session._data_panel.data_loaded.emit(ms)
        sessions.append(session)
        return session

    yield build
    for session in sessions:
        for thread in session.findChildren(QThread):
            thread.wait()
    qapp.processEvents()


def _wait_until(qapp, condition, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, 'timed out waiting'
        qapp.processEvents()
        time.sleep(0.01)


def _deliver(session, result: FitResult) -> None:
    """Hand *result* to *session* as the fit worker started by Run Fit does."""
    from gui.workers import FitWorker

    ms = session._state.measurement_set
    conditions = session._assay_panel.current_conditions()
    worker = FitWorker(copy.deepcopy(ms), IDAAssay, conditions, FitConfig(), parent=session)
    worker.finished.connect(session._on_fit_complete)
    worker.error.connect(session._on_fit_error)
    session._fit_worker = worker
    worker.finished.emit(result)


def _shown_session(qapp, make_session, fit):
    """A session showing *fit* on the data it was made on, with its Ka profile computed."""
    session = make_session(_data())
    _deliver(session, fit)
    _wait_until(qapp, lambda: session._state.profile_result is not None)
    return session


def _toggle(session, rid: str, on: bool) -> None:
    session._replica_panel._checkboxes[rid].setChecked(on)


def _pick(session, label: str) -> int:
    """Choose the selector item starting with *label*; returns the pool index it names."""
    combo = session._summary_widget._rep_combo
    index = next(i for i in range(combo.count()) if combo.itemText(i).startswith(label))
    assert index != combo.currentIndex()
    combo.setCurrentIndex(index)
    return combo.itemData(index)


def _numbers(session) -> tuple:
    """Every fit number the summary shows, with the selector's items."""
    summary = session._summary_widget
    combo = summary._rep_combo
    items = [combo.itemText(i) for i in range(combo.count())]
    labels = (summary._rmse_label, summary._r2_label, summary._passing_label)
    return _cell_texts(summary._table), [label.text() for label in labels], items, combo.currentText()


def _type_into(session, key: str, text: str, *, finish: bool = True) -> None:
    """Type *text* over condition *key*, then press Return when *finish*."""
    spin = session._assay_panel._field_widgets[key]._spinbox
    spin.selectAll()
    QTest.keyClicks(spin, text)
    if finish:
        QTest.keyClick(spin, Qt.Key.Key_Return)


def _assert_hidden(session, note: str, *, profiled: bool = True) -> None:
    """The fit's numbers are gone from every tab, with *note* in their place, and picks and exports are off.

    *profiled* says whether Identifiability holds the fit: an imported fit has no Ka profile to hide.
    """
    summary = session._summary_widget
    assert session._state.fit_results == []
    assert session.hidden_results_note() == note
    assert summary._table.rowCount() == 0
    assert summary._r2_label.text() == '—'
    assert summary._caption.text() == note
    assert not summary._rep_combo.isEnabled() and summary._rep_combo.toolTip() == note
    assert session._plot_widget._fit_results == [] and session._plot_widget._mismatch_note == note
    assert session._distribution_widget._mismatch_note == note
    identifiability = session._identifiability_widget
    assert identifiability._stack.currentWidget() is identifiability._message
    assert (identifiability._message.text() == note) is profiled


# ---------------------------------------------------------------------------
# Hide and restore on selection changes
# ---------------------------------------------------------------------------


def test_switching_the_left_out_replicate_keeps_the_fit_and_every_pick_reports_its_pool(
    qapp, make_session, fit, dialogs
):
    """'c' was left out of the fit, so switching it off or on changes nothing the fit describes.

    A pick is scored on the fit's own replicates: the selector, Fit Quality and
    the stored pool agree whether 'c' is on or off.
    """
    session = _shown_session(qapp, make_session, fit)
    summary = session._summary_widget
    quality = fit.quality_samples['r_squared']

    for on, label in ((False, 'Worst'), (True, 'Best')):
        _toggle(session, 'c', on)
        assert session._state.fit_results == [fit]
        assert session.hidden_results_note() is None
        index = _pick(session, label)
        assert fit.representative_index == index
        assert fit.r_squared == quality[index]
        assert float(summary._rep_combo.currentText().split('R²=')[1]) == pytest.approx(quality[index], abs=5e-5)
        assert float(summary._r2_label.text()) == pytest.approx(quality[index], abs=5e-5)


def test_switching_a_used_replicate_off_hides_the_fit_everywhere_until_it_is_back_on(qapp, make_session, fit, dialogs):
    session = _shown_session(qapp, make_session, fit)
    ms = session._state.measurement_set
    session._on_sensitivity_complete(_made_on(_sobol_result(), ms, session._assay_panel.current_conditions()))
    before = _numbers(session)
    sensitivity = session._sensitivity_widget
    assert sensitivity._stack.currentWidget() is sensitivity._results_host

    _toggle(session, 'a', False)

    _assert_hidden(
        session,
        'This fit was made on replicates A and B. Replicate A is now off. Switch it back on, or run the fit again.',
    )
    run_note = (
        'This sensitivity analysis was made on replicates A–C. Replicate A is now off. Switch it back on, or run '
        'the analysis again.'
    )
    assert sensitivity._stack.currentWidget() is sensitivity._mismatch_label
    assert sensitivity._mismatch_label.text() == run_note
    assert session._state.sensitivity_result is not None and session._state.held_fit_results == [fit]

    _toggle(session, 'a', True)

    assert session._state.fit_results == [fit] and session.hidden_results_note() is None
    assert _numbers(session) == before
    assert session._summary_widget._rep_combo.isEnabled()
    assert session._plot_widget._fit_results == [fit] and session._plot_widget._mismatch_note is None
    assert session._distribution_widget._mismatch_note is None
    assert session._identifiability_widget._stack.currentWidget() is session._identifiability_widget._content
    assert sensitivity._stack.currentWidget() is sensitivity._results_host


def test_the_status_bar_stops_describing_results_that_have_been_hidden(qapp, make_session, fit, dialogs):
    """A completion message would otherwise report numbers no tab is showing any more."""
    session = _shown_session(qapp, make_session, fit)
    messages: list[str] = []
    session.status_message.connect(messages.append)
    session.status_message.emit('Fit complete — R²=0.9991, RMSE=1.23×10¹, 8/8 trials passed')

    _toggle(session, 'a', False)

    assert messages[-1] == 'Results hidden — they do not describe the data and settings loaded now.'


def test_a_sensitivity_run_is_hidden_and_shown_on_its_own_record(qapp, make_session, fit, dialogs):
    """The run used every replicate, the fit left 'c' out: switching 'c' off hides the run only."""
    session = _shown_session(qapp, make_session, fit)
    ms = session._state.measurement_set
    session._on_sensitivity_complete(_made_on(_sobol_result(), ms, session._assay_panel.current_conditions()))

    _toggle(session, 'c', False)

    assert session._state.fit_results == [fit]
    assert session._state.sensitivity_note.startswith('This sensitivity analysis was made on replicates A–C.')
    assert session._summary_widget._sensitivity_note == session._state.sensitivity_note
    identifiability = session._identifiability_widget
    assert 'The sensitivity samples are not shown.' in identifiability._notes.text()
    assert identifiability._controls.isHidden(), 'no colour control for dots that are not drawn'
    _toggle(session, 'c', True)
    assert session._state.sensitivity_note is None
    assert not identifiability._controls.isHidden()


def test_a_condition_edit_hides_the_fit_once_finished_and_the_same_value_restores_it(qapp, make_session, fit, dialogs):
    session = _shown_session(qapp, make_session, fit)
    before = _numbers(session)

    _type_into(session, 'h0', '12', finish=False)
    assert session._state.fit_results == [fit], 'hidden while still typing'

    QTest.keyClick(session._assay_panel._field_widgets['h0']._spinbox, Qt.Key.Key_Return)
    _assert_hidden(
        session,
        'This fit was made on replicates A and B with [Host]₀ = 10 µM. [Host]₀ is now 12 µM. Set it back to 10 µM, '
        'or run the fit again.',
    )

    _type_into(session, 'h0', '10')
    assert session._state.fit_results == [fit]
    assert _numbers(session) == before

    session._assay_panel._field_widgets['h0']._combo.setCurrentText('nM')
    assert session._state.fit_results == [fit]
    assert _numbers(session) == before


def test_a_pause_in_typing_finishes_a_condition_edit(qapp, make_session, fit, dialogs):
    session = _shown_session(qapp, make_session, fit)

    _type_into(session, 'd0', '6', finish=False)
    assert session._state.fit_results == [fit]
    _wait_until(qapp, lambda: not session._state.fit_results, timeout=5.0)

    assert '[Dye]₀ is now 6 µM' in session.hidden_results_note()


def test_switching_the_assay_type_hides_the_fit_and_switching_back_restores_it(qapp, make_session, fit, dialogs):
    session = _shown_session(qapp, make_session, fit)
    before = _numbers(session)

    session._assay_panel.set_assay_type(AssayType.GDA)
    _assert_hidden(
        session,
        'This fit was made on replicates A and B for IDA (Indicator Displacement Assay). The assay is now GDA '
        '(Guest Displacement Assay). Switch the assay back to IDA (Indicator Displacement Assay), or run the fit '
        'again.',
    )

    session._assay_panel.set_assay_type(AssayType.IDA)  # the form comes back with the default conditions
    for key, text in (('Ka_dye', '500000'), ('h0', '10'), ('d0', '5')):
        _type_into(session, key, text)

    assert session._state.fit_results == [fit]
    assert _numbers(session) == before


def test_window_disables_result_exports_while_the_fit_is_hidden(qapp, make_session, fit, dialogs, monkeypatch):
    from gui.main_window import FittingMainWindow
    from gui.session import build_artefacts

    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    window = FittingMainWindow()
    session = window.active_session()
    session._assay_panel.set_assay_type(AssayType.IDA)
    for key, value in _CONDITIONS.items():
        session._assay_panel._field_widgets[key].setValue(value.magnitude)
    session._data_panel.data_loaded.emit(_data())
    _deliver(session, fit)
    exports = (window._act_export, window._act_export_txt, window._act_export_csv, window._act_export_dists)
    assert all(action.isEnabled() for action in exports)

    _toggle(session, 'b', False)
    note = session.hidden_results_note()
    assert note.startswith('This fit was made on replicates A and B. Replicate B is now off.')
    assert all(not action.isEnabled() and action.toolTip() == note for action in exports)
    artefacts = {artefact.key: artefact for artefact in build_artefacts(session)}
    for key in ('results_json', 'results_txt', 'results_csv', 'distributions_png'):
        assert not artefacts[key].available and artefacts[key].unavailable_reason == note

    _toggle(session, 'b', True)
    assert all(action.isEnabled() for action in exports)
    for thread in session.findChildren(QThread):
        thread.wait()


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def _import(session, monkeypatch, tmp_path, results: list[FitResult]) -> None:
    from gui.session import export_results

    path = tmp_path / 'results.json'
    export_results(results, path)
    monkeypatch.setattr('gui.fitting_session.QFileDialog.getOpenFileName', lambda *args: (str(path), ''))
    session.import_results()


def test_import_of_a_fit_made_on_the_loaded_data_is_shown_unchanged(
    qapp, make_session, fit, dialogs, monkeypatch, tmp_path
):
    session = make_session(_data())

    _import(session, monkeypatch, tmp_path, [fit])

    assert dialogs == {'warning': [], 'information': []}
    (shown,) = session._state.fit_results
    assert (shown.r_squared, shown.rmse, shown.representative_index) == (
        fit.r_squared,
        fit.rmse,
        fit.representative_index,
    )
    assert np.array_equal(shown.quality_samples['r_squared'], fit.quality_samples['r_squared'])
    assert session._summary_widget._r2_label.text() != '—'
    assert session._distribution_widget._result is shown


def test_import_keeps_the_replicate_selection_and_hides_a_fit_it_does_not_match(
    qapp, make_session, fit, dialogs, monkeypatch, tmp_path
):
    session = make_session(_data())
    _toggle(session, 'b', False)

    _import(session, monkeypatch, tmp_path, [fit])

    assert session._state.measurement_set.active_replica_ids == ['a', 'c']
    assert len(session._state.held_fit_results) == 1
    _assert_hidden(
        session,
        'This fit was made on replicates A and B. Replicate B is now off. Switch it back on, or run the fit again.',
        profiled=False,
    )


def test_import_of_an_older_per_replicate_file_recomputes_its_quality_on_the_used_replicates(
    qapp, make_session, fit, dialogs, monkeypatch, tmp_path
):
    """A file that scored its pool against every replicate it was given is re-scored on the replicates it used."""
    ms = _data()
    legacy = FitResult.from_dict(json.loads(json.dumps(fit.to_dict())))
    assay = ms.to_assay(IDAAssay, conditions=_CONDITIONS, use_average=True)
    rows = np.column_stack([legacy.parameter_samples[k] for k in _KEYS])
    scores = np.array(
        [calculate_fit_metrics(assay.y_data.magnitude, assay.forward_model(row).magnitude) for row in rows]
    )
    legacy.quality_samples = {'rmse': scores[:, 0], 'r_squared': scores[:, 1]}
    for key in ('quality_scored_on', 'data_fingerprint', 'active_replica_ids'):
        del legacy.metadata[key]
    session = make_session(_data())

    _import(session, monkeypatch, tmp_path, [legacy])

    (shown,) = session._state.fit_results
    for key in ('rmse', 'r_squared'):
        np.testing.assert_allclose(shown.quality_samples[key], fit.quality_samples[key], rtol=1e-12, atol=0)
    assert shown.r_squared == pytest.approx(fit.r_squared, rel=1e-12)
    assert shown.rmse == pytest.approx(fit.rmse, rel=1e-12)
    ((_, _, text),) = dialogs['information']
    assert 'did not describe the replicates each fit used, so the R², RMSE and curve were recomputed' in text
    assert 'pick' not in text, 'the reported fit is the one the file reported'
    assert dialogs['warning'] == []


def test_import_onto_other_data_is_refused(qapp, make_session, fit, dialogs, monkeypatch, tmp_path):
    ms = _data()
    other = MeasurementSet(concentrations=ms.concentrations * 1.001, signals=ms.signals, replica_ids=ms.replica_ids)
    session = make_session(other)

    _import(session, monkeypatch, tmp_path, [fit])

    assert session._state.held_fit_results == []
    ((_, title, text),) = dialogs['warning']
    assert title == 'Results Not Imported'
    assert 'were made on other data than the data loaded now, so nothing was imported' in text


def test_import_whose_numbers_do_not_reproduce_on_its_own_data_says_so(
    qapp, make_session, fit, dialogs, monkeypatch, tmp_path
):
    """The fingerprint matches, so the refusal does not blame the data."""
    altered = copy.deepcopy(fit)
    altered.quality_samples['r_squared'] = altered.quality_samples['r_squared'] * (1 - 1e-3)
    session = make_session(_data())

    _import(session, monkeypatch, tmp_path, [altered])

    assert session._state.held_fit_results == []
    ((_, _, text),) = dialogs['warning']
    assert 'were made on the data loaded now, but their numbers could not be reproduced on it' in text
    assert 'other data' not in text


def test_import_of_a_file_without_a_replicate_record_names_the_selection_when_refused(
    qapp, make_session, average_fit, dialogs, monkeypatch, tmp_path
):
    released = copy.deepcopy(average_fit)
    for key in ('active_replica_ids', 'data_fingerprint', 'quality_scored_on'):
        del released.metadata[key]
    session = make_session(_data())
    _toggle(session, 'c', False)

    _import(session, monkeypatch, tmp_path, [released])

    ((_, _, text),) = dialogs['warning']
    assert 'do not match the data and replicates selected now' in text
    assert 'does not record which replicates the fit used' in text

    dialogs['warning'].clear()
    _toggle(session, 'c', True)
    _import(session, monkeypatch, tmp_path, [released])
    assert dialogs['warning'] == []
    (shown,) = session._state.fit_results
    assert shown.metadata['active_replica_ids'] == ['a', 'b', 'c']


def test_import_that_cannot_be_checked_is_refused_in_plain_words(
    qapp, make_session, fit, dialogs, monkeypatch, tmp_path
):
    def broken(result, ms):
        raise TypeError('Ka_dye must be a pint Quantity, got float')

    monkeypatch.setattr('gui.fitting_session.verify_imported_result', broken)
    session = make_session(_data())

    _import(session, monkeypatch, tmp_path, [fit])

    assert session._state.held_fit_results == []
    ((_, title, text),) = dialogs['warning']
    assert title == 'Results Not Imported'
    assert 'could not be checked against the data loaded now, so nothing was imported' in text
    assert 'Quantity' not in text


def test_import_of_a_released_file_with_bare_number_conditions_is_checked_and_shown(
    qapp, make_session, average_fit, dialogs, monkeypatch, tmp_path
):
    """A release before condition units wrote each condition as a bare number in its base unit."""
    d = json.loads(json.dumps(average_fit.to_dict()))
    del d['condition_units']
    path = tmp_path / 'released.json'
    path.write_text(json.dumps([d]))
    monkeypatch.setattr('gui.fitting_session.QFileDialog.getOpenFileName', lambda *args: (str(path), ''))
    session = make_session(_data())

    session.import_results()

    assert dialogs['warning'] == []
    (shown,) = session._state.fit_results
    assert shown.r_squared == average_fit.r_squared
    _type_into(session, 'h0', '12')
    assert 'This fit was made on replicates A–C with [Host]₀ = 10 µM.' in session.hidden_results_note()


def test_import_of_a_file_written_before_the_arithmetic_marker_says_its_numbers_were_recomputed(
    qapp, make_session, dialogs, monkeypatch
):
    """``unmarked_gda.json`` stores the scores of a less precise equilibrium solve.

    Its fit is shown; the one notice tells the user which of its numbers the app
    computed again.
    """
    fixtures = Path(__file__).resolve().parents[2] / 'fixtures' / 'results'
    conditions = {'Ka_dye': 1e7, 'h0': 2e-7, 'g0': 2e-7}
    session = make_session()
    session._assay_panel.set_assay_type(AssayType.GDA)
    for key, value in conditions.items():
        session._assay_panel._field_widgets[key].setValue(value)
    session._data_panel.data_loaded.emit(
        MeasurementSet.from_dataframe(load_measurements(fixtures / 'unmarked_gda_data.txt'))
    )
    monkeypatch.setattr(
        'gui.fitting_session.QFileDialog.getOpenFileName', lambda *args: (str(fixtures / 'unmarked_gda.json'), '')
    )

    session.import_results()

    assert dialogs['warning'] == []
    ((_, title, text),) = dialogs['information']
    assert title == 'Imported Results'
    assert text == (
        'unmarked_gda.json was written by an earlier version of SupraSimFit. Its R², RMSE and fit curve were '
        'computed again with the equilibrium solution this version uses. The fitted values are unchanged.'
    )
    (shown,) = session._state.fit_results
    assert shown.parameters['Ka_guest'].magnitude > 0


def test_import_of_a_released_per_replicate_file_gives_both_reasons_its_numbers_changed(
    qapp, make_session, dialogs, monkeypatch
):
    """``v150_pr_drop.json`` scored its pool against a replicate the fit left out *and* records no
    arithmetic, so the app rebuilt its numbers twice over and owes the user both reasons."""
    root = Path(__file__).resolve().parents[3]
    fixtures = root / 'tests' / 'fixtures' / 'results'
    session = make_session()
    session._assay_panel.set_assay_type(AssayType.IDA)
    for key, value in (('Ka_dye', 16.8e6), ('h0', 4.3e-6), ('d0', 6e-6)):
        session._assay_panel._field_widgets[key].setValue(value)
    session._data_panel.data_loaded.emit(
        MeasurementSet.from_dataframe(load_measurements(root / 'data' / 'IDA_system.txt'))
    )
    monkeypatch.setattr(
        'gui.fitting_session.QFileDialog.getOpenFileName', lambda *args: (str(fixtures / 'v150_pr_drop.json'), '')
    )

    session.import_results()

    assert dialogs['warning'] == []
    ((_, _, text),) = dialogs['information']
    assert 'did not describe the replicates each fit used' in text
    assert 'written by an earlier version' in text
    assert text.index('replicates each fit used') < text.index('written by an earlier version'), (
        'the replicate reason comes first'
    )


def test_import_without_data_shows_the_stored_numbers_unchecked_with_picks_disabled(
    qapp, make_session, fit, dialogs, monkeypatch, tmp_path
):
    from gui.fitting_session import _UNCHECKED_NOTE

    session = make_session()

    _import(session, monkeypatch, tmp_path, [fit])

    (shown,) = session._state.fit_results
    summary = session._summary_widget
    assert float(summary._r2_label.text()) == pytest.approx(fit.r_squared, abs=5e-5)
    assert summary._caption.text() == _UNCHECKED_NOTE
    assert not summary._rep_combo.isEnabled() and summary._rep_combo.toolTip() == _UNCHECKED_NOTE
    worst = int(np.argmin(fit.quality_samples['r_squared']))
    session._on_plot_fit_selected(worst)
    assert shown.representative_index == fit.representative_index


def test_import_without_data_hides_a_fit_of_another_assay_type_and_labels_the_axes_for_the_fit(
    qapp, make_session, fit, dialogs, monkeypatch, tmp_path
):
    session = make_session()
    session._assay_panel.set_assay_type(AssayType.GDA)

    _import(session, monkeypatch, tmp_path, [fit])

    plot = session._plot_widget
    assert session._state.fit_results == [] and plot._fit_items == []
    assert session.hidden_results_note().startswith('This fit was made for IDA (Indicator Displacement Assay).')

    session._assay_panel.set_assay_type(AssayType.IDA)  # the form comes back with the default conditions
    for key, text in (('Ka_dye', '500000'), ('h0', '10'), ('d0', '5')):
        _type_into(session, key, text)

    assert len(session._state.fit_results) == 1
    assert len(plot._fit_items) == 1
    assert plot._pg_widget.getPlotItem().getAxis('bottom').labelText.startswith('Guest')


# ---------------------------------------------------------------------------
# Several results
# ---------------------------------------------------------------------------


def test_one_hidden_result_leaves_the_shown_one_drawn_and_exportable(
    qapp, make_session, fit, average_fit, dialogs, monkeypatch, tmp_path
):
    """Switching 'c' off hides the fit of the average of A–C only; the per-replicate fit on A and B stays."""
    from gui.session import build_artefacts

    session = make_session(_data())
    _import(session, monkeypatch, tmp_path, [average_fit, fit])
    _toggle(session, 'c', False)

    (shown,) = session._state.fit_results
    assert shown.id == fit.id
    assert session.hidden_results_note() is None
    plot = session._plot_widget
    assert plot._mismatch_note is None and len(plot._fit_items) == 1 and plot._fit_results == [shown]
    assert plot._note.text() == (
        '1 of the 2 fits is hidden and not drawn. This hidden fit was made on replicates A–C. Replicate C is now '
        'off. Switch it back on, or run the fit again.'
    )
    artefacts = {artefact.key: artefact for artefact in build_artefacts(session)}
    assert all(artefacts[key].available for key in ('results_json', 'results_txt', 'results_csv'))
    assert session._summary_widget._rep_combo.isEnabled()

    _toggle(session, 'c', True)
    assert len(session._state.fit_results) == 2 and len(plot._fit_items) == 2
    assert 'hidden' not in plot._note.text()


# ---------------------------------------------------------------------------
# Work still running
# ---------------------------------------------------------------------------


@pytest.fixture
def slow_fit(monkeypatch, fitted):
    """Make the fit worker return a copy of the module's fit, recording the data it was given."""
    from gui import workers

    given: list[MeasurementSet] = []

    def fake(ms, assay_cls, conditions, config, should_cancel=None):
        given.append(ms)
        deadline = time.monotonic() + 0.2
        while time.monotonic() < deadline:
            if should_cancel is not None and should_cancel():
                raise FitCancelled('The fit was cancelled.')
            time.sleep(0.005)
        return copy.deepcopy(fitted)

    monkeypatch.setattr(workers, 'fit_measurement_set', fake)
    return given


def test_loading_other_data_mid_fit_never_shows_that_fit(qapp, make_session, dialogs, slow_fit):
    session = make_session(_data())
    session.run_fit()
    worker = session._fit_worker

    session._data_panel.data_loaded.emit(_data())
    worker.wait()
    for _ in range(5):
        qapp.processEvents()

    assert not session.fit_running()
    assert session._state.held_fit_results == []
    assert session._summary_widget._r2_label.text() == '—'
    assert dialogs['warning'] == []


def test_a_fit_finishing_after_a_used_replicate_was_switched_off_is_held_hidden_and_profiled_on_its_record(
    qapp, make_session, dialogs, slow_fit
):
    session = make_session(_data())
    session.run_fit()
    messages: list[str] = []
    session.status_message.connect(lambda text: messages.append(text) if text.startswith('Fit') else None)

    _toggle(session, 'b', False)
    _wait_until(qapp, lambda: session._state.profile_result is not None)

    assert slow_fit[0].active_replica_ids == ['a', 'b', 'c']
    (held,) = session._state.held_fit_results
    assert session._state.fit_results == []
    assert session.hidden_results_note().startswith('This fit was made on replicates A and B. Replicate B is now off.')
    assert set(session._state.profile_result.replica_r2) == set(held.metadata['replica_ids_fit'])
    assert messages == [f'Fit complete but hidden — {session.hidden_results_note()}']


def test_a_new_fit_replaces_the_previous_one_on_identifiability_before_its_profile_arrives(
    qapp, make_session, fit, dialogs
):
    from gui.plotting.identifiability_widget import _PROFILE_PENDING

    session = _shown_session(qapp, make_session, fit)
    identifiability = session._identifiability_widget
    assert identifiability._stack.currentWidget() is identifiability._content
    second = copy.deepcopy(fit)
    second.id = 'second-fit'

    _deliver(session, second)

    assert identifiability._fit is second
    assert identifiability._stack.currentWidget() is identifiability._message
    assert identifiability._message.text() == _PROFILE_PENDING
    _wait_until(qapp, lambda: session._state.profile_result is not None)
    assert identifiability._fit is second and identifiability._profile is session._state.profile_result
    assert identifiability._stack.currentWidget() is identifiability._content


def test_run_fit_is_disabled_while_a_fit_runs(qapp, dialogs, slow_fit, monkeypatch):
    from gui.main_window import FittingMainWindow

    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    window = FittingMainWindow()
    session = window.active_session()
    session._assay_panel.set_assay_type(AssayType.IDA)
    session._data_panel.data_loaded.emit(_data())

    session.run_fit()
    worker = session._fit_worker
    assert not window._act_fit.isEnabled()
    assert window._act_fit.toolTip().startswith('A fit is already running in this session.')
    session.run_fit()
    assert session._fit_worker is worker and len(slow_fit) <= 1
    assert dialogs['warning'][-1][1] == 'Already Running'

    _wait_until(qapp, lambda: not session.fit_running())
    assert window._act_fit.isEnabled()
    for thread in session.findChildren(QThread):
        thread.wait()


def test_a_fit_where_every_replicate_fails_is_reported_in_plain_words(qapp, monkeypatch):
    from gui import workers

    reasons = {rid: 'None of its fit attempts reached the minimum R² of 0.99.' for rid in ('a', 'b', 'c')}

    def failing(*args, **kwargs):
        raise PerReplicaFitError('None of the 3 replicates could be fitted on its own.', reasons)

    monkeypatch.setattr(workers, 'fit_measurement_set', failing)
    worker = workers.FitWorker(_data(), IDAAssay, _CONDITIONS, FitConfig())
    messages: list[str] = []
    worker.error.connect(messages.append)
    worker.run()
    monkeypatch.setattr(workers, 'fit_measurement_set', lambda *args, **kwargs: 1 / 0)
    worker.run()

    first, second = messages
    assert first.startswith('None of the 3 replicates could be fitted on its own.')
    assert '  • Replicate C: None of its fit attempts reached the minimum R² of 0.99.' in first
    assert 'division' not in second and second.startswith('The fit could not be completed.')
