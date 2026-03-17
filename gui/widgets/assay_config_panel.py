"""AssayConfigPanel — registry-driven assay type selector and conditions form."""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QLocale, Qt, pyqtSignal
from PyQt6.QtWidgets import QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core.assays.base import BaseAssay
from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.units import Q_
from gui.widgets.assay_conditions import ASSAY_CONDITIONS, ConditionField, assay_class, condition_fields

# Unit definitions derived from pint (single source of truth).
# Each entry: (display_label, scale_factor_to_base_unit)
_CONCENTRATION_UNITS: list[tuple[str, float]] = [
    ('nM', float(Q_(1, 'nM').to('M').magnitude)),
    ('µM', float(Q_(1, 'µM').to('M').magnitude)),
    ('mM', float(Q_(1, 'millimolar').to('M').magnitude)),
    ('M', 1.0),
]
_BINDING_CONSTANT_UNITS: list[tuple[str, float]] = [
    ('M⁻¹', 1.0),
    ('kM⁻¹', float(Q_(1, 'millimolar**-1').to('M**-1').magnitude)),
    ('MM⁻¹', float(Q_(1, 'µM**-1').to('M**-1').magnitude)),
]

# Default unit labels by unit_type
_DEFAULT_UNIT: dict[str, str] = {
    'concentration': 'µM',
    'binding_constant': 'M⁻¹',
}

_LOCALE_EN = QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)


def _units_for_type(unit_type: str) -> list[tuple[str, float]]:
    if unit_type == 'concentration':
        return _CONCENTRATION_UNITS
    if unit_type == 'binding_constant':
        return _BINDING_CONSTANT_UNITS
    return []


def _spinbox_range_for_unit(unit_label: str) -> tuple[float, float, int]:
    """Return (min, max, decimals) appropriate for the given unit label."""
    ranges: dict[str, tuple[float, float, int]] = {
        'nM': (0.0, 1e9, 3),
        'µM': (0.0, 1e6, 3),
        'mM': (0.0, 1e3, 4),
        'M': (0.0, 1.0, 6),
        'M⁻¹': (0.0, 1e15, 3),
        'kM⁻¹': (0.0, 1e12, 3),
        'MM⁻¹': (0.0, 1e9, 3),
    }
    return ranges.get(unit_label, (0.0, 1e15, 3))


class _UnitWidget(QWidget):
    """Spinbox paired with an optional unit selector.

    For fields with ``unit_type`` of ``"concentration"`` or
    ``"binding_constant"`` a ``QComboBox`` is shown next to the spinbox.
    Changing the unit converts the displayed value so the physical quantity
    stays constant.

    ``value()`` always returns the quantity in the base unit (M or M⁻¹).
    ``setValue(v)`` accepts a value in the base unit.

    Signals
    -------
    value_changed()
        Emitted when the numeric value (in base units) changes.
    """

    value_changed = pyqtSignal()

    def __init__(self, field: ConditionField, parent=None):
        super().__init__(parent)
        self._unit_type = field.unit_type
        self._units = _units_for_type(field.unit_type)
        self._current_scale: float = 1.0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._spinbox = QDoubleSpinBox()
        self._spinbox.setLocale(_LOCALE_EN)
        layout.addWidget(self._spinbox, stretch=1)

        if self._units:
            self._combo = QComboBox()
            for label, _ in self._units:
                self._combo.addItem(label)
            default_label = _DEFAULT_UNIT.get(field.unit_type, self._units[0][0])
            default_idx = next((i for i, (lbl, _) in enumerate(self._units) if lbl == default_label), 0)
            self._combo.setCurrentIndex(default_idx)
            self._current_scale = self._units[default_idx][1]
            self._combo.currentIndexChanged.connect(self._on_unit_changed)
            layout.addWidget(self._combo)
        else:
            self._combo = None
            self._spinbox.setRange(0.0, 1e15)
            self._spinbox.setDecimals(3)

        # Set spinbox range/decimals for the initial unit
        self._apply_range_for_current_unit()

        # Set initial displayed value from base-unit default
        displayed = field.default / self._current_scale
        self._spinbox.setValue(displayed)

        self._spinbox.valueChanged.connect(self._on_spinbox_changed)

    def value(self) -> float:
        """Return value in base unit (M or M⁻¹)."""
        return self._spinbox.value() * self._current_scale

    def setValue(self, base_value: float) -> None:
        """Set widget from a base-unit value."""
        self._spinbox.blockSignals(True)
        self._spinbox.setValue(base_value / self._current_scale)
        self._spinbox.blockSignals(False)

    def setToolTip(self, tip: str) -> None:
        self._spinbox.setToolTip(tip)
        if self._combo is not None:
            self._combo.setToolTip(tip)

    def _apply_range_for_current_unit(self) -> None:
        if self._combo is not None:
            label = self._combo.currentText()
        else:
            label = ''
        lo, hi, dp = _spinbox_range_for_unit(label)
        self._spinbox.blockSignals(True)
        self._spinbox.setRange(lo, hi)
        self._spinbox.setDecimals(dp)
        self._spinbox.blockSignals(False)

    def _on_unit_changed(self, idx: int) -> None:
        # Preserve physical quantity when unit changes
        old_base = self._spinbox.value() * self._current_scale
        self._current_scale = self._units[idx][1]
        self._apply_range_for_current_unit()
        self._spinbox.blockSignals(True)
        self._spinbox.setValue(old_base / self._current_scale)
        self._spinbox.blockSignals(False)
        self.value_changed.emit()

    def _on_spinbox_changed(self) -> None:
        self.value_changed.emit()


class AssayConfigPanel(QGroupBox):
    """Registry-driven assay type selector and dynamic conditions form.

    The combo box is populated from :data:`ASSAY_CONDITIONS`.  Switching the
    assay type regenerates the conditions form automatically — no per-assay
    widget code is needed.

    Signals
    -------
    assay_type_changed(AssayType)
        Emitted when the user selects a different assay type.
    conditions_changed()
        Emitted when any condition field value changes.
    """

    assay_type_changed = pyqtSignal(object)  # AssayType
    conditions_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__('Assay Configuration', parent)
        self._current_type: AssayType = AssayType.GDA
        self._field_widgets: dict[str, _UnitWidget] = {}
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def current_assay_type(self) -> AssayType:
        return self._current_type

    def current_conditions(self) -> dict[str, Any]:
        """Return conditions dict (values in base units) including implicit DBA mode."""
        conditions = {key: w.value() for key, w in self._field_widgets.items()}
        if self._current_type == AssayType.DBA_HtoD:
            conditions['mode'] = 'HtoD'
        elif self._current_type == AssayType.DBA_DtoH:
            conditions['mode'] = 'DtoH'
        return conditions

    def get_assay_class(self) -> type[BaseAssay]:
        return assay_class(self._current_type)

    def set_assay_type(self, assay_type: AssayType) -> None:
        idx = list(ASSAY_CONDITIONS.keys()).index(assay_type)
        self._combo.setCurrentIndex(idx)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Assay type selector
        self._combo = QComboBox()
        for at in ASSAY_CONDITIONS:
            self._combo.addItem(ASSAY_REGISTRY[at].display_name, userData=at)
        self._combo.currentIndexChanged.connect(self._on_type_changed)
        layout.addWidget(self._combo)

        # Dynamic conditions form
        self._form_widget = QWidget()
        self._form_layout = QFormLayout(self._form_widget)
        self._form_layout.setContentsMargins(0, 4, 0, 0)
        layout.addWidget(self._form_widget)

        # Populate initial form
        self._rebuild_form(self._current_type)

    def _rebuild_form(self, assay_type: AssayType) -> None:
        # Clear previous widgets
        self._field_widgets.clear()
        while self._form_layout.rowCount():
            self._form_layout.removeRow(0)

        fields = condition_fields(assay_type)
        if not fields:
            self._form_layout.addRow(QLabel('(no conditions required)'))
            return

        for f in fields:
            unit_widget = _UnitWidget(f)
            unit_widget.setToolTip(f.tooltip)
            unit_widget.value_changed.connect(self.conditions_changed)

            lbl = QLabel(f.label)
            lbl.setTextFormat(Qt.TextFormat.RichText)

            self._form_layout.addRow(lbl, unit_widget)
            self._field_widgets[f.key] = unit_widget

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_type_changed(self, idx: int) -> None:
        at = self._combo.itemData(idx)
        self._current_type = at
        self._rebuild_form(at)
        self.assay_type_changed.emit(at)
        self.conditions_changed.emit()
