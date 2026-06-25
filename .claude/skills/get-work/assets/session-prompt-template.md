# Session prompt template

Fill one of these per work package in Phase 6 and emit it in its own fenced block so the user can copy it straight into a fresh Claude Code session. Replace every `<…>`. Drop the "Do not start until…" line for independent packages. Keep it self-contained — the target session has none of this planning context.

```
You are implementing one isolated work package for the SupraSimFit project. Work in your own worktree on a feature branch and open a single PR that closes the referenced issue(s). Stay strictly within the file boundaries below so this PR merges cleanly alongside sibling packages running in parallel.

## Issue(s)
- #<NN> — <title> — <url>
Read the full issue text on GitHub before starting; the issue is the source of truth.

## Scope
<concise statement of exactly what to build or fix — the refined definition of done agreed during planning>

## In-scope files / boundaries (edit ONLY these)
- <path>
- <path>
New files expected under: <dir(s)>

## Do not touch
- <shared hotspot files owned by other packages, e.g. "core/assays/registry.py — owned by Package A">
<Sequenced packages only:> Do not start until PR #<N> (Package <X>) has merged; branch from the updated main so the shared files already reflect that change.

## Acceptance criteria
- [ ] <criterion from the issue>
- [ ] <criterion from the issue>
- [ ] Tests added/updated in NEW package-specific test files (not shared modules); `uv run pytest -k "<subset>"` passes
- [ ] `uv run ruff check` and `uv run ruff format` are clean

## Conventions
Before starting, read CLAUDE.md and follow its worktree, graphify, commit-message, and testing conventions. In particular: do not stage or commit graphify-out/ on your feature branch.

## Deliverable
Open a PR titled "<type>: <subject>" with body containing "Closes #<NN>". Keep the entire diff within the in-scope files above. If you discover you need to edit a file outside your boundary, stop and report it rather than editing it — that file likely belongs to a parallel package.
```

## Emission format

Group the filled prompts in the Phase 6 output:

1. **Launch now (independent):** one fenced block per package, no dependencies.
2. **Sequenced (launch after a dependency merges):** one fenced block per package, each with its "Do not start until PR #N" line, listed in dependency order.

Add a one-line index above the blocks (e.g. "Package A → #12; Package B → #13; Package C → #14, #15 (after A)") so the user can see the whole fan-out at a glance.
