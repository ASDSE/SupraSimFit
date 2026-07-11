"""SimulationWindow — the non-modal forward-simulation applet.

Left: a two-level assay selector + the registry-driven control stack.  Right: a
live :class:`PlotWidget`.  Every control change re-evaluates the forward model at
the user's concentration vector and redraws — no fitting.  The window is opened
non-modally so the main fitting window stays usable alongside it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.simulation import build_concentration_vector, simulate_dataset, simulate_signal, simulate_species
from gui.plotting.plot_widget import PlotWidget
from gui.simulation.settings_io import load_simulation_settings, save_simulation_settings
from gui.simulation.simulation_panel import SimulationPanel
from gui.simulation.species_plot import SpeciesPlotWidget
from gui.widgets.assay_type_selector import AssayTypeSelector

_INITIAL_ASSAY = AssayType.IDA


class SimulationWindow(QMainWindow):
    """Interactive forward-simulation applet (non-modal)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Simulate Titration — SupraSimFit')
        self.resize(1100, 720)

        # (concentrations_M, [(replica_id, signal), ...]) of imported data to overlay.
        self._imported: tuple[np.ndarray, list[tuple[str, np.ndarray]]] | None = None

        self._build_toolbar()

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        self.setCentralWidget(splitter)

        # Left: selector + control stack, scrollable.
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(8, 8, 8, 8)
        self._selector = AssayTypeSelector(initial=_INITIAL_ASSAY)
        self._panel = SimulationPanel(assay_type=_INITIAL_ASSAY)
        left_layout.addWidget(self._selector)
        left_layout.addWidget(self._panel)
        left_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(left)
        scroll.setMinimumWidth(360)
        splitter.addWidget(scroll)

        # Right: the signal plot with the speciation plot stacked below it, sharing
        # the titrant x-axis so the hover crosshair tracks the same point on both.
        self._plot = PlotWidget()
        self._species_plot = SpeciesPlotWidget()
        right = QSplitter(Qt.Orientation.Vertical)
        right.setChildrenCollapsible(False)
        right.addWidget(self._plot)
        right.addWidget(self._species_plot)
        right.setStretchFactor(0, 3)
        right.setStretchFactor(1, 2)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        self._species_plot.link_x(self._plot.plot_item)

        self.setStatusBar(QStatusBar())

        self._selector.assay_type_changed.connect(self._on_assay_changed)
        self._panel.changed.connect(self._recompute)

        self._recompute()

    # -- toolbar -------------------------------------------------------------

    def _build_toolbar(self) -> None:
        tb = QToolBar('Simulation')
        tb.setMovable(False)
        self.addToolBar(tb)
        for text, slot, tip in (
            ('Export Curve…', self._on_export_curve, 'Save the plotted curve as PNG or SVG'),
            ('Export Data…', self._on_export_data, 'Save the simulated points as a loadable TXT/CSV'),
            ('Save Settings…', self._on_save_settings, 'Save all parameters/bounds/noise to JSON'),
            ('Load Settings…', self._on_load_settings, 'Restore parameters/bounds/noise from JSON'),
            ('Import Data…', self._on_import_data, 'Overlay a measurement file on the simulated curve'),
        ):
            act = QAction(text, self)
            act.setToolTip(tip)
            act.triggered.connect(slot)
            tb.addAction(act)

    # -- slots ---------------------------------------------------------------

    def _on_assay_changed(self, assay_type: AssayType) -> None:
        self._imported = None  # imported overlay no longer applies to a different assay
        self._panel.set_assay_type(assay_type)  # emits changed → _recompute

    def _recompute(self) -> None:
        """Re-evaluate the forward model and redraw.  Errors surface in the status bar."""
        try:
            spec = self._panel.spec()
            x = build_concentration_vector(spec.conc_mode, **spec.conc_kwargs)
            y = simulate_signal(spec.assay_cls, spec.conditions, spec.parameters, x)
        except Exception as exc:  # invalid range / non-physical params / solver failure
            self.statusBar().showMessage(f'⚠ {exc}')
            return

        scatter: list[tuple[str, np.ndarray]] = []
        noise = spec.noise
        if noise['enabled'] and noise['frac'] > 0:
            ms = simulate_dataset(
                spec.assay_cls,
                spec.conditions,
                spec.parameters,
                x,
                noise_frac=noise['frac'],
                n_replicas=noise['replicas'],
                rng=np.random.default_rng(noise['seed']),
            )
            scatter.extend(zip(ms.replica_ids, list(ms.signals)))

        if self._imported is not None:
            xi, reps = self._imported
            if len(xi) == len(x):
                scatter.extend(reps)
            else:
                self.statusBar().showMessage('Imported overlay hidden — concentration grid changed.')

        meta = ASSAY_REGISTRY[spec.assay_type]
        plot_data = {
            'concentrations': x,
            'active_replicas': scatter,
            'dropped_replicas': [],
            'average': None,
            'fits': [{'x': x, 'y': y, 'label': 'Simulated model', 'id': 'sim'}],
        }
        self._plot.update_plot(plot_data, x_label=meta.x_label, y_label=meta.y_label, y_unit=meta.y_unit)
        self._update_species(spec, x)
        self.statusBar().showMessage(f'{meta.display_name} — {len(x)} points')

    def _update_species(self, spec, x: np.ndarray) -> None:
        """Redraw the speciation plot, or show a note where there is no equilibrium.

        Only reached after the signal computed successfully, so the conditions are
        already validated; the species solve then returns NaN (never raises) for any
        non-physical parameters, and the plot gaps those points.  Deliberately no broad
        ``except`` here — that would only mask a genuine bug as a parameter note.
        """
        if spec.assay_type == AssayType.DYE_ALONE:
            self._species_plot.show_empty(
                'No speciation for a dye-alone calibration — the signal is a linear function of dye concentration.'
            )
            return
        meta = ASSAY_REGISTRY[spec.assay_type]
        species = simulate_species(spec.assay_cls, spec.conditions, spec.parameters, x)
        self._species_plot.update_species(x, species, meta.x_label, self._plot.x_unit)

    def _on_export_curve(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, 'Export Curve', self._default_name('.png'), 'PNG image (*.png);;SVG vector (*.svg)'
        )
        if not path:
            return
        try:
            self._plot.export_image(path)
            self.statusBar().showMessage(f'Curve saved to {path}')
        except Exception as exc:
            QMessageBox.warning(self, 'Export Error', str(exc))

    def _on_export_data(self) -> None:
        try:
            spec = self._panel.spec()
            x = build_concentration_vector(spec.conc_mode, **spec.conc_kwargs)
        except Exception as exc:
            QMessageBox.warning(self, 'Cannot Export', str(exc))
            return
        path, _ = QFileDialog.getSaveFileName(
            self, 'Export Simulated Data', self._default_name('.txt'), 'Text file (*.txt);;CSV file (*.csv)'
        )
        if not path:
            return
        noise = spec.noise
        replicas = noise['replicas'] if noise['enabled'] else 1
        ms = simulate_dataset(
            spec.assay_cls,
            spec.conditions,
            spec.parameters,
            x,
            noise_frac=noise['frac'] if noise['enabled'] else 0.0,
            n_replicas=replicas,
            rng=np.random.default_rng(noise['seed']),
        )
        try:
            if Path(path).suffix.lower() == '.csv':
                from core.io.formats.measurement_writer import write_measurements_csv

                write_measurements_csv(ms, path)
            else:
                from core.io.formats.measurement_writer import write_measurements_txt

                if Path(path).suffix.lower() != '.txt':
                    path = str(Path(path).with_suffix('.txt'))
                write_measurements_txt(ms, path)
        except Exception as exc:
            QMessageBox.warning(self, 'Export Error', str(exc))
            return
        self.statusBar().showMessage(f'Simulated data exported to {path}')

    def _on_save_settings(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, 'Save Settings', self._default_name('.json'), 'JSON (*.json)')
        if not path:
            return
        try:
            save_simulation_settings(self._panel.state(), path)
            self.statusBar().showMessage(f'Settings saved to {path}')
        except Exception as exc:
            QMessageBox.warning(self, 'Save Error', str(exc))

    def _on_load_settings(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, 'Load Settings', '', 'JSON (*.json);;All files (*)')
        if not path:
            return
        try:
            state = load_simulation_settings(path)
            self._selector.set_assay_type(AssayType[state['assay_type']])
            self._panel.load_state(state)
            self.statusBar().showMessage(f'Settings loaded from {path}')
        except Exception as exc:
            QMessageBox.warning(self, 'Load Error', str(exc))

    def _on_import_data(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, 'Import Measurement Data', '', 'Data files (*.txt *.csv *.xlsx);;All files (*)'
        )
        if not path:
            return
        try:
            from core.data_processing.measurement_set import MeasurementSet
            from core.io import load_measurements

            ms = MeasurementSet.from_dataframe(load_measurements(path))
        except Exception as exc:
            QMessageBox.warning(self, 'Import Error', f'Could not load data:\n{exc}')
            return
        self._imported = (
            np.asarray(ms.concentrations, dtype=float),
            [(f'data:{rid}', np.asarray(sig, dtype=float)) for rid, sig in zip(ms.replica_ids, ms.signals)],
        )
        # Evaluate the model at the imported grid so the comparison lines up.
        self._panel.set_concentration_explicit(ms.concentrations)
        self.statusBar().showMessage(f'Imported {ms.n_replicas} replica(s) from {Path(path).name}')

    # -- helpers -------------------------------------------------------------

    def _default_name(self, suffix: str) -> str:
        return f'simulation_{self._panel.assay_type().name}{suffix}'
