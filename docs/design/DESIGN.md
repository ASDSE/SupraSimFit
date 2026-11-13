# SupraSimFit design system

The design reference for the desktop app's interface: the approved design, final as
documented here. The choices still open are listed in §10; each is put to the owner when
the view it concerns is built.

- **Code.** `gui/design/` is the design system as code: `tokens.py` (colour, space,
  radius, sizes, type), `stylesheet.py` (the QSS template), `components.py` (the shared
  controls), `plot_theme.py` (pyqtgraph) and `icons.py`. The code holds every value; this
  document says how to use them.
- **Reference screens.** `docs/design/screens/<view>_<light|dark>.jpg` show each view as
  approved, at 1.5× scale (the main window is 1440 × 900, the Simulation window
  1280 × 800). They are rendered from `gui/design` by
  `uv run python -m docs.design.prototype.render --all`, so their colours are the tokens'. A view is finished when its real render
  matches its reference in both themes. Binding model and Plot appearance have no
  reference screen; they are forms built from the components (§8).
- **Rules for agents.** `gui/CLAUDE.md` is the short, binding version of this document.

Views set no stylesheet of their own.

---

## 1. Principles

1. **The data is the loudest thing on screen.** Chrome is quiet: one surface colour,
   hairline borders, no gradients, no decorative shadows.
2. **One meaning per colour.** Accent marks the reported result, selection and keyboard
   focus, links, the primary action, and work in progress. Amber, green and red mark a
   result's warnings, passes and errors. Neutral greys carry everything else, data
   included.
3. **Run state lives in three places.** Whether a session or analysis is running, done,
   out of date or carrying warnings shows as navigation marks, session-switcher lines and
   the status bar. A result's own warnings and test outcomes show inside its view, as
   callouts and diagnostic marks. The badge beside the title states neither.
4. **Every label means exactly what it says.** A number shown with a name is that
   quantity, in the unit shown. An axis, legend entry or sentence that can be read two
   ways is a defect.
5. **Plain language.** Users are chemists, not statisticians or programmers. Sentences say
   what happened, why, and what to do, in as few words as that takes.
6. **Light and dark are both first-class.** Every surface, control and plot is designed in
   both; neither is a recolouring of the other.
7. **A desktop tool for long sessions.** Dense but calm layouts, keyboard shortcuts for
   frequent commands, nothing that interrupts work that can be shown in place.

---

## 2. Foundations

### Colour

One map per theme in `tokens.py` (`LIGHT`, `DARK`), the same keys in both. Widgets read
colours only through a `Theme` — `t.q('token')`, `t['token']`, or `{{token}}` in the
stylesheet template.

| Token | Use |
|---|---|
| `bg-window` | Window background behind surfaces; Settings window; dark segmented-control track |
| `bg-sidebar` | Sidebar and status bar |
| `bg-surface` | Toolbar, canvas, side panel, plots, cards |
| `bg-raised` | Popovers, menus, tooltips; in dark, also the selected segment |
| `bg-subtle` | Wells: light segmented-control track, neutral badges, inset fields |
| `bg-hover` | Hover fill of rows, nav items, menu rows and tool buttons |
| `bg-selected` | Selected nav item and selected list row |
| `border` / `border-strong` | Hairlines and dividers / control outlines and plot axes |
| `grid` | Plot grid lines |
| `text-primary` | Body text, values, titles |
| `text-secondary` | Labels, captions, axis tick labels, secondary values |
| `text-tertiary` | Hints, notes, units after a value, shortcuts in menus, column headers of dense tables |
| `accent`, `accent-hover` | Reported (input-aware) result and fitted curve; selection; 2-px keyboard focus ring; links; primary button; work in progress (status-bar dot while work runs, the switcher's busy dot, progress rings); the open session switcher's outline and icon tile |
| `accent-subtle` | Tint behind accent text and marks: Input-aware badge, the switcher's icon tile |
| `on-accent` | Text and icons on accent |
| `success`, `warning`, `danger` with `-bg` (and `warning-border`) | A result's passed test, warning or error: diagnostic marks, callouts, messages |
| `replicate` | Replicate data points |
| `replicate-off` | A replicate switched off (drawn as ×) |
| `traffic` | Window controls of an inactive window |

**Contrast.** Every text token meets WCAG AA (4.5 : 1) on every background text is drawn
on, hover and selection fills included, and each status colour on its own `-bg`.
`tests/unit/gui/test_design_system.py` checks both themes.

**Data marks** may use a token at reduced opacity; text never does. The approved plots
use: replicate dots `replicate` at 45 %; the sample histogram `text-secondary` at 62 %
inside the middle 90 % and 22 % outside; the S_T bar fill `text-secondary` at 16 % (light)
and 24 % (dark) inside a 72 % edge; interval bands `accent` at 8 %. The reported result
and fitted curve take `accent`; the reading at the inputs as entered takes
`text-secondary` (its marker line in the sensitivity histogram is dashed `text-primary`).
S₁ and S_T take `series-1` and `series-2` (§8); the species colours of Simulation are open (§10).

### Type

The platform UI font (SF Pro on macOS, Segoe UI on Windows), four sizes on any screen.

| Role | Size / weight | Use |
|---|---|---|
| `metric` | 28 px DemiBold, tabular | The headline value of a view (the reported Ka) |
| `title` | 20 px DemiBold | Toolbar title |
| `body`, `body-strong` | 13 px Normal / DemiBold | Text, controls, section titles, selected segments |
| `number`, `number-strong` | 13 px, tabular | Values in rows and tables |
| `label`, `small`, `small-number` | 12 px Medium / Normal / tabular | Captions, axis titles, ticks, hints |
| `overline` | 12 px DemiBold, sentence case, `text-tertiary` | Sidebar group titles, popover headings |

Numbers use tabular figures so columns align. Scientific notation is `1.59 × 10⁸`, thin
spaces around `×`, superscript exponent. Where a view states an interval in prose or a
headline it shares one power of ten — `1.14 – 2.08 × 10⁸ M⁻¹`; interval-chart rows and
the TXT/CSV reports use `estimate [low, high]`.

### Space, size and shape

- **Spacing** (`SPACE`, `space(n)`): 0, 2, 4, 8, 12, 16, 24, 32, 48 px. Margins and
  spacings take only these.
- **Fixed sizes** (`SIZE`): sidebar 232, side panel 320 (at least 280), toolbar 52,
  status bar 28, nav item 28, session switcher 44, controls 28, badges 18, plot axes 56
  (left) and 44 (bottom) px.
- **Radius** (`RADIUS`): 6 px controls, 8 px cards, 10 px popovers, menus and the
  Settings window, pill for badges and toggles.
- **Hairlines** are 1 px `border`. Panels are separated by hairlines, not gaps or shadows.
- **Shadows** only under what floats above the window — popovers, menus, the Settings
  window: black at low opacity, deeper in dark than in light.

### Icons

Line icons in the Lucide style (ISC licence) on a 24-unit grid with round caps, tinted
from a text or accent token: 16 px with stroke 1.75 in controls and navigation, 14 px in
dense rows, 12 px with stroke 2–2.6 for chevrons and check marks inside fields, chips and
marks. The set is `gui/design/icons.py`; a new icon is added there in the same style.

### Themes

Appearance follows the System / Light / Dark setting (§8, Settings), applied at once to
every open window. One app-level object holds the current `Theme` and emits a signal when
it changes; under *System* it follows the operating system's colour scheme
(`QStyleHints.colorScheme`). On a change it re-applies the stylesheet and palette, and
every painted component, which reads the theme from that object, repaints. **Exported
figures always use the light plot theme on a white background**, whatever the window
shows.

### The stylesheet contract

`stylesheet.py` styles widgets by object name and by two dynamic properties; a widget
without them gets no styling.

| Selector | Set on |
|---|---|
| `#Sidebar`, `#StatusBar` | The sidebar and the status bar |
| `#Toolbar`, `#Canvas`, `#Inspector`, `#InspectorBody` | Toolbar, canvas, side panel and its scrolled body |
| `role="hairline"` | 1-px dividers |
| `role="badge"` + `tone="accent"` / `"neutral"` | Badges |
| `role="link"` | Link buttons |
| `tone="secondary"` / `"tertiary"` | Labels in those text colours |

---

## 3. The main window

![Fit results](screens/fit_light.jpg)

```
┌──────────┬──────────────────────────────────────────────────────────────┐
│ ● ● ●  ▯ │ Title  [summary badge]   Load data ▾  Export ▾ │ ? ▯  [Run] │ toolbar 52
│ Session ⇅│──────────────────────────────────────────────┬───────────────│
│          │ Headline                       Detail link → │ Side panel  × │
│ Experiment                                              │ ▾ Section     │
│  items  ✓│ Callout                                      │ ▾ Section     │
│ Analysis │                                              │ ▸ Section     │
│  items  ●│ Plot header: title · legend · tools · ⤓     │               │
│ Presentation  Plot                                      │               │
│          │                                              │               │
│ file card│                                              │               │
├──────────┴──────────────────────────────────────────────┴───────────────┤
│ ● what is running                                      model line       │ status 28
└─────────────────────────────────────────────────────────────────────────┘
  sidebar 232                                               side panel 320
```

- **Sidebar** (`bg-sidebar`): a 52-px top row with the sidebar toggle — on macOS the
  sidebar reaches up under a transparent title bar and the row also holds the native
  window controls; Windows and Linux keep the system's own title bar above the window — the **session
  switcher**; the navigation in three groups — *Experiment* (Measurements, Binding model,
  Input uncertainty), *Analysis* (Fit results, Ka confidence, Sensitivity),
  *Presentation* (Plot appearance); and the **file card** at its foot.
- **Navigation marks** at the right of an item: ✓ done; amber dot — the result carries a
  warning; hollow ring — out of date, its data or settings changed since it ran; none —
  not run. The selected item has the `bg-selected` fill and a 3-px accent bar at its left.
- **File card**: the data behind the session on screen — the file name (`GDA_run1.txt
  + 2 more` for several) and `<assay> · <n> replicates × <m> points`. Clicking it opens
  Measurements.
- **Toolbar** (`bg-surface`): the view title in `title` and its summary badge; at the
  right *Load data ▾*, *Export ▾*, a divider, Help, the side-panel toggle and the
  **primary button** — *Run fit* (⌘R), or *Run analysis* in Sensitivity — at one fixed
  width in every view, so the toolbar never shifts. It belongs to the session on screen:
  while that session runs it reads *Stop* (⌘R stops too). *Export ▾* holds: Results file… (⌘S,
  re-opens with its fit), Report (TXT)…, Table (CSV)…, Raw data…, Plot image…, and
  Export several… (⇧⌘E).
- **Canvas** (`bg-surface`): headline first — its row may end in one detail link at the
  right (*All results and diagnostics →*) — then any callout, then the plot or table.
  Content left edges share one column.
- **Side panel** (`bg-surface`, hairline on its left): the view's settings and details in
  collapsible sections. Its header names it (*Fit details*, *Measurement settings*,
  *Analysis settings*, *Notes*, *Effect on the fit*, *Simulation settings*), may hold one
  link (*Reading this plot →*), and closes it. Fit results and Ka confidence keep fit
  quality, diagnostics and notes in the side panel.
- **Status bar** (`bg-sidebar`): left, a dot — accent while work runs, `text-tertiary`
  when idle — and a summary of all running work (`2 running · IDA_system fitting ·
  DBA_HtoD_0411 Sensitivity 62 %`, or `Ready` with the session on screen's last message);
  clicking it opens the session switcher; right, the model line in `text-tertiary` (`Indicator displacement
  · 1 binding constant · Profile likelihood, 95 % · Weighted by noise law`).
- **Menu bar**: *File* (New session ⌘T, Load data…, Open results file…, the export
  commands, Settings… on Windows and Linux, Quit), *Tools* (Simulate…, Demo IDA), *View*,
  *Help* (Reading the plots…, Check for updates…). On macOS *Settings…* ⌘, is in the app
  menu.

**Shortcuts** are written here in macOS notation. In code a command uses Qt's standard
key where one exists (`QKeySequence.StandardKey`: Open, Save, Close, Preferences, Quit),
otherwise a `Ctrl+…` sequence, which Qt shows as ⌘ on macOS; every shortcut on screen is
rendered from its key sequence. A platform with no standard key for a command gives it no
shortcut.

One primary (filled accent) button per window. Every other toolbar command is a tool
button.

---

## 4. Sessions and files

A **session is one experiment**: its data, binding model, input uncertainties and
analyses. A different experiment is a different session. One window holds every open
session, reached through the session switcher.

![Session switcher](screens/switcher_light.jpg)

- **Session switcher** (top of the sidebar, 44 px): an icon tile, the session's name and
  `<assay> · <n> replicates`, the number of open sessions, and an accent dot when another
  session is busy. Clicking opens a popover headed *Open sessions* (⌘1 – ⌘9): one row per
  session with its name, its second line and a one-line summary at the right — its
  reported Ka and any warning (`Ka 1.59 × 10⁸ M⁻¹ · 1 warning`, amber dot; a session with
  two binding constants gives their count, `2 binding constants · 1 warning`), its progress
  while running (`Fitting · 62 %`, accent ring), or `Needs refit · data changed` (hollow
  ring) — the session on screen marked with ✓; then the commands *New session* ⌘T, *Load
  data into a new session…* ⇧⌘O, *Open results file…*, *Duplicate <session>*, *Close
  <session>* ⌘W.
- **Load data ▾** has three commands: *Add files to this session…* ⌘O, *Replace data…*,
  *Load data into a new session…* ⇧⌘O. Adding keeps every fit; replacing is always an
  explicit choice. Every load command goes through the session model (`load_files()`, `add_files()`).

![Load data menu](screens/measurements_load_light.jpg)

- **Files of one session become its replicates** on one shared concentration grid. Files
  are added later and removed one at a time from the Files table in Measurements. A file
  on a different grid is refused with a message that says so. A multi-channel file
  (EnSight) is loaded alone, one channel at a time.
- **Running work.** Each session runs its own fit or analysis, and work continues when
  another session is on screen. A running session shows its progress along a thin accent
  line at the top of its canvas — indeterminate until the work can be counted, then
  filling — and in its switcher row (ring and `Fitting · 62 %`). Its canvas keeps the last
  result, marked out of date. The controls that feed the run (binding model, input
  uncertainties, Sensitivity settings) are locked until it finishes or is stopped. The
  toolbar's primary button reads *Stop* for the session on screen while it runs; the
  status bar lists everything running, with no combined percentage, because a fit and a
  Sobol' run are counted in different units. Each session keeps its own last status
  message. ⌘O loads into the session on screen and leaves every other session as it is.
- **Session names.** A session is *New session* until data is loaded, then the first
  file's name without its extension (`IDA_system`); a results file opens under its saved
  name. Double-clicking a name in the switcher renames it.
- **Closing.** Closing a running session asks first (*Stop the fit and close
  IDA_system?*) and then stops its work. Closing the last session leaves one empty *New
  session*, so the window is never blank.

---

## 5. Badges and callouts

- The **badge beside the toolbar title is a summary** of what the view shows or is
  computed from — `Input-aware · 7 of 8 replicates`, `3 files`, `4 inputs vary`, `Profile
  likelihood · 95 %`, `Sobol' · N = 1024`, `IDA · 24 points · 3 replicates` — in the
  `neutral` tone.
- **Badges elsewhere** label a reading: `accent` for Input-aware; `neutral` for plain
  labels such as *Inputs as entered* and *Split*.
- **Callouts** carry a result's warning in its view: an icon, a bold title, one or two
  sentences, and at most one action link at the right (`Inputs conflict  Together, the
  inputs moved further from their entered values than you stated.  Show the input
  shifts`; in Sensitivity, *Review in Ka confidence*). Warning callouts use `warning-bg`
  with `warning-border`; neutral notes use `bg-subtle`.

---

## 6. Components

`gui/design/components.py` holds every shared control; each exists once, and a new one
is added there. QSS styles what Qt's widgets can express (§2); the rest is painted from
the same tokens.

| Component | What it is and its rules |
|---|---|
| **Primary button** | Filled accent, `on-accent` icon and label; one per window; fixed width in the toolbar |
| **Tool button** | Icon and optional text, no border, `bg-hover` on hover; ▾ when it opens a menu; a checked state for toggles (side panel) |
| **Outline button** | `border-strong` outline on `bg-surface`; secondary actions in forms (*Apply*, *Check now*) |
| **Link** | Accent text with an optional trailing →; navigates or opens detail |
| **Focus ring** | 2 px accent around the focused control, on every keyboard-reachable control |
| **Segmented control** | Mutually exclusive options (Fixed / σ / Range, units, modes). Light: `bg-subtle` track, selected segment `bg-surface` with a `border` outline, other labels `text-secondary`. Dark: `bg-window` track, selected segment `bg-raised` lifted by 6 % `text-primary` with a `border-strong` outline, other labels `text-tertiary`. Selected label `body-strong`; single options can be disabled |
| **Field** | Right-aligned value in a 6-px-radius box, an optional leading symbol inside (`σ`); its unit beside it — a segmented control where the unit is chosen once for a row or section, a menu beside a single value; a disabled state (Fixed seed off) |
| **Dropdown** | Field-styled box with the current choice and a chevron; opens a menu |
| **Checkbox** | Box with an accent check; label to its right |
| **Toggle** | Pill switch for on/off settings in the Settings window; accent when on |
| **Slider** | Track in accent up to the knob, ticks, and its two end values at either side, each edited in place |
| **Badge** | Pill, 18 px; tones `neutral` and `accent` (§5) |
| **Menu** | Popover on `bg-raised`: icon, label, right-aligned shortcut in `text-tertiary`, separators, optional footer note |
| **Navigation item** | Icon, label, status mark; hover and selected fills (§3) |
| **Session switcher and popover** | §4; the popover is `bg-raised`, 10-px radius, `border` outline, floating shadow |
| **File card** | Sidebar foot (§3) |
| **Side-panel section** | Disclosure header — chevron, `body-strong` title, trailing summary in `text-tertiary`, optionally a warning icon — its content, a hairline below |
| **Settings group** | Rows separated by hairlines inside a bordered card on `bg-window`; a group title above |
| **Callout** | §5 |
| **Interval chart** | Log-Ka strip comparing intervals: Input-aware in accent, Inputs as entered in `text-secondary`, accepted stretches as bars, estimates as dots, numbers to the right. In the side panel a compact form stacks label and numbers above each bar |
| **Shift bar** | An input's shift in σ against a ±1 σ band. In Fit details the % stands beside it, σ on hover; in the Ka confidence notes both % and σ |
| **Replicate chip** | Replicate letter with ✓ when used or × when switched off, `z` when the outlier filter switched it off; click toggles |
| **Legend row** | Above a plot, right-aligned, each entry drawn with the series' own mark |
| **Readout** | The values under the pointer: a dotted vertical hairline through the plot(s) with a value tag, and the values in a row above the plot or a card at its top-right corner; in Simulation the species readout row is also the legend |
| **Table** | Header row in `text-tertiary`, rows separated by hairlines, numbers right-aligned in tabular figures |

Every component meets these rules:

- **Accessible names.** Every control carries an accessible name that says which input
  it sets, unit included (`Lower bound of Kₐ guest (M⁻¹)`), also where its visible label
  is a separate rich-text label.
- **Fields fit their content.** A numeric field is as wide as the widest value it must
  show — sign, mantissa and a three-digit exponent, or a ten-digit seed — measured from
  its font and re-measured when the font changes.
- **Shortcuts in the platform's keys.** Every shortcut shown in a menu, tooltip or hint
  is rendered from its action's `QKeySequence` in native text (⌘ on macOS, Ctrl
  elsewhere), never written as a literal.
- **Data in rich text is escaped.** File names, replicate names and any other text that
  comes from data are HTML-escaped before they enter a rich-text label.
- **Results can be copied.** The headline value, intervals and the Fit details tables
  are selectable.
- **Selection holds.** Clicking the selected navigation item keeps it selected.

---

## 7. Plots

pyqtgraph draws the data plots (titration, profile, species); the interval chart, the
sample histogram and the Sobol' bars are painted components. Both read the same tokens.
`gui/design/plot_theme.py` styles every pyqtgraph plot:

- `bg-surface` background; left and bottom axes only, in `border-strong`; tick labels in
  `text-secondary`, `small-number`; axis titles in the `label` role with the unit in
  parentheses (`Guest (µM)`, `Signal (10⁵ a.u.)`; the exponent follows the axis's
  `on_exponent_changed` callback).
- No y tick marks: horizontal grid lines in `grid` follow the y axis's ticks; 4-px
  outward x ticks.
- **Titration series:** replicate dots in `replicate` at 45 %, 6 px; switched-off
  replicates as × in `replicate-off`; mean ± SD as 6-px `text-primary` dots with 1-px
  `text-primary` error bars; the fitted curve 2 px accent, round caps.
- **Sobol' bars:** S₁ solid, S_T outlined, each with a 1.25-px `text-primary` whisker
  with 6-px caps.
- **Log-Ka strips** (interval chart, histogram) carry no axis title; the shared power of
  ten and the unit follow the last tick (`× 10⁸ M⁻¹`).
- **Plot header row:** title in `body-strong`; a short description in `text-tertiary`
  where the title alone is ambiguous (*raw signal, as loaded*); then at the right the
  legend row, the view's own tools (replicate display, display unit, enlarge), and the
  image-export button last.
- Linked plots (signal above species) share the x axis and the left axis width, so their
  plot areas line up.
- Exports render with the light theme on white.

---

## 8. Views

Each view below is the approved design; its reference screens are in `screens/`.

### Measurements — `measurements_*.jpg`
Canvas: the **Files** table (file, format, replicate letter, points; *Add files…*, × to
remove one), a one-line note on how added files are used (*Load data into a new
session…* as its link), and the raw **Titration** plot with a *Display unit* menu in its
header. Side panel *Measurement settings*: Concentrations (imported unit, the
concentration list, *Load vector…* / *Save vector…*), Replicates (replicate chips,
*Reset all*), Outlier removal (Z-score threshold, minimum replicates, *Apply* / *Reset*,
the last result in a sentence).

### Binding model
A form from the same components as Input uncertainty: the two-level assay choice
(category, then model), the entered conditions as fields with units, the titrant stock,
and the bounds of the fitted parameters.

### Input uncertainty — `uncertainty_*.jpg`
Canvas: an intro sentence with *About input uncertainty*; **Each input** — one row per
input on a shared column grid: name and entered value, Fixed / σ / Range, amount, stated
in (% or unit), the ±2σ span on one shared ±20 % axis, and the span in numbers. A range
states its *from* and *to* in two fields stacked in the amount column; the unit is the one
the input's condition is entered in, and the titrant, a series, is stated in % only. A
fixed input shows no amount. **Shared error sources** with *Add shared source*; **Random error of each addition**.
Side panel *Effect on the fit*: the interval of the last fit (Input-aware against Inputs
as entered, compact interval chart), the three tests against what was stated, and
*Also used by*.

### Fit results — `fit_*.jpg`
Canvas: the headline — Ka in `metric` with its Input-aware badge and 95 % interval —
the interval chart against the reading at the inputs as entered, *All results and
diagnostics →*, any callout, and the **Titration** plot with a replicate-display tool.
With two binding constants the headline stacks: one row per Ka (K₁, K₂), each with its
value, interval and interval-chart rows, above the plot. Side panel *Fit details*: Fit quality (R², RMSE, replicates used, noise), Diagnostics
(each test with its mark and p-value), Parameters (estimate and unit; degenerate ones
starred and explained), Input shifts, Display.

### Ka confidence — `confidence_*.jpg`
Canvas: the two readings side by side (Input-aware; Inputs as entered, with *Split* where
the interval has a gap), any callout, and **one profile plot per binding constant**
holding both profiles, an enlarge tool, the pointer readout card, and the accepted
stretches of each interval in a strip under the plot. Side panel *Notes* with *Reading
this plot →*: the input conflict with the shifts, how to read the curves, the split
interval, what the intervals rest on. The y axis is each profile's **scaled drop**: its
rise above its own minimum divided by the rise its own 95 % test allows, so every curve
crosses one cut-off line at 1 and a Ka below the line is one the data accept. Each curve
is an exact rescaling of its own test, so the interval edges are unchanged; exported
figures use the same axis. With two binding constants the profile plots stack, one per
Ka, with the joint region below them.

### Sensitivity — `sensitivity_*.jpg`
Canvas: the spread of Ka from the stated inputs (×/÷ factor, 1 SD in decades, the centre
it is read around) beside the sample histogram with both intervals marked and *Plot
against each source →*; any callout — the samples are drawn around the inputs as
entered, so an input conflict is stated here; **Share of the variance, by source** — S₁
and S_T as two bars per source with their 95 % whiskers and values; the **Variance
budget** table; **What if one source were known better**. S₁ and S_T take two series
colours of their own (`series-1`, `series-2`). *Plot against each source →* opens a
window of small plots, one per error source: each sample's Ka against that source's
draw, so a source that matters shows as a trend. The **heatmap** colours Ka on a
perceptual multi-hue scale (viridis-like), defined in both themes, with the value under
the pointer as a readout. With two binding constants the canvas holds one block per Ka;
a Ka whose indices are withheld shows a callout saying why in place of its bars. Side panel *Analysis
settings*: Run (mode Sensitivity indices / Heatmap, sample size N of 1024, 2048 or 4096,
fixed seed), Error sources (*Edit in Input uncertainty →*), This run, Display (log₁₀ or
linear Ka axis).

### Plot appearance
A form in the side panel beside the live plot: markers, lines, colours and text sizes,
and *Use for new sessions*. Built from the Settings-window components.

### Simulation window — `simulation_*.jpg`, `simulation_scrolled_*.jpg`, `simulation_overlay_*.jpg`
A separate window (1280 × 800), part of no session, opened with *Tools ▸ Simulate…*. The
main window's toolbar, side panel and status bar, without the sidebar. Toolbar:
*Simulation* and its summary badge, *Overlay data…*, *Export ▾* (Curve image…, Data
file…), Help, the side-panel toggle, and the primary *Fit in new session*. Canvas:
**Titration** (simulated replicates at the measurement points, the model drawn
continuously) above **Species** on the same x axis, with the readout at the pointer.
Side panel *Simulation settings*, its ⋯ menu holding *Save settings…* ⌘S, *Load
settings…* and *Reset to defaults*: Binding model (category and model menus), Binding
constants (log sliders, M⁻¹), Fixed totals (sliders, unit menus), Concentrations (*Even
steps* or *Custom list*), Noise (add noise, σ in a.u., replicates, seed, new draw),
Signal (coefficient sliders). Each slider's end values are edited in place. *Overlay
data…* draws a measurement file over the model and takes its concentrations as the grid.

### Settings window — `preferences_*.jpg`
Opened with ⌘, (*Settings…* in the app menu on macOS; *File ▸ Settings…* on Windows and
Linux). One short page in three settings groups: **General** (Appearance System / Light
/ Dark; check for updates when the app starts; the version and *Check now*), **New
sessions** (concentration unit; plot appearance for new sessions), **Analysis**
(processor cores). Changes apply at once; the window has no OK or Cancel.

---

## 9. Writing

| Term | Meaning |
|---|---|
| **Input-aware** | The fit and interval with the entered inputs free to move inside their stated uncertainties |
| **Inputs as entered** | The fit and interval taking every entered input as exact |
| **Split** | An interval made of separate accepted stretches |
| **Needs refit** | A result whose data or settings changed after it ran |
| **Kₐ** | Association constant (never Kd), in M⁻¹, written with its subscript and name: Kₐ guest, Kₐ,dye |
| **σ / Range / Fixed** | One standard deviation of a normal distribution / drawn evenly between two ends / taken as exact |
| **Replicate** | One titration series; the files of a session become its replicates |
| **Session** | One experiment in the window |

- Say what happened, why, and what to do next, in plain words. No exception text, library
  names or developer phrasing. Name the files or values involved when it helps.
- Short: one sentence where one will do.
- A conflict is about the inputs together. No message, note or help text names one input
  as its cause.
- An estimate on a Ka bound is written *not limited below / above*, never as a number on
  that side.
- Every value carries its unit: concentrations in nM / µM / mM / M, binding constants in
  M⁻¹, signals in a.u.
- Labels, titles and commands use sentence case (*Load data*, *Outlier removal*).
  Commands that open a window or ask for more end in `…`.

---

## 10. Decided when the view is built

Put to the owner when the view is built; the answer then becomes part of this document
and the tokens.

1. **Species colours** of the stepwise models in Simulation; new series colours become
   tokens in both themes.
2. **Sensitivity heatmap** — its Run settings.
3. **Fit in new session** (Simulation) — it sends the noisy replicates as shown; the
   simulated values do not travel as starting values.
4. **Simulation noise** — an absolute σ in a.u., which the engine does not yet offer.
5. **Plot appearance for new sessions** — what is stored and where.
