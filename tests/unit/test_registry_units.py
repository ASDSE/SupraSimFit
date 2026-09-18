"""Registry unit-lint and the signal-dimension invariant.

These guard the "both" design (a custom ``[signal]`` dimension *and* an explicit
``ParamKind`` label): the lint keeps each parameter's kind, unit, log-scale
flag and signal species mutually consistent so none can silently drift, and the
dimension test pins that a signal coefficient (``au/M``) is not confusable with
a binding constant (``1/M``).
"""

import numpy as np
import pint
import pytest

from core.assays import ASSAY_CLASSES
from core.assays.registry import ASSAY_REGISTRY, KIND_UNIT, AssayType, ParamKind
from core.units import Q_

# One set of conditions per binding assay, enough to build it and ask for its species.
_CONDITIONS = {
    AssayType.GDA: dict(Ka_dye=Q_(5e5, '1/M'), h0=Q_(1e-5, 'M'), g0=Q_(2e-5, 'M')),
    AssayType.IDA: dict(Ka_dye=Q_(5e5, '1/M'), h0=Q_(1e-5, 'M'), d0=Q_(5e-6, 'M')),
    AssayType.DBA_HtoD: dict(fixed_conc=Q_(5e-6, 'M'), mode='HtoD'),
    AssayType.DBA_DtoH: dict(fixed_conc=Q_(5e-6, 'M'), mode='DtoH'),
    AssayType.DBA_HG2: dict(h0=Q_(1e-5, 'M')),
    AssayType.DBA_H2G: dict(h0=Q_(1e-5, 'M')),
}


def test_every_parameter_has_a_kind():
    """Every registered parameter carries an explicit ParamKind."""
    for at, meta in ASSAY_REGISTRY.items():
        for key in meta.parameter_keys:
            assert key in meta.param_kinds, f'{at.name}: parameter {key!r} has no ParamKind'


def test_param_kind_matches_declared_unit():
    """Each parameter's ParamKind is dimensionally consistent with its unit.

    With ``au = [signal]`` the three kinds have distinct dimensions
    (``1/[concentration]``, ``[signal]``, ``[signal]/[concentration]``), so a
    mislabeled parameter — e.g. a Ka declared as ``au/M`` — is caught here.
    """
    for at, meta in ASSAY_REGISTRY.items():
        units = meta.units
        for key, kind in meta.param_kinds.items():
            declared = Q_(1.0, units[key]).dimensionality
            expected = Q_(1.0, KIND_UNIT[kind]).dimensionality
            assert declared == expected, (
                f'{at.name}: {key} unit {units[key]!r} has dimension {dict(declared)} '
                f'but kind {kind.name} expects {KIND_UNIT[kind]!r} ({dict(expected)})'
            )


def test_binding_constants_are_exactly_the_log_scale_params():
    """A parameter is a BINDING_CONSTANT iff it is sampled in log space."""
    for at, meta in ASSAY_REGISTRY.items():
        for key, kind in meta.param_kinds.items():
            is_binding_constant = kind is ParamKind.BINDING_CONSTANT
            is_log_scale = key in meta.log_scale_keys
            assert is_binding_constant == is_log_scale, (
                f'{at.name}: {key} kind={kind.name} but log_scale={is_log_scale}'
            )


def test_signal_unit_has_its_own_dimension():
    """``au`` is not dimensionless, so ``au/M`` cannot be read as ``1/M``."""
    assert not Q_(1.0, 'au').dimensionless
    assert Q_(1.0, 'au/M').dimensionality != Q_(1.0, '1/M').dimensionality
    with pytest.raises(pint.DimensionalityError):
        Q_(1.0, 'au/M').to('1/M')


def test_every_signal_coefficient_of_a_binding_assay_names_a_species_the_assay_returns():
    """The fit engine's design columns come from ``species()``, so each coefficient must name one of them."""
    x = np.linspace(1e-7, 5e-5, 6)
    for at, meta in ASSAY_REGISTRY.items():
        coefficients = {k for k, kind in meta.param_kinds.items() if kind is ParamKind.SIGNAL_COEFFICIENT}
        if ParamKind.BINDING_CONSTANT not in meta.param_kinds.values():
            assert meta.signal_species == {}, f'{at.name} has no binding equilibrium and names species'
            continue
        assert set(meta.signal_species) == coefficients, f'{at.name}: signal_species does not cover every coefficient'
        assay = ASSAY_CLASSES[at](x_data=Q_(x, 'M'), y_data=Q_(np.ones(6), 'au'), **_CONDITIONS[at])
        species = assay.species(np.full(len(meta.parameter_keys), 1e5))
        for key, name in meta.signal_species.items():
            assert name in species, f'{at.name}: {key} names {name!r}, not a species the assay returns'
