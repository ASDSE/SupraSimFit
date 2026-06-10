# Plot Style Tests

> 32 nodes · cohesion 0.12

## Key Concepts

- **PlotWidget** (45 connections) — `gui/plotting/plot_widget.py`
- **PlotStyleWidget** (32 connections) — `gui/plotting/plot_style.py`
- **test_plot_widget.py** (24 connections) — `tests/unit/gui/test_plot_widget.py`
- **qapp fixture** (8 connections) — `tests/unit/gui/conftest.py`
- **test_plot_style.py** (8 connections) — `tests/unit/gui/test_plot_style.py`
- **test_style_roundtrip.py** (7 connections) — `tests/unit/gui/test_style_roundtrip.py`
- **_bottom_label()** (5 connections) — `tests/unit/gui/test_plot_widget.py`
- **test_clearing_override_restores_default_name()** (4 connections) — `tests/unit/gui/test_plot_widget.py`
- **test_x_name_override_replaces_name_but_keeps_unit()** (4 connections) — `tests/unit/gui/test_plot_widget.py`
- **test_x_unit_change_preserves_custom_name()** (4 connections) — `tests/unit/gui/test_plot_widget.py`
- **test_y_name_override_replaces_name_but_keeps_unit()** (4 connections) — `tests/unit/gui/test_plot_widget.py`
- **test_apply_style_with_no_items_does_not_raise()** (4 connections) — `tests/unit/gui/test_style_roundtrip.py`
- **_left_label()** (3 connections) — `tests/unit/gui/test_plot_widget.py`
- **test_default_x_label_uses_registry_name_and_x_unit()** (3 connections) — `tests/unit/gui/test_plot_widget.py`
- **test_default_y_label_uses_registry_name_and_y_unit()** (3 connections) — `tests/unit/gui/test_plot_widget.py`
- **test_style_signal_updates_plot_style()** (3 connections) — `tests/unit/gui/test_style_roundtrip.py`
- **launch** (3 connections) — `gui/main_window.py`
- **test_axes_group_does_not_expose_x_axis_unit()** (2 connections) — `tests/unit/gui/test_plot_style.py`
- **test_axis_name_overrides_round_trip_via_load_style()** (2 connections) — `tests/unit/gui/test_plot_style.py`
- **test_load_style_restores_x_unit()** (2 connections) — `tests/unit/gui/test_plot_style.py`
- **test_set_x_unit_emits_once()** (2 connections) — `tests/unit/gui/test_plot_style.py`
- **test_set_x_unit_updates_style_dict()** (2 connections) — `tests/unit/gui/test_plot_style.py`
- **test_update_plot_clears_on_second_call()** (2 connections) — `tests/unit/gui/test_plot_widget.py`
- **test_whitespace_only_override_falls_back_to_default()** (2 connections) — `tests/unit/gui/test_plot_widget.py`
- **Tests for PlotStyleWidget x-axis unit handling.  The x-axis unit was removed fro** (1 connections) — `tests/unit/gui/test_plot_style.py`
- *... and 7 more nodes in this community*

## Relationships

- [[Plot Colors & Palette]] (10 shared connections)
- [[Checkbox Grid UI Helpers]] (8 shared connections)
- [[Distributions Export Config]] (7 shared connections)
- [[Axis Exponent Formatting]] (7 shared connections)
- [[Scientific Axis Item]] (6 shared connections)
- [[Image Export Tests]] (4 shared connections)
- [[Label Formatting]] (4 shared connections)
- [[Plot Style Widget]] (4 shared connections)
- [[MeasurementSet & FitResult]] (2 shared connections)
- [[Style Template Persistence]] (2 shared connections)
- [[FittingSession Export]] (2 shared connections)
- [[Data Panel Tests]] (1 shared connections)

## Source Files

- `gui/main_window.py`
- `gui/plotting/plot_style.py`
- `gui/plotting/plot_widget.py`
- `tests/unit/gui/conftest.py`
- `tests/unit/gui/test_plot_style.py`
- `tests/unit/gui/test_plot_widget.py`
- `tests/unit/gui/test_style_roundtrip.py`

## Audit Trail

- EXTRACTED: 169 (91%)
- INFERRED: 17 (9%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*