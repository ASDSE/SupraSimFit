"""Help ▸ Reading the plots: each entry point opens the window's one non-modal guide at the right section.

Also guards the Identifiability example: its numbers are recomputed from the demo
data, so the guide cannot quietly drift away from what the app produces.
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


def test_the_guide_lists_a_section_named_after_each_plot_tab_and_the_summary_panel(qapp, guide_off_screen):
    """Section titles follow the tab labels, so a renamed tab cannot leave its guide section behind."""
    from gui.fitting_session import FittingSession
    from gui.plot_guide import PLOT_GUIDE

    tabs = FittingSession()._plot_tabs
    guide = guide_off_screen()
    listed = [guide._nav.item(row).text() for row in range(guide._nav.count())]

    assert listed == [tabs.tabText(i) for i in range(tabs.count())] + ['Summary panel']
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


def test_tab_bar_button_opens_the_section_of_the_tab_on_screen(qapp, guide_off_screen):
    """The "?" on the plot tab bar opens the guide at the current tab's section, for every tab."""
    from PyQt6.QtCore import Qt

    from gui import plot_guide
    from gui.fitting_session import FittingSession

    session = FittingSession()
    session.resize(1200, 800)
    _show(qapp, session)
    tabs = session._plot_tabs
    button = tabs.cornerWidget(Qt.Corner.TopRightCorner)
    assert button.isVisible() and '?' in button.text()

    expected = {
        session._sensitivity_widget: plot_guide.SENSITIVITY,
        session._plot_widget: plot_guide.FIT_CURVE,
        session._identifiability_widget: plot_guide.IDENTIFIABILITY,
        session._distribution_widget: plot_guide.DISTRIBUTIONS,
    }
    for page, key in expected.items():
        tabs.setCurrentWidget(page)
        button.click()
        qapp.processEvents()
        (guide,) = session.findChildren(guide_off_screen)
        assert guide.isVisible()
        assert guide.current_section() == key
        assert guide._text.toPlainText().startswith(plot_guide.PLOT_GUIDE[key][0])


def test_the_identifiability_example_still_describes_the_demo_data():
    """Recomputes the guide's quoted profile numbers from the demo data it names.

    The example invites the user to reproduce it, so every figure in it — the best
    fit and its R², the confidence interval and how far it reaches, the cut-off, and
    the R² a doubled and a halved Ka still reach — is recomputed here and looked for
    in the text. A change in the profile that the guide does not follow fails this.
    """
    import numpy as np

    from core.assays import IDAAssay
    from core.data_processing.measurement_set import MeasurementSet
    from core.data_processing.preprocessing import get_step
    from core.io import load_measurements
    from core.pipeline import profile as profile_module
    from core.pipeline.fit_pipeline import FitConfig, _resolve_bounds
    from core.pipeline.profile import fit_profile
    from core.units import Q_
    from gui.plot_guide import IDENTIFIABILITY, PLOT_GUIDE

    # Demo IDA as the guide's note describes it: the bundled data through Outlier
    # Removal at its defaults, the conditions the Demo IDA button sets, averaged.
    ms = MeasurementSet.from_dataframe(load_measurements(str(_IDA_DATA)))
    get_step('zscore_replica_filter', {'threshold': 3.5, 'min_replicas': 3})(ms)
    conditions = {'h0': Q_(4.3e-6, 'M'), 'd0': Q_(6e-6, 'M'), 'Ka_dye': Q_(16.8e6, '1/M')}
    profile = fit_profile(ms, IDAAssay, conditions, FitConfig(per_replica=False))

    # The guide quotes the R² at exactly half and twice the best Ka, which the
    # nearest drawn point misses by enough to move the fourth decimal.
    assay = ms.to_assay(IDAAssay, conditions=conditions, use_average=True)
    y_avg = ms.average_signal(active_only=True)[np.newaxis, :]
    _, _, ssr_at = profile_module._profile_function(assay, _resolve_bounds(assay, None), y_avg)
    ss_tot = float(profile_module._ss_tot(y_avg)[0])

    def at(factor: float) -> float:
        """The best R² the profile reaches at *factor* times the best Ka."""
        return 1.0 - float(ssr_at(profile.best_ka * factor)[0]) / ss_tot

    lo, hi = profile.ci
    text = re.sub(r'\s+', ' ', PLOT_GUIDE[IDENTIFIABILITY][1])
    quoted = [
        f'Best fit {profile.best_ka / 1e8:.2f}&times;10<sup>8</sup>',
        f'(R&sup2; {profile.best_r2:.4f})',
        f'CI {lo / 1e8:.1f}&ndash;{hi / 1e8:.1f}&times;10<sup>8</sup>',
        f'(&minus;{round(100 * (1 - lo / profile.best_ka))}&thinsp;% / +{round(100 * (hi / profile.best_ka - 1))}',
        f'cut-off {profile.r2_threshold:.4f}.',
        f'is {at(2.0):.4f} at twice the best K<sub>a</sub> and {at(0.5):.4f} at half',
    ]
    for phrase in quoted:
        assert phrase in text
