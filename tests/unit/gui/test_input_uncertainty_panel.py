"""The Input Uncertainty panel: what the user states about the inputs a fit rests on.

Pins the whole error model that reaches the fit and the sensitivity analysis from what
the user sets — each input's own uncertainty, the errors several inputs have in common,
and the random error of each titrant addition:

- every input opens *fixed* and no source is stated, so a fit takes the entered inputs
  as exact until something is stated, and the panel reports no problem;
- what :meth:`current_errors` hands on is what the rows state — fixed inputs left out,
  a percentage in percent and an absolute σ or range in the input's own base unit,
  neither converted on the way — plus the shared sources in the order they are shown
  and the additions entry;
- a shared source that states no error a titration can have is refused by name, and so
  is an additions entry of zero, each shown on its own row before a run is attempted;
- Tab runs from the input rows through the additions entry and the Add button to the
  shared sources, whatever order the widgets were built in;
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
- each assay's entries, kinds and units, its shared sources and its additions entry come
  back on switching back to it, and never reach another assay;
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
from core.pipeline.inputs import (  # noqa: E402
    TITRANT,
    AdditionError,
    ErrorModel,
    InputSpec,
    SharedSource,
    SpecKind,
)
from core.units import Q_  # noqa: E402

_KA_DYE = 16.8e6  # M⁻¹, the Ka,dye set in the conditions form
_H0 = 4.3e-6  # M

_SEQUENTIAL = 'sequential additions into one cuvette'
_SEPARATE = 'separately prepared samples'


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


def _add_shared(panel, name: str, sigma_pct: float, keys):
    """Add a shared error source and fill it in, as a user does; return its row."""
    panel._add_shared_btn.click()
    row = panel._shared_rows[-1]
    row._name.setText(name)
    row._sigma.setValue(sigma_pct)
    for key in keys:
        row._ticks[key].setChecked(True)
    return row


def _set_additions(panel, mode: str, sigma_pct: float) -> None:
    """Choose an additions mode and its σ, as a user does."""
    index = panel._additions_combo.findText(mode)
    assert index >= 0, mode
    panel._additions_combo.setCurrentIndex(index)
    panel._additions_sigma.setValue(sigma_pct)


def _assert_spec(actual: InputSpec | None, expected: InputSpec) -> None:
    assert actual is not None
    assert (actual.kind, actual.relative) == (expected.kind, expected.relative)
    assert (actual.sigma, actual.lo, actual.hi) == pytest.approx((expected.sigma, expected.lo, expected.hi), rel=1e-12)


def test_every_input_starts_fixed_so_a_fit_takes_the_entered_inputs_as_exact(qapp):
    """Nothing is assumed about the inputs until the user says something: no source, no problem."""
    panel = _ida_panel()

    assert [row.kind.currentText() for row in panel._rows.values()] == ['fixed'] * len(panel._rows)
    assert all(row.spec() is None for row in panel._rows.values())
    # The empty model: no input moves, nothing is shared, and no error is stated on the additions.
    assert panel.current_errors() == ErrorModel()
    assert panel.problems() == []
    assert panel._shared_rows == []
    assert panel._additions_combo.currentText() == 'none'
    assert panel._additions_sigma_row.isHidden()

    # The kind a user then picks starts from a usable number rather than an empty box.
    _choose(panel._rows['h0'], 'σ %')
    assert panel.current_errors() == ErrorModel(specs={'h0': InputSpec.sigma_pct(5.0)})


def test_current_errors_leaves_fixed_inputs_out_and_hands_on_what_the_rows_state(qapp):
    """A percentage stays a percentage and an absolute σ stays in the input's base unit."""
    panel = _ida_panel()
    panel._rows['h0'].set_spec(InputSpec.sigma_pct(3.0))
    panel._rows['Ka_dye'].set_spec(InputSpec.sigma_abs(0.84e6))
    panel._rows['d0'].set_spec(InputSpec.interval_abs(5.7e-6, 6.2e-6))
    panel._rows[TITRANT].set_spec(None)

    specs = panel.current_errors().specs

    assert set(specs) == {'h0', 'Ka_dye', 'd0'}
    assert specs['h0'] == InputSpec(SpecKind.SIGMA, sigma=3.0, relative=True)
    _assert_spec(specs['Ka_dye'], InputSpec(SpecKind.SIGMA, sigma=0.84e6, relative=False))
    _assert_spec(specs['d0'], InputSpec(SpecKind.INTERVAL, lo=5.7e-6, hi=6.2e-6, relative=False))


def test_specs_changed_reports_an_edit_a_kind_and_a_rebuild(qapp):
    panel = _ida_panel()
    seen = []
    panel.specs_changed.connect(lambda: seen.append(panel.current_errors().specs))

    _choose(panel._rows['h0'], 'σ %')
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
        (InputSpec.sigma_pct(5.0), 'σ', InputSpec.sigma_abs(0.84e6)),
        (InputSpec.sigma_pct(5.0), 'range', InputSpec.interval_abs(15.96e6, 17.64e6)),
        (InputSpec.sigma_abs(0.84e6), 'σ %', InputSpec.sigma_pct(5.0)),
        (InputSpec.sigma_abs(0.84e6), 'range', InputSpec.interval_abs(15.96e6, 17.64e6)),
        (InputSpec.interval_abs(15.96e6, 17.64e6), 'range %', InputSpec.interval_pct(-5.0, 5.0)),
        # A lopsided range keeps its ends in the other unit; as a σ it keeps half its width.
        (InputSpec.interval_pct(-6.0, 4.0), 'range', InputSpec.interval_abs(15.792e6, 17.472e6)),
        (InputSpec.interval_pct(-6.0, 4.0), 'σ %', InputSpec.sigma_pct(5.0)),
        (InputSpec.interval_abs(15.792e6, 17.472e6), 'σ', InputSpec.sigma_abs(0.84e6)),
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


def test_the_help_tells_an_input_own_error_from_a_shared_one_and_says_what_each_feeds():
    """Three statements, three readers: an own entry, a shared source, and the error of each addition."""
    from gui.widgets.input_uncertainty_panel import _UNCERTAINTY_HELP_HTML

    text = ' '.join(_UNCERTAINTY_HELP_HTML.split())
    # An own entry against a shared one, and where a shared one comes from.
    assert 'the error <b>only that input</b> has' in text
    assert 'come from one stock, were weighed on one balance or pipetted with one pipette' in text
    # Both readers use the model as stated — the analysis no longer assumes unrelated inputs.
    assert 'Both the interval of every fit and the K<sub>a</sub> Sensitivity analysis use exactly this model' in text
    assert 'take their errors to be unrelated' not in text
    # A binding constant measured with a shared stock moves the other way from the concentrations made from it.
    assert 'by the same percentage the other way' in text
    # The additions feed the analysis alone, and the interval of a fit does not hold them.
    assert 'feeds the K<sub>a</sub> Sensitivity analysis only' in text
    assert 'the interval the fit reports does not include the random error of each addition' in text
    assert 'already measures' not in text
    # What the σ means with replicates, and what that assumes of them.
    assert 'as σ/√<i>m</i> for <i>m</i> replicates' in text
    assert 'assumes the replicates are separate titrations' in text


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
        ('Ka_dye', InputSpec.sigma_abs(2e8), 'σ %', 'Ka,dye: σ would be 1190.5 %; this box can only show 1000 %.'),
        ('h0', InputSpec.sigma_pct(150.0), 'range', '[Host]₀: “from” would be −2.15 µM; this box can only show 0 µM.'),
        ('h0', InputSpec.sigma_abs(2e-9), 'σ %', '[Host]₀: σ would be 0.046512 %; this box can only show 0 %.'),
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

    _choose(row, 'σ')
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
    assert panel.current_errors().specs['Ka_dye'] == InputSpec(SpecKind.INTERVAL, lo=-6.0, hi=4.0)


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
    _choose(d0, 'σ %')
    _assert_spec(d0.spec(), InputSpec.sigma_pct(3.0))

    panel.set_assay_type(AssayType.DBA_DtoH)
    panel._rows['fixed_conc'].set_spec(InputSpec.interval_abs(143.45e-6, 158.55e-6))
    panel.set_assay_type(AssayType.DBA_HtoD)
    assert panel._rows['fixed_conc'].spec() is None


def test_the_panel_states_the_whole_error_model(qapp):
    """Each input's own uncertainty, what two of them share, and the error of each addition."""
    panel = _ida_panel()
    panel._rows['h0'].set_spec(InputSpec.sigma_pct(3.0))
    panel._rows[TITRANT].set_spec(InputSpec.interval_pct(-2.0, 2.0))
    _add_shared(panel, 'Host and dye stock', 4.0, ('d0', 'h0'))
    _set_additions(panel, _SEQUENTIAL, 1.5)

    errors = panel.current_errors()

    assert errors.specs == {'h0': InputSpec.sigma_pct(3.0), TITRANT: InputSpec.interval_pct(-2.0, 2.0)}
    # The inputs of a source are listed as the panel lists them, whatever order they were ticked in.
    assert errors.shared == (SharedSource('Host and dye stock', 4.0, ('h0', 'd0')),)
    assert errors.additions == AdditionError(1.5, sequential=True)
    assert panel.problems() == []

    # A second source is reported after the first, in the order the rows are shown.
    _add_shared(panel, 'Guest pipette', 2.0, ('d0', TITRANT))
    assert [source.name for source in panel.current_errors().shared] == ['Host and dye stock', 'Guest pipette']

    # Separately prepared samples carry no error from one point to the next.
    _set_additions(panel, _SEPARATE, 1.5)
    assert panel.current_errors().additions == AdditionError(1.5, sequential=False)

    # "none" is the absence of a statement, not an error of zero, and hides the σ.
    panel._additions_combo.setCurrentIndex(panel._additions_combo.findText('none'))
    assert panel.current_errors().additions is None
    assert panel._additions_sigma_row.isHidden()

    # Removing a source takes it out of the model.
    panel._shared_rows[0]._remove_btn.click()
    assert [source.name for source in panel.current_errors().shared] == ['Guest pipette']


def test_a_shared_source_offers_every_input_of_the_assay_named_as_the_panel_names_it(qapp):
    """The tick list is the assay's inputs, labelled as the rows above label them, as rich text."""
    from PyQt6.QtCore import Qt

    from gui.plotting.labels import plain_label

    panel = _ida_panel()
    panel._add_shared_btn.click()
    row = panel._shared_rows[0]

    assert list(row._ticks) == list(panel.input_labels())
    assert [label.textFormat() for label in row._labels.values()] == [Qt.TextFormat.RichText] * len(row._ticks)
    assert {key: plain_label(label.text()) for key, label in row._labels.items()} == panel.input_labels()
    # A fresh source is named for the user to overwrite and states an uncertainty to edit.
    assert row._name.text() == 'Shared source 1'
    assert row._sigma.value() > 0
    # Another source gets a name of its own, so two never collide by default.
    panel._add_shared_btn.click()
    assert panel._shared_rows[1]._name.text() == 'Shared source 2'


@pytest.mark.parametrize(
    ('spoil', 'problem'),
    [
        (
            lambda row: row._name.setText('  '),
            'A shared error source has no name. Give it a name, or remove it.',
        ),
        (
            lambda row: row._sigma.setValue(0.0),
            "The uncertainty of the shared error source 'Host and dye stock' has to be above zero. "
            'Enter it in percent, or remove the source.',
        ),
        (
            lambda row: row._ticks['d0'].setChecked(False),
            'A shared error source has to apply to at least two inputs. '
            "'Host and dye stock' applies to one: tick a second input, or remove it and enter the "
            'uncertainty on the input itself.',
        ),
    ],
)
def test_a_shared_source_that_states_no_error_a_titration_can_have_is_refused_naming_it(qapp, spoil, problem):
    """The panel refuses what the fit would refuse, in the same words, before a run starts."""
    panel = _ida_panel()
    row = _add_shared(panel, 'Host and dye stock', 4.0, ('h0', 'd0'))
    assert panel.problems() == []

    spoil(row)

    assert panel.problems() == [problem]


def test_two_shared_sources_of_one_name_are_refused(qapp):
    """A name is how every report calls the source, so two sources cannot share one."""
    panel = _ida_panel()
    _add_shared(panel, 'Host and dye stock', 4.0, ('h0', 'd0'))
    _add_shared(panel, 'Host and dye stock', 2.0, ('h0', TITRANT))

    assert panel.problems() == ["Two shared error sources are named 'Host and dye stock'. Give each its own name."]


def test_every_source_that_cannot_be_used_is_named_at_once(qapp):
    """The input rows all report together; the sources below them have to as well, or fixing one finds the next."""
    panel = _ida_panel()
    first = _add_shared(panel, 'Host and dye stock', 4.0, ('h0', 'd0'))
    second = _add_shared(panel, 'Titrant stock', 2.0, ('h0', TITRANT))
    _set_additions(panel, _SEPARATE, 0.0)

    first._sigma.setValue(0.0)
    second._ticks['h0'].setChecked(False)

    assert panel.problems() == [
        "The uncertainty of the shared error source 'Host and dye stock' has to be above zero. "
        'Enter it in percent, or remove the source.',
        "A shared error source has to apply to at least two inputs. 'Titrant stock' applies to one: tick a "
        'second input, or remove it and enter the uncertainty on the input itself.',
        "The random error of each addition has to be above zero. Enter it in percent, or set it to 'none'.",
    ]


def test_an_additions_error_that_cannot_vary_is_refused(qapp):
    """Choosing a mode states that the additions scatter; a σ of 0 says the opposite."""
    panel = _ida_panel()
    _set_additions(panel, _SEPARATE, 0.0)

    assert panel.problems() == [
        "The random error of each addition has to be above zero. Enter it in percent, or set it to 'none'."
    ]

    panel._additions_sigma.setValue(1.0)
    assert panel.problems() == []


def test_the_shared_sources_and_the_additions_come_back_on_switching_back(qapp):
    """They are remembered per assay, like the input rows: another assay starts with none."""
    panel = _ida_panel()
    _add_shared(panel, 'Host and dye stock', 4.0, ('h0', 'd0'))
    _set_additions(panel, _SEPARATE, 1.5)

    panel.set_assay_type(AssayType.GDA)
    assert panel.current_errors() == ErrorModel()
    assert panel._shared_rows == []
    assert panel._additions_combo.currentText() == 'none'
    assert panel._additions_sigma_row.isHidden()

    panel.set_assay_type(AssayType.IDA)
    errors = panel.current_errors()
    assert errors.shared == (SharedSource('Host and dye stock', 4.0, ('h0', 'd0')),)
    assert errors.additions == AdditionError(1.5, sequential=False)
    assert not panel._additions_sigma_row.isHidden()


def test_specs_changed_reports_every_shared_source_and_additions_control(qapp):
    """Whatever the user changes here changes the model, so the session hears about all of it."""
    panel = _ida_panel()
    seen = []
    panel.specs_changed.connect(lambda: seen.append(panel.current_errors()))

    def reports(action) -> bool:
        before = len(seen)
        action()
        return len(seen) > before

    assert reports(panel._add_shared_btn.click)
    row = panel._shared_rows[0]
    assert reports(lambda: row._name.setText('Host and dye stock'))
    assert reports(lambda: row._sigma.setValue(4.0))
    assert reports(lambda: row._ticks['h0'].setChecked(True))
    assert reports(lambda: row._ticks['d0'].setChecked(True))
    assert seen[-1].shared == (SharedSource('Host and dye stock', 4.0, ('h0', 'd0')),)

    assert reports(lambda: panel._additions_combo.setCurrentIndex(panel._additions_combo.findText(_SEQUENTIAL)))
    assert reports(lambda: panel._additions_sigma.setValue(1.5))
    assert seen[-1].additions == AdditionError(1.5, sequential=True)

    assert reports(row._remove_btn.click)
    assert seen[-1].shared == ()


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
    assert panel.current_errors() == ErrorModel()

    # Every assay whose signal the engine can project is open, the two-constant ones included.
    for assay_type in (AssayType.IDA, AssayType.DBA_HG2, AssayType.DBA_H2G):
        panel.set_assay_type(assay_type)
        assert panel.isEnabled()
        assert panel._unavailable.isHidden()


def test_every_control_locks_while_a_run_is_live(qapp):
    panel = _ida_panel()
    _add_shared(panel, 'Host and dye stock', 4.0, ('h0', 'd0'))
    _set_additions(panel, _SEPARATE, 1.5)

    panel.set_running(True)
    controls = [
        *(row.kind for row in panel._rows.values()),
        *panel._rows.values(),
        panel._add_shared_btn,
        *panel._shared_rows,
        panel._additions_combo,
        panel._additions_sigma,
    ]
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
    for kind in ('σ %', 'range %', 'σ', 'range', 'fixed'):
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
    _choose(row, 'σ')
    (box,) = row._values.currentWidget()._boxes
    box.selectAll()
    QTest.keyClicks(box, '2e6')

    assert box.text() == '2e6'
    _assert_spec(row.spec(), InputSpec.sigma_abs(2e6))
    _assert_spec(panel.current_errors().specs['Ka_dye'], InputSpec.sigma_abs(2e6))


def test_typed_text_that_is_not_a_number_is_named_as_a_problem(qapp):
    from PyQt6.QtTest import QTest

    panel = _ida_panel()
    row = panel._rows['Ka_dye']
    _choose(row, 'σ')
    (box,) = row._values.currentWidget()._boxes
    box.selectAll()
    QTest.keyClicks(box, '2e')

    assert 'is not a number' in row.problem() and row.name in row.problem()
    assert panel.problems() == [row.problem()]


def test_a_typed_absolute_value_is_used_as_shown(qapp):
    """A value typed with more figures than the box shows is used as the box shows it."""
    panel = _ida_panel()
    row = panel._rows['Ka_dye']
    _choose(row, 'σ')
    (box,) = row._values.currentWidget()._boxes
    box.setText('1234567')
    box.editingFinished.emit()

    assert box.text() == '1.2346e6'
    _assert_spec(row.spec(), InputSpec.sigma_abs(1.2346e6))


def test_set_specs_states_those_uncertainties_and_nothing_else(qapp):
    """What Demo IDA states: the uncertainties it names, every other input exact, no source beside them."""
    panel = _ida_panel()
    _choose(panel._rows['d0'], 'range %')
    _add_shared(panel, 'Host and dye stock', 4.0, ('h0', 'd0'))
    _set_additions(panel, _SEQUENTIAL, 2.0)
    seen = []
    panel.specs_changed.connect(lambda: seen.append(panel.current_errors()))
    specs = {'Ka_dye': InputSpec.sigma_pct(10.0), 'h0': InputSpec.sigma_pct(3.0)}

    panel.set_specs(specs)

    assert seen == [ErrorModel(specs=specs)]
    assert panel._rows['d0'].kind.currentText() == 'fixed'
    assert panel._shared_rows == [] and panel._additions_combo.currentText() == 'none'


def test_the_shared_source_ticks_stand_clear_of_their_labels(qapp):
    """The macOS style lays a check box out by a rectangle narrower than the one it paints.

    Unless the box is laid out by its own rectangle, the label beside it starts on
    the box. Offscreen (Fusion) the two rectangles coincide; the native run is what
    reproduces the overlap.
    """
    from PyQt6.QtCore import Qt

    panel = _ida_panel()
    row = _add_shared(panel, 'Host and dye stock', 4.0, ('h0', 'd0'))
    panel.resize(490, 900)
    panel.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    panel.show()
    qapp.processEvents()

    for key, tick in row._ticks.items():
        assert row._labels[key].geometry().x() > tick.geometry().right(), key


def _shown_problems(panel) -> list[str]:
    """What the panel shows under its shared sources and its additions entry, in that order."""
    shown = [row._warning.text() for row in panel._shared_rows if row._warning.isVisibleTo(panel)]
    return shown + ([panel._additions_warning.text()] if panel._additions_warning.isVisibleTo(panel) else [])


def test_a_shared_source_that_cannot_be_used_says_so_on_the_row(qapp):
    """An input row shows its problem in place; a source has to as well, or the user runs to find out."""
    panel = _ida_panel()
    row = _add_shared(panel, 'Host and dye stock', 4.0, ('h0', 'd0'))
    assert _shown_problems(panel) == []

    row._sigma.setValue(0.0)

    assert _shown_problems(panel) == [
        "The uncertainty of the shared error source 'Host and dye stock' has to be above zero. "
        'Enter it in percent, or remove the source.'
    ]
    # Fixing it takes the warning off the row again.
    row._sigma.setValue(4.0)
    assert _shown_problems(panel) == []


def test_the_additions_entry_that_cannot_be_used_says_so_under_it(qapp):
    panel = _ida_panel()

    _set_additions(panel, _SEPARATE, 0.0)

    assert _shown_problems(panel) == [
        "The random error of each addition has to be above zero. Enter it in percent, or set it to 'none'."
    ]


def test_each_source_is_told_its_own_fault_where_several_are_wrong(qapp):
    """The row a problem belongs to is the one that shows it, the duplicated name included."""
    panel = _ida_panel()
    _add_shared(panel, 'Host and dye stock', 4.0, ('h0', 'd0'))
    _add_shared(panel, 'Host and dye stock', 2.0, ('h0', TITRANT))
    _add_shared(panel, 'Pipette', 3.0, ('h0', 'd0'))

    assert [row._warning.isVisibleTo(panel) for row in panel._shared_rows] == [False, True, False]
    assert _shown_problems(panel) == [
        "Two shared error sources are named 'Host and dye stock'. Give each its own name."
    ]
    # What a run refuses with is the same list.
    assert panel.problems() == _shown_problems(panel)


def test_tab_runs_from_the_input_rows_through_the_additions_to_the_shared_sources(qapp):
    """The additions entry and the Add button are built before the rows, so the order is set after each rebuild."""
    from PyQt6.QtCore import Qt

    panel = _ida_panel()
    panel.resize(490, 900)
    panel.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    panel.show()
    qapp.processEvents()
    shared = _add_shared(panel, 'Host and dye stock', 4.0, ('h0', 'd0'))

    expected = [widget for row in panel._rows.values() for widget in row.focus_widgets()]
    expected += [panel._additions_combo, panel._additions_sigma, panel._add_shared_btn, *shared.focus_widgets()]

    reached, widget = [], expected[0]
    for _ in range(600):
        widget = widget.nextInFocusChain()
        if widget is expected[0]:
            break
        if widget in expected:
            reached.append(widget)
    assert reached == expected[1:]
