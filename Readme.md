<p align="center">
   <img src="assets/logo-suprasense.svg" alt="Suprasense Logo" width="80%"/>
</p>

[![License: GPL v3](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/downloads/)
[![Build and Release](https://github.com/ASDSE/SupraSimFit/actions/workflows/build_and_release.yml/badge.svg)](https://github.com/ASDSE/SupraSimFit/actions/workflows/build_and_release.yml)
[![Latest Release](https://img.shields.io/github/v/release/ASDSE/SupraSimFit?label=Latest%20Release)](https://github.com/ASDSE/SupraSimFit/releases/latest)

# SupraSimFit

A desktop app that fits binding models to fluorescence titration data and tells you how far to trust the association constant it finds.

It fits the raw signal with the full equilibrium model, with no Scatchard, Hill or double-reciprocal transform. Each Kₐ comes with a 95 % interval and a plain-language verdict on the fit.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/design/screens/fit_dark.jpg">
  <img src="docs/design/screens/fit_light.jpg" alt="Fit results: the association constant with its interval, the titration curve over eight replicates, and the fit's diagnostics">
</picture>

## What it does

- **Fits seven binding models**: direct binding in both titration directions, indicator displacement (IDA), guest displacement (GDA), the stepwise 1:2 and 2:1 models, and a dye-alone calibration.
- **Reports Kₐ with a 95 % interval** from the profile likelihood. Where the data place no limit on Kₐ on one side, it says so instead of printing a number.
- **Lets your inputs be uncertain.** Say how well you know each concentration and the dye's Kₐ, and the interval covers that too. The *input-aware* reading appears beside the one that takes your inputs as exact.
- **Checks the fit for you.** It says whether the curve misses the data, or whether your inputs had to move further than you said they could. A conflict always concerns the inputs together, never one input alone.
- **Shows where the uncertainty comes from.** The sensitivity analysis ranks your error sources and estimates what a better pipette, stock or calibration would buy.
- **Reads the noise from your replicates.** Each point is weighted by how precise the replicates show it to be. Fit replicates one by one, and one that needs a different Kₐ from the rest is left out of the average.
- **Simulates a titration** before you measure it, so you can choose concentrations that pin Kₐ down.
- **Exports everything.** A results file reopens and is checked again against your data. Reports come as TXT or CSV, and figures as PNG or SVG.

<table>
  <tr>
    <td><img src="docs/design/screens/confidence_light.jpg" alt="Ka confidence: the profile of each reading with its 95 % cut-off"></td>
    <td><img src="docs/design/screens/sensitivity_light.jpg" alt="Sensitivity: the spread of Ka and the share of it each error source explains"></td>
    <td><img src="docs/design/screens/simulation_light.jpg" alt="Simulation: a planned titration and its species"></td>
  </tr>
  <tr>
    <td align="center">How tightly the data pin Kₐ down</td>
    <td align="center">Which inputs matter</td>
    <td align="center">Planning an experiment</td>
  </tr>
</table>

## Download

Get the build for your system from the [Releases page](https://github.com/ASDSE/SupraSimFit/releases/latest) — `SupraSimFit-<version>-macos.zip`, `-windows.zip` or `-linux.zip`. Unzip it and open the app; no Python needed.

Betas are listed on the same page as pre-releases. The app tells you when a newer version is out. A beta is offered newer betas, and a stable version only newer stable ones.

## Getting started

The quickest way in is the demo: **Load data ▾ › Open demo data (IDA)**, then **Run fit** (⌘R / Ctrl+R).

With your own data:

1. **Load data** (⌘O): your titration as `.txt`, `.csv` or a BMG plate-reader `.xlsx`. Each replicate becomes one curve.
2. **Binding model**: pick the assay, enter the known concentrations and constants, and say whether the titrant dilutes the sample.
3. **Input uncertainty** (optional): how well you know each of those numbers. Every input starts as exact.
4. **Run fit**, then read **Fit results**, **Ka confidence** and **Sensitivity** in the sidebar.

**Help ▸ SupraSimFit help** explains each view and its settings.

## Data files

| Format | Layout |
|---|---|
| `.txt` | Tab-separated blocks, one per replicate, each starting with a `var  signal` header row; `#` starts a comment |
| `.csv` | Long format (`concentration,signal,replica`) or one column per replicate |
| `.xlsx` / `.xls` | BMG plate-reader exports, detected automatically |

Concentrations are those of the titrant in the cuvette after each addition. [data/](data/) holds an example of each assay with its reference parameters ([data/Readme.md](data/Readme.md)).

## How it works

For every candidate Kₐ, the app solves the mass-action equilibrium at each titration point. It then finds the signal coefficients that best explain the measured curve. Kₐ is searched across its whole allowed range, not from a single starting guess. The 95 % interval is read from how quickly the fit worsens as Kₐ moves away from its best value (the profile likelihood). With stated input uncertainties, the inputs may move inside them while the interval is drawn.

Every rate the app quotes, such as how often an interval covers the true value or how often a test raises a false alarm, is measured on thousands of synthetic titrations in [validation/](validation/README.md).

The mathematics, the assumptions and the references are in the [scientific summary](docs/scientific-summary.md).

## Run from source

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/ASDSE/SupraSimFit.git
cd SupraSimFit
uv sync
uv run run_app.py
```

Tests: `uv run pytest` (add `tests/unit` for the fast layer). Standalone build:

```bash
uv run --with pyinstaller pyinstaller --clean -y --distpath ./dist --workpath ./build SupraSimFit.spec
```

## License

GPL 3.0 — see [LICENSE](LICENSE).

## References

1. Sinn, S., Spuling, E., Bräse, S., & Biedermann, F. (2019). Rational design and implementation of a cucurbit[8]uril-based indicator-displacement assay for application in blood serum. *Chemical Science*, 10(28), 6584-6593. <https://doi.org/10.1039/C9SC00705A>
2. Sinn, S., Krämer, J., & Biedermann, F. (2020). Teaching old indicators even more tricks: binding affinity measurements with the guest-displacement assay (GDA). *Chemical Communications*, 56(49), 6620-6623. <https://doi.org/10.1039/D0CC01841D>

---

**Contact:** contact@suprabank.org
