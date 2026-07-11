"""Registry-driven knob model for the simulation applet.

A *knob* is one live, user-adjustable numeric input.  For a given assay the full
knob set is, mechanically, its conditions (``condition_fields``) plus its model
parameters (``parameter_keys``) — with **no assumption** about which Ka is a
condition vs a parameter (that differs across assays: ``Ka_dye`` is a condition
for GDA/IDA but a parameter for DBA).  The categorical DBA ``mode`` is not a knob;
it is derived from the assay subtype where the spec is assembled.

Each knob carries its **canonical Pint unit** (from the registry), so display and unit
conversions go through Pint / ``core.units`` — never a hand-rolled token or hardcoded
factor.  Classification is read from the registry's explicit labels, not re-derived:
parameters use ``param_kinds`` (``ParamKind`` + ``KIND_UNIT``) — ``log`` ⇔
``BINDING_CONSTANT``, unit from ``KIND_UNIT`` — which is lint-checked against the units on
the registry side, so the applet cannot drift.  Conditions (not in ``param_kinds``) use
``ConditionField.unit_type``.  Whether a knob is a concentration (→ nM/µM/mM/M selector)
is the one thing derived from the unit, via Pint dimensionality.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.assays.registry import ASSAY_REGISTRY, KIND_UNIT, AssayType, ParamKind
from core.units import Q_, Unit
from gui.widgets.assay_conditions import condition_fields

# Dimensionality shared by every concentration unit (M, µM, nM, …).
_MOLAR_DIM = Q_(1, 'M').dimensionality


@dataclass(frozen=True)
class SimKnob:
    """One live numeric control: a value plus a user-adjustable [vmin, vmax]."""

    key: str
    label: str  # HTML, e.g. 'K<sub>a,guest</sub>'
    tooltip: str
    unit: Unit  # canonical Pint unit from the registry
    log: bool  # association constant → log slider (registry-declared)
    default: float  # magnitude in `unit`
    vmin: float
    vmax: float
    is_condition: bool

    @property
    def is_concentration(self) -> bool:
        """Molar-dimensioned knobs get a nM/µM/mM/M selector (Pint dimensionality)."""
        return self.unit.dimensionality == _MOLAR_DIM

    @property
    def allows_negative(self) -> bool:
        """Concentrations and association constants are strictly positive; signal
        coefficients (au, au·M⁻¹ — e.g. a calibration intercept) may be negative."""
        return not (self.log or self.is_concentration)


@dataclass(frozen=True)
class _ParamSpec:
    label: str
    tooltip: str
    default: float
    vmin: float
    vmax: float


# Default model-parameter values + slider ranges, keyed by parameter name.
# Defaults are seeded from the proven ground truth in tests/conftest.py so each
# assay opens on a visibly-shaped curve.  Ranges are sensible *simulation* spans —
# deliberately NOT the registry ``default_bounds`` (those are 20+-decade fit search
# ranges, and ``I_H`` is pinned to a zero-width ``(0, 0)`` there).
SIM_PARAM_DEFAULTS: dict[str, _ParamSpec] = {
    'Ka_guest': _ParamSpec('K<sub>a,guest</sub>', 'Host–guest association constant', 1e6, 1e3, 1e9),
    'Ka_dye': _ParamSpec('K<sub>a,dye</sub>', 'Host–dye association constant', 5e5, 1e3, 1e9),
    'Ka_HG': _ParamSpec('K<sub>a,HG</sub>', 'First stepwise association constant', 1e6, 1e3, 1e9),
    'Ka_HG2': _ParamSpec('K<sub>a,HG₂</sub>', 'Second stepwise constant (host binds two guests)', 2e5, 1e3, 1e9),
    'Ka_H2G': _ParamSpec('K<sub>a,H₂G</sub>', 'Second stepwise constant (two hosts bind one guest)', 2e5, 1e3, 1e9),
    'I0': _ParamSpec('I<sub>0</sub>', 'Baseline signal offset', 0.0, -1e3, 1e3),
    'I_dye_free': _ParamSpec('I<sub>dye,free</sub>', 'Signal per unit free dye', 5e7, 0.0, 5e8),
    'I_dye_bound': _ParamSpec('I<sub>dye,bound</sub>', 'Signal per unit host–dye complex', 3e8, 0.0, 1e9),
    'I_G': _ParamSpec('I<sub>G</sub>', 'Signal per unit free guest', 1e6, 0.0, 1e8),
    'I_H': _ParamSpec('I<sub>H</sub>', 'Signal per unit free host', 0.0, 0.0, 1e8),
    'I_HG': _ParamSpec('I<sub>HG</sub>', 'Signal per unit HG complex', 1e7, 0.0, 1e8),
    'I_HG2': _ParamSpec('I<sub>HG₂</sub>', 'Signal per unit HG₂ complex', 5e6, 0.0, 1e8),
    'I_H2G': _ParamSpec('I<sub>H₂G</sub>', 'Signal per unit H₂G complex', 5e6, 0.0, 1e8),
    'slope': _ParamSpec('slope', 'Linear calibration slope', 5e10, 0.0, 1e11),
    'intercept': _ParamSpec('intercept', 'Linear calibration intercept', 100.0, -1e4, 1e4),
}


# Sensible default titration range per assay (start, stop in Molar), matching the
# species each assay titrates and the ranges used by the synthetic generators in
# tests/conftest.py — so the applet opens on a well-framed transition.
TITRANT_RANGE: dict[AssayType, tuple[float, float]] = {
    AssayType.GDA: (0.0, 30e-6),
    AssayType.IDA: (0.0, 50e-6),
    AssayType.DBA_HtoD: (0.0, 50e-6),
    AssayType.DBA_DtoH: (0.0, 50e-6),
    AssayType.DYE_ALONE: (0.0, 20e-6),
    AssayType.DBA_HG2: (0.0, 1.2e-3),
    AssayType.DBA_H2G: (0.0, 6e-4),
}


def slider_bounds(default: float, log: bool) -> tuple[float, float]:
    """Default slider range for a *condition* knob, derived from its default.

    Association constant (``log``): three decades either side.  Concentration:
    ``0 .. 5×default``.  Never derived from the registry fit search bounds.  Signal
    knobs are all parameters and carry explicit ranges in :data:`SIM_PARAM_DEFAULTS`
    instead (a signal coefficient has no natural scale derivable from a single
    default — e.g. ``I_H`` defaults to 0).
    """
    if log:
        d = default if default > 0 else 1e6
        return (d / 1e3, d * 1e3)
    d = default if default > 0 else 1e-5
    return (0.0, d * 5)


def knobs_for(assay_type: AssayType) -> list[SimKnob]:
    """Return the full live-knob list for *assay_type*: conditions ∪ parameters."""
    meta = ASSAY_REGISTRY[assay_type]
    knobs: list[SimKnob] = []

    for f in condition_fields(assay_type):
        log = f.unit_type == 'binding_constant'
        unit = Q_(1, f.unit).units
        vmin, vmax = slider_bounds(f.default, log)
        knobs.append(SimKnob(f.key, f.label, f.tooltip, unit, log, f.default, vmin, vmax, is_condition=True))

    for key in meta.parameter_keys:
        if key not in SIM_PARAM_DEFAULTS:
            raise KeyError(f'No simulation default for parameter {key!r}; add it to SIM_PARAM_DEFAULTS.')
        spec = SIM_PARAM_DEFAULTS[key]
        kind = meta.param_kinds[key]  # registry-declared, lint-checked classification
        log = kind == ParamKind.BINDING_CONSTANT
        unit = Q_(1, KIND_UNIT[kind]).units
        knobs.append(
            SimKnob(key, spec.label, spec.tooltip, unit, log, spec.default, spec.vmin, spec.vmax, is_condition=False)
        )

    return knobs
