# CLAUDE.md

Guidance for Claude Code when working in this repository.

## graphify (NON-NEGOTIABLE)

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review, or when query/path/explain don't surface enough. (There is no `wiki/` — it is not generated or tracked.)

**The graph is a `main`-only artifact.** graph.json / GRAPH_REPORT.md / manifest.json are committed on `main` only and refreshed there by a local `post-merge` hook (`graphify update . --force`, then auto-commit). Each Claude session runs in its own worktree on a feature branch and **inherits main's committed graph**.
- **Never stage or commit `graphify-out/` on a feature branch.** You may run `graphify update .` locally so your queries reflect in-session edits, but leave it uncommitted (or `git checkout -- graphify-out` to discard) — only `main` mutates the tracked graph.
- **Multi-session / multi-agent reality:** sessions run concurrently in separate worktrees off the same `main` (shared `.git`, separate working copies). The committed graph reflects `main` at your branch point — not your branch's WIP, and not other sessions' WIP. Don't assume it's current for code changed in-session; refresh locally if it matters. Do **not** reintroduce a git merge driver for graph.json — graphify's `merge-driver`/`merge-graphs` are naive unions (no base) that resurrect deleted nodes; correctness comes only from re-extraction.
- **Plausibility check after a merge.** The post-merge hook uses `--force`, which bypasses graphify's shrink-guard, so once a merged PR lands on `main` verify the refresh before trusting the graph: graph.json parses; node/edge counts are sane (not collapsed, not wildly inflated vs. the previous commit); nodes for files deleted in the PR are gone and new files are present; spot-check with a `graphify query` on a file the PR touched. If it looks wrong, rebuild from scratch instead of trusting the incremental result.

## Project Overview

SupraSimFit — a desktop toolkit that fits equilibrium binding models to fluorescence titration data by variable projection, extracting association constants (Ka) with a profile-likelihood confidence interval via rigorous forward-modelling rather than linearised transforms. Assay types: `GDA`, `IDA`, `DBA_HtoD`, `DBA_DtoH`, `DBA_HG2`, `DBA_H2G`, `DYE_ALONE`.

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
- Before implementing an established scientific or numerical method (sensitivity analysis, bootstrap, profile likelihood, …), look for a maintained library that provides it and present it as an option, with its tradeoffs, before writing a custom implementation. Never drop an option silently to avoid a dependency; ask.

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

All assay types are registered in `core/assays/registry.py` via `ASSAY_REGISTRY: dict[AssayType, AssayMetadata]`. The `AssayType` enum drives dispatch throughout — **no isinstance checks**. Each `AssayMetadata` defines parameter keys, default bounds, log-scale keys, units, labels, `param_kinds` + `signal_species` (which the fit engine reads to build its design matrix), and the `category` + `subtype_label` strings that drive the GUI's two-level (category → subtype) assay selector.

### Module Layers

| Layer | Path | Responsibility |
|-------|------|----------------|
| **Assays** | `core/assays/` | `BaseAssay` ABC + subclasses; each wraps a forward model reference |
| **Models** | `core/models/` | Pure, unit-free math: `equilibrium.py`, `linear.py` |
| **Optimizer** | `core/optimizer/` | Numerical helpers around the fit: `calculate_fit_metrics` (filters.py), `describe`/`describe_log10` summary stats (ensemble.py), `linear_regression` (linear_fit.py) |
| **Fit engine** | `core/pipeline/varpro.py` | Variable projection: `Projection` (bounded linear solve of the signal parameters at a fixed Ka, log-grid search + refinement over the Ka, profile, `KaInterval`), `replicate_outliers()`, `projectable()`. Pure numerics on an assay, its bounds and one or more signal rows |
| **Pipeline** | `core/pipeline/` | Orchestration: `fit_assay()`, `fit_measurement_set()`, `FitConfig`, `FitResult`, `summarize_parameters()` (`fit_pipeline.py`) |
| **Ka profile** | `core/pipeline/profile.py` | Curves for the Identifiability tab, built on the engine: `fit_profile()` → `ProfileSet` (one `ProfileResult` per Ka plus the two-Ka `JointRegion`) |
| **Ka sensitivity** | `core/pipeline/sensitivity.py` | `run_sensitivity()` → `SensitivityResult`: Sobol' (`sobol_design`, `sobol_indices_with_ci`) and heatmap runs over perturbed inputs; `perturbable_inputs()`, `InputSpec`, worker-process fan-out |
| **Data Processing** | `core/data_processing/` | `MeasurementSet` (immutable 2D container), Z-score replica filter, concentration helpers, `prepare_plot_data()` (`plotting.py`) |
| **I/O** | `core/io/` | Strategy pattern with explicit dict registries (no decorators); readers per format under `io/formats/` (BMG/csv/ensight/jasco/txt/xlsx) + measurement writer |
| **Units** | `core/units.py` | pint `UnitRegistry` singleton; plain `dict[str,str]` unit tables (`PARAM_UNITS`, `CONDITION_UNITS`); custom `au` unit for signals |
| **GUI shell** | `gui/main_window.py` | `FittingMainWindow` + `launch()` entry point; sets `QLocale` (English/US) before `QApplication`; triggers a silent update check on startup |
| **GUI session** | `gui/fitting_session.py` | `FittingSession` — one tab: owns state, wires all panels, dispatches the fit |
| **GUI state** | `gui/app_state.py` | `AppState` dataclass — mutable session state (`ms`, `fit_results`, …) |
| **GUI workers** | `gui/workers.py` | `FitWorker`, `ProfileWorker`, `SensitivityWorker` QThreads — run the fit, the Ka profile and the sensitivity analysis off the main thread; each emits `finished`/`error`, and `SensitivityWorker` also emits `progress(done, total)` and `stopped()` (a cancel that lands before the baseline fit) |
| **GUI widgets** | `gui/widgets/` | `AssayConfigPanel`, `BoundsPanel`, `DataPanel`, `FitConfigPanel`, `PreprocessingPanel`, `ReplicaPanel`, `SensitivityPanel` (per-input uncertainties, mode and sample size) + shared inputs (`numeric_inputs.py`, `info_button.py`) |
| **GUI plotting** | `gui/plotting/` | `PlotWidget`, `FitSummaryWidget`, `PlotStyleWidget`, `IdentifiabilityWidget` (Ka profiles and the joint region), `SensitivityWidget` (Ka Sensitivity tab); labels and interval formatters in `labels.py`, colors in `colors.py`, image export in `export.py` (PyQtGraph native) |
| **GUI dialogs** | `gui/dialogs/` | `ExportMultipleDialog`, `PreferencesDialog`, `PlotGuideDialog` — modal dialogs invoked from the toolbar and menus |
| **GUI help** | `gui/plot_guide.py`, `gui/dialogs/plot_guide_dialog.py` | "Reading the plots" guide: one HTML section per plot tab, opened from the Help menu |
| **Calibration scripts** | `scripts/` | Standalone coverage checks of the profile interval and the Sobol' index intervals; see `scripts/README.md` |
| **Auto-update** | `gui/update_check.py`, `gui/update_dialog.py`, `gui/download_worker.py` | Compares latest GitHub release against `_version.py`; prompts and downloads if newer |

### Fitting Pipeline Flow

`load_measurements()` → `MeasurementSet` → `.to_assay()` → `BaseAssay` → `fit_assay(assay, FitConfig)` → `Projection` (signal parameters by bounded linear least squares, Ka by log-grid search + refinement) → profile-likelihood interval per Ka → `FitResult`

A per-replicate fit (`fit_measurement_set_per_replica`) builds one `Projection` over all
replicate rows, runs `replicate_outliers()` to decide which replicates share a Ka, and
reports the fit of the average of the ones kept, with each replicate's own fit in
`replica_fits`.

**Reporting is derived, never stored.** `FitResult` keeps the fit's `parameters` and the
`KaInterval` of each binding constant; every reported row comes from
`summarize_parameters(result)` (`core/pipeline/fit_pipeline.py`), which the plot
annotation, the summary table and the TXT/CSV exports all render from. The headline form
is **`Estimate [low, high]`** — the fit, and the range of values the same data do not
reject at the stated level. Both come from one projection of one set of replicates; a
centre from one estimator paired with a spread from another describes no distribution.

### GUI Plotting Flow

`prepare_plot_data(ms, fit_results)` → `PlotWidget.update_plot(plot_data)` + `PlotWidget.set_fit_results(results)` → `PlotStyleWidget` emits `style_changed` → `PlotWidget.apply_style(style)`

- `PlotWidget` has **no dependency on `ASSAY_REGISTRY`** — the caller passes axis labels as plain strings. HTML math labels live in `gui/plotting/labels.py` (`fmt_param()`). Value/unit formatting uses Pint's built-in `~P` (pretty Unicode) and `~H` (HTML) formatters.
- **PyQtGraph timing gotcha:** `ScientificAxisItem.tickStrings()` runs during deferred Qt paint, not synchronously after `updateAutoRange()`. Axis exponents are propagated via `on_exponent_changed` callbacks (fired from `_set_exponent()` with a change guard to prevent recursion). **Never read `axis.exponent` directly after `update_plot()`** — use the callback pattern.

### Named Parameter Handling

Parameters use **string keys**, not positional indices. `FitConfig.custom_bounds` is `Dict[str, Tuple[Quantity, Quantity]]`, merged with registry defaults via `_resolve_bounds()`.

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
2. Create a `BaseAssay` subclass with `forward_model()` and `species()` implementations — the engine builds its design from `species()`, so the two must come from the same solve.
3. Add an `ASSAY_REGISTRY` entry with metadata (keys, bounds, log-scale, units, labels, `param_kinds`, `signal_species`, and `category` + `subtype_label` — the latter two slot it into the two-level assay menu; no widget code changes needed).
4. Add the forward-model math in `core/models/`.
5. Add tests (parameter recovery + fail-fast).

A model with one or two binding constants whose other parameters are all signal
offset or signal coefficient fits with no engine change: `projectable()` reads that
off the registry. Anything else it refuses by name.

## GUI Conventions

- **No silent fallbacks:** any unmet precondition must show `QMessageBox.warning()` with an explanation and fix instructions. Never silently skip or default. App behaviour must always reflect the user's configuration exactly.
- **User-facing messages are for users, not developers:** every error, warning, and dialog must be plain language a non-technical user understands — stating what happened, why, and what to do next, and naming the specific inputs involved (e.g. offending files/values) when it helps. Keep them as short and precise as the situation allows — no lengthiness. Never surface raw exception text, tracebacks, or library/debug phrasing (e.g. a numpy broadcast error); catch low-level errors at the boundary and translate them.
- **Unit-aware inputs:** `_UnitWidget` in `assay_config_panel.py` always returns base-unit floats (M or M⁻¹) regardless of display unit.
- **Locale:** `QLocale.setDefault(English/US)` in `launch()` before `QApplication` — guarantees dot decimal separators in all spinboxes.
- **HTML labels:** `ConditionField.label` is HTML; render with `lbl.setTextFormat(Qt.TextFormat.RichText)`. Use subscript/superscript consistently.
- The outlier-removal panel is labelled **"Outlier Removal"**. "Load Data" (Ctrl+O) on the toolbar is the only load entry point.

## Code Style

- PEP 8, formatted and linted with **ruff** (`uv run ruff format` / `uv run ruff check`).
- Numpy-style docstrings; type hints on all public methods.
- Prefer dataclasses, pure functions, and explicit dict registries over complex abstractions.
- Prefer built-ins and framework primitives over custom helpers — replace, don't wrap.

## Documentation and Docstrings

Describe the **present state as it is**. A docstring, comment, or doc file says what
the code does now — not what it used to do, what it stopped doing, or what was
considered and rejected on the way here.

- **No "not X" framing where X is a past or rejected approach.** "the estimate is a
  real fit, *not a synthetic average*"; "this *no longer* stores the spread"; "*unlike
  the old* registry lookup". State the positive fact and stop.
- **No migration narrative or deprecation history** — "superseded by", "we moved away
  from", "kept for backward compatibility with the old…". Git holds that. A reader who
  wasn't part of the decision only sees noise, and the note rots as soon as the thing
  it contrasts against is forgotten.
- **Rationale is welcome; history is not.** "Sampled on a log scale because Ka spans
  ten orders of magnitude" is rationale. "Sampled on a log scale after linear sampling
  failed" is history.
- **Exception — keep the contrast when the comparison *is* the information.** Two
  cases qualify: a genuine methodological trade-off between approaches a reader might
  actually choose between (the Scatchard/Hill discussion in `Readme.md`), and a
  non-obvious constraint they would otherwise violate. Write the second as a rule
  about the present — "statistics of log₁₀(Ka) must come from the per-fit log values,
  because log₁₀ of a Ka spread is meaningless" — never as a story about a past bug.
- A constraint imposed by data already on disk is present-tense, not history. Say the
  `replicate` token is the on-disk value in exported JSON and therefore part of that
  file format — not that it is *kept for backward compatibility*.

Applies to docstrings, inline comments, `Readme.md`, `docs/`, and these instruction
files alike. One genre is exempt because its subject *is* the past: a dated audit or
postmortem under `docs/` records what was found and what was done. Leave those as
written — and do not annotate them with later changes either. When the code has moved
on, the current behaviour belongs in the live reference, not as a footnote on the
record.

## Commit Messages

Format: `<type>: <subject>` — types: `feat`, `fix`, `refactor`, `chore`, `docs`, `style`, `test`, `perf`, `ci`. Imperative mood, < 72 chars. Body only if not self-explanatory; focus on **why**, not what — no implementation play-by-play or historical narrative. Optional `scope:` footer. **No `Co-Authored-By` trailers.**

## Pull Request Descriptions

Write PR descriptions for a human reviewer, not as a changelog of the diff. Briefly cover:
- **Why** — the need, bug, or pain point this addresses (link the issue with `Closes #N`).
- **What changed** — the gist at a high level, not a file-by-file account; the diff already shows the code.
- **How to verify** — what a reviewer can do to confirm it works (a command, a UI action, a test to run).
- **Anything to flag** — a tradeoff, a follow-up, a risk, or a screenshot for UI changes.

These are guidelines, not a rigid template — a few clear sentences beat an exhaustive checklist; omit what doesn't apply.
