"""The session model's rules, driven with no widget at all.

A held fit is shown only while the loaded data and the settings match the
record it was made on; the conditions are checked once their edit is finished,
every other setting as it changes. New data clears the results and stops the
work running on the old data, a cancelled fit leaves the previous result as it
was, the session is named after its data unless the user named it, and a run
that cannot start says why in the words a dialog shows.

One fit of the IDA ground truth is made per module and held the way an import
holds it.
"""

from __future__ import annotations

import copy
import time

import numpy as np
import pytest

pytest.importorskip('PyQt6')

from core.assays.ida import IDAAssay  # noqa: E402
from core.assays.registry import AssayType  # noqa: E402
from core.data_processing.measurement_set import MeasurementSet  # noqa: E402
from core.pipeline.fit_pipeline import FitConfig, FitResult, fit_measurement_set  # noqa: E402
from core.pipeline.varpro import FitCancelled  # noqa: E402
from core.units import Q_  # noqa: E402
from tests.conftest import GDA_IDA_RECOVERY_BOUNDS, IDA_TRUE, _make_ida_data  # noqa: E402

_CONDITIONS = {
    'Ka_dye': Q_(IDA_TRUE['Ka_dye'], '1/M'),
    'h0': Q_(IDA_TRUE['h0'], 'M'),
    'd0': Q_(IDA_TRUE['d0'], 'M'),
}


def _data() -> MeasurementSet:
    """Three replicates of the IDA ground truth with 1 % noise."""
    rng = np.random.default_rng(0)
    x, y = _make_ida_data(IDA_TRUE, n_points=20)
    signals = np.vstack([y * (1 + 0.01 * rng.standard_normal(y.size)) for _ in range(3)])
    return MeasurementSet(concentrations=x, signals=signals, replica_ids=('a', 'b', 'c'))


@pytest.fixture(scope='module')
def fitted() -> FitResult:
    """A fit of the average of the replicates, inputs taken as exact."""
    config = FitConfig(per_replica=False, custom_bounds=GDA_IDA_RECOVERY_BOUNDS)
    return fit_measurement_set(_data(), IDAAssay, _CONDITIONS, config)


@pytest.fixture
def make_model(qapp):
    """Build models set up as the fit was made; on teardown stop what they still run."""
    from gui.session_model import SessionModel

    models = []

    def build():
        model = SessionModel()
        _state(model, _CONDITIONS, per_replica=False)
        models.append(model)
        return model

    yield build
    for model in models:
        model.shutdown()


@pytest.fixture
def watchful_fit(monkeypatch):
    """Stand in for the fit with a run that only watches its cancel flag."""
    from gui import workers

    def run(ms, assay_cls, conditions, config, should_cancel=None, **kwargs):
        while not should_cancel():
            time.sleep(0.005)
        raise FitCancelled('The fit was cancelled.')

    monkeypatch.setattr(workers, 'fit_measurement_set', run)


def _state(model, conditions, *, per_replica=None, finished=True) -> None:
    """State the IDA model with *conditions* and the bounds the fit was made under, as Binding model does."""
    form = model.binding
    form.choose_model(AssayType.IDA)
    for key, value in conditions.items():
        form.set_value(key, value.to(form.entry(key).field.unit).magnitude)
    for key, (lo, hi) in GDA_IDA_RECOVERY_BOUNDS.items():
        form.set_bounds(key, lo.magnitude, hi.magnitude)
    if per_replica is not None:
        form.set_per_replica(per_replica)
    model.binding_edited(finished)


def _holding(make_model, fit: FitResult):
    """A model with the fit's data loaded and the fit held."""
    model = make_model()
    model.load(_data(), '/data/ida.txt')
    model.show_imported([fit], 'results.json')
    assert model.fit_results == [fit]
    return model


def _wait_until(qapp, condition, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, 'timed out waiting'
        qapp.processEvents()
        time.sleep(0.005)


def test_a_condition_hides_the_fit_once_its_edit_is_finished_and_setting_it_back_shows_it_again(make_model, fitted):
    model = _holding(make_model, fitted)

    _state(model, {**_CONDITIONS, 'h0': Q_(5e-6, 'M')}, finished=False)
    assert model.fit_results == [fitted], 'hidden while the value is still being typed'

    model.edit_finished()
    assert model.fit_results == [] and model.held_fit_results == [fitted]
    # Written in the unit the field shows: 10 µM, not 1×10⁻⁵ M.
    assert model.hidden_results_note() == (
        'This fit was made on replicates A–C with [Host]₀ = 10 µM. [Host]₀ is now 5 µM. '
        'Set it back to 10 µM, or run the fit again.'
    )

    _state(model, _CONDITIONS, finished=False)
    model.edit_finished()
    (shown,) = model.fit_results
    assert shown is fitted and model.hidden_results_note() is None


def test_the_replicate_mode_hides_the_fit_as_soon_as_it_changes(make_model, fitted):
    model = _holding(make_model, fitted)

    _state(model, {}, per_replica=True)

    assert model.fit_results == []
    assert 'Fitting each replicate separately is now switched on.' in model.hidden_results_note()
    assert model.status == 'Results hidden — they do not describe the data and settings loaded now.'


def test_loading_data_clears_the_results_and_stops_the_running_fit(qapp, make_model, fitted, watchful_fit):
    model = _holding(make_model, fitted)
    assert model.run_fit() is None
    worker = model._fit_worker
    _wait_until(qapp, worker.isRunning)

    model.load(_data(), '/data/other.txt')

    assert not model.fit_running() and worker.cancelled and worker.isFinished()
    assert model.held_fit_results == [] and model.fit_view() == (None, None)
    assert model.status.endswith('— the running fit was stopped')


def test_a_cancelled_fit_leaves_the_previous_result_as_it_was(qapp, make_model, fitted, watchful_fit):
    model = _holding(make_model, fitted)
    from gui.session_model import Change

    redraws: list[Change] = []
    model.changed.connect(lambda what: redraws.append(what) if Change.RESULTS in what else None)
    assert model.run_fit() is None
    worker = model._fit_worker
    _wait_until(qapp, worker.isRunning)

    model.cancel_fit()
    # A result the stopped run might still send reaches nothing.
    worker.finished.emit(copy.deepcopy(fitted))
    qapp.processEvents()

    assert not model.fit_running()
    (shown,) = model.fit_results
    assert shown is fitted and redraws == []
    assert model.status == 'Fit stopped — nothing in the session was changed.'


def test_the_session_is_named_by_the_user_else_by_its_data_file(make_model):
    model = make_model()
    from gui.session_model import Change

    names: list[str] = []
    model.changed.connect(lambda what: names.append(model.name()) if Change.NAME in what else None)
    assert model.name() == 'New session'

    model.load(_data(), '/data/tryptamine_424.txt')
    assert names[-1] == 'tryptamine_424'

    model.set_custom_name('Control run')
    model.load(_data(), '/data/other.csv')
    assert names[-1] == 'Control run', 'a name the user gave outlasts new data'

    model.set_custom_name('   ')
    assert names[-1] == 'other'

    model.clear()
    assert names[-1] == 'New session'


def test_a_fit_that_cannot_start_says_why(make_model):
    from gui.session_model import Refusal

    model = make_model()
    assert model.run_fit() == Refusal('No Data', 'Load a measurement file first.')

    ms = _data()
    model.load(ms, '/data/ida.txt')
    highest = float(ms.concentrations.max())
    model.binding.set_diluted(True)
    _state(model, {'titrant_stock': Q_(highest / 2, 'M')})

    refusal = model.run_fit()

    assert not model.fit_running()
    assert refusal.title == 'Binding model'
    # Both concentrations in the unit the stock's field shows.
    stock, top = (f'{value * 1e6:.4g} µM' for value in (highest / 2, highest))
    assert f'The titrant stock ({stock}) must be more concentrated than the highest titrant' in refusal.message
    assert f'in the data ({top})' in refusal.message


def test_the_switcher_line_reports_the_shown_ka_and_counts_the_warnings_of_its_verdict(make_model, fitted):
    from dataclasses import replace

    from core.pipeline.diagnostics import FitDiagnostics, Verdict

    ka = fitted.parameters['Ka_guest'].magnitude
    mantissa, exponent = f'{ka:.2e}'.split('e')
    model = _holding(make_model, fitted)
    state, words, _ = model.summary()
    assert words.startswith(f'Ka {mantissa}') and words.endswith('M⁻¹')
    assert str(int(exponent)).translate(str.maketrans('0123456789', '⁰¹²³⁴⁵⁶⁷⁸⁹')) in words

    for verdict, expected in (
        (Verdict.CONSISTENT, ('done', '')),
        (Verdict.INPUTS_CONFLICT, ('warning', ' · 1 warning')),
        (Verdict.MODEL_AND_INPUTS, ('warning', ' · 2 warnings')),
    ):
        diagnostics = FitDiagnostics(conditional_misfit=None, misfit=None, conflict=None, verdict=verdict)
        model = _holding(make_model, replace(fitted, diagnostics=diagnostics))
        state, words, _ = model.summary()
        assert (state, words[len(words.split(' · ')[0]) :]) == expected
        assert model.view_status('Fit results')[0] == expected[0]


def test_a_fit_that_needs_a_refit_is_marked_out_of_date_everywhere(make_model, fitted):
    model = _holding(make_model, fitted)

    _state(model, {}, per_replica=True)

    assert model.summary()[:2] == ('stale', 'Needs refit')
    assert model.view_status('Fit results') == ('stale', 0.0)
    assert model.view_status('Measurements') == ('done', 0.0)


def test_a_new_session_reads_as_empty(make_model):
    model = make_model()

    assert model.name() == 'New session'
    assert model.detail() == 'No data loaded'
    assert model.summary()[:2] == ('', '')
    assert all(model.view_status(view) == ('', 0.0) for view in ('Measurements', 'Fit results', 'Sensitivity'))


def test_the_file_card_and_the_model_line_describe_the_loaded_data_and_the_model(make_model):
    model = make_model()
    model.load(_data(), '/data/ida.txt')

    assert model.detail() == 'IDA · 3 replicates'
    assert model.file_card() == ('ida.txt', 'IDA · 3 replicates × 20 points')
    assert model.model_line()[:2] == ['Indicator displacement', '1 binding constant']


def test_the_model_line_names_a_calibration_as_the_badge_does_and_claims_no_interval(make_model):
    """Dye alone fits a straight line: no binding constant, so no profile-likelihood interval either."""
    model = make_model()
    model.binding.choose_model(AssayType.DYE_ALONE)
    model.binding_edited()

    assert model.model_line() == ['Dye alone', 'no binding constant']
    assert model.binding.badge() == 'Dye alone · no binding constant'


def test_stop_ends_a_running_fit_and_leaves_the_shown_one(qapp, make_model, fitted, watchful_fit):
    model = _holding(make_model, fitted)
    assert model.run_fit() is None
    assert model.summary()[:2] == ('running', 'Fitting')
    assert model.view_status('Fit results')[0] == 'running'

    model.stop()

    assert not model.running()
    assert model.fit_results == [fitted]


def test_a_waiting_conversion_is_made_against_the_condition_once_its_edit_is_finished(make_model):
    """Keystroke by keystroke the condition reads 4 then 45 µM; the σ of 5 % waiting for it is 5 % of 45 µM."""
    from core.pipeline.inputs import InputSpec, SpecKind

    model = make_model()
    model.uncertainty.set_spec('h0', InputSpec.sigma_pct(5.0))
    model.binding.edit('h0', '')
    model.binding_edited(False)
    model.uncertainty.state_in('h0', False)
    model.uncertainty_edited()

    for text in ('4', '45'):
        model.binding.edit('h0', text)
        model.binding_edited(False)
    assert model.uncertainty.spec('h0') is None, 'nothing is converted against a value still being typed'
    assert model.settings.input_problems

    model.edit_finished()
    spec = model.uncertainty.spec('h0')
    assert (spec.kind, spec.relative) == (SpecKind.SIGMA, False)
    assert spec.sigma == pytest.approx(0.05 * 45e-6, rel=1e-12)
    assert model.settings.input_problems == ()
    assert model.settings.errors.specs['h0'] == spec
