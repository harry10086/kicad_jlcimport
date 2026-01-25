"""Tests for symbol_writer.py - KiCad symbol generation."""

from kicad_jlcimport.ee_types import EECircle, EEPin, EEPolyline, EERectangle, EESymbol
from kicad_jlcimport.symbol_writer import _estimate_bottom, _estimate_top, write_symbol


def _make_symbol(**kwargs):
    """Create an EESymbol with optional components."""
    sym = EESymbol()
    if "pins" in kwargs:
        sym.pins = kwargs["pins"]
    if "rectangles" in kwargs:
        sym.rectangles = kwargs["rectangles"]
    if "circles" in kwargs:
        sym.circles = kwargs["circles"]
    if "polylines" in kwargs:
        sym.polylines = kwargs["polylines"]
    return sym


class TestWriteSymbol:
    def test_minimal_symbol(self):
        sym = _make_symbol()
        result = write_symbol(sym, "Test")
        assert '(symbol "Test"' in result
        assert "(in_bom yes)" in result
        assert "(on_board yes)" in result

    def test_reference_property(self):
        sym = _make_symbol()
        result = write_symbol(sym, "Test", prefix="R")
        assert '(property "Reference" "R"' in result

    def test_value_property(self):
        sym = _make_symbol()
        result = write_symbol(sym, "My_Resistor")
        assert '(property "Value" "My_Resistor"' in result

    def test_footprint_property(self):
        sym = _make_symbol()
        result = write_symbol(sym, "Test", footprint_ref="JLCImport:Test")
        assert '(property "Footprint" "JLCImport:Test"' in result

    def test_lcsc_property(self):
        sym = _make_symbol()
        result = write_symbol(sym, "Test", lcsc_id="C123456")
        assert '(property "LCSC" "C123456"' in result

    def test_datasheet_property(self):
        sym = _make_symbol()
        result = write_symbol(sym, "Test", datasheet="https://example.com/ds.pdf")
        assert '(property "Datasheet" "https://example.com/ds.pdf"' in result

    def test_manufacturer_properties(self):
        sym = _make_symbol()
        result = write_symbol(sym, "Test", manufacturer="Acme Corp", manufacturer_part="ACM-001")
        assert '(property "Manufacturer" "Acme Corp"' in result
        assert '(property "Manufacturer Part" "ACM-001"' in result

    def test_pin_generation(self):
        pin = EEPin(number="1", name="VCC", x=0, y=0, rotation=0, length=2.54, electrical_type="power_in")
        sym = _make_symbol(pins=[pin])
        result = write_symbol(sym, "Test")
        assert "(pin power_in line" in result
        assert '(name "VCC"' in result
        assert '(number "1"' in result

    def test_pin_hidden_name(self):
        pin = EEPin(
            number="1", name="VCC", x=0, y=0, rotation=0, length=2.54, electrical_type="power_in", name_visible=False
        )
        sym = _make_symbol(pins=[pin])
        result = write_symbol(sym, "Test")
        assert "(name" in result
        # The hide should be in the name effects
        name_line = [line for line in result.split("\n") if '(name "VCC"' in line][0]
        assert "hide" in name_line

    def test_pin_hidden_number(self):
        pin = EEPin(
            number="1", name="X", x=0, y=0, rotation=0, length=2.54, electrical_type="input", number_visible=False
        )
        sym = _make_symbol(pins=[pin])
        result = write_symbol(sym, "Test")
        num_line = [line for line in result.split("\n") if '(number "1"' in line][0]
        assert "hide" in num_line

    def test_rectangle_generation(self):
        rect = EERectangle(x=-5, y=5, width=10, height=-10)
        sym = _make_symbol(rectangles=[rect])
        result = write_symbol(sym, "Test")
        assert "(rectangle" in result
        assert "(start" in result
        assert "(end" in result
        assert "(fill (type background))" in result

    def test_circle_generation(self):
        circle = EECircle(cx=0, cy=0, radius=3.0, width=0.254, layer="")
        sym = _make_symbol(circles=[circle])
        result = write_symbol(sym, "Test")
        assert "(circle" in result
        assert "(center" in result
        assert "(radius" in result

    def test_polyline_generation(self):
        poly = EEPolyline(points=[(0, 0), (1, 1), (2, 0)], closed=False, fill=False)
        sym = _make_symbol(polylines=[poly])
        result = write_symbol(sym, "Test")
        assert "(polyline" in result
        assert "(pts" in result
        assert "(fill (type none))" in result

    def test_polygon_filled(self):
        poly = EEPolyline(points=[(0, 0), (1, 1), (2, 0)], closed=True, fill=True)
        sym = _make_symbol(polylines=[poly])
        result = write_symbol(sym, "Test")
        assert "(fill (type background))" in result

    def test_special_chars_escaped(self):
        sym = _make_symbol()
        result = write_symbol(sym, "Test", description='Has "quotes" and\nnewlines')
        assert '\\"quotes\\"' in result

    def test_unit_sub_symbol_naming(self):
        sym = _make_symbol()
        result = write_symbol(sym, "MyPart")
        # Single unit: uses _0_1
        assert '(symbol "MyPart_0_1"' in result


class TestEstimateTopBottom:
    def test_top_from_rectangles(self):
        sym = _make_symbol(rectangles=[EERectangle(x=0, y=5, width=10, height=-10)])
        top = _estimate_top(sym)
        assert top == 5  # max of y and y+height

    def test_bottom_from_rectangles(self):
        sym = _make_symbol(rectangles=[EERectangle(x=0, y=5, width=10, height=-10)])
        bottom = _estimate_bottom(sym)
        assert bottom == -5  # min of y and y+height

    def test_top_from_pins(self):
        sym = _make_symbol(
            pins=[EEPin(number="1", name="A", x=0, y=10, rotation=0, length=2.54, electrical_type="input")]
        )
        top = _estimate_top(sym)
        assert top == 10

    def test_defaults_when_empty(self):
        sym = _make_symbol()
        assert _estimate_top(sym) == 5.0
        assert _estimate_bottom(sym) == -5.0
