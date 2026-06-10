# Batch Artefact Export

> 18 nodes · cohesion 0.20

## Key Concepts

- **ExportableArtefact** (19 connections) — `gui/session.py`
- **session.py** (18 connections) — `gui/session.py`
- **export_multiple_dialog.py** (11 connections) — `gui/dialogs/export_multiple_dialog.py`
- **export_batch()** (9 connections) — `gui/session.py`
- **build_artefacts()** (8 connections) — `gui/session.py`
- **test_export_multiple.py** (7 connections) — `tests/unit/test_export_multiple.py`
- **test_export_batch_collects_exceptions_and_continues()** (6 connections) — `tests/unit/test_export_multiple.py`
- **_Row** (4 connections) — `gui/dialogs/export_multiple_dialog.py`
- **Exception** (4 connections) — `gui/session.py`
- **Path** (2 connections) — `tests/unit/test_export_multiple.py`
- **_raise()** (2 connections) — `tests/unit/test_export_multiple.py`
- **_write_text()** (2 connections) — `tests/unit/test_export_multiple.py`
- **Consolidated multi-artefact export dialog.  Lets the user pick which artefacts t** (1 connections) — `gui/dialogs/export_multiple_dialog.py`
- **Session-level helpers: JSON export/import of fit results, plot image export.** (1 connections) — `gui/session.py`
- **One thing the user can export in a batch.      Attributes     ----------     key** (1 connections) — `gui/session.py`
- **Build the list of artefacts exportable from a FittingSession.      Preconditions** (1 connections) — `gui/session.py`
- **Run a batch of artefact writers and report per-item outcomes.      Returns a lis** (1 connections) — `gui/session.py`
- **Tests for the batch-export helpers in gui.session (no Qt required).** (1 connections) — `tests/unit/test_export_multiple.py`

## Relationships

- [[Export Multiple Dialog]] (9 shared connections)
- [[Style Template Persistence]] (8 shared connections)
- [[FittingSession Export]] (5 shared connections)
- [[Assay Base & Registry Metadata]] (4 shared connections)
- [[Measurement Writer]] (4 shared connections)
- [[MeasurementSet & FitResult]] (3 shared connections)
- [[Preferences & QSettings]] (2 shared connections)
- [[Export Writers]] (2 shared connections)
- [[Label Formatting]] (1 shared connections)

## Source Files

- `gui/dialogs/export_multiple_dialog.py`
- `gui/session.py`
- `tests/unit/test_export_multiple.py`

## Audit Trail

- EXTRACTED: 82 (84%)
- INFERRED: 16 (16%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*