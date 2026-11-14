"""Tests for the export of the uncertainty budget table.

The Ka uncertainty budget is offered only where there is one, and the file holds the
rows the Ka Sensitivity tab reports.
"""

import csv
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip('PyQt6')
pytest.importorskip('pyqtgraph')

from tests.unit.gui.session_setup import state_binding  # noqa: E402

_IDA_DATA = Path(__file__).resolve().parents[3] / 'data' / 'IDA_system.txt'


# ----------------------------------------------------------------------
# The Ka uncertainty budget: a table of the analysis on screen, written as
# a CSV so its numbers can be read outside the app.
# ----------------------------------------------------------------------


@pytest.fixture
def analysed_session(qapp, monkeypatch):
    """Build a session on the IDA data showing a given sensitivity run."""
    from core.assays.registry import AssayType
    from gui.fitting_session import FittingSession
    from tests.unit.gui.sensitivity_results import made_on as _made_on

    monkeypatch.setattr('gui.fitting_session.QMessageBox.warning', lambda *args: None)
    sessions = []

    def build(result=None):
        session = FittingSession()
        sessions.append(session)
        state_binding(session, assay_type=AssayType.IDA)
        session.model.load_files([str(_IDA_DATA)])
        if result is None:
            return session
        run = _made_on(result, session.model.measurement_set, session.model.settings.conditions)
        for key, spec in run.config.errors.specs.items():
            session.model.uncertainty.set_spec(key, spec)
            session.model.uncertainty_edited()
        session.model._on_sensitivity_complete(run)
        assert session.model.sensitivity_note is None, 'the run has to be the one the session is showing'
        return session

    yield build
    for session in sessions:
        session.model.shutdown()


def _artefact(session, key):
    from gui.session import build_artefacts

    (artefact,) = [a for a in build_artefacts(session) if a.key == key]
    return artefact


def test_the_budget_is_written_as_the_sensitivity_tab_reports_it(analysed_session, tmp_path):
    """The file is the budget Sensitivity reports: every row of it, with the analysis's own numbers."""
    from gui.sensitivity import budget_csv_rows
    from tests.unit.gui.sensitivity_results import sobol_result as _sobol_result

    session = analysed_session(_sobol_result())
    artefact = _artefact(session, 'budget_csv')
    path = tmp_path / f'run{artefact.suffix}'

    assert artefact.available and artefact.label == 'Ka uncertainty budget (CSV)'
    assert artefact.suffix == '_budget.csv'
    artefact.writer(path)

    rows = budget_csv_rows(session.model.sensitivity_result)
    assert rows, 'the run reports a budget'
    with path.open(encoding='utf-8', newline='') as handle:
        written = list(csv.DictReader(handle))
    assert [list(row) for row in written] == [[str(key) for key in rows[0]]] * len(rows)
    assert written == [{key: str(value) for key, value in row.items()} for row in rows]


def test_a_budget_with_no_number_in_it_is_refused_rather_than_written_empty(analysed_session, tmp_path):
    """A run whose samples gave too few fits has a budget of NaN; a file of empty cells would answer nothing."""
    from core.pipeline.budget import Budget
    from tests.unit.gui.sensitivity_results import sobol_result as _sobol_result

    result = _sobol_result()
    result.budget = {'Ka_guest': Budget(np.nan, (np.nan, np.nan), result.budget['Ka_guest'].rows)}
    artefact = _artefact(analysed_session(result), 'budget_csv')
    path = tmp_path / f'run{artefact.suffix}'

    assert artefact.available, 'the tab is showing a Sobol run, so the file is offered'
    with pytest.raises(ValueError, match='too few of its samples have a fit'):
        artefact.writer(path)
    assert not path.exists()


def test_a_budget_withheld_for_every_constant_is_refused_rather_than_written_as_notes(analysed_session, tmp_path):
    """Every constant's numbers withheld leaves a file of reasons the tab already shows; the refusal points there."""
    from tests.unit.gui.sensitivity_results import sobol_result as _sobol_result

    result = _sobol_result()
    result.withheld = {key: 'open_interval' for key in result.budget}
    artefact = _artefact(analysed_session(result), 'budget_csv')
    path = tmp_path / f'run{artefact.suffix}'

    with pytest.raises(ValueError, match='says why its numbers are withheld'):
        artefact.writer(path)
    assert not path.exists()


def test_a_heatmap_has_no_budget_to_export_and_says_why(analysed_session):
    """A heatmap sweeps two inputs on a grid; it splits no variance between the sources."""
    from dataclasses import replace

    from tests.unit.gui.sensitivity_results import heatmap_result as _heatmap_result
    from tests.unit.gui.sensitivity_results import sobol_result as _sobol_result

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
