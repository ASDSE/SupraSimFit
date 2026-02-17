"""Style configuration widget using PyQtGraph ParameterTree."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QWidget
import pyqtgraph as pg
from pyqtgraph.parametertree import Parameter, ParameterTree

DEFAULT_STYLE: dict = {
    "data_points": {
        "symbol": "o",
        "size": 8,
        "alpha": 200,
    },
    "dropped_replicas": {
        "symbol": "x",
        "size": 8,
        "alpha": 120,
    },
    "average_line": {
        "width": 2,
        "style": "solid",
        "visible": True,
    },
    "fit_curves": {
        "width": 2,
        "style": "solid",
    },
    "error_bars": {
        "visible": True,
        "width": 1,
    },
    "visibility": {
        "show_data_points": True,
        "show_dropped": True,
        "show_average": True,
        "show_fit": True,
        "show_error_bars": True,
    },
    "legend": {
        "font_size": 10,
        "show_replicas": True,
        "show_average": True,
        "show_fit": True,
    },
    "annotations": {
        "show_fit_results": False,
        "font_size": 9,
    },
    "grid": {
        "show_major": True,
        "major_opacity": 120,
        "show_minor": True,
        "minor_opacity": 50,
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
    {
        "name": "Data points",
        "type": "group",
        "children": [
            {"name": "Marker", "type": "list", "value": "o", "limits": _MARKER_LIMITS},
            {"name": "Size", "type": "int", "value": 8, "limits": (2, 20)},
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
            {"name": "Width", "type": "int", "value": 2, "limits": (1, 8)},
            {"name": "Style", "type": "list", "value": "Solid",
             "limits": _LINE_STYLE_LIMITS},
            {"name": "Visible", "type": "bool", "value": True},
        ],
    },
    {
        "name": "Fit curves",
        "type": "group",
        "children": [
            {"name": "Width", "type": "int", "value": 2, "limits": (1, 8)},
            {"name": "Style", "type": "list", "value": "Solid",
             "limits": _LINE_STYLE_LIMITS},
        ],
    },
    {
        "name": "Visibility",
        "type": "group",
        "children": [
            {"name": "Show data points", "type": "bool", "value": True},
            {"name": "Show dropped replicas", "type": "bool", "value": True},
            {"name": "Show average", "type": "bool", "value": True},
            {"name": "Show fit", "type": "bool", "value": True},
            {"name": "Show error bars", "type": "bool", "value": True},
        ],
    },
    {
        "name": "Legend",
        "type": "group",
        "children": [
            {"name": "Font size", "type": "int", "value": 10, "limits": (6, 18)},
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
            {"name": "Font size", "type": "int", "value": 9, "limits": (7, 14)},
        ],
    },
    {
        "name": "Grid",
        "type": "group",
        "children": [
            {"name": "Show major grid", "type": "bool", "value": True},
            {"name": "Major opacity", "type": "int", "value": 120, "limits": (0, 255)},
            {"name": "Show minor grid", "type": "bool", "value": True},
            {"name": "Minor opacity", "type": "int", "value": 50, "limits": (0, 255)},
        ],
    },
]

_LINE_STYLE_MAP = {
    "Solid":  "solid",
    "Dashed": "dash",
    "Dotted": "dot",
}


def line_style_to_qt(style_str: str):
    """Map style string to Qt.PenStyle.

    Accepts both internal strings (``"solid"``, ``"dash"``, ``"dot"``)
    and display strings (``"Solid"``, ``"Dashed"``, ``"Dotted"``).

    Returns
    -------
    Qt.PenStyle
    """
    from PyQt6.QtCore import Qt
    # Normalise display → internal
    normalised = _LINE_STYLE_MAP.get(style_str, style_str)
    mapping = {
        "solid": Qt.PenStyle.SolidLine,
        "dash":  Qt.PenStyle.DashLine,
        "dot":   Qt.PenStyle.DotLine,
    }
    return mapping.get(normalised, Qt.PenStyle.SolidLine)


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
                "visible": p["Average line", "Visible"],
            },
            "fit_curves": {
                "width": p["Fit curves", "Width"],
                "style": p["Fit curves", "Style"],
            },
            "error_bars": {
                "visible": p["Visibility", "Show error bars"],
                "width": 1,
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
            "grid": {
                "show_major": p["Grid", "Show major grid"],
                "major_opacity": p["Grid", "Major opacity"],
                "show_minor": p["Grid", "Show minor grid"],
                "minor_opacity": p["Grid", "Minor opacity"],
            },
        }
