"""Image helpers and terminal detection for the TUI."""
from __future__ import annotations

import io
import os

from PIL import Image as PILImage
from textual_image.widget import (
    Image as _AutoTIImage,
    HalfcellImage as _HalfcellTIImage,
    SixelImage as _SixelTIImage,
)

# Warp terminal falsely reports Sixel support via device attributes query,
# so force half-cell rendering there.
# Rio supports Sixel but doesn't advertise it in DA1 response.
_term_program = os.environ.get("TERM_PROGRAM", "")
if _term_program == "WarpTerminal":
    TIImage = _HalfcellTIImage
elif _term_program == "rio":
    TIImage = _SixelTIImage
else:
    TIImage = _AutoTIImage


def pil_from_bytes(data: bytes | None) -> PILImage.Image | None:
    """Convert raw image bytes to a PIL Image, or None."""
    if not data:
        return None
    try:
        return PILImage.open(io.BytesIO(data))
    except Exception:
        return None


def make_skeleton_frame(width: int, height: int, phase: int) -> PILImage.Image:
    """Generate a skeleton shimmer frame as a PIL Image.

    Draws a dark gray rectangle with a lighter band sweeping left to right.
    """
    import math
    from PIL import ImageDraw
    img = PILImage.new("RGB", (width, height), (30, 30, 30))
    draw = ImageDraw.Draw(img)
    band_center = int(phase * (width + width // 2) / 100) - width // 4
    band_width = width // 3
    half_band = band_width // 2
    for x in range(max(0, band_center - half_band), min(width, band_center + half_band)):
        t = abs(x - band_center) / half_band
        boost = int(20 * (1 + math.cos(t * math.pi)) / 2)
        if boost > 0:
            c = 30 + boost
            draw.line([(x, 0), (x, height - 1)], fill=(c, c, c))
    return img
