"""Mean / STDEV aggregation over the accepted-fit pool.

Companion to the median/MAD tests in ``test_optimizer.py``. These pin the
classical (non-robust) summaries shown in the Fitted Parameters table,
computed directly from ``FitResult.parameter_samples`` — no re-fitting.

Expected values are hand-derived (not recomputed with the code's own formula).
"""

import numpy as np
import pytest

from core.optimizer.filters import compute_mean_params, compute_std_params


def test_mean_is_arithmetic_average():
    samples = {'Ka': np.array([1.0, 2.0, 3.0]), 'I0': np.array([10.0, 20.0])}
    means = compute_mean_params(samples)
    assert means['Ka'] == pytest.approx(2.0)  # (1+2+3)/3
    assert means['I0'] == pytest.approx(15.0)  # (10+20)/2


def test_std_is_sample_stdev():
    # [1,2,3]: mean 2, squared devs 1+0+1=2, /(3-1)=1, sqrt=1.
    stds = compute_std_params({'Ka': np.array([1.0, 2.0, 3.0])})
    assert stds['Ka'] == pytest.approx(1.0)


def test_std_single_sample_is_zero():
    # One accepted fit -> spread cannot be estimated; report 0.0 (as MAD does).
    stds = compute_std_params({'Ka': np.array([7.5])})
    assert stds['Ka'] == 0.0


def test_mean_and_std_pulled_by_outlier():
    """A skewed pool: mean and STDEV are dragged toward the outlier, whereas the
    robust median (2.5) and MAD (1.0, asserted in test_optimizer) stay put — the
    reason both pairs are shown side by side."""
    pool = np.array([1.0, 2.0, 3.0, 100.0])
    mean = compute_mean_params({'Ka': pool})['Ka']
    std = compute_std_params({'Ka': pool})['Ka']

    # Hand-computed: mean = 106/4 = 26.5.
    assert mean == pytest.approx(26.5)
    # Hand-computed sample STDEV: devs from 26.5 are -25.5,-24.5,-23.5,73.5;
    # squares sum to 7205; /(4-1)=2401.667; sqrt = 49.0068.
    assert std == pytest.approx(49.0068, abs=1e-3)
    # Classical pair sits far from the robust pair (median 2.5, MAD 1.0).
    assert mean > 25
    assert std > 40


def test_multiple_keys_independent():
    means = compute_mean_params({'a': np.array([0.0, 4.0]), 'b': np.array([5.0, 5.0])})
    stds = compute_std_params({'a': np.array([0.0, 4.0]), 'b': np.array([5.0, 5.0])})
    assert means == {'a': pytest.approx(2.0), 'b': pytest.approx(5.0)}
    assert stds['a'] == pytest.approx(np.sqrt(8.0))  # devs ±2 -> 8/(2-1)=8
    assert stds['b'] == 0.0  # identical values -> no spread
