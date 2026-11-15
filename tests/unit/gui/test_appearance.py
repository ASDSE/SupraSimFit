"""The app's Light / Dark choice reaches every surface Qt draws, whatever the operating system shows.

Qt draws the native surfaces (file dialogs, window frames, the menu bar) from the colour
scheme it is told about. Only a platform with a colour scheme of its own can show the app
in the other one, so the test of the scheme runs on macOS (``cocoa``); under ``offscreen``
it is skipped. A message box reads in either mode, its buttons and its icon.
"""

from __future__ import annotations

from collections import Counter

import pytest

pytest.importorskip('PyQt6')

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtGui import QColor  # noqa: E402
from PyQt6.QtWidgets import QMessageBox  # noqa: E402

from gui.design.appearance import appearance  # noqa: E402

SCHEMES = {'light': Qt.ColorScheme.Light, 'dark': Qt.ColorScheme.Dark}


def _luminance(colour: QColor) -> float:
    def channel(v: int) -> float:
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(colour.red()) + 0.7152 * channel(colour.green()) + 0.0722 * channel(colour.blue())


def _contrast(a: QColor, b: QColor) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.fixture
def restore_mode(qapp):
    before = appearance().mode
    yield
    appearance().set_mode(before)


@pytest.fixture
def fusion(qapp):
    """The style the app ships with (``start_application``), put back as the test found it."""
    from gui.design.appearance import DesignStyle

    before = qapp.style().name()
    qapp.setStyle(DesignStyle())
    yield
    qapp.setStyle(before)


def test_the_mode_chosen_is_the_scheme_qt_draws_in_against_the_operating_system(qapp, restore_mode):
    """In the scheme opposite the OS's, Qt reports the app's scheme, which its native surfaces are drawn in."""
    if qapp.platformName() != 'cocoa':
        pytest.skip('only macOS (cocoa) has a colour scheme of its own to differ from; offscreen has none')
    appearance().set_mode('system')
    qapp.processEvents()
    os_dark = qapp.styleHints().colorScheme() == Qt.ColorScheme.Dark
    other = 'light' if os_dark else 'dark'

    appearance().set_mode(other)
    qapp.processEvents()

    assert qapp.styleHints().colorScheme() == SCHEMES[other]

    appearance().set_mode('system')
    qapp.processEvents()
    assert (qapp.styleHints().colorScheme() == Qt.ColorScheme.Dark) == os_dark
    assert appearance().theme.dark == os_dark


@pytest.mark.parametrize('mode', ['light', 'dark'])
def test_a_message_box_reads_in_either_mode(qapp, restore_mode, fusion, mode):
    """Each button's text stands out from its face by at least 4.5:1, measured on the drawn box."""
    appearance().set_mode(mode)
    box = QMessageBox(QMessageBox.Icon.Question, 'Discard', 'Discard the results?')
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    box.setDefaultButton(QMessageBox.StandardButton.Yes)
    box.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    box.show()
    qapp.processEvents()
    try:
        image = box.grab().toImage()
        ratio = image.devicePixelRatio()
        for button in box.buttons():
            palette = button.palette()
            assert _contrast(palette.buttonText().color(), palette.button().color()) >= 4.5, button.text()
            corner = button.mapTo(box, button.rect().topLeft())
            pixels = [
                image.pixelColor(int(x * ratio), int(y * ratio))
                for x in range(corner.x() + 6, corner.x() + button.width() - 6)
                for y in range(corner.y() + 5, corner.y() + button.height() - 5)
            ]
            face = QColor(Counter(p.name() for p in pixels).most_common(1)[0][0])
            text = max(pixels, key=lambda p: _contrast(p, face))
            assert _contrast(text, face) >= 4.5, (button.text(), text.name(), face.name())
    finally:
        box.close()


#: The icons of a message box: what a box asks, tells, warns of, or says went wrong.
ICONS = (QMessageBox.Icon.Question, QMessageBox.Icon.Information, QMessageBox.Icon.Warning, QMessageBox.Icon.Critical)


@pytest.mark.parametrize('mode', ['light', 'dark'])
def test_a_message_box_icon_stands_out_from_the_box_in_either_mode(qapp, restore_mode, fusion, mode):
    """WCAG 2 non-text contrast: each icon's mark stands out from the box it is drawn on by at least 3 : 1."""
    appearance().set_mode(mode)
    for kind in ICONS:
        box = QMessageBox(kind, 'Title', 'Text')
        image = box.iconPixmap().toImage()
        ground = box.palette().window().color()
        marks = [image.pixelColor(x, y) for x in range(image.width()) for y in range(image.height())]
        marks = [p for p in marks if p.alpha() == 255]
        assert marks, f'{kind.name}: the icon draws no solid mark'
        best = max(_contrast(p, ground) for p in marks)
        assert best >= 3.0, f'{kind.name} in {mode}: its mark stands out by {best:.2f} : 1'
        box.deleteLater()
