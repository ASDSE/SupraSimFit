"""Widget tests for Fit results (:mod:`gui.views.fit_results`): what the view does with what :mod:`gui.results` says.

What the text and numbers say is pinned by ``test_results.py``; here only the view's own
work: the empty view, the callout's action, the link to the details, the side panel's
least width, the layout of Fit quality and Diagnostics, copyable results, the plot's ticks
and error bars and the exported image.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip('PyQt6')

from PyQt6.QtCore import Qt  # noqa: E402

from core.assays.registry import AssayType  # noqa: E402
from core.pipeline.diagnostics import Conflict, FitDiagnostics, InputShift, MisfitTest, Verdict  # noqa: E402
from gui.design import components as C  # noqa: E402
from gui.session_model import Change  # noqa: E402
from tests.unit.gui.session_setup import state_binding  # noqa: E402
from tests.unit.gui.test_results import aware_result, fit_on, four_replicates  # noqa: E402

_CONFLICT = FitDiagnostics(
    conditional_misfit=MisfitTest('lack_of_fit', 200.0, 1e-9, dof=(9, 72)),
    misfit=MisfitTest('lack_of_fit', 1.1, 0.4, dof=(9, 72)),
    conflict=Conflict(q=24.2, k=2, p_value=1e-5, weights=(0.3, 0.9)),
    verdict=Verdict.INPUTS_CONFLICT,
)

#: Shifts of every input of an IDA fit, the titrant's long name among them.
_SHIFTS = {
    'h0': InputShift('h0', -0.114, -3.8, False),
    '__titrant__': InputShift('__titrant__', 0.093, 3.1, False),
    'Ka_dye': InputShift('Ka_dye', 0.03, 0.3, False),
    'd0': InputShift('d0', 0.002, 0.1, False),
}


@pytest.fixture
def session(qapp):
    from gui.fitting_session import FittingSession

    made = FittingSession()
    yield made
    made.close()


def _show(session, fit) -> None:
    """Hold *fit* as the session's shown result, as a finished fit is held."""
    session.model._held_fit_results = [fit]
    session.model.changed.emit(Change.RESULTS)


def test_before_any_fit_the_view_says_what_to_do_with_the_platform_s_shortcut(session):
    from PyQt6.QtGui import QKeySequence

    view = session._results
    shortcut = QKeySequence('Ctrl+R').toString(QKeySequence.SequenceFormat.NativeText)

    assert not view.empty.isHidden() and f'Run fit ({shortcut})' in view.empty.text()
    assert view.headline.isHidden() and view.sections.isHidden()
    assert session.view_badge('Fit results') is None


def test_the_conflict_callout_reviews_the_inputs_in_ka_confidence(session):
    _show(session, aware_result(shifts=_SHIFTS, diagnostics=_CONFLICT))
    requested: list[str] = []
    session.view_requested.connect(requested.append)
    (callout,) = [c for c in session._results.callout_host.findChildren(C.Callout) if c.action is not None]

    callout.action.click()

    assert requested == ['Ka confidence']
    assert session.view_badge('Fit results') == 'Input-aware'  # an imported fit that records no replicates


def test_all_results_and_diagnostics_shows_the_side_panel_with_diagnostics_open(qapp, monkeypatch):
    from PyQt6.QtWidgets import QPushButton

    from gui.main_window import FittingMainWindow

    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    window = FittingMainWindow()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    window.show()
    window.show_view('Fit results')
    session = window.active_session()
    _show(session, aware_result(shifts=_SHIFTS, diagnostics=_CONFLICT))
    window._set_side_visible(False)
    view = session._results
    view.diagnostics_section.header.set_open(False)
    (link,) = [b for b in view.headline.findChildren(QPushButton) if b.text().startswith('All results and diagnostics')]

    link.click()
    qapp.processEvents()

    assert window._side_visible and session._views['Fit results'].side.isVisible()
    assert view.diagnostics_section.header._open
    window.close()


def _window(qapp, monkeypatch, fit):
    """A main window laid out off screen, showing *fit* in Fit results with Fit details open."""
    from gui.main_window import FittingMainWindow

    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    window = FittingMainWindow()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    window.show()
    window.show_view('Fit results')
    session = window.active_session()
    _show(session, fit)
    window._set_side_visible(True)
    for _ in range(6):
        qapp.processEvents()
    return window, session


def _two_ka_per_replica():
    """A 1:2 fit of four replicates, each fitted on its own: five columns in the Replicates table."""
    from dataclasses import replace

    from core.pipeline.varpro import KaInterval
    from core.units import Q_
    from tests.unit.gui.test_results import result

    signal = {'I0': 100.0, 'I_G': 5e4, 'I_H': 0.0, 'I_HG': 8e4, 'I_HG2': 2e4}
    base = result(
        parameters={
            'Ka_HG': Q_(1.24e6, '1/M'),
            'Ka_HG2': Q_(3.1e4, '1/M'),
            **{key: Q_(value, 'au' if key == 'I0' else 'au/M') for key, value in signal.items()},
        },
        assay_type='DBA_HG2',
        model_name='equilibrium_stepwise',
        fit_config={'per_replicate': True, 'level': 0.95},
        intervals={
            'Ka_HG': KaInterval(17541.0, 1.70e6, False, False, 0.95, 16),
            'Ka_HG2': KaInterval(1.0e4, 9.0e4, False, False, 0.95, 16),
        },
    )
    given = ['0', '1', '2', '3']
    fits = [
        replace(
            base,
            intervals=None,
            r_squared=0.9984 + 0.0003 * i,
            parameters={**base.parameters, 'Ka_HG': Q_(1.70e6 * (1 + i / 10), '1/M')},
            metadata={'replica_id': rid, 'active_replica_ids': [rid]},
        )
        for i, rid in enumerate(given)
    ]
    test = {'level': 0.01, 'p_values': {'0': 0.84, '1': 0.59, '2': 0.55, '3': 0.93}}
    return replace(
        base,
        replica_fits=fits,
        metadata={'active_replica_ids': given, 'replica_ids_fit': given, 'replicate_test': test},
    )


def _replicates_on_bound():
    """The 1:2 fit of four replicates whose own fits of each constant ran onto its search box, two of them."""
    from dataclasses import replace

    from core.units import Q_

    fit = _two_ka_per_replica()
    fits = list(fit.replica_fits)
    for i, key in ((0, 'Ka_HG'), (2, 'Ka_HG2')):
        fits[i] = replace(fits[i], parameters={**fits[i].parameters, key: Q_(1e-8, '1/M')})
    return replace(fit, replica_fits=fits)


def _on_bound(open_high: bool = False):
    """A host-to-dye fit whose Ka_dye ran onto the low end of its box, the data closing it above unless *open_high*."""
    from core.pipeline.varpro import KaInterval
    from core.units import Q_
    from tests.unit.gui.test_results import result

    return result(
        assay_type='DBA_HtoD',
        parameters={
            'Ka_dye': Q_(1e-8, '1/M'),
            'I0': Q_(100.0, 'au'),
            'I_dye_free': Q_(5e4, 'au/M'),
            'I_dye_bound': Q_(2.37e19, 'au/M'),
        },
        intervals={'Ka_dye': KaInterval(1e-8, 1e12 if open_high else 2413.6, True, open_high, 0.95, 16)},
    )


def _spread_per_replica():
    """The 1:2 fit of four replicates whose own fits of each constant lie more than three decades apart, with a
    replicate the test rejects: the widest Replicates table, every number written with its own power of ten."""
    from dataclasses import replace

    from core.units import Q_

    fit = _two_ka_per_replica()
    fits = [
        replace(
            rf, parameters={**rf.parameters, 'Ka_HG': Q_(2.0e3 * 10.0**i, '1/M'), 'Ka_HG2': Q_(3.0e2 * 10.0**i, '1/M')}
        )
        for i, rf in enumerate(fit.replica_fits)
    ]
    test = {'level': 0.01, 'p_values': {'0': 0.84, '1': 0.0004, '2': 0.55, '3': 0.93}}
    return replace(
        fit, replica_fits=fits, metadata={**fit.metadata, 'replicate_test': test}, degenerate_keys=('I0', 'I_HG')
    )


def _shared_source(name: str):
    """An IDA fit whose one error source is shared by [Host]₀ and [Dye]₀ and named *name*, as the user typed it."""
    from core.pipeline.inputs import ErrorModel, SharedSource, shared_key

    key = shared_key(name)
    fit = aware_result(shifts={key: InputShift(key, -0.041, -1.02, False)}, uncertainty={})
    fit.fit_config.update(ErrorModel(shared=(SharedSource(name, 4.0, ('h0', 'd0')),)).to_dict())
    return fit


_SIDE_PANEL_FITS = {
    'long-names': lambda: aware_result(shifts=_SHIFTS, diagnostics=_CONFLICT),
    'shared-source-one-word': lambda: _shared_source('HostAndDyeStockFromOneBalance2026'),
    'shared-source-underscores': lambda: _shared_source('Stock_HD_batch12'),
    'two-ka-per-replicate': _two_ka_per_replica,
    'spread-per-replicate': _spread_per_replica,
    'estimate-on-bound': _on_bound,
    'replicates-on-bound': _replicates_on_bound,
}


@pytest.mark.parametrize('fit', list(_SIDE_PANEL_FITS))
def test_fit_details_fit_the_side_panel_at_its_least_width_beside_the_scroll_bar(qapp, monkeypatch, fit):
    """The panel never scrolls sideways: wider than its viewport, a column would be cut and a p of 0.84 read 0.8."""
    from gui.design.tokens import SIZE

    window, session = _window(qapp, monkeypatch, _SIDE_PANEL_FITS[fit]())
    side = session._views['Fit results'].side
    scroll = side.scroll
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)  # the panel as tall content leaves it
    side.setFixedWidth(SIZE['inspector-min'])
    for _ in range(6):
        qapp.processEvents()

    assert scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert scroll.verticalScrollBar().isVisible()
    assert scroll.widget().minimumSizeHint().width() <= scroll.viewport().width()
    # A wrapped label's least width does not grow with its longest word, so read each text at the width it has.
    for label in _shown_text(scroll.widget()):
        assert _laid_out_width(label) <= label.contentsRect().width() + 1, label.text()
    window.close()


def _shown_text(root):
    """Every visible, non-empty label under *root*."""
    from PyQt6.QtWidgets import QLabel

    return [label for label in root.findChildren(QLabel) if label.isVisible() and label.text()]


def _laid_out_width(label) -> float:
    """The width *label*'s text takes at its own width, breaking lines only between words, as a label does."""
    from PyQt6.QtGui import QTextDocument, QTextOption

    doc = QTextDocument()
    doc.setDocumentMargin(0)
    doc.setDefaultFont(label.font())
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WordWrap if label.wordWrap() else QTextOption.WrapMode.NoWrap)
    doc.setDefaultTextOption(option)
    rich = label.textFormat() == Qt.TextFormat.RichText or (
        label.textFormat() == Qt.TextFormat.AutoText and Qt.mightBeRichText(label.text())
    )
    doc.setHtml(label.text()) if rich else doc.setPlainText(label.text())
    doc.setTextWidth(label.contentsRect().width())
    return doc.idealWidth()


def test_a_shared_source_named_in_one_long_word_is_shown_whole(qapp, monkeypatch):
    """The name is what the user typed; cut at the bar's column it could not be read anywhere."""
    from gui.design.tokens import SIZE

    name = 'Hoststocksolutionbatch20261113'
    window, session = _window(qapp, monkeypatch, _shared_source(name))
    side = session._views['Fit results'].side
    side.setFixedWidth(SIZE['inspector-min'])
    for _ in range(6):
        qapp.processEvents()
    view = session._results
    (label,) = [w for w in _shown_text(view.shifts_section) if name[:8] in w.text().replace('\u200b', '')]

    assert label.text().replace('\u200b', '') == f'{name} (shared by [Host]₀, [Dye]₀)'
    assert label.accessibleName() == f'{name} (shared by [Host]₀, [Dye]₀)'
    assert _laid_out_width(label) <= label.contentsRect().width() + 1
    assert label.heightForWidth(label.width()) <= label.height()
    window.close()


def test_a_long_name_breaks_only_between_the_characters_a_reader_sees(qapp):
    """A letter and its accent, or the parts of one emoji, are one character on screen: split, the accent is drawn
    apart from its letter. A name pasted from a macOS file name holds its accents as separate code points."""
    import unicodedata

    name = unicodedata.normalize('NFD', 'Lösungsmittelcharge2026') + '\U0001f469\u200d\U0001f52c' + 'Stock'
    label = C.BreakingLabel(name)
    label.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    label.resize(label.fontMetrics().horizontalAdvance('Lösung'), 400)
    label.show()
    qapp.processEvents()
    breaks = label.text()

    assert breaks.count('\u200b') > 1  # the name is wider than the label, so it breaks
    assert breaks.replace('\u200b', '') == name
    for i, char in enumerate(breaks):
        if char == '\u200b':
            after = breaks[i + 1]
            before = breaks[i - 1]
            assert not unicodedata.combining(after), f'accent split from its letter at {i}'
            assert '\u200d' not in (before, after), f'emoji split at {i}'
    assert label.accessibleName() == name
    label.close()


def test_every_cell_of_the_replicates_table_shows_its_value(qapp, monkeypatch):
    """A cell is rich text: a p below the floor written '< 0.001' unescaped is read as a tag and shows nothing,
    which hides the replicate the shared-Kₐ test rejects most strongly."""
    from PyQt6.QtGui import QTextDocument

    window, session = _window(qapp, monkeypatch, _spread_per_replica())  # p-values 0.84, 0.0004, 0.55, 0.93
    table = session._results.replicates_table

    def shown(row, col):
        doc = QTextDocument()
        doc.setHtml(table.cell(row, col).text())
        return ' '.join(doc.toPlainText().split())

    columns = len(table.texts()[0])
    assert [shown(row, columns - 1) for row in range(4)] == ['0.84', '< 0.001', '0.55', '0.93']
    assert all(shown(row, col).strip() for row in range(4) for col in range(columns))
    window.close()


def test_what_the_view_says_on_hover_is_attached_to_what_it_explains(session):
    """The interval's notes, what Split means, each replicate's R² and reason, a starred coefficient's meaning."""
    from dataclasses import replace

    from PyQt6.QtWidgets import QLabel

    from core.pipeline.varpro import KaInterval
    from gui import results as R
    from tests.unit.gui.test_results import result

    unsolvable = KaInterval(1e5, 1e12, False, True, 0.95, 16, unsolvable_high=True, split=True)
    _show(session, result(intervals={'Ka_guest': unsolvable}, degenerate_keys=('I_dye_bound',)))
    view = session._results
    (interval,) = [w for w in view.headline.findChildren(QLabel) if w.text().endswith(R.NO_UPPER)]
    (chart,) = view.headline.findChildren(C.IntervalChart)

    assert 'more measurements cannot close it' in interval.toolTip()
    assert chart.toolTip() == R.SPLIT_FOOTNOTE
    starred = [i for i, row in enumerate(view.parameters.texts()) if row[0].endswith('*')]
    assert starred and all(view.parameters.cell(i, 0).toolTip().startswith('The data fix only') for i in starred)

    fit = _spread_per_replica()
    excluded = {**fit.metadata, 'replica_ids_fit': ['0', '2', '3'], 'replica_failures': {'1': 'Its points scatter.'}}
    _show(session, replace(fit, metadata=excluded))
    table = view.replicates_table
    assert table.cell(0, 0).toolTip() == 'R² of its own fit 0.9984.'
    assert all(table.cell(1, c).toolTip().startswith('Its points scatter.') for c in range(len(table.texts()[1])))


def test_an_estimate_on_its_search_bound_keeps_its_number_beside_its_unit(qapp, monkeypatch):
    """The words go on a line of their own; the number stays on one line with its unit next to it."""
    from PyQt6.QtWidgets import QLabel

    window, session = _window(qapp, monkeypatch, _on_bound())
    view = session._results
    labels = view.headline.findChildren(QLabel)
    (words,) = [label for label in labels if label.text() == 'Not limited below']
    (value,) = [label for label in labels if label.text().startswith('2.41')]
    (unit,) = [label for label in labels if label.text() == 'M⁻¹']

    assert words.isVisible() and words.geometry().bottom() <= value.geometry().top()
    assert value.height() < 2 * value.fontMetrics().lineSpacing()  # one line
    assert 0 <= unit.geometry().left() - value.geometry().right() <= 12
    # Every unit in Parameters reads as one token, on one line, and whole.
    for row in range(len(view.parameters.texts())):
        cell = view.parameters.cell(row, 2)
        lines = cell.heightForWidth(cell.width()) if cell.wordWrap() else cell.sizeHint().height()
        assert lines < 2 * cell.fontMetrics().lineSpacing(), cell.text()
        assert cell.width() >= cell.sizeHint().width(), cell.text()
    window.close()


def test_an_estimate_the_data_limit_on_neither_side_shows_no_unit_without_a_number(qapp, monkeypatch):
    """'Not limited by the data' is the whole headline; a unit standing alone would belong to no number."""
    from PyQt6.QtWidgets import QLabel

    window, session = _window(qapp, monkeypatch, _on_bound(open_high=True))
    shown = [label for label in session._results.headline.findChildren(QLabel) if label.isVisible()]

    assert any(label.text() == 'Not limited by the data' for label in shown)
    assert not any(label.text() == 'M⁻¹' for label in shown)
    window.close()


def test_the_results_can_be_copied(session):
    from PyQt6.QtWidgets import QLabel

    _show(session, aware_result(shifts=_SHIFTS, diagnostics=_CONFLICT))
    view = session._results
    values = [label for label in view.headline.findChildren(QLabel) if label.text().startswith('1.30')]
    values += [view.r2, view.rmse, view.parameters.cell(0, 1)]

    assert len(values) == 4
    assert all(label.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse for label in values)


def _pixels_near(image, colour, tolerance: int = 24) -> int:
    """How many pixels of *image* lie within *tolerance* of *colour* in every channel."""
    from PyQt6.QtGui import QColor, QImage

    rgb = image.convertToFormat(QImage.Format.Format_RGB32)
    bits = rgb.constBits()
    bits.setsize(rgb.sizeInBytes())
    pixels = np.frombuffer(bits, np.uint8).reshape(rgb.height(), rgb.bytesPerLine() // 4, 4)[:, : rgb.width(), :3]
    target = QColor(colour)
    bgr = np.array([target.blue(), target.green(), target.red()], dtype=int)
    return int(np.sum(np.all(np.abs(pixels.astype(int) - bgr) <= tolerance, axis=-1)))


def _over_white(colour: str, alpha: float) -> str:
    from PyQt6.QtGui import QColor

    c = QColor(colour)
    blend = [round(alpha * v + (1 - alpha) * 255) for v in (c.red(), c.green(), c.blue())]
    return QColor(*blend).name()


def test_the_saved_titration_is_the_plot_drawn_light_on_white_in_a_dark_window(qapp, session, tmp_path):
    """The saved figure's plot — replicates and the fitted curve — is drawn in the light theme, on white."""
    from PyQt6.QtGui import QColor, QImage

    from gui.design.appearance import appearance
    from gui.design.plot_theme import REPLICATE_ALPHA
    from gui.design.tokens import Theme
    from gui.views.titration import EXPORT_SIZE

    def plot_of(path) -> QImage:
        """The plot of a saved figure, under its head: the figure's last rows, at twice the plot's size."""
        image = QImage(str(path))
        height = 2 * EXPORT_SIZE[1]
        return image.copy(0, image.height() - height, image.width(), height)

    ms = four_replicates()
    state_binding(session, assay_type=AssayType.GDA)
    session.model.load(ms, None)
    _show(session, fit_on(ms))
    appearance().set_mode('dark')
    try:
        path = tmp_path / 'fit.png'
        session._results.export_image(str(path))
    finally:
        appearance().set_mode('light')
    image = plot_of(path)
    light = Theme(dark=False)
    replicates = [_over_white(light[f'replicate-{n}'], REPLICATE_ALPHA) for n in (1, 2, 3, 4)]
    # The same figure without the replicates' own points, and without the mean ± SD: what each adds is its own.
    view = session._results
    counts = {}
    for name, display in (('without replicates', 1), ('without mean', 2)):
        session.model.set_replicate_display(display)
        other = tmp_path / f'{display}.png'
        view.export_image(str(other))
        counts[name] = plot_of(other)
    session.model.set_replicate_display(0)

    assert QColor(image.pixel(2, 2)).name() == '#ffffff'
    assert _pixels_near(image, light['accent']) > 40  # the fitted curve
    # Each replicate's dots, at its own colour's blend over white (a tight tolerance leaves out antialiased text).
    for replicate in replicates:
        assert _pixels_near(image, replicate, 3) > 4 * _pixels_near(counts['without replicates'], replicate, 3)
    # The mean ± SD, the only marks drawn in the text colour inside the plot.
    assert _pixels_near(image, light['text-primary'], 12) > 30 + 4 * _pixels_near(
        counts['without mean'], light['text-primary'], 12
    )


def test_the_saved_figure_states_each_fit_s_numbers_and_the_moved_inputs(session, tmp_path):
    """The headline is not in a saved image, so the image says the interval and where the curve is drawn."""
    ms = four_replicates()
    state_binding(session, assay_type=AssayType.GDA)
    session.model.load(ms, None)
    _show(session, fit_on(ms, input_shifts={'h0': InputShift('h0', -0.04, -1.3, False)}))
    path = tmp_path / 'fit.svg'
    session._results.export_image(str(path))
    svg = path.read_text(encoding='utf-8')

    assert 'Kₐ guest' in svg and '95' in svg and 'interval' in svg and 'R² 0.9980' in svg
    assert 'curve drawn at the fitted input shifts' in svg


def test_the_image_tool_of_the_titration_saves_the_plot(session, monkeypatch):
    """The button beside the plot asks where to save it, as Export ▸ Plot image… does."""
    from PyQt6.QtWidgets import QFileDialog

    assert not session._results.save_plot.isEnabled()  # an empty plot is not offered for saving
    assert not session._results.display_tool.isEnabled()
    asked: list[str] = []
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args, **kwargs: (asked.append(args[1]), ('', ''))[1])
    session.model.load(four_replicates(), None)

    session._results.save_plot.click()
    session._measurements.save_plot.click()

    assert asked == ['Save Plot', 'Save Plot']


def test_the_interval_chart_is_named_by_the_glossary_and_its_legend_dots_are_the_plot_s_own(session):
    """A screen reader hears 'Kₐ guest', not a parameter key; the legend draws replicates as the plot does."""
    from gui.design.appearance import appearance

    ms = four_replicates()
    state_binding(session, assay_type=AssayType.GDA)
    session.model.load(ms, None)
    _show(session, fit_on(ms))
    view = session._results
    (chart,) = view.headline.findChildren(C.IntervalChart)

    assert chart.accessibleName() == 'Interval chart of Kₐ guest'
    before = appearance().mode
    try:
        for mode in ('dark', 'light'):
            appearance().set_mode(mode)
            (dots, *_) = view.plot._items
            assert view.legend.dots_alpha() == pytest.approx(dots.opts['brush'].color().alphaF(), abs=0.01)
    finally:
        appearance().set_mode(before)


def test_a_hidden_fit_draws_the_data_without_its_curve(session):
    ms = four_replicates()
    state_binding(session, assay_type=AssayType.GDA)
    session.model.load(ms, None)
    fit = fit_on(ms)
    fit.metadata['data_fingerprint'] = 'other data'
    session.model._held_fit_results = [fit]
    session.model.check_results()
    view = session._results

    assert view.plot.data.curves == [] and view.plot.data.active == [True] * 4
    assert [c.title for c in view.callouts] == ['Results hidden']
    assert np.asarray(view.plot.data.signals).shape == (4, 8)


def test_the_batch_export_writes_the_titration_of_fit_results(session, tmp_path):
    """Export several… writes the plot Fit results shows, as PNG and SVG."""
    from PyQt6.QtGui import QImage

    from gui.session import build_artefacts, export_batch

    ms = four_replicates()
    state_binding(session, assay_type=AssayType.GDA)
    session.model.load(ms, None)
    arts = [a for a in build_artefacts(session) if a.key in ('fit_png', 'fit_svg')]

    outcomes = export_batch(arts, tmp_path, 'run')

    assert [error for _label, _path, error in outcomes] == [None, None]
    assert not QImage(str(tmp_path / 'run_fit.png')).isNull()
    assert (tmp_path / 'run_fit.svg').read_text(encoding='utf-8').lstrip().startswith('<?xml')


def _shown_fits(n: int):
    """*n* fits of a 1:2 model with moved inputs, as an imported file holding several shows them."""
    from dataclasses import replace

    from core.units import Q_

    base = replace(
        _two_ka_per_replica(), replica_fits=None, input_shifts={k: _SHIFTS[k] for k in ('h0', '__titrant__')}
    )
    return [
        replace(
            base, parameters={**base.parameters, 'Ka_HG': Q_(1.24e6 * (1 + i / 3), '1/M')}, r_squared=0.99 - i / 100
        )
        for i in range(n)
    ]


def test_a_saved_figure_keeps_its_width_whatever_its_summary_says(session, tmp_path):
    """Every fit's numbers are said in full, wrapped to the figure, so a long summary does not widen the image."""
    import re

    from PyQt6.QtGui import QImage

    from gui.views.titration import EXPORT_SIZE

    session.model._held_fit_results = _shown_fits(2)
    session.model.changed.emit(Change.RESULTS)
    view = session._results
    png, svg = tmp_path / 'fit.png', tmp_path / 'fit.svg'
    view.export_image(str(png))
    view.export_image(str(svg))
    image, text = QImage(str(png)), svg.read_text(encoding='utf-8')

    assert image.width() == 2 * EXPORT_SIZE[0]  # the PNG at twice the figure's width
    assert float(re.search(r'<svg[^>]*\swidth="([\d.]+)"', text).group(1)) == EXPORT_SIZE[0]
    summary = view.titration.summary
    assert summary[0].startswith('Reported fit: ') and summary[-1].startswith('Other fit 1 (dashed): ')
    words = ' '.join(summary).split()
    assert all(word in text for word in words if word.isalpha())


@pytest.mark.parametrize('n', [2, 3])
def test_the_titration_header_keeps_its_room_with_several_fits_shown(qapp, monkeypatch, n):
    """The legend grows with the fits shown; the header line gives way rather than pushing Fit details aside."""
    from dataclasses import replace

    from gui.design.tokens import SIZE

    window, session = _window(qapp, monkeypatch, aware_result())
    ms = four_replicates()
    state_binding(session, assay_type=AssayType.GDA)
    session.model.load(ms, None)
    session.model.set_replicate('0', False)  # one replicate switched off, one left out: the longest legend
    fit = fit_on(session.model.measurement_set, left_out=('1',), input_shifts={'h0': _SHIFTS['h0']})
    session.model._held_fit_results = [replace(fit, r_squared=0.99 - i / 100) for i in range(n)]
    session.model.changed.emit(Change.RESULTS)
    for _ in range(6):
        qapp.processEvents()
    view = session._results
    side = session._views['Fit results'].side
    description, legend = view.description, view.legend

    assert side.width() >= SIZE['inspector']
    assert not side.scroll.horizontalScrollBar().isVisible()
    assert description.geometry().right() < legend.geometry().left()
    assert view.canvas.width() >= view.canvas.minimumSizeHint().width()
    window.close()


def test_no_tick_label_of_the_empty_titration_is_cut_at_an_edge(qapp, monkeypatch):
    """The empty plot runs 0 to 1 on both axes, with ticks on its edges; each label is centred there and stays in view."""
    from PyQt6.QtGui import QImage, QPainter

    from gui.main_window import FittingMainWindow

    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    window = FittingMainWindow()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    window.show()
    window.show_view('Fit results')
    for _ in range(6):
        qapp.processEvents()
    session = window.active_session()
    for view, plot in (('Measurements', session._measurements.plot), ('Fit results', session._results.plot)):
        window.show_view(view)
        for _ in range(6):
            qapp.processEvents()
        drawn = {}
        for side in ('left', 'bottom'):
            axis = plot.pw.getPlotItem().getAxis(side)
            image = QImage(10, 10, QImage.Format.Format_ARGB32)
            painter = QPainter(image)
            try:
                _axis, _ticks, texts = axis.generateDrawSpecs(painter)
            finally:
                painter.end()
            drawn[side] = {text: axis.mapRectToScene(rect) for rect, _flags, text in texts}
        scene = plot.pw.sceneRect()

        for side, labels in drawn.items():
            assert {0.0, 1.0} <= {float(text) for text in labels}, (view, side, list(labels))
            assert all(scene.contains(rect) for rect in labels.values()), (view, side, labels)
    window.close()


def test_the_mean_sd_caps_take_the_same_share_of_the_x_axis_whatever_unit_it_reads_in(session):
    """A cap of fixed data width would vanish at nM and swamp the plot at M; its share of the span stays put."""
    import pyqtgraph as pg

    ms = four_replicates()
    state_binding(session, assay_type=AssayType.GDA)
    session.model.load(ms, None)
    plot = session._results.plot
    shares = []
    for unit in ('µM', 'nM'):
        plot.show_data(plot.data, unit)
        (bars,) = [item for item in plot._items if isinstance(item, pg.ErrorBarItem)]
        x = np.asarray(bars.opts['x'])
        shares.append(bars.opts['beam'] / (x.max() - x.min()))

    assert shares[0] > 0
    assert shares[0] == pytest.approx(shares[1])


def test_diagnostics_lists_the_tests_alone_each_with_its_full_sentence_on_hover(session):
    """The reference shows mark, finding and p-value; the statistic and the shifts are a hover away, naming no cause."""
    from PyQt6.QtWidgets import QLabel

    _show(session, aware_result(shifts=_SHIFTS, diagnostics=_CONFLICT))
    view = session._results
    rows = [view.test_box.itemAt(i).widget() for i in range(view.test_box.count())]

    assert [[label.text() for label in row.findChildren(QLabel)] for row in rows] == [
        ['Curve fits with inputs moved', 'p = 0.4'],
        ['Misfit at inputs as entered', 'p < 0.001'],
        ['Inputs conflict', 'p < 0.001'],
    ]
    assert 'F(9, 72) = 1.1' in rows[0].toolTip() and 'F(9, 72) = 200' in rows[1].toolTip()
    assert 'q = 24.2' in rows[2].toolTip() and rows[2].toolTip().endswith('not which input is wrong.')


def test_fit_quality_is_a_two_by_two_grid_with_noise_beside_the_replicates_used(qapp, monkeypatch):
    from core.pipeline.noise import NoiseBasis, NoiseLaw

    law = NoiseLaw(NoiseBasis.REPLICATES, share=0.4, floor=80.0, proportional=0.006, reference=1e5, n_replicates=7)
    window, session = _window(qapp, monkeypatch, aware_result(noise=law))
    view = session._results

    assert view.noise.text() == '0.6 % + 80 a.u.' and view.noise_note.text() == 'from replicate scatter'
    assert view.noise_stat.toolTip().startswith('About 0.6 % of the signal plus 80 a.u.')
    origin = view.used.mapTo(view.side, view.used.rect().topLeft())
    beside = view.noise.mapTo(view.side, view.noise.rect().topLeft())
    rmse = view.rmse.mapTo(view.side, view.rmse.rect().topLeft())
    assert beside.y() == origin.y() and beside.x() == rmse.x() > origin.x()
    window.close()


def test_the_single_replicate_line_of_two_binding_constants_takes_at_most_two_lines(qapp, monkeypatch):
    """One line of figures under the headline; why the replicates disagree is said on hover."""
    window, session = _window(qapp, monkeypatch, _spread_per_replica())
    line = session._results.replicate_line

    assert line.isVisible()
    assert line.height() < 3 * line.fontMetrics().lineSpacing()
    assert 'can fall outside it' in line.toolTip()
    window.close()
