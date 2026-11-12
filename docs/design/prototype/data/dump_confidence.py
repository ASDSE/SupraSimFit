"""Drive the real FittingSession through load_demo_ida() and dump the Ka confidence page's own text."""

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
    from gui.plotting import identifiability_widget as IW
    from gui.plotting import labels as L

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
    w = session._identifiability_widget
    result = session.model.fit_results[-1]
    from core.pipeline.reporting import summarize_parameters
    from gui.widgets.assay_conditions import result_input_labels

    diag = result.diagnostics
    labels = result_input_labels(result.assay_type, result.fit_config)
    out = {
        'summary_html': w._summary.text(),
        'verdict_headline': w._verdict.text(),
        'verdict_tone': w._verdict.property('tone'),
        'notice_html': w._notice.text() if w._notice.isVisibleTo(w) else '',
        'notes_html': w._notes.text(),
        'notes_list_html': list(w._note_lists[0]),
        'legend_html': w._legend.text(),
        'verdict_sentence_plain': L.verdict_sentence(diag, result.input_shifts, labels, html=False),
        'split_note': L.SPLIT_NOTE,
        'cut_note': IW._CUT_NOTE,
        'cut_step_note': IW._CUT_STEP_NOTE,
        'weighted_r2_note': IW._WEIGHTED_R2_NOTE,
        'tooltip': w.toolTip(),
        'r2_name': w._r2_name(),
        'widening': L.widening_sentences(summarize_parameters(result), result, L.fmt_param_plain),
    }
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print('ok', time.monotonic() - t0)
    session.model._stop_profile()
    session.close()


if __name__ == '__main__':
    main()
