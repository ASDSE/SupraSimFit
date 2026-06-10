# BaseAssay Contracts

> 10 nodes · cohesion 0.20

## Key Concepts

- **TestBaseAssayContracts** (10 connections) — `tests/unit/test_fail_fast.py`
- **.test_parameter_keys_from_registry()** (3 connections) — `tests/unit/test_fail_fast.py`
- **.test_params_to_dict()** (3 connections) — `tests/unit/test_fail_fast.py`
- **.test_residuals_correct()** (2 connections) — `tests/unit/test_fail_fast.py`
- **.test_sum_squared_residuals()** (2 connections) — `tests/unit/test_fail_fast.py`
- **Base assay properties and methods work correctly.** (1 connections) — `tests/unit/test_fail_fast.py`
- **Assay exposes correct parameter_keys from registry.** (1 connections) — `tests/unit/test_fail_fast.py`
- **params_to_dict maps array values to parameter names.** (1 connections) — `tests/unit/test_fail_fast.py`
- **Residuals = observed - predicted, hand-computed for a linear model.          slo** (1 connections) — `tests/unit/test_fail_fast.py`
- **SSR hand-computed: 0² + 10² + (-10)² = 200.** (1 connections) — `tests/unit/test_fail_fast.py`

## Relationships

- [[GDA Assay]] (3 shared connections)
- [[DBA Assay Integration]] (1 shared connections)
- [[Dye-Alone Calibration & Scaling]] (1 shared connections)
- [[IDA Assay & Per-Replica Fits]] (1 shared connections)
- [[Dye-Alone Fail-Fast]] (1 shared connections)

## Source Files

- `tests/unit/test_fail_fast.py`

## Audit Trail

- EXTRACTED: 21 (84%)
- INFERRED: 4 (16%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*