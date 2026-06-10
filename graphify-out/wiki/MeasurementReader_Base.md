# MeasurementReader Base

> 21 nodes · cohesion 0.12

## Key Concepts

- **registry.py** (8 connections) — `core/io/registry.py`
- **MeasurementReader** (7 connections) — `core/io/base.py`
- **ResultWriter** (7 connections) — `core/io/base.py`
- **get_writer()** (7 connections) — `core/io/registry.py`
- **register_writer()** (5 connections) — `core/io/registry.py`
- **.read()** (4 connections) — `core/io/base.py`
- **base.py** (3 connections) — `core/io/base.py`
- **.write()** (3 connections) — `core/io/base.py`
- **Protocol** (3 connections)
- **Path** (2 connections) — `core/io/base.py`
- **Path** (2 connections) — `core/io/registry.py`
- **ResultWriter** (2 connections) — `core/io/registry.py`
- **DataFrame** (1 connections) — `core/io/base.py`
- **Protocol definitions for I/O readers and writers.  This module defines the inter** (1 connections) — `core/io/base.py`
- **Protocol for reading measurement data files.      Implementations must define:** (1 connections) — `core/io/base.py`
- **Read measurement data from file.          Parameters         ----------** (1 connections) — `core/io/base.py`
- **Protocol for writing fit results.      Implementations must define:     - extens** (1 connections) — `core/io/base.py`
- **Write fit results to file.          Parameters         ----------         result** (1 connections) — `core/io/base.py`
- **Format registry for I/O dispatch.  Each extension can have one or more registere** (1 connections) — `core/io/registry.py`
- **Register a writer class for its supported extensions.** (1 connections) — `core/io/registry.py`
- **Get a writer instance for the given file path.** (1 connections) — `core/io/registry.py`

## Relationships

- [[Reader Registry Dispatch]] (5 shared connections)
- [[Core Domain Init]] (3 shared connections)
- [[DBA Datasets & Txt Reader]] (1 shared connections)
- [[Data Processing & Preprocessing]] (1 shared connections)

## Source Files

- `core/io/base.py`
- `core/io/registry.py`

## Audit Trail

- EXTRACTED: 62 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*