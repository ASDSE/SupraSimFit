# EnSight Reader

> 27 nodes · cohesion 0.14

## Key Concepts

- **EnsightReader** (34 connections) — `core/io/formats/ensight_reader.py`
- **TestParsing** (12 connections) — `tests/unit/test_ensight_reader.py`
- **test_ensight_reader.py** (8 connections) — `tests/unit/test_ensight_reader.py`
- **_minimal_ensight()** (8 connections) — `tests/unit/test_ensight_reader.py`
- **_read_legacy_var_signal()** (5 connections) — `tests/unit/test_ensight_reader.py`
- **.test_real_file_golden_row_match()** (4 connections) — `tests/unit/test_ensight_reader.py`
- **.test_trailing_section_does_not_bleed_into_details()** (4 connections) — `tests/unit/test_ensight_reader.py`
- **TestSniffing** (4 connections) — `tests/unit/test_ensight_reader.py`
- **TestDispatch** (3 connections) — `tests/unit/test_ensight_reader.py`
- **.test_minimal_multi_channel()** (3 connections) — `tests/unit/test_ensight_reader.py`
- **.test_minimal_single_channel()** (3 connections) — `tests/unit/test_ensight_reader.py`
- **.test_non_sequential_columns_raises()** (3 connections) — `tests/unit/test_ensight_reader.py`
- **.test_out_of_sequence_rows_raises()** (3 connections) — `tests/unit/test_ensight_reader.py`
- **ndarray** (2 connections) — `tests/unit/test_ensight_reader.py`
- **Path** (2 connections) — `tests/unit/test_ensight_reader.py`
- **.test_metadata_carries_ex_em_per_channel()** (2 connections) — `tests/unit/test_ensight_reader.py`
- **.test_no_result_blocks_raises()** (2 connections) — `tests/unit/test_ensight_reader.py`
- **.test_placeholder_concentrations_and_flag()** (2 connections) — `tests/unit/test_ensight_reader.py`
- **.test_three_channels_detected()** (2 connections) — `tests/unit/test_ensight_reader.py`
- **.test_can_read_with_bom()** (2 connections) — `tests/unit/test_ensight_reader.py`
- **Reader for PerkinElmer EnSight CSV_PLATE exports.** (1 connections) — `core/io/formats/ensight_reader.py`
- **Tests for the PerkinElmer EnSight CSV plate-reader.  Real fixtures are europium-** (1 connections) — `tests/unit/test_ensight_reader.py`
- **Row A of the FL channel must match the legacy txt row-for-row.** (1 connections) — `tests/unit/test_ensight_reader.py`
- **`Post Processing Sequence` rows must not parse into the last         `Details of** (1 connections) — `tests/unit/test_ensight_reader.py`
- **Parse the legacy var/signal txt into an n_replicas × n_points array.** (1 connections) — `tests/unit/test_ensight_reader.py`
- *... and 2 more nodes in this community*

## Relationships

- [[Plate Reader Format]] (8 shared connections)
- [[BMG Workbook Parsing]] (5 shared connections)
- [[load_measurements]] (2 shared connections)
- [[Core Domain Init]] (1 shared connections)
- [[Content-Sniffing Registry]] (1 shared connections)
- [[Reader Registry Dispatch]] (1 shared connections)
- [[Jasco Reader]] (1 shared connections)

## Source Files

- `core/io/formats/ensight_reader.py`
- `tests/unit/test_ensight_reader.py`

## Audit Trail

- EXTRACTED: 101 (88%)
- INFERRED: 14 (12%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*