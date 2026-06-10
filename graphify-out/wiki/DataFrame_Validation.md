# DataFrame Validation

> 7 nodes · cohesion 0.29

## Key Concepts

- **DataFrame** (5 connections) — `tests/unit/test_measurement_set.py`
- **_sample_dataframe()** (4 connections) — `tests/unit/test_measurement_set.py`
- **.test_mismatched_grids_raises()** (3 connections) — `tests/unit/test_measurement_set.py`
- **.test_missing_column_raises()** (3 connections) — `tests/unit/test_measurement_set.py`
- **Build a simple long-form DataFrame with known values.** (1 connections) — `tests/unit/test_measurement_set.py`
- **Missing required column raises ValueError.** (1 connections) — `tests/unit/test_measurement_set.py`
- **Replicas with different concentration grids raise ValueError.** (1 connections) — `tests/unit/test_measurement_set.py`

## Relationships

- [[MeasurementSet Construction]] (2 shared connections)
- [[GDA Assay]] (1 shared connections)
- [[MeasurementSet & FitResult]] (1 shared connections)
- [[MeasurementSet Immutability]] (1 shared connections)
- [[set_concentrations Mutation]] (1 shared connections)

## Source Files

- `tests/unit/test_measurement_set.py`

## Audit Trail

- EXTRACTED: 16 (89%)
- INFERRED: 2 (11%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*