"""The shipped texts describe the interval the app reports and where its inputs come from.

A fit reports two intervals — the one conditional on the entered inputs and the
one that lets them move inside their stated uncertainties — and a verdict on the
model and those inputs. None of that is imported by a paragraph, so the
documents can keep describing the older, single interval and stay green.

These tests read the live texts and cross-check them against the code: the
modules the pipeline actually has, the verdicts a fit can report, the checks the
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
}


def test_the_readme_explains_every_verdict_a_fit_can_report():
    """A verdict the app can print is one the reader can look up; one it cannot is a sentence with no explanation."""
    from core.pipeline.diagnostics import Verdict

    readme = (ROOT / 'Readme.md').read_text(encoding='utf-8')
    unexplained = [v.name for v in Verdict if v.name not in _VERDICT_IN_THE_README]
    assert not unexplained, f'Readme.md is not known to explain these verdicts: {unexplained}'
    missing = [name for name, clause in _VERDICT_IN_THE_README.items() if clause not in readme]
    assert not missing, f'Readme.md no longer explains these verdicts: {missing}'


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


def test_the_fit_help_points_at_the_panel_the_uncertainties_are_entered_in():
    """The Fit Configuration help sends the reader to a panel, under the name that panel carries."""
    pytest.importorskip('PyQt6')
    from gui.widgets import fit_config_panel, input_uncertainty_panel

    heading = input_uncertainty_panel._UNCERTAINTY_HELP_HTML.split('<h3>')[1].split('</h3>')[0]
    assert heading.strip() == 'Input Uncertainty'
    assert heading in fit_config_panel._SECTION_HELP_HTML
