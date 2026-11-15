"""Every menu is laid out from what its rows hold (DESIGN.md §6, *Menu* and *Choice menu*).

The sweep opens every menu the real window offers with Demo IDA loaded — every view, its
sections open, the Settings and Simulation windows — and holds each to the rules of
:mod:`tests.unit.gui.menus`. The fitted state, with the menus only a fit or a sensitivity
run shows, is swept in ``tests/integration/test_menus.py``. The component tests pin
where a menu opens and how it scrolls when its window is short.
"""

from __future__ import annotations

import pytest

pytest.importorskip('PyQt6')

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QWidget  # noqa: E402

from gui.design import components as C  # noqa: E402
from gui.design.appearance import theme  # noqa: E402
from tests.unit.gui.menus import open_menu, problems, settle, sweep  # noqa: E402

#: The menus a sweep must have opened, by where they open and their control's name.
NAMED = (
    'Measurements: Display unit of the titration plot',
    'Measurements: Load data',
    'Measurements: Export',
    'Measurements: Open sessions',
    'Binding model: Category of the binding model',
    'Binding model: Binding model',
    'Binding model: Unit of the titrant stock concentration',
    'Plot appearance: Colour of the replicate points',
    'Plot appearance: Colour of the fitted curve',
    'Sensitivity: X axis of the heatmap',
    'Sensitivity: Grid of the heatmap, cells per axis',
    'Settings: Processor cores',
    'Simulation: Binding model',
    'Simulation: Unit of the concentrations',
)


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


def test_every_menu_of_the_loaded_demo_fits_its_rows_and_its_window_and_marks_its_choice(qapp, window):
    from core.pipeline.sensitivity import SensitivityMode
    from tests.unit.gui.session_setup import state_dilution

    session = window.active_session()
    assert session.set_up_demo_ida()
    state_dilution(session, 1e-3)  # the titrant stock and its unit menu
    session.model.analysis.mode = SensitivityMode.HEATMAP  # the axes, spans and grid
    session.model.analysis_edited()
    settle(qapp)

    seen = sweep(qapp, window)

    assert not [name for name in NAMED if name not in seen], sorted(seen)
    assert {name: found for name, found in seen.items() if found} == {}


def _host(qapp, height: int) -> QWidget:
    host = QWidget()
    host.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    host.resize(480, height)
    host.show()
    settle(qapp)
    return host


def test_a_choice_menu_longer_than_its_window_is_capped_scrolls_to_every_row_and_opens_on_its_current_one(qapp):
    host = _host(qapp, 300)
    options = [f'Choice {i}' for i in range(40)]
    dropdown = C.Dropdown(theme(), options, current=25)
    dropdown.setParent(host)
    dropdown.move(16, 16)
    dropdown.show()

    menu = open_menu(qapp, dropdown)
    card = menu._card()
    assert problems(dropdown, menu) == []
    visible = [row.action.text() for row in menu.menu_rows() if card.contains(row.rect)]
    assert 'Choice 25' in visible and len(visible) < len(options)

    for _ in range(len(options) - 1 - 25):
        QTest.keyClick(menu, Qt.Key.Key_Down)
    last = menu.menu_rows()[-1]
    assert menu.hover == len(options) - 1 and card.contains(last.rect)
    host.close()


def test_a_menu_with_no_room_below_its_anchor_opens_above_it(qapp):
    host = _host(qapp, 400)
    dropdown = C.Dropdown(theme(), ['nM', 'µM', 'mM', 'M'], current=1)
    dropdown.setParent(host)
    dropdown.move(16, 400 - 16 - dropdown.height())
    dropdown.show()

    menu = open_menu(qapp, dropdown)
    card = menu._card().translated(menu.pos().x(), menu.pos().y())

    assert problems(dropdown, menu) == []
    assert card.bottom() <= dropdown.geometry().top()
    assert [row.action.text() for row in menu.menu_rows()] == ['nM', 'µM', 'mM', 'M']
    host.close()


def test_a_dropdown_shows_its_current_option_on_its_face_and_offers_it_in_its_menu_as_written(qapp):
    host = _host(qapp, 400)
    options = ['K<sub>a</sub> dye', '[Host]<sub>0</sub>']
    dropdown = C.Dropdown(theme(), options, current=1)
    dropdown.setParent(host)
    dropdown.show()
    chosen: list[int] = []
    dropdown.chosen.connect(chosen.append)

    assert dropdown.text == '[Host]<sub>0</sub>'
    assert dropdown.width() >= C.rich_width(options[0], 'number')
    menu = open_menu(qapp, dropdown)
    rows = menu.menu_rows()
    assert [row.action.text() for row in rows] == ['Ka dye', '[Host]0']
    assert [row.action.isChecked() for row in rows] == [False, True]

    menu._activate(0)
    assert chosen == [0]
    host.close()
