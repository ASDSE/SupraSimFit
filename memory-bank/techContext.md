# Technical Context

## Languages and runtimes

- **Language**: Python 3.13.5
- **Target platforms**: Windows, macOS, Linux
- **Nature of the project**: single‑developer research software in active development, not a production service.

## Core dependencies (current and planned)

- **Numerics and data**
  - `numpy` – numerical computations
  - `scipy` – optimization, root‑finding (e.g. `brentq`), statistics
  - `pandas` – tabular data handling
  - `xarray`, `pyarrow`, `h5netcdf` – structured data / NetCDF / Parquet (current code supports them but actual status is unknown and may be de‑scoped)
- **Visualization**
  - `matplotlib` – publication‑quality plots (currently integrated mainly via scripts/utilities)
- **GUI**
  - Current GUI: **Tkinter** (standard library)
  - Target GUI: **PyQt 6** (explicitly chosen over PySide)
- **Units**
  - Planned integration of **pint** (or similar) for physical units, unit‑safe calculations, and clearer parameter semantics.
- **Packaging / build**
  - `pyinstaller` – build standalone executables (`FittingApp.spec`)

## Project layout (high level, as of now)

- `main.py` – entry point for the current Tkinter GUI
- `core/` – domain logic, forward models, fitting, and I/O abstractions
- `gui/` – GUI implementations (currently Tkinter; PyQt 6 will also live here)
- `utils/` – monolithic scripts and helper modules (plotting, stats, converters, etc.)
- `docs/`, `examples/`, `tests/`, `assets/`, `build/`, `memory-bank/`

## Development workflows

- **Run app from source**: `uv run python main.py`
- **Install dependencies**: `uv sync` (or `uv add <package>`)
- **Build executable**:
  - `pyinstaller --clean -y --distpath ./dist --workpath ./build FittingApp.spec`
- **Testing**: `uv run pytest` (pytest workflow formalized 2026-02-03)
  - `uv run pytest -v` for verbose output
  - `uv run pytest -k "test_gda"` for specific tests
  - **62 tests, all passing** (P1–P4 complete as of 2026-02-09)
  - Runtime: ~10 minutes (dominated by P1 multi-start optimization)
- **Tolerance**: 10% for clean synthetic data, 20% for 5% Gaussian noise
- **Parameter identifiability**: Signal coefficients are structurally degenerate in DBA/IDA; tests verify Ka recovery + signal reconstruction only

## Tooling and future direction

- Enforce style with **Black** and PEP 8.
- Use Numpy‑style docstrings for public methods.
- Plan to migrate dependency management to **uv** + `pyproject.toml` for cleaner, reproducible setups.

## Constraints and non‑goals

- Backwards compatibility is **not** a requirement during refactoring; broken intermediate states are acceptable.
- Production‑grade stability, SLAs, or long‑term API guarantees are **explicitly not** goals at this stage.
- I/O support beyond `.txt` and `.xlsx` is experimental and may be removed or re‑implemented from scratch.

## Notes on current codebase and development practices

### Overview

- This toolkit analyzes molecular binding data from spectroscopic assays (GDA, IDA, DBA, Dye Alone) with robust fitting algorithms and a GUI (currently Tkinter, migrating to PyQt 6).
- Core logic is in `core/` (fitting, I/O, models), UI in `gui/`, utilities in `utils/`, docs in `docs/`, and sample data in `data/`.

### Current architecture & data flow (being refactored)

> **2026-01-30 NOTE**: Core fitting logic is being refactored. See [systemPatterns.md](systemPatterns.md) and [tasks/TASK003-core-refactor.md](tasks/TASK003-core-refactor.md) for the new architecture.

- **Assay-specific fitting**: Currently in `core/fitting/` (e.g., `gda.py`, `ida.py`). Being refactored to `core/assays/` with modular separation.
- **I/O system**: Extensible serialization in `core/io/`:
  - `MeasurementSet` and `FitResult` are the main data objects (see `measurement_set.py`, `fit_result.py`).
  - File format support (NetCDF, Parquet, XLSX, TXT, CSV) via plugin readers/writers in `core/io/serialize/`.
  - Registry pattern: new formats register via decorators in `core/io/registry.py`.
- **Units**: **pint** integration planned with boundary stripping strategy (strip to magnitude at optimizer/plotter/I/O boundaries).
- **GUI**:
  - **Current**: Tkinter-based, main entry in `main.py`, with interfaces in `gui/` (e.g., `interface_GDA_fitting.py`).
  - **Status**: PAUSED. Will break during core refactor.
  - **Future**: PyQt 6 migration deferred until after core refactor.
- **Utilities**: Plotting, stats, and fitting helpers in `utils/`.

### Current developer workflows

- **Run app**: `python main.py` (from repo root)
- **Build executable**: `pyinstaller --clean -y --distpath ./dist --workpath ./build FittingApp.spec`
- **Install dependencies**: `pip install -r requirements.txt` (or use `environment.yml` for conda)
- **Test**: (Unit tests WIP; see `tests/`)

### Current project conventions

- **Data objects**: Always use `MeasurementSet` for raw/processed data, `FitResult` for fit outputs. Use their factory methods for loading from DataFrame/xarray.
- **I/O**: Add new file formats by subclassing `Reader`/`Writer` and registering with `@register_reader`/`@register_writer`.
- **Metadata**: All data objects embed a `meta` dict (with `object_type`, `schema_version`, etc.) in file attributes.
- **Assay logic**: New assay types go in `core/fitting/` and are exposed via the GUI by adding new interface modules in `gui/`.
- **Style**: Follow PEP8 and Black formatting. Use Numpy-style docstrings with examples.
- **Qt GUI**:
  - Use Qt's resource system for icons and assets.
  - Keep UI responsive (avoid blocking the main thread; use QThread or QtConcurrent for long-running tasks).
  - Use type hints and docstrings for all public methods.

### Current integration points

- **External dependencies**: `numpy`, `pandas`, `scipy`, `matplotlib`, `xarray`, `pyarrow`, `h5netcdf` (for NetCDF), `PyQt6` (for Qt GUI), `tkinter` (legacy GUI).
- **Data import**: Supports `.txt`, `.xlsx`, `.parquet`, `.csv`, `.nc` (NetCDF). See `core/io/serialize/readers/` for details.
