"""Style configuration widget using PyQtGraph ParameterTree."""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QWidget
from pyqtgraph.parametertree import Parameter, ParameterTree

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
    # Type set and Ka scale of the Identifiability and Ka Sensitivity panels.
    # ``distribution`` is the group's name in saved style templates and so part
    # of that file format; the panel calls it "Analysis plots".
    'distribution': {
        'title_font_size': 16,
        'label_font_size': 14,
        'tick_font_size': 12,
        'ka_scale': 'log\u2081\u2080',
    },
    'sensitivity': {
        'baseline_line_width': 2.5,
        'baseline_line_color': (220, 0, 0, 255),
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

#: What Plot appearance offers: the look of the plots that read a style, Ka confidence and
#: Sensitivity. The titration plots of Measurements and Fit results are drawn to the
#: design (DESIGN.md §7), with the replicate display chosen in Fit results itself.
_PARAMS_SPEC = [
    {
        'name': 'Analysis plots',
        'type': 'group',
        'expanded': True,
        'children': [
            {'name': 'Ka scale', 'type': 'list', 'value': 'log\u2081\u2080', 'limits': ['log\u2081\u2080', 'linear']},
            {'name': 'Title font size', 'type': 'int', 'value': 16, 'limits': (6, 24)},
            {'name': 'Label font size', 'type': 'int', 'value': 14, 'limits': (6, 24)},
            {'name': 'Tick font size', 'type': 'int', 'value': 12, 'limits': (6, 24)},
        ],
    },
    {
        'name': 'Ka Sensitivity',
        'type': 'group',
        'expanded': True,
        'children': [
            {'name': 'Baseline line width', 'type': 'float', 'value': 2.5, 'limits': (0.5, 8.0), 'step': 0.5},
            {'name': 'Baseline line color', 'type': 'color', 'value': (220, 0, 0, 255)},
        ],
    },
]

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
        self._params = Parameter.create(name='Style', type='group', children=_PARAMS_SPEC)
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
            'distribution': {
                'title_font_size': p['Analysis plots', 'Title font size'],
                'label_font_size': p['Analysis plots', 'Label font size'],
                'tick_font_size': p['Analysis plots', 'Tick font size'],
                'ka_scale': p['Analysis plots', 'Ka scale'],
            },
            'sensitivity': {
                'baseline_line_width': p['Ka Sensitivity', 'Baseline line width'],
                'baseline_line_color': _qcolor_to_tuple(p['Ka Sensitivity', 'Baseline line color']),
            },
        }

    def load_style(self, style: dict) -> None:
        """Apply a style dict to the ParameterTree, updating all widgets.

        Parameters
        ----------
        style : dict
            Style dict in the same format as ``current_style()`` returns.
            Keys it does not hold are skipped: a saved template may carry the
            look of plots this panel does not style.
        """
        p = self._params
        _map = {
            ('Analysis plots', 'Title font size'): ('distribution', 'title_font_size'),
            ('Analysis plots', 'Label font size'): ('distribution', 'label_font_size'),
            ('Analysis plots', 'Tick font size'): ('distribution', 'tick_font_size'),
            ('Analysis plots', 'Ka scale'): ('distribution', 'ka_scale'),
            ('Ka Sensitivity', 'Baseline line width'): ('sensitivity', 'baseline_line_width'),
            ('Ka Sensitivity', 'Baseline line color'): ('sensitivity', 'baseline_line_color'),
        }
        # Block signals to avoid emitting per-param changes
        self._params.blockSignals(True)
        try:
            for (group, name), (section, key) in _map.items():
                if section in style and key in style[section]:
                    val = style[section][key]
                    # Color tuples need conversion for ParameterTree
                    if isinstance(val, (list, tuple)) and len(val) >= 3:
                        from PyQt6.QtGui import QColor

                        val = QColor(*val)
                    p[group, name] = val
        finally:
            self._params.blockSignals(False)
        # Emit one change after restoring all values
        self.style_changed.emit(self.current_style())


def save_style_json(style: dict, path: str | Path) -> None:
    """Save a style dict to a JSON file.

    Parameters
    ----------
    style : dict
        As returned by ``PlotStyleWidget.current_style()``.
    path : str or Path
        Destination file path.
    """
    with open(path, 'w') as f:
        json.dump(style, f, indent=2)


def load_style_json(path: str | Path) -> dict:
    """Load a style dict from a JSON file.

    Parameters
    ----------
    path : str or Path
        Source file path.

    Returns
    -------
    dict
        Style dict suitable for ``PlotStyleWidget.load_style()``.
    """
    with open(path) as f:
        return json.load(f)
