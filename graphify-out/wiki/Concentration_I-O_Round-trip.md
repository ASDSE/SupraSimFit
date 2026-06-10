# Concentration I/O Round-trip

> 13 nodes · cohesion 0.15

## Key Concepts

- **load_measurements** (9 connections) — `core/io/__init__.py`
- **TestBMGRoundTripAfterConcentrationFix** (6 connections) — `tests/unit/test_io_bmg.py`
- **I/O round-trip data integrity** (4 connections) — `tests/unit/test_io.py`
- **TestSerialization (FitResult)** (3 connections) — `tests/unit/test_fit_results.py`
- **TestParsing (JASCO)** (3 connections) — `tests/unit/test_jasco_reader.py`
- **.test_full_round_trip()** (3 connections) — `tests/unit/test_io_bmg.py`
- **extract_concentrations_from_file** (2 connections) — `core/data_processing/concentration.py`
- **read_raw_concentrations** (2 connections) — `core/data_processing/concentration.py`
- **_sample_fit_result** (2 connections) — `tests/unit/test_fit_results.py`
- **MeasurementSet.from_dataframe** (1 connections) — `core/data_processing/measurement_set.py`
- **TestDispatch (EnSight)** (1 connections) — `tests/unit/test_ensight_reader.py`
- **_minimal_jasco** (1 connections) — `tests/unit/test_jasco_reader.py`
- **Load BMG, replace placeholder concentrations, export, reload.** (1 connections) — `tests/unit/test_io_bmg.py`

## Relationships

- [[load_measurements]] (3 shared connections)
- [[MeasurementSet & FitResult]] (3 shared connections)
- [[EnSight Loading & Channels]] (2 shared connections)
- [[Concentration Helpers]] (1 shared connections)
- [[Parameter Descriptions & Linear Fit]] (1 shared connections)
- [[Txt Reader Round-trip]] (1 shared connections)
- [[Jasco Reader]] (1 shared connections)
- [[BMG Reader]] (1 shared connections)
- [[Measurement Writer]] (1 shared connections)

## Source Files

- `core/data_processing/concentration.py`
- `core/data_processing/measurement_set.py`
- `core/io/__init__.py`
- `tests/unit/test_ensight_reader.py`
- `tests/unit/test_fit_results.py`
- `tests/unit/test_io.py`
- `tests/unit/test_io_bmg.py`
- `tests/unit/test_jasco_reader.py`

## Audit Trail

- EXTRACTED: 29 (76%)
- INFERRED: 9 (24%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*