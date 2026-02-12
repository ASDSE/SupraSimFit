# Technical Context

## Languages and runtimes

- **Language**: Python 3.13.5
- **Target platforms**: Windows, macOS, Linux
- **Package manager**: **uv** (see `.github/instructions/uv_management.instructions.md`)
- **Nature of the project**: single‑developer research software in active development, not a production service.

## Core dependencies

- **Numerics and data**
  - `numpy` – numerical computations
  - `scipy` – optimization (`L-BFGS-B`), root‑finding (`brentq`), statistics
  - `pandas` – tabular data handling (I/O layer)
- **Visualization**
  - `matplotlib` – publication‑quality plots (via `utils/plot_utils.py`)
- **Units**
  - `pint>=0.24` – physical units with boundary‑stripping strategy (implemented in `core/units.py`)
- **GUI** (PAUSED)
  - Current: **Tkinter** (standard library) — `main.py`
  - Future: **PyQt 6** — deferred until after core refactor
- **Packaging / build**
  - `pyinstaller` – standalone executables (`FittingApp.spec`)

> **De‑scoped:** `xarray`, `pyarrow`, `h5netcdf`, NetCDF, Parquet — removed during Phase 2 Scorched Earth cleanup.

## Project layout

```
main.py                    # Entry point for Tkinter GUI
core/
├── units.py               # pint UnitRegistry, strip_units(), ensure_quantity()
├── forward_model.py       # Legacy forward model (aligned with new naming)
├── progress_window.py     # Legacy GUI progress bar
├── assays/                # Assay definitions (BaseAssay ABC + concrete classes)
│   ├── registry.py        # AssayType enum, AssayMetadata, ASSAY_REGISTRY
│   ├── base.py            # BaseAssay ABC
│   ├── dba.py             # DBAAssay (HtoD + DtoH modes)
│   ├── gda.py             # GDAAssay
│   ├── ida.py             # IDAAssay
│   └── dye_alone.py       # DyeAloneAssay
├── models/                # Forward models (pure math, unit-free)
│   ├── equilibrium.py     # dba_signal, gda_signal, ida_signal
│   └── linear.py          # linear_signal (dye-alone)
├── optimizer/             # Fitting engine (stateless)
│   ├── multistart.py      # Multi-start L-BFGS-B wrapper
│   ├── linear_fit.py      # Linear regression
│   └── filters.py         # RMSE/R² filtering, median+MAD aggregation
├── pipeline/              # Orchestration
│   └── fit_pipeline.py    # FitConfig, FitResult, fit_assay()
└── io/                    # I/O layer (minimal Strategy pattern)
    ├── __init__.py         # Public API: load_measurements(), save_results()
    ├── base.py             # MeasurementReader, ResultWriter protocols
    ├── registry.py         # Format dispatch (explicit dict, no decorators)
    └── formats/
        └── txt.py          # TxtReader, TxtWriter (multi-replica aware)
gui/                       # GUI (PAUSED — interface files deleted)
├── base_gui.py
├── dialogs/
└── widgets/
utils/                     # Plotting, stats, fitting helpers
tests/                     # pytest test suite (62 tests, all passing)
├── conftest.py            # Shared fixtures, synthetic data generators, RNG seed
├── data/                  # Committed test fixtures
└── unit/
    ├── test_parameter_recovery.py  # P1: Ka recovery + signal reconstruction
    ├── test_models.py              # P2: Forward model math
    ├── test_fail_fast.py           # P3: Constructor validation
    └── test_io.py                  # P4: I/O round-trip
docs/                      # Scientific documentation
data/                      # Sample data files
examples/                  # Usage examples
memory-bank/               # Agent memory bank
```

## Development workflows

- **Run app**: `uv run python main.py`
- **Install/sync deps**: `uv sync` (or `uv add <package>`)
- **Build executable**: `pyinstaller --clean -y --distpath ./dist --workpath ./build FittingApp.spec`
- **Testing**: `uv run pytest` (formalized 2026-02-03)
  - `uv run pytest -v` for verbose output
  - `uv run pytest -k "test_gda"` for specific tests
  - `uv run pytest --tb=short` for shorter tracebacks
  - **62 tests, all passing** (P1–P4 complete as of 2026-02-09)
  - Runtime: ~10 minutes (dominated by multi-start optimization in P1)
- **Tolerance**: 10% for clean synthetic data, 20% for 5% Gaussian noise
- **Parameter identifiability**: Signal coefficients are structurally degenerate in DBA/IDA; tests verify Ka recovery + signal reconstruction only

## Conventions

- **Style**: PEP 8, Black formatting.
- **Docstrings**: Numpy‑style for public methods.
- **Naming**: Association constants only (`Ka_dye`, `Ka_guest`). Unified 4-param signal model.
- **I/O**: Add new formats by implementing `MeasurementReader`/`ResultWriter` protocols and registering in `core/io/registry.py` (explicit dict, no decorators).
- **Assay logic**: New assay types subclass `BaseAssay` (in `core/assays/`) and register in `ASSAY_REGISTRY`.
- **Type hints**: Required for all public methods.

## Constraints and non‑goals

- Backwards compatibility is **not** a requirement during refactoring.
- Production‑grade stability, SLAs, or long‑term API guarantees are **not** goals.
- I/O support: `.txt` only currently. `.xlsx` planned next.
- GUI development: PAUSED (breakage acceptable).
