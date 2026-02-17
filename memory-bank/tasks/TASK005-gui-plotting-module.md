# TASK005 - GUI Plotting Module

**Status:** Completed
**Added:** 2026-02-17
**Updated:** 2026-02-17

## Original Request
Implement a `gui/plotting/` subpackage using PyQtGraph as the rendering engine. Purely additive — no existing files modified.

## Thought Process

The core layer already had `prepare_plot_data()` returning a framework-agnostic dict of arrays. The GUI needed a rendering layer. PyQtGraph chosen because it is fast, native Qt, and has built-in interactivity and a `ParameterTree` for user-configurable styling.

Key design choices:
- `update_plot()` always clears and redraws (data is small: 20–100 pts; simplicity wins over incremental updates)
- `apply_style()` mutates items in-place (snappy response to ParameterTree keypresses)
- `PlotWidget` has no dependency on `ASSAY_REGISTRY` — caller passes labels as plain strings
- Module-level helpers `_lookup_assay_type()` and `_fmt_value()` kept in `fit_summary_widget.py` so they can be tested without a QApplication

## Implementation Plan
- [x] Add `pyqtgraph` and `pyqt6` via `uv add`
- [x] `gui/plotting/colors.py` — palettes + `rgba()` helper
- [x] `gui/plotting/plot_style.py` — `DEFAULT_STYLE`, `PlotStyleWidget`, `line_style_to_qt()`
- [x] `gui/plotting/plot_widget.py` — `PlotWidget` consuming `prepare_plot_data()` output
- [x] `gui/plotting/fit_summary_widget.py` — `FitSummaryWidget` for `FitResult` display
- [x] `gui/plotting/__init__.py` — public re-exports
- [x] `tests/unit/gui/` — 37 tests across 5 test files
- [x] `tests/conftest.py` — `minimal_plot_data` fixture added

## Progress Tracking

**Overall Status:** Completed - 100%

### Subtasks
| ID | Description | Status | Updated | Notes |
|----|-------------|--------|---------|-------|
| 5.1 | Add pyqtgraph + pyqt6 dependencies | Complete | 2026-02-17 | pyqtgraph==0.14.0, pyqt6==6.10.2 |
| 5.2 | Create colors.py | Complete | 2026-02-17 | 8-color REPLICA_PALETTE, rgba() |
| 5.3 | Create plot_style.py | Complete | 2026-02-17 | ParameterTree, style_changed signal |
| 5.4 | Create plot_widget.py | Complete | 2026-02-17 | ScatterPlotItem × N, PlotCurveItem, ErrorBarItem |
| 5.5 | Create fit_summary_widget.py | Complete | 2026-02-17 | QTableWidget + QFormLayout |
| 5.6 | Create __init__.py | Complete | 2026-02-17 | |
| 5.7 | Tests: colors + fit summary logic (no QApp) | Complete | 2026-02-17 | 25 tests |
| 5.8 | Tests: widget tests (QApp) | Complete | 2026-02-17 | 12 tests |
| 5.9 | Add minimal_plot_data fixture to conftest.py | Complete | 2026-02-17 | |

## Progress Log
### 2026-02-17
- Implemented all 5 module files and 5 test files in a single session.
- 37 new tests; 251 tests total, all passing.
- `minimal_plot_data` fixture added to `tests/conftest.py`.
- No existing files modified (purely additive).

## Module Reference

### Files created
```
gui/plotting/
├── __init__.py              — re-exports PlotWidget, FitSummaryWidget, PlotStyleWidget
├── colors.py                — REPLICA_PALETTE (8), FIT_PALETTE, constants, rgba()
├── plot_style.py            — DEFAULT_STYLE, PlotStyleWidget, line_style_to_qt()
├── plot_widget.py           — PlotWidget (pg.PlotWidget wrapper)
└── fit_summary_widget.py    — FitSummaryWidget, _lookup_assay_type(), _fmt_value()

tests/unit/gui/
├── __init__.py
├── test_colors.py           — 8 tests, no QApp
├── test_fit_summary_logic.py — 17 tests, no QApp
├── test_plot_widget.py      — 6 tests, QApp
├── test_fit_summary_widget.py — 4 tests, QApp
└── test_style_roundtrip.py  — 2 tests, QApp
```

### PyQtGraph item mapping
| Data series | pg Item | Notes |
|---|---|---|
| Active replicas | `ScatterPlotItem` × N | One per replica, REPLICA_PALETTE cycling |
| Dropped replicas | `ScatterPlotItem` × 1 | All in single grey item |
| Average line | `PlotCurveItem` | Mean across active replicas |
| Error bars | `ErrorBarItem` | ± std at each concentration |
| Fit curves | `PlotCurveItem` × M | One per fit, FIT_PALETTE cycling |
