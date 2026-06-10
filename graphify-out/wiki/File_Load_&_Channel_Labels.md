# File Load & Channel Labels

> 17 nodes · cohesion 0.12

## Key Concepts

- **.load_file()** (8 connections) — `gui/widgets/data_panel.py`
- **._on_channel_changed()** (6 connections) — `gui/widgets/data_panel.py`
- **format_channel_label()** (5 connections) — `core/io/formats/ensight_reader.py`
- **._make_ms()** (5 connections) — `gui/widgets/data_panel.py`
- **._populate_channel_combo()** (5 connections) — `gui/widgets/data_panel.py`
- **MeasurementSet** (4 connections) — `gui/widgets/data_panel.py`
- **._slice_channel()** (4 connections) — `gui/widgets/data_panel.py`
- **_build_file_filter()** (3 connections) — `gui/widgets/data_panel.py`
- **.measurement_set()** (2 connections) — `gui/widgets/data_panel.py`
- **Any** (1 connections) — `core/io/formats/ensight_reader.py`
- **Build a human label for an EnSight channel: name + Ex/Em hints.      Used by the** (1 connections) — `core/io/formats/ensight_reader.py`
- **Load a measurement file, optionally bypassing the dialog.          The import pa** (1 connections) — `gui/widgets/data_panel.py`
- **Build a MeasurementSet from a single-channel frame, forwarding the         place** (1 connections) — `gui/widgets/data_panel.py`
- **Return the single-channel sub-frame for *channel*, attrs preserved.** (1 connections) — `gui/widgets/data_panel.py`
- **Fill the channel combo from the loaded frame; disable if ≤1 channel.** (1 connections) — `gui/widgets/data_panel.py`
- **Rebuild the MeasurementSet for the newly selected channel in-memory.          Th** (1 connections) — `gui/widgets/data_panel.py`
- **Build QFileDialog filter string from registered I/O readers.** (1 connections) — `gui/widgets/data_panel.py`

## Relationships

- [[EnSight Loading & Channels]] (10 shared connections)
- [[Concentration Helpers]] (2 shared connections)
- [[Core Domain Init]] (1 shared connections)
- [[MeasurementSet & FitResult]] (1 shared connections)
- [[Fit Config Panel]] (1 shared connections)
- [[load_measurements]] (1 shared connections)

## Source Files

- `core/io/formats/ensight_reader.py`
- `gui/widgets/data_panel.py`

## Audit Trail

- EXTRACTED: 48 (96%)
- INFERRED: 2 (4%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*