"""The style the Simulation window's plot is drawn with, and the line styles it names."""

from __future__ import annotations

from PyQt6.QtCore import Qt

DEFAULT_STYLE: dict = {
    'axes': {
        'label_font_size': 18,
        'tick_font_size': 16,
        'x_unit': 'µM',
    },
    'data_points': {
        'symbol': 'o',
        'size': 10,
        'alpha': 200,
        'palette': 'Default (Tab10)',
    },
    'dropped_replicas': {
        'symbol': 'x',
        'size': 11,
        'alpha': 255,
    },
    'average_line': {
        'width': 3,
        'style': 'dash',
        'color': (0, 0, 0, 255),
    },
    'fit_curves': {
        'width': 3,
        'style': 'dash',
        'color': (23, 190, 207, 255),
    },
    'error_bars': {
        'visible': True,
        'width': 2,
        'color': (80, 80, 80),
        'cap_size': 2,
    },
    'visibility': {
        'show_data_points': True,
        'show_dropped': True,
        'show_average': False,
        'show_fit': True,
        'show_error_bars': True,
        'show_fit_results': True,
    },
    'legend': {
        'font_size': 14,
        'show_replicas': True,
        'show_dropped': True,
        'show_average': True,
        'show_error_bars': True,
        'show_fit': True,
        'background_color': (255, 255, 255, 200),
    },
    'annotations': {
        'font_size': 14,
        'background_color': (255, 255, 255, 200),
    },
}

_LINE_STYLE_MAP = {
    'Solid': 'solid',
    'Dashed': 'dash',
    'Dotted': 'dot',
}


_PEN_STYLE_MAP: dict[str, Qt.PenStyle] = {
    'solid': Qt.PenStyle.SolidLine,
    'dash': Qt.PenStyle.DashLine,
    'dot': Qt.PenStyle.DotLine,
}


def line_style_to_qt(style_str: str) -> Qt.PenStyle:
    """Map style string to Qt.PenStyle.

    Accepts both internal strings (``"solid"``, ``"dash"``, ``"dot"``)
    and display strings (``"Solid"``, ``"Dashed"``, ``"Dotted"``).

    Parameters
    ----------
    style_str : str
        Style name in either display or internal form.

    Returns
    -------
    Qt.PenStyle
    """
    normalised = _LINE_STYLE_MAP.get(style_str, style_str)
    return _PEN_STYLE_MAP.get(normalised, Qt.PenStyle.SolidLine)
