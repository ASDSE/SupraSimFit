# FittingSession

> God node · 75 connections · `gui/fitting_session.py`

**Community:** [[FittingSession Export]]

## Connections by Relation

### calls
- [[test_plot_stays_embedded_through_ensight_load_and_switch()]] `EXTRACTED`
- [[test_sidebar_has_no_hard_maxwidth_cap()]] `EXTRACTED`

### conceptually_related_to
- [[DownloadWorker]] `INFERRED`

### contains
- [[fitting_session.py]] `EXTRACTED`

### imports
- [[session.py]] `EXTRACTED`
- [[main_window.py]] `EXTRACTED`
- [[export_multiple_dialog.py]] `EXTRACTED`
- [[test_fitting_session_layout.py]] `EXTRACTED`

### inherits
- [[QWidget]] `EXTRACTED`

### method
- [[._setup_ui()]] `EXTRACTED`
- [[._refresh_plot()]] `EXTRACTED`
- [[._default_save_name()]] `EXTRACTED`
- [[.export_raw_data()]] `EXTRACTED`
- [[.__init__()]] `EXTRACTED`
- [[._distributions_export_config()]] `EXTRACTED`
- [[.run_fit()]] `EXTRACTED`
- [[.save_distributions_plot()]] `EXTRACTED`
- [[.export_plot()]] `EXTRACTED`
- [[.export_results()]] `EXTRACTED`
- [[.export_results_txt()]] `EXTRACTED`
- [[.import_results()]] `EXTRACTED`
- [[.load_demo_ida()]] `EXTRACTED`
- [[.load_style_template()]] `EXTRACTED`
- [[._on_assay_type_changed()]] `EXTRACTED`
- [[._on_data_loaded()]] `EXTRACTED`
- [[._on_fit_complete()]] `EXTRACTED`
- [[.open_export_multiple_dialog()]] `EXTRACTED`
- [[.save_style_template()]] `EXTRACTED`
- [[._connect_signals()]] `EXTRACTED`

### rationale_for
- [[One complete fitting workflow: data → preprocess → configure → fit → visualize.]] `EXTRACTED`

### shares_data_with
- [[FittingMainWindow]] `EXTRACTED`

### uses
- [[MeasurementSet]] `INFERRED`
- [[FitResult]] `INFERRED`
- [[AssayType]] `INFERRED`
- [[FitConfig]] `INFERRED`
- [[DataPanel]] `INFERRED`
- [[InfoGroupBox]] `INFERRED`
- [[PlotWidget]] `INFERRED`
- [[DistributionWidget]] `INFERRED`
- [[SaveDistributionsPlotDialog]] `INFERRED`
- [[PlotStyleWidget]] `INFERRED`
- [[AssayConfigPanel]] `INFERRED`
- [[BoundsPanel]] `INFERRED`
- [[ExportMultipleDialog]] `INFERRED`
- [[FitSummaryWidget]] `INFERRED`
- [[PreprocessingPanel]] `INFERRED`
- [[FitWorker]] `INFERRED`
- [[ReplicaPanel]] `INFERRED`
- [[FitConfigPanel]] `INFERRED`
- [[ExportableArtefact]] `INFERRED`
- [[SessionState]] `INFERRED`

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*