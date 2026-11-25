# Calibration scripts

Two statements the app makes about Ka are checked here rather than asserted:

- the **Identifiability** tab's 95 % confidence interval holds the true Ka about 95 % of the time,
- the **Ka Sensitivity** tab's 95 % whiskers hold the true Sobol' index about 95 % of the time.

Each script imports the functions the app itself uses, generates data whose answer is known,
and prints a table. Both take `--designs` (how many independent datasets or designs to run) and
`--seed` (the first seed; the runs use consecutive seeds); `sobol_interval_coverage.py` also takes
`--n-base`, the base sample size or sizes of its coverage tables. Every table below is printed by
the one command stated above it, on the default seed; each takes a few minutes.

## `profile_interval_coverage.py`

Generates synthetic IDA titrations from a known `Ka_guest` of 2×10⁶ M⁻¹ (12 points, the ground
truth the test suite uses), fits each with `core.pipeline.profile.fit_profile`, and counts how
often the interval contains that value. The scatter is varied to break, one at a time, the
assumptions behind the F test: constant-size independent noise, then noise proportional to the
signal, then four replicates that share a smooth systematic misfit of 2 % of the largest signal.
For the replicate scenarios it also builds the interval the other way — pooling every replicate's
points as independent observations instead of averaging the replicates — which is the comparison
that decides how the app handles replicates.

```bash
uv run scripts/profile_interval_coverage.py --designs 200
```

Nominal 95 %, 200 datasets per scenario:

| Scenario | Coverage | 95 % exact interval | Median width (decades) | Pooled coverage | Pooled width |
|---|---|---|---|---|---|
| homoscedastic | 0.960 | [0.923, 0.983] | 0.343 | — | — |
| proportional | 0.910 | [0.861, 0.946] | 0.151 | — | — |
| replicates | 0.965 | [0.929, 0.986] | 0.169 | 0.945 | 0.156 |
| shared-misfit | 0.765 | [0.700, 0.822] | 0.191 | 0.665 | 0.158 |

Reading: the interval keeps its promise where its assumption holds, loses a few points of coverage
under proportional noise, and is optimistic when the replicates depart from the model together —
the case in which pooling their points would be worse still, producing a narrower interval that is
wrong more often. That last row is why the app profiles the replicates' average.

## `sobol_interval_coverage.py`

Runs the app's `sobol_design`, `sobol_indices_from_outputs` and `sobol_indices_with_ci` on two
functions whose Sobol' indices are known in closed form — the Ishigami function (3 inputs) and a
g-function with coefficients `[0, 0.5, 3, 9, 99, 99]` (6 inputs, indices from 0.59 down to 1×10⁻⁴).
One run prints both tables below, for both functions and both sample sizes:

```bash
uv run scripts/sobol_interval_coverage.py --designs 1000 --n-base 1024 4096
```

**Coverage of the delete-one-block jackknife interval**, over eight blocks and 1000 designs. Each
row is the range across that function's first- and total-order indices:

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
