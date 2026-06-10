# Ground-Truth Generators

> 20 nodes · cohesion 0.15

## Key Concepts

- **TestCompetitiveBoundaries** (9 connections) — `tests/unit/test_models.py`
- **TestIDARecoveryNonzeroI0** (9 connections) — `tests/unit/test_nonzero_i0_recovery.py`
- **gda_signal** (7 connections) — `core/models/equilibrium.py`
- **dba_signal** (6 connections) — `core/models/equilibrium.py`
- **ida_signal** (6 connections) — `core/models/equilibrium.py`
- **Pipeline end-to-end tests** (5 connections) — `tests/integration/test_pipeline_e2e.py`
- **Synthetic ground-truth parameters** (4 connections) — `tests/conftest.py`
- **_make_dba_data generator** (4 connections) — `tests/conftest.py`
- **DBA_DtoH signal-coefficient bug** (4 connections) — `docs/notes/dba-dtoh-signal-bug.md`
- **assert_within_tolerance** (3 connections) — `tests/conftest.py`
- **Per-replica fit tests** (3 connections) — `tests/integration/test_per_replica_fit.py`
- **ida_assay fixture** (3 connections) — `tests/unit/test_scaling.py`
- **_make_ida_data generator** (2 connections) — `tests/conftest.py`
- **Round-trip tests validate solver consistency, not model correctness** (2 connections) — `docs/notes/dba-dtoh-signal-bug.md`
- **_make_ida_assay** (2 connections) — `tests/unit/test_scaling.py`
- **Never check source against itself (anti-tautology)** (2 connections) — `tests/CLAUDE.md`
- **IDA_TRUE synthetic ground truth** (1 connections) — `tests/conftest.py`
- **_make_gda_data generator** (1 connections) — `tests/conftest.py`
- **Three-pillar testing philosophy** (1 connections) — `tests/CLAUDE.md`
- **Limiting cases for the competitive binding model.** (1 connections) — `tests/unit/test_models.py`

## Relationships

- [[Signal Model Edge Cases]] (3 shared connections)
- [[IDA Assay & Per-Replica Fits]] (3 shared connections)
- [[Equilibrium Forward Models]] (3 shared connections)
- [[Competitive Model Tests]] (2 shared connections)
- [[Global Fitting Design Notes]] (2 shared connections)
- [[Dye-Alone Calibration & Scaling]] (1 shared connections)
- [[Linear Dye-Alone Model]] (1 shared connections)
- [[BaseAssay Interface]] (1 shared connections)
- [[Forward Model Validation]] (1 shared connections)
- [[Robust Aggregation & Units]] (1 shared connections)
- [[IDA Ka Recovery]] (1 shared connections)

## Source Files

- `core/models/equilibrium.py`
- `docs/notes/dba-dtoh-signal-bug.md`
- `tests/CLAUDE.md`
- `tests/conftest.py`
- `tests/integration/test_per_replica_fit.py`
- `tests/integration/test_pipeline_e2e.py`
- `tests/unit/test_models.py`
- `tests/unit/test_nonzero_i0_recovery.py`
- `tests/unit/test_scaling.py`

## Audit Trail

- EXTRACTED: 60 (80%)
- INFERRED: 15 (20%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*