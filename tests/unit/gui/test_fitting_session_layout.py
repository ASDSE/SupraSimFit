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


def _shown_session(qapp):
    """A session at a fixed window size, shown off-screen.

    Qt propagates a panel's layout change to the sidebar only in a shown
    window; WA_DontShowOnScreen shows it without putting it on screen.
    """
    from PyQt6.QtCore import Qt

    from gui.fitting_session import FittingSession

    session = FittingSession()
    session.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    session.resize(1400, 900)
    session.show()
    qapp.processEvents()
    return session


def _settle(qapp):
    for _ in range(5):
        qapp.processEvents()


def test_sidebar_width_follows_a_panel_growing_and_shrinking(qapp):
    """A row wider than the sidebar appearing in a panel widens the sidebar; hiding it narrows it back.

    The window keeps its size: the plot pane gives up the width, and the
    sidebar content is never wider than the sidebar shows.
    """
    from PyQt6.QtWidgets import QWidget

    session = _shown_session(qapp)
    scroll = session._sidebar_scroll
    base = scroll.sizeHint().width()
    assert scroll.width() == base
    wide = QWidget()
    wide.setMinimumWidth(base + 200)

    session._sensitivity_panel.layout().addWidget(wide)
    _settle(qapp)
    assert scroll.minimumSizeHint().width() > base + 200
    assert scroll.sizeHint().width() == scroll.minimumSizeHint().width()
    assert scroll.width() == scroll.minimumSizeHint().width()
    assert scroll.widget().width() <= scroll.viewport().width()
    assert session.width() == 1400

    wide.hide()
    _settle(qapp)
    assert scroll.minimumSizeHint().width() == base
    assert scroll.sizeHint().width() == base
    assert scroll.width() == base
    session.close()


def test_sidebar_keeps_the_width_the_user_dragged_it_to(qapp):
    """Content narrowing back returns the sidebar to the width the user dragged it to, not below."""
    from PyQt6.QtWidgets import QWidget

    session = _shown_session(qapp)
    scroll = session._sidebar_scroll
    base = scroll.width()
    scroll.parentWidget().moveSplitter(base + 100, 1)
    _settle(qapp)
    dragged = scroll.width()
    assert dragged == base + 100

    wide = QWidget()
    wide.setMinimumWidth(base + 300)
    session._sensitivity_panel.layout().addWidget(wide)
    _settle(qapp)
    assert scroll.width() == scroll.minimumSizeHint().width() > dragged

    wide.hide()
    _settle(qapp)
    assert scroll.width() == dragged
    session.close()


def _window(qapp, monkeypatch):
    """The main window at 1400×900, shown off-screen, without its update check."""
    from PyQt6.QtCore import Qt

    from gui.main_window import FittingMainWindow

    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    window = FittingMainWindow()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.resize(1400, 900)
    window.show()
    _settle(qapp)
    return window


def _drag_range(qapp, splitter, index):
    """The smallest and largest size child *index* of *splitter* can be dragged to."""
    sizes = splitter.sizes()
    total = sum(sizes)
    extremes = []
    for target in (0, total):
        splitter.setSizes([target if i == index else total - target for i in range(2)])
        _settle(qapp)
        extremes.append(splitter.sizes()[index])
    splitter.setSizes(sizes)
    _settle(qapp)
    return tuple(extremes)


def test_summary_can_be_dragged_until_a_plot_page_reaches_its_readable_floor_on_every_tab(qapp, monkeypatch):
    """At 1400×900 the summary goes from its own minimum (below about 200 px) up to where the plot page is 250 px tall.

    Only the summary's own content sets the bottom of the range. At the top, every plot tab, shown or
    hidden, keeps exactly its readable floor: no taller page content limits the drag, and no plot is
    squeezed below the floor.
    """
    from gui.fitting_session import _PLOT_PAGE_MIN_HEIGHT

    window = _window(qapp, monkeypatch)
    session = window.active_session()
    summary = session._summary_widget
    splitter = summary.parentWidget()
    tabs = session._plot_tabs
    total = sum(splitter.sizes())
    assert _PLOT_PAGE_MIN_HEIGHT == 250
    for index in range(tabs.count()):
        tabs.setCurrentIndex(index)
        _settle(qapp)
        smallest, largest = _drag_range(qapp, splitter, splitter.indexOf(summary))
        assert smallest == summary.minimumSizeHint().height() < 210, tabs.tabText(index)
        splitter.setSizes([0, total])
        _settle(qapp)
        page = tabs.currentWidget()
        assert splitter.sizes()[splitter.indexOf(summary)] == largest > 450, tabs.tabText(index)
        assert _PLOT_PAGE_MIN_HEIGHT <= page.height() <= _PLOT_PAGE_MIN_HEIGHT + 8, tabs.tabText(index)
    window.close()


def test_a_hidden_tab_page_does_not_limit_the_sidebar_or_the_window(qapp, monkeypatch):
    """A page needing 900 px of width limits the sidebar only while it is on screen."""
    from PyQt6.QtWidgets import QWidget

    window = _window(qapp, monkeypatch)
    session = window.active_session()
    sidebar = session._sidebar_scroll
    splitter = sidebar.parentWidget()
    tabs = session._plot_tabs
    _, widest_before = _drag_range(qapp, splitter, 0)

    wide = QWidget()
    wide.setMinimumWidth(900)
    session._distribution_widget.layout().addWidget(wide)
    tabs.setCurrentWidget(session._distribution_widget)
    _settle(qapp)
    _, widest_on_page = _drag_range(qapp, splitter, 0)
    tabs.setCurrentWidget(session._plot_widget)
    _settle(qapp)
    _, widest_after = _drag_range(qapp, splitter, 0)

    assert widest_on_page <= 1400 - 900
    assert widest_after == widest_before
    assert window.width() == 1400
    window.close()
