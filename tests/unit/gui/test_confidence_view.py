"""Widget tests for Ka confidence (:mod:`gui.views.confidence`): what the view does with what :mod:`gui.confidence` says.

What the text and the curves say is pinned by ``test_confidence.py``; here only the view's
own work: its states (no fit, the profile still being worked out, a profile that failed, a
fit with no binding constant), the callout's action and the guide link, the pointer's
readout, the enlarge tool, the stacked plots and joint region of two binding constants,
and the saved figure.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip('PyQt6')

from PyQt6.QtCore import QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QFontMetrics  # noqa: E402

from core.pipeline.profile import JointRegion, ProfileResult, ProfileSet  # noqa: E402
from core.pipeline.varpro import KaInterval  # noqa: E402
from gui import confidence as CF  # noqa: E402
from gui.design import components as C  # noqa: E402
from gui.design.tokens import font, space  # noqa: E402
from gui.session_model import Change  # noqa: E402
from tests.unit.gui.test_fit_results_view import _CONFLICT, _SHIFTS, _pixels_near  # noqa: E402
from tests.unit.gui.test_results import _stepwise, aware_result, result  # noqa: E402


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
    made.show_view('Ka confidence')
    yield made
    made.model._profile_worker = None
    made.close()


def _show(session, fit, profile=None, *, running=False, error=None) -> None:
    """Hold *fit* as the shown result with *profile* as its Ka profile, as a finished fit and profile are held."""
    model = session.model
    model._held_fit_results = [fit]
    model._profiled_fit = fit
    model._profile = profile
    model._profile_error = error
    model._profile_worker = object() if running else None
    model.changed.emit(Change.RESULTS | Change.PROFILE)


def test_before_any_fit_the_view_says_what_to_do_with_the_platform_s_shortcut(session):
    from PyQt6.QtGui import QKeySequence

    view = session._confidence
    shortcut = QKeySequence('Ctrl+R').toString(QKeySequence.SequenceFormat.NativeText)

    assert not view.empty.isHidden() and f'Run fit ({shortcut})' in view.empty.text()
    assert view.header_host.isHidden() and not view.has_plot()
    assert session.view_badge('Ka confidence') is None


def test_the_readings_show_at_once_and_the_curves_when_the_profile_arrives(qapp, session, demo):
    fit, profile = demo
    view = session._confidence

    _show(session, fit, running=True)
    assert not view.header_host.isHidden() and not view.has_plot()
    assert [c.body for c in view.callouts][-1] == CF.PENDING

    _show(session, fit, profile)
    assert view.has_plot() and CF.PENDING not in [c.body for c in view.callouts]
    assert session.view_badge('Ka confidence') == 'Profile likelihood · 95 %'


def test_a_profile_that_failed_says_why_in_plain_words_beside_the_readings(session, demo):
    fit, _profile = demo
    why = 'The range of Kₐ your data support could not be worked out:\nthe data leave too few points.'

    _show(session, fit, error=why)

    view = session._confidence
    assert not view.has_plot() and not view.header_host.isHidden()
    assert view.message.text() == CF.failed_sentence(why) and '\n' not in view.message.text()


def test_a_fit_with_no_binding_constant_says_there_is_nothing_to_profile(session):
    from dataclasses import replace

    _show(session, replace(result(), assay_type='DYE_ALONE', intervals={}, parameters={}))

    view = session._confidence
    assert view.empty.text() == CF.NO_KA and view.header_host.isHidden() and not view.has_plot()


def test_the_conflict_callout_opens_notes_at_the_input_shifts(qapp, session):
    _show(session, aware_result(shifts=_SHIFTS, diagnostics=_CONFLICT))
    side = session._views['Ka confidence'].side
    side.hide()
    requested: list[bool] = []
    session.side_panel_requested.connect(lambda: requested.append(True))
    (callout,) = [c for c in session._confidence.callout_host.findChildren(C.Callout) if c.action is not None]

    callout.action.click()
    qapp.processEvents()

    section = session._confidence.sections['conflict']
    assert callout.action.text() == CF.SHOW_SHIFTS and requested == [True]
    assert side.isVisible() and section.isVisible() and section.header._open


def test_reading_this_plot_opens_the_guide_at_ka_confidence(session, monkeypatch):
    from gui import fitting_session

    opened: list[str] = []
    monkeypatch.setattr(fitting_session, 'show_plot_guide', lambda _parent, key: opened.append(key))

    session._confidence.guide_link.click()

    assert opened == ['Ka confidence']


def test_the_card_reads_the_estimate_until_the_pointer_reads_another_ka(qapp, session, demo):
    fit, profile = demo
    _show(session, fit, profile)
    (figure,) = session._confidence.figures
    best = np.log10(fit.parameters['Ka_guest'].magnitude)
    assert figure.card.title == figure.plot.readout_title(best) and not figure.hair.isVisible()

    figure.show_at(best + 0.3)

    (_color, name, value, verdict, _quiet) = figure.card.rows[0]
    assert figure.card.title == figure.plot.readout_title(best + 0.3) and figure.hair.isVisible()
    assert (name, verdict) == ('Inputs as entered', CF.readout(figure.plot, best + 0.3)[0].verdict)
    assert value == CF.readout(figure.plot, best + 0.3)[0].value
    figure.leaveEvent(None)
    assert not figure.hair.isVisible() and figure.card.title == figure.plot.readout_title(best)


def move_pointer(qapp, figure, x: float, y: float) -> None:
    """Move the pointer to (*x*, *y*) in *figure*'s data coordinates, as the plot's scene reports a move."""
    vb = figure.main.getPlotItem().getViewBox()
    figure.main.scene().sigMouseMoved.emit(vb.mapViewToScene(QPointF(x, y)))
    figure._proxy.flush()
    qapp.processEvents()


def assert_card_fits(figure) -> None:
    """The readout card of *figure* holds every text it paints, from its fonts' advances, inside the plot area."""
    card = figure.card
    title, value_font, small = (QFontMetrics(font(role)) for role in ('label', 'small-number', 'small'))
    across, down = 2 * space(4), 2 * space(3)
    line = max(small.height(), value_font.height())
    assert card.width() >= across + title.horizontalAdvance(card.title)
    for _color, name, value, verdict, _quiet in card.rows:
        row = space(4) + small.horizontalAdvance(name) + value_font.horizontalAdvance(value)
        row += small.horizontalAdvance(verdict) + (3 if verdict else 2) * space(3)
        assert card.width() >= across + row, f'{name} {value} {verdict} does not fit'
    assert card.height() >= down + title.height() + len(card.rows) * line
    assert card.size() == card.sizeHint(), 'the card is the size its content asks for'
    vb = figure.main.getPlotItem().getViewBox()
    plot_area = figure.main.mapFromScene(vb.sceneBoundingRect()).boundingRect()
    assert plot_area.contains(card.geometry()), 'the card lies inside the plot area'


def test_the_card_fits_what_it_reads_after_a_pointer_move_and_keeps_its_size(qapp, session, demo):
    fit, profile = demo
    _show(session, fit, profile)
    qapp.processEvents()
    (figure,) = session._confidence.figures
    best = np.log10(fit.parameters['Ka_guest'].magnitude)

    move_pointer(qapp, figure, best + 0.3, 1.0)
    assert figure.hair.isVisible() and len(figure.card.rows) == len(figure.plot.curves)
    assert_card_fits(figure)
    size = figure.card.size()
    move_pointer(qapp, figure, best - 0.2, 1.0)
    move_pointer(qapp, figure, best + 0.3, 1.0)
    assert figure.card.size() == size, 'the same reading takes the same room'


def test_enlarge_gives_the_plots_the_canvas_and_gives_back_the_readings(session):
    _show(session, aware_result(shifts=_SHIFTS, diagnostics=_CONFLICT))
    view = session._confidence
    view.set_enlarged(True)
    assert view.header_host.isHidden() and view.callout_host.isHidden()

    view.set_enlarged(False)
    assert not view.header_host.isHidden() and not view.callout_host.isHidden()


def _two_ka_profiles() -> ProfileSet:
    def bump(key, centre, interval):
        grid = np.logspace(centre - 2, centre + 2, 81)
        r2 = 0.99 * np.exp(-((np.log10(grid) - centre) ** 2))
        return ProfileResult(key, grid, r2, 10**centre, 0.99, interval, 0.98, 12, 5, False)

    x, y = np.geomspace(1e5, 1e7, 16), np.geomspace(1e3, 1e5, 12)
    r2 = 1.0 - 0.01 * ((np.log10(x)[:, None] - 5.3) ** 2 + (np.log10(y)[None, :] - 3.5) ** 2)
    first, second = KaInterval(1.5e5, 2.6e5, False, False, 0.95, 16), KaInterval(1.1e3, 8.0e3, False, False, 0.95, 16)
    region = JointRegion(('Ka_HG', 'Ka_HG2'), x, y, r2, 0.99, 0.95, (2e5, 3e3), intervals={'Ka_HG': first})
    return ProfileSet({'Ka_HG': bump('Ka_HG', 5.3, first), 'Ka_HG2': bump('Ka_HG2', 3.5, second)}, region)


def test_two_binding_constants_stack_a_plot_each_with_the_joint_region_below(session):
    fit = _stepwise(KaInterval(1.1e3, 8.0e3, False, False, 0.95, 16))
    _show(session, fit, _two_ka_profiles())
    view = session._confidence

    assert [f.plot.name for f in view.figures] == ['Kₐ HG', 'Kₐ HG₂']
    assert view.region_figure is not None
    widgets = [view.plots_box.itemAt(i).widget() for i in range(view.plots_box.count())]
    assert widgets.index(view.region_figure) > max(widgets.index(f) for f in view.figures)
    assert view.header_box.count() == 2


def test_the_saved_figure_is_the_plot_light_on_white_in_a_dark_window(qapp, session, demo, tmp_path):
    from PyQt6.QtGui import QColor, QImage

    from gui.design.appearance import appearance
    from gui.design.tokens import Theme

    fit, profile = demo
    _show(session, fit, profile)
    appearance().set_mode('dark')
    try:
        path = tmp_path / 'confidence.png'
        session._confidence.export_image(str(path))
    finally:
        appearance().set_mode('light')
    image = QImage(str(path))
    light = Theme(dark=False)

    assert QColor(image.pixel(2, 2)).name() == '#ffffff'
    assert _pixels_near(image, light['text-secondary'], 8) > 400  # the curve, its strip bars, the axis text
    # The window's dark surface is nowhere: the figure is white save for its marks and text.
    assert _pixels_near(image, '#ffffff', 2) > 0.5 * image.width() * image.height()


def test_the_image_tool_and_the_batch_export_save_the_ka_confidence_figure(session, demo, monkeypatch, tmp_path):
    from PyQt6.QtWidgets import QFileDialog

    from gui.session import build_artefacts

    fit, profile = demo
    _show(session, fit, profile)
    saved = tmp_path / 'shown.png'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args, **kwargs: (str(saved), ''))
    # The demo fit is held as it is, not checked against the settings of this empty session.
    monkeypatch.setattr(session.model, 'check_results', lambda *args, **kwargs: None)
    (save,) = [b for b in session._confidence.canvas.findChildren(C.Button) if b.accessibleName().startswith('Save')]

    save.click()
    (artefact,) = [a for a in build_artefacts(session) if a.key == 'confidence_png']
    artefact.writer(tmp_path / 'batch.png')

    assert saved.stat().st_size > 0 and (tmp_path / 'batch.png').stat().st_size > 0
    assert artefact.available and artefact.suffix == '_confidence.png'


def test_an_imported_result_with_no_data_says_its_numbers_were_not_checked(session, monkeypatch):
    """Ka confidence states the readings of the fit Fit results shows, with the same caveat."""
    from gui import results as R

    monkeypatch.setattr(session.model, 'mismatch_note', lambda *args, **kwargs: None)
    session.model.show_imported([result()], 'stored.json')

    view = session._confidence
    assert session.model.measurement_set is None and not view.header_host.isHidden()
    assert ('Not checked', R.UNCHECKED_NOTE) in [(c.title, c.body) for c in view.callouts]
    assert [c.title for c in view.callouts] == [c.title for c in session._results.callouts]


def test_the_enlarged_plots_give_the_canvas_back_when_no_plot_is_left(session, demo):
    """Without a plot there is no enlarge tool to leave the enlarged state with: the readings and callouts return."""
    fit, profile = demo
    _show(session, fit, profile)
    view = session._confidence
    view.enlarge_tools[0].setChecked(True)
    assert view.header_host.isHidden()

    _show(session, fit, running=True)  # the fit runs again: its curves are computed anew

    assert not view.header_host.isHidden() and not view.callout_host.isHidden()
    assert [c.body for c in view.callouts][-1] == CF.PENDING

    _show(session, fit, profile)
    assert not view.header_host.isHidden() and not any(t.isChecked() for t in view.enlarge_tools)


def test_the_notes_of_a_fit_with_no_binding_constant_say_so_not_that_there_is_no_fit(session):
    from dataclasses import replace

    _show(session, replace(result(), assay_type='DYE_ALONE', intervals={}, parameters={}))

    view = session._confidence
    assert not view.no_fit.isHidden() and view.no_fit.text() == CF.NO_KA


def test_the_legend_has_an_accent_swatch_for_the_shaded_reported_interval(qapp, session, demo):
    """With every input exact the band behind the curve is the plot's only accent mark; the legend says what it is."""
    from PyQt6.QtGui import QColor

    fit, profile = demo
    _show(session, fit, profile)
    (legend,) = [w for w in session._confidence.plots_host.findChildren(C.LegendRow)]
    image = legend.grab().toImage()
    accent = QColor(session._confidence.t['accent'])

    def is_tint(x, y):
        c = QColor(image.pixel(x, y))
        # Accent laid thinly over the surface: the accent's hue, faintly saturated.
        return c.saturation() > 10 and abs(c.hue() - accent.hue()) < 20

    tinted = sum(is_tint(x, y) for x in range(image.width()) for y in range(image.height()))
    assert tinted > 20


def test_each_plot_header_sits_closer_to_its_own_plot_than_to_the_one_above(qapp, session):
    fit = _stepwise(KaInterval(1.1e3, 8.0e3, False, False, 0.95, 16))
    _show(session, fit, _two_ka_profiles())
    qapp.processEvents()
    view = session._confidence
    first, second = view.figures
    (_first_legend, second_legend) = view.plots_host.findChildren(C.LegendRow)

    def top(w):
        return w.mapTo(view.plots_host, w.rect().topLeft()).y()

    def bottom(w):
        return w.mapTo(view.plots_host, w.rect().bottomLeft()).y()

    above = top(second_legend) - bottom(first)
    below = top(second) - bottom(second_legend)
    assert below < above / 2


@pytest.mark.parametrize('hidden', [False, True], ids=['readings shown', 'results hidden by a note'])
def test_without_a_plot_the_readings_and_callouts_keep_their_own_height(qapp, session, monkeypatch, hidden):
    """The canvas's spare height goes below the last part shown, never into a callout or between the readings."""
    if not hidden:
        monkeypatch.setattr(session.model, 'mismatch_note', lambda *args, **kwargs: None)
    session.resize(1200, 1400)
    session.model.show_imported([result()], 'stored.json')
    qapp.processEvents()
    view = session._confidence

    assert not view.has_plot() and view.callouts and view.header_host.isHidden() == hidden
    for part in (view.header_host, view.callout_host, view.message):
        if not part.isHidden():
            assert part.height() <= part.sizeHint().height() + 1
    if not hidden:
        gap = view.callout_host.geometry().top() - view.header_host.geometry().bottom()
        assert gap < view.header_host.height()


def test_a_fit_with_no_profile_and_no_data_asks_for_the_data_before_the_fit(session, demo):
    fit, _profile = demo
    _show(session, fit)
    view = session._confidence
    assert session.model.measurement_set is None
    assert view.message.text() == CF.no_profile_sentence(has_data=False) and 'Load' in view.message.text()
    assert CF.no_profile_sentence(has_data=True).endswith('Run the fit again to draw them.')


def test_each_saved_plot_title_sits_closer_to_its_own_plot_than_to_the_one_above(qapp, session):
    from gui.design.components import PaintedText
    from gui.views.confidence import ProfileFigure

    fit = _stepwise(KaInterval(1.1e3, 8.0e3, False, False, 0.95, 16))
    _show(session, fit, _two_ka_profiles())
    figure = session._confidence.export_figure()
    try:
        first, second = figure.findChildren(ProfileFigure)
        title = next(w for w in figure.findChildren(PaintedText) if w.text == 'Kₐ HG₂')
        top = title.mapTo(figure, title.rect().topLeft()).y()
        bottom = title.mapTo(figure, title.rect().bottomLeft()).y()

        above = top - first.geometry().bottom()
        below = second.geometry().top() - bottom
        assert below < above
    finally:
        figure.close()
