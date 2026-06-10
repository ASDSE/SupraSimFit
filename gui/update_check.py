"""Background check for newer SupraSimFit releases on GitHub.

Queries the GitHub REST API's ``/releases/latest`` endpoint, parses the
response, and emits a structured payload the GUI can consume. Designed
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

from _version import __github_repo__


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


class UpdateCheckWorker(QThread):
    """Query GitHub ``/releases/latest`` for the configured repo.

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
    _TIMEOUT_S = 5.0

    def run(self) -> None:
        try:
            req = urllib.request.Request(
                self._URL,
                headers={
                    'Accept': 'application/vnd.github+json',
                    'User-Agent': 'SupraSimFit-updater',
                },
            )
            with urllib.request.urlopen(req, timeout=self._TIMEOUT_S) as resp:
                data: dict[str, Any] = json.load(resp)
        except urllib.error.HTTPError as exc:
            self.error.emit(f'GitHub API returned HTTP {exc.code}: {exc.reason}')
            return
        except Exception as exc:  # noqa: BLE001 — surface any network/parse error
            self.error.emit(f'{type(exc).__name__}: {exc}')
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
        except KeyError as exc:
            self.error.emit(f'Unexpected GitHub response (missing key {exc})')
            return

        self.finished.emit(info)
