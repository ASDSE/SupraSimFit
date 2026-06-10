# Jasco Reader

> 42 nodes · cohesion 0.08

## Key Concepts

- **JascoReader** (27 connections) — `core/io/formats/jasco_reader.py`
- **TestParsing** (12 connections) — `tests/unit/test_jasco_reader.py`
- **_minimal_jasco()** (10 connections) — `tests/unit/test_jasco_reader.py`
- **test_jasco_reader.py** (8 connections) — `tests/unit/test_jasco_reader.py`
- **.read()** (7 connections) — `core/io/formats/jasco_reader.py`
- **._parse_data_block()** (6 connections) — `core/io/formats/jasco_reader.py`
- **Path** (5 connections) — `core/io/formats/jasco_reader.py`
- **._convert_x_to_M()** (5 connections) — `core/io/formats/jasco_reader.py`
- **._partition()** (5 connections) — `core/io/formats/jasco_reader.py`
- **TestSniffing** (5 connections) — `tests/unit/test_jasco_reader.py`
- **.test_single_key_still_returns_string()** (4 connections) — `tests/unit/test_jasco_reader.py`
- **.can_read()** (3 connections) — `core/io/formats/jasco_reader.py`
- **._parse_extended()** (3 connections) — `core/io/formats/jasco_reader.py`
- **TestDispatch** (3 connections) — `tests/unit/test_jasco_reader.py`
- **.test_extended_info_parsed()** (3 connections) — `tests/unit/test_jasco_reader.py`
- **.test_npoints_mismatch_raises()** (3 connections) — `tests/unit/test_jasco_reader.py`
- **.test_real_file_golden()** (3 connections) — `tests/unit/test_jasco_reader.py`
- **.test_repeated_keys_preserved_as_list()** (3 connections) — `tests/unit/test_jasco_reader.py`
- **.test_unit_conversion()** (3 connections) — `tests/unit/test_jasco_reader.py`
- **.test_unknown_unit_raises()** (3 connections) — `tests/unit/test_jasco_reader.py`
- **.test_variable_npoints()** (3 connections) — `tests/unit/test_jasco_reader.py`
- **ndarray** (2 connections) — `core/io/formats/jasco_reader.py`
- **.test_plain_csv_still_uses_generic_reader()** (2 connections) — `tests/unit/test_jasco_reader.py`
- **.test_metadata_round_trips()** (2 connections) — `tests/unit/test_jasco_reader.py`
- **.test_missing_xydata_marker_raises()** (2 connections) — `tests/unit/test_jasco_reader.py`
- *... and 17 more nodes in this community*

## Relationships

- [[Reader Registry Dispatch]] (3 shared connections)
- [[load_measurements]] (2 shared connections)
- [[CSV Reader]] (1 shared connections)
- [[EnSight Reader]] (1 shared connections)
- [[Core Domain Init]] (1 shared connections)
- [[Content-Sniffing Registry]] (1 shared connections)
- [[BMG Workbook Parsing]] (1 shared connections)
- [[Concentration I/O Round-trip]] (1 shared connections)

## Source Files

- `core/io/formats/jasco_reader.py`
- `tests/unit/test_jasco_reader.py`

## Audit Trail

- EXTRACTED: 142 (94%)
- INFERRED: 9 (6%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*