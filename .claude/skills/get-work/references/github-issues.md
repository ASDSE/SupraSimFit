# Opening GitHub issues for refined work units

Phase 5 turns each refined work unit into a GitHub issue that captures the *agreed* understanding (post-clarification), so the issue — not the vague Slack text — is what a session implements and what a PR later closes.

## Preconditions

For `gh` CLI usage patterns — structured `--json`/`--jq` output, pagination, `gh api` fallback, repo targeting — consult the **`gh` skill** instead of re-deriving them here.

- `gh auth status` succeeds.
- Resolve the repo explicitly: `gh repo view --json nameWithOwner`. Expected: `ASDSE/SupraSimFit` (public repo — keep personal data out of all issue text accordingly). Do not hardcode — confirm against the current remote.
- **Gate:** present all drafts and get approval **before** running any `gh issue create`. Creating issues is an outward-facing side effect; never do it unprompted.

## Issue body template

Use this structure for every issue. Keep it free of personal data (no reporter name, email, or assignee — rule 2).

```markdown
## Summary
<the refined, concrete understanding agreed with the maintainer — one short paragraph>

## Source
Reported via the fitting-app feedback channel. <Optional: refined restatement of the original request. NEVER include who reported it.>

## Acceptance criteria
- [ ] <concrete, checkable outcome>
- [ ] <concrete, checkable outcome>
- [ ] Tests added/updated and the targeted suite passes
- [ ] `uv run ruff check` and `uv run ruff format` clean

## Scope & file boundaries
This unit belongs to **Package <X>**. It is expected to touch only:
- `<path>`
- `<path>`
New files under: `<dir>`
It must NOT modify: `<shared hotspots owned by other packages, if any>`

## Parallelization
<one of:>
- Independent — can run in parallel with all other packages.
- Sequenced — start only after #<N> (Package <Y>) is merged.
```

## Labels

Map the Slack `Type` column to a label, and tag the parallel-work batch so issues are easy to find later. Create labels only if missing (`gh label create <name> 2>/dev/null || true`); if label creation isn't desired, omit `--label` rather than failing.

| Slack `Type` | GitHub label |
|---|---|
| Bug | `bug` |
| Feature Request | `enhancement` |
| Pain Point | `enhancement` (or `ux`) |
| Other | (no type label) |
| Praise | not an issue — never filed |

Optionally add `parallel-batch` to everything created in one run.

## Create and capture

```bash
gh issue create \
  --title "<type>: <concise title>" \
  --body-file <tmpfile> \
  --label "<type-label>" --label "parallel-batch"
```

Capture each new issue's number and URL from the command output. These feed directly into the Phase 6 session prompts (`assets/session-prompt-template.md`) and into the PR's `Closes #N`.

## Linking issues ↔ PRs

Don't link manually here. The session prompt instructs each session to put `Closes #N` in its PR body, so GitHub auto-links and auto-closes the issue when the PR merges. If several issues share one package/PR, list `Closes #N` once per issue.
