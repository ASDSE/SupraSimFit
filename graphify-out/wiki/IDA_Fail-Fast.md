# IDA Fail-Fast

> 8 nodes · cohesion 0.25

## Key Concepts

- **TestIDAFailFast** (12 connections) — `tests/unit/test_fail_fast.py`
- **.test_missing_d0_raises()** (2 connections) — `tests/unit/test_fail_fast.py`
- **.test_missing_h0_raises()** (2 connections) — `tests/unit/test_fail_fast.py`
- **.test_missing_ka_dye_raises()** (2 connections) — `tests/unit/test_fail_fast.py`
- **.test_negative_ka_dye_raises()** (2 connections) — `tests/unit/test_fail_fast.py`
- **.test_zero_d0_raises()** (2 connections) — `tests/unit/test_fail_fast.py`
- **IDA constructor rejects invalid inputs.** (1 connections) — `tests/unit/test_fail_fast.py`
- **._valid_kwargs()** (1 connections) — `tests/unit/test_fail_fast.py`

## Relationships

- [[Fail-Fast Contracts]] (5 shared connections)
- [[DBA Assay Integration]] (1 shared connections)
- [[Dye-Alone Calibration & Scaling]] (1 shared connections)
- [[GDA Assay]] (1 shared connections)
- [[IDA Assay & Per-Replica Fits]] (1 shared connections)
- [[Dye-Alone Fail-Fast]] (1 shared connections)

## Source Files

- `tests/unit/test_fail_fast.py`

## Audit Trail

- EXTRACTED: 20 (83%)
- INFERRED: 4 (17%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*