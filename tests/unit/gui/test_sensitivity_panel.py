"""The Input uncertainty rows of the Ka Sensitivity panel.

Pins what reaches the analysis from what the user sets:

- choosing another kind carries the numbers over (σ = s ↔ range −s..+s, percent ↔
  the input's unit through its set value in the conditions form), and a range becomes
  the σ of half its width; the help does not call that the same uncertainty;
- a number the new kind's boxes cannot hold is named under the input; a conversion that
  needs a set value above 0 waits for one, with a warning that blocks the run;
- a range entered as −6 % .. +4 % is exactly that interval;
- an input set so it cannot vary (σ = 0, "to" not above "from") shows a warning naming
  it and blocks the run with a message naming it; only *fixed* leaves an input out;
- a range that would draw an input down to zero blocks the run, naming it;
- a heatmap checks only its two axes: two different inputs, neither fixed, neither
  reaching zero over its sweep;
- an assay that fits no association constant is closed with one sentence saying why,
  while every assay the engine can project — one binding constant or two — is open;
- the help says what one sample is: an exact fit of one averaged signal;
- every input the analysis varies is named as the panel shows it;
- each assay's entries, kinds and units come back on switching back to it, and never
  reach another assay;
- every control locks while a run is live;
- the panel is as wide whichever kind each input shows.

Require a ``QApplication`` (the ``qapp`` fixture).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip('PyQt6')

from core.assays.registry import AssayType  # noqa: E402
from core.pipeline.sensitivity import TITRANT, InputSpec, SpecKind  # noqa: E402
from core.units import Q_  # noqa: E402

_IDA_DATA = Path(__file__).resolve().parents[3] / 'data' / 'IDA_system.txt'
_KA_DYE = 16.8e6  # M⁻¹, the Ka,dye set in the conditions form
_H0 = 4.3e-6  # M


def _ida_panel():
    from gui.widgets.sensitivity_panel import SensitivityPanel

    panel = SensitivityPanel()
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
    from gui.widgets.sensitivity_panel import _UNCERTAINTY_HELP_HTML

    text = ' '.join(_UNCERTAINTY_HELP_HTML.split())
    assert 'keeps the uncertainty' not in text and 'uncertainty over' not in text
    assert 'carries the numbers over' in text
    assert 'an even draw between −5 % and +5 % varies less than a σ of 5 %' in text


def test_the_help_says_what_one_sample_is():
    """Every sample is one exact fit of one signal, so the help promises no spread from the fitting itself."""
    from gui.widgets import sensitivity_panel

    text = ' '.join(sensitivity_panel._SECTION_HELP_HTML.split())
    assert 'one exact fit of the averaged signal of the replicates your fit used' in text
    assert 'the same inputs always give the same K<sub>a</sub>' in text
    # The replicates each sample uses follow the fit; the panel offers no choice of its own.
    helps = [value for name, value in vars(sensitivity_panel).items() if name.endswith('_HELP_HTML')]
    assert not any('Per replicate' in help_text or 'Average replicates' in help_text for help_text in helps)


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


def test_a_conversion_needing_a_set_value_waits_for_one_and_blocks_the_run_meanwhile(qapp):
    panel = _ida_panel()
    row = panel._rows['h0']
    row.set_nominal(0.0)
    _choose(row, 'range')

    message = (
        '[Host]₀ is 0 in the conditions, so its uncertainty cannot be converted to “range”: set [Host]₀ above 0 first.'
    )
    assert row._warning.text() == message
    assert panel.run_problems() == [message]
    with pytest.raises(ValueError, match='is 0 in the conditions'):
        panel.current_config()

    row.set_nominal(_H0)
    _assert_spec(row.spec(), InputSpec.interval_abs(0.95 * _H0, 1.05 * _H0))
    assert row._warning.isHidden() and panel.run_problems() == []

    # A value in the input's unit cannot be read against a set value of 0 either.
    row.set_nominal(0.0)
    assert panel.run_problems() == [
        '[Host]₀ is 0 in the conditions, so an uncertainty in its unit cannot be used: set [Host]₀ above 0 first.'
    ]


def test_percent_to_unit_uses_the_value_set_in_the_conditions_form(qapp):
    """σ = 5 % of [Host]₀ = 10 µM is 0.5 µM, not 5 % of the form's default."""
    from gui.fitting_session import FittingSession

    session = FittingSession()
    session._assay_panel.set_assay_type(AssayType.IDA)
    session._assay_panel._field_widgets['h0']._spinbox.setValue(10.0)  # µM
    row = session._sensitivity_panel._rows['h0']

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
    assert panel.current_config().input_specs['Ka_dye'] == InputSpec(SpecKind.INTERVAL, lo=-6.0, hi=4.0)


@pytest.mark.parametrize(
    ('spec', 'instruction'),
    [
        (InputSpec.interval_pct(5.0, 0.0), 'set “to” above “from”'),
        (InputSpec.interval_abs(16.8e6, 16.8e6), 'set “to” above “from”'),
        (InputSpec.sigma_abs(0.0), 'set σ above 0'),
    ],
)
def test_an_input_that_cannot_vary_warns_and_blocks_the_run_naming_it(qapp, monkeypatch, spec, instruction):
    from gui import workers
    from gui.fitting_session import FittingSession

    warnings = []
    monkeypatch.setattr('gui.fitting_session.QMessageBox.warning', lambda *args: warnings.append(args))
    monkeypatch.setattr(workers, 'run_sensitivity', lambda *a, **k: pytest.fail('the analysis must not start'))
    session = FittingSession()
    session._assay_panel.set_assay_type(AssayType.IDA)
    session._data_panel.load_file(str(_IDA_DATA))
    row = session._sensitivity_panel._rows['Ka_dye']

    row.set_spec(spec)

    assert not row._warning.isHidden()
    assert row._warning.text() == f'Ka,dye cannot vary: {instruction}, or choose “fixed”.'
    session.run_sensitivity()
    assert session._sensitivity_worker is None
    (message,) = [args[2] for args in warnings]
    assert f'Ka,dye cannot vary: {instruction}' in message
    with pytest.raises(ValueError, match='Ka,dye cannot vary'):
        session._sensitivity_panel.current_config()


def test_only_fixed_leaves_an_input_out_and_a_heatmap_axis_cannot_be_fixed(qapp):
    panel = _ida_panel()
    for key, row in panel._rows.items():
        row.set_spec(InputSpec.sigma_pct(7.0) if key == TITRANT else None)

    assert all(row._warning.isHidden() for row in panel._rows.values())
    assert panel.current_config().input_specs == {TITRANT: InputSpec.sigma_pct(7.0)}

    panel._mode_combo.setCurrentIndex(panel._mode_combo.findText('Heatmap'))
    panel._x_combo.setCurrentIndex(panel._x_combo.findData(TITRANT))
    panel._y_combo.setCurrentIndex(panel._y_combo.findData('h0'))
    assert panel.run_problems() == ['[Host]₀ is a heatmap axis, so it cannot be fixed: choose a σ or a range.']


def _heatmap(panel, x_key: str, y_key: str) -> None:
    panel._mode_combo.setCurrentIndex(panel._mode_combo.findText('Heatmap'))
    panel._x_combo.setCurrentIndex(panel._x_combo.findData(x_key))
    panel._y_combo.setCurrentIndex(panel._y_combo.findData(y_key))


def test_a_heatmap_checks_only_its_axes_and_takes_only_their_uncertainties(qapp):
    """Every other input keeps its set value in a heatmap, so its entry neither blocks the run nor reaches it."""
    panel = _ida_panel()
    panel._rows['d0'].set_spec(InputSpec.sigma_pct(0.0))
    _heatmap(panel, 'Ka_dye', 'h0')

    assert panel.run_problems() == []
    config = panel.current_config()
    assert config.input_specs == {'Ka_dye': InputSpec.sigma_pct(5.0), 'h0': InputSpec.sigma_pct(5.0)}
    assert (config.x_key, config.y_key) == ('Ka_dye', 'h0')

    _heatmap(panel, 'Ka_dye', 'Ka_dye')
    assert panel.run_problems() == ['Ka,dye is both heatmap axes: choose another input for one of them.']


@pytest.mark.parametrize(
    ('spec', 'problem', 'inside'),
    [
        (InputSpec.sigma_pct(50.0), 'set σ below 50 %, or use a range.', InputSpec.sigma_pct(49.9)),
        (
            InputSpec.sigma_abs(0.5 * _H0),
            'set σ below half its set value, or use a range.',
            InputSpec.sigma_abs(0.499 * _H0),
        ),
        (InputSpec.interval_pct(-100.0, 10.0), 'set “from” above −100 %.', InputSpec.interval_pct(-99.9, 10.0)),
        (InputSpec.interval_abs(0.0, 5e-6), 'set “from” above 0.', InputSpec.interval_abs(0.01e-6, 5e-6)),
    ],
)
def test_a_heatmap_axis_reaching_zero_blocks_the_run_naming_it(qapp, spec, problem, inside):
    """A σ axis runs from −2σ to +2σ and a range axis over the whole range, so an end at zero cannot be fitted."""
    panel = _ida_panel()
    _heatmap(panel, 'h0', 'd0')
    panel._rows['h0'].set_spec(spec)

    (message,) = panel.run_problems()
    assert message.startswith('[Host]₀ as a heatmap axis would reach zero') and message.endswith(problem)

    panel._rows['h0'].set_spec(inside)
    assert panel.run_problems() == []


def test_each_assays_entries_come_back_on_switching_back_and_reach_no_other_assay(qapp):
    """IDA's absolute Ka,dye range, its [Host]₀ σ in nM and a fixed [Dye]₀ that was σ 3 % all come back as left.

    GDA, whose Ka,dye and [Host]₀ are other set values, starts from its own defaults; so does
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
    assert all(row.spec() == InputSpec.sigma_pct(5.0) for row in panel._rows.values())
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
    assert panel._rows['fixed_conc'].spec() == InputSpec.sigma_pct(5.0)


def test_an_assay_with_no_association_constant_is_unavailable_and_says_why(qapp):
    """The analysis reports association constants, so an assay that fits none is closed with a reason."""
    from core.pipeline.varpro import projectable
    from gui.widgets.sensitivity_panel import SensitivityPanel

    closed = [assay_type for assay_type in AssayType if not projectable(assay_type)]
    assert closed == [AssayType.DYE_ALONE]
    panel = SensitivityPanel()

    panel.set_assay_type(AssayType.DYE_ALONE)
    assert not panel.isEnabled()
    assert not panel._unavailable.isHidden()
    assert panel._unavailable.text() == 'Dye Alone has no association constant, so there is nothing to analyse here.'

    # Every assay whose signal the engine can project is open, the two-constant ones included.
    for assay_type in (AssayType.IDA, AssayType.DBA_HG2, AssayType.DBA_H2G):
        panel.set_assay_type(assay_type)
        assert panel.isEnabled()
        assert panel._unavailable.isHidden()


def test_input_labels_name_every_input_the_analysis_varies_as_the_panel_shows_it(qapp):
    """The analysis reports a problem by name, so its names are the panel's, the titrant included."""
    panel = _ida_panel()

    labels = panel.input_labels()

    assert set(labels) == set(panel._rows)
    assert labels == {
        TITRANT: 'Guest (titrant, whole series)',
        'h0': '[Host]₀',
        'd0': '[Dye]₀',
        'Ka_dye': 'Ka,dye',
    }


def test_a_range_that_reaches_zero_blocks_the_run_naming_the_input(qapp):
    """A range end at −100 % would fit the model with no host at all; a σ is truncated above zero and may stay."""
    panel = _ida_panel()
    row = panel._rows['h0']

    row.set_spec(InputSpec.interval_pct(-100.0, 5.0))
    assert panel.run_problems() == ['[Host]₀ would be drawn down to zero: set “from” above −100 %.']
    assert not row._warning.isHidden()

    row.set_spec(InputSpec.interval_abs(0.0, 5e-6))
    assert panel.run_problems() == ['[Host]₀ would be drawn down to zero: set “from” above 0.']

    row.set_spec(InputSpec.sigma_pct(80.0))
    assert panel.run_problems() == []


def test_every_control_locks_while_a_run_is_live(qapp):
    panel = _ida_panel()
    panel.set_running(True)
    controls = [
        panel._mode_combo,
        panel._samples_combo,
        panel._seed_check,
        panel._x_combo,
        panel._y_combo,
        panel._steps_spin,
        *(row.kind for row in panel._rows.values()),
        *panel._rows.values(),
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
    assert panel.current_config().input_specs['Ka_dye'] == row.spec()


def test_typed_text_that_is_not_a_number_blocks_the_run_naming_the_input(qapp):
    from PyQt6.QtTest import QTest

    panel = _ida_panel()
    row = panel._rows['Ka_dye']
    _choose(row, '± σ')
    (box,) = row._values.currentWidget()._boxes
    box.selectAll()
    QTest.keyClicks(box, '2e')

    assert 'is not a number' in row.problem() and row.name in row.problem()
    with pytest.raises(ValueError, match='is not a number'):
        panel.current_config()


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
