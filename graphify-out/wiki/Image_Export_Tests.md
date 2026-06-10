# Image Export Tests

> 29 nodes · cohesion 0.08

## Key Concepts

- **test_export.py** (23 connections) — `tests/unit/gui/test_export.py`
- **QImage** (5 connections) — `gui/plotting/export.py`
- **test_live_per_cell_size_uses_live_widget_when_shown()** (4 connections) — `tests/unit/gui/test_export.py`
- **annotated_plot_widget()** (3 connections) — `tests/unit/gui/test_export.py`
- **fitted_dist_widget()** (3 connections) — `tests/unit/gui/test_export.py`
- **test_annotated_export_has_non_trivial_pixels_in_corner()** (3 connections) — `tests/unit/gui/test_export.py`
- **test_distribution_png_grid_layout()** (3 connections) — `tests/unit/gui/test_export.py`
- **test_distribution_png_width_is_exact_height_derived()** (3 connections) — `tests/unit/gui/test_export.py`
- **test_live_per_cell_size_falls_back_when_widget_not_shown()** (3 connections) — `tests/unit/gui/test_export.py`
- **simple_plot_widget()** (2 connections) — `tests/unit/gui/test_export.py`
- **test_annotation_state_restored_after_export()** (2 connections) — `tests/unit/gui/test_export.py`
- **test_derive_height_in_matches_live_cell_aspect()** (2 connections) — `tests/unit/gui/test_export.py`
- **test_plot_widget_png_honours_requested_width()** (2 connections) — `tests/unit/gui/test_export.py`
- **Tests for the consolidated image-export pipeline.  Verifies:   * single-plot PNG** (1 connections) — `tests/unit/gui/test_export.py`
- **The composite PNG's width matches the request exactly; height comes     from the** (1 connections) — `tests/unit/gui/test_export.py`
- **A 2x2 layout with 3 selected keys exports as a valid composite PNG.** (1 connections) — `tests/unit/gui/test_export.py`
- **``derive_height_in`` returns a height that preserves the live cell aspect.** (1 connections) — `tests/unit/gui/test_export.py`
- **A PlotWidget with a fit result + annotation visible.      The widget is shown of** (1 connections) — `tests/unit/gui/test_export.py`
- **The annotation TextItem's parent and position survive a round-trip export.** (1 connections) — `tests/unit/gui/test_export.py`
- **When the live widget has been laid out, ``live_per_cell_size`` reflects it.** (1 connections) — `tests/unit/gui/test_export.py`
- **When the widget hasn't been shown, fallback dimensions are used.      The fallba** (1 connections) — `tests/unit/gui/test_export.py`
- **The annotation occupies a corner; that corner must not be all background.      C** (1 connections) — `tests/unit/gui/test_export.py`
- **A DistributionWidget loaded with a FitResult that has parameter_samples.** (1 connections) — `tests/unit/gui/test_export.py`
- **test_build_composite_layout_rejects_empty_selection()** (1 connections) — `tests/unit/gui/test_export.py`
- **test_build_composite_layout_rejects_oversubscribed_grid()** (1 connections) — `tests/unit/gui/test_export.py`
- *... and 4 more nodes in this community*

## Relationships

- [[Distribution Plot Widget]] (4 shared connections)
- [[Plot Style Tests]] (4 shared connections)
- [[MeasurementSet & FitResult]] (2 shared connections)
- [[Plot Colors & Palette]] (1 shared connections)
- [[PyQtGraph Image Export]] (1 shared connections)

## Source Files

- `gui/plotting/export.py`
- `tests/unit/gui/test_export.py`

## Audit Trail

- EXTRACTED: 65 (88%)
- INFERRED: 9 (12%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*