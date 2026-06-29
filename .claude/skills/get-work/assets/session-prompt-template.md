# Session prompt template

Fill one of these per work package in Phase 6 and emit it in its own fenced block so the maintainer can paste it straight into a fresh Claude Code session. Replace every `<…>`.

Write the **"What I need"** section in the voice of a clear, capable user describing a need — *not* a spec. Do **not** list files, steps, or a design; the agent plans that. Keep the prompt about the need and how we'll work together, nothing more.

```text
I'm working on SupraSimFit (the fitting-app) and need help with the following. Please **start in plan mode**: look into it, then come back with a proposed approach so we can refine it together over a few rounds. Don't write code until I've approved a plan.

## What I need
<The need / bug / pain point in plain user language: what's happening or what I want, and why it matters. No prescribed solution, no files, no steps.>

## Reference
- #<NN> — <title> — <url>   (full context on the GitHub issue)
<Sequenced packages only:> Please wait until #<dependency> has merged, then branch from the updated main before you start.

Once we've agreed on a plan, implement it and open a single PR that closes the referenced issue(s).
```

## Emission format

Group the filled prompts in the Phase 6 output:
1. **Launch now (independent):** one fenced block per package.
2. **Sequenced (after a dependency merges):** one block per package, each with its "wait until #N has merged" line, in dependency order.

Add a one-line index above the blocks (e.g. "Package A → #21; Package B → #22 (after A)") so the maintainer sees the whole fan-out at a glance.
