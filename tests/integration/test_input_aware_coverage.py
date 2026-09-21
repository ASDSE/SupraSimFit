"""Coverage of the input-aware 95 % interval when the entered inputs carry ordinary entry errors.

Sixty seeded synthetic titrations per case. The truth generates the
signal; every entered input is then drawn around its true value at the stated
uncertainty, as a user who weighs and pipettes with that precision would enter
it. The input-aware interval has to contain the true Ka in about 95 % of the
datasets; the interval that takes the inputs as exact is reported beside it,
and so is how often the diagnostics blame the model or the inputs on these
consistent data.

With N = 60 the binomial 95 % range around a true coverage of 0.95 starts at
53 of 60, which is the pass mark.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.assays import ASSAY_CLASSES
from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.models.equilibrium import dba_signal, ida_signal
from core.pipeline.diagnostics import Verdict, runs_test, verdict
from core.pipeline.input_aware import conflict, fit_jacobian, input_aware
from core.pipeline.inputs import TITRANT, InputSpec, constraints
from core.pipeline.varpro import Projection
from core.units import Q_
from tests.conftest import DBA_TRUE, IDA_TRUE

N_DATASETS = 60
_SIGNAL = dict(I0=0.0, I_dye_free=5e7, I_dye_bound=3e8)

CASES = {
    'IDA': dict(
        assay_type=AssayType.IDA,
        ka_key='Ka_guest',
        n=12,
        noise=0.005,
        x_max=5e-5,
        truth={'Ka_dye': IDA_TRUE['Ka_dye'], 'h0': IDA_TRUE['h0'], 'd0': IDA_TRUE['d0']},
        sigmas={'Ka_dye': 0.10, 'h0': 0.03, 'd0': 0.03, TITRANT: 0.03},
    ),
    'DBA_DtoH': dict(
        assay_type=AssayType.DBA_DtoH,
        ka_key='Ka_dye',
        n=20,
        noise=0.01,
        x_max=4e-5,
        truth={'fixed_conc': DBA_TRUE['fixed_conc']},
        sigmas={'fixed_conc': 0.03, TITRANT: 0.03},
    ),
}
_TRUE_KA = {'IDA': IDA_TRUE['Ka_guest'], 'DBA_DtoH': DBA_TRUE['Ka_dye']}


def simulate(name: str, seed: int, entry_error: float = 1.0):
    """One dataset of *name*: the assay as a user would have entered it, and the true Ka.

    *entry_error* scales the entry errors against the stated uncertainties;
    above one the entered inputs contradict what is stated about them.
    """
    case = CASES[name]
    rng = np.random.default_rng([seed, len(name)])
    x_true = np.linspace(case['x_max'] / case['n'], case['x_max'], case['n'])
    truth = case['truth']
    if case['assay_type'] is AssayType.IDA:
        y = ida_signal(Ka_guest=_TRUE_KA[name], g0_values=x_true, **truth, **_SIGNAL)
    else:
        y = dba_signal(Ka_dye=_TRUE_KA[name], x_titrant=x_true, y_fixed=truth['fixed_conc'], mode='DtoH', **_SIGNAL)
    y = y + rng.normal(0.0, case['noise'] * np.ptp(y), y.size)
    # An entered value stays positive: a draw below 5 % of the truth is entered as 5 % of it.
    entered = {
        key: max(1.0 + entry_error * sigma * rng.standard_normal(), 0.05) for key, sigma in case['sigmas'].items()
    }
    units = {'Ka_dye': '1/M'}
    conditions = {key: Q_(value * entered[key], units.get(key, 'M')) for key, value in truth.items()}
    if name == 'DBA_DtoH':
        conditions['mode'] = 'DtoH'
    assay = ASSAY_CLASSES[case['assay_type']](
        x_data=Q_(x_true * entered[TITRANT], 'M'), y_data=Q_(y, 'au'), **conditions
    )
    return assay, _TRUE_KA[name]


def analyse(name: str, seed: int, entry_error: float = 1.0) -> tuple[bool, bool, Verdict]:
    """Whether each interval holds the true Ka, and the verdict of the diagnostics."""
    case = CASES[name]
    assay, true_ka = simulate(name, seed, entry_error)
    projection = Projection(assay, dict(ASSAY_REGISTRY[case['assay_type']].default_bounds))
    fit = projection.fit()
    key = case['ka_key']
    conditional = projection.interval(key, fit)
    specs = {k: InputSpec.sigma_pct(100 * s) for k, s in case['sigmas'].items()}
    result = input_aware(projection, fit, constraints(specs, assay.get_conditions()))
    aware = result.profiles[key].interval
    x = assay.x_data.magnitude
    found = verdict(
        runs_test(
            projection.residual(fit.ka),
            x,
            fit_jacobian(projection, input_aware(projection, fit, (), conditional={key: conditional})),
        ),
        runs_test(projection.residual(result.fit.ka, offsets=result.fit.offsets), x, fit_jacobian(projection, result)),
        conflict(result),
    )
    return aware.low <= true_ka <= aware.high, conditional.low <= true_ka <= conditional.high, found


@pytest.mark.parametrize('name', list(CASES))
def test_the_input_aware_interval_covers_the_truth_at_its_stated_level(name, capsys):
    outcomes = [analyse(name, seed) for seed in range(N_DATASETS)]
    aware = np.mean([o[0] for o in outcomes])
    conditional = np.mean([o[1] for o in outcomes])
    blamed = np.mean([o[2] in (Verdict.MODEL_INADEQUATE, Verdict.INPUTS_CONFLICT) for o in outcomes])
    with capsys.disabled():
        print(
            f'\n{name}: coverage input-aware {aware:.2f}, inputs taken as exact {conditional:.2f}; '
            f'model or inputs blamed on consistent data {blamed:.2f}'
        )
    assert aware >= 53 / 60
    # Entry errors of this size are what the fixed-input interval does not know about: where a binding
    # constant is among the inputs it misses the truth in a third of the datasets or more.
    assert conditional <= aware
    if 'Ka_dye' in CASES[name]['sigmas']:
        assert conditional < aware - 0.2
    # Entered inputs that are off by their stated uncertainty may well explain a misfit; they are not in conflict.
    assert blamed <= 0.15
