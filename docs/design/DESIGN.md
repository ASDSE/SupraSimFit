# SupraSimFit design system

The design reference for the desktop app's interface: the approved design, final as
documented here. A design choice it does not settle is put to the owner, never picked
silently, and the answer becomes part of this document and the tokens.

- **Code.** `gui/design/` is the design system as code: `tokens.py` (colour, space,
  radius, sizes, type), `stylesheet.py` (the QSS template), `components.py` (the shared
  controls), `plot_theme.py` (pyqtgraph) and `icons.py`. The code holds every value; this
  document says how to use them.
- **Reference screens.** `docs/design/screens/<view>_<light|dark>.jpg` show each view as
  approved, at 1.5× scale (the main window is 1440 × 900, the Simulation window
  1280 × 800). They are rendered from `gui/design` by
  `uv run python -m docs.design.prototype.render --all`, so their colours are the tokens'. A view is finished when its real render
  (`docs/design/render.py`, the running window drawn off screen) matches its reference in both themes. Binding model and Plot appearance have no
  reference screen; they are forms built from the components (§8).
- **Rules for agents.** `gui/CLAUDE.md` is the short, binding version of this document.

Views set no stylesheet of their own.

---

## 1. Principles

1. **The data is the loudest thing on screen.** Chrome is quiet: one surface colour,
   hairline borders, no gradients, no decorative shadows.
2. **One meaning per colour.** Accent marks the reported result, selection and keyboard
   focus, links, the primary action, and work in progress. Amber, green and red mark a
   result's warnings, passes and errors. Neutral greys carry everything else, with one
   exception: in the titration plot each replicate has a colour of its own, which names it
   (`replicate-1` … `replicate-12`); Plot appearance (§8) may draw them all in grey instead.
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
| `replicate-1` … `replicate-12` | The replicates of the titration plot, one colour each: replicate *n* in the order the data name them A, B, … takes `replicate-n`, in every view and whether or not others are switched off; past twelve the colours repeat with the next mark. The same hue in both themes, lighter in dark |
| `replicate` | Every replicate's points when Plot appearance (§8) chooses *Grey*; the simulated replicates of the Simulation window |
| `replicate-off` | The × of a replicate chip switched off |
| `series-1`, `series-2` | The two series of the Sobol' chart: S₁ (solid) and S_T (outlined) |
| `species-dye`, `species-guest`, `species-host`, `species-step2` | The species of the Simulation window, one hue per partner: the dye and its complex with the host, the guest and its first complex, the free host, the second-step complex (HG₂, H₂G); solid in a complex, dashed when free |
| `heat-0` … `heat-8` | The heat scale of the sensitivity heatmap, low to high: perceptual and multi-hue (viridis), each stop lighter than the one below |
| `traffic` | Window controls of an inactive window |
| `shadow` | Shadows under what floats (popovers, menus, the Settings window) and under a toggle's knob, always at low opacity |

**Contrast.** Every text token meets WCAG AA (4.5 : 1) on every background text is drawn
on, hover and selection fills included, and each status colour on its own `-bg`.
`tests/unit/gui/test_design_system.py` checks both themes.

**Data marks** may use a token at reduced opacity; text never does. The approved plots
use: replicate dots and the × of a replicate not used at 80 %, in both themes; the sample histogram `text-secondary` at 62 %
inside the middle 90 % and 22 % outside; S₁ bars solid `series-1`, S_T bars `series-2` at
16 % (light) and 24 % (dark) inside a 90 % edge; interval bands `accent` at 8 %. The
reported result and fitted curve take `accent` (Plot appearance may give the curve another colour); the reading at the inputs as entered takes
`text-secondary` (its marker line in the sensitivity histogram is dashed `text-primary`,
its interval a `text-secondary` bracket). Each series and species colour stands out from `bg-surface`
by 3 : 1, no species takes `accent` or a series colour, and the heat scale rises in
lightness. Each replicate colour, at the 80 % its points are drawn at, stands out from
`bg-surface` by 3 : 1 and differs by a CIEDE2000 ΔE of 15 at least from every other
replicate colour, from the means' `text-primary` and from every colour the fitted curve
may take. At 80 % a point that overlaps another replicate's still shows its edge; much
lighter, twelve colours cannot meet both bounds on white. `test_design_system.py`
checks all of these.

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

**Plot text** (`PLOT_TEXT`, `plot_font()`) is a scale of its own: the axis text of the
titration plot and the head of its saved figure, in the three sizes Plot appearance offers
(§8). Each step is 2 px up and about one ratio from the last, and the weight is the same
at every step, so a larger size changes the size of the text and nothing else.

| Step | Tick labels | Axis titles |
|---|---|---|
| *Standard* | 14 px Normal, tabular | 16 px Medium |
| *Large* | 16 px Normal, tabular | 18 px Medium |
| *Larger* | 18 px Normal, tabular | 20 px Medium |

Numbers use tabular figures so columns align. Scientific notation is `1.59 × 10⁸`, thin
spaces around `×`, superscript exponent. Where a view states an interval in prose or a
headline it shares one power of ten — `1.14 – 2.08 × 10⁸ M⁻¹`; interval-chart rows and
the TXT/CSV reports use `estimate [low, high]`.

### Space, size and shape

- **Spacing** (`SPACE`, `space(n)`): 0, 2, 4, 8, 12, 16, 24, 32, 48 px. Margins and
  spacings take only these.
- **Fixed sizes** (`SIZE`): sidebar 232, side panel 320 (at least 280), toolbar 52,
  status bar 28, nav item 28, session switcher 44, controls 28, badges 18, plot axes 56
  (left) and 44 (bottom) px; the inputs grid of Input uncertainty: name 168, kind 156,
  stated in 88 and spread bar 96 px wide, rows 60 px high; the headline column of Fit
  results, 264; the sample histogram of Sensitivity, 104; the least height of an analysis
  plot on screen, 320; the marks of the analysis plots — an estimate or entered point as
  a 14-px diamond, a 9-px dot where the pointer meets a curve, a 1.25-px whisker with
  6-px caps — and Simulation's pointer marks, 10 px on the signal and 8 px on each
  species; a saved figure 900 px wide, each Ka profile or joint region in it 420 px high,
  the titration plot 600, Simulation's signal and species plots 520 and 400; the help
  dialog at least 560 × 420.
- **Radius** (`RADIUS`): 6 px controls, 8 px cards, 10 px popovers, menus and the
  Settings window, 2 px the Sobol' index bars; badges and toggles are fully rounded, at
  half their height.
- **Hairlines** are 1 px `border`. Panels are separated by hairlines, not gaps or shadows.
- **Shadows** only under what floats above the window — popovers, menus, the Settings
  window: `shadow` (black) at low opacity, deeper in dark than in light.

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
- **Edits of the data in place keep every result.** Adding or removing a file, stating the
  concentrations in another unit, typing or loading concentrations, and switching the
  channel of a plate export hide a result made on other data (*Results hidden*) and show
  it again, unchanged, once the data match it. Only *Replace data…* and removing the last
  file drop the results. Any change to the data stops the fit or analysis running, which
  was given the data as they were; the status bar says what changed and what it stopped.

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
  name, and a duplicate under its original's name with ` copy` (`IDA_system copy`).
  Double-clicking a name in the switcher renames it.
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
| **Tool button** | Icon and optional text, no border, `bg-hover` on hover; ▾ when it opens a menu; a checked state for toggles (side panel); disabled, its icon and text in `text-tertiary` with no hover fill |
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
  `text-secondary`; axis titles with the unit in parentheses (`Guest (µM)`,
  `Signal (10⁵ a.u.)`, the power of ten that of the largest value drawn). The titration
  plot sets its tick labels and axis titles at the plot text step its appearance chooses
  (§2, §8); the other plots in `small-number` and `label`. The axes are `axis-left` wide
  and `axis-bottom` tall with `small-number` and `label`, and grow by what larger text adds
  to a four-figure tick label and a title line, so they grow by even steps as the plot
  text does.
- No y tick marks: horizontal grid lines in `grid` follow the y axis's ticks; 4-px
  outward x ticks.
- **Titration series:** each replicate's dots in its own colour (`replicate-n`) at 80 %,
  6 px; a replicate switched off or left out by the fit as × in its own colour; mean ± SD
  as 6-px `text-primary` dots with 1-px
  `text-primary` error bars, capped a hundredth of the x span wide; the fitted curve 2 px
  accent, round caps. The legend names each replicate drawn by its letter, marked with
  its point or × in its colour (`A`, `B switched off`, `C left out by the fit`), then
  *Mean ± SD* and *Fit*. Plot appearance (§8) restyles these marks per session.
- **Sobol' bars:** S₁ solid in `series-1`, S_T outlined in `series-2`, each with a
  1.25-px `text-primary` whisker with 6-px caps; an index or whisker past the axis ends in
  a small arrow at its edge.
- **Heatmap:** cells on the heat scale (`heat-0` … `heat-8`), empty where no fit was made,
  a colour bar beside it with its ticks and title, the entered point as a diamond.
- **Log-Ka strips** (interval chart, histogram) carry no axis title; the shared power of
  ten and the unit follow the last tick (`× 10⁸ M⁻¹`).
- **Plot header row:** title in `body-strong`; a short description in `text-tertiary`
  where the title alone is ambiguous (*raw signal, as loaded*); then at the right the
  legend row, the view's own tools (replicate display, display unit, enlarge), *Reset
  view* on an interactive plot, and the image-export button last.
- **Interactive plots** — the titration plot of Measurements, Fit results and Plot
  appearance, and the plots of *Plot against each source* — zoom and pan
  (`PlotNavigation`); every other plot is static. A drag pans; ⌘-wheel (Ctrl on other
  platforms) or a pinch zooms about the pointer; a wheel or trackpad scroll without ⌘
  passes over the plot to the page that holds it, so a scrolling canvas scrolls. A
  double-click, or the *Reset view* tool (the `rotate` icon), puts the plot back on its
  home view — auto-range, or for the source plots the frame they opened on; the tool is
  enabled only while the view is off it. New data, another display unit or new fits put
  a titration plot back on auto-range, so what is drawn is in view; a theme change or
  another plot appearance draws the same data again and keeps the user's zoom.
- Linked plots (signal above species) share the x axis and the left axis width, so their
  plot areas line up.
- Exports render with the light theme on white.
- **Saved figure head:** every saved plot carries, above it, the head its header row
  states on screen — the title in `body-strong`, the description in `small`, the legend
  at the right (on a line of its own under them where one line cannot hold both) — then
  any notes in `small`, wrapped to the figure's width; a titration's title, description
  and notes read at its plot text step instead (§8). A saved **titration** is that head
  above the plot as the view draws it, with its replicate display and appearance: in
  Fit results, Plot appearance and *Export several…*, the legend of replicates, mean ± SD
  and fit, and a summary of the fit drawn — one line per binding constant with its
  reading and interval (`Kₐ guest 1.59 × 10⁸ M⁻¹ (Input-aware), 95 % interval 1.14 –
  2.08 × 10⁸ M⁻¹`), then `R² 0.9980 · Replicates used 7 of 8 (A switched off)`, and each
  other fit shown in a line of its numbers; in Measurements, the raw titration under
  *raw signal, as loaded* and its legend, with no fit.

---

## 8. Views

Each view below is the approved design; its reference screens are in `screens/`.

### Measurements — `measurements_*.jpg`
Canvas: the **Files** table (file, format, replicate letter, points; *Add files…*, × to
remove one), a one-line note on how added files are used (*Load data into a new
session…* as its link), and the raw **Titration** plot — each replicate's own points as
loaded, no mean and no curve, drawn by the one titration plot model with no fit — with a
*Display unit* menu in its header. While a fit is on view, a neutral callout above the
plot names it — *Fitted* `Kₐ guest 1.59 × 10⁸ M⁻¹ — the fitted curve is in Fit results.`
— with the action *Show fit results*; it is absent with no fit, while the results are
hidden and while a fit runs. Side panel *Measurement settings*: Concentrations (under the small heading *Units in
the file*, the unit the file's concentrations are stated in — a statement about the file,
which reinterprets the numbers, kept apart from the plot's *Display unit* — then the
concentration list, *Load vector…* / *Save vector…*), Replicates (replicate chips,
*Reset all*), Outlier removal (Z-score threshold, minimum replicates, *Apply* / *Reset*,
the last result in a sentence).

### Binding model
A form from the same components as Input uncertainty, under an intro sentence with
*About this model* (the help of the model chosen): **Model** — the two-level assay choice
(category, then model) with a one-line summary of what it fits; **Conditions** — the
entered conditions as fields with units; **Titrant stock** — *Stay constant* / *Are
diluted*, then the stock and the concentrations it holds; **Bounds of the fitted
parameters** with *Reset to defaults* and *Bounds from dye alone…*; **Replicates** — *The
average* / *Each replicate separately*, with a note on what the choice does (a model with
no binding constant shows only the note: it is fitted from the average). No side panel.

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
diagnostics →*, any callout, and the **Titration** plot with a replicate-display tool —
the one control of the session's replicate display: *Replicates and mean ± SD*, *Mean ±
SD only* or *Replicates only*, which Fit results, Plot appearance and every saved
titration figure draw alike.
With two binding constants the headline stacks: one row per Ka (K₁, K₂), each with its
value, interval and interval-chart rows, above the plot. What an interval needs said
beside it is its tooltip: what *Split* means on the interval chart, what widened it or
left a side open on the interval line. A fit of each replicate separately adds one line
of the single-replicate fits under the headline, why they differ from the interval on
hover. *All results and diagnostics →* shows the Fit details side panel where it is
hidden and brings Diagnostics into view. Where the curve is drawn at the inputs the fit
moved, the plot header says so in its description: *curve drawn at the fitted input
shifts*.

Side panel *Fit details*, which fits its least width beside the vertical scroll bar and
never scrolls sideways: Fit quality — a 2 × 2 grid of R² and RMSE, then replicates used
(`7 of 8`, note `A switched off`) and noise (`0.6 % + 80 a.u.`, note `from replicate
scatter`, the law's sentence on hover); Replicates — each replicate's own fit and its
p-value, where each was fitted separately; Diagnostics — each test with its mark, finding
and p-value, a test that could not run reading its reason, the full sentence of each on
hover; Parameters (estimate and unit; degenerate ones starred, with one footnote naming
the total the model holds fixed where its balance ties them, `* Not separately determined
while the dye total is fixed.`, and a note where a signal parameter ended on an entered
bound); Input shifts.

### Ka confidence — `confidence_*.jpg`
Canvas: the two readings side by side (Input-aware in `metric`; Inputs as entered in
`title`, with *Split* where the interval has a gap; each with its 95 % interval and how far
each end lies from the estimate) — the one reading, Inputs as entered, where every input is
exact — any callout (*Inputs conflict*, whose *Show the input shifts* opens Notes at the
shifts; a neutral notice while the Ka profile is still being worked out, the readings shown
at once), and **one profile plot per binding constant** holding both profiles: Input-aware
in `accent`, Inputs as entered in `text-secondary`, each estimate a diamond on its curve,
the reported interval as an `accent` band at 8 %. The header row of each plot carries the
legend, the enlarge tool (the plots take the whole canvas, the readings and callouts set
aside) and the image export; the readout card sits at the plot's top-right corner and reads
the reported estimate until the pointer reads another Ka, its value on a tag at the top of
the pointer's hairline; the accepted stretches of each reading run in a strip under the plot,
on its Ka axis. The y axis is each profile's **scaled drop**: its rise above its own minimum
divided by the rise its own 95 % test allows, so every curve crosses one cut-off line at 1
and a Ka below the line is one the data accept. Each curve is an exact rescaling of its own
test, so the interval edges are unchanged; where the test allows a larger drop because the
fit at that Ka holds a signal parameter on its bound, the curve breaks and a dotted riser
carries it down. With two binding constants the canvas scrolls: the profile plots stack, one
per Ka named by the glossary, with the joint region below them (the accepted pairs in
`text-secondary`, the best fit marked, each constant's own interval a faint band). A profile
that could not be worked out is said in a sentence in place of the plots. Side panel *Notes*
with *Reading this plot →*: Inputs conflict (the shifts in % and σ, with the warning mark
and p-value in the header) or the input shifts, Reading the curves, Split interval, Open
sides, Second binding step, What the intervals rest on, What widened the intervals, Joint
region. Exported figures use the same axis: each plot under its head — its name and legend,
its readings as a note — the joint region last, without the readout card.

### Sensitivity — `sensitivity_*.jpg`
Canvas, for sensitivity indices: one block per binding constant, named by the glossary
where there are two (Kₐ HG, Kₐ HG₂). Its headline is the spread of Kₐ from the stated
inputs (×/÷ factor in `title`, 1 SD in decades, the value it is centred on — the fit at the
inputs as entered — with the spread's sampling interval on hover) beside the sample
histogram, both readings of the fit marked on it (Input-aware: accent line and band;
Inputs as entered: dashed line and bracket), and *Plot against each source →*. Then any
callout: an input conflict of the fit, stated about the inputs together, with *Review in Ka
confidence* — the samples centre on the inputs as entered — or, without one, the neutral
*Not a confidence interval* with *Compare in Fit results*; a run that was stopped; a run
hidden because the data or settings changed since (its note alone, *Results hidden*); a
run that failed, its reason in plain words above the last result; before any run, the
refusal to vary nothing, with *Edit in Input uncertainty*. A constant's own callouts
follow: fits that ran to the Kₐ bounds, or — in place of its bars, budget and what-if — why
its indices are withheld. With two binding constants the run's callouts stand above both
blocks, each constant's own callouts inside its block. **Share of the variance, by source**: S₁ and S_T as two bars per
source, largest first, with their 95 % whiskers and values, and the notes under the chart
(an S_T below its S₁, sample groups left out). The **Variance budget** table — Source,
Stated, Elasticity, Variance (under the power of ten its numbers share), Spread if exact,
each number with its sampling interval, then *Interactions* and *All sources* — its Source
column as wide as the chart's names, so the bars start where Stated does. **What if one
source were known better**: *Reduce* (source menu) *to* (¾, ½ or ¼ of the stated
uncertainty, or exact) and the spread before and after, with the line that says what the
answer is read from. *Plot against each source →* opens a window of small plots, one per
source with a draw of its own: each sample's Kₐ against that source's draw in percent of
the entered value, so a source that matters shows as a trend; the random error of each
addition is one draw per titration point, and the window says it has no plot.

For a **heatmap**: one map per binding constant, Kₐ coloured on the heat scale (§2, §7)
with its colour bar, both axes in the inputs' units (the titrant, a series, in percent of
the concentrations entered), the entered point as a diamond, and the readout card at the
plot's top-right corner reading the cell under the pointer — its two inputs, Kₐ, its change
from the entered point and R² — or the entered cell without a pointer.

Before a run the canvas says what to do, with the platform shortcut of *Run analysis*;
while one runs and none is held, that it is running. Progress shows only where run state
does (§1).

Side panel *Analysis settings*: **Run** — mode (Sensitivity indices / Heatmap); for
indices, sample size N of 1024, 2048 or 4096 with what it costs, and *Fixed seed* with its
value; for a heatmap, the X axis and the Y axis (input menus), each stated as a σ with its
span (±1σ, ±2σ or ±3σ, ±2σ to start; an axis stated as a range spans its range and shows
no span), and the grid (11 × 11, 21 × 21 or 31 × 31, each with its fit count); what stops
the run stands beside the settings. **Error sources** — the sources the run varies,
read-only, with *Edit in Input uncertainty →*. **This run** — samples fitted and fits made,
the sample blocks or the grid, the median R² of the samples, the duration and worker
processes, the seed used, and whether it was stopped. **Display** — a log₁₀ or a linear Kₐ
axis. The settings that feed a run lock while one runs. The badge reads what the run shown
was made with, else the next run: `Sobol' · N = 1024`, `Heatmap · 21 × 21`. A saved figure
is drawn again in the light theme on white: the run's callouts as notes; per constant its
spread, the samples and the shares, with its own callouts and the chart's notes under them;
for a heatmap, each map with its colour bar.

### Plot appearance
The appearance of the session's **titration plot**: the plot in Measurements and in Fit
results, and the figure saved from it (also in a batch export). Ka confidence,
Sensitivity and the Simulation window take no appearance setting; they are drawn from the
tokens alone. Canvas: a sentence saying what the settings style, then the **Titration**
plot as Fit results draws it — the fit where there is one, else the data, in the
session's replicate display — with its
legend and the image export; with nothing loaded, a sentence saying what to load. Every
choice redraws the plot at once, here and in the other views. Side panel *Titration
plot*, headed by *Reset to defaults* (a link; it gives this session the built-in
appearance): **Markers** — replicate points and mean points *Small* / *Medium* / *Large*
(`marker-small` / `marker-medium` / `marker-large`), replicate mark *Circle* / *Square* /
*Triangle*; **Lines** — fitted curve and error bars *Thin* / *Medium* / *Thick*
(`stroke-thin` / `stroke-medium` / `stroke-thick`); **Colour** — replicate points, *By
replicate* (built in: each replicate its `replicate-n`, past twelve the colours again
with the next mark — circle, square, triangle — after the one chosen) or *Grey* (every
replicate in `replicate`, one mark), the menu showing the first three replicates' colours
beside *By replicate*; and fitted curve, *Teal* (`accent`, built in), *Blue* (`series-1`),
*Magenta* (`series-2`) or *Text colour* (`text-primary`) — never a free colour picker;
the means and their error bars stay `text-primary`, so no choice draws the replicates in
the colour of the means; **Text** — axis text *Standard* / *Large* /
*Larger*, the steps of the plot text (§2): tick labels 14, 16 or 18 px, axis titles 16, 18
or 20 px, at one weight; a saved figure's head follows it, its title at the axis titles'
size and its description and fit summary at the tick labels'; **New sessions** — *Use for new sessions* (outline button; one click stores the
whole appearance, and it is enabled while the stored one differs). The built-in appearance is the titration of §7. The form
feeds no fit or analysis, so it stays open while one runs. The badge reads *Built-in
appearance* or *Custom appearance*.

Each session holds its own appearance. *Duplicate <session>* copies it, and the session's
results file records it (`plot_appearance` beside `results`); a session that imports a
results file takes the appearance it records, and one that records none leaves the
session's own. *Use for new sessions* stores the appearance in the preferences as the start of every
session opened later; sessions already open keep their own; with none stored, a new
session starts from the built-in appearance. A stored appearance this version cannot read
is never passed over in silence: each new session opens with a warning saying so, starts
from the built-in appearance.

### Simulation window — `simulation_*.jpg`, `simulation_scrolled_*.jpg`, `simulation_overlay_*.jpg`
A separate window (1280 × 800), part of no session, opened with *Tools ▸ Simulate…*. The
main window's toolbar, side panel and status bar, without the sidebar. Toolbar:
*Simulation* and its summary badge, *Overlay data…*, *Export ▾* (Curve image…, which
saves the titration above the species on their shared axis as one PNG or SVG in the light
theme on white, each plot under its title with its legend — the titration's entries and the
species' names and line styles as the window shows them; Data file…), Help, the side-panel toggle, and the primary *Fit in new session*. Canvas:
**Titration** (simulated replicates at the measurement points, the model drawn
continuously) above **Species** on the same x axis, with the readout at the pointer. Each
species takes the colour of its partner — `species-dye`, `species-guest`, `species-host`,
`species-step2` (§2) — solid in a complex and dashed when free; the reported-result accent
and the Sobol' series colours are not used for species.
Side panel *Simulation settings*, its ⋯ menu holding *Save settings…* ⌘S, *Load
settings…* and *Reset to defaults*: Binding model (category and model menus), Binding
constants (log sliders, M⁻¹), Fixed totals (sliders, unit menus; then *Totals during the
titration* — *Stay constant* / *Are diluted*, as in Binding model), Concentrations (*Even
steps* or *Custom list*), Noise, Signal (coefficient sliders). Each slider's end values
are edited in place.

**Titrant stock.** The totals stay constant until the user chooses *Are diluted*; that
choice shows the stock concentration with its unit menu (it starts at 10 × the highest
titrant concentration of the grid as it is then, in the largest unit that keeps it at 1 or
more), and, where the model has two or
more fixed totals, *Stock also contains* with one box per total the stock holds at the
sample's own concentration. The simulation then dilutes through the assay's own
`fixed_total()`, the forward model the fit uses. A stock no more concentrated than the
highest titrant concentration, or one holding every total, is refused in plain words on
the status bar. Choosing a model goes back to constant totals. *Overlay data…* draws a measurement file over the model and takes
its concentrations as the grid.

**Noise** is the two-part law the fit reads off replicates, `var(y) = floor² +
(proportional · y)²`: *Add measurement noise*, the floor σ in a.u. and the proportional
part in %, either of which may be 0, the replicates, the seed and *New draw*. *Read from
overlaid data* fills the floor and the proportional part from the noise law the fitter
reads off the overlaid replicates; without an overlay of two or more replicates it is
disabled and its tooltip says why, and where the replicates show no law a message says
why in plain words. Choosing a model opens it with a floor of 0.5 % of its default
curve's range. Without noise one noise-free replicate is simulated.

**Fit in new session** opens a new session named after the simulation (*Simulated IDA*,
the model's short name), with no file row, holding the simulated data exactly as shown —
noisy or noise-free — and the binding model with its conditions: the fixed totals and the
binding constants the model takes as entered (Kₐ,dye of an IDA or GDA), each in the unit
shown, and the totals constant or diluted by the titrant stock as stated here, the stock in
its unit with the totals it holds. The values of what the fit searches for — the binding
constants it fits and the signal coefficients — do not travel, as starting values or as
bounds: the fit searches as it does on measured data. The session shows Fit results and
the fit runs.

### Settings window — `preferences_*.jpg`
Opened with ⌘, (*Settings…* in the app menu on macOS; *File ▸ Settings…* on Windows and
Linux). One short page in three settings groups: **General** (Appearance System / Light
/ Dark; check for updates when the app starts; the version and *Check now*), **New
sessions** (concentration unit; plot appearance for new sessions — the one stored by *Use
for new sessions*, with a way back to the built-in one), **Analysis**
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
