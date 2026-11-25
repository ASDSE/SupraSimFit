"""Binding model on screen: the form draws the model's binding model, and its controls reach it.

The rules of stating a binding model are tested on the form itself (``test_binding.py``);
these pin what only the view can get wrong — the rows it lays out for the model chosen,
the order the keyboard takes, the column the stock shares with the conditions, each
control reaching the form and the form drawn back on it, each row's problem under it,
and the dye-alone command.
"""

from __future__ import annotations

import pytest

pytest.importorskip('PyQt6')

from PyQt6.QtCore import Qt  # noqa: E402

from core.assays.registry import AssayType  # noqa: E402
from tests.unit.gui.session_setup import state_binding, state_dilution  # noqa: E402


@pytest.fixture
def session(qapp):
    from gui.fitting_session import FittingSession

    session = FittingSession()
    session.resize(1100, 1400)
    session.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    session.show_view('Binding model')
    session.show()
    qapp.processEvents()
    yield session
    session.model.shutdown()
    session.close()


def _tab_order(start, wanted: list) -> list:
    """The widgets of *wanted* in the order Tab reaches them from *start*."""
    reached, widget = [], start
    for _ in range(10_000):
        widget = widget.nextInFocusChain()
        if widget is start:
            break
        if widget in wanted:
            reached.append(widget)
    return reached


def test_the_rows_follow_the_model_chosen(qapp, session):
    view = session._binding
    state_binding(session, assay_type=AssayType.DBA_HtoD)
    qapp.processEvents()
    assert list(view._conditions) == ['fixed_conc']
    assert list(view._bounds) == ['Ka_dye', 'I0', 'I_dye_free', 'I_dye_bound']
    assert view.assay.options == [
        'Host → dye (1:1)',
        'Dye → host (1:1)',
        'Host–guest 1:2 (HG₂)',
        'Host–guest 2:1 (H₂G)',
    ]
    assert view.stock_section.isVisibleTo(view.canvas) and not view._contains

    state_binding(session, assay_type=AssayType.DYE_ALONE)
    qapp.processEvents()
    assert view._conditions == {} and view.no_conditions.isVisibleTo(view.canvas)
    assert not view.stock_section.isVisibleTo(view.canvas)
    assert not view.dye_alone.isVisibleTo(view.canvas), 'a calibration bounds no parameter of a calibration'
    # Sentence case, and the model named as its badge names it.
    assert view.category.options == ['Competitive displacement', 'Direct binding', 'Calibration']
    assert view.no_conditions.text() == 'Dye alone needs no conditions besides the data.'
    assert view.replicates_note.text() == 'Dye alone is fitted from the average of the replicates switched on.'


def test_choosing_a_model_in_its_menu_reaches_the_session(qapp, session):
    view = session._binding
    view.category.chosen.emit(1)  # Direct binding
    view.assay.chosen.emit(2)  # its third model

    assert session.model.settings.assay_type is AssayType.DBA_HG2
    assert session.view_badge('Binding model') == 'HG₂ · 2 binding constants'


def test_tab_runs_from_the_model_through_the_conditions_and_the_stock_to_the_bounds(qapp, session):
    """Keyboard entry follows the form, not the order the rows were built in, after the model changes too."""
    state_binding(session, assay_type=AssayType.IDA)
    state_binding(session, assay_type=AssayType.GDA)
    state_dilution(session, 1e-3)
    qapp.processEvents()
    view = session._binding

    expected = [view.category, view.assay]
    for row in view._conditions.values():
        expected += row.focus_chain()
    expected += [view.dilution, view.stock.editor, view.stock_unit, *view._contains.values()]
    for row in view._bounds.values():
        expected += [field.editor for field in row.fields]
    expected += [view.reset, view.dye_alone, view.replicates]

    assert _tab_order(view.category, expected[1:]) == expected[1:]


def test_the_titrant_stock_shares_the_column_of_the_conditions(qapp, session):
    """The stock is a concentration of the same assay, so its field starts where the conditions' fields do."""
    state_binding(session, assay_type=AssayType.IDA)
    state_dilution(session, 1e-3)
    qapp.processEvents()
    view = session._binding

    def left(widget):
        return widget.mapTo(view.canvas, widget.rect().topLeft()).x()

    lefts = {left(row.value) for row in view._conditions.values()}
    assert lefts == {left(view.stock)} == {left(view.category)}


def test_a_dye_alone_file_sets_the_signal_bounds_to_what_it_measured(qapp, session, tmp_path):
    """A straight line through the calibration bounds the baseline and the free-dye signal to ±20 % of it."""
    state_binding(session, assay_type=AssayType.IDA)
    path = tmp_path / 'dye_alone.csv'
    rows = [f'{c:g},{100 + 2e6 * c + r},{r}' for r in (0, 1) for c in (0, 1e-6, 2e-6, 3e-6, 4e-6)]
    path.write_text('concentration,signal,replica\n' + '\n'.join(rows) + '\n')

    assert session.model.bounds_from_dye_alone(str(path)) is None

    bounds = session.model.settings.custom_bounds
    assert set(bounds) == {'I0', 'I_dye_free'}
    intercept, slope = 100.5, 2e6
    assert [b.to('au').magnitude for b in bounds['I0']] == pytest.approx([0.8 * intercept, 1.2 * intercept])
    assert [b.to('au/M').magnitude for b in bounds['I_dye_free']] == pytest.approx([0.8 * slope, 1.2 * slope])
    assert session._binding._bounds['I0'].fields[0].text == session.model.binding.bound_entries['I0'].amounts[0].text
    assert session.model.status == 'Bounds of I₀ and I_D set from the dye-alone calibration in dye_alone.csv'


def test_a_dye_alone_file_the_data_checks_refuse_is_named_with_the_refusal_itself(qapp, session, tmp_path):
    """The refusal names the file and the point and says what to do; a generic sentence would hide both."""
    path = tmp_path / 'dye_alone.csv'
    rows = [f'{c:g},{100 - 10 * i + r},{r}' for r in (0, 1) for i, c in enumerate((0, 1e-6, 2e-6, 3e-6, 4e-6))]
    path.write_text('concentration,signal,replica\n' + '\n'.join(rows) + '\n5e-6,,0\n5e-6,,1\n')
    state_binding(session, assay_type=AssayType.IDA)
    before = session.model.settings.custom_bounds

    refusal = session.model.bounds_from_dye_alone(str(path))

    assert refusal.message.startswith('No replicate in dye_alone.csv has a signal at 5 µM')
    assert 'delete that titration point' in refusal.message
    assert refusal.message.endswith('The signal bounds were not changed.')
    assert session.model.settings.custom_bounds == before


def test_the_command_shows_the_dye_alone_refusal_to_the_user(qapp, session, tmp_path, monkeypatch):
    """A calibration that cannot be used is said in a dialog, in the refusal's own words, never passed over."""
    path = tmp_path / 'dye_alone.csv'
    rows = [f'{c:g},{100 - 10 * i + r},{r}' for r in (0, 1) for i, c in enumerate((0, 1e-6, 2e-6, 3e-6, 4e-6))]
    path.write_text('concentration,signal,replica\n' + '\n'.join(rows) + '\n5e-6,,0\n5e-6,,1\n')
    state_binding(session, assay_type=AssayType.IDA)
    shown = []
    monkeypatch.setattr('gui.views.binding.QFileDialog.getOpenFileName', lambda *args: (str(path), ''))
    monkeypatch.setattr('gui.views.binding.QMessageBox.warning', lambda *args: shown.append(args[1:]))
    refusal = session.model.bounds_from_dye_alone(str(path))

    session._binding.dye_alone.click()

    assert shown == [(refusal.title, refusal.message)]


@pytest.mark.parametrize(
    ('assay_type', 'bounds', 'summary'),
    [
        (AssayType.IDA, {}, 'Fits K<sub>a</sub> guest and 3 signal parameters'),
        # I_H opens pinned at 0, so of I₀, I_G, I_H, I_HG and I_HG₂ four are fitted.
        (AssayType.DBA_HG2, {}, 'Fits K<sub>a</sub> HG, K<sub>a</sub> HG₂ and 4 signal parameters'),
        # Widened, I_H is fitted as well; the fit pins only where the bounds meet.
        (AssayType.DBA_HG2, {'I_H': (0.0, 1e9)}, 'Fits K<sub>a</sub> HG, K<sub>a</sub> HG₂ and 5 signal parameters'),
        # A binding constant or a signal held where its bounds meet is not fitted.
        (AssayType.IDA, {'Ka_guest': (1e5, 1e5), 'I0': (5.0, 5.0)}, 'Fits 2 signal parameters'),
    ],
)
def test_the_summary_counts_what_the_fit_fits_under_the_bounds_stated(qapp, session, assay_type, bounds, summary):
    state_binding(session, assay_type=assay_type, bounds=bounds)
    assert session._binding.summary.text() == summary


def test_each_bound_field_is_named_with_the_glossary_name_and_its_unit(qapp, session):
    """A screen reader hears the name the row shows: Kₐ guest by its glossary name, I_D as the row writes I<sub>D</sub>."""
    state_binding(session, assay_type=AssayType.IDA)
    view = session._binding
    names = [field.accessibleName() for row in view._bounds.values() for field in row.fields]
    assert names[:2] == ['Lower bound of Kₐ guest (M⁻¹)', 'Upper bound of Kₐ guest (M⁻¹)']
    named = [name.split(' bound of ')[1].split(' (')[0] for name in names[::2]]
    assert named == ['Kₐ guest', 'I₀', 'I_D', 'I_HD']


def test_the_dye_alone_command_is_offered_only_for_a_model_with_a_dye(qapp, session):
    """A dye-only calibration measures the dye; a stepwise host–guest model has none to bound."""
    view = session._binding
    state_binding(session, assay_type=AssayType.IDA)
    assert view.dye_alone.isVisibleTo(view.canvas)
    state_binding(session, assay_type=AssayType.DBA_HG2)
    assert not view.dye_alone.isVisibleTo(view.canvas)


def test_the_replicate_control_and_the_fit_setting_agree_both_ways(qapp, session):
    view = session._binding
    state_binding(session, assay_type=AssayType.IDA, per_replica=True)
    assert view.replicates.current == 1

    view.replicates._choose(0)
    assert session.model.settings.per_replica is False

    view.replicates._choose(1)
    assert session.model.settings.per_replica is True

    state_binding(session, per_replica=False)
    assert view.replicates.current == 0


def test_reset_brings_the_default_bounds_back_to_the_fit(qapp, session):
    state_binding(session, assay_type=AssayType.IDA, bounds={'Ka_guest': (1e2, 1e4)})
    assert session.model.settings.custom_bounds is not None

    session._binding.reset.click()

    assert session.model.settings.custom_bounds is None


def test_a_stock_typed_in_its_field_reaches_the_fit_in_the_unit_shown(qapp, session):
    from PyQt6.QtTest import QTest

    state_binding(session, assay_type=AssayType.IDA)
    view = session._binding
    view.dilution._choose(1)
    view.stock_unit.chosen.emit(view.stock_unit.options.index('mM'))
    QTest.keyClicks(view.stock.editor, '2')
    QTest.keyClick(view.stock.editor, Qt.Key.Key_Return)

    assert session.model.settings.conditions['titrant_stock'].to('M').magnitude == pytest.approx(2e-3)


def test_each_row_shows_its_own_problem_under_it(qapp, session):
    """A condition, a bound or the stock that cannot be used is named where it is entered, before any run."""
    form = session.model.binding
    state_binding(session, assay_type=AssayType.IDA)
    view = session._binding
    form.edit('h0', 'abc')
    form.edit_bound('Ka_guest', 0, '')
    form.set_diluted(True)
    session.model.binding_edited()

    def shown(problem):
        return problem.text.text() if problem.isVisibleTo(view.canvas) else None

    assert shown(view._conditions['h0'].problem) == form.condition_problem('h0')
    assert '“abc” is not a number' in shown(view._conditions['h0'].problem)
    assert shown(view._conditions['d0'].problem) is None
    assert shown(view._bounds['Ka_guest'].problem) == 'Kₐ guest: the lower bound is empty. Enter a number, such as 1e3.'
    assert shown(view._bounds['I0'].problem) is None
    assert shown(view.stock_problem).startswith('Enter the titrant stock concentration')

    # Back on constant totals the stock is not used, so the stock left empty is no problem of the fit.
    form.set_diluted(False)
    session.model.binding_edited()
    assert shown(view.stock_problem) is None


def test_a_condition_that_cannot_be_read_shows_no_number_under_input_uncertainty(qapp, session):
    """Input uncertainty states the entered value; a text that is no number has none to state, not NaN or 0."""
    from core.pipeline.inputs import InputSpec

    state_binding(session, assay_type=AssayType.IDA)
    model = session.model
    model.uncertainty.set_spec('h0', InputSpec.sigma_abs(0.2e-6))
    model.uncertainty_edited()
    model.binding.edit('h0', 'abc')
    model.binding_edited()
    session.show_view('Input uncertainty')
    qapp.processEvents()

    row = session._uncertainty._rows['h0']
    assert 'nan' not in row.entered.text().lower()
    assert not any(' is 0 ' in p for p in model.settings.input_problems)
