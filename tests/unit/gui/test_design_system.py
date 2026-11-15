"""The design system's own contracts: tokens, contrast, stylesheet, icons, references.

Each test guards a rule of ``docs/design/DESIGN.md``: both themes define every token,
text stays readable (WCAG AA) on every background it is drawn on, the stylesheet
template resolves completely, every icon is a valid SVG, no module of ``gui/`` carries a
colour, font-size or spacing literal, and every reference screen the document names
exists in both themes.
"""

from __future__ import annotations

import itertools
import math
import re
from pathlib import Path

import pytest
from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtSvg import QSvgRenderer

from gui.design import icons
from gui.design.stylesheet import stylesheet
from gui.design.tokens import DARK, LIGHT, SPACE, TYPE, Theme

ROOT = Path(__file__).resolve().parents[3]
DESIGN_DOC = ROOT / 'docs' / 'design' / 'DESIGN.md'
SCREENS = ROOT / 'docs' / 'design' / 'screens'

THEMES = {'light': LIGHT, 'dark': DARK}

# Every background text is drawn on; bg-raised is a surface of its own only in dark.
TEXT_BACKGROUNDS = ('bg-window', 'bg-sidebar', 'bg-surface', 'bg-raised', 'bg-subtle', 'bg-hover', 'bg-selected')
TEXT_TOKENS = ('text-primary', 'text-secondary', 'text-tertiary', 'accent')  # enabled text; text-disabled below
# Coloured text on its own tint: badges, callouts, the selected navigation item.
PAIRS = (
    ('on-accent', 'accent'),
    ('accent', 'accent-subtle'),
    ('accent', 'bg-selected'),
    ('text-primary', 'bg-selected'),
    ('success', 'success-bg'),
    ('warning', 'warning-bg'),
    ('danger', 'danger-bg'),
    ('text-secondary', 'bg-subtle'),
)
AA = 4.5


def _luminance(hex_colour: str) -> float:
    channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    """WCAG 2 contrast ratio of two ``#RRGGBB`` colours."""
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_contrast_reference_values():
    assert contrast('#000000', '#FFFFFF') == pytest.approx(21.0)
    assert contrast('#777777', '#FFFFFF') == pytest.approx(4.48, abs=0.01)


def test_both_themes_define_the_same_tokens_as_hex_colours():
    assert LIGHT.keys() == DARK.keys()
    for theme in THEMES.values():
        for key, value in theme.items():
            assert re.fullmatch(r'#[0-9A-F]{6}', value), f'{key} = {value!r} is not #RRGGBB'


@pytest.mark.parametrize('name', THEMES)
@pytest.mark.parametrize('text', TEXT_TOKENS)
def test_text_meets_aa_on_every_background(name, text):
    theme = THEMES[name]
    for bg in TEXT_BACKGROUNDS:
        ratio = contrast(theme[text], theme[bg])
        assert ratio >= AA, f'{name}: {text} on {bg} is {ratio:.2f} : 1, below {AA}'


@pytest.mark.parametrize('name', THEMES)
@pytest.mark.parametrize(('fg', 'bg'), PAIRS)
def test_coloured_text_meets_aa_on_its_tint(name, fg, bg):
    theme = THEMES[name]
    ratio = contrast(theme[fg], theme[bg])
    assert ratio >= AA, f'{name}: {fg} on {bg} is {ratio:.2f} : 1, below {AA}'


#: WCAG 2 non-text contrast: a mark that carries a value stands out from what it is drawn on by 3 : 1.
NON_TEXT = 3.0


@pytest.mark.parametrize('name', THEMES)
def test_the_series_colours_stand_out_from_the_plot_surface(name):
    """S₁ and S_T are told apart by hue and by mark (solid, outlined); each must first read on the plot."""
    theme = THEMES[name]
    for series in ('series-1', 'series-2'):
        ratio = contrast(theme[series], theme['bg-surface'])
        assert ratio >= NON_TEXT, f'{name}: {series} on bg-surface is {ratio:.2f} : 1, below {NON_TEXT}'
    assert theme['series-1'] != theme['series-2']


SPECIES = ('species-dye', 'species-guest', 'species-host', 'species-step2')


@pytest.mark.parametrize('name', THEMES)
def test_the_species_colours_read_on_the_plot_and_borrow_no_other_meaning(name):
    """Each species line stands out from the plot by 3 : 1, and none takes the colour of the reported
    result (``accent``), of the Sobol' series, or of another species."""
    theme = THEMES[name]
    for species in SPECIES:
        ratio = contrast(theme[species], theme['bg-surface'])
        assert ratio >= NON_TEXT, f'{name}: {species} on bg-surface is {ratio:.2f} : 1, below {NON_TEXT}'
    taken = [theme[k] for k in ('accent', 'series-1', 'series-2', *SPECIES)]
    assert len(set(taken)) == len(taken)


def _lab(hex_colour: str) -> tuple[float, float, float]:
    """CIELAB (D65) of a ``#RRGGBB`` colour."""
    channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
    xyz = (
        (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047,
        0.2126729 * r + 0.7151522 * g + 0.0721750 * b,
        (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883,
    )
    fx, fy, fz = (v ** (1 / 3) if v > (6 / 29) ** 3 else v / (3 * (6 / 29) ** 2) + 4 / 29 for v in xyz)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e2000(lab1: tuple[float, float, float], lab2: tuple[float, float, float]) -> float:
    """CIEDE2000 colour difference of two CIELAB colours (Sharma, Wu and Dalal 2005)."""
    (l1, a1, b1), (l2, a2, b2) = lab1, lab2
    c_bar = (math.hypot(a1, b1) + math.hypot(a2, b2)) / 2
    g = 0.5 * (1 - math.sqrt(c_bar**7 / (c_bar**7 + 25**7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if c1p else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if c2p else 0.0
    dh = 0.0 if not c1p * c2p else (h2p - h1p + 180) % 360 - 180
    d_l, d_c = l2 - l1, c2p - c1p
    d_h = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dh / 2))
    l_bar, cp_bar = (l1 + l2) / 2, (c1p + c2p) / 2
    if not c1p * c2p:
        h_bar = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        h_bar = (h1p + h2p) / 2
    else:
        h_bar = (h1p + h2p + 360) / 2 if h1p + h2p < 360 else (h1p + h2p - 360) / 2
    t = (
        1
        - 0.17 * math.cos(math.radians(h_bar - 30))
        + 0.24 * math.cos(math.radians(2 * h_bar))
        + 0.32 * math.cos(math.radians(3 * h_bar + 6))
        - 0.20 * math.cos(math.radians(4 * h_bar - 63))
    )
    s_l = 1 + 0.015 * (l_bar - 50) ** 2 / math.sqrt(20 + (l_bar - 50) ** 2)
    s_c, s_h = 1 + 0.045 * cp_bar, 1 + 0.015 * cp_bar * t
    r_t = (
        -2
        * math.sqrt(cp_bar**7 / (cp_bar**7 + 25**7))
        * math.sin(math.radians(60 * math.exp(-(((h_bar - 275) / 25) ** 2))))
    )
    return math.sqrt((d_l / s_l) ** 2 + (d_c / s_c) ** 2 + (d_h / s_h) ** 2 + r_t * (d_c / s_c) * (d_h / s_h))


@pytest.mark.parametrize(
    ('lab1', 'lab2', 'expected'),
    [  # pairs 1, 7, 17 and 25 of the published test data of Sharma, Wu and Dalal (2005)
        ((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
        ((50.0, 0.0, 0.0), (50.0, -1.0, 2.0), 2.3669),
        ((50.0, 2.5, 0.0), (73.0, 25.0, -18.0), 27.1492),
        ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ],
)
def test_delta_e2000_reference_values(lab1, lab2, expected):
    assert delta_e2000(lab1, lab2) == pytest.approx(expected, abs=1e-4)


def over(fg: str, bg: str, alpha: float) -> str:
    """*fg* at opacity *alpha* composited over *bg*, as the plot paints it (per channel, in sRGB)."""
    mix = [round(alpha * int(fg[i : i + 2], 16) + (1 - alpha) * int(bg[i : i + 2], 16)) for i in (1, 3, 5)]
    return '#' + ''.join(f'{c:02X}' for c in mix)


#: Two replicate colours, and a replicate colour and a mark it is drawn beside, differ by this CIEDE2000 at least.
DISTINCT = 15.0


@pytest.mark.parametrize('name', THEMES)
def test_each_replicate_colour_reads_on_the_plot_and_apart_from_every_other_mark(name):
    """DESIGN.md §2: each replicate's colour, at the opacity its points are drawn at, stands out from the plot
    by 3 : 1 and from every other replicate colour by ΔE₀₀ 15; so it does from the means (``text-primary``)
    and from every colour the fitted curve may take."""
    from gui.design.plot_theme import REPLICATE_ALPHA
    from gui.design.tokens import REPLICATE_COLOURS
    from gui.plot_appearance import FIT_COLOURS

    theme = THEMES[name]
    surface = theme['bg-surface']
    drawn = {f'replicate-{i}': over(theme[f'replicate-{i}'], surface, REPLICATE_ALPHA) for i in range(1, 13)}
    assert REPLICATE_COLOURS == 12 and f'replicate-{REPLICATE_COLOURS + 1}' not in theme
    for key, colour in drawn.items():
        ratio = contrast(colour, surface)
        assert ratio >= NON_TEXT, f'{name}: {key} at {REPLICATE_ALPHA} on bg-surface is {ratio:.2f} : 1'
    for (a, ca), (b, cb) in itertools.combinations(drawn.items(), 2):
        d = delta_e2000(_lab(ca), _lab(cb))
        assert d >= DISTINCT, f'{name}: {a} and {b} differ by ΔE₀₀ {d:.1f}, below {DISTINCT}'
    others = {'text-primary', *(token for _label, token in FIT_COLOURS.values())}
    for key, colour in drawn.items():
        for other in others:
            d = delta_e2000(_lab(colour), _lab(theme[other]))
            assert d >= DISTINCT, f'{name}: {key} and {other} differ by ΔE₀₀ {d:.1f}, below {DISTINCT}'


@pytest.mark.parametrize('name', THEMES)
def test_the_heat_scale_rises_in_lightness_from_low_to_high(name):
    """A perceptual scale reads as an order without its colour bar: each stop is lighter than the one below it."""
    from gui.design.tokens import HEAT_STOPS

    theme = THEMES[name]
    stops = [_luminance(theme[f'heat-{i}']) for i in range(HEAT_STOPS)]
    assert all(b > a for a, b in zip(stops, stops[1:])), f'{name}: the heat scale is not ordered by lightness'
    assert f'heat-{HEAT_STOPS}' not in theme


def test_scales_are_ordered_and_on_the_grid():
    steps = [SPACE[k] for k in sorted(SPACE)]
    assert steps == sorted(steps)
    assert all(v % 2 == 0 for v in steps)
    assert all(v % 4 == 0 for v in steps if v >= 4)
    assert {px for px, _, _ in TYPE.values()} == {28, 20, 13, 12}


#: The surfaces a disabled control is drawn on: the window, its panels and surfaces, and the sunken fill of a field.
DISABLED_GROUNDS = ('bg-window', 'bg-sidebar', 'bg-surface', 'bg-raised', 'bg-subtle')
#: Disabled text stands out from its ground by more than this, so it still reads as a word…
DISABLED_LEAST = 1.6
#: …and by no more than two thirds of the AA every enabled text keeps, so it is never taken for enabled text.
DISABLED_MOST = AA * 2 / 3


@pytest.mark.parametrize('name', THEMES)
def test_disabled_text_is_quiet_yet_readable_on_every_ground_a_disabled_control_stands_on(name):
    """DESIGN.md §2: ``text-disabled`` stands out from each ground by more than 1.6 : 1 and by at most 3 : 1, two
    thirds of the 4.5 : 1 of ``text-tertiary``, the quietest enabled text."""
    theme = THEMES[name]
    for ground in DISABLED_GROUNDS:
        ratio = contrast(theme['text-disabled'], theme[ground])
        assert DISABLED_LEAST < ratio <= DISABLED_MOST, f'{name}: text-disabled on {ground} is {ratio:.2f} : 1'


#: The palette's roles: every one Qt draws with.
ROLES = [r for r in QPalette.ColorRole if r not in (QPalette.ColorRole.NoRole, QPalette.ColorRole.NColorRoles)]
GROUPS = (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive, QPalette.ColorGroup.Disabled)


@pytest.mark.parametrize('dark', [False, True])
def test_every_palette_role_of_every_group_is_a_token_of_the_theme(qapp, dark):
    """What Qt draws itself takes no colour of the platform's (DESIGN.md §2, Themes): every role of the palette, in
    each group, is a colour of the theme, and disabled text is ``text-disabled``."""
    theme = Theme(dark)
    palette = theme.palette()
    tokens = {v.lower() for v in theme.c.values()}
    for group in GROUPS:
        for role in ROLES:
            colour = palette.color(group, role).name()
            assert colour in tokens, f'{group.name} {role.name} is {colour}, no colour of the theme'
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        assert palette.color(QPalette.ColorGroup.Disabled, role).name() == theme['text-disabled'].lower()
        assert palette.color(QPalette.ColorGroup.Active, role).name() == theme['text-primary'].lower()


def _controls(t: Theme) -> dict:
    """One of each control of :mod:`gui.design.components` that a view disables, with text or an icon to read."""
    from PyQt6.QtGui import QAction

    from gui.design import components as C

    rows = [QAction('Export several…')]
    rows[0].setEnabled(False)
    menu = C.PopoverMenu(t, None, rows)
    return {
        'button': C.Button(t, 'ghost', 'Overlay data', 'open'),
        'icon button': C.Button(t, 'icon', icon_name='image'),
        'outline button': C.OutlineButton(t, 'Use for new sessions'),
        'field': C.Field(t, '4.30', 96, suffix='µM'),
        'dropdown': C.Dropdown(t, ['Fixed', 'σ'], current=0, width=120),
        'segmented': C.Segmented(t, ['Fixed', 'σ', 'Range']),
        'checkbox': C.Checkbox(t, 'Fixed seed', checked=False),
        'menu row': menu,
    }


def _ink(widget) -> QColor:
    """The colour *widget* paints on its theme's surface that stands out most from the colour it paints most, at two
    device px per px."""
    from collections import Counter

    from PyQt6.QtGui import QImage
    from PyQt6.QtWidgets import QWidget

    image = QImage(widget.size() * 2, QImage.Format.Format_ARGB32)
    image.setDevicePixelRatio(2)
    image.fill(widget.t.q('bg-surface'))
    widget.render(image, flags=QWidget.RenderFlag.DrawChildren)
    pixels = [image.pixelColor(x, y) for x in range(image.width()) for y in range(image.height())]
    ground = Counter(p.name() for p in pixels).most_common(1)[0][0]
    return max(pixels, key=lambda p: contrast(p.name(), ground))


@pytest.mark.parametrize('dark', [False, True], ids=['light', 'dark'])
def test_every_disabled_control_draws_its_text_and_icon_in_text_disabled(qapp, dark):
    """A disabled control reads as one at a glance: its strongest mark is ``text-disabled``, where enabled it is a
    colour of enabled text."""
    t = Theme(dark)
    enabled_text = {t[k].lower() for k in ('text-primary', 'text-secondary', 'accent')}
    for name, control in _controls(t).items():
        control.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        control.show()
        qapp.processEvents()
        on = _ink(control)
        if name == 'menu row':
            control.actions_[0].setEnabled(True)
            on = _ink(control)
            control.actions_[0].setEnabled(False)
        else:
            control.setEnabled(False)
        off = _ink(control)
        assert _close(off, t['text-disabled']), f'{name}: disabled, it paints {off.name()}'
        assert any(_close(on, c) for c in enabled_text), f'{name}: enabled, it paints {on.name()}'
        control.close()


def _close(colour: QColor, token: str, tolerance: int = 6) -> bool:
    want = QColor(token)
    return all(abs(a - b) <= tolerance for a, b in zip(colour.getRgb()[:3], want.getRgb()[:3], strict=True))


@pytest.mark.parametrize('dark', [False, True], ids=['light', 'dark'])
def test_a_disabled_slider_and_toggle_take_no_accent(qapp, dark):
    """The accent of a slider's fill and a toggle's track says *on*; disabled, both are drawn in ``text-disabled``."""
    from gui.design import components as C

    t = Theme(dark)
    for control in (C.Slider(t, 0.6), C.Toggle(t, on=True)):
        control.resize(max(control.width(), 120), control.height())
        control.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        control.show()
        control.setEnabled(False)
        qapp.processEvents()
        image = control.grab().toImage()
        colours = {image.pixelColor(x, y).name() for x in range(image.width()) for y in range(image.height())}
        assert t['accent'].lower() not in colours and t['text-disabled'].lower() in colours, type(control).__name__
        control.close()


@pytest.mark.parametrize('dark', [False, True])
def test_stylesheet_resolves_every_placeholder(dark):
    sheet = stylesheet(Theme(dark))
    assert '{{' not in sheet and '}}' not in sheet


def test_every_icon_is_valid_svg(qapp):
    for name in icons.PATHS:
        assert QSvgRenderer(QByteArray(icons.svg(name, '#000000'))).isValid(), name


# Colour, font-size and spacing values written in place of a token. A zero margin or
# spacing is no value of the scale, a transparent fill no colour, and an ``rgba(...)`` built
# from a token's channels no literal, so none of them is caught.
_LITERAL = re.compile(
    r'#[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{3}\b'
    r"|rgba?\(\s*\d|QColor\(\s*['\"\d]|Qt\.GlobalColor\.(?!transparent\b)"
    r'|font-size:\s*\d|setPointSize\(|setPixelSize\('
    r'|setSpacing\(\s*[1-9]|setContentsMargins\((?:\s*0\s*,)*\s*[1-9]|setMargin\(\s*[1-9]'
)

#: The modules that hold literals by right, each with the literals it may hold.
ALLOWED = {
    # The tokens themselves: every colour, size and type value is defined here.
    'gui/design/tokens.py': None,
    # The macOS window-button colours (close, minimise, zoom), drawn where a frameless window
    # paints its own title bar: the platform's colours, the same in both themes, not the design's.
    'gui/design/components.py': {'#FF5F57', '#FEBC2E', '#28C840'},
}


def literals(source: str) -> list[str]:
    """The literals in *source* that a module of ``gui/`` must not contain."""
    return [m.group(0) for m in _LITERAL.finditer(source)]


def test_the_literal_guard_catches_each_kind_of_offender():
    offending = (
        "pen = QColor('#1C2024')\n"
        "w.setStyleSheet('color: rgba(0,0,0,0.5); font-size: 12px')\n"
        'lay.setContentsMargins(8, 8, 8, 8); lay.setSpacing(6)\n'
    )
    assert len(literals(offending)) == 6
    assert literals('lay.setContentsMargins(0, 0, 8, 0); image.fill(Qt.GlobalColor.white)') == [
        'setContentsMargins(0, 0, 8',
        'Qt.GlobalColor.',
    ]
    clean = (
        "lay.setSpacing(space(3)); c = t.q('accent'); lay.setContentsMargins(0, 0, 0, 0)\n"
        "pm.fill(Qt.GlobalColor.transparent); f'rgba({c.red()},{c.green()},{c.blue()},{c.alpha()})'\n"
    )
    assert literals(clean) == []


def test_no_module_of_the_interface_carries_a_literal():
    """Every module of ``gui/`` takes its colours, font sizes and spacings from the tokens."""
    offenders = []
    for path in sorted((ROOT / 'gui').rglob('*.py')):
        name = path.relative_to(ROOT).as_posix()
        allowed = ALLOWED.get(name, set())
        if allowed is None:
            continue
        hits = [hit for hit in literals(path.read_text(encoding='utf-8')) if hit not in allowed]
        offenders += [f'{name}: {hit}' for hit in hits]
    assert not offenders, 'literals outside the tokens:\n' + '\n'.join(offenders)


def test_the_reference_screens_are_the_ones_the_design_names_and_the_render_command_draws():
    """DESIGN.md, ``docs.design.render.SCREENS`` and ``docs/design/screens/`` list the same screens, in both themes."""
    from docs.design.render import SCREENS as RENDERED

    named = set(re.findall(r'`?([a-z_]+)_(?:\*|light|dark)\.jpg`?', DESIGN_DOC.read_text(encoding='utf-8')))
    assert named == set(RENDERED)
    on_disk = {p.name for p in SCREENS.glob('*.jpg')}
    assert on_disk == {f'{v}_{m}.jpg' for v in RENDERED for m in ('light', 'dark')}
