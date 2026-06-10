# Style Template Persistence

> 19 nodes · cohesion 0.13

## Key Concepts

- **fitting_session.py** (40 connections) — `gui/fitting_session.py`
- **Path** (7 connections) — `gui/session.py`
- **save_style_json()** (7 connections) — `gui/plotting/plot_style.py`
- **export_results_txt()** (6 connections) — `gui/session.py`
- **FitResult** (6 connections) — `gui/session.py`
- **export_results()** (5 connections) — `gui/session.py`
- **import_results()** (5 connections) — `gui/session.py`
- **load_style_json()** (5 connections) — `gui/plotting/plot_style.py`
- **.load_style_template()** (3 connections) — `gui/fitting_session.py`
- **.save_style_template()** (3 connections) — `gui/fitting_session.py`
- **Path** (2 connections) — `gui/plotting/plot_style.py`
- **FittingSession — one complete fitting workspace (one tab).** (1 connections) — `gui/fitting_session.py`
- **Save current plot style settings to a JSON file.** (1 connections) — `gui/fitting_session.py`
- **Load plot style settings from a JSON file.** (1 connections) — `gui/fitting_session.py`
- **Export a list of FitResult objects to a JSON file.      Parameters     ---------** (1 connections) — `gui/session.py`
- **Import fit results from a JSON file created by :func:`export_results`.      Para** (1 connections) — `gui/session.py`
- **Export fit results as a human-readable text report.      Parameters     --------** (1 connections) — `gui/session.py`
- **Save a style dict to a JSON file.      Parameters     ----------     style :** (1 connections) — `gui/plotting/plot_style.py`
- **Load a style dict from a JSON file.      Parameters     ----------     path** (1 connections) — `gui/plotting/plot_style.py`

## Relationships

- [[Batch Artefact Export]] (8 shared connections)
- [[MeasurementSet & FitResult]] (6 shared connections)
- [[FittingSession Export]] (5 shared connections)
- [[Assay Base & Registry Metadata]] (4 shared connections)
- [[BaseAssay Interface]] (3 shared connections)
- [[Checkbox Grid UI Helpers]] (3 shared connections)
- [[Label Formatting]] (3 shared connections)
- [[Measurement Writer]] (2 shared connections)
- [[Distributions Export Config]] (2 shared connections)
- [[Plot Style Tests]] (2 shared connections)
- [[Fit Config Panel]] (2 shared connections)
- [[prepare_plot_data]] (1 shared connections)

## Source Files

- `gui/fitting_session.py`
- `gui/plotting/plot_style.py`
- `gui/session.py`

## Audit Trail

- EXTRACTED: 91 (94%)
- INFERRED: 6 (6%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*