# Forward Model Validation

> 8 nodes · cohesion 0.25

## Key Concepts

- **TestModelVsIndependentEquilibrium** (6 connections) — `tests/unit/test_models.py`
- **.test_competitive_signal_matches_independent_equilibrium()** (3 connections) — `tests/unit/test_models.py`
- **.test_dba_signal_matches_independent_equilibrium()** (3 connections) — `tests/unit/test_models.py`
- **Independent equilibrium solve cross-validation** (2 connections) — `tests/unit/test_models.py`
- **Signal coefficient degeneracy (only Ka identifiable)** (2 connections) — `tests/unit/test_nonzero_i0_recovery.py`
- **Verify the forward models against equilibrium solutions computed by a     differ** (1 connections) — `tests/unit/test_models.py`
- **dba_signal (quadratic) agrees with a Brent solve of the dye balance.** (1 connections) — `tests/unit/test_models.py`
- **competitive_signal_point agrees with an fsolve of the full         3-species sys** (1 connections) — `tests/unit/test_models.py`

## Relationships

- [[Ground-Truth Generators]] (1 shared connections)
- [[Linear Dye-Alone Model]] (1 shared connections)
- [[Global Fitting Design Notes]] (1 shared connections)
- [[Equilibrium Forward Models]] (1 shared connections)
- [[Signal Model Edge Cases]] (1 shared connections)

## Source Files

- `tests/unit/test_models.py`
- `tests/unit/test_nonzero_i0_recovery.py`

## Audit Trail

- EXTRACTED: 14 (74%)
- INFERRED: 5 (26%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*