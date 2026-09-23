"""In-memory container for multi-replica measurement data.

MeasurementSet holds a shared concentration grid and all replica signals
in a 2D numpy array.  An internal boolean mask tracks which replicas are
"active" (included for fitting / averaging) without ever mutating the raw
data.

Typical construction::

    from core.io import load_measurements
    from core.data_processing import MeasurementSet

    df = load_measurements("data/GDA_system.txt")
    ms = MeasurementSet.from_dataframe(df, assay_type="GDA")
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Mapping, Optional, Tuple, Type

import numpy as np
import pandas as pd

from core.assays.base import BaseAssay
from core.assays.registry import ASSAY_REGISTRY
from core.io import InvalidData
from core.io.formats.bmg_reader import BMG_PLACEHOLDER_KEY
from core.units import Q_, Quantity

logger = logging.getLogger(__name__)


#: Fewest titration points a fit can use: one more than the fewest parameters
#: any model of the registry has, so every fit keeps a residual degree of freedom.
MIN_POINTS = 1 + min(len(meta.parameter_keys) for meta in ASSAY_REGISTRY.values())

#: Relative tolerance within which two replicates' concentrations are the same point.
_GRID_RTOL = 1e-9

#: The concentration units the Data panel offers, largest first.
_UNIT_SCALES = (('M', 1.0), ('mM', 1e-3), ('µM', 1e-6), ('nM', 1e-9))


def _molar_text(value: float) -> str:
    """A concentration given in M, written in the largest Data-panel unit it reaches: '4 µM', '-3.2 nM', '0 M'."""
    unit, scale = next(((u, s) for u, s in _UNIT_SCALES if abs(value) >= s), ('M', 1.0) if value == 0 else ('nM', 1e-9))
    return f'{value / scale:.4g} {unit}'


def _no_measurements(where: str) -> InvalidData:
    return InvalidData(
        f'The data{where} contain no measurements. Check that the file holds a concentration '
        'and a signal for each titration point, and load it again.'
    )


def _in_file(metadata: Mapping[str, Any]) -> str:
    """' in <file names>' for data read from files, '' otherwise."""
    sources = metadata.get('source_files') or [metadata.get('source_file')]
    names = [Path(source).name for source in sources if source]
    return f' in {", ".join(names)}' if names else ''


def _whose(replica_id: str, n_replicas: int) -> str:
    """Who holds a value: 'replicate <id>' among several, 'the titration' for a single one."""
    return f"replicate '{replica_id}'" if n_replicas > 1 else 'the titration'


def concentration_problem(values: Quantity, where: str = '') -> Optional[str]:
    """One sentence naming the first concentration that is not a finite number of zero or more.

    Parameters
    ----------
    values : pint.Quantity
        Concentration vector, in any concentration unit.
    where : str
        Where the values come from, as ``' in <file name>'``; empty when entered.

    Returns
    -------
    str or None
        The sentence, or ``None`` when every value is a concentration.
    """
    magnitudes = np.asarray(values.magnitude, dtype=np.float64).reshape(-1)
    bad = np.flatnonzero(~(np.isfinite(magnitudes) & (magnitudes >= 0)))
    if bad.size == 0:
        return None
    i = int(bad[0])
    value = magnitudes[i]
    if np.isnan(value):
        stated = 'no concentration'
    elif np.isinf(value):
        stated = 'an infinite concentration'
    else:
        stated = f'the concentration {_molar_text(Q_(value, values.units).to("M").magnitude)}'
    return (
        f'Titration point {i + 1} of {magnitudes.size}{where} has {stated}; '
        'a concentration must be a number of zero or more.'
    )


@dataclass
class MeasurementSet:
    """Multi-replica measurement data with non-destructive replica masking.

    Attributes
    ----------
    concentrations : np.ndarray
        Shared concentration grid, shape ``(n_points,)``.  Read-only after
        construction.
    signals : np.ndarray
        Replica signals, shape ``(n_replicas, n_points)``.  Read-only after
        construction.
    replica_ids : tuple[str, ...]
        Immutable identifiers for each replica row.
    metadata : dict[str, Any]
        Free-form provenance bag (``source_file``, ``assay_type``, ``units``,
        ``date``, etc.).
    id : str
        Auto-generated UUID (hex).
    processing_log : list[dict[str, Any]]
        Chronological log of preprocessing steps applied.
    """

    concentrations: np.ndarray
    signals: np.ndarray
    replica_ids: tuple[str, ...]
    metadata: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    processing_log: list[Dict[str, Any]] = field(default_factory=list)

    # Internal active mask — not part of public __init__
    _active_mask: np.ndarray = field(init=False, repr=False)

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    def __post_init__(self) -> None:
        """Validate shapes, freeze raw data, initialise active mask."""
        self.concentrations = np.array(self.concentrations, dtype=np.float64)
        self.signals = np.array(self.signals, dtype=np.float64)

        if self.concentrations.ndim != 1:
            raise ValueError(f'concentrations must be 1-D, got shape {self.concentrations.shape}')
        if self.signals.ndim != 2:
            raise ValueError(f'signals must be 2-D (n_replicas, n_points), got shape {self.signals.shape}')
        if self.signals.shape[1] != self.concentrations.shape[0]:
            raise ValueError(
                f'signals columns ({self.signals.shape[1]}) must match concentrations length ({self.concentrations.shape[0]})'
            )
        if len(self.replica_ids) != self.signals.shape[0]:
            raise ValueError(
                f'replica_ids length ({len(self.replica_ids)}) must match signals rows ({self.signals.shape[0]})'
            )

        self._check_values()

        # Freeze raw data
        self.concentrations.flags.writeable = False
        self.signals.flags.writeable = False
        self.replica_ids = tuple(self.replica_ids)

        # All replicas start active
        self._active_mask = np.ones(self.signals.shape[0], dtype=bool)

    def _check_values(self) -> None:
        """Refuse data no fit can use: too few points, a concentration below zero or not finite, a signal not finite.

        Raises
        ------
        InvalidData
            Naming the file, the replicate and the point, and what to do.
        """
        where = _in_file(self.metadata)
        n_points = self.concentrations.size
        if n_points == 0 or self.signals.shape[0] == 0:
            raise _no_measurements(where)
        if n_points < MIN_POINTS:
            raise InvalidData(
                f'The data{where} have only {n_points} titration points; no binding model can be fitted '
                f'to fewer than {MIN_POINTS}. Load a titration with more points.'
            )
        problem = concentration_problem(Q_(self.concentrations, 'M'), where)
        if problem:
            fix = 'Correct it in the file and load it again.' if where else 'Correct it and try again.'
            raise InvalidData(f'{problem} {fix}')
        bad = np.argwhere(~np.isfinite(self.signals))
        if bad.size == 0:
            return
        row, i = (int(k) for k in bad[0])
        rid = self.replica_ids[row]
        stated = 'no signal' if np.isnan(self.signals[row, i]) else 'an infinite signal'
        if self.metadata.get(BMG_PLACEHOLDER_KEY):
            at = f'plate column {self.concentrations[i]:g}'
        else:
            at = f'{_molar_text(self.concentrations[i])} (point {i + 1} of {n_points})'
        column = self.signals[:, i]
        if self.n_replicas > 1 and not np.isfinite(column).any():
            # Removing a replicate would only move the refusal to the next one.
            usable = 'a signal' if np.isnan(column).all() else 'a finite signal'
            raise InvalidData(
                f'No replicate{where} has {usable} at {at}. Fill in the values, or delete that titration point, '
                'and load the data again.'
            )
        message = f'{_whose(rid, self.n_replicas).capitalize()}{where} has {stated} at {at}.'
        if self.n_replicas > 1:
            message += (
                ' The replicates are averaged point by point, so each needs a signal at every concentration. '
                f"Fill in the value, or remove replicate '{rid}' from the data, and load it again."
            )
        else:
            message += ' Fill in the value, or delete that titration point, and load the data again.'
        raise InvalidData(message)

    @classmethod
    def from_dataframe(
        cls,
        df: pd.DataFrame,
        *,
        replica_col: str = 'replica',
        concentration_col: str = 'concentration',
        signal_col: str = 'signal',
        **metadata: Any,
    ) -> 'MeasurementSet':
        """Build a MeasurementSet from a long-form DataFrame.

        The DataFrame must contain columns for concentration, signal, and
        replica index.  All replicas must share the same concentration grid.

        Parameters
        ----------
        df : pd.DataFrame
            Long-form data with one row per (replica, concentration) pair.
        replica_col, concentration_col, signal_col : str
            Column names (defaults match ``load_measurements`` output).
        **metadata
            Arbitrary keyword arguments stored in ``metadata``.

        Returns
        -------
        MeasurementSet

        Raises
        ------
        ValueError
            If a required column is missing.
        InvalidData
            If the frame holds no measurement, a titration point has no
            concentration, or the replicates do not share one concentration
            grid; and whatever the constructor refuses.
        """
        for col in (replica_col, concentration_col, signal_col):
            if col not in df.columns:
                raise ValueError(f"Missing required column: '{col}'")

        # Capture a reader-declared concentration unit before any reshaping that
        # could drop ``df.attrs`` (readers tag non-M files, e.g. an external µM
        # CSV, via ``df.attrs['concentration_unit']``; absent means M).
        declared_conc_unit = df.attrs.get('concentration_unit')

        where = _in_file(metadata)
        if df.empty:
            raise _no_measurements(where)
        unnamed = np.flatnonzero(df[concentration_col].isna().to_numpy())
        if unnamed.size:
            i = int(unnamed[0])
            whose = _whose(str(df[replica_col].iloc[i]), df[replica_col].nunique())
            raise InvalidData(
                f'{whose.capitalize()}{where} has a titration point with no concentration '
                f'(its signal is {df[signal_col].iloc[i]:.6g}). Enter its concentration, or delete that '
                'titration point, and load the file again.'
            )

        # Sort for deterministic order
        df = df.sort_values([replica_col, concentration_col]).reset_index(drop=True)

        replica_labels = df[replica_col].unique()
        groups = {label: grp.sort_values(concentration_col) for label, grp in df.groupby(replica_col)}
        grids = {label: grp[concentration_col].to_numpy(dtype=np.float64) for label, grp in groups.items()}

        def at(c: float) -> str:
            if df.attrs.get(BMG_PLACEHOLDER_KEY):
                return f'plate column {c:g}'
            return _molar_text(Q_(c, declared_conc_unit or 'M').to('M').magnitude)

        # Every replicate shares the grid of the longest one: the replicates are
        # averaged point by point. Readers drop a blank cell, so a replicate with
        # a missing value arrives short of exactly the concentrations it lacks.
        reference = max(replica_labels, key=lambda label: grids[label].size)
        reference_conc = grids[reference]
        for label in replica_labels:
            conc = grids[label]
            if conc.size < reference_conc.size:
                lacking = [c for c in reference_conc if not np.isclose(conc, c, rtol=_GRID_RTOL, atol=0).any()]
                if len(lacking) == reference_conc.size - conc.size:
                    raise InvalidData(
                        f"Replicate '{label}'{where} has no signal at {', '.join(at(c) for c in lacking)}, "
                        f"where replicate '{reference}' has one. The replicates are averaged point by point, "
                        'so each needs a signal at every concentration. Fill in the missing value, or remove '
                        f"replicate '{label}' from the data, and load it again."
                    )
            if conc.size != reference_conc.size or not np.allclose(conc, reference_conc, rtol=_GRID_RTOL, atol=0):
                raise InvalidData(
                    f"Replicate '{label}'{where} was measured on a different concentration grid from replicate "
                    f"'{reference}', so the two cannot be averaged point by point. Correct the concentrations "
                    'in the file, or load the replicates as separate data sets.'
                )

        # Build 2-D signals array
        signals = np.array([groups[label][signal_col].values for label in replica_labels])
        replica_ids = tuple(str(label) for label in replica_labels)

        # Convert to molar if a non-M unit was declared, so the stored grid is
        # always M. Pint validates the token and the dimensionality.
        if declared_conc_unit and declared_conc_unit != 'M':
            reference_conc = Q_(np.asarray(reference_conc, dtype=float), declared_conc_unit).to('M').magnitude

        return cls(
            concentrations=reference_conc,
            signals=signals,
            replica_ids=replica_ids,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def n_replicas(self) -> int:
        """Total number of replicas (active + dropped)."""
        return self.signals.shape[0]

    @property
    def n_active(self) -> int:
        """Number of currently active replicas."""
        return int(self._active_mask.sum())

    @property
    def n_points(self) -> int:
        """Number of concentration points per replica."""
        return self.concentrations.shape[0]

    @property
    def active_replica_ids(self) -> list[str]:
        """Replica IDs currently marked active."""
        return [rid for rid, active in zip(self.replica_ids, self._active_mask) if active]

    @property
    def dropped_replica_ids(self) -> list[str]:
        """Replica IDs currently marked inactive."""
        return [rid for rid, active in zip(self.replica_ids, self._active_mask) if not active]

    # ------------------------------------------------------------------
    # Replica management
    # ------------------------------------------------------------------

    def _replica_index(self, replica_id: str) -> int:
        """Return the row index for *replica_id*, or raise ValueError."""
        try:
            return self.replica_ids.index(replica_id)
        except ValueError:
            raise ValueError(f"Unknown replica_id '{replica_id}'. Available: {self.replica_ids}") from None

    def set_active(self, replica_id: str, active: bool) -> None:
        """Set the active state of a single replica.

        Parameters
        ----------
        replica_id : str
            Must be one of ``replica_ids``.
        active : bool
            ``True`` to include, ``False`` to exclude.
        """
        idx = self._replica_index(replica_id)
        self._active_mask[idx] = active

    def is_active(self, replica_id: str) -> bool:
        """Check whether *replica_id* is currently active."""
        return bool(self._active_mask[self._replica_index(replica_id)])

    def reset_active(self) -> None:
        """Mark all replicas active (undo all filtering)."""
        self._active_mask[:] = True

    def with_active(self, replica_ids: Iterable[str]) -> 'MeasurementSet':
        """Copy of this set with exactly *replica_ids* active.

        The copy owns its arrays, mask, metadata and log, so a later change to
        this set (a replicate switched off, a concentration edit) never reaches
        it. It keeps ``id``: it holds the same measurement, and results made on
        it name that measurement.

        Parameters
        ----------
        replica_ids : iterable of str
            Replicates to mark active; every other replicate is inactive.

        Raises
        ------
        ValueError
            If a replicate is not part of this set.
        """
        wanted = set(replica_ids)
        unknown = sorted(wanted - set(self.replica_ids))
        if unknown:
            names = ', '.join(repr(rid) for rid in unknown)
            raise ValueError(
                f'This data has no replicate {names}. Its replicates are {", ".join(map(repr, self.replica_ids))}.'
            )
        copy = MeasurementSet(
            concentrations=self.concentrations,
            signals=self.signals,
            replica_ids=self.replica_ids,
            metadata=dict(self.metadata),
            id=self.id,
            processing_log=[dict(entry) for entry in self.processing_log],
        )
        copy._active_mask[:] = [rid in wanted for rid in self.replica_ids]
        return copy

    def fingerprint(self) -> str:
        """Stable hash of the measured data: concentrations, every signal and the replicate ids.

        It ignores which replicates are active and the set's ``id``, so the same
        file loaded twice gives the same fingerprint while any change to a
        concentration or signal value gives a different one. A fit stores it to
        tell whether data loaded later is the data it was made on.
        """
        digest = hashlib.sha256()
        for array in (self.concentrations, self.signals):
            digest.update(repr(array.shape).encode())
            digest.update(np.ascontiguousarray(array, dtype='<f8').tobytes())
        digest.update('\x1f'.join(self.replica_ids).encode())
        return digest.hexdigest()

    # ------------------------------------------------------------------
    # Data access
    # ------------------------------------------------------------------

    def iter_replicas(self, *, active_only: bool = True) -> Iterator[Tuple[str, np.ndarray]]:
        """Iterate over replicas as ``(replica_id, signal_view)`` pairs.

        Parameters
        ----------
        active_only : bool
            If ``True`` (default), skip inactive replicas.

        Yields
        ------
        tuple[str, np.ndarray]
            ``(replica_id, signal)`` where *signal* is a read-only **view**
            into the underlying signals array (no copy).
        """
        for i, rid in enumerate(self.replica_ids):
            if active_only and not self._active_mask[i]:
                continue
            yield rid, self.signals[i]

    def get_replica_signal(self, replica_id: str) -> np.ndarray:
        """Return the signal array (read-only view) for a single replica.

        Parameters
        ----------
        replica_id : str
            Must be one of ``replica_ids``.

        Returns
        -------
        np.ndarray
            Shape ``(n_points,)``, read-only view.
        """
        return self.signals[self._replica_index(replica_id)]

    def average_signal(self, *, active_only: bool = True) -> np.ndarray:
        """Compute the mean signal across replicas.

        Parameters
        ----------
        active_only : bool
            If ``True`` (default), average only over active replicas.

        Returns
        -------
        np.ndarray
            Shape ``(n_points,)``.

        Raises
        ------
        ValueError
            If no replicas are selected.
        """
        mask = self._active_mask if active_only else np.ones(self.n_replicas, dtype=bool)
        if not mask.any():
            raise ValueError('No replicas selected for averaging')
        return self.signals[mask].mean(axis=0)

    # ------------------------------------------------------------------
    # Bridge to assay objects
    # ------------------------------------------------------------------

    def to_assay(
        self,
        assay_cls: Type[BaseAssay],
        *,
        conditions: Dict[str, Any],
        use_average: bool = True,
        replica_id: Optional[str] = None,
    ) -> BaseAssay:
        """Construct a :class:`BaseAssay` from this measurement set.

        Parameters
        ----------
        assay_cls : Type[BaseAssay]
            Concrete assay class (e.g. ``GDAAssay``).
        conditions : dict
            Assay-specific keyword arguments (``Ka_dye``, ``h0``, etc.).
        use_average : bool
            If ``True``, use the averaged active-replica signal.
        replica_id : str, optional
            Use this specific replica instead of the average.  Raises if the
            replica is inactive.

        Returns
        -------
        BaseAssay
            Ready for fitting via ``fit_assay()``.

        Raises
        ------
        ValueError
            If *replica_id* is specified but inactive, or if both
            *use_average* is False and *replica_id* is None.
        """
        if replica_id is not None:
            if not self.is_active(replica_id):
                raise ValueError(f"Replica '{replica_id}' is inactive.  Activate it first or choose an active replica.")
            y = np.array(self.get_replica_signal(replica_id))  # writeable copy
        elif use_average:
            y = self.average_signal(active_only=True)
        else:
            raise ValueError('Either set use_average=True or provide a replica_id')

        return assay_cls(
            x_data=Q_(np.array(self.concentrations), 'M'),
            y_data=Q_(y, 'au'),
            name=self.metadata.get('source_file', ''),
            **conditions,
        )

    # ------------------------------------------------------------------
    # In-place mutation
    # ------------------------------------------------------------------

    def set_concentrations(
        self,
        new_conc: Quantity,
        *,
        drop_metadata_keys: Tuple[str, ...] = (),
    ) -> None:
        """Replace this MeasurementSet's concentration grid in place.

        The blessed mutation path for the concentration vector. The
        read-only lock on ``concentrations`` is lifted transiently so the
        existing buffer can be overwritten; the lock is restored before
        returning, so external code still cannot mutate the array.

        Parameters
        ----------
        new_conc : pint.Quantity
            New concentration vector. Must have concentration
            dimensionality and length equal to ``self.n_points``.
            Converted to molar via Pint; the unit declaration done at
            the call site is the single source of truth for the
            conversion.
        drop_metadata_keys : tuple of str, optional
            Metadata keys to drop after the update (e.g. the BMG
            placeholder flag once real concentrations are supplied).

        Raises
        ------
        InvalidData
            If a value is not a finite concentration of zero or more; the grid
            is left as it was.
        """
        if not isinstance(new_conc, Quantity):
            raise TypeError(f'new_conc must be a pint Quantity, got {type(new_conc).__name__}')
        if new_conc.dimensionality != Q_(1.0, 'M').dimensionality:
            raise ValueError(f'new_conc must have concentration dimensionality, got {new_conc.dimensionality}')
        molar_values = np.asarray(new_conc.to('M').magnitude, dtype=np.float64)
        if molar_values.shape != (self.n_points,):
            raise ValueError(f'new_conc length {molar_values.shape} does not match n_points ({self.n_points},)')
        problem = concentration_problem(new_conc)
        if problem:
            raise InvalidData(f'{problem} Correct it and try again.')

        self.concentrations.flags.writeable = True
        try:
            self.concentrations[:] = molar_values
        finally:
            self.concentrations.flags.writeable = False

        for key in drop_metadata_keys:
            self.metadata.pop(key, None)
