# Active Context

## Strategy Pivot (2026-01-30)

Major strategic change:
1. **GUI development is completely paused** — breakage is acceptable.
2. **Full-plate fitting: DELETE** — no longer kept as legacy (2026-02-02 decision).
3. **Sole focus: restructure Core Models and Fitting Logic.**
4. **Public API work is postponed** — revert/undo recent `core/api.py` changes.

## Current focus (2026-02-17)

**TASK005 GUI Plotting Module — COMPLETE ✅** (2026-02-17)

New `gui/plotting/` subpackage added using PyQtGraph as the rendering engine.
37 new tests added; 251 tests total, all passing.

**TASK003 Core Fitting Logic Refactor — COMPLETE ✅** (2026-02-16)

All phases done. P5 optimizer boundary tests and P6 end-to-end integration tests added on 2026-02-16.

**251 tests total, all passing.**

### Completed Phases
- **Phase 1**: Core modules ✅ (2026-01-30)
- **Phase 1.5**: Scientific remediation ✅ (2026-01-31)
- **Phase 2**: Scorched Earth cleanup + minimal I/O ✅ (2026-02-03)
- **Phase 3**: Testing P1–P4 ✅ (2026-02-09)
- **Scientific documentation**: Parameter identifiability section ✅ (2026-02-09)
- **Phase 4**: Data Processing Layer ✅ (2026-02-10)
- **Named Parameter Handling**: Bounds + log-scale refactor ✅ (2026-02-13)
- **P5+P6 Tests**: Optimizer boundaries + end-to-end integration ✅ (2026-02-16)

### Test Summary
| Category | Tests | Description |
|----------|-------|-------------|
| P1: Parameter Recovery | 11 | Ka recovery + signal reconstruction (DBA, GDA, IDA, DyeAlone) |
| P2: Forward Model Math | 14 | Known inputs → expected outputs |
| P3: Fail-Fast Contracts | 23 | Constructor validation for all assay types |
| P4: I/O Round-Trip | 14 | TxtReader, TxtWriter, registry dispatch |
| P5a: Parameter Handling | 33 | Named bounds, log-scale semantics, bounds_from_dye_alone, registry consistency |
| P5b: Optimizer Boundaries | 42 | generate_initial_guesses, multistart_minimize, filters, aggregation, metrics |
| P6: Integration | 22 | End-to-end pipeline (DBA/GDA/IDA/DyeAlone), chained workflow, FitConfig, failure modes |
| MeasurementSet | 30 | Construction, immutability, UUID, replica management, data access |
| Preprocessing | 13 | Z-score outlier detection, registry, pipeline |
| FitResult Serialization | 12 | Properties, round-trip, JSON safety |
| GUI: colors | 8 | Palette bounds, `rgba()` packing — no QApp |
| GUI: fit summary logic | 17 | `_lookup_assay_type()`, `_fmt_value()` edge cases — no QApp |
| GUI: plot widget | 6 | `update_plot()` item counts, `_clear_items()` — QApp |
| GUI: fit summary widget | 4 | Row count, metrics, `clear()`, unknown assay — QApp |
| GUI: style roundtrip | 2 | Signal wiring, `apply_style` on empty plot — QApp |
| **Total** | **251** | All passing (~6 min runtime) |

### Phase 4 Summary

#### MeasurementSet (`core/data_processing/measurement_set.py`)
- Multi-replica in-memory data container (2D numpy: n_replicas × n_points)
- Immutable concentrations/signals (read-only views), mutable `_active_mask` only
- `from_dataframe()`, `iter_replicas()`, `average_signal()`, `to_assay()`, `set_active()`/`reset_active()`
- UUID-based loose coupling to FitResult

#### FitResult Refactor (`core/pipeline/fit_pipeline.py`)
- **Removed**: `params` (ndarray), `params_dict` (property), `uncertainties` (ndarray), `assay` (BaseAssay), `all_attempts` (list)
- **Added**: `parameters` (dict), `uncertainties` (dict), `x_fit`, `y_fit` (ndarray), `assay_type` (str), `model_name` (str), `conditions` (dict), `fit_config` (dict), `measurement_set_id`, `source_file`, `id` (UUID), `timestamp` (ISO-8601)
- **Added**: `to_dict()`, `from_dict()`, `success` property, `fit_measurement_set()` convenience function
- **Bug fix**: Silent fallback in `fit_assay()` removed — now returns explicit failure FitResult with diagnostic metadata + actionable hint when no fits pass filtering

#### Preprocessing (`core/data_processing/preprocessing.py`)
- `PreprocessingStep` Protocol with `process(ms) -> ms` signature
- Dict-based registry (mirrors IO pattern): `PREPROCESSING_STEPS`, `register_step()`, `get_step()`
- `apply_preprocessing()` pipeline runner with processing log
- Built-in: `ZScoreReplicaFilter` — uses robust estimators (median + MAD, 0.6745 normalization) for outlier detection. Default threshold=3.5, min_replicas=3.

#### Plotting Helper (`core/data_processing/plotting.py`)
- `prepare_plot_data(ms, fit_results, show_dropped)` — GUI-friendly dict output, no matplotlib dependency

### Key Scientific Finding: Z-Score Masking Effect
With population std (`ddof=0`) and n replicas, a single extreme outlier's z-score is mathematically bounded at `2 * (n-1)/n` (for n=5, exactly 2.0). This means mean+std z-score CANNOT detect single outliers in small samples regardless of how extreme they are. Solution: use robust estimators (median + MAD) which are unaffected by the outlier.

### Key Scientific Finding: Signal Coefficient Degeneracy
In DBA/IDA, mass conservation on the fixed species collapses the 3 signal parameters (I0, I_dye_free, I_dye_bound) into 2 effective DOFs (offset + contrast). Ka remains identifiable (controls curve shape). Documented in `docs/scientific-summary.md` Section 5.

### Named Parameter Handling Refactor (2026-02-13)

Four user concerns addressed:
1. **`log_scale_params=None` silent bug** — `None` no longer hardcodes `[0]`; uses assay-level default from `AssayMetadata.log_scale_keys`
2. **Brittle positional bounds** — `FitConfig.custom_bounds` changed from `List[Tuple]` to `Dict[str, Tuple]`
3. **No partial overrides** — `_resolve_bounds()` merges user dict with registry defaults; unknown keys raise `ValueError`
4. **No dye-alone priors** — `bounds_from_dye_alone()` converts slope→`I_dye_free`, intercept→`I0` bounds

#### Files Modified
- `core/assays/registry.py` — Added `log_scale_keys: Tuple[str, ...]` to `AssayMetadata`, set for all 5 assay types
- `core/assays/base.py` — `get_default_bounds()` returns `Dict[str, Tuple]` (unified, old positional version deleted)
- `core/pipeline/fit_pipeline.py` — Breaking API changes to `FitConfig`, added `_resolve_bounds()`, `_resolve_log_scale()`, `bounds_from_dye_alone()`
- `core/pipeline/__init__.py` — Added `bounds_from_dye_alone` export
- `tests/conftest.py` — `DBA_RECOVERY_BOUNDS` + `GDA_IDA_RECOVERY_BOUNDS` (named dicts); legacy `RECOVERY_BOUNDS` alias deleted
- `tests/unit/test_parameter_recovery.py` — Updated to use named bounds and `log_scale_params=None`
- `tests/unit/test_param_handling.py` — **NEW** — 32 tests for named bounds, log-scale, bounds_from_dye_alone, registry consistency

### GUI Plotting Module (2026-02-17)

**`gui/plotting/` — new subpackage**

| Module | Contents |
|--------|----------|
| `colors.py` | `REPLICA_PALETTE` (8-color), `FIT_PALETTE`, scalar color constants, `rgba()` |
| `plot_style.py` | `DEFAULT_STYLE`, `PlotStyleWidget(QWidget)` with `pg.ParameterTree` and `style_changed` signal, `line_style_to_qt()` |
| `plot_widget.py` | `PlotWidget(QWidget)` wrapping `pg.PlotWidget`; `update_plot()` / `apply_style()` / `set_axis_labels()` / `_clear_items()` |
| `fit_summary_widget.py` | `FitSummaryWidget(QWidget)` — parameters table + quality metrics; `_lookup_assay_type()`, `_fmt_value()` module-level helpers |
| `__init__.py` | Re-exports `PlotWidget`, `FitSummaryWidget`, `PlotStyleWidget` |

**Dependencies added:** `pyqtgraph==0.14.0`, `pyqt6==6.10.2`

**Integration pattern:** Caller resolves assay labels from `ASSAY_REGISTRY`, passes as strings to `PlotWidget(x_label=..., y_label=...)`. `PlotWidget` has no dependency on `ASSAY_REGISTRY`. `style_changed` signal wired directly to `apply_style()`.

**`minimal_plot_data` fixture** added to `tests/conftest.py`.

### Next Steps
1. **TASK004**: Fix registry default bounds for realistic signal coefficients (informed by degeneracy analysis)
2. Investigate DBA DtoH model bug: `dba_signal` uses `y_free` (free HOST) with `I_dye_free` coefficient — possible naming/logic error
3. **TASK001**: Define public API surface (deferred until after core refactor — now unblocked)
4. Build PyQt6 main window wiring `PlotWidget`, `FitSummaryWidget`, `PlotStyleWidget` together

## Development reality

- This is a **single-developer research codebase** in active evolution.
- Backwards compatibility is not a constraint; breaking the GUI is acceptable.
- Prioritize code maintainability and clarity over complex enterprise abstractions.

## Architecture Design (confirmed 2026-01-30)

### New directory structure (actual)
```
core/
├── units.py              # Shared pint UnitRegistry
├── forward_model.py      # Legacy forward model (naming aligned)
├── assays/               # Domain: assay definitions
│   ├── registry.py       # AssayType enum + AssayMetadata + ASSAY_REGISTRY
│   ├── base.py           # BaseAssay ABC
│   ├── dba.py            # DBAAssay (both HtoD and DtoH)
│   ├── gda.py            # GDAAssay
│   ├── ida.py            # IDAAssay
│   └── dye_alone.py      # DyeAloneAssay
├── models/               # Forward models (pure math, unit-free)
│   ├── equilibrium.py    # dba_signal, gda_signal, ida_signal
│   └── linear.py         # linear_signal (dye-alone)
├── optimizer/            # Fitting engine (stateless)
│   ├── multistart.py     # Multi-start L-BFGS-B
│   ├── linear_fit.py     # Linear regression
│   └── filters.py        # RMSE/R² filtering, median+MAD aggregation
├── pipeline/             # Orchestration
│   └── fit_pipeline.py   # FitConfig, FitResult, fit_assay()
└── io/                   # I/O layer (minimal Strategy pattern)
    ├── __init__.py        # Public API: load_measurements(), save_results()
    ├── base.py            # MeasurementReader, ResultWriter protocols
    ├── registry.py        # Format dispatch (explicit dict, no decorators)
    └── formats/
        └── txt.py         # TxtReader, TxtWriter (multi-replica aware)
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
- Full-plate fitting: DELETED (2026-02-02 decision).
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

- 2026-02-17: **GUI Plotting Module COMPLETE** — `gui/plotting/` subpackage with PyQtGraph. 37 new tests. 251 tests total.
- 2026-02-16: **P5+P6 tests COMPLETE** — 42 optimizer boundary tests + 22 end-to-end integration tests. TASK003 fully complete. 214 tests.
- 2026-02-13: **Named parameter handling refactor COMPLETE** — Dict-based bounds, named log-scale, bounds_from_dye_alone(). 150 tests.
- 2026-02-10: **Phase 4 Data Processing COMPLETE** — MeasurementSet, preprocessing, FitResult refactor. 117 tests.
- 2026-02-09: **Phase 3 Testing COMPLETE** — 62 tests passing, all P1–P4 categories.
