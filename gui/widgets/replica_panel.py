"""ReplicaPanel — per-replica activation checkboxes."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QGridLayout, QGroupBox, QHBoxLayout, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from core.data_processing.measurement_set import MeasurementSet

_COLS_PER_ROW = 4


def _display_label(index: int) -> str:
    """Map a zero-based replica index to an A–Z display label.

    For indices 0–25 returns 'A'–'Z'.  Beyond that, returns 'AA', 'AB', etc.
    """
    if index < 26:
        return chr(65 + index)
    # Overflow: AA, AB, ...
    return chr(65 + index // 26 - 1) + chr(65 + index % 26)


class ReplicaPanel(QGroupBox):
    """Show one checkbox per replica and allow toggling active/inactive state.

    Auto-dropped replicas (deactivated by preprocessing) are visually
    distinguished with a ``(z-score)`` label.

    Signals
    -------
    replicas_changed()
        Emitted when any replica's active state is toggled by the user.
    """

    replicas_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__('Replicas', parent)
        self._ms: MeasurementSet | None = None
        self._checkboxes: dict[str, QCheckBox] = {}
        self._auto_dropped: set[str] = set()  # dropped by preprocessing
        self._setup_ui()
        self.setEnabled(False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_measurement_set(self, ms: MeasurementSet) -> None:
        """Populate checkboxes from MeasurementSet replica IDs."""
        self._ms = ms
        self._auto_dropped.clear()
        self._rebuild()
        self.setEnabled(True)

    def refresh(self) -> None:
        """Re-read active states from the MeasurementSet (after preprocessing)."""
        if self._ms is None:
            return
        # Track which replicas were just auto-dropped
        newly_inactive = {rid for rid in self._ms.replica_ids if not self._ms.is_active(rid)}
        self._auto_dropped = newly_inactive
        self._rebuild()

    def reset_all(self) -> None:
        if self._ms is None:
            return
        self._ms.reset_active()
        self._auto_dropped.clear()
        self._rebuild()
        self.replicas_changed.emit()

    def clear(self) -> None:
        self._ms = None
        self._checkboxes.clear()
        self._auto_dropped.clear()
        # Remove all widgets from the scroll area
        while self._replica_layout.count():
            item = self._replica_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.setEnabled(False)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)

        # Grid layout for compact replica checkboxes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(120)
        container = QWidget()
        self._replica_layout = QGridLayout(container)
        self._replica_layout.setContentsMargins(4, 4, 4, 4)
        self._replica_layout.setSpacing(4)
        scroll.setWidget(container)
        outer.addWidget(scroll)

        btn_row = QHBoxLayout()
        reset_btn = QPushButton('Reset All')
        reset_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        reset_btn.clicked.connect(self.reset_all)
        btn_row.addStretch(1)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch(1)
        outer.addLayout(btn_row)

    def _rebuild(self) -> None:
        """Rebuild the checkbox grid from current MeasurementSet state."""
        # Clear existing
        self._checkboxes.clear()
        while self._replica_layout.count():
            item = self._replica_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self._ms is None:
            return

        for i, rid in enumerate(self._ms.replica_ids):
            active = self._ms.is_active(rid)
            display = _display_label(i)
            label = display
            if rid in self._auto_dropped:
                label = f'{display} (z)'
            cb = QCheckBox(label)
            cb.setChecked(active)
            if rid in self._auto_dropped:
                cb.setStyleSheet('color: #888;')
            cb.setToolTip(f'Replica {rid}')
            # Capture rid in closure
            cb.toggled.connect(lambda checked, r=rid: self._on_toggled(r, checked))
            self._checkboxes[rid] = cb
            row, col = divmod(i, _COLS_PER_ROW)
            self._replica_layout.addWidget(cb, row, col)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_toggled(self, rid: str, checked: bool) -> None:
        if self._ms is None:
            return
        self._ms.set_active(rid, checked)
        # If user manually re-activates an auto-dropped replica, clear that label
        if checked and rid in self._auto_dropped:
            self._auto_dropped.discard(rid)
            cb = self._checkboxes.get(rid)
            if cb:
                idx = list(self._ms.replica_ids).index(rid)
                cb.setText(_display_label(idx))
                cb.setStyleSheet('')
        self.replicas_changed.emit()
