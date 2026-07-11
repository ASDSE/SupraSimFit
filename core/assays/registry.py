"""Assay type registry with metadata for dispatch and plotting.

This module defines the central registry of all assay types in the toolkit.
The Enum-Keyed Registry pattern provides:
- Type-safe assay identification
- Centralized metadata for plotting labels, parameter keys, etc.
- Easy extension for new assay types

Scientific Conventions
----------------------
All binding constants use the ASSOCIATION form:
    Ka = [complex] / ([free_A][free_B])

Naming:
- Ka_dye: Association constant for Host-Dye binding
- Ka_guest: Association constant for Host-Guest binding
- I_dye_free: Signal coefficient for free dye
- I_dye_bound: Signal coefficient for host-dye complex

Example
-------
>>> from core.assays.registry import AssayType, ASSAY_REGISTRY
>>> meta = ASSAY_REGISTRY[AssayType.GDA]
>>> meta.display_name
'GDA (Guest Displacement Assay)'
>>> meta.parameter_keys
('Ka_guest', 'I0', 'I_dye_free', 'I_dye_bound')
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, Tuple

from core.units import Q_, Quantity


class AssayType(Enum):
    """Enumeration of all supported assay types.

    Each assay type has associated metadata in ASSAY_REGISTRY that defines
    its display name, parameter keys, plot labels, and default bounds.
    """

    GDA = auto()  # Guest Displacement Assay
    IDA = auto()  # Indicator Displacement Assay
    DBA_HtoD = auto()  # Direct Binding Assay (Host titrated into Dye)
    DBA_DtoH = auto()  # Direct Binding Assay (Dye titrated into Host)
    DYE_ALONE = auto()  # Dye-only control (linear calibration)
    DBA_HG2 = auto()  # Stepwise 1:2 host:guest (host binds two guests)
    DBA_H2G = auto()  # Stepwise 2:1 host:guest (two hosts bind one guest)


class ParamKind(Enum):
    """Semantic identity of a fitted parameter.

    Dimensional analysis alone cannot separate a binding constant (``1/M``)
    from a signal coefficient (``au/M``) unless ``au`` carries its own
    ``[signal]`` dimension — and even then a *label* is clearer than
    re-deriving intent from the unit string.  ``ParamKind`` is that explicit
    label; it is cross-checked against each parameter's unit (and against
    ``log_scale_keys``) by the registry unit-lint test, so the two can never
    silently drift.
    """

    BINDING_CONSTANT = auto()  # association constant, unit 1/M, log-scale
    SIGNAL_OFFSET = auto()  # additive signal baseline, unit au
    SIGNAL_COEFFICIENT = auto()  # signal per unit concentration, unit au/M


# Canonical unit token expected for each ParamKind (used by the unit-lint test
# and by boundary validation to confirm a parameter's declared unit matches its
# semantic kind).
KIND_UNIT: Dict[ParamKind, str] = {
    ParamKind.BINDING_CONSTANT: '1/M',
    ParamKind.SIGNAL_OFFSET: 'au',
    ParamKind.SIGNAL_COEFFICIENT: 'au/M',
}


@dataclass(frozen=True)
class AssayMetadata:
    """Immutable metadata container for an assay type.

    Attributes
    ----------
    display_name : str
        Human-readable name for display in GUI and plots.
    parameter_keys : Tuple[str, ...]
        Names of fitted parameters in order.  The optimizer receives
        parameters in this order; ``params_to_dict`` / ``params_from_dict``
        on :class:`BaseAssay` use this ordering.
    x_label : str
        Default name portion of the x-axis label (e.g. ``"Guest"``).
        The unit suffix is appended at render time by ``PlotWidget`` from
        ``style['axes']['x_unit']``.
    y_label : str
        Default name portion of the y-axis label (e.g. ``"Signal"``).
        The unit suffix is appended at render time by ``PlotWidget`` from
        ``y_unit``.
    category : str
        Top-level grouping label for the GUI assay-type selector
        (e.g. ``"Direct Binding"``).  Assays sharing a ``category`` populate
        the same main-dropdown group; the panel derives the two-level menu
        from these strings, so re-grouping is a data-only change.
    subtype_label : str
        Short label shown in the dependent subtype dropdown
        (e.g. ``"Host → Dye (1:1)"``).  Distinct from ``display_name``, which
        stays the long descriptive name used for the window title.
    y_unit : str
        Unit string appended to the y-axis label (e.g. ``"a.u."``).
    default_bounds : Dict[str, Tuple[float, float]]
        Default ``(lower, upper)`` bounds keyed by parameter name.
        :meth:`BaseAssay.get_default_bounds` returns a copy of this dict.
        ``_resolve_bounds`` in the pipeline converts to positional arrays
        for the optimizer.
    log_scale_keys : Tuple[str, ...]
        Parameter names that should be sampled in log₁₀ space during
        multi-start initialisation.  Typically association constants
        that span many orders of magnitude (e.g. ``Ka_dye``, ``Ka_guest``).
        Used as the *assay-level default* when the user does not override
        ``FitConfig.log_scale_params``.
    units : Dict[str, str]
        Unit strings for each parameter (for display/export).
    param_kinds : Dict[str, ParamKind]
        Semantic identity of each parameter (binding constant / signal
        offset / signal coefficient).  Cross-checked against ``units`` and
        ``log_scale_keys`` by the registry unit-lint test.
    """

    display_name: str
    parameter_keys: Tuple[str, ...]
    x_label: str
    y_label: str
    category: str
    subtype_label: str
    default_bounds: Dict[str, Tuple[Quantity, Quantity]] = field(default_factory=dict)
    log_scale_keys: Tuple[str, ...] = ()
    param_kinds: Dict[str, ParamKind] = field(default_factory=dict)
    y_unit: str = 'a.u.'

    @property
    def units(self) -> Dict[str, str]:
        """Derive unit strings from default_bounds Quantities."""
        return {k: str(lo.units) for k, (lo, _) in self.default_bounds.items()}


# Central registry mapping AssayType -> AssayMetadata
ASSAY_REGISTRY: Dict[AssayType, AssayMetadata] = {
    AssayType.GDA: AssayMetadata(
        display_name='GDA (Guest Displacement Assay)',
        category='Competitive Displacement',
        subtype_label='GDA — Guest Displacement (1:1)',
        parameter_keys=('Ka_guest', 'I0', 'I_dye_free', 'I_dye_bound'),
        x_label='Dye',
        y_label='Signal',
        default_bounds={
            'Ka_guest': (Q_(1e-8, '1/M'), Q_(1e12, '1/M')),
            'I0': (Q_(0, 'au'), Q_(1e8, 'au')),
            'I_dye_free': (Q_(0, 'au/M'), Q_(1e12, 'au/M')),
            'I_dye_bound': (Q_(0, 'au/M'), Q_(1e12, 'au/M')),
        },
        log_scale_keys=('Ka_guest',),
        param_kinds={
            'Ka_guest': ParamKind.BINDING_CONSTANT,
            'I0': ParamKind.SIGNAL_OFFSET,
            'I_dye_free': ParamKind.SIGNAL_COEFFICIENT,
            'I_dye_bound': ParamKind.SIGNAL_COEFFICIENT,
        },
    ),
    AssayType.IDA: AssayMetadata(
        display_name='IDA (Indicator Displacement Assay)',
        category='Competitive Displacement',
        subtype_label='IDA — Indicator Displacement (1:1)',
        parameter_keys=('Ka_guest', 'I0', 'I_dye_free', 'I_dye_bound'),
        x_label='Guest',
        y_label='Signal',
        default_bounds={
            'Ka_guest': (Q_(1e-8, '1/M'), Q_(1e12, '1/M')),
            'I0': (Q_(0, 'au'), Q_(1e8, 'au')),
            'I_dye_free': (Q_(0, 'au/M'), Q_(1e12, 'au/M')),
            'I_dye_bound': (Q_(0, 'au/M'), Q_(1e12, 'au/M')),
        },
        log_scale_keys=('Ka_guest',),
        param_kinds={
            'Ka_guest': ParamKind.BINDING_CONSTANT,
            'I0': ParamKind.SIGNAL_OFFSET,
            'I_dye_free': ParamKind.SIGNAL_COEFFICIENT,
            'I_dye_bound': ParamKind.SIGNAL_COEFFICIENT,
        },
    ),
    AssayType.DBA_HtoD: AssayMetadata(
        display_name='DBA Host→Dye (Direct Binding Assay)',
        category='Direct Binding',
        subtype_label='Host → Dye (1:1)',
        parameter_keys=('Ka_dye', 'I0', 'I_dye_free', 'I_dye_bound'),
        x_label='Host',
        y_label='Signal',
        default_bounds={
            'Ka_dye': (Q_(1e-8, '1/M'), Q_(1e12, '1/M')),
            'I0': (Q_(0, 'au'), Q_(1e8, 'au')),
            'I_dye_free': (Q_(0, 'au/M'), Q_(1e12, 'au/M')),
            'I_dye_bound': (Q_(0, 'au/M'), Q_(1e12, 'au/M')),
        },
        log_scale_keys=('Ka_dye',),
        param_kinds={
            'Ka_dye': ParamKind.BINDING_CONSTANT,
            'I0': ParamKind.SIGNAL_OFFSET,
            'I_dye_free': ParamKind.SIGNAL_COEFFICIENT,
            'I_dye_bound': ParamKind.SIGNAL_COEFFICIENT,
        },
    ),
    AssayType.DBA_DtoH: AssayMetadata(
        display_name='DBA Dye→Host (Direct Binding Assay)',
        category='Direct Binding',
        subtype_label='Dye → Host (1:1)',
        parameter_keys=('Ka_dye', 'I0', 'I_dye_free', 'I_dye_bound'),
        x_label='Dye',
        y_label='Signal',
        default_bounds={
            'Ka_dye': (Q_(1e-8, '1/M'), Q_(1e12, '1/M')),
            'I0': (Q_(0, 'au'), Q_(1e8, 'au')),
            'I_dye_free': (Q_(0, 'au/M'), Q_(1e12, 'au/M')),
            'I_dye_bound': (Q_(0, 'au/M'), Q_(1e12, 'au/M')),
        },
        log_scale_keys=('Ka_dye',),
        param_kinds={
            'Ka_dye': ParamKind.BINDING_CONSTANT,
            'I0': ParamKind.SIGNAL_OFFSET,
            'I_dye_free': ParamKind.SIGNAL_COEFFICIENT,
            'I_dye_bound': ParamKind.SIGNAL_COEFFICIENT,
        },
    ),
    AssayType.DYE_ALONE: AssayMetadata(
        display_name='Dye Alone (Linear Calibration)',
        category='Calibration',
        subtype_label='Dye Alone',
        parameter_keys=('slope', 'intercept'),
        x_label='Dye',
        y_label='Signal',
        default_bounds={
            'slope': (Q_(0, 'au/M'), Q_(1e12, 'au/M')),
            'intercept': (Q_(-1e6, 'au'), Q_(1e6, 'au')),
        },
        log_scale_keys=(),
        param_kinds={
            'slope': ParamKind.SIGNAL_COEFFICIENT,
            'intercept': ParamKind.SIGNAL_OFFSET,
        },
    ),
    AssayType.DBA_HG2: AssayMetadata(
        display_name='DBA 1:2 (HG2, stepwise host–guest)',
        category='Direct Binding',
        subtype_label='Host–Guest 1:2 (HG₂)',
        parameter_keys=('Ka_HG', 'Ka_HG2', 'I0', 'I_G', 'I_H', 'I_HG', 'I_HG2'),
        x_label='Guest',
        y_label='Signal',
        default_bounds={
            'Ka_HG': (Q_(1e-8, '1/M'), Q_(1e12, '1/M')),
            'Ka_HG2': (Q_(1e-8, '1/M'), Q_(1e12, '1/M')),
            'I0': (Q_(0, 'au'), Q_(1e8, 'au')),
            'I_G': (Q_(0, 'au/M'), Q_(1e12, 'au/M')),
            # Free-host signal coefficient: pinned to zero by default
            # (no signal from free host); widen these bounds to fit it.
            'I_H': (Q_(0, 'au/M'), Q_(0, 'au/M')),
            'I_HG': (Q_(0, 'au/M'), Q_(1e12, 'au/M')),
            'I_HG2': (Q_(0, 'au/M'), Q_(1e12, 'au/M')),
        },
        log_scale_keys=('Ka_HG', 'Ka_HG2'),
        param_kinds={
            'Ka_HG': ParamKind.BINDING_CONSTANT,
            'Ka_HG2': ParamKind.BINDING_CONSTANT,
            'I0': ParamKind.SIGNAL_OFFSET,
            'I_G': ParamKind.SIGNAL_COEFFICIENT,
            'I_H': ParamKind.SIGNAL_COEFFICIENT,
            'I_HG': ParamKind.SIGNAL_COEFFICIENT,
            'I_HG2': ParamKind.SIGNAL_COEFFICIENT,
        },
    ),
    AssayType.DBA_H2G: AssayMetadata(
        display_name='DBA 2:1 (H2G, stepwise host–guest)',
        category='Direct Binding',
        subtype_label='Host–Guest 2:1 (H₂G)',
        parameter_keys=('Ka_HG', 'Ka_H2G', 'I0', 'I_G', 'I_H', 'I_HG', 'I_H2G'),
        x_label='Guest',
        y_label='Signal',
        default_bounds={
            'Ka_HG': (Q_(1e-8, '1/M'), Q_(1e12, '1/M')),
            'Ka_H2G': (Q_(1e-8, '1/M'), Q_(1e12, '1/M')),
            'I0': (Q_(0, 'au'), Q_(1e8, 'au')),
            'I_G': (Q_(0, 'au/M'), Q_(1e12, 'au/M')),
            # Free-host signal coefficient: pinned to zero by default
            # (no signal from free host); widen these bounds to fit it.
            'I_H': (Q_(0, 'au/M'), Q_(0, 'au/M')),
            'I_HG': (Q_(0, 'au/M'), Q_(1e12, 'au/M')),
            'I_H2G': (Q_(0, 'au/M'), Q_(1e12, 'au/M')),
        },
        log_scale_keys=('Ka_HG', 'Ka_H2G'),
        param_kinds={
            'Ka_HG': ParamKind.BINDING_CONSTANT,
            'Ka_H2G': ParamKind.BINDING_CONSTANT,
            'I0': ParamKind.SIGNAL_OFFSET,
            'I_G': ParamKind.SIGNAL_COEFFICIENT,
            'I_H': ParamKind.SIGNAL_COEFFICIENT,
            'I_HG': ParamKind.SIGNAL_COEFFICIENT,
            'I_H2G': ParamKind.SIGNAL_COEFFICIENT,
        },
    ),
}


def get_metadata(assay_type: AssayType) -> AssayMetadata:
    """Get metadata for an assay type.

    Parameters
    ----------
    assay_type : AssayType
        The assay type enum value.

    Returns
    -------
    AssayMetadata
        The metadata for this assay type.

    Raises
    ------
    KeyError
        If the assay type is not registered.
    """
    return ASSAY_REGISTRY[assay_type]


def list_assay_types() -> Tuple[AssayType, ...]:
    """Return all registered assay types.

    Returns
    -------
    Tuple[AssayType, ...]
        All assay types in registration order.
    """
    return tuple(ASSAY_REGISTRY.keys())
