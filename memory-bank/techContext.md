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
  - `pyqtgraph==0.14.0` – interactive Qt-native plots for GUI (`gui/plotting/`)
- **Units**
  - `pint>=0.24` – physical units with boundary‑stripping strategy (implemented in `core/units.py`)
- **GUI**
  - Current: **Tkinter** (standard library) — `main.py` (legacy entry point)
  - **PyQt6==6.10.2** — GUI plotting layer active (`gui/plotting/` subpackage)
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
│   └── fit_pipeline.py    # FitConfig, FitResult, fit_assay(), fit_measurement_set()
├── data_processing/       # Multi-replica data handling
│   ├── measurement_set.py # MeasurementSet (immutable 2D numpy container)
│   ├── preprocessing.py   # PreprocessingStep Protocol + ZScoreReplicaFilter
│   └── plotting.py        # prepare_plot_data() (GUI-friendly dict, no matplotlib)
└── io/                    # I/O layer (minimal Strategy pattern)
    ├── __init__.py         # Public API: load_measurements(), save_results()
    ├── base.py             # MeasurementReader, ResultWriter protocols
    ├── registry.py         # Format dispatch (explicit dict, no decorators)
    └── formats/
        └── txt.py          # TxtReader, TxtWriter (multi-replica aware)
gui/                       # GUI layer
├── base_gui.py
├── dialogs/
├── widgets/
└── plotting/              # PyQtGraph plotting subpackage (2026-02-17)
    ├── __init__.py        # Re-exports PlotWidget, FitSummaryWidget, PlotStyleWidget
    ├── colors.py          # REPLICA_PALETTE, FIT_PALETTE, rgba()
    ├── plot_style.py      # DEFAULT_STYLE, PlotStyleWidget (ParameterTree)
    ├── plot_widget.py     # PlotWidget consuming prepare_plot_data() output
    └── fit_summary_widget.py  # FitSummaryWidget for FitResult display
utils/                     # Plotting, stats, fitting helpers
tests/                     # pytest test suite (251 tests, all passing)
├── conftest.py            # Shared fixtures, synthetic data generators, RNG seed, minimal_plot_data
├── data/                  # Committed test fixtures
├── unit/
│   ├── test_parameter_recovery.py  # P1: Ka recovery + signal reconstruction
│   ├── test_models.py              # P2: Forward model math
│   ├── test_fail_fast.py           # P3: Constructor validation
│   ├── test_io.py                  # P4: I/O round-trip
│   ├── test_param_handling.py      # P5: Named bounds, log-scale, bounds_from_dye_alone (32)
│   ├── test_optimizer.py           # P5b: Optimizer boundary tests (42)
│   ├── test_measurement_set.py     # MeasurementSet tests (30)
│   ├── test_preprocessing.py       # Preprocessing tests (13)
│   ├── test_fit_results.py         # FitResult serialization tests (12)
│   └── gui/                        # GUI tests
│       ├── test_colors.py          # 8 tests, no QApp
│       ├── test_fit_summary_logic.py  # 17 tests, no QApp
│       ├── test_plot_widget.py     # 6 tests, QApp
│       ├── test_fit_summary_widget.py # 4 tests, QApp
│       └── test_style_roundtrip.py # 2 tests, QApp
└── integration/
    └── test_pipeline_e2e.py        # P6: End-to-end pipeline (22)
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
  - **251 tests, all passing** (as of 2026-02-17)
  - Runtime: ~6 minutes
- **Tolerance**: 10% for clean synthetic data, 25% for 5% Gaussian noise
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
- GUI development: `gui/plotting/` layer added and tested; main window wiring still pending.
