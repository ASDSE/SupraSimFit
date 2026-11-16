"""The component layer: layout helpers and the custom-painted controls of the design.

QSS (:mod:`gui.design.stylesheet`) styles what Qt's widgets can express; every control
here is painted where it cannot — a menu chevron on the token grid, a selection bar, a
focus ring, a field, a slider — from the same tokens (:mod:`gui.design.tokens`) and
icons (:mod:`gui.design.icons`). Each control takes the resolved :class:`Theme` it is
drawn in.
"""

from __future__ import annotations

import math
import sys
from collections.abc import Callable
from dataclasses import dataclass
from html import escape
from typing import TYPE_CHECKING, NamedTuple

from PyQt6.QtCore import (
    QEvent,
    QObject,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTextBoundaryFinder,
    QTimer,
    QVariantAnimation,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QAction,
    QColor,
    QFont,
    QFontMetrics,
    QFontMetricsF,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QTextDocument,
    QTextDocumentFragment,
)
from PyQt6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from gui.design import icons
from gui.design.plot_theme import REPLICATE_ALPHA
from gui.design.tokens import DURATION, RADIUS, SIZE, Theme, font, space

if TYPE_CHECKING:
    import pyqtgraph as pg

#: The platform's window-button colours (close, minimise, zoom): drawn where a frameless
#: window paints its own title bar, so they are the platform's and not design tokens.
WINDOW_BUTTON_COLOURS = ('#FF5F57', '#FEBC2E', '#28C840')

#: Corner radius of a popover card and of a window of its own.
#: Superscript digits and minus back to plain text, so a value shown as ``2.9×10⁻⁵`` is typed as ``2.9e-5``.
_FROM_SUPER = str.maketrans('⁰¹²³⁴⁵⁶⁷⁸⁹⁻', '0123456789-')

#: Room a popover leaves around its card for the soft shadow, in px.
SHADOW = 12


# ── Window chrome ──────────────────────────────────────────────────────────────────

#: macOS: a window reaches up under a transparent title bar, which keeps the window controls.
MAC = sys.platform == 'darwin'


def hide_title_text(window: QWidget) -> None:
    """macOS: hide the title text the transparent title bar would draw over the toolbar.

    Qt has no call for it, so it is set on the native window (``NSWindow.titleVisibility``)
    through the Objective-C runtime. The title stays the window's name in the Window menu
    and Mission Control.
    """
    import ctypes
    import ctypes.util

    objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library('objc'))
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    get = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(('objc_msgSend', objc))
    set_long = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long)(('objc_msgSend', objc))
    ns_window = get(int(window.winId()), objc.sel_registerName(b'window'))
    set_long(ns_window, objc.sel_registerName(b'setTitleVisibility:'), 1)  # NSWindowTitleHidden


class TitleBarArea(QWidget):
    """A stretch of window chrome that moves the window when dragged and zooms it on a double-click.

    On macOS a window's toolbar (and the main window's sidebar top row) sits where the title bar would be, so
    their empty parts behave as the title bar does; elsewhere the system's title bar does.
    """

    def mousePressEvent(self, event) -> None:
        if MAC and event.button() == Qt.MouseButton.LeftButton:
            self.window().windowHandle().startSystemMove()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if MAC and event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            window.showNormal() if window.isMaximized() else window.showMaximized()
            return
        super().mouseDoubleClickEvent(event)


# ── Text and layout ────────────────────────────────────────────────────────────────


def label(text: str, role: str = 'body', tone: str | None = None, rich: bool = False) -> QLabel:
    """A QLabel in type role *role*; *tone* (``secondary``, ``tertiary``) sets its colour
    through the stylesheet, and *rich* reads *text* as HTML."""
    lbl = QLabel(text)
    lbl.setFont(font(role))
    if tone:
        lbl.setProperty('tone', tone)
    lbl.setTextFormat(Qt.TextFormat.RichText if rich else Qt.TextFormat.PlainText)
    return lbl


def copyable(lbl: QLabel) -> QLabel:
    """*lbl* made selectable with the mouse, so the result it shows can be copied (DESIGN.md §6)."""
    lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    lbl.setCursor(Qt.CursorShape.IBeamCursor)
    return lbl


def badge(text: str, tone: str = 'neutral') -> QLabel:
    """A pill beside a title: ``accent`` for the reported kind of result, ``neutral`` otherwise."""
    lbl = QLabel(text)
    lbl.setFont(font('label'))
    lbl.setProperty('role', 'badge')
    lbl.setProperty('tone', tone)
    lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return lbl


def hairline(vertical: bool = False) -> QFrame:
    """A 1-px divider in the ``border`` colour."""
    f = QFrame()
    f.setProperty('role', 'hairline')
    if vertical:
        f.setFixedWidth(1)
    else:
        f.setFixedHeight(1)
    return f


def _fill(lay: QHBoxLayout | QVBoxLayout, items: tuple) -> None:
    for it in items:
        if it is None:
            lay.addStretch(1)
        elif isinstance(it, int):
            lay.addSpacing(space(it))
        elif isinstance(it, QWidget):
            lay.addWidget(it)
        else:
            lay.addLayout(it)


def hbox(*items, spacing: int = 3, margins: tuple[int, int, int, int] = (0, 0, 0, 0)) -> QHBoxLayout:
    """A row of *items*: a widget or layout is added, an int is a spacing step, ``None`` a stretch.

    *spacing* and *margins* are steps of the spacing scale, never pixels.
    """
    lay = QHBoxLayout()
    lay.setSpacing(space(spacing))
    lay.setContentsMargins(*(space(m) for m in margins))
    _fill(lay, items)
    return lay


def vbox(*items, spacing: int = 3, margins: tuple[int, int, int, int] = (0, 0, 0, 0)) -> QVBoxLayout:
    """A column of *items*, read as in :func:`hbox`."""
    lay = QVBoxLayout()
    lay.setSpacing(space(spacing))
    lay.setContentsMargins(*(space(m) for m in margins))
    _fill(lay, items)
    return lay


def _rich_document(html: str, role: str, color: QColor) -> QTextDocument:
    doc = QTextDocument()
    doc.setDocumentMargin(0)
    doc.setDefaultFont(font(role))
    doc.setHtml(f'<span style="color:{color.name()}; white-space:nowrap">{html}</span>')
    return doc


def rich_width(html: str, role: str) -> float:
    """The width *html* takes on one line in type role *role*."""
    return _rich_document(html, role, QColor()).idealWidth()


def paint_rich(p: QPainter, rect: QRectF, html: str, role: str, color: QColor, right: bool = False) -> float:
    """Paint rich text (subscripts, superscripts) into *rect* on the baseline plain text
    centred in *rect* sits on, so rich and plain names line up; returns the drawn width."""
    doc = _rich_document(html, role, color)
    width = doc.idealWidth()
    fm = QFontMetrics(font(role))
    baseline = rect.top() + (rect.height() - fm.height()) / 2 + fm.ascent()
    block = doc.firstBlock()
    doc.documentLayout().blockBoundingRect(block)  # lays the block out
    line = block.layout().lineAt(0)
    x = rect.right() - width if right else rect.left()
    p.save()
    p.translate(x, baseline - (line.y() + line.ascent()))
    doc.drawContents(p)
    p.restore()
    return width


def _rounded(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def _focus_ring(p: QPainter, t: Theme, r: QRectF) -> None:
    """The keyboard-focus ring: 2 px accent, inside the control's edge."""
    p.setPen(QPen(t.q('accent'), 2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(r.adjusted(1, 1, -1, -1), RADIUS['control'] - 1, RADIUS['control'] - 1)


# ── Buttons ────────────────────────────────────────────────────────────────────────


class Button(QAbstractButton):
    """One painted button for the three variants the app needs.

    ``ghost`` is icon and label with no border until hover, ``icon`` a 28 × 28 icon
    button, ``primary`` an accent fill; a disabled button draws its icon and label in
    ``text-disabled`` — a disabled ``primary`` on ``bg-subtle`` in place of the accent — and
    takes no hover fill. *menu* says a click opens a menu, which a
    labelled button shows with a chevron. Painting keeps the icon-label gap, the menu
    chevron and the focus ring on the token grid. *checked* makes it a toggle,
    shown pressed.
    """

    def __init__(
        self, theme: Theme, variant: str, text: str = '', icon_name: str = '', menu: bool = False, checked: bool = False
    ):
        super().__init__()
        self.t, self.variant, self._text, self._icon, self._menu = theme, variant, text, icon_name, menu
        self.setCheckable(checked)
        self.setChecked(checked)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setFixedHeight(SIZE['control'])
        # The label is painted, so it is also the name a screen reader announces.
        self.setAccessibleName(text)
        self._font = font('body-strong' if variant == 'primary' else 'body')
        if variant == 'icon':
            self.setFixedWidth(SIZE['control'])
        else:
            fm = QFontMetrics(self._font)
            w = space(3) + (16 + space(2) if icon_name else 0) + fm.horizontalAdvance(text)
            w += (space(2) + 12 if menu else 0) + (space(4) if variant == 'primary' else space(3))
            self.setFixedWidth(w)

    @property
    def opens_menu(self) -> bool:
        """Whether a click opens a menu (*menu*): a labelled button draws its chevron."""
        return self._menu

    def set_text(self, text: str, icon_name: str | None = None) -> None:
        """Change the label (and the icon, *icon_name*) in place; the width stays, so a toolbar never shifts."""
        if self.accessibleName() == self._text:
            self.setAccessibleName(text)
        self._text = text
        if icon_name is not None:
            self._icon = icon_name
        self.update()

    def paintEvent(self, _):
        t = self.t
        h = SIZE['control']
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        bg = None
        on = self.isEnabled()
        if self.variant == 'primary':
            bg = t.q(('accent-hover' if self.underMouse() else 'accent') if on else 'bg-subtle')
        elif self.isChecked():
            bg = t.q('bg-subtle')
        elif self.underMouse() and on:
            bg = t.q('bg-hover')
        if bg is not None:
            p.fillPath(_rounded(r, RADIUS['control']), bg)
        fg = t.q('on-accent') if self.variant == 'primary' else t.q('text-primary')
        ic = t.q('on-accent') if self.variant == 'primary' else t.q('text-secondary')
        if not on:
            fg = ic = t.q('text-disabled')
        if self.variant == 'icon':
            icons.paint(p, self._icon, ic, (h - 16) / 2, (h - 16) / 2, 16)
        else:
            x = space(3)
            if self.variant == 'primary':  # centred when the button is wider than its content
                content = 16 + space(2) + QFontMetrics(self._font).horizontalAdvance(self._text)
                x = (r.width() - content) / 2
            if self._icon:
                size = 14 if self.variant == 'primary' else 16
                icons.paint(p, self._icon, ic, x, (h - size) / 2, size)
                x += 16 + space(2)
            p.setFont(self._font)
            p.setPen(fg)
            p.drawText(QRectF(x, 0, r.width() - x, h), Qt.AlignmentFlag.AlignVCenter, self._text)
            if self._menu:
                chevron = t.q('text-tertiary' if on else 'text-disabled')
                icons.paint(p, 'chevron-down', chevron, r.width() - space(3) - 12, (h - 12) / 2, 12, 2)
        if self.hasFocus():
            _focus_ring(p, t, r)
        p.end()


def tool_button(theme: Theme, text: str | None, icon_name: str, checked: bool = False, menu: bool = False) -> Button:
    """A toolbar or header button: ``ghost`` with a label, ``icon`` without one."""
    return Button(theme, 'ghost' if text else 'icon', text or '', icon_name, menu, checked)


def primary_button(theme: Theme, text: str, icon_name: str) -> Button:
    """The one primary action of a toolbar (Run fit, Run analysis)."""
    return Button(theme, 'primary', text, icon_name)


#: The key that turns the wheel over a plot into zoom: ⌘ on macOS, Ctrl on other platforms (Qt names both Control).
ZOOM_MODIFIER = Qt.KeyboardModifier.ControlModifier


class PlotNavigation(QObject):
    """Zoom and pan of interactive pyqtgraph plots, and the *Reset view* tool that frames them again (DESIGN.md §7).

    A drag pans the plot under the pointer; the wheel with :data:`ZOOM_MODIFIER`, or a
    pinch, zooms about the pointer. A wheel without the modifier passes on to what holds
    the plot, so a scrolling page scrolls under it. A double-click on a plot, or
    :attr:`tool`, resets: every plot goes back to its home view — auto-range, or the frame
    its own *home* sets. The tool is enabled only while a plot is off its home view.
    """

    def __init__(self, t: Theme, name: str):
        super().__init__()
        self.tool = tool_button(t, None, 'rotate')
        key = QKeySequence(ZOOM_MODIFIER.value).toString(QKeySequence.SequenceFormat.NativeText).rstrip('+')
        self.tool.setToolTip(f'Reset view (or double-click the plot). Zoom with {key} and scroll, or pinch.')
        self.tool.setAccessibleName(name)
        self.tool.clicked.connect(self.reset)
        self.plots: list[tuple[pg.PlotWidget, Callable[[], None] | None]] = []
        self.moved = False
        self.tool.setEnabled(False)

    def set_plots(self, plots: list[tuple[pg.PlotWidget, Callable[[], None] | None]]) -> None:
        """Navigate *plots*, each ``(plot widget, home)`` — *home* ``None`` for auto-range — from now on.

        Plots drawn again in place of the last ones, as a theme change draws them, open where
        the user left those; otherwise they open on their home views.
        """
        kept = [pw.getPlotItem().getViewBox().viewRange() for pw, _home in self.plots] if self.moved else None
        self.plots = list(plots)
        for pw, _home in self.plots:
            pw.viewport().installEventFilter(self)
            pw.getPlotItem().getViewBox().sigRangeChangedManually.connect(self._on_moved)
        if kept is None:
            self.reset()
            return
        for (pw, _home), (x_range, y_range) in zip(self.plots, kept, strict=True):
            pw.getPlotItem().getViewBox().setRange(xRange=x_range, yRange=y_range, padding=0)

    def reset(self) -> None:
        """Put every plot on its home view, and disable the tool until one is moved off it."""
        for pw, home in self.plots:
            if home is None:
                pw.getPlotItem().getViewBox().enableAutoRange()
            else:
                home()
        self.moved = False
        self.tool.setEnabled(False)

    def _on_moved(self, *_) -> None:
        self.moved = True
        self.tool.setEnabled(True)

    def eventFilter(self, viewport, event) -> bool:  # noqa: N802 — Qt's name
        kind = event.type()
        if kind == QEvent.Type.Wheel and not event.modifiers() & ZOOM_MODIFIER:
            event.ignore()  # handled here, so the plot leaves it; ignored, so Qt hands it to the page
            return True
        if kind == QEvent.Type.MouseButtonDblClick and event.button() == Qt.MouseButton.LeftButton:
            self.reset()
            return True
        if kind == QEvent.Type.NativeGesture and event.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
            (pw,) = (pw for pw, _home in self.plots if pw.viewport() is viewport)
            vb = pw.getPlotItem().getViewBox()
            factor = 1 / (1 + event.value())
            vb.scaleBy((factor, factor), vb.mapSceneToView(pw.mapToScene(event.position().toPoint())))
            self._on_moved()
            return True
        return False


def link_button(text: str) -> QPushButton:
    """An inline command in accent text, styled by the stylesheet's ``link`` role."""
    b = QPushButton(text)
    b.setProperty('role', 'link')
    b.setFont(font('body'))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    return b


class OutlineButton(QAbstractButton):
    """A secondary command: control height, 1-px ``border-strong`` outline, label in body-strong."""

    def __init__(self, t: Theme, text: str, icon_name: str = ''):
        super().__init__()
        self.t, self.label, self.icon = t, text, icon_name
        self.setAccessibleName(text)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        fm = QFontMetrics(font('body-strong'))
        width = fm.horizontalAdvance(text) + 2 * space(4) + (16 + space(2) if icon_name else 0)
        self.setFixedSize(width, SIZE['control'])

    def paintEvent(self, _):
        t = self.t
        h = SIZE['control']
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = _rounded(r, RADIUS['control'])
        p.fillPath(path, t.q('bg-raised' if t.dark else 'bg-surface'))
        if self.underMouse() and self.isEnabled():
            p.fillPath(path, t.q('bg-hover'))
        p.setPen(QPen(t.q('border-strong'), 1))
        p.drawPath(path)
        x = space(4)
        tone = 'text-primary' if self.isEnabled() else 'text-disabled'
        if self.icon:
            icons.paint(p, self.icon, t.q('text-secondary' if self.isEnabled() else 'text-disabled'), x, (h - 16) / 2)
            x += 16 + space(2)
        p.setFont(font('body-strong'))
        p.setPen(t.q(tone))
        p.drawText(QRectF(x, 0, r.width() - x, h), Qt.AlignmentFlag.AlignVCenter, self.label)
        if self.hasFocus():
            _focus_ring(p, t, QRectF(self.rect()))
        p.end()


# ── Window chrome and navigation ───────────────────────────────────────────────────


class TrafficLights(QWidget):
    """The window buttons of a frameless window, which draws its own title bar.

    *active* names the buttons drawn in the platform's colours (0 close, 1 minimise,
    2 zoom); the others take ``traffic``, as for an inactive window or a fixed-size
    window that cannot zoom. With *active* empty the widget can be laid over another
    window's buttons to show that window inactive.
    """

    def __init__(self, theme: Theme, active: tuple[int, ...] = (0, 1, 2)):
        super().__init__()
        self.t, self.active = theme, active
        self.setFixedSize(60, 14)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        for i, colour in enumerate(WINDOW_BUTTON_COLOURS):
            if i in self.active:
                p.setBrush(QColor(colour))
                p.drawEllipse(QRectF(i * 20 + 1, 1, 12, 12))
            else:
                p.setBrush(self.t.q('traffic'))
                p.drawEllipse(QRectF(i * 20 + 0.5, 0.5, 13, 13))
        p.end()


class Icon(QWidget):
    """An icon in a text token, painted each time so it follows the theme: 16 px unless *size* says."""

    def __init__(self, t: Theme, name: str, tone: str = 'text-secondary', size: int = 16):
        super().__init__()
        self.t, self.name, self.tone, self.size = t, name, tone, size
        self.setFixedSize(size, size)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        icons.paint(p, self.name, self.t.q(self.tone), 0, 0, self.size)
        p.end()


class StatusDot(QWidget):
    """An 8-px dot in token *tone*: what the status bar's left-hand message is about."""

    def __init__(self, t: Theme, tone: str):
        super().__init__()
        self.t, self.tone = t, tone
        self.setFixedSize(8, 8)

    def set_tone(self, tone: str) -> None:
        """Draw the dot in token *tone*."""
        self.tone = tone
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.t.q(self.tone))
        p.drawEllipse(QRectF(0, 0, 8, 8))
        p.end()


def paint_status_glyph(p: QPainter, t: Theme, status: str, cx: float, cy: float, progress: float = 0.0) -> None:
    """The trailing state glyph of a navigation item or a session, centred on (*cx*, *cy*).

    ``done`` is a check, ``warning`` a warning dot, ``stale`` (out of date) a hollow
    ring, ``running`` an accent arc of *progress* (0–1); an empty status draws nothing.
    """
    if status == 'done':
        icons.paint(p, 'check', t.q('text-tertiary'), cx - 6, cy - 6, 12, 2.2)
    elif status == 'warning':
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(t.q('warning'))
        p.drawEllipse(QPointF(cx, cy), 3.5, 3.5)
    elif status == 'stale':
        p.setPen(QPen(t.q('text-tertiary'), 1.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), 3, 3)
    elif status == 'running':
        p.setPen(QPen(t.q('border' if t.dark else 'bg-subtle'), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), 4.5, 4.5)
        p.setPen(QPen(t.q('accent'), 2, cap=Qt.PenCapStyle.RoundCap))
        p.drawArc(QRectF(cx - 4.5, cy - 4.5, 9, 9), 90 * 16, int(-360 * 16 * progress))


class NavItem(QAbstractButton):
    """A sidebar row: icon, label and the trailing status glyph of :func:`paint_status_glyph`.

    Painted, so the selection (fill and a 3-px accent bar) and keyboard focus are
    distinct states.
    """

    def __init__(self, theme: Theme, text: str, icon_name: str, status: str = '', selected: bool = False):
        super().__init__()
        self.t, self._text, self._icon, self._status, self._progress = theme, text, icon_name, status, 0.0
        self.setAccessibleName(text)
        self.setCheckable(True)
        self.setChecked(selected)
        self.setFixedHeight(SIZE['nav-item'])
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    #: Where the label starts, past the icon, and the room the status glyph keeps at the right.
    TEXT_X, GLYPH_W = space(3) + 16 + space(3), 24

    def minimumSizeHint(self) -> QSize:
        label = QFontMetrics(font('body-strong')).horizontalAdvance(self._text)  # the selected weight
        return QSize(self.TEXT_X + label + self.GLYPH_W, SIZE['nav-item'])

    def sizeHint(self) -> QSize:
        return self.minimumSizeHint()

    def set_status(self, status: str, progress: float = 0.0) -> None:
        """Draw the trailing glyph of *status* (see :func:`paint_status_glyph`)."""
        if (status, progress) != (self._status, self._progress):
            self._status, self._progress = status, progress
            self.update()

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        sel = self.isChecked()
        if sel:
            p.fillPath(_rounded(r, RADIUS['control']), t.q('bg-selected'))
            p.fillPath(_rounded(QRectF(0, 7, 3, r.height() - 14), 1.5), t.q('accent'))
        elif self.underMouse():
            p.fillPath(_rounded(r, RADIUS['control']), t.q('bg-hover'))
        icons.paint(p, self._icon, t.q('accent' if sel else 'text-secondary'), space(3), (r.height() - 16) / 2, 16)
        p.setFont(font('body-strong' if sel else 'body'))
        p.setPen(t.q('text-primary'))
        text_w = r.width() - self.TEXT_X - self.GLYPH_W
        p.drawText(QRectF(self.TEXT_X, 0, text_w, r.height()), Qt.AlignmentFlag.AlignVCenter, self._text)
        paint_status_glyph(p, t, self._status, r.width() - 14, r.height() / 2, self._progress)
        if self.hasFocus():  # keyboard focus only (TabFocus policy)
            _focus_ring(p, t, r)
        p.end()


class SessionSwitcher(QAbstractButton):
    """The session on screen, at the top of the sidebar; a click opens :class:`SessionPopover`.

    The trailing pill counts the open sessions and carries an accent dot while another
    session is busy (*busy*). *open_* draws it with the popover open.
    """

    #: A click opens a menu, the session popover.
    opens_menu = True

    def __init__(self, theme: Theme, name: str, detail: str, count: int = 1, busy: int = 0, open_: bool = False):
        super().__init__()
        self.t, self._name, self._detail, self._count, self._busy = theme, name, detail, count, busy
        self.setCheckable(True)
        self.setChecked(open_)
        self.setFixedHeight(SIZE['switcher'])
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName('Open sessions')

    def set_session(self, name: str, detail: str, count: int, busy: int) -> None:
        """Show the session on screen (*name*, *detail*), *count* open sessions and *busy* others running."""
        self._name, self._detail, self._count, self._busy = name, detail, count, busy
        self.setAccessibleDescription(f'{name}, {detail}; {count} open')
        self.updateGeometry()
        self.update()

    #: Where the name and detail start, past the session tile.
    TEXT_X = 44

    def _pill_width(self) -> int:
        """The width of the pill counting the open sessions; 0 for one session, which has none."""
        return QFontMetrics(font('small-number')).horizontalAdvance(str(self._count)) + 12 if self._count > 1 else 0

    def _right(self) -> int:
        """The room right of the text: the chevrons, and the pill where there is one."""
        pill = self._pill_width()
        return 28 + (pill + 6 if pill else 0)

    def minimumSizeHint(self) -> QSize:
        # The name gives way to an ellipsis; the detail is shown whole.
        text = max(
            QFontMetrics(font('small')).horizontalAdvance(self._detail),
            QFontMetrics(font('body-strong')).horizontalAdvance('…'),
        )
        return QSize(self.TEXT_X + text + self._right(), SIZE['switcher'])

    def sizeHint(self) -> QSize:
        return self.minimumSizeHint()

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        path = _rounded(r.adjusted(0.5, 0.5, -0.5, -0.5), RADIUS['surface'])
        p.fillPath(path, t.q('bg-surface'))
        p.setPen(QPen(t.q('accent' if self.isChecked() else 'border'), 1))
        p.drawPath(path)
        tile = SIZE['control']
        p.fillPath(_rounded(QRectF(space(3), space(3), tile, tile), RADIUS['control']), t.q('accent-subtle'))
        icons.paint(p, 'fit', t.q('accent'), 14, 14, 16)
        right = self._right()
        if self._count > 1:
            p.setFont(font('small-number'))
            txt = str(self._count)
            pw = self._pill_width()
            pill = QRectF(r.width() - 28 - pw, 13, pw, SIZE['badge'])
            p.fillPath(_rounded(pill, SIZE['badge'] / 2), t.q('bg-subtle'))
            p.setPen(t.q('text-secondary'))
            p.drawText(pill, Qt.AlignmentFlag.AlignCenter, txt)
            if self._busy:
                p.setPen(QPen(t.q('bg-surface'), 2))
                p.setBrush(t.q('accent'))
                p.drawEllipse(QPointF(pill.right() - 1, pill.top() + 1), 4, 4)
        p.setPen(t.q('text-primary'))
        p.setFont(font('body-strong'))
        x, text_w = self.TEXT_X, r.width() - self.TEXT_X - right
        name = p.fontMetrics().elidedText(self._name, Qt.TextElideMode.ElideRight, int(text_w))
        p.drawText(QRectF(x, 6, text_w, 17), Qt.AlignmentFlag.AlignVCenter, name)
        p.setPen(t.q('text-secondary'))
        p.setFont(font('small'))
        p.drawText(QRectF(x, 22, text_w, 16), Qt.AlignmentFlag.AlignVCenter, self._detail)
        icons.paint(p, 'updown', t.q('text-tertiary'), r.width() - 24, 14, 16)
        p.end()


class ProgressLine(QWidget):
    """The thin accent line at the top of a canvas while its session runs.

    :meth:`set_progress` with a fraction fills it that far; with ``None`` a short
    stretch sweeps across, for work that cannot be counted yet. :meth:`stop` empties
    it. It keeps its 2-px height while idle, so the canvas never shifts.
    """

    HEIGHT = 2

    def __init__(self, theme: Theme):
        super().__init__()
        self.t = theme
        self.setFixedHeight(self.HEIGHT)
        self._fraction: float | None = None
        self._running = False
        self._sweep = QVariantAnimation(self)
        self._sweep.setStartValue(0.0)
        self._sweep.setEndValue(1.0)
        self._sweep.setDuration(1400)
        self._sweep.setLoopCount(-1)
        self._sweep.valueChanged.connect(lambda _v: self.update())

    def set_progress(self, fraction: float | None) -> None:
        """Show work running, *fraction* done (0–1), or uncounted with ``None``."""
        self._running, self._fraction = True, fraction
        if fraction is None:
            if self._sweep.state() != QVariantAnimation.State.Running:
                self._sweep.start()
        else:
            self._sweep.stop()
        self.update()

    def stop(self) -> None:
        """Show no work running."""
        self._running = False
        self._sweep.stop()
        self.update()

    def is_running(self) -> bool:
        return self._running

    def minimumSizeHint(self) -> QSize:
        return QSize(0, self.HEIGHT)

    def sizeHint(self) -> QSize:
        return self.minimumSizeHint()

    def paintEvent(self, _):
        if not self._running:
            return
        p = QPainter(self)
        w = self.width()
        if self._fraction is None:
            x = (self._sweep.currentValue() or 0.0) * w * 1.3 - w * 0.3
            p.fillRect(QRectF(x, 0, w * 0.3, self.HEIGHT), self.t.q('accent'))
        else:
            p.fillRect(QRectF(0, 0, w * max(0.0, min(1.0, self._fraction)), self.HEIGHT), self.t.q('accent'))
        p.end()


class FileCard(QAbstractButton):
    """The sidebar's foot: the data behind the session on screen; a click opens Measurements."""

    def __init__(self, theme: Theme, name: str = '', detail: str = ''):
        super().__init__()
        self.t = theme
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip('Data in this session. Click to open Measurements.')
        self.setFixedHeight(SIZE['switcher'])
        self.set_file(name, detail)

    def set_file(self, name: str, detail: str) -> None:
        """Show file *name* (``GDA_run1.txt + 2 more``) and *detail* (``GDA · 3 replicates × 24 points``)."""
        self._name, self._detail = name, detail
        self.setAccessibleName(f'Data: {name}')
        self.setAccessibleDescription(detail)
        self.update()

    #: Where the name and detail start, past the file icon.
    TEXT_X = space(3) + 16 + space(3)

    def minimumSizeHint(self) -> QSize:
        # Both lines give way to an ellipsis where the sidebar is narrower than they are.
        ellipsis = QFontMetrics(font('body-strong')).horizontalAdvance('…')
        return QSize(self.TEXT_X + ellipsis + space(3), SIZE['switcher'])

    def sizeHint(self) -> QSize:
        width = max(
            QFontMetrics(font('body-strong')).horizontalAdvance(self._name),
            QFontMetrics(font('small')).horizontalAdvance(self._detail),
        )
        return QSize(self.TEXT_X + width + space(3), SIZE['switcher'])

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        if self.underMouse():
            p.fillPath(_rounded(r, RADIUS['control']), t.q('bg-hover'))
        icons.paint(p, 'file', t.q('text-secondary'), space(3), space(3), 16)
        x = self.TEXT_X
        width = int(r.width() - x - space(3))
        p.setFont(font('body-strong'))
        p.setPen(t.q('text-primary'))
        name = p.fontMetrics().elidedText(self._name, Qt.TextElideMode.ElideMiddle, width)
        p.drawText(QRectF(x, space(2), width, 18), Qt.AlignmentFlag.AlignVCenter, name)
        p.setFont(font('small'))
        p.setPen(t.q('text-secondary'))
        detail = p.fontMetrics().elidedText(self._detail, Qt.TextElideMode.ElideRight, width)
        p.drawText(QRectF(x, space(2) + 18, width, 16), Qt.AlignmentFlag.AlignVCenter, detail)
        if self.hasFocus():
            _focus_ring(p, t, r)
        p.end()


# ── Popovers and menus ─────────────────────────────────────────────────────────────


def paint_popover(p: QPainter, t: Theme, card: QRectF) -> None:
    """A popover's raised card with its soft shadow: stacked translucent rounded
    rectangles, offset down, under a ``bg-raised`` fill and a 1-px ``border``."""
    for i in range(10, 0, -1):
        alpha = (0.07 if t.dark else 0.018) * (11 - i) / 10
        shadow = card.adjusted(-i, -i + 4, i, i + 4)
        p.fillPath(_rounded(shadow, RADIUS['popover'] + i), t.q('shadow', int(255 * alpha) / 255))
    path = _rounded(card, RADIUS['popover'])
    p.fillPath(path, t.q('bg-raised'))
    p.setPen(QPen(t.q('border'), 1))
    p.drawPath(path)


def _menu_separator(p: QPainter, t: Theme, x0: float, y: float, w: float) -> float:
    p.fillRect(QRectF(x0 + 8, y + 4, w - 16, 1), t.q('border'))
    return y + 9


def shortcut_text(action: QAction) -> str:
    """*action*'s shortcut in the platform's own keys (``⌘O`` on macOS, ``Ctrl+O`` elsewhere); ``''`` for none."""
    return action.shortcut().toString(QKeySequence.SequenceFormat.NativeText)


def menu_html(action: QAction) -> str:
    """The label of a menu row as rich text: the action's ``design_html`` property, else its text escaped."""
    return action.property('design_html') or escape(action.text())


class MenuRow(NamedTuple):
    """One row of a menu, in the widget's coordinates: the row and its check, icon, label and shortcut columns."""

    rect: QRectF
    check: QRectF
    icon: QRectF
    label: QRectF
    key: QRectF
    action: QAction


@dataclass(frozen=True)
class MenuColumns:
    """The columns of a menu's rows — check mark, icon, label, shortcut — measured from what the rows hold.

    A column no row uses takes no room: the check column only where a row can be checked,
    the icon column only where a row has an icon (``design_icon``), the shortcut column
    only where a row has a shortcut. The label column is as wide as the widest label in
    type role *role*. Sizing a menu (:attr:`width`) and painting its rows (:meth:`row`)
    read the same columns, so every label gets the room its text takes.
    """

    role: str
    check: float
    icon: float
    label: float
    key: float

    @classmethod
    def of(cls, actions: list, role: str = 'body') -> MenuColumns:
        """The columns of the rows of *actions* (``None`` a separator), labels in type role *role*."""
        rows = [a for a in actions if a is not None]
        keys = QFontMetricsF(font('small'))
        return cls(
            role=role,
            check=SIZE['menu-check'] + space(2) if any(a.isCheckable() for a in rows) else 0,
            icon=SIZE['menu-icon'] + space(3) if any(a.property('design_icon') for a in rows) else 0,
            label=math.ceil(max((rich_width(menu_html(a), role) for a in rows), default=0)),
            key=math.ceil(max((keys.horizontalAdvance(shortcut_text(a)) for a in rows), default=0)),
        )

    @property
    def width(self) -> float:
        """The width of a row that shows every column in full."""
        return space(3) + self.check + self.icon + self.label + (space(5) + self.key if self.key else 0) + space(3)

    def row(self, rect: QRectF, action: QAction) -> MenuRow:
        """The columns of *action*'s row *rect*; the label takes what the row has beside the others."""
        x, h = rect.left() + space(3), rect.height()
        label_x = x + self.check + self.icon
        key_x = rect.right() - space(3) - self.key
        label_right = key_x - space(5) if self.key else rect.right() - space(3)
        return MenuRow(
            rect,
            QRectF(x, rect.top() + (h - SIZE['menu-check']) / 2, SIZE['menu-check'], SIZE['menu-check']),
            QRectF(x + self.check, rect.top() + (h - SIZE['menu-icon']) / 2, SIZE['menu-icon'], SIZE['menu-icon']),
            QRectF(label_x, rect.top(), label_right - label_x, h),
            QRectF(key_x, rect.top(), self.key, h),
            action,
        )


def _menu_command(p: QPainter, t: Theme, row: MenuRow, role: str) -> None:
    """Paint *row*: its check mark while its action is checked, its icon, its label and its shortcut."""
    action = row.action
    on = action.isEnabled()
    if action.isChecked():
        icons.paint(
            p,
            'check',
            t.q('accent' if on else 'text-disabled'),
            row.check.left(),
            row.check.top(),
            SIZE['menu-check'],
            2,
        )
    ic = action.property('design_icon')
    if ic:
        icons.paint(
            p, ic, t.q('text-secondary' if on else 'text-disabled'), row.icon.left(), row.icon.top(), SIZE['menu-icon']
        )
    paint_rich(p, row.label, menu_html(action), role, t.q('text-primary' if on else 'text-disabled'))
    key = shortcut_text(action)
    if key:
        p.setFont(font('small'))
        p.setPen(t.q('text-tertiary' if on else 'text-disabled'))
        p.drawText(row.key, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, key)


class _Popover(QWidget):
    """What every popover shares: it floats over its window, follows the pointer and the keys, scrolls, and closes.

    A popover is a child of the window it opens in, drawn with its shadow inside its own
    rectangle. A subclass sizes it to its whole card with :meth:`_size_card`; :meth:`popup`
    shows it below an anchor, or above it where the window has more room there, its card
    cut to the room the window has and scrolled (wheel, arrow keys) where its rows need
    more. A press outside it, Escape, or the window losing focus or changing size closes
    it, and :attr:`closed` says so. Subclasses lay out their rows from :meth:`_top`, where
    the card's content starts as scrolled, in :meth:`_rows` — ``(rect, enabled)`` per row
    that can be chosen — and act on one in :meth:`_activate`. *hover* draws a row as under
    the pointer: the row the keys start from, and in a still picture of the popover.
    """

    closed = pyqtSignal()

    #: The room between a popover's card and the window's edges.
    GAP = space(1)
    #: The room between a popover's card and its anchor: the widget starts 2 px past the anchor, its card the
    #: shadow's room (less the shadow's 4-px drop) further in.
    ANCHOR_GAP = 2 + SHADOW - 4

    def __init__(self, t: Theme, parent: QWidget, hover: int | None = None):
        super().__init__(parent)
        self.t, self.hover = t, hover
        self._anchor: QWidget | None = None
        self._card_h = 0.0
        self._scroll = 0.0
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # Layout -------------------------------------------------------------------
    def _rows(self) -> list[tuple[QRectF, bool]]:
        raise NotImplementedError

    def _activate(self, index: int) -> None:
        raise NotImplementedError

    def _size_card(self, width: float, height: float) -> None:
        """Size the popover to a card of *width* × *height*, its whole content, plus the shadow's room."""
        self._card_h = height
        self.setFixedSize(math.ceil(width) + 2 * SHADOW, math.ceil(height) + 2 * SHADOW)

    def _row_at(self, pos: QPointF) -> int | None:
        if not self._card().contains(pos):
            return None
        for i, (rect, on) in enumerate(self._rows()):
            if on and rect.contains(pos):
                return i
        return None

    def _card(self) -> QRectF:
        """The card as shown, in the widget's coordinates: all of it, or what the window has room for."""
        return QRectF(SHADOW, SHADOW - 4, self.width() - 2 * SHADOW, self.height() - 2 * SHADOW)

    def _top(self) -> float:
        """Where the card's content starts, scrolled."""
        return self._card().top() - self._scroll

    def _scroll_to(self, offset: float) -> None:
        self._scroll = max(0.0, min(offset, self._card_h - self._card().height()))
        self.update()

    def _reveal(self, index: int) -> None:
        """Scroll row *index* fully into the card."""
        rect, card = self._rows()[index][0], self._card()
        if rect.top() < card.top():
            self._scroll_to(self._scroll - (card.top() - rect.top()))
        elif rect.bottom() > card.bottom():
            self._scroll_to(self._scroll + (rect.bottom() - card.bottom()))

    # Showing and closing -------------------------------------------------------
    def popup(self, anchor: QWidget, right: bool = False) -> None:
        """Show the popover under *anchor*, or over it where the window has more room above; its card's left
        edge on the anchor's (or right edge, *right*), and cut to the window's height where it is taller."""
        self._anchor = anchor
        window = self.parentWidget()
        top_left = anchor.mapTo(window, anchor.rect().topLeft())
        below = window.height() - self.GAP - (top_left.y() + anchor.height() + self.ANCHOR_GAP)
        above = top_left.y() - self.ANCHOR_GAP - self.GAP
        down = self._card_h <= below or below >= above
        card_h = min(self._card_h, below if down else above)
        self.setFixedHeight(math.floor(card_h) + 2 * SHADOW)
        lift = SHADOW - 4  # the card's top in the widget
        card_top = top_left.y() + anchor.height() + self.ANCHOR_GAP if down else top_left.y() - self.ANCHOR_GAP - card_h
        x = top_left.x() + (anchor.width() - self.width() + SHADOW if right else -SHADOW)
        self.move(max(0, min(x, window.width() - self.width())), round(card_top - lift))
        self._scroll_to(0)
        if self.hover is not None:
            self._reveal(self.hover)
        self.show()
        self.raise_()
        self.setFocus(Qt.FocusReason.PopupFocusReason)
        QApplication.instance().installEventFilter(self)

    def close_popover(self) -> None:
        """Close the popover and let it go."""
        if not self.isVisible():
            return
        QApplication.instance().removeEventFilter(self)
        self.hide()
        self.closed.emit()
        self.deleteLater()

    def eventFilter(self, obj, event) -> bool:  # type: ignore[override]
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress and isinstance(obj, QWidget) and obj.window() is self.window():
            inside = self.rect().contains(self.mapFromGlobal(event.globalPosition().toPoint()))
            if not inside and not self._is_own(obj):
                on_anchor = self._anchor is not None and (obj is self._anchor or self._anchor.isAncestorOf(obj))
                self.close_popover()
                return on_anchor  # the anchor's click would open it again
        elif kind == QEvent.Type.WindowDeactivate and obj is self.window():
            self.close_popover()
        elif kind == QEvent.Type.Resize and obj is self.parentWidget():
            self.close_popover()
        return False

    def _is_own(self, obj: QWidget) -> bool:
        return obj is self or self.isAncestorOf(obj)

    # Pointer and keys ----------------------------------------------------------
    def mouseMoveEvent(self, event) -> None:
        hover = self._row_at(event.position())
        if hover != self.hover:
            self.hover = hover
            self.update()

    def leaveEvent(self, _event) -> None:
        self.hover = None
        self.update()

    def wheelEvent(self, event) -> None:
        step = event.pixelDelta().y() or event.angleDelta().y() / 120 * SIZE['menu-item']
        self._scroll_to(self._scroll - step)
        self.hover = self._row_at(event.position())

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            index = self._row_at(event.position())
            if index is not None:
                self._activate(index)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.close_popover()
        elif key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            self._step(1 if key == Qt.Key.Key_Down else -1)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space) and self.hover is not None:
            self._activate(self.hover)
        else:
            super().keyPressEvent(event)

    def _step(self, direction: int) -> None:
        rows = self._rows()
        enabled = [i for i, (_rect, on) in enumerate(rows) if on]
        if not enabled:
            return
        if self.hover not in enabled:
            self.hover = enabled[0 if direction > 0 else -1]
        else:
            self.hover = enabled[(enabled.index(self.hover) + direction) % len(enabled)]
        self._reveal(self.hover)
        self.update()


class PopoverMenu(_Popover):
    """A menu of commands, or of choices, in a popover card, with an optional quiet footnote under them.

    *actions* are the rows, ``None`` a separator. Each row draws its action's check mark
    while it is checked, its icon (the ``design_icon`` property, a name in
    :mod:`gui.design.icons`), its label — the ``design_html`` property where it is rich
    text, else its text — and its shortcut, on the :class:`MenuColumns` its rows need; a
    row is drawn quiet and cannot be chosen while its action is disabled. Choosing a row
    closes the menu and triggers its action. A menu of choices — every row checkable — opens
    on its checked row, unless *hover* names another. The card is as wide as its widest row, and
    at least *least_width* (a choice menu is as wide as its field); *role* is the type
    role of the labels. *note* is the footnote, wrapped to the card. The card's top-left
    sits at (``SHADOW``, ``SHADOW - 4``).
    """

    PAD = 6

    def __init__(
        self,
        t: Theme,
        parent: QWidget,
        actions: list,
        note: str = '',
        hover: int | None = None,
        role: str = 'body',
        least_width: float = 0,
    ):
        choices = [a for a in actions if a is not None]
        if hover is None and choices and all(a.isCheckable() for a in choices):
            hover = next((i for i, a in enumerate(choices) if a.isChecked()), None)
        super().__init__(t, parent, hover)
        self.actions_, self.note = actions, note
        self.columns = MenuColumns.of(actions, role)
        self.card_w = max(least_width, self.columns.width + 2 * self.PAD)
        rows = sum(9 if a is None else SIZE['menu-item'] for a in actions)
        note_h = 9 + self._note_h() + space(3) if note else 0
        self._size_card(self.card_w, self.PAD + rows + note_h + self.PAD)
        self.setAccessibleName('Menu')

    def _note_h(self) -> int:
        fm = QFontMetrics(font('small'))
        w = int(self.card_w) - 2 * self.PAD - 2 * space(3)
        return fm.boundingRect(0, 0, w, 200, Qt.TextFlag.TextWordWrap, self.note).height()

    def _layout(self) -> tuple[list[MenuRow], list[float], float]:
        card = self._card()
        x0, w = card.left() + self.PAD, card.width() - 2 * self.PAD
        y = self._top() + self.PAD
        rows, separators = [], []
        for a in self.actions_:
            if a is None:
                separators.append(y)
                y += 9
            else:
                rows.append(self.columns.row(QRectF(x0, y, w, SIZE['menu-item']), a))
                y += SIZE['menu-item']
        return rows, separators, y

    def menu_rows(self) -> list[MenuRow]:
        """The rows as laid out and painted, in the widget's coordinates, scrolled."""
        return self._layout()[0]

    def _rows(self) -> list[tuple[QRectF, bool]]:
        return [(row.rect, row.action.isEnabled()) for row in self.menu_rows()]

    def _activate(self, index: int) -> None:
        action = self.menu_rows()[index].action
        self.close_popover()
        action.trigger()

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = self._card()
        paint_popover(p, t, card)
        p.setClipPath(_rounded(card, RADIUS['popover']))
        rows, separators, y = self._layout()
        x0, w = card.left() + self.PAD, card.width() - 2 * self.PAD
        for sy in separators:
            _menu_separator(p, t, x0, sy, w)
        for k, row in enumerate(rows):
            if k == self.hover and row.action.isEnabled():
                p.fillPath(_rounded(row.rect, RADIUS['control']), t.q('bg-hover'))
            _menu_command(p, t, row, self.columns.role)
        if self.note:
            y = _menu_separator(p, t, x0, y, w) + space(2)
            p.setFont(font('small'))
            p.setPen(t.q('text-tertiary'))
            p.drawText(
                QRectF(x0 + space(3), y, w - 2 * space(3), self._note_h()),
                Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft,
                self.note,
            )
        p.end()


class SessionPopover(_Popover):
    """The session switcher open: every open session with its state, then the session commands.

    *sessions* are dicts with ``name``, ``detail``, ``state`` (``warning``, ``running``,
    ``stale``, ``done`` or ``''``), ``status`` (the state in words, right of the name)
    and, while running, ``progress`` (0–1); *current* is the index of the session on
    screen. *commands* are actions, ``None`` a separator, laid out on the :class:`MenuColumns`
    of every menu; the card is *width* wide, or wider where a command needs it. Choosing a session emits
    :attr:`session_chosen`; double-clicking its name edits it in place, and Return
    emits :attr:`renamed` with the new name.
    """

    session_chosen = pyqtSignal(int)
    renamed = pyqtSignal(int, str)

    PAD = 6
    ROW_H = 52
    HEAD_H = 28

    def __init__(
        self,
        t: Theme,
        parent: QWidget,
        sessions: list[dict],
        commands: list,
        current: int = 0,
        width: int = 340,
        title: str = 'Open sessions',
        title_hint: str = '',
        hover: int | None = None,
    ):
        super().__init__(t, parent, hover)
        self.sessions, self.commands, self.current = sessions, commands, current
        self.title, self.title_hint = title, title_hint
        self._editor: QLineEdit | None = None
        self.columns = MenuColumns.of(commands)
        self.card_w = max(width, self.columns.width + 2 * self.PAD)
        h = self.PAD + self.HEAD_H + len(sessions) * self.ROW_H + 9
        h += sum(9 if c is None else SIZE['menu-item'] for c in commands) + self.PAD + space(3)
        self._size_card(self.card_w, h)
        self.setAccessibleName('Open sessions')

    def _layout(self) -> tuple[list[QRectF], list[MenuRow], list[float]]:
        card = self._card()
        x0, w = card.left() + self.PAD, card.width() - 2 * self.PAD
        y = self._top() + self.PAD + self.HEAD_H
        session_rows = []
        for _ in self.sessions:
            session_rows.append(QRectF(x0, y, w, self.ROW_H))
            y += self.ROW_H
        separators = [y]
        y += 9
        commands = []
        for c in self.commands:
            if c is None:
                separators.append(y)
                y += 9
            else:
                commands.append(self.columns.row(QRectF(x0, y, w, SIZE['menu-item']), c))
                y += SIZE['menu-item']
        return session_rows, commands, separators

    def menu_rows(self) -> list[MenuRow]:
        """The command rows as laid out and painted, in the widget's coordinates, scrolled."""
        return self._layout()[1]

    def _rows(self) -> list[tuple[QRectF, bool]]:
        sessions, commands, _ = self._layout()
        return [(r, True) for r in sessions] + [(row.rect, row.action.isEnabled()) for row in commands]

    def _activate(self, index: int) -> None:
        sessions, commands, _ = self._layout()
        if index < len(sessions):
            self.close_popover()
            self.session_chosen.emit(index)
            return
        action = commands[index - len(sessions)].action
        self.close_popover()
        action.trigger()

    def _name_rect(self, row: QRectF) -> QRectF:
        return QRectF(row.left() + 46, row.top() + 8, row.width() - 120, 18)

    def mouseDoubleClickEvent(self, event) -> None:
        sessions = self._layout()[0]
        for i, row in enumerate(sessions):
            if row.contains(event.position()):
                self._edit_name(i, row)
                return

    def _edit_name(self, index: int, row: QRectF) -> None:
        editor = QLineEdit(self.sessions[index]['name'], self)
        editor.setFont(font('body-strong'))
        editor.setAccessibleName('Session name')
        rect = self._name_rect(row).adjusted(-space(2), -space(1), space(2), space(1)).toRect()
        editor.setGeometry(rect)
        editor.selectAll()
        editor.show()
        editor.setFocus()
        self._editor = editor

        def commit() -> None:
            name = editor.text().strip()
            self._editor = None
            editor.deleteLater()
            self.setFocus()
            if name and name != self.sessions[index]['name']:
                self.sessions[index]['name'] = name
                self.renamed.emit(index, name)
            self.update()

        editor.returnPressed.connect(commit)
        editor.editingFinished.connect(lambda: self._editor is editor and commit())

    def keyPressEvent(self, event) -> None:
        if self._editor is not None and event.key() == Qt.Key.Key_Escape:
            self._editor.deleteLater()
            self._editor = None
            self.setFocus()
            return
        super().keyPressEvent(event)

    def _is_own(self, obj: QWidget) -> bool:
        return super()._is_own(obj) or obj is self._editor

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = self._card()
        paint_popover(p, t, card)
        p.setClipPath(_rounded(card, RADIUS['popover']))
        sessions, commands, separators = self._layout()
        x0, w = card.left() + self.PAD, card.width() - 2 * self.PAD
        head = QRectF(x0 + 8, self._top() + self.PAD, w - 16, self.HEAD_H)
        p.setFont(font('overline'))
        p.setPen(t.q('text-tertiary'))
        p.drawText(head, Qt.AlignmentFlag.AlignVCenter, self.title)
        p.setFont(font('small'))
        p.drawText(head, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, self.title_hint)
        tile = SIZE['control']
        for i, (s, r) in enumerate(zip(self.sessions, sessions)):
            current = i == self.current
            if current:
                p.fillPath(_rounded(r, RADIUS['control']), t.q('bg-selected'))
            elif i == self.hover:
                p.fillPath(_rounded(r, RADIUS['control']), t.q('bg-hover'))
            tile_rect = QRectF(r.left() + 8, r.top() + 12, tile, tile)
            p.fillPath(_rounded(tile_rect, RADIUS['control']), t.q('accent-subtle' if current else 'bg-subtle'))
            icons.paint(p, 'fit', t.q('accent' if current else 'text-secondary'), r.left() + 14, r.top() + 18, 16)
            # The state in words at the right of the name line, its glyph before it.
            state_rect = QRectF(r.left() + 46, r.top() + 8, w - 46 - 10, 18)
            p.setFont(font('small'))
            status_w = p.fontMetrics().horizontalAdvance(s['status'])
            p.setPen(t.q('text-tertiary' if s['state'] == 'stale' else 'text-secondary'))
            right = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
            p.drawText(state_rect, right, s['status'])
            if s['state']:
                cx = state_rect.right() - status_w - 10
                paint_status_glyph(p, t, s['state'], cx, state_rect.center().y(), s.get('progress', 0.0))
                status_w += 20
            name_w = state_rect.width() - status_w - space(3)
            p.setFont(font('body-strong'))
            p.setPen(t.q('text-primary'))
            name = p.fontMetrics().elidedText(s['name'], Qt.TextElideMode.ElideRight, int(name_w))
            p.drawText(QRectF(r.left() + 46, r.top() + 8, name_w, 18), Qt.AlignmentFlag.AlignVCenter, name)
            p.setFont(font('small'))
            p.setPen(t.q('text-secondary'))
            p.drawText(QRectF(r.left() + 46, r.top() + 27, w - 80, 16), Qt.AlignmentFlag.AlignVCenter, s['detail'])
            if current:
                icons.paint(p, 'check', t.q('accent'), r.right() - 26, r.top() + 27, 14, 2)
        for sy in separators:
            _menu_separator(p, t, x0, sy, w)
        for k, row in enumerate(commands):
            if k + len(sessions) == self.hover and row.action.isEnabled():
                p.fillPath(_rounded(row.rect, RADIUS['control']), t.q('bg-hover'))
            _menu_command(p, t, row, self.columns.role)
        p.end()


# ── Form controls ──────────────────────────────────────────────────────────────────


class Field(QWidget):
    """A control-height entry on the field grid: ``bg-surface`` (``bg-window`` in dark) in a
    ``border-strong`` outline.

    ``number`` shows *text* right-aligned in tabular figures, with an optional quiet
    *prefix* (σ, from, to) at the left and *suffix* unit at the right; ``choice`` shows
    *text* with a trailing chevron (a unit menu, a model menu); an editable ``text`` field
    takes words, left-aligned (a name). *width* 0 lets it fill its column. *focused* draws
    the accent outline and the focus halo. A disabled field is drawn sunken, its text in ``text-disabled``.
    """

    edited = pyqtSignal(str)
    #: The text as it is typed, before the edit is finished.
    typed = pyqtSignal(str)

    def __init__(
        self,
        t: Theme,
        text: str,
        width: int = 0,
        kind: str = 'number',
        prefix: str = '',
        suffix: str = '',
        focused: bool = False,
        editable: bool = False,
    ):
        super().__init__()
        self.t, self.text, self.kind, self.prefix, self.suffix, self.focused = t, text, kind, prefix, suffix, focused
        self.setFixedHeight(SIZE['control'])
        if width:
            self.setFixedWidth(width)
        else:
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.setMinimumWidth(48)
        # An editable number is typed into a frameless line edit laid over the painted box;
        # :attr:`edited` carries the text once the edit is finished.
        self.editor: QLineEdit | None = None
        if editable:
            editor = QLineEdit(text, self)
            editor.setProperty('role', 'field')
            words = kind == 'text'
            editor.setFont(font('body' if words else 'number'))
            side = Qt.AlignmentFlag.AlignLeft if words else Qt.AlignmentFlag.AlignRight
            editor.setAlignment(side | Qt.AlignmentFlag.AlignVCenter)
            editor.editingFinished.connect(lambda: self.edited.emit(editor.text().strip()))
            editor.textEdited.connect(self.typed)
            editor.installEventFilter(self)
            self.setFocusProxy(editor)
            self.editor = editor

    @staticmethod
    def width_for(sample: str, prefix: str = '', suffix: str = '') -> int:
        """The width a number field needs to show *sample* in full beside *prefix* and *suffix*."""
        width = 2 * space(3) + QFontMetrics(font('number')).horizontalAdvance(sample + '0')
        if prefix:
            width += QFontMetrics(font('body')).horizontalAdvance(prefix) + space(2)
        if suffix:
            width += QFontMetrics(font('small')).horizontalAdvance(suffix) + space(2)
        return width

    def set_text(self, text: str) -> None:
        """Show *text*, in the editor too when the field is editable."""
        self.text = text
        if self.editor is not None and self.editor.text() != text:
            self.editor.setText(text)
        self.update()

    def setAccessibleName(self, name: str) -> None:  # type: ignore[override]
        super().setAccessibleName(name)
        if self.editor is not None:
            self.editor.setAccessibleName(name)

    def eventFilter(self, obj, event) -> bool:  # type: ignore[override]
        if obj is self.editor and event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            self.focused = event.type() == QEvent.Type.FocusIn
            self.update()
        return False

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.editor is not None:
            right = space(3)
            if self.suffix:
                right += QFontMetrics(font('small')).horizontalAdvance(self.suffix) + space(2)
            left = space(3) + (
                QFontMetrics(font('body')).horizontalAdvance(self.prefix) + space(2) if self.prefix else 0
            )
            self.editor.setGeometry(left, 1, self.width() - left - right, self.height() - 2)

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = _rounded(r, RADIUS['control'])
        on = self.isEnabled()
        p.fillPath(path, t.q(('bg-window' if t.dark else 'bg-surface') if on else 'bg-subtle'))
        p.setPen(QPen(t.q('accent') if self.focused else t.q('border-strong' if on else 'border', 0.9), 1))
        p.drawPath(path)
        if self.focused:
            p.setPen(QPen(t.q('accent', 0.25), 3))
            p.drawPath(_rounded(r.adjusted(-2, -2, 2, 2), RADIUS['surface']))
        middle = Qt.AlignmentFlag.AlignVCenter
        quiet = t.q('text-tertiary' if on else 'text-disabled')
        if self.kind == 'choice':
            p.setFont(font('body'))
            p.setPen(t.q('text-primary' if on else 'text-disabled'))
            p.drawText(r.adjusted(space(3), 0, -24, 0), middle, self.text)
            icons.paint(p, 'chevron-down', quiet, r.right() - 20, 8, 12, 2)
            p.end()
            return
        right = space(3)
        if self.prefix:
            p.setFont(font('body'))
            p.setPen(quiet)
            p.drawText(r.adjusted(space(3), 0, 0, 0), middle, self.prefix)
        if self.suffix:
            p.setFont(font('small'))
            p.setPen(quiet)
            p.drawText(r.adjusted(0, 0, -right, 0), middle | Qt.AlignmentFlag.AlignRight, self.suffix)
            right += QFontMetrics(p.font()).horizontalAdvance(self.suffix) + space(2)
        if self.editor is None:
            p.setFont(font('number'))
            p.setPen(t.q('text-primary' if on else 'text-disabled'))
            p.drawText(r.adjusted(0, 0, -right, 0), middle | Qt.AlignmentFlag.AlignRight, self.text)
        p.end()


class Dropdown(QWidget):
    """A choice among *options*: a field-styled box (``bg-surface``, ``bg-raised`` in dark) showing the current
    one beside a chevron, which opens its choice menu.

    *options* are rich text (a source name keeps its subscript; data in them escaped), written
    once and shown both on the face — option *current*, nothing for ``-1`` — and in the
    menu, which lists them in the same type role, marks the current one with a check and
    opens on it. Choosing one emits :attr:`chosen` with its index; the owner then shows its
    model's choice with :meth:`set_current`. The box is as wide as its widest option needs,
    and at least *width* (a column of a grid). A disabled dropdown is greyed and opens
    nothing; *chevron* False and *align_right* show a value that is read rather than chosen.
    """

    chosen = pyqtSignal(int)

    #: The type role of the options, on the face and in the menu.
    ROLE = 'number'

    def __init__(
        self,
        t: Theme,
        options: list[str] = (),
        current: int = -1,
        width: int = 0,
        chevron: bool = True,
        align_right: bool = False,
    ):
        super().__init__()
        self.t, self.least_width, self.chevron, self.align_right = t, width, chevron, align_right
        self.setFixedHeight(SIZE['control'])
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        if chevron:
            self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_options(list(options), current)

    @property
    def opens_menu(self) -> bool:
        """Whether a click opens a menu: a dropdown with options to choose from."""
        return self.chevron and bool(self.options)

    @property
    def text(self) -> str:
        """The current option, as rich text; ``''`` for none."""
        return self.options[self.current] if 0 <= self.current < len(self.options) else ''

    def set_options(self, options: list[str], current: int) -> None:
        """Offer *options* from now on, option *current* chosen, and take the width the widest needs."""
        self.options, self.current = list(options), current
        widest = max((rich_width(o, self.ROLE) for o in self.options), default=0)
        need = max(self.least_width, math.ceil(space(3) + widest + self._right()))
        self.setMinimumWidth(need)
        self.resize(need, SIZE['control'])  # a layout gives it its place again
        self.updateGeometry()
        self.update()

    def set_current(self, index: int) -> None:
        """Show option *index* as the choice."""
        self.current = index
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(self.minimumWidth(), SIZE['control'])

    def _right(self) -> int:
        """The room right of the text: the chevron's, or the inset."""
        return SIZE['control'] if self.chevron else space(3)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_menu()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Down):
            self.open_menu()
        else:
            super().keyPressEvent(event)

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.EnabledChange:
            self.update()
        super().changeEvent(event)

    def open_menu(self) -> None:
        """Open the choice menu under the dropdown (over it where the window has more room there)."""
        if not self.opens_menu or not self.isEnabled():
            return
        actions = []
        for i, html in enumerate(self.options):
            action = QAction(QTextDocumentFragment.fromHtml(html).toPlainText(), self)
            action.setProperty('design_html', html)
            action.setCheckable(True)
            action.setChecked(i == self.current)
            action.triggered.connect(lambda _on=False, i=i: self.chosen.emit(i))
            actions.append(action)
        menu = PopoverMenu(self.t, self.window(), actions, role=self.ROLE, least_width=self.width())
        menu.popup(self)

    def paintEvent(self, _):
        t = self.t
        h = SIZE['control']
        on = self.isEnabled()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = _rounded(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), RADIUS['control'])
        p.fillPath(path, t.q(('bg-raised' if t.dark else 'bg-surface') if on else 'bg-subtle'))
        p.setPen(QPen(t.q('border-strong' if on else 'border'), 1))
        p.drawPath(path)
        text = QRectF(space(3), 0, self.width() - space(3) - self._right(), h)
        p.save()
        p.setClipRect(text)
        paint_rich(p, text, self.text, self.ROLE, t.q('text-primary' if on else 'text-disabled'), self.align_right)
        p.restore()
        if self.chevron:
            chevron = t.q('text-tertiary' if on else 'text-disabled')
            icons.paint(p, 'chevron-down', chevron, self.width() - 22, (h - 12) / 2, 12, 2)
        if self.hasFocus():
            _focus_ring(p, t, QRectF(self.rect()))
        p.end()


class Segmented(QWidget):
    """A segmented control: a sunken track with the chosen option raised on it.

    *width* fixes its width (0 leaves it to the layout). Options in *disabled* are shown
    but cannot be chosen. *dividers* draws a quiet rule between two unchosen options and
    sets the chosen one half a pixel in, for rows of segmented controls in a form.
    """

    def __init__(
        self,
        theme: Theme,
        options: list[str],
        current: int = 0,
        width: int = 0,
        disabled: tuple[int, ...] = (),
        dividers: bool = False,
    ):
        super().__init__()
        self.t, self.options, self.current = theme, options, current
        self.disabled, self.dividers = set(disabled), dividers
        self.setFixedHeight(SIZE['control'])
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        if width:
            self.setFixedWidth(width)

    changed = pyqtSignal(int)

    def _width(self, pad: int) -> int:
        """The width at which every segment holds the widest option, set in ``body-strong`` as when chosen,
        *pad* px either side of it: the segments share the width equally, inside a 2-px inset."""
        metrics = QFontMetrics(font('body-strong'))
        widest = max((metrics.horizontalAdvance(o) for o in self.options), default=0)
        return len(self.options) * (widest + 2 * pad) + 4

    def minimumSizeHint(self) -> QSize:
        return QSize(self._width(space(2)), SIZE['control'])

    def sizeHint(self) -> QSize:
        return QSize(self._width(space(3)), SIZE['control'])

    def set_options(self, options: list[str]) -> None:
        """Offer *options* from now on, and ask for the room they need."""
        self.options = list(options)
        self.updateGeometry()
        self.update()

    def set_current(self, index: int) -> None:
        """Choose option *index* without emitting :attr:`changed`."""
        self.current = index
        self.update()

    def _choose(self, index: int) -> None:
        if 0 <= index < len(self.options) and index not in self.disabled and index != self.current:
            self.current = index
            self.update()
            self.changed.emit(index)

    def mousePressEvent(self, event) -> None:
        sw = (self.width() - 4) / len(self.options)
        self._choose(int((event.position().x() - 2) // sw))

    def keyPressEvent(self, event) -> None:
        step = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1}.get(event.key())
        if step is None:
            super().keyPressEvent(event)
            return
        i = self.current + step
        while 0 <= i < len(self.options) and i in self.disabled:
            i += step
        self._choose(i)

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        # Dark: the track sinks to the window colour and the chosen segment is raised with
        # a strong border, so the choice reads at a glance; light keeps white on grey.
        p.fillPath(_rounded(r, RADIUS['control']), t.q('bg-window' if t.dark else 'bg-subtle'))
        sw = (r.width() - 4) / len(self.options)
        for i, opt in enumerate(self.options):
            seg = QRectF(2 + i * sw, 2, sw, r.height() - 4)
            sel = i == self.current
            off = i in self.disabled or not self.isEnabled()
            if sel:
                sp = _rounded(seg.adjusted(0.5, 0.5, -0.5, -0.5) if self.dividers else seg, RADIUS['control'] - 1)
                p.fillPath(sp, t.q('bg-raised' if t.dark else 'bg-surface', 0.5 if off else 1.0))
                if t.dark and not off:
                    p.fillPath(sp, t.q('text-primary', 0.06))
                p.setPen(QPen(t.q('border-strong' if t.dark else 'border', 0.6 if off else 1.0), 1))
                p.drawPath(sp)
            elif self.dividers and i and i - 1 != self.current:
                p.setPen(QPen(t.q('border'), 1))
                p.drawLine(QPointF(seg.left(), 8), QPointF(seg.left(), r.height() - 8))
            p.setFont(font('body-strong' if sel else 'body'))
            if off:
                p.setPen(t.q('text-disabled'))
            elif sel:
                p.setPen(t.q('text-primary'))
            else:
                p.setPen(t.q('text-tertiary' if t.dark else 'text-secondary'))
            p.drawText(seg, Qt.AlignmentFlag.AlignCenter, opt)
        if self.hasFocus():
            _focus_ring(p, t, r)
        p.end()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.EnabledChange:
            self.update()


class Checkbox(QWidget):
    """A 15-px box with its label: accent fill and a check when *checked*; a click or Space toggles it.

    *rich* reads *text* as HTML, so an input's name keeps its subscript.
    """

    toggled = pyqtSignal(bool)

    def __init__(self, t: Theme, text: str, checked: bool = False, rich: bool = False):
        super().__init__()
        self.t, self.text, self.checked, self.rich = t, text, checked, rich
        width = rich_width(text, 'body') if rich else QFontMetrics(font('body')).horizontalAdvance(text)
        self.setFixedSize(math.ceil(width) + 24, SIZE['control'])
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_checked(self, checked: bool) -> None:
        """Tick or untick the box without emitting :attr:`toggled`."""
        self.checked = checked
        self.update()

    def _toggle(self) -> None:
        self.checked = not self.checked
        self.update()
        self.toggled.emit(self.checked)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Space:
            self._toggle()
        else:
            super().keyPressEvent(event)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.EnabledChange:
            self.update()

    def paintEvent(self, _):
        t = self.t
        h = SIZE['control']
        on = self.isEnabled()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = _rounded(QRectF(0.5, 6.5, 15, 15), 4)
        if self.checked:
            p.fillPath(path, t.q('accent' if on else 'text-disabled'))
            icons.paint(p, 'check', t.q('on-accent'), 2, 8, 12, 2.6)
        else:
            p.fillPath(path, t.q(('bg-raised' if t.dark else 'bg-surface') if on else 'bg-subtle'))
            p.setPen(QPen(t.q('border-strong' if on else 'border'), 1))
            p.drawPath(path)
        tone = t.q('text-primary' if on else 'text-disabled')
        text_rect = QRectF(24, 0, self.width() - 24, h)
        if self.rich:
            paint_rich(p, text_rect, self.text, 'body', tone)
        else:
            p.setFont(font('body'))
            p.setPen(tone)
            p.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, self.text)
        if self.hasFocus():
            _focus_ring(p, t, QRectF(self.rect()))
        p.end()


class Toggle(QWidget):
    """An on/off switch, 36 × 20: an accent track with the knob at the right when *on*; a click or Space flips it.

    Disabled, its track is ``text-disabled`` whether on or off.
    """

    toggled = pyqtSignal(bool)

    def __init__(self, t: Theme, on: bool = True):
        super().__init__()
        self.t, self.on = t, on
        self.setFixedSize(36, 20)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _flip(self) -> None:
        self.on = not self.on
        self.update()
        self.toggled.emit(self.on)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._flip()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Space:
            self._flip()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        track = ('accent' if self.on else 'border-strong') if self.isEnabled() else 'text-disabled'
        p.fillPath(_rounded(r, r.height() / 2), t.q(track))
        knob = QRectF(r.right() - 18 if self.on else 2, 2, 16, 16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(t.q('shadow', 46 / 255))
        p.drawEllipse(knob.translated(0, 0.75))
        p.setBrush(t.q('text-primary' if t.dark else 'bg-surface'))
        p.drawEllipse(knob)
        if self.hasFocus():
            _focus_ring(p, t, r)
        p.end()


class Slider(QWidget):
    """A 16-px slider: track, accent fill up to the handle at *pos* (0–1), and the handle.

    *decades* > 0 marks each decade under the track, so a log scale reads as one. Pressing
    or dragging on it moves the handle there, the arrow keys by a hundredth, and
    :attr:`moved` carries each new position. Disabled, its fill is ``text-disabled``.
    """

    moved = pyqtSignal(float)
    RADIUS = 7.0

    def __init__(self, t: Theme, pos: float, decades: int = 0):
        super().__init__()
        self.t, self.pos, self.decades = t, pos, decades
        self.setFixedHeight(16)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_pos(self, pos: float, decades: int | None = None) -> None:
        """Show the handle at *pos* (and *decades* ticks when given) without emitting :attr:`moved`."""
        self.pos = min(max(pos, 0.0), 1.0)
        if decades is not None and decades != self.decades:
            self.decades = decades
            self.updateGeometry()
        self.update()

    def minimumSizeHint(self) -> QSize:
        # The handle's travel: a step of the spacing scale between decade ticks, and four at least.
        return QSize(math.ceil(2 * self.RADIUS) + max(self.decades, 4) * space(3), 16)

    def sizeHint(self) -> QSize:
        return self.minimumSizeHint()

    def _move_to(self, pos: float) -> None:
        pos = min(max(pos, 0.0), 1.0)
        if pos != self.pos:
            self.pos = pos
            self.update()
            self.moved.emit(pos)

    def _pos_at(self, x: float) -> float:
        r = self.RADIUS
        return (x - r) / max(self.width() - 2 * r, 1.0)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._move_to(self._pos_at(event.position().x()))

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._move_to(self._pos_at(event.position().x()))

    def keyPressEvent(self, event) -> None:
        step = {Qt.Key.Key_Left: -0.01, Qt.Key.Key_Right: 0.01, Qt.Key.Key_Down: -0.01, Qt.Key.Key_Up: 0.01}
        if event.key() in step:
            self._move_to(self.pos + step[event.key()])
        else:
            super().keyPressEvent(event)

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.RADIUS
        x0, x1, cy = r, self.width() - r, 7.0
        p.fillPath(_rounded(QRectF(x0, cy - 2, x1 - x0, 4), 2), t.q('border-strong' if t.dark else 'bg-hover'))
        hx = x0 + self.pos * (x1 - x0)
        p.fillPath(_rounded(QRectF(x0, cy - 2, hx - x0, 4), 2), t.q('accent' if self.isEnabled() else 'text-disabled'))
        if self.decades:
            p.setPen(QPen(t.q('text-tertiary' if t.dark else 'border-strong', 0.8), 1))
            for k in range(self.decades + 1):
                x = round(x0 + k / self.decades * (x1 - x0)) + 0.5
                p.drawLine(QPointF(x, cy + 5), QPointF(x, cy + 8))
        if t.dark:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(t.q('text-primary'))
        else:
            p.setPen(QPen(t.q('border-strong'), 1))
            p.setBrush(t.q('bg-surface'))
        p.drawEllipse(QPointF(hx, cy), r - 0.5, r - 0.5)
        if self.hasFocus():
            p.setPen(QPen(t.q('accent'), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(hx, cy), r - 1, r - 1)
        p.end()


class SliderEnd(QWidget):
    """One end of a :class:`Slider`, edited where it stands: quiet text, flush left (low
    end) or right (*right*, high end) in a column *width* px wide. Under the pointer it
    gains the outline of :class:`SliderEndOutline`; a click opens it for typing, and
    :attr:`edited` carries the text once the edit is finished. *hover* names it
    ``HoverEnd`` so a render can find it."""

    HEIGHT = 20
    edited = pyqtSignal(str)

    def __init__(self, t: Theme, text: str, width: int, right: bool = False, hover: bool = False):
        super().__init__()
        self.t, self.text, self.right = t, text, right
        self._outline: SliderEndOutline | None = None
        self._editor: QLineEdit | None = None
        self.setFixedSize(width, self.HEIGHT)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.setToolTip('Click to change this end of the slider')
        if hover:
            self.setObjectName('HoverEnd')

    def set_text(self, text: str) -> None:
        self.text = text
        self.update()

    def text_rect(self) -> QRectF:
        """Where the end's text is drawn, in the widget's own coordinates."""
        tw = QFontMetrics(font('small-number')).horizontalAdvance(self.text)
        return QRectF(self.width() - tw if self.right else 0, 0, tw, self.HEIGHT)

    def enterEvent(self, _event) -> None:
        if self._outline is None and self._editor is None:
            self._outline = SliderEndOutline(self.t, self.window(), self)
            self._outline.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self._outline.show()
            self._outline.raise_()

    def leaveEvent(self, _event) -> None:
        if self._outline is not None:
            drop(self._outline)
            self._outline = None

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.edit()

    def edit(self) -> None:
        """Open the end for typing over its outline; Return or leaving the field emits :attr:`edited`."""
        self.leaveEvent(None)
        window = self.window()
        r = self.text_rect().adjusted(-space(2), 0, space(2), 0)
        width = max(int(r.width()), QFontMetrics(font('small-number')).horizontalAdvance('0.000e-00') + space(3))
        left = (
            self.mapTo(window, r.topRight().toPoint()).x() - width
            if self.right
            else self.mapTo(window, r.topLeft().toPoint()).x()
        )
        editor = QLineEdit(self.text.replace('\u202f', '').replace('×10', 'e').translate(_FROM_SUPER), window)
        editor.setFont(font('small-number'))
        editor.setProperty('role', 'field')
        editor.setAccessibleName(self.accessibleName() or 'Slider end')
        editor.setGeometry(left, self.mapTo(window, self.rect().topLeft()).y(), width, self.HEIGHT)
        editor.selectAll()
        editor.show()
        editor.raise_()
        editor.setFocus()
        self._editor = editor

        def commit() -> None:
            if self._editor is not editor:
                return
            self._editor = None
            text = editor.text().strip()
            drop(editor)
            self.edited.emit(text)

        editor.editingFinished.connect(commit)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setFont(font('small-number'))
        p.setPen(self.t.q('text-tertiary' if self.isEnabled() else 'text-disabled'))
        p.drawText(self.text_rect(), Qt.AlignmentFlag.AlignCenter, self.text)
        p.end()


class SliderEndOutline(QWidget):
    """A :class:`SliderEnd` under the pointer: the field outline 4 px beyond its text,
    floated over *parent* as the editor it opens is (it reaches past the column edge)."""

    def __init__(self, t: Theme, parent: QWidget, end: SliderEnd):
        super().__init__(parent)
        self.t, self.text = t, end.text
        r = end.text_rect().adjusted(-space(2), 0, space(2), 0)
        top_left = end.mapTo(parent, r.topLeft().toPoint())
        self.setGeometry(top_left.x(), top_left.y(), int(r.width()), int(r.height()))

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = _rounded(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 4)
        p.fillPath(path, t.q('bg-window' if t.dark else 'bg-surface'))
        p.setPen(QPen(t.q('border-strong'), 1))
        p.drawPath(path)
        p.setFont(font('small-number'))
        p.setPen(t.q('text-secondary'))
        p.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, self.text)
        p.end()


class ReplicateChip(QWidget):
    """One replicate as a toggle chip.

    On: accent tint and a check. Off: a dashed outline and an ×; *by_filter* adds a small
    ``z`` tag, for a replicate outlier removal switched off.
    """

    toggled_on = pyqtSignal(bool)

    def __init__(self, t: Theme, letter: str, on: bool, by_filter: bool = False):
        super().__init__()
        self.t, self.letter = t, letter
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_state(on, by_filter)

    def set_state(self, on: bool, by_filter: bool = False) -> None:
        """Show the replicate used (*on*) or switched off, by the outlier filter where *by_filter*."""
        self.on, self.by_filter = on, by_filter
        self.setFixedSize(60 if by_filter else 52, SIZE['control'])
        self.setAccessibleName(f'Replicate {self.letter}, {"used" if on else "switched off"}')
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggled_on.emit(not self.on)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return):
            self.toggled_on.emit(not self.on)
        else:
            super().keyPressEvent(event)

    def paintEvent(self, _):
        t = self.t
        h = SIZE['control']
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = _rounded(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), RADIUS['control'])
        if self.on:
            p.fillPath(path, t.q('accent-subtle'))
            p.setPen(QPen(t.q('accent', 0.45), 1))
            p.drawPath(path)
            icons.paint(p, 'check', t.q('accent'), 10, 8, 12, 2.4)
            p.setPen(t.q('accent'))
        else:
            p.fillPath(path, t.q('bg-surface'))
            pen = QPen(t.q('border-strong'), 1)
            pen.setDashPattern([3, 2])
            p.setPen(pen)
            p.drawPath(path)
            p.setPen(QPen(t.q('replicate-off'), 1.6, cap=Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(12, 11), QPointF(18, 17))
            p.drawLine(QPointF(18, 11), QPointF(12, 17))
            p.setPen(t.q('text-secondary'))
        p.setFont(font('body-strong'))
        p.drawText(QRectF(28, 0, 16, h), Qt.AlignmentFlag.AlignVCenter, self.letter)
        if self.by_filter:
            tag = QRectF(41, 7, 14, 14)
            p.fillPath(_rounded(tag, 4), t.q('bg-subtle'))
            p.setFont(font('small'))
            p.setPen(t.q('text-secondary'))
            p.drawText(tag.adjusted(0, -1, 0, -1), Qt.AlignmentFlag.AlignCenter, 'z')
        if self.hasFocus():
            _focus_ring(p, t, QRectF(self.rect()))
        p.end()


class ConcentrationGrid(QWidget):
    """A concentration list in two side-by-side runs of rows: the point number and the
    value as entered (*values*, already formatted), under one *header*. Drawn like a
    parameters table: a header hairline, no box, a hairline between the two runs."""

    HEAD, ROW = 26, 20

    edited = pyqtSignal(int, str)

    def __init__(self, t: Theme, values: list[str], header: str, editable: bool = False):
        super().__init__()
        self.t, self.editable = t, editable
        self._editor: QLineEdit | None = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.set_values(values, header)
        if editable:
            self.setToolTip('Double-click a value to change it.')

    def set_values(self, values: list[str], header: str) -> None:
        """Show *values* (formatted) under *header*."""
        self.values, self.header = values, header
        self.rows = math.ceil(len(values) / 2)
        self.setFixedHeight(self.HEAD + self.rows * self.ROW + 4)
        self.updateGeometry()
        self.update()

    #: The column of point numbers, left of each run's values.
    INDEX_W = 24

    def minimumSizeHint(self) -> QSize:
        # Two runs, each its point numbers and its widest value or header, a gap either side of the rule between them.
        widest = max(
            [QFontMetrics(font('label')).horizontalAdvance(self.header)]
            + [QFontMetrics(font('number')).horizontalAdvance(v) for v in self.values]
        )
        return QSize(2 * (self.INDEX_W + space(2) + widest + space(4)), self.minimumHeight())

    def sizeHint(self) -> QSize:
        return self.minimumSizeHint()

    def _cell(self, index: int) -> QRectF:
        half = self.width() / 2
        col, k = divmod(index, self.rows)
        x0 = 0 if col == 0 else half + space(4)
        x1 = half - space(4) if col == 0 else self.width()
        return QRectF(x0 + self.INDEX_W, self.HEAD + 2 + k * self.ROW, x1 - x0 - self.INDEX_W, self.ROW)

    def mouseDoubleClickEvent(self, event) -> None:
        if not self.editable:
            return
        for i in range(len(self.values)):
            if self._cell(i).contains(event.position()):
                self.edit(i)
                return

    def edit(self, index: int) -> None:
        """Open value *index* for typing; Return or leaving the field emits :attr:`edited`."""
        if not self.values:
            return
        if self._editor is not None:
            self._editor.deleteLater()
        editor = QLineEdit(self.values[index].replace('\u202f', '').replace('×10', 'e').translate(_FROM_SUPER), self)
        editor.setFont(font('number'))
        editor.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        editor.setAccessibleName(f'Concentration of point {index + 1}')
        editor.setGeometry(self._cell(index).toRect().adjusted(0, -2, 0, 2))
        editor.selectAll()
        editor.show()
        editor.setFocus()
        self._editor = editor
        done = {'once': False}

        def commit() -> None:
            if done['once']:
                return
            done['once'] = True
            text = editor.text().strip()
            self._editor = None
            editor.deleteLater()
            self.edited.emit(index, text)

        editor.editingFinished.connect(commit)

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        half = w / 2
        p.fillRect(QRectF(0, self.HEAD - 1, w, 1), t.q('border'))
        p.fillRect(QRectF(half, 0, 1, h), t.q('border'))
        gap, idx_w = space(4), self.INDEX_W
        right = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        for col in range(2):
            x0 = 0 if col == 0 else half + gap
            x1 = half - gap if col == 0 else w
            p.setFont(font('label'))
            p.setPen(t.q('text-tertiary'))
            p.drawText(QRectF(x0, 0, idx_w, self.HEAD - 1), Qt.AlignmentFlag.AlignVCenter, '#')
            p.drawText(QRectF(x0, 0, x1 - x0, self.HEAD - 1), right, self.header)
            for k in range(self.rows):
                i = col * self.rows + k
                if i >= len(self.values):
                    break
                y = self.HEAD + 2 + k * self.ROW
                p.setFont(font('small-number'))
                p.setPen(t.q('text-tertiary'))
                p.drawText(QRectF(x0, y, idx_w, self.ROW), Qt.AlignmentFlag.AlignVCenter, str(i + 1))
                p.setFont(font('number'))
                p.setPen(t.q('text-primary'))
                p.drawText(QRectF(x0, y, x1 - x0, self.ROW), right, self.values[i])
        p.end()


# ── Settings cards ─────────────────────────────────────────────────────────────────


def _over(base: QColor, top: QColor) -> QColor:
    """*top* composited over *base*: one opaque colour for a translucent token."""
    a = top.alphaF()
    return QColor.fromRgbF(*(b + (c - b) * a for b, c in zip(base.getRgbF()[:3], top.getRgbF()[:3], strict=True)))


def card_edge(t: Theme) -> QColor:
    """The line round a settings card and between its rows. Dark: the card is lifted off
    a raised window, where ``border`` would vanish; a translucent strong border keeps it."""
    return t.q('border-strong', 0.55) if t.dark else t.q('border')


def card_fill(t: Theme) -> QColor:
    """A settings card's surface: ``bg-surface`` in light; in dark a shade lighter than the
    raised window, as grouped rows are on macOS."""
    return _over(t.q('bg-raised'), t.q('text-primary', 0.04)) if t.dark else t.q('bg-surface')


def on_card(t: Theme) -> Theme:
    """The theme the controls on a settings card are drawn with.

    A control sits one step off its surface: its well (``bg-window``: the track of a
    segmented control, the fill of a field) a step below, its face (``bg-raised``: an
    outlined button) a step above. A dark card is lifted above the raised window, so both
    move up with it: the well becomes ``bg-surface`` and the face the card fill lifted
    once more. On the light card, ``bg-surface``, the controls' own tokens hold.
    """
    if not t.dark:
        return t
    lifted = Theme(dark=True)
    face = _over(card_fill(t), t.q('text-primary', 0.06))
    lifted.c = {**t.c, 'bg-window': t['bg-surface'], 'bg-raised': face.name()}
    return lifted


def _card_rule(t: Theme) -> QFrame:
    c = card_edge(t)
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet(f'background: rgba({c.red()},{c.green()},{c.blue()},{c.alpha()}); border: none;')
    return f


class SettingsCard(QWidget):
    """A group of settings rows on one rounded surface, an inset rule between rows."""

    def __init__(self, t: Theme, rows: list[QWidget]):
        super().__init__()
        self.t = t
        lay = vbox(spacing=0)
        for i, row in enumerate(rows):
            if i:
                lay.addLayout(hbox(_card_rule(t), margins=(4, 0, 0, 0)))
            lay.addWidget(row)
        self.setLayout(lay)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = _rounded(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), RADIUS['surface'])
        p.fillPath(path, card_fill(self.t))
        p.setPen(QPen(card_edge(self.t), 1))
        p.drawPath(path)
        p.end()


def settings_group(title: str, card: QWidget, trailing: QWidget | None = None) -> QWidget:
    """A settings group (DESIGN.md §6): its title in ``body-strong``, an optional *trailing* control at the
    right of the title row, and its :class:`SettingsCard` below."""
    head = hbox(label(title, 'body-strong'), None, *([trailing] if trailing is not None else []), margins=(4, 0, 4, 0))
    w = QWidget()
    w.setLayout(vbox(head, 3, card, spacing=0))
    return w


# ── Results ────────────────────────────────────────────────────────────────────────


class Callout(QFrame):
    """One message across the canvas (DESIGN.md §5): tinted fill and border of *tone*, its icon,
    the title, the body and an optional trailing *action* link, :attr:`action`.

    ``warning`` carries a result's warning on ``warning-bg`` inside ``warning-border``;
    ``neutral`` a note on ``bg-subtle``. The body wraps, so a long note grows the callout.
    """

    #: Per tone: fill, border, icon and icon colour.
    TONES = {
        'warning': ('warning-bg', 'warning-border', 'alert', 'warning'),
        'neutral': ('bg-subtle', 'border', 'info', 'text-secondary'),
    }

    def __init__(self, theme: Theme, tone: str, title: str, body: str, action: str | None = None):
        super().__init__()
        self.t, self.tone = theme, tone
        fill, edge, icon, ink = self.TONES[tone]
        ic = Icon(theme, icon, ink)
        self.body = label(body, 'body', 'secondary')
        self.body.setWordWrap(True)
        self.body.setMinimumWidth(1)
        self.body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row = hbox(ic, label(title, 'body-strong'), margins=(4, 3, 4, 3))
        row.addWidget(self.body, 1)
        self.action = link_button(action) if action else None
        if self.action is not None:
            row.addWidget(self.action)
        self.setLayout(row)
        self.setMinimumHeight(40)
        self.setAccessibleName(f'{title}: {body}')

    def paintEvent(self, _):
        fill, edge, _icon, _ink = self.TONES[self.tone]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = _rounded(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), RADIUS['surface'])
        p.fillPath(path, self.t.q(fill))
        p.setPen(QPen(self.t.q(edge), 1))
        p.drawPath(path)
        p.end()


# ── Reveal ─────────────────────────────────────────────────────────────────────────


def _scroll_area_of(widget: QWidget) -> QScrollArea | None:
    """The scroll area *widget* scrolls in, or ``None`` where it scrolls in none."""
    parent = widget.parentWidget()
    while parent is not None and not isinstance(parent, QScrollArea):
        parent = parent.parentWidget()
    return parent


class RevealMark(QWidget):
    """The mark of a place a link revealed (DESIGN.md §6): a 2-px `accent` ring a gap of ``space(1)``
    outside *target*'s edge, for ``DURATION['reveal-mark']`` ms.

    It lies over the viewport of the scroll area the target scrolls in — or over the
    target's parent — and is drawn inside it, follows the target as it scrolls, moves or resizes,
    takes no pointer event, and clears early where the target is hidden or goes. A window
    shows one mark: a new one clears the one before. It neither moves nor fades, so it
    needs no reduced-motion form.
    """

    #: The ring's width, the keyboard-focus ring's.
    RING = 2

    def __init__(self, theme: Theme, target: QWidget):
        area = _scroll_area_of(target)
        super().__init__(area.viewport() if area is not None else target.parentWidget())
        self.t, self.target = theme, target
        for other in target.window().findChildren(RevealMark):
            if other is not self:
                other.clear()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        target.installEventFilter(self)
        target.destroyed.connect(self.clear)
        if area is not None:
            for bar in (area.horizontalScrollBar(), area.verticalScrollBar()):
                bar.valueChanged.connect(self._place)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.clear)
        self._timer.start(DURATION['reveal-mark'])
        self._place()
        self.raise_()
        self.show()

    def clear(self) -> None:
        """Take the mark away."""
        self.hide()
        self.deleteLater()

    def _place(self) -> None:
        outset = self.RING + space(1)
        corner = self.target.mapTo(self.parentWidget(), QPoint(0, 0))
        ring = QRect(corner, self.target.size()).adjusted(-outset, -outset, outset, outset)
        # Kept inside what it lies over, so a place at the top of its scroll area keeps the whole ring.
        self.setGeometry(ring.intersected(self.parentWidget().rect()))

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.target:
            if event.type() == QEvent.Type.Hide:
                self.clear()
            elif event.type() in (QEvent.Type.Move, QEvent.Type.Resize):
                self._place()
        return False

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(self.t.q('accent'), self.RING))
        p.setBrush(Qt.BrushStyle.NoBrush)
        half = self.RING / 2
        p.drawRoundedRect(QRectF(self.rect()).adjusted(half, half, -half, -half), RADIUS['surface'], RADIUS['surface'])
        p.end()


def _focus_in(target: QWidget) -> QWidget:
    """What takes the focus when *target* is revealed: the target where Tab reaches it, else the first control
    inside it Tab reaches, else the target itself, so that Tab goes on from there."""
    reachable = Qt.FocusPolicy.TabFocus.value
    if target.focusPolicy().value & reachable:
        return target
    widget = target.nextInFocusChain()
    for _ in range(len(target.window().findChildren(QWidget))):
        if widget is target:
            break
        if (
            target.isAncestorOf(widget)
            and widget.focusPolicy().value & reachable
            and widget.isVisible()
            and widget.isEnabled()
        ):
            return widget
        widget = widget.nextInFocusChain()
    return target


def reveal(theme: Theme, target: QWidget) -> None:
    """Show *target*, whose view is on screen: open every section holding it, scroll it to the top of its
    scroll area, move the focus into it (:func:`_focus_in`) and ring it with a :class:`RevealMark`.

    A target that stays hidden once its sections are open — a part the view shows only with a
    result — is left as it is.
    """
    widget = target
    while widget is not None:
        header = getattr(widget, 'header', None)
        if isinstance(header, SectionHeader):
            header.set_open(True)
        widget = widget.parentWidget()
    # The view, its side panel and the sections just opened are laid out before the target is measured.
    for _ in range(3):
        QApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest.value)
    if not target.isVisible():
        return
    area = _scroll_area_of(target)
    if area is not None:
        top = target.mapTo(area.widget(), QPoint(0, 0)).y()
        area.verticalScrollBar().setValue(top - (RevealMark.RING + space(2)))
    _focus_in(target).setFocus(Qt.FocusReason.OtherFocusReason)
    RevealMark(theme, target)


def spaced_ticks(
    ticks: list[tuple[float, str]], x_of, fm: QFontMetrics, left: float, right: float
) -> list[tuple[str, QRectF]]:
    """The tick labels a log axis draws, each with its box at the top of the label line, as tall as a line of *fm*.

    Each label is centred on its tick and kept inside *left* to *right*. Where two would
    come closer than ``space(2)``, the rounder value keeps its label — a power of ten,
    then 5, 2 and 3, then values of more figures — and the other is left out; its grid
    line still marks the axis.
    """

    def rank(value: float) -> tuple[int, int]:
        mantissa = float(f'{value / 10.0 ** math.floor(math.log10(value)):.6g}')
        return len(f'{mantissa:g}'.replace('.', '')), {1.0: 0, 5.0: 1, 2.0: 2, 3.0: 3}.get(mantissa, 4)

    placed: list[tuple[str, QRectF]] = []
    for i in sorted(range(len(ticks)), key=lambda i: (rank(ticks[i][0]), i)):
        value, text = ticks[i]
        width = fm.horizontalAdvance(text) + 4
        x = min(max(x_of(value) - width / 2, left), right - width)
        box = QRectF(x, 0, width, fm.height())
        if all(box.left() >= r.right() + space(2) or box.right() + space(2) <= r.left() for _t, r in placed):
            placed.append((text, box))
    return sorted(placed, key=lambda item: item[1].left())


class IntervalChart(QWidget):
    """A small forest plot on a log axis: one row per interval, each with its estimate.

    Each of *rows* is a dict with ``label``, ``color`` (a token), ``segments`` (the
    accepted stretches, ``(low, high)`` pairs), ``est`` (``None`` for an estimate that is
    no number, one on an end of its search box), ``text`` (the numbers, drawn on the right
    in tabular figures, in a column as wide as the widest of them), an optional ``badge``
    and an optional ``note`` drawn in place of the bars. The axis spans *lo* to *hi*;
    *ticks* are ``(value, label)`` pairs, with *unit* after them.
    """

    ROW_H = 26
    LABEL_W = 116  # the column of row labels, left of the axis

    def __init__(self, theme: Theme, rows: list[dict], lo: float, hi: float, ticks: list[tuple[float, str]], unit: str):
        super().__init__()
        self.t = theme
        self.setMinimumWidth(420)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.set_rows(rows, lo, hi, ticks, unit)

    def set_rows(self, rows: list[dict], lo: float, hi: float, ticks: list[tuple[float, str]], unit: str) -> None:
        """Show *rows* on the axis *lo* to *hi* with *ticks*, labelled in *unit*."""
        self.rows, self.lo, self.hi, self.ticks, self.unit = rows, lo, hi, ticks, unit
        self.setFixedHeight(len(rows) * self.ROW_H + 26)
        self.setMinimumWidth(420 - 176 + self._numbers_width())  # the axis keeps its room beside wider numbers
        self.setAccessibleDescription(
            '; '.join(
                f'{row["label"]}: {row["text"]}' + (f' ({row["badge"]})' if row.get('badge') else '') for row in rows
            )
        )
        self.update()

    def _x(self, v: float, x0: float, w: float) -> float:
        return x0 + (math.log10(v) - math.log10(self.lo)) / (math.log10(self.hi) - math.log10(self.lo)) * w

    def _numbers_width(self) -> int:
        """The width of the numbers column: the widest row's text and badge, the axis unit, 176 px at least."""
        numbers, badges = QFontMetrics(font('number')), QFontMetrics(font('label'))
        widths = [QFontMetrics(font('small-number')).horizontalAdvance(self.unit)]
        for row in self.rows:
            width = numbers.horizontalAdvance(row['text'])
            if row.get('badge'):
                width += space(3) + badges.horizontalAdvance(row['badge']) + 14
            widths.append(width)
        return max(176, math.ceil(max(widths)) + space(1))

    def _axis(self) -> tuple[float, float]:
        """Where the axis starts and how wide it is at the chart's width."""
        return self.LABEL_W, self.width() - self.LABEL_W - self._numbers_width() - space(5)

    def tick_room(self) -> tuple[float, float]:
        """The span the tick labels keep to: from the chart's left edge to a step short of the axis unit."""
        x0, w = self._axis()
        return 0.0, x0 + w + space(5) - space(2)

    def tick_rects(self) -> list[tuple[str, QRectF]]:
        """The tick labels drawn at the chart's width, and their boxes (:func:`spaced_ticks`)."""
        x0, w = self._axis()
        return spaced_ticks(
            self.ticks, lambda v: self._x(v, x0, w), QFontMetrics(font('small-number')), *self.tick_room()
        )

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        num_w = self._numbers_width()
        x0, w = self._axis()
        top = 2
        bottom = top + len(self.rows) * self.ROW_H
        p.setFont(font('small-number'))
        p.setPen(QPen(t.q('grid'), 1))
        for tk, _text in self.ticks:
            x = self._x(tk, x0, w)
            p.drawLine(QPointF(x, top), QPointF(x, bottom))
        p.setPen(t.q('text-tertiary'))
        for text, box in self.tick_rects():
            p.drawText(box.translated(0, bottom + 4), Qt.AlignmentFlag.AlignHCenter, text)
        p.drawText(QRectF(x0 + w + space(5), bottom + 4, num_w, 16), Qt.AlignmentFlag.AlignLeft, self.unit)
        for i, row in enumerate(self.rows):
            cy = top + i * self.ROW_H + self.ROW_H / 2
            p.setFont(font('small'))
            p.setPen(t.q('text-secondary'))
            p.drawText(QRectF(0, cy - 9, self.LABEL_W - 12, 18), Qt.AlignmentFlag.AlignVCenter, row['label'])
            col = t.q(row['color'])
            p.setPen(QPen(t.q('border'), 1))
            p.drawLine(QPointF(x0, cy), QPointF(x0 + w, cy))
            if row.get('note'):
                p.setFont(font('small'))
                p.setPen(t.q('text-tertiary'))
                p.drawText(QRectF(x0, cy - 9, w, 18), Qt.AlignmentFlag.AlignVCenter, row['note'])
            for a, b in row['segments']:
                pen = QPen(col, 4)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawLine(QPointF(self._x(a, x0, w), cy), QPointF(self._x(b, x0, w), cy))
            if row.get('est') is not None:
                p.setPen(QPen(t.q('bg-surface'), 2))
                p.setBrush(col)
                p.drawEllipse(QPointF(self._x(row['est'], x0, w), cy), 5, 5)
            p.setPen(t.q('text-primary'))
            p.setFont(font('number'))
            txt = row['text']
            p.drawText(QRectF(x0 + w + space(5), cy - 9, num_w, 18), Qt.AlignmentFlag.AlignVCenter, txt)
            if row.get('badge'):
                bx = x0 + w + space(5) + p.fontMetrics().horizontalAdvance(txt) + space(3)
                p.setFont(font('label'))
                bw = p.fontMetrics().horizontalAdvance(row['badge']) + 14
                pill = QRectF(bx, cy - SIZE['badge'] / 2, bw, SIZE['badge'])
                p.fillPath(_rounded(pill, SIZE['badge'] / 2), t.q('bg-subtle'))
                p.setPen(t.q('text-secondary'))
                p.drawText(pill, Qt.AlignmentFlag.AlignCenter, row['badge'])
        p.end()


class LegendRow(QWidget):
    """A plot legend as non-wrapping chips whose swatches are drawn with the plot's own marks.

    *items* are ``(kind, text)``: ``dots`` (replicates, at *dot_alpha*, by default the
    opacity the titration plot draws them at), ``cross`` (a replicate not used, always named),
    ``rings`` (an overlaid file, with an × that removes it), ``mean`` (mean ± SD), ``line``
    (the fitted or model curve, or the reported reading), ``line-other`` (a fit shown beside
    the reported one), ``line-secondary`` (the reading at the inputs as entered), ``bars``
    (the accepted stretches of both readings), ``bar`` (those of the one reading at the inputs
    as entered) and ``diamond`` (a best fit). A kind ending in ``+band`` draws its mark over
    the accent tint of a shaded interval, for the reading whose interval the plot shades.

    ``dots`` may and ``cross`` does name one replicate, ``(kind, text, index)`` with its place in
    the data's order: the entry is then one point or one × in that replicate's colour and mark,
    which :meth:`set_marks` takes from the titration plot's appearance. A click on the × of
    ``rings`` emits :attr:`removed`; with *removable* off, as in a saved figure, ``rings`` has
    no ×.
    """

    removed = pyqtSignal()

    def __init__(
        self, theme: Theme, items: list[tuple[str, str]], dot_alpha: float | None = None, removable: bool = True
    ):
        super().__init__()
        self.t, self.dot_alpha, self.removable = theme, dot_alpha, removable
        self.line_width, self.line_color = 2.0, 'accent'
        self.replicate_mark: Callable[[int], tuple[str, str]] = lambda _index: ('replicate', 'o')
        self.setFixedHeight(20)
        self.set_items(items)

    def set_marks(
        self, replicate_mark: Callable[[int], tuple[str, str]], line_width: float, line_color: str = 'accent'
    ) -> None:
        """Draw a replicate's entry in the colour token and pyqtgraph symbol (``o``, ``s``, ``t1``)
        *replicate_mark* gives its index, and the ``line`` *line_width* px wide in colour token
        *line_color*, as the plot draws its replicates and curve."""
        self.replicate_mark, self.line_width, self.line_color = replicate_mark, line_width, line_color
        self.update()

    def set_items(self, items: list[tuple]) -> None:
        """Show *items* as the legend."""
        self.items = items
        fm = QFontMetrics(font('small'))
        self.setFixedWidth(max(0, sum(self._width(kind, txt, fm) for kind, txt, *_ in items) - space(5)))
        self.update()
        if self.removable and any(kind == 'rings' for kind, *_ in items):
            self.setToolTip('The × removes the overlay')

    def dots_alpha(self) -> float:
        """The opacity the replicates' dots are drawn at."""
        return REPLICATE_ALPHA if self.dot_alpha is None else self.dot_alpha

    def _width(self, kind: str, txt: str, fm: QFontMetrics) -> int:
        return 20 + fm.horizontalAdvance(txt) + (space(2) + 12 if kind == 'rings' and self.removable else 0) + space(5)

    def _close_rect(self) -> QRectF | None:
        """Where the × of the ``rings`` entry is drawn, if there is one."""
        fm = QFontMetrics(font('small'))
        x = 0.0
        for kind, txt, *_ in self.items:
            if kind == 'rings' and self.removable:
                close_x = x + 20 + fm.horizontalAdvance(txt) + space(2)
                return QRectF(close_x - 2, 0, 16, self.height())
            x += self._width(kind, txt, fm)
        return None

    def mousePressEvent(self, event) -> None:
        close = self._close_rect()
        if event.button() == Qt.MouseButton.LeftButton and close is not None and close.contains(event.position()):
            self.removed.emit()
        else:
            super().mousePressEvent(event)

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(font('small'))
        fm = p.fontMetrics()
        x, cy = 0.0, self.height() / 2
        for kind, txt, *index in self.items:
            if kind.endswith('+band'):
                kind = kind.removesuffix('+band')
                p.fillPath(
                    _rounded(QRectF(x + 1, cy - 7, 14, 14), RADIUS['control'] / 2),
                    t.q('accent', 0.16 if t.dark else 0.14),
                )
            if index:
                colour, symbol = self.replicate_mark(index[0])
                if kind == 'dots':
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(t.q(colour, self.dots_alpha()))
                    paint_symbol(p, symbol, QPointF(x + 7.5, cy), 3.5)
                else:
                    p.setPen(QPen(t.q(colour, self.dots_alpha()), 1.4))
                    for s in (-1, 1):
                        p.drawLine(QPointF(x + 4, cy - 3.5 * s), QPointF(x + 11, cy + 3.5 * s))
            elif kind == 'dots':
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(t.q('replicate', self.dots_alpha()))
                for dx, dy in ((3, 2), (8, -2.5), (12, 1.5)):
                    paint_symbol(p, 'o', QPointF(x + dx, cy + dy), 2.5)
            elif kind == 'rings':
                p.setPen(QPen(t.q('text-secondary'), 1.3))
                p.setBrush(Qt.BrushStyle.NoBrush)
                for dx, dy in ((3.5, 2), (8.5, -2.5), (13, 1.5)):
                    p.drawEllipse(QPointF(x + dx, cy + dy), 2.4, 2.4)
            elif kind == 'mean':
                p.setPen(QPen(t.q('text-primary'), 1))
                p.drawLine(QPointF(x + 7.5, cy - 6), QPointF(x + 7.5, cy + 6))
                p.drawLine(QPointF(x + 5, cy - 6), QPointF(x + 10, cy - 6))
                p.drawLine(QPointF(x + 5, cy + 6), QPointF(x + 10, cy + 6))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(t.q('text-primary'))
                p.drawEllipse(QPointF(x + 7.5, cy), 3, 3)
            elif kind == 'line':
                pen = QPen(t.q(self.line_color), self.line_width)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawLine(QPointF(x + 1, cy), QPointF(x + 15, cy))
            elif kind == 'line-other':
                pen = QPen(t.q('text-tertiary'), 1.5, Qt.PenStyle.DashLine)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawLine(QPointF(x + 1, cy), QPointF(x + 15, cy))
            elif kind == 'line-secondary':
                pen = QPen(t.q('text-secondary'), 1.75)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawLine(QPointF(x + 1, cy), QPointF(x + 15, cy))
            elif kind in ('bars', 'bar'):
                pairs = (('accent', -2.5), ('text-secondary', 2.5)) if kind == 'bars' else (('text-secondary', 0),)
                for color, dy in pairs:
                    pen = QPen(t.q(color), 3)
                    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
                    p.setPen(pen)
                    p.drawLine(QPointF(x + 1, cy + dy), QPointF(x + 15, cy + dy))
            elif kind == 'diamond':
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(t.q('text-secondary'))
                p.drawPath(diamond(QPointF(x + 8, cy), 11))
            p.setPen(t.q('text-secondary'))
            p.drawText(QRectF(x + 20, 0, 400, self.height()), Qt.AlignmentFlag.AlignVCenter, txt)
            if kind == 'rings' and self.removable:
                close_x = x + 20 + fm.horizontalAdvance(txt) + space(2)
                icons.paint(p, 'x', t.q('text-tertiary'), close_x, cy - 6, 12, 2)
            x += self._width(kind, txt, fm)
        p.end()


def paint_symbol(p: QPainter, symbol: str, centre: QPointF, r: float) -> None:
    """Paint pyqtgraph's mark *symbol* — ``o`` circle, ``s`` square, ``t1`` triangle up — of half-size *r*
    at *centre*, in the painter's pen and brush."""
    x, y = centre.x(), centre.y()
    if symbol == 's':
        p.drawRect(QRectF(x - r, y - r, 2 * r, 2 * r))
    elif symbol == 't1':
        p.drawPolygon(QPolygonF([QPointF(x, y - r), QPointF(x + r, y + r), QPointF(x - r, y + r)]))
    else:
        p.drawEllipse(centre, r, r)


def diamond(centre: QPointF, size: float) -> QPainterPath:
    """A square diamond *size* px from tip to tip: the mark of a best fit, in a plot and in its legend."""
    half = size / 2
    path = QPainterPath()
    path.moveTo(centre.x(), centre.y() - half)
    path.lineTo(centre.x() + half, centre.y())
    path.lineTo(centre.x(), centre.y() + half)
    path.lineTo(centre.x() - half, centre.y())
    path.closeSubpath()
    return path


def paint_raised(p: QPainter, t: Theme, rect: QRectF, radius: float) -> None:
    """The raised surface a readout sits on: ``bg-raised`` inside a 1-px outline."""
    path = _rounded(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius)
    p.fillPath(path, t.q('bg-raised'))
    p.setPen(QPen(t.q('border-strong' if t.dark else 'border'), 1))
    p.drawPath(path)


class PlotHeader(QWidget):
    """A plot's header (DESIGN.md §7): the *title* in ``body-strong``, a quiet *description*, the *legend*
    and the view's *tools*, read as :func:`hbox` reads its items.

    One line where it holds them all whole. Where it does not, the legend takes a line of its own
    under it, at the right, and the title line keeps its room for the description, which is
    cut short only where even that line cannot hold it, its whole text on hover. The legend is
    the view's :class:`LegendRow`; the header follows the width its entries take.
    """

    def __init__(self, t: Theme, title: str, legend: LegendRow, tools: tuple | list = (), description: str = ''):
        super().__init__()
        self.legend = legend
        self.title = label(title, 'body-strong')
        self.description = ElidedLabel('', 'small', 'tertiary')
        self.tools = hbox(5, *tools, spacing=0)
        self._inline = hbox(spacing=0)  # the legend on the title line, a step after the description
        line = hbox(self.title, 3, self.description, self._inline, self.tools, spacing=0)
        line.setStretchFactor(self.description, 1)
        self._under = hbox(None, spacing=0)  # the legend on a line of its own
        self.setLayout(vbox(line, self._under, spacing=1))
        self._wrapped: bool | None = None
        self.set_description(description)

    def set_description(self, text: str) -> None:
        """Show *text* as the description, with the whole of it on hover."""
        self.description.set_full_text(text)
        self.description.setToolTip(text)
        self._place()

    def legend_wrapped(self) -> bool:
        """Whether the legend is on a line of its own, under the title line."""
        return bool(self._wrapped)

    def _description_width(self) -> int:
        return self.description.fontMetrics().horizontalAdvance(self.description.full_text)

    def _line_width(self) -> int:
        """The width of the title line without the legend: the title, the whole description and the tools."""
        description = self._description_width()
        return (
            self.title.sizeHint().width()
            + (space(3) + description if description else 0)
            + self.tools.sizeHint().width()
        )

    def _one_line_width(self) -> int:
        """The width one line takes with the legend on it."""
        return self._line_width() + space(4) + self.legend.minimumWidth()

    def _place(self) -> None:
        """Put the legend on the title line where one line holds it all, else under it."""
        wrap = self.width() < self._one_line_width()
        if wrap == self._wrapped:
            return
        self._wrapped = wrap
        (self._inline if wrap else self._under).removeWidget(self.legend)
        self._inline.setContentsMargins(0 if wrap else space(4), 0, 0, 0)
        (self._under if wrap else self._inline).addWidget(self.legend)
        self.updateGeometry()

    def minimumSizeHint(self) -> QSize:
        # The legend under the title line, the description cut to an ellipsis.
        least = self.title.sizeHint().width() + self.tools.minimumSize().width()
        return QSize(max(least, self.legend.minimumWidth()), super().minimumSizeHint().height())

    def sizeHint(self) -> QSize:
        return QSize(self._one_line_width(), super().sizeHint().height())

    def event(self, event: QEvent) -> bool:
        if event.type() in (QEvent.Type.LayoutRequest, QEvent.Type.Resize):
            self._place()  # a resize, or the legend's entries changed its width
        return super().event(event)


class ReadoutCard(QWidget):
    """The values under the pointer as a card at a plot's top-right corner (DESIGN.md §6, Readout).

    A title in ``label`` ``text-secondary``, then one row per series: a 12-px stroke in its
    colour, its name, its value — right-aligned in tabular figures, so the decimal points
    line up — and a verdict, quieter where it is the negative one. The verdict column is
    left out where no row has one. :meth:`set_values` fills it; one pass over the fonts'
    metrics both sizes and paints it, so its size is always that of what it reads. It lets
    the pointer through to the plot, whose values it reads; its accessible name carries
    the reading.
    """

    def __init__(self, t: Theme, parent: QWidget | None = None):
        super().__init__(parent)
        self.t, self.title = t, ''
        self.rows: list[tuple[str, str, str, str, bool]] = []
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.set_values('', [])

    def set_values(self, title: str, rows: list[tuple[str, str, str, str, bool]]) -> None:
        """Show *title* over *rows*, each ``(colour token, name, value, verdict, quiet)``."""
        self.title, self.rows = title, rows
        self.setAccessibleName(f'{title}: ' + '; '.join(f'{n} {v}, {d}'.removesuffix(', ') for _c, n, v, d, _q in rows))
        self.setFixedSize(self.sizeHint())
        self.update()

    def sizeHint(self) -> QSize:
        return self._run(None)

    def minimumSizeHint(self) -> QSize:
        return self._run(None)

    def _run(self, p: QPainter | None) -> QSize:
        """Lay the card out from its fonts' metrics, painting it with *p* where one is given; its size."""
        t = self.t
        title_fm, name_fm, value_fm = (QFontMetrics(font(role)) for role in ('label', 'small', 'small-number'))
        left, top, gap, swatch = space(4), space(3), space(3), space(4)
        line = max(space(5), name_fm.height(), value_fm.height())
        name_w = max((name_fm.horizontalAdvance(n) for _c, n, *_ in self.rows), default=0)
        value_w = max(
            [value_fm.horizontalAdvance('00.00')] + [value_fm.horizontalAdvance(v) for _c, _n, v, *_ in self.rows]
        )
        verdict_w = max((name_fm.horizontalAdvance(d) for *_, d, _q in self.rows), default=0)
        body = swatch + gap + name_w + gap + value_w + (gap + verdict_w if verdict_w else 0)
        title_w = title_fm.horizontalAdvance(self.title)
        name_w += max(0, title_w - body)  # the names take the room a longer title leaves
        width = 2 * left + max(body, title_w)
        height = 2 * top + title_fm.height() + len(self.rows) * (space(1) + line)
        if p is not None:
            flags = Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextDontClip
            paint_raised(p, t, QRectF(0, 0, width, height), RADIUS['surface'])
            p.setFont(font('label'))
            p.setPen(t.q('text-secondary'))
            p.drawText(QRectF(left, top, title_w, title_fm.height()), flags, self.title)
            y = top + title_fm.height()
            for color, name, value, verdict, quiet in self.rows:
                y += space(1)
                cy = y + line / 2
                pen = QPen(t.q(color), 2)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawLine(QPointF(left + 1, cy), QPointF(left + swatch - 1, cy))
                x = left + swatch + gap
                p.setFont(font('small'))
                p.setPen(t.q('text-primary'))
                p.drawText(QRectF(x, y, name_w, line), flags, name)
                x += name_w + gap
                p.setFont(font('small-number'))
                p.drawText(QRectF(x, y, value_w, line), flags | Qt.AlignmentFlag.AlignRight, value)
                if verdict:
                    p.setFont(font('small'))
                    p.setPen(t.q('text-secondary' if quiet else 'text-primary'))
                    p.drawText(QRectF(x + value_w + gap, y, verdict_w, line), flags, verdict)
                y += line
        return QSize(width, height)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._run(p)
        p.end()


class ValueTag(QWidget):
    """The pointer's value at the top end of its hairline, on the readout card's raised surface."""

    def __init__(self, t: Theme, parent: QWidget | None = None):
        super().__init__(parent)
        self.t, self.text = t, ''
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_text(self, text: str) -> None:
        self.text = text
        self.setFixedSize(QFontMetrics(font('small-number')).horizontalAdvance(text) + 2 * space(3), SIZE['badge'])
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_raised(p, self.t, QRectF(self.rect()), self.height() / 2)
        p.setFont(font('small-number'))
        p.setPen(self.t.q('text-primary'))
        p.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, self.text)
        p.end()


class Table(QWidget):
    """Rows of results under a header (DESIGN.md §6): the header in ``label`` ``text-tertiary``,
    hairlines between rows, numbers right-aligned in tabular figures.

    *columns* are ``(header, role, tone)``: a column in a ``number`` role is right-aligned.
    The first column, the names, wraps between words, and so does any other cell of words
    alone; a cell holding a number, and one of a single token such as a unit, stays on its
    line, so a number or a unit is never broken (where words precede a number the caller
    puts them on a line of their own with ``<br>``). A bound — a sign, a space and a number,
    ``< 0.001`` — reads on one line where its column has room and breaks after its sign
    where it has not, so the column needs no more width than the number. Cells are rich text — data in them is
    escaped by the caller — and selectable, so a value can be copied. :meth:`cell` reaches
    one cell, for its tooltip. *gap* is the step of the spacing scale between columns, narrower
    for a table of many columns in the side panel.
    """

    def __init__(self, t: Theme, columns: list[tuple[str, str, str | None]], gap: int = 3):
        super().__init__()
        self.t, self.columns = t, columns
        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(space(gap))
        self.grid.setVerticalSpacing(0)
        self.setLayout(self.grid)
        self._cells: list[list[QLabel]] = []
        self.set_rows([])

    @staticmethod
    def _right(role: str) -> bool:
        return role.startswith('number') or role == 'small-number'

    @staticmethod
    def _wraps(html: str) -> bool:
        """Whether a cell may break between its words: words alone, with no figure a break could split, or a bound."""
        plain = QTextDocumentFragment.fromHtml(html).toPlainText().strip()
        words = ' ' in plain and not any(ch.isdigit() for ch in plain)
        sign, _space, number = plain.partition(' ')
        return words or (sign in ('<', '>', '≤', '≥') and bool(number) and ' ' not in number)

    def set_rows(self, rows: list[list[str]]) -> None:
        """Show *rows*, one list of cell texts per row, under the header."""
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget() is not None:
                drop(item.widget())
        middle = Qt.AlignmentFlag.AlignVCenter
        for c, (head, role, _tone) in enumerate(self.columns):
            lbl = label(head, 'label', 'tertiary')
            lbl.setMinimumHeight(SIZE['control'])
            lbl.setAlignment(
                (Qt.AlignmentFlag.AlignRight if self._right(role) else Qt.AlignmentFlag.AlignLeft) | middle
            )
            self.grid.addWidget(lbl, 0, c)
        self.grid.addWidget(hairline(), 1, 0, 1, len(self.columns))
        self._cells = []
        for i, texts in enumerate(rows):
            r = 2 + 2 * i
            cells = []
            for c, ((_head, role, tone), text) in enumerate(zip(self.columns, texts, strict=True)):
                lbl = copyable(label(text, role, tone, rich=True))
                lbl.setMinimumHeight(SIZE['control'])
                lbl.setWordWrap(c == 0 or self._wraps(text))
                lbl.setAlignment(
                    (Qt.AlignmentFlag.AlignRight if self._right(role) else Qt.AlignmentFlag.AlignLeft) | middle
                )
                self.grid.addWidget(lbl, r, c)
                cells.append(lbl)
            self._cells.append(cells)
            if i < len(rows) - 1:
                self.grid.addWidget(hairline(), r + 1, 0, 1, len(self.columns))
        self.grid.setColumnStretch(0, 1)

    def cell(self, row: int, col: int) -> QLabel:
        """The label of one cell."""
        return self._cells[row][col]

    def texts(self) -> list[list[str]]:
        """Every cell's text, row by row, as the table shows it."""
        return [[cell.text() for cell in row] for row in self._cells]


def test_line(t: Theme, icon: str, tone: str, text: str, p: str, tooltip: str = '') -> QWidget:
    """One test of a fit in a list of tests (DESIGN.md §8): its mark in *tone*, what it found, its p-value at the
    right; *tooltip* is the test's full sentence. The text wraps where the panel is narrow; the p-value keeps its line.
    """
    row = QWidget()
    row.setMinimumHeight(SIZE['control'])
    found = wrapped(text, 'body', None)
    value = copyable(label(p, 'small-number', 'secondary'))
    lay = hbox(Icon(t, icon, tone), found, value, spacing=3)
    lay.setStretchFactor(found, 1)
    row.setLayout(lay)
    row.setToolTip(tooltip)
    row.setAccessibleName(f'{text}, {p}')
    return row


class ShiftBar(QWidget):
    """A diverging bar of a fitted input shift *z* in σ: the ±1 σ band shaded, axis ±4 σ.

    *z* ``None`` (an input stated as a range, which has no σ) draws the band and the axis alone.
    """

    def __init__(self, theme: Theme, z: float | None):
        super().__init__()
        self.t, self.z = theme, z
        self.setFixedSize(84, 16)

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, s = w / 2, (w / 2 - 2) / 4
        p.fillRect(QRectF(cx - s, 3, 2 * s, h - 6), t.q('bg-subtle'))
        p.setPen(QPen(t.q('border-strong'), 1))
        p.drawLine(QPointF(cx, 1), QPointF(cx, h - 1))
        if self.z is not None:
            z = max(-4, min(4, self.z))
            x1, x2 = sorted((cx, cx + z * s))
            p.fillPath(_rounded(QRectF(x1, 5, max(x2 - x1, 1.5), h - 10), 1.5), t.q('text-secondary'))
        p.end()


class SpreadBar(QWidget):
    """What an input's stated uncertainty spans, on one ±20 % axis shared by every row so the
    inputs compare at a glance: the band from *span*'s low to high offset in percent (±2σ, or a
    range's ends), the entered value at the centre. *span* ``None`` draws the entered value alone;
    a band past the axis runs to its edge."""

    TICK = 20.0  # the outermost tick, in percent
    INSET = 20  # px from the column edge to that tick, room to centre its label

    @classmethod
    def scale(cls, width: int) -> float:
        """Pixels per percent on a bar *width* wide."""
        return (width / 2 - cls.INSET) / cls.TICK

    def __init__(self, t: Theme, span: tuple[float, float] | float | None, width: int = 104):
        super().__init__()
        self.t = t
        self.setFixedSize(width, 20)
        self.set_span(span)

    def set_span(self, span: tuple[float, float] | float | None) -> None:
        """Show *span*: ``(low, high)`` offsets in percent, a half-width, or ``None``."""
        self.span = (-span, span) if isinstance(span, (int, float)) else span
        self.update()

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        s = self.scale(w)
        p.setPen(QPen(t.q('border'), 1))
        p.drawLine(QPointF(2, cy), QPointF(w - 2, cy))
        for v in (-20, -10, 10, 20):
            x = cx + v * s
            p.drawLine(QPointF(x, cy - 2), QPointF(x, cy + 2))
        if self.span is not None and self.span[1] > self.span[0]:
            x1, x2 = (min(max(cx + v * s, 1.0), w - 1.0) for v in self.span)
            p.fillPath(_rounded(QRectF(x1, cy - 4, x2 - x1, 8), 2), t.q('accent', 0.22))
            pen = QPen(t.q('accent'), 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            for x in (x1, x2):
                p.drawLine(QPointF(x, cy - 5), QPointF(x, cy + 5))
        p.setPen(QPen(t.q('text-primary'), 1.5))
        p.drawLine(QPointF(cx, cy - 6), QPointF(cx, cy + 6))
        p.end()


class AxisScale(QWidget):
    """The tick labels of a column of :class:`SpreadBar`, read once in the column's header."""

    def __init__(self, t: Theme, width: int = 104):
        super().__init__()
        self.t = t
        self.setFixedSize(width, 28)
        self.setToolTip('Offset from the entered value, in percent.')

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(font('small-number'))
        p.setPen(t.q('text-tertiary'))
        w, h = self.width(), self.height()
        s = SpreadBar.scale(w)
        # every label centred on its tick; the last one carries the axis unit
        for v, txt in ((-20, '−20'), (0, '0'), (20, '+20 %')):
            x = w / 2 + v * s
            p.drawText(QRectF(x - 20, 0, 40, h), Qt.AlignmentFlag.AlignCenter, txt)
        p.end()


class CompactIntervals(QWidget):
    """The interval chart stacked for the side panel: each row's label and numbers on one line,
    its bar on a shared log axis below, the tick labels once at the bottom.

    *rows* are as :class:`IntervalChart` takes them, *ticks* ``(value, label)`` pairs. A row
    may carry a ``note`` in place of its bars, for a reading whose bars cannot be drawn. Where
    a row's label and numbers do not fit on one line, every row puts its numbers on a line
    of their own under the label.
    """

    ROW = 46
    LINE = 18

    def __init__(self, t: Theme, rows: list[dict], lo: float, hi: float, ticks: list[tuple[float, str]]):
        super().__init__()
        self.t = t
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.set_rows(rows, lo, hi, ticks)

    def set_rows(self, rows: list[dict], lo: float, hi: float, ticks: list[tuple[float, str]]) -> None:
        """Show *rows* on the axis *lo* to *hi* with *ticks*."""
        self.rows, self.lo, self.hi, self.ticks = rows, lo, hi, ticks
        self._fit_height()
        self.updateGeometry()
        self.setAccessibleDescription(
            '; '.join(
                f'{row["label"]}: {row["text"]}' + (f' ({row["note"]})' if row.get('note') else '') for row in rows
            )
        )
        self.update()

    def minimumSizeHint(self) -> QSize:
        # Stacked, each row's label and numbers on lines of their own.
        labels, numbers = QFontMetrics(font('small')), QFontMetrics(font('number'))
        widest = max(
            (max(labels.horizontalAdvance(row['label']), numbers.horizontalAdvance(row['text'])) for row in self.rows),
            default=0,
        )
        return QSize(widest, self.minimumHeight())

    def sizeHint(self) -> QSize:
        return self.minimumSizeHint()

    def _stacked(self) -> bool:
        """Whether a row's label and numbers are too wide for one line at the width the chart has."""
        labels, numbers = QFontMetrics(font('small')), QFontMetrics(font('number'))
        return any(
            labels.horizontalAdvance(row['label']) + space(3) + numbers.horizontalAdvance(row['text']) > self.width()
            for row in self.rows
        )

    def _row_height(self) -> int:
        return self.ROW + (self.LINE if self._stacked() else 0)

    def _fit_height(self) -> None:
        height = len(self.rows) * self._row_height() + 20
        if height != self.height() or self.minimumHeight() != height:
            self.setFixedHeight(height)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_height()

    def tick_room(self) -> tuple[float, float]:
        """The span the tick labels keep to: the chart's width, so an end tick's label stays whole."""
        return 0.0, float(self.width())

    def tick_rects(self) -> list[tuple[str, QRectF]]:
        """The tick labels drawn at the chart's width, and their boxes (:func:`spaced_ticks`)."""
        return spaced_ticks(self.ticks, self._x, QFontMetrics(font('small-number')), *self.tick_room())

    def _x(self, v: float) -> float:
        w = self.width() - 12
        return 6 + (math.log10(v) - math.log10(self.lo)) / (math.log10(self.hi) - math.log10(self.lo)) * w

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        stacked, row_h = self._stacked(), self._row_height()
        bottom = len(self.rows) * row_h
        p.setFont(font('small-number'))
        p.setPen(QPen(t.q('grid'), 1))
        for tk, _text in self.ticks:
            x = self._x(tk)
            p.drawLine(QPointF(x, 22 + (self.LINE if stacked else 0)), QPointF(x, bottom))
        p.setPen(t.q('text-tertiary'))
        for text, box in self.tick_rects():
            p.drawText(box.translated(0, bottom + 2), Qt.AlignmentFlag.AlignHCenter, text)
        for i, row in enumerate(self.rows):
            y = i * row_h
            p.setFont(font('small'))
            p.setPen(t.q('text-secondary'))
            p.drawText(QRectF(0, y, w, self.LINE), Qt.AlignmentFlag.AlignVCenter, row['label'])
            p.setFont(font('number'))
            p.setPen(t.q('text-primary'))
            if stacked:
                p.drawText(QRectF(0, y + self.LINE, w, self.LINE), Qt.AlignmentFlag.AlignVCenter, row['text'])
            else:
                p.drawText(
                    QRectF(0, y, w, self.LINE), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, row['text']
                )
            cy = y + 31 + (self.LINE if stacked else 0)
            p.setPen(QPen(t.q('border'), 1))
            p.drawLine(QPointF(6, cy), QPointF(w - 6, cy))
            col = t.q(row['color'])
            if row.get('note'):
                p.setFont(font('small'))
                p.setPen(t.q('text-tertiary'))
                p.drawText(QRectF(6, cy - 9, w - 12, 18), Qt.AlignmentFlag.AlignVCenter, row['note'])
            for a, b in row['segments']:
                pen = QPen(col, 4)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawLine(QPointF(self._x(a), cy), QPointF(self._x(b), cy))
            if row.get('est') is not None:
                p.setPen(QPen(t.q('bg-surface'), 2))
                p.setBrush(col)
                p.drawEllipse(QPointF(self._x(row['est']), cy), 5, 5)
        p.end()


# ── Inspector ──────────────────────────────────────────────────────────────────────


class SectionHeader(QAbstractButton):
    """A collapsible inspector section's header: chevron, title, a quiet *trailing* summary, and the
    warning mark in tone *flag* after the title where the section carries a result's warning."""

    toggled_open = pyqtSignal(bool)
    HEIGHT = 32

    def __init__(self, theme: Theme, title: str, open_: bool = True, trailing: str = '', flag: str = ''):
        super().__init__()
        self.t, self._title, self._open, self._trailing, self._flag = theme, title, open_, trailing, flag
        self.setFixedHeight(self.HEIGHT)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(title)
        self.clicked.connect(lambda: self.set_open(not self._open))

    def set_open(self, open_: bool) -> None:
        """Open or close the section; :attr:`toggled_open` says which."""
        if open_ != self._open:
            self._open = open_
            self.update()
            self.toggled_open.emit(open_)

    def set_trailing(self, trailing: str) -> None:
        """Show *trailing* as the section's quiet summary."""
        self._trailing = trailing
        self.updateGeometry()
        self.update()

    #: Where the title starts, past the chevron.
    TITLE_X = 18

    def minimumSizeHint(self) -> QSize:
        width = self.TITLE_X + QFontMetrics(font('body-strong')).horizontalAdvance(self._title)
        if self._flag:
            width += space(3) + 16
        if self._trailing:
            width += space(3) + QFontMetrics(font('small')).horizontalAdvance(self._trailing)
        return QSize(width, self.HEIGHT)

    def sizeHint(self) -> QSize:
        return self.minimumSizeHint()

    def paintEvent(self, _):
        t = self.t
        h = self.HEIGHT
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        chevron = 'chevron-down' if self._open else 'chevron-right'
        icons.paint(p, chevron, t.q('text-tertiary'), -2, (h - 16) / 2, 16, 2)
        p.setFont(font('body-strong'))
        p.setPen(t.q('text-primary'))
        p.drawText(QRectF(self.TITLE_X, 0, self.width(), h), Qt.AlignmentFlag.AlignVCenter, self._title)
        if self._flag:
            # The mark Diagnostics gives the same finding, after the title.
            x = self.TITLE_X + QFontMetrics(font('body-strong')).horizontalAdvance(self._title) + space(3)
            icons.paint(p, 'alert-circle', t.q(self._flag), x, (h - 16) / 2, 16)
        if self._trailing:
            p.setFont(font('small'))
            p.setPen(t.q('text-tertiary'))
            right = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
            p.drawText(QRectF(0, 0, self.width(), h), right, self._trailing)
        if self.hasFocus():
            _focus_ring(p, t, QRectF(self.rect()))
        p.end()


def section(
    theme: Theme,
    title: str,
    content: QWidget | None,
    open_: bool = True,
    first: bool = False,
    trailing: str = '',
    flag: str = '',
) -> QWidget:
    """An inspector section: a hairline above (unless *first*), the header, and *content* while open.

    *flag* is the tone of the warning mark after the title (:class:`SectionHeader`).

    The header opens and closes it; the returned widget's ``header`` is that
    :class:`SectionHeader`, for its trailing summary.
    """
    w = QWidget()
    lay = vbox(spacing=0)
    # The layout is the section's before anything is shown or hidden in it, so no part is ever a window of its own.
    w.setLayout(lay)
    if not first:
        lay.addWidget(hairline())
        lay.addSpacing(space(3))
    header = SectionHeader(theme, title, open_ and content is not None, trailing, flag)
    lay.addWidget(header)
    closed = QWidget()
    closed.setFixedHeight(space(3))
    lay.addWidget(closed)
    if content is not None:
        body = QWidget()
        body.setLayout(vbox(2, content, 5, spacing=0))
        lay.addWidget(body)

        def show(on: bool) -> None:
            body.setVisible(on)
            closed.setVisible(not on)

        header.toggled_open.connect(show)
        show(open_)
    w.header = header
    return w


# ── Canvas forms ───────────────────────────────────────────────────────────────────


def wrapped(text: str, role: str = 'body', tone: str | None = 'secondary', rich: bool = False) -> QLabel:
    """A label that wraps to the width it is given, in type role *role* and *tone*."""
    lbl = label(text, role, tone, rich)
    lbl.setWordWrap(True)
    lbl.setMinimumWidth(1)
    return lbl


_ZERO_WIDTH_SPACE = '​'


def _graphemes(word: str) -> list[str]:
    """*word* as the characters a reader sees: a letter with its accents, an emoji with its joined parts, each one.

    Qt counts the boundaries in UTF-16 code units, which a character past U+FFFF takes two of.
    """
    finder = QTextBoundaryFinder(QTextBoundaryFinder.BoundaryType.Grapheme, word)
    index, units = {0: 0}, 0
    for i, char in enumerate(word):
        units += 2 if ord(char) > 0xFFFF else 1
        index[units] = i + 1
    cuts = [0]
    while (unit := finder.toNextBoundary()) != -1:
        cuts.append(index[unit])
    return [word[a:b] for a, b in zip(cuts, cuts[1:])]


class BreakingLabel(QLabel):
    """Plain text that wraps between words and, inside a word wider than the label, between its characters.

    For a name the user typed — one long word, or words joined by underscores — that must be
    read whole at any width the panel gives it; :attr:`full_text` keeps it as typed, and is
    the label's accessible name.
    """

    def __init__(self, text: str = '', role: str = 'body', tone: str | None = None):
        super().__init__()
        self.setFont(font(role))
        if tone:
            self.setProperty('tone', tone)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(True)
        self.setMinimumWidth(1)
        self.full_text = ''
        self.set_full_text(text)

    def set_full_text(self, text: str) -> None:
        """Show *text*, broken to the width the label has."""
        self.full_text = text
        self.setAccessibleName(text)
        self._break()

    def _broken(self, width: int) -> str:
        """The text with a break allowed between the characters of every word wider than *width*."""
        fm = self.fontMetrics()
        words = self.full_text.split(' ')
        return ' '.join(_ZERO_WIDTH_SPACE.join(_graphemes(w)) if fm.horizontalAdvance(w) > width else w for w in words)

    def _break(self) -> None:
        text = self._broken(self.contentsRect().width())
        if text != self.text():
            self.setText(text)

    def heightForWidth(self, width: int) -> int:
        margins = self.contentsMargins()
        inner = width - margins.left() - margins.right()
        rect = self.fontMetrics().boundingRect(0, 0, inner, 1 << 20, Qt.TextFlag.TextWordWrap, self._broken(inner))
        return rect.height() + margins.top() + margins.bottom()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._break()


class ElidedLabel(QLabel):
    """One line of plain text that gives way to its neighbours: cut short with an ellipsis where it does not fit.

    Its width is whatever the layout leaves it, so a row it sits in never grows past its
    other contents for it; :attr:`full_text` keeps the whole line.
    """

    def __init__(self, text: str = '', role: str = 'body', tone: str | None = None):
        super().__init__()
        self.setFont(font(role))
        if tone:
            self.setProperty('tone', tone)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.full_text = ''
        self.set_full_text(text)

    def set_full_text(self, text: str) -> None:
        """Show *text*, cut to the width the label has."""
        self.full_text = text
        self._elide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        self.setText(self.fontMetrics().elidedText(self.full_text, Qt.TextElideMode.ElideRight, self.width()))


def drop(widget: QWidget) -> None:
    """Take *widget* off the screen now and delete it once its events are handled."""
    widget.hide()
    widget.setParent(None)
    widget.deleteLater()


def canvas_section(title: str, content: QWidget, summary: str = '', first: bool = False) -> QWidget:
    """A section of a canvas form: a hairline above unless *first*, the plain title, a quiet *summary*, *content*."""
    w = QWidget()
    lay = vbox(spacing=0)
    if not first:
        lay.addSpacing(space(6))
        lay.addWidget(hairline())
        lay.addSpacing(space(5))
    head = [label(title, 'body-strong')]
    if summary:
        head += [3, label(summary, 'small', 'tertiary')]
    lay.addLayout(hbox(*head, None, spacing=0))
    lay.addSpacing(space(3))
    lay.addWidget(content)
    w.setLayout(lay)
    return w


class Problem(QWidget):
    """What is wrong with the statement above it: an amber mark and the sentences a run would refuse with."""

    def __init__(self, t: Theme):
        super().__init__()
        self.text = wrapped('', 'small', 'secondary')
        self.text.setMaximumWidth(SIZE['measure'])
        lay = hbox(vbox(Icon(t, 'alert-circle', 'warning', 14), None, margins=(0, 1, 0, 0)), self.text, None)
        lay.setStretchFactor(self.text, 1)  # the text takes the width up to its measure, the stretch the rest
        self.setLayout(lay)
        self.hide()

    def show_problems(self, problems: list[str]) -> None:
        """Show *problems*, one per line; hide the mark when there are none."""
        self.text.setText('\n'.join(problems))
        self.setVisible(bool(problems))


# ── Saved figures ──────────────────────────────────────────────────────────────────


class Figure(QWidget):
    """A saved figure's surface: its plots drawn off screen on ``bg-surface`` of *t*, the light theme on white
    (DESIGN.md §7)."""

    def __init__(self, t: Theme):
        super().__init__()
        self.t = t
        self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), self.t.q('bg-surface'))
        p.end()


class PaintedNote(QWidget):
    """A paragraph of rich text painted in a given theme and wrapped to *width*, for a saved figure.

    Reads in ``text-secondary`` whatever the window's palette, as :class:`PaintedText` does, in
    type role *role* or, where given, *text_font*.
    """

    def __init__(self, t: Theme, text: str, role: str, width: int, text_font: QFont | None = None):
        super().__init__()
        self.t, self.text, self.role = t, text, role
        self.doc = QTextDocument()
        self.doc.setDocumentMargin(0)
        self.doc.setDefaultFont(text_font or font(role))
        self.doc.setHtml(f'<span style="color:{t["text-secondary"]}">{text}</span>')
        self.doc.setTextWidth(width)
        self.setFixedSize(width, math.ceil(self.doc.size().height()))

    def paintEvent(self, _):
        p = QPainter(self)
        self.doc.drawContents(p)
        p.end()


class PaintedText(QWidget):
    """One line of text painted in a given theme, for a saved figure whatever the window's palette.

    ``body-strong`` is a title in ``text-primary``; every other role reads in ``text-secondary``.
    It is drawn in *role*'s font or, where given, *text_font* (the plot text of a titration figure).
    """

    def __init__(self, t: Theme, text: str, role: str, text_font: QFont | None = None):
        super().__init__()
        self.t, self.text, self.role = t, text, role
        self.text_font = text_font or font(role)
        metrics = QFontMetrics(self.text_font)
        self.setFixedHeight(metrics.height() + space(2))
        self.setMinimumWidth(metrics.horizontalAdvance(text))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setFont(self.text_font)
        p.setPen(self.t.q('text-primary' if self.role == 'body-strong' else 'text-secondary'))
        p.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text)
        p.end()
