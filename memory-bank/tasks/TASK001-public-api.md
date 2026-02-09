# TASK001 - Define public API surface

**Status:** Paused  
**Added:** 2026-01-26  
**Updated:** 2026-01-30

## Original Request
Start with public API definition for the toolkit.

## Thought Process
The codebase is large and organically grown. A small, stable API needs to be inferred from common workflows and current usage. Begin by surveying how data is loaded, fit routines are invoked, and results are exported. Then draft minimal function signatures around those core operations and validate them with light tests or scripts before refactoring internals.

**2026-01-30 UPDATE**: Strategy pivot - this task is now PAUSED. The core fitting logic needs to be refactored first before a stable public API can be defined. The initial API work (core/api.py) should be reverted.

## Implementation Plan
- Survey the codebase to identify core operations and recurring entry points.
- Identify candidate public types (e.g., `MeasurementSet`, `FitResult`) and the minimum data needed for workflows.
- Draft minimal API functions for I/O and fitting (names/signatures may evolve).
- Add a small test or example for each public API function.
- Document the API in the Memory Bank and README if needed.

## Progress Tracking

**Overall Status:** Paused - 50% (work to be reverted)

### Subtasks
| ID | Description | Status | Updated | Notes |
|----|-------------|--------|---------|-------|
| 1.1 | Survey current I/O and fitting entry points | Complete | 2026-01-28 | Mapped GUI → core fitting entry points and core I/O registry save/load. |
| 1.2 | Draft API function signatures and types | Complete (TO REVERT) | 2026-01-28 | Drafted `core/api.py` - now to be reverted per strategy pivot. |
| 1.3 | Create minimal tests/examples for API | Paused | 2026-01-30 | Deferred until after core refactor. |
| 1.4 | Document API decisions | Paused | 2026-01-30 | Deferred until after core refactor. |

## Progress Log
### 2026-01-26
- Task created and queued for execution.

### 2026-01-28
- Surveyed current fitting entry points and GUI wiring.
- Identified public I/O entry points and data object factories.
- Drafted initial public API wrappers in core/api.py.
- Exported API from core/__init__.py for stable imports.

### 2026-01-30
- **STRATEGY PIVOT**: Task paused.
- User decided to focus solely on Core Fitting Logic refactor.
- GUI development paused (breakage acceptable).
- API work postponed until core refactor is complete.
- core/api.py and API exports from core/__init__.py should be reverted.
- New task TASK003 created for core fitting refactor.

## Entry points observed (reference for future)
- GUI → fitting
  - gui/interface_GDA_fitting.py calls `run_gda_fitting()` in core/fitting/gda.py.
  - gui/interface_IDA_fitting.py calls `run_ida_fitting()` in core/fitting/ida.py.
  - gui/interface_DBA_dye_to_host_fitting.py calls `run_dba_dye_to_host_fitting()` in core/fitting/dba_dye_to_host.py.
  - gui/interface_DBA_host_to_dye_fitting.py calls `run_dba_host_to_dye_fitting()` in core/fitting/dba_host_to_dye.py.
  - gui/interface_DyeAlone_fitting.py uses `DyeAloneFittingAlgorithm.fit()` in core/fitting/dye_alone.py.
  - gui/interface_full_plate_fitting.py calls `run_full_plate_fit()` in core/fitting/full_plate_fit.py.
- Core I/O
  - Public entry points: `save()` and `load()` in core/io/registry.py.
  - Data objects: `MeasurementSet` in core/io/measurement_set.py and `FitResult` in core/io/fit_result.py.
