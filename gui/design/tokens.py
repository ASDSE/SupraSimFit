"""Design tokens: the one source of colour, space, radius and type.

Every visual value in a view built on ``gui.design`` comes from here: the stylesheet
(:mod:`gui.design.stylesheet`), the QPalette, the custom-painted components and the
plot theme (:mod:`gui.design.plot_theme`). ``docs/design/DESIGN.md`` says what each
token is for.
"""

from __future__ import annotations

import re

from PyQt6.QtGui import QColor, QFont, QFontDatabase, QPalette

# ── Space: a 4-pt scale with one 2-px step. The only values margins and spacings take.
SPACE = {0: 0, 1: 2, 2: 4, 3: 8, 4: 12, 5: 16, 6: 24, 7: 32, 8: 48}

# ── Radius: controls, surfaces (cards), popovers and floating windows, index bars. Badges and toggles are
#    fully rounded, at half their height.
RADIUS = {'control': 6, 'surface': 8, 'popover': 10, 'bar': 2}

# ── Fixed sizes of the window and its components, in px.
SIZE = {
    'sidebar': 232,
    'inspector': 320,
    'inspector-min': 280,
    'toolbar': 52,
    'statusbar': 28,
    'nav-item': 28,
    'switcher': 44,
    'control': 28,
    'badge': 18,
    'menu-item': 32,
    # A menu row's icon and its check mark.
    'menu-icon': 16,
    'menu-check': 14,
    # The column grid of the Input uncertainty inputs table; the span column takes the rest.
    'input-name': 168,
    'input-kind': 156,
    'stated-in': 88,
    'spread-bar': 96,
    'input-row': 60,
    # The headline column of Fit results: a binding constant's name, value and interval.
    'headline': 264,
    # The height of the bars of Sensitivity's sample histogram; its labels above and its axis below add their text.
    'histogram': 64,
    # The least height of an analysis plot on screen (a Ka profile, the joint region), below which its canvas scrolls.
    'plot-min': 320,
    # The longest line of help or warning text under a control, for a comfortable reading measure.
    'measure': 640,
    # The width of the Settings window.
    'settings-window': 640,
    # The one column of controls on the right of the Settings window: its segmented controls and menu.
    'settings-control': 216,
    # The knob grid of Simulation's side panel: a value field, its unit, and a slider end's text column.
    'knob-value': 112,
    'knob-unit': 76,
    'slider-end': 36,
    # The point sizes and stroke widths Plot appearance offers for the titration plot.
    'marker-small': 4,
    'marker-medium': 6,
    'marker-large': 9,
    'stroke-thin': 1,
    'stroke-medium': 2,
    'stroke-thick': 3,
    # The marks of the analysis plots: an estimate or entered point as a diamond, the dot
    # where the pointer meets a curve, and the 95 % whisker of a Sobol' bar with its caps.
    'diamond': 14,
    'pointer-dot': 9,
    'whisker': 1.25,
    'whisker-cap': 6,
    # Simulation's marks where the pointer meets the signal and each species.
    'pointer-signal': 10,
    'pointer-species': 8,
    # A saved figure: the white margin round everything in it, its width inside that margin, and the height of each plot in it — a Ka profile or the
    # joint region, the titration plot, Simulation's signal and species plots.
    'figure-margin': 24,
    'export-width': 900,
    'export-plot': 420,
    'export-titration': 600,
    'export-signal': 520,
    'export-species': 400,
}

# ── Durations, in ms: how long the mark of a place a link revealed stays on it.
DURATION = {'reveal-mark': 1500}

#: Colours of the replicates (``replicate-1`` … ``replicate-12``); past them the colours repeat with the next mark.
REPLICATE_COLOURS = 12

#: Stops of the heat scale (``heat-0`` … ``heat-8``), evenly spaced from low to high.
HEAT_STOPS = 9

# ── Colour: one map per theme, the same keys in both.
LIGHT = {
    'bg-window': '#F5F6F8',
    'bg-sidebar': '#F0F2F4',
    'bg-surface': '#FFFFFF',
    'bg-raised': '#FFFFFF',
    'bg-subtle': '#F3F4F6',
    'bg-hover': '#E8EBEE',
    'bg-selected': '#E1EFF0',
    'border': '#E2E5E9',
    'border-strong': '#C9CED4',
    'grid': '#EEF0F2',
    'text-primary': '#1C2024',
    'text-secondary': '#4C535C',
    'text-tertiary': '#656A71',
    # A disabled control's text and icon: quieter than any enabled text, still read as a word.
    'text-disabled': '#A1A7AE',
    'accent': '#067581',
    'accent-hover': '#06646E',
    'accent-subtle': '#E6F3F4',
    'on-accent': '#FFFFFF',
    'success': '#1A7F37',
    'success-bg': '#E9F6EC',
    'warning': '#9A6700',
    'warning-bg': '#FFF8E1',
    'warning-border': '#F2DFA8',
    'danger': '#C4314B',
    'danger-bg': '#FDECEE',
    'replicate': '#8A919A',
    'replicate-off': '#8A919A',
    # The replicates of the titration plot, one colour each in the order the data name them A, B, …:
    # at the opacity the points are drawn at, each stands out from the plot by 3 : 1 and from every
    # other replicate, the means and the fitted curve's colours by ΔE₀₀ 15; the same hue in both themes.
    'replicate-1': '#267AA0',
    'replicate-2': '#D90D33',
    'replicate-3': '#275005',
    'replicate-4': '#6015B2',
    'replicate-5': '#AD660A',
    'replicate-6': '#168169',
    'replicate-7': '#565A8C',
    'replicate-8': '#A26482',
    'replicate-9': '#5D420D',
    'replicate-10': '#894736',
    'replicate-11': '#7C7A3C',
    'replicate-12': '#17900E',
    'traffic': '#D9DCE0',
    'shadow': '#000000',
    # The two series of the Sobol' chart: S₁ and S_T.
    'series-1': '#2C6FB0',
    'series-2': '#B04F8E',
    # The species of Simulation, one hue per partner: the dye and its complex with the
    # host, the guest and its first complex, the free host, and the second-step complex (HG₂, H₂G).
    'species-dye': '#7048C8',
    'species-guest': '#B8580F',
    'species-host': '#6B7480',
    'species-step2': '#6E7A12',
    # The heat scale of the sensitivity heatmap, low to high: perceptual and multi-hue (viridis).
    'heat-0': '#440154',
    'heat-1': '#472D7B',
    'heat-2': '#3B528B',
    'heat-3': '#2C728E',
    'heat-4': '#21918C',
    'heat-5': '#28AE80',
    'heat-6': '#5EC962',
    'heat-7': '#ADDC30',
    'heat-8': '#FDE725',
}

DARK = {
    'bg-window': '#141619',
    'bg-sidebar': '#181A1E',
    'bg-surface': '#1E2125',
    'bg-raised': '#272A2F',
    'bg-subtle': '#24272C',
    'bg-hover': '#2A2E33',
    'bg-selected': '#17383C',
    'border': '#2E3238',
    'border-strong': '#454B53',
    'grid': '#2A2E33',
    'text-primary': '#E8EAED',
    'text-secondary': '#A2AAB4',
    'text-tertiary': '#959CA4',
    'text-disabled': '#5A6068',
    'accent': '#3BB5C1',
    'accent-hover': '#5BC6D0',
    'accent-subtle': '#12353A',
    'on-accent': '#0B1F22',
    'success': '#4AC26B',
    'success-bg': '#12301B',
    'warning': '#E3B341',
    'warning-bg': '#2E2610',
    'warning-border': '#4A3C14',
    'danger': '#F47067',
    'danger-bg': '#3D1A1C',
    'replicate': '#7C848E',
    'replicate-off': '#6F7781',
    'replicate-1': '#4893BB',
    'replicate-2': '#F93C4A',
    'replicate-3': '#668F43',
    'replicate-4': '#A95CF9',
    'replicate-5': '#F9A750',
    'replicate-6': '#57B69C',
    'replicate-7': '#A5A7DD',
    'replicate-8': '#BE7E9C',
    'replicate-9': '#A07E48',
    'replicate-10': '#DF927F',
    'replicate-11': '#C0BB79',
    'replicate-12': '#7BE364',
    'traffic': '#3A3E44',
    'shadow': '#000000',
    'series-1': '#6FA8E8',
    'series-2': '#DB86BE',
    'species-dye': '#A893F0',
    'species-guest': '#EE9550',
    'species-host': '#9AA3AD',
    'species-step2': '#BAC35A',
    'heat-0': '#440154',
    'heat-1': '#472D7B',
    'heat-2': '#3B528B',
    'heat-3': '#2C728E',
    'heat-4': '#21918C',
    'heat-5': '#28AE80',
    'heat-6': '#5EC962',
    'heat-7': '#ADDC30',
    'heat-8': '#FDE725',
}

# ── Type: four sizes on any screen — 28 metric, 20 title, 13 body, 12 small.
TYPE = {
    #  role:          (px, weight, tabular figures)
    'metric': (28, QFont.Weight.DemiBold, True),
    'title': (20, QFont.Weight.DemiBold, False),
    'title-number': (20, QFont.Weight.DemiBold, True),
    'body': (13, QFont.Weight.Normal, False),
    'body-strong': (13, QFont.Weight.DemiBold, False),
    'number': (13, QFont.Weight.Normal, True),
    'number-strong': (13, QFont.Weight.DemiBold, True),
    'label': (12, QFont.Weight.Medium, False),
    'small': (12, QFont.Weight.Normal, False),
    'small-number': (12, QFont.Weight.Normal, True),
    'overline': (12, QFont.Weight.DemiBold, False),
}

# ── Plot text: the text of every plot and of the head of its saved figure, in the three sizes
# Plot appearance offers. Each step is 2 px up, about one ratio apart; the weight is the same at
# every step, so a step changes the size and nothing else. Tick labels are Normal with tabular
# figures, axis titles Medium.
PLOT_TEXT = {
    #  step:      (tick px, title px)
    'standard': (16, 18),
    'large': (18, 20),
    'larger': (20, 22),
}
PLOT_TEXT_WEIGHT = {'tick': QFont.Weight.Normal, 'title': QFont.Weight.Medium}


def space(n: int) -> int:
    """Step *n* of the spacing scale, in px."""
    return SPACE[n]


def family() -> str:
    """The platform's UI font family (SF Pro on macOS, Segoe UI on Windows)."""
    return QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont).family()


def font(role: str) -> QFont:
    """The QFont of type role *role*; numbers use tabular figures so columns align."""
    px, weight, tabular = TYPE[role]
    f = QFont(family())
    f.setPixelSize(px)
    f.setWeight(weight)
    if tabular:
        f.setFeature(QFont.Tag('tnum'), 1)
    if role == 'metric':
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, -0.4)
    return f


def plot_font(step: str, part: str) -> QFont:
    """The QFont of the plot text at *step* of :data:`PLOT_TEXT`; *part* is ``tick`` (tabular figures) or ``title``."""
    f = QFont(family())
    f.setPixelSize(PLOT_TEXT[step][0 if part == 'tick' else 1])
    f.setWeight(PLOT_TEXT_WEIGHT[part])
    if part == 'tick':
        f.setFeature(QFont.Tag('tnum'), 1)
    return f


class Theme:
    """One resolved colour map (light or dark) with the helpers the widgets draw with."""

    def __init__(self, dark: bool = False):
        self.set_dark(dark)

    def set_dark(self, dark: bool) -> None:
        """Resolve the dark map (*dark*) or the light one; a widget holding this theme paints in it from then on."""
        self.dark = dark
        self.c = DARK if dark else LIGHT

    def __getitem__(self, key: str) -> str:
        return self.c[key]

    def q(self, key: str, alpha: float = 1.0) -> QColor:
        """Token *key* as a QColor, at opacity *alpha*."""
        col = QColor(self.c[key])
        col.setAlphaF(alpha)
        return col

    def palette(self) -> QPalette:
        """The QPalette that native-drawn controls (Fusion) read their colours from.

        Every role of every group is a token, so nothing Qt draws takes a colour of the
        platform's. Disabled text is ``text-disabled`` on the sunken ``bg-subtle`` a disabled
        field shows; an inactive window reads as an active one.
        """
        r = QPalette.ColorRole
        roles = {
            r.Window: 'bg-window',
            r.WindowText: 'text-primary',
            r.Base: 'bg-surface',
            r.AlternateBase: 'bg-subtle',
            r.Text: 'text-primary',
            r.PlaceholderText: 'text-tertiary',
            r.Button: 'bg-surface',
            r.ButtonText: 'text-primary',
            r.BrightText: 'on-accent',
            r.Highlight: 'accent',
            r.HighlightedText: 'on-accent',
            r.Accent: 'accent',
            r.ToolTipBase: 'bg-raised',
            r.ToolTipText: 'text-primary',
            r.Link: 'accent',
            r.LinkVisited: 'accent',
            r.Light: 'bg-surface',
            r.Midlight: 'bg-subtle',
            r.Mid: 'border-strong',
            r.Dark: 'border-strong',
            r.Shadow: 'shadow',
        }
        disabled = {
            **roles,
            r.WindowText: 'text-disabled',
            r.Text: 'text-disabled',
            r.ButtonText: 'text-disabled',
            r.PlaceholderText: 'text-disabled',
            r.Base: 'bg-subtle',
            r.Button: 'bg-subtle',
            r.Highlight: 'border-strong',
        }
        p = QPalette()
        g = QPalette.ColorGroup
        for group, keys in ((g.Active, roles), (g.Inactive, roles), (g.Disabled, disabled)):
            for role, key in keys.items():
                p.setColor(group, role, self.q(key))
        return p

    def render(self, template: str) -> str:
        """Fill a stylesheet template.

        ``{{ token }}`` becomes the colour, ``{{ opacity(token, 0.4) }}`` the colour at that
        opacity, ``{{ space(n) }}`` and ``{{ radius(name) }}`` the length in px.
        """

        def sub(m: re.Match) -> str:
            expr = m.group(1).strip()
            if expr.startswith('opacity('):
                key, a = expr[len('opacity(') : -1].split(',')
                col = self.q(key.strip(), float(a))
                return f'rgba({col.red()},{col.green()},{col.blue()},{col.alpha()})'
            if expr.startswith('space('):
                return f'{SPACE[int(expr[len("space(") : -1])]}px'
            if expr.startswith('radius('):
                return f'{RADIUS[expr[len("radius(") : -1].strip()]}px'
            return self.c[expr]

        return re.sub(r'\{\{(.+?)\}\}', sub, template)
