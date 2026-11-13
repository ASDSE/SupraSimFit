"""Measurements: the files of the session's experiment, their raw titration, and the settings
that decide which points and replicates reach the fit (DESIGN.md §8).

Canvas: the Files table (*Add files…*, × removes a file), a note on how added files are
used, and the Titration plot with its display unit. Side panel *Measurement settings*:
Concentrations, Replicates and Outlier removal. Every change goes to the session's
model; the view redraws when the model says the data changed.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QMargins, QObject, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QPainterPath
from PyQt6.QtWidgets import QFileDialog, QGridLayout, QMessageBox, QSizePolicy, QWidget

from core.assays.registry import ASSAY_REGISTRY
from core.units import Q_
from gui.dataset import UNITS, file_filter
from gui.design import components as C
from gui.design import icons
from gui.design.appearance import theme
from gui.design.tokens import Theme, font, space
from gui.plotting.labels import _display_label, and_join
from gui.session_model import SessionModel
from gui.views.titration import TitrationData, TitrationPlot

_SUPERSCRIPT = str.maketrans('0123456789-', '⁰¹²³⁴⁵⁶⁷⁸⁹⁻')
_THIN = ' '

NEW_SESSION = 'Load data into a new session…'


def molar(value: float) -> str:
    """A concentration as the list shows it: 0, or the mantissa with the digits entered × 10ⁿ."""
    if value == 0:
        return '0'
    e = math.floor(math.log10(abs(value)))
    mantissa = f'{value / 10**e:.5f}'.rstrip('0').rstrip('.')
    if e == 0:
        return mantissa
    return f'{mantissa}{_THIN}×{_THIN}10{str(e).translate(_SUPERSCRIPT)}'


class FilesTable(QWidget):
    """The files of the experiment, one row each, with the replicate it became; × removes one."""

    HEAD, ROW = 28, 40
    COLS = (('File', 0.0), ('Format', 0.42), ('Replicate', 0.66), ('Points', 0.86))

    remove_requested = pyqtSignal(str)

    def __init__(self, t: Theme):
        super().__init__()
        self.t = t
        self.rows: list[dict] = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.set_rows([])

    def set_rows(self, rows: list[dict]) -> None:
        """Show *rows*: dicts with ``path``, ``name``, ``format``, ``letters``, ``on`` and ``points``."""
        self.rows = rows
        self.setFixedHeight(self.HEAD + max(len(rows), 1) * self.ROW)
        self.setAccessibleDescription('; '.join(f'{r["name"]}, replicate {r["letters"]}' for r in rows))
        self.update()

    def _remove_rect(self, i: int) -> QRectF:
        return QRectF(self.width() - 24, self.HEAD + i * self.ROW + (self.ROW - 24) / 2, 24, 24)

    def mousePressEvent(self, event) -> None:
        for i, row in enumerate(self.rows):
            if self._remove_rect(i).contains(event.position()):
                self.remove_requested.emit(row['path'])
                return

    def mouseMoveEvent(self, event) -> None:
        over = any(self._remove_rect(i).contains(event.position()) for i in range(len(self.rows)))
        self.setCursor(Qt.CursorShape.PointingHandCursor if over else Qt.CursorShape.ArrowCursor)
        self.setToolTip('Remove this file and its replicates' if over else '')

    def paintEvent(self, _):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = self.width() - 32  # room for the remove button
        xs = {name: frac * width for name, frac in self.COLS}
        p.setFont(font('label'))
        p.setPen(t.q('text-tertiary'))
        for name, _frac in self.COLS:
            p.drawText(QRectF(xs[name], 0, 200, self.HEAD), Qt.AlignmentFlag.AlignVCenter, name)
        p.fillRect(QRectF(0, self.HEAD - 1, self.width(), 1), t.q('border'))
        if not self.rows:
            p.setFont(font('body'))
            p.setPen(t.q('text-tertiary'))
            text = 'No files yet. Add files to load the measurements of this experiment.'
            p.drawText(QRectF(0, self.HEAD, self.width(), self.ROW), Qt.AlignmentFlag.AlignVCenter, text)
        for i, row in enumerate(self.rows):
            y = self.HEAD + i * self.ROW
            cy = y + self.ROW / 2
            icons.paint(p, 'file-text', t.q('text-secondary'), 0, cy - 8, 16)
            p.setFont(font('body'))
            p.setPen(t.q('text-primary'))
            name_w = xs['Format'] - 16 - space(3) - space(4)
            name = p.fontMetrics().elidedText(row['name'], Qt.TextElideMode.ElideMiddle, int(name_w))
            p.drawText(QRectF(16 + space(3), y, name_w, self.ROW), Qt.AlignmentFlag.AlignVCenter, name)
            p.setPen(t.q('text-secondary'))
            p.drawText(
                QRectF(xs['Format'], y, xs['Replicate'] - xs['Format'], self.ROW),
                Qt.AlignmentFlag.AlignVCenter,
                row['format'],
            )
            on = row['on']
            tile_w = max(20, p.fontMetrics().horizontalAdvance(row['letters']) + space(3))
            tile = QRectF(xs['Replicate'], cy - 10, tile_w, 20)
            path = QPainterPath()
            path.addRoundedRect(tile, 5, 5)
            p.fillPath(path, t.q('accent-subtle' if on else 'bg-subtle'))
            p.setFont(font('number-strong'))
            p.setPen(t.q('accent' if on else 'text-tertiary'))
            p.drawText(tile, Qt.AlignmentFlag.AlignCenter, row['letters'])
            if row.get('off_note'):
                p.setFont(font('small'))
                p.setPen(t.q('text-secondary'))
                p.drawText(
                    QRectF(tile.right() + space(3), y, 140, self.ROW), Qt.AlignmentFlag.AlignVCenter, row['off_note']
                )
            p.setFont(font('number'))
            p.setPen(t.q('text-primary'))
            p.drawText(QRectF(xs['Points'], y, 60, self.ROW), Qt.AlignmentFlag.AlignVCenter, str(row['points']))
            r = self._remove_rect(i)
            icons.paint(p, 'x', t.q('text-tertiary'), r.left() + 4, r.top() + 4, 16)
            if i < len(self.rows) - 1:
                p.fillRect(QRectF(0, y + self.ROW - 1, self.width(), 1), t.q('border' if t.dark else 'grid'))
        p.end()


class MeasurementsView(QObject):
    """The canvas and side panel of Measurements over *model*; *parent* is where its dialogs open.

    :attr:`new_session_link` is the note's *Load data into a new session…*, which the window
    answers; :attr:`display_unit_changed` says the plots' unit was chosen.
    """

    display_unit_changed = pyqtSignal(str)

    def __init__(self, model: SessionModel, parent: QWidget):
        super().__init__(parent)
        self.model, self.parent, self.t = model, parent, theme()
        self.canvas = self._build_canvas()
        self.side = self._build_side()
        model.data_changed.connect(self.refresh)
        model.results_changed.connect(lambda _scope: self.refresh())
        self.refresh()

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def _ask_files(self, title: str) -> list[str]:
        paths, _ = QFileDialog.getOpenFileNames(self.parent, title, '', file_filter())
        return paths

    def add_files(self) -> None:
        """Ask for files and add them to the session as further replicates."""
        paths = self._ask_files('Add files to this session')
        if paths:
            self._say(self.model.add_files(paths))

    def replace_data(self) -> bool:
        """Ask for files and load them in place of the session's data; whether anything was loaded."""
        paths = self._ask_files('Load data')
        if not paths:
            return False
        refusal = self.model.load_files(paths)
        self._say(refusal)
        return refusal is None

    def _say(self, refusal) -> None:
        if refusal is not None:
            QMessageBox.warning(self.parent, refusal.title, refusal.message)

    def _remove(self, path: str) -> None:
        self._say(self.model.remove_file(path))

    def _set_display_unit(self, index: int) -> None:
        self.model.update_settings(display_unit=UNITS[index])
        self.display_unit_changed.emit(UNITS[index])
        self.refresh()

    def _set_imported_unit(self, index: int) -> None:
        if self.model.dataset is not None:
            self.model.set_imported_unit(UNITS[index])

    def _edit_concentration(self, index: int, text: str) -> None:
        refusal = self.model.set_concentration(index, text)
        self._say(refusal)
        if refusal is not None:
            self.refresh()

    def focus_concentrations(self) -> None:
        """Open the first concentration for typing, for a fit that needs real concentrations."""
        self.conc_section.header.set_open(True)
        self.grid.edit(0)

    def _load_vector(self) -> None:
        if self.model.dataset is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self.parent, 'Load concentrations', '', 'Concentration file (*.json);;All files (*)'
        )
        if not path:
            return
        refusal, notice = self.model.load_concentrations(path)
        self._say(refusal)
        if notice:
            QMessageBox.information(self.parent, 'Units Converted', notice)

    def _save_vector(self) -> None:
        dataset = self.model.dataset
        if dataset is None:
            return
        stem = Path(dataset.files[0].path).stem if dataset.files else 'concentrations'
        path, _ = QFileDialog.getSaveFileName(
            self.parent, 'Save concentrations', f'{stem}_concentrations.json', 'Concentration file (*.json)'
        )
        if path:
            self._say(self.model.save_concentrations(path))

    def _apply_outliers(self) -> None:
        try:
            threshold = float(self.threshold.text)
            minimum = int(self.min_replicates.text)
        except ValueError:
            QMessageBox.warning(
                self.parent,
                'Outlier Removal',
                'The Z-score threshold must be a number, such as 3.5, and Min replicates a whole number, such as 3.',
            )
            return
        if threshold <= 0 or minimum < 2:
            QMessageBox.warning(
                self.parent,
                'Outlier Removal',
                'The Z-score threshold must be above 0, and Min replicates at least 2.',
            )
            return
        self._say(self.model.remove_outliers(threshold, minimum))

    def _choose_channel(self, index: int) -> None:
        dataset = self.model.dataset
        if dataset is not None and dataset.channels:
            self._say(self.model.select_channel(dataset.channels[index]))

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    def _build_canvas(self) -> QWidget:
        t = self.t
        w = QWidget()
        w.setObjectName('Canvas')
        w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        add = C.tool_button(t, 'Add files…', 'plus')
        add.setToolTip('Add files to this session as further replicates')
        add.clicked.connect(self.add_files)
        self.files_summary = C.label('', 'small', 'tertiary')
        self.files = FilesTable(t)
        self.files.remove_requested.connect(self._remove)
        note = C.label(
            'Added files become replicates on this concentration grid. Another experiment needs its own session.',
            'small',
            'secondary',
        )
        note.setMinimumWidth(1)  # keeps the canvas from widening the split
        self.new_session_link = C.link_button(NEW_SESSION)
        self.legend = C.LegendRow(t, [])
        self.display_unit = C.Dropdown(t, 'µM', 72, options=list(UNITS))
        self.display_unit.setAccessibleName('Display unit of the titration plot')
        self.display_unit.chosen.connect(self._set_display_unit)
        self.save_plot = C.tool_button(t, None, 'image')
        self.save_plot.setToolTip('Save the plot as an image')
        self.save_plot.setAccessibleName('Save the titration plot as an image')
        self.plot = TitrationPlot()
        lay = C.vbox(
            C.hbox(C.label('Files', 'body-strong'), 3, self.files_summary, None, add, spacing=0),
            2,
            self.files,
            3,
            C.hbox(C.Icon(t, 'info', 'text-tertiary'), note, 3, self.new_session_link, None, spacing=3),
            6,
            C.hairline(),
            5,
            C.hbox(
                C.label('Titration', 'body-strong'),
                3,
                C.label('raw signal, as loaded', 'small', 'tertiary'),
                None,
                self.legend,
                6,
                C.label('Display unit', 'small', 'secondary'),
                2,
                self.display_unit,
                3,
                self.save_plot,
                spacing=0,
            ),
            2,
            spacing=0,
            margins=(6, 5, 6, 4),
        )
        lay.addWidget(self.plot, 1)
        w.setLayout(lay)
        return w

    def _build_side(self) -> QWidget:
        t = self.t
        # Concentrations
        self.imported_unit = C.Segmented(t, list(UNITS), current=UNITS.index('M'), width=168)
        self.imported_unit.setAccessibleName('Unit the concentrations are stated in')
        self.imported_unit.changed.connect(self._set_imported_unit)
        unit_note = C.label('Changing it reinterprets the values below.', 'small', 'tertiary')
        unit_note.setWordWrap(True)
        self.channel = C.Dropdown(t, '', 200)
        self.channel.setAccessibleName('Channel of the plate export')
        self.channel.chosen.connect(self._choose_channel)
        self.channel_row = QWidget()
        self.channel_row.setLayout(C.hbox(C.label('Channel', 'body', 'secondary'), None, self.channel, spacing=3))
        self.grid = C.ConcentrationGrid(t, [], '', editable=True)
        self.grid.edited.connect(self._edit_concentration)
        load = C.link_button('Load vector…')
        load.clicked.connect(self._load_vector)
        save = C.link_button('Save vector…')
        save.clicked.connect(self._save_vector)
        conc = QWidget()
        conc.setLayout(
            C.vbox(
                C.hbox(C.label('Imported unit', 'body', 'secondary'), None, self.imported_unit, spacing=3),
                unit_note,
                self.channel_row,
                3,
                self.grid,
                2,
                C.hbox(load, save, None, spacing=5),
                spacing=2,
            )
        )
        # Replicates
        # Chips wrap four to a row, so eight replicates stay inside the side panel's width.
        self.chip_row = QGridLayout()
        self.chip_row.setSpacing(space(2))
        self.chip_row.setContentsMargins(QMargins())
        self.chip_row.setColumnStretch(4, 1)
        self.reset_all = C.link_button('Reset all')
        self.reset_all.clicked.connect(self.model.reset_replicates)
        self.replicate_note = C.label('', 'small', 'tertiary')
        self.replicate_note.setWordWrap(True)
        chips = QWidget()
        chips.setLayout(self.chip_row)
        reps = QWidget()
        reps.setLayout(C.vbox(chips, C.hbox(None, self.reset_all, spacing=2), self.replicate_note, spacing=2))
        self._chips: list[QWidget] = []
        # Outlier removal
        self.threshold = C.Field(t, '3.5', editable=True)
        self.threshold.setAccessibleName('Z-score threshold of outlier removal')
        self.min_replicates = C.Field(t, '3', editable=True)
        self.min_replicates.setAccessibleName('Minimum replicates in use for outlier removal')
        self.outlier_note = C.label('', 'small', 'secondary')
        self.outlier_note.setWordWrap(True)
        self.outlier_icon = C.Icon(t, 'info')
        apply = C.OutlineButton(t, 'Apply')
        apply.clicked.connect(self._apply_outliers)
        reset = C.tool_button(t, 'Reset', 'rotate')
        reset.setToolTip('Use every replicate again')
        reset.clicked.connect(self.model.reset_replicates)

        def field(name: str, widget: QWidget) -> QWidget:
            box = QWidget()
            box.setLayout(C.vbox(C.label(name, 'small', 'secondary'), widget, spacing=2))
            return box

        self.outlier_result_row = QWidget()
        self.outlier_result_row.setLayout(
            C.hbox(C.vbox(self.outlier_icon, None, margins=(0, 1, 0, 0)), self.outlier_note, spacing=3)
        )
        outl = QWidget()
        outl.setLayout(
            C.vbox(
                C.hbox(
                    field('Z-score threshold', self.threshold), field('Min replicates', self.min_replicates), spacing=4
                ),
                2,
                self.outlier_result_row,
                2,
                C.hbox(apply, reset, None, spacing=2),
                spacing=3,
            )
        )
        self.conc_section = C.section(t, 'Concentrations', conc, first=True)
        self.reps_section = C.section(t, 'Replicates', reps)
        outl_section = C.section(t, 'Outlier removal', outl, trailing='Z-score')
        content = QWidget()
        content.setLayout(C.vbox(self.conc_section, self.reps_section, outl_section, spacing=0))
        return content

    # ------------------------------------------------------------------
    # Drawing from the model
    # ------------------------------------------------------------------

    def badge(self) -> str | None:
        """The summary beside the title: how many files the session holds."""
        dataset = self.model.dataset
        n = 0 if dataset is None else len(dataset.files)
        return f'{n} file{"" if n == 1 else "s"}' if n else None

    def refresh(self) -> None:
        model, dataset = self.model, self.model.dataset
        ms = model.measurement_set
        unit = model.settings.display_unit
        self.display_unit.set_choice(unit)
        x_name = ASSAY_REGISTRY[model.settings.assay_type].x_label
        if ms is None:
            self.files.set_rows([])
            self.files_summary.setText('')
            self.legend.set_items([])
            self.plot.show_data(None, unit)
            self.grid.set_values([], f'{x_name} (M)')
            self.conc_section.header.set_trailing('')
            self.reps_section.header.set_trailing('')
            self.channel_row.setVisible(False)
            self._set_chips([])
            self.replicate_note.setText('Load data to choose the replicates the fit uses.')
            self.outlier_result_row.setVisible(False)
            return
        letters = {rid: _display_label(i) for i, rid in enumerate(ms.replica_ids)}
        last = dataset.outlier_result
        by_filter = set(last.get('dropped', [])) if last and last.get('status') == 'applied' else set()
        rows = []
        for f in dataset.files:
            ids = [r for r in f.replica_ids if r in letters]
            on = any(ms.is_active(r) for r in ids)
            off = [r for r in ids if not ms.is_active(r)]
            note = ''
            if len(ids) == 1 and off:
                note = 'Off · outlier' if off[0] in by_filter else 'Off'
            span = letters[ids[0]] if len(ids) == 1 else f'{letters[ids[0]]}–{letters[ids[-1]]}'
            rows.append(
                {
                    'path': f.path,
                    'name': f.name,
                    'format': f.format,
                    'letters': span,
                    'on': on,
                    'off_note': note,
                    'points': ms.n_points,
                }
            )
        self.files.set_rows(rows)
        x_disp = np.asarray(ms.concentrations) * Q_(1.0, 'M').to(unit).magnitude
        n_files = len(dataset.files)
        self.files_summary.setText(
            f'{n_files} file{"" if n_files == 1 else "s"} · {ms.n_replicas} replicate{"" if ms.n_replicas == 1 else "s"}'
            f' · one grid of {ms.n_points} points, {x_disp.min():.3g} – {x_disp.max():.3g} {unit}'
        )
        off = [letters[r] for r in ms.replica_ids if not ms.is_active(r)]
        items = [('dots', f'Replicates ({ms.n_active})')]
        if off:
            items.append(('cross', f'{and_join(off)} switched off'))
        self.legend.set_items(items)
        self.plot.show_data(
            TitrationData(
                x_molar=np.asarray(ms.concentrations, dtype=float),
                signals=np.asarray(ms.signals, dtype=float),
                active=[ms.is_active(r) for r in ms.replica_ids],
                x_name=x_name,
            ),
            unit,
        )
        # Concentrations
        self.imported_unit.set_current(UNITS.index(dataset.imported_unit))
        self.grid.set_values([molar(v) for v in dataset.face_values], f'{x_name} ({dataset.imported_unit})')
        self.conc_section.header.set_trailing(f'{ms.n_points} points')
        self.channel_row.setVisible(len(dataset.channels) > 1)
        if dataset.channels:
            labels = [dataset.channel_label(c) for c in dataset.channels]
            self.channel.set_choice(dataset.channel_label(dataset.channel), labels)
        # Replicates
        self._set_chips([(rid, letters[rid], ms.is_active(rid), rid in by_filter) for rid in ms.replica_ids])
        self.reps_section.header.set_trailing(f'{ms.n_active} of {ms.n_replicas} used')
        filtered = [letters[r] for r in ms.replica_ids if r in by_filter and not ms.is_active(r)]
        lead = (
            f'{and_join(filtered)} {"was" if len(filtered) == 1 else "were"} switched off by outlier removal (z). '
            if filtered
            else ''
        )
        self.replicate_note.setText(f'{lead}Click a replicate to switch it on or off.')
        # Outlier removal
        self.outlier_result_row.setVisible(last is not None)
        if last is not None:
            self.outlier_note.setText(self._outlier_sentence(last, letters, ms, unit))

    def _set_chips(self, chips: list[tuple[str, str, bool, bool]]) -> None:
        for chip in self._chips:
            self.chip_row.removeWidget(chip)
            chip.deleteLater()
        self._chips = []
        for i, (rid, letter, on, by_filter) in enumerate(chips):
            chip = C.ReplicateChip(self.t, letter, on, by_filter=by_filter and not on)
            chip.setToolTip(rid)
            chip.toggled_on.connect(lambda state, rid=rid: self.model.set_replicate(rid, state))
            self.chip_row.addWidget(chip, *divmod(i, 4))
            self._chips.append(chip)
        self.reset_all.setVisible(bool(chips))

    @staticmethod
    def _outlier_sentence(entry: dict, letters: dict, ms, unit: str) -> str:
        """What the last outlier removal did, with the point that put each replicate out."""
        threshold = entry.get('threshold', 0.0)
        if entry.get('status') != 'applied':
            return f'Last attempt did not run: fewer replicates were in use than Min replicates ({entry.get("min_replicas")}).'
        dropped = entry.get('dropped', [])
        if not dropped:
            return f'Last applied: every replicate lies within z = {threshold:g} of the others; none was switched off.'
        scale = Q_(1.0, 'M').to(unit).magnitude
        evidence = entry.get('evidence', {})
        parts = []
        for rid in dropped:
            seen = evidence.get(rid)
            if seen is None:
                continue
            at = float(ms.concentrations[seen['point']]) * scale
            parts.append(f'{letters.get(rid, rid)}: its point at {at:.3g} {unit} has z = {seen["z"]:.1f}')
        names = and_join([letters.get(r, r) for r in dropped])
        why = f' ({"; ".join(parts)}, above {threshold:g})' if parts else ''
        return f'Last applied: switched off {names}, far from the other replicates{why}.'
