"""The icon set: 24-unit line icons in the Lucide style (ISC licence), tinted from a token.

Every icon is one SVG body drawn on a 24 × 24 grid with round caps and joins. ``fill="C"``
inside a body marks a filled part, which takes the same colour as the stroke. Icons are
drawn at 16 px in controls and navigation and at 14 px inside dense rows.
"""

from __future__ import annotations

from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

#: Stroke width of every icon, in units of its 24-unit grid.
STROKE = 1.75

PATHS: dict[str, str] = {
    'alert': (
        '<path d="m21.7 18-8-14a2 2 0 0 0-3.5 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3"/><path d="M12 9v'
        '4"/><path d="M12 17h.01"/>'
    ),
    'alert-circle': '<circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
    'arrow-up-right': '<path d="M7 7h10v10"/><path d="M7 17 17 7"/>',
    'bars': '<path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="M18 17V9M13 17V5M8 17v-3"/>',
    'check': '<path d="M20 6 9 17l-5-5"/>',
    'check-circle': '<circle cx="12" cy="12" r="10"/><path d="m8.5 12 2.5 2.5 4.5-5"/>',
    'chevron-down': '<path d="m6 9 6 6 6-6"/>',
    'chevron-right': '<path d="m9 18 6-6-6-6"/>',
    'copy': (
        '<rect width="14" height="14" x="8" y="8" rx="2"/><path d="M4 16a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h10'
        'a2 2 0 0 1 2 2"/>'
    ),
    'export': ('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>'),
    'file': (
        '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0'
        ' 2 2h4"/><path d="M16 13H8M16 17H8M10 9H8"/>'
    ),
    'file-plus': (
        '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0'
        ' 2 2h4"/><path d="M9 15h6M12 12v6"/>'
    ),
    'file-text': (
        '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0'
        ' 2 2h4"/><path d="M16 13H8M16 17H8M10 9H8"/>'
    ),
    'fit': '<path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="M7 7c1 5 3 9 6 9.5S18 16 20 16"/>',
    'flask': (
        '<path d="M10 2v7.5a2 2 0 0 1-.2.9L4.7 20.5a1 1 0 0 0 .9 1.5h12.8a1 1 0 0 0 .9-1.5l-5.1-10.1a2 2 '
        '0 0 1-.2-.9V2"/><path d="M8.5 2h7"/><path d="M7 16h10"/>'
    ),
    'help': ('<circle cx="12" cy="12" r="10"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>'),
    'image': (
        '<rect width="18" height="18" x="3" y="3" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.'
        '1-3.1a2 2 0 0 0-2.8 0L6 21"/>'
    ),
    'info': '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    'layers': '<path d="m12 2 10 5-10 5L2 7Z"/><path d="m2 12 10 5 10-5"/><path d="m2 17 10 5 10-5"/>',
    'maximize': (
        '<path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M3 16v3a2 2 0 0 0'
        ' 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/>'
    ),
    'more': (
        '<circle cx="12" cy="12" r="1" fill="C"/><circle cx="19" cy="12" r="1" fill="C"/><circle cx="5" c'
        'y="12" r="1" fill="C"/>'
    ),
    'open': (
        '<path d="m6 14 1.5-2.9A2 2 0 0 1 9.2 10H20a2 2 0 0 1 1.9 2.5l-1.5 6a2 2 0 0 1-2 1.5H4a2 2 0 0 1-'
        '2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.7.9l.8 1.2a2 2 0 0 0 1.7.9H18a2 2 0 0 1 2 2v2"/>'
    ),
    'palette': (
        '<path d="M12 22a10 10 0 1 1 10-10c0 2.5-2 3-3.5 3H16a2 2 0 0 0-1.5 3.3A2 2 0 0 1 12 22Z"/><circl'
        'e cx="13.5" cy="6.5" r=".6" fill="C"/><circle cx="17.5" cy="10.5" r=".6" fill="C"/><circle cx="8'
        '.5" cy="7.5" r=".6" fill="C"/><circle cx="6.5" cy="12.5" r=".6" fill="C"/>'
    ),
    'panel-left': '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/>',
    'panel-right': '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M15 3v18"/>',
    'play': ('<path d="M7 4.5v15a.8.8 0 0 0 1.2.7l12-7.5a.8.8 0 0 0 0-1.4l-12-7.5A.8.8 0 0 0 7 4.5Z" fill="C"/>'),
    'plus': '<path d="M5 12h14M12 5v14"/>',
    'profile': (
        '<path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="M7 5c1.5 8 3 10.5 5.5 10.5S16.5 13 18 5"/><path d="'
        'M6.5 11h14" stroke-dasharray="1.5 2.5"/>'
    ),
    'results': (
        '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0'
        ' 2 2h4"/><path d="M8 18v-3M12 18v-6M16 18v-4"/>'
    ),
    'rotate': '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
    'save': (
        '<path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2'
        ' 0 0 1 2-2z"/><path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"/><path d="M7 3v4a1 1 0 0 0 1 1'
        'h7"/>'
    ),
    'scatter': (
        '<circle cx="7.5" cy="7.5" r="1.6"/><circle cx="18.5" cy="5.5" r="1.6"/><circle cx="11.5" cy="11.'
        '5" r="1.6"/><circle cx="7.5" cy="16.5" r="1.6"/><circle cx="16.5" cy="14.5" r="1.6"/>'
    ),
    'sliders': '<path d="M21 4h-7M10 4H3M21 12h-9M8 12H3M21 20h-5M12 20H3M14 2v4M8 10v4M16 18v4"/>',
    'stop': '<rect width="12" height="12" x="6" y="6" rx="1.5" fill="C"/>',
    'table': '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18M3 15h18M12 3v18"/>',
    'updown': '<path d="m7 15 5 5 5-5"/><path d="m7 9 5-5 5 5"/>',
    'x': '<path d="M18 6 6 18M6 6l12 12"/>',
}


def svg(name: str, color: str, stroke: float = STROKE) -> bytes:
    """The SVG document of icon *name* in *color* (``#RRGGBB``)."""
    body = PATHS[name].replace('fill="C"', f'fill="{color}"')
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
        f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    ).encode()


def pixmap(name: str, color: QColor | str, size: int = 16, dpr: float = 2.0, stroke: float = STROKE) -> QPixmap:
    """Icon *name* rendered at *size* logical px for a screen of device-pixel ratio *dpr*."""
    hexc = color.name() if isinstance(color, QColor) else color
    renderer = QSvgRenderer(QByteArray(svg(name, hexc, stroke)))
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size * dpr, size * dpr))
    painter.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name: str, color: QColor | str, size: int = 16) -> QIcon:
    """Icon *name* as a QIcon for buttons and actions."""
    return QIcon(pixmap(name, color, size))


def paint(
    painter: QPainter, name: str, color: QColor | str, x: float, y: float, size: int = 16, stroke: float = STROKE
) -> None:
    """Draw icon *name* with its top-left corner at (*x*, *y*) inside a custom-painted widget."""
    hexc = color.name() if isinstance(color, QColor) else color
    QSvgRenderer(QByteArray(svg(name, hexc, stroke))).render(painter, QRectF(x, y, size, size))
