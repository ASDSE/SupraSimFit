# GDA Assay

> 16 nodes · cohesion 0.17

## Key Concepts

- **GDAAssay** (66 connections) — `core/assays/gda.py`
- **TestGDAQuantityConditions** (10 connections) — `tests/unit/test_assay_quantity.py`
- **test_assay_quantity.py** (8 connections) — `tests/unit/test_assay_quantity.py`
- **.get_conditions()** (3 connections) — `core/assays/gda.py`
- **Pint Quantity dimensional validation at assay boundary** (3 connections) — `tests/unit/test_assay_quantity.py`
- **.__post_init__()** (2 connections) — `core/assays/gda.py`
- **.test_bare_float_conditions_rejected()** (2 connections) — `tests/unit/test_assay_quantity.py`
- **.test_quantity_conditions_accepted()** (2 connections) — `tests/unit/test_assay_quantity.py`
- **.test_wrong_dimensionality_h0_raises()** (2 connections) — `tests/unit/test_assay_quantity.py`
- **.test_wrong_dimensionality_Ka_raises()** (2 connections) — `tests/unit/test_assay_quantity.py`
- **Return experimental conditions.          Returns         -------         Dict[st** (1 connections) — `core/assays/gda.py`
- **Guest Displacement Assay data container.      Attributes     ----------     x_da** (1 connections) — `core/assays/gda.py`
- **Validate data and conditions.** (1 connections) — `core/assays/gda.py`
- **Tests for assay constructors accepting pint Quantity conditions.** (1 connections) — `tests/unit/test_assay_quantity.py`
- **GDA assay accepts Quantity conditions with dimensional validation.** (1 connections) — `tests/unit/test_assay_quantity.py`
- **Q_ (pint Quantity factory)** (1 connections) — `core/units.py`

## Relationships

- [[DBA Assay Integration]] (13 shared connections)
- [[Fail-Fast Contracts]] (10 shared connections)
- [[Assay Base & Registry Metadata]] (5 shared connections)
- [[Bounds Resolution Helpers]] (5 shared connections)
- [[MeasurementSet & FitResult]] (3 shared connections)
- [[IDA Assay & Per-Replica Fits]] (3 shared connections)
- [[BaseAssay Contracts]] (3 shared connections)
- [[MeasurementSet Immutability]] (3 shared connections)
- [[BaseAssay Interface]] (2 shared connections)
- [[Dye-Alone Calibration Chain]] (2 shared connections)
- [[MeasurementSet Construction]] (2 shared connections)
- [[DBA Quantity Conditions]] (2 shared connections)

## Source Files

- `core/assays/gda.py`
- `core/units.py`
- `tests/unit/test_assay_quantity.py`

## Audit Trail

- EXTRACTED: 61 (58%)
- INFERRED: 45 (42%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*