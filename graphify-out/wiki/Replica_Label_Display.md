# Replica Label Display

> 23 nodes · cohesion 0.13

## Key Concepts

- **ReplicaPanel** (21 connections) — `gui/widgets/replica_panel.py`
- **_display_label()** (11 connections) — `gui/widgets/replica_panel.py`
- **._rebuild()** (8 connections) — `gui/widgets/replica_panel.py`
- **replica_panel.py** (7 connections) — `gui/widgets/replica_panel.py`
- **.set_measurement_set()** (5 connections) — `gui/widgets/replica_panel.py`
- **.clear()** (4 connections) — `gui/widgets/replica_panel.py`
- **test_replica_labels.py** (3 connections) — `tests/unit/gui/test_replica_labels.py`
- **TestDisplayLabel** (3 connections) — `tests/unit/gui/test_replica_labels.py`
- **MeasurementSet** (3 connections) — `gui/widgets/replica_panel.py`
- **._on_toggled()** (3 connections) — `gui/widgets/replica_panel.py`
- **.refresh()** (3 connections) — `gui/widgets/replica_panel.py`
- **.reset_all()** (3 connections) — `gui/widgets/replica_panel.py`
- **._setup_ui()** (3 connections) — `gui/widgets/replica_panel.py`
- **.test_double_letter_starts_at_26()** (2 connections) — `tests/unit/gui/test_replica_labels.py`
- **.test_single_letter_range()** (2 connections) — `tests/unit/gui/test_replica_labels.py`
- **.__init__()** (2 connections) — `gui/widgets/replica_panel.py`
- **Tests for _display_label() base-26 replica labelling.** (1 connections) — `tests/unit/gui/test_replica_labels.py`
- **ReplicaPanel — per-replica activation checkboxes.** (1 connections) — `gui/widgets/replica_panel.py`
- **Rebuild the checkbox grid from current MeasurementSet state.** (1 connections) — `gui/widgets/replica_panel.py`
- **Map a zero-based replica index to an A–Z display label.      For indices 0–25 re** (1 connections) — `gui/widgets/replica_panel.py`
- **Show one checkbox per replica and allow toggling active/inactive state.      Aut** (1 connections) — `gui/widgets/replica_panel.py`
- **Populate checkboxes from MeasurementSet replica IDs.** (1 connections) — `gui/widgets/replica_panel.py`
- **Re-read active states from the MeasurementSet (after preprocessing).** (1 connections) — `gui/widgets/replica_panel.py`

## Relationships

- [[Label Formatting]] (4 shared connections)
- [[Checkbox Grid UI Helpers]] (4 shared connections)
- [[MeasurementSet & FitResult]] (3 shared connections)
- [[Fit Config Panel]] (3 shared connections)
- [[Distributions Export Config]] (3 shared connections)
- [[Distribution Plot Widget]] (1 shared connections)
- [[Plot Colors & Palette]] (1 shared connections)
- [[Style Template Persistence]] (1 shared connections)
- [[FittingSession Export]] (1 shared connections)
- [[Preprocessing Panel]] (1 shared connections)

## Source Files

- `gui/widgets/replica_panel.py`
- `tests/unit/gui/test_replica_labels.py`

## Audit Trail

- EXTRACTED: 78 (87%)
- INFERRED: 12 (13%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*