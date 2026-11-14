"""The Simulation window: what *Fit in new session* carries, the noise read from an overlay, the wiring.

The rules are tested on :class:`gui.simulation.SimulationForm` without widgets; one smoke
test lays the window out off screen.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip('PyQt6')

from core.assays.registry import AssayType  # noqa: E402
from core.pipeline.noise import noise_law  # noqa: E402
from gui.simulation import SPECIES_TOKENS, Overlay, SimulationForm, SimulationProblem, value_text  # noqa: E402


@pytest.fixture
def session_model(qapp):
    from gui.session_model import SessionModel

    model = SessionModel()
    yield model
    model.shutdown()


@pytest.mark.parametrize('noisy', [True, False], ids=['noisy', 'noise-free'])
def test_fit_in_new_session_carries_the_data_as_shown_and_only_the_conditions(session_model, noisy):
    """The session gets the very replicates drawn and the model's conditions; no value a fit searches for travels."""
    form = SimulationForm(AssayType.IDA)
    form.set_noise(on=noisy)
    form.set_value('Ka_dye', '2.5e7')  # a condition: travels
    form.set_value('h0', '5.1')  # µM, a condition: travels
    form.set_value('Ka_guest', '3.3e9')  # fitted: stays here
    form.set_value('I_dye_bound', '1.23e11')  # fitted: stays here
    sim = form.simulate()
    form.carry_to(session_model, sim)

    ms = session_model.measurement_set
    np.testing.assert_array_equal(ms.signals, sim.signals)
    np.testing.assert_array_equal(ms.concentrations, sim.x)
    assert ms.n_replicas == (3 if noisy else 1)

    settings = session_model.settings
    assert settings.assay_type is AssayType.IDA
    conditions = {k: float(v.to('M' if k != 'Ka_dye' else '1/M').magnitude) for k, v in settings.conditions.items()}
    assert conditions == pytest.approx({'Ka_dye': 2.5e7, 'h0': 5.1e-6, 'd0': 6e-6}, rel=1e-12)
    # The fit starts from its own defaults: no bound, start or value of a fitted parameter is passed.
    assert settings.custom_bounds is None
    assert not settings.input_problems and not settings.assay_problems


def test_every_model_opens_on_a_curve_with_every_species_coloured():
    """Each model opens on a computed, non-flat titration whose species all have a colour token."""
    form = SimulationForm()
    for assay_type in AssayType:
        form.set_assay(assay_type)
        sim = form.simulate()
        assert np.ptp(sim.y_dense) > 10 * form.noise.floor > 0, assay_type
        assert set(sim.species) <= set(SPECIES_TOKENS), assay_type


def test_read_from_overlaid_data_takes_the_fitters_noise_law_in_the_fields_units():
    """The floor is read in a.u. and the proportional part as a fraction, as ``noise_law()`` states them."""
    form = SimulationForm(AssayType.IDA)
    assert form.read_noise_refusal() is not None  # nothing overlaid
    x = form.points()
    clean = form.simulate().y_dense
    rng = np.random.default_rng(3)
    y = np.interp(x, np.linspace(x.min(), x.max(), clean.size), clean)
    signals = y + rng.normal(size=(6, x.size)) * np.sqrt(500.0**2 + (0.01 * y) ** 2)
    form.set_overlay(Overlay('six.txt', x, signals))
    assert form.read_noise_refusal() is None
    form.read_noise()
    law = noise_law(signals)
    assert form.noise.floor == pytest.approx(law.floor, rel=0.05)
    assert form.noise.proportional == pytest.approx(law.proportional, rel=0.05)


def test_a_single_replicate_or_a_lawless_overlay_is_refused_in_plain_words():
    form = SimulationForm(AssayType.IDA)
    x = form.points()
    form.set_overlay(Overlay('one.txt', x, np.ones((1, x.size))))
    assert 'one replicate' in form.read_noise_refusal()
    # Identical replicates scatter nowhere, so no law can be read.
    form.set_overlay(Overlay('same.txt', x, np.tile(np.linspace(1.0, 2.0, x.size), (3, 1))))
    with pytest.raises(SimulationProblem, match='No noise law could be read from same.txt'):
        form.read_noise()


def test_settings_survive_a_save_and_load():
    form = SimulationForm(AssayType.DBA_HG2)
    form.set_value('Ka_HG2', '4.4e4')
    form.set_end('Ka_HG2', True, '1e8')
    form.set_noise(floor=12.0, proportional=0.02, replicates=5, seed=9)
    again = SimulationForm()
    again.load_dict(form.to_dict())
    np.testing.assert_array_equal(again.simulate().signals, form.simulate().signals)
    with pytest.raises(SimulationProblem):
        again.load_dict({'version': 1})


def test_the_window_draws_reads_noise_and_asks_for_a_new_session(qapp):
    from PyQt6.QtCore import Qt

    from gui.views.simulation import SimulationWindow

    window = SimulationWindow()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    window.show()
    assert not window.read_noise.isEnabled() and window.read_noise.toolTip()
    x = window.form.points()
    rng = np.random.default_rng(1)
    signals = 1e5 + rng.normal(size=(4, x.size)) * 300.0 * (1 + np.linspace(0, 1, x.size))
    window.edit(lambda f: f.set_overlay(Overlay('data.txt', x, signals)))
    assert window.read_noise.isEnabled()
    window.read_noise.click()
    noise = window.form.noise
    assert noise.proportional > 0  # the default states none
    assert (window.floor.text, window.proportional.text) == (
        value_text(noise.floor),
        value_text(100 * noise.proportional),
    )
    window.edit(lambda f: f.choose_model(AssayType.DBA_H2G), rebuild=True)
    assert set(window.rows) == set(window.form.knobs)
    asked = []
    window.fit_requested.connect(lambda form, sim: asked.append((form, sim)))
    window.fit_in_new_session()
    assert asked and asked[0][1] is window.sim
    window.close()
