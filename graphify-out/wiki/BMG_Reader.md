# BMG Reader

> 24 nodes · cohesion 0.13

## Key Concepts

- **test_io_bmg.py** (13 connections) — `tests/unit/test_io_bmg.py`
- **parse_bmg_workbook()** (12 connections) — `core/io/formats/bmg_reader.py`
- **is_bmg_workbook()** (9 connections) — `core/io/formats/bmg_reader.py`
- **bmg_reader.py** (6 connections) — `core/io/formats/bmg_reader.py`
- **_write_structured_xlsx()** (6 connections) — `tests/unit/test_io_bmg.py`
- **_extract_metadata()** (5 connections) — `core/io/formats/bmg_reader.py`
- **Workbook** (5 connections) — `core/io/formats/bmg_reader.py`
- **_find_bmg_sheet()** (4 connections) — `core/io/formats/bmg_reader.py`
- **_find_header_row()** (4 connections) — `core/io/formats/bmg_reader.py`
- **.test_structured_xlsx_still_works()** (4 connections) — `tests/unit/test_io_bmg.py`
- **TestBMGDetection** (3 connections) — `tests/unit/test_io_bmg.py`
- **.test_structured_xlsx_is_not_bmg()** (3 connections) — `tests/unit/test_io_bmg.py`
- **TestXlsxDispatcher** (3 connections) — `tests/unit/test_io_bmg.py`
- **Any** (2 connections) — `core/io/formats/bmg_reader.py`
- **Path** (2 connections) — `tests/unit/test_io_bmg.py`
- **DataFrame** (1 connections) — `core/io/formats/bmg_reader.py`
- **BMG plate reader export parser.  BMG CLARIOstar / FLUOstar / PHERAstar instrumen** (1 connections) — `core/io/formats/bmg_reader.py`
- **Return the 1-based row index of the column-number header, or None.** (1 connections) — `core/io/formats/bmg_reader.py`
- **Pull a small dict of free-form metadata from the BMG workbook.** (1 connections) — `core/io/formats/bmg_reader.py`
- **Return True if *wb* looks like a BMG plate-reader export.      Detection is chea** (1 connections) — `core/io/formats/bmg_reader.py`
- **Parse a BMG workbook into a long-format DataFrame plus metadata.      Returns** (1 connections) — `core/io/formats/bmg_reader.py`
- **Tests for the BMG plate-reader XLSX importer and raw data writers.  The BMG read** (1 connections) — `tests/unit/test_io_bmg.py`
- **Write a minimal non-BMG .xlsx so the dispatcher's fallback path is exercised.** (1 connections) — `tests/unit/test_io_bmg.py`
- **XlsxReader must fall back to the structured path for non-BMG files.** (1 connections) — `tests/unit/test_io_bmg.py`

## Relationships

- [[BMG Workbook Parsing]] (4 shared connections)
- [[MeasurementSet & FitResult]] (4 shared connections)
- [[Excel Reader]] (2 shared connections)
- [[load_measurements]] (2 shared connections)
- [[Measurement Writer]] (2 shared connections)
- [[Concentration I/O Round-trip]] (1 shared connections)
- [[Export Writers]] (1 shared connections)

## Source Files

- `core/io/formats/bmg_reader.py`
- `tests/unit/test_io_bmg.py`

## Audit Trail

- EXTRACTED: 85 (94%)
- INFERRED: 5 (6%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*