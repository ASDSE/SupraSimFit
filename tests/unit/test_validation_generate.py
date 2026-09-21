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

from validation.generate import dataset
from validation.scenarios import Scenario, SpecEntry, stated_specs

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
