# Initial Guess Generation

> 13 nodes · cohesion 0.23

## Key Concepts

- **generate_initial_guesses()** (13 connections) — `core/optimizer/multistart.py`
- **TestGenerateInitialGuesses** (9 connections) — `tests/unit/test_optimizer.py`
- **multistart.py** (6 connections) — `core/optimizer/multistart.py`
- **.test_log_scale_non_positive_lower_falls_back_to_linear()** (3 connections) — `tests/unit/test_optimizer.py`
- **.test_empty_bounds_returns_zero_length_arrays()** (2 connections) — `tests/unit/test_optimizer.py`
- **.test_equal_bounds_gives_fixed_value()** (2 connections) — `tests/unit/test_optimizer.py`
- **.test_guesses_within_bounds()** (2 connections) — `tests/unit/test_optimizer.py`
- **.test_log_scale_positive_bounds()** (2 connections) — `tests/unit/test_optimizer.py`
- **.test_single_trial()** (2 connections) — `tests/unit/test_optimizer.py`
- **.test_zero_trials_returns_empty()** (2 connections) — `tests/unit/test_optimizer.py`
- **Multi-start optimization for nonlinear fitting.  This module provides a robust m** (1 connections) — `core/optimizer/multistart.py`
- **Generate random initial parameter guesses within bounds.      Parameters     ---** (1 connections) — `core/optimizer/multistart.py`
- **When lower bound is 0, log-scale falls back to linear (no log10(0) crash).** (1 connections) — `tests/unit/test_optimizer.py`

## Relationships

- [[Dye-Alone Calibration & Scaling]] (3 shared connections)
- [[Multistart Optimizer]] (3 shared connections)
- [[Fit Filtering]] (2 shared connections)
- [[Linear Regression Fit]] (2 shared connections)

## Source Files

- `core/optimizer/multistart.py`
- `tests/unit/test_optimizer.py`

## Audit Trail

- EXTRACTED: 45 (98%)
- INFERRED: 1 (2%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*