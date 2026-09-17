"""GUI smoke tests for the Ka-sensitivity panel and widget.

Pins the wiring the compute-layer tests can't reach:

- :class:`SensitivityPanel` rebuilds its per-input uncertainty rows (titrant +
  every concentration / binding-constant condition, including ``Ka_dye``) when
  the assay type changes, hides the heatmap controls outside heatmap mode, and
  disables itself for ``DYE_ALONE``.
- :class:`SensitivityWidget` draws each Sobol index with a whisker spanning
  its confidence interval, the legend naming it, one Ka vs input panel per varied
  input with the below-floor samples light grey behind the others, a key to the
  two colours and the unfitted ones left out, each panel opening on the input's
  range as entered (± the farthest sampled offset for a σ input), rings
  below-floor heatmap cells, states those counts in a note, names the indices one
  way, and restyles/clears cleanly.
- The heatmap colours each cell by the chosen statistic (Ka change by default,
  symmetric in the log ratio to the baseline Ka; Ka on the Plot Style's Ka
  scale; R²), labels its colour bar in the style's tick font, keeps the choice
  across new results and restyles, and names both inputs in its hover readout.
- The summary under the plot tabs follows the tab. On Ka Sensitivity, after a
  Sobol run, it gives every parameter the fit table's statistics over all fitted
  samples (below-floor ones included) around the run's baseline fit, counts the
  samples below the floor and describes their R² under Fit Quality, hides the
  Representative selector, stars the degenerate signal parameters, says whether
  the estimate matches the fit on the other tabs and names why it can differ,
  and does not call samples a stopped run never reached unfittable. Without a
  Sobol run to summarise (none yet, a heatmap, no sample fits) it shows the fit
  with a note. Every other tab shows the fit cell for cell, and a new run, a
  failed run, a heatmap and new or cleared data never leave it stale.
- :class:`SensitivityWorker` sends at most about ten progress updates a second
  and always delivers the latest count at a cancel and at the end, so the bar
  still ends full; the status bar drops the time estimate at the last count and
  says when a run was stopped; a failed run takes the tab off the progress page.

Require a ``QApplication`` (the ``qapp`` fixture).
"""

import re
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip('PyQt6')

import pyqtgraph as pg  # noqa: E402

from core.assays.registry import AssayType  # noqa: E402
from core.pipeline.fit_pipeline import FitResult, summarize_parameters  # noqa: E402
from core.pipeline.sensitivity import (  # noqa: E402
    _SOBOL_BLOCKS,
    TITRANT,
    InputSpec,
    SensitivityConfig,
    SensitivityMode,
    SensitivityResult,
)
from core.units import Q_  # noqa: E402

# ---------------------------------------------------------------------------
# SensitivityPanel
# ---------------------------------------------------------------------------


def test_set_assay_type_rebuilds_input_rows(qapp):
    """The uncertainty rows track the assay's perturbable inputs (titrant + conditions)."""
    from gui.widgets.sensitivity_panel import SensitivityPanel

    panel = SensitivityPanel()

    panel.set_assay_type(AssayType.IDA)
    assert set(panel._rows) == {TITRANT, 'Ka_dye', 'h0', 'd0'}
    # Heatmap axis combos offer exactly those inputs.
    assert panel._x_combo.count() == len(panel._rows)

    panel.set_assay_type(AssayType.GDA)
    assert set(panel._rows) == {TITRANT, 'Ka_dye', 'h0', 'g0'}

    # A single-condition assay: just the titrant + its one fixed concentration.
    panel.set_assay_type(AssayType.DBA_HtoD)
    assert set(panel._rows) == {TITRANT, 'fixed_conc'}


def test_heatmap_controls_hidden_outside_heatmap_mode(qapp):
    """The heatmap axis group shows only in Heatmap mode; samples row is inverse."""
    from gui.widgets.sensitivity_panel import SensitivityPanel

    panel = SensitivityPanel()
    panel.set_assay_type(AssayType.IDA)

    # Default mode is the sensitivity-index analysis.
    assert panel._heatmap_group.isHidden()
    assert not panel._samples_row.isHidden()

    # Switch to Heatmap (combo index 1).
    panel._mode_combo.setCurrentIndex(1)
    assert not panel._heatmap_group.isHidden()
    assert panel._samples_row.isHidden()

    # Back to the index analysis.
    panel._mode_combo.setCurrentIndex(0)
    assert panel._heatmap_group.isHidden()
    assert not panel._samples_row.isHidden()


def test_sample_size_choices_are_the_valid_sobol_sizes_defaulting_to_1024(qapp):
    """The panel offers exactly the sizes the 8-block Sobol' design accepts, from 1024 up."""
    from gui.widgets.sensitivity_panel import SensitivityPanel

    panel = SensitivityPanel()
    sizes = [panel._samples_combo.itemData(i) for i in range(panel._samples_combo.count())]
    assert sizes == [1024, 2048, 4096]
    assert panel.current_config().n_samples == 1024


def test_panel_disabled_for_dye_alone(qapp):
    """DYE_ALONE has no Ka to analyse, so the whole panel is disabled."""
    from gui.widgets.sensitivity_panel import SensitivityPanel

    panel = SensitivityPanel()
    panel.set_assay_type(AssayType.IDA)
    assert panel.isEnabled()

    panel.set_assay_type(AssayType.DYE_ALONE)
    assert not panel.isEnabled()


# ---------------------------------------------------------------------------
# SensitivityWidget
# ---------------------------------------------------------------------------


_FLOOR = 0.99
_INPUTS = ('Ka_dye', 'h0', TITRANT)


def _baseline_fit():
    """The IDA fit with the inputs as entered, carrying its own multistart pool, far wider than the samples."""
    x = np.linspace(0.0, 1e-4, 5)
    return FitResult(
        parameters={
            'Ka_guest': Q_(2e8, '1/M'),
            'I0': Q_(100.0, 'au'),
            'I_dye_free': Q_(5e9, 'au/M'),
            'I_dye_bound': Q_(7e10, 'au/M'),
        },
        rmse=10.0,
        r_squared=0.998,
        n_passing=3,
        n_total=100,
        x_fit=x,
        y_fit=x,
        assay_type='IDA',
        model_name='equilibrium_4param',
        parameter_samples={
            'Ka_guest': np.array([1e8, 2e8, 4e8]),
            'I0': np.array([0.0, 100.0, 900.0]),
            'I_dye_free': np.array([1e9, 5e9, 9e9]),
            'I_dye_bound': np.array([6e10, 7e10, 8e10]),
        },
    )


def _sobol_result():
    """Three varied inputs, 40 A+B samples: every third below the floor, sample 5 unfitted."""
    rng = np.random.default_rng(0)
    n = 40
    offsets = {key: rng.normal(0.0, 5.0, n) for key in _INPUTS}
    ka = 2e8 * (1 + 0.01 * offsets[TITRANT])
    ka[5] = np.nan
    signal = {
        key: rng.normal(mean, 0.2 * mean, n)
        for key, mean in (('I0', 100.0), ('I_dye_free', 5e9), ('I_dye_bound', 7e10))
    }
    for values in signal.values():
        values[5] = np.nan
    r2 = np.where(np.arange(n) % 3 == 0, 0.95, 0.995)
    r2[5] = np.nan
    s1 = {'Ka_dye': 0.05, 'h0': 0.2, TITRANT: 0.6}
    st = {'Ka_dye': 0.08, 'h0': 0.25, TITRANT: np.nan}
    return SensitivityResult(
        mode=SensitivityMode.SOBOL,
        assay_type='IDA',
        ka_keys=('Ka_guest',),
        baseline_ka={'Ka_guest': 2e8},
        x_offsets_pct=None,
        y_offsets_pct=None,
        ka_grid=None,
        n_success=n - 1,
        n_total=n,
        config=SensitivityConfig(SensitivityMode.SOBOL, n // 2, {k: InputSpec.sigma_pct(5.0) for k in _INPUTS}, seed=0),
        seed_used=0,
        sobol_s1={'Ka_guest': s1},
        sobol_st={'Ka_guest': st},
        sobol_s1_ci={'Ka_guest': {k: (v - 0.03, v + 0.1) for k, v in s1.items()}},
        sobol_st_ci={'Ka_guest': {k: (v - 0.04, v + 0.2) for k, v in st.items()}},
        sample_offsets_pct=offsets,
        sample_ka={'Ka_guest': ka},
        sample_r2=r2,
        floor=_FLOOR,
        n_below_floor=int(np.sum(r2 < _FLOOR)),
        baseline_fit=_baseline_fit(),
        sample_params={'Ka_guest': ka, **signal},
        degenerate_keys=('I0', 'I_dye_free', 'I_dye_bound'),
    )


def _plots(widget):
    """Every plot item on the results page."""
    return [pw.getPlotItem() for pw in widget._results_host.widget().findChildren(pg.PlotWidget)]


def _heatmap_result():
    x = np.linspace(-5.0, 5.0, 3)
    y = np.linspace(-5.0, 5.0, 3)
    grid = np.array(
        [
            [1.8e6, 1.9e6, 2.0e6],
            [1.9e6, 2.0e6, 2.1e6],
            [2.0e6, np.nan, 2.2e6],  # one failed-fit cell (transparent path)
        ]
    )
    r2 = np.array(
        [
            [0.95, 0.995, 0.995],
            [0.995, 0.995, 0.995],
            [0.995, np.nan, 0.95],
        ]
    )
    return SensitivityResult(
        mode=SensitivityMode.HEATMAP,
        assay_type='IDA',
        ka_keys=('Ka_guest',),
        baseline_ka={'Ka_guest': 2e6},
        x_offsets_pct=x,
        y_offsets_pct=y,
        ka_grid={'Ka_guest': grid},
        n_success=8,
        n_total=9,
        config=SensitivityConfig(
            SensitivityMode.HEATMAP, 1, {TITRANT: 5.0, 'h0': 5.0}, x_key=TITRANT, y_key='h0', n_steps=3
        ),
        seed_used=0,
        r2_grid=r2,
        floor=_FLOOR,
        n_below_floor=2,
    )


def test_widget_renders_sobol_result(qapp):
    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    w.update_result(_sobol_result())
    # Landed on the results page (not placeholder/progress).
    assert w._stack.currentWidget() is w._results_host

    # Restyling with a linear Ka axis must also render cleanly.
    w.apply_style({'distribution': {'ka_scale': 'linear'}})
    assert w._stack.currentWidget() is w._results_host


def test_index_whiskers_span_the_confidence_interval(qapp):
    """Each finite index carries a whisker from the lower to the upper end of its confidence interval."""
    from gui.plotting.sensitivity_widget import SensitivityWidget

    result = _sobol_result()
    w = SensitivityWidget()
    w.update_result(result)
    (plot,) = [plot for plot in _plots(w) if 'Sobol indices' in plot.titleLabel.text]
    whiskers = [item for item in plot.items if isinstance(item, pg.ErrorBarItem)]
    spans = sorted(
        (float(y - h / 2), float(y + h / 2)) for item in whiskers for y, h in zip(item.opts['y'], item.opts['height'])
    )
    expected = sorted(
        ci
        for key in ('sobol_s1', 'sobol_st')
        for k, ci in getattr(result, f'{key}_ci')['Ka_guest'].items()
        if np.isfinite(getattr(result, key)['Ka_guest'][k])
    )
    # S_T of the titrant is NaN: no bar, so no whisker either.
    assert len(spans) == 5
    np.testing.assert_allclose(spans, expected)


def test_index_legend_names_the_whiskers_a_95_percent_confidence_interval(qapp):
    """The whisker legend entry reads exactly '95% confidence interval'."""
    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    w.update_result(_sobol_result())
    (plot,) = [plot for plot in _plots(w) if 'Sobol indices' in plot.titleLabel.text]
    by_label = {label.text: sample.item for sample, label in plot.legend.items}
    assert isinstance(by_label['95% confidence interval'], pg.ErrorBarItem)


def test_no_gui_text_calls_the_interval_wide_side():
    """No GUI text calls the interval "on the wide side"."""
    gui = Path(__file__).resolve().parents[3] / 'gui'
    offenders = [str(path) for path in gui.rglob('*.py') if 'wide side' in path.read_text(encoding='utf-8').lower()]
    assert offenders == []


def _ka_vs_input_panels(widget) -> dict:
    """Each "Ka vs input" panel's plot item, by the input key its x-axis names."""
    by_label = {plot.getAxis('bottom').labelText: plot for plot in _plots(widget)}
    return {
        key: by_label[f'Δ {widget._input_label(AssayType.IDA, key)} [%]'] for key in widget._result.sample_offsets_pct
    }


def _floor_keys(widget) -> list[str]:
    """Text of every dot-colour key on the results page, once the pages of earlier results are deleted."""
    from PyQt6.QtCore import QCoreApplication, QEvent
    from PyQt6.QtWidgets import QLabel

    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    return [label.text() for label in widget._results_host.widget().findChildren(QLabel) if '●' in label.text()]


def test_ka_vs_input_panels_draw_below_floor_samples_grey_behind_the_blue(qapp):
    """Below-floor fits are the same dots in light grey behind the blue, with a key; no line; the unfitted left out."""
    from gui.plotting.sensitivity_widget import SensitivityWidget

    result = _sobol_result()
    ka, r2 = result.sample_ka['Ka_guest'], result.sample_r2
    fitted = np.isfinite(ka)
    below = fitted & (r2 < _FLOOR)
    w = SensitivityWidget()
    w.update_result(result)

    panels = _ka_vs_input_panels(w)
    assert len(panels) == len(_INPUTS)
    for plot in panels.values():
        items = [item for item in plot.items if isinstance(item, pg.PlotDataItem)]
        by_name = {item.name(): item for item in items}
        assert len(items) == 2 and all(item.opts['pen'] is None for item in items)
        grey, blue = by_name['below the threshold'], by_name['meets the threshold']
        np.testing.assert_array_equal(np.sort(grey.getOriginalDataset()[1]), np.sort(ka[below]))
        np.testing.assert_array_equal(np.sort(blue.getOriginalDataset()[1]), np.sort(ka[fitted & ~below]))
        assert (grey.opts['symbolBrush'].color().name(), blue.opts['symbolBrush'].color().name()) == (
            '#c3c2b7',
            '#2a78d6',
        )
        assert grey.opts['symbol'] == blue.opts['symbol'] == 'o'
        assert grey.opts['symbolSize'] == blue.opts['symbolSize'] >= 8
        for dots in (grey, blue):
            assert (dots.opts['symbolPen'].color().name(), dots.opts['symbolPen'].widthF()) == ('#fcfcfb', 2.0)
        assert grey.zValue() < blue.zValue()

    (key,) = _floor_keys(w)
    assert 'color: #2a78d6;">●</span> best fit meets the Min R² (0.99)' in key
    assert 'color: #c3c2b7;">●</span> best fit falls below it' in key
    assert 'the Ka vs each input panels draw them in light grey' in w._note.text() and 'hollow' not in w._note.text()

    # With no fit below the floor the key has no grey entry.
    w.update_result(replace(result, sample_r2=np.where(fitted, 0.995, np.nan), n_below_floor=0))
    (key,) = _floor_keys(w)
    assert '#c3c2b7' not in key and 'below' not in key


_H0_RANGE_PCT = (100 * (4.1e-6 / 4.3e-6 - 1), 100 * (4.4e-6 / 4.3e-6 - 1))


def _ranged_result() -> SensitivityResult:
    """Ka,dye entered as the range −6 % to +4 %, [Host]₀ as 4.1–4.4 µM of 4.3 µM, the titrant as σ 5 %."""
    rng = np.random.default_rng(1)
    base = _sobol_result()
    specs = {
        'Ka_dye': InputSpec.interval_pct(-6.0, 4.0),
        'h0': InputSpec.interval_abs(4.1e-6, 4.4e-6),
        TITRANT: InputSpec.sigma_pct(5.0),
    }
    offsets = {
        'Ka_dye': rng.uniform(-6.0, 4.0, 40),
        'h0': rng.uniform(*_H0_RANGE_PCT, 40),
        TITRANT: base.sample_offsets_pct[TITRANT],
    }
    conditions = {'Ka_dye': Q_(1.68e7, '1/M'), 'h0': Q_(4.3e-6, 'M'), 'd0': Q_(6e-6, 'M')}
    return replace(
        base,
        config=replace(base.config, input_specs=specs),
        sample_offsets_pct=offsets,
        baseline_fit=replace(base.baseline_fit, conditions=conditions),
    )


def test_ka_vs_input_panels_open_on_the_range_entered_whatever_their_width(qapp):
    """A range opens on exactly its ends, an absolute one in percent of the set value; a σ on ± the farthest sample.

    The margin at each end is a fixed share of that range, so a narrow panel is framed like a wide one, and
    zoom, pan and View All stay available.
    """
    from PyQt6.QtCore import Qt

    from gui.plotting.sensitivity_widget import _OFFSET_VIEW_MARGIN, SensitivityWidget

    result = _ranged_result()
    reach = float(np.max(np.abs(result.sample_offsets_pct[TITRANT])))
    entered = {'Ka_dye': (-6.0, 4.0), 'h0': _H0_RANGE_PCT, TITRANT: (-reach, reach)}
    assert 0 < _OFFSET_VIEW_MARGIN <= 0.05

    w = SensitivityWidget()
    w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    w.update_result(result)
    w.show()
    for width in (1500, 560):
        w.resize(width, 1100)
        qapp.processEvents()
        for key, plot in _ka_vs_input_panels(w).items():
            lo, hi = entered[key]
            margin = _OFFSET_VIEW_MARGIN * (hi - lo)
            np.testing.assert_allclose(plot.viewRange()[0], (lo - margin, hi + margin), rtol=0, atol=1e-9)

    for plot in _ka_vs_input_panels(w).values():
        vb = plot.getViewBox()
        assert vb.state['mouseEnabled'] == [True, True]
        vb.autoRange()
        x_lo, x_hi = plot.viewRange()[0]
        for item in plot.items:
            if isinstance(item, pg.PlotDataItem) and item.getOriginalDataset()[0].size:
                x = item.getOriginalDataset()[0]
                assert x_lo <= x.min() and x.max() <= x_hi
    w.close()


def test_a_range_inputs_panel_labels_both_ends_entered_however_narrow(qapp):
    """The Δ-input axis of a range input labels its two ends (−6 and 4; −4.65 and 2.33 for 4.1–4.4 µM of 4.3 µM).

    A σ input has no entered ends, so its axis carries only the regular ticks.
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QImage, QPainter

    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    w.update_result(_ranged_result())
    w.show()
    expected = {'Ka_dye': {'-6', '4'}, 'h0': {'-4.65', '2.33'}, TITRANT: set()}
    image = QImage(10, 10, QImage.Format.Format_ARGB32)
    for width in (1500, 560):
        w.resize(width, 1100)
        qapp.processEvents()
        for key, plot in _ka_vs_input_panels(w).items():
            axis = plot.getAxis('bottom')
            painter = QPainter(image)
            _, _, texts = axis.generateDrawSpecs(painter)
            painter.end()
            labels = {text for _, _, text in texts}
            assert expected[key] <= labels, (width, key, labels)
            if key == TITRANT:
                assert all(float(label) == round(float(label)) for label in labels)
    w.close()


def test_ka_sensitivity_tab_names_the_indices_one_way_and_the_uncertainty_group(qapp):
    """S₁ (first order) and S_T (total), as the legend names them, are the only names the tab gives the indices."""
    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    assert 'Input uncertainty' in w._placeholder.text() and 'Δ' not in w._placeholder.text()

    w.update_result(replace(_sobol_result(), sobol_rows_left_out={'Ka_guest': 3}, sobol_s1={'Ka_guest': {'h0': 4.0}}))
    (index_panel,) = [
        pw
        for pw in w._results_host.widget().findChildren(pg.PlotWidget)
        if 'Sobol indices' in pw.getPlotItem().titleLabel.text
    ]
    legend = [label.text for _, label in index_panel.getPlotItem().legend.items]
    assert legend[:2] == ['S<sub>1</sub> (first order)', 'S<sub>T</sub> (total)']
    texts = (w.toolTip(), index_panel.toolTip(), w._note.text())
    assert 'An arrow on the index chart' in w._note.text() and 'Sobol indices leave out' in w._note.text()
    assert not any(re.search(r'share|first-order|total-order|direct', text, re.IGNORECASE) for text in texts)


def test_interval_texts_name_what_the_interval_covers_and_the_block_count(qapp):
    """Both interval texts describe the index unlimited samples give and take the block count from the core."""
    from gui.plotting.sensitivity_widget import SensitivityWidget
    from gui.widgets.sensitivity_panel import _SAMPLES_HELP_HTML

    w = SensitivityWidget()
    w.update_result(_sobol_result())
    (index_panel,) = [
        pw
        for pw in w._results_host.widget().findChildren(pg.PlotWidget)
        if 'Sobol indices' in pw.getPlotItem().titleLabel.text
    ]
    for text in (' '.join(_SAMPLES_HELP_HTML.split()), index_panel.toolTip()):
        assert f'{_SOBOL_BLOCKS} independent sample sets' in text
        assert 'unlimited samples' in text
        assert 'A repeat run with fresh samples usually lands inside it, but not always.' in text
        assert 'if the analysis were repeated' not in text
    gui = Path(__file__).resolve().parents[3] / 'gui'
    typed = [str(path) for path in gui.rglob('*.py') if re.search(r'\d\s+independent sample', path.read_text('utf-8'))]
    assert typed == []


@pytest.mark.parametrize(
    ('left_out', 'sentence'),
    [
        ({'Ka_guest': 0}, None),
        (
            {'Ka_guest': 3},
            'The Sobol indices leave out 3 of the 20 sample groups set by the sample size: '
            'at least one fit in each of those groups could not be made.',
        ),
        (
            {'Ka_dye': 0, 'Ka_guest': 1},
            'The Sobol indices for Ka(G) leave out 1 of the 20 sample groups set by the '
            'sample size: at least one fit in that group could not be made.',
        ),
    ],
)
def test_note_counts_design_rows_the_indices_leave_out(qapp, left_out, sentence):
    """Rows lost to a failed mixed-sample fit are reported, although every A and B sample was fitted."""
    from gui.plotting.sensitivity_widget import SensitivityWidget

    result = replace(_sobol_result(), sobol_rows_left_out=left_out)
    w = SensitivityWidget()
    w.update_result(result)
    text = w._note.text()
    assert ('sample groups' in text) == (sentence is not None)
    if sentence is not None:
        assert sentence in text


def test_note_states_below_floor_and_unfitted_counts(qapp):
    """The below-floor count is out of the samples that have a fit, as Fit Quality counts them."""
    from gui.plotting.sensitivity_widget import SensitivityWidget

    result = _sobol_result()  # 40 samples, one of them unfitted
    w = SensitivityWidget()
    w.update_result(result)
    text = w._note.text()
    assert f'{result.n_below_floor} of the 39 samples that have a fit' in text
    assert '1 of 40 samples could not be fitted' in text

    assert f'Seed {result.seed_used}' in text  # what repeats the run is on the tab, and in its picture

    # A result without quality data has no counts to report, only its seed.
    result.floor = result.sample_r2 = result.sample_ka = None
    w.update_result(result)
    assert w._note.text() == f'Seed {result.seed_used}: enter it under Fixed seed to repeat this analysis exactly.'


@pytest.mark.parametrize(
    'st_ci, expect, avoid',
    [
        ((0.30, 0.45), 'equal to within their whiskers', 'unreliable'),
        ((0.10, 0.20), 'wider than the two whiskers span', 'equal to within'),
    ],
    ids=['whiskers-overlap', 'whiskers-apart'],
)
def test_a_total_order_drawn_below_its_first_order_is_explained_by_the_whiskers(qapp, st_ci, expect, avoid):
    """A total order cannot really be below a first order, so the note says which of the two readings applies.

    Equal to within the whiskers means the input acts on its own and either can
    come out on top. A gap wider than the whiskers is not sampling noise of one
    index, and must not be reported as if it were.
    """
    from gui.plotting.sensitivity_widget import SensitivityWidget

    result = _sobol_result()
    result.sobol_s1 = {'Ka_guest': {'h0': 0.40}}
    result.sobol_st = {'Ka_guest': {'h0': 0.30}}
    result.sobol_s1_ci = {'Ka_guest': {'h0': (0.35, 0.45)}}
    result.sobol_st_ci = {'Ka_guest': {'h0': st_ci}}
    w = SensitivityWidget()
    w.update_result(result)

    text = w._note.text()
    assert expect in text
    assert avoid not in text


def test_below_floor_count_of_a_cancelled_run_leaves_out_the_samples_it_never_fitted(qapp):
    """A run stopped part way counts its below-floor fits out of the samples it fitted, not of every planned one."""
    from gui.plotting.sensitivity_widget import SensitivityWidget

    result = _sobol_result()  # 40 samples, sample 5 unfitted
    ka = np.asarray(result.sample_ka['Ka_guest'], dtype=float)
    r2 = np.asarray(result.sample_r2, dtype=float)
    ka[10:] = np.nan  # the run was cancelled after the tenth sample
    r2[10:] = np.nan
    r2[:10] = [0.95, 0.95, 0.95, *([0.995] * 7)]
    result.sample_ka = {'Ka_guest': ka}
    result.sample_r2 = r2
    result.stopped = True
    result.n_success = result.n_total = 9

    w = SensitivityWidget()
    w.update_result(result)
    text = w._note.text()
    assert 'The best fit of 3 of the 9 samples that have a fit falls below' in text
    assert 'of the 40 samples' not in text
    assert '31 of 40 samples' in text  # sample 5 plus the thirty the run never reached


def test_log_ka_axis_labels_round_values_within_a_decade(qapp):
    """A Ka spread under a factor of two still gets several readable ticks, in the app's ×10ⁿ notation."""
    from gui.plotting.sensitivity_widget import _LogKaAxis

    axis = _LogKaAxis(orientation='left')
    ((_, values),) = axis.logTickValues(np.log10(2.5e8), np.log10(4e8), 200, [])
    assert axis.logTickStrings(values, 1.0, None) == ['2.5×10⁸', '3×10⁸', '3.5×10⁸', '4×10⁸']


def _drawn_labels(axis) -> list:
    """``(box, text)`` of every tick label pyqtgraph would draw, left to right."""
    from PyQt6.QtGui import QImage, QPainter

    image = QImage(10, 10, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    _, _, texts = axis.generateDrawSpecs(painter)
    painter.end()
    return sorted(((rect, text) for rect, _, text in texts), key=lambda box: box[0].left())


@pytest.mark.parametrize('decades', [(8.1, 11.9), (7.8, 9.6), (8.0, 10.0), (-9.0, 13.0), (8.4, 8.6)])
@pytest.mark.parametrize('width', [420, 1060])
def test_log_ka_axis_labels_never_overlap(qapp, decades, width):
    """Across a few decades, labels thin out to what fits instead of running into each other."""
    from PyQt6.QtGui import QFont

    from gui.plotting.sensitivity_widget import _LogKaAxis

    axis = _LogKaAxis(orientation='bottom')
    font = QFont()
    font.setPointSize(14)
    axis.setTickFont(font)
    pw = pg.PlotWidget(axisItems={'bottom': axis})
    pw.resize(width, 300)
    pw.show()
    axis.setLogMode(True)
    pw.getPlotItem().setRange(xRange=decades, padding=0)
    qapp.processEvents()

    labels = _drawn_labels(axis)
    assert len(labels) >= 2
    touching = [(a[1], b[1]) for a, b in zip(labels, labels[1:]) if a[0].right() >= b[0].left()]
    assert touching == []
    pw.close()


def test_index_chart_keeps_its_scale_when_an_index_runs_far_off(qapp):
    """A wild index from a small run is cut at the edge with an arrow, and the others stay readable."""
    from gui.plotting.sensitivity_widget import SensitivityWidget

    result = _sobol_result()
    result.sobol_st['Ka_guest']['h0'] = 4.5e5
    result.sobol_st_ci['Ka_guest']['h0'] = (0.002, 3.2e8)
    w = SensitivityWidget()
    w.update_result(result)

    (plot,) = [plot for plot in _plots(w) if 'Sobol indices' in plot.titleLabel.text]
    _, (y_lo, y_hi) = plot.viewRange()
    assert -0.7 < y_lo and y_hi < 2.0
    arrows = [item for item in plot.items if isinstance(item, pg.TextItem) and '▲' in item.toHtml()]
    assert len(arrows) == 1
    assert 'An arrow on the index chart' in w._note.text()


def test_histogram_title_reads_in_plain_numbers(qapp):
    """Median as ×10ⁿ and the spread as a fold range, not ``3.25e+08`` and a percent of a raw Ka."""
    from gui.plotting.labels import fmt_sci
    from gui.plotting.sensitivity_widget import SensitivityWidget

    result = _sobol_result()
    w = SensitivityWidget()
    w.update_result(result)
    (plot,) = [plot for plot in _plots(w) if 'median' in plot.titleLabel.text]
    title = plot.titleLabel.text
    ka = np.asarray(result.sample_ka['Ka_guest'], dtype=float)
    assert f'median {fmt_sci(float(np.median(ka[np.isfinite(ka)])), 3)} M' in title
    assert '×10⁸' in title
    assert 'middle 90% within' in title and '-fold' in title
    assert 'e+' not in title and 'CV' not in title


def test_widget_renders_heatmap_result_with_nan_cell(qapp):
    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    w.update_result(_heatmap_result())  # must not raise despite the NaN cell
    assert w._stack.currentWidget() is w._results_host


def test_heatmap_axes_label_the_cells_and_label_themselves_again_when_zoomed_in(qapp):
    """Cell ticks read the map's own steps; zoomed past them the axis must not go unlabelled."""
    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    w.update_result(_heatmap_result())
    plot = w._hover_targets[0]['plot']
    bottom = plot.getAxis('bottom')

    assert [value for value, _label in bottom._tickLevels[0]] == [-5.0, 0.0, 5.0]

    plot.getViewBox().setXRange(-3.0, -1.0, padding=0)
    plot.getViewBox().setYRange(-3.0, -1.0, padding=0)
    qapp.processEvents()

    # No cell centre lies in view, so the axis falls back on ticks of its own.
    assert bottom._tickLevels is None


def _colour_by(widget, text: str) -> None:
    widget._colour_combo.setCurrentIndex(widget._colour_combo.findText(text))


@pytest.mark.parametrize('stat', ['Ka change', 'Ka', 'R²'])
def test_heatmap_rings_cells_below_the_floor(qapp, stat):
    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    w.update_result(_heatmap_result())
    _colour_by(w, stat)
    plot = w._hover_targets[0]['plot']
    rings = [
        item for item in plot.items if isinstance(item, pg.ScatterPlotItem) and item.name() == 'below the threshold'
    ]
    assert rings
    for ring in rings:
        # r2_grid is [iy, ix] with iy along the y offsets: cells (x, y) = (-5 %, -5 %) and (+5 %, +5 %).
        assert sorted(zip(*ring.getData())) == [(-5.0, -5.0), (5.0, 5.0)]
    assert 'The best fit of 2 of the 8 grid cells that have a fit' in w._note.text()
    assert '1 of 9 grid cells could not be fitted' in w._note.text()


def _pct_of(label: str) -> float:
    """Percent change stated by a colour-bar tick label (``'−50%'`` → -50, ``'0'`` → 0)."""
    return float(label.rstrip('%').replace('−', '-'))


def test_heatmap_colours_ka_change_by_default_symmetric_in_the_log_ratio(qapp):
    """Halving and doubling the baseline Ka land on the two ends of the diverging scale, the baseline on its centre."""
    from gui.plotting.sensitivity_widget import SensitivityWidget

    result = _heatmap_result()
    grid = np.array([[1e6, 2e6, 4e6], [2e6, 2e6, 2.5e6], [1.6e6, np.nan, 2e6]])
    result.ka_grid = {'Ka_guest': grid}
    w = SensitivityWidget()
    w.update_result(result)

    assert w._colour_combo.currentText() == 'Ka change'
    (target,) = w._hover_targets
    np.testing.assert_allclose(target['values'], np.log10(grid / 2e6))
    reach = np.log10(2.0)
    np.testing.assert_allclose(target['colour_bar'].values, (-reach, reach))
    (image,) = [item for item in target['plot'].items if isinstance(item, pg.ImageItem)]
    rgba = image.image  # [iy, ix], as the grid
    assert tuple(rgba[0, 0, :3]) == (42, 120, 214)  # Ka halved: lower end, blue
    assert tuple(rgba[0, 2, :3]) == (227, 73, 72)  # Ka doubled: higher end, red
    assert tuple(rgba[1, 1, :3]) == (240, 239, 236)  # baseline Ka: zero, grey
    assert rgba[2, 1, 3] == 0  # no fit: transparent

    # Every tick sits where the change it states puts it, halving and doubling included.
    (ticks,) = target['colour_bar'].axis._tickLevels
    labels = [text for _, text in ticks]
    assert {'−50%', '0', '+100%'} <= set(labels)
    for position, text in ticks:
        assert position == pytest.approx(np.log10(1 + _pct_of(text) / 100), abs=1e-12)


_FROM_SUPERSCRIPT = str.maketrans('⁰¹²³⁴⁵⁶⁷⁸⁹⁻', '0123456789-')


def _ratio_of(label: str) -> float:
    """Ka ratio a Ka-change tick label states (``'−50%'`` → 0.5, ``'+5×10⁷%'`` → 5×10⁵ + 1, ``'×10⁻⁶'`` → 10⁻⁶)."""
    mantissa, _, power = label.rstrip('%').replace('−', '-').partition('×10')
    value = float(mantissa or 1) * 10.0 ** int(power.translate(_FROM_SUPERSCRIPT) or 0)
    return value if label.startswith('×') else 1 + value / 100


@pytest.mark.parametrize('reach', [4.0, 6.0, 15.7, 40.0])
def test_ka_change_bar_labels_its_lower_half_however_far_it_reaches(reach):
    """Past −99.9 % the lower ticks read as the Ka ratio, so a bar spanning many decades is labelled to its end."""
    from gui.plotting.sensitivity_widget import _change_ticks

    ticks = _change_ticks(reach)

    for position, text in ticks:
        assert position == pytest.approx(np.log10(_ratio_of(text)), rel=1e-9, abs=1e-12)
    lower = sorted(-position / reach for position, _ in ticks if position <= 0)  # share of the half-bar, from zero
    assert lower[-1] >= 0.8
    assert np.max(np.diff(lower)) <= 0.5


@pytest.mark.parametrize('ka_scale', ['log₁₀', 'linear'])
def test_heatmap_colours_ka_on_the_plot_style_ka_scale(qapp, ka_scale):
    from gui.plotting.sensitivity_widget import SensitivityWidget

    result = _heatmap_result()
    grid = result.ka_grid['Ka_guest']
    w = SensitivityWidget()
    w.update_result(result)
    w.apply_style({'distribution': {'ka_scale': ka_scale}})
    _colour_by(w, 'Ka')

    (target,) = w._hover_targets
    expected = np.log10(grid) if ka_scale == 'log₁₀' else grid
    np.testing.assert_allclose(target['values'], expected)
    np.testing.assert_allclose(target['colour_bar'].values, (np.nanmin(expected), np.nanmax(expected)))
    (ticks,) = target['colour_bar'].axis._tickLevels
    by_label = dict((text, position) for position, text in ticks)
    for text, ka in (('1.9×10⁶', 1.9e6), ('2×10⁶', 2e6), ('2.1×10⁶', 2.1e6)):
        assert by_label[text] == pytest.approx(np.log10(ka) if ka_scale == 'log₁₀' else ka)


def test_heatmap_colours_r2(qapp):
    from gui.plotting.sensitivity_widget import SensitivityWidget

    result = _heatmap_result()
    w = SensitivityWidget()
    w.update_result(result)
    _colour_by(w, 'R²')

    (target,) = w._hover_targets
    np.testing.assert_allclose(target['values'], result.r2_grid)
    np.testing.assert_allclose(target['colour_bar'].values, (0.95, 0.995))
    (ticks,) = target['colour_bar'].axis._tickLevels
    assert [text for _, text in ticks] == ['0.95', '0.96', '0.97', '0.98', '0.99']


@pytest.mark.parametrize('stat', ['Ka change', 'Ka', 'R²'])
def test_colour_bar_ticks_use_the_style_tick_font(qapp, stat):
    """The colour bar's tick labels take the Plot Style's tick size, in ink, with room for the widest."""
    from PyQt6.QtGui import QFontMetrics

    from gui.plotting.plot_style import DEFAULT_STYLE
    from gui.plotting.sensitivity_widget import SensitivityWidget

    style = dict(DEFAULT_STYLE, distribution={**DEFAULT_STYLE['distribution'], 'tick_font_size': 17})
    w = SensitivityWidget()
    w.update_result(_heatmap_result())
    w.apply_style(style)
    _colour_by(w, stat)

    axis = w._hover_targets[0]['colour_bar'].axis
    font = axis.style['tickFont']
    assert font.pointSize() == 17
    assert axis.textPen().color().name() == '#52514e'
    (ticks,) = axis._tickLevels
    assert len(ticks) >= 3
    assert axis.style['tickTextWidth'] >= max(QFontMetrics(font).horizontalAdvance(text) for _, text in ticks)


def test_colour_choice_survives_new_results_and_restyles(qapp):
    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    w.update_result(_heatmap_result())
    _colour_by(w, 'R²')

    newer = _heatmap_result()
    newer.r2_grid = np.full((3, 3), 0.999)
    w.update_result(newer)
    w.apply_style({'distribution': {'ka_scale': 'linear', 'tick_font_size': 13}})

    assert w._colour_combo.currentText() == 'R²'
    np.testing.assert_allclose(w._hover_targets[0]['values'], newer.r2_grid)


def test_heatmap_readout_names_both_inputs_with_ka_change_and_r2(qapp):
    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    w.update_result(_heatmap_result())
    (target,) = w._hover_targets

    # Cell (x, y) = (-5 %, -5 %): Ka 1.8×10⁶ against a baseline of 2×10⁶, R² 0.95 under the floor.
    text = w._readout_html(target, 0, 0)
    assert 'Guest −5%, [Host]<sub>0</sub> −5%' in text
    assert '1.80×10⁶' in text
    assert 'change: −10%' in text
    assert 'R² = 0.9500 (below Min R²)' in text

    # The failed cell still names where it is.
    assert w._readout_html(target, 1, 2) == 'Guest 0%, [Host]<sub>0</sub> +5%<br>no fit could be produced'


def test_heatmap_readout_r2_never_reads_as_meeting_the_floor_it_misses(qapp):
    """A cell a hair below the Min R² reads below it, from the one shared R² formatter."""
    from gui.plotting.labels import fmt_r2
    from gui.plotting.sensitivity_widget import SensitivityWidget

    result = _heatmap_result()
    result.r2_grid[0, 0] = 0.98999
    w = SensitivityWidget()
    w.update_result(result)
    (target,) = w._hover_targets
    assert f'R² = {fmt_r2(0.98999, _FLOOR)} (below Min R²)' in w._readout_html(target, 0, 0)
    assert 'R² = 0.9900' not in w._readout_html(target, 0, 0)


def test_heatmap_axis_ticks_sit_at_the_cell_centres(qapp):
    """Each tick names a cell, so it stands at that cell's offset rather than on a round number between cells."""
    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    w.update_result(_heatmap_result())
    plot = w._hover_targets[0]['plot']
    for axis_name, offsets in (('bottom', _heatmap_result().x_offsets_pct), ('left', _heatmap_result().y_offsets_pct)):
        ((ticks, *_),) = [plot.getAxis(axis_name)._tickLevels]
        assert [value for value, _ in ticks] == [float(v) for v in offsets]


def test_colour_selector_shows_only_for_heatmaps(qapp):
    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    w.update_result(_heatmap_result())
    assert not w._colour_controls.isHidden()
    w.update_result(_sobol_result())
    assert w._colour_controls.isHidden()


def test_widget_progress_and_clear(qapp):
    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    w.show_running()
    assert w._stack.currentWidget() is w._progress_page
    w.set_progress(3, 10)
    assert w._progress_bar.value() == 3

    w.update_result(_sobol_result())
    w.clear()
    assert w._stack.currentWidget() is w._placeholder


def test_a_run_in_progress_counts_its_fits_and_carries_its_own_cancel(qapp):
    """The count and the Cancel button sit on the page the user is looking at, not in a panel off screen."""
    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    w.show_running()
    assert w._progress_bar.maximum() == 0  # nothing counted yet: an indeterminate bar
    assert 'Ka Sensitivity panel' not in w._progress_label.text()

    w.set_progress(1234, 6144)
    assert w._progress_label.text() == '1,234 of 6,144 fits'
    assert (w._progress_bar.value(), w._progress_bar.maximum()) == (1234, 6144)

    asked = []
    w.cancel_requested.connect(lambda: asked.append(True))
    w._cancel_button.click()
    assert asked == [True]

    # The page takes the request: the fits already running still land, and a
    # button that stays live with a rising count gives no sign it was pressed.
    assert not w._cancel_button.isEnabled()
    assert w._progress_label.text().startswith('Stopping')
    w.set_progress(1300, 6144)
    assert w._progress_label.text().startswith('Stopping')
    w.show_running()
    assert w._cancel_button.isEnabled()


def test_export_image_writes_the_whole_tab(tmp_path, qapp):
    """The picture carries the plots and the note below them; an empty tab says there is nothing to save.

    Only PNG: Qt's SVG painter drops the clip each plot keeps its curves inside,
    so a curve past its axes would be drawn across the key and the notes.
    """
    from PyQt6.QtCore import Qt

    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    with pytest.raises(ValueError, match='Run one'):
        w.export_image(str(tmp_path / 'empty.png'))

    w.update_result(_sobol_result())
    w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    w.resize(1000, 800)
    w.show()
    qapp.processEvents()
    path = tmp_path / 'sensitivity.png'
    w.export_image(str(path))
    assert path.stat().st_size > 0
    for unsupported in ('sensitivity.svg', 'sensitivity.pdf'):
        with pytest.raises(ValueError, match='cannot be written'):
            w.export_image(str(tmp_path / unsupported))
    w.close()


def test_the_sobol_chart_leaves_the_same_room_beside_its_first_and_last_bar(qapp):
    """The category axis pads both ends alike, so no group is drawn against the frame.

    The first and last groups are the ones a reader compares against the axis,
    and a bar touching the frame reads as one that ran off the scale.
    """
    from gui.plotting.sensitivity_widget import _BAR_HALF_WIDTH, _GROUP_OFFSET, SensitivityWidget

    result = _sobol_result()
    keys = list(result.sobol_s1['Ka_guest'])
    values = {key: 0.1 * (index + 1) for index, key in enumerate(keys)}
    result.sobol_s1 = result.sobol_st = {'Ka_guest': values}
    result.sobol_s1_ci = result.sobol_st_ci = {'Ka_guest': {k: (v - 0.02, v + 0.02) for k, v in values.items()}}
    w = SensitivityWidget()
    w.update_result(result)

    plot = next(p for p in _plots(w) if 'Sobol' in (p.titleLabel.text if p.titleLabel else ''))
    lo, hi = plot.getViewBox().viewRange()[0]
    first_bar = -_GROUP_OFFSET - _BAR_HALF_WIDTH
    last_bar = (len(keys) - 1) + _GROUP_OFFSET + _BAR_HALF_WIDTH

    assert first_bar - lo > 0
    assert (first_bar - lo) == pytest.approx(hi - last_bar)


def test_the_saved_heatmap_leaves_the_colour_selector_out(tmp_path, qapp):
    """The drop-down that chooses what the colour shows is not painted into the file.

    Each colour bar already names the statistic it carries, so the picture says
    what it shows without the control that picked it — and on macOS Qt draws no
    drop-down at all outside a window.
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor, QImage, QPalette

    from gui.plotting.sensitivity_widget import SensitivityWidget

    marker = QColor(255, 0, 255)
    w = SensitivityWidget()
    w.update_result(_heatmap_result())
    palette = w._colour_controls.palette()
    palette.setColor(QPalette.ColorRole.Window, marker)
    w._colour_controls.setPalette(palette)
    w._colour_controls.setAutoFillBackground(True)  # marks the strip the picture must not show
    w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    w.resize(1000, 800)
    w.show()
    qapp.processEvents()
    assert not w._colour_controls.isHidden()

    path = tmp_path / 'heatmap.png'
    w.export_image(str(path))

    image = QImage(str(path))
    assert not image.isNull()
    painted = {image.pixelColor(x, y).rgb() for y in range(image.height()) for x in range(0, image.width(), 40)}
    assert marker.rgb() not in painted
    assert not w._colour_controls.isHidden()  # still there for the next choice
    w.close()


def test_baseline_line_follows_its_own_style_not_the_median_line(qapp):
    """The histogram's baseline line takes the Ka Sensitivity style; the Distributions median style leaves it alone."""
    from PyQt6.QtGui import QColor

    from gui.plotting.plot_style import PlotStyleWidget
    from gui.plotting.sensitivity_widget import SensitivityWidget

    style_widget = PlotStyleWidget()
    w = SensitivityWidget()
    style_widget.style_changed.connect(w.apply_style)
    w.update_result(_sobol_result())

    def baseline_pen():
        (line,) = [item for plot in _plots(w) for item in plot.items if isinstance(item, pg.InfiniteLine)]
        return line.pen.color().getRgb(), line.pen.widthF()

    default_pen = baseline_pen()
    assert default_pen == ((220, 0, 0, 255), 2.5)

    style_widget._params['Distribution', 'Median line color'] = QColor(0, 0, 255, 255)
    style_widget._params['Distribution', 'Median line width'] = 6.0
    assert baseline_pen() == default_pen

    style_widget._params['Ka Sensitivity', 'Baseline line color'] = QColor(10, 120, 30, 255)
    style_widget._params['Ka Sensitivity', 'Baseline line width'] = 4.0
    assert baseline_pen() == ((10, 120, 30, 255), 4.0)


# ---------------------------------------------------------------------------
# Progress reporting
# ---------------------------------------------------------------------------


def _made_on(result: SensitivityResult, ms, conditions) -> SensitivityResult:
    """*result* with its baseline fit recording *ms* and *conditions*, as a real run's baseline does."""
    record = {'data_fingerprint': ms.fingerprint(), 'active_replica_ids': ms.active_replica_ids}
    return replace(result, baseline_fit=replace(result.baseline_fit, conditions=dict(conditions), metadata=record))


def _fake_run(n_fits: int, pause: float = 0.0):
    """Stand-in for ``run_sensitivity`` reporting *n_fits* finished fits, then a Sobol' result made on its inputs."""

    def run(ms, assay_cls, conditions, *args, progress, **kwargs):
        for done in range(1, n_fits + 1):
            time.sleep(pause)
            progress(done, n_fits)
        return _sobol_result() if ms is None else _made_on(_sobol_result(), ms, conditions)

    return run


def test_worker_throttles_progress_but_never_drops_the_last_count(qapp, monkeypatch):
    from gui import workers

    monkeypatch.setattr(workers, 'run_sensitivity', _fake_run(1000))
    worker = workers.SensitivityWorker(None, None, {}, None, None)
    events = []
    worker.progress.connect(lambda done, total: events.append((done, total)))
    worker.finished.connect(lambda result: events.append('finished'))

    worker.run()  # in this thread, so every signal is delivered on the spot

    # 1000 fits land within one interval: the first count starts the bar, the
    # last is held back and delivered before the result.
    assert events == [(1, 1000), (1000, 1000), 'finished']


def test_worker_reports_an_unexpected_failure_in_plain_words(qapp, monkeypatch):
    from gui import workers

    def fail(*args, **kwargs):
        raise RuntimeError('broadcast shapes (3,) (4,) mismatch in _jansen')

    monkeypatch.setattr(workers, 'run_sensitivity', fail)
    worker = workers.SensitivityWorker(None, None, {}, None, None)
    messages = []
    worker.error.connect(messages.append)

    worker.run()

    assert len(messages) == 1
    assert 'could not be completed' in messages[0]
    assert 'broadcast' not in messages[0] and '_jansen' not in messages[0]


def test_a_baseline_that_failed_per_replicate_names_the_replicates(qapp, monkeypatch):
    """The analysis tab explains a failed baseline the way the Fit Curve tab does."""
    from core.data_processing.measurement_set import MeasurementSet
    from core.pipeline.fit_pipeline import PerReplicaFitError
    from gui import workers

    def fail(*args, **kwargs):
        raise PerReplicaFitError(
            'None of the 2 replicates could be fitted on its own. There is no reference Ka for the '
            'analysis to compare against.',
            {'0': 'Its signal could not be fitted.', '1': 'Its signal could not be fitted.'},
        )

    monkeypatch.setattr(workers, 'run_sensitivity', fail)
    ms = MeasurementSet(concentrations=np.arange(3.0), signals=np.ones((2, 3)), replica_ids=('0', '1'))
    worker = workers.SensitivityWorker(ms, None, {}, None, None)
    messages = []
    worker.error.connect(messages.append)

    worker.run()

    assert len(messages) == 1
    assert 'no reference Ka' in messages[0]
    assert 'Replicate A: Its signal could not be fitted.' in messages[0]
    assert 'Replicate B: Its signal could not be fitted.' in messages[0]


def test_a_run_stopped_by_a_failed_refit_says_what_to_change(qapp, monkeypatch):
    """The analysis writes this one for the user, so the worker shows it as it stands."""
    from core.pipeline.sensitivity import SensitivityRunError
    from gui import workers

    def fail(*args, **kwargs):
        raise SensitivityRunError('The analysis stopped because one of the re-fits could not be completed. Retry.')

    monkeypatch.setattr(workers, 'run_sensitivity', fail)
    worker = workers.SensitivityWorker(None, None, {}, None, None)
    messages = []
    worker.error.connect(messages.append)

    worker.run()

    assert messages == ['The analysis stopped because one of the re-fits could not be completed. Retry.']


def _demo_session(monkeypatch):
    """A session with the demo IDA data and the smallest sample size; returns it and the list its warnings go to.

    The smallest size is long enough to ask for confirmation before starting; the prompt is answered Yes.
    """
    from PyQt6.QtWidgets import QMessageBox

    from gui.fitting_session import FittingSession

    warnings = []
    monkeypatch.setattr('gui.fitting_session.QMessageBox.warning', lambda *args: warnings.append(args))
    monkeypatch.setattr('gui.fitting_session.QMessageBox.question', lambda *args: QMessageBox.StandardButton.Yes)
    session = FittingSession()
    session._assay_panel.set_assay_type(AssayType.IDA)
    session._data_panel.load_file('data/IDA_system.txt')
    combo = session._sensitivity_panel._samples_combo
    combo.setCurrentIndex(combo.findData(1024))
    return session, warnings


def _wait_for_worker(session, qapp):
    """Wait for the running sensitivity worker to finish, then deliver its signals."""
    worker = session._sensitivity_worker
    deadline = time.monotonic() + 30
    while not worker.isFinished():
        assert time.monotonic() < deadline, 'timed out waiting for the sensitivity worker'
        qapp.processEvents()
        time.sleep(0.01)
    worker.wait()
    qapp.processEvents()


def test_throttled_run_fills_the_bar_and_estimates_time_left(qapp, monkeypatch):
    from gui import workers

    monkeypatch.setattr(workers, 'run_sensitivity', _fake_run(40, pause=0.01))
    session, warnings = _demo_session(monkeypatch)
    messages = []
    session.status_message.connect(messages.append)

    session.run_sensitivity()
    _wait_for_worker(session, qapp)

    bar = session._sensitivity_widget._progress_bar
    assert warnings == []
    assert session._state.sensitivity_result is not None
    assert (bar.value(), bar.maximum()) == (40, 40)
    assert any(message.startswith('Analysing') and message.endswith('left') for message in messages)
    # At the last count there is no time left to estimate.
    assert [message for message in messages if message.startswith('Analysing')][-1] == 'Analysing — 40 of 40'


def test_time_left_reads_as_plain_english():
    from gui.fitting_session import _format_remaining

    assert _format_remaining(0.3) == '1 second'
    assert _format_remaining(12) == '12 seconds'
    assert _format_remaining(60) == '1 minute'


def test_worker_delivers_a_held_back_count_as_soon_as_a_cancel_is_seen(qapp, monkeypatch):
    """After a cancel the driver waits for the fits still running; the bar does not wait with it."""
    from gui import workers

    events = []

    def run(*args, progress, should_cancel, **kwargs):
        for done in range(1, 51):
            progress(done, 1000)
        worker.cancel()
        assert should_cancel()
        events.append('driver waits for the running fits')
        return _sobol_result()

    monkeypatch.setattr(workers, 'run_sensitivity', run)
    worker = workers.SensitivityWorker(None, None, {}, None, None)
    worker.progress.connect(lambda done, total: events.append((done, total)))

    worker.run()

    assert events == [(1, 1000), (50, 1000), 'driver waits for the running fits']


def test_cancelled_run_says_it_stopped(qapp, monkeypatch):
    from gui import workers

    def run(*args, progress, should_cancel, **kwargs):
        done = 0
        while not should_cancel():
            done += 1
            progress(done, 1000)
            time.sleep(0.005)
        return _sobol_result()

    monkeypatch.setattr(workers, 'run_sensitivity', run)
    session, warnings = _demo_session(monkeypatch)
    messages = []
    session.status_message.connect(messages.append)

    session.run_sensitivity()
    session._cancel_sensitivity()
    _wait_for_worker(session, qapp)

    assert warnings == []
    # A cancel is an outcome, not an error. This result's baseline records no
    # data, so the tab hides it and the status bar says so in place of counts
    # from a result no tab is showing.
    assert messages[-1] == f'Sensitivity stopped but hidden — {session._state.sensitivity_note}'
    assert session._state.sensitivity_note is not None


def test_a_stopping_run_reads_the_same_on_the_page_and_in_the_status_bar(qapp, monkeypatch):
    """While a run stops, the counts still arriving stay off the status bar.

    The fits that were already running keep reporting until the analysis
    returns. The page says it is stopping, so a status bar counting those fits
    up beside it gives the window two answers at once.
    """
    from gui import workers
    from gui.plotting.sensitivity_widget import STOPPING_TEXT

    def run(*args, progress, should_cancel, **kwargs):
        progress(1, 1000)
        while not should_cancel():
            time.sleep(0.005)
        for done in (2, 3, 4):  # the fits that were already running
            progress(done, 1000)
        return _sobol_result()

    monkeypatch.setattr(workers, 'run_sensitivity', run)
    session, warnings = _demo_session(monkeypatch)
    messages = []
    session.status_message.connect(messages.append)

    session.run_sensitivity()
    session._sensitivity_widget._cancel_button.click()  # the button the user presses
    page_while_stopping = session._sensitivity_widget._progress_label.text()
    stopping_from = len(messages) - 1
    _wait_for_worker(session, qapp)

    assert warnings == []
    assert page_while_stopping == STOPPING_TEXT
    assert messages[stopping_from] == STOPPING_TEXT
    # The held-back counts arrive as the page's own sentence, not as a count.
    assert messages.count(STOPPING_TEXT) > 1
    assert not [message for message in messages[stopping_from:] if message.startswith('Analysing')]


def test_failed_run_takes_the_tab_off_the_progress_page(qapp, monkeypatch):
    """After an error the tab shows what it showed before the run, not a bar that looks busy."""
    from gui import workers

    def failing(*args, progress, **kwargs):
        progress(1, 97)
        raise ValueError('The unperturbed (baseline) fit did not converge.')

    session, warnings = _demo_session(monkeypatch)
    widget = session._sensitivity_widget

    monkeypatch.setattr(workers, 'run_sensitivity', failing)
    session.run_sensitivity()
    _wait_for_worker(session, qapp)
    assert len(warnings) == 1
    assert widget._stack.currentWidget() is widget._placeholder

    monkeypatch.setattr(workers, 'run_sensitivity', _fake_run(5))
    session.run_sensitivity()
    _wait_for_worker(session, qapp)
    earlier = session._state.sensitivity_result
    monkeypatch.setattr(workers, 'run_sensitivity', failing)
    session.run_sensitivity()
    _wait_for_worker(session, qapp)
    assert len(warnings) == 2
    assert widget._stack.currentWidget() is widget._results_host
    assert widget._result is earlier


# ---------------------------------------------------------------------------
# Fitted parameters across the samples (the summary under the plot tabs)
# ---------------------------------------------------------------------------


def _cell_texts(table) -> list[list[str]]:
    return [[table.cellWidget(r, c).text() for c in range(table.columnCount())] for r in range(table.rowCount())]


def _samples_summary(result, fit=None):
    """A summary widget in the samples view of *result*, with *fit* as the fit on the other tabs."""
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    if fit is not None:
        widget.update_result(fit)
    widget.set_sensitivity(result)
    widget.show_samples(True)
    return widget


def _caption_of(result, fit=None) -> str:
    widget = _samples_summary(result, fit)
    return widget._caption.text()


def _value_cells(rows) -> list[list[str]]:
    """Every column but the label, as the shared parameter table renders *rows*."""
    from gui.plotting.fit_summary_widget import ParameterTable

    table = ParameterTable()
    table.show_rows(rows)
    return [row[1:] for row in _cell_texts(table)]


def _over_samples(result, mask) -> list[list[str]]:
    samples = {key: values[mask] for key, values in result.sample_params.items()}
    return _value_cells(summarize_parameters(replace(result.baseline_fit, parameter_samples=samples)))


def _in_samples_view(widget) -> bool:
    from gui.plotting.fit_summary_widget import _REPORT_TITLE

    return widget._params_group.title() == _REPORT_TITLE


def test_samples_view_summarises_every_fitted_sample_around_the_baseline_fit(qapp):
    """The estimate is the baseline fit; the spread covers all fitted samples, never the baseline's own pool."""
    result = _sobol_result()
    widget = _samples_summary(result)
    fitted = np.isfinite(result.sample_ka['Ka_guest'])
    passing = fitted & (result.sample_r2 >= _FLOOR)

    cells = _cell_texts(widget._table)
    shown = [row[1:] for row in cells]
    assert _in_samples_view(widget)
    assert shown == _over_samples(result, fitted)
    assert shown != _over_samples(result, passing)
    assert shown != _value_cells(summarize_parameters(result.baseline_fit))

    # The log₁₀ Ka row by hand: its estimate from the baseline fit, its range from the samples.
    (log_row,) = [row[1:] for row in cells if row[0].startswith('log₁₀')]
    log_ka = np.log10(result.sample_ka['Ka_guest'][fitted])
    assert log_row[0] == f'{np.log10(2e8):.3f}'
    assert log_row[4] == f'[{log_ka.min():.3f}, {log_ka.max():.3f}]'


def test_samples_view_counts_the_samples_below_the_floor(qapp):
    result = _sobol_result()
    text = _caption_of(result)
    assert text.startswith('The estimate is the fit this analysis makes with the inputs as you entered them')
    assert (
        f'the 39 samples that have a fit, including the {result.n_below_floor} whose best fit falls below '
        'the Min R² this analysis used (0.99)'
    ) in text
    assert text.endswith('1 of 40 samples could not be fitted and is left out.')

    every_fit_passes = replace(
        result,
        sample_params={key: np.nan_to_num(values, nan=1.0) for key, values in result.sample_params.items()},
        sample_r2=np.full(40, 0.999),
        n_below_floor=0,
    )
    text = _caption_of(every_fit_passes)
    assert 'all 40 samples, and the best fit of every one meets the Min R² this analysis used (0.99)' in text
    assert 'left out' not in text


def test_samples_view_does_not_call_the_samples_a_stopped_run_never_reached_unfittable(qapp):
    result = replace(_sobol_result(), stopped=True)
    assert result.n_success < result.n_total
    assert (
        '1 of 40 samples have no fit, either because the analysis was stopped before reaching them or because '
        'they could not be fitted'
    ) in _caption_of(result)

    every_finished_fit_succeeded = replace(result, n_success=result.n_total)
    text = _caption_of(every_finished_fit_succeeded)
    assert '1 of 40 samples was not fitted before the analysis was stopped and is left out.' in text
    assert 'could not be fitted' not in text


def test_samples_view_describes_the_samples_under_fit_quality(qapp):
    """Fit Quality counts the fitted samples and those below the floor, and gives their R² median and range."""
    result = _sobol_result()
    widget = _samples_summary(result, fit=_summary_fit())
    fitted = np.isfinite(result.sample_r2)
    r2 = result.sample_r2[fitted]
    form = widget._quality_form

    assert widget._rep_row.isHidden()
    assert widget._fitted_label.text() == '39 / 40'
    assert widget._below_label.text() == f'{int(np.sum(r2 < _FLOOR))} of 39  (Min R² used: 0.99)'
    assert widget._median_r2_label.text() == f'{np.median(r2):.4f}'
    assert widget._r2_range_label.text() == f'[{r2.min():.4f}, {r2.max():.4f}]'
    assert all(form.isRowVisible(label) for label in widget._sample_rows)
    assert not any(form.isRowVisible(label) for label in widget._fit_rows)


def test_an_r2_just_below_one_never_reads_as_a_perfect_fit(qapp):
    r2 = np.full(40, 0.995)
    r2[[0, 1]] = 0.9999870, 1.0
    widget = _samples_summary(replace(_sobol_result(), sample_r2=r2))
    assert widget._r2_range_label.text() == '[0.9950, 1.0000]'
    r2[1] = 0.99
    widget = _samples_summary(replace(_sobol_result(), sample_r2=r2))
    assert widget._r2_range_label.text() == '[0.9900, 0.999987]'


def test_an_r2_just_below_the_floor_never_reads_as_meeting_it(qapp):
    """A sample counted below Min R² shows digits enough to read below it, in the range and the median."""
    r2 = np.full(40, 0.98996)
    r2[:10] = 0.995
    widget = _samples_summary(replace(_sobol_result(), sample_r2=r2))
    assert widget._below_label.text().startswith('30 of 39')
    assert widget._r2_range_label.text() == '[0.98996, 0.9950]'
    assert widget._median_r2_label.text() == '0.98996'


def test_the_floor_named_is_the_one_the_analysis_ran_with(qapp):
    """The run's floor is never attributed to the Fit panel, whose Min R² can change after the run."""
    widget = _samples_summary(_sobol_result())
    assert 'Fit panel' not in widget._caption.text()
    assert 'Fit panel' not in widget._below_label.text()


@pytest.mark.parametrize('degenerate', [(), ('I0',), ('I0', 'I_dye_free', 'I_dye_bound')])
def test_samples_view_stars_the_degenerate_signal_parameters(qapp, degenerate):
    from gui.plotting.labels import fmt_param

    result = replace(_sobol_result(), degenerate_keys=degenerate)
    widget = _samples_summary(result)
    keys = [row.key for row in summarize_parameters(result.baseline_fit)]
    labels = [widget._table.cellWidget(r, 0) for r in range(widget._table.rowCount())]

    assert [label.text().endswith('*') for label in labels] == [key in degenerate for key in keys]
    assert [label.toolTip().startswith('Marginal summary') for label in labels] == [key in degenerate for key in keys]
    assert widget._footnote.isHidden() == (not degenerate)
    if degenerate:
        assert widget._footnote.text().startswith('* Marginal summary. The data fix only a combination of')
        assert all(fmt_param(key) in widget._footnote.text() for key in degenerate)


def _fit_like_the_baseline(**changes):
    """The baseline fit re-made as a normal fit: same data, inputs, bounds and replicate handling, its own pool."""
    return replace(_baseline_fit(), id='normal-fit', **changes)


def test_samples_view_says_the_estimate_matches_the_fit_on_the_other_tabs(qapp):
    text = _caption_of(_sobol_result(), fit=_fit_like_the_baseline())
    assert 'Its unstarred estimates match the fit on the Fit Curve tab to the digits shown.' in text


def test_samples_view_names_the_estimate_that_differs_from_a_like_for_like_fit(qapp):
    fit = _fit_like_the_baseline(parameters={**_baseline_fit().parameters, 'Ka_guest': Q_(2.1e8, '1/M')})
    text = _caption_of(_sobol_result(), fit=fit)
    assert (
        'Its estimate of <b>K<sub>a(G)</sub></b> differs from the fit on the Fit Curve tab although the two use the '
        'same data, inputs, bounds and replicate handling'
    ) in text


@pytest.mark.parametrize(
    ('ours', 'theirs', 'reason'),
    [
        (
            {},
            {'uncertainty_source': 'replicate'},
            'because this analysis fits the average of the replicates, while that fit uses each replicate separately.',
        ),
        (
            {'uncertainty_source': 'replicate'},
            {},
            'because this analysis fits each replicate separately, while that fit uses the average of the replicates.',
        ),
        ({}, {'metadata': {'data_fingerprint': 'another'}}, 'because that fit was not made on the data as loaded now.'),
        (
            {'metadata': {'active_replica_ids': ['A', 'B']}},
            {'metadata': {'active_replica_ids': ['A', 'B', 'C']}},
            'because the two use different replicates.',
        ),
        ({}, {'conditions': {'h0': Q_(4.3, 'µM')}}, 'because the two use different inputs.'),
        (
            {},
            {'fit_config': {'custom_bounds': {'Ka_guest': [1.0, 1e9, '1 / molar']}}},
            'because the two use different parameter bounds.',
        ),
        ({}, {'assay_type': 'GDA'}, 'because the two are for different assay types.'),
        (
            {'metadata': {'active_replica_ids': ['A', 'B']}},
            {'metadata': {'active_replica_ids': ['A', 'B'], 'replica_ids_fit': ['B'], 'replica_failures': {'A': 'x'}}},
            'because the two use different replicates.',
        ),
        (
            {},
            {'representative_index': 2, 'metadata': {'fitted_representative_index': 1}},
            'because that fit shows an attempt you picked instead of the one the fit chose.',
        ),
    ],
    ids=[
        'average-vs-per-replica',
        'per-replica-vs-average',
        'data',
        'replicates',
        'inputs',
        'bounds',
        'assay',
        'fit-left-out-a-replicate-the-analysis-used',
        'picked-representative',
    ],
)
def test_samples_view_names_why_the_estimate_can_differ_from_the_fit_on_the_other_tabs(qapp, ours, theirs, reason):
    result = replace(_sobol_result(), baseline_fit=replace(_baseline_fit(), **ours))
    text = _caption_of(result, fit=_fit_like_the_baseline(**theirs))
    assert f'It can differ from the fit on the Fit Curve tab {reason}' in text
    assert 'match the fit' not in text
    assert 'own search for the best fit' not in text


def test_both_leaving_out_the_same_replicate_is_named_once(qapp):
    """Replicates the analysis and the fit both leave out are no difference between them: named once, never per fit."""
    record = {
        'active_replica_ids': ['A', 'B', 'C'],
        'replica_ids_fit': ['B', 'C'],
        'replica_failures': {'A': 'None of its fit attempts reached the minimum R² of 0.99.'},
    }
    per_replica = {'uncertainty_source': 'replicate', 'metadata': record}
    result = replace(_sobol_result(), baseline_fit=replace(_baseline_fit(), **per_replica))
    text = _caption_of(result, fit=_fit_like_the_baseline(**per_replica))
    assert 'Its unstarred estimates match the fit on the Fit Curve tab to the digits shown.' in text
    assert text.count('Both leave out replicate A, as neither found an acceptable fit for it.') == 1
    assert 'leaves out' not in text


def test_picking_another_representative_is_named_as_why_the_estimate_differs(qapp, monkeypatch):
    """A representative picked on the Fit Curve tab is named, never passed off as a separate search for the best fit."""
    from gui import workers

    monkeypatch.setattr(workers, 'run_sensitivity', _fake_run(3))
    session, warnings = _demo_session(monkeypatch)
    ms = session._state.measurement_set
    fit = _fit_like_the_baseline(
        representative_index=1,
        x_fit=Q_(_baseline_fit().x_fit, 'M'),
        y_fit=Q_(_baseline_fit().y_fit, 'au'),
        conditions=session._assay_panel.current_conditions(),
        metadata={'data_fingerprint': ms.fingerprint(), 'active_replica_ids': ms.active_replica_ids},
    )
    session._state.held_fit_results = [fit]
    session._show_results(force=True)
    session.run_sensitivity()
    _wait_for_worker(session, qapp)
    summary = session._summary_widget
    assert 'match the fit on the Fit Curve tab' in summary._caption.text()

    session._on_representative_selected(2)
    assert fit.metadata['fitted_representative_index'] == 1
    text = summary._caption.text()
    assert 'because that fit shows an attempt you picked instead of the one the fit chose.' in text
    assert 'own search for the best fit' not in text

    session._on_representative_selected(1)
    assert 'match the fit on the Fit Curve tab' in summary._caption.text()
    assert warnings == []


def test_sensitivity_run_uses_the_bounds_set_in_the_bounds_panel(qapp, monkeypatch):
    """The analysis fits within the same parameter bounds as the fit on the Fit Curve tab."""
    from gui import workers

    seen = {}

    def capture(ms, assay_cls, conditions, fit_config, sens_config, **kwargs):
        seen['bounds'] = fit_config.custom_bounds
        return _sobol_result()

    monkeypatch.setattr(workers, 'run_sensitivity', capture)
    session, warnings = _demo_session(monkeypatch)
    row = session._bounds_panel._rows['I0']
    lo, _ = row.values()
    row.set_values(lo, 5000.0)
    bounds = session._bounds_panel.current_bounds()
    assert bounds['I0'][1] == Q_(5000.0, 'au')

    session.run_sensitivity()
    _wait_for_worker(session, qapp)
    assert warnings == []
    assert seen['bounds'] == bounds


def test_same_inputs_in_other_display_units_are_the_same_inputs(qapp):
    result = replace(_sobol_result(), baseline_fit=replace(_baseline_fit(), conditions={'h0': Q_(4.3e-6, 'M')}))
    fit = _fit_like_the_baseline(conditions={'h0': Q_(4.3, 'µM')})
    assert 'It can differ' not in _caption_of(result, fit=fit)


@pytest.mark.parametrize(
    ('result', 'why'),
    [
        (None, 'Run a sensitivity analysis with Sensitivity indices to see the fitted parameters across its samples'),
        (replace(_heatmap_result(), baseline_fit=_baseline_fit()), 'The last analysis is a heatmap.'),
        (replace(_sobol_result(), baseline_fit=None), 'does not include the fitted parameters of each sample'),
        (replace(_sobol_result(), sample_params=None), 'does not include the fitted parameters of each sample'),
    ],
    ids=['no-run', 'heatmap', 'no-baseline', 'no-sample-fits'],
)
def test_without_samples_to_summarise_the_fit_shows_with_a_note(qapp, result, why):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    fit_view = FitSummaryWidget()
    fit_view.update_result(_summary_fit())
    widget = _samples_summary(result, fit=_summary_fit())

    assert not _in_samples_view(widget)
    assert _cell_texts(widget._table) == _cell_texts(fit_view._table)
    assert not widget._rep_row.isHidden()
    assert widget._footnote.isHidden()
    assert why in widget._caption.text()
    assert widget._caption.text().endswith('The table shows the fit from the Fit Curve tab instead.')

    empty = _samples_summary(result)
    assert empty._table.rowCount() == 0
    assert 'instead' not in empty._caption.text()


def test_a_heatmap_still_running_is_named_as_why_there_is_no_summary(qapp):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(_summary_fit())
    widget.show_samples(True)
    widget.show_running(SensitivityMode.HEATMAP)
    assert not _in_samples_view(widget)
    assert widget._caption.text().startswith('The analysis now running is a heatmap.')
    widget.set_sensitivity(_sobol_result())
    assert _in_samples_view(widget)


def test_switching_views_restores_the_fit_cell_for_cell(qapp):
    """Out of the samples view every trace of it is gone: title, caption, footnote, stars, Fit Quality rows."""
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    fit_view = FitSummaryWidget()
    fit_view.update_result(_summary_fit())
    widget = _samples_summary(_sobol_result(), fit=_summary_fit())

    for _ in range(2):
        widget.show_samples(False)
        assert _cell_texts(widget._table) == _cell_texts(fit_view._table)
        assert widget._params_group.title() == 'Fitted Parameters'
        assert not widget._rep_row.isHidden() and widget._rep_combo.count() == 3
        assert widget._caption.isHidden() and widget._footnote.isHidden()
        assert all(widget._quality_form.isRowVisible(label) for label in widget._fit_rows)
        assert widget._r2_label.text() == '0.9980'
        widget.show_samples(True)
        assert _in_samples_view(widget)
        assert widget._rep_row.isHidden()

    # A new fit arriving in the samples view keeps the view and is what the caption compares against.
    widget.update_result(_fit_like_the_baseline())
    assert _in_samples_view(widget)
    assert 'match the fit on the Fit Curve tab' in widget._caption.text()


def test_clearing_the_fit_empties_the_selector(qapp):
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(_summary_fit())
    widget.clear()
    assert widget._table.rowCount() == 0
    assert (widget._rep_combo.count(), widget._rep_combo.isEnabled()) == (1, False)
    assert widget._r2_label.text() == '—'


def _summary_fit():
    """A normal GDA fit with a three-fit multistart pool, the second of them reported."""
    x = np.linspace(0.0, 1e-4, 20)
    return FitResult(
        parameters={
            'Ka_guest': Q_(1.1e6, '1/M'),
            'I0': Q_(90.0, 'au'),
            'I_dye_free': Q_(5.1e4, 'au/M'),
            'I_dye_bound': Q_(8.1e4, 'au/M'),
        },
        rmse=0.005,
        r_squared=0.998,
        n_passing=3,
        n_total=10,
        x_fit=x,
        y_fit=x * 1.05,
        assay_type='GDA',
        model_name='equilibrium_4param',
        parameter_samples={
            'Ka_guest': np.array([1.0e6, 1.1e6, 0.9e6]),
            'I0': np.array([100.0, 90.0, 110.0]),
            'I_dye_free': np.array([5.0e4, 5.1e4, 4.9e4]),
            'I_dye_bound': np.array([8.0e4, 8.1e4, 7.9e4]),
        },
        quality_samples={'rmse': np.array([0.006, 0.005, 0.007]), 'r_squared': np.array([0.997, 0.998, 0.996])},
        representative_index=1,
    )


def test_fit_summary_renders_a_normal_fit_cell_for_cell(qapp):
    """The shared Fit Summary shows the representative fit and its own pool's statistics, with units."""
    from gui.plotting.fit_summary_widget import FitSummaryWidget

    widget = FitSummaryWidget()
    widget.update_result(_summary_fit())
    assert _cell_texts(widget._table) == [
        [
            '<b>K<sub>a(G)</sub></b>',
            '1.1×10<sup>6</sup>',
            '1×10<sup>6</sup> ± 1×10<sup>5</sup>',
            '1×10<sup>6</sup> ± 1×10<sup>5</sup>',
            '[9.32×10<sup>5</sup>, 1.07×10<sup>6</sup>]',
            '[9×10<sup>5</sup>, 1.1×10<sup>6</sup>]',
            'M<sup>−1</sup>',
        ],
        [
            'log₁₀(<b>K<sub>a(G)</sub></b> / M<sup>−1</sup>)',
            # Fixed decimals, so the value is never coarser than the spread beside it.
            '6.041',
            '6.000 ± 0.041',
            '5.999 ± 0.044',
            '[5.969, 6.028]',
            '[5.954, 6.041]',
            '—',
        ],
        ['<b>I<sub>0</sub></b>', '90', '100 ± 10', '100 ± 10', '[93.2, 107]', '[90, 110]', 'a.u.'],
        [
            '<b>I<sub>D</sub></b>',
            '5.1×10<sup>4</sup>',
            '5×10<sup>4</sup> ± 1×10<sup>3</sup>',
            '5×10<sup>4</sup> ± 1×10<sup>3</sup>',
            '[4.93×10<sup>4</sup>, 5.07×10<sup>4</sup>]',
            '[4.9×10<sup>4</sup>, 5.1×10<sup>4</sup>]',
            'a.u./M',
        ],
        [
            '<b>I<sub>HD</sub></b>',
            '8.1×10<sup>4</sup>',
            '8×10<sup>4</sup> ± 1×10<sup>3</sup>',
            '8×10<sup>4</sup> ± 1×10<sup>3</sup>',
            '[7.93×10<sup>4</sup>, 8.07×10<sup>4</sup>]',
            '[7.9×10<sup>4</sup>, 8.1×10<sup>4</sup>]',
            'a.u./M',
        ],
    ]


def _on_tab(session, name: str) -> None:
    tabs = session._plot_tabs
    tabs.setCurrentIndex(next(i for i in range(tabs.count()) if tabs.tabText(i) == name))


def test_summary_follows_the_plot_tab(qapp, monkeypatch):
    """On Ka Sensitivity the summary shows the run's samples; on every other tab the fit, cell for cell."""
    from gui import workers

    monkeypatch.setattr(workers, 'run_sensitivity', _fake_run(3))
    session, warnings = _demo_session(monkeypatch)
    summary = session._summary_widget
    summary.update_result(_summary_fit())
    before = _cell_texts(summary._table)

    session.run_sensitivity()
    _wait_for_worker(session, qapp)

    result = session._state.sensitivity_result
    assert warnings == []
    assert not hasattr(session._sensitivity_widget, '_report')
    assert session._plot_tabs.currentWidget() is session._sensitivity_widget
    assert _in_samples_view(summary)
    assert [row[1:] for row in _cell_texts(summary._table)] == _over_samples(
        result, np.isfinite(result.sample_ka['Ka_guest'])
    )
    for name in ('Fit Curve', 'Distributions', 'Identifiability'):
        _on_tab(session, name)
        assert not _in_samples_view(summary)
        assert _cell_texts(summary._table) == before
        assert not summary._rep_row.isHidden()
        _on_tab(session, 'Ka Sensitivity')
        assert _in_samples_view(summary)
        assert summary._rep_row.isHidden()


def test_summary_never_shows_a_run_that_is_not_the_tabs(qapp, monkeypatch):
    """A new run, a failed one, a heatmap and new or cleared data all leave the summary matching the tab."""
    from gui import workers

    def failing(*args, progress, **kwargs):
        raise ValueError('The unperturbed (baseline) fit did not converge.')

    session, warnings = _demo_session(monkeypatch)
    summary = session._summary_widget

    monkeypatch.setattr(workers, 'run_sensitivity', _fake_run(3))
    session.run_sensitivity()
    _wait_for_worker(session, qapp)
    earlier = session._state.sensitivity_result
    assert summary._sensitivity is earlier and _in_samples_view(summary)

    # While a run is going, the earlier run's statistics are gone; a failure brings them back with the tab.
    monkeypatch.setattr(workers, 'run_sensitivity', failing)
    session.run_sensitivity()
    assert summary._sensitivity is None and not _in_samples_view(summary)
    assert summary._caption.text().startswith('The sensitivity analysis is still running.')
    _wait_for_worker(session, qapp)
    assert len(warnings) == 1
    assert session._sensitivity_widget._result is earlier
    assert summary._sensitivity is earlier and _in_samples_view(summary)

    monkeypatch.setattr(
        workers,
        'run_sensitivity',
        lambda ms, cls, conditions, *a, progress, **k: _made_on(
            replace(_heatmap_result(), baseline_fit=_baseline_fit()), ms, conditions
        ),
    )
    session.run_sensitivity()
    _wait_for_worker(session, qapp)
    assert not _in_samples_view(summary)
    assert summary._caption.text().startswith('The last analysis is a heatmap.')

    session._data_panel.load_file('data/IDA_system.txt')
    assert session._state.sensitivity_result is None
    assert session._sensitivity_widget._stack.currentWidget() is session._sensitivity_widget._placeholder
    assert summary._sensitivity is None
    assert summary._caption.text().startswith('Run a sensitivity analysis with Sensitivity indices')

    monkeypatch.setattr(workers, 'run_sensitivity', _fake_run(3))
    session.run_sensitivity()
    _wait_for_worker(session, qapp)
    assert _in_samples_view(summary)
    session._data_panel.data_cleared.emit()
    assert session._state.sensitivity_result is None
    assert summary._sensitivity is None and not _in_samples_view(summary)


def test_new_data_discards_a_run_still_going(qapp, monkeypatch):
    """A run computed on the old data never reaches the tab or the summary once new data is loaded."""
    from gui import workers

    def slow(*args, progress, should_cancel, **kwargs):
        while not should_cancel():
            time.sleep(0.005)
        return _sobol_result()

    monkeypatch.setattr(workers, 'run_sensitivity', slow)
    session, warnings = _demo_session(monkeypatch)
    session.run_sensitivity()
    worker = session._sensitivity_worker

    session._data_panel.load_file('data/IDA_system.txt')
    worker.wait()
    qapp.processEvents()

    assert warnings == []
    assert session._sensitivity_worker is None
    assert session._state.sensitivity_result is None
    assert session._summary_widget._sensitivity is None
    assert session._sensitivity_widget._stack.currentWidget() is session._sensitivity_widget._placeholder
