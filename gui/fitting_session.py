"""FittingSession — one complete fitting workspace (one tab)."""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
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
from core.io.formats.bmg_reader import BMG_PLACEHOLDER_KEY
from core.pipeline.diagnostics import Verdict
from core.pipeline.fit_pipeline import (
    FitConfig,
    FitResult,
    fit_replica_ids,
    input_replica_ids,
    parameters_on_bound,
    verify_imported_result,
)
from core.pipeline.inputs import TITRANT_STOCK, ErrorModel, source_name
from core.pipeline.profile import ProfileSet
from core.pipeline.sensitivity import (
    LONG_RUN_SOLVES,
    SensitivityMode,
    SensitivityResult,
    estimated_fit_count,
    estimated_model_solves,
)
from core.pipeline.varpro import projectable
from core.units import Q_, Quantity
from gui import plot_guide, preferences
from gui.app_state import SessionState
from gui.dialogs.plot_guide_dialog import show_plot_guide
from gui.plotting.colors import INK, INK_2, INK_3
from gui.plotting.fit_summary_widget import FitSummaryWidget, same_inputs
from gui.plotting.identifiability_widget import IdentifiabilityWidget
from gui.plotting.labels import and_join, fmt_bound_note, fmt_r2, fmt_sci, fmt_unit_pretty
from gui.plotting.plot_style import PlotStyleWidget
from gui.plotting.plot_widget import PlotWidget
from gui.plotting.sensitivity_widget import STOPPING_TEXT, SensitivityWidget
from gui.widgets.assay_conditions import result_input_labels
from gui.widgets.assay_config_panel import AssayConfigPanel
from gui.widgets.bounds_panel import BoundsPanel
from gui.widgets.data_panel import DataPanel
from gui.widgets.fit_config_panel import FitConfigPanel
from gui.widgets.flat_tabs import FlatTabWidget
from gui.widgets.info_button import InfoGroupBox
from gui.widgets.input_uncertainty_panel import InputUncertaintyPanel
from gui.widgets.preprocessing_panel import PreprocessingPanel
from gui.widgets.replica_panel import ReplicaPanel, describe_replicates
from gui.widgets.sensitivity_panel import SensitivityPanel
from gui.workers import FitWorker, ProfileWorker, SensitivityWorker, retire

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

logger = logging.getLogger(__name__)

_DEMO_IDA_PATH = Path(__file__).parent.parent / 'data' / 'IDA_system.txt'

_UNCHECKED_NOTE = (
    'No data are loaded, so these numbers are shown as stored in the file and could not be checked against '
    'the data. To check them, load the data first and import the results again.'
)
_FIT_RUNNING_NOTE = (
    'A fit is already running in this session. Wait for it to finish, or stop it with Cancel Fit, '
    'then run the fit again.'
)
_SENSITIVITY_RUNNING_NOTE = (
    'A sensitivity analysis is running in this session. Wait for it to finish, or stop it, then run the fit.'
)
_FIT_RUNNING_ANALYSIS_NOTE = (
    'A fit is running in this session. Wait for it to finish, or stop it with Cancel Fit, '
    'then run the sensitivity analysis.'
)
_SENSITIVITY_RUNNING_ANALYSIS_NOTE = (
    'A sensitivity analysis is already running in this session. Wait for it to finish, or stop it, '
    'then run the analysis again.'
)
_RESULTS_HIDDEN_NOTE = 'Results hidden — they do not describe the data and settings loaded now.'

#: Said of a fit whose reported interval was worked out from other input
#: uncertainties than the ones set now, which is what the interval accounts for.
#: Both ways back are offered: the uncertainties of an imported fit are set
#: under the panel like its conditions, and a fit made here is run again. The
#: fit's own record fills ``{stated}``, so what to set back is named and not
#: only pointed at, as the conditions a fit was made with are.
_INPUTS_CHANGED_NOTE = (
    'This fit was made with {stated}. The input uncertainties set now differ: set them back under Input '
    'Uncertainty, or fit again to update the interval.'
)

#: Read for ``{stated}`` of a fit that was made with every input taken as exact.
_NO_UNCERTAINTY_STATED = 'every input taken as exact'

#: Said when the titrant stock entered is no more concentrated than the titrant
#: concentrations measured. The panel cannot make this check — it is the one
#: that needs the loaded data — and the assay refuses the same thing with the
#: same sentence once a fit reaches it.
_STOCK_BELOW_DATA = (
    'The titrant stock ({stock}) must be more concentrated than the highest titrant concentration in the data '
    '({highest}): a sample cannot hold more titrant than the stock it was made from. Check the stock '
    'concentration and its unit.'
)

#: Said instead where the two concentrations read alike in the unit the form
#: shows — the stock equals the highest titrant concentration, or is above it by
#: less than the figures shown. Naming one number twice would read as a value
#: having to be more concentrated than itself.
_STOCK_NOT_ABOVE_DATA = (
    'The titrant stock is no more concentrated than the highest titrant concentration in the data ({highest}): '
    'a sample cannot hold more titrant than the stock it was made from. Check the stock concentration and its unit.'
)

#: Said of a sensitivity analysis drawn from other input uncertainties than the
#: ones set now. They are what the analysis samples, so the spread it reports
#: and a heatmap's axes are entirely a function of them.
_SENSITIVITY_INPUTS_NOTE = (
    'The input uncertainties have changed since this analysis; set them back under Input Uncertainty, or run '
    'the analysis again.'
)

#: What the fit's diagnostics say, in the few words the status bar has room for.
#: The sentence in full — with the test statistics, the shifts and what to do —
#: is in the summary block under the plot and in the exported report.
#:
#: A rejected model is named by what the test measured rather than by the
#: conclusion it leads to: replicates that scatter little make the test powerful
#: enough to reject a curve that follows the data closely, and beside the R² on
#: the same line the conclusion alone reads as a failure of the app.
_VERDICT_NOTE = {
    Verdict.CONSISTENT: 'the model and the entered inputs describe the data',
    Verdict.INPUTS_EXPLAIN: 'the data fit once the inputs move within their uncertainties',
    Verdict.INPUTS_CONFLICT: 'the inputs together are further from their entered values than you stated',
    Verdict.MODEL_INADEQUATE: 'the curve misses the data by more than their scatter allows',
}

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


def _stated_as(result: FitResult) -> str:
    """What *result* was told about its inputs and about what they share, read back from its own record.

    Each source named and valued as the Input Uncertainty panel writes it — an
    input's own uncertainty and, after them, the ones several inputs share — so
    a note about a fit made with other uncertainties says which ones they were
    and they can be set back without opening the file.
    """
    from gui.session import stated_uncertainty

    sources = ErrorModel.from_dict(result.fit_config).source_specs()
    if not sources:
        return _NO_UNCERTAINTY_STATED
    labels = result_input_labels(result.assay_type, result.fit_config)
    stated = []
    for key, spec in sources.items():
        value = (result.conditions or {}).get(key)
        unit = fmt_unit_pretty(str(value.units)) if isinstance(value, Quantity) else ''
        # A shared source is named with the inputs it moves, which only the
        # labels of this fit's own record carry; source_name answers for a
        # result whose assay this version does not know.
        name = labels.get(key) or source_name(key, labels)
        stated.append(f'{name} {stated_uncertainty(spec, unit)}')
    return and_join(stated)


def _verdict_note(result: FitResult) -> str:
    """What the fit's diagnostics say in a few words, for the status bar; ``''`` for a fit that has none.

    A fit of an assay with no association constant, and a result read from a
    file written before the diagnostics existed, carry no verdict.
    """
    diagnostics = result.diagnostics
    return '' if diagnostics is None else _VERDICT_NOTE[diagnostics.verdict]


class FittingSession(QWidget):
    """One complete fitting workflow: data → preprocess → configure → fit → visualize.

    Each tab in the main window is one FittingSession.  All state is stored in
    :class:`SessionState`; widgets communicate via Qt signals coordinated here.

    A result stays on screen only while the loaded selection matches the
    record it was made on (:meth:`_mismatch_note` is the one test, joined for
    a sensitivity run by :meth:`_sensitivity_inputs_note`). After
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
        have changed, so the window can set its fit action — Run Fit, or
        Cancel Fit while one runs here — and the result exports.
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
        # The uncertainties as the panel last stated them, so a row that
        # reports itself without changing them leaves the results alone.
        self._stated_errors = ErrorModel()
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

    def sensitivity_running(self) -> bool:
        """Whether a sensitivity analysis started in this session is still running."""
        return self._sensitivity_worker is not None

    def busy_note(self) -> str | None:
        """Why the fit cannot start now — the work already running here — or ``None`` when it can.

        One analysis at a time per session: the two share the machine's
        processors, and each is reported against the inputs set while it ran.
        """
        if self.fit_running():
            return _FIT_RUNNING_NOTE
        if self.sensitivity_running():
            return _SENSITIVITY_RUNNING_NOTE
        return None

    def running_work(self) -> str:
        """What this session has running, named for a message, or ``''`` when nothing is."""
        running = ('fit', self.fit_running()), ('sensitivity analysis', self.sensitivity_running())
        return ' and '.join(name for name, is_running in running if is_running)

    def plot_export_note(self) -> str | None:
        """Why the plot on the tab on screen cannot be saved — or ``None`` when it can."""
        widget = self._plot_tabs.currentWidget()
        state = self._state
        if widget is self._plot_widget:
            if state.measurement_set is None and not state.fit_results:
                return 'There is nothing on the Fit Curve tab yet. Load a measurement file, then save it.'
            return None
        if widget is self._identifiability_widget:
            if not self._identifiability_widget.has_chart():
                return 'There is no identifiability chart to save yet. Run a fit, then save it.'
            return self._fit_view()[1]
        if state.sensitivity_result is None:
            return 'There is no sensitivity analysis to save yet. Run one, then save it.'
        return state.sensitivity_note

    def hidden_results_note(self) -> str | None:
        """Why result exports and picks are unavailable: the note of the latest fit when every held fit is hidden.

        ``None`` while any result is shown, or when none is held: exports and
        picks then act on the shown results only.
        """
        return self._fit_view()[1]

    def cancel_running(self) -> None:
        """Ask every background run this session started to stop, without waiting for any of it.

        Each run ends at its next cancel check, so asking all of them first
        lets them stop side by side; waiting for one before asking the next
        would add up their stopping times on the interface thread.
        """
        for worker in (self._fit_worker, self._profile_worker, self._sensitivity_worker):
            if worker is not None:
                worker.cancel()

    def cancel_fit(self) -> None:
        """Stop the fit running in this session, leaving the tab as it was before it started.

        A cancelled fit reports nothing, so whatever the tabs showed — the
        previous fit and its Ka profile, where there was one — still stands,
        and the next fit can start as soon as this one has stopped.
        """
        if self._fit_worker is None:
            return
        self._stop_fit()
        self.status_message.emit('Fit cancelled — nothing on the tab was changed.')

    def shutdown(self) -> None:
        """Stop every background run this session started and wait for its thread to end.

        Called before the tab or the window closes.
        """
        self.cancel_running()
        self._stop_fit()
        self._stop_profile()
        self._stop_sensitivity()

    def _assay_problems(self, ms: MeasurementSet) -> list[str]:
        """Why the assay as configured cannot describe the loaded data, one sentence per problem; empty when it can.

        The Assay Configuration panel's own checks, and the one that needs the
        data: a sample cannot hold more titrant than the stock it was made
        from, so the stock has to be more concentrated than every titrant
        concentration measured. A stock that has not been entered at all is
        already the panel's first sentence, so it is not measured against the
        data as well.
        """
        panel = self._assay_panel
        problems = panel.problems()
        stock = panel.current_conditions().get(TITRANT_STOCK)
        if stock is None or not stock.magnitude > 0:
            return problems
        concentrations = np.asarray(ms.concentrations, dtype=float)
        finite = concentrations[np.isfinite(concentrations)]
        if finite.size and float(finite.max()) >= stock.magnitude:
            entered = panel.format_condition(TITRANT_STOCK, stock)
            highest = panel.format_condition(TITRANT_STOCK, Q_(float(finite.max()), 'M'))
            problems.append(
                _STOCK_NOT_ABOVE_DATA.format(highest=highest)
                if entered == highest
                else _STOCK_BELOW_DATA.format(stock=entered, highest=highest)
            )
        return problems

    def run_fit(self) -> None:
        """Start a background fitting run on a copy of the loaded data, so later changes never reach it."""
        ms = self._state.measurement_set
        if ms is None:
            QMessageBox.warning(self, 'No Data', 'Load a measurement file first.')
            return
        busy = self.busy_note()
        if busy is not None:
            QMessageBox.warning(self, 'Already Running', busy)
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

        assay_problems = self._assay_problems(ms)
        if assay_problems:
            QMessageBox.warning(
                self,
                'Assay Configuration',
                'The fit cannot start:\n\n' + '\n'.join(f'• {problem}' for problem in assay_problems),
            )
            return

        bound_problems = self._bounds_panel.problems()
        if bound_problems:
            QMessageBox.warning(
                self,
                'Parameter Bounds',
                'The fit cannot start:\n\n' + '\n'.join(f'• {problem}' for problem in bound_problems),
            )
            return

        input_problems = self._input_panel.problems()
        if input_problems:
            QMessageBox.warning(
                self,
                'Input Uncertainty',
                'The fit cannot start:\n\n' + '\n'.join(f'• {problem}' for problem in input_problems),
            )
            return

        assay_cls = self._assay_panel.get_assay_class()
        conditions = self._assay_panel.current_conditions()
        config = self._fit_panel.current_config()
        custom_bounds = self._bounds_panel.current_bounds()
        if custom_bounds:
            config = replace(config, custom_bounds=custom_bounds)
        # The uncertainties widen the reported interval to cover them; a fit
        # that cannot be made with the inputs as free as they were stated to be
        # names them in its refusal the way the panel names them. The random
        # error of each addition is scatter the fit's own residuals already
        # measure, so it is left out here (``for_fit``) and a change to it never
        # puts a fit out of date.
        config = replace(
            config,
            errors=self._input_panel.current_errors().for_fit(),
            input_labels=self._input_panel.input_labels(),
        )

        if config.per_replica and ms.n_active < 3:
            # The shared-Ka test needs three replicates to name one of them as
            # the odd one out; with fewer, every active replicate is averaged.
            self.status_message.emit(
                f'Fitting {ms.n_active} replicate(s) — the replicates cannot be tested against each other '
                'with fewer than three, so all of them are used.'
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

        Resets the assay, the parameter bounds, the input uncertainties and the
        fit configuration to the IDA defaults first, so the run starts from the
        same settings whatever the session held before: every input is taken as
        exact and the interval is the one conditional on the demo's conditions.
        """
        if not _DEMO_IDA_PATH.exists():
            QMessageBox.warning(self, 'Demo Data Missing', f'Could not find:\n{_DEMO_IDA_PATH}')
            return
        busy = self.busy_note()
        if busy is not None:
            QMessageBox.warning(self, 'Already Running', busy)
            return

        # 1. Reset all panels to IDA defaults
        self._assay_panel.set_assay_type(AssayType.IDA)
        self._bounds_panel.reset_to_defaults()
        self._input_panel.reset_to_defaults()
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
        with a note that they could not be checked.
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
        rescored = recomputed = False
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
            # A file that records no arithmetic and had its numbers rebuilt was measured again
            # with the present equilibrium solution, whichever reason named the status.
            recomputed = recomputed or (
                status in ('rescored_precision', 'rescored_legacy') and 'model_arithmetic' not in result.metadata
            )
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
            notices.append(
                f'Some numbers stored in {name} did not describe the replicates each fit used, so the R², RMSE and '
                'curve were recomputed on those replicates.'
            )
        if recomputed:
            notices.append(
                f'{name} was written by an earlier version of SupraSimFit. Its R², RMSE and fit curve were '
                'computed again with the equilibrium solution this version uses. The fitted values are unchanged.'
            )
        if notices:
            QMessageBox.information(self, 'Imported Results', '\n\n'.join(notices))

    def export_plot(self) -> None:
        """Save the plot on the tab that is showing.

        The Fit Curve tab offers PNG or SVG. The Identifiability and Ka
        Sensitivity tabs are saved whole, as one picture, which only PNG can
        carry: see :func:`~gui.plotting.export.export_widget`.
        """
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
        except ValueError as exc:
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
        self.status_message.emit(f'Plot saved to {path}')

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
        self._bounds_panel.set_assay_type(self._state.assay_type)
        self._input_panel.set_assay_type(self._state.assay_type)
        self._sensitivity_panel.set_assay_type(self._state.assay_type)
        self._name_inputs()
        self._on_conditions_changed()

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

        # The uncertainties are what a fit's interval accounts for, so a change
        # to them puts the fit on screen out of date with the panel.
        self._input_panel.specs_changed.connect(self._on_input_specs_changed)

        self._fit_panel.config_changed.connect(self._on_config_changed)

        self._bounds_panel.bounds_changed.connect(self._on_bounds_changed)

        self._sensitivity_panel.run_requested.connect(self.run_sensitivity)
        # Cancel is offered in two places: the sidebar panel and the running tab.
        self._sensitivity_panel.cancel_requested.connect(self._cancel_sensitivity)
        self._sensitivity_widget.cancel_requested.connect(self._cancel_sensitivity)

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
            lambda: self._input_panel.set_running(self.fit_running() or self.sensitivity_running())
        )

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_data_loaded(self, ms: MeasurementSet) -> None:
        # Both describe the data being replaced, so neither can be left running.
        stopped = self.running_work()
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
        loaded = f'Loaded: {ms.n_points} pts × {total} replicates — {active}/{total} active'
        self.status_message.emit(f'{loaded} — the running {stopped} was stopped' if stopped else loaded)

    def _on_data_cleared(self) -> None:
        stopped = self.running_work()
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
        if stopped:
            self.status_message.emit(f'Data cleared — the running {stopped} was stopped')

    def _on_preprocessing_applied(self) -> None:
        self._replica_panel.refresh()
        self._show_results(redraw=True)
        ms = self._state.measurement_set
        if ms:
            self.status_message.emit(f'Outlier removal applied — {ms.n_active}/{ms.n_replicas} replicates active')

    def _on_preprocessing_reset(self) -> None:
        self._replica_panel.refresh()
        self._show_results(redraw=True)
        self.status_message.emit('Replicates reset — all active')

    def _on_replicas_changed(self) -> None:
        self._show_results(redraw=True)

    def _on_assay_type_changed(self, assay_type: AssayType) -> None:
        self._state.assay_type = assay_type
        self._bounds_panel.set_assay_type(assay_type)
        # The new assay has its own inputs: the uncertainty rows are rebuilt for
        # them first, and the heatmap axes then offer exactly those inputs.
        self._input_panel.set_assay_type(assay_type)
        self._name_inputs()
        meta = ASSAY_REGISTRY[assay_type]
        self._update_axis_labels(meta.x_label, meta.y_label, meta.y_unit)

    def _on_input_specs_changed(self) -> None:
        """Check the results against the error sources again, once the sources themselves have changed.

        The panel reports itself whenever a row is touched, which includes a
        set value arriving from the conditions form as it is typed. Only a
        change to what the panel states can put a result out of date, so the
        results are left alone until one happens.
        """
        stated = self._input_panel.current_errors()
        if stated != self._stated_errors:
            self._stated_errors = stated
            self._show_results()

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
        retire(worker)
        self.actions_changed.emit()

        # The fit is held, then shown or hidden by the selection as it is now.
        self._state.held_fit_results = [result]
        self._state.profile_result = None
        self._show_results(force=True)
        # The previous fit's profile describes data this one replaces, and only
        # one profile worker is reachable at a time: drop it through the one
        # path that sees its thread out.
        self._stop_profile()
        if projectable(AssayType[result.assay_type]):
            # Profile the replicates the fit used, so the tab describes the same data.
            ms = worker.ms.with_active(fit_replica_ids(result))
            # Until the profiles arrive the tab says they are being computed.
            self._identifiability_widget.show_profile_pending(result, result.assay_type)
            # The fit already worked out the penalised profiles behind its
            # interval: the tab draws those, rather than computing them again.
            self._profile_worker = ProfileWorker(
                ms, worker.assay_cls, worker.conditions, worker.config, result.aware, parent=self
            )
            self._profile_worker.finished.connect(self._on_profile_complete)
            self._profile_worker.error.connect(self._on_profile_error)
            self._profile_worker.start()
        else:
            self._identifiability_widget.update_fit(result, None, result.assay_type)

        left_out = self._left_out_text(result, worker.ms.replica_ids)
        hidden = self._state.hidden_fit_notes.get(result.id)
        if hidden is not None:
            self.status_message.emit(f'Fit complete but hidden — {hidden}')
        else:
            used = fit_replica_ids(result) or []
            given = input_replica_ids(result) or used
            counted = f', {len(used)} of {len(given)} replicates used' if given else ''
            on_bound = fmt_bound_note(parameters_on_bound(result))
            verdict = _verdict_note(result)
            self.status_message.emit(
                f'Fit complete — R²={fmt_r2(result.r_squared)}, RMSE={fmt_sci(result.rmse)}{counted}'
                f'{f" ({left_out})" if left_out else ""}{f" — {on_bound}" if on_bound else ""}'
                f'{f" — {verdict}" if verdict else ""}'
            )

    @staticmethod
    def _left_out_text(result: FitResult, replica_ids) -> str:
        """The replicates the fit left out and why, named as the sidebar names them; ``''`` when it used every one."""
        failures = result.metadata.get('replica_failures') or {}
        if not failures:
            return ''
        return '; '.join(
            f'{_capitalized(describe_replicates([rid], replica_ids))} left out: {reason}'
            for rid, reason in failures.items()
        )

    def _on_fit_error(self, msg: str) -> None:
        worker = self._fit_worker
        if self.sender() is not worker:
            return
        self._fit_worker = None
        retire(worker)
        self.actions_changed.emit()
        QMessageBox.warning(self, 'Fit Error', msg)
        self.status_message.emit(f'Fit failed: {msg}')

    def _stop_fit(self) -> None:
        """Stop a fit still running and wait for it, so its result is never shown and its thread is gone."""
        worker = self._fit_worker
        if worker is None:
            return
        self._fit_worker = None
        worker.cancel()
        retire(worker)
        self.actions_changed.emit()

    def _stop_profile(self) -> None:
        """Stop the Ka profile still being computed and see its thread out."""
        worker = self._profile_worker
        if worker is None:
            return
        self._profile_worker = None
        worker.cancel()
        retire(worker)

    def _stop_sensitivity(self) -> None:
        """Stop a sensitivity run still going and wait for it, which also ends its worker processes."""
        worker = self._sensitivity_worker
        if worker is None:
            return
        self._sensitivity_worker = None
        worker.cancel()
        retire(worker)
        self._sensitivity_panel.set_running(False)
        self.actions_changed.emit()

    # ------------------------------------------------------------------
    # Identifiability (Ka profile)
    # ------------------------------------------------------------------

    def _on_profile_complete(self, profile: ProfileSet) -> None:
        worker = self._profile_worker
        if self.sender() is not worker:
            return  # the fit this profile belongs to has been replaced
        self._profile_worker = None
        retire(worker)
        self._state.profile_result = profile
        result = self._state.held_fit_results[-1]
        self._identifiability_widget.update_fit(result, profile, result.assay_type)

    def _on_profile_error(self, msg: str) -> None:
        worker = self._profile_worker
        if self.sender() is not worker:
            return
        self._profile_worker = None
        retire(worker)
        result = self._state.held_fit_results[-1]
        self._identifiability_widget.update_fit(result, None, result.assay_type)
        QMessageBox.warning(self, 'Identifiability', f'{msg}\n\nThe fit itself is unaffected and is still shown.')

    def _clear_identifiability(self) -> None:
        """Empty the Identifiability tab and stop any Ka profile still being computed."""
        self._stop_profile()
        self._state.profile_result = None
        self._identifiability_widget.clear()

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
        """Start a background Ka input-sensitivity run."""
        ms = self._state.measurement_set
        if ms is None:
            QMessageBox.warning(self, 'No Data', 'Load a measurement file first.')
            return
        if self.fit_running():
            QMessageBox.warning(self, 'Already Running', _FIT_RUNNING_ANALYSIS_NOTE)
            return
        if self.sensitivity_running():
            QMessageBox.warning(self, 'Already Running', _SENSITIVITY_RUNNING_ANALYSIS_NOTE)
            return

        if not projectable(self._state.assay_type):
            QMessageBox.warning(
                self,
                'Sensitivity Analysis',
                'The selected assay has no association constant for the analysis to follow. '
                'Pick a binding assay to run a sensitivity analysis.',
            )
            return

        assay_problems = self._assay_problems(ms)
        if assay_problems:
            QMessageBox.warning(
                self,
                'Assay Configuration',
                'The analysis cannot start:\n\n' + '\n'.join(f'• {problem}' for problem in assay_problems),
            )
            return

        input_problems = self._input_panel.problems()
        if input_problems:
            QMessageBox.warning(
                self,
                'Input Uncertainty',
                'The analysis cannot start:\n\n' + '\n'.join(f'• {problem}' for problem in input_problems),
            )
            return

        # The analysis draws the inputs from the error sources stated in the
        # shared panel, the same ones the fit's interval accounts for, plus the
        # random error of each addition, which only it samples.
        errors = self._input_panel.current_errors()
        if not errors.varies:
            QMessageBox.warning(
                self,
                'Sensitivity Analysis',
                'Every input is set to fixed under Input Uncertainty, so the analysis has nothing to vary. '
                'Choose a σ or a range for at least one input.',
            )
            return
        problems = self._sensitivity_panel.run_problems(errors)
        if problems:
            QMessageBox.warning(
                self,
                'Sensitivity Analysis',
                'The analysis cannot start:\n\n' + '\n'.join(f'• {problem}' for problem in problems),
            )
            return
        sens_config = self._sensitivity_panel.current_config(errors)

        assay_cls = self._assay_panel.get_assay_class()
        conditions = self._assay_panel.current_conditions()
        fit_config = self._fit_panel.current_config()
        custom_bounds = self._bounds_panel.current_bounds()
        if custom_bounds:
            fit_config = replace(fit_config, custom_bounds=custom_bounds)

        # Every fit the run makes: the perturbations, the refits the
        # elasticities take, and the baseline.
        n_inputs = len(self._input_panel.input_labels())
        curve_fits = estimated_fit_count(sens_config, n_inputs) + 1
        worker_count = preferences.worker_count()
        if estimated_model_solves(sens_config, fit_config, self._state.assay_type, n_inputs) > LONG_RUN_SOLVES:
            spread = 'one at a time' if worker_count == 1 else f'{worker_count} at a time'
            reply = QMessageBox.question(
                self,
                'This Will Take a While',
                f'Your data will be re-fitted about {curve_fits:,} times to measure how much '
                f'the result moves, {spread}.\n\nYou can stop it at any point once it starts, '
                f'and the progress bar will estimate the time left.\n\n'
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
            max_workers=worker_count,
            input_labels=self._input_panel.input_labels(),
            parent=self,
        )
        self._sensitivity_worker.progress.connect(self._on_sensitivity_progress)
        self._sensitivity_worker.finished.connect(self._on_sensitivity_complete)
        self._sensitivity_worker.stopped.connect(self._on_sensitivity_stopped)
        self._sensitivity_worker.error.connect(self._on_sensitivity_error)

        self._sensitivity_started = time.monotonic()
        self._summary_widget.show_running(sens_config.mode)
        self._sensitivity_widget.show_running()
        self._sensitivity_panel.set_running(True)
        self._plot_tabs.setCurrentWidget(self._sensitivity_widget)
        self._sensitivity_worker.start()
        self.actions_changed.emit()
        self.status_message.emit('Running sensitivity analysis…')

    def _on_sensitivity_progress(self, done: int, total: int) -> None:
        """Report progress, with a time estimate once there is enough to judge.

        A run that has been asked to stop reports that instead: the counts still
        arrive from the fits that were already running, and a rising count in
        the status bar beside a page that says it is stopping reads as two
        contradictory answers.
        """
        self._sensitivity_widget.set_progress(done, total)
        if self._sensitivity_worker is not None and self._sensitivity_worker.cancelled:
            self.status_message.emit(STOPPING_TEXT)
            return
        elapsed = time.monotonic() - self._sensitivity_started
        if 3 <= done < total and elapsed > 0:
            remaining = elapsed / done * (total - done)
            self.status_message.emit(f'Analysing — {done:,} of {total:,}, about {_format_remaining(remaining)} left')
        else:
            self.status_message.emit(f'Analysing — {done:,} of {total:,}')

    def _on_sensitivity_complete(self, result) -> None:
        worker = self._sensitivity_worker
        if self.sender() is not worker:
            return  # a run whose data were replaced while it went
        self._sensitivity_worker = None
        cancelled = worker is not None and worker.cancelled
        retire(worker)
        self._state.sensitivity_result = result
        # Shown or hidden by the selection as it is now, before any tab draws it.
        self._show_results()
        self._sensitivity_widget.update_result(result)
        self._summary_widget.set_sensitivity(result)
        self._identifiability_widget.update_sensitivity(result)
        self._sensitivity_panel.set_running(False)
        self.actions_changed.emit()
        hidden = self._state.sensitivity_note
        if hidden is not None:
            # The counts describe a result no tab is showing, so the note takes their place.
            self.status_message.emit(f'Sensitivity {"stopped" if cancelled else "complete"} but hidden — {hidden}')
            return
        # Counted as the cost dialog and the progress bar count: every fit the
        # run makes, the baseline included. The baseline is this result, so it
        # succeeded; only the perturbed fits could have failed.
        planned = result.n_planned + 1
        succeeded = result.n_success + 1
        if cancelled:
            self.status_message.emit(
                f'Sensitivity stopped — {succeeded:,} of {planned:,} fits succeeded before you cancelled'
            )
        else:
            self.status_message.emit(f'Sensitivity complete — {succeeded:,} of {planned:,} fits succeeded')

    def _on_sensitivity_stopped(self) -> None:
        """A run cancelled before it had a single finished fit: there is nothing to show for it."""
        worker = self._sensitivity_worker
        if self.sender() is not worker:
            return  # a run whose data were replaced while it went
        self._sensitivity_worker = None
        retire(worker)
        self._show_previous_sensitivity()
        self._sensitivity_panel.set_running(False)
        self.actions_changed.emit()
        self.status_message.emit('Sensitivity stopped — no fits had finished')

    def _on_sensitivity_error(self, msg: str) -> None:
        worker = self._sensitivity_worker
        if self.sender() is not worker:
            return  # a run whose data were replaced while it went
        self._sensitivity_worker = None
        retire(worker)
        self.actions_changed.emit()
        self._show_previous_sensitivity()
        QMessageBox.warning(self, 'Sensitivity Analysis', msg)
        self._sensitivity_panel.set_running(False)
        self.status_message.emit(f'Sensitivity failed: {msg}')

    def _show_previous_sensitivity(self) -> None:
        """Take the Ka Sensitivity tab off the progress page: back to what it showed before the run."""
        previous = self._state.sensitivity_result
        if previous is None:
            self._sensitivity_widget.clear()
        else:
            self._sensitivity_widget.update_result(previous)
        self._summary_widget.set_sensitivity(previous)

    def _clear_sensitivity(self) -> None:
        """Drop the sensitivity result from the Ka Sensitivity tab and the summary, and stop a run still going.

        The stopped run's signals reach nothing, so its result never describes
        data it was not computed on.
        """
        self._stop_sensitivity()
        self._state.sensitivity_result = None
        self._state.sensitivity_note = None
        self._sync_notes()
        self._sensitivity_widget.clear()
        self._sensitivity_panel.set_running(False)
        self._summary_widget.set_sensitivity(None)

    def _cancel_sensitivity(self) -> None:
        if self._sensitivity_worker is not None:
            self._sensitivity_worker.cancel()
            self.status_message.emit(STOPPING_TEXT)

    # ------------------------------------------------------------------
    # Showing and hiding results
    # ------------------------------------------------------------------

    def _mismatch_note(
        self, result: FitResult | None, what: str, redo: str, *, uncertainties: bool = True
    ) -> str | None:
        """Why *result* does not describe the loaded selection, as a short plain note; ``None`` when it does.

        The one match test for every result the session holds. *result*
        matches when it was made on the loaded data (the same
        ``data_fingerprint``), every replicate it used is active and every
        active replicate was given to it, its conditions equal the entered ones
        by value (a unit switch changes nothing) and describe the same dilution
        by the titrant, its assay type is the one selected, and — for a fit,
        whose interval accounts for them — the error sources it was made with
        are the ones set now. The note names
        what differs and how to undo it. *what* names the result ("fit") and
        *redo* how to make a new one ("run the fit again"). With no data
        loaded only the assay type, the conditions and the uncertainties can be
        compared. *uncertainties* is ``False`` for a sensitivity analysis'
        baseline, which is fitted with the uncertainties stripped because the
        analysis draws them itself; the analysis' own record of them is
        compared by :meth:`_sensitivity_inputs_note`. The rest of the fit
        configuration is not part of the test: a sensitivity analysis is run
        from its own settings, and every configuration difference that changes
        what it means is named where it is shown.
        """
        ms = self._state.measurement_set
        opening = f'This {what} was made'
        made = opening
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
                dilution, dilution_fixes = self._dilution_mismatch(result.conditions, entered)
                changes += dilution
                fixes += dilution_fixes
                # Only what the conditions themselves said: a replicate switched
                # off is already in `changes` and does not name this difference.
                if not keys and not dilution:
                    changes.append('the assay conditions entered now differ from its own')
                    fixes.append('enter its conditions again')

        if not changes:
            used = ErrorModel.from_dict(result.fit_config)
            if uncertainties and used != self._input_panel.current_errors().for_fit():
                return _INPUTS_CHANGED_NOTE.format(stated=_stated_as(result))
            return None
        fix = fixes[0] if len(fixes) == 1 else 'change these back'
        # A dilution difference names nothing the result was made with — the
        # choice is on or off — so with nothing else differing the note has no
        # opening clause to carry and starts at the change itself.
        head = f'{made}. ' if made != opening else ''
        return f'{head}{_capitalized(and_join(changes))}. {_capitalized(fix)}, or {redo}.'

    def _dilution_mismatch(self, stored: dict, entered: dict) -> tuple[list[str], list[str]]:
        """What changed about the dilution by the titrant, and how to undo it; two empty lists when nothing did.

        The two differences a key-by-key comparison of the conditions cannot
        name: a result made with the additions diluting the sample carries the
        titrant stock and a result made with the totals constant carries
        neither dilution key, so switching the choice adds or removes a key
        rather than changing one; and which fixed concentrations the stock
        itself holds is a list of keys, not a value a condition field shows.
        """
        was, now = TITRANT_STOCK in stored, TITRANT_STOCK in entered
        if was != now:
            return (
                [f'the dilution by the titrant is now switched {"on" if now else "off"}'],
                [f'switch it {"off" if now else "back on"}'],
            )
        if not now:
            return [], []
        stored_in = tuple(stored.get('stock_contains') or ())
        entered_in = tuple(entered.get('stock_contains') or ())
        if set(stored_in) == set(entered_in):
            return [], []
        return (
            [
                f'the titrant stock is now stated to contain {self._contains_text(entered_in)}'
                if entered_in
                else 'the titrant stock is now stated to contain none of the fixed concentrations'
            ],
            [
                f'tick {self._contains_text(stored_in)} under the titrant stock again'
                if stored_in
                else 'untick every concentration under the titrant stock again'
            ],
        )

    def _contains_text(self, keys: tuple[str, ...]) -> str:
        """The concentrations *keys* names, as the conditions form labels them."""
        return and_join([self._assay_panel.condition_name(key) or key for key in keys])

    def _sensitivity_inputs_note(self, result: SensitivityResult) -> str | None:
        """Why *result* no longer describes the uncertainties set now; ``None`` while it does.

        The analysis draws its samples from the error sources it was run with,
        so the Ka spread, the Sobol' indices and a heatmap's axis ranges are
        entirely a function of them; the run records them in
        ``config.errors``. A heatmap holds every input but its two axes at its
        set value and records only those two, so only what it recorded is
        compared.
        """
        used = result.config.errors
        stated = self._input_panel.current_errors()
        if result.config.mode is SensitivityMode.HEATMAP:
            stated = ErrorModel(specs={key: stated.specs[key] for key in used.specs if key in stated.specs})
        return None if used == stated else _SENSITIVITY_INPUTS_NOTE

    def _show_results(self, *, redraw: bool = False, force: bool = False) -> None:
        """Show every held result whose record matches the loaded selection, and hide the rest behind a note.

        Runs after each change to the selection: a replicate switched on or
        off, Outlier Removal, a finished edit of the conditions or a new assay
        type. No number is recomputed: a hidden result is shown again exactly
        as it was. The tabs are redrawn only when a result is shown or hidden;
        *redraw* also redraws the Fit Curve, for a change to its points, and
        *force* redraws every tab, for new results. A change that hides a
        result replaces the status bar's message about it, which described
        results the tabs no longer show.
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
                state.sensitivity_result.baseline_fit,
                'sensitivity analysis',
                'run the analysis again',
                uncertainties=False,
            ) or self._sensitivity_inputs_note(state.sensitivity_result)
        changed = notes != state.hidden_fit_notes or sensitivity_note != state.sensitivity_note
        state.hidden_fit_notes = notes
        state.sensitivity_note = sensitivity_note
        self._sync_notes()
        if changed and (notes or sensitivity_note):
            self.status_message.emit(_RESULTS_HIDDEN_NOTE)
        if changed or force:
            self._render_results()
        elif redraw:
            self._refresh_plot()

    def _fit_view(self) -> tuple[FitResult | None, str | None]:
        """The fit the summary describes, and the note hiding it (``None`` while it is shown).

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

    def _render_results(self) -> None:
        """Put the held fit results on the Fit Curve and the summary, shown or hidden."""
        fit, _note = self._fit_view()
        self._refresh_plot()
        if fit is None:
            self._summary_widget.clear()
        else:
            unchecked = _UNCHECKED_NOTE if self._state.measurement_set is None else None
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
