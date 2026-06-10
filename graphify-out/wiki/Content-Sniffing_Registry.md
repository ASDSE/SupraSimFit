# Content-Sniffing Registry

> 15 nodes · cohesion 0.18

## Key Concepts

- **Content-sniffing reader registry dispatch** (5 connections) — `tests/unit/test_io_registry.py`
- **Path** (5 connections) — `tests/unit/test_io_registry.py`
- **_Accepter** (4 connections) — `tests/unit/test_io_registry.py`
- **TestRegistry (reader dispatch)** (3 connections) — `tests/unit/test_io_registry.py`
- **DataFrame** (3 connections) — `tests/unit/test_io_registry.py`
- **.read()** (3 connections) — `tests/unit/test_io_registry.py`
- **_Fallback** (3 connections) — `tests/unit/test_io_registry.py`
- **.read()** (3 connections) — `tests/unit/test_io_registry.py`
- **_Rejecter** (3 connections) — `tests/unit/test_io_registry.py`
- **.read()** (3 connections) — `tests/unit/test_io_registry.py`
- **get_reader** (2 connections) — `core/io/registry.py`
- **.can_read()** (2 connections) — `tests/unit/test_io_registry.py`
- **.can_read()** (2 connections) — `tests/unit/test_io_registry.py`
- **register_reader** (1 connections) — `core/io/registry.py`
- **No can_read → always-accepting fallback.** (1 connections) — `tests/unit/test_io_registry.py`

## Relationships

- [[Reader Registry Dispatch]] (3 shared connections)
- [[EnSight Reader]] (1 shared connections)
- [[Jasco Reader]] (1 shared connections)

## Source Files

- `core/io/registry.py`
- `tests/unit/test_io_registry.py`

## Audit Trail

- EXTRACTED: 35 (81%)
- INFERRED: 8 (19%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*