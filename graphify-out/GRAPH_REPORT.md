# Graph Report - SupraSimFit  (2026-11-26)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 9483 nodes · 26148 edges · 252 communities (166 shown, 86 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 2520 edges (avg confidence: 0.91)
- Token cost: 29,568 input · 3,448 output

## Graph Freshness
- Built from commit: `b274e300`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Error Model Sources
- Assay Module Definitions
- Reference Screen Rendering
- Fit Diagnostics Statistics
- Theme and Figure Painting
- Linearised Projected Fits
- Input-Aware Fitting
- IDA Assay Fitting Pipeline
- Export Multiple Dialog
- Input Uncertainty Specs
- Results CSV Export
- Sensitivity Result Formatting
- Button and Checkbox Widgets
- Hidden Fits Tests
- Menu and Popover Painting
- Variance Budget Computation
- Fit Result Container
- Joint Confidence Region
- Ka Profile Intervals
- Painted Text and Axes
- Noise Law Model
- Simulation Settings
- Profile Likelihood Fitting
- Measurement Set Container
- Card and Label Widgets
- Budget and Analysis Form
- Validation Table Tests
- Data Preprocessing Pipeline
- Plot Appearance Settings
- Parameter Summary Formatting
- DBA Assay Model
- Dye-Alone Calibration Assay
- Error Model Entry Form
- Base Assay Class
- User-Facing Labels
- Validation Coverage Checks
- Fit Diagnostics Serialization
- Ensemble Statistics and Metrics
- Validation Store Tests
- Path Problem Geometry
- Confidence Verdict Rejections
- Dark Mode Appearance
- Dataset Loading
- Shared and Addition Errors
- 1:2 Host-Guest Assay
- Validation Data Generation
- Main Window Sessions
- Ka Grid Intervals
- Measurement Set Tests
- Session Fit and Export Actions
- Session Editing and Status
- Confidence View
- GUI Layout Tests
- Binding Conditions Entry
- Binding Help and Tests
- Validation Scenario Grids
- Session Display State
- Reference Interval Validation
- Validation Run Jobs
- Conflict Verdict Sentences
- Sobol Sensitivity Indices
- Interval Inflation Factor
- Binding Form Model
- Session Model State
- Interval Chart Widget
- Binding View
- Sensitivity View Blocks
- Validation Scenario IDs
- Validation Statistics Ladder
- EnSight File Reader
- Binding View Tests
- BMG Workbook Parser
- Fit and Import Actions
- Jasco File Reader
- Titration Simulation
- Input Uncertainty Controls
- Saved Figure Tests
- Reader Registry Protocol
- Measurements View
- Plot Appearance Tests
- Dilution Recovery Fitting
- Variable Projection Profiles
- Graph CI Workflow
- Session Lifecycle Tests
- Results Serialization Tests
- Build and Release Workflow
- Confidence View Tests
- Uncertainty View Tests
- Session Export Actions
- Addition Error Validation
- Replica Signal Access
- Z-Score Replica Filter
- Fit View Reproduction
- CSV File Reader
- Plot Zoom Navigation
- Per-Replicate Fit Tests
- Imported Result Verification
- Concentration Vector IO
- Tab-Separated Reader Writer
- Fit Results View
- Main Window Views
- Results File Provenance Checks
- Session Model Consistency Tests
- Parameter Summary Reporting
- Background Sensitivity Runner
- Help Window Text
- Measurement Identity Keys
- Concentration Data Validation
- Multi-File Replicate Loading
- Fit Result Serialization
- Empty States and Demo
- Concentration Grid Editing
- Slider Knob Scaling
- GUI Layout Rule Checks
- GUI Render Test Helpers
- Value and Interval Formatting
- Simulation View
- Simulation Plots and Overlay
- Sensitivity Worker Processes
- Update Check Lifecycle Tests
- Fit Cancellation Test Stubs
- Sensitivity Export Fixtures
- Session Model Rule Tests
- Uncertainty Budget Validation
- Replicate Outlier Detection
- Update Check and Download
- Download Worker Dialog
- Session Copy and Cancellation
- Unit Display Formatting
- Analysis Configuration and Simulation
- Validation Check Rows
- Reference F-Test Profiles
- Dropdown Widget
- Session Data and Replicates
- Titration Data and Plot Axes
- Session Closing Tests
- Main Window Tests
- Units and Fit Pipeline Design
- Fit Worker Cleanup Tests
- Plain Text Labels
- Shared Error Sources
- Budget Validation Cases
- Conditional Fit Results Tests
- Datasets and Design System
- Parameter Kinds and Binding Constants
- Results Export and Import
- Files Table Widget
- Species Readout Widget
- Documentation Currency Tests
- Input-Aware Documentation Tests
- Input-Aware Validation Grid
- Slider Widget
- Titration Plot Widget
- Lack-of-Fit Parameter Tests
- Per-Replicate Fit Recovery
- Uncertainty Spread Bars
- Word-Breaking Label
- Fit Config Serialization
- Conditions Form Layout
- Render Harness Tests
- Fit Refusal Messages
- Stepwise Mass Balance Tests
- Simulated Truth Conditions
- Plot Zoom and Pan
- Sensitivity Panel Tests
- Test Store Fixtures
- Replicate Statistics Round Trip
- Interval Widening Reasons
- Parameter Bound Entry
- Sidebar and Status Bar
- Bound Estimate Formatting
- Error Warning Handling
- Side Panel Label Width
- Session Settings
- Plot Export Components
- Stepwise Assay Registration
- DBA Forward Model Tests
- Replica Display Labels
- Project Docs and References
- Run Input Locking Tests
- Replicate Fit Quality Scores
- Data Load Integrity Tests
- Root Solver Robustness
- Forward Model Equilibrium Checks
- Data Fingerprint and Refusals
- Profile Interval Literature
- Status Dot Widget
- Session Test Fixtures
- On-Bound Estimate Display
- R² Formatting
- Competitive Binding Model Tests
- Replicate Noise Variance
- Titration Legend Redraw
- Replicate Spread Columns
- Stepwise Reference Solve
- Dialog Recording Fixtures
- Stepwise Release Precision
- Solver Speciation Robustness Tests
- Validation Code Hashing
- Validation Seed Ladder
- Binding Constant Profiles
- Sobol Sensitivity Analysis
- GUI Command Actions
- Error Source Statements
- Simulation Measurement Set
- Parameter Name Formatting
- Input Error Quantiles
- Misfit and Conflict Tests
- Replicate Outlier Detection
- Tooling Configuration
- Weak Second Step Design
- Second Constant Pretest
- Diagnostic P-Values
- Titrant Perturbation Check
- Replicate Exclusion Check
- Fitting App
- Tryptamine Test Data
- Before-After Check

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
- `test_the_settings_show_what_the_mode_needs_and_lock_during_a_run()` --uses--> `SensitivityMode`  [INFERRED]
  tests/unit/gui/test_sensitivity_view.py → core/pipeline/sensitivity.py
- `curve()` --calls--> `Curve`  [INFERRED]
  tests/unit/gui/test_results.py → gui/confidence.py
- `test_a_duplicate_session_takes_the_appearance_of_the_one_it_copies()` --uses--> `Change`  [INFERRED]
  tests/unit/gui/test_plot_appearance.py → gui/session_model.py
- `test_setting_an_appearance_says_so_once_and_setting_it_again_says_nothing()` --uses--> `Change`  [INFERRED]
  tests/unit/gui/test_plot_appearance.py → gui/session_model.py
- `Fitting workflow flowchart (load data, generate parameter sets, optimize, filter by RMSE/R², aggregate per replica, save)` --conceptually_related_to--> `Variable projection fit`  [AMBIGUOUS]
  docs/fitting_workflow.jpg → docs/scientific-summary.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Ka confidence interval construction** — docs_scientific_summary_f_test_interval, docs_scientific_summary_design_effect, docs_scientific_summary_input_aware_interval, docs_scientific_summary_one_step_pretest, docs_scientific_summary_noise_law [EXTRACTED 0.85]
- **How a validation rate is judged** — validation_readme_bradley_criterion, validation_readme_clopper_pearson, validation_readme_ladder, validation_readme_operating_characteristic, validation_readme_ladder_operating_characteristic [EXTRACTED 0.85]
- **Saved figure export pipeline** — docs_design_design_saved_figure, docs_design_design_export_stacked, docs_design_design_export_widget, docs_design_design_figure_head [EXTRACTED 0.90]
- **Model checking verdict combining misfit and conflict tests** — docs_scientific_summary_verdict, docs_scientific_summary_lack_of_fit, docs_scientific_summary_conflict_statistic, docs_scientific_summary_input_aware_interval [EXTRACTED 0.90]
- **Example assay datasets** — data_dba_system_host_to_dye, data_gda_system, data_ida_system, data_dye_alone [INFERRED 0.80]
- **Checks fit through the interface's own calls** — validation_readme_fit_measurement_set, validation_readme_fit_measurement_set_per_replica, validation_readme_fit_profile [INFERRED 0.80]

## Communities (252 total, 86 thin omitted)

### Community 0 - "Error Model Sources"
Cohesion: 0.02
Nodes (127): ErrorModel, spec_fraction(), estimated_fit_count(), estimated_model_solves(), _reported_sources(), run_sensitivity(), SensitivityConfig, SensitivityMode (+119 more)

### Community 1 - "Assay Module Definitions"
Cohesion: 0.02
Nodes (72): create_dba_host_to_dye(), H2GAssay, AssayMetadata, get_metadata(), list_assay_types(), _all_valid(), _competitive_free_host(), competitive_signal_point() (+64 more)

### Community 2 - "Reference Screen Rendering"
Cohesion: 0.02
Nodes (58): _again_on_display(), main(), _pointer(), render_all(), render_screen(), Screen, _wait(), appearance() (+50 more)

### Community 3 - "Fit Diagnostics Statistics"
Cohesion: 0.02
Nodes (99): addition_noise_covariance(), AdditionDraws, _bootstrap_ratios(), conflict_added(), conflict_p_value(), conflict_reference(), conflict_test(), _count_runs() (+91 more)

### Community 4 - "Theme and Figure Painting"
Cohesion: 0.03
Nodes (45): Figure, MenuColumns, _add_grid_line(), apply_plot_theme(), axis_box(), fit_line(), _follow_ticks_with_grid(), update() (+37 more)

### Community 5 - "Linearised Projected Fits"
Cohesion: 0.03
Nodes (93): _linearised(), replicate_scatter_ssr(), _fit_perturbed(), ProjectedFit, Projection, at(), judge(), at() (+85 more)

### Community 6 - "Input-Aware Fitting"
Cohesion: 0.03
Nodes (92): at_edge(), AwareFit, AwareProfile, AwareResult, conflict(), _edges(), _excess(), fit_jacobian() (+84 more)

### Community 7 - "IDA Assay Fitting Pipeline"
Cohesion: 0.02
Nodes (43): IDAAssay, fit_measurement_set(), FitConfig, FitWorker, _diluted_data(), _ida_assay(), ida_clean_result(), TestDataWithoutScatter (+35 more)

### Community 8 - "Export Multiple Dialog"
Cohesion: 0.02
Nodes (60): ExportMultipleDialog, _row(), FittingSession, side(), _SidePanel, _View, ExportRefused, Place (+52 more)

### Community 9 - "Input Uncertainty Specs"
Cohesion: 0.03
Nodes (78): homogeneity_sum(), what_if(), axis_reaches_zero(), InputSpec, SpecKind, _count(), _kind_name(), restate() (+70 more)

### Community 10 - "Results CSV Export"
Cohesion: 0.04
Nodes (84): export_results_csv(), ends(), number(), _csv_rows(), _diluted_shared_result(), _input_aware_result(), _law(), _on_bound_result() (+76 more)

### Community 11 - "Sensitivity Result Formatting"
Cohesion: 0.03
Nodes (78): is_shared(), source_name(), SensitivityResult, fmt_param(), fmt_param_plain(), superscript(), _assay(), _axis_value() (+70 more)

### Community 12 - "Button and Checkbox Widgets"
Cohesion: 0.02
Nodes (23): Button, Checkbox, Field, FileCard, _focus_ring(), NavItem, OutlineButton, paint_rich() (+15 more)

### Community 13 - "Hidden Fits Tests"
Cohesion: 0.03
Nodes (77): status_messages(), _assert_back(), _assert_hidden(), average_fit(), _curves(), _data(), _deliver(), _deliver_sensitivity() (+69 more)

### Community 14 - "Menu and Popover Painting"
Cohesion: 0.03
Nodes (27): diamond(), _focus_in(), hide_title_text(), _menu_command(), menu_html(), _menu_separator(), MenuRow, paint_popover() (+19 more)

### Community 15 - "Variance Budget Computation"
Cohesion: 0.03
Nodes (58): budget_of(), _density_ratio(), elasticities(), elasticity_perturbations(), homogeneity_tolerance(), identity_applies(), _input_directions(), _require_aware_dof() (+50 more)

### Community 16 - "Fit Result Container"
Cohesion: 0.03
Nodes (54): FitResult, input_replica_ids(), parameters_on_bound(), replica_order(), _legacy_input_ids(), callouts(), and_join(), describe_replicates() (+46 more)

### Community 17 - "Joint Confidence Region"
Cohesion: 0.03
Nodes (56): JointRegion, _bounded_solve(), facts(), interval(), _rank(), region(), test_a_cell_is_judged_against_its_own_cut_off(), test_a_cell_the_model_could_not_be_solved_in_is_outside_the_region() (+48 more)

### Community 18 - "Ka Profile Intervals"
Cohesion: 0.03
Nodes (73): ProfileResult, KaInterval, _bump_profile(), _conflicted(), _crossings(), _pixel(), stepped(), test_a_constant_its_bounds_fix_has_no_profile_plot() (+65 more)

### Community 19 - "Painted Text and Axes"
Cohesion: 0.03
Nodes (56): PaintedNote, PaintedText, axis_text_problems(), _tick_band(), title_rect(), session(), test_choosing_a_model_in_its_menu_reaches_the_session(), assert_card_fits() (+48 more)

### Community 20 - "Noise Law Model"
Cohesion: 0.03
Nodes (47): _flatness(), noise_law(), NoiseBasis, NoiseLaw, _read_share(), objective(), replicate_scatter(), _scatter() (+39 more)

### Community 21 - "Simulation Settings"
Cohesion: 0.04
Nodes (15): AssayType, Grid, Noise, SimulationForm, SimulationProblem, test_a_single_replicate_or_a_lawless_overlay_is_refused_in_plain_words(), test_a_stated_stock_dilutes_the_totals_the_stock_lacks_through_the_fitters_forward_model(), test_choosing_dilution_offers_a_stock_ten_times_the_highest_titrant_concentration_of_the_grid() (+7 more)

### Community 22 - "Profile Likelihood Fitting"
Cohesion: 0.04
Nodes (51): _resolve_bounds(), fit_profile(), _make_ida_data(), test_ida_projection_residual_is_the_model_residual_with_dilution(), _gda_assay(), TestResolveBounds, TestTheNoiseLawTheFitCarries, _demo_ms() (+43 more)

### Community 23 - "Measurement Set Container"
Cohesion: 0.04
Nodes (25): MeasurementSet, load_measurements(), _record_assay(), _perturbed_ms(), TestDemoQualityOnFittedReplicates, demo(), test_import_of_a_file_written_before_the_arithmetic_marker_is_shown_as_stored(), test_import_of_a_released_per_replicate_file_says_why_its_numbers_changed() (+17 more)

### Community 24 - "Card and Label Widgets"
Cohesion: 0.03
Nodes (25): badge(), Callout, canvas_section(), card_edge(), card_fill(), _card_rule(), copyable(), ElidedLabel (+17 more)

### Community 25 - "Budget and Analysis Form"
Cohesion: 0.03
Nodes (41): Budget, WhatIf, AnalysisForm, _heatmap(), _plain(), test_a_fixed_seed_must_be_a_whole_number_the_analysis_accepts(), test_a_heatmap_axis_reaching_zero_at_its_span_blocks_the_run_naming_it_and_the_span(), test_a_heatmap_axis_that_is_fixed_used_twice_or_shared_only_blocks_the_run_naming_the_input() (+33 more)

### Community 26 - "Validation Table Tests"
Cohesion: 0.04
Nodes (39): rows(), test_a_check_reads_only_the_cases_it_names(), test_a_family_is_pooled_over_the_seeds_every_one_of_its_cases_reached(), test_a_family_one_of_whose_cases_has_no_rows_is_not_published_as_the_family_s_rate(), test_a_filter_prints_the_matching_cases_and_says_that_it_did(), test_a_filter_that_matches_nothing_reads_no_rows_at_all(), test_a_filtered_check_that_reads_its_parent_whole_says_so_rather_than_naming_no_cases(), test_a_gap_in_a_case_s_seeds_ends_the_prefix_the_family_is_pooled_over() (+31 more)

### Community 27 - "Data Preprocessing Pipeline"
Cohesion: 0.05
Nodes (17): apply_preprocessing(), get_step(), PreprocessingStep, register_step(), ResultWriter, _header_comment(), _iter_points(), write_measurements_csv() (+9 more)

### Community 28 - "Plot Appearance Settings"
Cohesion: 0.03
Nodes (28): menu(), PlotAppearance, plot_appearance_default(), set_plot_appearance_default(), PlotAppearanceView, body(), _widget(), test_a_duplicate_session_takes_the_appearance_of_the_one_it_copies() (+20 more)

### Community 29 - "Parameter Summary Formatting"
Cohesion: 0.04
Nodes (37): ParameterSummary, fmt_against(), fmt_concentration(), fmt_estimate(), fmt_interval_html(), fmt_interval_plain(), fmt_percent(), _interval_text() (+29 more)

### Community 30 - "DBA Assay Model"
Cohesion: 0.04
Nodes (24): create_dba_dye_to_host(), DBAAssay, GDAAssay, X(), TestDBAQuantityConditions, TestGDAQuantityConditions, _dba(), _gda() (+16 more)

### Community 31 - "Dye-Alone Calibration Assay"
Cohesion: 0.04
Nodes (27): DyeAloneAssay, linear_signal(), bounds_from_dye_alone(), fit_linear_assay(), assert_within_tolerance(), _dba_assay(), dba_clean_result(), _dye_alone_assay() (+19 more)

### Community 32 - "Error Model Entry Form"
Cohesion: 0.05
Nodes (6): AdditionsEntry, InputEntry, SourceEntry, UncertaintyForm, test_an_assay_with_no_association_constant_states_nothing_and_says_why(), test_the_inputs_are_the_assays_perturbable_inputs_named_as_every_report_names_them()

### Community 33 - "Base Assay Class"
Cohesion: 0.04
Nodes (16): _and_list(), BaseAssay, _conc(), _addition_loading(), _aware_params(), _diagnose(), fit_measurement_set_per_replica(), _fit_weighted() (+8 more)

### Community 34 - "User-Facing Labels"
Cohesion: 0.04
Nodes (34): input_name(), _alike(), _at_most(), _conflict_text(), _consistent_text(), decimal_text(), _escape(), fmt_log10() (+26 more)

### Community 35 - "Validation Coverage Checks"
Cohesion: 0.04
Nodes (41): test_a_verdict_that_blames_the_model_the_inputs_or_both_is_a_false_alarm_on_good_data(), test_the_replicate_metrics_count_a_fit_that_lost_a_clean_replicate_once(), test_the_reported_coverage_is_read_by_the_largest_entry_error_and_never_judged(), addition_coverage(), addition_misfit(), addition_misstated(), agreement(), aware_coverage() (+33 more)

### Community 36 - "Fit Diagnostics Serialization"
Cohesion: 0.04
Nodes (45): FitDiagnostics, InputShift, MisfitTest, Verdict, verdict(), test_a_conflict_lists_as_its_correction_only_the_inputs_it_judged(), test_moved_inputs_give_input_aware_beside_inputs_as_entered_with_one_power_of_ten(), test_moved_inputs_the_test_did_not_reject_quote_the_test_not_a_bound() (+37 more)

### Community 37 - "Ensemble Statistics and Metrics"
Cohesion: 0.04
Nodes (20): describe(), describe_log10(), calculate_fit_metrics(), linear_regression(), _excluded_reason(), _replicate_rows(), _basis(), _factors() (+12 more)

### Community 38 - "Validation Store Tests"
Cohesion: 0.05
Nodes (33): test_a_change_in_how_a_row_is_generated_or_scored_retires_the_rows(), test_a_field_named_as_ignored_does_not_decide_the_exit_status(), test_a_field_one_run_writes_and_the_other_does_not_is_a_difference(), test_a_field_that_moved_is_named_with_its_case_and_seed(), test_a_half_written_line_costs_its_own_row_and_no_other(), test_a_key_only_one_run_holds_is_not_compared(), test_a_quantity_neither_run_could_produce_is_not_a_difference(), test_a_resumed_run_computes_only_the_missing_rows() (+25 more)

### Community 39 - "Path Problem Geometry"
Cohesion: 0.05
Nodes (17): density(), _on_one_path(), _one_step_p(), _Point, _Problem, held(), held(), stacked() (+9 more)

### Community 40 - "Confidence Verdict Rejections"
Cohesion: 0.04
Nodes (37): rejections(), reports_conditional(), _axis(), badge(), _count(), curve(), Curve, deviance() (+29 more)

### Community 41 - "Dark Mode Appearance"
Cohesion: 0.04
Nodes (30): Appearance, icon(), pixmap(), svg(), stylesheet(), _close(), contrast(), _controls() (+22 more)

### Community 42 - "Dataset Loading"
Cohesion: 0.04
Nodes (28): format_channel_label(), Dataset, _format_of(), _from_file(), _make_ms(), readable_extensions(), _slice_channel(), SourceFile (+20 more)

### Community 43 - "Shared and Addition Errors"
Cohesion: 0.05
Nodes (31): BudgetRow, AdditionError, shared_key(), SharedSource, _fitted_offsets(), default_worker_count(), test_own_and_shared_sources_are_reported_per_source_and_the_record_verifies(), _dba() (+23 more)

### Community 44 - "1:2 Host-Guest Assay"
Cohesion: 0.05
Nodes (29): HG2Assay, dba_clean(), dba_noisy(), dye_alone_clean(), gda_clean(), gda_noisy(), h2g_clean(), hg2_clean() (+21 more)

### Community 45 - "Validation Data Generation"
Cohesion: 0.04
Nodes (31): test_the_command_renders_every_reference_screen_in_both_themes(), dba_complex(), dba_signal_at(), fingerprint(), test_a_diluted_titration_is_measured_on_the_totals_each_point_carries(), test_a_diluted_titration_is_the_curve_the_assay_itself_draws(), test_a_noise_floor_joins_the_proportional_part_in_quadrature(), test_a_noisy_replicate_carries_three_times_the_noise_of_the_others() (+23 more)

### Community 46 - "Main Window Sessions"
Cohesion: 0.05
Nodes (9): _more_sessions(), _open_window(), FittingMainWindow, UpdateCheckWorker, test_load_data_offers_the_demo_and_fills_the_empty_session_on_screen(), _window(), test_the_switcher_lists_every_session_and_choosing_one_puts_it_on_screen(), test_the_startup_check_runs_only_while_switched_on() (+1 more)

### Community 47 - "Ka Grid Intervals"
Cohesion: 0.05
Nodes (21): addition_signal_loading(), _cut_interval(), _interval(), edge(), _ka_grid(), held(), residual(), q() (+13 more)

### Community 48 - "Measurement Set Tests"
Cohesion: 0.04
Nodes (10): _sample_dataframe(), _sample_measurement_set(), TestConstruction, TestDataAccess, TestFingerprint, TestImmutability, TestReplicaManagement, TestSetConcentrations (+2 more)

### Community 49 - "Session Fit and Export Actions"
Cohesion: 0.08
Nodes (33): _overlay_data(), test_no_tick_label_of_the_empty_titration_is_cut_at_an_edge(), test_every_link_to_the_help_raises_the_one_window_at_its_section(), test_the_binding_model_section_follows_the_model_chosen(), test_the_help_menu_raises_the_same_window_at_the_view_on_screen(), test_toolbar_help_opens_one_non_modal_window_at_the_section_of_each_view(), test_the_primary_action_offers_stop_while_a_fit_runs(), _ancestors() (+25 more)

### Community 50 - "Session Editing and Status"
Cohesion: 0.06
Nodes (4): _edit(), edit(), _format_remaining(), retire()

### Community 51 - "Confidence View"
Cohesion: 0.05
Nodes (8): _clear(), ConfidenceView, gap(), gap(), _legend(), ProfileFigure, RegionFigure, test_the_names_on_a_profile_s_strip_stand_whole_clear_of_their_bars_and_on_the_plot_s_axis()

### Community 52 - "GUI Layout Tests"
Cohesion: 0.06
Nodes (29): qapp(), test_every_painted_component_of_the_fitted_demo_gets_its_room_and_no_plot_header_is_cut(), _wait(), qapp(), test_every_menu_of_the_fitted_demo_fits_its_rows_and_its_window_and_marks_its_choice(), _wait(), _accent_pixels(), check_window() (+21 more)

### Community 53 - "Binding Conditions Entry"
Cohesion: 0.05
Nodes (17): Amount, _bound_text(), ConditionEntry, dye_alone_keys(), _entry(), _write(), field_text(), fmt_species() (+9 more)

### Community 54 - "Binding Help and Tests"
Cohesion: 0.06
Nodes (36): _dye_alone_help(), help_html(), assay_class(), _concentration_keys(), _form(), test_a_binding_constant_is_entered_in_inverse_molar(), test_a_bound_set_from_code_is_the_very_number_it_was_written_from(), test_a_condition_that_cannot_be_used_is_named_and_reaches_no_fit_as_a_number() (+28 more)

### Community 55 - "Validation Scenario Grids"
Cohesion: 0.07
Nodes (27): test_the_ignored_dilution_grid_fits_the_titrations_the_declared_grid_measures(), test_the_independent_reference_refuses_a_scenario_it_cannot_answer_for(), addition_aware_grid(), addition_grid(), addition_joint_grid(), addition_misstated_grid(), addition_replicate_grid(), _additions() (+19 more)

### Community 56 - "Session Display State"
Cohesion: 0.06
Nodes (5): projectable(), EmptyView, _shortcut(), test_a_concentration_unit_chosen_is_where_a_new_session_starts(), test_projectable_means_one_or_two_binding_constants_with_linear_signal_parameters()

### Community 57 - "Reference Interval Validation"
Cohesion: 0.07
Nodes (34): _decades_apart(), _reference(), _stepwise(), test_a_coefficient_the_minimum_holds_on_its_bound_is_not_counted_in_either_computation(), test_a_constant_whose_objective_falls_to_its_bound_rests_on_it_in_both_computations(), test_a_second_step_the_data_show_keeps_its_lower_limit(), test_an_input_known_to_a_vanishing_sigma_gives_the_interval_of_exact_inputs(), test_data_with_one_binding_step_give_the_second_constant_no_lower_limit() (+26 more)

### Community 58 - "Validation Run Jobs"
Cohesion: 0.06
Nodes (22): coverage_rows(), jobs(), test_a_case_stops_only_once_every_check_reading_it_has_passed_as_well(), test_a_case_that_fails_at_the_first_stage_goes_on_to_the_next(), test_a_case_whose_rate_has_passed_stops_where_it_is(), test_a_job_that_dies_is_stored_as_an_error_under_its_own_key(), test_a_one_step_null_case_can_fail_alone_and_pass_only_in_its_pooled_row(), test_a_pool_that_never_finishes_a_row_ends_the_run_rather_than_looping() (+14 more)

### Community 59 - "Conflict Verdict Sentences"
Cohesion: 0.09
Nodes (9): Conflict, verdict_sentence(), _diagnostics(), _f_test(), _runs(), _shift(), TestFmtMisfit, TestVerdictHeadline (+1 more)

### Community 60 - "Sobol Sensitivity Indices"
Cohesion: 0.06
Nodes (26): _block_order(), _count_on_bound(), sobol_indices_from_outputs(), sobol_indices_with_ci(), estimate_of(), quantities(), SobolEstimate, _check_against_loop() (+18 more)

### Community 61 - "Interval Inflation Factor"
Cohesion: 0.08
Nodes (28): inflation(), perturb_titrant(), _addition_covariance(), signal(), _alone(), _closed_forms(), _dba(), _dba_signal() (+20 more)

### Community 63 - "Session Model State"
Cohesion: 0.06
Nodes (7): SessionModel, test_before_an_analysis_sensitivity_names_only_the_steps_still_to_take(), make_model(), build(), make_model(), build(), view()

### Community 64 - "Interval Chart Widget"
Cohesion: 0.06
Nodes (5): CompactIntervals, IntervalChart, LegendRow, spaced_ticks(), test_the_legend_paints_the_mark_and_the_line_width_the_plot_draws()

### Community 65 - "Binding View"
Cohesion: 0.07
Nodes (11): file_filter(), Change, BindingView, _BoundRow, _caption(), _clear(), _ConditionRow, _grid() (+3 more)

### Community 66 - "Sensitivity View Blocks"
Cohesion: 0.08
Nodes (6): _clear(), SensitivityView, choose_source(), choose_target(), update(), _widget()

### Community 67 - "Validation Scenario IDs"
Cohesion: 0.05
Nodes (21): id_digest(), test_a_field_that_changes_the_data_changes_the_id(), test_a_noise_floor_says_nothing_without_noise_that_grows_with_the_signal(), test_a_scenario_refuses_a_stock_that_says_nothing(), test_a_scenario_refuses_an_input_its_assay_does_not_have(), test_a_scenario_refuses_departing_replicates_that_are_not_a_minority(), test_an_id_names_exactly_one_scenario(), test_every_case_of_a_check_has_its_own_id() (+13 more)

### Community 68 - "Validation Statistics Ladder"
Cohesion: 0.07
Nodes (19): _count_thresholds(), _ladder_by_paths(), test_a_case_that_is_exactly_nominal_is_failed_about_one_time_in_fifty(), test_a_coverage_rate_fails_only_when_the_draws_put_it_below_the_level(), test_a_coverage_rate_the_data_put_above_bradley_s_far_end_is_a_pass_called_conservative(), test_a_ladder_of_one_stage_is_one_look(), test_a_lower_limit_claim_is_the_same_rule_the_other_way_round(), test_a_test_at_the_5_per_cent_level_fails_only_when_it_rejects_too_often() (+11 more)

### Community 69 - "EnSight File Reader"
Cohesion: 0.07
Nodes (5): EnsightReader, _minimal_ensight(), _read_legacy_var_signal(), TestParsing, TestSniffing

### Community 70 - "Binding View Tests"
Cohesion: 0.07
Nodes (23): _magnitude(), state_binding(), _tab_order(), test_a_dye_alone_file_sets_the_signal_bounds_to_what_it_measured(), test_a_dye_alone_file_the_data_checks_refuse_is_named_with_the_refusal_itself(), test_a_stock_typed_in_its_field_reaches_the_fit_in_the_unit_shown(), test_each_bound_field_is_named_with_the_glossary_name_and_its_unit(), test_each_row_shows_its_own_problem_under_it() (+15 more)

### Community 71 - "BMG Workbook Parser"
Cohesion: 0.07
Nodes (12): _extract_metadata(), _find_bmg_sheet(), _find_header_row(), is_bmg_workbook(), parse_bmg_workbook(), XlsxReader, TestBMGDetection, TestBMGParse (+4 more)

### Community 72 - "Fit and Import Actions"
Cohesion: 0.07
Nodes (10): _problem_list(), Refusal, test_a_failed_run_says_why_and_keeps_the_last_result_shown(), test_a_run_counts_its_fits_on_the_status_bar_and_estimates_the_time_left(), test_a_run_uses_the_bounds_and_the_settings_stated(), capture(), test_a_seed_typed_and_run_at_once_is_the_seed_the_run_uses(), test_a_stopping_run_says_so_on_the_status_bar_and_not_its_counts() (+2 more)

### Community 73 - "Jasco File Reader"
Cohesion: 0.09
Nodes (4): JascoReader, _minimal_jasco(), TestParsing, TestSniffing

### Community 74 - "Titration Simulation"
Cohesion: 0.09
Nodes (24): _as_count(), _build_assay(), build_concentration_vector(), simulate_dataset(), simulate_signal(), simulate_species(), two_part_sd(), _dba_case() (+16 more)

### Community 75 - "Input Uncertainty Controls"
Cohesion: 0.08
Nodes (4): _InputRow, _SourceRow, UncertaintyView, format_condition()

### Community 76 - "Saved Figure Tests"
Cohesion: 0.08
Nodes (25): test_a_hidden_fit_draws_the_data_without_its_curve(), test_the_image_tool_of_the_titration_saves_the_plot(), test_the_saved_figure_states_each_fit_s_numbers_and_the_moved_inputs(), test_the_titration_header_keeps_its_room_with_several_fits_shown(), fit_on(), four_replicates(), test_a_curve_drawn_at_moved_inputs_says_so_and_one_at_the_entered_inputs_does_not(), test_overlaid_fits_on_different_replicates_are_noted() (+17 more)

### Community 77 - "Reader Registry Protocol"
Cohesion: 0.07
Nodes (9): MeasurementReader, get_reader(), register_reader(), _Accepter, _Fallback, isolated_registry(), _Rejecter, TestRegistry (+1 more)

### Community 79 - "Plot Appearance Tests"
Cohesion: 0.08
Nodes (22): _colours(), _fitted(), _import(), _items(), _many(), _marks(), _painted(), session() (+14 more)

### Community 80 - "Dilution Recovery Fitting"
Cohesion: 0.09
Nodes (16): fit_assay(), _assay(), _binary_free_host(), _competitive_free_host(), balance(), _decades_off(), _dye_signal(), _generate() (+8 more)

### Community 81 - "Variable Projection Profiles"
Cohesion: 0.07
Nodes (13): _draw(), _with_points(), FittedParameters, _follow_curves(), _ka_text(), _nearer_bound(), _read_steps(), halve() (+5 more)

### Community 82 - "Graph CI Workflow"
Cohesion: 0.05
Nodes (36): concurrency, group, env, ANTHROPIC_API_KEY, ANTHROPIC_MODEL, GRAPHIFY_NO_BACKUP, PYTHONHASHSEED, default (+28 more)

### Community 83 - "Session Lifecycle Tests"
Cohesion: 0.09
Nodes (19): state_dilution(), _deliver_sensitivity(), _session(), _state_an_uncertainty(), test_a_condition_that_is_not_a_number_refuses_the_fit_under_binding_model(), test_a_fit_and_an_analysis_never_run_at_the_same_time(), test_a_second_analysis_is_refused_while_one_is_running(), test_loading_other_data_stops_the_running_fit_instead_of_abandoning_it() (+11 more)

### Community 84 - "Results Serialization Tests"
Cohesion: 0.08
Nodes (4): offsets_held_at_zero(), _sample_fit_result(), TestOffsetsHeldAtZero, TestSerialization

### Community 85 - "Build and Release Workflow"
Cohesion: 0.06
Nodes (35): runs-on, steps, strategy, jobs, build, publish_release, os, name (+27 more)

### Community 86 - "Confidence View Tests"
Cohesion: 0.09
Nodes (23): move_pointer(), _show(), test_a_fit_with_no_binding_constant_says_there_is_nothing_to_profile(), test_a_fit_with_no_profile_and_no_data_asks_for_the_data_before_the_fit(), test_a_profile_that_failed_says_why_in_plain_words_beside_the_readings(), test_an_imported_result_with_no_data_says_its_numbers_were_not_checked(), test_both_readings_write_their_value_in_tabular_figures(), test_each_plot_header_sits_closer_to_its_own_plot_than_to_the_one_above() (+15 more)

### Community 87 - "Uncertainty View Tests"
Cohesion: 0.10
Nodes (23): _additions_only_fit(), _aware_fit(), _profile(), _show(), _shown(), _split_fit(), test_a_closed_end_far_below_the_others_never_reads_zero(), test_a_constant_with_no_interval_is_named_beside_the_one_drawn() (+15 more)

### Community 88 - "Session Export Actions"
Cohesion: 0.07
Nodes (3): bundled(), test_with_nothing_loaded_the_canvas_says_what_to_load(), test_save_plot_says_what_the_view_has_to_save()

### Community 89 - "Addition Error Validation"
Cohesion: 0.07
Nodes (15): dba_signal(), facts(), moved_series(), test_a_diluting_titrant_moves_the_series_and_dilutes_the_sample_by_the_volume_added(), test_a_titration_without_addition_error_is_drawn_from_its_noise_stream_alone(), test_a_weighted_fit_reports_the_law_it_was_weighted_by(), test_an_addition_error_a_scenario_cannot_carry_is_refused(), test_each_replicate_is_measured_on_its_own_series_of_additions() (+7 more)

### Community 90 - "Replica Signal Access"
Cohesion: 0.11
Nodes (8): prepare_plot_data(), _noisy_ms(), _per_replicate_record(), _simple_fit_result(), _simple_ms(), TestMeanFollowsTheFittedReplicates, TestPrepPlotDataFits, TestPrepPlotDataReplicas

### Community 91 - "Z-Score Replica Filter"
Cohesion: 0.08
Nodes (5): ZScoreReplicaFilter, _ms_few_replicas(), _ms_with_outlier(), TestRegistry, TestZScoreReplicaFilter

### Community 92 - "Fit View Reproduction"
Cohesion: 0.09
Nodes (13): fit_view(), _parameter_vector(), _reproduces(), _unmarked_slack(), TestFitViewAtMovedInputs, signal(), _absolute_tolerance_host(), _gda_assay() (+5 more)

### Community 94 - "Plot Zoom Navigation"
Cohesion: 0.15
Nodes (19): _data(), _range(), _shown(), test_a_double_click_resets_the_view(), test_a_pinch_zooms(), test_a_plain_wheel_over_the_plot_scrolls_the_page_that_holds_it(), test_a_theme_change_keeps_the_zoom(), test_another_display_unit_frames_the_plot_again() (+11 more)

### Community 95 - "Per-Replicate Fit Tests"
Cohesion: 0.12
Nodes (8): clean_pr_result(), _config(), _ida_conditions(), _ida_ms(), noisy_pr_result(), _replaced(), TestReplicateExclusion, TestReportedFitWithUncertainInputs

### Community 96 - "Imported Result Verification"
Cohesion: 0.11
Nodes (15): verify_imported_result(), fitted(), _legacy(), _measurement_set(), _round_trip(), test_a_file_scored_on_every_replicate_is_rescored_on_the_ones_the_fit_used(), test_a_fit_records_the_equilibrium_arithmetic_its_scores_were_computed_with(), test_average_fit_without_a_replicate_record_is_scored_on_the_selection_loaded_now() (+7 more)

### Community 97 - "Concentration Vector IO"
Cohesion: 0.10
Nodes (7): extract_concentrations_from_file(), read_raw_concentrations(), save_concentration_vector(), test_a_vector_keeps_its_own_unit_and_one_outside_the_list_is_converted_to_molar(), test_a_vector_with_a_negative_value_is_refused_whole(), TestConcentrationRoundTrip, TestExtractConcentrations

### Community 98 - "Tab-Separated Reader Writer"
Cohesion: 0.10
Nodes (4): _as_float(), TxtReader, TxtWriter, TestTxtReader

### Community 100 - "Main Window Views"
Cohesion: 0.09
Nodes (28): Binding model view, Fit results view, Help window, Input-aware, Input uncertainty view, Inputs as entered, Ka confidence view, Measurements view (+20 more)

### Community 101 - "Results File Provenance Checks"
Cohesion: 0.08
Nodes (16): released(), _released(), test_a_diluted_fit_with_a_shared_source_verifies_on_its_own_data(), test_a_file_naming_an_arithmetic_this_version_does_not_have_is_not_checked(), test_a_file_of_this_layout_without_a_noise_law_is_imported_and_verified(), test_a_file_without_a_marker_is_still_refused_on_other_data(), test_a_file_written_before_intervals_carries_none(), test_a_fit_that_moved_its_inputs_verifies_where_it_put_them() (+8 more)

### Community 102 - "Session Model Consistency Tests"
Cohesion: 0.10
Nodes (12): _demo(), _fit(), fits(), _holding(), _inconsistencies(), second(), _signals(), test_an_edit_is_said_once() (+4 more)

### Community 103 - "Parameter Summary Reporting"
Cohesion: 0.12
Nodes (4): summarize_parameters(), _interval(), TestSummarizeParameters, _with_moved_inputs()

### Community 104 - "Background Sensitivity Runner"
Cohesion: 0.09
Nodes (8): SensitivityRunError, _release(), SensitivityWorker, test_worker_delivers_a_held_back_count_as_soon_as_a_cancel_is_seen(), run(), test_worker_reports_an_unexpected_failure_in_plain_words(), written(), test_worker_throttles_progress_but_never_drops_the_last_count()

### Community 105 - "Help Window Text"
Cohesion: 0.10
Nodes (11): section_html(), help_off_screen(), _plain(), test_each_settings_side_panel_is_explained_in_its_section(), test_every_section_uses_one_heading_convention(), test_every_section_with_a_demo_plot_ends_on_its_demo_ida_example(), test_no_help_opens_as_a_modal_dialog_with_its_own_buttons(), test_the_measurements_section_explains_outlier_removal_as_the_panel_offers_it() (+3 more)

### Community 106 - "Measurement Identity Keys"
Cohesion: 0.09
Nodes (9): test_what_is_drawn_keys_the_measurement_and_what_is_stated_keys_the_case(), test_what_the_fit_is_told_leaves_the_measurement_alone(), test_a_replicate_that_departs_from_the_rest_reaches_the_key_its_measurements_hang_on(), test_a_shared_source_reaches_the_entry_stream_and_the_row_key(), test_leaving_the_stock_undeclared_keeps_the_titration_and_changes_the_fit(), test_the_dilution_of_a_titration_reaches_the_key_its_measurements_hang_on(), test_the_noise_structure_of_a_titration_reaches_the_key_its_measurements_hang_on(), _additions_token() (+1 more)

### Community 107 - "Concentration Data Validation"
Cohesion: 0.09
Nodes (7): concentration_problem(), _in_file(), at(), _molar_text(), _no_measurements(), _whose(), InvalidData

### Community 108 - "Multi-File Replicate Loading"
Cohesion: 0.12
Nodes (13): load_measurements_multi(), _jasco(), test_channel_file_rejected(), test_duplicate_stems_disambiguated(), test_empty_paths_raises(), test_heterogeneous_declared_units_converted_before_stack(), test_mismatched_grid_rejected(), test_mismatched_point_counts_rejected() (+5 more)

### Community 109 - "Fit Result Serialization"
Cohesion: 0.09
Nodes (4): _common_fields(), test_a_condition_with_no_known_unit_is_refused(), test_a_diluted_file_read_and_written_again_is_the_same_record(), test_the_file_survives_being_read_and_written_again()

### Community 110 - "Empty States and Demo"
Cohesion: 0.12
Nodes (15): _button(), _offered_folders(), _on_screen(), test_a_save_offers_the_folder_of_the_data_it_was_made_from(), test_every_empty_view_offers_load_data_and_the_demo_and_draws_no_bare_axes(), test_export_several_offers_no_folder_of_the_bundled_examples(), test_no_save_after_the_demo_offers_a_folder_inside_the_app(), test_no_view_says_there_is_no_fit_while_the_fit_runs() (+7 more)

### Community 111 - "Concentration Grid Editing"
Cohesion: 0.10
Nodes (5): ConcentrationGrid, drop(), commit(), SliderEnd, commit()

### Community 112 - "Slider Knob Scaling"
Cohesion: 0.14
Nodes (4): Knob, _three_figures(), unit_text(), _KnobRow

### Community 113 - "GUI Layout Rule Checks"
Cohesion: 0.14
Nodes (11): check(), clashing_names(), cut_axis_text(), cut_headers(), cut_labels(), cut_sideways(), interactive(), _name() (+3 more)

### Community 114 - "GUI Render Test Helpers"
Cohesion: 0.13
Nodes (12): _open_menu(), _point_at(), render(), _settle(), _snapshot(), test_a_pointer_with_no_plot_on_screen_is_refused(), test_a_render_at_a_scale_has_that_many_device_pixels_per_logical_pixel(), test_a_render_is_drawn_in_the_style_the_app_ships_with() (+4 more)

### Community 115 - "Value and Interval Formatting"
Cohesion: 0.10
Nodes (10): fmt_value(), replicate_summary(), headline_interval(), number(), fmt(), Marker, _reading_marker(), number() (+2 more)

### Community 117 - "Simulation Plots and Overlay"
Cohesion: 0.12
Nodes (4): Overlay, tag_text(), SimulationPlots, power_of_ten()

### Community 118 - "Sensitivity Worker Processes"
Cohesion: 0.12
Nodes (9): batch(), _evaluate(), test_a_batch_over_worker_processes_leaves_this_process_uncapped(), test_a_job_that_fails_outright_stops_the_batch_at_once_in_plain_words(), test_a_stop_is_answered_while_the_pool_is_still_starting(), test_a_stopped_batch_drops_the_fits_it_had_queued(), test_a_worker_started_under_the_cap_inherits_it(), test_the_point_weights_of_the_run_reach_every_worker_process() (+1 more)

### Community 119 - "Update Check Lifecycle Tests"
Cohesion: 0.12
Nodes (10): checks(), dialogs(), _ScriptedCheck, _settle(), _SlowToEnd, test_a_check_that_reported_is_deleted_only_once_its_thread_has_ended(), test_a_finished_check_lets_go_of_itself_and_not_of_the_check_that_replaced_it(), test_asking_for_a_check_while_one_is_running_says_so() (+2 more)

### Community 120 - "Fit Cancellation Test Stubs"
Cohesion: 0.12
Nodes (14): FitCancelled, watchful_fit(), run(), watchful_sensitivity(), run(), window(), slow_fit(), fake() (+6 more)

### Community 121 - "Sensitivity Export Fixtures"
Cohesion: 0.13
Nodes (12): baseline_fit(), run(), heatmap_result(), made_on(), sobol_result(), stopped_result(), _artefact(), test_a_budget_with_no_number_in_it_is_refused_rather_than_written_empty() (+4 more)

### Community 122 - "Session Model Rule Tests"
Cohesion: 0.15
Nodes (15): _data(), _holding(), _state(), test_a_cancelled_fit_leaves_the_previous_result_as_it_was(), test_a_condition_hides_the_fit_once_its_edit_is_finished_and_setting_it_back_shows_it_again(), test_a_fit_that_cannot_start_says_why(), test_a_fit_that_needs_a_refit_is_marked_out_of_date_everywhere(), test_adding_files_to_a_session_with_no_data_keeps_the_results_it_holds() (+7 more)

### Community 123 - "Uncertainty Budget Validation"
Cohesion: 0.11
Nodes (10): conditional_variance(), _exact_row(), test_a_row_whose_fits_stayed_inside_the_ka_box_is_the_one_the_quadrature_judges(), test_a_row_with_a_fit_on_a_ka_bound_says_nothing_about_the_source_variance(), test_the_budget_row_estimates_the_quantities_it_labels(), test_the_closed_budget_of_a_test_function_is_the_one_sampling_it_finds(), test_the_spread_left_without_a_source_is_read_off_the_first_order_index(), test_the_what_if_errors_are_reported_again_over_the_rows_with_no_fit_on_a_bound() (+2 more)

### Community 124 - "Replicate Outlier Detection"
Cohesion: 0.15
Nodes (14): rows(), _cochran_limit(), replicate_outliers(), q_min(), _replicate_projection(), _replicates(), test_a_replicate_that_needs_another_ka_is_excluded_by_name(), test_a_replicate_three_times_noisier_than_the_others_is_left_out_for_its_scatter() (+6 more)

### Community 125 - "Update Check and Download"
Cohesion: 0.13
Nodes (4): is_newer(), newest_release(), test_a_beta_build_is_offered_the_newest_published_release_beta_or_stable(), TestIsNewer

### Community 126 - "Download Worker Dialog"
Cohesion: 0.10
Nodes (4): DownloadWorker, _os_label(), _pick_asset(), UpdateAvailableDialog

### Community 128 - "Unit Display Formatting"
Cohesion: 0.12
Nodes (7): _canonical_unit(), fmt_unit_html(), fmt_unit_pretty(), replicate_line(), _bounds_text(), TestFmtUnitHtml, TestFmtUnitPretty

### Community 129 - "Analysis Configuration and Simulation"
Cohesion: 0.10
Nodes (4): readout_value(), species_groups(), qapp(), test_the_help_examples_are_the_numbers_demo_ida_shows()

### Community 130 - "Validation Check Rows"
Cohesion: 0.10
Nodes (10): test_a_row_of_stated_additions_carries_the_factor_each_interval_was_widened_by(), replace_replicates(), test_a_row_of_each_new_scenario_carries_what_its_check_reads(), test_a_row_of_stated_inputs_carries_the_standard_score_each_entry_was_drawn_at(), test_a_row_says_what_the_replicates_showed_about_the_noise(), test_a_scenario_of_an_older_grid_stores_the_fields_its_rows_already_hold(), test_a_single_titration_reports_that_its_noise_was_taken_as_constant(), test_a_two_step_row_carries_the_one_step_p_value_of_the_second_constant_alone() (+2 more)

### Community 131 - "Reference F-Test Profiles"
Cohesion: 0.11
Nodes (15): _independent_one_ka(), solve(), verdict(), _independent_two_ka(), profile(), at(), solve(), verdict() (+7 more)

### Community 134 - "Titration Data and Plot Axes"
Cohesion: 0.11
Nodes (8): _equal(), TitrationData, _axes(), _drawn_text(), test_each_axis_text_size_is_one_even_step_up_at_one_weight(), test_the_axes_grow_with_the_text_in_even_steps_and_keep_it_whole(), test_the_x_axis_title_of_a_saved_figure_is_whole_at_every_size(), _title_font()

### Community 137 - "Session Closing Tests"
Cohesion: 0.20
Nodes (13): _load(), test_closing_a_session_mid_fit_stops_the_fit_and_leaves_no_thread_running(), test_closing_a_session_mid_run_takes_its_work_off_the_status_bar(), test_closing_a_session_mid_sensitivity_stops_the_run_and_its_worker_processes(), test_closing_the_last_session_leaves_an_empty_new_session(), test_closing_the_window_stops_the_work_in_every_session(), test_every_run_is_asked_to_stop_before_any_of_them_is_waited_for(), watchful_profile() (+5 more)

### Community 138 - "Main Window Tests"
Cohesion: 0.14
Nodes (10): _settings_at_end(), test_add_files_adds_replicates_to_the_session_on_screen(), test_loading_into_a_new_session_and_choosing_no_file_leaves_the_sessions_as_they_were(), test_the_number_shortcuts_reach_the_sessions_in_order(), test_the_side_panel_toggle_hides_the_side_panel_of_every_view(), test_the_view_on_screen_is_kept_across_sessions_and_its_selection_holds(), window(), test_fit_the_data_in_a_session_with_data_opens_a_new_session() (+2 more)

### Community 139 - "Units and Fit Pipeline Design"
Cohesion: 0.13
Nodes (17): Fitting workflow flowchart (load data, generate parameter sets, optimize, filter by RMSE/R², aggregate per replica, save), Pint units audit, au = [signal] dimension fix, core/units.py (reference), core/pipeline/fit_pipeline.py (reference), core/optimizer/scaling.py _scale_factor (reference), test_registry_units.py (reference), Pint practical reference (+9 more)

### Community 140 - "Fit Worker Cleanup Tests"
Cohesion: 0.12
Nodes (7): _settle(), test_a_finished_fit_leaves_neither_its_worker_nor_its_profile_worker_behind(), test_a_fit_that_fails_leaves_no_worker_behind(), test_a_second_fit_does_not_leave_the_first_fits_profile_running(), watch(), test_a_worker_whose_thread_ends_as_the_wait_runs_out_is_let_go_of(), test_loading_other_data_discards_the_ka_profile_still_computed_for_the_old_fit()

### Community 141 - "Plain Text Labels"
Cohesion: 0.16
Nodes (5): plain_label(), _subscript(), test_every_parameter_and_input_is_named_from_one_label_in_every_view(), test_plain_label_gives_back_the_characters_html_escaped(), TestPlainLabel

### Community 142 - "Shared Error Sources"
Cohesion: 0.12
Nodes (5): aware(), test_two_sources_on_one_input_multiply_there(), test_a_scenario_refuses_a_shared_source_it_cannot_carry(), test_the_error_model_carries_the_specs_and_the_shared_sources_the_scenario_states(), SharedEntry

### Community 143 - "Budget Validation Cases"
Cohesion: 0.15
Nodes (7): test_a_budget_case_is_addressed_by_what_it_runs(), test_every_exact_case_carries_the_source_its_claim_is_about(), test_every_what_if_case_asks_for_an_improvement_of_a_source_it_states(), BudgetCase, exact_cases(), whatif_cases(), whatif_row()

### Community 144 - "Conditional Fit Results Tests"
Cohesion: 0.17
Nodes (4): ConditionalFit, _stepwise_result(), test_a_signal_parameter_the_fit_ended_on_an_entered_bound_is_named_with_that_bound(), TestTheSecondStepAndTheMisfitReference

### Community 145 - "Datasets and Design System"
Cohesion: 0.13
Nodes (15): DBA host-to-dye titration data, Dye-alone calibration data, GDA titration data, IDA titration data, Data meta data readme, Dye-alone linear fit results, SupraSimFit design system, One meaning per colour principle (+7 more)

### Community 146 - "Parameter Kinds and Binding Constants"
Cohesion: 0.14
Nodes (6): ParamKind, _binding_constant_keys(), _ka_boxes(), binding_constants(), _ka_keys(), test_binding_constants_are_exactly_the_log_scale_params()

### Community 147 - "Results Export and Import"
Cohesion: 0.21
Nodes (8): export_results(), import_appearance(), import_results(), _read_results_file(), test_a_diluted_fit_with_a_shared_source_is_read_back_as_the_fit_it_was(), _wait_until(), test_a_results_file_carries_the_appearance_to_the_session_that_imports_it(), test_a_results_file_keeps_its_results_beside_the_appearance()

### Community 150 - "Documentation Currency Tests"
Cohesion: 0.14
Nodes (6): _live_texts(), test_no_live_text_names_machinery_the_app_does_not_have(), test_the_architecture_table_names_every_pipeline_module(), test_the_documents_name_the_fit_the_app_performs(), test_the_scan_reaches_the_texts_a_reader_and_the_program_depend_on(), test_the_validation_readme_lists_every_check_with_its_claim_and_criterion()

### Community 151 - "Input-Aware Documentation Tests"
Cohesion: 0.14
Nodes (6): test_the_binding_model_help_points_at_the_view_the_uncertainties_are_entered_in(), test_the_instructions_list_every_module_of_the_fitting_pipeline(), test_the_readme_explains_every_basis_a_noise_law_can_report(), test_the_readme_explains_every_verdict_a_fit_can_report(), test_the_validation_readme_names_every_check_the_package_runs(), test_the_validation_readme_quotes_each_check_s_own_claim()

### Community 152 - "Input-Aware Validation Grid"
Cohesion: 0.19
Nodes (7): test_every_shared_source_case_states_the_same_model_the_entries_come_from(), test_the_input_aware_noise_law_grid_states_its_inputs_and_replicates_them(), concentration_inputs(), _kind(), noise_law_aware_grid(), shared_source_grid(), stated_specs()

### Community 156 - "Per-Replicate Fit Recovery"
Cohesion: 0.17
Nodes (5): fit_replica_ids(), TestPerReplicateRecovery, test_replicates_of_one_titration_are_all_kept(), test_the_replicate_that_needs_another_ka_is_left_out_and_named(), test_the_reported_fit_is_the_fit_of_the_average_of_the_replicates_used()

### Community 159 - "Fit Config Serialization"
Cohesion: 0.20
Nodes (4): _config_to_dict(), _finite_or_none(), test_a_bound_with_no_limit_is_written_as_strict_json_and_read_back_as_no_limit(), fit()

### Community 161 - "Conditions Form Layout"
Cohesion: 0.44
Nodes (3): _caption(), _column(), _widget()

### Community 162 - "Render Harness Tests"
Cohesion: 0.20
Nodes (4): qapp(), test_the_fitted_state_is_drawn_after_the_fit_and_its_profile(), noting_snapshot(), test_the_heatmap_state_reads_the_cell_under_the_pointer()

### Community 164 - "Stepwise Mass Balance Tests"
Cohesion: 0.18
Nodes (3): TestH2GMassBalance, TestHG2MassBalance, equations()

### Community 165 - "Simulated Truth Conditions"
Cohesion: 0.20
Nodes (4): _addition_errors(), _point_totals(), _truth(), fixed_concentrations()

### Community 167 - "Sensitivity Panel Tests"
Cohesion: 0.24
Nodes (7): fake_run(), test_a_finished_analysis_leaves_no_worker_behind(), test_the_analysis_is_told_what_the_panel_calls_each_input(), record(), test_the_analysis_varies_the_inputs_the_shared_panel_states(), record(), run()

### Community 168 - "Test Store Fixtures"
Cohesion: 0.20
Nodes (4): store(), results(), code_copy(), results()

### Community 174 - "Error Warning Handling"
Cohesion: 0.25
Nodes (4): _Emitter, test_a_slot_that_raises_is_said_once_and_logged(), refresh(), test_an_error_while_the_warning_is_open_is_logged_without_a_second_dialog()

### Community 175 - "Side Panel Label Width"
Cohesion: 0.25
Nodes (4): _laid_out_width(), _shown_text(), test_a_shared_source_named_in_one_long_word_is_shown_whole(), test_fit_details_fit_the_side_panel_at_its_least_width_beside_the_scroll_bar()

### Community 176 - "Session Settings"
Cohesion: 0.25
Nodes (4): _cancelled(), _evaluate(), _tally(), SessionSettings

### Community 177 - "Plot Export Components"
Cohesion: 0.25
Nodes (5): figure_head(), PlotHeader, PlotNavigation, Plots (Design §7), Saved figure

### Community 181 - "Project Docs and References"
Cohesion: 0.29
Nodes (7): SupraSimFit Readme, data/Readme.md (reference), docs/scientific-summary.md (reference), Sinn et al. 2019 CB8 indicator-displacement assay, Sinn et al. 2020 guest-displacement assay, SupraSimFit desktop app, validation/README.md (reference)

### Community 182 - "Run Input Locking Tests"
Cohesion: 0.33
Nodes (3): _start(), test_the_binding_model_is_locked_while_a_run_reads_it(), test_the_uncertainty_rows_are_locked_while_a_run_reads_them()

### Community 183 - "Replicate Fit Quality Scores"
Cohesion: 0.33
Nodes (4): _score(), test_every_given_replicate_has_its_own_fit_measured_against_itself(), test_the_reported_quality_is_measured_on_the_replicates_used(), _used_mean()

### Community 188 - "Profile Interval Literature"
Cohesion: 0.33
Nodes (6): Bates & Watts 1988, F-test profile interval, Hodges & Sargent 2001, Input-aware penalised profile interval, Raue et al. 2009, Signal coefficient degeneracy

### Community 190 - "Session Test Fixtures"
Cohesion: 0.33
Nodes (3): make_session(), build(), qapp()

### Community 191 - "On-Bound Estimate Display"
Cohesion: 0.33
Nodes (3): _on_bound(), test_an_estimate_on_its_search_bound_keeps_its_number_beside_its_unit(), test_an_estimate_the_data_limit_on_neither_side_shows_no_unit_without_a_number()

### Community 194 - "Replicate Noise Variance"
Cohesion: 0.50
Nodes (3): cut(), reported(), result()

### Community 197 - "Stepwise Reference Solve"
Cohesion: 0.40
Nodes (4): top(), residual(), test_a_signal_offset_the_minimum_holds_on_zero_is_not_counted_among_what_the_fit_fitted(), solve()

### Community 199 - "Stepwise Release Precision"
Cohesion: 0.40
Nodes (3): test_a_stepwise_file_is_checked_at_the_precision_of_its_free_ligand_solve(), result_off_by(), solve()

### Community 202 - "Validation Seed Ladder"
Cohesion: 0.40
Nodes (5): Validation README, fit_measurement_set, Seed ladder 100→200→400, validation.criteria.ladder_operating_characteristic, Result store (code-hashed jsonl)

### Community 204 - "Sobol Sensitivity Analysis"
Cohesion: 0.50
Nodes (4): Dilution of fixed totals, Scaling identity of elasticities, Sobol' 2001, Sobol' variance decomposition

### Community 212 - "Misfit and Conflict Tests"
Cohesion: 0.67
Nodes (3): Input conflict statistic, Lack-of-fit F test and runs test, Holm-combined verdict

### Community 213 - "Replicate Outlier Detection"
Cohesion: 0.67
Nodes (3): Hadi & Simonoff 1993, Replicate forward search and Cochran test, Replicates averaged, not pooled

## Ambiguous Edges - Review These
- `Variable projection fit` → `Fitting workflow flowchart (load data, generate parameter sets, optimize, filter by RMSE/R², aggregate per replica, save)`  [AMBIGUOUS]
  docs/fitting_workflow.jpg · relation: conceptually_related_to

## Knowledge Gaps
- **55 isolated node(s):** `uv`, `fitting-app`, `Bradley, Robustness? (1978)`, `Buehler, Some validity criteria for statistical inferences (1959)`, `SimulationForm` (+50 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 3930 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **86 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `AssayType` connect `Simulation Settings` to `Error Model Sources`, `Assay Module Definitions`, `Reference Screen Rendering`, `Fit Diagnostics Statistics`, `Reference F-Test Profiles`, `Linearised Projected Fits`, `Input-Aware Fitting`, `IDA Assay Fitting Pipeline`, `Export Multiple Dialog`, `Input Uncertainty Specs`, `Main Window Tests`, `Sensitivity Result Formatting`, `Session Closing Tests`, `Hidden Fits Tests`, `Shared Error Sources`, `Variance Budget Computation`, `Fit Result Container`, `Plain Text Labels`, `Parameter Kinds and Binding Constants`, `Painted Text and Axes`, `Ka Profile Intervals`, `Conditional Fit Results Tests`, `Profile Likelihood Fitting`, `Measurement Set Container`, `Input-Aware Documentation Tests`, `Joint Confidence Region`, `Plot Appearance Settings`, `Parameter Summary Formatting`, `DBA Assay Model`, `Dye-Alone Calibration Assay`, `Error Model Entry Form`, `Base Assay Class`, `User-Facing Labels`, `Ensemble Statistics and Metrics`, `Confidence Verdict Rejections`, `Shared and Addition Errors`, `1:2 Host-Guest Assay`, `Validation Data Generation`, `Session Settings`, `Session Fit and Export Actions`, `Binding Conditions Entry`, `Binding Help and Tests`, `Session Display State`, `Reference Interval Validation`, `Interval Inflation Factor`, `Binding Form Model`, `Session Model State`, `Session Test Fixtures`, `Binding View Tests`, `Saved Figure Tests`, `Validation Check Rows`, `Plot Appearance Tests`, `Variable Projection Profiles`, `Session Lifecycle Tests`, `Results Serialization Tests`, `Uncertainty View Tests`, `Weak Second Step Design`, `Fit Results View`, `Session Model Consistency Tests`, `Parameter Summary Reporting`, `Help Window Text`, `Fit Result Serialization`, `Sensitivity Export Fixtures`, `Session Model Rule Tests`, `Replicate Outlier Detection`?**
  _High betweenness centrality (0.072) - this node is a cross-community bridge._
- **Are the 200 inferred relationships involving `AssayType` (e.g. with `BaseAssay` and `DBAAssay`) actually correct?**
  _`AssayType` has 200 INFERRED edges - model-reasoned connections that need verification._
- **What connects `uv`, `fitting-app`, `Bradley, Robustness? (1978)` to the rest of the system?**
  _55 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Error Model Sources` be split into smaller, more focused modules?**
  _Cohesion score 0.021333333333333333 - nodes in this community are weakly interconnected._
- **Why does `MeasurementSet` connect `Measurement Set Container` to `Error Model Sources`, `Assay Module Definitions`, `Reference Screen Rendering`, `IDA Assay Fitting Pipeline`, `Export Multiple Dialog`, `Input Uncertainty Specs`, `Hidden Fits Tests`, `Variance Budget Computation`, `Fit Result Container`, `Joint Confidence Region`, `Ka Profile Intervals`, `Noise Law Model`, `Simulation Settings`, `Profile Likelihood Fitting`, `Budget and Analysis Form`, `Data Preprocessing Pipeline`, `Per-Replicate Fit Recovery`, `Dye-Alone Calibration Assay`, `Base Assay Class`, `Ensemble Statistics and Metrics`, `Dataset Loading`, `Shared and Addition Errors`, `1:2 Host-Guest Assay`, `Measurement Set Tests`, `Session Fit and Export Actions`, `Binding Conditions Entry`, `Replicate Fit Quality Scores`, `Data Fingerprint and Refusals`, `Session Model State`, `Binding View Tests`, `Stepwise Release Precision`, `Fit and Import Actions`, `Titration Simulation`, `Saved Figure Tests`, `Simulation Measurement Set`, `Variable Projection Profiles`, `Replica Signal Access`, `Z-Score Replica Filter`, `Fit View Reproduction`, `Per-Replicate Fit Tests`, `Imported Result Verification`, `Results File Provenance Checks`, `Session Model Consistency Tests`, `Background Sensitivity Runner`, `Concentration Data Validation`, `Multi-File Replicate Loading`, `Sensitivity Worker Processes`, `Fit Cancellation Test Stubs`, `Session Model Rule Tests`?**
  _High betweenness centrality (0.066) - this node is a cross-community bridge._
- **Are the 34 inferred relationships involving `ErrorModel` (e.g. with `FitConfig` and `reports_conditional()`) actually correct?**
  _`ErrorModel` has 34 INFERRED edges - model-reasoned connections that need verification._

### Low-confidence Hints
_AMBIGUOUS edges — the extractor was unsure. Verify before acting on these._

- **What is the exact relationship between `Variable projection fit` and `Fitting workflow flowchart (load data, generate parameter sets, optimize, filter by RMSE/R², aggregate per replica, save)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._