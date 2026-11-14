"""The Settings window: what belongs to the app rather than to one session (DESIGN.md §8).

One short page in three groups. **General**: the appearance (System / Light / Dark),
whether the app looks for a newer release when it starts, the version with *Check now*.
**New sessions**: the concentration unit a new session shows and takes entries in, and
the plot appearance it starts from, with a way back to the built-in one. **Analysis**:
the processor cores a sensitivity analysis runs on. Every change is stored in
:mod:`gui.preferences` as it is made, so the window has no OK or Cancel.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QPainter
from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from _version import __version__
from core.pipeline.sensitivity import default_worker_count
from gui import preferences
from gui.design import components as C
from gui.design.appearance import MODES, appearance, theme
from gui.design.tokens import SIZE, space
from gui.plot_appearance import BUILT_IN

#: The appearance choices, in the order the segmented control shows them.
MODE_LABELS = {'system': 'System', 'light': 'Light', 'dark': 'Dark'}


def plot_appearance_note() -> tuple[str, bool]:
    """What the plot appearance row says new sessions start from, and whether the built-in one can be restored."""
    try:
        stored = preferences.plot_appearance_default()
    except ValueError:
        return 'The stored appearance cannot be read; new sessions start from the built-in appearance.', True
    if stored == BUILT_IN:
        return 'Built-in appearance.', False
    return 'Stored with Use for new sessions.', True


def worker_label(count: int) -> str:
    """How the processor-core menu names *count*: ``Automatic (15)`` for 0, else the number."""
    return f'Automatic ({default_worker_count()})' if count == 0 else str(count)


def _note(text: str) -> QWidget:
    return C.wrapped(text, 'small', 'secondary')


def _row(label: str, control: QWidget, text: QWidget | str = '', detail: str = '') -> QWidget:
    """One setting: its name (a short note under it) on the left, the control on the right, and
    *detail*, a longer note, under both."""
    left = QVBoxLayout()
    left.setSpacing(space(1))
    left.addWidget(C.label(label))
    if text:
        left.addWidget(_note(text) if isinstance(text, str) else text)
    line = QHBoxLayout()
    line.setSpacing(space(6))
    line.addLayout(left, 1)
    line.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
    pad = 4 if text or detail else 3
    lay = C.vbox(line, spacing=0, margins=(4, pad, 4, pad))
    if detail:
        lay.addSpacing(space(2))
        lay.addWidget(_note(detail))
    w = QWidget()
    w.setLayout(lay)
    return w


class SettingsWindow(QWidget):
    """The Settings window; *check_now* is the app's *Check for updates…* action, which *Check now* triggers."""

    def __init__(self, check_now: QAction, parent: QWidget | None = None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle('Settings')
        self.check_now_action = check_now
        self.setFixedWidth(SIZE['settings-window'])
        self.setLayout(C.vbox(spacing=0))
        self._body: QWidget | None = None
        self._build()
        check_now.changed.connect(self._show_check_now)
        # The controls on a dark card are drawn in colours lifted for it, read once, so a
        # change of theme draws the page again.
        appearance().changed.connect(self._build)

    def _build(self) -> None:
        t = theme()
        ct = C.on_card(t)
        width = SIZE['settings-control']

        self.mode = C.Segmented(ct, list(MODE_LABELS.values()), MODES.index(appearance().mode), width=width)
        self.mode.setAccessibleName('Appearance')
        self.mode.changed.connect(self._choose_mode)
        self.updates = C.Toggle(ct, preferences.check_for_updates())
        self.updates.setAccessibleName('Check for updates when the app starts')
        self.updates.toggled.connect(lambda on: preferences.set_bool(preferences.CHECK_FOR_UPDATES_KEY, on))
        self.check_now = C.OutlineButton(ct, 'Check now')
        self.check_now.clicked.connect(self.check_now_action.trigger)
        general = C.SettingsCard(
            t,
            [
                _row(
                    'Appearance',
                    self.mode,
                    'System follows your computer’s light or dark setting. '
                    'Exported figures always use a white background.',
                ),
                _row(
                    'Check for updates when the app starts',
                    self.updates,
                    'Looks for a newer release on GitHub. Nothing is downloaded without asking.',
                ),
                _row(f'Version {__version__}', self.check_now),
            ],
        )

        units = list(preferences.UNITS)
        self.unit = C.Segmented(ct, units, units.index(preferences.concentration_unit()), width=width)
        self.unit.setAccessibleName('Concentration unit of new sessions')
        self.unit.changed.connect(lambda i: preferences.set_concentration_unit(units[i]))
        self.use_built_in = C.OutlineButton(ct, 'Use built-in appearance')
        self.use_built_in.setAccessibleName('Start new sessions from the built-in plot appearance')
        self.use_built_in.clicked.connect(self._use_built_in)
        self.appearance_note = _note('')
        new_sessions = C.SettingsCard(
            t,
            [
                _row(
                    'Concentrations shown and entered in',
                    self.unit,
                    detail='A new session’s plot axis (its Display unit) and its condition and uncertainty '
                    'fields start in this unit. It does not change how data files are read.',
                ),
                _row('Plot appearance', self.use_built_in, self.appearance_note),
            ],
        )

        self.worker_counts = preferences.worker_choices()
        stored = preferences.get_int(preferences.WORKER_COUNT_KEY, 0)
        self.cores = C.Dropdown(ct, worker_label(stored), width, options=[worker_label(n) for n in self.worker_counts])
        self.cores.setAccessibleName('Processor cores')
        self.cores.chosen.connect(self._choose_cores)
        analysis = C.SettingsCard(
            t,
            [
                _row(
                    'Processor cores',
                    self.cores,
                    detail='A sensitivity analysis re-fits your data many times, and more cores finish it '
                    'sooner. Automatic leaves one free so the window stays responsive; 1 runs one fit at a '
                    'time. The result is the same either way.',
                ),
            ],
        )

        body = QWidget()
        body.setLayout(
            C.vbox(
                C.settings_group('General', general),
                6,
                C.settings_group('New sessions', new_sessions),
                6,
                C.settings_group('Analysis', analysis),
                spacing=0,
                margins=(6, 5, 6, 6),
            )
        )
        if self._body is not None:
            C.drop(self._body)
        self.layout().addWidget(body)
        body.show()  # a child added to a window already on screen is shown by hand
        self._body = body
        self._show_check_now()
        self._show_plot_appearance()
        lay = self.layout()
        lay.activate()
        self.setFixedHeight(lay.heightForWidth(self.width()) if lay.hasHeightForWidth() else lay.sizeHint().height())

    # ------------------------------------------------------------------
    # Editing
    # ------------------------------------------------------------------

    def _choose_mode(self, index: int) -> None:
        mode = MODES[index]
        preferences.set_appearance_mode(mode)
        appearance().set_mode(mode)

    def _use_built_in(self) -> None:
        preferences.reset_plot_appearance_default()
        self._show_plot_appearance()

    def _choose_cores(self, index: int) -> None:
        count = self.worker_counts[index]
        preferences.set_int(preferences.WORKER_COUNT_KEY, count)
        self.cores.set_choice(worker_label(count))

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _show_check_now(self) -> None:
        self.check_now.setEnabled(self.check_now_action.isEnabled())
        self.check_now.update()

    def _show_plot_appearance(self) -> None:
        text, can_reset = plot_appearance_note()
        self.appearance_note.setText(text)
        self.use_built_in.setEnabled(can_reset)
        self.use_built_in.update()

    def showEvent(self, event) -> None:
        # The stored appearance changes from a session's Plot appearance view while the window is closed.
        self._show_plot_appearance()
        super().showEvent(event)

    def paintEvent(self, _) -> None:
        t = theme()
        p = QPainter(self)
        p.fillRect(self.rect(), t.q('bg-raised' if t.dark else 'bg-window'))
        p.end()
