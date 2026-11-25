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

### Assays

1. Sinn, S., Spuling, E., Bräse, S., & Biedermann, F. (2019). Rational design and implementation of a cucurbit[8]uril-based indicator-displacement assay for application in blood serum. *Chemical Science*, 10(27), 6584-6593. <https://doi.org/10.1039/C9SC00705A>
2. Sinn, S., Krämer, J., & Biedermann, F. (2020). Teaching old indicators even more tricks: binding affinity measurements with the guest-displacement assay (GDA). *Chemical Communications*, 56(49), 6620-6623. <https://doi.org/10.1039/D0CC01841D>

### Fitting and reporting binding constants

3. Thordarson, P. (2011). Determining association constants from titration experiments in supramolecular chemistry. *Chemical Society Reviews*, 40(3), 1305-1323. <https://doi.org/10.1039/C0CS00062K>
4. Hibbert, D. B., & Thordarson, P. (2016). The death of the Job plot, transparency, open science and online tools, uncertainty estimation methods and other developments in supramolecular chemistry data analysis. *Chemical Communications*, 52(87), 12792-12805. <https://doi.org/10.1039/C6CC03888C>
5. Kazmierczak, N. P., Chew, J. A., & Vander Griend, D. A. (2022). Bootstrap methods for quantifying the uncertainty of binding constants in the hard modeling of spectrophotometric titration data. *Analytica Chimica Acta*, 1227, 339834. <https://doi.org/10.1016/j.aca.2022.339834>

### Software for binding and equilibrium constants

6. Hübler, C. (2022). SupraFit — an open source Qt based fitting application to determine stability constants from titration experiments. *Chemistry–Methods*, 2(7), e202200006. <https://doi.org/10.1002/cmtd.202200006>
7. Masson, E. (2026). Equilibrist: a browser-based platform for fitting equilibrium and rate constants from optical and NMR data. *Journal of Chemical Information and Modeling*, 66(16), 9976-9988. <https://doi.org/10.1021/acs.jcim.6c01004>
8. Kuzmič, P. (2009). DynaFit — a software package for enzymology. *Methods in Enzymology*, 467, 247-280. <https://doi.org/10.1016/S0076-6879(09)67010-5>
9. Kuzmič, P. (2018). *DynaFit Scripting*, manual version 4.08.005, section 9.3.11.5. BioKin Ltd. <http://www.biokin.com/dynafit/pdf/scripting.pdf>
10. Zhao, H., Piszczek, G., & Schuck, P. (2015). SEDPHAT — a platform for global ITC analysis and global multi-method analysis of molecular interactions. *Methods*, 76, 137-148. <https://doi.org/10.1016/j.ymeth.2014.11.012>
11. Piñeiro, Á., Muñoz, E., Sabín, J., Costas, M., Bastos, M., Velázquez-Campoy, A., et al. (2019). AFFINImeter: a software to analyze molecular recognition processes from experimental data. *Analytical Biochemistry*, 577, 117-134. <https://doi.org/10.1016/j.ab.2019.02.031>
12. Johnson, K. A., Simpson, Z. B., & Blom, T. (2009). FitSpace Explorer: an algorithm to evaluate multidimensional parameter space in fitting kinetic data. *Analytical Biochemistry*, 387(1), 30-41. <https://doi.org/10.1016/j.ab.2008.12.025>
13. Gans, P., Sabatini, A., & Vacca, A. (1996). Investigation of equilibria in solution. Determination of equilibrium constants with the HYPERQUAD suite of programs. *Talanta*, 43(10), 1739-1753. <https://doi.org/10.1016/0039-9140(96)01958-3>
14. Newville, M., Stensitzki, T., Allen, D. B., & Ingargiola, A. (2014). *LMFIT: Non-Linear Least-Square Minimization and Curve-Fitting for Python*. Zenodo. <https://doi.org/10.5281/zenodo.11813>

### Nonlinear regression and profile likelihood

15. Bates, D. M., & Watts, D. G. (1988). *Nonlinear Regression Analysis and Its Applications*. Wiley. <https://doi.org/10.1002/9780470316757>
16. Seber, G. A. F., & Wild, C. J. (1989). *Nonlinear Regression*. Wiley. <https://doi.org/10.1002/0471725315>
17. Venzon, D. J., & Moolgavkar, S. H. (1988). A method for computing profile-likelihood-based confidence intervals. *Journal of the Royal Statistical Society: Series C*, 37(1), 87-94. <https://doi.org/10.2307/2347496>
18. Raue, A., Kreutz, C., Maiwald, T., Bachmann, J., Schilling, M., Klingmüller, U., & Timmer, J. (2009). Structural and practical identifiability analysis of partially observed dynamical models by exploiting the profile likelihood. *Bioinformatics*, 25(15), 1923-1929. <https://doi.org/10.1093/bioinformatics/btp358>
19. Golub, G. H., & Pereyra, V. (1973). The differentiation of pseudo-inverses and nonlinear least squares problems whose variables separate. *SIAM Journal on Numerical Analysis*, 10(2), 413-432. <https://doi.org/10.1137/0710036>
20. Golub, G., & Pereyra, V. (2003). Separable nonlinear least squares: the variable projection method and its applications. *Inverse Problems*, 19(2), R1-R26. <https://doi.org/10.1088/0266-5611/19/2/201>
21. Self, S. G., & Liang, K.-Y. (1987). Asymptotic properties of maximum likelihood estimators and likelihood ratio tests under nonstandard conditions. *Journal of the American Statistical Association*, 82(398), 605-610. <https://doi.org/10.1080/01621459.1987.10478472>

### The noise of the measurement

22. Rocke, D. M., & Lorenzato, S. (1995). A two-component model for measurement error in analytical chemistry. *Technometrics*, 37(2), 176-184. <https://doi.org/10.1080/00401706.1995.10484302>
23. Carroll, R. J., & Ruppert, D. (1988). *Transformation and Weighting in Regression*. Chapman & Hall. <https://doi.org/10.1007/978-1-4899-2873-3>
24. Davidian, M., & Carroll, R. J. (1987). Variance function estimation. *Journal of the American Statistical Association*, 82(400), 1079-1091. <https://doi.org/10.1080/01621459.1987.10478543>

### Uncertain inputs and model checking

25. JCGM 100:2008. *Evaluation of measurement data — Guide to the expression of uncertainty in measurement*. Joint Committee for Guides in Metrology. <https://doi.org/10.59161/JCGM100-2008E>
26. JCGM 101:2008. *Evaluation of measurement data — Supplement 1 to the "Guide to the expression of uncertainty in measurement" — Propagation of distributions using a Monte Carlo method*. Joint Committee for Guides in Metrology. <https://doi.org/10.59161/JCGM101-2008>
27. Carroll, R. J., Ruppert, D., Stefanski, L. A., & Crainiceanu, C. M. (2006). *Measurement Error in Nonlinear Models: A Modern Perspective* (2nd ed.). Chapman & Hall/CRC. <https://doi.org/10.1201/9781420010138>
28. Cowan, G., Cranmer, K., Gross, E., & Vitells, O. (2011). Asymptotic formulae for likelihood-based tests of new physics. *The European Physical Journal C*, 71(2), 1554. <https://doi.org/10.1140/epjc/s10052-011-1554-0>
29. Hodges, J. S., & Sargent, D. J. (2001). Counting degrees of freedom in hierarchical and other richly-parameterised models. *Biometrika*, 88(2), 367-379. <https://doi.org/10.1093/biomet/88.2.367>
30. Draper, N. R., & Smith, H. (1998). *Applied Regression Analysis* (3rd ed.). Wiley. <https://doi.org/10.1002/9781118625590>
31. Wald, A., & Wolfowitz, J. (1940). On a test whether two samples are from the same population. *The Annals of Mathematical Statistics*, 11(2), 147-162. <https://doi.org/10.1214/aoms/1177731909>

### Sensitivity analysis

32. Sobol', I. M. (2001). Global sensitivity indices for nonlinear mathematical models and their Monte Carlo estimates. *Mathematics and Computers in Simulation*, 55(1-3), 271-280. <https://doi.org/10.1016/S0378-4754(00)00270-6>
33. Saltelli, A., Annoni, P., Azzini, I., Campolongo, F., Ratto, M., & Tarantola, S. (2010). Variance based sensitivity analysis of model output. Design and estimator for the total sensitivity index. *Computer Physics Communications*, 181(2), 259-270. <https://doi.org/10.1016/j.cpc.2009.09.018>
34. Jansen, M. J. W. (1999). Analysis of variance designs for model output. *Computer Physics Communications*, 117(1-2), 35-43. <https://doi.org/10.1016/S0010-4655(98)00154-4>
35. Jacques, J., Lavergne, C., & Devictor, N. (2006). Sensitivity analysis in presence of model uncertainty and correlated inputs. *Reliability Engineering & System Safety*, 91(10-11), 1126-1134. <https://doi.org/10.1016/j.ress.2005.11.047>
36. Matoušek, J. (1998). On the L2-discrepancy for anchored boxes. *Journal of Complexity*, 14(4), 527-556. <https://doi.org/10.1006/jcom.1998.0489>
37. L'Ecuyer, P., & Lemieux, C. (2002). Recent advances in randomized quasi-Monte Carlo methods. In *Modeling Uncertainty* (pp. 419-474). Springer. <https://doi.org/10.1007/0-306-48102-2_20>
38. Efron, B. (1982). *The Jackknife, the Bootstrap and Other Resampling Plans*. SIAM. <https://doi.org/10.1137/1.9781611970319>
39. Shao, J., & Tu, D. (1995). *The Jackknife and Bootstrap*. Springer. <https://doi.org/10.1007/978-1-4612-0795-5>
40. Archer, G. E. B., Saltelli, A., & Sobol', I. M. (1997). Sensitivity measures, ANOVA-like techniques and the use of bootstrap. *Journal of Statistical Computation and Simulation*, 58(2), 99-120. <https://doi.org/10.1080/00949659708811825>
41. Kahn, H., & Marshall, A. W. (1953). Methods of reducing sample size in Monte Carlo computations. *Journal of the Operations Research Society of America*, 1(5), 263-278. <https://doi.org/10.1287/opre.1.5.263>

### Replicates

42. Hadi, A. S., & Simonoff, J. S. (1993). Procedures for the identification of multiple outliers in linear models. *Journal of the American Statistical Association*, 88(424), 1264-1272. <https://doi.org/10.1080/01621459.1993.10476407>
43. Atkinson, A. C., & Riani, M. (2000). *Robust Diagnostic Regression Analysis*. Springer. <https://doi.org/10.1007/978-1-4612-1160-0>
44. Cochran, W. G. (1941). The distribution of the largest of a set of estimated variances as a fraction of their total. *Annals of Eugenics*, 11(1), 47-52. <https://doi.org/10.1111/j.1469-1809.1941.tb02271.x>
45. ISO 5725-2:2019. *Accuracy (trueness and precision) of measurement methods and results — Part 2: Basic method for the determination of repeatability and reproducibility of a standard measurement method*. International Organization for Standardization.

### Simulated references and weakly identified steps

46. Davison, A. C., & Hinkley, D. V. (1997). *Bootstrap Methods and Their Application*. Cambridge University Press. <https://doi.org/10.1017/CBO9780511802843>
47. Benjamin, D. J., Berger, J. O., Johannesson, M., et al. (2018). Redefine statistical significance. *Nature Human Behaviour*, 2(1), 6-10. <https://doi.org/10.1038/s41562-017-0189-z>
48. Andrews, D. W. K., & Cheng, X. (2012). Estimation and inference with weak, semi-strong, and strong identification. *Econometrica*, 80(5), 2153-2211. <https://doi.org/10.3982/ECTA9456>
49. Buehler, R. J. (1959). Some validity criteria for statistical inferences. *The Annals of Mathematical Statistics*, 30(4), 845-863. <https://doi.org/10.1214/aoms/1177706070>

### Widening an interval for what the residual does not show

50. Kent, J. T. (1982). Robust properties of likelihood ratio tests. *Biometrika*, 69(1), 19-27. <https://doi.org/10.1093/biomet/69.1.19>
51. Rao, J. N. K., & Scott, A. J. (1984). On chi-squared tests for multiway contingency tables with cell proportions estimated from survey data. *The Annals of Statistics*, 12(1), 46-60. <https://doi.org/10.1214/aos/1176346391>
52. Royall, R., & Tsou, T.-S. (2003). Interpreting statistical evidence by using imperfect models: robust adjusted likelihood functions. *Journal of the Royal Statistical Society: Series B*, 65(2), 391-404. <https://doi.org/10.1111/1467-9868.00392>
53. Berger, R. L., & Boos, D. D. (1994). P values maximized over a confidence set for the nuisance parameter. *Journal of the American Statistical Association*, 89(427), 1012-1016. <https://doi.org/10.1080/01621459.1994.10476836>
54. Paule, R. C., & Mandel, J. (1982). Consensus values and weighting factors. *Journal of Research of the National Bureau of Standards*, 87(5), 377-385. <https://doi.org/10.6028/jres.087.022>

---

**Contact:** contact@suprabank.org
