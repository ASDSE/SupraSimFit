"""Regression guard: the plot widget must stay embedded after any import.

A previous EnSight code path ran a modal ``QInputDialog`` mid-load, which
detached the plot from its ``QStackedWidget`` (it overlapped the sidebar and
floated above the Fit Curve tab). The fix removed the mid-load modal. This
test asserts the plot widget remains embedded — index 0 of the stack, never a
top-level window — across an EnSight import and a subsequent channel switch.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

ENSIGHT_FIXTURE = (
    Path(__file__).parent.parent.parent / "data" / "ensight" / "tryptamine.csv"
)


@pytest.fixture(scope="module")
def qapp():
    import sys

    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication(sys.argv)


def _assert_embedded(session):
    pw = session._plot_widget
    stack = session._plot_stack
    assert stack.indexOf(pw) == 0
    assert not pw.isWindow()
    assert pw.parent() is stack


def test_plot_stays_embedded_through_ensight_load_and_switch(qapp):
    if not ENSIGHT_FIXTURE.exists():
        pytest.skip("EnSight fixture missing")
    from gui.fitting_session import FittingSession

    session = FittingSession()
    session.resize(1200, 800)
    _assert_embedded(session)

    session._data_panel.load_file(str(ENSIGHT_FIXTURE))
    qapp.processEvents()
    _assert_embedded(session)

    # Channel switch must not detach the plot either.
    session._data_panel._channel_combo.setCurrentIndex(2)
    qapp.processEvents()
    _assert_embedded(session)
