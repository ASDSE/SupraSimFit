"""The Simulation window: what *Fit in new session* carries, the noise read from an overlay, the wiring.

The rules are tested on :class:`gui.simulation.SimulationForm` without widgets; one smoke
test lays the window out off screen.
"""

from __future__ import annotations

import re

import numpy as np
import pytest

pytest.importorskip('PyQt6')

from core.assays.registry import AssayType  # noqa: E402
from core.pipeline.noise import noise_law  # noqa: E402
from core.simulation import simulate_signal  # noqa: E402
from core.units import Q_  # noqa: E402
from gui.simulation import SPECIES_TOKENS, Overlay, SimulationForm, SimulationProblem, value_text  # noqa: E402
from gui.widgets.assay_conditions import assay_class  # noqa: E402


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
    assert session_model.name() == 'Simulated IDA' and not session_model.dataset.files

    settings = session_model.settings
    assert settings.assay_type is AssayType.IDA
    conditions = {k: float(v.to('M' if k != 'Ka_dye' else '1/M').magnitude) for k, v in settings.conditions.items()}
    assert conditions == pytest.approx({'Ka_dye': 2.5e7, 'h0': 5.1e-6, 'd0': 6e-6}, rel=1e-12)
    # The fit starts from its own defaults: no bound, start or value of a fitted parameter is passed.
    assert settings.custom_bounds is None
    assert not settings.input_problems and not settings.assay_problems
    assert 'titrant_stock' not in settings.conditions  # the totals stay constant


def test_a_stated_stock_dilutes_the_totals_the_stock_lacks_through_the_fitters_forward_model():
    """With a stock, each point is the constant-totals model at the totals left after that addition.

    The check is independent of ``fixed_total()``: every point is computed on its own with the
    totals written out by hand, ``h0·(1 − x/c_T)`` for the host and ``d0`` for the dye the stock
    holds. Without a stock the conditions carry no dilution key and the signal is the model's own.
    """
    form = SimulationForm(AssayType.IDA)
    form.set_noise(on=False)
    cls, params, x = assay_class(AssayType.IDA), form.parameters(), form.points()
    constant = {k.key: Q_(k.value, k.base_unit) for k in form.knobs.values() if k.condition}
    assert form.conditions() == constant
    np.testing.assert_array_equal(form.simulate().signals[0], simulate_signal(cls, constant, params, x))

    form.set_diluted(True)
    form.set_stock('50')  # µM: the last addition leaves 82 % of the host
    form.set_contains('d0', True)
    stock, h0 = 0.05e-3, constant['h0'].magnitude
    by_hand = [
        simulate_signal(cls, {**constant, 'h0': Q_(h0 * (1 - xi / stock), 'M')}, params, np.array([xi]))[0] for xi in x
    ]
    diluted = form.simulate().signals[0]
    np.testing.assert_allclose(diluted, by_hand, rtol=1e-9)
    assert not np.allclose(diluted, simulate_signal(cls, constant, params, x), rtol=1e-3)


def test_choosing_dilution_offers_a_stock_ten_times_the_highest_titrant_concentration_of_the_grid():
    """The offer follows the grid as it is when dilution is chosen, in the largest unit that keeps it at 1 or more."""
    form = SimulationForm(AssayType.IDA)  # its even grid ends at 9 µM
    form.set_diluted(True)
    assert form.stock == pytest.approx(90e-6, rel=1e-12)
    assert (form.stock_text(), form.stock_unit) == ('90', 'µM')
    form.set_diluted(False)
    form.set_grid_unit('mM')
    form.set_even('0', '0.2', '24')  # mM
    form.set_diluted(True)
    assert (form.stock_text(), form.stock_unit) == ('2', 'mM')


def test_the_stock_travels_to_the_new_session_and_is_refused_where_it_cannot_hold(session_model):
    form = SimulationForm(AssayType.IDA)
    form.set_diluted(True)
    form.set_stock_unit('µM')
    form.set_stock('50')
    form.set_contains('h0', True)
    with pytest.raises(SimulationProblem, match='every fixed total'):
        form.set_contains('d0', True)
    form.set_stock('8')  # below the highest titrant concentration, 9 µM
    with pytest.raises(SimulationProblem, match='more concentrated than the highest titrant'):
        form.simulate()
    form.set_stock('50')
    form.carry_to(session_model, form.simulate())
    settings = session_model.settings
    assert settings.conditions['titrant_stock'].to('M').magnitude == pytest.approx(50e-6, rel=1e-12)
    assert settings.conditions['stock_contains'] == ('h0',)
    assert settings.condition_units['titrant_stock'] == 'µM'
    assert not settings.assay_problems and session_model.stock_problem() is None


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
    form.set_diluted(True)
    form.set_stock('60')  # mM
    again = SimulationForm()
    again.load_dict(form.to_dict())
    assert (again.diluted, again.stock) == (True, 60e-3)
    np.testing.assert_array_equal(again.simulate().signals, form.simulate().signals)
    with pytest.raises(SimulationProblem):
        again.load_dict({'version': 1})


def test_the_window_draws_reads_noise_and_asks_for_a_new_session(qapp, tmp_path, monkeypatch):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QImage
    from PyQt6.QtWidgets import QFileDialog

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
    # The stock: its row shows once dilution is chosen, with one box per fixed total the stock may hold.
    assert window.stock_row.isHidden()
    window.dilution.changed.emit(1)
    assert window.form.diluted and not window.stock_row.isHidden() and set(window._contains) == {'h0', 'd0'}
    # The curve image: the titration above the species, one picture or one drawing.
    for ext in ('png', 'svg'):
        path = tmp_path / f'curves.{ext}'
        monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a, path=path: (str(path), ''))
        window.export_image()
    from gui.views.simulation import EXPORT_HEIGHTS

    assert QImage(str(tmp_path / 'curves.png')).height() > 2 * sum(EXPORT_HEIGHTS)  # the plots and their heads
    drawing = (tmp_path / 'curves.svg').read_text()
    assert drawing.count('<svg') == 5  # the figure, its two plots and their two heads
    # Each plot's title and legend, as the window heads it: the titration's entries, then the species.
    words = [
        'Titration',
        'Simulated (3)',
        'data.txt (4)',
        'Model',
        'Species',
        'Complexes',
        'HD',
        'HG',
        'Free',
        'D',
        'G',
        'H',
    ]
    texts = re.findall(r'<text[^>]*>([^<]*)</text>', drawing)
    assert all(word in texts for word in words), texts
    window.edit(lambda f: f.choose_model(AssayType.DBA_H2G), rebuild=True)
    assert set(window.rows) == set(window.form.knobs)
    asked = []
    window.fit_requested.connect(lambda form, sim: asked.append((form, sim)))
    window.fit_in_new_session()
    assert asked and asked[0][1] is window.sim
    window.close()
