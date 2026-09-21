"""What a scored row says about an interval and about a joint region.

A coverage rate is a count of these two answers. Scoring a split interval on
its outer edges would count a Ka the fit rejects as covered, and reading a
joint region anywhere but off the surface the Identifiability tab draws would
let the tab go wrong while the check stayed green.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from core.pipeline.profile import JointRegion
from core.pipeline.varpro import KaInterval
from validation.score import _profile_accepts, interval_facts, region_excess


def interval(low: float, high: float, split: bool = False) -> KaInterval:
    """A closed interval of the given edges."""
    return KaInterval(low=low, high=high, open_low=False, open_high=False, level=0.95, dof=8, split=split)


def test_a_connected_interval_covers_what_lies_between_its_edges():
    """The plain case: the accepted Ka are one stretch, so the edges answer it."""
    facts = interval_facts(interval(1e5, 1e7), truth=1e6, estimate=2e6)
    assert facts['covers'] is True
    assert facts['split'] is False
    assert facts['width'] == 2.0
    assert interval_facts(interval(1e5, 1e7), truth=1e8, estimate=2e6)['covers'] is False


def test_a_truth_in_a_split_interval_s_rejected_gap_is_not_covered():
    """The edges of a split interval span Ka the fit rejects; counting them would inflate coverage."""
    rejected = interval_facts(interval(1e5, 1e7, split=True), 1e6, 2e6, accepts=lambda ka: ka > 5e6)
    accepted = interval_facts(interval(1e5, 1e7, split=True), 1e6, 2e6, accepts=lambda ka: ka < 5e6)
    assert rejected['covers'] is False
    assert accepted['covers'] is True
    assert rejected['split'] is True


def test_a_truth_outside_a_split_interval_stays_outside_it():
    """The gap test refines what the edges enclose; it cannot pull in a Ka they never reached."""
    facts = interval_facts(interval(1e5, 1e7, split=True), 1e9, 2e6, accepts=lambda ka: True)
    assert facts['covers'] is False


def test_the_profile_decides_between_its_nodes_and_not_only_on_them():
    """A Ka between two nodes is accepted when the line joining them stays under the threshold."""
    profile = SimpleNamespace(
        grid=np.array([1e4, 1e6, 1e8]),
        objective=np.array([10.0, 0.0, 10.0]),
        threshold=5.0,
    )
    accepts = _profile_accepts(profile)
    assert accepts(1e6) is True
    assert accepts(10**5.0) is True  # halfway in log Ka: the interpolated value is 5.0
    assert accepts(10**4.5) is False
    assert accepts(1e2) is False, 'a Ka past the grid is not something the profile accepted'


def test_a_ka_the_model_could_not_be_solved_at_is_not_accepted():
    """An infinite profile value is the model failing, which is no evidence that the Ka fits."""
    profile = SimpleNamespace(grid=np.array([1e4, 1e6]), objective=np.array([np.inf, 0.0]), threshold=5.0)
    assert _profile_accepts(profile)(10**5.0) is False


def region(threshold: float) -> JointRegion:
    """A region whose surface falls off from a ridge along the first axis."""
    x = np.geomspace(1e4, 1e8, 5)
    y = np.geomspace(1e4, 1e8, 5)
    r2 = np.array([[1.0 - abs(i - j) / 10 for j in range(5)] for i in range(5)])
    return JointRegion(
        ka_keys=('Ka_HG', 'Ka_HG2'), x=x, y=y, r2=r2, r2_threshold=threshold, level=0.95, best=(1e6, 1e6)
    )


def test_a_pair_is_read_off_the_surface_the_region_is_drawn_from():
    """The check has to answer the question the tab's region answers: residual over cut-off, cell by cell."""
    drawn = region(0.95)
    assert region_excess(drawn, (1e6, 1e6)) == 0.0
    assert region_excess(drawn, (1e8, 1e4)) == pytest.approx((4 / 10) / 0.05)
    # Halfway between two nodes in each direction, bilinearly.
    assert region_excess(drawn, (10**5.0, 10**5.0)) == 0.0


def test_a_cell_is_judged_against_its_own_cut_off():
    """Where a signal parameter is given up the cut-off steps down in R²; the same residual is then inside."""
    drawn = region(0.95)
    assert region_excess(drawn, (1e7, 1e6)) == pytest.approx(0.1 / 0.05)
    drawn.r2_cut[:] = 0.8
    assert region_excess(drawn, (1e7, 1e6)) == pytest.approx(0.1 / 0.2)


def test_a_pair_outside_the_region_s_box_is_outside_the_region():
    """The box is the two intervals clipped to the Ka bounds; the tab draws nothing past it."""
    drawn = region(0.95)
    assert np.isnan(region_excess(drawn, (1e9, 1e6)))
    assert np.isnan(region_excess(drawn, (1e6, 1e2)))


def test_a_cell_the_model_could_not_be_solved_in_is_outside_the_region():
    """The tab draws no contour through a hole in the surface, so neither may the check."""
    drawn = region(0.95)
    drawn.r2[2, 2] = np.nan
    assert np.isnan(region_excess(drawn, (1e6, 1e6)))
