"""SessionModel — the data, settings, results, runs and rules of one fitting session, without widgets.

The user's settings live in two widget-free forms the model owns — the binding
model (:class:`~gui.binding.BindingForm`) and the input uncertainties
(:class:`~gui.uncertainty.UncertaintyForm`) — beside the appearance of its titration
plot (:class:`~gui.plot_appearance.PlotAppearance`) and the session's own copy of a
binding model to simulate (:class:`~gui.simulation.SimulationForm`). A view edits a form, tells the model
(:meth:`SessionModel.binding_edited`, :meth:`SessionModel.uncertainty_edited`),
and draws what the model's signals say changed. Every rule a session follows reads the model: whether a held result
still describes the loaded data and settings (and the note that says why not),
whether a run can start (and the message that says why not), the session's
name, and what is running.
"""

from __future__ import annotations

import copy
import functools
import logging
import math
import time
from dataclasses import dataclass, field, replace
from enum import Flag, auto
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from PyQt6.QtCore import QObject, QStandardPaths, pyqtSignal
from PyQt6.QtGui import QKeySequence

from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.data_processing.measurement_set import InvalidData, MeasurementSet
from core.io.formats.bmg_reader import BMG_PLACEHOLDER_KEY
from core.pipeline.fit_pipeline import FitConfig, FitResult
from core.pipeline.inputs import TITRANT, TITRANT_STOCK, ErrorModel, InputSpec, source_name
from core.pipeline.profile import ProfileSet
from core.pipeline.reporting import fit_replica_ids, input_replica_ids, parameters_on_bound, summarize_parameters
from core.pipeline.results_io import verify_imported_result
from core.pipeline.sensitivity import (
    _SOBOL_BLOCKS,
    LONG_RUN_SOLVES,
    SensitivityConfig,
    SensitivityMode,
    SensitivityResult,
    estimated_fit_count,
    estimated_model_solves,
)
from core.pipeline.varpro import REPLICATE_TEST_MIN, projectable
from core.units import Q_, Quantity
from gui import confidence as CF
from gui import preferences
from gui import results as R
from gui import sensitivity as S
from gui.binding import BindingForm, binding_constants
from gui.confidence import NO_KA as NO_KA_TO_PROFILE
from gui.dataset import DEMO_IDA, OUTLIER_DEFAULTS, Dataset, bundled
from gui.plot_appearance import BUILT_IN, PlotAppearance
from gui.plotting.labels import (
    STOPPING_TEXT,
    and_join,
    describe_replicates,
    field_text,
    fmt_bound_note,
    fmt_param_plain,
    fmt_r2,
    fmt_rmse,
    fmt_unit_pretty,
    fmt_value,
    stated_uncertainty,
    verdict_headline,
)
from gui.results import REPLICATE_DISPLAYS, RUN_FIT_KEY, CalloutSpec, Place
from gui.sensitivity import NO_KA as NO_KA_TO_FOLLOW
from gui.sensitivity import NOTHING_VARIES, RUN_ANALYSIS_KEY, AnalysisForm
from gui.simulation import Overlay, Simulation, SimulationForm, SimulationProblem
from gui.uncertainty import UncertaintyForm
from gui.widgets.assay_conditions import (
    ASSAY_NAMES,
    assay_class,
    condition_field,
    condition_name,
    format_condition,
    result_input_labels,
    same_inputs,
)
from gui.workers import FitWorker, ProfileWorker, SensitivityWorker, retire

logger = logging.getLogger(__name__)


class Change(Flag):
    """What one edit of a session changed; :attr:`SessionModel.changed` carries the union."""

    DATA = auto()  # the files, the concentrations as stated, the replicates in use
    RESULTS = auto()  # the held fits, which of them are shown, and the notes hiding the rest
    PROFILE = auto()  # the Ka profile of the latest fit: started, arrived, failed or dropped
    SENSITIVITY = auto()  # the sensitivity result held, or what is known of the last run
    RUN = auto()  # a fit or a sensitivity run started or ended
    PROGRESS = auto()  # the count of the running sensitivity analysis
    BINDING = auto()  # the binding model as stated
    UNCERTAINTY = auto()  # the statement of the input uncertainties
    ANALYSIS = auto()  # the settings of the next sensitivity run
    DISPLAY = auto()  # how the titration plots are drawn: the concentration unit and the replicate display
    APPEARANCE = auto()  # the appearance of the titration plot
    SIMULATION = auto()  # the simulation's settings, what they simulate, and the data laid over it
    NAME = auto()  # the session's name
    STATUS = auto()  # the status message


def _edit(method):
    """Make *method* one edit of the session: what it changes is said once, after it has returned.

    Edits nest, so an edit that calls another is still said once, when the
    outermost one returns and every piece of state derived from it is up to date.
    """

    @functools.wraps(method)
    def edit(self: SessionModel, *args: Any, **kwargs: Any) -> Any:
        self._depth += 1
        try:
            return method(self, *args, **kwargs)
        finally:
            self._depth -= 1
            self._say()

    return edit


_FIT_RUNNING_NOTE = (
    'A fit is already running in this session. Wait for it to finish, or stop it with Stop, then run the fit again.'
)
_SENSITIVITY_RUNNING_NOTE = (
    'A sensitivity analysis is running in this session. Wait for it to finish, or stop it, then run the fit.'
)
_FIT_RUNNING_IMPORT_NOTE = (
    'A fit is running in this session, and its result would replace the imported results when it finishes. '
    'Wait for it to finish, or stop it with Stop, then import the results.'
)
_FIT_RUNNING_ANALYSIS_NOTE = (
    'A fit is running in this session. Wait for it to finish, or stop it with Stop, then run the sensitivity analysis.'
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
    'uncertainty, or fit again to update the interval.'
)

#: Read for ``{stated}`` of a fit that was made with every input taken as exact.
_NO_UNCERTAINTY_STATED = 'every input taken as exact'

#: Said when the titrant stock entered is no more concentrated than the titrant
#: concentrations measured. The conditions form cannot make this check — it is
#: the one that needs the loaded data — and the assay refuses the same thing
#: with the same sentence once a fit reaches it.
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
    'The input uncertainties have changed since this analysis; set them back under Input uncertainty, or run '
    'the analysis again.'
)

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


@dataclass(frozen=True)
class Refusal:
    """Why a run or an import cannot start: the title and the message a dialog shows, and the *place*
    holding what to change, which the session shows once the dialog is closed."""

    title: str
    message: str
    place: Place | None = None


@dataclass(frozen=True)
class EmptyView:
    """What a view shows in place of content it does not have yet (:meth:`SessionModel.empty_view`).

    *title* names the state in a few words, which a side panel says alone; *sentence* says
    what comes next; *offers_data* puts *Load data…* and *Try the demo data* under them, in
    a session that holds nothing.
    """

    title: str
    sentence: str
    offers_data: bool = False


#: The input uncertainties the demo states: a literature Ka,dye known to about 10 %, and stock
#: concentrations pipetted to about 3 %. Typical figures, so that the demo's first fit reports
#: the interval that covers them.
DEMO_UNCERTAINTIES = {
    'Ka_dye': InputSpec.sigma_pct(10.0),
    'h0': InputSpec.sigma_pct(3.0),
    'd0': InputSpec.sigma_pct(3.0),
    TITRANT: InputSpec.sigma_pct(3.0),
}

#: The views that show a result or a plot of the data, and so can have nothing to show yet.
EMPTY_VIEWS = ('Measurements', 'Fit results', 'Ka confidence', 'Sensitivity', 'Plot appearance')

#: What each of :data:`EMPTY_VIEWS` asks for while the session holds no data.
_LOAD_DATA = {
    'Measurements': 'Load the titration files of this experiment',
    'Fit results': 'Load your titration files to fit them',
    'Ka confidence': 'Load your titration files and fit them to see the Kₐ profile here',
    'Sensitivity': 'Load your titration files to see here how the stated input uncertainties move each Kₐ',
    'Plot appearance': 'Load your titration files to see the titration plot these settings style',
}


def _shortcut(key: str) -> str:
    """*key* as the platform writes it: ⌘R on macOS, Ctrl+R elsewhere."""
    return QKeySequence(key).toString(QKeySequence.SequenceFormat.NativeText)


@dataclass(frozen=True)
class ImportCheck:
    """What a check of imported results against the loaded data found.

    Attributes
    ----------
    accepted : list[FitResult]
        The results that describe the loaded data, as checked.
    refusal : str or None
        Why the others were left out, one paragraph per reason; ``None`` when none was.
    notice : str or None
        What the user should know about the accepted ones; ``None`` when nothing.
    """

    accepted: list[FitResult]
    refusal: str | None = None
    notice: str | None = None


@dataclass(frozen=True)
class SessionSettings:
    """Everything the user has set in a session, as its forms state it.

    Attributes
    ----------
    assay_type : AssayType
        The selected assay.
    conditions : Mapping[str, Any]
        The entered conditions in base units, with the titrant stock and the
        concentrations it holds once dilution is chosen.
    condition_units : Mapping[str, str]
        The unit each condition is shown in, which the notes write it in; a
        condition with none is written in its base unit.
    assay_problems : tuple[str, ...]
        Why the conditions as entered cannot be used, one sentence per problem.
    bounds : Mapping
        Each parameter's bounds as shown, as Quantities in its unit; ``None``
        for a parameter whose bounds cannot be read.
    custom_bounds : Mapping or None
        The bounds that differ from the registry defaults; ``None`` when none does.
    bound_problems : tuple[str, ...]
        Why the bounds as shown cannot be used, one sentence per parameter.
    per_replica : bool
        Whether each replicate is fitted on its own as well.
    errors : ErrorModel
        The stated uncertainties of the inputs.
    input_labels : Mapping[str, str]
        Each input's key and the plain name the views give it, the titrant included.
    input_problems : tuple[str, ...]
        Why the uncertainties as stated cannot be used, one sentence per problem.
    display_unit : str
        The concentration unit the plots show.
    replicate_display : int
        What the titration plots show of the replicates: the index of
        :data:`gui.results.REPLICATE_DISPLAYS` — their points and mean ± SD, the mean
        ± SD only, or their points only.
    """

    assay_type: AssayType = AssayType.GDA
    conditions: Mapping[str, Any] = field(default_factory=dict)
    condition_units: Mapping[str, str] = field(default_factory=dict)
    assay_problems: tuple[str, ...] = ()
    bounds: Mapping[str, tuple[Quantity, Quantity] | None] = field(default_factory=dict)
    custom_bounds: Mapping[str, tuple[Quantity, Quantity]] | None = None
    bound_problems: tuple[str, ...] = ()
    per_replica: bool = FitConfig().per_replica
    errors: ErrorModel = field(default_factory=ErrorModel)
    input_labels: Mapping[str, str] = field(default_factory=dict)
    input_problems: tuple[str, ...] = ()
    display_unit: str = 'µM'
    replicate_display: int = 0

    def fit_config(self) -> FitConfig:
        """The configuration a fit or an analysis runs under: the replicate mode and the bounds."""
        config = FitConfig(per_replica=self.per_replica)
        if self.custom_bounds:
            config = replace(config, custom_bounds=dict(self.custom_bounds))
        return config


#: The settings a held result is checked against as soon as they change. The
#: conditions arrive as they are typed and are checked once the edit is
#: finished (:meth:`SessionModel.edit_finished`).
_CHECKED_SETTINGS = frozenset({'assay_type', 'bounds', 'per_replica', 'errors'})


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

    Each source named and valued as Input uncertainty writes it — an
    input's own uncertainty, after them the ones several inputs share, and last
    the random error of each addition with its mode and what the replicates
    are — so a note about a fit made with other uncertainties says which ones
    they were and they can be set back without opening the file.
    """
    errors = ErrorModel.from_dict(result.fit_config)
    sources = errors.source_specs()
    if not sources and errors.additions is None:
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
    additions = errors.additions
    if additions is not None:
        mode = 'sequential additions into one cuvette' if additions.sequential else 'separately prepared samples'
        replicates = 'separate titrations' if additions.separate_titrations else 'repeated reads of one titration'
        stated.append(
            f'a random error of each addition of σ {additions.sigma_pct:g} % ({mode}; replicates are {replicates})'
        )
    return and_join(stated)


def _verdict_note(result: FitResult) -> str:
    """What the fit's diagnostics say in a few words, for the status bar; ``''`` for a fit that has none.

    The verdict's headline (:func:`verdict_headline`), continuing the sentence the
    status bar opens. A fit of an assay with no
    association constant, and a result read from a file written before the
    diagnostics existed, carry no verdict.
    """
    if result.diagnostics is None:
        return ''
    headline = verdict_headline(result.diagnostics)[0]
    return f'{headline[0].lower()}{headline[1:]}'


def _open_note(result: FitResult) -> str:
    """The binding constants whose estimate ran to an end of its search box, in words; ``''`` for none.

    Such an estimate is the box, not a measurement, so the status bar says the
    data do not limit it rather than reporting a clean fit.
    """
    sides = {'low': 'below', 'high': 'above'}
    return and_join(
        f'{fmt_param_plain(row.key)} not limited {sides[row.estimate_at_bound]} by the data'
        for row in summarize_parameters(result)
        if row.estimate_at_bound and not row.is_log
    )


def _bounds_text(lo: float, hi: float, unit: str) -> str:
    """A parameter's bounds in plain text, written as their fields write them: ``1 × 10⁻⁸ to 1 × 10¹² M⁻¹``, or
    ``from 0 a.u. with no upper limit``."""
    shown_unit = fmt_unit_pretty(unit)
    low = field_text(lo)
    if math.isinf(hi):
        return f'from {low}{f" {shown_unit}" if shown_unit else ""} with no upper limit'
    return f'{low} to {field_text(hi)} {shown_unit}'.rstrip()


def _left_out_text(result: FitResult, replica_ids: Sequence[str]) -> str:
    """The replicates the fit left out and why, named as the sidebar names them; ``''`` when it used every one."""
    failures = result.metadata.get('replica_failures') or {}
    if not failures:
        return ''
    return '; '.join(
        f'{_capitalized(describe_replicates([rid], replica_ids))} left out: {reason}'
        for rid, reason in failures.items()
    )


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


def _problem_list(verb: str, problems: Sequence[str]) -> str:
    return f'The {verb} cannot start:\n\n' + '\n'.join(f'• {problem}' for problem in problems)


def _count(n: int, noun: str) -> str:
    """``1 replicate``, ``8 replicates``."""
    return f'{n} {noun}{"" if n == 1 else "s"}'


class SessionModel(QObject):
    """The state and the rules of one fitting session.

    A result stays shown only while the loaded selection and the settings
    match the record it was made on (:meth:`mismatch_note` is the one test,
    joined for a sensitivity run by :meth:`_sensitivity_inputs_note`). After
    every change to the replicates, the conditions, the assay type, the
    parameter bounds, the replicate mode or the input uncertainties, a result
    that no longer matches is hidden behind a note naming what changed, and
    shown again, unchanged, once they match. An edit of the data in place —
    a file added or removed, the unit the concentrations are stated in, a
    concentration, the channel shown — is checked the same way: a result made
    on other data is hidden, and shown again once the data match it. Only
    data loaded in place of the session's own, or cleared, drop every result.
    Either kind of change stops the fit and the analysis still running, which
    were given the data as they were before it. One fit or analysis runs at a
    time.

    Signals
    -------
    changed(Change)
        What an edit changed, said once the edit is over and every piece of
        state derived from it — which fits are shown, the notes hiding the
        rest, the profile, the sensitivity note — is up to date.
    warning(str, str)
        Work in the background failed: a title and a message to show, said
        after the :attr:`changed` of the edit that met the failure.
    """

    changed = pyqtSignal(Change)
    warning = pyqtSignal(str, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        #: The binding model as stated; :meth:`binding_edited` after every change.
        unit = preferences.concentration_unit()
        self.binding = BindingForm(concentration_unit=unit)
        #: What the user states about the inputs; :meth:`uncertainty_edited` after every change.
        self.uncertainty = UncertaintyForm(self.binding.assay_type)
        self.uncertainty.set_conditions(self.binding.conditions(), self.binding.condition_units())
        self._settings = SessionSettings(**self.binding_settings(), **self.uncertainty_settings(), display_unit=unit)
        #: The settings of the next sensitivity run; :meth:`analysis_edited` after every change.
        self.analysis = AnalysisForm()
        self.analysis.set_inputs(list(self._settings.input_labels))
        #: Why the session starts from the built-in plot appearance in place of the one stored
        #: for new sessions — which cannot be read — or ``None``; the window shows it.
        self.appearance_refusal: Refusal | None = None
        try:
            appearance = preferences.plot_appearance_default()
        except ValueError as exc:
            appearance = BUILT_IN
            self.appearance_refusal = Refusal(
                'Plot Appearance Not Read',
                f'{exc} This session starts from the built-in plot appearance. To store another for new '
                'sessions, choose it in Plot appearance and click Use for new sessions.',
            )
        self._plot_appearance = appearance
        #: The session's own copy of a binding model to simulate, seeded from :attr:`binding` when Simulation is
        #: first shown (:meth:`open_simulation`); :meth:`edit_simulation` for every change.
        self.simulation = SimulationForm()
        self._simulation_open = False
        self._simulated: Simulation | None = None
        self._simulation_problem: str | None = None
        self._dataset: Dataset | None = None
        self._custom_name: str | None = None
        self._progress: tuple[int, int] | None = None  # the running analysis's count, done of total
        self._status = ''
        # Results. A result is held until other data are loaded or a new result
        # replaces it, and shown while it matches the loaded selection and the
        # settings; a hidden result comes back unchanged once they match.
        self._held_fit_results: list[FitResult] = []
        self._hidden_fit_notes: dict[str, str] = {}  # FitResult.id -> why it is hidden
        self._sensitivity_result: SensitivityResult | None = None
        self._sensitivity_note: str | None = None
        self._profiled_fit: FitResult | None = None
        self._profile: ProfileSet | None = None
        self._profile_error: str | None = None
        # Runs
        self._fit_worker: FitWorker | None = None
        self._profile_worker: ProfileWorker | None = None
        self._sensitivity_worker: SensitivityWorker | None = None
        self._sensitivity_started = 0.0
        self._sensitivity_error: str | None = None  # why the last run could not be completed
        self._sensitivity_seconds: float | None = None  # how long the run held took
        self._sensitivity_workers: int | None = None  # the worker processes it ran on
        self._run_workers: int | None = None
        # Edits (:func:`_edit`): how deep the one running is nested, and what it has changed and has to say.
        self._depth = 0
        self._changes = Change(0)
        self._warnings: list[tuple[str, str]] = []

    def _note(self, change: Change) -> None:
        """Record *change* to say once the edit making it is over; said at once outside an edit."""
        self._changes |= change
        self._say()

    def _warn(self, title: str, message: str) -> None:
        """Say *message* in a warning once the edit that met it is over."""
        self._warnings.append((title, message))
        self._say()

    def _say(self) -> None:
        """Say what changed, then the warnings met, unless an edit is still under way."""
        if self._depth:
            return
        changes, self._changes = self._changes, Change(0)
        warnings, self._warnings = self._warnings, []
        if changes:
            self.changed.emit(changes)
        for title, message in warnings:
            self.warning.emit(title, message)

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    @property
    def dataset(self) -> Dataset | None:
        """The session's files and the concentrations they share."""
        return self._dataset

    @property
    def measurement_set(self) -> MeasurementSet | None:
        """The loaded data, whose active replicates the views switch on and off in place."""
        return None if self._dataset is None else self._dataset.ms

    @property
    def _source_file(self) -> str | None:
        files = () if self._dataset is None else self._dataset.files
        return files[0].path if files else None

    @property
    def source_file(self) -> str | None:
        """The first file the loaded data were read from."""
        return self._source_file

    @_edit
    def load(self, ms: MeasurementSet, source_file: str | None) -> None:
        """Take *ms* as the session's data, clearing every result and stopping the work running on the old data."""
        self._take(Dataset.from_set(ms, source_file))

    @_edit
    def load_files(self, paths: list[str]) -> Refusal | None:
        """Load *paths* as the session's data in place of what it holds; say why when they cannot be loaded."""
        try:
            dataset = Dataset.open(list(paths))
        except InvalidData as exc:
            return Refusal('Load Error', str(exc))
        self._take(dataset)
        return None

    @_edit
    def add_files(self, paths: list[str]) -> Refusal | None:
        """Add *paths* to the session's data as further replicates, keeping every result; say why when they cannot be.

        A result made without the new replicates is then hidden like one made
        before a replicate was switched on, and comes back if they are removed. A
        session with no data takes the files as its data, keeping the results it holds
        as well: they are shown wherever they were made on these data.
        """
        empty = self._dataset is None or self._dataset.ms is None
        try:
            dataset = Dataset.open(list(paths)) if empty else self._dataset.added(list(paths))
        except InvalidData as exc:
            return Refusal('Files Not Added', str(exc))
        added = len(dataset.files) - (0 if empty else len(self._dataset.files))
        self._dataset = dataset
        self._data_edited(f'Added {added} file{"s" if added != 1 else ""} — {self._loaded_text()}')
        return None

    @_edit
    def remove_file(self, path: str) -> Refusal | None:
        """Remove the file *path* and its replicates; the session's last file clears the data."""
        if self._dataset is None:
            return None
        try:
            dataset = self._dataset.without(path)
        except InvalidData as exc:
            return Refusal('File Not Removed', str(exc))
        if dataset is None:
            self.clear()
            return None
        self._dataset = dataset
        self._data_edited(f'Removed {Path(path).name} — {self._loaded_text()}')
        return None

    @_edit
    def select_channel(self, channel: str) -> Refusal | None:
        """Show *channel* of a multi-channel file: an edit of the data in place (:meth:`_data_edited`)."""
        if channel == self._dataset.channel:
            return None
        try:
            self._dataset.select_channel(channel)
        except InvalidData as exc:
            return Refusal('Channel Error', str(exc))
        self._data_edited(f'Showing channel {self._dataset.channel_label(channel)}')
        return None

    @_edit
    def set_imported_unit(self, unit: str) -> None:
        """Read the concentrations as stated in *unit*: an edit of the data in place (:meth:`_data_edited`)."""
        if unit == self._dataset.imported_unit:
            return
        self._dataset.set_imported_unit(unit)
        self._data_edited(f'Concentrations now stated in {unit}')

    @_edit
    def set_concentration(self, index: int, text: str) -> Refusal | None:
        """Set point *index* to *text* in the imported unit: an edit of the data in place (:meth:`_data_edited`)."""
        try:
            self._dataset.set_concentration(index, text)
        except InvalidData as exc:
            return Refusal('Invalid Concentration', f'{exc} The point keeps its value.')
        self._data_edited(f'Point {index + 1} set to {text} {self._dataset.imported_unit}')
        return None

    @_edit
    def load_concentrations(self, path: str) -> tuple[Refusal | None, str | None]:
        """Take the concentrations from *path*: the refusal, or a notice when their unit was converted."""
        try:
            notice = self._dataset.load_concentrations(path)
        except InvalidData as exc:
            return Refusal('Concentrations Not Loaded', str(exc)), None
        self._data_edited(f'Concentrations loaded from {Path(path).name}')
        return None, notice

    @_edit
    def save_concentrations(self, path: str) -> Refusal | None:
        """Write the concentrations as stated to *path*."""
        try:
            self._dataset.save_concentrations(path)
        except OSError:
            return Refusal(
                'Concentrations Not Saved',
                'Could not save the concentrations. Check that the folder exists and that you can write there.',
            )
        self.show_status(f'Concentrations saved to {Path(path).name}')
        return None

    @_edit
    def set_replicate(self, replica_id: str, on: bool) -> None:
        """Use replicate *replica_id* in the fit (*on*) or switch it off."""
        self.measurement_set.set_active(replica_id, on)
        self._data_changed()

    @_edit
    def reset_replicates(self) -> None:
        """Use every replicate again."""
        self.measurement_set.reset_active()
        self._data_changed()
        self.show_status('Replicates reset — all in use')

    @_edit
    def remove_outliers(self, threshold: float, min_replicates: int) -> Refusal | None:
        """Switch off the replicates the outlier filter finds at *threshold*; say why when it cannot run."""
        try:
            self._dataset.remove_outliers(threshold, min_replicates)
        except InvalidData as exc:
            return Refusal('Outlier Removal', str(exc))
        self._data_changed()
        ms = self.measurement_set
        self.show_status(f'Outlier removal applied — {ms.n_active} of {ms.n_replicas} replicates in use')
        return None

    def _loaded_text(self) -> str:
        ms = self.measurement_set
        return f'{ms.n_points} points × {ms.n_replicas} replicates, {ms.n_active} in use'

    def _take(self, dataset: Dataset) -> None:
        """Hold *dataset* as the session's data in place of its own, dropping every result."""
        self._dataset = dataset
        self._data_edited(f'Loaded: {self._loaded_text()}', discard=True)

    @_edit
    def clear(self) -> None:
        """Drop the data and every result, stopping the work still running."""
        self._dataset = None
        self._data_edited('Data cleared', discard=True)

    def _data_edited(self, message: str, *, discard: bool = False) -> None:
        """The session's data changed: stop the work on the data it had, check the results again, say *message*.

        The fit and the analysis still running were given the data as they
        were, so their results would describe data no longer loaded; the Ka
        profile describes the fit it belongs to and runs on. *discard* drops
        every result, for data loaded in place of the session's own; an edit in
        place keeps them, hidden while they were made on other data
        (:meth:`mismatch_note`) and shown again, unchanged, once the data match.
        """
        stopped = self.running_work()
        self._stop_fit()
        self._stop_sensitivity()
        if discard:
            self._held_fit_results = []
            self._clear_profile()
            self._clear_sensitivity()
        self._data_changed()
        self.show_status(f'{message} — the running {stopped} was stopped' if stopped else message)

    def _data_changed(self) -> None:
        """The data or the replicates in use changed; the held results are checked against them again, and the data
        laid over the simulation follow them."""
        self._note(Change.NAME | Change.DATA)
        if self.simulation.overlay is not None:
            self.edit_simulation(lambda f: f.set_overlay(self._data_overlay()))
        self.check_results()

    def dataset_file(self) -> str | None:
        """The file the session's data come from: the loaded one, else the one the latest shown fit was made on."""
        if not self._source_file and self.fit_results:
            return self.fit_results[-1].source_file
        return self._source_file

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    @property
    def settings(self) -> SessionSettings:
        return self._settings

    @_edit
    def set_display_unit(self, unit: str) -> None:
        """Draw the titration plots with the concentrations in *unit* from now on, and say so when it changed."""
        if unit != self._settings.display_unit:
            self.update_settings(display_unit=unit)
            self._note(Change.DISPLAY)

    @_edit
    def set_replicate_display(self, index: int) -> None:
        """Show the replicates on the titration plots as :data:`gui.results.REPLICATE_DISPLAYS` [*index*] says."""
        if not 0 <= index < len(REPLICATE_DISPLAYS):
            raise ValueError(f'No replicate display {index}; there are {len(REPLICATE_DISPLAYS)}.')
        if index != self._settings.replicate_display:
            self.update_settings(replicate_display=index)
            self._note(Change.DISPLAY)

    @_edit
    def update_settings(self, **changes: Any) -> None:
        """Take *changes* to the settings, and check the held results when one they are checked by changed.

        The conditions are not checked here: they arrive as they are typed, and
        are checked once the edit is finished (:meth:`edit_finished`).
        """
        self._take_settings(changes, check=False)

    def _take_settings(self, changes: Mapping[str, Any], check: bool) -> None:
        """Take *changes*; check the held results when *check* is set or a setting they are checked by changed."""
        old, new = self._settings, replace(self._settings, **changes)
        self._settings = new
        if check or any(getattr(old, key) != getattr(new, key) for key in _CHECKED_SETTINGS & changes.keys()):
            self.check_results()

    def binding_settings(self) -> dict[str, Any]:
        """The settings :attr:`binding` states: the model, its conditions, the bounds and the replicate mode."""
        form = self.binding
        return {
            'assay_type': form.assay_type,
            'conditions': form.conditions(),
            'condition_units': form.condition_units(),
            'assay_problems': tuple(form.problems()),
            'bounds': form.bounds(),
            'custom_bounds': form.custom_bounds(),
            'bound_problems': tuple(form.bound_problems()),
            'per_replica': form.per_replica,
        }

    @_edit
    def binding_edited(self, finished: bool = True) -> None:
        """Take the binding model as :attr:`binding` states it now, and say it changed.

        The input uncertainties follow it: another model has other inputs, and an
        uncertainty in percent is read against the conditions as entered. While a
        condition is still being typed (*finished* false) the held results are not
        checked against the conditions; every other setting is checked as it changes.
        """
        form = self.binding
        if form.assay_type is not self.uncertainty.assay_type:
            self.uncertainty.set_assay(form.assay_type)
        self.uncertainty.set_conditions(form.conditions(), form.condition_units(), finished)
        self._take_settings({**self.binding_settings(), **self.uncertainty_settings()}, check=finished)
        self.analysis.set_inputs(list(self._settings.input_labels))
        self._note(Change.BINDING | Change.UNCERTAINTY)

    def uncertainty_settings(self) -> dict[str, Any]:
        """The settings :attr:`uncertainty` states: the error model, the inputs' names and its problems."""
        form = self.uncertainty
        return {
            'errors': form.errors(),
            'input_labels': form.input_labels(),
            'input_problems': tuple(form.problems()),
        }

    @_edit
    def uncertainty_edited(self) -> None:
        """Take the statement of :attr:`uncertainty` as it reads now, and say it changed."""
        self.update_settings(**self.uncertainty_settings())
        self._note(Change.UNCERTAINTY)

    @_edit
    def analysis_edited(self) -> None:
        """Take the settings of the next sensitivity run as :attr:`analysis` states them now, and say they changed."""
        self._note(Change.ANALYSIS)

    def _analysis_inputs(self) -> tuple[ErrorModel, Mapping[str, str], dict[str, float]]:
        """What the analysis settings are read against: the stated sources, the inputs' names, their entered values."""
        settings = self._settings
        nominals = {k: float(v.magnitude) for k, v in settings.conditions.items() if isinstance(v, Quantity)}
        return settings.errors, settings.input_labels, nominals

    def analysis_problems(self) -> list[str]:
        """Why the analysis as set cannot run on the uncertainties stated, one sentence each (:meth:`AnalysisForm.problems`)."""
        return self.analysis.problems(*self._analysis_inputs())

    def analysis_config(self) -> SensitivityConfig:
        """The configuration of a run of the analysis as set; raises ``ValueError`` while :meth:`analysis_problems` finds one."""
        return self.analysis.config(*self._analysis_inputs())

    @property
    def plot_appearance(self) -> PlotAppearance:
        """How the session's titration plot is drawn, on screen and in a saved figure.

        A new session starts from the appearance stored for new sessions
        (:func:`gui.preferences.plot_appearance_default`), else from the built-in one.
        """
        return self._plot_appearance

    @_edit
    def set_plot_appearance(self, appearance: PlotAppearance) -> None:
        """Draw the titration plot with *appearance* from now on."""
        if appearance != self._plot_appearance:
            self._plot_appearance = appearance
            self._note(Change.APPEARANCE)

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------

    @property
    def simulated(self) -> Simulation | None:
        """What :attr:`simulation` simulates, or ``None`` before Simulation is first shown or where it cannot
        be computed (:attr:`simulation_problem` says why)."""
        return self._simulated

    @property
    def simulation_problem(self) -> str | None:
        """Why the last change of the simulation was refused, or why it cannot be computed; ``None`` when neither."""
        return self._simulation_problem

    @_edit
    def open_simulation(self) -> None:
        """Simulation is on screen: the first time, its copy takes the binding model this session states."""
        if not self._simulation_open:
            self._simulation_open = True
            self.use_session_model()

    @_edit
    def use_session_model(self) -> None:
        """Simulate the binding model this session states (:meth:`SimulationForm.take_binding`)."""
        self.edit_simulation(lambda f: f.take_binding(self.binding))

    @_edit
    def edit_simulation(self, change) -> None:
        """Apply *change* to :attr:`simulation` and simulate again; a change the form refuses is
        :attr:`simulation_problem`."""
        refused = None
        try:
            change(self.simulation)
        except SimulationProblem as problem:
            refused = str(problem)
        try:
            self._simulated = self.simulation.simulate()
        except SimulationProblem as problem:
            self._simulated = None
            refused = refused or str(problem)
        self._simulation_problem = refused
        self._note(Change.SIMULATION)

    def _data_overlay(self) -> Overlay | None:
        """The session's data as laid over the simulation: its replicates in use, named as the file card names them."""
        ms = self.measurement_set
        if ms is None:
            return None
        signals = np.array([signal for _rid, signal in ms.iter_replicas()])
        return Overlay(self.file_card()[0], np.asarray(ms.concentrations, dtype=float), signals)

    def overlay_data(self, on: bool) -> None:
        """Lay this session's data over the simulation and simulate at its concentrations (*on*), or take it off."""
        self.edit_simulation(lambda f: f.set_overlay(self._data_overlay() if on else None))

    def noise_refusal(self) -> str | None:
        """Why the simulation cannot read its noise from this session's replicates; ``None`` when it can."""
        overlay = self._data_overlay()
        return SimulationForm.read_noise_refusal(self.file_card()[0], None if overlay is None else overlay.signals)

    def read_noise(self) -> None:
        """Take the simulation's noise from the noise law of this session's replicates in use."""
        overlay = self._data_overlay()
        self.edit_simulation(lambda f: f.read_noise(overlay.name, overlay.signals))

    def fit_refusal(self) -> Refusal | None:
        """Why the simulated data cannot be fitted now; ``None`` when they can."""
        if self._simulated is not None:
            return None
        return Refusal(
            'Nothing to Fit',
            f'{self._simulation_problem or "The model cannot be computed with these settings."} Change the '
            'settings in Simulation, then fit again.',
        )

    @_edit
    def edit_finished(self) -> None:
        """Once an edit of the conditions is finished, make the conversions waiting for them and check the results."""
        if self.uncertainty.convert_pending():
            self._take_settings(self.uncertainty_settings(), check=True)
            self._note(Change.UNCERTAINTY)
        else:
            self.check_results()

    @_edit
    def bounds_from_dye_alone(self, path: str) -> Refusal | None:
        """Bound the signal coefficients by a dye-alone calibration in *path*; say why when it cannot be used.

        A straight line fitted to the calibration gives the free-dye signal (its
        slope) and the baseline (its intercept); each is bounded to ±20 % of it. The
        bounds are then shown as bounds typed in, and nothing changes when the file
        cannot be used.
        """
        from core.assays import DyeAloneAssay
        from core.io import load_measurements
        from core.pipeline.fit_pipeline import bounds_from_dye_alone, fit_linear_assay

        name = Path(path).name
        try:
            ms = MeasurementSet.from_dataframe(load_measurements(path), source_file=path)
            result = fit_linear_assay(ms.to_assay(DyeAloneAssay, conditions={}))
            bounds = bounds_from_dye_alone(result, margin=0.2)
        except InvalidData as exc:
            # Written for the user: it names the file, the replicate and the point, and the fix.
            return Refusal('Dye-alone calibration', f'{exc} The signal bounds were not changed.')
        except Exception:
            logger.exception('Could not fit the dye-alone data in %s', path)
            return Refusal(
                'Dye-alone calibration',
                f'Could not fit a straight line to the dye-alone data in {name}. Check that the file is a '
                'measurement of the dye alone, with its concentrations, then load it again. The signal bounds '
                'were not changed.',
            )
        self.binding.apply_dye_alone(bounds)
        self.binding_edited()
        names = and_join(fmt_param_plain(key) for key in self.binding.dye_alone_keys())
        self.show_status(f'Bounds of {names} set from the dye-alone calibration in {name}')
        return None

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------

    def name(self) -> str:
        """The session's name: the custom one, else the loaded file's stem, else 'New session'."""
        if self._custom_name:
            return self._custom_name
        return Path(self._source_file).stem if self._source_file else 'New session'

    @_edit
    def copy_from(self, other: SessionModel) -> None:
        """Take a copy of everything *other* states, and none of its results.

        Its data — the files, the concentrations as stated, which replicates are
        used — its binding model, input uncertainties, display unit, replicate
        display, plot appearance and simulation settings. The copy is named after *other*, so the two
        read apart in the switcher.
        """
        self.shutdown()
        self._dataset = copy.deepcopy(other._dataset)
        self.binding = copy.deepcopy(other.binding)
        self.uncertainty = copy.deepcopy(other.uncertainty)
        self.analysis = copy.deepcopy(other.analysis)
        self.simulation = copy.deepcopy(other.simulation)
        self._simulation_open = other._simulation_open
        self._simulated, self._simulation_problem = other.simulated, other.simulation_problem
        self._settings = other.settings
        self._plot_appearance = other.plot_appearance
        self._custom_name = f'{other.name()} copy'
        self._held_fit_results = []
        self._clear_profile()
        self._clear_sensitivity()
        self._note(
            Change.NAME
            | Change.DATA
            | Change.BINDING
            | Change.UNCERTAINTY
            | Change.ANALYSIS
            | Change.DISPLAY
            | Change.APPEARANCE
            | Change.SIMULATION
        )
        self.check_results()

    @_edit
    def set_custom_name(self, name: str) -> None:
        """Name the session *name*; an empty name gives it back its automatic one."""
        self._custom_name = name.strip() or None
        self._note(Change.NAME)

    @property
    def status(self) -> str:
        """The latest status message."""
        return self._status

    @_edit
    def show_status(self, message: str) -> None:
        """Say *message* on the status bar."""
        self._status = message
        self._note(Change.STATUS)

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------

    @property
    def held_fit_results(self) -> list[FitResult]:
        return self._held_fit_results

    @property
    def hidden_fit_notes(self) -> dict[str, str]:
        return self._hidden_fit_notes

    @property
    def fit_results(self) -> list[FitResult]:
        """The held fit results that are shown: every number, curve and export uses these."""
        return [result for result in self._held_fit_results if result.id not in self._hidden_fit_notes]

    @property
    def sensitivity_result(self) -> SensitivityResult | None:
        return self._sensitivity_result

    @property
    def sensitivity_error(self) -> str | None:
        """Why the last sensitivity run could not be completed, in plain words; ``None`` after one that was."""
        return self._sensitivity_error

    @property
    def sensitivity_seconds(self) -> float | None:
        """How long the sensitivity run held took, in seconds; ``None`` where none is held."""
        return self._sensitivity_seconds

    @property
    def sensitivity_workers(self) -> int | None:
        """The worker processes the sensitivity run held was made on; ``None`` where none is held."""
        return self._sensitivity_workers

    @property
    def sensitivity_note(self) -> str | None:
        """Why the sensitivity result is hidden; ``None`` while it is shown."""
        return self._sensitivity_note

    @property
    def profiled_fit(self) -> FitResult | None:
        """The fit the Ka profile belongs to; ``None`` when there is none to show."""
        return self._profiled_fit

    @property
    def profile(self) -> ProfileSet | None:
        """The Ka profile of :attr:`profiled_fit`; ``None`` while it runs, failed, or for an assay without a Ka."""
        return self._profile

    @property
    def profile_error(self) -> str | None:
        """Why the Ka profile of :attr:`profiled_fit` could not be worked out, in plain words; ``None`` otherwise."""
        return self._profile_error

    def fit_view(self) -> tuple[FitResult | None, str | None]:
        """The fit a summary describes, and the note hiding it (``None`` while it is shown).

        The latest shown fit, or the latest held fit when every one is hidden.
        """
        shown = self.fit_results
        if shown:
            return shown[-1], None
        held = self._held_fit_results
        return (held[-1], self._hidden_fit_notes[held[-1].id]) if held else (None, None)

    def hidden_results_note(self) -> str | None:
        """Why result exports and picks are unavailable: the note of the latest fit when every held fit is hidden.

        ``None`` while any result is shown, or when none is held: exports and
        picks then act on the shown results only.
        """
        return self.fit_view()[1]

    def other_hidden_note(self) -> str | None:
        """A note naming the held fits that are hidden while others are shown; ``None`` otherwise."""
        hidden = [r for r in self._held_fit_results if r.id in self._hidden_fit_notes]
        if not self.fit_results or not hidden:
            return None
        n = len(hidden)
        head = f'{n} of the {len(self._held_fit_results)} fits {"is" if n == 1 else "are"} hidden and not drawn.'
        latest = self.mismatch_note(hidden[-1], 'hidden fit' if n == 1 else 'latest hidden fit', 'run the fit again')
        return f'{head} {latest}'

    @_edit
    def check_results(self) -> None:
        """Show every held result whose record matches the loaded selection and the settings, and hide the rest.

        No number is recomputed: a hidden result is shown again exactly as it
        was. A change that hides a result replaces the status bar's message
        about it, which described results the views no longer show.
        """
        notes: dict[str, str] = {}
        for result in self._held_fit_results:
            note = self.mismatch_note(result, 'fit', 'run the fit again')
            if note is not None:
                notes[result.id] = note
        sensitivity_note = None
        if self._sensitivity_result is not None:
            sensitivity_note = self.mismatch_note(
                self._sensitivity_result.baseline_fit,
                'sensitivity analysis',
                'run the analysis again',
                uncertainties=False,
            ) or self._sensitivity_inputs_note(self._sensitivity_result)
        changed = notes != self._hidden_fit_notes or sensitivity_note != self._sensitivity_note
        self._hidden_fit_notes = notes
        self._sensitivity_note = sensitivity_note
        if changed and (notes or sensitivity_note):
            self.show_status(_RESULTS_HIDDEN_NOTE)
        self._note(Change.RESULTS)

    def mismatch_note(
        self, result: FitResult | None, what: str, redo: str, *, uncertainties: bool = True
    ) -> str | None:
        """Why *result* does not describe the loaded selection, as a short plain note; ``None`` when it does.

        The one match test for every result the session holds. *result*
        matches when it was made on the loaded data (the same
        ``data_fingerprint``), every replicate it used is active and every
        active replicate was given to it, its conditions equal the entered ones
        by value (a unit switch changes nothing) and describe the same dilution
        by the titrant, its assay type is the one selected, it was made under
        the parameter bounds and in the replicate mode set now (the bounds
        decide where the search runs and whether an interval end is open, the
        mode which replicates the fit keeps), and — for a fit, whose interval
        accounts for them — the error sources it was made with are the ones set
        now. The note names what differs and how to undo it. *what* names the
        result ("fit") and *redo* how to make a new one ("run the fit again").
        With no data loaded the replicates cannot be compared. *uncertainties*
        is ``False`` for a sensitivity analysis' baseline, which is fitted with
        the uncertainties stripped because the analysis draws them itself; the
        analysis' own record of them is compared by
        :meth:`_sensitivity_inputs_note`.
        """
        ms = self.measurement_set
        settings = self._settings
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

        assay_type = settings.assay_type
        if result.assay_type != assay_type.name:
            theirs = ASSAY_NAMES[AssayType[result.assay_type]][0]
            made += f' for {theirs}'
            changes.append(f'the model is now {ASSAY_NAMES[assay_type][0]}')
            fixes.append(f'switch the model back to {theirs}')
        else:
            entered = settings.conditions
            if not same_inputs(result.conditions, entered):
                keys = [
                    key
                    for key, value in result.conditions.items()
                    if key in entered
                    and self._condition_name(key) is not None
                    and not same_inputs({key: value}, {key: entered[key]})
                ]
                if keys:
                    stored = {key: self._format_condition(key, result.conditions[key]) for key in keys}
                    made += ' with ' + and_join([f'{self._condition_name(key)} = {stored[key]}' for key in keys])
                    changes += [
                        f'{self._condition_name(key)} is now {self._format_condition(key, entered[key])}'
                        if math.isfinite(entered[key].magnitude)
                        else f'{self._condition_name(key)} cannot be read now'
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
            bounds, bound_fixes = self._bounds_mismatch(result)
            changes += bounds
            fixes += bound_fixes
            recorded_mode = result.fit_config.get('per_replicate')
            per_replica = settings.per_replica
            # A calibration without a binding constant is fitted from the average in either mode.
            if recorded_mode is not None and projectable(assay_type) and recorded_mode != per_replica:
                changes.append(f'fitting each replicate separately is now switched {"on" if per_replica else "off"}')
                fixes.append(f'switch it back {"off" if per_replica else "on"}')

        if not changes:
            used = ErrorModel.from_dict(result.fit_config)
            if uncertainties and used != settings.errors:
                return _INPUTS_CHANGED_NOTE.format(stated=_stated_as(result))
            return None
        fix = fixes[0] if len(fixes) == 1 else 'change these back'
        # A dilution difference names nothing the result was made with — the
        # choice is on or off — so with nothing else differing the note has no
        # opening clause to carry and starts at the change itself.
        head = f'{made}. ' if made != opening else ''
        return f'{head}{_capitalized(and_join(changes))}. {_capitalized(fix)}, or {redo}.'

    def _condition_name(self, key: str) -> str | None:
        """Plain-text name of condition *key* in the selected assay's form; ``None`` when the form has no such field."""
        found = condition_field(self._settings.assay_type, key)
        return None if found is None else condition_name(found)

    def _format_condition(self, key: str, value: Quantity) -> str:
        """*value* of condition *key* in plain text, in the unit its field shows: ``4.3 µM``."""
        found = condition_field(self._settings.assay_type, key)
        if found is None:
            raise KeyError(key)
        return format_condition(found, value, self._settings.condition_units.get(key, found.unit))

    def _bounds_mismatch(self, result: FitResult) -> tuple[list[str], list[str]]:
        """Which parameter bounds differ from the ones *result* was made under, and how to undo it.

        Two empty lists when none does. A record lists only the bounds that
        differ from the registry defaults, so a parameter it does not list was
        made under its default; a record with no bounds entry at all is not
        compared. A row that cannot be read describes no bounds, so it differs
        from any.
        """
        if 'custom_bounds' not in result.fit_config:
            return [], []
        meta = ASSAY_REGISTRY[AssayType[result.assay_type]]
        recorded = result.fit_config['custom_bounds'] or {}
        changes: list[str] = []
        fixes: list[str] = []
        for key, shown in self._settings.bounds.items():
            unit = meta.units.get(key, '')
            if key in recorded:
                lo, hi, recorded_unit = recorded[key]
                made = [
                    Q_(-math.inf if lo is None else lo, recorded_unit),
                    Q_(math.inf if hi is None else hi, recorded_unit),
                ]
            else:
                made = [bound if isinstance(bound, Quantity) else Q_(bound, unit) for bound in meta.default_bounds[key]]
            made_values = [float(bound.to(unit).magnitude) for bound in made]
            name = fmt_param_plain(key)
            if shown is None:
                changes.append(f'the {name} bounds cannot be read now')
            else:
                shown_values = [float(bound.to(unit).magnitude) for bound in shown]
                if np.allclose(shown_values, made_values, rtol=1e-12, atol=0.0):
                    continue
                changes.append(f'the {name} bounds are now {_bounds_text(*shown_values, unit)}')
            fixes.append(f'set them back to {_bounds_text(*made_values, unit)}')
        return changes, fixes

    def _dilution_mismatch(self, stored: Mapping, entered: Mapping) -> tuple[list[str], list[str]]:
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
        return and_join([self._condition_name(key) or key for key in keys])

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
        stated = self._settings.errors
        if result.config.mode is SensitivityMode.HEATMAP:
            stated = ErrorModel(specs={key: stated.specs[key] for key in used.specs if key in stated.specs})
        return None if used == stated else _SENSITIVITY_INPUTS_NOTE

    # ------------------------------------------------------------------
    # Imported results
    # ------------------------------------------------------------------

    def import_refusal(self) -> Refusal | None:
        """Why results cannot be imported now — a fit running, whose result would replace them — or ``None``."""
        if self.fit_running():
            return Refusal('Fit Running', _FIT_RUNNING_IMPORT_NOTE)
        return None

    def check_imported(self, results: Sequence[FitResult], name: str) -> ImportCheck:
        """Check results read from the file *name* against the loaded data; nothing is held yet.

        Each result is checked by
        :func:`~core.pipeline.results_io.verify_imported_result`: one that
        does not describe the loaded data, or whose check fails, is refused
        with the reason (:func:`_refusal_reason`). With data loaded the notice
        names the results the check could not judge or had to recompute.
        """
        ms = self.measurement_set
        accepted: list[FitResult] = []
        refused: dict[str, int] = {}  # reason -> how many results it refuses
        rescored = unverified = False
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
            rescored = rescored or status == 'rescored_legacy'
            unverified = unverified or (status == 'unverifiable' and ms is not None)
            accepted.append(checked)
        refusal = None
        if refused:
            imported = 'nothing was imported' if not accepted else 'they were left out'
            paragraphs = []
            for reason, count in refused.items():
                which = 'The results' if count == len(results) else f'{count} of the {len(results)} results'
                paragraphs.append(_REFUSALS[reason].format(which=which, name=name, imported=imported))
            refusal = '\n\n'.join(paragraphs)
        notices = []
        if rescored:
            notices.append(
                f'Some numbers stored in {name} did not describe the replicates each fit used, so the R², RMSE and '
                'curve were recomputed on those replicates.'
            )
        if unverified:
            notices.append(
                f'Some results in {name} could not be checked against the data loaded now, because this version '
                'cannot recompute their R² and RMSE closely enough to tell. They are shown as stored in the file; '
                'fit the data again to get results that are checked.'
            )
        return ImportCheck(accepted, refusal, '\n\n'.join(notices) or None)

    @_edit
    def show_imported(self, results: list[FitResult], path: str, appearance: PlotAppearance | None = None) -> None:
        """Hold *results*, checked by :meth:`check_imported`, in place of the fits held now.

        *appearance* is the plot appearance the results file records, which the session
        takes; a file that records none (``None``) leaves the session's own.
        """
        if appearance is not None:
            self.set_plot_appearance(appearance)
        # Imported fits carry no Ka profile; the profile waits for the next fit.
        self._clear_profile()
        self._held_fit_results = results
        self.check_results()
        self.show_status(f'Imported {len(results)} result(s) from {path}')

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------

    def fit_running(self) -> bool:
        """Whether a fit started in this session is still running."""
        return self._fit_worker is not None

    def sensitivity_running(self) -> bool:
        """Whether a sensitivity analysis started in this session is still running."""
        return self._sensitivity_worker is not None

    def profile_running(self) -> bool:
        """Whether the Ka profile of the latest fit is still being computed."""
        return self._profile_worker is not None

    def set_up_demo(self) -> Refusal | None:
        """State the demo's settings and load its bundled titration (:data:`gui.dataset.DEMO_IDA`), without fitting it.

        The same settings whatever the session held before:

        - the IDA assay with its default conditions (Ka,dye 16.8 MM⁻¹, [Host]₀ 4.3 µM,
          [Dye]₀ 6 µM), constant totals and default parameter bounds;
        - the input uncertainties of :data:`DEMO_UNCERTAINTIES` — Ka,dye σ 10 %, [Host]₀,
          [Dye]₀ and the titrant σ 3 % each — and no shared source or error of the
          additions, so the first fit reports the interval that covers them, with the
          conditional one beside it;
        - the replicates averaged without the per-replicate test;
        - Outlier removal at its defaults (:data:`gui.dataset.OUTLIER_DEFAULTS`: Z-score
          threshold 3.5, Min replicates 3), which Measurement settings then shows.

        Says why where the demo cannot be set up: its data missing, or work running here.
        """
        if not DEMO_IDA.exists():
            return Refusal(
                'Demo Data Missing',
                f'The demo data ({DEMO_IDA.name}) are missing from this installation. Reinstall SupraSimFit to '
                'bring them back.',
            )
        busy = self.busy_note()
        if busy is not None:
            return Refusal('Already Running', busy)
        self.binding.set_assay(AssayType.IDA)
        self.binding.set_per_replica(False)
        self.binding_edited()
        self.uncertainty.set_specs(DEMO_UNCERTAINTIES)
        self.uncertainty_edited()
        # Loading resets the replicates and clears the results.
        return self.load_files([str(DEMO_IDA)]) or self.remove_outliers(*OUTLIER_DEFAULTS)

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

    def running(self) -> bool:
        """Whether this session has any work running: a fit, its Ka profile or a sensitivity analysis."""
        return self.fit_running() or self.profile_running() or self.sensitivity_running()

    def progress_fraction(self) -> float | None:
        """How much of the running work is done (0–1), or ``None`` while it cannot be counted."""
        if self.sensitivity_running() and self._progress is not None and self._progress[1] > 0:
            done, total = self._progress
            return done / total
        return None

    def running_label(self) -> str:
        """The running work in a few words (``fitting``, ``Ka profile``, ``Sensitivity 62 %``); ``''`` when idle."""
        if self.fit_running():
            return 'fitting'
        if self.sensitivity_running():
            fraction = self.progress_fraction()
            return 'Sensitivity' if fraction is None else f'Sensitivity {fraction:.0%}'.replace('%', '\u202f%')
        if self.profile_running():
            return 'Ka profile'
        return ''

    # ------------------------------------------------------------------
    # Summaries for the window
    # ------------------------------------------------------------------

    def detail(self) -> str:
        """The session's second line: ``IDA · 8 replicates``, or ``No data loaded``."""
        ms = self.measurement_set
        if ms is None:
            return 'No data loaded'
        short = ASSAY_NAMES[self.settings.assay_type][0]
        return f'{short} · {_count(ms.n_replicas, "replicate")}'

    def file_card(self) -> tuple[str, str]:
        """The file behind the session and its shape: (``IDA_system.txt``, ``IDA · 8 replicates × 12 points``)."""
        ms = self.measurement_set
        if ms is None:
            return 'No data loaded', 'Load data to start'
        files = self._dataset.files
        name = files[0].name if files else 'Data'
        if len(files) > 1:
            name += f' + {len(files) - 1} more'
        short = ASSAY_NAMES[self.settings.assay_type][0]
        return name, f'{short} · {_count(ms.n_replicas, "replicate")} × {ms.n_points} points'

    def warnings(self) -> int:
        """How many warnings the fit on show carries: the warning callouts of Fit results."""
        return sum(spec.tone == 'warning' for spec in self.callouts('Fit results'))

    def callouts(self, view: str) -> list[CalloutSpec]:
        """The callouts *view* shows above its content: the one list the view draws and its navigation mark reads.

        Fit results speaks of the fit on view and the fits drawn beside it; Ka confidence of
        that fit, while it has a binding constant to profile; Sensitivity of the run on
        show, or of why the last one failed. Every other view shows none.
        """
        fit, note = self.fit_view()
        shown = fit if note is None else None
        ms = self.measurement_set
        if view == 'Fit results':
            return R.callouts(
                shown,
                note,
                others=self.fit_results[:-1],
                order=None if ms is None else ms.replica_ids,
                unchecked=shown is not None and ms is None,
                others_hidden=self.other_hidden_note(),
            )
        if view == 'Ka confidence':
            has_ka = shown is not None and self.empty_view(view) is None
            ours = shown is not None and self.profiled_fit is shown
            return CF.callouts(
                shown if has_ka or note else None,
                note,
                pending=ours and self.profile_running(),
                unchecked=has_ka and ms is None,
                others_hidden=self.other_hidden_note() if has_ka else None,
            )
        if view == 'Sensitivity':
            settings = self.settings
            if not projectable(settings.assay_type):
                return []
            return S.callouts(
                self.sensitivity_result,
                shown,
                self.sensitivity_note,
                running=self.sensitivity_running(),
                error=self.sensitivity_error,
                nothing_varies=ms is not None and not settings.errors.varies,
            )
        return []

    def _warns(self, view: str) -> bool:
        """Whether a callout *view* shows carries a warning."""
        return any(spec.tone == 'warning' for spec in self.callouts(view))

    def summary(self) -> tuple[str, str, float]:
        """The session's state for the switcher: (glyph state, state in words, progress 0–1).

        Running work first (``Fitting``, ``Sensitivity · 62 %``), then a result that
        needs a refit, then the reported Ka with its warnings, one binding constant
        by its value and two by their count.
        """
        if self.running():
            label = self.running_label()
            fraction = self.progress_fraction()
            words = label[:1].upper() + label[1:]
            if fraction is not None:
                words = f'Sensitivity · {fraction:.0%}'.replace('%', '\u202f%')
            return 'running', words, fraction or 0.0
        fit, note = self.fit_view()
        if note is not None:
            return 'stale', 'Needs refit', 0.0
        if fit is None:
            return '', 'Not fitted' if self.measurement_set is not None else '', 0.0
        rows = [row for row in summarize_parameters(fit) if not row.is_log and row.key in (fit.intervals or {})]
        if len(rows) == 1:
            row = rows[0]
            side = {'low': 'below', 'high': 'above'}.get(row.estimate_at_bound)
            value = fmt_value(row.estimate)
            words = f'Ka not limited {side}' if side else f'Ka {value} {fmt_unit_pretty(row.unit)}'
        else:
            words = f'{len(rows)} binding constants'
        n = self.warnings()
        if n:
            words += f' · {_count(n, "warning")}'
        return ('warning' if n else 'done'), words, 0.0

    def is_empty(self) -> bool:
        """Whether the session holds nothing and runs nothing: no data, no results, no work."""
        return self.measurement_set is None and not self.held_fit_results and not self.running()

    def empty_view(self, view: str) -> EmptyView | None:
        """What *view* shows in place of its content, or ``None`` where it has content to show.

        One rule for every view of :data:`EMPTY_VIEWS`, which reads the work running: a fit
        or an analysis on its way is said as running, never as not made. A result the data
        no longer match is content — its view says so in a callout — and a model with no
        binding constant leaves Ka confidence and Sensitivity nothing to follow.
        """
        ms = self.measurement_set
        if view in ('Fit results', 'Ka confidence'):
            fit, note = self.fit_view()
            if fit is not None:
                if view == 'Ka confidence' and note is None and not projectable(AssayType[fit.assay_type]):
                    return EmptyView('No binding constant', NO_KA_TO_PROFILE)
                return None
            if self.fit_running():
                return EmptyView('Fit running', 'The fit is running. Its results appear here when it finishes.')
            if ms is not None:
                key = _shortcut(RUN_FIT_KEY)
                return EmptyView(
                    'No fit yet', f'Check the binding model and its conditions, then choose Run fit ({key}).'
                )
        elif view == 'Sensitivity':
            if not projectable(self.settings.assay_type):
                return EmptyView('No binding constant', NO_KA_TO_FOLLOW)
            if self.sensitivity_result is not None:
                return None
            if self.sensitivity_running():
                return EmptyView(
                    'Analysis running',
                    'The analysis is running. Its results appear here when it finishes; the status bar counts its fits.',
                )
            if ms is not None:
                run = f'choose Run analysis ({_shortcut(RUN_ANALYSIS_KEY)})'
                steps = (
                    run
                    if self.settings.errors.varies
                    else f'state how uncertain each input is under Input uncertainty, then {run}'
                )
                return EmptyView('No analysis yet', f'{steps[0].upper()}{steps[1:]}.')
        elif view in ('Measurements', 'Plot appearance'):
            if ms is not None or (view == 'Plot appearance' and self.fit_results):
                return None
        else:
            return None
        if self.is_empty():
            return EmptyView(
                'No data loaded',
                f'{_LOAD_DATA[view]}, or try the demo data: an indicator displacement titration, fitted as it loads.',
                offers_data=True,
            )
        return EmptyView(
            'No data loaded', f'{_LOAD_DATA[view]} with Load data; they take the place of the results held.'
        )

    def save_folder(self) -> Path:
        """The folder a save offers first: the data file's own, or Documents where the data are a bundled example
        (inside the app) or come from no file."""
        src = self.dataset_file()
        if src and not bundled(src) and Path(src).parent.is_dir():
            return Path(src).parent
        documents = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation))
        return documents if documents.is_dir() else Path.home()

    def view_status(self, view: str) -> tuple[str, float]:
        """The navigation mark of *view* (see :func:`gui.design.components.paint_status_glyph`) and its progress."""
        ms = self.measurement_set
        settings = self.settings
        if view == 'Measurements':
            return ('done' if ms is not None else ''), 0.0
        if view == 'Binding model':
            ok = ms is not None and not settings.assay_problems and not settings.bound_problems
            return ('done' if ok else ''), 0.0
        if view == 'Input uncertainty':
            return ('done' if ms is not None and not settings.input_problems else ''), 0.0
        if view == 'Fit results':
            if self.fit_running():
                return 'running', 0.0
            fit, note = self.fit_view()
            if note is not None:
                return 'stale', 0.0
            if fit is None:
                return '', 0.0
            return ('warning' if self._warns(view) else 'done'), 0.0
        if view == 'Ka confidence':
            if self.profile_running():
                return 'running', 0.0
            held = self.held_fit_results
            if not held:
                return '', 0.0
            if held[-1].id in self.hidden_fit_notes:
                return ('stale' if self.profile is not None else ''), 0.0
            if self._warns(view):
                return 'warning', 0.0
            return ('done' if self.profile is not None else ''), 0.0
        if view == 'Sensitivity':
            if self.sensitivity_running():
                return 'running', self.progress_fraction() or 0.0
            if self._warns(view):
                return 'warning', 0.0
            if self.sensitivity_result is None:
                return '', 0.0
            return ('stale' if self.sensitivity_note is not None else 'done'), 0.0
        return '', 0.0

    def model_line(self) -> list[str]:
        """What the fit is, for the status bar: the model, its binding constants, the interval and the weighting."""
        fit, _ = self.fit_view()
        assay_type = AssayType[fit.assay_type] if fit is not None else self.settings.assay_type
        parts = [ASSAY_NAMES[assay_type][1], binding_constants(assay_type)]
        if projectable(assay_type):
            parts.append('Profile likelihood, 95\u202f%')
        noise = None if fit is None else fit.noise
        if noise is not None and noise.share > 0:
            parts.append('Weighted by noise law')
        return parts

    def stock_problem(self) -> str | None:
        """Why the titrant stock entered cannot be the one the loaded data were made from; ``None`` when it can.

        The one check of the conditions that needs the data: a sample cannot hold more
        titrant than the stock it was made from, so the stock has to be more
        concentrated than every titrant concentration measured. A stock that has not
        been entered at all is already the form's own problem, so it is not measured
        against the data as well.
        """
        ms = self.measurement_set
        stock = self._settings.conditions.get(TITRANT_STOCK)
        if ms is None or stock is None or not stock.magnitude > 0:
            return None
        concentrations = np.asarray(ms.concentrations, dtype=float)
        finite = concentrations[np.isfinite(concentrations)]
        if not finite.size or float(finite.max()) < stock.magnitude:
            return None
        entered = self._format_condition(TITRANT_STOCK, stock)
        highest = self._format_condition(TITRANT_STOCK, Q_(float(finite.max()), 'M'))
        if entered == highest:
            return _STOCK_NOT_ABOVE_DATA.format(highest=highest)
        return _STOCK_BELOW_DATA.format(stock=entered, highest=highest)

    def _settings_refusal(self, verb: str) -> Refusal | None:
        """The first view whose settings cannot be used, with every problem it has; ``None`` when all can."""
        for title, problems, place in (
            (
                'Binding model',
                [*self._settings.assay_problems, self.stock_problem(), *self._settings.bound_problems],
                Place.BINDING_PROBLEM,
            ),
            ('Input uncertainty', self._settings.input_problems, Place.INPUT_PROBLEM),
        ):
            problems = [problem for problem in problems if problem]
            if problems:
                return Refusal(title, _problem_list(verb, problems), place)
        return None

    @_edit
    def run_fit(self) -> Refusal | None:
        """Start a background fit on a copy of the loaded data, so later changes never reach it; or say why not."""
        ms = self.measurement_set
        if ms is None:
            return Refusal('No Data', 'Load a measurement file first.')
        busy = self.busy_note()
        if busy is not None:
            return Refusal('Already Running', busy)
        # Fitting with column indices 1..N as concentrations would silently
        # produce meaningless Ka values. Any plate-reader import that lacks
        # concentrations sets this flag, whatever the instrument.
        if ms.metadata.get(BMG_PLACEHOLDER_KEY):
            return Refusal(
                'Concentrations Required',
                'This dataset has placeholder concentrations. Enter the real '
                'concentration list in Measurements before running the fit.',
                Place.CONCENTRATIONS,
            )
        refusal = self._settings_refusal('fit')
        if refusal is not None:
            return refusal

        settings = self._settings
        # The uncertainties, the random error of each addition included, widen
        # the reported interval to cover them; a fit that cannot be made with
        # the inputs as free as they were stated to be names them in its
        # refusal the way the panel names them.
        config = replace(settings.fit_config(), errors=settings.errors, input_labels=dict(settings.input_labels))

        fitting = 'Fitting…'
        if config.per_replica and 1 < ms.n_active < REPLICATE_TEST_MIN and projectable(settings.assay_type):
            # With fewer replicates than the replicate test can judge, every active
            # one is averaged; said in the one message the bar keeps while it fits.
            fitting = (
                f'Fitting {ms.n_active} replicates — too few to test against each other (the test needs three), '
                'so all of them are used…'
            )

        self._fit_worker = FitWorker(
            ms.with_active(ms.active_replica_ids),
            assay_class(settings.assay_type),
            dict(settings.conditions),
            config,
            source_file=self._source_file,
            parent=self,
        )
        self._fit_worker.finished.connect(self._on_fit_complete)
        self._fit_worker.error.connect(self._on_fit_error)
        self._fit_worker.start()
        self._note(Change.RUN)
        self.show_status(fitting)
        return None

    @_edit
    def cancel_fit(self) -> None:
        """Stop the fit running in this session, leaving every result as it was before it started.

        A cancelled fit reports nothing, so whatever was shown — the previous
        fit and its Ka profile, where there was one — still stands, and the
        next fit can start as soon as this one has stopped.
        """
        if self._fit_worker is None:
            return
        self._stop_fit()
        self.show_status('Fit stopped — nothing in the session was changed.')

    @_edit
    def _on_fit_complete(self, result: FitResult) -> None:
        worker = self._fit_worker
        if self.sender() is not worker:
            return  # a fit whose data were replaced while it ran
        self._fit_worker = None
        retire(worker)
        self._note(Change.RUN)

        # The fit is held, then shown or hidden by the selection as it is now.
        self._held_fit_results = [result]
        self.check_results()
        # The previous fit's profile describes data this one replaces, and only
        # one profile worker is reachable at a time: drop it through the one
        # path that sees its thread out.
        self._stop_profile()
        self._profiled_fit = result
        self._profile = None
        self._profile_error = None
        if projectable(AssayType[result.assay_type]):
            # Profile the replicates the fit used, so the profile describes the
            # same data. The fit already worked out the penalised profiles
            # behind its interval: they are drawn rather than computed again,
            # with the weights and design effects the fit ran with.
            ms = worker.ms.with_active(fit_replica_ids(result))
            self._profile_worker = ProfileWorker(
                ms, worker.assay_cls, worker.conditions, worker.config, result, parent=self
            )
            self._profile_worker.finished.connect(self._on_profile_complete)
            self._profile_worker.error.connect(self._on_profile_error)
            self._profile_worker.start()
        self._note(Change.PROFILE)

        hidden = self._hidden_fit_notes.get(result.id)
        if hidden is not None:
            self.show_status(f'Fit complete but hidden — {hidden}')
            return
        left_out = _left_out_text(result, worker.ms.replica_ids)
        used = fit_replica_ids(result) or []
        given = input_replica_ids(result) or used
        # Counted against every loaded replicate, as Fit details and the badge count them.
        counted = f', {len(used)} of {len(worker.ms.replica_ids)} replicates used' if given else ''
        if (
            result.fit_config.get('per_replicate')
            and 'replicate_test' not in result.metadata
            and 1 < len(given) < REPLICATE_TEST_MIN
        ):
            counted += ', too few to test against each other'
        on_bound = fmt_bound_note(parameters_on_bound(result))
        open_ka = _open_note(result)
        verdict = _verdict_note(result)
        self.show_status(
            f'Fit complete — R² {fmt_r2(result.r_squared)}, RMSE {fmt_rmse(result.rmse)}{counted}'
            f'{f" ({left_out})" if left_out else ""}{f" — {open_ka}" if open_ka else ""}'
            f'{f" — {on_bound}" if on_bound else ""}{f" — {verdict}" if verdict else ""}'
        )

    @_edit
    def _on_fit_error(self, msg: str) -> None:
        worker = self._fit_worker
        if self.sender() is not worker:
            return
        self._fit_worker = None
        retire(worker)
        self._note(Change.RUN)
        self._warn('Fit Error', msg)
        self.show_status(f'Fit failed: {msg}')

    def _stop_fit(self) -> None:
        """Stop a fit still running and wait for it, so its result is never shown and its thread is gone."""
        worker = self._fit_worker
        if worker is None:
            return
        self._fit_worker = None
        worker.cancel()
        retire(worker)
        self._note(Change.RUN)

    @_edit
    def _on_profile_complete(self, profile: ProfileSet) -> None:
        worker = self._profile_worker
        if self.sender() is not worker:
            return  # the fit this profile belongs to has been replaced
        self._profile_worker = None
        retire(worker)
        self._profile = profile
        self._note(Change.PROFILE)

    @_edit
    def _on_profile_error(self, msg: str) -> None:
        worker = self._profile_worker
        if self.sender() is not worker:
            return
        self._profile_worker = None
        retire(worker)
        self._profile_error = msg
        self.show_status('The Kₐ profile could not be worked out — the fit itself is unaffected. See Ka confidence.')
        self._note(Change.PROFILE)

    def _stop_profile(self) -> None:
        """Stop the Ka profile still being computed and see its thread out."""
        worker = self._profile_worker
        if worker is None:
            return
        self._profile_worker = None
        worker.cancel()
        retire(worker)

    def _clear_profile(self) -> None:
        """Drop the Ka profile and the fit it belongs to, stopping its computation."""
        self._stop_profile()
        self._profiled_fit = None
        self._profile = None
        self._profile_error = None
        self._note(Change.PROFILE)

    def sensitivity_refusal(self, problems: Sequence[str] = ()) -> Refusal | None:
        """Why the sensitivity analysis cannot start now; ``None`` when it can.

        *problems* are the analysis' own settings' problems with the stated
        uncertainties, one sentence each, judged after every other check.
        """
        ms = self.measurement_set
        if ms is None:
            return Refusal('No Data', 'Load a measurement file first.')
        if self.fit_running():
            return Refusal('Already Running', _FIT_RUNNING_ANALYSIS_NOTE)
        if self.sensitivity_running():
            return Refusal('Already Running', _SENSITIVITY_RUNNING_ANALYSIS_NOTE)
        if not projectable(self._settings.assay_type):
            return Refusal(
                'Sensitivity Analysis',
                'The selected assay has no association constant for the analysis to follow. '
                'Pick a binding assay to run a sensitivity analysis.',
            )
        refusal = self._settings_refusal('analysis')
        if refusal is not None:
            return refusal
        # The analysis draws the inputs from the error sources stated, the same
        # ones the fit's interval accounts for.
        if not self._settings.errors.varies:
            return Refusal('Sensitivity Analysis', NOTHING_VARIES, Place.INPUTS)
        if problems:
            return Refusal('Sensitivity Analysis', _problem_list('analysis', problems), Place.ANALYSIS_PROBLEM)
        return None

    def sensitivity_cost_note(self, config: SensitivityConfig) -> str | None:
        """What a long analysis will cost, to put to the user before it starts; ``None`` for a short one."""
        n_inputs = len(self._settings.input_labels)
        # Every fit the run makes: the perturbations, the refits the
        # elasticities take, and the baseline.
        curve_fits = estimated_fit_count(config, n_inputs) + 1
        worker_count = preferences.worker_count()
        solves = estimated_model_solves(config, self._settings.fit_config(), self._settings.assay_type, n_inputs)
        if solves <= LONG_RUN_SOLVES:
            return None
        spread = 'one at a time' if worker_count == 1 else f'{worker_count} at a time'
        return (
            f'Your data will be re-fitted about {curve_fits:,} times to measure how much '
            f'the result moves, {spread}.\n\nYou can stop it at any point once it starts, '
            f'and the progress bar will estimate the time left.\n\n'
            f'Start the analysis?'
        )

    @_edit
    def run_sensitivity(self, config: SensitivityConfig) -> Refusal | None:
        """Start a background Ka input-sensitivity run of *config*, or say why it cannot start."""
        refusal = self.sensitivity_refusal()
        if refusal is not None:
            return refusal
        ms = self.measurement_set
        settings = self._settings
        self._run_workers = preferences.worker_count()
        self._sensitivity_worker = SensitivityWorker(
            ms.with_active(ms.active_replica_ids),
            assay_class(settings.assay_type),
            dict(settings.conditions),
            settings.fit_config(),
            config,
            max_workers=self._run_workers,
            input_labels=dict(settings.input_labels),
            parent=self,
        )
        self._sensitivity_worker.progress.connect(self._on_sensitivity_progress)
        self._sensitivity_worker.finished.connect(self._on_sensitivity_complete)
        self._sensitivity_worker.stopped.connect(self._on_sensitivity_stopped)
        self._sensitivity_worker.error.connect(self._on_sensitivity_error)

        self._sensitivity_started = time.monotonic()
        self._progress = None
        self._sensitivity_error = None
        self._sensitivity_worker.start()
        self._note(Change.RUN)
        self.show_status('Running sensitivity analysis…')
        return None

    @_edit
    def cancel_sensitivity(self) -> None:
        """Ask the running sensitivity analysis to stop; it reports what it finished."""
        if self._sensitivity_worker is not None:
            self._sensitivity_worker.cancel()
            self.show_status(STOPPING_TEXT)

    @_edit
    def _on_sensitivity_progress(self, done: int, total: int) -> None:
        """Report progress, with a time estimate once there is enough to judge.

        A run that has been asked to stop reports that instead: the counts still
        arrive from the fits that were already running, and a rising count in
        the status bar beside a page that says it is stopping reads as two
        contradictory answers.
        """
        self._progress = (done, total)
        self._note(Change.PROGRESS)
        if self._sensitivity_worker is not None and self._sensitivity_worker.cancelled:
            self.show_status(STOPPING_TEXT)
            return
        elapsed = time.monotonic() - self._sensitivity_started
        if 3 <= done < total and elapsed > 0:
            remaining = elapsed / done * (total - done)
            self.show_status(f'Analysing — {done:,} of {total:,}, about {_format_remaining(remaining)} left')
        else:
            self.show_status(f'Analysing — {done:,} of {total:,}')

    @_edit
    def _on_sensitivity_complete(self, result: SensitivityResult) -> None:
        worker = self._sensitivity_worker
        if self.sender() is not worker:
            return  # a run whose data were replaced while it went
        self._sensitivity_worker = None
        cancelled = worker is not None and worker.cancelled
        retire(worker)
        self._sensitivity_result = result
        self._sensitivity_seconds = time.monotonic() - self._sensitivity_started
        self._sensitivity_workers = self._run_workers
        # Shown or hidden by the selection as it is now, before any view draws it.
        self.check_results()
        self._note(Change.SENSITIVITY | Change.RUN)
        hidden = self._sensitivity_note
        if hidden is not None:
            # The counts describe a result no view is showing, so the note takes their place.
            self.show_status(f'Sensitivity {"stopped" if cancelled else "complete"} but hidden — {hidden}')
            return
        # Counted as the cost note and the progress bar count: every fit the
        # run makes, the baseline included. The baseline is this result, so it
        # succeeded; only the perturbed fits could have failed.
        planned = result.n_planned + 1
        succeeded = result.n_success + 1
        if cancelled and result.mode is SensitivityMode.SOBOL:
            # A stopped Sobol run keeps whole sample blocks only, and is counted as the tab counts it.
            self.show_status(
                f'Sensitivity stopped — the results rest on the {result.n_blocks_finished} of {_SOBOL_BLOCKS} '
                'sample blocks that finished before you cancelled'
            )
        elif cancelled:
            self.show_status(f'Sensitivity stopped — {succeeded:,} of {planned:,} fits succeeded before you cancelled')
        else:
            self.show_status(f'Sensitivity complete — {succeeded:,} of {planned:,} fits succeeded')

    @_edit
    def _on_sensitivity_stopped(self) -> None:
        """A run cancelled before it had a single finished fit: there is nothing to show for it."""
        worker = self._sensitivity_worker
        if self.sender() is not worker:
            return  # a run whose data were replaced while it went
        self._sensitivity_worker = None
        retire(worker)
        self._note(Change.SENSITIVITY | Change.RUN)
        self.show_status('Sensitivity stopped — no fits had finished')

    @_edit
    def _on_sensitivity_error(self, msg: str) -> None:
        worker = self._sensitivity_worker
        if self.sender() is not worker:
            return  # a run whose data were replaced while it went
        self._sensitivity_worker = None
        retire(worker)
        self._sensitivity_error = msg
        self._note(Change.RUN | Change.SENSITIVITY)
        self._warn('Sensitivity Analysis', msg)
        self.show_status(f'Sensitivity failed: {msg}')

    def _stop_sensitivity(self) -> None:
        """Stop a sensitivity run still going and wait for it, which also ends its worker processes."""
        worker = self._sensitivity_worker
        if worker is None:
            return
        self._sensitivity_worker = None
        worker.cancel()
        retire(worker)
        self._note(Change.RUN)

    def _clear_sensitivity(self) -> None:
        """Drop the sensitivity result and stop a run still going.

        The stopped run's signals reach nothing, so its result never describes
        data it was not computed on.
        """
        self._stop_sensitivity()
        self._sensitivity_result = None
        self._sensitivity_note = None
        self._sensitivity_error = None
        self._sensitivity_seconds = self._sensitivity_workers = None
        self._note(Change.SENSITIVITY)

    @_edit
    def stop(self) -> None:
        """Stop the work running in this session, as the toolbar's Stop does.

        A fit stops leaving every result as it was; an analysis reports what it
        finished; a Ka profile still being computed is dropped, and the fit it
        belongs to stays.
        """
        if self.fit_running():
            self.cancel_fit()
        if self.sensitivity_running():
            self.cancel_sensitivity()
        if self.profile_running():
            self._clear_profile()
            self.show_status('Ka profile stopped — run the fit again to compute it.')

    def cancel_running(self) -> None:
        """Ask every background run this session started to stop, without waiting for any of it.

        Each run ends at its next cancel check, so asking all of them first
        lets them stop side by side; waiting for one before asking the next
        would add up their stopping times on the interface thread.
        """
        for worker in (self._fit_worker, self._profile_worker, self._sensitivity_worker):
            if worker is not None:
                worker.cancel()

    @_edit
    def shutdown(self) -> None:
        """Stop every background run this session started and wait for its thread to end.

        Called before the session closes.
        """
        self.cancel_running()
        self._stop_fit()
        self._stop_profile()
        self._stop_sensitivity()
