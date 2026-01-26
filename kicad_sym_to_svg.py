#!/usr/bin/env python3
"""Convert a KiCad symbol (.kicad_sym) to SVG for visual debugging.

This tool parses a KiCad symbol file and generates an SVG preview, useful for
verifying that symbol imports are rendering correctly without opening KiCad.

Usage:
    python kicad_sym_to_svg.py <input.kicad_sym> [output.svg]

If output.svg is not specified, SVG is written to stdout.

Supported elements:
    - Rectangles
    - Polylines (line segments)
    - Arcs (rendered as quadratic bezier approximations)
    - Pins (with connection points and pin numbers)

Colors:
    - Green: Symbol graphics (rectangles, lines, arcs)
    - Red: Pins and connection points
"""

import argparse
import math
import re
import sys
from pathlib import Path

# Display settings
DEFAULT_SCALE = 20  # Pixels per mm (KiCad uses mm)
DEFAULT_PADDING = 40  # Padding around content in pixels


def _compute_bounding_box(content, scale):
    """Compute bounding box of all elements in KiCad coordinates."""
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")

    def extend(x, y):
        nonlocal min_x, min_y, max_x, max_y
        min_x = min(min_x, x)
        min_y = min(min_y, y)
        max_x = max(max_x, x)
        max_y = max(max_y, y)

    # Rectangles
    for m in re.finditer(r"\(rectangle \(start ([\d.-]+) ([\d.-]+)\) \(end ([\d.-]+) ([\d.-]+)\)", content):
        extend(float(m.group(1)), float(m.group(2)))
        extend(float(m.group(3)), float(m.group(4)))

    # Polylines
    for m in re.finditer(r"\(polyline\s+\(pts\s+((?:\(xy[\s\d.-]+\)\s*)+)\)", content):
        for px, py in re.findall(r"\(xy ([\d.-]+) ([\d.-]+)\)", m.group(1)):
            extend(float(px), float(py))

    # Arcs
    for m in re.finditer(
        r"\(arc \(start ([\d.-]+) ([\d.-]+)\) \(mid ([\d.-]+) ([\d.-]+)\) \(end ([\d.-]+) ([\d.-]+)\)", content
    ):
        for i in range(0, 6, 2):
            extend(float(m.group(i + 1)), float(m.group(i + 2)))

    # Circles
    for m in re.finditer(r"\(circle \(center ([\d.-]+) ([\d.-]+)\) \(radius ([\d.-]+)\)", content):
        cx, cy, r = float(m.group(1)), float(m.group(2)), float(m.group(3))
        extend(cx - r, cy - r)
        extend(cx + r, cy + r)

    # Pins
    for m in re.finditer(r"\(pin \w+ line \(at ([\d.-]+) ([\d.-]+) ([\d.-]+)\) \(length ([\d.-]+)\)", content):
        px, py = float(m.group(1)), float(m.group(2))
        rotation = float(m.group(3))
        length = float(m.group(4))
        extend(px, py)
        rad = math.radians(rotation)
        extend(px + length * math.cos(rad), py + length * math.sin(rad))

    if min_x == float("inf"):
        return 0, 0, 300, 200  # Fallback

    return min_x, min_y, max_x, max_y


def parse_kicad_sym_to_svg(filepath, scale=DEFAULT_SCALE, width=None, height=None):
    """Parse a .kicad_sym file and return SVG markup.

    Args:
        filepath: Path to the .kicad_sym file
        scale: Pixels per mm for scaling
        width: SVG canvas width in pixels (None = auto-fit)
        height: SVG canvas height in pixels (None = auto-fit)

    Returns:
        SVG markup as a string
    """
    with open(filepath) as f:
        content = f.read()

    # Compute bounding box and auto-fit canvas
    min_x, min_y, max_x, max_y = _compute_bounding_box(content, scale)
    content_width = (max_x - min_x) * scale
    content_height = (max_y - min_y) * scale

    if width is None:
        width = max(content_width + 2 * DEFAULT_PADDING, 150)
    if height is None:
        height = max(content_height + 2 * DEFAULT_PADDING + 20, 100)  # +20 for title

    # Center the drawing based on content center
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2
    offset_x = width / 2 - center_x * scale
    offset_y = height / 2 + center_y * scale  # Flip Y

    svg_elements = []

    # Extract symbol name for the title
    name_match = re.search(r'\(symbol "([^"]+)"', content)
    symbol_name = name_match.group(1) if name_match else "Unknown"

    # --- Parse rectangles ---
    # Format: (rectangle (start X1 Y1) (end X2 Y2) ...)
    for m in re.finditer(r"\(rectangle \(start ([\d.-]+) ([\d.-]+)\) \(end ([\d.-]+) ([\d.-]+)\)", content):
        x1, y1, x2, y2 = float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4))
        # Convert to SVG coordinates (Y is flipped: KiCad Y+ is up, SVG Y+ is down)
        x1_svg = x1 * scale + offset_x
        y1_svg = -y1 * scale + offset_y
        x2_svg = x2 * scale + offset_x
        y2_svg = -y2 * scale + offset_y
        # SVG rect needs top-left corner and positive width/height
        svg_elements.append(
            f'<rect x="{min(x1_svg, x2_svg)}" y="{min(y1_svg, y2_svg)}" '
            f'width="{abs(x2_svg - x1_svg)}" height="{abs(y2_svg - y1_svg)}" '
            f'fill="none" stroke="darkgreen" stroke-width="2"/>'
        )

    # --- Parse polylines ---
    # Format: (polyline (pts ...) (stroke ...) (fill (type TYPE)))
    for m in re.finditer(r"\(polyline\s+(.*?)\n\s*\)", content, re.DOTALL):
        block = m.group(1)
        pts_match = re.search(r"\(pts\s+((?:\(xy[\s\d.-]+\)\s*)+)\)", block)
        if not pts_match:
            continue
        points = re.findall(r"\(xy ([\d.-]+) ([\d.-]+)\)", pts_match.group(1))
        if not points:
            continue
        # Check fill type
        fill_match = re.search(r"\(fill \(type (\w+)\)\)", block)
        fill_type = fill_match.group(1) if fill_match else "none"
        # Build SVG path
        path_parts = []
        for i, (x, y) in enumerate(points):
            x_svg = float(x) * scale + offset_x
            y_svg = -float(y) * scale + offset_y  # Flip Y
            cmd = "M" if i == 0 else "L"
            path_parts.append(f"{cmd} {x_svg} {y_svg}")
        path_d = " ".join(path_parts)
        # Fill with stroke color if fill type is "outline" or "background"
        fill_attr = "darkgreen" if fill_type in ("outline", "background") else "none"
        svg_elements.append(f'<path d="{path_d}" fill="{fill_attr}" stroke="darkgreen" stroke-width="2"/>')

    # --- Parse arcs ---
    # Format: (arc (start SX SY) (mid MX MY) (end EX EY) ...)
    # KiCad uses start/mid/end points; we use quadratic bezier with computed control point
    for m in re.finditer(
        r"\(arc \(start ([\d.-]+) ([\d.-]+)\) \(mid ([\d.-]+) ([\d.-]+)\) \(end ([\d.-]+) ([\d.-]+)\)", content
    ):
        sx, sy, mx, my, ex, ey = [float(g) for g in m.groups()]

        # For a quadratic bezier to pass through mid at t=0.5, the control point must be:
        # control = 2*mid - (start + end)/2
        ctrl_x = 2 * mx - (sx + ex) / 2
        ctrl_y = 2 * my - (sy + ey) / 2

        # Convert to SVG coordinates
        sx_svg = sx * scale + offset_x
        sy_svg = -sy * scale + offset_y
        ctrl_x_svg = ctrl_x * scale + offset_x
        ctrl_y_svg = -ctrl_y * scale + offset_y
        ex_svg = ex * scale + offset_x
        ey_svg = -ey * scale + offset_y

        svg_elements.append(
            f'<path d="M {sx_svg} {sy_svg} Q {ctrl_x_svg} {ctrl_y_svg} {ex_svg} {ey_svg}" '
            f'fill="none" stroke="darkgreen" stroke-width="2"/>'
        )

    # --- Parse circles ---
    # Format: (circle (center CX CY) (radius R) ...)
    for m in re.finditer(r"\(circle \(center ([\d.-]+) ([\d.-]+)\) \(radius ([\d.-]+)\)", content):
        cx, cy, r = float(m.group(1)), float(m.group(2)), float(m.group(3))
        cx_svg = cx * scale + offset_x
        cy_svg = -cy * scale + offset_y
        r_svg = r * scale
        svg_elements.append(
            f'<circle cx="{cx_svg}" cy="{cy_svg}" r="{r_svg}" fill="none" stroke="darkgreen" stroke-width="2"/>'
        )

    # --- Parse pins ---
    # Format: (pin TYPE STYLE (at X Y ROTATION) (length LEN) ... (number "N") ...)
    for m in re.finditer(r"\(pin \w+ line \(at ([\d.-]+) ([\d.-]+) ([\d.-]+)\) \(length ([\d.-]+)\)", content):
        px, py = float(m.group(1)), float(m.group(2))
        rotation = float(m.group(3))  # Degrees
        length = float(m.group(4))

        # Pin origin (connection point) in SVG coords
        px_svg = px * scale + offset_x
        py_svg = -py * scale + offset_y

        # Calculate pin end point based on rotation
        # Rotation 0 = pin extends right, 90 = up, 180 = left, 270 = down
        rad = math.radians(rotation)
        end_x = px + length * math.cos(rad)
        end_y = py + length * math.sin(rad)
        end_x_svg = end_x * scale + offset_x
        end_y_svg = -end_y * scale + offset_y

        # Draw pin line
        svg_elements.append(
            f'<line x1="{px_svg}" y1="{py_svg}" x2="{end_x_svg}" y2="{end_y_svg}" stroke="red" stroke-width="2"/>'
        )
        # Draw connection point (circle at pin origin)
        svg_elements.append(f'<circle cx="{px_svg}" cy="{py_svg}" r="4" fill="red"/>')

        # Find pin number and name
        # Look for (name "N") and (number "N") after this pin's (at ...) clause
        pin_match = re.search(
            rf"\(pin \w+ line \(at {re.escape(m.group(1))} {re.escape(m.group(2))} "
            rf'{re.escape(m.group(3))}\).*?\(name "([^"]+)".*?\(number "([^"]+)"',
            content,
            re.DOTALL,
        )
        if pin_match:
            pin_name = pin_match.group(1)
            pin_number = pin_match.group(2)
            # Pin number near connection point
            svg_elements.append(
                f'<text x="{px_svg}" y="{py_svg - 10}" text-anchor="middle" '
                f'font-size="10" fill="red">{pin_number}</text>'
            )
            # Pin name near the end of pin (inside symbol body)
            # Position depends on pin rotation
            name_offset = 8  # pixels from pin end
            if rotation == 0:  # pin extends right, name to right of end
                name_x, name_y = end_x_svg + name_offset, end_y_svg + 4
                anchor = "start"
            elif rotation == 180:  # pin extends left, name to left of end
                name_x, name_y = end_x_svg - name_offset, end_y_svg + 4
                anchor = "end"
            elif rotation == 90:  # pin extends up, name above end
                name_x, name_y = end_x_svg, end_y_svg - name_offset
                anchor = "middle"
            else:  # rotation == 270, pin extends down, name below end
                name_x, name_y = end_x_svg, end_y_svg + name_offset + 8
                anchor = "middle"
            svg_elements.append(
                f'<text x="{name_x}" y="{name_y}" text-anchor="{anchor}" '
                f'font-size="10" fill="darkgreen">{pin_name}</text>'
            )

    # Assemble final SVG
    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="white"/>
  <text x="{width / 2}" y="15" text-anchor="middle" font-size="10" fill="black">{symbol_name}</text>
  {chr(10).join(svg_elements)}
</svg>'''
    return svg


def main():
    parser = argparse.ArgumentParser(description="Convert KiCad symbol (.kicad_sym) to SVG for debugging")
    parser.add_argument("input", help="Input .kicad_sym file")
    parser.add_argument("output", nargs="?", help="Output .svg file (default: stdout)")
    parser.add_argument("--scale", type=float, default=DEFAULT_SCALE, help=f"Pixels per mm (default: {DEFAULT_SCALE})")
    parser.add_argument("--width", type=int, default=None, help="SVG width in pixels (default: auto-fit)")
    parser.add_argument("--height", type=int, default=None, help="SVG height in pixels (default: auto-fit)")

    args = parser.parse_args()

    svg = parse_kicad_sym_to_svg(args.input, args.scale, args.width, args.height)

    if args.output:
        Path(args.output).write_text(svg)
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(svg)


if __name__ == "__main__":
    main()
