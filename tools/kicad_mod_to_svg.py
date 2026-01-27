#!/usr/bin/env python3
"""Convert a KiCad footprint (.kicad_mod) to SVG for visual debugging.

This tool parses a KiCad footprint file and generates an SVG preview, useful for
verifying that footprint imports are rendering correctly without opening KiCad.

Usage:
    python kicad_mod_to_svg.py <input.kicad_mod> [output.svg]

If output.svg is not specified, SVG is written to stdout.

Supported elements:
    - Pads (SMD, through-hole, NPTH) with various shapes
    - Lines (fp_line)
    - Circles (fp_circle)
    - Arcs (fp_arc)
    - Polygons (fp_poly)
    - Text/properties

Layer colors:
    - F.Cu (front copper): Red
    - B.Cu (back copper): Blue
    - F.SilkS (front silkscreen): Yellow/Gold
    - B.SilkS (back silkscreen): Magenta
    - Edge.Cuts: Magenta (dashed)
    - F.Fab: Gray
    - Pads: Light copper with darker outline
    - Drill holes: White with dark outline
"""

import argparse
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Display settings
DEFAULT_SCALE = 40  # Pixels per mm (footprints are often small)
DEFAULT_PADDING = 30  # Padding around content in pixels

# Layer colors (mimicking KiCad's color scheme)
LAYER_COLORS: Dict[str, str] = {
    "F.Cu": "#840000",  # Dark red for front copper
    "B.Cu": "#000084",  # Dark blue for back copper
    "F.SilkS": "#C4A000",  # Gold/yellow for front silkscreen
    "B.SilkS": "#840084",  # Magenta for back silkscreen
    "F.Paste": "#808080",  # Gray for paste
    "B.Paste": "#404040",  # Dark gray
    "F.Mask": "#840084",  # Purple for mask
    "B.Mask": "#840084",
    "Edge.Cuts": "#C4C400",  # Yellow for board outline
    "F.Fab": "#808080",  # Gray for fab
    "B.Fab": "#606060",
    "F.CrtYd": "#C0C0C0",  # Light gray for courtyard
    "B.CrtYd": "#A0A0A0",
    "User.1": "#0000FF",
    "User.2": "#00FF00",
}

PAD_FILL_COLOR = "#C87533"  # Copper color
PAD_STROKE_COLOR = "#8B4513"  # Darker copper outline
DRILL_FILL_COLOR = "#FFFFFF"  # White for drill holes
DRILL_STROKE_COLOR = "#333333"  # Dark outline


@dataclass
class BoundingBox:
    """Track min/max coordinates for auto-fitting."""

    min_x: float = float("inf")
    min_y: float = float("inf")
    max_x: float = float("-inf")
    max_y: float = float("-inf")

    def extend(self, x: float, y: float):
        self.min_x = min(self.min_x, x)
        self.min_y = min(self.min_y, y)
        self.max_x = max(self.max_x, x)
        self.max_y = max(self.max_y, y)

    def extend_rect(self, cx: float, cy: float, w: float, h: float, rotation: float = 0):
        """Extend to include rotated rectangle centered at (cx, cy)."""
        hw, hh = w / 2, h / 2
        corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
        if rotation != 0:
            rad = math.radians(rotation)
            cos_r, sin_r = math.cos(rad), math.sin(rad)
            corners = [(x * cos_r - y * sin_r, x * sin_r + y * cos_r) for x, y in corners]
        for dx, dy in corners:
            self.extend(cx + dx, cy + dy)

    def extend_circle(self, cx: float, cy: float, r: float):
        self.extend(cx - r, cy - r)
        self.extend(cx + r, cy + r)

    @property
    def width(self) -> float:
        return self.max_x - self.min_x if self.max_x > self.min_x else 0

    @property
    def height(self) -> float:
        return self.max_y - self.min_y if self.max_y > self.min_y else 0

    @property
    def center(self) -> Tuple[float, float]:
        return ((self.min_x + self.max_x) / 2, (self.min_y + self.max_y) / 2)


@dataclass
class ParsedPad:
    number: str
    pad_type: str  # smd, thru_hole, np_thru_hole
    shape: str  # rect, oval, circle, roundrect, custom
    x: float
    y: float
    width: float
    height: float
    rotation: float = 0
    drill: float = 0
    layers: List[str] = field(default_factory=list)
    roundrect_ratio: float = 0.25  # Default KiCad roundrect ratio


@dataclass
class ParsedLine:
    x1: float
    y1: float
    x2: float
    y2: float
    width: float
    layer: str


@dataclass
class ParsedCircle:
    cx: float
    cy: float
    radius: float
    width: float
    layer: str
    fill: bool = False


@dataclass
class ParsedArc:
    start: Tuple[float, float]
    mid: Tuple[float, float]
    end: Tuple[float, float]
    width: float
    layer: str


@dataclass
class ParsedPoly:
    points: List[Tuple[float, float]]
    width: float
    layer: str
    fill: bool = False


@dataclass
class ParsedText:
    text: str
    x: float
    y: float
    rotation: float
    layer: str
    font_size: float = 1.0
    visible: bool = True


@dataclass
class ParsedFootprint:
    """Container for all parsed footprint elements."""

    name: str = "Unknown"
    pads: List[ParsedPad] = field(default_factory=list)
    lines: List[ParsedLine] = field(default_factory=list)
    circles: List[ParsedCircle] = field(default_factory=list)
    arcs: List[ParsedArc] = field(default_factory=list)
    polys: List[ParsedPoly] = field(default_factory=list)
    texts: List[ParsedText] = field(default_factory=list)


def compute_arc_center_and_radius(
    start: Tuple[float, float], mid: Tuple[float, float], end: Tuple[float, float]
) -> Tuple[Tuple[float, float], float]:
    """Compute center and radius of arc from three points."""
    sx, sy = start
    mx, my = mid
    ex, ey = end

    mid1 = ((sx + mx) / 2, (sy + my) / 2)
    mid2 = ((mx + ex) / 2, (my + ey) / 2)

    d1 = (mx - sx, my - sy)
    d2 = (ex - mx, ey - my)

    perp1 = (-d1[1], d1[0])
    perp2 = (-d2[1], d2[0])

    denom = perp1[0] * perp2[1] - perp1[1] * perp2[0]
    if abs(denom) < 1e-10:
        cx = (sx + ex) / 2
        cy = (sy + ey) / 2
        radius = math.sqrt((ex - sx) ** 2 + (ey - sy) ** 2) / 2
        return (cx, cy), radius

    dx = mid2[0] - mid1[0]
    dy = mid2[1] - mid1[1]
    t = (dx * perp2[1] - dy * perp2[0]) / denom

    cx = mid1[0] + t * perp1[0]
    cy = mid1[1] + t * perp1[1]
    radius = math.sqrt((sx - cx) ** 2 + (sy - cy) ** 2)

    return (cx, cy), radius


def arc_flags(
    start: Tuple[float, float],
    mid: Tuple[float, float],
    end: Tuple[float, float],
    center: Tuple[float, float],
) -> Tuple[int, int]:
    """Compute SVG arc large-arc-flag and sweep-flag."""
    sx, sy = start
    mx, my = mid
    ex, ey = end
    cx, cy = center

    def angle(px, py):
        return math.atan2(py - cy, px - cx)

    start_a = angle(sx, sy)
    mid_a = angle(mx, my)
    end_a = angle(ex, ey)

    def normalize(a):
        while a < 0:
            a += 2 * math.pi
        while a >= 2 * math.pi:
            a -= 2 * math.pi
        return a

    start_a = normalize(start_a)
    mid_a = normalize(mid_a)
    end_a = normalize(end_a)

    # Check if going CCW from start includes mid
    if start_a <= end_a:
        ccw_includes = start_a <= mid_a <= end_a
    else:
        ccw_includes = mid_a >= start_a or mid_a <= end_a

    # Angular span
    if ccw_includes:
        span = end_a - start_a
        if span < 0:
            span += 2 * math.pi
    else:
        span = start_a - end_a
        if span < 0:
            span += 2 * math.pi

    large = 1 if span > math.pi else 0
    sweep = 0 if ccw_includes else 1

    # Flip for SVG Y-down coordinate system
    sweep = 1 - sweep

    return large, sweep


def parse_footprint_content(content: str) -> ParsedFootprint:
    """Parse a .kicad_mod file content into structured data."""
    fp = ParsedFootprint()

    # Extract footprint name
    name_match = re.search(r'\(footprint "([^"]+)"', content)
    fp.name = name_match.group(1) if name_match else "Unknown"

    # --- Parse pads ---
    pad_pattern = (
        r'\(pad\s+"([^"]*)"\s+(\w+)\s+(\w+)\s+'
        r"\(at\s+([\d.-]+)\s+([\d.-]+)\s*([\d.-]*)\)\s+"
        r"\(size\s+([\d.-]+)\s+([\d.-]+)\)"
        r"(.*?)"
        r"\(layers\s+([^)]+)\)"
    )
    for m in re.finditer(pad_pattern, content, re.DOTALL):
        number = m.group(1)
        pad_type = m.group(2)
        shape = m.group(3)
        x, y = float(m.group(4)), float(m.group(5))
        rotation = float(m.group(6)) if m.group(6).strip() else 0
        width, height = float(m.group(7)), float(m.group(8))
        rest = m.group(9)
        layers_str = m.group(10)

        # Parse drill
        drill = 0
        drill_match = re.search(r"\(drill\s+([\d.-]+)", rest)
        if drill_match:
            drill = float(drill_match.group(1))

        # Parse roundrect ratio
        roundrect_ratio = 0.25
        rr_match = re.search(r"\(roundrect_rratio\s+([\d.-]+)", rest)
        if rr_match:
            roundrect_ratio = float(rr_match.group(1))

        # Parse layers
        layers = re.findall(r'"([^"]+)"', layers_str)
        if not layers:
            # Try without quotes (e.g., *.Cu)
            layers = layers_str.strip().split()

        fp.pads.append(
            ParsedPad(
                number=number,
                pad_type=pad_type,
                shape=shape,
                x=x,
                y=y,
                width=width,
                height=height,
                rotation=rotation,
                drill=drill,
                layers=layers,
                roundrect_ratio=roundrect_ratio,
            )
        )

    # --- Parse fp_line ---
    line_pattern = (
        r"\(fp_line\s+"
        r"\(start\s+([\d.-]+)\s+([\d.-]+)\)\s+"
        r"\(end\s+([\d.-]+)\s+([\d.-]+)\)"
        r".*?"
        r"\(stroke\s+\(width\s+([\d.-]+)\)"
        r".*?"
        r'\(layer\s+"([^"]+)"\)'
    )
    for m in re.finditer(line_pattern, content, re.DOTALL):
        fp.lines.append(
            ParsedLine(
                x1=float(m.group(1)),
                y1=float(m.group(2)),
                x2=float(m.group(3)),
                y2=float(m.group(4)),
                width=float(m.group(5)),
                layer=m.group(6),
            )
        )

    # --- Parse fp_circle ---
    circle_pattern = (
        r"\(fp_circle\s+"
        r"\(center\s+([\d.-]+)\s+([\d.-]+)\)\s+"
        r"\(end\s+([\d.-]+)\s+([\d.-]+)\)"
        r"(.*?)"
        r'\(layer\s+"([^"]+)"\)'
    )
    for m in re.finditer(circle_pattern, content, re.DOTALL):
        cx, cy = float(m.group(1)), float(m.group(2))
        end_x, end_y = float(m.group(3)), float(m.group(4))
        rest = m.group(5)
        layer = m.group(6)

        # Radius is distance from center to end point
        radius = math.sqrt((end_x - cx) ** 2 + (end_y - cy) ** 2)

        # Parse stroke width
        width_match = re.search(r"\(stroke\s+\(width\s+([\d.-]+)\)", rest)
        width = float(width_match.group(1)) if width_match else 0.15

        # Check for fill
        fill = bool(re.search(r"\(fill\s+solid\)", rest))

        fp.circles.append(ParsedCircle(cx=cx, cy=cy, radius=radius, width=width, layer=layer, fill=fill))

    # --- Parse fp_arc ---
    arc_pattern = (
        r"\(fp_arc\s+"
        r"\(start\s+([\d.-]+)\s+([\d.-]+)\)\s+"
        r"\(mid\s+([\d.-]+)\s+([\d.-]+)\)\s+"
        r"\(end\s+([\d.-]+)\s+([\d.-]+)\)"
        r"(.*?)"
        r'\(layer\s+"([^"]+)"\)'
    )
    for m in re.finditer(arc_pattern, content, re.DOTALL):
        sx, sy = float(m.group(1)), float(m.group(2))
        mx, my = float(m.group(3)), float(m.group(4))
        ex, ey = float(m.group(5)), float(m.group(6))
        rest = m.group(7)
        layer = m.group(8)

        width_match = re.search(r"\(stroke\s+\(width\s+([\d.-]+)\)", rest)
        width = float(width_match.group(1)) if width_match else 0.15

        fp.arcs.append(ParsedArc(start=(sx, sy), mid=(mx, my), end=(ex, ey), width=width, layer=layer))

    # --- Parse fp_poly ---
    poly_pattern = r"\(fp_poly\s+\(pts\s+((?:\(xy\s+[\d.-]+\s+[\d.-]+\)\s*)+)\)(.*?)\(layer\s+\"([^\"]+)\"\)"
    for m in re.finditer(poly_pattern, content, re.DOTALL):
        pts_str = m.group(1)
        rest = m.group(2)
        layer = m.group(3)

        points = [(float(x), float(y)) for x, y in re.findall(r"\(xy\s+([\d.-]+)\s+([\d.-]+)\)", pts_str)]

        width_match = re.search(r"\(stroke\s+\(width\s+([\d.-]+)\)", rest)
        width = float(width_match.group(1)) if width_match else 0

        fill = bool(re.search(r"\(fill\s+solid\)", rest))

        if points:
            fp.polys.append(ParsedPoly(points=points, width=width, layer=layer, fill=fill))

    # --- Parse property/text ---
    prop_pattern = (
        r'\(property\s+"([^"]+)"\s+"([^"]*)"\s+'
        r"\(at\s+([\d.-]+)\s+([\d.-]+)\s*([\d.-]*)\)\s+"
        r'\(layer\s+"([^"]+)"\)'
        r"(.*?)"
        r"\)"
    )
    for m in re.finditer(prop_pattern, content, re.DOTALL):
        prop_name = m.group(1)
        prop_value = m.group(2)
        x, y = float(m.group(3)), float(m.group(4))
        rotation = float(m.group(5)) if m.group(5).strip() else 0
        layer = m.group(6)
        rest = m.group(7)

        # Display property name for Reference/Value, otherwise value
        text = prop_value if prop_name in ("Reference", "Value") else prop_name

        # Check visibility
        visible = "hide yes" not in rest

        # Parse font size
        font_match = re.search(r"\(font\s+\(size\s+([\d.-]+)\s+([\d.-]+)\)", rest)
        font_size = float(font_match.group(1)) if font_match else 1.0

        if visible:
            fp.texts.append(ParsedText(text=text, x=x, y=y, rotation=rotation, layer=layer, font_size=font_size))

    return fp


def compute_bounding_box(fp: ParsedFootprint) -> BoundingBox:
    """Compute the bounding box of all footprint elements."""
    bbox = BoundingBox()

    for pad in fp.pads:
        bbox.extend_rect(pad.x, pad.y, pad.width, pad.height, pad.rotation)

    for line in fp.lines:
        bbox.extend(line.x1, line.y1)
        bbox.extend(line.x2, line.y2)

    for circle in fp.circles:
        bbox.extend_circle(circle.cx, circle.cy, circle.radius)

    for arc in fp.arcs:
        bbox.extend(*arc.start)
        bbox.extend(*arc.mid)
        bbox.extend(*arc.end)

    for poly in fp.polys:
        for x, y in poly.points:
            bbox.extend(x, y)

    return bbox


def get_layer_color(layer: str) -> str:
    """Get color for a layer."""
    return LAYER_COLORS.get(layer, "#888888")


def render_pad_shape(pad: ParsedPad, scale: float, offset_x: float, offset_y: float) -> Tuple[str, Optional[str]]:
    """Render a pad shape and return (pad_svg, drill_svg)."""
    cx = pad.x * scale + offset_x
    cy = pad.y * scale + offset_y  # Y not flipped for footprints (already in correct orientation)
    w = pad.width * scale
    h = pad.height * scale

    transform = ""
    if pad.rotation != 0:
        transform = f' transform="rotate({pad.rotation} {cx:.2f} {cy:.2f})"'

    pad_svg = ""
    if pad.shape == "circle":
        r = w / 2
        pad_svg = (
            f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" '
            f'fill="{PAD_FILL_COLOR}" stroke="{PAD_STROKE_COLOR}" stroke-width="1"{transform}/>'
        )
    elif pad.shape == "oval":
        rx, ry = w / 2, h / 2
        pad_svg = (
            f'<ellipse cx="{cx:.2f}" cy="{cy:.2f}" rx="{rx:.2f}" ry="{ry:.2f}" '
            f'fill="{PAD_FILL_COLOR}" stroke="{PAD_STROKE_COLOR}" stroke-width="1"{transform}/>'
        )
    elif pad.shape == "roundrect":
        r = min(w, h) * pad.roundrect_ratio / 2
        x = cx - w / 2
        y = cy - h / 2
        pad_svg = (
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
            f'rx="{r:.2f}" ry="{r:.2f}" '
            f'fill="{PAD_FILL_COLOR}" stroke="{PAD_STROKE_COLOR}" stroke-width="1"{transform}/>'
        )
    else:  # rect or default
        x = cx - w / 2
        y = cy - h / 2
        pad_svg = (
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
            f'fill="{PAD_FILL_COLOR}" stroke="{PAD_STROKE_COLOR}" stroke-width="1"{transform}/>'
        )

    # Drill hole
    drill_svg = None
    if pad.drill > 0:
        drill_r = pad.drill * scale / 2
        drill_svg = (
            f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{drill_r:.2f}" '
            f'fill="{DRILL_FILL_COLOR}" stroke="{DRILL_STROKE_COLOR}" stroke-width="1"/>'
        )

    return pad_svg, drill_svg


def render_svg(
    fp: ParsedFootprint,
    scale: float = DEFAULT_SCALE,
    padding: float = DEFAULT_PADDING,
    show_layers: Optional[List[str]] = None,
) -> str:
    """Render parsed footprint to SVG markup."""
    bbox = compute_bounding_box(fp)

    # Calculate canvas size
    content_width = bbox.width * scale
    content_height = bbox.height * scale
    width = max(content_width + 2 * padding, 100)
    height = max(content_height + 2 * padding + 20, 80)

    # Center offset
    cx, cy = bbox.center
    offset_x = width / 2 - cx * scale
    offset_y = height / 2 - cy * scale

    svg_elements = []

    # Layer filter
    def should_render(layer: str) -> bool:
        if show_layers is None:
            return True
        return any(lyr in layer for lyr in show_layers)

    # --- Render polygons (background) ---
    for poly in fp.polys:
        if not should_render(poly.layer):
            continue
        if not poly.points:
            continue

        points_str = " ".join(f"{x * scale + offset_x:.2f},{y * scale + offset_y:.2f}" for x, y in poly.points)
        color = get_layer_color(poly.layer)
        fill = color if poly.fill else "none"
        stroke_w = poly.width * scale if poly.width > 0 else 1

        svg_elements.append(
            f'<polygon points="{points_str}" fill="{fill}" '
            f'stroke="{color}" stroke-width="{stroke_w:.2f}" fill-opacity="0.5"/>'
        )

    # --- Render lines ---
    for line in fp.lines:
        if not should_render(line.layer):
            continue

        x1 = line.x1 * scale + offset_x
        y1 = line.y1 * scale + offset_y
        x2 = line.x2 * scale + offset_x
        y2 = line.y2 * scale + offset_y
        color = get_layer_color(line.layer)
        stroke_w = max(line.width * scale, 1)

        dash = ""
        if "Edge.Cuts" in line.layer:
            dash = ' stroke-dasharray="4,2"'

        svg_elements.append(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke="{color}" stroke-width="{stroke_w:.2f}"{dash}/>'
        )

    # --- Render circles ---
    for circle in fp.circles:
        if not should_render(circle.layer):
            continue

        cx_svg = circle.cx * scale + offset_x
        cy_svg = circle.cy * scale + offset_y
        r = circle.radius * scale
        color = get_layer_color(circle.layer)
        stroke_w = max(circle.width * scale, 1)
        fill = color if circle.fill else "none"

        svg_elements.append(
            f'<circle cx="{cx_svg:.2f}" cy="{cy_svg:.2f}" r="{r:.2f}" '
            f'fill="{fill}" stroke="{color}" stroke-width="{stroke_w:.2f}" fill-opacity="0.5"/>'
        )

    # --- Render arcs ---
    for arc in fp.arcs:
        if not should_render(arc.layer):
            continue

        sx = arc.start[0] * scale + offset_x
        sy = arc.start[1] * scale + offset_y
        ex = arc.end[0] * scale + offset_x
        ey = arc.end[1] * scale + offset_y

        center, radius = compute_arc_center_and_radius(arc.start, arc.mid, arc.end)
        r_svg = radius * scale
        large, sweep = arc_flags(arc.start, arc.mid, arc.end, center)

        color = get_layer_color(arc.layer)
        stroke_w = max(arc.width * scale, 1)

        svg_elements.append(
            f'<path d="M {sx:.2f} {sy:.2f} A {r_svg:.2f} {r_svg:.2f} 0 {large} {sweep} {ex:.2f} {ey:.2f}" '
            f'fill="none" stroke="{color}" stroke-width="{stroke_w:.2f}"/>'
        )

    # --- Render pads ---
    drill_elements = []  # Render drills on top of pads
    pad_labels = []

    for pad in fp.pads:
        pad_svg, drill_svg = render_pad_shape(pad, scale, offset_x, offset_y)
        svg_elements.append(pad_svg)
        if drill_svg:
            drill_elements.append(drill_svg)

        # Pad number label
        if pad.number:
            px = pad.x * scale + offset_x
            py = pad.y * scale + offset_y
            font_size = min(pad.width, pad.height) * scale * 0.5
            font_size = max(font_size, 8)
            font_size = min(font_size, 14)
            pad_labels.append(
                f'<text x="{px:.2f}" y="{py + font_size / 3:.2f}" text-anchor="middle" '
                f'font-size="{font_size:.1f}" font-family="monospace" fill="white" '
                f'font-weight="bold">{pad.number}</text>'
            )

    svg_elements.extend(drill_elements)
    svg_elements.extend(pad_labels)

    # --- Render text ---
    for text in fp.texts:
        if not should_render(text.layer):
            continue

        tx = text.x * scale + offset_x
        ty = text.y * scale + offset_y
        font_size = text.font_size * scale
        color = get_layer_color(text.layer)

        transform = ""
        if text.rotation != 0:
            transform = f' transform="rotate({text.rotation} {tx:.2f} {ty:.2f})"'

        svg_elements.append(
            f'<text x="{tx:.2f}" y="{ty:.2f}" text-anchor="middle" '
            f'font-size="{font_size:.1f}" font-family="sans-serif" fill="{color}"{transform}>'
            f"{text.text}</text>"
        )

    # Assemble final SVG
    title_y = 15
    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}">
  <rect width="100%" height="100%" fill="#1a1a2e"/>
  <text x="{width / 2:.0f}" y="{title_y}" text-anchor="middle" font-size="12" font-family="sans-serif" fill="white">{fp.name}</text>
  {chr(10).join("  " + e for e in svg_elements)}
</svg>'''
    return svg


def parse_kicad_mod_to_svg(
    filepath,
    scale=DEFAULT_SCALE,
    show_layers: Optional[List[str]] = None,
) -> str:
    """Parse a .kicad_mod file and return SVG markup."""
    with open(filepath) as f:
        content = f.read()

    fp = parse_footprint_content(content)
    return render_svg(fp, scale=scale, show_layers=show_layers)


def main():
    parser = argparse.ArgumentParser(description="Convert KiCad footprint (.kicad_mod) to SVG for debugging")
    parser.add_argument("input", help="Input .kicad_mod file")
    parser.add_argument("output", nargs="?", help="Output .svg file (default: stdout)")
    parser.add_argument(
        "--scale",
        type=float,
        default=DEFAULT_SCALE,
        help=f"Pixels per mm (default: {DEFAULT_SCALE})",
    )
    parser.add_argument(
        "--layers",
        type=str,
        default=None,
        help="Comma-separated list of layers to show (e.g., 'F.Cu,F.SilkS')",
    )

    args = parser.parse_args()

    layers = args.layers.split(",") if args.layers else None
    svg = parse_kicad_mod_to_svg(args.input, args.scale, layers)

    if args.output:
        Path(args.output).write_text(svg)
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(svg)


if __name__ == "__main__":
    main()
