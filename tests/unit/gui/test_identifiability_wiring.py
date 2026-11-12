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
from core.pipeline.profile import ProfileSet  # noqa: E402
from tests.conftest import DYE_ALONE_TRUE, IDA_TRUE, _make_dye_alone_data, _make_ida_data  # noqa: E402
from tests.unit.gui.test_identifiability_gui import _fit  # noqa: E402
from tests.unit.gui.test_sensitivity_gui import _sobol_result  # noqa: E402


def _ida_signals(true: dict, noise_seed: int, n_replicates: int) -> tuple[np.ndarray, np.ndarray]:
    """Replicates of one IDA ground truth with 1 % multiplicative noise."""
    rng = np.random.default_rng(noise_seed)
    x, y = _make_ida_data(true, n_points=20)
    return x, np.vstack([y * (1 + 0.01 * rng.standard_normal(y.size)) for _ in range(n_replicates)])


def _ida_set(noise_seed: int = 0) -> MeasurementSet:
    """Three IDA replicates with 1 % multiplicative noise around the shared ground truth."""
    x, signals = _ida_signals(IDA_TRUE, noise_seed, 3)
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
        session._fit_panel.set_config(FitConfig(per_replica=per_replica))
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


def test_the_identifiability_tab_is_one_of_the_plot_tabs(make_session):
    """The tab is offered under its own name, so the wiring below has somewhere to reach."""
    from gui.plotting.identifiability_widget import IdentifiabilityWidget

    session = _ida_session(make_session)
    tabs = session._plot_tabs
    names = [tabs.tabText(i) for i in range(tabs.count())]
    assert isinstance(tabs.widget(names.index('Identifiability')), IdentifiabilityWidget)


def test_the_tab_names_a_shifted_input_from_the_fit_s_own_assay(make_session):
    """The names belong to the fit being reported, so switching the assay selector cannot rename its inputs."""
    from core.pipeline.diagnostics import FitDiagnostics, InputShift, MisfitTest, Verdict

    session = _ida_session(make_session)
    widget = session._identifiability_widget
    widget._fit = _fit(
        shifts={'h0': InputShift(key='h0', fraction=-0.041, z=-1.4, at_edge=False)},
        diagnostics=FitDiagnostics(
            conditional_misfit=MisfitTest(kind='runs', statistic=4.0, p_value=0.004, expected=7.0),
            misfit=MisfitTest(kind='runs', statistic=7.0, p_value=0.55, expected=7.0),
            conflict=None,
            verdict=Verdict.INPUTS_EXPLAIN,
        ),
    )

    assert '[Host]₀ −4.1 % (1.4 σ)' in widget._verdict_html()

    session._assay_panel.set_assay_type(AssayType.GDA)
    assert '[Host]₀ −4.1 % (1.4 σ)' in widget._verdict_html()


def test_style_changes_reach_identifiability_tab(make_session):
    session = _ida_session(make_session)
    style = dict(session._identifiability_widget._style)
    session._style_widget.widget.style_changed.emit(style)
    assert session._identifiability_widget._style is style


@pytest.mark.parametrize('per_replica', [False, True])
def test_fit_then_profile_reach_identifiability_tab(qapp, make_session, warnings, per_replica):
    """The tab gets the fit together with the Ka profiles of exactly that fit's inputs."""
    session = _ida_session(make_session, per_replica=per_replica)
    calls = _spy(session._identifiability_widget, 'update_fit')

    session.run_fit()
    _wait_until(qapp, lambda: calls or warnings)

    assert warnings == []
    ((result, profile_set, assay_type_name),) = calls
    assert result is session.model.fit_results[-1]
    assert assay_type_name == 'IDA'
    assert isinstance(profile_set, ProfileSet)
    assert profile_set is session._identifiability_widget._profile
    profile = profile_set.profiles['Ka_guest']
    assert profile.per_replica is per_replica
    # The profile was computed from the fit's own inputs: its interval is the
    # one the fit reports, and it holds the ground truth the data were simulated
    # with.
    reported = result.intervals['Ka_guest']
    assert (profile.interval.low, profile.interval.high) == (reported.low, reported.high)
    assert profile.best_ka == pytest.approx(result.parameters['Ka_guest'].to('1/M').magnitude)
    assert profile.interval.low < IDA_TRUE['Ka_guest'] < profile.interval.high
    widget = session._identifiability_widget
    assert widget._stack.currentWidget() is widget._content


def test_profile_leaves_out_the_replicates_the_fit_skipped(qapp, make_session, warnings):
    """A replicate the per-replicate fit excluded is left out of its Ka profile too.

    Replicate C follows a binding constant three times the one A and B share, so
    the shared-Ka test drops it from the average. The profile covers A and B,
    and the session's own data keep C active.
    """
    x, signals = _ida_signals(IDA_TRUE, 0, 2)
    _, odd = _ida_signals({**IDA_TRUE, 'Ka_guest': 3 * IDA_TRUE['Ka_guest']}, 1, 1)
    ms = MeasurementSet(concentrations=x, signals=np.vstack([signals, odd]), replica_ids=('A', 'B', 'C'))
    conditions = {k: IDA_TRUE[k] for k in ('Ka_dye', 'h0', 'd0')}
    session = make_session(AssayType.IDA, ms, conditions, per_replica=True)
    calls = _spy(session._identifiability_widget, 'update_fit')

    session.run_fit()
    _wait_until(qapp, lambda: calls or warnings)

    assert warnings == []
    ((result, profile_set, _),) = calls
    assert list(result.metadata['replica_failures']) == ['C']
    assert set(profile_set.profiles['Ka_guest'].replica_r2) == {'A', 'B'}
    assert session.model.measurement_set.is_active('C')
    assert 'Replicate C is left out' in session._identifiability_widget._notes.text()


def test_an_assay_without_a_binding_constant_gets_no_profile(qapp, make_session, warnings):
    """A dye-alone fit is shown at once, with no profile computed."""
    x, y = _make_dye_alone_data(DYE_ALONE_TRUE)
    ms = MeasurementSet(concentrations=x, signals=np.vstack([y, y * 1.001]), replica_ids=('A', 'B'))
    session = make_session(AssayType.DYE_ALONE, ms)
    calls = _spy(session._identifiability_widget, 'update_fit')

    session.run_fit()
    _wait_until(qapp, lambda: calls or warnings)

    assert warnings == []
    ((result, profile_set, assay_type_name),) = calls
    assert result is session.model.fit_results[-1]
    assert profile_set is None
    assert assay_type_name == 'DYE_ALONE'
    assert session.model._profile_worker is None
    assert session._identifiability_widget._profile is None


def test_sensitivity_result_reaches_identifiability_tab(make_session):
    session = _ida_session(make_session)
    calls = _spy(session._identifiability_widget, 'update_sensitivity')
    result = _sobol_result()

    session.model._on_sensitivity_complete(result)

    assert calls == [(result,)]


def test_loading_data_clears_tab_and_discards_pending_profile(qapp, make_session, warnings):
    """New data empties the tab, and a profile still computing for the old fit is never shown."""
    session = _ida_session(make_session)
    widget = session._identifiability_widget
    fits = _spy(widget, 'update_fit')
    clears = _spy(widget, 'clear')

    session.run_fit()
    _wait_until(qapp, lambda: session.model._profile_worker is not None or warnings)
    pending = session.model._profile_worker
    assert fits == []  # the profiles of the finished fit are still being computed

    session._data_panel.data_loaded.emit(_ida_set(noise_seed=1))
    pending.wait()
    for _ in range(5):
        qapp.processEvents()

    assert warnings == []
    assert clears == [()]
    assert fits == []
    assert widget._profile is None
    assert widget._stack.currentWidget() is widget._message
