# TASK003 - Core fitting logic refactor

**Status:** In Progress  
**Added:** 2026-01-30  
**Updated:** 2026-02-09

## Original Request
Restructure the Core Models and Fitting Logic with a modular architecture. GUI development is paused (breakage acceptable). Full-plate fitting kept as legacy. Public API work postponed.

## Thought Process

### Problem Analysis (2026-01-30)
Analyzed all fitting modules and found massive code duplication:
- gda.py, ida.py, dba_dye_to_host.py, dba_host_to_dye.py all follow the same pattern:
  1. Load bounds from GUI fields
  2. Unit conversion (µM → M)
  3. Load replicas from text files
  4. Multi-start L-BFGS-B optimization
  5. Filter by RMSE/R² threshold
  6. Compute median + MAD
  7. Plot results
  8. Export to text file
- dye_alone.py is simpler (linear regression) but still follows similar I/O patterns.

### Architecture Decision
New modular structure with clear separation of concerns:
- **Assays**: Data containers + forward model reference
- **Models**: Pure math functions (unit-free)
- **Optimizer**: Stateless fitting engine
- **Pipeline**: Orchestration layer
- **I/O**: Decoupled readers/writers

### Dispatch Pattern Decision
Chose **Enum-Keyed Registry Pattern**:
- `AssayType` enum defines what assays exist
- `AssayMetadata` frozen dataclass holds labels, parameter keys
- `ASSAY_REGISTRY` dict maps `AssayType -> AssayMetadata`
- Simple, explicit, type-safe, easy to extend

### Pint Integration Strategy
**Boundary stripping** approach:
- Internal: concentrations as `pint.Quantity`
- Optimizer receives `.magnitude` (plain floats)
- Plotter receives `.magnitude` arrays
- I/O writes magnitude + unit string metadata

## Implementation Plan
1. Create core/units.py (pint UnitRegistry)
2. Create core/assays/registry.py (AssayType, AssayMetadata, ASSAY_REGISTRY)
3. Create core/assays/base.py (BaseAssay ABC)
4. Create core/models/equilibrium.py (DBA, GDA, IDA forward models)
5. Create core/models/linear.py (dye-alone model)
6. Create core/optimizer/multistart.py (L-BFGS-B wrapper)
7. Create core/optimizer/linear_fit.py (linear regression)
8. Create core/optimizer/filters.py (RMSE/R² filtering, median aggregation)
9. Create core/pipeline/fit_pipeline.py (FitPipeline.run())
10. Create core/assays/gda.py (GDAAssay)
11. Create core/assays/ida.py (IDAAssay)
12. Create core/assays/dba.py (DBAAssay with HtoD/DtoH modes)
13. Create core/assays/dye_alone.py (DyeAloneAssay)
14. Update core/io to work with new assay structure
15. Delete/archive old fitting modules
16. Revert core/api.py (from TASK001)

## Progress Tracking

**Overall Status:** In Progress - 98% (P1–P4 tests complete, P5/P6 remaining)

### Subtasks
| ID | Description | Status | Updated | Notes |
|----|-------------|--------|---------|-------|
| 3.1 | Analyze existing fitting modules | Complete | 2026-01-30 | Identified duplication and common patterns |
| 3.2 | Design new directory structure | Complete | 2026-01-30 | Documented in systemPatterns.md |
| 3.3 | Finalize dispatch pattern | Complete | 2026-01-30 | Enum-Keyed Registry chosen |
| 3.4 | Plan pint integration | Complete | 2026-01-30 | Boundary stripping strategy |
| 3.5 | Create parameter/assay matrix | Complete | 2026-01-30 | Documented in systemPatterns.md |
| 3.6 | Create core/units.py | Complete | 2026-01-30 | ureg, Q_, strip_units(), ensure_quantity() |
| 3.7 | Create core/assays/registry.py | Complete | 2026-01-30 | AssayType enum, AssayMetadata, ASSAY_REGISTRY |
| 3.8 | Create core/assays/base.py | Complete | 2026-01-30 | BaseAssay ABC with forward_model(), residuals() |
| 3.9 | Create core/models/*.py | Complete | 2026-01-30 | equilibrium.py + linear.py |
| 3.10 | Create core/optimizer/*.py | Complete | 2026-01-30 | multistart.py + filters.py + linear_fit.py |
| 3.11 | Create core/pipeline/*.py | Complete | 2026-01-30 | fit_pipeline.py with FitConfig, FitResult |
| 3.12 | Create individual assay classes | Complete | 2026-01-30 | GDAAssay, IDAAssay, DBAAssay, DyeAloneAssay |
| 3.13 | Revert core/api.py | Complete | 2026-01-30 | Deleted file, cleaned core/__init__.py |
| 3.14 | **Scientific review vs forward_model.py** | Complete | 2026-01-31 | Found critical bugs |
| 3.15 | **Fix registry.py: 4 params + unified naming** | Complete | 2026-01-31 | Ka_dye, Ka_guest, I_dye_free, I_dye_bound |
| 3.16 | **Fix equilibrium.py: rename K_D→Ka_dye, etc** | Complete | 2026-01-31 | Updated function signatures + docstrings |
| 3.17 | **Fix gda.py: 4-param fitting** | Complete | 2026-01-31 | Removed I_HD=0.0, dye as titrant |
| 3.18 | **Fix ida.py: 4-param + rename K_I→Ka_guest** | Complete | 2026-01-31 | Removed I_HD=0.0, guest as titrant |
| 3.19 | **Fix dba.py: 4-param fitting** | Complete | 2026-01-31 | Removed I_D=0.0, None defaults |
| 3.20 | **Remove dangerous defaults** | Complete | 2026-01-31 | All assays use None + __post_init__ |
| 3.21 | **Update legacy forward_model.py naming** | Complete | 2026-01-31 | Aligned Kd→Ka_dye, Kg→Ka_guest |
| 3.22 | **Delete core/fitting/ entirely** | Complete | 2026-02-03 | 11 files removed |
| 3.23 | **Delete core/io/ entirely** | Complete | 2026-02-03 | ~15 files removed |
| 3.24 | **Delete gui/interface_*.py** | Complete | 2026-02-03 | 9 files removed |
| 3.25 | **Create new core/io/ (minimal)** | Complete | 2026-02-03 | Strategy pattern, .txt format |
| 3.26 | **Verify imports after cleanup** | Complete | 2026-02-03 | All imports working, data loads correctly |
| 3.27 | **Formalize testing strategy** | Complete | 2026-02-03 | Tolerance 10%/20%, pytest workflow |
| 3.28 | Create tests/conftest.py | Complete | 2026-02-06 | Synthetic data generators, RNG seed, tight bounds |
| 3.29 | Implement P1: Parameter recovery tests | Complete | 2026-02-09 | 11 tests: Ka recovery + signal reconstruction |
| 3.30 | Implement P2-P4: Core test categories | Complete | 2026-02-06 | P2 (14), P3 (23), P4 (14) = 51 tests |
| 3.31 | Diagnose signal coefficient degeneracy | Complete | 2026-02-09 | Root cause: mass conservation collapses 3 params to 2 DOFs |
| 3.32 | Document parameter identifiability | Complete | 2026-02-09 | docs/scientific-summary.md Section 5 |
| 3.33 | Implement P5: Optimizer boundary tests | Not Started | 2026-02-09 | |
| 3.34 | Implement P6: End-to-end integration tests | Not Started | 2026-02-09 | |

## Progress Log
### 2026-02-09 (Phase 3: Testing COMPLETE + Scientific Documentation)
- **All 62 tests passing** (`uv run pytest -v`, ~10 min):
  - P1: 11 tests (Ka recovery + signal reconstruction)
  - P2: 14 tests (forward model math)
  - P3: 23 tests (fail-fast contracts)
  - P4: 14 tests (I/O round-trip)
- **Signal coefficient degeneracy diagnosed**:
  - Root cause: mass conservation on fixed species collapses 3 signal params to 2 DOFs
  - Ka remains identifiable (controls curve shape via equilibrium)
  - Signal coefficients form degenerate manifold — different triplets produce identical signals
  - GDA: Ka_guest sensitivity depends critically on g0 (guest concentration)
- **P1 test fixes applied**:
  - Removed signal coefficient recovery tests (structurally impossible)
  - Added signal reconstruction tests (1% threshold for DBA/IDA, 5% for GDA)
  - conftest.py: I0=0, GDA g0=20µM, tight signal bounds (±20%), np.random.seed(42)
  - GDA uses 500 trials (DBA/IDA use 200)
- **Scientific documentation added**:
  - New Section 5 "Parameter Identifiability and Signal Coefficient Degeneracy" in docs/scientific-summary.md
  - Covers: mathematical derivation (IDA + DBA), consequences table, 6 inspection steps, 4 mitigation strategies
- **Memory bank updated** with degeneracy findings

### 2026-02-03 (Testing Strategy Formalized)
- **Testing strategy approved and documented**:
  - Workflow: `uv run pytest`
  - Tolerance: 10% for clean synthetic, 20% for 5% Gaussian noise
  - Test fixtures: Committed to `tests/data/` for reproducible edge cases
- **Priority test categories defined**:
  - P1: Parameter recovery (fit synthetic, verify Ka)
  - P2: Forward model math (known inputs → expected outputs)
  - P3: Fail-fast contracts (missing params, NaN, negative K)
  - P4: I/O round-trip (write→read preserves data)
  - P5: Optimizer boundaries
  - P6: Integration (end-to-end with real data)
- **Next**: Create conftest.py and implement P1 tests

### 2026-02-03 (Phase 2: Implementation COMPLETE)
- **Scorched Earth cleanup done**:
  - Deleted `core/fitting/` (11 files)
  - Deleted `core/io/` (~15 files)
  - Deleted `gui/interface_*.py` (9 files)
- **New minimal I/O created**:
  - `core/io/__init__.py` — Public API: `load_measurements()`, `save_results()`
  - `core/io/base.py` — `MeasurementReader`, `ResultWriter` protocols
  - `core/io/registry.py` — Simple dict-based format dispatch
  - `core/io/formats/txt.py` — Multi-replica `.txt` reader + result writer
- **Tests passed**:
  - All imports successful
  - Loaded GDA data: 72 rows, 3 replicas
  - Result writer outputs proper tab-separated format
- **Next**: End-to-end fitting test with real data

### 2026-02-03 (Phase 2: Scorched Earth Planning)
- **Cleanup policy approved**: Delete superseded code immediately, don't comment out or archive.
- **Decisions confirmed**:
  - Delete `core/fitting/` entirely (11 files) — including full_plate_fit.py
  - Delete `core/io/` entirely (~15 files) — over-engineered registry pattern
  - Delete `gui/interface_*.py` (9 files) — GUI is paused, will rebuild later
- **New I/O design**:
  - Minimal Strategy pattern with explicit dict registry (no decorators)
  - `.txt` format only initially (multi-replica tab-separated)
  - Multi-replica handling: long format DataFrame with `replica` column
  - BMG format: add when needed, not now
- Updated subtasks 3.22–3.26 for cleanup and I/O rewrite.

### 2026-02-02 (Memory Bank Update)
- Updated all memory bank files to reflect current state.
- **Scientific Remediation fully verified** — all tests passing.
- Current branch: `refactor-io` with active PR #4.
- Next: Phase 2 — Wire I/O layer to new assay structure (subtasks 3.22, 3.23).

### 2026-01-31 (Scientific Remediation COMPLETE)
- **All critical bugs fixed** — 4-parameter fitting restored, unified naming enforced.
- Changes implemented:
  - **registry.py**: Updated parameter_keys to 4 params with unified naming, bounds to M^-1
  - **equilibrium.py**: Renamed K_D→Ka_dye, K_G→Ka_guest, I_D→I_dye_free, I_HD→I_dye_bound; fixed GDA titrant
  - **gda.py**: Complete rewrite with 4-param model, None defaults, dye as titrant
  - **ida.py**: Complete rewrite with 4-param model, None defaults, guest as titrant
  - **dba.py**: 4-param model (Ka_dye, I0, I_dye_free, I_dye_bound), None defaults
  - **forward_model.py**: Full naming alignment with comprehensive docstrings
- **All tests passed** — imports, forward_model calls, fail-fast validation verified.
- Next: Wire I/O layer to new assay structure (Phase 2).

### 2026-01-31 (Scientific Remediation Planning)
- **CRITICAL BUGS FOUND** in Phase 1 implementation via logic review against `forward_model.py`.
- Issues identified:
  - I_HD hardcoded to 0.0 in GDA/IDA wrappers (should be fitted)
  - I_D hardcoded to 0.0 in DBA wrapper (should be fitted)
  - Only 3 params fitted; legacy uses 4: `[I0, Ka, I_dye_free, I_dye_bound]`
  - IDA uses `K_I` but should use `Ka_guest` (same param as GDA)
  - Physical params have dangerous `= 0.0` defaults
  - Naming suggests dissociation (K_D) but formulas use association
- Remediation plan approved:
  - Restore 4-parameter fitting
  - Unify naming: `Ka_dye`, `Ka_guest`, `I_dye_free`, `I_dye_bound`
  - Remove defaults via Option B (None + __post_init__ validation)
  - Update legacy `forward_model.py` to match new convention
  - Default bounds for 4th param → future task (TASK004)
- Added subtasks 3.16–3.23 for remediation work.

### 2026-01-30 (Implementation Complete)
- **Phase 1 Implementation COMPLETE** — all core modules created and tested.
- Created `core/units.py` with shared pint UnitRegistry (ureg, Q_, strip_units(), ensure_quantity()).
- Created `core/assays/registry.py` with AssayType enum, AssayMetadata dataclass, ASSAY_REGISTRY dict.
- Created `core/assays/base.py` with BaseAssay ABC (forward_model(), get_conditions(), residuals()).
- Created `core/assays/gda.py`, `ida.py`, `dba.py`, `dye_alone.py` — concrete assay classes.
- Created `core/models/equilibrium.py` with dba_signal(), gda_signal(), ida_signal().
- Created `core/models/linear.py` with linear_signal().
- Created `core/optimizer/multistart.py` with FitAttempt dataclass, generate_initial_guesses(), multistart_minimize().
- Created `core/optimizer/filters.py` with RMSE/R² filtering and median aggregation.
- Created `core/optimizer/linear_fit.py` with linear_regression().
- Created `core/pipeline/fit_pipeline.py` with FitResult, FitConfig, fit_assay(), fit_linear_assay().
- Reverted `core/api.py` (deleted file) and cleaned up `core/__init__.py`.
- Added `pint>=0.24` to requirements.txt.
- **All imports verified working** — no errors.
- **DyeAlone functional test passed** — True slope 5.00e+10, Fitted 5.00e+10, R² = 1.0000.
- Next: Wire I/O layer to new assay structure (Phase 2).

### 2026-01-30 (Architecture Design)
- Task created from strategy pivot.
- Completed comprehensive analysis of all fitting modules.
- Designed new modular architecture.
- Finalized Enum-Keyed Registry dispatch pattern.
- Planned pint integration with boundary stripping.
- Created parameter/assay dependency matrix.
- Updated memory bank to reflect new architecture.

## Architecture Reference

### Directory structure
```
core/
├── units.py              # Shared pint UnitRegistry
├── assays/               # Domain: assay definitions
│   ├── registry.py       # AssayType enum + AssayMetadata + ASSAY_REGISTRY
│   ├── base.py           # BaseAssay ABC
│   ├── dba.py            # DBAAssay (both HtoD and DtoH)
│   ├── gda.py            # GDAAssay
│   ├── ida.py            # IDAAssay
│   └── dye_alone.py      # DyeAloneAssay
├── models/               # Forward models (pure math, unit-free)
│   ├── equilibrium.py    # DBA, competitive equilibrium
│   └── linear.py         # Linear model for dye-alone
├── optimizer/            # Fitting engine (stateless)
│   ├── multistart.py     # Multi-start L-BFGS-B
│   ├── linear_fit.py     # Linear regression
│   └── filters.py        # RMSE/R² filtering, aggregation
├── pipeline/             # Orchestration
│   └── fit_pipeline.py   # FitPipeline.run()
└── io/                   # I/O layer (readers/writers)
    ├── readers.py        # TxtReader
    └── writers.py        # ResultWriter
```

### Parameter/Assay Matrix (Corrected Naming)
| Parameter       | GDA | IDA | DBA-HtoD | DBA-DtoH | DyeAlone |
|-----------------|-----|-----|----------|----------|----------|
| Ka_guest (fitted) | ✓   | ✓   |          |          |          |
| Ka_dye (known)  | ✓   | ✓   |          |          |          |
| Ka_dye (fitted) |     |     | ✓        | ✓        |          |
| I0              | ✓   | ✓   | ✓        | ✓        |          |
| I_dye_free      | ✓   | ✓   | ✓        | ✓        |          |
| I_dye_bound     | ✓   | ✓   | ✓        | ✓        |          |
| slope (m)       |     |     |          |          | ✓        |
| intercept (c)   |     |     |          |          | ✓        |
