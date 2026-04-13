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
        Label for x-axis in plots.
    y_label : str
        Label for y-axis in plots.
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
    """

    display_name: str
    parameter_keys: Tuple[str, ...]
    x_label: str
    y_label: str
    default_bounds: Dict[str, Tuple[Quantity, Quantity]] = field(default_factory=dict)
    log_scale_keys: Tuple[str, ...] = ()

    @property
    def units(self) -> Dict[str, str]:
        """Derive unit strings from default_bounds Quantities."""
        return {k: str(lo.units) for k, (lo, _) in self.default_bounds.items()}


# Central registry mapping AssayType -> AssayMetadata
ASSAY_REGISTRY: Dict[AssayType, AssayMetadata] = {
    AssayType.GDA: AssayMetadata(
        display_name='GDA (Guest Displacement Assay)',
        parameter_keys=('Ka_guest', 'I0', 'I_dye_free', 'I_dye_bound'),
        x_label='Dye',
        y_label='Signal [a.u.]',
        default_bounds={
            'Ka_guest': (Q_(1e-8, '1/M'), Q_(1e12, '1/M')),
            'I0': (Q_(0, 'au'), Q_(1e8, 'au')),
            'I_dye_free': (Q_(0, 'au/M'), Q_(1e12, 'au/M')),
            'I_dye_bound': (Q_(0, 'au/M'), Q_(1e12, 'au/M')),
        },
        log_scale_keys=('Ka_guest',),
    ),
    AssayType.IDA: AssayMetadata(
        display_name='IDA (Indicator Displacement Assay)',
        parameter_keys=('Ka_guest', 'I0', 'I_dye_free', 'I_dye_bound'),
        x_label='Guest',
        y_label='Signal [a.u.]',
        default_bounds={
            'Ka_guest': (Q_(1e-8, '1/M'), Q_(1e12, '1/M')),
            'I0': (Q_(0, 'au'), Q_(1e8, 'au')),
            'I_dye_free': (Q_(0, 'au/M'), Q_(1e12, 'au/M')),
            'I_dye_bound': (Q_(0, 'au/M'), Q_(1e12, 'au/M')),
        },
        log_scale_keys=('Ka_guest',),
    ),
    AssayType.DBA_HtoD: AssayMetadata(
        display_name='DBA Host→Dye (Direct Binding Assay)',
        parameter_keys=('Ka_dye', 'I0', 'I_dye_free', 'I_dye_bound'),
        x_label='Host',
        y_label='Signal [a.u.]',
        default_bounds={
            'Ka_dye': (Q_(1e-8, '1/M'), Q_(1e12, '1/M')),
            'I0': (Q_(0, 'au'), Q_(1e8, 'au')),
            'I_dye_free': (Q_(0, 'au/M'), Q_(1e12, 'au/M')),
            'I_dye_bound': (Q_(0, 'au/M'), Q_(1e12, 'au/M')),
        },
        log_scale_keys=('Ka_dye',),
    ),
    AssayType.DBA_DtoH: AssayMetadata(
        display_name='DBA Dye→Host (Direct Binding Assay)',
        parameter_keys=('Ka_dye', 'I0', 'I_dye_free', 'I_dye_bound'),
        x_label='[Dye] / M',
        y_label='Signal / a.u.',
        default_bounds={
            'Ka_dye': (Q_(1e-8, '1/M'), Q_(1e12, '1/M')),
            'I0': (Q_(0, 'au'), Q_(1e8, 'au')),
            'I_dye_free': (Q_(0, 'au/M'), Q_(1e12, 'au/M')),
            'I_dye_bound': (Q_(0, 'au/M'), Q_(1e12, 'au/M')),
        },
        log_scale_keys=('Ka_dye',),
    ),
    AssayType.DYE_ALONE: AssayMetadata(
        display_name='Dye Alone (Linear Calibration)',
        parameter_keys=('slope', 'intercept'),
        x_label='Dye',
        y_label='Signal [a.u.]',
        default_bounds={
            'slope': (Q_(0, 'au/M'), Q_(1e12, 'au/M')),
            'intercept': (Q_(-1e6, 'au'), Q_(1e6, 'au')),
        },
        log_scale_keys=(),
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
