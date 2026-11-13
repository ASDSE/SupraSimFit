"""GUI smoke tests for the Ka-sensitivity panel and widget.

Pins the wiring the compute-layer tests can't reach:

- :class:`SensitivityPanel` rebuilds its per-input uncertainty rows (titrant +
  every concentration / binding-constant condition, including ``Ka_dye``) when
  the assay type changes, hides the heatmap controls outside heatmap mode, and
  disables itself for ``DYE_ALONE``.
- :class:`SensitivityWidget` draws each Sobol index with a whisker spanning
  its confidence interval, the legend naming it, one Ka vs input panel per varied
  input with the samples that have no fit left out, each panel opening on the
  input's range as entered (± the farthest sampled offset for a σ input), counts
  the samples with no fit in a note, names the indices one way, gives a model
  with two binding constants a row of panels and a map per constant, and
  restyles/clears cleanly.
- The heatmap colours each cell by the chosen statistic (Ka change by default,
  symmetric in the log ratio to the baseline Ka; Ka on the Plot Style's Ka
  scale; R²), labels its colour bar in the style's tick font, keeps the choice
  across new results and restyles, and names both inputs in its hover readout.
- The budget says when fits ran to the edge of the Ka bounds, counting a share
  of the samples there above the numbers it keeps; a constant the run withholds
  (baseline on a bound, open interval, homogeneity identity broken) gets the
  reason in place of its budget and no number at all. The page says once that
  it propagates the stated uncertainties, and how that differs from the
  input-aware interval; the Variance column adds up to the square of the spread,
  and an interval is printed to the figures that tell it from its estimate.
- A stopped run is counted in the sample blocks it kept, once.
- The summary under the plot tabs follows the tab: the samples view on Ka
  Sensitivity, the fit on every other tab, and a new run, a failed run, a
  heatmap and new or cleared data never leave it stale. What that view shows is
  pinned by ``test_fit_summary_widget.py``.
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
from core.pipeline.budget import Budget, BudgetRow, WhatIf  # noqa: E402
from core.pipeline.fit_pipeline import FitResult  # noqa: E402
from core.pipeline.inputs import (  # noqa: E402
    ADDITIONS,
    TITRANT,
    AdditionError,
    ErrorModel,
    InputSpec,
    SharedSource,
    shared_key,
)
from core.pipeline.sensitivity import (  # noqa: E402
    _SOBOL_BLOCKS,
    SensitivityConfig,
    SensitivityMode,
    SensitivityResult,
)
from core.units import Q_  # noqa: E402

# ---------------------------------------------------------------------------
# SensitivityPanel
# ---------------------------------------------------------------------------


def test_the_heatmap_axes_offer_the_inputs_the_uncertainty_panel_names(qapp):
    """A heatmap sweeps two of the assay's inputs, so its axes are the rows of the panel that states them."""
    from gui.widgets.input_uncertainty_panel import InputUncertaintyPanel
    from gui.widgets.sensitivity_panel import SensitivityPanel

    inputs, panel = InputUncertaintyPanel(), SensitivityPanel()

    for assay_type, keys in (
        (AssayType.IDA, {TITRANT, 'Ka_dye', 'h0', 'd0'}),
        (AssayType.GDA, {TITRANT, 'Ka_dye', 'h0', 'g0'}),
        # A single-condition assay: just the titrant + its one fixed concentration.
        (AssayType.DBA_HtoD, {TITRANT, 'fixed_conc'}),
    ):
        inputs.set_assay_type(assay_type)
        panel.set_assay_type(assay_type)
        panel.set_inputs(inputs.input_labels())

        assert set(inputs.input_labels()) == keys
        offered = {panel._x_combo.itemData(i): panel._x_combo.itemText(i) for i in range(panel._x_combo.count())}
        assert offered == inputs.input_labels()


# ---------------------------------------------------------------------------
# SensitivityWidget
# ---------------------------------------------------------------------------


_INPUTS = ('Ka_dye', 'h0', TITRANT)


def _baseline_fit():
    """The IDA fit with the inputs as entered, which every sample is compared against."""
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
        x_fit=x,
        y_fit=x,
        assay_type='IDA',
        model_name='equilibrium_4param',
        degenerate_keys=('I0', 'I_dye_free', 'I_dye_bound'),
    )


#: The budget of the IDA run below, in round numbers: a variance of 0.007056
#: decades² is a spread of exactly 0.084 decades, and the ends of its interval,
#: 0.006561 and 0.007569, are exactly 0.081 and 0.087 decades — so what the
#: header line should read is known without repeating the widget's arithmetic.
_VARIANCE = 0.007056
_BUDGET = Budget(
    variance=_VARIANCE,
    variance_ci=(0.006561, 0.007569),
    rows=(
        BudgetRow('Ka_dye', 0.05 * _VARIANCE, (2e-4, 5e-4), 0.081873, (0.079, 0.084), 0.31),
        BudgetRow('h0', 0.2 * _VARIANCE, (1.1e-3, 1.7e-3), 0.075132, (0.072, 0.078), -1.2),
        BudgetRow(TITRANT, 0.6 * _VARIANCE, (3.8e-3, 4.7e-3), 0.053126, (0.050, 0.056), 0.95),
    ),
)
#: Every perturbable input of the IDA assay, the two that are not sources of
#: their own included, as a run's elasticity refits report them.
_ELASTICITY = {'Ka_dye': 0.31, 'h0': -1.2, 'd0': 0.62, TITRANT: 0.95}


def _two_ka_budget() -> Budget:
    """A budget for a constant of the 1:2 model: two sources, neither dominant."""
    return Budget(
        variance=0.01,
        variance_ci=(0.008, 0.012),
        rows=(
            BudgetRow('h0', 0.004, (0.003, 0.005), 0.0775, (0.07, 0.085), 0.4),
            BudgetRow(TITRANT, 0.004, (0.003, 0.005), 0.0775, (0.07, 0.085), 0.4),
        ),
    )


def _sobol_result():
    """Three varied inputs, 40 A+B samples, sample 5 unfitted."""
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
    # Each sample's place on the Identifiability tab's axis: the objective its
    # fit minimised, a different number from the unweighted R² beside it.
    profile_r2 = r2 + 0.002
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
        config=SensitivityConfig(
            SensitivityMode.SOBOL, n // 2, ErrorModel(specs={k: InputSpec.sigma_pct(5.0) for k in _INPUTS}), seed=0
        ),
        seed_used=0,
        sobol_s1={'Ka_guest': s1},
        sobol_st={'Ka_guest': st},
        sobol_s1_ci={'Ka_guest': {k: (v - 0.03, v + 0.1) for k, v in s1.items()}},
        sobol_st_ci={'Ka_guest': {k: (v - 0.04, v + 0.2) for k, v in st.items()}},
        sample_offsets_pct=offsets,
        sample_ka={'Ka_guest': ka},
        # As a run records it: the A and the B sample of a design row are kept
        # or dropped together, so sample 5 takes its partner 25 with it.
        sample_usable={'Ka_guest': np.tile(np.isfinite(ka[: n // 2]) & np.isfinite(ka[n // 2 :]), 2)},
        sample_r2=r2,
        sample_profile_r2=profile_r2,
        baseline_fit=_baseline_fit(),
        sample_params={'Ka_guest': ka, **signal},
        degenerate_keys=('I0', 'I_dye_free', 'I_dye_bound'),
        budget={'Ka_guest': _BUDGET},
        elasticity={'Ka_guest': _ELASTICITY},
        sources=_INPUTS,
        source_inputs={key: (key,) for key in _INPUTS},
        n_planned=n * (len(_INPUTS) + 2) + 2 * len(_INPUTS),
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
            SensitivityMode.HEATMAP,
            1,
            ErrorModel(specs={TITRANT: InputSpec.sigma_pct(5.0), 'h0': InputSpec.sigma_pct(5.0)}),
            x_key=TITRANT,
            y_key='h0',
            n_steps=3,
        ),
        seed_used=0,
        r2_grid=r2,
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


_TWO_KA_INPUTS = ('h0', TITRANT)


def _two_ka_result(mode: SensitivityMode = SensitivityMode.SOBOL) -> SensitivityResult:
    """A host–guest 1:2 run: the analysis reports both binding constants of the model."""
    rng = np.random.default_rng(2)
    n = 20
    keys = ('Ka_HG', 'Ka_HG2')
    baseline = {'Ka_HG': 1e6, 'Ka_HG2': 3e4}
    fit = replace(
        _baseline_fit(),
        assay_type='DBA_HG2',
        parameters={'Ka_HG': Q_(1e6, '1/M'), 'Ka_HG2': Q_(3e4, '1/M'), 'I0': Q_(100.0, 'au')},
        degenerate_keys=(),
    )
    if mode is SensitivityMode.HEATMAP:
        offsets = np.linspace(-5.0, 5.0, 3)
        return SensitivityResult(
            mode=mode,
            assay_type='DBA_HG2',
            ka_keys=keys,
            baseline_ka=baseline,
            x_offsets_pct=offsets,
            y_offsets_pct=offsets,
            ka_grid={key: value * (1 + 0.01 * rng.normal(size=(3, 3))) for key, value in baseline.items()},
            n_success=9,
            n_total=9,
            config=SensitivityConfig(
                mode,
                1,
                ErrorModel(specs={key: InputSpec.sigma_pct(5.0) for key in _TWO_KA_INPUTS}),
                x_key=TITRANT,
                y_key='h0',
                n_steps=3,
            ),
            seed_used=7,
            r2_grid=np.full((3, 3), 0.99),
            baseline_fit=fit,
        )
    offsets = {key: rng.normal(0.0, 5.0, n) for key in _TWO_KA_INPUTS}
    indices = {key: {input_key: 0.4 for input_key in _TWO_KA_INPUTS} for key in keys}
    return SensitivityResult(
        mode=mode,
        assay_type='DBA_HG2',
        ka_keys=keys,
        baseline_ka=baseline,
        x_offsets_pct=None,
        y_offsets_pct=None,
        ka_grid=None,
        n_success=n,
        n_total=n,
        config=SensitivityConfig(
            mode, n // 2, ErrorModel(specs={key: InputSpec.sigma_pct(5.0) for key in _TWO_KA_INPUTS}), seed=7
        ),
        seed_used=7,
        sobol_s1=indices,
        sobol_st=indices,
        sobol_s1_ci={key: {k: (0.3, 0.5) for k in _TWO_KA_INPUTS} for key in keys},
        sobol_st_ci={key: {k: (0.3, 0.5) for k in _TWO_KA_INPUTS} for key in keys},
        sample_offsets_pct=offsets,
        sample_ka={key: value * (1 + 0.01 * offsets[TITRANT]) for key, value in baseline.items()},
        sample_usable={key: np.ones(n, dtype=bool) for key in keys},
        sample_r2=np.full(n, 0.99),
        baseline_fit=fit,
        sample_params={key: value * (1 + 0.01 * offsets[TITRANT]) for key, value in baseline.items()},
        budget={key: _two_ka_budget() for key in keys},
        elasticity={key: dict.fromkeys(_TWO_KA_INPUTS, 0.5) for key in keys},
        sources=_TWO_KA_INPUTS,
        source_inputs={key: (key,) for key in _TWO_KA_INPUTS},
    )


def test_a_two_constant_model_is_reported_per_binding_constant(qapp):
    """Both constants of a 1:2 model get their own histogram, index chart, panel row and map."""
    from PyQt6.QtWidgets import QLabel

    from gui.plotting.labels import fmt_param
    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    w.update_result(_two_ka_result())
    assert w._stack.currentWidget() is w._results_host

    titles = [plot.titleLabel.text for plot in _plots(w)]
    for ka_key in ('Ka_HG', 'Ka_HG2'):
        label = fmt_param(ka_key)
        assert sum(title.startswith(label) and 'median' in title for title in titles) == 1
        assert titles.count(f'{label} — Sobol indices') == 1
    # One row of "Ka vs input" panels per constant, one panel per varied input.
    headings = [
        label.text()
        for label in w._results_host.widget().findChildren(QLabel)
        if label.text().endswith('vs each source')
    ]
    assert headings == [f'{fmt_param(key)} vs each source' for key in ('Ka_HG', 'Ka_HG2')]
    x_labels = [plot.getAxis('bottom').labelText for plot in _plots(w)]
    assert sum(label.startswith('Δ ') for label in x_labels) == 2 * len(_TWO_KA_INPUTS)

    w.update_result(_two_ka_result(SensitivityMode.HEATMAP))
    assert [target['ka_key'] for target in w._hover_targets] == ['Ka_HG', 'Ka_HG2']
    assert fmt_param('Ka_HG2') in w._readout_html(w._hover_targets[1], 0, 0)


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


def test_ka_vs_input_panels_draw_every_fitted_sample_as_a_dot(qapp):
    """One dot per sample that has a fit, no line through them, and the samples without one left out."""
    from gui.plotting.sensitivity_widget import SensitivityWidget

    result = _sobol_result()
    ka = result.sample_ka['Ka_guest']
    fitted = np.isfinite(ka)
    assert not fitted.all()
    w = SensitivityWidget()
    w.update_result(result)

    panels = _ka_vs_input_panels(w)
    assert len(panels) == len(_INPUTS)
    for plot in panels.values():
        (dots,) = [item for item in plot.items if isinstance(item, pg.PlotDataItem)]
        assert dots.opts['pen'] is None
        np.testing.assert_array_equal(np.sort(dots.getOriginalDataset()[1]), np.sort(ka[fitted]))
        assert dots.opts['symbol'] == 'o'
        assert dots.opts['symbolSize'] >= 8
        assert dots.opts['symbolBrush'].color().name() == '#2a78d6'
        assert (dots.opts['symbolPen'].color().name(), dots.opts['symbolPen'].widthF()) == ('#fcfcfb', 2.0)


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
        config=replace(base.config, errors=ErrorModel(specs=specs)),
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
    assert 'Input Uncertainty' in w._placeholder.text() and 'Δ' not in w._placeholder.text()

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


def test_note_states_the_unfitted_count_and_the_seed(qapp):
    """The samples with no fit are counted out of every sample the run planned, and the seed repeats the run."""
    from gui.plotting.sensitivity_widget import SensitivityWidget

    result = _sobol_result()  # 40 samples, one of them unfitted
    w = SensitivityWidget()
    w.update_result(result)
    text = w._note.text()
    assert '1 of 40 samples could not be fitted and is left out.' in text

    assert f'Seed {result.seed_used}' in text  # what repeats the run is on the tab, and in its picture

    # A result with no Ka per sample has no count to report and no budget to
    # draw from them, only its seed.
    result.sample_r2 = result.sample_ka = result.budget = None
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


def _stopped_result(kept: int) -> SensitivityResult:
    """A run of 16 sample groups in eight blocks of two, stopped with *kept* blocks finished.

    As a run records it: every sample of an unfinished block reads as having
    no fit, and inside the finished ones the A sample of group 1 could not be
    fitted, which takes that group out of the indices.
    """
    result = _sobol_result()
    n_base, per_block = 16, 2
    finished = np.arange(n_base) < kept * per_block
    fitted = np.tile(finished, 2)
    fitted[1] = False
    ka = np.where(fitted, np.asarray(result.sample_ka['Ka_guest'][: 2 * n_base], dtype=float), np.nan)
    ka[fitted] = 2e8
    left_out = int(n_base - finished.sum()) + 1
    return replace(
        result,
        config=replace(result.config, n_samples=n_base),
        sample_ka={'Ka_guest': ka},
        sample_r2=np.where(fitted, 0.99, np.nan),
        sample_profile_r2=np.where(fitted, 0.991, np.nan),
        sample_usable={'Ka_guest': np.tile(fitted[:n_base] & fitted[n_base:], 2)},
        sample_offsets_pct={key: values[: 2 * n_base] for key, values in result.sample_offsets_pct.items()},
        sample_params=None,
        sobol_rows_left_out={'Ka_guest': left_out},
        stopped=True,
        n_blocks_finished=kept,
        n_success=int(fitted.sum()),
        n_total=int(fitted.sum()) + 1,
    )


def test_a_stopped_run_is_counted_once_in_the_blocks_it_kept(qapp):
    """A stopped run keeps whole sample blocks, so it is stated in blocks, and what failed is counted inside them.

    Counting the samples of the dropped blocks as unfitted, or the groups as
    left out of the indices, would give three counts of one stop in three units.
    """
    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    w.update_result(_stopped_result(kept=3))
    text = w._note.text()

    assert f'The analysis was stopped after 3 of {_SOBOL_BLOCKS} sample blocks had finished' in text
    assert 'rests on the 6 sample groups of those blocks' in text
    assert '1 of 12 samples in them could not be fitted and are left out.' in text
    assert 'The Sobol indices leave out 1 of the 6 sample groups of the finished blocks' in text
    assert 'either because' not in text and '32 samples' not in text and 'of the 16' not in text


def test_a_run_stopped_before_any_block_finished_says_so_where_the_bars_would_be(qapp):
    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    missing = {'Ka_guest': dict.fromkeys(_INPUTS, np.nan)}
    no_ci = {'Ka_guest': dict.fromkeys(_INPUTS, (np.nan, np.nan))}
    w.update_result(
        replace(_stopped_result(kept=0), sobol_s1=missing, sobol_st=missing, sobol_s1_ci=no_ci, sobol_st_ci=no_ci)
    )
    (plot,) = [plot for plot in _plots(w) if 'Sobol indices' in plot.titleLabel.text]
    texts = [item.textItem.toPlainText() for item in plot.items if isinstance(item, pg.TextItem)]

    (reason,) = [text for text in texts if text != 'n/a']
    assert reason.startswith(f'No index: the analysis was stopped before any of its {_SOBOL_BLOCKS} sample blocks')
    assert 'stopped after' not in w._note.text()


def test_a_run_stopped_during_its_elasticity_refits_says_it_was_stopped_and_nothing_else(qapp, monkeypatch):
    """The refits a stop leaves unrun did not fail: the tab says the run was stopped, not that Ka jumps.

    A run is stopped after two of the elasticity refits, which come before the
    first sample block. No reason to withhold may be given, and nothing on the
    tab may say the refits gave no fit or do not follow the inputs.
    """
    from PyQt6.QtWidgets import QLabel

    import core.pipeline.sensitivity as sens
    from core.assays.ida import IDAAssay
    from core.data_processing.measurement_set import MeasurementSet
    from core.pipeline.fit_pipeline import FitConfig
    from gui.plotting.sensitivity_widget import SensitivityWidget
    from tests.conftest import IDA_TRUE, _make_ida_data

    def fake_fit(ms, assay_cls, x_base, base_conditions, offsets, fit_config, *_):
        signal = dict.fromkeys(('I0', 'I_dye_free', 'I_dye_bound'), 0.0)
        return {'Ka_guest': 10.0 ** (8 + offsets.get('h0', 0.0)), **signal}, 1.0, 1.0

    monkeypatch.setattr(sens, '_fit_perturbed', fake_fit)
    x, y = _make_ida_data(IDA_TRUE, n_points=20)
    ms = MeasurementSet(concentrations=x, signals=y.reshape(1, -1), replica_ids=('r0',))
    conditions = {k: Q_(IDA_TRUE[k], u) for k, u in (('Ka_dye', '1/M'), ('h0', 'M'), ('d0', 'M'))}
    finished: list[int] = []
    result = sens.run_sensitivity(
        ms,
        IDAAssay,
        conditions,
        FitConfig(),  # the default bounds, under which the homogeneity identity applies
        SensitivityConfig(SensitivityMode.SOBOL, 1024, ErrorModel(specs={'h0': InputSpec.sigma_pct(3.0)}), seed=1),
        max_workers=1,
        progress=lambda done, total: finished.append(done),
        should_cancel=lambda: len(finished) >= 3,  # the baseline and two refits
    )
    assert (result.stopped, result.n_blocks_finished, result.withheld) == (True, 0, {'Ka_guest': ''})

    w = SensitivityWidget()
    w.update_result(result)
    (plot,) = [plot for plot in _plots(w) if 'Sobol indices' in plot.titleLabel.text]
    texts = [item.textItem.toPlainText() for item in plot.items if isinstance(item, pg.TextItem)]
    texts += [label.text() for label in w.findChildren(QLabel)]
    assert any(t.startswith('No index: the analysis was stopped before any') for t in texts)
    assert not any('smoothly' in t or 'gave no fit' in t for t in texts)


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


def test_heatmap_note_counts_the_cells_with_no_fit(qapp):
    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    w.update_result(_heatmap_result())

    assert '1 of 9 grid cells could not be fitted and is left out.' in w._note.text()


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

    # Cell (x, y) = (-5 %, -5 %): Ka 1.8×10⁶ against a baseline of 2×10⁶, R² 0.95.
    text = w._readout_html(target, 0, 0)
    assert 'Guest −5%, [Host]<sub>0</sub> −5%' in text
    assert '1.80×10⁶' in text
    assert 'change: −10%' in text
    assert 'R² = 0.9500' in text

    # The failed cell still names where it is.
    assert w._readout_html(target, 1, 2) == 'Guest 0%, [Host]<sub>0</sub> +5%<br>no fit could be produced'


def test_heatmap_readout_r2_reads_as_far_from_one_as_it_is(qapp):
    """A cell a hair below 1 reads below it, from the one shared R² formatter."""
    from gui.plotting.labels import fmt_r2
    from gui.plotting.sensitivity_widget import SensitivityWidget

    result = _heatmap_result()
    result.r2_grid[0, 0] = 0.9999870
    w = SensitivityWidget()
    w.update_result(result)
    (target,) = w._hover_targets
    assert f'R² = {fmt_r2(0.9999870)}' in w._readout_html(target, 0, 0)
    assert 'R² = 1.0000' not in w._readout_html(target, 0, 0)


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


def test_baseline_line_follows_its_own_style_and_no_other(qapp):
    """The histogram's baseline line takes the Ka Sensitivity style; the shared Analysis plots style leaves it alone."""
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

    style_widget._params['Analysis plots', 'Tick font size'] = 20
    style_widget._params['Analysis plots', 'Label font size'] = 20
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
    """Stand-in for ``run_sensitivity`` reporting *n_fits* finished fits, then a Sobol' result made on its inputs.

    The result carries the configuration it was asked to run, as a real run's
    does: the session checks a held run against the uncertainties it records.
    """

    def run(ms, assay_cls, conditions, _fit_config, sens_config, *args, progress, **kwargs):
        for done in range(1, n_fits + 1):
            time.sleep(pause)
            progress(done, n_fits)
        result = replace(_sobol_result(), config=sens_config)
        return result if ms is None else _made_on(result, ms, conditions)

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
    session.model.load_files(['data/IDA_system.txt'])
    # Every uncertainty row opens fixed, so the analysis has nothing to vary
    # until one is stated: σ 5 % on each of the assay's four inputs.
    for row in session._input_panel._rows.values():
        row.set_spec(InputSpec.sigma_pct(5.0))
    combo = session._sensitivity_panel._samples_combo
    combo.setCurrentIndex(combo.findData(1024))
    return session, warnings


def _wait_for_worker(session, qapp):
    """Wait for the running sensitivity worker to finish, then deliver its signals."""
    worker = session.model._sensitivity_worker
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
    session.model.status_changed.connect(messages.append)

    session.run_sensitivity()
    _wait_for_worker(session, qapp)

    bar = session._sensitivity_widget._progress_bar
    assert warnings == []
    assert session.model.sensitivity_result is not None
    assert (bar.value(), bar.maximum()) == (40, 40)
    assert any(message.startswith('Analysing') and message.endswith('left') for message in messages)
    # At the last count there is no time left to estimate.
    assert [message for message in messages if message.startswith('Analysing')][-1] == 'Analysing — 40 of 40'


def test_time_left_reads_as_plain_english():
    from gui.session_model import _format_remaining

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
    session.model.status_changed.connect(messages.append)

    session.run_sensitivity()
    session.model.cancel_sensitivity()
    _wait_for_worker(session, qapp)

    assert warnings == []
    # A cancel is an outcome, not an error. This result's baseline records no
    # data, so the tab hides it and the status bar says so in place of counts
    # from a result no tab is showing.
    assert messages[-1] == f'Sensitivity stopped but hidden — {session.model.sensitivity_note}'
    assert session.model.sensitivity_note is not None


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
    session.model.status_changed.connect(messages.append)

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
    earlier = session.model.sensitivity_result
    monkeypatch.setattr(workers, 'run_sensitivity', failing)
    session.run_sensitivity()
    _wait_for_worker(session, qapp)
    assert len(warnings) == 2
    assert widget._stack.currentWidget() is widget._results_host
    assert widget._result is earlier


# ---------------------------------------------------------------------------
# The summary under the plot tabs
# ---------------------------------------------------------------------------
#
# What the samples view shows — the statistics over the samples, the caption and
# Fit Quality — is pinned by tests/unit/gui/test_fit_summary_widget.py. Here only
# the wiring is checked: which view the session shows, and that no run reaches a
# tab it does not belong to.


def _in_samples_view(widget) -> bool:
    from gui.plotting.fit_summary_widget import _REPORT_TITLE

    return widget._params_group.title() == _REPORT_TITLE


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


def test_summary_follows_the_view(qapp, monkeypatch):
    """In Sensitivity the summary shows the run's samples; Fit results brings the fit back."""
    from gui import workers

    monkeypatch.setattr(workers, 'run_sensitivity', _fake_run(3))
    session, warnings = _demo_session(monkeypatch)
    summary = session._summary_widget
    session.show_view('Sensitivity')

    session.run_sensitivity()
    _wait_for_worker(session, qapp)

    assert warnings == []
    assert _in_samples_view(summary)
    session.show_view('Fit results')
    assert not _in_samples_view(summary)
    session.show_view('Sensitivity')
    assert _in_samples_view(summary)


def test_summary_never_shows_a_run_that_is_not_the_views(qapp, monkeypatch):
    """A new run, a failed one, a heatmap and new or cleared data all leave the summary matching the view."""
    from gui import workers

    def failing(*args, progress, **kwargs):
        raise ValueError('The unperturbed (baseline) fit did not converge.')

    session, warnings = _demo_session(monkeypatch)
    summary = session._summary_widget
    session.show_view('Sensitivity')

    monkeypatch.setattr(workers, 'run_sensitivity', _fake_run(3))
    session.run_sensitivity()
    _wait_for_worker(session, qapp)
    earlier = session.model.sensitivity_result
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

    session.model.load_files(['data/IDA_system.txt'])
    assert session.model.sensitivity_result is None
    assert session._sensitivity_widget._stack.currentWidget() is session._sensitivity_widget._placeholder
    assert summary._sensitivity is None
    assert summary._caption.text().startswith('Run a sensitivity analysis with Sensitivity indices')

    monkeypatch.setattr(workers, 'run_sensitivity', _fake_run(3))
    session.run_sensitivity()
    _wait_for_worker(session, qapp)
    assert _in_samples_view(summary)
    session.model.clear()
    assert session.model.sensitivity_result is None
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
    worker = session.model._sensitivity_worker

    session.model.load_files(['data/IDA_system.txt'])
    worker.wait()
    qapp.processEvents()

    assert warnings == []
    assert session.model._sensitivity_worker is None
    assert session.model.sensitivity_result is None
    assert session._summary_widget._sensitivity is None
    assert session._sensitivity_widget._stack.currentWidget() is session._sensitivity_widget._placeholder


# ---------------------------------------------------------------------------
# A run with no indices to show, and the size one run is quoted
# ---------------------------------------------------------------------------


def _no_index_result(*, stopped: bool):
    """A Sobol result whose every index is NaN: no sample group was ever completed."""
    inputs = list(_sobol_result().sobol_s1['Ka_guest'])
    missing = {'Ka_guest': {key: np.nan for key in inputs}}
    missing_ci = {'Ka_guest': {key: (np.nan, np.nan) for key in inputs}}
    ka = np.array(_sobol_result().sample_ka['Ka_guest'])
    ka[6:] = np.nan  # only the first fits of the first matrix were made
    return replace(
        _sobol_result(),
        sobol_s1=missing,
        sobol_st=missing,
        sobol_s1_ci=missing_ci,
        sobol_st_ci=missing_ci,
        sample_ka={'Ka_guest': ka},
        sample_usable={'Ka_guest': np.zeros(ka.size, dtype=bool)},
        sobol_rows_left_out={'Ka_guest': _sobol_result().config.n_samples},
        stopped=stopped,
        n_success=6,
        n_total=6,
    )


@pytest.mark.parametrize(
    ('stopped', 'fix'),
    [(True, 'let it finish'), (False, 'Input Uncertainty')],
    ids=['stopped', 'failed'],
)
def test_an_index_panel_with_no_bars_says_why_it_is_empty(qapp, stopped, fix):
    """Axes, a title and a legend with nothing drawn between them state only that something is missing.

    The reason belongs where the bars would be: the panel is what the user is
    looking at, and it is the picture the tab saves.
    """
    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    w.update_result(_no_index_result(stopped=stopped))
    (plot,) = [plot for plot in _plots(w) if 'Sobol indices' in plot.titleLabel.text]

    bars = [item for item in plot.items if isinstance(item, pg.BarGraphItem)]
    assert all(len(item.opts['x0']) == 0 for item in bars)  # nothing is drawn
    texts = [item.textItem.toPlainText() for item in plot.items if isinstance(item, pg.TextItem)]
    (reason,) = [text for text in texts if text != 'n/a']
    assert reason.startswith('No index')
    assert fix in reason
    w.close()


def test_an_empty_index_panel_counts_the_samples_that_did_get_a_fit(qapp):
    """A run can hold a fit for every sample it reports and still have finished no sample group.

    A group needs its mixed samples too, so Fit Quality can count samples with
    a fit while the index panels have nothing to rank. The two readings sit in
    different panes and read as contradicting each other unless the panel with
    no bars gives both counts.
    """
    from gui.plotting.sensitivity_widget import SensitivityWidget

    result = _no_index_result(stopped=False)
    fitted = int(np.isfinite(result.sample_ka['Ka_guest']).sum())
    groups = result.config.n_samples
    finished = groups - result.sobol_rows_left_out['Ka_guest']
    assert fitted and not finished  # samples were fitted; no group of them is complete

    w = SensitivityWidget()
    w.update_result(result)
    (plot,) = [plot for plot in _plots(w) if 'Sobol indices' in plot.titleLabel.text]
    texts = [item.textItem.toPlainText() for item in plot.items if isinstance(item, pg.TextItem)]
    (reason,) = [text for text in texts if text != 'n/a']

    assert f'{finished:,} of {groups:,} sample groups' in reason
    assert f'{fitted:,} samples were fitted' in reason
    w.close()


def test_one_run_is_quoted_the_same_number_of_fits_wherever_it_is_counted(qapp, monkeypatch):
    """The cost dialog, the progress line and the message at the end all size the same run, written the same way.

    The run makes one fit per perturbed sample and one baseline fit. Quoting two
    of those numbers reads as two different runs, and so does quoting one of
    them as 5121 where the others say 5,121.
    """
    from PyQt6.QtWidgets import QMessageBox

    from core.pipeline.inputs import perturbable_inputs
    from core.pipeline.sensitivity import estimated_fit_count
    from gui import workers

    def run(ms, assay_cls, conditions, fit_config, sens_config, *, progress, **kwargs):
        # What run_sensitivity itself counts to: the perturbed fits, the
        # elasticity refits of every perturbable input, and the baseline.
        total = estimated_fit_count(sens_config, len(perturbable_inputs(conditions))) + 1
        progress(total, total)
        result = _made_on(_sobol_result(), ms, conditions)
        return replace(result, config=sens_config, n_success=total - 1, n_total=total - 1, n_planned=total - 1)

    monkeypatch.setattr(workers, 'run_sensitivity', run)
    session, warnings = _demo_session(monkeypatch)
    asked = []
    monkeypatch.setattr('gui.session_model.LONG_RUN_SOLVES', 0)  # so the cost dialog is offered
    monkeypatch.setattr(
        'gui.fitting_session.QMessageBox.question',
        lambda parent, title, text, *args: (asked.append(text), QMessageBox.StandardButton.Yes)[1],
    )
    messages = []
    session.model.status_changed.connect(messages.append)

    session.run_sensitivity()
    _wait_for_worker(session, qapp)

    counted = session._sensitivity_widget._progress_bar.maximum()
    assert warnings == []
    assert counted > 1
    assert counted >= 1000  # so the thousands separator is visible at all
    assert f'{counted:,} times' in asked[0]
    assert f'Analysing — {counted:,} of {counted:,}' in messages
    assert messages[-1] == f'Sensitivity complete — {counted:,} of {counted:,} fits succeeded'


# ---------------------------------------------------------------------------
# Uncertainty budget
# ---------------------------------------------------------------------------


def _budget_tables(widget) -> list:
    """The budget table of each binding constant, in the order the constants are drawn."""
    from gui.plotting.fit_summary_widget import ParameterTable

    return widget._results_host.widget().findChildren(ParameterTable)


def _cells(table) -> list[list[str]]:
    """A table's rows as the text of their cells."""
    return [
        [table.cellWidget(row, col).text() for col in range(table.columnCount())] for row in range(table.rowCount())
    ]


def _headers(table) -> list[str]:
    return [table.horizontalHeaderItem(col).text() for col in range(table.columnCount())]


def test_the_budget_table_shows_the_numbers_of_the_result_it_was_given(qapp):
    """Every cell is the analysis's own number, formatted; nothing in the table is worked out here.

    The fixture's variance, its interval and the share of each source are round
    numbers, so what each cell must read is known without repeating the widget's
    arithmetic: 0.05 × 0.007056 decades² for the dye constant, and the share no
    single source explains, 1 − (0.05 + 0.2 + 0.6) = 0.15.
    """
    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    w.update_result(_sobol_result())
    (table,) = _budget_tables(w)

    assert _headers(table) == [
        'Source',
        'Stated uncertainty',
        'Elasticity',
        'Share of variance S₁ [95 %]',
        'Variance (decades²) [95 %]',
        'Spread if exact (decades) [95 %]',
    ]
    rows = _cells(table)
    assert [row[0] for row in rows] == [w._input_label(AssayType.IDA, key) for key in _INPUTS] + ['Interactions']
    # Ka,dye: stated as σ 5 %, elasticity 0.31, S₁ 0.05 [0.02, 0.15],
    # 0.05 × 0.007056 = 3.528e-4 decades², 0.0819 decades left if it were exact.
    assert rows[0] == [
        w._input_label(AssayType.IDA, 'Ka_dye'),
        'σ 5 %',
        '0.31',
        '0.050 [0.020, 0.15]',
        '3.5×10⁻⁴ [2.0×10⁻⁴, 5.0×10⁻⁴]',
        '0.082 [0.079, 0.084]',
    ]
    # An input the fit answers to the other way round keeps its sign.
    assert rows[1][2] == '−1.2'
    # The interactions row carries its share, 0.15, and that share of the variance, 0.15 × 0.007056.
    assert rows[-1] == ['Interactions', '–', '–', '0.15', '1.1×10⁻³', '–']


def test_the_variance_column_adds_up_to_the_square_of_the_spread(qapp):
    """What the sources explain alone and what they explain only together make up the whole variance."""
    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    result = _sobol_result()
    w.update_result(result)
    rows = w.budget_rows()

    parts = [row['Variance (decades^2)'] for row in rows if row['Kind'] in ('source', 'interactions')]
    assert sum(parts) == pytest.approx(result.budget['Ka_guest'].sd ** 2, rel=1e-12)


def test_an_interval_is_printed_to_the_figures_that_tell_it_from_its_estimate(qapp):
    """``0.050 [0.050, 0.050]`` reads as no uncertainty at all; the ends get the figures that show them."""
    from gui.plotting.labels import fmt_param
    from gui.plotting.sensitivity_widget import SensitivityWidget

    result = _sobol_result()
    first = result.budget['Ka_guest'].rows[0]
    tight = BudgetRow(first.source, first.variance, first.variance_ci, 0.05, (0.04999, 0.05001), first.elasticity)
    result.budget = {'Ka_guest': Budget(0.0025, (0.04999**2, 0.05001**2), (tight, *result.budget['Ka_guest'].rows[1:]))}
    w = SensitivityWidget()
    w.update_result(result)

    assert w._budget_header(result, 'Ka_guest') == (
        f'Spread of log₁₀({fmt_param("Ka_guest")}) from the stated input uncertainties, 1 SD: '
        '0.05000 decades (×/÷&nbsp;1.1220) [0.04999, 0.05001]'
    )
    assert _cells(_budget_tables(w)[0])[0][-1] == '0.05000 [0.04999, 0.05001]'
    # Where two figures already tell them apart, two it is.
    assert _cells(_budget_tables(w)[0])[1][-1] == '0.075 [0.072, 0.078]'


def test_the_spread_column_never_shows_a_negative_standard_deviation(qapp):
    """The jackknife interval is symmetric, so on a source that explains almost everything its lower end dips below
    zero; a spread cannot be negative, and the header line reads such an end the same way."""
    from gui.plotting.sensitivity_widget import SensitivityWidget

    result = _sobol_result()
    budget = result.budget['Ka_guest']
    first = budget.rows[0]
    quiet = BudgetRow(first.source, first.variance, first.variance_ci, 0.004, (-0.004, 0.012), first.elasticity)
    result.budget = {'Ka_guest': Budget(budget.variance, budget.variance_ci, (quiet, *budget.rows[1:]))}
    w = SensitivityWidget()

    w.update_result(result)

    assert _cells(_budget_tables(w)[0])[0][-1] == '4.0×10⁻³ [0, 0.012]'


def test_the_budget_table_states_a_range_input_by_its_two_ends(qapp):
    """A range is stated as the ends entered, in percent of the value the analysis started from."""
    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    w.update_result(_ranged_result())
    stated = {row[0]: row[1] for row in _cells(_budget_tables(w)[0])}

    assert stated[w._input_label(AssayType.IDA, 'Ka_dye')] == '−6 % to +4 %'
    # A range is reduced by shrinking it about its centre, so the what-if row
    # asks for half a width and says so.
    _, spin, sentence = w._what_if['Ka_guest']
    assert spin.prefix() == '±'
    assert spin.maximum() == 5.0  # half of −6 % to +4 %
    assert 'from ±5 % to ±2.5 %' in sentence.text()
    # [Host]₀ is entered as 4.1–4.4 µM of 4.3 µM: −4.65 % to +2.33 % of it.
    low, high = (f'{value:+.3g}'.replace('-', '−') for value in _H0_RANGE_PCT)
    assert stated[w._input_label(AssayType.IDA, 'h0')] == f'{low} % to {high} %'


def test_the_header_line_states_the_spread_and_the_interval_of_the_spread(qapp):
    """A variance of 0.007056 decades² is a spread of 0.084 decades, a factor of 1.21 either way.

    The interval is the interval of the variance read in decades: 0.006561 and
    0.007569 decades² are 0.081 and 0.087 decades.
    """
    from gui.plotting.labels import fmt_param
    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    result = _sobol_result()
    w.update_result(result)

    assert w._budget_header(result, 'Ka_guest') == (
        f'Spread of log₁₀({fmt_param("Ka_guest")}) from the stated input uncertainties, 1 SD: 0.084 decades '
        '(×/÷&nbsp;1.21) [0.081, 0.087]'
    )


def test_a_budget_no_run_could_pin_down_says_so_instead_of_writing_nan(qapp):
    """Too few finished fits leave no variance; the line says that, rather than printing a number that is not one."""
    from core.pipeline.budget import Budget
    from gui.plotting.sensitivity_widget import SensitivityWidget

    result = _sobol_result()
    result.budget = {'Ka_guest': Budget(np.nan, (np.nan, np.nan), result.budget['Ka_guest'].rows)}
    w = SensitivityWidget()
    w.update_result(result)

    line = w._budget_header(result, 'Ka_guest')
    assert line.endswith('too few fits finished to work it out.')
    assert 'nan' not in line.lower()
    # With no variance there is no share for the sources to leave over, and a
    # row of "0" beside sources that all read n/a would state one.
    assert _cells(_budget_tables(w)[0])[-1] == ['Interactions', '–', '–', 'n/a', 'n/a', '–']


_KNOWN_WHAT_IF = WhatIf(sd=0.056, sd_reweighted=0.057, effective_samples=1111.4, largest_after='h0')


def test_the_what_if_sentence_leads_with_the_re_weighted_answer(qapp, monkeypatch):
    """With enough samples carrying it, the spread after the reduction is the re-weighted one.

    The re-weighted value is the more accurate of the two, so it is the spread
    the sentence states and the formula is the number behind it.
    """
    from gui.plotting import sensitivity_widget as widget_module
    from gui.plotting.labels import fmt_param
    from gui.plotting.sensitivity_widget import SensitivityWidget

    asked = []

    def fake_what_if(result, ka_key, source, ratio):
        asked.append((ka_key, source, ratio))
        return _KNOWN_WHAT_IF

    monkeypatch.setattr(widget_module, 'what_if', fake_what_if)
    w = SensitivityWidget()
    w.update_result(_sobol_result())

    combo, spin, sentence = w._what_if['Ka_guest']
    spin.setValue(1.0)
    # The core call gets the reduction as a share of what was stated: 1 % of 5 %.
    assert asked[-1] == ('Ka_guest', 'Ka_dye', 0.2)
    assert sentence.text() == (
        f'Reducing {w._input_label(AssayType.IDA, "Ka_dye")} from 5 % to 1 % would shrink the spread the stated '
        f'uncertainties give {fmt_param("Ka_guest")} from 0.084 decades (×/÷&nbsp;1.21) to 0.057 decades '
        '(×/÷&nbsp;1.14), read from the samples re-weighted towards the narrower uncertainty '
        '(1,111 effective samples). Cross-check by the formula: 0.056. '
        f'{w._input_label(AssayType.IDA, "h0")} would then be the largest item.'
    )


def test_the_what_if_sentence_says_when_no_cross_check_backs_it(qapp, monkeypatch):
    """Too few samples carrying weight and a source made exact are different reasons, and read as different ones."""
    from dataclasses import replace as replace_dc

    from gui.plotting import sensitivity_widget as widget_module
    from gui.plotting.sensitivity_widget import SensitivityWidget

    answers = iter(
        [
            replace_dc(_KNOWN_WHAT_IF, sd_reweighted=None, effective_samples=31.0),
            replace_dc(_KNOWN_WHAT_IF, sd_reweighted=None, effective_samples=None),
        ]
    )
    monkeypatch.setattr(widget_module, 'what_if', lambda *args: next(answers))
    w = SensitivityWidget()
    w.update_result(_sobol_result())
    _, spin, sentence = w._what_if['Ka_guest']

    # With no re-weighting the formula states the spread, as it did before it.
    assert 'to 0.056 decades (×/÷&nbsp;1.14). ' in sentence.text()
    assert '(no cross-check: too few samples carry weight at this reduction).' in sentence.text()
    spin.setValue(0.0)
    assert '(no cross-check: with the source exact there is no sample left to re-weight).' in sentence.text()


def test_the_what_if_row_only_offers_a_reduction_of_a_single_source(qapp):
    """The spin is bounded by the stated uncertainty, and the random error of each addition is no single offset."""
    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    w.update_result(_shared_source_result())
    combo, spin, _ = w._what_if['Ka_guest']

    assert [combo.itemData(i) for i in range(combo.count())] == ['h0', shared_key('Stock A')]
    assert (spin.minimum(), spin.maximum()) == (0.0, 4.0)  # [Host]₀ was stated as σ 4 %
    combo.setCurrentIndex(1)
    assert spin.maximum() == 3.0  # the shared stock, stated as σ 3 %


_SHARED = shared_key('Stock A')


def _shared_source_result() -> SensitivityResult:
    """An IDA run over [Host]₀'s own error, a stock both concentrations share, and the additions."""
    rng = np.random.default_rng(3)
    n = 40
    sources = ('h0', _SHARED, ADDITIONS)
    offsets = {'h0': rng.normal(0.0, 4.0, n), _SHARED: rng.normal(0.0, 3.0, n)}
    ka = 2e8 * (1 + 0.01 * offsets['h0'])
    s1 = {'h0': 0.3, _SHARED: 0.5, ADDITIONS: 0.1}
    variance = 0.01
    return replace(
        _sobol_result(),
        config=SensitivityConfig(
            SensitivityMode.SOBOL,
            n // 2,
            ErrorModel(
                specs={'h0': InputSpec.sigma_pct(4.0)},
                shared=(SharedSource('Stock A', 3.0, ('h0', 'd0')),),
                additions=AdditionError(1.0, sequential=False),
            ),
            seed=0,
        ),
        sobol_s1={'Ka_guest': s1},
        sobol_st={'Ka_guest': s1},
        sobol_s1_ci={'Ka_guest': {k: (v - 0.05, v + 0.05) for k, v in s1.items()}},
        sobol_st_ci={'Ka_guest': {k: (v - 0.05, v + 0.05) for k, v in s1.items()}},
        sample_offsets_pct=offsets,
        sample_ka={'Ka_guest': ka},
        sample_r2=np.full(n, 0.99),
        sample_params={'Ka_guest': ka},
        budget={
            'Ka_guest': Budget(
                variance=variance,
                variance_ci=(0.008, 0.012),
                rows=(
                    BudgetRow('h0', 0.3 * variance, (0.002, 0.004), 0.0837, (0.08, 0.087), -1.2),
                    BudgetRow(_SHARED, 0.5 * variance, (0.004, 0.006), 0.0707, (0.067, 0.074), -0.6),
                    BudgetRow(ADDITIONS, 0.1 * variance, (0.0005, 0.0015), 0.0949, (0.092, 0.097), None),
                ),
            )
        },
        elasticity={'Ka_guest': {'h0': -1.2, 'd0': 0.6, 'Ka_dye': 0.3, TITRANT: 0.95}},
        sources=sources,
        source_inputs={'h0': ('h0',), _SHARED: ('h0', 'd0'), ADDITIONS: ()},
    )


def test_a_shared_source_and_the_additions_are_listed_beside_the_inputs(qapp):
    """Both are sources of the spread, so both get a bar and a budget row; neither is an input offset panel.

    A shared source goes by the name it was given and moves several inputs at
    once, so its elasticity is the sum over them. The additions are one item
    standing for every addition: no single offset, so no elasticity and no
    "Ka vs source" panel.
    """
    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    result = _shared_source_result()
    w.update_result(result)

    (bars,) = [plot for plot in _plots(w) if 'Sobol indices' in plot.titleLabel.text]
    axis = bars.getAxis('bottom')
    axis.resize(2000, axis.height())
    assert axis.tickStrings([0.0, 1.0, 2.0], 1, 1) == ['[Host]₀', 'Stock A', 'Each addition (random)']

    rows = _cells(_budget_tables(w)[0])
    assert [row[0] for row in rows] == ['[Host]<sub>0</sub>', 'Stock A', 'Each addition (random)', 'Interactions']
    assert rows[1][1:3] == ['σ 3 %', '−0.60']
    assert rows[2][1:3] == ['σ 1 % each addition', '–']

    # One panel per source that has an offset of its own; the additions have none.
    panels = [plot.getAxis('bottom').labelText for plot in _plots(w) if plot.getAxis('bottom').labelText]
    assert 'Δ Stock A [%]' in panels
    assert not any('addition' in label for label in panels)


def test_a_source_name_wider_than_its_bar_slot_is_cut_to_it(qapp):
    """A shared source carries the name the user typed, and two full names would be drawn over each other."""
    from gui.plotting.sensitivity_widget import _SourceAxis

    names = ('Host and dye stock', 'Each addition (random)')
    axis = _SourceAxis(names)

    axis.resize(2000, 30)
    assert axis.tickStrings([0.0, 1.0], 1, 1) == list(names)

    axis.resize(140, 30)
    cut = axis.tickStrings([0.0, 1.0], 1, 1)
    assert [len(text) for text in cut] < [len(name) for name in names]
    assert all(text.endswith('…') for text in cut)

    # One tick per source, wherever the view sits.
    assert axis.tickValues(-0.5, 1.5, 140) == [(1.0, [0.0, 1.0])]


def test_the_additions_row_says_the_interval_the_fit_reports_holds_it_when_stated(qapp):
    """A stated random error of each addition widens the fit's interval; the analysis ranks it against the rest."""
    from PyQt6.QtWidgets import QLabel

    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    w.update_result(_shared_source_result())
    texts = [label.text() for label in w._results_host.widget().findChildren(QLabel)]
    assert any(
        'The random error of each addition is part of the reported interval when stated under Input Uncertainty' in text
        for text in texts
    )
    assert not any('does not include the random error of each addition' in text for text in texts)

    # A run with no additions has nothing to say about them.
    other = SensitivityWidget()
    other.update_result(_sobol_result())
    texts = [label.text() for label in other._results_host.widget().findChildren(QLabel)]
    assert not any('random error of each addition' in text for text in texts)


def test_the_page_says_it_propagates_the_stated_uncertainties_and_how_that_differs_from_the_interval(qapp):
    """Every sample counts the same here; the input-aware interval also weighs what the data say about the inputs."""
    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    w.update_result(_sobol_result())
    (caption,) = [text for text in _labels(w) if 'GUM Supplement 1' in text]

    assert 'propagate the uncertainties stated under Input Uncertainty' in caption
    assert 'input-aware interval on the Fit Curve tab also weighs what the data say about the inputs' in caption
    assert 'can differ' in caption and 'splits' not in caption


def _labels(widget) -> list[str]:
    """The text of every label on the results page."""
    from PyQt6.QtWidgets import QLabel

    return [label.text() for label in widget._results_host.widget().findChildren(QLabel)]


@pytest.mark.parametrize(
    'reason, words',
    [
        ('baseline_on_bound', 'ran to the edge of its bounds'),
        ('open_interval', 'no upper or lower limit'),
        ('homogeneity', 'do not follow the inputs smoothly'),
    ],
)
def test_a_withheld_constant_gets_its_reason_and_no_number(qapp, reason, words):
    """Where the run says a constant's numbers describe the search, not the inputs, none of them is printed.

    A baseline on a bound gives elasticities of zero and a spread of none, which
    read as "the inputs do not matter" where the data simply do not limit Ka; an
    open interval or refits that break the homogeneity identity give numbers of
    any size. The tab has to say which, and print no figure.
    """
    from gui.plotting.sensitivity_widget import SensitivityWidget

    result = replace(_sobol_result(), withheld={'Ka_guest': reason}, homogeneity={'Ka_guest': 56.0})
    w = SensitivityWidget()

    w.update_result(result)

    (note,) = [text for text in _labels(w) if words in text]
    assert 'no share, spread or elasticity is given' in note and 'Identifiability' in note
    assert w._budget_header(result, 'Ka_guest').endswith('not given.')
    assert _budget_tables(w) == [] and w._what_if == {}
    (index_plot,) = [plot for plot in _plots(w) if 'Sobol indices' in plot.titleLabel.text]
    assert all(len(item.opts['x0']) == 0 for item in index_plot.items if isinstance(item, pg.BarGraphItem))
    assert not any(isinstance(item, pg.ErrorBarItem) for item in index_plot.items)
    texts = [item.textItem.toPlainText() for item in index_plot.items if isinstance(item, pg.TextItem)]
    (chart_reason,) = [text for text in texts if text != 'n/a']
    assert chart_reason.startswith('No index for') and 'The note below says more.' in chart_reason
    (histogram,) = [
        plot for plot in _plots(w) if 'median' in plot.titleLabel.text or 'no summary' in plot.titleLabel.text
    ]
    assert 'median' not in histogram.titleLabel.text
    # The exported file carries the same sentence and nothing beside it.
    (row,) = w.budget_rows()
    assert row['Kind'] == 'note' and words in row['Item'] and '<' not in row['Item']
    assert not re.search(r'\d', row['Item'])


def test_an_open_interval_note_names_the_side_the_data_leave_open(qapp):
    from core.pipeline.varpro import KaInterval
    from gui.plotting.sensitivity_widget import _withheld_note

    baseline = replace(_baseline_fit(), intervals={'Ka_guest': KaInterval(1e7, 1e12, False, True, 0.95, 16)})
    result = replace(_sobol_result(), baseline_fit=baseline, withheld={'Ka_guest': 'open_interval'})

    assert 'no upper limit' in _withheld_note(result, 'Ka_guest')


def test_one_withheld_constant_leaves_the_other_its_budget(qapp):
    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    w.update_result(replace(_two_ka_result(), withheld={'Ka_HG': 'open_interval', 'Ka_HG2': ''}))

    assert len(_budget_tables(w)) == 1 and list(w._what_if) == ['Ka_HG2']


def test_a_share_of_the_fits_on_the_ka_bounds_is_counted_in_a_note_above_the_budget(qapp):
    """Those fits sit decades from the rest, so the spread beside them is theirs rather than the inputs'."""
    from gui.plotting.sensitivity_widget import SensitivityWidget

    result = _sobol_result()
    # 40 A+B samples: a design of 20 rows per matrix, five matrices, 100 fits.
    result.n_on_bound = {'Ka_guest': 3}
    w = SensitivityWidget()

    w.update_result(result)

    note = next(text for text in _labels(w) if 'ran to the edge of its bounds' in text)
    assert note.startswith('In 3 of 100 fits (3 %)')
    assert 'those fits jump by many decades and inflate the spread and the budget' in note
    assert 'unidentifiable over part of their range' in note
    # The numbers stay: the spread is inflated, not unknowable.
    assert w._budget_header(result, 'Ka_guest').startswith('Spread of')
    assert _cells(_budget_tables(w)[0])[0][-1] == '0.082 [0.079, 0.084]'
    assert list(w._what_if) == ['Ka_guest']
    assert any(row['Kind'] == 'note' for row in w.budget_rows())


def test_one_fit_on_the_ka_bounds_is_counted_in_the_singular(qapp):
    """A note that says "1 fits jump" reads as a bug and is skimmed past."""
    from gui.plotting.sensitivity_widget import _on_bound_note

    result = _sobol_result()
    result.n_on_bound = {'Ka_guest': 1}

    note = _on_bound_note(result, 'Ka_guest')

    assert note.startswith('In 1 of 100 fits (1 %)')
    assert 'that fit jumps by many decades and inflates' in note


def test_a_large_count_of_fits_on_the_ka_bounds_is_written_for_reading(qapp):
    """A run of thousands of fits reports thousands; four digits in a row are read wrong."""
    from gui.plotting.sensitivity_widget import _on_bound_note

    result = _sobol_result()
    result.config = replace(result.config, n_samples=1024)
    result.n_on_bound = {'Ka_guest': 1230}

    assert _on_bound_note(result, 'Ka_guest').startswith('In 1,230 of 5,120 fits (24 %)')


def test_a_run_that_stayed_inside_the_ka_bounds_carries_no_note(qapp):
    """A note on every run is a note nobody reads; a clean run gets the budget alone."""
    from gui.plotting.sensitivity_widget import SensitivityWidget, _on_bound_note

    result = _sobol_result()
    w = SensitivityWidget()

    w.update_result(result)

    assert _on_bound_note(result, 'Ka_guest') is None
    assert not any('edge of its bounds' in text for text in _labels(w))
    assert not any(row['Kind'] == 'note' for row in w.budget_rows())


def test_each_binding_constant_gets_its_own_budget(qapp):
    """A 1:2 model has two constants, each with its own spread and its own sources."""
    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    w.update_result(_two_ka_result())

    assert len(_budget_tables(w)) == 2
    assert sorted(w._what_if) == ['Ka_HG', 'Ka_HG2']


def test_the_heatmap_has_no_budget_to_show(qapp):
    """A heatmap sweeps a grid; it runs no Sobol design, so there are no shares to split a variance into."""
    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    w.update_result(_heatmap_result())

    assert _budget_tables(w) == []
    assert w._what_if == {}
    assert w.budget_rows() == []


def test_the_exported_budget_carries_the_numbers_the_table_rounds(qapp):
    """The CSV is for a spreadsheet: the analysis's own floats, the elasticity of every input, and the seed."""
    from gui.plotting.sensitivity_widget import SensitivityWidget

    w = SensitivityWidget()
    result = _sobol_result()
    w.update_result(result)
    rows = w.budget_rows()

    by_kind = {}
    for row in rows:
        by_kind.setdefault(row['Kind'], []).append(row)
    assert set(by_kind) == {'total', 'source', 'interactions', 'input'}
    assert all(row['Seed'] == result.seed_used for row in rows)
    assert all(row['Ka'] == 'Ka(G)' for row in rows)

    (total,) = by_kind['total']
    assert total['Variance (decades^2)'] == result.budget['Ka_guest'].variance
    assert (total['Variance (decades^2) low'], total['Variance (decades^2) high']) == (0.006561, 0.007569)
    assert total['S1'] == ''  # a total is not a share of itself

    dye = next(row for row in by_kind['source'] if row['Item'] == 'Ka,dye')
    assert dye['Elasticity'] == 0.31
    assert dye['Variance (decades^2)'] == 0.05 * result.budget['Ka_guest'].variance
    assert dye['Spread if exact (decades)'] == 0.081873

    # Every perturbable input is there, [Dye]₀ included, although no source of
    # its own moves it: a source's elasticity is the sum over the inputs it moves.
    assert {row['Item']: row['Elasticity'] for row in by_kind['input']} == {
        'Ka,dye': 0.31,
        '[Host]₀': -1.2,
        '[Dye]₀': 0.62,
        'Guest': 0.95,
    }


def test_the_exported_budget_leaves_out_what_the_run_could_not_pin_down(qapp):
    """A cell the analysis has no number for is empty in the file, never the text 'nan'."""
    from core.pipeline.budget import Budget, BudgetRow
    from gui.plotting.sensitivity_widget import SensitivityWidget

    result = _sobol_result()
    result.sources = ('h0',)
    result.budget = {
        'Ka_guest': Budget(
            variance=0.007056,
            variance_ci=(np.nan, np.nan),
            rows=(BudgetRow('h0', np.nan, (np.nan, np.nan), np.nan, (np.nan, np.nan), None),),
        )
    }
    w = SensitivityWidget()
    w.update_result(result)

    values = [value for row in w.budget_rows() for value in row.values()]
    assert not any(isinstance(value, float) and np.isnan(value) for value in values)
    assert 'nan' not in ' '.join(str(value) for value in values).lower()
