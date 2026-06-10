# MeasurementSet Construction

> 14 nodes · cohesion 0.18

## Key Concepts

- **TestConstruction** (12 connections) — `tests/unit/test_measurement_set.py`
- **MeasurementSet** (7 connections) — `tests/unit/test_measurement_set.py`
- **.test_from_dataframe_basic()** (3 connections) — `tests/unit/test_measurement_set.py`
- **.test_from_dataframe_sorted()** (3 connections) — `tests/unit/test_measurement_set.py`
- **.test_shape_validation_1d_concentrations()** (3 connections) — `tests/unit/test_measurement_set.py`
- **.test_shape_validation_columns_match()** (3 connections) — `tests/unit/test_measurement_set.py`
- **.test_shape_validation_replica_ids_match()** (3 connections) — `tests/unit/test_measurement_set.py`
- **.test_shape_validation_2d_signals()** (2 connections) — `tests/unit/test_measurement_set.py`
- **MeasurementSet construction and validation.** (1 connections) — `tests/unit/test_measurement_set.py`
- **Happy-path construction from a long-form DataFrame.** (1 connections) — `tests/unit/test_measurement_set.py`
- **Concentrations are sorted ascending after construction.** (1 connections) — `tests/unit/test_measurement_set.py`
- **concentrations must be 1-D.** (1 connections) — `tests/unit/test_measurement_set.py`
- **signals columns must match concentrations length.** (1 connections) — `tests/unit/test_measurement_set.py`
- **replica_ids length must match signals rows.** (1 connections) — `tests/unit/test_measurement_set.py`

## Relationships

- [[set_concentrations Mutation]] (3 shared connections)
- [[GDA Assay]] (2 shared connections)
- [[MeasurementSet & FitResult]] (2 shared connections)
- [[DataFrame Validation]] (2 shared connections)
- [[MeasurementSet Immutability]] (1 shared connections)

## Source Files

- `tests/unit/test_measurement_set.py`

## Audit Trail

- EXTRACTED: 38 (90%)
- INFERRED: 4 (10%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*