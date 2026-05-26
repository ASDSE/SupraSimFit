"""Dialog for saving the distributions plot as a composite PNG.

Replaces the older ``ExportDistributionsDialog`` (checkbox-only) with a
fully ergonomic layout + dimension picker plus a live preview pane.

Persisted under ``QSettings`` group ``distributions_export/*``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from gui.plotting.labels import fmt_param
from gui.preferences import _settings

if TYPE_CHECKING:
    from gui.plotting.distribution_widget import DistributionWidget


_LAYOUT_MODES = ('auto', 'row', 'col', 'grid', 'custom')

_DIM_PRESETS = (
    ('per_panel', 'Per-panel (4 in each)'),
    ('wide', 'Wide (16 × 9 in)'),
    ('square', 'Square (8 × 8 in)'),
    ('single_col', 'Single-column figure (3.5 in wide)'),
    ('double_col', 'Double-column figure (7 in wide)'),
    ('custom', 'Custom'),
)

_PER_PANEL_IN = 4.0
_PREVIEW_W = 360
_PREVIEW_H = 280


@dataclass
class DistributionsExportConfig:
    """Return value when the dialog is accepted."""

    keys: list[str]
    rows: int
    cols: int
    width_in: float
    height_in: float
    dpi: int


class SaveDistributionsPlotDialog(QDialog):
    """Pick subplots, layout, and dimensions for the distributions PNG.

    Notes
    -----
    The dialog never writes to disk itself. On Accepted, the caller reads
    :pyattr:`config` and runs the save via
    :meth:`DistributionWidget.save_plot`.
    """

    SETTINGS_GROUP = 'distributions_export'

    def __init__(
        self,
        dist_widget: 'DistributionWidget',
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle('Save Distributions Plot')
        self.setMinimumWidth(720)

        self._dist_widget = dist_widget
        self._keys: list[str] = list(dist_widget.param_keys())
        self._thumb_cache: list[QImage] = []
        self.config: DistributionsExportConfig | None = None

        self._build_ui()
        self._load_settings()
        self._build_thumbnails()
        self._update_layout_state()
        self._update_dimension_state()
        self._refresh_preview()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        outer = QHBoxLayout()
        outer.setSpacing(16)
        root.addLayout(outer, stretch=1)
        controls = QVBoxLayout()
        controls.setSpacing(10)
        outer.addLayout(controls, stretch=0)

        # --- subplots ----------------------------------------------------
        sub_box = QGroupBox('Subplots')
        sub_lay = QVBoxLayout(sub_box)
        self._checkboxes: list[QCheckBox] = []
        check_row = QHBoxLayout()
        check_row.setSpacing(16)
        for key in self._keys:
            self._add_check_cell(check_row, key)
        check_row.addStretch(1)
        sub_lay.addLayout(check_row)

        all_btn = QPushButton('Select all')
        none_btn = QPushButton('Select none')
        all_btn.clicked.connect(lambda: [c.setChecked(True) for c in self._checkboxes])
        none_btn.clicked.connect(lambda: [c.setChecked(False) for c in self._checkboxes])
        btn_row = QHBoxLayout()
        btn_row.addWidget(all_btn)
        btn_row.addWidget(none_btn)
        btn_row.addStretch(1)
        sub_lay.addLayout(btn_row)
        controls.addWidget(sub_box)

        # --- layout ------------------------------------------------------
        layout_box = QGroupBox('Layout')
        layout_lay = QVBoxLayout(layout_box)
        self._layout_group = QButtonGroup(self)
        self._layout_radios: dict[str, QRadioButton] = {}
        for mode, label in (
            ('auto', 'Auto (smart default)'),
            ('row', '1 × N (single row)'),
            ('col', 'N × 1 (single column)'),
            ('grid', '2 × 2 grid'),
            ('custom', 'Custom'),
        ):
            rb = QRadioButton(label)
            self._layout_group.addButton(rb)
            self._layout_radios[mode] = rb
            rb.toggled.connect(self._on_layout_changed)
            layout_lay.addWidget(rb)

        custom_row = QHBoxLayout()
        self._custom_rows = QSpinBox()
        self._custom_rows.setRange(1, 12)
        self._custom_rows.setValue(2)
        self._custom_cols = QSpinBox()
        self._custom_cols.setRange(1, 12)
        self._custom_cols.setValue(2)
        custom_row.addSpacing(20)
        custom_row.addWidget(QLabel('rows'))
        custom_row.addWidget(self._custom_rows)
        custom_row.addWidget(QLabel('× cols'))
        custom_row.addWidget(self._custom_cols)
        custom_row.addStretch(1)
        layout_lay.addLayout(custom_row)
        self._custom_rows.valueChanged.connect(self._on_custom_layout_changed)
        self._custom_cols.valueChanged.connect(self._on_custom_layout_changed)

        self._layout_warning = QLabel('')
        self._layout_warning.setStyleSheet('color: #b00; font-size: 11px;')
        self._layout_warning.setWordWrap(True)
        layout_lay.addWidget(self._layout_warning)
        controls.addWidget(layout_box)

        # --- dimensions --------------------------------------------------
        dim_box = QGroupBox('Dimensions')
        dim_form = QFormLayout(dim_box)
        self._dim_preset = QComboBox()
        for key, label in _DIM_PRESETS:
            self._dim_preset.addItem(label, userData=key)
        self._dim_preset.currentIndexChanged.connect(self._on_preset_changed)
        dim_form.addRow('Preset', self._dim_preset)

        self._width_spin = QDoubleSpinBox()
        self._width_spin.setRange(1.0, 40.0)
        self._width_spin.setSingleStep(0.5)
        self._width_spin.setSuffix(' in')
        self._height_spin = QDoubleSpinBox()
        self._height_spin.setRange(1.0, 40.0)
        self._height_spin.setSingleStep(0.5)
        self._height_spin.setSuffix(' in')
        self._dpi_spin = QSpinBox()
        self._dpi_spin.setRange(72, 600)
        self._dpi_spin.setSingleStep(50)
        self._dpi_spin.setSuffix(' DPI')

        self._width_spin.valueChanged.connect(self._on_dim_edited)
        self._height_spin.valueChanged.connect(self._on_dim_edited)
        self._dpi_spin.valueChanged.connect(self._refresh_preview)

        dim_form.addRow('Width', self._width_spin)
        dim_form.addRow('Height', self._height_spin)
        dim_form.addRow('Resolution', self._dpi_spin)
        controls.addWidget(dim_box)

        controls.addStretch(1)

        # --- preview pane ------------------------------------------------
        preview_col = QVBoxLayout()
        preview_col.addWidget(QLabel('Preview'))
        self._preview_label = QLabel()
        self._preview_label.setFixedSize(_PREVIEW_W, _PREVIEW_H)
        self._preview_label.setStyleSheet(
            'border: 1px solid #888; background: white;'
        )
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_col.addWidget(self._preview_label)
        self._size_label = QLabel('Output: —')
        self._size_label.setStyleSheet('color: #444;')
        preview_col.addWidget(self._size_label)
        preview_col.addStretch(1)
        outer.addLayout(preview_col, stretch=1)

        # --- buttons -----------------------------------------------------
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Save…')
        self._buttons.accepted.connect(self._on_accept)
        self._buttons.rejected.connect(self.reject)
        root.addWidget(self._buttons)

    def _add_check_cell(self, row: QHBoxLayout, key: str) -> None:
        """Append one checkbox + HTML label to a shared single-row layout."""
        cb = QCheckBox()
        cb.setChecked(True)
        cb.toggled.connect(self._on_selection_changed)
        lbl = QLabel(fmt_param(key))
        lbl.setTextFormat(Qt.TextFormat.RichText)

        def _toggle(_event, c=cb):
            c.toggle()

        lbl.mousePressEvent = _toggle
        row.addWidget(cb)
        row.addWidget(lbl)
        self._checkboxes.append(cb)

    # ------------------------------------------------------------------
    # State derivation
    # ------------------------------------------------------------------

    def _selected_keys(self) -> list[str]:
        return [k for k, c in zip(self._keys, self._checkboxes) if c.isChecked()]

    def _selected_count(self) -> int:
        return sum(1 for c in self._checkboxes if c.isChecked())

    def _current_layout_mode(self) -> str:
        for mode, rb in self._layout_radios.items():
            if rb.isChecked():
                return mode
        return 'auto'

    def _current_preset(self) -> str:
        return self._dim_preset.currentData()

    def _resolved_layout(self) -> tuple[int, int]:
        from gui.plotting.distribution_widget import DistributionWidget

        n = max(1, self._selected_count())
        mode = self._current_layout_mode()
        if mode == 'auto':
            return DistributionWidget.auto_layout(n)
        if mode == 'row':
            return 1, n
        if mode == 'col':
            return n, 1
        if mode == 'grid':
            if n <= 4:
                return 2, 2
            return DistributionWidget.auto_layout(n)
        # custom
        return self._custom_rows.value(), self._custom_cols.value()

    def _dimensions_for_preset(
        self, preset: str, rows: int, cols: int
    ) -> tuple[float, float] | None:
        """Return (width_in, height_in) for a preset, or None for 'custom'."""
        if preset == 'per_panel':
            return cols * _PER_PANEL_IN, rows * _PER_PANEL_IN
        if preset == 'wide':
            return 16.0, 9.0
        if preset == 'square':
            return 8.0, 8.0
        if preset == 'single_col':
            return 3.5, 3.5 * rows / max(1, cols)
        if preset == 'double_col':
            return 7.0, 7.0 * rows / max(1, cols)
        return None

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------

    def _on_selection_changed(self) -> None:
        self._update_layout_state()
        self._update_dimension_state()
        self._refresh_preview()

    def _on_layout_changed(self) -> None:
        self._update_layout_state()
        self._update_dimension_state()
        self._refresh_preview()

    def _on_custom_layout_changed(self) -> None:
        if self._current_layout_mode() == 'custom':
            self._update_layout_state()
            self._update_dimension_state()
            self._refresh_preview()

    def _on_preset_changed(self) -> None:
        self._update_dimension_state()
        self._refresh_preview()

    def _on_dim_edited(self) -> None:
        # If the user drives width/height directly, the preset is no longer
        # a defining input — flip silently to "Custom".
        if self._suppress_dim_signal:
            return
        if self._current_preset() != 'custom':
            self._set_preset_silently('custom')
        self._refresh_preview()

    # ------------------------------------------------------------------
    # State application
    # ------------------------------------------------------------------

    def _update_layout_state(self) -> None:
        n = self._selected_count()
        custom_active = self._current_layout_mode() == 'custom'
        self._custom_rows.setEnabled(custom_active)
        self._custom_cols.setEnabled(custom_active)

        ok = self._buttons.button(QDialogButtonBox.StandardButton.Ok) if hasattr(self, '_buttons') else None
        rows, cols = self._resolved_layout()
        if n == 0:
            msg = 'Select at least one subplot.'
            if ok:
                ok.setEnabled(False)
        elif rows * cols < n:
            msg = f'{rows}×{cols} cannot fit {n} subplots — increase rows or cols.'
            if ok:
                ok.setEnabled(False)
        else:
            msg = ''
            if ok:
                ok.setEnabled(True)
        self._layout_warning.setText(msg)

    _suppress_dim_signal = False

    def _update_dimension_state(self) -> None:
        preset = self._current_preset()
        rows, cols = self._resolved_layout()
        dims = self._dimensions_for_preset(preset, rows, cols)
        if dims is not None:
            w, h = dims
            self._suppress_dim_signal = True
            try:
                self._width_spin.setValue(w)
                self._height_spin.setValue(h)
            finally:
                self._suppress_dim_signal = False

    def _set_preset_silently(self, key: str) -> None:
        idx = next(
            (i for i, (k, _) in enumerate(_DIM_PRESETS) if k == key), 0
        )
        self._dim_preset.blockSignals(True)
        self._dim_preset.setCurrentIndex(idx)
        self._dim_preset.blockSignals(False)

    # ------------------------------------------------------------------
    # Preview rendering
    # ------------------------------------------------------------------

    def _build_thumbnails(self) -> None:
        """Render a moderate-res thumbnail per subplot once.

        Sized large enough to avoid upscaling in any practical preview
        layout (preview pane is rendered at up to ~720 px wide before
        being scaled down for display).
        """
        import pyqtgraph as pg
        import pyqtgraph.exporters  # noqa: F401

        thumb_w = 600
        for idx, _key in enumerate(self._keys):
            if idx >= len(self._dist_widget._plots):
                break
            exporter = pg.exporters.ImageExporter(
                self._dist_widget._plots[idx].getPlotItem()
            )
            exporter.parameters()['width'] = thumb_w
            img = exporter.export(toBytes=True)
            if isinstance(img, QImage):
                self._thumb_cache.append(img)

    def _refresh_preview(self) -> None:
        if not self._thumb_cache:
            return
        n = self._selected_count()
        if n == 0:
            self._preview_label.clear()
            self._size_label.setText('Output: —')
            return

        rows, cols = self._resolved_layout()
        if rows * cols < n:
            self._preview_label.clear()
            self._size_label.setText('Output: (invalid layout)')
            return

        w_in = self._width_spin.value()
        h_in = self._height_spin.value()
        dpi = self._dpi_spin.value()
        px_w = round(w_in * dpi)
        px_h = round(h_in * dpi)
        self._size_label.setText(
            f'Output: {px_w} × {px_h} px  ({w_in:.2f} × {h_in:.2f} in @ {dpi} DPI)'
        )

        # Render the composite into an oversized canvas that matches the
        # real aspect ratio, then scale-to-fit the fixed preview area.
        # Oversizing relative to ``_PREVIEW_W`` lets the final smooth
        # downscale produce a crisp anti-aliased preview.
        target_long = 2 * max(_PREVIEW_W, _PREVIEW_H)  # ~720 px
        if w_in >= h_in:
            aspect_w = target_long
            aspect_h = max(1, round(target_long * h_in / max(w_in, 1e-6)))
        else:
            aspect_h = target_long
            aspect_w = max(1, round(target_long * w_in / max(h_in, 1e-6)))
        cell_w = aspect_w // cols
        cell_h = aspect_h // rows
        canvas = QImage(aspect_w, aspect_h, QImage.Format.Format_ARGB32)
        canvas.fill(Qt.GlobalColor.white)
        painter = QPainter(canvas)
        try:
            i = 0
            for key_idx, key in enumerate(self._keys):
                if not self._checkboxes[key_idx].isChecked():
                    continue
                if key_idx >= len(self._thumb_cache):
                    continue
                thumb = self._thumb_cache[key_idx]
                scaled = thumb.scaled(
                    cell_w,
                    cell_h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                r, c = divmod(i, cols)
                x = c * cell_w + (cell_w - scaled.width()) // 2
                y = r * cell_h + (cell_h - scaled.height()) // 2
                painter.drawImage(x, y, scaled)
                i += 1
        finally:
            painter.end()

        pix = QPixmap.fromImage(canvas).scaled(
            _PREVIEW_W,
            _PREVIEW_H,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._preview_label.setPixmap(pix)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_settings(self) -> None:
        s = _settings()
        s.beginGroup(self.SETTINGS_GROUP)
        try:
            mode = s.value('layout_mode', 'auto', type=str)
            self._layout_radios.get(mode, self._layout_radios['auto']).setChecked(True)
            self._custom_rows.setValue(int(s.value('custom_rows', 2)))
            self._custom_cols.setValue(int(s.value('custom_cols', 2)))
            preset = s.value('dimension_preset', 'per_panel', type=str)
            self._set_preset_silently(preset)
            w = float(s.value('width_in', 0.0))
            h = float(s.value('height_in', 0.0))
            if w > 0 and h > 0:
                self._suppress_dim_signal = True
                try:
                    self._width_spin.setValue(w)
                    self._height_spin.setValue(h)
                finally:
                    self._suppress_dim_signal = False
            dpi = int(s.value('dpi', 300))
            self._dpi_spin.setValue(dpi)

            sel = s.value('selected_keys', None)
            if isinstance(sel, list) and sel:
                keep = set(sel)
                for k, cb in zip(self._keys, self._checkboxes):
                    cb.setChecked(k in keep)
        finally:
            s.endGroup()

    def _save_settings(self) -> None:
        s = _settings()
        s.beginGroup(self.SETTINGS_GROUP)
        try:
            s.setValue('layout_mode', self._current_layout_mode())
            s.setValue('custom_rows', self._custom_rows.value())
            s.setValue('custom_cols', self._custom_cols.value())
            s.setValue('dimension_preset', self._current_preset())
            s.setValue('width_in', float(self._width_spin.value()))
            s.setValue('height_in', float(self._height_spin.value()))
            s.setValue('dpi', self._dpi_spin.value())
            s.setValue('selected_keys', self._selected_keys())
        finally:
            s.endGroup()

    # ------------------------------------------------------------------
    # Accept
    # ------------------------------------------------------------------

    def _on_accept(self) -> None:
        keys = self._selected_keys()
        if not keys:
            return
        rows, cols = self._resolved_layout()
        self.config = DistributionsExportConfig(
            keys=keys,
            rows=rows,
            cols=cols,
            width_in=float(self._width_spin.value()),
            height_in=float(self._height_spin.value()),
            dpi=self._dpi_spin.value(),
        )
        self._save_settings()
        self.accept()
