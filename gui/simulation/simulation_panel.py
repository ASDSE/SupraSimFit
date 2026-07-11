"""SimulationPanel — the registry-driven control stack for one assay.

Rebuilds its knob controls entirely from ``knobs_for(assay_type)`` whenever the
assay changes, then assembles a :class:`SimSpec` (everything
:mod:`core.simulation` needs) from the live control values.  Knows nothing
assay-specific beyond the registries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Type

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QGroupBox, QVBoxLayout, QWidget

from core.assays.base import BaseAssay
from core.assays.registry import ASSAY_REGISTRY, AssayType
from gui.simulation.controls import NoiseControl, ParameterControl, TitrantInput
from gui.simulation.sim_knob import SECTION_CONCENTRATION, SECTION_ORDER, SECTION_TITLES, TITRANT_RANGE, knobs_for
from gui.widgets.assay_conditions import assay_class

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

        # The titrant is itself a concentration, so its setup renders inside the
        # Concentrations section (placed there by _rebuild_knobs).  Created here,
        # parentless, so it survives the section boxes being rebuilt on assay change.
        self._titrant = TitrantInput()

        noise_box = QGroupBox('Noise')
        noise_layout = QVBoxLayout(noise_box)
        self._noise = NoiseControl()
        noise_layout.addWidget(self._noise)
        root.addWidget(noise_box)

        self._titrant.changed.connect(self.changed)
        self._noise.changed.connect(self.changed)

        self.set_assay_type(assay_type)

    # -- public API ----------------------------------------------------------

    def assay_type(self) -> AssayType:
        return self._assay_type

    def set_assay_type(self, assay_type: AssayType) -> None:
        """Rebuild the knob controls for *assay_type* (registry-driven)."""
        self._assay_type = assay_type
        self._rebuild_knobs(assay_type)  # reparents self._titrant into the Concentrations box
        species = ASSAY_REGISTRY[assay_type].x_label
        _, stop = TITRANT_RANGE.get(assay_type, (0.0, 50e-6))
        self._titrant.set_titrant(
            f'[{species}]<sub>0</sub>',
            f'Maximum {species.lower()} concentration — the titration scans 0 → this in '
            f'{TitrantInput.N_POINTS} points.',
            stop,
        )
        self.changed.emit()

    def set_concentration_explicit(self, values_m) -> None:
        """Switch the titration input to an explicit vector (Molar). Used on data import."""
        self._titrant.set_explicit([float(v) for v in values_m])

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
        conc_mode, conc_kwargs = self._titrant.spec()
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
        return {
            'assay_type': self._assay_type.name,
            'knobs': {key: ctrl.state() for key, ctrl in self._controls.items()},
            'titrant': self._titrant.state(),
            'noise': self._noise.settings(),
        }

    def load_state(self, data: dict) -> None:
        at = AssayType[data['assay_type']]
        self.set_assay_type(at)
        for key, st in data.get('knobs', {}).items():
            if key in self._controls:
                self._controls[key].load_state(st)
        self._titrant.load_state(data.get('titrant', {}))
        self._noise.load_settings(data.get('noise', {}))
        self.changed.emit()

    # -- internals -----------------------------------------------------------

    def _rebuild_knobs(self, assay_type: AssayType) -> None:
        # Detach the persistent titration widgets first so they survive the teardown
        # below (they are re-added to the new Concentrations box), then remove the old
        # section boxes synchronously: deleteLater() alone is async, so the previous
        # assay's knobs keep painting (overlapping the new ones) until the event loop
        # runs — setParent(None) hides them immediately.
        self._titrant.setParent(None)
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

        # One group box per section, in canonical display order.  The Concentrations
        # box is always shown — it also hosts the titrant input, which every assay has
        # (dye-alone has no fixed concentrations but is still a titration).  The other
        # sections appear only when they contain knobs.
        for section in SECTION_ORDER:
            section_knobs = by_section.get(section, [])
            is_concentration = section == SECTION_CONCENTRATION
            if not section_knobs and not is_concentration:
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
            if is_concentration:
                box_layout.addWidget(self._titrant)
            self._knob_layout.addWidget(box)
