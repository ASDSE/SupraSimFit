"""Every saved figure stands on white with one margin around it, its head laid out as the screen lays it (DESIGN.md §7).

A figure is written by :func:`~gui.plotting.export.export_stacked` (the titration, the
Simulation) or :func:`~gui.plotting.export.export_widget` (Ka confidence,
Sensitivity), and each puts the one margin of ``SIZE['figure-margin']`` round what it is
given: no ink reaches into it, and the head and legend stand at it, left and right.
"""

from __future__ import annotations

import pytest

pytest.importorskip('PyQt6')

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtGui import QImage  # noqa: E402

from gui.design.tokens import SIZE, space  # noqa: E402
from tests.unit.gui import sensitivity_results as F  # noqa: E402
from tests.unit.gui.test_confidence_view import _show  # noqa: E402
from tests.unit.gui.test_sensitivity_view import _hold  # noqa: E402

#: How far into a figure, past its margin, its outermost ink may start: a glyph's side bearing, or the top
#: line's leading above its letters.
SLACK = {'side': 3, 'top': space(3)}


@pytest.fixture
def session(qapp, monkeypatch):
    from gui.fitting_session import FittingSession

    def refuse(*args):
        raise AssertionError(f'a dialog would have blocked the test: {args[1:]}')

    for kind in ('warning', 'information', 'question'):
        monkeypatch.setattr(f'gui.fitting_session.QMessageBox.{kind}', refuse)
    made = FittingSession()
    made.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    made.resize(1440, 900)
    made.show()
    yield made
    made.model.shutdown()
    made.close()


def margins(path) -> dict[str, float]:
    """The white round the ink of the figure at *path*, each side in logical px of the figure."""
    image = QImage(str(path))
    scale = image.width() / (SIZE['export-width'] + 2 * SIZE['figure-margin'])

    def ink(x: int, y: int) -> bool:
        return image.pixelColor(x, y).lightness() < 250

    w, h = image.width(), image.height()
    columns = [x for x in range(w) if any(ink(x, y) for y in range(0, h, 2))]
    rows = [y for y in range(h) if any(ink(x, y) for x in range(0, w, 2))]
    return {
        'left': columns[0] / scale,
        'right': (w - 1 - columns[-1]) / scale,
        'top': rows[0] / scale,
        'bottom': (h - 1 - rows[-1]) / scale,
    }


def _figures(qapp, session, demo, tmp_path, monkeypatch) -> dict[str, object]:
    """Each kind of saved figure of the app, written to *tmp_path*, by name."""
    paths = {}
    assert session.set_up_demo_ida()
    paths['measurements'] = tmp_path / 'measurements.png'
    session._measurements.export_image(str(paths['measurements']))
    fit, profile = demo
    _show(session, fit, profile)
    paths['confidence'] = tmp_path / 'confidence.png'
    session._confidence.export_image(str(paths['confidence']))
    for name, result in (('sensitivity', F.sobol_result()), ('heatmap', F.heatmap_result())):
        _hold(session, result)
        paths[name] = tmp_path / f'{name}.png'
        session._sensitivity.export_image(str(paths[name]))
    session.show_view('Simulation')
    paths['simulation'] = tmp_path / 'simulation.png'
    session._simulation.export_image(str(paths['simulation']))
    return paths


def test_every_saved_figure_has_the_one_margin_round_its_head_and_plots(qapp, session, demo, tmp_path, monkeypatch):
    margin = SIZE['figure-margin']
    seen = {name: margins(path) for name, path in _figures(qapp, session, demo, tmp_path, monkeypatch).items()}

    for name, m in seen.items():
        for side in ('left', 'right'):
            assert margin <= m[side] <= margin + SLACK['side'], (name, side, m)
        assert margin <= m['top'] <= margin + SLACK['top'], (name, m)
        assert m['bottom'] >= margin, (name, m)


def test_a_figure_head_too_narrow_for_its_legend_puts_it_under_the_title_at_the_right(qapp):
    """As a plot header on screen does (DESIGN.md §7): the legend's line is right-aligned to the head."""
    from gui.design import components as C
    from gui.design.tokens import Theme
    from gui.plotting.export import figure_head

    light = Theme(dark=False)
    legend = C.LegendRow(light, [('line', 'Input-aware'), ('line-secondary', 'Inputs as entered')], removable=False)
    head = figure_head(light, 'Kₐ guest', 'a description long enough to push the legend under it', legend, 420)
    head.show()
    qapp.processEvents()
    try:
        title = head.findChildren(C.PaintedText)[0]
        assert legend.geometry().top() >= title.geometry().bottom(), 'the legend has a line of its own'
        assert legend.geometry().right() == head.contentsRect().right()
    finally:
        head.close()
