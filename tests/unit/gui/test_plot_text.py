"""Every plot draws its text at the session's plot text step and keeps it whole (DESIGN.md §2, §7, §8).

The titration, Ka confidence's profiles, strips and joint region, Sensitivity's sample
histogram, heatmap and plots against each source, and Simulation's titration and species
share one scale of plot text, :data:`~gui.design.tokens.PLOT_TEXT`: a session's Plot
appearance chooses its step, on screen and in the figures saved from it. The axes grow with the text, so
at every step an axis title stands whole inside its plot, clear of the tick labels.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip('PyQt6')

from PyQt6.QtCore import QRectF, Qt  # noqa: E402

from core.pipeline.varpro import KaInterval  # noqa: E402
from gui.design.tokens import PLOT_TEXT, plot_font  # noqa: E402
from gui.plot_appearance import PlotAppearance  # noqa: E402
from tests.unit.gui import layout_rules  # noqa: E402
from tests.unit.gui import sensitivity_results as F  # noqa: E402
from tests.unit.gui.test_confidence_view import _show, _two_ka_profiles  # noqa: E402
from tests.unit.gui.test_results import _stepwise  # noqa: E402
from tests.unit.gui.test_sensitivity_view import _hold  # noqa: E402

STEPS = tuple(PLOT_TEXT)


@pytest.fixture
def session(qapp, monkeypatch):
    from gui.fitting_session import FittingSession

    def refuse(*args):
        raise AssertionError(f'a dialog would have blocked the test: {args[1:]}')

    for kind in ('warning', 'information', 'question'):
        monkeypatch.setattr(f'gui.fitting_session.QMessageBox.{kind}', refuse)
    made = FittingSession()
    made.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    made.resize(1440, 900)
    made.show()
    yield made
    made.model.shutdown()
    made.close()


def _sizes(pw) -> set[tuple[str, int, int]]:
    """``(side, tick px, title px)`` of each axis of *pw* that draws its values or its title."""
    found = set()
    for side in ('left', 'bottom'):
        axis = pw.getPlotItem().getAxis(side)
        if not axis.isVisible():
            continue
        title = int(axis.labelStyle['font-size'].removesuffix('px')) if axis.label.isVisible() else 0
        found.add((side, axis.style['tickFont'].pixelSize(), title))
    return found


def _drawn_at(pw, step: str) -> bool:
    """Whether every axis of *pw* draws its tick labels, and any title it shows, at *step*."""
    tick, title = plot_font(step, 'tick').pixelSize(), plot_font(step, 'title').pixelSize()
    return all(t == tick and h in (0, title) for _side, t, h in _sizes(pw))


def test_the_plot_text_steps_are_the_ones_chosen():
    """Tick labels 16, 18 and 20 px, axis titles 2 px above them (DESIGN.md §2)."""
    assert PLOT_TEXT == {'standard': (16, 18), 'large': (18, 20), 'larger': (20, 22)}


def _two_constants(session) -> None:
    """Show a fit of two binding constants with their profiles and joint region."""
    _show(session, _stepwise(KaInterval(1.1e3, 8.0e3, False, False, 0.95, 16)), _two_ka_profiles())


def test_ka_confidence_draws_every_plot_at_the_session_s_text_size(qapp, session):
    """Each profile, its strip and the joint region follow Plot appearance at once, and so does the saved figure."""
    _two_constants(session)
    view = session._confidence
    for step in STEPS:
        session.model.set_plot_appearance(PlotAppearance(text_size=step))
        plots = [w for f in view.figures for w in (f.main, f.strip)] + [view.region_figure.main]
        assert all(_drawn_at(pw, step) for pw in plots), step
        figure = view.export_figure()
        try:
            from gui.views.confidence import ProfileFigure, RegionFigure

            saved = [w for f in figure.findChildren(ProfileFigure) for w in (f.main, f.strip)]
            saved += [f.main for f in figure.findChildren(RegionFigure)]
            assert saved and all(_drawn_at(pw, step) for pw in saved), step
        finally:
            figure.close()


def test_sensitivity_draws_its_samples_heatmap_and_source_plots_at_the_session_s_text_size(qapp, session, monkeypatch):
    from PyQt6.QtWidgets import QWidget

    from gui.views import sensitivity as V

    def show(window):
        window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        QWidget.show(window)

    monkeypatch.setattr(V.SourcePlotsWindow, 'show', show)
    session.show_view('Sensitivity')
    view = session._sensitivity
    _hold(session, F.ranged_result())
    view.open_source_plots('Ka_guest')
    (window,) = view.windows
    for step in STEPS:
        session.model.set_plot_appearance(PlotAppearance(text_size=step))
        assert all(h.tick_font.pixelSize() == plot_font(step, 'tick').pixelSize() for h in view.histograms), step
        assert view.histograms and all(_drawn_at(pw, step) for pw in window.plots), step
    window.close()

    _hold(session, F.heatmap_result())
    for step in STEPS:
        session.model.set_plot_appearance(PlotAppearance(text_size=step))
        (figure,) = view.heatmap_figures
        assert _drawn_at(figure.main, step) and figure.bar.tick_font.pixelSize() == plot_font(step, 'tick').pixelSize()


def test_simulation_draws_at_the_sessions_plot_text(qapp, session):
    session.show_view('Simulation')
    view = session._simulation
    for step in STEPS:
        session.model.set_plot_appearance(PlotAppearance(text_size=step))
        assert _drawn_at(view.plots.signal_pw, step) and _drawn_at(view.plots.species_pw, step), step


# ── Whole at every step ──────────────────────────────────────────────────────────


@pytest.mark.parametrize('step', STEPS)
def test_every_axis_title_is_whole_and_clear_of_the_tick_labels_at_every_step(qapp, session, monkeypatch, step):
    """The rule of :func:`layout_rules.cut_axis_text`, held by each kind of plot of the app at each step."""
    session.model.set_plot_appearance(PlotAppearance(text_size=step))
    found = {}
    _two_constants(session)
    session.show_view('Ka confidence')
    qapp.processEvents()
    found['Ka confidence'] = layout_rules.cut_axis_text(session)
    _hold(session, F.heatmap_result())
    session.show_view('Sensitivity')
    qapp.processEvents()
    found['Sensitivity'] = layout_rules.cut_axis_text(session)
    assert session.set_up_demo_ida()
    session.show_view('Measurements')
    qapp.processEvents()
    found['Measurements'] = layout_rules.cut_axis_text(session)
    session.show_view('Simulation')
    qapp.processEvents()
    found['Simulation'] = layout_rules.cut_axis_text(session)

    assert {where: cut for where, cut in found.items() if cut} == {}


def test_the_axis_text_rule_catches_a_title_over_the_tick_labels(qapp):
    """A left axis too narrow for its tick labels and its title draws one over the other: the rule names it."""
    import pyqtgraph as pg

    from gui.design.appearance import theme
    from gui.design.plot_theme import apply_plot_theme

    pw = pg.PlotWidget()
    pw.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    apply_plot_theme(pw, theme(), 'Guest (µM)', 'Signal (a.u.)', 'larger')
    pw.getPlotItem().getAxis('left').setWidth(30)
    pw.plot(np.arange(5.0), np.arange(5.0) * 1000)
    pw.resize(600, 400)
    pw.show()
    qapp.processEvents()

    assert layout_rules.axis_text_problems(pw) != []
    assert isinstance(layout_rules.title_rect(pw.getPlotItem().getAxis('left')), QRectF)
    pw.close()


def test_the_names_on_a_profile_s_strip_stand_whole_clear_of_their_bars_and_on_the_plot_s_axis(qapp, demo):
    """Each reading's name sits whole inside its lane of the strip, ending before the lane's first bar, however large the
    plot text and however the figure was sized on its way to its width; where a name needs the axis opened further left,
    the profile above opens with it, so the strip's Ka stay under the plot's."""
    from dataclasses import replace

    import pyqtgraph as pg

    from gui import confidence as CF
    from gui.design.appearance import theme
    from gui.design.tokens import space
    from gui.views.confidence import ProfileFigure

    fit, profile = demo
    (plot,) = [CF.profile_plot(fit, p) for p in profile.profiles.values()]
    lo, hi = plot.x_range
    # The reported reading's first bar starts a twentieth of the axis in: no name of either reading fits before it.
    near_edge = [(10 ** (lo + 0.05 * (hi - lo)), 10 ** (lo + 0.3 * (hi - lo)))]
    curve = plot.curves[0]
    two = replace(
        plot,
        curves=[replace(curve, label='Inputs as entered'), replace(curve, label='Input-aware', stretches=near_edge)],
    )
    for step in STEPS:
        figure = ProfileFigure(theme(), two, step)
        figure.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        figure.resize(520, 420)  # as a window lays the canvas out on its way to its width
        figure.show()
        qapp.processEvents()
        figure.resize(900, 420)
        qapp.processEvents()
        figure.strip.grab()  # an in-plot label takes its place in the view as the plot paints
        strip = figure.strip.getPlotItem()
        vb = strip.getViewBox()
        area = vb.sceneBoundingRect()
        names = {i.textItem.toPlainText(): i for i in strip.items if isinstance(i, pg.TextItem)}

        def text(n):
            margin = n.textItem.document().documentMargin()
            return n.sceneBoundingRect().adjusted(margin, margin, -margin, -margin)

        assert vb.viewRange()[0] == pytest.approx(figure.main.getPlotItem().getViewBox().viewRange()[0]), step
        assert set(names) == {'Inputs as entered', 'Input-aware'}, step
        for label, name in names.items():
            assert area.contains(text(name)), (step, label, text(name), area)
        for c in two.curves:
            first_bar = vb.mapViewToScene(pg.Point(np.log10(c.stretches[0][0]), 0)).x()
            assert text(names[c.label]).right() + space(1) <= first_bar, (step, c.label)
        figure.close()


@pytest.mark.parametrize('step', STEPS)
def test_a_painted_axis_gives_each_tick_label_a_line_of_its_text(qapp, step):
    """The sample histogram's tick labels are boxed as tall as a line of the plot text, so none is cut short."""
    from PyQt6.QtGui import QFontMetrics

    from gui.design import components as C

    fm = QFontMetrics(plot_font(step, 'tick'))
    boxes = C.spaced_ticks([(1.0, '1'), (10.0, '10'), (100.0, '100')], lambda v: 100.0 * np.log10(v), fm, 0, 400)
    assert boxes and all(box.height() >= fm.height() for _text, box in boxes)


@pytest.mark.parametrize('step', STEPS)
def test_an_axis_title_set_after_the_plot_is_laid_out_stands_whole_and_centred(qapp, step):
    """A saved figure sets its titles once its plots are sized (Simulation's does): each is placed again
    as it is set, whole inside the plot and centred on its axis, not where the last title put it."""
    import pyqtgraph as pg

    from gui.design.appearance import theme
    from gui.design.plot_theme import apply_plot_theme

    pw = pg.PlotWidget()
    pw.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    apply_plot_theme(pw, theme(), '', '', step)
    pw.resize(900, 400)
    pw.show()
    qapp.processEvents()
    bottom = pw.getPlotItem().getAxis('bottom')
    bottom.setLabel('Guest (µM)')

    title = layout_rules.title_rect(bottom)
    assert layout_rules.axis_text_problems(pw) == []
    assert title.center().x() == pytest.approx(bottom.sceneBoundingRect().center().x(), abs=1)
    pw.close()
