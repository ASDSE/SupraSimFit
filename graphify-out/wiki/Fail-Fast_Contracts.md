# Fail-Fast Contracts

> 17 nodes · cohesion 0.18

## Key Concepts

- **._valid_kwargs()** (16 connections) — `tests/unit/test_fail_fast.py`
- **TestGDAFailFast** (15 connections) — `tests/unit/test_fail_fast.py`
- **TestDBAFailFast** (10 connections) — `tests/unit/test_fail_fast.py`
- **.test_invalid_mode_raises()** (3 connections) — `tests/unit/test_fail_fast.py`
- **.test_missing_fixed_conc_raises()** (3 connections) — `tests/unit/test_fail_fast.py`
- **.test_negative_fixed_conc_raises()** (3 connections) — `tests/unit/test_fail_fast.py`
- **.test_mismatched_data_shapes_raises()** (3 connections) — `tests/unit/test_fail_fast.py`
- **.test_missing_g0_raises()** (3 connections) — `tests/unit/test_fail_fast.py`
- **.test_missing_h0_raises()** (3 connections) — `tests/unit/test_fail_fast.py`
- **.test_missing_ka_dye_raises()** (3 connections) — `tests/unit/test_fail_fast.py`
- **.test_negative_g0_raises()** (3 connections) — `tests/unit/test_fail_fast.py`
- **.test_negative_ka_dye_raises()** (3 connections) — `tests/unit/test_fail_fast.py`
- **.test_zero_h0_raises()** (3 connections) — `tests/unit/test_fail_fast.py`
- **Fail-fast contract (reject invalid input immediately)** (2 connections) — `tests/unit/test_fail_fast.py`
- **DBA constructor rejects invalid inputs.** (1 connections) — `tests/unit/test_fail_fast.py`
- **GDA constructor rejects invalid inputs.** (1 connections) — `tests/unit/test_fail_fast.py`
- **._valid_kwargs()** (1 connections) — `tests/unit/test_fail_fast.py`

## Relationships

- [[GDA Assay]] (10 shared connections)
- [[DBA Assay Integration]] (5 shared connections)
- [[IDA Fail-Fast]] (5 shared connections)
- [[Dye-Alone Calibration & Scaling]] (2 shared connections)
- [[IDA Assay & Per-Replica Fits]] (2 shared connections)
- [[Dye-Alone Fail-Fast]] (2 shared connections)

## Source Files

- `tests/unit/test_fail_fast.py`

## Audit Trail

- EXTRACTED: 65 (86%)
- INFERRED: 11 (14%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*