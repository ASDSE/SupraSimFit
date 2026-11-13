"""Input uncertainty view (setup): the stated error model as one form on the canvas,
what it did to the last fit in the inspector.

The form takes the canvas rather than the inspector because every input row needs five
aligned controls (kind, amount, unit, and what the amount spans): at 320 px they would
wrap onto three lines per input, and the comparison down the column, which input is
stated loosest, would be lost. What the three kinds mean is one legend line under the
table. The inspector holds what a form cannot show: the effect of these statements on
the reported interval and on the tests of the last fit.

Every number is the demo's (demo.json): the stated σ of each input, the entered
conditions, the titrant series, and the input-aware and conditional intervals. The
"±2σ spans" column is arithmetic on the entered value and the stated σ.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QScrollArea, QWidget

from gui.design import components as C
from gui.design import icons
from gui.design.tokens import Theme, space

from .common import DEMO, THIN, sci, split_stretches, sub

# ── Data ───────────────────────────────────────────────────────────────────────────

COND = {k: dict(v) for k, v in DEMO['assay_conditions'].items()}
# Binding constants are entered in M⁻¹, as everywhere in the app.
COND['Ka_dye']['display'] = {'value': COND['Ka_dye']['display']['value'] * 1e6, 'unit': 'M⁻¹'}
SIGMA = {u['key']: u['sigma_pct'] for u in DEMO['input_uncertainties']}
X = DEMO['x_uM']


def _num(v: float) -> str:
    return sci(v) if abs(v) >= 1e4 else f'{v:.3g}'


def SUP_DIGITS(e: int) -> str:
    return str(e).translate(str.maketrans('0123456789-', '⁰¹²³⁴⁵⁶⁷⁸⁹⁻'))


def _span(key: str) -> str:
    """Entered value ± 2σ, in the entered value's own unit."""
    d = COND[key]['display']
    half = 2 * SIGMA[key] / 100
    lo, hi = d['value'] * (1 - half), d['value'] * (1 + half)
    if hi >= 1e4:  # one shared power of ten: 1.34 – 2.02 × 10⁷ M⁻¹
        e = math.floor(math.log10(hi))
        return f'{lo / 10**e:.2f} – {hi / 10**e:.2f}{THIN}×{THIN}10{SUP_DIGITS(e)} {d["unit"]}'
    return f'{_num(lo)} – {_num(hi)} {d["unit"]}'


INPUTS = [
    {
        'name': f'K{sub("a,dye")}',
        'entered': f'Entered{THIN} {_num(COND["Ka_dye"]["display"]["value"])} {COND["Ka_dye"]["display"]["unit"]}',
        'units': ['%', COND['Ka_dye']['display']['unit']],
        'sigma': SIGMA['Ka_dye'],
        'span': _span('Ka_dye'),
    },
    {
        'name': f'[Host]{sub("0")}',
        'entered': f'Entered{THIN} {COND["h0"]["display"]["value"]:g} {COND["h0"]["display"]["unit"]}',
        'units': ['%', COND['h0']['display']['unit']],
        'sigma': SIGMA['h0'],
        'span': _span('h0'),
    },
    {
        'name': f'[Dye]{sub("0")}',
        'entered': f'Entered{THIN} {COND["d0"]["display"]["value"]:g} {COND["d0"]["display"]["unit"]}',
        'units': ['%', COND['d0']['display']['unit']],
        'sigma': SIGMA['d0'],
        'span': _span('d0'),
    },
    {
        'name': 'Guest (titrant)',
        'entered': f'Whole series, {X[0]:g} – {X[-1]:g} µM',
        'units': ['%', 'µM'],
        'unit_disabled': True,
        'sigma': SIGMA['__titrant__'],
        'span': f'every point ±{2 * SIGMA["__titrant__"]:g} %',
    },
]

# Column grid (px) of the inputs table; the last column takes the rest.
COL_NAME, COL_KIND, COL_AMOUNT, COL_UNIT, COL_BAR = 176, 168, 96, 104, 104
GUTTER = space(5)
ROW_H = 60


# ── Canvas: the form ───────────────────────────────────────────────────────────────


def inputs_table(t: Theme) -> QWidget:
    w = QWidget()
    g = QGridLayout()
    g.setContentsMargins(0, 0, 0, 0)
    g.setHorizontalSpacing(GUTTER)
    g.setVerticalSpacing(0)
    for c, width in enumerate((COL_NAME, COL_KIND, COL_AMOUNT, COL_UNIT, COL_BAR)):
        g.setColumnMinimumWidth(c, width)
    g.setColumnStretch(5, 1)

    heads = ['Input', 'Kind', 'Amount', 'Stated in', None, '±2σ spans']
    for c, h in enumerate(heads):
        if h is None:
            cell = C.AxisScale(t, COL_BAR)
            cell.setToolTip('Offset from the entered value, in percent.')
        else:
            cell = C.label(h, 'label', 'tertiary')
        cell.setFixedHeight(28)
        g.addWidget(cell, 0, c, Qt.AlignmentFlag.AlignVCenter)
    g.addWidget(C.hairline(), 1, 0, 1, 6)

    for i, inp in enumerate(INPUTS):
        r = 2 + 2 * i
        name = QWidget()
        name.setFixedHeight(ROW_H)
        nl = C.label(inp['name'], 'body-strong', rich=True)
        el = C.label(inp['entered'], 'small-number', 'secondary')
        name.setLayout(C.vbox(None, nl, el, None, spacing=1))
        g.addWidget(name, r, 0)

        kind = C.Segmented(t, ['Fixed', 'σ', 'Range'], 1, COL_KIND, dividers=True)
        kind.setToolTip(
            'σ is one standard deviation of a normal distribution. A range is drawn evenly between '
            'its two ends and may be lopsided. Fixed takes the set value as exact.'
        )
        g.addWidget(kind, r, 1, Qt.AlignmentFlag.AlignVCenter)
        g.addWidget(C.Field(t, f'{inp["sigma"]:.1f}', COL_AMOUNT, prefix='σ'), r, 2, Qt.AlignmentFlag.AlignVCenter)
        unit = C.Segmented(
            t, inp['units'], 0, COL_UNIT, disabled=(1,) if inp.get('unit_disabled') else (), dividers=True
        )
        if inp.get('unit_disabled'):
            unit.setToolTip('The titrant is a series with no single value, so its uncertainty is a percentage.')
        g.addWidget(unit, r, 3, Qt.AlignmentFlag.AlignVCenter)
        g.addWidget(C.SpreadBar(t, 2 * inp['sigma'], COL_BAR), r, 4, Qt.AlignmentFlag.AlignVCenter)
        g.addWidget(C.label(inp['span'], 'number', 'secondary'), r, 5, Qt.AlignmentFlag.AlignVCenter)
        if i < len(INPUTS) - 1:
            g.addWidget(C.hairline(), r + 1, 0, 1, 6)
    w.setLayout(g)
    return w


def wrap(text: str, role: str = 'body', tone: str | None = 'secondary', rich: bool = False) -> QLabel:
    lbl = C.label(text, role, tone, rich=rich)
    lbl.setWordWrap(True)
    return lbl


def shared_sources(t: Theme) -> QWidget:
    w = QWidget()
    add = C.tool_button(t, 'Add shared source', 'plus')
    add.setToolTip('State an error several inputs have in common.')
    text = C.label(
        'Errors several inputs have in common: one stock, one balance, one pipette. '
        'Each moves the inputs you tick alike.',
        'body',
        'secondary',
    )
    empty = C.label('None stated, so each input above carries only its own error.', 'body', 'tertiary')
    w.setLayout(C.vbox(text, 3, C.hbox(empty, None, add, spacing=3), spacing=0))
    return w


def _spacer(width: int) -> QWidget:
    w = QWidget()
    w.setFixedSize(width, 1)
    return w


# The additions controls span the table's Kind-to-Stated-in columns, so their left and
# right edges continue the input grid above.
FORM_W = COL_KIND + COL_AMOUNT + COL_UNIT + 2 * GUTTER


def _form_row(caption: str, control: QWidget) -> QHBoxLayout:
    cap = C.label(caption, 'label', 'tertiary')
    cap.setFixedWidth(COL_NAME)
    return C.hbox(cap, control, None, spacing=5)


def additions(t: Theme) -> QWidget:
    w = QWidget()
    mode = C.Segmented(t, ['None', 'One cuvette', 'Separate samples'], 0, FORM_W, dividers=True)
    mode.setToolTip(
        'How the titrant was added: sequential additions into one cuvette, or separately '
        'prepared samples, each point pipetted on its own.'
    )
    text = C.label(
        'The titrant entry above moves the whole series by one factor; the scatter of single additions goes here.',
        'body',
        'secondary',
    )
    rep_seg = C.Segmented(t, ['Separate titrations', 'Repeated reads'], 0, FORM_W, disabled=(0, 1), dividers=True)
    rep_seg.setToolTip(
        'Separate titrations each have their own addition errors; repeated reads of one titration share them. '
        'Choose how the titrant was added first.'
    )
    hint = C.label('Choose how the titrant was added to state σ of each addition.', 'small', 'tertiary')
    w.setLayout(
        C.vbox(
            text,
            5,
            _form_row('How the titrant was added', mode),
            3,
            _form_row('Replicates are', rep_seg),
            2,
            C.hbox(_spacer(COL_NAME), hint, None, spacing=5),
            spacing=0,
        )
    )
    return w


def kinds_legend(t: Theme) -> QWidget:
    """What the three kinds mean, read once under the table that uses them."""
    w = QWidget()
    items = []
    for term, text in (
        ('σ', 'one standard deviation of a normal distribution'),
        ('Range', 'drawn evenly between its two ends, may be lopsided'),
        ('Fixed', 'taken as exact'),
    ):
        items += [C.label(term, 'label', 'secondary'), 2, C.label(text, 'small', 'tertiary'), 6]
    w.setLayout(C.hbox(*items[:-1], None, spacing=0))
    return w


def canvas_section(title: str, content: QWidget, summary: str = '', first: bool = False) -> QWidget:
    """A canvas section: the same plain title on the 24-px edge as every other canvas."""
    w = QWidget()
    lay = C.vbox(spacing=0)
    if not first:
        lay.addSpacing(space(6))
        lay.addWidget(C.hairline())
        lay.addSpacing(space(5))
    head = [C.label(title, 'body-strong')]
    if summary:
        head += [3, C.label(summary, 'small', 'tertiary')]
    lay.addLayout(C.hbox(*head, None, spacing=0))
    lay.addSpacing(space(3))
    lay.addWidget(content)
    w.setLayout(lay)
    return w


def canvas(t: Theme) -> QWidget:
    w = QWidget()
    w.setObjectName('Canvas')
    w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    intro = C.label(
        'How far each entered input may be off. A fixed input is taken as exact; the fit lets the others<br>'
        'move within what you state, and the Sensitivity analysis draws them from it.',
        'body',
        'secondary',
        rich=True,
    )
    link = C.link_button('About input uncertainty')
    head = C.hbox(intro, None, C.vbox(link, None), spacing=5)
    table = QWidget()
    table.setLayout(C.vbox(inputs_table(t), 3, kinds_legend(t), spacing=0))
    lay = C.vbox(
        head,
        6,
        canvas_section('Each input', table, '±2σ holds about 95 of every 100 draws', first=True),
        canvas_section('Shared error sources', shared_sources(t)),
        canvas_section('Random error of each addition', additions(t)),
        None,
        spacing=0,
        margins=(6, 5, 6, 4),
    )
    w.setLayout(lay)
    return w


# ── Inspector: what the statements did ────────────────────────────────────────────


def inspector(t: Theme) -> QWidget:
    w = QWidget()
    w.setObjectName('Inspector')
    w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    head = QWidget()
    head.setFixedHeight(44)
    head.setLayout(
        C.hbox(C.label('Effect on the fit', 'body-strong'), None, C.tool_button(t, None, 'x'), margins=(5, 0, 3, 0))
    )

    # Interval of Ka guest: as stated vs inputs as entered
    h, ci = DEMO['headline'], DEMO['conditional']
    cond = DEMO['profile']['profiles']['Ka_guest']['conditional']
    rows = [
        {
            'label': 'Input-aware',
            'color': 'accent',
            'segments': [(h['low_per_M'], h['high_per_M'])],
            'est': h['estimate_per_M'],
            'text': f'{h["estimate_MM"] / 100:.2f}  [{h["low_MM"] / 100:.2f}, {h["high_MM"] / 100:.2f}]',
        },
        {
            'label': 'Inputs as entered',
            'color': 'text-tertiary',
            'segments': split_stretches(cond),
            'est': cond['best_ka_per_M'],
            'text': f'{ci["estimate_MM"] / 100:.2f}  [{ci["low_MM"] / 100:.2f}, {ci["high_MM"] / 100:.2f}]',
        },
    ]
    chart = C.CompactIntervals(t, rows, 0.95e8, 5.3e8, [1e8, 1.5e8, 2e8, 3e8, 4e8, 5e8], 1e8)
    unit_line = C.label(f'K{sub("a")} guest, 95 % interval, ×{THIN}10⁸ M⁻¹', 'small', 'tertiary', rich=True)
    cap = wrap(
        'Letting the inputs move within what you stated explains a misfit the entered values could not, '
        'so the interval is narrower than with the inputs as entered.',
        'small',
        'tertiary',
    )
    iv = QWidget()
    iv.setLayout(C.vbox(unit_line, 2, chart, 2, cap, spacing=0))

    # Inputs against what was stated
    d = DEMO['diagnostics']
    diag = QWidget()
    dl = C.vbox(spacing=0)
    for ic, tone, text, pv in (
        ('check-circle', 'success', 'Curve fits with inputs moved', f'p = {d["misfit"]["p_value"]:.2f}'),
        ('alert-circle', 'warning', 'Misfit at inputs as entered', f'p = {d["conditional_misfit"]["p_value"]:.3f}'),
        ('alert-circle', 'warning', 'Inputs conflict', 'p < 0.001'),
    ):
        icl = QLabel()
        icl.setPixmap(icons.pixmap(ic, t[tone], 16))
        row = QWidget()
        row.setFixedHeight(28)
        row.setLayout(C.hbox(icl, C.label(text), None, C.label(pv, 'small-number', 'secondary'), spacing=3))
        dl.addWidget(row)
    dl.addSpacing(space(2))
    dl.addWidget(
        wrap(
            'Together, the inputs moved further from their entered values than you stated. Several inputs '
            'move the curve almost alike, so this is not a verdict on any one of them.',
            'small',
            'tertiary',
        )
    )
    dl.addSpacing(space(3))
    dl.addLayout(C.hbox(C.link_button('Review in Ka confidence  →'), None))
    diag.setLayout(dl)

    body = QWidget()
    body.setObjectName('InspectorBody')
    body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    body.setLayout(
        C.vbox(
            C.section(t, 'Interval of the last fit', iv, first=True),
            C.section(t, 'Inputs against what you stated', diag),
            C.section(t, 'Also used by', None, open_=False, trailing='Sensitivity'),
            None,
            spacing=0,
            margins=(5, 0, 5, 4),
        )
    )
    scroll = QScrollArea()
    scroll.setWidget(body)
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    w.setLayout(C.vbox(head, scroll, spacing=0))
    return w


def build(t: Theme) -> dict:
    return {
        'nav': 'Input uncertainty',
        'title': 'Input uncertainty',
        'badge': (f'{len(INPUTS)} inputs vary', 'neutral'),
        'canvas': canvas(t),
        'inspector': inspector(t),
    }
