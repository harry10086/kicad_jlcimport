"""Integration tests using real downloaded EasyEDA component data."""
import json
import os
import pytest

from kicad_jlcimport.parser import parse_footprint_shapes, parse_symbol_shapes
from kicad_jlcimport.footprint_writer import write_footprint
from kicad_jlcimport.symbol_writer import write_symbol


TESTDATA_DIR = os.path.join(os.path.dirname(__file__), "..", "testdata")


def load_component_data(lcsc_id: str):
    """Load footprint and symbol data from testdata directory."""
    fp_path = os.path.join(TESTDATA_DIR, f"{lcsc_id}_footprint.json")
    sym_path = os.path.join(TESTDATA_DIR, f"{lcsc_id}_symbol.json")

    with open(fp_path) as f:
        fp_data = json.load(f)
    with open(sym_path) as f:
        sym_data = json.load(f)

    return fp_data, sym_data


class TestC427602:
    """SOT-23-5 package - simple 5-pin SMD IC."""

    @pytest.fixture
    def component(self):
        fp_data, sym_data = load_component_data("C427602")
        fp_result = fp_data["result"]["dataStr"]
        sym_result = sym_data["result"]["dataStr"]
        return {
            "fp_shapes": fp_result["shape"],
            "fp_origin_x": fp_result["head"]["x"],
            "fp_origin_y": fp_result["head"]["y"],
            "sym_shapes": sym_result["shape"],
            "sym_origin_x": sym_result["head"]["x"],
            "sym_origin_y": sym_result["head"]["y"],
        }

    def test_footprint_pad_count(self, component):
        """Should have 5 pads for SOT-23-5."""
        fp = parse_footprint_shapes(
            component["fp_shapes"],
            component["fp_origin_x"],
            component["fp_origin_y"]
        )
        assert len(fp.pads) == 5

    def test_footprint_pad_numbers(self, component):
        """Pads should be numbered 1-5."""
        fp = parse_footprint_shapes(
            component["fp_shapes"],
            component["fp_origin_x"],
            component["fp_origin_y"]
        )
        pad_numbers = sorted([p.number for p in fp.pads])
        assert pad_numbers == ["1", "2", "3", "4", "5"]

    def test_footprint_layer_101_filtered(self, component):
        """Layer 101 (Component Marking Layer) circles should be filtered."""
        # Verify raw data has layer 101 circles
        raw_layer_101_count = sum(
            1 for s in component["fp_shapes"]
            if s.startswith("CIRCLE") and s.split("~")[5] == "101"
        )
        assert raw_layer_101_count > 0, "Test data should have layer 101 circles"

        fp = parse_footprint_shapes(
            component["fp_shapes"],
            component["fp_origin_x"],
            component["fp_origin_y"]
        )
        # Only the F.Fab circle (layer 12) should remain, layer 101 filtered
        assert len(fp.circles) == 1
        assert fp.circles[0].layer == "F.Fab"

        # Verify output doesn't have extra circles
        output = write_footprint(fp, "Test", lcsc_id="C427602")
        assert output.count("(fp_circle") == 1

    def test_footprint_has_silkscreen_pin1_dot(self, component):
        """Silkscreen pin 1 indicator (SOLIDREGION on layer 3) should be imported.

        The pin 1 dot is stored as a filled arc/circle SOLIDREGION on layer 3
        (Top Silkscreen Layer), not as a CIRCLE shape.
        """
        fp = parse_footprint_shapes(
            component["fp_shapes"],
            component["fp_origin_x"],
            component["fp_origin_y"]
        )
        # Should have at least one silkscreen region for the pin 1 dot
        silkscreen_regions = [r for r in fp.regions if r.layer == "F.SilkS"]
        assert len(silkscreen_regions) >= 1, "Missing silkscreen pin 1 indicator"
        # Region must have valid polygon (at least 3 points)
        assert len(silkscreen_regions[0].points) >= 3, "Region has too few points"

        # Verify it actually appears in the output
        output = write_footprint(fp, "Test", lcsc_id="C427602")
        assert "(fp_poly" in output, "fp_poly missing from output"
        assert 'layer "F.SilkS"' in output, "Silkscreen layer missing"

    def test_footprint_has_silkscreen_tracks(self, component):
        """Should have silkscreen outline tracks."""
        fp = parse_footprint_shapes(
            component["fp_shapes"],
            component["fp_origin_x"],
            component["fp_origin_y"]
        )
        silk_tracks = [t for t in fp.tracks if t.layer == "F.SilkS"]
        assert len(silk_tracks) > 0

        # Verify silkscreen lines appear in output
        output = write_footprint(fp, "Test", lcsc_id="C427602")
        assert "(fp_line" in output
        assert 'layer "F.SilkS"' in output

    def test_footprint_writes_valid_kicad(self, component):
        """Should generate valid KiCad footprint format."""
        fp = parse_footprint_shapes(
            component["fp_shapes"],
            component["fp_origin_x"],
            component["fp_origin_y"]
        )
        output = write_footprint(fp, "SOT-23-5_Test", lcsc_id="C427602")

        assert output.startswith('(footprint "SOT-23-5_Test"')
        assert "(pad " in output
        assert 'property "LCSC" "C427602"' in output

    def test_symbol_pin_count(self, component):
        """Symbol should have 5 pins."""
        sym = parse_symbol_shapes(
            component["sym_shapes"],
            component["sym_origin_x"],
            component["sym_origin_y"]
        )
        assert len(sym.pins) == 5

        # Verify pins appear in output
        output = write_symbol(sym, "Test", prefix="U", lcsc_id="C427602")
        assert output.count("(pin ") == 5

    def test_symbol_has_rectangle(self, component):
        """Symbol should have a body rectangle."""
        sym = parse_symbol_shapes(
            component["sym_shapes"],
            component["sym_origin_x"],
            component["sym_origin_y"]
        )
        assert len(sym.rectangles) >= 1

        # Verify rectangle appears in output
        output = write_symbol(sym, "Test", prefix="U", lcsc_id="C427602")
        assert "(rectangle" in output


class TestC2040:
    """RP2040 QFN-56 package - complex multi-pin microcontroller."""

    @pytest.fixture
    def component(self):
        fp_data, sym_data = load_component_data("C2040")
        fp_result = fp_data["result"]["dataStr"]
        sym_result = sym_data["result"]["dataStr"]
        return {
            "fp_shapes": fp_result["shape"],
            "fp_origin_x": fp_result["head"]["x"],
            "fp_origin_y": fp_result["head"]["y"],
            "sym_shapes": sym_result["shape"],
            "sym_origin_x": sym_result["head"]["x"],
            "sym_origin_y": sym_result["head"]["y"],
        }

    def test_footprint_pad_count(self, component):
        """Should have 57 pads (56 pins + thermal pad)."""
        fp = parse_footprint_shapes(
            component["fp_shapes"],
            component["fp_origin_x"],
            component["fp_origin_y"]
        )
        assert len(fp.pads) == 57

        # Verify output has all 57 pads
        output = write_footprint(fp, "RP2040_Test", lcsc_id="C2040")
        assert output.count("(pad ") == 57

    def test_footprint_centered_at_origin(self, component):
        """After origin adjustment, footprint should be roughly centered."""
        fp = parse_footprint_shapes(
            component["fp_shapes"],
            component["fp_origin_x"],
            component["fp_origin_y"]
        )
        # Calculate centroid of pads
        avg_x = sum(p.x for p in fp.pads) / len(fp.pads)
        avg_y = sum(p.y for p in fp.pads) / len(fp.pads)
        # Should be near origin (within 1mm)
        assert abs(avg_x) < 1.0
        assert abs(avg_y) < 1.0

    def test_footprint_has_silkscreen_pin1(self, component):
        """QFN should have silkscreen pin 1 indicator circles."""
        fp = parse_footprint_shapes(
            component["fp_shapes"],
            component["fp_origin_x"],
            component["fp_origin_y"]
        )
        silk_circles = [c for c in fp.circles if c.layer == "F.SilkS"]
        assert len(silk_circles) >= 1, "Missing silkscreen pin 1 indicator"

        # Verify circles appear in output
        output = write_footprint(fp, "RP2040_Test", lcsc_id="C2040")
        assert "(fp_circle" in output
        assert 'layer "F.SilkS"' in output

    def test_symbol_pin_count(self, component):
        """Symbol should have 57 pins."""
        sym = parse_symbol_shapes(
            component["sym_shapes"],
            component["sym_origin_x"],
            component["sym_origin_y"]
        )
        assert len(sym.pins) == 57

        # Verify output has all 57 pins
        output = write_symbol(sym, "RP2040_Test", prefix="U", lcsc_id="C2040")
        assert output.count("(pin ") == 57

    def test_symbol_writes_valid_kicad(self, component):
        """Should generate valid KiCad symbol format."""
        sym = parse_symbol_shapes(
            component["sym_shapes"],
            component["sym_origin_x"],
            component["sym_origin_y"]
        )
        output = write_symbol(
            sym, "RP2040_Test",
            prefix="U",
            lcsc_id="C2040"
        )

        assert '(symbol "RP2040_Test"' in output
        assert "(pin " in output
        assert 'property "LCSC" "C2040"' in output


class TestC87097:
    """DIP-16 package - tests layer 101 filtering (Component Marking Layer)."""

    @pytest.fixture
    def component(self):
        fp_data, sym_data = load_component_data("C87097")
        fp_result = fp_data["result"]["dataStr"]
        sym_result = sym_data["result"]["dataStr"]
        return {
            "fp_shapes": fp_result["shape"],
            "fp_origin_x": fp_result["head"]["x"],
            "fp_origin_y": fp_result["head"]["y"],
            "sym_shapes": sym_result["shape"],
            "sym_origin_x": sym_result["head"]["x"],
            "sym_origin_y": sym_result["head"]["y"],
        }

    def test_footprint_pad_count(self, component):
        """Should have 16 pads for DIP-16."""
        fp = parse_footprint_shapes(
            component["fp_shapes"],
            component["fp_origin_x"],
            component["fp_origin_y"]
        )
        assert len(fp.pads) == 16

        # Verify output has all 16 pads
        output = write_footprint(fp, "DIP-16_Test", lcsc_id="C87097")
        assert output.count("(pad ") == 16

    def test_layer_101_circles_filtered(self, component):
        """Layer 101 (Component Marking Layer) circles must be filtered.

        This is a regression test - C87097 has a circle on layer 101 that
        was incorrectly appearing inside the silkscreen outline.
        """
        # Count circles by layer in raw data
        raw_layer_101_count = sum(
            1 for s in component["fp_shapes"]
            if s.startswith("CIRCLE") and s.split("~")[5] == "101"
        )
        assert raw_layer_101_count > 0, "Test data should have layer 101 circles"

        # Count non-101 circles in raw data
        raw_other_circles = sum(
            1 for s in component["fp_shapes"]
            if s.startswith("CIRCLE") and s.split("~")[5] != "101"
        )

        fp = parse_footprint_shapes(
            component["fp_shapes"],
            component["fp_origin_x"],
            component["fp_origin_y"]
        )

        # Parsed circles should only include non-101 circles
        assert len(fp.circles) == raw_other_circles, \
            f"Expected {raw_other_circles} circles, got {len(fp.circles)} (layer 101 not filtered)"

        # Verify output has correct circle count
        output = write_footprint(fp, "DIP-16_Test", lcsc_id="C87097")
        assert output.count("(fp_circle") == raw_other_circles

    def test_symbol_pin_count(self, component):
        """Symbol should have 16 pins."""
        sym = parse_symbol_shapes(
            component["sym_shapes"],
            component["sym_origin_x"],
            component["sym_origin_y"]
        )
        assert len(sym.pins) == 16

        # Verify output has all 16 pins
        output = write_symbol(sym, "DIP-16_Test", prefix="U", lcsc_id="C87097")
        assert output.count("(pin ") == 16

    def test_footprint_writes_valid_kicad(self, component):
        """Should generate valid KiCad footprint format."""
        fp = parse_footprint_shapes(
            component["fp_shapes"],
            component["fp_origin_x"],
            component["fp_origin_y"]
        )
        output = write_footprint(fp, "DIP-16_Test", lcsc_id="C87097")

        assert output.startswith('(footprint "DIP-16_Test"')
        assert output.count("(pad ") == 16
        assert 'property "LCSC" "C87097"' in output


class TestC5360901:
    """Another component for variety in testing."""

    @pytest.fixture
    def component(self):
        fp_data, sym_data = load_component_data("C5360901")
        fp_result = fp_data["result"]["dataStr"]
        sym_result = sym_data["result"]["dataStr"]
        return {
            "fp_shapes": fp_result["shape"],
            "fp_origin_x": fp_result["head"]["x"],
            "fp_origin_y": fp_result["head"]["y"],
            "sym_shapes": sym_result["shape"],
            "sym_origin_x": sym_result["head"]["x"],
            "sym_origin_y": sym_result["head"]["y"],
        }

    def test_footprint_parses(self, component):
        """Footprint should parse without errors and produce valid output."""
        fp = parse_footprint_shapes(
            component["fp_shapes"],
            component["fp_origin_x"],
            component["fp_origin_y"]
        )
        assert len(fp.pads) > 0

        # Verify output matches parsed data
        output = write_footprint(fp, "C5360901_Test", lcsc_id="C5360901")
        assert output.count("(pad ") == len(fp.pads)

    def test_symbol_parses(self, component):
        """Symbol should parse without errors and produce valid output."""
        sym = parse_symbol_shapes(
            component["sym_shapes"],
            component["sym_origin_x"],
            component["sym_origin_y"]
        )
        assert len(sym.pins) > 0

        # Verify output matches parsed data
        output = write_symbol(sym, "C5360901_Test", prefix="U", lcsc_id="C5360901")
        assert output.count("(pin ") == len(sym.pins)

    def test_roundtrip_footprint(self, component):
        """Parse and write should produce valid output with all elements."""
        fp = parse_footprint_shapes(
            component["fp_shapes"],
            component["fp_origin_x"],
            component["fp_origin_y"]
        )
        output = write_footprint(fp, "C5360901_Test", lcsc_id="C5360901")

        # Verify all elements present in output
        assert "(footprint " in output
        assert output.count("(pad ") == len(fp.pads)
        assert output.count("(fp_line") >= len([t for t in fp.tracks if len(t.points) > 1])
        assert output.count("(fp_circle") == len(fp.circles)
        assert output.count("(fp_poly") == len(fp.regions)

    def test_roundtrip_symbol(self, component):
        """Parse and write should produce valid output with all elements."""
        sym = parse_symbol_shapes(
            component["sym_shapes"],
            component["sym_origin_x"],
            component["sym_origin_y"]
        )
        output = write_symbol(sym, "C5360901_Test", prefix="U", lcsc_id="C5360901")

        # Verify all elements present in output
        assert "(symbol " in output
        assert output.count("(pin ") == len(sym.pins)
        assert output.count("(rectangle") == len(sym.rectangles)

    def test_symbol_pin1_dot_filled(self, component):
        """Pin 1 indicator circle should be filled, not hollow."""
        sym = parse_symbol_shapes(
            component["sym_shapes"],
            component["sym_origin_x"],
            component["sym_origin_y"]
        )
        # Should have one filled circle
        assert len(sym.circles) == 1
        assert sym.circles[0].filled is True

        # Output must have filled circle (outline = solid dark fill)
        output = write_symbol(sym, "C5360901_Test", prefix="U", lcsc_id="C5360901")
        assert "(circle " in output
        assert "(fill (type outline))" in output

    def test_symbol_pin_names_parsed(self, component):
        """Pin names (including numeric ones like '1') must be parsed and output."""
        sym = parse_symbol_shapes(
            component["sym_shapes"],
            component["sym_origin_x"],
            component["sym_origin_y"]
        )
        # All 9 pins should have names
        for pin in sym.pins:
            assert pin.name != "", f"Pin {pin.number} has empty name"

        # Output must contain pin names
        output = write_symbol(sym, "C5360901_Test", prefix="U", lcsc_id="C5360901")
        # Check that pin names appear (name "1" for pin 1, etc)
        assert '(name "1"' in output
        assert '(name "9"' in output
