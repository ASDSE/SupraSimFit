# Fit Filtering

> 14 nodes · cohesion 0.22

## Key Concepts

- **__init__.py** (15 connections) — `core/optimizer/__init__.py`
- **filters.py** (10 connections) — `core/optimizer/filters.py`
- **filter_by_r_squared()** (10 connections) — `core/optimizer/filters.py`
- **filter_fits()** (9 connections) — `core/optimizer/filters.py`
- **FitAttempt** (7 connections) — `core/optimizer/filters.py`
- **TestFilterByRSquared** (6 connections) — `tests/unit/test_optimizer.py`
- **.test_min_one_strict()** (3 connections) — `tests/unit/test_optimizer.py`
- **.test_min_zero_passes_all()** (3 connections) — `tests/unit/test_optimizer.py`
- **.test_nan_r_squared_filtered_out()** (3 connections) — `tests/unit/test_optimizer.py`
- **.test_empty_input()** (2 connections) — `tests/unit/test_optimizer.py`
- **Filtering and aggregation utilities for fit results.  This module provides funct** (1 connections) — `core/optimizer/filters.py`
- **Filter fit attempts by minimum R² value.      Parameters     ----------     resu** (1 connections) — `core/optimizer/filters.py`
- **Filter fit attempts by both RMSE and R² criteria.      Parameters     ----------** (1 connections) — `core/optimizer/filters.py`
- **Optimization utilities for fitting binding assay models.** (1 connections) — `core/optimizer/__init__.py`

## Relationships

- [[Fit Aggregation]] (10 shared connections)
- [[Dye-Alone Calibration & Scaling]] (6 shared connections)
- [[RMSE Filtering]] (4 shared connections)
- [[Linear Regression Fit]] (4 shared connections)
- [[MAD Computation]] (3 shared connections)
- [[Fit Metrics RMSE/R²]] (2 shared connections)
- [[Initial Guess Generation]] (2 shared connections)
- [[Multistart Optimizer]] (1 shared connections)

## Source Files

- `core/optimizer/__init__.py`
- `core/optimizer/filters.py`
- `tests/unit/test_optimizer.py`

## Audit Trail

- EXTRACTED: 70 (97%)
- INFERRED: 2 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*