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

### 3.4. Totals That Fall with Each Addition

A mass balance needs the total concentration of every fixed species *at the point being modelled*. Unless the samples were made up to a common volume, or the titrant stock was prepared in the sample solution itself, each addition of titrant adds volume and every fixed total falls along the titration.

Only the titrant stock concentration $c_T$ is needed to describe that, because the measured titrant concentration already carries the volume. A sample of volume $V_0$ that has taken up a cumulative volume $W_i$ of stock holds

$$x_i = \frac{c_T W_i}{V_0 + W_i} \quad\Longrightarrow\quad \varphi_i \;=\; \frac{W_i}{V_0 + W_i} \;=\; \frac{x_i}{c_T},$$

so the fraction of the final volume that came from the stock is $x_i / c_T$ and a fixed species the stock does not contain has total

$$c_k(x_i) \;=\; c_k \left(1 - \frac{x_i}{c_T}\right),$$

while one the stock carries at the sample's own concentration stays at $c_k$. The relation between $\varphi_i$ and $x_i$ is a ratio of volumes, so it holds equally for additions into one cuvette and for separately prepared samples: the mode of preparation does not enter. The convention for $x$ is the titrant concentration in the cuvette after each addition; concentrations computed without dilution convert as $x = x_{\text{nom}} c_T / (c_T + x_{\text{nom}})$.

The model is therefore exact rather than approximate, and one code path serves both cases: with no stock declared, $c_k(x_i)$ is the scalar $c_k$ and the equilibrium arithmetic is the scalar arithmetic, operation for operation. Fitting diluted data with the totals held constant biases $K_a$ by an amount and in a direction that depend on the assay and on the dilution reached; `python -m validation run dilution-coverage dilution-ignored` measures the coverage recovered and the error left behind.

Dilution is also consistent with the scaling identity of Section 9.6: $c_T$ is a concentration and scales with the others, while $\varphi_i$ is invariant.

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
- **Points.** Each titration point carries a weight $\omega_i$ of its own, read from the noise law the replicates show, so $S(K)$ above is $\min_\mathbf{c} \sum_i \omega_i (y_i - (A(K)\mathbf{c})_i)^2$. Section 4.4 derives the law and states where the whitening happens; with one titration, and wherever the replicates show constant noise, $\boldsymbol\omega = \mathbf{1}$ and the solve is the unweighted one.

### 4.2. Root-Finding Algorithms

For the competitive assays (GDA/IDA) and the stepwise 1:2 models (HG2/H2G) the free concentration cannot be isolated algebraically; the direct binding assay (DBA) has a closed form, evaluated in the branch that is free of cancellation.

- **Role:** the mass balance of every single data point is solved for the free concentration by a **Newton iteration started from a guaranteed lower bound on the root** and stopped on a *relative* step of $4\varepsilon \approx 8.9 \times 10^{-16}$. The competitive balance is increasing and concave in the free host, so every iterate from that start stays at or below the root and rises to it: the iteration is monotone and needs no bracket. That monotonicity also ends it — a balance computed as no longer negative means the iterate has reached the floor set by the rounding error of the balance, below which no step carries digits. The stepwise balance is increasing but not concave when the second binding step is cooperative, so its iteration is safeguarded by a bracket, falling back on the geometric mean of the bracket's ends whenever a Newton step would leave it.
- **Why this algorithm:** where binding is tight the free concentration lies ten or more decades below the totals, so an absolute tolerance, or a balance summed as it stands, leaves the root undetermined by the ratio of the two. The balance is therefore evaluated in a form that adds, per binding partner, only its *minority* species — the complex while less than half of the partner is bound, the free form once more than half is — which rounds at the scale on which the balance responds to a relative change of the root. The solved concentration is then accurate to a few $\varepsilon$ *relative*, at any binding constant and any ratio of the totals whose product with that constant a double can still represent; `tests/unit/test_equilibrium_precision.py` certifies that: it brackets each returned root between the exact signs of the balance evaluated in rational arithmetic (`fractions.Fraction`).
- **What it gives the fit:** concentrations that are always physically meaningful (each species is a product of positive quantities and stays within its total), a residual surface that is smooth in $K_a$ — so the profile of Section 6 has the minimum the data put there and no other — and a defined answer for inputs there is no speciation for (a negative constant, a product of a constant with a total or a stepwise product beyond the range of a double, or a free concentration the solve drives below the smallest normal double): those species are *not a number*, and such a point has no fit rather than a wrong one.
- **Results files:** each result records which equilibrium arithmetic produced its quality scores, so a file written by an earlier version of the app is checked against the data with the arithmetic that wrote it, and its $R^2$, RMSE and fit curve are recomputed with the present one where the two differ. The fitted parameters are the file's throughout.

### 4.3. Replicates: The Reported Fit and the Shared-$K_a$ Test

Replicates of one titration measure the same chemistry, so they share $K_a$ and may differ in amplitude and in scatter. For replicates of equal variance, the joint least-squares fit of all of them *is* the fit of their average, and the average of model signals that share $K$ is itself a model signal, $\overline{A(K)\mathbf{c}_r} = A(K)\overline{\mathbf{c}_r}$. The reported estimate is therefore the projected fit of the **average of the replicates used**, in both fitting modes, with its profile interval (Section 6).

Fitting each replicate separately adds two things the average cannot give:

1. **What each replicate says on its own.** Every active replicate is fitted by itself, deterministically, with the inputs as entered, and the summary reports the median and the range of those values on a line of their own under the table; a replicate whose own fit ran to an end of the $K_a$ search box has no value there, and is counted rather than summarised. This is real between-replicate information — reproducibility of the experiment — and it answers a different question from the interval, which is how well the fitted data pin $K_a$ down.
2. **A test of the assumption the average rests on.** Averaging is only honest if the replicates share $K$. That hypothesis is tested explicitly. With $q$ the design rank at the shared optimum, $k$ the number of fitted association constants and $\nu = n - q - k$, each replicate's own residual gives its variance $s_r^2 = S_r(\hat{K}_r)/\nu$ and its weight $w_r = 1/s_r^2$, so every replicate's misfit is measured in units of its own scatter and a noisier replicate is not penalised for being noisy. For a set $A$, $Q_{\min}(A) = \min_K \sum_{r \in A} w_r S_r(K)$, and the leave-one-out statistic $T_r = Q_{\min}(A) - Q_{\min}(A \setminus r) - \nu$ is referred to $F(k, \nu)$ through $p_r = \mathrm{sf}_F(T_r/k)$. The replicate with the smallest $p_r$ is removed while $p_r < 0.01/R$, and the test is then repeated on what is left.

The level is the ISO 5725-2 outlier level: 1 % family-wise, Bonferroni-corrected over the $R$ replicates given, so a replicate significant at 5 % but not at 1 % is a *straggler* and is kept. Removal is sequential because a single pass lets one genuine outlier drag the shared $K$ of the others — measured, on synthetic IDA data with one replicate at three times the true $K_a$: eight replicates give 12 % wrong exclusions in a single pass and none sequentially, and with four replicates the power rises from 10 % to 100 %. Fewer than three remaining replicates, or $\nu < 1$, cannot be judged at all (two replicates cannot say which of them is off), and half of the replicates or more are never removed, because a majority is what defines the consensus $K$.

Calibration is done per assay type, on synthetic data of that assay (replicate amplitudes ±20 %, 100–300 datasets per scenario). **False exclusions.** Over 216 scenarios of GDA, IDA and both DBA directions — 3, 4 or 8 replicates, 8, 12 or 20 points, 1 % or 5 % noise, and one replicate 1×, 3× or 4× noisier than the rest — the family-wise rate of excluding a replicate that in truth shares $K_a$ is at most 1.7 % and averages 0.18 % (GDA 0.03 %, IDA 0.30 %, DBA host-to-dye 0.31 %, DBA dye-to-host 0.06 %); over 16 HG2 scenarios it is at most 1.0 %, and where every replicate carries the same smooth 2 % systematic departure from the model at most 0.7 %. The test therefore stays at or below the level it claims across the assays.

**Power depends on what one replicate alone resolves, not on the rule.** A leave-one-out test can only see a shift in $K_a$ that one replicate's own data pin down; where a single replicate's 95 % interval spans decades, no shift within those decades is significant at $0.01/R$. Measured with one replicate planted at ten times the true $K_a$ (8 replicates, 20 points, 2 % noise, 300 datasets): it is excluded in 96 % of IDA runs, 63–68 % of DBA host-to-dye runs, and under 8 % of GDA, DBA dye-to-host and HG2 runs — whose randomised designs give a single replicate a median interval of 20, 5.9 and 8.2 decades. Binned by that width instead of by assay, the picture is one rule: where the planted replicate's own interval is under half a decade it is excluded in 450 of 450 runs of every assay, between half a decade and a decade in 50–100 %, and beyond two decades almost never. Another replicate is wrongly excluded in at most 1.3 % of runs throughout. A design that determines $K_a$ from one replicate therefore also detects a replicate that disagrees; a design that does not, does not, and the replicates' own intervals say which case is at hand.

Every excluded replicate is named in the report with its $p$-value and the reason, and plays no part in the reported parameters, RMSE or R².

### 4.4. The Noise Law the Replicates Show

The $F$ tests of Sections 6 and 8 rest on scatter of one size across the titration. A fluorescence titration rarely has that: at the bright end the noise is a percentage of the signal, at the dark end it is the detector's own floor. Where two or more replicates were measured the app reads where between those two regimes the data lie and weights the fit accordingly; with one titration it cannot, and says so instead of assuming.

**What replicate scatter is, and what it is not.** Two runs of one titration differ by the noise of each measurement *and* by an affine image of the whole curve — a lamp, a gain, a path length, a background. The second is not error about the model. For every registered assay

$$\alpha + \beta\Big(I_0 + \sum_i I_i [C_i]\Big) = (\alpha + \beta I_0) + \sum_i (\beta I_i)\,[C_i],$$

the same model with different signal parameters, so a replicate measured 3 % brighter is a curve the fit reproduces exactly and has not measured any less precisely. The noise is therefore read from the residuals of each replicate about its **own** affine image of the mean curve,

$$\mathbf{e}_r \;=\; \mathbf{y}_r - \big(\hat\alpha_r + \hat\beta_r\,\bar{\mathbf{y}}\big), \qquad r = 1 \dots m,$$

each fitted by weighted least squares on the two columns $[\mathbf{1}, \bar{\mathbf{y}}]$ — one thin QR for all of them, and the residuals read whitened by those same weights — and not from the raw deviations $y_{ri} - \bar{y}_i$. The replicates of the datasets shipped in `data/` differ by scale factors of 0.97 to 1.03, and read raw that structure alone makes their scatter grow with the signal: the raw spread of `data/DBA_system_host_to_dye.txt` reads a proportional share of 0.97 (0.94 once the default outlier removal has run) where the detrended scatter reads 0.20 (0.37), and the data would be weighted as though their noise were proportional to the signal when most of it is not.

**The law.** The two-component model of analytical chemistry (Rocke & Lorenzato 1995),

$$\operatorname{var}(y_i) \;=\; a^2 + \big(b\,\bar{y}_i\big)^2 \;=\; c\,g_i(\lambda), \qquad g_i(\lambda) = (1 - \lambda) + \lambda\,\frac{\bar{y}_i^2}{\mathrm{ref}^2}, \qquad \mathrm{ref}^2 = \frac{1}{n}\sum_i \bar{y}_i^2,$$

a constant floor $a$ in signal units and a part $b$ proportional to the signal, written as a level $c$ times a relative variance $g$ that is 1 at the root-mean-square signal. The **share** $\lambda \in [0, 1]$ is the fraction of the variance at that signal which grows with the signal squared: $\lambda = 0$ is constant noise, $\lambda = 1$ proportional noise, and $a = \sqrt{c(1 - \lambda)}$, $b = \sqrt{c\lambda}/\mathrm{ref}$. It is preferred to a power law $c\,\bar{y}^{2\theta}$ on four counts: it contains constant, proportional and mixed noise exactly rather than approximately; its share is confined to $[0, 1]$ by the non-negativity of the two variances, so no exponent has to be clipped at a chosen value; the signal enters squared, so a blank-subtracted point at or below zero is harmless where $\log \bar{y}$ is undefined; and the weights it implies are bounded, where a power law's grow without limit as the signal goes to zero.

**The estimator.** Only $\lambda$ is searched. For a candidate share, every replicate is detrended as above with the points weighted by $1/g_i(\lambda)$, giving whitened residuals $e_{ri}$ and the leverages $h_i$ of the two-column fit, and

$$t_i \;=\; \frac{1}{1 - h_i}\sum_{r=1}^{m} e_{ri}^2, \qquad \mathbb{E}\,t_i = c\,(m-1) \ \text{ at the true } \lambda,$$

the leverage correction undoing what the line removed and the one missing replicate being what the mean costs. Under the right share the whitened scatter is flat along the titration, so

$$\hat\lambda \;=\; \arg\min_{\lambda \in [0,1]} \ \sum_{i \,:\, t_i > 0} \big(\log t_i - \overline{\log t}\,\big)^2,$$

over the points whose $t_i$ stands above the rounding error of the projection that produced it. The spread of $\log t_i$ does not depend on the size of the noise, and a least-squares fit of logarithms is not carried away by the single wild value of one replicate at one point that a real titration has. A whole replicate that runs apart from the others raises the scatter wherever it goes, and the law is read from the replicates it is handed: removing such a replicate is the outlier step's business, before the fit. The points that scatter are decided once, with equal weights, so that every share is judged on the same points. The detrending is weighted by the same share it is judged at, so there is one objective and no fixed-point iteration. The minimum is taken on a grid of 101 nodes across $[0, 1]$ — the objective need not be unimodal with a handful of replicates — and refined by bounded Brent between the best node's neighbours, kept only if lower; a refinement that ends within its tolerance of 0 or 1 is that end, so a share of zero is exactly zero. Nothing in it draws a random number. The level follows from the same scatter as the mean of $\log t_i$ corrected for the bias of a log $\chi^2$ on $m - 1$ degrees of freedom,

$$c \;=\; \exp\!\Big(\overline{\log\big(t_i/(m-1)\big)} \;-\; \psi\big(\tfrac{m-1}{2}\big) \;+\; \log \tfrac{m-1}{2}\Big).$$

**One shape parameter, and no degrees of freedom charged for it.** Only the shape of the variance reaches the fit: the interval's threshold is a residual-variance $F$ threshold, which profiles the noise level out, so $c$ is reported and never inferred against. And $\hat\lambda$ is a function of the deviations $y_r - \bar{y}$, which under normal noise are independent of $\bar{y}$ — the only thing the fit sees — so the fit's residual degrees of freedom are those of Section 6.2 unchanged.

**The weights.** The fit is handed one weight per titration point,

$$\omega_i \;=\; \frac{1}{g_i(\hat\lambda)} \;=\; \frac{1}{(1 - \hat\lambda) + \hat\lambda\,\bar{y}_i^2/\mathrm{ref}^2},$$

computed once, before the fit, from the measured means. Consequences: there is no reweighting loop around the $K_a$ search, and the conditional fit, the input-aware fit, every profile point and every sensitivity sample see one and the same vector. $\operatorname{var}(\bar{y}_i) = c\,g_i/m$ with the same $m$ at every point, so $m$ cancels out of the relative weights and the weighted fit of the average *is* the weighted fit of the pooled replicates. Taking the weights from the observed responses rather than the fitted curve biases the fitted mean by a relative $2\lambda\,\mathrm{CV}^2/m$ (Carroll & Ruppert 1988) — $10^{-4}$ at a coefficient of variation of 2 % with four replicates — and a common relative shift of the curve is absorbed by the signal coefficients rather than by $K_a$. Their size is bounded by the law itself: $\omega_{\max}/\omega_{\min} \le (\max_i|\bar{y}_i| / \min_i|\bar{y}_i|)^2$, reached only at $\lambda = 1$, and below that every weight is under $1/(1 - \lambda)$. The extreme is not reached by accident, so nothing floors the weights: constant noise at a point far down the signal range leaves its whitened $t_i$ at $\lambda = 1$ larger than the others by that same factor, which the objective charges as a squared logarithm and so stops the share short of 1 — exactly where a floor would have acted.

**Where the whitening happens.** In one place. The bounded solve of Section 4.1 multiplies the signal rows and the free design columns by $\sqrt{\boldsymbol\omega}$ before scaling and solving, so

$$S(K) = \min_{\mathbf{lb} \le \mathbf{c} \le \mathbf{ub}} \sum_i \omega_i\big(y_i - (A(K)\mathbf{c})_i\big)^2, \qquad \mathrm{SS}_{\text{tot}} = \sum_i \omega_i\big(y_i - \bar{y}_\omega\big)^2,$$

and the residual the projection returns is the whitened one $\sqrt{\omega_i}(y_i - (A\mathbf{c})_i)$, which is in units of one noise everywhere. Everything downstream — the profile, both thresholds, the input-aware objective and its Jacobian, the runs test and the conflict reference — is that same code path, and is thereby in the space its derivation assumes. Ranks are read on the unwhitened design, where a positive row scaling cannot change them and the cut-offs of Sections 5 and 6.2 keep the scale they were measured on. With $\boldsymbol\omega = \mathbf{1}$ the whitening multiplies by exactly 1.0: a single titration is fitted with the arithmetic of an engine that has no weights, to the last bit.

**When no law can be read.** Two cases, each a state of the result rather than a silent default, and each worded in the fit summary, the text report and the CSV export:

| Case | Basis | Weights | What the summary says |
|---|---|---|---|
| One signal — a single titration, or one replicate fitted on its own | `single_titration` | $\mathbf{1}$ | taken as constant — one titration cannot show how the noise varies with the signal |
| Two or more replicates, scattering at fewer than three titration points | `too_few_points` | $\mathbf{1}$ | taken as constant — the replicates scatter at too few titration points to show how it varies |
| Otherwise | `replicates` | $1/g(\hat\lambda)$ | the law, as a floor in signal units and a percentage of the signal |

A variance function is not estimable from the residuals of a single titration — a dozen points against three or four parameters (Carroll & Ruppert 1988) — so nothing is guessed there.

**Two numbers called $R^2$.** The $R^2$ and RMSE a fit reports are unweighted, in signal units, against the averaged data, which is what their labels say and what keeps them comparable between fits and between versions of the app. The vertical axis of the Identifiability tab is the surface the fit minimises, $1 - S/\mathrm{SS}_{\text{tot}}$ with both weighted; where a law was read, that is a different number and the tab names it *weighted $R^2$*.

### 4.5. Physical Constraints: Non-Negative Signal Intensities

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

the smallest residual the model can reach with that constant held there — $S$ weighted by the point weights of Section 4.4 throughout, and unweighted wherever no noise law could be read. It is built from the same calls as the fit, so its minimum *is* the reported fit, and its shape is the profile likelihood of $K_j$ under Gaussian errors of the variance the law states. A curve drawn across the bounds in force therefore bounds every fit of these data at every value of that constant; the Identifiability tab draws it as $1 - P_j(k)/\mathrm{SS}_{\text{tot}}$, adding points wherever straight lines between them would miss the exact curve. Numerator and denominator carry the same weights, so that axis is the weighted $R^2$ of Section 4.4 wherever a law was read, and the plain $R^2$ otherwise.

### 6.2. The F-Test Interval

The interval keeps every $K_j$ whose residual sum of squares is not significantly above the minimum (Bates & Watts 1988; Seber & Wild 1989; Venzon & Moolgavkar 1988):

$$P_j(k) \;\le\; \mathrm{SSR}_{\min}\left(1 + \frac{F(\alpha;\, 1,\, n - p)}{n - p}\right)$$

- $n$ — points in the profiled signal.
- $p = (\text{association constants fitted}) + \operatorname{rank} X(\hat{K})$ — the **numerical rank** of the coefficient columns the best fit leaves strictly inside their bounds, plus one per association constant the best fit places strictly inside its search box; a constant pinned by equal bounds, or resting on an end of its box, is not fitted and adds nothing, and neither does a coefficient held on its bound. Counting the nominal number of coefficients would be wrong here: the signal coefficients are structurally degenerate (Section 5), so two columns the data cannot separate must contribute one degree of freedom, not two. The rank is taken from the singular values of the norm-scaled design, at a relative cut-off of $10^{-8}$: measured over synthetic GDA, IDA and DBA titrations with the constant swept over the whole default range, exact dependencies carry relative singular values of $2\times10^{-17}$ to $2\times10^{-15}$ while a direction the signal does separate stays above $7\times10^{-7}$, and nothing falls between.
- $\mathrm{SSR}_{\min}$ is floored at $10^{-10}$ of the total sum of squares. An $R^2$ above $1 - 10^{-10}$ means a scatter below $10^{-5}$ of the signal range, which no instrument delivers; without the floor, data reproduced to rounding would return a zero-width interval whose ends are arithmetic.

**Bounded signal parameters.** The $F$ test compares two nested fits, and its numerator counts the parameters the best fit has and the fit at the tested constant has not. With $\mathbf{c}$ free that is the tested constant alone. With $\mathbf{c}$ inside bounds — non-negative by default — the bounded solve at a tested $k$ often holds a coefficient *on* a bound that the best fit leaves free, typically the coefficient of a weakly emitting species; a coefficient on its bound is not fitted, so that fit has given up more than one parameter. With $r(K)$ the numerical rank of the design columns whose coefficient lies inside its bounds at $K$, read at the profile point of $k$ (the other constant at its minimiser),

$$m(k) = 1 + \max\big(0,\; r(\hat{K}) - r(K(k))\big), \qquad P_j(k) \;\le\; \mathrm{SSR}_{\min}\left(1 + \frac{m(k)\,F(\alpha;\, m(k),\, n - p)}{n - p}\right),$$

with $n - p$ that of the best fit throughout. Wherever the tested constant pins nothing the best fit leaves free, $m = 1$ and the rule is the one above; elsewhere the cut-off steps up, and the Identifiability tab draws it as a stepped line. A parameter on the boundary of its range makes the exact reference a mixture of $F$ distributions with 1 to $m$ numerator degrees of freedom (Self & Liang 1987), so taking $m$ is conservative, which is the side an interval may err on. A coefficient counts as on its bound when its distance from the bound, times the norm of its design column, is below $10^{-8}$ of the signal's variation about its mean (the square root of the total sum of squares) — the resolution the rank is read at, on a scale that a constant background under the signal leaves unchanged. Over 86 400 tests of the true constants of synthetic 1:2 and 2:1 titrations, the plain test ($m = 1$) accepts the truth in 92.7 % of the cases where the fit at the true constant pins one coefficient more than the best fit, in 86.4 % where it pins two and in 75.1 % where it pins three; judged with $m$ these are 97.7, 97.5 and 97.0 %. Of the 216 intervals-by-scenario of that study (two constants each in 108 cells of 400 titrations: both models, $K_1 h_0$ 0.3–3, $K_1/K_2$ 10–1000, 12 and 30 points, noise 0.5–3 %) 22 cover significantly below 95 % with the plain test, the worst at 87.5 %, and none with the count, the worst at 93.5 % [90.6, 95.7]. In six cells the plain test already covers, 88–99 % of the intervals closed at both ends stay closed, at a median width ratio of 1.00–1.05. For one association constant (32 cells of 500, half with a dark free dye) the plain test has no cell below 94.0 %, and the count widens the mean interval by 2.3 %.

Every entered condition enters $A(K)$ as the number the user typed, so this is the interval **conditional on the entered inputs**: what the data leave for $K_j$ when $h_0$, $d_0$, $K_{a,\text{dye}}$ and the titrant concentrations are exactly right. Section 7 states what they are known to within and carries that into the interval; the app reports the conditional interval beside the result whenever the two differ.

The edges are located by root-finding on the exact curve. An edge that reaches a $K_a$ bound without crossing the cut-off is reported as **open**: the measurement places no limit on $K_a$ on that side, and the result is a limit rather than an interval. The same holds for an estimate that the search left on an end of the box: that value is where the search stopped, not a measurement, so every view and export states it in words — *not limited below* the closed end of the interval — and the CSV export leaves the number out and flags the side. A model with two association constants has one more way of producing a crossing that is not a limit: along the profile of one constant the other compensates until it reaches its own bound, and from there the residual rises and crosses the threshold although the data would accept the pair further out. Such a crossing moves decade for decade with that bound. It is recognised at the edge itself — the minimum over the other constant lies on its bound and the residual still falls towards it, by more than $10^{-3}$ of the rise the $F$ test allows over the last quarter decade — and the side is then reported as open, naming the constant whose bound it rests on. On 120 random HG2/H2G designs this rule marks all 93 closed edges that move when both $K_a$ bounds are widened by three decades and none of the 76 that stay (the two groups lie at $\ge 1.6\times10^{-2}$ and $\le 1.6\times10^{-4}$ of the allowed rise). This is the practical-identifiability reading of a profile likelihood in the sense of Raue et al. (2009).

### 6.3. Two Association Constants: Intervals and the Joint Region

A model with two stepwise constants gets one interval per constant, each read off that constant's own profile — with the other constant refitted at every point, so the interval is what the data say about that constant alone. The pair additionally has a **joint 95 % confidence region**, the same test with two degrees of freedom:

$$S(K_1, K_2) \;\le\; \mathrm{SSR}_{\min}\left(1 + \frac{m\,F(\alpha;\, m,\, n - p)}{n - p}\right), \qquad m = 2 + \max\big(0,\; r(\hat{K}) - r(K_1, K_2)\big),$$

the count of Section 6.2 with two constrained constants — on the same synthetic titrations the region holds the true pair in 90.7–91.5 % of fits with $m = 2$ throughout and in 95.0–95.8 % with the count — drawn as a filled region in $(\log_{10} K_1, \log_{10} K_2)$ with the two one-dimensional intervals as bands across it. The two readings answer different questions, and the region is not the rectangle the intervals span: it extends past them along the direction in which one constant compensates the other, and rejects pairs that lie inside both. Stepwise constants are correlated almost by construction — a titration that resolves only the product $K_1K_2$ leaves a ridge along which the two exchange — so the region, not the pair of intervals, is what says whether a reported pair is supported.

### 6.4. Replicates Are Averaged, Not Pooled

The profile, the best fit and the interval describe the **average of the replicates the fit used** (Section 4.3). Replicates of one titration share their systematic departure from the model: if the model misses a point, it misses that point in every replicate. Treating $m$ replicates as $m \times n$ independent observations counts one shared miss $m$ times as independent evidence: the interval narrows — by up to about $\sqrt{m}$ where that miss dominates the scatter — while the miss itself, the dominant error, stays exactly where it was.

`python -m validation tables replicate-pooling` prints the comparison for every assay, on synthetic data with each kind of scatter a row of its own: independent noise of constant size, noise proportional to the signal, and replicates sharing a smooth systematic misfit, each read once from the average and once with the replicates' points pooled as independent.

Constant-variance scatter is the assumption the $F$ test is built on. Noise proportional to the signal breaks it, which is what the weights of Section 4.4 repair wherever the replicates can show the law. A misfit the replicates share breaks something the weights cannot repair — it is not noise — and it is the case the averaging protects against: pooling would make the same data look more informative while being less accurate.

## 7. The Entered Inputs as Constrained Nuisance Parameters

### 7.1. What a Stated Uncertainty Means

Every projectable model reads a set of entered inputs $\theta$: the fixed conditions of the assay ($h_0$, $d_0$, $K_{a,\text{dye}}$, the fixed concentration of the stepwise models) and the titrant concentration vector, which enters as a single scale factor — a stock or dilution error displaces every titration point by the same fraction. Input $j$ is written relative to what was entered,

$$\theta_j = \theta_{e,j}\,(1 + e_j),$$

and the user states, per input, one of three things:

- a **standard deviation** $s_j$ of $e_j$ (in percent of the entered value, or in the input's own unit converted through it): the input becomes a parameter carrying a pseudo-observation $z_j = e_j / s_j \sim N(0, 1)$;
- a **range** $[lo_j, hi_j]$ of offsets: a box constraint on $e_j$ and no penalty — every value inside is equally acceptable and none outside, which is the form in which a $K_{a,\text{dye}}$ carried over from an earlier fit, or a tolerance quoted by a supplier, naturally arrives;
- **fixed**: $e_j = 0$, the input is not a parameter. This is where every input starts, so a fit reports the interval of Section 6 until an uncertainty is stated.

**Errors several inputs share.** The three statements above describe the error an input carries *alone*. An error common to several inputs — their solutions come from one stock, were weighed on one balance, were pipetted with one pipette — is stated once, as a named source with a standard deviation $s_S$ in percent and the set $L(S)$ of inputs it loads. The sources are independent and act multiplicatively, so

$$\theta_j \;=\; \theta_{e,j} \prod_{S \,:\, j \in L(S)} (1 + e_S),$$

for a concentration, and $\theta_j = \theta_{e,j} \prod_S (1 + e_S)^{-1}$ for a binding constant a source loads — a $K_{a,\text{dye}}$ measured with the same stock comes out too small by the factor the stock is too large. The vector of parameters the fit carries is one offset per **source**, not per input. Each source contributes its own pseudo-observation $z_S = e_S / s_S$ exactly as an input's own $\sigma$ does, so nothing in Section 7.2 changes but the map from the offsets the fit varies to the inputs the model is evaluated at. With no shared source that map is the identity and the two coincide.

The distinction matters because the data can separate some input combinations and not others. By the scaling identity of Section 9.6, a source loading every concentration of a direct-binding assay lies along a direction the model cannot distinguish from $K_a$ itself: its residual column is collinear with the $K_a$ column and only its penalty row tells the two apart. The penalised profile is then $P(k) = \min_{e}\big[\,n \log S_e(k(1+e)) + (e/s_S)^2\,\big]$ — the conditional profile widened by the source's own distribution — so the reported interval carries that uncertainty in full, and no amount of data narrows it. Split into per-input errors instead, the same physical stock error would be spread over directions the data *can* resolve and the interval would come out too narrow. In a competitive assay the same source widens the interval only by its small net elasticity, for the reason given in Section 9.6. `python -m validation run shared-source-coverage` measures coverage when the entered values really are drawn from a model with a shared source.

The statements are independent per source, and the same error model feeds the sensitivity analysis of Section 9, which samples from it instead of fitting it. One entry it does not feed is the random error of each titrant addition (Section 9.5): the interval the fit reports does not include it. Carrying it would turn the profile into an errors-in-variables fit with $n$ further nuisance parameters.

### 7.2. The Penalised Profile and Its Threshold

With the projected residual sum of squares at shifted inputs

$$S(K, \mathbf{e}) \;=\; \min_{\mathbf{lb}\,\le\,\mathbf{c}\,\le\,\mathbf{ub}} \sum_i \omega_i \big(y_i - \big(A(K, \theta(\mathbf{e}))\,\mathbf{c}\big)_i\big)^2$$

— the bounded solve of Section 4.1 on the design built at the shifted inputs, weighted by the point weights of Section 4.4 — Gaussian noise of unknown scale, of variance $\sigma^2/\omega_i$ at point $i$, and the pseudo-observations above make minus twice the log likelihood $n \log \sigma^2 + S/\sigma^2 + \mathbf{z}'\mathbf{z}$, up to the constant $-\sum_i \log \omega_i$ that the known weights contribute. Profiling $\sigma^2 = S/n$ leaves, up to a constant, the objective $n \log S + \mathbf{z}'\mathbf{z}$, so the profile of one association constant and its interval are

$$P_j(k) = \min_{K_j = k,\; \mathbf{e} \in \text{box}} \Big[\, n \log S(K, \mathbf{e}) + \mathbf{z}'\mathbf{z} \,\Big], \qquad
P_j(k) - P_{\min} \;\le\; n \log\!\left(1 + \frac{m(k)\,F(\alpha;\,m(k),\,\nu)}{\nu}\right)$$

$$\nu \;=\; n - p - \sum_i w_i, \qquad p = (\text{association constants fitted}) + \operatorname{rank} X(\hat{K}) + (\text{inputs stated as a range, off its ends}).$$

$m(k)$ is the count of Section 6.2, read at each profile point's own solution — its constants and its shifted inputs — against the optimum's: one, plus every signal parameter the optimum fits and that solution holds on a bound.

**Why the degrees of freedom are effective ones.** An input stated with a $\sigma$ adds one parameter *and* one observation, which leaves the $\chi^2$ part of the test alone — but the noise variance is profiled from $S$ alone, and every input direction the data themselves determine takes a residual degree of freedom out of $S$. The weights $w_i \in [0, 1)$ of Section 8.2 measure exactly that: 1 where the data determine an input, 0 along a direction they cannot see, and their sum is the effective number of parameters of a penalised fit (Hodges & Sargent 2001). An input stated as a range adds a parameter and no observation, so it counts in $p$ wherever the optimum places it inside its range; one resting on an end of its range is held there, like a coefficient on its bound, and counts nothing. $p$ is one count throughout — the interval's $n - p$, the lack-of-fit numerator, the conflict statistic of Section 8.2 and the runs-test reference all read the same set of what the best fit fitted. Over 2400 synthetic one-constant titrations of 5, 6, 8 and 12 points (GDA, IDA, both DBA directions, every entered input drawn at the $\sigma$ stated for it) the nominal 95 % interval covered the true $K_a$ in 98.3, 98.0, 97.5 and 96.3 % of them, and in 98.4, 96.9, 96.6 and 95.9 % of the fits whose interval is closed at both ends. With $n - p$ in place of $\nu$ the same runs cover 85–93 %, and 73 % among the closed intervals of fits where $n - p - \sum w < 1$.

**It reduces to the conditional interval.** With no input varying, $\mathbf{z}'\mathbf{z} = 0$, $\nu = n - p$ and $P_j(k) - P_{\min} = n \log\big(S(k)/S_{\min}\big)$, so the rule reads $S(k) \le S_{\min}(1 + m F/(n-p))$ — Section 6.2 exactly, and the app returns those objects rather than recomputing them. Driving a stated $\sigma$ to zero converges onto the same edges quadratically: $3.6\times10^{-4}$, $3.6\times10^{-8}$ and $3.5\times10^{-12}$ decades away at $\sigma = 10^{-3}$, $10^{-5}$ and $10^{-7}$.

**The curve that is drawn.** $\exp(P(k)/n)$ is a residual sum of squares inflated by the input penalty, so

$$R^2_{\text{aware}}(k) = 1 - \frac{\exp\big(P(k)/n\big)}{\mathrm{SS}_{\text{tot}}}$$

is drawn on the $R^2$ axis of Section 6.1 beside the conditional profile and never below it — $\mathbf{e} = 0$ is always feasible — with its own cut-off $1 - \exp(P_{\min}/n)\,(1 + m F(\alpha; m, \nu)/\nu)/\mathrm{SS}_{\text{tot}}$, stepped like the conditional one.

**What it delivers.** Coverage of the nominal 95 %, measured on about 6000 synthetic titrations across GDA, IDA and both DBA directions, 5 to 20 points, noise of 0.5–3 % of the signal range and one scenario with noise proportional to the signal, $K_a c$ from 0.1 to 1000, four inputs stated at 3–10 % and every entered value drawn at exactly the $\sigma$ stated for it:

| Assay | fits | input-aware | conditional | closed intervals only (aware / conditional) |
|---|---|---|---|---|
| GDA | 1440 | 0.986 | 0.926 | 0.972 / 0.799 |
| IDA | 1559 | 0.965 | 0.720 | 0.966 / 0.717 |
| DBA host→dye | 1440 | 0.958 | 0.801 | 0.949 / 0.776 |
| DBA dye→host | 1549 | 0.974 | 0.923 | 0.963 / 0.870 |

The conditional interval is not wrong in these runs; it answers the narrower question, and the gap is the price of taking entered numbers as exact when they are not. Where the entry error is larger than stated, the input-aware interval degrades gracefully rather than collapsing: with an error of three times the stated $\sigma$ planted in $h_0$ (IDA, 20 points, 0.5 % noise, 100 datasets) it covered 0.94 against 0.49 for the conditional one. It is usually the wider of the two, and comes out narrower in a small minority of consistent fits, where moving an input explains a departure the entered values could not.

**When it is refused.** $\nu < 1$ — the data cannot support the model *and* the inputs they are asked to free — is refused in plain language naming the inputs, the continuous form of the $n - p < 1$ rule of Section 6.2. Holding an input at its entered value, or measuring more points, is what that message asks for.

**Replicates** are handled as in Section 6.4: the interval is computed on the average of the replicates used, in the same residual-variance form, which is what makes it reduce to the conditional interval when nothing varies. The replicates' own scatter is used instead for the lack-of-fit test of Section 8.1.

### 7.3. How the Profile Is Computed

At a fixed $k$ the inner problem over $x = (\text{the other free } \log_{10} K,\ \mathbf{e})$ is solved by a bounded trust-region least-squares solve (`scipy.optimize.least_squares`, TRF, finite-difference Jacobian) on the stacked residual $[\,\mathbf{r}(k, x)/s\ ;\ \mathbf{z}(x)\,]$, where $\mathbf{r}$ is the projected residual $\mathbf{y} - A\mathbf{c}$ at the shifted inputs. That objective is $S/s^2 + \mathbf{z}'\mathbf{z}$, which equals the profile objective only at the fixed point $s^2 = S/n$; the fixed point is found by a bracketed secant iteration on $g(u) = \log(S/n) - u$ with $u = \log s^2$, each step one warm-started solve. $g$ decreases in $u$ with slope in $[-1, -\tfrac{1}{2}]$, so the sign of $g$ at every visited $u$ brackets the root, and a secant step is taken only inside the bracket and clipped to between one and two Picard steps. Two to six steps reach $|g| < 10^{-6}$; the profile value is stationary in $x$, so an error $\delta$ in the scale moves $P$ by $O(\delta^2)$, and $P$ is converged to $10^{-9}$ there.

The profile is traced rather than swept: from the search-grid node nearest the conditional fit outwards in both directions on the four-per-decade grid of Section 4.1, each node started from its neighbour's solution, the trace stopping two acceptance excesses above the running minimum; the optimum by bounded Brent between the neighbours of the best node; the edges by root-finding on $P(k) - \text{threshold}$ between the outermost accepted point and the first rejected node; and a coarse continuation of one node per decade to the ends of the $K_a$ box, which fills its decade at full resolution wherever it finds a second stretch below the threshold. Against a full double-continuation scan of every node of the box on 60 random IDA designs, the trace agreed on every edge to $3.5\times10^{-11}$ decades, on the optimum to $1.2\times10^{-6}$ (the resolution of Brent itself) and on every split flag, at a median 24 of 81 nodes solved. A second accepted region narrower than one decade and more than two excesses beyond the traced stretch is the resolution this trades away; the conditional profile is swept across the whole box and carries such a split where it exists.

Every profile value is a pure function of the $k$ it is asked at and of the start points it is solved from, and the start points come only from the table of solved nodes — never from the previous evaluation — so root finding cannot change a value through the order of its calls, and the construction draws no random numbers. Cost, one process per core: a residual evaluation is one moved copy of the assay, one species solve and one bounded linear solve, and an interval takes 5000 to 15 000 of them. Over 5760 random one-constant titrations of 8 and 20 points the input-aware part took a median of 0.4–1.8 s depending on the assay (99th percentile 2.0–5.0 s, maximum 20.5 s), and over 1080 stepwise fits a median of 3.7 s (99th percentile 9.5 s, maximum 47 s). The tail is fits whose interval edge sits where a signal coefficient reaches its bound and the solver creeps; capping its evaluations halves the tail and moves an edge by up to $1.6\times10^{-3}$ decades, so they are not capped. Cancellation is checked before every evaluation.

## 8. Model Checking and the Consistency of the Inputs

An interval is a statement made *within* a model. Two questions are asked beside it and answered from the fit itself: does the curve miss the data by more than the data's own scatter allows, and did the inputs have to move further than the user said they could? Both tests are computed at the conditional fit and at the input-aware fit, which is what separates *the inputs explain the miss* from *the model misses whatever the inputs do*. The two tests are judged together, by Holm's step-down procedure at $5\,\%$ over those of the two that ran (the misfit test at the input-aware fit and the conflict statistic): the smaller $p$-value against $2.5\,\%$ and, if it rejects, the other against $5\,\%$. Where each test holds its own level, the chance that either names a cause when the model holds and the inputs are as stated is then at most $5\,\%$, where two tests at $5\,\%$ each reach up to twice that; a test that rejects more often than its level carries its excess into the verdict, so the verdict's rate is measured by the validation check `verdict-false-alarm` rather than assumed. Each test reports its own $p$-value.

### 8.1. Does the Model Describe the Data

**With two or more replicates** the scatter of the replicates estimates the noise without using the model at all, and the lack-of-fit $F$ test (Draper & Smith 1998) compares the misfit of the fitted curve with it:

$$F = \frac{m \sum_i \omega_i \big(\bar{y}_i - f_i\big)^2 \big/ (n - p)}{\sum_{r,i} e_{ri}^2 \big/ \big((m-1)(n-2)\big)}, \qquad \text{d.f. } \big(n - p,\; (m-1)(n-2)\big),$$

with $f$ the fitted curve, $\boldsymbol\omega$ the point weights and $\mathbf{e}$ the whitened scatter of each replicate about its own affine image of the mean curve, both from Section 4.4. Numerator and denominator carry the same weights, so only their ratios matter, and with $\boldsymbol\omega = \mathbf{1}$ this is the unweighted test. The numerator has expectation $(n-p)$ times the noise variance because $\operatorname{var}(\bar{y}_i) = \sigma^2/(m\,\omega_i)$; the denominator counts $n - 2$ dimensions per replicate, the two columns $[\mathbf{1}, \bar{\mathbf{y}}]$ being projected out, less the one replicate the mean costs, since the $\mathbf{e}_r$ sum to zero across replicates. The deviations of the replicates from their mean are independent of the mean, so the two are independent and the ratio is exactly $F$ under normal noise of the variance the law states.

**Why the detrended scatter and not the raw spread.** $\sum_{r,i}(y_{ri} - \bar{y}_i)^2$ counts the affine difference between replicates — a lamp or gain difference the model follows exactly (Section 4.4) — as noise, and inflates the denominator until the test cannot fire. With a replicate scale factor of 3 %, the size of the ones the datasets in `data/` show, the raw pure error rejects 1.3 % ($m = 2$) to 0.1 % ($m = 8$) of consistent fits at the 5 % level, where the scatter used here rejects 4.7 to 5.6 % (4 000 linearised draws per cell, 12 points, three parameters, the weights known). Those are the rates for weights fixed beforehand, where the ratio is exactly $F$. A fit takes its weights from the law of Section 4.4, read from the same replicates, so numerator and denominator share one estimated share and the ratio is $F$ only approximately: in the same linearised construction — constant noise, proportional noise, and constant noise with the 3 % scale factor — it rejects 4.7 to 7.5 % of consistent fits at the 5 % level, the most at $m = 2$ (3 000 draws per cell, $m = 2, 4, 8$). The rate through the whole fit is measured by the validation check `noise-law-lof-null`.

The parameter count $p$ is the one of Section 7.2 at both fits: the inputs the data determine are not subtracted, which makes the test at the input-aware fit slightly lenient ($E[F] \le 1$ under the null) rather than falsely alarming.

**Data with no scatter.** Neither misfit test — the $F$ test above nor the runs test below — is run when the scatter it would be judged against is below $10^{-10}$ of the signal's variance per point — the resolution the engine reads every residual at (Section 6.2), a scatter under $10^{-5}$ of the signal's spread. Noise-free titrations leave residuals of $10^{-12}$ to $10^{-8}$ of their spread, set by how finely the search resolves $K_a$ rather than by rounding, and replicates that agree to the last bit leave a pure error at rounding; a test on either would judge the solver's stopping point. The report says the data carry no scatter to judge the curve against.

**With a single replicate** there is no model-free noise estimate, and the question falls to the *signs* of the residuals along the titration: a systematic departure leaves long runs of one sign, so few runs speak against the model. Residuals of a fitted curve are not exchangeable — the fit removes what its parameters can follow, which makes their signs alternate more than independent ones — so the reference is the fitted model's own: the number of runs of $(I - JJ^{+})\mathbf{e}$ for standard normal $\mathbf{e}$, with $J$ the Jacobian of the whole fit (free signal columns, association constants, and the inputs with their penalty rows), 100 000 draws at a fixed seed, and the $p$-value the mid-$p$ $P(\text{fewer}) + P(\text{as many})/2$ because the statistic takes few values. Measured on 4800 fits of correct one-constant models, this reference raises a false alarm at the 5 % level in 2.3, 5.6, 4.7 and 3.8 % of fits at 8, 12, 20 and 30 points and detects a 15 % error in the titrant scale in 13, 24, 31 and 35 %; the permutation distribution of the same statistic (Wald & Wolfowitz 1940), which assumes exchangeable signs, rejects 0.0–1.5 % of those correct fits and detects 1–28 %. A Durbin–Watson statistic against the same reference has more power against smooth misfit (19–24 % against a 2 % sinusoidal departure at 20–30 points, where the runs test reaches 12–14 %) and less against a step.

### 8.2. Did the Inputs Have to Move Too Far

The fitted shifts $\hat{e}_j$ are reported per **source** — an input's own uncertainty or a source several inputs share — in percent of the entered value and, for a source stated with a $\sigma$, in units of that $\sigma$, $\hat{z}_j = \hat{e}_j / s_j$; a shared source is reported with the inputs it moves named beside it. Whether they agree with what was stated is one statistic. Linearised at the optimum, the penalised estimate satisfies

$$\hat{\mathbf{z}} \sim N(0, V), \qquad V = I - \big[H^{-1}\big]_{zz}, \qquad H = J'J,$$

with $J$ the Jacobian of the stacked residual over the free association constants and the varying sources, its residual rows in units of the fit's own noise scale $s = \sqrt{S_{\min}/n}$ — the Jacobian the last inner solve has already computed, since the projected residual's Jacobian carries the same $(K, \mathbf{e})$ block as the full one (Golub & Pereyra 1973). An association constant the fit left on an end of its search box, and an input stated as a range that the fit left on an end of that range, are held there, like a signal parameter on its bound, and their columns stay out of $J$: free, it would absorb part of what the data say about the other inputs, and the weights would come out too small for the shifts the fit actually made. $[H^{-1}]_{zz}$ is read off the singular value decomposition of $J$ with every column scaled to unit length, so the units of a column do not decide which directions count as informed and the condition number of $J$ is not squared. The eigenvalues of $V$ are $g/(1+g)$ for the information $g$ the data hold about each input direction: 1 where the data determine an input, 0 along a direction they cannot see, such as a common scale of every concentration. The statistic is the squared length of $\hat{\mathbf{z}}$ along the informed directions,

$$q = \sum_{i:\,w_i \ge 0.01} \big(\mathbf{v}_i'\hat{\mathbf{z}}\big)^2 \;\sim\; \sum_i w_i\,\chi^2_1 \quad\text{under the null,}$$

and its $p$-value is $P(q_{\text{null}} \ge q)$ from 200 000 draws of that weighted sum at a fixed seed — a deterministic quadrature of the distribution of a quadratic form in normal variables (Imhof 1961), with Monte Carlo error $5\times10^{-4}$ at $p = 0.05$ and the noise scale estimated from the fit's own residual. It costs one Jacobian and no refit.

Directions of weight below 0.01 are left out: such a direction's whole null range is under $0.1\,\sigma$ — the last digit a shift is reported to — and what the fit shows along it is model curvature and the solver's stopping point rather than evidence. Taken into the statistic, they made 21–37 % of consistent fits look like conflicts in stoichiometric DBA and in the stepwise models. A specification of ranges only, or one in which no direction is informed, has no statistic at all, and the report then says the data cannot check the entered inputs.

Referring $q$ to $\chi^2_k$ instead, as if every direction were fully informed, is what makes that test dead: on a calibration run (IDA, 12 points, 0.5 % noise, inputs stated at 10/3/3/3 %, 300 datasets per row) the mean weights were $(0,\,0,\,0.23,\,0.92)$ — with 12 points the data inform two of the four input directions — and $\chi^2_4$ rejected 0.3 % of consistent fits and 25 % of fits entered three $\sigma$ off, where the reference above rejected 6.3 % and 53 %.

Measured across the validation sweep (8 to 30 points, 0.5–3 % noise, $K_a c$ from 0.1 to 1000, inputs entered at exactly their stated $\sigma$), among the fits that have a direction to test — 44–57 % of the one-constant fits, 38 % of H2G and 61 % of HG2 — the 5 % level rejects 3.1 % (GDA), 4.9 % (IDA), 5.6 and 3.2 % (DBA host-to-dye and dye-to-host; 6468 fits), 6.4 and 7.8 % (HG2, H2G; 1080 fits). With the inputs entered three times their stated $\sigma$ off it flags 7–34 % of fits, depending on how much the design says about the inputs.

**The statistic judges the inputs together.** A titration usually determines one or two *combinations* of the inputs — $h_0$ and the titrant scale move the curve almost alike — so the shift reported against a single input says where the fit put the correction, not which stock is wrong. With a three-$\sigma$ error planted in $h_0$, the largest $|z|$ sat on $h_0$ in well under two thirds of the fits that flagged a conflict, and a conflict can be significant with every individual $|z|$ below 1. Every user-facing sentence is worded that way: the app asks for the stated inputs to be checked, and names none of them as the cause.

### 8.3. The Verdict

The three results — the misfit test at the conditional fit, the misfit test at the input-aware fit, and the conflict statistic — are read in one fixed order, the last two judged together as above:

1. **The inputs conflict with what was stated, and the model misses the data even so**, when both the conflict statistic and the misfit test at the input-aware fit reject. An input error can itself make the curve miss, so the report names the inputs first.
2. **The inputs conflict with what was stated**, when $q$ rejects.
3. **The model does not describe the data**, when the misfit test rejects at the input-aware fit (with no varying input: at the conditional fit).
4. **The inputs explain the misfit**, when neither rejects and the misfit test fails at the conditional fit, judged at the threshold the misfit test faced in the procedure: it is the same test at other inputs, and a miss the shifted inputs left as it was is no miss they explain.
5. **No test found evidence against the model or the entered inputs**, otherwise. This is a statement about the tests, not a finding that the model and the inputs are right, and the report names any test that could not run and why: no scatter to judge a curve against, too few residual degrees of freedom, no input stated with a standard deviation, or no input direction the data inform.

The interval is reported in every case, with the verdict beside it. Withholding it under the first verdict would blank one good fit in twenty on a false alarm of the misfit test, and an interval that is correct conditional on the model, shown with a sentence saying the model is in doubt, states more than an empty cell. All three inputs of the decision are stored with the result, so what is shown can change without recomputing anything.

## 9. Input Sensitivity: Sobol' Variance Decomposition

The interval of Section 7 says how wide the uncertainty of $K_a$ is when the entered inputs are uncertain. The sensitivity analysis answers the other questions about that statement: *which* error it comes from, how much of $K_a$ it accounts for in absolute terms, and what a smaller error would buy. The error model of Section 7.1 is read here as a distribution to draw from, and the fit is repeated over it, every sample holding its own drawn inputs as exact: a propagation of the **stated** uncertainties in the sense of GUM Supplement 1 (JCGM 101:2008). Every draw counts the same, however well the data agree with it, whereas the input-aware interval also weighs what the data say about the inputs; the two answer different questions and can differ.

A constant's indices, budget, what-if and elasticities are withheld, with the reason stated, when its fit at the entered inputs rests on an end of its search box, when its conditional interval is open, or when its own refits miss the scaling identity of Section 9.6 by more than the resolution of the refits allows: in each case the local derivatives the budget rests on describe the box, not the data.

### 9.1. Error Sources and Their Distributions

What is drawn, decomposed and reported is one offset per **source**, not per input, because a source is the physical thing an experimenter can act on: one stock to re-make, one pipette to recalibrate. Three kinds appear:

- an input's **own** uncertainty — one offset moving that input;
- a **shared** source — one offset moving every input it loads, by the same fraction;
- the **random error of each addition** — $n$ offsets, one per titration point, reported as a single item (Section 9.5).

Each offset is drawn independently, through its inverse CDF, so the same definition serves plain random draws and a low-discrepancy sequence alike: a $\sigma$ (in percent of nominal, or in the input's own unit) draws from a normal distribution truncated at zero, so a concentration never goes negative; a range draws uniformly between its ends, the form in which a $K_a$ carried over from an earlier fit naturally arrives. A shared source is a precision figure of one physical object, so it is a $\sigma$ in percent and nothing else. An input loaded by several sources takes the product of their factors, exactly as in Section 7.1, with a binding constant loaded by the inverse factor.

The titrant's own entry is **one common factor**: a single draw scales the whole concentration vector, which is how a mis-calibrated stock solution acts — it displaces every titration point together. With the stock declared (Section 3.4) the same draw scales $c_T$, because the titrant's scale error *is* the stock's concentration error: $x_i = c_T \varphi_i$, and $\varphi_i$ is a ratio of volumes that a concentration error cannot move. The stock is therefore not an input of its own.

### 9.2. Estimators

For output $Y = \log_{10} K_a$ and inputs $X_1 \dots X_k$, the first-order and total-order Sobol' indices (Sobol' 2001) are

$$S_i = \frac{\operatorname{Var}_{X_i}\!\big(E[Y \mid X_i]\big)}{\operatorname{Var}(Y)}, \qquad S_{T_i} = \frac{E\!\big[\operatorname{Var}(Y \mid X_{\sim i})\big]}{\operatorname{Var}(Y)}$$

They are estimated on a Saltelli design: two independent sample matrices $A$ and $B$ and one matrix $AB_g$ per reported source, which takes that source's columns from $B$ — $N \times (g + 2)$ fits for $g$ reported sources. A source with one offset contributes one column; the additions contribute all of theirs, taken from $B$ **together**, and the same two estimators applied to $AB_g$ then give the closed first-order index $\operatorname{Var}(E[Y \mid \mathbf{e}_g]) / \operatorname{Var}(Y)$ and the total index of that group of columns (Jacques, Lavergne & Devictor 2006). The cost of the analysis therefore depends on how many *sources* were stated, not on how many titration points they move. First order uses the Saltelli et al. (2010) estimator and total order the Jansen (1999) estimator:

$$\hat{S}_i = \frac{\frac{1}{N}\sum_j f(B)_j\big(f(AB_i)_j - f(A)_j\big)}{\hat{V}}, \qquad \hat{S}_{T_i} = \frac{\frac{1}{2N}\sum_j \big(f(A)_j - f(AB_i)_j\big)^2}{\hat{V}}$$

The outputs are centred on the mean of $A$ and $B$ before either estimator is applied. Neither expectation changes under a constant shift, but the variance of the first-order estimator grows with the square of the output mean, and $\log_{10} K_a$ sits near 8 with a spread of a few tenths — uncentred, the first-order indices would be buried in that offset.

$\log_{10} K_a$ rather than $K_a$ is decomposed because an association constant varies multiplicatively over orders of magnitude; a variance decomposition of $K_a$ itself would be dominated by whichever input happens to push it highest.

### 9.3. Sampling Error of an Index

The design is built from $B = 8$ **independently scrambled** Sobol' blocks (Owen 1997; L'Ecuyer & Lemieux 2002), each the first $N/B$ points of its own scrambled sequence. The indices come from all usable rows pooled; leaving each block out in turn gives a delete-one-block jackknife standard error (Archer, Saltelli & Sobol' 1997),

$$\mathrm{SE} = \sqrt{\frac{B-1}{B}\sum_j \big(\hat{\theta}_{(j)} - \bar{\hat{\theta}}\big)^2}, \qquad \text{CI} = \hat{\theta} \pm t_{B-1,\,0.975}\,\mathrm{SE}$$

The blocks are independent replicates of one design; the rows *inside* a scrambled block are not independent draws and cannot stand in for them. The interval covers the Monte Carlo sampling error of one index at a time — not error in the stated input uncertainties, and not model error. It is symmetric and is not clipped to $[0, 1]$, so a small index can show a negative lower end.

`python -m validation run sobol-coverage` measures the calibration and `validation/README.md` carries the table it prints: up to 400 designs each of the Ishigami function and of a six-input g-function at the sizes the analysis offers, how often the nominal 95 % interval held the analytically known index, and the signed error of every estimate, whose median over the designs is the estimator's bias and whose root mean square is the scatter the interval has to cover. `python -m validation run sobol-blocking` measures the price of blocking: at a fixed budget, eight blocks raise the root-mean-square error of an index by up to a factor of about five, index by index — a few indices are barely affected — over a single undivided scramble, which is the cost of having an error bar at all.

### 9.4. Every Sample Is Kept

Each sample is refitted by the projection of Section 4.1, on the average of the replicates the reported fit used and with its own drawn inputs held exact, so its $K_a$ is the best the model can do for them; the run's baseline is that same projection at the inputs as entered, and with the point weights of the baseline's noise law: a perturbation of the entered inputs leaves the measured replicates untouched, so the law is a constant of the run and re-using it makes the baseline the sample with no offset by construction. Each sample's place on the weighted axis of Section 6.1 is recorded beside its unweighted $R^2$, so the samples the Identifiability tab draws sit on the same scale as the profile there. Every sample counts, however poorly it describes the data. Discarding the poor ones would remove precisely the input combinations the data disagree with, which would bias the sampled distribution back towards the inputs as entered and make the analysis look more reassuring than the evidence allows.

Because every refit is one deterministic projection, the spread the analysis reports is the effect of the stated input uncertainties and nothing else — there is no search scatter mixed into it. The analysis therefore covers every assay with an association constant, the stepwise two-constant models included; a model with no association constant has nothing to decompose.

### 9.5. The Random Error of Each Addition

The titrant's own entry moves the whole series by one factor. The scatter of the *individual* additions is a separate statement: a standard deviation $\sigma_\delta$ in percent, and the mode of preparation, which fixes how the errors accumulate. With $w_i = W_i/V_0 = x_i/(c_T - x_i)$ — the volume ratio, which is $x_i$ itself in the undiluted limit $c_T \to \infty$ — the exact transform for unequal aliquots is

$$\text{sequential:}\quad w'_i = \sum_{j \le i} (w_j - w_{j-1})(1 + \delta_j), \qquad \text{separate samples:}\quad w'_i = w_i (1 + \delta_i),$$

followed by $x'_i = c_T w'_i / (1 + w'_i)$. For equal aliquots the sequential case reproduces the familiar accumulation — a relative standard deviation of $\sigma_\delta/\sqrt{i}$ at point $i$, correlated across points — without assuming equal aliquots anywhere. Sequential mode requires $x$ non-decreasing in file order and refuses otherwise, naming the first point that falls.

Which of the two modes costs more variance depends on the design, so the mode is the user's statement and not a default. Replicates are separate titrations with independent addition errors, and the reported fit is of their average, whose first-order addition error is the mean of $m$ independent ones; the analysis therefore draws $\delta$ at $\sigma_\delta/\sqrt{m}$ for $m$ replicates used.

The item is reported and ranked beside the other sources; the interval the fit reports does not include it (Section 7.1).

### 9.6. The Absolute Budget, Elasticities and the Scaling Identity

**From shares to decades.** The same run is read once more as absolute numbers, per association constant. With $V = \operatorname{Var}(Y)$ over the usable $A$ and $B$ rows, $Y = \log_{10} K_a$:

$$\mathrm{SD} = \sqrt{V} \ \text{decades}, \qquad V_i = S_i V, \qquad \mathrm{SD}_{-i} = \sqrt{\max(V - V_i,\, 0)}.$$

$\mathrm{SD}_{-i}$ is the spread that would be left if source $i$ were exact, and it is the **first-order** index that answers that question, by the law of total variance $E[\operatorname{Var}(Y \mid e_i)] = V(1 - S_i)$; the total index answers a different one. Every quantity above joins the jackknifed vector of Section 9.3 and carries its own 95 % interval — the interval of $V_i$ is not that of $S_i$ scaled by $V$, because $V$ has a sampling error of its own. What no single source explains alone, $1 - \sum_i S_i$, is reported with its sign as *interactions*, being an estimate like the rest.

**What a smaller error would buy.** Reducing source $i$ from $s$ to $r s$, $0 \le r \le 1$, gives

$$V' = V - V_i\,(1 - r^2),$$

exact when the model is additive in $e_i$ with a linear effect and first order otherwise. The same question is answered a second time with no further fits and no such assumption, by importance re-weighting (Kahn & Marshall 1953): each sample is weighted by $w = \mathrm{pdf}'(e_i)/\mathrm{pdf}(e_i)$, the ratio of the narrowed sampling density to the one it was drawn from, and $V'_w = \sum w (y - \bar y_w)^2 / \sum w$ recomputed with an effective sample size $(\sum w)^2 / \sum w^2$. Re-weighting can only narrow a density — weights towards a wider one are unbounded — so only reductions are offered, and the cross-check is shown only while enough samples carry weight for it to be more precise than the formula's own error. It is not offered for the additions group, where a product of $n$ weights collapses.

**Elasticities.** Beside the shares the run reports $s_j = \partial \ln K_a / \partial \ln \theta_j$ for every perturbable input, varying or not, by a central difference at a relative step of $10^{-3}$ — two refits per input, added to the same batch. The step is a measured compromise: the truncation error of the central difference falls as the step squared while the resolution of the refit ($10^{-7}$ decades) divided by the step rises, and $10^{-3}$ sits below $10^{-5}$ truncation with about $10^{-4}$ of resolution noise across all six assays. A source's elasticity is the sum over the inputs it loads, to first order, which is what makes cancellation between them visible.

**The scaling identity.** Every registered model is built from mass balances and association constants of unit M$^{-1}$ alone. Multiplying every concentration — fixed totals, titrant and titrant stock — by $c$ and every *entered* binding constant by $1/c$ multiplies every species concentration by $c$; the signal coefficients (au/M) absorb the $1/c$ and the offset is unchanged, so the least-squares problem is identical and every fitted constant is divided by $c$:

$$F(c\,\theta_{\text{conc}},\; K_{\text{known}}/c) \;=\; F(\theta)/c.$$

Differentiating at $c = 1$ (Euler's theorem on homogeneous functions) gives, for **each** fitted constant,

$$\sum_{j \,\in\, \text{concentrations}} s_j \;-\; \sum_{j \,\in\, \text{entered binding constants}} s_j \;=\; -1,$$

that is $s_{h_0} + s_{d_0} + s_{\text{titrant}} - s_{K_{a,\text{dye}}} = -1$ for IDA (with $g_0$ for $d_0$ in GDA), $s_{\text{fixed}} + s_{\text{titrant}} = -1$ for both DBA directions, and $s_{h_0} + s_{\text{titrant}} = -1$ for each constant of the stepwise models. It holds with dilution declared, since the stock scales with the titrant, and it needs no bound to be active at the fit, since bounds do not scale.

Two consequences follow for the budget. A source loading every concentration of a **competitive** assay has elasticity exactly $s_{K_{a,\text{dye}}} - 1$: it cancels only as far as $s_{K_{a,\text{dye}}}$ is close to 1, which holds for strong dye binding and not in general, and when $K_{a,\text{dye}}$ was itself measured with the same stock the source loads it too, with the inverse factor, and its elasticity is $-1$. In **direct binding** the same source has elasticity exactly $-1$ — a 1 % error of the concentration scale is a 1 % error of $K_a$, which no amount of data removes — and it therefore contributes exactly $\operatorname{Var}(\log_{10}(1 + e))$ to the budget, additively, with $S_T = S_1$. That closed form is the reference the check `source-variance-exact` holds the budget's interval of $V_i$ against; `budget-coverage` does the same for $V$, $V_i$, $\mathrm{SD}_{-i}$ and a grouped index on the Ishigami and g-function test problems, and `what-if-accuracy` compares both what-if answers against a second run made at the reduced $\sigma$. The identity itself is a property of the models and says nothing about the user's data, so it is not displayed; every Sobol' run evaluates $\sum_{\text{conc}} s_j - \sum_{\text{entered } K} s_j$ from its own elasticity refits and withholds a constant's numbers when that sum misses $-1$ by more than $10 \cdot 2k\,\delta_{\log K} \ln 10 / h$ for $k$ inputs — ten times the refit resolution $\delta_{\log K} = 10^{-7}$ decades carried through the central difference of span $h = 2\times10^{-3}$. Identified fits of every assay meet it within $6\times10^{-4}$; flat profiles miss it by 0.85 to over 2000.

## 10. General Theoretical Workflow Diagram

![Workflow Diagram](fitting_workflow.jpg)
