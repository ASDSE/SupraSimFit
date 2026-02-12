# Project Brief: Molecular Binding Assay Fitting Toolkit

## Purpose

Build a research‑grade toolkit for fitting molecular binding assays (GDA, IDA, DBA, Dye Alone) using forward modeling and robust nonlinear optimization. The toolkit provides a GUI and a Python API for extracting binding constants and signal parameters from titration data.

## Primary goals

1. **Restructure core fitting logic** with a modular, maintainable architecture.
2. Integrate **pint** for physical units across the pipeline.
3. Separate concerns: **Assay definitions**, **Forward models**, **Optimizer**, **Pipeline**, **I/O**.
4. Simplify I/O to **.txt** and **.xlsx** with clear validation.
5. Add tests around the new architecture to enable aggressive refactoring.

## Paused / Postponed

- **GUI development** — completely paused; breakage acceptable.
- **Public API stabilization** — postponed until core refactor is complete.
- **PyQt 6 migration** — deferred.

## Scope (now)

- **Core fitting logic redesign** — modular assay classes, shared optimizer, decoupled I/O.
- I/O for `.txt` and `.xlsx` only.
- Testing: P1–P4 complete (62 tests). P5–P6 pending.

## Out of scope (for now)

- Support for NetCDF, Parquet, and other non‑essential formats.
- Production‑grade stability or long‑term backward compatibility.
- GUI development (Tkinter or PyQt 6).
- Public API wrappers.

## Constraints and assumptions

- Single‑developer research codebase; breaking changes are acceptable.
- Prefer simplicity and clarity over preserving legacy abstractions.
- Python 3.13.5, managed with **uv**.

## Scientific background

The detailed scientific and mathematical summary lives in docs/scientific-summary.md, including parameter identifiability analysis (Section 5).