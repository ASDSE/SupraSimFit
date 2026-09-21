"""The Input Uncertainty panel: what the user states about the inputs a fit rests on.

Pins what reaches the fit and the sensitivity analysis from what the user sets:

- every input opens *fixed*, so a fit takes the entered inputs as exact until an
  uncertainty is stated, and the panel reports no spec and no problem;
- what :meth:`current_specs` hands on is what the rows state — fixed inputs left out,
  a percentage in percent and an absolute σ or range in the input's own base unit,
  neither converted on the way;
- choosing another kind carries the numbers over (σ = s ↔ range −s..+s, percent ↔
  the input's unit through its set value in the conditions form), and a range becomes
  the σ of half its width; the help does not call that the same uncertainty;
- a number the new kind's boxes cannot hold is named under the input; a conversion that
  needs a set value above 0 waits for one, with a warning that blocks the fit;
- a range entered as −6 % .. +4 % is exactly that interval;
- an input set so it cannot vary (σ = 0, "to" not above "from") shows a warning naming
  it and :meth:`problems` names it; only *fixed* leaves an input out;
- a range that would take an input down to zero is named as a problem;
- every input is named as the panel shows it;
- each assay's entries, kinds and units come back on switching back to it, and never
  reach another assay;
- an assay that fits no association constant is closed with one sentence saying why;
- the rows lock while a fit or an analysis is live;
- the panel is as wide whichever kind each input shows;
- the help says what the uncertainties feed and what each kind means for the interval.

Require a ``QApplication`` (the ``qapp`` fixture).
"""

from __future__ import annotations

import pytest

pytest.importorskip('PyQt6')

from core.assays.registry import AssayType  # noqa: E402
from core.pipeline.inputs import TITRANT, InputSpec, SpecKind  # noqa: E402
from core.units import Q_  # noqa: E402

_KA_DYE = 16.8e6  # M⁻¹, the Ka,dye set in the conditions form
_H0 = 4.3e-6  # M


def _ida_panel():
    from gui.widgets.input_uncertainty_panel import InputUncertaintyPanel

    panel = InputUncertaintyPanel()
    panel.set_assay_type(AssayType.IDA)
    panel.set_nominal_values({'Ka_dye': Q_(_KA_DYE, '1/M'), 'h0': Q_(_H0, 'M'), 'd0': Q_(6e-6, 'M')})
    return panel


def _choose(row, kind: str) -> None:
    """Pick *kind* in the row's selector, as a user does."""
    index = row.kind.findText(kind)
    assert index >= 0, kind
    row.kind.setCurrentIndex(index)


def _assert_spec(actual: InputSpec | None, expected: InputSpec) -> None:
    assert actual is not None
    assert (actual.kind, actual.relative) == (expected.kind, expected.relative)
    assert (actual.sigma, actual.lo, actual.hi) == pytest.approx((expected.sigma, expected.lo, expected.hi), rel=1e-12)


def test_every_input_starts_fixed_so_a_fit_takes_the_entered_inputs_as_exact(qapp):
    """Nothing is assumed about the inputs until the user says something: no spec, no problem."""
    panel = _ida_panel()

    assert [row.kind.currentText() for row in panel._rows.values()] == ['fixed'] * len(panel._rows)
    assert all(row.spec() is None for row in panel._rows.values())
    assert panel.current_specs() == {}
    assert panel.problems() == []

    # The kind a user then picks starts from a usable number rather than an empty box.
    _choose(panel._rows['h0'], '± σ %')
    assert panel.current_specs() == {'h0': InputSpec.sigma_pct(5.0)}


def test_current_specs_leaves_fixed_inputs_out_and_hands_on_what_the_rows_state(qapp):
    """A percentage stays a percentage and an absolute σ stays in the input's base unit."""
    panel = _ida_panel()
    panel._rows['h0'].set_spec(InputSpec.sigma_pct(3.0))
    panel._rows['Ka_dye'].set_spec(InputSpec.sigma_abs(0.84e6))
    panel._rows['d0'].set_spec(InputSpec.interval_abs(5.7e-6, 6.2e-6))
    panel._rows[TITRANT].set_spec(None)

    specs = panel.current_specs()

    assert set(specs) == {'h0', 'Ka_dye', 'd0'}
    assert specs['h0'] == InputSpec(SpecKind.SIGMA, sigma=3.0, relative=True)
    _assert_spec(specs['Ka_dye'], InputSpec(SpecKind.SIGMA, sigma=0.84e6, relative=False))
    _assert_spec(specs['d0'], InputSpec(SpecKind.INTERVAL, lo=5.7e-6, hi=6.2e-6, relative=False))


def test_specs_changed_reports_an_edit_a_kind_and_a_rebuild(qapp):
    panel = _ida_panel()
    seen = []
    panel.specs_changed.connect(lambda: seen.append(panel.current_specs()))

    _choose(panel._rows['h0'], '± σ %')
    assert seen and seen[-1] == {'h0': InputSpec.sigma_pct(5.0)}

    (box,) = panel._rows['h0']._values.currentWidget()._boxes
    box.setValue(2.0)
    assert seen[-1] == {'h0': InputSpec.sigma_pct(2.0)}

    seen.clear()
    panel.set_assay_type(AssayType.GDA)
    assert seen and seen[-1] == {}


@pytest.mark.parametrize(
    ('start', 'kind', 'expected'),
    [
        # σ = 5 % of Ka,dye = 16.8e6 M⁻¹, stated four ways.
        (InputSpec.sigma_pct(5.0), 'range %', InputSpec.interval_pct(-5.0, 5.0)),
        (InputSpec.sigma_pct(5.0), '± σ', InputSpec.sigma_abs(0.84e6)),
        (InputSpec.sigma_pct(5.0), 'range', InputSpec.interval_abs(15.96e6, 17.64e6)),
        (InputSpec.sigma_abs(0.84e6), '± σ %', InputSpec.sigma_pct(5.0)),
        (InputSpec.sigma_abs(0.84e6), 'range', InputSpec.interval_abs(15.96e6, 17.64e6)),
        (InputSpec.interval_abs(15.96e6, 17.64e6), 'range %', InputSpec.interval_pct(-5.0, 5.0)),
        # A lopsided range keeps its ends in the other unit; as a σ it keeps half its width.
        (InputSpec.interval_pct(-6.0, 4.0), 'range', InputSpec.interval_abs(15.792e6, 17.472e6)),
        (InputSpec.interval_pct(-6.0, 4.0), '± σ %', InputSpec.sigma_pct(5.0)),
        (InputSpec.interval_abs(15.792e6, 17.472e6), '± σ', InputSpec.sigma_abs(0.84e6)),
    ],
)
def test_choosing_another_kind_carries_the_numbers_over(qapp, start, kind, expected):
    panel = _ida_panel()
    row = panel._rows['Ka_dye']
    row.set_spec(start)

    _choose(row, kind)

    _assert_spec(row.spec(), expected)


def test_help_says_the_numbers_carry_over_and_the_spread_changes():
    """σ = 5 % and the range −5 % to +5 % are different spreads, so the help never calls the switch the same uncertainty."""
    from gui.widgets.input_uncertainty_panel import _UNCERTAINTY_HELP_HTML

    text = ' '.join(_UNCERTAINTY_HELP_HTML.split())
    assert 'keeps the uncertainty' not in text and 'uncertainty over' not in text
    assert 'carries the numbers over' in text
    assert 'an even draw between −5 % and +5 % varies less than a σ of 5 %' in text


def test_the_help_says_what_the_uncertainties_feed_and_what_each_kind_means_for_the_fit():
    """Both readers of these specs are named, and the interval is promised as usually wider, never as a diagnosis."""
    from gui.widgets.input_uncertainty_panel import _UNCERTAINTY_HELP_HTML

    text = ' '.join(_UNCERTAINTY_HELP_HTML.split())
    # The two things a stated uncertainty feeds.
    assert 'The interval of every fit.' in text
    assert 'K<sub>a</sub> Sensitivity analysis' in text
    # A σ is a penalty the fit pays, a range is a box, fixed is exact.
    assert 'moving it by <i>e</i> costs (<i>e</i>/σ)<sup>2</sup>' in text
    assert 'every value between them is equally acceptable and none outside' in text
    assert 'the input is taken as exact' in text
    # Fixed everywhere is the interval conditional on the entered inputs.
    assert 'With every input fixed, as the panel starts, the reported interval is the interval' in text
    assert 'conditional on the entered inputs' in text
    # The interval usually widens; the wording never promises it always does.
    assert 'Stating uncertainties usually widens the interval.' in text
    assert 'always widens' not in text


@pytest.mark.parametrize(
    ('key', 'start', 'kind', 'note'),
    [
        (
            TITRANT,
            InputSpec.sigma_pct(150.0),
            'range %',
            'Guest (titrant, whole series): “from” would be −150 %; this box can only show −100 %.',
        ),
        ('Ka_dye', InputSpec.sigma_abs(2e8), '± σ %', 'Ka,dye: σ would be 1190.5 %; this box can only show 1000 %.'),
        ('h0', InputSpec.sigma_pct(150.0), 'range', '[Host]₀: “from” would be −2.15 µM; this box can only show 0 µM.'),
        ('h0', InputSpec.sigma_abs(2e-9), '± σ %', '[Host]₀: σ would be 0.046512 %; this box can only show 0 %.'),
    ],
)
def test_a_number_the_new_kind_cannot_hold_is_named_under_the_input(qapp, key, start, kind, note):
    panel = _ida_panel()
    row = panel._rows[key]
    row.set_spec(start)
    _choose(row, kind)

    assert not row._warning.isHidden()
    assert note in row._warning.text().split('\n')
    # The next edit is the user's own value: the note goes.
    row._values.currentWidget().edited.emit()
    assert note not in row._warning.text()


def test_a_conversion_needing_a_set_value_waits_for_one_and_blocks_the_fit_meanwhile(qapp):
    panel = _ida_panel()
    row = panel._rows['h0']
    row.set_nominal(0.0)
    _choose(row, 'range')

    message = (
        '[Host]₀ is 0 in the conditions, so its uncertainty cannot be converted to “range”: set [Host]₀ above 0 first.'
    )
    assert row._warning.text() == message
    assert panel.problems() == [message]

    row.set_nominal(_H0)
    _assert_spec(row.spec(), InputSpec.interval_abs(0.95 * _H0, 1.05 * _H0))
    assert row._warning.isHidden() and panel.problems() == []

    # A value in the input's unit cannot be read against a set value of 0 either.
    row.set_nominal(0.0)
    assert panel.problems() == [
        '[Host]₀ is 0 in the conditions, so an uncertainty in its unit cannot be used: set [Host]₀ above 0 first.'
    ]


def test_percent_to_unit_uses_the_value_set_in_the_conditions_form(qapp):
    """σ = 5 % of [Host]₀ = 10 µM is 0.5 µM, not 5 % of the form's default."""
    from gui.widgets.assay_config_panel import AssayConfigPanel

    assay_panel = AssayConfigPanel()
    assay_panel.set_assay_type(AssayType.IDA)
    assay_panel._field_widgets['h0']._spinbox.setValue(10.0)  # µM

    panel = _ida_panel()
    panel.set_nominal_values(assay_panel.current_conditions())
    row = panel._rows['h0']

    _choose(row, '± σ')
    _assert_spec(row.spec(), InputSpec.sigma_abs(0.5e-6))
    _choose(row, 'range')
    _assert_spec(row.spec(), InputSpec.interval_abs(9.5e-6, 10.5e-6))


def test_fixed_carries_the_last_uncertainty_into_the_next_kind(qapp):
    panel = _ida_panel()
    row = panel._rows['Ka_dye']
    row.set_spec(InputSpec.interval_pct(-6.0, 4.0))

    _choose(row, 'fixed')
    assert row.spec() is None
    _choose(row, 'range %')

    _assert_spec(row.spec(), InputSpec.interval_pct(-6.0, 4.0))


def test_a_range_from_minus_6_to_plus_4_percent_is_exactly_that_interval(qapp):
    panel = _ida_panel()
    row = panel._rows['Ka_dye']
    _choose(row, 'range %')
    low, high = row._values.currentWidget()._boxes
    low.setValue(-6.0)
    high.setValue(4.0)

    assert row.spec() == InputSpec(SpecKind.INTERVAL, lo=-6.0, hi=4.0)
    assert panel.current_specs()['Ka_dye'] == InputSpec(SpecKind.INTERVAL, lo=-6.0, hi=4.0)


@pytest.mark.parametrize(
    ('spec', 'instruction'),
    [
        (InputSpec.interval_pct(5.0, 0.0), 'set “to” above “from”'),
        (InputSpec.interval_abs(16.8e6, 16.8e6), 'set “to” above “from”'),
        (InputSpec.sigma_abs(0.0), 'set σ above 0'),
    ],
)
def test_an_input_that_cannot_vary_warns_and_is_named_as_a_problem(qapp, spec, instruction):
    panel = _ida_panel()
    row = panel._rows['Ka_dye']

    row.set_spec(spec)

    assert not row._warning.isHidden()
    assert row._warning.text() == f'Ka,dye cannot vary: {instruction}, or choose “fixed”.'
    assert panel.problems() == [f'Ka,dye cannot vary: {instruction}, or choose “fixed”.']


def test_a_range_that_reaches_zero_is_named_as_a_problem(qapp):
    """A range end at −100 % would ask the model to fit with no host at all; a σ is a penalty above zero and may stay."""
    panel = _ida_panel()
    row = panel._rows['h0']

    row.set_spec(InputSpec.interval_pct(-100.0, 5.0))
    assert panel.problems() == ['[Host]₀ would be taken down to zero: set “from” above −100 %.']
    assert not row._warning.isHidden()

    row.set_spec(InputSpec.interval_abs(0.0, 5e-6))
    assert panel.problems() == ['[Host]₀ would be taken down to zero: set “from” above 0.']

    row.set_spec(InputSpec.sigma_pct(80.0))
    assert panel.problems() == []


def test_the_rows_are_the_assays_perturbable_inputs(qapp):
    """One row per input a fit can move: the titrant plus every concentration / binding-constant condition."""
    from gui.widgets.input_uncertainty_panel import InputUncertaintyPanel

    panel = InputUncertaintyPanel()

    panel.set_assay_type(AssayType.IDA)
    assert set(panel._rows) == {TITRANT, 'Ka_dye', 'h0', 'd0'}

    panel.set_assay_type(AssayType.GDA)
    assert set(panel._rows) == {TITRANT, 'Ka_dye', 'h0', 'g0'}

    # A single-condition assay: just the titrant and its one fixed concentration.
    panel.set_assay_type(AssayType.DBA_HtoD)
    assert set(panel._rows) == {TITRANT, 'fixed_conc'}


def test_input_labels_name_every_input_as_the_panel_shows_it(qapp):
    """A message about an input names it as the panel does, the titrant included."""
    panel = _ida_panel()

    labels = panel.input_labels()

    assert set(labels) == set(panel._rows)
    assert labels == {
        TITRANT: 'Guest (titrant, whole series)',
        'h0': '[Host]₀',
        'd0': '[Dye]₀',
        'Ka_dye': 'Ka,dye',
    }


def test_each_assays_entries_come_back_on_switching_back_and_reach_no_other_assay(qapp):
    """IDA's absolute Ka,dye range, its [Host]₀ σ in nM and a [Dye]₀ put back to fixed all come back as left.

    GDA, whose Ka,dye and [Host]₀ are other set values, starts from its own fixed rows; so does
    DBA host-to-dye, whose fixed_conc is the host where dye-to-host's is the dye.
    """
    panel = _ida_panel()
    panel._rows['Ka_dye'].set_spec(InputSpec.interval_abs(15.96e6, 17.64e6))
    h0 = panel._rows['h0']
    h0.set_spec(InputSpec.sigma_abs(0.2e-6))
    h0._values.currentWidget().set_unit_index(h0._values.currentWidget()._unit_combo.findText('nM'))
    d0 = panel._rows['d0']
    d0.set_spec(InputSpec.sigma_pct(3.0))
    _choose(d0, 'fixed')

    panel.set_assay_type(AssayType.GDA)
    assert all(row.spec() is None for row in panel._rows.values())
    panel.set_assay_type(AssayType.IDA)

    _assert_spec(panel._rows['Ka_dye'].spec(), InputSpec.interval_abs(15.96e6, 17.64e6))
    h0 = panel._rows['h0']
    _assert_spec(h0.spec(), InputSpec.sigma_abs(0.2e-6))
    assert [box.text() for box in h0._values.currentWidget()._boxes] == ['200']
    assert h0._values.currentWidget()._unit_combo.currentText() == 'nM'
    d0 = panel._rows['d0']
    assert d0.spec() is None
    _choose(d0, '± σ %')
    _assert_spec(d0.spec(), InputSpec.sigma_pct(3.0))

    panel.set_assay_type(AssayType.DBA_DtoH)
    panel._rows['fixed_conc'].set_spec(InputSpec.interval_abs(143.45e-6, 158.55e-6))
    panel.set_assay_type(AssayType.DBA_HtoD)
    assert panel._rows['fixed_conc'].spec() is None


def test_an_assay_with_no_association_constant_is_unavailable_and_says_why(qapp):
    """An uncertainty only widens an interval of a Ka, so an assay that fits none is closed with a reason."""
    from core.pipeline.varpro import projectable
    from gui.widgets.input_uncertainty_panel import InputUncertaintyPanel

    closed = [assay_type for assay_type in AssayType if not projectable(assay_type)]
    assert closed == [AssayType.DYE_ALONE]
    panel = InputUncertaintyPanel()

    panel.set_assay_type(AssayType.DYE_ALONE)
    assert not panel.isEnabled()
    assert not panel._unavailable.isHidden()
    assert panel._unavailable.text() == (
        'Dye Alone has no association constant, so an uncertainty in the inputs changes nothing here.'
    )
    assert panel.current_specs() == {}

    # Every assay whose signal the engine can project is open, the two-constant ones included.
    for assay_type in (AssayType.IDA, AssayType.DBA_HG2, AssayType.DBA_H2G):
        panel.set_assay_type(assay_type)
        assert panel.isEnabled()
        assert panel._unavailable.isHidden()


def test_the_rows_lock_while_a_run_is_live(qapp):
    panel = _ida_panel()
    panel.set_running(True)
    controls = [*(row.kind for row in panel._rows.values()), *panel._rows.values()]
    assert not any(control.isEnabled() for control in controls)
    panel.set_running(False)
    assert all(control.isEnabled() for control in controls)


def test_the_panel_is_as_wide_whichever_kind_each_input_shows(qapp):
    """Switching kinds never changes the panel's minimum width, so the sidebar never jumps."""
    from PyQt6.QtCore import Qt

    panel = _ida_panel()
    panel.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    panel.show()
    qapp.processEvents()
    widths = set()
    for kind in ('± σ %', 'range %', '± σ', 'range', 'fixed'):
        for key, row in panel._rows.items():
            _choose(row, kind if row.kind.findText(kind) >= 0 else 'range %')
        qapp.processEvents()
        widths.add(panel.minimumSizeHint().width())
    # A warning wraps inside that width.
    panel._rows['h0'].set_spec(InputSpec.interval_pct(5.0, 0.0))
    qapp.processEvents()
    widths.add(panel.minimumSizeHint().width())
    panel.close()

    assert len(widths) == 1


def test_a_typed_value_counts_before_the_box_loses_focus(qapp):
    """Run can be clicked without leaving the box (a toolbar click on macOS); the number on screen is used."""
    from PyQt6.QtTest import QTest

    panel = _ida_panel()
    row = panel._rows['Ka_dye']
    _choose(row, '± σ')
    (box,) = row._values.currentWidget()._boxes
    box.selectAll()
    QTest.keyClicks(box, '2e6')

    assert box.text() == '2e6'
    _assert_spec(row.spec(), InputSpec.sigma_abs(2e6))
    _assert_spec(panel.current_specs()['Ka_dye'], InputSpec.sigma_abs(2e6))


def test_typed_text_that_is_not_a_number_is_named_as_a_problem(qapp):
    from PyQt6.QtTest import QTest

    panel = _ida_panel()
    row = panel._rows['Ka_dye']
    _choose(row, '± σ')
    (box,) = row._values.currentWidget()._boxes
    box.selectAll()
    QTest.keyClicks(box, '2e')

    assert 'is not a number' in row.problem() and row.name in row.problem()
    assert panel.problems() == [row.problem()]


def test_a_typed_absolute_value_is_used_as_shown(qapp):
    """A value typed with more figures than the box shows is used as the box shows it."""
    panel = _ida_panel()
    row = panel._rows['Ka_dye']
    _choose(row, '± σ')
    (box,) = row._values.currentWidget()._boxes
    box.setText('1234567')
    box.editingFinished.emit()

    assert box.text() == '1.2346e6'
    _assert_spec(row.spec(), InputSpec.sigma_abs(1.2346e6))


def test_reset_to_defaults_takes_every_input_as_exact_again(qapp):
    """Demo IDA promises the same run every time, so it resets these settings as it resets the bounds."""
    panel = _ida_panel()
    _choose(panel._rows['h0'], '± σ %')
    _choose(panel._rows[TITRANT], 'range %')
    seen = []
    panel.specs_changed.connect(lambda: seen.append(panel.current_specs()))

    panel.reset_to_defaults()

    assert panel.current_specs() == {}
    assert [row.kind.currentText() for row in panel._rows.values()] == ['fixed'] * len(panel._rows)
    assert seen == [{}]  # the session is told, so a fit made with the old ones is marked out of date
