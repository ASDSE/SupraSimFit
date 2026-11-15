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
