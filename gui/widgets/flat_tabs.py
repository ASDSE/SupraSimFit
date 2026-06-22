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

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QResizeEvent, QWheelEvent
from PyQt6.QtWidgets import QAbstractButton, QLineEdit, QStyle, QTabBar, QTabWidget, QToolButton

# Authoritative flat/minimal QSS. The 2px transparent bottom border lives on the
# base ::tab rule (not only on :selected) so selecting a tab never shifts its
# label. ::scroller collapses the native overflow arrows to nothing (we scroll
# the tab strip by mouse wheel instead — see FlatTabBar.wheelEvent).
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
/* No native overflow chevrons — collapse the scroller region; wheel scrolls. */
QTabWidget#flatTabs QTabBar::scroller {
    width: 0px;
}
"""

_WHITE_PANE_QSS = 'QTabWidget#flatTabs::pane { background: #FFFFFF; }'

# Inline "+": borderless, transparent, neutral grey that darkens on hover, glyph
# a touch larger than the labels. Its own sheet overrides any inherited button box.
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
        """Create (or reconfigure) the inline "+" affordance; run ``callback`` on click."""
        if self._add_button is None:
            btn = QToolButton(self)
            btn.setText('+')
            btn.setAutoRaise(True)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setCursor(Qt.CursorShape.ArrowCursor)
            btn.setStyleSheet(_ADD_BUTTON_QSS)
            self._add_button = btn
        self._add_button.setToolTip(tooltip)
        try:
            self._add_button.clicked.disconnect()
        except TypeError:
            pass  # nothing connected yet
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

    def _scroll_buttons(self) -> list[QAbstractButton]:
        # QTabBar's two internal overflow scroll buttons: every QAbstractButton
        # child that isn't our own "+" or a tab close button. The QSS collapses
        # them to zero width (no chevrons); we drive them from the wheel.
        return [
            c
            for c in self.children()
            if isinstance(c, QAbstractButton) and c is not self._add_button and not isinstance(c, _FlatCloseButton)
        ]

    def wheelEvent(self, event: QWheelEvent) -> None:
        # Scroll the tab strip with the wheel when it overflows. The native scroll
        # arrows are collapsed to zero width (QSS) but still functional; pick the
        # one by its arrow direction (robust to their collapsed geometry) —
        # RightArrow scrolls toward later tabs, LeftArrow back.
        delta = event.angleDelta().y() or event.angleDelta().x()
        if delta:
            want = Qt.ArrowType.RightArrow if delta < 0 else Qt.ArrowType.LeftArrow
            for b in self._scroll_buttons():
                # Only intercept when a matching arrow can actually scroll —
                # otherwise let the wheel propagate (don't swallow it).
                if isinstance(b, QToolButton) and b.arrowType() == want and b.isEnabled():
                    b.click()
                    event.accept()
                    return
        super().wheelEvent(event)


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


class _TabRenameEdit(QLineEdit):
    """One-shot inline editor for a tab label.

    Emits ``done(text, committed)`` exactly once: committed on Enter or focus-out,
    cancelled (``committed=False``) on Escape. The ``_finished`` guard avoids the
    Escape-then-focus-out double-fire.
    """

    done = pyqtSignal(str, bool)

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, parent)
        self._finished = False
        self.setFrame(False)
        self.editingFinished.connect(lambda: self._finish(True))

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._finish(False)
        else:
            super().keyPressEvent(event)

    def _finish(self, commit: bool) -> None:
        if self._finished:
            return
        self._finished = True
        self.done.emit(self.text(), commit)


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
    editable : bool
        If True, double-clicking a tab opens an inline editor; committing emits
        ``tab_renamed(index, text)`` for the caller to apply.

    Signals
    -------
    tab_renamed(int, str)
        Emitted when a tab is renamed inline — (index, new text).
    """

    tab_renamed = pyqtSignal(int, str)

    def __init__(
        self,
        *,
        closable: bool = False,
        movable: bool = False,
        white_pane: bool = False,
        editable: bool = False,
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
        # Keep full labels and scroll on overflow (native chevrons) — don't elide.
        self.tabBar().setElideMode(Qt.TextElideMode.ElideNone)
        self.setUsesScrollButtons(True)
        self._closable = closable
        self.setMovable(movable)
        self._editor: _TabRenameEdit | None = None
        if editable:
            self.tabBarDoubleClicked.connect(self._begin_rename)
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

    # ------------------------------------------------------------------
    # Inline rename (when editable)
    # ------------------------------------------------------------------

    def _begin_rename(self, index: int) -> None:
        if index < 0 or self._editor is not None:
            return
        rect = self.tabBar().tabRect(index)
        if rect.isNull():
            return
        editor = _TabRenameEdit(self.tabText(index), self.tabBar())
        editor.setGeometry(rect)
        editor.selectAll()
        editor.done.connect(lambda text, ok, i=index: self._finish_rename(i, text, ok))
        self._editor = editor
        editor.show()
        editor.setFocus()

    def _finish_rename(self, index: int, text: str, commit: bool) -> None:
        editor, self._editor = self._editor, None
        if editor is not None:
            editor.deleteLater()
        # The consumer applies the name (the session resolves empty -> filename),
        # so it stays the single source of truth for the title.
        if commit and 0 <= index < self.count():
            self.tab_renamed.emit(index, text)
