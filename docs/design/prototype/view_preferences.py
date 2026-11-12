"""Settings window: the few things that belong to the app rather than to one session.

Opened from the app menu (Settings…, ⌘,) as a small window of its own, shown here over
Fit results, which goes inactive behind it. One short page in three groups, every row
something a user would actually change:

- General: appearance (System / Light / Dark; exported figures stay on white whatever
  it is), checking for updates when the app starts, the installed version with a check
  on demand.
- New sessions: the concentration unit a new session shows and takes entries in (its
  plot axis, the Display unit of Measurements, and its condition and uncertainty
  fields; the Imported unit that reads a data file is set per session), and the plot
  appearance it starts from. Binding constants are entered in M⁻¹ only, so they have no
  row. Sessions already open keep their own.
- Analysis: processor cores for the many refits of a sensitivity analysis.

The plot appearance row is a read-out with one command. A style is saved for new
sessions from the session it belongs to, with Use for new sessions in that session's
Plot appearance view, so the command sits next to the style it copies. What is saved is
the look alone (markers, lines, colours, palette, text sizes, Ka scale); axis titles, the
axis unit and what each plot shows stay with each session. Use built-in style is
disabled while new sessions already start from the built-in style, and the note then
reads "Built-in style.".

A single page rather than tabs: seven rows fit on one screen, and a tab row would hide
two thirds of them for no gain. Changes apply as they are made, as in any macOS settings
window, so there is no OK or Cancel.
"""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from _version import __version__
from core.pipeline.sensitivity import default_worker_count
from gui.design import components as C
from gui.design.tokens import RADIUS, Theme, space

from . import view_fit

WIN_W = 640
WIN_RADIUS = RADIUS['popover']
TITLE_H = 44
CONTROL_W = 216  # one right-hand column: every segmented control and popup shares its two edges
# Room around the window for its shadow, deeper below where the light falls.
PAD_X, PAD_TOP, PAD_BOTTOM = 32, 24, 40
SAVED_FROM = 'GDA_titrations'  # the session whose plot appearance new sessions start from


# ── Rows and groups ────────────────────────────────────────────────────────────────


def note(text: str) -> QWidget:
    lbl = C.label(text, 'small', 'secondary')
    lbl.setWordWrap(True)
    return lbl


def row(label: str, control: QWidget | None, text: str = '', detail: str = '') -> QWidget:
    """One setting: its name (and a short note under it) on the left, the control on the
    right; ``detail`` is a longer note under both, across the row."""
    w = QWidget()
    left = QVBoxLayout()
    left.setSpacing(space(1))
    left.addWidget(C.label(label))
    if text:
        left.addWidget(note(text))
    line = QHBoxLayout()
    line.setSpacing(space(6))
    line.addLayout(left, 1)
    if control is not None:
        line.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
    pad = 4 if text or detail else 3
    lay = C.vbox(line, spacing=0, margins=(4, pad, 4, pad))
    if detail:
        lay.addSpacing(space(2))
        lay.addWidget(note(detail))
    w.setLayout(lay)
    w.setMinimumHeight(44)
    return w


def group(title: str, card: C.SettingsCard, footnote: str = '') -> QWidget:
    w = QWidget()
    lay = C.vbox(C.hbox(C.label(title, 'body-strong'), margins=(4, 0, 4, 0)), 3, card, spacing=0)
    if footnote:
        lay.addSpacing(space(3))
        lay.addLayout(C.hbox(C.label(footnote, 'small', 'tertiary'), margins=(4, 0, 4, 0)))
    w.setLayout(lay)
    return w


def segmented(t: Theme, options: list[str], current: int) -> C.Segmented:
    return C.Segmented(t, options, current, width=CONTROL_W)


def body(t: Theme) -> QWidget:
    ct = C.on_card(t)
    general = C.SettingsCard(
        t,
        [
            row(
                'Appearance',
                segmented(ct, ['System', 'Light', 'Dark'], 0),
                'System follows your computer’s light or dark setting. Exported figures always use a white background.',
            ),
            row(
                'Check for updates when the app starts',
                C.Toggle(ct, True),
                'Looks for a newer release on GitHub. Nothing is downloaded without asking.',
            ),
            row(f'Version {__version__}', C.OutlineButton(ct, 'Check now')),
        ],
    )
    new_sessions = C.SettingsCard(
        t,
        [
            row(
                'Concentrations shown and entered in',
                segmented(ct, ['nM', 'µM', 'mM', 'M'], 1),
                detail='A new session’s plot axis (its Display unit) and its condition and uncertainty fields '
                'start in this unit. It does not change how data files are read.',
            ),
            row(
                'Plot appearance',
                C.OutlineButton(ct, 'Use built-in style'),
                f'Saved from {SAVED_FROM}.',
                detail='New sessions take its markers, lines, colours and text sizes; axis titles and what each '
                'plot shows stay with each session. Save another from a session’s Plot appearance view.',
            ),
        ],
    )
    cores = C.Field(ct, f'Automatic ({default_worker_count()})', CONTROL_W, kind='choice')
    analysis = C.SettingsCard(
        t,
        [
            row(
                'Processor cores',
                cores,
                detail='A sensitivity analysis re-fits your data many times, and more cores finish it sooner. '
                'Automatic leaves one free so the window stays responsive; 1 runs one fit at a time. '
                'The result is the same either way.',
            ),
        ],
    )
    w = QWidget()
    w.setLayout(
        C.vbox(
            group('General', general),
            6,
            group('New sessions', new_sessions, 'Sessions already open keep their own units and plot appearance.'),
            6,
            group('Analysis', analysis),
            spacing=0,
            margins=(6, 1, 6, 6),
        )
    )
    return w


def title_bar(t: Theme) -> QWidget:
    w = QWidget()
    w.setFixedHeight(TITLE_H)
    lights = C.TrafficLights(t, active=(0, 1))  # a fixed-size window cannot zoom
    balance = QWidget()  # mirrors the lights so the title sits on the window's centre line
    balance.setFixedWidth(lights.width())
    w.setLayout(
        C.hbox(lights, None, C.label('Settings', 'body-strong'), None, balance, spacing=0, margins=(5, 0, 5, 0))
    )
    return w


class SettingsWindow(QWidget):
    """A separate, fixed-size window: its own chrome, surface and soft shadow."""

    def __init__(self, t: Theme, parent: QWidget):
        super().__init__(parent)
        self.t = t
        lay = C.vbox(title_bar(t), body(t), spacing=0)
        lay.setContentsMargins(PAD_X, PAD_TOP, PAD_X, PAD_BOTTOM)
        self.setLayout(lay)
        w = WIN_W + 2 * PAD_X
        self.setFixedSize(w, lay.totalHeightForWidth(w) if lay.hasHeightForWidth() else lay.sizeHint().height())

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        win = QRectF(PAD_X, PAD_TOP, WIN_W, self.height() - PAD_TOP - PAD_BOTTOM)
        # Soft window shadow: stacked translucent rounded rects, offset down; a tight
        # contact shadow under the edge keeps the outline crisp on any background.
        steps = 24
        for i in range(steps, 0, -1):
            sp = QPainterPath()
            sp.addRoundedRect(win.adjusted(-i, -i + 10, i, i + 10), WIN_RADIUS + i, WIN_RADIUS + i)
            a = (0.04 if t.dark else 0.016) * (steps + 1 - i) / steps
            p.fillPath(sp, QColor(0, 0, 0, int(255 * a)))
        cp = QPainterPath()
        cp.addRoundedRect(win.adjusted(-1, 0, 1, 2), WIN_RADIUS + 1, WIN_RADIUS + 1)
        p.fillPath(cp, QColor(0, 0, 0, 90 if t.dark else 22))
        path = QPainterPath()
        path.addRoundedRect(win, WIN_RADIUS, WIN_RADIUS)
        # Dark: the window is raised above the canvas behind it, so it reads as in front
        # of it rather than as a hole in it; light keeps the grey window under white rows.
        p.fillPath(path, t.q('bg-raised' if t.dark else 'bg-window'))
        p.setPen(QPen(t.q('border-strong' if t.dark else 'border'), 1))
        p.drawPath(QPainterPath(path))
        p.end()


def build(t: Theme) -> dict:
    spec = view_fit.build(t)

    def overlay(root: QWidget):
        lights = root.findChildren(C.TrafficLights)[0]
        dim = C.TrafficLights(t, active=())  # the window behind is not the key window
        dim.setParent(root)
        dim.move(lights.mapTo(root, lights.rect().topLeft()))
        dim.show()
        win = SettingsWindow(t, root)
        win.move((root.width() - win.width()) // 2, 72)
        win.show()
        win.raise_()

    spec['overlay'] = overlay
    return spec
