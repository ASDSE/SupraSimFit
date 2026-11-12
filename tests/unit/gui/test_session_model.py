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

#: The units the conditions form shows by default, which the notes write the conditions in.
_UNITS = {'Ka_dye': 'M⁻¹', 'h0': 'µM', 'd0': 'µM', 'titrant_stock': 'µM'}


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
        model.update_settings(
            assay_type=AssayType.IDA, conditions=dict(_CONDITIONS), condition_units=_UNITS, per_replica=False
        )
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

    model.update_settings(conditions={**_CONDITIONS, 'h0': Q_(5e-6, 'M')})
    assert model.fit_results == [fitted], 'hidden while the value is still being typed'

    model.edit_finished()
    assert model.fit_results == [] and model.held_fit_results == [fitted]
    # Written in the unit the field shows: 10 µM, not 1×10⁻⁵ M.
    assert model.hidden_results_note() == (
        'This fit was made on replicates A–C with [Host]₀ = 10 µM. [Host]₀ is now 5 µM. '
        'Set it back to 10 µM, or run the fit again.'
    )

    model.update_settings(conditions=dict(_CONDITIONS))
    model.edit_finished()
    (shown,) = model.fit_results
    assert shown is fitted and model.hidden_results_note() is None


def test_the_replicate_mode_hides_the_fit_as_soon_as_it_changes(make_model, fitted):
    model = _holding(make_model, fitted)

    model.update_settings(per_replica=True)

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
    redraws: list[str] = []
    model.results_changed.connect(redraws.append)
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
    assert model.status == 'Fit cancelled — nothing on the tab was changed.'


def test_the_session_is_named_by_the_user_else_by_its_data_file(make_model):
    model = make_model()
    names: list[str] = []
    model.name_changed.connect(names.append)
    assert model.name() == 'Untitled'

    model.load(_data(), '/data/tryptamine_424.txt')
    assert names[-1] == 'tryptamine_424'

    model.set_custom_name('Control run')
    model.load(_data(), '/data/other.csv')
    assert names[-1] == 'Control run', 'a name the user gave outlasts new data'

    model.set_custom_name('   ')
    assert names[-1] == 'other'

    model.clear()
    assert names[-1] == 'Untitled'


def test_a_fit_that_cannot_start_says_why(make_model):
    from gui.session_model import Refusal

    model = make_model()
    assert model.run_fit() == Refusal('No Data', 'Load a measurement file first.')

    ms = _data()
    model.load(ms, '/data/ida.txt')
    highest = float(ms.concentrations.max())
    model.update_settings(conditions={**_CONDITIONS, 'titrant_stock': Q_(highest / 2, 'M'), 'stock_contains': ()})

    refusal = model.run_fit()

    assert not model.fit_running()
    assert refusal.title == 'Assay Configuration'
    # Both concentrations in the unit the stock's field shows.
    stock, top = (f'{value * 1e6:.4g} µM' for value in (highest / 2, highest))
    assert f'The titrant stock ({stock}) must be more concentrated than the highest titrant' in refusal.message
    assert f'in the data ({top})' in refusal.message
