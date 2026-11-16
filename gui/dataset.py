"""The data of one session: its files, the replicates they became, and the concentrations they share.

A session is one experiment. Its files are stacked as replicates on one concentration
grid (:func:`core.io.load_measurements_multi`); a multi-channel file (EnSight) is
loaded alone and shows one channel at a time. The concentrations are kept as entered —
their face values under the *imported unit* — so declaring another unit reinterprets
the numbers rather than converting them. Every change builds the new
:class:`MeasurementSet` first and keeps the old state when the data are refused, with
an :class:`InvalidData` written for the user. No widget is involved.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from core.data_processing.concentration import read_raw_concentrations, save_concentration_vector
from core.data_processing.measurement_set import InvalidData, MeasurementSet, concentration_problem
from core.data_processing.preprocessing import apply_preprocessing
from core.io import load_measurements, load_measurements_multi
from core.io.formats.bmg_reader import BMG_METADATA_KEY, BMG_PLACEHOLDER_KEY
from core.io.formats.ensight_reader import ENSIGHT_CHANNEL_COLUMN, ENSIGHT_METADATA_KEY, format_channel_label
from core.io.formats.jasco_reader import JASCO_METADATA_KEY
from core.io.registry import READERS, get_reader
from core.units import Q_
from gui.plotting.labels import parse_number

logger = logging.getLogger(__name__)

#: The concentration units a session's values can be stated in.
UNITS: tuple[str, ...] = ('nM', 'µM', 'mM', 'M')

#: The folder of the example datasets bundled with the app: inside the app, never a place to save to.
EXAMPLES = Path(__file__).resolve().parent.parent / 'data'

#: The bundled titration the demo loads: an indicator displacement assay (IDA) of eight replicates.
DEMO_IDA = EXAMPLES / 'IDA_system.txt'

#: The Z-score threshold and the least replicates in use that Outlier removal starts from, and the demo applies.
OUTLIER_DEFAULTS: tuple[float, int] = (3.5, 3)


def bundled(path: str) -> bool:
    """Whether *path* is one of the example datasets bundled with the app (:data:`EXAMPLES`)."""
    return Path(path).resolve().is_relative_to(EXAMPLES)


#: Each reader's format, as the Files table names it.
FORMATS = {
    'TxtReader': 'Tab-separated text',
    'CsvReader': 'CSV',
    'JascoReader': 'JASCO export',
    'EnsightReader': 'EnSight plate export',
    'XlsxReader': 'Excel workbook',
}

_METADATA_KEYS = (BMG_PLACEHOLDER_KEY, BMG_METADATA_KEY, ENSIGHT_METADATA_KEY, JASCO_METADATA_KEY)


def readable_extensions() -> list[str]:
    """The file extensions a reader is registered for, sorted."""
    return sorted(READERS)


def file_filter() -> str:
    """The open-file filter of every format a reader is registered for."""
    exts = ' '.join(f'*{ext}' for ext in readable_extensions())
    return f'Measurement files ({exts});;All files (*)'


def _unreadable(paths: list[str]) -> InvalidData:
    """Why *paths* did not load, naming them, for an error no reader wrote for the user."""
    names = ', '.join(Path(p).name for p in paths)
    formats = ', '.join(readable_extensions())
    if len(paths) == 1:
        return InvalidData(
            f'Could not read the measurements in {names}. Check that it is a measurement file SupraSimFit reads '
            f'({formats}), then load it again.'
        )
    return InvalidData(
        f'Could not load {names} as replicates of one measurement. Check that each is a measurement file '
        f'SupraSimFit reads ({formats}) and that all come from the same titration, then load them again.'
    )


def _unit_token(units) -> str | None:
    """The token of :data:`UNITS` whose pint unit is *units* (``'uM'`` reads as ``'µM'``); ``None`` for none."""
    return next((u for u in UNITS if Q_(1.0, u).units == units), None)


@dataclass(frozen=True)
class SourceFile:
    """One loaded file: its path, its format and the replicates it became."""

    path: str
    format: str
    replica_ids: tuple[str, ...]

    @property
    def name(self) -> str:
        return Path(self.path).name


class Dataset:
    """The data of one session: see the module docstring.

    Attributes
    ----------
    ms : MeasurementSet
        The replicates on the session's grid, molar.
    files : tuple[SourceFile, ...]
        The files, in the order loaded.
    imported_unit : str
        The unit the concentrations are stated in (:data:`UNITS`).
    face_values : numpy.ndarray
        The concentrations as stated, in *imported_unit*.
    channels : list[str]
        A multi-channel file's channels; empty for any other data.
    channel : str or None
        The channel shown.
    """

    def __init__(self) -> None:
        self.ms: MeasurementSet | None = None
        self.files: tuple[SourceFile, ...] = ()
        self.imported_unit = 'M'
        self.face_values = np.array([], dtype=np.float64)
        self.channels: list[str] = []
        self.channel: str | None = None
        self._channel_frame: pd.DataFrame | None = None
        self.outlier_result: dict | None = None

    # ------------------------------------------------------------------
    # Opening, adding and removing files
    # ------------------------------------------------------------------

    @classmethod
    def from_set(cls, ms: MeasurementSet, source_file: str | None) -> Dataset:
        """The dataset of *ms*, loaded elsewhere from *source_file* (or from nothing on disk)."""
        ds = cls()
        ds.ms = ms
        ds.face_values = np.asarray(ms.concentrations, dtype=np.float64).copy()
        if source_file:
            ds.files = (SourceFile(source_file, _format_of(source_file), tuple(ms.replica_ids)),)
        return ds

    @classmethod
    def open(cls, paths: list[str]) -> Dataset:
        """Load *paths* as the replicates of one experiment; a single file keeps its own channels and unit.

        Raises
        ------
        InvalidData
            When the files cannot be read or are not replicates on one grid.
        """
        ds = cls()
        if len(paths) == 1:
            ds._open_single(paths[0])
        else:
            ds._open_multiple(list(paths))
        return ds

    def _open_single(self, path: str) -> None:
        try:
            df = load_measurements(path)
            channels = list(df[ENSIGHT_CHANNEL_COLUMN].unique()) if ENSIGHT_CHANNEL_COLUMN in df.columns else []
            used = _slice_channel(df, channels[0]) if channels else df
            ms = _make_ms(used, str(path))
        except InvalidData:
            raise
        except Exception as exc:
            logger.exception('Could not load %s', path)
            raise _unreadable([str(path)]) from exc
        self.ms = ms
        self.channels = channels
        self.channel = channels[0] if channels else None
        self._channel_frame = df if channels else None
        self.files = (SourceFile(str(path), _format_of(str(path), used), tuple(ms.replica_ids)),)
        # The concentrations are molar now; a file that states its own unit shows its own
        # numbers under it, so the values read as the file wrote them.
        declared = used.attrs.get('concentration_unit')
        unit = _unit_token(Q_(1.0, declared).units) if declared else None
        molar = np.asarray(ms.concentrations, dtype=np.float64)
        self.imported_unit = unit or 'M'
        self.face_values = Q_(molar, 'M').to(unit).magnitude if unit else molar.copy()

    def _open_multiple(self, paths: list[str]) -> None:
        try:
            combined = load_measurements_multi(paths)
            ms = MeasurementSet.from_dataframe(combined, source_file=str(paths[0]), source_files=list(paths))
        except InvalidData:
            raise
        except Exception as exc:
            logger.exception('Could not load %s as replicates', paths)
            raise _unreadable(list(paths)) from exc
        self.ms = ms
        self.files = tuple(
            SourceFile(path, _format_of(path), tuple(r for r in ms.replica_ids if _from_file(r, path, paths)))
            for path in paths
        )
        self.face_values = np.asarray(ms.concentrations, dtype=np.float64).copy()
        self.imported_unit = 'M'

    def added(self, paths: list[str]) -> Dataset:
        """This dataset with *paths* added as further replicates on its grid.

        The concentrations stay as stated, and every replicate keeps whether it is used.

        Raises
        ------
        InvalidData
            When a file is a multi-channel one, cannot be read, or does not share the grid.
        """
        if self.channels:
            raise InvalidData(
                f'{self.files[0].name} holds several channels and is loaded on its own, one channel at a time. '
                'Load the other files into a new session.'
            )
        known = {f.path for f in self.files}
        fresh = [p for p in paths if p not in known]
        if not fresh:
            raise InvalidData('These files are already in this session.')
        ds = Dataset.open([f.path for f in self.files] + fresh)
        ds._keep_from(self)
        return ds

    def without(self, path: str) -> Dataset | None:
        """This dataset with the file *path* removed; ``None`` when it was the only one."""
        rest = [f.path for f in self.files if f.path != path]
        if not rest:
            return None
        ds = Dataset.open(rest)
        ds._keep_from(self)
        return ds

    def _keep_from(self, old: Dataset) -> None:
        """Keep *old*'s stated concentrations and the replicates it had switched off."""
        if old.face_values.size == self.ms.n_points and old.ms is not None:
            self.imported_unit = old.imported_unit
            self.face_values = old.face_values.copy()
            self.ms.set_concentrations(Q_(self.face_values, self.imported_unit))
        # A replicate's label depends on how many files are loaded (the file stem when
        # several are, the file's own labels when one is), so it is found again by its
        # file and its place in that file.
        old_files = {f.path: f.replica_ids for f in old.files}
        for f in self.files:
            for rid, old_id in zip(f.replica_ids, old_files.get(f.path, ()), strict=False):
                if not old.ms.is_active(old_id):
                    self.ms.set_active(rid, False)

    # ------------------------------------------------------------------
    # Channel and concentrations
    # ------------------------------------------------------------------

    def channel_label(self, channel: str) -> str:
        """*channel* as the file names it."""
        meta = self._channel_frame.attrs.get(ENSIGHT_METADATA_KEY, {}) if self._channel_frame is not None else {}
        return format_channel_label(channel, meta)

    def select_channel(self, channel: str) -> None:
        """Show *channel* of the multi-channel file; concentrations already entered are kept."""
        if self._channel_frame is None or channel == self.channel:
            return
        entered = not (self.ms is not None and self.ms.metadata.get(BMG_PLACEHOLDER_KEY))
        ms = _make_ms(_slice_channel(self._channel_frame, channel), self.files[0].path)
        if entered and self.face_values.size == ms.n_points:
            ms.set_concentrations(Q_(self.face_values, self.imported_unit), drop_metadata_keys=(BMG_PLACEHOLDER_KEY,))
        else:
            self.face_values = np.asarray(ms.concentrations, dtype=np.float64).copy()
        self.ms, self.channel = ms, channel

    def set_imported_unit(self, unit: str) -> None:
        """State the concentrations in *unit*: the same numbers, read in another unit."""
        if unit == self.imported_unit:
            return
        self.ms.set_concentrations(Q_(self.face_values, unit), drop_metadata_keys=(BMG_PLACEHOLDER_KEY,))
        self.imported_unit = unit

    def set_concentration(self, index: int, text: str) -> None:
        """Set point *index* to the number typed as *text*, in the imported unit.

        Raises
        ------
        InvalidData
            When *text* is not a concentration of zero or more.
        """
        value = parse_number(text)
        if value is None:
            raise InvalidData(f'“{text}” is not a number. Enter a concentration such as 2.5e-6.')
        values = self.face_values.copy()
        values[index] = value
        problem = concentration_problem(Q_(values, self.imported_unit))
        if problem:
            raise InvalidData(problem)
        self.ms.set_concentrations(Q_(values, self.imported_unit), drop_metadata_keys=(BMG_PLACEHOLDER_KEY,))
        self.face_values = values

    def load_concentrations(self, path: str) -> str | None:
        """Take the concentrations from the vector file *path*; a sentence when their unit was converted to M.

        Raises
        ------
        InvalidData
            When the file is not a concentration vector of this grid's length and of
            concentrations of zero or more.
        """
        try:
            q = read_raw_concentrations(path)
        except Exception as exc:
            raise InvalidData(
                f'Could not read {Path(path).name}. Make sure it is a concentration file (.json) saved by SupraSimFit.'
            ) from exc
        values = np.asarray(q.magnitude, dtype=np.float64)
        if values.size != self.ms.n_points:
            raise InvalidData(
                f'{Path(path).name} holds {values.size} concentrations, but the data have {self.ms.n_points} points. '
                'Load a vector with one value per point.'
            )
        problem = concentration_problem(q, f' in {Path(path).name}')
        if problem:
            raise InvalidData(f'{problem} Correct it in the file and load it again.')
        unit = _unit_token(q.units)
        self.ms.set_concentrations(q, drop_metadata_keys=(BMG_PLACEHOLDER_KEY,))
        if unit is not None:
            self.face_values, self.imported_unit = values, unit
            return None
        self.face_values, self.imported_unit = np.asarray(q.to('M').magnitude, dtype=np.float64), 'M'
        return (
            f'The file states its concentrations in {q.units:~P}, which is not one of {", ".join(UNITS)}, '
            'so they were converted to molar and are shown in M.'
        )

    def save_concentrations(self, path: str) -> None:
        """Write the concentrations as stated, with their unit, to *path*."""
        save_concentration_vector(self.face_values, path, unit=self.imported_unit)

    # ------------------------------------------------------------------
    # Replicates
    # ------------------------------------------------------------------

    def remove_outliers(self, threshold: float, min_replicates: int) -> None:
        """Switch off the replicates the modified Z-score filter finds; :attr:`outlier_result` says what it did.

        Raises
        ------
        InvalidData
            When fewer replicates are used than the filter needs.
        """
        ms = self.ms
        if ms.n_active < min_replicates:
            raise InvalidData(
                f'Outlier removal needs at least {min_replicates} replicates in use, and {ms.n_active} are. '
                f'Lower Min replicates to {ms.n_active}, or switch replicates back on with Reset all.'
            )
        params = {'threshold': threshold, 'min_replicas': min_replicates}
        apply_preprocessing(ms, [{'name': 'zscore_replica_filter', 'params': params}])
        self.outlier_result = ms.processing_log[-1]


def _format_of(path: str, frame: pd.DataFrame | None = None) -> str:
    """The format *path* was read as, named for the Files table."""
    if frame is not None and frame.attrs.get(BMG_METADATA_KEY):
        return 'BMG plate export'
    try:
        reader = type(get_reader(Path(path))).__name__
    except ValueError:
        return Path(path).suffix.lstrip('.').upper() or 'Data'
    return FORMATS.get(reader, Path(path).suffix.lstrip('.').upper())


def _from_file(replica_id: str, path: str, paths: list[str]) -> bool:
    """Whether *replica_id* came from *path* (labels are the file stem, numbered for a repeated stem)."""
    stem = Path(path).stem
    repeats = [p for p in paths if Path(p).stem == stem]
    label = stem if repeats.index(path) == 0 else f'{stem} ({repeats.index(path) + 1})'
    return replica_id == label or replica_id.startswith(f'{label}#')


def _make_ms(df: pd.DataFrame, source_file: str) -> MeasurementSet:
    """A MeasurementSet of a single-channel frame, with the metadata the app reads off it."""
    metadata = {k: df.attrs[k] for k in _METADATA_KEYS if k in df.attrs}
    return MeasurementSet.from_dataframe(df, source_file=source_file, **metadata)


def _slice_channel(df: pd.DataFrame, channel: str) -> pd.DataFrame:
    """The single-channel frame of *channel*, attrs kept and the channel noted."""
    out = df[df[ENSIGHT_CHANNEL_COLUMN] == channel].drop(columns=ENSIGHT_CHANNEL_COLUMN).reset_index(drop=True)
    out.attrs.update(df.attrs)
    if isinstance(out.attrs.get(ENSIGHT_METADATA_KEY), dict):
        out.attrs[ENSIGHT_METADATA_KEY] = {**out.attrs[ENSIGHT_METADATA_KEY], 'selected_channel': channel}
    return out
