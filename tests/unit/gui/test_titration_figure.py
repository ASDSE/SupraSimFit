"""The saved titration figure: every path that writes one composes the same head above the plot.

A saved figure leaves the window behind, so it carries what the view states beside the
plot: its title and description with the legend, and — for a fit — the summary of the
fit drawn (each binding constant with its reading and interval, R², the replicates used).
Measurements saves the raw titration: its points and legend, no fit.
"""

from __future__ import annotations

import re

import pyqtgraph as pg
import pytest

pytest.importorskip('PyQt6')

from core.assays.registry import AssayType  # noqa: E402
from gui import results as R  # noqa: E402
from gui.design import components as C  # noqa: E402
from gui.plotting.labels import fmt_param_plain  # noqa: E402
from gui.session_model import Change  # noqa: E402
from tests.unit.gui.session_setup import state_binding  # noqa: E402
from tests.unit.gui.test_results import fit_on, four_replicates  # noqa: E402


@pytest.fixture
def session(qapp):
    from gui.fitting_session import FittingSession

    made = FittingSession()
    yield made
    made.close()


@pytest.fixture
def saved(monkeypatch):
    """What each saved titration is composed of, recorded as it is written: legend, texts and curves."""
    import gui.views.titration as T

    real = T.export_stacked
    figures: list[dict] = []

    def record(parts, path, *, width_px):
        head, plot = parts
        (legend,) = head.findChildren(C.LegendRow)
        texts = [w.text for w in head.findChildren(C.PaintedText)]
        texts += [w.doc.toPlainText() for w in head.findChildren(C.PaintedNote)]
        curves = [i for i in plot.items if isinstance(i, pg.PlotDataItem)]
        figures.append({'legend': list(legend.items), 'text': '\n'.join(texts), 'curves': len(curves)})
        real(parts, path, width_px=width_px)

    monkeypatch.setattr(T, 'export_stacked', record)
    return figures


def _fitted(session):
    """Four replicates, A switched off, and a fit of the others shown."""
    state_binding(session, assay_type=AssayType.GDA)
    session.model.load(four_replicates(), None)
    session.model.set_replicate('0', False)
    fit = fit_on(session.model.measurement_set)
    session.model._held_fit_results = [fit]
    session.model.changed.emit(Change.RESULTS)
    return fit


def _svg_text(path) -> str:
    """The text a saved SVG draws, its elements' contents one per line."""
    return '\n'.join(t.strip() for t in re.findall(r'>([^<>]+)<', path.read_text(encoding='utf-8')) if t.strip())


def _write(session, path_name: str, path) -> None:
    if path_name == 'Export several':
        from gui.session import build_artefacts, export_batch

        (art,) = [a for a in build_artefacts(session) if a.key == 'fit_svg']
        ((_label, written, error),) = export_batch([art], path.parent, path.stem)
        assert error is None
        written.rename(path)
    else:
        {'Fit results': session._results, 'Plot appearance': session._appearance}[path_name].export_image(str(path))


@pytest.mark.parametrize('path_name', ['Fit results', 'Plot appearance', 'Export several'])
def test_a_saved_fit_carries_the_legend_the_curve_and_the_summary(session, saved, tmp_path, path_name):
    fit = _fitted(session)
    ms = session.model.measurement_set
    expected = R.titration(ms, [fit], AssayType.GDA, session.model.settings.replicate_display)
    path = tmp_path / 'fit.svg'

    _write(session, path_name, path)

    ((figure),) = saved
    assert figure['legend'] == expected.legend
    assert figure['curves'] == 1
    (block,) = R.ka_blocks(fit)
    text = figure['text']
    assert block.plain_value in text and block.interval in text
    assert R.reading(fit)[0] in text and 'R² 0.9980' in text
    assert '3 of 4' in text and 'A switched off' in text
    # Written into the file as text, the legend's words among it.
    drawn = _svg_text(path)
    assert block.plain_value in drawn and 'Replicates used' in drawn
    assert all(entry[1] in drawn.splitlines() for entry in expected.legend)


def test_measurements_saves_the_raw_titration_with_its_legend_and_no_fit(session, saved, tmp_path):
    _fitted(session)
    expected = R.titration(session.model.measurement_set, [], AssayType.GDA, R.RAW)

    session._measurements.export_image(str(tmp_path / 'raw.png'))

    ((figure),) = saved
    assert figure['legend'] == expected.legend
    assert figure['curves'] == 0
    assert 'raw signal, as loaded' in figure['text'] and 'Kₐ' not in figure['text']


def test_a_saved_fit_of_two_binding_constants_states_both(session, saved, tmp_path):
    from tests.unit.gui.test_fit_results_view import _two_ka_per_replica

    session.model._held_fit_results = [_two_ka_per_replica()]
    session.model.changed.emit(Change.RESULTS)

    session._results.export_image(str(tmp_path / 'fit.png'))

    ((figure),) = saved
    lines = figure['text'].splitlines()
    for key in ('Ka_HG', 'Ka_HG2'):
        assert sum(line.startswith(f'{fmt_param_plain(key)} ') for line in lines) == 1
    assert figure['curves'] == 1
