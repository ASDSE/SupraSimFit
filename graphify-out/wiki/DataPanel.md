# DataPanel

> God node · 51 connections · `gui/widgets/data_panel.py`

**Community:** [[EnSight Loading & Channels]]

## Connections by Relation

### calls
- [[._setup_ui()]] `EXTRACTED`
- [[load_measurements]] `EXTRACTED`
- [[multi_channel_panel()]] `EXTRACTED`
- [[loaded_panel()]] `EXTRACTED`
- [[read_raw_concentrations]] `EXTRACTED`
- [[.test_load_real_ensight_no_modal_multichannel()]] `EXTRACTED`
- [[.test_switch_channel_resets_via_emit()]] `EXTRACTED`
- [[.test_jasco_metadata_forwarded_to_measurement_set()]] `EXTRACTED`
- [[format_channel_label]] `EXTRACTED`

### conceptually_related_to
- [[Plate-reader placeholder concentration flag]] `INFERRED`

### contains
- [[data_panel.py]] `EXTRACTED`

### imports
- [[fitting_session.py]] `EXTRACTED`
- [[test_data_panel.py]] `EXTRACTED`

### method
- [[.load_file()]] `EXTRACTED`
- [[._push_buffer_to_ms()]] `EXTRACTED`
- [[._on_channel_changed()]] `EXTRACTED`
- [[._refresh_after_load()]] `EXTRACTED`
- [[._make_ms()]] `EXTRACTED`
- [[._populate_channel_combo()]] `EXTRACTED`
- [[._populate_table()]] `EXTRACTED`
- [[.clear()]] `EXTRACTED`
- [[._on_load_concentrations()]] `EXTRACTED`
- [[._set_concentration_controls_enabled()]] `EXTRACTED`
- [[._setup_ui()]] `EXTRACTED`
- [[._slice_channel()]] `EXTRACTED`
- [[.__init__()]] `EXTRACTED`
- [[._on_cell_changed()]] `EXTRACTED`
- [[._update_info()]] `EXTRACTED`
- [[.focus_concentration_table()]] `EXTRACTED`
- [[.measurement_set()]] `EXTRACTED`
- [[._on_imported_unit_changed()]] `EXTRACTED`
- [[._on_save_concentrations()]] `EXTRACTED`
- [[.set_display_unit()]] `EXTRACTED`

### rationale_for
- [[Load measurement data and edit the concentration vector inline.      Signals]] `EXTRACTED`

### references
- [[READERS]] `EXTRACTED`

### uses
- [[MeasurementSet]] `INFERRED`
- [[FittingSession]] `INFERRED`
- [[InfoGroupBox]] `INFERRED`
- [[_GroupedPlain]] `INFERRED`
- [[_GroupedWithInfo]] `INFERRED`
- [[MeasurementSet]] `INFERRED`
- [[AssayType]] `INFERRED`
- [[FitResult]] `INFERRED`
- [[TestChannelCombo]] `INFERRED`
- [[TestDisplayUnitSignal]] `INFERRED`
- [[TestEnsightLoadIntegration]] `INFERRED`
- [[TestImportedUnitReinterpret]] `INFERRED`
- [[TestJascoLoadIntegration]] `INFERRED`
- [[TestLiveCommit]] `INFERRED`

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*