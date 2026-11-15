"""Widget tests for Sensitivity (:mod:`gui.views.sensitivity`) and the runs a session makes for it.

What the text and the numbers say is pinned by ``test_sensitivity.py``; here only the view's
own work: its states (no run, a run hidden by a note, a constant whose numbers are
withheld, two binding constants, a heatmap), the what-if menus, the window of Kₐ against
each source, the side panel's settings and their lock during a run, its links, the saved
figure — and the runs themselves: the worker's progress and its plain failures, the status
bar while a run goes and stops, a failed run leaving the last result shown, new data
discarding a run still going, and one run quoted the same number of fits everywhere.
"""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

import pytest

pytest.importorskip('PyQt6')

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QLabel  # noqa: E402

from core.assays.registry import AssayType  # noqa: E402
from core.pipeline.inputs import InputSpec  # noqa: E402
from core.pipeline.sensitivity import SensitivityMode  # noqa: E402
from core.units import Q_  # noqa: E402
from gui import sensitivity as S  # noqa: E402
from gui.plotting.labels import STOPPING_TEXT  # noqa: E402
from gui.session_model import Change  # noqa: E402
from tests.unit.gui import sensitivity_results as F  # noqa: E402
from tests.unit.gui.session_setup import state_binding, status_messages  # noqa: E402
from tests.unit.gui.test_confidence_view import assert_card_fits, move_pointer  # noqa: E402
from tests.unit.gui.test_plot_navigation import NONE, ZOOM, _wheel  # noqa: E402

#: The demo titration, found from this file so the tests run from any directory.
IDA_DATA = str(Path(__file__).resolve().parents[3] / 'data' / 'IDA_system.txt')

#: The margin a source plot leaves at each end of its draw axis, as a share of it.
V_MARGIN = 0.03


@pytest.fixture
def session(qapp, monkeypatch):
    from gui.fitting_session import FittingSession

    def refuse(*args):
        raise AssertionError(f'a dialog would have blocked the test: {args[1:]}')

    for kind in ('warning', 'information', 'question'):
        monkeypatch.setattr(f'gui.fitting_session.QMessageBox.{kind}', refuse)

    made = FittingSession()
    made.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    made.resize(1200, 800)
    made.show()
    made.show_view('Sensitivity')
    yield made
    made.model.shutdown()
    made.close()


def _hold(session, result, note=None) -> None:
    """Hold *result* as the session's sensitivity run, shown or hidden behind *note*."""
    model = session.model
    state_binding(session, assay_type=AssayType[result.assay_type])
    model._sensitivity_result = result
    model._sensitivity_note = note
    model.changed.emit(Change.SENSITIVITY)


def test_building_a_session_and_drawing_a_run_flashes_no_window(qapp):
    """A widget shown before it has a parent is a window of its own for that moment: on a desktop it flashes."""
    from PyQt6.QtCore import QEvent, QObject
    from PyQt6.QtWidgets import QWidget

    from gui.fitting_session import FittingSession

    class Shown(QObject):
        def __init__(self):
            super().__init__()
            self.windows = []

        def eventFilter(self, obj, event):
            if (
                event.type() == QEvent.Type.Show
                and isinstance(obj, QWidget)
                and obj.isWindow()
                and not obj.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
            ):
                self.windows.append(type(obj).__name__)
            return False

    shown = Shown()
    qapp.installEventFilter(shown)
    try:
        made = FittingSession()
        made.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        made.show()
        made.show_view('Sensitivity')
        for result in (F.sobol_result(), F.two_ka_result()):
            _hold(made, result)
        qapp.processEvents()
    finally:
        qapp.removeEventFilter(shown)
    assert shown.windows == []
    made.model.shutdown()
    made.close()


def test_before_any_run_the_view_says_what_to_do_with_the_platform_s_shortcut(session):
    from PyQt6.QtGui import QKeySequence

    view = session._sensitivity
    shortcut = QKeySequence('Ctrl+R').toString(QKeySequence.SequenceFormat.NativeText)

    assert not view.empty.isHidden() and f'Run analysis ({shortcut})' in view.empty.text()
    assert not view.has_plot() and view.blocks_host.isHidden()
    assert session.view_badge('Sensitivity') == S.badge(None, session.model.analysis)


def test_a_sobol_run_draws_its_spread_samples_shares_budget_and_what_if(session):
    _hold(session, F.sobol_result())
    view = session._sensitivity

    assert view.empty.isHidden() and len(view.histograms) == len(view.charts) == len(view.tables) == 1
    assert [c.title for c in view.callouts] == ['Not a confidence interval']
    (table,) = view.tables
    assert table.texts()[0][0] == 'Guest (titrant)'
    assert session.view_badge('Sensitivity').startswith('Sobol’ · N = 20')


def test_the_what_if_menus_answer_for_the_source_and_reduction_chosen(session):
    result = F.sobol_result()
    _hold(session, result)
    pick, to, sentence, detail, _state = session._sensitivity.what_ifs['Ka_guest']
    first = detail.text()

    pick.chosen.emit(2)  # Kₐ,dye, the third source by its share
    to.chosen.emit(3)  # taken as exact
    expected = S.what_if_answer(result, 'Ka_guest', 'Ka_dye', 0.0)

    assert detail.text() == expected.detail != first
    assert expected.after in sentence.text() and to.text == 'Exact'


def test_a_withheld_constant_shows_its_reason_in_place_of_its_shares(session):
    result = F.sobol_result()
    result.withheld = {'Ka_guest': 'baseline_on_bound'}
    _hold(session, result)
    view = session._sensitivity

    assert not view.charts and not view.tables and not view.what_ifs
    assert len(view.histograms) == 1, 'the samples stay on show'


def test_two_binding_constants_get_a_block_each_under_the_run_s_own_callouts(session):
    """A callout about the run stands above both blocks, not inside the first one."""
    _hold(session, F.two_ka_result())
    view = session._sensitivity
    assert [b.key for b in view.blocks] == ['Ka_HG', 'Ka_HG2']
    assert len(view.charts) == len(view.tables) == 2
    assert [c.title for c in view.callouts] == ['Not a confidence interval']
    first_name = min((w for w in view.content.findChildren(QLabel) if w.text() == view.blocks[0].name), key=_top)
    assert _top(view.callout_host) + view.callout_host.height() <= _top(first_name)


def _top(widget) -> int:
    return widget.mapTo(widget.window(), widget.rect().topLeft()).y()


def test_a_run_hidden_by_a_note_shows_the_note_and_none_of_its_numbers(session):
    """The canvas and This run alike: a run that no longer describes the data gives none of its facts."""
    note = 'The input uncertainties have changed since this analysis; set them back, or run the analysis again.'
    result = F.sobol_result()
    result.seed_used = 424242
    _hold(session, result, note=note)
    view = session._sensitivity
    assert [(c.title, c.body) for c in view.callouts] == [('Results hidden', note)]
    assert not view.has_plot() and view.blocks_host.isHidden()
    texts = [label.text() for label in view.sections['this run'].findChildren(QLabel)]
    assert not any('424242' in t or 'Samples fitted' in t for t in texts)
    _hold(session, result)
    texts = [label.text() for label in view.sections['this run'].findChildren(QLabel)]
    assert '424242' in texts, 'shown again, its facts come back'


def test_an_assay_with_no_association_constant_offers_no_analysis_and_says_why(session):
    state_binding(session, assay_type=AssayType.DYE_ALONE)
    view = session._sensitivity
    assert view.empty.text() == S.NO_KA and not view.unavailable.isHidden()
    assert all(section.isHidden() for section in view.sections.values())
    assert not view.has_plot() and session.view_badge('Sensitivity') is None
    session.model.load_files([IDA_DATA])
    refusal = session.model.sensitivity_refusal()
    assert refusal is not None and 'no association constant' in refusal.message
    state_binding(session, assay_type=AssayType.IDA)
    assert view.unavailable.isHidden() and not view.sections['run'].isHidden()


def test_a_heatmap_reads_the_cell_under_the_pointer_and_the_entered_one_without(session):
    _hold(session, F.heatmap_result())
    (figure,) = session._sensitivity.heatmap_figures

    assert figure.card.title == S.heatmap_readout(figure.hm, 1, 1)[0]
    figure.show_cell(2, 0)
    assert figure.card.title == S.heatmap_readout(figure.hm, 2, 0)[0]
    assert figure.cell.isVisible()
    assert session.view_badge('Sensitivity') == S.badge(F.heatmap_result(), session.model.analysis)


def test_the_heatmap_card_fits_the_cell_it_reads_and_keeps_its_size(qapp, session):
    _hold(session, F.heatmap_result())
    qapp.processEvents()
    (figure,) = session._sensitivity.heatmap_figures
    hm = figure.hm

    move_pointer(qapp, figure, hm.x[2], hm.y[0])
    assert figure.cell.isVisible() and figure.card.title == S.heatmap_readout(hm, 2, 0)[0]
    assert_card_fits(figure)
    size = figure.card.size()
    move_pointer(qapp, figure, hm.x[0], hm.y[0])
    move_pointer(qapp, figure, hm.x[2], hm.y[0])
    assert figure.card.size() == size, 'the same reading takes the same room'


@pytest.fixture
def off_screen_windows(monkeypatch):
    """Windows a view opens of its own are laid out off screen, as the session is."""
    from PyQt6.QtWidgets import QWidget

    from gui.views import sensitivity as V

    def show(window):
        window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        QWidget.show(window)

    monkeypatch.setattr(V.SourcePlotsWindow, 'show', show)


def _drawn_labels(pw) -> set[str]:
    """The tick labels the bottom axis of *pw* draws, those it leaves out for want of room excluded."""
    from PyQt6.QtGui import QImage, QPainter

    image = QImage(10, 10, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        _, _, texts = pw.getPlotItem().getAxis('bottom').generateDrawSpecs(painter)
    finally:
        painter.end()
    return {text for _, _, text in texts}


def test_plot_against_each_source_opens_on_the_range_entered(qapp, session, off_screen_windows):
    """Each plot opens on its source's own draw axis, with a margin of a fixed share of it, and draws the label of
    every tick it was given — a range's two ends among them — however wide the window; zoom and pan stay
    available, and Reset view frames each plot as it opened."""
    result = F.ranged_result()
    _hold(session, result)
    view = session._sensitivity
    view.open_source_plots('Ka_guest')
    (window,) = view.windows
    expected = {p.name: p for p in S.source_plots(result, 'Ka_guest')[0]}
    assert len(window.plots) == len(expected) == 3
    assert {'−4.65', '2.33'} <= {text for p in expected.values() for _v, text in p.x_ticks}
    for width in (None, 1500, 500):
        if width is not None:
            window.resize(width, window.height())
        qapp.processEvents()
        for pw, plot in zip(window.plots, expected.values()):
            lo, hi = plot.x_range
            margin = V_MARGIN * (hi - lo)
            assert pw.getPlotItem().viewRange()[0] == pytest.approx((lo - margin, hi + margin))
            assert _drawn_labels(pw) == {text for _v, text in plot.x_ticks}, (width, plot.name)

    pw = window.plots[0]
    opened = _shown(pw)
    assert not window.navigation.tool.isEnabled()
    _wheel(pw, ZOOM, notches=-2)
    assert _shown(pw) != pytest.approx(opened)
    window.navigation.tool.click()
    assert _shown(pw) == pytest.approx(opened)
    assert not window.navigation.tool.isEnabled()
    window.close()


def _shown(pw) -> list[float]:
    return [v for side in pw.getPlotItem().viewRange() for v in side]


def test_source_plots_keep_their_zoom_through_a_theme_change_and_pass_a_plain_wheel_to_the_window(
    qapp, session, off_screen_windows
):
    from gui.design.appearance import appearance

    _hold(session, F.ranged_result())
    view = session._sensitivity
    view.open_source_plots('Ka_guest')
    (window,) = view.windows
    window.resize(window.width(), 300)
    qapp.processEvents()
    bar = window.area.verticalScrollBar()
    assert bar.maximum() > 0
    framed = [v for pw in window.plots for v in _shown(pw)]

    event = _wheel(window.plots[0], NONE)
    assert not event.isAccepted()
    assert bar.value() > 0
    assert [v for pw in window.plots for v in _shown(pw)] == pytest.approx(framed)

    _wheel(window.plots[1], ZOOM, notches=-2)
    zoomed = [v for pw in window.plots for v in _shown(pw)]
    try:
        appearance().set_mode('dark')
        qapp.processEvents()
        assert [v for pw in window.plots for v in _shown(pw)] == pytest.approx(zoomed)
        assert window.navigation.tool.isEnabled()
    finally:
        appearance().set_mode('light')
    window.close()


def test_an_open_window_of_source_plots_follows_the_theme(session, off_screen_windows):
    from gui.design.appearance import appearance
    from gui.design.tokens import Theme

    _hold(session, F.sobol_result())
    view = session._sensitivity
    view.open_source_plots('Ka_guest')
    (window,) = view.windows
    try:
        for mode in ('dark', 'light'):
            appearance().set_mode(mode)
            surface = Theme(dark=mode == 'dark')['bg-surface'].lower()
            assert window.plots and all(pw.backgroundBrush().color().name() == surface for pw in window.plots)
    finally:
        appearance().set_mode('light')
        window.close()


def test_the_what_if_chosen_and_an_open_window_outlive_a_redraw_of_the_same_run(session, off_screen_windows):
    """Notes, a fit starting, Display or a theme change redraw the view; the run on show is the same one."""
    from gui.design.appearance import appearance

    _hold(session, F.sobol_result())
    view = session._sensitivity
    pick, to, _sentence, _detail, state = view.what_ifs['Ka_guest']
    pick.chosen.emit(2)
    to.chosen.emit(3)
    view.open_source_plots('Ka_guest')
    (window,) = view.windows

    session.model.changed.emit(Change.RESULTS)
    session.model.analysis_edited()
    appearance().set_mode('dark')
    appearance().set_mode('light')

    assert view.what_ifs['Ka_guest'][4] == [2, 3] and view.what_ifs['Ka_guest'][1].text == 'Exact'
    assert view.windows == [window]
    # A new run is another result: its what-if starts afresh and the window of the last one closes.
    _hold(session, F.sobol_result())
    assert view.what_ifs['Ka_guest'][4] == [0, S.WHAT_IF_RATIOS.index(S.WHAT_IF_START)] and not view.windows


def test_the_settings_show_what_the_mode_needs_and_lock_during_a_run(session):
    view = session._sensitivity
    assert not view.indices_part.isHidden() and view.heatmap_part.isHidden()

    view.mode.changed.emit(1)
    assert session.model.analysis.mode is SensitivityMode.HEATMAP
    assert view.indices_part.isHidden() and not view.heatmap_part.isHidden()

    view.set_locked(True)
    assert not any(c.isEnabled() for c in (view.mode, view.size, view.seed_check, view.x_axis, view.grid))
    assert view.axis.isEnabled(), 'Display feeds no run'
    view.set_locked(False)
    assert view.mode.isEnabled() and not view.seed.isEnabled(), 'the seed follows Fixed seed'


def test_a_heatmap_axis_problem_names_the_span_beside_the_settings(session):
    state_binding(session, assay_type=AssayType.IDA)
    session.model.uncertainty.set_specs({'h0': InputSpec.sigma_pct(40.0), 'd0': InputSpec.sigma_pct(5.0)})
    session.model.uncertainty_edited()
    form = session.model.analysis
    form.mode, form.x_key, form.y_key, form.x_span = SensitivityMode.HEATMAP, 'h0', 'd0', 3.0
    session.model.analysis_edited()

    problem = session._sensitivity.problem
    assert not problem.isHidden() and 'from −3σ to +3σ' in problem.text.text()
    form.x_span = 2.0
    session.model.analysis_edited()
    assert problem.isHidden()


def test_the_links_ask_for_the_view_they_name(session):
    asked = []
    session.view_requested.connect(asked.append)
    session._sensitivity.edit_inputs.click()
    assert asked == ['Input uncertainty']


def test_the_saved_figure_is_drawn_whatever_the_run(session, tmp_path):
    for result in (F.sobol_result(), F.heatmap_result(), F.two_ka_result()):
        _hold(session, result)
        path = tmp_path / f'{result.mode.value}{len(result.ka_keys)}.png'
        session._sensitivity.export_image(str(path))
        assert path.stat().st_size > 0


def _figure_texts(view) -> list[str]:
    from gui.design.components import PaintedNote, PaintedText

    figure = view.export_figure()
    try:
        return [w.text for w in figure.findChildren((PaintedText, PaintedNote))]
    finally:
        figure.close()
        figure.deleteLater()


def test_the_saved_figure_carries_the_notes_that_qualify_its_numbers(session):
    result = F.sobol_result()
    result.withheld = {'Ka_guest': 'baseline_on_bound'}
    _hold(session, result)
    texts = _figure_texts(session._sensitivity)
    assert not any('callout' in t for t in texts)
    assert any('ran to the edge of its bounds' in t for t in texts)
    assert not any('fold' in t for t in texts), "no figure is read off a withheld constant's samples"

    result = F.sobol_result()
    result.n_on_bound = {'Ka_guest': 7}
    _hold(session, result)
    texts = _figure_texts(session._sensitivity)
    assert any(t.startswith('Fits on the Kₐ bounds') for t in texts)
    assert any(t.startswith('Not a confidence interval') for t in texts)


def _near(image, colour: str, tol: int):
    """Pixels of *image* within *tol* of *colour* in every channel."""
    import numpy as np
    from PyQt6.QtGui import QColor, QImage

    image = image.convertToFormat(QImage.Format.Format_RGB32)
    bits = image.constBits()
    bits.setsize(image.sizeInBytes())
    bgra = np.frombuffer(bits, np.uint8).reshape(image.height(), image.bytesPerLine() // 4, 4)[:, : image.width()]
    c = QColor(colour)
    target = np.array([c.blue(), c.green(), c.red()])
    return int((np.abs(bgra[..., :3].astype(int) - target) <= tol).all(axis=-1).sum())


def test_the_saved_figure_is_light_on_white_in_a_dark_window(session, tmp_path):
    """Surface, text, notes, samples and bars all in the light theme: a part drawn in the window's dark theme
    leaves its dark text or dark bars, colours no light mark has, on the white."""
    from PyQt6.QtGui import QColor, QImage

    from gui.design.appearance import appearance
    from gui.design.tokens import Theme

    _hold(session, F.sobol_result())
    appearance().set_mode('dark')
    try:
        path = tmp_path / 'sensitivity.png'
        session._sensitivity.export_image(str(path))
    finally:
        appearance().set_mode('light')
    image = QImage(str(path))
    light, dark = Theme(dark=False), Theme(dark=True)

    assert QColor(image.pixel(2, 2)).name() == '#ffffff'
    assert _near(image, '#ffffff', 2) > 0.5 * image.width() * image.height()
    # The dark surface is a shade off the light text-primary, so an edge pixel of black text may match it:
    # a surface left behind the figure would be thousands of them.
    assert _near(image, dark['bg-surface'], 0) < 0.01 * image.width() * image.height()
    assert _near(image, light['text-secondary'], 3) > 400 and _near(image, light['series-1'], 3) > 400
    # Antialiased light text never lands this close to the dark tokens; a part drawn dark puts hundreds there.
    assert _near(image, dark['text-secondary'], 3) < 50
    assert _near(image, dark['series-1'], 3) < 50


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


def test_worker_throttles_progress_but_never_drops_the_last_count(qapp, monkeypatch):
    from gui import workers

    monkeypatch.setattr(workers, 'run_sensitivity', F.fake_run(1000))
    worker = workers.SensitivityWorker(None, None, {}, None, None)
    events = []
    worker.progress.connect(lambda done, total: events.append((done, total)))
    worker.finished.connect(lambda result: events.append('finished'))

    worker.run()  # in this thread, so every signal is delivered on the spot

    assert events == [(1, 1000), (1000, 1000), 'finished']


def test_worker_reports_an_unexpected_failure_in_plain_words(qapp, monkeypatch):
    from core.pipeline.sensitivity import SensitivityRunError
    from gui import workers

    def fail(*args, **kwargs):
        raise RuntimeError('broadcast shapes (3,) (4,) mismatch in _jansen')

    monkeypatch.setattr(workers, 'run_sensitivity', fail)
    worker = workers.SensitivityWorker(None, None, {}, None, None)
    messages = []
    worker.error.connect(messages.append)
    worker.run()
    assert len(messages) == 1 and 'stopped on an unexpected error' in messages[0] and '_jansen' not in messages[0]

    def written(*args, **kwargs):
        raise SensitivityRunError('The analysis stopped because one of the re-fits could not be completed. Retry.')

    monkeypatch.setattr(workers, 'run_sensitivity', written)
    worker.run()
    assert messages[-1] == 'The analysis stopped because one of the re-fits could not be completed. Retry.'


def test_worker_delivers_a_held_back_count_as_soon_as_a_cancel_is_seen(qapp, monkeypatch):
    """After a cancel the driver waits for the fits still running; the count does not wait with it."""
    from gui import workers

    events = []

    def run(*args, progress, should_cancel, **kwargs):
        for done in range(1, 51):
            progress(done, 1000)
        worker.cancel()
        assert should_cancel()
        events.append('driver waits for the running fits')
        return F.sobol_result()

    monkeypatch.setattr(workers, 'run_sensitivity', run)
    worker = workers.SensitivityWorker(None, None, {}, None, None)
    worker.progress.connect(lambda done, total: events.append((done, total)))
    worker.run()
    assert events == [(1, 1000), (50, 1000), 'driver waits for the running fits']


@pytest.fixture
def demo_session(qapp, monkeypatch):
    """A session with the demo IDA data and σ 5 % on each of its four inputs; its warnings are collected."""
    from PyQt6.QtWidgets import QMessageBox

    from gui.fitting_session import FittingSession

    warnings = []
    monkeypatch.setattr('gui.fitting_session.QMessageBox.warning', lambda *args: warnings.append(args))
    monkeypatch.setattr('gui.fitting_session.QMessageBox.question', lambda *args: QMessageBox.StandardButton.Yes)
    made = FittingSession()
    state_binding(made, assay_type=AssayType.IDA)
    made.model.load_files([IDA_DATA])
    form = made.model.uncertainty
    form.set_specs({key: InputSpec.sigma_pct(5.0) for key in form.keys})
    made.model.uncertainty_edited()
    made.warnings = warnings
    yield made
    made.model.shutdown()
    made.close()


def _wait_for_worker(session, qapp):
    worker = session.model._sensitivity_worker
    deadline = time.monotonic() + 30
    while not worker.isFinished():
        assert time.monotonic() < deadline, 'timed out waiting for the sensitivity worker'
        qapp.processEvents()
        time.sleep(0.01)
    worker.wait()
    qapp.processEvents()


def test_a_run_counts_its_fits_on_the_status_bar_and_estimates_the_time_left(qapp, monkeypatch, demo_session):
    from gui import workers

    monkeypatch.setattr(workers, 'run_sensitivity', F.fake_run(40, pause=0.01))
    messages = status_messages(demo_session.model)

    demo_session.run_sensitivity()
    assert demo_session._sensitivity.locked, 'the settings that feed the run lock while it goes'
    _wait_for_worker(demo_session, qapp)

    assert demo_session.warnings == [] and demo_session.model.sensitivity_result is not None
    assert not demo_session._sensitivity.locked
    assert any(m.startswith('Analysing') and m.endswith('left') for m in messages)
    assert [m for m in messages if m.startswith('Analysing')][-1] == 'Analysing — 40 of 40'
    assert demo_session._sensitivity.charts, 'the finished run is drawn'


def test_a_stopping_run_says_so_on_the_status_bar_and_not_its_counts(qapp, monkeypatch, demo_session):
    from gui import workers

    def run(*args, progress, should_cancel, **kwargs):
        progress(1, 1000)
        while not should_cancel():
            time.sleep(0.005)
        for done in (2, 3, 4):  # the fits that were already running
            progress(done, 1000)
        return F.sobol_result()

    monkeypatch.setattr(workers, 'run_sensitivity', run)
    messages = status_messages(demo_session.model)

    demo_session.run_sensitivity()
    demo_session.run_primary('Sensitivity')  # the toolbar's Stop
    stopping_from = len(messages) - 1
    _wait_for_worker(demo_session, qapp)

    assert demo_session.warnings == []
    assert messages[stopping_from] == STOPPING_TEXT
    assert not [m for m in messages[stopping_from:] if m.startswith('Analysing')]


def test_a_failed_run_says_why_and_keeps_the_last_result_shown(qapp, monkeypatch, demo_session):
    from gui import workers

    def failing(*args, progress, **kwargs):
        progress(1, 97)
        raise ValueError('The unperturbed (baseline) fit did not converge.')

    monkeypatch.setattr(workers, 'run_sensitivity', F.fake_run(5))
    demo_session.run_sensitivity()
    _wait_for_worker(demo_session, qapp)
    earlier = demo_session.model.sensitivity_result

    monkeypatch.setattr(workers, 'run_sensitivity', failing)
    demo_session.run_sensitivity()
    _wait_for_worker(demo_session, qapp)

    view = demo_session._sensitivity
    assert len(demo_session.warnings) == 1
    assert demo_session.model.sensitivity_result is earlier and view.charts
    assert view.callouts[0].title == 'Analysis failed'


def test_new_data_discards_a_run_still_going(qapp, monkeypatch, demo_session):
    from gui import workers

    def slow(*args, progress, should_cancel, **kwargs):
        while not should_cancel():
            time.sleep(0.005)
        return F.sobol_result()

    monkeypatch.setattr(workers, 'run_sensitivity', slow)
    demo_session.run_sensitivity()
    worker = demo_session.model._sensitivity_worker

    demo_session.model.load_files([IDA_DATA])
    worker.wait()
    qapp.processEvents()

    assert demo_session.warnings == [] and demo_session.model.sensitivity_result is None
    assert not demo_session._sensitivity.has_plot()


def test_a_run_uses_the_bounds_and_the_settings_stated(qapp, monkeypatch, demo_session):
    from gui import workers

    seen = {}

    def capture(ms, assay_cls, conditions, fit_config, sens_config, **kwargs):
        seen.update(bounds=fit_config.custom_bounds, config=sens_config)
        return F.sobol_result()

    monkeypatch.setattr(workers, 'run_sensitivity', capture)
    state_binding(demo_session, bounds={'I0': (0.0, 5000.0)})
    form = demo_session.model.analysis
    form.mode, form.x_key, form.y_key, form.grid, form.x_span = SensitivityMode.HEATMAP, 'h0', 'd0', 21, 1.0
    demo_session.model.analysis_edited()

    demo_session.run_sensitivity()
    _wait_for_worker(demo_session, qapp)

    assert demo_session.warnings == []
    assert seen['bounds']['I0'][1] == Q_(5000.0, 'au')
    config = seen['config']
    assert (config.mode, config.n_steps, config.x_span, config.y_span) == (SensitivityMode.HEATMAP, 21, 1.0, 2.0)


def test_one_run_is_quoted_the_same_number_of_fits_wherever_it_is_counted(qapp, monkeypatch, demo_session):
    """The cost dialog, the status bar while it runs and the message at the end size the same run, alike."""
    from PyQt6.QtWidgets import QMessageBox

    from core.pipeline.inputs import perturbable_inputs
    from core.pipeline.sensitivity import estimated_fit_count
    from gui import workers

    def run(ms, assay_cls, conditions, fit_config, sens_config, *, progress, **kwargs):
        total = estimated_fit_count(sens_config, len(perturbable_inputs(conditions))) + 1
        progress(total, total)
        result = F.made_on(F.sobol_result(), ms, conditions)
        return replace(result, config=sens_config, n_success=total - 1, n_total=total - 1, n_planned=total - 1)

    monkeypatch.setattr(workers, 'run_sensitivity', run)
    asked = []
    monkeypatch.setattr('gui.session_model.LONG_RUN_SOLVES', 0)  # so the cost dialog is offered
    monkeypatch.setattr(
        'gui.fitting_session.QMessageBox.question',
        lambda parent, title, text, *args: (asked.append(text), QMessageBox.StandardButton.Yes)[1],
    )
    messages = status_messages(demo_session.model)

    demo_session.run_sensitivity()
    _wait_for_worker(demo_session, qapp)

    counted = demo_session.model._progress[1]
    assert demo_session.warnings == [] and counted >= 1000
    assert f'{counted:,} times' in asked[0]
    assert f'Analysing — {counted:,} of {counted:,}' in messages
    assert messages[-1] == f'Sensitivity complete — {counted:,} of {counted:,} fits succeeded'
    stats = {s.name: s.value for s in S.this_run(demo_session.model.sensitivity_result)}
    assert stats['Fits'] == f'{counted:,}'
    assert f'{counted:,} fits in all' in demo_session._sensitivity.size_note.text()


def test_a_seed_typed_and_run_at_once_is_the_seed_the_run_uses(qapp, monkeypatch, demo_session):
    """Run analysis straight from the field, with no Return or Tab first: the typed seed is the one used."""
    from PyQt6.QtTest import QTest

    from gui import workers

    seen = {}

    def capture(ms, assay_cls, conditions, fit_config, sens_config, **kwargs):
        seen['config'] = sens_config
        return F.made_on(replace(F.sobol_result(), config=sens_config), ms, conditions)

    monkeypatch.setattr(workers, 'run_sensitivity', capture)
    view = demo_session._sensitivity
    view.seed_check.toggled.emit(True)
    QTest.keyClicks(view.seed.editor, '424242')
    demo_session.model.changed.emit(Change.RESULTS)  # any redraw while the field is being typed in

    assert view.seed.editor.text().endswith('424242')
    demo_session.run_primary('Sensitivity')
    _wait_for_worker(demo_session, qapp)
    assert seen['config'].seed == int(view.seed.editor.text())
