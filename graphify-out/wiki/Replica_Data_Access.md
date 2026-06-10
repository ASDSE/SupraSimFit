# Replica Data Access

> 9 nodes · cohesion 0.22

## Key Concepts

- **TestDataAccess** (10 connections) — `tests/unit/test_measurement_set.py`
- **.test_iter_replicas_returns_views()** (3 connections) — `tests/unit/test_measurement_set.py`
- **.test_average_signal_active_only()** (2 connections) — `tests/unit/test_measurement_set.py`
- **.test_average_signal_all()** (2 connections) — `tests/unit/test_measurement_set.py`
- **.test_average_signal_no_replicas_raises()** (2 connections) — `tests/unit/test_measurement_set.py`
- **.test_iter_replicas_active_only()** (2 connections) — `tests/unit/test_measurement_set.py`
- **.test_iter_replicas_all()** (2 connections) — `tests/unit/test_measurement_set.py`
- **iter_replicas, get_replica_signal, average_signal.** (1 connections) — `tests/unit/test_measurement_set.py`
- **Yielded signals are views (not copies) into the underlying array.** (1 connections) — `tests/unit/test_measurement_set.py`

## Relationships

- [[set_concentrations Mutation]] (6 shared connections)
- [[GDA Assay]] (1 shared connections)
- [[MeasurementSet & FitResult]] (1 shared connections)
- [[MeasurementSet Immutability]] (1 shared connections)

## Source Files

- `tests/unit/test_measurement_set.py`

## Audit Trail

- EXTRACTED: 23 (92%)
- INFERRED: 2 (8%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*