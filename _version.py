"""Single source of truth for SupraSimFit's version and GitHub repo.

Everything that needs to know the app's version reads from this file:
- gui.main_window (window title, update-check comparison)
- SupraSimFit.spec (CFBundleShortVersionString)
- .github/workflows/build_and_release.yml (drift guard: the build fails
  if the pushed tag does not match ``__version__``)

To cut a release: bump ``__version__`` here and merge to ``main``, then
tag manually::

    git tag vX.Y.Z && git push origin vX.Y.Z

The pushed ``v*`` tag triggers build_and_release.yml, whose first step
verifies the tag matches this value before building.
"""

__version__ = '1.5.0'
__github_repo__ = 'ASDSE/SupraSimFit'
