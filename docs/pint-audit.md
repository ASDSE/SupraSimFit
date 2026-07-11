# Pint units audit — SupraSimFit

_Scientific-integrity audit of how Pint is integrated across the codebase, with
the remediation applied. Companion to [`pint-findings.md`](pint-findings.md) (the
usage reference). Every claim was verified by reading the code and running Pint in
the repo venv (pint 0.25.2); nothing was sampled._

## Method

Five parallel research passes — core numerical path, data-processing + I/O,
GUI + plotting/export, official Pint docs, and prior-art in scientific Python —
followed by lead re-verification of every load-bearing claim (reading the code
and executing Pint). Findings were fixed in staged, individually-tested commits.
The branch was then rebased onto `main` (PR #37 batch import, PR #38 ensemble
redesign) and a **full multi-agent re-audit** (38 agents: five lenses →
adversarial verify → synthesis + completeness critic) was run on the merged tree;
its findings are remediated in six further staged commits (see
[Re-audit after merging `main`](#re-audit-after-merging-main-pr-37--pr-38)). The
full suite is green after each stage.

## Verdict

**Before:** Pint was already well integrated — a single shared registry, a clear
boundary-normalization architecture, and a float-only numeric core matching
community best practice. **No active silent-wrong-result bug existed in normal
operation.** The real issues were *latent fragility*, *silent fallbacks*, *missing
runtime enforcement*, *self-describing-I/O gaps*, and one *serialization
degradation* — with the dimensionless `au` unit as the single highest scientific
risk.

**After:** `au` now carries its own `[signal]` dimension, parameter identity is
explicit (`ParamKind`) and lint-checked, unit correctness is validated at every
boundary crossing (at zero hot-loop cost), silent fallbacks are gone, TXT I/O is
self-describing, and conditions round-trip with their units. The signal law is now
dimensionally checkable end-to-end.

## Verified facts (empirical)

- `au` was dimensionless (`{}`), shadowing `astronomical_unit`; its `a.u.` symbol
  mis-parses (`ureg('1 a.u.')` → `year·atomic_mass_unit`).
- No Pint built-in for fluorescence/absorbance is usable — `fluorescence`,
  `RFU`, `absorbance`, `OD` undefined; `AU`, `count` exist but are dimensionless.
- `Q_(1,'M').to_base_units()` → `999.999… mol/m³` (×1000 + float noise).
- `Q_(3,'au/M').to('1/M')` silently returned `3/molar` (before), now raises.
- Runtime unit check cost: bare 3.2 µs/call; per-iteration `@ureg.wraps` 41 µs
  (12.7×); check-once-at-boundary 1.01× (free).
- `au = [signal] = a.u.` gives `au` its own dimension while keeping tokens
  (`'au'`, `'au / molar'`) and display (`~P → 'a.u.'`) identical — no migration.

## Findings — severity, disposition, evidence

| # | Sev | Location | Problem | Fix (disposition) |
|---|-----|----------|---------|-------------------|
| F1 | HIGH | `core/optimizer/scaling.py:126` `_scale_factor` | classified unit components by `.dimensionless` over private `unit._units`; `au/M ≡ 1/M` | **Fixed** — classify by `[signal]`/`[concentration]` dimension; genuine dimensionless → factor 1.0 |
| F2 | HIGH (root) | `core/units.py:31` | `au = []` dimensionless + shadows `astronomical_unit`; `a.u.` mis-parses | **Fixed** — `au = [signal] = a.u.`; `set_application_registry(ureg)` added |
| F3 | MED | `gui/plotting/plot_widget.py:272` | `_X_UNIT_SCALES.get(x_unit, 1e6)` silent µM fallback for unknown unit | **Fixed** — `_x_unit_scale()` derives via Pint, raises on invalid |
| F4 | MED | CSV/TXT/XLSX readers assume M, no in-band unit | µM file silently read as M by default | **Fixed (contract)** — TXT self-describing (F8), `from_dataframe` honors declared unit, M contract documented on `load_measurements`; column-name guessing deliberately excluded |
| F5 | MED | `core/pipeline/fit_pipeline.py` `from_dict` (+ `apply_statistics_mode`) | missing unit → silent `dimensionless` (drops `1/M`) | **Fixed** — `from_dict` **raises** (GUI surfaces it); the median/mean toggle takes each unit from the fitted parameter; both mirror the raising `_wrap_params_as_quantities` (hardened further in the re-audit) |
| F6 | MED | `fit_pipeline.py` `to_dict`/`from_dict` conditions | units dropped on export, not restored on import | **Fixed** — `condition_units` stored + re-wrapped |
| F7 | MED (core) | `fit_pipeline.py` `fit_assay` bound extraction | `.magnitude` without `.to(canonical)` → non-canonical custom bound takes face value; forward-model I/O unchecked | **Fixed** — bounds converted to canonical unit before `.magnitude` (validates + converts); boundary checks §5 |
| F8 | MED | `measurement_writer.py`, `txt.py` | files not self-describing (bare floats) | **Fixed** — TXT writer emits `# units:` header; `TxtReader` parses it |
| F9 | LOW→fixed | `core/data_processing/concentration.py:83` `read_raw_concentrations` | returned `(bare_ndarray, unit_str)` footgun | **Fixed** — returns a `Quantity`; sole caller (`data_panel`) updated |
| F10 | LOW | `core/assays/base.py:62` | raw `DimensionalityError` on wrong x/y unit | **Fixed** — domain-clear `ValueError` (x=concentration, y=signal) |
| F11 | LOW | `gui/plotting/fit_summary_widget.py:171` | `rsplit(' ',1)` to strip a formatted unit — fragile | **Fixed** — magnitude-only `Q_(v,'dimensionless'):.3g~H` |
| F12 | LOW | `gui/plotting/labels.py:55` | reciprocal post-process only handles `1/X` prefix (`au/M` shows as fraction) | **Not changed** — `a.u./M` is acceptable display; generalizing risks regressing `1/M→M⁻¹` (cosmetic-only) |
| F13 | MED (safeguard) | tests | no unit round-trip / registry-lint guards | **Added** — `test_registry_units.py` (kind↔unit↔log-scale + collision); µM→M round-trip and conditions-round-trip tests |

## Re-audit after merging `main` (PR #37 + #38)

The branch was rebased onto `main`, then a full multi-agent re-audit ran on the
merged tree. It confirmed F1–F3, F6, F7(runtime), F11–F13 still hold, and found
that the self-describing-unit work (F4/F8/F9) was only **half-wired**, plus new
issues in main's added code. All are fixed in six further tested commits; the
merge-conflict surface and the re-audit surface were the same files.

### Concentration-input boundary — 3 HIGH (silent 1e6–1e9)

The readers declared a file's unit (`df.attrs['concentration_unit']`), but three
consumers ignored it and assumed molar:

- **H1** `concentration.py` `extract_concentrations_from_file` wrapped face values
  as `M`. **Fixed** — returns a self-describing `Quantity` in the declared unit.
- **H2** `io/__init__.py` `load_measurements_multi` — `pd.concat` dropped per-file
  attrs, so a µM replicate stacked as M. **Fixed** — each file is converted to
  molar via its own declared unit before the concat.
- **H3** `data_panel.py` `_on_load_concentrations` discarded the loaded Quantity's
  unit for anything outside nM/µM/mM/M, reusing the stale Imported Unit. **Fixed** —
  converts to molar (or shows the file's unit when selectable) with a notice, never
  a silent reinterpret; `_load_single` reflects the declared unit in the UI.
- **G1 (CSV/XLSX carry no in-band unit):** kept the documented M default — the GUI
  Imported-Unit selector is the explicit boundary; no column-name guessing.

### Silent `dimensionless` re-wrap — MED/LOW (F5 revisited)

`apply_statistics_mode` (the GUI median/mean toggle) and `from_dict` re-attached a
registry-looked-up unit, defaulting to `dimensionless` for an unknown/legacy assay.
**Fixed** — the toggle takes each ± unit from the fitted parameter itself; `from_dict`
**raises** (surfaced by the GUI import handler) rather than loading a Ka as a bare
number.

### Display / export parity — LOW

- **L2/G5/G6** the fit summary and TXT export read units from the registry (empty
  for an unknown assay) instead of `value.units`. **Fixed** — sourced from the
  parameter Quantity, correct for any assay.
- **L3** the registry `a.u.` y-unit alias garbled to `u a` through the formatters
  (pint parses the dots as `year·amu`). **Fixed** — the formatters normalise the
  alias; `y_unit` stays `a.u.` for raw display.
- **L8** RMSE unit hardcoded in three sites → sourced from the canonical `au` token.

### Serialization provenance — LOW

- **L9** `custom_bounds` stored bare magnitudes → now keeps the unit token.
- **L10** `x_fit`/`y_fit` were re-wrapped with a hardcoded M/au → now store and read
  their own unit tokens (older files fall back to M/au).
- **L11 (Infinity/NaN JSON tokens):** left as-is — the app's own importer reads them
  (permissive `json.loads`) and there is no external-consumer requirement; a sentinel
  encoding would add complexity to a test-covered NaN round-trip.

### Miscellaneous — LOW

- **L4** `forward_model`'s ABC contract now documents it must return an `au` Quantity
  (the `au=[signal]` subtraction in `residuals` enforces it at runtime).
- **L7** the distribution plot's `log10` goes through a positivity guard matching
  `ensemble.describe_log10` (loud, not silent `-inf`/`nan`).
- **L12** the dead, unit-mismatched `load_concentration_vector` is removed (its tests
  now exercise the live `save → read_raw_concentrations` path).

New regression guards: non-M TXT import + heterogeneous-unit batch, the `_UnitWidget`
input conversion, the DataPanel non-M vector load, `apply_statistics_mode` unit
preservation + `from_dict` fail-loud, x/y-fit + `custom_bounds` unit round-trip, and
the `a.u.` formatter.

### Ensemble / distribution (main's new code)

`core/optimizer/ensemble.py` is a float-only statistics layer (no unit defect in
itself); its outputs are re-wrapped at the pipeline boundary — the F5 fix covers
that re-wrap. The one consumer-side gap (distribution `log10` contract) is L7.

## Preserved (verified correct — do not "fix")

Single shared registry; `_UnitWidget` Pint-derived scale caching; `_X_UNIT_SCALES`
Pint-derived; explicit `.to('M'/'au'/'1/M')` normalization (never
`.to_base_units()`); `FitResult` JSON `parameter_units` tokens; `labels.py`
`~H`/`~P` minimal reciprocal wrapper; float-only optimizer/kernel; the assay
condition validation (`.to(...)` fail-fast, tested with `DimensionalityError` —
left as-is rather than churned).

## Prior-art comparison

Consensus across astropy, MetPy, unyt, Pint, OpenFF: **Quantities at edges,
magnitudes in the numeric core** — exactly this repo's architecture. Adopted from
prior art: `set_application_registry` (Pint project guidance); a distinct
dimension for the arbitrary signal unit (the "quantity-kind" pattern —
mp-units/astropy `physical_type`, and the dimensionless-collision literature).
Kept Pint-only (astropy/unyt/pint-pandas are overkill/orthogonal for a
scipy-fitting desktop app). Kept the readable magnitude+token serialization over
`to_tuple` (we own the registry, so string tokens round-trip and stay
human-readable).

## Key questions answered

- **Built-in absorbance/fluorescence unit instead of overriding `astronomical_unit`?**
  None exists, and any dimensionless one keeps the collision. A custom
  `[signal]` dimension is the fix.
- **Enum vs dimension for classification?** Adopted **both**: the `[signal]`
  dimension makes the unit unambiguous, and `ParamKind` is the explicit label;
  a lint test cross-checks them so neither drifts.
- **Is `I0` `au`?** Yes — a signal offset in `au`; coefficients are `au/M`; the
  law is `[signal]`. Now runtime-checkable.
- **Runtime-check the forward models without slowing the fit?** Yes — validate at
  boundaries (once/fit, 1.01×), not per-iteration (12.7×).
- **Are exports carrying explicit units?** JSON (`parameter_units` +
  `condition_units`) and the TXT report (Units column, `~P` conditions) — yes;
  raw TXT/CSV now carry a `# units:` header (TXT) / documented M contract.

## Deliberate non-changes (and why)

- **Column-name unit auto-detection (CSV/XLSX):** excluded — a heuristic
  classifier that could itself produce silent wrong conversions; explicit
  declaration (header / `XUNITS` / GUI selector) is the safe boundary.
- **Condition exception types:** left as `pint.DimensionalityError` (already
  fail-fast and test-locked) rather than churned to a custom type.
- **F12 reciprocal display generalization:** cosmetic; skipped to avoid
  regressing the working `1/M → M⁻¹` path.

## Verification

Per stage: `uv run pytest`, `ruff check`. On the merged tree after all
remediation: **459 passed, 3 skipped**; ruff clean. Regression guards added
across the effort: `test_registry_units.py` (kind↔unit↔log-scale + collision),
non-M TXT import and heterogeneous-unit batch (`test_concentration.py`,
`test_io_multi.py`), the `_UnitWidget` input conversion and DataPanel non-M vector
load (`test_assay_config_panel.py`, `test_data_panel.py`), `apply_statistics_mode`
unit preservation + `from_dict` fail-loud + x/y-fit and `custom_bounds` unit
round-trip (`test_fit_results.py`), and the `a.u.` formatter (`test_labels.py`).
