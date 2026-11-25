"""Export ▸ Export several…: write a chosen set of the session's files to one folder in one step.

One page in two settings groups, in the look of the Settings window. **Files**: one row per
artefact :func:`gui.session.build_artefacts` defines, a checkbox with the name the file
will take; one that cannot be written now is disabled, its reason as its tooltip. Every
available one starts ticked. **Destination**: the folder (*Choose…*) and the text every
file name starts with. *Export* is the window's one primary button. The folder and the
name are remembered under the ``QSettings`` group ``export_multiple``; the name only for
the data file it was chosen for.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QDialog, QFileDialog, QLabel, QMessageBox, QWidget

from gui.design import components as C
from gui.design.appearance import appearance, theme
from gui.design.tokens import SIZE
from gui.plotting.export import ExportRefused
from gui.preferences import _settings
from gui.session import ExportableArtefact, build_artefacts, export_batch

if TYPE_CHECKING:
    from gui.fitting_session import FittingSession


SETTINGS_GROUP = 'export_multiple'
#: What to check when a file or the folder cannot be written.
WRITE_HINT = 'Check that the folder exists and that you may write there.'


def _row(*items) -> QWidget:
    w = QWidget()
    w.setLayout(C.hbox(*items, margins=(4, 2, 4, 2)))
    return w


class ExportMultipleDialog(QDialog):
    """Pick the files, the folder and the start of their names; *Export* writes them all."""

    def __init__(self, session: 'FittingSession', parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle('Export several')
        self.setFixedWidth(SIZE['settings-window'])
        self._session = session
        self._artefacts = build_artefacts(session)
        self.outcomes: list[tuple[str, Path, Exception | None]] = []
        self.setLayout(C.vbox(spacing=0))
        self._body: QWidget | None = None
        folder, base = self._remembered()
        self._build({a.key for a in self._artefacts if a.available}, folder, base)
        # The controls on a dark card are drawn in colours lifted for it, read once, so a
        # change of theme draws the page again.
        appearance().changed.connect(self._rebuild)

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _build(self, ticked: set[str], folder: str, base: str) -> None:
        t = theme()
        ct = C.on_card(t)
        self.boxes: dict[str, C.Checkbox] = {}
        self._names: dict[str, QLabel] = {}
        rows = []
        for art in self._artefacts:
            box = C.Checkbox(ct, art.label, art.available and art.key in ticked)
            box.setAccessibleName(f'Export {art.label}')
            name = C.label('', 'small', 'tertiary')
            if not art.available:
                box.setEnabled(False)
                box.setToolTip(art.unavailable_reason)
                name.setToolTip(art.unavailable_reason)
            self.boxes[art.key] = box
            self._names[art.key] = name
            rows.append(_row(box, None, name))
        select_all, select_none = C.link_button('Select all'), C.link_button('Select none')
        select_all.clicked.connect(lambda: self._tick_all(True))
        select_none.clicked.connect(lambda: self._tick_all(False))
        links = QWidget()
        links.setLayout(C.hbox(select_all, select_none, spacing=4))

        self.folder = C.Field(ct, folder, kind='text', editable=True)
        self.folder.setAccessibleName('Folder to export to')
        choose = C.OutlineButton(ct, 'Choose…')
        choose.setAccessibleName('Choose the folder to export to')
        choose.clicked.connect(self._choose_folder)
        self.base = C.Field(ct, base, kind='text', editable=True)
        self.base.setAccessibleName('Start of every file name')
        self.base.typed.connect(lambda _text: self._show_names())
        label_width = SIZE['input-name']

        def named(text: str) -> QWidget:
            lbl = C.label(text)
            lbl.setFixedWidth(label_width)
            return lbl

        destination = C.SettingsCard(
            t,
            [
                _row(named('Folder'), self.folder, choose),
                _row(named('File names start with'), self.base),
            ],
        )

        cancel = C.OutlineButton(t, 'Cancel')
        cancel.clicked.connect(self.reject)
        export = C.primary_button(t, 'Export', 'export')
        export.clicked.connect(self._on_export)

        body = QWidget()
        body.setLayout(
            C.vbox(
                C.settings_group('Files', C.SettingsCard(t, rows), links),
                6,
                C.settings_group('Destination', destination),
                6,
                C.hbox(None, cancel, export),
                spacing=0,
                margins=(6, 5, 6, 5),
            )
        )
        if self._body is not None:
            C.drop(self._body)
        self.layout().addWidget(body)
        body.show()  # a child added to a window already on screen is shown by hand
        self._body = body
        self._show_names()

    def _rebuild(self) -> None:
        ticked = {key for key, box in self.boxes.items() if box.checked}
        self._build(ticked, self._folder_text(), self.base.editor.text())

    def _show_names(self) -> None:
        base = self._base_text()
        for art in self._artefacts:
            self._names[art.key].setText(f'{base}{art.suffix}')

    def paintEvent(self, _) -> None:
        t = theme()
        p = QPainter(self)
        p.fillRect(self.rect(), t.q('bg-raised' if t.dark else 'bg-window'))
        p.end()

    # ------------------------------------------------------------------
    # Editing
    # ------------------------------------------------------------------

    def _tick_all(self, on: bool) -> None:
        for art in self._artefacts:
            if art.available:
                self.boxes[art.key].set_checked(on)

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, 'Choose a folder', self._folder_text() or str(Path.home()))
        if folder:
            self.folder.set_text(folder)

    def _folder_text(self) -> str:
        return self.folder.editor.text().strip()

    def _base_text(self) -> str:
        return self.base.editor.text().strip() or self._default_base()

    def _selected_artefacts(self) -> list[ExportableArtefact]:
        return [a for a in self._artefacts if a.available and self.boxes[a.key].checked]

    # ------------------------------------------------------------------
    # Remembered folder and name
    # ------------------------------------------------------------------

    def _remembered(self) -> tuple[str, str]:
        """The folder and the start of the file names to open with: the ones last used, where they still apply."""
        s = _settings()
        s.beginGroup(SETTINGS_GROUP)
        try:
            folder = s.value('folder', '', type=str)
            base = s.value('filename_base', '', type=str)
            dataset = s.value('filename_dataset', '', type=str)
        finally:
            s.endGroup()
        default_base = self._default_base()
        if not (folder and Path(folder).is_dir()):
            folder = str(self._session.model.save_folder())
        return folder, base if base and dataset == default_base else default_base

    def _save_settings(self) -> None:
        s = _settings()
        s.beginGroup(SETTINGS_GROUP)
        try:
            s.setValue('folder', self._folder_text())
            s.setValue('filename_base', self.base.editor.text().strip())
            s.setValue('filename_dataset', self._default_base())
        finally:
            s.endGroup()

    def _default_base(self) -> str:
        """The stem of the session's data file, which the file names start with unless changed."""
        src = self._session.model.dataset_file()
        return Path(src).stem if src else 'output'

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _on_export(self) -> None:
        selected = self._selected_artefacts()
        if not selected:
            QMessageBox.warning(self, 'Nothing to export', 'Tick at least one file to export.')
            return
        folder_text = self._folder_text()
        if not folder_text:
            QMessageBox.warning(self, 'No folder', 'Choose the folder to export to.')
            return
        folder = Path(folder_text)
        try:
            outcomes = export_batch(selected, folder, self._base_text())
        except OSError:
            QMessageBox.warning(
                self, 'Folder not created', f'Could not create the folder {folder}. {WRITE_HINT} Then export again.'
            )
            return
        self._save_settings()
        self.outcomes = outcomes
        failures = [(label, exc) for label, _path, exc in outcomes if exc is not None]
        if failures:
            # An ExportRefused carries a sentence the app wrote for the user; any other
            # error carries a library's or a programmer's text, which is not shown.
            lines = '\n'.join(
                f'• {label}: {exc if isinstance(exc, ExportRefused) else "could not be written."}'
                for label, exc in failures
            )
            hint = '' if all(isinstance(exc, ExportRefused) for _label, exc in failures) else f'\n\n{WRITE_HINT}'
            written = len(outcomes) - len(failures)
            QMessageBox.warning(
                self,
                'Some files were not exported',
                f'{written} of {len(outcomes)} files were written to {folder}.\n\n{lines}{hint}',
            )
        self.accept()
