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

# ── Radius: controls, surfaces (cards), popovers and floating windows, pills (badges, toggles).
RADIUS = {'control': 6, 'surface': 8, 'popover': 10, 'pill': 999}

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
    'axis-left': 56,
    'axis-bottom': 44,
    # The column grid of the Input uncertainty inputs table; the span column takes the rest.
    'input-name': 168,
    'input-kind': 156,
    'stated-in': 88,
    'spread-bar': 96,
    'input-row': 60,
    # The headline column of Fit results: a binding constant's name, value and interval.
    'headline': 264,
    # The height of the sample histogram of Sensitivity, its labels and axis included.
    'histogram': 104,
    # The least height of an analysis plot on screen (a Ka profile, the joint region), below which its canvas scrolls.
    'plot-min': 320,
    # The longest line of help or warning text under a control, for a comfortable reading measure.
    'measure': 640,
    # The point sizes and stroke widths Plot appearance offers for the titration plot.
    'marker-small': 4,
    'marker-medium': 6,
    'marker-large': 9,
    'stroke-thin': 1,
    'stroke-medium': 2,
    'stroke-thick': 3,
}

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
    'traffic': '#D9DCE0',
    # The two series of the Sobol' chart: S₁ and S_T.
    'series-1': '#2C6FB0',
    'series-2': '#B04F8E',
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
    'traffic': '#3A3E44',
    'series-1': '#6FA8E8',
    'series-2': '#DB86BE',
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
    'number-large': (20, QFont.Weight.Normal, True),
    'body': (13, QFont.Weight.Normal, False),
    'body-strong': (13, QFont.Weight.DemiBold, False),
    'number': (13, QFont.Weight.Normal, True),
    'number-strong': (13, QFont.Weight.DemiBold, True),
    'label': (12, QFont.Weight.Medium, False),
    'small': (12, QFont.Weight.Normal, False),
    'small-number': (12, QFont.Weight.Normal, True),
    'overline': (12, QFont.Weight.DemiBold, False),
}


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
        """The QPalette that native-drawn controls (Fusion) read their colours from."""
        p = QPalette()
        r = QPalette.ColorRole
        for role, key in (
            (r.Window, 'bg-window'),
            (r.WindowText, 'text-primary'),
            (r.Base, 'bg-surface'),
            (r.AlternateBase, 'bg-subtle'),
            (r.Text, 'text-primary'),
            (r.PlaceholderText, 'text-tertiary'),
            (r.Button, 'bg-surface'),
            (r.ButtonText, 'text-primary'),
            (r.Highlight, 'accent'),
            (r.HighlightedText, 'on-accent'),
            (r.ToolTipBase, 'bg-raised'),
            (r.ToolTipText, 'text-primary'),
            (r.Link, 'accent'),
            (r.Mid, 'border-strong'),
            (r.Dark, 'border-strong'),
            (r.Light, 'bg-surface'),
        ):
            p.setColor(role, self.q(key))
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
