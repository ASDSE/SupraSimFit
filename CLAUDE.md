# CLAUDE.md

Guidance for Claude Code when working in this repository.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

## Project Overview

SupraSimFit — a desktop toolkit that fits equilibrium binding models to fluorescence titration data using multi-start L-BFGS-B optimization, extracting association constants (Ka) via rigorous forward-modelling rather than linearised transforms. Assay types: `GDA`, `IDA`, `DBA_HtoD`, `DBA_DtoH`, `DYE_ALONE`.

PyQt6 GUI + PyQtGraph plots, packaged as a standalone PyInstaller binary (no Python required by end users). Single-developer research codebase — backwards compatibility and GUI stability are **not** constraints. Python **3.13+**, package manager is **uv** (not pip/poetry).

## Setup & Commands

```bash
uv sync                                  # install deps into .venv
uv run run_app.py                        # launch the GUI (dev)

uv run pytest                            # full suite (~6 min — use -k while iterating)
uv run pytest tests/unit                 # fast layer only (skips integration fits)
uv run pytest -k "gda"                   # subset by pattern
uv run pytest -x                         # stop on first failure

uv run ruff check                        # lint
uv run ruff format                       # format
```

Use `uv run` to execute, `uv add`/`uv remove` for dependencies. Never edit `uv.lock` by hand.

## Build & Release

`_version.py` (`__version__`) is the **single source of truth** for the app version — the window title, update check, PyInstaller bundle, and the CI drift-guard all read it.

- **Local build:** `pyinstaller --clean -y --distpath ./dist --workpath ./build SupraSimFit.spec`
- **Release (tag-driven):** bump `__version__` in `_version.py`, merge to `main`, then `git tag vX.Y.Z && git push origin vX.Y.Z`. The pushed `v*` tag triggers `.github/workflows/build_and_release.yml`, which first fails if the tag doesn't match `__version__`, then builds macOS/Linux/Windows artifacts and publishes a GitHub release. (The `/release` skill automates this.)

## Behavioral Guidelines

**Before implementing, think first:**
- State assumptions explicitly. If uncertain, ask — don't pick an interpretation silently.
- If multiple approaches exist, present them with tradeoffs. If a simpler one exists, say so.
- If something is unclear, stop. Name what's confusing. Ask.
- Push back when warranted — including on the user's request if it would introduce unnecessary complexity.

**Simplicity is the priority:**
- Minimum code that solves the problem. No speculative features, no premature abstractions, no "flexibility" that wasn't requested.
- If you spot unnecessary complexity while working (wrappers that do nothing, abstractions with one implementation, code that reimplements a built-in), simplify it.
- Don't introduce new abstractions unless something is used in three or more places. When in doubt, inline it.
- If you write 200 lines and it could be 50, rewrite it.

**THE SENIOR DEV OVERRIDE:**
If architecture is flawed, state is duplicated, or patterns are inconsistent — propose and implement structural fixes. Ask: "What would a senior, perfectionist dev reject in code review?" Fix all of it.

**When simplifying or refactoring:**
- State what you changed and why — don't silently refactor alongside a feature change.
- No cosmetic-only changes (reformatting, style renames) unless asked.
- When your changes create orphans, remove them. When you find pre-existing dead code, remove it and call it out.

**Goal-driven execution:**
- Turn tasks into verifiable goals: "fix the bug" → write a failing test that reproduces it, then make it pass.
- For multi-step tasks, state a brief plan with verification checks before starting.
- Run `uv run pytest` (or a targeted subset) to verify changes don't break existing tests.

## Architecture

### Enum-Keyed Registry Pattern (central design)

All assay types are registered in `core/assays/registry.py` via `ASSAY_REGISTRY: dict[AssayType, AssayMetadata]`. The `AssayType` enum drives dispatch throughout — **no isinstance checks**. Each `AssayMetadata` defines parameter keys, default bounds, log-scale keys, units, and labels.

### Module Layers

| Layer | Path | Responsibility |
|-------|------|----------------|
| **Assays** | `core/assays/` | `BaseAssay` ABC + subclasses; each wraps a forward model reference |
| **Models** | `core/models/` | Pure, unit-free math: `equilibrium.py`, `linear.py` |
| **Optimizer** | `core/optimizer/` | Stateless multi-start L-BFGS-B: `multistart`, result filtering, robust aggregation (median + MAD), scaling, linear fit |
| **Pipeline** | `core/pipeline/` | Orchestration: `fit_assay()`, `FitConfig`, `FitResult` (`fit_pipeline.py`) |
| **Data Processing** | `core/data_processing/` | `MeasurementSet` (immutable 2D container), Z-score replica filter, concentration helpers, `prepare_plot_data()` (`plotting.py`) |
| **I/O** | `core/io/` | Strategy pattern with explicit dict registries (no decorators); readers per format under `io/formats/` (BMG/csv/ensight/jasco/txt/xlsx) + measurement writer |
| **Units** | `core/units.py` | pint `UnitRegistry` singleton; plain `dict[str,str]` unit tables (`PARAM_UNITS`, `CONDITION_UNITS`); custom `au` unit for signals |
| **GUI shell** | `gui/main_window.py` | `FittingMainWindow` + `launch()` entry point; sets `QLocale` (English/US) before `QApplication`; triggers a silent update check on startup |
| **GUI session** | `gui/fitting_session.py` | `FittingSession` — one tab: owns state, wires all panels, dispatches the fit |
| **GUI state** | `gui/app_state.py` | `AppState` dataclass — mutable session state (`ms`, `fit_results`, …) |
| **GUI workers** | `gui/workers.py` | `FitWorker` QThread — runs the fit off the main thread, emits `fit_complete`/`fit_error` |
| **GUI widgets** | `gui/widgets/` | `AssayConfigPanel`, `BoundsPanel`, `DataPanel`, `FitConfigPanel`, `PreprocessingPanel`, `ReplicaPanel` + shared inputs (`numeric_inputs.py`, `info_button.py`) |
| **GUI plotting** | `gui/plotting/` | `PlotWidget`, `FitSummaryWidget`, `PlotStyleWidget`, `DistributionWidget`; labels in `labels.py`, colors in `colors.py`, image export in `export.py` (PyQtGraph native) |
| **GUI dialogs** | `gui/dialogs/` | `ExportMultipleDialog`, `SaveDistributionsDialog` — modal dialogs invoked from the toolbar |
| **Auto-update** | `gui/update_check.py`, `gui/update_dialog.py`, `gui/download_worker.py` | Compares latest GitHub release against `_version.py`; prompts and downloads if newer |

### Fitting Pipeline Flow

`load_measurements()` → `MeasurementSet` → `.to_assay()` → `BaseAssay` → `fit_assay(assay, FitConfig)` → multi-start L-BFGS-B → filter by RMSE/R² → aggregate via median + MAD → `FitResult`

### GUI Plotting Flow

`prepare_plot_data(ms, fit_results)` → `PlotWidget.update_plot(plot_data)` + `PlotWidget.set_fit_results(results)` → `PlotStyleWidget` emits `style_changed` → `PlotWidget.apply_style(style)`

- `PlotWidget` has **no dependency on `ASSAY_REGISTRY`** — the caller passes axis labels as plain strings. HTML math labels live in `gui/plotting/labels.py` (`fmt_param()`). Value/unit formatting uses Pint's built-in `~P` (pretty Unicode) and `~H` (HTML) formatters.
- **PyQtGraph timing gotcha:** `ScientificAxisItem.tickStrings()` runs during deferred Qt paint, not synchronously after `updateAutoRange()`. Axis exponents are propagated via `on_exponent_changed` callbacks (fired from `_set_exponent()` with a change guard to prevent recursion). **Never read `axis.exponent` directly after `update_plot()`** — use the callback pattern.

### Named Parameter Handling

Parameters use **string keys**, not positional indices. `FitConfig.custom_bounds` is `Dict[str, Tuple[float, float]]`, merged with registry defaults via `_resolve_bounds()`. Log-scale params resolve the same way.

## Scientific Conventions

- **Association constants only** (Ka, never Kd): `Ka_dye` for host–dye, `Ka_guest` for host–guest binding.
- **4-parameter signal model:** `Signal = I0 + I_dye_free·[D_free] + I_dye_bound·[HD]`.
- Signal coefficients (`I0`, `I_dye_free`, `I_dye_bound`) are **structurally degenerate** in DBA/IDA — only Ka is identifiable. Tests verify Ka recovery + signal reconstruction, never the individual coefficients.
- Concentrations are stored internally in **Molar**; GUI inputs (nM/µM/mM/M, M⁻¹/kM⁻¹/MM⁻¹) convert to base units at the boundary.
- Example datasets with reference parameters live in `data/` (see `data/Readme.md`).

## Testing

Tests verify **scientific correctness first** — reproduce a bug as a failing test, then make it pass. See `tests/CLAUDE.md` for the full philosophy: the three pillars (scientific validity, data integrity, fail-fast contracts), how to avoid tautological/trivial tests, tolerance bands, and the shared synthetic ground truth in `tests/conftest.py`. Layout: `tests/unit/` (fast), `tests/unit/gui/` (PyQt6 widgets), `tests/integration/` (slow real fits).

## Adding a New Assay Type

1. Add an enum value to `AssayType` in `core/assays/registry.py`.
2. Create a `BaseAssay` subclass with a `forward_model()` implementation.
3. Add an `ASSAY_REGISTRY` entry with metadata (keys, bounds, log-scale, units, labels).
4. Add the forward-model math in `core/models/`.
5. Add tests (parameter recovery + fail-fast).

## GUI Conventions

- **No silent fallbacks:** any unmet precondition must show `QMessageBox.warning()` with an explanation and fix instructions. Never silently skip or default. App behaviour must always reflect the user's configuration exactly.
- **Unit-aware inputs:** `_UnitWidget` in `assay_config_panel.py` always returns base-unit floats (M or M⁻¹) regardless of display unit.
- **Locale:** `QLocale.setDefault(English/US)` in `launch()` before `QApplication` — guarantees dot decimal separators in all spinboxes.
- **HTML labels:** `ConditionField.label` is HTML; render with `lbl.setTextFormat(Qt.TextFormat.RichText)`. Use subscript/superscript consistently.
- The outlier-removal panel is labelled **"Outlier Removal"**. "Load Data" (Ctrl+O) on the toolbar is the only load entry point.

## Code Style

- PEP 8, formatted and linted with **ruff** (`uv run ruff format` / `uv run ruff check`).
- Numpy-style docstrings; type hints on all public methods.
- Prefer dataclasses, pure functions, and explicit dict registries over complex abstractions.
- Prefer built-ins and framework primitives over custom helpers — replace, don't wrap.

## Commit Messages

Format: `<type>: <subject>` — types: `feat`, `fix`, `refactor`, `chore`, `docs`, `style`, `test`, `perf`, `ci`. Imperative mood, < 72 chars. Body only if not self-explanatory; focus on **why**, not what — no implementation play-by-play or historical narrative. Optional `scope:` footer. **No `Co-Authored-By` trailers.**
