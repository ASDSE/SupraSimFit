# Opening GitHub issues (user-voice need statements)

Phase 5 turns each articulated request into a GitHub issue written **in the voice of a clear, capable user** — the need and why it matters, plus outcome-level "done when" signals. The issue is *not* an implementation plan: no file lists, no design, no step-by-step. The implementing agent (starting in plan mode) owns all of that.

## Preconditions

For `gh` CLI usage patterns — structured `--json`/`--jq` output, pagination, `gh api` fallback, repo targeting — consult the **`gh` skill** instead of re-deriving them here.

- `gh auth status` succeeds.
- Resolve the repo explicitly: `gh repo view --json nameWithOwner`. Expected: `ASDSE/SupraSimFit` (public repo — keep personal data out of all issue text accordingly). Do not hardcode — confirm against the current remote.
- **Gate:** present all drafts and get approval (via AskUserQuestion) **before** running any `gh issue create`. Creating issues is an outward-facing side effect; never do it unprompted.

## Issue body template

Keep it in user voice, free of personal data (no reporter name, email, or assignee), and free of implementation detail.

```markdown
## What's needed
<plain-language description of the bug / pain point / desired capability, and why it matters to users. Describe the need — not a solution, not files, not steps.>

## Context
Reported via the fitting-app feedback channel.
<Optional: a clarifying detail agreed with the maintainer during refinement. Never include who reported it.>

## Done when
<Outcome-level signals that the need is met — what the user can now do, or what no longer happens. NOT implementation steps. 2–4 bullets.>
```

If a package is sequenced behind another, add a single line of context — `Depends on #<N>.` — and nothing more.

## Labels

Map the Slack `Type` to a label; tag the batch so issues are easy to find. Create labels only if missing (`gh label create <name> 2>/dev/null || true`); if creation isn't desired, omit `--label` rather than failing.

| Slack `Type` | GitHub label |
|---|---|
| Bug | `bug` |
| Feature Request | `enhancement` |
| Pain Point | `enhancement` |
| Other | (no type label) |
| Praise | not an issue — never filed |

Optionally add `parallel-batch` to everything created in one run.

## Create and capture

```bash
gh issue create \
  --title "<type>: <concise, plain title>" \
  --body-file <tmpfile> \
  --label "<type-label>" --label "parallel-batch"
```

The title may use a conventional prefix (`feat:`/`fix:`/`docs:`) but stays a plain summary of the need — not a description of the chosen implementation. Capture each issue's number and URL from the output — they feed the Phase 6 session prompts and the PR's `Closes #N`. Don't link issues↔PRs manually: each session prompt tells the agent to put `Closes #N` in its PR body, so GitHub auto-links on merge.
