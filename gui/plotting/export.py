"""High-quality image export for PyQtGraph plots and scenes.

This module owns every export-time concern in one place:

* Dispatching PNG vs. SVG via file extension.
* Screen-space items (LegendItem, TextItem) participate in the painter
  transform during export so they scale up with the rest of the figure
  instead of staying tiny at high resolutions.
* Pixel-exact sizing for composite scenes: resize the source widget,
  then export.

PyQtGraph provides ``ImageExporter`` and ``SVGExporter`` natively. They
both accept either a ``PlotItem`` or a ``QGraphicsScene`` — the latter
is what allows multi-subplot composite export of a
``GraphicsLayoutWidget`` in a single native call, without any manual
``QImage``/``QPainter`` stitching.

The only piece of "manual plumbing" that remains is
:func:`_screen_space_items_to_scene_space` (+ its supporting one-time
:func:`_install_textitem_export_patch`). This addresses a real
limitation: items with ``ItemIgnoresTransformations`` and
``pg.TextItem`` deliberately bypass the painter transform so they keep
a fixed on-screen size during interactive zoom. That UX choice fights
the painter transform that ``scene.render()`` sets up during export.
There is no native PyQtGraph mechanism to suspend it. The context
manager flips both off for the duration of the render and restores
them on exit; the monkey-patch is gated by a per-instance sentinel so
it is a no-op for every TextItem that isn't currently being exported.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import pyqtgraph as pg
import pyqtgraph.exporters  # noqa: F401 — registers exporters
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QImage, QTransform
from PyQt6.QtWidgets import QGraphicsItem

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsScene, QWidget


_TEXTITEM_PATCHED = False


def _install_textitem_export_patch() -> None:
    """Idempotently patch ``pg.TextItem.updateTransform`` for export bypass.

    When a TextItem carries the sentinel ``_suspend_export_transform =
    True``, its ``updateTransform`` becomes a no-op so the
    inverted-parent-transform reset cannot fight whatever transform we
    set on the item during export. Without this, TextItem repaints
    during ``scene.render`` re-apply its inverse parent transform and
    cancel the export painter scaling.
    """
    global _TEXTITEM_PATCHED
    if _TEXTITEM_PATCHED:
        return
    _orig_update_transform = pg.TextItem.updateTransform

    def _patched_update_transform(self, force: bool = False) -> None:  # type: ignore[override]
        if getattr(self, '_suspend_export_transform', False):
            return
        _orig_update_transform(self, force)

    pg.TextItem.updateTransform = _patched_update_transform  # type: ignore[assignment]
    _TEXTITEM_PATCHED = True


@contextmanager
def _screen_space_items_to_scene_space(scene: 'QGraphicsScene'):
    """Temporarily flip every screen-space scene item into scene-space.

    On entry:
      * Items with ``ItemIgnoresTransformations`` have the flag cleared
        so the painter transform reaches them during ``scene.render``.
      * ``pg.TextItem`` instances are reparented to the scene root
        (their current scene position is preserved). This sidesteps
        the data-coords scaling that would otherwise apply when an
        annotation is parented under a ViewBox's ``childGroup`` —
        without reparenting, an X-axis range of ``1e-4`` M would
        multiply the glyphs by ``~1e7`` and push them off-canvas.
      * Their auto-inverting transform is frozen via the per-instance
        sentinel installed by :func:`_install_textitem_export_patch`,
        and the transform reset to identity so the painter scale
        applies cleanly.

    On exit: every change is undone exactly so interactive behaviour
    survives the export.
    """
    _install_textitem_export_patch()

    flagged: list[QGraphicsItem] = []
    text_items: list[pg.TextItem] = []
    for item in scene.items():
        if item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations:
            item.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,
                False,
            )
            flagged.append(item)
        if isinstance(item, pg.TextItem):
            item._export_saved_transform = item.transform()
            item._export_saved_last = getattr(item, '_lastTransform', None)
            item._export_saved_parent = item.parentItem()
            item._export_saved_pos = item.pos()
            scene_pos = item.mapToScene(QPointF(0, 0))
            item.setParentItem(None)
            item.setPos(scene_pos)
            item.setTransform(QTransform())
            item.updateTextPos()
            item._suspend_export_transform = True
            text_items.append(item)
    try:
        yield
    finally:
        for item in flagged:
            item.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,
                True,
            )
        for item in text_items:
            item._suspend_export_transform = False
            item.setParentItem(item._export_saved_parent)
            item.setPos(item._export_saved_pos)
            item.setTransform(item._export_saved_transform)
            item._lastTransform = item._export_saved_last
            del item._export_saved_parent
            del item._export_saved_pos
            del item._export_saved_transform
            del item._export_saved_last
            item.updateTransform(force=True)


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
        raise ValueError(f"Unsupported export format: '{ext}'. Use .png or .svg")


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
        raise ValueError(f"Unsupported export format: '{ext}'. Use .png or .svg")


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
