"""Background check for newer SupraSimFit releases on GitHub.

Queries the GitHub REST API — ``/releases/latest``, the newest stable
release, from a stable build, and the newest published release of any kind
from a pre-release build (:func:`newest_release`), so a beta is offered only
to those already running one — parses the response, and emits a structured payload the GUI can consume. Designed
to mirror the :class:`gui.workers.FitWorker` pattern (QThread with
``finished``/``error`` signals).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from packaging.version import InvalidVersion, Version
from PyQt6.QtCore import QThread, pyqtSignal

from _version import __github_repo__, __version__


def is_newer(remote_tag: str, local: str) -> bool:
    """Return True if *remote_tag* represents a strictly newer version than *local*.

    Both arguments may carry a leading ``v``. Comparison uses
    :class:`packaging.version.Version`, which normalizes
    ``"1.2"`` and ``"1.2.0"`` to be equal.

    On unparseable input the function returns False (treat as "not newer")
    rather than raising, so a malformed remote tag never disrupts startup.
    """
    try:
        return Version(remote_tag.lstrip('v')) > Version(local.lstrip('v'))
    except InvalidVersion:
        return False


def newest_release(releases: list[dict]) -> dict | None:
    """The published release of highest version among *releases*, pre-releases included.

    Drafts and tags that are not versions are left out; ``None`` when nothing is left.
    """
    best, best_version = None, None
    for release in releases:
        if release.get('draft'):
            continue
        try:
            version = Version(str(release.get('tag_name', '')).lstrip('v'))
        except InvalidVersion:
            continue
        if best_version is None or version > best_version:
            best, best_version = release, version
    return best


class UpdateCheckWorker(QThread):
    """Query GitHub for the newest release this build should be offered.

    Signals
    -------
    finished(dict)
        Payload with keys:

        - ``latest_version`` (str): tag name as published, e.g. ``"v1.3.0"``.
        - ``release_url`` (str): HTML URL of the release page.
        - ``body`` (str): release notes (GitHub-flavored markdown).
        - ``assets`` (list[dict]): each item has ``name``,
          ``browser_download_url``, ``size``.
    error(str)
        Error message on any network/parse failure.
    """

    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    _URL = f'https://api.github.com/repos/{__github_repo__}/releases/latest'
    _ALL_URL = f'https://api.github.com/repos/{__github_repo__}/releases?per_page=30'
    _TIMEOUT_S = 5.0

    def run(self) -> None:
        try:
            beta = Version(__version__).is_prerelease
            req = urllib.request.Request(
                self._ALL_URL if beta else self._URL,
                headers={
                    'Accept': 'application/vnd.github+json',
                    'User-Agent': 'SupraSimFit-updater',
                },
            )
            with urllib.request.urlopen(req, timeout=self._TIMEOUT_S) as resp:
                data: Any = json.load(resp)
        except urllib.error.HTTPError as exc:
            self.error.emit(f'The update server returned an error (HTTP {exc.code}). Please try again later.')
            return
        except Exception:  # noqa: BLE001 — any network/parse error → one clear message
            self.error.emit('Could not reach the update server. Check your internet connection and try again.')
            return

        if beta:
            data = newest_release(data if isinstance(data, list) else [])
            if data is None:
                self.error.emit('The update server returned an unexpected response. Please try again later.')
                return
        try:
            info = {
                'latest_version': data['tag_name'],
                'release_url': data['html_url'],
                'body': data.get('body') or '',
                'assets': [
                    {
                        'name': a['name'],
                        'browser_download_url': a['browser_download_url'],
                        'size': a.get('size', 0),
                    }
                    for a in data.get('assets', [])
                ],
            }
        except KeyError:
            self.error.emit('The update server returned an unexpected response. Please try again later.')
            return

        self.finished.emit(info)
