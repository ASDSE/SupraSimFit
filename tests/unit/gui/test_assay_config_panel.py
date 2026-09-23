"""What the Assay Configuration panel hands to a fit.

The two-level (category → subtype) selector: the dependent dropdowns react
correctly and exactly one ``assay_type_changed`` is emitted per selection — the
contract the fitting session and demo loader rely on. The unit-aware fields:
every value crosses in base units. The dilution choice: the totals stay constant
unless the user says otherwise, and once they do, the stock and the species it
holds reach the assay as the assay takes them.
"""

import numpy as np
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel

from core.assays import AssayType
from core.assays.registry import ASSAY_REGISTRY
from core.pipeline.inputs import shared_key
from core.units import Q_, Quantity
from gui.widgets.assay_conditions import ASSAY_CONDITIONS, ConditionField, result_input_labels
from gui.widgets.assay_config_panel import AssayConfigPanel, _UnitWidget


@pytest.fixture
def panel(qapp):
    return AssayConfigPanel()


def _direct_binding_types():
    return [at for at, m in ASSAY_REGISTRY.items() if m.category == 'Direct Binding']


def test_default_is_gda_without_emission(qapp):
    emitted = []
    p = AssayConfigPanel()
    p.assay_type_changed.connect(emitted.append)
    # Construction must not fire the signal (matches prior single-combo init).
    assert p.current_assay_type() is AssayType.GDA
    assert emitted == []


def test_set_assay_type_selects_category_and_subtype_once(panel):
    emitted = []
    panel.assay_type_changed.connect(emitted.append)

    panel.set_assay_type(AssayType.IDA)

    assert panel.current_assay_type() is AssayType.IDA
    assert panel._main_combo.currentData() == 'Competitive Displacement'
    assert panel._sub_combo.currentData() is AssayType.IDA
    assert emitted == [AssayType.IDA]  # exactly one emission


def test_changing_category_repopulates_subtypes_and_emits_once(panel):
    emitted = []
    panel.assay_type_changed.connect(emitted.append)

    panel._main_combo.setCurrentIndex(panel._main_combo.findData('Direct Binding'))

    direct = _direct_binding_types()
    sub_data = [panel._sub_combo.itemData(i) for i in range(panel._sub_combo.count())]
    assert sub_data == direct  # subtype combo now lists exactly the category's assays
    assert panel.current_assay_type() is direct[0]  # first subtype applied
    assert emitted == [direct[0]]  # one emission for the category switch, not two


def test_changing_subtype_within_category_emits_that_assay(panel):
    panel.set_assay_type(AssayType.DBA_HtoD)  # Direct Binding
    emitted = []
    panel.assay_type_changed.connect(emitted.append)

    panel._sub_combo.setCurrentIndex(panel._sub_combo.findData(AssayType.DBA_H2G))

    assert panel.current_assay_type() is AssayType.DBA_H2G
    assert emitted == [AssayType.DBA_H2G]


class TestUnitWidgetInputConversion:
    """The primary user-input boundary: _UnitWidget always returns a base-unit
    Quantity (M / M⁻¹) regardless of the display unit selected (G13)."""

    def test_concentration_default_returns_base_molar(self, qapp):
        w = _UnitWidget(ConditionField('h0', '[Host]', '', 50e-6, 'M', 'concentration'))
        v = w.value()
        assert v.units == Q_(1, 'M').units
        assert v.to('M').magnitude == pytest.approx(50e-6)

    # Switching a field's display unit must never alter the physical quantity —
    # for *every* offered unit, including a coarse one like 'M'. Regression for a
    # fixed 3-decimal spinbox that silently rounded a small value to 0 on switch
    # (e.g. 50 µM shown as M → 0.000), zeroing the condition and corrupting fits.
    @pytest.mark.parametrize('base_value', [1e-9, 50e-6])  # smallest (where the bug bit) + typical
    def test_switching_display_unit_preserves_quantity(self, qapp, base_value):
        w = _UnitWidget(ConditionField('h0', '[Host]', '', base_value, 'M', 'concentration'))
        for idx, (label, _) in enumerate(w._units):  # includes 'M', where the bug bit
            w._combo.setCurrentIndex(idx)
            got = w.value().to('M').magnitude
            assert got == pytest.approx(base_value, rel=1e-9), (
                f'switching to {label!r} changed {base_value} M to {got} M'
            )

    def test_spinbox_value_interpreted_in_display_unit(self, qapp):
        w = _UnitWidget(ConditionField('h0', '[Host]', '', 1e-6, 'M', 'concentration'))
        w._combo.setCurrentText('µM')
        w._spinbox.setValue(5.0)  # 5 µM
        assert w.value().to('M').magnitude == pytest.approx(5e-6)

    def test_binding_constant_returns_inverse_molar(self, qapp):
        w = _UnitWidget(ConditionField('Ka_dye', 'Ka', '', 1e6, 'M⁻¹', 'binding_constant'))
        assert w.value().to('1/M').magnitude == pytest.approx(1e6)


# ----------------------------------------------------------------------
# Dilution by the titrant: the choice is explicit, and off unless chosen.
# ----------------------------------------------------------------------


def _expected_default_conditions(assay_type: AssayType) -> dict:
    """What the panel's form has always answered, derived from the field registry alone."""
    expected = {f.key: f.default for f in ASSAY_CONDITIONS[assay_type]}
    if assay_type is AssayType.DBA_HtoD:
        expected['mode'] = 'HtoD'
    elif assay_type is AssayType.DBA_DtoH:
        expected['mode'] = 'DtoH'
    return expected


def _concentration_keys(assay_type: AssayType) -> list[str]:
    return [f.key for f in ASSAY_CONDITIONS[assay_type] if f.unit_type == 'concentration']


@pytest.mark.parametrize('assay_type', list(AssayType))
def test_untouched_panel_states_constant_totals(panel, assay_type):
    """The default is today's fit exactly: no dilution key reaches the assay."""
    panel.set_assay_type(assay_type)

    conditions = panel.current_conditions()

    assert 'titrant_stock' not in conditions
    assert 'stock_contains' not in conditions
    expected = _expected_default_conditions(assay_type)
    assert set(conditions) == set(expected)
    for key, value in expected.items():
        got = conditions[key]
        if isinstance(got, Quantity):
            assert got.magnitude == pytest.approx(value)
        else:
            assert got == value
    assert panel.problems() == []


def test_choosing_dilution_adds_the_stock_and_the_species_it_holds(panel):
    panel.set_assay_type(AssayType.IDA)
    panel._dilution_combo.setCurrentIndex(1)
    panel._stock_widget.setValue(1e-3)
    panel._contains_boxes['h0'].setChecked(True)

    conditions = panel.current_conditions()

    assert conditions['titrant_stock'].to('M').magnitude == pytest.approx(1e-3)
    assert conditions['stock_contains'] == ('h0',)
    assert panel.problems() == []


def test_species_the_stock_holds_are_reported_in_field_order(panel):
    """``stock_contains`` names conditions in the order the assay declares them."""
    panel.set_assay_type(AssayType.GDA)
    panel._dilution_combo.setCurrentIndex(1)
    panel._stock_widget.setValue(1e-2)
    # Ticked bottom-up; the order reported is the assay's, not the clicking order.
    panel._contains_boxes['g0'].setChecked(True)
    panel._contains_boxes['h0'].setChecked(True)

    assert panel.current_conditions()['stock_contains'] == ('h0', 'g0')


def test_panel_conditions_build_a_diluted_assay(panel):
    """What the panel hands over is what the assay takes: the two keys cross the seam."""
    panel.set_assay_type(AssayType.IDA)
    panel._dilution_combo.setCurrentIndex(1)
    panel._stock_widget.setValue(1e-3)
    panel._contains_boxes['d0'].setChecked(True)

    assay = panel.get_assay_class()(
        x_data=Q_(np.array([0.0, 1e-5, 2e-5]), 'M'),
        y_data=Q_(np.array([1.0, 0.8, 0.6]), 'au'),
        **panel.current_conditions(),
    )

    assert assay.titrant_stock.to('M').magnitude == pytest.approx(1e-3)
    assert assay.stock_contains == ('d0',)
    # The dye is in the stock and stays; the host is diluted by 2 % at the last point.
    assert assay.fixed_total('d0', np.array([2e-5])) == pytest.approx(6e-6)
    assert assay.fixed_total('h0', np.array([2e-5]))[0] == pytest.approx(4.3e-6 * 0.98)


def test_dilution_without_a_stock_is_refused_in_plain_language(panel):
    panel.set_assay_type(AssayType.IDA)
    panel._dilution_combo.setCurrentIndex(1)  # stock left at its 0 default

    problems = panel.problems()

    assert len(problems) == 1
    assert 'titrant stock' in problems[0].lower()
    assert 'stay constant' in problems[0]


def test_a_stock_holding_everything_is_the_constant_case(panel):
    panel.set_assay_type(AssayType.IDA)
    panel._dilution_combo.setCurrentIndex(1)
    panel._stock_widget.setValue(1e-3)
    for box in panel._contains_boxes.values():
        box.setChecked(True)

    problems = panel.problems()

    assert len(problems) == 1
    assert 'stay constant' in problems[0]
    assert '[Host]₀' in problems[0] and '[Dye]₀' in problems[0]


def test_switching_assay_returns_to_constant_totals(panel):
    panel.set_assay_type(AssayType.IDA)
    panel._dilution_combo.setCurrentIndex(1)
    panel._stock_widget.setValue(1e-3)
    panel._contains_boxes['h0'].setChecked(True)

    panel.set_assay_type(AssayType.GDA)
    assert 'titrant_stock' not in panel.current_conditions()

    # The same assay again is a fresh form too — the demo loader reselects one.
    panel.set_assay_type(AssayType.IDA)
    assert 'titrant_stock' not in panel.current_conditions()
    assert not any(box.isChecked() for box in panel._contains_boxes.values())


def test_dye_alone_offers_no_dilution(panel):
    """Nothing is diluted where there is no fixed concentration."""
    panel.set_assay_type(AssayType.DYE_ALONE)

    assert not panel._dilution_widget.isVisibleTo(panel)
    assert panel.current_conditions() == {}
    assert panel.problems() == []


@pytest.mark.parametrize(
    'assay_type',
    [at for at in AssayType if at is not AssayType.DYE_ALONE],
)
def test_species_checkboxes_only_where_a_choice_exists(panel, assay_type):
    """One fixed concentration cannot be in the stock — that would dilute nothing."""
    panel.set_assay_type(assay_type)
    expected = _concentration_keys(assay_type)

    assert list(panel._contains_boxes) == (expected if len(expected) > 1 else [])


def test_dilution_labels_are_rich_text(panel):
    panel.set_assay_type(AssayType.IDA)

    labels = [panel._dilution_label] + panel._contains_widget.findChildren(QLabel)
    assert labels
    for lbl in labels:
        assert lbl.textFormat() == Qt.TextFormat.RichText
    assert '<sub>0</sub>' in panel._dilution_label.text()


def test_each_dilution_control_reports_one_finished_edit(panel):
    panel.set_assay_type(AssayType.IDA)
    edits = []
    panel.conditions_edited.connect(lambda: edits.append(None))

    panel._dilution_combo.setCurrentIndex(1)
    assert len(edits) == 1

    panel._contains_boxes['h0'].setChecked(True)
    assert len(edits) == 2

    panel._stock_widget._spinbox.setValue(1.0)
    panel._stock_widget.edit_finished.emit()
    assert len(edits) == 3


def test_the_stock_is_named_and_formatted_like_a_condition(panel):
    """``_mismatch_note`` names a stored fit's inputs through these two."""
    panel.set_assay_type(AssayType.IDA)
    panel._dilution_combo.setCurrentIndex(1)
    panel._stock_widget._combo.setCurrentText('mM')

    assert panel.condition_name('titrant_stock') == 'Titrant stock concentration'
    assert panel.format_condition('titrant_stock', Q_(1e-3, 'M')) == '1 mM'


def test_result_input_labels_names_a_shared_source():
    plain = result_input_labels('IDA')
    assert plain['h0'] == '[Host]₀'
    assert not any(key.startswith('shared:') for key in plain)

    fit_config = {
        'input_uncertainty': {},
        'shared_sources': [{'name': 'Host and dye stock', 'sigma_pct': 3.0, 'inputs': ['h0', 'd0']}],
    }
    labelled = result_input_labels('IDA', fit_config)

    assert labelled[shared_key('Host and dye stock')] == 'Host and dye stock (shared by [Host]₀, [Dye]₀)'
    assert {k: v for k, v in labelled.items() if not k.startswith('shared:')} == plain


def _lay_out(panel, qapp) -> None:
    """Resolve the panel's geometry without putting a window on screen."""
    panel.resize(490, 700)
    panel.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    panel.show()
    qapp.processEvents()


def _tab_order(start, wanted: list) -> list:
    """The widgets of *wanted* in the order Tab reaches them from *start*."""
    reached, widget = [], start
    for _ in range(400):
        widget = widget.nextInFocusChain()
        if widget is start:
            break
        if widget in wanted:
            reached.append(widget)
    return reached


def test_both_dilution_answers_are_read_without_opening_the_list(panel):
    """The point of the control is that the assumption is stated, so the closed combo shows it in full."""
    from PyQt6.QtGui import QFontMetrics

    panel.set_assay_type(AssayType.IDA)
    combo = panel._dilution_combo
    metrics = QFontMetrics(combo.font())
    widest = max(metrics.horizontalAdvance(combo.itemText(i)) for i in range(combo.count()))

    assert combo.sizeHint().width() >= widest


@pytest.mark.parametrize('assay_type', [AssayType.IDA, AssayType.GDA, AssayType.DBA_HG2])
def test_the_titrant_stock_shares_the_column_of_the_conditions(qapp, assay_type):
    """The stock is a concentration of the same assay, so its box starts where the conditions' boxes do."""
    panel = AssayConfigPanel()
    panel.set_assay_type(assay_type)
    panel._dilution_combo.setCurrentIndex(1)
    _lay_out(panel, qapp)

    def left(widget):
        box = widget.focus_widgets()[0]
        return box.mapTo(panel, box.rect().topLeft()).x()

    lefts = {left(widget) for widget in panel._field_widgets.values()}
    assert lefts == {left(panel._stock_widget)}


def test_tab_runs_from_the_conditions_through_the_stock_to_the_species_it_holds(qapp):
    """Keyboard entry of a diluted assay follows the panel, not the order the widgets were built in."""
    panel = AssayConfigPanel()
    panel.set_assay_type(AssayType.IDA)
    panel._dilution_combo.setCurrentIndex(1)
    _lay_out(panel, qapp)

    expected = [widget for field in panel._field_widgets.values() for widget in field.focus_widgets()]
    expected += [panel._dilution_combo, *panel._stock_widget.focus_widgets(), *panel._contains_boxes.values()]

    assert _tab_order(panel._sub_combo, expected) == expected


def test_a_second_assay_leaves_the_dilution_controls_behind_its_conditions(qapp):
    """The ticks are rebuilt per assay, so the order is set again after every switch."""
    panel = AssayConfigPanel()
    panel.set_assay_type(AssayType.IDA)
    panel.set_assay_type(AssayType.GDA)
    panel._dilution_combo.setCurrentIndex(1)
    _lay_out(panel, qapp)

    expected = [widget for field in panel._field_widgets.values() for widget in field.focus_widgets()]
    expected += [panel._dilution_combo, *panel._stock_widget.focus_widgets(), *panel._contains_boxes.values()]

    assert _tab_order(panel._sub_combo, expected) == expected


def test_the_species_ticks_stand_clear_of_their_sentences(qapp):
    """The macOS style lays a check box out by a rectangle narrower than the one it paints.

    Unless the box is laid out by its own rectangle, the sentence beside it starts on the
    box. Offscreen (Fusion) the two rectangles coincide; the native run is what
    reproduces the overlap.
    """
    panel = AssayConfigPanel()
    panel.set_assay_type(AssayType.IDA)
    panel._dilution_combo.setCurrentIndex(1)
    _lay_out(panel, qapp)

    for box in panel._contains_boxes.values():
        (sentence,) = box.parentWidget().findChildren(QLabel)
        assert box.geometry().x() >= 0
        assert sentence.geometry().x() > box.geometry().right()
