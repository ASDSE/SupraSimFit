"""Style configuration widget using PyQtGraph ParameterTree."""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QWidget
from pyqtgraph.parametertree import Parameter, ParameterTree

from gui.plotting.colors import PALETTE_NAMES

DEFAULT_STYLE: dict = {
    'axes': {
        'label_font_size': 18,
        'tick_font_size': 16,
        'x_unit': 'µM',
        'x_name_override': '',
        'y_name_override': '',
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

_MARKER_LIMITS = {
    'Circle': 'o',
    'Square': 's',
    'Triangle': 't',
    'Diamond': 'd',
    'Plus': '+',
    'Cross': 'x',
}

_LINE_STYLE_LIMITS = ['Solid', 'Dashed', 'Dotted']

_PARAMS_SPEC = [
    # Visibility is first — the most common thing to toggle
    {
        'name': 'Visibility',
        'type': 'group',
        'children': [
            {'name': 'Show replicates', 'type': 'bool', 'value': True},
            {'name': 'Show dropped replicates', 'type': 'bool', 'value': True},
            {'name': 'Show average', 'type': 'bool', 'value': False},
            {'name': 'Show error bars', 'type': 'bool', 'value': True},
            {'name': 'Show fit', 'type': 'bool', 'value': True},
            {'name': 'Show fit results', 'type': 'bool', 'value': True},
        ],
    },
    {
        'name': 'Axes',
        'type': 'group',
        'expanded': False,
        'children': [
            {'name': 'Label font size', 'type': 'int', 'value': 18, 'limits': (6, 24)},
            {'name': 'Tick font size', 'type': 'int', 'value': 16, 'limits': (6, 24)},
            {
                'name': 'X-axis name',
                'type': 'str',
                'value': '',
                'tip': 'Override the x-axis name (the unit suffix stays auto-managed). Leave empty to use the assay default. HTML is supported (e.g. [Host]<sub>0</sub>).',
            },
            {
                'name': 'Y-axis name',
                'type': 'str',
                'value': '',
                'tip': 'Override the y-axis name (the unit suffix stays auto-managed). Leave empty to use the assay default. HTML is supported.',
            },
        ],
    },
    {
        'name': 'Replicates',
        'type': 'group',
        'expanded': False,
        'children': [
            {'name': 'Marker', 'type': 'list', 'value': 'o', 'limits': _MARKER_LIMITS},
            {'name': 'Size', 'type': 'int', 'value': 10, 'limits': (2, 20)},
            {'name': 'Opacity', 'type': 'int', 'value': 200, 'limits': (0, 255)},
            {'name': 'Color palette', 'type': 'list', 'value': 'Default (Tab10)', 'limits': PALETTE_NAMES},
        ],
    },
    {
        'name': 'Dropped replicates',
        'type': 'group',
        'expanded': False,
        'children': [
            {'name': 'Marker', 'type': 'list', 'value': 'x', 'limits': _MARKER_LIMITS},
            {'name': 'Size', 'type': 'int', 'value': 11, 'limits': (2, 20)},
            {'name': 'Opacity', 'type': 'int', 'value': 255, 'limits': (0, 255)},
        ],
    },
    {
        'name': 'Average line',
        'type': 'group',
        'expanded': False,
        'children': [
            {'name': 'Width', 'type': 'int', 'value': 4, 'limits': (1, 8)},
            {'name': 'Style', 'type': 'list', 'value': 'Dashed', 'limits': _LINE_STYLE_LIMITS},
            {'name': 'Color', 'type': 'color', 'value': (0, 0, 0, 255)},
        ],
    },
    {
        'name': 'Fit curves',
        'type': 'group',
        'expanded': False,
        'children': [
            {'name': 'Width', 'type': 'int', 'value': 3, 'limits': (1, 8)},
            {'name': 'Style', 'type': 'list', 'value': 'Dashed', 'limits': _LINE_STYLE_LIMITS},
            {'name': 'Color', 'type': 'color', 'value': (23, 190, 207, 255)},
        ],
    },
    {
        'name': 'Analysis plots',
        'type': 'group',
        'expanded': False,
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
        'expanded': False,
        'children': [
            {'name': 'Baseline line width', 'type': 'float', 'value': 2.5, 'limits': (0.5, 8.0), 'step': 0.5},
            {'name': 'Baseline line color', 'type': 'color', 'value': (220, 0, 0, 255)},
        ],
    },
    {
        'name': 'Error bars',
        'type': 'group',
        'expanded': False,
        'children': [
            {'name': 'Width', 'type': 'int', 'value': 2, 'limits': (1, 8)},
            {'name': 'Color', 'type': 'color', 'value': (80, 80, 80, 255)},
            {'name': 'Cap size', 'type': 'int', 'value': 2, 'limits': (0, 30)},
        ],
    },
    {
        'name': 'Legend',
        'type': 'group',
        'expanded': False,
        'children': [
            {'name': 'Font size', 'type': 'int', 'value': 14, 'limits': (6, 24)},
            {'name': 'Background', 'type': 'color', 'value': (255, 255, 255, 200)},
            {'name': 'Show replicates', 'type': 'bool', 'value': True},
            {'name': 'Show dropped', 'type': 'bool', 'value': True},
            {'name': 'Show average', 'type': 'bool', 'value': True},
            {'name': 'Show error bars', 'type': 'bool', 'value': True},
            {'name': 'Show fit', 'type': 'bool', 'value': True},
        ],
    },
    {
        'name': 'Annotations',
        'type': 'group',
        'expanded': False,
        'children': [
            {'name': 'Font size', 'type': 'int', 'value': 14, 'limits': (7, 24)},
            {'name': 'Background', 'type': 'color', 'value': (255, 255, 255, 200)},
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

        # X-axis display unit is owned by Measurements (no ParameterTree
        # node here), but still round-trips through saved style JSONs via
        # ``axes.x_unit``. Externally settable via ``set_x_unit``.
        self._x_unit: str = DEFAULT_STYLE['axes']['x_unit']

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._tree)

    def _on_change(self, *_):
        self.style_changed.emit(self.current_style())

    def set_x_unit(self, unit: str) -> None:
        """Set the x-axis display unit and emit ``style_changed``.

        The x-axis unit no longer lives in the ParameterTree — it is
        owned by Measurements and pushed in here so that saved style
        dicts still carry it via ``axes.x_unit``.
        """
        if unit == self._x_unit:
            return
        self._x_unit = unit
        self.style_changed.emit(self.current_style())

    def current_style(self) -> dict:
        """Return a copy of the current style as a plain dict."""
        p = self._params
        return {
            'axes': {
                'label_font_size': p['Axes', 'Label font size'],
                'tick_font_size': p['Axes', 'Tick font size'],
                'x_unit': self._x_unit,
                'x_name_override': p['Axes', 'X-axis name'],
                'y_name_override': p['Axes', 'Y-axis name'],
            },
            'data_points': {
                'symbol': p['Replicates', 'Marker'],
                'size': p['Replicates', 'Size'],
                'alpha': p['Replicates', 'Opacity'],
                'palette': p['Replicates', 'Color palette'],
            },
            'dropped_replicas': {
                'symbol': p['Dropped replicates', 'Marker'],
                'size': p['Dropped replicates', 'Size'],
                'alpha': p['Dropped replicates', 'Opacity'],
            },
            'average_line': {
                'width': p['Average line', 'Width'],
                'style': p['Average line', 'Style'],
                'color': _qcolor_to_tuple(p['Average line', 'Color']),
            },
            'fit_curves': {
                'width': p['Fit curves', 'Width'],
                'style': p['Fit curves', 'Style'],
                'color': _qcolor_to_tuple(p['Fit curves', 'Color']),
            },
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
            'error_bars': {
                'visible': p['Visibility', 'Show error bars'],
                'width': p['Error bars', 'Width'],
                'color': _qcolor_to_tuple(p['Error bars', 'Color']),
                'cap_size': p['Error bars', 'Cap size'],
            },
            'visibility': {
                'show_data_points': p['Visibility', 'Show replicates'],
                'show_dropped': p['Visibility', 'Show dropped replicates'],
                'show_average': p['Visibility', 'Show average'],
                'show_fit': p['Visibility', 'Show fit'],
                'show_error_bars': p['Visibility', 'Show error bars'],
                'show_fit_results': p['Visibility', 'Show fit results'],
            },
            'legend': {
                'font_size': p['Legend', 'Font size'],
                'background_color': _qcolor_to_tuple(p['Legend', 'Background']),
                'show_replicas': p['Legend', 'Show replicates'],
                'show_dropped': p['Legend', 'Show dropped'],
                'show_average': p['Legend', 'Show average'],
                'show_error_bars': p['Legend', 'Show error bars'],
                'show_fit': p['Legend', 'Show fit'],
            },
            'annotations': {
                'font_size': p['Annotations', 'Font size'],
                'background_color': _qcolor_to_tuple(p['Annotations', 'Background']),
            },
        }

    def load_style(self, style: dict) -> None:
        """Apply a style dict to the ParameterTree, updating all widgets.

        Parameters
        ----------
        style : dict
            Style dict in the same format as ``current_style()`` returns.
            Missing keys are silently skipped.
        """
        p = self._params
        _map = {
            ('Axes', 'Label font size'): ('axes', 'label_font_size'),
            ('Axes', 'Tick font size'): ('axes', 'tick_font_size'),
            ('Axes', 'X-axis name'): ('axes', 'x_name_override'),
            ('Axes', 'Y-axis name'): ('axes', 'y_name_override'),
            ('Replicates', 'Marker'): ('data_points', 'symbol'),
            ('Replicates', 'Size'): ('data_points', 'size'),
            ('Replicates', 'Opacity'): ('data_points', 'alpha'),
            ('Replicates', 'Color palette'): ('data_points', 'palette'),
            ('Dropped replicates', 'Marker'): ('dropped_replicas', 'symbol'),
            ('Dropped replicates', 'Size'): ('dropped_replicas', 'size'),
            ('Dropped replicates', 'Opacity'): ('dropped_replicas', 'alpha'),
            ('Average line', 'Width'): ('average_line', 'width'),
            ('Average line', 'Style'): ('average_line', 'style'),
            ('Average line', 'Color'): ('average_line', 'color'),
            ('Fit curves', 'Width'): ('fit_curves', 'width'),
            ('Fit curves', 'Style'): ('fit_curves', 'style'),
            ('Fit curves', 'Color'): ('fit_curves', 'color'),
            ('Analysis plots', 'Title font size'): ('distribution', 'title_font_size'),
            ('Analysis plots', 'Label font size'): ('distribution', 'label_font_size'),
            ('Analysis plots', 'Tick font size'): ('distribution', 'tick_font_size'),
            ('Analysis plots', 'Ka scale'): ('distribution', 'ka_scale'),
            ('Ka Sensitivity', 'Baseline line width'): ('sensitivity', 'baseline_line_width'),
            ('Ka Sensitivity', 'Baseline line color'): ('sensitivity', 'baseline_line_color'),
            ('Error bars', 'Width'): ('error_bars', 'width'),
            ('Error bars', 'Color'): ('error_bars', 'color'),
            ('Error bars', 'Cap size'): ('error_bars', 'cap_size'),
            ('Visibility', 'Show replicates'): ('visibility', 'show_data_points'),
            ('Visibility', 'Show dropped replicates'): ('visibility', 'show_dropped'),
            ('Visibility', 'Show average'): ('visibility', 'show_average'),
            ('Visibility', 'Show fit'): ('visibility', 'show_fit'),
            ('Visibility', 'Show error bars'): ('visibility', 'show_error_bars'),
            ('Visibility', 'Show fit results'): ('visibility', 'show_fit_results'),
            ('Legend', 'Font size'): ('legend', 'font_size'),
            ('Legend', 'Background'): ('legend', 'background_color'),
            ('Legend', 'Show replicates'): ('legend', 'show_replicas'),
            ('Legend', 'Show dropped'): ('legend', 'show_dropped'),
            ('Legend', 'Show average'): ('legend', 'show_average'),
            ('Legend', 'Show error bars'): ('legend', 'show_error_bars'),
            ('Legend', 'Show fit'): ('legend', 'show_fit'),
            ('Annotations', 'Font size'): ('annotations', 'font_size'),
            ('Annotations', 'Background'): ('annotations', 'background_color'),
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
            # x_unit lives outside the ParameterTree.
            if 'axes' in style and 'x_unit' in style['axes']:
                self._x_unit = style['axes']['x_unit']
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
