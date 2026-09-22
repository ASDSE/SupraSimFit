# tests/ — Testing Philosophy

This suite protects the **scientific correctness** of a binding-assay fitting
toolkit. A test earns its place by catching a plausible math or logic bug that
would otherwise ship silently. Use these principles to decide *what* to test and
to write tests that are meaningful rather than ceremonial.

## What's worth testing — the three pillars

Most tests should serve one of these:

1. **Scientific validity** — does the math do the right thing? Forward-model
   values at known inputs, conservation / mass-balance laws, limiting cases
   (no-guest → DBA, zero concentration, saturation), and parameter recovery:
   fit synthetic data with known ground truth and assert the fitted parameters
   return within tolerance.
2. **Data integrity** — do I/O and transforms preserve values? Round-trip a
   write→read, a unit conversion, a reshape; assert what went in comes out.
3. **Fail-fast contracts** — do invalid inputs raise immediately with a clear
   message instead of silently producing garbage? (Wrong units, missing
   conditions, mismatched shapes, non-positive constants.)

If a proposed test doesn't serve one of these, question whether it's worth adding.

## How to write a meaningful test

- **Test a property, not an implementation.** Assert an invariant, a limit, a
  conservation law, or recovery-within-tolerance — not that a line of code
  returns what that same line of code computes.
- **Never check source against itself.** Computing the expected value with the
  same formula the code uses (or calling the same method on both sides of an
  assertion) is a tautology that passes even when the code is wrong. Derive the
  expected value an **independent** way: solve the equilibrium by a different
  method, hand-compute a small case, or use a closed-form limit.
- **Prefer analytical / direct checks over fit-then-compare.** A direct model
  call with an independently-computed expected value is faster and stronger than
  running a fit and inspecting its output. Reserve full fits for genuine
  end-to-end recovery tests — one or two representative cases, not every
  parameter combination.
- **For fits, assert recovery within a tolerance band, not bit-equality.**
  Convention: ~10 % for clean synthetic data, ~25 % for ~5 % Gaussian noise.
- **One test, one property.** Each test pins a single invariant or behavior. If
  two tests catch the same class of bug, keep the stronger one.
- **Pin observed behavior for edge cases — don't assume it.** For degenerate or
  boundary inputs (NaN, empty array, single point, underdetermined fit), run it
  once, see what actually happens, and assert that with a comment on *why* it's
  correct.
- **Reproduce a bug as a failing test first**, then make it pass.

## What to avoid

- Safety-blanket tests with no logic beneath them: constructor-sets-attribute,
  trivial getters, `repr`, default-value echoes, config dicts that merely
  round-trip. Skip these unless one guards a specific past regression.
- Sprawling `parametrize` matrices that drive one code path many times. Cover the
  nominal case, the boundaries (zero / edge), and one pathological case; justify
  anything beyond that.
- Slow tests where a smaller input or an analytical value verifies the same math.
  A slow suite is run less often, so bugs survive longer.

## Repo-specific truths that make tests meaningful

- **Reuse the synthetic ground truth.** `tests/conftest.py` is the single source
  of known-truth parameters, data generators, recovery bounds, and the tolerance
  helper. Build on it; don't re-roll constants or synthetic data per file.
- **Fits are deterministic.** A fit draws no random numbers: the same data,
  conditions and bounds give the same parameters every run, so a test may compare
  two fits of the same input exactly. Still assert the recovered *physics* against
  independent ground truth, not a number copied from a previous run — a pinned
  number passes a fit that is wrong in the same way twice. Only the sensitivity
  analysis samples, and it takes a `seed`. The reference distributions of the
  runs test and of the conflict statistic are drawn at a fixed seed, which makes
  each p-value a function of its arguments like any other computed number.
- **Weights of one are no weights.** Where two or more replicates were measured,
  a fit reads a noise law off their scatter (`core.pipeline.noise`) and hands
  `Projection` one weight per titration point. A single titration, and replicates
  whose law comes out constant, get exactly `np.ones`: whitening multiplies by
  1.0, so the fit, its interval and its diagnostics are those of an engine
  without weights *to the last bit*. Tests pin that by comparing the two
  projections' numbers exactly — `==`, not `approx` — and they are what a change
  that reorders the arithmetic of the unweighted path has to answer to. The law
  itself draws no random numbers either, but a test of it asserts a property —
  proportional noise gives a share near one, a replicate measured at a slightly
  different gain is not read as noise — against independently generated data,
  never a share copied from a run.
- **An input-aware fit costs seconds.** Letting the inputs move turns each point
  of a profile into a small bounded optimisation: typically 1–2 s per fit, up to
  about 20 s for one association constant and 45 s for two on hard designs with
  few points. A test that states an input uncertainty belongs in
  `tests/integration/`; the fast layer states none, or drives
  `core.pipeline.input_aware` on a handful of points.
- **Intervals are a claim to check, not a field to echo.** A test of a confidence
  interval either verifies the property that defines it — the endpoint is where
  the profile crosses the threshold, the interval contains the fit, coverage over
  many synthetic datasets is near the nominal level — or it is testing nothing.
  Asserting that the reported interval equals what the same call returns is a
  tautology.
- **Two intervals, two claims.** A fit reports the interval *conditional on the
  entered inputs* and, when an uncertainty is stated for an input, the
  *input-aware* one that lets the inputs move inside it. Their defining
  properties differ and are tested separately: the conditional edge is where the
  profile crosses `SSR_min (1 + m F(m, n − p)/(n − p))`; the input-aware edge is
  where the penalised profile `n log S + z'z` rises by `n log(1 + m F(m, ν)/ν)`
  above its minimum, with the effective residual degrees of freedom
  `ν = n − p − Σw`. `m` is 1 plus the signal parameters the best fit determines
  and the fit at that Ka holds on a bound, so it is 1 wherever none is. Two
  reductions are worth pinning cheaply: with every input fixed the input-aware
  result *is* the conditional one, and as a stated σ goes to zero the two edges
  converge. Coverage — the property the interval is for — is a sweep over
  synthetic datasets with the inputs drawn at their stated uncertainty, and
  belongs in `tests/integration/`.
- **A diagnostic is a rate, not a p-value.** The misfit tests and the conflict
  statistic claim a false-alarm rate at their level and some power against a real
  fault. A unit test pins what is checkable fast — the runs test on residuals of
  one sign, the lack-of-fit F ratio against a hand-computed replicate scatter, a
  verdict read from given test results — and the rates come from the checks in
  `validation/`. Never assert that a single dataset gets a particular verdict
  because a run once produced it.
- **A conflict names no input.** The statistic judges the stated inputs together,
  so a test may assert that a planted input error raises the statistic, never
  that the shift lands on the input that was planted.
- **Signal coefficients are degenerate.** In DBA/IDA only `Ka` is identifiable
  (`I0`, `I_dye_free`, `I_dye_bound` trade off). Test `Ka` recovery and signal
  reconstruction — never the individual signal coefficients.
- **GUI tests never pop a window.** A widget test that needs real geometry
  (`tabRect()`, child positions, `isVisible()`) has to be laid out, and Qt only
  computes that on `show()`. Set `WA_DontShowOnScreen` before showing: the
  layout resolves, nothing appears on screen, and the test still runs under the
  platform's native style. A visible window interrupts whoever is running the
  suite, and needs a display server that CI will not have.
- Layout: `tests/unit/` is the fast layer, `tests/unit/gui/` holds PyQt6 widget
  tests, `tests/integration/` runs real fits (the slow part).

## Running

```bash
uv run pytest                  # full suite
uv run pytest tests/unit       # fast layer only (skips the integration fits)
uv run pytest -k <pattern>     # iterate on a subset
uv run pytest -x               # stop on first failure
```
