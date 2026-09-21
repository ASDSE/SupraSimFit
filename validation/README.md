# Validation

Every rate SupraSimFit states about a binding constant — how often an interval holds the truth,
how often a test fires on data it should not, how often a warning is a false alarm — is produced
here. The generators, the scoring and the result store live in one package, the checks are run
from one command, and the tables below are its output. Nothing in a document, a docstring or the
paper is typed by hand from a run someone remembers.

## Running it

```bash
PYTHONPATH=$PWD uv run python -m validation list                       # what each check claims, and its rows so far
PYTHONPATH=$PWD uv run python -m validation run conditional-coverage   # compute what is missing
PYTHONPATH=$PWD uv run python -m validation run --jobs 8 --time-limit-min 120
PYTHONPATH=$PWD uv run python -m validation tables conditional-coverage
PYTHONPATH=$PWD uv run python -m validation tables --format csv > rows.csv
PYTHONPATH=$PWD uv run python -m validation prune                      # drop rows an earlier engine produced
PYTHONPATH=$PWD uv run python -m validation compare "$BEFORE"          # that code's rows against this code's

PYTHONPATH=$PWD uv run python -m validation list --cases 'DBA_HG2'     # the ids one expression selects
PYTHONPATH=$PWD uv run python -m validation run runs-null --cases 'DBA_HG2' --cases 'GDA,K=0.1'
PYTHONPATH=$PWD uv run python -m validation tables runs-null --cases 'DBA_HG2'
```

`run` with no check named runs every check that has cases of its own. It is idempotent: rows
already stored for the current code are never computed again, so a run that is killed — or one
given `--time-limit-min` — is continued by running the same command again. `--max-n` caps the
seeds any one case reaches.

`--cases` takes a regular expression searched in the case ids and may be repeated; a case is
taken when any of them matches. A fix round re-runs and prints the cells it touched and leaves
the rest of the store alone, and a table rendered through the filter says which expressions it
was narrowed by — the cases left out are cases nobody asked about, not cases that passed.

A full run is hours of processor time. A smoke run is `--max-n 2` on one check.

`compare CODE_A [CODE_B] [<check>...]` reads the rows two code hashes stored for the same
`(case, seed)` and prints, per check, how many were compared, how many differ and the first
`(case, seed, field)` that does; it exits 1 on any difference. Everything but `code`, `t_fit`
and `t_total` is compared, and a value is equal only when it is the same number, so it is the
guard behind a change that was meant to leave a path alone: run the checks that cover that path
before the change, run the same command after it into the same store — never `prune` in between,
since both hashes have to be on disk — and compare. Zero differing rows over some thousands of
fits is the pass; a check named on the command line with no rows under both hashes is a failure,
because the comparison that was asked for did not happen.

## What is in a row

One row is one `(scenario, seed)`. The scenario fixes the model, the binding regime, the design,
the noise, how well the entered inputs are said to be known and how wrongly they are entered; the
seed draws the truth inside it — the concentration scale, the titrant span, the signal
coefficients and the exact binding constants — so a scenario stands for a family of titrations
rather than one hand-picked curve. The dataset is reproducible from `(scenario.id, seed)` alone,
and a scenario's truth and noise do not change when its inputs are stated or mis-entered: what a
stated uncertainty does to a fit is read off the same measurement.

The fit goes through the calls the interface makes — `fit_measurement_set` on a
`MeasurementSet` — so what is scored is what ships. The row holds the truth, the reported
interval, the interval conditional on the entered inputs, where the fit put the inputs, what the
misfit tests and the conflict statistic say, and the wall time.

A fit the application declines is stored with the message a user would see and counted as
**refused**; anything else that escapes is stored with its type and counted as an **error**.
Neither is dropped, and `tables` prints both counts beside every rate.

## The store

Rows are appended to `validation/results/<check>.jsonl`, keyed by `(case, seed, code)`. The code
hash is taken over the executable code — docstrings stripped, formatting gone — of `core/models`,
`core/assays`, `core/pipeline`, `core/optimizer` and `core/data_processing`. Rewording a
docstring keeps a run's rows; changing what the engine does retires them, and `prune` removes
them once nobody wants the record of what the previous engine did.

The hash does **not** cover this package. When a change here alters what a row holds rather than
how it is computed, delete the check's file rather than letting old and new rows be read together.

Each row is one unbuffered append of the whole encoded line, so a process killed between two rows
leaves whole lines behind it. A line that is nonetheless unreadable — a full disk, a kill landing
mid-write — is skipped with a count on stderr rather than raising, and `prune` rewrites the file
without it. A killed run costs the rows it had not finished and nothing else.

One dead worker costs one row as well: a job that raises inside its worker is stored as an error
row, and a worker process that dies outright takes its pool with it, whereupon the jobs that
produced no row go on a new pool. A job is a pure function of `(check, case, seed)`, so
resubmitting it is free.

## The ladder

Seeds are always 0, 1, 2 … in order, so extending a case re-uses every row it already has. Every
case runs the first stage (100 seeds for most checks); a case stops there once every rate judged
of it has **passed**, and every other case goes on to 200 and then 400 seeds. A pass at 100 seeds
would be a pass at 400, so stopping on it changes no decision. A fail and an undecided both go on,
which is what puts every published failure on the full 400 draws and keeps the chance of failing a
case whose procedure is exactly nominal at the 2 % the exact limits carry, rather than
accumulating it over the three looks. Each table states the N it reached, and an undecided rate at
the end of the ladder is printed as it stands, with its limits.

## How a rate is judged

The criterion is **Bradley's liberal criterion of robustness** (J. V. Bradley, *Robustness?*,
British Journal of Mathematical and Statistical Psychology **31**, 144-152, 1978): a procedure
with nominal error rate α is acceptable when its true error rate lies in `[0.5 α, 1.5 α]`. For a
95 % confidence interval that is coverage in `[0.925, 0.975]`; for a test run at the 5 % level, a
rejection rate on the null in `[0.025, 0.075]`.

An interval that is too wide and a test that is too quiet err on the safe side, so **only the
anti-conservative side can fail**. Every verdict is read off the exact 95 % Clopper-Pearson limits
of the observed rate, `[CP low, CP high]`:

| claim | fail | pass | otherwise |
| --- | --- | --- | --- |
| coverage of a 95 % interval | `CP high < 0.95` | `CP low >= 0.925` | undecided |
| rate of a 5 % test on the null | `CP low > 0.05` | `CP high <= 0.075` | undecided |
| the verdict's false alarms, claimed `<= 0.15` | `CP low > 0.15` | `CP high <= 0.15` | undecided |
| the two profiles agree, claimed `>= 0.99` | `CP high < 0.99` | `CP low >= 0.99` | undecided |

A pass the limits also put past the far end of Bradley's range is labelled **conservative** and is
still a pass: coverage with `CP low > 0.975`, a test rate with `CP high < 0.025`. The two
upper- and lower-limit claims state a threshold rather than a level, so there is nothing to call
conservative there. Fail is read first; the two conditions of a level can both hold only when the
exact limits are narrower than the gap between the thresholds, which needs some two thousand
draws — five times what the ladder reaches.

**What the rule can decide.** Exactly from the binomial, at the 400 draws the ladder ends on
(`validation.criteria.operating_characteristic`):

| true coverage | P(pass) | P(fail) | P(undecided) |
| ---: | ---: | ---: | ---: |
| 0.900 | 0.000 | 0.964 | 0.036 |
| 0.925 | 0.018 | 0.527 | 0.455 |
| 0.950 | 0.468 | 0.019 | 0.513 |
| 0.970 | 0.980 | 0.000 | 0.020 |

The 5 % test rule is the mirror image of it, term for term: 0.997 / 0.000 at a true rate of 0.025,
0.468 / 0.019 at 0.05, 0.018 / 0.527 at 0.075 and 0.000 / 0.964 at 0.10. The false-alarm rule
passes a verdict that fires on 5 % of good data with probability 1.000 and fails one that fires on
20 % with probability 0.752. The agreement rule passes two computations that always agree with
probability 1.000 and fails a pair that disagrees on 3 % of datasets with probability 0.849.

A procedure that is exactly nominal is therefore passed about half the time and otherwise left
undecided, never failed on the strength of the draws alone; one a full Bradley step
anti-conservative is failed almost always. An undecided rate at 400 draws is a statement about
what 400 draws can settle, and the honest thing to print.

**What is judged is the coverage over every draw.** That is the frequentist property the level
promises, and an interval that runs to a Ka bound covers that side by telling the user the data do
not limit Ka there — which is what the application reports and how a reader acts on it. Beside the
judged `cov.KEY` the tables report `closed_cov.KEY` over the draws closed on both sides, the
fractions `open.KEY`, `split.KEY` and `limited.KEY`, the median `width.KEY` and `bound_active`.
None of those is judged: conditioning on closure keeps the draws whose noise happened to make the
profile steep, which is a different population from the one the level is about.

**Reported, not judged.** A check with no criterion describes what happens — the power of a test,
the price of blocking a Sobol' design, what the previous release gave on the same data. A series
whose name the tables print without a criterion is reported for the same reason: calling any of it
a pass or a failure would be an invention.

**A partial store says so.** Every table's header states how many of the check's cases have rows,
and a check that is not finished carries a warning line above its tables. A pooled per-assay rate
is judged by the same rule as a case, and is marked `partial` unless every case of that family has
rows at the same seed count, because a pool over whichever cases happened to finish is not the
family's rate.

## Adding to it

A validator who needs a scenario that does not exist adds it to `scenarios.py` and, if it carries
a claim of its own, a check to `checks.py`. A private generator in a scratch directory is fine for
hunting a cause and never for a number anyone quotes.

## The checks

Generated by `python -m validation list`; the claim and the criterion of each live in `checks.py`.

```
conditional-coverage   180 cases                                95 % interval
  The interval reported when every entered input is taken as exact holds the true binding
  constant as often as its 95 % level says, across every assay, regime, design and noise size,
  over every draw — with the fraction of draws in which the data limit Ka on both sides beside
  it.

two-ka-weak            108 cases                                95 % interval
  What the interval does for the two stepwise models in the weak regime, where the host is dark
  and the two binding constants are separated by one to three orders of magnitude: how often the
  interval holds a constant, and how often the data limit it on both sides at all.

input-aware-coverage   144 cases                                95 % interval
  The reported interval, which lets every entered input move within the uncertainty stated for
  it, holds the true binding constant as often as its level says when the inputs are entered
  exactly as wrongly as stated.

range-spec-coverage    36 cases                                 95 % interval
  The same holds when an input is stated as a range rather than a standard deviation, with the
  entered value drawn uniformly over that range.

conflict-null          reads 72 cases of input-aware-coverage   5 % test
  On the grid conflict-power runs, the check on the entered inputs calls them in conflict about
  as often as its level allows when they are entered exactly as wrongly as stated, over the fits
  whose data inform an input direction at all.

conflict-power         216 cases                                reported
  How often the same check fires when the inputs are entered two, three and five times as
  wrongly as stated, on the grid its null rate is measured on — what a user gains from it,
  reported rather than required.

lof-null               72 cases                                 5 % test
  The replicate lack-of-fit F test calls the model inadequate about as often as its level allows
  on replicated data the model does describe.

runs-null              48 cases                                 5 % test
  The runs test on the residuals fires about as often as its level allows on single titrations
  the model does describe.

misfit-power           84 cases                                 reported
  How often the misfit tests see a departure the model cannot follow: a smooth sine of 2 % of
  the signal range shared by every replicate, and a titrant series entered 15 % off.

verdict-false-alarm    reads every case of input-aware-coverage <= 0.15
  A fit of data the model describes, with the inputs entered as wrongly as stated, is blamed on
  the model or on the inputs in at most one fit in seven.

robustness             66 cases                                 95 % interval
  The reported interval still holds its level when the entries are half as wrong as stated, when
  the truth puts a signal coefficient on its bound (a dark free dye and no offset), and when the
  noise scales with the signal instead of being constant.

robustness-strained    72 cases                                 reported
  What the interval does when its premise is broken: entries twice as wrong as stated, and one
  stock error shared by two inputs that were each stated on their own. Described, not required.

reference-agreement    36 cases                                 >= 0.99
  The engine places both edges of its interval where an independent profile — its own design,
  its own search and its own root finding — places them, to a ten-thousandth of a decade of Ka.

joint-region           48 cases                                 95 % interval
  The joint confidence region of a two-constant model holds the true pair as often as its level
  says — the reading the Identifiability tab offers where the two constants trade off against
  each other and neither interval alone settles the pair.

replicate-pooling      36 cases                                 reported
  What the app gains by fitting the average of the replicates rather than pooling their points:
  the coverage and the width of both intervals on the same data, under independent noise, under
  noise that grows with the signal, and under one departure the replicates share. Reported, not
  required — under a shared departure neither holds its level, which is the point.

before-after           72 cases                                 reported
  What the same datasets gave before the engine: how often the range spanned by the pool of
  attempts the previous release kept held the truth, how wide it was, and how often it kept no
  attempt at all, beside the present interval on the same data.

sobol-coverage         4 cases                                  95 % interval
  The 95 % interval the Ka sensitivity analysis draws around a Sobol' index holds the
  analytically known index of two test functions as often as it says.

dilution-coverage      40 cases                                 95 % interval
  The interval holds the true binding constant as often as its 95 % level says when the titrant
  dilutes the fixed totals of the sample and the titrant stock is declared, across every assay,
  regime and noise size, at final dilutions of two to twenty percent.

dilution-ignored       12 cases                                 reported
  What the same diluted titrations give when the titrant stock is not declared and the fit holds
  the totals constant: how far log10 of the binding constant lands from the truth, and how often
  the interval still reaches it. Reported, not required — it is the cost the dilution option
  removes.

shared-source-coverage 36 cases                                 95 % interval
  The reported interval holds its level when one error of four percent is common to every
  concentration of the sample — one stock behind the host, the fixed partner and the titrant —
  the entries are drawn from exactly that model and the fit is told it.

budget-coverage        4 cases                                  95 % interval
  The 95 % intervals the Ka uncertainty budget draws — around the variance of the output, around
  the variance one source explains, around the spread left once that source is exact, and around
  the two indices of a group of inputs taken together — hold the analytically known values of
  two test functions as often as they say.

source-variance-exact  4 cases                                  95 % interval
  On a direct-binding titration, where one error common to every concentration moves log10 of
  the binding constant by exactly minus log10 of itself, the budget's 95 % interval for that
  source's variance holds the value the identity gives it. The identity holds where every fit of
  the analysis lies strictly inside the Ka bounds; a draw where one ran to a bound reports the
  edge of the box, where the output is constant, and is left out of the rate and counted beside
  it.

what-if-accuracy       3 cases                                  reported
  How far the what-if line lands from the truth: the first-order formula and the re-weighted
  cross-check against a second analysis run at the reduced uncertainty on the same data and the
  same design, with the effective sample size the cross-check carried. Both errors are given
  again over the draws where no fit ran to a Ka bound, since a fit that did reports the edge of
  the box rather than a spread of the inputs.

sobol-blocking         10 cases                                 reported
  What splitting one budget into independently scrambled blocks costs: the root-mean-square
  error of each index, block count by block count, at a fixed budget. Reported, not required.

runtime                reads every case of input-aware-coverage reported
  How long one fit takes, per assay family: the median, the 99th percentile and the worst seen.
```

`joint-region` goes through `fit_profile`, the call the Identifiability tab makes, and asks the
region it returns whether the true pair lies in it — the same surface, the same threshold and the
same bounding box the tab draws. That surface is 64 x 64 exact solves, which puts a row of this
check at some ten seconds; `python -m validation run joint-region --max-n 200` is the half of it
worth running when the full ladder is more than a machine can give.

`conflict-null` and `conflict-power` read one grid: the null rate is the rows of
`input-aware-coverage` whose scenarios are the multiple-1 members of `conflict_grid`, and the
power curve is the same designs at 2, 3 and 5 times the stated uncertainty. What the two
checks state rests on the definitions in `checks.py` and on the rows they produce.

`source-variance-exact` and `what-if-accuracy` both rest on fits that stayed inside the Ka box.
A fit that ran to a bound reports that bound: the output is constant there, so the variance the
shared source really carries is no longer the quadrature the first check compares against, and the
spread the second one measures is a jump of decades rather than the movement of the inputs. Each
row records whether the baseline ran there and how many of the design's fits did. The judged
coverage of `source-variance-exact` is over the rows where none did, with `~on_bound.KEY` the share
that were left out beside it; `what-if-accuracy` keeps every row and gives its two error series a
second time over the clean ones, `~formula_err_clean.KEY` and `~reweighted_err_clean.KEY`. A case
whose regime leaves most rows on a bound therefore says little: widen the Ka bounds or move the
case to a regime the default box contains.

`before-after` runs the release before the engine. It extracts that commit with `git archive`
into a directory of its own and runs it in a subprocess with that directory on the path, so the
comparison needs nothing but this repository.

## Tables

Generated by `python -m validation tables`. Empty until the checks have been run.
