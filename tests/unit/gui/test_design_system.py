"""The design system's own contracts: tokens, contrast, stylesheet, icons, references.

Each test guards a rule of ``docs/design/DESIGN.md``: both themes define every token,
text stays readable (WCAG AA) on every background it is drawn on, the stylesheet
template resolves completely, every icon is a valid SVG, a view built on ``gui.design``
carries no colour or font-size literal, and every reference screen the document names
exists in both themes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from PyQt6.QtCore import QByteArray
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
TEXT_TOKENS = ('text-primary', 'text-secondary', 'text-tertiary', 'accent')
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


@pytest.mark.parametrize('dark', [False, True])
def test_stylesheet_resolves_every_placeholder(dark):
    sheet = stylesheet(Theme(dark))
    assert '{{' not in sheet and '}}' not in sheet


def test_every_icon_is_valid_svg(qapp):
    for name in icons.PATHS:
        assert QSvgRenderer(QByteArray(icons.svg(name, '#000000'))).isValid(), name


# Colour, font-size and spacing values written in place of a token, and the plot palette outside the tokens.
_LITERAL = re.compile(
    r'#[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{3}\b'
    r"|rgba?\(|QColor\(\s*['\"\d]|Qt\.GlobalColor"
    r'|font-size:\s*\d|setPointSize\(|setPixelSize\('
    r'|setSpacing\(\s*\d|setContentsMargins\(\s*\d'
    r'|gui\.plotting\.colors|plotting import colors'
)
_USES_DESIGN = re.compile(r'^\s*(from gui\.design\b|import gui\.design\b)', re.MULTILINE)


def literals(source: str) -> list[str]:
    """The literals in *source* that a module built on ``gui.design`` must not contain."""
    return [m.group(0) for m in _LITERAL.finditer(source)]


def test_the_literal_guard_catches_each_kind_of_offender():
    offending = (
        "pen = QColor('#1C2024')\n"
        "w.setStyleSheet('color: rgba(0,0,0,0.5); font-size: 12px')\n"
        'lay.setContentsMargins(8, 8, 8, 8); lay.setSpacing(6)\n'
        'from gui.plotting.colors import INK\n'
    )
    assert len(literals(offending)) == 7
    assert literals("lay.setSpacing(space(3)); c = t.q('accent')") == []


def test_views_on_the_design_system_carry_no_literals():
    """A module that imports ``gui.design`` takes every colour, size and spacing from its tokens."""
    offenders = []
    for path in sorted((ROOT / 'gui').rglob('*.py')):
        if (ROOT / 'gui' / 'design') in path.parents:
            continue
        text = path.read_text(encoding='utf-8')
        if _USES_DESIGN.search(text):
            offenders += [f'{path.relative_to(ROOT)}: {hit}' for hit in literals(text)]
    assert not offenders, 'literals outside the tokens:\n' + '\n'.join(offenders)


def test_every_reference_screen_named_in_the_design_exists_in_both_themes():
    named = set(re.findall(r'`?([a-z_]+)_(?:\*|light|dark)\.jpg`?', DESIGN_DOC.read_text(encoding='utf-8')))
    assert named, 'DESIGN.md names no reference screen'
    missing = [
        f'{v}_{m}.jpg' for v in sorted(named) for m in ('light', 'dark') if not (SCREENS / f'{v}_{m}.jpg').is_file()
    ]
    assert not missing, f'missing reference screens: {missing}'
