"""Registry mapping AssayType to its condition fields for the GUI.

This is the only place assay-specific GUI knowledge lives.  Adding a new
assay type to the GUI requires only one new entry in ASSAY_CONDITIONS plus
the usual core registry changes — zero widget code changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.assays import AssayType, DBAAssay, DyeAloneAssay, GDAAssay, IDAAssay
from core.assays.base import BaseAssay


@dataclass(frozen=True)
class ConditionField:
    """Schema for one assay condition input field.

    Attributes
    ----------
    key : str
        Dict key passed to the assay constructor (e.g. ``"Ka_dye"``).
    label : str
        HTML display label shown in the form (e.g. ``"K<sub>a,dye</sub>"``).
    tooltip : str
        Longer scientific description shown as a tooltip.
    default : float
        Default numeric value in the base unit (M or M⁻¹).
    unit : str
        Base unit string (e.g. ``"M"`` or ``"M⁻¹"``).
    unit_type : str
        Controls the unit-selector dropdown shown next to the spinbox:
        ``"concentration"`` → nM / µM / mM / M selector (default µM),
        ``"binding_constant"`` → M⁻¹ selector,
        ``""`` → no selector, plain spinbox.
        Exact choices/defaults are derived from ``core.units.CONDITION_UNITS``.
    """

    key: str
    label: str
    tooltip: str
    default: float
    unit: str = ''
    unit_type: str = ''


# Maps AssayType → (assay_class, tuple of ConditionField)
# AssayConfigPanel reads this to build the dynamic conditions form.
ASSAY_CONDITIONS: dict[AssayType, tuple[type[BaseAssay], tuple[ConditionField, ...]]] = {
    AssayType.GDA: (
        GDAAssay,
        (
            ConditionField(
                'Ka_dye',
                'K<sub>a,dye</sub>',
                'Known host–dye association constant (M⁻¹)',
                33e3,
                'M⁻¹',
                'binding_constant',
            ),
            ConditionField(
                'h0',
                '[Host]<sub>0</sub>',
                'Total host concentration in the cuvette',
                50e-6,
                'M',
                'concentration',
            ),
            ConditionField(
                'g0',
                '[Guest]<sub>0</sub>',
                'Total guest concentration in the cuvette',
                292e-6,
                'M',
                'concentration',
            ),
        ),
    ),
    AssayType.IDA: (
        IDAAssay,
        (
            ConditionField(
                'Ka_dye',
                'K<sub>a,dye</sub>',
                'Known host–dye association constant (M⁻¹)',
                16800000,
                'M⁻¹',
                'binding_constant',
            ),
            ConditionField(
                'h0',
                '[Host]<sub>0</sub>',
                'Total host concentration in the cuvette',
                4.3e-6,
                'M',
                'concentration',
            ),
            ConditionField(
                'd0',
                '[Dye]<sub>0</sub>',
                'Total dye concentration in the cuvette',
                6e-6,
                'M',
                'concentration',
            ),
        ),
    ),
    AssayType.DBA_HtoD: (
        DBAAssay,
        (
            ConditionField(
                'fixed_conc',
                '[Dye]<sub>0</sub>',
                'Fixed dye concentration (host is titrated)',
                151e-6,
                'M',
                'concentration',
            ),
        ),
    ),
    AssayType.DBA_DtoH: (
        DBAAssay,
        (
            ConditionField(
                'fixed_conc',
                '[Host]<sub>0</sub>',
                'Fixed host concentration (dye is titrated)',
                10e-6,
                'M',
                'concentration',
            ),
        ),
    ),
    AssayType.DYE_ALONE: (
        DyeAloneAssay,
        (),  # no conditions needed
    ),
}


def assay_class(assay_type: AssayType) -> type[BaseAssay]:
    """Return the assay class for the given type."""
    return ASSAY_CONDITIONS[assay_type][0]


def condition_fields(assay_type: AssayType) -> tuple[ConditionField, ...]:
    """Return the condition field schemas for the given assay type."""
    return ASSAY_CONDITIONS[assay_type][1]
