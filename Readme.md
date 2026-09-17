<p align="center">
   <img src="assets/logo-suprasense.svg" alt="Suprasense Logo" width="80%"/>
</p>

[![License: GPL v3](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/downloads/)
[![Build and Release](https://github.com/ASDSE/SupraSimFit/actions/workflows/build_and_release.yml/badge.svg)](https://github.com/ASDSE/SupraSimFit/actions/workflows/build_and_release.yml)
[![Latest Release](https://img.shields.io/github/v/release/ASDSE/SupraSimFit?label=Latest%20Release)](https://github.com/ASDSE/SupraSimFit/releases/latest)

# Molecular Binding Assay Fitting Toolkit

A desktop application for fitting equilibrium binding models to fluorescence titration data. It is aimed at supramolecular and biochemical researchers who need to extract association constants (Ka) from indicator-displacement, guest-displacement, and direct-binding assays using robust forward-modelling rather than linearised transforms.

The app ships a PyQt6 GUI with interactive plots, per-replicate outlier removal, and one-click import of BMG plate-reader Excel exports.

## Download

Packaged builds for each OS are published on the [Releases page](https://github.com/ASDSE/SupraSimFit/releases/latest):

- macOS — `SupraSimFit-<version>-macos.zip`
- Windows — `SupraSimFit-<version>-windows.zip`
- Linux — `SupraSimFit-<version>-linux.zip`

Unzip and launch the executable or `.app` bundle. No Python installation required.

## Quick start (from source)

Requirements: Python **3.13+** and [**uv**](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/ASDSE/SupraSimFit.git
cd SupraSimFit
uv sync
uv run run_app.py
```

To try the app immediately without loading your own data, click **Demo IDA** in the toolbar — it loads a bundled IDA dataset and runs a fit with sensible defaults.

## Usage

### 1. Load data

Use **Load Data** (Ctrl+O) in the toolbar. Supported input formats:

| Format | Extension | Notes |
|---|---|---|
| Tab-separated text | `.txt` | Multi-replicate blocks; see below |
| Comma-separated | `.csv` | Long-format, wide-format, or multi-replicate blocks |
| BMG plate reader | `.xlsx` / `.xls` | Auto-detected; non-BMG Excel files fall back to a structured reader |

**TXT layout** — each replicate is a block that starts with a header row (`var` and `signal`, separated by a tab). Lines beginning with `#` are treated as comments.

```
var     signal
0.0     506.246
2.985e-05       1064.85
...
var     signal
0.0     503.100
2.985e-05       1059.21
...
```

**CSV layout** — either long-format (recommended) or wide-format with one column per replicate. Column names are matched case-insensitively; `concentration`, `conc`, `x`, `[conc]`, or `titrant` are accepted for the independent variable, and `signal`, `y`, `fluorescence`, `intensity`, or `emission` for the dependent variable.

```
concentration,signal,replica
1e-7,506.246,0
2e-7,612.300,0
1e-7,503.100,1
2e-7,610.000,1
```

Concentrations are stored internally in **Molar**. The GUI accepts input in nM/µM/mM/M and converts automatically. Example datasets with reference parameters live in [data/](data/) — see [data/Readme.md](data/Readme.md).

### 2. Configure and fit

1. Pick the assay type in the **Assay** panel.
2. Enter the known experimental conditions for that assay (e.g. `[Host]₀`, `[Dye]₀`, `Ka_dye`). These fields are unit-aware and accept any supported concentration or binding-constant unit.
3. In the **Bounds** panel, review or tighten the parameter bounds. Defaults cover a wide physically reasonable range; narrower bounds produce better-conditioned fits when prior information is available.
4. In the **Fit Configuration** panel, adjust:
   - **Trials** — how many multi-start trials the optimiser runs (default 100). More starts → more robust estimate, at the cost of runtime.
   - **Min R²** — the R² floor (default 0.99). In a per-replicate fit each replicate is judged against its own signal, and a replicate with no attempt above the floor is left out of the reported fit.
   - **Trim by RMSE factor** — an optional extra trim relative to the best accepted RMSE.
   - **Fixed seed** — tick it to reuse one seed across runs. Left unticked, the app draws a seed per run; either way the seed that produced the fit is recorded with the result.
5. Optionally use the **Outlier Removal** panel to drop noisy replicates via a modified Z-score filter (default threshold 3.5, MAD-based).
6. Click **Run Fit**. Fitting runs off the main thread, and results appear in the plot and summary panel when it finishes.

See the [Scientific background](#scientific-background) below for how each of these configuration options maps onto the underlying physics.

### 3. See how tightly the data pin Ka down

The **Identifiability** tab profiles Ka for the fit in the plot: across the Ka bounds in force it draws the best R² any fit can reach with Ka held at each value, and marks the 95 % confidence interval — every Ka whose fit is not measurably worse than the best one. A narrow band means the data fix Ka; a flat curve over decades means they do not. When the band runs into a Ka bound the tab says so: the data place no limit on Ka on that side, and the honest report is a limit rather than a value.

The curve describes the average of the replicates the fit used, and it assumes the model and the conditions you entered are right. The [Scientific background](#scientific-background) gives the mathematics; **Help ▸ Reading the plots** explains the display.

### 4. Test what an error in your inputs would do

The **Ka Sensitivity** tab answers a different question: how far does Ka move if the numbers you typed in are slightly off? Give each input its uncertainty — the titrant concentrations, `[Host]₀`, `[Dye]₀`, `Ka_dye` — either as a σ or as a plain range, in percent of the entered value or in the input's own unit (the titrant has no single nominal value, so it takes percentages). The app then refits your data many times with those inputs perturbed:

- **Sobol'** — every varied input moved at once. You get the spread of Ka, and Sobol' indices that split that spread among the inputs, so you can see which input your Ka actually depends on. Sample sizes 1024, 2048 and 4096; a run costs `N × (k + 2)` fits for `k` varied inputs.
- **Heatmap** — two inputs stepped over a grid, one fit per cell, so you can read the Ka surface and spot where the fit jumps to another solution.

The analysis is available for the assays with a single association constant (GDA, IDA and both DBA modes). A run prints the seed it used under its plots, so it can be repeated exactly by entering that seed under Fixed seed. **Preferences ▸ Processor cores to use** sets how many fits run side by side; the result is the same whatever you choose.

### 5. Export results

From the **File** menu:

- **Export Fit Results (JSON)** — full result ensemble (parameters, statistics, source file) with the seed that produced it and a fingerprint of the measured values it was fitted to. Re-importable via *Import Results*, which first re-scores each result on the data loaded now and refuses one whose fingerprint belongs to other data. With no data loaded, the stored numbers are shown unchecked.
- **Export Results (TXT)** — human-readable report, naming the replicates the fit used and any it left out.
- **Export Raw Data** — round-trip the loaded measurements back to `.txt` or `.csv`.
- **Save Plot** — save the plot on the tab that is showing. The Fit Curve tab offers PNG or SVG, and the Distributions tab offers both through its layout picker. The Identifiability and Ka Sensitivity tabs are saved whole — heading, plots, key and notes in one picture, without the controls that change what the tab shows — and Qt's SVG painter draws that without the clip that keeps each plot's curves inside its axes, so those two are PNG.

## Scientific background

### Binding models

All assays are described with **association constants** (Ka) and rigorous mass-action equilibria.

#### Direct Binding Assay (DBA)

Direct measurement of host–guest or dye–host binding interactions, available in both titration modes. Monitors spectroscopic changes upon complex formation, but is limited in complex matrices due to competitive binding from naturally occurring interferents.

A host `H` binds directly to a spectroscopically active dye `D`:

```
H + D ⇌ HD        Ka_dye = [HD] / ([H][D])
```

The observed fluorescence signal is modelled as a four-parameter linear combination:

```
I = I0 + I_dye_free · [D_free] + I_dye_bound · [HD]
```

where `I0` absorbs baseline offsets and `I_dye_free`, `I_dye_bound` are the per-species molar signal coefficients. The app supports both titration modes: host titrated into dye (`DBA_HtoD`) and dye titrated into host (`DBA_DtoH`).

#### Indicator Displacement Assay (IDA)

Determines binding constants by competitive displacement of indicator dyes — enabling detection in complex biological matrices through ultra-high-affinity reporter pairs. IDA involves two coupled equilibria, where the reporter dye and the analyte guest compete for the same host binding site:

```
H + D ⇌ HD        Ka_dye    (assumed known, measured via DBA first)
H + G ⇌ HG        Ka_guest  (the quantity being fitted)
```

The guest `G` is titrated into a preformed `HD` complex. As `G` displaces `D`, the observed signal tracks the free-dye / bound-dye ratio, letting the fit recover `Ka_guest` from the same 4-parameter signal model as DBA applied to the coupled mass-balance at each titration point.

#### Guest Displacement Assay (GDA)

Quantifies guest binding affinity by monitoring displacement of a preformed host–indicator complex — particularly valuable for spectroscopically silent hosts and guests, and superior for insoluble or weakly binding guests that are difficult to measure by IDA.

Mechanistically, GDA shares the same coupled equilibria as IDA, but the *dye* is titrated into a pre-equilibrated host + guest mixture instead of the guest being titrated into `HD`. The fitted quantity is again `Ka_guest`.

#### Dye Alone

Linear calibration fitting for indicator dyes — establishes baseline fluorescence properties and helps correct for inner-filter effects in competitive binding assays. Concretely, a linear fit of dye-only fluorescence against dye concentration yields the free-dye response (`I_dye_free`) and baseline (`I0`), which can then be used as priors or fixed values for subsequent DBA/IDA/GDA fits.

### Why forward modelling

Historical fitting methods (Scatchard, Hill, double-reciprocal) rearrange the binding isotherm so it can be fit with linear regression. Those transforms:

- distort the measurement noise structure (non-uniform error weighting in the transformed space),
- lose validity in ligand-depletion regimes, and
- cannot handle coupled competitive equilibria without strong approximations.

This toolkit instead fits the raw signal directly with the full nonlinear model — so the residual is evaluated in the measurement space where the experimental error is best understood.

### Fitting strategy

The nonlinear binding likelihood is typically multi-modal, so single-start gradient methods get trapped in local minima. The toolkit uses:

- **Multi-start L-BFGS-B** — the constrained quasi-Newton optimiser is launched from many random initial parameter vectors (the `n_trials` knob), with Ka parameters sampled in log space (they span several orders of magnitude).
- **Physical bounds** — every parameter has lower/upper bounds so the search stays inside a thermodynamically reasonable region (Ka defaults: 10⁻⁸ to 10¹² M⁻¹). Tighten these in the Bounds panel when you have prior knowledge.
- **Quality filter** — after all starts complete, failed fits are rejected by `min_r_squared` and by an RMSE tolerance factor (`rmse_threshold_factor × best_RMSE`). Only survivors are aggregated.
- **Real fits, honestly summarised** — the reported estimate is the **representative fit**: an actual member of the surviving ensemble. A fit of the averaged signal reports its highest-R² attempt; a per-replicate fit reports, among each replicate's best attempt, the one with the highest R² against the average of the replicates it used (a replicate with no acceptable fit is left out and plays no part in the reported R² or RMSE). The Representative selector in the Fit Summary lets you report another accepted fit instead. Being a real fit, it lies on the model's degenerate manifold and reproduces the plotted curve exactly. Alongside it the app quotes the **range (min, max) across every accepted fit**, with the median ± MAD, mean ± SD and central-68% interval in the summary table. Each of these is read straight from the ensemble, so it describes a skewed or nonlinear parameter distribution as faithfully as a symmetric one.
- **Replicate outlier removal** — the optional Z-score preprocessing step uses a *modified* Z-score based on the median and MAD, so it is not biased by the very outliers it is trying to flag.

The spread across the accepted ensemble says how reproducibly the optimiser converges on this data. How precisely the data determine Ka is a separate question, answered by the Ka profile below; how much the entered conditions determine it is answered by the sensitivity analysis after that.

### How precisely the data pin Ka down — the exact Ka profile

For every assay with a single association constant (GDA, IDA, both DBA modes), the model signal is a *linear* combination of the remaining parameters — the offset `I0` and the signal coefficients — once Ka is held fixed. The best fit at a fixed Ka is therefore a bounded linear least-squares solve rather than a search: the nonlinear parameter is separated from the linear ones (variable projection, Golub & Pereyra). Sweeping Ka across the bounds in force and solving at each value gives the **exact** profile — the highest R² any fit can reach with Ka held there. The curve bounds every fit the optimiser can find, and its peak is located by a grid search along it with a bounded refinement between the best grid point's neighbours, not by a multi-start search.

The **Identifiability** tab reads the confidence interval off that curve with an F test on the residual sum of squares:

```
SSR(Ka) ≤ SSR_min · (1 + F(level; 1, n − p) / (n − p))
```

`n` is the number of points in the profiled signal and `p = 1 + rank of the coefficient design` at the best fit — the number of parameters the data actually resolve. Equal Ka bounds pin Ka: it is then not fitted and contributes nothing, so `p` is the rank alone. The rank is computed numerically, so a pinned coefficient (equal lower and upper bound) and a pair of columns the data cannot separate each count once, not twice; this matters because the signal coefficients are degenerate in DBA and IDA (see below). The interval is every Ka that clears the threshold, its edges found by root-finding on the exact curve. An edge that runs into a Ka bound is reported as open: the data stop nothing there, and the bound, not the measurement, is what ends the interval.

What the interval assumes:

- the binding model is the right one for the system,
- the conditions you entered (`[Host]₀`, `[Dye]₀`, `Ka_dye`, the titrant concentrations) are correct,
- the bounds in force are wide enough not to clip the answer,
- the scatter about the model is independent from point to point and of about the same size across the titration.

**Replicates are averaged, not pooled.** The profile, the best fit and the interval describe the average of the active replicates. Replicates of one titration depart from the model together — the same systematic miss appears in each — so counting their points as independent evidence counts one shared miss as many independent observations, narrowing the interval — by up to about √(number of replicates) where that miss dominates the scatter — and claiming a precision the experiment does not have. `scripts/profile_interval_coverage.py` measures what the interval delivers on synthetic IDA data: 96 % coverage for a nominal 95 % when the scatter is well behaved, 91 % when it scales with the signal, and 77 % when the replicates share a smooth systematic departure from the model — which is the case the averaging protects against, and where pooling the replicates' points instead drops coverage to 67 %.

### How much your inputs matter — Ka sensitivity

The confidence interval takes the entered conditions as exact. The **Ka Sensitivity** tab drops that assumption: state an uncertainty for each input and it refits the data over the input distribution, so you can see what a pipetting error or a `Ka_dye` carried over from an earlier fit does to your result.

- **Sampling.** Each input is drawn independently: a σ from a normal distribution truncated so the value stays positive, a range uniformly between its ends. The titrant enters as one common factor — a single draw scales the whole concentration vector, the way a mis-calibrated stock affects every point at once.
- **Design.** A Saltelli design — matrices `A` and `B` plus the `k` matrices that take one column from `B` — evaluated at `N × (k + 2)` fits. First-order indices use the Saltelli (2010) estimator and total-order indices the Jansen (1999) estimator, both on the variance of log₁₀(Ka), which is the scale on which an association constant varies.
- **Sampling error of the indices.** The design is built from eight independently scrambled Sobol' blocks. Leaving each block out in turn gives a delete-one-block jackknife standard error, and the whiskers on the index chart are the estimate ± t(7, 0.975) × that error. They cover the Monte Carlo sampling error of one index — *not* error in the uncertainties you stated, nor in the model. Blocking costs accuracy: at a fixed budget, splitting the design into eight blocks raises the root-mean-square error of an index by up to a factor of about five, index by index — a few indices are barely affected — over one undivided scramble of the same size. That is the price of being told how far an index can be trusted. The accepted sample sizes start at 1024 because an index there already carries about the error of one undivided scramble of 512; below that the indices are too coarse to rank the inputs by. `scripts/sobol_interval_coverage.py` measures the blocking price, and how often the whiskers hold their index at the sizes offered.
- **Every fit counts.** Each sample is fitted through the same exact Ka profile, so its Ka is the best point of that profile for its perturbed inputs, and it is kept whatever its R². Samples below the R² floor are flagged and drawn grey rather than dropped: discarding them would remove exactly the input combinations your data disagree with and bias the spread towards the inputs as entered.
- **Reading it.** A total-order index near zero, whisker included, means that for the uncertainty you gave it, that input's share is too small to measure here — which is not the same as none. A total-order index well above the first-order one means the input acts through combinations with others; drawn below it, the input acts almost entirely on its own and either estimate can come out on top in any run. Whiskers that clearly stand apart settle which of two inputs matters more; overlapping whiskers are a conservative sign: two 95 % intervals can overlap while the difference between the indices is still significant, so their order may hold — a larger sample size decides it.

### Reproducibility

Every fit records the seed that produced it, and the JSON export carries it, so a result can be reproduced from its file. Tick **Fixed seed** in Fit Configuration to hold one seed across runs; otherwise a seed is drawn per run and recorded. A sensitivity run has its own root seed, which fixes both the Sobol' scrambles and every perturbed fit's optimiser seed; it is printed under the run's plots and so is carried in the saved picture of the tab. Exported results also carry a fingerprint of the measured values, which is what lets *Import Results* refuse numbers that were fitted to other data.

### Identifiability note

In the 4-parameter signal model, the coefficients `I0`, `I_dye_free`, and `I_dye_bound` are **structurally degenerate** for DBA and IDA — only `Ka` is uniquely identifiable from a single titration. The app fits the full 4-parameter model because it reconstructs the observed signal faithfully, but only `Ka` should be reported as a physical constant across datasets. Fixing the signal coefficients with a dye-alone calibration (see [data/Readme.md](data/Readme.md)) breaks the degeneracy when stronger constraints are needed.

## Development

```bash
uv sync                # install runtime + dev dependencies
uv run pytest          # run the test suite
uv run run_app.py      # launch the GUI
```

The GUI can also be launched directly as a module: `uv run python -m gui.main_window`.

Build a standalone executable with PyInstaller:

```bash
uv run --with pyinstaller pyinstaller --clean -y \
    --distpath ./dist --workpath ./build SupraSimFit.spec
```

## Dependencies

Runtime dependencies are pinned in [pyproject.toml](pyproject.toml):

- `numpy`, `scipy` — numerics and L-BFGS-B optimisation
- `pandas`, `openpyxl` — tabular I/O and Excel / BMG plate-reader import
- `pint` — unit-aware parameter conversion
- `PyQt6`, `pyqtgraph` — GUI and interactive plots

## License

GPL 3.0 — see [LICENSE](LICENSE).

## References

### Assays

1. Sinn, S., Spuling, E., Bräse, S., & Biedermann, F. (2019). Rational design and implementation of a cucurbit[8]uril-based indicator-displacement assay for application in blood serum. *Chemical Science*, 10(28), 6584-6593. <https://doi.org/10.1039/C9SC00705A>
2. Sinn, S., Krämer, J., & Biedermann, F. (2020). Teaching old indicators even more tricks: binding affinity measurements with the guest-displacement assay (GDA). *Chemical Communications*, 56(49), 6620-6623. <https://doi.org/10.1039/D0CC01841D>

### Fitting and reporting binding constants

3. Thordarson, P. (2011). Determining association constants from titration experiments in supramolecular chemistry. *Chemical Society Reviews*, 40(3), 1305-1323. <https://doi.org/10.1039/C0CS00062K>
4. Hibbert, D. B., & Thordarson, P. (2016). The death of the Job plot, transparency, open science and online tools, uncertainty estimation methods and other developments in supramolecular chemistry data analysis. *Chemical Communications*, 52(87), 12792-12805. <https://doi.org/10.1039/C6CC03888C>
5. Kazmierczak, N. P., Chew, J. A., & Vander Griend, D. A. (2022). Bootstrap methods for quantifying the uncertainty of binding constants in the hard modeling of spectrophotometric titration data. *Analytica Chimica Acta*, 1227, 339834. <https://doi.org/10.1016/j.aca.2022.339834>
6. Hübler, C. (2022). SupraFit — an open source Qt based fitting application to determine stability constants from titration experiments. *Chemistry–Methods*, 2(6), e202200006. <https://doi.org/10.1002/cmtd.202200006>

### Nonlinear regression and profile likelihood

7. Bates, D. M., & Watts, D. G. (1988). *Nonlinear Regression Analysis and Its Applications*. Wiley. <https://doi.org/10.1002/9780470316757>
8. Seber, G. A. F., & Wild, C. J. (1989). *Nonlinear Regression*. Wiley. <https://doi.org/10.1002/0471725315>
9. Venzon, D. J., & Moolgavkar, S. H. (1988). A method for computing profile-likelihood-based confidence intervals. *Journal of the Royal Statistical Society: Series C*, 37(1), 87-94. <https://doi.org/10.2307/2347496>
10. Raue, A., Kreutz, C., Maiwald, T., Bachmann, J., Schilling, M., Klingmüller, U., & Timmer, J. (2009). Structural and practical identifiability analysis of partially observed dynamical models by exploiting the profile likelihood. *Bioinformatics*, 25(15), 1923-1929. <https://doi.org/10.1093/bioinformatics/btp358>
11. Golub, G. H., & Pereyra, V. (1973). The differentiation of pseudo-inverses and nonlinear least squares problems whose variables separate. *SIAM Journal on Numerical Analysis*, 10(2), 413-432. <https://doi.org/10.1137/0710036>
12. Golub, G., & Pereyra, V. (2003). Separable nonlinear least squares: the variable projection method and its applications. *Inverse Problems*, 19(2), R1-R26. <https://doi.org/10.1088/0266-5611/19/2/201>

### Sensitivity analysis

13. Sobol', I. M. (2001). Global sensitivity indices for nonlinear mathematical models and their Monte Carlo estimates. *Mathematics and Computers in Simulation*, 55(1-3), 271-280. <https://doi.org/10.1016/S0378-4754(00)00270-6>
14. Saltelli, A., Annoni, P., Azzini, I., Campolongo, F., Ratto, M., & Tarantola, S. (2010). Variance based sensitivity analysis of model output. Design and estimator for the total sensitivity index. *Computer Physics Communications*, 181(2), 259-270. <https://doi.org/10.1016/j.cpc.2009.09.018>
15. Jansen, M. J. W. (1999). Analysis of variance designs for model output. *Computer Physics Communications*, 117(1-2), 35-43. <https://doi.org/10.1016/S0010-4655(98)00154-4>
16. Archer, G. E. B., Saltelli, A., & Sobol', I. M. (1997). Sensitivity measures, ANOVA-like techniques and the use of bootstrap. *Journal of Statistical Computation and Simulation*, 58(2), 99-120. <https://doi.org/10.1080/00949659708811825>
17. Owen, A. B. (1997). Monte Carlo variance of scrambled net quadrature. *SIAM Journal on Numerical Analysis*, 34(5), 1884-1910. <https://doi.org/10.1137/S0036142994277468>
18. L'Ecuyer, P., & Lemieux, C. (2002). Recent advances in randomized quasi-Monte Carlo methods. In *Modeling Uncertainty* (pp. 419-474). Springer. <https://doi.org/10.1007/0-306-48102-2_20>

---

**Contact:** contact@suprabank.org
