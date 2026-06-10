# MeasurementSet Immutability

> 9 nodes · cohesion 0.22

## Key Concepts

- **test_measurement_set.py** (13 connections) — `tests/unit/test_measurement_set.py`
- **TestImmutability** (6 connections) — `tests/unit/test_measurement_set.py`
- **TestUUID** (5 connections) — `tests/unit/test_measurement_set.py`
- **.test_concentrations_readonly()** (2 connections) — `tests/unit/test_measurement_set.py`
- **.test_signals_readonly()** (2 connections) — `tests/unit/test_measurement_set.py`
- **.test_unique_ids()** (2 connections) — `tests/unit/test_measurement_set.py`
- **Tests for MeasurementSet construction and behaviour.** (1 connections) — `tests/unit/test_measurement_set.py`
- **Raw data arrays are read-only after construction.** (1 connections) — `tests/unit/test_measurement_set.py`
- **Auto-generated IDs are unique.** (1 connections) — `tests/unit/test_measurement_set.py`

## Relationships

- [[set_concentrations Mutation]] (5 shared connections)
- [[GDA Assay]] (3 shared connections)
- [[MeasurementSet & FitResult]] (3 shared connections)
- [[Assay Base & Registry Metadata]] (1 shared connections)
- [[DataFrame Validation]] (1 shared connections)
- [[MeasurementSet Construction]] (1 shared connections)
- [[Replica Data Access]] (1 shared connections)
- [[Replica Active Mask]] (1 shared connections)
- [[to_assay Construction]] (1 shared connections)

## Source Files

- `tests/unit/test_measurement_set.py`

## Audit Trail

- EXTRACTED: 29 (88%)
- INFERRED: 4 (12%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*