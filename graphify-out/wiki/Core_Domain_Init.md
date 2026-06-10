# Core Domain Init

> 15 nodes · cohesion 0.14

## Key Concepts

- **__init__.py** (12 connections) — `core/io/__init__.py`
- **save_results()** (7 connections) — `core/io/__init__.py`
- **__init__.py** (6 connections) — `core/__init__.py`
- **ensight_reader.py** (5 connections) — `core/io/formats/ensight_reader.py`
- **jasco_reader.py** (5 connections) — `core/io/formats/jasco_reader.py`
- **csv_reader.py** (4 connections) — `core/io/formats/csv_reader.py`
- **.test_write_results_via_public_api()** (3 connections) — `tests/unit/test_io.py`
- **Path** (2 connections) — `core/io/__init__.py`
- **Core domain logic for molecular binding assay fitting.  Main entry points: - cor** (1 connections) — `core/__init__.py`
- **CSV format reader for comma-separated measurement data.  Supported formats -----** (1 connections) — `core/io/formats/csv_reader.py`
- **PerkinElmer EnSight plate-reader CSV export parser.  EnSight (Kaleido 3.x) expor** (1 connections) — `core/io/formats/ensight_reader.py`
- **JASCO Spectra Manager titration export reader.  JASCO instruments (FP-8300 spect** (1 connections) — `core/io/formats/jasco_reader.py`
- **Minimal I/O module for measurement data and fit results.  Public API ----------** (1 connections) — `core/io/__init__.py`
- **Save fit results to file.      Parameters     ----------     results : dict** (1 connections) — `core/io/__init__.py`
- **save_results() public API works end-to-end.** (1 connections) — `tests/unit/test_io.py`

## Relationships

- [[Reader Registry Dispatch]] (4 shared connections)
- [[load_measurements]] (3 shared connections)
- [[MeasurementReader Base]] (3 shared connections)
- [[Txt Reader Round-trip]] (2 shared connections)
- [[Data Processing & Preprocessing]] (1 shared connections)
- [[MeasurementSet & FitResult]] (1 shared connections)
- [[CSV Reader]] (1 shared connections)
- [[EnSight Reader]] (1 shared connections)
- [[File Load & Channel Labels]] (1 shared connections)
- [[Assay Base & Registry Metadata]] (1 shared connections)
- [[Jasco Reader]] (1 shared connections)
- [[DBA Datasets & Txt Reader]] (1 shared connections)

## Source Files

- `core/__init__.py`
- `core/io/__init__.py`
- `core/io/formats/csv_reader.py`
- `core/io/formats/ensight_reader.py`
- `core/io/formats/jasco_reader.py`
- `tests/unit/test_io.py`

## Audit Trail

- EXTRACTED: 51 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*