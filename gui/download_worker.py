"""Background download worker — streams a URL to a local file with progress.

Used by :class:`gui.update_dialog.UpdateAvailableDialog` to fetch the
OS-matched release asset into ``~/Downloads`` without blocking the GUI.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal


class DownloadWorker(QThread):
    """Stream a URL to a local path, emitting progress in 64 KB chunks.

    Signals
    -------
    progress(int, int)
        Bytes downloaded so far, total bytes (0 if unknown).
    finished(str)
        Absolute path of the saved file, on success.
    error(str)
        Error message on failure.
    """

    progress = pyqtSignal(int, int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    _CHUNK = 64 * 1024
    _TIMEOUT_S = 30.0

    def __init__(self, url: str, dest: Path, parent=None) -> None:
        super().__init__(parent)
        self._url = url
        self._dest = Path(dest)

    def run(self) -> None:
        try:
            self._dest.parent.mkdir(parents=True, exist_ok=True)
            req = urllib.request.Request(
                self._url,
                headers={"User-Agent": "SupraSimFit-updater"},
            )
            with urllib.request.urlopen(req, timeout=self._TIMEOUT_S) as resp:
                total = int(resp.headers.get("Content-Length", 0) or 0)
                done = 0
                with open(self._dest, "wb") as f:
                    while True:
                        chunk = resp.read(self._CHUNK)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
                        self.progress.emit(done, total)
            self.finished.emit(str(self._dest))
        except urllib.error.HTTPError as exc:
            self.error.emit(f"HTTP {exc.code}: {exc.reason}")
        except Exception as exc:  # noqa: BLE001 — surface any network/disk error
            self.error.emit(f"{type(exc).__name__}: {exc}")
