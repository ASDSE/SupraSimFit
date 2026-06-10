# Reader Registry Dispatch

> 18 nodes · cohesion 0.19

## Key Concepts

- **register_reader()** (19 connections) — `core/io/registry.py`
- **get_reader()** (16 connections) — `core/io/registry.py`
- **test_io_registry.py** (8 connections) — `tests/unit/test_io_registry.py`
- **TestRegistry** (8 connections) — `tests/unit/test_io_registry.py`
- **.test_all_sniffers_reject_raises()** (3 connections) — `tests/unit/test_io_registry.py`
- **.test_existing_extensions_still_dispatch()** (3 connections) — `tests/unit/test_io_registry.py`
- **.test_first_matching_sniffer_wins()** (3 connections) — `tests/unit/test_io_registry.py`
- **.test_no_can_read_acts_as_fallback()** (3 connections) — `tests/unit/test_io_registry.py`
- **MeasurementReader** (2 connections) — `core/io/registry.py`
- **isolated_registry()** (2 connections) — `tests/unit/test_io_registry.py`
- **.test_register_is_idempotent()** (2 connections) — `tests/unit/test_io_registry.py`
- **.test_registration_order_preserved()** (2 connections) — `tests/unit/test_io_registry.py`
- **.test_unknown_extension_raises()** (2 connections) — `tests/unit/test_io_registry.py`
- **Register a reader class for its supported extensions.      Multiple readers may** (1 connections) — `core/io/registry.py`
- **Get a reader instance for the given file path.      Walks the registered candida** (1 connections) — `core/io/registry.py`
- **Tests for the content-sniffing reader registry.  Covers the dispatch contract in** (1 connections) — `tests/unit/test_io_registry.py`
- **Snapshot READERS and restore after the test.** (1 connections) — `tests/unit/test_io_registry.py`
- **Default registrations (txt, csv, xlsx) survive the rewrite.** (1 connections) — `tests/unit/test_io_registry.py`

## Relationships

- [[MeasurementReader Base]] (5 shared connections)
- [[Core Domain Init]] (4 shared connections)
- [[Jasco Reader]] (3 shared connections)
- [[Content-Sniffing Registry]] (3 shared connections)
- [[load_measurements]] (1 shared connections)
- [[CSV Reader]] (1 shared connections)
- [[EnSight Reader]] (1 shared connections)
- [[DBA Datasets & Txt Reader]] (1 shared connections)
- [[BMG Workbook Parsing]] (1 shared connections)

## Source Files

- `core/io/registry.py`
- `tests/unit/test_io_registry.py`

## Audit Trail

- EXTRACTED: 76 (97%)
- INFERRED: 2 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*