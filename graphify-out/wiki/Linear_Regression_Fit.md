# Linear Regression Fit

> 13 nodes · cohesion 0.18

## Key Concepts

- **test_optimizer.py** (21 connections) — `tests/unit/test_optimizer.py`
- **linear_regression()** (9 connections) — `core/optimizer/linear_fit.py`
- **TestLinearRegression** (5 connections) — `tests/unit/test_optimizer.py`
- **.fit_linear()** (3 connections) — `core/assays/dye_alone.py`
- **linear_fit.py** (3 connections) — `core/optimizer/linear_fit.py`
- **.test_fewer_than_2_points_raises()** (2 connections) — `tests/unit/test_optimizer.py`
- **.test_perfect_fit()** (2 connections) — `tests/unit/test_optimizer.py`
- **Fit linear model using simple linear regression.          Returns         ------** (1 connections) — `core/assays/dye_alone.py`
- **ndarray** (1 connections) — `core/optimizer/linear_fit.py`
- **Linear fitting for dye-alone calibration.** (1 connections) — `core/optimizer/linear_fit.py`
- **Perform simple linear regression.      Parameters     ----------     x : np.ndar** (1 connections) — `core/optimizer/linear_fit.py`
- **P5: Optimizer boundary tests.  Unit tests for edge cases and boundary conditions** (1 connections) — `tests/unit/test_optimizer.py`
- **Edge cases for the linear regression helper.** (1 connections) — `tests/unit/test_optimizer.py`

## Relationships

- [[Fit Aggregation]] (5 shared connections)
- [[Fit Filtering]] (4 shared connections)
- [[Dye-Alone Calibration & Scaling]] (3 shared connections)
- [[RMSE Filtering]] (2 shared connections)
- [[MAD Computation]] (2 shared connections)
- [[Fit Metrics RMSE/R²]] (2 shared connections)
- [[Initial Guess Generation]] (2 shared connections)
- [[Multistart Optimizer]] (2 shared connections)
- [[Assay Base & Registry Metadata]] (1 shared connections)

## Source Files

- `core/assays/dye_alone.py`
- `core/optimizer/linear_fit.py`
- `tests/unit/test_optimizer.py`

## Audit Trail

- EXTRACTED: 50 (98%)
- INFERRED: 1 (2%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*