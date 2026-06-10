# Signal Model Edge Cases

> 14 nodes · cohesion 0.16

## Key Concepts

- **dba_signal()** (18 connections) — `core/models/equilibrium.py`
- **TestDBAModel** (6 connections) — `tests/unit/test_models.py`
- **.test_gda_g0_zero_matches_dba()** (4 connections) — `tests/unit/test_models.py`
- **.test_ida_g0_zero_matches_dba()** (4 connections) — `tests/unit/test_models.py`
- **.test_high_ka_saturates()** (3 connections) — `tests/unit/test_models.py`
- **.test_htod_dtoh_equivalence()** (3 connections) — `tests/unit/test_models.py`
- **.test_zero_titrant_gives_baseline()** (3 connections) — `tests/unit/test_models.py`
- **Compute DBA signal for host-dye equilibrium.      Works for both Host→Dye and Dy** (1 connections) — `core/models/equilibrium.py`
- **GDA with g0=0 numerically matches DBA.** (1 connections) — `tests/unit/test_models.py`
- **IDA's titration start (g0=0) numerically matches the DBA quadratic         for t** (1 connections) — `tests/unit/test_models.py`
- **Tests for the DBA (direct binding) forward model.** (1 connections) — `tests/unit/test_models.py`
- **HtoD with no host => all dye free; signal = I0 + I_dye_free * d0.** (1 connections) — `tests/unit/test_models.py`
- **Very high Ka_dye should drive binding to saturation.** (1 connections) — `tests/unit/test_models.py`
- **HtoD and DtoH produce the same signal at the same physical state.          Regre** (1 connections) — `tests/unit/test_models.py`

## Relationships

- [[Equilibrium Forward Models]] (5 shared connections)
- [[Ground-Truth Generators]] (3 shared connections)
- [[Assay Base & Registry Metadata]] (2 shared connections)
- [[DBA Assay Integration]] (2 shared connections)
- [[Synthetic Test Fixtures]] (2 shared connections)
- [[Linear Dye-Alone Model]] (2 shared connections)
- [[Global Fitting Design Notes]] (1 shared connections)
- [[Forward Model Validation]] (1 shared connections)

## Source Files

- `core/models/equilibrium.py`
- `tests/unit/test_models.py`

## Audit Trail

- EXTRACTED: 48 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*