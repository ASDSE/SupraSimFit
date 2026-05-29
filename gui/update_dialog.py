"""Dialog shown when a newer SupraSimFit release is available.

Displays release notes (markdown) plus two paths:
  1. Primary button — download the OS-matched zip into ``~/Downloads``.
  2. Secondary button — open the release page on GitHub.

After a successful download the primary button becomes "Show in file manager".
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from _version import __version__
from gui.download_worker import DownloadWorker


# sys.platform → (asset-name substring, human label)
_OS_ASSET_MAP: dict[str, tuple[str, str]] = {
    "darwin": ("macos", "macOS"),
    "win32": ("windows", "Windows"),
    "linux": ("linux", "Linux"),
}


def _pick_asset(assets: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the asset whose name matches the current OS, or None."""
    entry = _OS_ASSET_MAP.get(sys.platform)
    if not entry:
        return None
    substring = entry[0]
    for a in assets:
        if substring in a["name"].lower():
            return a
    return None


def _os_label() -> str:
    return _OS_ASSET_MAP.get(sys.platform, ("", sys.platform))[1]


class UpdateAvailableDialog(QDialog):
    """Show release notes; let the user download or visit GitHub."""

    def __init__(self, info: dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Update available")
        self.resize(640, 520)

        self._info = info
        self._asset = _pick_asset(info.get("assets", []))
        self._download_worker: DownloadWorker | None = None

        layout = QVBoxLayout(self)

        header = QLabel(
            f"<b>SupraSimFit {info['latest_version']} is available.</b><br>"
            f"You're running {__version__}."
        )
        header.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(header)

        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        notes.setMarkdown(info.get("body") or "_(no release notes)_")
        layout.addWidget(notes, 1)

        # ------------------------------------------------------------------
        # Action row: Download | View on GitHub | (spacer) | Close
        # ------------------------------------------------------------------
        action_row = QHBoxLayout()

        if self._asset:
            self._download_btn = QPushButton(f"Download for {_os_label()}")
            self._download_btn.clicked.connect(self._start_download)
        else:
            self._download_btn = QPushButton("No download for this OS")
            self._download_btn.setEnabled(False)
            self._download_btn.setToolTip(
                "This release does not include an asset for your platform. "
                "Use the GitHub link to see what is available."
            )
        action_row.addWidget(self._download_btn)

        view_btn = QPushButton("View on GitHub")
        view_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(info["release_url"]))
        )
        action_row.addWidget(view_btn)

        action_row.addStretch(1)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        action_row.addWidget(close_btn)

        layout.addLayout(action_row)

        # Progress widgets — hidden until download starts
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self._status = QLabel("")
        self._status.setVisible(False)
        layout.addWidget(self._status)

    # ------------------------------------------------------------------
    # Download flow
    # ------------------------------------------------------------------

    def _start_download(self) -> None:
        if not self._asset:
            return
        url = self._asset["browser_download_url"]
        name = self._asset["name"]
        dest = Path.home() / "Downloads" / name

        self._download_btn.setEnabled(False)
        self._download_btn.setText("Downloading…")
        self._progress.setVisible(True)
        self._status.setVisible(True)
        self._status.setText(f"Saving to {dest}")

        self._download_worker = DownloadWorker(url, dest)
        self._download_worker.progress.connect(self._on_progress)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_worker.error.connect(self._on_download_error)
        self._download_worker.start()

    def _on_progress(self, done: int, total: int) -> None:
        mb_done = done / 1_048_576
        if total > 0:
            self._progress.setValue(int(100 * done / total))
            self._status.setText(
                f"Downloaded {mb_done:.1f} MB of {total / 1_048_576:.1f} MB"
            )
        else:
            self._status.setText(f"Downloaded {mb_done:.1f} MB")

    def _on_download_finished(self, path: str) -> None:
        self._progress.setValue(100)
        self._status.setText(f"Saved to {path}")
        # Repurpose the primary button as a "Reveal in file manager" action.
        self._download_btn.setText("Show in file manager")
        self._download_btn.setEnabled(True)
        try:
            self._download_btn.clicked.disconnect()
        except TypeError:
            pass  # already disconnected
        folder = str(Path(path).parent)
        self._download_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        )

    def _on_download_error(self, msg: str) -> None:
        self._progress.setVisible(False)
        self._status.setVisible(False)
        self._download_btn.setEnabled(True)
        self._download_btn.setText(f"Download for {_os_label()}")
        QMessageBox.warning(self, "Download failed", msg)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """Cancel and join an in-flight download before the dialog closes.

        Closing via Close/Esc/window-close while the ``DownloadWorker`` is
        running would otherwise destroy a live ``QThread`` and abort the
        app. ``cancel()`` flips a flag the worker checks between 64 KB
        chunks, so ``wait()`` returns almost immediately.
        """
        worker = self._download_worker
        if worker is not None and worker.isRunning():
            worker.cancel()
            worker.wait()
        super().closeEvent(event)
