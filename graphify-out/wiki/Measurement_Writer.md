# Measurement Writer

> 12 nodes · cohesion 0.24

## Key Concepts

- **write_measurements_txt()** (12 connections) — `core/io/formats/measurement_writer.py`
- **write_measurements_csv()** (10 connections) — `core/io/formats/measurement_writer.py`
- **measurement_writer.py** (8 connections) — `core/io/formats/measurement_writer.py`
- **.export_raw_data()** (5 connections) — `gui/fitting_session.py`
- **_iter_points()** (4 connections) — `core/io/formats/measurement_writer.py`
- **Path** (3 connections) — `core/io/formats/measurement_writer.py`
- **_header_comment()** (2 connections) — `core/io/formats/measurement_writer.py`
- **Writers that serialise a :class:`MeasurementSet` back to disk.  These produce fi** (1 connections) — `core/io/formats/measurement_writer.py`
- **Yield ``(replica_idx, concentration, signal)`` tuples for every point.      Incl** (1 connections) — `core/io/formats/measurement_writer.py`
- **Write *ms* to a tab-separated ``.txt`` file with repeated headers.      Output r** (1 connections) — `core/io/formats/measurement_writer.py`
- **Write *ms* to a long-format ``.csv`` file.      Output round-trips through :clas** (1 connections) — `core/io/formats/measurement_writer.py`
- **Export the currently loaded raw measurements to TXT or CSV.          The output** (1 connections) — `gui/fitting_session.py`

## Relationships

- [[Batch Artefact Export]] (4 shared connections)
- [[MeasurementSet & FitResult]] (3 shared connections)
- [[Style Template Persistence]] (2 shared connections)
- [[BMG Reader]] (2 shared connections)
- [[Export Writers]] (2 shared connections)
- [[FittingSession Export]] (2 shared connections)
- [[DBA Datasets & Txt Reader]] (1 shared connections)
- [[Concentration I/O Round-trip]] (1 shared connections)

## Source Files

- `core/io/formats/measurement_writer.py`
- `gui/fitting_session.py`

## Audit Trail

- EXTRACTED: 48 (98%)
- INFERRED: 1 (2%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*