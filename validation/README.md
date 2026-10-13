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
`(case, seed)` and prints, per check, how many were compared, how many differ, every field they
differ on with the number of keys it moved on, and the first `(case, seed, field)` that does; it
exits 1 on any difference. Everything but `code`, `t_fit`, `t_total` and the fields named with
`--ignore FIELD` (repeatable) is compared, and a value
is equal only when it is the same number, so it is the guard behind a change that was meant to
leave a path alone: run the checks that cover that path
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
misfit tests and the conflict statistic say, what the replicates showed about the noise
(`noise_share`, `noise_basis` — the share of the variance that grows with the signal, and what
the law was read from — `share_set`, the range of shares the replicates allow, `weight_ratio`,
the largest weight the law gives at the measured means over its smallest, `fit_weight_ratio`, the
same of the weights the fit ran with, and `refit`, whether those were read off the fitted curve of
a first fit), and the wall time. Each interval carries its edges, whether it is open and whether
its lower side is (`open_low`), `inflation`, the factor its cut-off was widened by — exactly 1
where nothing widened it — and `one_step_p`: for the second constant of a two-step model, the
p-value of the one-step model that sets it to zero, which is what decides whether that constant is
limited below; `None` for every other constant. `misfit_reference` says what the misfit test's p-value was read
against — the F distribution, or a parametric bootstrap where the law was read off the replicates;
for the runs test of a single titration, its simulated runs.

A scenario says what the noise does as well as how big it is: `proportional` makes it grow with
the signal, `noise_floor` puts a constant part under it in quadrature, and `replicate_scale`
gives each replicate one scale factor of its own — a lamp or gain difference between runs, which
is a difference between whole replicates and not noise about the curve. A replicated scenario can also
make some replicates depart from the rest: `shifted_replicates` measured at `replicate_shift` times
every binding constant the fit moves, and `noisy_replicates` at three times the noise. Each of these
enters a scenario's key only where it is stated.

A scenario can put a random error on every titrant addition as well: `additions` is its standard
deviation in percent, `sequential` says whether the additions went into one cuvette one after
another or each sample was prepared on its own, and `repeated_reads` whether the replicates are
reads of one titration that share its errors rather than titrations of their own. Each replicate is
then measured on its own true titrant series — the planned one moved by
`core.pipeline.inputs.perturb_titrant`, the dilution by a declared stock following the volume
actually added — while the fit is handed the planned series. What the fit is told is separate:
`stated_additions` and `stated_repeated_reads` enter the case's id and not the key of its
measurement, so an error stated too large, too small or for the wrong kind of replicate is a
statement about the same data a correctly stated twin was fitted to.

A fit the application declines is stored with the message a user would see and counted as
**refused**; anything else that escapes is stored with its type and counted as an **error**.
Neither is dropped, and `tables` prints both counts beside every rate.

## The store

Rows are appended to `validation/results/<check>.jsonl`, keyed by `(case, seed, code)`; the
directory is ignored by git. The code hash is taken over the executable code — docstrings stripped,
formatting gone — of the whole `core/` package and of the modules here that generate, fit and score
a dataset (`generate`, `scenarios`, `score`, `reference`, `legacy`, `sobol`, `budget`), together with
the numpy and scipy versions: numpy promises a random stream only within one build, and a scipy
release can move a solver. Rewording a docstring keeps a run's rows; changing what the engine does,
how a dataset is drawn or how a fit is scored, or the libraries under them, retires them, and
`prune` removes them once nobody wants the record of what the previous code did. The modules that
only read rows — the metrics and the registry in `checks.py`, the criteria, the tables, the runner
and the command line — are outside the hash, so rewording a claim or re-rendering a table costs no
stored row. A test holds the two sides apart: every row function lives in a hashed module, and a
hashed module imports nothing outside the hash.

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
of it has **passed**, and every other case goes on to 200 and then 400 seeds. A fail and an
undecided both go on, which puts every published failure on the full 400 draws and keeps the
chance of failing a case whose procedure is exactly nominal at the 1.9 % the exact limits carry at
400 draws.

Stopping on a pass is three looks at a pass, though, and that **raises the chance of passing a case
that is anti-conservative** (`validation.criteria.ladder_operating_characteristic`, exactly from the
binomial):

| true coverage | P(pass), ladder 100 → 200 → 400 | P(pass), one look at 400 | P(fail), either |
| ---: | ---: | ---: | ---: |
| 0.925 | 0.040 | 0.018 | 0.53 |
| 0.930 | 0.073 | 0.042 | 0.37 |
| 0.950 | 0.515 | 0.468 | 0.019 |

The 5 % test rule is the mirror image of it. A case-level pass therefore says less than a pass on one
look would, and the rates a document quotes rest on the **pooled family rows**, which read the same
seeds of every case of a family (see *A table reads the same seeds of every case* below), not on the
count of cases that passed.

**Chance fails.** A full run judges several hundred case rates, and at 400 draws an exactly nominal
procedure fails about 1.9 % of them by chance alone — some fifteen of eight hundred. Every table says
how many of its own case rates chance would fail (the sum of each rate's chance at the draws it
has), so a fail or two among many cases is read against that number and is not evidence on its own;
a check whose failing cases far outnumber it, or whose pooled row fails, is.

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
| a clean replicate left out, claimed `<= 0.05` | `CP low > 0.05` | `CP high <= 0.05` | undecided |
| the two profiles agree, claimed `>= 0.99` | `CP high < 0.99` | `CP low >= 0.99` | undecided |
| a second constant closed below with no second step, claimed `<= 0.0075` | `CP low > 0.0075` | `CP high <= 0.0075` | undecided |

A pass the limits also put past the far end of Bradley's range is labelled **conservative** and is
still a pass: coverage with `CP low > 0.975`, a test rate with `CP high < 0.025`. The two
upper- and lower-limit claims state a threshold rather than a level, so there is nothing to call
conservative there. The last claim is Bradley's liberal limit of the one-step test's 0.5 % level,
1.5 times it, stated as the limit itself; no closure in 400 draws still leaves an exact upper limit
of 0.0092, so a case of it can fail at 400 draws but not pass, and its pass rests on the pooled row
of each model, 3200 draws over eight cases. Fail is read first; the two conditions of a level can both hold only when the
exact limits are narrower than the gap between the thresholds, which needs some two thousand
draws — five times what the ladder reaches.

**What the rule can decide.** Exactly from the binomial, on one look at 400 draws
(`validation.criteria.operating_characteristic`):

| true coverage | P(pass) | P(fail) | P(undecided) |
| ---: | ---: | ---: | ---: |
| 0.900 | 0.000 | 0.964 | 0.036 |
| 0.925 | 0.018 | 0.527 | 0.455 |
| 0.950 | 0.468 | 0.019 | 0.513 |
| 0.970 | 0.980 | 0.000 | 0.020 |

The 5 % test rule is the mirror image of it, term for term: 0.997 / 0.000 at a true rate of 0.025,
0.468 / 0.019 at 0.05, 0.018 / 0.527 at 0.075 and 0.000 / 0.964 at 0.10. The agreement rule passes
two computations that always agree with probability 1.000 and fails a pair that disagrees on 3 % of
datasets with probability 0.849.

A procedure that is exactly nominal is therefore passed about half the time, failed about one time
in fifty and otherwise left undecided; one a full Bradley step anti-conservative is failed almost
always. A fail means the draws put the rate demonstrably on the wrong side of the nominal one, which
is stricter than Bradley's range: a procedure at 0.94 lies inside the range and still fails one
time in eight. An undecided rate at 400 draws is a statement about what 400 draws can settle, and
the honest thing to print.

**What is judged is the coverage over every draw**, and where the claim is about closed intervals,
the coverage over those as well. The coverage over every draw is the frequentist property the level
promises, and an interval that runs to a Ka bound covers that side by telling the user the data do
not limit Ka there — which is what the application reports and how a reader acts on it. A closed
interval, though, is a subset of draws a user can recognise from the interval itself (R. J. Buehler,
*Some validity criteria for statistical inferences*, Annals of Mathematical Statistics **30**,
845-863, 1959),
and a user reads it as a finite guarantee; where the data barely identify the constants — two
stepwise constants a decade or more apart on a dark host — its coverage can fall far below the level
while the rate over every draw holds, because the open draws cover by construction. So
`conditional-coverage` and `two-ka-weak` judge `closed_cov.KEY` beside `cov.KEY`, and a case passes
only when both do, and report `false_closed.KEY` beside them: the share of every draw in which the
interval is closed on both sides and misses the truth, which is how often a user is handed a finite
interval that is wrong — the number the closed coverage leaves out, since it is divided by how many
draws were closed. For the second constant of a two-step model they also report
`false_closed_low.KEY`, the share of every draw whose lower edge is closed and lies above the truth —
a false claim of a second step as strong as that edge, which an interval open above (running to the
upper bound) makes too and which neither `closed_cov.KEY` nor `false_closed.KEY` counts. Everywhere
else `closed_cov.KEY` is reported, with the fractions `open.KEY`, `split.KEY` and `limited.KEY`, the
median `width.KEY` and `bound_active`.

**The input-aware level is an average over the entry errors.** `input-aware-coverage` draws each
entered input from the distribution its stated uncertainty describes — the reading of a Type B
uncertainty — and its judged rate is the coverage averaged over those draws. It is not the same at
every entry: beside it the table reports `cov_zmax_<bin>.KEY`, the coverage in bins of the largest
standard score among a draw's entry errors (below 1, 1 to 2, 2 to 2.5, 2.5 and above), which says
how far the rate falls for a draw whose entries lie far out in the stated distribution. The level is
a statement about inputs whose errors are what was stated, on average, and not about one entry that
happens to be several standard deviations off.

**Reported, not judged.** A check with no criterion describes what happens — the power of a test,
the price of blocking a Sobol' design, what the previous release gave on the same data. A series
whose name the tables print without a criterion is reported for the same reason: calling any of it
a pass or a failure would be an invention.

**A table reads the same seeds of every case.** A pooled per-assay rate is read over the seeds
`0 … N-1` that every case of the family holds, `N` being the fewest any of them reached — the
`cases x seeds` column says which — so a case the ladder carried to 400 seeds weighs no more than
one it stopped at 100, and the pool is the family's rate over a balanced design. It is judged by the
same rule as a case. A family one of whose cases has no rows at all is marked `partial` and not
judged, because a pool over the cases that happened to run is their rate and not the family's.

**A partial store says so.** Every table's header states how many of the check's cases have rows,
and a check that is not finished carries a warning line above its tables.

## Adding to it

A validator who needs a scenario that does not exist adds it to `scenarios.py` and, if it carries
a claim of its own, a check to `checks.py`. A private generator in a scratch directory is fine for
hunting a cause and never for a number anyone quotes.

## The checks

Generated by `python -m validation list`; the claim and the criterion of each live in `checks.py`.

```
conditional-coverage   180 cases                                95 % interval
  The interval reported when every entered input is taken as exact holds the true binding constant
  as often as its 95 % level says, across every assay, regime, design and noise size, over every
  draw and over the draws in which the data limit Ka on both sides.

two-ka-weak            108 cases                                95 % interval
  The interval of the two stepwise models holds each true binding constant as often as its 95 %
  level says in the weak regime, where the host is dark and the two constants are separated by one
  to three orders of magnitude — over every draw, and over the draws in which the data limit the
  constant on both sides.

input-aware-coverage   144 cases                                95 % interval
  The reported interval, which lets every entered input move within the uncertainty stated for it,
  holds the true binding constant as often as its level says when the inputs are entered exactly
  as wrongly as stated — on average over those entry errors, with the coverage by the largest
  standard score among them reported beside it.

range-spec-coverage    36 cases                                 95 % interval
  The same holds when an input is stated as a range rather than a standard deviation, with the
  entered value drawn uniformly over that range.

conflict-null          reads 72 cases of input-aware-coverage   5 % test
  On the grid conflict-power runs, the check on the entered inputs calls them in conflict about as
  often as its level allows when they are entered exactly as wrongly as stated, over the fits
  whose data inform an input direction at all.

conflict-power         216 cases                                reported
  How often the same check fires when the inputs are entered two, three and five times as wrongly
  as stated, on the grid its null rate is measured on — what a user gains from it, reported rather
  than required.

lof-null               72 cases                                 5 % test
  The replicate lack-of-fit F test calls the model inadequate about as often as its level allows
  on replicated data the model does describe.

runs-null              48 cases                                 5 % test
  The runs test on the residuals fires about as often as its level allows on single titrations the
  model does describe.

misfit-power           84 cases                                 reported
  How often the misfit tests see a departure the model cannot follow: a smooth sine of 2 % of the
  signal range shared by every replicate, and a titrant series entered 15 % off.

verdict-false-alarm    reads every case of input-aware-coverage 5 % test
  A fit of data the model describes, with the inputs entered as wrongly as stated, is blamed on
  the model, on the inputs or on both about as often as the 5 % family-wise level of the verdict
  allows.

robustness             66 cases                                 95 % interval
  The reported interval still holds its level when the entries are half as wrong as stated, when
  the truth puts a signal coefficient on its bound (a dark free dye and no offset), and when the
  noise scales with the signal instead of being constant.

robustness-strained    72 cases                                 reported
  What the interval does when its premise is broken: entries twice as wrong as stated, and one
  stock error shared by two inputs that were each stated on their own. Described, not required.

reference-agreement    42 cases                                 >= 0.99
  The engine places both edges of its interval where an independent profile — its own design, its
  own search and its own root finding — places them, to a ten-thousandth of a decade of Ka.

one-step-null          16 cases                                 <= 0.0075
  On titrations of the two stepwise models that carry no second step — the second constant a
  millionth of the first, the first step at K1·h0 of 1 and 3, 12 and 30 points, one titration of
  constant noise and three replicates of noise that grows with the signal — the reported interval of
  the second constant is closed below no more often than the 0.5 % level of the one-step test
  allows.

joint-region           48 cases                                 95 % interval
  The joint confidence region of a two-constant model holds the true pair as often as its level
  says — the reading the Identifiability tab offers where the two constants trade off against each
  other and neither interval alone settles the pair.

replicate-pooling      36 cases                                 reported
  What the app gains by fitting the average of the replicates rather than pooling their points,
  and what weighting the points by the law the replicates show buys: the coverage and the width of
  the averaged interval, of the pooled one — both carrying that same law — and of the same average
  fitted with every point counted equally, on the same data, under independent noise, under noise
  that grows with the signal, and under one departure the replicates share. Reported, not required
  — under a shared departure none of the three holds its level, which is the point.

before-after           72 cases                                 reported
  What the same datasets gave before the engine: how often the range spanned by the pool of
  attempts the previous release kept held the truth, how wide it was, and how often it kept no
  attempt at all, beside the present interval on the same data.

sobol-coverage         4 cases                                  95 % interval
  The 95 % interval the Ka sensitivity analysis draws around a Sobol' index holds the analytically
  known index of two test functions as often as it says.

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
  concentration of the sample — one stock behind the host, the fixed partner and the titrant — the
  entries are drawn from exactly that model and the fit is told it.

noise-law-coverage     188 cases                                95 % interval
  The interval reported when every entered input is taken as exact holds the true binding constant
  as often as its 95 % level says on replicated titrations, whatever the noise does along them:
  constant, growing with the signal, and the two together, at two, three and eight replicates and 8
  and 20 points and at four replicates and 12 points for every one-Ka assay in the medium and strong
  regimes; with whole replicates differing by a scale factor of three percent; and for the two-step
  model under the same noise at 12 points.

noise-law-lof-null     reads 188 cases of noise-law-coverage    5 % test
  On the same replicated titrations, every one of which the model does describe, the lack-of-fit
  test calls the model inadequate about as often as its level allows — with the fit weighted by the
  law the replicates show, the pure error taken as their scatter about their own image of the mean
  curve, and the F ratio read against a parametric bootstrap drawn at that law.

noise-law-aware        16 cases                                 95 % interval
  The reported interval, which lets every entered input move within the uncertainty stated for it,
  holds its level on replicated titrations whose noise grows with the signal, with and without a
  constant floor under it, when the inputs are entered exactly as wrongly as stated.

noise-law-conflict-null reads 16 cases of noise-law-aware        5 % test
  On the same fits, the check on the entered inputs calls them in conflict about as often as its
  level allows when they are entered exactly as wrongly as stated and the noise grows with the
  signal.

conflict-single-proportional reads 18 cases of robustness             reported
  How often the same check fires on single titrations whose noise grows with the signal. One curve
  cannot show how the noise varies along it, so the fit takes the noise as constant and the
  statistic is read against a reference that assumes it. Reported, not required: it is the rate
  that stays where no law can be estimated, and the summary and the plot guide say the noise was
  taken as constant.

addition-coverage      104 cases                                95 % interval
  The reported interval holds the true binding constant as often as its 95 % level says when every
  titrant addition carries a random error and the fit is told its size and how the additions were
  made, the inputs otherwise exact. It spans every one-Ka assay with the additions made one after
  another into one cuvette or as separate samples, at 1 % and 3 %: one titration of 12 points with
  constant noise of 0.2 % of the signal range and three separate titrations of 12 points with 0.5 %,
  each in the medium and strong regimes; one titration of 8 and of 30 points with 0.5 % and
  additions of 1 %; three separate titrations whose noise is 1 % of the signal itself, additions of
  3 %; one titration with sequential additions of 3 % diluting the sample by two to twenty percent,
  the titrant stock declared; and three replicates that are repeated reads of one titration sharing
  its additions of 3 %, stated so, with 0.5 % — these in the medium regime. Beside them both
  two-step models, one titration with sequential additions of 3 % in the medium and strong regimes.

addition-misfit-null   reads 104 cases of addition-coverage     5 % test
  On the same titrations, every one of which the model describes and whose addition error is stated
  as it was drawn, the misfit test — the runs test of one titration, the lack-of-fit test of
  replicates — calls the model inadequate about as often as its level allows.

addition-misstated     32 cases                                 reported
  What the reported interval and the misfit test do when the addition error is stated otherwise than
  it was drawn: 3 % stated where the additions carry none, on one titration and on three separate
  titrations — the coverage and what the widening costs; 1 % stated where they carry 3 %, on one
  titration; and three repeated reads of one titration sharing additions of 3 %, stated as three
  separate titrations. Every one-Ka assay, sequential and separate additions, the medium regime, 12
  points. Described, not judged.

addition-aware-coverage 32 cases                                95 % interval
  The reported interval holds the true binding constant as often as its 95 % level says when the
  inputs are entered as wrongly as stated and every titrant addition carries a random error the fit
  is told, so that the inputs and the additions widen it together: every one-Ka assay, sequential and
  separate additions of 3 % on one titration of 12 points with 0.2 % noise in the medium and strong
  regimes and on three separate titrations with 0.5 % in the medium regime, and additions of 1 % on
  one titration in the medium regime.

addition-verdict-null  reads 32 cases of addition-aware-coverage 5 % test
  On the same titrations the check on the entered inputs calls them in conflict, and the verdict
  blames the model, the inputs or both, about as often as the level allows: the additions move the
  curve much as an input does, and the conflict reference carries the share of them a fit free to
  move the inputs puts there.

addition-replicate-exclusion-null 36 cases                      <= 0.05
  Fitted replicate by replicate, replicates measured alike whose every addition carries a random
  error the fit is told lose a replicate that agrees with the rest in at most one fit in twenty:
  three and five separate titrations of every one-Ka assay with sequential and with separate
  additions of 3 %, in the medium and strong regimes, and three repeated reads of one titration
  sharing its additions.

addition-joint-region  12 cases                                 95 % region
  The joint region of a two-constant model holds the true pair as often as its level says when
  every addition carries a random error the fit is told: both stepwise models, one titration of 12
  points with sequential additions of 3 % and 0.2 % noise, the first step at K1·h0 of 1, 10 and 1000
  and the second constant a tenth and a hundredth of the first.

budget-coverage        4 cases                                  95 % interval
  The 95 % intervals the Ka uncertainty budget draws — around the variance of the output, around
  the variance one source explains, around the spread left once that source is exact, and around
  the two indices of a group of inputs taken together — hold the analytically known values of two
  test functions as often as they say.

source-variance-exact  4 cases                                  95 % interval
  On a direct-binding titration, where one error common to every concentration moves log10 of the
  binding constant by exactly minus log10 of itself, the budget's 95 % interval for that source's
  variance holds the value the identity gives it. The identity holds where every fit of the
  analysis lies strictly inside the Ka bounds; a draw where one ran to a bound reports the edge of
  the box, where the output is constant, and is left out of the rate and counted beside it.

what-if-accuracy       3 cases                                  reported
  How far the what-if line lands from the truth: the first-order formula and the re-weighted
  cross-check against a second analysis run at the reduced uncertainty on the same data and the
  same design, with the effective sample size the cross-check carried. Both errors are given again
  over the draws where no fit ran to a Ka bound, since a fit that did reports the edge of the box
  rather than a spread of the inputs.

sobol-blocking         10 cases                                 reported
  What splitting one budget into independently scrambled blocks costs: the root-mean-square error
  of each index, block count by block count, at a fixed budget. Reported, not required.

replicate-exclusion-null 72 cases                                 <= 0.05
  Fitted replicate by replicate, a set of replicates measured alike — or alike but for one that
  carries three times the noise of the others — loses a replicate that agrees with the rest in at
  most one fit in twenty.

replicate-exclusion-power 96 cases                                 reported
  How often a per-replicate fit leaves out a replicate measured at three times or a third of the
  binding constant the others share, one of three, five or eight or two of five or eight, and how
  often it loses a good replicate beside it — what the replicate test gains a user, reported
  rather than required.

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
shared source really carries is not the quadrature the first check compares against, and the
spread the second one measures is a jump of decades rather than the movement of the inputs. Each
row records whether the baseline ran there and how many of the design's fits did. The judged
coverage of `source-variance-exact` is over the rows where none did, with `~on_bound.KEY` the share
that were left out beside it; `what-if-accuracy` keeps every row and gives its two error series a
second time over the clean ones, `~formula_err_clean.KEY` and `~reweighted_err_clean.KEY`. A case
whose regime leaves most rows on a bound therefore says little: widen the Ka bounds or move the
case to a regime the default box contains.

The five `noise-law-*` and `conflict-single-proportional` entries read one change from two sides.
`noise-law-coverage` and `noise-law-aware` run replicated titrations whose noise the fit reads a
law off, and `noise-law-lof-null` and `noise-law-conflict-null` ask the two tests of the same fits
what they do on data the model describes and inputs entered as wrongly as stated.
`conflict-single-proportional` reads the proportional cases of `robustness`, which are single
titrations: one curve cannot show how the noise varies along it, so there the noise is taken as
constant, and the rate is reported rather than judged — it is what the fit does where no law can be
estimated, and the summary and the plot guide say so.

`noise-law-coverage` spans constant, proportional and mixed noise at two, three and eight
replicates and 8 and 20 points and at four replicates and 12 points for every one-Ka assay in the
medium and strong regimes, the lamp case beside them, and the two-step model at 12 points. Where
the law gives the signal a share above zero the fit is weighted by the law at the fitted curve of a
first fit and its interval is widened to hold for every share the replicates allow; the rows say how
often that happened (`refit`), how wide that range of shares was (`share_set_width`) and by what
factor each interval was widened (`inflation.KEY`). A law read at the measured means of few
replicates can weight some points a thousand times others, so beside the judged rate the table
gives the coverage in bins of that spread — `cov_wratio_le10.KEY`, `cov_wratio_10-1e3.KEY` and
`cov_wratio_gt1e3.KEY` — with the distribution of the ratio at the means, `weight_ratio`, and of the
weights the fit ran with, `fit_weight_ratio`. `noise-law-lof-null` reads the same fits; wherever
the law was read off the replicates the misfit test's F ratio is read against a parametric
bootstrap at that law, and its rate says whether that reference holds the level.

The three `addition-*` entries read the random error of each titrant addition. `addition-coverage`
states the error exactly as it was drawn, the inputs otherwise exact, and judges the reported
interval, which the stated error widens by a factor and never narrows; beside the rate it reports
that factor (`inflation.KEY`), how often the interval is closed on both sides (`open.KEY` is the
rest), its width, and its width over the width of the interval the same data give with the
additions taken as exact (`width_ratio.KEY`, read where both are closed) — what the widening costs,
which a coverage rate alone does not show. `addition-misfit-null` reads the same fits and asks the
misfit test of each — the runs test of one titration, the lack-of-fit test of replicates, named
apart — how often it calls a model that describes the data inadequate. `addition-misstated` runs
the same measurements stated otherwise: an error stated where none was drawn, one stated at a third
of its size, and repeated reads stated as separate titrations. It describes what the interval and
the misfit test do then and judges nothing, since the interval's premise is that the statement is
right.

Four more read the additions where something else moves with them. `addition-aware-coverage` states
the inputs as wrongly as they were entered beside the additions, so the input-aware interval and the
design effect widen the interval together, and `addition-verdict-null` reads its fits for the two
false alarms the additions could cause: the additions move the curve much as a titrant scale or a
concentration does, a fit free to move those inputs puts part of them there, and the conflict
statistic's reference carries that part. `addition-replicate-exclusion-null` runs the per-replicate
mode on separate titrations, each with its own addition errors, which move the replicates' own Ka
apart by more than their scatter; the replicate test divides its statistic by each replicate's
design effect and compares their scatter with the addition residue taken out.
`addition-joint-region` judges the region of the pair, which the additions widen as they widen the
two intervals.

`one-step-null` fits both stepwise models to titrations that carry no second step — the second
constant a millionth of the first — and asks how often the reported interval of that constant is
closed below. A lower edge there tells the user the data hold a second step; the fit leaves that
side open unless the one-step model is rejected at 0.5 %, so the rate is the false-alarm rate of
that test, judged against Bradley's limit of 0.75 %, with the p-value each fit read reported
beside it. The rule acts on the input-aware interval as well, which `input-aware-coverage` covers
through its two-step cases.

`replicate-exclusion-null` and `replicate-exclusion-power` run the per-replicate mode, the fit of
every replicate on its own followed by the test of whether they share their binding constants, through
`fit_measurement_set_per_replica` — the call the interface makes. Every other check fits the average
of the replicates. The null check judges, per fit, whether a replicate measured like the others was
left out; one noisy replicate among them is part of the null, since it shares the binding constant
and leaving a clean replicate out because of it is a false exclusion all the same. How often the
noisy or the shifted replicates themselves are left out is reported, with the coverage of the
interval the fit reports: for a noisy replicate that is the power of Cochran's test to exclude a
replicate whose scatter is out of line with the rest, and not a false exclusion.

`before-after` runs the release before the engine. It extracts that commit with `git archive`
into a directory of its own and runs it in a subprocess with that directory on the path, so the
comparison needs nothing but this repository.

## Tables

Generated by `python -m validation tables`. Empty until the checks have been run.
