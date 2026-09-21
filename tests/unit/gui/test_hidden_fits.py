"""A fit is shown only while the loaded selection matches the record it was made on.

The session holds each result with its record: the replicates it used and was
given, its conditions, its assay type and a fingerprint of the data. A change
to the replicates, the conditions or the assay type that breaks the match hides
the result on every tab behind a note naming what changed, and disables the
result exports; undoing the change shows it again with identical numbers.
Imports are checked against the loaded data, and work still running never
reaches data it was not given.

A change to what the Input Uncertainty panel states hides the fit too: the
interval it reports is the one that covers the uncertainties the fit was given,
so a different set of them asks a different question of the same data.

The data hold two replicates that follow the IDA ground truth and one that
follows the same model at three times its Ka, which the replicate test leaves
out of the fit. One fit is made per module and handed to each session the way
the fit worker hands over its result.
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
from core.pipeline.fit_pipeline import FitConfig, FitResult, fit_measurement_set, fit_view  # noqa: E402
from core.pipeline.varpro import FitCancelled, FitRefused  # noqa: E402
from core.units import Q_  # noqa: E402
from tests.conftest import GDA_IDA_RECOVERY_BOUNDS, IDA_TRUE, _make_ida_data  # noqa: E402
from tests.unit.gui.test_sensitivity_gui import _made_on, _sobol_result  # noqa: E402
from tests.unit.gui.test_session_lifecycle import _state_dilution, _state_shared_source  # noqa: E402

_CONDITIONS = {
    'Ka_dye': Q_(IDA_TRUE['Ka_dye'], '1/M'),
    'h0': Q_(IDA_TRUE['h0'], 'M'),
    'd0': Q_(IDA_TRUE['d0'], 'M'),
}


def _data() -> MeasurementSet:
    """'a' and 'b' carry 1 % noise around the IDA ground truth; 'c' follows the same model at 3× its Ka."""
    rng = np.random.default_rng(0)
    x, y = _make_ida_data(IDA_TRUE, n_points=20)
    _, y_off = _make_ida_data({**IDA_TRUE, 'Ka_guest': 3 * IDA_TRUE['Ka_guest']}, n_points=20)
    signals = np.vstack([row * (1 + 0.01 * rng.standard_normal(row.size)) for row in (y, y, y_off)])
    return MeasurementSet(concentrations=x, signals=signals, replica_ids=('a', 'b', 'c'))


@pytest.fixture(scope='module')
def fitted() -> FitResult:
    config = FitConfig(per_replica=True, custom_bounds=GDA_IDA_RECOVERY_BOUNDS)
    result = fit_measurement_set(_data(), IDAAssay, _CONDITIONS, config)
    assert result.metadata['replica_ids_fit'] == ['a', 'b']
    assert list(result.metadata['replica_failures']) == ['c']
    return result


@pytest.fixture
def fit(fitted) -> FitResult:
    """A fresh copy of the module's fit: a session records its own checks on the result it is given."""
    return copy.deepcopy(fitted)


#: Titrant stock of the diluted fit: ten times the highest titrant
#: concentration in the data, so the last point sits at a tenth of the sample's
#: volume and the totals there are down by 10 %.
_STOCK = Q_(10 * float(_data().concentrations.max()), 'M')


@pytest.fixture(scope='module')
def diluted_fitted() -> FitResult:
    """A fit made with the additions diluting the sample, for the notes about the dilution."""
    conditions = {**_CONDITIONS, 'titrant_stock': _STOCK, 'stock_contains': ()}
    config = FitConfig(per_replica=True, custom_bounds=GDA_IDA_RECOVERY_BOUNDS)
    return fit_measurement_set(_data(), IDAAssay, conditions, config)


@pytest.fixture
def diluted_fit(diluted_fitted) -> FitResult:
    """A fresh copy of the module's diluted fit."""
    return copy.deepcopy(diluted_fitted)


@pytest.fixture(scope='module')
def average_fit() -> FitResult:
    """A fit of the average of every replicate, 'c' included."""
    config = FitConfig(per_replica=False, custom_bounds=GDA_IDA_RECOVERY_BOUNDS)
    result = fit_measurement_set(_data(), IDAAssay, _CONDITIONS, config)
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


def _deliver_sensitivity(session, fit):
    """Hand *session* a Sobol' run, with the uncertainties it was drawn from stated on the panel.

    The panel is what both results are checked against, so the run's own specs
    are set on it and recorded on *fit* — the state the app is in once a fit
    and an analysis have been run on one set of uncertainties.
    """
    from core.pipeline.inputs import specs_to_dict

    ms = session._state.measurement_set
    result = _made_on(_sobol_result(), ms, session._assay_panel.current_conditions())
    fit.fit_config['input_uncertainty'] = specs_to_dict(result.config.errors.specs)
    for key, spec in result.config.errors.specs.items():
        session._input_panel._rows[key].set_spec(spec)
    session._on_sensitivity_complete(result)
    return result


def _toggle(session, rid: str, on: bool) -> None:
    session._replica_panel._checkboxes[rid].setChecked(on)


def _cell_texts(table) -> list[list[str]]:
    """Every cell of a summary table, as the user reads it."""
    return [
        [table.cellWidget(row, col).text() for col in range(table.columnCount())] for row in range(table.rowCount())
    ]


def _numbers(session) -> tuple:
    """Every fit number the summary shows."""
    summary = session._summary_widget
    labels = (summary._rmse_label, summary._r2_label, summary._replicates_label)
    return _cell_texts(summary._table), [label.text() for label in labels]


def _type_into(session, key: str, text: str, *, finish: bool = True) -> None:
    """Type *text* over condition *key*, then press Return when *finish*."""
    spin = session._assay_panel._field_widgets[key]._spinbox
    spin.selectAll()
    QTest.keyClicks(spin, text)
    if finish:
        QTest.keyClick(spin, Qt.Key.Key_Return)


def _assert_hidden(session, note: str, *, profiled: bool = True) -> None:
    """The fit's numbers are gone from every tab, with *note* in their place, and the exports are off.

    *profiled* says whether Identifiability holds the fit: an imported fit has no Ka profile to hide.
    """
    summary = session._summary_widget
    assert session._state.fit_results == []
    assert session.hidden_results_note() == note
    assert summary._table.rowCount() == 0
    assert summary._r2_label.text() == '—'
    assert summary._caption.text() == note
    assert session._plot_widget._fit_results == [] and session._plot_widget._mismatch_note == note
    identifiability = session._identifiability_widget
    assert identifiability._stack.currentWidget() is identifiability._message
    assert (identifiability._message.text() == note) is profiled


# ---------------------------------------------------------------------------
# Hide and restore on selection changes
# ---------------------------------------------------------------------------


def test_switching_the_left_out_replicate_keeps_the_fit_and_its_numbers(qapp, make_session, fit, dialogs):
    """'c' was left out of the fit, so switching it off or on changes nothing the fit describes."""
    session = _shown_session(qapp, make_session, fit)
    before = _numbers(session)

    for on in (False, True):
        _toggle(session, 'c', on)
        assert session._state.fit_results == [fit]
        assert session.hidden_results_note() is None
        assert _numbers(session) == before


def test_switching_a_used_replicate_off_hides_the_fit_everywhere_until_it_is_back_on(qapp, make_session, fit, dialogs):
    session = _shown_session(qapp, make_session, fit)
    _deliver_sensitivity(session, fit)
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
    assert session._plot_widget._fit_results == [fit] and session._plot_widget._mismatch_note is None
    assert session._identifiability_widget._stack.currentWidget() is session._identifiability_widget._content
    assert sensitivity._stack.currentWidget() is sensitivity._results_host


def test_the_status_bar_stops_describing_results_that_have_been_hidden(qapp, make_session, fit, dialogs):
    """A completion message would otherwise report numbers no tab is showing any more."""
    session = _shown_session(qapp, make_session, fit)
    messages: list[str] = []
    session.status_message.connect(messages.append)
    session.status_message.emit('Fit complete — R²=0.9991, RMSE=1.23×10¹, 2 of 3 replicates used')

    _toggle(session, 'a', False)

    assert messages[-1] == 'Results hidden — they do not describe the data and settings loaded now.'


def test_a_sensitivity_run_is_hidden_and_shown_on_its_own_record(qapp, make_session, fit, dialogs):
    """The run used every replicate, the fit left 'c' out: switching 'c' off hides the run only."""
    session = _shown_session(qapp, make_session, fit)
    _deliver_sensitivity(session, fit)

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


def test_changing_an_uncertainty_hides_the_sensitivity_run_it_was_drawn_from(qapp, make_session, fit, dialogs):
    """The uncertainties are what the analysis samples, so another set of them makes it answer another question."""
    from core.pipeline.inputs import InputSpec

    session = _shown_session(qapp, make_session, fit)
    _deliver_sensitivity(session, fit)
    assert session._state.sensitivity_note is None

    session._input_panel._rows['h0'].set_spec(InputSpec.sigma_pct(30.0))

    assert session._state.sensitivity_note == (
        'The input uncertainties have changed since this analysis; set them back under Input Uncertainty, or '
        'run the analysis again.'
    )
    assert session._summary_widget._sensitivity_note == session._state.sensitivity_note
    assert session._sensitivity_widget._mismatch_label.text() == session._state.sensitivity_note

    session._input_panel._rows['h0'].set_spec(InputSpec.sigma_pct(5.0))

    assert session._state.sensitivity_note is None


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


def test_a_conditions_difference_with_no_name_is_said_even_beside_a_replicate_change(qapp, make_session, fit, dialogs):
    """Two changes, two sentences: a replicate switched off must not swallow the one about the conditions.

    A result can carry a condition the form has no field for — here one of
    another assay's — so the comparison sees the conditions differ without a
    name to put on the difference. A note that then mentioned only the
    replicate would offer a fix that leaves the result describing another
    configuration than the one entered.
    """
    session = _shown_session(qapp, make_session, fit)
    fit.conditions = {**fit.conditions, 'g0': Q_(1e-6, 'M')}

    _toggle(session, 'a', False)

    _assert_hidden(
        session,
        'This fit was made on replicates A and B. Replicate A is now off and the assay conditions entered now '
        'differ from its own. Change these back, or run the fit again.',
    )


def _diluted_session(qapp, make_session, diluted_fit):
    """A session with the dilution stated as the diluted fit was made with it, showing that fit."""
    session = make_session(_data())
    _state_dilution(session, _STOCK.magnitude)
    _deliver(session, diluted_fit)
    _wait_until(qapp, lambda: session._state.profile_result is not None)
    assert session.hidden_results_note() is None
    return session


def test_changing_the_titrant_stock_hides_the_fit_and_names_it(qapp, make_session, diluted_fit, dialogs):
    """The stock says how much each addition dilutes the sample, so another one is another model of the data."""
    session = _diluted_session(qapp, make_session, diluted_fit)

    session._assay_panel._stock_widget.setValue(2 * _STOCK.magnitude)
    session._assay_panel._finish_edit()

    _assert_hidden(
        session,
        'This fit was made on replicates A and B with Titrant stock concentration = 500 µM. Titrant stock '
        'concentration is now 1000 µM. Set it back to 500 µM, or run the fit again.',
    )


def test_switching_the_dilution_off_hides_a_fit_made_with_it(qapp, make_session, diluted_fit, dialogs):
    """Constant totals are a different model of the same data, and no condition field shows the difference."""
    session = _diluted_session(qapp, make_session, diluted_fit)

    session._assay_panel._dilution_combo.setCurrentIndex(0)

    _assert_hidden(
        session,
        'This fit was made on replicates A and B. The dilution by the titrant is now switched off. '
        'Switch it back on, or run the fit again.',
    )


def test_switching_the_dilution_on_hides_a_fit_made_without_it(qapp, make_session, fit, dialogs):
    session = _shown_session(qapp, make_session, fit)

    _state_dilution(session, _STOCK.magnitude)

    _assert_hidden(
        session,
        'This fit was made on replicates A and B. The dilution by the titrant is now switched on. '
        'Switch it off, or run the fit again.',
    )


def test_ticking_a_species_into_the_stock_hides_the_fit(qapp, make_session, diluted_fit, dialogs):
    """A species the stock holds at the sample's concentration does not fall with the additions, so the model changes."""
    session = _diluted_session(qapp, make_session, diluted_fit)

    session._assay_panel._contains_boxes['d0'].setChecked(True)

    _assert_hidden(
        session,
        'This fit was made on replicates A and B. The titrant stock is now stated to contain [Dye]₀. '
        'Untick every concentration under the titrant stock again, or run the fit again.',
    )


def test_changing_a_shared_source_hides_the_fit_and_names_it(qapp, make_session, fit, dialogs):
    """A source several inputs share widens the interval like any other, so the note names it as it names an input."""
    from core.pipeline.inputs import ErrorModel, SharedSource

    session = _shown_session(qapp, make_session, fit)
    fit.fit_config.update(ErrorModel(shared=(SharedSource('Host and dye stock', 4.0, ('h0', 'd0')),)).to_dict())

    _state_shared_source(session, SharedSource('Host and dye stock', 6.0, ('h0', 'd0')))

    _assert_hidden(
        session,
        'This fit was made with Host and dye stock (shared by [Host]₀, [Dye]₀) σ 4 %. The input uncertainties '
        'set now differ: set them back under Input Uncertainty, or fit again to update the interval.',
    )


def test_a_pause_in_typing_finishes_a_condition_edit(qapp, make_session, fit, dialogs):
    session = _shown_session(qapp, make_session, fit)

    _type_into(session, 'd0', '6', finish=False)
    assert session._state.fit_results == [fit]
    _wait_until(qapp, lambda: not session._state.fit_results, timeout=5.0)

    assert '[Dye]₀ is now 6 µM' in session.hidden_results_note()


def test_the_ka_profile_is_given_the_fit_s_own_penalised_profiles(qapp, make_session, fit, dialogs, monkeypatch):
    """The tab has to draw the interval the fit reported, which a second computation of it need not reproduce."""
    from gui import workers

    seen: list = []
    profile = workers.fit_profile

    def record(*args, aware=None, **kwargs):
        seen.append(aware)
        return profile(*args, aware=aware, **kwargs)

    monkeypatch.setattr(workers, 'fit_profile', record)

    session = _shown_session(qapp, make_session, fit)

    assert len(seen) == 1
    assert seen[0] is fit.aware, "the profile got the fit's own result, not one of its own"
    assert session._state.profile_result is not None


def test_stating_an_uncertainty_hides_the_fit_until_it_is_run_again(qapp, make_session, fit, dialogs):
    """The interval on screen takes the inputs as exact; saying they are not makes it answer another question."""
    from core.pipeline.inputs import InputSpec

    session = _shown_session(qapp, make_session, fit)
    before = _numbers(session)

    session._input_panel._rows['h0'].set_spec(InputSpec.sigma_pct(5.0))

    # The note names what the fit was made with, so the panel can be set back
    # to it without opening the file the fit came from.
    _assert_hidden(
        session,
        'This fit was made with every input taken as exact. The input uncertainties set now differ: set them '
        'back under Input Uncertainty, or fit again to update the interval.',
    )

    session._input_panel._rows['h0'].set_spec(None)

    assert session._state.fit_results == [fit]
    assert _numbers(session) == before


def test_the_note_names_the_uncertainties_the_hidden_fit_was_made_with(qapp, make_session, fit, dialogs):
    """A fit made with uncertainties says which ones, as a fit made with other conditions names those."""
    from core.pipeline.inputs import InputSpec, specs_to_dict

    session = _shown_session(qapp, make_session, fit)
    fit.fit_config['input_uncertainty'] = specs_to_dict(
        {'h0': InputSpec.sigma_pct(10.0), '__titrant__': InputSpec.sigma_pct(3.0)}
    )

    session._input_panel._rows['h0'].set_spec(InputSpec.sigma_pct(5.0))

    assert session.hidden_results_note() == (
        'This fit was made with [Host]₀ σ 10 % and Guest (titrant, whole series) σ 3 %. The input uncertainties '
        'set now differ: set them back under Input Uncertainty, or fit again to update the interval.'
    )


def test_typing_a_condition_does_not_hide_the_fit_through_the_uncertainty_rows(qapp, make_session, fit, dialogs):
    """The rows read the conditions as they are typed; an unfinished edit is not a change to what they state."""
    session = _shown_session(qapp, make_session, fit)

    _type_into(session, 'h0', '12', finish=False)

    assert session._state.fit_results == [fit]


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
    exports = (window._act_export, window._act_export_txt, window._act_export_csv)
    assert all(action.isEnabled() for action in exports)

    _toggle(session, 'b', False)
    note = session.hidden_results_note()
    assert note.startswith('This fit was made on replicates A and B. Replicate B is now off.')
    assert all(not action.isEnabled() and action.toolTip() == note for action in exports)
    artefacts = {artefact.key: artefact for artefact in build_artefacts(session)}
    for key in ('results_json', 'results_txt', 'results_csv'):
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
    assert (shown.r_squared, shown.rmse) == (fit.r_squared, fit.rmse)
    assert shown.intervals['Ka_guest'].low == fit.intervals['Ka_guest'].low
    assert shown.degenerate_keys == fit.degenerate_keys
    assert [rf.metadata['replica_id'] for rf in shown.replica_fits] == ['a', 'b', 'c']
    assert session._summary_widget._r2_label.text() != '—'


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
    """A file that scored its fit against every replicate it was given is re-scored on the replicates it used."""
    ms = _data()
    legacy = copy.deepcopy(fit)
    assay = ms.to_assay(IDAAssay, conditions=_CONDITIONS, use_average=True)
    params = np.array([float(legacy.parameters[key].magnitude) for key in assay.parameter_keys])
    legacy.rmse, legacy.r_squared, legacy.x_fit, legacy.y_fit = fit_view(assay, params)
    for key in ('quality_scored_on', 'data_fingerprint'):
        del legacy.metadata[key]
    session = make_session(_data())

    _import(session, monkeypatch, tmp_path, [legacy])

    (shown,) = session._state.fit_results
    assert shown.r_squared == pytest.approx(fit.r_squared, rel=1e-12)
    assert shown.rmse == pytest.approx(fit.rmse, rel=1e-12)
    ((_, _, text),) = dialogs['information']
    assert 'did not describe the replicates each fit used, so the R², RMSE and curve were recomputed' in text
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
    altered.r_squared *= 1 - 1e-3
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
    assert shown.intervals is None, 'a file written before intervals were reported carries none'


def test_import_of_a_released_per_replicate_file_gives_both_reasons_its_numbers_changed(
    qapp, make_session, dialogs, monkeypatch
):
    """``v150_pr_drop.json`` scored its numbers against a replicate the fit left out *and* records no
    arithmetic, so the app rebuilt them twice over and owes the user both reasons."""
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


def test_import_without_data_shows_the_stored_numbers_unchecked(
    qapp, make_session, fit, dialogs, monkeypatch, tmp_path
):
    from gui.fitting_session import _UNCHECKED_NOTE

    session = make_session()

    _import(session, monkeypatch, tmp_path, [fit])

    (shown,) = session._state.fit_results
    summary = session._summary_widget
    assert shown.r_squared == fit.r_squared
    assert summary._r2_label.text() != '—'
    assert _UNCHECKED_NOTE in summary._caption.text()


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
    profile = session._state.profile_result.profiles['Ka_guest']
    assert set(profile.replica_r2) == set(held.metadata['replica_ids_fit'])
    assert messages == [f'Fit complete but hidden — {session.hidden_results_note()}']


def test_a_finished_fit_names_the_replicates_it_left_out_and_why(qapp, make_session, dialogs, slow_fit):
    """Minutes of data must not be dropped without a word — the no-silent-fallbacks rule."""
    session = make_session(_data())
    messages: list[str] = []
    session.status_message.connect(lambda text: messages.append(text) if text.startswith('Fit complete') else None)

    session.run_fit()
    _wait_until(qapp, lambda: session._state.profile_result is not None)

    (message,) = messages
    assert '2 of 3 replicates used' in message
    assert 'Replicate C left out:' in message
    assert 'needs a different Ka' in message
    assert dialogs['warning'] == []


def test_the_status_bar_names_the_test_a_rejected_model_failed_and_not_the_verdict(qapp):
    """Low-scatter replicates reject a curve that follows the data closely, so the short note says what was measured.

    On one line beside an R² of 0.99, a bare verdict on the model reads as a
    failure of the app rather than as the outcome of a powerful test. The
    verdict in full, with the statistic and what to do about it, is in the
    summary block under the plot and in the exported report, which have the
    room for it.
    """
    from core.pipeline.diagnostics import FitDiagnostics, MisfitTest, Verdict
    from gui.fitting_session import _verdict_note
    from gui.plotting.labels import verdict_sentence

    diagnostics = FitDiagnostics(
        conditional_misfit=MisfitTest(kind='lack_of_fit', statistic=199.6, p_value=3.2e-47, dof=(9, 72)),
        misfit=None,
        conflict=None,
        verdict=Verdict.MODEL_INADEQUATE,
    )
    result = FitResult(
        parameters={'Ka_guest': Q_(1e6, '1/M')},
        rmse=5.7e3,
        r_squared=0.9941,
        x_fit=Q_(np.zeros(3), 'M'),
        y_fit=Q_(np.zeros(3), 'au'),
        assay_type='IDA',
        model_name='equilibrium_4param',
        diagnostics=diagnostics,
    )
    note = _verdict_note(result)

    assert note == 'the curve misses the data by more than their scatter allows'
    full = verdict_sentence(diagnostics, {}, {}, html=False)
    assert 'The model does not describe the data' in full
    assert 'try another binding model or check the data' in full


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


def test_the_fit_action_offers_cancel_while_a_fit_runs(qapp, dialogs, slow_fit, monkeypatch):
    """The one fit action stops the running fit; a second fit is refused while it is still going."""
    from gui.main_window import FittingMainWindow

    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    window = FittingMainWindow()
    session = window.active_session()
    session._assay_panel.set_assay_type(AssayType.IDA)
    session._data_panel.data_loaded.emit(_data())

    session.run_fit()
    worker = session._fit_worker
    assert window._act_fit.text() == 'Cancel Fit' and window._act_fit.isEnabled()
    session.run_fit()
    assert session._fit_worker is worker and len(slow_fit) <= 1
    assert dialogs['warning'][-1][1] == 'Already Running'
    assert dialogs['warning'][-1][2].startswith('A fit is already running in this session.')

    _wait_until(qapp, lambda: not session.fit_running())
    assert window._act_fit.text() == 'Run Fit' and window._act_fit.isEnabled()
    for thread in session.findChildren(QThread):
        thread.wait()


def test_a_fit_the_pipeline_refuses_is_reported_in_its_own_words(qapp, monkeypatch):
    """A refusal written for the user is shown as it is; every other failure is translated.

    The pipeline raises :class:`~core.pipeline.varpro.FitRefused` where it has a
    sentence that names the input and the fix. A plain ``ValueError`` is not
    that sentence — numpy and pint raise them with their own jargon — so it is
    logged and reported like any other unexpected failure.
    """
    from gui import workers

    refusal = (
        'The signal of replicate(s) c is the same at every titration point, so nothing in them tells what Ka is. '
        'Switch them off under Replicates and fit again.'
    )

    def raising(exc):
        def run(*args, **kwargs):
            raise exc

        return run

    worker = workers.FitWorker(_data(), IDAAssay, _CONDITIONS, FitConfig())
    messages: list[str] = []
    worker.error.connect(messages.append)
    for failure in (FitRefused(refusal), ValueError('operands could not be broadcast together'), ZeroDivisionError()):
        monkeypatch.setattr(workers, 'fit_measurement_set', raising(failure))
        worker.run()

    shown, library, unexpected = messages
    assert shown == refusal
    for message in (library, unexpected):
        assert 'broadcast' not in message and message.startswith('The fit could not be completed.')


def test_a_dilution_difference_without_data_reads_as_a_sentence(
    qapp, make_session, diluted_fit, dialogs, monkeypatch, tmp_path
):
    """The dilution names no value the fit was made with, so with nothing else differing the note is the change."""
    session = make_session()

    _import(session, monkeypatch, tmp_path, [diluted_fit])

    assert session.hidden_results_note() == (
        'The dilution by the titrant is now switched off. Switch it back on, or run the fit again.'
    )
