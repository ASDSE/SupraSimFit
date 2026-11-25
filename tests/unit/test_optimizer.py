"""Fit quality and the dye-alone linear fit.

Both are measured against hand-computed values rather than against the
formulas the code uses.
"""

import numpy as np
import pytest

from core.optimizer.filters import calculate_fit_metrics
from core.optimizer.linear_fit import linear_regression

# ---------------------------------------------------------------------------
# calculate_fit_metrics
# ---------------------------------------------------------------------------


class TestCalculateFitMetrics:
    def test_perfect_fit(self):
        y = np.array([1.0, 2.0, 3.0, 4.0])
        rmse, r2 = calculate_fit_metrics(y, y)
        assert rmse == pytest.approx(0.0, abs=1e-15)
        assert r2 == pytest.approx(1.0)

    def test_constant_y_observed(self):
        """When all y_observed are identical, ss_tot=0 → R²=0."""
        y_obs = np.array([5.0, 5.0, 5.0])
        y_pred = np.array([4.0, 5.0, 6.0])
        rmse, r2 = calculate_fit_metrics(y_obs, y_pred)
        assert r2 == 0.0
        assert rmse > 0

    def test_known_values(self):
        """Hand-computed RMSE and R² for simple data.

        residuals = [-0.1, 0, +0.1] → ss_res = 0.02, RMSE = sqrt(0.02/3);
        mean(y_obs) = 2 → ss_tot = 2, so R² = 1 − 0.02/2 = 0.99.
        """
        rmse, r2 = calculate_fit_metrics(np.array([1.0, 2.0, 3.0]), np.array([1.1, 2.0, 2.9]))
        assert rmse == pytest.approx(0.081649658092772, rel=1e-9)
        assert r2 == pytest.approx(0.99, rel=1e-12)

    def test_nan_prediction_propagates_nan(self):
        """A NaN anywhere in y_predicted (a binding model with no solution there)
        must yield NaN metrics, never a finite number reported as a fit's quality."""
        y_obs = np.array([1.0, 2.0, 3.0])
        y_pred = np.array([1.0, np.nan, 3.0])
        rmse, r2 = calculate_fit_metrics(y_obs, y_pred)
        assert np.isnan(rmse)
        assert np.isnan(r2)


# ---------------------------------------------------------------------------
# linear_regression
# ---------------------------------------------------------------------------


class TestLinearRegression:
    """Edge cases for the linear regression helper."""

    def test_fewer_than_2_points_raises(self):
        with pytest.raises(ValueError):
            linear_regression(np.array([1.0]), np.array([2.0]))
        with pytest.raises(ValueError):
            linear_regression(np.array([]), np.array([]))

    def test_perfect_fit(self):
        x = np.array([0.0, 1.0, 2.0])
        y = np.array([3.0, 5.0, 7.0])  # slope=2, intercept=3
        slope, intercept, r2, rmse = linear_regression(x, y)

        assert slope == pytest.approx(2.0)
        assert intercept == pytest.approx(3.0)
        assert r2 == pytest.approx(1.0)
        assert rmse == pytest.approx(0.0, abs=1e-12)
