# Data Panel Tests

> 22 nodes · cohesion 0.10

## Key Concepts

- **test_data_panel.py** (13 connections) — `tests/unit/gui/test_data_panel.py`
- **TestDisplayUnitSignal** (6 connections) — `tests/unit/gui/test_data_panel.py`
- **TestImportedUnitReinterpret** (6 connections) — `tests/unit/gui/test_data_panel.py`
- **TestJascoLoadIntegration** (5 connections) — `tests/unit/gui/test_data_panel.py`
- **TestLiveCommit** (5 connections) — `tests/unit/gui/test_data_panel.py`
- **multi_channel_panel()** (4 connections) — `tests/unit/gui/test_data_panel.py`
- **loaded_panel()** (3 connections) — `tests/unit/gui/test_data_panel.py`
- **_multi_channel_frame()** (3 connections) — `tests/unit/gui/test_data_panel.py`
- **.test_jasco_metadata_forwarded_to_measurement_set()** (2 connections) — `tests/unit/gui/test_data_panel.py`
- **Tests for the inline DataPanel concentration controls.** (1 connections) — `tests/unit/gui/test_data_panel.py`
- **Two-channel placeholder frame: chA signals 0.., chB signals 1000...** (1 connections) — `tests/unit/gui/test_data_panel.py`
- **A DataPanel set up as ``load_file`` would leave it for a 2-channel file.** (1 connections) — `tests/unit/gui/test_data_panel.py`
- **JASCO reader metadata must survive the load into MeasurementSet.** (1 connections) — `tests/unit/gui/test_data_panel.py`
- **A DataPanel populated with a tiny three-point dataset (face values in M).** (1 connections) — `tests/unit/gui/test_data_panel.py`
- **Changing the Imported Unit must reinterpret face values via Pint.** (1 connections) — `tests/unit/gui/test_data_panel.py`
- **Every committed cell edit immediately rebuilds the MeasurementSet.** (1 connections) — `tests/unit/gui/test_data_panel.py`
- **The Display Unit combo emits ``display_unit_changed`` independently.** (1 connections) — `tests/unit/gui/test_data_panel.py`
- **.test_display_unit_combo_emits()** (1 connections) — `tests/unit/gui/test_data_panel.py`
- **.test_display_unit_does_not_emit_data_loaded()** (1 connections) — `tests/unit/gui/test_data_panel.py`
- **.test_unit_change_does_not_rewrite_table_values()** (1 connections) — `tests/unit/gui/test_data_panel.py`
- **.test_unit_change_rescales_underlying_molar()** (1 connections) — `tests/unit/gui/test_data_panel.py`
- **.test_single_cell_edit_emits_and_rebuilds()** (1 connections) — `tests/unit/gui/test_data_panel.py`

## Relationships

- [[EnSight Loading & Channels]] (9 shared connections)
- [[MeasurementSet & FitResult]] (5 shared connections)
- [[Plot Style Tests]] (1 shared connections)
- [[Channel Combo Tests]] (1 shared connections)

## Source Files

- `tests/unit/gui/test_data_panel.py`

## Audit Trail

- EXTRACTED: 52 (87%)
- INFERRED: 8 (13%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*