# Parameter Descriptions & Linear Fit

> 27 nodes · cohesion 0.11

## Key Concepts

- **BoundsPanel** (30 connections) — `gui/widgets/bounds_panel.py`
- **bounds_panel.py** (15 connections) — `gui/widgets/bounds_panel.py`
- **_BoundRow** (14 connections) — `gui/widgets/bounds_panel.py`
- **Quantity** (6 connections) — `gui/widgets/bounds_panel.py`
- **AssayType** (5 connections) — `gui/widgets/bounds_panel.py`
- **.apply_dye_alone_bounds()** (5 connections) — `gui/widgets/bounds_panel.py`
- **._on_load_dye_alone()** (5 connections) — `gui/widgets/bounds_panel.py`
- **.current_bounds()** (4 connections) — `gui/widgets/bounds_panel.py`
- **._rebuild_form()** (4 connections) — `gui/widgets/bounds_panel.py`
- **_parse_sci()** (4 connections) — `gui/widgets/bounds_panel.py`
- **parameter_descriptions.py** (3 connections) — `gui/parameter_descriptions.py`
- **.set_values()** (3 connections) — `gui/widgets/bounds_panel.py`
- **.values()** (3 connections) — `gui/widgets/bounds_panel.py`
- **.set_assay_type()** (3 connections) — `gui/widgets/bounds_panel.py`
- **fit_linear_assay** (2 connections) — `core/pipeline/fit_pipeline.py`
- **.default_hi()** (2 connections) — `gui/widgets/bounds_panel.py`
- **.default_lo()** (2 connections) — `gui/widgets/bounds_panel.py`
- **.reset_to_defaults()** (2 connections) — `gui/widgets/bounds_panel.py`
- **Scientist-facing descriptions of fitted parameters and their bounds.  Each entry** (1 connections) — `gui/parameter_descriptions.py`
- **_with_sci_note()** (1 connections) — `gui/parameter_descriptions.py`
- **fmt_param** (1 connections) — `gui/plotting/labels.py`
- **._on_dye_alone_toggled()** (1 connections) — `gui/widgets/bounds_panel.py`
- **BoundsPanel — registry-driven parameter bounds editor with dye-alone priors.** (1 connections) — `gui/widgets/bounds_panel.py`
- **Registry-driven parameter bounds editor.      Auto-populates from ``ASSAY_REGIST** (1 connections) — `gui/widgets/bounds_panel.py`
- **Return custom Quantity bounds or None if all match defaults.** (1 connections) — `gui/widgets/bounds_panel.py`
- *... and 2 more nodes in this community*

## Relationships

- [[Fit Config Panel]] (10 shared connections)
- [[Checkbox Grid UI Helpers]] (7 shared connections)
- [[Assay Base & Registry Metadata]] (6 shared connections)
- [[MeasurementSet & FitResult]] (5 shared connections)
- [[Dye-Alone Calibration & Scaling]] (3 shared connections)
- [[Distributions Export Config]] (3 shared connections)
- [[load_measurements]] (2 shared connections)
- [[Dye-Alone Calibration Chain]] (2 shared connections)
- [[Label Formatting]] (2 shared connections)
- [[BaseAssay Interface]] (1 shared connections)
- [[Style Template Persistence]] (1 shared connections)
- [[FittingSession Export]] (1 shared connections)

## Source Files

- `core/pipeline/fit_pipeline.py`
- `gui/parameter_descriptions.py`
- `gui/plotting/labels.py`
- `gui/widgets/bounds_panel.py`

## Audit Trail

- EXTRACTED: 99 (82%)
- INFERRED: 22 (18%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*