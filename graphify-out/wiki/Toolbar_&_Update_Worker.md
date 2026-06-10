# Toolbar & Update Worker

> 9 nodes · cohesion 0.28

## Key Concepts

- **UpdateCheckWorker** (14 connections) — `gui/update_check.py`
- **._make_menu_button()** (5 connections) — `gui/main_window.py`
- **QToolButton** (5 connections) — `gui/main_window.py`
- **QMenu** (5 connections) — `gui/main_window.py`
- **._setup_toolbar()** (4 connections) — `gui/main_window.py`
- **QThread** (3 connections)
- **Create a toolbar button that pops a menu without the Qt auto-arrow.          The** (1 connections) — `gui/main_window.py`
- **Query GitHub ``/releases/latest`` for the configured repo.      Signals     ----** (1 connections) — `gui/update_check.py`
- **.run()** (1 connections) — `gui/update_check.py`

## Relationships

- [[Main Window Session Mgmt]] (4 shared connections)
- [[Update Download Worker]] (4 shared connections)
- [[App Launch & Main Window]] (3 shared connections)
- [[Update Check Flow]] (2 shared connections)
- [[FittingSession Export]] (2 shared connections)
- [[BaseAssay Interface]] (2 shared connections)
- [[Fit Config Panel]] (1 shared connections)
- [[Version Compare]] (1 shared connections)

## Source Files

- `gui/main_window.py`
- `gui/update_check.py`

## Audit Trail

- EXTRACTED: 25 (64%)
- INFERRED: 14 (36%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*