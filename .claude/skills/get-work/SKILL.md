---
name: get-work
description: >-
  Turn the fitting-app issue backlog into ready-to-run work packages — one per
  Claude Code session/worktree. Fetches and lists the Slack "Issues Tracker",
  lets you pick which issues to tackle this round, clarifies the vague ones with
  you, articulates each as a clear user-style request, does a light grouping
  pass, opens GitHub issues, and emits copy-paste prompts that hand each need to
  a plan-mode agent — without prescribing the implementation. User-invoked only:
  trigger when the user explicitly asks to get / plan / triage / parallelize the
  backlog, select issues to work on, split issues into parallel sessions or
  worktrees, or turn the Slack issues into work packages or PRs. Do NOT
  auto-trigger on incidental mentions of issues, Slack, or the backlog.
---

# get-work

Turn the user-submitted issue backlog into a set of **ready-to-run work packages**, one per Claude Code session/worktree. Each package hands a well-described *need* to a downstream agent, which plans and implements it (in plan mode, with the maintainer's approval) and opens its own PR.

The skill's job is to **articulate and hand off needs — not to plan the implementation.** It fetches and lists the backlog, lets the maintainer pick a focused subset, clarifies the vague ones, expresses each as a clear user-style request, does a *light* grouping pass, opens GitHub issues, and emits copy-paste prompts. The downstream agents own interpretation, planning, and every file-level decision.

Selection-first and gated: **six phases** separated by hard STOPs. Never collapse them into one autonomous run.

## Interaction model — drive every gate with AskUserQuestion

Every point where you need the maintainer's input — issue **selection** (Phase 2), **clarifying** vague issues (Phase 3), and **approvals** for the grouping (Phase 4) and for issue creation (Phase 5) — is collected with the **AskUserQuestion tool**, not free-form prose. Prose is for *presenting*; every *decision* comes back through the tool.

- Each question offers **2–4 options**; one call carries **up to 4 questions** (~16 options max). An "Other" free-text choice is always added automatically.
- Use `multiSelect` when more than one choice can apply (issue selection; multi-interpretation clarifications).
- When choices exceed one call, **batch/paginate** across calls — or first ask a narrowing question (e.g. which status group) — rather than truncating.

Each phase below ends at a **STOP**: the AskUserQuestion call *is* the stop — proceed only on its answer.

## Operating rules (non-negotiable)

1. **Slack is the only issue source.** The fitting-app "Issues Tracker" List, fetched directly by stable ID (from the maintainer's memory `slack-issues-tracker`, never fuzzy search). Recipe in `references/slack-fetch.md`.
2. **Never leak personal data.** Drop `Submitted by`, `Assignee`, and any author/email/identity field at fetch. It must never reach a GitHub issue, a session prompt, your notes, or memory.
3. **Never assume on a vague issue.** Issues come from non-technical users and are often ambiguous or over-scoped. When meaning is unclear, ask (via AskUserQuestion) and refine *with the maintainer* before acting. A question is cheap; a guessed interpretation is not.
4. **Describe needs, not solutions.** Everything you hand downstream — GitHub issues *and* session prompts — states *what is needed and why*, in plain user language, never *how to build it*. No file lists, no step-by-step, no prescribed design. The implementing agent owns that; over-specifying wastes its judgement and biases it toward your guess. This is the core posture: you are a clear-communicating user expressing a need, not an architect writing a spec.

## Setup

- **Issue source:** Slack only (rule 1). IDs live in memory, not in this public repo; see `references/slack-fetch.md`.
- **GitHub:** Phase 5 opens issues with `gh` (see `references/github-issues.md`, which defers `gh` usage to the **`gh` skill**). Confirm `gh auth status` and the repo with `gh repo view` first.
- **Conventions stay out of the prompts.** Downstream agents automatically read the repo's `CLAUDE.md` (worktree usage, commit style, testing, PR descriptions) and pick up graphify guidance from the harness. The emitted prompts therefore **do not mention conventions, graphify, or PR-writing at all** — they carry only the need and the plan-first handoff.

## Phase 1 — Fetch and list (no evaluation)

1. Fetch using `references/slack-fetch.md`; strip personal fields immediately (rule 2).
2. Present a **plain catalog** grouped by status (`New`, `In progress`, `Backlog`): number · title · status · a one-line *neutral* gist (a paraphrase, not a judgement). Show the `Done` count for reference; don't list it.
3. No relevance/feasibility assessment, no clustering, no planning yet. The catalog exists only to choose from.

## Phase 2 — Select issues to work on → STOP

Use **AskUserQuestion** (`multiSelect: true`), options labelled by the Phase 1 numbers/titles. If the catalog fits one call (~16 across ≤4 paged questions), present it directly; if larger, ask a narrowing question (which status group) first, then paginate. Never drop issues to fit. Everything after this operates **only** on the selected subset; echo it back, then proceed.

## Phase 3 — Clarify, then articulate as user-style requests → STOP until resolved

For the selected subset only:
1. Where an issue is vague, ambiguous, or over-scoped, **clarify via AskUserQuestion** — one question per ambiguity, candidate interpretations as options (+ the automatic "Other"), `multiSelect` where several apply. Surface what each interpretation implies; never pick one yourself (rule 3). Iterate until each issue's *intent* is clear.
2. Rewrite each issue as a clean **user-style request**: what's wrong or wanted, and why it matters — as an experienced, clear-communicating user with light technical awareness would put it. **No prescribed solution, no file references, no implementation steps** (rule 4). This articulation is the single source that feeds both the GitHub issue and the session prompt.

Assess relevance/feasibility only enough to ask good questions — not to design the fix.

## Phase 4 — Light grouping into packages → STOP

Group the articulated requests into work packages. This is a **rough, up-front pass — just enough to decide what ships together.** It is **not** an implementation plan and **not** a file assignment.
- **Default: one issue = one package.** Simplest and most parallel.
- **Merge** issues into one package only when they're *obviously* the same feature/area and clearly belong together.
- If two packages will *obviously* work the same area of the app, you may note it so the maintainer can choose to run them one-after-another — but estimate at the level of "same feature area", **not files**, and don't try to prove disjointness. Real conflicts surface during each agent's plan-mode review and ordinary merging.

Present the grouping (packages → issues, with any light sequencing note) and get approval via **AskUserQuestion**. STOP.

## Phase 5 — Open GitHub issues → STOP before creating

Draft one GitHub issue per articulated request, in **user voice** — the need, why it matters, and outcome-level "done when" signals — with **no implementation detail and no file boundaries** (`references/github-issues.md`). No personal data (rule 2). Present the drafts, get approval via **AskUserQuestion**, then create with `gh` and capture the numbers/URLs.

## Phase 6 — Emit session prompts

Produce **one copy-paste prompt per package**, each in its own fenced block, by filling `assets/session-prompt-template.md`. Keep each prompt to just two things:
- the **need in user voice** (what/why), referencing its GitHub issue(s) by number/URL (and a one-line "wait until #N merges" for any sequenced package);
- a **plan-first handoff** — start in plan mode, propose a plan, iterate with the maintainer, implement only after approval, then open one PR that closes the issue(s).

Nothing else — no file boundaries, no conventions, no graphify or PR instructions; the agent reads `CLAUDE.md` and the harness for those. Group the output: independent packages first, then any sequenced ones (dependency noted).
