# set_concentrations Mutation

> 13 nodes · cohesion 0.26

## Key Concepts

- **_sample_measurement_set()** (32 connections) — `tests/unit/test_measurement_set.py`
- **TestSetConcentrations** (13 connections) — `tests/unit/test_measurement_set.py`
- **.test_array_remains_read_only_after_set()** (2 connections) — `tests/unit/test_measurement_set.py`
- **.test_drop_metadata_keys()** (2 connections) — `tests/unit/test_measurement_set.py`
- **.test_id_is_stable()** (2 connections) — `tests/unit/test_measurement_set.py`
- **.test_micromolar_quantity_stored_as_molar()** (2 connections) — `tests/unit/test_measurement_set.py`
- **.test_preserves_active_mask()** (2 connections) — `tests/unit/test_measurement_set.py`
- **.test_preserves_signals_and_replica_ids()** (2 connections) — `tests/unit/test_measurement_set.py`
- **.test_rejects_length_mismatch()** (2 connections) — `tests/unit/test_measurement_set.py`
- **.test_rejects_non_quantity()** (2 connections) — `tests/unit/test_measurement_set.py`
- **.test_rejects_wrong_dimensionality()** (2 connections) — `tests/unit/test_measurement_set.py`
- **Shortcut to create a MeasurementSet from a sample DataFrame.** (1 connections) — `tests/unit/test_measurement_set.py`
- **``set_concentrations`` mutates the grid in place via a Pint Quantity.** (1 connections) — `tests/unit/test_measurement_set.py`

## Relationships

- [[Replica Data Access]] (6 shared connections)
- [[MeasurementSet Immutability]] (5 shared connections)
- [[Replica Active Mask]] (4 shared connections)
- [[to_assay Construction]] (4 shared connections)
- [[MeasurementSet Construction]] (3 shared connections)
- [[DataFrame Validation]] (1 shared connections)
- [[GDA Assay]] (1 shared connections)
- [[MeasurementSet & FitResult]] (1 shared connections)

## Source Files

- `tests/unit/test_measurement_set.py`

## Audit Trail

- EXTRACTED: 63 (97%)
- INFERRED: 2 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*