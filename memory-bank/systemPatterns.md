# System Patterns and Architecture

## Current Status (2026-02-13)

**Strategy Pivot**: GUI paused, Public API postponed, focus solely on Core Fitting Logic refactor.

**Phase 1 + Scientific Remediation: COMPLETE** ✅
**Phase 2: Scorched Earth Cleanup + Minimal I/O: COMPLETE** ✅
**Phase 3: Testing (P1–P4): COMPLETE** ✅ (62 tests, all passing)
**Scientific Documentation: COMPLETE** ✅ (Parameter identifiability, docs/scientific-summary.md Section 5)
**Phase 4: Data Processing Layer: COMPLETE** ✅ (MeasurementSet, preprocessing, FitResult refactor)
**Named Parameter Handling Refactor: COMPLETE** ✅ (Named bounds, log-scale, bounds_from_dye_alone — 149 tests total)

All core modules implemented with correct scientific conventions:
- `core/units.py` — pint UnitRegistry with boundary stripping utilities
- `core/assays/` — registry, base ABC, and concrete assay classes (GDA, IDA, DBA, DyeAlone)
- `core/models/` — equilibrium.py and linear.py forward models (4-param, unified naming)
- `core/optimizer/` — multistart.py, filters.py, linear_fit.py
- `core/pipeline/` — fit_pipeline.py with FitConfig and FitResult (serializable, decoupled)
- `core/io/` — minimal Strategy pattern with TxtReader/TxtWriter
- `core/data_processing/` — MeasurementSet, preprocessing pipeline, plot data helper
- `core/forward_model.py` — Legacy code aligned with new naming convention

**Remaining work:**
- TASK004: Fix registry default bounds (informed by degeneracy analysis)
- P6: End-to-end integration tests
- DBA DtoH signal bug investigation

## High-level architecture

- **Core domain (`core/`)** — REFACTOR COMPLETE (Phases 1–3)
  - Structure: `assays/`, `models/`, `optimizer/`, `pipeline/`, `io/`
  - Legacy: `forward_model.py` (aligned with new naming), `progress_window.py`
- **GUI (`gui/`)** — PAUSED
  - Tkinter-based (`base_gui.py`). Interface files deleted.
  - Future PyQt 6 migration deferred.
- **Utilities (`utils/`)** — LOW PRIORITY
  - Plotting, stats, converters. Will be cleaned up after core refactor.
- **Tests (`tests/`)** — P1–P4 COMPLETE (62 tests)

## Architecture (Core Refactor — IMPLEMENTED)

### Directory structure (actual)
```
core/
├── units.py              # Shared pint UnitRegistry
├── forward_model.py      # Legacy forward model (naming aligned)
├── progress_window.py    # Legacy GUI progress bar
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
│   └── fit_pipeline.py   # FitConfig, FitResult, fit_assay(), fit_measurement_set()
├── data_processing/      # Multi-replica data handling
│   ├── measurement_set.py  # MeasurementSet (immutable 2D numpy container)
│   ├── preprocessing.py    # PreprocessingStep Protocol + registry + ZScoreReplicaFilter
│   └── plotting.py         # prepare_plot_data() — GUI-friendly dict output
└── io/                   # I/O layer (minimal Strategy pattern)
    ├── __init__.py        # Public API: load_measurements(), save_results()
    ├── base.py            # MeasurementReader, ResultWriter protocols
    ├── registry.py        # Format dispatch (explicit dict, no decorators)
    └── formats/
        └── txt.py         # TxtReader, TxtWriter (multi-replica aware)
```

### Assay Dispatch Pattern: Enum-Keyed Registry

```python
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Tuple

class AssayType(Enum):
    GDA = auto()
    IDA = auto()
    DBA_HtoD = auto()
    DBA_DtoH = auto()
    DYE_ALONE = auto()

@dataclass(frozen=True)
class AssayMetadata:
    display_name: str
    parameter_keys: Tuple[str, ...]
    x_label: str
    y_label: str
    default_bounds: dict = field(default_factory=dict)
    log_scale_keys: Tuple[str, ...] = ()  # Params sampled in log₁₀ space

ASSAY_REGISTRY: dict[AssayType, AssayMetadata] = {
    AssayType.GDA: AssayMetadata(
        display_name="GDA",
        parameter_keys=("Ka_guest", "I0", "I_dye_free", "I_dye_bound"),
        x_label="[Guest] / M",
        y_label="Signal / a.u."
    ),
    # ... etc for each assay
}
```

**Benefits**:
- Central definition of all assay types
- Type-safe dispatch without isinstance checks
- Easy to extend with new assays

### Pint Integration: Boundary Stripping

- **Internal**: concentrations and constants as `pint.Quantity`
- **Optimizer boundary**: strip to `.magnitude` before passing to scipy
- **Plotter boundary**: strip to `.magnitude` arrays with unit labels in metadata
- **I/O boundary**: write magnitude + unit string, reconstruct on read

```python
# core/units.py
import pint
ureg = pint.UnitRegistry()
Q_ = ureg.Quantity
```

### Scientific Conventions (ENFORCED 2026-01-31)

**Association Constants Only** — formulas use: $K_a = [complex] / ([H][L])$

**Unified Naming Convention:**
| Old Name | New Name | Meaning |
|----------|----------|--------|
| Kd, K_D (fitted) | `Ka_dye` | Association constant for Host-Dye |
| Kg, K_G, K_I | `Ka_guest` | Association constant for Host-Guest |
| Id, I_D | `I_dye_free` | Signal from free dye |
| Ihd, I_HD, I_HG, I_HI | `I_dye_bound` | Signal from bound dye (HD complex) |

**4-Parameter Signal Model** (all equilibrium assays):
```
Signal = I0 + I_dye_free * [D_free] + I_dye_bound * [HD]
```

### Parameter/Assay Dependency Matrix (CORRECTED)

| Parameter       | GDA | IDA | DBA-HtoD | DBA-DtoH | DyeAlone |
|-----------------|-----|-----|----------|----------|----------|
| Ka_guest        | ✓   | ✓   |          |          |          |
| Ka_dye (known)  | ✓   | ✓   |          |          |          |
| Ka_dye (fitted) |     |     | ✓        | ✓        |          |
| I0              | ✓   | ✓   | ✓        | ✓        |          |
| I_dye_free      | ✓   | ✓   | ✓        | ✓        |          |
| I_dye_bound     | ✓   | ✓   | ✓        | ✓        |          |
| slope (m)       |     |     |          |          | ✓        |
| intercept (c)   |     |     |          |          | ✓        |

### Assay Definitions (Source of Truth)

| Assay | Titrant | Fixed | Fitted | Signal Trend |
|-------|---------|-------|--------|--------------|
| DyeAlone | Dye (d0) | None | slope, intercept | ↑ Linear |

## Testing Strategy (Formalized 2026-02-03)

### Philosophy: Three Pillars
1. **Scientific Validation** — Fitted parameters recover known/synthetic values
2. **Data Integrity** — I/O preserves measurement data and metadata
3. **Fail-Fast Contracts** — Invalid inputs raise immediately, not silently corrupt

### Tolerance Guidelines
| Data Type | Tolerance | Rationale |
|-----------|-----------|-----------|
| Clean synthetic | 10% | Optimizer noise, numerical precision |
| 5% Gaussian noise | 20% | Realistic experimental scatter |
| Edge cases | Per-case | Document in test comments |

### Test Infrastructure
```
tests/
├── conftest.py       # Shared fixtures (synthetic data generators, RNG seed)
├── data/             # Committed test fixtures (edge cases)
└── unit/
    ├── test_parameter_recovery.py  # P1: Ka recovery + signal reconstruction
    ├── test_models.py             # P2: Forward model math
    ├── test_fail_fast.py          # P3: Constructor validation
    ├── test_io.py                 # P4: I/O round-trip
    ├── test_measurement_set.py    # MeasurementSet construction, access, to_assay
    ├── test_preprocessing.py      # Z-score filter, registry, pipeline
    └── test_fit_results.py        # FitResult properties, serialization
```

### Parameter Identifiability (2026-02-09)
Signal coefficients (I0, I_dye_free, I_dye_bound) are NOT individually identifiable in DBA/IDA due to mass conservation collapsing 3 params to 2 effective DOFs. Only Ka is identifiable. Tests verify Ka recovery + signal reconstruction, NOT individual signal coefficients. See `docs/scientific-summary.md` Section 5 for full derivation.

### Priority Test Categories
1. **P1: Parameter Recovery** — Fit synthetic data, verify Ka within tolerance
2. **P2: Forward Model Math** — Known inputs → expected outputs
3. **P3: Fail-Fast Contracts** — Missing params, NaN, negative K
4. **P4: I/O Round-Trip** — Write→Read preserves data exactly
5. **P5: Parameter Handling** — Named bounds, log-scale semantics, bounds_from_dye_alone, registry consistency
6. **P6: Integration** — End-to-end with real data files

### Pytest Workflow
```bash
uv run pytest                    # Run all tests
uv run pytest -v                 # Verbose output
uv run pytest -k "test_gda"     # Run specific tests
uv run pytest --tb=short        # Shorter tracebacks
```
| DBA | Dye (d0) | Host (h0) | Ka_dye | ↑ Increases |
| GDA | Dye (d0) | Host (h0), Guest (g0) | Ka_guest | ↑ Increases (dye displaces guest) |
| IDA | Guest (g0) | Host (h0), Dye (d0) | Ka_guest | ↓ Decreases (guest displaces dye) |

## Key Domain Concepts

- **BaseAssay** – ABC for all assay types; subclassed by GDAAssay, IDAAssay, DBAAssay, DyeAloneAssay.
- **AssayMetadata** – frozen dataclass holding display name, parameter keys, axis labels, default bounds.
- **ASSAY_REGISTRY** – dict mapping `AssayType` enum → `AssayMetadata`.
- **FitConfig** – dataclass configuring a fit run (named `Dict[str, Tuple]` bounds, `List[str]` log-scale params, n_trials).
- **FitResult** – dataclass holding fitted parameters, uncertainties, diagnostics.
- **bounds_from_dye_alone()** – derives I_dye_free/I0 bounds from dye-alone calibration for downstream fits.
- **Assay types** – GDA, IDA, DBA (host↔dye), Dye Alone.
- **Forward model** – parameters + conditions → predicted signal.

## Core Computational Patterns

### Forward modeling pipeline
1. Take trial parameters and experimental conditions.
2. Use equilibrium/mass-balance equations (varies by assay).
3. Solve numerically (scipy.optimize.brentq for 1D roots).
4. Compute species concentrations and predicted signal.
5. Compute residuals.

### Optimization strategy
- Multi-start L-BFGS-B for nonlinear assays (GDA, IDA, DBA).
- Simple linear regression for dye-alone.
- Filter by RMSE/R² threshold.
- Aggregate via median + MAD for robustness.

### I/O Pattern (implemented 2026-02-03)
- Minimal Strategy pattern with explicit dict registry (no decorators)
- Formats: `.txt` only currently (`.xlsx` planned)
- Multi-replica handling: long format DataFrame with `replica` column
- Public API: `load_measurements()`, `save_results()` in `core/io/__init__.py`

### I/O Structure (actual)
```
core/io/
├── __init__.py      # Public API: load_measurements(), save_results()
├── base.py          # MeasurementReader, ResultWriter protocols
├── registry.py      # Format dispatch (explicit dict, no decorators)
└── formats/
    ├── __init__.py
    └── txt.py       # TxtReader, TxtWriter (multi-replica aware)
```

## Separation of Concerns

| Layer | Responsibility | Imports |
|-------|---------------|---------|
| Assays | Data containers, forward model ref | models, units |
| Models | Pure math, unit-free | numpy, scipy |
| Optimizer | Fit execution, stateless | scipy.optimize |
| Pipeline | Orchestration, FitResult | assays, optimizer |
| Data Processing | Multi-replica containers, preprocessing | assays (via to_assay) |
| I/O | Read/write, validation | pandas, units |
| Plotting | External, optional | matplotlib, assay metadata |

### Data Processing Patterns (2026-02-10)

#### MeasurementSet
- Immutable 2D numpy container (n_replicas × n_points) with shared concentration grid
- UUID hex string identity for loose coupling to FitResult
- `_active_mask` (dict[str, bool]) is the only mutable field — tracks which replicas are active
- `to_assay()` bridges to BaseAssay subclasses for fitting

#### FitResult (Refactored)
- Fully decoupled from BaseAssay — no assay reference stored
- Parameters/uncertainties as `dict[str, float]` (named, not positional ndarray)
- `x_fit`/`y_fit` stored directly — no need to reconstruct from model
- `to_dict()` / `from_dict()` for JSON-safe serialization
- `success` property: `r_squared > 0 and len(parameters) > 0`
- Failure case: explicit FitResult with diagnostic metadata + actionable hint

#### Preprocessing Registry
- `PreprocessingStep` Protocol: `name: str`, `process(ms) -> ms`
- Dict-based registry: `PREPROCESSING_STEPS`, `register_step()`, `get_step()`
- `apply_preprocessing(ms, steps, log)` pipeline runner
- Built-in `ZScoreReplicaFilter`: median + MAD (robust), threshold=3.5

#### Z-Score Masking Effect (Scientific)
With population std, a single outlier's z-score is bounded at `2(n-1)/n` (exactly 2.0 for n=5).
Solution: use robust estimators (median + MAD with 0.6745 normalization factor).

### Named Parameter Handling (2026-02-13)

#### Design: Named Bounds + Log-Scale
Parameters are identified by **name** (string keys matching `parameter_keys`), not positional index.

```python
# FitConfig (breaking API change)
@dataclass
class FitConfig:
    custom_bounds: Optional[Dict[str, Tuple[float, float]]] = None  # Partial overrides
    log_scale_params: Optional[List[str]] = None  # None=assay default, []=linear, names=override
```

#### Resolution Flow
1. `_resolve_bounds(assay, custom_bounds)` — merges user dict with `assay.get_default_bounds_dict()`; unknown keys → ValueError
2. `_resolve_log_scale(assay, log_scale_params)` — None → `assay.registry_metadata.log_scale_keys`; names → indices
3. Optimizer receives positional arrays (translation happens in `fit_assay()`)

#### Assay-Level Log-Scale Defaults
`AssayMetadata.log_scale_keys` defines which params are sampled in log₁₀ space by default:
- DBA: `('Ka_dye',)` — index 0
- GDA/IDA: `('Ka_guest',)` — index 0
- DYE_ALONE: `()` — no log-scale

#### Dye-Alone → Downstream Priors
`bounds_from_dye_alone(result, margin=0.2)` extracts signal bounds from a calibration:
- slope → `I_dye_free` bounds (±margin)
- intercept → `I0` bounds (±margin)
- Returns `Dict[str, Tuple]` for direct merge: `FitConfig(custom_bounds={**priors, 'Ka_guest': ...})`

## Concurrency

- Ensemble fitting is parallelisable (future enhancement).
- For now, sequential multi-start is sufficient.
- GUI threading deferred (GUI is paused).
