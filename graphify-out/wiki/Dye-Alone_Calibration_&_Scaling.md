# Dye-Alone Calibration & Scaling

> 45 nodes · cohesion 0.08

## Key Concepts

- **DyeAloneAssay** (40 connections) — `core/assays/dye_alone.py`
- **fit_assay()** (33 connections) — `core/pipeline/fit_pipeline.py`
- **FitAttempt** (31 connections) — `core/optimizer/multistart.py`
- **ParamScaler** (29 connections) — `core/optimizer/scaling.py`
- **fit_pipeline.py** (27 connections) — `core/pipeline/fit_pipeline.py`
- **fit_measurement_set_per_replica()** (20 connections) — `core/pipeline/fit_pipeline.py`
- **fit_measurement_set()** (19 connections) — `core/pipeline/fit_pipeline.py`
- **BaseAssay** (13 connections) — `core/pipeline/fit_pipeline.py`
- **bounds_from_dye_alone()** (13 connections) — `core/pipeline/fit_pipeline.py`
- **Any** (11 connections) — `core/pipeline/fit_pipeline.py`
- **TestFitMeasurementSet** (10 connections) — `tests/integration/test_pipeline_e2e.py`
- **Quantity** (9 connections) — `core/pipeline/fit_pipeline.py`
- **_resolve_bounds()** (9 connections) — `core/pipeline/fit_pipeline.py`
- **MeasurementSet** (8 connections) — `core/pipeline/fit_pipeline.py`
- **__init__.py** (8 connections) — `core/pipeline/__init__.py`
- **ndarray** (7 connections) — `core/pipeline/fit_pipeline.py`
- **_config_to_dict()** (6 connections) — `core/pipeline/fit_pipeline.py`
- **_wrap_params_as_quantities()** (6 connections) — `core/pipeline/fit_pipeline.py`
- **_model_name_for_assay()** (5 connections) — `core/pipeline/fit_pipeline.py`
- **IDAAssay** (4 connections) — `tests/unit/test_scaling.py`
- **ndarray** (4 connections) — `tests/unit/test_scaling.py`
- **.get_conditions()** (3 connections) — `core/assays/dye_alone.py`
- **Any** (3 connections) — `core/assays/dye_alone.py`
- **.test_fit_measurement_set_dye_alone()** (3 connections) — `tests/integration/test_pipeline_e2e.py`
- **.test_fit_measurement_set_gda()** (3 connections) — `tests/integration/test_pipeline_e2e.py`
- *... and 20 more nodes in this community*

## Relationships

- [[BaseAssay Interface]] (30 shared connections)
- [[DBA Assay Integration]] (25 shared connections)
- [[MeasurementSet & FitResult]] (20 shared connections)
- [[IDA Assay & Per-Replica Fits]] (17 shared connections)
- [[Assay Base & Registry Metadata]] (13 shared connections)
- [[Dye-Alone Calibration Chain]] (13 shared connections)
- [[Multistart Optimizer]] (8 shared connections)
- [[Bounds Resolution Helpers]] (7 shared connections)
- [[Fit Filtering]] (6 shared connections)
- [[Parameter Scaling]] (5 shared connections)
- [[Fit Metrics RMSE/R²]] (5 shared connections)
- [[Linear Regression Fit]] (3 shared connections)

## Source Files

- `core/assays/dye_alone.py`
- `core/optimizer/multistart.py`
- `core/optimizer/scaling.py`
- `core/pipeline/__init__.py`
- `core/pipeline/fit_pipeline.py`
- `tests/integration/test_pipeline_e2e.py`
- `tests/unit/test_scaling.py`

## Audit Trail

- EXTRACTED: 233 (68%)
- INFERRED: 112 (32%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*