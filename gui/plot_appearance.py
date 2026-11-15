"""The appearance of a session's titration plot, with no widget (DESIGN.md §8, Plot appearance).

A :class:`PlotAppearance` styles the titration plot of Measurements and Fit results and
its saved figure: the size of the replicates' points and of the mean's, the replicates'
mark and colours, the fitted curve's width and colour, the width of the error bars, and
the size of the axis text. Every choice is one of a short menu, and each maps to
tokens — a ``SIZE`` entry, colours of both themes, a ``TYPE`` role — so the plot stays
in the design in either theme. The means and the error bars keep ``text-primary``. The
built-in appearance draws the plot as DESIGN.md §7 describes it: each replicate in a
colour of its own, the fitted curve in ``accent``.

Each session holds its own appearance. It is written into the session's results file
(:meth:`PlotAppearance.to_dict`) and stored as the start of new sessions in the
preferences (:func:`gui.preferences.set_plot_appearance_default`).
"""

from __future__ import annotations

from dataclasses import dataclass, fields

from gui.design.tokens import REPLICATE_COLOURS, SIZE

#: The point sizes offered: key → (label, ``SIZE`` token).
MARKER_SIZES = {
    'small': ('Small', 'marker-small'),
    'medium': ('Medium', 'marker-medium'),
    'large': ('Large', 'marker-large'),
}

#: The marks offered for the replicates' points: key → (label, pyqtgraph symbol).
SHAPES = {
    'circle': ('Circle', 'o'),
    'square': ('Square', 's'),
    'triangle': ('Triangle', 't1'),
}

#: The stroke widths offered for the fitted curve and the error bars: key → (label, ``SIZE`` token).
WIDTHS = {
    'thin': ('Thin', 'stroke-thin'),
    'medium': ('Medium', 'stroke-medium'),
    'thick': ('Thick', 'stroke-thick'),
}

#: The colours offered for the replicates' points: key → (label, colour tokens). Replicate *n* of
#: the data takes the *n*-th token, so it keeps its colour in every view and when others are
#: switched off; *Grey* draws every replicate in one. Each is a token of both themes, so the plot
#: keeps its contrast in light and dark; none is the ``text-primary`` of the means.
COLOURS = {
    'by-replicate': ('By replicate', tuple(f'replicate-{n}' for n in range(1, REPLICATE_COLOURS + 1))),
    'grey': ('Grey', ('replicate',)),
}

#: The colours offered for the fitted curve: key → (label, colour token), ``accent`` first.
FIT_COLOURS = {
    'teal': ('Teal', 'accent'),
    'blue': ('Blue', 'series-1'),
    'magenta': ('Magenta', 'series-2'),
    'text': ('Text colour', 'text-primary'),
}

#: The sizes offered for the axis text: key → (label, tick-label role, axis-title role).
#: Every tick-label role has tabular figures, so a column of ticks aligns digit for digit.
TEXT_SIZES = {
    'standard': ('Standard', 'small-number', 'label'),
    'large': ('Large', 'number', 'body-strong'),
    'larger': ('Larger', 'number-large', 'title'),
}

#: The × of a replicate switched off is drawn a sixth larger than a point, so its thin
#: strokes read at the weight of the filled points beside it.
CROSS_SCALE = 7 / 6

#: The menu each field chooses from, and what the field is called in a message.
_MENUS = {
    'replicate_size': (MARKER_SIZES, 'the size of the replicate points'),
    'mean_size': (MARKER_SIZES, 'the size of the mean points'),
    'replicate_shape': (SHAPES, 'the mark of the replicate points'),
    'fit_width': (WIDTHS, 'the width of the fitted curve'),
    'error_bar_width': (WIDTHS, 'the width of the error bars'),
    'replicate_colour': (COLOURS, 'the colour of the replicate points'),
    'fit_colour': (FIT_COLOURS, 'the colour of the fitted curve'),
    'text_size': (TEXT_SIZES, 'the size of the axis text'),
}


def menu(name: str) -> dict:
    """The menu field *name* chooses from: key → (label, …)."""
    return _MENUS[name][0]


@dataclass(frozen=True)
class PlotAppearance:
    """How the titration plot is drawn; each field is a key of its menu (:func:`menu`).

    Raises ``ValueError`` on a key its menu does not offer, in words for the user.
    """

    replicate_size: str = 'medium'
    mean_size: str = 'medium'
    replicate_shape: str = 'circle'
    fit_width: str = 'medium'
    error_bar_width: str = 'thin'
    replicate_colour: str = 'by-replicate'
    fit_colour: str = 'teal'
    text_size: str = 'standard'

    def __post_init__(self) -> None:
        for f in fields(self):
            options, what = _MENUS[f.name]
            value = getattr(self, f.name)
            if value not in options:
                *first, last = options
                raise ValueError(
                    f'The plot appearance sets {what} to “{value}”, where this version reads only '
                    f'{", ".join(first)} or {last}.'
                )

    # ── What the plot draws with ───────────────────────────────────────────────

    @property
    def replicate_px(self) -> int:
        """The size of a replicate's point, in px."""
        return SIZE[MARKER_SIZES[self.replicate_size][1]]

    @property
    def cross_px(self) -> float:
        """The size of the × of a replicate switched off, in px."""
        return self.replicate_px * CROSS_SCALE

    @property
    def mean_px(self) -> int:
        """The size of a mean's point, in px."""
        return SIZE[MARKER_SIZES[self.mean_size][1]]

    @property
    def symbol(self) -> str:
        """The pyqtgraph symbol of a replicate's point."""
        return SHAPES[self.replicate_shape][1]

    @property
    def fit_px(self) -> int:
        """The width of the fitted curve, in px."""
        return SIZE[WIDTHS[self.fit_width][1]]

    @property
    def error_bar_px(self) -> int:
        """The width of the mean ± SD error bars, in px."""
        return SIZE[WIDTHS[self.error_bar_width][1]]

    def replicate_mark(self, index: int) -> tuple[str, str]:
        """The colour token and pyqtgraph symbol of the replicate at *index* in the data's order (A is 0).

        By replicate, the colours repeat past the last with the next mark of :data:`SHAPES`, so
        every replicate up to three times the colours has a mark of its own; Grey draws every
        replicate alike.
        """
        tokens = COLOURS[self.replicate_colour][1]
        if len(tokens) == 1:
            return tokens[0], self.symbol
        shapes = list(SHAPES)
        shape = shapes[(shapes.index(self.replicate_shape) + index // len(tokens)) % len(shapes)]
        return tokens[index % len(tokens)], SHAPES[shape][1]

    @property
    def fit_token(self) -> str:
        """The colour token of the fitted curve."""
        return FIT_COLOURS[self.fit_colour][1]

    @property
    def tick_role(self) -> str:
        """The type role of the tick labels."""
        return TEXT_SIZES[self.text_size][1]

    @property
    def title_role(self) -> str:
        """The type role of the axis titles."""
        return TEXT_SIZES[self.text_size][2]

    def label(self, name: str) -> str:
        """The label of the choice field *name* holds, as its menu shows it."""
        return menu(name)[getattr(self, name)][0]

    # ── Files ──────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, str]:
        """The appearance as written into a results file and the preferences: field → key."""
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, d: object) -> PlotAppearance:
        """The appearance *d* records (:meth:`to_dict`).

        A field it does not name keeps the built-in choice. Raises ``ValueError``, in words
        for the user, on anything else: not a record of fields, a field this version has
        not got, or a choice its menu does not offer.
        """
        if not isinstance(d, dict):
            raise ValueError('The plot appearance holds no settings this version can read.')
        unknown = sorted(str(k) for k in d if k not in _MENUS)
        if unknown:
            raise ValueError(f'The plot appearance names settings this version does not have: {", ".join(unknown)}.')
        return cls(**{k: str(v) for k, v in d.items()})


#: The appearance a session starts from when no other is stored.
BUILT_IN = PlotAppearance()


def badge(current: PlotAppearance) -> str:
    """The summary beside the title of Plot appearance: whether the plot is drawn as built in."""
    return 'Built-in appearance' if current == BUILT_IN else 'Custom appearance'
