"""Widget tests for Plot appearance (:mod:`gui.views.plot_appearance`) and the titration plot it styles.

The rules of the appearance are pinned by ``test_plot_appearance.py``; here what the
plot draws with them: the built-in look as DESIGN.md §7 states it, a choice in the form
redrawing the plots of every view at once, the saved figure in the light theme on white
with the chosen sizes, larger text kept whole, and the form's commands.
"""

from __future__ import annotations

import uuid

import numpy as np
import pyqtgraph as pg
import pytest

pytest.importorskip('PyQt6')

from PyQt6.QtCore import Qt  # noqa: E402

from core.assays.registry import AssayType  # noqa: E402
from gui.plot_appearance import BUILT_IN, CROSS_SCALE, PlotAppearance  # noqa: E402
from gui.session_model import Change  # noqa: E402
from tests.unit.gui.session_setup import state_binding  # noqa: E402
from tests.unit.gui.test_plot_appearance import CHANGED  # noqa: E402
from tests.unit.gui.test_results import fit_on, four_replicates  # noqa: E402


@pytest.fixture
def session(qapp):
    from PyQt6.QtCore import QCoreApplication, QSettings

    from gui.fitting_session import FittingSession

    QCoreApplication.setApplicationName(f'plot_appearance_view_{uuid.uuid4().hex[:8]}')
    QSettings().clear()
    made = FittingSession()
    yield made
    made.close()
    QSettings().clear()


def _fitted(session) -> None:
    """Four replicates, one switched off, and a fit of the others held as shown."""
    state_binding(session, assay_type=AssayType.GDA)
    session.model.load(four_replicates(), None)
    session.model.set_replicate('0', False)
    session.model._held_fit_results = [fit_on(session.model.measurement_set)]
    session.model.changed.emit(Change.RESULTS)


def _items(plot, kind):
    return [item for item in plot._items if isinstance(item, kind)]


def _marks(plot):
    """What *plot* draws with: (replicate dots, the ×, the means), the error bars' pen and the curve's pen."""
    scatters = _items(plot, pg.ScatterPlotItem)
    crosses = [s for s in scatters if s.opts['symbol'] == 'x']
    means = [s for s in scatters if s.opts['brush'].color() == plot.t.q('text-primary')]
    dots = [s for s in scatters if s not in crosses and s not in means]
    (bars,) = _items(plot, pg.ErrorBarItem)
    (curve,) = _items(plot, pg.PlotDataItem)
    return dots, crosses, means, bars.opts['pen'], curve.opts['pen']


def test_the_built_in_appearance_draws_the_titration_as_the_design_specifies(session):
    """DESIGN.md §7: replicate dots 6 px, each replicate in its own colour; × 7 px; 6-px means; 1-px error bars; 2-px accent curve."""
    from gui.design.plot_theme import REPLICATE_ALPHA, px

    _fitted(session)
    plot = session._results.plot
    t = plot.t
    dots, crosses, means, bar_pen, curve_pen = _marks(plot)

    assert {(d.opts['size'], d.opts['symbol']) for d in dots} == {(6, 'o')}
    assert [d.opts['brush'].color().name() for d in dots] == [t[f'replicate-{i}'].lower() for i in (2, 3, 4)]
    assert all(d.opts['brush'].color().alphaF() == pytest.approx(REPLICATE_ALPHA, abs=0.01) for d in dots)
    assert {c.opts['size'] for c in crosses} == {7}
    assert {m.opts['size'] for m in means} == {6}
    assert bar_pen.widthF() == px(1)
    assert curve_pen.widthF() == px(2) and curve_pen.color().name() == t['accent'].lower()


def test_a_choice_in_the_form_redraws_every_titration_plot_at_once(session, qapp):
    from PyQt6.QtTest import QTest

    from gui.design.plot_theme import px
    from gui.design.tokens import SIZE

    _fitted(session)
    view = session._appearance
    QTest.keyClick(view.choices['fit_width'], Qt.Key.Key_Right)  # Medium → Thick
    view.choices['replicate_colour'].chosen.emit(1)  # Grey
    QTest.keyClick(view.choices['replicate_shape'], Qt.Key.Key_Right)  # Circle → Square
    view.choices['fit_colour'].chosen.emit(1)  # Blue

    t = view.plot.t
    for plot in (view.plot, session._results.plot):
        dots, _crosses, _means, _bars, curve_pen = _marks(plot)
        assert curve_pen.widthF() == px(SIZE['stroke-thick'])
        assert curve_pen.color().name() == t['series-1'].lower()
        assert {d.opts['symbol'] for d in dots} == {'s'}
        assert {d.opts['brush'].color().name() for d in dots} == {t['replicate'].lower()}
    measured = [s for s in _items(session._measurements.plot, pg.ScatterPlotItem) if s.opts['symbol'] != 'x']
    assert {s.opts['symbol'] for s in measured} == {'s'}
    assert session.view_badge('Plot appearance') == 'Custom appearance'


def test_the_saved_figure_is_drawn_in_the_light_theme_on_white_with_the_chosen_sizes(session):
    from gui.design.appearance import appearance
    from gui.design.plot_theme import px
    from gui.design.tokens import LIGHT, SIZE, plot_font

    _fitted(session)
    session.model.set_plot_appearance(CHANGED)
    appearance().set_mode('dark')
    try:
        figure = session._results.plot.figure()
    finally:
        appearance().set_mode('light')
    try:
        dots, crosses, means, bar_pen, curve_pen = _marks(figure)
        assert not figure.t.dark
        assert figure.pw.backgroundBrush().color().name() == LIGHT['bg-surface'].lower()
        assert {(d.opts['size'], d.opts['symbol']) for d in dots} == {(SIZE['marker-large'], 't1')}
        assert {d.opts['brush'].color().name() for d in dots} == {LIGHT['replicate'].lower()}
        assert {m.opts['size'] for m in means} == {SIZE['marker-small']}
        # The × of the replicate switched off follows the replicate size, the error bars their width.
        assert [c.opts['size'] for c in crosses] == [pytest.approx(SIZE['marker-large'] * CROSS_SCALE)]
        assert bar_pen.widthF() == px(SIZE['stroke-medium'])
        assert curve_pen.color().name() == LIGHT['series-2'].lower()
        assert curve_pen.widthF() == px(SIZE['stroke-thick'])
        bottom = figure.pw.getPlotItem().getAxis('bottom')
        assert bottom.style['tickFont'].pixelSize() == plot_font(CHANGED.text_step, 'tick').pixelSize()
    finally:
        figure.close()


#: The axis text sizes Plot appearance offers, smallest first.
TEXT_STEPS = ('standard', 'large', 'larger')


def _axes(size: str):
    """The left and bottom axes of a titration plot of four replicates drawn with axis text *size*, and its plot."""
    from gui.views.titration import TitrationData, TitrationPlot

    ms = four_replicates()
    plot = TitrationPlot(plot_appearance=PlotAppearance(text_size=size))
    plot.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    plot.resize(900, 600)
    plot.show_data(
        TitrationData(ms.concentrations, ms.signals * 1e3, [True] * 4, 'Guest', replicate_ids=list(ms.replica_ids)),
        'µM',
    )
    return plot, plot.pw.getPlotItem().getAxis('left'), plot.pw.getPlotItem().getAxis('bottom')


def _title_font(axis):
    """The font *axis* draws its title in, as its label style states it."""
    from PyQt6.QtGui import QFont

    from gui.design.tokens import family

    f = QFont(family())
    f.setPixelSize(int(axis.labelStyle['font-size'].removesuffix('px')))
    f.setWeight(QFont.Weight(int(axis.labelStyle['font-weight'])))
    return f


def _drawn_text(size: str) -> dict[str, tuple[int, int]]:
    """The (px, weight) the plot draws its tick labels and axis titles in at axis text *size*."""
    plot, _left, bottom = _axes(size)
    try:
        tick = bottom.style['tickFont']
        title = (int(bottom.labelStyle['font-size'].removesuffix('px')), int(bottom.labelStyle['font-weight']))
        return {'tick': (tick.pixelSize(), int(tick.weight())), 'title': title}
    finally:
        plot.close()


@pytest.mark.parametrize('part', ['tick', 'title'])
def test_each_axis_text_size_is_one_even_step_up_at_one_weight(qapp, part):
    """Standard → Large → Larger reads as two equal steps: each a constant ratio up (within 5 %) and at
    least 2 px, and the weight never changes, so a step changes the size of the text and nothing else."""
    drawn = [_drawn_text(size)[part] for size in TEXT_STEPS]
    sizes = [px for px, _weight in drawn]
    ratios = [b / a for a, b in zip(sizes, sizes[1:], strict=False)]

    assert all(b - a >= 2 for a, b in zip(sizes, sizes[1:], strict=False)), sizes
    assert max(ratios) / min(ratios) <= 1.05, ratios
    assert len({weight for _px, weight in drawn}) == 1, drawn


def test_the_axes_grow_with_the_text_in_even_steps_and_keep_it_whole(qapp):
    """Each larger size widens and heightens the axes by about as much as the step before did, never by a
    jump, and leaves as much room for the axis title, under the x ticks and beside the widest y tick, as the
    standard size does."""
    from PyQt6.QtGui import QFontMetrics

    boxes, below, beside = [], {}, {}
    for size in TEXT_STEPS:
        plot, left, bottom = _axes(size)
        plot.show()
        qapp.processEvents()
        ticks = QFontMetrics(bottom.style['tickFont'])
        title = QFontMetrics(_title_font(bottom))
        boxes.append((left.width(), bottom.height()))
        below[size] = bottom.height() - ticks.height() - title.height()
        beside[size] = left.width() - ticks.horizontalAdvance('0000') - title.height()
        plot.close()

    for side in (0, 1):
        grows = [b[side] - a[side] for a, b in zip(boxes, boxes[1:], strict=False)]
        assert min(grows) > 0 and max(grows) <= 1.5 * min(grows), boxes
    assert all(below[size] >= below['standard'] > 0 for size in TEXT_STEPS)
    assert all(beside[size] >= beside['standard'] > 0 for size in TEXT_STEPS)


@pytest.mark.parametrize('size', TEXT_STEPS)
def test_the_x_axis_title_of_a_saved_figure_is_whole_at_every_size(qapp, tmp_path, size):
    """The figure ends under the x axis title, so its descenders (the µ and the brackets of ``(µM)``) must
    end inside the image: the bottom pixel row is blank."""
    from PyQt6.QtGui import QImage

    plot, _left, _bottom = _axes(size)
    try:
        plot.export_image(str(tmp_path / 'titration.png'), [])
    finally:
        plot.close()
    image = QImage(str(tmp_path / 'titration.png'))
    last = image.height() - 1

    assert all(image.pixelColor(x, last).lightness() > 240 for x in range(image.width()))


def test_the_head_of_a_saved_figure_reads_in_the_axis_text_size(qapp):
    """The caption and the fit's summary of a saved titration figure take the tick labels' size, and its title
    the axis titles', so the head reads at the size of the plot under it at every step."""
    from gui.design import components as C
    from gui.design.tokens import Theme, plot_font
    from gui.plotting.export import figure_head

    light = Theme(dark=False)
    for size in TEXT_STEPS:
        step = PlotAppearance(text_size=size).text_step
        legend = C.LegendRow(light, [], removable=False)
        head = figure_head(light, 'Titration', 'raw signal', legend, 900, ['Reported fit: Ka = 1.5 × 10⁸ M⁻¹'], step)
        title, caption = head.findChildren(C.PaintedText)
        (note,) = head.findChildren(C.PaintedNote)
        assert title.text_font.pixelSize() == plot_font(step, 'title').pixelSize()
        assert caption.text_font.pixelSize() == plot_font(step, 'tick').pixelSize()
        assert note.doc.defaultFont().pixelSize() == plot_font(step, 'tick').pixelSize()
        head.close()


def test_with_nothing_loaded_the_canvas_says_what_to_load(session):
    view = session._appearance

    assert not view.empty_state.isHidden() and view.empty_state.load.isVisibleTo(view.empty_state)
    assert view.plot.isHidden() and view.header.isHidden()
    assert session.plot_export_note('Plot appearance') is not None


def test_use_for_new_sessions_stores_this_appearance_and_reset_gives_back_the_built_in_one(session):
    from gui.fitting_session import FittingSession
    from gui.preferences import plot_appearance_default

    view = session._appearance
    assert not view.use_for_new.isEnabled() and not view.reset.isEnabled()  # built-in, and what new sessions get
    session.model.set_plot_appearance(CHANGED)
    assert view.use_for_new.isEnabled()

    view.use_for_new.click()
    new = FittingSession()
    try:
        assert plot_appearance_default() == CHANGED and new.model.plot_appearance == CHANGED
        assert not view.use_for_new.isEnabled()
    finally:
        new.close()

    view.reset.click()
    assert session.model.plot_appearance == BUILT_IN
    assert plot_appearance_default() == CHANGED  # the stored one is the Settings window's to reset


def test_every_titration_plot_follows_the_display_unit_and_saves_in_it(session):
    """A unit chosen in Measurements redraws the plot of every view, Plot appearance's and its figure included."""
    from gui.views.measurements import UNITS

    _fitted(session)
    session._measurements._set_display_unit(UNITS.index('nM'))

    plots = (session._measurements.plot, session._results.plot, session._appearance.plot)
    assert [plot.unit for plot in plots] == ['nM'] * 3
    for plot in plots:
        assert plot.pw.getPlotItem().getAxis('bottom').labelText.endswith('(nM)')
    figure = session._appearance.plot.figure()
    try:
        assert figure.unit == 'nM'
    finally:
        figure.close()


def test_a_new_text_size_restyles_the_axes_of_a_plot_already_on_screen(session):
    """Tick labels and axis titles take the new size at once, in every view, not only in a new figure."""
    from gui.design.tokens import plot_font

    _fitted(session)
    look = PlotAppearance(text_size='larger')
    session.model.set_plot_appearance(look)

    for plot in (session._measurements.plot, session._results.plot, session._appearance.plot):
        bottom = plot.pw.getPlotItem().getAxis('bottom')
        assert bottom.style['tickFont'].pixelSize() == plot_font(look.text_step, 'tick').pixelSize()
        assert bottom.labelStyle['font-size'] == f'{plot_font(look.text_step, "title").pixelSize()}px'


def _swatch(legend, item, columns=18) -> tuple[list, object]:
    """The colours *legend* paints for its one *item*, in the columns before its text, and the ground they are painted on."""
    from PyQt6.QtGui import QImage

    legend.set_items([item])
    image = QImage(legend.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    legend.render(image)
    ground = image.pixelColor(0, 0)
    pixels = [image.pixelColor(x, y) for x in range(columns) for y in range(image.height())]
    return [c for c in pixels if c != ground], ground


def _painted(legend, kind, columns=18) -> int:
    """How many pixels *legend* paints for its one mark of *kind*, in the columns before its text."""
    return len(_swatch(legend, (kind, 'x', 0) if kind == 'dots' else (kind, 'x'), columns)[0])


def test_the_legend_paints_the_mark_and_the_line_width_the_plot_draws(qapp):
    """A square covers more of its box than a circle and a triangle less; a thicker curve paints a wider line."""
    from gui.design import components as C
    from gui.design.appearance import theme

    legend = C.LegendRow(theme(), [])
    areas = {}
    for shape, symbol in (('square', 's'), ('circle', 'o'), ('triangle', 't1')):
        legend.set_marks(lambda _index, symbol=symbol: ('replicate', symbol), 2.0)
        areas[shape] = _painted(legend, 'dots')
    assert areas['square'] > areas['circle'] > areas['triangle'] > 0

    widths = []
    for width in (1.0, 3.0):
        legend.set_marks(lambda _index: ('replicate', 'o'), width)
        widths.append(_painted(legend, 'line'))
    assert widths[1] > widths[0] > 0


def test_the_view_s_legend_follows_its_plot(session):
    _fitted(session)
    session.model.set_plot_appearance(CHANGED)
    legend = session._results.legend
    look = CHANGED

    assert [legend.replicate_mark(i) for i in range(14)] == [look.replicate_mark(i) for i in range(14)]
    assert legend.line_width == look.fit_px


# ── Replicate identity ─────────────────────────────────────────────────────────────


def _colours(plot) -> dict[str, tuple[str, str]]:
    """Each replicate's colour in *plot* and how it is drawn (``dot`` or ``cross``), by replicate id."""
    drawn = {}
    for rid, item in plot.replicate_items.items():
        cross = item.opts['symbol'] == 'x'
        colour = (item.opts['pen'] if cross else item.opts['brush']).color()
        drawn[rid] = (colour.name(), 'cross' if cross else 'dot')
    return drawn


def test_each_replicate_is_drawn_in_its_palette_colour_in_every_view(session):
    """Replicate n of the data is ``replicate-n`` in Measurements, Fit results and Plot appearance alike;
    the one switched off keeps its colour, drawn as ×."""
    _fitted(session)
    t = session._results.plot.t
    expected = {
        '0': (t['replicate-1'].lower(), 'cross'),
        '1': (t['replicate-2'].lower(), 'dot'),
        '2': (t['replicate-3'].lower(), 'dot'),
        '3': (t['replicate-4'].lower(), 'dot'),
    }
    for plot in (session._results.plot, session._measurements.plot, session._appearance.plot):
        assert _colours(plot) == expected
    assert len({colour for colour, _ in expected.values()}) == 4


def test_switching_a_replicate_off_changes_no_other_replicate_s_colour(session):
    state_binding(session, assay_type=AssayType.GDA)
    session.model.load(four_replicates(), None)
    before = _colours(session._measurements.plot)

    session.model.set_replicate('1', False)
    after = _colours(session._measurements.plot)

    assert {rid: colour for rid, (colour, _) in after.items()} == {rid: colour for rid, (colour, _) in before.items()}
    assert after['1'][1] == 'cross' and {how for rid, (_, how) in after.items() if rid != '1'} == {'dot'}


def _many(n: int):
    from gui.views.titration import TitrationData

    x = np.linspace(1e-6, 1e-5, 5)
    return TitrationData(
        x, np.stack([x * (k + 1) for k in range(n)]), [True] * n, 'Guest', replicate_ids=[str(k) for k in range(n)]
    )


def test_twelve_replicates_take_twelve_colours_and_the_next_ones_the_next_shape(qapp):
    """Past the twelve colours, the colours repeat with the next mark, so every replicate stays one of its own."""
    from gui.design.tokens import Theme
    from gui.views.titration import TitrationPlot

    plot = TitrationPlot(Theme(dark=False))
    plot.show_data(_many(14), 'µM')
    marks = [(item.opts['brush'].color().name(), item.opts['symbol']) for item in plot.replicate_items.values()]

    assert len({colour for colour, _ in marks[:12]}) == 12
    assert {symbol for _, symbol in marks[:12]} == {'o'}
    assert marks[12:] == [(marks[0][0], 's'), (marks[1][0], 's')]
    assert len(set(marks)) == 14


def test_grey_draws_every_replicate_in_one_colour(qapp):
    from gui.design.tokens import Theme
    from gui.views.titration import TitrationPlot

    t = Theme(dark=True)
    plot = TitrationPlot(t, PlotAppearance(replicate_colour='grey'))
    plot.show_data(_many(14), 'µM')

    assert {(item.opts['brush'].color().name(), item.opts['symbol']) for item in plot.replicate_items.values()} == {
        (t['replicate'].lower(), 'o')
    }


def test_the_legend_marks_each_replicate_in_the_colour_its_points_are_drawn_in(qapp):
    """A replicate's entry, a point or the × of one not used, is painted in that replicate's colour."""
    from PyQt6.QtGui import QColor

    from gui.design import components as C
    from gui.design.plot_theme import REPLICATE_ALPHA
    from gui.design.tokens import Theme

    t = Theme(dark=False)
    legend = C.LegendRow(t, [])
    legend.set_marks(BUILT_IN.replicate_mark, 2.0)

    def far(c, d) -> int:
        return max(abs(c.red() - d.red()), abs(c.green() - d.green()), abs(c.blue() - d.blue()))

    def over(token, ground):
        c, a = t.q(token), REPLICATE_ALPHA
        return QColor(*(round(a * v + (1 - a) * g) for v, g in zip(c.getRgb()[:3], ground.getRgb()[:3], strict=True)))

    for kind, index in (('dots', 0), ('dots', 5), ('cross', 2)):
        painted, ground = _swatch(legend, (kind, 'A', index))
        core = max(painted, key=lambda c: far(c, ground))  # the pixel the mark covers most
        # Of the twelve replicate colours as the plot paints them on this ground, the core is the replicate's own.
        nearest = min(range(12), key=lambda n: far(core, over(f'replicate-{n + 1}', ground)))
        assert nearest == index, f'{kind} {index}'


def test_opening_plot_appearance_reads_what_another_session_stored(session):
    """Another session may store the appearance for new sessions; this one's button follows on opening."""
    from gui.fitting_session import FittingSession

    session.model.set_plot_appearance(CHANGED)
    assert session._appearance.use_for_new.isEnabled()
    other = FittingSession()
    try:
        other.model.set_plot_appearance(CHANGED)
        other._appearance.use_for_new.click()

        session.show_view('Plot appearance')
        view = session._appearance
        assert not view.use_for_new.isEnabled()
    finally:
        other.close()


def test_export_results_and_the_batch_json_record_the_session_s_appearance(session, monkeypatch, tmp_path):
    import json

    from gui.session import build_artefacts

    _fitted(session)
    session.model.set_plot_appearance(CHANGED)
    path = tmp_path / 'r.json'
    monkeypatch.setattr('gui.fitting_session.QFileDialog.getSaveFileName', lambda *args: (str(path), ''))
    # The synthetic fit is not re-checked against the settings; that check is tested on its own.
    monkeypatch.setattr(session, '_finish_edits', lambda: None)

    session.export_results()
    assert json.loads(path.read_text())['plot_appearance'] == CHANGED.to_dict()

    batch = tmp_path / 'batch.json'
    (artefact,) = [a for a in build_artefacts(session) if a.key == 'results_json']
    artefact.writer(batch)
    assert json.loads(batch.read_text())['plot_appearance'] == CHANGED.to_dict()


def _import(session, monkeypatch, path, shown):
    from types import SimpleNamespace

    monkeypatch.setattr('gui.fitting_session.QFileDialog.getOpenFileName', lambda *args: (str(path), ''))
    for kind in ('warning', 'information'):
        monkeypatch.setattr(f'gui.fitting_session.QMessageBox.{kind}', lambda *args: shown.append(args[1:]))
    # The re-scoring of a result is tested on its own; here every result is taken as it is.
    monkeypatch.setattr(
        session.model,
        'check_imported',
        lambda results, _name: SimpleNamespace(refusal=None, accepted=results, notice=None),
    )
    session.import_results()


def test_import_results_gives_the_session_the_appearance_the_file_records(session, monkeypatch, tmp_path):
    from gui.session import export_results

    _fitted(session)
    path = tmp_path / 'r.json'
    export_results(session.model.fit_results, path, CHANGED)
    shown = []

    _import(session, monkeypatch, path, shown)

    assert session.model.plot_appearance == CHANGED and shown == []
    assert session._appearance.plot.plot_appearance == CHANGED


def test_import_results_says_so_when_the_file_s_appearance_cannot_be_read(session, monkeypatch, tmp_path):
    import json

    from gui.session import export_results

    _fitted(session)
    path = tmp_path / 'unreadable.json'
    export_results(session.model.fit_results, path, CHANGED)
    record = json.loads(path.read_text())
    record['plot_appearance'] = {'replicate_size': 'huge'}
    path.write_text(json.dumps(record))
    shown = []

    _import(session, monkeypatch, path, shown)

    ((title, message),) = shown
    assert 'unreadable.json' in message and '“huge”' in message
    assert 'keeps this session’s own appearance' in message
    assert session.model.plot_appearance == BUILT_IN and session.model.held_fit_results  # the results still came in


def test_a_new_session_says_when_the_stored_appearance_cannot_be_read(qapp, monkeypatch):
    """No silent fallback: the New session command, from an unreadable stored appearance, warns."""
    import json

    from PyQt6.QtCore import QCoreApplication, QSettings

    from gui.main_window import FittingMainWindow
    from gui.preferences import PLOT_APPEARANCE_KEY

    QCoreApplication.setApplicationName(f'plot_appearance_window_{uuid.uuid4().hex[:8]}')
    QSettings().clear()
    shown = []
    monkeypatch.setattr('gui.main_window.QMessageBox.warning', lambda *args: shown.append(args[1:]))
    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    window = FittingMainWindow()
    try:
        assert shown == []
        QSettings().setValue(PLOT_APPEARANCE_KEY, json.dumps({'replicate_size': 'Small'}))
        # The New session command (menu, shortcut, switcher) passes QAction.triggered's checked flag.
        window._act_new.trigger()
        ((title, message),) = shown
        assert 'built-in' in message and 'Use for new sessions' in message
        # A duplicate takes the appearance of the session it copies, so it says nothing.
        window._duplicate_current()
        assert len(shown) == 1
    finally:
        window.close()
        QSettings().clear()
