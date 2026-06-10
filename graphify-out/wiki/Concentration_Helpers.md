# Concentration Helpers

> 30 nodes · cohesion 0.11

## Key Concepts

- **data_panel.py** (12 connections) — `gui/widgets/data_panel.py`
- **load_concentration_vector()** (9 connections) — `core/data_processing/concentration.py`
- **save_concentration_vector()** (9 connections) — `core/data_processing/concentration.py`
- **extract_concentrations_from_file()** (8 connections) — `core/data_processing/concentration.py`
- **concentration.py** (7 connections) — `core/data_processing/concentration.py`
- **read_raw_concentrations()** (7 connections) — `core/data_processing/concentration.py`
- **TestConcentrationRoundTrip** (7 connections) — `tests/unit/test_concentration.py`
- **test_concentration.py** (6 connections) — `tests/unit/test_concentration.py`
- **ndarray** (4 connections) — `core/data_processing/concentration.py`
- **Path** (4 connections) — `core/data_processing/concentration.py`
- **.test_save_M_load_M()** (4 connections) — `tests/unit/test_concentration.py`
- **.test_save_uM_load_M()** (4 connections) — `tests/unit/test_concentration.py`
- **.test_extract_from_txt_file()** (3 connections) — `tests/unit/test_concentration.py`
- **_build_data_help_html()** (3 connections) — `gui/widgets/data_panel.py`
- **.test_empty_list_raises()** (2 connections) — `tests/unit/test_concentration.py`
- **.test_missing_concentrations_raises()** (2 connections) — `tests/unit/test_concentration.py`
- **TestExtractConcentrations** (2 connections) — `tests/unit/test_concentration.py`
- **._on_save_concentrations()** (2 connections) — `gui/widgets/data_panel.py`
- **Helpers for saving, loading, and extracting concentration vectors.  Concentratio** (1 connections) — `core/data_processing/concentration.py`
- **Load a data file via the I/O registry and extract its concentration column.** (1 connections) — `core/data_processing/concentration.py`
- **Save a concentration vector to a JSON file.      Parameters     ----------     c** (1 connections) — `core/data_processing/concentration.py`
- **Load a concentration vector from a JSON file.      Parameters     ----------** (1 connections) — `core/data_processing/concentration.py`
- **Read a concentration vector as face-value numbers plus a declared unit.      Dis** (1 connections) — `core/data_processing/concentration.py`
- **Tests for concentration vector save/load with unit handling.** (1 connections) — `tests/unit/test_concentration.py`
- **Verify save → load preserves values regardless of stored unit.** (1 connections) — `tests/unit/test_concentration.py`
- *... and 5 more nodes in this community*

## Relationships

- [[EnSight Loading & Channels]] (5 shared connections)
- [[load_measurements]] (3 shared connections)
- [[Assay Base & Registry Metadata]] (2 shared connections)
- [[File Load & Channel Labels]] (2 shared connections)
- [[Concentration I/O Round-trip]] (1 shared connections)
- [[MeasurementSet & FitResult]] (1 shared connections)
- [[Fit Config Panel]] (1 shared connections)

## Source Files

- `core/data_processing/concentration.py`
- `gui/widgets/data_panel.py`
- `tests/unit/test_concentration.py`

## Audit Trail

- EXTRACTED: 106 (99%)
- INFERRED: 1 (1%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*