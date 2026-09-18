# Scientific Summary of the Molecular Binding Assay Fitting Toolkit

## 1. Introduction

This report provides a high-level overview of the scientific principles, mathematical frameworks, and algorithmic strategies employed by the Molecular Binding Assay Fitting Toolkit. The software is designed to analyze spectroscopic data from various molecular binding assays—specifically Guest Displacement Assays (GDA), Indicator Displacement Assays (IDA), and Direct Binding Assays (DBA). Its primary objective is to accurately quantify binding affinities (equilibrium constants) and physical response parameters (e.g., fluorescence coefficients) by fitting theoretical models directly to experimental observations.

## 2. Scientific Methodology: The Forward Modeling Approach

The core philosophy of this codebase is **Forward Modeling**. Traditional methods in supramolecular chemistry often rely on linearizing data (e.g., Scatchard or double-reciprocal plots) to extract binding constants. While computationally simple, these transformations distort the experimental error structure, leading to biased estimates and unreliable confidence intervals.

In contrast, this toolkit employs a direct non-linear regression approach:
1. **Model Prediction:** Based on a trial binding constant, the software simulates the exact concentrations of all chemical species at equilibrium.
2. **Signal Simulation:** It then calculates the expected physical signal (e.g., fluorescence intensity) corresponding to these concentrations.
3. **Optimization:** The signal parameters that best match the raw experimental data at that binding constant are obtained in closed form, and the binding constant itself is chosen by covering its whole allowed range (Section 4.1).

This approach preserves the native error distribution of the measurement, allows for the application of rigorous physical constraints (e.g., ensuring concentrations are non-negative), and enables the analysis of complex competitive systems that do not lend themselves to simple linearization.

## 3. Mathematical Framework

The mathematical engine of the toolkit is built upon the fundamental laws of chemical thermodynamics and mass conservation.

### 3.1. Law of Mass Action

The interactions are modeled as reversible equilibrium processes. For a simple 1:1 binding event between a Host ($H$) and a Guest ($G$), the equilibrium is governed by the association constant ($K_a$) or dissociation constant ($K_d$):
$$ H + G \rightleftharpoons HG $$
$$ K_a = \frac{[HG]}{[H][G]} $$

### 3.2. Mass Balance Equations

To solve for the unknown free concentrations ($[H]$, $[G]$) required by the mass action law, the software utilizes mass balance equations. These equations state that the total concentration of a species (a known experimental input) is the sum of its free form and its bound forms.

- **Direct Binding:** Leads to a system of equations that can be reduced to a **quadratic equation**, allowing for an analytical solution for the complex concentration.
- **Competitive Binding (GDA/IDA):** Involves two competing equilibria (Host-Dye and Host-Guest). This results in a more complex system that reduces to a **cubic equation** with respect to the free host concentration. Unlike the quadratic case, this often requires numerical solution methods to ensure stability and physical validity.

### 3.3. Signal Response Model

The observable signal ($I$) is modeled as a linear combination of the contributions from all active species. For a fluorescence assay, this follows the additive property of intensity:
$$ I = I_0 + \sum I_i [C_i] $$
Where $I_0$ is the background signal, $[C_i]$ is the concentration of species $i$, and $I_i$ is its molar response factor (e.g., brightness).

**Connecting Parameters to Measurement Data:**
The signal equation provides the critical link between the chemical model and the experimental data. The concentrations $[C_i]$ are determined by the binding constants ($K_a$) via the mass balance equations. Thus, the calculated signal depends directly on the unknown parameters ($K_a, I_i$). The fitting process simply adjusts these parameters until the calculated signal matches the measured data.

The process works as a chain of dependencies:
1. **A candidate binding constant:** one value of $K_a$ from the range the bounds allow.
2. **Chemical Equilibrium:** Using that $K_a$ and the known total concentrations of reagents, the mass balance equations are solved to determine the exact equilibrium concentration $[C_i]$ of every species in the solution.
3. **Signal Prediction:** Those concentrations are the columns of the signal equation above, so the molar response factors $I_i$ that come closest to the measured data ($I_{obs}$) follow from a linear least-squares solve — no guess and no iteration.
4. **Comparison:** The residual that remains is the price of that $K_a$.
5. **Search:** Steps 1–4 are repeated across the whole allowed range of $K_a$ and refined around the best candidates. The $K_a$ with the smallest residual, and the response factors solved with it, are the best estimates.

## 4. Algorithmic Implementation

The toolkit integrates several classes of algorithms to solve the inverse problem of finding parameters that best explain the measurement data.

### 4.1. The Fit: Variable Projection

Every registered binding model is **separable**: with the association constants $K$ held fixed, the equilibrium solve fixes every species concentration, and the signal is linear in the remaining parameters,

$$\mathbf{y} = A(K)\,\mathbf{c} + \mathbf{e}$$

where the columns of $A(K)$ are a column of ones for the offset $I_0$ and the species concentration each signal coefficient multiplies, and $\mathbf{c}$ collects the signal parameters. Only $K$ — one association constant for GDA, IDA and both DBA directions, two for the stepwise 1:2 and 2:1 models — enters nonlinearly. The fit is therefore split (Golub & Pereyra 1973, 2003):

$$S(K) \;=\; \min_{\mathbf{lb}\,\le\,\mathbf{c}\,\le\,\mathbf{ub}} \lVert \mathbf{y} - A(K)\,\mathbf{c} \rVert^2, \qquad \hat{K} = \arg\min_K S(K), \quad \hat{\mathbf{c}} = \mathbf{c}(\hat{K})$$

and $(\hat{K}, \hat{\mathbf{c}})$ is the least-squares fit of the full model.

- **The linear part is solved.** At a given $K$ the best coefficients inside their bounds are a bounded-variable least-squares problem, solved exactly (`scipy.optimize.lsq_linear`, method `bvls`). Columns are scaled to unit norm first, which keeps coefficients spanning many orders of magnitude well conditioned; a coefficient with equal bounds leaves the solve and contributes a fixed signal. There is no starting point and nothing to converge.
- **The nonlinear part is searched exhaustively.** What is left is $S$ over one or two decades-wide axes of $\log_{10} K$. It is evaluated on a grid of at least four points per decade across the bounds in force, and the best grid points are refined — a bounded Brent search between the neighbours of the best node for one constant, and for two constants a trust-region least-squares refinement of the projected residual, started from the five best local minima of the grid and free to move anywhere in the box. Against a 16-per-decade brute force on 84 random two-constant designs (constants $10^1$–$10^9$ M⁻¹, host $10^{-6.5}$–$10^{-3}$ M, 8–30 points, 0.2–8 % noise) this search was never beaten by more than $1.2\times10^{-6}$ in relative SSR; with a single refinement the worst miss is $3.4\times10^{-5}$, still far below the $\ge 0.1$ relative SSR that separates the interval's threshold from the optimum.
- **Why exhaust the range rather than start somewhere.** The residual as a function of $K$ can have more than one basin, and the isotherm responds to $\log K$ on a scale of about half a decade, so four points per decade put a node inside every basin with room to spare — which is what the brute-force comparison above measures. The fit is then a property of the data and the bounds alone: it draws no random numbers, and the same input gives the same answer on every run and every machine.
- **Cost.** Covering the range instead of starting from a guess costs little: for 30 points over the default bounds, a one-constant fit with its confidence interval takes about 0.1 s, and a two-constant fit about one second, with three to five seconds more for both of its intervals.
- **Replicates.** With several replicate signal rows and row weights $w_r$ the objective is $Q(K) = \sum_r w_r S_r(K)$ — one shared $K$, each row its own coefficients. Section 4.3 says what that is used for.

### 4.2. Root-Finding Algorithms

For the competitive assays (GDA/IDA) and the stepwise 1:2 models (HG2/H2G) the free concentration cannot be isolated algebraically; the direct binding assay (DBA) has a closed form, evaluated in the branch that is free of cancellation.

- **Role:** the mass balance of every single data point is solved for the free concentration by a **Newton iteration started from a guaranteed lower bound on the root** and stopped on a *relative* step of $4\varepsilon \approx 8.9 \times 10^{-16}$. The competitive balance is increasing and concave in the free host, so every iterate from that start stays at or below the root and rises to it: the iteration is monotone and needs no bracket. That monotonicity also ends it — a balance computed as no longer negative means the iterate has reached the floor set by the rounding error of the balance, below which no step carries digits. The stepwise balance is increasing but not concave when the second binding step is cooperative, so its iteration is safeguarded by a bracket, falling back on the geometric mean of the bracket's ends whenever a Newton step would leave it.
- **Why this algorithm:** where binding is tight the free concentration lies ten or more decades below the totals, so an absolute tolerance, or a balance summed as it stands, leaves the root undetermined by the ratio of the two. The balance is therefore evaluated in a form that adds, per binding partner, only its *minority* species — the complex while less than half of the partner is bound, the free form once more than half is — which rounds at the scale on which the balance responds to a relative change of the root. The solved concentration is then accurate to a few $\varepsilon$ *relative*, at any binding constant and any ratio of the totals whose product with that constant a double can still represent; `tests/unit/test_equilibrium_precision.py` certifies that: it brackets each returned root between the exact signs of the balance evaluated in rational arithmetic (`fractions.Fraction`).
- **What it gives the fit:** concentrations that are always physically meaningful (each species is a product of positive quantities and stays within its total), a residual surface that is smooth in $K_a$ — so the profile of Section 6 has the minimum the data put there and no other — and a defined answer for inputs there is no speciation for (a negative constant, a product of a constant with a total or a stepwise product beyond the range of a double, or a free concentration the solve drives below the smallest normal double): those species are *not a number*, and such a point has no fit rather than a wrong one.
- **Results files:** each result records which equilibrium arithmetic produced its quality scores, so a file written by an earlier version of the app is checked against the data with the arithmetic that wrote it, and its $R^2$, RMSE and fit curve are recomputed with the present one where the two differ. The fitted parameters are the file's throughout.

### 4.3. Replicates: The Reported Fit and the Shared-$K_a$ Test

Replicates of one titration measure the same chemistry, so they share $K_a$ and may differ in amplitude and in scatter. For replicates of equal variance, the joint least-squares fit of all of them *is* the fit of their average, and the average of model signals that share $K$ is itself a model signal, $\overline{A(K)\mathbf{c}_r} = A(K)\overline{\mathbf{c}_r}$. The reported estimate is therefore the projected fit of the **average of the replicates used**, in both fitting modes, with its profile interval (Section 6).

Fitting each replicate separately adds two things the average cannot give:

1. **What each replicate says on its own.** Every active replicate is fitted by itself, deterministically, and the summary reports the median and the min–max of those values next to the estimate. This is real between-replicate information — reproducibility of the experiment — and it answers a different question from the interval, which is how well the fitted data pin $K_a$ down.
2. **A test of the assumption the average rests on.** Averaging is only honest if the replicates share $K$. That hypothesis is tested explicitly. With $q$ the design rank at the shared optimum, $k$ the number of fitted association constants and $\nu = n - q - k$, each replicate's own residual gives its variance $s_r^2 = S_r(\hat{K}_r)/\nu$ and its weight $w_r = 1/s_r^2$, so every replicate's misfit is measured in units of its own scatter and a noisier replicate is not penalised for being noisy. For a set $A$, $Q_{\min}(A) = \min_K \sum_{r \in A} w_r S_r(K)$, and the leave-one-out statistic $T_r = Q_{\min}(A) - Q_{\min}(A \setminus r) - \nu$ is referred to $F(k, \nu)$ through $p_r = \mathrm{sf}_F(T_r/k)$. The replicate with the smallest $p_r$ is removed while $p_r < 0.01/R$, and the test is then repeated on what is left.

The level is the ISO 5725-2 outlier level: 1 % family-wise, Bonferroni-corrected over the $R$ replicates given, so a replicate significant at 5 % but not at 1 % is a *straggler* and is kept. Removal is sequential because a single pass lets one genuine outlier drag the shared $K$ of the others — measured, on synthetic IDA data with one replicate at three times the true $K_a$: eight replicates give 12 % wrong exclusions in a single pass and none sequentially, and with four replicates the power rises from 10 % to 100 %. Fewer than three remaining replicates, or $\nu < 1$, cannot be judged at all (two replicates cannot say which of them is off), and half of the replicates or more are never removed, because a majority is what defines the consensus $K$.

Calibration is done per assay type, on synthetic data of that assay (replicate amplitudes ±20 %, 100–300 datasets per scenario). **False exclusions.** Over 216 scenarios of GDA, IDA and both DBA directions — 3, 4 or 8 replicates, 8, 12 or 20 points, 1 % or 5 % noise, and one replicate 1×, 3× or 4× noisier than the rest — the family-wise rate of excluding a replicate that in truth shares $K_a$ is at most 1.7 % and averages 0.18 % (GDA 0.03 %, IDA 0.30 %, DBA host-to-dye 0.31 %, DBA dye-to-host 0.06 %); over 16 HG2 scenarios it is at most 1.0 %, and where every replicate carries the same smooth 2 % systematic departure from the model at most 0.7 %. The test therefore stays at or below the level it claims across the assays.

**Power depends on what one replicate alone resolves, not on the rule.** A leave-one-out test can only see a shift in $K_a$ that one replicate's own data pin down; where a single replicate's 95 % interval spans decades, no shift within those decades is significant at $0.01/R$. Measured with one replicate planted at ten times the true $K_a$ (8 replicates, 20 points, 2 % noise, 300 datasets): it is excluded in 96 % of IDA runs, 63–68 % of DBA host-to-dye runs, and under 8 % of GDA, DBA dye-to-host and HG2 runs — whose randomised designs give a single replicate a median interval of 20, 5.9 and 8.2 decades. Binned by that width instead of by assay, the picture is one rule: where the planted replicate's own interval is under half a decade it is excluded in 450 of 450 runs of every assay, between half a decade and a decade in 50–100 %, and beyond two decades almost never. Another replicate is wrongly excluded in at most 1.3 % of runs throughout. A design that determines $K_a$ from one replicate therefore also detects a replicate that disagrees; a design that does not, does not, and the replicates' own intervals say which case is at hand.

Every excluded replicate is named in the report with its $p$-value and the reason, and plays no part in the reported parameters, RMSE or R².

### 4.4. Physical Constraints: Non-Negative Signal Intensities

All parameters representing physical signal intensities or association constants are **strictly non-negative**:

- $K_a > 0$ — association constants are ratios of concentrations at equilibrium.
- $I_0 \geq 0$ — baseline/background signal from the instrument.
- $I_{\text{dye,free}} \geq 0$ — molar response of free dye.
- $I_{\text{dye,bound}} \geq 0$ — molar response of bound dye (host-dye complex).

The fit enforces this through the bounds: the $K_a$ search covers only positive values, and the signal parameters are the solution of a least-squares problem constrained to lie between their lower and upper bounds, with $\geq 0$ the default lower bound across all assay types and no default upper bound: the size of a signal coefficient follows the detector gain and the concentration scale, so a finite default would tie the fit and its interval to the units a titration happens to be recorded in. A finite bound on a signal parameter is knowledge the user enters, and a fit that ends on one says so. Functions that derive parameter bounds from prior fits (e.g. propagating dye-alone calibration results to downstream DBA/GDA/IDA fits) also clamp lower bounds to zero. Raw measured signals may occasionally appear negative due to instrument noise or baseline drift, but the underlying physical quantities being modelled are always non-negative.

## 5. Parameter Identifiability and Signal Coefficient Degeneracy

### 5.1. The Problem

The 4-parameter signal model $I = I_0 + I_{\text{dye,free}} [D_{\text{free}}] + I_{\text{dye,bound}} [HD]$ contains a **structural degeneracy** in certain assay configurations. Different combinations of $(I_0, I_{\text{dye,free}}, I_{\text{dye,bound}})$ can produce **identical predicted signals**, making these parameters individually non-identifiable from curve fitting alone.

### 5.2. Mathematical Origin

The degeneracy arises from the **mass conservation constraint** on the fixed species.

**IDA example** (fixed dye, $d_0$ constant):

From dye mass balance: $[D_{\text{free}}] = d_0 - [HD]$. Substituting into the signal equation:

$$I = I_0 + I_{\text{dye,free}}(d_0 - [HD]) + I_{\text{dye,bound}}[HD]$$

$$I = \underbrace{(I_0 + I_{\text{dye,free}} \cdot d_0)}_{\text{effective offset}} + \underbrace{(I_{\text{dye,bound}} - I_{\text{dye,free}})}_{\text{effective contrast}} \cdot [HD]$$

The three parameters $(I_0, I_{\text{dye,free}}, I_{\text{dye,bound}})$ collapse into **two effective degrees of freedom**: an offset and a contrast. Any parameter triplet satisfying the same offset and contrast produces an identical signal curve. This defines a **one-dimensional degenerate manifold** in parameter space.

**DBA host-to-dye** (host titrated into a fixed dye $d_0$): the signal reads the dye, $[D_{\text{free}}] + [HD] = d_0$, and the same reduction applies word for word — three parameters, two effective quantities.

**DBA dye-to-host** (dye titrated into a fixed host $h_0$): the signal still reads the free dye and the complex, but now the dye total changes at every titration point, so $[D_{\text{free}}]$ and $[HD]$ are not tied to each other by a constant. The host balance $[H_{\text{free}}] = h_0 - [HD]$ ties a species the signal does not contain. No combination of the three signal parameters reproduces the same curve, and all three are separately determined.

**GDA** (dye titrated into host and guest) is the same case: $d_0$ varies along the titration, $[D_{\text{free}}]$ and $[HD]$ move independently, and the three signal parameters are separately determined — as long as the fitted binding populates the complex at all; where it does not, $[HD]$ is a negligible multiple of $[D_{\text{free}}]$ and $I_{\text{dye,bound}}$ is starred on its own (Section 5.3).

### 5.3. Consequences

| What is identifiable | What is NOT identifiable |
|---------------------|------------------------|
| $K_a$ (controls curve **shape** via equilibrium) | Individual $I_0$, $I_{\text{dye,free}}$, $I_{\text{dye,bound}}$ |
| Effective offset $(I_0 + I_{\text{dye,free}} \cdot c_{\text{fixed}})$ | Their individual contributions |
| Effective contrast $(I_{\text{dye,bound}} - I_{\text{dye,free}})$ | Decomposition into the two coefficients |
| Overall fit quality ($R^2$, RMSE) | Which parameter triplet is "correct" |

Practically this means:
- A **perfect fit** ($R^2 \approx 1$) can carry the **wrong** individual signal coefficients.
- $K_a$ is reliably recovered regardless — it is the only parameter that affects the curve's inflection point and saturation behavior.
- Fitting with wide signal coefficient bounds typically produces artificially large or small values for $I_{\text{dye,free}}$ compensated by $I_0$.

**How the app reports it.** The degeneracy is measured on the fit itself rather than assumed per assay. At $\hat{K}$ the signal is linear in the offset and the coefficients, one design column each, and what the data can say about one of them is carried by the part of its column that the other columns do not reproduce: the residual of that column after its least-squares fit on the others, solved to machine precision. A parameter is flagged when that residual is below $10^{-8}$ of the largest species column (for the offset, of its own column). A coefficient of the size that produces the whole signal on the most populated species then changes the curve by less than $10^{-8}$ of it once the other parameters have taken back what they can, so the fit trades the parameter against the others at no cost. The residual is read in concentration, not relative to the column's own length, and the judgement is made column by column against all the others, so a mass balance names every parameter it ties however sparsely one of the species is populated — $[H] + [HG] + [HG_2] = h_0$ writes the $[H]$ column exactly as $h_0$ times the offset column minus the two others, whether $[H]$ is a tenth of the host or a millionth — and a species the fit leaves unpopulated is named too, together with the coefficients its short column trades against: at a negligible second binding step $[HG_2] = K_{a,HG_2} h_0 [G] - (K_{a,HG_2}/K_{a,HG}) [HG]$ to the order the fit resolves, so $I_G$, $I_{HG}$ and $I_{HG_2}$ are all three exchangeable. The threshold is the resolution the design is read at, the same as the rank cut-off of Section 6.2. Over 2400 random designs (every model, the stepwise ones also with $I_H$ fitted, $K_a c$ from $10^{-2}$ to $10^{5}$, host $10^{-9}$ to $10^{-2}$ M, 8–30 points) 48 % of the fitted signal parameters leave $10^{-12}$ or less of their column unexplained and 51 % leave $10^{-8}$ or more; the 1.2 % in between are species populated below $10^{-4}$ of the host whose short column the others nearly reproduce, and the offset at a binding constant so large that no free host is left. On either side of the line such a coefficient is not a result at physical scale; the line decides only whether it is starred. Flagged parameters are starred wherever they are listed — summary table, text report, and the `degenerate` column of the CSV export — with the statement that only a combination of them is determined. The flag appears where the mathematics puts it: all three signal parameters in IDA and DBA host-to-dye, where $[D] + [HD] = d_0$ is collinear with the offset; none in GDA and DBA dye-to-host at a binding the titration resolves; in the stepwise models whenever $I_H$ is freed from its pinned zero; and, in any model, on a species the fitted binding constants leave unpopulated — a weakly bound complex at $10^{-5}$ of the free dye in GDA, or the second complex of a stepwise model whose second constant the search has driven to the edge of its range.

### 5.4. Recommended Inspection Steps

To systematically demonstrate and inspect this degeneracy:

1. **Generate synthetic data** from known ground-truth parameters using the forward model.
2. **Fit with wide signal coefficient bounds** (e.g., $10^4$ to $10^{12}$ for both $I_{\text{dye,free}}$ and $I_{\text{dye,bound}}$).
3. **Compare fitted vs. true values**:
   - $K_a$ should be recovered within tolerance (≤10% for clean data).
   - $I_{\text{dye,free}}$ and $I_{\text{dye,bound}}$ will deviate significantly from truth (often $>50\%$  error), yet $R^2 \approx 1$.
4. **Verify degeneracy invariant**: Compute the effective offset and contrast from the fitted parameters — they should match the true values even when individual coefficients do not.
5. **Repeat with tight signal coefficient bounds** (±20% of truth): $K_a$ recovery improves because the degenerate manifold is constrained.
6. **Sweep $I_0$**: Fix $I_{\text{dye,free}}$ and $I_{\text{dye,bound}}$ at their true values, vary $I_0$, and recompute the signal — observe that offsetting $I_0$ by $\Delta$ and $I_{\text{dye,free}}$ by $-\Delta / c_{\text{fixed}}$ produces an identical curve.

### 5.5. Mitigation Strategies

- **Fix signal coefficients from a prior DBA calibration.** In the standard experimental workflow, DBA is performed first, and the resulting $I_{\text{dye,free}}$ and $I_{\text{dye,bound}}$ are treated as known constants in subsequent GDA/IDA fits. This eliminates the degeneracy entirely and is the scientifically correct approach.
- **Use tight bounds** (±20%) on signal coefficients when fitting, if fixing them is not feasible.
- **Set $I_0 = 0$** in synthetic test scenarios to reduce the parameter-space dimension, which makes the remaining coefficients directly comparable with their true values.
- **Report the effective offset and contrast** rather than (or in addition to) the individual coefficients, since these are the physically identifiable quantities.

## 6. Confidence Intervals for the Association Constants

### 6.1. The Profile

Holding one association constant $K_j$ at a value $k$ and minimising over everything else — the signal coefficients by the exact bounded solve of Section 4.1, any other association constant by the same search along its own axis — gives the **profile**

$$P_j(k) = \min_{K:\,K_j = k} S(K)$$

the smallest residual the model can reach with that constant held there. It is built from the same calls as the fit, so its minimum *is* the reported fit, and its shape is the profile likelihood of $K_j$ under Gaussian errors. A curve drawn across the bounds in force therefore bounds every fit of these data at every value of that constant; the Identifiability tab draws it, adding points wherever straight lines between them would miss the exact curve.

### 6.2. The F-Test Interval

The interval keeps every $K_j$ whose residual sum of squares is not significantly above the minimum (Bates & Watts 1988; Seber & Wild 1989; Venzon & Moolgavkar 1988):

$$P_j(k) \;\le\; \mathrm{SSR}_{\min}\left(1 + \frac{F(\alpha;\, 1,\, n - p)}{n - p}\right)$$

- $n$ — points in the profiled signal.
- $p = (\text{association constants fitted}) + \operatorname{rank} X(\hat{K})$ — the **numerical rank** of the free coefficient columns at the best fit, plus one per association constant that was free to move; a constant pinned by equal bounds is not fitted and adds nothing. Counting the nominal number of coefficients would be wrong here: the signal coefficients are structurally degenerate (Section 5), so two columns the data cannot separate must contribute one degree of freedom, not two. The rank is taken from the singular values of the norm-scaled design, at a relative cut-off of $10^{-8}$: measured over synthetic GDA, IDA and DBA titrations with the constant swept over the whole default range, exact dependencies carry relative singular values of $2\times10^{-17}$ to $2\times10^{-15}$ while a direction the signal does separate stays above $7\times10^{-7}$, and nothing falls between.
- $\mathrm{SSR}_{\min}$ is floored at $10^{-10}$ of the total sum of squares. An $R^2$ above $1 - 10^{-10}$ means a scatter below $10^{-5}$ of the signal range, which no instrument delivers; without the floor, data reproduced to rounding would return a zero-width interval whose ends are arithmetic.

The edges are located by root-finding on the exact curve. An edge that reaches a $K_a$ bound without crossing the threshold is reported as **open**: the measurement places no limit on $K_a$ on that side, and the result is a limit rather than an interval. A model with two association constants has one more way of producing a crossing that is not a limit: along the profile of one constant the other compensates until it reaches its own bound, and from there the residual rises and crosses the threshold although the data would accept the pair further out. Such a crossing moves decade for decade with that bound. It is recognised at the edge itself — the minimum over the other constant lies on its bound and the residual still falls towards it, by more than $10^{-3}$ of the rise the $F$ test allows over the last quarter decade — and the side is then reported as open, naming the constant whose bound it rests on. On 120 random HG2/H2G designs this rule marks all 93 closed edges that move when both $K_a$ bounds are widened by three decades and none of the 76 that stay (the two groups lie at $\ge 1.6\times10^{-2}$ and $\le 1.6\times10^{-4}$ of the allowed rise). This is the practical-identifiability reading of a profile likelihood in the sense of Raue et al. (2009).

### 6.3. Two Association Constants: Intervals and the Joint Region

A model with two stepwise constants gets one interval per constant, each read off that constant's own profile — with the other constant refitted at every point, so the interval is what the data say about that constant alone. The pair additionally has a **joint 95 % confidence region**, the same test with two degrees of freedom:

$$S(K_1, K_2) \;\le\; \mathrm{SSR}_{\min}\left(1 + \frac{2\,F(\alpha;\, 2,\, n - p)}{n - p}\right)$$

drawn as a filled region in $(\log_{10} K_1, \log_{10} K_2)$ with the two one-dimensional intervals as bands across it. The two readings answer different questions, and the region is not the rectangle the intervals span: it extends past them along the direction in which one constant compensates the other, and rejects pairs that lie inside both. Stepwise constants are correlated almost by construction — a titration that resolves only the product $K_1K_2$ leaves a ridge along which the two exchange — so the region, not the pair of intervals, is what says whether a reported pair is supported.

### 6.4. Replicates Are Averaged, Not Pooled

The profile, the best fit and the interval describe the **average of the replicates the fit used** (Section 4.3). Replicates of one titration share their systematic departure from the model: if the model misses a point, it misses that point in every replicate. Treating $m$ replicates as $m \times n$ independent observations counts one shared miss $m$ times as independent evidence: the interval narrows — by up to about $\sqrt{m}$ where that miss dominates the scatter — while the miss itself, the dominant error, stays exactly where it was.

`scripts/profile_interval_coverage.py` measures the interval on synthetic IDA data, 200 designs per scenario, nominal 95 %:

| Scenario | Coverage of the true $K_a$ |
|---|---|
| Independent noise of constant size | 0.96 |
| Noise proportional to the signal | 0.91 |
| Four replicates sharing a smooth 2 % misfit | 0.77 |
| The same, with the replicates' points pooled as independent | 0.67 |

Constant-variance scatter is the assumption the F test is built on, and it is met. Proportional noise breaks it mildly and costs a few points of coverage. A shared systematic misfit breaks it badly — and the last row is why the app averages: pooling would make the same data look more informative while being less accurate.

## 7. Input Sensitivity: Sobol' Variance Decomposition

The interval of Section 6 conditions on the entered experimental conditions being correct. The sensitivity analysis removes that condition: each input is given a stated uncertainty, and the fit is repeated over the resulting input distribution.

### 7.1. Inputs and Their Distributions

The perturbable inputs are the fixed conditions ($h_0$, $d_0$, $K_{a,\text{dye}}$, …) and the titrant concentration vector. Each is drawn independently, through its inverse CDF, so the same definition of an input's distribution serves plain random draws and a low-discrepancy sequence alike:

- a $\sigma$ spec (in percent of nominal, or in the input's own unit) draws from a normal distribution truncated at zero, so a concentration never goes negative;
- an interval spec draws uniformly between its ends, the form in which a $K_a$ carried over from an earlier fit naturally arrives.

The titrant enters as **one common factor**: a single draw scales the whole concentration vector, which is how a mis-calibrated stock solution acts — it displaces every titration point together, not each one independently.

### 7.2. Estimators

For output $Y = \log_{10} K_a$ and inputs $X_1 \dots X_k$, the first-order and total-order Sobol' indices (Sobol' 2001) are

$$S_i = \frac{\operatorname{Var}_{X_i}\!\big(E[Y \mid X_i]\big)}{\operatorname{Var}(Y)}, \qquad S_{T_i} = \frac{E\!\big[\operatorname{Var}(Y \mid X_{\sim i})\big]}{\operatorname{Var}(Y)}$$

They are estimated on a Saltelli design: two independent sample matrices $A$ and $B$ and the $k$ matrices $AB_i$ that take column $i$ from $B$ — $N \times (k + 2)$ fits in total. First order uses the Saltelli et al. (2010) estimator and total order the Jansen (1999) estimator:

$$\hat{S}_i = \frac{\frac{1}{N}\sum_j f(B)_j\big(f(AB_i)_j - f(A)_j\big)}{\hat{V}}, \qquad \hat{S}_{T_i} = \frac{\frac{1}{2N}\sum_j \big(f(A)_j - f(AB_i)_j\big)^2}{\hat{V}}$$

The outputs are centred on the mean of $A$ and $B$ before either estimator is applied. Neither expectation changes under a constant shift, but the variance of the first-order estimator grows with the square of the output mean, and $\log_{10} K_a$ sits near 8 with a spread of a few tenths — uncentred, the first-order indices would be buried in that offset.

$\log_{10} K_a$ rather than $K_a$ is decomposed because an association constant varies multiplicatively over orders of magnitude; a variance decomposition of $K_a$ itself would be dominated by whichever input happens to push it highest.

### 7.3. Sampling Error of an Index

The design is built from $B = 8$ **independently scrambled** Sobol' blocks (Owen 1997; L'Ecuyer & Lemieux 2002), each the first $N/B$ points of its own scrambled sequence. The indices come from all usable rows pooled; leaving each block out in turn gives a delete-one-block jackknife standard error (Archer, Saltelli & Sobol' 1997),

$$\mathrm{SE} = \sqrt{\frac{B-1}{B}\sum_j \big(\hat{\theta}_{(j)} - \bar{\hat{\theta}}\big)^2}, \qquad \text{CI} = \hat{\theta} \pm t_{B-1,\,0.975}\,\mathrm{SE}$$

The blocks are independent replicates of one design; the rows *inside* a scrambled block are not independent draws and cannot stand in for them. The interval covers the Monte Carlo sampling error of one index at a time — not error in the stated input uncertainties, and not model error. It is symmetric and is not clipped to $[0, 1]$, so a small index can show a negative lower end.

`scripts/sobol_interval_coverage.py` reproduces the calibration, and `scripts/README.md` carries the table it prints. Over 1000 designs each of the Ishigami function and of a six-input g-function at $N = 1024$, the nominal 95 % intervals covered the analytically known index in 94.2–97.1 % of designs, and the estimator's bias stayed within 0.07 standard deviations. The same script measures the price of blocking: at a fixed budget, eight blocks raise the root-mean-square error of an index by up to a factor of about five, index by index — a few indices are barely affected — over a single undivided scramble, which is the cost of having an error bar at all.

### 7.4. Every Sample Is Kept

Each sample is refitted by the projection of Section 4.1, on the average of the replicates the reported fit used, so its $K_a$ is the best the model can do for its perturbed inputs. Every sample counts, however poorly it describes the data. Discarding the poor ones would remove precisely the input combinations the data disagree with, which would bias the sampled distribution back towards the inputs as entered and make the analysis look more reassuring than the evidence allows.

Because every refit is one deterministic projection, the spread the analysis reports is the effect of the stated input uncertainties and nothing else — there is no search scatter mixed into it. The analysis therefore covers every assay with an association constant, the stepwise two-constant models included; a model with no association constant has nothing to decompose.

## 8. General Theoretical Workflow Diagram

![Workflow Diagram](fitting_workflow.jpg)
