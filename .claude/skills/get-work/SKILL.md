---
name: get-work
description: >-
  Turn the fitting-app issue backlog into isolated, parallelizable work packages
  — one per Claude Code session/worktree, each opening its own non-conflicting PR
  into main. Fetches and lists the Slack "Issues Tracker", lets you pick which
  issues to tackle this round, refines the vague ones with you through interactive
  prompts, partitions the work into disjoint file sets, opens GitHub issues, and
  emits ready-to-paste session prompts. User-invoked only: trigger when the user
  explicitly asks to plan / triage / parallelize the backlog, select issues to
  work on, split issues into parallel sessions or worktrees, or turn the Slack
  issues into work packages or parallel PRs. Do NOT auto-trigger on incidental
  mentions of issues, Slack, or the backlog.
---

# Parallel work packages

Turn the user-submitted issue backlog into a set of **isolated, parallelizable work packages**. Each package is sized to run in its own Claude Code session and worktree, open a single PR, and merge into `main` without colliding with the others. The goal is throughput: many small correct PRs landing in parallel — not solving everything in one serial pass.

The run is **selection-first and gated**. It fetches and lists the backlog, lets the maintainer pick a focused subset, and only then evaluates, clarifies, and plans — across **six phases** separated by hard STOPs. Restricting everything after Phase 2 to the chosen issues is deliberate: it keeps each feedback and planning round small. **Never collapse the phases into one autonomous run.**

## Interaction model — drive every gate with AskUserQuestion

Every point where you need the maintainer's input — issue **selection** (Phase 2), **clarifying** vague issues (Phase 3), and **approvals** for the breakdown (Phase 4) and for issue creation (Phase 5) — is collected with the **AskUserQuestion tool**, not free-form prose. Prose is for *presenting*; every *decision* comes back through the tool. That is what "interactive" means here, and it keeps each answer crisp.

Work within the tool's shape, and never let it silently hide choices:
- Each question offers **2–4 options**; one call carries **up to 4 questions** — so a single call surfaces at most ~16 options. An "Other" free-text choice is always added automatically.
- Use `multiSelect` when more than one choice can apply (issue selection; multi-interpretation clarifications).
- When the choices exceed what one call can hold, **batch or paginate across multiple calls** — or first ask a narrowing question (e.g. which status group) — rather than truncating. Dropping options silently would hide work from the maintainer, which is its own failure.

Each phase below ends at a **STOP**: the AskUserQuestion call *is* the stop — proceed only on its answer.

## Operating rules (non-negotiable)

These hold in every phase. They exist because the cost of breaking them is high and silent.

1. **Never assume on a vague issue.** Issues are written by non-technical users and are frequently ambiguous, multi-interpretation, or over-scoped. When meaning is unclear, ask (via AskUserQuestion) — as many rounds as it takes — and refine the issue *with the maintainer* before acting. Acting on a guessed interpretation burns an entire parallel session and produces a misdirected PR. A question is cheap; a wrong guess is the most expensive thing here.

2. **Never leak personal data.** Drop `Submitted by`, `Assignee`, and any author / email / identity field at the moment of fetch (see `references/slack-fetch.md`). It must never reach a GitHub issue, a session prompt, your notes, or memory. Only issue text crosses from Slack into a coding session; reporter identities are not needed to do the work and must not travel with it.

3. **Strict file-level non-conflict between packages.** No two packages that run in parallel may edit the same file. Parallel sessions branch from `main` and merge independently, so two PRs touching one file silently overwrite each other at merge. Partition the work so each package's file set is **disjoint**. Anything that cannot be cleanly separated gets **sequenced** (one package depends on another's merged PR), not parallelized. Verified explicitly in Phase 4 — see `references/conflict-analysis.md`.

## Setup

- **Issue source: Slack only.** The fitting-app channel's "Issues Tracker" List is the single source of issues. Fetch it directly by stable ID — never re-discover it by fuzzy search. The IDs live in the maintainer's private memory (`slack-issues-tracker`), not in this public repo; the full recipe and the personal-data exclusion are in `references/slack-fetch.md`.
- **GitHub:** Phase 5 opens issues with the `gh` CLI (see `references/github-issues.md`, which defers `gh` usage to the **`gh` skill**). Confirm `gh auth status` and resolve the repo with `gh repo view` before that phase.
- **Where it runs:** this planning skill runs once, in a single session. The *packages* it emits are what fan out into separate worktrees. Worktree, graphify, commit, and testing conventions live in the repo's `CLAUDE.md` (graphify is committed per-worktree — there is no shared graph to manage); the emitted prompts point each session there rather than restating them.

## Phase 1 — Fetch and list (no evaluation)

1. Fetch the backlog using `references/slack-fetch.md`. Strip personal fields immediately (rule 2).
2. Present a **plain catalog** of the available issues, grouped by status (`New`, `In progress`, `Backlog`). Each entry is just: a stable number, the title, the status, and a one-line *neutral* gist (a paraphrase, not a judgment). Show the `Done` count as reference but do not list those — they are shipped, never redone.
3. Stop there. Do **no** relevance or implementability assessment, **no** clustering, **no** breakdown, **no** planning yet. Evaluating the whole backlog wastes effort on issues that won't be picked and biases the maintainer's selection. The catalog exists only to choose from.

## Phase 2 — Select issues to work on → STOP

Use **AskUserQuestion** to ask which issues to tackle this iteration (`multiSelect: true`), with options labelled by the Phase 1 numbers/titles.
- If the catalog fits one call (≈ up to 16 issues across ≤4 paged questions of ≤4 options), present it directly.
- If it's larger, first ask a **narrowing** question (which status group(s) to focus on), then paginate the chosen group(s) across further calls. Never drop issues from the choices to make them fit.

Everything after this operates **only** on the selected subset. Echo the selection back, then proceed.

## Phase 3 — Evaluate and clarify the selected issues → STOP until resolved

For the selected subset only:
1. Assess **relevance** (still makes sense given what shipped?) and **implementability** (feasible in this architecture? partially done? blocked?) against the codebase — `graphify query` / `graphify explain` plus CLAUDE.md's architecture map.
2. For every issue that is vague, ambiguous, or over-scoped, **clarify via AskUserQuestion**: one question per ambiguity, options = the candidate interpretations you see (plus the automatic "Other"), `multiSelect` where several can apply. Lay out what each interpretation implies for scope — never pick one yourself (rule 1). Batch up to 4 related questions per call; iterate with more calls until nothing is ambiguous.
3. STOP until every selected issue has a concrete, agreed definition of done. The output is a set of concrete **work units** — possibly several per issue.

## Phase 4 — Break down and verify non-conflict → STOP

1. Split over-scoped units into the smallest concrete pieces that still deliver something.
2. Estimate each unit's **file touch-set** (procedure in `references/conflict-analysis.md`).
3. Group units into packages tuned for parallelism with **disjoint file sets**; a unit large enough to deserve its own PR is fine as its own package.
4. Run the conflict check: build a file→package map, confirm no file appears in two parallel packages, and resolve every overlap by co-locating or sequencing. Watch the hotspots (`core/assays/registry.py`, `gui/app_state.py`, `gui/main_window.py`, `gui/plotting/plot_widget.py`).
5. Present the breakdown — each package with its units, the issues it will reference, its file set / boundaries, the **conflict matrix** proving disjointness, and any sequencing — then get **approval via AskUserQuestion** (e.g. Approve / Adjust grouping / Adjust boundaries / Re-scope). STOP.

## Phase 5 — Open GitHub issues → STOP before creating

1. For each refined unit, draft a GitHub issue: title, refined understanding, acceptance criteria, its package, and its file boundaries. No personal data (rule 2). Format and labels in `references/github-issues.md`.
2. Present the drafts and get **approval via AskUserQuestion** (e.g. Create all / Create a subset / Edit drafts first / Cancel) **before** any `gh issue create`. Only after approval, create them and capture the issue numbers / URLs.

## Phase 6 — Emit session prompts

Produce **one ready-to-paste prompt per package**, each in its own fenced block, by filling `assets/session-prompt-template.md`. Each prompt must:
- reference its GitHub issue(s) by number / URL,
- state the package scope and its **disjoint file set / boundaries** (and any "start only after PR #N merges" sequencing),
- be self-contained enough to run cold in an isolated worktree and open its own PR,
- point the session at `CLAUDE.md` for worktree / graphify / commit / testing conventions.

Emit them grouped: the independent packages that can launch **now**, then any **sequenced** packages with their dependency noted.
