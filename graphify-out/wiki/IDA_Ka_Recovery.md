# IDA Ka Recovery

> 4 nodes · cohesion 0.50

## Key Concepts

- **.test_ida_ka_guest_recovery_with_nonzero_i0()** (6 connections) — `tests/unit/test_nonzero_i0_recovery.py`
- **_bounds_with_i0_window()** (3 connections) — `tests/unit/test_nonzero_i0_recovery.py`
- **Override the I0 bounds to a finite window around the non-zero ground truth.** (1 connections) — `tests/unit/test_nonzero_i0_recovery.py`
- **IDA recovers Ka_guest to within 10% even with a non-zero I0 baseline.** (1 connections) — `tests/unit/test_nonzero_i0_recovery.py`

## Relationships

- [[IDA Assay & Per-Replica Fits]] (2 shared connections)
- [[Equilibrium Forward Models]] (1 shared connections)
- [[Dye-Alone Calibration & Scaling]] (1 shared connections)
- [[Ground-Truth Generators]] (1 shared connections)

## Source Files

- `tests/unit/test_nonzero_i0_recovery.py`

## Audit Trail

- EXTRACTED: 11 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*