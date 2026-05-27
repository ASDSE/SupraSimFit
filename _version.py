"""Single source of truth for SupraSimFit's version and GitHub repo.

Everything that needs to know the app's version reads from this file:
- gui.main_window (window title, update-check comparison)
- SupraSimFit.spec (CFBundleShortVersionString)
- .github/workflows/auto_tag.yml (tag creation on bump)

To cut a release: bump ``__version__`` here, merge to ``main``.
The ``auto_tag`` workflow pushes the matching ``vX.Y.Z`` tag, which
triggers the existing build/release workflow.
"""

__version__ = "1.2.0"
__github_repo__ = "ASDSE/SupraSimFit"
