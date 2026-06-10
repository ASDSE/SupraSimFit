# App Launch & Main Window

> 17 nodes · cohesion 0.16

## Key Concepts

- **main_window.py** (15 connections) — `gui/main_window.py`
- **_SpinBoxWheelRedirect** (9 connections) — `gui/main_window.py`
- **update_dialog.py** (8 connections) — `gui/update_dialog.py`
- **launch()** (6 connections) — `gui/main_window.py`
- **update_check.py** (6 connections) — `gui/update_check.py`
- **_version.py** (6 connections) — `_version.py`
- **_app_icon_path()** (3 connections) — `gui/main_window.py`
- **run_app.py** (3 connections) — `run_app.py`
- **FittingMainWindow — thin shell managing tabbed fitting sessions.** (1 connections) — `gui/main_window.py`
- **Block non-focused spinboxes from swallowing wheel events.      Qt's event-filter** (1 connections) — `gui/main_window.py`
- **Locate the bundled app icon for both source runs and PyInstaller bundles.** (1 connections) — `gui/main_window.py`
- **Entry point — create the QApplication and launch the main window.** (1 connections) — `gui/main_window.py`
- **.eventFilter()** (1 connections) — `gui/main_window.py`
- **Background check for newer SupraSimFit releases on GitHub.  Queries the GitHub R** (1 connections) — `gui/update_check.py`
- **Dialog shown when a newer SupraSimFit release is available.  Displays release no** (1 connections) — `gui/update_dialog.py`
- **QObject** (1 connections)
- **Single source of truth for SupraSimFit's version and GitHub repo.  Everything th** (1 connections) — `_version.py`

## Relationships

- [[Update Download Worker]] (7 shared connections)
- [[Version Compare]] (3 shared connections)
- [[Toolbar & Update Worker]] (3 shared connections)
- [[FittingSession Export]] (2 shared connections)
- [[Main Window Session Mgmt]] (2 shared connections)
- [[Style Template Persistence]] (1 shared connections)
- [[Preferences & QSettings]] (1 shared connections)
- [[Plot Style Tests]] (1 shared connections)
- [[README Reference Params]] (1 shared connections)

## Source Files

- `_version.py`
- `gui/main_window.py`
- `gui/update_check.py`
- `gui/update_dialog.py`
- `run_app.py`

## Audit Trail

- EXTRACTED: 59 (91%)
- INFERRED: 6 (9%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*