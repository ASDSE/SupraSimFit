"""FittingMainWindow — the window of every open session: sidebar, toolbar, the session on screen and the status bar."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QLocale, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QIcon, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QWidget,
)

from _version import __version__
from gui import preferences
from gui.design import components as C
from gui.design.appearance import appearance, theme
from gui.design.tokens import SIZE, Theme, space
from gui.dialogs.plot_guide_dialog import show_plot_guide
from gui.errors import install_exception_hook, log_dir
from gui.fitting_session import NAVIGATION, VIEWS, FittingSession
from gui.preferences import APP_NAME, ORG_NAME
from gui.results import RUN_FIT_KEY
from gui.update_check import UpdateCheckWorker, is_newer
from gui.update_dialog import UpdateAvailableDialog
from gui.workers import retire


def _action(parent: QObject, text: str, icon: str = '', shortcut=None, slot=None) -> QAction:
    """A command: its text, design icon (a name in :mod:`gui.design.icons`), shortcut and slot."""
    action = QAction(text, parent)
    if icon:
        action.setProperty('design_icon', icon)
    if isinstance(shortcut, QKeySequence.StandardKey):
        action.setShortcuts(shortcut)  # every binding the platform has for it
    elif shortcut is not None:
        action.setShortcut(QKeySequence(shortcut))
    if slot is not None:
        action.triggered.connect(slot)
    return action


class _Sidebar(QWidget):
    """The sidebar: the sidebar toggle, the session switcher, the views and the file card."""

    view_chosen = pyqtSignal(str)

    def __init__(self, t: Theme):
        super().__init__()
        self.setObjectName('Sidebar')
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setFixedWidth(SIZE['sidebar'])
        self.toggle = C.tool_button(t, None, 'panel-left')
        self.toggle.setToolTip('Hide the sidebar')
        self.toggle.setAccessibleName('Hide the sidebar')
        chrome = C.TitleBarArea()
        chrome.setFixedHeight(SIZE['toolbar'])
        chrome.setLayout(C.hbox(None, self.toggle, margins=(1, 0, 0, 0)))
        self.switcher = C.SessionSwitcher(t, '', '')
        self.switcher.setToolTip('Open sessions')
        self.nav: dict[str, C.NavItem] = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        lay = C.vbox(chrome, self.switcher, 6, spacing=0, margins=(4, 0, 4, 4))
        for gi, (title, items) in enumerate(NAVIGATION):
            if gi:
                lay.addSpacing(space(5))
            lay.addLayout(C.hbox(C.label(title, 'overline', 'tertiary'), margins=(3, 0, 0, 0)))
            lay.addSpacing(space(2))
            for view, icon in items:
                item = C.NavItem(t, view, icon)
                item.clicked.connect(lambda _checked=False, v=view: self.view_chosen.emit(v))
                group.addButton(item)
                self.nav[view] = item
                lay.addWidget(item)
                lay.addSpacing(space(1))
        lay.addStretch(1)
        lay.addWidget(C.hairline())
        self.file_card = C.FileCard(t)
        lay.addWidget(self.file_card)
        self.setLayout(lay)


class _Toolbar(C.TitleBarArea):
    """The toolbar: the view's title and badge, Load data ▾, Export ▾, Help, the side-panel toggle and Run."""

    def __init__(self, t: Theme):
        super().__init__()
        self.setObjectName('Toolbar')
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setFixedHeight(SIZE['toolbar'])
        self.sidebar_toggle = C.tool_button(t, None, 'panel-left')
        self.sidebar_toggle.setToolTip('Show the sidebar')
        self.sidebar_toggle.setAccessibleName('Show the sidebar')
        self.title = C.label('', 'title')
        self.badge = C.badge('')
        self.load = C.tool_button(t, 'Load data', 'open', menu=True)
        self.load.setObjectName('LoadData')
        self.export = C.tool_button(t, 'Export', 'export', menu=True)
        self.help = C.tool_button(t, None, 'help')
        self.help.setToolTip('Reading the plots')
        self.help.setAccessibleName('Reading the plots')
        self.side = C.tool_button(t, None, 'panel-right', checked=True)
        self.side.setToolTip('Show or hide the side panel')
        self.side.setAccessibleName('Side panel')
        # One width for every label ('Run fit', 'Run analysis', 'Stop'), so the toolbar never shifts.
        self.run = C.primary_button(t, 'Run analysis', 'play')
        divider = C.hairline(vertical=True)
        divider.setFixedHeight(space(6) - space(2))
        # Room for the window controls the title bar keeps on macOS while the sidebar is hidden.
        self.inset = QWidget()
        self.inset.setFixedWidth(space(8) + space(6))
        self.inset.setVisible(False)
        self.sidebar_toggle.setVisible(False)
        self.setLayout(
            C.hbox(
                self.inset,
                self.sidebar_toggle,
                self.title,
                3,
                self.badge,
                None,
                self.load,
                self.export,
                2,
                divider,
                2,
                self.help,
                self.side,
                2,
                self.run,
                spacing=1,
                margins=(6, 0, 5, 0),
            )
        )


class _StatusBar(QWidget):
    """The status bar: what is running in every session (or the last message here) and what the fit is."""

    clicked = pyqtSignal()

    def __init__(self, t: Theme):
        super().__init__()
        self.setObjectName('StatusBar')
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setFixedHeight(SIZE['statusbar'])
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dot = C.StatusDot(t, 'text-tertiary')
        # The summary gives way to the model line and is cut short with an ellipsis where it does not fit.
        self.text = C.ElidedLabel('Ready', 'small', 'secondary')
        self.model_line = C.label('', 'small', 'tertiary')
        lay = C.hbox(self.dot, 2, self.text, 4, self.model_line, spacing=0, margins=(5, 0, 5, 0))
        lay.setStretchFactor(self.text, 1)
        self.setLayout(lay)

    def set_text(self, text: str) -> None:
        """Show *text* as the summary, with the whole of it in the tooltip."""
        self.text.set_full_text(text)
        self.setToolTip(f'{text}\nClick to open the sessions.')

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class FittingMainWindow(QMainWindow):
    """The main window: every open session, one on screen, with the commands that act on it.

    All fitting state lives in the :class:`~gui.session_model.SessionModel` of
    each :class:`~gui.fitting_session.FittingSession`; the window holds the
    sessions, which one is on screen, the view shown and whether the sidebar
    and side panels are, and draws the sidebar, toolbar and status bar from the
    sessions' models.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._t = theme()
        self._update_worker: UpdateCheckWorker | None = None
        self._sim_window: QMainWindow | None = None
        self._settings_window: QWidget | None = None
        self._sessions: list[FittingSession] = []
        self._view = 'Measurements'
        self._side_visible = True
        self._window_message: str | None = None
        self._popover: QWidget | None = None
        if C.MAC:
            self.setWindowFlag(Qt.WindowType.ExpandedClientAreaHint, True)
            self.setWindowFlag(Qt.WindowType.NoTitleBarBackgroundHint, True)
            self.setAttribute(Qt.WidgetAttribute.WA_ContentsMarginsRespectsSafeArea, False)
        self._set_title()
        self.resize(1440, 900)
        self._setup_ui()
        self._setup_actions()
        self._setup_menus()
        self._new_session()
        appearance().changed.connect(self._refresh)
        # Silent background check for newer releases on GitHub, unless switched off in Settings.
        # Failures (offline, rate-limited, etc.) are intentionally swallowed.
        if preferences.check_for_updates():
            self._run_update_check(silent=True)

    def _set_title(self, suffix: str = '') -> None:
        """Set the window title to ``SupraSimFit <version> [suffix]``."""
        self.setWindowTitle(f'SupraSimFit {__version__} {suffix}'.rstrip())

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def active_session(self) -> FittingSession | None:
        widget = self._stack.currentWidget()
        return widget if isinstance(widget, FittingSession) else None

    def sessions(self) -> list[FittingSession]:
        """Every open session, in the order they were opened."""
        return list(self._sessions)

    def current_view(self) -> str:
        return self._view

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        t = self._t
        self._sidebar = _Sidebar(t)
        self._sidebar_rule = C.hairline(vertical=True)
        self._toolbar = _Toolbar(t)
        self._stack = QStackedWidget()
        self._status = _StatusBar(t)
        content = QWidget()
        content.setLayout(C.vbox(self._toolbar, C.hairline(), self._stack, spacing=0))
        top = QWidget()
        top.setLayout(C.hbox(self._sidebar, self._sidebar_rule, content, spacing=0))
        root = QWidget()
        root.setLayout(C.vbox(top, C.hairline(), self._status, spacing=0))
        # The window opens with the focus on no control, so no focus ring shows until the keyboard moves it.
        root.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        if C.MAC:
            # The window reaches up under the transparent title bar.
            root.setAttribute(Qt.WidgetAttribute.WA_ContentsMarginsRespectsSafeArea, False)
            if QApplication.platformName() == 'cocoa':  # a native window to set it on
                C.hide_title_text(self)
        self.setCentralWidget(root)
        root.setFocus()

        self._sidebar.view_chosen.connect(self.show_view)
        self._sidebar.switcher.clicked.connect(self._open_switcher)
        self._sidebar.file_card.clicked.connect(lambda: self.show_view('Measurements'))
        self._sidebar.toggle.clicked.connect(lambda: self._set_sidebar_visible(False))
        self._toolbar.sidebar_toggle.clicked.connect(lambda: self._set_sidebar_visible(True))
        self._toolbar.load.clicked.connect(self._open_load_menu)
        self._toolbar.export.clicked.connect(self._open_export_menu)
        self._toolbar.help.clicked.connect(self._show_guide)
        self._toolbar.side.clicked.connect(lambda: self._set_side_visible(self._toolbar.side.isChecked()))
        self._toolbar.run.clicked.connect(self._on_primary)
        self._status.clicked.connect(self._open_switcher)

    def _setup_actions(self) -> None:
        keys = QKeySequence.StandardKey
        self._act_run = _action(self, 'Run fit', 'play', RUN_FIT_KEY, self._on_primary)
        self._act_new = _action(self, 'New session', 'plus', keys.AddTab, lambda: self._new_session())
        self._act_add = _action(self, 'Add files to this session…', 'plus', keys.Open, self._on_add_files)
        self._act_replace = _action(self, 'Replace data…', 'open', None, self._on_replace)
        self._act_load_new = _action(self, 'Load data into a new session…', 'file-plus', 'Ctrl+Shift+O')
        self._act_load_new.triggered.connect(self._on_load_new)
        self._act_open_results = _action(self, 'Open results file…', 'results', None, self._on_open_results)
        self._act_duplicate = _action(self, 'Duplicate session', 'copy', None, self._duplicate_current)
        self._act_close = _action(self, 'Close session', 'x', keys.Close, self._close_current)
        self._act_results = _action(
            self, 'Results file…', 'save', keys.Save, lambda: self._on_session('export_results')
        )
        self._act_txt = _action(
            self, 'Report (TXT)…', 'file-text', None, lambda: self._on_session('export_results_txt')
        )
        self._act_csv = _action(self, 'Table (CSV)…', 'table', None, lambda: self._on_session('export_results_csv'))
        self._act_raw = _action(self, 'Raw data…', 'file', None, lambda: self._on_session('export_raw_data'))
        self._act_plot = _action(self, 'Plot image…', 'image', None, self._on_save_plot)
        self._act_several = _action(self, 'Export several…', 'layers', 'Ctrl+Shift+E', self._on_export_several)
        self._act_demo = _action(self, 'Demo IDA', '', None, self._on_load_demo)
        self._act_simulate = _action(self, 'Simulate…', '', None, self._on_simulate)
        self._act_guide = _action(self, 'Reading the plots…', '', None, self._show_guide)
        self._act_check_updates = _action(
            self, 'Check for updates…', '', None, lambda: self._run_update_check(silent=False)
        )
        self._act_settings = _action(self, 'Settings…', '', keys.Preferences, self._open_settings)
        self._act_settings.setMenuRole(QAction.MenuRole.PreferencesRole)
        self._act_quit = _action(self, 'Quit', '', keys.Quit, self.close)
        self._act_quit.setMenuRole(QAction.MenuRole.QuitRole)
        self._act_sidebar = _action(self, 'Show sidebar', '', None, lambda on: self._set_sidebar_visible(on))
        self._act_sidebar.setCheckable(True)
        self._act_sidebar.setChecked(True)
        self._act_side = _action(self, 'Show side panel', '', None, lambda on: self._set_side_visible(on))
        self._act_side.setCheckable(True)
        self._act_side.setChecked(True)
        self._view_actions: dict[str, QAction] = {}
        views = QActionGroup(self)
        for view in VIEWS:
            act = _action(self, view, '', None, lambda _on=False, v=view: self.show_view(v))
            act.setCheckable(True)
            views.addAction(act)
            self._view_actions[view] = act
        # Shortcuts work wherever the focus is in the window, menus or not.
        self.addActions([self._act_run, self._act_add, self._act_load_new, self._act_close, self._act_several])
        for n in range(1, 10):
            act = _action(self, f'Session {n}', '', f'Ctrl+{n}', lambda _on=False, i=n - 1: self._switch_to_index(i))
            self.addAction(act)

    def _setup_menus(self) -> None:
        mb = self.menuBar()
        file_menu = mb.addMenu('&File')
        file_menu.addActions([self._act_new, self._act_add, self._act_replace, self._act_load_new])
        file_menu.addAction(self._act_open_results)
        file_menu.addSeparator()
        file_menu.addActions([self._act_results, self._act_txt, self._act_csv, self._act_raw, self._act_plot])
        file_menu.addAction(self._act_several)
        file_menu.addSeparator()
        file_menu.addAction(self._act_close)
        file_menu.addSeparator()
        file_menu.addAction(self._act_settings)
        file_menu.addAction(self._act_quit)
        tools = mb.addMenu('&Tools')
        tools.addActions([self._act_simulate, self._act_demo])
        view_menu = mb.addMenu('&View')
        view_menu.addActions([self._act_sidebar, self._act_side])
        view_menu.addSeparator()
        view_menu.addActions(list(self._view_actions.values()))
        help_menu = mb.addMenu('&Help')
        help_menu.addAction(self._act_guide)
        help_menu.addSeparator()
        help_menu.addAction(self._act_check_updates)

    # ------------------------------------------------------------------
    # Drawing the window from the sessions
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        """Draw the sidebar, toolbar and status bar from the session on screen and every running one."""
        session = self.active_session()
        if session is None:
            return
        model = session.model
        busy_others = sum(s.model.running() for s in self._sessions if s is not session)
        self._sidebar.switcher.set_session(model.name(), model.detail(), len(self._sessions), busy_others)
        self._sidebar.file_card.set_file(*model.file_card())
        for view, item in self._sidebar.nav.items():
            item.setChecked(view == self._view)
            item.set_status(*model.view_status(view))
        self._view_actions[self._view].setChecked(True)

        bar = self._toolbar
        bar.title.setText(self._view)
        badge = session.view_badge(self._view)
        bar.badge.setText(badge or '')
        bar.badge.setVisible(bool(badge))
        has_side = session.has_side_panel(self._view)
        bar.side.setEnabled(has_side)
        bar.side.setChecked(has_side and self._side_visible)
        running = model.running()
        label = 'Stop' if running else ('Run analysis' if self._view == 'Sensitivity' else 'Run fit')
        bar.run.set_text(label, 'stop' if running else 'play')
        bar.run.setAccessibleName(label)
        self._act_run.setText(label)
        shortcut = self._act_run.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
        bar.run.setToolTip(f'{label} ({shortcut})')
        self._act_duplicate.setText(f'Duplicate {model.name()}')
        self._act_close.setText(f'Close {model.name()}')

        running_sessions = [s for s in self._sessions if s.model.running()]
        if running_sessions:
            parts = [f'{s.model.name()} {s.model.running_label()}' for s in running_sessions]
            if len(parts) > 1:
                parts.insert(0, f'{len(parts)} running')
            text, tone = '  ·  '.join(parts), 'accent'
        else:
            message = self._window_message or model.status
            text, tone = ('Ready  ·  ' + message) if message else 'Ready', 'text-tertiary'
        self._status.set_text(text)
        self._status.dot.set_tone(tone)
        self._status.model_line.setText('  ·  '.join(model.model_line()))

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def _new_session(self, *, warn: bool = True) -> FittingSession:
        """Open a new session and put it on screen; with *warn*, say when it could not take the
        plot appearance stored for new sessions."""
        session = FittingSession()
        session.changed.connect(self._refresh)
        session.side_panel_closed.connect(lambda: self._set_side_visible(False))
        session.side_panel_requested.connect(lambda: self._set_side_visible(True))
        session.view_requested.connect(self.show_view)
        session.new_session_requested.connect(self._on_load_new)
        session.set_side_panels_visible(self._side_visible)
        session.show_view(self._view)
        self._sessions.append(session)
        self._stack.addWidget(session)
        self._switch_to(session)
        refusal = session.model.appearance_refusal
        if warn and refusal is not None:
            QMessageBox.warning(self, refusal.title, refusal.message)
        return session

    def _switch_to(self, session: FittingSession) -> None:
        session.show_view(self._view)
        self._stack.setCurrentWidget(session)
        self._refresh()

    def _switch_to_index(self, index: int) -> None:
        if 0 <= index < len(self._sessions):
            self._switch_to(self._sessions[index])

    def _fresh_session(self) -> FittingSession:
        """The session on screen when it holds nothing and runs nothing, else a new one."""
        session = self.active_session()
        model = session.model if session is not None else None
        if model is None or model.measurement_set is not None or model.held_fit_results or model.running():
            return self._new_session()
        return session

    def _duplicate_current(self) -> None:
        """Open a copy of the session on screen: its data, binding model and input uncertainties, and no results."""
        source = self.active_session()
        if source is not None:
            # The copy takes the appearance of the session it copies, so a stored one is not read.
            self._new_session(warn=False).copy_from(source)

    def _close_current(self) -> None:
        session = self.active_session()
        if session is not None:
            self._close_session(session)

    def _close_session(self, session: FittingSession) -> None:
        """Close *session*, asking first when it runs and stopping its work; the window keeps one session."""
        model = session.model
        work = model.running_work() or ('Ka profile' if model.running() else '')
        if work:
            answer = QMessageBox.question(
                self,
                'Close session',
                f'Stop the {work} and close {model.name()}?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        index = self._sessions.index(session)
        self._sessions.remove(session)
        self._stack.removeWidget(session)
        model.shutdown()
        session.deleteLater()
        if not self._sessions:
            self._new_session()
        else:
            self._switch_to(self._sessions[min(index, len(self._sessions) - 1)])

    # ------------------------------------------------------------------
    # Views, sidebar and side panel
    # ------------------------------------------------------------------

    def show_view(self, view: str) -> None:
        """Put *view* of the session on screen."""
        self._view = view
        session = self.active_session()
        if session is not None:
            session.show_view(view)
        self._refresh()

    def _set_sidebar_visible(self, visible: bool) -> None:
        self._sidebar.setVisible(visible)
        self._sidebar_rule.setVisible(visible)
        self._toolbar.sidebar_toggle.setVisible(not visible)
        self._toolbar.inset.setVisible(C.MAC and not visible)
        self._act_sidebar.setChecked(visible)

    def _set_side_visible(self, visible: bool) -> None:
        self._side_visible = visible
        for session in self._sessions:
            session.set_side_panels_visible(visible)
        self._act_side.setChecked(visible)
        self._refresh()

    # ------------------------------------------------------------------
    # Popovers
    # ------------------------------------------------------------------

    def _show_popover(self, popover: QWidget, anchor: QWidget, right: bool = False) -> None:
        if self._popover is not None:
            self._popover.close_popover()
        self._popover = popover
        popover.closed.connect(lambda: setattr(self, '_popover', None))
        popover.popup(anchor, right)

    def _open_switcher(self) -> None:
        session = self.active_session()
        rows = []
        for s in self._sessions:
            state, words, progress = s.model.summary()
            rows.append(
                {
                    'name': s.model.name(),
                    'detail': s.model.detail(),
                    'state': state,
                    'status': words,
                    'progress': progress,
                }
            )
        hint = ''
        first, last = QKeySequence('Ctrl+1'), QKeySequence(f'Ctrl+{min(len(rows), 9)}')
        if len(rows) > 1:
            native = QKeySequence.SequenceFormat.NativeText
            hint = f'{first.toString(native)} – {last.toString(native)}'
        commands = [
            self._act_new,
            self._act_load_new,
            self._act_open_results,
            None,
            self._act_duplicate,
            self._act_close,
        ]
        popover = C.SessionPopover(
            self._t, self, rows, commands, current=self._sessions.index(session), title_hint=hint
        )
        popover.session_chosen.connect(self._switch_to_index)
        popover.renamed.connect(lambda i, name: self._sessions[i].model.set_custom_name(name))
        self._sidebar.switcher.setChecked(True)
        popover.closed.connect(lambda: self._sidebar.switcher.setChecked(False))
        anchor = self._sidebar.switcher if self._sidebar.isVisible() else self._toolbar.title
        self._show_popover(popover, anchor)

    def _open_load_menu(self) -> None:
        actions = [self._act_add, self._act_replace, None, self._act_load_new]
        note = 'Added files become replicates and must share this session’s concentrations.'
        self._show_menu(C.PopoverMenu(self._t, self, actions, note), self._toolbar.load)

    def _open_export_menu(self) -> None:
        actions = [self._act_results, self._act_txt, self._act_csv, self._act_raw, None, self._act_plot]
        actions += [None, self._act_several]
        self._show_menu(C.PopoverMenu(self._t, self, actions, width=264), self._toolbar.export)

    def _show_menu(self, menu: C.PopoverMenu, button: C.Button) -> None:
        button.setCheckable(True)
        button.setChecked(True)

        def released() -> None:
            button.setChecked(False)
            button.setCheckable(False)

        menu.closed.connect(released)
        self._show_popover(menu, button)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def _on_primary(self) -> None:
        session = self.active_session()
        if session is not None:
            session.run_primary(self._view)

    def _on_session(self, method: str) -> None:
        session = self.active_session()
        if session is not None:
            getattr(session, method)()

    def _on_add_files(self) -> None:
        session = self.active_session()
        if session is not None:
            session.add_files()

    def _on_replace(self) -> None:
        session = self.active_session()
        if session is not None:
            session.replace_data()

    def _on_load_new(self) -> None:
        previous = self.active_session()
        session = self._new_session()
        if not session.replace_data() and previous is not None:
            # Nothing was loaded: the new session goes and the one before comes back.
            self._close_session(session)
            self._switch_to(previous)

    def _on_open_results(self) -> None:
        self._fresh_session().import_results()

    def _on_load_demo(self) -> None:
        self._fresh_session().load_demo_ida()

    def _on_save_plot(self) -> None:
        session = self.active_session()
        if session is not None:
            session.export_plot(self._view)

    def _on_export_several(self) -> None:
        session = self.active_session()
        if session is not None:
            session.open_export_multiple_dialog()

    def _show_guide(self) -> None:
        show_plot_guide(self, self._view)

    def _on_simulate(self) -> None:
        """Open (or raise) the Simulation window."""
        if self._sim_window is None:
            from gui.views.simulation import SimulationWindow

            self._sim_window = SimulationWindow(self)
            self._sim_window.fit_requested.connect(self._fit_simulation)
        self._sim_window.show()
        self._sim_window.raise_()
        self._sim_window.activateWindow()

    def _fit_simulation(self, form, simulation) -> None:
        """Give the simulated data and the binding model of *form* to a session of their own, and fit them.

        The session on screen takes them where it holds nothing and runs nothing; else a new one opens.
        """
        session = self._fresh_session()
        form.carry_to(session.model, simulation)
        self.show_view('Fit results')
        self.raise_()
        self.activateWindow()
        session.run_fit()

    def _open_settings(self) -> None:
        """Open (or raise) the Settings window."""
        if self._settings_window is None:
            from gui.dialogs.settings_window import SettingsWindow

            self._settings_window = SettingsWindow(self._act_check_updates, self)
        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()

    # ------------------------------------------------------------------
    # Update check
    # ------------------------------------------------------------------

    def _say(self, message: str | None) -> None:
        """Say *message* on the status bar for the whole window, or give it back to the sessions (``None``)."""
        self._window_message = message
        self._refresh()

    def _run_update_check(self, *, silent: bool) -> None:
        """Spawn an :class:`UpdateCheckWorker`.

        Parameters
        ----------
        silent : bool
            ``True`` for the background startup check — errors are swallowed,
            and the dialog is not opened (only the title-bar hint appears).
            ``False`` for the user-triggered menu action — errors raise a
            :class:`QMessageBox.warning`, the dialog opens when a newer release
            is found, and a check already in flight is said to be so.
        """
        # One check at a time: the startup check is already on its way when the
        # window opens, and the menu item says so rather than doing nothing.
        if self._update_worker is not None and self._update_worker.isRunning():
            if not silent:
                QMessageBox.information(
                    self,
                    'Already checking',
                    'A check for updates is already running. Give it a moment, then try again.',
                )
            return
        if not silent:
            self._act_check_updates.setEnabled(False)
            self._say('Checking for updates…')

        worker = UpdateCheckWorker(self)
        self._update_worker = worker
        worker.finished.connect(lambda info, w=worker: self._on_update_check_done(w, info, silent=silent))
        worker.error.connect(lambda msg, w=worker: self._on_update_check_error(w, msg, silent=silent))
        worker.start()

    def _on_update_check_done(self, worker: UpdateCheckWorker, info: dict, *, silent: bool) -> None:
        self._discard_update_worker(worker)
        if not silent:
            self._act_check_updates.setEnabled(True)
            self._say(None)
        if is_newer(info['latest_version'], __version__):
            self._set_title('(updates available)')
            if not silent:
                UpdateAvailableDialog(info, self).exec()
        elif not silent:
            QMessageBox.information(
                self,
                'Up to date',
                f"You're on the latest version ({__version__}).",
            )

    def _on_update_check_error(self, worker: UpdateCheckWorker, msg: str, *, silent: bool) -> None:
        self._discard_update_worker(worker)
        if silent:
            return  # Offline / rate-limited / etc. — stay quiet.
        self._act_check_updates.setEnabled(True)
        self._say(None)
        QMessageBox.warning(self, 'Could not check for updates', msg)

    def _discard_update_worker(self, worker: UpdateCheckWorker) -> None:
        """Let go of the check that just reported, and clear the reference when it is the one held.

        A check reports from inside its thread's ``run()``, so the thread may
        still be ending when the report arrives; :func:`~gui.workers.retire`
        deletes the worker only once it has, since destroying a running
        ``QThread`` aborts the app. Only the check that reported is let go of;
        a newer one has the reference by then and runs on.
        """
        retire(worker)
        if self._update_worker is worker:
            self._update_worker = None

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """Stop the work every session started, and any update check, before closing.

        Destroying a running ``QThread`` aborts the app with ``QThread:
        Destroyed while thread is still running``, so every run is seen out
        before the window goes; a sensitivity run's worker processes end with
        it. Every session is asked to stop first and waited for afterwards, so
        the runs stop side by side rather than one after another.
        """
        for session in self._sessions:
            session.model.cancel_running()
        for session in self._sessions:
            session.model.shutdown()
        retire(self._update_worker)
        self._update_worker = None
        super().closeEvent(event)


def _app_icon_path() -> str | None:
    """Locate the bundled app icon for both source runs and PyInstaller bundles."""
    base = getattr(sys, '_MEIPASS', None) or str(Path(__file__).resolve().parent.parent)
    for name in ('AppIcon.ico', 'AppIcon.png'):
        p = Path(base) / 'assets' / name
        if p.exists():
            return str(p)
    return None


def start_application(argv: list[str]) -> QApplication:
    """The application as the app runs it, created from *argv* unless one is running.

    English (US) locale — a dot as decimal separator in every field — set before the
    application exists, the Fusion style and the app icon. :func:`launch` and the render
    harness (``docs/design/render.py``) both start from it, so a render is drawn as the
    app ships.
    """
    QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
    app = QApplication.instance() or QApplication(argv)
    app.setStyle('Fusion')
    icon_path = _app_icon_path()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))
    return app


def launch() -> None:
    """Entry point — create the QApplication and launch the main window."""
    # Set org/app identity before QApplication so QSettings (used by
    # gui.preferences) lands in the correct per-user location.
    QCoreApplication.setOrganizationName(ORG_NAME)
    QCoreApplication.setApplicationName(APP_NAME)

    # Windows: pin an explicit AppUserModelID so the taskbar groups under us, not python.exe.
    if sys.platform == 'win32':
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f'{ORG_NAME}.{APP_NAME}')
        except Exception:
            pass

    app = start_application(sys.argv)
    reset = preferences.reset_unreadable()  # said once the window is on screen
    appearance().set_mode(preferences.appearance_mode())

    window = FittingMainWindow()
    # pyqtgraph, imported with the views, has put in a hook that only prints; this one replaces it.
    install_exception_hook(window, log_dir())
    window.show()
    if reset:
        QMessageBox.warning(
            window,
            'Settings Reset',
            ' '.join([*reset, f'You can change {"it" if len(reset) == 1 else "them"} in Settings.']),
        )
    sys.exit(app.exec())


if __name__ == '__main__':
    launch()
