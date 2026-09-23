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

To try the app immediately without loading your own data, click **Demo IDA** in the toolbar — it loads a bundled IDA dataset and fits it with typical input uncertainties (`Ka_dye` σ 10 %; `[Host]₀`, `[Dye]₀` and the titrant σ 3 % each), which the status bar lists and the **Input Uncertainty** panel shows.

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
3. Under the conditions, say whether the fixed concentrations **stay constant** during the titration — samples made up to the same volume, or the titrant stock prepared in the sample solution — or **are diluted by each addition of titrant**. Diluted asks for the titrant stock concentration, and for an assay with two fixed concentrations lets you tick one the stock itself holds at the sample's own concentration. The concentrations in your data file are the titrant concentrations *in the cuvette after each addition*; if yours were computed without dilution, `x_nominal`, convert them with `x = x_nominal · c_T / (c_T + x_nominal)`.
4. In the **Input Uncertainty** panel, say how well you know each of those numbers and the titrant concentrations — a σ or a plain range, in percent of the entered value or in the input's own unit. Every row starts at **fixed**, which takes the input as exact. State an uncertainty and the fit may move that input within it: the reported interval then covers that freedom too, and the same statement feeds the Ka Sensitivity tab. Under the input rows you can add a **shared error source** — one stock, one balance, one pipette behind two or more inputs, which then move together by the same fraction — and state the **random error of each addition** of titrant, which the sensitivity analysis uses.
5. In the **Bounds** panel, review or tighten the parameter bounds. Defaults cover a wide physically reasonable range; narrower bounds produce better-conditioned fits when prior information is available.
6. In the **Fit Configuration** panel, decide whether to **fit each replicate separately**. The reported fit is the fit of the average of the replicates used either way — for replicates of equal scatter that average *is* their joint least-squares fit. With the box ticked, the app additionally fits every replicate on its own, reports what each one gives for the association constant, and leaves a replicate out of the average when its own fit needs a different Ka than the others share, or when its points scatter about its own fit far more than the others' do.
7. Optionally use the **Outlier Removal** panel to drop noisy replicates via a modified Z-score filter (default threshold 3.5, MAD-based).
8. Click **Run Fit**. Fitting runs off the main thread, and results appear in the plot and summary panel when it finishes. With every input fixed a fit takes a fraction of a second; letting inputs move costs one to two seconds typically, and up to about twenty on a hard design with few points — forty-five for the stepwise models, which have two association constants to profile. While a fit runs, the same button reads **Cancel Fit** and stops it; the tab keeps what it showed before.

See the [Scientific background](#scientific-background) below for how each of these configuration options maps onto the underlying physics.

### 3. See how tightly the data pin Ka down

The **Identifiability** tab profiles each association constant of the fit in the plot: across the Ka bounds in force it draws the best R² any fit can reach with that Ka held at each value, and marks the 95 % confidence interval — every Ka whose fit is not measurably worse than the best one. A narrow band means the data fix Ka; a flat curve over decades means they do not. When the band runs into a Ka bound the tab says so: the data place no limit on Ka on that side, and the honest report is a limit rather than a value.

State an uncertainty for an input and the tab draws a second curve, *with input uncertainties*: at each Ka the fit may also move those inputs inside what you stated, so that curve runs at or above the first one and its band — the interval the app reports — is usually the wider of the two. The curve with every input held as entered stays underneath it, so you can read off what the inputs cost.

For the stepwise models, which have two association constants, each one gets its own profile — drawn with the other constant refitted at every point, so the curve shows what the data say about that constant alone — and a third panel maps the joint 95 % region of the pair. The two constants trade off against each other, so the region is not the rectangle the two intervals span: it reaches further along the direction in which one constant compensates the other, and it rejects pairs that each interval on its own allows. Whether a *pair* of values is compatible with the data is the region's answer, not the two intervals'.

The curves describe the average of the replicates the fit used, and they assume the model is right and the conditions you entered are right to within the uncertainty you stated for them — exactly right, where you stated none. Where two or more replicates showed how the noise varies with the signal, the vertical axis is a **weighted R²**, which counts each titration point by how precise the replicates show it to be; the R² under Fit Quality counts every point equally, so the two are different numbers and the tab names the one it draws. The [Scientific background](#scientific-background) gives the mathematics; **Help ▸ Reading the plots** explains the display.

### 4. Read the verdict on the model and the inputs

A coloured line above the summary table gives the verdict in a few words — grey when there is nothing to act on, amber when something is worth checking, red when the result rests on something the data reject — and the same line is printed on the Fit Curve plot and its exported figure. Under the table, **Model and inputs** says what the fit found, in a sentence:

- whether the curve misses the data by more than the data's own scatter allows — measured against the replicates' scatter where you have two or more replicates, and otherwise from runs of residuals on one side of the curve along the titration;
- whether a shift of the inputs inside the uncertainties you stated turns a miss into a fit — in which case the reported interval already covers it;
- whether the data fit only with the inputs, taken together, further from the entered values than you said they could be. The shift printed against each error source says where the fit put the correction, not which stock is off: several inputs move the curve almost alike, so the statement is about the inputs together and the thing to do is check them all;
- or that the model does not describe the data even with the inputs free — the interval then assumes a model the data reject;
- or both of the last two, with the inputs named first: an input error can itself make the curve miss, so the inputs are the first thing to check.

When no test finds anything, the sentence says that no test found evidence against the model or the entered inputs — not that they are right — and names any test that could not run, with the reason: data with no scatter to judge a curve against, too few points, no input stated with a standard deviation, or no input direction the data inform.

The interval is reported in every case, with the sentence beside it.

### 5. Test what an error in your inputs would do

The **Ka Sensitivity** tab answers a different question: not how wide the uncertainty of Ka is, but where it comes from, and what a better input would buy. It uses the uncertainties from the **Input Uncertainty** panel — the same statement the interval rests on — and needs at least one error source that is not fixed. The app then refits your data many times with the inputs perturbed:

- **Sobol'** — every source moved at once. You get the spread of Ka, and Sobol' indices that split that spread among the sources. Sample sizes 1024, 2048 and 4096; a run costs `N × (g + 2)` fits for `g` reported sources, plus two refits per input for the elasticities.
- **Heatmap** — two inputs stepped over a grid, one fit per cell, so you can read the Ka surface and spot where the fit jumps to another solution.

What is ranked is an **error source**, of which there are three kinds: an input's own uncertainty; a **shared source** — one stock, balance or pipette behind two or more inputs, which then move together by the same fraction, and which is reported as the one item you can act on; and the **random error of each addition** of titrant, reported as a single item standing for every addition.

Under the index bars, each association constant gets an **uncertainty budget**: the spread the stated uncertainties leave log₁₀(Ka) with — in decades and as the factor Ka spreads by — split by source into an elasticity (percent of Ka per percent of the source), the share of the variance that source explains alone, that share as an absolute variance, and the spread that would be left if the source were exact. A **what-if** row asks what reducing one source would do, and answers it twice: by re-weighting the samples already fitted towards the narrower distribution, which assumes nothing about how Ka depends on the source, and from the variance the source contributes. The re-weighted answer is the spread the row states wherever enough samples carry it, with the formula behind it as the cross-check; where they do not, the formula states it and the row says why. No fit is run for a what-if.

The random error of each addition is listed and ranked with the other sources. The interval the fit reports does not include it. With *m* replicates it is drawn at σ/√*m*, which takes the replicates to be separate titrations, each pipetted on its own.

Every sample is fitted with its own perturbed inputs held exact, and the run's baseline is the fit at the inputs as entered, so the spread the tab shows is the effect of the stated uncertainties alone. Every sample is weighted by the noise law of the baseline fit: moving the entered inputs does not change what the replicates measured, so re-reading the law would return the same weights, and re-using them is what makes the baseline the sample with no offset. The analysis propagates the stated uncertainties (GUM Supplement 1): every draw counts the same, whereas the input-aware headline interval also weighs what the data say about the inputs, so the two can differ. A constant gets a reason in place of numbers when its fit at the entered inputs sits on a bound of its search range, when its conditional interval is open, or when its refits break the scaling identity described below.

The analysis is available for every assay that has an association constant, the stepwise 1:2 and 2:1 models included. A run prints the seed it used under its plots, so it can be repeated exactly by entering that seed under Fixed seed. **Preferences ▸ Processor cores to use** sets how many fits run side by side; the result is the same whatever you choose.

### 6. Export results

From the **File** menu:

- **Export Results (JSON)** — the fitted parameters, the confidence interval of every association constant, the fit at the entered inputs and its intervals beside it, where the fit put each error source, the verdict and the tests it was read from, the fit statistics, the noise law the replicates showed, the replicates used and left out, the source file, and a fingerprint of the measured values it was fitted to. Re-importable via *Import Results*, which first re-scores each result on the data loaded now — at the input shifts the file records — and refuses one whose fingerprint belongs to other data. With no data loaded, the stored numbers are shown unchecked. A file written by an earlier version imports too; it carries neither an interval nor a noise law, and the summary says so of each and asks for a new fit.
- **Export Results (TXT)** — human-readable report: the parameter table, the interval conditional on the entered inputs beside each association constant, what you stated for each error source and where the fit put it — with the inputs a shared source moves named beside it — the noise law the replicates showed, the verdict sentence, and the replicates the fit used and any it left out.
- **Export Results (CSV)** — one row per parameter: estimate, interval and its level, the conditional estimate and interval, the verdict and the test results, the replicate statistics, and the fit statistics with the noise law beside them; plus one row per error source that was allowed to move, holding its shift in percent of the entered value.
- **Export All…** — the artefacts above plus **Ka uncertainty budget (CSV)**: the budget table of the analysis on screen, one row per source and association constant, with the spread, the elasticity of every input and the run's seed.
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

#### Dilution by the titrant

Each addition of titrant adds volume, so unless the samples were made up to the same volume — or the titrant stock was prepared in the sample solution itself — every fixed concentration falls along the titration. You state which of the two happened under the conditions form; the diluted case asks for the titrant stock concentration `c_T` and nothing else.

No volumes are needed. A sample of volume `V₀` that has taken up a cumulative volume `W` of stock holds `x = c_T·W/(V₀+W)` of titrant, so the fraction of the final volume that came from the stock is `x/c_T` — and `x` is what the data file already holds. A fixed species the stock does not contain is therefore at `c·(1 − x/c_T)` at that point; one the stock carries at the sample's own concentration stays where it is, which is the checkbox beside the stock. The same algebra holds whether the additions went into one cuvette or each point was made up separately, so the mode of preparation does not enter.

The convention for `x` is the titrant concentration **in the cuvette after each addition**. Concentrations computed without dilution — stock times volume added over the starting volume, `x_nominal` — convert with `x = x_nominal·c_T/(c_T + x_nominal)`.

Fitting diluted data with the totals held constant biases the association constant, by an amount and in a direction that depend on the assay and on how far the titration dilutes: nothing but the exact model removes it, and with the stock declared the model *is* exact. `python -m validation run dilution-coverage dilution-ignored` measures both — the coverage of the interval when the stock is declared, and the error left when it is not — and `validation/README.md` carries the tables.

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
- **Replicates** — the reported fit is the fit of the average of the replicates used, which for replicates of equal scatter is their joint least-squares fit. Their scatter also sets how much each titration point weighs in that fit, through the noise law of the next section. Fitting each replicate separately additionally reports what each one gives on its own — real between-replicate information — and leaves a replicate out of the average when its own fit needs a different Ka than the others share or its scatter is far larger than theirs. The Ka test is a forward search from a clean start: it begins with the majority of replicates whose own Ka lie nearest the median, so a minority that shares a wrong Ka cannot pull the fit its way and push a good replicate out, and adds back the others one at a time, each judged by an F test against the shared fit of those already in; a replicate in the set that the test then rejects leaves again (Hadi & Simonoff 1993). The scatter test is Cochran's C (ISO 5725-2) on the replicates' own residual variances. Both work at a family-wise 1 % (the ISO 5725-2 outlier level), the Ka test spread over the replicates given, Cochran's over the replicates still in it. Half of the replicates or more are never removed, it takes at least three replicates to test them, and the report names every replicate left out and why.
- **Replicate outlier removal** — the optional Z-score preprocessing step uses a *modified* Z-score based on the median and MAD, so it is not biased by the very outliers it is trying to flag.

How precisely the data determine Ka is the interval, described next — first with the entered conditions taken as exact, then with the uncertainty you state for them carried into it. Whether the model and those conditions describe the data at all is what the diagnostics after that report, and which input the uncertainty comes from is what the sensitivity analysis answers.

### How precise each point is — the noise law the replicates show

A titration measured twice differs in two ways: the noise of each measurement, and an overall difference between the runs — a lamp, a gain, a background. The second is not noise about the fitted curve. An affine image `α + β·signal` of any model here is a member of the same model, because the offset and the signal coefficients absorb it, so a replicate lying 3 % high is a curve the fit follows rather than one it misses. What is left once a replicate is put on its own best line in the mean curve is its noise, so the law is read from the scatter of each replicate about its own line in the mean curve — not from the raw spread of the replicates at each point, which counts a difference in gain as imprecision.

One number is read from that scatter: the **share** of the variance, at the root-mean-square signal, that grows with the signal rather than staying flat. It is the shape parameter of the two-component law

```
var(y) = a² + (b · y)²
```

a constant floor `a` plus a part proportional to the signal (Rocke & Lorenzato 1995, the standard model of analytical chemistry). Three properties make it the law to read here rather than a power of the signal: it contains constant noise, noise proportional to the signal and every mixture of the two exactly; its share lies in `[0, 1]` by construction, because neither variance can be negative, so nothing has to be clipped at a chosen value; and the signal enters squared, so a blank-subtracted point at or below zero — which the low end of a titration can be — is harmless, where a power of the signal is not defined at all.

The share reported is the one that makes the scatter flattest along the titration once it is whitened by the variance that share implies. Each replicate is detrended and weighted at the same share it is judged at, and the share is chosen to minimise the spread of the logarithm of the whitened scatter — on a log scale because that spread does not depend on how large the noise is, and because a least-squares fit of logarithms is not carried away by the single wild value a real titration has. A whole replicate that runs apart from the others is another matter: it raises the scatter at every point it touches, and the law is read from exactly the replicates the fit uses, so a replicate that **Outlier Removal** drops changes the law along with the fit. The whole range of shares is covered on a grid before the minimum is refined, since with a handful of replicates the objective need not have one basin. Nothing in it draws a random number: the same replicates always give the same law.

What the fit gets is one weight per titration point,

```
w = 1 / ((1 − share) + share · ȳ² / ref²)
```

with `ȳ` the mean signal at that point and `ref` its root-mean-square along the titration, so the weight is 1 at the rms signal and a point the replicates show to be twice as precise counts four times. The weights are computed once, from the measured means, before the fit: there is no reweighting loop, and the fit, both profiles, both intervals, the two diagnostics and every sensitivity sample are the same code path run with the same weights. Their size is bounded by the law: below a share of one no weight exceeds `1/(1 − share)`, and only at a share of exactly one — noise strictly proportional — does the ratio of the largest weight to the smallest reach the square of the ratio of the largest mean signal to the smallest, which is the weight a point at 1 % of the top signal should carry when the noise really is proportional down to there. Nothing floors the weights, and nothing needs to: constant noise at such a point leaves its whitened scatter at a share of one larger than the others by that same factor, which the estimator charges and so stops short of one — exactly where a floor would have acted.

The size of the noise — `a` in signal units and `b` as a percent of the signal — is reported and enters no inference: the F test of the interval profiles the noise level out, so only the shape of the variance reaches the fit. The **Fit Quality** box, the text report and the CSV export carry the law as one sentence, of the form `about 1.1 % of the signal plus 890 a.u. (scatter of 8 replicates about the curve)`.

Where no law can be read the app says so and counts every point equally:

- **a single titration** — `Noise: taken as constant — one titration cannot show how the noise varies with the signal.` A dozen points and three or four parameters do not determine a variance function from the residuals of the fit itself, and a guessed one would be the larger error. The fit is then the unweighted fit exactly, to the last digit, and where such data really do have noise proportional to the signal the interval is the one a constant-variance F test gives.
- **replicates that scatter at too few titration points** — `Noise: taken as constant — the replicates scatter at too few titration points to show how it varies.`

Two numbers are called R², and the app keeps them apart. The R² and the RMSE under **Fit Quality** are what their labels say — unweighted, in signal units, against the averaged data — so they stay comparable across fits. The vertical axis of the **Identifiability** tab is the surface the fit actually minimises, weighted by the same law; where a law was read the tab calls that axis *weighted R²* and its caption says that the two count the titration points differently.

`python -m validation run noise-law-coverage noise-law-lof-null noise-law-aware noise-law-conflict-null` measures what the weighting delivers — the coverage of both intervals under constant, proportional and mixed noise, with two to four replicates and with replicates that differ by a scale factor, and the false-alarm rates of the two diagnostics on such data — and `validation/README.md` carries the tables.

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
- the scatter about the model is independent from point to point and varies with the signal as the replicates showed it does — of about the same size across the titration wherever no noise law could be read.

**Replicates are averaged, not pooled.** The profile, the best fit and the interval describe the average of the replicates the fit used. Replicates of one titration depart from the model together — the same systematic miss appears in each — so counting their points as independent evidence counts one shared miss as many independent observations, narrowing the interval — by up to about √(number of replicates) where that miss dominates the scatter — and claiming a precision the experiment does not have. `python -m validation run replicate-pooling` measures that comparison across the assays, with each kind of scatter a row of its own — independent noise, noise that scales with the signal, and replicates sharing a smooth systematic departure from the model, the case the averaging protects against — and `validation/README.md` carries the table.

### When the inputs are not exact — the input-aware interval

`[Host]₀` is a weighing and a dilution; the titrant stock is a dilution too; `Ka_dye` is the estimate of an earlier fit. The interval above takes all of them as exact. State what you know about them in the **Input Uncertainty** panel and they become parameters of the fit, held by what you stated rather than pinned:

- a **σ** — the input may take any value, but moving it by a fraction `e` of what you entered costs `(e/σ)²` in the fit's objective: one σ is cheap, three σ is not;
- a **range** — every value between the ends is equally acceptable to the fit and none outside;
- **fixed** — the input is not a parameter at all, which is how every row starts.

Those three describe the error an input has **alone**. An error several inputs have in common — their solutions come from one stock, were weighed on one balance, were pipetted with one pipette — is stated once, as a named **shared source** with a σ in percent and the inputs it moves. The sources are independent and multiply, so an input written `entered × Π(1 + eₛ)` over the sources `s` that load it carries every one of them; a source loading only one input is that input's own entry. The fit treats a shared source exactly as it treats an input's own σ: one more parameter, held by its own penalty, costing a fraction of a residual degree of freedom. What changes is that one correction now moves several inputs together, which is what the experiment did.

That distinction is not cosmetic. A source common to **every** concentration of a direct-binding assay lies along a direction the data cannot see at all — by the scaling identity below, multiplying every concentration by `1+e` and dividing every binding constant by it leaves the least-squares problem unchanged — so the profile of Ka becomes the conditional profile widened by that source's own distribution: the reported interval carries the stock's uncertainty in full, and no amount of data narrows it. Entered as separate per-input errors instead, the same physical stock error would be shared out among inputs the data *can* separate, and the interval would come out too narrow. `python -m validation run shared-source-coverage` measures the coverage of the interval when the entered values really are drawn from a model with a shared source, and `validation/README.md` carries the table.

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

- **Does the curve miss the data by more than their scatter allows?** With two or more replicates, the scatter of each replicate about its own line in the mean curve is an estimate of the noise that owes nothing to the model, and the lack-of-fit F test compares the misfit of the fitted curve against it, each point counted by the weight its noise law gives it. Taking the raw spread of the replicates for noise instead would count a replicate measured at a slightly different gain as imprecision, which inflates the estimate until the test can no longer fire on real replicated data. With a single replicate there is no such estimate, so the judgement falls to a runs test on the *signs* of the residuals along the titration: a systematic miss leaves long runs of one sign. The reference is the fitted model's own — residuals of a fitted curve alternate more than independent ones, and treating them as exchangeable makes the test reject almost nothing. Measured on 4 800 fits of correct models, the runs test raises a false alarm in 2.3–5.6 % of them at the 5 % level (8 to 30 points), and detects a 15 % error in the titrant scale in 13–35 %.
- **Did the inputs have to move further than you said they could?** The shifts, each in units of its own stated σ, are summed along the directions the data actually inform — `q`, compared against the distribution it has when the entered inputs are consistent with their stated uncertainties. Directions the data cannot see are left out: along them the fit's shift is arithmetic, not evidence. Over a sweep of 7 500 fits whose inputs were entered exactly as well as they were stated (8 to 30 points) the test can be run at all on about half of them — on the rest the data inform no direction, and the report says so rather than passing the inputs. Among those it can judge, it rejects 3.1–5.6 % of the one-constant fits at the 5 % level, and 6.4 and 7.8 % of the two stepwise models; with the inputs entered three σ off it flags 7–34 %.

Both tests are run at the fit with the inputs as entered and at the fit with them free, which is what separates *the inputs explain the miss* from *the model does not fit whatever the inputs do*. The verdict is one of: no test found evidence against the model or the entered inputs (a test that could not run is named with the reason); the data fit once the inputs move within what you stated; the inputs together are further from their entered values than you stated; the curve misses the data by more than their scatter allows whatever the allowed shifts; or both of the last two, with the inputs named first. The two tests share one 5 % level between them by Holm's procedure instead of taking 5 % each; the p-values printed are each test's own. Holm keeps the pair at 5 % only as far as each test holds its own level, so the rate at which the verdict blames a correct model or correct inputs is measured, not assumed: the validation check `verdict-false-alarm` reports it. The interval is reported in every case, with the sentence beside it saying what to check next.

**A conflict is a statement about the inputs together.** The data on a titration usually determine one or two *combinations* of the inputs — `[Host]₀` and the titrant scale move the curve almost alike — so the shift printed against each input says where the fit put the correction, not which stock is wrong. A conflict can be significant with every individual shift under one σ. The app words it that way throughout, and the thing it asks for is a check of the stated inputs, not of one of them.

### How much your inputs matter — Ka sensitivity and the uncertainty budget

The interval says how wide the uncertainty of Ka is. The **Ka Sensitivity** tab says where it comes from and what a better input would buy: it draws the error sources from the same **Input Uncertainty** panel and refits the data over that distribution, so you can see what a pipetting error, a shared stock or a `Ka_dye` carried over from an earlier fit does to your result.

- **What is varied.** One offset per **source**, not per input: an input's own uncertainty, a named source shared by several inputs, and — when you state one — the random error of each titrant addition. A σ draws from a normal distribution truncated so the value stays positive, a range uniformly between its ends. An input loaded by several sources takes the product of their factors. The titrant's own entry is one common factor over the whole series, the way a mis-calibrated stock affects every point at once; when the stock is declared it scales with the titrant, because the titrant's scale error *is* the stock's concentration error.
- **Design.** A Saltelli design — matrices `A` and `B` plus one matrix per reported source that takes that source's columns from `B` — evaluated at `N × (g + 2)` fits for `g` reported sources. First-order indices use the Saltelli (2010) estimator and total-order indices the Jansen (1999) estimator, both on the variance of log₁₀(Ka), which is the scale on which an association constant varies. The random error of each addition is one offset per titration point, and those columns are taken from `B` **together**: the estimators then give the closed first-order and the total index of that group (Jacques et al. 2006), so pipetting is ranked as one item at a cost of `N` fits however many points the titration has.
- **The budget.** The same run read as absolute numbers. `V = Var(log₁₀ Ka)` over the design's own `A` and `B` rows is the spread the stated uncertainties leave the constant with; `Vᵢ = S₁ᵢ·V` is what one source contributes, and `√(V − Vᵢ)` is what would be left if that source were exact — which is the *first-order* index's question, by the law of total variance `E[Var(Y | eᵢ)] = V(1 − S₁ᵢ)`. Every one of those carries its own 95 % interval from the same delete-one-block jackknife as the indices; the interval of `Vᵢ` is not the interval of `S₁ᵢ` times `V`, because `V` has a sampling error of its own. What no single source explains alone — `1 − Σ S₁ᵢ` — is reported as *interactions*, with its sign, because it is an estimate.
- **What-if.** Reducing source `i` from σ to `rσ` gives `V′ = V − Vᵢ(1 − r²)`, exact when the source enters additively and linearly and first order otherwise. The same question is answered a second way with no fits and no such assumption, by importance re-weighting: each sample is re-weighted by the ratio of the narrower sampling density to the one it was drawn from, and the spread recomputed. Re-weighting only ever narrows a distribution, so only reductions are offered; it is available only where at least 200 samples effectively carry the weight, and not at all for the per-addition item, where a product of one weight per point collapses. Where it is available it is the spread the row states and the formula is the cross-check behind it: `what-if-accuracy` measures the re-weighted value against a second analysis at the reduced uncertainty at a relative error of rms 0.9–1.5 %, against the formula's rms 5–15 %. The 200 is where the two meet — a variance re-weighted from m samples carries a relative error of about √(2/m), 10 % at 200 — so below it the formula states the spread and the row says why the re-weighted value is missing.
- **Elasticities.** Beside the shares, `d ln Ka / d ln input` for every perturbable input — percent of Ka per percent of the input — from two refits per input at a small step either side. A source's elasticity is the sum over the inputs it loads, so a source whose inputs pull Ka in opposite directions shows a small one: the cancellation is visible rather than implied.
- **Sampling error of the indices.** The design is built from eight independently scrambled Sobol' blocks. Leaving each block out in turn gives a delete-one-block jackknife standard error, and the whiskers on the index chart are the estimate ± t(7, 0.975) × that error. They cover the Monte Carlo sampling error of one index — *not* error in the uncertainties you stated, nor in the model. Blocking costs accuracy: at a fixed budget, splitting the design into eight blocks raises the root-mean-square error of an index by up to a factor of about five, index by index — a few indices are barely affected — over one undivided scramble of the same size. That is the price of being told how far an index can be trusted. The accepted sample sizes start at 1024 because an index there already carries about the error of one undivided scramble of 512; below that the indices are too coarse to rank the sources by. `python -m validation run sobol-blocking sobol-coverage budget-coverage source-variance-exact what-if-accuracy` measures the blocking price, how often the whiskers hold their index, and whether the budget, the grouped index and the what-if hit the values they claim.
- **Every fit counts.** Each sample is fitted by the same projection as the reported fit, on the average of the replicates that fit used, with its own drawn inputs held exact, so its Ka is the best the model can do for them — and every sample is kept, however poorly it describes the data. Dropping the poor ones would remove exactly the input combinations your data disagree with and bias the spread towards the inputs as entered. The run's baseline is that same projection at the inputs exactly as entered, the fit the summary shows as conditional on the entered inputs.
- **Reading it.** A total-order index near zero, whisker included, means that for the uncertainty you gave it, that source's share is too small to measure here — which is not the same as none. A total-order index well above the first-order one means the source acts through combinations with others; drawn below it, the source acts almost entirely on its own and either estimate can come out on top in any run. Whiskers that clearly stand apart settle which of two sources matters more; overlapping whiskers are a conservative sign: two 95 % intervals can overlap while the difference between the indices is still significant, so their order may hold — a larger sample size decides it.

#### The scaling identity, and why some errors cancel

Every binding model here is built from mass balances and association constants of unit M⁻¹ alone. Multiply every concentration — the fixed totals, the titrant, the titrant stock — by `c` and every *entered* binding constant by `1/c`, and every species concentration is multiplied by `c`; the signal coefficients (au/M) absorb the `1/c`, the offset is untouched, and the least-squares problem is the one you started from with every fitted constant divided by `c`. Differentiating that at `c = 1` gives, for each fitted constant, an identity the elasticities must satisfy:

```
Σ (concentration inputs) sⱼ − Σ (entered binding constants) sⱼ = −1
```

So for IDA, `s_[Host]₀ + s_[Dye]₀ + s_titrant − s_Ka_dye = −1`, and for GDA the same with `[Guest]₀` in place of `[Dye]₀`; for both DBA directions, `s_fixed + s_titrant = −1`; for the stepwise models, `s_[Host]₀ + s_titrant = −1`, separately for each of the two constants.

It has two consequences worth acting on. In a **competitive** assay (IDA, GDA) an error common to every concentration has elasticity exactly `s_Ka_dye − 1`, so it cancels only as far as the elasticity to `Ka_dye` is close to 1, which holds when the dye binds strongly and not in general: the Elasticity column shows the value for your data. If `Ka_dye` was itself measured with the same stock, that error moves `Ka_dye` the other way, and the source's elasticity is then exactly `−1`, as in direct binding. In **direct binding** (DBA, and the stepwise models) the same error has elasticity exactly `−1`: a 1 % error in the concentration scale is a 1 % error in Ka, and no amount of data removes it. The app does not display the identity — it is a property of the models, not a measurement of your data — but every Sobol' analysis checks its own elasticities against it and withholds the numbers of a constant whose refits miss it, and it is what makes the elasticity column read as physics rather than as a number.

### Reproducibility

A fit draws no random numbers — the noise law read from the replicates included: the same data, conditions, bounds and input uncertainties give the same result on every machine and every run, so a reported Ka can be reproduced from the file it came with. The reference distributions the two diagnostics are read against are Monte Carlo quadratures at a fixed seed, which makes each p-value a function of the fit like any other computed number. Only the sensitivity analysis samples the inputs, and it has one root seed fixing the Sobol' scrambles; the seed is printed under the run's plots and so is carried in the saved picture of the tab. Exported results carry a fingerprint of the measured values, which is what lets *Import Results* refuse numbers that were fitted to other data, and which equilibrium arithmetic scored them, so a file written by an earlier version is checked with the arithmetic that wrote it and its R², RMSE and fit curve are recomputed with the present one where the two differ.

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

### The noise of the measurement

14. Rocke, D. M., & Lorenzato, S. (1995). A two-component model for measurement error in analytical chemistry. *Technometrics*, 37(2), 176-184. <https://doi.org/10.1080/00401706.1995.10484302>
15. Carroll, R. J., & Ruppert, D. (1988). *Transformation and Weighting in Regression*. Chapman & Hall/CRC. <https://doi.org/10.1201/9780203735268>
16. Davidian, M., & Carroll, R. J. (1987). Variance function estimation. *Journal of the American Statistical Association*, 82(400), 1079-1091. <https://doi.org/10.1080/01621459.1987.10478543>

### Uncertain inputs and model checking

17. Carroll, R. J., Ruppert, D., Stefanski, L. A., & Crainiceanu, C. M. (2006). *Measurement Error in Nonlinear Models: A Modern Perspective* (2nd ed.). Chapman & Hall/CRC. <https://doi.org/10.1201/9781420010138>
18. Hodges, J. S., & Sargent, D. J. (2001). Counting degrees of freedom in hierarchical and other richly-parameterised models. *Biometrika*, 88(2), 367-379. <https://doi.org/10.1093/biomet/88.2.367>
19. Draper, N. R., & Smith, H. (1998). *Applied Regression Analysis* (3rd ed.). Wiley. <https://doi.org/10.1002/9781118625590>
20. Wald, A., & Wolfowitz, J. (1940). On a test whether two samples are from the same population. *The Annals of Mathematical Statistics*, 11(2), 147-162. <https://doi.org/10.1214/aoms/1177731909>
21. Imhof, J. P. (1961). Computing the distribution of quadratic forms in normal variables. *Biometrika*, 48(3-4), 419-426. <https://doi.org/10.1093/biomet/48.3-4.419>

### Sensitivity analysis

22. Sobol', I. M. (2001). Global sensitivity indices for nonlinear mathematical models and their Monte Carlo estimates. *Mathematics and Computers in Simulation*, 55(1-3), 271-280. <https://doi.org/10.1016/S0378-4754(00)00270-6>
23. Saltelli, A., Annoni, P., Azzini, I., Campolongo, F., Ratto, M., & Tarantola, S. (2010). Variance based sensitivity analysis of model output. Design and estimator for the total sensitivity index. *Computer Physics Communications*, 181(2), 259-270. <https://doi.org/10.1016/j.cpc.2009.09.018>
24. Jansen, M. J. W. (1999). Analysis of variance designs for model output. *Computer Physics Communications*, 117(1-2), 35-43. <https://doi.org/10.1016/S0010-4655(98)00154-4>
25. Archer, G. E. B., Saltelli, A., & Sobol', I. M. (1997). Sensitivity measures, ANOVA-like techniques and the use of bootstrap. *Journal of Statistical Computation and Simulation*, 58(2), 99-120. <https://doi.org/10.1080/00949659708811825>
26. Owen, A. B. (1997). Monte Carlo variance of scrambled net quadrature. *SIAM Journal on Numerical Analysis*, 34(5), 1884-1910. <https://doi.org/10.1137/S0036142994277468>
27. L'Ecuyer, P., & Lemieux, C. (2002). Recent advances in randomized quasi-Monte Carlo methods. In *Modeling Uncertainty* (pp. 419-474). Springer. <https://doi.org/10.1007/0-306-48102-2_20>
28. Jacques, J., Lavergne, C., & Devictor, N. (2006). Sensitivity analysis in presence of model uncertainty and correlated inputs. *Reliability Engineering & System Safety*, 91(10-11), 1126-1134. <https://doi.org/10.1016/j.ress.2005.11.047>
29. Kahn, H., & Marshall, A. W. (1953). Methods of reducing sample size in Monte Carlo computations. *Journal of the Operations Research Society of America*, 1(5), 263-278. <https://doi.org/10.1287/opre.1.5.263>

### Replicates

30. Hadi, A. S., & Simonoff, J. S. (1993). Procedures for the identification of multiple outliers in linear models. *Journal of the American Statistical Association*, 88(424), 1264-1272. <https://doi.org/10.1080/01621459.1993.10476407>
31. Atkinson, A. C., & Riani, M. (2000). *Robust Diagnostic Regression Analysis*. Springer. <https://doi.org/10.1007/978-1-4612-1160-0>
32. Cochran, W. G. (1941). The distribution of the largest of a set of estimated variances as a fraction of their total. *Annals of Eugenics*, 11(1), 47-52. <https://doi.org/10.1111/j.1469-1809.1941.tb02271.x>
33. ISO 5725-2:2019. *Accuracy (trueness and precision) of measurement methods and results — Part 2: Basic method for the determination of repeatability and reproducibility of a standard measurement method*. International Organization for Standardization.

---

**Contact:** contact@suprabank.org
