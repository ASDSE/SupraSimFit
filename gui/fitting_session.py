"""FittingSession — one complete fitting workspace (one tab)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.assays.registry import ASSAY_REGISTRY, AssayType

_DEMO_IDA_PATH = Path(__file__).parent.parent / "data" / "IDA_system.txt"
from core.data_processing.measurement_set import MeasurementSet
from core.data_processing.plotting import prepare_plot_data
from core.pipeline.fit_pipeline import FitConfig, FitResult
from gui.app_state import SessionState
from gui.plotting.fit_summary_widget import FitSummaryWidget
from gui.plotting.plot_style import PlotStyleWidget
from gui.plotting.plot_widget import PlotWidget
from gui.widgets.assay_config_panel import AssayConfigPanel
from gui.widgets.bounds_panel import BoundsPanel
from gui.widgets.data_panel import DataPanel
from gui.widgets.fit_config_panel import FitConfigPanel
from gui.widgets.preprocessing_panel import PreprocessingPanel
from gui.widgets.replica_panel import ReplicaPanel
from gui.workers import FitWorker


class FittingSession(QWidget):
    """One complete fitting workflow: data → preprocess → configure → fit → visualize.

    Each tab in the main window is one FittingSession.  All state is stored in
    :class:`SessionState`; widgets communicate via Qt signals coordinated here.

    Signals
    -------
    title_changed(str)
        Emitted when the tab title should change (e.g. after assay type switch).
    status_message(str)
        Emitted to update the main window's status bar.
    """

    title_changed = pyqtSignal(str)
    status_message = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = SessionState()
        self._fit_worker: FitWorker | None = None
        self._setup_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # Public API (called by FittingMainWindow)
    # ------------------------------------------------------------------

    def run_fit(self) -> None:
        """Start a background fitting run."""
        ms = self._state.measurement_set
        if ms is None:
            QMessageBox.warning(self, "No Data", "Load a measurement file first.")
            return

        assay_cls = self._assay_panel.get_assay_class()
        conditions = self._assay_panel.current_conditions()
        config = self._fit_panel.current_config()
        custom_bounds = self._bounds_panel.current_bounds()
        if custom_bounds:
            config = FitConfig(
                n_trials=config.n_trials,
                rmse_threshold_factor=config.rmse_threshold_factor,
                min_r_squared=config.min_r_squared,
                custom_bounds=custom_bounds,
            )

        self._fit_worker = FitWorker(
            ms,
            assay_cls,
            conditions,
            config,
            source_file=self._state.source_file,
            parent=self,
        )
        self._fit_worker.finished.connect(self._on_fit_complete)
        self._fit_worker.error.connect(self._on_fit_error)
        self._fit_worker.start()
        self.status_message.emit("Fitting…")

    def load_demo_ida(self) -> None:
        """Load the bundled IDA demo dataset and run a fit with default settings."""
        if not _DEMO_IDA_PATH.exists():
            QMessageBox.warning(self, "Demo Data Missing", f"Could not find:\n{_DEMO_IDA_PATH}")
            return
        self._assay_panel.set_assay_type(AssayType.IDA)
        self._data_panel.load_file(str(_DEMO_IDA_PATH))
        self.run_fit()

    def export_results(self) -> None:
        """Export current fit results to JSON."""
        if not self._state.fit_results:
            QMessageBox.information(self, "No Results", "Run a fit first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Fit Results", "results.json", "JSON (*.json)"
        )
        if not path:
            return
        from gui.session import export_results
        export_results(self._state.fit_results, path)
        self.status_message.emit(f"Results exported to {path}")

    def import_results(self) -> None:
        """Import fit results from JSON and replot."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Fit Results", "", "JSON (*.json);;All files (*)"
        )
        if not path:
            return
        try:
            from gui.session import import_results
            results = import_results(path)
            if self._state.measurement_set is not None:
                # Raw data already loaded — overlay imported fits immediately
                self._state.fit_results = results
                self._refresh_plot()
            elif results:
                # No raw data loaded — try to auto-load from source_file stored in result
                source_file = results[-1].source_file
                if source_file and Path(source_file).exists():
                    # load_file triggers _on_data_loaded which clears fit_results.
                    # Do NOT assign self._state.fit_results before load_file, or the
                    # in-place .clear() inside _on_data_loaded will wipe `results` too
                    # (same list object). Assign only after load_file returns.
                    self._data_panel.load_file(source_file)
                    self._state.fit_results = results
                    self._refresh_plot()
                else:
                    # Source file not available — show fit curves only
                    self._state.fit_results = results
                    meta = ASSAY_REGISTRY[self._state.assay_type]
                    last = results[-1]
                    plot_data = {
                        'concentrations': last.x_fit,
                        'active_replicas': [],
                        'dropped_replicas': [],
                        'average': None,
                        'fits': [
                            {'x': r.x_fit, 'y': r.y_fit, 'label': 'Best Fit', 'id': r.id}
                            for r in results
                        ],
                    }
                    self._plot_widget.update_plot(
                        plot_data, x_label=meta.x_label, y_label=meta.y_label
                    )
                    self._plot_widget.set_fit_results(results)
            if results:
                self._summary_widget.update_result(results[-1])
            self.status_message.emit(f"Imported {len(results)} result(s) from {path}")
        except Exception as exc:
            QMessageBox.warning(self, "Import Error", str(exc))

    def export_plot(self) -> None:
        """Save the current plot as PNG or SVG."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Plot",
            "plot.png",
            "PNG image (*.png);;SVG vector (*.svg)",
        )
        if not path:
            return
        try:
            self._plot_widget.export_image(path)
            self.status_message.emit(f"Plot saved to {path}")
        except Exception as exc:
            QMessageBox.warning(self, "Export Error", str(exc))

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        outer.addWidget(splitter)

        # ---- Left panel (scrollable) --------------------------------
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(300)
        left_scroll.setMaximumWidth(380)

        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setSpacing(6)
        left_layout.setContentsMargins(6, 6, 6, 6)

        self._data_panel = DataPanel()
        self._preprocess_panel = PreprocessingPanel()
        self._replica_panel = ReplicaPanel()
        self._assay_panel = AssayConfigPanel()
        self._fit_panel = FitConfigPanel()
        self._bounds_panel = BoundsPanel()
        self._style_widget = _Grouped("Plot Style", PlotStyleWidget())

        for widget in (
            self._data_panel,
            self._preprocess_panel,
            self._replica_panel,
            self._assay_panel,
            self._fit_panel,
            self._bounds_panel,
            self._style_widget,
        ):
            left_layout.addWidget(widget)

        left_layout.addStretch()
        left_scroll.setWidget(left_container)
        splitter.addWidget(left_scroll)

        # ---- Right panel (plot + summary) ---------------------------
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self._plot_widget = PlotWidget()
        self._summary_widget = FitSummaryWidget()

        right_layout.addWidget(self._plot_widget, stretch=3)
        right_layout.addWidget(self._summary_widget, stretch=1)
        splitter.addWidget(right_widget)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        # Initialise BoundsPanel for default assay type
        self._bounds_panel.set_assay_type(self._state.assay_type)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._data_panel.data_loaded.connect(self._on_data_loaded)
        self._data_panel.data_cleared.connect(self._on_data_cleared)

        self._preprocess_panel.preprocessing_applied.connect(self._on_preprocessing_applied)
        self._preprocess_panel.preprocessing_reset.connect(self._on_preprocessing_reset)

        self._replica_panel.replicas_changed.connect(self._on_replicas_changed)

        self._assay_panel.assay_type_changed.connect(self._on_assay_type_changed)
        self._assay_panel.conditions_changed.connect(self._on_conditions_changed)

        self._fit_panel.config_changed.connect(self._on_config_changed)

        self._bounds_panel.bounds_changed.connect(self._on_bounds_changed)

        # Direct widget-to-widget: style → plot
        self._style_widget.widget.style_changed.connect(self._plot_widget.apply_style)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_data_loaded(self, ms: MeasurementSet) -> None:
        self._state.measurement_set = ms
        self._state.source_file = self._data_panel.current_path()
        self._state.fit_results.clear()
        self._preprocess_panel.set_measurement_set(ms)
        self._replica_panel.set_measurement_set(ms)
        self._summary_widget.clear()
        self._refresh_plot()
        active = ms.n_active
        total = ms.n_replicas
        self.status_message.emit(
            f"Loaded: {ms.n_points} pts × {total} replicas — {active}/{total} active"
        )

    def _on_data_cleared(self) -> None:
        self._state.measurement_set = None
        self._state.source_file = None
        self._state.fit_results.clear()
        self._replica_panel.clear()
        self._summary_widget.clear()

    def _on_preprocessing_applied(self) -> None:
        self._replica_panel.refresh()
        self._refresh_plot()
        ms = self._state.measurement_set
        if ms:
            self.status_message.emit(
                f"Preprocessing applied — {ms.n_active}/{ms.n_replicas} replicas active"
            )

    def _on_preprocessing_reset(self) -> None:
        self._replica_panel.refresh()
        self._refresh_plot()
        self.status_message.emit("Replicas reset — all active")

    def _on_replicas_changed(self) -> None:
        self._refresh_plot()

    def _on_assay_type_changed(self, assay_type: AssayType) -> None:
        self._state.assay_type = assay_type
        self._bounds_panel.set_assay_type(assay_type)
        meta = ASSAY_REGISTRY[assay_type]
        self._update_axis_labels(meta.x_label, meta.y_label)
        self.title_changed.emit(meta.display_name)

    def _on_conditions_changed(self) -> None:
        self._state.conditions = self._assay_panel.current_conditions()

    def _on_config_changed(self) -> None:
        self._state.fit_config = self._fit_panel.current_config()

    def _on_bounds_changed(self) -> None:
        self._state.custom_bounds = self._bounds_panel.current_bounds()

    def _on_fit_complete(self, result: FitResult) -> None:
        self._state.fit_results = [result]
        self._refresh_plot()
        self._summary_widget.update_result(result)
        self._plot_widget.set_fit_results(self._state.fit_results)
        self.status_message.emit(
            f"Fit complete — R²={result.r_squared:.4f}, RMSE={result.rmse:.4e}, "
            f"{result.n_passing}/{result.n_total} trials passed"
        )

    def _on_fit_error(self, msg: str) -> None:
        QMessageBox.warning(self, "Fit Error", msg)
        self.status_message.emit(f"Fit failed: {msg}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _refresh_plot(self) -> None:
        ms = self._state.measurement_set
        if ms is None:
            return
        meta = ASSAY_REGISTRY[self._state.assay_type]
        plot_data = prepare_plot_data(ms, self._state.fit_results, show_dropped=True)
        self._plot_widget.update_plot(
            plot_data,
            x_label=meta.x_label,
            y_label=meta.y_label,
        )
        self._plot_widget.set_fit_results(self._state.fit_results)

    def _update_axis_labels(self, x: str, y: str) -> None:
        self._plot_widget.set_axis_labels(x, y)


class _Grouped(QGroupBox):
    """Thin wrapper that places an existing widget inside a QGroupBox."""

    def __init__(self, title: str, widget: QWidget, parent=None):
        super().__init__(title, parent)
        self.widget = widget
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(widget)
