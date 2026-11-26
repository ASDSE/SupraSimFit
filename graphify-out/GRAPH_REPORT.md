# Graph Report - SupraSimFit  (2026-11-26)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 9493 nodes · 26157 edges · 238 communities (153 shown, 85 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 2524 edges (avg confidence: 0.91)
- Token cost: 26,602 input · 3,236 output

## Graph Freshness
- Built from commit: `7bb3ff15`
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
- Status Bar
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
- Profile Interval Display Tests
- Stepwise Titration Engine Tests
- Weak Identification Pretest
- Diagnostic P-Values
- Non-Blocking Dialog Recording
- Diluted Fit Fixture
- Fit Fixture Copies
- Replicate Exclusion Checks
- Fitting App
- Tryptamine Fluorescence Test Data

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
- `curve()` --calls--> `Curve`  [INFERRED]
  tests/unit/gui/test_results.py → gui/confidence.py
- `scores_off_by()` --indirect_call--> `released()`  [INFERRED]
  tests/unit/test_released_results.py → gui/main_window.py
- `Fitting workflow flowchart: load data, initial guess, multi-start optimization, RMSE/R² filtering, aggregate good fits, replicas loop, save results` --conceptually_related_to--> `Variable projection fit`  [AMBIGUOUS]
  docs/fitting_workflow.jpg → docs/scientific-summary.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Rate judging rule** — validation_readme_bradley_criterion, validation_readme_clopper_pearson, validation_readme_ladder, validation_readme_criteria [EXTRACTED 0.85]
- **Saved figure export pipeline** — docs_design_design_saved_figure, docs_design_design_export_stacked, docs_design_design_export_widget, docs_design_design_figure_head [EXTRACTED 0.90]
- **Model checking and verdict** — docs_scientific_summary_lack_of_fit_test, docs_scientific_summary_conflict_statistic, docs_scientific_summary_verdict, docs_scientific_summary_input_aware_interval [EXTRACTED 0.90]
- **Bundled example assay datasets** — data_dba_system_host_to_dye, data_dye_alone, data_gda_system, data_ida_system, data_readme [INFERRED 0.80]
- **Pint unit boundary design** — docs_pint_findings_quantities_at_edges, docs_pint_findings_paramkind, docs_pint_audit_au_signal_dimension_fix, docs_pint_findings_never_to_base_units [INFERRED 0.80]

## Communities (238 total, 85 thin omitted)

### Community 0 - "Assay Base Classes"
Cohesion: 0.02
Nodes (71): BaseAssay, create_dba_dye_to_host(), create_dba_host_to_dye(), AssayMetadata, get_metadata(), list_assay_types(), _excluded_reason(), _replica_fit() (+63 more)

### Community 1 - "Sensitivity Run Configuration"
Cohesion: 0.03
Nodes (105): ErrorModel, default_worker_count(), estimated_fit_count(), estimated_model_solves(), run_sensitivity(), _cancelled(), _evaluate(), _tally() (+97 more)

### Community 2 - "Fit Configuration and Bounds"
Cohesion: 0.03
Nodes (83): HG2Assay, IDAAssay, FitConfig, _resolve_bounds(), fit_profile(), _make_ida_data(), test_own_and_shared_sources_are_reported_per_source_and_the_record_verifies(), ida_clean_result() (+75 more)

### Community 3 - "Theme and Appearance Mode"
Cohesion: 0.02
Nodes (48): Appearance, AxisScale, badge(), Callout, canvas_section(), card_edge(), card_fill(), _card_rule() (+40 more)

### Community 4 - "Addition Error Validation Tests"
Cohesion: 0.02
Nodes (76): dba_signal(), moved_series(), test_a_diluting_titrant_moves_the_series_and_dilutes_the_sample_by_the_volume_added(), test_a_row_of_stated_additions_carries_the_factor_each_interval_was_widened_by(), test_a_titration_without_addition_error_is_drawn_from_its_noise_stream_alone(), test_an_addition_error_a_scenario_cannot_carry_is_refused(), test_each_replicate_is_measured_on_its_own_series_of_additions(), test_repeated_reads_of_one_titration_share_its_additions() (+68 more)

### Community 5 - "Uncertainty Budget Elasticities"
Cohesion: 0.02
Nodes (69): Budget, budget_of(), BudgetRow, _density_ratio(), elasticities(), elasticity_perturbations(), homogeneity_sum(), homogeneity_tolerance() (+61 more)

### Community 6 - "Custom Button Widgets"
Cohesion: 0.02
Nodes (21): Button, CompactIntervals, ConcentrationGrid, Field, FileCard, IntervalChart, LegendRow, NavItem (+13 more)

### Community 7 - "Results CSV Export"
Cohesion: 0.04
Nodes (84): export_results_csv(), ends(), number(), _csv_rows(), _diluted_shared_result(), _input_aware_result(), _law(), _on_bound_result() (+76 more)

### Community 8 - "Input-Aware Weighted Fitting"
Cohesion: 0.03
Nodes (88): _addition_loading(), _aware_params(), _diagnose(), _fit_weighted(), _titrant_stock(), at_edge(), AwareFit, AwareProfile (+80 more)

### Community 9 - "Fit Result Container"
Cohesion: 0.03
Nodes (69): ParamKind, FitResult, _at_bound(), _binding_constant_keys(), fit_replica_ids(), input_replica_ids(), _ka_boxes(), offsets_held_at_zero() (+61 more)

### Community 10 - "Sensitivity Result Display"
Cohesion: 0.03
Nodes (76): SensitivityResult, fmt_param(), _assay(), _axis_value(), badge(), budget_csv_rows(), row(), budget_refusal() (+68 more)

### Community 11 - "Fit Diagnostics Tests"
Cohesion: 0.03
Nodes (74): addition_noise_covariance(), AdditionDraws, _bootstrap_ratios(), conflict_added(), conflict_p_value(), conflict_reference(), conflict_test(), _count_runs() (+66 more)

### Community 12 - "Variable Projection Fitting"
Cohesion: 0.03
Nodes (42): _point_weights(), _fixed_inputs(), cut(), reported(), result(), FittedParameters, _ka_grid(), _nearer_bound() (+34 more)

### Community 13 - "Input Uncertainty Specs"
Cohesion: 0.03
Nodes (70): InputConstraint, InputSpec, SpecKind, specs_from_dict(), specs_to_dict(), restate(), spread_pct(), ranged_result() (+62 more)

### Community 14 - "Measurement Set Replicas"
Cohesion: 0.03
Nodes (33): _in_file(), MeasurementSet, _whose(), load_measurements(), _replicate_rows(), _record_assay(), _experiment(), _scaled() (+25 more)

### Community 15 - "Assay Types and Residuals"
Cohesion: 0.04
Nodes (86): AssayType, hg2_signal(), test_the_model_line_names_a_calibration_as_the_badge_does_and_claims_no_interval(), _assay(), _compensated_bounds(), _compensated_hg2(), _gda_offset_on_its_floor(), _hand_built() (+78 more)

### Community 16 - "Fit Metrics and Fingerprints"
Cohesion: 0.03
Nodes (56): calculate_fit_metrics(), _fitted_offsets(), _legacy_input_ids(), verify_imported_result(), _diluted_data(), test_a_diluted_fit_with_a_shared_source_is_read_back_as_the_fit_it_was(), _wait_until(), test_an_imported_fit_names_its_replicates_by_their_letters_without_the_data() (+48 more)

### Community 17 - "Plot Theme Styling"
Cohesion: 0.03
Nodes (30): _add_grid_line(), apply_plot_theme(), axis_box(), fit_line(), _follow_ticks_with_grid(), update(), least_height(), px() (+22 more)

### Community 18 - "Dye-Alone Calibration Assay"
Cohesion: 0.03
Nodes (32): DyeAloneAssay, linear_signal(), bounds_from_dye_alone(), fit_linear_assay(), fit_measurement_set(), assert_within_tolerance(), _dba_assay(), dba_clean_result() (+24 more)

### Community 19 - "Diagnostics Serialization"
Cohesion: 0.03
Nodes (65): FitDiagnostics, InputShift, MisfitTest, Verdict, test_a_conflict_lists_as_its_correction_only_the_inputs_it_judged(), test_moved_inputs_give_input_aware_beside_inputs_as_entered_with_one_power_of_ten(), test_moved_inputs_the_test_did_not_reject_quote_the_test_not_a_bound(), test_moved_inputs_whose_test_could_not_run_say_they_were_not_tested_and_why() (+57 more)

### Community 20 - "Input-Aware Verdict Tests"
Cohesion: 0.03
Nodes (51): test_the_readout_reads_the_profile_between_the_drawn_points(), aware(), test_every_drawn_point_is_judged_as_the_interval_judges_it(), test_a_split_interval_draws_its_stretches_under_a_cut_off_that_steps(), test_every_given_replicate_has_its_own_fit_measured_against_itself(), test_with_inputs_moves_exactly_the_named_inputs(), test_with_inputs_refuses_what_is_not_an_input_and_what_the_assay_cannot_hold(), test_signal_unit_has_its_own_dimension() (+43 more)

### Community 21 - "Menu Rendering"
Cohesion: 0.03
Nodes (20): diamond(), _focus_ring(), _menu_command(), menu_html(), _menu_separator(), MenuColumns, MenuRow, paint_popover() (+12 more)

### Community 22 - "Noise Law Model"
Cohesion: 0.03
Nodes (48): _flatness(), noise_law(), NoiseBasis, NoiseLaw, _read_share(), objective(), replicate_scatter(), _scatter() (+40 more)

### Community 23 - "Fit Results Serialization"
Cohesion: 0.03
Nodes (15): ConditionalFit, _config_to_dict(), _interval(), _replica(), _sample_fit_result(), _stepwise_result(), test_the_diagnostics_and_the_tests_they_could_not_run_are_written_as_strict_json_and_read_back(), TestOffsetsHeldAtZero (+7 more)

### Community 24 - "Reference Screen Rendering"
Cohesion: 0.04
Nodes (17): _again_on_display(), main(), _pointer(), render_all(), render_screen(), Screen, theme(), _Boundary (+9 more)

### Community 25 - "Binding Condition Entry"
Cohesion: 0.03
Nodes (35): Amount, _bound_text(), ConditionEntry, _entry(), _write(), _alike(), conflict_note(), _conflict_text() (+27 more)

### Community 26 - "Main Window Screenshots"
Cohesion: 0.03
Nodes (21): _more_sessions(), _overlay_data(), _settings_at_end(), _action(), FittingMainWindow, released(), UpdateCheckWorker, session() (+13 more)

### Community 27 - "Plot Appearance Settings"
Cohesion: 0.03
Nodes (47): appearance(), PaintedNote, PlotAppearance, test_choosing_a_model_in_its_menu_reaches_the_session(), assert_card_fits(), test_before_any_fit_the_view_says_what_to_do_with_the_platform_s_shortcut(), test_before_any_fit_the_view_says_what_to_do_with_the_platform_s_shortcut(), test_the_appearance_resolves_the_one_theme_every_window_holds() (+39 more)

### Community 28 - "Uncertainty Input Entry"
Cohesion: 0.04
Nodes (9): parse_number(), AdditionsEntry, _count(), InputEntry, _kind_name(), SourceEntry, UncertaintyForm, test_an_assay_with_no_association_constant_states_nothing_and_says_why() (+1 more)

### Community 29 - "Session Model State"
Cohesion: 0.04
Nodes (12): projectable(), _count(), EmptyView, SessionModel, _shortcut(), Overlay, test_no_signal_reaches_an_edit_that_takes_no_argument_directly(), make_model() (+4 more)

### Community 30 - "Replicate Metric Formatting"
Cohesion: 0.03
Nodes (38): rejections(), and_join(), describe_replicates(), _display_label(), fmt_estimate(), fmt_r2(), fmt_rmse(), accepted_stretches() (+30 more)

### Community 31 - "Validation Table Tests"
Cohesion: 0.04
Nodes (40): rows(), test_a_check_reads_only_the_cases_it_names(), test_a_family_is_pooled_over_the_seeds_every_one_of_its_cases_reached(), test_a_family_one_of_whose_cases_has_no_rows_is_not_published_as_the_family_s_rate(), test_a_filter_prints_the_matching_cases_and_says_that_it_did(), test_a_filter_that_matches_nothing_reads_no_rows_at_all(), test_a_filtered_check_that_reads_its_parent_whole_says_so_rather_than_naming_no_cases(), test_a_gap_in_a_case_s_seeds_ends_the_prefix_the_family_is_pooled_over() (+32 more)

### Community 32 - "Plot Appearance Preferences"
Cohesion: 0.04
Nodes (49): plot_appearance_default(), set_plot_appearance_default(), export_results(), Change, test_a_vector_keeps_its_own_unit_and_one_outside_the_list_is_converted_to_molar(), test_a_vector_with_a_negative_value_is_refused_whole(), test_a_duplicate_session_takes_the_appearance_of_the_one_it_copies(), test_a_new_session_starts_from_the_stored_appearance_and_else_from_the_built_in_one() (+41 more)

### Community 33 - "Sensitivity Analysis Form"
Cohesion: 0.03
Nodes (39): AnalysisForm, _heatmap(), _plain(), test_a_fixed_seed_must_be_a_whole_number_the_analysis_accepts(), test_a_heatmap_axis_reaching_zero_at_its_span_blocks_the_run_naming_it_and_the_span(), test_a_new_run_going_is_said_only_where_run_state_shows(), test_a_seed_that_is_no_whole_number_in_range_is_refused_not_raised(), test_a_shared_source_and_the_additions_are_ranked_beside_the_inputs() (+31 more)

### Community 34 - "Simulation View Settings"
Cohesion: 0.04
Nodes (11): SimulationForm, SimulationProblem, test_a_single_replicate_or_a_lawless_overlay_is_refused_in_plain_words(), test_a_stated_stock_dilutes_the_totals_the_stock_lacks_through_the_fitters_forward_model(), test_choosing_dilution_offers_a_stock_ten_times_the_highest_titrant_concentration_of_the_grid(), test_every_model_opens_on_a_curve_with_every_species_coloured(), test_fit_in_new_session_carries_the_data_as_shown_and_only_the_conditions(), test_reading_the_noise_takes_the_fitters_noise_law_in_the_fields_units() (+3 more)

### Community 35 - "Heatmap and Chart Views"
Cohesion: 0.04
Nodes (13): _clear(), HeatmapFigure, IndexChartView, IndexLegend, paint_index_bar(), paint_whisker(), SampleHistogram, x_of() (+5 more)

### Community 36 - "Session Lifecycle Tests"
Cohesion: 0.05
Nodes (47): fake_run(), state_dilution(), _deliver_sensitivity(), _load(), _session(), _settle(), _start(), _state_an_uncertainty() (+39 more)

### Community 37 - "Validation Coverage Checks"
Cohesion: 0.04
Nodes (42): test_the_misfit_rate_is_named_by_the_test_that_ran(), test_a_verdict_that_blames_the_model_the_inputs_or_both_is_a_false_alarm_on_good_data(), test_the_replicate_metrics_count_a_fit_that_lost_a_clean_replicate_once(), test_the_reported_coverage_is_read_by_the_largest_entry_error_and_never_judged(), addition_coverage(), addition_misfit(), addition_misstated(), agreement() (+34 more)

### Community 38 - "Diagnostics Text Formatting"
Cohesion: 0.04
Nodes (36): _inputs_tested(), fmt_against(), fmt_concentration(), fmt_p(), fmt_percent(), fmt_test_p(), not_run_reason(), region_sentence() (+28 more)

### Community 39 - "Ka Profile Intervals"
Cohesion: 0.04
Nodes (49): ProfileResult, ProfileSet, KaInterval, PaintedText, _bump_profile(), stepped(), test_a_constant_its_bounds_fix_has_no_profile_plot(), test_an_estimate_on_its_search_bound_reads_not_limited_below_and_no_percentage_of_it() (+41 more)

### Community 40 - "Interval and Unit Formatting"
Cohesion: 0.04
Nodes (25): _canonical_unit(), fmt_bound_estimate(), fmt_interval_html(), fmt_interval_plain(), fmt_log10(), fmt_unit_html(), fmt_unit_pretty(), _interval_text() (+17 more)

### Community 41 - "Profile Path Geometry"
Cohesion: 0.05
Nodes (19): density(), _on_one_path(), _one_step_p(), _Point, _Problem, held(), held(), stacked() (+11 more)

### Community 42 - "Fitting Session Exports"
Cohesion: 0.04
Nodes (21): FittingSession, make_session(), build(), qapp(), boundary(), _broken(), _Emitter, _export_batch() (+13 more)

### Community 43 - "Hidden Fits Tests"
Cohesion: 0.06
Nodes (43): _assert_back(), _assert_hidden(), _curves(), _deliver(), _deliver_sensitivity(), _diluted_session(), _numbers(), _shown_session() (+35 more)

### Community 44 - "Addition Error Inflation"
Cohesion: 0.06
Nodes (35): _replicate_additions(), addition_signal_loading(), _basis(), _factors(), inflation(), joint_inflation(), _linearised(), replicate_scatter_ssr() (+27 more)

### Community 45 - "Fit Results View Tests"
Cohesion: 0.04
Nodes (39): _laid_out_width(), _on_bound(), _over_white(), session(), _shared_source(), _show(), _shown_fits(), _shown_text() (+31 more)

### Community 46 - "Validation Store Tests"
Cohesion: 0.05
Nodes (32): test_a_change_in_how_a_row_is_generated_or_scored_retires_the_rows(), test_a_field_named_as_ignored_does_not_decide_the_exit_status(), test_a_field_one_run_writes_and_the_other_does_not_is_a_difference(), test_a_field_that_moved_is_named_with_its_case_and_seed(), test_a_half_written_line_costs_its_own_row_and_no_other(), test_a_key_only_one_run_holds_is_not_compared(), test_a_quantity_neither_run_could_produce_is_not_a_difference(), test_a_resumed_run_computes_only_the_missing_rows() (+24 more)

### Community 47 - "Settings Window"
Cohesion: 0.05
Nodes (29): _note(), plot_appearance_note(), _row(), SettingsWindow, worker_label(), appearance_mode(), check_for_updates(), _choice() (+21 more)

### Community 48 - "Measurement File Readers"
Cohesion: 0.06
Nodes (11): MeasurementReader, ResultWriter, save_results(), get_reader(), get_writer(), register_reader(), register_writer(), bundled() (+3 more)

### Community 49 - "Shared Addition Errors"
Cohesion: 0.04
Nodes (33): addition_loading(), AdditionError, perturb_titrant(), _require_rising(), SharedSource, test_the_additions_are_one_item_with_the_first_order_variance(), test_duplicate_opens_a_session_stating_everything_the_original_states_and_holding_no_results(), test_a_heatmap_axis_that_is_fixed_used_twice_or_shared_only_blocks_the_run_naming_the_input() (+25 more)

### Community 50 - "Sobol Sensitivity Indices"
Cohesion: 0.04
Nodes (35): _block_order(), _check_design_size(), _count_on_bound(), _reported_sources(), sobol_design(), sobol_indices_from_outputs(), sobol_indices_with_ci(), estimate_of() (+27 more)

### Community 51 - "Test Assay Fixtures"
Cohesion: 0.04
Nodes (28): dba_clean(), dba_noisy(), dye_alone_clean(), gda_clean(), gda_noisy(), h2g_clean(), hg2_clean(), ida_clean() (+20 more)

### Community 52 - "Dataset Loading"
Cohesion: 0.05
Nodes (26): Dataset, _format_of(), _from_file(), _make_ms(), _slice_channel(), SourceFile, _unit_token(), _unreadable() (+18 more)

### Community 53 - "Demo IDA Integration Tests"
Cohesion: 0.08
Nodes (37): test_export_several_offers_no_folder_of_the_bundled_examples(), test_the_outlier_removal_the_demo_applied_shows_in_measurement_settings(), test_no_tick_label_of_the_empty_titration_is_cut_at_an_edge(), test_every_link_to_the_help_raises_the_one_window_at_its_section(), test_every_painted_component_of_the_loaded_demo_is_given_the_room_its_content_needs(), test_the_loaded_demo_at_the_narrowest_window_cuts_no_text_and_gives_every_component_its_room(), _ancestors(), _assert_revealed() (+29 more)

### Community 54 - "Budget Validation Tests"
Cohesion: 0.05
Nodes (27): _exact_row(), test_a_row_whose_fits_stayed_inside_the_ka_box_is_the_one_the_quadrature_judges(), test_a_row_with_a_fit_on_a_ka_bound_says_nothing_about_the_source_variance(), test_a_small_shared_source_is_its_own_percent_in_decades(), test_every_exact_case_carries_the_source_its_claim_is_about(), test_every_what_if_case_asks_for_an_improvement_of_a_source_it_states(), test_the_budget_row_estimates_the_quantities_it_labels(), test_the_budget_row_names_every_quantity_the_application_prints() (+19 more)

### Community 55 - "Assay Forward Model"
Cohesion: 0.05
Nodes (17): DBAAssay, H2GAssay, X(), TestDBAQuantityConditions, test_dba_projection_residual_is_the_model_residual_with_dilution(), TestDBAFailFast, _free_fixed_exactly(), _sig() (+9 more)

### Community 56 - "Session Edits and Runs"
Cohesion: 0.06
Nodes (5): _edit(), edit(), _format_remaining(), retire(), view()

### Community 57 - "Confidence View"
Cohesion: 0.06
Nodes (8): _clear(), ConfidenceView, gap(), gap(), _legend(), ProfileFigure, RegionFigure, test_the_names_on_a_profile_s_strip_stand_whole_clear_of_their_bars_and_on_the_plot_s_axis()

### Community 58 - "Binding Model Help"
Cohesion: 0.06
Nodes (36): _dye_alone_help(), help_html(), assay_class(), _concentration_keys(), _form(), test_a_binding_constant_is_entered_in_inverse_molar(), test_a_bound_set_from_code_is_the_very_number_it_was_written_from(), test_a_condition_that_cannot_be_used_is_named_and_reaches_no_fit_as_a_number() (+28 more)

### Community 59 - "GUI Layout Tests"
Cohesion: 0.06
Nodes (27): qapp(), test_every_painted_component_of_the_fitted_demo_gets_its_room_and_no_plot_header_is_cut(), _wait(), qapp(), test_every_menu_of_the_fitted_demo_fits_its_rows_and_its_window_and_marks_its_choice(), _wait(), _accent_pixels(), check_window() (+19 more)

### Community 60 - "Data Preprocessing Pipeline"
Cohesion: 0.06
Nodes (10): apply_preprocessing(), get_step(), PreprocessingStep, register_step(), ZScoreReplicaFilter, demo(), _ms_few_replicas(), _ms_with_outlier() (+2 more)

### Community 61 - "Validation Run Jobs"
Cohesion: 0.05
Nodes (23): coverage_rows(), jobs(), test_a_case_stops_only_once_every_check_reading_it_has_passed_as_well(), test_a_case_that_fails_at_the_first_stage_goes_on_to_the_next(), test_a_case_whose_rate_has_passed_stops_where_it_is(), test_a_job_that_dies_is_stored_as_an_error_under_its_own_key(), test_a_one_step_null_case_can_fail_alone_and_pass_only_in_its_pooled_row(), test_a_pool_that_never_finishes_a_row_ends_the_run_rather_than_looping() (+15 more)

### Community 62 - "Binding Form"
Cohesion: 0.05
Nodes (3): BindingForm, dye_alone_keys(), test_every_field_shows_a_number_one_way_and_reads_back_both_ways_a_number_is_written()

### Community 63 - "Equilibrium Forward Models"
Cohesion: 0.06
Nodes (15): _all_valid(), _competitive_free_host(), competitive_signal_point(), _competitive_speciation(), _competitive_species_grid(), dba_signal(), gda_signal(), h2g_signal() (+7 more)

### Community 64 - "Conflict Verdict Tests"
Cohesion: 0.09
Nodes (9): Conflict, verdict_sentence(), _diagnostics(), _f_test(), _runs(), _shift(), TestFmtMisfit, TestVerdictHeadline (+1 more)

### Community 65 - "Dilution Speciation Tests"
Cohesion: 0.07
Nodes (37): ida_species(), _dba(), _diluted(), _dye_alone(), _gda(), _h2g(), _hg2(), _ida() (+29 more)

### Community 66 - "Results Import Checks"
Cohesion: 0.05
Nodes (7): _problem_list(), Refusal, readout_value(), species_groups(), qapp(), test_the_help_examples_are_the_numbers_demo_ida_shows(), test_before_an_analysis_sensitivity_names_only_the_steps_still_to_take()

### Community 67 - "Example Data and Design Docs"
Cohesion: 0.04
Nodes (49): DBA host-to-dye titration data (8 replicates), Dye-alone calibration data (4 replicates), GDA titration data (3 replicates), IDA titration data (8 replicates), Example data metadata, DBA host-to-dye reference parameters, GDA reference parameters (CB7, nButanol, TNS dye), IDA reference parameters (+41 more)

### Community 68 - "GDA Assay Tests"
Cohesion: 0.07
Nodes (7): GDAAssay, TestGDAQuantityConditions, TestBaseAssayContracts, TestGDAFailFast, TestIDAFailFast, test_a_signal_parameter_the_fit_ended_on_an_entered_bound_is_named_with_that_bound(), TestTheParametersTheLackOfFitTestCounts

### Community 70 - "Design System Contrast Tests"
Cohesion: 0.07
Nodes (25): _close(), contrast(), _controls(), delta_e2000(), _ink(), _lab(), literals(), _luminance() (+17 more)

### Community 71 - "Ensight Reader"
Cohesion: 0.07
Nodes (6): EnsightReader, _minimal_ensight(), _read_legacy_var_signal(), TestDispatch, TestParsing, TestSniffing

### Community 72 - "Binding View Tests"
Cohesion: 0.06
Nodes (24): _magnitude(), state_binding(), session(), _tab_order(), test_a_condition_that_cannot_be_read_shows_no_number_under_input_uncertainty(), test_a_dye_alone_file_sets_the_signal_bounds_to_what_it_measured(), test_a_dye_alone_file_the_data_checks_refuse_is_named_with_the_refusal_itself(), test_a_stock_typed_in_its_field_reaches_the_fit_in_the_unit_shown() (+16 more)

### Community 73 - "Equilibrium Precision Tests"
Cohesion: 0.09
Nodes (24): competitive_species_point(), dba_species(), _positive_root(), _assert_close(), _brackets_root(), _certify_free(), _check_competitive(), _check_stepwise() (+16 more)

### Community 74 - "Dilution Recovery Tests"
Cohesion: 0.07
Nodes (16): fit_assay(), _assay(), _binary_free_host(), _competitive_free_host(), balance(), _decades_off(), _dye_signal(), _generate() (+8 more)

### Community 75 - "Titration Simulation"
Cohesion: 0.08
Nodes (26): _as_count(), _build_assay(), build_concentration_vector(), simulate_dataset(), simulate_signal(), simulate_species(), two_part_sd(), _dba_case() (+18 more)

### Community 76 - "Validation Statistics Tests"
Cohesion: 0.07
Nodes (19): _count_thresholds(), _ladder_by_paths(), test_a_case_that_is_exactly_nominal_is_failed_about_one_time_in_fifty(), test_a_coverage_rate_fails_only_when_the_draws_put_it_below_the_level(), test_a_coverage_rate_the_data_put_above_bradley_s_far_end_is_a_pass_called_conservative(), test_a_ladder_of_one_stage_is_one_look(), test_a_lower_limit_claim_is_the_same_rule_the_other_way_round(), test_a_test_at_the_5_per_cent_level_fails_only_when_it_rejects_too_often() (+11 more)

### Community 77 - "Jasco Reader"
Cohesion: 0.08
Nodes (5): JascoReader, _minimal_jasco(), TestDispatch, TestParsing, TestSniffing

### Community 78 - "Per-Replicate Fitting"
Cohesion: 0.10
Nodes (11): fit_measurement_set_per_replica(), _record_data(), clean_pr_result(), _config(), _ida_conditions(), _ida_ms(), noisy_pr_result(), _replaced() (+3 more)

### Community 80 - "BMG Workbook Parser"
Cohesion: 0.07
Nodes (12): _extract_metadata(), _find_bmg_sheet(), _find_header_row(), is_bmg_workbook(), parse_bmg_workbook(), XlsxReader, TestBMGDetection, TestBMGParse (+4 more)

### Community 81 - "Simulation View"
Cohesion: 0.11
Nodes (4): _caption(), _column(), SimulationView, _widget()

### Community 82 - "Export Multiple Dialog"
Cohesion: 0.08
Nodes (12): ExportMultipleDialog, _row(), ExportableArtefact, _data(), test_export_prefix_is_reused_only_for_the_same_dataset(), dialog(), _raise(), test_a_folder_that_cannot_be_made_is_said_in_plain_words() (+4 more)

### Community 83 - "Status Message Tests"
Cohesion: 0.07
Nodes (24): status_messages(), _data(), _import(), _shown(), test_a_dilution_difference_without_data_reads_as_a_sentence(), test_a_finished_fit_names_the_replicates_it_left_out_and_why(), test_a_fit_finishing_after_a_used_replicate_was_switched_off_is_held_hidden_and_profiled_on_its_record(), test_import_keeps_the_replicate_selection_and_hides_a_fit_it_does_not_match() (+16 more)

### Community 84 - "Ka Display Helpers"
Cohesion: 0.09
Nodes (25): _ka_text(), second(), _axis(), _column_rank(), _on_box(), reference_intervals(), bound_closes(), bounded() (+17 more)

### Community 86 - "Input Uncertainty View"
Cohesion: 0.09
Nodes (3): _InputRow, _SourceRow, UncertaintyView

### Community 87 - "Legacy Results Loading"
Cohesion: 0.06
Nodes (8): _common_fields(), unexpected(), FitWorker, ProfileWorker, _release(), test_a_worker_failure_names_the_step_and_the_log(), test_a_fit_the_pipeline_refuses_is_reported_in_its_own_words(), raising()

### Community 88 - "Build and Release Workflow"
Cohesion: 0.06
Nodes (35): runs-on, steps, strategy, jobs, build, publish_release, os, name (+27 more)

### Community 89 - "Plot Navigation"
Cohesion: 0.14
Nodes (20): TitrationData, _data(), _range(), _shown(), test_a_double_click_resets_the_view(), test_a_pinch_zooms(), test_a_plain_wheel_over_the_plot_scrolls_the_page_that_holds_it(), test_a_theme_change_keeps_the_zoom() (+12 more)

### Community 90 - "Fit Cancellation Tests"
Cohesion: 0.09
Nodes (21): FitCancelled, slow_fit(), fake(), watchful_fit(), _data(), fitted(), _holding(), _state() (+13 more)

### Community 91 - "Binding View"
Cohesion: 0.10
Nodes (6): BindingView, _BoundRow, _caption(), _clear(), _ConditionRow, _name()

### Community 92 - "Plot Design Docs"
Cohesion: 0.06
Nodes (30): figure_head(), Input-aware interval, Inputs as entered interval, Two-part noise law var(y)=floor²+(proportional·y)², PlotHeader, PlotNavigation, Plots design (§7), Saved figure (+22 more)

### Community 93 - "Graph CI Workflow"
Cohesion: 0.06
Nodes (33): concurrency, group, ANTHROPIC_API_KEY, ANTHROPIC_MODEL, PYTHONHASHSEED, default, description, type (+25 more)

### Community 94 - "Confidence View Tests"
Cohesion: 0.09
Nodes (23): _conflicted(), _crossings(), _pixel(), test_a_drop_close_to_minus_100_percent_is_not_rounded_to_it(), test_a_fit_of_exact_inputs_has_the_one_reading_as_entered(), test_a_ka_its_bounds_fix_is_said_to_be_fixed_and_quotes_no_interval(), test_a_result_that_records_no_interval_says_so_as_fit_results_does(), test_a_split_interval_names_the_ka_it_rejects_between_its_stretches() (+15 more)

### Community 96 - "Design Style Icons"
Cohesion: 0.08
Nodes (12): DesignStyle, icon(), pixmap(), svg(), _contrast(), fusion(), _luminance(), restore_mode() (+4 more)

### Community 97 - "Uncertainty View Tests"
Cohesion: 0.10
Nodes (19): _aware_fit(), _show(), _shown(), _split_fit(), test_a_closed_end_far_below_the_others_never_reads_zero(), test_a_constant_with_no_interval_is_named_beside_the_one_drawn(), test_a_fit_whose_association_constant_records_no_interval_says_so(), test_a_fit_with_no_association_constant_says_it_has_no_interval() (+11 more)

### Community 98 - "Layout Rules Checks"
Cohesion: 0.11
Nodes (13): axis_text_problems(), check(), clashing_names(), cut_axis_text(), cut_headers(), cut_labels(), cut_sideways(), interactive() (+5 more)

### Community 100 - "Plot Data Preparation Tests"
Cohesion: 0.14
Nodes (8): prepare_plot_data(), _noisy_ms(), _per_replicate_record(), _simple_fit_result(), _simple_ms(), TestMeanFollowsTheFittedReplicates, TestPrepPlotDataFits, TestPrepPlotDataReplicas

### Community 101 - "Tab-Separated File IO"
Cohesion: 0.10
Nodes (4): _as_float(), TxtReader, TxtWriter, TestTxtReader

### Community 102 - "Summary Statistics Helpers"
Cohesion: 0.10
Nodes (5): describe(), describe_log10(), linear_regression(), TestDescribe, TestLinearRegression

### Community 103 - "Checkbox and Dropdown Widgets"
Cohesion: 0.08
Nodes (4): Checkbox, Dropdown, _rich_document(), rich_width()

### Community 104 - "Render Harness Tests"
Cohesion: 0.09
Nodes (15): qapp(), test_the_fitted_state_is_drawn_after_the_fit_and_its_profile(), noting_snapshot(), test_the_heatmap_state_reads_the_cell_under_the_pointer(), _cue(), _fitted(), _same(), session() (+7 more)

### Community 105 - "Empty State Views Tests"
Cohesion: 0.11
Nodes (17): _button(), _offered_folders(), _on_screen(), test_a_save_offers_the_folder_of_the_data_it_was_made_from(), test_every_empty_view_offers_load_data_and_the_demo_and_draws_no_bare_axes(), test_no_save_after_the_demo_offers_a_folder_inside_the_app(), test_no_view_says_there_is_no_analysis_while_it_runs(), test_no_view_says_there_is_no_fit_while_the_fit_runs() (+9 more)

### Community 106 - "GUI Test Helpers"
Cohesion: 0.11
Nodes (14): _open_menu(), _open_window(), _point_at(), render(), _settle(), _snapshot(), _wait(), test_a_pointer_with_no_plot_on_screen_is_refused() (+6 more)

### Community 107 - "Concentration Vector IO"
Cohesion: 0.11
Nodes (5): extract_concentrations_from_file(), read_raw_concentrations(), save_concentration_vector(), TestConcentrationRoundTrip, TestExtractConcentrations

### Community 108 - "Multi-File Replica Loading"
Cohesion: 0.11
Nodes (13): load_measurements_multi(), _jasco(), test_channel_file_rejected(), test_duplicate_stems_disambiguated(), test_empty_paths_raises(), test_heterogeneous_declared_units_converted_before_stack(), test_mismatched_grid_rejected(), test_mismatched_point_counts_rejected() (+5 more)

### Community 109 - "Help Window Tests"
Cohesion: 0.08
Nodes (13): help_off_screen(), _plain(), test_each_settings_side_panel_is_explained_in_its_section(), test_every_section_uses_one_heading_convention(), test_every_section_with_a_demo_plot_ends_on_its_demo_ida_example(), test_no_help_opens_as_a_modal_dialog_with_its_own_buttons(), test_the_binding_model_section_follows_the_model_chosen(), test_the_help_menu_raises_the_same_window_at_the_view_on_screen() (+5 more)

### Community 110 - "1:2 Host-Guest Speciation"
Cohesion: 0.10
Nodes (9): h2g_species(), hg2_species(), test_hg2_and_h2g_speciation_is_exact_to_rounding_in_every_regime(), TestH2GMassBalance, TestHG2MassBalance, equations(), TestSolverRobustness, solve() (+1 more)

### Community 111 - "Plot Appearance View"
Cohesion: 0.13
Nodes (4): menu(), PlotAppearanceView, body(), _widget()

### Community 112 - "Slider Knob Values"
Cohesion: 0.14
Nodes (4): Knob, _three_figures(), unit_text(), _KnobRow

### Community 113 - "Sensitivity Background Worker"
Cohesion: 0.10
Nodes (7): SensitivityRunError, SensitivityWorker, test_worker_delivers_a_held_back_count_as_soon_as_a_cancel_is_seen(), run(), test_worker_reports_an_unexpected_failure_in_plain_words(), written(), test_worker_throttles_progress_but_never_drops_the_last_count()

### Community 114 - "Profile Plot Readout"
Cohesion: 0.09
Nodes (12): ProfilePlot, readout(), ReadoutRow, fmt_value(), number(), fmt(), Marker, _reading_marker() (+4 more)

### Community 116 - "Fit Result Reproduction Checks"
Cohesion: 0.12
Nodes (8): _finite_or_none(), fit_view(), _reproduces(), _unmarked_slack(), TestFitViewAtMovedInputs, signal(), result_off_by(), solve()

### Community 117 - "Profile Interval Cutting"
Cohesion: 0.09
Nodes (12): _cut_interval(), _interval(), edge(), _read_steps(), halve(), _scan_turns(), scan(), test_a_gap_in_the_accepted_ka_values_is_reported_as_a_split_interval() (+4 more)

### Community 118 - "Update Check Lifecycle Tests"
Cohesion: 0.12
Nodes (10): checks(), dialogs(), _ScriptedCheck, _settle(), _SlowToEnd, test_a_check_that_reported_is_deleted_only_once_its_thread_has_ended(), test_a_finished_check_lets_go_of_itself_and_not_of_the_check_that_replaced_it(), test_asking_for_a_check_while_one_is_running_says_so() (+2 more)

### Community 119 - "Batch Export and Titration Figure"
Cohesion: 0.11
Nodes (11): export_batch(), _replicates_on_bound(), _two_ka_per_replica(), _fitted(), saved(), session(), _svg_text(), test_a_saved_fit_carries_the_legend_the_curve_and_the_summary() (+3 more)

### Community 120 - "Export Test Fixtures"
Cohesion: 0.13
Nodes (12): baseline_fit(), run(), heatmap_result(), made_on(), sobol_result(), stopped_result(), _artefact(), test_a_budget_with_no_number_in_it_is_refused_rather_than_written_empty() (+4 more)

### Community 121 - "Reference Grid Interval Tests"
Cohesion: 0.11
Nodes (14): test_a_gap_inside_one_search_cell_is_reported_as_the_fixed_input_interval_reports_it(), test_an_accepted_stretch_inside_one_search_cell_extends_the_interval_as_far_as_the_fixed_input_one(), test_an_accepted_stretch_past_a_step_of_the_cut_off_is_inside_the_input_aware_interval_too(), _vanishing(), _grid_projection(), _independent_one_ka(), solve(), verdict() (+6 more)

### Community 122 - "Replicate Outlier Detection"
Cohesion: 0.15
Nodes (14): rows(), _cochran_limit(), replicate_outliers(), q_min(), _replicate_projection(), _replicates(), test_a_replicate_that_needs_another_ka_is_excluded_by_name(), test_a_replicate_three_times_noisier_than_the_others_is_left_out_for_its_scatter() (+6 more)

### Community 123 - "Update Download Worker"
Cohesion: 0.10
Nodes (4): DownloadWorker, _os_label(), _pick_asset(), UpdateAvailableDialog

### Community 124 - "Concentration Validation"
Cohesion: 0.12
Nodes (5): concentration_problem(), at(), _molar_text(), _no_measurements(), InvalidData

### Community 125 - "MeasurementSet Writers"
Cohesion: 0.14
Nodes (6): _header_comment(), _iter_points(), write_measurements_csv(), write_measurements_txt(), _write_raw_csv(), TestMeasurementWriters

### Community 126 - "Competitive GDA Speciation"
Cohesion: 0.13
Nodes (5): gda_species(), _assert_same(), test_every_solve_of_a_profiled_titration_returns_a_number(), test_zero_totals_give_the_unbound_state(), TestClosedFormLimits

### Community 127 - "Sobol Sampling Design Tests"
Cohesion: 0.14
Nodes (11): spec_fraction(), _record_designs(), test_a_stopped_sobol_run_keeps_the_sample_blocks_that_finished(), fake_fit(), outputs(), test_relative_sigma_is_one_standard_deviation(), test_run_intervals_leave_out_rows_without_a_fit(), fake_fit() (+3 more)

### Community 128 - "Editable Slider Ends"
Cohesion: 0.15
Nodes (4): drop(), SliderEnd, commit(), SliderEndOutline

### Community 129 - "Run Actions and Failures"
Cohesion: 0.14
Nodes (8): test_a_failed_run_says_why_and_keeps_the_last_result_shown(), test_a_run_counts_its_fits_on_the_status_bar_and_estimates_the_time_left(), test_a_run_uses_the_bounds_and_the_settings_stated(), capture(), test_a_seed_typed_and_run_at_once_is_the_seed_the_run_uses(), test_a_stopping_run_says_so_on_the_status_bar_and_not_its_counts(), test_new_data_discards_a_run_still_going(), _wait_for_worker()

### Community 130 - "Titration Plot Rendering"
Cohesion: 0.14
Nodes (5): TitrationPlot, _many(), test_grey_draws_every_replicate_in_one_colour(), test_twelve_replicates_take_twelve_colours_and_the_next_ones_the_next_shape(), plot()

### Community 133 - "Sensitivity Worker Processes"
Cohesion: 0.17
Nodes (6): _evaluate(), test_a_batch_over_worker_processes_leaves_this_process_uncapped(), test_a_job_that_fails_outright_stops_the_batch_at_once_in_plain_words(), test_a_stop_is_answered_while_the_pool_is_still_starting(), test_a_stopped_batch_drops_the_fits_it_had_queued(), _thread_limits()

### Community 135 - "Help Window Dialog"
Cohesion: 0.16
Nodes (3): HelpWindow, _topic_style(), section_html()

### Community 136 - "Release Version Checking"
Cohesion: 0.18
Nodes (4): is_newer(), newest_release(), test_a_beta_build_is_offered_the_newest_published_release_beta_or_stable(), TestIsNewer

### Community 137 - "Reference Screens and Legacy"
Cohesion: 0.18
Nodes (4): test_the_command_renders_every_reference_screen_in_both_themes(), archive(), previous_release(), row()

### Community 139 - "Documentation Currency Tests"
Cohesion: 0.14
Nodes (6): _live_texts(), test_no_live_text_names_machinery_the_app_does_not_have(), test_the_architecture_table_names_every_pipeline_module(), test_the_documents_name_the_fit_the_app_performs(), test_the_scan_reaches_the_texts_a_reader_and_the_program_depend_on(), test_the_validation_readme_lists_every_check_with_its_claim_and_criterion()

### Community 140 - "Input-Aware Documentation Tests"
Cohesion: 0.14
Nodes (6): test_the_binding_model_help_points_at_the_view_the_uncertainties_are_entered_in(), test_the_instructions_list_every_module_of_the_fitting_pipeline(), test_the_readme_explains_every_basis_a_noise_law_can_report(), test_the_readme_explains_every_verdict_a_fit_can_report(), test_the_validation_readme_names_every_check_the_package_runs(), test_the_validation_readme_quotes_each_check_s_own_claim()

### Community 141 - "Second Step Sentence Formatting"
Cohesion: 0.18
Nodes (4): _at_most(), _one_figure(), one_step_sentence(), TestOneStepSentence

### Community 143 - "Export Artefact Builders"
Cohesion: 0.15
Nodes (7): build_artefacts(), _write_raw_txt(), _write_results_csv(), _write_results_json(), _write_results_txt(), test_the_batch_export_writes_the_titration_of_fit_results(), test_save_plot_follows_the_ka_confidence_plot_not_the_held_fit()

### Community 144 - "Model Notification Consistency"
Cohesion: 0.19
Nodes (6): _holding(), _inconsistencies(), _signals(), test_an_edit_is_said_once(), test_every_notification_finds_the_model_consistent(), test_no_view_raises_and_each_draws_once()

### Community 146 - "Profile Curve Deviance"
Cohesion: 0.21
Nodes (5): curve(), Curve, deviance(), _log_extent(), _read()

### Community 149 - "Fit Cancellation and Bounds"
Cohesion: 0.21
Nodes (4): _gda_assay(), TestCancellation, should_cancel(), TestResolveBounds

### Community 151 - "Input Shift Formatting"
Cohesion: 0.24
Nodes (3): _escape(), fmt_shift(), TestFmtShift

### Community 152 - "Analysis Dialog Tests"
Cohesion: 0.20
Nodes (7): dialogs(), record(), test_the_analysis_varies_the_inputs_the_shared_panel_states(), record(), run(), watchful_sensitivity(), run()

### Community 153 - "Reader Registry Test Stubs"
Cohesion: 0.25
Nodes (3): _Accepter, _Fallback, _Rejecter

### Community 156 - "Isolated Test Fixtures"
Cohesion: 0.20
Nodes (4): store(), results(), code_copy(), results()

### Community 157 - "Interval Coverage Metrics"
Cohesion: 0.20
Nodes (5): facts(), test_a_closed_interval_that_misses_the_truth_is_counted_over_every_fit(), test_a_closed_lower_edge_of_the_second_constant_above_the_truth_is_counted_whatever_the_upper_side_does(), test_the_coverage_of_a_weighted_fit_is_split_by_how_far_its_weights_spread(), test_the_one_step_null_judges_a_second_constant_closed_below()

### Community 160 - "View Side Panels"
Cohesion: 0.28
Nodes (3): side(), _SidePanel, _View

### Community 161 - "Plot Axis Text Sizes"
Cohesion: 0.25
Nodes (4): _axes(), _drawn_text(), test_each_axis_text_size_is_one_even_step_up_at_one_weight(), test_the_x_axis_title_of_a_saved_figure_is_whole_at_every_size()

### Community 163 - "Validation Package"
Cohesion: 0.22
Nodes (9): addition-* checks, before-after check, validation.criteria (operating_characteristic, ladder_operating_characteristic), fit_measurement_set, Seed ladder 100→200→400, MeasurementSet, core.pipeline.inputs.perturb_titrant, Result store (validation/results/<check>.jsonl) (+1 more)

### Community 167 - "Profile Likelihood References"
Cohesion: 0.29
Nodes (7): Bates & Watts 1988 Nonlinear Regression, F-test profile likelihood interval, Hodges & Sargent 2001 effective degrees of freedom, Input-aware penalised profile interval, Raue et al. 2009 profile-likelihood identifiability, Replicates averaged, not pooled, Signal coefficient degeneracy

### Community 180 - "Weighted Interval Metrics"
Cohesion: 0.33
Nodes (3): facts(), test_a_weighted_fit_reports_the_law_it_was_weighted_by(), test_the_reported_interval_is_judged_and_its_cost_reported_beside_it()

### Community 181 - "Bound Resting Tests"
Cohesion: 0.33
Nodes (3): _decades_apart(), test_a_coefficient_the_minimum_holds_on_its_bound_is_not_counted_in_either_computation(), test_a_constant_whose_objective_falls_to_its_bound_rests_on_it_in_both_computations()

### Community 186 - "Sensitivity and Dilution References"
Cohesion: 0.50
Nodes (4): Dilution of fixed totals, Scaling identity of binding models, Sobol' 2001 global sensitivity indices, Sobol' variance decomposition

### Community 193 - "Robustness Criteria References"
Cohesion: 0.50
Nodes (4): Bradley 1978, Robustness?, Bradley's liberal criterion of robustness, one-step-null check, Clopper-Pearson exact limits

### Community 194 - "Replicate Outlier References"
Cohesion: 0.67
Nodes (3): Cochran 1941 largest variance test, Hadi & Simonoff 1993 multiple outliers, Replicate test (forward search + Cochran)

### Community 195 - "Fit Verdict Statistics"
Cohesion: 0.67
Nodes (3): Input conflict statistic, Lack-of-fit F test and runs test, Fit verdict (Holm procedure)

### Community 198 - "Penalised Interval Widening"
Cohesion: 1.00
Nodes (3): test_a_source_common_to_every_concentration_widens_the_interval_by_its_own_sigma(), edge(), penalised()

### Community 199 - "Residual Solve Helpers"
Cohesion: 0.67
Nodes (3): top(), residual(), solve()

## Ambiguous Edges - Review These
- `GDA reference parameters (CB7, nButanol, TNS dye)` → `Dye-alone calibration data (4 replicates)`  [AMBIGUOUS]
  data/Readme.md · relation: conceptually_related_to
- `Variable projection fit` → `Fitting workflow flowchart: load data, initial guess, multi-start optimization, RMSE/R² filtering, aggregate good fits, replicas loop, save results`  [AMBIGUOUS]
  docs/fitting_workflow.jpg · relation: conceptually_related_to

## Knowledge Gaps
- **59 isolated node(s):** `uv`, `fitting-app`, `Andrews & Cheng 2012 weak identification`, `Bates & Watts 1988 Nonlinear Regression`, `Cochran 1941 largest variance test` (+54 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 3932 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **85 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `AssayType` connect `Assay Types and Residuals` to `Assay Base Classes`, `Sensitivity Run Configuration`, `Fit Configuration and Bounds`, `Uncertainty Budget Elasticities`, `Help Window Dialog`, `Input-Aware Weighted Fitting`, `Fit Result Container`, `Sensitivity Result Display`, `Variable Projection Fitting`, `Input Uncertainty Specs`, `Measurement Set Replicas`, `Session Settings`, `Fit Metrics and Fingerprints`, `Export Artefact Builders`, `Dye-Alone Calibration Assay`, `Diagnostics Serialization`, `Input-Aware Verdict Tests`, `Binding Model Form`, `Fit Results Serialization`, `Reference Screen Rendering`, `Binding Condition Entry`, `Main Window Screenshots`, `Plot Appearance Settings`, `Uncertainty Input Entry`, `Session Model State`, `Replicate Metric Formatting`, `Plot Appearance Preferences`, `Simulation View Settings`, `Session Lifecycle Tests`, `Diagnostics Text Formatting`, `File Filters and Help Text`, `Interval and Unit Formatting`, `Fitting Session Exports`, `Hidden Fits Tests`, `Addition Error Inflation`, `Fit Results View Tests`, `Shared Addition Errors`, `Test Assay Fixtures`, `Demo IDA Integration Tests`, `Assay Forward Model`, `Session Edits and Runs`, `Binding Model Help`, `Binding Form`, `Input-Aware Documentation Tests`, `GDA Assay Tests`, `Binding View Tests`, `Status Message Tests`, `Legacy Results Loading`, `Fit Cancellation Tests`, `Uncertainty View Tests`, `Fit Results View`, `Render Harness Tests`, `Help Window Tests`, `Plot Appearance View`, `Batch Export and Titration Figure`, `Export Test Fixtures`, `Replicate Outlier Detection`?**
  _High betweenness centrality (0.064) - this node is a cross-community bridge._
- **Are the 200 inferred relationships involving `AssayType` (e.g. with `BaseAssay` and `DBAAssay`) actually correct?**
  _`AssayType` has 200 INFERRED edges - model-reasoned connections that need verification._
- **What connects `uv`, `fitting-app`, `Andrews & Cheng 2012 weak identification` to the rest of the system?**
  _59 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Assay Base Classes` be split into smaller, more focused modules?**
  _Cohesion score 0.021029701311214444 - nodes in this community are weakly interconnected._
- **Why does `SessionModel` connect `Session Model State` to `Sensitivity Run Configuration`, `Fit Result Container`, `Sensitivity Result Display`, `Measurement Set Replicas`, `Assay Types and Residuals`, `Session Settings`, `Plot Theme Styling`, `Reference Screen Rendering`, `Binding Condition Entry`, `Plot Appearance Settings`, `Session File Paths`, `Uncertainty Input Entry`, `Replicate Metric Formatting`, `Plot Appearance Preferences`, `Sensitivity Analysis Form`, `Simulation View Settings`, `Heatmap and Chart Views`, `Simulation Data Loading`, `Ka Profile Intervals`, `Fitting Session Exports`, `Analysis Configuration Checks`, `Dataset Loading`, `Session Edits and Runs`, `Confidence View`, `Binding Form`, `Results Import Checks`, `Session Copy and Cancellation`, `Simulation View`, `Measurements View`, `Input Uncertainty View`, `Legacy Results Loading`, `Fit Cancellation Tests`, `Binding View`, `Uncertainty View Tests`, `Fit Results View`, `Empty State Views Tests`, `Plot Appearance View`, `Sensitivity Background Worker`?**
  _High betweenness centrality (0.052) - this node is a cross-community bridge._

### Low-confidence Hints
_AMBIGUOUS edges — the extractor was unsure. Verify before acting on these._

- **What is the exact relationship between `GDA reference parameters (CB7, nButanol, TNS dye)` and `Dye-alone calibration data (4 replicates)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Variable projection fit` and `Fitting workflow flowchart: load data, initial guess, multi-start optimization, RMSE/R² filtering, aggregate good fits, replicas loop, save results`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._