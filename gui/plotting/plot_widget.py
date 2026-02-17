"""Main plot widget wrapping a PyQtGraph PlotWidget."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from gui.plotting.colors import (
    AVERAGE_LINE_COLOR,
    BACKGROUND_COLOR,
    DROPPED_REPLICA_COLOR,
    ERROR_BAR_COLOR,
    FOREGROUND_COLOR,
    FIT_PALETTE,
    REPLICA_PALETTE,
    rgba,
)
from gui.plotting.plot_style import DEFAULT_STYLE, line_style_to_qt


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
        x_label: str = "",
        y_label: str = "",
        title: str = "",
        parent=None,
    ):
        super().__init__(parent)
        pg.setConfigOption("background", BACKGROUND_COLOR)
        pg.setConfigOption("foreground", FOREGROUND_COLOR)

        self._pg_widget = pg.PlotWidget(title=title)
        self._pg_widget.setLabel("bottom", x_label)
        self._pg_widget.setLabel("left", y_label)
        self._pg_widget.addLegend()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._pg_widget)

        self._style: dict = {k: dict(v) for k, v in DEFAULT_STYLE.items()}

        # Item lists for in-place style mutation
        self._replica_items: List[pg.ScatterPlotItem] = []
        self._dropped_item: Optional[pg.ScatterPlotItem] = None
        self._average_item: Optional[pg.PlotCurveItem] = None
        self._error_bar_item: Optional[pg.ErrorBarItem] = None
        self._fit_items: List[pg.PlotCurveItem] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_plot(
        self,
        plot_data: Dict[str, Any],
        *,
        x_label: Optional[str] = None,
        y_label: Optional[str] = None,
    ) -> None:
        """Clear and redraw from a ``prepare_plot_data()`` dict.

        Parameters
        ----------
        plot_data : dict
            As returned by ``core.data_processing.plotting.prepare_plot_data()``.
        x_label : str, optional
            Override x-axis label.
        y_label : str, optional
            Override y-axis label.
        """
        self._clear_items()
        if x_label is not None:
            self._pg_widget.setLabel("bottom", x_label)
        if y_label is not None:
            self._pg_widget.setLabel("left", y_label)

        x = np.asarray(plot_data.get("concentrations", []))
        style = self._style

        # --- Active replicas ---
        active = plot_data.get("active_replicas", [])
        if style["visibility"]["show_replicas"]:
            for i, (rid, sig) in enumerate(active):
                color = REPLICA_PALETTE[i % len(REPLICA_PALETTE)]
                item = pg.ScatterPlotItem(
                    x=x,
                    y=np.asarray(sig),
                    symbol=style["data_points"]["symbol"],
                    size=style["data_points"]["size"],
                    pen=pg.mkPen(None),
                    brush=pg.mkBrush(rgba(color, style["data_points"]["alpha"])),
                    name=str(rid),
                )
                self._pg_widget.addItem(item)
                self._replica_items.append(item)

        # --- Dropped replicas ---
        dropped = plot_data.get("dropped_replicas", [])
        if dropped and style["dropped_replicas"]["visible"]:
            all_x = np.concatenate([x] * len(dropped))
            all_y = np.concatenate([np.asarray(sig) for _, sig in dropped])
            self._dropped_item = pg.ScatterPlotItem(
                x=all_x,
                y=all_y,
                symbol=style["dropped_replicas"]["symbol"],
                size=style["dropped_replicas"]["size"],
                pen=pg.mkPen(None),
                brush=pg.mkBrush(
                    rgba(DROPPED_REPLICA_COLOR, style["dropped_replicas"]["alpha"])
                ),
                name="dropped",
            )
            self._pg_widget.addItem(self._dropped_item)

        # --- Average line + error bars ---
        avg = plot_data.get("average")
        if avg is not None and len(active) > 0 and style["visibility"]["show_average"]:
            avg_arr = np.asarray(avg)
            pen = pg.mkPen(
                color=AVERAGE_LINE_COLOR,
                width=style["average_line"]["width"],
                style=line_style_to_qt(style["average_line"]["style"]),
            )
            self._average_item = pg.PlotCurveItem(
                x=x, y=avg_arr, pen=pen, name="average"
            )
            self._pg_widget.addItem(self._average_item)

            if len(active) > 1 and style["visibility"]["show_error_bars"]:
                signals = np.stack([np.asarray(sig) for _, sig in active])
                std = signals.std(axis=0)
                self._error_bar_item = pg.ErrorBarItem(
                    x=x,
                    y=avg_arr,
                    height=2 * std,
                    pen=pg.mkPen(
                        color=ERROR_BAR_COLOR,
                        width=style["error_bars"]["width"],
                    ),
                )
                self._pg_widget.addItem(self._error_bar_item)

        # --- Fit curves ---
        fits = plot_data.get("fits", [])
        if style["visibility"]["show_fit"]:
            for i, fit in enumerate(fits):
                color = FIT_PALETTE[i % len(FIT_PALETTE)]
                pen = pg.mkPen(
                    color=color,
                    width=style["fit_curves"]["width"],
                    style=line_style_to_qt(style["fit_curves"]["style"]),
                )
                item = pg.PlotCurveItem(
                    x=np.asarray(fit["x"]),
                    y=np.asarray(fit["y"]),
                    pen=pen,
                    name=fit.get("label", f"fit {i}"),
                )
                self._pg_widget.addItem(item)
                self._fit_items.append(item)

    def apply_style(self, style: dict) -> None:
        """Mutate existing plot items in-place with new style settings.

        Wired to ``PlotStyleWidget.style_changed``.

        Parameters
        ----------
        style : dict
            Full style dict as returned by ``PlotStyleWidget.current_style()``.
        """
        self._style = style

        dp = style["data_points"]
        for i, item in enumerate(self._replica_items):
            color = REPLICA_PALETTE[i % len(REPLICA_PALETTE)]
            item.setSymbol(dp["symbol"])
            item.setSize(dp["size"])
            item.setBrush(pg.mkBrush(rgba(color, dp["alpha"])))
            item.setVisible(style["visibility"]["show_replicas"])

        dr = style["dropped_replicas"]
        if self._dropped_item is not None:
            self._dropped_item.setSymbol(dr["symbol"])
            self._dropped_item.setSize(dr["size"])
            self._dropped_item.setBrush(
                pg.mkBrush(rgba(DROPPED_REPLICA_COLOR, dr["alpha"]))
            )
            self._dropped_item.setVisible(dr["visible"])

        al = style["average_line"]
        if self._average_item is not None:
            self._average_item.setPen(
                pg.mkPen(
                    color=AVERAGE_LINE_COLOR,
                    width=al["width"],
                    style=line_style_to_qt(al["style"]),
                )
            )
            self._average_item.setVisible(al["visible"])

        if self._error_bar_item is not None:
            self._error_bar_item.setVisible(style["visibility"]["show_error_bars"])

        fc = style["fit_curves"]
        for i, item in enumerate(self._fit_items):
            color = FIT_PALETTE[i % len(FIT_PALETTE)]
            item.setPen(
                pg.mkPen(
                    color=color,
                    width=fc["width"],
                    style=line_style_to_qt(fc["style"]),
                )
            )
            item.setVisible(style["visibility"]["show_fit"])

    def set_axis_labels(self, x_label: str, y_label: str) -> None:
        """Update axis labels.

        Parameters
        ----------
        x_label : str
        y_label : str
        """
        self._pg_widget.setLabel("bottom", x_label)
        self._pg_widget.setLabel("left", y_label)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _clear_items(self) -> None:
        """Remove all data items and rebuild the legend."""
        for item in self._replica_items:
            self._pg_widget.removeItem(item)
        if self._dropped_item is not None:
            self._pg_widget.removeItem(self._dropped_item)
        if self._average_item is not None:
            self._pg_widget.removeItem(self._average_item)
        if self._error_bar_item is not None:
            self._pg_widget.removeItem(self._error_bar_item)
        for item in self._fit_items:
            self._pg_widget.removeItem(item)

        self._replica_items = []
        self._dropped_item = None
        self._average_item = None
        self._error_bar_item = None
        self._fit_items = []

        # Rebuild legend to avoid ghost entries
        plot_item = self._pg_widget.getPlotItem()
        if plot_item.legend is not None:
            plot_item.legend.clear()
