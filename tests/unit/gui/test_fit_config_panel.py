"""The Fit Configuration panel: what reaches :class:`FitConfig`, and help that matches it.

Pins two things a user relies on:

- the seed the fit runs with — the fixed one when the box is ticked, and none
  otherwise, which leaves the session to draw and record one, so a fit is
  repeatable rather than silently different each run;
- the Min R² help quotes the floor the panel actually starts from.

Requires a ``QApplication`` (the ``qapp`` fixture).
"""

from __future__ import annotations

import pytest

pytest.importorskip('PyQt6')

from core.pipeline.fit_pipeline import FitConfig  # noqa: E402


def test_the_seed_reaches_the_config_only_when_it_is_fixed(qapp):
    """Unticked, nothing is imposed; ticked, the entered seed is what the fit runs with."""
    from gui.widgets.fit_config_panel import FitConfigPanel

    panel = FitConfigPanel()
    assert panel.current_config().seed is None
    assert not panel._seed_spin.isEnabled()

    panel._seed_check.setChecked(True)
    panel._seed_spin.setValue(4321)
    assert panel._seed_spin.isEnabled()
    assert panel.current_config().seed == 4321

    panel._seed_check.setChecked(False)
    assert panel.current_config().seed is None


def test_a_config_carrying_a_seed_is_shown_as_fixed(qapp):
    """Showing a config with a seed as an open draw would misreport the fit it describes."""
    from gui.widgets.fit_config_panel import FitConfigPanel

    panel = FitConfigPanel()

    panel.set_config(FitConfig(seed=77))
    assert panel._seed_check.isChecked() and panel._seed_spin.value() == 77
    assert panel.current_config().seed == 77

    panel.set_config(FitConfig())
    assert not panel._seed_check.isChecked()
    assert panel.current_config().seed is None


def test_the_min_r2_help_quotes_the_floor_the_panel_starts_from(qapp):
    """Guards the help against drifting from the default it explains."""
    from gui.widgets import fit_config_panel
    from gui.widgets.fit_config_panel import FitConfigPanel

    default = FitConfig().min_r_squared
    panel = FitConfigPanel()

    assert panel._r2_spin.value() == pytest.approx(default)
    assert panel.current_config().min_r_squared == pytest.approx(default)
    assert f'<b>{default}</b> (default)' in fit_config_panel._R2_HELP_HTML
