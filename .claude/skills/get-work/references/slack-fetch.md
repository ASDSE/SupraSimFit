# Slack fetch recipe — Issues Tracker

The fitting-app "Issues Tracker" is a Slack **List** (not a Canvas). It is the **only** source of issues for this skill. Fetch it directly by its stable ID — never re-discover it with `slack_search_channels` / `slack_search_public`.

## Stable identifiers (resolved locally — not committed)

SupraSimFit is a **public** repo, so the concrete channel / List IDs are intentionally not stored in this file. Use placeholders here and resolve them at run time:

| Placeholder | What it is |
|---|---|
| `<CHANNEL_ID>` | `#fitting-app` channel ID |
| `<LIST_ID>` | Issues Tracker List file ID |

**Source of truth:** the maintainer's private memory note `slack-issues-tracker` holds both IDs. If it isn't available in the session, ask the maintainer for them — never fall back to fuzzy `slack_search_*`, which is exactly what pinning the IDs avoids. (The IDs are opaque identifiers, not credentials; they're kept out of the public repo only to avoid leaking workspace metadata.)

## Step 1 — Direct retrieval (one call, no search)

```
slack_read_file(file_id="<LIST_ID>")
```

Returns the whole List as CSV. The tool has **no query / sort / column parameters** — it returns everything in one shot. So "sorted by status" and "personal fields removed" are deterministic transforms applied to this fixed output, not a re-query and not loose post-filtering. Same input → same result every time.

CSV columns, in order:
`Feedback, Details, Type, Severity, Submitted by, Date submitted, Status, Assignee, Zip File`

## Step 2 — Strip personal fields (STANDING, ALWAYS-ON)

Immediately drop these columns from the parsed rows and **never** carry them into output, GitHub issues, session prompts, notes, or memory:

- ❌ `Submitted by`
- ❌ `Assignee`

Keep only: `Feedback, Details, Type, Severity, Date submitted, Status, Zip File`.

This is not specific to this List — any author / email / reader-identity / assignee field from any Slack source is excluded by default. Reporter identity is never needed to implement the work.

## Step 3 — Group by status for the Phase 1 catalog

Bucket the surviving rows by exact `Status` value. In the selection-first flow the skill does **not** pre-judge scope — it lists, and the maintainer selects (Phase 2). The status only decides what gets *listed*:

| List status | Meaning | In the Phase 1 catalog |
|---|---|---|
| `New` | = "Not started" | **Listed** (selectable) |
| `In progress` | actively being worked | **Listed** (selectable) |
| `Backlog` | parked | **Listed** (selectable) |
| `Done` | shipped | **Not listed** — reference only (show the count); never redone |

Within each bucket, sort by `Severity` (High → Medium → Low), then by `Date submitted` ascending. Match status strings exactly; if Slack later adds a status value, list it under its own group and surface it — do not fuzzy-match it into an existing bucket.

## Fields the row carries

- **Feedback** — issue title.
- **Details** — full description (multi-line, written by a non-technical user; often vague or over-scoped → expect Phase 3 clarification). The maintainer sometimes embeds a `*For Claude:*` note here with extra direction — treat it as authoritative clarification.
- **Type** — Bug / Feature Request / Pain Point / Praise / Other. Maps to a GitHub label (see `github-issues.md`).
- **Severity** — Low / Medium / High. Use for ordering the catalog and, later, parallelization priority.
- **Date submitted**.
- **Status** — see table above.
- **Zip File** — comma-separated Slack file IDs of attachments (screenshots, data, zips). Fetchable with `slack_read_file(file_id=...)` — it resolves images and text/data files. Pull these when an issue's meaning depends on an attached screenshot or sample dataset.

## Not available

Native per-row List **comments** are not exposed by any Slack tool. Discussion *about* an issue is only reachable indirectly via channel thread search (`slack_search_public in:#fitting-app` → `slack_read_thread`). Don't rely on it for scoping; if an issue is unclear, that is what Phase 3 (clarifying with the maintainer) is for.
