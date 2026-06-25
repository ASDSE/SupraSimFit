# Conflict analysis — guaranteeing disjoint file sets

The hard constraint: **no two packages that run in parallel may edit the same file.** Parallel sessions each branch from `main` and merge back independently. Git does not three-way-merge two PRs against each other before they land — whichever merges second silently clobbers or conflicts with the first on any shared file. So conflict prevention is structural, done here at planning time, not at merge time.

This procedure produces a partition where each package's file set is disjoint, and a sequencing list for anything that can't be separated.

## Step 1 — Estimate each unit's file touch-set

For every work unit from Phase 4, derive the set of files it will likely create or modify. Combine:

- **graphify** (fastest, scoped): `graphify query "<feature / keywords>"`, `graphify explain "<concept>"`, and `graphify path "<A>" "<B>"` for the files that sit between two areas. This returns a small subgraph — usually enough to see the real touch-set.
- **CLAUDE.md architecture map**: translate the unit into layers (Assays / Models / Optimizer / Pipeline / Data Processing / I/O / Units / GUI shell / session / state / workers / widgets / plotting / dialogs / update) and read off the paths.
- **grep** for the concrete symbols, registry keys, or UI strings the unit touches.

Classify each file:
- **will-edit** — a core change lands here.
- **may-touch** — plausibly edited incidentally.

For conflict purposes, treat **may-touch as part of the set**. Underestimating the set is what causes silent merge clobbering; overestimating only costs a little parallelism.

## Step 2 — Flag the hotspots

A few files attract edits from many unrelated units. They are where most conflicts hide. Whenever a unit needs one, flag it loudly:

| Hotspot | Why it collides |
|---|---|
| `core/assays/registry.py` | `ASSAY_REGISTRY` / `AssayType` — **every** new assay edits this one file |
| `gui/app_state.py` | shared mutable session state — many GUI features add a field |
| `gui/fitting_session.py` | wires panels + dispatches the fit — broad surface, many features touch it |
| `gui/main_window.py` | toolbar / menu / window shell — most new actions register here |
| `core/units.py` | unit tables — anything adding a unit or parameter |
| `gui/plotting/plot_widget.py` | dense plotting hub — most plot changes converge here |
| `pyproject.toml` / `uv.lock` | any new dependency |
| `_version.py` | version bump — keep out of feature packages entirely |
| `CLAUDE.md` | docs — only one package should edit it per round, if any |

## Step 3 — Build the file→package map

List every package and the union of its units' file sets. Invert it to file → {packages}. **Any file mapped to two or more parallel packages is a conflict.** Present this as a conflict matrix (packages × shared files) so the overlap is visible, not buried.

## Step 4 — Resolve every overlap

In order of preference:

1. **Reassign units** so the sets become disjoint. Often a unit landed in the wrong package; moving it removes the overlap at no cost. Best outcome.
2. **Co-locate** the conflicting units in **one** package. They then run in the same session and their edits to the shared file are serialized by one agent. Cost: those units lose parallelism with each other (but the package still runs in parallel with all others). Use when the shared edit is small and the units are related.
3. **Sequence** them. Package B starts only after package A's PR has merged; B branches from the updated `main`, where the file already reflects A's change. Mark the dependency explicitly so the emitted prompt says "do not start until PR #N merges." Use when co-locating would make a package too large or the units are otherwise unrelated.

Never resolve a conflict by hoping the edits are "in different parts of the file" — git conflicts are textual, and an append by two branches to the same list still conflicts.

## Step 5 — Project-specific patterns

- **New assay types** (`AssayType` + `ASSAY_REGISTRY`): the new model file (`core/models/…`), the new `BaseAssay` subclass (`core/assays/…`), and the new tests are **unique per assay** and never conflict. The **only** collision point is the shared registry edit in `core/assays/registry.py`. So either batch all new-assay units into one package (serialize the registry edits), or sequence them. Do not parallelize them as-is just because most of their files differ.
- **New I/O readers** (`core/io/formats/…`): the reader file is new and unique; the shared edit is the registration entry in the io registry. Same handling as new assays — isolate or sequence the registration.
- **New GUI widgets / panels**: the widget file is new, but registration usually touches `fitting_session.py` and/or `main_window.py` (hotspots). Two such units collide there → sequence or co-locate.
- **Plot-style / plot-widget changes**: `gui/plotting/*` is a tight cluster centered on `plot_widget.py`. Two independent plot changes almost always collide there — sequence them rather than splitting.
- **Tests**: two packages adding tests to the **same** existing test file conflict. Prefer new, package-specific test files; if a package must extend a shared test module, treat that module as part of its (potentially conflicting) set.

## Output of this analysis

1. The final **disjoint partition**: packages whose file sets share nothing.
2. A **sequencing list**: ordered dependencies ("Package E after Package A's PR") for anything that couldn't be made disjoint.
3. The **conflict matrix** you used to prove disjointness — include it in the Phase 4 presentation so the user can see the constraint is actually satisfied, not asserted.
