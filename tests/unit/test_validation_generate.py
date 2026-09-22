"""A row's data are fixed by its (scenario, seed) and describe what the scenario says.

Every rate the package reports rests on these datasets. If the same key gave
different data on a second run, no stored row could be checked; if the clean
signal were not the model at the stated truth, or the noise not the stated
size, a coverage rate would describe a titration nobody asked for.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from core.pipeline.inputs import TITRANT
from validation.generate import dataset
from validation.scenarios import Scenario, SharedEntry, SpecEntry, stated_specs

ROOT = Path(__file__).resolve().parents[2]

CASE = Scenario(assay='IDA', regime=10.0, n_points=12, noise=0.01)


def fingerprint(data) -> str:
    """A hash of everything a fit sees, so two datasets can be compared across processes."""
    digest = hashlib.sha256()
    for array in (data.x, data.clean, data.signals, data.entered_x):
        digest.update(np.asarray(array, dtype=float).tobytes())
    for key in sorted(data.truth):
        digest.update(f'{key}={data.truth[key]!r}'.encode())
    return digest.hexdigest()


def test_the_same_scenario_and_seed_give_the_same_data_in_a_fresh_process():
    """A stored row is only checkable if its dataset can be rebuilt from its key alone."""
    code = (
        'from validation.generate import dataset\n'
        'from tests.unit.test_validation_generate import CASE, fingerprint\n'
        'print(fingerprint(dataset(CASE, 7)))\n'
    )
    finished = subprocess.run(
        [sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True, env={'PYTHONPATH': str(ROOT)}
    )
    assert finished.returncode == 0, finished.stderr
    assert finished.stdout.strip() == fingerprint(dataset(CASE, 7))


def test_different_seeds_draw_different_titrations():
    """A scenario stands for a family; identical seeds would collapse it to one curve."""
    prints = {fingerprint(dataset(CASE, seed)) for seed in range(5)}
    assert len(prints) == 5


def test_the_clean_signal_is_the_model_at_the_truth_as_the_fit_reads_it():
    """The truth, the entered conditions and the noise-free signal have to describe one titration.

    The generator builds the signal by calling the model with named arguments;
    the fit evaluates it from a parameter vector in the registry's order. A
    parameter mapped to the wrong slot, an offset added twice or a dark dye not
    applied would part the two.
    """
    for scenario in (
        CASE,
        replace(CASE, assay='GDA', i0=True),
        replace(CASE, assay='DBA_HtoD', dark_free_dye=True, i0=False),
        replace(CASE, assay='DBA_HG2', regime=1.0, k_ratio=100.0),
    ):
        data = dataset(scenario, 3)
        params = np.array([data.truth[key] for key in data.assay.parameter_keys])
        modelled = data.assay.forward_model(params).magnitude
        assert np.allclose(modelled, data.clean, rtol=1e-10, atol=0), scenario.id


def test_a_planted_misfit_leaves_the_model_behind():
    """The sine is a departure from the model, so the clean signal must stop being a model curve."""
    scenario = replace(CASE, misfit_sine=0.02)
    data = dataset(scenario, 3)
    params = np.array([data.truth[key] for key in data.assay.parameter_keys])
    departure = data.clean - data.assay.forward_model(params).magnitude
    assert np.max(np.abs(departure)) == pytest.approx(0.02 * np.ptp(data.clean), rel=0.1)


def test_the_noise_comes_out_at_the_size_the_scenario_states():
    """Coverage is a claim about data of a stated noise size; a mis-scaled draw would void it."""
    scenario = replace(CASE, n_points=30, noise=0.02)
    # Each titration has its own signal range, so each seed's residuals are
    # measured against its own before they are pooled.
    standardised = []
    for seed in range(40):
        data = dataset(scenario, seed)
        standardised.append((data.signals[0] - data.clean) / np.ptp(data.clean))
    realised = np.concatenate(standardised).std(ddof=1)
    # 1200 draws: the sample standard deviation is within a few percent of the true one.
    assert realised == pytest.approx(0.02, rel=0.08)


def test_proportional_noise_scales_with_the_signal():
    """The proportional scenarios claim noise that grows with the reading, not a constant size."""
    data = dataset(replace(CASE, n_points=30, noise=0.02, proportional=True), 1)
    assert np.all(data.noise_sigma == pytest.approx(0.02 * np.abs(data.clean)))
    assert data.noise_sigma.max() > 3 * data.noise_sigma.min()


def test_inputs_entered_at_multiple_zero_are_the_true_ones():
    """The conditional checks rest on the inputs being exactly right; an offset would move the truth."""
    scenario = replace(CASE, specs=stated_specs('IDA'), entry_multiple=0.0)
    for seed in range(3):
        data = dataset(scenario, seed)
        assert data.entry_errors == {key: 0.0 for key in data.entry_errors}
        assert np.allclose(data.entered_x, data.x, rtol=0, atol=0)


def test_inputs_entered_at_multiple_one_carry_the_stated_spread():
    """The input-aware claim is that the interval holds when the entries are as wrong as stated."""
    scenario = replace(CASE, specs=(SpecEntry('h0', sigma=3.0), SpecEntry('Ka_dye', sigma=10.0)))
    errors = np.array([[dataset(scenario, seed).entry_errors[key] for key in ('h0', 'Ka_dye')] for seed in range(200)])
    # 200 draws: the sample standard deviation is within about 15 % of the true one.
    assert errors[:, 0].std(ddof=1) == pytest.approx(0.03, rel=0.2)
    assert errors[:, 1].std(ddof=1) == pytest.approx(0.10, rel=0.2)
    assert abs(errors.mean(axis=0)).max() < 0.02


def test_a_wronger_entry_is_the_same_draw_scaled():
    """The conflict power curve compares multiples; an independent draw at each would confound them."""
    stated = replace(CASE, specs=stated_specs('IDA'))
    once = dataset(stated, 7).entry_errors
    thrice = dataset(replace(stated, entry_multiple=3.0), 7).entry_errors
    assert set(once) == set(thrice)
    for key, error in once.items():
        assert thrice[key] == pytest.approx(3 * error)


def test_a_shared_stock_error_moves_two_inputs_together():
    """The strained robustness case is one error entered as two independent ones."""
    scenario = replace(
        CASE,
        specs=(SpecEntry('h0', sigma=3.0), SpecEntry('d0', sigma=3.0)),
        shared_entries=('h0', 'd0'),
    )
    for seed in range(4):
        errors = dataset(scenario, seed).entry_errors
        assert errors['h0'] == pytest.approx(errors['d0'])


def test_the_noise_does_not_change_when_the_entries_start_moving():
    """A scenario and its uncertain twin have to differ in the entries alone, not in the measurement."""
    exact = dataset(CASE, 5)
    stated = dataset(replace(CASE, specs=stated_specs('IDA')), 5)
    assert np.allclose(exact.signals, stated.signals, rtol=0, atol=0)
    assert not np.allclose(exact.entered_x, stated.entered_x, rtol=0, atol=0)


#: One dataset of a stored grid, spelled out: the first three true titrant
#: concentrations, the first three measured signals of its one replicate, and
#: every entry error. The rows of ``robustness-strained`` were computed from
#: exactly these numbers, so a draw that moved would make them rows of another
#: titration under the same key.
STRAINED = Scenario(
    assay='GDA',
    regime=0.1,
    n_points=12,
    noise=0.005,
    specs=stated_specs('GDA'),
    shared_entries=('h0', TITRANT),
)
STRAINED_X = [6.559714763398443e-05, 0.00013119429526796888, 0.00019679144290195332]
STRAINED_SIGNAL = [1443.927832757218, 3151.4126292557225, 4818.700461862025]
STRAINED_ERRORS = {
    'Ka_dye': 0.06708563317022377,
    'h0': -0.016929754596704375,
    'g0': 0.03700605307465419,
    TITRANT: -0.016929754596704375,
}


def test_a_stored_scenario_draws_the_titration_its_rows_were_computed_from():
    """A new field on a scenario must not touch a stream an existing grid already drew from."""
    assert STRAINED.id == 'GDA,K=0.1,n=12,noise=0.005,sig,shared(h0/titrant)'
    data = dataset(STRAINED, 3)
    assert data.x[:3].tolist() == STRAINED_X
    assert data.signals[0][:3].tolist() == STRAINED_SIGNAL
    assert data.entry_errors == STRAINED_ERRORS


def dba_complex(ka: float, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """``[HD]`` of 1:1 binding at totals *x* and *y*, from the mass-balance quadratic.

    ``Ka (x - c)(y - c) = c`` has one root below both totals; it is written as
    ``2 Ka x y / (b + sqrt(b² - 4 Ka² x y))`` with ``b = Ka (x + y) + 1`` so
    that no digits are lost to cancellation where the binding is strong.
    """
    b = ka * (x + y) + 1.0
    return 2 * ka * x * y / (b + np.sqrt(b**2 - 4 * ka**2 * x * y))


def dba_signal_at(data, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """The four-parameter signal of a dye-to-host titration at totals *x* (dye) and *y* (host)."""
    bound = dba_complex(data.truth['Ka_dye'], x, y)
    return data.truth['I0'] + data.truth['I_dye_free'] * (x - bound) + data.truth['I_dye_bound'] * bound


DILUTED = Scenario(assay='DBA_DtoH', regime=10.0, n_points=12, noise=0.005, dilution=(0.02, 0.2))


def test_a_diluted_titration_is_measured_on_the_totals_each_point_carries():
    """Every addition of titrant dilutes the host; a signal built on the entered total is another curve."""
    data = dataset(DILUTED, 2)
    stock = float(data.conditions['titrant_stock'].to('M').magnitude)
    assert 0.02 <= data.x[-1] / stock <= 0.2
    host = data.fixed_conc * (1.0 - data.x / stock)
    assert np.allclose(dba_signal_at(data, data.x, host), data.clean, rtol=1e-10, atol=0)
    # The same truth on constant totals is a different measurement, so the
    # agreement above is the dilution and not an identity.
    constant = dba_signal_at(data, data.x, np.full(data.x.shape, data.fixed_conc))
    assert np.max(np.abs(constant - data.clean)) > 10 * float(data.noise_sigma.max())


def test_a_diluted_titration_is_the_curve_the_assay_itself_draws():
    """The generator dilutes the totals and the assay dilutes them again from the stock it was handed.

    The two are separate pieces of arithmetic — one in the generator, one in
    ``BaseAssay.fixed_total`` — and the inputs of these scenarios are exact, so
    a total either of them dilutes and the other does not parts the curves.
    Both diluted totals and one carried by the stock are covered.
    """
    for scenario in (
        DILUTED,
        Scenario(assay='IDA', regime=10.0, n_points=12, noise=0.005, dilution=(0.02, 0.2)),
        Scenario(
            assay='IDA',
            regime=10.0,
            n_points=12,
            noise=0.005,
            dilution=(0.02, 0.2),
            stock_contains=('d0',),
        ),
        Scenario(assay='DBA_HG2', regime=1.0, n_points=12, noise=0.005, dilution=(0.02, 0.2)),
    ):
        data = dataset(scenario, 1)
        params = np.array([data.truth[key] for key in data.assay.parameter_keys])
        assert np.allclose(data.assay.forward_model(params).magnitude, data.clean, rtol=1e-10, atol=0), scenario.id


def test_the_undeclared_twin_is_the_same_titration():
    """The price of leaving the stock out is read off the measurement that was made with it."""
    ignored = dataset(replace(DILUTED, declare_stock=False), 2)
    declared = dataset(DILUTED, 2)
    assert np.allclose(ignored.x, declared.x, rtol=0, atol=0)
    assert np.allclose(ignored.signals, declared.signals, rtol=0, atol=0)
    assert 'titrant_stock' not in ignored.conditions
    assert 'titrant_stock' in declared.conditions


def test_the_entered_stock_carries_the_error_of_the_entered_titrant():
    """The series and the stock come from one solution, so the dilution itself is entered exactly."""
    scenario = replace(DILUTED, specs=(SpecEntry(TITRANT, sigma=10.0),))
    data = dataset(scenario, 4)
    stock = float(data.conditions['titrant_stock'].to('M').magnitude)
    assert data.entry_errors[TITRANT] != 0.0
    assert np.allclose(data.entered_x / stock, data.x / (stock * (1 + data.entry_errors[TITRANT])), rtol=1e-12)


SHARED = Scenario(
    assay='IDA',
    regime=10.0,
    n_points=12,
    noise=0.005,
    shared_sources=(SharedEntry('Stock', 4.0, ('h0', 'd0')),),
)


def test_one_shared_source_moves_every_input_it_loads_by_the_same_factor():
    """An input a source loads and nothing else moves carries that source's draw and nothing else."""
    errors = dataset(SHARED, 6).entry_errors
    assert set(errors) == {'h0', 'd0'}
    assert errors['h0'] == errors['d0']
    assert errors['h0'] != 0.0
    assert dataset(SHARED, 6).entry_errors == errors


def test_two_sources_on_one_input_multiply_there():
    """Sources are independent, so an input two of them load ends up at ``(1 + a)(1 + b) - 1``."""
    scenario = replace(
        SHARED,
        shared_sources=(
            SharedEntry('Balance', 4.0, ('h0', 'd0')),
            SharedEntry('Pipette', 3.0, ('d0', TITRANT)),
        ),
    )
    errors = dataset(scenario, 6).entry_errors
    assert 1 + errors['d0'] == pytest.approx((1 + errors['h0']) * (1 + errors[TITRANT]), rel=1e-12)
    assert errors['h0'] != errors[TITRANT]


def test_a_shared_source_comes_out_at_the_spread_it_states():
    """A source drawn at another width would measure the interval against an uncertainty nobody stated."""
    drawn = np.array([dataset(SHARED, seed).entry_errors['h0'] for seed in range(200)])
    # 200 draws: the sample standard deviation is within about 15 % of the true one.
    assert drawn.std(ddof=1) == pytest.approx(0.04, rel=0.2)
    assert abs(drawn.mean()) < 0.01


#: One dataset of the noise-law grid, spelled out: the first three signals of
#: its first replicate, the last signal of its last one, and the binding
#: constant they were drawn around. The truth and the noise come from the first
#: two children of the data stream, and the scale factor of a replicate from a
#: third that is only drawn from where a scenario states one — so these numbers
#: are what every stored row of every replicated grid was computed from. A
#: changed stream moves them by order one; the tolerance is there for the last
#: bits of a platform, since the release builds run on three of them.
NOISE_LAW_CASE = Scenario(assay='IDA', regime=10.0, n_points=12, noise=0.02, proportional=True, replicates=4)
NOISE_LAW_FIRST = [187610.22265797152, 130755.45764137199, 96888.4453711552]
NOISE_LAW_LAST = 48981.393649496604
NOISE_LAW_KA = 216209.1393077571


def test_a_replicated_dataset_draws_the_measurement_its_rows_were_computed_from():
    """A third stream for the replicate scale factors must leave the truth and the noise where they were."""
    data = dataset(NOISE_LAW_CASE, 7)
    assert data.signals[0, :3] == pytest.approx(NOISE_LAW_FIRST, rel=1e-9)
    assert data.signals[-1, -1] == pytest.approx(NOISE_LAW_LAST, rel=1e-9)
    assert data.truth['Ka_guest'] == pytest.approx(NOISE_LAW_KA, rel=1e-9)


def test_a_noise_floor_joins_the_proportional_part_in_quadrature():
    """The mixed cases claim a noise that neither vanishes with the signal nor stays flat along it."""
    data = dataset(replace(CASE, n_points=30, noise=0.02, proportional=True, noise_floor=0.005, replicates=2), 1)
    floor = 0.005 * np.ptp(data.clean)
    grows = 0.02 * np.abs(data.clean)
    assert np.all(data.noise_sigma == pytest.approx(np.hypot(floor, grows)))
    assert np.all(data.noise_sigma > grows), 'a floor has to add to the part that grows with the signal'
    # A scenario that states no floor keeps the noise it always had, to the
    # last bit: the rows of every proportional grid were computed from it.
    plain = dataset(replace(CASE, n_points=30, noise=0.02, proportional=True, replicates=2), 1)
    assert np.array_equal(plain.noise_sigma, 0.02 * np.abs(plain.clean))


def test_a_replicate_scale_factor_multiplies_one_replicate_and_is_not_noise():
    """A lamp or gain difference is an affine image of the whole curve, which no point's noise describes."""
    data = dataset(replace(CASE, noise=0.0, replicates=4, replicate_scale=0.03), 2)
    assert np.all(data.noise_sigma == 0.0)
    # Each replicate is one factor times the clean curve, so every point of it
    # gives the same ratio, and the four factors differ.
    factors = data.signals / data.clean
    assert np.allclose(factors, factors[:, :1], rtol=1e-12, atol=0)
    drawn = factors[:, 0]
    assert len(set(drawn.tolist())) == 4
    assert np.std(drawn) > 0.005
