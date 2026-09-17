"""High-quality image export for PyQtGraph plots and scenes.

This module owns every export-time concern in one place:

* Dispatching PNG vs. SVG via file extension.
* Screen-space items (the legend) participate in the painter transform
  during export so they scale up with the rest of the figure instead of
  staying tiny at high resolutions.
* Pixel-exact sizing for composite scenes: resize the source widget,
  then export.

PyQtGraph provides ``ImageExporter`` and ``SVGExporter`` natively. They
both accept either a ``PlotItem`` or a ``QGraphicsScene`` — the latter
is what allows multi-subplot composite export of a
``GraphicsLayoutWidget`` in a single native call, without any manual
``QImage``/``QPainter`` stitching.

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

from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

import pyqtgraph as pg
import pyqtgraph.exporters  # noqa: F401 — registers exporters
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QGraphicsItem, QWidget

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsScene


@contextmanager
def _screen_space_items_to_scene_space(scene: 'QGraphicsScene'):
    """Temporarily flip every screen-space scene item into scene-space.

    On entry, items carrying ``ItemIgnoresTransformations`` (the legend)
    have the flag cleared so the painter transform reaches them during
    ``scene.render``; on exit it is restored, so interactive behaviour
    survives the export.

    ``pg.TextItem`` needs no handling here: the fit-summary annotation is
    parented to the ViewBox itself rather than to its ``childGroup``, so
    it already lives in pixel space and its auto-inverting transform is
    the identity.
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
        raise ValueError(f"A plot is saved as a picture or a drawing, so '{ext}' cannot be written. Use .png or .svg.")


def export_scene(
    scene: 'QGraphicsScene',
    path: str | Path,
    *,
    width_px: int | None = None,
) -> None:
    """Export an entire scene (e.g. a ``GraphicsLayoutWidget.scene()``).

    Parameters
    ----------
    scene
        The Qt graphics scene to export. Typical use: pass
        ``glw.scene()`` where ``glw`` is a
        :class:`pyqtgraph.GraphicsLayoutWidget` holding several
        PlotItems in a grid.
    path
        Output path. ``.png`` → rasterised PNG, ``.svg`` → vector SVG.
    width_px
        Output width in pixels for PNG. The scene's aspect ratio
        determines the height — resize the source widget beforehand if
        you need an exact (width × height) result.

    Raises
    ------
    ValueError
        If the file extension is not ``.png`` or ``.svg``.
    """
    ext = _ext(path)
    if ext == '.png':
        exporter = pg.exporters.ImageExporter(scene)
        if width_px is not None:
            exporter.parameters()['width'] = int(width_px)
        with _screen_space_items_to_scene_space(scene):
            exporter.export(str(path))
    elif ext == '.svg':
        exporter = pg.exporters.SVGExporter(scene)
        exporter.export(str(path))
    else:
        raise ValueError(f"A plot is saved as a picture or a drawing, so '{ext}' cannot be written. Use .png or .svg.")


@contextmanager
def _left_out(parent: 'QWidget', widgets: 'Sequence[QWidget]'):
    """Hide *widgets* and lay *parent* out without them, putting both back on exit.

    Only the ones currently on screen are touched, and the layout is applied at
    once so what is painted matches what is left: the space a hidden row held
    goes to whatever stretches beside it rather than staying blank.
    """
    hidden = [widget for widget in widgets if not widget.isHidden()]
    layout = parent.layout()
    for widget in hidden:
        widget.setVisible(False)
    if hidden and layout is not None:
        layout.activate()
    try:
        yield
    finally:
        for widget in hidden:
            widget.setVisible(True)
        if hidden and layout is not None:
            layout.activate()


def export_widget(
    widget: 'QWidget',
    path: str | Path,
    *,
    width_px: int = 2100,
    without: 'Sequence[QWidget]' = (),
) -> None:
    """Export a whole widget tree — text, plots and all — to a PNG.

    A tab that mixes labels with several plots is one picture to the reader, so
    it is painted as one: ``QWidget.render`` walks the tree and every child
    paints itself through the same painter. Screen-space items are flipped into
    scene space for the duration, as in :func:`export_scene`, so a legend scales
    with the rest.

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
        :func:`export_scene`, which draws through pyqtgraph's own exporter.
    width_px
        Output width in pixels; the height follows the widget's aspect ratio.
    without
        Children to leave out of the picture. A saved figure is read on its own,
        so the controls that change what a tab shows have nothing to offer it;
        on macOS a check box or a drop-down painted outside the window draws as
        its label with no frame at all.

    Raises
    ------
    ValueError
        If the file extension is not ``.png``, or the widget has no size to
        paint.
    """
    from PyQt6.QtCore import QSize, Qt
    from PyQt6.QtGui import QPainter

    ext = _ext(path)
    if ext != '.png':
        raise ValueError(f"A whole tab is saved as one picture, so '{ext}' cannot be written. Use .png.")
    scenes = [child.scene() for child in widget.findChildren(pg.GraphicsView) if child.scene() is not None]
    with ExitStack() as stack:
        stack.enter_context(_left_out(widget, without))
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
            raise ValueError(f'The image could not be written to {path}.')


def render_scene_to_qimage(
    scene: 'QGraphicsScene',
    width_px: int,
) -> QImage:
    """Render a scene to an in-memory ``QImage`` (for previews).

    Uses the same export pipeline as :func:`export_scene` so the
    preview cannot drift from what the saved PNG would contain.

    Parameters
    ----------
    scene
        The Qt graphics scene to render.
    width_px
        Output width in pixels. Height is derived from scene aspect.

    Returns
    -------
    QImage
        The rendered image, sized by PyQtGraph's ``ImageExporter``.
    """
    exporter = pg.exporters.ImageExporter(scene)
    exporter.parameters()['width'] = int(width_px)
    with _screen_space_items_to_scene_space(scene):
        img = exporter.export(toBytes=True)
    if not isinstance(img, QImage):
        raise RuntimeError('ImageExporter did not return a QImage.')
    return img


def prepare_widget_for_offscreen_render(widget: 'QWidget', width_px: int, height_px: int) -> None:
    """Resize a widget to a target pixel size and force its layout to apply.

    PyQtGraph's ``GraphicsLayoutWidget`` lays out its cells (and the
    underlying scene bounding rect) in response to the widget's size.
    For pixel-exact composite export the widget must be resized to the
    target dimensions before ``ImageExporter`` reads its scene.

    The widget is configured with ``WA_DontShowOnScreen`` so calling
    ``show()`` triggers layout without putting anything on screen, and
    pending Qt events are processed so the resize propagates to the
    scene before the caller reads it. Callers must keep a reference
    until export is complete and then drop or delete the widget.
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication

    widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    widget.resize(int(width_px), int(height_px))
    widget.show()
    QApplication.processEvents()
