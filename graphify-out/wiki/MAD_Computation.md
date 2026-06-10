# MAD Computation

> 9 nodes · cohesion 0.31

## Key Concepts

- **compute_mad()** (11 connections) — `core/optimizer/filters.py`
- **TestComputeMad** (6 connections) — `tests/unit/test_optimizer.py`
- **.test_asymmetric_data()** (4 connections) — `tests/unit/test_optimizer.py`
- **.test_known_mad_value()** (4 connections) — `tests/unit/test_optimizer.py`
- **.test_single_result_is_zero()** (3 connections) — `tests/unit/test_optimizer.py`
- **.test_empty_returns_none()** (2 connections) — `tests/unit/test_optimizer.py`
- **Compute median absolute deviation of parameters.      MAD is a robust measure of** (1 connections) — `core/optimizer/filters.py`
- **MAD of [1, 2, 3]: median=2, |deviations|=[1, 0, 1], MAD=1.** (1 connections) — `tests/unit/test_optimizer.py`
- **MAD of [1, 2, 3, 100]: median=2.5, |dev|=[1.5, 0.5, 0.5, 97.5], MAD=1.0.** (1 connections) — `tests/unit/test_optimizer.py`

## Relationships

- [[Fit Aggregation]] (4 shared connections)
- [[Fit Filtering]] (3 shared connections)
- [[Linear Regression Fit]] (2 shared connections)
- [[Fit Metrics RMSE/R²]] (1 shared connections)
- [[Dye-Alone Calibration & Scaling]] (1 shared connections)

## Source Files

- `core/optimizer/filters.py`
- `tests/unit/test_optimizer.py`

## Audit Trail

- EXTRACTED: 32 (97%)
- INFERRED: 1 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*