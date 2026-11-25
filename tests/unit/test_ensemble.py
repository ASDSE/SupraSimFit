"""Statistics of a set of values in a parameter's own scale and in log₁₀.

The replicate columns of a per-replicate fit report these, so what they mean
is pinned here directly.
"""

import numpy as np
import pytest

from core.optimizer import ensemble

# ---------------------------------------------------------------------------
# describe / describe_log10 (a parameter's own scale vs log space)
# ---------------------------------------------------------------------------


class TestDescribe:
    def test_every_statistic_is_hand_computable(self):
        """All eight keys, against arithmetic done by hand rather than by numpy.

        [1, 2, 3]: median 2; |dev| = [1, 0, 1] → MAD 1; mean 2; sample SD
        (ddof=1) 1; min 1; max 3. The percentiles interpolate linearly over
        index = q/100 × (n−1): p16 at index 0.32 → 1.32, p84 at 1.68 → 2.68.
        """
        d = ensemble.describe(np.array([1.0, 2.0, 3.0]))
        assert d['median'] == pytest.approx(2.0)
        assert d['mad'] == pytest.approx(1.0)
        assert d['mean'] == pytest.approx(2.0)
        assert d['std'] == pytest.approx(1.0)
        assert d['min'] == pytest.approx(1.0)
        assert d['max'] == pytest.approx(3.0)
        assert d['p16'] == pytest.approx(1.32)
        assert d['p84'] == pytest.approx(2.68)

    def test_single_sample_has_zero_spread(self):
        """One sample → no dispersion defined; report 0, never NaN."""
        d = ensemble.describe(np.array([7.0]))
        assert d['median'] == pytest.approx(7.0)
        assert d['mean'] == pytest.approx(7.0)
        assert d['mad'] == 0.0
        assert d['std'] == 0.0
        assert d['min'] == d['max'] == pytest.approx(7.0)

    def test_describe_log10_transforms_first_not_log_of_spread(self):
        """log₁₀ stats must come from log₁₀(pool). The centre commutes (median),
        but the spread does NOT — log of a Ka MAD/std is wrong."""
        s = np.array([10.0, 100.0, 1000.0, 50.0, 500.0])  # odd length: exact median
        d = ensemble.describe(s)
        dl = ensemble.describe_log10(s)

        # transform-first == summarising the log-transformed pool (independent path)
        expected = ensemble.describe(np.log10(s))
        for k in dl:
            assert dl[k] == pytest.approx(expected[k])

        # median commutes with log; MAD and mean do not
        assert dl['median'] == pytest.approx(np.log10(d['median']))
        assert dl['mad'] != pytest.approx(np.log10(d['mad']))
        assert dl['mean'] != pytest.approx(np.log10(d['mean']))  # Jensen bias

    def test_describe_log10_rejects_non_positive(self):
        with pytest.raises(ValueError, match='positive'):
            ensemble.describe_log10(np.array([1.0, -2.0, 3.0]))
        with pytest.raises(ValueError):
            ensemble.describe_log10(np.array([]))
