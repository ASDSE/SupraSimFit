"""A fit is shown only while the loaded selection matches the record it was made on.

The session holds each result with its record: the replicates it used and was
given, its conditions, its assay type and a fingerprint of the data. A change
to the replicates, the conditions or the assay type that breaks the match hides
the result on every tab behind a note naming what changed, and disables the
result exports; undoing the change shows it again with identical numbers.
Imports are checked against the loaded data, and work still running never
reaches data it was not given.

A change to what Input uncertainty states hides the fit too: the
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
from tests.unit.gui.sensitivity_results import made_on as _made_on  # noqa: E402
from tests.unit.gui.sensitivity_results import sobol_result as _sobol_result  # noqa: E402
from tests.unit.gui.session_setup import state_binding, state_dilution  # noqa: E402
from tests.unit.gui.test_session_lifecycle import _state_shared_source  # noqa: E402

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
    """Build IDA sessions with the fit's conditions and bounds entered; on teardown wait for their worker threads."""
    from gui.fitting_session import FittingSession

    sessions = []

    def build(ms: MeasurementSet | None = None):
        session = FittingSession()
        state_binding(session, assay_type=AssayType.IDA, conditions=_CONDITIONS, bounds=GDA_IDA_RECOVERY_BOUNDS)
        if ms is not None:
            session.model.load(ms, None)
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

    ms = session.model.measurement_set
    conditions = session.model.settings.conditions
    worker = FitWorker(copy.deepcopy(ms), IDAAssay, conditions, FitConfig(), parent=session)
    worker.finished.connect(session.model._on_fit_complete)
    worker.error.connect(session.model._on_fit_error)
    session.model._fit_worker = worker
    worker.finished.emit(result)


def _shown_session(qapp, make_session, fit):
    """A session showing *fit* on the data it was made on, with its Ka profile computed."""
    session = make_session(_data())
    _deliver(session, fit)
    _wait_until(qapp, lambda: session.model.profile is not None)
    return session


def _deliver_sensitivity(session, fit):
    """Hand *session* a Sobol' run, with the uncertainties it was drawn from stated on the panel.

    The panel is what both results are checked against, so the run's own specs
    are set on it and recorded on *fit* — the state the app is in once a fit
    and an analysis have been run on one set of uncertainties.
    """
    from core.pipeline.inputs import specs_to_dict

    ms = session.model.measurement_set
    result = _made_on(_sobol_result(), ms, session.model.settings.conditions)
    # A run's baseline is fitted under the bounds and the replicate mode set, and records them as a fit does.
    result.baseline_fit.fit_config = {key: fit.fit_config[key] for key in ('custom_bounds', 'per_replicate')}
    fit.fit_config['input_uncertainty'] = specs_to_dict(result.config.errors.specs)
    for key, spec in result.config.errors.specs.items():
        session.model.uncertainty.set_spec(key, spec)
        session.model.uncertainty_edited()
    session.model._on_sensitivity_complete(result)
    return result


def _toggle(session, rid: str, on: bool) -> None:
    session.model.set_replicate(rid, on)


def _numbers(session) -> tuple:
    """Every fit number Fit results shows: the parameters and the fit quality."""
    view = session._results
    labels = (view.rmse, view.r2, view.used)
    return view.parameters.texts(), [label.text() for label in labels]


def _curves(session) -> int:
    """How many fitted curves the titration plot of Fit results draws."""
    data = session._results.plot.data
    return 0 if data is None else len(data.curves)


def _shown(session) -> bool:
    """Whether Fit results shows a fit's numbers: its headline and Fit details."""
    view = session._results
    return not view.headline.isHidden() and not view.sections.isHidden()


def _type_into(session, key: str, text: str, *, finish: bool = True) -> None:
    """Type *text* over condition *key* in Binding model, then press Return when *finish*."""
    editor = session._binding._conditions[key].value.editor
    editor.selectAll()
    QTest.keyClicks(editor, text)
    if finish:
        QTest.keyClick(editor, Qt.Key.Key_Return)


def _type_bound(session, key: str, index: int, text: str) -> None:
    """Type *text* over the lower (0) or upper (1) bound of parameter *key* in Binding model."""
    editor = session._binding._bounds[key].fields[index].editor
    editor.selectAll()
    if text:
        QTest.keyClicks(editor, text)
    else:
        QTest.keyClick(editor, Qt.Key.Key_Delete)


def _assert_hidden(session, note: str) -> None:
    """The fit's numbers are gone from every view, with *note* in their place, and the exports are off."""
    view = session._results
    assert session.model.fit_results == []
    assert session.model.hidden_results_note() == note
    assert not _shown(session)
    assert [(c.tone, c.body) for c in view.callouts] == [('neutral', note)]
    assert _curves(session) == 0
    confidence = session._confidence
    assert [(c.tone, c.body) for c in confidence.callouts] == [('neutral', note)]
    assert not confidence.has_plot() and confidence.header_host.isHidden()


# ---------------------------------------------------------------------------
# Hide and restore on selection changes
# ---------------------------------------------------------------------------


def test_switching_the_left_out_replicate_keeps_the_fit_and_its_numbers(qapp, make_session, fit, dialogs):
    """'c' was left out of the fit, so switching it off or on changes nothing the fit describes."""
    session = _shown_session(qapp, make_session, fit)
    before = _numbers(session)

    for on in (False, True):
        _toggle(session, 'c', on)
        assert session.model.fit_results == [fit]
        assert session.model.hidden_results_note() is None
        assert _numbers(session) == before


def test_switching_a_used_replicate_off_hides_the_fit_everywhere_until_it_is_back_on(qapp, make_session, fit, dialogs):
    session = _shown_session(qapp, make_session, fit)
    _deliver_sensitivity(session, fit)
    before = _numbers(session)
    sensitivity = session._sensitivity
    assert sensitivity.has_plot()

    _toggle(session, 'a', False)

    _assert_hidden(
        session,
        'This fit was made on replicates A and B. Replicate A is now off. Switch it back on, or run the fit again.',
    )
    run_note = (
        'This sensitivity analysis was made on replicates A–C. Replicate A is now off. Switch it back on, or run '
        'the analysis again.'
    )
    assert not sensitivity.has_plot()
    assert [(c.title, c.body) for c in sensitivity.callouts] == [('Results hidden', run_note)]
    assert session.model.sensitivity_result is not None and session.model.held_fit_results == [fit]

    _toggle(session, 'a', True)

    assert session.model.fit_results == [fit] and session.model.hidden_results_note() is None
    assert _numbers(session) == before
    assert _curves(session) == 1 and _shown(session)
    assert all(c.tone != 'neutral' for c in session._results.callouts)
    assert session._confidence.has_plot()
    assert sensitivity.has_plot()


def test_the_status_bar_stops_describing_results_that_have_been_hidden(qapp, make_session, fit, dialogs):
    """A completion message would otherwise report numbers no tab is showing any more."""
    session = _shown_session(qapp, make_session, fit)
    messages: list[str] = []
    session.model.status_changed.connect(messages.append)
    session.model.show_status('Fit complete — R²=0.9991, RMSE=1.23×10¹, 2 of 3 replicates used')

    _toggle(session, 'a', False)

    assert messages[-1] == 'Results hidden — they do not describe the data and settings loaded now.'


def test_a_sensitivity_run_is_hidden_and_shown_on_its_own_record(qapp, make_session, fit, dialogs):
    """The run used every replicate, the fit left 'c' out: switching 'c' off hides the run only."""
    session = _shown_session(qapp, make_session, fit)
    _deliver_sensitivity(session, fit)

    _toggle(session, 'c', False)

    assert session.model.fit_results == [fit]
    assert session.model.sensitivity_note.startswith('This sensitivity analysis was made on replicates A–C.')
    assert session._sensitivity.callouts[0].body == session.model.sensitivity_note
    assert session._confidence.has_plot(), 'the fit is still shown in Ka confidence'
    _toggle(session, 'c', True)
    assert session.model.sensitivity_note is None


def test_changing_an_uncertainty_hides_the_sensitivity_run_it_was_drawn_from(qapp, make_session, fit, dialogs):
    """The uncertainties are what the analysis samples, so another set of them makes it answer another question."""
    from core.pipeline.inputs import InputSpec

    session = _shown_session(qapp, make_session, fit)
    _deliver_sensitivity(session, fit)
    assert session.model.sensitivity_note is None

    session.model.uncertainty.set_spec('h0', InputSpec.sigma_pct(30.0))

    session.model.uncertainty_edited()
    assert session.model.sensitivity_note == (
        'The input uncertainties have changed since this analysis; set them back under Input uncertainty, or '
        'run the analysis again.'
    )
    assert session._sensitivity.callouts[0].body == session.model.sensitivity_note

    session.model.uncertainty.set_spec('h0', InputSpec.sigma_pct(5.0))

    session.model.uncertainty_edited()
    assert session.model.sensitivity_note is None


def test_a_condition_edit_hides_the_fit_once_finished_and_the_same_value_restores_it(qapp, make_session, fit, dialogs):
    session = _shown_session(qapp, make_session, fit)
    before = _numbers(session)

    _type_into(session, 'h0', '12', finish=False)
    assert session.model.fit_results == [fit], 'hidden while still typing'

    QTest.keyClick(session._binding._conditions['h0'].value.editor, Qt.Key.Key_Return)
    _assert_hidden(
        session,
        'This fit was made on replicates A and B with [Host]₀ = 10 µM. [Host]₀ is now 12 µM. Set it back to 10 µM, '
        'or run the fit again.',
    )

    _type_into(session, 'h0', '10')
    assert session.model.fit_results == [fit]
    assert _numbers(session) == before

    session._binding._conditions['h0'].unit.chosen.emit(0)  # nM
    assert session.model.fit_results == [fit]
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
    state_dilution(session, _STOCK.magnitude)
    _deliver(session, diluted_fit)
    _wait_until(qapp, lambda: session.model.profile is not None)
    assert session.model.hidden_results_note() is None
    return session


def test_changing_the_titrant_stock_hides_the_fit_and_names_it(qapp, make_session, diluted_fit, dialogs):
    """The stock says how much each addition dilutes the sample, so another one is another model of the data."""
    session = _diluted_session(qapp, make_session, diluted_fit)

    session.model.binding.set_value('titrant_stock', 2 * _STOCK.magnitude)
    session.model.binding_edited()

    _assert_hidden(
        session,
        'This fit was made on replicates A and B with Titrant stock concentration = 500 µM. Titrant stock '
        'concentration is now 1000 µM. Set it back to 500 µM, or run the fit again.',
    )


def test_switching_the_dilution_off_hides_a_fit_made_with_it(qapp, make_session, diluted_fit, dialogs):
    """Constant totals are a different model of the same data, and no condition field shows the difference."""
    session = _diluted_session(qapp, make_session, diluted_fit)

    session._binding.dilution.changed.emit(0)  # Stay constant

    _assert_hidden(
        session,
        'This fit was made on replicates A and B. The dilution by the titrant is now switched off. '
        'Switch it back on, or run the fit again.',
    )


def test_switching_the_dilution_on_hides_a_fit_made_without_it(qapp, make_session, fit, dialogs):
    session = _shown_session(qapp, make_session, fit)

    state_dilution(session, _STOCK.magnitude)

    _assert_hidden(
        session,
        'This fit was made on replicates A and B. The dilution by the titrant is now switched on. '
        'Switch it off, or run the fit again.',
    )


def test_ticking_a_species_into_the_stock_hides_the_fit(qapp, make_session, diluted_fit, dialogs):
    """A species the stock holds at the sample's concentration does not fall with the additions, so the model changes."""
    session = _diluted_session(qapp, make_session, diluted_fit)

    session._binding._contains['d0'].toggled.emit(True)

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
        'set now differ: set them back under Input uncertainty, or fit again to update the interval.',
    )


def test_a_pause_in_typing_finishes_a_condition_edit(qapp, make_session, fit, dialogs):
    session = _shown_session(qapp, make_session, fit)

    _type_into(session, 'd0', '6', finish=False)
    assert session.model.fit_results == [fit]
    _wait_until(qapp, lambda: not session.model.fit_results, timeout=5.0)

    assert '[Dye]₀ is now 6 µM' in session.model.hidden_results_note()


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
    assert session.model.profile is not None


def test_stating_an_uncertainty_hides_the_fit_until_it_is_run_again(qapp, make_session, fit, dialogs):
    """The interval on screen takes the inputs as exact; saying they are not makes it answer another question."""
    from core.pipeline.inputs import InputSpec

    session = _shown_session(qapp, make_session, fit)
    before = _numbers(session)

    session.model.uncertainty.set_spec('h0', InputSpec.sigma_pct(5.0))

    session.model.uncertainty_edited()
    # The note names what the fit was made with, so the panel can be set back
    # to it without opening the file the fit came from.
    _assert_hidden(
        session,
        'This fit was made with every input taken as exact. The input uncertainties set now differ: set them '
        'back under Input uncertainty, or fit again to update the interval.',
    )

    session.model.uncertainty.set_spec('h0', None)

    session.model.uncertainty_edited()
    assert session.model.fit_results == [fit]
    assert _numbers(session) == before


def test_the_note_names_the_uncertainties_the_hidden_fit_was_made_with(qapp, make_session, fit, dialogs):
    """A fit made with uncertainties says which ones, as a fit made with other conditions names those."""
    from core.pipeline.inputs import InputSpec, specs_to_dict

    session = _shown_session(qapp, make_session, fit)
    fit.fit_config['input_uncertainty'] = specs_to_dict(
        {'h0': InputSpec.sigma_pct(10.0), '__titrant__': InputSpec.sigma_pct(3.0)}
    )

    session.model.uncertainty.set_spec('h0', InputSpec.sigma_pct(5.0))

    session.model.uncertainty_edited()
    assert session.model.hidden_results_note() == (
        'This fit was made with [Host]₀ σ 10 % and Guest (titrant, whole series) σ 3 %. The input uncertainties '
        'set now differ: set them back under Input uncertainty, or fit again to update the interval.'
    )


def test_typing_a_condition_does_not_hide_the_fit_through_the_uncertainty_rows(qapp, make_session, fit, dialogs):
    """The rows read the conditions as they are typed; an unfinished edit is not a change to what they state."""
    session = _shown_session(qapp, make_session, fit)

    _type_into(session, 'h0', '12', finish=False)

    assert session.model.fit_results == [fit]


def test_switching_the_assay_type_hides_the_fit_and_switching_back_restores_it(qapp, make_session, fit, dialogs):
    session = _shown_session(qapp, make_session, fit)
    before = _numbers(session)

    state_binding(session, assay_type=AssayType.GDA)
    _assert_hidden(
        session,
        'This fit was made on replicates A and B for IDA. The model is now GDA. Switch the model back to IDA, or '
        'run the fit again.',
    )

    # the form and the bounds come back as the defaults
    state_binding(session, assay_type=AssayType.IDA, bounds=GDA_IDA_RECOVERY_BOUNDS)
    for key, text in (('Ka_dye', '500000'), ('h0', '10'), ('d0', '5')):
        _type_into(session, key, text)

    assert session.model.fit_results == [fit]
    assert _numbers(session) == before


def test_editing_a_bound_hides_the_fit_and_the_bound_it_was_made_under_restores_it(qapp, make_session, fit, dialogs):
    """A bound decides where the search runs and whether an interval end is open: another one asks another question.

    The fit's Ka(G) is about 2×10⁶ M⁻¹, above the upper bound typed here, so no fit under the new bound could
    report it.
    """
    session = _shown_session(qapp, make_session, fit)
    before = _numbers(session)
    assert fit.parameters['Ka_guest'].magnitude > 1e6

    _type_bound(session, 'Ka_guest', 1, '1e6')

    _assert_hidden(
        session,
        'This fit was made on replicates A and B. The Kₐ guest bounds are now 1×10⁻⁸ to 1×10⁶ M⁻¹. Set them back to '
        '1×10⁻⁸ to 1×10¹² M⁻¹, or run the fit again.',
    )

    _type_bound(session, 'Ka_guest', 1, '1e12')

    assert session.model.fit_results == [fit] and session.model.hidden_results_note() is None
    assert _numbers(session) == before


def test_a_bound_that_cannot_be_read_hides_the_fit(qapp, make_session, fit, dialogs):
    """While a row cannot be read, the bounds on screen describe no fit, the one shown included."""
    session = _shown_session(qapp, make_session, fit)

    _type_bound(session, 'I0', 0, '')

    assert session.model.hidden_results_note() == (
        'This fit was made on replicates A and B. The I₀ bounds cannot be read now. Set them back to −100 to 100 '
        'a.u., or run the fit again.'
    )


def test_a_condition_that_cannot_be_read_hides_the_fit_and_says_so(qapp, make_session, fit, dialogs):
    """A text that is no number is no value, so the note says it cannot be read rather than giving it as NaN."""
    session = _shown_session(qapp, make_session, fit)

    _type_into(session, 'h0', 'abc')

    assert session.model.hidden_results_note() == (
        'This fit was made on replicates A and B with [Host]₀ = 10 µM. [Host]₀ cannot be read now. Set it back '
        'to 10 µM, or run the fit again.'
    )


def test_switching_the_replicate_mode_hides_the_fit_and_switching_back_restores_it(qapp, make_session, fit, dialogs):
    """Fitting each replicate separately decides which replicates the fit keeps, so the fit belongs to its mode."""
    session = _shown_session(qapp, make_session, fit)
    before = _numbers(session)

    state_binding(session, per_replica=False)

    _assert_hidden(
        session,
        'This fit was made on replicates A and B. Fitting each replicate separately is now switched off. Switch it '
        'back on, or run the fit again.',
    )

    state_binding(session, per_replica=True)

    assert session.model.fit_results == [fit] and _numbers(session) == before


def test_a_sensitivity_run_is_hidden_by_a_bound_or_the_replicate_mode_its_baseline_was_not_fitted_under(
    qapp, make_session, fit, dialogs
):
    session = _shown_session(qapp, make_session, fit)
    _deliver_sensitivity(session, fit)
    assert session.model.sensitivity_note is None

    _type_bound(session, 'Ka_guest', 1, '1e6')

    assert session.model.sensitivity_note == (
        'This sensitivity analysis was made on replicates A–C. The Kₐ guest bounds are now 1×10⁻⁸ to 1×10⁶ M⁻¹. Set '
        'them back to 1×10⁻⁸ to 1×10¹² M⁻¹, or run the analysis again.'
    )
    assert session._sensitivity.callouts[0].body == session.model.sensitivity_note

    _type_bound(session, 'Ka_guest', 1, '1e12')
    assert session.model.sensitivity_note is None

    state_binding(session, per_replica=False)
    assert 'Fitting each replicate separately is now switched off.' in session.model.sensitivity_note


def test_window_result_exports_say_why_while_the_fit_is_hidden(qapp, make_session, fit, dialogs, monkeypatch):
    from gui.main_window import FittingMainWindow
    from gui.session import build_artefacts

    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    window = FittingMainWindow()
    session = window.active_session()
    state_binding(session, assay_type=AssayType.IDA, conditions=_CONDITIONS, bounds=GDA_IDA_RECOVERY_BOUNDS)
    session.model.load(_data(), None)
    _deliver(session, fit)

    _toggle(session, 'b', False)
    note = session.model.hidden_results_note()
    assert note.startswith('This fit was made on replicates A and B. Replicate B is now off.')
    for action in (window._act_results, window._act_txt, window._act_csv):
        action.trigger()
    assert dialogs['warning'] == [(session, 'Results Hidden', note)] * 3
    artefacts = {artefact.key: artefact for artefact in build_artefacts(session)}
    for key in ('results_json', 'results_txt', 'results_csv'):
        assert not artefacts[key].available and artefacts[key].unavailable_reason == note
    for thread in session.findChildren(QThread):
        thread.wait()


def test_an_export_straight_after_typing_a_condition_writes_nothing_the_form_contradicts(
    qapp, make_session, fit, dialogs, monkeypatch, tmp_path
):
    """The shortcut leaves the focus in the field, so the edit is finished by the export itself."""
    session = _shown_session(qapp, make_session, fit)
    path = tmp_path / 'results.json'
    monkeypatch.setattr('gui.fitting_session.QFileDialog.getSaveFileName', lambda *args: (str(path), ''))

    _type_into(session, 'h0', '12', finish=False)
    session.export_results()

    assert not path.exists()
    ((_, title, text),) = dialogs['warning']
    assert title == 'Results Hidden'
    assert text.startswith('This fit was made on replicates A and B with [Host]₀ = 10 µM. [Host]₀ is now 12 µM.')


def test_a_plot_saved_straight_after_typing_a_condition_shows_the_note_and_not_the_fit(
    qapp, make_session, fit, dialogs, monkeypatch, tmp_path
):
    session = _shown_session(qapp, make_session, fit)
    monkeypatch.setattr(
        'gui.fitting_session.QFileDialog.getSaveFileName', lambda *args: (str(tmp_path / 'plot.png'), '')
    )
    saved_with: list = []
    monkeypatch.setattr(
        session._results,
        'export_image',
        lambda path: saved_with.append((_curves(session), [c.body for c in session._results.callouts])),
    )

    _type_into(session, 'h0', '12', finish=False)
    session.export_plot('Fit results')

    ((curves, (note,)),) = saved_with
    assert curves == 0
    assert note.startswith('This fit was made on replicates A and B with [Host]₀ = 10 µM.')


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
    (shown,) = session.model.fit_results
    assert (shown.r_squared, shown.rmse) == (fit.r_squared, fit.rmse)
    assert shown.intervals['Ka_guest'].low == fit.intervals['Ka_guest'].low
    assert shown.degenerate_keys == fit.degenerate_keys
    assert [rf.metadata['replica_id'] for rf in shown.replica_fits] == ['a', 'b', 'c']
    assert _shown(session)


def test_import_keeps_the_replicate_selection_and_hides_a_fit_it_does_not_match(
    qapp, make_session, fit, dialogs, monkeypatch, tmp_path
):
    session = make_session(_data())
    _toggle(session, 'b', False)

    _import(session, monkeypatch, tmp_path, [fit])

    assert session.model.measurement_set.active_replica_ids == ['a', 'c']
    assert len(session.model.held_fit_results) == 1
    _assert_hidden(
        session,
        'This fit was made on replicates A and B. Replicate B is now off. Switch it back on, or run the fit again.',
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

    (shown,) = session.model.fit_results
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

    assert session.model.held_fit_results == []
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

    assert session.model.held_fit_results == []
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
    state_binding(session, per_replica=False)  # the mode the fit was made in
    _toggle(session, 'c', False)

    _import(session, monkeypatch, tmp_path, [released])

    ((_, _, text),) = dialogs['warning']
    assert 'do not match the data and replicates selected now' in text
    assert 'does not record which replicates the fit used' in text

    dialogs['warning'].clear()
    _toggle(session, 'c', True)
    _import(session, monkeypatch, tmp_path, [released])
    assert dialogs['warning'] == []
    (shown,) = session.model.fit_results
    assert shown.metadata['active_replica_ids'] == ['a', 'b', 'c']


def test_import_that_cannot_be_checked_is_refused_in_plain_words(
    qapp, make_session, fit, dialogs, monkeypatch, tmp_path
):
    def broken(result, ms):
        raise TypeError('Ka_dye must be a pint Quantity, got float')

    monkeypatch.setattr('gui.session_model.verify_imported_result', broken)
    session = make_session(_data())

    _import(session, monkeypatch, tmp_path, [fit])

    assert session.model.held_fit_results == []
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
    state_binding(session, per_replica=False)  # the mode the fit was made in

    session.import_results()

    assert dialogs['warning'] == []
    (shown,) = session.model.fit_results
    assert shown.r_squared == average_fit.r_squared
    _type_into(session, 'h0', '12')
    assert 'This fit was made on replicates A–C with [Host]₀ = 10 µM.' in session.model.hidden_results_note()


def test_import_of_a_file_written_before_the_arithmetic_marker_is_shown_as_stored(
    qapp, make_session, dialogs, monkeypatch
):
    """``unmarked_gda.json`` stores the scores of a less precise equilibrium solve.

    They reproduce at that solve's precision, so the fit is shown with the
    numbers the file holds and nothing to tell the user.
    """
    fixtures = Path(__file__).resolve().parents[2] / 'fixtures' / 'results'
    conditions = {'Ka_dye': 1e7, 'h0': 2e-7, 'g0': 2e-7}
    session = make_session()
    # with the GDA default bounds the file was made under
    state_binding(session, assay_type=AssayType.GDA, conditions=conditions, per_replica=False)
    session.model.load(MeasurementSet.from_dataframe(load_measurements(fixtures / 'unmarked_gda_data.txt')), None)
    monkeypatch.setattr(
        'gui.fitting_session.QFileDialog.getOpenFileName', lambda *args: (str(fixtures / 'unmarked_gda.json'), '')
    )

    session.import_results()

    assert dialogs['warning'] == []
    assert dialogs['information'] == []
    (shown,) = session.model.fit_results
    stored = json.loads((fixtures / 'unmarked_gda.json').read_text())
    assert (shown.rmse, shown.r_squared) == (stored['rmse'], stored['r_squared'])
    assert shown.intervals is None, 'a file written before intervals were reported carries none'


def test_import_of_a_released_per_replicate_file_says_why_its_numbers_changed(qapp, make_session, dialogs, monkeypatch):
    """``v150_pr_drop.json`` scored its numbers against a replicate the fit left out, so the app rebuilt them."""
    root = Path(__file__).resolve().parents[3]
    fixtures = root / 'tests' / 'fixtures' / 'results'
    session = make_session()
    # with the IDA default bounds the file was made under
    state_binding(session, assay_type=AssayType.IDA, conditions={'Ka_dye': 16.8e6, 'h0': 4.3e-6, 'd0': 6e-6})
    session.model.load(MeasurementSet.from_dataframe(load_measurements(root / 'data' / 'IDA_system.txt')), None)
    monkeypatch.setattr(
        'gui.fitting_session.QFileDialog.getOpenFileName', lambda *args: (str(fixtures / 'v150_pr_drop.json'), '')
    )

    session.import_results()

    assert dialogs['warning'] == []
    ((_, _, text),) = dialogs['information']
    assert text == (
        'Some numbers stored in v150_pr_drop.json did not describe the replicates each fit used, so the R², RMSE '
        'and curve were recomputed on those replicates.'
    )


def test_import_of_results_that_cannot_be_checked_on_the_loaded_data_says_so(
    qapp, make_session, fit, dialogs, monkeypatch, tmp_path
):
    """A file naming an arithmetic this version does not have is shown as stored, with a notice why."""
    later = fit.to_dict()
    later['metadata']['model_arithmetic'] = later['metadata']['model_arithmetic'] + 1
    session = make_session(_data())

    _import(session, monkeypatch, tmp_path, [FitResult.from_dict(later)])

    (shown,) = session.model.held_fit_results
    assert (shown.rmse, shown.r_squared) == (fit.rmse, fit.r_squared)
    ((_, title, text),) = dialogs['information']
    assert title == 'Imported Results'
    assert 'could not be checked against the data loaded now' in text
    assert 'shown as stored in the file' in text


def test_import_without_data_shows_the_stored_numbers_unchecked(
    qapp, make_session, fit, dialogs, monkeypatch, tmp_path
):
    from gui.results import UNCHECKED_NOTE

    session = make_session()

    _import(session, monkeypatch, tmp_path, [fit])

    (shown,) = session.model.fit_results
    assert shown.r_squared == fit.r_squared
    assert _shown(session)
    assert UNCHECKED_NOTE in [c.body for c in session._results.callouts]


def test_import_without_data_hides_a_fit_of_another_assay_type_and_labels_the_axes_for_the_fit(
    qapp, make_session, fit, dialogs, monkeypatch, tmp_path
):
    session = make_session()
    state_binding(session, assay_type=AssayType.GDA)

    _import(session, monkeypatch, tmp_path, [fit])

    assert session.model.fit_results == [] and _curves(session) == 0
    assert session.model.hidden_results_note().startswith('This fit was made for IDA.')

    # the form and the bounds come back as the defaults
    state_binding(session, assay_type=AssayType.IDA, bounds=GDA_IDA_RECOVERY_BOUNDS)
    for key, text in (('Ka_dye', '500000'), ('h0', '10'), ('d0', '5')):
        _type_into(session, key, text)

    assert len(session.model.fit_results) == 1
    assert _curves(session) == 1
    assert session._results.plot.pw.getPlotItem().getAxis('bottom').labelText.startswith('Guest')


# ---------------------------------------------------------------------------
# Several results
# ---------------------------------------------------------------------------


def test_one_hidden_result_leaves_the_shown_one_drawn_and_exportable(
    qapp, make_session, fit, average_fit, dialogs, monkeypatch, tmp_path
):
    """The fit of the average of A–C and the per-replicate fit on A and B: the replicate mode set shows one of them.

    Switching the mode over swaps which one is drawn; the other stays held, named in a note on the plot.
    """
    from gui.session import build_artefacts

    session = make_session(_data())  # fitting each replicate separately, as `fit` was made
    _import(session, monkeypatch, tmp_path, [average_fit, fit])

    (shown,) = session.model.fit_results
    assert shown.id == fit.id
    assert session.model.hidden_results_note() is None
    notes = {c.title: c.body for c in session._results.callouts if c.tone == 'neutral'}
    assert _curves(session) == 1 and _shown(session) and 'Results hidden' not in notes
    assert notes['Fits hidden'] == (
        '1 of the 2 fits is hidden and not drawn. This hidden fit was made on replicates A–C. Fitting each '
        'replicate separately is now switched on. Switch it back off, or run the fit again.'
    )
    artefacts = {artefact.key: artefact for artefact in build_artefacts(session)}
    assert all(artefacts[key].available for key in ('results_json', 'results_txt', 'results_csv'))

    state_binding(session, per_replica=False)

    (shown,) = session.model.fit_results
    assert shown.id == average_fit.id and _curves(session) == 1
    notes = {c.title: c.body for c in session._results.callouts}
    assert 'Fitting each replicate separately is now switched off. Switch it back on' in notes['Fits hidden']


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
    worker = session.model._fit_worker

    session.model.load(_data(), None)
    worker.wait()
    for _ in range(5):
        qapp.processEvents()

    assert not session.model.fit_running()
    assert session.model.held_fit_results == []
    assert not _shown(session)
    assert dialogs['warning'] == []


def test_importing_results_is_refused_while_a_fit_runs(
    qapp, make_session, fit, dialogs, slow_fit, monkeypatch, tmp_path
):
    """The running fit would replace the imported results the moment it finished, without a word."""
    session = make_session(_data())
    session.run_fit()

    _import(session, monkeypatch, tmp_path, [fit])

    ((_, title, text),) = dialogs['warning']
    assert title == 'Fit Running'
    assert text == (
        'A fit is running in this session, and its result would replace the imported results when it finishes. '
        'Wait for it to finish, or stop it with Stop, then import the results.'
    )
    assert session.model.held_fit_results == []
    _wait_until(qapp, lambda: not session.model.fit_running())


def test_the_status_bar_keeps_saying_that_too_few_replicates_were_tested(qapp, make_session, fit, dialogs, slow_fit):
    """With two replicates the replicate test cannot run: the start and the end of the fit both say so."""
    session = make_session(_data())
    _toggle(session, 'c', False)
    messages: list[str] = []
    session.model.status_changed.connect(messages.append)

    session.run_fit()

    assert messages[-1] == (
        'Fitting 2 replicates — too few to test against each other (the test needs three), so all of them are used…'
    )
    session.model.shutdown()

    two = copy.deepcopy(fit)  # the per-replicate fit of A and B, as the pipeline records it
    two.metadata['active_replica_ids'] = two.metadata['replica_ids_fit'] = ['a', 'b']
    for key in ('replica_failures', 'replicate_test'):
        two.metadata.pop(key, None)
    _deliver(session, two)

    assert messages[-1].startswith('Fit complete — ')
    assert '2 of 3 replicates used, too few to test against each other' in messages[-1]
    # One label, one number: Fit details counts the same replicates against the same loaded ones.
    from gui.results import quality

    assert f'{quality(two, session.model.measurement_set).used} replicates used' in messages[-1]


def test_a_fit_finishing_after_a_used_replicate_was_switched_off_is_held_hidden_and_profiled_on_its_record(
    qapp, make_session, dialogs, slow_fit
):
    session = make_session(_data())
    session.run_fit()
    messages: list[str] = []
    session.model.status_changed.connect(lambda text: messages.append(text) if text.startswith('Fit') else None)

    _toggle(session, 'b', False)
    _wait_until(qapp, lambda: session.model.profile is not None)

    assert slow_fit[0].active_replica_ids == ['a', 'b', 'c']
    (held,) = session.model.held_fit_results
    assert session.model.fit_results == []
    assert session.model.hidden_results_note().startswith(
        'This fit was made on replicates A and B. Replicate B is now off.'
    )
    profile = session.model.profile.profiles['Ka_guest']
    # Profiled on the replicates the fit used, with its weights: the profile's best fit is the fit's.
    assert profile.best_ka == pytest.approx(held.parameters['Ka_guest'].magnitude, rel=1e-9)
    assert messages == [f'Fit complete but hidden — {session.model.hidden_results_note()}']


def test_a_finished_fit_names_the_replicates_it_left_out_and_why(qapp, make_session, dialogs, slow_fit):
    """Minutes of data must not be dropped without a word — the no-silent-fallbacks rule."""
    session = make_session(_data())
    messages: list[str] = []
    session.model.status_changed.connect(
        lambda text: messages.append(text) if text.startswith('Fit complete') else None
    )

    session.run_fit()
    _wait_until(qapp, lambda: session.model.profile is not None)

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
    from gui.plotting.labels import verdict_sentence
    from gui.session_model import _verdict_note

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


def test_a_new_fit_replaces_the_previous_one_in_ka_confidence_before_its_profile_arrives(
    qapp, make_session, fit, dialogs
):
    """The readings of the new fit show at once, the curves of the old one never stand beside them."""
    from gui import confidence as CF

    session = _shown_session(qapp, make_session, fit)
    confidence = session._confidence
    assert confidence.has_plot()
    second = copy.deepcopy(fit)
    second.id = 'second-fit'

    _deliver(session, second)

    assert not confidence.has_plot() and not confidence.header_host.isHidden()
    assert any(c.body == CF.PENDING for c in confidence.callouts)
    _wait_until(qapp, lambda: session.model.profile is not None)
    assert session.model.profiled_fit is second and confidence.has_plot()
    assert all(c.body != CF.PENDING for c in confidence.callouts)


def test_the_primary_action_offers_stop_while_a_fit_runs(qapp, dialogs, slow_fit, monkeypatch):
    """The toolbar's one primary action stops the running fit; a second fit is refused while it is still going."""
    from gui.main_window import FittingMainWindow

    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    window = FittingMainWindow()
    session = window.active_session()
    state_binding(session, assay_type=AssayType.IDA)
    session.model.load(_data(), None)

    session.run_fit()
    worker = session.model._fit_worker
    assert window._act_run.text() == 'Stop' and window._act_run.isEnabled()
    session.run_fit()
    assert session.model._fit_worker is worker and len(slow_fit) <= 1
    assert dialogs['warning'][-1][1] == 'Already Running'
    assert dialogs['warning'][-1][2].startswith('A fit is already running in this session.')

    _wait_until(qapp, lambda: not session.model.running())
    assert window._act_run.text() == 'Run fit' and window._act_run.isEnabled()
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
        assert 'broadcast' not in message and message.startswith('The fit stopped on an unexpected error')


def test_a_dilution_difference_without_data_reads_as_a_sentence(
    qapp, make_session, diluted_fit, dialogs, monkeypatch, tmp_path
):
    """The dilution names no value the fit was made with, so with nothing else differing the note is the change."""
    session = make_session()

    _import(session, monkeypatch, tmp_path, [diluted_fit])

    assert session.model.hidden_results_note() == (
        'The dilution by the titrant is now switched off. Switch it back on, or run the fit again.'
    )
