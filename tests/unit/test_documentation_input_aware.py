"""The shipped texts describe the interval the app reports and where its inputs come from.

A fit reports two intervals — the one conditional on the entered inputs and the
one that lets them move inside their stated uncertainties — and a verdict on the
model and those inputs. None of that is imported by a paragraph, so the
documents can keep describing the older, single interval and stay green.

These tests read the live texts and cross-check them against the code: the
modules the pipeline actually has, the verdicts a fit can report, the noise law
the fit is weighted by and what it says when it cannot be read, the checks the
validation package runs and the claim each one makes, and the name the panel the
uncertainties are entered in gives itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_the_instructions_list_every_module_of_the_fitting_pipeline():
    """A module added to the pipeline without a row in the table leaves the map wrong."""
    modules = sorted(p.name for p in (ROOT / 'core' / 'pipeline').glob('*.py') if p.name != '__init__.py')
    assert len(modules) >= 7  # the walk reached the package
    instructions = (ROOT / 'CLAUDE.md').read_text(encoding='utf-8')
    missing = [name for name in modules if name not in instructions]
    assert not missing, f'CLAUDE.md does not say what these modules do: {missing}'


#: The clause Readme.md carries for each verdict a fit can report. Keyed by the
#: enum, so a verdict added to the code without a paragraph fails here rather
#: than shipping a sentence no document explains.
_VERDICT_IN_THE_README = {
    'CONSISTENT': "whether the curve misses the data by more than the data's own scatter allows",
    'INPUTS_EXPLAIN': 'whether a shift of the inputs inside the uncertainties you stated turns a miss into a fit',
    'INPUTS_CONFLICT': 'whether the data fit only with the inputs, taken together, further from the entered values',
    'MODEL_INADEQUATE': 'the model does not describe the data even with the inputs free',
    'MODEL_AND_INPUTS': 'or both of the last two, with the inputs named first',
}


def test_the_readme_explains_every_verdict_a_fit_can_report():
    """A verdict the app can print is one the reader can look up; one it cannot is a sentence with no explanation."""
    from core.pipeline.diagnostics import Verdict

    readme = (ROOT / 'Readme.md').read_text(encoding='utf-8')
    unexplained = [v.name for v in Verdict if v.name not in _VERDICT_IN_THE_README]
    assert not unexplained, f'Readme.md is not known to explain these verdicts: {unexplained}'
    missing = [name for name, clause in _VERDICT_IN_THE_README.items() if clause not in readme]
    assert not missing, f'Readme.md no longer explains these verdicts: {missing}'


#: The clause Readme.md carries for each basis a noise law can report. Keyed by
#: the enum, so a basis added to the code without a paragraph fails here rather
#: than reaching the fit summary as a sentence no document explains.
_NOISE_BASIS_IN_THE_README = {
    'REPLICATES': 'the scatter of each replicate about its own line in the mean curve',
    'SINGLE_TITRATION': 'one titration cannot show how the noise varies with the signal',
    'TOO_FEW_POINTS': 'the replicates scatter at too few titration points to show how it varies',
}


def test_the_readme_explains_every_basis_a_noise_law_can_report():
    """The weights a fit is run with rest on one of these, and each one is a paragraph a reader can find."""
    from core.pipeline.noise import NoiseBasis

    readme = ' '.join((ROOT / 'Readme.md').read_text(encoding='utf-8').split())
    unexplained = [b.name for b in NoiseBasis if b.name not in _NOISE_BASIS_IN_THE_README]
    assert not unexplained, f'Readme.md is not known to explain these bases: {unexplained}'
    missing = [name for name, clause in _NOISE_BASIS_IN_THE_README.items() if clause not in readme]
    assert not missing, f'Readme.md no longer explains these bases: {missing}'


def test_the_readme_carries_the_words_a_fit_prints_where_no_law_can_be_read():
    """The sentence the summary shows instead of a law is the one the document explains, word for word."""
    from core.pipeline.noise import NoiseBasis, NoiseLaw

    for basis in NoiseBasis:
        law = NoiseLaw(basis)
        if law.estimated:
            continue
        clause = _NOISE_BASIS_IN_THE_README[basis.name]
        assert clause in law.describe(), (
            f'{basis.name}: the app prints "{law.describe()}", which the document does not explain'
        )


def test_the_validation_readme_names_every_check_the_package_runs():
    """The table is the map of what was measured; a check missing from it is a claim nobody can find."""
    from validation.checks import CHECKS

    readme = (ROOT / 'validation' / 'README.md').read_text(encoding='utf-8')
    missing = [name for name in sorted(CHECKS) if name not in readme]
    assert not missing, f'validation/README.md does not describe these checks: {missing}'


def test_the_validation_readme_quotes_each_check_s_own_claim():
    """The claim is written once, in the check; a README paraphrase would drift from what was measured."""
    from validation.checks import CHECKS

    readme = ' '.join((ROOT / 'validation' / 'README.md').read_text(encoding='utf-8').split())
    missing = [name for name, check in sorted(CHECKS.items()) if ' '.join(check.claim.split()) not in readme]
    assert not missing, f'validation/README.md states another claim than these checks make: {missing}'


def test_the_binding_model_help_points_at_the_view_the_uncertainties_are_entered_in():
    """The Binding model help of a model with inputs sends the reader to a view, under the name the sidebar gives it."""
    pytest.importorskip('PyQt6')
    from core.assays.registry import AssayType
    from gui import binding, uncertainty
    from gui.fitting_session import VIEWS

    heading = uncertainty.HELP_HTML.split('<h3>')[1].split('</h3>')[0].strip()
    assert heading in VIEWS
    # Dye alone has no entered input to state an uncertainty for, so its help has no view to point at.
    for assay_type in (at for at in AssayType if at is not AssayType.DYE_ALONE):
        assert f'<b>{heading}</b>' in binding.help_html(assay_type)
