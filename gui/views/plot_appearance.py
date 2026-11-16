"""Plot appearance: how the session's titration plot is drawn, beside the plot itself (DESIGN.md §8).

Canvas: a sentence on what the appearance styles, then the **Titration** plot as Fit
results draws it — the fit where there is one, else the data — with its legend and the
image export; with nothing loaded, a sentence saying what to load. Side panel *Titration
plot*, headed by *Reset to defaults*: Markers (the replicates' and the mean's point size,
the replicates' mark), Lines (the fitted curve and the error bars), Colour (the
replicates, from a short menu of the theme's colours), Text (the plot text of every plot of
the session, Simulation's included) and New
sessions (*Use for new sessions* and what new sessions start from). Every choice goes to the session model's
:class:`~gui.plot_appearance.PlotAppearance` and redraws the plot at once. The appearance
feeds no fit or analysis, so the form stays open while one runs.
"""

from __future__ import annotations

from dataclasses import replace
from html import escape

from PyQt6.QtCore import QObject, Qt
from PyQt6.QtWidgets import QLayout, QWidget

from core.assays.registry import AssayType
from gui import preferences
from gui import results as R
from gui.design import components as C
from gui.design.appearance import appearance, theme
from gui.plot_appearance import BUILT_IN, PlotAppearance, badge, menu
from gui.session_model import Change, SessionModel
from gui.views.titration import TitrationPlot, legend_marks

#: What the canvas says the appearance styles.
SCOPE = (
    'These settings style this session’s titration plot in Measurements and Fit results, and the figure saved '
    'from it. The text size applies to every plot of the session — Simulation, Ka confidence and Sensitivity too — and to '
    'the figures saved from them. Saved figures use the light theme on white.'
)

#: The segmented choices of the form: (section, ((field, caption, accessible name), …)).
_SEGMENTED = (
    (
        'Markers',
        (
            ('replicate_size', 'Replicate points', 'Size of the replicate points'),
            ('mean_size', 'Mean points', 'Size of the mean points'),
            ('replicate_shape', 'Replicate mark', 'Mark of the replicate points'),
        ),
    ),
    (
        'Lines',
        (
            ('fit_width', 'Fitted curve', 'Width of the fitted curve'),
            ('error_bar_width', 'Error bars', 'Width of the error bars'),
        ),
    ),
)


def _widget(layout: QLayout) -> QWidget:
    w = QWidget()
    w.setLayout(layout)
    return w


class PlotAppearanceView(QObject):
    """The canvas and side panel of Plot appearance over *model*; *parent* is where its menus open.

    :attr:`reset` is the side panel's *Reset to defaults* link.
    """

    def __init__(self, model: SessionModel, parent: QWidget):
        super().__init__(parent)
        self.model, self.parent, self.t = model, parent, theme()
        self.canvas = self._build_canvas()
        self.side = self._build_side()
        model.changed.connect(self._on_changed)
        appearance().changed.connect(self._show_form)
        self._show_plot_appearance()

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    def _build_canvas(self) -> QWidget:
        t = self.t
        w = QWidget()
        w.setObjectName('Canvas')
        w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.empty_state = C.EmptyState(t)
        self.legend = C.LegendRow(t, [])
        self.save_plot = C.tool_button(t, None, 'image')
        self.save_plot.setToolTip('Save the plot as an image')
        self.save_plot.setAccessibleName('Save the titration plot as an image')
        self.plot = TitrationPlot()
        self.header = C.PlotHeader(t, 'Titration', self.legend, [self.plot.navigation.tool, 1, self.save_plot])
        lay = C.vbox(
            C.wrapped(SCOPE, 'body', 'secondary'),
            5,
            self.empty_state,
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
        self.choices: dict[str, C.Segmented | C.Dropdown] = {}

        def field(caption: str, control: QWidget) -> QLayout:
            return C.vbox(C.label(caption, 'label', 'secondary'), control, spacing=2)

        def body(*fields: QLayout) -> QWidget:
            items: list = []
            for i, f in enumerate(fields):
                items += [4, f] if i else [f]
            return _widget(C.vbox(*items, spacing=0))

        sections = []
        for title, rows in _SEGMENTED:
            fields = []
            for name, caption, accessible in rows:
                labels = [label for label, *_ in menu(name).values()]
                control = C.Segmented(t, labels)
                control.setAccessibleName(accessible)
                control.changed.connect(lambda i, name=name: self._choose(name, i))
                self.choices[name] = control
                fields.append(field(caption, control))
            sections.append(C.section(t, title, body(*fields), first=not sections))
        # The colours, each a menu with each colour's swatch beside its name — the first three
        # replicates' for By replicate. The means and the error bars keep their own colour (DESIGN.md §7).
        colours = []
        for name, caption, accessible in (
            ('replicate_colour', 'Replicate points', 'Colour of the replicate points'),
            ('fit_colour', 'Fitted curve', 'Colour of the fitted curve'),
        ):
            control = C.Dropdown(t)
            control.setAccessibleName(accessible)
            control.chosen.connect(lambda i, name=name: self._choose(name, i))
            self.choices[name] = control
            colours.append(C.vbox(C.label(caption, 'label', 'secondary'), C.hbox(control, None), spacing=2))
        sections.append(C.section(t, 'Colour', body(*colours)))
        text = C.Segmented(t, [label for label, *_ in menu('text_size').values()])
        text.setAccessibleName('Size of the text of every plot')
        text.changed.connect(lambda i: self._choose('text_size', i))
        self.choices['text_size'] = text
        sections.append(C.section(t, 'Text', body(field('Plot text', text))))
        # New sessions
        self.use_for_new = C.OutlineButton(t, 'Use for new sessions')
        self.use_for_new.setToolTip('Start every new session with this appearance')
        self.use_for_new.clicked.connect(self._use_for_new_sessions)
        sections.append(C.section(t, 'New sessions', _widget(C.hbox(self.use_for_new, None))))
        self.reset = C.link_button('Reset to defaults')
        self.reset.setToolTip('Draw this session’s plot with the built-in appearance')
        self.reset.clicked.connect(lambda: self.model.set_plot_appearance(BUILT_IN))
        return _widget(C.vbox(*sections, spacing=0))

    # ------------------------------------------------------------------
    # Editing
    # ------------------------------------------------------------------

    def _choose(self, name: str, index: int) -> None:
        key = list(menu(name))[index]
        self.model.set_plot_appearance(replace(self.model.plot_appearance, **{name: key}))

    def _use_for_new_sessions(self) -> None:
        preferences.set_plot_appearance_default(self.model.plot_appearance)
        self.model.show_status('New sessions start from this plot appearance')
        self.refresh_buttons()

    # ------------------------------------------------------------------
    # Drawing from the model
    # ------------------------------------------------------------------

    def badge(self) -> str:
        """The summary beside the title: whether the plot is drawn as built in."""
        return badge(self.model.plot_appearance)

    def export_image(self, path: str) -> None:
        """Save the titration plot as shown to *path*, PNG or SVG, in the light theme on white: the figure
        Fit results saves."""
        t = self.titration
        self.plot.export_image(path, t.legend, t.description, t.summary)

    def _on_changed(self, what: Change) -> None:
        if Change.APPEARANCE in what:
            self._show_plot_appearance()
        elif what & (Change.DATA | Change.RESULTS | Change.BINDING | Change.DISPLAY):
            self.refresh()

    def _show_plot_appearance(self) -> None:
        look = self.model.plot_appearance
        self.plot.set_plot_appearance(look)
        legend_marks(self.legend, look)
        self._show_form()
        self.refresh()

    def _show_form(self) -> None:
        """Show the appearance's choices in the form, each colour beside its swatch in the theme as it is now."""
        look: PlotAppearance = self.model.plot_appearance
        for name, control in self.choices.items():
            index = list(menu(name)).index(getattr(look, name))
            if isinstance(control, C.Segmented):
                control.set_current(index)
            else:
                options = []
                for label, tokens in menu(name).values():
                    shown = (tokens,) if name == 'fit_colour' else tokens[:3]
                    dots = ''.join(f'<span style="color:{self.t[token]}">●</span>' for token in shown)
                    options.append(f'{dots} {escape(label)}')
                control.set_options(options, index)
        self.refresh_buttons()

    def refresh_buttons(self) -> None:
        """Enable *Use for new sessions* where another appearance is stored, and *Reset* off the built-in one."""
        try:
            stored = preferences.plot_appearance_default()
        except ValueError:
            stored = None
        current = self.model.plot_appearance
        self.use_for_new.setEnabled(stored != current)
        self.reset.setEnabled(current != BUILT_IN)

    def refresh(self) -> None:
        model = self.model
        shown = model.fit_results
        assay_type = AssayType[shown[-1].assay_type] if shown else model.settings.assay_type
        titration = R.titration(model.measurement_set, shown, assay_type, model.settings.replicate_display)
        self.titration = titration
        empty = model.empty_view('Plot appearance')
        self.empty_state.show_empty(empty)
        has_plot = empty is None
        self.plot.show_data(titration.data, model.settings.display_unit)
        self.legend.set_items(titration.legend)
        self.header.set_description(titration.description)
        # With no plot, the empty state takes its room.
        self.header.setVisible(has_plot)
        self.plot.setVisible(has_plot)
