"""Registry unit-lint and the signal-dimension invariant.

These guard the "both" design (a custom ``[signal]`` dimension *and* an explicit
``ParamKind`` label): the lint keeps each parameter's kind, unit, and log-scale
flag mutually consistent so none can silently drift, and the dimension test pins
that a signal coefficient (``au/M``) is not confusable with a binding constant
(``1/M``).
"""

import pint
import pytest

from core.assays.registry import ASSAY_REGISTRY, KIND_UNIT, ParamKind
from core.units import Q_


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
