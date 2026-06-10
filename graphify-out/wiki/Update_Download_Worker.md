# Update Download Worker

> 24 nodes · cohesion 0.10

## Key Concepts

- **UpdateAvailableDialog** (19 connections) — `gui/update_dialog.py`
- **DownloadWorker** (13 connections) — `gui/download_worker.py`
- **.__init__()** (5 connections) — `gui/update_dialog.py`
- **_pick_asset()** (4 connections) — `gui/update_dialog.py`
- **download_worker.py** (3 connections) — `gui/download_worker.py`
- **_os_label()** (3 connections) — `gui/update_dialog.py`
- **Any** (3 connections) — `gui/update_dialog.py`
- **QDialog** (3 connections)
- **.cancel()** (2 connections) — `gui/download_worker.py`
- **.__init__()** (2 connections) — `gui/download_worker.py`
- **.closeEvent()** (2 connections) — `gui/update_dialog.py`
- **._on_download_error()** (2 connections) — `gui/update_dialog.py`
- **._start_download()** (2 connections) — `gui/update_dialog.py`
- **.run()** (1 connections) — `gui/download_worker.py`
- **Path** (1 connections) — `gui/download_worker.py`
- **Background download worker — streams a URL to a local file with progress.  Used** (1 connections) — `gui/download_worker.py`
- **Stream a URL to a local path, emitting progress in 64 KB chunks.      Signals** (1 connections) — `gui/download_worker.py`
- **Request cooperative cancellation.          Safe to call from the GUI thread. The** (1 connections) — `gui/download_worker.py`
- **Cancel and join an in-flight download before the dialog closes.          Closing** (1 connections) — `gui/update_dialog.py`
- **Return the asset whose name matches the current OS, or None.** (1 connections) — `gui/update_dialog.py`
- **Show release notes; let the user download or visit GitHub.** (1 connections) — `gui/update_dialog.py`
- **._on_download_finished()** (1 connections) — `gui/update_dialog.py`
- **._on_progress()** (1 connections) — `gui/update_dialog.py`
- **_pick_asset** (1 connections) — `gui/update_dialog.py`

## Relationships

- [[App Launch & Main Window]] (7 shared connections)
- [[Toolbar & Update Worker]] (4 shared connections)
- [[Main Window Session Mgmt]] (3 shared connections)
- [[BaseAssay Interface]] (1 shared connections)
- [[FittingSession Export]] (1 shared connections)
- [[Update Check Flow]] (1 shared connections)
- [[Checkbox Grid UI Helpers]] (1 shared connections)
- [[Export Multiple Dialog]] (1 shared connections)
- [[Save Distributions Dialog]] (1 shared connections)

## Source Files

- `gui/download_worker.py`
- `gui/update_dialog.py`

## Audit Trail

- EXTRACTED: 62 (84%)
- INFERRED: 12 (16%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*