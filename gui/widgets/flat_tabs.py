"""Flat / minimal tab widgets — one reusable style for every tab in the app.

Implements the flat/minimal tab design (see ``flat_minimal_tabs_spec.md``):
transparent tabs, normal-weight labels, a 2px underline on the *active* tab only
(the 2px is reserved in every state so the label never shifts vertically), a
single ``#ECECEC`` hairline under the row, left-aligned tabs, and an inline "+"
button glued immediately after the last tab (not a corner widget).

Used by both tab systems:
- session tabs — closable, movable, with a "+" that opens a new session;
- plot tabs — fixed Fit Curve / Distributions over a white content pane.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import QStyle, QTabBar, QTabWidget, QToolButton

# Authoritative flat/minimal QSS. The 2px transparent bottom border lives on the
# base ::tab rule (not only on :selected) so selecting a tab never shifts its
# label. The QTabBar QToolButton rule neutralises the app-wide boxed QToolButton
# style for the overflow scroll chevrons (and the inline "+").
_FLAT_TABS_QSS = """
QTabWidget#flatTabs::pane {
    border: none;
    border-top: 1px solid #ECECEC;
}
QTabWidget#flatTabs > QTabBar {
    qproperty-drawBase: 0;
}
QTabWidget#flatTabs QTabBar::tab {
    background: transparent;
    color: #888888;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 10px 16px;
    margin-right: 4px;
}
QTabWidget#flatTabs QTabBar::tab:hover {
    color: #222222;
}
QTabWidget#flatTabs QTabBar::tab:selected {
    color: #111111;
    border-bottom: 2px solid #111111;
}
QTabWidget#flatTabs QTabBar::tab:disabled {
    color: #C8C8C8;
}
QTabWidget#flatTabs QTabBar QToolButton {
    background: transparent;
    border: none;
    min-width: 0;
}
"""

_WHITE_PANE_QSS = 'QTabWidget#flatTabs::pane { background: #FFFFFF; }'

# Inline "+": borderless, transparent, neutral grey that darkens on hover, glyph
# a touch larger than the labels. Its own sheet overrides the app-wide QToolButton
# box (border / gradient / min-width) so it never renders as a boxed button.
_ADD_BUTTON_QSS = """
QToolButton {
    border: none;
    background: transparent;
    color: #888888;
    font-size: 18px;
    min-width: 0;
    padding: 0 10px;
}
QToolButton:hover {
    color: #111111;
}
"""

# Minimal close affordance: a faint neutral "✕" that darkens on hover — no box,
# no colour. Replaces the platform default close glyph (which can render heavy or
# coloured, e.g. a red box) so the look is identical on every style / OS.
_CLOSE_BUTTON_QSS = """
QToolButton {
    border: none;
    background: transparent;
    color: #BBBBBB;
    font-size: 13px;
    min-width: 0;
    padding: 0 2px;
}
QToolButton:hover {
    color: #111111;
}
"""


class FlatTabBar(QTabBar):
    """Tab bar that keeps an optional inline "+" button after the last tab."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._add_button: QToolButton | None = None

    def set_add_callback(self, callback: Callable[[], None], tooltip: str = 'New tab') -> None:
        """Create the inline "+" affordance and run ``callback`` on click."""
        if self._add_button is None:
            btn = QToolButton(self)
            btn.setText('+')
            btn.setToolTip(tooltip)
            btn.setAutoRaise(True)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setCursor(Qt.CursorShape.ArrowCursor)
            btn.setStyleSheet(_ADD_BUTTON_QSS)
            self._add_button = btn
        self._add_button.clicked.connect(callback)
        self._reposition_add_button()

    def _reposition_add_button(self) -> None:
        btn = self._add_button
        if btn is None:
            return
        if self.count() == 0:
            btn.hide()
            return
        last = self.tabRect(self.count() - 1)
        if last.isNull():
            btn.hide()
            return
        btn.adjustSize()
        # 4px gap after the last tab (matches the inter-tab gap), vertically centred.
        btn.move(last.right() + 4, last.center().y() - btn.height() // 2)
        btn.show()

    # tabLayoutChange fires on every layout change — add, remove, move, resize,
    # overflow scroll — so it is the single hook needed to keep "+" glued last.
    def tabLayoutChange(self) -> None:
        super().tabLayoutChange()
        self._reposition_add_button()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._reposition_add_button()


class _FlatCloseButton(QToolButton):
    """Borderless neutral "✕" close affordance for a flat tab."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setText('✕')
        self.setToolTip('Close')
        self.setAutoRaise(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setStyleSheet(_CLOSE_BUTTON_QSS)


class FlatTabWidget(QTabWidget):
    """A ``QTabWidget`` rendered in the flat/minimal style (see module docstring).

    Parameters
    ----------
    closable, movable : bool
        Enable the close affordance / drag-reordering.
    white_pane : bool
        Fill the content pane white (``#FFFFFF``). Off by default so the pane
        inherits the window background.
    add_callback : Callable[[], None] | None
        If given, show an inline "+" after the last tab that calls this on click.
    add_tooltip : str
        Tooltip for the "+".
    """

    def __init__(
        self,
        *,
        closable: bool = False,
        movable: bool = False,
        white_pane: bool = False,
        add_callback: Callable[[], None] | None = None,
        add_tooltip: str = 'New tab',
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName('flatTabs')
        self.setTabBar(FlatTabBar(self))
        self.setStyleSheet(_FLAT_TABS_QSS + (_WHITE_PANE_QSS if white_pane else ''))
        self.setDocumentMode(True)
        self.tabBar().setExpanding(False)
        self.tabBar().setDrawBase(False)
        self.setUsesScrollButtons(True)
        self._closable = closable
        self.setMovable(movable)
        if add_callback is not None:
            self.tabBar().set_add_callback(add_callback, add_tooltip)

    def tabInserted(self, index: int) -> None:
        super().tabInserted(index)
        if self._closable:
            self._install_close_button(index)
        self._update_close_buttons()

    def tabRemoved(self, index: int) -> None:
        super().tabRemoved(index)
        self._update_close_buttons()

    def _close_side(self) -> QTabBar.ButtonPosition:
        # Platform convention: close button is left-side on macOS, right elsewhere.
        return QTabBar.ButtonPosition(self.style().styleHint(QStyle.StyleHint.SH_TabBar_CloseButtonPosition))

    def _install_close_button(self, index: int) -> None:
        bar = self.tabBar()
        btn = _FlatCloseButton(bar)
        btn.clicked.connect(lambda: self._emit_close_for(btn))
        bar.setTabButton(index, self._close_side(), btn)

    def _emit_close_for(self, btn: QToolButton) -> None:
        # Map the clicked button to its current tab index (robust to reordering),
        # then route through the standard close signal the app already handles.
        bar = self.tabBar()
        side = self._close_side()
        for i in range(self.count()):
            if bar.tabButton(i, side) is btn:
                self.tabCloseRequested.emit(i)
                return

    def _update_close_buttons(self) -> None:
        # Spec §8.1: never allow zero tabs — hide the close control on the sole
        # remaining tab so it cannot be closed to empty; re-show it once ≥2 tabs.
        if not self._closable:
            return
        bar = self.tabBar()
        side = self._close_side()
        single = self.count() == 1
        for i in range(self.count()):
            btn = bar.tabButton(i, side)
            if btn is not None:
                btn.setVisible(not single)
