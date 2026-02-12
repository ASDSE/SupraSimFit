# System Patterns and Architecture

## Current Status (2026-02-09)

**Strategy Pivot**: GUI paused, Public API postponed, focus solely on Core Fitting Logic refactor.

**Phase 1 + Scientific Remediation: COMPLETE** ✅
**Phase 2: Scorched Earth Cleanup + Minimal I/O: COMPLETE** ✅
**Phase 3: Testing (P1–P4): COMPLETE** ✅ (62 tests, all passing)
**Scientific Documentation: COMPLETE** ✅ (Parameter identifiability, docs/scientific-summary.md Section 5)

All core modules implemented with correct scientific conventions:
- `core/units.py` — pint UnitRegistry with boundary stripping utilities
- `core/assays/` — registry, base ABC, and concrete assay classes (GDA, IDA, DBA, DyeAlone)
- `core/models/` — equilibrium.py and linear.py forward models (4-param, unified naming)
- `core/optimizer/` — multistart.py, filters.py, linear_fit.py
- `core/pipeline/` — fit_pipeline.py with FitConfig and FitResult
- `core/forward_model.py` — Legacy code aligned with new naming convention

**Remaining work:**
- TASK004: Fix registry default bounds (informed by degeneracy analysis)
- P5: Optimizer boundary tests
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
│   └── fit_pipeline.py   # FitConfig, FitResult, fit_assay()
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
    └── test_io.py                 # P4: I/O round-trip
```

### Parameter Identifiability (2026-02-09)
Signal coefficients (I0, I_dye_free, I_dye_bound) are NOT individually identifiable in DBA/IDA due to mass conservation collapsing 3 params to 2 effective DOFs. Only Ka is identifiable. Tests verify Ka recovery + signal reconstruction, NOT individual signal coefficients. See `docs/scientific-summary.md` Section 5 for full derivation.

### Priority Test Categories
1. **P1: Parameter Recovery** — Fit synthetic data, verify Ka within tolerance
2. **P2: Forward Model Math** — Known inputs → expected outputs
3. **P3: Fail-Fast Contracts** — Missing params, NaN, negative K
4. **P4: I/O Round-Trip** — Write→Read preserves data exactly
5. **P5: Optimizer Boundaries** — Bounds enforced, edge cases handled
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
- **FitConfig** – dataclass configuring a fit run (bounds, n_trials, custom_bounds).
- **FitResult** – dataclass holding fitted parameters, uncertainties, diagnostics.
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
| Pipeline | Orchestration | assays, optimizer, io |
| I/O | Read/write, validation | pandas, units |
| Plotting | External, optional | matplotlib, assay metadata |

## Concurrency

- Ensemble fitting is parallelisable (future enhancement).
- For now, sequential multi-start is sufficient.
- GUI threading deferred (GUI is paused).
