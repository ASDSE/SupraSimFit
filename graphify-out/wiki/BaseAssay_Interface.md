# BaseAssay Interface

> 54 nodes · cohesion 0.06

## Key Concepts

- **BaseAssay** (73 connections) — `core/assays/base.py`
- **FitConfig** (66 connections) — `core/pipeline/fit_pipeline.py`
- **PerReplicaFitError** (27 connections) — `core/pipeline/fit_pipeline.py`
- **FitWorker** (21 connections) — `gui/workers.py`
- **workers.py** (9 connections) — `gui/workers.py`
- **ndarray** (7 connections) — `core/assays/base.py`
- **.residuals()** (6 connections) — `core/assays/base.py`
- **Any** (6 connections) — `gui/workers.py`
- **BaseAssay** (6 connections) — `gui/workers.py`
- **FitConfig** (6 connections) — `gui/workers.py`
- **MeasurementSet** (6 connections) — `gui/workers.py`
- **.forward_model()** (5 connections) — `core/assays/dye_alone.py`
- **.forward_model()** (5 connections) — `core/assays/gda.py`
- **.forward_model()** (5 connections) — `core/assays/ida.py`
- **fit_measurement_set** (5 connections) — `core/pipeline/fit_pipeline.py`
- **.__init__()** (5 connections) — `gui/workers.py`
- **.forward_model()** (4 connections) — `core/assays/base.py`
- **.sum_squared_residuals()** (4 connections) — `core/assays/base.py`
- **Quantity** (4 connections) — `core/assays/base.py`
- **.get_default_bounds()** (3 connections) — `core/assays/base.py`
- **.params_from_dict()** (3 connections) — `core/assays/base.py`
- **.params_to_dict()** (3 connections) — `core/assays/base.py`
- **ndarray** (3 connections) — `core/assays/dye_alone.py`
- **Quantity** (3 connections) — `core/assays/dye_alone.py`
- **ndarray** (3 connections) — `core/assays/gda.py`
- *... and 29 more nodes in this community*

## Relationships

- [[Dye-Alone Calibration & Scaling]] (30 shared connections)
- [[Assay Base & Registry Metadata]] (26 shared connections)
- [[IDA Assay & Per-Replica Fits]] (25 shared connections)
- [[MeasurementSet & FitResult]] (23 shared connections)
- [[DBA Assay Integration]] (11 shared connections)
- [[Assay Condition Fields]] (9 shared connections)
- [[Distributions Export Config]] (6 shared connections)
- [[MeasurementSet DataFrame]] (4 shared connections)
- [[Checkbox Grid UI Helpers]] (4 shared connections)
- [[Fit Config Panel]] (4 shared connections)
- [[Dye-Alone Calibration Chain]] (3 shared connections)
- [[Robust Aggregation & Units]] (3 shared connections)

## Source Files

- `core/assays/base.py`
- `core/assays/dye_alone.py`
- `core/assays/gda.py`
- `core/assays/ida.py`
- `core/pipeline/fit_pipeline.py`
- `examples/plotting_demo.py`
- `gui/workers.py`
- `tests/unit/test_scaling.py`

## Audit Trail

- EXTRACTED: 171 (52%)
- INFERRED: 161 (48%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*