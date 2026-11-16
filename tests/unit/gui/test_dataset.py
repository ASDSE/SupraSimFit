"""The data of one session, with no widget: files stacked as replicates, concentrations as stated.

What goes in comes out: a unit reinterprets the stated numbers, an edit or a loaded
vector reaches the molar grid, a channel switch keeps concentrations already entered,
and added files keep the replicates switched off. Data that cannot be used are refused
whole, in a sentence that names the file and leaves the dataset as it was.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core.data_processing.measurement_set import InvalidData, MeasurementSet
from gui.dataset import Dataset

DATA = Path(__file__).parent.parent.parent / 'data'
ENSIGHT_FIXTURE = DATA / 'ensight' / 'tryptamine.csv'
JASCO_FIXTURE = DATA / 'jasco' / 'cb7in30umbc_1-1.csv'

_GRID = 'concentration,signal\n0,10\n1e-6,12\n2e-6,14\n3e-6,15\n4e-6,16\n'


def _csv(tmp_path: Path, name: str, text: str = _GRID) -> str:
    path = tmp_path / name
    path.write_text(text)
    return str(path)


@pytest.fixture
def three_points(tmp_path) -> Dataset:
    """Two replicates on three points, stated in M."""
    df = pd.DataFrame(
        [
            {'concentration': c, 'signal': (i + 1) * 100.0, 'replica': r}
            for r in range(2)
            for i, c in enumerate((1e-6, 2e-6, 3e-6))
        ]
    )
    return Dataset.from_set(MeasurementSet.from_dataframe(df, source_file='fake.txt'), 'fake.txt')


def test_a_unit_reinterprets_the_stated_numbers(three_points):
    three_points.set_imported_unit('µM')

    np.testing.assert_allclose(three_points.ms.concentrations, [1e-12, 2e-12, 3e-12])
    np.testing.assert_allclose(three_points.face_values, [1e-6, 2e-6, 3e-6])


def test_an_edit_reaches_the_molar_grid_in_the_stated_unit(three_points):
    three_points.set_imported_unit('µM')

    three_points.set_concentration(0, '5')

    np.testing.assert_allclose(three_points.ms.concentrations, [5e-6, 2e-12, 3e-12])


@pytest.mark.parametrize('typed', ['nan', '-1e-6', 'inf', 'abc'])
def test_an_edit_that_is_not_a_concentration_is_refused_and_changes_nothing(three_points, typed):
    with pytest.raises(InvalidData) as refused:
        three_points.set_concentration(1, typed)

    np.testing.assert_allclose(three_points.ms.concentrations, [1e-6, 2e-6, 3e-6])
    np.testing.assert_allclose(three_points.face_values, [1e-6, 2e-6, 3e-6])
    text = str(refused.value)
    assert (
        'is not a number' in text
        if typed in ('abc', 'nan', 'inf')
        else ('point 2 of 3' in text and 'zero or more' in text)
    )


def test_a_vector_keeps_its_own_unit_and_one_outside_the_list_is_converted_to_molar(three_points, tmp_path):
    um = tmp_path / 'um.json'
    um.write_text(json.dumps({'concentrations': [1.0, 2.0, 3.0], 'unit': 'µM'}))
    assert three_points.load_concentrations(str(um)) is None
    assert three_points.imported_unit == 'µM'
    np.testing.assert_allclose(three_points.ms.concentrations, [1e-6, 2e-6, 3e-6])

    pm = tmp_path / 'pm.json'
    pm.write_text(json.dumps({'concentrations': [1000, 2000, 5000], 'unit': 'pM'}))
    notice = three_points.load_concentrations(str(pm))
    # 1000 pM is 1e-9 M: converted, never read as 1000 of the unit shown before.
    assert three_points.imported_unit == 'M' and 'pM' in notice
    np.testing.assert_allclose(three_points.ms.concentrations, [1e-9, 2e-9, 5e-9])


def test_a_vector_with_a_negative_value_is_refused_whole(three_points, tmp_path):
    bad = tmp_path / 'bad.json'
    bad.write_text(json.dumps({'concentrations': [1.0, -2.0, 3.0], 'unit': 'µM'}))

    with pytest.raises(InvalidData) as refused:
        three_points.load_concentrations(str(bad))

    np.testing.assert_allclose(three_points.ms.concentrations, [1e-6, 2e-6, 3e-6])
    assert three_points.imported_unit == 'M'
    assert 'point 2 of 3 in bad.json' in str(refused.value) and '-2 µM' in str(refused.value)


def test_files_opened_together_become_replicates_one_per_file(tmp_path):
    paths = [_csv(tmp_path, f'{stem}.csv') for stem in ('rep_a', 'rep_b', 'rep_c')]

    ds = Dataset.open(paths)

    assert ds.ms.n_replicas == 3
    assert [f.replica_ids for f in ds.files] == [('rep_a',), ('rep_b',), ('rep_c',)]


def test_added_files_join_the_grid_and_keep_the_replicates_switched_off(tmp_path):
    ds = Dataset.open([_csv(tmp_path, 'a.csv'), _csv(tmp_path, 'b.csv')])
    ds.ms.set_active('b', False)

    more = ds.added([_csv(tmp_path, 'c.csv')])

    assert list(more.ms.replica_ids) == ['a', 'b', 'c']
    assert not more.ms.is_active('b') and more.ms.is_active('c')
    assert [f.name for f in more.files] == ['a.csv', 'b.csv', 'c.csv']


def test_a_file_on_another_grid_is_refused_and_the_session_keeps_its_files(tmp_path):
    ds = Dataset.open([_csv(tmp_path, 'a.csv')])
    short = _csv(tmp_path, 'short.csv', 'concentration,signal\n0,10\n1e-6,12\n2e-6,14\n3e-6,15\n')

    with pytest.raises(InvalidData) as refused:
        ds.added([short])

    assert 'different numbers of titration points' in str(refused.value)
    assert [f.name for f in ds.files] == ['a.csv'] and ds.ms.n_replicas == 1


def test_removing_a_file_takes_its_replicate_and_keeps_the_others_as_they_were(tmp_path):
    a, b, c = (_csv(tmp_path, f'{stem}.csv') for stem in 'abc')
    ds = Dataset.open([a, b, c])
    ds.ms.set_active('a', False)

    left = ds.without(c).without(b)

    assert left.ms.n_replicas == 1 and [f.name for f in left.files] == ['a.csv']
    assert left.ms.n_active == 0  # a stays switched off
    assert left.without(a) is None


def test_an_unreadable_file_is_named_in_a_sentence_without_the_reader_error(tmp_path):
    from core.io import load_measurements

    bad = _csv(tmp_path, 'garbled.csv', 'this is not;a titration\n\x00\x01 at all\n')
    with pytest.raises(Exception) as raw:
        load_measurements(bad)
    good = _csv(tmp_path, 'good.csv')

    for paths in ([bad], [good, bad]):
        with pytest.raises(InvalidData) as refused:
            Dataset.open(paths)
        text = str(refused.value)
        assert 'garbled.csv' in text and str(raw.value) not in text and 'Traceback' not in text
    assert 'good.csv' not in str(refused.value) or 'garbled.csv' in str(refused.value)


def test_a_refusal_written_for_the_user_is_kept_as_it_is(tmp_path):
    from core.io import load_measurements

    path = _csv(tmp_path, 'negative.csv', 'concentration,signal\n0,10\n1e-6,12\n-2e-6,14\n3e-6,15\n4e-6,16\n')
    with pytest.raises(InvalidData) as expected:
        MeasurementSet.from_dataframe(load_measurements(path), source_file=path)

    with pytest.raises(InvalidData) as refused:
        Dataset.open([path])

    assert str(refused.value) == str(expected.value)
    assert 'negative.csv' in str(refused.value) and '-2 µM' in str(refused.value)


def _multi_channel(placeholder: bool = True) -> Dataset:
    rows = [
        {'concentration': float(i + 1), 'signal': base + r * 10 + i, 'replica': r, 'channel': ch}
        for ch, base in (('chA', 0.0), ('chB', 1000.0))
        for r in range(2)
        for i in range(3)
    ]
    df = pd.DataFrame(rows)
    df.attrs['bmg_placeholder_concentrations'] = placeholder
    df.attrs['ensight_metadata'] = {'channels': {'chA': {}, 'chB': {}}}
    from gui import dataset

    ds = Dataset()
    ds._channel_frame = df
    ds.channels, ds.channel = ['chA', 'chB'], 'chA'
    ds.ms = dataset._make_ms(dataset._slice_channel(df, 'chA'), 'plate.csv')
    ds.face_values = np.asarray(ds.ms.concentrations, dtype=float).copy()
    ds.files = (dataset.SourceFile('plate.csv', 'EnSight plate export', tuple(ds.ms.replica_ids)),)
    return ds


def test_a_channel_switch_keeps_the_concentrations_entered_and_takes_the_new_signals():
    ds = _multi_channel()
    for i, value in enumerate(('1e-6', '2e-6', '3e-6')):
        ds.set_concentration(i, value)

    ds.select_channel('chB')

    np.testing.assert_allclose(ds.ms.concentrations, [1e-6, 2e-6, 3e-6])
    np.testing.assert_allclose(ds.ms.signals, [[1000, 1001, 1002], [1010, 1011, 1012]])


def test_a_channel_switch_before_any_entry_keeps_placeholders():
    ds = _multi_channel()

    ds.select_channel('chB')

    assert ds.ms.metadata.get('bmg_placeholder_concentrations')
    np.testing.assert_allclose(ds.ms.concentrations, [1.0, 2.0, 3.0])


def test_a_multi_channel_file_takes_no_further_files(tmp_path):
    with pytest.raises(InvalidData) as refused:
        _multi_channel().added([_csv(tmp_path, 'a.csv')])

    assert 'one channel at a time' in str(refused.value)


@pytest.mark.skipif(not ENSIGHT_FIXTURE.exists(), reason='EnSight fixture missing')
def test_a_real_ensight_export_opens_on_its_first_of_three_channels():
    ds = Dataset.open([str(ENSIGHT_FIXTURE)])

    assert len(ds.channels) == 3 and ds.channel == ds.channels[0]
    assert (ds.ms.n_replicas, ds.ms.n_points) == (8, 12)
    first = ds.ms.signals.copy()
    ds.select_channel(ds.channels[2])
    assert not np.array_equal(first, ds.ms.signals)


@pytest.mark.skipif(not JASCO_FIXTURE.exists(), reason='JASCO fixture missing')
def test_jasco_metadata_reaches_the_measurement_set():
    ds = Dataset.open([str(JASCO_FIXTURE)])

    sections = ds.ms.metadata['jasco_metadata']['sections']
    assert sections['Measurement Information']['Ex wavelength'] == '415.0 nm'
    assert ds.files[0].format == 'JASCO export'


def test_outlier_removal_names_the_point_that_put_a_replicate_out():
    x = np.linspace(0, 1e-5, 6)
    signals = np.vstack([np.linspace(10, 20, 6) + k * 0.01 for k in range(5)])
    signals[3, 2] += 50.0  # replicate 3 is far out at the third point
    ms = MeasurementSet(concentrations=x, signals=signals, replica_ids=tuple('abcde'))
    ds = Dataset.from_set(ms, None)

    ds.remove_outliers(3.5, 3)

    assert ds.outlier_result['dropped'] == ['d']
    assert ds.outlier_result['evidence']['d']['point'] == 2
    assert ds.outlier_result['evidence']['d']['z'] > 3.5
    assert not ds.ms.is_active('d')


def test_outlier_removal_refuses_with_fewer_replicates_than_it_needs(three_points):
    with pytest.raises(InvalidData) as refused:
        three_points.remove_outliers(3.5, 3)

    assert 'at least 3' in str(refused.value) and three_points.ms.n_active == 2
