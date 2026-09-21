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
3. In the **Input Uncertainty** panel, say how well you know each of those numbers and the titrant concentrations — a σ or a plain range, in percent of the entered value or in the input's own unit. Every row starts at **fixed**, which takes the input as exact. State an uncertainty and the fit may move that input within it: the reported interval then covers that freedom too, and the same statement feeds the Ka Sensitivity tab.
4. In the **Bounds** panel, review or tighten the parameter bounds. Defaults cover a wide physically reasonable range; narrower bounds produce better-conditioned fits when prior information is available.
5. In the **Fit Configuration** panel, decide whether to **fit each replicate separately**. The reported fit is the fit of the average of the replicates used either way — for replicates of equal scatter that average *is* their joint least-squares fit. With the box ticked, the app additionally fits every replicate on its own, reports what each one gives for the association constant, and leaves a replicate out of the average when its own fit needs a different Ka than the others share.
6. Optionally use the **Outlier Removal** panel to drop noisy replicates via a modified Z-score filter (default threshold 3.5, MAD-based).
7. Click **Run Fit**. Fitting runs off the main thread, and results appear in the plot and summary panel when it finishes. With every input fixed a fit takes a fraction of a second; letting inputs move costs one to two seconds typically, and up to about twenty on a hard design with few points — forty-five for the stepwise models, which have two association constants to profile. While a fit runs, the same button reads **Cancel Fit** and stops it; the tab keeps what it showed before.

See the [Scientific background](#scientific-background) below for how each of these configuration options maps onto the underlying physics.

### 3. See how tightly the data pin Ka down

The **Identifiability** tab profiles each association constant of the fit in the plot: across the Ka bounds in force it draws the best R² any fit can reach with that Ka held at each value, and marks the 95 % confidence interval — every Ka whose fit is not measurably worse than the best one. A narrow band means the data fix Ka; a flat curve over decades means they do not. When the band runs into a Ka bound the tab says so: the data place no limit on Ka on that side, and the honest report is a limit rather than a value.

State an uncertainty for an input and the tab draws a second curve, *with input uncertainties*: at each Ka the fit may also move those inputs inside what you stated, so that curve runs at or above the first one and its band — the interval the app reports — is usually the wider of the two. The curve with every input held as entered stays underneath it, so you can read off what the inputs cost.

For the stepwise models, which have two association constants, each one gets its own profile — drawn with the other constant refitted at every point, so the curve shows what the data say about that constant alone — and a third panel maps the joint 95 % region of the pair. The two constants trade off against each other, so the region is not the rectangle the two intervals span: it reaches further along the direction in which one constant compensates the other, and it rejects pairs that each interval on its own allows. Whether a *pair* of values is compatible with the data is the region's answer, not the two intervals'.

The curves describe the average of the replicates the fit used, and they assume the model is right and the conditions you entered are right to within the uncertainty you stated for them — exactly right, where you stated none. The [Scientific background](#scientific-background) gives the mathematics; **Help ▸ Reading the plots** explains the display.

### 4. Read the verdict on the model and the inputs

Under the summary table, **Model and inputs** says what the fit found, in a sentence:

- whether the curve misses the data by more than the data's own scatter allows — measured against the replicates' scatter where you have two or more replicates, and otherwise from runs of residuals on one side of the curve along the titration;
- whether a shift of the inputs inside the uncertainties you stated turns a miss into a fit — in which case the reported interval already covers it;
- whether the data fit only with the inputs, taken together, further from the entered values than you said they could be. The shift printed against each input says where the fit put the correction, not which stock is off: several inputs move the curve almost alike, so the statement is about the inputs together and the thing to do is check them all;
- or that the model does not describe the data even with the inputs free — the interval then assumes a model the data reject.

The interval is reported in every case, with the sentence beside it.

### 5. Test what an error in your inputs would do

The **Ka Sensitivity** tab answers a different question: not how wide the uncertainty of Ka is, but which input it comes from. It uses the uncertainties from the **Input Uncertainty** panel — the same statement the interval rests on — and needs at least one input that is not fixed. The app then refits your data many times with those inputs perturbed:

- **Sobol'** — every varied input moved at once. You get the spread of Ka, and Sobol' indices that split that spread among the inputs, so you can see which input your Ka actually depends on. Sample sizes 1024, 2048 and 4096; a run costs `N × (k + 2)` fits for `k` varied inputs.
- **Heatmap** — two inputs stepped over a grid, one fit per cell, so you can read the Ka surface and spot where the fit jumps to another solution.

Every sample is fitted with its own perturbed inputs held exact, and the run's baseline is the fit at the inputs as entered, so the spread the tab shows is the effect of the stated uncertainties alone. The headline interval on the Fit Curve tab already accounts for those uncertainties; this tab splits their effect between them.

The analysis is available for every assay that has an association constant, the stepwise 1:2 and 2:1 models included. A run prints the seed it used under its plots, so it can be repeated exactly by entering that seed under Fixed seed. **Preferences ▸ Processor cores to use** sets how many fits run side by side; the result is the same whatever you choose.

### 6. Export results

From the **File** menu:

- **Export Results (JSON)** — the fitted parameters, the confidence interval of every association constant, the fit at the entered inputs and its intervals beside it, where the fit put each input, the verdict and the tests it was read from, the fit statistics, the replicates used and left out, the source file, and a fingerprint of the measured values it was fitted to. Re-importable via *Import Results*, which first re-scores each result on the data loaded now — at the input shifts the file records — and refuses one whose fingerprint belongs to other data. With no data loaded, the stored numbers are shown unchecked. A file written by an earlier version imports too; it carries no interval, and the summary says so and asks for a new fit.
- **Export Results (TXT)** — human-readable report: the parameter table, the interval conditional on the entered inputs beside each association constant, what you stated for each input and where the fit put it, the verdict sentence, and the replicates the fit used and any it left out.
- **Export Results (CSV)** — one row per parameter: estimate, interval and its level, the conditional estimate and interval, the verdict and the test results, the replicate statistics, and the fit statistics; plus one row per input that was allowed to move, holding its shift in percent of the entered value.
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
- **What is reported** — the fit, and beside each association constant the 95 % profile-likelihood confidence interval described below: `Ka = estimate [low, high]`. The headline pair is the input-aware one wherever you state an uncertainty for an input, with the pair conditional on the entered inputs shown beside it; with every input fixed the two are the same numbers. An end the data do not close is written in words (`no upper limit`) rather than as a number, because a limit of the search is not a measurement. Signal coefficients that the data fix only in combination with each other are starred wherever they are listed: the combination reproduces the curve exactly, the individual values are not a result.
- **Replicates** — the reported fit is the fit of the average of the replicates used, which for replicates of equal scatter is their joint least-squares fit. Fitting each replicate separately additionally reports what each one gives on its own — real between-replicate information — and leaves a replicate out of the average when an F test says its own fit needs a different Ka than the others share, at a family-wise 1 % (the ISO 5725-2 outlier level, spread over the replicates given). Half of the replicates or more are never removed, and the report names every replicate left out and why.
- **Replicate outlier removal** — the optional Z-score preprocessing step uses a *modified* Z-score based on the median and MAD, so it is not biased by the very outliers it is trying to flag.

How precisely the data determine Ka is the interval, described next — first with the entered conditions taken as exact, then with the uncertainty you state for them carried into it. Whether the model and those conditions describe the data at all is what the diagnostics after that report, and which input the uncertainty comes from is what the sensitivity analysis answers.

### How precisely the data pin Ka down — the Ka profile

Sweeping one association constant across the bounds in force, and at each of its values solving the signal coefficients exactly and refitting any other association constant, gives the **profile**: the highest R² any fit can reach with that constant held there. It is the same projection the fit itself is made of, so the peak of the profile *is* the reported fit, to the last digit, and the curve bounds every fit of these data with that constant held at that value.

The **Identifiability** tab reads the confidence interval off that curve with an F test on the residual sum of squares:

```
SSR(Ka) ≤ SSR_min · (1 + m · F(level; m, n − p) / (n − p))
```

`m` counts the parameters the best fit has and the fit at the tested Ka has not. That is the tested Ka itself, so `m = 1` — the plain F test — wherever nothing else changes. The signal coefficients are fitted inside bounds (non-negative by default), and a fit at a Ka far from the best one often has to hold a coefficient *on* its bound that the best fit leaves free. A coefficient on its bound is not fitted, so that fit has given up two parameters, not one, and is judged with `m = 2`; each further coefficient it pins adds one. (The exact reference for a parameter on the boundary of its range is a mixture of F distributions with 1 to `m` numerator degrees of freedom — Self & Liang 1987 — so taking `m` errs on the wide side.) The count is the rank of the design columns whose coefficient lies inside its bounds, at the best fit minus at the tested Ka, never below zero. On the Identifiability tab the dotted cut-off line steps down where that happens. Judging such a Ka with `m = 1` rejects true values too often: for the 1:2 model with a weakly emitting species the nominal 95 % interval then holds the true Ka in as few as 88 % of synthetic titrations, against 93.5 % at worst — no scenario significantly below 95 % — with the count.

`n` is the number of points in the profiled signal and `p = (association constants fitted) + rank of the coefficient design` at the best fit — the number of parameters the data actually resolve. Equal Ka bounds pin that constant: it is then not fitted and contributes nothing to `p`. The rank is computed numerically, so a pinned coefficient (equal lower and upper bound) and a pair of columns the data cannot separate each count once, not twice; this matters because the signal coefficients are degenerate in DBA and IDA (see below). The interval is every Ka that clears the cut-off of its own fit, its edges found by root-finding on the exact curve. An edge that runs into a Ka bound is reported as open: the data stop nothing there, and the bound, not the measurement, is what ends the interval. With two association constants, so is an edge that exists only because the *other* constant has reached its bound: the report names that constant, and gives no limit on that side.

A model with two association constants gets one interval per constant, each read off that constant's own profile, and a **joint region** — the pairs whose fit clears the same test with two constrained constants, `m = 2` plus every coefficient the fit at that pair pins and the best fit leaves free. The two readings answer different questions: an interval is what the data say about one constant with the other free, the region is which *pairs* they allow. Reading the two intervals as a pair would claim both more and less than the data support — the region stretches beyond them along the direction the two constants trade off in, and excludes pairs that lie inside both.

What this interval assumes:

- the binding model is the right one for the system,
- the conditions you entered (`[Host]₀`, `[Dye]₀`, `Ka_dye`, the titrant concentrations) are correct — which is why it is the interval **conditional on the entered inputs**, and why the next section drops that assumption,
- the bounds in force are wide enough not to clip the answer,
- the scatter about the model is independent from point to point and of about the same size across the titration.

**Replicates are averaged, not pooled.** The profile, the best fit and the interval describe the average of the replicates the fit used. Replicates of one titration depart from the model together — the same systematic miss appears in each — so counting their points as independent evidence counts one shared miss as many independent observations, narrowing the interval — by up to about √(number of replicates) where that miss dominates the scatter — and claiming a precision the experiment does not have. On synthetic IDA data the interval delivers 96 % coverage for a nominal 95 % when the scatter is well behaved, 91 % when it scales with the signal, and 77 % when the replicates share a smooth systematic departure from the model — which is the case the averaging protects against, and where pooling the replicates' points instead drops coverage to 67 %. `python -m validation run replicate-pooling` measures that comparison across the assays, with each kind of scatter a row of its own, and `validation/README.md` carries the table.

### When the inputs are not exact — the input-aware interval

`[Host]₀` is a weighing and a dilution; the titrant stock is a dilution too; `Ka_dye` is the estimate of an earlier fit. The interval above takes all of them as exact. State what you know about them in the **Input Uncertainty** panel and they become parameters of the fit, held by what you stated rather than pinned:

- a **σ** — the input may take any value, but moving it by a fraction `e` of what you entered costs `(e/σ)²` in the fit's objective: one σ is cheap, three σ is not;
- a **range** — every value between the ends is equally acceptable to the fit and none outside;
- **fixed** — the input is not a parameter at all, which is how every row starts.

With the inputs written as `entered × (1 + e)` and the noise scale unknown, the fit's objective becomes `n · log SSR + Σ (e/σ)²` and the profile of one association constant is its minimum over everything else — the signal coefficients by the same exact bounded solve, any other association constant, and every input inside what you allowed it. The interval is read off that curve with the same F test as before, written on the log scale, with one change: an input the data can determine takes a residual degree of freedom out of the fit, one a σ merely constrains takes a fraction of one, so the test uses the **effective** residual degrees of freedom `ν = n − p − Σw` rather than `n − p`. The weights `w` between 0 and 1 are measured at the fit itself, from how much the data say about each direction the inputs can move in.

Two properties follow and are worth stating: with every input fixed the construction *is* the F-test interval above — the same numbers, the same object — and a stated σ driven to zero converges onto it. And the interval is usually wider, because the data now have to distinguish Ka from an input error that mimics it; it comes out narrower in a small minority of fits, where letting an input move explains a miss the entered values could not.

Coverage of the nominal 95 %, measured on about 6 000 synthetic titrations — GDA, IDA and both DBA directions, 5 to 20 points, noise of 0.5–3 % of the signal range and one scenario with noise proportional to the signal, `Ka·c` from 0.1 to 1000, four inputs stated at 3–10 % and every entered value drawn at exactly the σ stated for it:

| Assay | fits | input-aware | conditional on the entered inputs |
|---|---|---|---|
| GDA | 1440 | 0.986 | 0.926 |
| IDA | 1559 | 0.965 | 0.720 |
| DBA host→dye | 1440 | 0.958 | 0.801 |
| DBA dye→host | 1549 | 0.974 | 0.923 |

An interval left open at one end covers by construction, so the same figures over the fits whose interval is closed at both ends are 0.972 / 0.966 / 0.949 / 0.963 for the input-aware interval and 0.799 / 0.717 / 0.776 / 0.870 for the conditional one. The conditional interval is not wrong in these runs — it is answering the narrower question, and the gap is what taking the entered numbers as exact costs when they are not.

`python -m validation run input-aware-coverage` reproduces these figures — it draws each entered input at the uncertainty stated for it and reports both intervals' coverage, their widths and the verdicts — and `python -m validation run conflict-null conflict-power` the false-alarm and power curves of the check on the inputs described next.

Letting an input move needs points to pay for it: a fit is refused, in plain language naming the inputs, when what is left of the data cannot support both the model and the inputs it is asked to free (`ν < 1`). Holding one input at its entered value, or measuring more points, is what that message asks for.

### Whether the model and the inputs describe the data — the diagnostics

Every fit is also judged, and the verdict travels with the interval:

- **Does the curve miss the data by more than their scatter allows?** With two or more replicates, the scatter of the replicates about their mean is an estimate of the noise that owes nothing to the model, and the lack-of-fit F test compares the misfit of the fitted curve against it. With a single replicate there is no such estimate, so the judgement falls to a runs test on the *signs* of the residuals along the titration: a systematic miss leaves long runs of one sign. The reference is the fitted model's own — residuals of a fitted curve alternate more than independent ones, and treating them as exchangeable makes the test reject almost nothing. Measured on 4 800 fits of correct models, the runs test raises a false alarm in 2.3–5.6 % of them at the 5 % level (8 to 30 points), and detects a 15 % error in the titrant scale in 13–35 %.
- **Did the inputs have to move further than you said they could?** The shifts, each in units of its own stated σ, are summed along the directions the data actually inform — `q`, compared against the distribution it has when the entered inputs are consistent with their stated uncertainties. Directions the data cannot see are left out: along them the fit's shift is arithmetic, not evidence. Over a sweep of 7 500 fits whose inputs were entered exactly as well as they were stated (8 to 30 points) the test can be run at all on about half of them — on the rest the data inform no direction, and the report says so rather than passing the inputs. Among those it can judge, it rejects 3.1–5.6 % of the one-constant fits at the 5 % level, and 6.4 and 7.8 % of the two stepwise models; with the inputs entered three σ off it flags 7–34 %.

Both tests are run at the fit with the inputs as entered and at the fit with them free, which is what separates *the inputs explain the miss* from *the model does not fit whatever the inputs do*. The verdict is one of: the model and the entered inputs describe the data; they describe it once the inputs move within what you stated; the inputs had to go further than you allowed; or no allowed shift rescues the model. The interval is reported in every case, with the sentence beside it saying what to check next.

**A conflict is a statement about the inputs together.** The data on a titration usually determine one or two *combinations* of the inputs — `[Host]₀` and the titrant scale move the curve almost alike — so the shift printed against each input says where the fit put the correction, not which stock is wrong. A conflict can be significant with every individual shift under one σ. The app words it that way throughout, and the thing it asks for is a check of the stated inputs, not of one of them.

### How much your inputs matter — Ka sensitivity

The interval says how wide the uncertainty of Ka is. The **Ka Sensitivity** tab says where it comes from: it draws the inputs from the uncertainties stated in the same **Input Uncertainty** panel and refits the data over that distribution, so you can see what a pipetting error or a `Ka_dye` carried over from an earlier fit does to your result.

- **Sampling.** Each input is drawn independently: a σ from a normal distribution truncated so the value stays positive, a range uniformly between its ends. The titrant enters as one common factor — a single draw scales the whole concentration vector, the way a mis-calibrated stock affects every point at once.
- **Design.** A Saltelli design — matrices `A` and `B` plus the `k` matrices that take one column from `B` — evaluated at `N × (k + 2)` fits. First-order indices use the Saltelli (2010) estimator and total-order indices the Jansen (1999) estimator, both on the variance of log₁₀(Ka), which is the scale on which an association constant varies.
- **Sampling error of the indices.** The design is built from eight independently scrambled Sobol' blocks. Leaving each block out in turn gives a delete-one-block jackknife standard error, and the whiskers on the index chart are the estimate ± t(7, 0.975) × that error. They cover the Monte Carlo sampling error of one index — *not* error in the uncertainties you stated, nor in the model. Blocking costs accuracy: at a fixed budget, splitting the design into eight blocks raises the root-mean-square error of an index by up to a factor of about five, index by index — a few indices are barely affected — over one undivided scramble of the same size. That is the price of being told how far an index can be trusted. The accepted sample sizes start at 1024 because an index there already carries about the error of one undivided scramble of 512; below that the indices are too coarse to rank the inputs by. `python -m validation run sobol-blocking sobol-coverage` measures the blocking price, and how often the whiskers hold their index at the sizes offered.
- **Every fit counts.** Each sample is fitted by the same projection as the reported fit, on the average of the replicates that fit used, with its own drawn inputs held exact, so its Ka is the best the model can do for them — and every sample is kept, however poorly it describes the data. Dropping the poor ones would remove exactly the input combinations your data disagree with and bias the spread towards the inputs as entered. The run's baseline is that same projection at the inputs exactly as entered, the fit the summary shows as conditional on the entered inputs.
- **Reading it.** A total-order index near zero, whisker included, means that for the uncertainty you gave it, that input's share is too small to measure here — which is not the same as none. A total-order index well above the first-order one means the input acts through combinations with others; drawn below it, the input acts almost entirely on its own and either estimate can come out on top in any run. Whiskers that clearly stand apart settle which of two inputs matters more; overlapping whiskers are a conservative sign: two 95 % intervals can overlap while the difference between the indices is still significant, so their order may hold — a larger sample size decides it.

### Reproducibility

A fit draws no random numbers: the same data, conditions, bounds and input uncertainties give the same result on every machine and every run, so a reported Ka can be reproduced from the file it came with. The reference distributions the two diagnostics are read against are Monte Carlo quadratures at a fixed seed, which makes each p-value a function of the fit like any other computed number. Only the sensitivity analysis samples the inputs, and it has one root seed fixing the Sobol' scrambles; the seed is printed under the run's plots and so is carried in the saved picture of the tab. Exported results carry a fingerprint of the measured values, which is what lets *Import Results* refuse numbers that were fitted to other data, and which equilibrium arithmetic scored them, so a file written by an earlier version is checked with the arithmetic that wrote it and its R², RMSE and fit curve are recomputed with the present one where the two differ.

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
13. Self, S. G., & Liang, K.-Y. (1987). Asymptotic properties of maximum likelihood estimators and likelihood ratio tests under nonstandard conditions. *Journal of the American Statistical Association*, 82(398), 605-610. <https://doi.org/10.1080/01621459.1987.10478472>

### Uncertain inputs and model checking

14. Carroll, R. J., Ruppert, D., Stefanski, L. A., & Crainiceanu, C. M. (2006). *Measurement Error in Nonlinear Models: A Modern Perspective* (2nd ed.). Chapman & Hall/CRC. <https://doi.org/10.1201/9781420010138>
15. Hodges, J. S., & Sargent, D. J. (2001). Counting degrees of freedom in hierarchical and other richly-parameterised models. *Biometrika*, 88(2), 367-379. <https://doi.org/10.1093/biomet/88.2.367>
16. Draper, N. R., & Smith, H. (1998). *Applied Regression Analysis* (3rd ed.). Wiley. <https://doi.org/10.1002/9781118625590>
17. Wald, A., & Wolfowitz, J. (1940). On a test whether two samples are from the same population. *The Annals of Mathematical Statistics*, 11(2), 147-162. <https://doi.org/10.1214/aoms/1177731909>
18. Imhof, J. P. (1961). Computing the distribution of quadratic forms in normal variables. *Biometrika*, 48(3-4), 419-426. <https://doi.org/10.1093/biomet/48.3-4.419>

### Sensitivity analysis

19. Sobol', I. M. (2001). Global sensitivity indices for nonlinear mathematical models and their Monte Carlo estimates. *Mathematics and Computers in Simulation*, 55(1-3), 271-280. <https://doi.org/10.1016/S0378-4754(00)00270-6>
20. Saltelli, A., Annoni, P., Azzini, I., Campolongo, F., Ratto, M., & Tarantola, S. (2010). Variance based sensitivity analysis of model output. Design and estimator for the total sensitivity index. *Computer Physics Communications*, 181(2), 259-270. <https://doi.org/10.1016/j.cpc.2009.09.018>
21. Jansen, M. J. W. (1999). Analysis of variance designs for model output. *Computer Physics Communications*, 117(1-2), 35-43. <https://doi.org/10.1016/S0010-4655(98)00154-4>
22. Archer, G. E. B., Saltelli, A., & Sobol', I. M. (1997). Sensitivity measures, ANOVA-like techniques and the use of bootstrap. *Journal of Statistical Computation and Simulation*, 58(2), 99-120. <https://doi.org/10.1080/00949659708811825>
23. Owen, A. B. (1997). Monte Carlo variance of scrambled net quadrature. *SIAM Journal on Numerical Analysis*, 34(5), 1884-1910. <https://doi.org/10.1137/S0036142994277468>
24. L'Ecuyer, P., & Lemieux, C. (2002). Recent advances in randomized quasi-Monte Carlo methods. In *Modeling Uncertainty* (pp. 419-474). Springer. <https://doi.org/10.1007/0-306-48102-2_20>

---

**Contact:** contact@suprabank.org
