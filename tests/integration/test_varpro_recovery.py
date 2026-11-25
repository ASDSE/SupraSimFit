"""Variable projection engine — recovery and coverage on seeded synthetic data.

Slow checks of the two claims a fit engine has to make good on: the fitted
binding constants of the stepwise 1:2 and 2:1 models land near the truth on
noisy data across the default Ka box, and the 95 % profile interval of a
one-Ka model covers the true Ka at about the stated rate on one fixed set of
seeds. The coverage rates themselves, for every assay and both stepwise
models, are measured by the validation package (``conditional-coverage``,
``two-ka-weak``).
"""

import numpy as np
import pytest

from core.assays.h2g import H2GAssay
from core.assays.hg2 import HG2Assay
from core.assays.ida import IDAAssay
from core.assays.registry import ASSAY_REGISTRY, AssayType
from core.pipeline.varpro import Projection
from core.units import Q_
from tests.conftest import (
    H2G_RECOVERY_BOUNDS,
    H2G_TRUE,
    HG2_RECOVERY_BOUNDS,
    HG2_TRUE,
    IDA_TRUE,
    _make_h2g_data,
    _make_hg2_data,
    _make_ida_data,
)


def _homoscedastic(y: np.ndarray, frac: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return y + rng.normal(0.0, frac * np.ptp(y), y.size)


@pytest.mark.parametrize(
    'assay_cls, true, bounds, make',
    [
        (HG2Assay, HG2_TRUE, HG2_RECOVERY_BOUNDS, _make_hg2_data),
        (H2GAssay, H2G_TRUE, H2G_RECOVERY_BOUNDS, _make_h2g_data),
    ],
    ids=['HG2', 'H2G'],
)
def test_stepwise_constants_are_recovered_from_noisy_data_across_the_default_box(assay_cls, true, bounds, make):
    # Eight datasets at 30 points and 1 % noise: every stepwise constant within
    # half a decade of the truth on each, and within 0.35 decades in the median.
    errors = []
    for seed in range(8):
        x, y = make(true, 30, 0.01, np.random.default_rng(seed))
        projection = Projection(assay_cls(x_data=Q_(x, 'M'), y_data=Q_(y, 'au'), h0=Q_(true['h0'], 'M')), bounds)
        fit = projection.fit()
        errors.append([abs(np.log10(fit.ka[k]) - np.log10(true[k])) for k in projection.ka_keys])
    errors = np.array(errors)
    assert (np.median(errors, axis=0) <= 0.35).all(), errors
    assert (errors <= 0.5).all(), errors


def test_one_ka_intervals_cover_the_true_ka_at_about_the_stated_rate():
    # 100 IDA datasets, 20 points, 2 % homoscedastic noise: the 95 % interval
    # holds the truth in 89 to 99 of them (binomial band about 0.95).
    x, clean = _make_ida_data(IDA_TRUE, 20)
    conditions = dict(Ka_dye=Q_(IDA_TRUE['Ka_dye'], '1/M'), h0=Q_(IDA_TRUE['h0'], 'M'), d0=Q_(IDA_TRUE['d0'], 'M'))
    covered = 0
    for seed in range(100):
        assay = IDAAssay(x_data=Q_(x, 'M'), y_data=Q_(_homoscedastic(clean, 0.02, seed), 'au'), **conditions)
        projection = Projection(assay, ASSAY_REGISTRY[AssayType.IDA].default_bounds)
        interval = projection.interval('Ka_guest', projection.fit())
        covered += interval.low <= IDA_TRUE['Ka_guest'] <= interval.high
    assert 89 <= covered <= 99, covered
