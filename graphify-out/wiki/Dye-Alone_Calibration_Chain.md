# Dye-Alone Calibration Chain

> 17 nodes · cohesion 0.17

## Key Concepts

- **fit_linear_assay()** (15 connections) — `core/pipeline/fit_pipeline.py`
- **TestChainedWorkflow** (13 connections) — `tests/integration/test_pipeline_e2e.py`
- **TestDyeAloneEndToEnd** (10 connections) — `tests/integration/test_pipeline_e2e.py`
- **DyeAloneAssay** (7 connections) — `core/pipeline/fit_pipeline.py`
- **_dye_alone_assay()** (6 connections) — `tests/integration/test_pipeline_e2e.py`
- **._dye_alone_bounds()** (6 connections) — `tests/integration/test_pipeline_e2e.py`
- **.test_bounds_from_dye_alone_values()** (5 connections) — `tests/integration/test_pipeline_e2e.py`
- **.test_dye_alone_to_dba()** (5 connections) — `tests/integration/test_pipeline_e2e.py`
- **.test_margin_zero_collapses_to_point()** (4 connections) — `tests/integration/test_pipeline_e2e.py`
- **._consistent_dye_alone_assay()** (4 connections) — `tests/integration/test_pipeline_e2e.py`
- **.test_linear_fit_round_trip()** (4 connections) — `tests/integration/test_pipeline_e2e.py`
- **.test_metadata()** (3 connections) — `tests/integration/test_pipeline_e2e.py`
- **Test the calibration chain: dye-alone → derive signal bounds → downstream fit.** (1 connections) — `tests/integration/test_pipeline_e2e.py`
- **Build a dye-alone assay with signal params matching binding assays.** (1 connections) — `tests/integration/test_pipeline_e2e.py`
- **Fit consistent dye-alone and derive signal bounds.** (1 connections) — `tests/integration/test_pipeline_e2e.py`
- **Verify derived bounds bracket the known truth.** (1 connections) — `tests/integration/test_pipeline_e2e.py`
- **Fit a dye-alone assay using simple linear regression.      Parameters     ------** (1 connections) — `core/pipeline/fit_pipeline.py`

## Relationships

- [[Dye-Alone Calibration & Scaling]] (13 shared connections)
- [[DBA Assay Integration]] (9 shared connections)
- [[MeasurementSet & FitResult]] (6 shared connections)
- [[IDA Assay & Per-Replica Fits]] (4 shared connections)
- [[BaseAssay Interface]] (3 shared connections)
- [[GDA Assay]] (2 shared connections)
- [[Parameter Descriptions & Linear Fit]] (2 shared connections)
- [[Assay Base & Registry Metadata]] (1 shared connections)
- [[Linear Dye-Alone Model]] (1 shared connections)

## Source Files

- `core/pipeline/fit_pipeline.py`
- `tests/integration/test_pipeline_e2e.py`

## Audit Trail

- EXTRACTED: 67 (77%)
- INFERRED: 20 (23%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*