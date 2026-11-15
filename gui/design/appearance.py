"""The app's one theme source: the current :class:`Theme`, the System / Light / Dark mode and its signal.

Every window and painted component holds :attr:`Appearance.theme`, one object resolved in
place, so a change of theme needs no rebuilding: :meth:`Appearance.set_mode` resolves it,
re-applies the stylesheet and palette and repaints every widget, then emits
:attr:`Appearance.changed` for what draws outside ``paintEvent`` (pyqtgraph plots).
Under *System* the theme follows the operating system's colour scheme. The mode is also
the colour scheme Qt is asked for, so what Qt draws from the platform — native file
dialogs, window frames, the menu bar — is drawn in the app's choice, not the operating
system's. :class:`DesignStyle` is the style the app runs: Fusion, with the icons of a
message box drawn from the design's icon set in the theme on screen.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QProxyStyle, QStyle, QStyleFactory

from gui.design import icons
from gui.design.stylesheet import stylesheet
from gui.design.tokens import Theme

#: The colour scheme Qt is asked for in each mode; ``Unknown`` lets the platform's own apply.
SCHEMES = {'system': Qt.ColorScheme.Unknown, 'light': Qt.ColorScheme.Light, 'dark': Qt.ColorScheme.Dark}
MODES = tuple(SCHEMES)


class Appearance(QObject):
    """The theme of every window of the app; see the module docstring."""

    changed = pyqtSignal()

    def __init__(self, app: QApplication, mode: str = 'system') -> None:
        super().__init__(app)
        self._app = app
        self.mode = mode
        app.styleHints().setColorScheme(SCHEMES[mode])
        self.theme = Theme(self._dark())
        app.styleHints().colorSchemeChanged.connect(lambda _scheme: self._follow_system())
        self._apply()

    def set_mode(self, mode: str) -> None:
        """Show every window in *mode* (``'system'``, ``'light'`` or ``'dark'``) from now on."""
        if mode not in MODES:
            raise ValueError(f'unknown appearance mode {mode!r}')
        self.mode = mode
        self._app.styleHints().setColorScheme(SCHEMES[mode])
        self._resolve()

    def _follow_system(self) -> None:
        if self.mode == 'system':
            self._resolve()

    def _dark(self) -> bool:
        if self.mode == 'system':
            return self._app.styleHints().colorScheme() == Qt.ColorScheme.Dark
        return self.mode == 'dark'

    def _resolve(self) -> None:
        dark = self._dark()
        if dark == self.theme.dark:
            return
        self.theme.set_dark(dark)
        self._apply()
        for widget in self._app.allWidgets():
            widget.update()
        self.changed.emit()

    def _apply(self) -> None:
        self._app.setPalette(self.theme.palette())
        self._app.setStyleSheet(stylesheet(self.theme))


#: The icon of each kind of message box, and its colour: what a box asks or tells in ``accent``, a warning in
#: ``warning`` and an error in ``danger``.
MESSAGE_ICONS = {
    QStyle.StandardPixmap.SP_MessageBoxQuestion: ('help', 'accent'),
    QStyle.StandardPixmap.SP_MessageBoxInformation: ('info', 'accent'),
    QStyle.StandardPixmap.SP_MessageBoxWarning: ('alert', 'warning'),
    QStyle.StandardPixmap.SP_MessageBoxCritical: ('alert-circle', 'danger'),
}


class DesignStyle(QProxyStyle):
    """Fusion, with the icons of a message box drawn from :mod:`gui.design.icons` in the theme on screen.

    Fusion's own message-box icons are bitmaps drawn for a light window — its question mark
    a grey outline that vanishes on a dark one — so each is the design's line icon in a
    token of the theme the box opens in.
    """

    def __init__(self):
        super().__init__(QStyleFactory.create('Fusion'))

    def standardIcon(self, standard, option=None, widget=None) -> QIcon:  # noqa: N802 — Qt's name
        if standard in MESSAGE_ICONS:
            name, token = MESSAGE_ICONS[standard]
            size = self.pixelMetric(QStyle.PixelMetric.PM_MessageBoxIconSize, option, widget)
            return icons.icon(name, theme().q(token), size)
        return super().standardIcon(standard, option, widget)


_appearance: Appearance | None = None


def appearance() -> Appearance:
    """The app's theme source, made on first use for the running :class:`QApplication`."""
    global _appearance
    if _appearance is None:
        app = QApplication.instance()
        if not isinstance(app, QApplication):
            raise RuntimeError('the appearance needs a QApplication')
        _appearance = Appearance(app)
    return _appearance


def theme() -> Theme:
    """The theme every window is drawn in now."""
    return appearance().theme
