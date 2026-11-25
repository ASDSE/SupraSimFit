"""Widget tests for FitSummaryWidget — requires a QApplication."""

import numpy as np
import pytest

pytest.importorskip('PyQt6')


@pytest.fixture
def minimal_fit_result():
    from core.pipeline.fit_pipeline import FitResult

    x = np.linspace(0, 1e-4, 20)
    return FitResult(
        parameters={'Ka_guest': 1e6, 'I0': 100.0, 'I_dye_free': 5e4, 'I_dye_bound': 8e4},
        rmse=0.005,
        r_squared=0.998,
        n_passing=87,
        n_total=100,
        x_fit=x,
        y_fit=x * 1.05 + 0.01,
        assay_type='GDA',
        model_name='equilibrium_4param',
    )


def test_update_result_metric_labels_nonempty(qapp, minimal_fit_result):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(minimal_fit_result)

    assert widget._rmse_label.text() not in ('', '—')
    assert widget._r2_label.text() not in ('', '—')
    assert widget._passing_label.text() not in ('', '—')


def test_clear_resets_state(qapp, minimal_fit_result):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(minimal_fit_result)
    widget.clear()

    assert widget._table.rowCount() == 0
    assert widget._rmse_label.text() == '—'
    assert widget._r2_label.text() == '—'
    assert widget._passing_label.text() == '—'


def test_unknown_assay_type_does_not_crash(qapp):
    from core.pipeline.fit_pipeline import FitResult
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    x = np.linspace(0, 1e-4, 5)
    result = FitResult(
        parameters={'slope': 1.5},
        rmse=0.01,
        r_squared=0.99,
        n_passing=1,
        n_total=1,
        x_fit=x,
        y_fit=x * 1.5,
        assay_type='UNKNOWN_TYPE',
        model_name='linear',
    )
    widget = FitSummaryWidget()
    widget.update_result(result)  # must not raise

    assert widget._table.rowCount() == 1


@pytest.fixture
def full_fit_result():
    """A FitResult carrying the ensemble pool (parameter + quality samples)."""
    from core.pipeline.fit_pipeline import FitResult

    x = np.linspace(0, 1e-4, 20)
    samples = {
        'Ka_guest': np.array([1.0e6, 1.1e6, 0.9e6]),
        'I0': np.array([100.0, 90.0, 110.0]),
        'I_dye_free': np.array([5.0e4, 5.1e4, 4.9e4]),
        'I_dye_bound': np.array([8.0e4, 8.1e4, 7.9e4]),
    }
    quality = {
        'rmse': np.array([0.006, 0.005, 0.007]),
        'r_squared': np.array([0.997, 0.998, 0.996]),
    }
    return FitResult(
        # Representative = index 1 (best RMSE / R²).
        parameters={'Ka_guest': 1.1e6, 'I0': 90.0, 'I_dye_free': 5.1e4, 'I_dye_bound': 8.1e4},
        rmse=0.005,
        r_squared=0.998,
        n_passing=3,
        n_total=10,
        x_fit=x,
        y_fit=x * 1.05,
        assay_type='GDA',
        model_name='equilibrium_4param',
        parameter_samples=samples,
        quality_samples=quality,
        representative_index=1,
    )


def test_seven_columns_merged_stats_and_ranges(qapp, full_fit_result):
    from gui.plotting.fit_summary_widget import _COLUMN_HEADERS, FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(full_fit_result)

    assert widget._table.columnCount() == 7
    headers = [widget._table.horizontalHeaderItem(c).text() for c in range(7)]
    assert headers == list(_COLUMN_HEADERS)
    # Merged 'central ± spread' cells (Median ± MAD, Mean ± SD) render one '±'.
    for col in (2, 3):
        assert '±' in widget._table.cellWidget(0, col).text()
    # 68% Range (col 4) and Min-Max Range (col 5) both render '[lo, hi]'.
    for col in (4, 5):
        t = widget._table.cellWidget(0, col).text()
        assert t.startswith('[') and t.endswith(']') and ',' in t


def test_log10_ka_row_computed_in_log_space(qapp, full_fit_result):
    """A log₁₀(Ka) row follows the Ka row; its Estimate is log₁₀ of the
    representative Ka (checked independently), not derived from a Ka spread."""
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(full_fit_result)

    # GDA has one log-scale key (Ka_guest) -> 4 params + 1 log row = 5 rows.
    assert widget._table.rowCount() == 5
    labels = [widget._table.cellWidget(r, 0).text() for r in range(5)]
    log_rows = [i for i, t in enumerate(labels) if t.startswith('log₁₀')]
    assert len(log_rows) == 1
    est = widget._table.cellWidget(log_rows[0], 1).text()
    assert abs(float(est) - np.log10(1.1e6)) < 0.05  # representative Ka = 1.1e6


def test_log10_row_is_never_written_coarser_than_its_own_spread(qapp, full_fit_result):
    """8.9974 must not read as '9': the log₁₀ row's decimals follow the spread it reports beside it."""
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    # A pool whose log₁₀(Ka) values sit a few thousandths apart around 8.9974.
    full_fit_result.parameter_samples['Ka_guest'] = 10 ** np.array([8.9940, 8.9974, 9.0008])
    full_fit_result.parameters['Ka_guest'] = 10**8.9974

    widget = FitSummaryWidget()
    widget.update_result(full_fit_result)
    (row,) = [r for r in range(widget._table.rowCount()) if widget._table.cellWidget(r, 0).text().startswith('log₁₀')]
    cells = [widget._table.cellWidget(row, c).text() for c in range(widget._table.columnCount())]

    assert cells[1] == '8.9974'
    # Every statistic beside it is written to the same decimals, so they compare.
    assert cells[2].startswith('8.9974 ± 0.00')
    assert cells[5] == '[8.9940, 9.0008]'


def test_a_log10_row_whose_pool_has_no_spread_keeps_the_figures_the_fit_knows(qapp, full_fit_result):
    """A pool of one fit reports a spread of zero, which is no reason to round the value.

    Written to the coarsest reading, the log₁₀ row would throw away three
    figures the Ka row directly above it still carries.
    """
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    full_fit_result.parameter_samples['Ka_guest'] = np.array([3.14e8])
    full_fit_result.parameters['Ka_guest'] = 3.14e8

    widget = FitSummaryWidget()
    widget.update_result(full_fit_result)
    (row,) = [r for r in range(widget._table.rowCount()) if widget._table.cellWidget(r, 0).text().startswith('log₁₀')]
    estimate = widget._table.cellWidget(row, 1).text()

    assert abs(float(estimate) - np.log10(3.14e8)) < 1e-6
    assert estimate.startswith('8.4969')


def test_a_log10_spread_too_tight_for_its_decimals_is_not_written_as_zero(qapp, full_fit_result):
    """A pool agreeing to a billionth of a decade has a spread, and reading '± 0.000000' denies it."""
    from gui.plotting.labels import fmt_log10

    stats = {'mad': 5.09e-9, 'std': 6e-9, 'p16': 8.496983, 'p84': 8.496983, 'min': 8.496983, 'max': 8.496983}

    assert fmt_log10(8.496983, stats) == '8.496983'
    assert float(fmt_log10(5.09e-9, stats)) == pytest.approx(5.09e-9)


def test_the_units_column_stays_readable_when_the_table_is_too_narrow(qapp, full_fit_result):
    """Squeezed, the columns give back width down to their headers; short of that, a scrollbar stays on screen."""
    from PyQt6.QtCore import Qt

    from gui.plotting.fit_summary_widget import _UNITS_COL, FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(full_fit_result)
    table = widget._table
    table.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    table.resize(420, 300)
    table.show()
    qapp.processEvents()
    table.autosize_columns()

    header_width = table.horizontalHeader().fontMetrics().horizontalAdvance('Units')
    assert table.columnWidth(_UNITS_COL) >= header_width
    right_edge = sum(table.columnWidth(c) for c in range(table.columnCount()))
    assert (
        right_edge <= table.viewport().width()
        or table.horizontalScrollBarPolicy() is Qt.ScrollBarPolicy.ScrollBarAlwaysOn
    )
    table.close()


def test_rep_combo_offers_named_choices_before_plot_selection(qapp, full_fit_result):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(full_fit_result)

    # Fresh fit, no plot pick yet: Best / Median / Worst only (no 'Selected').
    names = [widget._rep_combo.itemText(i).split(' ·')[0] for i in range(widget._rep_combo.count())]
    assert names == ['Best', 'Median', 'Worst']


def test_representative_selector_emits_pool_index(qapp, full_fit_result):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(full_fit_result)
    captured = []
    widget.representative_selected.connect(captured.append)

    # 'Worst' = lowest R² = pool index 2 (r² = [0.997, 0.998, 0.996]).
    widget._rep_combo.setCurrentIndex(2)
    assert captured == [2]


def test_selected_item_is_sticky_across_switches(qapp, full_fit_result):
    """The plot-picked fit becomes a sticky 'Selected' item that survives
    switching the representative to Best, so the user can compare and go back."""
    from dataclasses import replace

    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(full_fit_result)

    # Pick pool index 2 from the plot -> a 'Selected' item appears, and the
    # combo reflects the reported representative.
    widget.note_plot_selection(2)
    widget.update_result(replace(full_fit_result, representative_index=2))
    assert any(widget._rep_combo.itemText(i).startswith('Selected') for i in range(widget._rep_combo.count()))
    assert widget._rep_combo.currentData() == 2

    # Switch the representative to Best (index 1): 'Selected' (2) must remain.
    widget.update_result(replace(full_fit_result, representative_index=1))
    sel = [i for i in range(widget._rep_combo.count()) if widget._rep_combo.itemText(i).startswith('Selected')]
    assert len(sel) == 1
    assert widget._rep_combo.itemData(sel[0]) == 2  # still points at the plot pick


def test_new_fit_clears_sticky_selection(qapp, full_fit_result):
    """A different fit (new id) resets the sticky 'Selected' choice."""
    from dataclasses import replace

    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(full_fit_result)
    widget.note_plot_selection(2)
    widget.update_result(replace(full_fit_result, representative_index=2))
    assert any(widget._rep_combo.itemText(i).startswith('Selected') for i in range(widget._rep_combo.count()))

    fresh = replace(full_fit_result, id='different-fit-id', representative_index=1)
    widget.update_result(fresh)
    names = [widget._rep_combo.itemText(i).split(' ·')[0] for i in range(widget._rep_combo.count())]
    assert 'Selected' not in names


@pytest.fixture
def pool_result():
    """A five-attempt pool: Best = 1, Median = 0, Worst = 4, and attempt 3 in between.

    By default it is a per-replicate fit whose replicates hold attempts 0-2 and
    3-4, each led by its first attempt; against the averaged signal attempt 3
    beats attempt 0, so the fit chose attempt 3. With ``per_replicate=False``
    it is a single fit, which chose its top-R² attempt 1.
    """
    from dataclasses import replace

    from core.pipeline.fit_pipeline import FitResult

    def make(representative_index, metadata=None, *, per_replicate=True):
        x = np.linspace(0, 1e-4, 20)
        result = FitResult(
            parameters={'Ka_guest': 1e6, 'I0': 100.0, 'I_dye_free': 5e4, 'I_dye_bound': 8e4},
            rmse=0.005,
            r_squared=0.9985,
            n_passing=5,
            n_total=10,
            x_fit=x,
            y_fit=x,
            assay_type='GDA',
            model_name='equilibrium_4param',
            parameter_samples={
                'Ka_guest': np.array([1.0e6, 1.1e6, 0.9e6, 1.05e6, 0.8e6]),
                'I0': np.full(5, 100.0),
                'I_dye_free': np.full(5, 5e4),
                'I_dye_bound': np.full(5, 8e4),
            },
            quality_samples={
                'rmse': np.array([0.007, 0.005, 0.008, 0.006, 0.009]),
                'r_squared': np.array([0.9970, 0.9990, 0.9960, 0.9980, 0.9950]),
            },
            representative_index=representative_index,
            metadata=metadata or {},
        )
        if per_replicate:
            result.uncertainty_source = 'replicate'
            result.replica_fits = [
                replace(
                    result,
                    parameter_samples={k: v[s] for k, v in result.parameter_samples.items()},
                    quality_samples=None,
                    representative_index=0,
                    metadata={},
                )
                for s in (slice(0, 3), slice(3, 5))
            ]
        return result

    return make


def _items(widget):
    combo = widget._rep_combo
    return [(combo.itemText(i).split(' ·')[0], combo.itemData(i)) for i in range(combo.count())]


def _current(widget):
    return widget._rep_combo.currentText().split(' ·')[0], widget._rep_combo.currentData()


def _repoint_like_session(widget, result):
    """Re-point *result* the way ``select_representative`` does, then redisplay it."""

    def pick(index):
        result.metadata.setdefault('fitted_representative_index', result.representative_index)
        result.representative_index = index
        widget.update_result(result)

    widget.representative_selected.connect(pick)


def test_fit_choice_listed_first_when_not_the_top_r2_attempt(qapp, pool_result):
    """A per-replicate fit reporting attempt 3 must not be shown as 'Best' (attempt 1)."""
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(pool_result(3))

    assert _items(widget) == [("Fit's choice", 3), ('Best', 1), ('Median', 0), ('Worst', 4)]
    assert _current(widget) == ("Fit's choice", 3)
    assert widget._rep_combo.currentText() == "Fit's choice · R²=0.9980"


def test_top_r2_fit_choice_appears_once_as_best(qapp, pool_result):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(pool_result(1, per_replicate=False))

    assert _items(widget) == [('Best', 1), ('Median', 0), ('Worst', 4)]
    assert _current(widget) == ('Best', 1)


def test_fit_choice_stays_offered_after_picking_another_and_restores_it(qapp, pool_result):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    result = pool_result(3)
    widget.update_result(result)
    _repoint_like_session(widget, result)

    widget._rep_combo.setCurrentIndex(3)  # Worst
    assert result.representative_index == 4
    assert _current(widget) == ('Worst', 4)
    assert ("Fit's choice", 3) in _items(widget)

    widget._rep_combo.setCurrentIndex(0)  # Fit's choice
    assert result.representative_index == 3
    assert _current(widget) == ("Fit's choice", 3)


def test_plot_clicked_attempt_is_shown_as_selected(qapp, pool_result):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    result = pool_result(3)
    widget.update_result(result)
    widget.note_plot_selection(2)
    result.metadata['fitted_representative_index'] = 3
    result.representative_index = 2
    widget.update_result(result)

    assert _items(widget)[-1] == ('Selected', 2)
    assert _current(widget) == ('Selected', 2)


@pytest.mark.parametrize(
    ('representative_index', 'metadata', 'expected'),
    [
        (3, {}, ("Fit's choice", 3)),
        (1, {}, ('Best', 1)),
        (0, {'fitted_representative_index': 1}, ('Median', 0)),
        (4, {'fitted_representative_index': 3}, ('Worst', 4)),
        (2, {'fitted_representative_index': 3}, ('Picked', 2)),
        (2, {}, ('Picked', 2)),
        (None, {}, ('Shown fit', -1)),
    ],
)
def test_current_item_always_names_the_shown_attempt(qapp, pool_result, representative_index, metadata, expected):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    emitted = []
    widget.representative_selected.connect(emitted.append)
    widget.update_result(pool_result(representative_index, metadata))

    assert _current(widget) == expected
    assert emitted == []


@pytest.mark.parametrize(
    ('per_replicate', 'fit_choice'),
    [(True, [("Fit's choice", 3)]), (False, [])],
)
def test_a_pick_from_a_file_without_the_recorded_choice_is_not_called_the_fit_s_choice(
    qapp, pool_result, per_replicate, fit_choice
):
    """A file can store a picked attempt without recording the fit's own choice; the pool still tells them apart."""
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(pool_result(4, per_replicate=per_replicate))

    assert _items(widget) == [*fit_choice, ('Best', 1), ('Median', 0), ('Worst', 4)]
    assert _current(widget) == ('Worst', 4)


@pytest.mark.parametrize('shown', [2, 3])
def test_shown_attempt_is_named_only_as_shown_when_the_fit_s_choice_cannot_be_told(qapp, pool_result, shown):
    """A per-replicate pool without its replicates' fits cannot say which attempt the fit chose."""
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    result = pool_result(shown)
    result.replica_fits = None
    widget = FitSummaryWidget()
    widget.update_result(result)

    assert _items(widget) == [('Best', 1), ('Median', 0), ('Worst', 4), ('Shown fit', shown)]
    assert _current(widget) == ('Shown fit', shown)


def test_listed_r2_values_carry_the_decimals_that_tell_attempts_apart(qapp, pool_result):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    result = pool_result(3)
    result.quality_samples['r_squared'] = np.array([0.9970, 0.999004, 0.9960, 0.999001, 0.9950])
    widget = FitSummaryWidget()
    widget.update_result(result)

    combo = widget._rep_combo
    assert [combo.itemText(i) for i in range(combo.count())] == [
        "Fit's choice · R²=0.999001",
        'Best · R²=0.999004',
        'Median · R²=0.997000',
        'Worst · R²=0.995000',
    ]


def test_listed_r2_values_stop_at_six_decimals():
    """Attempts that agree to six decimals fit equally well and read the same."""
    from gui.plotting.fit_summary_widget import _distinct_r2_texts

    assert _distinct_r2_texts([0, 1], [0.9934149172, 0.9934149167]) == ['0.993415', '0.993415']
