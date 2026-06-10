# Export Writers

> 12 nodes · cohesion 0.20

## Key Concepts

- **build_artefacts** (7 connections) — `gui/session.py`
- **TestMeasurementWriters** (6 connections) — `tests/unit/test_io_bmg.py`
- **._build_ms()** (4 connections) — `tests/unit/test_io_bmg.py`
- **.test_csv_round_trip()** (4 connections) — `tests/unit/test_io_bmg.py`
- **.test_txt_round_trip()** (4 connections) — `tests/unit/test_io_bmg.py`
- **export_batch** (3 connections) — `gui/session.py`
- **write_measurements_txt** (2 connections) — `core/io/formats/measurement_writer.py`
- **export_results** (2 connections) — `gui/session.py`
- **MeasurementSet** (2 connections) — `tests/unit/test_io_bmg.py`
- **write_measurements_csv** (1 connections) — `core/io/formats/measurement_writer.py`
- **save_style_json** (1 connections) — `gui/plotting/plot_style.py`
- **test_export_batch_collects_exceptions_and_continues** (1 connections) — `tests/unit/test_export_multiple.py`

## Relationships

- [[MeasurementSet & FitResult]] (3 shared connections)
- [[Batch Artefact Export]] (2 shared connections)
- [[load_measurements]] (2 shared connections)
- [[Measurement Writer]] (2 shared connections)
- [[Assay Conditions Registry]] (1 shared connections)
- [[BMG Reader]] (1 shared connections)

## Source Files

- `core/io/formats/measurement_writer.py`
- `gui/plotting/plot_style.py`
- `gui/session.py`
- `tests/unit/test_export_multiple.py`
- `tests/unit/test_io_bmg.py`

## Audit Trail

- EXTRACTED: 33 (89%)
- INFERRED: 4 (11%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*