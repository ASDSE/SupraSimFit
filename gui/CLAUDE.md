# gui/ — design rules

The interface follows `docs/design/DESIGN.md`, built from `gui/design/` (tokens,
stylesheet, components, plot theme, icons). `docs/design/screens/` shows the approved
look of each view in light and dark. Read the DESIGN.md section of the view you touch
first.

Binding rules:

- **Values come from tokens.** Colours through a `Theme` (`t.q('token')`, `{{token}}` in
  the stylesheet template), spacing from `space(n)`, fixed sizes from `SIZE`, radii from
  `RADIUS`, fonts from `font(role)`, icons from `gui/design/icons.py`. No module
  in `gui/` holds a colour, font-size or spacing literal (the tokens themselves and the
  platform's own window-button colours excepted). A value the tokens lack becomes a
  token, in both themes, that passes `tests/unit/gui/test_design_system.py`.
- **Components live in `gui/design/components.py`.** Reuse them; a new shared control is
  added there, never defined a second time in a view. Every component meets the rules
  under DESIGN.md §6: accessible names, fields that fit their content, shortcuts in the
  platform's keys, escaped data in rich text, copyable results.
- **Colour meanings:** one primary button per window. Accent: reported result,
  selection and focus, links, primary action, work in progress. Amber / green / red: a
  result's warnings, passes, errors.
- **Run state** (running, done, out of date, carrying warnings) shows only as navigation
  marks, session-switcher lines and the status bar. A result's own warnings and test
  outcomes show in its view as callouts and diagnostic marks. **The badge beside the
  title is a neutral summary** and states neither.
- **Sessions and files:** ⌘O adds files to the session on screen; *Replace data…* and
  *Load data into a new session…* (⇧⌘O) are separate commands; another experiment is
  another session (DESIGN.md §4).
- **Text** follows DESIGN.md §9: the glossary terms (Input-aware, Inputs as entered,
  Split, Needs refit), plain language, sentence case, units on every value, binding
  constants in M⁻¹, no message naming one input as the cause of a conflict.
- **Exported figures** use the light plot theme on white, whatever the window shows.
- **Open choices** — a design choice DESIGN.md does not settle — are put to the owner, never
  picked silently; the answer goes into DESIGN.md and the tokens.
- **Done means seen.** Render the view in light and dark with
  `uv run python -m docs.design.render <view> <out.png> [--theme dark] [--state …] [--menu …] [--pointer across,down]`
  — the running window as the app ships it, off screen — and compare it with its
  reference screen before calling it finished. A deliberate change to an approved view
  renders its screens again with `uv run python -m docs.design.render --all docs/design/screens`.
