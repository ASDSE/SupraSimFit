"""Widget tests for the summary of a sensitivity run's samples (:mod:`gui.plotting.samples_summary`)."""

from dataclasses import replace

import numpy as np
import pytest

pytest.importorskip('PyQt6')

from tests.unit.gui.test_results import aware_result, per_replica_result, result  # noqa: E402


def _headers(table):
    return [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]


def _row(table, row):
    return [table.cellWidget(row, c).text() for c in range(table.columnCount())]


def _named_row(table, label_html):
    for r in range(table.rowCount()):
        if table.cellWidget(r, 0).text().startswith(label_html):
            return _row(table, r)
    raise AssertionError(f'no row labelled {label_html}')


def _sobol_run(samples, *, sample_r2=None, degenerate_keys=()):
    """A finished Sobol' run whose baseline is :func:`result` and whose samples are *samples*."""
    from core.pipeline.inputs import InputSpec
    from core.pipeline.sensitivity import SensitivityConfig, SensitivityMode, SensitivityResult

    n = len(next(iter(samples.values())))
    return SensitivityResult(
        mode=SensitivityMode.SOBOL,
        assay_type='GDA',
        ka_keys=('Ka_guest',),
        baseline_ka={'Ka_guest': 1.24e6},
        x_offsets_pct=None,
        y_offsets_pct=None,
        ka_grid=None,
        n_success=n,
        n_total=n,
        config=SensitivityConfig(SensitivityMode.SOBOL, 1024, {'h0': InputSpec.sigma_pct(5.0)}, seed=0),
        seed_used=0,
        sample_r2=None if sample_r2 is None else np.asarray(sample_r2, dtype=float),
        baseline_fit=result(),
        sample_params={key: np.asarray(v, dtype=float) for key, v in samples.items()},
        degenerate_keys=degenerate_keys,
    )


def _summary(run=None, fit=None):
    from gui.plotting.samples_summary import SamplesSummary

    widget = SamplesSummary()
    widget.update_result(result() if fit is None else fit)
    if run is not None:
        widget.set_sensitivity(run)
    return widget


def test_the_summary_tables_the_fitted_samples_around_the_run_s_own_fit(qapp):
    """Each column is the stated statistic of the samples — hand-computed here, not read back from the widget."""
    from gui.plotting.samples_summary import _SAMPLE_HEADERS

    # I0 over four samples, the last one unfitted: median 2, MAD 1, min 1,
    # max 3, and [P16, P84] = [1.32, 2.68] by linear interpolation.
    run = _sobol_run(
        {
            'Ka_guest': [1e6, 1.2e6, 1.4e6, np.nan],
            'I0': [1.0, 2.0, 3.0, np.nan],
            'I_dye_free': [5e4, 5e4, 5e4, np.nan],
            'I_dye_bound': [8e4, 8e4, 8e4, np.nan],
        }
    )
    widget = _summary(run)

    assert _headers(widget._table) == list(_SAMPLE_HEADERS)
    _, estimate, median_mad, _, p68, span, _ = _named_row(widget._table, '<b>I<sub>0</sub>')
    assert estimate == '100'  # the run's own fit, not a statistic of the samples
    assert median_mad == '2.00 ± 1.00'
    assert p68 == '[1.32, 2.68]'
    assert span == '[1.00, 3.00]'


def test_the_summary_reports_how_many_samples_it_summarises(qapp):
    """A sample with no fit is left out of the statistics and counted, never quietly folded in."""
    widget = _summary(_sobol_run({'I0': [1.0, 2.0, 3.0, np.nan]}, sample_r2=[0.99, 0.98, 0.97, np.nan]))

    assert widget._fitted_label.text() == '3 / 4'
    assert widget._r2_range_label.text() == '[0.9700, 0.9900]'
    assert 'could not be fitted' in widget._caption.text()


def test_the_caption_counts_a_single_sample_as_one_sample(qapp):
    """A count reads as a sentence, not as a slot: one sample is 'the one sample', never 'the 1 samples'."""
    one_of_three = _summary(_sobol_run({'I0': [1.0, np.nan, np.nan]}))
    one_of_one = _summary(_sobol_run({'I0': [1.0]}))

    assert 'the one sample that has a fit' in one_of_three._caption.text()
    assert 'the one sample.' in one_of_one._caption.text()
    assert '1 samples' not in one_of_three._caption.text() + one_of_one._caption.text()


def test_a_degenerate_row_is_starred_as_a_marginal_summary(qapp):
    """Its spread says how one member of a tied family moved, not how well the data fix it."""
    widget = _summary(_sobol_run({'I0': [1.0, 1.0, 1.0]}, degenerate_keys=('I0',)))

    assert _named_row(widget._table, '<b>I<sub>0</sub>')[0].endswith('*')
    assert 'marginal summary' in widget._footnote.text()


def test_with_nothing_to_summarise_the_caption_says_why(qapp):
    from core.pipeline.sensitivity import SensitivityMode

    widget = _summary()
    assert widget._caption.text().startswith('Run a sensitivity analysis')
    assert widget._table.rowCount() == 0

    widget.show_running(SensitivityMode.SOBOL)
    assert widget._caption.text().startswith('The sensitivity analysis is still running.')


def test_a_hidden_run_shows_its_note_and_comes_back(qapp):
    widget = _summary(_sobol_run({'I0': [1.0, 2.0, 3.0]}))
    note = 'This sensitivity analysis was made on replicates A–C. Replicate A is now off.'

    widget.show_mismatch(None, note)
    assert widget._caption.text() == note and widget._table.rowCount() == 0

    widget.show_mismatch(None, None)
    assert widget._table.rowCount() > 0


def test_the_caption_compares_the_run_with_the_fit_at_the_entered_inputs(qapp):
    """The analysis fits at the entered inputs; the Fit results headline let them move, and the caption says so."""
    fit = aware_result()
    baseline = replace(
        fit,
        parameters=fit.conditional.parameters,
        intervals=fit.conditional.intervals,
        input_shifts={},
        conditional=None,
        diagnostics=None,
    )
    run = replace(
        _sobol_run({'Ka_guest': [1e6, 1.2e6, 1.4e6], 'I0': [1.0, 2.0, 3.0]}), assay_type='IDA', baseline_fit=baseline
    )
    widget = _summary(run, fit)
    caption = widget._caption.text()

    assert 'match the fit at the entered inputs in Fit results to the digits shown' in caption
    assert 'lets the inputs move within the uncertainties you stated' in caption
    assert 'although' not in caption


@pytest.mark.parametrize(
    ('reasons', 'why'),
    [
        ({'3': 'ka'}, 'as its own fit needs a different Ka than the other replicates share'),
        ({'3': 'scatter'}, "as its points scatter far more than the other replicates' do"),
    ],
)
def test_a_replicate_both_fits_leave_out_is_explained_by_the_reason_recorded_for_it(reasons, why):
    from gui.plotting.samples_summary import _shared_left_out

    fit = per_replica_result(p_values={'0': 0.5, '1': 0.4, '2': 0.3}, excluded=('3',))
    fit = replace(fit, metadata={**fit.metadata, 'replicate_test': {'level': 0.01, 'reasons': reasons}})

    sentence = _shared_left_out(fit, fit, None)

    assert sentence.startswith('Both leave out') and sentence.endswith(f', {why}.')


def _too_narrow(table):
    """Cells of *table* whose text does not fit: a word wider than the column, or wrapped lines taller than the row."""
    from gui.plotting.samples_summary import _text_widths

    clipped = []
    for col in range(table.columnCount()):
        width = table.columnWidth(col)
        for row in range(table.rowCount()):
            label = table.cellWidget(row, col)
            _, word = _text_widths(label)
            if word > width or label.heightForWidth(width) > table.rowHeight(row):
                clipped.append((table.horizontalHeaderItem(col).text(), row, width))
    return clipped


@pytest.mark.parametrize('width', [220, 560, 1000])
def test_every_value_can_be_read_whole_in_a_narrow_pane(qapp, width):
    """A value cut off mid-number still reads as a number, so a user can copy a wrong one.

    Squeezed, the columns wrap their cells between words and the rows grow, so every
    value stays whole; below the widest word of every column the table scrolls sideways
    to reach the rest.
    """
    from PyQt6.QtCore import Qt

    widget = _summary(_sobol_run({'Ka_guest': [1e6, 1.2e6, 1.4e6], 'I0': [1.0, 2.0, 3.0]}))
    widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    widget.resize(width, 400)
    widget.show()
    for _ in range(4):
        qapp.processEvents()
    table = widget._table

    assert _too_narrow(table) == []
    # The table stays as wide as the pane for as long as its headers and widest words fit:
    # only past that does a sideways scrollbar take over.
    assert _overflow(table) == 0 or all(_at_its_least(table, col) for col in range(table.columnCount()))
    bar = table.horizontalScrollBar()
    bar.setValue(bar.maximum())
    qapp.processEvents()
    last = table.columnCount() - 1
    assert table.columnViewportPosition(last) + table.columnWidth(last) <= table.viewport().width()
    widget.close()


def _overflow(table):
    """How far the columns of *table* reach past its viewport, in pixels; 0 where they fit."""
    return max(0, sum(table.columnWidth(c) for c in range(table.columnCount())) - table.viewport().width())


def _at_its_least(table, col):
    """Whether column *col* is as narrow as its header and its widest word let it be."""
    from gui.plotting.samples_summary import _CELL_PAD_X, _text_widths

    header = table.horizontalHeader().fontMetrics().horizontalAdvance(table.horizontalHeaderItem(col).text()) + 24
    words = (_text_widths(table.cellWidget(row, col))[1] + _CELL_PAD_X for row in range(table.rowCount()))
    return table.columnWidth(col) <= max(header, *words)


def _two_ka_run():
    """A Sobol' run on a 1:2 fit: nine rows, the five signal ones starred with a footnote under the table."""
    from core.pipeline.varpro import KaInterval
    from core.units import Q_

    signal = {'I0': 100.0, 'I_G': 5e4, 'I_H': 1e4, 'I_HG': 8e4, 'I_HG2': 2e4}
    fit = result(
        parameters={
            'Ka_HG': Q_(1.24e6, '1/M'),
            'Ka_HG2': Q_(3.1e4, '1/M'),
            **{key: Q_(value, 'au' if key == 'I0' else 'au/M') for key, value in signal.items()},
        },
        assay_type='DBA_HG2',
        model_name='equilibrium_stepwise',
        intervals={
            'Ka_HG': KaInterval(0.7e6, 2.2e6, False, False, 0.95, 16),
            'Ka_HG2': KaInterval(1.0e4, 9.0e4, False, False, 0.95, 16),
        },
    )
    samples = {'Ka_HG': [1e6, 1.2e6, 1.4e6], 'Ka_HG2': [3e4, 3.1e4, 3.2e4], **{k: [1.0, 2.0, 3.0] for k in signal}}
    run = replace(_sobol_run(samples, degenerate_keys=tuple(signal)), baseline_fit=fit, ka_keys=('Ka_HG', 'Ka_HG2'))
    return run, fit


def _shown_summary(qapp, monkeypatch, run, fit, size):
    """The samples summary of a main window opened at *size* on Sensitivity, showing *run*."""
    from PyQt6.QtCore import Qt

    from gui.main_window import FittingMainWindow

    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    window = FittingMainWindow()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    window.show_view('Sensitivity')
    widget = window.active_session()._summary_widget
    widget.update_result(fit)
    widget.set_sensitivity(run)
    window.resize(*size)
    window.show()
    for _ in range(8):
        qapp.processEvents()
    return window, widget


@pytest.mark.parametrize('size', [(1100, 700), (1600, 1000)], ids=['small', 'large'])
@pytest.mark.parametrize('rows', ['five', 'nine'])
def test_every_row_and_the_whole_footnote_can_be_read_at_the_sizes_the_window_opens_at(qapp, monkeypatch, size, rows):
    """The pane gets part of the window's height, which a nine-row table and its footnote outgrow.

    Nothing may be cut off with no way to reach it: the table shows all of its rows,
    and scrolling the pane to the bottom brings the last of them and the whole footnote
    into view.
    """
    if rows == 'five':
        run, fit = _sobol_run({'Ka_guest': [1e6, 1.2e6, 1.4e6], 'I0': [1.0, 2.0, 3.0]}), result()
    else:
        run, fit = _two_ka_run()
    window, widget = _shown_summary(qapp, monkeypatch, run, fit, size)
    table = widget._table

    needed = table.horizontalHeader().height() + sum(table.rowHeight(r) for r in range(table.rowCount()))
    assert table.rowCount() == (5 if rows == 'five' else 9)
    assert table.viewport().height() >= sum(table.rowHeight(r) for r in range(table.rowCount()))
    assert table.height() >= needed

    bar = widget._page.verticalScrollBar()
    bar.setValue(bar.maximum())
    for _ in range(4):
        qapp.processEvents()
    viewport = widget._page.viewport()
    assert table.mapTo(viewport, table.rect().bottomLeft()).y() <= viewport.height()
    if not widget._footnote.isHidden():
        footnote = widget._footnote
        assert footnote.height() >= footnote.heightForWidth(footnote.width())
        assert footnote.mapTo(viewport, footnote.rect().bottomLeft()).y() <= viewport.height()
    window.close()


def test_the_columns_are_shared_out_again_over_the_width_the_table_ends_up_with(qapp, monkeypatch):
    """Columns measured once against a width the table no longer has leave a scrollbar over a table that fits.

    Widening the window gives the table spare width, which the columns share out between
    them; narrowing it takes that spare back, down to the width their contents need.
    Below that the table scrolls sideways.
    """
    window, widget = _shown_summary(qapp, monkeypatch, *_two_ka_run(), (1600, 1000))
    table = widget._table
    wide = sum(table.columnWidth(c) for c in range(table.columnCount()))
    assert wide <= table.viewport().width()
    assert not table.horizontalScrollBar().isVisible()

    window.resize(1100, 700)
    for _ in range(8):
        qapp.processEvents()
    narrow = sum(table.columnWidth(c) for c in range(table.columnCount()))

    assert narrow < wide  # the spare width went back
    assert _too_narrow(table) == []  # but never below what the cells need
    assert table.horizontalScrollBar().isVisible() == (narrow > table.viewport().width())

    window.resize(1600, 1000)
    for _ in range(8):
        qapp.processEvents()
    assert sum(table.columnWidth(c) for c in range(table.columnCount())) == wide
    assert not table.horizontalScrollBar().isVisible()
    window.close()
