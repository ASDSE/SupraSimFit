"""The Ka Sensitivity panel: the run's own settings, on specs stated elsewhere.

The error model is stated in Input uncertainty (its own test files); this panel
takes it from the caller. Pins:

- the axis combos offer the inputs it was given, named as that panel names them, and
  default to the first two;
- the config it builds carries the passed error model — the whole of it for sensitivity
  indices, the two axis inputs' own uncertainties for a heatmap — and the mode, sample
  size, seed and grid steps shown;
- indices need at least one source that varies, and say so in plain language;
- a heatmap refuses an axis that is fixed, an axis used twice, and an axis whose
  passed spec would sweep the input down to zero, naming the input each time;
- an assay that fits no association constant is closed with one sentence saying why;
- a run that was never told its inputs fails loudly rather than guessing;
- the run's controls lock while a run is live;
- the help says what one sample is, where the uncertainties are set, that the
  analysis propagates them, and when it gives a reason instead of numbers.

Require a ``QApplication`` (the ``qapp`` fixture).
"""

from __future__ import annotations

from dataclasses import replace

import pytest

pytest.importorskip('PyQt6')

from core.assays.registry import AssayType  # noqa: E402
from core.pipeline.inputs import (  # noqa: E402
    TITRANT,
    AdditionError,
    ErrorModel,
    InputSpec,
    SharedSource,
)
from core.pipeline.sensitivity import SensitivityMode  # noqa: E402
from core.units import Q_  # noqa: E402

_KA_DYE = 16.8e6  # M⁻¹, the Ka,dye set in the conditions form
_H0 = 4.3e-6  # M
_D0 = 6e-6  # M

#: The IDA inputs as Input uncertainty names them.
_IDA_LABELS = {
    'Ka_dye': 'Ka,dye',
    'h0': '[Host]₀',
    'd0': '[Dye]₀',
    TITRANT: 'Guest (titrant, whole series)',
}


def _ida_panel():
    from gui.widgets.sensitivity_panel import SensitivityPanel

    panel = SensitivityPanel()
    panel.set_assay_type(AssayType.IDA)
    panel.set_inputs(_IDA_LABELS)
    panel.set_nominal_values({'Ka_dye': Q_(_KA_DYE, '1/M'), 'h0': Q_(_H0, 'M'), 'd0': Q_(_D0, 'M')})
    return panel


def _heatmap(panel, x_key: str, y_key: str) -> None:
    panel._mode_combo.setCurrentIndex(panel._mode_combo.findText('Heatmap'))
    panel._x_combo.setCurrentIndex(panel._x_combo.findData(x_key))
    panel._y_combo.setCurrentIndex(panel._y_combo.findData(y_key))


def test_the_axis_combos_offer_the_inputs_they_were_given_named_as_input_uncertainty_names_them(qapp):
    from gui.widgets.sensitivity_panel import SensitivityPanel

    panel = SensitivityPanel()
    panel.set_inputs(_IDA_LABELS)

    keys = [panel._x_combo.itemData(i) for i in range(panel._x_combo.count())]
    names = [panel._x_combo.itemText(i) for i in range(panel._x_combo.count())]
    assert keys == list(_IDA_LABELS)
    assert names == list(_IDA_LABELS.values())
    # The two axes start on different inputs.
    assert (panel._x_combo.currentData(), panel._y_combo.currentData()) == (keys[0], keys[1])

    # Another assay replaces them rather than adding to them.
    panel.set_inputs({'fixed_conc': '[Host]₀', TITRANT: 'Dye (titrant, whole series)'})
    assert [panel._y_combo.itemData(i) for i in range(panel._y_combo.count())] == ['fixed_conc', TITRANT]


def test_the_config_carries_the_passed_error_model_and_the_settings_shown(qapp):
    panel = _ida_panel()
    specs = {'Ka_dye': InputSpec.sigma_pct(5.0), 'h0': InputSpec.sigma_abs(0.2e-6)}
    errors = ErrorModel(
        specs=specs,
        shared=(SharedSource('Host and dye stock', 4.0, ('Ka_dye', 'h0')),),
        additions=AdditionError(1.5, sequential=True),
    )
    panel._samples_combo.setCurrentIndex(panel._samples_combo.findText('2048'))
    panel._seed_check.setChecked(True)
    panel._seed_spin.setValue(7)

    config = panel.current_config(errors)

    # Sensitivity indices split the spread between every source stated, so all of them go.
    assert config.mode is SensitivityMode.SOBOL
    assert config.errors == errors
    assert (config.n_samples, config.seed) == (2048, 7)

    # A heatmap sweeps two inputs and holds everything else at its set value: only their
    # own uncertainties reach the run, and a source that moves several inputs at once
    # is no axis of a grid.
    _heatmap(panel, 'Ka_dye', 'h0')
    panel._steps_spin.setValue(9)
    config = panel.current_config(replace(errors, specs={**specs, 'd0': InputSpec.sigma_pct(4.0)}))
    assert config.mode is SensitivityMode.HEATMAP
    assert config.errors == ErrorModel(specs=specs)
    assert (config.x_key, config.y_key, config.n_steps) == ('Ka_dye', 'h0', 9)


def test_the_sample_sizes_offered_are_the_ones_the_sobol_design_accepts(qapp):
    """The 8-block design needs a power of two per block, so the panel offers only sizes it can split."""
    from core.pipeline.sensitivity import _SOBOL_SAMPLE_SIZES

    panel = _ida_panel()

    sizes = [panel._samples_combo.itemData(i) for i in range(panel._samples_combo.count())]
    assert sizes == list(_SOBOL_SAMPLE_SIZES)
    assert panel.current_config(ErrorModel(specs={'h0': InputSpec.sigma_pct(5.0)})).n_samples == sizes[0]


def test_indices_need_a_source_that_varies_and_say_so(qapp):
    """With nothing stated there is no spread to split, and the message names where to state it."""
    panel = _ida_panel()

    (problem,) = panel.run_problems(ErrorModel())
    assert problem == (
        'No input varies, so there is no spread to split. Set an uncertainty for at least one input '
        'under Input uncertainty.'
    )
    with pytest.raises(ValueError, match='No input varies'):
        panel.current_config(ErrorModel())

    assert panel.run_problems(ErrorModel(specs={'d0': InputSpec.sigma_pct(5.0)})) == []
    # A source several inputs share moves them all, so it is a spread to split on its own.
    assert panel.run_problems(ErrorModel(shared=(SharedSource('Stock', 4.0, ('h0', 'd0')),))) == []


def test_a_heatmap_axis_that_is_fixed_or_used_twice_blocks_the_run_naming_the_input(qapp):
    panel = _ida_panel()
    _heatmap(panel, TITRANT, 'h0')

    assert panel.run_problems(ErrorModel(specs={TITRANT: InputSpec.sigma_pct(7.0)})) == [
        '[Host]₀ is a heatmap axis, so it cannot be fixed: set a σ or a range for it under Input uncertainty.'
    ]

    _heatmap(panel, 'Ka_dye', 'Ka_dye')
    assert panel.run_problems(ErrorModel(specs={'Ka_dye': InputSpec.sigma_pct(5.0)})) == [
        'Ka,dye is both heatmap axes: choose another input for one of them.'
    ]


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
    """A σ axis runs from −2σ to +2σ and a range axis over the whole range, so an end at zero cannot be fitted.

    An axis stated in the input's own unit is read against the set value the conditions
    form holds, so σ = 2.15 µM on a [Host]₀ of 4.3 µM reaches zero where 2.147 µM does not.
    """
    panel = _ida_panel()
    _heatmap(panel, 'h0', 'd0')
    other = {'d0': InputSpec.sigma_pct(5.0)}

    (message,) = panel.run_problems(ErrorModel(specs={'h0': spec, **other}))
    assert message.startswith('[Host]₀ as a heatmap axis would reach zero') and message.endswith(problem)

    assert panel.run_problems(ErrorModel(specs={'h0': inside, **other})) == []


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


def test_a_panel_never_told_its_inputs_refuses_to_configure_a_run(qapp):
    """The axis names come from Input uncertainty; without them the panel guesses nothing."""
    from gui.widgets.sensitivity_panel import SensitivityPanel

    panel = SensitivityPanel()
    panel.set_assay_type(AssayType.IDA)

    with pytest.raises(RuntimeError, match='set_inputs'):
        panel.run_problems(ErrorModel(specs={'h0': InputSpec.sigma_pct(5.0)}))


def test_heatmap_controls_are_shown_only_in_heatmap_mode(qapp):
    panel = _ida_panel()

    assert panel._heatmap_group.isHidden() and not panel._samples_row.isHidden()

    panel._mode_combo.setCurrentIndex(panel._mode_combo.findText('Heatmap'))
    assert not panel._heatmap_group.isHidden() and panel._samples_row.isHidden()

    panel._mode_combo.setCurrentIndex(panel._mode_combo.findText('Sensitivity indices'))
    assert panel._heatmap_group.isHidden() and not panel._samples_row.isHidden()


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
    ]
    assert not any(control.isEnabled() for control in controls)
    assert panel._run_btn.text() == 'Cancel'
    panel.set_running(False)
    assert all(control.isEnabled() for control in controls)
    assert panel._run_btn.text() == 'Run Sensitivity Analysis'


def test_the_help_says_what_one_sample_is_and_where_the_uncertainties_are_set():
    """Every sample is one complete fit of one signal, drawn from the uncertainties stated for the fit.

    The analysis propagates those uncertainties, every draw counted the same;
    the fit's interval also weighs what the data say about the inputs, so the
    help says the two answer different questions and can differ.
    """
    from gui.widgets import sensitivity_panel

    text = ' '.join(sensitivity_panel._SECTION_HELP_HTML.split())
    assert 'one complete, deterministic fit of the averaged signal of the replicates your fit used' in text
    assert 'the same inputs always give the same K<sub>a</sub>' in text
    assert 'the uncertainty you set under <i>Input uncertainty</i>' in text
    assert 'a propagation of the uncertainties you stated (GUM Supplement 1)' in text
    assert 'also weighs what the data say about the inputs, so the two can differ' in text
    assert 'the same uncertainties widen the interval' not in text
    assert 'instead of its shares, spread and elasticities' in text
    # The zero-offset sample is the fit at the entered inputs (the baseline of the run).
    assert 'The sample at no offset at all is the fit at the inputs you entered.' in text
    # The replicates each sample uses follow the fit; the panel offers no choice of its own.
    helps = [value for name, value in vars(sensitivity_panel).items() if name.endswith('_HELP_HTML')]
    assert not any('Per replicate' in help_text or 'Average replicates' in help_text for help_text in helps)


def test_the_mode_help_says_a_shared_source_is_one_item_of_the_split():
    """The analysis splits the spread between the sources as stated, shared ones included."""
    from gui.widgets import sensitivity_panel

    text = ' '.join(sensitivity_panel._MODE_HELP_HTML.split())
    assert 'An error several inputs share is one source of its own' in text
    assert 'errors are unrelated' not in text
