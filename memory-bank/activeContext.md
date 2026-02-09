# Active Context

## Strategy Pivot (2026-01-30)

Major strategic change:
1. **GUI development is completely paused** — breakage is acceptable.
2. **Full-plate fitting: DELETE** — no longer kept as legacy (2026-02-02 decision).
3. **Sole focus: restructure Core Models and Fitting Logic.**
4. **Public API work is postponed** — revert/undo recent `core/api.py` changes.

## Current focus (2026-02-09)

**Phase 3: Testing — COMPLETE ✅ (62 tests, all passing)**

All P1–P4 test categories implemented and passing. Scientific documentation on parameter identifiability added to `docs/scientific-summary.md`.

### Completed Phases
- **Phase 1**: Core modules ✅ (2026-01-30)
- **Phase 1.5**: Scientific remediation ✅ (2026-01-31)
- **Phase 2**: Scorched Earth cleanup + minimal I/O ✅ (2026-02-03)
- **Phase 3**: Testing P1–P4 ✅ (2026-02-09)
- **Scientific documentation**: Parameter identifiability section ✅ (2026-02-09)

### Test Summary
| Category | Tests | Description |
|----------|-------|-------------|
| P1: Parameter Recovery | 11 | Ka recovery + signal reconstruction (DBA, GDA, IDA, DyeAlone) |
| P2: Forward Model Math | 14 | Known inputs → expected outputs |
| P3: Fail-Fast Contracts | 23 | Constructor validation for all assay types |
| P4: I/O Round-Trip | 14 | TxtReader, TxtWriter, registry dispatch |
| **Total** | **62** | All passing (~10 min runtime) |

### Key Scientific Finding: Signal Coefficient Degeneracy
In DBA/IDA, mass conservation on the fixed species collapses the 3 signal parameters (I0, I_dye_free, I_dye_bound) into 2 effective DOFs (offset + contrast). Ka remains identifiable (controls curve shape). Documented in `docs/scientific-summary.md` Section 5.

### Next Steps
1. **TASK004**: Fix registry default bounds for realistic signal coefficients (informed by degeneracy analysis)
2. **P5**: Optimizer boundary tests
3. **P6**: End-to-end integration tests with real data
4. Investigate DBA DtoH model bug: `dba_signal` uses `y_free` (free HOST) with `I_dye_free` coefficient — possible naming/logic error
5. Clean up scratch diagnostic files (`scratch/test_diag*.py`)

## Development reality

- This is a **single-developer research codebase** in active evolution.
- Backwards compatibility is not a constraint; breaking the GUI is acceptable.
- Prioritize code maintainability and clarity over complex enterprise abstractions.

## Architecture Design (confirmed 2026-01-30)

### New directory structure
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

### Key design decisions

1. **Assay Identity: Enum-Keyed Registry Pattern**
   - `AssayType` enum defines what assays exist
   - `AssayMetadata` frozen dataclass holds labels, parameter keys
   - `ASSAY_REGISTRY` dict maps `AssayType -> AssayMetadata`
   - Plotter looks up metadata by enum key — no isinstance checks

2. **Pint Integration: Boundary Stripping**
   - Internal: concentrations and constants as `pint.Quantity`
   - Optimizer receives `.magnitude` (plain floats)
   - Plotter receives `.magnitude` arrays
   - I/O writes magnitude + unit string metadata

3. **Separation of Concerns**
   - Assays: data containers + forward model reference
   - Pipeline: orchestrates load → fit → aggregate → return
   - I/O: completely decoupled readers/writers
   - Plotting: external, optional, receives stripped magnitudes + metadata

## Working assumptions

- GUI breakage is acceptable.
- Full-plate fitting stays as-is (legacy).
- De-scoping overengineered features is encouraged.

## Implementation Status

### Phase 1: COMPLETE ✅ (2026-01-30)
All core modules have been implemented and tested:
- `core/units.py` — pint UnitRegistry with boundary stripping utilities
- `core/assays/registry.py` — AssayType enum, AssayMetadata, ASSAY_REGISTRY
- `core/assays/base.py` — BaseAssay ABC
- `core/assays/gda.py`, `ida.py`, `dba.py`, `dye_alone.py` — concrete assay classes
- `core/models/equilibrium.py` — dba_signal, gda_signal, ida_signal
- `core/models/linear.py` — linear_signal
- `core/optimizer/multistart.py` — multi-start L-BFGS-B wrapper
- `core/optimizer/filters.py` — RMSE/R² filtering, aggregation
- `core/optimizer/linear_fit.py` — simple linear regression
- `core/pipeline/fit_pipeline.py` — FitResult, FitConfig, fit_assay()

### Phase 1.5: SCIENTIFIC REMEDIATION ✅ COMPLETE (2026-01-31)
Logic review against legacy `forward_model.py` revealed critical bugs — **ALL FIXED**:

#### Issues Found & Fixed
| Issue | Severity | Description | Status |
|-------|----------|-------------|--------|
| **I_HD/I_D hardcoded to 0** | 🔴 Critical | Assay wrappers hardcode signal coefficients; should fit 4 params | ✅ Fixed |
| **IDA naming confusion** | 🟡 Medium | Uses `K_I` but should be `Ka_guest` (same as GDA) | ✅ Fixed |
| **Dangerous defaults** | 🟡 Medium | Physical params (Ka_dye, h0, d0) have `= 0.0` defaults | ✅ Fixed |
| **Association vs Dissociation** | 🟡 Medium | Code uses association form but names suggest dissociation | ✅ Fixed |

#### Files Modified
- **registry.py**: 4 params with unified naming, bounds in M^-1
- **equilibrium.py**: Full rename (K_D→Ka_dye, K_G→Ka_guest, I_D→I_dye_free, I_HD→I_dye_bound)
- **gda.py**: 4-param model, None defaults, dye as titrant
- **ida.py**: 4-param model, None defaults, guest as titrant
- **dba.py**: 4-param model, None defaults
- **forward_model.py**: Full naming alignment with comprehensive docstrings

#### Tests Verified ✅
- All imports successful
- DBA, GDA, IDA forward_model calls work
- Fail-fast validation working (missing params raise ValueError)

#### Remediation Plan
1. **Restore 4-parameter fitting** — `I0`, `Ka_*`, `I_dye_free`, `I_dye_bound`
2. **Unify naming** — `Ka_dye`, `Ka_guest`, `I_dye_free`, `I_dye_bound`
3. **Remove dangerous defaults** — use `None` with `__post_init__` validation
4. **Update legacy `forward_model.py`** — align naming with new convention
5. **Fix all docstrings** — clarify association constants, correct assay descriptions

#### Design Decisions (confirmed 2026-01-31)
- Default removal strategy: **Option B** — use `None` with validation in `__post_init__`
- Legacy code: **Update `forward_model.py`** to match new naming convention
- Default bounds for 4th parameter: **Future task** — defer to TASK004

### Phase 2: COMPLETE ✅ (2026-02-03)
### Phase 3: COMPLETE ✅ (2026-02-09)

## Scientific Conventions (ENFORCED)

1. **Association Constants Only** — All binding constants use association form:
   - $K_a = [complex] / ([free_A][free_B])$
   - Named as `Ka_dye`, `Ka_guest` (NOT `Kd`, `K_D`, `K_I`)

2. **Assay Definitions**
   | Assay | Titrant | Fixed | Target | Signal Trend |
   |-------|---------|-------|--------|--------------|
   | DyeAlone | Dye (d0) | None | slope, intercept | ↑ Linear |
   | DBA | Dye (d0) | Host (h0) | Ka_dye | ↑ Increases |
   | GDA | Dye (d0) | Host, Guest | Ka_guest | ↑ Increases |
   | IDA | Guest (g0) | Host, Dye | Ka_guest | ↓ Decreases |

3. **4-Parameter Signal Model** (all equilibrium assays):
   - `I0` — background signal
   - `Ka_*` — association constant (dye or guest)
   - `I_dye_free` — signal coefficient for free dye
   - `I_dye_bound` — signal coefficient for host-dye complex

## Recent updates

- 2026-02-09: **Scientific documentation** — Parameter identifiability section added to `docs/scientific-summary.md` (Section 5).
- 2026-02-09: **Phase 3 Testing COMPLETE** — 62 tests passing, all P1–P4 categories.
- 2026-02-06: Diagnosed signal coefficient degeneracy — root cause of P1 test failures.
- 2026-02-03: **Phase 2 Scorched Earth COMPLETE** — cleanup + minimal I/O.
- 2026-01-31: **Scientific Remediation COMPLETE** — 4-param fitting restored.
- 2026-01-30: **Phase 1 implementation complete** — all core modules.
- 2026-01-30: Major strategy pivot — GUI paused, API postponed, core refactor only.
