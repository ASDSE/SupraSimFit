"""Simulation, a view of every session: what *Fit the data* carries, the session's model and data it reads, the wiring.

The rules are tested on :class:`gui.simulation.SimulationForm` without widgets; the view
tests lay the main window out off screen.
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
from gui.simulation import SPECIES_TOKENS, SimulationForm, SimulationProblem  # noqa: E402
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


def test_reading_the_noise_takes_the_fitters_noise_law_in_the_fields_units():
    """The floor is read in a.u. and the proportional part as a fraction, as ``noise_law()`` states them."""
    form = SimulationForm(AssayType.IDA)
    assert form.read_noise_refusal('empty', None) is not None  # no data
    x = form.points()
    clean = form.simulate().y_dense
    rng = np.random.default_rng(3)
    y = np.interp(x, np.linspace(x.min(), x.max(), clean.size), clean)
    signals = y + rng.normal(size=(6, x.size)) * np.sqrt(500.0**2 + (0.01 * y) ** 2)
    assert form.read_noise_refusal('six', signals) is None
    form.read_noise('six', signals)
    law = noise_law(signals)
    assert form.noise.floor == pytest.approx(law.floor, rel=0.05)
    assert form.noise.proportional == pytest.approx(law.proportional, rel=0.05)


def test_a_single_replicate_or_a_lawless_overlay_is_refused_in_plain_words():
    form = SimulationForm(AssayType.IDA)
    x = form.points()
    assert 'one replicate' in form.read_noise_refusal('one', np.ones((1, x.size)))
    # Identical replicates scatter nowhere, so no law can be read.
    with pytest.raises(SimulationProblem, match='No noise law could be read from same'):
        form.read_noise('same', np.tile(np.linspace(1.0, 2.0, x.size), (3, 1)))


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


def test_the_form_takes_a_binding_models_conditions_and_stock_in_their_units():
    """*Use this session's model*: the model, each condition in the unit shown and the dilution travel; a condition
    the session states no number for keeps the simulation's own value, and is named."""
    from gui.binding import BindingForm

    binding = BindingForm(AssayType.IDA)
    binding.set_unit('h0', 'nM')
    binding.set_value('h0', 5.1e-6)
    binding.set_value('Ka_dye', 2.5e7)
    binding.set_diluted(True)
    binding.set_unit('titrant_stock', 'mM')
    binding.set_value('titrant_stock', 2e-3)
    binding.set_contains('d0', True)
    form = SimulationForm(AssayType.GDA)
    form.take_binding(binding)
    assert form.assay_type is AssayType.IDA
    assert (form.knobs['h0'].value, form.knobs['h0'].unit, form.knobs['Ka_dye'].value) == (5.1e-6, 'nM', 2.5e7)
    assert (form.diluted, form.stock, form.stock_unit, form.contains) == (True, 2e-3, 'mM', {'d0'})
    binding.edit('d0', 'abc')
    with pytest.raises(SimulationProblem, match='Dye'):
        form.take_binding(binding)
    assert form.knobs['d0'].value == 6e-6 and form.knobs['h0'].value == 5.1e-6


# ── The view ─────────────────────────────────────────────────────────────────────────


@pytest.fixture
def window(qapp, monkeypatch):
    from PyQt6.QtCore import Qt

    from gui.main_window import FittingMainWindow

    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    made = FittingMainWindow()
    made.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    made.show()
    qapp.processEvents()
    yield made
    made.close()


def test_simulation_is_the_first_view_of_every_session(qapp, window):
    from gui.fitting_session import NAVIGATION, VIEWS

    assert NAVIGATION[0][0] == 'Design' and VIEWS[0] == 'Simulation'
    assert list(window._sidebar.nav) == list(VIEWS)
    window._act_new.trigger()
    for session in window.sessions():
        window._switch_to(session)
        window._sidebar.nav['Simulation'].click()
        assert session.current_view() == 'Simulation' and window._toolbar.title.text() == 'Simulation'
    (tools,) = [a.menu() for a in window.menuBar().actions() if a.text() == '&Tools']
    window.show_view('Measurements')
    next(a for a in tools.actions() if a.text() == 'Simulate…').trigger()
    assert window.current_view() == 'Simulation'


def test_the_view_opens_on_the_sessions_model_and_keeps_its_own_copy(qapp, window):
    """Seeded once, when first shown; a later edit of Binding model leaves it, *Use this session's model* copies it."""
    from tests.unit.gui.session_setup import state_binding

    session = window.active_session()
    state_binding(session, assay_type=AssayType.IDA, conditions={'h0': 5e-6})
    window.show_view('Simulation')
    form = session.model.simulation
    assert form.assay_type is AssayType.IDA and form.knobs['h0'].value == 5e-6
    state_binding(session, conditions={'h0': 7e-6})
    window.show_view('Measurements')
    window.show_view('Simulation')
    assert form.knobs['h0'].value == 5e-6
    session._simulation.use_model.click()
    assert form.knobs['h0'].value == 7e-6


def test_a_slider_recomputes_the_plots_and_leaves_the_binding_model_untouched(qapp, window):
    session = window.active_session()
    window.show_view('Simulation')
    view = session._simulation
    binding = session.model.settings
    before = view.plots.sim.y_dense.copy()
    key = next(k.key for k in session.model.simulation.section('binding') if not k.condition)
    view.rows[key].slider.moved.emit(0.9)
    assert not np.array_equal(view.plots.sim.y_dense, before)
    assert view.plots.sim is session.model.simulated
    assert session.model.settings == binding


@pytest.mark.parametrize('width', [1440, 0], ids=['wide', 'narrowest'])
def test_the_settings_fit_their_side_panel_and_the_readout_wraps_to_its_room(qapp, window, width):
    """Simulation's side panel never cuts its settings at the right, and the species readout breaks onto further
    lines rather than widening the window."""
    from tests.unit.gui import layout_rules

    session = window.active_session()
    assert session.set_up_demo_ida()
    window.show_view('Simulation')
    session.model.overlay_data(True)
    window.resize(width, 900)
    qapp.processEvents()
    assert layout_rules.cut_sideways(window) == []
    readout = session._simulation.readout
    assert readout.width() >= readout.minimumSizeHint().width()
    assert readout.height() == readout.heightForWidth(readout.width())
    if not width:
        assert readout.width() < readout.sizeHint().width() and readout.height() > readout.HEIGHT


def test_a_value_the_form_refuses_is_said_beside_the_settings(qapp, window):
    session = window.active_session()
    window.show_view('Simulation')
    view = session._simulation
    view.rows['h0'].value.edited.emit('abc')
    assert not view.problem.isHidden() and 'needs a number' in view.problem.text.text()
    view.rows['h0'].value.edited.emit('5')
    assert view.problem.isHidden()


def test_the_sessions_data_are_drawn_over_the_simulation_and_its_noise_read_from_them(qapp, window):
    session = window.active_session()
    window.show_view('Simulation')
    view = session._simulation
    assert not view.overlay.isEnabled() and not view.read_noise.isEnabled() and view.read_noise.toolTip()
    assert session.set_up_demo_ida()
    ms = session.model.measurement_set
    used = np.array([signal for _rid, signal in ms.iter_replicas()])
    view.overlay.toggled.emit(True)
    form = session.model.simulation
    np.testing.assert_array_equal(form.overlay.signals, used)
    np.testing.assert_array_equal(form.points(), ms.concentrations)
    assert view.read_noise.isEnabled()
    view.read_noise.click()
    law = noise_law(used)
    assert form.noise.floor == pytest.approx(law.floor, rel=0.05)
    assert form.noise.proportional == pytest.approx(law.proportional, rel=0.05)
    # The session's data change: the overlay follows them.
    session.model.set_replicate(ms.active_replica_ids[0], False)
    assert len(form.overlay.signals) == len(used) - 1


def test_fit_the_data_in_an_empty_session_makes_the_simulation_its_data(qapp, window, monkeypatch):
    from gui.fitting_session import FittingSession

    fitted = []
    monkeypatch.setattr(FittingSession, 'run_fit', lambda self: fitted.append(self))
    session = window.active_session()
    window.show_view('Simulation')
    window._toolbar.run.click()
    assert window.sessions() == [session] and fitted == [session]
    np.testing.assert_array_equal(session.model.measurement_set.signals, session.model.simulated.signals)
    assert window.current_view() == 'Fit results' and session.model.name().startswith('Simulated ')


def test_fit_the_data_in_a_session_with_data_opens_a_new_session(qapp, window, monkeypatch):
    from gui.fitting_session import FittingSession

    fitted = []
    monkeypatch.setattr(FittingSession, 'run_fit', lambda self: fitted.append(self))
    session = window.active_session()
    assert session.set_up_demo_ida()
    measured = session.model.measurement_set.signals.copy()
    window.show_view('Simulation')
    window._toolbar.run.click()
    first, new = window.sessions()
    assert first is session and fitted == [new] and window.active_session() is new
    np.testing.assert_array_equal(session.model.measurement_set.signals, measured)
    np.testing.assert_array_equal(new.model.measurement_set.signals, session.model.simulated.signals)
    assert new.model.name() == 'Simulated IDA'


def test_a_copy_of_a_session_carries_its_simulation_settings(qapp, session_model):
    from gui.session_model import SessionModel

    session_model.open_simulation()
    session_model.edit_simulation(lambda f: f.set_value('Ka_guest', '3.3e9'))
    copy = SessionModel()
    try:
        copy.copy_from(session_model)
        assert copy.simulation.to_dict() == session_model.simulation.to_dict()
        copy.edit_simulation(lambda f: f.set_value('Ka_guest', '1e7'))
        assert session_model.simulation.knobs['Ka_guest'].value == 3.3e9
        np.testing.assert_array_equal(copy.simulated.x, session_model.simulated.x)
    finally:
        copy.shutdown()


def test_the_curve_image_holds_the_titration_above_the_species(qapp, window, tmp_path):
    from PyQt6.QtGui import QImage

    from gui.views.simulation import EXPORT_HEIGHTS

    session = window.active_session()
    assert session.set_up_demo_ida()
    window.show_view('Simulation')
    view = session._simulation
    view.overlay.toggled.emit(True)
    for ext in ('png', 'svg'):
        view.export_image(str(tmp_path / f'curves.{ext}'))
    assert QImage(str(tmp_path / 'curves.png')).height() > 2 * sum(EXPORT_HEIGHTS)  # the plots and their heads
    drawing = (tmp_path / 'curves.svg').read_text()
    assert drawing.count('<svg') == 5  # the figure, its two plots and their two heads
    # Each plot's title and legend, as the view heads it: the titration's entries, then the species.
    n = session.model.measurement_set.n_active
    words = ['Titration', 'Simulated (3)', f'IDA_system.txt ({n})', 'Model', 'Species', 'Complexes', 'HD', 'HG', 'Free']
    texts = re.findall(r'<text[^>]*>([^<]*)</text>', drawing)
    assert all(word in texts for word in words), texts
