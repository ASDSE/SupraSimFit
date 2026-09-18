# Calibration scripts

Two statements the app makes about Ka are checked here rather than asserted:

- the 95 % confidence interval of every binding constant, and the joint region of a two-constant
  model, hold the true values about 95 % of the time,
- the **Ka Sensitivity** tab's 95 % whiskers hold the true Sobol' index about 95 % of the time.

Each script imports the functions the app itself uses, generates data whose answer is known,
and prints a table. Both take `--designs` (how many independent datasets or designs to run) and
`--seed` (the first seed; the runs use consecutive seeds). `profile_interval_coverage.py` also
takes `--assay`, `--regime` (Ka·c of the truth), `--points` and `--jobs` (worker processes);
`sobol_interval_coverage.py` takes `--n-base`, the base sample size or sizes of its coverage
tables. Every table below is printed by the command stated above it, on the default seed.

## `profile_interval_coverage.py`

Generates synthetic titrations of one assay from the ground truth the test suite uses
(`tests/conftest.py`), fits each with the app's engine (`core.pipeline.varpro.Projection`, the
calls a fit makes, with the app's default bounds) and counts how often each binding constant's
interval, and for the stepwise models the joint region, contains the true value. The scatter is
varied to break, one at a time, the assumptions behind the F test: constant-size independent
noise, then noise proportional to the signal, then four replicates that share a smooth systematic
misfit of 2 % of the largest signal. Two more columns say what the intervals looked like: how
often one was **open** on a side, reaching a Ka bound because the data do not limit Ka there, and
how often the best fit had a signal parameter the data determine sitting on a **bound** (the
offset is zero in every system, on its lower bound, a case the F test's derivation does not
foresee). For the replicate scenarios it also builds the interval the other way, pooling every
replicate's points as independent observations instead of averaging the replicates, by a profile
written in the script; on one replicate that profile is the app's own interval, and the two agree
to within 2×10⁻⁸ decades at every edge for every assay.

`--regime` moves the true binding constants so that the first one times the fixed concentration
of the titration (the host for GDA, IDA, HG2 and H2G, the fixed partner for DBA) equals the value
given, from weak binding, where the isotherm bends little over the titration, to stoichiometric
binding, where it breaks at equivalence; the titrant range, the noise and the other conditions
stay those of the assay's system.

```bash
uv run scripts/profile_interval_coverage.py --assay IDA --designs 200        # and GDA, DBA_HtoD, DBA_DtoH
uv run scripts/profile_interval_coverage.py --assay HG2 --designs 200 --points 30   # and H2G
```

Nominal 95 %, 200 datasets per scenario from seed 1000, 2 % noise. The one-constant assays use 12
titration points; the stepwise models 30, because their six parameters leave 12 points with six
degrees of freedom and intervals open in most datasets (at 12 points and 2 % noise, Ka_HG is open
in 60–87 % of HG2 datasets and 87–98 % of H2G datasets, with coverage 0.960–1.000). Width is the
median width in decades of Ka.

**IDA** (Ka_guest = 2×10⁶ M⁻¹, Ka_guest·[Host]₀ = 20):

| Scenario | Coverage | 95 % exact | Width | Open | Bound | Pooled coverage | Pooled width |
|---|---|---|---|---|---|---|---|
| homoscedastic | 0.960 | [0.923, 0.983] | 0.343 | 0.00 | 0.00 | — | — |
| proportional | 0.910 | [0.861, 0.946] | 0.151 | 0.00 | 0.00 | — | — |
| replicates | 0.965 | [0.929, 0.986] | 0.169 | 0.00 | 0.00 | 0.945 [0.904, 0.972] | 0.156 |
| shared-misfit | 0.765 | [0.700, 0.822] | 0.191 | 0.00 | 0.00 | 0.665 [0.595, 0.730] | 0.158 |

**DBA host → dye** (Ka_dye = 5×10⁵ M⁻¹, Ka_dye·[Dye]₀ = 5):

| Scenario | Coverage | 95 % exact | Width | Open | Bound | Pooled coverage | Pooled width |
|---|---|---|---|---|---|---|---|
| homoscedastic | 0.955 | [0.916, 0.979] | 0.344 | 0.00 | 0.00 | — | — |
| proportional | 0.980 | [0.950, 0.995] | 0.305 | 0.00 | 0.00 | — | — |
| replicates | 0.965 | [0.929, 0.986] | 0.169 | 0.00 | 0.00 | 0.965 [0.929, 0.986] | 0.154 |
| shared-misfit | 0.885 | [0.832, 0.926] | 0.194 | 0.00 | 0.00 | 0.815 [0.754, 0.866] | 0.159 |

**DBA dye → host** (Ka_dye = 5×10⁵ M⁻¹, Ka_dye·[Host]₀ = 5):

| Scenario | Coverage | 95 % exact | Width | Open | Bound | Pooled coverage | Pooled width |
|---|---|---|---|---|---|---|---|
| homoscedastic | 0.945 | [0.904, 0.972] | 1.895 | 0.27 | 0.47 | — | — |
| proportional | 0.925 | [0.879, 0.957] | 1.178 | 0.02 | 0.47 | — | — |
| replicates | 0.940 | [0.898, 0.969] | 0.796 | 0.00 | 0.54 | 0.955 [0.916, 0.979] | 0.697 |
| shared-misfit | 0.850 | [0.793, 0.896] | 0.691 | 0.00 | 0.56 | 0.775 [0.711, 0.831] | 0.609 |

**GDA** (Ka_guest = 1.5×10⁶ M⁻¹, Ka_guest·[Host]₀ = 15):

| Scenario | Coverage | 95 % exact | Width | Open | Bound | Pooled coverage | Pooled width |
|---|---|---|---|---|---|---|---|
| homoscedastic | 1.000 | [0.982, 1.000] | 15.7 | 1.00 | 0.66 | — | — |
| proportional | 0.995 | [0.972, 1.000] | 15.2 | 0.97 | 0.40 | — | — |
| replicates | 0.995 | [0.972, 1.000] | 15.2 | 0.99 | 0.66 | 1.000 [0.982, 1.000] | 15.1 |
| shared-misfit | 0.995 | [0.972, 1.000] | 14.9 | 0.97 | 0.82 | 0.990 [0.964, 0.999] | 14.9 |

**HG2, stepwise 1:2** (Ka_HG = 10⁶ M⁻¹, Ka_HG2 = 2×10⁵ M⁻¹, Ka_HG·[Host]₀ = 300, 30 points):

| Scenario | Quantity | Coverage | 95 % exact | Width | Open | Bound | Pooled coverage | Pooled width |
|---|---|---|---|---|---|---|---|---|
| homoscedastic | Ka_HG | 0.955 | [0.916, 0.979] | 1.735 | 0.33 | 0.50 | — | — |
| | Ka_HG2 | 0.965 | [0.929, 0.986] | 1.820 | 0.00 | | — | — |
| | joint region | 0.955 | [0.916, 0.979] | | | | | |
| proportional | Ka_HG | 0.955 | [0.916, 0.979] | 1.243 | 0.14 | 0.56 | — | — |
| | Ka_HG2 | 0.965 | [0.929, 0.986] | 1.304 | 0.00 | | — | — |
| | joint region | 0.965 | [0.929, 0.986] | | | | | |
| replicates | Ka_HG | 0.915 | [0.867, 0.950] | 0.683 | 0.00 | 0.52 | 0.925 [0.879, 0.957] | 0.658 |
| | Ka_HG2 | 0.930 | [0.885, 0.961] | 0.711 | 0.00 | | 0.940 [0.898, 0.969] | 0.689 |
| | joint region | 0.925 | [0.879, 0.957] | | | | | |
| shared-misfit | Ka_HG | 0.930 | [0.885, 0.961] | 0.737 | 0.00 | 0.41 | 0.920 [0.873, 0.954] | 0.716 |
| | Ka_HG2 | 0.935 | [0.891, 0.965] | 0.766 | 0.00 | | 0.930 [0.885, 0.961] | 0.733 |
| | joint region | 0.920 | [0.873, 0.954] | | | | | |

**H2G, stepwise 2:1** (Ka_HG = 10⁶ M⁻¹, Ka_H2G = 2×10⁵ M⁻¹, Ka_HG·[Host]₀ = 300, 30 points):

| Scenario | Quantity | Coverage | 95 % exact | Width | Open | Bound | Pooled coverage | Pooled width |
|---|---|---|---|---|---|---|---|---|
| homoscedastic | Ka_HG | 0.970 | [0.936, 0.989] | 7.132 | 0.86 | 0.57 | — | — |
| | Ka_H2G | 0.960 | [0.923, 0.983] | 7.494 | 0.41 | | — | — |
| | joint region | 0.950 | [0.910, 0.976] | | | | | |
| proportional | Ka_HG | 1.000 | [0.982, 1.000] | 7.019 | 0.90 | 0.55 | — | — |
| | Ka_H2G | 1.000 | [0.982, 1.000] | 7.215 | 0.07 | | — | — |
| | joint region | 1.000 | [0.982, 1.000] | | | | | |
| replicates | Ka_HG | 0.960 | [0.923, 0.983] | 2.944 | 0.48 | 0.47 | 0.945 [0.904, 0.972] | 2.744 |
| | Ka_H2G | 0.950 | [0.910, 0.976] | 2.606 | 0.01 | | 0.930 [0.885, 0.961] | 2.447 |
| | joint region | 0.925 | [0.879, 0.957] | | | | | |
| shared-misfit | Ka_HG | 0.955 | [0.916, 0.979] | 2.646 | 0.46 | 0.49 | 0.935 [0.891, 0.965] | 2.645 |
| | Ka_H2G | 0.940 | [0.898, 0.969] | 2.445 | 0.01 | | 0.930 [0.885, 0.961] | 2.369 |
| | joint region | 0.920 | [0.873, 0.954] | | | | | |

Reading: the interval keeps its promise where its assumption holds, in every model, whether or
not the fit sits on a signal-parameter bound and whether the interval is closed or open. Its
lowest cell, 0.915 for Ka_HG in the HG2 replicates row, is sampling: 600 further datasets of that
scenario (`--designs 600 --seed 5000`) give 0.960 [0.941, 0.974] for Ka_HG, 0.953 for Ka_HG2 and
0.957 for the joint region. It loses a few points of coverage under proportional noise in IDA and DBA
dye → host, and it is optimistic when the replicates depart from the model together, in IDA and
both DBA directions the case in which pooling their points would be worse still, producing a
narrower interval that is wrong more often. That row is why the app profiles the replicates'
average. In the stepwise models a 2 % misfit costs two to three points of coverage and the two
ways of using the replicates come out alike; with 24 degrees of freedom the averaged interval is
barely wider than the pooled one, while with the six of a 12-point titration it can be several
times wider (HG2: 6.3 against 1.5 decades), because it has fewer residuals to measure the
scatter with.

The GDA rows are honest in a different way: with the signal parameters free, dye titrated into
host and guest at these conditions (Ka_dye·[Host]₀ = 5) barely distinguishes a competing guest
from none — the noise-free residual stays below 10⁻⁴ of the total sum of squares all the way to
Ka_guest → 0, at every regime from 0.15 to 15 000 — so at 2 % noise the interval is open below in
nearly every dataset and the fit says so instead of reporting a number. Ka_HG of the stepwise
models is open above in a third of the HG2 datasets and most of the H2G datasets with one
replicate: at [Host]₀ = 300 µM, Ka_HG·[Host]₀ = 300, the first step is past the point where the
data say more than "at least this strong"; the second step's interval closes far more often, and
the joint region carries the pair.

## `sobol_interval_coverage.py`

Runs the app's `sobol_design`, `sobol_indices_from_outputs` and `sobol_indices_with_ci` on two
functions whose Sobol' indices are known in closed form — the Ishigami function (3 inputs) and a
g-function with coefficients `[0, 0.5, 3, 9, 99, 99]` (6 inputs, indices from 0.59 down to 1×10⁻⁴).
One run prints both tables below, for both functions and both sample sizes:

```bash
uv run scripts/sobol_interval_coverage.py --designs 1000 --n-base 1024 4096
```

**Coverage of the delete-one-block jackknife interval**, over eight blocks and 1000 designs from
seed 0. Each row is the range across that function's first- and total-order indices:

| Function | Coverage across its indices | Mean half-width ÷ (t × empirical SD) | Bias ÷ empirical SD |
|---|---|---|---|
| Ishigami, N = 1024 | 0.944 – 0.971 | 0.85 – 1.01 | ≤ 0.03 |
| g-function, N = 1024 | 0.942 – 0.969 | 0.92 – 0.98 | ≤ 0.07 |
| Ishigami, N = 4096 | 0.957 – 0.988 | 0.92 – 0.98 | ≤ 0.03 |
| g-function, N = 4096 | 0.940 – 0.982 | 0.83 – 1.04 | ≤ 0.06 |

Reading: the interval is close to nominal across indices spanning four orders of magnitude, its
half-width is within about 15 % of what the estimator's true scatter would give, and the
estimators' bias is small against their own scatter — so the interval is honest about sampling
error rather than about bias.

**The price of blocking.** The same budget split into eight independently scrambled blocks has a
larger error than one undivided scramble, because a scrambled Sobol' set integrates better the
longer it is. Ratios of the root-mean-square error against one scramble at N = 1024, index by
index over the same 1000 designs:

| Split | Ishigami | g-function |
|---|---|---|
| 1 × 1024 (N = 1024) | 1.0 | 1.0 |
| 8 × 128 (N = 1024) | 1.6 – 3.7 | 0.8 – 4.9 |
| 32 × 32 (N = 1024) | 3.1 – 6.2 | 1.3 – 5.9 |
| 1 × 128 (N = 128) | 5.0 – 10.4 | 2.4 – 13.5 |
| 1 × 4096 (N = 4096) | 0.4 – 0.5 | 0.1 – 0.7 |
| 8 × 512 (N = 4096) | 0.5 – 2.4 | 0.4 – 2.7 |

Reading: eight blocks cost up to about a factor of five in accuracy, index by index — a few indices
are barely affected — and buy an error bar; more blocks cost more and buy only a slightly narrower
t quantile, and the `1 × 128` row shows what a design as small as one block would deliver on its
own. That trade is why the analysis uses eight blocks and offers no sample size below 1024. The
last two rows say what the larger budget buys: undivided it beats a scramble of N = 1024 on every
index, and split into eight blocks most indices still come out at or below it while a few, mostly
total-order ones, stay up to about three times worse.
