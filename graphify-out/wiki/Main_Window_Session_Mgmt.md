# Main Window Session Mgmt

> 21 nodes · cohesion 0.17

## Key Concepts

- **FittingMainWindow** (37 connections) — `gui/main_window.py`
- **.active_session()** (14 connections) — `gui/main_window.py`
- **FittingSession** (6 connections) — `gui/main_window.py`
- **._new_session()** (4 connections) — `gui/main_window.py`
- **._rename_tab()** (3 connections) — `gui/main_window.py`
- **.closeEvent()** (2 connections) — `gui/main_window.py`
- **._on_export()** (2 connections) — `gui/main_window.py`
- **._on_export_all()** (2 connections) — `gui/main_window.py`
- **._on_export_raw()** (2 connections) — `gui/main_window.py`
- **._on_export_txt()** (2 connections) — `gui/main_window.py`
- **._on_import()** (2 connections) — `gui/main_window.py`
- **._on_load()** (2 connections) — `gui/main_window.py`
- **._on_load_demo()** (2 connections) — `gui/main_window.py`
- **._on_load_style()** (2 connections) — `gui/main_window.py`
- **._on_run_fit()** (2 connections) — `gui/main_window.py`
- **._on_save_distributions_plot()** (2 connections) — `gui/main_window.py`
- **._on_save_plot()** (2 connections) — `gui/main_window.py`
- **._on_save_style()** (2 connections) — `gui/main_window.py`
- **Main application window: tab management + toolbar + menu routing.      All fitti** (1 connections) — `gui/main_window.py`
- **Block until any in-flight update check finishes before closing.          The sta** (1 connections) — `gui/main_window.py`
- **QMainWindow** (1 connections)

## Relationships

- [[Update Check Flow]] (11 shared connections)
- [[Toolbar & Update Worker]] (4 shared connections)
- [[Update Download Worker]] (3 shared connections)
- [[FittingSession Export]] (2 shared connections)
- [[App Launch & Main Window]] (2 shared connections)
- [[Plot Style Tests]] (1 shared connections)

## Source Files

- `gui/main_window.py`

## Audit Trail

- EXTRACTED: 87 (94%)
- INFERRED: 6 (6%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*