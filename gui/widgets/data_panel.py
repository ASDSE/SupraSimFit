"""DataPanel — file loading and concentration vector management."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from core.data_processing.measurement_set import MeasurementSet
from core.io import load_measurements
from core.io.formats.bmg_reader import BMG_METADATA_KEY, BMG_PLACEHOLDER_KEY
from core.io.registry import READERS
from gui.widgets.info_button import InfoGroupBox


def _build_file_filter() -> str:
    """Build QFileDialog filter string from registered I/O readers."""
    parts = []
    for ext, cls in sorted(READERS.items()):
        parts.append(f"*{ext}")
    all_exts = " ".join(parts)
    return f"Measurement files ({all_exts});;All files (*)"


def _build_data_help_html() -> str:
    """Build the Data panel help dialog HTML, listing supported formats dynamically."""
    exts = sorted(READERS.keys())
    ext_list = ", ".join(f"<code>{e}</code>" for e in exts) or "(none registered)"
    tab = "&#9;"
    return f"""
<h3>Loading Measurement Data</h3>

<p><b>What This Section Is For</b></p>
<p>Where the fitting session gets its raw numbers. Everything below
(outlier removal, replica selection, bounds, fit configuration, plot
style) operates on the measurements you load here.</p>

<p><b>Supported File Formats</b></p>
<p>Reader selection is automatic from the file extension. Currently
registered: {ext_list}.</p>

<p><b>TXT &mdash; Tab-Separated, Multi-Replica</b></p>
<p>The default format. One header row followed by tab-separated rows of
<i>concentration</i> and <i>signal</i>. The parser detects a header row
whenever its first cell is non-numeric &mdash; typical values are
<code>var</code>, <code>concentration</code>, <code>conc</code>, or
<code>x</code>. Additional replicas are appended as new blocks, each
starting with another header row:</p>
<pre style="background:#f3f3f3; padding:6px;">
var{tab}signal
0.0{tab}506.246
2.985e-05{tab}1064.85
&hellip;
var{tab}signal
0.0{tab}503.103
2.985e-05{tab}1058.21
&hellip;
</pre>
<p>Blank lines and lines starting with <code>#</code> are ignored.
Concentrations are parsed as floats in molar; if yours aren&rsquo;t in
M, fix them afterwards via the <b>Concentration Vector</b> dialog
(which lets you enter values in nM / &micro;M / mM / M and converts to
molar internally).</p>

<p><b>CSV &mdash; Long or Wide</b></p>
<p>CSV files work in two shapes. <i>Long</i> format uses three named
columns (<code>concentration</code>, <code>signal</code>, and
optionally <code>replica</code>). <i>Wide</i> format puts concentration
in the first column and one replica per remaining column. Column names
are matched case-insensitively and several aliases are accepted:
<code>concentration</code> / <code>conc</code> / <code>x</code> /
<code>[conc]</code> / <code>titrant</code> for the x column, and
<code>signal</code> / <code>y</code> / <code>fluorescence</code> /
<code>intensity</code> / <code>emission</code> for the y column.
Repeated-header CSVs (the same shape as TXT) are also accepted.</p>

<p><b>Excel &mdash; <code>.xlsx</code> / <code>.xls</code></b></p>
<p>Two shapes are auto-detected:</p>
<ul>
  <li><b>Structured workbooks</b> follow the same long / wide rules as
      CSV (multi-sheet = one sheet per replica).</li>
  <li><b>BMG plate-reader exports</b> are recognised from the
      <i>Microplate End point</i> sheet and the 8&times;12 (or
      16&times;24) plate grid. Each plate <b>row</b> becomes one
      replica, each plate <b>column</b> becomes one concentration
      point. BMG files do not carry concentration values &mdash; the
      reader assigns placeholder positions <b>1&hellip;N</b> and a
      dialog opens so you can enter (or load) the real vector. The
      fit refuses to run until you do.</li>
</ul>

<p><b>How to Feed In Data</b></p>
<ul>
  <li><b>Import &rarr; Import Data&hellip;</b> (<code>Ctrl+O</code>)
      &mdash; pick any supported file.</li>
  <li><b>Demo IDA</b> toolbar button &mdash; loads a bundled example so
      you can try the fitter without your own data.</li>
  <li><b>Import &rarr; Import Fit Results&hellip;</b> &mdash; reload a
      previously exported <code>.json</code> fit, optionally without
      the raw data.</li>
</ul>

<p><b>Saving What You Loaded</b></p>
<p>Use <b>Export &rarr; Export Raw Data&hellip;</b> to write the current
replicas + concentrations back out as TXT or CSV &mdash; handy for
converting a BMG plate into a re-loadable flat file once real
concentrations are in place.</p>
"""


class DataPanel(InfoGroupBox):
    """Load measurement data files and manage concentration vectors.

    Signals
    -------
    data_loaded(MeasurementSet)
        Emitted after a file is successfully loaded and parsed.
    data_cleared()
        Emitted when data is removed.
    """

    data_loaded = pyqtSignal(object)   # MeasurementSet
    data_cleared = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(
            "Data",
            info_title="Loading measurement data",
            info_html=_build_data_help_html(),
            parent=parent,
        )
        self._ms: MeasurementSet | None = None
        self._source_path: str | None = None
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Info labels
        self._file_label = QLabel("No file loaded")
        self._file_label.setWordWrap(True)
        self._info_label = QLabel("")
        layout.addWidget(self._file_label)
        layout.addWidget(self._info_label)

        # Concentration vector button (enabled after data is loaded).
        # Wrap in an HBox with a trailing stretch so the button hugs its text
        # instead of stretching to the full panel width.
        self._conc_btn = QPushButton("Concentration Vector")
        self._conc_btn.setEnabled(False)
        self._conc_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._conc_btn.clicked.connect(self.open_concentration_dialog)
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.addWidget(self._conc_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_file(self, path: str | None = None) -> None:
        """Load a measurement file, optionally bypassing the dialog."""
        if path is None:
            path, _ = QFileDialog.getOpenFileName(
                self, "Load Measurement File", "", _build_file_filter()
            )
        if not path:
            return
        try:
            df = load_measurements(path)
            # Forward reader-level flags (e.g. BMG placeholder concentrations)
            # onto the MeasurementSet so downstream widgets can react to them.
            extra_metadata: dict = {
                k: df.attrs[k]
                for k in (BMG_PLACEHOLDER_KEY, BMG_METADATA_KEY)
                if k in df.attrs
            }
            ms = MeasurementSet.from_dataframe(
                df, source_file=str(path), **extra_metadata
            )
            self._ms = ms
            self._source_path = path
            self._update_info()
            self._conc_btn.setEnabled(True)
            self.data_loaded.emit(ms)
        except Exception as exc:
            QMessageBox.warning(self, "Load Error", f"Could not load file:\n{exc}")

    def clear(self) -> None:
        self._ms = None
        self._source_path = None
        self._file_label.setText("No file loaded")
        self._info_label.setText("")
        self._conc_btn.setEnabled(False)
        self.data_cleared.emit()

    def current_path(self) -> str | None:
        return self._source_path

    def measurement_set(self) -> MeasurementSet | None:
        return self._ms

    def open_concentration_dialog(self) -> None:
        """Open the concentration-vector editor for the current MeasurementSet.

        Public entry point used by the Concentration Vector button and by
        :class:`~gui.fitting_session.FittingSession` (both the BMG import
        prompt and the fit-time guard). A no-op when no data is loaded.
        """
        if self._ms is None:
            return
        from gui.dialogs.concentration_dialog import ConcentrationDialog

        dlg = ConcentrationDialog(self._ms.concentrations, parent=self)
        if dlg.exec():
            new_conc = dlg.result_concentrations()
            if new_conc is not None:
                self._rebuild_ms_with_concentrations(new_conc)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _update_info(self) -> None:
        if self._ms is None:
            return
        name = Path(self._source_path).name if self._source_path else "?"
        self._file_label.setText(name)
        self._info_label.setText(
            f"{self._ms.n_points} points × {self._ms.n_replicas} replicas"
        )

    def _rebuild_ms_with_concentrations(self, new_conc) -> None:
        """Rebuild MeasurementSet with a new concentration vector."""
        ms = self._ms
        if len(new_conc) != ms.n_points:
            QMessageBox.warning(
                self,
                "Mismatch",
                f"Concentration vector has {len(new_conc)} points but data has "
                f"{ms.n_points}. They must match.",
            )
            return
        try:
            rows = []
            for i, (rid, sig) in enumerate(ms.iter_replicas(active_only=False)):
                for j, (c, s) in enumerate(zip(new_conc, sig)):
                    rows.append({"concentration": c, "signal": float(s), "replica": i})
            df = pd.DataFrame(rows)
            # Drop the BMG placeholder flag — once real concentrations are in,
            # the dataset is ready to fit. Everything else carries over.
            carry = {k: v for k, v in ms.metadata.items() if k != BMG_PLACEHOLDER_KEY}
            new_ms = MeasurementSet.from_dataframe(
                df, source_file=self._source_path, **carry
            )
            self._ms = new_ms
            self._update_info()
            self.data_loaded.emit(new_ms)
        except Exception as exc:
            QMessageBox.warning(self, "Error", f"Failed to apply concentration vector:\n{exc}")
