"""The component layer: layout helpers and the custom-painted controls of the design.

QSS (:mod:`gui.design.stylesheet`) styles what Qt's widgets can express; every control
here is painted where it cannot — a menu chevron on the token grid, a selection bar, a
focus ring, a field, a slider — from the same tokens (:mod:`gui.design.tokens`) and
icons (:mod:`gui.design.icons`). Each control takes the resolved :class:`Theme` it is
drawn in.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen, QTextDocument
from PyQt6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from gui.design import icons
from gui.design.tokens import RADIUS, SIZE, Theme, font, space

#: The platform's window-button colours (close, minimise, zoom): drawn where a frameless
#: window paints its own title bar, so they are the platform's and not design tokens.
WINDOW_BUTTON_COLOURS = ('#FF5F57', '#FEBC2E', '#28C840')

#: Corner radius of a popover card and of a window of its own.
#: Room a popover leaves around its card for the soft shadow, in px.
SHADOW = 12


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
    button, ``primary`` an accent fill. Painting keeps the icon-label gap, the menu
    chevron (*menu*) and the focus ring on the token grid. *checked* makes it a toggle,
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
        self._font = font('body-strong' if variant == 'primary' else 'body')
        if variant == 'icon':
            self.setFixedWidth(SIZE['control'])
        else:
            fm = QFontMetrics(self._font)
            w = space(3) + (16 + space(2) if icon_name else 0) + fm.horizontalAdvance(text)
            w += (space(2) + 12 if menu else 0) + (space(4) if variant == 'primary' else space(3))
            self.setFixedWidth(w)

    def set_text(self, text: str) -> None:
        """Change the label in place; the width stays, so a toolbar never shifts."""
        self._text = text
        self.update()

    def paintEvent(self, _):
        t = self.t
        h = SIZE['control']
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        bg = None
        if self.variant == 'primary':
            bg = t.q('accent-hover' if self.underMouse() else 'accent')
        elif self.isChecked():
            bg = t.q('bg-subtle')
        elif self.underMouse():
            bg = t.q('bg-hover')
        if bg is not None:
            p.fillPath(_rounded(r, RADIUS['control']), bg)
        fg = t.q('on-accent') if self.variant == 'primary' else t.q('text-primary')
        ic = t.q('on-accent') if self.variant == 'primary' else t.q('text-secondary')
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
                icons.paint(p, 'chevron-down', t.q('text-tertiary'), r.width() - space(3) - 12, (h - 12) / 2, 12, 2)
        if self.hasFocus():
            _focus_ring(p, t, r)
        p.end()


def tool_button(theme: Theme, text: str | None, icon_name: str, checked: bool = False, menu: bool = False) -> Button:
    """A toolbar or header button: ``ghost`` with a label, ``icon`` without one."""
    return Button(theme, 'ghost' if text else 'icon', text or '', icon_name, menu, checked)


def primary_button(theme: Theme, text: str, icon_name: str) -> Button:
    """The one primary action of a toolbar (Run fit, Run analysis)."""
    return Button(theme, 'primary', text, icon_name)


def link_button(text: str) -> QPushButton:
    """An inline command in accent text, styled by the stylesheet's ``link`` role."""
    b = QPushButton(text)
    b.setProperty('role', 'link')
    b.setFont(font('body'))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    return b


class OutlineButton(QWidget):
    """A secondary command: control height, 1-px ``border-strong`` outline, label in body-strong."""

    def __init__(self, t: Theme, text: str, icon_name: str = ''):
        super().__init__()
        self.t, self.text, self.icon = t, text, icon_name
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
        p.setPen(QPen(t.q('border-strong'), 1))
        p.drawPath(path)
        x = space(4)
        if self.icon:
            icons.paint(p, self.icon, t.q('text-secondary'), x, (h - 16) / 2, 16)
            x += 16 + space(2)
        p.setFont(font('body-strong'))
        p.setPen(t.q('text-primary'))
        p.drawText(QRectF(x, 0, r.width() - x, h), Qt.AlignmentFlag.AlignVCenter, self.text)
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


class StatusDot(QWidget):
    """An 8-px dot in token *tone*: what the status bar's left-hand message is about."""

    def __init__(self, t: Theme, tone: str):
        super().__init__()
        self.t, self.tone = t, tone
        self.setFixedSize(8, 8)

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
        self.t, self._text, self._icon, self._status = theme, text, icon_name, status
        self.setCheckable(True)
        self.setChecked(selected)
        self.setFixedHeight(SIZE['nav-item'])
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self) -> QSize:
        return QSize(180, SIZE['nav-item'])

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
        p.drawText(QRectF(32, 0, r.width() - 56, r.height()), Qt.AlignmentFlag.AlignVCenter, self._text)
        paint_status_glyph(p, t, self._status, r.width() - 14, r.height() / 2)
        if self.hasFocus():  # keyboard focus only (TabFocus policy)
            _focus_ring(p, t, r)
        p.end()


class SessionSwitcher(QAbstractButton):
    """The session on screen, at the top of the sidebar; a click opens :class:`SessionPopover`.

    The trailing pill counts the open sessions and carries an accent dot while another
    session is busy (*busy*). *open_* draws it with the popover open.
    """

    def __init__(self, theme: Theme, name: str, detail: str, count: int = 1, busy: int = 0, open_: bool = False):
        super().__init__()
        self.t, self._name, self._detail, self._count, self._busy = theme, name, detail, count, busy
        self.setCheckable(True)
        self.setChecked(open_)
        self.setFixedHeight(SIZE['switcher'])
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)

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
        right = 28
        if self._count > 1:
            p.setFont(font('small-number'))
            txt = str(self._count)
            pw = QFontMetrics(p.font()).horizontalAdvance(txt) + 12
            pill = QRectF(r.width() - 28 - pw, 13, pw, SIZE['badge'])
            p.fillPath(_rounded(pill, SIZE['badge'] / 2), t.q('bg-subtle'))
            p.setPen(t.q('text-secondary'))
            p.drawText(pill, Qt.AlignmentFlag.AlignCenter, txt)
            if self._busy:
                p.setPen(QPen(t.q('bg-surface'), 2))
                p.setBrush(t.q('accent'))
                p.drawEllipse(QPointF(pill.right() - 1, pill.top() + 1), 4, 4)
            right += pw + 6
        p.setPen(t.q('text-primary'))
        p.setFont(font('body-strong'))
        p.drawText(QRectF(44, 6, r.width() - 44 - right, 17), Qt.AlignmentFlag.AlignVCenter, self._name)
        p.setPen(t.q('text-secondary'))
        p.setFont(font('small'))
        p.drawText(QRectF(44, 22, r.width() - 44 - right, 16), Qt.AlignmentFlag.AlignVCenter, self._detail)
        icons.paint(p, 'updown', t.q('text-tertiary'), r.width() - 24, 14, 16)
        p.end()


# ── Popovers and menus ─────────────────────────────────────────────────────────────


def paint_popover(p: QPainter, t: Theme, card: QRectF) -> None:
    """A popover's raised card with its soft shadow: stacked translucent rounded
    rectangles, offset down, under a ``bg-raised`` fill and a 1-px ``border``."""
    for i in range(10, 0, -1):
        alpha = (0.07 if t.dark else 0.018) * (11 - i) / 10
        shadow = card.adjusted(-i, -i + 4, i, i + 4)
        p.fillPath(_rounded(shadow, RADIUS['popover'] + i), QColor(0, 0, 0, int(255 * alpha)))
    path = _rounded(card, RADIUS['popover'])
    p.fillPath(path, t.q('bg-raised'))
    p.setPen(QPen(t.q('border'), 1))
    p.drawPath(path)


def _menu_separator(p: QPainter, t: Theme, x0: float, y: float, w: float) -> float:
    p.fillRect(QRectF(x0 + 8, y + 4, w - 16, 1), t.q('border'))
    return y + 9


def _menu_command(
    p: QPainter, t: Theme, x0: float, y: float, w: float, item: tuple, icon_x: float, text_x: float, key_inset: float
) -> None:
    ic, text, key = item
    row = SIZE['menu-item']
    icons.paint(p, ic, t.q('text-secondary'), x0 + icon_x, y + (row - 16) / 2, 16)
    p.setFont(font('body'))
    p.setPen(t.q('text-primary'))
    p.drawText(QRectF(x0 + text_x, y, w - 100, row), Qt.AlignmentFlag.AlignVCenter, text)
    if key:
        p.setFont(font('small'))
        p.setPen(t.q('text-tertiary'))
        right = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        p.drawText(QRectF(x0, y, w - key_inset, row), right, key)


class PopoverMenu(QWidget):
    """An open menu: a popover card of command rows and a quiet footnote under them.

    *items* are ``(icon, text, shortcut)`` rows, ``None`` a separator; *note* is the
    footnote, wrapped to the card. *hover* is the index of the row under the pointer
    (``None`` for none). The widget is *width* plus the shadow margin on every side, so
    its card's top-left sits at (``SHADOW``, ``SHADOW - 4``).
    """

    PAD = 6

    def __init__(self, t: Theme, parent: QWidget, items: list, note: str, width: int, hover: int | None = 0):
        super().__init__(parent)
        self.t, self.items, self.note, self.card_w, self.hover = t, items, note, width, hover
        rows = sum(9 if it is None else SIZE['menu-item'] for it in items)
        h = self.PAD + rows + 9 + self._note_h() + space(3) + self.PAD
        self.setFixedSize(width + 2 * SHADOW, h + 2 * SHADOW)

    def _note_h(self) -> int:
        fm = QFontMetrics(font('small'))
        w = self.card_w - 2 * self.PAD - 2 * space(3)
        return fm.boundingRect(0, 0, w, 200, Qt.TextFlag.TextWordWrap, self.note).height()

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = QRectF(SHADOW, SHADOW - 4, self.card_w, self.height() - 2 * SHADOW)
        paint_popover(p, t, card)
        x0, w = card.left() + self.PAD, card.width() - 2 * self.PAD
        y = card.top() + self.PAD
        for k, it in enumerate(self.items):
            if it is None:
                y = _menu_separator(p, t, x0, y, w)
                continue
            if k == self.hover:
                p.fillPath(_rounded(QRectF(x0, y, w, SIZE['menu-item']), RADIUS['control']), t.q('bg-hover'))
            _menu_command(p, t, x0, y, w, it, icon_x=space(3), text_x=40, key_inset=space(3))
            y += SIZE['menu-item']
        y = _menu_separator(p, t, x0, y, w) + space(2)
        p.setFont(font('small'))
        p.setPen(t.q('text-tertiary'))
        p.drawText(
            QRectF(x0 + space(3), y, w - 2 * space(3), self._note_h()),
            Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft,
            self.note,
        )
        p.end()


class SessionPopover(QWidget):
    """The session switcher open: every open session with its state, then the session commands.

    *sessions* are dicts with ``name``, ``detail``, ``state`` (``warning``, ``running``,
    ``stale`` or ``done``), ``status`` (the state in words, right of the name) and, while
    running, ``progress`` (0–1); the first is the session on screen. *commands* are
    ``(icon, text, shortcut)`` rows, ``None`` a separator.
    """

    PAD = 6
    ROW_H = 52
    HEAD_H = 28

    def __init__(
        self,
        t: Theme,
        parent: QWidget,
        sessions: list[dict],
        commands: list,
        width: int = 340,
        title: str = 'Open sessions',
        title_hint: str = '',
    ):
        super().__init__(parent)
        self.t, self.sessions, self.commands, self.card_w = t, sessions, commands, width
        self.title, self.title_hint = title, title_hint
        h = self.PAD + self.HEAD_H + len(sessions) * self.ROW_H + 9
        h += sum(9 if c is None else SIZE['menu-item'] for c in commands) + self.PAD + space(3)
        self.setFixedSize(width + 2 * SHADOW, h + 2 * SHADOW)

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = QRectF(SHADOW, SHADOW - 4, self.card_w, self.height() - 2 * SHADOW)
        paint_popover(p, t, card)

        x0, w = card.left() + self.PAD, card.width() - 2 * self.PAD
        y = card.top() + self.PAD
        head = QRectF(x0 + 8, y, w - 16, self.HEAD_H)
        p.setFont(font('overline'))
        p.setPen(t.q('text-tertiary'))
        p.drawText(head, Qt.AlignmentFlag.AlignVCenter, self.title)
        p.setFont(font('small'))
        p.drawText(head, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, self.title_hint)
        y += self.HEAD_H
        tile = SIZE['control']
        for i, s in enumerate(self.sessions):
            current = i == 0
            r = QRectF(x0, y, w, self.ROW_H)
            if current:
                p.fillPath(_rounded(r, RADIUS['control']), t.q('bg-selected'))
            tile_rect = QRectF(r.left() + 8, r.top() + 12, tile, tile)
            p.fillPath(_rounded(tile_rect, RADIUS['control']), t.q('accent-subtle' if current else 'bg-subtle'))
            icons.paint(p, 'fit', t.q('accent' if current else 'text-secondary'), r.left() + 14, r.top() + 18, 16)
            p.setFont(font('body-strong'))
            p.setPen(t.q('text-primary'))
            p.drawText(QRectF(r.left() + 46, r.top() + 8, w - 120, 18), Qt.AlignmentFlag.AlignVCenter, s['name'])
            p.setFont(font('small'))
            p.setPen(t.q('text-secondary'))
            p.drawText(QRectF(r.left() + 46, r.top() + 27, w - 60, 16), Qt.AlignmentFlag.AlignVCenter, s['detail'])
            # The state in words at the right of the name line, its glyph before it.
            state_rect = QRectF(r.left() + 46, r.top() + 8, w - 46 - 10, 18)
            p.setPen(t.q('text-tertiary' if s['state'] == 'stale' else 'text-secondary'))
            right = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
            p.drawText(state_rect, right, s['status'])
            cx = state_rect.right() - p.fontMetrics().horizontalAdvance(s['status']) - 10
            paint_status_glyph(p, t, s['state'], cx, state_rect.center().y(), s.get('progress', 0.0))
            if current:
                icons.paint(p, 'check', t.q('accent'), r.right() - 26, r.top() + 27, 14, 2)
            y += self.ROW_H
        y = _menu_separator(p, t, x0, y, w)
        for c in self.commands:
            if c is None:
                y = _menu_separator(p, t, x0, y, w)
                continue
            _menu_command(p, t, x0, y, w, c, icon_x=14, text_x=46, key_inset=10)
            y += SIZE['menu-item']
        p.end()


# ── Form controls ──────────────────────────────────────────────────────────────────


class Field(QWidget):
    """A control-height entry on the field grid: ``bg-surface`` (``bg-window`` in dark) in a
    ``border-strong`` outline.

    ``number`` shows *text* right-aligned in tabular figures, with an optional quiet
    *prefix* (σ, from, to) at the left and *suffix* unit at the right; ``choice`` shows
    *text* with a trailing chevron (a unit menu, a model menu). *width* 0 lets it fill
    its column. *focused* draws the accent outline and the focus halo.
    """

    def __init__(
        self,
        t: Theme,
        text: str,
        width: int = 0,
        kind: str = 'number',
        prefix: str = '',
        suffix: str = '',
        focused: bool = False,
    ):
        super().__init__()
        self.t, self.text, self.kind, self.prefix, self.suffix, self.focused = t, text, kind, prefix, suffix, focused
        self.setFixedHeight(SIZE['control'])
        if width:
            self.setFixedWidth(width)
        else:
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.setMinimumWidth(48)

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = _rounded(r, RADIUS['control'])
        p.fillPath(path, t.q('bg-window' if t.dark else 'bg-surface'))
        p.setPen(QPen(t.q('accent') if self.focused else t.q('border-strong', 0.9), 1))
        p.drawPath(path)
        if self.focused:
            p.setPen(QPen(t.q('accent', 0.25), 3))
            p.drawPath(_rounded(r.adjusted(-2, -2, 2, 2), RADIUS['surface']))
        middle = Qt.AlignmentFlag.AlignVCenter
        if self.kind == 'choice':
            p.setFont(font('body'))
            p.setPen(t.q('text-primary'))
            p.drawText(r.adjusted(space(3), 0, -24, 0), middle, self.text)
            icons.paint(p, 'chevron-down', t.q('text-tertiary'), r.right() - 20, 8, 12, 2)
            p.end()
            return
        right = space(3)
        if self.prefix:
            p.setFont(font('body'))
            p.setPen(t.q('text-tertiary'))
            p.drawText(r.adjusted(space(3), 0, 0, 0), middle, self.prefix)
        if self.suffix:
            p.setFont(font('small'))
            p.setPen(t.q('text-tertiary'))
            p.drawText(r.adjusted(0, 0, -right, 0), middle | Qt.AlignmentFlag.AlignRight, self.suffix)
            right += QFontMetrics(p.font()).horizontalAdvance(self.suffix) + space(2)
        p.setFont(font('number'))
        p.setPen(t.q('text-primary'))
        p.drawText(r.adjusted(0, 0, -right, 0), middle | Qt.AlignmentFlag.AlignRight, self.text)
        p.end()


class Dropdown(QWidget):
    """A popup button: ``bg-surface`` (``bg-raised`` in dark) in a 1-px outline, trailing chevron.

    *text* is rich text, so a source name keeps its subscript. *disabled* greys it;
    *chevron* False and *align_right* show a value that is read rather than chosen.
    """

    def __init__(
        self,
        t: Theme,
        text: str,
        width: int,
        disabled: bool = False,
        chevron: bool = True,
        align_right: bool = False,
    ):
        super().__init__()
        self.t, self.text, self.disabled, self.chevron, self.align_right = t, text, disabled, chevron, align_right
        self.setFixedSize(width, SIZE['control'])

    def paintEvent(self, _):
        t = self.t
        h = SIZE['control']
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = _rounded(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), RADIUS['control'])
        p.fillPath(path, t.q('bg-subtle' if self.disabled else ('bg-raised' if t.dark else 'bg-surface')))
        p.setPen(QPen(t.q('border' if self.disabled else 'border-strong'), 1))
        p.drawPath(path)
        inset = 10
        right = h if self.chevron else inset
        tone = t.q('text-tertiary' if self.disabled else 'text-primary')
        paint_rich(p, QRectF(inset, 0, self.width() - inset - right, h), self.text, 'number', tone, self.align_right)
        if self.chevron:
            icons.paint(p, 'chevron-down', t.q('text-tertiary'), self.width() - 22, (h - 12) / 2, 12, 2)
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
        if width:
            self.setFixedWidth(width)

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
            off = i in self.disabled
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
                p.setPen(t.q('text-tertiary', 0.6))
            elif sel:
                p.setPen(t.q('text-primary'))
            else:
                p.setPen(t.q('text-tertiary' if t.dark else 'text-secondary'))
            p.drawText(seg, Qt.AlignmentFlag.AlignCenter, opt)
        p.end()


class Checkbox(QWidget):
    """A 15-px box with its label: accent fill and a check when *checked*."""

    def __init__(self, t: Theme, text: str, checked: bool = False):
        super().__init__()
        self.t, self.text, self.checked = t, text, checked
        self.setFixedSize(QFontMetrics(font('body')).horizontalAdvance(text) + 24, SIZE['control'])

    def paintEvent(self, _):
        t = self.t
        h = SIZE['control']
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = _rounded(QRectF(0.5, 6.5, 15, 15), 4)
        if self.checked:
            p.fillPath(path, t.q('accent'))
            icons.paint(p, 'check', t.q('on-accent'), 2, 8, 12, 2.6)
        else:
            p.fillPath(path, t.q('bg-raised' if t.dark else 'bg-surface'))
            p.setPen(QPen(t.q('border-strong'), 1))
            p.drawPath(path)
        p.setFont(font('body'))
        p.setPen(t.q('text-primary'))
        p.drawText(QRectF(24, 0, self.width() - 24, h), Qt.AlignmentFlag.AlignVCenter, self.text)
        p.end()


class Toggle(QWidget):
    """An on/off switch, 36 × 20: an accent track with the knob at the right when *on*."""

    def __init__(self, t: Theme, on: bool = True):
        super().__init__()
        self.t, self.on = t, on
        self.setFixedSize(36, 20)

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        p.fillPath(_rounded(r, r.height() / 2), t.q('accent' if self.on else 'border-strong'))
        knob = QRectF(r.right() - 18 if self.on else 2, 2, 16, 16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 46))
        p.drawEllipse(knob.translated(0, 0.75))
        p.setBrush(t.q('text-primary' if t.dark else 'bg-surface'))
        p.drawEllipse(knob)
        p.end()


class Slider(QWidget):
    """A 16-px slider: track, accent fill up to the handle at *pos* (0–1), and the handle.

    *decades* > 0 marks each decade under the track, so a log scale reads as one.
    """

    def __init__(self, t: Theme, pos: float, decades: int = 0):
        super().__init__()
        self.t, self.pos, self.decades = t, pos, decades
        self.setFixedHeight(16)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = 7.0
        x0, x1, cy = r, self.width() - r, 7.0
        p.fillPath(_rounded(QRectF(x0, cy - 2, x1 - x0, 4), 2), t.q('border-strong' if t.dark else 'bg-hover'))
        hx = x0 + self.pos * (x1 - x0)
        p.fillPath(_rounded(QRectF(x0, cy - 2, hx - x0, 4), 2), t.q('accent'))
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
        p.end()


class SliderEnd(QWidget):
    """One end of a :class:`Slider`, edited where it stands: quiet text, flush left (low
    end) or right (*right*, high end) in a column *width* px wide. Under the pointer it
    gains the outline of :class:`SliderEndOutline`; *hover* names it ``HoverEnd`` so a
    render can find it."""

    HEIGHT = 20

    def __init__(self, t: Theme, text: str, width: int, right: bool = False, hover: bool = False):
        super().__init__()
        self.t, self.text, self.right = t, text, right
        self.setFixedSize(width, self.HEIGHT)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.setToolTip('Click to change this end of the slider')
        if hover:
            self.setObjectName('HoverEnd')

    def text_rect(self) -> QRectF:
        """Where the end's text is drawn, in the widget's own coordinates."""
        tw = QFontMetrics(font('small-number')).horizontalAdvance(self.text)
        return QRectF(self.width() - tw if self.right else 0, 0, tw, self.HEIGHT)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setFont(font('small-number'))
        p.setPen(self.t.q('text-tertiary'))
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

    def __init__(self, t: Theme, letter: str, on: bool, by_filter: bool = False):
        super().__init__()
        self.t, self.letter, self.on, self.by_filter = t, letter, on, by_filter
        self.setFixedSize(60 if by_filter else 52, SIZE['control'])

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
        p.end()


class ConcentrationGrid(QWidget):
    """A concentration list in two side-by-side runs of rows: the point number and the
    value as entered (*values*, already formatted), under one *header*. Drawn like a
    parameters table: a header hairline, no box, a hairline between the two runs."""

    HEAD, ROW = 26, 20

    def __init__(self, t: Theme, values: list[str], header: str):
        super().__init__()
        self.t, self.values, self.header = t, values, header
        self.rows = math.ceil(len(values) / 2)
        self.setFixedHeight(self.HEAD + self.rows * self.ROW + 4)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        half = w / 2
        p.fillRect(QRectF(0, self.HEAD - 1, w, 1), t.q('border'))
        p.fillRect(QRectF(half, 0, 1, h), t.q('border'))
        gap, idx_w = space(4), 24
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


# ── Results ────────────────────────────────────────────────────────────────────────


class Callout(QFrame):
    """One message across the canvas: tinted fill and border of *tone* (``warning``,
    ``danger``), its icon, the title, the body and an optional trailing *action* link."""

    def __init__(self, theme: Theme, tone: str, title: str, body: str, action: str | None = None):
        super().__init__()
        self.t, self.tone = theme, tone
        ic = QLabel()
        ic.setPixmap(icons.pixmap('alert', theme[tone], 16))
        ic.setFixedSize(16, 16)
        row = hbox(ic, label(title, 'body-strong'), label(body, 'body', 'secondary'), None, margins=(4, 0, 4, 0))
        if action:
            row.addWidget(link_button(action))
        self.setLayout(row)
        self.setFixedHeight(40)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = _rounded(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), RADIUS['surface'])
        p.fillPath(path, self.t.q(f'{self.tone}-bg'))
        p.setPen(QPen(self.t.q(f'{self.tone}-border'), 1))
        p.drawPath(path)
        p.end()


class IntervalChart(QWidget):
    """A small forest plot on a log axis: one row per interval, each with its estimate.

    Each of *rows* is a dict with ``label``, ``color`` (a token), ``segments`` (the
    accepted stretches, ``(low, high)`` pairs), ``est``, ``text`` (the numbers, drawn on
    the right in tabular figures) and an optional ``badge``. The axis spans *lo* to *hi*;
    *ticks* are labelled divided by *tick_scale*, with *unit* after them.
    """

    ROW_H = 26

    def __init__(
        self,
        theme: Theme,
        rows: list[dict],
        lo: float,
        hi: float,
        ticks: list[float],
        unit: str,
        tick_scale: float = 1.0,
    ):
        super().__init__()
        self.t, self.rows, self.lo, self.hi, self.ticks, self.unit = theme, rows, lo, hi, ticks, unit
        self.tick_scale = tick_scale
        self.setFixedHeight(len(rows) * self.ROW_H + 26)
        self.setMinimumWidth(420)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def _x(self, v: float, x0: float, w: float) -> float:
        return x0 + (math.log10(v) - math.log10(self.lo)) / (math.log10(self.hi) - math.log10(self.lo)) * w

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        lab_w, num_w = 116, 176
        x0, w = lab_w, self.width() - lab_w - num_w - space(5)
        top = 2
        bottom = top + len(self.rows) * self.ROW_H
        p.setFont(font('small-number'))
        for tk in self.ticks:
            x = self._x(tk, x0, w)
            p.setPen(QPen(t.q('grid'), 1))
            p.drawLine(QPointF(x, top), QPointF(x, bottom))
            p.setPen(t.q('text-tertiary'))
            p.drawText(QRectF(x - 30, bottom + 4, 60, 16), Qt.AlignmentFlag.AlignHCenter, f'{tk / self.tick_scale:g}')
        p.drawText(QRectF(x0 + w + space(5), bottom + 4, num_w, 16), Qt.AlignmentFlag.AlignLeft, self.unit)
        for i, row in enumerate(self.rows):
            cy = top + i * self.ROW_H + self.ROW_H / 2
            p.setFont(font('small'))
            p.setPen(t.q('text-secondary'))
            p.drawText(QRectF(0, cy - 9, lab_w - 12, 18), Qt.AlignmentFlag.AlignVCenter, row['label'])
            col = t.q(row['color'])
            p.setPen(QPen(t.q('border'), 1))
            p.drawLine(QPointF(x0, cy), QPointF(x0 + w, cy))
            for a, b in row['segments']:
                pen = QPen(col, 4)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawLine(QPointF(self._x(a, x0, w), cy), QPointF(self._x(b, x0, w), cy))
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

    *items* are ``(kind, text)``: ``dots`` (replicates, at *dot_alpha*), ``cross`` (a
    replicate switched off), ``rings`` (an overlaid file, with an × that removes it),
    ``mean`` (mean ± SD) and ``line`` (the fitted or model curve).
    """

    def __init__(self, theme: Theme, items: list[tuple[str, str]], dot_alpha: float = 0.6):
        super().__init__()
        self.t, self.items, self.dot_alpha = theme, items, dot_alpha
        self.setFixedHeight(20)
        fm = QFontMetrics(font('small'))
        self.setFixedWidth(sum(self._width(kind, txt, fm) for kind, txt in items) - space(5))
        if any(kind == 'rings' for kind, _ in items):
            self.setToolTip('The × removes the overlay')

    @staticmethod
    def _width(kind: str, txt: str, fm: QFontMetrics) -> int:
        return 20 + fm.horizontalAdvance(txt) + (space(2) + 12 if kind == 'rings' else 0) + space(5)

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(font('small'))
        fm = p.fontMetrics()
        x, cy = 0.0, self.height() / 2
        for kind, txt in self.items:
            if kind == 'dots':
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(t.q('replicate', self.dot_alpha))
                for dx, dy in ((3, 2), (8, -2.5), (12, 1.5)):
                    p.drawEllipse(QPointF(x + dx, cy + dy), 2.5, 2.5)
            elif kind == 'rings':
                p.setPen(QPen(t.q('text-secondary'), 1.3))
                p.setBrush(Qt.BrushStyle.NoBrush)
                for dx, dy in ((3.5, 2), (8.5, -2.5), (13, 1.5)):
                    p.drawEllipse(QPointF(x + dx, cy + dy), 2.4, 2.4)
            elif kind == 'cross':
                p.setPen(QPen(t.q('replicate-off'), 1.4))
                for s in (-1, 1):
                    p.drawLine(QPointF(x + 4, cy - 3.5 * s), QPointF(x + 11, cy + 3.5 * s))
            elif kind == 'mean':
                p.setPen(QPen(t.q('text-primary'), 1))
                p.drawLine(QPointF(x + 7.5, cy - 6), QPointF(x + 7.5, cy + 6))
                p.drawLine(QPointF(x + 5, cy - 6), QPointF(x + 10, cy - 6))
                p.drawLine(QPointF(x + 5, cy + 6), QPointF(x + 10, cy + 6))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(t.q('text-primary'))
                p.drawEllipse(QPointF(x + 7.5, cy), 3, 3)
            elif kind == 'line':
                pen = QPen(t.q('accent'), 2)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawLine(QPointF(x + 1, cy), QPointF(x + 15, cy))
            p.setPen(t.q('text-secondary'))
            p.drawText(QRectF(x + 20, 0, 400, self.height()), Qt.AlignmentFlag.AlignVCenter, txt)
            if kind == 'rings':
                close_x = x + 20 + fm.horizontalAdvance(txt) + space(2)
                icons.paint(p, 'x', t.q('text-tertiary'), close_x, cy - 6, 12, 2)
            x += self._width(kind, txt, fm)
        p.end()


class ShiftBar(QWidget):
    """A diverging bar of a fitted input shift *z* in σ: the ±1 σ band shaded, axis ±4 σ."""

    def __init__(self, theme: Theme, z: float):
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
        z = max(-4, min(4, self.z))
        x1, x2 = sorted((cx, cx + z * s))
        p.fillPath(_rounded(QRectF(x1, 5, max(x2 - x1, 1.5), h - 10), 1.5), t.q('text-secondary'))
        p.end()


# ── Inspector ──────────────────────────────────────────────────────────────────────


class SectionHeader(QAbstractButton):
    """A collapsible inspector section's header: chevron, title and a quiet *trailing* summary."""

    toggled_open = pyqtSignal(bool)
    HEIGHT = 32

    def __init__(self, theme: Theme, title: str, open_: bool = True, trailing: str = ''):
        super().__init__()
        self.t, self._title, self._open, self._trailing = theme, title, open_, trailing
        self.setFixedHeight(self.HEIGHT)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)

    def paintEvent(self, _):
        t = self.t
        h = self.HEIGHT
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        chevron = 'chevron-down' if self._open else 'chevron-right'
        icons.paint(p, chevron, t.q('text-tertiary'), -2, (h - 16) / 2, 16, 2)
        p.setFont(font('body-strong'))
        p.setPen(t.q('text-primary'))
        p.drawText(QRectF(18, 0, self.width(), h), Qt.AlignmentFlag.AlignVCenter, self._title)
        if self._trailing:
            p.setFont(font('small'))
            p.setPen(t.q('text-tertiary'))
            right = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
            p.drawText(QRectF(0, 0, self.width(), h), right, self._trailing)
        p.end()


def section(
    theme: Theme, title: str, content: QWidget | None, open_: bool = True, first: bool = False, trailing: str = ''
) -> QWidget:
    """An inspector section: a hairline above (unless *first*), the header, and *content* while open."""
    w = QWidget()
    lay = vbox(spacing=0)
    if not first:
        lay.addWidget(hairline())
        lay.addSpacing(space(3))
    lay.addWidget(SectionHeader(theme, title, open_, trailing))
    if content is not None and open_:
        lay.addSpacing(space(2))
        lay.addWidget(content)
        lay.addSpacing(space(5))
    else:
        lay.addSpacing(space(3))
    w.setLayout(lay)
    return w
