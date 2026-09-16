"""FittingSession — one complete fitting workspace (one tab)."""

from __future__ import annotations

import logging
import time
from dataclasses import replace
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
    QVBoxLayout,
    QWidget,
)

from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.data_processing.measurement_set import MeasurementSet
from core.data_processing.plotting import prepare_plot_data
from core.io.formats.bmg_reader import BMG_PLACEHOLDER_KEY
from core.pipeline.fit_pipeline import (
    FitConfig,
    FitResult,
    fit_replica_ids,
    input_replica_ids,
    scoring_assay,
    select_representative,
    verify_imported_result,
)
from core.pipeline.profile import ProfileResult, profile_supported
from core.pipeline.sensitivity import estimated_fit_count, estimated_optimizer_runs, resolve_fit_config
from gui import preferences
from gui.app_state import SessionState
from gui.plotting.distribution_widget import DistributionWidget
from gui.plotting.fit_summary_widget import FitSummaryWidget, and_join, same_inputs
from gui.plotting.identifiability_widget import IdentifiabilityWidget
from gui.plotting.plot_style import PlotStyleWidget
from gui.plotting.plot_widget import PlotWidget
from gui.plotting.sensitivity_widget import SensitivityWidget
from gui.widgets.assay_config_panel import AssayConfigPanel
from gui.widgets.bounds_panel import BoundsPanel
from gui.widgets.data_panel import DataPanel
from gui.widgets.fit_config_panel import FitConfigPanel
from gui.widgets.flat_tabs import FlatTabWidget
from gui.widgets.info_button import InfoGroupBox
from gui.widgets.preprocessing_panel import PreprocessingPanel
from gui.widgets.replica_panel import ReplicaPanel, describe_replicates
from gui.widgets.sensitivity_panel import SensitivityPanel
from gui.workers import FitWorker, ProfileWorker, SensitivityWorker


def _format_remaining(seconds: float) -> str:
    """Time left, rounded to something a person would actually say."""
    if seconds < 60:
        whole = max(1, round(seconds))
        return f'{whole} second' + ('' if whole == 1 else 's')
    minutes = seconds / 60
    if minutes < 60:
        return f'{round(minutes)} minute' + ('' if round(minutes) == 1 else 's')
    hours, rest = divmod(round(minutes), 60)
    return f'{hours} h {rest:02d} min'


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
visible (replicas, average, error bars, fit curves), axis/tick/legend
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
  <li><b>Replicas, Dropped Replicas, Average Line, Fit Curves, Error
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

logger = logging.getLogger(__name__)

_DEMO_IDA_PATH = Path(__file__).parent.parent / 'data' / 'IDA_system.txt'

_UNCHECKED_NOTE = (
    'No data are loaded, so these numbers are shown as stored in the file and could not be checked against '
    'the data. To check them, and to pick another fit, load the data first and import the results again.'
)
_FIT_RUNNING_NOTE = 'A fit is already running in this session. Wait for it to finish, then run the fit again.'

#: Why imported results were refused, by :func:`_refusal_reason`; formatted with
#: ``which`` ("The results" or "2 of the 3 results"), ``name`` and ``imported``.
_REFUSALS = {
    'other_data': (
        '{which} in {name} were made on other data than the data loaded now, so {imported}. '
        'Load the data they were made on, then import them again.'
    ),
    'not_reproduced': (
        '{which} in {name} were made on the data loaded now, but their numbers could not be reproduced on it, '
        'so {imported}. The file may come from another version of SupraSimFit. Run the fit again to get results '
        'for these data.'
    ),
    'selection': (
        '{which} in {name} do not match the data and replicates selected now, so {imported}. The file does not '
        'record which replicates the fit used. Switch on only those replicates, or load the data they were made '
        'on, then import them again.'
    ),
    'other_record': (
        '{which} in {name} do not match the data loaded now, so {imported}. '
        'Load the data they were made on, then import them again.'
    ),
    'unchecked': (
        '{which} in {name} could not be checked against the data loaded now, so {imported}. '
        'Run the fit again to get results for these data.'
    ),
}


def _refusal_reason(result: FitResult, ms: MeasurementSet) -> str:
    """Which :data:`_REFUSALS` entry explains why *result* was refused on the loaded data *ms*.

    A recorded fingerprint tells other data from numbers that do not
    reproduce on the same data. Without one, a file that does not record its
    replicates may simply have been made on another replicate selection.
    """
    recorded = result.metadata.get('data_fingerprint')
    if recorded is not None:
        return 'other_data' if recorded != ms.fingerprint() else 'not_reproduced'
    return 'selection' if fit_replica_ids(result) is None else 'other_record'


def _capitalized(text: str) -> str:
    return f'{text[0].upper()}{text[1:]}'


class FittingSession(QWidget):
    """One complete fitting workflow: data → preprocess → configure → fit → visualize.

    Each tab in the main window is one FittingSession.  All state is stored in
    :class:`SessionState`; widgets communicate via Qt signals coordinated here.

    A result stays on screen only while the loaded selection matches the
    record it was made on (:meth:`_mismatch_note` is the one test). After
    every change to the replicates, the conditions or the assay type, a result
    that no longer matches is hidden on every tab behind a note naming what
    changed, and shown again, unchanged, once the selection matches. A change
    to the data itself clears the results and discards any work still running.

    Signals
    -------
    title_changed(str)
        Emitted when the tab title should change — the loaded dataset's filename,
        a user-set custom name, or "Untitled".
    status_message(str)
        Emitted to update the main window's status bar.
    actions_changed()
        Emitted when :meth:`fit_running` or :meth:`hidden_results_note` may
        have changed, so the window can enable Run Fit and the result exports.
    """

    title_changed = pyqtSignal(str)
    status_message = pyqtSignal(str)
    actions_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = SessionState()
        self._fit_worker: FitWorker | None = None
        self._profile_worker: ProfileWorker | None = None
        self._plot_note: str | None = None  # the note hiding a fit on the Fit Curve
        self._sensitivity_worker: SensitivityWorker | None = None
        self._sensitivity_started = 0.0
        self._custom_tab_name: str | None = None
        self._setup_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # Public API (called by FittingMainWindow)
    # ------------------------------------------------------------------

    def set_custom_tab_name(self, name: str) -> None:
        """Set a manual tab name (double-click rename); empty reverts to auto."""
        self._custom_tab_name = name.strip() or None
        self._emit_tab_title()

    def _tab_title(self) -> str:
        """Resolve the tab title: custom name, else dataset stem, else 'Untitled'."""
        if self._custom_tab_name:
            return self._custom_tab_name
        src = self._state.source_file
        return Path(src).stem if src else 'Untitled'

    def _emit_tab_title(self) -> None:
        self.title_changed.emit(self._tab_title())

    def fit_running(self) -> bool:
        """Whether a fit started in this session is still running."""
        return self._fit_worker is not None

    def hidden_results_note(self) -> str | None:
        """Why result exports and picks are unavailable: the note of the latest fit when every held fit is hidden.

        ``None`` while any result is shown, or when none is held: exports and
        picks then act on the shown results only.
        """
        return self._fit_view()[1]

    def run_fit(self) -> None:
        """Start a background fitting run on a copy of the loaded data, so later changes never reach it."""
        ms = self._state.measurement_set
        if ms is None:
            QMessageBox.warning(self, 'No Data', 'Load a measurement file first.')
            return
        if self.fit_running():
            QMessageBox.warning(self, 'Fit Running', _FIT_RUNNING_NOTE)
            return

        # Placeholder guard — fitting with column indices 1..N as
        # concentrations would silently produce meaningless Ka values.
        # Source-agnostic: any plate-reader import that lacks concentrations
        # sets this flag, regardless of instrument.
        if ms.metadata.get(BMG_PLACEHOLDER_KEY):
            QMessageBox.warning(
                self,
                'Concentrations Required',
                'This dataset has placeholder concentrations. Enter the real '
                'concentration vector in the Data panel before running the fit.',
            )
            self._data_panel.focus_concentration_table()
            return

        assay_cls = self._assay_panel.get_assay_class()
        conditions = self._assay_panel.current_conditions()
        config = self._fit_panel.current_config()
        custom_bounds = self._bounds_panel.current_bounds()
        if custom_bounds:
            config = replace(config, custom_bounds=custom_bounds)

        if config.per_replica and ms.n_active < 3:
            self.status_message.emit(
                f'Per-replica fit on {ms.n_active} replica(s) — uncertainty estimate may not be meaningful (<3 active).'
            )

        self._fit_worker = FitWorker(
            ms.with_active(ms.active_replica_ids),
            assay_cls,
            conditions,
            config,
            source_file=self._state.source_file,
            parent=self,
        )
        self._fit_worker.finished.connect(self._on_fit_complete)
        self._fit_worker.error.connect(self._on_fit_error)
        self._fit_worker.start()
        self.actions_changed.emit()
        self.status_message.emit('Fitting…')

    def load_demo_ida(self) -> None:
        """Load the bundled IDA demo dataset and run a fit with default settings.

        Resets all panels to defaults first so every click produces an
        identical, reproducible result regardless of prior session state.
        """
        if not _DEMO_IDA_PATH.exists():
            QMessageBox.warning(self, 'Demo Data Missing', f'Could not find:\n{_DEMO_IDA_PATH}')
            return

        # 1. Reset all panels to IDA defaults
        self._assay_panel.set_assay_type(AssayType.IDA)
        self._bounds_panel.reset_to_defaults()
        self._fit_panel.set_config(FitConfig(per_replica=False))

        # 2. Load data (triggers _on_data_loaded → resets replicas, clears results)
        self._data_panel.load_file(str(_DEMO_IDA_PATH))

        # 3. Apply z-score outlier removal with default settings
        self._preprocess_panel.apply()

        # 4. Run fit
        self.run_fit()

    def _default_save_name(self, suffix: str, tag: str = '') -> str:
        """Build a default save filename based on the loaded dataset's stem.

        Falls back to the ``source_file`` on the most recent fit result when
        no dataset is currently loaded (e.g. after importing results whose
        source file is missing on disk).
        """
        src = self._state.source_file
        if not src and self._state.fit_results:
            src = self._state.fit_results[-1].source_file
        if not src:
            return f'{tag or "output"}{suffix}'
        stem = Path(src).stem
        return f'{stem}{("_" + tag) if tag else ""}{suffix}'

    def _default_filename_base(self) -> str:
        """Stem-only version of :meth:`_default_save_name` (no tag, no suffix)."""
        src = self._state.source_file
        if not src and self._state.fit_results:
            src = self._state.fit_results[-1].source_file
        return Path(src).stem if src else 'output'

    def _distributions_export_config(self):
        """Build a DistributionsExportConfig from persisted QSettings.

        Used by the multi-artefact export when there's no opportunity to
        show the layout picker inline. Defaults match the standalone
        dialog: Auto layout, per-panel dimensions, 300 DPI, all subplots
        selected.
        """
        from gui.dialogs.save_distributions_dialog import (
            _PER_PANEL_IN,
            DistributionsExportConfig,
            SaveDistributionsPlotDialog,
        )
        from gui.plotting.distribution_widget import DistributionWidget
        from gui.preferences import _settings

        keys = self._distribution_widget.param_keys()
        s = _settings()
        s.beginGroup(SaveDistributionsPlotDialog.SETTINGS_GROUP)
        try:
            mode = s.value('layout_mode', 'auto', type=str)
            custom_rows = int(s.value('custom_rows', 2))
            custom_cols = int(s.value('custom_cols', 2))
            saved_w = float(s.value('width_in', 0.0))
            saved_h = float(s.value('height_in', 0.0))
            dpi = int(s.value('dpi', 300))
            sel = s.value('selected_keys', None)
        finally:
            s.endGroup()

        selected = [k for k in keys if k in set(sel)] if isinstance(sel, list) and sel else list(keys)
        n = max(1, len(selected))
        if mode == 'row':
            rows, cols = 1, n
        elif mode == 'col':
            rows, cols = n, 1
        elif mode == 'grid':
            rows, cols = (2, 2) if n <= 4 else DistributionWidget.auto_layout(n)
        elif mode == 'custom':
            rows, cols = custom_rows, custom_cols
            if rows * cols < n:
                rows, cols = DistributionWidget.auto_layout(n)
        else:
            rows, cols = DistributionWidget.auto_layout(n)

        if saved_w > 0 and saved_h > 0:
            width_in, height_in = saved_w, saved_h
        else:
            width_in, height_in = cols * _PER_PANEL_IN, rows * _PER_PANEL_IN

        return DistributionsExportConfig(
            keys=selected,
            rows=rows,
            cols=cols,
            width_in=width_in,
            height_in=height_in,
            dpi=dpi,
        )

    def _can_export_results(self) -> bool:
        """Whether there are shown results to export; says why not otherwise."""
        note = self.hidden_results_note()
        if note is not None:
            QMessageBox.warning(self, 'Results Hidden', note)
            return False
        if not self._state.fit_results:
            QMessageBox.information(self, 'No Results', 'Run a fit first.')
            return False
        return True

    def _replica_order(self) -> list[str] | None:
        ms = self._state.measurement_set
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

        export_results(self._state.fit_results, path)
        self.status_message.emit(f'Results exported to {path}')

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

        export_results_txt(self._state.fit_results, path, replica_ids=self._replica_order())
        self.status_message.emit(f'Results exported to {path}')

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

        export_results_csv(self._state.fit_results, path, replica_ids=self._replica_order())
        self.status_message.emit(f'Results exported to {path}')

    def export_raw_data(self) -> None:
        """Export the currently loaded raw measurements to TXT or CSV.

        The output format is chosen by the file extension and round-trips
        through the existing :class:`TxtReader` and :class:`CsvReader`.
        """
        ms = self._state.measurement_set
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
        self.status_message.emit(f'Raw data exported to {path}')

    def import_results(self) -> None:
        """Import fit results from JSON, check each against the loaded data, and show those that describe it.

        With no data loaded, the results' source file is loaded first when it
        still exists. Each result is then checked by
        :func:`~core.pipeline.fit_pipeline.verify_imported_result`: one that
        does not describe the loaded data, or cannot be checked, is refused
        with the reason (:func:`_refusal_reason`); the others replace the held
        results and are shown or hidden like a fit made here. The replicate
        selection is never changed. Without data the stored numbers are shown
        with a note that they could not be checked, and picks are disabled.
        """
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
        name = Path(path).name
        if self._state.measurement_set is None and results:
            source_file = results[-1].source_file
            if source_file and Path(source_file).exists():
                self._data_panel.load_file(source_file)
        ms = self._state.measurement_set

        accepted: list[FitResult] = []
        refused: dict[str, int] = {}  # reason -> how many results it refuses
        rescored = repicked = False
        for result in results:
            try:
                status, checked = verify_imported_result(result, ms)
            except Exception:
                logger.exception('Could not check imported result %s against the loaded data', result.id)
                status, checked = 'unchecked', result
            if status in ('different_data', 'unchecked'):
                reason = 'unchecked' if status == 'unchecked' else _refusal_reason(result, ms)
                refused[reason] = refused.get(reason, 0) + 1
                continue
            if status == 'rescored_legacy':
                rescored = True
                repicked = repicked or checked.representative_index != result.representative_index
            accepted.append(checked)
        if refused:
            imported = 'nothing was imported' if not accepted else 'they were left out'
            paragraphs = []
            for reason, count in refused.items():
                which = 'The results' if count == len(results) else f'{count} of the {len(results)} results'
                paragraphs.append(_REFUSALS[reason].format(which=which, name=name, imported=imported))
            QMessageBox.warning(self, 'Results Not Imported', '\n\n'.join(paragraphs))
            if not accepted:
                return

        # Imported fits carry no Ka profile; the tab waits for the next fit.
        self._clear_identifiability()
        self._state.held_fit_results = accepted
        self._show_results(force=True)
        self.status_message.emit(f'Imported {len(accepted)} result(s) from {path}')

        notices = []
        if rescored:
            text = (
                f'Some numbers stored in {name} did not describe the replicates each fit used, so the R², RMSE and '
                'curve were recomputed on those replicates.'
            )
            if repicked:
                text += ' The reported fit is now the one the fit chose itself, so an earlier pick is not kept.'
            notices.append(text)
        # Ranges and spread come from the stored pool of accepted fits. Files
        # without one cannot show them, so say so rather than leaving the user
        # to wonder why those columns are dashes.
        if any(not r.parameter_samples for r in accepted):
            notices.append(
                f'{name} does not store the individual fits behind its results, so the plot and the table can only '
                'show each best-fit value — no range or spread statistics. Re-run the fit to get them.'
            )
        if notices:
            QMessageBox.information(self, 'Imported Results', '\n\n'.join(notices))

    def export_plot(self) -> None:
        """Save the current plot as PNG or SVG."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            'Save Plot',
            self._default_save_name('.png'),
            'PNG image (*.png);;SVG vector (*.svg)',
        )
        if not path:
            return
        try:
            self._plot_widget.export_image(path)
            self.status_message.emit(f'Plot saved to {path}')
        except Exception:
            QMessageBox.warning(
                self,
                'Export Error',
                'Could not save the plot. Check that the destination folder exists and you '
                'have permission to write there.',
            )

    def open_export_multiple_dialog(self, *, select_all_default: bool) -> None:
        """Show the consolidated multi-artefact export dialog."""
        from gui.dialogs.export_multiple_dialog import ExportMultipleDialog

        dlg = ExportMultipleDialog(self, select_all_default=select_all_default, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            outcomes = dlg.outcomes
            successes = sum(1 for _l, _p, e in outcomes if e is None)
            if successes:
                folder = outcomes[0][1].parent
                self.status_message.emit(f'Exported {successes}/{len(outcomes)} artefact(s) to {folder}')

    def save_distributions_plot(self) -> None:
        """Save the distributions plot as a composite PNG with a layout picker."""
        keys = self._distribution_widget.param_keys()
        if not keys:
            QMessageBox.warning(
                self,
                'Save Error',
                'No distributions to save. Run a fit first.',
            )
            return
        from gui.dialogs.save_distributions_dialog import SaveDistributionsPlotDialog

        dlg = SaveDistributionsPlotDialog(self._distribution_widget, self)
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.config is None:
            return
        cfg = dlg.config
        ext = f'.{cfg.format}'
        filter_str = 'PNG image (*.png)' if cfg.format == 'png' else 'SVG vector (*.svg)'
        path, _ = QFileDialog.getSaveFileName(
            self,
            'Save Distributions Plot',
            self._default_save_name(ext, 'distributions'),
            filter_str,
        )
        if not path:
            return
        try:
            self._distribution_widget.save_plot(
                keys=cfg.keys,
                rows=cfg.rows,
                cols=cfg.cols,
                width_in=cfg.width_in,
                dpi=cfg.dpi,
                path=path,
                format=cfg.format,
            )
            self.status_message.emit(f'Distributions plot saved to {path}')
        except Exception:
            QMessageBox.warning(
                self,
                'Save Error',
                'Could not save the distributions plot. Check that the destination folder '
                'exists and you have permission to write there.',
            )

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
        self.status_message.emit(f'Style template saved to {path}')

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
                self._state.display_unit = loaded_unit
                self._data_panel.set_display_unit(loaded_unit)
            self.status_message.emit(f'Style template loaded from {path}')
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

        self._data_panel = DataPanel(initial_display_unit=self._state.display_unit)
        self._preprocess_panel = PreprocessingPanel()
        self._replica_panel = ReplicaPanel()
        self._assay_panel = AssayConfigPanel()
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
        # Fit Curve | Distributions | Identifiability | Ka Sensitivity.
        self._plot_widget = PlotWidget()
        self._distribution_widget = DistributionWidget()
        self._identifiability_widget = IdentifiabilityWidget()
        self._sensitivity_widget = SensitivityWidget()
        self._plot_tabs = FlatTabWidget(white_pane=True)
        self._plot_tabs.addTab(self._plot_widget, 'Fit Curve')
        self._plot_tabs.addTab(self._distribution_widget, 'Distributions')
        self._plot_tabs.addTab(self._identifiability_widget, 'Identifiability')
        self._plot_tabs.addTab(self._sensitivity_widget, 'Ka Sensitivity')

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

        # Initialise BoundsPanel and SensitivityPanel for default assay type
        self._bounds_panel.set_assay_type(self._state.assay_type)
        self._sensitivity_panel.set_assay_type(self._state.assay_type)

        # Push the initial display unit into PlotStyleWidget so the style
        # dict reflects the DataPanel's combo from the first emission.
        self._style_widget.widget.set_x_unit(self._state.display_unit)

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
        self._assay_panel.conditions_edited.connect(self._show_results)

        self._fit_panel.config_changed.connect(self._on_config_changed)

        self._bounds_panel.bounds_changed.connect(self._on_bounds_changed)

        self._sensitivity_panel.run_requested.connect(self.run_sensitivity)
        self._sensitivity_panel.cancel_requested.connect(self._cancel_sensitivity)

        # Direct widget-to-widget: style → every plot tab
        self._style_widget.widget.style_changed.connect(self._plot_widget.apply_style)
        self._style_widget.widget.style_changed.connect(self._distribution_widget.apply_style)
        self._style_widget.widget.style_changed.connect(self._identifiability_widget.apply_style)
        self._style_widget.widget.style_changed.connect(self._sensitivity_widget.apply_style)

        # The summary under the tabs shows the samples of a sensitivity run while its tab is current.
        self._plot_tabs.currentChanged.connect(
            lambda _: self._summary_widget.show_samples(self._plot_tabs.currentWidget() is self._sensitivity_widget)
        )

        # Ensemble interaction: pick a different representative fit.
        self._summary_widget.representative_selected.connect(self._on_representative_selected)
        self._distribution_widget.representative_selected.connect(self._on_plot_fit_selected)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_data_loaded(self, ms: MeasurementSet) -> None:
        self._stop_fit()
        self._state.measurement_set = ms
        self._state.source_file = self._data_panel.current_path()
        self._emit_tab_title()
        self._state.held_fit_results = []
        self._preprocess_panel.set_measurement_set(ms)
        self._replica_panel.set_measurement_set(ms)
        self._summary_widget.set_replica_ids(ms.replica_ids)
        self._identifiability_widget.set_replica_ids(ms.replica_ids)
        self._clear_identifiability()
        self._clear_sensitivity()
        self._show_results(force=True)
        active = ms.n_active
        total = ms.n_replicas
        self.status_message.emit(f'Loaded: {ms.n_points} pts × {total} replicas — {active}/{total} active')

    def _on_data_cleared(self) -> None:
        self._stop_fit()
        self._state.measurement_set = None
        self._state.source_file = None
        self._emit_tab_title()
        self._state.held_fit_results = []
        self._replica_panel.clear()
        self._summary_widget.set_replica_ids(None)
        self._identifiability_widget.set_replica_ids(None)
        self._clear_identifiability()
        self._clear_sensitivity()
        self._show_results(force=True)

    def _on_preprocessing_applied(self) -> None:
        self._replica_panel.refresh()
        self._show_results(redraw=True)
        ms = self._state.measurement_set
        if ms:
            self.status_message.emit(f'Preprocessing applied — {ms.n_active}/{ms.n_replicas} replicas active')

    def _on_preprocessing_reset(self) -> None:
        self._replica_panel.refresh()
        self._show_results(redraw=True)
        self.status_message.emit('Replicas reset — all active')

    def _on_replicas_changed(self) -> None:
        self._show_results(redraw=True)

    def _on_assay_type_changed(self, assay_type: AssayType) -> None:
        self._state.assay_type = assay_type
        self._bounds_panel.set_assay_type(assay_type)
        meta = ASSAY_REGISTRY[assay_type]
        self._update_axis_labels(meta.x_label, meta.y_label, meta.y_unit)

    def _on_conditions_changed(self) -> None:
        self._state.conditions = self._assay_panel.current_conditions()

    def _on_config_changed(self) -> None:
        self._state.fit_config = self._fit_panel.current_config()

    def _on_bounds_changed(self) -> None:
        self._state.custom_bounds = self._bounds_panel.current_bounds()

    def _on_display_unit_changed(self, unit: str) -> None:
        """DataPanel announces a new plot-display unit — propagate to plot."""
        self._state.display_unit = unit
        self._style_widget.widget.set_x_unit(unit)

    def _on_fit_complete(self, result: FitResult) -> None:
        worker = self._fit_worker
        if self.sender() is not worker:
            return  # a fit whose data were replaced while it ran
        self._fit_worker = None
        self.actions_changed.emit()
        if not result.success:
            self._report_no_passing_fit(result)
            return

        # The fit is held, then shown or hidden by the selection as it is now.
        self._state.held_fit_results = [result]
        self._state.profile_result = None
        self._show_results(force=True)
        if profile_supported(AssayType[result.assay_type]):
            # Profile the replicates the fit used, so the tab describes the same data.
            ms = worker.ms.with_active(fit_replica_ids(result))
            # Until the profile arrives (well under a second) the tab says it is being computed.
            self._identifiability_widget.show_profile_pending(result, result.assay_type)
            self._profile_worker = ProfileWorker(ms, worker.assay_cls, worker.conditions, worker.config, parent=self)
            self._profile_worker.finished.connect(self._on_profile_complete)
            self._profile_worker.error.connect(self._on_profile_error)
            self._profile_worker.start()
        else:
            self._profile_worker = None
            self._identifiability_widget.update_fit(result, None, result.assay_type)

        per_replica = result.uncertainty_source == 'replicate'  # JSON-compat magic value
        n_fit = result.metadata.get('n_replicas_fit', result.n_passing)
        n_total = result.metadata.get('n_replicas_total', result.n_total)
        hidden = self._state.hidden_fit_notes.get(result.id)
        if hidden is not None:
            self.status_message.emit(f'Fit complete but hidden — {hidden}')
        elif per_replica:
            self.status_message.emit(
                f'Per-replica fit complete — R²={result.r_squared:.4f}, '
                f'RMSE={result.rmse:.4e}, {n_fit}/{n_total} replicas fit'
            )
        else:
            self.status_message.emit(
                f'Fit complete — R²={result.r_squared:.4f}, RMSE={result.rmse:.4e}, '
                f'{result.n_passing}/{result.n_total} trials passed'
            )

        failures = (result.metadata.get('replica_failures') or {}) if per_replica else {}
        if failures:
            names = {rid: describe_replicates([rid], worker.ms.replica_ids) for rid in failures}
            details = '\n'.join(f'  • {_capitalized(names[rid])}: {reason}' for rid, reason in failures.items())
            QMessageBox.warning(
                self,
                'Some Replicates Were Left Out',
                f'{len(failures)} of the {n_total} replicates could not be fitted, so the fit leaves them out:\n\n'
                f'{details}\n\nThe results describe the {n_fit} replicates that were fitted, and their R² and '
                'RMSE are measured against the average of those replicates.',
            )

    def _report_no_passing_fit(self, result: FitResult) -> None:
        """Report a fit where no trial cleared the quality floor it ran with.

        Clears the previous result so a stale curve is never left on screen
        looking like the outcome of this run.
        """
        self._state.held_fit_results = []
        self._clear_identifiability()
        self._show_results(force=True)

        floor = result.fit_config['min_r_squared']
        best = result.metadata.get('best_attempt_r_squared')
        closest = f'The closest attempt reached R² = {best:.4f}. ' if isinstance(best, float) else ''
        QMessageBox.warning(
            self,
            'No Fit Met the Quality Threshold',
            f'None of the {result.n_total} attempts reached the minimum R² of {floor:.2f}, '
            f'so there is no result to show. {closest}'
            'Try lowering Min R², increasing Trials, or widening the parameter bounds.',
        )
        self.status_message.emit('Fit failed — no trial met the quality threshold')

    def _on_fit_error(self, msg: str) -> None:
        if self.sender() is not self._fit_worker:
            return
        self._fit_worker = None
        self.actions_changed.emit()
        QMessageBox.warning(self, 'Fit Error', msg)
        self.status_message.emit(f'Fit failed: {msg}')

    def _stop_fit(self) -> None:
        """Discard a fit still running: its signals are disconnected, so its result is never shown."""
        worker = self._fit_worker
        if worker is None:
            return
        for signal in (worker.finished, worker.error):
            try:
                signal.disconnect()
            except TypeError:
                pass
        self._fit_worker = None
        self.actions_changed.emit()

    # ------------------------------------------------------------------
    # Identifiability (Ka profile)
    # ------------------------------------------------------------------

    def _on_profile_complete(self, profile: ProfileResult) -> None:
        if self.sender() is not self._profile_worker:
            return  # the fit this profile belongs to has been replaced
        self._state.profile_result = profile
        result = self._state.held_fit_results[-1]
        self._identifiability_widget.update_fit(result, profile, result.assay_type)

    def _on_profile_error(self, msg: str) -> None:
        if self.sender() is not self._profile_worker:
            return
        result = self._state.held_fit_results[-1]
        self._identifiability_widget.update_fit(result, None, result.assay_type)
        QMessageBox.warning(
            self, 'Identifiability', f'{msg}\n\nThe Identifiability tab shows the individual fit attempts only.'
        )

    def _clear_identifiability(self) -> None:
        """Empty the Identifiability tab and discard any Ka profile still being computed."""
        worker = self._profile_worker
        if worker is not None:
            for signal in (worker.finished, worker.error):
                try:
                    signal.disconnect()
                except TypeError:
                    pass
        self._profile_worker = None
        self._state.profile_result = None
        self._identifiability_widget.clear()

    # ------------------------------------------------------------------
    # Ka sensitivity analysis
    # ------------------------------------------------------------------

    def run_sensitivity(self) -> None:
        """Start a background Ka input-sensitivity run."""
        ms = self._state.measurement_set
        if ms is None:
            QMessageBox.warning(self, 'No Data', 'Load a measurement file first.')
            return

        if self._state.assay_type is AssayType.DYE_ALONE:
            QMessageBox.warning(
                self,
                'Sensitivity Analysis',
                'Dye-only measurements have no association constant to analyse. '
                'Pick a binding assay (GDA, IDA, or DBA) to run a sensitivity analysis.',
            )
            return

        sens_config = self._sensitivity_panel.current_config()
        if not sens_config.input_specs:
            QMessageBox.warning(
                self,
                'Sensitivity Analysis',
                'No input is set to vary. Set a ±% above zero for at least one input '
                '(the titrant or a concentration) so the analysis has something to perturb.',
            )
            return

        assay_cls = self._assay_panel.get_assay_class()
        conditions = self._assay_panel.current_conditions()
        fit_config = self._fit_panel.current_config()
        custom_bounds = self._bounds_panel.current_bounds()
        if custom_bounds:
            fit_config = replace(fit_config, custom_bounds=custom_bounds)

        resolved = resolve_fit_config(fit_config, sens_config)
        n_replicas = ms.n_active if resolved.per_replica else 1
        curve_fits = (estimated_fit_count(sens_config) + 1) * n_replicas
        if estimated_optimizer_runs(sens_config, resolved, n_replicas, assay_type=self._state.assay_type) > 20_000:
            reply = QMessageBox.question(
                self,
                'This Will Take a While',
                f'Your data will be re-fitted about {curve_fits:,} times to measure how much '
                f'the result moves.\n\nThat can take several minutes. You can stop it at any '
                f'point once it starts, and the progress bar will estimate the time left.\n\n'
                f'Start the analysis?',
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self._sensitivity_worker = SensitivityWorker(
            ms.with_active(ms.active_replica_ids),
            assay_cls,
            conditions,
            fit_config,
            sens_config,
            max_workers=preferences.worker_count(),
            parent=self,
        )
        self._sensitivity_worker.progress.connect(self._on_sensitivity_progress)
        self._sensitivity_worker.finished.connect(self._on_sensitivity_complete)
        self._sensitivity_worker.error.connect(self._on_sensitivity_error)

        self._sensitivity_started = time.monotonic()
        self._summary_widget.show_running(sens_config.mode)
        self._sensitivity_widget.show_running()
        self._sensitivity_panel.set_running(True)
        self._plot_tabs.setCurrentWidget(self._sensitivity_widget)
        self._sensitivity_worker.start()
        self.status_message.emit('Running sensitivity analysis…')

    def _on_sensitivity_progress(self, done: int, total: int) -> None:
        """Report progress, with a time estimate once there is enough to judge."""
        self._sensitivity_widget.set_progress(done, total)
        elapsed = time.monotonic() - self._sensitivity_started
        if 3 <= done < total and elapsed > 0:
            remaining = elapsed / done * (total - done)
            self.status_message.emit(f'Analysing — {done} of {total}, about {_format_remaining(remaining)} left')
        else:
            self.status_message.emit(f'Analysing — {done} of {total}')

    def _on_sensitivity_complete(self, result) -> None:
        self._state.sensitivity_result = result
        # Shown or hidden by the selection as it is now, before any tab draws it.
        self._show_results()
        self._sensitivity_widget.update_result(result)
        self._summary_widget.set_sensitivity(result)
        self._identifiability_widget.update_sensitivity(result)
        self._sensitivity_panel.set_running(False)
        if self._sensitivity_worker is not None and self._sensitivity_worker.cancelled:
            self.status_message.emit(
                f'Sensitivity stopped — {result.n_success}/{result.n_total} fits succeeded before you cancelled'
            )
        else:
            self.status_message.emit(f'Sensitivity complete — {result.n_success}/{result.n_total} fits succeeded')

    def _on_sensitivity_error(self, msg: str) -> None:
        # Take the tab off the progress page: back to what it showed before the run.
        previous = self._state.sensitivity_result
        if previous is None:
            self._sensitivity_widget.clear()
        else:
            self._sensitivity_widget.update_result(previous)
        self._summary_widget.set_sensitivity(previous)
        QMessageBox.warning(self, 'Sensitivity Analysis', msg)
        self._sensitivity_panel.set_running(False)
        self.status_message.emit(f'Sensitivity failed: {msg}')

    def _clear_sensitivity(self) -> None:
        """Drop the sensitivity result from the Ka Sensitivity tab and the summary, and stop a run still going.

        The stopped run's signals are disconnected first, so its result never
        reaches data it was not computed on.
        """
        worker = self._sensitivity_worker
        if worker is not None:
            for signal in (worker.progress, worker.finished, worker.error):
                try:
                    signal.disconnect()
                except TypeError:
                    pass
            worker.cancel()
        self._sensitivity_worker = None
        self._state.sensitivity_result = None
        self._state.sensitivity_note = None
        self._sync_notes()
        self._sensitivity_widget.clear()
        self._sensitivity_panel.set_running(False)
        self._summary_widget.set_sensitivity(None)

    def _cancel_sensitivity(self) -> None:
        if self._sensitivity_worker is not None:
            self._sensitivity_worker.cancel()
            self.status_message.emit('Cancelling…')

    def _on_plot_fit_selected(self, index: int) -> None:
        """A fit picked by clicking a distribution point: remember it as the
        sticky 'Selected' choice, then report it as the representative."""
        if self._state.measurement_set is None or not self._state.fit_results:
            return  # picks need the data the fit was made on, and a shown fit
        self._summary_widget.note_plot_selection(index)
        self._on_representative_selected(index)

    def _on_representative_selected(self, index: int) -> None:
        """Report a different valid fit as the representative (from the
        Representative selector or a distribution-plot click).

        The pick is scored on the fit's own record, so its RMSE and R² are the
        ones its pool records, whatever is active or entered now.
        """
        ms = self._state.measurement_set
        results = self._state.fit_results
        if ms is None or not results:
            return
        result = results[-1]
        if result.parameter_samples is None:
            return
        select_representative(result, scoring_assay(ms, result), index)
        self._refresh_plot()
        self._summary_widget.update_result(result)
        self._distribution_widget.update_result(result, self._replica_order())

    # ------------------------------------------------------------------
    # Showing and hiding results
    # ------------------------------------------------------------------

    def _mismatch_note(self, result: FitResult | None, what: str, redo: str) -> str | None:
        """Why *result* does not describe the loaded selection, as a short plain note; ``None`` when it does.

        The one match test for every result the session holds. *result*
        matches when it was made on the loaded data (the same
        ``data_fingerprint``), every replicate it used is active and every
        active replicate was given to it, its conditions equal the entered ones
        by value (a unit switch changes nothing), and its assay type is the one
        selected. The note names what differs and how to undo it. *what* names
        the result ("fit") and *redo* how to make a new one ("run the fit
        again"). With no data loaded only the assay type and the conditions
        can be compared.
        """
        ms = self._state.measurement_set
        made = f'This {what} was made'
        changes: list[str] = []
        fixes: list[str] = []
        if result is None or ms is not None:
            recorded = None if result is None else result.metadata.get('data_fingerprint')
            if recorded is None:
                return (
                    f'This {what} does not record the data it was made on, so it cannot be shown. {_capitalized(redo)}.'
                )
            if recorded != ms.fingerprint():
                return f'This {what} was made on other data than the data loaded now. {_capitalized(redo)}.'
            used, given = fit_replica_ids(result), input_replica_ids(result)
            if used is None or given is None:
                return (
                    f'This {what} does not record which replicates it was made on, so it cannot be shown. '
                    f'{_capitalized(redo)}.'
                )

            order, active = ms.replica_ids, ms.active_replica_ids
            made += f' on {describe_replicates(used, order)}'
            for ids, state, fix in (
                ([rid for rid in used if rid not in active], 'off', 'back on'),
                ([rid for rid in active if rid not in given], 'on', 'off'),
            ):
                if ids:
                    many = len(ids) > 1
                    changes.append(f'{describe_replicates(ids, order)} {"are" if many else "is"} now {state}')
                    fixes.append(f'switch {"them" if many else "it"} {fix}')

        panel = self._assay_panel
        assay_type = panel.current_assay_type()
        if result.assay_type != assay_type.name:
            theirs = ASSAY_REGISTRY[AssayType[result.assay_type]].display_name
            made += f' for {theirs}'
            changes.append(f'the assay is now {ASSAY_REGISTRY[assay_type].display_name}')
            fixes.append(f'switch the assay back to {theirs}')
        else:
            entered = panel.current_conditions()
            if not same_inputs(result.conditions, entered):
                keys = [
                    key
                    for key, value in result.conditions.items()
                    if key in entered
                    and panel.condition_name(key) is not None
                    and not same_inputs({key: value}, {key: entered[key]})
                ]
                if keys:
                    stored = {key: panel.format_condition(key, result.conditions[key]) for key in keys}
                    made += ' with ' + and_join([f'{panel.condition_name(key)} = {stored[key]}' for key in keys])
                    changes += [
                        f'{panel.condition_name(key)} is now {panel.format_condition(key, entered[key])}'
                        for key in keys
                    ]
                    fixes.append(f'set it back to {stored[keys[0]]}' if len(keys) == 1 else 'set them back')
                else:
                    changes.append('the assay conditions entered now differ from its own')
                    fixes.append('enter its conditions again')

        if not changes:
            return None
        fix = fixes[0] if len(fixes) == 1 else 'change these back'
        return f'{made}. {_capitalized(and_join(changes))}. {_capitalized(fix)}, or {redo}.'

    def _show_results(self, *, redraw: bool = False, force: bool = False) -> None:
        """Show every held result whose record matches the loaded selection, and hide the rest behind a note.

        Runs after each change to the selection: a replicate switched on or
        off, Outlier Removal, a finished edit of the conditions or a new assay
        type. No number is recomputed: a hidden result is shown again exactly
        as it was. The tabs are redrawn only when a result is shown or hidden;
        *redraw* also redraws the Fit Curve, for a change to its points, and
        *force* redraws every tab, for new results.
        """
        state = self._state
        notes: dict[str, str] = {}
        for result in state.held_fit_results:
            note = self._mismatch_note(result, 'fit', 'run the fit again')
            if note is not None:
                notes[result.id] = note
        sensitivity_note = None
        if state.sensitivity_result is not None:
            sensitivity_note = self._mismatch_note(
                state.sensitivity_result.baseline_fit, 'sensitivity analysis', 'run the analysis again'
            )
        changed = notes != state.hidden_fit_notes or sensitivity_note != state.sensitivity_note
        state.hidden_fit_notes = notes
        state.sensitivity_note = sensitivity_note
        self._sync_notes()
        if changed or force:
            self._render_results(force=force)
        elif redraw:
            self._refresh_plot()

    def _fit_view(self) -> tuple[FitResult | None, str | None]:
        """The fit the summary and Distributions describe, and the note hiding it (``None`` while it is shown).

        The latest shown fit, or the latest held fit when every one is hidden.
        """
        shown = self._state.fit_results
        if shown:
            return shown[-1], None
        held = self._state.held_fit_results
        return (held[-1], self._state.hidden_fit_notes[held[-1].id]) if held else (None, None)

    def _sync_notes(self) -> None:
        """Give the summary, Identifiability and Ka Sensitivity the notes that hide their results."""
        state = self._state
        _, fit_note = self._fit_view()
        held = state.held_fit_results
        profiled_note = state.hidden_fit_notes.get(held[-1].id) if held else None
        self._summary_widget.show_mismatch(fit_note, state.sensitivity_note)
        self._identifiability_widget.show_mismatch(profiled_note, state.sensitivity_note)
        self._sensitivity_widget.show_mismatch(state.sensitivity_note)

    def _render_results(self, *, force: bool = False) -> None:
        """Put the held fit results on the Fit Curve, the summary and Distributions, shown or hidden.

        *force* redraws Distributions even for a hidden fit, for new results.
        """
        fit, note = self._fit_view()
        self._refresh_plot()
        if fit is None:
            self._summary_widget.clear()
            self._distribution_widget.clear()
        else:
            unchecked = _UNCHECKED_NOTE if self._state.measurement_set is None else None
            self._summary_widget.update_result(fit, unchecked=unchecked)
            # A hidden fit's plots are redrawn from the stored result when it is shown again.
            self._distribution_widget.show_mismatch(note)
            if force or note is None:
                self._distribution_widget.update_result(fit, self._replica_order())
        self.actions_changed.emit()

    def _refresh_plot(self) -> None:
        """Draw the loaded points with the curves of the shown fits, and say which held fits are hidden.

        When every held fit is hidden, the note of the latest one replaces the
        fits; when only some are, the shown curves stay and a note names the
        hidden ones. With no data loaded only the shown curves are drawn.
        The axes are labelled for the assay type of the fit the summary
        reports, or of the selected assay when none is shown.
        """
        state = self._state
        ms = state.measurement_set
        shown = state.fit_results
        if ms is None and not state.held_fit_results:
            return
        assay_type = AssayType[shown[-1].assay_type] if shown else self._assay_panel.current_assay_type()
        meta = ASSAY_REGISTRY[assay_type]
        if ms is not None:
            plot_data = prepare_plot_data(ms, shown, show_dropped=True)
        else:
            plot_data = {
                'concentrations': state.held_fit_results[-1].x_fit.magnitude,
                'active_replicas': [],
                'dropped_replicas': [],
                'average': None,
                'fits': [{'x': r.x_fit.magnitude, 'y': r.y_fit.magnitude, 'label': 'Fit', 'id': r.id} for r in shown],
            }
        self._plot_widget.update_plot(plot_data, x_label=meta.x_label, y_label=meta.y_label, y_unit=meta.y_unit)
        self._plot_widget.set_fit_results(shown)
        self._set_plot_note(self.hidden_results_note())
        self._plot_widget.show_hidden_results(self._other_hidden_note())

    def _other_hidden_note(self) -> str | None:
        """A note naming the held fits that are hidden while others are shown; ``None`` otherwise."""
        state = self._state
        hidden = [r for r in state.held_fit_results if r.id in state.hidden_fit_notes]
        if not state.fit_results or not hidden:
            return None
        n = len(hidden)
        head = f'{n} of the {len(state.held_fit_results)} fits {"is" if n == 1 else "are"} hidden and not drawn.'
        latest = self._mismatch_note(hidden[-1], 'hidden fit' if n == 1 else 'latest hidden fit', 'run the fit again')
        return f'{head} {latest}'

    def _set_plot_note(self, note: str | None) -> None:
        """Hide the Fit Curve's fit behind *note*, or show it with ``None``; the plot redraws only on a change."""
        if note != self._plot_note:
            self._plot_note = note
            self._plot_widget.show_mismatch(note)

    def _update_axis_labels(self, x: str, y: str, y_unit: str) -> None:
        self._plot_widget.set_axis_labels(x, y, y_unit)


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
