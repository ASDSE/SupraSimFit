"""FittingMainWindow — thin shell managing tabbed fitting sessions."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtCore import QLocale
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QToolBar,
)

from gui.fitting_session import FittingSession

_APP_QSS = """
QToolBar {
    spacing: 6px;
    padding: 4px 10px;
    border-bottom: 1px solid rgba(0, 0, 0, 0.15);
}
QToolButton {
    padding: 5px 14px;
    min-width: 70px;
    border: 1px solid rgba(0, 0, 0, 0.22);
    border-radius: 5px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255,255,255,0.95), stop:1 rgba(225,225,225,0.95));
    font-size: 12px;
}
QToolButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255,255,255,1.0), stop:1 rgba(235,235,235,1.0));
    border-color: rgba(0, 0, 0, 0.32);
}
QToolButton:pressed {
    background: rgba(195, 195, 195, 0.95);
}
QTabBar {
    alignment: left;
}
QTabBar::tab {
    min-width: 100px;
    padding: 6px 16px;
    font-size: 12px;
    border: 1px solid rgba(0, 0, 0, 0.25);
    border-bottom: none;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(235,235,235,0.95), stop:1 rgba(215,215,215,0.95));
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: white;
    border-color: rgba(0, 0, 0, 0.3);
}
QTabBar::tab:!selected:hover {
    background: rgba(245,245,245,0.95);
}
"""


class FittingMainWindow(QMainWindow):
    """Main application window: tab management + toolbar + menu routing.

    All fitting state lives in each :class:`~gui.fitting_session.FittingSession`
    tab.  The main window holds no fitting state of its own.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Fitting App')
        self.resize(1280, 820)
        self._setup_tabs()
        self._setup_toolbar()
        self._setup_menus()
        self._setup_statusbar()
        # Open one empty session on startup
        self._new_session()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def active_session(self) -> FittingSession | None:
        widget = self._tabs.currentWidget()
        return widget if isinstance(widget, FittingSession) else None

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_tabs(self) -> None:
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        self._tabs.setMovable(True)
        # Don't stretch tabs to fill the bar — left-aligned, natural width
        self._tabs.tabBar().setExpanding(False)

        # "+" button to open new sessions, placed at the top-right corner
        plus_btn = QPushButton("+")
        plus_btn.setFixedSize(28, 28)
        plus_btn.setToolTip("New Session (Ctrl+T)")
        plus_btn.clicked.connect(self._new_session)
        self._tabs.setCornerWidget(plus_btn, Qt.Corner.TopRightCorner)

        self.setCentralWidget(self._tabs)

    def _setup_toolbar(self) -> None:
        tb = QToolBar('Main')
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(tb)

        self._act_load = QAction('Load Data', self)
        self._act_load.setShortcut(QKeySequence.StandardKey.Open)
        self._act_load.setToolTip('Load measurement data into the active session (Ctrl+O)')
        self._act_load.triggered.connect(self._on_load)
        tb.addAction(self._act_load)

        self._act_demo = QAction('Demo IDA', self)
        self._act_demo.setToolTip('Load bundled IDA demo data and run a fit with default settings')
        self._act_demo.triggered.connect(self._on_load_demo)
        tb.addAction(self._act_demo)

        tb.addSeparator()

        self._act_fit = QAction('Run Fit', self)
        self._act_fit.setShortcut(QKeySequence('Ctrl+R'))
        self._act_fit.setToolTip('Run multi-start fitting in the active session (Ctrl+R)')
        self._act_fit.triggered.connect(self._on_run_fit)
        tb.addAction(self._act_fit)

        tb.addSeparator()

        self._act_export = QAction('Export Results', self)
        self._act_export.setShortcut(QKeySequence.StandardKey.Save)
        self._act_export.setToolTip('Export fit results to JSON (Ctrl+S)')
        self._act_export.triggered.connect(self._on_export)
        tb.addAction(self._act_export)

        self._act_import = QAction('Import Results', self)
        self._act_import.setToolTip('Import fit results from JSON for re-plotting')
        self._act_import.triggered.connect(self._on_import)
        tb.addAction(self._act_import)

        self._act_save_plot = QAction('Save Plot', self)
        self._act_save_plot.setToolTip('Export the current plot as PNG or SVG')
        self._act_save_plot.triggered.connect(self._on_save_plot)
        tb.addAction(self._act_save_plot)

    def _setup_menus(self) -> None:
        mb = self.menuBar()

        # File menu
        file_menu = mb.addMenu('&File')

        self._act_new = QAction('New Session', self)
        self._act_new.setShortcut(QKeySequence('Ctrl+T'))
        self._act_new.setToolTip('Open a new fitting session tab (Ctrl+T)')
        self._act_new.triggered.connect(self._new_session)
        file_menu.addAction(self._act_new)

        file_menu.addAction(self._act_load)
        file_menu.addSeparator()
        file_menu.addAction(self._act_fit)
        file_menu.addSeparator()
        file_menu.addAction(self._act_export)
        file_menu.addAction(self._act_import)
        file_menu.addAction(self._act_save_plot)
        file_menu.addSeparator()
        quit_act = QAction('&Quit', self)
        quit_act.setShortcut(QKeySequence.StandardKey.Quit)
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        # View menu
        view_menu = mb.addMenu('&View')
        close_tab_act = QAction('Close Tab', self)
        close_tab_act.setShortcut(QKeySequence('Ctrl+W'))
        close_tab_act.triggered.connect(lambda: self._close_tab(self._tabs.currentIndex()))
        view_menu.addAction(close_tab_act)

    def _setup_statusbar(self) -> None:
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._statusbar.showMessage('Ready')

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _new_session(self) -> None:
        session = FittingSession()
        session.title_changed.connect(lambda title, s=session: self._rename_tab(s, title))
        session.status_message.connect(self._statusbar.showMessage)
        idx = self._tabs.addTab(session, 'New Session')
        self._tabs.setCurrentIndex(idx)

    def _close_tab(self, idx: int) -> None:
        if self._tabs.count() == 1:
            # Keep at least one tab
            QMessageBox.information(self, 'Cannot Close', 'At least one session must remain open.')
            return
        widget = self._tabs.widget(idx)
        self._tabs.removeTab(idx)
        if widget:
            widget.deleteLater()

    def _rename_tab(self, session: FittingSession, title: str) -> None:
        idx = self._tabs.indexOf(session)
        if idx >= 0:
            self._tabs.setTabText(idx, title)

    # ------------------------------------------------------------------
    # Toolbar / menu slots
    # ------------------------------------------------------------------

    def _on_load(self) -> None:
        session = self.active_session()
        if session:
            session._data_panel.load_file()

    def _on_load_demo(self) -> None:
        session = self.active_session()
        if session:
            session.load_demo_ida()

    def _on_run_fit(self) -> None:
        session = self.active_session()
        if session:
            session.run_fit()

    def _on_export(self) -> None:
        session = self.active_session()
        if session:
            session.export_results()

    def _on_import(self) -> None:
        session = self.active_session()
        if session:
            session.import_results()

    def _on_save_plot(self) -> None:
        session = self.active_session()
        if session:
            session.export_plot()


def launch() -> None:
    """Entry point — create the QApplication and launch the main window."""
    import sys

    # Force English locale globally: dot as decimal separator, comma as thousands
    QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))

    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(_APP_QSS)
    window = FittingMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    launch()
