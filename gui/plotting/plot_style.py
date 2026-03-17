"""Style configuration widget using PyQtGraph ParameterTree."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QWidget
import pyqtgraph as pg
from pyqtgraph.parametertree import Parameter, ParameterTree

DEFAULT_STYLE: dict = {
    "axes": {
        "label_font_size": 18,
        "tick_font_size": 16,
        "x_unit": "µM",
    },
    "data_points": {
        "symbol": "o",
        "size": 10,
        "alpha": 200,
    },
    "dropped_replicas": {
        "symbol": "x",
        "size": 8,
        "alpha": 120,
    },
    "average_line": {
        "width": 1,
        "style": "dash",
    },
    "fit_curves": {
        "width": 2,
        "style": "dash",
    },
    "error_bars": {
        "visible": True,
        "width": 2,
        "color": (80, 80, 80),
        "cap_size": 2,
    },
    "visibility": {
        "show_data_points": True,
        "show_dropped": True,
        "show_average": False,
        "show_fit": True,
        "show_error_bars": True,
    },
    "legend": {
        "font_size": 14,
        "show_replicas": True,
        "show_average": True,
        "show_fit": True,
    },
    "annotations": {
        "show_fit_results": False,
        "font_size": 14,
    },
}

_MARKER_LIMITS = {
    "Circle":   "o",
    "Square":   "s",
    "Triangle": "t",
    "Diamond":  "d",
    "Plus":     "+",
    "Cross":    "x",
}

_LINE_STYLE_LIMITS = ["Solid", "Dashed", "Dotted"]

_PARAMS_SPEC = [
    # Visibility is first — the most common thing to toggle
    {
        "name": "Visibility",
        "type": "group",
        "children": [
            {"name": "Show data points", "type": "bool", "value": True},
            {"name": "Show dropped replicas", "type": "bool", "value": True},
            {"name": "Show average", "type": "bool", "value": False},
            {"name": "Show error bars", "type": "bool", "value": True},
            {"name": "Show fit", "type": "bool", "value": True},
        ],
    },
    {
        "name": "Axes",
        "type": "group",
        "children": [
            {"name": "Label font size", "type": "int", "value": 14, "limits": (6, 24)},
            {"name": "Tick font size",  "type": "int", "value": 14, "limits": (6, 24)},
            {"name": "X-axis unit", "type": "list", "value": "µM",
             "limits": ["nM", "µM", "mM", "M"]},
        ],
    },
    {
        "name": "Data points",
        "type": "group",
        "children": [
            {"name": "Marker", "type": "list", "value": "o", "limits": _MARKER_LIMITS},
            {"name": "Size", "type": "int", "value": 10, "limits": (2, 20)},
            {"name": "Opacity", "type": "int", "value": 200, "limits": (0, 255)},
        ],
    },
    {
        "name": "Dropped replicas",
        "type": "group",
        "children": [
            {"name": "Marker", "type": "list", "value": "x", "limits": _MARKER_LIMITS},
            {"name": "Size", "type": "int", "value": 8, "limits": (2, 20)},
            {"name": "Opacity", "type": "int", "value": 120, "limits": (0, 255)},
        ],
    },
    {
        "name": "Average line",
        "type": "group",
        "children": [
            {"name": "Width", "type": "int", "value": 1, "limits": (1, 8)},
            {"name": "Style", "type": "list", "value": "Dashed",
             "limits": _LINE_STYLE_LIMITS},
        ],
    },
    {
        "name": "Fit curves",
        "type": "group",
        "children": [
            {"name": "Width", "type": "int", "value": 2, "limits": (1, 8)},
            {"name": "Style", "type": "list", "value": "Dashed",
             "limits": _LINE_STYLE_LIMITS},
        ],
    },
    {
        "name": "Error bars",
        "type": "group",
        "children": [
            {"name": "Width", "type": "int", "value": 2, "limits": (1, 5)},
            {"name": "Color", "type": "color", "value": (80, 80, 80, 255)},
            {"name": "Cap size", "type": "int", "value": 2, "limits": (0, 30)},
        ],
    },
    {
        "name": "Legend",
        "type": "group",
        "children": [
            {"name": "Font size", "type": "int", "value": 14, "limits": (6, 24)},
            {"name": "Show replicas", "type": "bool", "value": True},
            {"name": "Show average", "type": "bool", "value": True},
            {"name": "Show fit", "type": "bool", "value": True},
        ],
    },
    {
        "name": "Annotations",
        "type": "group",
        "children": [
            {"name": "Show fit results", "type": "bool", "value": False},
            {"name": "Font size", "type": "int", "value": 14, "limits": (7, 24)},
        ],
    },
]

_LINE_STYLE_MAP = {
    "Solid":  "solid",
    "Dashed": "dash",
    "Dotted": "dot",
}


_PEN_STYLE_MAP: dict[str, Qt.PenStyle] = {
    "solid": Qt.PenStyle.SolidLine,
    "dash":  Qt.PenStyle.DashLine,
    "dot":   Qt.PenStyle.DotLine,
}


def _qcolor_to_tuple(color) -> tuple:
    """Convert a QColor (or tuple) from ParameterTree to an (R, G, B, A) tuple."""
    from PyQt6.QtGui import QColor
    if isinstance(color, QColor):
        return (color.red(), color.green(), color.blue(), color.alpha())
    if hasattr(color, '__iter__'):
        return tuple(color)
    return (80, 80, 80, 255)


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


class PlotStyleWidget(QWidget):
    """Style configuration panel backed by a PyQtGraph ParameterTree.

    Emits ``style_changed`` with the full style dict whenever any parameter
    is modified.
    """

    style_changed = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._params = Parameter.create(
            name="Style", type="group", children=_PARAMS_SPEC
        )
        self._tree = ParameterTree(showHeader=False)
        self._tree.setParameters(self._params, showTop=False)
        self._params.sigTreeStateChanged.connect(self._on_change)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._tree)

    def _on_change(self, *_):
        self.style_changed.emit(self.current_style())

    def current_style(self) -> dict:
        """Return a copy of the current style as a plain dict."""
        p = self._params
        return {
            "axes": {
                "label_font_size": p["Axes", "Label font size"],
                "tick_font_size":  p["Axes", "Tick font size"],
                "x_unit":          p["Axes", "X-axis unit"],
            },
            "data_points": {
                "symbol": p["Data points", "Marker"],
                "size": p["Data points", "Size"],
                "alpha": p["Data points", "Opacity"],
            },
            "dropped_replicas": {
                "symbol": p["Dropped replicas", "Marker"],
                "size": p["Dropped replicas", "Size"],
                "alpha": p["Dropped replicas", "Opacity"],
            },
            "average_line": {
                "width": p["Average line", "Width"],
                "style": p["Average line", "Style"],
            },
            "fit_curves": {
                "width": p["Fit curves", "Width"],
                "style": p["Fit curves", "Style"],
            },
            "error_bars": {
                "visible": p["Visibility", "Show error bars"],
                "width": p["Error bars", "Width"],
                "color": _qcolor_to_tuple(p["Error bars", "Color"]),
                "cap_size": p["Error bars", "Cap size"],
            },
            "visibility": {
                "show_data_points": p["Visibility", "Show data points"],
                "show_dropped": p["Visibility", "Show dropped replicas"],
                "show_average": p["Visibility", "Show average"],
                "show_fit": p["Visibility", "Show fit"],
                "show_error_bars": p["Visibility", "Show error bars"],
            },
            "legend": {
                "font_size": p["Legend", "Font size"],
                "show_replicas": p["Legend", "Show replicas"],
                "show_average": p["Legend", "Show average"],
                "show_fit": p["Legend", "Show fit"],
            },
            "annotations": {
                "show_fit_results": p["Annotations", "Show fit results"],
                "font_size": p["Annotations", "Font size"],
            },
        }
