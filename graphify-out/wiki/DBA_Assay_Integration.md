# DBA Assay Integration

> 41 nodes · cohesion 0.07

## Key Concepts

- **DBAAssay** (42 connections) — `core/assays/dba.py`
- **test_pipeline_e2e.py** (35 connections) — `tests/integration/test_pipeline_e2e.py`
- **TestFailureModes** (13 connections) — `tests/integration/test_pipeline_e2e.py`
- **TestBoundsMarginEdgeCases** (10 connections) — `tests/integration/test_pipeline_e2e.py`
- **TestDBAEndToEnd** (10 connections) — `tests/integration/test_pipeline_e2e.py`
- **assay_conditions.py** (10 connections) — `gui/widgets/assay_conditions.py`
- **TestDBAHtoD** (9 connections) — `tests/integration/test_pipeline_e2e.py`
- **TestDyeAloneNoisy** (9 connections) — `tests/integration/test_pipeline_e2e.py`
- **TestFitConfigCustomization** (9 connections) — `tests/integration/test_pipeline_e2e.py`
- **TestGDAEndToEnd** (9 connections) — `tests/integration/test_pipeline_e2e.py`
- **_dba_assay()** (7 connections) — `tests/integration/test_pipeline_e2e.py`
- **.test_htod_mode_clean_round_trip()** (6 connections) — `tests/integration/test_pipeline_e2e.py`
- **dba_clean_result()** (5 connections) — `tests/integration/test_pipeline_e2e.py`
- **BaseAssay** (4 connections)
- **.test_noisy_linear_fit()** (4 connections) — `tests/integration/test_pipeline_e2e.py`
- **.test_very_wrong_bounds_no_crash()** (4 connections) — `tests/integration/test_pipeline_e2e.py`
- **.test_relaxed_min_r_squared_passes_more()** (4 connections) — `tests/integration/test_pipeline_e2e.py`
- **.test_clean_round_trip()** (4 connections) — `tests/integration/test_pipeline_e2e.py`
- **.get_conditions()** (3 connections) — `core/assays/dba.py`
- **Any** (3 connections) — `core/assays/dba.py`
- **_gda_assay()** (3 connections) — `tests/integration/test_pipeline_e2e.py`
- **.test_failed_fit_raises()** (3 connections) — `tests/integration/test_pipeline_e2e.py`
- **.test_bounds_from_dye_alone_rejects_nonlinear()** (3 connections) — `tests/integration/test_pipeline_e2e.py`
- **.test_underdetermined_data_returns_result()** (3 connections) — `tests/integration/test_pipeline_e2e.py`
- **.test_unknown_custom_bounds_key_raises()** (3 connections) — `tests/integration/test_pipeline_e2e.py`
- *... and 16 more nodes in this community*

## Relationships

- [[Dye-Alone Calibration & Scaling]] (25 shared connections)
- [[IDA Assay & Per-Replica Fits]] (18 shared connections)
- [[MeasurementSet & FitResult]] (16 shared connections)
- [[GDA Assay]] (13 shared connections)
- [[BaseAssay Interface]] (11 shared connections)
- [[Assay Base & Registry Metadata]] (9 shared connections)
- [[Dye-Alone Calibration Chain]] (9 shared connections)
- [[Fail-Fast Contracts]] (5 shared connections)
- [[Synthetic Test Fixtures]] (5 shared connections)
- [[DBA Quantity Conditions]] (3 shared connections)
- [[Assay Condition Fields]] (3 shared connections)
- [[Dye-Alone Fail-Fast]] (2 shared connections)

## Source Files

- `core/assays/dba.py`
- `gui/widgets/assay_conditions.py`
- `tests/integration/test_pipeline_e2e.py`

## Audit Trail

- EXTRACTED: 163 (69%)
- INFERRED: 72 (31%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*