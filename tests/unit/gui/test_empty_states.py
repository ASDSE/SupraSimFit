"""What a view says before it has anything to show, and the demo that fills it (DESIGN.md §6, *Empty state*).

Every view with nothing to show puts the one empty state in place of its content —
its title, one sentence and, in a session that holds nothing, *Load data…* and *Try
the demo data* — never a pair of bare axes. What it says comes from one rule of the
session model, so no view says a fit or an analysis has not been made while it runs.
The long runs are stood in for by functions that only watch their cancel flag.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

pytest.importorskip('PyQt6')

from PyQt6.QtCore import QSettings, Qt  # noqa: E402
from PyQt6.QtWidgets import QAbstractButton, QLabel, QPushButton, QWidget  # noqa: E402

from core.pipeline.varpro import FitCancelled  # noqa: E402

_REPO = Path(__file__).resolve().parents[3]
_IDA_DATA = _REPO / 'data' / 'IDA_system.txt'

#: The views that show a result or a plot, and so have nothing to show in an empty session.
EMPTY_VIEWS = ('Measurements', 'Fit results', 'Ka confidence', 'Sensitivity', 'Plot appearance')

LOAD, DEMO = 'Load data…', 'Try the demo data'


@pytest.fixture
def window(qapp, monkeypatch):
    from gui.main_window import FittingMainWindow

    shown: list[tuple] = []
    monkeypatch.setattr('gui.fitting_session.QMessageBox.warning', lambda *args: shown.append(args))
    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    win = FittingMainWindow()
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    win.show()
    qapp.processEvents()
    yield win
    for session in win._sessions:
        session.model.shutdown()
    win.close()
    assert shown == []


@pytest.fixture
def watchful_fit(monkeypatch):
    """Stand in for the fit with a run that only watches its cancel flag."""
    from gui import workers

    def run(ms, assay_cls, conditions, config, should_cancel=None, **kwargs):
        while should_cancel is None or not should_cancel():
            time.sleep(0.005)
        raise FitCancelled('The fit was cancelled.')

    monkeypatch.setattr(workers, 'fit_measurement_set', run)


@pytest.fixture
def watchful_sensitivity(monkeypatch):
    """Stand in for the analysis with a run that only watches its cancel flag."""
    from gui import workers

    def run(*args, progress, should_cancel, **kwargs):
        while not should_cancel():
            time.sleep(0.005)
        raise FitCancelled('The analysis was cancelled before its baseline fit.')

    monkeypatch.setattr(workers, 'run_sensitivity', run)


def _on_screen(qapp, window, view: str) -> QWidget:
    """Put *view* on screen and give back its page."""
    window.show_view(view)
    qapp.processEvents()
    return window.active_session()._views[view]


def _button(page: QWidget, name: str) -> QAbstractButton | None:
    """The button on screen in *page* named *name*, or ``None``."""
    found = [
        b
        for b in page.findChildren(QAbstractButton)
        if b.isVisible() and name in (b.accessibleName(), b.text() if isinstance(b, QPushButton) else '')
    ]
    return found[0] if found else None


def _texts(page: QWidget) -> str:
    """Every line of text on screen in *page*, side panel included."""
    return '\n'.join(label.text() for label in page.findChildren(QLabel) if label.isVisible())


def _wait_until(qapp, condition, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, 'timed out waiting for a background worker'
        qapp.processEvents()
        time.sleep(0.01)


def test_every_empty_view_offers_load_data_and_the_demo_and_draws_no_bare_axes(qapp, window):
    import pyqtgraph as pg

    for view in EMPTY_VIEWS:
        page = _on_screen(qapp, window, view)
        assert _button(page, LOAD) is not None, f'{view} offers no {LOAD}'
        assert _button(page, DEMO) is not None, f'{view} offers no {DEMO}'
        axes = [w for w in page.findChildren(pg.GraphicsView) if w.isVisible()]
        assert axes == [], f'{view} draws an empty plot in an empty session'


def test_the_demo_action_loads_and_fits_in_the_same_session(qapp, window, watchful_fit):
    session = window.active_session()
    page = _on_screen(qapp, window, 'Ka confidence')

    _button(page, DEMO).click()

    assert window._sessions == [session]
    assert session.model.measurement_set is not None
    assert session.model.fit_running()


def test_the_load_action_loads_into_the_same_session(qapp, window, monkeypatch):
    session = window.active_session()
    monkeypatch.setattr('gui.views.measurements.QFileDialog.getOpenFileNames', lambda *args: ([str(_IDA_DATA)], ''))
    page = _on_screen(qapp, window, 'Fit results')

    _button(page, LOAD).click()

    assert window._sessions == [session]
    assert session.model.dataset_file() == str(_IDA_DATA)


def test_no_view_says_there_is_no_fit_while_the_fit_runs(qapp, window, watchful_fit):
    session = window.active_session()
    session.model.load_files([str(_IDA_DATA)])
    session.run_fit()
    _wait_until(qapp, session.model._fit_worker.isRunning)

    for view in ('Input uncertainty', 'Fit results', 'Ka confidence'):
        text = _texts(_on_screen(qapp, window, view))
        assert 'No fit' not in text, f'{view} says there is no fit while one runs:\n{text}'


def test_no_view_says_there_is_no_analysis_while_it_runs(qapp, window, watchful_sensitivity):
    from core.pipeline.inputs import InputSpec

    session = window.active_session()
    session.model.load_files([str(_IDA_DATA)])
    session.model.uncertainty.set_spec('h0', InputSpec.sigma_pct(5.0))
    session.model.uncertainty_edited()
    session.run_sensitivity()
    _wait_until(qapp, session.model._sensitivity_worker.isRunning)

    text = _texts(_on_screen(qapp, window, 'Sensitivity'))
    assert 'No run' not in text and 'No analysis' not in text, text


def test_load_data_offers_the_demo_and_fills_the_empty_session_on_screen(qapp, window, monkeypatch, watchful_fit):
    menus = []
    monkeypatch.setattr(window, '_show_menu', lambda menu, button: menus.append(menu))
    session = window.active_session()

    window._open_load_menu()
    (demo,) = [a for a in menus[0].actions_ if a is not None and a.text() == 'Open demo data (IDA)']
    demo.trigger()

    assert window._sessions == [session]
    assert session.model.measurement_set is not None and session.model.fit_running()


def test_export_several_offers_no_folder_of_the_bundled_examples(qapp, window, monkeypatch, tmp_path):
    from gui.dialogs import export_multiple_dialog as module

    monkeypatch.setattr(
        module, '_settings', lambda: QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    )
    session = window.active_session()
    assert session.set_up_demo_ida()

    folder = Path(module.ExportMultipleDialog(session).folder.editor.text()).resolve()

    assert folder.is_dir()
    assert not folder.is_relative_to(_REPO), f'Export several offers {folder}, inside the app'


def test_the_outlier_removal_the_demo_applied_shows_in_measurement_settings(qapp, window):
    session = window.active_session()
    view = session._measurements
    view.threshold.set_text('2')
    view.min_replicates.set_text('5')

    assert session.set_up_demo_ida()

    applied = session.model.dataset.outlier_result
    assert applied is not None and applied['status'] == 'applied'
    assert float(view.threshold.text) == applied['threshold']
    assert int(view.min_replicates.text) == applied['min_replicas']


def test_before_an_analysis_sensitivity_names_only_the_steps_still_to_take(qapp):
    """A session with data and a varying source is told to run, not to state what it already stated."""
    from PyQt6.QtGui import QKeySequence

    from core.pipeline.inputs import InputSpec
    from gui.session_model import SessionModel

    model = SessionModel()
    key = QKeySequence('Ctrl+R').toString(QKeySequence.SequenceFormat.NativeText)
    no_data = model.empty_view('Sensitivity')
    assert no_data.offers_data and 'Input uncertainty' not in no_data.sentence

    model.load_files([str(_IDA_DATA)])
    assert 'Input uncertainty' in model.empty_view('Sensitivity').sentence
    model.uncertainty.set_spec('h0', InputSpec.sigma_pct(5.0))
    model.uncertainty_edited()
    assert model.empty_view('Sensitivity').sentence == f'Choose Run analysis ({key}).'


def _offered_folders(session, monkeypatch) -> list[Path]:
    """The folder each single-file save of *session* offers first: raw data, the titration plot, the concentrations."""
    offered: list[Path] = []

    def ask(_parent, _title, start, _filters):
        offered.append(Path(start).parent.resolve())
        return '', ''

    monkeypatch.setattr('gui.fitting_session.QFileDialog.getSaveFileName', ask)
    monkeypatch.setattr('gui.views.measurements.QFileDialog.getSaveFileName', ask)
    session.export_raw_data()
    session.export_plot('Measurements')
    session._measurements._save_vector()
    return offered


def test_no_save_after_the_demo_offers_a_folder_inside_the_app(qapp, window, monkeypatch):
    session = window.active_session()
    assert session.set_up_demo_ida()

    offered = _offered_folders(session, monkeypatch)

    assert len(offered) == 3
    assert [f for f in offered if not f.is_dir() or f.is_relative_to(_REPO)] == [], offered


def test_a_save_offers_the_folder_of_the_data_it_was_made_from(qapp, window, monkeypatch, tmp_path):
    import shutil

    data = Path(shutil.copy(_IDA_DATA, tmp_path / 'titration.txt'))
    session = window.active_session()
    assert session.model.load_files([str(data)]) is None

    assert _offered_folders(session, monkeypatch) == [tmp_path.resolve()] * 3
