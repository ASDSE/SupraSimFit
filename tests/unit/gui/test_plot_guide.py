"""Help ▸ Reading the plots: each entry point opens the window's one non-modal guide at the right section.

Also guards the examples and the Sensitivity entry against the code they
describe: the Ka confidence numbers are recomputed from the demo data, the
budget's columns and the name of the per-addition item are read off the
rules the view draws them from, and the fit count the example quotes is computed by the
analysis itself. A guide that drifts away from what the app produces fails here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytest.importorskip('PyQt6')

_IDA_DATA = Path(__file__).resolve().parents[3] / 'data' / 'IDA_system.txt'


@pytest.fixture
def guide_off_screen(monkeypatch):
    """Guides created during the test lay out and count as shown, but never appear on screen."""
    from PyQt6.QtCore import Qt

    from gui.dialogs.plot_guide_dialog import PlotGuideDialog

    create = PlotGuideDialog.__init__

    def create_off_screen(self, *args, **kwargs):
        create(self, *args, **kwargs)
        self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)

    monkeypatch.setattr(PlotGuideDialog, '__init__', create_off_screen)
    return PlotGuideDialog


def _show(qapp, widget):
    from PyQt6.QtCore import Qt

    widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    widget.show()
    qapp.processEvents()
    return widget


def test_every_section_of_the_guide_is_listed_under_its_own_title(qapp, guide_off_screen):
    from gui.plot_guide import PLOT_GUIDE

    guide = guide_off_screen()
    listed = [guide._nav.item(row).text() for row in range(guide._nav.count())]

    assert len(listed) == len(PLOT_GUIDE)
    for row, key in enumerate(PLOT_GUIDE):
        guide._nav.setCurrentRow(row)
        assert guide.current_section() == key
        assert guide._text.toPlainText().startswith(listed[row])


def test_help_menu_opens_one_non_modal_guide(qapp, monkeypatch, guide_off_screen):
    """Help ▸ Reading the plots… shows the guide beside the window; choosing it again raises the same one."""
    from PyQt6.QtCore import Qt

    from gui.main_window import FittingMainWindow

    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    window = _show(qapp, FittingMainWindow())
    (help_menu,) = [action.menu() for action in window.menuBar().actions() if action.text() == '&Help']
    (reading,) = [action for action in help_menu.actions() if action.text() == 'Reading the plots…']

    reading.trigger()
    reading.trigger()
    qapp.processEvents()

    (guide,) = window.findChildren(guide_off_screen)
    assert guide.isVisible()
    assert guide.windowModality() is Qt.WindowModality.NonModal


def test_toolbar_help_opens_the_section_of_the_view_on_screen(qapp, monkeypatch, guide_off_screen):
    """The toolbar's Help opens the guide at the section of the plot the view shows, for every view with one."""
    from gui import plot_guide
    from gui.main_window import FittingMainWindow

    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    window = _show(qapp, FittingMainWindow())
    expected = {
        'Fit results': plot_guide.FIT_CURVE,
        'Ka confidence': plot_guide.CONFIDENCE,
        'Sensitivity': plot_guide.SENSITIVITY,
    }
    for view, key in expected.items():
        window.show_view(view)
        window._toolbar.help.click()
        qapp.processEvents()
        (guide,) = window.findChildren(guide_off_screen)
        assert guide.isVisible()
        assert guide.current_section() == key
        assert guide._text.toPlainText().startswith(plot_guide.PLOT_GUIDE[key][0])


def test_the_examples_still_describe_the_demo_data():
    """Recomputes the guide's quoted numbers from the demo data it names.

    The examples invite the user to reproduce them, so every figure in them — the
    fit and its interval, R², RMSE, the parameter count behind the interval, and
    the scaled drop a doubled and a halved Ka reach — is recomputed here and
    looked for in the text. A change in the fit that the guide does not follow
    fails this.
    """
    import numpy as np
    from scipy.optimize import brentq

    from core.assays import IDAAssay
    from core.data_processing.measurement_set import MeasurementSet
    from core.data_processing.preprocessing import get_step
    from core.io import load_measurements
    from core.pipeline.fit_pipeline import FitConfig, _resolve_bounds, fit_measurement_set
    from core.pipeline.profile import fit_profile
    from core.pipeline.varpro import Projection
    from core.units import Q_
    from gui.plot_guide import CONFIDENCE, FIT_CURVE, PLOT_GUIDE, SUMMARY

    # Demo IDA as the guide's note describes it: the bundled data through Outlier
    # Removal at its defaults, the conditions the Demo IDA button sets, averaged.
    ms = MeasurementSet.from_dataframe(load_measurements(str(_IDA_DATA)))
    get_step('zscore_replica_filter', {'threshold': 3.5, 'min_replicas': 3})(ms)
    conditions = {'h0': Q_(4.3e-6, 'M'), 'd0': Q_(6e-6, 'M'), 'Ka_dye': Q_(16.8e6, '1/M')}
    config = FitConfig(per_replica=False)
    result = fit_measurement_set(ms, IDAAssay, conditions, config)
    profiles = fit_profile(ms, IDAAssay, conditions, config, **result.profile_arguments())
    profile = profiles.profiles['Ka_guest']

    # The demo data carry replicates, so they show a noise law and the fit is
    # weighted by it: this projection has to carry the same weights or its
    # ss_tot and row_ssr describe another fit.
    assay = ms.to_assay(IDAAssay, conditions=conditions, use_average=True)
    assert profiles.weighted
    projection = Projection(assay, _resolve_bounds(assay, None), point_weights=result.point_weights)
    ss_tot = float(projection.ss_tot[0])

    def at(factor: float) -> float:
        """The best weighted R² the profile reaches at *factor* times the best Ka."""
        return 1.0 - float(projection.row_ssr({'Ka_guest': profile.best_ka * factor})[0]) / ss_tot

    interval = result.intervals['Ka_guest']
    lo, hi = interval.low, interval.high
    best = float(result.parameters['Ka_guest'].magnitude)
    assert (profile.best_ka, profile.interval.low) == (best, lo), 'the view and the fit report the same numbers'

    # Where the cut-off steps down because the fit holds the signal offset on
    # its bound: the profile falls under the upper level above the step and
    # clears the lower one again below it, so the interval spans two stretches.
    grid, cut = np.asarray(profile.grid, dtype=float), np.asarray(profile.r2_cut, dtype=float)
    (step,) = np.flatnonzero(np.diff(cut) != 0)
    edge = float(np.sqrt(grid[step] * grid[step + 1]))  # the step falls between two drawn Ka
    assert lo < grid[step] and interval.split, 'the interval no longer reaches past the step the guide describes'
    assert abs(at(lo / best) - cut[step]) < 1e-6, 'the low edge is where the profile crosses the lower cut-off'
    below = grid[(grid > lo) & (grid <= grid[step])]
    assert below.size and all(at(k / best) >= cut[step] for k in below)
    # The upper stretch begins where the profile crosses the upper cut-off, between
    # the last drawn Ka above the step it rejects and the first it accepts.
    above = grid[(grid > grid[step]) & (grid < best)]
    rejected = above[[at(k / best) < cut[step + 1] for k in above]]
    start = brentq(lambda k: at(k / best) - cut[step + 1], rejected.max(), best)

    def drop(factor: float) -> float:
        """The scaled drop at *factor* times the best Ka: the rise over the best fit, over the rise the test allows there.

        Read off the residual of an independent solve and the cut-off of the nearest drawn point, which
        holds over the whole stretch either side of a step.
        """
        level = cut[int(np.argmin(np.abs(np.log10(grid) - np.log10(best * factor))))]
        return (profile.r2_top - at(factor)) / (profile.r2_top - level)

    confidence = re.sub(r'\s+', ' ', PLOT_GUIDE[CONFIDENCE][1])
    for phrase in (
        f'best fit {best / 1e8:.2f}&times;10<sup>8</sup>',
        f'interval [{lo / 1e8:.2f}&times;10<sup>8</sup>, {hi / 1e8:.2f}&times;10<sup>8</sup>]',
        f'(&minus;{round(100 * (1 - lo / best))}&thinsp;% / +{round(100 * (hi / best - 1))}',
        f'worked out from {profile.n_points} data points and {profile.n_params} fitted parameters.',
        f'At twice the best K<sub>a</sub> the curve stands at {drop(2.0):.2f}, at half at {drop(0.5):.2f}',
        f'Below {edge / 1e8:.1f}&times;10<sup>8</sup>',
        f'line at 1 at {start / 1e8:.2f}&times;10<sup>8</sup>',
        f'from the step down to {lo / 1e8:.2f}&times;10<sup>8</sup>',
        f'by {result.rmse / 1e3:.1f}&times;10<sup>3</sup> a.u. (RMSE)',
    ):
        assert phrase in confidence, phrase
    assert drop(2.0) > 1 and drop(0.5) > 1, 'the guide calls both rejected'
    assert profile.scaled_drop()[grid == lo] == pytest.approx(1.0, abs=1e-6), 'the curve meets the line at the edge'

    # Why the cut-off sits below the plain F test's: the shares the replicates
    # allow and the design effect the interval was widened by over them.
    low_share, high_share = result.noise.share_set
    for phrase in (
        f'the {len(result.metadata["active_replica_ids"])} replicates leave the share of proportional noise '
        f'anywhere between {low_share:.2g} and {high_share:.2g}',
        f'(variance &times;{interval.inflation:.2f})',
    ):
        assert phrase in confidence
    # The Readme quotes the noise sentence this fit carries.
    readme = re.sub(r'\s+', ' ', (_IDA_DATA.parents[1] / 'Readme.md').read_text(encoding='utf-8'))
    assert f'`{result.noise.describe()}`' in readme

    # The headline Fit results and Fit details quote is the same fit, to the three
    # significant figures every view writes a fitted value with.
    headline = (
        f'{best / 1e8:.2f}&times;10<sup>8</sup> M<sup>&minus;1</sup> [{lo / 1e8:.2f}&times;10<sup>8</sup>, '
        f'{hi / 1e8:.2f}&times;10<sup>8</sup>]' + (' &dagger;' if interval.split else '')
    )
    used = len(result.metadata['active_replica_ids'])
    signals = ms.signals[[ms.replica_ids.index(r) for r in ms.active_replica_ids]]
    # How many concentrations the Fit results example calls a systematic miss:
    # every replicate on one side of the curve the fit drew.
    fitted = assay.y_data.magnitude - projection.residual({'Ka_guest': best}) / np.sqrt(projection.point_weights)
    one_sided = int(np.sum(np.all(signals > fitted, axis=0) | np.all(signals < fitted, axis=0)))
    for key, extra in (
        (
            FIT_CURVE,
            (
                f'R&sup2; {result.r_squared:.4f}.',
                f'At {one_sided} of the {fitted.size} concentrations all {used} replicates',
            ),
        ),
        # Counted as Fit quality counts them, against every replicate loaded.
        (SUMMARY, (f'R&sup2; {result.r_squared:.4f}, {used} of {ms.n_replicas} replicates used',)),
    ):
        text = re.sub(r'\s+', ' ', PLOT_GUIDE[key][1])
        assert headline in text
        for phrase in extra:
            assert phrase in text
    summary = re.sub(r'\s+', ' ', PLOT_GUIDE[SUMMARY][1])
    assert f'{np.max(signals) / 1e5:.1f}&times;10<sup>5</sup> a.u.' in summary
    assert f'{result.rmse / 1e3:.2f}&times;10<sup>3</sup> a.u.' in summary


def test_the_demo_note_states_what_demo_ida_sets():
    """The note names the replicates Outlier Removal keeps and the uncertainties the Demo IDA button states."""
    from collections import defaultdict

    from core.data_processing.measurement_set import MeasurementSet
    from core.data_processing.preprocessing import get_step
    from core.io import load_measurements
    from core.pipeline.inputs import SpecKind
    from gui.fitting_session import _DEMO_UNCERTAINTIES
    from gui.plot_guide import DEMO_NOTE

    ms = MeasurementSet.from_dataframe(load_measurements(str(_IDA_DATA)))
    get_step('zscore_replica_filter', {'threshold': 3.5, 'min_replicas': 3})(ms)
    dropped = [chr(ord('A') + i) for i, rid in enumerate(ms.replica_ids) if rid not in ms.active_replica_ids]
    note = re.sub(r'\s+', ' ', DEMO_NOTE)
    assert f'{len(ms.active_replica_ids)} of its {ms.n_replicas} replicates averaged' in note
    assert f'(Outlier Removal drops {", ".join(dropped)})' in note

    named = {'Ka_dye': 'K<sub>a,dye</sub>', 'h0': '[Host]<sub>0</sub>', 'd0': '[Dye]<sub>0</sub>'}
    by_sigma = defaultdict(list)
    for key, spec in _DEMO_UNCERTAINTIES.items():
        assert (spec.kind, spec.relative) == (SpecKind.SIGMA, True), 'the note states each as a σ in percent'
        by_sigma[spec.sigma].append(named.get(key, 'the titrant'))
    for sigma, inputs in by_sigma.items():
        on = inputs[0] if len(inputs) == 1 else f'{", ".join(inputs[:-1])} and {inputs[-1]}'
        assert f'&sigma; {sigma:g}&thinsp;% on {on}' in note


#: What the Sensitivity entry says about each column of the budget, keyed by the column the view draws.
#: Written out here rather than matched loosely, so a column renamed or added in the view fails until
#: the guide explains it.
_BUDGET_COLUMN_IN_THE_GUIDE = {
    'Source': 'What is ranked: sources, not inputs',
    'Stated': '<i>Stated</i> &mdash; what you entered',
    'Elasticity': '<i>Elasticity</i> &mdash; how many percent K<sub>a</sub> moves per percent',
    'Variance': '<i>Variance</i> &mdash; the variance this source explains on its own, in decades&sup2;',
    'Spread if exact (decades)': '<i>Spread if exact</i> &mdash; what would be left',
}


def _sensitivity_text() -> str:
    """The Sensitivity entry as one line, so a phrase broken over two lines still matches."""
    from gui.plot_guide import PLOT_GUIDE, SENSITIVITY

    return re.sub(r'\s+', ' ', PLOT_GUIDE[SENSITIVITY][1])


def test_the_sensitivity_entry_explains_every_column_of_the_budget_table():
    """A column on screen with no explanation is a number the reader cannot act on."""
    from gui.sensitivity import ALL_SOURCES, BUDGET_COLUMNS, INTERACTIONS

    assert tuple(_BUDGET_COLUMN_IN_THE_GUIDE) == BUDGET_COLUMNS
    text = _sensitivity_text()
    missing = [header for header, phrase in _BUDGET_COLUMN_IN_THE_GUIDE.items() if ' '.join(phrase.split()) not in text]
    assert not missing, f'the guide no longer explains these budget columns: {missing}'
    assert f'<i>{INTERACTIONS}</i>' in text and f'<i>{ALL_SOURCES}</i>' in text, 'the last rows are unexplained'


def test_the_sensitivity_entry_calls_the_per_addition_item_what_the_view_labels_it():
    """The reader looks the item up by the name on screen, and reads what the view says under the budget."""
    from gui.sensitivity import ADDITIONS_LABEL, ADDITIONS_NOTE

    text = _sensitivity_text()

    assert f'<b>{ADDITIONS_LABEL}</b>' in text
    # A stated error of each addition is part of the fit's interval, and both texts say so.
    statement = 'The random error of each addition is part of the reported interval when stated under Input uncertainty'
    assert ADDITIONS_NOTE.startswith(statement)
    assert statement in text
    assert 'does not include the random error of each addition' not in text


def test_the_sensitivity_example_quotes_the_fit_count_its_own_run_would_cost():
    """The example runs the demo's four stated sources at a sample size; the run's own estimate has to match it.

    The elasticity refits are part of that estimate, so a guide written before
    them would quote the older, smaller number and fail here.
    """
    from core.pipeline.inputs import ErrorModel
    from core.pipeline.sensitivity import SensitivityConfig, SensitivityMode, estimated_fit_count
    from gui.fitting_session import _DEMO_UNCERTAINTIES

    inputs = tuple(_DEMO_UNCERTAINTIES)
    config = SensitivityConfig(
        mode=SensitivityMode.SOBOL, n_samples=1024, errors=ErrorModel(specs=dict(_DEMO_UNCERTAINTIES))
    )

    fits = estimated_fit_count(config, len(inputs))

    assert fits > config.n_samples * (len(inputs) + 2), 'the elasticity refits are part of the cost'
    assert f'sample size 1024, which costs {fits} fits' in _sensitivity_text()


def test_the_guide_quotes_the_level_the_one_step_test_is_run_at():
    """The level a closed lower end of a second constant has to pass is the engine's, not a number copied once."""
    from core.pipeline.varpro import SECOND_STEP_LEVEL
    from gui.plot_guide import CONFIDENCE, PLOT_GUIDE

    text = re.sub(r'\s+', ' ', PLOT_GUIDE[CONFIDENCE][1])
    assert f'the <i>one-step test</i>, at p&nbsp;&le;&nbsp;{SECOND_STEP_LEVEL:g}' in text


def test_the_guide_names_the_views_and_fit_details_sections_the_window_has(qapp):
    """A guide pointing at a view or section that is not there sends the reader looking for nothing."""
    from gui import plot_guide
    from gui.design.components import SectionHeader
    from gui.fitting_session import VIEWS, FittingSession

    text = ' '.join(html for _title, html in plot_guide.PLOT_GUIDE.values()).replace('\n', ' ')
    session = FittingSession()
    sections = [header._title for header in session._results.side.findChildren(SectionHeader)]
    session.close()
    named = re.findall(r'<b>(.*?)</b>', plot_guide._SUMMARY_HTML)

    assert all(view in VIEWS for view in re.findall(r'\(see ([^)]*)\)', text))
    assert [name for name in named if name in sections] == sections
    assert re.findall(r'Fit [A-Z]\w+', text) == []  # every view and section title is in sentence case


def test_the_fit_results_entry_names_each_mark_by_what_the_theme_does_not_change():
    """The guide is one text in both themes: the mean ± SD is the darkest mark in light and the lightest in dark."""
    from gui.plot_guide import _FIT_CURVE_HTML

    text = _FIT_CURVE_HTML.lower()
    assert not [word for word in ('dark', 'grey', 'gray', 'black', 'white', 'light') if re.search(rf'\b{word}\b', text)]
    assert 'mean &plusmn; sd' in text and 'replicates the fit used' in text
