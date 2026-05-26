"""Dialog for saving the distributions plot as a composite PNG or SVG.

The dialog uses :meth:`DistributionWidget.build_composite_layout` for
both the live preview and the eventual saved file, so the preview
cannot drift from the output. Persisted under ``QSettings`` group
``distributions_export/*``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
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

from gui.plotting.export import (
    prepare_widget_for_offscreen_render,
    render_scene_to_qimage,
)
from gui.plotting.labels import fmt_param
from gui.preferences import _settings

if TYPE_CHECKING:
    from gui.plotting.distribution_widget import DistributionWidget


_LAYOUT_MODES = ('auto', 'row', 'col', 'grid', 'custom')

# Width presets. Height is always derived from the live cell aspect ×
# the chosen layout (rows × cols) — picking a width fully determines
# the output figure since each cell's pixel size is locked to the
# live distribution widget's per-cell size.
_DIM_PRESETS = (
    ('per_panel', 'Per-panel (4 in / col)'),
    ('wide', 'Wide (16 in)'),
    ('single_col', 'Single-column (3.5 in)'),
    ('double_col', 'Double-column (7 in)'),
    ('custom', 'Custom'),
)

_PER_PANEL_IN = 4.0
_PREVIEW_W = 360
_PREVIEW_H = 280
# Cap preview render resolution to keep refresh snappy. For DPI ≤ ~375
# the preview renders at the user's chosen scale exactly (= save scale);
# above that, the cap reduces fidelity but keeps proportions close.
_PREVIEW_MAX_DIM = 1500


@dataclass
class DistributionsExportConfig:
    """Return value when the dialog is accepted.

    ``height_in`` is derived from ``width_in`` × layout × live cell
    aspect (see :meth:`DistributionWidget.derive_height_in`). It is
    included for callers that need to display it but never used as an
    input to the save.
    """

    keys: list[str]
    rows: int
    cols: int
    width_in: float
    height_in: float  # derived; informational only
    dpi: int
    format: str = 'png'


class SaveDistributionsPlotDialog(QDialog):
    """Pick subplots, layout, dimensions, and format for the distributions image.

    Notes
    -----
    The dialog never writes to disk itself. On Accepted, the caller
    reads :pyattr:`config` and runs the save via
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
        self.config: DistributionsExportConfig | None = None
        self._suppress_dim_signal = False

        self._build_ui()
        self._load_settings()
        self._update_layout_state()
        self._update_dimension_state()
        self._update_format_state()
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

        # --- format ------------------------------------------------------
        format_box = QGroupBox('Format')
        format_lay = QHBoxLayout(format_box)
        self._format_group = QButtonGroup(self)
        self._format_png = QRadioButton('PNG (raster)')
        self._format_svg = QRadioButton('SVG (vector)')
        self._format_png.setChecked(True)
        self._format_group.addButton(self._format_png)
        self._format_group.addButton(self._format_svg)
        self._format_png.toggled.connect(self._on_format_changed)
        self._format_svg.toggled.connect(self._on_format_changed)
        format_lay.addWidget(self._format_png)
        format_lay.addWidget(self._format_svg)
        format_lay.addStretch(1)
        controls.addWidget(format_box)

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
        self._dpi_spin = QSpinBox()
        self._dpi_spin.setRange(72, 600)
        self._dpi_spin.setSingleStep(50)
        self._dpi_spin.setSuffix(' DPI')

        self._width_spin.valueChanged.connect(self._on_dim_edited)
        self._dpi_spin.valueChanged.connect(self._refresh_preview)

        # Height label is derived from width × layout × live cell aspect.
        # Showing it informs the user without exposing a fudge-able input.
        self._height_label = QLabel('—')
        self._height_label.setStyleSheet('color: #555;')

        dim_form.addRow('Width', self._width_spin)
        dim_form.addRow('Height', self._height_label)
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

    def _current_format(self) -> str:
        return 'svg' if self._format_svg.isChecked() else 'png'

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
        return self._custom_rows.value(), self._custom_cols.value()

    def _width_for_preset(self, preset: str, cols: int) -> float | None:
        """Return ``width_in`` for a preset, or ``None`` for 'custom'.

        Height is no longer a preset input — it is derived from the
        live cell aspect × layout via :meth:`_derived_height_in`.
        """
        if preset == 'per_panel':
            return cols * _PER_PANEL_IN
        if preset == 'wide':
            return 16.0
        if preset == 'single_col':
            return 3.5
        if preset == 'double_col':
            return 7.0
        return None

    def _derived_height_in(self, *, width_in: float, rows: int, cols: int) -> float:
        return self._dist_widget.derive_height_in(
            width_in=width_in, rows=rows, cols=cols,
        )

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
        # If the user drives width directly, the preset is no longer a
        # defining input — flip silently to "Custom".
        if self._suppress_dim_signal:
            return
        if self._current_preset() != 'custom':
            self._set_preset_silently('custom')
        self._refresh_preview()

    def _on_format_changed(self) -> None:
        self._update_format_state()
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

    def _update_dimension_state(self) -> None:
        preset = self._current_preset()
        _rows, cols = self._resolved_layout()
        width = self._width_for_preset(preset, cols)
        if width is not None:
            self._suppress_dim_signal = True
            try:
                self._width_spin.setValue(width)
            finally:
                self._suppress_dim_signal = False
        self._refresh_height_label()

    def _refresh_height_label(self) -> None:
        rows, cols = self._resolved_layout()
        h_in = self._derived_height_in(
            width_in=self._width_spin.value(),
            rows=rows,
            cols=cols,
        )
        self._height_label.setText(f'{h_in:.2f} in (auto, matches GUI aspect)')

    def _update_format_state(self) -> None:
        """DPI input is meaningless for vector SVG; grey it out."""
        self._dpi_spin.setEnabled(self._current_format() == 'png')

    def _set_preset_silently(self, key: str) -> None:
        idx = next(
            (i for i, (k, _) in enumerate(_DIM_PRESETS) if k == key), 0
        )
        self._dim_preset.blockSignals(True)
        self._dim_preset.setCurrentIndex(idx)
        self._dim_preset.blockSignals(False)

    # ------------------------------------------------------------------
    # Preview rendering — uses the same code path as the final save.
    # ------------------------------------------------------------------

    def _refresh_preview(self) -> None:
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
        h_in = self._derived_height_in(width_in=w_in, rows=rows, cols=cols)
        dpi = self._dpi_spin.value()
        fmt = self._current_format()
        self._refresh_height_label()

        if fmt == 'png':
            px_w = round(w_in * dpi)
            px_h = round(h_in * dpi)
            self._size_label.setText(
                f'Output: {px_w} × {px_h} px  '
                f'({w_in:.2f} × {h_in:.2f} in @ {dpi} DPI, PNG)'
            )
        else:
            self._size_label.setText(
                f'Output: {w_in:.2f} × {h_in:.2f} in (SVG vector)'
            )

        # Build the same composite the save will build. Each cell is
        # sized at the live distribution subplot's pixel dimensions, so
        # font:cell, line:cell, marker:cell ratios are identical to
        # the GUI by construction. ImageExporter scales the whole
        # scene uniformly to the requested output width.
        keys = self._selected_keys()
        cell_w, cell_h = self._dist_widget.live_per_cell_size()
        logical_w = max(1, cell_w * cols)
        logical_h = max(1, cell_h * rows)
        if fmt == 'png':
            preview_target_w = min(round(w_in * dpi), _PREVIEW_MAX_DIM)
        else:
            preview_target_w = min(round(w_in * 200), _PREVIEW_MAX_DIM)
        preview_target_w = max(preview_target_w, _PREVIEW_W)

        glw = self._dist_widget.build_composite_layout(keys, rows, cols)
        try:
            prepare_widget_for_offscreen_render(glw, logical_w, logical_h)
            img = render_scene_to_qimage(glw.scene(), preview_target_w)
        finally:
            glw.deleteLater()

        pix = QPixmap.fromImage(img).scaled(
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
            if w > 0:
                self._suppress_dim_signal = True
                try:
                    self._width_spin.setValue(w)
                finally:
                    self._suppress_dim_signal = False
            dpi = int(s.value('dpi', 300))
            self._dpi_spin.setValue(dpi)

            fmt = s.value('format', 'png', type=str)
            if fmt == 'svg':
                self._format_svg.setChecked(True)
            else:
                self._format_png.setChecked(True)

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
            s.setValue('dpi', self._dpi_spin.value())
            s.setValue('format', self._current_format())
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
        w_in = float(self._width_spin.value())
        h_in = self._derived_height_in(width_in=w_in, rows=rows, cols=cols)
        self.config = DistributionsExportConfig(
            keys=keys,
            rows=rows,
            cols=cols,
            width_in=w_in,
            height_in=h_in,
            dpi=self._dpi_spin.value(),
            format=self._current_format(),
        )
        self._save_settings()
        self.accept()
