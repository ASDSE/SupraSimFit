# load_measurements

> 12 nodes · cohesion 0.18

## Key Concepts

- **load_measurements()** (25 connections) — `core/io/__init__.py`
- **TestIODataIntegrity** (8 connections) — `tests/unit/test_io.py`
- **.test_dtypes_are_numeric()** (3 connections) — `tests/unit/test_io.py`
- **.test_roundtrip_preserves_values()** (3 connections) — `tests/unit/test_io.py`
- **.test_loads_real_gda_data()** (3 connections) — `tests/unit/test_io.py`
- **.test_load_measurements_returns_channel_column()** (2 connections) — `tests/unit/test_ensight_reader.py`
- **DataFrame** (1 connections) — `core/io/__init__.py`
- **Load measurement data from file.      Parameters     ----------     path : str o** (1 connections) — `core/io/__init__.py`
- **Measurement data survives load with correct types and values.** (1 connections) — `tests/unit/test_io.py`
- **Write a measurement file, read it back, values match.** (1 connections) — `tests/unit/test_io.py`
- **Loaded data has numeric dtypes, not strings.** (1 connections) — `tests/unit/test_io.py`
- **Load the actual GDA data file from the data/ directory.** (1 connections) — `tests/unit/test_io.py`

## Relationships

- [[Txt Reader Round-trip]] (4 shared connections)
- [[Core Domain Init]] (3 shared connections)
- [[Concentration Helpers]] (3 shared connections)
- [[Concentration I/O Round-trip]] (3 shared connections)
- [[EnSight Reader]] (2 shared connections)
- [[BMG Reader]] (2 shared connections)
- [[Export Writers]] (2 shared connections)
- [[Jasco Reader]] (2 shared connections)
- [[Parameter Descriptions & Linear Fit]] (2 shared connections)
- [[Reader Registry Dispatch]] (1 shared connections)
- [[File Load & Channel Labels]] (1 shared connections)
- [[CSV Reader]] (1 shared connections)

## Source Files

- `core/io/__init__.py`
- `tests/unit/test_ensight_reader.py`
- `tests/unit/test_io.py`

## Audit Trail

- EXTRACTED: 47 (94%)
- INFERRED: 3 (6%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*