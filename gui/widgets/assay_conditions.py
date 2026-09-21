"""Registry mapping AssayType to its condition fields for the GUI.

This is the only place assay-specific GUI knowledge lives.  Adding a new
assay type to the GUI requires only one new entry in ASSAY_CONDITIONS plus
the usual core registry changes — zero widget code changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from core.assays import ASSAY_CLASSES, AssayType
from core.assays.base import BaseAssay
from core.assays.registry import ASSAY_REGISTRY
from core.pipeline.inputs import TITRANT, ErrorModel, shared_key


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


# Maps AssayType → the condition fields its form shows, in the order they appear.
# AssayConfigPanel reads this to build the dynamic conditions form.
ASSAY_CONDITIONS: dict[AssayType, tuple[ConditionField, ...]] = {
    AssayType.GDA: (
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
    AssayType.IDA: (
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
    AssayType.DBA_HtoD: (
        ConditionField(
            'fixed_conc',
            '[Dye]<sub>0</sub>',
            'Fixed dye concentration (host is titrated)',
            151e-6,
            'M',
            'concentration',
        ),
    ),
    AssayType.DBA_DtoH: (
        ConditionField(
            'fixed_conc',
            '[Host]<sub>0</sub>',
            'Fixed host concentration (dye is titrated)',
            10e-6,
            'M',
            'concentration',
        ),
    ),
    AssayType.DYE_ALONE: (),  # no conditions needed
    AssayType.DBA_HG2: (
        ConditionField(
            'h0',
            '[Host]<sub>0</sub>',
            'Total host concentration in the cuvette (fixed; guest is titrated)',
            3e-4,
            'M',
            'concentration',
        ),
    ),
    AssayType.DBA_H2G: (
        ConditionField(
            'h0',
            '[Host]<sub>0</sub>',
            'Total host concentration in the cuvette (fixed; guest is titrated)',
            3e-4,
            'M',
            'concentration',
        ),
    ),
}


#: The titrant stock, the one condition no assay declares: it says how the
#: samples were made rather than what is in them. A sample of volume V₀ that has
#: received a cumulative volume W of this stock holds x = c_T·W/(V₀+W) of
#: titrant, so the fraction of the final volume that came from the stock is
#: x/c_T and every other total falls by that fraction. Entered in the Assay
#: Configuration panel only when the user states that the additions dilute the
#: sample; 0 means nothing has been entered yet.
TITRANT_STOCK_FIELD = ConditionField(
    'titrant_stock',
    'Titrant stock concentration',
    'Concentration of the stock the titrant was added from. The concentrations in the data file are the '
    'titrant concentrations in the cuvette after each addition, so the stock is more concentrated than the '
    'highest of them.',
    0.0,
    'M',
    'concentration',
)


def assay_class(assay_type: AssayType) -> type[BaseAssay]:
    """Return the assay class for the given type."""
    return ASSAY_CLASSES[assay_type]


def condition_fields(assay_type: AssayType) -> tuple[ConditionField, ...]:
    """Return the condition field schemas for the given assay type."""
    return ASSAY_CONDITIONS[assay_type]


def input_labels(assay_type: AssayType) -> dict[str, str]:
    """Every input a fit of *assay_type* rests on, as an HTML display label.

    Its conditions, plus the titrant, which moves as one factor over the whole
    series. One definition: the Input Uncertainty panel writes these names on
    screen and the exported report writes them for the same inputs, so the two
    must not drift apart.
    """
    labels = {field.key: field.label for field in ASSAY_CONDITIONS[assay_type]}
    labels[TITRANT] = f'{ASSAY_REGISTRY[assay_type].x_label} (titrant, whole series)'
    return labels


def result_input_labels(assay_type_name: str, fit_config: Optional[Mapping[str, Any]] = None) -> dict[str, str]:
    """Every source of a stored fit, as plain display text, named from the fit's own assay.

    The one naming a report of a finished fit uses — on screen and in the
    exported files alike — so one fit's inputs read the same wherever they are
    shown, whatever assay is selected now.

    Parameters
    ----------
    assay_type_name : str
        ``FitResult.assay_type``: the ``AssayType`` name the fit records.
    fit_config : Mapping, optional
        ``FitResult.fit_config``. Its shared error sources get a name of their
        own, ``'Host and dye stock (shared by [Host]₀, [Dye]₀)'``, under
        :func:`~core.pipeline.inputs.shared_key` of the source's name: a shift
        reported against a shared source then reads as the several inputs it
        moved.

    Returns
    -------
    dict[str, str]
        Source key → plain display name. Empty for an assay type this version
        does not know, where a report falls back on the source's key.
    """
    # Imported here, not at module scope: gui.plotting's package __init__ pulls
    # in the widgets that read this registry, so a module-level import of
    # anything under gui.plotting would close a cycle through it.
    from gui.plotting.labels import plain_label

    try:
        assay_type = AssayType[assay_type_name]
    except KeyError:
        return {}
    labels = {key: plain_label(label) for key, label in input_labels(assay_type).items()}
    for source in ErrorModel.from_dict(fit_config or {}).shared:
        moved = ', '.join(labels.get(key, key) for key in source.inputs)
        labels[shared_key(source.name)] = f'{source.name} (shared by {moved})'
    return labels
