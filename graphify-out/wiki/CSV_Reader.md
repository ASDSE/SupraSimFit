# CSV Reader

> 33 nodes · cohesion 0.11

## Key Concepts

- **CsvReader** (27 connections) — `core/io/formats/csv_reader.py`
- **TestCsvReader** (11 connections) — `tests/unit/test_io.py`
- **.read()** (9 connections) — `core/io/formats/csv_reader.py`
- **DataFrame** (7 connections) — `core/io/formats/csv_reader.py`
- **._identify_columns()** (7 connections) — `core/io/formats/csv_reader.py`
- **._parse()** (5 connections) — `core/io/formats/csv_reader.py`
- **._header_is_numeric()** (4 connections) — `core/io/formats/csv_reader.py`
- **._numeric_columns()** (4 connections) — `core/io/formats/csv_reader.py`
- **._find_named()** (3 connections) — `core/io/formats/csv_reader.py`
- **._is_monotonic()** (3 connections) — `core/io/formats/csv_reader.py`
- **._long_format()** (3 connections) — `core/io/formats/csv_reader.py`
- **._tokenize()** (3 connections) — `core/io/formats/csv_reader.py`
- **._wide_format()** (3 connections) — `core/io/formats/csv_reader.py`
- **.test_european_semicolon_comma()** (3 connections) — `tests/unit/test_io.py`
- **.test_fuzzy_headers_via_name_match()** (3 connections) — `tests/unit/test_io.py`
- **.test_headerless_inferred_by_monotonicity()** (3 connections) — `tests/unit/test_io.py`
- **.test_loads_patrick_file()** (3 connections) — `tests/unit/test_io.py`
- **.test_standard_comma_dot()** (3 connections) — `tests/unit/test_io.py`
- **.test_unparseable_raises()** (3 connections) — `tests/unit/test_io.py`
- **.test_wide_format_replicas()** (3 connections) — `tests/unit/test_io.py`
- **Path** (2 connections) — `core/io/formats/csv_reader.py`
- **True if every column name parses as a number (suggesting no header row).** (1 connections) — `core/io/formats/csv_reader.py`
- **Reader for CSV measurement files.** (1 connections) — `core/io/formats/csv_reader.py`
- **Read a CSV measurement file.          Parameters         ----------         path** (1 connections) — `core/io/formats/csv_reader.py`
- **Series** (1 connections) — `core/io/formats/csv_reader.py`
- *... and 8 more nodes in this community*

## Relationships

- [[Txt Reader Round-trip]] (5 shared connections)
- [[Core Domain Init]] (1 shared connections)
- [[BMG Workbook Parsing]] (1 shared connections)
- [[Reader Registry Dispatch]] (1 shared connections)
- [[Jasco Reader]] (1 shared connections)
- [[load_measurements]] (1 shared connections)

## Source Files

- `core/io/formats/csv_reader.py`
- `tests/unit/test_io.py`

## Audit Trail

- EXTRACTED: 117 (94%)
- INFERRED: 7 (6%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*