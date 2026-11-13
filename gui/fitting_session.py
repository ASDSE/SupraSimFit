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

from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.data_processing.plotting import prepare_plot_data
from core.pipeline.fit_pipeline import FitConfig
from core.pipeline.inputs import TITRANT, InputSpec
from gui import plot_guide
from gui.design import components as C
from gui.design.appearance import theme
from gui.design.tokens import SIZE
from gui.plotting.export import ExportRefused
from gui.plotting.fit_summary_widget import FitSummaryWidget
from gui.plotting.identifiability_widget import IdentifiabilityWidget
from gui.plotting.labels import and_join, stated_uncertainty
from gui.plotting.plot_style import PlotStyleWidget
from gui.plotting.plot_widget import PlotWidget
from gui.plotting.sensitivity_widget import SensitivityWidget
from gui.session_model import CONCENTRATIONS_REQUIRED, SessionModel
from gui.views.measurements import MeasurementsView
from gui.widgets.assay_config_panel import AssayConfigPanel
from gui.widgets.bounds_panel import BoundsPanel
from gui.widgets.fit_config_panel import FitConfigPanel
from gui.widgets.input_uncertainty_panel import InputUncertaintyPanel
from gui.widgets.sensitivity_panel import SensitivityPanel

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
    'Ka confidence': plot_guide.IDENTIFIABILITY,
    'Sensitivity': plot_guide.SENSITIVITY,
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

_UNCHECKED_NOTE = (
    'No data are loaded, so these numbers are shown as stored in the file and could not be checked against '
    'the data. To check them, load the data first and import the results again.'
)


class _SidePanel(QWidget):
    """A view's side panel: its name and a close button over a scrolled body of *content*."""

    close_requested = pyqtSignal()

    def __init__(self, title: str, content: QWidget):
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
        header.setLayout(C.hbox(C.label(title, 'body-strong'), None, close, margins=(5, 0, 3, 0)))
        body = QWidget()
        body.setObjectName('InspectorBody')
        body.setLayout(C.vbox(content, None, spacing=0, margins=(5, 0, 5, 5)))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(body)
        self.setLayout(C.vbox(header, scroll, spacing=0))


def _canvas(*widgets: QWidget, scroll: bool = False) -> QWidget:
    """A view's canvas holding *widgets*, scrolled when it holds a form taller than the window."""
    content = QWidget()
    content.setObjectName('Canvas')
    content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    items = [*widgets, None] if scroll else list(widgets)
    content.setLayout(C.vbox(*items, spacing=5, margins=(6, 5, 6, 5)))
    if not scroll:
        return content
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidget(content)
    return area


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
    live in :attr:`model`, a :class:`~gui.session_model.SessionModel`: the
    view states what its panels show to the model (:meth:`_push_settings`)
    whenever a panel reports a change, draws what the model's signals say
    changed, and keeps the parts that need a screen — file dialogs, message
    boxes and plot images. Its views are the sidebar's (:data:`NAVIGATION`);
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
    view_requested(str)
        Emitted when the session needs one of its views on screen, such as
        Measurements for concentrations a fit needs.
    new_session_requested()
        Emitted by *Load data into a new session…* inside a view.
    """

    changed = pyqtSignal()
    side_panel_closed = pyqtSignal()
    view_requested = pyqtSignal(str)
    new_session_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = SessionModel(self)
        self._plot_note: str | None = None  # the note hiding a fit on the Fit Curve
        self._setup_ui()
        self._connect_signals()
        self._push_settings()

    # ------------------------------------------------------------------
    # Views
    # ------------------------------------------------------------------

    def show_view(self, view: str) -> None:
        """Put *view* (one of :data:`VIEWS`) on screen.

        Fit results and Sensitivity share the summary under their plot: it shows the fit
        in the one and the samples of the sensitivity run in the other.
        """
        for split in self._summary_splits:
            if split.isAncestorOf(self._views[view]) or self._views[view].isAncestorOf(split):
                if split.indexOf(self._summary_widget) < 0:
                    split.addWidget(self._summary_widget)
                    split.setStretchFactor(0, 3)
                    split.setStretchFactor(1, 2)
                self._summary_widget.show_samples(view == 'Sensitivity')
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
        return None

    def _plot_widget_of(self, view: str):
        return {
            'Measurements': self._measurements.plot,
            'Fit results': self._plot_widget,
            'Ka confidence': self._identifiability_widget,
            'Sensitivity': self._sensitivity_widget,
        }.get(view)

    def plot_export_note(self, view: str) -> str | None:
        """Why the plot of *view* cannot be saved — or ``None`` when it can."""
        widget = self._plot_widget_of(view)
        model = self.model
        if widget is None:
            return 'This view has no plot to save. Open Measurements, Fit results, Ka confidence or Sensitivity.'
        if widget is self._measurements.plot:
            return None if model.measurement_set is not None else 'There is no titration yet. Load data, then save it.'
        if widget is self._plot_widget:
            if model.measurement_set is None and not model.fit_results:
                return 'There is no titration plot yet. Load a measurement file, then save it.'
            return None
        if widget is self._identifiability_widget:
            if not self._identifiability_widget.has_chart():
                return 'There is no Ka confidence chart to save yet. Run a fit, then save it.'
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

        self._assay_panel.set_assay_type(AssayType.IDA)
        self._bounds_panel.reset_to_defaults()
        self._input_panel.set_specs(_DEMO_UNCERTAINTIES)
        self._fit_panel.set_config(FitConfig(per_replica=False))

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
        """Finish a conditions edit still being typed, and check the results against the settings as they read now.

        An action run from a shortcut leaves the focus in the field being typed
        into, so no edit has ended by itself before the action reads the form.
        """
        self._assay_panel.finish_edit()
        self._push_settings()
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

        export_results(self.model.fit_results, path)
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
        from gui.session import import_results

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

        self._push_settings()
        check = self.model.check_imported(results, Path(path).name)
        if check.refusal is not None:
            QMessageBox.warning(self, 'Results Not Imported', check.refusal)
            if not check.accepted:
                return
        self.model.show_imported(check.accepted, path)
        if self.model.measurement_set is None:
            # A results file opens under the name of the data it was made from.
            source = check.accepted[-1].source_file if check.accepted else None
            self.model.set_custom_name(Path(source or path).stem)
        if check.notice is not None:
            QMessageBox.information(self, 'Imported Results', check.notice)

    def export_plot(self, view: str) -> None:
        """Save the plot of *view*.

        The titration plot of Fit results offers PNG or SVG. Ka confidence and
        Sensitivity are saved whole, as one picture, which only PNG can carry:
        see :func:`~gui.plotting.export.export_widget`. An edit still being
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
            self._plot_widget: ('', 'PNG image (*.png);;SVG vector (*.svg)'),
            self._identifiability_widget: ('identifiability', 'PNG image (*.png)'),
            self._sensitivity_widget: ('sensitivity', 'PNG image (*.png)'),
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
        self._assay_panel = AssayConfigPanel()
        self._input_panel = InputUncertaintyPanel()
        self._fit_panel = FitConfigPanel()
        self._sensitivity_panel = SensitivityPanel()
        self._bounds_panel = BoundsPanel()
        self._style_widget = PlotStyleWidget()
        self._plot_widget = PlotWidget()
        self._identifiability_widget = IdentifiabilityWidget()
        self._sensitivity_widget = SensitivityWidget()
        self._summary_widget = FitSummaryWidget()
        self._summary_splits: list[QSplitter] = []

        def side(title: str, *widgets: QWidget) -> _SidePanel:
            content = QWidget()
            content.setLayout(C.vbox(*widgets, spacing=5))
            panel = _SidePanel(title, content)
            panel.close_requested.connect(self.side_panel_closed)
            return panel

        self._views: dict[str, _View] = {
            'Measurements': _View(self._measurements.canvas, side('Measurement settings', self._measurements.side)),
            'Binding model': _View(_canvas(self._assay_panel, self._bounds_panel, self._fit_panel, scroll=True)),
            'Input uncertainty': _View(_canvas(self._input_panel, scroll=True)),
            'Fit results': _View(_canvas(self._fit_split(self._plot_widget))),
            'Ka confidence': _View(_canvas(self._identifiability_widget)),
            'Sensitivity': _View(
                _canvas(self._fit_split(self._sensitivity_widget)), side('Analysis settings', self._sensitivity_panel)
            ),
            'Plot appearance': _View(_canvas(self._style_widget, scroll=True)),
        }
        self._stack = QStackedWidget()
        for view in VIEWS:
            self._stack.addWidget(self._views[view])
        self._progress_line = C.ProgressLine(theme())
        self.setLayout(C.vbox(self._progress_line, self._stack, spacing=0))
        self.show_view('Fit results')

        # Open the panels that follow the assay on the default assay type. The
        # heatmap axes are the uncertainty panel's inputs, named as it names them.
        assay_type = self._assay_panel.current_assay_type()
        self._bounds_panel.set_assay_type(assay_type)
        self._input_panel.set_assay_type(assay_type)
        self._sensitivity_panel.set_assay_type(assay_type)
        self._name_inputs()
        self._on_conditions_changed()

        # The style's x unit is the session's display unit from the first emission.
        self._style_widget.set_x_unit(self.model.settings.display_unit)

    def _fit_split(self, plot: QWidget) -> QSplitter:
        """*plot* above the summary, the split between them dragged by the user."""
        split = QSplitter(Qt.Orientation.Vertical)
        split.setChildrenCollapsible(False)
        split.addWidget(plot)
        self._summary_splits.append(split)
        return split

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self.model.data_changed.connect(self._on_data_changed)
        self._measurements.display_unit_changed.connect(self._style_widget.set_x_unit)
        self._measurements.new_session_link.clicked.connect(self.new_session_requested)

        self._assay_panel.assay_type_changed.connect(self._on_assay_type_changed)
        self._assay_panel.assay_type_changed.connect(self._sensitivity_panel.set_assay_type)
        self._assay_panel.conditions_changed.connect(self._on_conditions_changed)
        self._assay_panel.conditions_edited.connect(self._on_conditions_edited)

        # Every setting a result is checked against goes to the model as it
        # changes; the model decides what a change puts out of date.
        self._input_panel.specs_changed.connect(self._push_settings)
        self._fit_panel.config_changed.connect(self._push_settings)
        self._bounds_panel.bounds_changed.connect(self._push_settings)

        self._sensitivity_panel.run_requested.connect(self.run_sensitivity)
        # Cancel is offered in two places: the side panel and the running view.
        self._sensitivity_panel.cancel_requested.connect(self.model.cancel_sensitivity)
        self._sensitivity_widget.cancel_requested.connect(self.model.cancel_sensitivity)

        # Direct widget-to-widget: style → every plot
        self._style_widget.style_changed.connect(self._plot_widget.apply_style)
        self._style_widget.style_changed.connect(self._identifiability_widget.apply_style)
        self._style_widget.style_changed.connect(self._sensitivity_widget.apply_style)

        model = self.model
        model.run_changed.connect(self._on_run_changed)
        model.progress.connect(self._sensitivity_widget.set_progress)
        model.progress.connect(lambda _done, _total: self._on_progress())
        model.results_changed.connect(self._on_results_changed)
        model.profile_changed.connect(self._on_profile_changed)
        model.sensitivity_changed.connect(self._on_sensitivity_changed)
        model.warning.connect(lambda title, message: QMessageBox.warning(self, title, message))
        for signal in (model.results_changed, model.name_changed, model.status_changed):
            signal.connect(self.changed)

    def _push_settings(self) -> None:
        """State to the model every setting the panels show now.

        Called on every change a panel reports, and before every check of the
        results the view starts, so the model reads the panels as they read
        at that moment.
        """
        assay, bounds, inputs = self._assay_panel, self._bounds_panel, self._input_panel
        self.model.update_settings(
            assay_type=assay.current_assay_type(),
            conditions=assay.current_conditions(),
            condition_units=assay.condition_units(),
            assay_problems=tuple(assay.problems()),
            bounds=bounds.shown_bounds(),
            custom_bounds=bounds.current_bounds(),
            bound_problems=tuple(bounds.problems()),
            per_replica=self._fit_panel.current_config().per_replica,
            errors=inputs.current_errors(),
            input_labels=inputs.input_labels(),
            input_problems=tuple(inputs.problems()),
        )

    # ------------------------------------------------------------------
    # Panel slots
    # ------------------------------------------------------------------

    def _on_data_changed(self) -> None:
        """Give the views that name replicates the replicates of the data now loaded."""
        ms = self.model.measurement_set
        ids = None if ms is None else ms.replica_ids
        self._summary_widget.set_replica_ids(ids)
        self._identifiability_widget.set_replica_ids(ids)
        self.changed.emit()

    def _on_assay_type_changed(self, assay_type: AssayType) -> None:
        self._bounds_panel.set_assay_type(assay_type)
        # The new assay has its own inputs: the uncertainty rows are rebuilt for
        # them first, and the heatmap axes then offer exactly those inputs.
        self._input_panel.set_assay_type(assay_type)
        self._name_inputs()
        meta = ASSAY_REGISTRY[assay_type]
        self._plot_widget.set_axis_labels(meta.x_label, meta.y_label, meta.y_unit)
        self._push_settings()

    def _name_inputs(self) -> None:
        """Offer the heatmap axes the selected assay's inputs, named as the uncertainty panel names them.

        A finished fit names its own inputs from the assay it was made for
        (:func:`~gui.widgets.assay_conditions.result_input_labels`), so what is
        reported about a fit does not follow the assay selected now.
        """
        self._sensitivity_panel.set_inputs(self._input_panel.input_labels())

    def _on_conditions_changed(self) -> None:
        """Give both panels the conditions' set values, which an uncertainty in percent is read against."""
        conditions = self._assay_panel.current_conditions()
        self._input_panel.set_nominal_values(conditions)
        self._sensitivity_panel.set_nominal_values(conditions)
        self._push_settings()

    def _on_conditions_edited(self) -> None:
        self._push_settings()
        self.model.edit_finished()

    # ------------------------------------------------------------------
    # Ka sensitivity analysis
    # ------------------------------------------------------------------

    def run_sensitivity(self) -> None:
        """Start a background Ka input-sensitivity run, once the user has accepted what a long one costs."""
        self._finish_edits()
        errors = self.model.settings.errors
        refusal = self.model.sensitivity_refusal(self._sensitivity_panel.run_problems(errors))
        if refusal is not None:
            QMessageBox.warning(self, refusal.title, refusal.message)
            return
        config = self._sensitivity_panel.current_config(errors)
        cost = self.model.sensitivity_cost_note(config)
        if cost is not None and QMessageBox.question(self, 'This Will Take a While', cost) != (
            QMessageBox.StandardButton.Yes
        ):
            return
        refusal = self.model.run_sensitivity(config)
        if refusal is not None:
            QMessageBox.warning(self, refusal.title, refusal.message)
            return
        self._summary_widget.show_running(config.mode)
        self._sensitivity_widget.show_running()

    # ------------------------------------------------------------------
    # Model slots
    # ------------------------------------------------------------------

    def _on_run_changed(self, kind: str, running: bool) -> None:
        if kind == 'sensitivity':
            self._sensitivity_panel.set_running(running)
        self._show_running()

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
        for panel in (self._assay_panel, self._bounds_panel, self._fit_panel):
            panel.setEnabled(not work)
        self._input_panel.set_running(work)
        self.changed.emit()

    def _on_profile_changed(self) -> None:
        """Show the latest fit's Ka profile in Ka confidence: pending, drawn, or emptied."""
        self._show_running()
        fit = self.model.profiled_fit
        if fit is None:
            self._identifiability_widget.clear()
        elif self.model.profile_running():
            # Until the profiles arrive the tab says they are being computed.
            self._identifiability_widget.show_profile_pending(fit, fit.assay_type)
        else:
            self._identifiability_widget.update_fit(fit, self.model.profile, fit.assay_type)

    def _on_sensitivity_changed(self, replaced: bool) -> None:
        """Draw the held sensitivity result on Ka Sensitivity and the summary, which a run that left none restores."""
        result = self.model.sensitivity_result
        if result is None:
            self._sensitivity_widget.clear()
        else:
            self._sensitivity_widget.update_result(result)
        self._summary_widget.set_sensitivity(result)
        if replaced:
            self._identifiability_widget.update_sensitivity(result)
        self._sensitivity_panel.set_running(self.model.sensitivity_running())

    def _on_results_changed(self, scope: str) -> None:
        """Give every tab the notes hiding its results, and redraw as much as *scope* says changed."""
        self._sync_notes()
        if scope == 'all':
            self._render_results()
        elif scope == 'points':
            self._refresh_plot()

    def _sync_notes(self) -> None:
        """Give the summary, Identifiability and Ka Sensitivity the notes that hide their results."""
        model = self.model
        _, fit_note = model.fit_view()
        held = model.held_fit_results
        profiled_note = model.hidden_fit_notes.get(held[-1].id) if held else None
        self._summary_widget.show_mismatch(fit_note, model.sensitivity_note)
        self._identifiability_widget.show_mismatch(profiled_note, model.sensitivity_note)
        self._sensitivity_widget.show_mismatch(model.sensitivity_note)

    def _render_results(self) -> None:
        """Put the held fit results on the Fit Curve and the summary, shown or hidden."""
        fit, _note = self.model.fit_view()
        self._refresh_plot()
        if fit is None:
            self._summary_widget.clear()
        else:
            unchecked = _UNCHECKED_NOTE if self.model.measurement_set is None else None
            self._summary_widget.update_result(fit, unchecked=unchecked)
        self.changed.emit()

    def _refresh_plot(self) -> None:
        """Draw the loaded points with the curves of the shown fits, and say which held fits are hidden.

        When every held fit is hidden, the note of the latest one replaces the
        fits; when only some are, the shown curves stay and a note names the
        hidden ones. With no data loaded only the shown curves are drawn.
        The axes are labelled for the assay type of the fit the summary
        reports, or of the selected assay when none is shown.
        """
        model = self.model
        ms = model.measurement_set
        shown = model.fit_results
        held = model.held_fit_results
        if ms is None and not held:
            return
        assay_type = AssayType[shown[-1].assay_type] if shown else model.settings.assay_type
        meta = ASSAY_REGISTRY[assay_type]
        if ms is not None:
            plot_data = prepare_plot_data(ms, shown, show_dropped=True)
        else:
            plot_data = {
                'concentrations': held[-1].x_fit.magnitude,
                'active_replicas': [],
                'dropped_replicas': [],
                'average': None,
                'fits': [{'x': r.x_fit.magnitude, 'y': r.y_fit.magnitude, 'label': 'Fit', 'id': r.id} for r in shown],
            }
        self._plot_widget.update_plot(plot_data, x_label=meta.x_label, y_label=meta.y_label, y_unit=meta.y_unit)
        self._plot_widget.set_fit_results(shown)
        self._set_plot_note(model.hidden_results_note())
        self._plot_widget.show_hidden_results(model.other_hidden_note())

    def _set_plot_note(self, note: str | None) -> None:
        """Hide the Fit Curve's fit behind *note*, or show it with ``None``; the plot redraws only on a change."""
        if note != self._plot_note:
            self._plot_note = note
            self._plot_widget.show_mismatch(note)
