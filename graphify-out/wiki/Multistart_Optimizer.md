# Multistart Optimizer

> 18 nodes · cohesion 0.15

## Key Concepts

- **multistart_minimize()** (18 connections) — `core/optimizer/multistart.py`
- **TestMultistartMinimize** (10 connections) — `tests/unit/test_optimizer.py`
- **multistart_minimize** (6 connections) — `core/optimizer/multistart.py`
- **ndarray** (3 connections) — `core/optimizer/multistart.py`
- **.test_all_attempts_fail_returns_empty()** (3 connections) — `tests/unit/test_optimizer.py`
- **.test_compute_metrics_callback()** (3 connections) — `tests/unit/test_optimizer.py`
- **.test_custom_initial_guesses()** (3 connections) — `tests/unit/test_optimizer.py`
- **.test_simple_quadratic()** (3 connections) — `tests/unit/test_optimizer.py`
- **.test_without_compute_metrics_uses_cost_fallback()** (3 connections) — `tests/unit/test_optimizer.py`
- **generate_initial_guesses** (2 connections) — `core/optimizer/multistart.py`
- **ParamScaler** (2 connections) — `core/optimizer/multistart.py`
- **.test_results_sorted_by_cost()** (2 connections) — `tests/unit/test_optimizer.py`
- **Run L-BFGS-B optimizer from multiple starting points.      Parameters     ------** (1 connections) — `core/optimizer/multistart.py`
- **Minimizes f(x) = (x-3)^2 with bounds [0, 10].** (1 connections) — `tests/unit/test_optimizer.py`
- **Provided initial_guesses are used instead of random generation.** (1 connections) — `tests/unit/test_optimizer.py`
- **compute_metrics populates rmse and r_squared fields.** (1 connections) — `tests/unit/test_optimizer.py`
- **Objective that always raises returns empty results.** (1 connections) — `tests/unit/test_optimizer.py`
- **Without compute_metrics, rmse = sqrt(cost) and r_squared = NaN.** (1 connections) — `tests/unit/test_optimizer.py`

## Relationships

- [[Dye-Alone Calibration & Scaling]] (8 shared connections)
- [[Initial Guess Generation]] (3 shared connections)
- [[Linear Regression Fit]] (2 shared connections)
- [[Parameter Scaling]] (2 shared connections)
- [[Robust Aggregation & Units]] (1 shared connections)
- [[README Reference Params]] (1 shared connections)
- [[Fit Filtering]] (1 shared connections)

## Source Files

- `core/optimizer/multistart.py`
- `tests/unit/test_optimizer.py`

## Audit Trail

- EXTRACTED: 57 (89%)
- INFERRED: 7 (11%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*