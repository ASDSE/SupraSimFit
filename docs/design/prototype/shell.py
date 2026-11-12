"""Window shell shared by every view: sidebar (session switcher + navigation), toolbar,
canvas | inspector split, and the quiet status bar along the bottom of the window.

A view module exposes ``build(t) -> dict`` with keys:
    nav        name of the selected navigation item
    title      toolbar title
    badge      (text, tone) or None
    canvas     QWidget for the main area
    inspector  QWidget or None (right-hand panel)
    status     optional (left_text, left_tone) for the status bar
    sidebar    optional kwargs for ``sidebar`` (session_name, session_detail, others_busy, open_)
    nav_status optional {nav item: status} merged over NAV_STATUS (the session on screen)
    model_line optional list of parts replacing MODEL_LINE in the status bar
    overlay    optional callable(root) -> None, run after layout to float popovers
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QSplitter, QWidget

from gui.design import components as C
from gui.design import icons
from gui.design.tokens import SIZE, Theme, space

from .common import keys

WIDTH, HEIGHT = 1440, 900

# Sessions open in the window. The first is the one on screen.
SESSIONS = [
    {'name': 'IDA_system', 'detail': 'IDA · 8 replicates', 'state': 'warning'},
    {'name': 'GDA_titrations', 'detail': 'GDA · 3 replicates', 'state': 'stale'},
    {'name': 'DBA_HtoD_0411', 'detail': 'DBA host → dye · 4 replicates', 'state': 'running', 'progress': 0.62},
]

NAV_STATUS = {
    'Measurements': 'done',
    'Binding model': 'done',
    'Input uncertainty': 'done',
    'Fit results': 'warning',
    'Ka confidence': 'done',
    'Sensitivity': '',
    'Plot appearance': '',
}

MODEL_LINE = ['Indicator displacement', '1 binding constant', 'Profile likelihood, 95 %', 'Weighted by noise law']


def sidebar(
    t: Theme,
    selected: str,
    session_name: str = 'IDA_system',
    session_detail: str = 'IDA · 8 replicates',
    others_busy: int = 1,
    open_: bool = False,
    nav_status: dict | None = None,
    file_name: str = 'IDA_system.txt',
    file_detail: str = 'IDA · 8 replicates × 12 points',
) -> QWidget:
    status = {**NAV_STATUS, **(nav_status or {})}
    w = QWidget()
    w.setObjectName('Sidebar')
    w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    w.setFixedWidth(SIZE['sidebar'])
    lay = C.vbox(spacing=0, margins=(4, 0, 4, 4))

    chrome = QWidget()
    chrome.setFixedHeight(SIZE['toolbar'])
    side_toggle = C.tool_button(t, None, 'panel-left')
    chrome.setLayout(C.hbox(C.TrafficLights(t), None, side_toggle, margins=(2, 0, 0, 0)))
    lay.addWidget(chrome)
    switcher = C.SessionSwitcher(t, session_name, session_detail, count=len(SESSIONS), busy=others_busy, open_=open_)
    switcher.setObjectName('SessionSwitcher')
    lay.addWidget(switcher)
    lay.addSpacing(space(6))

    groups = [
        ('Experiment', [('Measurements', 'table'), ('Binding model', 'flask'), ('Input uncertainty', 'sliders')]),
        ('Analysis', [('Fit results', 'fit'), ('Ka confidence', 'profile'), ('Sensitivity', 'bars')]),
        ('Presentation', [('Plot appearance', 'palette')]),
    ]
    for gi, (title, items) in enumerate(groups):
        if gi:
            lay.addSpacing(space(5))
        lay.addLayout(C.hbox(C.label(title, 'overline', 'tertiary'), margins=(3, 0, 0, 0)))
        lay.addSpacing(space(2))
        for text, ic in items:
            lay.addWidget(C.NavItem(t, text, ic, status[text], selected=(text == selected)))
            lay.addSpacing(space(1))
    lay.addStretch(1)
    # The data behind the session on screen: its file(s) and their shape.
    lay.addWidget(C.hairline())
    card = QWidget()
    card.setToolTip('Data in this session. Click to open Measurements.')
    ic = QLabel()
    ic.setPixmap(icons.icon('file', t.q('text-secondary'), 16).pixmap(16, 16))
    text = C.vbox(C.label(file_name, 'body-strong'), C.label(file_detail, 'small', 'secondary'), spacing=1)
    row = C.hbox(ic, 3, text, None, spacing=0, margins=(3, 4, 3, 2))
    row.setAlignment(ic, Qt.AlignmentFlag.AlignTop)
    card.setLayout(row)
    lay.addWidget(card)
    w.setLayout(lay)
    return w


def toolbar(t: Theme, title: str, badge: tuple[str, str] | None, inspector: bool = True) -> QWidget:
    w = QWidget()
    w.setObjectName('Toolbar')
    w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    w.setFixedHeight(SIZE['toolbar'])
    div = C.hairline(vertical=True)
    div.setFixedHeight(20)
    run = C.primary_button(t, 'Run fit', 'play')
    # One width for every view ('Run fit' / 'Run analysis'), so the toolbar never shifts.
    run.setFixedWidth(C.primary_button(t, 'Run analysis', 'play').width())
    # One entry point for data, three outcomes; the canvas's "Add files…" and the
    # switcher's "Load data into a new session…" are the same commands.
    load = C.tool_button(t, 'Load data', 'open', menu=True)
    load.setObjectName('LoadData')
    load.setToolTip(
        f'Add files to this session ({keys("Ctrl+O")}), replace its data, '
        f'or load into a new session ({keys("Ctrl+Shift+O")})'
    )
    items = [C.label(title, 'title'), 3]
    if badge:
        items.append(C.badge(*badge))
    items += [
        None,
        load,
        C.tool_button(t, 'Export', 'export', menu=True),
        2,
        div,
        2,
        C.tool_button(t, None, 'help'),
        C.tool_button(t, None, 'panel-right', checked=inspector),
        2,
        run,
    ]
    w.setLayout(C.hbox(*items, spacing=2, margins=(6, 0, 5, 0)))
    return w


def status_bar(t: Theme, left: tuple[str, str] | None = None, model_line: list[str] | None = None) -> QWidget:
    """Quiet 28-px status bar: what the app is doing on the left, what the fit is on the right."""
    w = QWidget()
    w.setObjectName('StatusBar')
    w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    w.setFixedHeight(SIZE['statusbar'])
    text, tone = left or ('Ready  ·  DBA_HtoD_0411 is fitting in the background (62 %)', 'accent')
    items: list = [C.StatusDot(t, tone), 2, C.label(text, 'small', 'secondary'), None]
    for i, part in enumerate(model_line or MODEL_LINE):
        if i:
            items += [3, C.label('·', 'small', 'tertiary'), 3]
        items.append(C.label(part, 'small', 'tertiary'))
    w.setLayout(C.hbox(*items, spacing=0, margins=(5, 0, 5, 0)))
    return w


def window(t: Theme, spec: dict) -> QWidget:
    root = QWidget()
    root.setObjectName('Root')
    content = QWidget()
    if spec.get('inspector') is not None:
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setHandleWidth(1)
        split.setChildrenCollapsible(False)
        split.addWidget(spec['canvas'])
        insp = spec['inspector']
        insp.setMinimumWidth(SIZE['inspector-min'])
        split.addWidget(insp)
        split.setStretchFactor(0, 1)
        split.setSizes([WIDTH - SIZE['sidebar'] - 1 - SIZE['inspector'], SIZE['inspector']])
        main = split
    else:
        main = spec['canvas']
    content.setLayout(
        C.vbox(
            toolbar(t, spec['title'], spec.get('badge'), spec.get('inspector') is not None),
            C.hairline(),
            main,
            spacing=0,
        )
    )
    top = QWidget()
    top.setLayout(
        C.hbox(
            sidebar(t, spec['nav'], nav_status=spec.get('nav_status'), **spec.get('sidebar', {})),
            C.hairline(vertical=True),
            content,
            spacing=0,
        )
    )
    root.setLayout(C.vbox(top, C.hairline(), status_bar(t, spec.get('status'), spec.get('model_line')), spacing=0))
    return root
