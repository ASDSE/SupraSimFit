"""Drive a FittingSession offscreen through load_demo_ida and dump the real demo fit to demo.json."""

import json
import math
import os
import sys
import time
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

OUT = Path(__file__).parent


def clean(v):
    """JSON-safe conversion (nan/inf -> None, numpy -> python)."""
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
    return v


def interval_dict(iv):
    if iv is None:
        return None
    return {
        'low': iv.low,
        'high': iv.high,
        'open_low': iv.open_low,
        'open_high': iv.open_high,
        'level': iv.level,
        'dof': iv.dof,
        'split': iv.split,
        'inflation': iv.inflation,
    }


def main():
    import numpy as np
    from PyQt6.QtCore import QLocale
    from PyQt6.QtWidgets import QApplication, QLabel, QTextBrowser, QTextEdit

    QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    try:
        from gui.theme import APP_STYLESHEET

        app.setStyleSheet(APP_STYLESHEET)
    except Exception:
        pass

    import gui.fitting_session as fs
    from core.pipeline.inputs import TITRANT
    from core.pipeline.reporting import fit_replica_ids, input_replica_ids, reports_conditional, summarize_parameters
    from gui.session_model import SessionModel

    captured = {}
    orig = SessionModel._on_profile_complete

    def patched(self, profile):
        captured['profile'] = profile
        return orig(self, profile)

    SessionModel._on_profile_complete = patched

    session = fs.FittingSession()
    session.resize(1440, 900)
    session.show()
    statuses = []
    session.model.status_changed.connect(statuses.append)

    session.load_demo_ida()
    t0 = time.monotonic()
    while (session.model.fit_running() or session.model.profile_running()) and time.monotonic() - t0 < 900:
        app.processEvents()
        time.sleep(0.02)
    for _ in range(50):
        app.processEvents()
    fit_seconds = time.monotonic() - t0

    st = session.model
    result = st.fit_results[-1]
    ms = st.measurement_set

    # ---- data
    x = np.asarray(ms.concentrations, dtype=float)
    used = set(fit_replica_ids(result) or [])
    replicates = []
    for rid in ms.replica_ids:
        sig = ms.get_replica(rid) if hasattr(ms, 'get_replica') else None
        if sig is None:
            idx = list(ms.replica_ids).index(rid)
            sig = np.asarray(ms.signals)[idx]
        replicates.append(
            {
                'id': rid,
                'signal': np.asarray(sig, dtype=float),
                'active': rid in set(ms.active_replica_ids),
                'used_by_fit': rid in used,
                'dropped': rid not in used,
            }
        )
    used_sigs = np.array([r['signal'] for r in replicates if r['used_by_fit']])
    mean = used_sigs.mean(axis=0)
    sd = used_sigs.std(axis=0, ddof=1) if len(used_sigs) > 1 else np.zeros_like(mean)

    x_fit = np.asarray(result.x_fit.to('M').magnitude, dtype=float)
    y_fit = np.asarray(getattr(result.y_fit, 'magnitude', result.y_fit), dtype=float)
    # resample to 200 points on the fit's own curve
    xs = np.linspace(x_fit.min(), x_fit.max(), 200)
    ys = np.interp(xs, x_fit, y_fit)

    # ---- parameters
    rows = summarize_parameters(result)
    params = []
    for r in rows:
        params.append(
            {
                'key': r.key,
                'is_log': r.is_log,
                'estimate': r.estimate,
                'estimate_at_bound': r.estimate_at_bound,
                'unit': r.unit,
                'interval': r.interval,
                'interval_open': r.interval_open,
                'level': r.level,
                'degenerate': r.degenerate,
                'inflation': getattr(r, 'inflation', None),
                'conditional_estimate': r.conditional_estimate,
                'conditional_interval': r.conditional_interval,
                'conditional_inflation': r.conditional_inflation,
            }
        )
    ka = next(p for p in params if p['key'] == 'Ka_guest' and not p['is_log'])
    ka_log = next((p for p in params if p['key'] == 'Ka_guest' and p['is_log']), None)
    aware = not reports_conditional(result)

    # ---- diagnostics
    diag = result.diagnostics
    diag_d = None
    if diag is not None:
        diag_d = diag.to_dict()

    # ---- text shown in the summary widget
    def texts(widget):
        out = []
        for lbl in widget.findChildren(QLabel):
            t = lbl.text().strip()
            if t and lbl.isVisibleTo(widget):
                out.append(t)
        for tb in widget.findChildren(QTextEdit) + widget.findChildren(QTextBrowser):
            t = tb.toPlainText().strip()
            if t:
                out.append(t)
        return out

    summary_texts = texts(session._results.canvas) + texts(session._results.side)
    ident_texts = texts(session._confidence.canvas) + texts(session._confidence.side)

    # ---- inputs
    labels = session.model.uncertainty.input_labels()
    unc = []
    for key, spec in fs._DEMO_UNCERTAINTIES.items():
        unc.append(
            {
                'key': key,
                'label_html': labels.get(key, key),
                'kind': getattr(spec, 'kind', None) if not callable(getattr(spec, 'kind', None)) else None,
                'spec_repr': repr(spec),
                'sigma_pct': {'Ka_dye': 10.0, 'h0': 3.0, 'd0': 3.0, TITRANT: 3.0}[key],
            }
        )

    conds = session.model.settings.conditions
    cond_out = {}
    for k, v in conds.items():
        mag = getattr(v, 'magnitude', v)
        unit = str(getattr(v, 'units', ''))
        cond_out[k] = {'value_base': mag, 'unit_base': unit}
    if 'Ka_dye' in cond_out:
        cond_out['Ka_dye']['display'] = {'value': cond_out['Ka_dye']['value_base'] / 1e6, 'unit': 'MM⁻¹'}
    for k in ('h0', 'd0'):
        if k in cond_out:
            cond_out[k]['display'] = {'value': cond_out[k]['value_base'] * 1e6, 'unit': 'µM'}

    # ---- profile
    prof_out = None
    profile = captured.get('profile')
    if profile is not None:
        prof_out = {'weighted': profile.weighted, 'profiles': {}}
        for key, p in profile.profiles.items():
            d = {
                'ka_key': key,
                'conditional': {
                    'grid_per_M': p.grid,
                    'grid_per_MM': p.grid / 1e6,
                    'r2': p.r2,
                    'r2_cut': p.r2_cut,
                    'r2_threshold': p.r2_threshold,
                    'best_ka_per_M': p.best_ka,
                    'best_r2': p.best_r2,
                    'interval_per_M': interval_dict(p.interval),
                },
                'n_points': p.n_points,
                'n_params': p.n_params,
            }
            if p.aware is not None:
                a = p.aware
                d['input_aware'] = {
                    'grid_per_M': a.grid,
                    'grid_per_MM': a.grid / 1e6,
                    'r2': a.r2,
                    'r2_cut': a.r2_cut,
                    'r2_threshold': a.r2_threshold,
                    'interval_per_M': interval_dict(a.interval),
                    'offsets': a.offsets,
                }
            prof_out['profiles'][key] = d

    shifts = {}
    for k, s in (result.input_shifts or {}).items():
        shifts[k] = {kk: vv for kk, vv in vars(s).items()} if hasattr(s, '__dict__') else repr(s)

    params_q = {k: {'value': float(v.magnitude), 'unit': f'{v.units:~P}'} for k, v in result.parameters.items()}

    data = {
        'source': {
            'file': 'data/IDA_system.txt',
            'how': 'FittingSession.load_demo_ida() driven offscreen (QT_QPA_PLATFORM=offscreen); real FitWorker + ProfileWorker',
            'fit_and_profile_seconds': fit_seconds,
            'assay_type': result.assay_type,
            'model_name': result.model_name,
        },
        'x_label': 'Guest',
        'x_unit': 'µM',
        'y_label': 'Signal [a.u.]',
        'x_uM': x * 1e6,
        'replicates': replicates,
        'replicates_used': sorted(used, key=list(ms.replica_ids).index),
        'replicates_given': list(input_replica_ids(result) or []),
        'mean': mean,
        'sd': sd,
        'fit_curve': {'x_uM': xs * 1e6, 'y': ys},
        'fit_curve_native': {'x_uM': x_fit * 1e6, 'y': y_fit},
        'headline': {
            'key': 'Ka_guest',
            'label': 'Ka,guest',
            'input_aware': aware,
            'estimate_per_M': ka['estimate'],
            'low_per_M': ka['interval'][0] if ka['interval'] else None,
            'high_per_M': ka['interval'][1] if ka['interval'] else None,
            'estimate_MM': ka['estimate'] / 1e6,
            'low_MM': ka['interval'][0] / 1e6 if ka['interval'] else None,
            'high_MM': ka['interval'][1] / 1e6 if ka['interval'] else None,
            'unit': 'MM⁻¹',
            'level': ka['level'],
            'open': ka['interval_open'],
            'log10': {'estimate': ka_log['estimate'], 'interval': ka_log['interval']} if ka_log else None,
        },
        'conditional': {
            'estimate_MM': ka['conditional_estimate'] / 1e6 if ka['conditional_estimate'] else None,
            'low_MM': ka['conditional_interval'][0] / 1e6 if ka['conditional_interval'] else None,
            'high_MM': ka['conditional_interval'][1] / 1e6 if ka['conditional_interval'] else None,
        },
        'r_squared': result.r_squared,
        'rmse': result.rmse,
        'parameters': params_q,
        'parameter_rows': params,
        'degenerate_keys': list(result.degenerate_keys),
        'input_shifts': shifts,
        'diagnostics': diag_d,
        'noise': result.noise.describe() if result.noise is not None else None,
        'status_messages': statuses,
        'summary_widget_texts': summary_texts,
        'ka_confidence_widget_texts': ident_texts,
        'input_uncertainties': unc,
        'assay_conditions': cond_out,
        'profile': prof_out,
    }

    (OUT / 'demo.json').write_text(json.dumps(clean(data), indent=1, ensure_ascii=False, default=str))
    print('ok', fit_seconds, ka, result.r_squared, result.rmse)
    session.model._stop_profile()
    session.close()


if __name__ == '__main__':
    main()
