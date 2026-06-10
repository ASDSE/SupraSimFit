# Plate Reader Format

> 18 nodes · cohesion 0.12

## Key Concepts

- **.read()** (10 connections) — `core/io/formats/ensight_reader.py`
- **._parse_grid()** (5 connections) — `core/io/formats/ensight_reader.py`
- **Path** (3 connections) — `core/io/formats/ensight_reader.py`
- **._block_details()** (3 connections) — `core/io/formats/ensight_reader.py`
- **.can_read()** (3 connections) — `core/io/formats/ensight_reader.py`
- **._find_result_blocks()** (3 connections) — `core/io/formats/ensight_reader.py`
- **._parse_key_value_section()** (3 connections) — `core/io/formats/ensight_reader.py`
- **._parse_top_header()** (3 connections) — `core/io/formats/ensight_reader.py`
- **._expected_plate_dims()** (2 connections) — `core/io/formats/ensight_reader.py`
- **DataFrame** (1 connections) — `core/io/formats/ensight_reader.py`
- **ndarray** (1 connections) — `core/io/formats/ensight_reader.py`
- **Capture the few lines above the first 'Result for ...' block.** (1 connections) — `core/io/formats/ensight_reader.py`
- **Return list of (block name, line index) for every 'Result for' line.** (1 connections) — `core/io/formats/ensight_reader.py`
- **Locate and parse the plate grid that follows a 'Result for' line.** (1 connections) — `core/io/formats/ensight_reader.py`
- **Extract a flat key/value dict from one of the trailing sections.          Sectio** (1 connections) — `core/io/formats/ensight_reader.py`
- **Return the subset of details belonging to one Operation block.          Walks ``** (1 connections) — `core/io/formats/ensight_reader.py`
- **Return True if the first non-empty line is the EnSight signature.** (1 connections) — `core/io/formats/ensight_reader.py`
- **Parse an EnSight CSV into a long-format DataFrame.          Returned columns: ``** (1 connections) — `core/io/formats/ensight_reader.py`

## Relationships

- [[EnSight Reader]] (8 shared connections)

## Source Files

- `core/io/formats/ensight_reader.py`

## Audit Trail

- EXTRACTED: 44 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*