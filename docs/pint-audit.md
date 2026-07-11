# Pint units audit — SupraSimFit

_Scientific-integrity audit of how Pint is integrated across the codebase, with
the remediation applied. Companion to [`pint-findings.md`](pint-findings.md) (the
usage reference). Every claim was verified by reading the code and running Pint in
the repo venv (pint 0.25.2); nothing was sampled._

## Method

Five parallel research passes — core numerical path, data-processing + I/O,
GUI + plotting/export, official Pint docs, and prior-art in scientific Python —
followed by lead re-verification of every load-bearing claim (reading the code
and executing Pint). Findings were then fixed in seven staged, individually-tested
commits; the full suite (376 unit + 35 integration) is green after each stage.

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
| F5 | MED | `core/pipeline/fit_pipeline.py` `from_dict` | missing unit → silent `dimensionless` (drops `1/M`) | **Fixed** — warns naming the parameter; `_wrap_params_as_quantities` raises on missing registry unit |
| F6 | MED | `fit_pipeline.py` `to_dict`/`from_dict` conditions | units dropped on export, not restored on import | **Fixed** — `condition_units` stored + re-wrapped |
| F7 | MED (core) | `fit_pipeline.py` `fit_assay` bound extraction | `.magnitude` without `.to(canonical)` → non-canonical custom bound takes face value; forward-model I/O unchecked | **Fixed** — bounds converted to canonical unit before `.magnitude` (validates + converts); boundary checks §5 |
| F8 | MED | `measurement_writer.py`, `txt.py` | files not self-describing (bare floats) | **Fixed** — TXT writer emits `# units:` header; `TxtReader` parses it |
| F9 | LOW→fixed | `core/data_processing/concentration.py:83` `read_raw_concentrations` | returned `(bare_ndarray, unit_str)` footgun | **Fixed** — returns a `Quantity`; sole caller (`data_panel`) updated |
| F10 | LOW | `core/assays/base.py:62` | raw `DimensionalityError` on wrong x/y unit | **Fixed** — domain-clear `ValueError` (x=concentration, y=signal) |
| F11 | LOW | `gui/plotting/fit_summary_widget.py:171` | `rsplit(' ',1)` to strip a formatted unit — fragile | **Fixed** — magnitude-only `Q_(v,'dimensionless'):.3g~H` |
| F12 | LOW | `gui/plotting/labels.py:55` | reciprocal post-process only handles `1/X` prefix (`au/M` shows as fraction) | **Not changed** — `a.u./M` is acceptable display; generalizing risks regressing `1/M→M⁻¹` (cosmetic-only) |
| F13 | MED (safeguard) | tests | no unit round-trip / registry-lint guards | **Added** — `test_registry_units.py` (kind↔unit↔log-scale + collision); µM→M round-trip and conditions-round-trip tests |

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

Per stage: `uv run pytest` (full unit + integration), `ruff check`,
`ruff format --check`. Final: **376 unit passed (3 skipped), 35 integration
passed**; ruff clean; `plot_widget.py` line endings preserved (CRLF). New
regression guards: `tests/unit/test_registry_units.py`, plus µM→M and
conditions-round-trip tests in `test_io.py` / `test_fit_results.py`.
