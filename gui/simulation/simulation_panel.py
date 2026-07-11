"""SimulationPanel — the registry-driven control stack for one assay.

Rebuilds its knob controls entirely from ``knobs_for(assay_type)`` whenever the
assay changes, then assembles a :class:`SimSpec` (everything
:mod:`core.simulation` needs) from the live control values.  Knows nothing
assay-specific beyond the registries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Type

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QGroupBox, QLabel, QVBoxLayout, QWidget

from core.assays.base import BaseAssay
from core.assays.registry import ASSAY_REGISTRY, AssayType
from gui.simulation.controls import ConcentrationInput, NoiseControl, ParameterControl
from gui.simulation.sim_knob import SECTION_ORDER, SECTION_TITLES, TITRANT_RANGE, knobs_for
from gui.widgets.assay_conditions import assay_class

_DEFAULT_N = 11

# DBA carries a categorical titration mode that is NOT a knob — it is fixed by the
# chosen subtype, exactly as AssayConfigPanel.current_conditions injects it.
_DBA_MODE = {AssayType.DBA_HtoD: 'HtoD', AssayType.DBA_DtoH: 'DtoH'}


@dataclass
class SimSpec:
    """Everything needed to simulate, assembled from the live controls."""

    assay_type: AssayType
    assay_cls: Type[BaseAssay]
    conditions: dict[str, Any]  # Quantity-valued (+ 'mode' str for DBA)
    parameters: dict[str, float]  # base-unit floats keyed by parameter_keys
    conc_mode: str
    conc_kwargs: dict[str, Any]
    noise: dict[str, Any]


class SimulationPanel(QWidget):
    """Live control stack: model/condition knobs + titration vector + noise."""

    changed = pyqtSignal()

    def __init__(self, assay_type: AssayType = AssayType.IDA, parent=None):
        super().__init__(parent)
        self._assay_type = assay_type
        self._controls: dict[str, ParameterControl] = {}
        self._is_condition: dict[str, bool] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # Knob controls live in registry-derived sections (built in _rebuild_knobs):
        # Concentrations / Equilibrium / Signal parameters.
        self._knob_container = QWidget()
        self._knob_layout = QVBoxLayout(self._knob_container)
        self._knob_layout.setContentsMargins(0, 0, 0, 0)
        self._knob_layout.setSpacing(8)
        root.addWidget(self._knob_container)

        conc_box = QGroupBox('Titration')
        conc_layout = QVBoxLayout(conc_box)
        self._conc_label = QLabel()
        conc_layout.addWidget(self._conc_label)
        self._conc_input = ConcentrationInput()
        conc_layout.addWidget(self._conc_input)
        root.addWidget(conc_box)

        noise_box = QGroupBox('Noise')
        noise_layout = QVBoxLayout(noise_box)
        self._noise = NoiseControl()
        noise_layout.addWidget(self._noise)
        root.addWidget(noise_box)

        self._conc_input.changed.connect(self.changed)
        self._noise.changed.connect(self.changed)

        self.set_assay_type(assay_type, _reset_range=True)

    # -- public API ----------------------------------------------------------

    def assay_type(self) -> AssayType:
        return self._assay_type

    def set_assay_type(self, assay_type: AssayType, *, _reset_range: bool = True) -> None:
        """Rebuild the knob controls for *assay_type* (registry-driven)."""
        self._assay_type = assay_type
        self._rebuild_knobs(assay_type)
        species = ASSAY_REGISTRY[assay_type].x_label
        self._conc_label.setTextFormat(Qt.TextFormat.RichText)
        self._conc_label.setText(f'Titrated species: <b>{species}</b>')
        if _reset_range:
            start, stop = TITRANT_RANGE.get(assay_type, (0.0, 50e-6))
            self._conc_input.set_linear(start, stop, _DEFAULT_N)
        self.changed.emit()

    def set_concentration_explicit(self, values_m) -> None:
        """Switch the titration input to an explicit vector (Molar). Used on data import."""
        self._conc_input.load_spec('explicit', {'values': [float(v) for v in values_m]})

    def spec(self) -> SimSpec:
        conditions: dict[str, Any] = {}
        parameters: dict[str, float] = {}
        for key, ctrl in self._controls.items():
            if self._is_condition.get(key, False):
                conditions[key] = ctrl.quantity()
            else:
                parameters[key] = ctrl.value()
        if self._assay_type in _DBA_MODE:
            conditions['mode'] = _DBA_MODE[self._assay_type]
        conc_mode, conc_kwargs = self._conc_input.spec()
        return SimSpec(
            assay_type=self._assay_type,
            assay_cls=assay_class(self._assay_type),
            conditions=conditions,
            parameters=parameters,
            conc_mode=conc_mode,
            conc_kwargs=conc_kwargs,
            noise=self._noise.settings(),
        )

    def state(self) -> dict:
        """Full serializable settings for save."""
        mode, kwargs = self._conc_input.spec()
        return {
            'assay_type': self._assay_type.name,
            'knobs': {key: ctrl.state() for key, ctrl in self._controls.items()},
            'concentration': {'mode': mode, 'kwargs': kwargs},
            'noise': self._noise.settings(),
        }

    def load_state(self, data: dict) -> None:
        at = AssayType[data['assay_type']]
        self.set_assay_type(at, _reset_range=False)
        for key, st in data.get('knobs', {}).items():
            if key in self._controls:
                self._controls[key].load_state(st)
        conc = data.get('concentration', {})
        if conc:
            self._conc_input.load_spec(conc.get('mode', 'linear'), conc.get('kwargs', {}))
        self._noise.load_settings(data.get('noise', {}))
        self.changed.emit()

    # -- internals -----------------------------------------------------------

    def _rebuild_knobs(self, assay_type: AssayType) -> None:
        # Detach old section boxes synchronously: deleteLater() alone is async, so
        # the previous assay's knobs keep painting (overlapping the new ones) until
        # the event loop runs — setParent(None) hides them immediately.
        while self._knob_layout.count():
            item = self._knob_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._controls.clear()
        self._is_condition.clear()

        by_section: dict[str, list] = {}
        for knob in knobs_for(assay_type):
            by_section.setdefault(knob.section, []).append(knob)

        # One group box per non-empty section, in the canonical display order.
        for section in SECTION_ORDER:
            section_knobs = by_section.get(section)
            if not section_knobs:
                continue
            box = QGroupBox(SECTION_TITLES[section])
            box_layout = QVBoxLayout(box)
            box_layout.setSpacing(2)
            for knob in section_knobs:
                ctrl = ParameterControl(knob)
                ctrl.changed.connect(self.changed)
                box_layout.addWidget(ctrl)
                self._controls[knob.key] = ctrl
                self._is_condition[knob.key] = knob.is_condition
            self._knob_layout.addWidget(box)
