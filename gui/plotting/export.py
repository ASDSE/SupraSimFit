"""High-quality image export for PyQtGraph plots and whole tabs.

This module owns every export-time concern in one place:

* Dispatching PNG vs. SVG via file extension.
* Screen-space items (the legend) participate in the painter transform
  during export so they scale up with the rest of the figure instead of
  staying tiny at high resolutions.

PyQtGraph provides ``ImageExporter`` and ``SVGExporter`` natively, and
both accept a ``PlotItem``: :func:`export_stacked` writes each plot of a
figure through them and sets it under the painted head
:func:`figure_head` gives it — title, caption, legend and notes. A whole
tab — text, controls and several plots — is painted by Qt itself in
:func:`export_widget`.

The only piece of "manual plumbing" that remains is
:func:`_screen_space_items_to_scene_space`. This addresses a real
limitation: items with ``ItemIgnoresTransformations`` deliberately
bypass the painter transform so they keep a fixed on-screen size during
interactive zoom. That UX choice fights the painter transform that
``scene.render()`` sets up during export, and there is no native
PyQtGraph mechanism to suspend it. The context manager flips the flag
off for the duration of the render and restores it on exit.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from contextlib import ExitStack, contextmanager
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING

import pyqtgraph as pg
import pyqtgraph.exporters  # noqa: F401 — registers exporters
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QGraphicsItem, QWidget

from gui.design import components as C
from gui.design.tokens import LIGHT, Theme, plot_font, space

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsScene


#: The page a saved figure is drawn on: the light theme's surface, white (DESIGN.md §7).
PAPER = QColor(LIGHT['bg-surface'])


def figure_head(
    t: Theme,
    title: str,
    caption: str,
    legend: QWidget,
    width: int,
    notes: Sequence[str] = (),
    text: str | None = None,
) -> QWidget:
    """A saved plot's head in theme *t*, *width* px wide, as the plot's header line states it on screen.

    Its *title* and *caption* on the left and its *legend* on the right — on a line of its
    own under them where one line cannot hold all three — then each of *notes*, a line of
    plain text wrapped to the width. An empty caption takes no room. With a step *text* of
    :data:`~gui.design.tokens.PLOT_TEXT` — the axis text of the plot under it — the title reads
    at the size of its axis titles and the caption and notes at the size of its tick labels.
    """
    title_font, body_font = (plot_font(text, 'title'), plot_font(text, 'tick')) if text else (None, None)
    title_text = C.PaintedText(t, title, 'body-strong', title_font)
    texts = [title_text, *([C.PaintedText(t, caption, 'small', body_font)] if caption else [])]
    for text_item in texts:
        text_item.setFixedWidth(text_item.minimumWidth())
    words = [texts[0], *([3, texts[1]] if caption else [])]
    room = sum(text_item.width() for text_item in texts) + (space(3) if caption else 0) + space(5) + legend.width()
    if room <= width:
        rows = [C.hbox(*words, None, legend, spacing=0)]
    else:
        rows = [C.hbox(*words, None, spacing=0), C.hbox(legend, None, spacing=0)]
    for note in notes:
        # Kept as written: rich text would otherwise fold the thin spaces of 1.59 × 10⁸ into plain ones.
        html = f'<span style="white-space:pre-wrap">{escape(note)}</span>'
        rows += [C.PaintedNote(t, html, 'small', width, body_font)]
    w = C.Figure(t)
    w.setLayout(C.vbox(*rows, spacing=1, margins=(0, 3, 0, 2)))
    w.setFixedWidth(width)
    w.adjustSize()
    return w


class ExportRefused(ValueError):
    """An export that cannot be made, with a message written for the user.

    The interface shows its text as it is. Every other error of an export
    carries a library's or a programmer's wording and is replaced by a
    sentence of the caller's.
    """


@contextmanager
def _screen_space_items_to_scene_space(scene: 'QGraphicsScene'):
    """Temporarily flip every screen-space scene item into scene-space.

    On entry, items carrying ``ItemIgnoresTransformations`` (the legend)
    have the flag cleared so the painter transform reaches them during
    ``scene.render``; on exit it is restored, so interactive behaviour
    survives the export.

    ``pg.TextItem`` needs no handling here: one parented to the ViewBox
    itself rather than to its ``childGroup`` already lives in pixel space,
    and its auto-inverting transform is the identity.
    """
    flagged: list[QGraphicsItem] = []
    for item in scene.items():
        if item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations:
            item.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,
                False,
            )
            flagged.append(item)
    try:
        yield
    finally:
        for item in flagged:
            item.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,
                True,
            )


def _ext(path: str | Path) -> str:
    return Path(path).suffix.lower()


def export_stacked(parts: list[pg.PlotItem | QWidget], path: str | Path, *, width_px: int) -> None:
    """Export *parts* one above the other, in order, as one PNG or SVG on white.

    A part is a plot or a widget — a plot's title and legend. Each plot goes through
    pyqtgraph's own exporter, which keeps its curves inside its axes in both formats and
    paints the plot's own background; a widget paints itself, at the size it has, scaled
    to the plots. The pictures are set one under the next at the width of the widest.
    Plots of one width with axes of one width keep their x axes aligned, and a widget as
    wide as the plots spans them.

    Parameters
    ----------
    parts
        The plots and widgets, top first. A widget is laid out and as wide as the plots.
    path
        Output path, ``.png`` or ``.svg``.
    width_px
        Output width of the PNG in pixels; ignored for SVG.

    Raises
    ------
    ExportRefused
        If the extension is neither, or the PNG cannot be written.
    """
    ext = _ext(path)
    if ext == '.png':
        images = []
        for part in parts:
            if isinstance(part, QWidget):
                scale = width_px / part.width()
                image = QImage(int(width_px), round(part.height() * scale), QImage.Format.Format_ARGB32)
                image.fill(PAPER)
                painter = QPainter(image)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.scale(scale, scale)
                part.render(painter, flags=QWidget.RenderFlag.DrawChildren)
                painter.end()
                images.append(image)
                continue
            exporter = pg.exporters.ImageExporter(part)
            exporter.parameters()['width'] = int(width_px)
            with _screen_space_items_to_scene_space(part.scene()):
                images.append(exporter.export(toBytes=True))
        image = QImage(max(i.width() for i in images), sum(i.height() for i in images), QImage.Format.Format_ARGB32)
        image.fill(PAPER)
        painter = QPainter(image)
        y = 0
        for part in images:
            painter.drawImage(0, y, part)
            y += part.height()
        painter.end()
        if not image.save(str(path)):
            raise ExportRefused(
                f'The picture could not be written to {path}. Check that the folder exists and that you may '
                'write there, then save it again.'
            )
    elif ext == '.svg':
        drawings, y, width = [], 0.0, 0.0
        for part in parts:
            svg = (
                _widget_svg(part) if isinstance(part, QWidget) else pg.exporters.SVGExporter(part).export(toBytes=True)
            )
            svg = svg.decode('utf-8')
            w, h = (float(v) for v in re.search(r'viewBox\s*=\s*"0 0 ([\d.]+) ([\d.]+)"', svg).groups())
            body = svg[svg.index('<svg') :]
            # The drawing's own size gives way to its place in the figure.
            end = body.index('>')
            tag = re.sub(r'\s(?:x|y|width|height)\s*=\s*"[^"]*"', '', body[:end])
            drawings.append(tag.replace('<svg', f'<svg x="0" y="{y:g}" width="{w:g}" height="{h:g}"', 1) + body[end:])
            y, width = y + h, max(width, w)
        Path(path).write_text(
            '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" version="1.2" '
            f'width="{width:g}" height="{y:g}" viewBox="0 0 {width:g} {y:g}">\n' + '\n'.join(drawings) + '\n</svg>\n',
            encoding='utf-8',
        )
    else:
        raise ExportRefused(
            f"A plot is saved as a picture or a drawing, so '{ext}' cannot be written. Use .png or .svg."
        )


def _widget_svg(widget: QWidget) -> bytes:
    """*widget* painted as an SVG drawing at the size it has, its text kept as text."""
    from PyQt6.QtCore import QBuffer, QRect
    from PyQt6.QtSvg import QSvgGenerator

    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    generator = QSvgGenerator()
    generator.setOutputDevice(buffer)
    generator.setSize(widget.size())
    generator.setViewBox(QRect(0, 0, widget.width(), widget.height()))
    painter = QPainter(generator)
    widget.render(painter, flags=QWidget.RenderFlag.DrawChildren)
    painter.end()
    return bytes(buffer.data())


def export_widget(
    widget: 'QWidget',
    path: str | Path,
    *,
    width_px: int = 2100,
) -> None:
    """Export a whole widget tree — text, plots and all — to a PNG.

    A tab that mixes labels with several plots is one picture to the reader, so
    it is painted as one: ``QWidget.render`` walks the tree and every child
    paints itself through the same painter. Screen-space items are flipped into
    scene space for the duration, as in :func:`export_stacked`, so a legend
    scales with the rest.

    Parameters
    ----------
    widget
        The widget to paint. It is rendered at the size it currently has, so
        the caller passes the one holding the full contents (a scroll area's
        inner widget, not the viewport).
    path
        Output path, which must end in ``.png``. Qt's SVG painter drops the clip
        that keeps each plot's curves inside its axes, so a whole tab drawn as
        SVG puts a curve that runs past its axes across the legend and the text
        beside it. Plots set one above the other export to SVG through
        :func:`export_stacked`, which draws each through pyqtgraph's own exporter.
    width_px
        Output width in pixels; the height follows the widget's aspect ratio.

    Raises
    ------
    ValueError
        If the file extension is not ``.png``, or the widget has no size to
        paint.
    """
    from PyQt6.QtCore import QSize

    ext = _ext(path)
    if ext != '.png':
        raise ExportRefused(f"A whole tab is saved as one picture, so '{ext}' cannot be written. Use .png.")
    scenes = [child.scene() for child in widget.findChildren(pg.GraphicsView) if child.scene() is not None]
    with ExitStack() as stack:
        for scene in scenes:
            stack.enter_context(_screen_space_items_to_scene_space(scene))
        size = widget.size()
        if size.width() <= 0 or size.height() <= 0:
            raise ValueError('The widget has no size to export.')
        scale = width_px / size.width()
        image = QImage(
            QSize(int(width_px), int(round(size.height() * scale))),
            QImage.Format.Format_ARGB32,
        )
        image.fill(PAPER)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(scale, scale)
        widget.render(painter, flags=QWidget.RenderFlag.DrawChildren)
        painter.end()
        if not image.save(str(path)):
            raise ExportRefused(
                f'The picture could not be written to {path}. Check that the folder exists and that you may '
                'write there, then save it again.'
            )
