"""Style configuration widget using PyQtGraph ParameterTree."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QWidget
import pyqtgraph as pg
from pyqtgraph.parametertree import Parameter, ParameterTree

from gui.plotting.colors import (
    AVERAGE_LINE_COLOR,
    DROPPED_REPLICA_COLOR,
    ERROR_BAR_COLOR,
    FIT_PALETTE,
    REPLICA_PALETTE,
    rgba,
)

try:
    from PyQt6.QtCore import Qt
    _PenStyle = Qt.PenStyle
except ImportError:
    _PenStyle = None

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
        "visible": True,
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
        "show_replicas": True,
        "show_average": True,
        "show_fit": True,
        "show_error_bars": True,
    },
}

_PARAMS_SPEC = [
    {
        "name": "Data points",
        "type": "group",
        "children": [
            {"name": "Symbol", "type": "list", "value": "o",
             "limits": ["o", "s", "t", "d", "+"]},
            {"name": "Size", "type": "int", "value": 8, "limits": (2, 20)},
            {"name": "Alpha", "type": "int", "value": 200, "limits": (0, 255)},
        ],
    },
    {
        "name": "Dropped replicas",
        "type": "group",
        "children": [
            {"name": "Symbol", "type": "list", "value": "x",
             "limits": ["o", "s", "t", "d", "+", "x"]},
            {"name": "Size", "type": "int", "value": 8, "limits": (2, 20)},
            {"name": "Alpha", "type": "int", "value": 120, "limits": (0, 255)},
            {"name": "Visible", "type": "bool", "value": True},
        ],
    },
    {
        "name": "Average line",
        "type": "group",
        "children": [
            {"name": "Width", "type": "int", "value": 2, "limits": (1, 8)},
            {"name": "Style", "type": "list", "value": "solid",
             "limits": ["solid", "dash", "dot"]},
            {"name": "Visible", "type": "bool", "value": True},
        ],
    },
    {
        "name": "Fit curves",
        "type": "group",
        "children": [
            {"name": "Width", "type": "int", "value": 2, "limits": (1, 8)},
            {"name": "Style", "type": "list", "value": "solid",
             "limits": ["solid", "dash", "dot"]},
        ],
    },
    {
        "name": "Visibility",
        "type": "group",
        "children": [
            {"name": "Show replicas", "type": "bool", "value": True},
            {"name": "Show average", "type": "bool", "value": True},
            {"name": "Show fit", "type": "bool", "value": True},
            {"name": "Show error bars", "type": "bool", "value": True},
        ],
    },
]


def line_style_to_qt(style_str: str):
    """Map style string to Qt.PenStyle.

    Parameters
    ----------
    style_str : str
        One of ``"solid"``, ``"dash"``, ``"dot"``.

    Returns
    -------
    Qt.PenStyle
    """
    from PyQt6.QtCore import Qt
    mapping = {
        "solid": Qt.PenStyle.SolidLine,
        "dash": Qt.PenStyle.DashLine,
        "dot": Qt.PenStyle.DotLine,
    }
    return mapping.get(style_str, Qt.PenStyle.SolidLine)


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
                "symbol": p["Data points", "Symbol"],
                "size": p["Data points", "Size"],
                "alpha": p["Data points", "Alpha"],
            },
            "dropped_replicas": {
                "symbol": p["Dropped replicas", "Symbol"],
                "size": p["Dropped replicas", "Size"],
                "alpha": p["Dropped replicas", "Alpha"],
                "visible": p["Dropped replicas", "Visible"],
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
                "show_replicas": p["Visibility", "Show replicas"],
                "show_average": p["Visibility", "Show average"],
                "show_fit": p["Visibility", "Show fit"],
                "show_error_bars": p["Visibility", "Show error bars"],
            },
        }
