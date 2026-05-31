"""DataPanel — file loading and concentration vector management."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.data_processing.concentration import (
    read_raw_concentrations,
    save_concentration_vector,
)
from core.data_processing.measurement_set import MeasurementSet
from core.io import load_measurements
from core.io.formats.bmg_reader import BMG_METADATA_KEY, BMG_PLACEHOLDER_KEY
from core.io.formats.ensight_reader import (
    ENSIGHT_CHANNEL_COLUMN,
    ENSIGHT_METADATA_KEY,
    format_channel_label,
)
from core.io.formats.jasco_reader import JASCO_METADATA_KEY
from core.io.registry import READERS
from core.units import Q_
from gui.widgets.info_button import InfoGroupBox

UNITS: tuple[str, ...] = ('nM', 'µM', 'mM', 'M')
DEFAULT_IMPORTED_UNIT = 'M'
DEFAULT_DISPLAY_UNIT = 'µM'


def _build_file_filter() -> str:
    """Build QFileDialog filter string from registered I/O readers."""
    parts = [f"*{ext}" for ext, _ in sorted(READERS.items())]
    all_exts = " ".join(parts)
    return f"Measurement files ({all_exts});;All files (*)"


def _build_data_help_html() -> str:
    """Build the Data panel help dialog HTML, listing supported formats dynamically."""
    exts = sorted(READERS.keys())
    ext_list = ", ".join(f"<code>{e}</code>" for e in exts) or "(none registered)"
    return f"""
<h3>Loading Measurement Data</h3>

<p>Raw data for the fitting session &mdash; everything below operates on
what you load here.</p>

<p><b>Load:</b> <i>Import &rarr; Import Data&hellip;</i> (<code>Ctrl+O</code>),
or <b>Demo IDA</b> for a bundled example. The format is detected from the
file. Supported: {ext_list} &mdash; including JASCO and PerkinElmer EnSight
CSVs and BMG plate exports.</p>

<p><b>Your own data &mdash; quickest path:</b> a plain CSV with a header row,
concentration in the first column and signal in the second:</p>
<pre style="background:#f3f3f3; padding:6px;">concentration,signal
0,1024
1e-6,2890
2e-6,4210</pre>
<p>For replicates in a CSV, add one signal column per replica
(<code>concentration,rep1,rep2,rep3</code>). A tab-separated <code>.txt</code>
takes the same two columns and appends each extra replica as a repeated
header+data block. Headers are matched loosely
(<code>conc</code>/<code>x</code>/<code>titrant</code>,
<code>signal</code>/<code>intensity</code>/<code>fluorescence</code>) and
European <code>;</code>/<code>,</code> files are read automatically.</p>

<p><b>Units:</b> <b>Imported Unit</b> declares what unit the loaded numbers
are in (it reinterprets them, it does not convert). <b>Display Unit</b> only
changes the plot's x-axis and never touches the stored data.</p>

<p><b>Concentrations:</b> titration files carry their own values. Plate-reader
and EnSight imports do not &mdash; the table shows placeholders
<b>1&hellip;N</b>; enter the real concentrations before fitting (a fit is
blocked until you do).</p>

<p><b>Channel:</b> enabled when a file holds multiple channels (e.g. EnSight
optical channels). Switch to plot and fit each one without re-importing; your
concentration vector carries over.</p>
"""


def _fmt_cell(value: float) -> str:
    """Format a float for the concentration table — short, scientific when needed."""
    if value == 0.0:
        return '0'
    if abs(value) < 1e-3 or abs(value) >= 1e4:
        return f'{value:.6g}'
    return f'{value:g}'


class DataPanel(InfoGroupBox):
    """Load measurement data and edit the concentration vector inline.

    Signals
    -------
    data_loaded(MeasurementSet)
        Emitted after data is loaded or after the user commits any edit
        to the concentration vector (cell change or unit change).
    data_cleared()
        Emitted when data is removed.
    display_unit_changed(str)
        Emitted when the plot's x-axis display unit is changed via the
        Display Unit combo. Carries the new unit string (one of ``UNITS``).
    """

    data_loaded = pyqtSignal(object)        # MeasurementSet
    data_cleared = pyqtSignal()
    display_unit_changed = pyqtSignal(str)

    def __init__(self, parent=None, *, initial_display_unit: str = DEFAULT_DISPLAY_UNIT):
        super().__init__(
            "Data",
            info_title="Loading measurement data",
            info_html=_build_data_help_html(),
            parent=parent,
        )
        self._ms: MeasurementSet | None = None
        self._source_path: str | None = None
        self._face_values: np.ndarray = np.array([], dtype=np.float64)
        self._imported_unit: str = DEFAULT_IMPORTED_UNIT
        self._suppress_cell_signal: bool = False
        # Multi-channel support: readers that emit a `channel` column (e.g.
        # EnSight) keep ALL channels in memory here so the user can switch
        # between them without re-importing the file.
        self._multi_channel_df = None
        self._channels: list[str] = []
        self._setup_ui(initial_display_unit)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self, initial_display_unit: str) -> None:
        layout = QVBoxLayout(self)

        self._file_label = QLabel("No file loaded")
        self._file_label.setWordWrap(True)
        self._info_label = QLabel("")
        layout.addWidget(self._file_label)
        layout.addWidget(self._info_label)

        # Units grid — Imported above Display, labels left-aligned.
        units_grid = QGridLayout()
        units_grid.setContentsMargins(0, 4, 0, 4)
        units_grid.setColumnStretch(1, 1)

        units_grid.addWidget(QLabel("Imported Unit:"), 0, 0)
        self._imported_unit_combo = QComboBox()
        self._imported_unit_combo.addItems(UNITS)
        self._imported_unit_combo.setCurrentText(DEFAULT_IMPORTED_UNIT)
        self._imported_unit_combo.currentTextChanged.connect(self._on_imported_unit_changed)
        units_grid.addWidget(self._imported_unit_combo, 0, 1)

        units_grid.addWidget(QLabel("Display Unit:"), 1, 0)
        self._display_unit_combo = QComboBox()
        self._display_unit_combo.addItems(UNITS)
        self._display_unit_combo.setCurrentText(initial_display_unit)
        self._display_unit_combo.currentTextChanged.connect(self.display_unit_changed.emit)
        units_grid.addWidget(self._display_unit_combo, 1, 1)

        # Channel selector — enabled only when the loaded file carries more
        # than one channel (keyed off the presence of a `channel` column, not
        # any single format). Switching rebuilds the MeasurementSet in-memory.
        units_grid.addWidget(QLabel("Channel:"), 2, 0)
        self._channel_combo = QComboBox()
        self._channel_combo.setEnabled(False)
        self._channel_combo.setToolTip(
            "Optical channel. Enabled when the imported file has multiple channels."
        )
        self._channel_combo.currentIndexChanged.connect(self._on_channel_changed)
        units_grid.addWidget(self._channel_combo, 2, 1)

        layout.addLayout(units_grid)

        # Concentration table — single editable column of face values.
        # Every successful cell commit rebuilds the MeasurementSet immediately;
        # there is no batched-apply state, so no widget can ever be staler
        # than what the user last typed.
        self._conc_table = QTableWidget(0, 1, self)
        self._conc_table.setHorizontalHeaderLabels(["Concentration"])
        self._conc_table.verticalHeader().setVisible(True)
        self._conc_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._conc_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self._conc_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.AnyKeyPressed
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self._conc_table.setMaximumHeight(220)
        self._conc_table.cellChanged.connect(self._on_cell_changed)
        layout.addWidget(self._conc_table)

        # Load / Save buttons.
        btn_row = QHBoxLayout()
        self._load_btn = QPushButton("Load…")
        self._load_btn.setToolTip("Load a saved concentration vector (.json)")
        self._load_btn.clicked.connect(self._on_load_concentrations)
        btn_row.addWidget(self._load_btn)

        self._save_btn = QPushButton("Save…")
        self._save_btn.setToolTip("Save the current concentration vector to a .json file")
        self._save_btn.clicked.connect(self._on_save_concentrations)
        btn_row.addWidget(self._save_btn)

        btn_row.addStretch(1)

        layout.addLayout(btn_row)

        self._set_concentration_controls_enabled(False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_file(self, path: str | None = None) -> None:
        """Load a measurement file, optionally bypassing the dialog.

        The import path is identical for every format: parse → build the
        MeasurementSet → emit. No modal dialog runs mid-load. When the
        parsed frame carries multiple channels, the full frame is kept in
        memory and the first channel is shown; the Channel combo lets the
        user switch without re-reading the file.
        """
        if path is None:
            path, _ = QFileDialog.getOpenFileName(
                self, "Load Measurement File", "", _build_file_filter()
            )
        if not path:
            return
        try:
            df = load_measurements(path)
        except Exception as exc:
            QMessageBox.warning(self, "Load Error", f"Could not load file:\n{exc}")
            return

        has_channels = ENSIGHT_CHANNEL_COLUMN in df.columns
        channels = list(df[ENSIGHT_CHANNEL_COLUMN].unique()) if has_channels else []
        try:
            df_used = self._slice_channel(df, channels[0]) if channels else df
            ms = self._make_ms(df_used, str(path))
        except Exception as exc:
            QMessageBox.warning(self, "Load Error", f"Could not load file:\n{exc}")
            return

        # Commit state only after a successful parse + build.
        self._multi_channel_df = df if has_channels else None
        self._channels = channels
        self._ms = ms
        self._source_path = path
        # Numbers in the file are taken as face values (no implicit unit
        # conversion). Default the Imported Unit to M, which matches the
        # historical loader behavior and preserves fits on existing files.
        self._face_values = np.asarray(ms.concentrations, dtype=np.float64).copy()
        self._imported_unit = DEFAULT_IMPORTED_UNIT
        self._populate_channel_combo(df)
        self._refresh_after_load()
        self.data_loaded.emit(ms)

    @staticmethod
    def _make_ms(df, source_file: str) -> MeasurementSet:
        """Build a MeasurementSet from a single-channel frame, forwarding the
        placeholder/metadata flags that downstream code keys off."""
        extra_metadata = {
            k: df.attrs[k]
            for k in (
                BMG_PLACEHOLDER_KEY,
                BMG_METADATA_KEY,
                ENSIGHT_METADATA_KEY,
                JASCO_METADATA_KEY,
            )
            if k in df.attrs
        }
        return MeasurementSet.from_dataframe(
            df, source_file=source_file, **extra_metadata
        )

    @staticmethod
    def _slice_channel(df, channel: str):
        """Return the single-channel sub-frame for *channel*, attrs preserved."""
        out = (
            df[df[ENSIGHT_CHANNEL_COLUMN] == channel]
            .drop(columns=ENSIGHT_CHANNEL_COLUMN)
            .reset_index(drop=True)
        )
        out.attrs.update(df.attrs)
        if isinstance(out.attrs.get(ENSIGHT_METADATA_KEY), dict):
            out.attrs[ENSIGHT_METADATA_KEY] = {
                **out.attrs[ENSIGHT_METADATA_KEY],
                "selected_channel": channel,
            }
        return out

    def _populate_channel_combo(self, df) -> None:
        """Fill the channel combo from the loaded frame; disable if ≤1 channel."""
        meta = df.attrs.get(ENSIGHT_METADATA_KEY, {}) if self._channels else {}
        self._channel_combo.blockSignals(True)
        self._channel_combo.clear()
        for ch in self._channels:
            self._channel_combo.addItem(format_channel_label(ch, meta), ch)
        self._channel_combo.setCurrentIndex(0 if self._channels else -1)
        self._channel_combo.blockSignals(False)
        self._channel_combo.setEnabled(len(self._channels) > 1)
        # Full label as tooltip so the channel name stays readable when the
        # combo elides it at narrow sidebar widths.
        self._channel_combo.setToolTip(
            self._channel_combo.currentText()
            if self._channels
            else "Optical channel. Enabled when the imported file has multiple channels."
        )

    def _on_channel_changed(self, _index: int) -> None:
        """Rebuild the MeasurementSet for the newly selected channel in-memory.

        The concentration vector is physically identical across channels
        (same plate columns), so a vector the user has already entered is
        carried over; everything channel-specific (signals, fit, outliers)
        resets via the downstream ``data_loaded`` handler.
        """
        if self._multi_channel_df is None or not self._channels:
            return
        channel = self._channel_combo.currentData()
        if channel is None:
            return
        # Has the user supplied real concentrations yet? Any edit drops the
        # placeholder flag, so its absence means "real values are in place".
        keep_entered = not (
            self._ms is not None and self._ms.metadata.get(BMG_PLACEHOLDER_KEY)
        )
        try:
            ms = self._make_ms(
                self._slice_channel(self._multi_channel_df, channel),
                self._source_path or "",
            )
        except Exception as exc:
            QMessageBox.warning(self, "Channel Error", f"Could not switch channel:\n{exc}")
            return

        reuse = keep_entered and self._face_values.size == ms.n_points
        self._ms = ms
        if not reuse:
            self._face_values = np.asarray(ms.concentrations, dtype=np.float64).copy()
        self._channel_combo.setToolTip(self._channel_combo.currentText())
        self._refresh_after_load()
        if reuse:
            # Re-apply the entered vector to the new channel (emits data_loaded).
            self._push_buffer_to_ms()
        else:
            self.data_loaded.emit(ms)

    def clear(self) -> None:
        self._ms = None
        self._source_path = None
        self._face_values = np.array([], dtype=np.float64)
        self._multi_channel_df = None
        self._channels = []
        self._channel_combo.blockSignals(True)
        self._channel_combo.clear()
        self._channel_combo.blockSignals(False)
        self._channel_combo.setEnabled(False)
        self._channel_combo.setToolTip(
            "Optical channel. Enabled when the imported file has multiple channels."
        )
        self._file_label.setText("No file loaded")
        self._info_label.setText("")
        self._populate_table()
        self._set_concentration_controls_enabled(False)
        self.data_cleared.emit()

    def current_path(self) -> str | None:
        return self._source_path

    def measurement_set(self) -> MeasurementSet | None:
        return self._ms

    def display_unit(self) -> str:
        return self._display_unit_combo.currentText()

    def set_display_unit(self, unit: str) -> None:
        """Set the Display Unit combo without re-emitting if unchanged."""
        if unit == self._display_unit_combo.currentText():
            return
        self._display_unit_combo.setCurrentText(unit)

    def focus_concentration_table(self) -> None:
        """Bring keyboard focus to the inline table.

        Public hook for the fit-time placeholder guard, which jumps the
        user to the table when a fit is blocked on placeholder data.
        """
        if self._ms is None:
            return
        self._conc_table.setFocus(Qt.FocusReason.OtherFocusReason)
        if self._conc_table.rowCount() > 0:
            self._conc_table.setCurrentCell(0, 0)
            self._conc_table.editItem(self._conc_table.item(0, 0))

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_imported_unit_changed(self, new_unit: str) -> None:
        if new_unit == self._imported_unit or self._ms is None:
            return
        # Reinterpret: same face values, new declared unit, new molar grid.
        self._imported_unit = new_unit
        self._push_buffer_to_ms()

    def _on_cell_changed(self, row: int, _col: int) -> None:
        if self._suppress_cell_signal:
            return
        item = self._conc_table.item(row, 0)
        if item is None:
            return
        text = item.text().strip()
        try:
            value = float(text)
        except ValueError:
            # Revert the cell to the last good value and warn.
            self._suppress_cell_signal = True
            try:
                item.setText(_fmt_cell(self._face_values[row]))
            finally:
                self._suppress_cell_signal = False
            QMessageBox.warning(
                self,
                "Invalid Number",
                f"'{text}' is not a valid number. Reverted to previous value.",
            )
            return
        if value == self._face_values[row]:
            return
        self._face_values[row] = value
        self._push_buffer_to_ms()

    def _push_buffer_to_ms(self) -> None:
        """Write the face-value buffer into the current MeasurementSet and announce it."""
        if self._ms is None or self._face_values.size == 0:
            return
        try:
            quantity = Q_(self._face_values.copy(), self._imported_unit)
            self._ms.set_concentrations(
                quantity, drop_metadata_keys=(BMG_PLACEHOLDER_KEY,)
            )
        except Exception as exc:
            QMessageBox.warning(self, "Error", f"Failed to apply concentrations:\n{exc}")
            return
        self._update_info()
        self.data_loaded.emit(self._ms)

    def _on_load_concentrations(self) -> None:
        if self._ms is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Concentration Vector",
            "",
            "Concentration JSON (*.json);;All files (*)",
        )
        if not path:
            return
        try:
            values, declared_unit = read_raw_concentrations(path)
        except Exception as exc:
            QMessageBox.warning(self, "Load Error", f"Could not load:\n{exc}")
            return
        if values.size != self._ms.n_points:
            QMessageBox.warning(
                self,
                "Mismatch",
                f"Loaded vector has {values.size} points but the dataset has "
                f"{self._ms.n_points}. They must match.",
            )
            return
        self._face_values = np.asarray(values, dtype=np.float64)
        if declared_unit and declared_unit in UNITS:
            self._imported_unit = declared_unit
            self._imported_unit_combo.blockSignals(True)
            self._imported_unit_combo.setCurrentText(declared_unit)
            self._imported_unit_combo.blockSignals(False)
        self._populate_table()
        self._push_buffer_to_ms()
        self._info_label.setText(
            f"{self._ms.n_points} points × {self._ms.n_replicas} replicas — "
            f"loaded from {Path(path).name}"
        )

    def _on_save_concentrations(self) -> None:
        if self._ms is None or self._face_values.size == 0:
            return
        suggested = ""
        if self._source_path:
            suggested = f"{Path(self._source_path).stem}_concentrations.json"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Concentration Vector",
            suggested,
            "Concentration JSON (*.json)",
        )
        if not path:
            return
        try:
            save_concentration_vector(
                self._face_values, path, unit=self._imported_unit
            )
        except Exception as exc:
            QMessageBox.warning(self, "Save Error", f"Could not save:\n{exc}")
            return
        self._info_label.setText(
            f"{self._ms.n_points} points × {self._ms.n_replicas} replicas — "
            f"saved to {Path(path).name}"
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _refresh_after_load(self) -> None:
        self._imported_unit_combo.blockSignals(True)
        self._imported_unit_combo.setCurrentText(self._imported_unit)
        self._imported_unit_combo.blockSignals(False)
        self._populate_table()
        self._update_info()
        self._set_concentration_controls_enabled(True)

    def _populate_table(self) -> None:
        self._suppress_cell_signal = True
        try:
            self._conc_table.setRowCount(self._face_values.size)
            for i, v in enumerate(self._face_values):
                item = QTableWidgetItem(_fmt_cell(float(v)))
                self._conc_table.setItem(i, 0, item)
        finally:
            self._suppress_cell_signal = False

    def _update_info(self) -> None:
        if self._ms is None:
            return
        name = Path(self._source_path).name if self._source_path else "?"
        self._file_label.setText(name)
        self._info_label.setText(
            f"{self._ms.n_points} points × {self._ms.n_replicas} replicas"
        )

    def _set_concentration_controls_enabled(self, enabled: bool) -> None:
        self._imported_unit_combo.setEnabled(enabled)
        self._conc_table.setEnabled(enabled)
        self._load_btn.setEnabled(enabled)
        self._save_btn.setEnabled(enabled)
