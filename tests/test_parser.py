"""Tests for parser.py - shape parsing and coordinate conversion."""
import math
import pytest

from kicad_jlcimport.parser import (
    mil_to_mm, parse_footprint_shapes, parse_symbol_shapes,
    compute_arc_midpoint, _parse_svg_arc_path, _find_svg_path,
    MILS_TO_MM_DIVISOR,
)
from kicad_jlcimport.ee_types import EEFootprint, EESymbol


class TestMilToMm:
    def test_zero(self):
        assert mil_to_mm(0) == 0

    def test_positive(self):
        result = mil_to_mm(100)
        assert abs(result - 100 / MILS_TO_MM_DIVISOR) < 1e-10

    def test_negative(self):
        result = mil_to_mm(-50)
        assert result < 0
        assert abs(result - (-50 / MILS_TO_MM_DIVISOR)) < 1e-10


class TestParseSvgArcPath:
    def test_valid_arc(self):
        path = "M 100 200 A 50 50 0 0 1 150 250"
        result = _parse_svg_arc_path(path)
        assert result is not None
        sx, sy, rx, ry, large_arc, sweep, ex, ey = result
        assert sx == 100.0
        assert sy == 200.0
        assert rx == 50.0
        assert ry == 50.0
        assert large_arc == 0
        assert sweep == 1
        assert ex == 150.0
        assert ey == 250.0

    def test_valid_arc_with_commas(self):
        path = "M100,200A50,50,0,1,0,150,250"
        result = _parse_svg_arc_path(path)
        assert result is not None
        sx, sy, rx, ry, large_arc, sweep, ex, ey = result
        assert sx == 100.0
        assert sy == 200.0
        assert large_arc == 1
        assert sweep == 0

    def test_valid_arc_negative_coords(self):
        path = "M -10.5 -20.3 A 30 30 0 0 1 -5.5 -15.3"
        result = _parse_svg_arc_path(path)
        assert result is not None
        sx, sy, _, _, _, _, ex, ey = result
        assert sx == -10.5
        assert sy == -20.3
        assert ex == -5.5
        assert ey == -15.3

    def test_invalid_no_arc(self):
        assert _parse_svg_arc_path("M 100 200 L 150 250") is None

    def test_invalid_empty(self):
        assert _parse_svg_arc_path("") is None

    def test_invalid_malformed(self):
        assert _parse_svg_arc_path("M abc A def") is None


class TestFindSvgPath:
    def test_finds_path(self):
        parts = ["ARC", "2", "3", "id123", "M 100 200 A 50 50 0 0 1 150 250"]
        assert _find_svg_path(parts, start=3) == "M 100 200 A 50 50 0 0 1 150 250"

    def test_strips_whitespace(self):
        parts = ["ARC", "2", "3", "  M100,200A50,50  "]
        assert _find_svg_path(parts, start=1) == "M100,200A50,50"

    def test_returns_empty_when_not_found(self):
        parts = ["ARC", "2", "3", "no_path_here"]
        assert _find_svg_path(parts, start=1) == ""

    def test_returns_empty_for_empty_parts(self):
        assert _find_svg_path([], start=0) == ""


class TestParseFootprintShapes:
    def test_empty_shapes(self):
        fp = parse_footprint_shapes([], 0, 0)
        assert isinstance(fp, EEFootprint)
        assert fp.pads == []
        assert fp.tracks == []

    def test_parse_rect_pad(self):
        shape = "PAD~RECT~400~300~10~10~1~~1~0~~~0~id1"
        fp = parse_footprint_shapes([shape], 400, 300)
        assert len(fp.pads) == 1
        pad = fp.pads[0]
        assert pad.shape == "RECT"
        assert pad.number == "1"
        assert abs(pad.x) < 0.01  # origin-corrected
        assert abs(pad.y) < 0.01

    def test_parse_oval_pad(self):
        shape = "PAD~OVAL~400~300~5~10~1~~2~3~~~0~id2"
        fp = parse_footprint_shapes([shape], 400, 300)
        assert len(fp.pads) == 1
        assert fp.pads[0].shape == "OVAL"
        assert fp.pads[0].number == "2"

    def test_parse_track(self):
        shape = "TRACK~2~3~id1~100 100 200 200"
        fp = parse_footprint_shapes([shape], 0, 0)
        assert len(fp.tracks) == 1
        track = fp.tracks[0]
        assert track.layer == "F.SilkS"
        assert len(track.points) == 2

    def test_parse_circle(self):
        shape = "CIRCLE~100~100~10~1~3~id1"
        fp = parse_footprint_shapes([shape], 0, 0)
        assert len(fp.circles) == 1
        circle = fp.circles[0]
        assert circle.layer == "F.SilkS"

    def test_skip_decorative_circle(self):
        shape = "CIRCLE~100~100~10~1~100~id1"
        fp = parse_footprint_shapes([shape], 0, 0)
        assert len(fp.circles) == 0

    def test_parse_hole(self):
        shape = "HOLE~200~200~5~id1"
        fp = parse_footprint_shapes([shape], 0, 0)
        assert len(fp.holes) == 1
        hole = fp.holes[0]
        assert hole.radius == mil_to_mm(5)

    def test_origin_offset_applied(self):
        shape = "PAD~RECT~400~300~10~10~1~~1~0~~~0~id1"
        fp = parse_footprint_shapes([shape], 200, 100)
        pad = fp.pads[0]
        # Pad at (400,300) with origin (200,100) => offset (200, 200) in mils
        expected_x = mil_to_mm(400) - mil_to_mm(200)
        expected_y = mil_to_mm(300) - mil_to_mm(100)
        assert abs(pad.x - expected_x) < 0.001
        assert abs(pad.y - expected_y) < 0.001


class TestParseSymbolShapes:
    def test_empty_shapes(self):
        sym = parse_symbol_shapes([], 0, 0)
        assert isinstance(sym, EESymbol)
        assert sym.pins == []
        assert sym.rectangles == []

    def test_parse_rectangle(self):
        shape = "R~100~100~0~0~50~30~0~0~0~1~0~id1"
        sym = parse_symbol_shapes([shape], 0, 0)
        assert len(sym.rectangles) == 1
        rect = sym.rectangles[0]
        assert rect.width == mil_to_mm(50)

    def test_parse_circle(self):
        shape = "E~100~100~20~20~0~0"
        sym = parse_symbol_shapes([shape], 0, 0)
        assert len(sym.circles) == 1
        assert sym.circles[0].radius == mil_to_mm(20)

    def test_parse_polyline(self):
        shape = "PL~100~100~200~200~0~3"
        sym = parse_symbol_shapes([shape], 0, 0)
        assert len(sym.polylines) == 1
        assert len(sym.polylines[0].points) == 2
        assert sym.polylines[0].closed is False

    def test_parse_polygon(self):
        shape = "PG~100~100~200~200~100~200~0~3"
        sym = parse_symbol_shapes([shape], 0, 0)
        assert len(sym.polylines) == 1
        assert sym.polylines[0].closed is True
        assert sym.polylines[0].fill is True

    def test_parse_pin(self):
        shape = "P~show~0~1~400~300~0~id1^^section1^^M400,300h10^^1~0~0~0~0~TestPin^^1~0~0~0~0~1"
        sym = parse_symbol_shapes([shape], 400, 300)
        assert len(sym.pins) == 1
        pin = sym.pins[0]
        assert pin.number == "1"
        assert pin.electrical_type == "unspecified"

    def test_y_inversion_for_symbols(self):
        shape = "E~100~200~10~10~0~0"
        sym = parse_symbol_shapes([shape], 0, 0)
        circle = sym.circles[0]
        # Y should be inverted: -(200 - 0) in mils -> mm
        assert circle.cy == -mil_to_mm(200)


class TestComputeArcMidpoint:
    def test_semicircle(self):
        # A half-circle from (0, -1) to (0, 1) with radius 1
        mid = compute_arc_midpoint((0, -1), (0, 1), 1, 1, 0, 1)
        # Midpoint should be at approximately (1, 0) or (-1, 0)
        assert abs(mid[0] ** 2 + mid[1] ** 2 - 1) < 0.1  # on circle of radius 1

    def test_coincident_points(self):
        mid = compute_arc_midpoint((5, 5), (5, 5), 10, 10, 0, 1)
        assert mid == (5, 5)

    def test_large_arc_flag(self):
        # Use radius > chord/2 so center is off-chord and flags diverge
        mid0 = compute_arc_midpoint((0, 0), (2, 0), 2, 2, 0, 1)
        mid1 = compute_arc_midpoint((0, 0), (2, 0), 2, 2, 1, 1)
        # Different large_arc flags should give different midpoints
        assert mid0 != mid1
