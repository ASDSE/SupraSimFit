"""Every link, callout action and refusal that points at a place shows that place (:meth:`FittingSession.reveal`).

A link whose target is already on screen still answers: the view it names comes on
screen, its side panel shows where the place is there, the section holding it opens,
the place is scrolled to the top of its scroll area, focus moves into it, and an accent
mark rings it for a moment. Each test clicks a link from the layout a window opens in,
and again from one where every one of those steps has work to do: another view on
screen, the side panels hidden, every section of the panels closed and every scroll
area scrolled to its end.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

pytest.importorskip('PyQt6')

from PyQt6.QtCore import QPoint, QRect, Qt  # noqa: E402
from PyQt6.QtWidgets import QPushButton, QScrollArea, QWidget  # noqa: E402

from core.assays.registry import AssayType  # noqa: E402
from core.data_processing.measurement_set import MeasurementSet  # noqa: E402
from core.io.formats.bmg_reader import BMG_PLACEHOLDER_KEY  # noqa: E402
from core.pipeline.inputs import InputSpec  # noqa: E402
from gui.design import components as C  # noqa: E402
from gui.design import tokens  # noqa: E402
from gui.session_model import Change  # noqa: E402
from tests.unit.gui import sensitivity_results as F  # noqa: E402
from tests.unit.gui.session_setup import state_binding  # noqa: E402
from tests.unit.gui.test_fit_results_view import _CONFLICT, _SHIFTS  # noqa: E402
from tests.unit.gui.test_results import aware_result, fit_on, four_replicates  # noqa: E402

#: How long a test waits for the mark to clear, in seconds.
_CLEARS_WITHIN = 2.0


@pytest.fixture
def window(qapp, monkeypatch):
    """A main window off screen, short enough that the side panels scroll; every dialog it raises recorded."""
    from gui.main_window import FittingMainWindow

    said: list[str] = []

    def say(_parent, title, *_args, **_kwargs):
        said.append(title)

    for kind in ('warning', 'information'):
        monkeypatch.setattr(f'gui.fitting_session.QMessageBox.{kind}', say)
    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    # A mark that clears at once, so a test sees it come and go without waiting the designed while.
    monkeypatch.setitem(tokens.DURATION, 'reveal-mark', 30)
    made = FittingMainWindow()
    made.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    made.resize(1280, 560)
    made.show()
    made.said = said
    yield made
    session = made.active_session()
    session.model._fit_worker = session.model._profile_worker = None
    made.close()


def _settle(qapp) -> None:
    for _ in range(3):
        qapp.processEvents()


def _disturb(window, away: str) -> None:
    """Put *away* on screen, hide the side panels, close every section of them and scroll every scroll area to its end."""
    session = window.active_session()
    window.show_view(away)
    window._set_side_visible(False)
    for page in session._views.values():
        if page.side is not None:
            for header in page.side.findChildren(C.SectionHeader):
                header.set_open(False)
    for area in session.findChildren(QScrollArea):
        bar = area.verticalScrollBar()
        bar.setValue(bar.maximum())


def _scroll_area(widget: QWidget) -> QScrollArea | None:
    parent = widget.parentWidget()
    while parent is not None and not isinstance(parent, QScrollArea):
        parent = parent.parentWidget()
    return parent


def _assert_revealed(qapp, window, view: str, target: QWidget, focus: QWidget | None = None) -> None:
    """*view* on screen with *target* shown at the top of its scroll area, focus in it, and the mark round it, then gone."""
    session = window.active_session()
    assert window._view == view and session.current_view() == view
    page = session._views[view]
    if page.side is not None and page.side.isAncestorOf(target):
        assert window._side_visible and page.side.isVisible()
    assert target.isVisible(), 'every section holding the place is open'
    for header in [w.header for w in _ancestors(target) if isinstance(getattr(w, 'header', None), C.SectionHeader)]:
        assert header._open
    area = _scroll_area(target)
    if area is not None:
        top = target.mapTo(area.viewport(), QPoint(0, 0)).y()
        bar = area.verticalScrollBar()
        assert 0 <= top <= tokens.space(4) or bar.value() == bar.maximum(), 'the place is at the top of its scroll area'
        assert top < area.viewport().height(), 'the place is in view'
    focused = window.focusWidget()
    if focus is not None:
        assert focused is focus
    else:
        assert focused is target or target.isAncestorOf(focused), 'focus moved into the place'
    marks = [m for m in window.findChildren(C.RevealMark) if m.isVisible()]
    assert [m.target for m in marks] == [target], 'one mark rings the place'
    (mark,) = marks
    shown = QRect(target.mapTo(mark.parentWidget(), QPoint(0, 0)), target.size()).intersected(
        mark.parentWidget().rect()
    )
    assert mark.geometry().contains(shown), 'the mark rings what is shown of the place'
    deadline = time.monotonic() + _CLEARS_WITHIN
    while any(m.isVisible() for m in window.findChildren(C.RevealMark)) and time.monotonic() < deadline:
        qapp.processEvents()
    assert not any(m.isVisible() for m in window.findChildren(C.RevealMark)), 'the mark clears'


def _ancestors(widget: QWidget):
    while widget is not None:
        yield widget
        widget = widget.parentWidget()


def _show_conflicted_fit(window) -> None:
    model = window.active_session().model
    model._held_fit_results = [aware_result(shifts=_SHIFTS, diagnostics=_CONFLICT)]
    model.changed.emit(Change.RESULTS)


def _link(host: QWidget, text: str) -> QPushButton:
    (link,) = [b for b in host.findChildren(QPushButton) if b.text().startswith(text) and b.isVisibleTo(host)]
    return link


def _callout_action(host: QWidget, title_text: str | None = None) -> QPushButton:
    actions = [c.action for c in host.findChildren(C.Callout) if c.action is not None and not c.isHidden()]
    if title_text is not None:
        actions = [a for a in actions if a.text() == title_text]
    (action,) = actions
    return action


_FROM = ('as-opened', 'disturbed')


@pytest.mark.parametrize('start', _FROM)
def test_all_results_and_diagnostics_shows_diagnostics(qapp, window, start):
    session = window.active_session()
    _show_conflicted_fit(window)
    window.show_view('Fit results')
    if start == 'disturbed':
        _disturb(window, 'Measurements')
    _settle(qapp)

    _link(session._results.headline, 'All results and diagnostics').click()

    _assert_revealed(qapp, window, 'Fit results', session._results.diagnostics_section)


@pytest.mark.parametrize('start', _FROM)
def test_the_conflict_callout_of_ka_confidence_shows_the_input_shifts(qapp, window, start):
    session = window.active_session()
    _show_conflicted_fit(window)
    window.show_view('Ka confidence')
    _settle(qapp)
    action = _callout_action(session._confidence.callout_host)
    if start == 'disturbed':
        _disturb(window, 'Ka confidence')
    _settle(qapp)

    action.click()

    _assert_revealed(qapp, window, 'Ka confidence', session._confidence.sections['conflict'])


@pytest.mark.parametrize('start', _FROM)
def test_the_conflict_callout_of_fit_results_shows_the_readings_in_ka_confidence(qapp, window, start):
    session = window.active_session()
    _show_conflicted_fit(window)
    window.show_view('Fit results')
    _settle(qapp)
    action = _callout_action(session._results.callout_host)
    if start == 'disturbed':
        _disturb(window, 'Fit results')
    _settle(qapp)

    action.click()

    _assert_revealed(qapp, window, 'Ka confidence', session._confidence.header_host)


@pytest.mark.parametrize('start', _FROM)
def test_review_in_ka_confidence_of_input_uncertainty_shows_the_readings(qapp, window, start):
    session = window.active_session()
    _show_conflicted_fit(window)
    window.show_view('Input uncertainty')
    if start == 'disturbed':
        _disturb(window, 'Input uncertainty')
        window._set_side_visible(True)
    _settle(qapp)

    session._uncertainty.review.click()

    _assert_revealed(qapp, window, 'Ka confidence', session._confidence.header_host)


@pytest.mark.parametrize('start', _FROM)
def test_show_fit_results_of_measurements_shows_the_headline(qapp, window, start):
    session = window.active_session()
    state_binding(session, assay_type=AssayType.GDA)
    session.model.load(four_replicates(), None)
    session.model._held_fit_results = [fit_on(session.model.measurement_set)]
    session.model.changed.emit(Change.RESULTS)
    window.show_view('Measurements')
    _settle(qapp)
    action = _callout_action(session._measurements.cue_host)
    if start == 'disturbed':
        _disturb(window, 'Measurements')
    _settle(qapp)

    action.click()

    _assert_revealed(qapp, window, 'Fit results', session._results.headline)


@pytest.mark.parametrize('start', _FROM)
def test_edit_in_input_uncertainty_shows_the_inputs(qapp, window, start):
    session = window.active_session()
    state_binding(session, assay_type=AssayType.IDA)
    window.show_view('Sensitivity')
    if start == 'disturbed':
        _disturb(window, 'Sensitivity')
        window._set_side_visible(True)
    _settle(qapp)

    session._sensitivity.edit_inputs.click()

    _assert_revealed(qapp, window, 'Input uncertainty', session._uncertainty.table)


@pytest.mark.parametrize(
    ('make', 'action', 'view', 'target'),
    [
        (None, 'Edit in Input uncertainty', 'Input uncertainty', lambda s: s._uncertainty.table),
        (F.sobol_result, 'Compare in Fit results', 'Fit results', lambda s: s._results.headline),
    ],
    ids=['nothing-to-vary', 'not-a-confidence-interval'],
)
def test_the_callouts_of_sensitivity_show_the_place_they_name(qapp, window, make, action, view, target):
    session = window.active_session()
    model = session.model
    state_binding(session, assay_type=AssayType.IDA)
    if make is None:
        model.load(four_replicates(), None)  # with data and every input fixed, the callout says nothing varies
    else:
        model._held_fit_results = [aware_result()]
        model._sensitivity_result = make()
        model.changed.emit(Change.RESULTS | Change.SENSITIVITY)
    window.show_view('Sensitivity')
    _settle(qapp)

    _callout_action(session._sensitivity.callout_host, action).click()

    _assert_revealed(qapp, window, view, target(session))


def _placeholder_concentrations() -> MeasurementSet:
    ms = four_replicates()
    return MeasurementSet(
        concentrations=np.arange(1.0, ms.n_points + 1),
        signals=ms.signals,
        replica_ids=ms.replica_ids,
        metadata={BMG_PLACEHOLDER_KEY: True},
    )


@pytest.mark.parametrize('start', _FROM)
def test_a_fit_refused_for_placeholder_concentrations_opens_the_first_one_for_typing(qapp, window, start):
    session = window.active_session()
    state_binding(session, assay_type=AssayType.GDA)
    session.model.load(_placeholder_concentrations(), None)
    window.show_view('Fit results')
    if start == 'disturbed':
        _disturb(window, 'Fit results')
    _settle(qapp)

    session.run_fit()

    grid = session._measurements.grid
    assert window.said == ['Concentrations Required']
    _assert_revealed(qapp, window, 'Measurements', session._measurements.conc_section, focus=grid._editor)


def test_a_fit_refused_for_the_binding_model_shows_the_problem(qapp, window):
    session = window.active_session()
    state_binding(session, assay_type=AssayType.GDA)
    session.model.load(four_replicates(), None)
    form = session.model.binding
    form.edit(next(iter(form.entries)), '-1')
    session.model.binding_edited()
    session.model.edit_finished()
    window.show_view('Fit results')
    _settle(qapp)
    (problem,) = [p for p in session._binding.canvas.findChildren(C.Problem) if not p.isHidden()]

    session.run_fit()

    assert window.said == ['Binding model']
    _assert_revealed(qapp, window, 'Binding model', problem.parentWidget())


def test_an_analysis_refused_for_nothing_to_vary_shows_the_inputs(qapp, window):
    session = window.active_session()
    state_binding(session, assay_type=AssayType.IDA)
    session.model.load(four_replicates(), None)
    window.show_view('Sensitivity')
    _settle(qapp)

    session.run_sensitivity()

    assert window.said == ['Sensitivity Analysis']
    _assert_revealed(qapp, window, 'Input uncertainty', session._uncertainty.table)


def test_an_analysis_refused_for_its_settings_shows_the_problem_beside_them(qapp, window):
    from core.pipeline.sensitivity import SensitivityMode

    session = window.active_session()
    state_binding(session, assay_type=AssayType.IDA)
    session.model.load(four_replicates(), None)
    session.model.uncertainty.set_specs({'h0': InputSpec.sigma_pct(40.0), 'd0': InputSpec.sigma_pct(5.0)})
    session.model.uncertainty_edited()
    form = session.model.analysis
    form.mode, form.x_key, form.y_key, form.x_span = SensitivityMode.HEATMAP, 'h0', 'd0', 3.0
    session.model.analysis_edited()
    _disturb(window, 'Measurements')
    _settle(qapp)

    session.run_sensitivity()

    assert window.said == ['Sensitivity Analysis']
    _assert_revealed(qapp, window, 'Sensitivity', session._sensitivity.problem.parentWidget())


def test_a_second_reveal_moves_the_one_mark(qapp, window):
    session = window.active_session()
    _show_conflicted_fit(window)
    window.show_view('Fit results')
    _settle(qapp)
    _link(session._results.headline, 'All results and diagnostics').click()
    _callout_action(session._results.callout_host).click()

    marks = [m for m in window.findChildren(C.RevealMark) if m.isVisible()]
    assert [m.target for m in marks] == [session._confidence.header_host]


def test_the_mark_follows_its_place_scrolled_sideways(qapp):
    """A place wider than its scroll area keeps its mark round it as the area scrolls sideways."""
    from gui.design.appearance import theme

    area = QScrollArea()
    area.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    area.resize(300, 200)
    content = QWidget()
    content.setFixedSize(900, 600)
    place = QWidget(content)
    place.setGeometry(40, 40, 800, 100)
    area.setWidget(content)
    area.show()
    _settle(qapp)
    C.reveal(theme(), place)
    bar = area.horizontalScrollBar()

    bar.setValue(bar.maximum())
    qapp.processEvents()

    (mark,) = [m for m in area.findChildren(C.RevealMark) if m.isVisible()]
    shown = QRect(place.mapTo(mark.parentWidget(), QPoint(0, 0)), place.size()).intersected(mark.parentWidget().rect())
    assert mark.geometry().contains(shown), 'the mark rings what is shown of the place'
    area.close()
