"""What the user states about the inputs a fit rests on: the rules of :class:`gui.uncertainty.UncertaintyForm`.

Pins the whole error model that reaches the fit and the sensitivity analysis from what
the user states — each input's own uncertainty, the errors several inputs have in common,
and the random error of each titrant addition:

- every input opens *Fixed* and no source is stated, so a fit takes the entered inputs
  as exact until something is stated, and nothing is a problem;
- :meth:`errors` hands on what the inputs state — fixed ones left out, a percentage in
  percent and an absolute σ or range in the input's own base unit — plus the shared
  sources in the order stated and the additions entry;
- choosing another kind or unit carries the numbers over (σ = s ↔ range −s..+s, percent
  ↔ the input's unit through its entered value), a range becomes the σ of half its width,
  and the number used is the number shown;
- a conversion that needs an entered value above 0 waits for one, and blocks the fit
  meanwhile;
- a statement no fit could use is a problem naming its input or source, every one at once;
- each assay's statements come back on switching back to it, and never reach another;
- an assay that fits no association constant states nothing, and says why.
"""

from __future__ import annotations

import pytest

from core.assays.registry import AssayType
from core.pipeline.inputs import TITRANT, AdditionError, ErrorModel, InputSpec, SharedSource, SpecKind
from core.units import Q_
from gui.uncertainty import HELP_HTML, UncertaintyForm

_KA_DYE = 16.8e6  # M⁻¹, the Ka,dye set in the conditions form
_H0 = 4.3e-6  # M
_UNITS = {'Ka_dye': 'M⁻¹', 'h0': 'µM', 'd0': 'µM'}


def _conditions(h0: float = _H0) -> dict:
    return {'Ka_dye': Q_(_KA_DYE, '1/M'), 'h0': Q_(h0, 'M'), 'd0': Q_(6e-6, 'M')}


def _ida() -> UncertaintyForm:
    form = UncertaintyForm()
    form.set_assay(AssayType.IDA)
    form.set_conditions(_conditions(), _UNITS)
    return form


def _assert_spec(actual: InputSpec | None, expected: InputSpec) -> None:
    assert actual is not None
    assert (actual.kind, actual.relative) == (expected.kind, expected.relative)
    assert (actual.sigma, actual.lo, actual.hi) == pytest.approx((expected.sigma, expected.lo, expected.hi), rel=1e-12)


def _source(form: UncertaintyForm, name: str, sigma: str, keys) -> int:
    """Add a shared source and fill it in, as a user does; return its index."""
    form.add_source()
    index = len(form.sources) - 1
    form.rename_source(index, name)
    form.set_source_sigma(index, sigma)
    for key in keys:
        form.tick(index, key, True)
    return index


def test_every_input_starts_fixed_so_a_fit_takes_the_entered_inputs_as_exact():
    """Nothing is assumed about the inputs until the user says something: no source, no problem."""
    form = _ida()

    assert [entry.kind for entry in form.entries()] == [None] * 4
    assert form.errors() == ErrorModel()
    assert form.problems() == []
    assert form.sources == [] and form.additions_entry.mode == 0
    assert form.varying() == 0

    # The kind a user then picks starts from a usable number rather than an empty box.
    form.choose_kind('h0', SpecKind.SIGMA)
    assert form.errors() == ErrorModel(specs={'h0': InputSpec.sigma_pct(5.0)})
    assert form.entry('h0').texts == ('5.0',)


def test_errors_leave_fixed_inputs_out_and_hand_on_what_each_input_states():
    """A percentage stays a percentage and an amount in the input's unit is handed on in its base unit."""
    form = _ida()
    form.set_spec('h0', InputSpec.sigma_pct(3.0))
    form.set_spec('Ka_dye', InputSpec.sigma_abs(0.84e6))
    form.set_spec('d0', InputSpec.interval_abs(5.7e-6, 6.2e-6))

    specs = form.errors().specs

    assert set(specs) == {'h0', 'Ka_dye', 'd0'}
    assert specs['h0'] == InputSpec.sigma_pct(3.0)
    _assert_spec(specs['Ka_dye'], InputSpec.sigma_abs(0.84e6))
    # Shown in µM, handed on in M.
    assert form.entry('d0').texts == ('5.7', '6.2')
    _assert_spec(specs['d0'], InputSpec.interval_abs(5.7e-6, 6.2e-6))


@pytest.mark.parametrize(
    ('start', 'kind', 'relative', 'expected'),
    [
        # σ = 5 % of Ka,dye = 16.8e6 M⁻¹, stated four ways.
        (InputSpec.sigma_pct(5.0), SpecKind.INTERVAL, True, InputSpec.interval_pct(-5.0, 5.0)),
        (InputSpec.sigma_pct(5.0), SpecKind.SIGMA, False, InputSpec.sigma_abs(0.84e6)),
        (InputSpec.sigma_abs(0.84e6), SpecKind.SIGMA, True, InputSpec.sigma_pct(5.0)),
        (InputSpec.interval_abs(15.96e6, 17.64e6), SpecKind.INTERVAL, True, InputSpec.interval_pct(-5.0, 5.0)),
        # A lopsided range keeps its ends in the other unit; as a σ it keeps half its width.
        (InputSpec.interval_pct(-6.0, 4.0), SpecKind.INTERVAL, False, InputSpec.interval_abs(15.792e6, 17.472e6)),
        (InputSpec.interval_pct(-6.0, 4.0), SpecKind.SIGMA, True, InputSpec.sigma_pct(5.0)),
        (InputSpec.interval_abs(15.792e6, 17.472e6), SpecKind.SIGMA, False, InputSpec.sigma_abs(0.84e6)),
    ],
)
def test_choosing_another_kind_or_unit_carries_the_numbers_over(start, kind, relative, expected):
    form = _ida()
    form.set_spec('Ka_dye', start)

    form.choose_kind('Ka_dye', kind)
    form.state_in('Ka_dye', relative)

    _assert_spec(form.spec('Ka_dye'), expected)


def test_the_number_used_is_the_number_shown():
    """A conversion is written to five figures, and the uncertainty used is read back from what is written."""
    form = _ida()
    form.set_spec('h0', InputSpec.sigma_abs(2e-9))  # 0.002 µM

    form.state_in('h0', True)

    assert form.entry('h0').texts == ('0.046512',)  # 2e-9 / 4.3e-6, to five figures
    assert form.spec('h0') == InputSpec.sigma_pct(0.046512)


def test_the_titrant_is_stated_in_percent_only():
    form = _ida()
    form.choose_kind(TITRANT, SpecKind.SIGMA)

    form.state_in(TITRANT, False)

    assert form.entry(TITRANT).relative
    assert form.spec(TITRANT) == InputSpec.sigma_pct(5.0)


def test_a_conversion_needing_an_entered_value_waits_for_one_and_blocks_the_fit_meanwhile():
    form = _ida()
    form.set_conditions(_conditions(h0=0.0), _UNITS)
    form.choose_kind('h0', SpecKind.INTERVAL)

    form.state_in('h0', False)

    # The sentence names the conversion asked for: a range, in µM.
    message = '[Host]₀ is 0 in the conditions, so its uncertainty cannot be converted to a range in µM: set [Host]₀ above 0 first.'
    assert form.problems() == [message]
    assert form.spec('h0') is None

    form.set_conditions(_conditions(), _UNITS)
    _assert_spec(form.spec('h0'), InputSpec.interval_abs(0.95 * _H0, 1.05 * _H0))
    assert form.problems() == []

    # An amount in the input's unit cannot be read against an entered value of 0 either.
    form.set_conditions(_conditions(h0=0.0), _UNITS)
    assert form.problems() == [
        '[Host]₀ is 0 in the conditions, so an uncertainty in its unit cannot be used: set [Host]₀ above 0 first.'
    ]


def test_percent_to_unit_uses_the_value_entered_in_the_conditions():
    """σ = 5 % of [Host]₀ = 10 µM is 0.5 µM, not 5 % of the form's default."""
    form = _ida()
    form.set_conditions(_conditions(h0=10e-6), _UNITS)
    form.choose_kind('h0', SpecKind.SIGMA)

    form.state_in('h0', False)
    _assert_spec(form.spec('h0'), InputSpec.sigma_abs(0.5e-6))
    form.choose_kind('h0', SpecKind.INTERVAL)
    _assert_spec(form.spec('h0'), InputSpec.interval_abs(9.5e-6, 10.5e-6))


def test_an_amount_in_a_unit_is_written_again_when_the_condition_changes_unit():
    """The amount stays the same quantity: 0.2 µM reads 200 nM once [Host]₀ is shown in nM."""
    form = _ida()
    form.set_spec('h0', InputSpec.sigma_abs(0.2e-6))
    assert form.entry('h0').texts == ('0.2',)

    form.set_conditions(_conditions(), {**_UNITS, 'h0': 'nM'})

    assert form.entry('h0').texts == ('200',)
    _assert_spec(form.spec('h0'), InputSpec.sigma_abs(0.2e-6))


def test_a_conversion_waiting_for_an_entered_value_names_the_kind_and_unit_asked_for():
    """Asked for a σ in %, the sentence says %; asked for a range in µM, it says a range."""
    form = _ida()
    form.set_spec('Ka_dye', InputSpec.sigma_abs(1650.0))
    form.set_conditions({**_conditions(), 'Ka_dye': Q_(0.0, '1/M')}, _UNITS)

    form.state_in('Ka_dye', True)
    assert form.problems() == [
        'Ka,dye is 0 in the conditions, so its uncertainty cannot be converted to a σ in %: set Ka,dye above 0 first.'
    ]

    form = _ida()
    form.set_spec('h0', InputSpec.sigma_abs(0.2e-6))
    form.set_conditions(_conditions(h0=0.0), _UNITS)
    form.choose_kind('h0', SpecKind.INTERVAL)
    assert form.problems() == [
        '[Host]₀ is 0 in the conditions, so its uncertainty cannot be converted to a range in µM: '
        'set [Host]₀ above 0 first.'
    ]


def test_an_amount_that_cannot_be_read_is_never_replaced_by_a_switch():
    """A switch to another kind or unit is refused while the amount shown is not a number, and the row says why.

    No default and no older number takes the typed text's place, so nothing the user did
    not state reaches a fit; *Fixed* is the way out, and the text comes back with its kind.
    """
    form = _ida()
    form.choose_kind('h0', SpecKind.SIGMA)
    form.edit('h0', 0, '12')
    form.edit('h0', 0, '12,5')

    form.choose_kind('h0', SpecKind.INTERVAL)
    entry = form.entry('h0')
    assert (entry.kind, entry.relative, entry.texts) == (SpecKind.SIGMA, True, ('12,5',))
    assert form.errors().specs == {}
    assert form.problems() == [
        '[Host]₀: “12,5” is not a number, so it cannot be carried over to a range. Enter a number, or choose “Fixed”.'
    ]

    form.state_in('h0', False)
    assert (entry.kind, entry.relative, entry.texts) == (SpecKind.SIGMA, True, ('12,5',))
    assert form.problems() == [
        '[Host]₀: “12,5” is not a number, so it cannot be carried over to µM. Enter a number, or choose “Fixed”.'
    ]

    form.choose_kind('h0', None)
    assert form.problems() == [] and form.errors().specs == {}
    form.choose_kind('h0', SpecKind.SIGMA)
    assert entry.texts == ('12,5',) and form.errors().specs == {}
    assert form.problems() == ['[Host]₀: “12,5” is not a number. Enter a number, or choose “Fixed”.']

    form.edit('h0', 0, '12.5')
    form.choose_kind('h0', SpecKind.INTERVAL)
    _assert_spec(form.spec('h0'), InputSpec.interval_pct(-12.5, 12.5))


def test_a_condition_shown_in_another_unit_leaves_the_stated_uncertainty_exactly_as_it_was():
    """Only the text is written again: the model a fit was made with still matches, digit for digit."""
    form = _ida()
    form.choose_kind('h0', SpecKind.SIGMA)
    form.state_in('h0', False)
    form.edit('h0', 0, '0.215')
    before = form.errors()

    form.set_conditions(_conditions(), {**_UNITS, 'h0': 'nM'})
    assert form.entry('h0').texts == ('215',)
    assert form.errors() == before

    # Every figure typed survives a round trip through other units.
    form.edit('h0', 0, '123.456')  # nM
    before = form.errors()
    form.set_conditions(_conditions(), _UNITS)
    assert form.entry('h0').texts == ('0.123456',)
    form.set_conditions(_conditions(), {**_UNITS, 'h0': 'M'})
    assert form.entry('h0').texts == ('1.23456e−7',)
    form.set_conditions(_conditions(), {**_UNITS, 'h0': 'nM'})
    assert form.entry('h0').texts == ('123.456',)
    assert form.errors() == before


def test_an_input_that_cannot_vary_is_not_counted_as_varying():
    """σ = 0 is named as a problem, so the summary beside the title does not count it."""
    form = _ida()
    form.set_spec('h0', InputSpec.sigma_pct(0.0))
    form.set_spec('d0', InputSpec.interval_pct(2.0, 2.0))
    assert form.varying() == 0

    form.set_spec('d0', InputSpec.sigma_pct(3.0))
    _source(form, 'Pipette', '0', ('h0', 'Ka_dye'))
    assert form.varying() == 1


def test_fixed_carries_the_last_uncertainty_into_the_next_kind():
    form = _ida()
    form.set_spec('Ka_dye', InputSpec.interval_pct(-6.0, 4.0))

    form.choose_kind('Ka_dye', None)
    assert form.spec('Ka_dye') is None and form.errors().specs == {}
    form.choose_kind('Ka_dye', SpecKind.INTERVAL)

    _assert_spec(form.spec('Ka_dye'), InputSpec.interval_pct(-6.0, 4.0))


def test_a_range_typed_as_minus_6_to_plus_4_percent_is_exactly_that_interval():
    form = _ida()
    form.choose_kind('Ka_dye', SpecKind.INTERVAL)
    form.edit('Ka_dye', 0, '−6')
    form.edit('Ka_dye', 1, '4')

    assert form.errors().specs['Ka_dye'] == InputSpec(SpecKind.INTERVAL, lo=-6.0, hi=4.0)


@pytest.mark.parametrize(
    ('spec', 'instruction'),
    [
        (InputSpec.interval_pct(5.0, 0.0), 'set “to” above “from”'),
        (InputSpec.interval_abs(16.8e6, 16.8e6), 'set “to” above “from”'),
        (InputSpec.sigma_abs(0.0), 'set σ above 0'),
    ],
)
def test_an_input_that_cannot_vary_is_named_as_a_problem(spec, instruction):
    form = _ida()
    form.set_spec('Ka_dye', spec)

    assert form.problems() == [f'Ka,dye cannot vary: {instruction}, or choose “Fixed”.']


def test_a_range_that_reaches_zero_is_named_as_a_problem():
    """A range end at −100 % would ask the model to fit with no host at all; a σ is a penalty above zero and may stay."""
    form = _ida()

    form.set_spec('h0', InputSpec.interval_pct(-100.0, 5.0))
    assert form.problems() == ['[Host]₀ would be taken down to zero: set “from” above −100 %.']

    form.set_spec('h0', InputSpec.interval_abs(0.0, 5e-6))
    assert form.problems() == ['[Host]₀ would be taken down to zero: set “from” above 0.']

    form.set_spec('h0', InputSpec.sigma_pct(80.0))
    assert form.problems() == []


@pytest.mark.parametrize(
    ('text', 'problem'),
    [
        ('2e', 'Ka,dye: “2e” is not a number. Enter a number, or choose “Fixed”.'),
        ('', 'Ka,dye has no amount: enter a number, or choose “Fixed”.'),
    ],
)
def test_an_amount_that_is_not_a_number_is_named_as_a_problem(text, problem):
    form = _ida()
    form.choose_kind('Ka_dye', SpecKind.SIGMA)

    form.edit('Ka_dye', 0, text)

    assert form.problems() == [problem]
    assert form.spec('Ka_dye') is None


def test_the_inputs_are_the_assays_perturbable_inputs_named_as_every_report_names_them():
    form = UncertaintyForm()

    form.set_assay(AssayType.IDA)
    assert form.input_labels() == {
        'Ka_dye': 'Ka,dye',
        'h0': '[Host]₀',
        'd0': '[Dye]₀',
        TITRANT: 'Guest (titrant, whole series)',
    }
    form.set_assay(AssayType.GDA)
    assert set(form.keys) == {TITRANT, 'Ka_dye', 'h0', 'g0'}
    # A single-condition assay: just the titrant and its one fixed concentration.
    form.set_assay(AssayType.DBA_HtoD)
    assert set(form.keys) == {TITRANT, 'fixed_conc'}


def test_each_assays_statements_come_back_on_switching_back_and_reach_no_other_assay():
    """IDA's entries, sources and additions come back as left; GDA starts from its own empty statement.

    So does DBA host-to-dye, whose fixed_conc is the host where dye-to-host's is the dye.
    """
    form = _ida()
    form.set_spec('Ka_dye', InputSpec.interval_abs(15.96e6, 17.64e6))
    form.set_spec('d0', InputSpec.sigma_pct(3.0))
    form.choose_kind('d0', None)
    _source(form, 'Host and dye stock', '4', ('h0', 'd0'))
    form.set_additions_mode(2)
    form.set_additions_sigma('1.5')
    form.set_separate_titrations(False)

    form.set_assay(AssayType.GDA)
    assert form.errors() == ErrorModel()
    assert form.additions_entry.mode == 0 and form.additions_entry.separate
    form.set_assay(AssayType.IDA)
    form.set_conditions(_conditions(), _UNITS)

    errors = form.errors()
    _assert_spec(errors.specs['Ka_dye'], InputSpec.interval_abs(15.96e6, 17.64e6))
    assert 'd0' not in errors.specs
    assert errors.shared == (SharedSource('Host and dye stock', 4.0, ('h0', 'd0')),)
    assert errors.additions == AdditionError(1.5, sequential=False, separate_titrations=False)
    form.choose_kind('d0', SpecKind.SIGMA)
    _assert_spec(form.spec('d0'), InputSpec.sigma_pct(3.0))

    form.set_assay(AssayType.DBA_DtoH)
    form.set_spec('fixed_conc', InputSpec.sigma_pct(2.0))
    form.set_assay(AssayType.DBA_HtoD)
    assert form.spec('fixed_conc') is None


def test_the_form_states_the_whole_error_model():
    """Each input's own uncertainty, what two of them share, and the error of each addition."""
    form = _ida()
    form.set_spec('h0', InputSpec.sigma_pct(3.0))
    form.set_spec(TITRANT, InputSpec.interval_pct(-2.0, 2.0))
    _source(form, 'Host and dye stock', '4.0', ('d0', 'h0'))
    form.set_additions_mode(1)
    form.set_additions_sigma('1.5')

    errors = form.errors()

    assert errors.specs == {'h0': InputSpec.sigma_pct(3.0), TITRANT: InputSpec.interval_pct(-2.0, 2.0)}
    # The inputs of a source are listed as the form lists them, whatever order they were ticked in.
    assert errors.shared == (SharedSource('Host and dye stock', 4.0, ('h0', 'd0')),)
    assert errors.additions == AdditionError(1.5, sequential=True, separate_titrations=True)
    assert form.problems() == []
    assert form.varying() == 3

    # A second source is reported after the first, in the order stated.
    _source(form, 'Guest pipette', '2', ('d0', TITRANT))
    assert [source.name for source in form.errors().shared] == ['Host and dye stock', 'Guest pipette']
    # Separately prepared samples carry no error from one point to the next.
    form.set_additions_mode(2)
    assert form.errors().additions == AdditionError(1.5, sequential=False)
    # 'None' is the absence of a statement, not an error of zero.
    form.set_additions_mode(0)
    assert form.errors().additions is None
    # Removing a source takes it out of the model.
    form.remove_source(0)
    assert [source.name for source in form.errors().shared] == ['Guest pipette']


def test_a_new_source_is_named_apart_from_the_others_and_states_an_uncertainty_to_edit():
    form = _ida()
    form.add_source()
    form.add_source()

    assert [source.name for source in form.sources] == ['Shared source 1', 'Shared source 2']
    assert all(source.sigma_text == '5.0' for source in form.sources)


@pytest.mark.parametrize(
    ('spoil', 'problem'),
    [
        (
            lambda form: form.rename_source(0, '  '),
            'A shared error source has no name. Give it a name, or remove it.',
        ),
        (
            lambda form: form.set_source_sigma(0, '0'),
            "The uncertainty of the shared error source 'Host and dye stock' has to be above zero. "
            'Enter it in percent, or remove the source.',
        ),
        (
            lambda form: form.set_source_sigma(0, 'x'),
            "The uncertainty of the shared error source 'Host and dye stock': “x” is not a number. "
            'Enter it in percent, or remove the source.',
        ),
        (
            lambda form: form.tick(0, 'd0', False),
            'A shared error source has to apply to at least two inputs. '
            "'Host and dye stock' applies to one: tick a second input, or remove it and enter the "
            'uncertainty on the input itself.',
        ),
    ],
)
def test_a_shared_source_that_states_no_error_a_titration_can_have_is_refused_naming_it(spoil, problem):
    """The form refuses what the fit would refuse, in the same words, before a run starts."""
    form = _ida()
    _source(form, 'Host and dye stock', '4.0', ('h0', 'd0'))
    assert form.problems() == []

    spoil(form)

    assert form.problems() == [problem]


def test_each_source_is_told_its_own_fault_and_every_fault_is_named_at_once():
    """The source a problem belongs to is the one it is listed under, the duplicated name included."""
    form = _ida()
    _source(form, 'Host and dye stock', '4.0', ('h0', 'd0'))
    _source(form, 'Host and dye stock', '2.0', ('h0', TITRANT))
    _source(form, 'Titrant stock', '0', ('h0', TITRANT))
    form.tick(2, 'h0', False)
    form.set_additions_mode(2)
    form.set_additions_sigma('0')

    assert form.source_problems() == [
        [],
        ["Two shared error sources are named 'Host and dye stock'. Give each its own name."],
        [
            "The uncertainty of the shared error source 'Titrant stock' has to be above zero. "
            'Enter it in percent, or remove the source.',
            "A shared error source has to apply to at least two inputs. 'Titrant stock' applies to one: tick a "
            'second input, or remove it and enter the uncertainty on the input itself.',
        ],
    ]
    assert form.problems() == [
        *(problem for own in form.source_problems() for problem in own),
        "The random error of each addition has to be above zero. Enter it in percent, or set it to 'none'.",
    ]
    form.set_additions_sigma('1')
    assert form.additions_problem() is None


def test_set_specs_states_those_uncertainties_and_nothing_else():
    """What Demo IDA states: the uncertainties it names, every other input exact, no source beside them."""
    form = _ida()
    form.choose_kind('d0', SpecKind.INTERVAL)
    _source(form, 'Host and dye stock', '4.0', ('h0', 'd0'))
    form.set_additions_mode(1)
    specs = {'Ka_dye': InputSpec.sigma_pct(10.0), 'h0': InputSpec.sigma_pct(3.0)}

    form.set_specs(specs)

    assert form.errors() == ErrorModel(specs=specs)
    assert form.entry('Ka_dye').texts == ('10.0',)
    with pytest.raises(KeyError):
        form.set_specs({'g0': InputSpec.sigma_pct(1.0)})


def test_an_assay_with_no_association_constant_states_nothing_and_says_why():
    """An uncertainty only widens an interval of a Ka, so an assay that fits none is closed with a reason."""
    from core.pipeline.varpro import projectable

    assert [assay_type for assay_type in AssayType if not projectable(assay_type)] == [AssayType.DYE_ALONE]
    form = UncertaintyForm()

    form.set_assay(AssayType.DYE_ALONE)
    assert not form.available
    assert form.unavailable_reason() == (
        'Dye Alone has no association constant, so an uncertainty in the inputs changes nothing here.'
    )
    assert form.errors() == ErrorModel() and form.problems() == []
    for assay_type in (AssayType.IDA, AssayType.DBA_HG2, AssayType.DBA_H2G):
        form.set_assay(assay_type)
        assert form.available


def test_the_help_says_the_numbers_carry_over_and_the_spread_changes():
    """σ = 5 % and the range −5 % to +5 % are different spreads, so the help never calls the switch the same uncertainty."""
    text = ' '.join(HELP_HTML.split())
    assert 'keeps the uncertainty' not in text and 'uncertainty over' not in text
    assert 'carries the numbers over' in text
    assert 'an even draw between −5 % and +5 % varies less than a σ of 5 %' in text


def test_the_help_tells_an_input_own_error_from_a_shared_one_and_says_what_each_feeds():
    """Three statements, three readers: an own entry, a shared source, and the error of each addition."""
    text = ' '.join(HELP_HTML.split())
    assert 'the error <b>only that input</b> has' in text
    assert 'come from one stock, were weighed on one balance or pipetted with one pipette' in text
    assert 'Both the interval of every fit and the K<sub>a</sub> Sensitivity analysis use exactly this model' in text
    assert 'by the same percentage the other way' in text
    # With a noise law of the replicates the interval allowing for the additions can come out
    # no wider than the one at the law alone, so no promise to widen is made.
    assert 'allows for that factor in the interval of K<sub>a</sub>' in text
    assert 'about as wide as, or slightly narrower than, the one without the additions' in text
    assert 'widens the interval of K<sub>a</sub>' not in text
    assert 'allow for the same error' in text
    assert 'their average carries σ/√<i>m</i> of them for <i>m</i>' in text
    assert '<i>Repeated reads of one titration</i> share them, and their average carries σ itself' in text
    assert 'A σ larger than the real one gives a wider interval than needed' in text


def test_the_help_says_what_the_uncertainties_feed_and_what_each_kind_means_for_the_fit():
    """Both readers are named, and the interval is promised as usually wider, never as a diagnosis."""
    text = ' '.join(HELP_HTML.split())
    assert 'The interval of every fit.' in text
    assert 'with every draw counted the same, whereas the interval also weighs what the data say' in text
    assert 'splits' not in text
    # A σ is a penalty the fit pays, a range is a box, fixed is exact.
    assert 'moving it by <i>e</i> costs (<i>e</i>/σ)<sup>2</sup>' in text
    assert 'every value between them is equally acceptable and none outside' in text
    assert 'the input is taken as exact' in text
    # The intervals are named by the glossary terms the view's side panel and every report show.
    assert 'With every input fixed, as the view opens, the fit reports one interval, <b>Inputs as entered</b>' in text
    assert '<b>Input-aware</b>' in text
    assert 'conditional on the entered inputs' not in text
    assert 'Stating uncertainties usually widens the interval.' in text
    assert 'always widens' not in text


def test_a_nan_amount_is_not_a_number():
    form = _ida()
    form.choose_kind('Ka_dye', SpecKind.SIGMA)
    form.edit('Ka_dye', 0, 'nan')

    assert form.spec('Ka_dye') is None
    assert form.problems() == ['Ka,dye: “nan” is not a number. Enter a number, or choose “Fixed”.']
