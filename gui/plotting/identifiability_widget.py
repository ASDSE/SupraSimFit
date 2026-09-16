"""Identifiability view: how well each Ka value explains the data (pyqtgraph).

Section 1, after a fit: every multistart attempt as a dot at its Ka and R², the
exact profile (the best R² reachable at each Ka) as a line, the quality floor,
and the profile confidence interval as a band, with marginal Ka and R²
histograms of the attempts. Section 2, after a sensitivity run: the best fit of
every Sobol sample on the same axes, optionally coloured by one input's offset.

The R² axis plots ``y = -log10(1 - R²)`` so that the gap between good fits
(0.99 against 0.999) gets as much room as the gap between 0 and 0.9; its ticks
read in R².
"""

from __future__ import annotations

import re
from typing import Sequence

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFontMetrics
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QStackedLayout, QVBoxLayout, QWidget

from core.assays.registry import ASSAY_REGISTRY, AssayType, ParamKind
from core.pipeline.fit_pipeline import FitResult, fit_replica_ids, input_replica_ids
from core.pipeline.profile import ProfileResult, profile_supported
from core.pipeline.sensitivity import TITRANT, ReplicateMode, SensitivityResult
from gui.plotting.labels import fmt_param, fmt_param_plain, fmt_sci, fmt_unit_html
from gui.plotting.plot_style import DEFAULT_STYLE
from gui.plotting.sensitivity_widget import _LogKaAxis
from gui.widgets.assay_conditions import condition_fields
from gui.widgets.replica_panel import describe_replicates

_SURFACE = '#fcfcfb'
_INK = '#0b0b0b'
_INK_2 = '#52514e'
_INK_3 = '#898781'
_BELOW_FLOOR = '#c3c2b7'
_SAMPLE = '#2a78d6'
_BAND = (82, 81, 78, 28)
# Diverging scale for colouring samples by an input's offset: lower, zero, higher.
_OFFSET_CMAP = pg.ColorMap(pos=[0.0, 0.5, 1.0], color=[(42, 120, 214), (240, 239, 236), (227, 73, 72)])
# Ring of a coloured sample: the same hues, with a mid-grey centre that stays
# visible on the surface where the fill near zero offset does not.
_OFFSET_RING_CMAP = pg.ColorMap(pos=[0.0, 0.5, 1.0], color=[(42, 120, 214), (137, 135, 129), (227, 73, 72)])

_DOT_SIZE = 10
_RING_WIDTH = 2
# 1 - R² is clipped here, so R² = 0.999999 is the top of the axis.
_MIN_R2_GAP = 1e-6
# Marginal-histogram bin width, in axis units (decades of Ka, decades of 1 - R²).
_BIN_WIDTH = 0.1
# Mantissas k of the minor R² ticks, where 1 - R² = k·10⁻ⁿ, coarsest first. The
# axis takes the first set that gives at least three ticks in view.
_R2_MANTISSAS = (
    (2, 5),
    (2, 3, 5, 7),
    (1.5, 2, 3, 4, 5, 6, 7, 8, 9),
    tuple(np.round(np.arange(1.1, 10.0, 0.1), 1)),
    tuple(np.round(np.arange(1.01, 10.0, 0.01), 2)),
)

_PLACEHOLDER = 'Run a fit to see how well each Ka value can explain your data.'
_PROFILE_PENDING = 'Working out how well each Ka value can explain the data of this fit…'

_SUB_DIGITS = str.maketrans('0123456789', '₀₁₂₃₄₅₆₇₈₉')


def _r2_to_y(r2: np.ndarray) -> np.ndarray:
    """Plot coordinate of R²: ``-log10(1 - R²)``, so better fits sit higher."""
    return -np.log10(np.maximum(1.0 - np.asarray(r2, dtype=float), _MIN_R2_GAP))


def _pct(ratio: float) -> str:
    """Signed percent change for a ratio to the best fit, with a real minus sign.

    Whole percent, with as many decimals as it takes for a drop to stay short of
    −100 %, which would read as a Ka of zero.
    """
    change = 100.0 * (ratio - 1.0)
    decimals = 0
    while decimals < 4 and round(change, decimals) <= -100.0 < change:
        decimals += 1
    return f'{change:+.{decimals}f}%'.replace('-', '−')


def _plain_input_label(assay_type: AssayType, key: str) -> str:
    """Plain-text name of a perturbable input, for the colour-by combo box."""
    if key == TITRANT:
        return f'{ASSAY_REGISTRY[assay_type].x_label} (titrant)'
    for field in condition_fields(assay_type):
        if field.key == key:
            text = re.sub(r'<sub>(.*?)</sub>', lambda m: m.group(1).translate(_SUB_DIGITS), field.label)
            return re.sub(r'<[^>]+>', '', text)
    return fmt_param_plain(key)


def _histogram(values: np.ndarray, masks: list[np.ndarray]) -> tuple[np.ndarray, list[np.ndarray]]:
    """Bin edges over ``values`` and the counts of each masked subset, for stacked bars."""
    lo = np.floor(values.min() / _BIN_WIDTH) * _BIN_WIDTH
    n_bins = max(int(np.ceil((values.max() - lo) / _BIN_WIDTH)), 1)
    edges = lo + _BIN_WIDTH * np.arange(n_bins + 1)
    return edges, [np.histogram(values[m], bins=edges)[0] for m in masks]


class _R2Axis(pg.AxisItem):
    """Axis of ``y = -log10(1 - R²)`` whose ticks read in R².

    The axis is logarithmic in ``1 - R²``, so ticks sit where ``1 - R²`` is
    ``10⁻ⁿ`` (R² = 0, 0.9, 0.99, …) and, between them, at round multiples
    ``k·10⁻ⁿ``: 2 and 5 (0.98, 0.95, …) across a wide range, finer steps of
    ``k`` from ``_R2_MANTISSAS`` (0.97, 0.993, …) as the range narrows. Every
    tick is a value a reader can take at face value.
    """

    def tickValues(self, minVal, maxVal, size):
        lo, hi = sorted((minVal, maxVal))
        decades = range(int(np.floor(lo)), int(np.ceil(hi)) + 1)
        majors = [float(d) for d in decades if lo <= d <= hi]
        for mantissas in _R2_MANTISSAS:
            minors = sorted(d - np.log10(k) for d in decades for k in mantissas if lo <= d - np.log10(k) <= hi)
            if len(majors) + len(minors) >= 3:
                break
        return [(1.0, majors), (None, minors)]

    def tickStrings(self, values, scale, spacing):
        return [_r2_label(v) for v in values]


def _r2_label(y: float) -> str:
    """R² at plot coordinate *y*, with the fewest decimals that state it exactly.

    Ticks sit at round values of ``1 - R²``, so a short exact label exists; the
    tolerance only absorbs floating-point error.
    """
    if abs(y) < 1e-9:
        return '0'
    r2 = 1.0 - 10.0 ** (-y)
    gap = abs(1.0 - r2)
    for digits in range(max(int(np.ceil(y - 1e-9)), 0), 12):
        if abs(round(r2, digits) - r2) <= 1e-6 * gap:
            break
    return f'{r2:.{digits}f}'


class IdentifiabilityWidget(QWidget):
    """Fit attempts, the exact Ka profile and sensitivity samples on one R²-vs-Ka chart.

    :meth:`update_fit` shows a fit and its :class:`ProfileResult`;
    :meth:`update_sensitivity` overlays a :class:`SensitivityResult`;
    :meth:`clear` returns to the placeholder and :meth:`apply_style` restyles.
    :meth:`show_mismatch` hides the fit, or only the sensitivity overlay, behind
    a note while it no longer matches the loaded selection; both are kept and
    drawn again once the note is removed.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setToolTip(
            '<qt>Each dot is one fit attempt: its K<sub>a</sub> across, how well it fits up.<br>'
            'The line is the best R² any fit can reach at each K<sub>a</sub>; the shaded band is '
            'the range of K<sub>a</sub> the data support.<br>Scroll to zoom, drag to pan, '
            'right-click for the full view.</qt>'
        )
        self._style: dict = dict(DEFAULT_STYLE)
        self._fit: FitResult | None = None
        self._profile: ProfileResult | None = None
        self._profile_pending = False  # the fit's profile is still being computed
        self._assay_type_name = ''
        self._sensitivity: SensitivityResult | None = None
        self._fit_note: str | None = None  # why the fit is hidden
        self._sensitivity_note: str | None = None  # why the sensitivity overlay is hidden
        self._replica_ids: list[str] | None = None
        self._colour_key: str | None = None
        # Drawn items per Ka key, for tests and restyling: main plot, curves, scatters.
        self._items: dict[str, dict] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._stack_host = QWidget()
        self._stack = QStackedLayout(self._stack_host)

        self._message = QLabel(_PLACEHOLDER)
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setWordWrap(True)
        self._message.setStyleSheet(f'color: {_INK_3}; font-size: 14px;')
        self._stack.addWidget(self._message)

        self._content = QWidget()
        self._content.setObjectName('identifiabilityContent')
        self._content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._content.setStyleSheet(f'#identifiabilityContent {{ background: {_SURFACE}; }}')
        content = QVBoxLayout(self._content)
        content.setContentsMargins(10, 6, 10, 6)
        content.setSpacing(4)

        self._summary = QLabel()
        self._summary.setTextFormat(Qt.TextFormat.RichText)
        self._summary.setWordWrap(True)
        self._summary.setStyleSheet(f'color: {_INK}; font-size: 14px;')
        content.addWidget(self._summary)

        self._controls = QWidget()
        controls = QHBoxLayout(self._controls)
        controls.setContentsMargins(0, 0, 0, 0)
        colour_label = QLabel('Colour sensitivity samples by:')
        colour_label.setStyleSheet(f'color: {_INK_2};')
        controls.addWidget(colour_label)
        self._colour_combo = QComboBox()
        self._colour_combo.setToolTip('Colour each sample by how far that input was moved from what you entered.')
        self._colour_combo.currentIndexChanged.connect(self._on_colour_changed)
        controls.addWidget(self._colour_combo)
        controls.addStretch(1)
        self._controls.setVisible(False)
        content.addWidget(self._controls)

        self._glw = pg.GraphicsLayoutWidget()
        self._glw.setBackground(_SURFACE)
        self._glw.setMinimumHeight(360)
        content.addWidget(self._glw, stretch=1)

        self._legend = QLabel()
        self._legend.setTextFormat(Qt.TextFormat.RichText)
        self._legend.setWordWrap(True)
        self._legend.setStyleSheet(f'color: {_INK_2}; font-size: 13px;')
        content.addWidget(self._legend)

        self._notes = QLabel()
        self._notes.setTextFormat(Qt.TextFormat.RichText)
        self._notes.setWordWrap(True)
        self._notes.setStyleSheet(f'color: {_INK_2}; font-size: 13px;')
        content.addWidget(self._notes)

        self._stack.addWidget(self._content)
        self._stack.setCurrentWidget(self._message)
        outer.addWidget(self._stack_host)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_fit(self, fit_result: FitResult, profile: ProfileResult | None, assay_type_name: str) -> None:
        """Show *fit_result*'s attempts and, when given, its Ka *profile*.

        *profile* is ``None`` for an assay without a single binding constant,
        or when the profile has not been computed.
        """
        self._fit = fit_result
        self._profile = profile
        self._profile_pending = False
        self._assay_type_name = assay_type_name
        self._render()

    def show_profile_pending(self, fit_result: FitResult, assay_type_name: str) -> None:
        """Hold *fit_result* and say its Ka profile is being computed, until :meth:`update_fit` brings it.

        The page never shows a previous fit meanwhile; a note hiding the fit
        still takes precedence.
        """
        self._fit = fit_result
        self._profile = None
        self._profile_pending = True
        self._assay_type_name = assay_type_name
        self._render()

    def update_sensitivity(self, result: SensitivityResult | None) -> None:
        """Overlay the sample best fits of a sensitivity *result* (``None`` removes them)."""
        self._sensitivity = result
        self._sync_colour_combo()
        self._render()

    def show_mismatch(self, fit_note: str | None, sensitivity_note: str | None = None) -> None:
        """Hide the fit behind *fit_note* and the sensitivity overlay behind *sensitivity_note*; ``None`` shows it.

        Unchanged notes leave the page as it is.
        """
        if (fit_note, sensitivity_note) == (self._fit_note, self._sensitivity_note):
            return
        self._fit_note = fit_note
        self._sensitivity_note = sensitivity_note
        self._render()

    def set_replica_ids(self, replica_ids: Sequence[str] | None) -> None:
        """The loaded data's replicate ids in order, so notes name replicates as the Replicas panel does."""
        self._replica_ids = None if replica_ids is None else list(replica_ids)
        self._render()

    def clear(self) -> None:
        """Drop the fit, profile and sensitivity overlay and show the placeholder."""
        self._fit = None
        self._profile = None
        self._profile_pending = False
        self._assay_type_name = ''
        self._sensitivity = None
        self._sync_colour_combo()
        self._render()

    def apply_style(self, style: dict) -> None:
        """Adopt a new style dict (fonts) and re-render."""
        self._style = style
        self._render()

    # ------------------------------------------------------------------
    # Colour-by control
    # ------------------------------------------------------------------

    def _sample_inputs(self) -> list[str]:
        result = self._sensitivity
        if result is None or result.sample_offsets_pct is None:
            return []
        return list(result.sample_offsets_pct)

    def _sync_colour_combo(self) -> None:
        """Offer None plus each varied input of the current run; keep the choice if still offered."""
        keys = self._sample_inputs()
        if self._colour_key not in keys:
            self._colour_key = None
        self._colour_combo.blockSignals(True)
        self._colour_combo.clear()
        self._colour_combo.addItem('None', None)
        if keys:
            assay_type = AssayType[self._sensitivity.assay_type]
            for key in keys:
                self._colour_combo.addItem(_plain_input_label(assay_type, key), key)
        self._colour_combo.setCurrentIndex(0 if self._colour_key is None else keys.index(self._colour_key) + 1)
        self._colour_combo.blockSignals(False)

    def _on_colour_changed(self, index: int) -> None:
        self._colour_key = self._colour_combo.itemData(index)
        self._render()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _show_message(self, text: str) -> None:
        self._message.setText(text)
        self._stack.setCurrentWidget(self._message)

    def _render(self) -> None:
        """Rebuild the page from the stored fit, profile and sensitivity result."""
        self._glw.clear()
        self._items = {}
        # The colour control is offered only while the sensitivity dots it colours are drawn.
        self._controls.setVisible(False)
        if self._fit is None:
            self._show_message(_PLACEHOLDER)
            return
        if self._fit_note:
            self._show_message(self._fit_note)
            return
        assay_type = AssayType[self._assay_type_name]
        meta = ASSAY_REGISTRY[assay_type]
        ka_keys = [k for k in meta.parameter_keys if meta.param_kinds[k] is ParamKind.BINDING_CONSTANT]
        if not ka_keys:
            self._show_message(f'Not applicable: a {meta.subtype_label} fit has no binding constant to examine.')
            return
        if self._profile_pending:
            self._show_message(_PROFILE_PENDING)
            return

        fit = self._fit
        floor = fit.fit_config.get('min_r_squared')
        profile = self._profile
        notes: list[str] = []
        legend: dict[str, tuple[str, str]] = {}
        if not profile_supported(assay_type):
            notes.append(
                'The best R² reachable at each K<sub>a</sub> can only be computed for assays with a single '
                'binding constant, so only the fit attempts are shown.'
            )
        elif profile is None:
            notes.append('The best-R² line and the confidence interval are not available for this fit.')
        if floor is None:
            notes.append('This fit does not record its quality floor, so no floor is drawn.')

        attempts = self._attempts(fit, notes)
        samples = self._samples(notes)
        self._controls.setVisible(samples is not None and bool(self._sample_inputs()))
        self._replicate_notes(fit, samples is not None, notes)
        if profile is not None and profile.per_replica:
            notes.append(
                "The line and the interval are for the replicates' average: the replicates miss the model in the "
                'same way, so counting every replicate as separate evidence would make K<sub>a</sub> look more '
                'certain than it is.'
            )

        summary = []
        for col, ka_key in enumerate(ka_keys):
            key_profile = profile if profile is not None and profile.ka_key == ka_key else None
            unit_html = fmt_unit_html(meta.units.get(ka_key, ''))
            self._render_key(3 * col, ka_key, unit_html, floor, key_profile, attempts, samples, legend, notes)
            summary.append(self._summary_line(ka_key, unit_html, key_profile))

        self._summary.setText('<br>'.join(summary))
        # Non-breaking spaces inside each entry, so the legend only wraps between entries.
        self._legend.setText(
            '&emsp; '.join(f'{glyph}&nbsp;{text.replace(" ", "&nbsp;")}' for glyph, text in legend.values())
        )
        self._notes.setText('<br>'.join(notes))
        self._notes.setVisible(bool(notes))
        self._stack.setCurrentWidget(self._content)

    def _replicate_notes(self, fit: FitResult, dots: bool, notes: list[str]) -> None:
        """Name the replicates the fit left out, and a sensitivity run whose dots describe other replicates.

        *dots* says whether the sensitivity dots are drawn.
        """
        used = fit_replica_ids(fit)
        if used is None:
            skipped = list(fit.metadata.get('replica_failures') or {})
        else:
            skipped = [rid for rid in input_replica_ids(fit) or () if rid not in used]
        run_used = None
        if dots and self._sensitivity.baseline_fit is not None:
            run_used = fit_replica_ids(self._sensitivity.baseline_fit)
        same_run = dots and run_used is not None and used is not None and set(run_used) == set(used)
        if skipped:
            names = describe_replicates(skipped, self._replica_ids)
            many = len(skipped) > 1
            where = 'of the line, the attempts and the sensitivity dots' if same_run else 'here'
            notes.append(
                f'{names[0].upper()}{names[1:]} {"are" if many else "is"} left out {where}, '
                f'as {"they were" if many else "it was"} from the fit.'
            )
        if run_used is not None and used is not None and set(run_used) != set(used):
            notes.append(
                f'The sensitivity run used {describe_replicates(run_used, self._replica_ids)}, but this fit used '
                f'{describe_replicates(used, self._replica_ids)}, so the dots describe other replicates than the '
                'line and the attempts.'
            )

    def _attempts(self, fit: FitResult, notes: list[str]) -> dict | None:
        """The fit's attempts with R² ≥ 0, noting how many were hidden and why."""
        if fit.attempt_samples is None or fit.attempt_quality is None:
            notes.append('This fit has no record of its individual attempts, so no dots are shown.')
            return None
        r2 = np.asarray(fit.attempt_quality['r_squared'], dtype=float)
        n_negative = int(np.sum(r2 < 0))
        if n_negative:
            notes.append(f'{n_negative} of {r2.size} attempts not shown: they fit worse than a flat line (R² &lt; 0).')
        if fit.uncertainty_source == 'replicate':
            notes.append(
                "Each attempt fitted one replicate, so its R² belongs to that replicate's own thin line, "
                'not to the line for their average.'
            )
        return {'samples': fit.attempt_samples, 'r2': r2}

    def _samples(self, notes: list[str]) -> dict | None:
        """The sensitivity run's sample best fits, when they can be compared with this fit."""
        result = self._sensitivity
        if result is None:
            return None
        if self._sensitivity_note:
            notes.append(f'The sensitivity dots are not shown. {self._sensitivity_note}')
            return None
        if result.assay_type != self._assay_type_name:
            notes.append('The last sensitivity run was for another assay type; run it again to compare it here.')
            return None
        if result.sample_ka is None:
            notes.append(
                'Heatmap runs are shown on the Ka Sensitivity tab only; run the sensitivity-index analysis '
                'to see its fits here.'
            )
            return None
        r2 = np.asarray(result.sample_r2, dtype=float)
        below = r2 < result.floor if result.floor is not None else np.zeros(r2.size, dtype=bool)
        hidden = int(np.sum(~(r2 >= 0)))
        text = f'Sensitivity dots: the best fit of each of the {r2.size} samples'
        text += f'; the {int(below.sum())} below the quality floor are hollow.' if below.any() else '.'
        if hidden:
            text += f' {hidden} not shown: no fit could be made, or it fit worse than a flat line (R² &lt; 0).'
        text += ' A dot can sit above the line: the line uses the inputs as entered, each dot its own changed inputs.'
        notes.append(text)
        mode = result.config.replicate_mode
        fit_per_replica = self._fit.uncertainty_source == 'replicate'
        if mode is not ReplicateMode.FOLLOW and (mode is ReplicateMode.PER_REPLICA) != fit_per_replica:
            run_way, fit_way = (
                ('each replicate separately', 'their average')
                if mode is ReplicateMode.PER_REPLICA
                else ('the average of the replicates', 'each replicate separately')
            )
            notes.append(
                f'The sensitivity run fitted {run_way} but this fit used {fit_way}, so the blue dots and the '
                'grey ones measure R² against different signals.'
            )
        offsets = result.sample_offsets_pct.get(self._colour_key) if self._colour_key is not None else None
        return {'ka': result.sample_ka, 'r2': r2, 'below': below, 'offsets': offsets}

    def _summary_line(self, ka_key: str, unit_html: str, profile: ProfileResult | None) -> str:
        """One line per Ka key: best fit, then the confidence interval and how far it reaches."""
        label = fmt_param(ka_key)
        if profile is None:
            return f'{label}: fit attempts'
        best = profile.best_ka
        lo, hi = profile.ci
        lo_open, hi_open = profile.ci_open
        if lo_open or hi_open:
            # The unit follows each number, never the word "open".
            ends = [
                ('open' if is_open else f'{fmt_sci(v)} {unit_html}'.strip())
                for v, is_open in ((lo, lo_open), (hi, hi_open))
            ]
            ci_txt = ' – '.join(ends)
        else:
            ci_txt = f'{fmt_sci(lo)} – {fmt_sci(hi)} {unit_html}'.strip()
        lo_pct, hi_pct = ('open' if lo_open else _pct(lo / best)), ('open' if hi_open else _pct(hi / best))
        line = (
            f'{label}: best fit{" of the replicates' average" if profile.per_replica else ""} '
            f'{fmt_sci(best, 3)} {unit_html} (R² {profile.best_r2:.4f}) · '
            f'{profile.level:.0%} CI {ci_txt} ({lo_pct} / {hi_pct})'
        )
        for is_open, side, bound in ((lo_open, 'lower', lo), (hi_open, 'higher', hi)):
            if is_open:
                line += (
                    f'<br><span style="color:{_INK_2}">Open: the data cannot rule out a {side} '
                    f'K<sub>a</sub>, up to the bound of {fmt_sci(bound)} {unit_html}.</span>'
                )
        return line

    def _render_key(
        self,
        col: int,
        ka_key: str,
        unit_html: str,
        floor: float | None,
        profile: ProfileResult | None,
        attempts: dict | None,
        samples: dict | None,
        legend: dict[str, tuple[str, str]],
        notes: list[str],
    ) -> None:
        """Draw one Ka key's chart: marginal histograms, main plot and, when colouring, a colour bar."""
        tick_font, label_font = self._fonts()
        tick_fm, label_fm = QFontMetrics(tick_font), QFontMetrics(label_font)
        left_width = tick_fm.horizontalAdvance('0.999999') + label_fm.height() + 16
        bottom_height = tick_fm.height() + label_fm.height() + 16

        main = self._glw.addPlot(row=1, col=col, axisItems={'left': _R2Axis('left'), 'bottom': _LogKaAxis('bottom')})
        main.getAxis('bottom').setLogMode(True)
        for name in ('left', 'bottom'):
            main.getAxis(name).enableAutoSIPrefix(False)
        main.setLabel('left', 'R²')
        main.setLabel('bottom', f'{fmt_param(ka_key)} [{unit_html}]' if unit_html else fmt_param(ka_key))
        main.showGrid(x=True, y=True, alpha=0.18)
        self._style_axes(main, tick_font, label_font)
        main.getAxis('left').setWidth(left_width)
        main.getAxis('bottom').setHeight(bottom_height)
        items: dict = {'main': main, 'average': None, 'replicas': [], 'colour_bar': None}
        self._items[ka_key] = items
        xs: list[np.ndarray] = []
        ys: list[np.ndarray] = []
        attempt_x = np.empty(0)

        if profile is not None:
            log_grid = np.log10(profile.grid)
            lo, hi = np.log10(profile.ci)
            band = pg.LinearRegionItem(values=(lo, hi), movable=False, brush=pg.mkBrush(*_BAND), pen=pg.mkPen(None))
            band.setZValue(-10)
            main.addItem(band)
            legend['band'] = ('<span style="color:#dddcd7">&#9608;</span>', f'{profile.level:.0%} confidence interval')
            for r2 in (profile.replica_r2 or {}).values():
                curve = main.plot(log_grid, _r2_to_y(r2), pen=pg.mkPen(_INK_3, width=1))
                curve.setZValue(2.8)
                items['replicas'].append(curve)
            if profile.replica_r2:
                legend['replicas'] = (f'<span style="color:{_INK_3}">&#9472;</span>', 'each replicate on its own')
            items['average'] = main.plot(log_grid, _r2_to_y(profile.r2), pen=pg.mkPen(_INK, width=2))
            items['average'].setZValue(3)
            legend['profile'] = (
                f'<span style="color:{_INK}">&#9473;</span>',
                'best R² reachable at each K<sub>a</sub>'
                + (" on the replicates' average" if profile.per_replica else ''),
            )
            xs.append(np.array([lo, hi, np.log10(profile.best_ka)]))

        if floor is not None:
            floor_y = float(_r2_to_y(floor))
            line = pg.InfiniteLine(
                pos=floor_y,
                angle=0,
                pen=pg.mkPen(_INK_2, width=1.5, style=Qt.PenStyle.DashLine),
                label=f'quality floor {floor:g}',
                labelOpts={
                    'position': 0.02,
                    'color': _INK_2,
                    'anchors': [(0, 1), (0, 1)],
                    'fill': pg.mkBrush(_SURFACE),
                },
            )
            line.label.setFont(tick_font)
            # Above every dot, so the filled label stays legible where it crosses them.
            line.setZValue(6)
            main.addItem(line, ignoreBounds=True)
            legend['floor'] = (f'<span style="color:{_INK_2}">&#8211;&nbsp;&#8211;</span>', 'quality floor')
            ys.append(np.array([floor_y]))

        if attempts is not None:
            ka = np.asarray(attempts['samples'][ka_key], dtype=float)
            r2 = attempts['r2']
            positive = np.isfinite(ka) & (ka > 0)
            if (~positive).any():
                notes.append(f'{int((~positive).sum())} attempts without a positive {fmt_param(ka_key)} not shown.')
            shown = positive & (r2 >= 0)
            x, y = np.log10(ka[shown]), _r2_to_y(r2[shown])
            passing = r2[shown] >= floor if floor is not None else np.ones(x.size, dtype=bool)
            for key, mask, colour, z in (('below', ~passing, _BELOW_FLOOR, 2), ('passing', passing, _INK_2, 2.5)):
                scatter = pg.ScatterPlotItem(
                    x=x[mask],
                    y=y[mask],
                    size=_DOT_SIZE,
                    brush=pg.mkBrush(colour),
                    pen=pg.mkPen(_SURFACE, width=_RING_WIDTH),
                )
                scatter.setZValue(z)
                main.addItem(scatter)
                items[f'attempts_{key}'] = scatter
            legend['passing'] = (f'<span style="color:{_INK_2}">&#9679;</span>', 'fit attempt passing the floor')
            if (~passing).any():
                legend['below'] = (f'<span style="color:{_BELOW_FLOOR}">&#9679;</span>', 'fit attempt below the floor')
            # An attempt below the floor far from the rest (at a Ka bound, say)
            # would squeeze the interval to a sliver, so the view frames the
            # passing attempts across and every attempt up and down.
            attempt_x = x
            xs.append(x[passing])
            ys.append(y)
            if x.size:
                self._add_marginals(col, main, x, y, passing, left_width, bottom_height)

        if samples is not None and ka_key in samples['ka']:
            x, y = self._add_samples(col, main, ka_key, samples, legend)
            xs.append(x)
            ys.append(y)

        if not any(x.size for x in xs):
            xs = [attempt_x]
        x_view = self._frame(main, profile, xs, ys)
        outside = int(np.sum((attempt_x < x_view[0]) | (attempt_x > x_view[1]))) if x_view else 0
        if outside:
            notes.append(
                f'{outside} of {attempt_x.size} attempts at {fmt_param(ka_key)}, all below the quality floor, '
                'lie outside this view; zoom out to see them.'
            )

    def _add_samples(
        self, col: int, main: pg.PlotItem, ka_key: str, samples: dict, legend: dict[str, tuple[str, str]]
    ) -> tuple[np.ndarray, np.ndarray]:
        """Scatter the sensitivity samples' best fits, hollow below the floor, coloured by offset if chosen."""
        ka = np.asarray(samples['ka'][ka_key], dtype=float)
        r2 = samples['r2']
        shown = np.isfinite(ka) & (ka > 0) & (r2 >= 0)
        x, y = np.log10(ka[shown]), _r2_to_y(r2[shown])
        below = samples['below'][shown]
        offsets = samples['offsets']
        if offsets is None:
            brushes = [pg.mkBrush(_SURFACE) if b else pg.mkBrush(_SAMPLE) for b in below]
            pens = [pg.mkPen(_SAMPLE if b else _SURFACE, width=_RING_WIDTH) for b in below]
        else:
            off = np.asarray(offsets, dtype=float)[shown]
            reach = float(np.max(np.abs(off))) if off.size else 0.0
            reach = reach or 1.0
            position = (off + reach) / (2.0 * reach)
            colours = [pg.mkColor(*c) for c in _OFFSET_CMAP.map(position, mode='byte')]
            rings = [pg.mkColor(*c) for c in _OFFSET_RING_CMAP.map(position, mode='byte')]
            # Fills near zero offset are close to the surface colour, so every
            # coloured dot carries a ring of its own hue that stays visible.
            brushes = [pg.mkBrush(_SURFACE) if b else pg.mkBrush(c) for b, c in zip(below, colours)]
            pens = [pg.mkPen(r, width=_RING_WIDTH if b else 1) for b, r in zip(below, rings)]
            name = self._colour_combo.currentText()
            cbar = pg.ColorBarItem(
                values=(-reach, reach), colorMap=_OFFSET_CMAP, interactive=False, width=14, pen=_INK_3
            )
            tick_font, label_font = self._fonts()
            cbar.axis.setTickFont(tick_font)
            cbar.axis.setTextPen(pg.mkPen(_INK_2))
            cbar.axis.setLabel(f'{name} offset [%]', color=_INK_2, **{'font-size': f'{label_font.pointSize()}pt'})
            legend['colour'] = (
                f'<span style="color:{_SAMPLE}">&#9679;</span><span style="color:#e34948">&#9679;</span>',
                f'{name} set lower (blue) or higher (red) than entered',
            )
            self._glw.addItem(cbar, row=1, col=col + 2)
            self._items[ka_key]['colour_bar'] = cbar
        scatter = pg.ScatterPlotItem(x=x, y=y, size=_DOT_SIZE, brush=brushes, pen=pens)
        scatter.setZValue(5)
        main.addItem(scatter)
        self._items[ka_key]['samples'] = scatter
        colour = _SAMPLE if offsets is None else _INK_2
        legend['samples'] = (f'<span style="color:{colour}">&#9679;</span>', 'sensitivity sample best fit')
        if below.any():
            legend['samples_below'] = (f'<span style="color:{colour}">&#9675;</span>', 'sample below the floor')
        return x, y

    def _add_marginals(
        self,
        col: int,
        main: pg.PlotItem,
        x: np.ndarray,
        y: np.ndarray,
        passing: np.ndarray,
        left_width: int,
        bottom_height: int,
    ) -> None:
        """Stacked Ka histogram above and R² histogram to the right of *main*, linked to its axes."""
        top = self._glw.addPlot(row=0, col=col)
        right = self._glw.addPlot(row=1, col=col + 1)
        top.setMaximumHeight(80)
        right.setMaximumWidth(110)
        top.setXLink(main)
        right.setYLink(main)
        for plot, count_axis in ((top, 'y'), (right, 'x')):
            plot.hideButtons()
            plot.setMenuEnabled(False)
            plot.setMouseEnabled(x=count_axis == 'y', y=count_axis == 'x')
            plot.enableAutoRange(axis=count_axis)
            plot.setAutoVisible(**{count_axis: True})
        top.hideAxis('bottom')
        right.hideAxis('left')
        tick_font, _ = self._fonts()
        caption = pg.LabelItem('counts of<br>attempts', color=_INK_3, size=f'{tick_font.pointSize()}pt', justify='left')
        caption.setMaximumSize(110, 80)
        self._glw.addItem(caption, row=0, col=col + 1)
        # The main plot takes every spare pixel; the marginal cells keep their capped sizes.
        grid = self._glw.ci.layout
        grid.setRowStretchFactor(1, 1)
        grid.setColumnStretchFactor(col, 1)
        # Invisible axes of the same size as the main plot's keep the histograms aligned with it.
        top.getAxis('left').setStyle(showValues=False)
        top.getAxis('left').setPen(pg.mkPen(None))
        top.getAxis('left').setWidth(left_width)
        right.showAxis('bottom')
        right.getAxis('bottom').setStyle(showValues=False)
        right.getAxis('bottom').setPen(pg.mkPen(None))
        right.getAxis('bottom').setHeight(bottom_height)

        for values, plot, vertical in ((x, top, True), (y, right, False)):
            edges, (below, passed) = _histogram(values, [~passing, passing])
            for y0, y1, colour in ((0, below, _BELOW_FLOOR), (below, below + passed, _INK_2)):
                if vertical:
                    bars = pg.BarGraphItem(x0=edges[:-1], x1=edges[1:], y0=y0, y1=y1, brush=colour, pen=pg.mkPen(None))
                else:
                    bars = pg.BarGraphItem(x0=y0, x1=y1, y0=edges[:-1], y1=edges[1:], brush=colour, pen=pg.mkPen(None))
                plot.addItem(bars)

    def _frame(
        self, main: pg.PlotItem, profile: ProfileResult | None, xs: list[np.ndarray], ys: list[np.ndarray]
    ) -> tuple[float, float] | None:
        """Default view: the Ka values in *xs* across, *ys* and the best-R² line inside that span up and down.

        Returns the Ka range of the view in log10 units, ``None`` when there is nothing to frame.
        """
        x_all = np.concatenate(xs) if xs else np.empty(0)
        if not x_all.size:
            return None
        x_lo, x_hi = float(x_all.min()), float(x_all.max())
        if x_hi - x_lo < 1.0:
            mid = 0.5 * (x_lo + x_hi)
            x_lo, x_hi = mid - 0.5, mid + 0.5
        pad = 0.05 * (x_hi - x_lo)
        x_lo, x_hi = x_lo - pad, x_hi + pad
        if profile is not None:
            log_grid = np.log10(profile.grid)
            inside = (log_grid >= x_lo) & (log_grid <= x_hi)
            ys.append(_r2_to_y(profile.r2[inside]))
        y_all = np.concatenate(ys)
        y_lo, y_hi = float(y_all.min()), float(y_all.max())
        y_pad = max(0.08 * (y_hi - y_lo), 0.1)
        main.setRange(xRange=(x_lo, x_hi), yRange=(y_lo - y_pad, y_hi + y_pad), padding=0)
        return x_lo, x_hi

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------

    def _fonts(self) -> tuple[QFont, QFont]:
        dist = self._style.get('distribution', {})
        tick_font = QFont()
        tick_font.setPointSize(dist.get('tick_font_size', 12))
        label_font = QFont()
        label_font.setPointSize(dist.get('label_font_size', 14))
        return tick_font, label_font

    @staticmethod
    def _style_axes(plot: pg.PlotItem, tick_font: QFont, label_font: QFont) -> None:
        for name in ('left', 'bottom'):
            axis = plot.getAxis(name)
            axis.setTickFont(tick_font)
            axis.label.setFont(label_font)
            axis.setPen(pg.mkPen(_INK_3, width=1))
            axis.setTextPen(pg.mkPen(_INK_2))
