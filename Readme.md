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
4. In the **Fit Configuration** panel, decide whether to **fit each replicate separately**. The reported fit is the fit of the average of the replicates used either way — for replicates of equal scatter that average *is* their joint least-squares fit. With the box ticked, the app additionally fits every replicate on its own, reports what each one gives for the association constant, and leaves a replicate out of the average when its own fit needs a different Ka than the others share.
5. Optionally use the **Outlier Removal** panel to drop noisy replicates via a modified Z-score filter (default threshold 3.5, MAD-based).
6. Click **Run Fit**. Fitting runs off the main thread, and results appear in the plot and summary panel when it finishes.

See the [Scientific background](#scientific-background) below for how each of these configuration options maps onto the underlying physics.

### 3. See how tightly the data pin Ka down

The **Identifiability** tab profiles each association constant of the fit in the plot: across the Ka bounds in force it draws the best R² any fit can reach with that Ka held at each value, and marks the 95 % confidence interval — every Ka whose fit is not measurably worse than the best one. A narrow band means the data fix Ka; a flat curve over decades means they do not. When the band runs into a Ka bound the tab says so: the data place no limit on Ka on that side, and the honest report is a limit rather than a value.

For the stepwise models, which have two association constants, each one gets its own profile — drawn with the other constant refitted at every point, so the curve shows what the data say about that constant alone — and a third panel maps the joint 95 % region of the pair. The two constants trade off against each other, so the region is not the rectangle the two intervals span: it reaches further along the direction in which one constant compensates the other, and it rejects pairs that each interval on its own allows. Whether a *pair* of values is compatible with the data is the region's answer, not the two intervals'.

The curves describe the average of the replicates the fit used, and they assume the model and the conditions you entered are right. The [Scientific background](#scientific-background) gives the mathematics; **Help ▸ Reading the plots** explains the display.

### 4. Test what an error in your inputs would do

The **Ka Sensitivity** tab answers a different question: how far does Ka move if the numbers you typed in are slightly off? Give each input its uncertainty — the titrant concentrations, `[Host]₀`, `[Dye]₀`, `Ka_dye` — either as a σ or as a plain range, in percent of the entered value or in the input's own unit (the titrant has no single nominal value, so it takes percentages). The app then refits your data many times with those inputs perturbed:

- **Sobol'** — every varied input moved at once. You get the spread of Ka, and Sobol' indices that split that spread among the inputs, so you can see which input your Ka actually depends on. Sample sizes 1024, 2048 and 4096; a run costs `N × (k + 2)` fits for `k` varied inputs.
- **Heatmap** — two inputs stepped over a grid, one fit per cell, so you can read the Ka surface and spot where the fit jumps to another solution.

The analysis is available for every assay that has an association constant, the stepwise 1:2 and 2:1 models included. A run prints the seed it used under its plots, so it can be repeated exactly by entering that seed under Fixed seed. **Preferences ▸ Processor cores to use** sets how many fits run side by side; the result is the same whatever you choose.

### 5. Export results

From the **File** menu:

- **Export Results (JSON)** — the fitted parameters, the confidence interval of every association constant, the fit statistics, the replicates used and left out, the source file, and a fingerprint of the measured values it was fitted to. Re-importable via *Import Results*, which first re-scores each result on the data loaded now and refuses one whose fingerprint belongs to other data. With no data loaded, the stored numbers are shown unchecked. A file written by an earlier version imports too; it carries no interval, and the summary says so and asks for a new fit.
- **Export Results (TXT)** — human-readable report, naming the replicates the fit used and any it left out.
- **Export Results (CSV)** — one row per parameter: estimate, interval and its level, the replicate statistics, and the fit statistics.
- **Export Raw Data** — round-trip the loaded measurements back to `.txt` or `.csv`.
- **Save Plot** — save the plot on the tab that is showing. The Fit Curve tab offers PNG or SVG. The Identifiability and Ka Sensitivity tabs are saved whole — heading, plots, key and notes in one picture, without the controls that change what the tab shows — and Qt's SVG painter draws that without the clip that keeps each plot's curves inside its axes, so those two are PNG.

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

#### Solving the equilibrium

Every predicted signal needs the free concentrations at that titration point. DBA has a closed form. The competitive assays (IDA, GDA) and the stepwise 1:2 models (HG2, H2G) need a numerical solve of the mass balance: a Newton iteration started from a guaranteed lower bound on the root and stopped on a **relative** step of 4 machine epsilons — monotone for the competitive balance, which is increasing and concave in the free host, and safeguarded by a bracket for the stepwise balance, which need not be. Where binding is tight the free concentration lies ten or more decades below the totals, so the balance is evaluated in a form that adds only the minority species of each binding partner. The solved concentration is accurate to a few epsilons *relative*, at any Ka and any ratio of the totals whose product with that Ka a double can still represent — certified against exact rational arithmetic — which is what keeps the Ka profile smooth enough that its minimum and its interval edges are the data's. Inputs there is no speciation for, such as a negative constant, a product of a constant with a total or a stepwise product beyond the range of a double, or a free concentration the solve drives below the smallest normal double, give *not a number*: that point has no fit rather than a wrong one.

### Why forward modelling

Historical fitting methods (Scatchard, Hill, double-reciprocal) rearrange the binding isotherm so it can be fit with linear regression. Those transforms:

- distort the measurement noise structure (non-uniform error weighting in the transformed space),
- lose validity in ligand-depletion regimes, and
- cannot handle coupled competitive equilibria without strong approximations.

This toolkit instead fits the raw signal directly with the full nonlinear model — so the residual is evaluated in the measurement space where the experimental error is best understood.

### Fitting strategy — variable projection

Every binding model here is linear in all of its parameters but the association constants: hold Ka fixed and the equilibrium solve fixes the concentration of every species, which leaves the signal `I = I0 + Σ Iᵢ · [species i]` a plain linear combination of known columns. The fit is built on that split (variable projection, Golub & Pereyra):

- **The signal parameters are solved, not searched.** At a fixed Ka the best coefficients inside their bounds are a bounded linear least-squares solve — one exact answer, no starting point, nothing to converge. The bounds you set on those parameters are the constraints of that solve, and equal bounds pin a parameter at its value.
- **Only Ka is searched, in one or two dimensions.** What remains is the residual as a function of the association constants alone. The app evaluates it on a log grid of at least four points per decade across the Ka bounds in force and refines from the best grid points, so the reported fit is the least-squares fit of the whole model, obtained by covering the range rather than by starting somewhere and hoping. A model with two association constants is covered the same way on the two-dimensional grid, refining its five best local minima. The same data always give the same fit.
- **Physical bounds** — every association constant is searched inside lower/upper bounds that keep it in a thermodynamically reasonable region (defaults: 10⁻⁸ to 10¹² M⁻¹). A signal parameter cannot be negative and has no upper limit unless you enter one, so the same titration gives the same fit at any detector gain. Tighten bounds in the Bounds panel when you have prior knowledge; a fit that ends on a signal bound you entered says so.
- **What is reported** — the fit, and beside each association constant the 95 % profile-likelihood confidence interval described below: `Ka = estimate [low, high]`. An end the data do not close is written in words (`no upper limit`) rather than as a number, because a limit of the search is not a measurement. Signal coefficients that the data fix only in combination with each other are starred wherever they are listed: the combination reproduces the curve exactly, the individual values are not a result.
- **Replicates** — the reported fit is the fit of the average of the replicates used, which for replicates of equal scatter is their joint least-squares fit. Fitting each replicate separately additionally reports what each one gives on its own — real between-replicate information — and leaves a replicate out of the average when an F test says its own fit needs a different Ka than the others share, at a family-wise 1 % (the ISO 5725-2 outlier level, spread over the replicates given). Half of the replicates or more are never removed, and the report names every replicate left out and why.
- **Replicate outlier removal** — the optional Z-score preprocessing step uses a *modified* Z-score based on the median and MAD, so it is not biased by the very outliers it is trying to flag.

How precisely the data determine Ka is the interval, described next; how much the entered conditions determine it is answered by the sensitivity analysis after that.

### How precisely the data pin Ka down — the Ka profile

Sweeping one association constant across the bounds in force, and at each of its values solving the signal coefficients exactly and refitting any other association constant, gives the **profile**: the highest R² any fit can reach with that constant held there. It is the same projection the fit itself is made of, so the peak of the profile *is* the reported fit, to the last digit, and the curve bounds every fit of these data with that constant held at that value.

The **Identifiability** tab reads the confidence interval off that curve with an F test on the residual sum of squares:

```
SSR(Ka) ≤ SSR_min · (1 + F(level; 1, n − p) / (n − p))
```

`n` is the number of points in the profiled signal and `p = (association constants fitted) + rank of the coefficient design` at the best fit — the number of parameters the data actually resolve. Equal Ka bounds pin that constant: it is then not fitted and contributes nothing to `p`. The rank is computed numerically, so a pinned coefficient (equal lower and upper bound) and a pair of columns the data cannot separate each count once, not twice; this matters because the signal coefficients are degenerate in DBA and IDA (see below). The interval is every Ka that clears the threshold, its edges found by root-finding on the exact curve. An edge that runs into a Ka bound is reported as open: the data stop nothing there, and the bound, not the measurement, is what ends the interval. With two association constants, so is an edge that exists only because the *other* constant has reached its bound: the report names that constant, and gives no limit on that side.

A model with two association constants gets one interval per constant, each read off that constant's own profile, and a **joint region** — the pairs whose fit clears the same test with two degrees of freedom, `SSR ≤ SSR_min · (1 + 2 F(level; 2, n − p) / (n − p))`. The two readings answer different questions: an interval is what the data say about one constant with the other free, the region is which *pairs* they allow. Reading the two intervals as a pair would claim both more and less than the data support — the region stretches beyond them along the direction the two constants trade off in, and excludes pairs that lie inside both.

What the interval assumes:

- the binding model is the right one for the system,
- the conditions you entered (`[Host]₀`, `[Dye]₀`, `Ka_dye`, the titrant concentrations) are correct,
- the bounds in force are wide enough not to clip the answer,
- the scatter about the model is independent from point to point and of about the same size across the titration.

**Replicates are averaged, not pooled.** The profile, the best fit and the interval describe the average of the replicates the fit used. Replicates of one titration depart from the model together — the same systematic miss appears in each — so counting their points as independent evidence counts one shared miss as many independent observations, narrowing the interval — by up to about √(number of replicates) where that miss dominates the scatter — and claiming a precision the experiment does not have. `scripts/profile_interval_coverage.py` measures what the interval delivers on synthetic IDA data: 96 % coverage for a nominal 95 % when the scatter is well behaved, 91 % when it scales with the signal, and 77 % when the replicates share a smooth systematic departure from the model — which is the case the averaging protects against, and where pooling the replicates' points instead drops coverage to 67 %.

### How much your inputs matter — Ka sensitivity

The confidence interval takes the entered conditions as exact. The **Ka Sensitivity** tab drops that assumption: state an uncertainty for each input and it refits the data over the input distribution, so you can see what a pipetting error or a `Ka_dye` carried over from an earlier fit does to your result.

- **Sampling.** Each input is drawn independently: a σ from a normal distribution truncated so the value stays positive, a range uniformly between its ends. The titrant enters as one common factor — a single draw scales the whole concentration vector, the way a mis-calibrated stock affects every point at once.
- **Design.** A Saltelli design — matrices `A` and `B` plus the `k` matrices that take one column from `B` — evaluated at `N × (k + 2)` fits. First-order indices use the Saltelli (2010) estimator and total-order indices the Jansen (1999) estimator, both on the variance of log₁₀(Ka), which is the scale on which an association constant varies.
- **Sampling error of the indices.** The design is built from eight independently scrambled Sobol' blocks. Leaving each block out in turn gives a delete-one-block jackknife standard error, and the whiskers on the index chart are the estimate ± t(7, 0.975) × that error. They cover the Monte Carlo sampling error of one index — *not* error in the uncertainties you stated, nor in the model. Blocking costs accuracy: at a fixed budget, splitting the design into eight blocks raises the root-mean-square error of an index by up to a factor of about five, index by index — a few indices are barely affected — over one undivided scramble of the same size. That is the price of being told how far an index can be trusted. The accepted sample sizes start at 1024 because an index there already carries about the error of one undivided scramble of 512; below that the indices are too coarse to rank the inputs by. `scripts/sobol_interval_coverage.py` measures the blocking price, and how often the whiskers hold their index at the sizes offered.
- **Every fit counts.** Each sample is fitted by the same projection as the reported fit, on the average of the replicates that fit used, so its Ka is the best the model can do for its perturbed inputs — and every sample is kept, however poorly it describes the data. Dropping the poor ones would remove exactly the input combinations your data disagree with and bias the spread towards the inputs as entered.
- **Reading it.** A total-order index near zero, whisker included, means that for the uncertainty you gave it, that input's share is too small to measure here — which is not the same as none. A total-order index well above the first-order one means the input acts through combinations with others; drawn below it, the input acts almost entirely on its own and either estimate can come out on top in any run. Whiskers that clearly stand apart settle which of two inputs matters more; overlapping whiskers are a conservative sign: two 95 % intervals can overlap while the difference between the indices is still significant, so their order may hold — a larger sample size decides it.

### Reproducibility

A fit draws no random numbers: the same data, conditions and bounds give the same result on every machine and every run, so a reported Ka can be reproduced from the file it came with. Only the sensitivity analysis samples, and it has one root seed fixing the Sobol' scrambles; the seed is printed under the run's plots and so is carried in the saved picture of the tab. Exported results carry a fingerprint of the measured values, which is what lets *Import Results* refuse numbers that were fitted to other data, and which equilibrium arithmetic scored them, so a file written by an earlier version is checked with the arithmetic that wrote it and its R², RMSE and fit curve are recomputed with the present one where the two differ.

### Identifiability note

In the 4-parameter signal model, the coefficients `I0`, `I_dye_free`, and `I_dye_bound` are **structurally degenerate** for DBA and IDA — only `Ka` is uniquely identifiable from a single titration. The app fits the full 4-parameter model because it reconstructs the observed signal faithfully, but only `Ka` should be reported as a physical constant across datasets. The app marks this where it happens: it measures which parameters lie in a direction the data do not fix, and stars those rows in the summary, the text report and the CSV. Fixing the signal coefficients with a dye-alone calibration (see [data/Readme.md](data/Readme.md)) breaks the degeneracy when stronger constraints are needed.

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

- `numpy`, `scipy` — numerics: bounded linear least squares, root finding, F distribution, Sobol' sequences
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
