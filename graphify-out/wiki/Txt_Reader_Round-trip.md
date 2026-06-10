# Txt Reader Round-trip

> 20 nodes · cohesion 0.14

## Key Concepts

- **TxtReader** (15 connections) — `core/io/formats/txt.py`
- **TestTxtReader** (13 connections) — `tests/unit/test_io.py`
- **test_io.py** (9 connections) — `tests/unit/test_io.py`
- **TestTxtWriter** (5 connections) — `tests/unit/test_io.py`
- **.test_concentration_header_variant()** (3 connections) — `tests/unit/test_io.py`
- **.test_empty_file_raises()** (3 connections) — `tests/unit/test_io.py`
- **.test_multi_replica()** (3 connections) — `tests/unit/test_io.py`
- **.test_single_data_row()** (3 connections) — `tests/unit/test_io.py`
- **.test_single_replica()** (3 connections) — `tests/unit/test_io.py`
- **.test_skips_comment_lines()** (3 connections) — `tests/unit/test_io.py`
- **Reader for tab-separated measurement files with multi-replica support.** (1 connections) — `core/io/formats/txt.py`
- **P4: I/O round-trip tests.  Verify that measurement data survives write→read cycl** (1 connections) — `tests/unit/test_io.py`
- **TxtReader correctly parses measurement files.** (1 connections) — `tests/unit/test_io.py`
- **TxtWriter correctly serializes fit results.** (1 connections) — `tests/unit/test_io.py`
- **Single replica file loads correctly.** (1 connections) — `tests/unit/test_io.py`
- **Multi-replica file with repeated headers is parsed correctly.** (1 connections) — `tests/unit/test_io.py`
- **Lines starting with # are ignored.** (1 connections) — `tests/unit/test_io.py`
- **A file with exactly one data row loads as a 1-row replica.** (1 connections) — `tests/unit/test_io.py`
- **Empty file raises ValueError.** (1 connections) — `tests/unit/test_io.py`
- **Accepts 'concentration' as header name.** (1 connections) — `tests/unit/test_io.py`

## Relationships

- [[CSV Reader]] (5 shared connections)
- [[load_measurements]] (4 shared connections)
- [[DBA Datasets & Txt Reader]] (3 shared connections)
- [[Core Domain Init]] (2 shared connections)
- [[Concentration I/O Round-trip]] (1 shared connections)
- [[Robust Aggregation & Units]] (1 shared connections)

## Source Files

- `core/io/formats/txt.py`
- `tests/unit/test_io.py`

## Audit Trail

- EXTRACTED: 62 (89%)
- INFERRED: 8 (11%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*