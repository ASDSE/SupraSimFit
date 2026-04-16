"""AssayConfigPanel — registry-driven assay type selector and conditions form."""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QLocale, Qt, pyqtSignal
from PyQt6.QtWidgets import QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core.assays.base import BaseAssay
from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.units import Q_, Quantity
from gui.assay_descriptions import ASSAY_DESCRIPTIONS
from gui.widgets.assay_conditions import ASSAY_CONDITIONS, ConditionField, assay_class, condition_fields
from gui.widgets.info_button import InfoButton, InfoGroupBox
from gui.widgets.numeric_inputs import NoScrollDoubleSpinBox

# Display choices derived from ConditionField.unit_type
_UNIT_TYPE_CHOICES: dict[str, tuple[tuple[str, ...], str]] = {
    'concentration': (('nM', 'µM', 'mM', 'M'), 'µM'),
    'binding_constant': (('M⁻¹',), 'M⁻¹'),
}

_LOCALE_EN = QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)


class _UnitWidget(QWidget):
    """Spinbox paired with an optional unit selector.

    For fields with display choices (concentration, binding constant) a
    ``QComboBox`` is shown next to the spinbox.  Changing the unit converts
    the displayed value so the physical quantity stays constant.

    ``value()`` always returns a ``pint.Quantity`` in the base unit.
    ``setValue(v)`` accepts a float in the base unit.

    Signals
    -------
    value_changed()
        Emitted when the numeric value (in base units) changes.
    """

    value_changed = pyqtSignal()

    def __init__(self, field: ConditionField, parent=None):
        super().__init__(parent)
        self._base_unit: str = field.unit or ''
        entry = _UNIT_TYPE_CHOICES.get(field.unit_type)
        choices = entry[0] if entry else ()
        default_lbl = entry[1] if entry else ''
        self._units: list[tuple[str, float]] = [(label, float(Q_(1, label).to(self._base_unit).magnitude)) for label in choices] if choices and self._base_unit else []
        self._current_scale: float = 1.0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._spinbox = NoScrollDoubleSpinBox()
        self._spinbox.setLocale(_LOCALE_EN)
        layout.addWidget(self._spinbox, stretch=1)

        if self._units:
            self._combo = QComboBox()
            for label, _ in self._units:
                self._combo.addItem(label)
            default_idx = next((i for i, (lbl, _) in enumerate(self._units) if lbl == default_lbl), 0)
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

    def value(self) -> Quantity:
        """Return value as a Quantity in the base unit (M or M⁻¹)."""
        return Q_(self._spinbox.value() * self._current_scale, self._base_unit)

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
        self._spinbox.blockSignals(True)
        self._spinbox.setRange(0.0, 1e15)
        self._spinbox.setDecimals(3)
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


_SECTION_HELP_HTML = """
<h3>Assay Configuration</h3>
<p>Select the assay type (DBA, GDA, IDA, Dye Alone) and enter the
experimental conditions (concentrations, known binding constants) used
in the measurement. The form updates automatically when you switch
assay type.</p>
<p>See the <i>i</i> next to the assay selector for a description of
each assay model.</p>
"""


class AssayConfigPanel(InfoGroupBox):
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
        super().__init__('Assay Configuration', 'Assay Configuration', _SECTION_HELP_HTML, parent)
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

        # Assay type selector + info button
        self._combo = QComboBox()
        for at in ASSAY_CONDITIONS:
            self._combo.addItem(ASSAY_REGISTRY[at].display_name, userData=at)
        self._combo.currentIndexChanged.connect(self._on_type_changed)

        self._assay_info_btn = InfoButton('Assay type', '')

        combo_row = QWidget()
        combo_lay = QHBoxLayout(combo_row)
        combo_lay.setContentsMargins(0, 0, 0, 0)
        combo_lay.setSpacing(6)
        combo_lay.addWidget(self._combo, 1)
        combo_lay.addWidget(self._assay_info_btn)
        layout.addWidget(combo_row)

        # Dynamic conditions form
        self._form_widget = QWidget()
        self._form_layout = QFormLayout(self._form_widget)
        self._form_layout.setContentsMargins(0, 4, 0, 0)
        layout.addWidget(self._form_widget)

        # Populate initial form + info text
        self._rebuild_form(self._current_type)
        self._refresh_assay_info(self._current_type)

    def _refresh_assay_info(self, assay_type: AssayType) -> None:
        title, body = ASSAY_DESCRIPTIONS.get(
            assay_type.name,
            (
                ASSAY_REGISTRY[assay_type].display_name,
                f'<p>No description available for <b>{assay_type.name}</b>.</p>',
            ),
        )
        self._assay_info_btn.set_content(title, body)

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
        self._refresh_assay_info(at)
        self.assay_type_changed.emit(at)
        self.conditions_changed.emit()
