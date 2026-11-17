"""The session model is consistent whenever it says it changed, and says so once per edit.

An edit of the data — a replicate switched off, outlier removal, a file added
or removed, the replicates reset, another session copied — changes which held
fits describe the loaded data. Every view draws the shown fits over the active
replicates, and :func:`core.data_processing.plotting.prepare_plot_data` refuses
a fit whose replicates are not active: a view told of the edit before the
held fits were checked against it raises in its slot and is left half drawn.

The sequences are the ones that raised in the app: the IDA demo, fitted with
replicate 0 left out by its outlier filter, then outlier removal at 2.6
switching off the replicates 1, 2 and 7 the fit used; a fit of all eight with
replicate 0 switched off; and the file a fit used removed.
"""

from __future__ import annotations

import copy
import sys
import uuid
from pathlib import Path

import pytest

pytest.importorskip('PyQt6')

from PyQt6.QtCore import QMetaMethod  # noqa: E402

from core.assays.ida import IDAAssay  # noqa: E402
from core.assays.registry import AssayType  # noqa: E402
from core.data_processing.measurement_set import MeasurementSet  # noqa: E402
from core.io import load_measurements  # noqa: E402
from core.pipeline.fit_pipeline import FitConfig, fit_measurement_set  # noqa: E402
from core.pipeline.reporting import fit_replica_ids  # noqa: E402
from core.units import Q_  # noqa: E402
from tests.unit.gui.session_setup import state_binding  # noqa: E402

_DEMO = str(Path(__file__).resolve().parents[3] / 'data' / 'IDA_system.txt')
_CONDITIONS = {'h0': Q_(4.3e-6, 'M'), 'd0': Q_(6e-6, 'M'), 'Ka_dye': Q_(16.8e6, '1/M')}


def _demo(*, filtered: bool) -> MeasurementSet:
    ms = MeasurementSet.from_dataframe(load_measurements(_DEMO), source_file=_DEMO)
    if filtered:
        ms.set_active('0', False)  # what the demo's outlier filter at 3.5 leaves out
    return ms


def _fit(ms: MeasurementSet):
    """The fit the worker makes of the active replicates of *ms*, every input exact."""
    return fit_measurement_set(
        ms.with_active(ms.active_replica_ids), IDAAssay, _CONDITIONS, FitConfig(per_replica=False)
    )


@pytest.fixture(scope='module')
def second(tmp_path_factory) -> str:
    """The demo's measurements in a second file."""
    path = tmp_path_factory.mktemp('second') / 'IDA_system_again.txt'
    path.write_bytes(Path(_DEMO).read_bytes())
    return str(path)


@pytest.fixture(scope='module')
def fits(second):
    """A fit of the demo as its filter leaves it (replicates 1–7), one of all eight, and one of both files."""
    from gui.dataset import Dataset

    return {
        'filtered': _fit(_demo(filtered=True)),
        'all': _fit(_demo(filtered=False)),
        'two files': _fit(Dataset.open([_DEMO]).added([second]).ms),
        'second': second,
    }


@pytest.fixture
def make_session(qapp):
    """Sessions stating the demo's binding model; on teardown their threads are seen out."""
    from PyQt6.QtCore import QCoreApplication, QSettings

    from gui.fitting_session import FittingSession

    QCoreApplication.setApplicationName(f'model_consistency_{uuid.uuid4().hex[:8]}')
    QSettings().clear()
    sessions = []

    def build():
        session = FittingSession()
        state_binding(session, assay_type=AssayType.IDA, conditions=_CONDITIONS)
        session.model.binding.set_per_replica(False)
        session.model.binding_edited()
        sessions.append(session)
        return session

    yield build
    for session in sessions:
        session.model.shutdown()
        session.close()
    QSettings().clear()


def _holding(session, fits, held: str, *, filtered: bool):
    """*session* with the demo loaded and the fit *held* of *fits* held, its profile beside it, shown."""
    model = session.model
    assert model.load_files([_DEMO]) is None
    if held == 'two files':
        assert model.add_files([fits['second']]) is None
    fit = fits[held]
    if filtered:
        model.set_replicate('0', False)
    fit = copy.deepcopy(fit)
    model._held_fit_results = [fit]
    model._profiled_fit = fit
    model.check_results()
    assert model.fit_results == [fit], model.hidden_fit_notes
    return model


def _deliver_new_fit(model, fit):
    """Hand *model* a further fit as the fit worker does."""
    from gui.workers import FitWorker

    ms = model.measurement_set
    worker = FitWorker(
        ms.with_active(ms.active_replica_ids), IDAAssay, _CONDITIONS, FitConfig(per_replica=False), parent=model
    )
    worker.finished.connect(model._on_fit_complete)
    model._fit_worker = worker
    worker.finished.emit(copy.deepcopy(fit))


#: (name, the fit held, whether replicate 0 is off, the edit of a model given the fits)
SEQUENCES = [
    (
        'outlier removal switches off used replicates 1, 2 and 7',
        'filtered',
        True,
        lambda m, f: m.remove_outliers(2.6, 3),
    ),
    ('a used replicate is switched off', 'all', False, lambda m, f: m.set_replicate('0', False)),
    ('every replicate is switched off by outlier removal', 'all', False, lambda m, f: m.remove_outliers(0.5, 3)),
    ('the replicates are reset', 'filtered', True, lambda m, f: m.reset_replicates()),
    ('a file is added', 'all', False, lambda m, f: m.add_files([f['second']])),
    ('a file the fit used is removed', 'two files', False, lambda m, f: m.remove_file(m.dataset.files[-1].path)),
    ('the data are cleared', 'all', False, lambda m, f: m.clear()),
    ('a fit arrives', 'all', False, lambda m, f: _deliver_new_fit(m, m.held_fit_results[0])),
]
_IDS = [name for name, *_ in SEQUENCES]


def _signals(model):
    """Every signal the model declares, by name."""
    meta = model.metaObject()
    names = (bytes(meta.method(i).name()).decode() for i in range(meta.methodOffset(), meta.methodCount()))
    kinds = (meta.method(i).methodType() for i in range(meta.methodOffset(), meta.methodCount()))
    return [name for name, kind in zip(names, kinds, strict=True) if kind == QMetaMethod.MethodType.Signal]


def _inconsistencies(model) -> list[str]:
    """What a view reading *model* now would find contradicting itself."""
    found = []
    ms = model.measurement_set
    active = [] if ms is None else ms.active_replica_ids
    for fit in model.fit_results:
        off = [rid for rid in fit_replica_ids(fit) or () if rid not in active]
        if off:
            found.append(f'a shown fit used replicates {off} that are not active')
    expected = {}
    for fit in model.held_fit_results:
        note = model.mismatch_note(fit, 'fit', 'run the fit again')
        if note is not None:
            expected[fit.id] = note
    if set(expected) != set(model.hidden_fit_notes):
        found.append('the fits hidden are not the ones that fail to match the data')
    if model.profiled_fit is not None and not any(fit is model.profiled_fit for fit in model.held_fit_results):
        found.append('the profile belongs to a fit no longer held')
    return found


@pytest.mark.parametrize(('name', 'held', 'filtered', 'edit'), SEQUENCES, ids=_IDS)
def test_every_notification_finds_the_model_consistent(make_session, fits, name, held, filtered, edit):
    session = make_session()
    model = _holding(session, fits, held, filtered=filtered)
    found: list[tuple[str, str]] = []
    for signal in _signals(model):
        getattr(model, signal).connect(
            lambda *_args, signal=signal: found.extend((signal, problem) for problem in _inconsistencies(model))
        )

    edit(model, fits)

    assert found == []


@pytest.mark.parametrize(('name', 'held', 'filtered', 'edit'), SEQUENCES, ids=_IDS)
def test_an_edit_is_said_once(make_session, fits, name, held, filtered, edit):
    """One notification per edit, sent once the model is consistent: no view draws a state in between."""
    session = make_session()
    model = _holding(session, fits, held, filtered=filtered)
    said: list[str] = []
    for signal in _signals(model):
        getattr(model, signal).connect(lambda *_args, signal=signal: said.append(signal))

    edit(model, fits)

    assert len(said) == 1, said


@pytest.mark.parametrize(('name', 'held', 'filtered', 'edit'), SEQUENCES, ids=_IDS)
def test_no_view_raises_and_each_draws_once(make_session, fits, monkeypatch, name, held, filtered, edit):
    """The whole session through each edit: no slot raises, and no view draws more than once."""
    from gui.views.binding import BindingView
    from gui.views.confidence import ConfidenceView
    from gui.views.fit_results import FitResultsView
    from gui.views.measurements import MeasurementsView
    from gui.views.plot_appearance import PlotAppearanceView
    from gui.views.sensitivity import SensitivityView
    from gui.views.uncertainty import UncertaintyView

    draws: dict[str, int] = {}
    for view in (
        BindingView,
        ConfidenceView,
        FitResultsView,
        MeasurementsView,
        PlotAppearanceView,
        SensitivityView,
        UncertaintyView,
    ):

        def counted(self, *args, _refresh=view.refresh, _name=view.__name__, **kwargs):
            draws[_name] = draws.get(_name, 0) + 1
            return _refresh(self, *args, **kwargs)

        monkeypatch.setattr(view, 'refresh', counted)
    session = make_session()
    model = _holding(session, fits, held, filtered=filtered)
    raised: list[str] = []
    monkeypatch.setattr(sys, 'excepthook', lambda kind, value, tb: raised.append(f'{kind.__name__}: {value}'))
    draws.clear()

    edit(model, fits)

    assert raised == []
    assert {name: n for name, n in draws.items() if n > 1} == {}


def test_no_signal_reaches_an_edit_that_takes_no_argument_directly():
    """PyQt drops a signal's extra arguments only for a slot whose own parameters it can count;
    an edit's wrapper takes ``*args``, so ``clicked(bool)`` connected straight to an edit of no
    argument passes ``checked`` into it and the click fails. Such an edit is connected through a lambda."""
    import ast
    import inspect

    from gui.session_model import SessionModel

    root = Path(__file__).resolve().parents[3] / 'gui'
    direct = []
    for path in root.rglob('*.py'):
        for node in ast.walk(ast.parse(path.read_text())):
            if not (isinstance(node, ast.Call) and getattr(node.func, 'attr', None) == 'connect' and node.args):
                continue
            target = node.args[0]
            if isinstance(target, ast.Attribute) and getattr(target.value, 'attr', None) == 'model':
                method = getattr(SessionModel, target.attr, None)
                wrapped = getattr(method, '__wrapped__', None)
                if wrapped is not None and len(inspect.signature(wrapped).parameters) == 1:
                    direct.append(f'{path.relative_to(root.parent)}:{node.lineno} {target.attr}')
    assert direct == []
