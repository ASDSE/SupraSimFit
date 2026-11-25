"""Main plot widget wrapping a PyQtGraph PlotWidget."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from core.units import Q_
from gui.plotting.colors import (
    AVERAGE_LINE_COLOR,
    BACKGROUND_COLOR,
    DROPPED_REPLICA_COLOR,
    ERROR_BAR_COLOR,
    FIT_PALETTE,
    FOREGROUND_COLOR,
    INK_2,
    NOTE_SURFACE,
    PALETTES,
    REPLICA_PALETTE,
    rgba,
)
from gui.plotting.labels import (
    SHIFTED_CURVE_NOTE,
    _format_exponent_unicode,
    fmt_estimate,
    fmt_interval_html,
    fmt_param,
    fmt_r2,
    fmt_unit_html,
    fmt_value,
)
from gui.plotting.plot_style import DEFAULT_STYLE, line_style_to_qt
from gui.widgets.replica_panel import _display_label, describe_replicates

# Overlay auto-placement (legend + fit-summary annotation). PyQtGraph has no
# equivalent of matplotlib's legend loc='best' — upstream issue #2769 asking for
# one is still open — so the candidate-and-score search lives here.
_OVERLAY_PAD_PX = 8
#: Candidate slots as (x, y) fractions of the free space inside the ViewBox,
#: in preference order: ties fall to the conventional top-right.
_OVERLAY_SLOTS: tuple[tuple[float, float], ...] = (
    (1.0, 0.0),
    (0.0, 0.0),
    (1.0, 1.0),
    (0.0, 1.0),
    (0.5, 0.0),
    (0.5, 1.0),
)
#: Overlapping another overlay costs more than covering any plausible number
#: of data points, so a slot that collides is only chosen as a last resort.
_BLOCKED_PENALTY = 10_000


class _DraggableTextItem(pg.TextItem):
    """A ``TextItem`` that reports where the user dropped it.

    ``pg.TextItem`` has no "moved" signal, so the drop is captured here and
    handed to *on_moved*. Only a position change reports: a click that moves
    nothing leaves auto-placement in charge, and a programmatic ``setPos``
    never routes through these handlers at all.
    """

    def __init__(self, *args, on_moved: Callable[[QPointF], None] | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._on_moved = on_moved
        self._press_pos: QPointF | None = None

    def mousePressEvent(self, ev) -> None:
        super().mousePressEvent(ev)
        self._press_pos = self.pos()

    def mouseReleaseEvent(self, ev) -> None:
        super().mouseReleaseEvent(ev)
        self._report_if_moved()

    def _report_if_moved(self) -> None:
        """Hand the drop position to *on_moved*, but only after a real move.

        A press whose position was never recorded reports nothing: leaving
        auto-placement running is recoverable (the user can drag again),
        whereas latching a position the user never chose is not.
        """
        start, self._press_pos = self._press_pos, None
        if self._on_moved is not None and start is not None and self.pos() != start:
            self._on_moved(self.pos())


_X_UNIT_SCALES: dict[str, float] = {label: float(Q_(1, label).to('M').magnitude) for label in ('nM', 'µM', 'mM', 'M')}
# Invert: we need M→display, i.e. multiply M value to get display value
_X_UNIT_SCALES = {k: 1.0 / v for k, v in _X_UNIT_SCALES.items()}


def _x_unit_scale(x_unit: str) -> float:
    """Return the M→display multiplier for an x-axis concentration unit.

    Fast path uses the precomputed table; any other valid concentration unit is
    derived from Pint. An unknown/invalid token raises instead of silently
    falling back to a fixed scale (which would mis-scale the axis while the
    label showed a different unit).
    """
    scale = _X_UNIT_SCALES.get(x_unit)
    if scale is not None:
        return scale
    try:
        return 1.0 / float(Q_(1, x_unit).to('M').magnitude)
    except Exception as err:
        raise ValueError(
            f'Invalid x-axis concentration unit {x_unit!r} in plot style; expected e.g. nM, µM, mM, M.'
        ) from err


def _replica_order(plot_data: dict[str, Any]) -> tuple[str, ...]:
    """Every replicate id in the data's order, which fixes each replicate's label and colour.

    ``all_replica_ids`` when the data carries it (``prepare_plot_data`` always
    does); otherwise the order the replicates are listed in.
    """
    listed = plot_data.get('all_replica_ids')
    if listed:
        return tuple(str(rid) for rid in listed)
    groups = ('active_replicas', 'left_out_replicas', 'dropped_replicas')
    return tuple(str(rid) for group in groups for rid, _ in plot_data.get(group, []))


def _without_fit(plot_data: dict[str, Any]) -> dict[str, Any]:
    """*plot_data* as drawn with no fit: left-out replicates rejoin the active ones and the mean covers them all."""
    left_out = plot_data.get('left_out_replicas', [])
    if not left_out:
        return {**plot_data, 'fits': []}
    order = _replica_order(plot_data)
    active = sorted([*plot_data.get('active_replicas', []), *left_out], key=lambda pair: order.index(str(pair[0])))
    average = np.stack([np.asarray(sig) for _, sig in active]).mean(axis=0)
    return {**plot_data, 'active_replicas': active, 'left_out_replicas': [], 'average': average, 'fits': []}


def _differing_replicates_note(fits: list[dict[str, Any]], order: tuple[str, ...]) -> str | None:
    """A plain note when overlaid fits used different replicates, naming each set; otherwise None.

    The mean and SD follow the last fit, the one the summary panel reports.
    """
    if len(fits) < 2 or any('replica_ids' not in fit for fit in fits):
        return None
    reported = fits[-1]['replica_ids']
    others = [fit['replica_ids'] for fit in fits[:-1] if set(fit['replica_ids']) != set(reported)]
    if not others:
        return None
    other_names = '; '.join(describe_replicates(ids, order) for ids in others)
    return (
        f'Mean \u00b1 SD is over {describe_replicates(reported, order)}, the ones the fit in the summary used. '
        f'{"Another fit" if len(others) == 1 else "Other fits"} shown used {other_names}.'
    )


class _ErrorBarSample(pg.ItemSample):
    """Legend sample that renders an error-bar glyph instead of a line.

    pyqtgraph's default :class:`ItemSample` only knows how to paint
    curves, scatter markers, and bar graphs. Passing a plain
    ``PlotCurveItem`` for the error-bar legend entry therefore draws a
    plain horizontal line, which is visually indistinguishable from the
    mean line. Subclassing and overriding ``paint`` lets us draw a
    ``┬ ┴`` glyph (vertical stem with two caps) that matches the on-plot
    error bars.
    """

    _WIDTH = 20
    _HEIGHT = 20

    def paint(self, p, *args):  # type: ignore[override]
        pen = self.item.opts.get('pen') if hasattr(self.item, 'opts') else None
        if pen is None:
            return
        p.setPen(pen)
        # Vertical stem
        p.drawLine(QPointF(10.0, 3.0), QPointF(10.0, 17.0))
        # Top cap
        p.drawLine(QPointF(5.0, 3.0), QPointF(15.0, 3.0))
        # Bottom cap
        p.drawLine(QPointF(5.0, 17.0), QPointF(15.0, 17.0))

    def boundingRect(self):  # type: ignore[override]
        return QRectF(0.0, 0.0, float(self._WIDTH), float(self._HEIGHT))


class ScientificAxisItem(pg.AxisItem):
    """AxisItem that formats tick labels with a shared exponent.

    When all tick values share a common order of magnitude (outside the
    [0.01, 10 000] range), the exponent is factored out and stored in
    :attr:`exponent`.  Tick labels then show plain mantissa values (e.g.
    "2", "4", "6") and the caller appends "×10ⁿ" once to the axis label.

    Values in [0.01, 10 000] are displayed as plain numbers with no
    exponent factored out.  SI prefix auto-scaling is disabled.

    One exponent holds for every tick level of a draw, and it is read from the
    major level: pyqtgraph formats each level on its own, and a minor tick past
    10 000 under major ticks that end at 10 000 would otherwise set an exponent
    the major labels, written plain, do not carry.

    Parameters
    ----------
    use_exponent : bool
        If ``False``, tick labels are always plain ``:g``-formatted values
        and no exponent is factored out.  Useful for axes where the caller
        already handles unit scaling (e.g. concentration with a user-selected
        unit).
    """

    def __init__(self, *args, use_exponent: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.enableAutoSIPrefix(False)
        self.exponent: int | None = None
        self._use_exponent = use_exponent
        self.on_exponent_changed: Callable[[int | None], None] | None = None
        # The major tick values of the draw in progress, which every level's
        # labels take their exponent from; None until the axis draws ticks of
        # its own choosing.
        self._major_values: list[float] | None = None

    def _set_exponent(self, exp: int | None) -> None:
        """Update exponent, firing callback only on change.

        The callback guard (``exp != self.exponent``) prevents infinite
        recursion: ``setLabel`` → ``update()`` → ``tickStrings`` →
        same exponent → no callback.
        """
        if exp != self.exponent:
            self.exponent = exp
            if self.on_exponent_changed is not None:
                self.on_exponent_changed(exp)

    def tickValues(self, minVal, maxVal, size):
        """The ticks of one draw; the first level holding any is the major one, which sets the exponent."""
        levels = super().tickValues(minVal, maxVal, size)
        self._major_values = next((list(values) for _, values in levels if len(values)), [])
        return levels

    @staticmethod
    def _exponent_of(values, scale) -> int | None:
        """The exponent factored out of *values*: none where the largest lies in [0.01, 10 000] or all are 0."""
        abs_vals = [abs(v * scale) for v in values if v * scale != 0]
        if not abs_vals:
            return None
        max_abs = max(abs_vals)
        if 1e-2 <= max_abs <= 1e4:
            return None
        return int(np.floor(np.log10(max_abs)))

    def tickStrings(self, values, scale, spacing):
        if not values:
            # An empty minor level leaves the major level's exponent standing;
            # an axis with no tick at all has none.
            if not self._major_values:
                self._set_exponent(None)
            return []

        if not self._use_exponent:
            self._set_exponent(None)
            return [f'{v * scale:g}' for v in values]

        # Every level of a draw takes the major level's exponent; values given
        # outside a draw (no major level known) set their own.
        exp = self._exponent_of(self._major_values or values, scale)
        self._set_exponent(exp)
        if exp is None:
            return [f'{v * scale:g}' for v in values]
        divisor = 10**exp
        return ['0' if v * scale == 0 else f'{v * scale / divisor:g}' for v in values]


class PlotWidget(QWidget):
    """Qt widget that renders ``prepare_plot_data()`` output via PyQtGraph.

    Parameters
    ----------
    x_label : str
        Initial x-axis label.
    y_label : str
        Initial y-axis label.
    title : str
        Plot title.
    parent : QWidget, optional
    """

    def __init__(
        self,
        x_label: str = '',
        y_label: str = '',
        title: str = '',
        parent=None,
    ):
        super().__init__(parent)
        axis_items = {
            'bottom': ScientificAxisItem(orientation='bottom'),
            'left': ScientificAxisItem(orientation='left'),
        }
        # Colours and antialiasing are set on this view and on the curves drawn
        # in it, never on pyqtgraph's process-wide defaults: those reach every
        # other plot in the application, so a tab would draw differently
        # depending on whether a Fit Curve tab had been built yet. A curve
        # carries its own antialiasing setting, taken when it is built, and
        # paints by that rather than by the view's, so each says so itself.
        self._pg_widget = pg.PlotWidget(axisItems=axis_items, background=BACKGROUND_COLOR)
        self._pg_widget.setAntialiasing(True)
        self._pg_widget.setTitle(title, color=FOREGROUND_COLOR)
        self._pg_widget.setLabel('bottom', x_label)
        self._pg_widget.setLabel('left', y_label)
        self._legend = self._pg_widget.addLegend(labelTextSize='10pt', labelTextColor=FOREGROUND_COLOR)

        # Style axes: bold pen + tick/label fonts from DEFAULT_STYLE
        _axes_style = DEFAULT_STYLE['axes']
        _tick_font = QFont()
        _tick_font.setPointSize(_axes_style['tick_font_size'])
        _label_font = QFont()
        _label_font.setPointSize(_axes_style['label_font_size'])
        _label_font.setBold(True)
        for axis_name in ('bottom', 'left'):
            ax = self._pg_widget.getAxis(axis_name)
            ax.setPen(pg.mkPen(color='k', width=1.5))
            ax.setTextPen(pg.mkPen('k'))
            ax.setStyle(tickLength=-8, tickFont=_tick_font)
            ax.label.setFont(_label_font)

        # A short plain note above the plot: why a fit is hidden, or that
        # overlaid fits used different replicates.
        self._note = QLabel()
        self._note.setTextFormat(Qt.TextFormat.PlainText)
        self._note.setWordWrap(True)
        self._note.setStyleSheet(f'color: {INK_2}; background: {NOTE_SURFACE}; padding: 4px 8px;')
        self._note.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._note)
        layout.addWidget(self._pg_widget)

        # The ViewBox has no real geometry until it has been laid out and
        # ranged, so a placement computed during update_plot() can be based on
        # a default (0,0)-(1,1) view. Re-place once the range/size is real —
        # the same deferred-paint caveat that ScientificAxisItem works around
        # with its exponent callbacks.
        _vb = self._pg_widget.getViewBox()
        _vb.sigRangeChanged.connect(self._on_view_geometry_changed)
        _vb.sigResized.connect(self._on_view_geometry_changed)

        # Wire exponent callbacks so axis labels update reactively after paint
        left_ax: ScientificAxisItem = self._pg_widget.getAxis('left')
        left_ax.on_exponent_changed = self._on_y_exponent_changed
        bottom_ax: ScientificAxisItem = self._pg_widget.getAxis('bottom')
        bottom_ax.on_exponent_changed = self._on_x_exponent_changed

        self._style: dict = DEFAULT_STYLE

        self._replica_items: list[pg.ScatterPlotItem] = []
        self._dropped_items: list[pg.ScatterPlotItem] = []
        self._left_out_items: list[pg.ScatterPlotItem] = []
        self._average_item: pg.PlotCurveItem | None = None
        self._error_bar_item: pg.ErrorBarItem | None = None
        self._error_cap_items: list[pg.PlotCurveItem] = []
        self._fit_items: list[pg.PlotCurveItem] = []
        self._annotation_item: pg.TextItem | None = None
        # Set only by a user drag (in ViewBox pixels). While None, the
        # annotation re-places itself automatically on every rebuild.
        self._annotation_pos: QPointF | None = None
        self._legend_placed = False

        self._replica_ids: list[str] = []
        self._all_replica_ids: tuple[str, ...] = ()
        self._dropped_replica_ids: list[str] = []
        self._left_out_replica_ids: list[str] = []
        self._fit_labels: list[str] = []
        self._fit_results: list[Any] = []
        # Set by show_mismatch(): while not None the fit is hidden and this note says why.
        self._mismatch_note: str | None = None
        self._replicates_note: str | None = None
        # Set by show_hidden_results(): other results held but not drawn, while the drawn fits stay.
        self._hidden_results_note: str | None = None

        self._last_plot_data: dict[str, Any] = {}
        self._last_error_bar_data: tuple | None = None
        self._last_x_label_base: str | None = None
        self._last_y_label: str | None = None
        self._last_y_unit: str = 'a.u.'

    @property
    def plot_item(self) -> pg.PlotItem:
        """The underlying pyqtgraph PlotItem — used to x-link a second plot to this one."""
        return self._pg_widget.getPlotItem()

    @property
    def x_unit(self) -> str:
        """Current x-axis concentration unit (e.g. ``'µM'``) — for a linked plot to match."""
        return self._style['axes'].get('x_unit', 'µM')

    def update_plot(
        self,
        plot_data: dict[str, Any],
        *,
        x_label: str | None = None,
        y_label: str | None = None,
        y_unit: str | None = None,
        preserve_positions: bool = False,
    ) -> None:
        """Clear and redraw from a ``prepare_plot_data()`` dict.

        Parameters
        ----------
        plot_data : dict
            As returned by ``core.data_processing.plotting.prepare_plot_data()``.
        x_label : str, optional
            Default x-axis name (registry value). Composed with the unit
            from ``style['axes']['x_unit']`` and, if set, the user override
            in ``style['axes']['x_name_override']``.
        y_label : str, optional
            Default y-axis name (registry value).
        y_unit : str, optional
            Y-axis unit suffix (e.g. ``"a.u."``). Auto-managed; not editable
            in the GUI.
        preserve_positions : bool
            If False (the default), forget where the legend and annotation
            were put so both are re-placed against the new data. Set to True
            when the caller is redrawing the *same* data (e.g. an x-axis unit
            rescale) and wants user-dragged positions to survive.

        Notes
        -----
        Each replicate's colour and label come from its position in
        ``all_replica_ids``, so they stay the same whichever replicates are
        active and whether or not a fit is shown. Replicates the fit left out
        are drawn in the dropped style. While :meth:`show_mismatch` hides the
        fit, the data is drawn without it.
        """
        self._last_plot_data = plot_data
        if self._mismatch_note is not None:
            plot_data = _without_fit(plot_data)
        if not preserve_positions:
            self._legend_placed = False
            self._annotation_pos = None
        self._clear_items()

        style = self._style
        x_unit = style['axes'].get('x_unit', 'µM')
        x_scale = _x_unit_scale(x_unit)

        if x_label is not None:
            self._last_x_label_base = x_label
        if y_label is not None:
            self._last_y_label = y_label
        if y_unit is not None:
            self._last_y_unit = y_unit

        x = np.asarray(plot_data.get('concentrations', [])) * x_scale

        # Resolve the active palette
        palette_name = style['data_points'].get('palette', 'Default (Tab10)')
        palette = PALETTES.get(palette_name, REPLICA_PALETTE)

        self._all_replica_ids = _replica_order(plot_data)

        # Active replicas — outlined markers for matplotlib-like look
        active = plot_data.get('active_replicas', [])
        self._replica_ids = []
        if style['visibility']['show_data_points']:
            for rid, sig in active:
                color = palette[self._all_replica_ids.index(str(rid)) % len(palette)]
                item = pg.ScatterPlotItem(
                    x=x,
                    y=np.asarray(sig),
                    symbol=style['data_points']['symbol'],
                    size=style['data_points']['size'],
                    pen=pg.mkPen(color=rgba(color, 220), width=0.8),
                    brush=pg.mkBrush(rgba(color, style['data_points']['alpha'])),
                    name=None,
                )
                self._pg_widget.addItem(item)
                self._replica_items.append(item)
                self._replica_ids.append(str(rid))

        # Replicates the fit left out, then inactive ones, in the dropped style:
        # individual items so each gets its own legend entry.
        self._left_out_items, self._left_out_replica_ids = self._add_greyed(x, plot_data.get('left_out_replicas', []))
        self._dropped_items, self._dropped_replica_ids = self._add_greyed(x, plot_data.get('dropped_replicas', []))

        # Average line + error bars — always create items when data permits so
        # that apply_style() can toggle visibility without requiring a full redraw.
        avg = plot_data.get('average')
        if avg is not None and len(active) > 0:
            avg_arr = np.asarray(avg)
            show_avg = style['visibility']['show_average']
            avg_color = style['average_line'].get('color', AVERAGE_LINE_COLOR)
            pen = pg.mkPen(
                color=avg_color,
                width=style['average_line']['width'],
                style=line_style_to_qt(style['average_line']['style']),
            )
            self._average_item = pg.PlotCurveItem(x=x, y=avg_arr, pen=pen, name=None, antialias=True)
            self._average_item.setVisible(show_avg)
            self._pg_widget.addItem(self._average_item)

            if len(active) > 1:
                signals = np.stack([np.asarray(sig) for _, sig in active])
                std = signals.std(axis=0)
                eb_color = style['error_bars'].get('color', ERROR_BAR_COLOR)
                eb_width = style['error_bars'].get('width', 1)
                show_eb = style['visibility']['show_error_bars']
                self._error_bar_item = pg.ErrorBarItem(
                    x=x,
                    y=avg_arr,
                    height=2 * std,
                    pen=pg.mkPen(color=eb_color, width=eb_width),
                )
                self._pg_widget.addItem(self._error_bar_item)
                cap_size = style['error_bars'].get('cap_size', 5)
                if show_eb:
                    if cap_size > 0:
                        self._draw_error_caps(x, avg_arr, std, eb_color, eb_width, cap_size)
                else:
                    # Hide by setting empty data (ErrorBarItem doesn't support setVisible reliably)
                    self._error_bar_item.setData(x=np.array([]), y=np.array([]), height=np.array([]))
                self._last_error_bar_data = (x, avg_arr, std)

        # Fit curves
        fits = plot_data.get('fits', [])
        self._replicates_note = _differing_replicates_note(fits, self._all_replica_ids)
        self._fit_labels = []
        if style['visibility']['show_fit']:
            for i, fit in enumerate(fits):
                color = style['fit_curves'].get('color', FIT_PALETTE[i % len(FIT_PALETTE)])
                pen = pg.mkPen(
                    color=color,
                    width=style['fit_curves']['width'],
                    style=line_style_to_qt(style['fit_curves']['style']),
                )
                item = pg.PlotCurveItem(
                    x=np.asarray(fit['x']) * x_scale,
                    y=np.asarray(fit['y']),
                    pen=pen,
                    name=None,
                    antialias=True,
                )
                self._pg_widget.addItem(item)
                self._fit_items.append(item)
                self._fit_labels.append(fit.get('label', f'fit {i}'))

        # Auto-range first so overlay placement scores against the new view
        # rect; otherwise it would score the previous data range and drop the
        # legend or annotation onto the data.
        self._pg_widget.getViewBox().autoRange()
        self._rebuild_legend()
        self._rebuild_annotation()
        self._update_axis_labels_with_exponents()
        self._sync_note()

    def _sync_note(self) -> None:
        """Put the note above the plot: why the fit is hidden, or else what to know about the fits drawn."""
        if self._mismatch_note is not None:
            note = self._mismatch_note
        else:
            note = ' '.join(text for text in (self._replicates_note, self._hidden_results_note) if text)
        self._note.setText(note)
        self._note.setVisible(bool(note))

    def show_hidden_results(self, note: str | None) -> None:
        """Say above the plot that other results are held but not drawn; ``None`` removes the note.

        The fits drawn stay as they are. A note from :meth:`show_mismatch`
        takes its place while every fit is hidden.
        """
        self._hidden_results_note = note
        self._sync_note()

    def show_mismatch(self, note: str | None) -> None:
        """Hide the fit while it does not match the loaded data, or show it again with ``None``.

        With a *note*, the plot shows the data with no fit curve and no
        annotation: replicates the fit left out are drawn as ordinary points,
        Mean ± SD covers every replicate drawn as active, and *note* sits above
        the plot saying why. The widget stays so through later
        :meth:`update_plot`, :meth:`set_fit_results` and style changes, so a
        hidden fit is never drawn by accident. ``None`` shows the last data and
        fit results given, exactly as before they were hidden.

        Parameters
        ----------
        note : str or None
            Short plain text naming what differs from the fit's record, or
            ``None`` when the fit matches the loaded data.
        """
        self._mismatch_note = note
        self._redraw()

    def _redraw(self) -> None:
        """Redraw the last plot data and fit results, keeping the legend and annotation where they are."""
        results = self._fit_results
        self.update_plot(self._last_plot_data, preserve_positions=True)
        self.set_fit_results(results)

    def apply_style(self, style: dict) -> None:
        """Mutate existing plot items in-place with new style settings.

        Wired to ``PlotStyleWidget.style_changed``.

        Parameters
        ----------
        style : dict
            Full style dict as returned by ``PlotStyleWidget.current_style()``.
        """
        old_x_unit = self._style['axes'].get('x_unit', 'µM')
        new_x_unit = style['axes'].get('x_unit', 'µM')
        if old_x_unit != new_x_unit and self._last_plot_data:
            # x-unit change requires rescaling all data — do a full redraw
            # but keep legend/annotation exactly where the user left them.
            self._style = style
            self._redraw()
            return

        self._style = style

        # Resolve palette
        palette_name = style['data_points'].get('palette', 'Default (Tab10)')
        palette = PALETTES.get(palette_name, REPLICA_PALETTE)

        dp = style['data_points']
        for item, rid in zip(self._replica_items, self._replica_ids):
            color = palette[self._all_replica_ids.index(rid) % len(palette)]
            item.setSymbol(dp['symbol'])
            item.setSize(dp['size'])
            item.setPen(pg.mkPen(color=rgba(color, 220), width=0.8))
            item.setBrush(pg.mkBrush(rgba(color, dp['alpha'])))
            item.setVisible(style['visibility']['show_data_points'])

        dr = style['dropped_replicas']
        for item in [*self._left_out_items, *self._dropped_items]:
            item.setSymbol(dr['symbol'])
            item.setSize(dr['size'])
            item.setBrush(pg.mkBrush(rgba(DROPPED_REPLICA_COLOR, dr['alpha'])))
            item.setVisible(style['visibility']['show_dropped'])

        al = style['average_line']
        if self._average_item is not None:
            avg_color = al.get('color', AVERAGE_LINE_COLOR)
            pen = pg.mkPen(
                color=avg_color,
                width=al['width'],
                style=line_style_to_qt(al['style']),
            )
            # Reset opts['pen'] directly before setPen: pyqtgraph short-circuits
            # ``setPen`` when the stored pen compares equal, which happens when a
            # QColor is mutated in-place by the ParameterTree color picker.
            self._average_item.opts['pen'] = None
            self._average_item.setPen(pen)
            self._average_item.update()
            self._average_item.setVisible(style['visibility']['show_average'])

        # Error bars: use setData with empty arrays to reliably hide/show
        if self._error_bar_item is not None:
            visible = style['visibility']['show_error_bars']
            eb_color = style['error_bars'].get('color', ERROR_BAR_COLOR)
            eb_width = style['error_bars'].get('width', 1)

            # Remove existing caps
            for cap in self._error_cap_items:
                self._pg_widget.removeItem(cap)
            self._error_cap_items.clear()

            if visible and self._last_error_bar_data is not None:
                x_eb, avg_eb, std_eb = self._last_error_bar_data
                self._error_bar_item.setData(
                    x=x_eb,
                    y=avg_eb,
                    height=2 * std_eb,
                    pen=pg.mkPen(color=eb_color, width=eb_width),
                )
                cap_size = style['error_bars'].get('cap_size', 5)
                if cap_size > 0:
                    self._draw_error_caps(x_eb, avg_eb, std_eb, eb_color, eb_width, cap_size)
            else:
                # Clear by setting empty data
                self._error_bar_item.setData(x=np.array([]), y=np.array([]), height=np.array([]))

        fc = style['fit_curves']
        for i, item in enumerate(self._fit_items):
            color = fc.get('color', FIT_PALETTE[i % len(FIT_PALETTE)])
            item.setPen(
                pg.mkPen(
                    color=color,
                    width=fc['width'],
                    style=line_style_to_qt(fc['style']),
                )
            )
            item.setVisible(style['visibility']['show_fit'])

        self._legend.setLabelTextSize(f'{style["legend"]["font_size"]}pt')

        # Apply axis font sizes
        axes_style = style.get('axes', DEFAULT_STYLE['axes'])
        _tick_font = QFont()
        _tick_font.setPointSize(axes_style['tick_font_size'])
        _label_font = QFont()
        _label_font.setPointSize(axes_style['label_font_size'])
        _label_font.setBold(True)
        for axis_name in ('bottom', 'left'):
            ax = self._pg_widget.getAxis(axis_name)
            ax.setStyle(tickFont=_tick_font)
            ax.label.setFont(_label_font)

        self._rebuild_legend()
        self._rebuild_annotation()
        self._update_axis_labels_with_exponents()

    def set_axis_labels(self, x_label: str, y_label: str, y_unit: str | None = None) -> None:
        """Update default axis names (and optionally the y-unit).

        The current overrides in ``style['axes']`` still take precedence;
        defaults are only used when an override is empty.

        Parameters
        ----------
        x_label : str
            Default x-axis name.
        y_label : str
            Default y-axis name.
        y_unit : str, optional
            Y-axis unit suffix. If ``None``, the previous value is kept.
        """
        self._last_x_label_base = x_label
        self._last_y_label = y_label
        if y_unit is not None:
            self._last_y_unit = y_unit
        self._update_axis_labels_with_exponents()

    def set_fit_results(self, results: list[Any]) -> None:
        """Store FitResult objects used to populate the annotation.

        Call this after ``update_plot()`` whenever fit results are available.
        Pass an empty list to clear the annotation.

        Parameters
        ----------
        results : list[FitResult]
            One entry per fit curve shown in the plot.
        """
        self._fit_results = list(results)
        self._rebuild_annotation()

    def export_image(self, path: str, width_px: int = 2100) -> None:
        """Export the current plot to a PNG or SVG file.

        Parameters
        ----------
        path : str
            Output file path. Extension determines format: ``.png`` →
            rasterised PNG, ``.svg`` → vector SVG.
        width_px : int
            Output width in pixels for PNG (default 2100, ~7 in @ 300
            DPI). Height is derived from the plot's aspect ratio.
            Ignored for SVG output.

        Raises
        ------
        ValueError
            If the file extension is not ``.png`` or ``.svg``.
        """
        from gui.plotting.export import export_plot_item

        export_plot_item(self._pg_widget.getPlotItem(), path, width_px=width_px)

    def _set_axis_label(self, axis: str, base_label: str, exp: int | None) -> None:
        """Set an axis label, appending ×10ⁿ if *exp* is not None."""
        if exp is not None:
            exp_str = _format_exponent_unicode(exp)
            self._pg_widget.setLabel(axis, f'{base_label}  (×10{exp_str})')
        else:
            self._pg_widget.setLabel(axis, base_label)

    def _compose_axis_label(self, default_name: str, override: str, unit: str) -> str:
        """Compose ``"<name> [<unit>]"`` using *override* if non-empty.

        The override is stripped before testing for emptiness so whitespace-
        only values revert to the default.
        """
        name = override.strip() if override else ''
        if not name:
            name = default_name
        if unit:
            return f'{name} [{unit}]'
        return name

    def _on_y_exponent_changed(self, exp: int | None) -> None:
        """Update y-axis label reactively when the exponent changes during paint."""
        override = self._style['axes'].get('y_name_override', '') or ''
        label = self._compose_axis_label(
            self._last_y_label or '',
            override,
            self._last_y_unit,
        )
        self._set_axis_label('left', label, exp)

    def _on_x_exponent_changed(self, exp: int | None) -> None:
        """Update x-axis label reactively when the exponent changes during paint."""
        x_unit = self._style['axes'].get('x_unit', 'µM')
        override = self._style['axes'].get('x_name_override', '') or ''
        label = self._compose_axis_label(
            self._last_x_label_base or '',
            override,
            x_unit,
        )
        self._set_axis_label('bottom', label, exp)

    def _update_axis_labels_with_exponents(self) -> None:
        """Set axis labels with exponent suffix if known.

        Exponents may be stale on the first call (before the initial
        paint); the ``on_exponent_changed`` callbacks on each
        :class:`ScientificAxisItem` correct them reactively once
        ``tickStrings`` runs during paint.
        """
        self._on_y_exponent_changed(self._pg_widget.getAxis('left').exponent)
        self._on_x_exponent_changed(self._pg_widget.getAxis('bottom').exponent)

    def _draw_error_caps(
        self,
        x: np.ndarray,
        avg: np.ndarray,
        std: np.ndarray,
        color,
        width: int,
        cap_size: int,
    ) -> None:
        """Draw horizontal cap lines at ±1σ above/below error bars.

        Cap width is computed as a fraction of the x data span, so caps
        remain sensible regardless of when this is called relative to
        the view auto-range.  ``cap_size`` acts as a percentage-like scale
        (default 5 → ~2.5% of the x span per side).
        """
        if len(x) == 0:
            return
        x_min, x_max = float(x.min()), float(x.max())
        x_span = x_max - x_min if x_max != x_min else (abs(x_min) or 1.0)
        cap_half = x_span * cap_size / 200.0

        pen = pg.mkPen(color=color, width=width)
        for xi, yi, si in zip(x, avg, std):
            for sign in (+1, -1):
                cap_y = yi + sign * si
                cap_item = pg.PlotCurveItem(
                    x=[xi - cap_half, xi + cap_half],
                    y=[cap_y, cap_y],
                    pen=pen,
                    antialias=True,
                )
                self._pg_widget.addItem(cap_item)
                self._error_cap_items.append(cap_item)

    def _rebuild_legend(self) -> None:
        """Rebuild legend entries from current style and stored item metadata.

        Legend entries are only added when the corresponding item is both
        configured to appear in the legend AND is currently visible.
        The legend is placed in the least-occupied corner of the plot.
        """
        leg = self._style['legend']
        vis = self._style['visibility']
        self._legend.clear()
        entry_count = 0
        if leg['show_replicas'] and vis['show_data_points']:
            for item, rid in zip(self._replica_items, self._replica_ids):
                self._legend.addItem(item, _display_label(self._all_replica_ids.index(rid)))
                entry_count += 1
        if leg.get('show_dropped', True) and vis['show_dropped']:
            greyed = (
                (self._left_out_items, self._left_out_replica_ids, 'left out of fit'),
                (self._dropped_items, self._dropped_replica_ids, 'dropped'),
            )
            for items, ids, reason in greyed:
                for item, rid in zip(items, ids):
                    self._legend.addItem(item, f'{_display_label(self._all_replica_ids.index(rid))} ({reason})')
                    entry_count += 1
        if leg['show_average'] and vis['show_average'] and self._average_item is not None:
            self._legend.addItem(self._average_item, 'Mean')
            entry_count += 1
        if leg.get('show_error_bars', True) and vis['show_error_bars'] and self._error_bar_item is not None:
            # Custom sample draws a ┬ ┴ glyph so the legend entry is
            # visually distinct from the average line.
            eb_color = self._style['error_bars'].get('color', ERROR_BAR_COLOR)
            eb_pen = pg.mkPen(color=eb_color, width=self._style['error_bars'].get('width', 1))
            eb_stub = pg.PlotCurveItem(pen=eb_pen, antialias=True)
            self._legend.addItem(_ErrorBarSample(eb_stub), 'Mean \u00b1 SD')
            entry_count += 1
        if leg['show_fit'] and vis['show_fit']:
            for item, label in zip(self._fit_items, self._fit_labels):
                self._legend.addItem(item, label)
                entry_count += 1

        # Background brush — applied on every rebuild so the colour
        # picker updates live. Falls back to the legacy inline default.
        bg = self._style['legend'].get('background_color', (255, 255, 255, 200))
        brush = pg.mkBrush(color=tuple(bg))
        if hasattr(self._legend, 'setBrush'):
            self._legend.setBrush(brush)
        else:
            self._legend.opts['brush'] = brush
            self._legend.update()

        # Position the legend once per data load. On later rebuilds (style
        # changes, x-unit rescales, visibility toggles) leave the anchor
        # alone: pyqtgraph's GraphicsWidgetAnchor already tracks the
        # legend's current position, including any user drag, so
        # touching it would clobber those.
        if entry_count == 0:
            self._legend_placed = False
        elif not self._legend_placed:
            rect = self._legend.boundingRect()
            slot = self._best_overlay_slot((rect.width(), rect.height()))
            if slot is not None:
                (fx, fy), _ = slot
                # Anchoring (rather than setPos) keeps the legend pinned to the
                # same relative corner when the widget is resized.
                pad = _OVERLAY_PAD_PX
                self._legend.anchor(
                    itemPos=(fx, fy),
                    parentPos=(fx, fy),
                    offset=(pad * (1 - 2 * fx), pad * (1 - 2 * fy)),
                )
                self._legend_placed = True

    def _clear_items(self) -> None:
        """Remove all data items and reset the legend."""
        if self._annotation_item is not None:
            scene = self._annotation_item.scene()
            if scene is not None:
                scene.removeItem(self._annotation_item)
        all_items = [
            self._average_item,
            self._error_bar_item,
            *self._replica_items,
            *self._fit_items,
            *self._error_cap_items,
            *self._dropped_items,
            *self._left_out_items,
        ]
        for item in all_items:
            if item is not None:
                self._pg_widget.removeItem(item)

        self._replica_items = []
        self._dropped_items = []
        self._left_out_items = []
        self._average_item = None
        self._error_bar_item = None
        self._error_cap_items = []
        self._fit_items = []
        self._annotation_item = None
        self._last_error_bar_data = None

        self._replica_ids = []
        self._dropped_replica_ids = []
        self._left_out_replica_ids = []
        self._fit_labels = []
        self._fit_results = []

        plot_item = self._pg_widget.getPlotItem()
        if plot_item.legend is not None:
            plot_item.legend.clear()

    def _add_greyed(self, x: np.ndarray, replicas: list) -> tuple[list[pg.ScatterPlotItem], list[str]]:
        """Scatter each ``(replica_id, signal)`` of *replicas* in the dropped style; return the items and ids."""
        style = self._style['dropped_replicas']
        items: list[pg.ScatterPlotItem] = []
        ids: list[str] = []
        if not self._style['visibility']['show_dropped']:
            return items, ids
        for rid, sig in replicas:
            item = pg.ScatterPlotItem(
                x=x,
                y=np.asarray(sig),
                symbol=style['symbol'],
                size=style['size'],
                pen=pg.mkPen(None),
                brush=pg.mkBrush(rgba(DROPPED_REPLICA_COLOR, style['alpha'])),
                name=None,
            )
            self._pg_widget.addItem(item)
            items.append(item)
            ids.append(str(rid))
        return items, ids

    def _obstacle_points_px(self) -> np.ndarray:
        """Every plotted vertex, in ViewBox-local pixel coordinates.

        Includes the fitted curves and the mean line, not just the scatter
        points — the curve is what an overlay most often lands on. Fit curves
        are already sampled densely (``_FIT_CURVE_POINTS``), so counting
        vertices stands in for testing segment/rectangle intersection.
        """
        vb = self._pg_widget.getViewBox()
        (x0, x1), (y0, y1) = vb.viewRange()
        width, height = vb.width(), vb.height()
        if x1 <= x0 or y1 <= y0 or width <= 0 or height <= 0:
            return np.empty((0, 2))

        xs: list[np.ndarray] = []
        ys: list[np.ndarray] = []
        items = [
            *self._replica_items,
            *self._dropped_items,
            *self._left_out_items,
            *self._fit_items,
            *self._error_cap_items,
            self._average_item,
        ]
        for item in items:
            if item is None or not item.isVisible():
                continue
            data_x, data_y = item.getData()
            if data_x is None or len(data_x) == 0:
                continue
            xs.append(np.asarray(data_x, dtype=float))
            ys.append(np.asarray(data_y, dtype=float))
        if not xs:
            return np.empty((0, 2))

        data_x = np.concatenate(xs)
        data_y = np.concatenate(ys)
        # y grows upward in data space but downward in pixels.
        px = (data_x - x0) / (x1 - x0) * width
        py = (1.0 - (data_y - y0) / (y1 - y0)) * height
        return np.column_stack((px, py))

    def _best_overlay_slot(
        self,
        size: tuple[float, float],
        blocked: tuple[QRectF, ...] = (),
    ) -> tuple[tuple[float, float], QRectF] | None:
        """Emptiest slot for a *size* box: ``(anchor_fractions, rect)`` in pixels.

        A compact port of matplotlib's ``Legend._find_best_position``, which
        PyQtGraph has no equivalent of (upstream issue #2769 is still open):
        score each candidate slot by how many plotted vertices it would cover,
        add a penalty for overlapping an already-placed overlay, and keep the
        lowest. Candidates are ordered so ties fall to the conventional
        top-right. Returns ``None`` while the ViewBox has no usable geometry.
        """
        vb = self._pg_widget.getViewBox()
        width, height = vb.width(), vb.height()
        box_w, box_h = size
        if width <= 0 or height <= 0 or box_w <= 0 or box_h <= 0:
            return None

        pad = _OVERLAY_PAD_PX
        free_w = max(0.0, width - box_w - 2 * pad)
        free_h = max(0.0, height - box_h - 2 * pad)
        points = self._obstacle_points_px()

        best: tuple[tuple[float, float], QRectF] | None = None
        best_badness = None
        for fx, fy in _OVERLAY_SLOTS:
            rect = QRectF(pad + fx * free_w, pad + fy * free_h, box_w, box_h)
            badness = 0.0
            if points.size:
                inside = (
                    (points[:, 0] >= rect.left())
                    & (points[:, 0] <= rect.right())
                    & (points[:, 1] >= rect.top())
                    & (points[:, 1] <= rect.bottom())
                )
                badness = float(np.count_nonzero(inside))
            badness += _BLOCKED_PENALTY * sum(1 for other in blocked if rect.intersects(other))
            if best_badness is None or badness < best_badness:
                best, best_badness = ((fx, fy), rect), badness
            if badness == 0:
                break
        return best

    def _legend_rect_px(self) -> QRectF | None:
        """The legend's current footprint in ViewBox-local pixels, if placed."""
        if self._legend is None or not self._legend.isVisible():
            return None
        rect = self._legend.boundingRect()
        if rect.isEmpty():
            return None
        return QRectF(self._legend.pos(), rect.size())

    def _annotation_html(self) -> str:
        """Body of the fit-summary overlay — what an exported figure says about the fit.

        Each binding constant reads ``estimate unit, 95 % CI [low, high]``: the
        fit the curve is drawn from and the confidence interval of that same
        fit, labelled by its level as a table or caption would write it. An estimate
        that sits on an end of its Ka search box reads in words, as the limit
        the data set (``not limited below 2.41×10³``). Every other parameter is
        its fitted value alone. Under R², where the fit moved an input, a line
        says the curve is drawn at the inputs where it put them. Rows come from
        :func:`~core.pipeline.reporting.summarize_parameters` and numbers from
        :func:`~gui.plotting.labels.fmt_value`, so the plot, the summary table
        and the exports quote the same numbers the same way. The verdict of the
        diagnostics, the marks of degenerate coefficients and split intervals,
        and the conditional fit beside an input-aware one are in the summary
        table, not on the figure. RMSE is omitted: it is already in the Fit
        Quality panel and is monotone in the R² shown here.
        """
        from core.pipeline.reporting import fit_replica_ids, summarize_parameters

        lines: list[str] = []
        for idx, result in enumerate(self._fit_results):
            rows = [spec for spec in summarize_parameters(result) if not spec.is_log]

            if len(self._fit_results) > 1:
                title = self._fit_labels[idx] if idx < len(self._fit_labels) else f'fit {idx}'
            else:
                title = 'Fit Summary'
            # A per-replicate fit is the fit of the average of the replicates it
            # used, so the heading says how many signals that average holds.
            used = fit_replica_ids(result) if result.per_replica else None
            if used:
                title += f' (average of {len(used)} replicate{"" if len(used) == 1 else "s"})'
            lines.append(f'<b>{title}</b>')

            for spec in rows:
                # The unit follows the estimate; the interval is labelled by its level.
                unit_html = f' {fmt_unit_html(spec.unit)}' if spec.unit else ''
                ends = None if spec.interval is None else tuple(map(fmt_value, spec.interval))
                estimate = fmt_estimate(
                    spec.estimate, spec.estimate_at_bound, spec.interval, spec.interval_open, html=True
                )
                # Words read as a statement about the constant, a number as its value.
                text = f'{fmt_param(spec.key)}{": " if spec.estimate_at_bound else " = "}{estimate}{unit_html}'
                if ends is not None:
                    level = f'{100 * spec.level:g} % CI ' if spec.level is not None else ''
                    text += f', {level}{fmt_interval_html(*ends, *spec.interval_open)}'
                lines.append(text)

            lines.append(f'<b>R\u00b2:</b> {fmt_r2(result.r_squared)}')
            if result.input_shifts:
                lines.append(SHIFTED_CURVE_NOTE)

            if idx < len(self._fit_results) - 1:
                lines.append('')
        return '<br>'.join(lines)

    def _rebuild_annotation(self) -> None:
        """Rebuild the draggable fit-summary overlay, then re-place it."""
        if self._annotation_item is not None:
            scene = self._annotation_item.scene()
            if scene is not None:
                scene.removeItem(self._annotation_item)
            self._annotation_item = None

        if not self._style['visibility']['show_fit_results']:
            return
        if not self._fit_results or self._mismatch_note is not None:
            return

        font_pt = self._style['annotations']['font_size']
        body = self._annotation_html()
        bg_rgba = self._style['annotations'].get('background_color', (255, 255, 255, 200))
        r, g, b = int(bg_rgba[0]), int(bg_rgba[1]), int(bg_rgba[2])
        a_frac = (bg_rgba[3] if len(bg_rgba) >= 4 else 255) / 255.0
        bg_css = f'rgba({r},{g},{b},{a_frac:.3f})'
        html = f'<div style="font-size:{font_pt}pt; background-color: {bg_css}; padding:4px; border:1px solid #aaa;">{body}</div>'
        # Parent to the ViewBox itself, not to its childGroup (which is what
        # PlotWidget.addItem does). The item then lives in ViewBox-local *pixel*
        # coordinates — exactly how PlotItem.addLegend parents the legend — so
        # its position cannot go stale when the data range or x-unit changes,
        # and it stays out of autoRange instead of feeding its own position in.
        self._annotation_item = _DraggableTextItem(html=html, anchor=(0, 0), on_moved=self._on_annotation_moved)
        self._annotation_item.setFlag(self._annotation_item.GraphicsItemFlag.ItemIsMovable)
        self._annotation_item.setParentItem(self._pg_widget.getViewBox())
        self._place_annotation()

    def _place_annotation(self) -> None:
        """Move the annotation to the emptiest slot, unless the user moved it.

        Once dragged, the annotation stays put — auto-placement is what happens
        *until* the user takes over. The dragged position is in ViewBox pixels,
        so it survives range and unit changes; it is cleared when new data
        arrives.
        """
        if self._annotation_item is None:
            return
        if self._annotation_pos is not None:
            self._annotation_item.setPos(self._annotation_pos)
            return

        rect = self._annotation_item.boundingRect()
        slot = self._best_overlay_slot(
            (rect.width(), rect.height()),
            blocked=tuple(r for r in (self._legend_rect_px(),) if r is not None),
        )
        if slot is None:
            # The ViewBox has no geometry yet (pre-paint). sigRangeChanged /
            # sigResized will call back once it does.
            return
        self._annotation_item.setPos(slot[1].topLeft())

    def _on_annotation_moved(self, pos: QPointF) -> None:
        """Remember a user drag so later rebuilds stop re-placing the box."""
        self._annotation_pos = pos

    def _on_view_geometry_changed(self, *_args) -> None:
        """Re-place the annotation once the view range or size is real."""
        self._place_annotation()
