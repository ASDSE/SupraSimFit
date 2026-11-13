"""The Input uncertainty view: what its controls hand to the session model, and what it shows of it.

- a typed amount reaches the model's settings before the field loses focus, so a run
  started from the toolbar reads the number on screen;
- a fixed input shows no amount, a range two, and the titrant offers percent only;
- a shared source is stated with a name, a σ and ticks named as the inputs are, and its
  problems show on its own row; the additions entry's σ and replicates are statements
  about a mode, open only once one is chosen;
- every control locks while a run reads the statement;
- the canvas is as wide whichever kind each input shows;
- Tab runs through the inputs, the sources, then the additions entry.

Require a ``QApplication`` (the ``qapp`` fixture).
"""

from __future__ import annotations

import pytest

pytest.importorskip('PyQt6')

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QLabel, QWidget  # noqa: E402

from core.assays.registry import AssayType  # noqa: E402
from core.pipeline.inputs import TITRANT, AdditionError, InputSpec, SharedSource  # noqa: E402
from core.units import Q_  # noqa: E402


@pytest.fixture
def view(qapp):
    from gui.session_model import SessionModel
    from gui.views.uncertainty import UncertaintyView

    parent = QWidget()
    model = SessionModel(parent)
    model.uncertainty.set_assay(AssayType.IDA)
    model.uncertainty.set_conditions(
        {'Ka_dye': Q_(16.8e6, '1/M'), 'h0': Q_(4.3e-6, 'M'), 'd0': Q_(6e-6, 'M')},
        {'Ka_dye': 'M⁻¹', 'h0': 'µM', 'd0': 'µM'},
    )
    model.uncertainty_edited()
    v = UncertaintyView(model, parent)
    v.canvas.resize(900, 1200)
    v.canvas.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    v.canvas.show()
    qapp.processEvents()
    yield v
    v.canvas.close()


def _shown(widget: QWidget, view) -> bool:
    return widget.isVisibleTo(view.canvas)


def test_a_typed_amount_reaches_the_model_before_the_field_loses_focus(view):
    row = view._rows['Ka_dye']
    row.kind._choose(1)  # σ
    editor = row.fields[0].editor
    editor.selectAll()
    QTest.keyClicks(editor, '12')

    assert view.model.settings.errors.specs == {'Ka_dye': InputSpec.sigma_pct(12.0)}
    QTest.keyClicks(editor, 'x')
    assert view.model.settings.input_problems == ('Ka,dye: “12x” is not a number. Enter a number, or choose “Fixed”.',)
    assert _shown(row.problem, view)


def test_a_fixed_input_shows_no_amount_a_range_two_and_the_titrant_percent_only(view):
    row = view._rows['h0']
    assert not any(_shown(field, view) for field in row.fields) and not _shown(row.unit, view)
    assert row.span.text() == 'taken as exact'

    row.kind._choose(2)  # Range
    assert [_shown(field, view) for field in row.fields] == [False, True, True]
    assert view.model.settings.errors.specs == {'h0': InputSpec.interval_pct(-5.0, 5.0)}
    assert row.span.text() == '4.08 – 4.52 µM'

    row.unit._choose(1)  # µM
    assert [field.editor.text() for field in row.fields[1:]] == ['4.085', '4.515']

    titrant = view._rows[TITRANT]
    titrant.kind._choose(1)
    titrant.unit._choose(1)  # offered greyed out: the titrant has no single value
    assert view.model.uncertainty.entry(TITRANT).relative


def test_a_shared_source_is_stated_on_its_own_row_with_its_problems(view, qapp):
    from gui.plotting.labels import plain_label

    view.add_source.click()
    qapp.processEvents()  # a row added to a shown layout is shown once its events are handled
    (source,) = view._sources
    assert {key: plain_label(box.text) for key, box in source.ticks.items()} == view.model.uncertainty.input_labels()
    assert all(box.rich for box in source.ticks.values())
    assert _shown(source.problem, view)  # it applies to no input yet

    for key in ('h0', 'd0'):
        QTest.mouseClick(source.ticks[key], Qt.MouseButton.LeftButton)
    source.name.editor.selectAll()
    QTest.keyClicks(source.name.editor, 'Host and dye stock')

    assert view.model.settings.errors.shared == (SharedSource('Host and dye stock', 5.0, ('h0', 'd0')),)
    assert not _shown(source.problem, view)
    assert view.badge() == '2 inputs vary'

    view._sources[0].remove.click()
    assert view._sources == [] and view.model.settings.errors.shared == ()
    assert view.badge() is None


def test_the_additions_sigma_and_replicates_are_open_only_once_a_mode_is_chosen(view):
    assert not view.replicates.isEnabled() and not _shown(view.sigma_row, view)

    view.mode._choose(1)
    assert view.replicates.isEnabled() and _shown(view.sigma_row, view)
    view.replicates._choose(1)
    assert view.model.settings.errors.additions == AdditionError(5.0, sequential=True, separate_titrations=False)

    view.add_sigma.editor.selectAll()
    QTest.keyClicks(view.add_sigma.editor, '0')
    assert _shown(view.add_problem, view)


def test_every_control_locks_while_a_run_reads_the_statement(view):
    view.add_source.click()
    view.mode._choose(2)
    controls = [
        *(control for row in view._rows.values() for control in row.controls()),
        view._sources[0].name,
        view._sources[0].sigma,
        *view._sources[0].ticks.values(),
        view.add_source,
        view.mode,
        view.replicates,
        view.add_sigma,
    ]

    view.set_locked(True)
    assert not any(control.isEnabled() for control in controls)
    view.set_locked(False)
    assert all(control.isEnabled() for control in controls)
    # The end of a run opens the replicates only while an error of the additions is stated.
    view.mode._choose(0)
    view.set_locked(True)
    view.set_locked(False)
    assert not view.replicates.isEnabled()


def test_the_canvas_is_as_wide_whichever_kind_each_input_shows(view, qapp):
    widths = set()
    for kind in (0, 1, 2):
        for row in view._rows.values():
            row.kind._choose(kind)
        qapp.processEvents()
        widths.add(view.canvas.widget().minimumSizeHint().width())
    view.model.uncertainty.set_spec('h0', InputSpec.interval_pct(5.0, 0.0))
    view.model.uncertainty_edited()
    qapp.processEvents()
    widths.add(view.canvas.widget().minimumSizeHint().width())

    assert len(widths) == 1


def test_an_assay_with_no_association_constant_shows_why_instead_of_the_form(view):
    view.model.uncertainty.set_assay(AssayType.DYE_ALONE)
    view.model.uncertainty_edited()

    assert not _shown(view.sections, view)
    assert _shown(view.unavailable, view)
    assert 'has no association constant' in view.unavailable.text()


def test_tab_runs_through_the_inputs_the_sources_then_the_additions(view):
    view.add_source.click()
    expected = [widget for row in view._rows.values() for widget in row.focus_chain()]
    expected += [*view._sources[0].focus_chain(), view.add_source, view.mode, view.replicates, view.add_sigma.editor]

    reached, widget = [], expected[0]
    for _ in range(600):
        widget = widget.nextInFocusChain()
        if widget is expected[0]:
            break
        if widget in expected:
            reached.append(widget)
    assert reached == expected[1:]


def test_with_no_fit_the_side_panel_says_so(view):
    assert view.no_fit.isVisibleTo(view.side)
    assert view.no_fit.text().startswith('No fit is shown.')
    assert not view.tests_section.isVisibleTo(view.side)


def test_about_input_uncertainty_opens_the_help(view, monkeypatch):
    seen = []
    monkeypatch.setattr('gui.views.uncertainty.show_help', lambda parent, title, html: seen.append((title, html)))

    view.help_link.click()

    assert seen and seen[0][0] == 'Input uncertainty' and 'Shared error sources' in seen[0][1]


def _aware_fit():
    """An IDA fit whose inputs moved further than stated: the conflict rejects, the curve fits once they move."""
    import numpy as np

    from core.pipeline.diagnostics import Conflict, FitDiagnostics, InputShift, MisfitTest, Verdict
    from core.pipeline.fit_pipeline import ConditionalFit, FitResult
    from core.pipeline.varpro import KaInterval

    x = np.linspace(0, 1e-4, 20)
    parameters = {
        'Ka_guest': Q_(1.30e6, '1/M'),
        'I0': Q_(100.0, 'au'),
        'I_dye_free': Q_(5e4, 'au/M'),
        'I_dye_bound': Q_(8e4, 'au/M'),
    }
    return FitResult(
        parameters=parameters,
        rmse=0.005,
        r_squared=0.998,
        x_fit=Q_(x, 'M'),
        y_fit=Q_(x, 'au'),
        assay_type='IDA',
        model_name='equilibrium_4param',
        fit_config={
            'per_replicate': False,
            'level': 0.95,
            'input_uncertainty': {
                key: {'kind': 'sigma', 'sigma': 3.0, 'lo': 0.0, 'hi': 0.0, 'relative': True} for key in ('h0', 'd0')
            },
        },
        intervals={'Ka_guest': KaInterval(0.5e6, 3.0e6, False, False, 0.95, 16)},
        conditions={'h0': Q_(4.3e-6, 'M'), 'd0': Q_(6e-6, 'M'), 'Ka_dye': Q_(1.68e7, '1/M')},
        input_shifts={'h0': InputShift('h0', -0.09, -3.0, False), 'd0': InputShift('d0', 0.08, 2.7, False)},
        diagnostics=FitDiagnostics(
            conditional_misfit=MisfitTest('lack_of_fit', 4.0, 0.004, dof=(9, 72)),
            misfit=MisfitTest('lack_of_fit', 0.9, 0.55, dof=(9, 72)),
            conflict=Conflict(q=16.0, k=2, p_value=0.0004, weights=(0.5, 0.9)),
            verdict=Verdict.INPUTS_CONFLICT,
        ),
        conditional=ConditionalFit(
            parameters={**parameters, 'Ka_guest': Q_(1.24e6, '1/M')},
            intervals={'Ka_guest': KaInterval(0.7e6, 2.2e6, False, False, 0.95, 16)},
            rmse=0.006,
            r_squared=0.997,
        ),
    )


def test_the_side_panel_sets_the_input_aware_interval_beside_the_one_at_the_inputs_as_entered(view):
    view.model._held_fit_results = [_aware_fit()]
    view.model.results_changed.emit('all')

    (chart,) = view.charts
    assert [(row['label'], row['color'], row['text']) for row in chart.rows] == [
        ('Input-aware', 'accent', '1.30  [0.500, 3.00]'),
        ('Inputs as entered', 'text-secondary', '1.24  [0.700, 2.20]'),
    ]
    assert view.unit_lines[0].text() == 'K<sub>a</sub> guest, 95 % interval, × 10⁶ M⁻¹'
    assert view.interval_caption.text() == (
        'Letting the inputs move within what you stated widens the interval beyond the one with the inputs as entered.'
    )
    assert not view.no_fit.isVisibleTo(view.side)


def test_the_tests_are_marked_as_judged_and_a_conflict_names_no_input(view):
    from gui.design import components as C

    view.model._held_fit_results = [_aware_fit()]
    view.model.results_changed.emit('all')

    rows = [view.test_rows.itemAt(i).widget() for i in range(view.test_rows.count())]
    marks = [(row.findChild(C.Icon).tone, [label.text() for label in row.findChildren(QLabel)]) for row in rows]
    assert marks == [
        ('success', ['Curve fits with inputs moved', 'p = 0.55']),
        ('warning', ['Misfit at inputs as entered', 'p = 0.004']),
        ('warning', ['Inputs conflict', 'p < 0.001']),
    ]
    caption = view.tests_caption.text()
    assert 'does not say which of them is off' in caption
    assert '[Host]' not in caption and '[Dye]' not in caption


def _show(view, fit, rows=None, monkeypatch=None) -> None:
    """Show *fit* as the session's latest; with *rows*, its summary rows are edited by them first."""
    if rows is not None:
        from dataclasses import replace

        from core.pipeline.reporting import summarize_parameters

        edited = [
            replace(row, **rows) if row.key == 'Ka_guest' and not row.is_log else row
            for row in summarize_parameters(fit)
        ]
        monkeypatch.setattr('gui.views.uncertainty.summarize_parameters', lambda _fit: edited)
    view.model._held_fit_results = [fit]
    view.model.results_changed.emit('all')


def _additions_only_fit():
    """Every input fixed, only a random error of each addition stated: no input moved."""
    from dataclasses import replace

    from core.pipeline.inputs import ErrorModel

    fit = _aware_fit()
    errors = ErrorModel(additions=AdditionError(2.0, sequential=True, separate_titrations=True))
    return replace(fit, input_shifts={}, fit_config={'per_replicate': False, 'level': 0.95, **errors.to_dict()})


def test_the_caption_names_the_stated_error_of_the_additions_where_no_input_moved(view):
    _show(view, _additions_only_fit())

    caption = view.interval_caption.text()
    assert caption == (
        'The random error of each addition you stated widens the interval beyond the one with the inputs as entered.'
    )
    assert 'inputs move' not in caption


def test_a_fit_with_no_association_constant_says_it_has_no_interval(view):
    import numpy as np

    from core.pipeline.fit_pipeline import FitResult

    x = np.linspace(0, 1e-5, 10)
    fit = FitResult(
        parameters={'slope': Q_(2e9, 'au/M'), 'intercept': Q_(10.0, 'au')},
        rmse=0.01,
        r_squared=0.999,
        x_fit=Q_(x, 'M'),
        y_fit=Q_(x, 'au'),
        assay_type='DYE_ALONE',
        model_name='linear',
        fit_config={'per_replicate': False},
    )
    _show(view, fit)

    assert view.charts == []
    assert view.interval_caption.text() == 'This fit has no association constant, so it has no interval.'


def test_a_fit_whose_association_constant_records_no_interval_says_so(view):
    """A Ka held fixed, or read from a results file that carries no interval, has a constant and no interval."""
    from dataclasses import replace

    _show(view, replace(_aware_fit(), intervals=None, conditional=None, input_shifts={}, diagnostics=None))

    assert view.charts == []
    assert view.interval_caption.text() == 'This fit records no interval for K<sub>a</sub> guest.'
    assert view.interval_caption.textFormat() == Qt.TextFormat.RichText
    assert view.interval_caption.isVisibleTo(view.side)


def test_a_constant_with_no_interval_is_named_beside_the_one_drawn(view):
    import numpy as np

    from core.pipeline.fit_pipeline import FitResult
    from core.pipeline.varpro import KaInterval

    x = np.linspace(0, 1e-4, 20)
    signal = {key: Q_(1e4, 'au/M') for key in ('I_G', 'I_H', 'I_HG', 'I_HG2')}
    fit = FitResult(
        parameters={'Ka_HG': Q_(1.3e6, '1/M'), 'Ka_HG2': Q_(2e4, '1/M'), 'I0': Q_(100.0, 'au'), **signal},
        rmse=0.005,
        r_squared=0.998,
        x_fit=Q_(x, 'M'),
        y_fit=Q_(x, 'au'),
        assay_type='DBA_HG2',
        model_name='stepwise',
        fit_config={'per_replicate': False, 'level': 0.95},
        intervals={'Ka_HG': KaInterval(0.5e6, 3.0e6, False, False, 0.95, 16)},
    )
    _show(view, fit)

    assert len(view.charts) == 1
    assert view.unit_lines[0].text().startswith('K<sub>a</sub> HG, ')
    assert view.interval_caption.text().endswith(' This fit records no interval for K<sub>a</sub> HG₂.')


def test_an_open_end_is_said_in_the_words_every_view_uses_and_sets_no_power_of_ten(view, monkeypatch):
    """The shared power of ten comes from the numbers written; an end at the search bound is written in words."""
    _show(
        view,
        _aware_fit(),
        dict(
            estimate=1.6e8,
            interval=(1.1e8, 1e12),
            interval_open=(False, True),
            conditional_estimate=1.65e8,
            conditional_interval=(1.3e8, 2.1e8),
        ),
        monkeypatch,
    )

    (chart,) = view.charts
    assert [row['text'] for row in chart.rows] == ['1.60  [1.10, no upper limit]', '1.65  [1.30, 2.10]']
    assert view.unit_lines[0].text().endswith('× 10⁸ M⁻¹')


def test_a_closed_end_far_below_the_others_never_reads_zero(view, monkeypatch):
    _show(
        view,
        _aware_fit(),
        dict(estimate=1.6e8, interval=(1.1e5, 2.0e8), conditional_estimate=1.65e8, conditional_interval=(1.3e8, 1.9e8)),
        monkeypatch,
    )

    assert view.charts[0].rows[0]['text'] == '1.60  [1.10×10⁻³, 2.00]'


def test_an_estimate_on_a_bound_reads_as_every_view_writes_it(view, monkeypatch):
    _show(
        view,
        _aware_fit(),
        dict(
            estimate=1e3,
            estimate_at_bound='low',
            interval=(1e3, 2.08e8),
            interval_open=(True, False),
            conditional_estimate=1.65e8,
            conditional_interval=(1.3e8, 2.1e8),
        ),
        monkeypatch,
    )

    rows = view.charts[0].rows
    assert rows[0]['text'] == 'not limited below 2.08' and rows[0]['est'] is None
    assert view.unit_lines[0].text().endswith('× 10⁸ M⁻¹')


def _profile(fit, grid, r2, cut):
    import numpy as np

    from core.pipeline.profile import ProfileResult, ProfileSet

    interval = fit.conditional.intervals['Ka_guest']
    result = ProfileResult(
        ka_key='Ka_guest',
        grid=np.asarray(grid, dtype=float),
        r2=np.asarray(r2, dtype=float),
        replica_r2=None,
        best_ka=1.24e6,
        best_r2=max(r2),
        interval=interval,
        r2_threshold=cut,
        n_points=20,
        n_params=4,
        per_replica=False,
    )
    return ProfileSet(profiles={'Ka_guest': result}, region=None)


def _split_fit():
    from dataclasses import replace

    from core.pipeline.varpro import KaInterval

    fit = _aware_fit()
    split = KaInterval(0.7e6, 2.2e6, False, False, 0.95, 16, split=True)
    return replace(fit, conditional=replace(fit.conditional, intervals={'Ka_guest': split}))


def test_a_split_interval_draws_each_accepted_stretch_as_its_own_bar(view):
    """The values between the stretches are rejected, so no bar runs across them (DESIGN.md §6)."""
    fit = _split_fit()
    grid = [0.5e6, 0.7e6, 0.9e6, 1.0e6, 1.2e6, 1.24e6, 1.6e6, 2.2e6, 3.0e6]
    r2 = [0.90, 0.99, 0.995, 0.97, 0.98, 0.999, 0.996, 0.99, 0.90]
    view.model._profiled_fit = fit
    view.model._profile = _profile(fit, grid, r2, 0.985)
    _show(view, fit)

    entered = view.charts[0].rows[1]
    assert entered['label'] == 'Inputs as entered · Split'
    assert entered['segments'] == [(0.7e6, 0.9e6), (1.24e6, 2.2e6)]


def test_a_split_interval_without_its_stretches_says_so_instead_of_bridging_the_gap(view):
    fit = _split_fit()
    _show(view, fit)

    entered = view.charts[0].rows[1]
    assert entered['segments'] == [] and entered['est'] is None
    assert entered['note'] == 'No Kₐ profile, so the stretches are not drawn'


def test_every_control_is_named_and_an_amount_names_its_unit(view, qapp):
    row = view._rows['h0']
    row.kind._choose(1)  # σ
    assert row.fields[0].editor.accessibleName() == 'σ of the uncertainty of [Host]₀ (%)'
    row.unit._choose(1)  # µM
    assert row.fields[0].editor.accessibleName() == 'σ of the uncertainty of [Host]₀ (µM)'
    row.kind._choose(2)
    assert [field.editor.accessibleName() for field in row.fields[1:]] == [
        'Lower end of the uncertainty of [Host]₀ (µM)',
        'Upper end of the uncertainty of [Host]₀ (µM)',
    ]
    assert view.add_source.accessibleName() == 'Add shared source'


def test_the_inputs_grid_takes_its_sizes_from_the_tokens(view):
    from gui.design.tokens import SIZE

    widths = [view.grid.columnMinimumWidth(c) for c in (0, 1, 3, 4)]
    assert widths == [SIZE['input-name'], SIZE['input-kind'], SIZE['stated-in'], SIZE['spread-bar']]
