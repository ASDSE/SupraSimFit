# Replica Active Mask

> 6 nodes · cohesion 0.33

## Key Concepts

- **TestReplicaManagement** (8 connections) — `tests/unit/test_measurement_set.py`
- **.test_all_active_initially()** (2 connections) — `tests/unit/test_measurement_set.py`
- **.test_reset_active()** (2 connections) — `tests/unit/test_measurement_set.py`
- **.test_set_active_false()** (2 connections) — `tests/unit/test_measurement_set.py`
- **.test_set_active_true_reactivates()** (2 connections) — `tests/unit/test_measurement_set.py`
- **Active mask management.** (1 connections) — `tests/unit/test_measurement_set.py`

## Relationships

- [[set_concentrations Mutation]] (4 shared connections)
- [[GDA Assay]] (1 shared connections)
- [[MeasurementSet & FitResult]] (1 shared connections)
- [[MeasurementSet Immutability]] (1 shared connections)

## Source Files

- `tests/unit/test_measurement_set.py`

## Audit Trail

- EXTRACTED: 15 (88%)
- INFERRED: 2 (12%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*