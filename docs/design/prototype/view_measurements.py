"""Measurements view (setup): the files of one experiment, their raw titration, and the
settings that decide which points and replicates reach the fit.

A session is one experiment. Files selected together, or added later, are stacked as
replicates of it on one shared concentration grid (``core.io.load_measurements_multi``:
replicate labels from the file stems, shown as A, B, C … in the order loaded). Another
experiment is another session.

Data come in through one toolbar menu, *Load data*: *Add files to this session…* (also the
canvas's *Add files…*), *Replace data…*, and *Load data into a new session…* (also in the
session switcher and the Files note). ``view_measurements_load`` renders that menu open.

Every number comes from ``data/measurements.json``, written by
``data/make_measurements_data.py`` from the app's own loader and outlier filter.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QPainter, QPainterPath
from PyQt6.QtWidgets import QLabel, QScrollArea, QSizePolicy, QWidget

from gui.design import components as C
from gui.design import icons
from gui.design.plot_theme import apply_plot_theme, scatter
from gui.design.tokens import Theme, font, space

from .common import LETTERS, keys, load, molar

DATA = load('measurements.json')


FORMATS = {'TxtReader': 'Tab-separated text'}

X_M = np.array(DATA['x_M'])
X_UM = X_M * 1e6
SIG = np.array(DATA['signals'])
ACTIVE = DATA['active']
N_REP = DATA['n_replicas']
N_PTS = DATA['n_points']
LOG = DATA['log'][-1]
OFF = [LETTERS[i] for i, a in enumerate(ACTIVE) if not a]
X_NAME = 'Dye'  # ASSAY_REGISTRY[AssayType.GDA].x_label: a guest displacement titrates the dye
NEW_SESSION = 'Load data into a new session…'  # the session switcher's command
ON = [LETTERS[i] for i, a in enumerate(ACTIVE) if a]


def join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f'{", ".join(names[:-1])} and {names[-1]}'


class SourcesTable(QWidget):
    """The files of this experiment: one row each, with the replicate it became."""

    HEAD, ROW = 28, 40
    COLS = [('File', 0), ('Format', 0.42), ('Replicate', 0.66), ('Points', 0.86)]

    def __init__(self, t: Theme, files: list[dict]):
        super().__init__()
        self.t, self.files = t, files
        self.setFixedHeight(self.HEAD + len(files) * self.ROW)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W = self.width() - 32  # room for the remove button
        xs = {name: frac * W for name, frac in self.COLS}
        p.setFont(font('label'))
        p.setPen(t.q('text-tertiary'))
        for name, _ in self.COLS:
            p.drawText(QRectF(xs[name], 0, 200, self.HEAD), Qt.AlignmentFlag.AlignVCenter, name)
        p.fillRect(QRectF(0, self.HEAD - 1, self.width(), 1), t.q('border'))
        for i, f in enumerate(self.files):
            y = self.HEAD + i * self.ROW
            on = ACTIVE[i]
            cy = y + self.ROW / 2
            icons.paint(p, 'file-text', t.q('text-secondary'), 0, cy - 8, 16)
            p.setFont(font('body'))
            p.setPen(t.q('text-primary'))
            p.drawText(QRectF(16 + space(3), y, xs['Format'] - 32, self.ROW), Qt.AlignmentFlag.AlignVCenter, f['name'])
            p.setPen(t.q('text-secondary'))
            p.drawText(QRectF(xs['Format'], y, 200, self.ROW), Qt.AlignmentFlag.AlignVCenter, FORMATS[f['reader']])
            # replicate letter: a 20-px tile, tinted while used
            tile = QRectF(xs['Replicate'], cy - 10, 20, 20)
            tp = QPainterPath()
            tp.addRoundedRect(tile, 5, 5)
            p.fillPath(tp, t.q('accent-subtle' if on else 'bg-subtle'))
            p.setFont(font('number-strong'))
            p.setPen(t.q('accent' if on else 'text-tertiary'))
            p.drawText(tile, Qt.AlignmentFlag.AlignCenter, LETTERS[i])
            if not on:
                p.setFont(font('small'))
                p.setPen(t.q('text-secondary'))
                p.drawText(
                    QRectF(tile.right() + space(3), y, 120, self.ROW), Qt.AlignmentFlag.AlignVCenter, 'Off · outlier'
                )
            p.setFont(font('number'))
            p.setPen(t.q('text-primary'))
            p.drawText(QRectF(xs['Points'], y, 60, self.ROW), Qt.AlignmentFlag.AlignVCenter, str(f['points']))
            icons.paint(p, 'x', t.q('text-tertiary'), self.width() - 22, cy - 8, 16)
            if i < len(self.files) - 1:
                p.fillRect(QRectF(0, y + self.ROW - 1, self.width(), 1), t.q('grid' if not t.dark else 'border'))
        p.end()


# ── Canvas ─────────────────────────────────────────────────────────────────────────


def titration_plot(t: Theme) -> pg.PlotWidget:
    pw = pg.PlotWidget()
    pw.setFrameShape(pg.QtWidgets.QFrame.Shape.NoFrame)
    pi = apply_plot_theme(pw, t, f'{X_NAME} (µM)', 'Signal (10³ a.u.)', [0, 2, 4, 6, 8, 10], text='standard')
    s = 1e-3
    for i, on in enumerate(ACTIVE):
        y = SIG[i] * s
        if on:
            pi.addItem(scatter(t, X_UM, y, 'replicate', 0.8 if t.dark else 0.55, 6))
        else:
            pi.addItem(scatter(t, X_UM, y, 'text-secondary' if t.dark else 'replicate-off', 0.8, 7, symbol='x'))
    pi.setXRange(-14, 640, padding=0)
    pi.setYRange(-0.35, 11.2, padding=0)
    pi.getAxis('bottom').setTicks([[(v, f'{v:g}') for v in range(0, 700, 100)]])
    return pw


def canvas(t: Theme) -> QWidget:
    w = QWidget()
    w.setObjectName('Canvas')
    w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

    files = DATA['files']
    add = C.tool_button(t, 'Add files…', 'plus')
    add.setToolTip(f'Add files to this session as further replicates ({keys("Ctrl+O")})')
    files_head = C.hbox(
        C.label('Files', 'body-strong'),
        3,
        C.label(
            f'{len(files)} files · {N_REP} replicates · one grid of {N_PTS} points, '
            f'{X_UM.min():.0f} – {X_UM.max():.0f} µM',
            'small',
            'tertiary',
        ),
        None,
        add,
        spacing=0,
    )
    info = QLabel()
    info.setPixmap(icons.pixmap('info', t['text-tertiary'], 16))
    info.setFixedSize(16, 16)
    note = C.label(
        'Added files become replicates on this concentration grid. Another experiment needs its own session.',
        'small',
        'secondary',
    )
    note.setMinimumWidth(1)  # keep the canvas from widening the split
    note_row = C.hbox(info, note, 3, C.link_button(NEW_SESSION), None, spacing=3)

    legend = C.LegendRow(t, [('dots', f'Replicates ({len(ON)})'), ('cross', f'{join(OFF)} switched off')])
    plot_head = C.hbox(
        C.label('Titration', 'body-strong'),
        3,
        C.label('raw signal, as loaded', 'small', 'tertiary'),
        None,
        legend,
        6,
        C.label('Display unit', 'small', 'secondary'),
        2,
        C.Field(t, 'µM', 72, kind='choice'),
        3,
        C.tool_button(t, None, 'image'),
        spacing=0,
    )
    lay = C.vbox(
        files_head,
        2,
        SourcesTable(t, files),
        3,
        note_row,
        6,
        C.hairline(),
        5,
        plot_head,
        2,
        spacing=0,
        margins=(6, 5, 6, 4),
    )
    lay.addWidget(titration_plot(t), 1)
    w.setLayout(lay)
    return w


# ── Inspector ──────────────────────────────────────────────────────────────────────


def field(t: Theme, name: str, value: str) -> QWidget:
    w = QWidget()
    w.setLayout(C.vbox(C.label(name, 'small', 'secondary'), C.Field(t, value), spacing=2))
    return w


def inspector(t: Theme) -> QWidget:
    w = QWidget()
    w.setObjectName('Inspector')
    w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

    head = QWidget()
    head.setFixedHeight(44)
    head.setLayout(
        C.hbox(C.label('Measurement settings', 'body-strong'), None, C.tool_button(t, None, 'x'), margins=(5, 0, 3, 0))
    )

    # Concentrations
    unit_row = C.hbox(
        C.label('Concentrations', 'body', 'secondary'),
        None,
        C.Segmented(t, ['nM', 'µM', 'mM', 'M'], current=3, width=168),
        spacing=3,
    )
    unit_note = C.label(
        'The numbers below are read in this unit. To draw the plot in another unit, use its Display unit.',
        'small',
        'tertiary',
    )
    unit_note.setWordWrap(True)
    vec = C.hbox(C.link_button('Load vector…'), C.link_button('Save vector…'), None, spacing=5)
    conc = QWidget()
    conc.setLayout(
        C.vbox(
            C.label('Units in the file', 'label', 'tertiary'),
            unit_row,
            unit_note,
            5,
            C.ConcentrationGrid(t, [molar(v) for v in DATA['x_M']], f'{X_NAME} (M)'),
            2,
            vec,
            spacing=2,
        )
    )

    # Replicates
    chips = []
    for i, (rid, on) in enumerate(zip(DATA['replica_ids'], ACTIVE, strict=True)):
        chip = C.ReplicateChip(t, LETTERS[i], on, by_filter=rid in LOG.get('dropped', []))
        if chip.by_filter:
            chip.setToolTip(f'Switched off by outlier removal (z = {DATA["max_z"][i]:.1f})')
        chips.append(chip)
    chip_row = C.hbox(*chips, None, C.link_button('Reset all'), spacing=2)
    rep_note = C.label(
        f'{join(OFF)} was switched off by outlier removal (z). Click a replicate to switch it on or off.',
        'small',
        'tertiary',
    )
    rep_note.setWordWrap(True)
    reps = QWidget()
    reps.setLayout(C.vbox(chip_row, rep_note, spacing=3))

    # Outlier removal
    i_off = DATA['replica_ids'].index(LOG['dropped'][0])
    z = DATA['max_z'][i_off]
    at = X_UM[DATA['argmax_z'][i_off]]
    fields = C.hbox(
        field(t, 'Z-score threshold', f'{LOG["threshold"]:.1f}'), field(t, 'Min replicates', '3'), spacing=4
    )
    ic = QLabel()
    ic.setPixmap(icons.pixmap('info', t['text-secondary'], 16))
    ic.setFixedSize(16, 16)
    res_txt = C.label(
        f'Last applied: switched off {join(OFF)}. Its point at {at:.0f} µM lies far from the other '
        f'replicates (z = {z:.1f}, above {LOG["threshold"]:.1f}).',
        'small',
        'secondary',
    )
    res_txt.setWordWrap(True)
    res = C.hbox(C.vbox(ic, None, margins=(0, 1, 0, 0)), res_txt, spacing=3)
    btns = C.hbox(C.OutlineButton(t, 'Apply'), C.tool_button(t, 'Reset', 'rotate'), None, spacing=2)
    outl = QWidget()
    outl.setLayout(C.vbox(fields, 2, res, 2, btns, spacing=3))

    body = QWidget()
    body.setObjectName('InspectorBody')
    body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    body.setLayout(
        C.vbox(
            C.section(t, 'Concentrations', conc, first=True, trailing=f'{N_PTS} points'),
            C.section(t, 'Replicates', reps, trailing=f'{len(ON)} of {N_REP} used'),
            C.section(t, 'Outlier removal', outl, trailing='Z-score'),
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
        'nav': 'Measurements',
        'title': 'Measurements',
        'badge': (f'{len(DATA["files"])} files', 'neutral'),
        'canvas': canvas(t),
        'inspector': inspector(t),
        # Outlier removal just changed the replicates, so every analysis is out of date
        # while another session fits in the background.
        'status': ('Ready  ·  DBA_HtoD_0411 is fitting in the background (62 %)', 'accent'),
        'nav_status': {'Fit results': 'stale', 'Ka confidence': 'stale', 'Sensitivity': 'stale'},
        'model_line': ['Guest displacement', '1 binding constant', 'Profile likelihood, 95 %'],
        'sidebar': {
            'session_name': 'GDA_titrations',
            'session_detail': f'GDA · {len(DATA["files"])} replicates',
            'others_busy': 1,
            'file_name': f'{DATA["files"][0]["name"]} + {len(DATA["files"]) - 1} more',
            'file_detail': f'GDA · {N_REP} replicates × {N_PTS} points',
        },
    }
