# PyQtGraph Image Export

> 20 nodes · cohesion 0.14

## Key Concepts

- **export.py** (10 connections) — `gui/plotting/export.py`
- **export_plot_item()** (8 connections) — `gui/plotting/export.py`
- **export_scene()** (7 connections) — `gui/plotting/export.py`
- **render_scene_to_qimage()** (7 connections) — `gui/plotting/export.py`
- **prepare_widget_for_offscreen_render()** (6 connections) — `gui/plotting/export.py`
- **_screen_space_items_to_scene_space()** (6 connections) — `gui/plotting/export.py`
- **_ext()** (4 connections) — `gui/plotting/export.py`
- **Path** (3 connections) — `gui/plotting/export.py`
- **_install_textitem_export_patch()** (3 connections) — `gui/plotting/export.py`
- **.export_image()** (3 connections) — `gui/plotting/plot_widget.py`
- **RuntimeError** (2 connections)
- **PlotItem** (1 connections) — `gui/plotting/export.py`
- **High-quality image export for PyQtGraph plots and scenes.  This module owns ever** (1 connections) — `gui/plotting/export.py`
- **Export a single ``pg.PlotItem`` to PNG or SVG.      Parameters     ----------** (1 connections) — `gui/plotting/export.py`
- **Export an entire scene (e.g. a ``GraphicsLayoutWidget.scene()``).      Parameter** (1 connections) — `gui/plotting/export.py`
- **Render a scene to an in-memory ``QImage`` (for previews).      Uses the same exp** (1 connections) — `gui/plotting/export.py`
- **Resize a widget to a target pixel size and force its layout to apply.      PyQtG** (1 connections) — `gui/plotting/export.py`
- **Idempotently patch ``pg.TextItem.updateTransform`` for export bypass.      When** (1 connections) — `gui/plotting/export.py`
- **Temporarily flip every screen-space scene item into scene-space.      On entry:** (1 connections) — `gui/plotting/export.py`
- **Export the current plot to a PNG or SVG file.          Parameters         ---** (1 connections) — `gui/plotting/plot_widget.py`

## Relationships

- [[Label Formatting]] (5 shared connections)
- [[Distribution Plot Widget]] (2 shared connections)
- [[Distributions Export Config]] (2 shared connections)
- [[Save Distributions Dialog]] (2 shared connections)
- [[Image Export Tests]] (1 shared connections)
- [[Plot Style Tests]] (1 shared connections)
- [[BaseAssay Interface]] (1 shared connections)

## Source Files

- `gui/plotting/export.py`
- `gui/plotting/plot_widget.py`

## Audit Trail

- EXTRACTED: 66 (97%)
- INFERRED: 2 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*