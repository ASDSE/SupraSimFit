"""Fit results: the reported binding constants, what to know about them, and the fitted titration (DESIGN.md §8).

Canvas: the headline — each binding constant in the ``metric`` role with the badge of the
reading reported (Input-aware, or Inputs as entered) and its 95 % interval, beside the
interval chart that sets it against the reading at the inputs as entered — then *All
results and diagnostics →*, any callout, and the **Titration** plot with its legend, the
replicate-display tool (the session's one replicate display) and the image export. The
notes of an interval are the tooltips of its interval line and chart, and why the
single-replicate fits differ from it the tooltip of their line. Side panel *Fit details*, which fits its least width and never scrolls sideways:
Fit quality (R², RMSE, replicates used, noise), the replicates' own fits where each was
fitted separately, Diagnostics (each test with its mark and p-value, its full sentence on
hover), Parameters with the footnote of the starred ones and its notes, Input shifts — each
input's name shown whole, a long one broken where it must be.
Everything is read from the session model's held results and redrawn when the model says
they changed; the text and numbers come from :mod:`gui.results`.
"""

from __future__ import annotations

from PyQt6.QtCore import QMargins, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QFont
from PyQt6.QtWidgets import QGridLayout, QLayout, QWidget

from core.assays.registry import AssayType
from gui import results as R
from gui.design import components as C
from gui.design.appearance import theme
from gui.design.tokens import SIZE, font, space
from gui.session_model import Change, SessionModel
from gui.views.titration import TitrationPlot, legend_marks


def _clear(layout: QLayout) -> None:
    """Take every widget and nested layout out of *layout*."""
    while layout.count():
        item = layout.takeAt(0)
        if item.widget() is not None:
            C.drop(item.widget())
        elif item.layout() is not None:
            _clear(item.layout())


class FitResultsView(QObject):
    """The canvas and side panel of Fit results over *model*; *parent* is where its menus open.

    :attr:`reveal_requested` asks for the :class:`~gui.results.Place` a link or a callout's
    action names (*All results and diagnostics →* Diagnostics, the conflict callout the
    readings of Ka confidence); the session shows it.
    """

    reveal_requested = pyqtSignal(object)

    def __init__(self, model: SessionModel, parent: QWidget):
        super().__init__(parent)
        self.model, self.parent, self.t = model, parent, theme()
        self.callouts: list[R.CalloutSpec] = []  # what the callouts on the canvas say
        self.canvas = self._build_canvas()
        self.side = self._build_side()
        model.changed.connect(self._on_changed)
        self._show_plot_appearance()
        self.refresh()

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    def _build_canvas(self) -> QWidget:
        t = self.t
        w = QWidget()
        w.setObjectName('Canvas')
        w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.empty_state = C.EmptyState(t)
        self.headline = QWidget()
        self.headline_box = C.vbox(spacing=4)
        self.replicate_line = C.copyable(C.wrapped('', 'small', 'secondary', rich=True))
        self.headline.setLayout(C.vbox(self.headline_box, 2, self.replicate_line, spacing=0))
        self.callout_host = QWidget()
        self.callout_box = C.vbox(spacing=3, margins=(0, 5, 0, 0))
        self.callout_host.setLayout(self.callout_box)
        self.legend = C.LegendRow(t, [])
        self.display_tool = C.tool_button(t, None, 'scatter', menu=True)
        self.display_tool.setToolTip('Replicate display')
        self.display_tool.setAccessibleName('Replicate display of the titration plot')
        self.display_tool.clicked.connect(self._open_display_menu)
        self.save_plot = C.tool_button(t, None, 'image')
        self.save_plot.setToolTip('Save the plot as an image')
        self.save_plot.setAccessibleName('Save the titration plot as an image')
        self.plot = TitrationPlot()
        self.header = C.PlotHeader(
            t, 'Titration', self.legend, [self.display_tool, 1, self.plot.navigation.tool, 1, self.save_plot]
        )
        lay = C.vbox(
            self.headline,
            self.callout_host,
            self.empty_state,
            6,
            self.header,
            2,
            spacing=0,
            margins=(6, 5, 6, 4),
        )
        lay.addWidget(self.plot, 1)
        w.setLayout(lay)
        return w

    def _build_side(self) -> QWidget:
        t = self.t
        self.no_fit = C.wrapped('', 'small', 'tertiary')

        # Fit quality: R² | RMSE, then Replicates used | Noise, each a value over its note.
        self.r2, self.rmse, self.used, self.noise = (C.copyable(C.label('', 'number-strong')) for _ in range(4))
        self.used_note, self.noise_note = (C.wrapped('', 'small', 'tertiary') for _ in range(2))
        self.noise_stat = QWidget()
        self.noise_stat.setLayout(self._stat('Noise', self.noise, self.noise_note))
        grid = QGridLayout()
        grid.setContentsMargins(QMargins())
        grid.setHorizontalSpacing(space(5))
        grid.setVerticalSpacing(space(4))
        grid.addLayout(self._stat('R²', self.r2), 0, 0)
        grid.addLayout(self._stat('RMSE', self.rmse), 0, 1)
        grid.addLayout(self._stat('Replicates used', self.used, self.used_note), 1, 0)
        grid.addWidget(self.noise_stat, 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        quality = QWidget()
        quality.setLayout(grid)

        # The replicates' own fits
        self.replicate_box = C.vbox(spacing=2)
        replicates = QWidget()
        replicates.setLayout(self.replicate_box)

        # Diagnostics
        self.test_box = C.vbox(spacing=0)
        diagnostics = QWidget()
        diagnostics.setLayout(self.test_box)

        # Parameters
        self.parameters = C.Table(
            t, [('Parameter', 'body', None), ('Estimate', 'number', None), ('Unit', 'small', 'secondary')]
        )
        self.parameter_notes = C.vbox(spacing=2)
        parameters = QWidget()
        parameters.setLayout(C.vbox(self.parameters, 3, self.parameter_notes, spacing=0))

        # Input shifts
        self.shift_grid = QGridLayout()
        self.shift_grid.setContentsMargins(QMargins())
        self.shift_grid.setHorizontalSpacing(space(4))
        self.shift_grid.setVerticalSpacing(0)
        self.shift_grid.setColumnStretch(0, 1)
        self.shift_note = C.wrapped('', 'small', 'tertiary')
        shifts = QWidget()
        shifts.setLayout(C.vbox(self.shift_grid, 3, self.shift_note, spacing=0))

        self.quality_section = C.section(t, 'Fit quality', quality, first=True)
        self.replicates_section = C.section(t, 'Replicates', replicates)
        self.diagnostics_section = C.section(t, 'Diagnostics', diagnostics)
        self.parameters_section = C.section(t, 'Parameters', parameters)
        self.shifts_section = C.section(t, 'Input shifts', shifts)
        self.sections = QWidget()
        self.sections.setLayout(
            C.vbox(
                self.quality_section,
                self.replicates_section,
                self.diagnostics_section,
                self.parameters_section,
                self.shifts_section,
                spacing=0,
            )
        )
        content = QWidget()
        self.no_fit_box = QWidget()
        self.no_fit_box.setLayout(C.vbox(self.no_fit, spacing=0, margins=(0, 0, 0, 3)))
        content.setLayout(C.vbox(self.no_fit_box, self.sections, spacing=0))
        return content

    @staticmethod
    def _stat(name: str, value: QWidget, sub: QWidget | None = None):
        return C.vbox(C.label(name, 'small', 'secondary'), value, *([sub] if sub is not None else []), None, spacing=1)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def display_actions(self) -> list[QAction]:
        """The choices of the replicate-display tool, the session's own checked; each sets the session's display."""
        actions = []
        for i, name in enumerate(R.REPLICATE_DISPLAYS):
            action = QAction(name, self)
            action.setCheckable(True)
            action.setChecked(i == self.model.settings.replicate_display)
            action.triggered.connect(lambda _on=False, i=i: self.model.set_replicate_display(i))
            actions.append(action)
        return actions

    def _open_display_menu(self) -> None:
        menu = C.PopoverMenu(self.t, self.parent.window(), self.display_actions())
        menu.popup(self.display_tool)

    def export_image(self, path: str) -> None:
        """Save the titration plot as shown to *path*, PNG or SVG, in the light theme on white: under its
        description and legend, with the summary of the fit drawn."""
        t = self.titration
        self.plot.export_image(path, t.legend, t.description, t.summary)

    # ------------------------------------------------------------------
    # Drawing from the model
    # ------------------------------------------------------------------

    def _on_changed(self, what: Change) -> None:
        if Change.APPEARANCE in what:
            self._show_plot_appearance()
        if what & (Change.DATA | Change.RESULTS | Change.PROFILE | Change.RUN | Change.BINDING | Change.DISPLAY):
            self.refresh()

    def _show_plot_appearance(self) -> None:
        look = self.model.plot_appearance
        self.plot.set_plot_appearance(look)
        legend_marks(self.legend, look)

    def fit(self):
        """The fit this view reports, or ``None`` when none is shown."""
        fit, note = self.model.fit_view()
        return fit if note is None else None

    def badge(self) -> str | None:
        """The summary beside the title: the reading reported and the replicates it rests on."""
        return R.badge(self.fit(), self.model.measurement_set)

    def refresh(self) -> None:
        model = self.model
        fit, note = model.fit_view()
        shown = fit if note is None else None
        ms = model.measurement_set
        empty = model.empty_view('Fit results')
        self.empty_state.show_empty(empty)
        self._refresh_headline(shown)
        titration = self._refresh_plot()
        # With nothing to show, the empty state takes the plot's room.
        self.header.setVisible(empty is None)
        self.plot.setVisible(empty is None)
        self._refresh_callouts(
            R.callouts(
                shown,
                note,
                unchecked=shown is not None and ms is None,
                others_hidden=model.other_hidden_note(),
                replicates_note=titration.replicates_note,
                others_note=titration.others_note,
            )
        )
        self._refresh_side(shown, note, empty)

    def _refresh_plot(self) -> R.Titration:
        model = self.model
        shown = model.fit_results
        assay_type = AssayType[shown[-1].assay_type] if shown else model.settings.assay_type
        titration = R.titration(model.measurement_set, shown, assay_type, model.settings.replicate_display)
        self.titration = titration
        self.plot.show_data(titration.data, model.settings.display_unit)
        self.legend.set_items(titration.legend)
        self.header.set_description(titration.description)
        # Nothing to display differently or to save until there is something on the plot.
        for tool in (self.display_tool, self.save_plot):
            tool.setEnabled(titration.data is not None)
        return titration

    def _refresh_headline(self, fit) -> None:
        _clear(self.headline_box)
        self.headline.setVisible(fit is not None)
        if fit is None:
            self.replicate_line.setText('')
            return
        model = self.model
        profile = model.profile if model.profiled_fit is fit else None
        blocks = R.ka_blocks(fit, profile, model.profile_running())
        text, tone = R.reading(fit)
        link = C.link_button('All results and diagnostics  →')
        link.clicked.connect(lambda: self.reveal_requested.emit(R.Place.DIAGNOSTICS))
        if not blocks:
            sentence = C.wrapped(
                'This fit has no association constant. Its parameters are listed in Fit details.', 'body', 'secondary'
            )
            self.headline_box.addLayout(C.hbox(sentence, None, link, spacing=3))
        lefts = []
        for i, block in enumerate(blocks):
            row, left = self._headline_row(block, text, tone, link if i == 0 else None)
            self.headline_box.addLayout(row)
            lefts.append(left)
        # One column for every constant, so their interval charts line up.
        width = max([SIZE['headline'], *(left.sizeHint().width() for left in lefts)])
        for left in lefts:
            left.setFixedWidth(width)
        line, tip = R.replicate_line(fit)
        self.replicate_line.setText(line)
        self.replicate_line.setToolTip(tip)
        self.replicate_line.setVisible(bool(line))

    def _headline_row(self, block: R.KaBlock, reading: str, tone: str, link):
        t = self.t
        left = QWidget()
        # An estimate on an end of its search box is no number: the words stand on a line
        # of their own above the bound the data do set, which keeps the number by its unit.
        qualifier = C.label(block.qualifier, 'title', 'secondary')
        qualifier.setVisible(bool(block.qualifier))
        value = C.copyable(C.label(block.value, 'metric'))
        unit_font = font('title')
        unit_font.setWeight(QFont.Weight.Normal)
        unit = C.label(block.unit, 'title', 'secondary')
        unit.setFont(unit_font)
        interval = C.copyable(C.label(block.interval, 'number'))
        level = C.label(block.level, 'number', 'secondary')
        for widget in (level, interval):
            widget.setToolTip(block.tooltip)
        # 'Not limited by the data' leaves no number, and a unit with none would stand alone.
        value.setVisible(bool(block.value))
        unit.setVisible(bool(block.value))
        value_row = C.hbox(value, unit, None, spacing=2)
        value_row.setAlignment(value, Qt.AlignmentFlag.AlignBottom)
        value_row.setAlignment(unit, Qt.AlignmentFlag.AlignBottom)
        left.setLayout(
            C.vbox(
                C.hbox(C.label(block.name, 'label', 'secondary', rich=True), C.badge(reading, tone), None, spacing=3),
                qualifier,
                value_row,
                C.hbox(level, interval, None, spacing=3),
                None,
                spacing=2,
            )
        )
        right = C.vbox(spacing=2)
        if link is not None:
            right.addLayout(C.hbox(None, link))
        if block.rows:
            chart = C.IntervalChart(t, block.rows, block.lo, block.hi, block.ticks, block.axis_unit)
            chart.setToolTip(block.chart_tooltip)
            chart.setAccessibleName(f'Interval chart of {block.plain_name}')
            right.addWidget(chart)
        right.addStretch(1)
        row = C.hbox(left, right, spacing=7)
        row.setStretch(1, 1)
        return row, left

    def _refresh_callouts(self, specs: list[R.CalloutSpec]) -> None:
        _clear(self.callout_box)
        self.callouts = list(specs)
        for spec in specs:
            callout = C.Callout(self.t, spec.tone, spec.title, spec.body, spec.action or None)
            if spec.place is not None:
                callout.action.clicked.connect(lambda _=False, place=spec.place: self.reveal_requested.emit(place))
            self.callout_box.addWidget(callout)
        self.callout_host.setVisible(bool(specs))

    # ------------------------------------------------------------------
    # Fit details
    # ------------------------------------------------------------------

    def _refresh_side(self, fit, note: str | None, empty) -> None:
        self.sections.setVisible(fit is not None)
        self.no_fit_box.setVisible(fit is None)
        if fit is None:
            self.no_fit.setText(f'The last fit is not shown. {note}' if note else f'{empty.title}.')
            return
        ms = self.model.measurement_set
        # Fit quality
        q = R.quality(fit, ms)
        self.r2.setText(q.r2)
        self.rmse.setText(q.rmse)
        self.used.setText(q.used)
        self.used_note.setText(q.used_note)
        self.used_note.setVisible(bool(q.used_note))
        self.used_note.setToolTip(f'Left out by the fit: {q.left_out}' if q.left_out else '')
        self.noise_stat.setVisible(q.noise is not None)
        self.noise.setText(q.noise or '')
        self.noise_note.setText(q.noise_note)
        self.noise_note.setVisible(bool(q.noise_note))
        self.noise_stat.setToolTip(q.noise_tooltip)
        # The replicates' own fits
        _clear(self.replicate_box)
        headers, rows, tips = R.replicate_rows(fit, ms)
        self.replicates_section.setVisible(bool(rows))
        if rows:
            columns = [(headers[0], 'body', None), *((h, 'number', None) for h in headers[1:-1])]
            # A column per binding constant and the p-value: the narrow gap keeps them inside the panel.
            table = C.Table(self.t, [*columns, (headers[-1], 'small-number', 'secondary')], gap=2)
            table.set_rows(rows)
            for i, tip in enumerate(tips):
                for cell in range(len(headers)):
                    table.cell(i, cell).setToolTip(tip)
            self.replicate_box.addWidget(table)
            self.replicates_table = table
        # Diagnostics: each test with its mark and p-value, its full sentence on hover.
        _clear(self.test_box)
        for test in R.test_rows(fit):
            self.test_box.addWidget(C.test_line(self.t, test.icon, test.tone, test.text, test.p, test.tooltip))
        # Parameters
        cells, tips, footnote = R.parameter_rows(fit)
        self.parameters.set_rows(cells)
        for i, tip in enumerate(tips):
            if tip:
                self.parameters.cell(i, 0).setToolTip(tip)
        _clear(self.parameter_notes)
        for text in ([footnote] if footnote else []) + R.parameter_notes(fit):
            self.parameter_notes.addWidget(C.copyable(C.wrapped(text, 'small', 'tertiary')))
        # Input shifts
        _clear(self.shift_grid)
        shifts = R.shift_rows(fit)
        self.shift_note.setText(R.shifts_footnote(shifts))
        for i, shift in enumerate(shifts):
            # A shared source's name is the user's own, often one word: shown whole at any panel width.
            name = C.BreakingLabel(shift.name, 'body')
            name.setMinimumHeight(SIZE['control'])
            if shift.note:
                # A range has no σ to draw a bar in: where the fit left the input is said under its name.
                named = QWidget()
                named.setLayout(
                    C.vbox(name, C.wrapped(shift.note, 'small', 'secondary'), spacing=0, margins=(0, 0, 0, 2))
                )
                name = named
            bar = C.ShiftBar(self.t, shift.z)
            bar.setToolTip(shift.tooltip)
            bar.setAccessibleName(f'Shift of {shift.name}: {shift.percent}, {shift.tooltip}')
            value = C.copyable(C.label(shift.percent, 'number'))
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            value.setToolTip(shift.tooltip)
            self.shift_grid.addWidget(name, i, 0)
            self.shift_grid.addWidget(bar, i, 1)
            self.shift_grid.addWidget(value, i, 2)
