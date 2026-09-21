"""Tests for the export pipeline: the plot images and the uncertainty budget table.

Verifies:
  * single-plot PNG export honours the requested width
  * single-plot SVG export writes a parseable vector file
  * unsupported export formats raise ``ValueError``
  * the fit-summary annotation survives an export and actually lands in it
  * the Ka uncertainty budget is offered only where there is one, and the file
    holds the rows the Ka Sensitivity tab reports
"""

import csv
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip('PyQt6')
pytest.importorskip('pyqtgraph')

_IDA_DATA = Path(__file__).resolve().parents[3] / 'data' / 'IDA_system.txt'


@pytest.fixture
def simple_plot_widget(qapp):
    from gui.plotting.plot_widget import PlotWidget

    x = np.linspace(0, 1e-4, 20)
    pw = PlotWidget()
    pw.update_plot(
        {
            'concentrations': x,
            'active_replicas': [('r1', x + 0.01), ('r2', x * 0.95 + 0.015)],
            'dropped_replicas': [],
            'average': x + 0.0125,
            'fits': [{'x': x, 'y': x + 0.02, 'label': 'fit', 'id': 'abc'}],
        }
    )
    return pw


# ----------------------------------------------------------------------
# Single-plot export
# ----------------------------------------------------------------------


def test_plot_widget_png_honours_requested_width(simple_plot_widget, tmp_path):
    from PyQt6.QtGui import QImage

    path = tmp_path / 'plot.png'
    simple_plot_widget.export_image(str(path), width_px=1200)

    assert path.exists()
    img = QImage(str(path))
    assert img.width() == 1200
    assert img.height() > 0


def test_plot_widget_svg_writes_vector_file(simple_plot_widget, tmp_path):
    path = tmp_path / 'plot.svg'
    simple_plot_widget.export_image(str(path))

    assert path.exists()
    assert path.stat().st_size > 0
    content = path.read_text(encoding='utf-8')
    assert '<svg' in content


def test_plot_widget_rejects_unknown_extension(simple_plot_widget, tmp_path):
    with pytest.raises(ValueError, match='cannot be written'):
        simple_plot_widget.export_image(str(tmp_path / 'x.bmp'))


# ----------------------------------------------------------------------
# Fit-summary annotation in exported images. The overlay is a scene item
# the exporter has to render like any other; these pin that it survives an
# export unmoved and actually appears in the output.
# ----------------------------------------------------------------------


@pytest.fixture
def annotated_plot_widget(qapp):
    """A PlotWidget with a fit result + annotation visible.

    Shown off-screen with events processed so the ViewBox resolves to real
    geometry before the annotation is placed.
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication

    from core.pipeline.fit_pipeline import FitResult
    from core.pipeline.varpro import KaInterval
    from core.units import Q_
    from gui.plotting.plot_widget import PlotWidget

    x = np.linspace(0, 1e-4, 20)
    pw = PlotWidget()
    pw.update_plot(
        {
            'concentrations': x,
            'active_replicas': [('r1', x * 1.1 + 0.01)],
            'dropped_replicas': [],
            'average': x * 1.05 + 0.012,
            'fits': [{'x': x, 'y': x * 1.05 + 0.012, 'label': 'GDA fit', 'id': 'abc'}],
        }
    )
    result = FitResult(
        parameters={
            'Ka_guest': Q_(1e6, '1/M'),
            'I0': Q_(100.0, 'au'),
            'I_dye_free': Q_(5e4, 'au/M'),
            'I_dye_bound': Q_(8e4, 'au/M'),
        },
        rmse=0.005,
        r_squared=0.998,
        x_fit=Q_(x, 'M'),
        y_fit=Q_(x * 1.05 + 0.012, 'au'),
        assay_type='GDA',
        model_name='equilibrium_4param',
        intervals={'Ka_guest': KaInterval(low=8e5, high=1.3e6, open_low=False, open_high=False, level=0.95, dof=16)},
    )
    pw.set_fit_results([result])
    pw.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    pw.resize(800, 600)
    pw.show()
    QApplication.processEvents()
    return pw


def test_annotation_state_restored_after_export(annotated_plot_widget, tmp_path):
    """The annotation TextItem's parent and position survive a round-trip export."""
    annotation = annotated_plot_widget._annotation_item
    assert annotation is not None, 'annotation should be visible'

    saved_parent = annotation.parentItem()
    saved_pos = annotation.pos()

    annotated_plot_widget.export_image(str(tmp_path / 'annot.png'), width_px=1200)

    assert annotation.parentItem() is saved_parent
    assert annotation.pos() == saved_pos


def test_annotation_actually_renders_into_the_export(annotated_plot_widget, tmp_path):
    """The annotation must appear in the exported image, not drift off-canvas.

    Measured by exporting the same plot with the overlay on and off and
    counting changed pixels, rather than sampling fixed corners: the overlay
    is auto-placed into whichever candidate slot is emptiest, so a corner scan
    would encode one particular dataset's outcome.
    """
    import copy

    from PyQt6.QtGui import QImage

    pw = annotated_plot_widget
    with_ann, without_ann = tmp_path / 'with.png', tmp_path / 'without.png'

    pw.export_image(str(with_ann), width_px=1200)

    style = copy.deepcopy(pw._style)
    style['visibility']['show_fit_results'] = False
    pw.apply_style(style)
    assert pw._annotation_item is None, 'overlay should be gone with the flag off'
    pw.export_image(str(without_ann), width_px=1200)

    a, b = QImage(str(with_ann)), QImage(str(without_ann))
    assert (a.width(), a.height()) == (b.width(), b.height())
    changed = sum(a.pixel(x, y) != b.pixel(x, y) for y in range(0, a.height(), 4) for x in range(0, a.width(), 4))
    # The overlay is a multi-line boxed label; anything under a few hundred
    # sampled pixels means it did not render where the canvas can see it.
    assert changed > 300, f'annotation contributed only {changed} sampled pixels to the export'


# ----------------------------------------------------------------------
# The Ka uncertainty budget: a table of the analysis on screen, written as
# a CSV so its numbers can be read outside the app.
# ----------------------------------------------------------------------


@pytest.fixture
def analysed_session(qapp, monkeypatch):
    """Build a session on the IDA data showing a given sensitivity run."""
    from core.assays.registry import AssayType
    from gui.fitting_session import FittingSession
    from tests.unit.gui.test_sensitivity_gui import _made_on

    monkeypatch.setattr('gui.fitting_session.QMessageBox.warning', lambda *args: None)
    sessions = []

    def build(result=None):
        session = FittingSession()
        sessions.append(session)
        session._assay_panel.set_assay_type(AssayType.IDA)
        session._data_panel.load_file(str(_IDA_DATA))
        if result is None:
            return session
        run = _made_on(result, session._state.measurement_set, session._assay_panel.current_conditions())
        for key, spec in run.config.errors.specs.items():
            session._input_panel._rows[key].set_spec(spec)
        session._on_sensitivity_complete(run)
        assert session._state.sensitivity_note is None, 'the run has to be the one the session is showing'
        return session

    yield build
    for session in sessions:
        session.shutdown()


def _artefact(session, key):
    from gui.session import build_artefacts

    (artefact,) = [a for a in build_artefacts(session) if a.key == key]
    return artefact


def test_the_budget_is_written_as_the_sensitivity_tab_reports_it(analysed_session, tmp_path):
    """The file is the table on screen: every row of it, with the analysis's own numbers."""
    from tests.unit.gui.test_sensitivity_gui import _sobol_result

    session = analysed_session(_sobol_result())
    artefact = _artefact(session, 'budget_csv')
    path = tmp_path / f'run{artefact.suffix}'

    assert artefact.available and artefact.label == 'Ka uncertainty budget (CSV)'
    assert artefact.suffix == '_budget.csv'
    artefact.writer(path)

    rows = session._sensitivity_widget.budget_rows()
    assert rows, 'the run reports a budget'
    with path.open(encoding='utf-8', newline='') as handle:
        written = list(csv.DictReader(handle))
    assert [list(row) for row in written] == [[str(key) for key in rows[0]]] * len(rows)
    assert written == [{key: str(value) for key, value in row.items()} for row in rows]


def test_a_budget_with_no_number_in_it_is_refused_rather_than_written_empty(analysed_session, tmp_path):
    """A run whose samples gave too few fits has a budget of NaN; a file of empty cells would answer nothing."""
    from core.pipeline.sensitivity import Budget
    from tests.unit.gui.test_sensitivity_gui import _sobol_result

    result = _sobol_result()
    result.budget = {'Ka_guest': Budget(np.nan, (np.nan, np.nan), result.budget['Ka_guest'].rows)}
    artefact = _artefact(analysed_session(result), 'budget_csv')
    path = tmp_path / f'run{artefact.suffix}'

    assert artefact.available, 'the tab is showing a Sobol run, so the file is offered'
    with pytest.raises(ValueError, match='too few of its samples have a fit'):
        artefact.writer(path)
    assert not path.exists()


def test_a_heatmap_has_no_budget_to_export_and_says_why(analysed_session):
    """A heatmap sweeps two inputs on a grid; it splits no variance between the sources."""
    from dataclasses import replace

    from tests.unit.gui.test_sensitivity_gui import _heatmap_result, _sobol_result

    # The fit at the entered inputs is what the session checks a run against,
    # and a heatmap makes one like any other run.
    heatmap = replace(_heatmap_result(), baseline_fit=_sobol_result().baseline_fit)
    artefact = _artefact(analysed_session(heatmap), 'budget_csv')

    assert not artefact.available
    assert artefact.unavailable_reason == (
        'The analysis shown is a heatmap. Run one with Sensitivity indices to get an uncertainty budget.'
    )


def test_without_an_analysis_the_budget_says_to_run_one(analysed_session):
    artefact = _artefact(analysed_session(), 'budget_csv')

    assert not artefact.available
    assert artefact.unavailable_reason == 'Run a sensitivity analysis first.'
