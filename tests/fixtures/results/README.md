# Results files

Genuine exports, each written by the version of the app it names, so the import
path is tested against files the app really produces rather than dicts a test
assembles. `tests/unit/test_released_results.py` imports each one against the
data it was made on and pins the status and the numbers a user sees.

## Files written by released versions

Every one fits `data/IDA_system.txt` with the demo IDA conditions
(`Ka_dye` 16.8 MM⁻¹, `[Host]₀` 4.3 µM, `[Dye]₀` 6 µM) at 60 trials:

| File | Release | Fit | Min R² |
|---|---|---|---|
| `v1_3_0_avg.json` | v1.3.0 | average of the replicates | 0.90 |
| `v1_3_0_pr_drop.json` | v1.3.0 | per replicate, replicate `0` left out | 0.99 |
| `v150_avg.json` | v1.5.0 | average of the replicates | 0.90 |
| `v150_pr_all.json` | v1.5.0 | per replicate, all eight fitted | 0.90 |
| `v150_pr_drop.json` | v1.5.0 | per replicate, replicate `0` left out | 0.99 |

To add a file, check out the release, run its own `fit_measurement_set` on a
dataset in `data/`, and write `FitResult.to_dict()` as JSON.

## Files written before the fit reported confidence intervals

Both fit `pr42_data.txt` with the conditions below at 40 trials, a minimum R² of
0.95 and seed 20260918:

| File | Written by | Fit |
|---|---|---|
| `pr42_avg.json` | commit `ccba0f1` | average of the three replicates |
| `pr42_pr.json` | commit `ccba0f1` | per replicate, all three fitted |

They carry a pool, an attempt record and an `uncertainty_source` entry, and no
`format` key — the layout the explicit legacy reader handles — so an import
keeps their reported fit and shows it without an interval.

`pr42_data.txt` beside them holds the data they were fitted on: a synthetic IDA
titration of 30 guest concentrations up to 50 µM into `[Host]₀` = 10 µM and
`[Dye]₀` = 5 µM, with `Ka_dye` = 0.5 MM⁻¹, a true `Ka_guest` of 2 MM⁻¹, signal
coefficients `I0` = 0, `I_dye_free` = 5·10⁷ au/M and `I_dye_bound` = 3·10⁸ au/M
(the `tests/conftest.py` IDA ground truth), and three replicates carrying 2 %
proportional Gaussian noise (NumPy seed 20260918). With that tree on
`PYTHONPATH`, the signals are generated from `ida_signal`, written with
`write_measurements_txt`, loaded again and fitted by `fit_measurement_set`;
`FitResult.to_dict()` is written as JSON.

## A file that records no equilibrium arithmetic

`unmarked_gda.json` carries no `model_arithmetic` entry, so its stored scores
are those of the earlier equilibrium arithmetic and an import reproduces them
with `core.models.equilibrium.legacy_arithmetic` before showing the numbers of
the present one. Its pool reaches binding constants of 1e12 M⁻¹, where the two
arithmetics differ by up to 3e-5 relative in RMSE; on the demo IDA data above
they differ by at most 3e-7, which the import gate would let pass unnoticed.

`unmarked_gda_data.txt` beside it holds the data the fit was made on: a
synthetic GDA titration of 15 dye concentrations up to 2 µM into
`[Host]₀` = `[Guest]₀` = 0.2 µM, with `Ka_dye` = 10 MM⁻¹, a true `Ka_guest` of
100 MM⁻¹, signal coefficients `I0` = 0, `I_dye_free` = 5·10⁷ au/M and
`I_dye_bound` = 3·10⁸ au/M, and three replicates carrying 1 % constant Gaussian
noise (NumPy seed 20260917).

Both files are written by the code at commit `ccba0f1`: with that tree on
`PYTHONPATH`, the signals are generated from `GDAAssay.forward_model`, written
with `write_measurements_txt`, loaded again, and fitted by `fit_measurement_set`
with the conditions above, 40 trials, a minimum R² of 0.95 and seed 20260917;
`FitResult.to_dict()` is written as JSON.

## A file whose fit moved the inputs it was given an uncertainty for

`input_aware_ida.json` is a fit of the average of three replicates whose host
concentration was entered 8 % above the value the data were made at, with that
stock stated to 10 % and the titrant to 3 %. The fit moves the host
concentration by −8.6 % and reports a Ka of 1.88 MM⁻¹ against the 2 MM⁻¹ the
data carry, where the interval that holds the entered inputs exact — the file's
`conditional` block — runs from 2.14 to 2.60 MM⁻¹ and does not reach the truth.
Its `diagnostics` say `inputs_explain`: at the entered inputs the replicates
reject the curve (lack of fit p = 1e-7) and once the inputs move they do not
(p = 0.55).

Its `noise` block holds the law the three replicates show, a share of 0.56
between a floor of 3.2 au and 0.6 % of the signal, and the fit counts each
titration point by the weight that law gives it.

An import scores the reported parameters where the fit put the inputs, so the
file verifies; strip its `input_shifts` and the same numbers no longer describe
the data, which is what `different_data` says.

`input_aware_ida_data.txt` beside it holds the data: a synthetic IDA titration
of 20 guest concentrations up to 50 µM into `[Host]₀` = 10 µM and `[Dye]₀` =
5 µM, with `Ka_dye` = 0.5 MM⁻¹, a true `Ka_guest` of 2 MM⁻¹, signal
coefficients `I0` = 0, `I_dye_free` = 5·10⁷ au/M and `I_dye_bound` = 3·10⁸ au/M
(the `tests/conftest.py` IDA ground truth), and three replicates carrying 1 %
proportional Gaussian noise (NumPy seed 20260921). The signals are generated
from `ida_signal`, written with `write_measurements_txt`, loaded again and
fitted by `fit_measurement_set` with `[Host]₀` entered as 10.8 µM, the average
of the replicates and the two uncertainties above; `FitResult.to_dict()` is
written as JSON with an indent of two.

## A file whose totals were diluted by the titrant, with a shared error source

`diluted_shared_ida.json` is a fit of the average of three replicates of a
titration whose fixed concentrations fall with every addition of titrant. The
stock is declared at 0.5 mM against a highest titrant concentration of 50 µM, so
the host and the dye are down to 90 % of their entered values at the last point,
and the stock holds neither of them. `[Host]₀` carries an uncertainty of its own
(σ 3 %) and one source named *Host and dye stock* (σ 4 %) moves `[Host]₀` and
`[Dye]₀` together, so the file's `fit_config` carries a `shared_sources` entry
and its `input_shifts` report the shared source under its own key beside the
host's own shift. The reported interval, 1.84 to 2.13 MM⁻¹, holds the 2 MM⁻¹
the data carry. Its `noise` block reads the replicates' scatter as
proportional to the signal, 0.9 % of it, the structure the data were made
with.

An import rebuilds the diluted assay from the file's own `titrant_stock` and
`stock_contains` conditions and scores the reported parameters where the fit put
the inputs, so the file verifies; scored with the totals held constant instead,
the same parameters miss the data by an order of magnitude more.

`diluted_shared_ida_data.txt` beside it holds the data: a synthetic IDA
titration of 20 guest concentrations up to 50 µM into `[Host]₀` = 10 µM and
`[Dye]₀` = 5 µM diluted as above, with `Ka_dye` = 0.5 MM⁻¹, a true `Ka_guest` of
2 MM⁻¹, signal coefficients `I0` = 0, `I_dye_free` = 5·10⁷ au/M and
`I_dye_bound` = 3·10⁸ au/M (the `tests/conftest.py` IDA ground truth), and three
replicates carrying 1 % proportional Gaussian noise (NumPy seed 20260922). The
signals are generated from `IDAAssay.forward_model` with the stock declared,
written with `write_measurements_txt`, loaded again and fitted by
`fit_measurement_set` with the entered conditions above, the stock, the two
error sources and the average of the replicates; `FitResult.to_dict()` is
written as JSON with an indent of two.
