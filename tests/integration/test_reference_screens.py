"""The reference screens of the design are rendered by one command from the running app.

``python -m docs.design.render --all <dir>`` draws every screen of
:data:`docs.design.render.SCREENS` in both themes from the real windows with Demo IDA,
its fit and its sensitivity analysis: each costs seconds, so this check lives here, the
slow layer.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip('PyQt6')

ROOT = Path(__file__).resolve().parents[2]


def test_the_command_renders_every_reference_screen_in_both_themes(tmp_path):
    from PyQt6.QtGui import QImage

    from docs.design.render import SCALE, SCREENS, THEMES

    done = subprocess.run(
        [sys.executable, '-m', 'docs.design.render', '--all', str(tmp_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-2000:]

    expected = {f'{name}_{theme}.jpg' for name in SCREENS for theme in THEMES}
    assert {p.name for p in tmp_path.iterdir()} == expected
    blank = []
    for file in sorted(expected):
        image = QImage(str(tmp_path / file))
        colours = {image.pixel(x, y) for x in range(0, image.width(), 12) for y in range(0, image.height(), 12)}
        if image.isNull() or len(colours) < 64:
            blank.append(file)
    assert not blank, f'blank or unreadable screens: {blank}'
    main = QImage(str(tmp_path / 'fit_light.jpg'))
    assert (main.width(), main.height()) == (round(1440 * SCALE), round(900 * SCALE))
