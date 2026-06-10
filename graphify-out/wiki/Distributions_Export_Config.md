# Distributions Export Config

> 17 nodes · cohesion 0.15

## Key Concepts

- **FitSummaryWidget** (24 connections) — `gui/plotting/fit_summary_widget.py`
- **AssayType** (21 connections) — `gui/fitting_session.py`
- **FitResult** (21 connections) — `gui/fitting_session.py`
- **MeasurementSet** (21 connections) — `gui/fitting_session.py`
- **DistributionsExportConfig** (14 connections) — `gui/dialogs/save_distributions_dialog.py`
- **save_distributions_dialog.py** (9 connections) — `gui/dialogs/save_distributions_dialog.py`
- **test_fit_summary_widget.py** (8 connections) — `tests/unit/gui/test_fit_summary_widget.py`
- **test_unknown_assay_type_does_not_crash()** (3 connections) — `tests/unit/gui/test_fit_summary_widget.py`
- **test_clear_resets_state()** (2 connections) — `tests/unit/gui/test_fit_summary_widget.py`
- **test_update_result_metric_labels_nonempty()** (2 connections) — `tests/unit/gui/test_fit_summary_widget.py`
- **.clear()** (2 connections) — `gui/plotting/fit_summary_widget.py`
- **Dialog for saving the distributions plot as a composite PNG or SVG.  The dialog** (1 connections) — `gui/dialogs/save_distributions_dialog.py`
- **Return value when the dialog is accepted.      ``height_in`` is derived from ``w** (1 connections) — `gui/dialogs/save_distributions_dialog.py`
- **minimal_fit_result()** (1 connections) — `tests/unit/gui/test_fit_summary_widget.py`
- **Widget tests for FitSummaryWidget — requires a QApplication.** (1 connections) — `tests/unit/gui/test_fit_summary_widget.py`
- **Reset all fields to their empty state.** (1 connections) — `gui/plotting/fit_summary_widget.py`
- **Read-only display of ``FitResult`` statistics.      Layout     ------     -** (1 connections) — `gui/plotting/fit_summary_widget.py`

## Relationships

- [[MeasurementSet & FitResult]] (13 shared connections)
- [[Checkbox Grid UI Helpers]] (7 shared connections)
- [[Plot Style Tests]] (7 shared connections)
- [[Fit Config Panel]] (7 shared connections)
- [[Save Distributions Dialog]] (6 shared connections)
- [[BaseAssay Interface]] (6 shared connections)
- [[Distribution Plot Widget]] (5 shared connections)
- [[FittingSession Export]] (5 shared connections)
- [[Assay Base & Registry Metadata]] (5 shared connections)
- [[Export Multiple Dialog]] (4 shared connections)
- [[Preferences & QSettings]] (3 shared connections)
- [[Assay Conditions Registry]] (3 shared connections)

## Source Files

- `gui/dialogs/save_distributions_dialog.py`
- `gui/fitting_session.py`
- `gui/plotting/fit_summary_widget.py`
- `tests/unit/gui/test_fit_summary_widget.py`

## Audit Trail

- EXTRACTED: 56 (42%)
- INFERRED: 77 (58%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*