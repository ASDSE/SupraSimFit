"""Every painted component is given the room its content needs, and no plot header cuts its text (DESIGN.md §6, §7).

The sweep walks the real window with Demo IDA loaded — every view, its sections open, the
Settings, Simulation and Help windows — and holds it to the rules of :mod:`tests.unit.gui.layout_rules`.
The fitted state, whose plot headers carry a description, is swept in
``tests/integration/test_layout.py``. The component tests pin the two layouts the rules
rest on: a segmented control beside a stretch, and a plot header at a width that cannot
hold its legend on its title line.
"""

from __future__ import annotations

import pytest

pytest.importorskip('PyQt6')

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtGui import QFontMetrics  # noqa: E402
from PyQt6.QtWidgets import QWidget  # noqa: E402

from gui.design import components as C  # noqa: E402
from gui.design.appearance import theme  # noqa: E402
from gui.design.tokens import font  # noqa: E402
from tests.unit.gui import layout_rules  # noqa: E402
from tests.unit.gui.menus import settle, sweep  # noqa: E402


@pytest.fixture
def window(qapp, monkeypatch):
    from gui.main_window import FittingMainWindow

    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    made = FittingMainWindow()
    made.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    made.resize(1440, 900)
    made.show()
    settle(qapp)
    yield made
    made.close()


def _host(qapp, layout, width: int) -> QWidget:
    host = QWidget()
    host.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    host.setLayout(layout)
    host.resize(width, 200)
    host.show()
    settle(qapp)
    return host


def test_every_painted_component_of_the_loaded_demo_is_given_the_room_its_content_needs(qapp, window):
    from core.pipeline.sensitivity import SensitivityMode

    session = window.active_session()
    assert session.set_up_demo_ida()
    session.model.analysis.mode = SensitivityMode.HEATMAP  # the heatmap's axes, spans and grid
    session.model.analysis_edited()
    settle(qapp)

    seen = sweep(qapp, window, check=layout_rules.check)

    assert {'Measurements', 'Sensitivity', 'Plot appearance', 'Settings', 'Simulation'} <= set(seen)
    assert {where: found for where, found in seen.items() if found} == {}


def test_the_loaded_demo_at_the_narrowest_window_cuts_no_text_and_gives_every_component_its_room(qapp, window):
    """A window made as narrow as it goes gives each view its least width: a line of text there wraps or gives way to
    an ellipsis rather than being cut off."""
    session = window.active_session()
    assert session.set_up_demo_ida()
    window.resize(800, 800)  # below the window's least width, which it keeps
    settle(qapp)
    assert window.width() == window.minimumSizeHint().width()

    seen = sweep(qapp, window, check=layout_rules.check)

    assert {where: found for where, found in seen.items() if found} == {}


def test_an_empty_session_at_the_narrowest_window_cuts_no_text_and_gives_every_component_its_room(qapp, window):
    """Every view's empty state — its title, sentence and two commands — stands whole in the least window."""
    window.resize(800, 800)
    settle(qapp)

    seen = sweep(qapp, window, check=layout_rules.check)

    assert {where: found for where, found in seen.items() if found} == {}


def test_a_segmented_control_beside_a_stretch_shows_each_option_whole(qapp):
    options = ['Fixed', 'σ', 'Range']
    control = C.Segmented(theme(), options)
    host = _host(qapp, C.hbox(control, None), 480)

    # The segments share the width equally, and the chosen one is set in body-strong.
    widest = max(QFontMetrics(font('body-strong')).horizontalAdvance(o) for o in options)
    assert control.width() >= len(options) * widest
    host.close()


def test_a_plot_header_too_narrow_for_its_legend_puts_the_legend_under_its_title_line(qapp):
    t = theme()
    replicates = [('cross', 'A switched off', 0), *(('dots', c, i) for i, c in enumerate('BCDEFGH', 1))]
    legend = C.LegendRow(t, [*replicates, ('mean', 'Mean ± SD'), ('line', 'Fit')])  # Fit results' legend of the demo
    tools = [C.tool_button(t, None, 'scatter', menu=True), 1, C.tool_button(t, None, 'image')]
    header = C.PlotHeader(t, 'Titration', legend, tools, 'curve drawn at the fitted input shifts')
    host = _host(qapp, C.vbox(header, None), 838)

    assert header.description.text() == header.description.full_text
    assert header.legend_wrapped()
    assert legend.geometry().right() <= header.width()
    assert legend.geometry().top() >= header.description.geometry().bottom()

    host.resize(1400, 200)
    settle(qapp)
    assert not header.legend_wrapped()
    assert abs(legend.geometry().center().y() - header.description.geometry().center().y()) <= 1
    host.close()
