"""GUI tests for the forward-simulation applet.

These pin the applet-specific contracts (not the forward-model math, which
``tests/unit/test_simulation.py`` covers): the registry-driven knob set, the
slider↔value mapping, negative-coefficient support, settings persistence, and
that every assay's default state yields a usable curve.
"""

import math

import numpy as np
import pytest

from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.simulation import build_concentration_vector, simulate_signal
from core.units import Q_
from gui.simulation.controls import ConcentrationInput, ParameterControl, _display_factor
from gui.simulation.sim_knob import knobs_for
from gui.simulation.simulation_panel import SimulationPanel
from gui.widgets.assay_conditions import condition_fields


def _knob(assay_type, key):
    """Fetch a real registry-sourced knob (carries its canonical Pint unit)."""
    return next(k for k in knobs_for(assay_type) if k.key == key)


def test_knob_set_is_registry_union_without_mode(qapp):
    """Each assay's knobs are exactly its conditions ∪ parameters — and never ``mode``."""
    panel = SimulationPanel()
    for at in AssayType:
        panel.set_assay_type(at)
        keys = set(panel._controls)
        expected = {f.key for f in condition_fields(at)} | set(ASSAY_REGISTRY[at].parameter_keys)
        assert keys == expected, at
        assert 'mode' not in keys  # categorical — derived from subtype, not a knob


def test_dba_treats_ka_dye_as_parameter(qapp):
    """Regression for the assay-uniformity bug: Ka_dye is a *parameter* in DBA."""
    panel = SimulationPanel()
    panel.set_assay_type(AssayType.DBA_DtoH)
    spec = panel.spec()
    assert 'Ka_dye' in spec.parameters  # not a condition here
    assert 'Ka_dye' not in spec.conditions
    assert spec.conditions['mode'] == 'DtoH'


def test_param_knob_classification_matches_registry_param_kinds(qapp):
    """Applet's per-parameter log/unit track the registry's ParamKind — they can't drift."""
    from core.assays.registry import ASSAY_REGISTRY, KIND_UNIT, ParamKind

    for at in AssayType:
        knobs = {k.key: k for k in knobs_for(at)}
        for key, kind in ASSAY_REGISTRY[at].param_kinds.items():
            assert knobs[key].log == (kind == ParamKind.BINDING_CONSTANT), (at, key)
            assert knobs[key].unit == Q_(1, KIND_UNIT[kind]).units, (at, key)


def test_log_slider_maps_geometrically(qapp):
    knob = _knob(AssayType.GDA, 'Ka_guest')  # association constant → log slider, [1e3, 1e9]
    c = ParameterControl(knob)
    c._slider.setValue(0)
    assert c.value() == pytest.approx(knob.vmin, rel=1e-3)
    c._slider.setValue(1000)
    assert c.value() == pytest.approx(knob.vmax, rel=1e-3)
    c._slider.setValue(500)  # midpoint of a log slider is the geometric mean
    assert c.value() == pytest.approx(math.sqrt(knob.vmin * knob.vmax), rel=1e-2)


def test_linear_slider_maps_arithmetically(qapp):
    knob = _knob(AssayType.GDA, 'I_dye_free')  # signal coefficient → linear slider
    c = ParameterControl(knob)
    c._slider.setValue(500)
    assert c.value() == pytest.approx((knob.vmin + knob.vmax) / 2, rel=1e-2)


def test_signal_coefficient_allows_negative(qapp):
    """A calibration intercept must be settable below zero (registry widget cannot)."""
    knob = _knob(AssayType.DYE_ALONE, 'intercept')
    c = ParameterControl(knob)
    c.load_state({'value': -250.0, 'min': -1e4, 'max': 1e4})
    assert c.value() == pytest.approx(-250.0)


def test_concentration_unit_switch_preserves_physical_quantity(qapp):
    """Switching a concentration knob's display unit must not change the physical value."""
    c = ParameterControl(_knob(AssayType.GDA, 'h0'))  # concentration → has a nM/µM/mM/M selector
    base = c.quantity().to('M').magnitude
    for unit in ('nM', 'mM', 'M', 'µM'):
        c._unit_combo.setCurrentText(unit)
        assert c.quantity().to('M').magnitude == pytest.approx(base, rel=1e-9)


def test_display_factor_is_pint_derived(qapp):
    """Concentration scale factors come from Pint (core.units), not hardcoded literals."""
    assert _display_factor('nM', 'M') == Q_(1, 'nM').to('M').magnitude
    assert _display_factor('mM', 'M') == Q_(1, 'mM').to('M').magnitude


def test_concentration_log_mode_round_trips_to_geometric_vector(qapp):
    ci = ConcentrationInput()
    ci.load_spec('log', {'start': 1e-8, 'stop': 1e-4, 'n': 9})
    mode, kwargs = ci.spec()
    v = build_concentration_vector(mode, **kwargs)
    ratios = v[1:] / v[:-1]
    assert np.allclose(ratios, ratios[0], rtol=1e-4)


def test_settings_round_trip_restores_assay_and_values(qapp):
    panel = SimulationPanel()
    panel.set_assay_type(AssayType.GDA)
    panel._controls['Ka_guest'].load_state({'value': 3e6, 'min': 1e3, 'max': 1e9})
    saved = panel.state()

    panel.set_assay_type(AssayType.DYE_ALONE)  # perturb
    panel.load_state(saved)
    restored = panel.state()

    assert restored['assay_type'] == 'GDA'
    assert restored['knobs']['Ka_guest']['value'] == pytest.approx(3e6)


def test_every_assay_default_yields_a_non_flat_curve(qapp):
    """Each assay opens on a simulatable, visibly-shaped curve (first-open UX)."""
    panel = SimulationPanel()
    for at in AssayType:
        panel.set_assay_type(at)
        spec = panel.spec()
        x = build_concentration_vector(spec.conc_mode, **spec.conc_kwargs)
        y = simulate_signal(spec.assay_cls, spec.conditions, spec.parameters, x)
        assert y.shape == x.shape
        assert np.ptp(y) > 0, f'{at.name} default curve is flat'


def test_window_recompute_overlays_noisy_scatter(qapp):
    """Enabling noise puts N replicate scatter series alongside the model line."""
    from gui.simulation.simulation_window import SimulationWindow

    w = SimulationWindow()
    captured: dict = {}
    w._plot.update_plot = lambda pd, **kw: captured.update(pd)  # intercept the redraw
    w._panel._noise.load_settings({'enabled': True, 'frac': 0.05, 'replicas': 3, 'seed': 1})
    w._recompute()

    assert len(captured['active_replicas']) == 3
    assert captured['fits'][0]['label'] == 'Simulated model'


def test_format_number_is_readable_and_scientific():
    """Large magnitudes read as scientific notation; O(1) values stay plain."""
    from gui.widgets.numeric_inputs import format_number

    assert format_number(33000000.0) == '3.3e7'
    assert format_number(5e7) == '5e7'
    assert format_number(1e9) == '1e9'
    assert format_number(50.0) == '50'
    assert format_number(292.0) == '292'
    assert format_number(0.0) == '0'
    assert format_number(-250.0) == '-250'
    assert format_number(5e-5) == '5e-5'


def test_sci_line_edit_accepts_scientific_entry(qapp):
    """A user can type '1e8' — the field parses and reformats it, no zero-counting."""
    from gui.widgets.numeric_inputs import SciLineEdit

    e = SciLineEdit()
    e.setValue(3.3e7)
    assert e.text() == '3.3e7'
    e.setText('1e8')
    e.editingFinished.emit()
    assert e.value() == pytest.approx(1e8)
    assert e.text() == '1e8'


def test_knobs_partition_into_registry_sections(qapp):
    """Every knob lands in the section its physical role dictates, for all assays."""
    from gui.simulation.sim_knob import SECTION_CONCENTRATION, SECTION_EQUILIBRIUM, SECTION_SIGNAL

    for at in AssayType:
        for k in knobs_for(at):
            if k.is_concentration:
                assert k.section == SECTION_CONCENTRATION, (at, k.key)
            elif k.log:  # association constant, condition or parameter
                assert k.section == SECTION_EQUILIBRIUM, (at, k.key)
            else:
                assert k.section == SECTION_SIGNAL, (at, k.key)


def test_panel_groups_knobs_into_section_boxes(qapp):
    """The flat list is gone: knobs render inside titled section group boxes."""
    from PyQt6.QtWidgets import QGroupBox

    from gui.simulation.sim_knob import SECTION_TITLES

    panel = SimulationPanel()
    panel.set_assay_type(AssayType.GDA)
    titles = {b.title() for b in panel._knob_container.findChildren(QGroupBox)}
    assert SECTION_TITLES['concentration'] in titles
    assert SECTION_TITLES['equilibrium'] in titles
    assert SECTION_TITLES['signal'] in titles

    # Dye-alone is purely a linear calibration → only the Signal parameters box.
    panel.set_assay_type(AssayType.DYE_ALONE)
    titles = {b.title() for b in panel._knob_container.findChildren(QGroupBox)}
    assert titles == {SECTION_TITLES['signal']}


def test_ka_log10_toggle_preserves_value_and_flips_display(qapp):
    """Toggling log₁₀ changes only the readout — the physical Ka is untouched."""
    c = ParameterControl(_knob(AssayType.GDA, 'Ka_guest'))
    base = c.value()
    c._log_toggle.setChecked(True)
    assert c.value() == pytest.approx(base)
    assert float(c._value_spin.text()) == pytest.approx(math.log10(base), rel=1e-3)
