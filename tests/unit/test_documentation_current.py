"""The shipped documents and help texts describe the fit the app performs.

Prose rots silently: nothing imports a paragraph, so a document can keep
describing machinery the code does not have and no test notices. These two
tests read the live documents and the GUI help strings as text and pin the
one property that matters — they name the present fit engine and nothing
that was taken out of it.

The scan is every live ``.py`` and ``.md`` the repository ships — the documents
a user reads, the instruction files, the live reference under ``docs/``, the
application's own modules and the standalone scripts beside them. They are found
by walking the tree rather than listed, so a file added or a module left behind
by a removal is scanned without anyone remembering to name it here. Outside it:
the tests themselves, which name retired machinery to assert it is gone, and the
files that record the past on purpose — the dated audits under ``docs/``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: Directories holding nothing the repository ships as its own live text.
_SKIP_DIRS = frozenset({'.git', '.github', '.claude', '.venv', '.ruff_cache', 'build', 'dist', 'graphify-out'})

#: Texts whose subject is the past: a dated audit records what was found and
#: what was done about it, and the suite names removed machinery to pin that it
#: is gone.
_RECORDS_THE_PAST = frozenset({'docs/pint-audit.md'})

#: The one thing a live text may still name, because it is a property of a file
#: the app reads rather than of the app: a results file written by an earlier
#: version holds an estimate that a multi-start search produced. That note is
#: the reader's only explanation for an imported result with no interval, so it
#: is taken out of the text before the scan instead of being forbidden.
_IMPORTED_FILE_PROVENANCE = 'multi-start estimate'


def _live_texts() -> list[str]:
    """Every ``.py`` and ``.md`` the repository ships, as paths relative to the root."""
    found = []
    for path in sorted(ROOT.rglob('*')):
        if path.suffix not in ('.py', '.md') or not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if _SKIP_DIRS & set(relative.parts) or relative.parts[0] == 'tests':
            continue
        if any(part.startswith('__pycache__') for part in relative.parts):
            continue
        if relative.as_posix() not in _RECORDS_THE_PAST:
            found.append(relative.as_posix())
    return found


LIVE_TEXTS = _live_texts()

#: Machinery the app does not have. A live text naming one of these describes
#: something the reader cannot find in the program: a search over random
#: starting points, the pool of attempts it left behind, the controls that
#: filtered that pool, and the tab that drew it.
RETIRED = (
    'multi-start',
    'multistart',
    'multi_start',
    'L-BFGS-B',
    'n_trials',
    'min_r_squared',
    'rmse_threshold_factor',
    'parameter_samples',
    'accepted pool',
    'accepted fits',
    'representative fit',
    'Representative selector',
    'select_representative',
    'Distributions tab',
    'DistributionWidget',
    'SaveDistributionsDialog',
)


@pytest.mark.parametrize('relative', LIVE_TEXTS)
def test_no_live_text_names_machinery_the_app_does_not_have(relative):
    lowered = (ROOT / relative).read_text(encoding='utf-8').lower().replace(_IMPORTED_FILE_PROVENANCE, '')
    named = [term for term in RETIRED if term.lower() in lowered]
    assert not named, f'{relative} describes machinery the app does not have: {named}'


def test_the_scan_reaches_the_texts_a_reader_and_the_program_depend_on():
    """An exclusion that quietly emptied the walk would leave every text above unscanned and green."""
    expected = {
        'Readme.md',
        'CLAUDE.md',
        'docs/scientific-summary.md',
        'data/Readme.md',
        'gui/assay_descriptions.py',
        'core/pipeline/varpro.py',
        'core/pipeline/fit_pipeline.py',
        'scripts/README.md',
    }
    assert expected <= set(LIVE_TEXTS), f'not scanned: {sorted(expected - set(LIVE_TEXTS))}'


def test_the_documents_name_the_fit_the_app_performs():
    """Both user-facing documents state the method and what is reported."""
    for relative, required in (
        ('Readme.md', ('variable projection', 'profile', 'confidence interval')),
        ('docs/scientific-summary.md', ('variable projection', 'profile', 'joint')),
    ):
        lowered = (ROOT / relative).read_text(encoding='utf-8').lower()
        missing = [term for term in required if term not in lowered]
        assert not missing, f'{relative} does not say how a fit is made: {missing}'
