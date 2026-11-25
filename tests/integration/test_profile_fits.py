"""Ka profiles — the checks that repeat whole fits or a dense brute force.

Two claims that cannot be made on one fit: the 95 % profile interval covers the
true Ka at about the stated rate over many noise draws and is about as wide as
its own threshold implies, and the profile of a two-constant model is at every
node the true minimum over the other constant, found here by a brute-force scan
that shares no code with the engine's refinement.
"""

import numpy as np
import pytest
from scipy.stats import f as f_dist

from core.assays.hg2 import HG2Assay
from core.assays.ida import IDAAssay
from core.data_processing.measurement_set import MeasurementSet
from core.pipeline import varpro
from core.pipeline.fit_pipeline import FitConfig, _resolve_bounds
from core.pipeline.profile import fit_profile
from core.pipeline.varpro import Projection
from core.units import Q_
from tests.conftest import HG2_TRUE, IDA_TRUE, _make_hg2_data, _make_ida_data

_IDA_CONDITIONS = {
    'Ka_dye': Q_(IDA_TRUE['Ka_dye'], '1/M'),
    'h0': Q_(IDA_TRUE['h0'], 'M'),
    'd0': Q_(IDA_TRUE['d0'], 'M'),
}
_HG2_CONDITIONS = {'h0': Q_(HG2_TRUE['h0'], 'M')}
# A Ka box of four decades around the HG2 truths keeps the two-Ka search grid
# at 17 x 17 nodes, so the brute force below has a short axis to cover.
_HG2_BOX = {'Ka_HG': (Q_(1e4, '1/M'), Q_(1e8, '1/M')), 'Ka_HG2': (Q_(1e4, '1/M'), Q_(1e8, '1/M'))}
_HG2_AVERAGE = FitConfig(per_replica=False, custom_bounds=_HG2_BOX)


def _homoscedastic(y: np.ndarray, frac: float, seed: int) -> np.ndarray:
    return y + np.random.default_rng(seed).normal(0.0, frac * np.abs(y).max(), y.size)


def _single(x, y) -> MeasurementSet:
    """One-replicate measurement set from bare arrays."""
    return MeasurementSet(concentrations=x, signals=np.asarray(y).reshape(1, -1), replica_ids=('r0',))


def _projection(ms: MeasurementSet, assay_cls, conditions, config: FitConfig) -> Projection:
    """The engine's projection of the averaged signal under *config*'s bounds."""
    assay = ms.to_assay(assay_cls, conditions=conditions, use_average=True)
    return Projection(assay, _resolve_bounds(assay, config.custom_bounds))


def test_interval_covers_the_true_ka_at_about_the_stated_rate_and_is_no_wider_than_that_takes():
    # Homoscedastic Gaussian noise meets the F test's assumptions, so the 95 %
    # interval should cover the truth in close to 95 % of noise draws. 40 draws
    # leave sampling slack; 85 % still catches an interval that is too narrow.
    # Ka bounds a few decades either side of the truth keep the grid short.
    #
    # Coverage alone cannot catch the opposite failure: an interval stretched to
    # the Ka bounds covers every draw. So each interval is measured against the
    # width the same threshold implies through the curvature of the profile,
    # which here is close to quadratic in log Ka. For SSR ≈ SSR_min + H·t²/2 in
    # t = log10(Ka), the cut sits sqrt(2·SSR_min·F/((n - p)·H)) either side of
    # the best fit -- a route to the width that uses no root finding.
    x, y = _make_ida_data(IDA_TRUE, n_points=12)
    bounds = {'Ka_guest': (Q_(1e5, '1/M'), Q_(1e8, '1/M'))}
    config = FitConfig(per_replica=False, custom_bounds=bounds)
    step = 0.02  # decades of Ka, for the second difference
    n_seeds = 40
    covered = 0
    width_ratios = []
    for seed in range(n_seeds):
        ms = _single(x, _homoscedastic(y, 0.02, seed))
        profile = fit_profile(ms, IDAAssay, _IDA_CONDITIONS, config).profiles['Ka_guest']
        interval = profile.interval
        covered += interval.low <= IDA_TRUE['Ka_guest'] <= interval.high

        projection = _projection(ms, IDAAssay, _IDA_CONDITIONS, config)
        t = np.log10(profile.best_ka)
        ssr = [float(projection.row_ssr({'Ka_guest': 10.0 ** (t + d * step)})[0]) for d in (-1, 0, 1)]
        curvature = (ssr[0] - 2.0 * ssr[1] + ssr[2]) / step**2
        dof = profile.n_points - profile.n_params
        half = np.sqrt(2.0 * ssr[1] * f_dist.ppf(interval.level, 1, dof) / (dof * curvature))
        width_ratios.append(np.log10(interval.high / interval.low) / (2.0 * half))

    median_ratio = float(np.median(width_ratios))
    print(
        f'95% interval coverage of the true Ka: {covered}/{n_seeds}; median width / curvature width: {median_ratio:.3f}'
    )
    assert covered / n_seeds >= 0.85
    assert 0.8 <= median_ratio <= 1.25


def test_two_ka_profile_nodes_equal_a_brute_force_minimum_over_the_other_ka():
    # Each curve is the objective minimised over the other Ka. At three of its
    # search-grid nodes per curve the minimum is found again by brute force: a
    # 16-per-decade scan of the other axis, then 1601 points across the two
    # cells around its best node. The scan is dense enough when the residual at
    # the neighbours of its best point is within 1e-7 of it, so the true
    # minimum between them is closer still. The engine's refinement is neither
    # scan, so agreement to 1e-6 is not the same code twice.
    x, y = _make_hg2_data(HG2_TRUE, n_points=10)
    ms = _single(x, _homoscedastic(y, 0.02, 5))
    profiles = fit_profile(ms, HG2Assay, _HG2_CONDITIONS, _HG2_AVERAGE)
    projection = _projection(ms, HG2Assay, _HG2_CONDITIONS, _HG2_AVERAGE)
    ss_tot = projection.ss_tot[0]
    coarse = np.geomspace(1e4, 1e8, 65)

    assert profiles.region is not None
    for key, other in (('Ka_HG', 'Ka_HG2'), ('Ka_HG2', 'Ka_HG')):
        profile = profiles.profiles[key]
        assert profile.replica_r2 is None
        nodes = varpro._ka_grid(1e4, 1e8, varpro._SEARCH_PER_DECADE)
        assert np.isin(nodes, profile.grid).all()
        for ka in nodes[[3, 8, 13]]:
            drawn = (1.0 - profile.r2[np.flatnonzero(profile.grid == ka)[0]]) * ss_tot
            scan = np.array([projection.row_ssr({key: ka, other: k})[0] for k in coarse])
            i = int(np.argmin(scan))
            fine = np.geomspace(coarse[max(i - 1, 0)], coarse[min(i + 1, coarse.size - 1)], 1601)
            fine_ssr = np.array([projection.row_ssr({key: ka, other: k})[0] for k in fine])
            j = int(np.argmin(fine_ssr))
            if 0 < j < fine.size - 1:
                assert fine_ssr[[j - 1, j + 1]].max() <= fine_ssr[j] * (1.0 + 1e-7)
            else:
                assert fine[j] in (1e4, 1e8)  # the minimum over the other Ka sits on its bound
            assert drawn == pytest.approx(fine_ssr[j], rel=1e-6)
