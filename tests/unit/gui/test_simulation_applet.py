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
from gui.simulation.controls import ConcentrationInput, ParameterControl
from gui.simulation.sim_knob import SimKnob, knobs_for
from gui.simulation.simulation_panel import SimulationPanel
from gui.widgets.assay_conditions import condition_fields


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


def test_log_slider_maps_geometrically(qapp):
    knob = SimKnob('Ka', 'Ka', '', 'binding', 'M⁻¹', 1e6, 1e3, 1e9, is_condition=False)
    c = ParameterControl(knob)
    c._slider.setValue(0)
    assert c.value() == pytest.approx(1e3, rel=1e-3)
    c._slider.setValue(1000)
    assert c.value() == pytest.approx(1e9, rel=1e-3)
    c._slider.setValue(500)  # midpoint of a log slider is the geometric mean
    assert c.value() == pytest.approx(math.sqrt(1e3 * 1e9), rel=1e-2)


def test_linear_slider_maps_arithmetically(qapp):
    knob = SimKnob('I', 'I', '', 'signal', 'au/M', 5e7, 0.0, 1e8, is_condition=False)
    c = ParameterControl(knob)
    c._slider.setValue(500)
    assert c.value() == pytest.approx(5e7, rel=1e-2)


def test_signal_coefficient_allows_negative(qapp):
    """A calibration intercept must be settable below zero (registry widget cannot)."""
    knob = next(k for k in knobs_for(AssayType.DYE_ALONE) if k.key == 'intercept')
    c = ParameterControl(knob)
    c.load_state({'value': -250.0, 'min': -1e4, 'max': 1e4})
    assert c.value() == pytest.approx(-250.0)


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
