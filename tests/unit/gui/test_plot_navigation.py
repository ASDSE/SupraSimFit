"""Zoom and pan of the interactive plots, and the way back (DESIGN.md §7).

A titration plot frames what it is given: new data, another display unit or new fits
put it back on auto-range, so data loaded after a zoom are in view. A theme change or
another plot appearance draws the same data again and keeps the user's zoom. A wheel
without ⌘ (Ctrl elsewhere) passes on to the page that holds the plot; with it, or a
pinch, it zooms. A double-click or *Reset view* puts the plot back, and the tool is
enabled only while the view is off auto-range.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip('PyQt6')

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QNativeGestureEvent, QPointingDevice, QWheelEvent  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QScrollArea, QWidget  # noqa: E402

from gui.design import components as C  # noqa: E402
from gui.design.appearance import appearance  # noqa: E402
from gui.views.titration import TitrationData, TitrationPlot  # noqa: E402
from tests.unit.gui.test_results import four_replicates  # noqa: E402

NONE = Qt.KeyboardModifier.NoModifier
ZOOM = Qt.KeyboardModifier.ControlModifier  # ⌘ on macOS


def _data(top: float = 1e-5, level: float = 1e4) -> TitrationData:
    x = np.linspace(0.0, top, 8)
    signals = np.stack([level * (1 + 0.1 * i) * x / (x + top / 3) for i in range(2)])
    return TitrationData(x, signals, [True, True], 'Guest', replicate_ids=['0', '1'])


@pytest.fixture
def plot(qapp):
    made = TitrationPlot()
    made.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    made.resize(600, 400)
    made.show()
    qapp.processEvents()
    yield made
    made.close()


def _view_box(plot: TitrationPlot):
    return plot.pw.getPlotItem().getViewBox()


def _range(plot: TitrationPlot) -> list[list[float]]:
    """The x and y ranges the plot shows once drawn: pyqtgraph applies auto-range as events are delivered."""
    QApplication.processEvents()
    return _view_box(plot).viewRange()


def _shown(plot: TitrationPlot) -> list[float]:
    """The x and y ranges the plot shows, as one flat list."""
    return [v for side in _range(plot) for v in side]


def _wheel(pw, modifiers=NONE, notches: int = 1) -> QWheelEvent:
    """*notches* turns of the wheel (down where positive) over the middle of plot widget *pw*, delivered as the
    platform's own are: to the widget under the pointer, then — while none accepts it — to each of its parents in
    turn, as ``QApplication::notify`` hands on a wheel event from the platform. A synthetic event Qt delivers to its
    receiver only, so the test hands it on itself. Returns the event the plot itself was given."""
    QApplication.processEvents()
    vp = pw.viewport()
    centre = QPoint(vp.width() // 2, vp.height() // 2)
    first = None
    widget = vp
    while widget is not None:
        at = QPointF(widget.mapFrom(vp, centre))
        event = QWheelEvent(
            at,
            QPointF(vp.mapToGlobal(centre)),
            QPoint(0, 0),
            QPoint(0, -120 * notches),
            Qt.MouseButton.NoButton,
            modifiers,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        handled = QApplication.sendEvent(widget, event)
        first = first or event
        if handled and event.isAccepted():
            break
        widget = None if widget.isWindow() else widget.parentWidget()
    return first


def _x_in_view(plot: TitrationPlot, data: TitrationData, unit: str = 'µM') -> bool:
    scale = {'nM': 1e9, 'µM': 1e6, 'mM': 1e3, 'M': 1.0}[unit]
    lo, hi = _range(plot)[0]
    return lo <= data.x_molar.min() * scale and data.x_molar.max() * scale <= hi


def test_new_data_after_a_zoom_are_in_view(plot):
    first, other = _data(1e-5), _data(4e-4, level=3e5)
    plot.show_data(first, 'µM')
    _wheel(plot.pw, ZOOM, notches=3)
    assert _view_box(plot).autoRangeEnabled() == [False, False]
    assert plot.navigation.tool.isEnabled()

    plot.show_data(other, 'µM')

    assert _view_box(plot).autoRangeEnabled() == [True, True]
    assert _x_in_view(plot, other)
    assert not plot.navigation.tool.isEnabled()


def test_another_display_unit_frames_the_plot_again(plot):
    data = _data()
    plot.show_data(data, 'µM')
    _wheel(plot.pw, ZOOM, notches=3)

    plot.show_data(data, 'nM')

    assert _view_box(plot).autoRangeEnabled() == [True, True]
    assert _x_in_view(plot, data, 'nM')


def test_the_same_data_shown_again_keep_the_zoom(plot):
    """A refresh that draws what is already drawn, as a finished Ka profile does, keeps the view the user chose."""
    plot.show_data(_data(), 'µM')
    _wheel(plot.pw, ZOOM, notches=3)
    zoomed = _shown(plot)

    plot.show_data(_data(), 'µM')

    assert _shown(plot) == pytest.approx(zoomed)
    assert plot.navigation.tool.isEnabled()


def test_reset_view_restores_auto_range_and_disables_itself(plot):
    plot.show_data(_data(), 'µM')
    framed = _shown(plot)
    assert not plot.navigation.tool.isEnabled()
    _wheel(plot.pw, ZOOM, notches=3)
    assert _shown(plot) != pytest.approx(framed)

    plot.navigation.tool.click()

    assert _view_box(plot).autoRangeEnabled() == [True, True]
    assert _shown(plot) == pytest.approx(framed)
    assert not plot.navigation.tool.isEnabled()


def test_a_double_click_resets_the_view(plot):
    plot.show_data(_data(), 'µM')
    framed = _shown(plot)
    _wheel(plot.pw, ZOOM, notches=3)

    vp = plot.pw.viewport()
    QTest.mouseDClick(vp, Qt.MouseButton.LeftButton, NONE, QPoint(vp.width() // 2, vp.height() // 2))

    assert _shown(plot) == pytest.approx(framed)
    assert not plot.navigation.tool.isEnabled()


def test_a_plain_wheel_over_the_plot_scrolls_the_page_that_holds_it(qapp):
    """A trackpad scroll meant for the page passes over the plot: the page scrolls and the plot keeps auto-range."""
    plot = TitrationPlot()
    plot.setMinimumHeight(400)
    page = QWidget()
    page.setLayout(C.vbox(plot, None, spacing=0))
    page.setMinimumHeight(1600)
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(page)
    area.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    area.resize(600, 500)
    area.show()
    qapp.processEvents()
    plot.show_data(_data(), 'µM')
    framed = _shown(plot)
    bar = area.verticalScrollBar()
    assert bar.value() == 0

    event = _wheel(plot.pw, NONE)

    assert not event.isAccepted()
    assert bar.value() > 0
    assert _view_box(plot).autoRangeEnabled() == [True, True]
    assert _shown(plot) == pytest.approx(framed)
    assert not plot.navigation.tool.isEnabled()
    area.close()


def test_the_wheel_with_the_zoom_modifier_zooms(plot):
    plot.show_data(_data(), 'µM')
    (x_lo, x_hi), _y = _range(plot)

    event = _wheel(plot.pw, ZOOM, notches=-1)

    assert event.isAccepted()
    (lo, hi), _y = _range(plot)
    assert hi - lo < x_hi - x_lo
    assert plot.navigation.tool.isEnabled()


def test_a_pinch_zooms(plot):
    plot.show_data(_data(), 'µM')
    (x_lo, x_hi), _y = _range(plot)
    vp = plot.pw.viewport()
    centre = QPointF(vp.width() / 2, vp.height() / 2)
    pinch = QNativeGestureEvent(
        Qt.NativeGestureType.ZoomNativeGesture,
        QPointingDevice.primaryPointingDevice(),
        2,
        centre,
        centre,
        QPointF(vp.mapToGlobal(centre.toPoint())),
        0.5,
        QPointF(),
    )
    assert pinch.type() == QEvent.Type.NativeGesture

    QApplication.sendEvent(vp, pinch)

    (lo, hi), _y = _range(plot)
    assert hi - lo == pytest.approx((x_hi - x_lo) / 1.5)
    assert plot.navigation.tool.isEnabled()


def test_a_theme_change_keeps_the_zoom(plot):
    plot.show_data(_data(), 'µM')
    _wheel(plot.pw, ZOOM, notches=3)
    zoomed = _shown(plot)
    try:
        appearance().set_mode('dark')
        QApplication.processEvents()
        assert _shown(plot) == pytest.approx(zoomed)
        assert plot.navigation.tool.isEnabled()
    finally:
        appearance().set_mode('light')
    assert _shown(plot) == pytest.approx(zoomed)


def test_another_plot_text_size_keeps_the_zoom(plot):
    """Another text size styles the axes afresh on a new plot widget; the view stays where the user put it."""
    from dataclasses import replace

    plot.show_data(_data(), 'µM')
    _wheel(plot.pw, ZOOM, notches=3)
    zoomed = _shown(plot)
    old = plot.pw

    plot.set_plot_appearance(replace(plot.plot_appearance, text_size='large'))

    assert plot.pw is not old
    assert _shown(plot) == pytest.approx(zoomed)
    assert plot.navigation.tool.isEnabled()


def test_data_loaded_after_a_zoom_of_the_empty_measurements_plot_are_in_view(qapp):
    """The empty Measurements plot zoomed by a notch, then data loaded: the data are in view."""
    from gui.fitting_session import FittingSession

    session = FittingSession()
    session.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    session.resize(1200, 800)
    session.show()
    session.show_view('Measurements')
    qapp.processEvents()
    plot = session._measurements.plot
    _wheel(plot.pw, ZOOM)
    assert _view_box(plot).autoRangeEnabled() == [False, False]

    ms = four_replicates()
    session.model.load(ms, None)
    qapp.processEvents()

    assert plot.data is not None
    assert _x_in_view(plot, plot.data, session.model.settings.display_unit)
    assert not plot.navigation.tool.isEnabled()
    session.close()


@pytest.mark.parametrize('view', ['Measurements', 'Fit results', 'Plot appearance'])
def test_every_titration_header_carries_the_reset_view_tool(qapp, view):
    from gui.fitting_session import FittingSession

    session = FittingSession()
    page = {
        'Measurements': session._measurements,
        'Fit results': session._results,
        'Plot appearance': session._appearance,
    }[view]
    tool = page.plot.navigation.tool
    assert page.canvas.isAncestorOf(tool)
    assert tool.accessibleName() == 'Reset the view of the titration plot'
    session.close()


def test_the_tool_looks_disabled_while_the_view_is_on_auto_range(plot):
    """Disabled, the tool draws its icon quieter than enabled, so its state shows."""
    tool = plot.navigation.tool
    tool.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    tool.show()
    disabled = tool.grab().toImage()
    _wheel(plot.pw, ZOOM, notches=-1)
    assert tool.isEnabled()
    assert tool.grab().toImage() != disabled
