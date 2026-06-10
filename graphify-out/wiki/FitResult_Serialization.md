# FitResult Serialization

> 19 nodes · cohesion 0.13

## Key Concepts

- **_sample_fit_result()** (9 connections) — `tests/unit/test_fit_results.py`
- **TestSerialization** (8 connections) — `tests/unit/test_fit_results.py`
- **test_fit_results.py** (6 connections) — `tests/unit/test_fit_results.py`
- **TestFitResultProperties** (4 connections) — `tests/unit/test_fit_results.py`
- **.test_round_trip()** (3 connections) — `tests/unit/test_fit_results.py`
- **.test_round_trip_nan_uncertainty()** (3 connections) — `tests/unit/test_fit_results.py`
- **.test_to_dict_json_safe()** (3 connections) — `tests/unit/test_fit_results.py`
- **FitResult** (2 connections) — `tests/unit/test_fit_results.py`
- **.test_unique_ids()** (2 connections) — `tests/unit/test_fit_results.py`
- **.test_from_dict_missing_optional_fields()** (2 connections) — `tests/unit/test_fit_results.py`
- **.test_x_fit_y_fit_are_ndarray_after_from_dict()** (2 connections) — `tests/unit/test_fit_results.py`
- **Tests for FitResult serialization and traceability.** (1 connections) — `tests/unit/test_fit_results.py`
- **from_dict handles missing optional keys gracefully.** (1 connections) — `tests/unit/test_fit_results.py`
- **NaN uncertainties survive round-trip.** (1 connections) — `tests/unit/test_fit_results.py`
- **Build a minimal FitResult for testing.** (1 connections) — `tests/unit/test_fit_results.py`
- **Core properties and defaults.** (1 connections) — `tests/unit/test_fit_results.py`
- **to_dict / from_dict round-trip.** (1 connections) — `tests/unit/test_fit_results.py`
- **All values must be JSON-serializable.** (1 connections) — `tests/unit/test_fit_results.py`
- **from_dict(to_dict(r)) reproduces r faithfully.** (1 connections) — `tests/unit/test_fit_results.py`

## Relationships

- [[MeasurementSet & FitResult]] (5 shared connections)
- [[Assay Base & Registry Metadata]] (1 shared connections)

## Source Files

- `tests/unit/test_fit_results.py`

## Audit Trail

- EXTRACTED: 49 (94%)
- INFERRED: 3 (6%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*