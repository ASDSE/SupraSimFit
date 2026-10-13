"""The independent reference computes the interval the engine's definition names, rules included.

The reference-agreement check compares the engine's interval with the one
:func:`validation.reference.reference_intervals` computes by machinery of its
own. A rule of the reported interval that the reference lacks shows there as a
disagreement that is a gap in the reference and not a defect of the engine, so
each rule is pinned here on data whose answer is known without either
computation: a one-step titration has no second binding step, and the engine's
reading of the same definition is a second, independent one.
"""

from __future__ import annotations

import numpy as np

from core.assays.hg2 import HG2Assay
from core.pipeline.inputs import ErrorModel, InputSpec
from core.pipeline.varpro import Projection
from core.units import Q_
from tests.conftest import HG2_TRUE, _make_hg2_data
from validation.checks import CHECKS
from validation.generate import dataset
from validation.reference import AGREEMENT_DECADES, reference_intervals

_CASES = {case.id: case for case in CHECKS['reference-agreement'].cases}

#: Ka box of the stepwise titrations below: six and seven decades around the
#: constants, so the reference's two-dimensional grid stays small.
_HG2_BOUNDS = {'Ka_HG': (1e3, 1e9), 'Ka_HG2': (1.0, 1e7)}


def _stepwise(ka_hg2: float, seed: int) -> HG2Assay:
    """The 1:2 ground truth with the second constant *ka_hg2*: twelve points, noise of 1 % of the largest signal."""
    x, clean = _make_hg2_data({**HG2_TRUE, 'Ka_HG2': ka_hg2}, n_points=12)
    y = clean + np.random.default_rng(seed).normal(0, 0.01 * np.abs(clean).max(), x.size)
    assay = HG2Assay(x_data=Q_(x, 'M'), y_data=Q_(y, 'au'), h0=Q_(HG2_TRUE['h0'], 'M'))
    narrowed = {k: (Q_(lo, '1/M'), Q_(hi, '1/M')) for k, (lo, hi) in _HG2_BOUNDS.items()}
    bounds = {**assay.get_default_bounds(), **narrowed}
    assay.get_default_bounds = lambda: dict(bounds)
    return assay


def _reference(assay, errors: ErrorModel = ErrorModel()) -> dict[str, tuple[float, float]]:
    return reference_intervals(assay, assay.y_data.magnitude[np.newaxis, :], errors, 0, 'test')


def _decades_apart(a: tuple[float, float], b: tuple[float, float]) -> float:
    return float(max(abs(np.log10(a[0] / b[0])), abs(np.log10(a[1] / b[1]))))


def test_data_with_one_binding_step_give_the_second_constant_no_lower_limit():
    """On a titration without a second step, the second constant's interval is open below at its bound.

    The noise of this draw lets the profile close below the true zero at the
    95 % level, while the model without the second step is not rejected at
    ``SECOND_STEP_LEVEL``: a closed lower edge would claim a binding step the
    data do not show.
    """
    low, _ = _reference(_stepwise(0.0, seed=1))['Ka_HG2']
    assert low == _HG2_BOUNDS['Ka_HG2'][0]


def test_a_second_step_the_data_show_keeps_its_lower_limit():
    """Where the second step is real, the pretest rejects the one-step model and the interval stays closed."""
    truth = HG2_TRUE['Ka_HG2']
    low, high = _reference(_stepwise(truth, seed=1))['Ka_HG2']
    assert _HG2_BOUNDS['Ka_HG2'][0] < low <= truth <= high


def test_the_fitted_parameters_are_read_where_the_optimum_lies():
    """A best fit a fraction of a microdecade beside the Ka where a coefficient reaches its bound is read on its side.

    On this host-to-dye titration the signal offset reaches its lower bound
    0.6 microdecades from the optimum, on the side the optimum lies on, so the
    best fit holds it there and the count of fitted parameters is one lower
    than just across the step. The engine's interval is the same definition
    computed by other machinery.
    """
    case = _CASES['DBA_HtoD,K=1000,n=8,noise=0.01']
    data = dataset(case, 1)
    signals = data.signals.mean(axis=0)[np.newaxis, :]
    projection = Projection(data.assay, data.assay.get_default_bounds(), signals=signals)
    engine = projection.interval('Ka_dye', projection.fit())
    found = reference_intervals(data.assay, signals, case.error_model, 1, case.id)['Ka_dye']
    assert _decades_apart(found, (engine.low, engine.high)) <= AGREEMENT_DECADES


def test_a_stretch_the_stepped_cut_off_accepts_between_two_rejected_nodes_is_found():
    """Where the fitted rank changes inside a grid cell, the stretch the higher cut-off accepts there is in the interval.

    On this 2:1 titration the profile of the first constant gives up a signal
    coefficient over about a tenth of a decade below the closed stretch, and
    the stepped cut-off accepts it; no node of the reference's grid lies in it.
    The engine's own test at one Ka inside it is the independent reading.
    """
    case = _CASES['DBA_H2G,K=10,n=12,noise=0.01']
    data = dataset(case, 1)
    signals = data.signals.mean(axis=0)[np.newaxis, :]
    projection = Projection(data.assay, data.assay.get_default_bounds(), signals=signals)
    fit = projection.fit()
    inside = 3.5e6
    _, value, fitted = projection.profile_point('Ka_HG', inside, inner_per_decade=64)
    assert value <= projection.cut_off(fit)(fitted), 'the engine must accept the Ka this test is built on'
    low, _ = reference_intervals(data.assay, signals, case.error_model, 1, case.id)['Ka_HG']
    assert low <= inside


def test_an_input_known_to_a_vanishing_sigma_gives_the_interval_of_exact_inputs():
    """As the stated sigma of an input goes to zero, the interval with that input free is the conditional one.

    The edges are root-found after the effective degrees of freedom are read
    off the Jacobian, so this also pins that the whitening of every later
    solve is still the point weights' (none here) and not a matrix of that
    computation.
    """
    case = _CASES['GDA,K=10,n=8,noise=0.01']
    data = dataset(case, 0)
    signals = data.signals.mean(axis=0)[np.newaxis, :]
    exact = reference_intervals(data.assay, signals, ErrorModel(), 0, case.id)['Ka_guest']
    stated = ErrorModel(specs={'h0': InputSpec.sigma_pct(1e-4)})
    free = reference_intervals(data.assay, signals, stated, 0, case.id)['Ka_guest']
    assert _decades_apart(free, exact) <= 1e-3
