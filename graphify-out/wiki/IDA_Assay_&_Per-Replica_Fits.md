# IDA Assay & Per-Replica Fits

> 56 nodes · cohesion 0.07

## Key Concepts

- **IDAAssay** (50 connections) — `core/assays/ida.py`
- **test_per_replica_fit.py** (24 connections) — `tests/integration/test_per_replica_fit.py`
- **assert_within_tolerance()** (18 connections) — `tests/conftest.py`
- **_ida_ms()** (12 connections) — `tests/integration/test_per_replica_fit.py`
- **TestPoolAggregation** (12 connections) — `tests/integration/test_per_replica_fit.py`
- **TestPerReplicateRecovery** (11 connections) — `tests/integration/test_per_replica_fit.py`
- **TestIDAEndToEnd** (10 connections) — `tests/integration/test_pipeline_e2e.py`
- **test_nonzero_i0_recovery.py** (10 connections) — `tests/unit/test_nonzero_i0_recovery.py`
- **_ida_conditions()** (9 connections) — `tests/integration/test_per_replica_fit.py`
- **_seeded_per_replica_fit()** (9 connections) — `tests/integration/test_per_replica_fit.py`
- **FitConfig** (9 connections) — `tests/integration/test_per_replica_fit.py`
- **MeasurementSet** (9 connections) — `tests/integration/test_per_replica_fit.py`
- **TestFailureHandling** (8 connections) — `tests/integration/test_per_replica_fit.py`
- **.test_one_bad_replica_does_not_wreck_median()** (8 connections) — `tests/integration/test_per_replica_fit.py`
- **TestRescalingInvariance** (8 connections) — `tests/integration/test_per_replica_fit.py`
- **FitResult** (8 connections) — `tests/integration/test_per_replica_fit.py`
- **_per_replica_config()** (7 connections) — `tests/integration/test_per_replica_fit.py`
- **.test_all_failures_raise_per_replica_fit_error()** (7 connections) — `tests/integration/test_per_replica_fit.py`
- **.test_degenerate_replica_is_skipped()** (7 connections) — `tests/integration/test_per_replica_fit.py`
- **TestOutlierReplicateRobustness** (7 connections) — `tests/integration/test_per_replica_fit.py`
- **.test_dispatch_via_fit_measurement_set()** (6 connections) — `tests/integration/test_per_replica_fit.py`
- **.test_average_mode_also_populates_parameter_samples()** (6 connections) — `tests/integration/test_per_replica_fit.py`
- **.test_per_replica_result_matches_with_and_without_rescale()** (6 connections) — `tests/integration/test_per_replica_fit.py`
- **Any** (6 connections) — `tests/integration/test_per_replica_fit.py`
- **clean_pr_result()** (4 connections) — `tests/integration/test_per_replica_fit.py`
- *... and 31 more nodes in this community*

## Relationships

- [[BaseAssay Interface]] (25 shared connections)
- [[MeasurementSet & FitResult]] (23 shared connections)
- [[DBA Assay Integration]] (18 shared connections)
- [[Dye-Alone Calibration & Scaling]] (17 shared connections)
- [[Assay Base & Registry Metadata]] (5 shared connections)
- [[Synthetic Test Fixtures]] (5 shared connections)
- [[Dye-Alone Calibration Chain]] (4 shared connections)
- [[Ground-Truth Generators]] (3 shared connections)
- [[GDA Assay]] (3 shared connections)
- [[Dye-Alone Fail-Fast]] (2 shared connections)
- [[Fail-Fast Contracts]] (2 shared connections)
- [[Parameter Scaling]] (2 shared connections)

## Source Files

- `core/assays/ida.py`
- `tests/conftest.py`
- `tests/integration/test_per_replica_fit.py`
- `tests/integration/test_pipeline_e2e.py`
- `tests/unit/test_nonzero_i0_recovery.py`

## Audit Trail

- EXTRACTED: 234 (73%)
- INFERRED: 85 (27%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*