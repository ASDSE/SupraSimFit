# MeasurementSet & FitResult

> 53 nodes · cohesion 0.04

## Key Concepts

- **MeasurementSet** (137 connections) — `core/data_processing/measurement_set.py`
- **FitResult** (98 connections) — `core/pipeline/fit_pipeline.py`
- **SessionState** (16 connections) — `gui/app_state.py`
- **plotting_demo.py** (12 connections) — `examples/plotting_demo.py`
- **app_state.py** (8 connections) — `gui/app_state.py`
- **measurement_set.py** (6 connections) — `core/data_processing/measurement_set.py`
- **plotting.py** (6 connections) — `core/data_processing/plotting.py`
- **ndarray** (5 connections) — `examples/plotting_demo.py`
- **Any** (3 connections) — `core/data_processing/plotting.py`
- **FitResult** (3 connections) — `core/data_processing/plotting.py`
- **MeasurementSet** (3 connections) — `core/data_processing/plotting.py`
- **.set_concentrations()** (3 connections) — `core/data_processing/measurement_set.py`
- **.from_dict()** (3 connections) — `core/pipeline/fit_pipeline.py`
- **.to_dict()** (3 connections) — `core/pipeline/fit_pipeline.py`
- **prepare_plot_data** (3 connections) — `core/data_processing/plotting.py`
- **Quantity** (2 connections) — `core/data_processing/measurement_set.py`
- **.active_replica_ids()** (2 connections) — `core/data_processing/measurement_set.py`
- **.dropped_replica_ids()** (2 connections) — `core/data_processing/measurement_set.py`
- **.n_active()** (2 connections) — `core/data_processing/measurement_set.py`
- **.n_points()** (2 connections) — `core/data_processing/measurement_set.py`
- **.n_replicas()** (2 connections) — `core/data_processing/measurement_set.py`
- **.__post_init__()** (2 connections) — `core/data_processing/measurement_set.py`
- **.reset_active()** (2 connections) — `core/data_processing/measurement_set.py`
- **_noisy()** (2 connections) — `examples/plotting_demo.py`
- **Backward-compat magic JSON keys (per_replicate, replicate)** (2 connections) — `core/pipeline/fit_pipeline.py`
- *... and 28 more nodes in this community*

## Relationships

- [[BaseAssay Interface]] (23 shared connections)
- [[IDA Assay & Per-Replica Fits]] (23 shared connections)
- [[Dye-Alone Calibration & Scaling]] (20 shared connections)
- [[DBA Assay Integration]] (16 shared connections)
- [[prepare_plot_data]] (14 shared connections)
- [[Data Processing & Preprocessing]] (14 shared connections)
- [[Distributions Export Config]] (13 shared connections)
- [[Assay Base & Registry Metadata]] (9 shared connections)
- [[MeasurementSet DataFrame]] (8 shared connections)
- [[Distribution Plot Widget]] (7 shared connections)
- [[Dye-Alone Calibration Chain]] (6 shared connections)
- [[Style Template Persistence]] (6 shared connections)

## Source Files

- `core/data_processing/measurement_set.py`
- `core/data_processing/plotting.py`
- `core/pipeline/fit_pipeline.py`
- `examples/plotting_demo.py`
- `gui/app_state.py`
- `gui/session.py`
- `tests/unit/test_measurement_set.py`
- `tests/unit/test_plotting_data.py`
- `tests/unit/test_preprocessing.py`

## Audit Trail

- EXTRACTED: 185 (52%)
- INFERRED: 174 (48%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*