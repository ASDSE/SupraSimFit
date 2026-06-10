# Update Check Flow

> 13 nodes · cohesion 0.19

## Key Concepts

- **.__init__()** (8 connections) — `gui/main_window.py`
- **._run_update_check()** (7 connections) — `gui/main_window.py`
- **._on_update_check_done()** (6 connections) — `gui/main_window.py`
- **._discard_update_worker()** (4 connections) — `gui/main_window.py`
- **._set_title()** (4 connections) — `gui/main_window.py`
- **._setup_menus()** (4 connections) — `gui/main_window.py`
- **._on_update_check_error()** (3 connections) — `gui/main_window.py`
- **._close_tab()** (2 connections) — `gui/main_window.py`
- **._setup_statusbar()** (2 connections) — `gui/main_window.py`
- **._setup_tabs()** (2 connections) — `gui/main_window.py`
- **Set the window title to ``SupraSimFit <version> [suffix]``.          Called once** (1 connections) — `gui/main_window.py`
- **Spawn an :class:`UpdateCheckWorker`.          Parameters         ----------** (1 connections) — `gui/main_window.py`
- **Clear the worker reference and schedule the QObject for deletion.          Must** (1 connections) — `gui/main_window.py`

## Relationships

- [[Main Window Session Mgmt]] (11 shared connections)
- [[Toolbar & Update Worker]] (2 shared connections)
- [[Version Compare]] (1 shared connections)
- [[Update Download Worker]] (1 shared connections)

## Source Files

- `gui/main_window.py`

## Audit Trail

- EXTRACTED: 45 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*