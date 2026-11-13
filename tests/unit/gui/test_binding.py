"""What the binding model of a session hands to a fit (:class:`gui.binding.BindingForm`), without widgets.

The two-level choice of the model; the conditions, each read in the unit it is shown in
and handed over in base units; the dilution by the titrant, which is off until the user
states it and then reaches the assay as the assay takes it; the bounds, refused in the
open when they cannot be used; and the replicate mode.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from core.assays import AssayType
from core.assays.registry import ASSAY_REGISTRY
from core.pipeline.varpro import REPLICATE_TEST_LEVEL
from core.units import Q_, Quantity
from gui.binding import CATEGORIES, REPLICATES_HELP_HTML, BindingForm, help_html
from gui.uncertainty import parse_amount
from gui.widgets.assay_conditions import ASSAY_CONDITIONS, assay_class


def _form(assay_type: AssayType = AssayType.IDA) -> BindingForm:
    return BindingForm(assay_type)


def _concentration_keys(assay_type: AssayType) -> list[str]:
    return [f.key for f in ASSAY_CONDITIONS[assay_type] if f.unit_type == 'concentration']


# ----------------------------------------------------------------------
# The model
# ----------------------------------------------------------------------


def test_each_category_lists_its_models_in_registry_order():
    assert set(CATEGORIES) == {meta.category for meta in ASSAY_REGISTRY.values()}
    for category, models in CATEGORIES.items():
        assert models == [at for at, meta in ASSAY_REGISTRY.items() if meta.category == category]


def test_choosing_a_category_picks_its_first_model_and_the_category_shown_keeps_its_model():
    form = _form(AssayType.DBA_H2G)
    form.set_value('h0', 1e-4)

    form.choose_category('Direct binding')
    assert form.assay_type is AssayType.DBA_H2G
    assert form.entry('h0').value() == 1e-4, 'the model shown already keeps what was stated for it'

    form.choose_category('Competitive displacement')
    assert form.assay_type is CATEGORIES['Competitive displacement'][0]


def test_choosing_the_model_shown_keeps_everything_stated_for_it():
    form = _form()
    form.set_diluted(True)
    form.choose_model(AssayType.IDA)
    assert form.diluted


@pytest.mark.parametrize(
    ('assay_type', 'badge'),
    [
        (AssayType.IDA, 'IDA · 1 binding constant'),
        (AssayType.DBA_HG2, 'HG₂ · 2 binding constants'),
        (AssayType.DYE_ALONE, 'Dye alone · no binding constant'),
    ],
)
def test_the_badge_counts_the_binding_constants_the_model_fits(assay_type, badge):
    assert _form(assay_type).badge() == badge


# ----------------------------------------------------------------------
# Conditions
# ----------------------------------------------------------------------


@pytest.mark.parametrize('assay_type', list(AssayType))
def test_an_untouched_form_states_the_defaults_with_constant_totals(assay_type):
    """No dilution key reaches the assay until the user states one, and every value is the field's default."""
    form = _form(assay_type)

    conditions = form.conditions()

    assert 'titrant_stock' not in conditions and 'stock_contains' not in conditions
    expected = {f.key: f.default for f in ASSAY_CONDITIONS[assay_type]}
    assert set(conditions) - {'mode'} == set(expected)
    for key, value in expected.items():
        assert conditions[key].magnitude == pytest.approx(value, rel=1e-12)
    assert conditions.get('mode') == {AssayType.DBA_HtoD: 'HtoD', AssayType.DBA_DtoH: 'DtoH'}.get(assay_type)
    assert form.problems() == []


@pytest.mark.parametrize('base_value', [1e-9, 50e-6])  # the smallest a coarse unit could round away, and a typical one
def test_switching_the_unit_keeps_the_concentration(base_value):
    """Every offered unit, the coarse M included, shows the same concentration."""
    form = _form()
    form.set_value('h0', base_value)
    for unit in ('nM', 'µM', 'mM', 'M', 'µM'):
        form.set_unit('h0', unit)
        entry = form.entry('h0')
        assert form.conditions()['h0'].to('M').magnitude == pytest.approx(base_value, rel=1e-12), unit
        # What the field shows is that concentration too: a keystroke in it reads the text, not the value kept.
        assert parse_amount(entry.amount.text) * entry.scale() == pytest.approx(base_value, rel=1e-12), unit


def test_a_typed_value_is_read_in_the_unit_shown_and_a_unit_switch_keeps_every_figure():
    form = _form()
    form.set_unit('h0', 'nM')
    form.edit('h0', '4300.25')
    assert form.conditions()['h0'].to('M').magnitude == pytest.approx(4.30025e-6, rel=1e-12)

    form.set_unit('h0', 'mM')

    assert form.entry('h0').amount.text == '0.00430025'
    assert form.conditions()['h0'].to('M').magnitude == pytest.approx(4.30025e-6, rel=1e-12)


def test_a_binding_constant_is_entered_in_inverse_molar():
    form = _form()
    form.edit('Ka_dye', '2.5e6')
    value = form.conditions()['Ka_dye']
    assert value.to('1/M').magnitude == pytest.approx(2.5e6)
    assert form.condition_units()['Ka_dye'] == 'M⁻¹'


@pytest.mark.parametrize(
    ('text', 'says'),
    [
        ('', '[Host]₀ has no value: enter a number.'),
        ('4,3', '[Host]₀: “4,3” is not a number. Enter a number, such as 2.5.'),
        ('−1', '[Host]₀ is below zero: enter a value of 0 or more.'),
    ],
)
def test_a_condition_that_cannot_be_used_is_named_and_reaches_no_fit_as_a_number(text, says):
    form = _form()
    form.edit('h0', text)

    assert form.problems() == [says]
    if text != '−1':
        assert math.isnan(form.conditions()['h0'].magnitude), 'a value that cannot be read is no number at all'


# ----------------------------------------------------------------------
# Dilution by the titrant: the choice is explicit, and off unless chosen.
# ----------------------------------------------------------------------


def test_choosing_dilution_adds_the_stock_and_the_species_it_holds_in_field_order():
    form = _form(AssayType.GDA)
    form.set_diluted(True)
    form.set_value('titrant_stock', 1e-2)
    # Ticked bottom-up; the order reported is the assay's, not the clicking order.
    form.set_contains('g0', True)
    form.set_contains('h0', True)
    form.set_contains('g0', False)
    form.set_contains('g0', True)

    conditions = form.conditions()

    assert conditions['titrant_stock'].to('M').magnitude == pytest.approx(1e-2)
    assert conditions['stock_contains'] == ('h0', 'g0')


def test_the_conditions_of_a_diluted_titration_build_the_assay_they_describe():
    """What the form hands over is what the assay takes: the two keys cross the seam."""
    form = _form()
    form.set_diluted(True)
    form.set_value('titrant_stock', 1e-3)
    form.set_contains('d0', True)

    assay = assay_class(form.assay_type)(
        x_data=Q_(np.array([0.0, 1e-5, 2e-5]), 'M'),
        y_data=Q_(np.array([1.0, 0.8, 0.6]), 'au'),
        **form.conditions(),
    )

    # The dye is in the stock and stays; the host is diluted by 2 % at the last point.
    assert assay.fixed_total('d0', np.array([2e-5])) == pytest.approx(6e-6)
    assert assay.fixed_total('h0', np.array([2e-5]))[0] == pytest.approx(4.3e-6 * 0.98)


def test_dilution_without_a_stock_is_refused_in_plain_language():
    form = _form()
    form.set_diluted(True)

    (problem,) = form.problems()

    assert problem.startswith('Enter the titrant stock concentration, or choose “Stay constant”.')


def test_a_stock_holding_every_fixed_concentration_is_the_constant_case():
    form = _form()
    form.set_diluted(True)
    form.set_value('titrant_stock', 1e-3)
    for key in _concentration_keys(AssayType.IDA):
        form.set_contains(key, True)

    (problem,) = form.problems()

    assert '“Stay constant”' in problem and '[Host]₀' in problem and '[Dye]₀' in problem


def test_the_stock_keeps_its_value_and_unit_across_a_change_of_model():
    """The choice above it returns to constant totals, so the stock carried over is seen before it reaches a fit."""
    form = _form()
    form.set_diluted(True)
    form.set_unit('titrant_stock', 'mM')
    form.edit('titrant_stock', '2')

    form.choose_model(AssayType.GDA)
    form.choose_model(AssayType.IDA)

    assert not form.diluted and 'titrant_stock' not in form.conditions()
    assert (form.stock.unit, form.stock.amount.text) == ('mM', '2')
    form.set_diluted(True)
    assert form.conditions()['titrant_stock'].to('M').magnitude == pytest.approx(2e-3, rel=1e-12)
    assert form.problems() == []


def test_choosing_a_model_returns_to_constant_totals_even_the_model_shown():
    """A stock carried over would reach a fit unseen; the demo chooses the model it already shows."""
    form = _form()
    form.set_diluted(True)
    form.set_value('titrant_stock', 1e-3)
    form.set_contains('h0', True)

    form.set_assay(AssayType.IDA)

    assert 'titrant_stock' not in form.conditions() and not form.contains and not form.diluted


def test_dye_alone_offers_no_dilution():
    """Nothing is diluted where there is no fixed concentration."""
    form = _form(AssayType.DYE_ALONE)
    form.set_diluted(True)

    assert not form.offers_dilution and not form.diluted
    assert form.conditions() == {} and form.problems() == []


@pytest.mark.parametrize('assay_type', [at for at in AssayType if at is not AssayType.DYE_ALONE])
def test_the_species_of_the_stock_are_offered_only_where_there_is_a_choice(assay_type):
    """One fixed concentration cannot be in the stock — that would dilute nothing."""
    form = _form(assay_type)
    assert form.offers_contains == (len(_concentration_keys(assay_type)) > 1)


@pytest.mark.parametrize('assay_type', [AssayType.DBA_HG2, AssayType.DBA_H2G])
def test_the_conditions_of_a_stepwise_model_build_its_assay(assay_type):
    conditions = _form(assay_type).conditions()
    assert set(conditions) == {'h0'} and isinstance(conditions['h0'], Quantity)

    assay = assay_class(assay_type)(
        x_data=Q_(np.linspace(1e-6, 1e-3, 10), 'M'), y_data=Q_(np.ones(10), 'au'), **conditions
    )
    assert assay.h0.to('M').magnitude > 0


# ----------------------------------------------------------------------
# Bounds
# ----------------------------------------------------------------------


def test_the_default_bounds_are_usable_and_reported_as_untouched():
    form = _form()
    assert form.bound_problems() == []
    assert form.custom_bounds() is None  # nothing edited: the registry defaults apply


def test_an_unreadable_bound_is_named_and_is_not_passed_on():
    form = _form()

    form.edit_bound('Ka_guest', 0, '1e')
    assert form.bound_problems() == ['Kₐ guest: the lower bound “1e” is not a number. Enter a number, such as 1e3.']
    assert 'Ka_guest' not in (form.custom_bounds() or {}) and form.bounds()['Ka_guest'] is None

    form.edit_bound('Ka_guest', 0, '')
    assert form.bound_problems() == ['Kₐ guest: the lower bound is empty. Enter a number, such as 1e3.']

    form.edit_bound('Ka_guest', 0, '1e3')
    assert form.bound_problems() == []
    assert form.custom_bounds()['Ka_guest'][0] == Q_(1e3, '1/M')


def test_a_lower_bound_above_the_upper_one_is_refused():
    """A backwards search range is not a range the optimiser can use."""
    form = _form()
    form.set_bounds('Ka_guest', 1e8, 1e6)
    assert form.bound_problems() == ['Kₐ guest: the lower bound must not be above the upper bound.']
    assert 'Ka_guest' not in (form.custom_bounds() or {})


def test_equal_bounds_pin_the_parameter_and_are_passed_on():
    """Equal bounds hold a parameter at a value instead of fitting it, so they are carried through."""
    form = _form()
    form.set_bounds('Ka_guest', 3.14e8, 3.14e8)
    assert form.bound_problems() == []
    lo, hi = form.custom_bounds()['Ka_guest']
    assert (lo.magnitude, hi.magnitude) == (3.14e8, 3.14e8)


def test_a_signal_parameter_has_no_upper_limit_until_one_is_entered():
    """An empty upper field of a signal parameter means no limit; a binding constant is searched, so it needs both."""
    form = _form()
    entry = form.bound_entries['I_dye_bound']
    assert entry.amounts[1].text == '' and entry.values() == (0.0, math.inf)

    form.edit_bound('I_dye_bound', 1, '5e9')
    assert set(form.custom_bounds()) == {'I_dye_bound'}  # the rows left at their defaults are not passed on
    assert form.custom_bounds()['I_dye_bound'][1].magnitude == 5e9

    form.edit_bound('I_dye_bound', 1, '')
    assert form.bound_problems() == [] and form.custom_bounds() is None

    form.edit_bound('Ka_guest', 1, '')
    assert form.bound_problems() == ['Kₐ guest: the upper bound is empty. Enter a number, such as 1e3.']


def test_reset_brings_the_defaults_back():
    form = _form()
    form.set_bounds('Ka_guest', 1e2, 1e4)
    form.edit_bound('I0', 0, 'x')
    form.reset_bounds()
    assert form.custom_bounds() is None and form.bound_problems() == []


def test_a_bound_set_from_code_is_the_very_number_it_was_written_from():
    """A recorded bound is compared to the twelfth figure, so it may not be rounded to the figures shown."""
    form = _form()
    form.set_bounds('Ka_guest', 1.2345678901234e3, 9.87654321e9)
    lo, hi = form.custom_bounds()['Ka_guest']
    assert (lo.magnitude, hi.magnitude) == (1.2345678901234e3, 9.87654321e9)
    # and it is the number shown: the text reads back as that very number
    assert [parse_amount(a.text) for a in form.bound_entries['Ka_guest'].amounts] == [lo.magnitude, hi.magnitude]


def test_a_dye_alone_bound_is_used_as_shown_so_retyping_it_changes_nothing():
    """A calibration's ±20 % bound is fitted with the number on screen, not with figures the field does not show."""
    form = _form()
    form.apply_dye_alone({'I0': (Q_(9876.5424, 'au'), Q_(14814.8136, 'au'))})
    entry = form.bound_entries['I0']
    shown = [a.text for a in entry.amounts]
    before = form.custom_bounds()['I0']

    assert [b.magnitude for b in before] == [parse_amount(text) for text in shown]
    for index, text in enumerate(shown):
        form.edit_bound('I0', index, text)
    assert form.custom_bounds()['I0'] == before


def test_dye_alone_bounds_reach_the_signal_coefficients_it_measured_only():
    form = _form()
    form.apply_dye_alone({'I0': (Q_(80.0, 'au'), Q_(120.0, 'au')), 'I_dye_free': (Q_(0.8, 'au/µM'), Q_(1.2, 'au/µM'))})

    bounds = form.custom_bounds()
    assert set(bounds) == {'I0', 'I_dye_free'}
    assert bounds['I_dye_free'][0].to('au/M').magnitude == pytest.approx(0.8e6)
    assert _form(AssayType.DBA_HG2).dye_alone_keys() == ()  # no dye to calibrate


# ----------------------------------------------------------------------
# Replicates and help
# ----------------------------------------------------------------------


def test_the_replicate_help_states_the_level_and_the_replicate_count_the_test_needs():
    """Guards the help against drifting from the rule the engine applies."""
    level = f'{REPLICATE_TEST_LEVEL:.0%}'.replace('%', '&thinsp;%')
    assert level in REPLICATES_HELP_HTML
    assert '<b>three</b>' in REPLICATES_HELP_HTML  # the smallest number of replicates the test runs on
    assert 'fit of the <i>average</i>' in REPLICATES_HELP_HTML


@pytest.mark.parametrize('assay_type', list(AssayType))
def test_the_help_describes_the_model_and_each_of_its_parameters(assay_type):
    from gui.assay_descriptions import ASSAY_DESCRIPTIONS
    from gui.parameter_descriptions import PARAMETER_DESCRIPTIONS

    html = help_html(assay_type)
    assert ASSAY_DESCRIPTIONS[assay_type.name][1] in html
    for key in ASSAY_REGISTRY[assay_type].default_bounds:
        assert PARAMETER_DESCRIPTIONS[key][1] in html


def test_the_help_explains_only_what_the_model_offers():
    """A calibration has no binding constant, no dye-alone command and no replicate test to explain."""
    calibration = help_html(AssayType.DYE_ALONE)
    # (Its own description says how a binding session uses the calibration; the command's section is not there.)
    for absent in (
        '<h4>Bounds from dye alone',
        'Each replicate separately',
        'association constant is',
        'no upper',
        'Titrant stock',
    ):
        assert absent not in calibration, absent
    assert 'fitted from the average of the replicates switched on' in calibration

    ida = help_html(AssayType.IDA)
    assert '<h4>Bounds from dye alone' in ida and REPLICATES_HELP_HTML in ida

    # A stepwise host–guest model has no dye: the help offers no calibration.
    assert '<h4>Bounds from dye alone' not in help_html(AssayType.DBA_HG2)


@pytest.mark.parametrize('assay_type', list(AssayType))
def test_the_help_names_the_views_as_the_window_does(assay_type):
    """The window has views, not tabs, and each by its own name."""
    import re

    html = help_html(assay_type)
    assert not re.search(r'\btab\b', html)
    assert 'the <i>Ka confidence' not in html


@pytest.mark.parametrize('assay_type', list(AssayType))
def test_the_help_headings_are_in_sentence_case(assay_type):
    """DESIGN.md §9: only a heading's first word is capitalised, besides names and symbols (DBA, Kₐ, I₀)."""
    import re

    from gui.plotting.labels import plain_label

    html = help_html(assay_type)
    headings = re.findall(r'<h[34]>(.*?)</h[34]>', html) + re.findall(r'<p><b>(.*?)</b></p>', html)
    for heading in headings:
        words = plain_label(heading).split()[1:]
        assert not [w for w in words if re.fullmatch(r'[A-Z][a-z]+\W*', w)], heading
