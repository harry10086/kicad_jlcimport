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
DEFAULT_SCALE = 20      # Pixels per mm (KiCad uses mm)
DEFAULT_WIDTH = 300     # SVG canvas width
DEFAULT_HEIGHT = 200    # SVG canvas height


def parse_kicad_sym_to_svg(filepath, scale=DEFAULT_SCALE, width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT):
    """Parse a .kicad_sym file and return SVG markup.

    Args:
        filepath: Path to the .kicad_sym file
        scale: Pixels per mm for scaling
        width: SVG canvas width in pixels
        height: SVG canvas height in pixels

    Returns:
        SVG markup as a string
    """
    with open(filepath) as f:
        content = f.read()

    # Center the drawing in the SVG canvas
    offset_x = width / 2
    offset_y = height / 2

    svg_elements = []

    # Extract symbol name for the title
    name_match = re.search(r'\(symbol "([^"]+)"', content)
    symbol_name = name_match.group(1) if name_match else "Unknown"

    # --- Parse rectangles ---
    # Format: (rectangle (start X1 Y1) (end X2 Y2) ...)
    for m in re.finditer(r'\(rectangle \(start ([\d.-]+) ([\d.-]+)\) \(end ([\d.-]+) ([\d.-]+)\)', content):
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
    # Format: (polyline (pts (xy X1 Y1) (xy X2 Y2) ...) ...)
    polyline_pattern = r'\(polyline\s+\(pts\s+((?:\(xy[\s\d.-]+\)\s*)+)\)'
    for m in re.finditer(polyline_pattern, content):
        pts_str = m.group(1)
        points = re.findall(r'\(xy ([\d.-]+) ([\d.-]+)\)', pts_str)
        if points:
            # Build SVG path: M = move to first point, L = line to subsequent points
            path_parts = []
            for i, (x, y) in enumerate(points):
                x_svg = float(x) * scale + offset_x
                y_svg = -float(y) * scale + offset_y  # Flip Y
                cmd = "M" if i == 0 else "L"
                path_parts.append(f"{cmd} {x_svg} {y_svg}")
            path_d = " ".join(path_parts)
            svg_elements.append(
                f'<path d="{path_d}" fill="none" stroke="darkgreen" stroke-width="2"/>'
            )

    # --- Parse arcs ---
    # Format: (arc (start SX SY) (mid MX MY) (end EX EY) ...)
    # KiCad uses start/mid/end points; we approximate with quadratic bezier
    for m in re.finditer(
        r'\(arc \(start ([\d.-]+) ([\d.-]+)\) \(mid ([\d.-]+) ([\d.-]+)\) \(end ([\d.-]+) ([\d.-]+)\)',
        content
    ):
        sx, sy, mx, my, ex, ey = [float(g) for g in m.groups()]
        # Convert to SVG coordinates
        sx_svg = sx * scale + offset_x
        sy_svg = -sy * scale + offset_y
        mx_svg = mx * scale + offset_x
        my_svg = -my * scale + offset_y
        ex_svg = ex * scale + offset_x
        ey_svg = -ey * scale + offset_y
        # Quadratic bezier: Q control_point end_point
        # Using midpoint as control gives a reasonable approximation
        svg_elements.append(
            f'<path d="M {sx_svg} {sy_svg} Q {mx_svg} {my_svg} {ex_svg} {ey_svg}" '
            f'fill="none" stroke="darkgreen" stroke-width="2"/>'
        )

    # --- Parse circles ---
    # Format: (circle (center CX CY) (radius R) ...)
    for m in re.finditer(r'\(circle \(center ([\d.-]+) ([\d.-]+)\) \(radius ([\d.-]+)\)', content):
        cx, cy, r = float(m.group(1)), float(m.group(2)), float(m.group(3))
        cx_svg = cx * scale + offset_x
        cy_svg = -cy * scale + offset_y
        r_svg = r * scale
        svg_elements.append(
            f'<circle cx="{cx_svg}" cy="{cy_svg}" r="{r_svg}" '
            f'fill="none" stroke="darkgreen" stroke-width="2"/>'
        )

    # --- Parse pins ---
    # Format: (pin TYPE STYLE (at X Y ROTATION) (length LEN) ... (number "N") ...)
    for m in re.finditer(
        r'\(pin \w+ line \(at ([\d.-]+) ([\d.-]+) ([\d.-]+)\) \(length ([\d.-]+)\)',
        content
    ):
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
            f'<line x1="{px_svg}" y1="{py_svg}" x2="{end_x_svg}" y2="{end_y_svg}" '
            f'stroke="red" stroke-width="2"/>'
        )
        # Draw connection point (circle at pin origin)
        svg_elements.append(f'<circle cx="{px_svg}" cy="{py_svg}" r="4" fill="red"/>')

        # Find and display pin number
        # Look for (number "N") after this pin's (at ...) clause
        pin_num_match = re.search(
            rf'\(pin \w+ line \(at {re.escape(m.group(1))} {re.escape(m.group(2))} '
            rf'{re.escape(m.group(3))}\).*?\(number "([^"]+)"',
            content,
            re.DOTALL
        )
        if pin_num_match:
            svg_elements.append(
                f'<text x="{px_svg}" y="{py_svg - 10}" text-anchor="middle" '
                f'font-size="12" fill="red">{pin_num_match.group(1)}</text>'
            )

    # Assemble final SVG
    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="white"/>
  <text x="{width/2}" y="15" text-anchor="middle" font-size="10" fill="black">{symbol_name}</text>
  {chr(10).join(svg_elements)}
</svg>'''
    return svg


def main():
    parser = argparse.ArgumentParser(
        description="Convert KiCad symbol (.kicad_sym) to SVG for debugging"
    )
    parser.add_argument("input", help="Input .kicad_sym file")
    parser.add_argument("output", nargs="?", help="Output .svg file (default: stdout)")
    parser.add_argument("--scale", type=float, default=DEFAULT_SCALE,
                        help=f"Pixels per mm (default: {DEFAULT_SCALE})")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH,
                        help=f"SVG width in pixels (default: {DEFAULT_WIDTH})")
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT,
                        help=f"SVG height in pixels (default: {DEFAULT_HEIGHT})")

    args = parser.parse_args()

    svg = parse_kicad_sym_to_svg(args.input, args.scale, args.width, args.height)

    if args.output:
        Path(args.output).write_text(svg)
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(svg)


if __name__ == "__main__":
    main()
