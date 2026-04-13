"""FittingMainWindow — thin shell managing tabbed fitting sessions."""

from __future__ import annotations

from PyQt6.QtCore import QLocale, Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QApplication, QMainWindow, QMenu, QMessageBox, QPushButton, QStatusBar, QTabWidget, QToolBar, QToolButton

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
QGroupBox {
    font-size: 14px;
    font-weight: bold;
    margin-top: 22px;
    border: 1px solid rgba(0, 0, 0, 0.2);
    border-radius: 5px;
    padding: 14px 6px 6px 6px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 2px 8px;
    color: rgba(20, 40, 90, 0.9);
    background: transparent;
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
        plus_btn = QPushButton('+')
        plus_btn.setFixedSize(28, 28)
        plus_btn.setToolTip('New Session (Ctrl+T)')
        plus_btn.clicked.connect(self._new_session)
        self._tabs.setCornerWidget(plus_btn, Qt.Corner.TopRightCorner)

        self.setCentralWidget(self._tabs)

    def _setup_toolbar(self) -> None:
        tb = QToolBar('Main')
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(tb)

        # Import actions (grouped under the Import button)
        self._act_load = QAction('Import Data\u2026', self)
        self._act_load.setShortcut(QKeySequence.StandardKey.Open)
        self._act_load.setToolTip('Import measurement data into the active session (Ctrl+O)')
        self._act_load.triggered.connect(self._on_load)
        # Register action on the main window so the Ctrl+O shortcut is active
        # even though the action is not placed directly on the toolbar.
        self.addAction(self._act_load)

        self._act_import = QAction('Import Fit Results\u2026', self)
        self._act_import.setToolTip('Import fit results from JSON for re-plotting')
        self._act_import.triggered.connect(self._on_import)

        self._act_load_style = QAction('Load Style Template\u2026', self)
        self._act_load_style.setToolTip('Load plot style settings from a JSON file')
        self._act_load_style.triggered.connect(self._on_load_style)

        import_menu = QMenu(self)
        import_menu.addAction(self._act_load)
        import_menu.addAction(self._act_import)
        import_menu.addSeparator()
        import_menu.addAction(self._act_load_style)

        self._import_btn = self._make_menu_button('Import', import_menu, 'Import / Load options')
        tb.addWidget(self._import_btn)

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

        # Export actions
        self._act_export = QAction('Export Results (JSON)', self)
        self._act_export.setShortcut(QKeySequence.StandardKey.Save)
        self._act_export.setToolTip('Export fit results to JSON (Ctrl+S)')
        self._act_export.triggered.connect(self._on_export)

        self._act_export_txt = QAction('Export Results (TXT)', self)
        self._act_export_txt.setToolTip('Export fit results as a human-readable text report')
        self._act_export_txt.triggered.connect(self._on_export_txt)

        self._act_save_plot = QAction('Save Plot', self)
        self._act_save_plot.setToolTip('Export the current plot as PNG or SVG')
        self._act_save_plot.triggered.connect(self._on_save_plot)

        self._act_save_style = QAction('Save Style Template', self)
        self._act_save_style.setToolTip('Save current plot style settings to a JSON file')
        self._act_save_style.triggered.connect(self._on_save_style)

        export_menu = QMenu(self)
        export_menu.addAction(self._act_export)
        export_menu.addAction(self._act_export_txt)
        export_menu.addSeparator()
        export_menu.addAction(self._act_save_plot)
        export_menu.addSeparator()
        export_menu.addAction(self._act_save_style)

        self._export_btn = self._make_menu_button('Export', export_menu, 'Export / Save options')
        tb.addWidget(self._export_btn)

    @staticmethod
    def _make_menu_button(label: str, menu: QMenu, tooltip: str) -> QToolButton:
        """Create a toolbar button that pops a menu without the Qt auto-arrow.

        The default ``InstantPopup`` mode draws a dropdown triangle in the
        bottom-right corner of the button; hiding the ``menu-indicator`` via
        stylesheet gives a clean text-only button while preserving the menu.
        """
        btn = QToolButton()
        btn.setText(label)
        btn.setToolTip(tooltip)
        btn.setAutoRaise(False)
        btn.setMenu(menu)
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setStyleSheet('QToolButton::menu-indicator { image: none; width: 0; }')
        return btn

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
        file_menu.addAction(self._act_export_txt)
        file_menu.addAction(self._act_import)
        file_menu.addAction(self._act_save_plot)
        file_menu.addSeparator()
        file_menu.addAction(self._act_save_style)
        file_menu.addAction(self._act_load_style)
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

    def _on_export_txt(self) -> None:
        session = self.active_session()
        if session:
            session.export_results_txt()

    def _on_import(self) -> None:
        session = self.active_session()
        if session:
            session.import_results()

    def _on_save_plot(self) -> None:
        session = self.active_session()
        if session:
            session.export_plot()

    def _on_save_style(self) -> None:
        session = self.active_session()
        if session:
            session.save_style_template()

    def _on_load_style(self) -> None:
        session = self.active_session()
        if session:
            session.load_style_template()


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
