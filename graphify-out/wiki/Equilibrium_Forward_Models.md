# Equilibrium Forward Models

> 17 nodes · cohesion 0.16

## Key Concepts

- **ida_signal()** (18 connections) — `core/models/equilibrium.py`
- **gda_signal()** (14 connections) — `core/models/equilibrium.py`
- **competitive_signal_point()** (9 connections) — `core/models/equilibrium.py`
- **__init__.py** (8 connections) — `core/models/__init__.py`
- **equilibrium.py** (6 connections) — `core/models/equilibrium.py`
- **ndarray** (3 connections) — `core/models/equilibrium.py`
- **.test_competitive_d0_zero_gives_I0()** (3 connections) — `tests/unit/test_models.py`
- **.test_ida_ka_guest_huge_displaces_all_dye()** (3 connections) — `tests/unit/test_models.py`
- **.test_ida_ka_guest_zero_no_displacement()** (3 connections) — `tests/unit/test_models.py`
- **Forward models for equilibrium binding assays.  This module contains pure mathem** (1 connections) — `core/models/equilibrium.py`
- **Compute signal for a single point in competitive binding equilibrium.      This** (1 connections) — `core/models/equilibrium.py`
- **Compute GDA signal across dye concentration range.      In GDA (Guest Displaceme** (1 connections) — `core/models/equilibrium.py`
- **Compute IDA signal across guest concentration range.      In IDA (Indicator Disp** (1 connections) — `core/models/equilibrium.py`
- **Forward models for molecular binding assays.** (1 connections) — `core/models/__init__.py`
- **Non-binding guest (Ka→0) produces constant signal.** (1 connections) — `tests/unit/test_models.py`
- **Overwhelmingly strong guest saturates host → dye fully displaced.** (1 connections) — `tests/unit/test_models.py`
- **No dye → signal equals I0 (no dye contribution).** (1 connections) — `tests/unit/test_models.py`

## Relationships

- [[Linear Dye-Alone Model]] (6 shared connections)
- [[Signal Model Edge Cases]] (5 shared connections)
- [[Synthetic Test Fixtures]] (4 shared connections)
- [[Ground-Truth Generators]] (3 shared connections)
- [[Assay Base & Registry Metadata]] (2 shared connections)
- [[BaseAssay Interface]] (2 shared connections)
- [[Competitive Model Tests]] (2 shared connections)
- [[Parameter Scaling]] (2 shared connections)
- [[Global Fitting Design Notes]] (1 shared connections)
- [[Forward Model Validation]] (1 shared connections)
- [[MeasurementSet & FitResult]] (1 shared connections)
- [[IDA Assay & Per-Replica Fits]] (1 shared connections)

## Source Files

- `core/models/__init__.py`
- `core/models/equilibrium.py`
- `tests/unit/test_models.py`

## Audit Trail

- EXTRACTED: 75 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*