"""Run a real Sobol' sensitivity analysis on the IDA demo session and cache what the view needs.

Drives a FittingSession offscreen through load_demo_ida() (the same data, conditions,
bounds, uncertainties and Outlier Removal the app's demo uses), waits for the fit,
then calls core.pipeline.sensitivity.run_sensitivity with exactly the arguments
FittingSession.run_sensitivity() hands the SensitivityWorker, with the panel's
default settings (Sensitivity indices, sample size 1024, no fixed seed).

The texts the real SensitivityWidget and FitSummaryWidget would print are read
back from those widgets, so the view shows the app's own wording and numbers.

Run from the repo:
    uv run python -m docs.design.prototype.data.compute_sensitivity
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from dataclasses import replace
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
OUT = Path(__file__).resolve().parent / 'sensitivity.json'


def clean(v):
    import numpy as np

    if isinstance(v, dict):
        return {str(k): clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [clean(x) for x in v]
    if isinstance(v, np.ndarray):
        return clean(v.tolist())
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if hasattr(v, 'value') and hasattr(v, 'name'):  # Enum
        return v.name
    return v


def main():
    import numpy as np
    from PyQt6.QtCore import QLocale
    from PyQt6.QtWidgets import QApplication

    QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
    app = QApplication(sys.argv)

    import gui.fitting_session as fs
    from core.optimizer.ensemble import describe, describe_log10
    from core.pipeline.budget import what_if
    from core.pipeline.sensitivity import estimated_fit_count, run_sensitivity
    from gui.plotting.labels import plain_label
    from gui.plotting.sensitivity_widget import SensitivityWidget, _stated_pct, _stated_text

    session = fs.FittingSession()
    session.resize(1440, 900)
    session.show()
    session.load_demo_ida()
    t0 = time.monotonic()
    while (session.fit_running() or session._profile_worker is not None) and time.monotonic() - t0 < 900:
        app.processEvents()
        time.sleep(0.02)
    for _ in range(50):
        app.processEvents()
    print('fit done in', round(time.monotonic() - t0, 1), 's', flush=True)

    # Exactly what FittingSession.run_sensitivity() hands the worker.
    ms = session._state.measurement_set
    errors = session._input_panel.current_errors()
    panel = session._sensitivity_panel
    sens_config = panel.current_config(errors)
    assay_cls = session._assay_panel.get_assay_class()
    conditions = session._assay_panel.current_conditions()
    fit_config = session._fit_panel.current_config()
    custom_bounds = session._bounds_panel.current_bounds()
    if custom_bounds:
        fit_config = replace(fit_config, custom_bounds=custom_bounds)
    labels = session._input_panel.input_labels()
    n_inputs = len(labels)
    planned = estimated_fit_count(sens_config, n_inputs) + 1
    workers = fs.preferences.worker_count() if hasattr(fs, 'preferences') else None
    print('config', sens_config.mode, sens_config.n_samples, 'fits', planned, 'workers', workers, flush=True)

    t1 = time.monotonic()
    last = [0.0]

    def progress(done, total):
        if time.monotonic() - last[0] > 10:
            last[0] = time.monotonic()
            print(f'  {done}/{total}  {time.monotonic() - t1:.0f}s', flush=True)

    result = run_sensitivity(
        ms.with_active(ms.active_replica_ids),
        assay_cls,
        conditions,
        fit_config,
        sens_config,
        progress=progress,
        max_workers=workers,
        input_labels=labels,
    )
    seconds = time.monotonic() - t1
    print('sensitivity done in', round(seconds, 1), 's', flush=True)

    # Read the real widgets' wording back.
    widget = SensitivityWidget()
    widget.update_result(result)
    assay_type = widget._assay_type(result)
    out = {
        'how': 'FittingSession.load_demo_ida() offscreen, then core run_sensitivity() with the arguments '
        'FittingSession.run_sensitivity() passes (panel defaults)',
        'seconds': seconds,
        'planned_fits': planned,
        'workers': workers,
        'mode': result.mode.name,
        'n_samples': sens_config.n_samples,
        'seed_fixed': sens_config.seed is not None,
        'seed_used': result.seed_used,
        'n_success': result.n_success,
        'n_total': result.n_total,
        'n_planned': result.n_planned,
        'n_blocks_finished': result.n_blocks_finished,
        'stopped': result.stopped,
        'ka_keys': list(result.ka_keys),
        'baseline_ka': result.baseline_ka,
        'withheld': result.withheld,
        'homogeneity': result.homogeneity,
        'baseline_on_bound': result.baseline_on_bound,
        'n_on_bound': result.n_on_bound,
        'sources': list(result.sources),
        'source_inputs': result.source_inputs,
        'input_labels': labels,
        'source_labels': {s: plain_label(widget._input_label(assay_type, s)) for s in result.sources},
        'stated': {s: _stated_text(result, s) for s in result.sources},
        'stated_pct': {s: _stated_pct(result, s) for s in result.sources},
        'sobol_s1': result.sobol_s1,
        'sobol_st': result.sobol_st,
        'sobol_s1_ci': result.sobol_s1_ci,
        'sobol_st_ci': result.sobol_st_ci,
        'sobol_rows_left_out': result.sobol_rows_left_out,
        'elasticity': result.elasticity,
        'budget': {},
        'what_if': {},
        'widget_text': {},
        'sample_ka': {k: np.asarray(v, dtype=float) for k, v in (result.sample_ka or {}).items()},
        'sample_param_stats': {},
    }
    for ka_key, b in (result.budget or {}).items():
        out['budget'][ka_key] = {
            'variance': b.variance,
            'variance_ci': b.variance_ci,
            'sd': b.sd,
            'interactions': b.interactions,
            'rows': [
                {
                    'source': r.source,
                    'variance': r.variance,
                    'variance_ci': r.variance_ci,
                    'sd_if_exact': r.sd_if_exact,
                    'sd_if_exact_ci': r.sd_if_exact_ci,
                    'elasticity': r.elasticity,
                }
                for r in b.rows
            ],
        }
        wi = {}
        for r in b.rows:
            for frac in (0.0, 0.5):
                try:
                    a = what_if(result, ka_key, r.source, frac)
                    wi[f'{r.source}@{frac}'] = {
                        'sd': a.sd,
                        'sd_reweighted': a.sd_reweighted,
                        'effective_samples': a.effective_samples,
                        'largest_after': a.largest_after,
                    }
                except Exception as exc:  # noqa: BLE001
                    wi[f'{r.source}@{frac}'] = {'error': str(exc)}
        out['what_if'][ka_key] = wi
        texts = {
            'budget_header': widget._budget_header(result, ka_key),
            'budget_table': widget._budget_table(result, ka_key, assay_type),
        }
        if ka_key in widget._what_if:
            texts['what_if_sentence'] = widget._what_if_sentence(
                ka_key, b.rows[0].source, 0.5 * _stated_pct(result, b.rows[0].source)
            )
            texts['what_if_sentences'] = {
                r.source: widget._what_if_sentence(ka_key, r.source, 0.5 * _stated_pct(result, r.source))
                for r in b.rows
            }
        out['widget_text'][ka_key] = texts
    out['quality_note'] = widget._note.text()
    for key, vals in (result.sample_params or {}).items():
        v = np.asarray(vals, dtype=float)
        v = v[np.isfinite(v)]
        if v.size:
            out['sample_param_stats'][key] = {
                'linear': describe(v),
                'log10': describe_log10(v) if np.all(v > 0) else None,
                'n': int(v.size),
            }
    if result.baseline_fit is not None:
        out['baseline_params'] = {
            k: float(getattr(p, 'value', p)) if not hasattr(p, 'magnitude') else float(p.magnitude)
            for k, p in result.baseline_fit.parameters.items()
        }
        out['baseline_r2'] = result.baseline_fit.r_squared
    sp = result.sample_params or {}
    if sp:
        stacked = np.vstack([np.asarray(v, dtype=float) for v in sp.values()])
        out['n_fitted_samples'] = int(np.all(np.isfinite(stacked), axis=0).sum())
        out['n_samples_total'] = int(stacked.shape[1])

    # The fit summary the session floats over a Sobol' run.
    session._state.sensitivity_result = result
    try:
        session._summary_widget.set_sensitivity(result)
        session._summary_widget.show_samples(True)
        from PyQt6.QtWidgets import QLabel

        out['summary_texts'] = [
            lbl.text() for lbl in session._summary_widget.findChildren(QLabel) if lbl.text().strip()
        ]
    except Exception as exc:  # noqa: BLE001
        out['summary_texts_error'] = str(exc)

    OUT.write_text(json.dumps(clean(out), indent=1, ensure_ascii=False))
    print('wrote', OUT, flush=True)
    app.quit()


if __name__ == '__main__':
    main()
