# Global Fitting Design Notes

> 13 nodes · cohesion 0.17

## Key Concepts

- **competitive_signal_point** (6 connections) — `core/models/equilibrium.py`
- **TestBrentBracketRobustness** (5 connections) — `tests/unit/test_models.py`
- **Global / multi-dataset fitting design** (3 connections) — `docs/notes/global-fitting-design.md`
- **Linear-in-species signal model validity (Beer-Lambert exact, fluorescence dilute-approx)** (3 connections) — `docs/notes/observable-scope.md`
- **.test_competitive_root_is_physical()** (3 connections) — `tests/unit/test_models.py`
- **.test_dba_root_is_physical()** (3 connections) — `tests/unit/test_models.py`
- **linear_signal** (2 connections) — `core/models/linear.py`
- **Observable scope: fluorescence vs absorbance** (2 connections) — `docs/notes/observable-scope.md`
- **_make_dye_alone_data generator** (1 connections) — `tests/conftest.py`
- **Parameter-mapping pattern (shared vs per-dataset)** (1 connections) — `docs/notes/global-fitting-design.md`
- **Verify the competitive Brent solver finds a physical root across     several dec** (1 connections) — `tests/unit/test_models.py`
- **[H_free] must be finite and in (0, h0) regardless of Ka magnitudes.** (1 connections) — `tests/unit/test_models.py`
- **DBA quadratic must produce a non-negative free fixed-species root.** (1 connections) — `tests/unit/test_models.py`

## Relationships

- [[Ground-Truth Generators]] (2 shared connections)
- [[Forward Model Validation]] (1 shared connections)
- [[Linear Dye-Alone Model]] (1 shared connections)
- [[Equilibrium Forward Models]] (1 shared connections)
- [[Signal Model Edge Cases]] (1 shared connections)

## Source Files

- `core/models/equilibrium.py`
- `core/models/linear.py`
- `docs/notes/global-fitting-design.md`
- `docs/notes/observable-scope.md`
- `tests/conftest.py`
- `tests/unit/test_models.py`

## Audit Trail

- EXTRACTED: 26 (81%)
- INFERRED: 6 (19%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*