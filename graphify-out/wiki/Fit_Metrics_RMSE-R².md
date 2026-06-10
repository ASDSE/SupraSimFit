# Fit Metrics RMSE/R²

> 12 nodes · cohesion 0.21

## Key Concepts

- **calculate_fit_metrics()** (12 connections) — `core/optimizer/filters.py`
- **TestCalculateFitMetrics** (8 connections) — `tests/unit/test_optimizer.py`
- **ndarray** (5 connections) — `core/optimizer/filters.py`
- **.test_constant_y_observed()** (3 connections) — `tests/unit/test_optimizer.py`
- **.test_known_values()** (3 connections) — `tests/unit/test_optimizer.py`
- **.test_nan_prediction_propagates_nan()** (3 connections) — `tests/unit/test_optimizer.py`
- **.test_perfect_fit()** (2 connections) — `tests/unit/test_optimizer.py`
- **calculate_fit_metrics** (1 connections) — `core/optimizer/filters.py`
- **Calculate RMSE and R² for a fit.      Parameters     ----------     y_observed :** (1 connections) — `core/optimizer/filters.py`
- **When all y_observed are identical, ss_tot=0 → R²=0.** (1 connections) — `tests/unit/test_optimizer.py`
- **Hand-computed RMSE and R² for simple data.** (1 connections) — `tests/unit/test_optimizer.py`
- **A NaN anywhere in y_predicted (failed model eval) must yield NaN         metrics** (1 connections) — `tests/unit/test_optimizer.py`

## Relationships

- [[Dye-Alone Calibration & Scaling]] (5 shared connections)
- [[Fit Aggregation]] (2 shared connections)
- [[Fit Filtering]] (2 shared connections)
- [[Linear Regression Fit]] (2 shared connections)
- [[MAD Computation]] (1 shared connections)
- [[README Reference Params]] (1 shared connections)

## Source Files

- `core/optimizer/filters.py`
- `tests/unit/test_optimizer.py`

## Audit Trail

- EXTRACTED: 39 (95%)
- INFERRED: 2 (5%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*