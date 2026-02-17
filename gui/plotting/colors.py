"""Color constants and helpers for the plotting module."""

from __future__ import annotations

# 8-color cycle for active replicas (RGB)
REPLICA_PALETTE: list[tuple[int, int, int]] = [
    (31, 119, 180),   # blue
    (255, 127, 14),   # orange
    (44, 160, 44),    # green
    (214, 39, 40),    # red
    (148, 103, 189),  # purple
    (140, 86, 75),    # brown
    (227, 119, 194),  # pink
    (127, 127, 127),  # grey
]

# Fit curve colors (distinct from replica palette)
FIT_PALETTE: list[tuple[int, int, int]] = [
    (23, 190, 207),   # cyan
    (188, 189, 34),   # yellow-green
    (174, 199, 232),  # light blue
    (255, 187, 120),  # light orange
]

DROPPED_REPLICA_COLOR: tuple[int, int, int] = (180, 180, 180)
AVERAGE_LINE_COLOR: tuple[int, int, int] = (0, 0, 0)
ERROR_BAR_COLOR: tuple[int, int, int] = (80, 80, 80)

BACKGROUND_COLOR = "w"
FOREGROUND_COLOR = "k"


def rgba(rgb: tuple[int, int, int], alpha: int = 255) -> tuple[int, int, int, int]:
    """Return an RGBA tuple from an RGB tuple and optional alpha.

    Parameters
    ----------
    rgb : tuple[int, int, int]
        Red, green, blue values (0–255).
    alpha : int
        Alpha value (0–255), default 255 (fully opaque).

    Returns
    -------
    tuple[int, int, int, int]
    """
    return (rgb[0], rgb[1], rgb[2], alpha)
