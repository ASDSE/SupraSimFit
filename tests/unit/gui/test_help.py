"""The Help window: one non-modal window per main window, a section per view and one for the Simulation
window, opened at its section by every help control, and text that names what the app draws."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytest.importorskip('PyQt6')

GUI = Path(__file__).resolve().parents[3] / 'gui'


@pytest.fixture
def help_off_screen(monkeypatch):
    """Help windows created during the test lay out and count as shown, but never appear on screen."""
    from PyQt6.QtCore import Qt

    from gui.dialogs.help_window import HelpWindow

    create = HelpWindow.__init__

    def create_off_screen(self, *args, **kwargs):
        create(self, *args, **kwargs)
        self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)

    monkeypatch.setattr(HelpWindow, '__init__', create_off_screen)
    return HelpWindow


@pytest.fixture
def window(qapp, monkeypatch):
    from PyQt6.QtCore import Qt

    from gui.main_window import FittingMainWindow

    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    w = FittingMainWindow()
    w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    w.show()
    qapp.processEvents()
    yield w
    w.close()


def _plain(html: str) -> str:
    return re.sub(r'\s+', ' ', html)


def test_the_help_has_a_section_for_each_view_and_the_simulation_window():
    from gui.fitting_session import VIEWS
    from gui.help import SECTIONS

    assert list(SECTIONS) == [*VIEWS, 'Simulation']


def test_toolbar_help_opens_one_non_modal_window_at_the_section_of_each_view(qapp, window, help_off_screen):
    """Every view has a section of its own, so Help never shows the one a previous view left open."""
    from PyQt6.QtCore import Qt

    from gui.fitting_session import VIEWS

    for view in VIEWS:
        window.show_view(view)
        window._toolbar.help.click()
        qapp.processEvents()
        (help_window,) = window.findChildren(help_off_screen)
        assert help_window.isVisible() and help_window.windowModality() is Qt.WindowModality.NonModal
        assert help_window.current_section() == view, view
        assert help_window._title.text() == view and help_window._items[view].isChecked()


def test_the_help_menu_raises_the_same_window_at_the_view_on_screen(qapp, window, help_off_screen):
    (help_menu,) = [action.menu() for action in window.menuBar().actions() if action.text() == '&Help']
    (command,) = [action for action in help_menu.actions() if action.text() == 'SupraSimFit help']

    window.show_view('Measurements')
    command.trigger()
    window.show_view('Sensitivity')
    command.trigger()
    qapp.processEvents()

    (help_window,) = window.findChildren(help_off_screen)
    assert help_window.current_section() == 'Sensitivity'


def test_every_link_to_the_help_raises_the_one_window_at_its_section(qapp, window, help_off_screen):
    """*About this model*, *About input uncertainty*, *Reading this plot →* and the Simulation window's Help."""
    from PyQt6.QtCore import Qt

    session = window.active_session()
    window.show_view('Measurements')
    window._toolbar.help.click()
    (first,) = window.findChildren(help_off_screen)

    simulation = window._simulation_window()
    simulation.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    links = {
        'Binding model': session._binding.help_link,
        'Input uncertainty': session._uncertainty.help_link,
        'Ka confidence': session._confidence.guide_link,
        'Simulation': simulation.help_button,
    }
    for section, link in links.items():
        link.click()
        qapp.processEvents()
        assert window.findChildren(help_off_screen) == [first], section
        assert first.current_section() == section
    simulation.close()


def test_the_binding_model_section_follows_the_model_chosen(qapp, window, help_off_screen):
    """It names the model of the session on screen, and changes when that model or the session does."""
    from core.assays.registry import AssayType
    from gui.assay_descriptions import ASSAY_DESCRIPTIONS

    def heading(assay_type: AssayType) -> str:
        return ASSAY_DESCRIPTIONS[assay_type.name][1].split('</p>')[0]

    model = window.active_session().model
    model.binding.set_assay(AssayType.IDA)
    model.binding_edited()
    window.show_view('Binding model')
    window._toolbar.help.click()
    qapp.processEvents()
    (help_window,) = window.findChildren(help_off_screen)
    assert heading(AssayType.IDA) in help_window._text.text()

    model.binding.set_assay(AssayType.GDA)
    model.binding_edited()
    qapp.processEvents()
    assert heading(AssayType.GDA) in help_window._text.text()
    assert heading(AssayType.IDA) not in help_window._text.text()

    window._act_new.trigger()  # a new session opens on its own model
    qapp.processEvents()
    opened = window.active_session().model.binding.assay_type
    assert heading(opened) in help_window._text.text()


def test_each_settings_side_panel_is_explained_in_its_section(qapp, window):
    """The help of a view names its side panel and every settings group in it, as they are titled on screen."""
    from gui.design import components as C
    from gui.help import section_html

    session = window.active_session()
    assay = session.model.binding.assay_type
    for view, title in (
        ('Measurements', 'Measurement settings'),
        ('Input uncertainty', 'Effect on the fit'),
        ('Fit results', 'Fit details'),
        ('Ka confidence', 'Notes'),
        ('Sensitivity', 'Analysis settings'),
        ('Plot appearance', 'Titration plot'),
    ):
        text = _plain(section_html(view, assay))
        assert f'<i>{title}</i>' in text, (view, title)
        if view in ('Measurements', 'Input uncertainty', 'Sensitivity', 'Plot appearance'):
            groups = [h.accessibleName() for h in session._views[view].side.findChildren(C.SectionHeader)]
            assert groups
            for group in groups:
                assert f'<b>{group}</b>' in text, (view, group)


def test_the_simulation_section_explains_every_group_of_its_settings(qapp, window):
    from PyQt6.QtCore import Qt

    from gui.design import components as C
    from gui.help import section_html

    simulation = window._simulation_window()
    simulation.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    text = _plain(section_html('Simulation', window.active_session().model.binding.assay_type))
    groups = [h.accessibleName() for h in simulation.findChildren(C.SectionHeader)]
    assert '<i>Simulation settings</i>' in text and groups
    for group in groups:
        assert f'<b>{group}</b>' in text, group
    simulation.close()


def test_the_measurements_section_explains_outlier_removal_as_the_panel_offers_it():
    """The settings help the rebuild had lost: what the threshold and Min replicates do, and Apply after Apply."""
    from core.assays.registry import AssayType
    from gui.help import section_html

    text = _plain(section_html('Measurements', AssayType.IDA))
    for words in ('<i>Z-score threshold</i>', '<i>Min replicates</i>', '<i>Apply</i>', '<i>Reset all</i>', 'median'):
        assert words in text, words
    assert '0.6745' in text and '3.5' in text  # the scale of the modified z and the threshold the field opens on


def test_the_sensitivity_section_names_every_column_and_closing_row_of_the_budget():
    """The reader looks a number up by the name on screen; a column renamed in the view fails here."""
    from core.assays.registry import AssayType
    from gui.help import section_html
    from gui.sensitivity import ALL_SOURCES, BUDGET_COLUMNS, INTERACTIONS

    text = _plain(section_html('Sensitivity', AssayType.IDA))
    for name in [*BUDGET_COLUMNS[1:], INTERACTIONS, ALL_SOURCES]:
        assert f'<i>{name.split(" (")[0]}</i>' in text, name


def test_every_section_with_a_demo_plot_ends_on_its_demo_ida_example():
    """The examples are filled from DEMO, whose numbers tests/integration/test_help_demo.py works out again."""
    from core.assays.registry import AssayType
    from gui.help import DEMO, SECTIONS, section_html

    # Every view Demo IDA fills with a number to read.
    examples = ('Measurements', 'Fit results', 'Ka confidence', 'Sensitivity', 'Simulation')

    texts = {section: section_html(section, AssayType.IDA) for section in SECTIONS}
    filled = ' '.join(texts.values())
    for section, text in texts.items():
        assert ('<b>Example: Demo IDA' in text) is (section in examples), section
    for key, value in DEMO.items():
        assert value in filled, key


def test_every_section_uses_one_heading_convention():
    """A topic is a ``topic`` paragraph and a sub-head a bold paragraph, so the window gives each its type role."""
    from core.assays.registry import AssayType
    from gui.help import SECTIONS, section_html

    for assay_type in AssayType:
        for section in SECTIONS:
            assert not re.search(r'<h\d', section_html(section, assay_type)), (section, assay_type)


def test_no_help_opens_as_a_modal_dialog_with_its_own_buttons():
    """One help mechanism: no module of the interface builds a button box or a help dialog of its own."""
    offenders = [
        f'{path.relative_to(GUI.parent)}: {word}'
        for path in GUI.rglob('*.py')
        for word in ('QDialogButtonBox', 'show_help', 'show_plot_guide')
        if word in path.read_text(encoding='utf-8')
    ]
    assert not offenders
