"""Registry mapping AssayType to its condition fields for the GUI.

This is the only place assay-specific GUI knowledge lives.  Adding a new
assay type to the GUI requires only one new entry in ASSAY_CONDITIONS plus
the usual core registry changes — zero widget code changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

import numpy as np

from core.assays import ASSAY_CLASSES, AssayType
from core.assays.base import BaseAssay
from core.assays.registry import ASSAY_REGISTRY
from core.pipeline.inputs import TITRANT, ErrorModel, shared_key
from core.units import Q_, Quantity
from gui.plotting.labels import PARAM_LABELS, field_text, plain_label

#: Each assay's names in the window: short, where a session is named beside its data
#: (session switcher, file card), and in words, where the model is stated (status bar).
ASSAY_NAMES: dict[AssayType, tuple[str, str]] = {
    AssayType.GDA: ('GDA', 'Guest displacement'),
    AssayType.IDA: ('IDA', 'Indicator displacement'),
    AssayType.DBA_HtoD: ('DBA host → dye', 'Direct binding, host into dye'),
    AssayType.DBA_DtoH: ('DBA dye → host', 'Direct binding, dye into host'),
    AssayType.DBA_HG2: ('HG₂', 'Host–guest 1:2'),
    AssayType.DBA_H2G: ('H₂G', 'Host–guest 2:1'),
    AssayType.DYE_ALONE: ('Dye alone', 'Dye alone'),
}


@dataclass(frozen=True)
class ConditionField:
    """Schema for one assay condition input field.

    Attributes
    ----------
    key : str
        Dict key passed to the assay constructor (e.g. ``"Ka_dye"``).
    label : str
        HTML display label shown in the form (e.g. ``"K<sub>a</sub>,dye"``).
    tooltip : str
        Longer scientific description shown as a tooltip.
    default : float
        Default numeric value in the base unit (M or M⁻¹).
    unit : str
        Base unit string (e.g. ``"M"`` or ``"M⁻¹"``).
    unit_type : str
        The units the condition is entered in:
        ``"concentration"`` → nM / µM / mM / M, chosen per condition (default µM),
        ``"binding_constant"`` → M⁻¹,
        ``""`` → no unit.
        The choices and the default of each are listed in :data:`UNIT_CHOICES`.
    """

    key: str
    label: str
    tooltip: str
    default: float
    unit: str = ''
    unit_type: str = ''


#: The ``mode`` condition of a direct binding assay, fixed by the model chosen.
DBA_MODES: dict[AssayType, str] = {AssayType.DBA_HtoD: 'HtoD', AssayType.DBA_DtoH: 'DtoH'}

#: The units a condition of each ``unit_type`` can be entered in, and the one its field opens on.
UNIT_CHOICES: dict[str, tuple[tuple[str, ...], str]] = {
    'concentration': (('nM', 'µM', 'mM', 'M'), 'µM'),
    'binding_constant': (('M⁻¹',), 'M⁻¹'),
}


# Maps AssayType → the condition fields its form shows, in the order they appear.
# The binding model (gui.binding) reads this to build the conditions of each model.
ASSAY_CONDITIONS: dict[AssayType, tuple[ConditionField, ...]] = {
    AssayType.GDA: (
        ConditionField(
            'Ka_dye',
            PARAM_LABELS['Ka_dye'],
            'Known host–dye association constant',
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
            PARAM_LABELS['Ka_dye'],
            'Known host–dye association constant',
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
#: x/c_T and every other total falls by that fraction. Entered under Binding
#: model only when the user states that the additions dilute the sample.
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


def condition_field(assay_type: AssayType, key: str) -> ConditionField | None:
    """The field condition *key* has in *assay_type*'s form, the titrant stock included; ``None`` when it has none."""
    if key == TITRANT_STOCK_FIELD.key:
        return TITRANT_STOCK_FIELD
    return next((field for field in ASSAY_CONDITIONS[assay_type] if field.key == key), None)


def condition_name(field: ConditionField) -> str:
    """*field*'s label in plain text: ``[Host]₀``."""
    return plain_label(field.label)


def format_condition(field: ConditionField, value: Quantity, unit: str) -> str:
    """*value* of *field* in plain text in *unit*, one of the units its form offers: ``4.3 µM``.

    *unit* is ignored for a field without a unit, whose value is written bare. The number is
    written as the field writes it.
    """
    if not field.unit:
        return field_text(float(value.magnitude))
    scale = float(Q_(1, unit).to(field.unit).magnitude)
    return f'{field_text(value.to(field.unit).magnitude / scale)} {unit}'.rstrip()


def same_inputs(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """Whether two assay-condition dicts hold the same inputs, compared in base units."""
    if a.keys() != b.keys():
        return False
    for key, x in a.items():
        y = b[key]
        if hasattr(x, 'dimensionality') and hasattr(y, 'dimensionality'):
            if x.dimensionality != y.dimensionality:
                return False
            if not np.isclose(x.to_base_units().magnitude, y.to_base_units().magnitude, rtol=1e-9, atol=0.0):
                return False
        elif x != y:
            return False
    return True


def input_labels(assay_type: AssayType) -> dict[str, str]:
    """Every input a fit of *assay_type* rests on, as an HTML display label.

    Its conditions, plus the titrant, which moves as one factor over the whole
    series. One definition: Input uncertainty writes these names on
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
    try:
        assay_type = AssayType[assay_type_name]
    except KeyError:
        return {}
    labels = {key: plain_label(label) for key, label in input_labels(assay_type).items()}
    for source in ErrorModel.from_dict(fit_config or {}).shared:
        moved = ', '.join(labels.get(key, key) for key in source.inputs)
        labels[shared_key(source.name)] = f'{source.name} (shared by {moved})'
    return labels
