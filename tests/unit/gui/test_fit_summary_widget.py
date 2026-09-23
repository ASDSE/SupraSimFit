"""Widget tests for FitSummaryWidget — requires a QApplication.

Every fixture here is a hand-built :class:`FitResult`, so what the table shows
is checked against numbers written in the test rather than against whatever a
fit happened to produce.
"""

import numpy as np
import pytest

pytest.importorskip('PyQt6')


def _result(**overrides):
    """A GDA fit of one signal: Ka with a closed interval, the signal parameters without one."""
    from core.pipeline.fit_pipeline import FitResult
    from core.pipeline.varpro import KaInterval
    from core.units import Q_

    x = np.linspace(0, 1e-4, 20)
    fields = dict(
        parameters={
            'Ka_guest': Q_(1.24e6, '1/M'),
            'I0': Q_(100.0, 'au'),
            'I_dye_free': Q_(5e4, 'au/M'),
            'I_dye_bound': Q_(8e4, 'au/M'),
        },
        rmse=0.005,
        r_squared=0.998,
        x_fit=Q_(x, 'M'),
        y_fit=Q_(x * 1.05 + 0.01, 'au'),
        assay_type='GDA',
        model_name='equilibrium_4param',
        fit_config={'per_replicate': False, 'level': 0.95},
        intervals={'Ka_guest': KaInterval(0.7e6, 2.2e6, False, False, 0.95, 16)},
    )
    fields.update(overrides)
    return FitResult(**fields)


def _widget(result=None, **overrides):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(_result(**overrides) if result is None else result)
    return widget


def _headers(table):
    return [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]


def _row(table, row):
    return [table.cellWidget(row, c).text() for c in range(table.columnCount())]


def _ka_row(table):
    """The Ka row: the first one whose label is not a log₁₀ twin and names a binding constant."""
    for r in range(table.rowCount()):
        label = table.cellWidget(r, 0).text()
        if 'K<sub>a' in label and not label.startswith('log₁₀'):
            return _row(table, r)
    raise AssertionError('no Ka row in the table')


def _log_row(table):
    for r in range(table.rowCount()):
        if table.cellWidget(r, 0).text().startswith('log₁₀'):
            return _row(table, r)
    raise AssertionError('no log₁₀ row in the table')


# ---------------------------------------------------------------------------
# The interval column
# ---------------------------------------------------------------------------


def test_the_empty_panel_asks_only_for_the_height_of_what_it_shows(qapp):
    """With no fit yet, the rows that only a fit fills are hidden and must not reserve height.

    The panel shares the window's height with the plot tabs above it through a
    splitter, so height reserved for nothing is height the chart loses.
    """
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    reserved = widget._page.widget().layout().itemAt(0).sizeHint().height()

    assert reserved == widget._params_group.sizeHint().height()


def test_the_table_reports_an_estimate_and_its_interval_per_binding_constant(qapp):
    from gui.plotting.fit_summary_widget import _LEVEL_TEXT

    widget = _widget()
    table = widget._table

    assert f'{_LEVEL_TEXT} interval' in _headers(table)
    _, estimate, interval, _ = _ka_row(table)
    assert estimate == '1.24×10⁶'
    # Both endpoints are the interval's own, written like the estimate: three
    # significant figures with their zeros, so 7×10⁵ and 7.0×10⁵ never both appear.
    assert interval == '[7.00×10⁵, 2.20×10⁶]'
    assert 'limit' not in interval


def test_the_log10_row_is_the_ka_row_read_on_a_log_scale(qapp):
    """log₁₀ of a monotone interval is the interval of the log₁₀, endpoint by endpoint."""
    widget = _widget()
    _, estimate, interval, _ = _log_row(widget._table)

    assert float(estimate) == pytest.approx(np.log10(1.24e6), abs=5e-5)
    low, high = (float(v) for v in interval.strip('[]').split(', '))
    assert (low, high) == (pytest.approx(np.log10(0.7e6), abs=5e-5), pytest.approx(np.log10(2.2e6), abs=5e-5))


@pytest.mark.parametrize(
    ('open_low', 'open_high', 'expected'),
    [
        (False, True, 'no upper limit'),
        (True, False, 'no lower limit'),
        (True, True, 'not limited by the data'),
    ],
    ids=['upper-open', 'lower-open', 'both-open'],
)
def test_an_open_side_is_written_in_words_not_as_the_bound_the_search_stopped_at(qapp, open_low, open_high, expected):
    """A side the data do not close has no limit to show; printing the bound would claim one."""
    from core.pipeline.varpro import KaInterval

    widget = _widget(intervals={'Ka_guest': KaInterval(1e-8, 1e12, open_low, open_high, 0.95, 16)})
    interval = _ka_row(widget._table)[2]

    assert expected in interval
    assert ('10¹²' in interval) == (not open_high)
    assert ('10⁻⁸' in interval) == (not open_low)


def test_an_interval_that_spans_rejected_values_is_marked_and_says_why(qapp):
    """A split interval's bracket covers Ka the F test rejects, so read as a plain range it overstates the data.

    The flag reaches the text report and the Identifiability tab; it has to
    reach the two places the headline is actually read as well.
    """
    from core.pipeline.varpro import KaInterval
    from gui.plotting.labels import SPLIT_MARK

    plain = _widget(intervals={'Ka_guest': KaInterval(1e5, 1e7, False, False, 0.95, 16, split=False)})
    widget = _widget(intervals={'Ka_guest': KaInterval(1e5, 1e7, False, False, 0.95, 16, split=True)})
    row = _ka_row(widget._table)

    assert SPLIT_MARK not in _ka_row(plain._table)[2]
    assert SPLIT_MARK in row[2]
    assert row[1] == _ka_row(plain._table)[1]  # only the interval is marked, not the estimate
    assert not widget._footnote.isHidden()
    assert 'separate stretches' in widget._footnote.text()
    assert 'Identifiability' in widget._footnote.text()


def test_an_open_side_no_more_data_could_close_says_so_where_the_bracket_cannot(qapp):
    """'no upper limit' covers a side more points would close and one the model's arithmetic ends at."""
    from core.pipeline.varpro import KaInterval

    closable = _widget(intervals={'Ka_guest': KaInterval(1e5, 1e12, False, True, 0.95, 16)})
    unsolvable = _widget(intervals={'Ka_guest': KaInterval(1e5, 1e12, False, True, 0.95, 16, unsolvable_high=True)})
    column = _headers(unsolvable._table).index('95 % interval')
    row = next(r for r in range(unsolvable._table.rowCount()) if 'K<sub>a' in unsolvable._table.cellWidget(r, 0).text())

    assert closable._table.cellWidget(row, column).toolTip() == ''
    assert 'more measurements cannot close it' in unsolvable._table.cellWidget(row, column).toolTip().lower()


def test_a_binding_constant_held_fixed_says_so_instead_of_an_interval(qapp):
    """A Ka that was not fitted has no interval to report, and 'fixed' is why — not 'unknown'."""
    widget = _widget(intervals={})
    label, _, interval, _ = _ka_row(widget._table)

    assert 'fixed' in interval
    assert widget._caption.text() == ''


def test_a_signal_parameter_carries_no_interval(qapp):
    """Only the binding constants are tested; a signal coefficient's row must not invent one."""
    widget = _widget()
    table = widget._table
    rows = [_row(table, r) for r in range(table.rowCount())]
    signal_rows = [r for r in rows if 'I<sub>' in r[0]]

    assert len(signal_rows) == 3
    assert all(r[2] == '—' for r in signal_rows)


def test_a_file_written_before_intervals_says_so_and_shows_none(qapp):
    """An imported legacy fit keeps its parameters; claiming an interval it never carried would be a fabrication."""
    from gui.plotting.fit_summary_widget import _LEGACY_NOTE

    widget = _widget(intervals=None)

    assert _ka_row(widget._table)[2] == '—'
    assert widget._caption.text() == _LEGACY_NOTE
    assert widget._caption.isVisible() or not widget._caption.isHidden()


def test_a_dye_alone_fit_has_no_binding_constant_and_no_legacy_note(qapp):
    """The note is about a missing interval, and a linear calibration was never going to have one."""
    from core.pipeline.fit_pipeline import FitResult
    from core.units import Q_

    x = np.linspace(0, 1e-4, 5)
    result = FitResult(
        parameters={'slope': Q_(1.5, 'au/M'), 'intercept': Q_(0.2, 'au')},
        rmse=0.01,
        r_squared=0.99,
        x_fit=Q_(x, 'M'),
        y_fit=Q_(x * 1.5, 'au'),
        assay_type='DYE_ALONE',
        model_name='linear',
    )
    widget = _widget(result)

    assert widget._table.rowCount() == 2
    assert widget._caption.text() == ''


def test_an_unknown_assay_type_still_renders_its_parameters(qapp):
    from core.pipeline.fit_pipeline import FitResult
    from core.units import Q_

    x = np.linspace(0, 1e-4, 5)
    result = FitResult(
        parameters={'slope': Q_(1.5, 'au/M')},
        rmse=0.01,
        r_squared=0.99,
        x_fit=Q_(x, 'M'),
        y_fit=Q_(x * 1.5, 'au'),
        assay_type='UNKNOWN_TYPE',
        model_name='linear',
    )
    widget = _widget(result)  # must not raise

    assert widget._table.rowCount() == 1


# ---------------------------------------------------------------------------
# Degenerate rows
# ---------------------------------------------------------------------------


def test_a_fit_that_ended_on_an_entered_bound_says_so_above_the_table(qapp):
    """A curve a bound may be holding away from the data must not look like any other fit."""
    config = {'per_replicate': False, 'level': 0.95, 'custom_bounds': {'I_dye_bound': [0.0, 8e4, 'au/M']}}
    widget = _widget(fit_config=config)

    assert 'ended on a bound entered under Parameter Bounds (' in widget._caption.text()
    assert '8.0×10⁴' in widget._caption.text()
    assert not widget._caption.isHidden()


def test_degenerate_rows_are_starred_and_explained_once(qapp):
    """The value is one member of a family that draws the same curve, and the table has to say so."""
    widget = _widget(degenerate_keys=('I0', 'I_dye_free', 'I_dye_bound'))
    table = widget._table
    starred = [r for r in range(table.rowCount()) if table.cellWidget(r, 0).text().endswith('*')]

    assert len(starred) == 3
    assert not _ka_row(table)[0].endswith('*')
    assert not widget._footnote.isHidden()
    assert 'only a combination' in widget._footnote.text()
    assert table.cellWidget(starred[0], 0).toolTip() == widget._footnote.text().removeprefix('* ')


def test_a_fit_with_nothing_degenerate_shows_no_footnote(qapp):
    widget = _widget()

    assert widget._footnote.isHidden()


# ---------------------------------------------------------------------------
# Replicates: the two columns, the quality row, and the table
# ---------------------------------------------------------------------------


def _per_replica_result(p_values=None, excluded=(), ka_by_replicate=None):
    """A per-replicate GDA fit of four replicates, each with its own fit."""
    from dataclasses import replace

    from core.units import Q_

    ka_by_replicate = ka_by_replicate or {'0': 1.0e6, '1': 1.2e6, '2': 1.4e6, '3': 9.0e6}
    given = ['0', '1', '2', '3']
    used = [rid for rid in given if rid not in excluded]
    base = _result(fit_config={'per_replicate': True, 'level': 0.95})
    replica_fits = [
        replace(
            base,
            parameters={**base.parameters, 'Ka_guest': Q_(ka_by_replicate[rid], '1/M')},
            r_squared=0.99 + 0.001 * i,
            intervals=None,
            metadata={'replica_id': rid, 'active_replica_ids': [rid]},
        )
        for i, rid in enumerate(given)
    ]
    metadata = {'active_replica_ids': given, 'replica_ids_fit': used}
    if excluded:
        metadata['replica_failures'] = {rid: f'Replicate {rid} needs a different Ka.' for rid in excluded}
    if p_values:
        metadata['replicate_test'] = {'level': 0.01, 'p_values': p_values}
    return replace(base, replica_fits=replica_fits, metadata=metadata)


def test_the_replicates_own_fits_are_a_line_under_the_table_not_columns_of_the_headline(qapp):
    """Median and min–max come from the used replicates' own fits — a left-out one describes data the fit does not.

    They are fits at the entered inputs and answer another question than the
    headline, so they sit under the table with one sentence relating them to
    the interval, not in the headline's row.
    """
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.set_replica_ids(['0', '1', '2', '3'])
    widget.update_result(_per_replica_result(excluded=('3',)))

    assert _headers(widget._table) == ['Parameter', 'Estimate', '95 % interval', 'Units']
    # Used replicates hold 1.0, 1.2 and 1.4 ×10⁶ — the excluded 9.0×10⁶ is out.
    footnote = widget._footnote.text()
    assert (
        'Single-replicate fits (inputs as entered): <b>K<sub>a(G)</sub></b> median 1.20×10⁶, '
        'range [1.00×10⁶, 1.40×10⁶] M<sup>−1</sup>.'
    ) in footnote
    assert 'can fall outside it' in footnote


def test_a_replicate_fit_that_ran_to_a_bound_is_counted_and_not_summarised(qapp):
    """A single-replicate Ka on its search bound is the bound, not a value, and must not enter a median."""
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.set_replica_ids(['0', '1', '2', '3'])
    widget.update_result(_per_replica_result(ka_by_replicate={'0': 1.0e6, '1': 1.2e6, '2': 1.4e6, '3': 1e-8}))
    footnote = widget._footnote.text()

    assert 'median 1.20×10⁶, range [1.00×10⁶, 1.40×10⁶]' in footnote
    assert '1 of 4 single-replicate fits of <b>K<sub>a(G)</sub></b> ran to a bound of its search range' in footnote
    assert '10⁻⁸' not in footnote
    # The Replicates table names the bound, not a Ka.
    own = _row(widget._replicates_table, 3)[1]
    assert own == '<i>at the lower end of its search range</i>'


def test_a_fit_of_one_signal_is_not_shown_two_empty_replicate_columns(qapp):
    widget = _widget()

    assert _headers(widget._table) == ['Parameter', 'Estimate', '95 % interval', 'Units']
    assert 'Single-replicate' not in widget._footnote.text()


def test_replicates_used_counts_the_ones_that_entered_and_names_the_rest(qapp):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.set_replica_ids(['0', '1', '2', '3'])
    widget.update_result(_per_replica_result(excluded=('3',)))

    assert widget._replicates_label.text() == '3 of 4'
    tooltip = widget._replicates_label.toolTip()
    assert tooltip.startswith('Left out: D')  # the fourth replicate's panel label
    assert 'needs a different Ka' in tooltip


def test_the_replicates_table_lists_every_replicate_with_its_own_fit_and_verdict(qapp):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.set_replica_ids(['0', '1', '2', '3'])
    widget.update_result(_per_replica_result(p_values={'0': 0.8, '1': 0.6, '2': 0.4, '3': 0.0004}, excluded=('3',)))
    table = widget._replicates_table

    assert not table.isHidden()
    # A header is painted as plain text, so the binding constant is named in plain text.
    assert _headers(table) == ['Replicate', 'Ka(G) [M⁻¹]', 'R²', 'p-value', 'In the fit']
    assert not any('<' in header for header in _headers(table))
    assert [_row(table, r)[0] for r in range(4)] == ['A', 'B', 'C', 'D']
    assert [_row(table, r)[-1] for r in range(4)] == ['used', 'used', 'used', 'left out']
    assert _row(table, 3)[1] == '9.00×10⁶'
    assert _row(table, 3)[3] == '0.0004'
    assert 'needs a different Ka' in table.cellWidget(3, 4).toolTip()


def test_a_fit_of_the_average_shows_no_replicates_table(qapp):
    widget = _widget()

    assert widget._replicates_table.isHidden()
    assert widget._replicates_heading.isHidden()


def test_replicates_too_few_to_test_show_no_p_value_rather_than_a_made_up_one(qapp):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.set_replica_ids(['0', '1', '2', '3'])
    widget.update_result(_per_replica_result())  # no replicate_test recorded
    table = widget._replicates_table

    assert [_row(table, r)[3] for r in range(4)] == ['—', '—', '—', '—']


# ---------------------------------------------------------------------------
# Quality, clearing and hiding
# ---------------------------------------------------------------------------


def test_the_quality_panel_reports_rmse_and_r2(qapp):
    widget = _widget()

    assert widget._rmse_label.text() not in ('', '—')
    assert widget._r2_label.text() == '0.9980'


def _law(**overrides):
    """A noise law read from replicates, with the shape the overrides ask for."""
    from core.pipeline.noise import NoiseBasis, NoiseLaw

    fields = dict(
        basis=NoiseBasis.REPLICATES, share=0.5, floor=890.0, proportional=0.011, reference=1.2e5, n_replicates=8
    )
    fields.update(overrides)
    return NoiseLaw(**fields)


@pytest.mark.parametrize(
    ('law', 'expected'),
    [
        pytest.param(dict(share=0.5), 'about 1.1 % of the signal plus 890 a.u. (scatter of 8 replicates', id='mixed'),
        pytest.param(dict(share=0.0), 'constant, about 890 a.u. (scatter of 8 replicates', id='constant'),
        pytest.param(dict(share=1.0), 'proportional to the signal, about 1.1 % of it (scatter of 8', id='proportional'),
    ],
)
def test_the_quality_panel_says_what_the_replicates_showed_the_noise_to_be(qapp, law, expected):
    """The row is the law in words: the reader has to see which part of it the fit was weighted by."""
    widget = _widget(noise=_law(**law))

    assert widget._noise_label.text().startswith(f'Noise: {expected}')


@pytest.mark.parametrize(
    ('basis', 'expected'),
    [
        ('SINGLE_TITRATION', 'taken as constant — one titration cannot show how the noise varies'),
        ('TOO_FEW_POINTS', 'taken as constant — the replicates scatter at too few titration points'),
    ],
)
def test_one_titration_says_the_noise_was_taken_as_constant_and_why(qapp, basis, expected):
    from core.pipeline.noise import NoiseBasis

    widget = _widget(noise=_law(basis=NoiseBasis[basis], share=0.0, floor=0.0, proportional=0.0, n_replicates=1))

    assert widget._noise_label.text().startswith(f'Noise: {expected}')


def test_the_samples_view_shows_no_noise_row_and_the_fit_view_gets_it_back(qapp):
    """The law is the one fit's, read off the replicates of the data; the samples box reports the samples."""
    widget = _samples_widget(_sobol_run({'I0': [1.0, 2.0, 3.0]}))

    assert widget._noise_label.isHidden()

    widget.show_samples(False)
    assert not widget._noise_label.isHidden()


def test_the_noise_law_spans_the_box_under_the_readings(qapp):
    """A sentence in the narrow value column wraps to seven lines and pushes the readings out of the pane."""
    from PyQt6.QtWidgets import QFormLayout

    widget = _widget(noise=_law())
    form = widget._quality_form

    noise_row, role = form.getWidgetPosition(widget._noise_label)
    readings = [form.getWidgetPosition(label)[0] for label in widget._fit_rows]

    assert role is QFormLayout.ItemRole.SpanningRole
    assert noise_row > max(readings)


def test_a_result_written_before_the_law_existed_says_so_rather_than_guessing(qapp):
    """An imported file with no noise key: the row states that this result does not record one."""
    widget = _widget(noise=None)

    assert widget._noise_label.text() == 'Noise: not recorded in this result'
    assert not widget._noise_label.isHidden()


def _dye_alone_result():
    """A dye-alone calibration: a line, fitted by ``fit_linear_assay``, which estimates no noise law."""
    from core.assays.registry import AssayType
    from core.pipeline.fit_pipeline import FitResult
    from core.units import Q_

    x = np.linspace(0, 1e-4, 5)
    return FitResult(
        parameters={'slope': Q_(1.5, 'au/M'), 'intercept': Q_(0.2, 'au')},
        rmse=0.01,
        r_squared=0.99,
        x_fit=Q_(x, 'M'),
        y_fit=Q_(x * 1.5, 'au'),
        assay_type=AssayType.DYE_ALONE.name,
        model_name='linear',
    )


def test_a_dye_alone_calibration_shows_no_noise_row(qapp):
    """A calibration line is fitted with no noise law and needs none, so the row is not on screen."""
    widget = _widget(_dye_alone_result())

    assert widget._noise_label.isHidden()


def test_the_noise_row_comes_back_for_the_next_fit_of_a_binding_assay(qapp):
    """The row is hidden by the result on screen, not for good."""
    widget = _widget(_dye_alone_result())
    widget.update_result(_result(noise=_law()))

    assert not widget._noise_label.isHidden()
    assert '890 a.u.' in widget._noise_label.text()


def test_the_fit_quality_help_explains_the_noise_row(qapp):
    """Whatever the row says, the info button has to say where the law comes from and what it does."""
    from gui.plotting.fit_summary_widget import _FIT_QUALITY_HELP_HTML

    text = ' '.join(_FIT_QUALITY_HELP_HTML.split())

    assert '<b>Noise</b>' in text
    assert 'replicates' in text
    assert 'One titration cannot show how the noise varies' in text


def test_clear_resets_state(qapp):
    widget = _widget()
    widget.clear()

    assert widget._table.rowCount() == 0
    assert widget._rmse_label.text() == '—'
    assert widget._r2_label.text() == '—'
    assert widget._noise_label.text() == 'Noise: —'
    assert widget._replicates_label.text() == '—'
    assert widget._replicates_table.isHidden()


def test_a_hidden_fit_shows_its_note_instead_of_numbers_and_comes_back(qapp):
    widget = _widget()
    shown = _ka_row(widget._table)

    note = 'This fit was made on replicates B–D. Replicate B is now off.'
    widget.show_mismatch(note)
    assert widget._table.rowCount() == 0
    assert widget._caption.text() == note

    widget.show_mismatch(None)
    assert _ka_row(widget._table) == shown


def _shown_tables(qapp, widget, size):
    """*widget* laid out at *size* without a window on screen, and the tables it is showing."""
    from PyQt6.QtCore import Qt

    widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    widget.resize(*size)
    widget.show()
    for _ in range(4):
        qapp.processEvents()
    return [table for table in (widget._table, widget._replicates_table) if not table.isHidden()]


def _too_narrow(table):
    """Cells of *table* whose text does not fit: a word wider than the column, or wrapped lines taller than the row."""
    from gui.plotting.fit_summary_widget import _text_widths

    clipped = []
    for col in range(table.columnCount()):
        width = table.columnWidth(col)
        for row in range(table.rowCount()):
            label = table.cellWidget(row, col)
            _, word = _text_widths(label)
            if word > width or label.heightForWidth(width) > table.rowHeight(row):
                clipped.append((table.horizontalHeaderItem(col).text(), row, width))
    return clipped


def _overflow(table):
    """How far the columns of *table* reach past its viewport, in pixels; 0 where they fit."""
    return max(0, sum(table.columnWidth(c) for c in range(table.columnCount())) - table.viewport().width())


def _at_its_least(table, col):
    """Whether column *col* is as narrow as its header and its widest word let it be."""
    from gui.plotting.fit_summary_widget import _text_widths

    header = table.horizontalHeader().fontMetrics().horizontalAdvance(table.horizontalHeaderItem(col).text()) + 24
    words = (_text_widths(table.cellWidget(row, col))[1] + 16 for row in range(table.rowCount()))
    return table.columnWidth(col) <= max(header, *words)


@pytest.mark.parametrize('view', ['one-ka', 'two-ka', 'samples', 'inputs-free'])
@pytest.mark.parametrize('width', [560, 760, 1000])
def test_every_value_can_be_read_whole_in_a_narrow_pane(qapp, view, width):
    """A value cut off mid-number still reads as a number, so a user can copy a wrong one.

    Squeezed, the columns wrap their cells between words and the rows grow, so
    every value stays whole, and the table stays as wide as the pane for as
    long as its headers and its widest words fit: only past that does a
    sideways scrollbar take over.
    """
    if view == 'samples':
        widget = _samples_widget(_sobol_run({'Ka_guest': [1e6, 1.2e6, 1.4e6], 'I0': [1.0, 2.0, 3.0]}))
    elif view == 'inputs-free':
        widget = _aware_widget()
    else:
        widget = _widget() if view == 'one-ka' else _widget(_two_ka_per_replica_result())
        widget.set_replica_ids(['0', '1', '2', '3'])

    for table in _shown_tables(qapp, widget, (width, 400)):
        assert _too_narrow(table) == []
        assert _overflow(table) == 0 or all(_at_its_least(table, col) for col in range(table.columnCount()))
    widget.close()


def test_a_pane_narrower_than_the_widest_words_scrolls_to_them(qapp):
    """Below the widest word of every column the table cannot wrap further, and the scrollbar reaches the rest."""
    widget = _aware_widget()
    for table in _shown_tables(qapp, widget, (220, 400)):
        assert _too_narrow(table) == []
        bar = table.horizontalScrollBar()
        bar.setValue(bar.maximum())
        qapp.processEvents()
        last = table.columnCount() - 1
        assert table.columnViewportPosition(last) + table.columnWidth(last) <= table.viewport().width()
    widget.close()


def test_a_log10_row_is_never_written_coarser_than_the_replicate_spread(qapp):
    """8.9974 must not read as '9': the log₁₀ row's decimals follow the spread of the replicates' own fits."""
    from core.units import Q_
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    ka = {rid: float(10**v) for rid, v in zip('0123', (8.9940, 8.9974, 9.0008, 8.9960))}
    result = _per_replica_result(ka_by_replicate=ka)
    result.parameters['Ka_guest'] = Q_(10**8.9974, '1/M')

    widget = FitSummaryWidget()
    widget.set_replica_ids(['0', '1', '2', '3'])
    widget.update_result(result)
    _, estimate, _, _ = _log_row(widget._table)

    assert estimate == '8.9974'


# ---------------------------------------------------------------------------
# The samples view of a sensitivity run
# ---------------------------------------------------------------------------


def _sobol_run(samples, *, sample_r2=None, degenerate_keys=()):
    """A finished Sobol' run whose baseline is :func:`_result` and whose samples are *samples*."""
    from core.pipeline.sensitivity import InputSpec, SensitivityConfig, SensitivityMode, SensitivityResult

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
        baseline_fit=_result(),
        sample_params={key: np.asarray(v, dtype=float) for key, v in samples.items()},
        degenerate_keys=degenerate_keys,
    )


def _samples_widget(run):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(_result())
    widget.set_sensitivity(run)
    widget.show_samples(True)
    return widget


def _named_row(table, label_html):
    for r in range(table.rowCount()):
        if table.cellWidget(r, 0).text().startswith(label_html):
            return _row(table, r)
    raise AssertionError(f'no row labelled {label_html}')


def test_the_samples_view_summarises_the_fitted_samples_around_the_run_s_own_fit(qapp):
    """Each column is the stated statistic of the samples — hand-computed here, not read back from the widget."""
    from gui.plotting.fit_summary_widget import _SAMPLE_HEADERS

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
    widget = _samples_widget(run)

    assert _headers(widget._table) == list(_SAMPLE_HEADERS)
    _, estimate, median_mad, _, p68, span, _ = _named_row(widget._table, '<b>I<sub>0</sub>')
    assert estimate == '100'  # the run's own fit, not a statistic of the samples
    assert median_mad == '2.00 ± 1.00'
    assert p68 == '[1.32, 2.68]'
    assert span == '[1.00, 3.00]'


def test_the_samples_view_reports_how_many_samples_it_summarises(qapp):
    """A sample with no fit is left out of the statistics and counted, never quietly folded in."""
    run = _sobol_run({'I0': [1.0, 2.0, 3.0, np.nan]}, sample_r2=[0.99, 0.98, 0.97, np.nan])
    widget = _samples_widget(run)

    assert widget._fitted_label.text() == '3 / 4'
    assert widget._r2_range_label.text() == '[0.9700, 0.9900]'
    assert 'could not be fitted' in widget._caption.text()


def test_the_samples_caption_counts_a_single_sample_as_one_sample(qapp):
    """A count reads as a sentence, not as a slot: one sample is 'the one sample', never 'the 1 samples'."""
    one_of_three = _samples_widget(_sobol_run({'I0': [1.0, np.nan, np.nan]}))
    one_of_one = _samples_widget(_sobol_run({'I0': [1.0]}))

    assert 'the one sample that has a fit' in one_of_three._caption.text()
    assert 'the one sample.' in one_of_one._caption.text()
    assert '1 samples' not in one_of_three._caption.text() + one_of_one._caption.text()


def test_a_degenerate_row_of_the_samples_view_is_starred_as_a_marginal_summary(qapp):
    """Its spread says how one member of a tied family moved, not how well the data fix it."""
    run = _sobol_run({'I0': [1.0, 1.0, 1.0]}, degenerate_keys=('I0',))
    widget = _samples_widget(run)

    assert _named_row(widget._table, '<b>I<sub>0</sub>')[0].endswith('*')
    assert 'marginal summary' in widget._footnote.text()


def test_the_fit_view_says_why_it_is_showing_when_the_samples_view_has_nothing(qapp):
    """Switching to Ka Sensitivity with no run must explain itself rather than show the fit table unannounced."""
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.show_samples(True)

    assert widget._caption.text().startswith('Run a sensitivity analysis')
    assert widget._caption.isVisibleTo(widget)


# ---------------------------------------------------------------------------
# The pane's own size: what the splitter leaves it, and what it does with that
# ---------------------------------------------------------------------------


def _two_ka_per_replica_result():
    """A 1:2 fit of four replicates: nine reported rows, five of them starred, and a Replicates table."""
    from dataclasses import replace

    from core.pipeline.varpro import KaInterval
    from core.units import Q_

    signal = {'I0': 100.0, 'I_G': 5e4, 'I_H': 1e4, 'I_HG': 8e4, 'I_HG2': 2e4}
    base = _result(
        parameters={
            'Ka_HG': Q_(1.24e6, '1/M'),
            'Ka_HG2': Q_(3.1e4, '1/M'),
            **{key: Q_(value, 'au' if key == 'I0' else 'au/M') for key, value in signal.items()},
        },
        assay_type='DBA_HG2',
        model_name='stepwise_hg2',
        fit_config={'per_replicate': True, 'level': 0.95},
        intervals={
            'Ka_HG': KaInterval(0.7e6, 2.2e6, False, False, 0.95, 16),
            'Ka_HG2': KaInterval(1.0e4, 9.0e4, False, False, 0.95, 16),
        },
        degenerate_keys=tuple(signal),
    )
    given = ['0', '1', '2', '3']
    fits = [replace(base, intervals=None, metadata={'replica_id': rid, 'active_replica_ids': [rid]}) for rid in given]
    return replace(base, replica_fits=fits, metadata={'active_replica_ids': given, 'replica_ids_fit': given})


def _shown_summary(qapp, monkeypatch, result, size):
    """The summary pane of a main window opened at *size*, showing *result*."""
    from PyQt6.QtCore import Qt

    from gui.main_window import FittingMainWindow

    monkeypatch.setattr(FittingMainWindow, '_run_update_check', lambda self, silent: None)
    window = FittingMainWindow()
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    session = window.active_session()
    widget = session._summary_widget
    widget.set_replica_ids(['0', '1', '2', '3'])
    widget.update_result(result)
    window.resize(*size)
    window.show()
    for _ in range(8):
        qapp.processEvents()
    return window, widget


@pytest.mark.parametrize('size', [(1100, 700), (1600, 1000)], ids=['small', 'large'])
@pytest.mark.parametrize('rows', ['five', 'nine'])
def test_every_row_and_the_whole_footnote_can_be_read_at_the_sizes_the_window_opens_at(qapp, monkeypatch, size, rows):
    """The pane gets about a third of the window's height, which a nine-row table and its footnote outgrow.

    Nothing may be cut off with no way to reach it: the table shows all of its
    rows, and scrolling the pane to the bottom brings the last of them and the
    whole footnote into view.
    """
    result = _result() if rows == 'five' else _two_ka_per_replica_result()
    window, widget = _shown_summary(qapp, monkeypatch, result, size)
    table = widget._table

    # No row is hidden inside the table itself.
    needed = table.horizontalHeader().height() + sum(table.rowHeight(r) for r in range(table.rowCount()))
    assert table.rowCount() == (5 if rows == 'five' else 9)
    assert table.viewport().height() >= sum(table.rowHeight(r) for r in range(table.rowCount()))
    assert table.height() >= needed

    bar = widget._page.verticalScrollBar()
    bar.setValue(bar.maximum())
    for _ in range(4):
        qapp.processEvents()
    viewport = widget._page.viewport()
    last = widget._replicates_table if not widget._replicates_table.isHidden() else table
    assert last.mapTo(viewport, last.rect().bottomLeft()).y() <= viewport.height()
    if not widget._footnote.isHidden():
        footnote = widget._footnote
        assert footnote.height() >= footnote.heightForWidth(footnote.width())
        assert footnote.mapTo(viewport, footnote.rect().bottomLeft()).y() <= viewport.height()
    window.close()


def test_the_columns_are_shared_out_again_over_the_width_the_table_ends_up_with(qapp, monkeypatch):
    """Columns measured once against a width the table no longer has leave a scrollbar over a table that fits.

    Widening the window gives the table spare width, which the columns share out
    between them; narrowing it takes that spare back, down to the width their
    contents need. Below that the table scrolls sideways.
    """
    window, widget = _shown_summary(qapp, monkeypatch, _two_ka_per_replica_result(), (1600, 1000))
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
    # The scrollbar is there when the columns need it and gone when they do not,
    # rather than staying on over a row once it has been shown.
    assert table.horizontalScrollBar().isVisible() == (narrow > table.viewport().width())

    window.resize(1600, 1000)
    for _ in range(8):
        qapp.processEvents()
    assert sum(table.columnWidth(c) for c in range(table.columnCount())) == wide
    assert not table.horizontalScrollBar().isVisible()
    window.close()


# ---------------------------------------------------------------------------
# Inputs that were free to move: the conditional column and the Model and
# inputs block
# ---------------------------------------------------------------------------


#: What the block calls the inputs of an IDA fit, which is what
#: :func:`~gui.widgets.assay_conditions.result_input_labels` derives from the
#: assay the fit records.
_INPUT_LABELS = {'h0': '[Host]₀', 'd0': '[Dye]₀', '__titrant__': 'Guest (titrant, whole series)'}

#: Stands for "leave this at the fixture's default", so a test can ask for None.
_DEFAULT = object()


def _aware_result(*, shifts=None, diagnostics=_DEFAULT, uncertainty=None, conditional=True, **overrides):
    """A GDA fit whose entered inputs were free to move, with its conditional fit beside it."""
    from core.pipeline.diagnostics import FitDiagnostics, InputShift, MisfitTest, Verdict
    from core.pipeline.fit_pipeline import ConditionalFit
    from core.pipeline.varpro import KaInterval
    from core.units import Q_

    shifts = {'h0': InputShift('h0', -0.041, -1.4, False)} if shifts is None else shifts
    if diagnostics is _DEFAULT:
        diagnostics = FitDiagnostics(
            conditional_misfit=MisfitTest('lack_of_fit', 0.9, 0.55, dof=(9, 72)),
            misfit=MisfitTest('lack_of_fit', 0.8, 0.62, dof=(9, 72)),
            conflict=None,
            verdict=Verdict.CONSISTENT,
        )
    base = _result(
        # h0, d0 and Ka_dye are the inputs of an IDA fit, and the block names
        # them from the assay the result records.
        assay_type='IDA',
        # The headline: the fit with the inputs free to move, and its wider interval.
        parameters={
            'Ka_guest': Q_(1.30e6, '1/M'),
            'I0': Q_(100.0, 'au'),
            'I_dye_free': Q_(5e4, 'au/M'),
            'I_dye_bound': Q_(8e4, 'au/M'),
        },
        intervals={'Ka_guest': KaInterval(0.5e6, 3.0e6, False, False, 0.95, 16)},
        fit_config={
            'per_replicate': False,
            'level': 0.95,
            'input_uncertainty': {'h0': {'kind': 'sigma', 'sigma': 3.0, 'lo': 0.0, 'hi': 0.0, 'relative': True}}
            if uncertainty is None
            else uncertainty,
        },
        conditions={'h0': Q_(4.3e-6, 'M'), 'd0': Q_(6e-6, 'M'), 'Ka_dye': Q_(1.68e7, '1/M')},
        input_shifts=shifts,
        diagnostics=diagnostics,
        **overrides,
    )
    if not conditional:
        return base
    from dataclasses import replace

    return replace(
        base,
        conditional=ConditionalFit(
            parameters={**base.parameters, 'Ka_guest': Q_(1.24e6, '1/M')},
            intervals={'Ka_guest': KaInterval(0.7e6, 2.2e6, False, False, 0.95, 16)},
            rmse=0.006,
            r_squared=0.997,
        ),
    )


def _aware_widget(result=None):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(_aware_result() if result is None else result)
    return widget


def _block(widget):
    return widget._diagnostics_label.text()


def test_the_conditional_column_shows_the_fit_with_the_inputs_taken_as_entered(qapp):
    """The headline moved the inputs; the column beside it is what the data say with them held where entered."""
    from gui.plotting.fit_summary_widget import _CONDITIONAL_HEADER

    widget = _aware_widget()
    table = widget._table
    column = _headers(table).index(_CONDITIONAL_HEADER)
    row = _ka_row(table)

    assert row[1] == '1.30×10⁶'  # the headline estimate, with the inputs free
    assert row[column] == '1.24×10⁶ [7.00×10⁵, 2.20×10⁶]'  # the conditional one
    # The headline interval is the one the column of intervals carries.
    assert row[2] == '[5.00×10⁵, 3.00×10⁶]'


def test_a_split_conditional_interval_is_marked_like_any_other(qapp):
    """The bracket in that column spans rejected values just as the headline one can, and reads as a range unmarked."""
    from dataclasses import replace

    from gui.plotting.fit_summary_widget import _CONDITIONAL_HEADER
    from gui.plotting.labels import SPLIT_MARK

    base = _aware_result()
    split = replace(base.conditional.intervals['Ka_guest'], split=True)
    result = replace(base, conditional=replace(base.conditional, intervals={'Ka_guest': split}))
    widget = _aware_widget(result)
    column = _headers(widget._table).index(_CONDITIONAL_HEADER)

    assert SPLIT_MARK in _ka_row(widget._table)[column]
    assert SPLIT_MARK not in _ka_row(widget._table)[2]  # the headline interval is not split
    assert 'separate stretches' in widget._footnote.text()


def test_the_log10_twin_carries_the_conditional_numbers_on_a_log_scale(qapp):
    from gui.plotting.fit_summary_widget import _CONDITIONAL_HEADER

    widget = _aware_widget()
    column = _headers(widget._table).index(_CONDITIONAL_HEADER)
    text = _log_row(widget._table)[column]
    estimate, interval = text.split(' [')
    low, high = (float(v) for v in interval.rstrip(']').split(', '))

    assert float(estimate) == pytest.approx(np.log10(1.24e6), abs=5e-5)
    assert (low, high) == (pytest.approx(np.log10(0.7e6), abs=5e-5), pytest.approx(np.log10(2.2e6), abs=5e-5))


def test_a_fit_with_every_input_as_entered_is_not_shown_a_column_repeating_its_own_numbers(qapp):
    from gui.plotting.fit_summary_widget import _CONDITIONAL_HEADER

    widget = _widget()

    assert _CONDITIONAL_HEADER not in _headers(widget._table)


def test_the_block_says_what_the_diagnostics_say_and_which_uncertainties_were_used(qapp):
    from gui.plotting.labels import verdict_sentence

    widget = _aware_widget()
    text = _block(widget)
    result = widget._fit

    assert verdict_sentence(result.diagnostics, result.input_shifts, _INPUT_LABELS, html=True) in text
    # Both misfit tests are quoted: the fit as entered, and the fit that moved.
    assert 'F(9, 72) = 0.9' in text and 'F(9, 72) = 0.8' in text
    assert '[Host]₀ −4.1 % (1.4 σ)' in text
    assert 'Input uncertainties used' in text and '[Host]₀ σ 3 %' in text
    assert not widget._diagnostics_label.isHidden()


def test_the_block_names_a_shared_source_with_the_inputs_it_moves(qapp):
    """A shift of a source several inputs share is read against the source, so the block has to name it as one."""
    from core.pipeline.diagnostics import InputShift
    from core.pipeline.inputs import ErrorModel, SharedSource, shared_key

    key = shared_key('Host and dye stock')
    errors = ErrorModel(shared=(SharedSource('Host and dye stock', 4.0, ('h0', 'd0')),))
    result = _aware_result(shifts={key: InputShift(key, -0.041, -1.02, False)}, uncertainty={})
    result.fit_config.update(errors.to_dict())
    text = _block(_aware_widget(result))

    assert 'Host and dye stock (shared by [Host]₀, [Dye]₀) −4.1 % (1.0 σ)' in text
    assert 'Input uncertainties used: Host and dye stock (shared by [Host]₀, [Dye]₀) σ 4 %.' in text


def test_the_block_says_that_the_titrant_diluted_the_sample(qapp):
    """The totals the fit used fall with each addition, which is part of the model behind the numbers above."""
    from core.units import Q_

    result = _aware_result()
    result.conditions.update({'titrant_stock': Q_(1.0e-3, 'M'), 'stock_contains': ('d0',)})
    text = _block(_aware_widget(result))

    # In the unit the stock was entered in, not in raw molar.
    assert 'a stock of 1 mM' in text and 'every fixed concentration falls with each addition' in text
    assert 'except [Dye]₀' in text


def test_the_block_of_a_fit_with_constant_totals_says_nothing_about_dilution(qapp):
    assert 'each addition' not in _block(_aware_widget())


def test_a_fit_that_took_every_input_as_entered_says_the_interval_takes_them_as_exact(qapp):
    """The block is the record of what the interval covers, so 'nothing stated' has to be stated."""
    widget = _aware_widget(_aware_result(shifts={}, uncertainty={}, conditional=False))
    text = _block(widget)

    assert 'none — the interval takes the inputs as exact' in text
    assert 'Shifts' not in text


def test_an_input_stated_as_a_range_reports_the_end_it_rests_on_and_no_sigma(qapp):
    from core.pipeline.diagnostics import InputShift

    widget = _aware_widget(
        _aware_result(
            shifts={'d0': InputShift('d0', -0.06, None, True)},
            uncertainty={'d0': {'kind': 'interval', 'sigma': 0.0, 'lo': -6.0, 'hi': 10.0, 'relative': True}},
        )
    )
    text = _block(widget)

    assert '[Dye]₀ −6.0 % (at the edge of its range)' in text
    assert 'σ)' not in text
    assert '[Dye]₀ −6 % to +10 %' in text
    # There is no statistic for a range, and the block says why rather than
    # leaving the reader to infer that nothing was tested.
    assert 'there is nothing to test a shift against' in text
    assert 'q =' not in text


def test_an_absolute_uncertainty_is_reported_in_the_input_s_own_unit(qapp):
    widget = _aware_widget(
        _aware_result(uncertainty={'h0': {'kind': 'sigma', 'sigma': 2e-7, 'lo': 0.0, 'hi': 0.0, 'relative': False}})
    )

    assert '[Host]₀ σ 2.0×10⁻⁷ M' in _block(widget)


def test_a_conflict_is_reported_as_one_statement_about_the_inputs_together(qapp):
    from core.pipeline.diagnostics import Conflict, FitDiagnostics, InputShift, MisfitTest, Verdict

    diagnostics = FitDiagnostics(
        conditional_misfit=MisfitTest('lack_of_fit', 200.0, 1e-9, dof=(9, 72)),
        misfit=MisfitTest('lack_of_fit', 1.1, 0.4, dof=(9, 72)),
        conflict=Conflict(q=24.2, k=2, p_value=1e-5, weights=(0.3, 0.9)),
        verdict=Verdict.INPUTS_CONFLICT,
    )
    shifts = {
        'h0': InputShift('h0', -0.114, -3.8, False),
        '__titrant__': InputShift('__titrant__', 0.093, 3.1, False),
    }
    widget = _aware_widget(_aware_result(shifts=shifts, diagnostics=diagnostics))
    text = _block(widget)

    assert 'q = 24.2' in text
    assert '2 directions' in text
    # Largest |z| first, and the culprit left open: the statistic judges them together.
    assert text.index('[Host]₀ −11.4') < text.index('Guest (titrant, whole series) +9.3')
    # The data inform one direction per stated input here, so the block says only
    # that the statistic weighs them as one — it does not claim they are alike.
    assert 'does not say which of them is off' in text
    assert 'almost alike' not in text


def test_sigma_inputs_the_data_cannot_check_are_said_to_be_unchecked(qapp):
    """With no direction the data inform there is no conflict statistic, and no verdict on the inputs."""
    from core.pipeline.diagnostics import FitDiagnostics, InputShift, MisfitTest, Verdict

    diagnostics = FitDiagnostics(
        conditional_misfit=MisfitTest('runs', 6.0, 0.41, expected=7.0),
        misfit=MisfitTest('runs', 6.0, 0.41, expected=7.0),
        conflict=None,
        verdict=Verdict.CONSISTENT,
    )
    widget = _aware_widget(_aware_result(shifts={'h0': InputShift('h0', -0.041, -1.4, False)}, diagnostics=diagnostics))
    text = _block(widget)

    assert 'cannot check' in text
    assert 'q =' not in text


def test_an_imported_result_without_diagnostics_shows_no_block_rather_than_an_empty_one(qapp):
    widget = _aware_widget(_aware_result(shifts={}, diagnostics=None, conditional=False, uncertainty={}))

    assert widget._diagnostics_label.isHidden()
    assert widget._diagnostics_heading.isHidden()


def test_the_samples_view_shows_no_model_and_inputs_block(qapp):
    """The block tests one fit against the data; the samples table summarises many fits of moved inputs."""
    widget = _aware_widget()
    widget.set_sensitivity(_sobol_run({'Ka_guest': [1.1e6, 1.2e6, 1.3e6]}))
    widget.show_samples(True)

    assert widget._diagnostics_label.isHidden()

    widget.show_samples(False)
    assert not widget._diagnostics_label.isHidden()


# ---------------------------------------------------------------------------
# An estimate on its search bound, the verdict line, the samples caption and
# the table at the size the window opens at on a laptop
# ---------------------------------------------------------------------------


def _weak_result(**overrides):
    """A DBA fit whose Ka ran onto the lower bound of its search box, the registry's 1e-8 M⁻¹.

    The data limit Ka only from above, at 2.41×10³ M⁻¹: the interval is open
    below and closed above.
    """
    from core.pipeline.varpro import KaInterval
    from core.units import Q_

    return _result(
        assay_type='DBA_HtoD',
        parameters={
            'Ka_dye': Q_(1e-8, '1/M'),
            'I0': Q_(100.0, 'au'),
            'I_dye_free': Q_(5e4, 'au/M'),
            'I_dye_bound': Q_(2.37e19, 'au/M'),
        },
        intervals={'Ka_dye': KaInterval(1e-8, 2413.6, True, False, 0.95, 16)},
        **overrides,
    )


def test_an_estimate_on_its_search_bound_is_written_as_the_limit_the_data_set(qapp):
    """The value the search stopped at is the bound of the box, not a measurement, so no number stands for it."""
    widget = _widget(_weak_result())
    ka = _ka_row(widget._table)
    log = _log_row(widget._table)

    assert ka[1] == '<i>not limited below</i> 2.41×10³'
    assert log[1] == f'<i>not limited below</i> {np.log10(2413.6):.4f}'
    assert all('10⁻⁸' not in cell and '-8.0' not in cell for cell in ka + log)


def test_a_conditional_estimate_on_its_search_bound_is_written_in_words_too(qapp):
    from dataclasses import replace

    from core.pipeline.varpro import KaInterval
    from core.units import Q_
    from gui.plotting.fit_summary_widget import _CONDITIONAL_HEADER

    base = _aware_result()
    conditional = replace(
        base.conditional,
        parameters={**base.conditional.parameters, 'Ka_guest': Q_(1e-8, '1/M')},
        intervals={'Ka_guest': KaInterval(1e-8, 2.2e6, True, False, 0.95, 16)},
    )
    widget = _aware_widget(replace(base, conditional=conditional))
    cell = _ka_row(widget._table)[_headers(widget._table).index(_CONDITIONAL_HEADER)]

    assert cell == '<i>not limited below</i> 2.20×10⁶ [<i>no lower limit</i>, 2.20×10⁶]'


@pytest.mark.parametrize(
    ('verdict', 'tone'),
    [('consistent', 'neutral'), ('inputs_explain', 'amber'), ('model_inadequate', 'red')],
)
def test_the_verdict_leads_the_box_above_the_table_in_the_colour_of_what_it_asks(qapp, verdict, tone):
    """Whether the result can be taken as it stands is read before the numbers, not below the fold."""
    from PyQt6.QtCore import Qt

    from core.pipeline.diagnostics import FitDiagnostics, MisfitTest, Verdict
    from gui.plotting.labels import VERDICT_TONES, verdict_headline

    diagnostics = FitDiagnostics(
        conditional_misfit=MisfitTest('lack_of_fit', 300.0, 1e-9, dof=(9, 72)),
        misfit=MisfitTest('lack_of_fit', 0.9, 0.5, dof=(9, 72)),
        conflict=None,
        verdict=Verdict(verdict),
    )
    widget = _aware_widget(_aware_result(diagnostics=diagnostics))
    widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    widget.resize(900, 400)
    widget.show()
    qapp.processEvents()

    assert widget._verdict.text() == verdict_headline(diagnostics)[0]
    assert widget._verdict.property('tone') == tone
    assert VERDICT_TONES[tone][0] in widget._verdict.styleSheet()
    assert widget._verdict.geometry().bottom() < widget._table.geometry().top()
    widget.close()


def test_a_result_without_diagnostics_shows_no_verdict_line(qapp):
    widget = _widget()

    assert widget._verdict.isHidden()


def test_the_samples_caption_compares_the_run_with_the_fit_at_the_entered_inputs(qapp):
    """The analysis fits at the entered inputs; the Fit Curve headline let them move, and the caption says so.

    It never claims the two differ although they use the same data and inputs:
    the headline differs because it moved the inputs.
    """
    from dataclasses import replace

    fit = _aware_result()
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
    widget = _samples_widget(run)
    widget.update_result(fit)
    caption = widget._caption.text()

    assert 'match the fit at the entered inputs on the Fit Curve tab to the digits shown' in caption
    assert 'lets the inputs move within the uncertainties you stated' in caption
    assert 'although' not in caption


@pytest.mark.parametrize('which', ['inputs-free', 'per-replicate'])
def test_the_table_fits_the_pane_of_a_laptop_window(qapp, monkeypatch, which):
    """At 1440×900 the table is as wide as the pane and every value reads whole, with no sideways scrolling."""
    result = _aware_result() if which == 'inputs-free' else _two_ka_per_replica_result()
    window, widget = _shown_summary(qapp, monkeypatch, result, (1440, 900))
    table = widget._table

    assert _overflow(table) == 0
    assert _too_narrow(table) == []
    assert not table.horizontalScrollBar().isVisible()
    window.close()


@pytest.mark.parametrize(
    ('reasons', 'why'),
    [
        ({'3': 'ka'}, 'as its own fit needs a different Ka than the other replicates share'),
        ({'3': 'scatter'}, "as its points scatter far more than the other replicates' do"),
    ],
)
def test_a_replicate_both_fits_leave_out_is_explained_by_the_reason_recorded_for_it(reasons, why):
    """The sentence under the samples table gives the ground the replicate test left the replicate out on."""
    from dataclasses import replace

    from gui.plotting.fit_summary_widget import _shared_left_out

    result = _per_replica_result(p_values={'0': 0.5, '1': 0.4, '2': 0.3}, excluded=('3',))
    result = replace(result, metadata={**result.metadata, 'replicate_test': {'level': 0.01, 'reasons': reasons}})

    sentence = _shared_left_out(result, result, None)

    assert sentence.startswith('Both leave out') and sentence.endswith(f', {why}.')
