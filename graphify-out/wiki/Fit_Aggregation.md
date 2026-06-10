# Fit Aggregation

> 17 nodes · cohesion 0.20

## Key Concepts

- **_make_attempt()** (19 connections) — `tests/unit/test_optimizer.py`
- **aggregate_fits()** (13 connections) — `core/optimizer/filters.py`
- **compute_median_params()** (11 connections) — `core/optimizer/filters.py`
- **TestAggregateFits** (7 connections) — `tests/unit/test_optimizer.py`
- **TestComputeMedianParams** (6 connections) — `tests/unit/test_optimizer.py`
- **.test_all_filtered_out()** (4 connections) — `tests/unit/test_optimizer.py`
- **.test_multiple_passing()** (3 connections) — `tests/unit/test_optimizer.py`
- **.test_single_passing_fit()** (3 connections) — `tests/unit/test_optimizer.py`
- **.test_even_count()** (3 connections) — `tests/unit/test_optimizer.py`
- **.test_odd_count()** (3 connections) — `tests/unit/test_optimizer.py`
- **.test_single_result()** (3 connections) — `tests/unit/test_optimizer.py`
- **.test_empty_input()** (2 connections) — `tests/unit/test_optimizer.py`
- **.test_empty_returns_none()** (2 connections) — `tests/unit/test_optimizer.py`
- **Filter and aggregate fit results to median parameters.      Parameters     -----** (1 connections) — `core/optimizer/filters.py`
- **Compute median parameters from filtered fit attempts.      Parameters     ------** (1 connections) — `core/optimizer/filters.py`
- **Create a FitAttempt with sensible defaults.** (1 connections) — `tests/unit/test_optimizer.py`
- **All results have low R² → none pass filtering.** (1 connections) — `tests/unit/test_optimizer.py`

## Relationships

- [[Fit Filtering]] (10 shared connections)
- [[Linear Regression Fit]] (5 shared connections)
- [[MAD Computation]] (4 shared connections)
- [[RMSE Filtering]] (4 shared connections)
- [[Dye-Alone Calibration & Scaling]] (3 shared connections)
- [[Fit Metrics RMSE/R²]] (2 shared connections)
- [[Robust Aggregation & Units]] (1 shared connections)

## Source Files

- `core/optimizer/filters.py`
- `tests/unit/test_optimizer.py`

## Audit Trail

- EXTRACTED: 81 (98%)
- INFERRED: 2 (2%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*