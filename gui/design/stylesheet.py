"""The application stylesheet, written once as a template over the tokens.

QSS styles what Qt's widgets can express, keyed by object name (``Sidebar``,
``StatusBar``, ``Toolbar``, ``Canvas``, ``Inspector``, ``InspectorBody``) and by the
dynamic properties ``role`` (``hairline``, ``badge``, ``link``) and ``tone``
(``secondary``, ``tertiary``, ``accent``, ``neutral``). The controls QSS cannot express
are painted in :mod:`gui.design.components` from the same tokens.
"""

from __future__ import annotations

from gui.design.tokens import Theme

TEMPLATE = """
QWidget { color: {{text-primary}}; }
QWidget#Sidebar { background: {{bg-sidebar}}; }
QWidget#StatusBar { background: {{bg-sidebar}}; }
QWidget#Toolbar, QWidget#Canvas, QWidget#Inspector, QWidget#InspectorBody { background: {{bg-surface}}; }
QFrame[role="hairline"] { background: {{border}}; border: none; }
QSplitter::handle { background: {{border}}; }
QLabel { background: transparent; }
QLabel[tone="secondary"] { color: {{text-secondary}}; }
QLabel[tone="tertiary"] { color: {{text-tertiary}}; }
QLabel[role="badge"] { border-radius: 9px; padding: 0px {{space(3)}}; min-height: 18px; max-height: 18px; }
QLabel[role="badge"][tone="accent"] { background: {{accent-subtle}}; color: {{accent}}; }
QLabel[role="badge"][tone="neutral"] { background: {{bg-subtle}}; color: {{text-secondary}}; }
QPushButton[role="link"] {
    border: none; background: transparent; color: {{accent}}; padding: 0px; min-height: 20px;
}
QPushButton[role="link"]:hover { color: {{accent-hover}}; }
QPushButton[role="link"]:disabled { color: {{text-tertiary}}; }
QScrollArea { border: none; background: transparent; }
QLineEdit[role="field"] { background: transparent; border: none; padding: 0px; color: {{text-primary}}; }
QScrollBar:vertical { width: 8px; background: transparent; margin: 0px; }
QScrollBar::handle:vertical { background: {{opacity(text-tertiary, 0.35)}}; border-radius: 4px; min-height: 32px; }
QScrollBar::handle:vertical:hover { background: {{opacity(text-tertiary, 0.6)}}; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0px; width: 0px; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QToolTip {
    background: {{bg-raised}}; color: {{text-primary}}; border: 1px solid {{border}};
    border-radius: {{radius(control)}}; padding: {{space(2)}} {{space(3)}};
}
"""


def stylesheet(theme: Theme) -> str:
    """The stylesheet for *theme*, every token filled in."""
    return theme.render(TEMPLATE)
