"""The entered inputs of a fit: moving them on an assay, and reading their stated uncertainty.

- ``BaseAssay.with_inputs`` moves exactly the named inputs: the speciation of the
  moved copy equals that of an assay constructed directly at the moved values,
  for every binding assay; anything that is not an input is refused.
- ``constraints`` turns the stated uncertainties into offsets a fit may use, in
  the order the inputs are declared, converts a spread given in the input's own
  unit, and refuses what cannot be fitted in words that name the input.
- A shared source adds one constraint after the inputs' own; the titrant stock
  is a condition of dimension M that is not an input.
- The specs survive the round trip through a results file.
"""

import numpy as np
import pytest

from core.assays import ASSAY_CLASSES
from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.pipeline.inputs import (
    _INPUT_FLOOR,
    TITRANT,
    TITRANT_STOCK,
    ErrorModel,
    InputConstraint,
    InputSpec,
    SharedSource,
    constraints,
    perturbable_inputs,
    shared_key,
    specs_from_dict,
    specs_to_dict,
)
from core.units import Q_, Quantity
from tests.unit.test_varpro import _BINDING_ASSAYS, _CONDITIONS

_IDA = _CONDITIONS[AssayType.IDA]
_LABELS = {'Ka_dye': 'Ka(dye)', 'h0': '[Host]0', 'd0': '[Dye]0', TITRANT: 'Guest (titrant)'}


@pytest.mark.parametrize('assay_type', _BINDING_ASSAYS, ids=lambda t: t.name)
def test_with_inputs_moves_exactly_the_named_inputs(assay_type):
    x = np.linspace(1e-7, 5e-5, 9)
    y = np.linspace(1.0, 2.0, 9)
    conditions = _CONDITIONS[assay_type]
    assay = ASSAY_CLASSES[assay_type](x_data=Q_(x, 'M'), y_data=Q_(y, 'au'), **conditions)
    inputs = [k for k, v in conditions.items() if isinstance(v, Quantity)]
    offsets = {key: 0.04 * (i + 1) * (-1) ** i for i, key in enumerate(inputs)} | {TITRANT: 0.07}

    moved = assay.with_inputs(offsets)
    direct = ASSAY_CLASSES[assay_type](
        x_data=Q_(x * 1.07, 'M'),
        y_data=Q_(y, 'au'),
        **{k: v * (1 + offsets[k]) if k in offsets else v for k, v in conditions.items()},
    )
    params = np.array([3e5 if k.startswith('Ka') else 1.0 for k in ASSAY_REGISTRY[assay_type].parameter_keys])
    for name, values in direct.species(params).items():
        assert moved.species(params)[name] == pytest.approx(values, rel=1e-13), name
    assert moved.assay_type is assay_type and np.array_equal(moved.y_data.magnitude, y)

    # One input alone leaves every other one, and the original, as entered.
    only = assay.with_inputs({inputs[0]: 0.1})
    assert np.array_equal(only.x_data.magnitude, x) and np.array_equal(assay.x_data.magnitude, x)
    for key in inputs:
        expected = conditions[key].magnitude * (1.1 if key == inputs[0] else 1.0)
        assert only.get_conditions()[key].magnitude == pytest.approx(expected, rel=1e-15)
        assert assay.get_conditions()[key].magnitude == conditions[key].magnitude


def test_with_inputs_refuses_what_is_not_an_input_and_what_the_assay_cannot_hold():
    x = np.linspace(1e-7, 5e-5, 9)
    dba = ASSAY_CLASSES[AssayType.DBA_DtoH](
        x_data=Q_(x, 'M'), y_data=Q_(x * 1e6, 'au'), **_CONDITIONS[AssayType.DBA_DtoH]
    )
    for key in ('h0', 'mode', 'y_data'):
        with pytest.raises(ValueError, match='is not an input of the DBA_DtoH assay'):
            dba.with_inputs({key: 0.1})
    with pytest.raises(ValueError, match='fixed_conc must be positive'):
        dba.with_inputs({'fixed_conc': -1.0})


def test_constraints_follow_the_declared_order_and_keep_only_what_varies():
    specs = {
        TITRANT: InputSpec.sigma_pct(2.0),
        'd0': InputSpec.interval_pct(-4.0, 6.0),
        'h0': InputSpec.sigma_pct(0.0),
        'Ka_dye': InputSpec.sigma_abs(5e4),
    }
    found = constraints(ErrorModel(specs=specs), _IDA)
    assert [c.key for c in found] == ['Ka_dye', 'd0', TITRANT]
    ka_dye, d0, titrant = found
    # 5e4 1/M on an entered 5e5 1/M is 10 %.
    assert ka_dye == InputConstraint('Ka_dye', pytest.approx(0.10), -1.0 + _INPUT_FLOOR, np.inf, 5e5, 'this input')
    # A message names an input by the label the interface gives it.
    assert [c.name for c in constraints(ErrorModel(specs=specs), _IDA, _LABELS)] == [
        _LABELS['Ka_dye'],
        _LABELS['d0'],
        _LABELS[TITRANT],
    ]
    assert titrant.name == 'the titrant'
    assert (d0.sigma, d0.lo, d0.hi, d0.nominal) == (None, pytest.approx(-0.04), pytest.approx(0.06), 5e-6)
    assert (titrant.sigma, titrant.nominal) == (pytest.approx(0.02), None)
    # A range given as the input's own low and high values.
    (h0,) = constraints(ErrorModel(specs={'h0': InputSpec.interval_abs(0.9e-5, 1.2e-5)}), _IDA)
    assert (h0.lo, h0.hi) == (pytest.approx(-0.1), pytest.approx(0.2))
    assert constraints(ErrorModel(specs={}), _IDA) == ()


@pytest.mark.parametrize(
    ('specs', 'message'),
    [
        ({'g0': InputSpec.sigma_pct(3.0)}, 'stated for an input, which this assay does not have as an input'),
        ({TITRANT: InputSpec.sigma_abs(1e-6)}, 'titrant .* has to be given as a percentage'),
        ({TITRANT: InputSpec.interval_abs(1e-6, 2e-6)}, 'titrant .* has to be given as percentages'),
        ({'h0': InputSpec.sigma_pct(-1.0)}, r'The uncertainty of \[Host\]0 is negative'),
        ({'d0': InputSpec.interval_pct(5.0, -5.0)}, r'The range of \[Dye\]0 ends below where it starts'),
        ({'Ka_dye': InputSpec.interval_pct(-100.0, 10.0)}, r'The range of Ka\(dye\) reaches zero'),
        ({'h0': InputSpec.interval_abs(0.0, 2e-5)}, r'The range of \[Host\]0 reaches zero'),
    ],
)
def test_what_cannot_be_fitted_is_refused_in_words_that_name_the_input(specs, message):
    with pytest.raises(ValueError, match=message):
        constraints(ErrorModel(specs=specs), _IDA, _LABELS)


def test_specs_round_trip_through_a_results_file_dict():
    specs = {
        'Ka_dye': InputSpec.interval_abs(4e5, 7e5),
        'h0': InputSpec.sigma_pct(3.0),
        'd0': InputSpec.sigma_abs(2e-7),
        TITRANT: InputSpec.interval_pct(-2.0, 5.0),
    }
    written = specs_to_dict(specs)
    assert written['Ka_dye'] == {'kind': 'interval', 'sigma': 0.0, 'lo': 4e5, 'hi': 7e5, 'relative': False}
    assert specs_from_dict(written) == specs
    assert constraints(ErrorModel(specs=specs_from_dict(written)), _IDA) == constraints(ErrorModel(specs=specs), _IDA)


def test_the_titrant_stock_is_not_an_input_of_its_own():
    """The stock is the titrant's scale, so it moves with ``TITRANT`` and is not listed."""
    diluted = {**_IDA, TITRANT_STOCK: Q_(1e-3, 'M'), 'stock_contains': ('d0',)}
    assert perturbable_inputs(diluted) == perturbable_inputs(_IDA)
    assert TITRANT_STOCK not in dict(perturbable_inputs(diluted))


def test_a_shared_source_is_one_sigma_constraint_after_the_inputs_own():
    own = {TITRANT: InputSpec.sigma_pct(2.0), 'h0': InputSpec.interval_pct(-5, 5)}
    shared = (SharedSource('Host and dye stock', 4.0, ('h0', 'd0')), SharedSource('Balance', 1.5, ('d0', TITRANT)))
    found = constraints(ErrorModel(specs=own, shared=shared), _IDA, _LABELS)

    # The own constraints are those of the same specs alone, in the declared order of the inputs.
    assert found[:2] == constraints(ErrorModel(specs=own), _IDA, _LABELS)
    assert [c.key for c in found] == ['h0', TITRANT, shared_key('Host and dye stock'), shared_key('Balance')]
    assert found[2] == InputConstraint(
        shared_key('Host and dye stock'), 0.04, -1.0 + _INPUT_FLOOR, np.inf, None, 'Host and dye stock'
    )
    assert found[3].sigma == pytest.approx(0.015) and found[3].name == 'Balance'
