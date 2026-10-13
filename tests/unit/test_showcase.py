"""The showcase package: the cases load, its datasets are reproducible and the page is self-contained.

No fit runs here. What is checked is what a reader of the page depends on: that
every case is defined, that a synthetic titration is the same titration every
time it is built, that the page carries every case, and that it reaches for
nothing outside itself.
"""

from __future__ import annotations

import json
import re

import numpy as np
import pytest

from core.assays.registry import ASSAY_REGISTRY, AssayType
from showcase import build_page, run
from showcase.cases import CASES, Synthetic


def test_every_case_is_defined_and_distinct():
    """Each case has a key, a unique slug, a title and a paragraph of intent."""
    assert list(CASES) == list('ABCDEFGHIJ')
    slugs = [case.slug for case in CASES.values()]
    assert len(set(slugs)) == len(slugs)
    for key, case in CASES.items():
        assert case.key == key
        assert case.slug.startswith(f'{key}-')
        assert case.title.strip()
        assert len(case.intent.split()) >= 30, f'case {key} has no paragraph of intent'


def _synthetics():
    """Every synthetic titration the cases name, keyed by where it comes from."""
    out = {}
    for key, case in CASES.items():
        if isinstance(case.dataset, Synthetic):
            out[key] = case.dataset
        elif isinstance(case.dataset, dict):
            out.update({f'{key}-{name}': spec for name, spec in case.dataset.items()})
    return out


def test_a_synthetic_dataset_is_reproducible_and_seed_dependent():
    """The same spec builds the same titration; a different seed builds a different one."""
    spec = _synthetics()['E']
    first, second = spec.build(), spec.build()
    assert np.array_equal(first.signals, second.signals)
    assert np.array_equal(first.concentrations, second.concentrations)

    import dataclasses

    other = dataclasses.replace(spec, seed=spec.seed + 1).build()
    assert not np.array_equal(first.signals, other.signals)
    # The grid is the design, not the draw: only the signals move with the seed.
    assert np.array_equal(first.concentrations, other.concentrations)


@pytest.mark.parametrize('name', sorted(_synthetics()))
def test_a_synthetic_truth_names_every_parameter_of_its_model(name):
    """A generator that left a parameter out would silently fit a different model."""
    spec = _synthetics()[name]
    keys = ASSAY_REGISTRY[AssayType[spec.assay]].parameter_keys
    assert set(spec.truth) == set(keys)
    signals = spec.build().signals
    assert signals.shape == (spec.replicates, spec.n_points)
    assert np.isfinite(signals).all()
    assert np.ptp(spec.clean()) > 0, 'a titration whose signal does not move carries no information'


def _results(path):
    """A minimal computed-results folder: one file per case, with one of everything the page renders."""
    path.mkdir(parents=True, exist_ok=True)
    for key, case in CASES.items():
        (path / f'{case.slug}.json').write_text(
            json.dumps(
                {
                    'key': key,
                    'slug': case.slug,
                    'title': case.title,
                    'intent': case.intent,
                    'seconds': 1.0,
                    'dataset': {'kind': 'synthetic', 'text': 'a titration'},
                    'tables': [{'title': 'a table', 'columns': ['a', 'verdict'], 'rows': [[1, 'pass']]}],
                    'figures': [
                        {
                            'id': f'{key}1',
                            'title': 'a figure',
                            'caption': 'a caption',
                            'panels': [
                                {
                                    'title': 'a panel',
                                    'x': {'label': 'x'},
                                    'y': {'label': 'y'},
                                    'series': [
                                        {'kind': 'line', 'name': 'a line', 'color': 'c1', 'x': [0, 1], 'y': [0, 1]}
                                    ],
                                }
                            ],
                        }
                    ],
                    'reading': ['what it says'],
                    'limits': ['what it does not say'],
                    'before_after': [
                        {
                            'case': key,
                            'dataset': 'a titration',
                            'key': 'Ka_guest',
                            'truth': 6.0,
                            'previous_low': 5.0,
                            'previous_high': 7.0,
                            'previous_width_median': 2.0,
                            'previous_on_bound': 'upper (Ka bound 12.0)',
                            'current_low': 5.9,
                            'current_high': 6.1,
                            'current_width': 0.2,
                            'current_holds': True,
                        }
                    ],
                }
            )
        )
    (path / 'index.json').write_text(
        json.dumps(
            {
                'order': list(CASES),
                'generated': '2026-01-01T00:00:00+00:00',
                'git_commit': 'abc1234',
                'code_hash': '0123456789ab',
                'validation_source': {
                    'origin': 'a validation store',
                    'root': '/somewhere',
                    'command': 'python -m validation tables --format csv',
                    'rendered': '2026-01-01T00:00:00+00:00',
                    'code_hash': '0123456789ab',
                    'rows': 3,
                },
                'regenerate': 'python -m showcase run && python -m showcase page',
            }
        )
    )
    return path


def test_the_page_carries_every_case(tmp_path):
    """Rendering a known results folder puts every case's key, title and figure on the page."""
    page = build_page.build(_results(tmp_path / 'results'), tmp_path / 'index.html')
    document = page.read_text()
    for key, case in CASES.items():
        assert case.title in document, f'case {key} is missing from the page'
        assert f'id="case-{case.slug}"' in document
        assert f'{key}1. a figure' in document
    assert 'What an experimenter learns here' in document
    assert 'abc1234' in document and '0123456789ab' in document


def test_the_page_says_which_validation_run_its_rates_are(tmp_path):
    """The footer names the store case J was rendered from, so a reader can go and look at it."""
    document = build_page.build(_results(tmp_path / 'results'), tmp_path / 'index.html').read_text()
    assert '/somewhere' in document
    assert 'python -m validation tables --format csv' in document


def test_case_j_refuses_an_empty_validation_store():
    """No rows and no failures are different statements; the second would read as a clean bill of health."""
    with pytest.raises(SystemExit) as refused:
        run.case_j([], {'root': '/nowhere', 'command': 'python -m validation tables --format csv'})
    assert '/nowhere' in str(refused.value)


def test_the_rates_are_reproducible_from_this_repository():
    """The validation tables case J renders are kept here, with the run they came from named."""
    assert run.VALIDATION_TABLES.exists(), 'showcase/results/validation-tables.csv is what makes case J rebuildable'
    source = json.loads(run.VALIDATION_SOURCE.read_text())
    assert source['root'] and source['rendered'] and source['code_hash']
    assert source['command'] == run.VALIDATION_COMMAND
    rows = run._parse_tables(run.VALIDATION_TABLES.read_text())
    assert len(rows) == source['rows']
    assert {row['code'] for row in rows} == {source['code_hash']}


def test_validation_rows_refuses_when_there_is_nothing_to_render(tmp_path, monkeypatch):
    """A root with no store and no kept tables stops the run rather than rendering an empty section."""
    monkeypatch.setattr(run, 'VALIDATION_TABLES', tmp_path / 'validation-tables.csv')
    monkeypatch.setattr(run, 'VALIDATION_SOURCE', tmp_path / 'validation-tables.json')
    with pytest.raises(SystemExit) as refused:
        run.validation_rows(tmp_path)
    assert 'validation run' in str(refused.value)


def test_the_page_loads_nothing_from_the_network(tmp_path):
    """Everything the page needs is inside it: no stylesheet, script or image comes from elsewhere."""
    document = build_page.build(_results(tmp_path / 'results'), tmp_path / 'index.html').read_text()
    assert not re.search(r'<script[^>]+\bsrc\s*=', document)
    assert not re.search(r'<link[^>]+\bhref\s*=', document)
    assert not re.search(r'<img|<iframe|@import|url\(\s*["\']?https?:', document)
    # The only URL-shaped text left is the SVG namespace the script creates elements in.
    urls = {url for url in re.findall(r'https?://[^\s"\'<>]+', document)}
    assert urls <= {'http://www.w3.org/2000/svg'}, urls
