# EnSight Loading & Channels

> 28 nodes · cohesion 0.11

## Key Concepts

- **DataPanel** (51 connections) — `gui/widgets/data_panel.py`
- **._push_buffer_to_ms()** (7 connections) — `gui/widgets/data_panel.py`
- **TestEnsightLoadIntegration** (6 connections) — `tests/unit/gui/test_data_panel.py`
- **._refresh_after_load()** (6 connections) — `gui/widgets/data_panel.py`
- **._populate_table()** (5 connections) — `gui/widgets/data_panel.py`
- **.clear()** (4 connections) — `gui/widgets/data_panel.py`
- **._on_load_concentrations()** (4 connections) — `gui/widgets/data_panel.py`
- **._set_concentration_controls_enabled()** (4 connections) — `gui/widgets/data_panel.py`
- **._setup_ui()** (4 connections) — `gui/widgets/data_panel.py`
- **_fmt_cell()** (4 connections) — `gui/widgets/data_panel.py`
- **.__init__()** (3 connections) — `gui/widgets/data_panel.py`
- **._on_cell_changed()** (3 connections) — `gui/widgets/data_panel.py`
- **._update_info()** (3 connections) — `gui/widgets/data_panel.py`
- **.test_load_real_ensight_no_modal_multichannel()** (2 connections) — `tests/unit/gui/test_data_panel.py`
- **.test_switch_channel_resets_via_emit()** (2 connections) — `tests/unit/gui/test_data_panel.py`
- **READERS** (2 connections) — `core/io/registry.py`
- **.focus_concentration_table()** (2 connections) — `gui/widgets/data_panel.py`
- **._on_imported_unit_changed()** (2 connections) — `gui/widgets/data_panel.py`
- **.set_display_unit()** (2 connections) — `gui/widgets/data_panel.py`
- **format_channel_label** (1 connections) — `core/io/formats/ensight_reader.py`
- **End-to-end load of the real EnSight fixture through ``load_file``.** (1 connections) — `tests/unit/gui/test_data_panel.py`
- **.current_path()** (1 connections) — `gui/widgets/data_panel.py`
- **.display_unit()** (1 connections) — `gui/widgets/data_panel.py`
- **Load measurement data and edit the concentration vector inline.      Signals** (1 connections) — `gui/widgets/data_panel.py`
- **Set the Display Unit combo without re-emitting if unchanged.** (1 connections) — `gui/widgets/data_panel.py`
- *... and 3 more nodes in this community*

## Relationships

- [[File Load & Channel Labels]] (10 shared connections)
- [[Data Panel Tests]] (9 shared connections)
- [[Concentration Helpers]] (5 shared connections)
- [[Checkbox Grid UI Helpers]] (4 shared connections)
- [[Distributions Export Config]] (3 shared connections)
- [[MeasurementSet & FitResult]] (2 shared connections)
- [[Concentration I/O Round-trip]] (2 shared connections)
- [[Parameter Descriptions & Linear Fit]] (1 shared connections)
- [[Style Template Persistence]] (1 shared connections)
- [[FittingSession Export]] (1 shared connections)
- [[BMG Workbook Parsing]] (1 shared connections)
- [[Fit Config Panel]] (1 shared connections)

## Source Files

- `core/io/formats/ensight_reader.py`
- `core/io/registry.py`
- `gui/widgets/data_panel.py`
- `tests/unit/gui/test_data_panel.py`

## Audit Trail

- EXTRACTED: 107 (86%)
- INFERRED: 18 (14%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*