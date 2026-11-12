"""Dump the IDA demo's fit at the entered inputs (``FitResult.conditional``) for the Simulation view.

Run from the repo (for its venv):
    uv run python -m docs.design.prototype.data.dump_conditional

Drives ``FittingSession.load_demo_ida()`` offscreen, as ``dump_demo.py`` does, waits for
the fit, and writes ``conditional_fit.json`` next to this file: the entered conditions,
the conditional parameters (every entered input taken as exact), the replicate scatter
of the replicates the fit used, and the input-aware estimates beside them for reference.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

HERE = Path(__file__).resolve().parent


def main():
    import numpy as np
    from PyQt6.QtCore import QLocale
    from PyQt6.QtWidgets import QApplication

    QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
    app = QApplication(sys.argv)

    import gui.fitting_session as fs
    from core.pipeline.reporting import fit_replica_ids

    session = fs.FittingSession()
    session.load_demo_ida()
    t0 = time.monotonic()
    while session.model.fit_running() and time.monotonic() - t0 < 600:
        app.processEvents()
        time.sleep(0.02)
    for _ in range(20):
        app.processEvents()

    st = session.model
    result = st.fit_results[-1]
    ms = st.measurement_set
    cond = session._assay_panel.current_conditions()
    used = set(fit_replica_ids(result) or [])
    sigs = np.array([np.asarray(s, dtype=float) for rid, s in zip(ms.replica_ids, ms.signals) if rid in used])
    sd = sigs.std(axis=0, ddof=1)
    out = {
        'conditions': {k: float(getattr(v, 'magnitude', v)) for k, v in cond.items()},
        'conditional': {k: float(v.magnitude) for k, v in result.conditional.parameters.items()},
        'conditional_r2': float(result.conditional.r_squared),
        'input_aware': {k: float(v.magnitude) for k, v in result.parameters.items()},
        'replicate_sd_rms': float(np.sqrt(np.mean(sd**2))),
        'replicate_sd': sd.tolist(),
        'replicates_used': sorted(used),
    }
    (HERE / 'conditional_fit.json').write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != 'replicate_sd'}, indent=1))
    app.quit()


if __name__ == '__main__':
    main()
