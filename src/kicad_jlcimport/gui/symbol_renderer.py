"""Render an EasyEDA SVG string as a wx.Bitmap for the detail panel preview."""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET

import wx

try:
    import wx.svg

    _has_svg = True
except (ImportError, ModuleNotFoundError):
    _has_svg = False

# Pattern to extract layerid CSS rules from EasyEDA's <style> block.
# Example: *[layerid="1"] {stroke:#FF0000;fill:#FF0000;}
_CSS_RULE_RE = re.compile(
    r'\*\[layerid="(\d+)"\]\s*\{([^}]+)\}',
)


def _inline_layer_styles(svg: str) -> str:
    """Inline EasyEDA's CSS layerid rules as style attributes.

    nanosvg (used by wx.svg) doesn't support <style> blocks, so we
    extract the CSS rules and apply them directly to matching elements.
    """
    rules: dict[str, str] = {}
    for m in _CSS_RULE_RE.finditer(svg):
        rules[m.group(1)] = m.group(2).strip().rstrip(";")

    if not rules:
        return svg

    # Remove the <style> block so nanosvg doesn't choke on it
    svg = re.sub(r"<style[^>]*>.*?</style>", "", svg, flags=re.DOTALL)

    # Add inline style to elements with layerid="N"
    def _add_style(m: re.Match) -> str:
        tag_content = m.group(0)
        lid_match = re.search(r'layerid="(\d+)"', tag_content)
        if lid_match and lid_match.group(1) in rules:
            css = rules[lid_match.group(1)]
            # Respect fill="none" / stroke="none" attributes — the
            # original CSS has *[fill="none"]{fill:none} rules that
            # override layerid colours for outline-only elements.
            if 'fill="none"' in tag_content:
                css = re.sub(r"fill:[^;]+", "fill:none", css)
            if 'stroke="none"' in tag_content:
                css = re.sub(r"stroke:[^;]+", "stroke:none", css)
            # Append to existing style or add new
            if 'style="' in tag_content:
                return tag_content.replace('style="', f'style="{css};', 1)
            # Insert style before /> (self-closing) or >
            if tag_content.endswith("/>"):
                return tag_content[:-2] + f' style="{css}"/>'
            return tag_content[:-1] + f' style="{css}">'
        return tag_content

    return re.sub(r"<[^/][^>]*layerid=[^>]*>", _add_style, svg)


def has_svg_support() -> bool:
    """Return True if the platform can render SVG via wx.svg."""
    return True  # Always True now — we have fallback renderer


def render_svg_bitmap(svg_string: str, size: int = 160) -> wx.Bitmap | None:
    """Render an SVG string to a wx.Bitmap, scaled to fit *size* x *size*.

    Uses wx.svg if available, otherwise falls back to a custom DC-based
    renderer that handles EasyEDA's SVG subset.
    """
    if _has_svg:
        processed = _inline_layer_styles(svg_string)
        try:
            img = wx.svg.SVGimage.CreateFromBytes(processed.encode("utf-8"))
        except Exception:
            return _render_svg_fallback(svg_string, size)
        if img.width <= 0 or img.height <= 0:
            return _render_svg_fallback(svg_string, size)
        return img.ConvertToScaledBitmap(wx.Size(size, size))

    return _render_svg_fallback(svg_string, size)


# ---------------------------------------------------------------------------
# Fallback SVG renderer — handles EasyEDA's SVG subset using wx.DC
# ---------------------------------------------------------------------------

_SVG_NS = {"svg": "http://www.w3.org/2000/svg"}

_HEX3_RE = re.compile(r"^#([0-9a-fA-F]{3})$")
_HEX6_RE = re.compile(r"^#([0-9a-fA-F]{6})$")


def _parse_colour(raw: str | None, default: wx.Colour = None) -> wx.Colour | None:
    """Parse CSS/SVG colour value to wx.Colour."""
    if not raw or raw.strip().lower() == "none":
        return None
    raw = raw.strip()
    m6 = _HEX6_RE.match(raw)
    if m6:
        h = m6.group(1)
        return wx.Colour(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    m3 = _HEX3_RE.match(raw)
    if m3:
        h = m3.group(1)
        return wx.Colour(int(h[0] * 2, 16), int(h[1] * 2, 16), int(h[2] * 2, 16))
    # Named colours
    named = {
        "black": wx.BLACK,
        "white": wx.WHITE,
        "red": wx.RED,
        "blue": wx.BLUE,
        "green": wx.Colour(0, 128, 0),
        "yellow": wx.YELLOW,
        "gray": wx.Colour(128, 128, 128),
        "grey": wx.Colour(128, 128, 128),
    }
    c = named.get(raw.lower())
    if c:
        return wx.Colour(c) if isinstance(c, wx.Colour) else wx.Colour(c)
    return default


def _css_val(style_str: str | None, key: str) -> str | None:
    """Extract a value from an inline CSS style string, e.g. 'fill:#FF0000;stroke:none'."""
    if not style_str:
        return None
    for part in style_str.split(";"):
        part = part.strip()
        if ":" in part:
            k, v = part.split(":", 1)
            if k.strip() == key:
                return v.strip()
    return None


def _get_style_attr(elem, key: str, default=None):
    """Get an SVG attribute, falling back to inline style."""
    val = elem.get(key)
    if val is not None:
        return val
    return _css_val(elem.get("style"), key) or default


def _flt(val: str | None, default: float = 0.0) -> float:
    """Parse float from SVG attribute."""
    if not val:
        return default
    try:
        return float(val)
    except ValueError:
        return default


def _parse_path_commands(d: str):
    """Very simple SVG path tokenizer — yields (command, [args])."""
    tokens = re.findall(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?[\d.]+(?:[eE][-+]?\d+)?", d)
    cmd = None
    args = []
    for tok in tokens:
        if tok.isalpha() and len(tok) == 1:
            if cmd is not None:
                yield cmd, args
            cmd = tok
            args = []
        else:
            try:
                args.append(float(tok))
            except ValueError:
                pass
    if cmd is not None:
        yield cmd, args


def _render_svg_fallback(svg_string: str, size: int) -> wx.Bitmap | None:
    """Render EasyEDA SVG by parsing XML and drawing with wx.DC."""
    try:
        root = ET.fromstring(svg_string)
    except ET.ParseError:
        return None

    # Get viewBox for coordinate mapping
    vb = root.get("viewBox")
    if vb:
        parts = vb.replace(",", " ").split()
        if len(parts) == 4:
            vb_x, vb_y, vb_w, vb_h = (float(p) for p in parts)
        else:
            return None
    else:
        vb_x = _flt(root.get("x"), 0)
        vb_y = _flt(root.get("y"), 0)
        vb_w = _flt(root.get("width"), size)
        vb_h = _flt(root.get("height"), size)

    if vb_w <= 0 or vb_h <= 0:
        return None

    # Scale to fit
    padding = 8
    draw_size = size - 2 * padding
    scale = min(draw_size / vb_w, draw_size / vb_h)
    offset_x = padding + (draw_size - vb_w * scale) / 2 - vb_x * scale
    offset_y = padding + (draw_size - vb_h * scale) / 2 - vb_y * scale

    def tx(x: float) -> int:
        return int(x * scale + offset_x)

    def ty(y: float) -> int:
        return int(y * scale + offset_y)

    def ts(v: float) -> int:
        return max(1, int(v * scale))

    bmp = wx.Bitmap(size, size)
    dc = wx.MemoryDC(bmp)
    dc.SetBackground(wx.Brush(wx.Colour(255, 255, 255)))
    dc.Clear()

    def _set_pen_brush(elem, dc):
        """Set pen and brush from element attributes."""
        stroke_str = _get_style_attr(elem, "stroke", "#000000")
        fill_str = _get_style_attr(elem, "fill", "none")
        stroke_width = _flt(_get_style_attr(elem, "stroke-width", "1"))

        stroke_c = _parse_colour(stroke_str)
        fill_c = _parse_colour(fill_str)

        if stroke_c:
            dc.SetPen(wx.Pen(stroke_c, max(1, int(stroke_width * scale))))
        else:
            dc.SetPen(wx.TRANSPARENT_PEN)

        if fill_c:
            dc.SetBrush(wx.Brush(fill_c))
        else:
            dc.SetBrush(wx.TRANSPARENT_BRUSH)

    def _draw_element(elem):
        """Draw a single SVG element."""
        # Strip namespace for tag comparison
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag

        if tag == "rect":
            _set_pen_brush(elem, dc)
            x = _flt(elem.get("x"))
            y = _flt(elem.get("y"))
            w = _flt(elem.get("width"))
            h = _flt(elem.get("height"))
            rx = _flt(elem.get("rx"))
            ry = _flt(elem.get("ry"))
            if w > 0 and h > 0:
                if rx > 0 or ry > 0:
                    dc.DrawRoundedRectangle(tx(x), ty(y), ts(w), ts(h), max(1, int(max(rx, ry) * scale)))
                else:
                    dc.DrawRectangle(tx(x), ty(y), ts(w), ts(h))

        elif tag == "circle":
            _set_pen_brush(elem, dc)
            cx = _flt(elem.get("cx"))
            cy = _flt(elem.get("cy"))
            r = _flt(elem.get("r"))
            if r > 0:
                dc.DrawCircle(tx(cx), ty(cy), max(1, int(r * scale)))

        elif tag == "ellipse":
            _set_pen_brush(elem, dc)
            cx = _flt(elem.get("cx"))
            cy = _flt(elem.get("cy"))
            rx = _flt(elem.get("rx"))
            ry = _flt(elem.get("ry"))
            if rx > 0 and ry > 0:
                dc.DrawEllipse(tx(cx - rx), ty(cy - ry), ts(2 * rx), ts(2 * ry))

        elif tag == "line":
            _set_pen_brush(elem, dc)
            x1 = _flt(elem.get("x1"))
            y1 = _flt(elem.get("y1"))
            x2 = _flt(elem.get("x2"))
            y2 = _flt(elem.get("y2"))
            dc.DrawLine(tx(x1), ty(y1), tx(x2), ty(y2))

        elif tag == "polyline" or tag == "polygon":
            _set_pen_brush(elem, dc)
            pts_str = elem.get("points", "")
            nums = re.findall(r"[-+]?[\d.]+(?:[eE][-+]?\d+)?", pts_str)
            points = []
            for i in range(0, len(nums) - 1, 2):
                points.append(wx.Point(tx(float(nums[i])), ty(float(nums[i + 1]))))
            if len(points) >= 2:
                if tag == "polygon":
                    dc.DrawPolygon(points)
                else:
                    dc.DrawLines(points)

        elif tag == "path":
            _set_pen_brush(elem, dc)
            d = elem.get("d", "")
            if d:
                _draw_path(dc, d, tx, ty, scale)

        elif tag == "text":
            text = "".join(elem.itertext()).strip()
            if text:
                fill_str = _get_style_attr(elem, "fill", "#000000")
                fill_c = _parse_colour(fill_str, wx.Colour(0, 0, 0))
                if fill_c:
                    dc.SetTextForeground(fill_c)
                x = _flt(elem.get("x"))
                y = _flt(elem.get("y"))
                font_size = _flt(_get_style_attr(elem, "font-size", "7pt").replace("pt", ""), 7)
                font = dc.GetFont()
                font.SetPointSize(max(5, int(font_size * scale * 0.8)))
                dc.SetFont(font)
                dc.DrawText(text, tx(x), ty(y) - int(font_size * scale * 0.8))

        # Recursively draw children (handles <g> groups)
        for child in elem:
            _draw_element(child)

    _draw_element(root)

    dc.SelectObject(wx.NullBitmap)
    return bmp


def _draw_path(dc, d: str, tx, ty, scale):
    """Draw SVG path commands using wx.DC lines and curves."""
    cx, cy = 0.0, 0.0  # current position
    sx, sy = 0.0, 0.0  # subpath start

    for cmd, args in _parse_path_commands(d):
        if cmd == "M":
            # Absolute moveto
            if len(args) >= 2:
                cx, cy = args[0], args[1]
                sx, sy = cx, cy
                # Additional coordinate pairs are implicit lineto
                for i in range(2, len(args) - 1, 2):
                    nx, ny = args[i], args[i + 1]
                    dc.DrawLine(tx(cx), ty(cy), tx(nx), ty(ny))
                    cx, cy = nx, ny

        elif cmd == "m":
            # Relative moveto
            if len(args) >= 2:
                cx += args[0]
                cy += args[1]
                sx, sy = cx, cy
                for i in range(2, len(args) - 1, 2):
                    nx, ny = cx + args[i], cy + args[i + 1]
                    dc.DrawLine(tx(cx), ty(cy), tx(nx), ty(ny))
                    cx, cy = nx, ny

        elif cmd == "L":
            for i in range(0, len(args) - 1, 2):
                nx, ny = args[i], args[i + 1]
                dc.DrawLine(tx(cx), ty(cy), tx(nx), ty(ny))
                cx, cy = nx, ny

        elif cmd == "l":
            for i in range(0, len(args) - 1, 2):
                nx, ny = cx + args[i], cy + args[i + 1]
                dc.DrawLine(tx(cx), ty(cy), tx(nx), ty(ny))
                cx, cy = nx, ny

        elif cmd == "H":
            for a in args:
                dc.DrawLine(tx(cx), ty(cy), tx(a), ty(cy))
                cx = a

        elif cmd == "h":
            for a in args:
                nx = cx + a
                dc.DrawLine(tx(cx), ty(cy), tx(nx), ty(cy))
                cx = nx

        elif cmd == "V":
            for a in args:
                dc.DrawLine(tx(cx), ty(cy), tx(cx), ty(a))
                cy = a

        elif cmd == "v":
            for a in args:
                ny = cy + a
                dc.DrawLine(tx(cx), ty(cy), tx(cx), ty(ny))
                cy = ny

        elif cmd in ("Z", "z"):
            dc.DrawLine(tx(cx), ty(cy), tx(sx), ty(sy))
            cx, cy = sx, sy

        elif cmd == "C":
            # Absolute cubic bezier — approximate with line segments
            for i in range(0, len(args) - 5, 6):
                x1, y1 = args[i], args[i + 1]
                x2, y2 = args[i + 2], args[i + 3]
                x3, y3 = args[i + 4], args[i + 5]
                _draw_cubic(dc, cx, cy, x1, y1, x2, y2, x3, y3, tx, ty)
                cx, cy = x3, y3

        elif cmd == "c":
            for i in range(0, len(args) - 5, 6):
                x1, y1 = cx + args[i], cy + args[i + 1]
                x2, y2 = cx + args[i + 2], cy + args[i + 3]
                x3, y3 = cx + args[i + 4], cy + args[i + 5]
                _draw_cubic(dc, cx, cy, x1, y1, x2, y2, x3, y3, tx, ty)
                cx, cy = x3, y3

        elif cmd == "Q":
            for i in range(0, len(args) - 3, 4):
                x1, y1 = args[i], args[i + 1]
                x2, y2 = args[i + 2], args[i + 3]
                _draw_quadratic(dc, cx, cy, x1, y1, x2, y2, tx, ty)
                cx, cy = x2, y2

        elif cmd == "q":
            for i in range(0, len(args) - 3, 4):
                x1, y1 = cx + args[i], cy + args[i + 1]
                x2, y2 = cx + args[i + 2], cy + args[i + 3]
                _draw_quadratic(dc, cx, cy, x1, y1, x2, y2, tx, ty)
                cx, cy = x2, y2

        elif cmd == "A":
            # Elliptical arc — approximate with line to endpoint
            for i in range(0, len(args) - 6, 7):
                nx, ny = args[i + 5], args[i + 6]
                dc.DrawLine(tx(cx), ty(cy), tx(nx), ty(ny))
                cx, cy = nx, ny

        elif cmd == "a":
            for i in range(0, len(args) - 6, 7):
                nx, ny = cx + args[i + 5], cy + args[i + 6]
                dc.DrawLine(tx(cx), ty(cy), tx(nx), ty(ny))
                cx, cy = nx, ny


def _draw_cubic(dc, x0, y0, x1, y1, x2, y2, x3, y3, tx, ty, segments=12):
    """Approximate cubic bezier with line segments."""
    px, py = x0, y0
    for i in range(1, segments + 1):
        t = i / segments
        u = 1 - t
        x = u ** 3 * x0 + 3 * u ** 2 * t * x1 + 3 * u * t ** 2 * x2 + t ** 3 * x3
        y = u ** 3 * y0 + 3 * u ** 2 * t * y1 + 3 * u * t ** 2 * y2 + t ** 3 * y3
        dc.DrawLine(tx(px), ty(py), tx(x), ty(y))
        px, py = x, y


def _draw_quadratic(dc, x0, y0, x1, y1, x2, y2, tx, ty, segments=10):
    """Approximate quadratic bezier with line segments."""
    px, py = x0, y0
    for i in range(1, segments + 1):
        t = i / segments
        u = 1 - t
        x = u ** 2 * x0 + 2 * u * t * x1 + t ** 2 * x2
        y = u ** 2 * y0 + 2 * u * t * y1 + t ** 2 * y2
        dc.DrawLine(tx(px), ty(py), tx(x), ty(y))
        px, py = x, y
