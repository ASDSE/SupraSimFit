"""The render harness draws the running app, so a visual check sees what the user sees.

The fast layer renders Demo IDA as loaded, before its input-aware fit; the fitted state
is rendered in ``tests/integration/test_render_harness.py``.
"""

from __future__ import annotations

import pytest

pytest.importorskip('PyQt6')

MENU = 'Display unit of the titration plot'


def test_render_returns_window_image(qapp):
    from docs.design.render import render

    image = render('Measurements', state='demo-loaded')

    assert (image.width(), image.height()) == (1440, 900)
    colours = {image.pixel(x, y) for x in range(0, 1440, 16) for y in range(0, 900, 16)}
    assert len(colours) > 1


def test_an_opened_menu_is_in_the_image(qapp):
    from docs.design.render import render

    closed = render('Measurements', state='demo-loaded')
    opened = render('Measurements', state='demo-loaded', open_menu=MENU)

    assert opened != closed


def test_an_unknown_control_is_refused(qapp):
    from docs.design.render import render

    with pytest.raises(ValueError, match='0 controls on screen'):
        render('Measurements', state='empty', open_menu='No such control')


def test_a_render_is_drawn_in_the_style_the_app_ships_with(qapp):
    """The harness sets the application up as launch() does, whatever style the process had."""
    from PyQt6.QtWidgets import QStyleFactory

    from docs.design.render import render

    other = next(name for name in QStyleFactory.keys() if name.lower() != 'fusion')
    before = qapp.style().name()
    qapp.setStyle(other)
    try:
        render('Measurements', state='empty')
        # The theme's style sheet wraps the style; without it the style reads its own name.
        sheet = qapp.styleSheet()
        qapp.setStyleSheet('')
        style = qapp.style().name()
        qapp.setStyleSheet(sheet)
    finally:
        qapp.setStyle(before)

    assert style.lower() == 'fusion'


def test_a_pointer_with_no_plot_on_screen_is_refused(qapp):
    from docs.design.render import render

    with pytest.raises(ValueError, match='no plot is on screen'):
        render('Binding model', state='empty', pointer=(0.5, 0.5))


def test_a_window_the_main_window_opens_is_drawn_at_its_own_size(qapp):
    from docs.design.render import render
    from gui.views.simulation import WINDOW_SIZE

    image = render('Simulation', state='empty')

    assert (image.width(), image.height()) == WINDOW_SIZE


def test_a_render_at_a_scale_has_that_many_device_pixels_per_logical_pixel(qapp):
    from docs.design.render import render

    image = render('Measurements', state='empty', scale=1.5)

    assert (image.width(), image.height()) == (2160, 1350)
