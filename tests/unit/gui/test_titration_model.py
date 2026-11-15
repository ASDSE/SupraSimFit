"""One titration plot model: every view draws the session's titration from :func:`gui.results.titration`.

Fit results and Plot appearance draw one plot, the replicate display read off the
session; Measurements draws the same points raw, with no curve, and after a fit a cue
that names the fitted value and opens Fit results.
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

pytest.importorskip('PyQt6')

from core.assays.registry import AssayType  # noqa: E402
from gui.design import components as C  # noqa: E402
from gui.session_model import Change  # noqa: E402
from tests.unit.gui.session_setup import state_binding  # noqa: E402
from tests.unit.gui.test_results import THIN, fit_on, four_replicates  # noqa: E402

GUI = Path(__file__).resolve().parents[3] / 'gui'


@pytest.fixture
def session(qapp):
    from gui.fitting_session import FittingSession

    made = FittingSession()
    yield made
    made.model._fit_worker = None
    made.close()


def _fitted(session):
    """Four replicates, one switched off, and a fit of the others held as shown; the fit."""
    state_binding(session, assay_type=AssayType.GDA)
    session.model.load(four_replicates(), None)
    session.model.set_replicate('0', False)
    fit = fit_on(session.model.measurement_set)
    session.model._held_fit_results = [fit]
    session.model.changed.emit(Change.RESULTS)
    return fit


def _same(a, b) -> bool:
    """Whether two :class:`~gui.views.titration.TitrationData` draw the same plot."""
    arrays = all(np.array_equal(getattr(a, k), getattr(b, k)) for k in ('x_molar', 'signals'))
    curves = [(len(x.curves), len(x.other_curves)) for x in (a, b)]
    pairs = [np.array_equal(u, v) for c, d in zip(a.curves, b.curves, strict=True) for u, v in zip(c, d, strict=True)]
    flags = [(x.active, x.x_name, x.mean_sd, x.replicates, x.caption) for x in (a, b)]
    return arrays and curves[0] == curves[1] and all(pairs) and flags[0] == flags[1]


def test_fit_results_and_plot_appearance_draw_one_plot_whatever_the_replicate_display(session):
    _fitted(session)

    for display in (1, 2, 0):
        session.model.set_replicate_display(display)
        results, appearance = session._results.plot.data, session._appearance.plot.data

        assert _same(results, appearance)
        assert len(results.curves) == 1
        assert (results.replicates, results.mean_sd) == (display in (0, 2), display in (0, 1))


def test_the_plot_header_tool_sets_the_session_s_replicate_display(session):
    _fitted(session)
    session._results.display_actions()[1].trigger()

    assert session.model.settings.replicate_display == 1
    assert session._appearance.plot.data.replicates is False
    assert [action.isChecked() for action in session._results.display_actions()] == [False, True, False]


def test_measurements_draws_the_same_points_raw_with_no_curve(session):
    _fitted(session)
    raw, fitted = session._measurements.plot.data, session._results.plot.data

    assert np.array_equal(raw.x_molar, fitted.x_molar) and np.array_equal(raw.signals, fitted.signals)
    assert raw.active == fitted.active == [False, True, True, True]
    assert raw.curves == [] and raw.other_curves == []
    assert raw.replicates is True and raw.mean_sd is False
    assert session._measurements.plot.plot_appearance == session._results.plot.plot_appearance


def _cue(session):
    """The cue above Measurements' plot, or ``None`` where none is shown."""
    cues = [c for c in session._measurements.cue_host.findChildren(C.Callout) if not c.isHidden()]
    assert len(cues) <= 1
    return cues[0] if cues else None


def test_measurements_names_the_fitted_value_and_opens_fit_results(session):
    assert _cue(session) is None  # nothing loaded
    state_binding(session, assay_type=AssayType.GDA)
    session.model.load(four_replicates(), None)
    assert _cue(session) is None  # no fit yet
    _fitted(session)
    requested: list[str] = []
    session.view_requested.connect(requested.append)

    cue = _cue(session)
    cue.action.click()

    assert f'Kₐ guest 1.24{THIN}×{THIN}10⁶ M⁻¹ — the fitted curve is in Fit results.' == cue.body.text()
    assert cue.action.text() == 'Show fit results'
    assert requested == ['Fit results']


def test_the_cue_is_gone_while_the_results_are_hidden(session):
    fit = _fitted(session)
    session.model._hidden_fit_notes[fit.id] = 'The replicates in use changed since this fit.'
    session.model.changed.emit(Change.RESULTS)

    assert _cue(session) is None


def test_the_cue_is_gone_while_a_fit_runs(session):
    _fitted(session)
    session.model._fit_worker = mock.Mock()
    session.model.changed.emit(Change.RUN)

    assert _cue(session) is None


def test_titration_data_is_built_only_by_the_one_plot_model():
    """Within gui/, ``TitrationData(`` is constructed in gui/results.py alone."""
    builders = []
    for path in GUI.rglob('*.py'):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, ast.Call) and getattr(node.func, 'id', getattr(node.func, 'attr', None)) == (
                'TitrationData'
            ):
                builders.append(path.relative_to(GUI.parent).as_posix())

    assert builders and set(builders) == {'gui/results.py'}
