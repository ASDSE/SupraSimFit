"""AssayTypeSelector — a standalone two-level (category → subtype) assay picker.

Derived from ``ASSAY_REGISTRY`` (grouped by ``AssayMetadata.category``), it emits
``assay_type_changed`` exactly once per selection.  Used by the simulation applet;
``AssayConfigPanel`` keeps its own equivalent selector (only two call sites, so no
shared abstraction is forced).
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QVBoxLayout, QWidget

from core.assays.registry import ASSAY_REGISTRY, AssayType


class AssayTypeSelector(QWidget):
    """Two dependent combos: assay *category* then *subtype*.

    Signals
    -------
    assay_type_changed(AssayType)
        Emitted once whenever the selected assay type changes.
    """

    assay_type_changed = pyqtSignal(object)  # AssayType

    def __init__(self, initial: AssayType = AssayType.IDA, parent=None):
        super().__init__(parent)
        self._current_type = initial
        self._groups: dict[str, list[AssayType]] = {}
        for at, meta in ASSAY_REGISTRY.items():
            self._groups.setdefault(meta.category, []).append(at)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._main_combo = QComboBox()
        for category in self._groups:
            self._main_combo.addItem(category, userData=category)
        layout.addWidget(self._main_combo)

        self._sub_combo = QComboBox()
        layout.addWidget(self._sub_combo)

        # Initial selection without emitting during construction.
        category = ASSAY_REGISTRY[initial].category
        self._main_combo.blockSignals(True)
        self._main_combo.setCurrentIndex(self._main_combo.findData(category))
        self._main_combo.blockSignals(False)
        self._populate_sub(category)
        self._sub_combo.setCurrentIndex(self._sub_combo.findData(initial))

        self._main_combo.currentIndexChanged.connect(self._on_main_changed)
        self._sub_combo.currentIndexChanged.connect(self._on_sub_changed)

    # -- public API ----------------------------------------------------------

    def current_assay_type(self) -> AssayType:
        return self._current_type

    def set_assay_type(self, assay_type: AssayType) -> None:
        """Programmatically select an assay, emitting ``assay_type_changed`` once."""
        category = ASSAY_REGISTRY[assay_type].category
        main_blocked = self._main_combo.blockSignals(True)
        sub_blocked = self._sub_combo.blockSignals(True)
        self._main_combo.setCurrentIndex(self._main_combo.findData(category))
        self._populate_sub(category)
        self._sub_combo.setCurrentIndex(self._sub_combo.findData(assay_type))
        self._main_combo.blockSignals(main_blocked)
        self._sub_combo.blockSignals(sub_blocked)
        self._apply(assay_type)

    # -- internals -----------------------------------------------------------

    def _populate_sub(self, category: str) -> None:
        was_blocked = self._sub_combo.blockSignals(True)
        self._sub_combo.clear()
        for at in self._groups[category]:
            self._sub_combo.addItem(ASSAY_REGISTRY[at].subtype_label, userData=at)
        self._sub_combo.setCurrentIndex(0)
        self._sub_combo.blockSignals(was_blocked)

    def _apply(self, assay_type: AssayType) -> None:
        self._current_type = assay_type
        self.assay_type_changed.emit(assay_type)

    def _on_main_changed(self, idx: int) -> None:
        category = self._main_combo.itemData(idx)
        self._populate_sub(category)
        self._apply(self._sub_combo.itemData(0))

    def _on_sub_changed(self, idx: int) -> None:
        at = self._sub_combo.itemData(idx)
        if at is None:  # transient empty state during repopulation
            return
        self._apply(at)
