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

SupraSimFit — a desktop toolkit that fits equilibrium binding models to fluorescence titration data by variable projection, extracting association constants (Ka) with a profile-likelihood confidence interval — optionally input-aware, covering the uncertainty of the entered conditions as well — via rigorous forward-modelling rather than linearised transforms. Assay types: `GDA`, `IDA`, `DBA_HtoD`, `DBA_DtoH`, `DBA_HG2`, `DBA_H2G`, `DYE_ALONE`.

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
| **Assays** | `core/assays/` | `BaseAssay` ABC + subclasses; each wraps a forward model reference. Two optional keyword-only conditions declare dilution by the titrant — `titrant_stock` and `stock_contains` — and `fixed_total(key, x)` is what every `forward_model` / `species` reads a fixed total from; `_check_dilution()` (last statement of each subclass `__post_init__`) refuses a stock the data contradict |
| **Models** | `core/models/` | Pure, unit-free math: `equilibrium.py`, `linear.py` |
| **Optimizer** | `core/optimizer/` | Numerical helpers around the fit: `calculate_fit_metrics` (filters.py), `describe`/`describe_log10` summary stats (ensemble.py), `linear_regression` (linear_fit.py) |
| **Fit engine** | `core/pipeline/varpro.py` | Variable projection: `Projection` (bounded linear solve of the signal parameters at a fixed Ka, log-grid search + refinement over the Ka, profile, `KaInterval`, `residual()` / `inner_start()` at shifted inputs, `one_step_p()` — the test of the model without the second step that opens the second constant's interval below above `SECOND_STEP_LEVEL`), `replicate_outliers()`, `projectable()`. Pure numerics on an assay, its bounds and one or more signal rows |
| **Noise law** | `core/pipeline/noise.py` | What the replicates say about how precise each titration point is: `replicate_scatter()` (each replicate about its own affine image of the mean curve, whitened, with the leverages) and `noise_law()` → `NoiseLaw` — the `NoiseBasis` it rests on, the `share` of the two-component law `var(y) = floor² + (proportional·y)²`, `relative_variance(signal, share)` and `weights(signal)` (one vector over the titration points, `np.ones` where no law could be read or its share is zero; `u = signal²/reference²` clipped below at `u_floor`, the smallest `u` among the points that scatter, read off the curve the caller passes), `share_set` (the shares the replicates accept at 99 %), `level` (the variance at the rms signal), `describe()` (the `Noise:` sentence the summary, the report and the CSV carry) and `to_dict()` / `from_dict()`. Deterministic, drawn before the fit |
| **Inputs** | `core/pipeline/inputs.py` | What the user states about the entered inputs, as one `ErrorModel` of independent sources: each input's own `InputSpec` (σ or range, relative or absolute), the named `SharedSource`s that move two or more inputs together (`shared_key()`, `input_offsets()` maps source offsets to input offsets), and the `AdditionError` of each titrant addition (`perturb_titrant()`, `addition_loading()`; `separate_titrations` says whether the replicates are titrations of their own or repeated reads of one), which widens the reported interval through `core/pipeline/inflation.py` and is sampled by the sensitivity analysis. Plus `perturbable_inputs()`, `TITRANT`, `TITRANT_STOCK`, `ADDITIONS`, the `InputConstraint` tuple `constraints()` hands to the fit (one per source), `validate()`, `source_name()`, and `to_dict()` / `from_dict()` for the results file. Shared by the interval and the sensitivity analysis |
| **Input-aware interval** | `core/pipeline/input_aware.py` | `input_aware()` → `AwareResult`: the penalised profile of each Ka with the entered inputs free inside their stated uncertainties (`AwareFit`, `AwareProfile`), `fit_jacobian()`, `misfit_design()` (the columns of the counted parameters, for the lack-of-fit bootstrap), `conflict()`, `input_shifts()` |
| **Interval widening** | `core/pipeline/inflation.py` | `inflation()` → one design effect κ ≥ 1 per Ka (`KaInterval.inflation`), widening its cut-off to `S_min (1 + κ m F/ν)`: the sandwich variance of the Ka under the covariance a stated error of the additions (`addition_signal_loading()`) and the shares a noise law leaves open (`NoiseLaw.share_set`) put on the residual, over the variance the profile assumes; `joint_inflation()` for the two-Ka joint region (`FitResult.joint_inflation`, which carries the additions too); `replicate_scatter_ssr()` (each separate titration's residual with its own addition residue taken out, for Cochran's step of the replicate test); `paule_mandel()`. Exactly 1.0, computed from nothing, without a law of positive share and without additions |
| **Diagnostics** | `core/pipeline/diagnostics.py` | Pure functions on arrays: `lack_of_fit()` / `runs_test()` (does the curve miss the data; with an estimated noise law or a stated error of the additions the lack-of-fit p-value comes from a parametric bootstrap, `MisfitTest.reference == 'bootstrap'`, whose draws carry the addition offsets (`AdditionDraws`), else from F; the runs reference is drawn with the additions' covariance where they are stated), `conflict_reference()` / `conflict_test()` / `conflict_p_value()` (did the inputs move further than stated; with a stated error of the additions the reference carries the share of them a fit free to move the inputs puts there, `conflict_added()`), `verdict()` → `FitDiagnostics` |
| **Pipeline** | `core/pipeline/` | Orchestration: `fit_assay()`, `fit_measurement_set()`, `FitConfig`, `FitResult` (with `point_weights` and `profile_arguments()`), `ConditionalFit`, `summarize_parameters()`, `reports_conditional()` (`fit_pipeline.py`) |
| **Ka profile** | `core/pipeline/profile.py` | Curves for the Identifiability tab, built on the engine: `fit_profile()` → `ProfileSet` (one `ProfileResult` per Ka, each carrying the conditional curve and the `AwareProfile` beside it, plus the two-Ka `JointRegion`); it runs with the point weights and design effects the fit hands it (`FitResult.profile_arguments()`) and never reads the noise law itself |
| **Ka sensitivity** | `core/pipeline/sensitivity.py` | `run_sensitivity()` → `SensitivityResult`: Sobol' (`sobol_design`, `sobol_indices_with_ci` → `SobolEstimate`) and heatmap runs over the same `ErrorModel`, each sample one fixed-input fit; indices are per **source**, with the per-addition offsets taken from `B` as one column group; the absolute budget (`Budget`, `BudgetRow`) with `what_if()` (pure: formula plus importance re-weighting) and `input_elasticities()` / `homogeneity_sum()`; worker-process fan-out |
| **Data Processing** | `core/data_processing/` | `MeasurementSet` (immutable 2D container), Z-score replica filter, concentration helpers, `prepare_plot_data()` (`plotting.py`) |
| **I/O** | `core/io/` | Strategy pattern with explicit dict registries (no decorators); readers per format under `io/formats/` (BMG/csv/ensight/jasco/txt/xlsx) + measurement writer |
| **Units** | `core/units.py` | pint `UnitRegistry` singleton; plain `dict[str,str]` unit tables (`PARAM_UNITS`, `CONDITION_UNITS`); custom `au` unit for signals |
| **GUI shell** | `gui/main_window.py` | `FittingMainWindow` + `launch()` entry point; sets `QLocale` (English/US) before `QApplication`; triggers a silent update check on startup |
| **GUI session** | `gui/fitting_session.py` | `FittingSession` — one tab: owns state, wires all panels, dispatches the fit |
| **GUI state** | `gui/app_state.py` | `AppState` dataclass — mutable session state (`ms`, `fit_results`, …) |
| **GUI workers** | `gui/workers.py` | `FitWorker`, `ProfileWorker`, `SensitivityWorker` QThreads — run the fit (interval, input-aware interval and diagnostics together), the Ka profile and the sensitivity analysis off the main thread; each emits `finished`/`error`, `ProfileWorker` takes the `FitResult` it profiles, and `SensitivityWorker` also emits `progress(done, total)` and `stopped()` (a cancel that lands before the baseline fit) |
| **GUI widgets** | `gui/widgets/` | `AssayConfigPanel`, `BoundsPanel`, `DataPanel`, `FitConfigPanel`, `InputUncertaintyPanel` (the one place uncertainties are stated: per-input σ / range / fixed, the named shared error sources, and the random error of each addition — `current_errors()` → `ErrorModel`, shared by the interval and the sensitivity analysis), `PreprocessingPanel`, `ReplicaPanel`, `SensitivityPanel` (mode, sample size, heatmap axes, seed) + shared inputs (`numeric_inputs.py`, `info_button.py`) |
| **GUI plotting** | `gui/plotting/` | `PlotWidget`, `FitSummaryWidget`, `PlotStyleWidget`, `IdentifiabilityWidget` (Ka profiles and the joint region), `SensitivityWidget` (Ka Sensitivity tab); labels and interval formatters in `labels.py`, colors in `colors.py`, image export in `export.py` (PyQtGraph native) |
| **GUI dialogs** | `gui/dialogs/` | `ExportMultipleDialog`, `PreferencesDialog`, `PlotGuideDialog` — modal dialogs invoked from the toolbar and menus |
| **GUI help** | `gui/plot_guide.py`, `gui/dialogs/plot_guide_dialog.py` | "Reading the plots" guide: one HTML section per plot tab, opened from the Help menu |
| **Validation** | `validation/` | The synthetic-data generators, the scoring and the result store behind every rate the app states: `python -m validation run <check>` computes rows, `python -m validation tables` renders them, `python -m validation compare <code hash>` asserts that two builds produced the same rows field for field; the budget and what-if checks live in `validation/budget.py`; see `validation/README.md` |
| **Auto-update** | `gui/update_check.py`, `gui/update_dialog.py`, `gui/download_worker.py` | Compares latest GitHub release against `_version.py`; prompts and downloads if newer |

### Fitting Pipeline Flow

`load_measurements()` → `MeasurementSet` → `.to_assay()` → `BaseAssay` → `fit_assay(assay, FitConfig)` → `noise_law(replicate_signals)` → `Projection` (point weights from that law — where its share is above zero, two-stage: a first fit at the weights of the means, then the weights read off its fitted curve and one refit, recorded as `FitResult.point_weights` — signal parameters by bounded weighted linear least squares, Ka by log-grid search + refinement) → `inflation()` (the design effect of the law's share set) → profile-likelihood interval per Ka (the **conditional** fit and interval, every entered input taken as exact, cut-off widened by that design effect) → `input_aware()` with the constraints of `FitConfig.errors` — one per error source, an input's own or a shared one (penalised profile: each Ka against the best fit reachable while the inputs move inside their stated uncertainties, a `loading` map turning source offsets into input offsets), its cut-off widened by the design effect of the law and of the stated error of the additions → `diagnostics` (misfit test at both fits — against F, or against a bootstrap at the noise law and the additions where the replicates showed a law or additions are stated — conflict statistic, `verdict()`) → `FitResult`

With no uncertainty and no error of the additions stated — how the Input Uncertainty
panel opens — `input_aware()` returns the conditional interval objects themselves, so a fit of exact inputs costs
nothing extra and reports one interval. A titration with no titrant stock and no shared
source must give bit-identical numbers: `fixed_total()` hands the model the entered
scalar, so the equilibrium arithmetic is the scalar one operation for operation and in
the same order; `input_offsets()` is the identity; and `get_conditions()` / `fit_config`
carry no dilution or shared-source key. Any change on that path has to preserve all
three.

The same holds for the weights. A single titration, and any set of replicates whose
noise law comes out constant, gets `np.ones` from `NoiseLaw.weights()`, no refit, and
every design effect exactly 1.0; `Projection` whitens by `sqrt` of that, so every solve
multiplies by exactly 1.0 and the fit and the interval are those of an engine with no
weights at all, to the last bit, and so are the diagnostics of a single titration.
Arithmetic on that path is not to be reordered. The lack-of-fit p-value of replicates is
read against the parametric bootstrap whenever their law was estimated, constant or not
(`law.estimated`), or an error of the additions is stated, and against F otherwise.

A per-replicate fit (`fit_measurement_set_per_replica`) builds one `Projection` over all
replicate rows, runs `replicate_outliers()` to decide which replicates share a Ka — for
replicates stated as separate titrations with an error of the additions, at each
replicate's own design effect and with its addition residue out of Cochran's step — and
reports the fit of the average of the ones kept, with each replicate's own fit in
`replica_fits`; those per-replicate fits stay conditional, and are made with the weights a
fit of the average of the replicates given runs with (two-stage where the share is above
zero) while carrying no `noise` of their own — a sentence about the scatter
of several replicates does not describe a result whose data are one of them. In either
mode the signals of the replicates used reach `fit_assay` as `replicate_signals`, which
is what the noise law and the lack-of-fit F test are read from.

**Reporting is derived, never stored.** `FitResult` keeps the fit's `parameters`, the
`KaInterval` of each binding constant and the `ConditionalFit` beside it; every reported
row comes from `summarize_parameters(result)` (`core/pipeline/fit_pipeline.py`), which
the plot annotation, the summary table and the TXT/CSV exports all render from. The
headline form is **`Estimate [low, high]`** — the input-aware fit and its interval
wherever an input may move or an error of the additions is stated, the conditional ones
otherwise (`reports_conditional()`) — and the conditional `estimate [low, high]` is filled
in beside it in the first case. Both ends of a pair
come from one projection of one set of replicates; a centre from one estimator paired
with a spread from another describes no distribution.

### GUI Plotting Flow

`prepare_plot_data(ms, fit_results)` → `PlotWidget.update_plot(plot_data)` + `PlotWidget.set_fit_results(results)` → `PlotStyleWidget` emits `style_changed` → `PlotWidget.apply_style(style)`

- `PlotWidget` has **no dependency on `ASSAY_REGISTRY`** — the caller passes axis labels as plain strings. HTML math labels live in `gui/plotting/labels.py` (`fmt_param()`). Value/unit formatting uses Pint's built-in `~P` (pretty Unicode) and `~H` (HTML) formatters.
- **PyQtGraph timing gotcha:** `ScientificAxisItem.tickStrings()` runs during deferred Qt paint, not synchronously after `updateAutoRange()`. Axis exponents are propagated via `on_exponent_changed` callbacks (fired from `_set_exponent()` with a change guard to prevent recursion). **Never read `axis.exponent` directly after `update_plot()`** — use the callback pattern.

### Named Parameter Handling

Parameters use **string keys**, not positional indices. `FitConfig.custom_bounds` is `Dict[str, Tuple[Quantity, Quantity]]`, merged with registry defaults via `_resolve_bounds()`. `FitConfig.errors` is the one `ErrorModel` a fit reads; `FitResult.input_shifts` is keyed by **source** key, which is an input key for an input's own uncertainty and `shared_key(name)` for a shared source.

## Scientific Conventions

- **Association constants only** (Ka, never Kd): `Ka_dye` for host–dye, `Ka_guest` for host–guest binding.
- **4-parameter signal model:** `Signal = I0 + I_dye_free·[D_free] + I_dye_bound·[HD]`.
- Signal coefficients (`I0`, `I_dye_free`, `I_dye_bound`) are **structurally degenerate** in DBA/IDA — only Ka is identifiable. Tests verify Ka recovery + signal reconstruction, never the individual coefficients.
- Concentrations are stored internally in **Molar**; GUI inputs (nM/µM/mM/M, M⁻¹/kM⁻¹/MM⁻¹) convert to base units at the boundary.
- **Entered inputs are exact until the user says otherwise.** Every row of the Input Uncertainty panel opens *fixed*, no shared source is present and the additions entry reads *none*, so a fit reports the conditional interval as its headline until an error source is stated. The sensitivity analysis needs at least one varying source and says so in plain language when none is set.
- **Totals stay constant until the user says otherwise.** The conditions form opens on *stay constant*; declaring a titrant stock is the user's explicit statement, and the concentrations in a data file are the titrant concentrations in the cuvette **after** each addition.
- **Homogeneity.** Scaling every concentration by `c` and every entered binding constant by `1/c` divides every fitted constant by `c`, so the elasticities of each fitted constant satisfy `Σ(concentrations) − Σ(entered binding constants) = −1`. A source loading every concentration therefore has elasticity `s_Ka_dye − 1` in a competitive assay (it largely cancels) and exactly `−1` in direct binding (it does not). Tested, never displayed.
- **A conflict is a statement about the inputs together.** The per-input shift says where the fit put the correction, not which input is wrong — several inputs move the curve almost alike, and a significant conflict can come with every shift under one σ. No message, help text or document may name one input as the cause.
- Example datasets with reference parameters live in `data/` (see `data/Readme.md`).

## Testing

Tests verify **scientific correctness first** — reproduce a bug as a failing test, then make it pass. See `tests/CLAUDE.md` for the full philosophy: the three pillars (scientific validity, data integrity, fail-fast contracts), how to avoid tautological/trivial tests, tolerance bands, and the shared synthetic ground truth in `tests/conftest.py`. Layout: `tests/unit/` (fast), `tests/unit/gui/` (PyQt6 widgets), `tests/integration/` (slow real fits).

## Adding a New Assay Type

1. Add an enum value to `AssayType` in `core/assays/registry.py`.
2. Create a `BaseAssay` subclass with `forward_model()` and `species()` implementations — the engine builds its design from `species()`, so the two must come from the same solve. Read every fixed total through `self.fixed_total(key, x)`, never `self.<key>.magnitude`, so the assay dilutes when a titrant stock is declared, and end `__post_init__` with `self._check_dilution()`.
3. Add an `ASSAY_REGISTRY` entry with metadata (keys, bounds, log-scale, units, labels, `param_kinds`, `signal_species`, and `category` + `subtype_label` — the latter two slot it into the two-level assay menu; no widget code changes needed).
4. Add the forward-model math in `core/models/`.
5. Add tests (parameter recovery + fail-fast).

A model with one or two binding constants whose other parameters are all signal
offset or signal coefficient fits with no engine change: `projectable()` reads that
off the registry. Anything else it refuses by name. The input-aware interval and the
sensitivity analysis need no assay code either — `perturbable_inputs()` classifies
the assay's own Quantity conditions by dimension (M → concentration, M⁻¹ → binding
constant) and adds the titrant, and `BaseAssay.with_inputs()` moves them generically.

## GUI Conventions

- **No silent fallbacks:** any unmet precondition must show `QMessageBox.warning()` with an explanation and fix instructions. Never silently skip or default. App behaviour must always reflect the user's configuration exactly.
- **User-facing messages are for users, not developers:** every error, warning, and dialog must be plain language a non-technical user understands — stating what happened, why, and what to do next, and naming the specific inputs involved (e.g. offending files/values) when it helps. Keep them as short and precise as the situation allows — no lengthiness. Never surface raw exception text, tracebacks, or library/debug phrasing (e.g. a numpy broadcast error); catch low-level errors at the boundary and translate them.
- **Unit-aware inputs:** `_UnitWidget` in `assay_config_panel.py` always returns base-unit floats (M or M⁻¹) regardless of display unit.
- **Locale:** `QLocale.setDefault(English/US)` in `launch()` before `QApplication` — guarantees dot decimal separators in all spinboxes.
- **HTML labels:** `ConditionField.label` is HTML; render with `lbl.setTextFormat(Qt.TextFormat.RichText)`. Use subscript/superscript consistently.
- The outlier-removal panel is labelled **"Outlier Removal"**. "Load Data" (Ctrl+O) on the toolbar is the only load entry point.
- The uncertainties of the entered inputs are stated once, in the **"Input Uncertainty"** panel (sidebar, under Assay Configuration), and feed both the headline interval and the Ka Sensitivity tab. The Sensitivity panel keeps only mode, sample size, heatmap axes and seed.

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
