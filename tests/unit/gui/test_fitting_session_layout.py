"""Regression guard: the plot widget must stay embedded after any import.

A previous EnSight code path ran a modal ``QInputDialog`` mid-load, which
detached the plot from its tab container (it overlapped the sidebar and
floated above the Fit Curve tab). The fix removed the mid-load modal. This
test asserts the plot widget remains embedded — the first page of the plot
tab widget, never a top-level window — across an EnSight import and a
subsequent channel switch.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip('PyQt6')

ENSIGHT_FIXTURE = Path(__file__).parent.parent.parent / 'data' / 'ensight' / 'tryptamine.csv'


def _assert_embedded(session):
    pw = session._plot_widget
    tabs = session._plot_tabs
    # The plot is the first page of the flat plot-tab widget, never detached
    # into a top-level window.
    assert tabs.indexOf(pw) == 0
    assert not pw.isWindow()


def test_plot_stays_embedded_through_ensight_load_and_switch(qapp):
    if not ENSIGHT_FIXTURE.exists():
        pytest.skip('EnSight fixture missing')
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


def test_sidebar_has_no_hard_maxwidth_cap(qapp):
    """The sidebar must be freely widenable — no finite max-width cap.

    A previous `setMaximumWidth(380)` clamped the sidebar to 300–380px, so
    after import long filenames/channel labels cropped with no way to widen.
    """
    from PyQt6.QtWidgets import QWIDGETSIZE_MAX

    from gui.fitting_session import FittingSession

    session = FittingSession()
    scroll = session._sidebar_scroll
    # No finite upper bound: maximumWidth stays at Qt's sentinel max.
    assert scroll.maximumWidth() == QWIDGETSIZE_MAX


def test_sidebar_reserves_content_width_so_it_never_clips(qapp):
    """The sidebar must advertise at least its content's width to the splitter.

    A plain ``QScrollArea`` reports a near-zero width hint (≈90px) regardless of
    its content (~336px here), so a ``QSplitter`` shrinks it until the content
    clips at the plot boundary. ``_SidebarScrollArea`` propagates the content's
    width (plus the vertical scrollbar) as its own minimum, so the splitter
    honors it and the plot pane yields instead — the content is structurally
    unclippable, whatever the panels need.
    """
    from gui.fitting_session import FittingSession

    session = FittingSession()
    scroll = session._sidebar_scroll
    content = scroll.widget()
    scrollbar = scroll.verticalScrollBar().sizeHint().width()
    assert scroll.minimumSizeHint().width() >= content.minimumSizeHint().width() + scrollbar
