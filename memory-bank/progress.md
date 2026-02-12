# Project Progress

## Strategy Pivot (2026-01-30)

**MAJOR CHANGE**: Focus shifted exclusively to Core Fitting Logic refactor.
- GUI development: PAUSED (breakage acceptable)
- Public API work: POSTPONED (revert recent core/api.py)
- Full-plate fitting: **DELETE** (changed from LEGACY on 2026-02-02)

## Recent updates (2026-02-09)

### Phase 3: Testing — COMPLETE ✅ (All P1–P4)
- **62 tests total, all passing** (`uv run pytest -v`, ~10 min)
- **P1: Parameter recovery** (11 tests) — Ka recovery for DBA, GDA, IDA, DyeAlone
  - Signal coefficient tests removed (structural degeneracy — see below)
  - Signal reconstruction tests added instead (predict vs observed)
  - GDA needs 500 trials and g0=20µM for reliable convergence
  - RNG seeded (`np.random.seed(42)`) via autouse fixture for determinism
- **P2: Forward model math** (14 tests) — Linear, DBA, competitive model tests
- **P3: Fail-fast contracts** (23 tests) — Constructor validation for all assay types
- **P4: I/O round-trip** (14 tests) — TxtReader, TxtWriter, registry dispatch

### Key Finding: Signal Coefficient Degeneracy
In DBA and IDA, signal coefficients (I0, I_dye_free, I_dye_bound) form a
degenerate manifold due to mass conservation on the fixed species:
- IDA: `[D_free] = d0 - [HD]` → 3 params collapse to 2 DOFs (offset + contrast)
- DBA: `[H_free] = h0 - [HD]` → same collapse
- Only Ka (controls curve shape) is independently identifiable
- Tests use tight signal bounds (±20% of truth) to constrain the manifold
- GDA has weaker degeneracy but requires g0 >> Ka_dye⁻¹ for Ka_guest sensitivity

### Scientific Documentation (2026-02-09)
- Added Section 5 "Parameter Identifiability and Signal Coefficient Degeneracy" to `docs/scientific-summary.md`
- Covers: mathematical derivation, consequences table, 6 inspection steps, 4 mitigation strategies

## Recent updates (2026-02-03)

### Testing Strategy Formalized
- **Workflow**: `uv run pytest` (migrated from Conda to uv)
- **Tolerance**: 10% for clean synthetic, 20% for 5% Gaussian noise
- **Test fixtures**: Committed to `tests/data/` for reproducible edge cases
- **Priority categories**:
  - P1: Parameter recovery (fit synthetic, verify Ka)
  - P2: Forward model math (known inputs → expected outputs)
  - P3: Fail-fast contracts (missing params, NaN, negative K)
  - P4: I/O round-trip (write→read preserves data)
  - P5: Optimizer boundaries
  - P6: Integration (end-to-end with real data)

### Phase 2: Scorched Earth Cleanup — COMPLETE ✅
**Deleted:**
- `core/fitting/` — 11 files removed
- `core/io/` — ~15 files removed (old over-engineered system)
- `gui/interface_*.py` — 9 files removed

**Created (minimal I/O):**
```
core/io/
├── __init__.py      # Public API: load_measurements(), save_results()
├── base.py          # MeasurementReader, ResultWriter protocols
├── registry.py      # Format dispatch (explicit dict)
└── formats/
    ├── __init__.py
    └── txt.py       # TxtReader, TxtWriter (multi-replica aware)
```

**Verified:**
- All imports working
- Loaded GDA data: 72 rows, 3 replicas
- Result writer outputs proper tab-separated format

## Recent updates (2026-01-30)

### Phase 1 Implementation COMPLETE
- Reverted `core/api.py` and cleaned up `core/__init__.py` exports.
- Created `core/units.py` with shared pint UnitRegistry.
- Created `core/assays/registry.py` with AssayType enum, AssayMetadata, ASSAY_REGISTRY.
- Created `core/assays/base.py` with BaseAssay ABC.
- Created `core/models/equilibrium.py` with dba_signal, gda_signal, ida_signal.
- Created `core/models/linear.py` with linear_signal.
- Created `core/optimizer/multistart.py` with multi-start L-BFGS-B.
- Created `core/optimizer/filters.py` with RMSE/R² filtering and median aggregation.
- Created `core/optimizer/linear_fit.py` with linear regression.
- Created `core/pipeline/fit_pipeline.py` with fit_assay, FitConfig, FitResult.
- Created concrete assay classes: GDAAssay, IDAAssay, DBAAssay, DyeAloneAssay.
- Added `pint>=0.24` to requirements.txt.
- All imports verified working; DyeAlone linear fit functional test passed.

### Earlier (2026-01-30)
- Completed comprehensive analysis of all fitting modules.
- Designed new modular architecture with clear separation of concerns.
- Finalized Enum-Keyed Registry pattern for assay dispatch.

## Recent updates (2026-01-28)

- Started TASK001 by mapping GUI-to-core fitting entry points.
- Drafted initial public API wrappers in `core/api.py` (REVERTED on 2026-01-30).

## Recent updates (2026-01-26)

- Condensed the project brief; scientific background moved to docs/scientific-summary.md.
- Initialized task tracking for public API definition and I/O validation.

## High-level status

| Component | Status | Notes |
|-----------|--------|-------|
| Core fitting logic | ✅ COMPLETE | Phase 1 + Scientific Remediation done |
| Forward modeling | ✅ FIXED | 4-param fitting, unified naming |
| GUI | PAUSED | interface_*.py files deleted |
| I/O | ✅ REWRITTEN | Minimal Strategy pattern, .txt support |
| Public API | POSTPONED | core/api.py reverted |
| Pint integration | IMPLEMENTED | core/units.py with boundary stripping |
| Testing | ✅ P1-P4 COMPLETE | 62 tests, all passing (2026-02-09) |
| Scientific docs | ✅ UPDATED | Parameter identifiability section added |
| Legacy fitting | ✅ DELETED | core/fitting/ removed |

## What works now

- Running `python main.py` for Tkinter GUI.
- Fitting real assay datasets (GDA, IDA, DBA, DyeAlone).
- Generating plots and statistics.
- TXT file I/O for measurement sets.

## Architecture refactor plan

### Completed design work
- [x] Analyze all fitting modules for overlap
- [x] Design new directory structure (core/assays, models, optimizer, pipeline, io)
- [x] Define Enum-Keyed Registry pattern (AssayType, AssayMetadata, ASSAY_REGISTRY)
- [x] Plan pint integration (boundary stripping)
- [x] Create parameter/assay dependency matrix

### Implementation Phases (ALL COMPLETE)
- [x] Phase 1: Core modules (2026-01-30)
- [x] Phase 1.5: Scientific remediation (2026-01-31)
- [x] Phase 2: Scorched Earth cleanup + minimal I/O (2026-02-03)
- [x] Phase 3: Testing P1–P4 (2026-02-09)

### Remaining
- [ ] TASK004: Fix registry default bounds (informed by degeneracy analysis)
- [ ] P5: Optimizer boundary tests
- [ ] P6: End-to-end integration tests with real data
- [ ] DBA DtoH signal bug investigation

## Known gaps

- ~~CRITICAL: Assay wrappers fit 3 params instead of 4~~ — ✅ FIXED (2026-01-31)
- ~~CRITICAL: Naming inconsistency~~ — ✅ FIXED (2026-01-31)
- ~~Dangerous defaults~~ — ✅ FIXED (2026-01-31)
- **I/O layer needs complete rewrite** — ✅ DONE (minimal Strategy pattern).
- **Old core/fitting/*.py must be deleted** — ✅ DONE (Scorched Earth).
- **GUI interfaces must be deleted** — ✅ DONE (9 files removed).
- Default bounds for 4th signal parameter not yet defined (TASK004) — informed by degeneracy analysis.
- End-to-end tests with real data files not yet written (P6).
- Optimizer boundary tests not yet written (P5).
- DBA DtoH signal model: `I_dye_free` applied to `y_free` (free HOST) — possible naming/logic bug.
- Scratch diagnostic files (`scratch/test_diag*.py`) not yet cleaned up.

## Process notes

- Prefer clarity and simplicity over legacy compatibility.
- Accept temporary breakage during refactors.
- GUI breakage is explicitly acceptable.
- **Scorched Earth policy**: Delete superseded code immediately, don't comment out.
