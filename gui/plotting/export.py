"""High-quality image export for PyQtGraph plots and whole tabs.

This module owns every export-time concern in one place:

* Dispatching PNG vs. SVG via file extension.
* Screen-space items (the legend) participate in the painter transform
  during export so they scale up with the rest of the figure instead of
  staying tiny at high resolutions.

PyQtGraph provides ``ImageExporter`` and ``SVGExporter`` natively, and
both accept a ``PlotItem``, so a single plot is written through the
library's own exporters; plots stacked on one axis are written by
:func:`export_stacked`, each through those exporters and set one above the
other. A whole tab — text, controls and several plots
— is painted by Qt itself in :func:`export_widget`.

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
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import pyqtgraph as pg
import pyqtgraph.exporters  # noqa: F401 — registers exporters
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QGraphicsItem, QWidget

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsScene


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


def export_plot_item(
    plot_item: pg.PlotItem,
    path: str | Path,
    *,
    width_px: int | None = None,
) -> None:
    """Export a single ``pg.PlotItem`` to PNG or SVG.

    Parameters
    ----------
    plot_item
        The plot item to export.
    path
        Output path. ``.png`` → rasterised PNG, ``.svg`` → vector SVG.
    width_px
        Output width in pixels for PNG. Height is derived by PyQtGraph
        from the plot's aspect ratio. Ignored for SVG.

    Raises
    ------
    ValueError
        If the file extension is not ``.png`` or ``.svg``.
    """
    ext = _ext(path)
    scene = plot_item.scene()
    if ext == '.png':
        exporter = pg.exporters.ImageExporter(plot_item)
        if width_px is not None:
            exporter.parameters()['width'] = int(width_px)
        with _screen_space_items_to_scene_space(scene):
            exporter.export(str(path))
    elif ext == '.svg':
        exporter = pg.exporters.SVGExporter(plot_item)
        exporter.export(str(path))
    else:
        raise ExportRefused(
            f"A plot is saved as a picture or a drawing, so '{ext}' cannot be written. Use .png or .svg."
        )


def export_stacked(plot_items: list[pg.PlotItem], path: str | Path, *, width_px: int) -> None:
    """Export *plot_items* one above the other, in order, as one PNG or SVG on white.

    Each plot goes through pyqtgraph's own exporter, which keeps its curves inside its
    axes in both formats and paints the plot's own background, and the pictures are set
    one under the next at the width of
    the widest. Plots of one width with axes of one width keep their x axes aligned.

    Parameters
    ----------
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
        for item in plot_items:
            exporter = pg.exporters.ImageExporter(item)
            exporter.parameters()['width'] = int(width_px)
            with _screen_space_items_to_scene_space(item.scene()):
                images.append(exporter.export(toBytes=True))
        image = QImage(max(i.width() for i in images), sum(i.height() for i in images), QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.white)
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
        parts, y, width = [], 0.0, 0.0
        for item in plot_items:
            svg = pg.exporters.SVGExporter(item).export(toBytes=True).decode('utf-8')
            w, h = (float(v) for v in re.search(r'viewBox\s*=\s*"0 0 ([\d.]+) ([\d.]+)"', svg).groups())
            body = svg[svg.index('<svg') :]
            parts.append(body.replace('<svg', f'<svg x="0" y="{y:g}" width="{w:g}" height="{h:g}"', 1))
            y, width = y + h, max(width, w)
        Path(path).write_text(
            '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" version="1.2" '
            f'width="{width:g}" height="{y:g}" viewBox="0 0 {width:g} {y:g}">\n' + '\n'.join(parts) + '\n</svg>\n',
            encoding='utf-8',
        )
    else:
        raise ExportRefused(
            f"A plot is saved as a picture or a drawing, so '{ext}' cannot be written. Use .png or .svg."
        )


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
    scene space for the duration, as in :func:`export_plot_item`, so a legend
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
        beside it. A single plot still exports to SVG through
        :func:`export_plot_item`, which draws through pyqtgraph's own exporter.
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
        image.fill(Qt.GlobalColor.white)
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
