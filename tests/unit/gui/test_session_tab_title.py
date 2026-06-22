"""Session tab-title logic: dataset filename, custom name, and fallbacks.

The session owns its title (emitted via ``title_changed``): a user-set custom
name wins, else the loaded dataset's filename stem, else "Untitled". A custom
name persists across data loads until cleared (renamed to empty).
"""

import pytest

pytest.importorskip('PyQt6')


def test_tab_title_resolution_and_emission(qapp):
    from gui.fitting_session import FittingSession

    s = FittingSession()
    emitted = []
    s.title_changed.connect(emitted.append)

    # No file loaded yet → "Untitled".
    assert s._tab_title() == 'Untitled'

    # A loaded dataset → filename stem (no extension), emitted.
    s._state.source_file = '/data/tryptamine_424.txt'
    s._emit_tab_title()
    assert s._tab_title() == 'tryptamine_424'
    assert emitted[-1] == 'tryptamine_424'

    # A custom name wins and persists across a later data load.
    s.set_custom_tab_name('Control run')
    assert emitted[-1] == 'Control run'
    s._state.source_file = '/data/other.csv'
    assert s._tab_title() == 'Control run'

    # Renaming to empty reverts to the current filename.
    s.set_custom_tab_name('   ')
    assert s._tab_title() == 'other'
    assert emitted[-1] == 'other'

    # Clearing the data → "Untitled".
    s._state.source_file = None
    assert s._tab_title() == 'Untitled'
