"""AssayConfigPanel — registry-driven assay type selector and conditions form."""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QLocale, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core.assays.base import BaseAssay
from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.units import Q_, Quantity
from gui.assay_descriptions import ASSAY_DESCRIPTIONS
from gui.plotting.labels import and_join, plain_label
from gui.widgets.assay_conditions import TITRANT_STOCK_FIELD, ConditionField, assay_class, condition_fields
from gui.widgets.info_button import InfoButton, InfoGroupBox
from gui.widgets.numeric_inputs import NoScrollDoubleSpinBox, decimals_for_scale

# Display choices derived from ConditionField.unit_type
_UNIT_TYPE_CHOICES: dict[str, tuple[tuple[str, ...], str]] = {
    'concentration': (('nM', 'µM', 'mM', 'M'), 'µM'),
    'binding_constant': (('M⁻¹',), 'M⁻¹'),
}

_LOCALE_EN = QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)

# Pause in typing or stepping after which a conditions edit counts as finished.
_EDIT_SETTLE_MS = 600

_SUPERSCRIPT = str.maketrans('-0123456789', '⁻⁰¹²³⁴⁵⁶⁷⁸⁹')

# What the two entries of the dilution combo stand for, as their item data.
_CONSTANT_TOTALS = 'constant'
_DILUTED = 'diluted'


def _set_form_geometry(form: QFormLayout) -> None:
    """One column geometry for every form that holds a concentration of the assay.

    The conditions and the titrant stock below them sit in separate layouts, so
    each would otherwise size its label column and its fields on its own and the
    stock's box would start at another x than the conditions' boxes.
    """
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)


def plain_number(value: float) -> str:
    """Up to four significant figures, with a power of ten written as ``1.68×10⁷``."""
    mantissa, _, exponent = f'{value:.4g}'.partition('e')
    return f'{mantissa}×10{str(int(exponent)).translate(_SUPERSCRIPT)}' if exponent else mantissa


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
    edit_finished()
        Emitted when Return is pressed or focus leaves the spinbox, and when the unit is switched.
    """

    value_changed = pyqtSignal()
    edit_finished = pyqtSignal()

    def __init__(self, field: ConditionField, parent=None):
        super().__init__(parent)
        self._label = field.label
        self._base_unit: str = field.unit or ''
        entry = _UNIT_TYPE_CHOICES.get(field.unit_type)
        choices = entry[0] if entry else ()
        default_lbl = entry[1] if entry else ''
        self._units: list[tuple[str, float]] = (
            [(label, float(Q_(1, label).to(self._base_unit).magnitude)) for label in choices]
            if choices and self._base_unit
            else []
        )
        # Finest offered unit sets the smallest representable step; coarser units
        # widen their decimals relative to it so a switch never loses the value.
        self._min_scale: float = min((scale for _, scale in self._units), default=1.0)
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

        # Set spinbox range/decimals for the initial unit
        self._apply_range_for_current_unit()

        # Set initial displayed value from base-unit default
        displayed = field.default / self._current_scale
        self._spinbox.setValue(displayed)

        self._spinbox.valueChanged.connect(self._on_spinbox_changed)
        self._spinbox.editingFinished.connect(self.edit_finished)

    def value(self) -> Quantity:
        """Return value as a Quantity in the base unit (M or M⁻¹)."""
        return Q_(self._spinbox.value() * self._current_scale, self._base_unit)

    def name(self) -> str:
        """This field's label in plain text: ``[Host]₀``."""
        return plain_label(self._label)

    def format(self, value: Quantity) -> str:
        """*value* in plain text in the unit this field shows now: ``4.3 µM``."""
        magnitude = value.to(self._base_unit).magnitude if self._base_unit else float(value.magnitude)
        unit = self._combo.currentText() if self._combo is not None else self._base_unit
        return f'{plain_number(magnitude / self._current_scale)} {unit}'.rstrip()

    def setValue(self, base_value: float) -> None:
        """Set widget from a base-unit value."""
        self._spinbox.blockSignals(True)
        self._spinbox.setValue(base_value / self._current_scale)
        self._spinbox.blockSignals(False)

    def setToolTip(self, tip: str) -> None:
        self._spinbox.setToolTip(tip)
        if self._combo is not None:
            self._combo.setToolTip(tip)

    def focus_widgets(self) -> list[QWidget]:
        """The widgets that take the keyboard in this field, in reading order: the box, then its unit."""
        return [self._spinbox] if self._combo is None else [self._spinbox, self._combo]

    def _decimals_for_scale(self, scale: float) -> int:
        """Per-unit decimals via the shared policy in ``gui.widgets.numeric_inputs``."""
        return decimals_for_scale(scale, self._min_scale)

    def _apply_range_for_current_unit(self) -> None:
        self._spinbox.blockSignals(True)
        self._spinbox.setRange(0.0, 1e15)
        self._spinbox.setDecimals(self._decimals_for_scale(self._current_scale))
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
        self.edit_finished.emit()

    def _on_spinbox_changed(self) -> None:
        self.value_changed.emit()


_SECTION_HELP_HTML = """
<h3>Assay Configuration</h3>
<p>Pick the assay <b>category</b> (Competitive Displacement, Direct Binding,
Calibration) in the first dropdown, then the specific <b>variant</b> in the
second. The conditions form and parameter bounds update automatically when
you switch.</p>
<p>See the <i>i</i> next to the variant selector for a description of each
assay model.</p>
<h4>Dilution by the titrant</h4>
<p>Below the conditions you state whether each addition of titrant dilutes the
sample. The fixed concentrations <b>stay constant</b> when the samples were made
up to the same volume, or when the titrant stock was prepared in the sample
solution itself; otherwise they <b>are diluted by each addition of titrant</b>.
The concentrations in your data file are the titrant concentrations
<b>in the cuvette after each addition</b>. If yours were computed without
dilution — stock concentration times volume added, over the starting volume,
call it <i>x</i><sub>nominal</sub> — convert them with
<i>x</i> = <i>x</i><sub>nominal</sub>·<i>c</i><sub>T</sub> /
(<i>c</i><sub>T</sub> + <i>x</i><sub>nominal</sub>), where
<i>c</i><sub>T</sub> is the titrant stock concentration.</p>
<p><b>Diluted</b> asks for that stock concentration. A sample of volume
<i>V</i><sub>0</sub> that has taken up a volume <i>W</i> of the stock holds
<i>x</i> = <i>c</i><sub>T</sub>·<i>W</i>/(<i>V</i><sub>0</sub>+<i>W</i>) of
titrant, so a fraction <i>x</i>/<i>c</i><sub>T</sub> of the final volume came
from the stock and every fixed concentration falls by it — no volumes needed.
Tick a species the stock itself holds at the sample's own concentration: the
additions leave that one where it is.</p>
"""


class AssayConfigPanel(InfoGroupBox):
    """Registry-driven assay type selector and dynamic conditions form.

    A two-level selector — a *category* combo and a dependent *subtype* combo —
    is derived from ``ASSAY_REGISTRY`` (grouped by ``AssayMetadata.category``).
    Switching either combo regenerates the conditions form automatically — no
    per-assay widget code is needed.

    Under the form, every assay with a fixed concentration asks whether the
    additions of titrant dilute the sample. The answer is the user's: the form
    opens on constant totals and ``current_conditions()`` carries the titrant
    stock only once dilution is chosen.

    Signals
    -------
    assay_type_changed(AssayType)
        Emitted when the user selects a different assay type.
    conditions_changed()
        Emitted when any condition field value changes, keystroke by keystroke.
    conditions_edited()
        Emitted once an edit is finished: Return or focus leaving a field, a
        unit or assay switch, a pause in typing or stepping, or
        :meth:`finish_edit`. Typing a value emits it once, not per keystroke.
    """

    assay_type_changed = pyqtSignal(object)  # AssayType
    conditions_changed = pyqtSignal()
    conditions_edited = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__('Assay Configuration', 'Assay Configuration', _SECTION_HELP_HTML, parent)
        self._current_type: AssayType = AssayType.GDA
        self._field_widgets: dict[str, _UnitWidget] = {}
        # The conditions form's labels, in field order: one column with the stock's.
        self._condition_labels: list[QLabel] = []
        # The assay's fixed concentrations, in field order: what dilutes.
        self._conc_keys: tuple[str, ...] = ()
        self._contains_boxes: dict[str, QCheckBox] = {}
        # category -> assay types (registry order); drives the two-level menu.
        self._groups: dict[str, list[AssayType]] = {}
        for at, meta in ASSAY_REGISTRY.items():
            self._groups.setdefault(meta.category, []).append(at)
        self._settle_timer = QTimer(self)
        self._settle_timer.setSingleShot(True)
        self._settle_timer.setInterval(_EDIT_SETTLE_MS)
        self._settle_timer.timeout.connect(self.conditions_edited)
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def current_assay_type(self) -> AssayType:
        return self._current_type

    def current_conditions(self) -> dict[str, Any]:
        """Return conditions dict (values in base units) including implicit DBA mode.

        With dilution chosen it also carries ``titrant_stock`` (a Quantity in M)
        and ``stock_contains`` (the concentration keys the stock holds, in field
        order); with the totals constant neither key is there, so the assay is
        built exactly as it is without this form's dilution controls.
        """
        conditions = {key: w.value() for key, w in self._field_widgets.items()}
        if self._current_type == AssayType.DBA_HtoD:
            conditions['mode'] = 'HtoD'
        elif self._current_type == AssayType.DBA_DtoH:
            conditions['mode'] = 'DtoH'
        if self._diluted():
            conditions[TITRANT_STOCK_FIELD.key] = self._stock_widget.value()
            conditions['stock_contains'] = tuple(key for key, box in self._contains_boxes.items() if box.isChecked())
        return conditions

    def problems(self) -> list[str]:
        """Why the dilution as stated cannot be used, one sentence per problem.

        Empty with the totals constant, and empty once a titration's dilution is
        fully described. The remaining check — the stock has to be more
        concentrated than the highest titrant concentration — needs the loaded
        data, so the session makes that one.
        """
        if not self._diluted():
            return []
        problems: list[str] = []
        if self._stock_widget.value().magnitude <= 0:
            problems.append(
                "Enter the titrant stock concentration, or choose 'stay constant'. It is the concentration "
                'of the stock the titrant was added from, and it says how much each addition dilutes the sample.'
            )
        contained = [key for key, box in self._contains_boxes.items() if box.isChecked()]
        if contained and len(contained) == len(self._conc_keys):
            names = and_join(self._field_widgets[key].name() for key in contained)
            problems.append(
                f'The titrant stock is ticked for every fixed concentration ({names}), so nothing is left '
                "for the additions to dilute — that is the 'stay constant' case: choose it instead."
            )
        return problems

    def get_assay_class(self) -> type[BaseAssay]:
        return assay_class(self._current_type)

    def finish_edit(self) -> None:
        """Finish an edit still waiting for its pause, so what reads the form next sees it finished.

        Emits ``conditions_edited`` when an edit is pending and nothing otherwise.
        An action run from a shortcut leaves the focus in the field being typed
        into, so no edit ends by itself before the action reads the form.
        """
        if self._settle_timer.isActive():
            self._finish_edit()

    def condition_name(self, key: str) -> str | None:
        """Plain-text label of condition *key* (``[Host]₀``), or ``None`` when the form has no such field."""
        widget = self._condition_widget(key)
        return None if widget is None else widget.name()

    def format_condition(self, key: str, value: Quantity) -> str:
        """*value* of condition *key* in plain text, in the unit its field shows now: ``4.3 µM``."""
        widget = self._condition_widget(key)
        if widget is None:
            raise KeyError(key)
        return widget.format(value)

    def _condition_widget(self, key: str) -> _UnitWidget | None:
        """The widget holding condition *key*, the titrant stock included."""
        if key == TITRANT_STOCK_FIELD.key:
            return self._stock_widget
        return self._field_widgets.get(key)

    def set_assay_type(self, assay_type: AssayType) -> None:
        """Programmatically select an assay (demo loader, tests).

        Selects the matching category and subtype and emits
        ``assay_type_changed`` exactly once, like a user selection.
        """
        category = ASSAY_REGISTRY[assay_type].category
        main_blocked = self._main_combo.blockSignals(True)
        sub_blocked = self._sub_combo.blockSignals(True)
        self._main_combo.setCurrentIndex(self._main_combo.findData(category))
        self._populate_sub(category)
        self._sub_combo.setCurrentIndex(self._sub_combo.findData(assay_type))
        self._main_combo.blockSignals(main_blocked)
        self._sub_combo.blockSignals(sub_blocked)
        self._apply_assay(assay_type)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Category selector (main) on its own row.
        self._main_combo = QComboBox()
        for category in self._groups:
            self._main_combo.addItem(category, userData=category)
        self._main_combo.currentIndexChanged.connect(self._on_main_changed)
        layout.addWidget(self._main_combo)

        # Subtype selector (dependent) + info button on the row below.
        self._sub_combo = QComboBox()
        self._assay_info_btn = InfoButton('Assay type', '')
        sub_row = QWidget()
        sub_lay = QHBoxLayout(sub_row)
        sub_lay.setContentsMargins(0, 0, 0, 0)
        sub_lay.setSpacing(6)
        sub_lay.addWidget(self._sub_combo, 1)
        sub_lay.addWidget(self._assay_info_btn)
        layout.addWidget(sub_row)

        # Initial selection: default assay, without emitting during construction.
        default_category = ASSAY_REGISTRY[self._current_type].category
        self._main_combo.blockSignals(True)
        self._main_combo.setCurrentIndex(self._main_combo.findData(default_category))
        self._main_combo.blockSignals(False)
        self._populate_sub(default_category)
        self._sub_combo.setCurrentIndex(self._sub_combo.findData(self._current_type))
        self._sub_combo.currentIndexChanged.connect(self._on_sub_changed)

        # Dynamic conditions form
        self._form_widget = QWidget()
        self._form_layout = QFormLayout(self._form_widget)
        self._form_layout.setContentsMargins(0, 4, 0, 0)
        _set_form_geometry(self._form_layout)
        layout.addWidget(self._form_widget)

        layout.addWidget(self._build_dilution_controls())

        # Populate initial form + info text (no signal emission — matches prior init).
        self._rebuild_form(self._current_type)
        self._refresh_assay_info(self._current_type)

    def _build_dilution_controls(self) -> QWidget:
        """The dilution choice and what it asks for, built once for the session.

        The stock keeps its unit and its value across assay switches — the
        choice above it returns to constant totals, so a value carried over is
        one the user sees in front of them before it can reach a fit.
        """
        self._dilution_widget = QWidget()
        outer = QVBoxLayout(self._dilution_widget)
        outer.setContentsMargins(0, 6, 0, 0)
        outer.setSpacing(4)

        self._dilution_label = QLabel()
        self._dilution_label.setTextFormat(Qt.TextFormat.RichText)
        self._dilution_label.setWordWrap(True)
        outer.addWidget(self._dilution_label)

        self._dilution_combo = QComboBox()
        self._dilution_combo.addItem('stay constant', userData=_CONSTANT_TOTALS)
        self._dilution_combo.addItem('are diluted by each addition of titrant', userData=_DILUTED)
        # The entry chosen completes the sentence above it, so it is read closed:
        # the combo is as wide as its longest entry. What each answer means is in
        # the tooltip and in the section help.
        self._dilution_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._dilution_combo.setToolTip(
            'Whether each addition of titrant dilutes the sample. It does not if the samples were made up to '
            'the same volume, or if the titrant stock was prepared in the sample solution itself.'
        )
        self._dilution_combo.currentIndexChanged.connect(self._on_dilution_changed)
        outer.addWidget(self._dilution_combo)

        self._stock_row = QWidget()
        stock_form = QFormLayout(self._stock_row)
        stock_form.setContentsMargins(0, 2, 0, 0)
        _set_form_geometry(stock_form)
        self._stock_widget = _UnitWidget(TITRANT_STOCK_FIELD)
        self._stock_widget.setToolTip(TITRANT_STOCK_FIELD.tooltip)
        self._stock_widget.value_changed.connect(self.conditions_changed)
        self._stock_widget.value_changed.connect(self._settle_timer.start)
        self._stock_widget.edit_finished.connect(self._finish_edit)
        self._stock_label = QLabel(TITRANT_STOCK_FIELD.label)
        self._stock_label.setTextFormat(Qt.TextFormat.RichText)
        self._stock_label.setToolTip(TITRANT_STOCK_FIELD.tooltip)
        stock_form.addRow(self._stock_label, self._stock_widget)
        outer.addWidget(self._stock_row)

        self._contains_widget = QWidget()
        self._contains_layout = QVBoxLayout(self._contains_widget)
        self._contains_layout.setContentsMargins(0, 0, 0, 0)
        self._contains_layout.setSpacing(2)
        outer.addWidget(self._contains_widget)

        return self._dilution_widget

    def _populate_sub(self, category: str) -> None:
        """Fill the subtype combo with the assays in ``category`` (index 0 selected).

        Restores the combo's prior signal-blocked state so callers that have
        pre-blocked it stay blocked.
        """
        was_blocked = self._sub_combo.blockSignals(True)
        self._sub_combo.clear()
        for at in self._groups[category]:
            self._sub_combo.addItem(ASSAY_REGISTRY[at].subtype_label, userData=at)
        self._sub_combo.setCurrentIndex(0)
        self._sub_combo.blockSignals(was_blocked)

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
        self._condition_labels.clear()
        while self._form_layout.rowCount():
            self._form_layout.removeRow(0)

        fields = condition_fields(assay_type)
        if not fields:
            self._form_layout.addRow(QLabel('(no conditions required)'))
        for f in fields:
            unit_widget = _UnitWidget(f)
            unit_widget.setToolTip(f.tooltip)
            unit_widget.value_changed.connect(self.conditions_changed)
            unit_widget.value_changed.connect(self._settle_timer.start)
            unit_widget.edit_finished.connect(self._finish_edit)

            lbl = QLabel(f.label)
            lbl.setTextFormat(Qt.TextFormat.RichText)

            self._form_layout.addRow(lbl, unit_widget)
            self._field_widgets[f.key] = unit_widget
            self._condition_labels.append(lbl)

        self._rebuild_dilution(fields)
        self._align_columns()
        self._apply_tab_order()

    def _align_columns(self) -> None:
        """Give every label of a concentration the same width, so their boxes share a left edge.

        The titrant stock has the longest label and sits in a layout of its own,
        so it is the width the conditions above it take as well — whether or not
        the stock is on screen, so choosing the dilution shifts nothing.
        """
        labels = [*self._condition_labels, self._stock_label]
        width = max(label.sizeHint().width() for label in labels)
        for label in labels:
            label.setMinimumWidth(width)

    def _apply_tab_order(self) -> None:
        """Chain the panel's controls in the order they are read.

        Qt builds its focus chain from the order widgets were created, and the
        dilution controls are built once for the session while the conditions are
        rebuilt per assay. Chaining after every rebuild is what puts the stock and
        the species it holds behind the conditions they belong under.
        """
        chain: list[QWidget] = [self._main_combo, self._sub_combo, self._assay_info_btn]
        for widget in self._field_widgets.values():
            chain += widget.focus_widgets()
        chain.append(self._dilution_combo)
        chain += self._stock_widget.focus_widgets()
        chain += list(self._contains_boxes.values())
        for first, second in zip(chain, chain[1:]):
            QWidget.setTabOrder(first, second)

    def _rebuild_dilution(self, fields: tuple[ConditionField, ...]) -> None:
        """Offer this assay's fixed concentrations the dilution choice, unanswered.

        Only a concentration dilutes, so an assay with none (dye alone) is not
        asked. One fixed concentration gets no species boxes: a stock holding
        the only thing that could fall leaves nothing diluted, which is the
        constant case the other entry states.
        """
        conc_fields = [f for f in fields if f.unit_type == 'concentration']
        self._conc_keys = tuple(f.key for f in conc_fields)
        self._contains_boxes.clear()
        while self._contains_layout.count():
            widget = self._contains_layout.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        self._dilution_widget.setVisible(bool(conc_fields))
        if not conc_fields:
            return

        self._dilution_label.setText(f'During the titration, {and_join(f.label for f in conc_fields)}')
        blocked = self._dilution_combo.blockSignals(True)
        self._dilution_combo.setCurrentIndex(self._dilution_combo.findData(_CONSTANT_TOTALS))
        self._dilution_combo.blockSignals(blocked)

        if len(conc_fields) > 1:
            for f in conc_fields:
                self._contains_layout.addWidget(self._contains_row(f))

        self._show_dilution_inputs()

    def _contains_row(self, field: ConditionField) -> QWidget:
        """A tick for a species the titrant stock holds at the sample's own concentration."""
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)

        box = QCheckBox()
        # The macOS style lays a check box out by a rectangle narrower than the
        # one it paints, which puts the sentence beside it on the box.
        box.setAttribute(Qt.WidgetAttribute.WA_LayoutUsesWidgetRect)
        box.toggled.connect(self._on_contains_toggled)
        # The label carries the species' HTML, which a check box paints as text.
        lbl = QLabel(f'the titrant stock also contains {field.label} at this concentration')
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setWordWrap(True)
        row_layout.addWidget(box)
        row_layout.addWidget(lbl, 1)

        self._contains_boxes[field.key] = box
        return row

    def _diluted(self) -> bool:
        """Whether the user has said the additions dilute the sample."""
        return bool(self._conc_keys) and self._dilution_combo.currentData() == _DILUTED

    def _show_dilution_inputs(self) -> None:
        """Show what the chosen answer asks for, and nothing else."""
        diluted = self._diluted()
        self._stock_row.setVisible(diluted)
        self._contains_widget.setVisible(diluted and bool(self._contains_boxes))

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_dilution_changed(self, _idx: int) -> None:
        self._show_dilution_inputs()
        self.conditions_changed.emit()
        self._finish_edit()

    def _on_contains_toggled(self, _checked: bool) -> None:
        self.conditions_changed.emit()
        self._finish_edit()

    def _apply_assay(self, assay_type: AssayType) -> None:
        """Adopt a newly selected assay: rebuild the form/info and announce it."""
        self._current_type = assay_type
        self._rebuild_form(assay_type)
        self._refresh_assay_info(assay_type)
        self.assay_type_changed.emit(assay_type)
        self.conditions_changed.emit()
        self._finish_edit()

    def _finish_edit(self) -> None:
        self._settle_timer.stop()
        self.conditions_edited.emit()

    def _on_main_changed(self, idx: int) -> None:
        # Repopulate the subtype combo (signals blocked), then apply its first
        # entry — exactly one assay_type_changed emission per category switch.
        category = self._main_combo.itemData(idx)
        self._populate_sub(category)
        self._apply_assay(self._sub_combo.itemData(0))

    def _on_sub_changed(self, idx: int) -> None:
        at = self._sub_combo.itemData(idx)
        if at is None:  # transient empty state during repopulation
            return
        self._apply_assay(at)
