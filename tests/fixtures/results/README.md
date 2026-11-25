# Released results files

Genuine exports, each written by the release its name carries, so the import
path is tested against files the app really produces rather than dicts a test
assembles.

Every file fits `data/IDA_system.txt` with the demo IDA conditions
(`Ka_dye` 16.8 MM⁻¹, `[Host]₀` 4.3 µM, `[Dye]₀` 6 µM) at 60 trials:

| File | Release | Fit | Min R² |
|---|---|---|---|
| `v1_3_0_avg.json` | v1.3.0 | average of the replicates | 0.90 |
| `v1_3_0_pr_drop.json` | v1.3.0 | per replicate, replicate `0` left out | 0.99 |
| `v150_avg.json` | v1.5.0 | average of the replicates | 0.90 |
| `v150_pr_all.json` | v1.5.0 | per replicate, all eight fitted | 0.90 |
| `v150_pr_drop.json` | v1.5.0 | per replicate, replicate `0` left out | 0.99 |

`tests/unit/test_released_results.py` imports each one against
`data/IDA_system.txt` and pins the status and the numbers a user sees. To add a
file, check out the release, run its own `fit_measurement_set` on a dataset in
`data/`, and write `FitResult.to_dict()` as JSON.
