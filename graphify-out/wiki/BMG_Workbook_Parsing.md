# BMG Workbook Parsing

> 12 nodes · cohesion 0.18

## Key Concepts

- **xlsx_reader.py** (9 connections) — `core/io/formats/xlsx_reader.py`
- **parse_bmg_workbook** (6 connections) — `core/io/formats/bmg_reader.py`
- **Long-format measurement DataFrame contract** (5 connections) — `core/io/formats/csv_reader.py`
- **TestBMGParse** (5 connections) — `tests/unit/test_io_bmg.py`
- **TestParsing (EnSight)** (4 connections) — `tests/unit/test_ensight_reader.py`
- **Plate-reader placeholder concentration flag** (3 connections) — `core/io/formats/bmg_reader.py`
- **is_bmg_workbook** (2 connections) — `core/io/formats/bmg_reader.py`
- **BMG placeholder concentrations sentinel flag** (2 connections) — `tests/unit/test_io_bmg.py`
- **_read_legacy_var_signal** (2 connections) — `tests/unit/test_ensight_reader.py`
- **.test_shape_and_placeholders()** (2 connections) — `tests/unit/test_io_bmg.py`
- **Excel (.xlsx/.xls) format reader for measurement data.  Sheet conventions ------** (1 connections) — `core/io/formats/xlsx_reader.py`
- **_minimal_ensight** (1 connections) — `tests/unit/test_ensight_reader.py`

## Relationships

- [[EnSight Reader]] (5 shared connections)
- [[BMG Reader]] (4 shared connections)
- [[CSV Reader]] (1 shared connections)
- [[Jasco Reader]] (1 shared connections)
- [[Assay Condition Fields]] (1 shared connections)
- [[EnSight Loading & Channels]] (1 shared connections)
- [[Core Domain Init]] (1 shared connections)
- [[DBA Datasets & Txt Reader]] (1 shared connections)
- [[Excel Reader]] (1 shared connections)
- [[Reader Registry Dispatch]] (1 shared connections)
- [[MeasurementSet & FitResult]] (1 shared connections)

## Source Files

- `core/io/formats/bmg_reader.py`
- `core/io/formats/csv_reader.py`
- `core/io/formats/xlsx_reader.py`
- `tests/unit/test_ensight_reader.py`
- `tests/unit/test_io_bmg.py`

## Audit Trail

- EXTRACTED: 28 (67%)
- INFERRED: 13 (31%)
- AMBIGUOUS: 1 (2%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*