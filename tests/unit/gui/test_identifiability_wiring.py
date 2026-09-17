"""Wiring tests: the Identifiability tab follows fits, Ka profiles, sensitivity runs and data changes.

Require a ``QApplication`` (the ``qapp`` fixture). Background workers are
awaited by pumping the event loop until the expected call arrives.
"""

import time

import numpy as np
import pytest

pytest.importorskip('PyQt6')

from PyQt6.QtCore import QThread  # noqa: E402

from core.assays.registry import AssayType  # noqa: E402
from core.data_processing.measurement_set import MeasurementSet  # noqa: E402
from core.pipeline.fit_pipeline import FitConfig  # noqa: E402
from core.pipeline.profile import ProfileResult  # noqa: E402
from tests.conftest import DYE_ALONE_TRUE, IDA_TRUE, _make_dye_alone_data, _make_ida_data  # noqa: E402
from tests.unit.gui.test_sensitivity_gui import _sobol_result  # noqa: E402

TAB_ORDER = ['Fit Curve', 'Distributions', 'Identifiability', 'Ka Sensitivity']

#: Fit seed every session here runs with, so each fit is the same one each time.
_FIT_SEED = 42


def _ida_set(noise_seed: int = 0) -> MeasurementSet:
    """Three IDA replicates with 1% multiplicative noise around the shared ground truth."""
    rng = np.random.default_rng(noise_seed)
    x, y = _make_ida_data(IDA_TRUE, n_points=20)
    signals = np.vstack([y * (1 + 0.01 * rng.standard_normal(y.size)) for _ in range(3)])
    return MeasurementSet(concentrations=x, signals=signals, replica_ids=('A', 'B', 'C'))


def _spy(widget, name: str) -> list[tuple]:
    """Record every call the session makes to ``widget.<name>`` (the call still goes through)."""
    calls: list[tuple] = []
    original = getattr(widget, name)

    def record(*args):
        calls.append(args)
        original(*args)

    setattr(widget, name, record)
    return calls


def _wait_until(qapp, condition, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, 'timed out waiting for a background worker'
        qapp.processEvents()
        time.sleep(0.01)


@pytest.fixture
def warnings(monkeypatch):
    """Record warning dialogs instead of blocking on them."""
    shown: list[tuple] = []
    monkeypatch.setattr('gui.fitting_session.QMessageBox.warning', lambda *args: shown.append(args))
    return shown


@pytest.fixture
def make_session(qapp):
    """Build FittingSessions; on teardown wait for their worker threads so none is destroyed while running."""
    from gui.fitting_session import FittingSession

    sessions = []

    def build(assay_type: AssayType, ms: MeasurementSet, conditions: dict | None = None, *, per_replica=False):
        session = FittingSession()
        session._assay_panel.set_assay_type(assay_type)
        for key, value in (conditions or {}).items():
            session._assay_panel._field_widgets[key].setValue(value)
        # A fixed seed in the panel: Run Fit draws its own seed otherwise, so the
        # starting points — and with them whether a trial clears the quality
        # floor — would differ from run to run.
        session._fit_panel.set_config(FitConfig(per_replica=per_replica, seed=_FIT_SEED))
        session._data_panel.data_loaded.emit(ms)
        sessions.append(session)
        return session

    yield build
    for session in sessions:
        for thread in session.findChildren(QThread):
            thread.wait()
    qapp.processEvents()


def _ida_session(make_session, *, per_replica=False):
    conditions = {k: IDA_TRUE[k] for k in ('Ka_dye', 'h0', 'd0')}
    return make_session(AssayType.IDA, _ida_set(), conditions, per_replica=per_replica)


def test_plot_tabs_in_contract_order(make_session):
    from gui.plotting.identifiability_widget import IdentifiabilityWidget

    session = _ida_session(make_session)
    tabs = session._plot_tabs
    assert [tabs.tabText(i) for i in range(tabs.count())] == TAB_ORDER
    assert isinstance(tabs.widget(2), IdentifiabilityWidget)


def test_style_changes_reach_identifiability_tab(make_session):
    session = _ida_session(make_session)
    style = dict(session._identifiability_widget._style)
    session._style_widget.widget.style_changed.emit(style)
    assert session._identifiability_widget._style is style


@pytest.mark.parametrize('per_replica', [False, True])
def test_fit_then_profile_reach_identifiability_tab(qapp, make_session, warnings, per_replica):
    """The tab gets the fit together with the Ka profile of exactly that fit's inputs."""
    session = _ida_session(make_session, per_replica=per_replica)
    calls = _spy(session._identifiability_widget, 'update_fit')

    session.run_fit()
    _wait_until(qapp, lambda: calls or warnings)

    assert warnings == []
    ((result, profile, assay_type_name),) = calls
    assert result is session._state.fit_results[-1]
    assert assay_type_name == 'IDA'
    assert isinstance(profile, ProfileResult)
    assert profile is session._state.profile_result
    assert profile.per_replica is per_replica
    # The profile was computed from the fit's own inputs: its interval holds both
    # the fitted Ka and the ground truth the data were simulated with.
    fitted_ka = result.parameters['Ka_guest'].to('1/M').magnitude
    assert profile.ci[0] <= fitted_ka <= profile.ci[1]
    assert profile.ci[0] < IDA_TRUE['Ka_guest'] < profile.ci[1]
    widget = session._identifiability_widget
    assert widget._stack.currentWidget() is widget._content


def test_profile_leaves_out_the_replicates_the_fit_skipped(qapp, make_session, warnings):
    """A replicate the per-replicate fit excluded is left out of its Ka profile too.

    Replicate C is pure noise, so none of its fits reaches the quality floor and
    the fit skips it. The profile covers A and B, and the session's own data
    keep C active.
    """
    clean = _ida_set()
    signals = clean.signals.copy()
    signals[2] = np.random.default_rng(1).normal(signals[2].mean(), signals[2].std(), signals[2].size)
    ms = MeasurementSet(concentrations=clean.concentrations, signals=signals, replica_ids=clean.replica_ids)
    conditions = {k: IDA_TRUE[k] for k in ('Ka_dye', 'h0', 'd0')}
    session = make_session(AssayType.IDA, ms, conditions, per_replica=True)
    calls = _spy(session._identifiability_widget, 'update_fit')

    session.run_fit()
    _wait_until(qapp, lambda: calls)

    ((result, profile, _),) = calls
    assert list(result.metadata['replica_failures']) == ['C']
    assert set(profile.replica_r2) == {'A', 'B'}
    assert session._state.measurement_set.is_active('C')


def test_unsupported_assay_gets_fit_without_profile(qapp, make_session, warnings):
    """An assay without a single binding constant is shown at once, with no profile computed."""
    x, y = _make_dye_alone_data(DYE_ALONE_TRUE)
    ms = MeasurementSet(concentrations=x, signals=np.vstack([y, y * 1.001]), replica_ids=('A', 'B'))
    session = make_session(AssayType.DYE_ALONE, ms)
    calls = _spy(session._identifiability_widget, 'update_fit')

    session.run_fit()
    _wait_until(qapp, lambda: calls or warnings)

    assert warnings == []
    ((result, profile, assay_type_name),) = calls
    assert result is session._state.fit_results[-1]
    assert profile is None
    assert assay_type_name == 'DYE_ALONE'
    assert session._profile_worker is None
    assert session._state.profile_result is None


def test_sensitivity_result_reaches_identifiability_tab(make_session):
    session = _ida_session(make_session)
    calls = _spy(session._identifiability_widget, 'update_sensitivity')
    result = _sobol_result()

    session._on_sensitivity_complete(result)

    assert calls == [(result,)]


def test_loading_data_clears_tab_and_discards_pending_profile(qapp, make_session, warnings):
    """New data empties the tab, and a profile still computing for the old fit is never shown."""
    session = _ida_session(make_session)
    widget = session._identifiability_widget
    fits = _spy(widget, 'update_fit')
    clears = _spy(widget, 'clear')

    session.run_fit()
    _wait_until(qapp, lambda: session._profile_worker is not None or warnings)
    pending = session._profile_worker
    assert fits == []  # the profile of the finished fit is still being computed

    session._data_panel.data_loaded.emit(_ida_set(noise_seed=1))
    pending.wait()
    for _ in range(5):
        qapp.processEvents()

    assert warnings == []
    assert clears == [()]
    assert fits == []
    assert session._state.profile_result is None
    assert widget._stack.currentWidget() is widget._message
