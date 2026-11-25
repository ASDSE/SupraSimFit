"""The Help window's Demo IDA examples read the numbers the views show for the demo.

Demo IDA states input uncertainties, so its fit is the input-aware one, which costs
seconds, and the Sensitivity example needs a seeded Sobol' run at the smallest N the
window offers: this check lives here, the slow layer, while the fast layer only checks
that every section carries its example (``tests/unit/gui/test_help.py``).
"""

from __future__ import annotations

import sys
from dataclasses import replace

import numpy as np
import pytest

pytest.importorskip('PyQt6')


@pytest.fixture(scope='module')
def qapp():
    """The one QApplication of the process."""
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication(sys.argv)


def test_the_help_examples_are_the_numbers_demo_ida_shows(qapp):
    """Every figure of :data:`gui.help.DEMO` is worked out again as its view writes it, to the digit shown."""
    import gui.confidence as Cf
    import gui.results as R
    import gui.sensitivity as S
    from core.pipeline.fit_pipeline import fit_measurement_set
    from core.pipeline.profile import fit_profile
    from core.pipeline.reporting import fit_replica_ids
    from core.pipeline.sensitivity import run_sensitivity
    from gui.help import DEMO
    from gui.session_model import SessionModel
    from gui.simulation import readout_value, species_groups
    from gui.widgets.assay_conditions import assay_class

    # Demo IDA as load_demo_ida() states it, and the fit and Ka profile the session runs on it.
    model = SessionModel()
    assert model.set_up_demo() is None
    settings, ms = model.settings, model.measurement_set
    used = ms.with_active(ms.active_replica_ids)
    cls, conditions = assay_class(settings.assay_type), dict(settings.conditions)
    config = replace(settings.fit_config(), errors=settings.errors, input_labels=dict(settings.input_labels))
    fit = fit_measurement_set(used, cls, conditions, config)
    profile = fit_profile(ms.with_active(fit_replica_ids(fit)), cls, conditions, config, **fit.profile_arguments())

    # Measurements: the replicates loaded and the one Outlier removal switches off.
    quality = R.quality(fit, ms)
    off = [chr(ord('A') + i) for i, r in enumerate(ms.replica_ids) if r not in ms.active_replica_ids]
    assert (str(len(ms.replica_ids)), ', '.join(off), quality.used) == (DEMO['loaded'], DEMO['off'], DEMO['used'])

    # Fit results: both readings, the conflict callout and the two misfit tests.
    (header,) = Cf.headers(fit)
    aware, entered = header.readings
    assert (aware.label, entered.label) == (R.INPUT_AWARE, R.AS_ENTERED)
    assert (aware.value, aware.interval) == (DEMO['aware'], DEMO['aware_interval'])
    assert (entered.value, entered.interval, entered.split) == (DEMO['entered'], DEMO['entered_interval'], False)
    assert R.callouts(fit, None)[0].title == DEMO['conflict']
    tests = {row.name: row for row in R.test_rows(fit)}
    assert tests['misfit'].tone == 'success' and tests['misfit'].p == DEMO['p_moved']
    assert tests['conditional_misfit'].tone == 'warning' and tests['conditional_misfit'].p == DEMO['p_entered']

    # Ka confidence: how much higher the lowest point of Inputs as entered lies, and the card at the reported estimate.
    plot = Cf.profile_plot(fit, profile.profiles['Ka_guest'])
    curves = {c.label: c for c in plot.curves}
    assert f'{np.nanmin(curves[R.AS_ENTERED].y):.1f}' == DEMO['depth']
    card = {row.label: row for row in Cf.readout(plot, curves[R.INPUT_AWARE].estimate[0])}
    assert (card[R.INPUT_AWARE].value, card[R.INPUT_AWARE].verdict) == (DEMO['card_aware'], 'accepted')
    assert (card[R.AS_ENTERED].value, card[R.AS_ENTERED].verdict) == (DEMO['card_entered'], 'rejected')

    # Sensitivity: Sensitivity indices at Fixed seed on and the N the example names.
    model.analysis.fixed_seed, model.analysis.seed_text = True, DEMO['seed']
    model.analysis.n_samples = int(DEMO['n'])
    sens = run_sensitivity(
        used, cls, conditions, settings.fit_config(), model.analysis_config(), input_labels=dict(settings.input_labels)
    )
    spread = S.spread(sens, 'Ka_guest')
    assert (spread.factor, spread.decades, spread.centre) == (DEMO['spread'], DEMO['decades'], DEMO['centre'])
    rows = S.index_chart(sens, 'Ka_guest').rows
    assert ', '.join(f'{r.name} {S.share(r.s1)}' for r in rows) == DEMO['shares']
    first = S.budget_table(sens, 'Ka_guest').rows[0]
    assert (first[0].value, first[4].value) == (DEMO['top'], DEMO['exact'])

    # Simulation: in the demo's session it opens on the Inputs as entered fit, its species row at a third of the axis.
    model.open_simulation()
    form, sim = model.simulation, model.simulated
    assert R.headline_value(form.knobs['Ka_guest'].value, '', (1, 1), (False, False))[0] == DEMO['entered']
    i = len(sim.x_dense) // 3
    scale = 1e6  # the grid's µM
    assert form.grid.unit == 'µM'
    assert f'{form.x_name} {readout_value(float(sim.x_dense[i] * scale))} µM' == DEMO['sim_x']
    shown = {
        k: readout_value(float(sim.species[k][i] * scale)) for _w, keys in species_groups(sim.species) for k in keys
    }
    assert (shown['HG'], shown['HD'], shown['G']) == (DEMO['sim_hg'], DEMO['sim_hd'], DEMO['sim_g'])
