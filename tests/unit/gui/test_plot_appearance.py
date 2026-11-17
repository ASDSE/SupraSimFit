"""Tests of the plot appearance's rules (:mod:`gui.plot_appearance`), where it is stored and how a session holds it.

No widget here: the record and its refusals, what the built-in appearance draws with
(DESIGN.md §7), the preference new sessions start from, and the session model's copy,
duplicate and results-file round trip. What the plot draws with it is pinned by
``test_plot_appearance_view.py``.
"""

from __future__ import annotations

import json
import uuid

import pytest

from gui.design.tokens import DARK, LIGHT

pytest.importorskip('PyQt6')

from gui.plot_appearance import (  # noqa: E402
    BUILT_IN,
    COLOURS,
    MARKER_SIZES,
    SHAPES,
    TEXT_SIZES,
    WIDTHS,
    PlotAppearance,
)
from gui.session_model import Change  # noqa: E402

#: An appearance that differs from the built-in one in every field.
CHANGED = PlotAppearance(
    replicate_size='large',
    mean_size='small',
    replicate_shape='triangle',
    fit_width='thick',
    error_bar_width='medium',
    replicate_colour='grey',
    fit_colour='magenta',
    text_size='larger',
)


@pytest.fixture
def store(qapp):
    """A preference store of this test's own, empty before and after."""
    from PyQt6.QtCore import QCoreApplication, QSettings

    QCoreApplication.setApplicationName(f'plot_appearance_{uuid.uuid4().hex[:8]}')
    QSettings().clear()
    yield QSettings()
    QSettings().clear()


# ── The record ─────────────────────────────────────────────────────────────────────


def test_the_built_in_appearance_draws_the_titration_as_the_design_specifies():
    """DESIGN.md §7: replicate n in ``replicate-n``, 6-px dots and means, 1-px error bars, a 2-px accent curve, standard axis text."""
    look = BUILT_IN

    assert (look.replicate_px, look.mean_px, look.symbol) == (6, 6, 'o')
    assert look.cross_px == 7  # the × of a replicate switched off
    assert (look.fit_px, look.error_bar_px) == (2, 1)
    assert [look.replicate_mark(i) for i in (0, 1, 11)] == [
        ('replicate-1', 'o'),
        ('replicate-2', 'o'),
        ('replicate-12', 'o'),
    ]
    assert look.text_step == 'standard'


def test_every_field_survives_a_round_trip_through_json():
    written = json.loads(json.dumps(CHANGED.to_dict()))

    assert PlotAppearance.from_dict(written) == CHANGED
    assert all(getattr(CHANGED, k) != getattr(BUILT_IN, k) for k in written)  # CHANGED moves every field


def test_a_record_that_leaves_a_field_out_keeps_the_built_in_choice_for_it():
    assert PlotAppearance.from_dict({'fit_colour': 'blue'}) == PlotAppearance(fit_colour='blue')


@pytest.mark.parametrize('single', ['blue', 'magenta'])
def test_a_record_stating_a_replicate_colour_this_version_does_not_offer_is_refused(single):
    """A record whose replicate colour the menu does not offer is refused in words naming the choices,
    never drawn in another colour without a word: the app draws what the user chose or says it cannot."""
    with pytest.raises(ValueError) as refused:
        PlotAppearance.from_dict({'replicate_colour': single})

    said = str(refused.value)
    assert f'“{single}”' in said and all(key in said for key in COLOURS)


def test_grey_draws_every_replicate_in_one_colour_with_the_mark_chosen():
    look = PlotAppearance(replicate_colour='grey', replicate_shape='square')

    assert {look.replicate_mark(i) for i in range(20)} == {('replicate', 's')}


@pytest.mark.parametrize(
    ('record', 'said'),
    [
        ({'replicate_colour': '#ff0000'}, 'the colour of the replicate points'),
        ({'replicate_size': 12}, 'the size of the replicate points'),
        ({'line_style': 'dash'}, 'line_style'),
        (['medium'], 'holds no settings'),
    ],
)
def test_a_record_this_version_cannot_draw_is_refused_in_plain_words(record, said):
    with pytest.raises(ValueError) as refused:
        PlotAppearance.from_dict(record)

    assert said in str(refused.value)
    assert 'Traceback' not in str(refused.value) and 'KeyError' not in str(refused.value)


@pytest.mark.parametrize(
    ('record', 'name'),
    [({'fit_width': 'hairline'}, 'fit_width'), ({'replicate_size': 'Small'}, 'replicate_size')],
)
def test_a_refusal_names_the_values_a_record_may_hold(record, name):
    """The refusal lists what a record may hold, so each value it offers is one a record is read with —
    a label shown in the menu (``Small``) is not, and is never offered as if it were."""
    from gui.plot_appearance import menu

    with pytest.raises(ValueError) as refused:
        PlotAppearance.from_dict(record)

    said = str(refused.value)
    offered = list(menu(name))
    assert all(f'{key}' in said for key in offered)
    for key in offered:
        PlotAppearance.from_dict({name: key})  # every value it offers is read
    assert all(label not in said.split('“')[-1].split('”')[-1] for label, *_ in menu(name).values())


def test_the_replicates_never_take_the_colour_of_the_means_and_the_curve_is_built_in_accent():
    """DESIGN.md §7: the means are ``text-primary``, so no replicate choice draws in it; the
    fitted curve is ``accent`` unless the user picks another of its menu."""
    from gui.plot_appearance import FIT_COLOURS

    assert 'text-primary' not in {token for _label, tokens in COLOURS.values() for token in tokens}
    assert BUILT_IN.fit_token == 'accent'
    assert PlotAppearance.from_dict({'fit_colour': 'blue'}).fit_token == 'series-1'
    assert all(token in LIGHT and token in DARK for _label, token in FIT_COLOURS.values())


def test_every_tick_label_has_tabular_figures(qapp):
    """DESIGN.md §2: numbers use tabular figures so a column of tick labels aligns digit for digit."""
    from PyQt6.QtGui import QFont

    from gui.design.tokens import plot_font

    assert all(plot_font(step, 'tick').featureValue(QFont.Tag('tnum')) == 1 for _label, step in TEXT_SIZES.values())


def test_every_choice_maps_to_a_token_of_both_themes_and_a_step_of_the_plot_text():
    """No menu offers a value outside the tokens, so a choice keeps both themes and the plot text scale."""
    from gui.design.tokens import PLOT_TEXT, SIZE

    assert all(token in SIZE for _label, token in (*MARKER_SIZES.values(), *WIDTHS.values()))
    assert all(token in LIGHT and token in DARK for _label, tokens in COLOURS.values() for token in tokens)
    assert [step for _label, step in TEXT_SIZES.values()] == list(PLOT_TEXT)
    assert {symbol for _label, symbol in SHAPES.values()} == {'o', 's', 't1'}


@pytest.mark.parametrize('part', ['tick', 'title'])
def test_the_plot_text_rises_in_even_steps_of_at_least_two_px_at_one_weight(qapp, part):
    """DESIGN.md §8: Standard → Large → Larger are two equal steps — one ratio within 5 %, each at least
    2 px — and the weight is the same at every step, so a larger size changes the size and nothing else."""
    from gui.design.tokens import plot_font

    fonts = [plot_font(step, part) for _label, step in TEXT_SIZES.values()]
    sizes = [f.pixelSize() for f in fonts]
    ratios = [b / a for a, b in zip(sizes, sizes[1:], strict=False)]

    assert all(b - a >= 2 for a, b in zip(sizes, sizes[1:], strict=False)), sizes
    assert max(ratios) / min(ratios) <= 1.05, ratios
    assert len({f.weight() for f in fonts}) == 1


# ── The preference new sessions start from ─────────────────────────────────────────


def test_with_nothing_stored_new_sessions_start_from_the_built_in_appearance(store):
    from gui.preferences import plot_appearance_default

    assert plot_appearance_default() == BUILT_IN


def test_the_stored_appearance_is_read_back_and_a_reset_gives_the_built_in_one_again(store):
    from gui.preferences import plot_appearance_default, reset_plot_appearance_default, set_plot_appearance_default

    set_plot_appearance_default(CHANGED)
    store.sync()
    assert plot_appearance_default() == CHANGED

    reset_plot_appearance_default()
    assert plot_appearance_default() == BUILT_IN


# ── A session's appearance ─────────────────────────────────────────────────────────


@pytest.fixture
def make_model(store):
    from gui.session_model import SessionModel

    models = []

    def build():
        models.append(SessionModel())
        return models[-1]

    yield build
    for model in models:
        model.shutdown()


def test_a_new_session_starts_from_the_stored_appearance_and_else_from_the_built_in_one(make_model):
    from gui.preferences import set_plot_appearance_default

    assert make_model().plot_appearance == BUILT_IN
    set_plot_appearance_default(CHANGED)
    made = make_model()
    assert made.plot_appearance == CHANGED


def test_a_stored_choice_this_version_does_not_offer_is_the_built_in_one_and_the_rest_are_kept(make_model):
    from PyQt6.QtCore import QSettings

    from gui.preferences import PLOT_APPEARANCE_KEY

    QSettings().setValue(PLOT_APPEARANCE_KEY, json.dumps({'replicate_colour': 'blue', 'replicate_size': 'large'}))

    assert make_model().plot_appearance == PlotAppearance(replicate_size='large')


def test_setting_an_appearance_says_so_once_and_setting_it_again_says_nothing(make_model):
    model = make_model()
    said = []
    model.changed.connect(lambda what: said.append(model.plot_appearance) if Change.APPEARANCE in what else None)

    model.set_plot_appearance(CHANGED)
    model.set_plot_appearance(CHANGED)

    assert said == [CHANGED]


def test_a_duplicate_session_takes_the_appearance_of_the_one_it_copies(make_model):
    source, copy = make_model(), make_model()
    source.set_plot_appearance(CHANGED)
    said = []
    copy.changed.connect(lambda what: said.append(Change.APPEARANCE in what))

    copy.copy_from(source)

    assert copy.plot_appearance == CHANGED and said == [True]


def test_a_results_file_carries_the_appearance_to_the_session_that_imports_it(make_model, tmp_path):
    from gui.session import export_results, import_appearance, import_results

    path = tmp_path / 'r.json'
    export_results([], path, CHANGED)
    model = make_model()

    model.show_imported(import_results(path), str(path), import_appearance(path))

    assert model.plot_appearance == CHANGED


def test_a_results_file_without_an_appearance_leaves_the_session_s_own(make_model, tmp_path):
    from gui.session import import_appearance

    path = tmp_path / 'r.json'
    path.write_text(json.dumps([]))  # a list of results, the file written without the session's appearance
    model = make_model()
    model.set_plot_appearance(CHANGED)

    model.show_imported([], str(path), import_appearance(path))

    assert import_appearance(path) is None and model.plot_appearance == CHANGED


def test_a_results_file_keeps_its_results_beside_the_appearance(tmp_path):
    from gui.session import export_results, import_results
    from tests.unit.gui.test_results import aware_result

    result = aware_result()
    path = tmp_path / 'r.json'
    export_results([result], path, CHANGED)

    (read,) = import_results(path)

    assert read.to_dict() == result.to_dict()
