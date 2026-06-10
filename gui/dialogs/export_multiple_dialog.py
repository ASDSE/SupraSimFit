"""Consolidated multi-artefact export dialog.

Lets the user pick which artefacts to export (raw data, fit results,
plots, style template), choose a target folder + filename base, and
write them all in a single click. Persists the last selection under
``QSettings`` group ``export_multiple/*``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui.preferences import _settings
from gui.session import ExportableArtefact, build_artefacts, export_batch

if TYPE_CHECKING:
    from gui.fitting_session import FittingSession


SETTINGS_GROUP = 'export_multiple'


@dataclass
class _Row:
    art: ExportableArtefact
    checkbox: QCheckBox
    filename_label: QLabel


class ExportMultipleDialog(QDialog):
    """Pick artefacts, folder, and filename base; export in one click."""

    def __init__(
        self,
        session: 'FittingSession',
        select_all_default: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle('Export Multiple' if not select_all_default else 'Export All')
        self.setMinimumWidth(560)

        self._session = session
        self._artefacts = build_artefacts(session)
        self._rows: list[_Row] = []

        self._build_ui()
        self._load_settings(select_all_default=select_all_default)
        self._refresh_filenames()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # --- artefacts box -----------------------------------------------
        box = QGroupBox('Artefacts')
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        for art in self._artefacts:
            cb = QCheckBox(art.label)
            fname = QLabel('')
            fname.setStyleSheet('color: #555;')
            if not art.available:
                cb.setEnabled(False)
                cb.setChecked(False)
                cb.setToolTip(art.unavailable_reason)
                fname.setEnabled(False)
            cb.toggled.connect(self._refresh_filenames)
            row_layout = QHBoxLayout()
            row_layout.addWidget(cb, stretch=0)
            row_layout.addStretch(1)
            row_layout.addWidget(fname, stretch=0)
            form.addRow(row_layout)
            self._rows.append(_Row(art=art, checkbox=cb, filename_label=fname))

        btn_row = QHBoxLayout()
        all_btn = QPushButton('Select all available')
        none_btn = QPushButton('Select none')
        all_btn.clicked.connect(self._select_all_available)
        none_btn.clicked.connect(self._select_none)
        btn_row.addWidget(all_btn)
        btn_row.addWidget(none_btn)
        btn_row.addStretch(1)
        root.addWidget(box)
        root.addLayout(btn_row)

        # --- folder + base name ------------------------------------------
        target_box = QGroupBox('Target')
        target_form = QFormLayout(target_box)
        folder_row = QHBoxLayout()
        self._folder_edit = QLineEdit()
        browse = QPushButton('Browse…')
        browse.clicked.connect(self._on_browse)
        folder_row.addWidget(self._folder_edit, stretch=1)
        folder_row.addWidget(browse)
        target_form.addRow('Folder', folder_row)

        self._base_edit = QLineEdit()
        self._base_edit.textChanged.connect(self._refresh_filenames)
        target_form.addRow('Filename base', self._base_edit)
        root.addWidget(target_box)

        # --- distributions config summary --------------------------------
        self._dist_summary = QLabel('')
        self._dist_summary.setStyleSheet('color: #444;')
        self._dist_summary.setWordWrap(True)
        root.addWidget(self._dist_summary)

        # --- buttons -----------------------------------------------------
        self._buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self._export_btn = QPushButton('Export')
        self._export_btn.setDefault(True)
        self._buttons.addButton(self._export_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        self._buttons.rejected.connect(self.reject)
        self._export_btn.clicked.connect(self._on_export)
        root.addWidget(self._buttons)

    # ------------------------------------------------------------------
    # Behaviour
    # ------------------------------------------------------------------

    def _select_all_available(self) -> None:
        for row in self._rows:
            if row.art.available:
                row.checkbox.setChecked(True)

    def _select_none(self) -> None:
        for row in self._rows:
            row.checkbox.setChecked(False)

    def _selected_artefacts(self) -> list[ExportableArtefact]:
        return [r.art for r in self._rows if r.checkbox.isChecked() and r.art.available]

    def _on_browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, 'Choose Export Folder', self._folder_edit.text() or str(Path.home())
        )
        if folder:
            self._folder_edit.setText(folder)

    def _refresh_filenames(self) -> None:
        base = self._base_edit.text().strip() or 'output'
        for row in self._rows:
            row.filename_label.setText(f'→ {base}{row.art.suffix}')
        # Refresh distributions summary if that artefact is checked.
        dist_checked = any(r.checkbox.isChecked() and r.art.key == 'distributions_png' for r in self._rows)
        if dist_checked:
            cfg = self._session._distributions_export_config()
            self._dist_summary.setText(
                f'Distributions layout: {cfg.rows}×{cfg.cols}, '
                f'{cfg.width_in:.1f}×{cfg.height_in:.1f} in @ {cfg.dpi} DPI '
                f'(change via "Save Distributions Plot…")'
            )
            self._dist_summary.setVisible(True)
        else:
            self._dist_summary.setVisible(False)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_settings(self, *, select_all_default: bool) -> None:
        s = _settings()
        s.beginGroup(SETTINGS_GROUP)
        try:
            saved_sel = s.value('selected', None)
            saved_folder = s.value('folder', '', type=str)
            saved_base = s.value('filename_base', '', type=str)
        finally:
            s.endGroup()

        # Selection: Export All overrides with every available artefact.
        if select_all_default:
            keep = {r.art.key for r in self._rows if r.art.available}
        elif isinstance(saved_sel, list) and saved_sel:
            keep = set(saved_sel)
        else:
            keep = {r.art.key for r in self._rows if r.art.available}
        for row in self._rows:
            if row.art.available:
                row.checkbox.setChecked(row.art.key in keep)

        # Folder: prefer saved, else dataset's directory, else home.
        if saved_folder and Path(saved_folder).exists():
            self._folder_edit.setText(saved_folder)
        else:
            self._folder_edit.setText(self._default_folder())

        # Base: prefer the saved value only if it's still relevant.
        default_base = self._session._default_filename_base()
        self._base_edit.setText(saved_base or default_base)

    def _save_settings(self) -> None:
        s = _settings()
        s.beginGroup(SETTINGS_GROUP)
        try:
            s.setValue(
                'selected',
                [r.art.key for r in self._rows if r.checkbox.isChecked()],
            )
            s.setValue('folder', self._folder_edit.text())
            s.setValue('filename_base', self._base_edit.text())
        finally:
            s.endGroup()

    def _default_folder(self) -> str:
        src = self._session._state.source_file
        if not src and self._session._state.fit_results:
            src = self._session._state.fit_results[-1].source_file
        if src:
            parent = Path(src).parent
            if parent.exists():
                return str(parent)
        return str(Path.home())

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _on_export(self) -> None:
        selected = self._selected_artefacts()
        if not selected:
            QMessageBox.information(
                self,
                'Nothing Selected',
                'Tick at least one artefact to export.',
            )
            return
        folder_text = self._folder_edit.text().strip()
        if not folder_text:
            QMessageBox.warning(self, 'Missing Folder', 'Choose a target folder.')
            return
        folder = Path(folder_text)
        base = self._base_edit.text().strip() or 'output'

        outcomes = export_batch(selected, folder, base)
        self._save_settings()

        successes = [o for o in outcomes if o[2] is None]
        failures = [o for o in outcomes if o[2] is not None]

        if failures:
            details = '\n'.join(f'  • {label}: {exc}' for label, _path, exc in failures)
            QMessageBox.warning(
                self,
                'Export — some artefacts failed',
                (f'Wrote {len(successes)}/{len(outcomes)} artefacts to:\n{folder}\n\nFailures:\n{details}'),
            )
        # Even on partial failure we close — the user has the message.
        self.accept()
        self._last_outcomes = outcomes  # exposed for callers / tests

    # ------------------------------------------------------------------
    # Public access for callers
    # ------------------------------------------------------------------

    @property
    def outcomes(self) -> list[tuple[str, Path, Exception | None]]:
        return getattr(self, '_last_outcomes', [])
