"""The render harness draws the running app, so a visual check sees what the user sees."""

from __future__ import annotations

import pytest

pytest.importorskip('PyQt6')


def test_render_returns_window_image(qapp):
    from docs.design.render import render

    image = render('Measurements', state='demo-fitted')

    assert (image.width(), image.height()) == (1440, 900)
    colours = {image.pixel(x, y) for x in range(0, 1440, 16) for y in range(0, 900, 16)}
    assert len(colours) > 1
