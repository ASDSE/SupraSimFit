"""FittingSession — the view of one fitting session (one tab): its panels and plot tabs over a SessionModel."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QEvent, QObject, QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.data_processing.measurement_set import MeasurementSet
from core.data_processing.plotting import prepare_plot_data
from core.pipeline.fit_pipeline import FitConfig
from core.pipeline.inputs import TITRANT, InputSpec
from gui import plot_guide
from gui.dialogs.plot_guide_dialog import show_plot_guide
from gui.plotting.colors import INK, INK_2, INK_3
from gui.plotting.export import ExportRefused
from gui.plotting.fit_summary_widget import FitSummaryWidget
from gui.plotting.identifiability_widget import IdentifiabilityWidget
from gui.plotting.labels import and_join, stated_uncertainty
from gui.plotting.plot_style import PlotStyleWidget
from gui.plotting.plot_widget import PlotWidget
from gui.plotting.sensitivity_widget import SensitivityWidget
from gui.session_model import CONCENTRATIONS_REQUIRED, SessionModel
from gui.widgets.assay_config_panel import AssayConfigPanel
from gui.widgets.bounds_panel import BoundsPanel
from gui.widgets.data_panel import DataPanel
from gui.widgets.fit_config_panel import FitConfigPanel
from gui.widgets.flat_tabs import FlatTabWidget
from gui.widgets.info_button import InfoGroupBox
from gui.widgets.input_uncertainty_panel import InputUncertaintyPanel
from gui.widgets.preprocessing_panel import PreprocessingPanel
from gui.widgets.replica_panel import ReplicaPanel
from gui.widgets.sensitivity_panel import SensitivityPanel

# Height a plot tab's page keeps however far the summary below is dragged up, so
# the Fit Curve plot keeps its axis labels apart.
_PLOT_PAGE_MIN_HEIGHT = 250

# The plot tab bar's "?" button: secondary ink on a hairline pill, darker on hover.
_GUIDE_BUTTON_QSS = f"""
QToolButton {{
    color: {INK_2};
    background: transparent;
    border: 1px solid #d6d5cf;
    border-radius: 10px;
    padding: 2px 9px;
    margin: 4px 8px 4px 0;
    font-size: 13px;
}}
QToolButton:hover {{
    color: {INK};
    border-color: {INK_3};
}}
"""


class _SidebarScrollArea(QScrollArea):
    """Vertically-scrolling sidebar whose width follows its content.

    A plain ``QScrollArea`` reports a near-zero width hint regardless of its
    content, so a ``QSplitter`` will shrink it until the content clips. The
    sidebar scrolls vertically only, so its width must track the content: we
    advertise the content's *minimum* width (plus the frame and the vertical
    scrollbar) as both our minimum and preferred width. The splitter then honors
    it as the sidebar's floor and shrinks the *other* pane instead — content is
    never clipped — while the sidebar opens compact (the content minimum) rather
    than at the widest panel's much larger preferred width.

    When the content's minimum width changes (a panel row widens or narrows),
    the sidebar takes that width in its splitter at once, or the width the user
    last dragged it to if that is wider.
    """

    def __init__(self) -> None:
        super().__init__()
        self._dragged_width = 0

    def remember_dragged_width(self) -> None:
        """Keep the sidebar's current width as the user's choice (connect to ``QSplitter.splitterMoved``)."""
        self._dragged_width = self.width()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        # QScrollArea already filters its content widget's events. A content
        # layout change alters this area's size hints, which Qt does not pass
        # on to the splitter by itself.
        if obj is self.widget() and event.type() == QEvent.Type.LayoutRequest:
            self.updateGeometry()
            self._fit_width()
        return super().eventFilter(obj, event)

    def _fit_width(self) -> None:
        """Resize within the splitter to the content's width, or the dragged width if wider."""
        splitter = self.parentWidget()
        if not isinstance(splitter, QSplitter) or not splitter.isVisible():
            return
        sizes = splitter.sizes()
        i = splitter.indexOf(self)
        delta = max(self._content_width(), self._dragged_width) - sizes[i]
        if delta:
            sizes[i] += delta
            sizes[i + 1] -= delta
            splitter.setSizes(sizes)

    def _content_width(self) -> int:
        # Width needed to show the content un-clipped: the content's own minimum
        # width + the frame + the vertical scrollbar. Read from Qt at runtime so
        # it adapts to platform/style and to the panels' current contents.
        content = self.widget()
        if content is None:
            return 0
        return content.minimumSizeHint().width() + 2 * self.frameWidth() + self.verticalScrollBar().sizeHint().width()

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        if self.widget() is not None:
            hint.setWidth(self._content_width())
        return hint

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        if self.widget() is not None:
            hint.setWidth(self._content_width())
        return hint


_PLOT_STYLE_HELP_HTML = """
<h3>Plot Style</h3>

<p><b>What This Section Is For</b></p>
<p>Controls for the interactive plot on the right: which series are
visible (replicates, average, error bars, fit curves), axis/tick/legend
font sizes, marker shapes and palette, line widths and colors, and the
x-axis display unit. Changes apply live &mdash; no need to re-run the
fit.</p>

<p><b>What Affects What</b></p>
<ul>
  <li><b>Visibility</b> &mdash; toggles whole series on or off. Hidden
      series are not drawn and do not appear in the legend.</li>
  <li><b>Axes</b> &mdash; font sizes for labels/ticks and the x-axis
      unit (nM / &micro;M / mM / M). Data is stored in M internally and
      rescaled at render time.</li>
  <li><b>Replicates, Dropped replicates, Average Line, Fit Curves, Error
      Bars</b> &mdash; per-series style groups.</li>
  <li><b>Legend, Annotations</b> &mdash; toggle the legend and the
      draggable fit-results overlay.</li>
</ul>

<p><b>Save and Reuse: Style Templates</b></p>
<p>You can save the entire Plot Style configuration and reload it
later, so you don&rsquo;t have to reconfigure fonts, colors, and
visibility every session.</p>
<ul>
  <li><b>Import &rarr; Load Style Template&hellip;</b> &mdash; load a
      <code>.json</code> template (all controls update at once).</li>
  <li><b>Export &rarr; Save Style Template</b> &mdash; write the
      current style to a <code>.json</code> file you can share or
      commit to your project.</li>
</ul>
<p>Style templates round-trip exactly, so they&rsquo;re a good way to
enforce a consistent look across figures in a paper or lab report.</p>

<p><b>Tip</b></p>
<p>If the fit-results annotation or the legend ends up in an awkward
spot, drag them with the mouse. The app remembers the drag position
until you toggle the corresponding overlay off and back on.</p>
"""

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


class FittingSession(QWidget):
    """One complete fitting workflow on screen: data → preprocess → configure → fit → visualize.

    Each tab in the main window is one FittingSession. Its state and rules
    live in :attr:`model`, a :class:`~gui.session_model.SessionModel`: the
    view states what its panels show to the model (:meth:`_push_settings`)
    whenever a panel reports a change, draws what the model's signals say
    changed, and keeps the parts that need a screen — file dialogs, message
    boxes, plot images and style templates.

    Signals
    -------
    actions_changed()
        Emitted when what the window's actions can do may have changed — a
        run started or ended, results were shown or hidden, or another plot
        tab came on screen — so the window can set its fit action, Save Plot
        and the result exports.
    """

    actions_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = SessionModel(self)
        self._plot_note: str | None = None  # the note hiding a fit on the Fit Curve
        self._setup_ui()
        self._connect_signals()
        self._push_settings()

    # ------------------------------------------------------------------
    # Public API (called by FittingMainWindow)
    # ------------------------------------------------------------------

    def plot_export_note(self) -> str | None:
        """Why the plot on the tab on screen cannot be saved — or ``None`` when it can."""
        widget = self._plot_tabs.currentWidget()
        model = self.model
        if widget is self._plot_widget:
            if model.measurement_set is None and not model.fit_results:
                return 'There is nothing on the Fit Curve tab yet. Load a measurement file, then save it.'
            return None
        if widget is self._identifiability_widget:
            if not self._identifiability_widget.has_chart():
                return 'There is no identifiability chart to save yet. Run a fit, then save it.'
            return model.hidden_results_note()
        if model.sensitivity_result is None:
            return 'There is no sensitivity analysis to save yet. Run one, then save it.'
        return model.sensitivity_note

    def load_data(self) -> None:
        """Ask for a measurement file and load it into this session."""
        self._data_panel.load_file()

    def run_fit(self) -> None:
        """Start a background fit of the loaded data with the settings shown; say why when it cannot start."""
        self._finish_edits()
        refusal = self.model.run_fit()
        if refusal is None:
            return
        QMessageBox.warning(self, refusal.title, refusal.message)
        if refusal == CONCENTRATIONS_REQUIRED:
            self._data_panel.focus_concentration_table()

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
        self._data_panel.load_file(str(_DEMO_IDA_PATH))
        self._preprocess_panel.apply()
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
                self._data_panel.load_file(source_file)

        self._push_settings()
        check = self.model.check_imported(results, Path(path).name)
        if check.refusal is not None:
            QMessageBox.warning(self, 'Results Not Imported', check.refusal)
            if not check.accepted:
                return
        self.model.show_imported(check.accepted, path)
        if check.notice is not None:
            QMessageBox.information(self, 'Imported Results', check.notice)

    def export_plot(self) -> None:
        """Save the plot on the tab that is showing.

        The Fit Curve tab offers PNG or SVG. The Identifiability and Ka
        Sensitivity tabs are saved whole, as one picture, which only PNG can
        carry: see :func:`~gui.plotting.export.export_widget`. An edit still
        being typed is finished first, so the picture matches the settings.
        """
        self._finish_edits()
        note = self.plot_export_note()
        if note is not None:
            QMessageBox.warning(self, 'Save Plot', note)
            return
        widget = self._plot_tabs.currentWidget()
        # A whole tab is saved as one picture, which rules out SVG; see
        # gui.plotting.export.export_widget.
        tag, formats = {
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

    def save_style_template(self) -> None:
        """Save current plot style settings to a JSON file."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            'Save Style Template',
            'style_template.json',
            'JSON (*.json)',
        )
        if not path:
            return
        from gui.plotting.plot_style import save_style_json

        style = self._style_widget.widget.current_style()
        save_style_json(style, path)
        self.model.show_status(f'Style template saved to {path}')

    def load_style_template(self) -> None:
        """Load plot style settings from a JSON file."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            'Load Style Template',
            '',
            'JSON (*.json);;All files (*)',
        )
        if not path:
            return
        try:
            from gui.plotting.plot_style import load_style_json

            style = load_style_json(path)
            self._style_widget.widget.load_style(style)
            # Reflect the loaded x_unit in the Data panel's Display Unit
            # combo so the two stay in sync after a style import.
            loaded_unit = style.get('axes', {}).get('x_unit')
            if loaded_unit:
                self.model.update_settings(display_unit=loaded_unit)
                self._data_panel.set_display_unit(loaded_unit)
            self.model.show_status(f'Style template loaded from {path}')
        except Exception:
            QMessageBox.warning(
                self,
                'Load Error',
                'Could not load this style template. Make sure it is a style file (.json) exported by SupraSimFit.',
            )

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
        # The sidebar scrolls vertically only; its width is driven by the
        # content's own size hints (see _SidebarScrollArea). The splitter honors
        # that as the sidebar's minimum and shrinks the plot pane instead, so the
        # content is never clipped. No max-width cap and childrenCollapsible(False)
        # keep it freely widenable yet never collapsible to zero.
        self._sidebar_scroll = _SidebarScrollArea()
        self._sidebar_scroll.setWidgetResizable(True)
        self._sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll = self._sidebar_scroll

        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setSpacing(6)
        left_layout.setContentsMargins(6, 6, 6, 6)

        self._data_panel = DataPanel(initial_display_unit=self.model.settings.display_unit)
        self._preprocess_panel = PreprocessingPanel()
        self._replica_panel = ReplicaPanel()
        self._assay_panel = AssayConfigPanel()
        self._input_panel = InputUncertaintyPanel()
        self._fit_panel = FitConfigPanel()
        self._sensitivity_panel = SensitivityPanel()
        self._bounds_panel = BoundsPanel()
        self._style_widget = _Grouped(
            'Plot Style',
            PlotStyleWidget(),
            info_title='Plot Style',
            info_html=_PLOT_STYLE_HELP_HTML,
        )

        for widget in (
            self._data_panel,
            self._preprocess_panel,
            self._replica_panel,
            self._assay_panel,
            self._input_panel,
            self._fit_panel,
            self._sensitivity_panel,
            self._bounds_panel,
            self._style_widget,
        ):
            left_layout.addWidget(widget)

        left_layout.addStretch()
        left_scroll.setWidget(left_container)
        splitter.addWidget(left_scroll)
        splitter.splitterMoved.connect(left_scroll.remember_dragged_width)

        # ---- Right panel (tabbed plot area + summary, vertically resizable)
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.setChildrenCollapsible(False)

        # Tabbed plot area (flat/minimal, white pane):
        # Fit Curve | Identifiability | Ka Sensitivity.
        self._plot_widget = PlotWidget()
        self._identifiability_widget = IdentifiabilityWidget()
        self._sensitivity_widget = SensitivityWidget()
        self._plot_tabs = FlatTabWidget(white_pane=True)
        self._plot_tabs.addTab(self._plot_widget, 'Fit Curve')
        self._plot_tabs.addTab(self._identifiability_widget, 'Identifiability')
        self._plot_tabs.addTab(self._sensitivity_widget, 'Ka Sensitivity')
        guide_button = QToolButton()
        guide_button.setText('? How to read this plot')
        guide_button.setToolTip('Open the guide to reading the plot on this tab')
        guide_button.setCursor(Qt.CursorShape.PointingHandCursor)
        guide_button.setStyleSheet(_GUIDE_BUTTON_QSS)
        guide_button.clicked.connect(self._show_plot_guide)
        self._plot_tabs.setCornerWidget(guide_button, Qt.Corner.TopRightCorner)

        # Every plot page's floor is _PLOT_PAGE_MIN_HEIGHT, whichever tab is showing:
        # dragging the summary up stops where a plot is still readable, and a page
        # whose content is taller scrolls or clips rather than limiting the drag.
        # Only the page on screen sets the tabs' width (FlatTabWidget).
        for index in range(self._plot_tabs.count()):
            self._plot_tabs.widget(index).setMinimumHeight(_PLOT_PAGE_MIN_HEIGHT)

        self._summary_widget = FitSummaryWidget()

        right_splitter.addWidget(self._plot_tabs)
        right_splitter.addWidget(self._summary_widget)
        right_splitter.setStretchFactor(0, 1)
        right_splitter.setStretchFactor(1, 1)
        splitter.addWidget(right_splitter)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        # No explicit initial split: the sidebar opens at its content-driven
        # sizeHint width and the plot (stretch factor 1) takes the rest.

        # Open the panels that follow the assay on the default assay type. The
        # heatmap axes are the uncertainty panel's inputs, named as it names them.
        assay_type = self._assay_panel.current_assay_type()
        self._bounds_panel.set_assay_type(assay_type)
        self._input_panel.set_assay_type(assay_type)
        self._sensitivity_panel.set_assay_type(assay_type)
        self._name_inputs()
        self._on_conditions_changed()

        # Push the initial display unit into PlotStyleWidget so the style
        # dict reflects the DataPanel's combo from the first emission.
        self._style_widget.widget.set_x_unit(self.model.settings.display_unit)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._data_panel.data_loaded.connect(self._on_data_loaded)
        self._data_panel.data_cleared.connect(self._on_data_cleared)
        self._data_panel.display_unit_changed.connect(self._on_display_unit_changed)

        self._preprocess_panel.preprocessing_applied.connect(self._on_preprocessing_applied)
        self._preprocess_panel.preprocessing_reset.connect(self._on_preprocessing_reset)

        self._replica_panel.replicas_changed.connect(self._on_replicas_changed)

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
        # Cancel is offered in two places: the sidebar panel and the running tab.
        self._sensitivity_panel.cancel_requested.connect(self.model.cancel_sensitivity)
        self._sensitivity_widget.cancel_requested.connect(self.model.cancel_sensitivity)

        # Direct widget-to-widget: style → every plot tab
        self._style_widget.widget.style_changed.connect(self._plot_widget.apply_style)
        self._style_widget.widget.style_changed.connect(self._identifiability_widget.apply_style)
        self._style_widget.widget.style_changed.connect(self._sensitivity_widget.apply_style)

        # The summary under the tabs shows the samples of a sensitivity run while its tab is current.
        self._plot_tabs.currentChanged.connect(
            lambda _: self._summary_widget.show_samples(self._plot_tabs.currentWidget() is self._sensitivity_widget)
        )
        # Save Plot saves the tab on screen, so what it can do changes with the tab.
        self._plot_tabs.currentChanged.connect(lambda _: self.actions_changed.emit())

        # A fit and an analysis each read the uncertainties as they were when it
        # started, so the rows stay as they were read until it ends.
        self.actions_changed.connect(
            lambda: self._input_panel.set_running(self.model.fit_running() or self.model.sensitivity_running())
        )

        model = self.model
        model.run_changed.connect(self._on_run_changed)
        model.progress.connect(self._sensitivity_widget.set_progress)
        model.results_changed.connect(self._on_results_changed)
        model.profile_changed.connect(self._on_profile_changed)
        model.sensitivity_changed.connect(self._on_sensitivity_changed)
        model.warning.connect(lambda title, message: QMessageBox.warning(self, title, message))

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
            display_unit=self._data_panel.display_unit(),
        )

    # ------------------------------------------------------------------
    # Panel slots
    # ------------------------------------------------------------------

    def _on_data_loaded(self, ms: MeasurementSet) -> None:
        self._preprocess_panel.set_measurement_set(ms)
        self._replica_panel.set_measurement_set(ms)
        self._summary_widget.set_replica_ids(ms.replica_ids)
        self._identifiability_widget.set_replica_ids(ms.replica_ids)
        self._push_settings()
        self.model.load(ms, self._data_panel.current_path())

    def _on_data_cleared(self) -> None:
        self._replica_panel.clear()
        self._summary_widget.set_replica_ids(None)
        self._identifiability_widget.set_replica_ids(None)
        self._push_settings()
        self.model.clear()

    def _on_replicas_changed(self) -> None:
        self._push_settings()
        self.model.replicates_changed()

    def _on_preprocessing_applied(self) -> None:
        self._replica_panel.refresh()
        self._on_replicas_changed()
        ms = self.model.measurement_set
        if ms:
            self.model.show_status(f'Outlier removal applied — {ms.n_active}/{ms.n_replicas} replicates active')

    def _on_preprocessing_reset(self) -> None:
        self._replica_panel.refresh()
        self._on_replicas_changed()
        self.model.show_status('Replicates reset — all active')

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

    def _on_display_unit_changed(self, unit: str) -> None:
        """DataPanel announces a new plot-display unit — propagate to plot."""
        self.model.update_settings(display_unit=unit)
        self._style_widget.widget.set_x_unit(unit)

    def _show_plot_guide(self) -> None:
        """Open Help ▸ Reading the plots at the section for the plot tab on screen."""
        sections = {
            self._plot_widget: plot_guide.FIT_CURVE,
            self._identifiability_widget: plot_guide.IDENTIFIABILITY,
            self._sensitivity_widget: plot_guide.SENSITIVITY,
        }
        show_plot_guide(self, sections[self._plot_tabs.currentWidget()])

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
        self._plot_tabs.setCurrentWidget(self._sensitivity_widget)

    # ------------------------------------------------------------------
    # Model slots
    # ------------------------------------------------------------------

    def _on_run_changed(self, kind: str, running: bool) -> None:
        if kind == 'sensitivity':
            self._sensitivity_panel.set_running(running)
        self.actions_changed.emit()

    def _on_profile_changed(self) -> None:
        """Show the latest fit's Ka profile on Identifiability: pending, drawn, or the tab emptied."""
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
        self.actions_changed.emit()

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


class _GroupedPlain(QGroupBox):
    """Thin wrapper that places an existing widget inside a QGroupBox."""

    def __init__(self, title: str, widget: QWidget, parent=None):
        super().__init__(title, parent)
        self.widget = widget
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(widget)


class _GroupedWithInfo(InfoGroupBox):
    """Plain wrapper around :class:`InfoGroupBox` exposing ``self.widget``."""

    def __init__(
        self,
        title: str,
        widget: QWidget,
        info_title: str,
        info_html: str,
        parent=None,
    ):
        super().__init__(title, info_title, info_html, parent)
        self.widget = widget
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(widget)


def _Grouped(
    title: str,
    widget: QWidget,
    parent=None,
    info_title: str | None = None,
    info_html: str | None = None,
):
    """Factory: return a plain or info-bearing group-box wrapper."""
    if info_html is not None:
        return _GroupedWithInfo(title, widget, info_title or title, info_html, parent)
    return _GroupedPlain(title, widget, parent)
