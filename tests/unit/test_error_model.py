"""The error model of a titration's inputs: independent sources, shared ones, and the additions.

- ``ErrorModel.input_offsets`` multiplies the ``1 + e`` of the sources that move
  an input, checked against the perturbed input computed by hand; with no
  shared source it hands the offsets through float for float, which is what
  keeps a fit without shared sources on the arithmetic it has always had. A
  shared source moves a binding constant measured with it by ``1 / (1 + e)``,
  checked against the association constant the law of mass action gives when
  every concentration of its measurement is read off by the same factor.
- ``validate`` refuses a source that states no error a titration can have, in a
  sentence that names it, and ``source_problems`` lists every fault of every
  source so the panel can state them all before a run.
- The model's entries in a results file: a model without shared sources writes
  the per-input layout alone, and a ``fit_config`` holding only that reads back;
  whether the replicates are separate titrations survives, and a file that does
  not say reads as separate titrations.
- ``perturb_titrant`` against an explicit simulation of the volumes pipetted,
  and against the law of accumulated errors for equal aliquots;
  ``addition_loading`` against central differences of it.
"""

import numpy as np
import pytest

from core.pipeline.inputs import (
    ADDITIONS,
    TITRANT,
    AdditionError,
    ErrorModel,
    InputSpec,
    SharedSource,
    addition_loading,
    perturb_titrant,
    shared_key,
    source_name,
    source_problems,
    specs_to_dict,
    validate,
)
from core.pipeline.varpro import FitRefused
from core.units import Q_

_IDA = {'Ka_dye': Q_(1e6, '1/M'), 'h0': Q_(1e-5, 'M'), 'd0': Q_(5e-6, 'M')}
_LABELS = {'Ka_dye': 'Ka(dye)', 'h0': '[Host]0', 'd0': '[Dye]0', TITRANT: 'Guest (titrant)'}
_STOCK = SharedSource('Host and dye stock', 4.0, ('h0', 'd0'))
_BALANCE = SharedSource('Balance', 1.0, ('d0', TITRANT))


# -- sources and what they move ----------------------------------------------------


def test_an_input_is_moved_by_the_product_of_its_sources():
    errors = ErrorModel(
        specs={'h0': InputSpec.sigma_pct(3), 'Ka_dye': InputSpec.sigma_pct(10)}, shared=(_STOCK, _BALANCE)
    )
    e = {'h0': 0.02, 'Ka_dye': -0.07, shared_key(_STOCK.name): -0.05, shared_key(_BALANCE.name): 0.011}
    moved = errors.input_offsets(e, _IDA)

    # The perturbed inputs written out by hand from entered * prod(1 + e).
    h0, d0 = 1e-5, 5e-6
    assert set(moved) == {'h0', 'Ka_dye', 'd0', TITRANT}
    assert h0 * (1 + moved['h0']) == pytest.approx(h0 * 1.02 * 0.95, rel=1e-15)
    assert d0 * (1 + moved['d0']) == pytest.approx(d0 * 0.95 * 1.011, rel=1e-15)
    # One source alone: its own float, with no round trip through 1 + e.
    assert moved['Ka_dye'] == e['Ka_dye'] and moved[TITRANT] == e[shared_key(_BALANCE.name)]


def test_without_a_shared_source_the_offsets_pass_float_for_float():
    errors = ErrorModel(specs={'h0': InputSpec.sigma_pct(3), TITRANT: InputSpec.interval_pct(-2, 2)})
    e = {'h0': 0.1 + 0.2, TITRANT: -1e-17, 'd0': 0.3}
    moved = errors.input_offsets(e, _IDA)
    assert moved == e and list(moved) == list(e) and moved is not e
    assert all(moved[key].hex() == e[key].hex() for key in e)


def test_a_shared_source_moves_a_binding_constant_measured_with_it_the_other_way():
    """A stock whose true concentration is ``1 + e`` times the one assumed, behind [Host]0 and an earlier Ka(dye).

    The earlier measurement read every concentration ``1 / (1 + e)`` times its
    true value, so the constant it reported, ``[HD] / ([H] [D])`` by the law of
    mass action, is ``1 + e`` times the true one: the true Ka(dye) is the entered
    one over ``1 + e``, while the true [Host]0 is the entered one times it.
    """
    e = 0.05
    free_h, free_d, bound = 3e-6, 2e-6, 4e-6  # true equilibrium concentrations of that measurement
    true_ka = bound / (free_h * free_d)
    reported_ka = (bound / (1 + e)) / ((free_h / (1 + e)) * (free_d / (1 + e)))
    entered = {**_IDA, 'Ka_dye': Q_(reported_ka, '1/M')}
    stock = SharedSource('Host stock', 4.0, ('h0', 'Ka_dye'))
    errors = ErrorModel(shared=(stock,))

    moved = errors.input_offsets({shared_key(stock.name): e}, entered)

    assert errors.powers(shared_key(stock.name), entered) == {'h0': 1, 'Ka_dye': -1}
    assert reported_ka * (1 + moved['Ka_dye']) == pytest.approx(true_ka, rel=1e-12)
    assert 1 + moved['h0'] == pytest.approx(1 + e, rel=1e-15)
    # Its own error moves a binding constant as stated: only a shared stock inverts.
    assert ErrorModel(specs={'Ka_dye': InputSpec.sigma_pct(5)}).powers('Ka_dye', entered) == {'Ka_dye': 1}


def test_a_source_behind_every_input_is_a_change_of_the_concentration_unit():
    """Every concentration times ``1 + e`` and every entered binding constant over it: the scaling the models are homogeneous in."""
    everything = SharedSource('Everything', 4.0, ('Ka_dye', 'h0', 'd0', TITRANT))
    errors = ErrorModel(specs={'h0': InputSpec.sigma_pct(3)}, shared=(everything,))

    moved = errors.input_offsets({'h0': 0.02, shared_key(everything.name): 0.1}, _IDA)

    assert 1 + moved['d0'] == pytest.approx(1.1, rel=1e-15) and 1 + moved[TITRANT] == pytest.approx(1.1, rel=1e-15)
    assert 1 + moved['Ka_dye'] == pytest.approx(1 / 1.1, rel=1e-15)
    assert 1 + moved['h0'] == pytest.approx(1.02 * 1.1, rel=1e-15)
    assert errors.loading(_IDA)({shared_key(everything.name): 0.1}) == errors.input_offsets(
        {shared_key(everything.name): 0.1}, _IDA
    )
    assert ErrorModel(specs={'h0': InputSpec.sigma_pct(3)}).loading(_IDA) is None


def test_sources_are_listed_own_first_then_shared_and_say_what_they_move():
    errors = ErrorModel(
        specs={TITRANT: InputSpec.sigma_pct(2), 'd0': InputSpec.sigma_pct(0), 'h0': InputSpec.interval_pct(-5, 5)},
        shared=(_STOCK, _BALANCE),
    )
    sources = errors.source_specs()
    assert list(sources) == [TITRANT, 'h0', shared_key(_STOCK.name), shared_key(_BALANCE.name)]
    assert sources['h0'] == InputSpec.interval_pct(-5, 5)
    assert sources[shared_key(_STOCK.name)] == InputSpec.sigma_pct(4.0)

    assert errors.loaded('h0') == ('h0',)
    assert errors.loaded(shared_key(_BALANCE.name)) == ('d0', TITRANT)
    assert errors.loaded(ADDITIONS) == (TITRANT,)
    assert source_name(shared_key(_STOCK.name), _LABELS) == _STOCK.name
    assert source_name('h0', _LABELS) == '[Host]0'
    assert 'addition' in source_name(ADDITIONS, _LABELS)


def test_varies_says_whether_any_source_moves_anything():
    assert not ErrorModel().varies
    assert not ErrorModel(specs={'h0': InputSpec.sigma_pct(0)}).varies
    assert ErrorModel(specs={'h0': InputSpec.sigma_pct(1)}).varies
    assert ErrorModel(shared=(_STOCK,)).varies
    assert ErrorModel(additions=AdditionError(1.0, True)).varies


# -- refusals ----------------------------------------------------------------------


@pytest.mark.parametrize(
    'errors, message',
    [
        (ErrorModel(shared=(SharedSource('  ', 4.0, ('h0', 'd0')),)), 'has no name'),
        (ErrorModel(shared=(_STOCK, SharedSource(_STOCK.name, 1.0, ('h0', TITRANT)))), "named 'Host and dye stock'"),
        (ErrorModel(shared=(SharedSource('Pipette', 0.0, ('h0', 'd0')),)), "'Pipette' has to be above zero"),
        (ErrorModel(shared=(SharedSource('Pipette', float('nan'), ('h0', 'd0')),)), "'Pipette' has to be above zero"),
        (
            ErrorModel(shared=(SharedSource('Host stock', 4.0, ('h0',)),)),
            "A shared error source has to apply to at least two inputs. 'Host stock' applies to one: tick a "
            'second input, or remove it and enter the uncertainty on the input itself.',
        ),
        (ErrorModel(shared=(SharedSource('Host stock', 4.0, ('h0', 'h0')),)), "'Host stock' applies to one"),
        (ErrorModel(shared=(SharedSource('Host stock', 4.0, ()),)), "'Host stock' applies to none"),
        (
            ErrorModel(shared=(SharedSource('Host stock', 4.0, ('h0', 'h0', 'd0')),)),
            "The shared error source 'Host stock' lists [Host]0 more than once, which would move it by the source "
            'twice. List each input once.',
        ),
        (ErrorModel(shared=(SharedSource('Guest stock', 4.0, ('h0', 'g0')),)), "'Guest stock' applies to an input"),
        (ErrorModel(additions=AdditionError(0.0, True)), 'error of each addition has to be above zero'),
    ],
)
def test_a_source_that_states_no_error_is_refused_by_name(errors, message):
    with pytest.raises(FitRefused) as refused:
        validate(errors, _IDA, _LABELS)
    assert message in str(refused.value)
    assert 'shared:' not in str(refused.value) and ADDITIONS not in str(refused.value)


def test_every_fault_of_a_source_is_reported_at_once():
    """One source can be wrong in several ways, and fixing them one per attempt is one refusal per round.

    The panel below the inputs states what a run would refuse over, so anything
    it leaves out is found only on the next attempt.
    """
    found = source_problems(ErrorModel(shared=(SharedSource('', 0.0, ('h0',)),)), _IDA, _LABELS)

    assert len(found) == 3
    assert 'has no name' in found[0]
    assert 'has to be above zero' in found[1]
    assert 'at least two inputs' in found[2]


def test_every_source_is_reported_whatever_is_wrong_with_the_one_before_it():
    """Sentences come source by source, in the order stated, so a panel can put each under its own row."""
    sources = (SharedSource('Pipette', 0.0, ('h0', 'd0')), SharedSource('Pipette', 4.0, ('g0', TITRANT)))

    found = source_problems(ErrorModel(shared=sources), _IDA, _LABELS)

    assert len(found) == 3
    assert "'Pipette' has to be above zero" in found[0]
    assert "Two shared error sources are named 'Pipette'" in found[1]
    # The repeated name does not hide the input this assay does not have.
    assert 'which this assay does not have as an input' in found[2]


def test_a_stated_model_passes():
    validate(ErrorModel(shared=(_STOCK, _BALANCE), additions=AdditionError(0.5, False)), _IDA, _LABELS)
    assert source_problems(ErrorModel(shared=(_STOCK, _BALANCE)), _IDA, _LABELS) == []


# -- the entries of a results file -------------------------------------------------


def test_a_model_without_shared_sources_writes_the_per_input_layout_alone():
    specs = {'h0': InputSpec.sigma_pct(3), TITRANT: InputSpec.interval_pct(-2, 2)}
    assert ErrorModel(specs=specs).to_dict() == {'input_uncertainty': specs_to_dict(specs)}
    assert ErrorModel().to_dict() == {'input_uncertainty': {}}


def test_a_fit_config_without_the_new_entries_reads_as_a_model_without_them():
    specs = {'h0': InputSpec.sigma_abs(3e-7), 'Ka_dye': InputSpec.interval_abs(8e5, 1.3e6)}
    fit_config = {
        'custom_bounds': None,
        'per_replicate': True,
        'level': 0.95,
        'input_uncertainty': specs_to_dict(specs),
    }
    assert ErrorModel.from_dict(fit_config) == ErrorModel(specs=specs)
    # A file written before inputs could move holds no entry at all.
    assert ErrorModel.from_dict({'custom_bounds': None}) == ErrorModel()


def test_the_whole_model_survives_a_json_round_trip():
    import json

    errors = ErrorModel(
        specs={'h0': InputSpec.sigma_pct(3)}, shared=(_STOCK, _BALANCE), additions=AdditionError(0.8, True)
    )
    written = errors.to_dict()
    assert written['shared_sources'][0] == {'name': _STOCK.name, 'sigma_pct': 4.0, 'inputs': ['h0', 'd0']}
    assert written['titrant_additions'] == {'sigma_pct': 0.8, 'sequential': True, 'separate_titrations': True}
    assert ErrorModel.from_dict(json.loads(json.dumps(written))) == errors


def test_replicates_read_from_one_titration_survive_a_round_trip_and_a_file_without_them_means_separate():
    import json

    reads = ErrorModel(additions=AdditionError(0.8, True, separate_titrations=False))
    assert ErrorModel.from_dict(json.loads(json.dumps(reads.to_dict()))) == reads
    # A results file that does not say how the replicates were made holds separate titrations.
    assert ErrorModel.from_dict({'titrant_additions': {'sigma_pct': 0.8, 'sequential': True}}) == ErrorModel(
        additions=AdditionError(0.8, True, separate_titrations=True)
    )


# -- the random error of each addition ---------------------------------------------

_V0 = 2.0e-3  # sample volume, L
_C_T = 1.0e-3  # titrant stock, M
_ALIQUOTS = np.array([0.0, 5, 5, 10, 10, 20, 40, 80, 150]) * 1e-6  # unequal additions, L; the first point has none


def _in_cuvette(volumes):
    """Titrant concentration of a sample of volume ``_V0`` holding *volumes* of stock."""
    return _C_T * volumes / (_V0 + volumes)


@pytest.mark.parametrize('stock', [None, 2.5e-3])
@pytest.mark.parametrize('sequential', [True, False])
def test_additions_without_error_leave_the_series_bit_for_bit(sequential, stock):
    x = np.cumsum(np.array([0.0, 1.1e-6, 2.3e-6, 0.7e-6, 9.9e-6, 1e-4]))
    moved = perturb_titrant(x, np.zeros(x.size), sequential, stock)
    assert moved.tobytes() == x.tobytes()


def test_sequential_additions_with_a_stock_are_the_volumes_pipetted():
    deltas = np.random.default_rng(3).normal(0.0, 0.05, _ALIQUOTS.size)
    x = _in_cuvette(np.cumsum(_ALIQUOTS))
    expected = _in_cuvette(np.cumsum(_ALIQUOTS * (1 + deltas)))
    assert perturb_titrant(x, deltas, True, _C_T) == pytest.approx(expected, rel=1e-12, abs=0)
    assert np.max(np.abs(expected / x[1:].max() - x / x[1:].max())) > 1e-3  # the errors do move the series


def test_separate_samples_with_a_stock_are_each_their_own_volume():
    deltas = np.random.default_rng(4).normal(0.0, 0.05, _ALIQUOTS.size)
    volumes = np.cumsum(_ALIQUOTS)
    expected = _in_cuvette(volumes * (1 + deltas))
    assert perturb_titrant(_in_cuvette(volumes), deltas, False, _C_T) == pytest.approx(expected, rel=1e-12, abs=0)


def test_separate_samples_without_a_stock_move_point_by_point():
    x = np.array([0.0, 1e-6, 5e-6, 2e-6, 4e-5])  # any order: every sample is its own
    deltas = np.array([0.3, -0.02, 0.05, 0.01, -0.04])
    assert perturb_titrant(x, deltas, False, None) == pytest.approx(x * (1 + deltas), rel=1e-15)


def test_equal_sequential_aliquots_accumulate_as_a_random_walk():
    """Point i is the sum of i independent additions: relative SD sigma / sqrt(i), correlation sqrt(i / k)."""
    sigma, k, n = 0.02, 12, 100_000
    x = 1e-6 * np.arange(1, k + 1)
    rng = np.random.default_rng(11)
    moved = np.array([perturb_titrant(x, rng.normal(0.0, sigma, k), True, None) for _ in range(n)])

    i = np.arange(1, k + 1)
    assert moved.std(axis=0) / x == pytest.approx(sigma / np.sqrt(i), rel=0.02)
    correlation = np.corrcoef(moved, rowvar=False)
    # A sample correlation has standard error (1 - rho²) / sqrt(n) <= 0.003 here.
    assert correlation[:, -1] == pytest.approx(np.sqrt(i / k), abs=0.01)
    assert correlation[2, 7] == pytest.approx(np.sqrt(3 / 8), abs=0.01)


def test_a_falling_series_cannot_be_sequential_and_the_refusal_names_the_point():
    x = np.array([0.0, 1e-6, 2e-6, 1.5e-6, 3e-6, 2e-6])
    with pytest.raises(FitRefused) as refused:
        perturb_titrant(x, np.zeros(x.size), True, None)
    message = str(refused.value)
    assert 'point 4' in message and '1.5×10⁻⁶ M' in message
    assert "Choose 'separately prepared samples' or check the order of the data" in message
    # A series that stays level (a repeated point) is no fall.
    perturb_titrant(np.array([0.0, 1e-6, 1e-6, 2e-6]), np.zeros(4), True, None)


@pytest.mark.parametrize('stock', [None, _C_T], ids=['no stock', 'stock'])
@pytest.mark.parametrize('sequential', [True, False], ids=['sequential', 'separate'])
def test_the_addition_loading_is_the_derivative_of_the_perturbed_series(sequential, stock):
    """Column j is how far every point moves per unit relative error of addition j: central differences of the series."""
    x = _in_cuvette(np.cumsum(_ALIQUOTS)) if stock else 1e-6 * np.cumsum(np.array([0.0, 1, 1, 2, 2, 4, 8, 16, 30]))
    loading = addition_loading(x, sequential, stock)

    h = 1e-6
    expected = np.column_stack(
        [
            (perturb_titrant(x, h * e, sequential, stock) - perturb_titrant(x, -h * e, sequential, stock)) / (2 * h)
            for e in np.eye(x.size)
        ]
    )
    assert loading == pytest.approx(expected, rel=1e-7, abs=1e-12 * x.max())
    # Sequential errors reach the later points only; a separate sample carries its own error alone.
    assert np.array_equal(loading != 0, expected != 0)
    assert not np.triu(loading, 1).any() and (sequential or not np.tril(loading, -1).any())


def test_a_falling_series_has_no_sequential_loading():
    with pytest.raises(FitRefused, match='point 3'):
        addition_loading(np.array([0.0, 2e-6, 1e-6]), True, None)
