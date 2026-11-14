"""FittingSession — the view of one session: its views, each a canvas and a side panel, over a SessionModel."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QWidget,
)

from core.assays.registry import AssayType
from core.pipeline.inputs import TITRANT, InputSpec
from gui import plot_guide
from gui.design import components as C
from gui.design.appearance import theme
from gui.design.tokens import SIZE
from gui.dialogs.plot_guide_dialog import show_plot_guide
from gui.plotting.export import ExportRefused
from gui.plotting.labels import and_join, stated_uncertainty
from gui.session_model import CONCENTRATIONS_REQUIRED, SessionModel
from gui.views.binding import BindingView
from gui.views.confidence import ConfidenceView
from gui.views.fit_results import FitResultsView
from gui.views.measurements import MeasurementsView
from gui.views.plot_appearance import PlotAppearanceView
from gui.views.sensitivity import SensitivityView
from gui.views.uncertainty import UncertaintyView

#: A session's views as the sidebar groups them: (group, ((view, icon), …)).
NAVIGATION = (
    ('Experiment', (('Measurements', 'table'), ('Binding model', 'flask'), ('Input uncertainty', 'sliders'))),
    ('Analysis', (('Fit results', 'fit'), ('Ka confidence', 'profile'), ('Sensitivity', 'bars'))),
    ('Presentation', (('Plot appearance', 'palette'),)),
)
VIEWS = tuple(view for _group, items in NAVIGATION for view, _icon in items)

#: The section of *Reading the plots* each view with a plot opens at.
_GUIDE_SECTIONS = {
    'Fit results': plot_guide.FIT_CURVE,
    'Ka confidence': plot_guide.CONFIDENCE,
    'Sensitivity': plot_guide.SENSITIVITY,
    'Plot appearance': plot_guide.FIT_CURVE,
}

_DEMO_IDA_PATH = Path(__file__).parent.parent / 'data' / 'IDA_system.txt'

#: The input uncertainties Demo IDA states: a literature Ka,dye known to about 10 %, and
#: stock concentrations pipetted to about 3 %. Typical figures, so that the demo's first fit
#: reports the interval that covers them.
_DEMO_UNCERTAINTIES = {
    'Ka_dye': InputSpec.sigma_pct(10.0),
    'h0': InputSpec.sigma_pct(3.0),
    'd0': InputSpec.sigma_pct(3.0),
    TITRANT: InputSpec.sigma_pct(3.0),
}


class _SidePanel(QWidget):
    """A view's side panel: its name, an optional *link* and a close button over a scrolled body of *content*."""

    close_requested = pyqtSignal()

    def __init__(self, title: str, content: QWidget, link: QWidget | None = None):
        super().__init__()
        t = theme()
        self.setObjectName('Inspector')
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setMinimumWidth(SIZE['inspector-min'])
        close = C.tool_button(t, None, 'x')
        close.setToolTip('Close the side panel')
        close.setAccessibleName(f'Close {title}')
        close.clicked.connect(self.close_requested)
        header = QWidget()
        header.setFixedHeight(SIZE['toolbar'])
        links = [link, 2] if link is not None else []
        header.setLayout(C.hbox(C.label(title, 'body-strong'), None, *links, close, margins=(5, 0, 3, 0)))
        body = QWidget()
        body.setObjectName('InspectorBody')
        body.setLayout(C.vbox(content, None, spacing=0, margins=(5, 0, 5, 5)))
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        # The panel never scrolls sideways: every section fits its least width beside the
        # vertical scroll bar.
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidget(body)
        self.setLayout(C.vbox(header, self.scroll, spacing=0))


class _View(QSplitter):
    """One view of a session: its canvas, and its side panel when it has one."""

    def __init__(self, canvas: QWidget, side: _SidePanel | None = None):
        super().__init__(Qt.Orientation.Horizontal)
        self.side = side
        self.setHandleWidth(1)
        self.setChildrenCollapsible(False)
        self.addWidget(canvas)
        if side is not None:
            self.addWidget(side)
            self.setStretchFactor(0, 1)
            self.setStretchFactor(1, 0)
            self.setSizes([10_000, SIZE['inspector']])


class FittingSession(QWidget):
    """One session on screen: data → binding model → inputs → fit → analyses, one view at a time.

    Each session of the main window is one FittingSession. Its state and rules
    live in :attr:`model`, a :class:`~gui.session_model.SessionModel`: each
    view edits the model's state, draws what the model's signals say changed,
    and keeps the parts that need a screen — file dialogs, message boxes and
    plot images. Its views are the sidebar's (:data:`NAVIGATION`);
    :meth:`show_view` puts one on screen, under the progress line the session
    shows while it runs.

    Signals
    -------
    changed()
        Emitted whenever what the window shows of this session may have
        changed — a run started, advanced or ended, results were shown or
        hidden, data or settings changed, or the session was renamed.
    side_panel_closed()
        Emitted when the side panel's close button is pressed.
    side_panel_requested()
        Emitted when the session needs the side panel shown, such as Fit details for
        *All results and diagnostics →*.
    view_requested(str)
        Emitted when the session needs one of its views on screen, such as
        Measurements for concentrations a fit needs.
    new_session_requested()
        Emitted by *Load data into a new session…* inside a view.
    """

    changed = pyqtSignal()
    side_panel_closed = pyqtSignal()
    side_panel_requested = pyqtSignal()
    view_requested = pyqtSignal(str)
    new_session_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = SessionModel(self)
        self._assay_shown = None  # the model the views that follow it were last given
        self._setup_ui()
        self._connect_signals()
        self._on_binding_changed()

    # ------------------------------------------------------------------
    # Views
    # ------------------------------------------------------------------

    def show_view(self, view: str) -> None:
        """Put *view* (one of :data:`VIEWS`) on screen."""
        if view == 'Plot appearance':
            # Another session may have stored the appearance for new sessions since.
            self._appearance.refresh_buttons()
        self._stack.setCurrentWidget(self._views[view])

    def current_view(self) -> str:
        widget = self._stack.currentWidget()
        return next(name for name, page in self._views.items() if page is widget)

    def has_side_panel(self, view: str) -> bool:
        """Whether *view* has a side panel."""
        return self._views[view].side is not None

    def set_side_panels_visible(self, visible: bool) -> None:
        """Show or hide the side panel of every view."""
        for page in self._views.values():
            if page.side is not None:
                page.side.setVisible(visible)

    def guide_section(self, view: str) -> str | None:
        """The section of *Reading the plots* for *view*, or ``None`` for a view without a plot."""
        return _GUIDE_SECTIONS.get(view)

    def run_primary(self, view: str) -> None:
        """The toolbar's primary action in *view*: stop the work running here, else run the analysis or the fit."""
        if self.model.running():
            self.model.stop()
        elif view == 'Sensitivity':
            self.run_sensitivity()
        else:
            self.run_fit()

    def view_badge(self, view: str) -> str | None:
        """The summary beside the title of *view*, or ``None`` for a view that states none yet."""
        if view == 'Measurements':
            return self._measurements.badge()
        if view == 'Binding model':
            return self._binding.badge()
        if view == 'Input uncertainty':
            return self._uncertainty.badge()
        if view == 'Fit results':
            return self._results.badge()
        if view == 'Ka confidence':
            return self._confidence.badge()
        if view == 'Sensitivity':
            return self._sensitivity.badge()
        if view == 'Plot appearance':
            return self._appearance.badge()
        return None

    def _plot_widget_of(self, view: str):
        return {
            'Measurements': self._measurements.plot,
            'Fit results': self._results,
            'Ka confidence': self._confidence,
            'Sensitivity': self._sensitivity,
            'Plot appearance': self._appearance,
        }.get(view)

    def plot_export_note(self, view: str) -> str | None:
        """Why the plot of *view* cannot be saved — or ``None`` when it can."""
        widget = self._plot_widget_of(view)
        model = self.model
        if widget is None:
            return (
                'This view has no plot to save. Open Measurements, Fit results, Ka confidence, Sensitivity or '
                'Plot appearance.'
            )
        if widget is self._measurements.plot:
            return None if model.measurement_set is not None else 'There is no titration yet. Load data, then save it.'
        if widget is self._results or widget is self._appearance:
            if model.measurement_set is None and not model.fit_results:
                return 'There is no titration plot yet. Load a measurement file, then save it.'
            return None
        if widget is self._confidence:
            if not self._confidence.has_plot():
                return 'There is no Ka confidence plot to save yet. Run a fit and wait for its profile, then save it.'
            return model.hidden_results_note()
        if model.sensitivity_result is None:
            return 'There is no sensitivity analysis to save yet. Run one, then save it.'
        return model.sensitivity_note

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def add_files(self) -> None:
        """Ask for files and add them to this session as further replicates."""
        self._measurements.add_files()

    def replace_data(self) -> bool:
        """Ask for files and load them in place of this session's data; whether anything was loaded."""
        return self._measurements.replace_data()

    def run_fit(self) -> None:
        """Start a background fit of the loaded data with the settings shown; say why when it cannot start."""
        self._finish_edits()
        refusal = self.model.run_fit()
        if refusal is None:
            return
        QMessageBox.warning(self, refusal.title, refusal.message)
        if refusal == CONCENTRATIONS_REQUIRED:
            self.view_requested.emit('Measurements')
            self._measurements.focus_concentrations()

    def load_demo_ida(self) -> None:
        """Load the bundled IDA demo dataset and fit it with the demo's own settings.

        The same settings whatever the session held before, and what they are
        is said on the status bar:

        - the IDA assay with its default conditions (Ka,dye 16.8 MM⁻¹,
          [Host]₀ 4.3 µM, [Dye]₀ 6 µM) and constant totals;
        - the IDA default parameter bounds;
        - the input uncertainties of :data:`_DEMO_UNCERTAINTIES` — Ka,dye
          σ 10 %, [Host]₀, [Dye]₀ and the titrant σ 3 % each — and no shared
          source or error of the additions, so the first fit reports the
          interval that covers them, with the conditional one beside it;
        - the replicates averaged without the per-replicate test;
        - Outlier Removal applied as the panel is set (its defaults unless changed).
        """
        if not _DEMO_IDA_PATH.exists():
            QMessageBox.warning(self, 'Demo Data Missing', f'Could not find:\n{_DEMO_IDA_PATH}')
            return
        busy = self.model.busy_note()
        if busy is not None:
            QMessageBox.warning(self, 'Already Running', busy)
            return

        binding = self.model.binding
        binding.set_assay(AssayType.IDA)
        binding.set_per_replica(False)
        self.model.binding_edited()
        self.model.uncertainty.set_specs(_DEMO_UNCERTAINTIES)
        self.model.uncertainty_edited()

        # Loading resets the replicates and clears the results.
        refusal = self.model.load_files([str(_DEMO_IDA_PATH)]) or self.model.remove_outliers(3.5, 3)
        if refusal is not None:
            QMessageBox.warning(self, refusal.title, refusal.message)
            return
        self.run_fit()
        if self.model.fit_running():
            labels = self.model.settings.input_labels
            stated = and_join(
                f'{labels[key]} {stated_uncertainty(spec, "")}' for key, spec in _DEMO_UNCERTAINTIES.items()
            )
            self.model.show_status(f'Demo settings: {stated} — fitting…')

    def _default_save_name(self, suffix: str, tag: str = '') -> str:
        """A default save filename from the stem of the session's data file (:meth:`SessionModel.dataset_file`)."""
        src = self.model.dataset_file()
        if not src:
            return f'{tag or "output"}{suffix}'
        stem = Path(src).stem
        return f'{stem}{("_" + tag) if tag else ""}{suffix}'

    def _finish_edits(self) -> None:
        """Check the results against the settings as they read now, a condition still being typed included.

        An action run from a shortcut leaves the focus in the field being typed
        into, so no edit has ended by itself before the action reads the form.
        """
        self.model.check_results()

    def _can_export_results(self) -> bool:
        """Whether there are shown results to export, checked against the settings as they read now; says why not."""
        self._finish_edits()
        note = self.model.hidden_results_note()
        if note is not None:
            QMessageBox.warning(self, 'Results Hidden', note)
            return False
        if not self.model.fit_results:
            QMessageBox.information(self, 'No Results', 'Run a fit first.')
            return False
        return True

    def _replica_order(self) -> list[str] | None:
        ms = self.model.measurement_set
        return None if ms is None else list(ms.replica_ids)

    def export_results(self) -> None:
        """Export current fit results to JSON."""
        if not self._can_export_results():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, 'Export Fit Results', self._default_save_name('.json', 'results'), 'JSON (*.json)'
        )
        if not path:
            return
        from gui.session import export_results

        export_results(self.model.fit_results, path, self.model.plot_appearance)
        self.model.show_status(f'Results exported to {path}')

    def export_results_txt(self) -> None:
        """Export current fit results as a human-readable text report."""
        if not self._can_export_results():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, 'Export Results (TXT)', self._default_save_name('.txt', 'results'), 'Text files (*.txt)'
        )
        if not path:
            return
        from gui.session import export_results_txt

        export_results_txt(self.model.fit_results, path, replica_ids=self._replica_order())
        self.model.show_status(f'Results exported to {path}')

    def export_results_csv(self) -> None:
        """Export current fit results as a machine-readable CSV table."""
        if not self._can_export_results():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, 'Export Results (CSV)', self._default_save_name('.csv', 'results'), 'CSV files (*.csv)'
        )
        if not path:
            return
        from gui.session import export_results_csv

        export_results_csv(self.model.fit_results, path, replica_ids=self._replica_order())
        self.model.show_status(f'Results exported to {path}')

    def export_raw_data(self) -> None:
        """Export the currently loaded raw measurements to TXT or CSV.

        The output format is chosen by the file extension and round-trips
        through the existing :class:`TxtReader` and :class:`CsvReader`.
        """
        ms = self.model.measurement_set
        if ms is None:
            QMessageBox.information(self, 'No Data', 'Load a measurement file first.')
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            'Export Raw Data',
            self._default_save_name('.txt'),
            'Text file (*.txt);;CSV file (*.csv)',
        )
        if not path:
            return
        suffix = Path(path).suffix.lower()
        try:
            if suffix == '.csv':
                from core.io.formats.measurement_writer import write_measurements_csv

                write_measurements_csv(ms, path)
            else:
                # Default to TXT if the user typed a different extension.
                from core.io.formats.measurement_writer import write_measurements_txt

                if suffix != '.txt':
                    path = str(Path(path).with_suffix('.txt'))
                write_measurements_txt(ms, path)
        except Exception:
            QMessageBox.warning(
                self,
                'Export Error',
                'Could not save the raw data. Check that the destination folder exists and '
                'you have permission to write there.',
            )
            return
        self.model.show_status(f'Raw data exported to {path}')

    def import_results(self) -> None:
        """Import fit results from JSON, check each against the loaded data, and show those that describe it.

        With no data loaded, the results' source file is loaded first when it
        still exists. The model checks each result
        (:meth:`~gui.session_model.SessionModel.check_imported`): the ones it
        refuses are named with the reason, the others replace the held results
        and are shown or hidden like a fit made here. The replicate selection is
        never changed. Without data the stored numbers are shown with a note
        that they could not be checked, and with data loaded a notice names the
        results the check could not judge. Refused while a fit runs, whose
        result would replace the imported ones as it finished.
        """
        refusal = self.model.import_refusal()
        if refusal is not None:
            QMessageBox.warning(self, refusal.title, refusal.message)
            return
        path, _ = QFileDialog.getOpenFileName(self, 'Import Fit Results', '', 'JSON (*.json);;All files (*)')
        if not path:
            return
        from gui.session import import_appearance, import_results

        try:
            results = import_results(path)
        except Exception:
            QMessageBox.warning(
                self,
                'Import Error',
                'Could not import these results. Make sure the file is a results file (.json) exported by SupraSimFit.',
            )
            return
        if self.model.measurement_set is None and results:
            source_file = results[-1].source_file
            if source_file and Path(source_file).exists():
                self.model.load_files([source_file])

        check = self.model.check_imported(results, Path(path).name)
        if check.refusal is not None:
            QMessageBox.warning(self, 'Results Not Imported', check.refusal)
            if not check.accepted:
                return
        try:
            appearance = import_appearance(path)
        except ValueError as exc:
            appearance = None
            QMessageBox.information(self, 'Imported Results', f'{exc} The plot keeps this session’s own appearance.')
        self.model.show_imported(check.accepted, path, appearance)
        if self.model.measurement_set is None:
            # A results file opens under the name of the data it was made from.
            source = check.accepted[-1].source_file if check.accepted else None
            self.model.set_custom_name(Path(source or path).stem)
        if check.notice is not None:
            QMessageBox.information(self, 'Imported Results', check.notice)

    def export_plot(self, view: str) -> None:
        """Save the plot of *view*.

        The titration plot of Fit results offers PNG or SVG. Ka confidence and
        Sensitivity are saved as one picture of several plots, which only PNG can
        carry: see :func:`~gui.plotting.export.export_widget`. An edit still being
        typed is finished first, so the picture matches the settings.
        """
        self._finish_edits()
        note = self.plot_export_note(view)
        if note is not None:
            QMessageBox.warning(self, 'Save Plot', note)
            return
        widget = self._plot_widget_of(view)
        # A whole tab is saved as one picture, which rules out SVG; see
        # gui.plotting.export.export_widget.
        tag, formats = {
            self._measurements.plot: ('titration', 'PNG image (*.png);;SVG vector (*.svg)'),
            self._results: ('', 'PNG image (*.png);;SVG vector (*.svg)'),
            self._appearance: ('', 'PNG image (*.png);;SVG vector (*.svg)'),
            self._confidence: ('confidence', 'PNG image (*.png)'),
            self._sensitivity: ('sensitivity', 'PNG image (*.png)'),
        }[widget]
        path, _ = QFileDialog.getSaveFileName(
            self,
            'Save Plot',
            self._default_save_name('.png', tag),
            formats,
        )
        if not path:
            return
        try:
            widget.export_image(path)
        except ExportRefused as exc:
            QMessageBox.warning(self, 'Save Plot', str(exc))
            return
        except Exception:
            QMessageBox.warning(
                self,
                'Export Error',
                'Could not save the plot. Check that the destination folder exists and you '
                'have permission to write there.',
            )
            return
        self.model.show_status(f'Plot saved to {path}')

    def open_export_multiple_dialog(self, *, select_all_default: bool) -> None:
        """Show the consolidated multi-artefact export dialog, once an edit still being typed is finished."""
        self._finish_edits()
        from gui.dialogs.export_multiple_dialog import ExportMultipleDialog

        dlg = ExportMultipleDialog(self, select_all_default=select_all_default, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            outcomes = dlg.outcomes
            successes = sum(1 for _l, _p, e in outcomes if e is None)
            if successes:
                folder = outcomes[0][1].parent
                self.model.show_status(f'Exported {successes}/{len(outcomes)} artefact(s) to {folder}')

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self._measurements = MeasurementsView(self.model, self)
        self._binding = BindingView(self.model, self)
        self._uncertainty = UncertaintyView(self.model, self)
        self._results = FitResultsView(self.model, self)
        self._confidence = ConfidenceView(self.model, self)
        self._sensitivity = SensitivityView(self.model, self)
        self._appearance = PlotAppearanceView(self.model, self)

        def side(title: str, *widgets: QWidget, link: QWidget | None = None) -> _SidePanel:
            content = QWidget()
            content.setLayout(C.vbox(*widgets, spacing=5))
            panel = _SidePanel(title, content, link)
            panel.close_requested.connect(self.side_panel_closed)
            return panel

        self._views: dict[str, _View] = {
            'Measurements': _View(self._measurements.canvas, side('Measurement settings', self._measurements.side)),
            'Binding model': _View(self._binding.canvas),
            'Input uncertainty': _View(self._uncertainty.canvas, side('Effect on the fit', self._uncertainty.side)),
            'Fit results': _View(self._results.canvas, side('Fit details', self._results.side)),
            'Ka confidence': _View(
                self._confidence.canvas, side('Notes', self._confidence.side, link=self._confidence.guide_link)
            ),
            'Sensitivity': _View(self._sensitivity.canvas, side('Analysis settings', self._sensitivity.side)),
            'Plot appearance': _View(
                self._appearance.canvas, side('Titration plot', self._appearance.side, link=self._appearance.reset)
            ),
        }
        self._stack = QStackedWidget()
        for view in VIEWS:
            self._stack.addWidget(self._views[view])
        self._progress_line = C.ProgressLine(theme())
        self.setLayout(C.vbox(self._progress_line, self._stack, spacing=0))
        self.show_view('Fit results')

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self.model.data_changed.connect(self._on_data_changed)
        self._measurements.new_session_link.clicked.connect(self.new_session_requested)

        self._uncertainty.review_requested.connect(lambda: self.view_requested.emit('Ka confidence'))
        self._results.review_requested.connect(lambda: self.view_requested.emit('Ka confidence'))
        self._results.details_requested.connect(self._show_fit_details)
        self._confidence.shifts_requested.connect(self._show_input_shifts)
        self._confidence.save_requested.connect(lambda: self.export_plot('Ka confidence'))
        self._confidence.guide_requested.connect(
            lambda: show_plot_guide(self.window(), self.guide_section('Ka confidence'))
        )
        self._results.save_plot.clicked.connect(lambda: self.export_plot('Fit results'))
        self._appearance.save_plot.clicked.connect(lambda: self.export_plot('Plot appearance'))
        self._measurements.save_plot.clicked.connect(lambda: self.export_plot('Measurements'))
        self.model.uncertainty_changed.connect(self.changed)
        self.model.binding_changed.connect(self._on_binding_changed)

        self._sensitivity.view_requested.connect(self.view_requested)
        self.model.analysis_changed.connect(self.changed)

        model = self.model
        model.run_changed.connect(lambda _kind, _running: self._show_running())
        model.progress.connect(lambda _done, _total: self._on_progress())
        model.profile_changed.connect(self._show_running)
        model.sensitivity_changed.connect(lambda _replaced: self.changed.emit())
        model.plot_appearance_changed.connect(self.changed)
        model.warning.connect(lambda title, message: QMessageBox.warning(self, title, message))
        for signal in (model.results_changed, model.name_changed, model.status_changed):
            signal.connect(self.changed)

    # ------------------------------------------------------------------
    # Panel slots
    # ------------------------------------------------------------------

    def _on_data_changed(self) -> None:
        self.changed.emit()

    def _on_binding_changed(self) -> None:
        """Give Measurements the model chosen, which names its titrant, once it changes."""
        assay_type = self.model.binding.assay_type
        if assay_type is not self._assay_shown:
            self._assay_shown = assay_type
            self._measurements.refresh()
        self.changed.emit()

    def copy_from(self, other: FittingSession) -> None:
        """Take a copy of what *other* states — data, binding model, input uncertainties — and none of its results."""
        self.model.copy_from(other.model)

    # ------------------------------------------------------------------
    # Ka sensitivity analysis
    # ------------------------------------------------------------------

    def run_sensitivity(self) -> None:
        """Start a background Ka input-sensitivity run, once the user has accepted what a long one costs."""
        self._finish_edits()
        refusal = self.model.sensitivity_refusal(self.model.analysis_problems())
        if refusal is not None:
            QMessageBox.warning(self, refusal.title, refusal.message)
            return
        config = self.model.analysis_config()
        cost = self.model.sensitivity_cost_note(config)
        if cost is not None and QMessageBox.question(self, 'This Will Take a While', cost) != (
            QMessageBox.StandardButton.Yes
        ):
            return
        refusal = self.model.run_sensitivity(config)
        if refusal is not None:
            QMessageBox.warning(self, refusal.title, refusal.message)

    # ------------------------------------------------------------------
    # Model slots
    # ------------------------------------------------------------------

    def _on_progress(self) -> None:
        self._progress_line.set_progress(self.model.progress_fraction())
        self.changed.emit()

    def _show_running(self) -> None:
        """Show the work running here: the progress line, and the inputs that feed it locked until it ends."""
        model = self.model
        running = model.running()
        if running:
            self._progress_line.set_progress(model.progress_fraction())
        else:
            self._progress_line.stop()
        # A fit and an analysis each read the binding model and the uncertainties
        # as they were when it started, so those stay as they were read until it ends.
        work = model.fit_running() or model.sensitivity_running()
        self._binding.set_locked(work)
        self._uncertainty.set_locked(work)
        self._sensitivity.set_locked(work)
        self.changed.emit()

    def _show_input_shifts(self) -> None:
        """Show the Notes side panel of Ka confidence with the input shifts in view."""
        self.side_panel_requested.emit()
        side = self._views['Ka confidence'].side
        side.show()
        self._confidence.show_shifts(side.scroll)

    def _show_fit_details(self) -> None:
        """Show the side panel of Fit results with Diagnostics in view."""
        self.side_panel_requested.emit()
        side = self._views['Fit results'].side
        side.show()
        self._results.show_diagnostics(side.scroll)
