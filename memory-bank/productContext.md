# Product Context: Molecular Binding Assay Fitting Toolkit

## Why this project exists

Experimental chemists and biochemists need reliable binding constants and uncertainty estimates for host–guest and indicator-based assays. Traditional analysis (Scatchard, Hill, double‑reciprocal plots) distorts errors and struggles with complex equilibria and ligand depletion.

This toolkit provides a **forward‑modeling** approach that can be applied to any titration assay where:

- there is a change in some measurable signal (e.g. fluorescence, absorbance), and
- we have a physically motivated forward model connecting concentrations to signal.

It is not limited to plate‑reader exports or a specific vendor; those are just common practical sources of data.

## Problems it solves

- **Biased parameters** from linearized plots and ad‑hoc fitting.
- **Limited models** that cannot capture competitive binding, ligand depletion, or multi‑component equilibria.
- **Manual, non‑reproducible workflows** for titration data.
- **Inconsistent handling of units** when switching between molarity scales or datasets.

## How it should work (conceptually)

1. User prepares titration data (fluorescence, absorbance, etc.) in a supported file format (initial focus: `.txt`, `.xlsx`).
2. User selects an assay type (GDA, IDA, DBA host→dye or dye→host, Dye Alone) and configures fit options.
3. Core engine:
   - Uses equilibrium and mass‑balance equations to relate total concentrations to free/bound species.
   - Solves the resulting equations numerically (e.g. via root‑finding such as `scipy.optimize.brentq`).
   - Computes predicted signal via the forward model.
   - Adjusts parameters to minimize discrepancies between predicted and measured signals.
4. Toolkit reports best‑fit parameters, uncertainty estimates (via ensembles), and diagnostics (residuals, goodness‑of‑fit).
5. User exports results and plots for publication or further analysis.

## User personas and workflows

- **Bench scientist / PhD student**
  - Uses the GUI; cares about ease‑of‑use, transparent error messages, and publication‑ready plots.
- **Method developer / power user**
  - Uses the Python API and notebooks for custom models, batch fits, or automation.
- **Single‑developer maintainer**
  - Iteratively refactors, experiments with new models, and is free to break backward compatibility during development.

Typical workflows:

- Fit a single titration experiment for a given assay.
- Batch fitting across many datasets (plate layouts, series of titrations, etc.).
- Merging independent fits into combined statistics.

## User experience goals

- **Low friction**: `python main.py` or a platform‑specific executable should be enough to run the GUI.
- **Guided flow**: load → configure → fit → inspect → export.
- **Physical transparency**: always expose residuals and diagnostics in the measurement space.
- **Unit‑aware analysis**: integrate physical units (e.g. via `pint`) so that parameters and data are consistently unit‑safe.
- **Research‑grade, not production‑grade**: prioritise flexibility, clarity, and experiment speed over long‑term API stability.

## Scientific background

Detailed theory and mathematical context live in [docs/scientific-summary.md](docs/scientific-summary.md).
