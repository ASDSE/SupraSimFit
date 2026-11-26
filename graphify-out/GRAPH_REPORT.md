# Graph Report - SupraSimFit  (2026-11-26)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 9495 nodes · 26159 edges · 257 communities (166 shown, 91 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 2524 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `36940f2f`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Assay Base Classes
- Sensitivity Run Configuration
- Fit Configuration and Bounds
- Theme and Appearance Mode
- Addition Error Validation Tests
- Uncertainty Budget Elasticities
- Custom Button Widgets
- Results CSV Export
- Input-Aware Weighted Fitting
- Fit Result Container
- Sensitivity Result Display
- Fit Diagnostics Tests
- Variable Projection Fitting
- Input Uncertainty Specs
- Measurement Set Replicas
- Assay Types and Residuals
- Fit Metrics and Fingerprints
- Plot Theme Styling
- Dye-Alone Calibration Assay
- Diagnostics Serialization
- Input-Aware Verdict Tests
- Menu Rendering
- Noise Law Model
- Fit Results Serialization
- Reference Screen Rendering
- Binding Condition Entry
- Main Window Screenshots
- Plot Appearance Settings
- Uncertainty Input Entry
- Session Model State
- Replicate Metric Formatting
- Validation Table Tests
- Plot Appearance Preferences
- Sensitivity Analysis Form
- Simulation View Settings
- Heatmap and Chart Views
- Session Lifecycle Tests
- Validation Coverage Checks
- Diagnostics Text Formatting
- Ka Profile Intervals
- Interval and Unit Formatting
- Profile Path Geometry
- Fitting Session Exports
- Hidden Fits Tests
- Addition Error Inflation
- Fit Results View Tests
- Validation Store Tests
- Settings Window
- Measurement File Readers
- Shared Addition Errors
- Sobol Sensitivity Indices
- Test Assay Fixtures
- Dataset Loading
- Demo IDA Integration Tests
- Budget Validation Tests
- Assay Forward Model
- Session Edits and Runs
- Confidence View
- Binding Model Help
- GUI Layout Tests
- Data Preprocessing Pipeline
- Validation Run Jobs
- Binding Form
- Equilibrium Forward Models
- Conflict Verdict Tests
- Dilution Speciation Tests
- Results Import Checks
- Example Data and Design Docs
- GDA Assay Tests
- Session Copy and Cancellation
- Design System Contrast Tests
- Ensight Reader
- Binding View Tests
- Equilibrium Precision Tests
- Dilution Recovery Tests
- Titration Simulation
- Validation Statistics Tests
- Jasco Reader
- Per-Replicate Fitting
- Dilution Conditions
- BMG Workbook Parser
- Simulation View
- Export Multiple Dialog
- Status Message Tests
- Ka Display Helpers
- Measurements View
- Input Uncertainty View
- Legacy Results Loading
- Build and Release Workflow
- Plot Navigation
- Fit Cancellation Tests
- Binding View
- Plot Design Docs
- Graph CI Workflow
- Confidence View Tests
- CSV Reader
- Design Style Icons
- Uncertainty View Tests
- Layout Rules Checks
- Fit Results View
- Plot Data Preparation Tests
- Tab-Separated File IO
- Summary Statistics Helpers
- Checkbox and Dropdown Widgets
- Render Harness Tests
- Empty State Views Tests
- GUI Test Helpers
- Concentration Vector IO
- Multi-File Replica Loading
- Help Window Tests
- 1:2 Host-Guest Speciation
- Slider Knob Values
- Sensitivity Background Worker
- Profile Plot Readout
- Elided Labels and Plot Header
- Fit Result Reproduction Checks
- Profile Interval Cutting
- Update Check Lifecycle Tests
- Batch Export and Titration Figure
- Export Test Fixtures
- Reference Grid Interval Tests
- Replicate Outlier Detection
- Update Download Worker
- Concentration Validation
- MeasurementSet Writers
- Competitive GDA Speciation
- Sobol Sampling Design Tests
- Editable Slider Ends
- Run Actions and Failures
- Titration Plot Rendering
- Species Readout Legend
- MeasurementSet Construction Tests
- Sensitivity Worker Processes
- Segmented Control Widget
- Help Window Dialog
- Release Version Checking
- Reference Screens and Legacy
- Files Table Widget
- Documentation Currency Tests
- Input-Aware Documentation Tests
- Second Step Sentence Formatting
- Session Settings
- Export Artefact Builders
- Model Notification Consistency
- Set Concentrations Tests
- Profile Curve Deviance
- Word-Breaking Labels
- Binding Model Form
- Fit Cancellation and Bounds
- Slider Widget
- Input Shift Formatting
- Analysis Dialog Tests
- Reader Registry Test Stubs
- Plot Zoom and Pan
- Session File Paths
- Isolated Test Fixtures
- Interval Coverage Metrics
- Parameter Bound Entries
- View Side Panels
- Plot Axis Text Sizes
- Replica Data Access Tests
- Validation Package
- Simulation Data Loading
- MeasurementSet Immutability Tests
- DBA Model Tests
- Profile Likelihood References
- File Filters and Help Text
- IO Data Integrity Tests
- Root Robustness Tests
- Independent Equilibrium Verification
- Reader Writer Interfaces
- Status Bar
- Analysis Configuration Checks
- Simulation Grid and Noise
- Off-Screen Window Fixtures
- Assay Conversion Tests
- Competitive Model Tests
- Linear Model Tests
- Weighted Interval Metrics
- Bound Resting Tests
- Channel Labels
- Active Mask Management
- Replicate Selection Copies
- Validation Hash Coverage
- Sensitivity and Dilution References
- Model Bounds Summary
- Window Flash Prevention
- Assay Category Tests
- Data Fingerprint Tests
- Extreme Input Tests
- Bound Resting Rule
- Robustness Criteria References
- Replicate Outlier References
- Fit Verdict Statistics
- Value Equality Helper
- Penalised Interval Widening
- Residual Solve Helpers
- Profile Interval Display Tests
- Stepwise Titration Engine Tests
- Weak Identification Pretest
- Plot Labels and Export
- Diagnostic P-Values
- Session Views Package
- Non-Blocking Dialog Recording
- Diluted Fit Fixture
- Fit Fixture Copies
- Replicate Exclusion Checks
- Combined Misfit Test Findings
- Misfit and Conflict Summary
- Profile Curve Drawing
- Profile Curve Height
- Profile Reading Cut-off
- Ka Acceptance Check
- Drawn Profile Curve
- App Theme Source
- Window Theme Management
- Theme Mode Switching
- Titration Plot Contents
- Titration Plot Curves
- Fit Quality Statistics
- Fit Quality Metrics
- Binding Constant Spread
- Binding Constant Samples Histogram
- Widgets Package
- fitting-app
- Tryptamine expected FL test data

## God Nodes (most connected - your core abstractions)
1. `AssayType` - 286 edges
2. `ErrorModel` - 242 edges
3. `MeasurementSet` - 232 edges
4. `InputSpec` - 222 edges
5. `FitConfig` - 217 edges
6. `FitResult` - 202 edges
7. `SessionModel` - 200 edges
8. `Theme` - 193 edges
9. `Projection` - 192 edges
10. `IDAAssay` - 160 edges

## Surprising Connections (you probably didn't know these)
- `docs/scientific-summary.md (reference)` --semantically_similar_to--> `Scientific Summary of the Binding Assay Fitting Toolkit`  [INFERRED] [semantically similar]
  Readme.md → docs/scientific-summary.md
- `test_the_settings_show_what_the_mode_needs_and_lock_during_a_run()` --uses--> `SensitivityMode`  [INFERRED]
  tests/unit/gui/test_sensitivity_view.py → core/pipeline/sensitivity.py
- `test_a_duplicate_session_takes_the_appearance_of_the_one_it_copies()` --uses--> `Change`  [INFERRED]
  tests/unit/gui/test_plot_appearance.py → gui/session_model.py
- `test_setting_an_appearance_says_so_once_and_setting_it_again_says_nothing()` --uses--> `Change`  [INFERRED]
  tests/unit/gui/test_plot_appearance.py → gui/session_model.py
- `scores_off_by()` --indirect_call--> `released()`  [INFERRED]
  tests/unit/test_released_results.py → gui/main_window.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Rate judging rule** — validation_readme_bradley_criterion, validation_readme_clopper_pearson, validation_readme_ladder, validation_readme_criteria [EXTRACTED 0.85]
- **Saved figure export pipeline** — docs_design_design_saved_figure, docs_design_design_export_stacked, docs_design_design_export_widget, docs_design_design_figure_head [EXTRACTED 0.90]
- **Model checking and verdict** — docs_scientific_summary_lack_of_fit_test, docs_scientific_summary_conflict_statistic, docs_scientific_summary_verdict, docs_scientific_summary_input_aware_interval [EXTRACTED 0.90]
- **Bundled example assay datasets** — data_dba_system_host_to_dye, data_dye_alone, data_gda_system, data_ida_system, data_readme [INFERRED 0.80]
- **Pint unit boundary design** — docs_pint_findings_quantities_at_edges, docs_pint_findings_paramkind, docs_pint_audit_au_signal_dimension_fix, docs_pint_findings_never_to_base_units [INFERRED 0.80]

## Communities (257 total, 91 thin omitted)

### Community 0 - "Assay Base Classes"
Cohesion: 0.01
Nodes (181): ParamKind, input_replica_ids(), parameters_on_bound(), ParameterSummary, reports_conditional(), Amount, binding_constants(), _bound_text() (+173 more)

### Community 1 - "Sensitivity Run Configuration"
Cohesion: 0.01
Nodes (81): AxisScale, badge(), Button, Callout, canvas_section(), card_edge(), card_fill(), _card_rule() (+73 more)

### Community 2 - "Fit Configuration and Bounds"
Cohesion: 0.01
Nodes (146): aware(), dba_signal(), moved_series(), test_a_diluting_titrant_moves_the_series_and_dilutes_the_sample_by_the_volume_added(), test_a_row_of_stated_additions_carries_the_factor_each_interval_was_widened_by(), test_a_titration_without_addition_error_is_drawn_from_its_noise_stream_alone(), test_an_addition_error_a_scenario_cannot_carry_is_refused(), test_each_replicate_is_measured_on_its_own_series_of_additions() (+138 more)

### Community 3 - "Theme and Appearance Mode"
Cohesion: 0.02
Nodes (76): BaseAssay, create_dba_host_to_dye(), GDAAssay, H2GAssay, HG2Assay, IDAAssay, AssayMetadata, get_metadata() (+68 more)

### Community 4 - "Addition Error Validation Tests"
Cohesion: 0.01
Nodes (118): facts(), test_a_weighted_fit_reports_the_law_it_was_weighted_by(), test_the_misfit_rate_is_named_by_the_test_that_ran(), test_the_reported_interval_is_judged_and_its_cost_reported_beside_it(), coverage_rows(), test_a_case_stops_only_once_every_check_reading_it_has_passed_as_well(), test_a_case_that_fails_at_the_first_stage_goes_on_to_the_next(), test_a_case_whose_rate_has_passed_stops_where_it_is() (+110 more)

### Community 5 - "Uncertainty Budget Elasticities"
Cohesion: 0.01
Nodes (120): linear_regression(), addition_noise_covariance(), AdditionDraws, _covariance_root(), lack_of_fit(), no_scatter(), _noise_fraction(), runs_test() (+112 more)

### Community 6 - "Custom Button Widgets"
Cohesion: 0.02
Nodes (62): _all_valid(), _competitive_free_host(), competitive_signal_point(), _competitive_speciation(), _competitive_species_grid(), dba_signal(), dba_species(), gda_signal() (+54 more)

### Community 7 - "Results CSV Export"
Cohesion: 0.03
Nodes (41): Screen, theme(), _add_grid_line(), apply_plot_theme(), axis_box(), fit_line(), _follow_ticks_with_grid(), update() (+33 more)

### Community 8 - "Input-Aware Weighted Fitting"
Cohesion: 0.02
Nodes (56): DyeAloneAssay, bounds_from_dye_alone(), fit_assay(), fit_linear_assay(), fit_measurement_set(), FitConfig, assert_within_tolerance(), _make_dba_data() (+48 more)

### Community 9 - "Fit Result Container"
Cohesion: 0.02
Nodes (83): _block_order(), sobol_design(), sobol_indices_from_outputs(), sobol_indices_with_ci(), estimate_of(), quantities(), SobolEstimate, _assert_identical() (+75 more)

### Community 10 - "Sensitivity Result Display"
Cohesion: 0.03
Nodes (82): InputSpec, SpecKind, specs_from_dict(), specs_to_dict(), _count(), _kind_name(), restate(), spread_pct() (+74 more)

### Community 11 - "Fit Diagnostics Tests"
Cohesion: 0.02
Nodes (84): _density_ratio(), elasticities(), elasticity_perturbations(), homogeneity_tolerance(), identity_applies(), what_if(), WhatIf, axis_reaches_zero() (+76 more)

### Community 12 - "Variable Projection Fitting"
Cohesion: 0.02
Nodes (72): appearance(), PlotAppearance, _contrast(), _luminance(), restore_mode(), test_a_message_box_icon_stands_out_from_the_box_in_either_mode(), test_a_message_box_reads_in_either_mode(), test_the_mode_chosen_is_the_scheme_qt_draws_in_against_the_operating_system() (+64 more)

### Community 13 - "Input Uncertainty Specs"
Cohesion: 0.03
Nodes (66): FitResult, fit_replica_ids(), replica_order(), _fitted_offsets(), _legacy_input_ids(), _parameter_vector(), _record_assay(), _reproduces() (+58 more)

### Community 14 - "Measurement Set Replicas"
Cohesion: 0.03
Nodes (35): MeasurementReader, ResultWriter, _extract_metadata(), _find_bmg_sheet(), _find_header_row(), is_bmg_workbook(), parse_bmg_workbook(), _header_comment() (+27 more)

### Community 15 - "Assay Types and Residuals"
Cohesion: 0.03
Nodes (67): Budget, budget_of(), BudgetRow, homogeneity_sum(), ErrorModel, default_worker_count(), estimated_fit_count(), estimated_model_solves() (+59 more)

### Community 16 - "Fit Metrics and Fingerprints"
Cohesion: 0.04
Nodes (78): export_results_csv(), ends(), number(), _csv_rows(), _diluted_shared_result(), _input_aware_result(), _law(), _on_bound_result() (+70 more)

### Community 17 - "Plot Theme Styling"
Cohesion: 0.03
Nodes (52): _addition_loading(), _replicate_additions(), _titrant_stock(), addition_signal_loading(), _basis(), _factors(), inflation(), joint_inflation() (+44 more)

### Community 18 - "Dye-Alone Calibration Assay"
Cohesion: 0.03
Nodes (19): BarChip, _clear(), _extent(), heat_map(), HeatBar, HeatmapFigure, IndexChartView, IndexLegend (+11 more)

### Community 19 - "Diagnostics Serialization"
Cohesion: 0.03
Nodes (46): SharedSource, AnalysisForm, test_a_shared_source_is_named_with_the_inputs_it_moves(), _heatmap(), _plain(), test_a_fixed_seed_must_be_a_whole_number_the_analysis_accepts(), test_a_heatmap_axis_reaching_zero_at_its_span_blocks_the_run_naming_it_and_the_span(), test_a_heatmap_axis_that_is_fixed_used_twice_or_shared_only_blocks_the_run_naming_the_input() (+38 more)

### Community 20 - "Input-Aware Verdict Tests"
Cohesion: 0.03
Nodes (16): _in_file(), MeasurementSet, _experiment(), _scaled(), demo(), test_import_of_a_file_written_before_the_arithmetic_marker_is_shown_as_stored(), _demo(), _fit() (+8 more)

### Community 21 - "Menu Rendering"
Cohesion: 0.06
Nodes (66): AssayType, test_the_model_line_names_a_calibration_as_the_badge_does_and_claims_no_interval(), _assay(), _compensated_bounds(), _compensated_hg2(), _gda_offset_on_its_floor(), _hand_built(), _hg2_truth_signal() (+58 more)

### Community 22 - "Noise Law Model"
Cohesion: 0.04
Nodes (7): AdditionsEntry, InputEntry, SourceEntry, UncertaintyForm, input_labels(), test_an_assay_with_no_association_constant_states_nothing_and_says_why(), test_the_inputs_are_the_assays_perturbable_inputs_named_as_every_report_names_them()

### Community 23 - "Fit Results Serialization"
Cohesion: 0.04
Nodes (25): _fixed_inputs(), cut(), FittedParameters, _norms(), ProjectedFit, Projection, at(), judge() (+17 more)

### Community 24 - "Reference Screen Rendering"
Cohesion: 0.05
Nodes (47): fake_run(), run(), made_on(), state_dilution(), _deliver_sensitivity(), _load(), _session(), _settle() (+39 more)

### Community 25 - "Binding Condition Entry"
Cohesion: 0.05
Nodes (49): status_messages(), _assert_back(), _assert_hidden(), _curves(), _deliver(), _deliver_sensitivity(), _diluted_session(), _numbers() (+41 more)

### Community 26 - "Main Window Screenshots"
Cohesion: 0.04
Nodes (31): format_channel_label(), Dataset, file_filter(), _format_of(), _from_file(), _make_ms(), readable_extensions(), _slice_channel() (+23 more)

### Community 27 - "Plot Appearance Settings"
Cohesion: 0.05
Nodes (4): _edit(), edit(), _format_remaining(), retire()

### Community 28 - "Uncertainty Input Entry"
Cohesion: 0.04
Nodes (39): _laid_out_width(), _on_bound(), _over_white(), _replicates_on_bound(), _show(), _shown_fits(), _shown_text(), _spread_per_replica() (+31 more)

### Community 29 - "Session Model State"
Cohesion: 0.06
Nodes (16): density(), _Point, _Problem, held(), held(), stacked(), _Trace, limited_by() (+8 more)

### Community 30 - "Replicate Metric Formatting"
Cohesion: 0.06
Nodes (9): extract_concentrations_from_file(), read_raw_concentrations(), save_concentration_vector(), _caption(), _column(), SimulationView, _widget(), TestConcentrationRoundTrip (+1 more)

### Community 31 - "Validation Table Tests"
Cohesion: 0.05
Nodes (33): _diagnose(), at_edge(), AwareFit, AwareResult, conflict(), _edges(), _excess(), fit_jacobian() (+25 more)

### Community 32 - "Plot Appearance Preferences"
Cohesion: 0.06
Nodes (34): Conflict, FitDiagnostics, MisfitTest, rejections(), Verdict, verdict(), test_the_status_bar_names_the_test_a_rejected_model_failed_and_not_the_verdict(), test_a_conflict_is_called_out_about_the_inputs_together_with_the_way_to_review_it() (+26 more)

### Community 33 - "Sensitivity Analysis Form"
Cohesion: 0.05
Nodes (10): _more_sessions(), _open_window(), FittingMainWindow, released(), UpdateCheckWorker, test_load_data_offers_the_demo_and_fills_the_empty_session_on_screen(), _window(), test_the_switcher_lists_every_session_and_choosing_one_puts_it_on_screen() (+2 more)

### Community 34 - "Simulation View Settings"
Cohesion: 0.04
Nodes (24): _settings_at_end(), FittingSession, make_session(), build(), qapp(), session(), session(), test_add_files_adds_replicates_to_the_session_on_screen() (+16 more)

### Community 35 - "Heatmap and Chart Views"
Cohesion: 0.05
Nodes (25): _note(), plot_appearance_note(), _row(), SettingsWindow, worker_label(), launch(), badge(), appearance_mode() (+17 more)

### Community 36 - "Session Lifecycle Tests"
Cohesion: 0.08
Nodes (35): _overlay_data(), test_export_several_offers_no_folder_of_the_bundled_examples(), test_the_outlier_removal_the_demo_applied_shows_in_measurement_settings(), test_no_tick_label_of_the_empty_titration_is_cut_at_an_edge(), test_every_link_to_the_help_raises_the_one_window_at_its_section(), _ancestors(), _assert_revealed(), _callout_action() (+27 more)

### Community 37 - "Validation Coverage Checks"
Cohesion: 0.07
Nodes (12): _escape(), fmt_shift(), verdict_sentence(), _diagnostics(), _f_test(), _runs(), _shift(), test_a_log10_reading_is_never_written_coarser_than_the_spread_beside_it() (+4 more)

### Community 38 - "Diagnostics Text Formatting"
Cohesion: 0.05
Nodes (39): test_replicates_the_fit_left_out_are_named_with_what_the_intervals_rest_on(), per_replica_result(), _read(), result(), _shown(), test_a_binding_constant_held_fixed_has_no_interval_and_says_why(), test_a_column_of_own_fits_shares_a_power_of_ten_only_where_every_value_reads_as_itself(), test_a_curve_that_misses_the_data_is_called_out_and_a_fit_that_passes_is_not() (+31 more)

### Community 39 - "Ka Profile Intervals"
Cohesion: 0.05
Nodes (30): addition_loading(), perturb_titrant(), _require_rising(), shared_key(), source_problems(), validate(), _reported_sources(), sobol_jobs() (+22 more)

### Community 40 - "Interval and Unit Formatting"
Cohesion: 0.04
Nodes (5): BindingForm, dye_alone_keys(), test_every_field_shows_a_number_one_way_and_reads_back_both_ways_a_number_is_written(), test_a_constant_rests_on_its_bound_only_where_the_objective_there_is_no_higher_than_where_the_search_stopped(), rest()

### Community 41 - "Profile Path Geometry"
Cohesion: 0.05
Nodes (37): _dye_alone_help(), help_html(), parse_number(), assay_class(), _concentration_keys(), _form(), test_a_binding_constant_is_entered_in_inverse_molar(), test_a_bound_set_from_code_is_the_very_number_it_was_written_from() (+29 more)

### Community 42 - "Fitting Session Exports"
Cohesion: 0.06
Nodes (6): MenuColumns, MenuRow, _Popover, PopoverMenu, SessionPopover, notes()

### Community 43 - "Hidden Fits Tests"
Cohesion: 0.05
Nodes (39): ProfileResult, KaInterval, _bump_profile(), _conflicted(), _crossings(), _pixel(), stepped(), test_a_constant_its_bounds_fix_has_no_profile_plot() (+31 more)

### Community 44 - "Addition Error Inflation"
Cohesion: 0.05
Nodes (5): Grid, Noise, SimulationForm, test_every_model_opens_on_a_curve_with_every_species_coloured(), test_the_form_takes_a_binding_models_conditions_and_stock_in_their_units()

### Community 45 - "Fit Results View Tests"
Cohesion: 0.05
Nodes (11): _problem_list(), Refusal, test_the_help_examples_are_the_numbers_demo_ida_shows(), test_a_failed_run_says_why_and_keeps_the_last_result_shown(), test_a_run_counts_its_fits_on_the_status_bar_and_estimates_the_time_left(), test_a_run_uses_the_bounds_and_the_settings_stated(), capture(), test_a_seed_typed_and_run_at_once_is_the_seed_the_run_uses() (+3 more)

### Community 46 - "Validation Store Tests"
Cohesion: 0.04
Nodes (8): SessionModel, test_no_signal_reaches_an_edit_that_takes_no_argument_directly(), make_model(), build(), make_model(), build(), session_model(), test_a_copy_of_a_session_carries_its_simulation_settings()

### Community 47 - "Settings Window"
Cohesion: 0.06
Nodes (10): Simulation, SimulationProblem, test_a_single_replicate_or_a_lawless_overlay_is_refused_in_plain_words(), test_a_stated_stock_dilutes_the_totals_the_stock_lacks_through_the_fitters_forward_model(), test_choosing_dilution_offers_a_stock_ten_times_the_highest_titrant_concentration_of_the_grid(), test_fit_in_new_session_carries_the_data_as_shown_and_only_the_conditions(), test_reading_the_noise_takes_the_fitters_noise_law_in_the_fields_units(), test_settings_survive_a_save_and_load() (+2 more)

### Community 48 - "Measurement File Readers"
Cohesion: 0.06
Nodes (33): second(), _reference(), test_a_second_step_the_data_show_keeps_its_lower_limit(), test_data_with_one_binding_step_give_the_second_constant_no_lower_limit(), _bounded_solve(), _rank(), test_the_reference_counts_in_n_minus_p_only_what_its_best_fit_fitted(), test_the_reference_counts_no_binding_constant_its_best_fit_left_on_a_bound_of_the_box() (+25 more)

### Community 49 - "Shared Addition Errors"
Cohesion: 0.06
Nodes (3): projectable(), EmptyView, _shortcut()

### Community 50 - "Sobol Sensitivity Indices"
Cohesion: 0.06
Nodes (30): plot_appearance_default(), reset_plot_appearance_default(), set_plot_appearance_default(), export_results(), import_appearance(), import_results(), _read_results_file(), test_a_diluted_fit_with_a_shared_source_is_read_back_as_the_fit_it_was() (+22 more)

### Community 51 - "Test Assay Fixtures"
Cohesion: 0.06
Nodes (6): CompactIntervals, diamond(), IntervalChart, LegendRow, paint_symbol(), spaced_ticks()

### Community 52 - "Dataset Loading"
Cohesion: 0.05
Nodes (26): _magnitude(), state_binding(), session(), _tab_order(), test_a_condition_that_cannot_be_read_shows_no_number_under_input_uncertainty(), test_a_dye_alone_file_sets_the_signal_bounds_to_what_it_measured(), test_a_dye_alone_file_the_data_checks_refuse_is_named_with_the_refusal_itself(), test_a_stock_typed_in_its_field_reaches_the_fit_in_the_unit_shown() (+18 more)

### Community 53 - "Demo IDA Integration Tests"
Cohesion: 0.07
Nodes (11): _ka_grid(), _ka_text(), q(), refined(), _rank(), _refine_at(), _refine_minima(), _scan_turns() (+3 more)

### Community 54 - "Budget Validation Tests"
Cohesion: 0.04
Nodes (49): DBA host-to-dye titration data (8 replicates), Dye-alone calibration data (4 replicates), GDA titration data (3 replicates), IDA titration data (8 replicates), Example data metadata, DBA host-to-dye reference parameters, GDA reference parameters (CB7, nButanol, TNS dye), IDA reference parameters (+41 more)

### Community 55 - "Assay Forward Model"
Cohesion: 0.06
Nodes (9): _sample_dataframe(), _sample_measurement_set(), TestDataAccess, TestFingerprint, TestImmutability, TestReplicaManagement, TestSetConcentrations, TestToAssay (+1 more)

### Community 56 - "Session Edits and Runs"
Cohesion: 0.06
Nodes (9): fmt_species(), Overlay, species_groups(), tag_text(), _legend_items(), _Readout, SimulationPlots, species_pen() (+1 more)

### Community 57 - "Confidence View"
Cohesion: 0.05
Nodes (28): top(), _aware(), hg2_case(), ida_case(), _independent_one_ka_excess(), excess(), solve(), _noisy() (+20 more)

### Community 58 - "Binding Model Help"
Cohesion: 0.08
Nodes (36): _dba(), _diluted(), _dye_alone(), _gda(), _h2g(), _hg2(), _ida(), _same() (+28 more)

### Community 59 - "GUI Layout Tests"
Cohesion: 0.07
Nodes (8): get_step(), PreprocessingStep, register_step(), ZScoreReplicaFilter, _ms_few_replicas(), _ms_with_outlier(), TestRegistry, TestZScoreReplicaFilter

### Community 60 - "Data Preprocessing Pipeline"
Cohesion: 0.07
Nodes (5): EnsightReader, _minimal_ensight(), _read_legacy_var_signal(), TestParsing, TestSniffing

### Community 61 - "Validation Run Jobs"
Cohesion: 0.10
Nodes (22): competitive_species_point(), _assert_close(), _brackets_root(), _certify_free(), _check_competitive(), _check_stepwise(), _exact_root(), _host_balance() (+14 more)

### Community 62 - "Binding Form"
Cohesion: 0.06
Nodes (12): SensitivityRunError, FitWorker, _release(), SensitivityWorker, test_a_worker_failure_names_the_step_and_the_log(), test_a_fit_the_pipeline_refuses_is_reported_in_its_own_words(), raising(), test_worker_delivers_a_held_back_count_as_soon_as_a_cancel_is_seen() (+4 more)

### Community 63 - "Equilibrium Forward Models"
Cohesion: 0.10
Nodes (11): fit_measurement_set_per_replica(), _record_data(), _replica_fit(), clean_pr_result(), _config(), _ida_conditions(), _ida_ms(), noisy_pr_result() (+3 more)

### Community 64 - "Conflict Verdict Tests"
Cohesion: 0.09
Nodes (22): _accent_pixels(), check_window(), _name(), open_menu(), open_sections(), openers(), problems(), settle() (+14 more)

### Community 65 - "Dilution Speciation Tests"
Cohesion: 0.08
Nodes (25): JointRegion, ProfileSet, test_the_joint_region_is_the_pairs_at_or_over_their_own_cut_off_with_the_best_fit_and_both_bands(), move_pointer(), _show(), test_a_fit_with_no_binding_constant_says_there_is_nothing_to_profile(), test_a_fit_with_no_profile_and_no_data_asks_for_the_data_before_the_fit(), test_a_profile_that_failed_says_why_in_plain_words_beside_the_readings() (+17 more)

### Community 67 - "Example Data and Design Docs"
Cohesion: 0.09
Nodes (17): create_dba_dye_to_host(), DBAAssay, X(), TestDBAQuantityConditions, test_dba_projection_residual_is_the_model_residual_with_dilution(), TestDBAFailFast, _free_fixed_exactly(), _sig() (+9 more)

### Community 68 - "GDA Assay Tests"
Cohesion: 0.09
Nodes (4): JascoReader, _minimal_jasco(), TestParsing, TestSniffing

### Community 69 - "Session Copy and Cancellation"
Cohesion: 0.08
Nodes (20): export_batch(), ExportableArtefact, _broken(), _Emitter, _export_batch(), _export_plot(), _export_raw_data(), _import_results() (+12 more)

### Community 70 - "Design System Contrast Tests"
Cohesion: 0.09
Nodes (7): BindingView, _BoundRow, _caption(), _clear(), _ConditionRow, _grid(), _name()

### Community 71 - "Ensight Reader"
Cohesion: 0.06
Nodes (35): runs-on, steps, strategy, jobs, build, publish_release, os, name (+27 more)

### Community 72 - "Binding View Tests"
Cohesion: 0.06
Nodes (35): concurrency, group, env, ANTHROPIC_API_KEY, ANTHROPIC_MODEL, GRAPHIFY_NO_BACKUP, PYTHONHASHSEED, default (+27 more)

### Community 73 - "Equilibrium Precision Tests"
Cohesion: 0.08
Nodes (18): FitCancelled, ProfileWorker, watchful_fit(), run(), watchful_sensitivity(), run(), window(), dialogs() (+10 more)

### Community 74 - "Dilution Recovery Tests"
Cohesion: 0.06
Nodes (30): figure_head(), Input-aware interval, Inputs as entered interval, Two-part noise law var(y)=floor²+(proportional·y)², PlotHeader, PlotNavigation, Plots design (§7), Saved figure (+22 more)

### Community 76 - "Validation Statistics Tests"
Cohesion: 0.09
Nodes (3): summarize_parameters(), _replica(), TestSummarizeParameters

### Community 77 - "Jasco Reader"
Cohesion: 0.15
Nodes (19): _data(), _range(), _shown(), test_a_double_click_resets_the_view(), test_a_pinch_zooms(), test_a_plain_wheel_over_the_plot_scrolls_the_page_that_holds_it(), test_a_theme_change_keeps_the_zoom(), test_another_display_unit_frames_the_plot_again() (+11 more)

### Community 78 - "Per-Replicate Fitting"
Cohesion: 0.10
Nodes (19): _aware_fit(), _profile(), _show(), _shown(), _split_fit(), test_a_closed_end_far_below_the_others_never_reads_zero(), test_a_constant_with_no_interval_is_named_beside_the_one_drawn(), test_a_fit_whose_association_constant_records_no_interval_says_so() (+11 more)

### Community 79 - "Dilution Conditions"
Cohesion: 0.11
Nodes (13): axis_text_problems(), check(), clashing_names(), cut_axis_text(), cut_headers(), cut_labels(), cut_sideways(), interactive() (+5 more)

### Community 80 - "BMG Workbook Parser"
Cohesion: 0.14
Nodes (8): prepare_plot_data(), _noisy_ms(), _per_replicate_record(), _simple_fit_result(), _simple_ms(), TestMeanFollowsTheFittedReplicates, TestPrepPlotDataFits, TestPrepPlotDataReplicas

### Community 81 - "Simulation View"
Cohesion: 0.11
Nodes (6): ExportMultipleDialog, _row(), _data(), test_export_prefix_is_reused_only_for_the_same_dataset(), test_a_folder_that_cannot_be_made_is_said_in_plain_words(), test_the_failures_of_a_batch_are_said_in_plain_words()

### Community 82 - "Export Multiple Dialog"
Cohesion: 0.09
Nodes (18): budget_csv_rows(), row(), budget_refusal(), _csv_interval(), _csv_number(), build_artefacts(), _write_budget_csv(), _write_raw_csv() (+10 more)

### Community 83 - "Status Message Tests"
Cohesion: 0.12
Nodes (13): test_a_half_written_line_costs_its_own_row_and_no_other(), test_a_resumed_run_computes_only_the_missing_rows(), test_a_row_of_another_code_is_not_read_but_is_not_lost(), test_pruning_drops_only_the_rows_of_another_code(), test_pruning_repairs_a_damaged_file(), test_rows_come_back_as_they_went_in(), append(), load() (+5 more)

### Community 84 - "Ka Display Helpers"
Cohesion: 0.10
Nodes (4): _as_float(), TxtReader, TxtWriter, TestTxtReader

### Community 85 - "Measurements View"
Cohesion: 0.08
Nodes (13): _evaluate_batch(), _init_worker(), _run_job(), _thread_capped_children(), _worker_fit(), _evaluate(), test_a_batch_over_worker_processes_leaves_this_process_uncapped(), test_a_job_that_fails_outright_stops_the_batch_at_once_in_plain_words() (+5 more)

### Community 86 - "Input Uncertainty View"
Cohesion: 0.10
Nodes (18): _data(), _import(), _shown(), test_a_dilution_difference_without_data_reads_as_a_sentence(), test_import_keeps_the_replicate_selection_and_hides_a_fit_it_does_not_match(), test_import_of_a_file_without_a_replicate_record_names_the_selection_when_refused(), test_import_of_a_fit_made_on_the_loaded_data_is_shown_unchanged(), test_import_of_a_released_file_with_bare_number_conditions_is_checked_and_shown() (+10 more)

### Community 87 - "Legacy Results Loading"
Cohesion: 0.11
Nodes (4): menu(), PlotAppearanceView, body(), _widget()

### Community 88 - "Build and Release Workflow"
Cohesion: 0.11
Nodes (15): _axis_value(), budget_table(), BudgetTable, Cell, _decimals_apart(), _figures(), grid_label(), Heatmap (+7 more)

### Community 90 - "Fit Cancellation Tests"
Cohesion: 0.08
Nodes (13): help_off_screen(), _plain(), test_each_settings_side_panel_is_explained_in_its_section(), test_every_section_uses_one_heading_convention(), test_every_section_with_a_demo_plot_ends_on_its_demo_ida_example(), test_no_help_opens_as_a_modal_dialog_with_its_own_buttons(), test_the_binding_model_section_follows_the_model_chosen(), test_the_help_menu_raises_the_same_window_at_the_view_on_screen() (+5 more)

### Community 91 - "Binding View"
Cohesion: 0.11
Nodes (13): conflict_added(), conflict_p_value(), conflict_reference(), conflict_test(), _count_runs(), _draw_added(), _shift_operator(), _null_rejection_rates() (+5 more)

### Community 92 - "Plot Design Docs"
Cohesion: 0.12
Nodes (13): _open_menu(), _point_at(), render(), _settle(), _snapshot(), _wait(), test_a_pointer_with_no_plot_on_screen_is_refused(), test_a_render_at_a_scale_has_that_many_device_pixels_per_logical_pixel() (+5 more)

### Community 93 - "Graph CI Workflow"
Cohesion: 0.09
Nodes (3): SessionSettings, test_before_an_analysis_sensitivity_names_only_the_steps_still_to_take(), view()

### Community 94 - "Confidence View Tests"
Cohesion: 0.10
Nodes (12): _replicates(), test_a_mixed_law_recovers_both_of_its_components(), test_a_share_at_the_end_of_its_range_is_that_end_exactly(), test_blank_subtracted_replicates_read_a_finite_law(), test_constant_noise_at_a_near_zero_point_does_not_pull_the_share_to_one(), test_constant_noise_reads_a_share_of_zero_and_the_true_floor(), test_proportional_noise_reads_a_share_of_one_and_the_true_fraction(), test_replicate_scatter_refuses_data_that_has_no_scatter_to_read() (+4 more)

### Community 95 - "CSV Reader"
Cohesion: 0.10
Nodes (14): InputShift, test_a_conflict_lists_as_its_correction_only_the_inputs_it_judged(), test_moved_inputs_give_input_aware_beside_inputs_as_entered_with_one_power_of_ten(), test_moved_inputs_the_test_did_not_reject_quote_the_test_not_a_bound(), test_moved_inputs_whose_test_could_not_run_say_they_were_not_tested_and_why(), test_moved_inputs_without_a_conflict_list_their_shifts_unflagged(), test_both_readings_write_their_value_in_tabular_figures(), test_fit_quality_is_a_two_by_two_grid_with_noise_beside_the_replicates_used() (+6 more)

### Community 97 - "Uncertainty View Tests"
Cohesion: 0.14
Nodes (4): Knob, _three_figures(), unit_text(), _KnobRow

### Community 98 - "Layout Rules Checks"
Cohesion: 0.11
Nodes (16): _homoscedastic(), _no_number_above(), _single(), test_a_dba_edge_the_data_cannot_close_stays_open_however_high_the_bound_reaches(), test_a_fit_that_held_every_input_as_entered_draws_one_curve(), test_a_ka_bound_far_above_any_real_affinity_still_has_a_curve_at_every_point(), test_a_ka_the_model_cannot_be_solved_at_is_no_fit_rather_than_an_error(), profile_up_to() (+8 more)

### Community 99 - "Fit Results View"
Cohesion: 0.10
Nodes (12): _jasco(), test_channel_file_rejected(), test_duplicate_stems_disambiguated(), test_empty_paths_raises(), test_heterogeneous_declared_units_converted_before_stack(), test_mismatched_grid_rejected(), test_mismatched_point_counts_rejected(), test_placeholder_concentration_file_rejected() (+4 more)

### Community 100 - "Plot Data Preparation Tests"
Cohesion: 0.13
Nodes (15): _demo_ms(), _independent_fit(), _independent_ssr(), _projection(), _proportional_replicates(), test_a_one_ka_profile_is_cut_at_one_level_where_the_fit_pins_a_signal_parameter(), test_a_profile_handed_no_weights_is_unweighted_whatever_the_replicates_show(), test_a_profile_whose_fits_pin_nothing_the_best_fit_leaves_free_is_cut_at_one_level() (+7 more)

### Community 101 - "Tab-Separated File IO"
Cohesion: 0.10
Nodes (9): _again_on_display(), main(), _pointer(), render_all(), render_screen(), set_int(), test_the_command_renders_every_reference_screen_in_both_themes(), archive() (+1 more)

### Community 102 - "Summary Statistics Helpers"
Cohesion: 0.10
Nodes (12): _assay(), index_chart(), IndexChart, IndexRow, ordered_sources(), source_label(), source_plots(), SourcePlot (+4 more)

### Community 103 - "Checkbox and Dropdown Widgets"
Cohesion: 0.11
Nodes (10): test_a_field_one_run_writes_and_the_other_does_not_is_a_difference(), test_a_field_that_moved_is_named_with_its_case_and_seed(), test_a_key_only_one_run_holds_is_not_compared(), test_a_quantity_neither_run_could_produce_is_not_a_difference(), test_every_module_a_row_is_computed_in_is_hashed_with_everything_it_imports(), test_the_code_and_the_wall_times_are_not_compared(), test_the_whole_engine_package_is_hashed_and_not_only_the_fit_path(), test_two_runs_of_the_same_code_differ_in_nothing() (+2 more)

### Community 104 - "Render Harness Tests"
Cohesion: 0.12
Nodes (10): checks(), dialogs(), _ScriptedCheck, _settle(), _SlowToEnd, test_a_check_that_reported_is_deleted_only_once_its_thread_has_ended(), test_a_finished_check_lets_go_of_itself_and_not_of_the_check_that_replaced_it(), test_asking_for_a_check_while_one_is_running_says_so() (+2 more)

### Community 105 - "Empty State Views Tests"
Cohesion: 0.14
Nodes (3): TestFitViewAtMovedInputs, signal(), TestTheParametersTheLackOfFitTestCounts

### Community 106 - "GUI Test Helpers"
Cohesion: 0.16
Nodes (10): _bootstrap_ratios(), _flatness(), noise_law(), _read_share(), objective(), _scatter(), _scatter_sums(), _scattering_points() (+2 more)

### Community 107 - "Concentration Vector IO"
Cohesion: 0.10
Nodes (11): _draw(), fit_profile(), rows(), _with_points(), q_min(), _regular_grid_size(), test_narrowing_a_coefficient_bound_never_raises_the_profile(), test_per_replicate_profile_is_the_profile_of_the_average() (+3 more)

### Community 109 - "Help Window Tests"
Cohesion: 0.16
Nodes (15): _data(), fitted(), _holding(), _state(), test_a_cancelled_fit_leaves_the_previous_result_as_it_was(), test_a_condition_hides_the_fit_once_its_edit_is_finished_and_setting_it_back_shows_it_again(), test_a_fit_that_cannot_start_says_why(), test_a_fit_that_needs_a_refit_is_marked_out_of_date_everywhere() (+7 more)

### Community 112 - "Slider Knob Values"
Cohesion: 0.11
Nodes (6): concentration_problem(), at(), _molar_text(), _no_measurements(), _whose(), InvalidData

### Community 114 - "Profile Plot Readout"
Cohesion: 0.10
Nodes (4): DownloadWorker, _os_label(), _pick_asset(), UpdateAvailableDialog

### Community 115 - "Elided Labels and Plot Header"
Cohesion: 0.16
Nodes (12): _button(), _offered_folders(), _on_screen(), test_a_save_offers_the_folder_of_the_data_it_was_made_from(), test_every_empty_view_offers_load_data_and_the_demo_and_draws_no_bare_axes(), test_no_save_after_the_demo_offers_a_folder_inside_the_app(), test_no_view_says_there_is_no_analysis_while_it_runs(), test_no_view_says_there_is_no_fit_while_the_fit_runs() (+4 more)

### Community 116 - "Fit Result Reproduction Checks"
Cohesion: 0.12
Nodes (17): _ida(), _independent_two_ka(), profile(), at(), solve(), verdict(), test_a_design_effect_below_one_or_not_a_number_is_refused(), test_a_design_effect_moves_both_closed_edges_out_to_the_widened_cut_off() (+9 more)

### Community 117 - "Profile Interval Cutting"
Cohesion: 0.10
Nodes (9): NoiseBasis, test_a_mean_of_exactly_zero_leaves_every_weight_finite(), test_one_titration_cannot_show_a_noise_law(), test_replicates_that_are_exact_images_of_one_curve_show_no_law(), test_replicates_that_scatter_nowhere_cannot_show_a_noise_law(), test_the_law_round_trips_through_a_results_file(), test_the_level_is_the_variance_at_the_rms_signal(), test_the_share_set_holds_the_estimate_and_is_nothing_where_no_law_was_read() (+1 more)

### Community 118 - "Update Check Lifecycle Tests"
Cohesion: 0.13
Nodes (11): SensitivityResult, callouts(), _dropped_groups(), _duration(), _fitted_samples(), _no_index_reason(), seed_stat(), Stat (+3 more)

### Community 119 - "Batch Export and Titration Figure"
Cohesion: 0.11
Nodes (5): _Boundary, install_exception_hook(), log_dir(), unexpected(), boundary()

### Community 121 - "Reference Grid Interval Tests"
Cohesion: 0.13
Nodes (12): spec_fraction(), _record_designs(), test_a_stopped_sobol_run_keeps_the_sample_blocks_that_finished(), fake_fit(), outputs(), test_run_intervals_leave_out_rows_without_a_fit(), fake_fit(), log_ka() (+4 more)

### Community 122 - "Replicate Outlier Detection"
Cohesion: 0.17
Nodes (12): _cochran_limit(), replicate_outliers(), _replicate_projection(), _replicates(), test_a_replicate_that_needs_another_ka_is_excluded_by_name(), test_a_replicate_three_times_noisier_than_the_others_is_left_out_for_its_scatter(), test_every_replicate_kept_passes_the_limit_while_the_allowance_lasts(), test_replicates_that_share_ka_and_scatter_are_all_kept() (+4 more)

### Community 123 - "Update Download Worker"
Cohesion: 0.14
Nodes (4): is_newer(), newest_release(), test_a_beta_build_is_offered_the_newest_published_release_beta_or_stable(), TestIsNewer

### Community 124 - "Concentration Validation"
Cohesion: 0.11
Nodes (8): test_a_change_in_how_a_row_is_generated_or_scored_retires_the_rows(), test_another_numpy_or_scipy_retires_the_rows(), test_changing_what_the_code_does_retires_the_rows(), test_rewording_a_docstring_keeps_the_rows(), test_the_hash_covers_every_package_a_fit_goes_through(), code_hash(), _files(), _without_docstrings()

### Community 125 - "MeasurementSet Writers"
Cohesion: 0.16
Nodes (3): describe(), describe_log10(), TestDescribe

### Community 126 - "Competitive GDA Speciation"
Cohesion: 0.14
Nodes (4): ConditionalFit, _interval(), TestWhatWidenedTheInterval, _widened()

### Community 128 - "Editable Slider Ends"
Cohesion: 0.12
Nodes (9): _cut_interval(), _interval(), edge(), _read_steps(), halve(), test_a_gap_between_two_accepted_points_where_the_cut_off_steps_makes_the_interval_split(), test_an_accepted_stretch_that_begins_where_the_cut_off_steps_up_is_inside_the_interval(), test_the_interval_routine_finds_a_stretch_and_a_gap_that_lie_between_two_search_grid_nodes() (+1 more)

### Community 130 - "Titration Plot Rendering"
Cohesion: 0.14
Nodes (8): _binary_free_host(), _competitive_free_host(), balance(), _dye_signal(), _generate(), _stepwise_free_ligand(), _stepwise_signal(), _titration()

### Community 131 - "Species Readout Legend"
Cohesion: 0.15
Nodes (5): TitrationPlot, _many(), test_grey_draws_every_replicate_in_one_colour(), test_twelve_replicates_take_twelve_colours_and_the_next_ones_the_next_shape(), plot()

### Community 132 - "MeasurementSet Construction Tests"
Cohesion: 0.14
Nodes (6): test_a_job_that_dies_is_stored_as_an_error_under_its_own_key(), _case(), compute(), _error_row(), _one_pool(), TimeLimit

### Community 133 - "Sensitivity Worker Processes"
Cohesion: 0.21
Nodes (10): _cue(), _fitted(), _same(), test_fit_results_and_plot_appearance_draw_one_plot_whatever_the_replicate_display(), test_measurements_draws_the_same_points_raw_with_no_curve(), test_measurements_names_the_fitted_value_and_opens_fit_results(), test_the_cue_is_gone_while_a_fit_runs(), test_the_cue_is_gone_while_the_results_are_hidden() (+2 more)

### Community 134 - "Segmented Control Widget"
Cohesion: 0.13
Nodes (9): histogram(), Histogram, Marker, _offset_axis(), _reading_marker(), number(), _readings(), _row() (+1 more)

### Community 135 - "Help Window Dialog"
Cohesion: 0.14
Nodes (6): _equal(), TitrationData, _axes(), _drawn_text(), test_each_axis_text_size_is_one_even_step_up_at_one_weight(), test_the_x_axis_title_of_a_saved_figure_is_whole_at_every_size()

### Community 136 - "Release Version Checking"
Cohesion: 0.16
Nodes (7): literals(), _luminance(), test_both_themes_define_the_same_tokens_as_hex_colours(), test_no_module_of_the_interface_carries_a_literal(), test_the_heat_scale_rises_in_lightness_from_low_to_high(), test_the_literal_guard_catches_each_kind_of_offender(), test_the_reference_screens_are_the_ones_the_design_names_and_the_render_command_draws()

### Community 137 - "Reference Screens and Legacy"
Cohesion: 0.14
Nodes (8): average_fit(), dialogs(), diluted_fit(), diluted_fitted(), fit(), fitted(), slow_fit(), fake()

### Community 138 - "Files Table Widget"
Cohesion: 0.19
Nodes (4): _config_to_dict(), offsets_held_at_zero(), TestOffsetsHeldAtZero, fit()

### Community 140 - "Input-Aware Documentation Tests"
Cohesion: 0.19
Nodes (8): contrast(), test_a_disabled_slider_and_toggle_take_no_accent(), test_coloured_text_meets_aa_on_its_tint(), test_contrast_reference_values(), test_disabled_text_is_quiet_yet_readable_on_every_ground_a_disabled_control_stands_on(), test_text_meets_aa_on_every_background(), test_the_series_colours_stand_out_from_the_plot_surface(), test_the_species_colours_read_on_the_plot_and_borrow_no_other_meaning()

### Community 142 - "Session Settings"
Cohesion: 0.14
Nodes (6): _live_texts(), test_no_live_text_names_machinery_the_app_does_not_have(), test_the_architecture_table_names_every_pipeline_module(), test_the_documents_name_the_fit_the_app_performs(), test_the_scan_reaches_the_texts_a_reader_and_the_program_depend_on(), test_the_validation_readme_lists_every_check_with_its_claim_and_criterion()

### Community 143 - "Export Artefact Builders"
Cohesion: 0.14
Nodes (6): test_the_binding_model_help_points_at_the_view_the_uncertainties_are_entered_in(), test_the_instructions_list_every_module_of_the_fitting_pipeline(), test_the_readme_explains_every_basis_a_noise_law_can_report(), test_the_readme_explains_every_verdict_a_fit_can_report(), test_the_validation_readme_names_every_check_the_package_runs(), test_the_validation_readme_quotes_each_check_s_own_claim()

### Community 144 - "Model Notification Consistency"
Cohesion: 0.19
Nodes (6): test_a_field_named_as_ignored_does_not_decide_the_exit_status(), _compare(), _list_cases(), _list_checks(), main(), tables()

### Community 146 - "Profile Curve Deviance"
Cohesion: 0.19
Nodes (6): curve(), Curve, deviance(), _read(), test_a_split_input_aware_reading_draws_the_stretches_of_its_own_penalised_profile(), curve()

### Community 147 - "Word-Breaking Labels"
Cohesion: 0.21
Nodes (6): get_bool(), set_bool(), _isolated_settings(), test_get_bool_returns_default_when_unset(), test_set_and_get_bool_round_trip(), test_string_backed_values_are_coerced()

### Community 149 - "Fit Cancellation and Bounds"
Cohesion: 0.19
Nodes (6): _holding(), _inconsistencies(), _signals(), test_an_edit_is_said_once(), test_every_notification_finds_the_model_consistent(), test_no_view_raises_and_each_draws_once()

### Community 151 - "Input Shift Formatting"
Cohesion: 0.17
Nodes (4): DesignStyle, _app_icon_path(), start_application(), fusion()

### Community 152 - "Analysis Dialog Tests"
Cohesion: 0.18
Nodes (4): icon(), pixmap(), svg(), test_every_icon_is_valid_svg()

### Community 154 - "Plot Zoom and Pan"
Cohesion: 0.17
Nodes (7): _design_fits(), ka_blocks(), on_bound_note(), Spread, spread(), withheld_note(), withheld_title()

### Community 156 - "Isolated Test Fixtures"
Cohesion: 0.21
Nodes (6): region(), test_a_cell_is_judged_against_its_own_cut_off(), test_a_cell_the_model_could_not_be_solved_in_is_outside_the_region(), test_a_pair_is_read_off_the_surface_the_region_is_drawn_from(), test_a_pair_outside_the_region_s_box_is_outside_the_region(), region_excess()

### Community 160 - "View Side Panels"
Cohesion: 0.20
Nodes (4): qapp(), test_the_fitted_state_is_drawn_after_the_fit_and_its_profile(), noting_snapshot(), test_the_heatmap_state_reads_the_cell_under_the_pointer()

### Community 162 - "Replica Data Access Tests"
Cohesion: 0.25
Nodes (3): _Accepter, _Fallback, _Rejecter

### Community 164 - "Simulation Data Loading"
Cohesion: 0.27
Nodes (3): side(), _SidePanel, _View

### Community 165 - "MeasurementSet Immutability Tests"
Cohesion: 0.20
Nodes (5): badge(), config_summary(), figure_caption(), figure_notes(), KaBlock

### Community 166 - "DBA Model Tests"
Cohesion: 0.20
Nodes (4): store(), results(), code_copy(), results()

### Community 167 - "Profile Likelihood References"
Cohesion: 0.22
Nodes (5): _hg2_ms(), test_a_profile_asked_to_stop_ends_at_its_next_solve(), test_stated_additions_widen_the_joint_region_and_its_bands_as_they_widen_the_reported_intervals(), test_the_profile_carries_the_fit_it_belongs_to_exactly(), test_the_profile_meets_its_cut_off_exactly_where_the_reported_interval_ends()

### Community 170 - "Root Robustness Tests"
Cohesion: 0.28
Nodes (5): heatmaps(), ka_axis(), _ka_ticks(), _linear_ticks(), _unit_after()

### Community 172 - "Reader Writer Interfaces"
Cohesion: 0.22
Nodes (5): delta_e2000(), _lab(), over(), test_delta_e2000_reference_values(), test_each_replicate_colour_reads_on_the_plot_and_apart_from_every_other_mark()

### Community 174 - "Analysis Configuration Checks"
Cohesion: 0.25
Nodes (5): jobs(), test_a_pool_that_never_finishes_a_row_ends_the_run_rather_than_looping(), test_the_jobs_a_dead_pool_left_unanswered_go_on_a_new_one(), one_pool(), _execute()

### Community 175 - "Simulation Grid and Noise"
Cohesion: 0.22
Nodes (9): addition-* checks, before-after check, validation.criteria (operating_characteristic, ladder_operating_characteristic), fit_measurement_set, Seed ladder 100→200→400, MeasurementSet, core.pipeline.inputs.perturb_titrant, Result store (validation/results/<check>.jsonl) (+1 more)

### Community 176 - "Off-Screen Window Fixtures"
Cohesion: 0.29
Nodes (4): AwareProfile, reported(), result(), test_a_profile_given_one_cut_off_array_fills_the_other_from_its_constant_level()

### Community 177 - "Assay Conversion Tests"
Cohesion: 0.25
Nodes (3): _two_digits(), test_the_readme_carries_the_words_a_fit_prints_where_no_law_can_be_read(), test_the_law_is_described_in_one_sentence()

### Community 178 - "Competitive Model Tests"
Cohesion: 0.32
Nodes (5): replicate_scatter(), test_the_guards_change_nothing_where_no_mean_is_zero_and_every_point_scatters(), _unguarded_share(), objective(), scatter()

### Community 179 - "Linear Model Tests"
Cohesion: 0.29
Nodes (3): _binding_constant_keys(), _ka_boxes(), _replicate_values()

### Community 183 - "Active Mask Management"
Cohesion: 0.29
Nodes (4): _close(), _controls(), _ink(), test_every_disabled_control_draws_its_text_and_icon_in_text_disabled()

### Community 187 - "Model Bounds Summary"
Cohesion: 0.29
Nodes (7): Bates & Watts 1988 Nonlinear Regression, F-test profile likelihood interval, Hodges & Sargent 2001 effective degrees of freedom, Input-aware penalised profile interval, Raue et al. 2009 profile-likelihood identifiability, Replicates averaged, not pooled, Signal coefficient degeneracy

### Community 189 - "Assay Category Tests"
Cohesion: 0.29
Nodes (5): test_choosing_a_model_in_its_menu_reaches_the_session(), test_before_any_fit_the_view_says_what_to_do_with_the_platform_s_shortcut(), test_before_any_fit_the_view_says_what_to_do_with_the_platform_s_shortcut(), test_an_assay_with_no_association_constant_offers_no_analysis_and_says_why(), test_before_any_run_the_view_says_what_to_do_with_the_platform_s_shortcut()

### Community 191 - "Extreme Input Tests"
Cohesion: 0.33
Nodes (3): qapp(), test_every_painted_component_of_the_fitted_demo_gets_its_room_and_no_plot_header_is_cut(), _wait()

### Community 192 - "Bound Resting Rule"
Cohesion: 0.33
Nodes (3): qapp(), test_every_menu_of_the_fitted_demo_fits_its_rows_and_its_window_and_marks_its_choice(), _wait()

### Community 203 - "Plot Labels and Export"
Cohesion: 0.33
Nodes (3): _strict_local_minima(), test_the_profiled_residuals_fall_and_rise_once_across_the_tight_binding_decades(), absolute_tolerance_host()

### Community 208 - "Fit Fixture Copies"
Cohesion: 0.40
Nodes (3): _svg_text(), test_a_saved_fit_carries_the_legend_the_curve_and_the_summary(), _write()

### Community 209 - "Replicate Exclusion Checks"
Cohesion: 0.40
Nodes (3): _raw_share(), objective(), test_replicates_that_differ_by_a_scale_factor_are_not_read_as_proportional_noise()

### Community 210 - "Combined Misfit Test Findings"
Cohesion: 0.50
Nodes (4): Dilution of fixed totals, Scaling identity of binding models, Sobol' 2001 global sensitivity indices, Sobol' variance decomposition

### Community 214 - "Profile Reading Cut-off"
Cohesion: 0.50
Nodes (4): Bradley 1978, Robustness?, Bradley's liberal criterion of robustness, one-step-null check, Clopper-Pearson exact limits

### Community 215 - "Ka Acceptance Check"
Cohesion: 0.67
Nodes (3): Cochran 1941 largest variance test, Hadi & Simonoff 1993 multiple outliers, Replicate test (forward search + Cochran)

### Community 216 - "Drawn Profile Curve"
Cohesion: 0.67
Nodes (3): Input conflict statistic, Lack-of-fit F test and runs test, Fit verdict (Holm procedure)

### Community 223 - "Fit Quality Metrics"
Cohesion: 0.67
Nodes (3): for_key(), accepts(), accepts()

## Ambiguous Edges - Review These
- `GDA reference parameters (CB7, nButanol, TNS dye)` → `Dye-alone calibration data (4 replicates)`  [AMBIGUOUS]
  data/Readme.md · relation: conceptually_related_to
- `Variable projection fit` → `Fitting workflow flowchart: load data, initial guess, multi-start optimization, RMSE/R² filtering, aggregate good fits, replicas loop, save results`  [AMBIGUOUS]
  docs/fitting_workflow.jpg · relation: conceptually_related_to

## Knowledge Gaps
- **59 isolated node(s):** `uv`, `fitting-app`, `Andrews & Cheng 2012 weak identification`, `Bates & Watts 1988 Nonlinear Regression`, `Cochran 1941 largest variance test` (+54 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 3933 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **91 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `AssayType` connect `Menu Rendering` to `Assay Base Classes`, `Fit Configuration and Bounds`, `Theme and Appearance Mode`, `Sensitivity Worker Processes`, `Uncertainty Budget Elasticities`, `Results CSV Export`, `Input-Aware Weighted Fitting`, `Fit Result Container`, `Files Table Widget`, `Fit Diagnostics Tests`, `Sensitivity Result Display`, `Input Uncertainty Specs`, `Variable Projection Fitting`, `Assay Types and Residuals`, `Export Artefact Builders`, `Plot Theme Styling`, `Input-Aware Verdict Tests`, `Noise Law Model`, `Fit Results Serialization`, `Reference Screen Rendering`, `Binding Condition Entry`, `Uncertainty Input Entry`, `Validation Table Tests`, `Simulation View Settings`, `Session Lifecycle Tests`, `Diagnostics Text Formatting`, `Interval and Unit Formatting`, `Profile Path Geometry`, `Addition Error Inflation`, `Validation Store Tests`, `Settings Window`, `Shared Addition Errors`, `Linear Model Tests`, `Dataset Loading`, `Confidence View`, `Assay Category Tests`, `Example Data and Design Docs`, `Session Copy and Cancellation`, `Validation Statistics Tests`, `Per-Replicate Fitting`, `Fit Fixture Copies`, `Export Multiple Dialog`, `Input Uncertainty View`, `Legacy Results Loading`, `Build and Release Workflow`, `Plot Navigation`, `Fit Cancellation Tests`, `Graph CI Workflow`, `Layout Rules Checks`, `Plot Data Preparation Tests`, `Summary Statistics Helpers`, `Help Window Tests`, `Fit Result Reproduction Checks`, `Replicate Outlier Detection`, `Competitive GDA Speciation`?**
  _High betweenness centrality (0.080) - this node is a cross-community bridge._
- **Are the 200 inferred relationships involving `AssayType` (e.g. with `BaseAssay` and `DBAAssay`) actually correct?**
  _`AssayType` has 200 INFERRED edges - model-reasoned connections that need verification._
- **What connects `uv`, `fitting-app`, `Andrews & Cheng 2012 weak identification` to the rest of the system?**
  _59 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Assay Base Classes` be split into smaller, more focused modules?**
  _Cohesion score 0.010790634543603664 - nodes in this community are weakly interconnected._
- **Why does `MeasurementSet` connect `Input-Aware Verdict Tests` to `Assay Base Classes`, `Fit Configuration and Bounds`, `Theme and Appearance Mode`, `Custom Button Widgets`, `Input-Aware Weighted Fitting`, `Reference Screens and Legacy`, `Fit Result Container`, `Fit Diagnostics Tests`, `Input Uncertainty Specs`, `Measurement Set Replicas`, `Assay Types and Residuals`, `Diagnostics Serialization`, `Fit Results Serialization`, `Binding Condition Entry`, `Main Window Screenshots`, `Uncertainty Input Entry`, `Progress Line Indicator`, `Session Lifecycle Tests`, `Diagnostics Text Formatting`, `Profile Likelihood References`, `Addition Error Inflation`, `Fit Results View Tests`, `Validation Store Tests`, `Settings Window`, `Weighted Interval Metrics`, `Dataset Loading`, `Assay Forward Model`, `GUI Layout Tests`, `Binding Form`, `Equilibrium Forward Models`, `Session Copy and Cancellation`, `Equilibrium Precision Tests`, `BMG Workbook Parser`, `Simulation View`, `Input Uncertainty View`, `Layout Rules Checks`, `Fit Results View`, `Plot Data Preparation Tests`, `Concentration Vector IO`, `Help Window Tests`, `Slider Knob Values`?**
  _High betweenness centrality (0.054) - this node is a cross-community bridge._

### Low-confidence Hints
_AMBIGUOUS edges — the extractor was unsure. Verify before acting on these._

- **What is the exact relationship between `GDA reference parameters (CB7, nButanol, TNS dye)` and `Dye-alone calibration data (4 replicates)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Variable projection fit` and `Fitting workflow flowchart: load data, initial guess, multi-start optimization, RMSE/R² filtering, aggregate good fits, replicas loop, save results`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._