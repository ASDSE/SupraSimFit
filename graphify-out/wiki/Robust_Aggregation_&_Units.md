# Robust Aggregation & Units

> 29 nodes · cohesion 0.09

## Key Concepts

- **fit_assay** (11 connections) — `core/pipeline/fit_pipeline.py`
- **Scientific Summary** (9 connections) — `docs/scientific-summary.md`
- **aggregate_fits** (8 connections) — `core/optimizer/filters.py`
- **bounds_from_dye_alone** (4 connections) — `core/pipeline/fit_pipeline.py`
- **Pint Findings note** (4 connections) — `docs/pint-findings.md`
- **Signal-coefficient structural degeneracy** (4 connections) — `docs/scientific-summary.md`
- **4-parameter signal response model** (4 connections) — `docs/scientific-summary.md`
- **filter_fits** (3 connections) — `core/optimizer/filters.py`
- **Pooled passing-trial aggregation (median + MAD)** (3 connections) — `core/pipeline/fit_pipeline.py`
- **Mass balance equations (quadratic/cubic)** (3 connections) — `docs/scientific-summary.md`
- **ureg (single shared UnitRegistry)** (2 connections) — `core/units.py`
- **filter_by_rmse** (2 connections) — `core/optimizer/filters.py`
- **Robust aggregation (median + MAD ensemble)** (2 connections) — `core/optimizer/filters.py`
- **save_results** (2 connections) — `core/io/__init__.py`
- **Normalize-at-boundaries, float hot path** (2 connections) — `docs/pint-findings.md`
- **Built-in Pint format specifiers (~P/~H/L)** (2 connections) — `docs/pint-findings.md`
- **Single shared UnitRegistry principle** (2 connections) — `docs/pint-findings.md`
- **Modified Z-score (median + MAD) outlier filter** (2 connections) — `core/data_processing/preprocessing.py`
- **Brent's method root-finding** (2 connections) — `docs/scientific-summary.md`
- **Forward Modeling approach** (2 connections) — `docs/scientific-summary.md`
- **Law of Mass Action / association constant Ka** (2 connections) — `docs/scientific-summary.md`
- **L-BFGS-B bound-constrained optimization** (2 connections) — `docs/scientific-summary.md`
- **Non-negative signal/Ka constraints** (2 connections) — `docs/scientific-summary.md`
- **Robust median + MAD aggregation** (2 connections) — `docs/scientific-summary.md`
- **compute_mad** (1 connections) — `core/optimizer/filters.py`
- *... and 4 more nodes in this community*

## Relationships

- [[BaseAssay Interface]] (3 shared connections)
- [[Assay Base & Registry Metadata]] (2 shared connections)
- [[Dye-Alone Calibration & Scaling]] (2 shared connections)
- [[MeasurementSet & FitResult]] (2 shared connections)
- [[Fit Aggregation]] (1 shared connections)
- [[Parameter Descriptions & Linear Fit]] (1 shared connections)
- [[Ground-Truth Generators]] (1 shared connections)
- [[Bounds Resolution Helpers]] (1 shared connections)
- [[Multistart Optimizer]] (1 shared connections)
- [[Txt Reader Round-trip]] (1 shared connections)
- [[Data Processing & Preprocessing]] (1 shared connections)

## Source Files

- `core/data_processing/preprocessing.py`
- `core/io/__init__.py`
- `core/optimizer/filters.py`
- `core/pipeline/fit_pipeline.py`
- `core/units.py`
- `docs/pint-findings.md`
- `docs/scientific-summary.md`
- `tests/unit/test_optimizer.py`
- `tests/unit/test_scaling.py`

## Audit Trail

- EXTRACTED: 57 (66%)
- INFERRED: 29 (34%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*