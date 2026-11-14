"""Drive the real FittingSession through load_demo_ida() and dump what Ka confidence says of the demo fit."""

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
OUT = Path(__file__).parent / 'confidence_texts.json'


def main():
    from PyQt6.QtCore import QLocale
    from PyQt6.QtWidgets import QApplication

    QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
    app = QApplication(sys.argv)
    import gui.fitting_session as fs
    from core.pipeline.reporting import summarize_parameters
    from gui import confidence as CF
    from gui.plotting import labels as L
    from gui.widgets.assay_conditions import result_input_labels

    session = fs.FittingSession()
    session.resize(1440, 900)
    session.show()
    session.load_demo_ida()
    t0 = time.monotonic()
    while (session.model.fit_running() or session.model.profile_running()) and time.monotonic() - t0 < 900:
        app.processEvents()
        time.sleep(0.02)
    for _ in range(50):
        app.processEvents()
    result = session.model.fit_results[-1]
    profile = session.model.profile
    labels = result_input_labels(result.assay_type, result.fit_config)
    notes = CF.notes(result, profile, list(session.model.measurement_set.replica_ids))
    out = {
        'headers': [
            {'key': h.key, 'name_html': h.name, 'readings': [r.__dict__ for r in h.readings]}
            for h in CF.headers(result)
        ],
        'callouts': [c.__dict__ for c in CF.callouts(result, None)],
        'notes': {s.title: s.paragraphs for s in notes},
        'notes_trailing': {s.title: s.trailing for s in notes if s.trailing},
        'verdict_sentence_plain': L.verdict_sentence(result.diagnostics, result.input_shifts, labels, html=False),
        'split_note': L.SPLIT_NOTE,
        'widening': L.widening_sentences(summarize_parameters(result), result, L.fmt_param_plain),
    }
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print('ok', time.monotonic() - t0)
    session.model._stop_profile()
    session.close()


if __name__ == '__main__':
    main()
