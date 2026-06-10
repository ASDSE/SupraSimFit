# Synthetic Test Fixtures

> 28 nodes · cohesion 0.09

## Key Concepts

- **conftest.py** (23 connections) — `tests/conftest.py`
- **_make_dba_data()** (7 connections) — `tests/conftest.py`
- **_make_ida_data()** (7 connections) — `tests/conftest.py`
- **_make_dye_alone_data()** (6 connections) — `tests/conftest.py`
- **_make_gda_data()** (5 connections) — `tests/conftest.py`
- **dba_clean()** (3 connections) — `tests/conftest.py`
- **dba_noisy()** (3 connections) — `tests/conftest.py`
- **dye_alone_clean()** (3 connections) — `tests/conftest.py`
- **gda_clean()** (3 connections) — `tests/conftest.py`
- **gda_noisy()** (3 connections) — `tests/conftest.py`
- **ida_clean()** (3 connections) — `tests/conftest.py`
- **ida_noisy()** (3 connections) — `tests/conftest.py`
- **minimal_plot_data()** (2 connections) — `tests/conftest.py`
- **_seed_rng()** (2 connections) — `tests/conftest.py`
- **Shared test fixtures for synthetic assay data and GUI helpers.  Generates clean** (1 connections) — `tests/conftest.py`
- **Seed numpy global RNG before each test for reproducible optimization.** (1 connections) — `tests/conftest.py`
- **Generate synthetic DBA data.      Default mode is ``'DtoH'`` (dye titrated, host** (1 connections) — `tests/conftest.py`
- **Generate synthetic GDA data (Dye titrated into Host+Guest).** (1 connections) — `tests/conftest.py`
- **Generate synthetic IDA data (Guest titrated into Host+Dye).** (1 connections) — `tests/conftest.py`
- **Generate synthetic dye-alone data.** (1 connections) — `tests/conftest.py`
- **DBA synthetic data with no noise.** (1 connections) — `tests/conftest.py`
- **GDA synthetic data with no noise.** (1 connections) — `tests/conftest.py`
- **IDA synthetic data with no noise.** (1 connections) — `tests/conftest.py`
- **DyeAlone synthetic data with no noise.** (1 connections) — `tests/conftest.py`
- **DBA synthetic data with 5% Gaussian noise.** (1 connections) — `tests/conftest.py`
- *... and 3 more nodes in this community*

## Relationships

- [[IDA Assay & Per-Replica Fits]] (5 shared connections)
- [[DBA Assay Integration]] (5 shared connections)
- [[Equilibrium Forward Models]] (4 shared connections)
- [[Signal Model Edge Cases]] (2 shared connections)
- [[Linear Dye-Alone Model]] (2 shared connections)
- [[Assay Base & Registry Metadata]] (1 shared connections)

## Source Files

- `tests/conftest.py`

## Audit Trail

- EXTRACTED: 87 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*