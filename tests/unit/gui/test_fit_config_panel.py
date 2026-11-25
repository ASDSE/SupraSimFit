"""The Fit Configuration panel: what reaches :class:`FitConfig`, and help that matches it.

The panel has one control, and what it decides — whether the replicates are
fitted and tested individually — has to survive a round trip in both
directions, or a session would fit something other than what the sidebar shows.

Requires a ``QApplication`` (the ``qapp`` fixture).
"""

from __future__ import annotations

import pytest

pytest.importorskip('PyQt6')

from core.pipeline.fit_pipeline import FitConfig  # noqa: E402
from core.pipeline.varpro import REPLICATE_TEST_LEVEL  # noqa: E402


def test_the_panel_round_trips_the_replicate_setting(qapp):
    from gui.widgets.fit_config_panel import FitConfigPanel

    panel = FitConfigPanel()
    assert panel.current_config() == FitConfig()

    panel.set_config(FitConfig(per_replica=False))
    assert not panel._per_replica_check.isChecked()
    assert panel.current_config().per_replica is False

    panel.set_config(FitConfig(per_replica=True))
    assert panel.current_config().per_replica is True


def test_the_help_states_the_level_and_the_replicate_count_the_test_needs(qapp):
    """Guards the help against drifting from the rule the engine applies."""
    from gui.widgets import fit_config_panel

    # The help quotes the level as a percentage, with the thin space the rest of
    # the interface uses between a number and its unit.
    level = f'{REPLICATE_TEST_LEVEL:.0%}'.replace('%', '&thinsp;%')
    html = fit_config_panel._PER_REPLICA_HELP_HTML

    assert level in html
    assert '<b>three</b>' in html  # the smallest number of replicates the test runs on
    assert 'fit of the <i>average</i>' in html
