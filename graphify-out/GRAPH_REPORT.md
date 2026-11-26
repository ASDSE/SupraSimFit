# Graph Report - SupraSimFit  (2026-11-26)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 9496 nodes · 26160 edges · 242 communities (148 shown, 94 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 2524 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `0c69c178`
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
- Plot Appearance View
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
- Progress Line Indicator
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
- Analysis Configuration Checks
- Off-Screen Window Fixtures
- Assay Conversion Tests
- Competitive Model Tests
- Linear Model Tests
- Bound Resting Tests
- Channel Labels
- Active Mask Management
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
- Project Tooling Config
- Penalised Interval Widening
- Residual Solve Helpers
- Stepwise Titration Engine Tests
- Weak Identification Pretest
- Profile Curve Drawing
- Profile Curve Height
- Unit Tests Package
- Utils Package

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
- `test_a_duplicate_session_takes_the_appearance_of_the_one_it_copies()` --uses--> `Change`  [INFERRED]
  tests/unit/gui/test_plot_appearance.py → gui/session_model.py
- `test_setting_an_appearance_says_so_once_and_setting_it_again_says_nothing()` --uses--> `Change`  [INFERRED]
  tests/unit/gui/test_plot_appearance.py → gui/session_model.py
- `curve()` --calls--> `Curve`  [INFERRED]
  tests/unit/gui/test_results.py → gui/confidence.py
- `test_the_settings_show_what_the_mode_needs_and_lock_during_a_run()` --uses--> `SensitivityMode`  [INFERRED]
  tests/unit/gui/test_sensitivity_view.py → core/pipeline/sensitivity.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Rate judging rule** — validation_readme_bradley_criterion, validation_readme_clopper_pearson, validation_readme_ladder, validation_readme_criteria [EXTRACTED 0.85]
- **Saved figure export pipeline** — docs_design_design_saved_figure, docs_design_design_export_stacked, docs_design_design_export_widget, docs_design_design_figure_head [EXTRACTED 0.90]
- **Model checking and verdict** — docs_scientific_summary_lack_of_fit_test, docs_scientific_summary_conflict_statistic, docs_scientific_summary_verdict, docs_scientific_summary_input_aware_interval [EXTRACTED 0.90]
- **Bundled example assay datasets** — data_dba_system_host_to_dye, data_dye_alone, data_gda_system, data_ida_system, data_readme [INFERRED 0.80]
- **Pint unit boundary design** — docs_pint_findings_quantities_at_edges, docs_pint_findings_paramkind, docs_pint_audit_au_signal_dimension_fix, docs_pint_findings_never_to_base_units [INFERRED 0.80]

## Communities (242 total, 94 thin omitted)

### Community 0 - "Assay Base Classes"
Cohesion: 0.02
Nodes (77): H2GAssay, HG2Assay, _all_valid(), _competitive_free_host(), competitive_signal_point(), _competitive_speciation(), _competitive_species_grid(), dba_signal() (+69 more)

### Community 1 - "Sensitivity Run Configuration"
Cohesion: 0.02
Nodes (59): _again_on_display(), main(), _pointer(), render_all(), render_screen(), Screen, appearance(), DesignStyle (+51 more)

### Community 2 - "Fit Configuration and Bounds"
Cohesion: 0.03
Nodes (126): AssayType, gda_species(), _point_weights(), _cochran_limit(), Projection, replicate_outliers(), _homoscedastic(), test_one_ka_intervals_cover_the_true_ka_at_about_the_stated_rate() (+118 more)

### Community 3 - "Theme and Appearance Mode"
Cohesion: 0.02
Nodes (52): AxisScale, badge(), Button, Callout, canvas_section(), card_edge(), card_fill(), _card_rule() (+44 more)

### Community 4 - "Addition Error Validation Tests"
Cohesion: 0.03
Nodes (93): ErrorModel, estimated_fit_count(), estimated_model_solves(), SensitivityConfig, SensitivityMode, _scaled(), test_fitted_constants_follow_the_concentration_unit(), _grid() (+85 more)

### Community 5 - "Uncertainty Budget Elasticities"
Cohesion: 0.02
Nodes (72): budget_of(), _density_ratio(), elasticities(), elasticity_perturbations(), homogeneity_sum(), homogeneity_tolerance(), identity_applies(), axis_reaches_zero() (+64 more)

### Community 6 - "Custom Button Widgets"
Cohesion: 0.03
Nodes (70): IDAAssay, _resolve_bounds(), _draw(), fit_profile(), reported(), result(), rows(), JointRegion (+62 more)

### Community 7 - "Results CSV Export"
Cohesion: 0.03
Nodes (24): Checkbox, diamond(), Field, FileCard, _focus_ring(), LegendRow, _menu_command(), MenuRow (+16 more)

### Community 8 - "Input-Aware Weighted Fitting"
Cohesion: 0.04
Nodes (84): export_results_csv(), ends(), number(), _csv_rows(), _diluted_shared_result(), _input_aware_result(), _law(), _on_bound_result() (+76 more)

### Community 9 - "Fit Result Container"
Cohesion: 0.02
Nodes (40): _cut_interval(), FittedParameters, _follow_curves(), _interval(), edge(), _ka_grid(), _ka_text(), _nearer_bound() (+32 more)

### Community 10 - "Sensitivity Result Display"
Cohesion: 0.03
Nodes (77): fit_measurement_set(), fitted(), _decades_apart(), test_a_coefficient_the_minimum_holds_on_its_bound_is_not_counted_in_either_computation(), test_a_constant_whose_objective_falls_to_its_bound_rests_on_it_in_both_computations(), test_an_input_known_to_a_vanishing_sigma_gives_the_interval_of_exact_inputs(), test_the_reference_edge_is_where_an_exhaustive_computation_puts_it(), _bounded_solve() (+69 more)

### Community 11 - "Fit Diagnostics Tests"
Cohesion: 0.03
Nodes (26): menu_html(), MenuColumns, shortcut_text(), space(), Stat, BarChip, _clear(), _extent() (+18 more)

### Community 12 - "Variable Projection Fitting"
Cohesion: 0.03
Nodes (41): concentration_problem(), _in_file(), MeasurementSet, at(), _molar_text(), _no_measurements(), _whose(), InvalidData (+33 more)

### Community 13 - "Input Uncertainty Specs"
Cohesion: 0.03
Nodes (68): Budget, BudgetRow, what_if(), InputSpec, spec_fraction(), _reported_sources(), SensitivityResult, sobol_jobs() (+60 more)

### Community 14 - "Measurement Set Replicas"
Cohesion: 0.03
Nodes (54): _bootstrap_ratios(), _flatness(), noise_law(), NoiseBasis, NoiseLaw, _read_share(), objective(), replicate_scatter() (+46 more)

### Community 15 - "Assay Types and Residuals"
Cohesion: 0.04
Nodes (71): at_edge(), AwareResult, conflict(), fit_jacobian(), input_aware(), _input_directions(), input_shifts(), misfit_design() (+63 more)

### Community 16 - "Fit Metrics and Fingerprints"
Cohesion: 0.04
Nodes (59): addition_noise_covariance(), AdditionDraws, conflict_added(), conflict_p_value(), conflict_reference(), conflict_test(), _count_runs(), _covariance_root() (+51 more)

### Community 17 - "Plot Theme Styling"
Cohesion: 0.04
Nodes (54): px(), export_results(), _equal(), TitrationData, TitrationPlot, _axes(), _colours(), _drawn_text() (+46 more)

### Community 18 - "Dye-Alone Calibration Assay"
Cohesion: 0.04
Nodes (4): _edit(), edit(), SessionModel, retire()

### Community 19 - "Diagnostics Serialization"
Cohesion: 0.03
Nodes (52): _block_order(), _check_design_size(), sobol_design(), sobol_indices_from_outputs(), sobol_indices_with_ci(), estimate_of(), quantities(), SobolEstimate (+44 more)

### Community 20 - "Input-Aware Verdict Tests"
Cohesion: 0.03
Nodes (46): rejections(), reports_conditional(), _axis(), _count(), curve(), Curve, deviance(), failed_sentence() (+38 more)

### Community 21 - "Menu Rendering"
Cohesion: 0.03
Nodes (58): is_shared(), fmt_param(), superscript(), _assay(), _axis_value(), budget_table(), BudgetTable, Cell (+50 more)

### Community 22 - "Noise Law Model"
Cohesion: 0.02
Nodes (48): WhatIf, AnalysisForm, badge(), config_summary(), figure_caption(), _conflicted(), _heatmap(), _plain() (+40 more)

### Community 23 - "Fit Results Serialization"
Cohesion: 0.03
Nodes (46): PlotAppearance, appearance_mode(), _choice(), concentration_unit(), plot_appearance_default(), reset_plot_appearance_default(), reset_unreadable(), set_plot_appearance_default() (+38 more)

### Community 24 - "Reference Screen Rendering"
Cohesion: 0.04
Nodes (19): MeasurementReader, ResultWriter, _header_comment(), _iter_points(), write_measurements_csv(), write_measurements_txt(), save_results(), get_reader() (+11 more)

### Community 25 - "Binding Condition Entry"
Cohesion: 0.03
Nodes (62): InputShift, ConditionalFit, AwareProfile, ProfileResult, KaInterval, _bump_profile(), _conflicted(), _crossings() (+54 more)

### Community 26 - "Main Window Screenshots"
Cohesion: 0.03
Nodes (19): _and_list(), BaseAssay, _conc(), AssayMetadata, get_metadata(), list_assay_types(), ParamKind, _experiment() (+11 more)

### Community 27 - "Plot Appearance Settings"
Cohesion: 0.03
Nodes (16): Amount, binding_constants(), BindingForm, _bound_text(), BoundEntry, ConditionEntry, dye_alone_keys(), _entry() (+8 more)

### Community 28 - "Uncertainty Input Entry"
Cohesion: 0.04
Nodes (21): _more_sessions(), _open_window(), _overlay_data(), _settings_at_end(), FittingMainWindow, released(), _Sidebar, UpdateCheckWorker (+13 more)

### Community 29 - "Session Model State"
Cohesion: 0.04
Nodes (18): DyeAloneAssay, GDAAssay, bounds_from_dye_alone(), fit_linear_assay(), assert_within_tolerance(), _dye_alone_assay(), TestChainedWorkflow, TestDyeAloneEndToEnd (+10 more)

### Community 30 - "Replicate Metric Formatting"
Cohesion: 0.04
Nodes (43): ParameterSummary, _consistent_text(), fmt_against(), fmt_bound_note(), fmt_concentration(), fmt_interval_html(), fmt_interval_plain(), fmt_log10() (+35 more)

### Community 31 - "Validation Table Tests"
Cohesion: 0.04
Nodes (11): SimulationForm, SimulationProblem, test_a_single_replicate_or_a_lawless_overlay_is_refused_in_plain_words(), test_a_stated_stock_dilutes_the_totals_the_stock_lacks_through_the_fitters_forward_model(), test_choosing_dilution_offers_a_stock_ten_times_the_highest_titrant_concentration_of_the_grid(), test_every_model_opens_on_a_curve_with_every_species_coloured(), test_fit_in_new_session_carries_the_data_as_shown_and_only_the_conditions(), test_reading_the_noise_takes_the_fitters_noise_law_in_the_fields_units() (+3 more)

### Community 32 - "Plot Appearance Preferences"
Cohesion: 0.04
Nodes (50): fake_run(), run(), made_on(), state_dilution(), _deliver_sensitivity(), _load(), _session(), _settle() (+42 more)

### Community 33 - "Sensitivity Analysis Form"
Cohesion: 0.05
Nodes (46): SpecKind, specs_from_dict(), specs_to_dict(), restate(), spread_pct(), test_the_note_names_the_uncertainties_the_hidden_fit_was_made_with(), test_every_field_shows_a_number_one_way_and_reads_back_both_ways_a_number_is_written(), TestStatedUncertainty (+38 more)

### Community 34 - "Simulation View Settings"
Cohesion: 0.04
Nodes (54): ProfileSet, PaintedText, test_choosing_a_model_in_its_menu_reaches_the_session(), assert_card_fits(), move_pointer(), _show(), test_a_fit_with_no_binding_constant_says_there_is_nothing_to_profile(), test_a_fit_with_no_profile_and_no_data_asks_for_the_data_before_the_fit() (+46 more)

### Community 35 - "Heatmap and Chart Views"
Cohesion: 0.04
Nodes (41): test_a_split_interval_draws_its_stretches_under_a_cut_off_that_steps(), test_a_vector_with_a_negative_value_is_refused_whole(), test_an_edit_that_is_not_a_concentration_is_refused_and_changes_nothing(), test_outlier_removal_refuses_with_fewer_replicates_than_it_needs(), test_with_inputs_refuses_what_is_not_an_input_and_what_the_assay_cannot_hold(), test_signal_unit_has_its_own_dimension(), fingerprint(), test_a_diluted_titration_is_measured_on_the_totals_each_point_carries() (+33 more)

### Community 36 - "Session Lifecycle Tests"
Cohesion: 0.04
Nodes (38): test_a_change_in_how_a_row_is_generated_or_scored_retires_the_rows(), test_a_field_named_as_ignored_does_not_decide_the_exit_status(), test_a_field_one_run_writes_and_the_other_does_not_is_a_difference(), test_a_field_that_moved_is_named_with_its_case_and_seed(), test_a_half_written_line_costs_its_own_row_and_no_other(), test_a_key_only_one_run_holds_is_not_compared(), test_a_quantity_neither_run_could_produce_is_not_a_difference(), test_a_resumed_run_computes_only_the_missing_rows() (+30 more)

### Community 37 - "Validation Coverage Checks"
Cohesion: 0.04
Nodes (44): replica_order(), and_join(), fmt_estimate(), fmt_r2(), fmt_rmse(), fmt_value(), own_estimates(), accepted_stretches() (+36 more)

### Community 38 - "Diagnostics Text Formatting"
Cohesion: 0.03
Nodes (8): ConcentrationGrid, NavItem, ProgressLine, ReadoutCard, SectionHeader, Segmented, commit(), Slider

### Community 39 - "Ka Profile Intervals"
Cohesion: 0.04
Nodes (34): shared_key(), SharedSource, SourceEntry, _diluted_data(), test_a_diluted_fit_with_a_shared_source_is_read_back_as_the_fit_it_was(), _wait_until(), _dba(), _log_ka() (+26 more)

### Community 40 - "Interval and Unit Formatting"
Cohesion: 0.05
Nodes (36): aware(), test_every_drawn_point_is_judged_as_the_interval_judges_it(), test_every_shared_source_case_states_the_same_model_the_entries_come_from(), test_the_ignored_dilution_grid_fits_the_titrations_the_declared_grid_measures(), test_the_input_aware_noise_law_grid_states_its_inputs_and_replicates_them(), addition_aware_grid(), addition_grid(), addition_joint_grid() (+28 more)

### Community 41 - "Profile Path Geometry"
Cohesion: 0.05
Nodes (20): density(), _on_one_path(), _one_step_p(), _Point, _Problem, held(), held(), stacked() (+12 more)

### Community 42 - "Fitting Session Exports"
Cohesion: 0.05
Nodes (44): status_messages(), average_fit(), _data(), _deliver(), dialogs(), diluted_fit(), diluted_fitted(), _diluted_session() (+36 more)

### Community 43 - "Hidden Fits Tests"
Cohesion: 0.04
Nodes (45): hg2_species(), ida_species(), _dba(), _diluted(), _dye_alone(), _gda(), _h2g(), _hg2() (+37 more)

### Community 44 - "Addition Error Inflation"
Cohesion: 0.05
Nodes (42): test_a_result_that_records_no_interval_says_so_as_fit_results_does(), test_an_imported_result_with_no_data_says_its_numbers_were_not_checked(), test_without_a_plot_the_readings_and_callouts_keep_their_own_height(), per_replica_result(), _read(), result(), _shown(), test_a_binding_constant_held_fixed_has_no_interval_and_says_why() (+34 more)

### Community 45 - "Fit Results View Tests"
Cohesion: 0.05
Nodes (38): _laid_out_width(), _on_bound(), _over_white(), session(), _show(), _shown_text(), _spread_per_replica(), test_a_hidden_fit_draws_the_data_without_its_curve() (+30 more)

### Community 46 - "Validation Store Tests"
Cohesion: 0.05
Nodes (34): calculate_fit_metrics(), _fitted_offsets(), _record_assay(), verify_imported_result(), test_own_and_shared_sources_are_reported_per_source_and_the_record_verifies(), _absolute_tolerance_host(), _diluted_score(), _gda_assay() (+26 more)

### Community 47 - "Settings Window"
Cohesion: 0.04
Nodes (35): test_the_misfit_rate_is_named_by_the_test_that_ran(), test_a_verdict_that_blames_the_model_the_inputs_or_both_is_a_false_alarm_on_good_data(), test_the_coverage_of_a_weighted_fit_is_split_by_how_far_its_weights_spread(), test_the_reported_coverage_is_read_by_the_largest_entry_error_and_never_judged(), addition_coverage(), addition_misfit(), addition_misstated(), agreement() (+27 more)

### Community 48 - "Measurement File Readers"
Cohesion: 0.04
Nodes (12): FittingSession, side(), _SidePanel, _View, make_session(), build(), qapp(), session() (+4 more)

### Community 49 - "Shared Addition Errors"
Cohesion: 0.05
Nodes (5): _count(), EmptyView, _shortcut(), test_the_help_examples_are_the_numbers_demo_ida_shows(), test_a_concentration_unit_chosen_is_where_a_new_session_starts()

### Community 50 - "Sobol Sensitivity Indices"
Cohesion: 0.05
Nodes (24): format_channel_label(), Dataset, _format_of(), _from_file(), _make_ms(), _slice_channel(), SourceFile, _unit_token() (+16 more)

### Community 51 - "Test Assay Fixtures"
Cohesion: 0.04
Nodes (10): _sample_dataframe(), _sample_measurement_set(), TestConstruction, TestDataAccess, TestFingerprint, TestImmutability, TestReplicaManagement, TestSetConcentrations (+2 more)

### Community 52 - "Dataset Loading"
Cohesion: 0.05
Nodes (38): _dye_alone_help(), help_html(), parse_number(), assay_class(), _concentration_keys(), _form(), test_a_binding_constant_is_entered_in_inverse_molar(), test_a_bound_set_from_code_is_the_very_number_it_was_written_from() (+30 more)

### Community 53 - "Demo IDA Integration Tests"
Cohesion: 0.06
Nodes (26): _addition_loading(), _aware_params(), _diagnose(), _finite_or_none(), _fit_weighted(), _misfit(), _replicate_additions(), _replicate_rows() (+18 more)

### Community 54 - "Budget Validation Tests"
Cohesion: 0.06
Nodes (31): competitive_species_point(), dba_species(), _positive_root(), top(), _assert_close(), _assert_same(), _brackets_root(), _certify_free() (+23 more)

### Community 55 - "Assay Forward Model"
Cohesion: 0.05
Nodes (30): icon(), pixmap(), svg(), stylesheet(), _close(), contrast(), _controls(), delta_e2000() (+22 more)

### Community 56 - "Session Edits and Runs"
Cohesion: 0.05
Nodes (26): rows(), test_a_check_reads_only_the_cases_it_names(), test_a_family_is_pooled_over_the_seeds_every_one_of_its_cases_reached(), test_a_family_one_of_whose_cases_has_no_rows_is_not_published_as_the_family_s_rate(), test_a_filter_prints_the_matching_cases_and_says_that_it_did(), test_a_filter_that_matches_nothing_reads_no_rows_at_all(), test_a_filtered_check_that_reads_its_parent_whole_says_so_rather_than_naming_no_cases(), test_a_gap_in_a_case_s_seeds_ends_the_prefix_the_family_is_pooled_over() (+18 more)

### Community 57 - "Confidence View"
Cohesion: 0.06
Nodes (27): linear_signal(), _as_count(), _build_assay(), build_concentration_vector(), simulate_dataset(), simulate_signal(), simulate_species(), two_part_sd() (+19 more)

### Community 58 - "Binding Model Help"
Cohesion: 0.07
Nodes (16): test_a_run_takes_the_cases_whose_id_one_expression_matches(), test_every_case_of_a_check_has_its_own_id(), case_by_id(), Check, conditional_coverage(), matches(), matching_cases(), pooling() (+8 more)

### Community 59 - "GUI Layout Tests"
Cohesion: 0.06
Nodes (9): Appearance, sub(), _diamond_symbol(), _dotted(), ProfileFigure, clear_names(), RegionFigure, species_pen() (+1 more)

### Community 60 - "Data Preprocessing Pipeline"
Cohesion: 0.07
Nodes (31): _assert_back(), _assert_hidden(), _curves(), _deliver_sensitivity(), _numbers(), _shown_session(), test_a_bound_that_cannot_be_read_hides_the_fit(), test_a_concentration_edited_and_typed_back_restores_the_fit() (+23 more)

### Community 61 - "Validation Run Jobs"
Cohesion: 0.07
Nodes (9): apply_preprocessing(), get_step(), PreprocessingStep, register_step(), ZScoreReplicaFilter, _ms_few_replicas(), _ms_with_outlier(), TestRegistry (+1 more)

### Community 62 - "Binding Form"
Cohesion: 0.05
Nodes (24): _magnitude(), state_binding(), session(), _tab_order(), test_a_condition_that_cannot_be_read_shows_no_number_under_input_uncertainty(), test_a_dye_alone_file_sets_the_signal_bounds_to_what_it_measured(), test_a_dye_alone_file_the_data_checks_refuse_is_named_with_the_refusal_itself(), test_a_stock_typed_in_its_field_reaches_the_fit_in_the_unit_shown() (+16 more)

### Community 63 - "Equilibrium Forward Models"
Cohesion: 0.04
Nodes (6): test_an_imported_fit_names_its_replicates_by_their_letters_without_the_data(), test_a_signal_parameter_the_fit_ended_on_an_entered_bound_is_named_with_that_bound(), TestTheSecondStepAndTheMisfitReference, test_a_condition_with_no_known_unit_is_refused(), test_a_diluted_file_read_and_written_again_is_the_same_record(), test_the_file_survives_being_read_and_written_again()

### Community 64 - "Conflict Verdict Tests"
Cohesion: 0.07
Nodes (6): summarize_parameters(), TestReplicateColumns, _interval(), _replica(), _sample_fit_result(), TestSummarizeParameters

### Community 65 - "Dilution Speciation Tests"
Cohesion: 0.06
Nodes (15): _canonical_unit(), fmt_bound_estimate(), fmt_unit_html(), fmt_unit_pretty(), replicate_summary(), test_a_log10_reading_is_never_written_coarser_than_the_spread_beside_it(), test_every_fitted_value_reads_to_three_significant_figures_with_its_zeros(), test_every_number_shown_is_written_in_the_notation_of_the_design() (+7 more)

### Community 66 - "Results Import Checks"
Cohesion: 0.07
Nodes (18): create_dba_dye_to_host(), create_dba_host_to_dye(), DBAAssay, X(), TestDBAQuantityConditions, test_dba_projection_residual_is_the_model_residual_with_dilution(), TestDBAFailFast, _free_fixed_exactly() (+10 more)

### Community 67 - "Example Data and Design Docs"
Cohesion: 0.04
Nodes (49): DBA host-to-dye titration data (8 replicates), Dye-alone calibration data (4 replicates), GDA titration data (3 replicates), IDA titration data (8 replicates), Example data metadata, DBA host-to-dye reference parameters, GDA reference parameters (CB7, nButanol, TNS dye), IDA reference parameters (+41 more)

### Community 68 - "GDA Assay Tests"
Cohesion: 0.09
Nodes (13): _excluded_reason(), fit_measurement_set_per_replica(), ReplicateTest, clean_pr_result(), _config(), _ida_conditions(), _ida_ms(), noisy_pr_result() (+5 more)

### Community 69 - "Session Copy and Cancellation"
Cohesion: 0.06
Nodes (19): _note(), plot_appearance_note(), _row(), SettingsWindow, worker_label(), check_for_updates(), get_bool(), get_int() (+11 more)

### Community 70 - "Design System Contrast Tests"
Cohesion: 0.07
Nodes (24): fit_replica_ids(), input_replica_ids(), _replicate_names(), _replicate_record(), fitted(), _legacy(), _measurement_set(), _round_trip() (+16 more)

### Community 71 - "Ensight Reader"
Cohesion: 0.06
Nodes (27): inflation(), addition_loading(), perturb_titrant(), _require_rising(), _in_cuvette(), test_additions_without_error_leave_the_series_bit_for_bit(), test_equal_sequential_aliquots_accumulate_as_a_random_walk(), test_separate_samples_with_a_stock_are_each_their_own_volume() (+19 more)

### Community 72 - "Binding View Tests"
Cohesion: 0.06
Nodes (22): fmt_param_plain(), plain_label(), _subscript(), budget_csv_rows(), row(), budget_refusal(), _csv_interval(), _csv_number() (+14 more)

### Community 73 - "Equilibrium Precision Tests"
Cohesion: 0.05
Nodes (21): id_digest(), test_a_field_that_changes_the_data_changes_the_id(), test_a_noise_floor_says_nothing_without_noise_that_grows_with_the_signal(), test_a_scenario_refuses_a_stock_that_says_nothing(), test_a_scenario_refuses_an_input_its_assay_does_not_have(), test_a_scenario_refuses_departing_replicates_that_are_not_a_minority(), test_an_id_names_exactly_one_scenario(), test_every_check_either_runs_cases_or_reads_another_checks_rows() (+13 more)

### Community 74 - "Dilution Recovery Tests"
Cohesion: 0.13
Nodes (7): Conflict, verdict_sentence(), _diagnostics(), _f_test(), _shift(), TestVerdictHeadline, TestVerdictSentence

### Community 75 - "Titration Simulation"
Cohesion: 0.10
Nodes (4): _caption(), _column(), SimulationView, _widget()

### Community 76 - "Validation Statistics Tests"
Cohesion: 0.07
Nodes (5): EnsightReader, _minimal_ensight(), _read_legacy_var_signal(), TestParsing, TestSniffing

### Community 77 - "Jasco Reader"
Cohesion: 0.08
Nodes (21): qapp(), test_every_menu_of_the_fitted_demo_fits_its_rows_and_its_window_and_marks_its_choice(), _wait(), _accent_pixels(), check_window(), _name(), open_menu(), open_sections() (+13 more)

### Community 78 - "Per-Replicate Fitting"
Cohesion: 0.07
Nodes (13): _common_fields(), _config_to_dict(), FitResult, _record_data(), _replica_fit(), offsets_held_at_zero(), badge(), _ka_keys() (+5 more)

### Community 79 - "Dilution Conditions"
Cohesion: 0.06
Nodes (16): test_the_command_renders_every_reference_screen_in_both_themes(), replace_replicates(), test_a_row_of_each_new_scenario_carries_what_its_check_reads(), test_a_row_of_stated_inputs_carries_the_standard_score_each_entry_was_drawn_at(), test_a_row_says_what_the_replicates_showed_about_the_noise(), test_a_scenario_of_an_older_grid_stores_the_fields_its_rows_already_hold(), test_a_single_titration_reports_that_its_noise_was_taken_as_constant(), test_a_two_step_row_carries_the_one_step_p_value_of_the_second_constant_alone() (+8 more)

### Community 80 - "BMG Workbook Parser"
Cohesion: 0.10
Nodes (8): prepare_plot_data(), _noisy_ms(), _per_replicate_record(), _simple_fit_result(), _simple_ms(), TestMeanFollowsTheFittedReplicates, TestPrepPlotDataFits, TestPrepPlotDataReplicas

### Community 81 - "Simulation View"
Cohesion: 0.09
Nodes (19): FitDiagnostics, MisfitTest, Verdict, verdict(), test_the_status_bar_names_the_test_a_rejected_model_failed_and_not_the_verdict(), test_a_conflict_is_called_out_about_the_inputs_together_with_the_way_to_review_it(), test_a_hidden_fit_shows_its_note_and_nothing_else(), test_a_misfit_the_moved_inputs_explain_is_called_out_at_the_inputs_as_entered() (+11 more)

### Community 82 - "Export Multiple Dialog"
Cohesion: 0.08
Nodes (11): ExportMultipleDialog, _row(), ExportableArtefact, test_export_prefix_is_reused_only_for_the_same_dataset(), dialog(), _raise(), test_a_folder_that_cannot_be_made_is_said_in_plain_words(), test_export_batch_collects_exceptions_and_continues() (+3 more)

### Community 83 - "Status Message Tests"
Cohesion: 0.07
Nodes (21): _button(), _offered_folders(), _on_screen(), test_a_save_offers_the_folder_of_the_data_it_was_made_from(), test_every_empty_view_offers_load_data_and_the_demo_and_draws_no_bare_axes(), test_export_several_offers_no_folder_of_the_bundled_examples(), test_no_save_after_the_demo_offers_a_folder_inside_the_app(), test_no_view_says_there_is_no_fit_while_the_fit_runs() (+13 more)

### Community 84 - "Ka Display Helpers"
Cohesion: 0.07
Nodes (18): _count_thresholds(), _ladder_by_paths(), test_a_case_that_is_exactly_nominal_is_failed_about_one_time_in_fifty(), test_a_coverage_rate_fails_only_when_the_draws_put_it_below_the_level(), test_a_coverage_rate_the_data_put_above_bradley_s_far_end_is_a_pass_called_conservative(), test_a_ladder_of_one_stage_is_one_look(), test_a_lower_limit_claim_is_the_same_rule_the_other_way_round(), test_a_test_at_the_5_per_cent_level_fails_only_when_it_rejects_too_often() (+10 more)

### Community 85 - "Measurements View"
Cohesion: 0.09
Nodes (4): JascoReader, _minimal_jasco(), TestParsing, TestSniffing

### Community 86 - "Input Uncertainty View"
Cohesion: 0.05
Nodes (36): concurrency, group, env, ANTHROPIC_API_KEY, ANTHROPIC_MODEL, GRAPHIFY_NO_BACKUP, PYTHONHASHSEED, default (+28 more)

### Community 88 - "Build and Release Workflow"
Cohesion: 0.09
Nodes (3): _InputRow, _SourceRow, UncertaintyView

### Community 89 - "Plot Navigation"
Cohesion: 0.06
Nodes (35): runs-on, steps, strategy, jobs, build, publish_release, os, name (+27 more)

### Community 90 - "Fit Cancellation Tests"
Cohesion: 0.17
Nodes (23): test_add_files_adds_replicates_to_the_session_on_screen(), _ancestors(), _assert_revealed(), _callout_action(), _disturb(), _link(), _placeholder_concentrations(), _scroll_area() (+15 more)

### Community 91 - "Binding View"
Cohesion: 0.10
Nodes (7): BindingView, _BoundRow, _caption(), _clear(), _ConditionRow, _grid(), _name()

### Community 92 - "Plot Design Docs"
Cohesion: 0.07
Nodes (12): test_what_is_drawn_keys_the_measurement_and_what_is_stated_keys_the_case(), test_what_the_fit_is_told_leaves_the_measurement_alone(), test_a_replicate_that_departs_from_the_rest_reaches_the_key_its_measurements_hang_on(), test_a_scenario_refuses_a_shared_source_it_cannot_carry(), test_a_shared_source_reaches_the_entry_stream_and_the_row_key(), test_leaving_the_stock_undeclared_keeps_the_titration_and_changes_the_fit(), test_the_dilution_of_a_titration_reaches_the_key_its_measurements_hang_on(), test_the_error_model_carries_the_specs_and_the_shared_sources_the_scenario_states() (+4 more)

### Community 93 - "Graph CI Workflow"
Cohesion: 0.07
Nodes (15): dba_signal(), facts(), moved_series(), test_a_diluting_titrant_moves_the_series_and_dilutes_the_sample_by_the_volume_added(), test_a_row_of_stated_additions_carries_the_factor_each_interval_was_widened_by(), test_a_titration_without_addition_error_is_drawn_from_its_noise_stream_alone(), test_a_weighted_fit_reports_the_law_it_was_weighted_by(), test_an_addition_error_a_scenario_cannot_carry_is_refused() (+7 more)

### Community 94 - "Confidence View Tests"
Cohesion: 0.10
Nodes (14): axis_text_problems(), check(), clashing_names(), cut_axis_text(), cut_headers(), cut_labels(), cut_sideways(), interactive() (+6 more)

### Community 95 - "CSV Reader"
Cohesion: 0.06
Nodes (30): figure_head(), Input-aware interval, Inputs as entered interval, Two-part noise law var(y)=floor²+(proportional·y)², PlotHeader, PlotNavigation, Plots design (§7), Saved figure (+22 more)

### Community 96 - "Design Style Icons"
Cohesion: 0.10
Nodes (20): _aware_fit(), _profile(), _show(), _shown(), _split_fit(), test_a_closed_end_far_below_the_others_never_reads_zero(), test_a_constant_with_no_interval_is_named_beside_the_one_drawn(), test_a_fit_whose_association_constant_records_no_interval_says_so() (+12 more)

### Community 98 - "Layout Rules Checks"
Cohesion: 0.10
Nodes (8): describe(), describe_log10(), _at_bound(), _binding_constant_keys(), _ka_boxes(), parameters_on_bound(), _replicate_values(), TestDescribe

### Community 99 - "Fit Results View"
Cohesion: 0.09
Nodes (9): AdditionError, _additions_only_fit(), test_replicates_read_from_one_titration_survive_a_round_trip_and_a_file_without_them_means_separate(), test_the_whole_model_survives_a_json_round_trip(), TestSerialization, TestWhatWidenedTheInterval, _widened(), kappa() (+1 more)

### Community 100 - "Plot Data Preparation Tests"
Cohesion: 0.08
Nodes (9): SensitivityRunError, ProfileWorker, _release(), SensitivityWorker, test_worker_delivers_a_held_back_count_as_soon_as_a_cancel_is_seen(), run(), test_worker_reports_an_unexpected_failure_in_plain_words(), written() (+1 more)

### Community 102 - "Summary Statistics Helpers"
Cohesion: 0.08
Nodes (6): projectable(), ImportCheck, _problem_list(), Refusal, test_before_an_analysis_sensitivity_names_only_the_steps_still_to_take(), view()

### Community 103 - "Checkbox and Dropdown Widgets"
Cohesion: 0.10
Nodes (4): _as_float(), TxtReader, TxtWriter, TestTxtReader

### Community 104 - "Render Harness Tests"
Cohesion: 0.11
Nodes (3): AdditionsEntry, UncertaintyForm, test_the_inputs_are_the_assays_perturbable_inputs_named_as_every_report_names_them()

### Community 105 - "Empty State Views Tests"
Cohesion: 0.08
Nodes (14): help_off_screen(), _plain(), test_each_settings_side_panel_is_explained_in_its_section(), test_every_link_to_the_help_raises_the_one_window_at_its_section(), test_every_section_uses_one_heading_convention(), test_every_section_with_a_demo_plot_ends_on_its_demo_ida_example(), test_no_help_opens_as_a_modal_dialog_with_its_own_buttons(), test_the_binding_model_section_follows_the_model_chosen() (+6 more)

### Community 106 - "GUI Test Helpers"
Cohesion: 0.11
Nodes (19): _data(), _holding(), make_model(), build(), _state(), test_a_cancelled_fit_leaves_the_previous_result_as_it_was(), test_a_condition_hides_the_fit_once_its_edit_is_finished_and_setting_it_back_shows_it_again(), test_a_fit_that_cannot_start_says_why() (+11 more)

### Community 107 - "Concentration Vector IO"
Cohesion: 0.09
Nodes (11): _extract_metadata(), _find_bmg_sheet(), _find_header_row(), is_bmg_workbook(), parse_bmg_workbook(), TestBMGDetection, TestBMGParse, TestBMGParseSynthetic (+3 more)

### Community 108 - "Multi-File Replica Loading"
Cohesion: 0.10
Nodes (7): Overlay, Simulation, species_groups(), tag_text(), _legend_items(), SimulationPlots, power_of_ten()

### Community 109 - "Help Window Tests"
Cohesion: 0.10
Nodes (12): _demo(), _fit(), fits(), _holding(), _inconsistencies(), second(), _signals(), test_an_edit_is_said_once() (+4 more)

### Community 110 - "1:2 Host-Guest Speciation"
Cohesion: 0.11
Nodes (5): extract_concentrations_from_file(), read_raw_concentrations(), save_concentration_vector(), TestConcentrationRoundTrip, TestExtractConcentrations

### Community 111 - "Plot Appearance View"
Cohesion: 0.10
Nodes (17): FitCancelled, watchful_fit(), run(), watchful_sensitivity(), run(), window(), slow_fit(), fake() (+9 more)

### Community 112 - "Slider Knob Values"
Cohesion: 0.11
Nodes (4): menu(), PlotAppearanceView, body(), _widget()

### Community 113 - "Sensitivity Background Worker"
Cohesion: 0.12
Nodes (13): _open_menu(), _point_at(), render(), _settle(), _snapshot(), _wait(), test_a_pointer_with_no_plot_on_screen_is_refused(), test_a_render_at_a_scale_has_that_many_device_pixels_per_logical_pixel() (+5 more)

### Community 114 - "Profile Plot Readout"
Cohesion: 0.11
Nodes (12): Place, _cue(), _fitted(), _same(), session(), test_fit_results_and_plot_appearance_draw_one_plot_whatever_the_replicate_display(), test_measurements_draws_the_same_points_raw_with_no_curve(), test_measurements_names_the_fitted_value_and_opens_fit_results() (+4 more)

### Community 115 - "Elided Labels and Plot Header"
Cohesion: 0.09
Nodes (13): export_batch(), _replicates_on_bound(), _shown_fits(), test_a_saved_figure_keeps_its_width_whatever_its_summary_says(), _two_ka_per_replica(), _fitted(), saved(), session() (+5 more)

### Community 117 - "Profile Interval Cutting"
Cohesion: 0.14
Nodes (4): Knob, _three_figures(), unit_text(), _KnobRow

### Community 118 - "Update Check Lifecycle Tests"
Cohesion: 0.09
Nodes (11): jobs(), test_a_job_that_dies_is_stored_as_an_error_under_its_own_key(), test_a_pool_that_never_finishes_a_row_ends_the_run_rather_than_looping(), test_the_jobs_a_dead_pool_left_unanswered_go_on_a_new_one(), one_pool(), _case(), compute(), _error_row() (+3 more)

### Community 119 - "Batch Export and Titration Figure"
Cohesion: 0.11
Nodes (11): qapp(), test_every_painted_component_of_the_fitted_demo_gets_its_room_and_no_plot_header_is_cut(), _wait(), test_a_failed_run_says_why_and_keeps_the_last_result_shown(), test_a_run_counts_its_fits_on_the_status_bar_and_estimates_the_time_left(), test_a_run_uses_the_bounds_and_the_settings_stated(), capture(), test_a_seed_typed_and_run_at_once_is_the_seed_the_run_uses() (+3 more)

### Community 121 - "Reference Grid Interval Tests"
Cohesion: 0.12
Nodes (10): checks(), dialogs(), _ScriptedCheck, _settle(), _SlowToEnd, test_a_check_that_reported_is_deleted_only_once_its_thread_has_ended(), test_a_finished_check_lets_go_of_itself_and_not_of_the_check_that_replaced_it(), test_asking_for_a_check_while_one_is_running_says_so() (+2 more)

### Community 123 - "Update Download Worker"
Cohesion: 0.09
Nodes (7): decimal_text(), times_ten(), interval_caption(), KaBlock, tick_label(), _pct(), span_text()

### Community 124 - "Concentration Validation"
Cohesion: 0.10
Nodes (4): DownloadWorker, _os_label(), _pick_asset(), UpdateAvailableDialog

### Community 126 - "Competitive GDA Speciation"
Cohesion: 0.11
Nodes (4): condition_fields(), same_inputs(), TestLabelsAndHelp, TestRegistration

### Community 128 - "Editable Slider Ends"
Cohesion: 0.12
Nodes (7): fmt_misfit(), fmt_test_p(), _inputs_line(), test_rows(), TestRow, _runs(), TestFmtMisfit

### Community 129 - "Run Actions and Failures"
Cohesion: 0.14
Nodes (12): _broken(), _Emitter, _export_batch(), _export_plot(), _export_raw_data(), _import_results(), _load_vector(), _measured() (+4 more)

### Community 131 - "Species Readout Legend"
Cohesion: 0.12
Nodes (3): linear_regression(), TestCalculateFitMetrics, TestLinearRegression

### Community 134 - "Segmented Control Widget"
Cohesion: 0.14
Nodes (8): _binary_free_host(), _competitive_free_host(), balance(), _dye_signal(), _generate(), _stepwise_free_ligand(), _stepwise_signal(), _titration()

### Community 138 - "Files Table Widget"
Cohesion: 0.15
Nodes (7): test_a_budget_case_is_addressed_by_what_it_runs(), test_every_exact_case_carries_the_source_its_claim_is_about(), test_every_what_if_case_asks_for_an_improvement_of_a_source_it_states(), test_reducing_a_shared_source_leaves_the_inputs_it_loads_alone(), BudgetCase, exact_cases(), whatif_cases()

### Community 139 - "Documentation Currency Tests"
Cohesion: 0.16
Nodes (3): HelpWindow, _topic_style(), section_html()

### Community 141 - "Second Step Sentence Formatting"
Cohesion: 0.23
Nodes (5): fit_view(), TestFitViewAtMovedInputs, signal(), result_off_by(), solve()

### Community 142 - "Session Settings"
Cohesion: 0.20
Nodes (4): is_newer(), newest_release(), test_a_beta_build_is_offered_the_newest_published_release_beta_or_stable(), TestIsNewer

### Community 144 - "Model Notification Consistency"
Cohesion: 0.14
Nodes (6): _live_texts(), test_no_live_text_names_machinery_the_app_does_not_have(), test_the_architecture_table_names_every_pipeline_module(), test_the_documents_name_the_fit_the_app_performs(), test_the_scan_reaches_the_texts_a_reader_and_the_program_depend_on(), test_the_validation_readme_lists_every_check_with_its_claim_and_criterion()

### Community 145 - "Set Concentrations Tests"
Cohesion: 0.18
Nodes (7): coverage_rows(), test_a_case_stops_only_once_every_check_reading_it_has_passed_as_well(), test_a_case_that_fails_at_the_first_stage_goes_on_to_the_next(), test_a_case_whose_rate_has_passed_stops_where_it_is(), test_a_one_step_null_case_can_fail_alone_and_pass_only_in_its_pooled_row(), test_an_undecided_case_goes_on_and_a_case_with_nothing_judged_yet_goes_on_too(), _case_passed()

### Community 146 - "Profile Curve Deviance"
Cohesion: 0.15
Nodes (7): facts(), test_a_closed_interval_that_misses_the_truth_is_counted_over_every_fit(), test_a_closed_lower_edge_of_the_second_constant_above_the_truth_is_counted_whatever_the_upper_side_does(), test_the_one_step_null_judges_a_second_constant_closed_below(), closed_coverage(), _false_closures(), _interval_metrics()

### Community 148 - "Binding Model Form"
Cohesion: 0.19
Nodes (4): _legacy_input_ids(), _parameter_vector(), _reproduces(), _unmarked_slack()

### Community 150 - "Slider Widget"
Cohesion: 0.20
Nodes (4): FitWorker, test_a_worker_failure_names_the_step_and_the_log(), test_a_fit_the_pipeline_refuses_is_reported_in_its_own_words(), raising()

### Community 151 - "Input Shift Formatting"
Cohesion: 0.24
Nodes (3): _escape(), fmt_shift(), TestFmtShift

### Community 153 - "Reader Registry Test Stubs"
Cohesion: 0.25
Nodes (3): _Accepter, _Fallback, _Rejecter

### Community 154 - "Plot Zoom and Pan"
Cohesion: 0.20
Nodes (3): callouts(), CalloutSpec, _clear()

### Community 157 - "Interval Coverage Metrics"
Cohesion: 0.31
Nodes (3): demo(), _free_dropped_widgets(), qapp()

### Community 159 - "Progress Line Indicator"
Cohesion: 0.22
Nodes (4): Grid, _knobs(), Noise, _ParamDefault

### Community 160 - "View Side Panels"
Cohesion: 0.25
Nodes (3): _render_csv(), _size(), Summary

### Community 161 - "Plot Axis Text Sizes"
Cohesion: 0.33
Nodes (4): _heatmap(), _ida_ms(), test_a_run_is_not_refused_because_the_interval_of_a_fit_would_be(), test_the_run_starts_from_the_fit_at_the_inputs_as_entered()

### Community 162 - "Replica Data Access Tests"
Cohesion: 0.22
Nodes (9): addition-* checks, before-after check, validation.criteria (operating_characteristic, ladder_operating_characteristic), fit_measurement_set, Seed ladder 100→200→400, MeasurementSet, core.pipeline.inputs.perturb_titrant, Result store (validation/results/<check>.jsonl) (+1 more)

### Community 163 - "Validation Package"
Cohesion: 0.25
Nodes (6): _excess(), cut(), _allowed_rise(), at(), judge(), at()

### Community 165 - "MeasurementSet Immutability Tests"
Cohesion: 0.29
Nodes (7): Bates & Watts 1988 Nonlinear Regression, F-test profile likelihood interval, Hodges & Sargent 2001 effective degrees of freedom, Input-aware penalised profile interval, Raue et al. 2009 profile-likelihood identifiability, Replicates averaged, not pooled, Signal coefficient degeneracy

### Community 172 - "Reader Writer Interfaces"
Cohesion: 0.38
Nodes (3): dba_complex(), dba_signal_at(), test_a_shifted_replicate_is_the_model_at_its_own_binding_constant()

### Community 181 - "Bound Resting Tests"
Cohesion: 0.50
Nodes (4): Dilution of fixed totals, Scaling identity of binding models, Sobol' 2001 global sensitivity indices, Sobol' variance decomposition

### Community 188 - "Window Flash Prevention"
Cohesion: 0.50
Nodes (4): Bradley 1978, Robustness?, Bradley's liberal criterion of robustness, one-step-null check, Clopper-Pearson exact limits

### Community 190 - "Data Fingerprint Tests"
Cohesion: 0.67
Nodes (3): Cochran 1941 largest variance test, Hadi & Simonoff 1993 multiple outliers, Replicate test (forward search + Cochran)

### Community 191 - "Extreme Input Tests"
Cohesion: 0.67
Nodes (3): Input conflict statistic, Lack-of-fit F test and runs test, Fit verdict (Holm procedure)

## Ambiguous Edges - Review These
- `GDA reference parameters (CB7, nButanol, TNS dye)` → `Dye-alone calibration data (4 replicates)`  [AMBIGUOUS]
  data/Readme.md · relation: conceptually_related_to
- `Variable projection fit` → `Fitting workflow flowchart: load data, initial guess, multi-start optimization, RMSE/R² filtering, aggregate good fits, replicas loop, save results`  [AMBIGUOUS]
  docs/fitting_workflow.jpg · relation: conceptually_related_to

## Knowledge Gaps
- **59 isolated node(s):** `uv`, `fitting-app`, `Andrews & Cheng 2012 weak identification`, `Bates & Watts 1988 Nonlinear Regression`, `Cochran 1941 largest variance test` (+54 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 3934 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **94 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `SessionModel` connect `Dye-Alone Calibration Assay` to `Sensitivity Run Configuration`, `Fit Configuration and Bounds`, `Titration Plot Rendering`, `Addition Error Validation Tests`, `Fit Diagnostics Tests`, `Variable Projection Fitting`, `Input Uncertainty Specs`, `Noise Law Model`, `Fit Results Serialization`, `Reference Screen Rendering`, `Slider Widget`, `Plot Zoom and Pan`, `Plot Appearance Settings`, `Parameter Bound Entries`, `Validation Table Tests`, `Simulation View Settings`, `Profile Likelihood References`, `Simulation Grid and Noise`, `Measurement File Readers`, `Shared Addition Errors`, `Sobol Sensitivity Indices`, `Confidence View`, `Replicate Outlier References`, `Plot Labels and Export`, `Diagnostic P-Values`, `Session Views Package`, `Per-Replicate Fitting`, `Diluted Fit Fixture`, `Non-Blocking Dialog Recording`, `Titration Simulation`, `Status Message Tests`, `Legacy Results Loading`, `Build and Release Workflow`, `Binding View`, `Design Style Icons`, `Plot Data Preparation Tests`, `Summary Statistics Helpers`, `Render Harness Tests`, `GUI Test Helpers`, `Multi-File Replica Loading`, `Help Window Tests`, `Slider Knob Values`, `Profile Plot Readout`, `Replicate Outlier Detection`, `MeasurementSet Writers`, `Sobol Sampling Design Tests`?**
  _High betweenness centrality (0.075) - this node is a cross-community bridge._
- **Are the 200 inferred relationships involving `AssayType` (e.g. with `BaseAssay` and `DBAAssay`) actually correct?**
  _`AssayType` has 200 INFERRED edges - model-reasoned connections that need verification._
- **What connects `uv`, `fitting-app`, `Andrews & Cheng 2012 weak identification` to the rest of the system?**
  _59 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Assay Base Classes` be split into smaller, more focused modules?**
  _Cohesion score 0.016641806323301454 - nodes in this community are weakly interconnected._
- **Why does `AssayType` connect `Fit Configuration and Bounds` to `Assay Base Classes`, `Sensitivity Run Configuration`, `Addition Error Validation Tests`, `Uncertainty Budget Elasticities`, `Custom Button Widgets`, `Fit Result Container`, `Reference Screens and Legacy`, `Documentation Currency Tests`, `Variable Projection Fitting`, `Input Uncertainty Specs`, `Measurement Set Replicas`, `Assay Types and Residuals`, `Sensitivity Result Display`, `Plot Theme Styling`, `Dye-Alone Calibration Assay`, `Binding Model Form`, `Input-Aware Verdict Tests`, `Menu Rendering`, `Reference Screen Rendering`, `Binding Condition Entry`, `Main Window Screenshots`, `Plot Appearance Settings`, `Session Model State`, `Replicate Metric Formatting`, `Parameter Bound Entries`, `Progress Line Indicator`, `Validation Table Tests`, `Sensitivity Analysis Form`, `Simulation View Settings`, `Plot Appearance Preferences`, `Validation Coverage Checks`, `Heatmap and Chart Views`, `Ka Profile Intervals`, `Interval and Unit Formatting`, `Fitting Session Exports`, `Addition Error Inflation`, `Fit Results View Tests`, `Validation Store Tests`, `Measurement File Readers`, `Dataset Loading`, `Demo IDA Integration Tests`, `Confidence View`, `Data Preprocessing Pipeline`, `Binding Form`, `Conflict Verdict Tests`, `Dilution Speciation Tests`, `Results Import Checks`, `Ensight Reader`, `Binding View Tests`, `Per-Replicate Fitting`, `Dilution Conditions`, `Status Message Tests`, `Fit Cancellation Tests`, `Design Style Icons`, `Layout Rules Checks`, `Summary Statistics Helpers`, `Render Harness Tests`, `Empty State Views Tests`, `GUI Test Helpers`, `Help Window Tests`, `Slider Knob Values`, `Profile Plot Readout`, `Elided Labels and Plot Header`, `MeasurementSet Writers`, `Competitive GDA Speciation`?**
  _High betweenness centrality (0.071) - this node is a cross-community bridge._

### Low-confidence Hints
_AMBIGUOUS edges — the extractor was unsure. Verify before acting on these._

- **What is the exact relationship between `GDA reference parameters (CB7, nButanol, TNS dye)` and `Dye-alone calibration data (4 replicates)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Variable projection fit` and `Fitting workflow flowchart: load data, initial guess, multi-start optimization, RMSE/R² filtering, aggregate good fits, replicas loop, save results`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._