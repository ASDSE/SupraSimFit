# Parameter Scaling

> 18 nodes · cohesion 0.14

## Key Concepts

- **test_scaling.py** (20 connections) — `tests/unit/test_scaling.py`
- **_make_ida_assay()** (8 connections) — `tests/unit/test_scaling.py`
- **_scale_factor()** (6 connections) — `core/optimizer/scaling.py`
- **.from_assay()** (3 connections) — `core/optimizer/scaling.py`
- **ida_assay()** (3 connections) — `tests/unit/test_scaling.py`
- **test_from_assay_rejects_zero_concentration()** (2 connections) — `tests/unit/test_scaling.py`
- **test_from_assay_rejects_zero_signal()** (2 connections) — `tests/unit/test_scaling.py`
- **test_multistart_returns_raw_params_when_scaled()** (2 connections) — `tests/unit/test_scaling.py`
- **test_scale_factor_known_units()** (2 connections) — `tests/unit/test_scaling.py`
- **Compute the affine rescaling factor for a parameter unit.      For each componen** (1 connections) — `core/optimizer/scaling.py`
- **Build a scaler from a ``BaseAssay`` instance.          Raises         ------** (1 connections) — `core/optimizer/scaling.py`
- **Unit** (1 connections) — `core/optimizer/scaling.py`
- **Tests for the parameter scaler (core.optimizer.scaling).  The scaler is an exact** (1 connections) — `tests/unit/test_scaling.py`
- **Build an IDAAssay around arbitrary (x, y) arrays using local truth conditions.** (1 connections) — `tests/unit/test_scaling.py`
- **test_bounds_preserve_ordering_and_width()** (1 connections) — `tests/unit/test_scaling.py`
- **test_from_assay_derives_scales()** (1 connections) — `tests/unit/test_scaling.py`
- **test_round_trip()** (1 connections) — `tests/unit/test_scaling.py`
- **test_wrap_objective_divides_by_loss_scale()** (1 connections) — `tests/unit/test_scaling.py`

## Relationships

- [[Dye-Alone Calibration & Scaling]] (5 shared connections)
- [[Assay Base & Registry Metadata]] (2 shared connections)
- [[IDA Assay & Per-Replica Fits]] (2 shared connections)
- [[Equilibrium Forward Models]] (2 shared connections)
- [[Multistart Optimizer]] (2 shared connections)
- [[BaseAssay Interface]] (2 shared connections)

## Source Files

- `core/optimizer/scaling.py`
- `tests/unit/test_scaling.py`

## Audit Trail

- EXTRACTED: 57 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*