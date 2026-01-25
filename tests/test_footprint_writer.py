"""Tests for footprint_writer.py - KiCad footprint generation."""

from kicad_jlcimport.ee_types import EECircle, EEFootprint, EEHole, EEPad, EETrack
from kicad_jlcimport.footprint_writer import write_footprint


def _make_footprint(**kwargs):
    """Create an EEFootprint with optional components."""
    fp = EEFootprint()
    if "pads" in kwargs:
        fp.pads = kwargs["pads"]
    if "tracks" in kwargs:
        fp.tracks = kwargs["tracks"]
    if "circles" in kwargs:
        fp.circles = kwargs["circles"]
    if "holes" in kwargs:
        fp.holes = kwargs["holes"]
    if "arcs" in kwargs:
        fp.arcs = kwargs["arcs"]
    return fp


class TestWriteFootprint:
    def test_minimal_footprint(self):
        fp = _make_footprint()
        result = write_footprint(fp, "Test")
        assert '(footprint "Test"' in result
        assert "(version 20241229)" in result
        assert '(generator "JLCImport")' in result
        assert "(embedded_fonts no)" in result
        assert result.endswith(")\n")

    def test_smd_attribute(self):
        pad = EEPad(shape="RECT", x=0, y=0, width=1, height=1, layer="1", number="1", drill=0)
        fp = _make_footprint(pads=[pad])
        result = write_footprint(fp, "Test")
        assert "(attr smd)" in result

    def test_tht_attribute(self):
        pad = EEPad(shape="OVAL", x=0, y=0, width=1, height=1, layer="11", number="1", drill=0.8)
        fp = _make_footprint(pads=[pad])
        result = write_footprint(fp, "Test")
        assert "(attr through_hole)" in result

    def test_pad_generation(self):
        pad = EEPad(shape="RECT", x=1.0, y=2.0, width=0.5, height=0.8, layer="1", number="1", drill=0)
        fp = _make_footprint(pads=[pad])
        result = write_footprint(fp, "Test")
        assert '(pad "1" smd rect' in result
        assert "(size" in result
        assert "(layers" in result

    def test_pad_with_drill(self):
        pad = EEPad(shape="OVAL", x=0, y=0, width=1.5, height=1.5, layer="11", number="A1", drill=1.0)
        fp = _make_footprint(pads=[pad])
        result = write_footprint(fp, "Test")
        assert "(drill" in result
        assert '(pad "A1" thru_hole' in result

    def test_pad_with_rotation(self):
        pad = EEPad(shape="RECT", x=0, y=0, width=1, height=2, layer="1", number="1", drill=0, rotation=45.0)
        fp = _make_footprint(pads=[pad])
        result = write_footprint(fp, "Test")
        assert "45" in result

    def test_track_generation(self):
        track = EETrack(width=0.2, layer="F.SilkS", points=[(0, 0), (1, 0), (1, 1)])
        fp = _make_footprint(tracks=[track])
        result = write_footprint(fp, "Test")
        assert "(fp_line" in result
        # Two segments for 3 points
        assert result.count("(fp_line") == 2

    def test_circle_generation(self):
        circle = EECircle(cx=0, cy=0, radius=2.0, width=0.15, layer="F.SilkS")
        fp = _make_footprint(circles=[circle])
        result = write_footprint(fp, "Test")
        assert "(fp_circle" in result
        assert "(center" in result
        assert "(end" in result

    def test_hole_generation(self):
        hole = EEHole(x=0, y=0, radius=0.5)
        fp = _make_footprint(holes=[hole])
        result = write_footprint(fp, "Test")
        assert "np_thru_hole" in result
        assert "(drill" in result

    def test_properties_added(self):
        fp = _make_footprint()
        result = write_footprint(
            fp, "Test", lcsc_id="C123456", description="A test part", datasheet="https://example.com/ds.pdf"
        )
        assert '(property "LCSC" "C123456"' in result
        assert '(property "Description"' in result
        assert '(property "Datasheet"' in result

    def test_model_reference(self):
        fp = _make_footprint()
        result = write_footprint(
            fp,
            "Test",
            model_path="${KIPRJMOD}/lib.3dshapes/Test.step",
            model_offset=(1.0, 2.0, 3.0),
            model_rotation=(0, 0, 90),
        )
        assert '(model "${KIPRJMOD}/lib.3dshapes/Test.step"' in result
        assert "(offset" in result
        assert "(rotate" in result

    def test_special_chars_escaped(self):
        fp = _make_footprint()
        result = write_footprint(fp, "Test", description='Has "quotes" and\nnewlines')
        assert '\\"quotes\\"' in result
        assert "\n" not in result.split("Description")[1].split(")")[0]

    def test_uuid_uniqueness(self):
        pad1 = EEPad(shape="RECT", x=0, y=0, width=1, height=1, layer="1", number="1", drill=0)
        pad2 = EEPad(shape="RECT", x=2, y=0, width=1, height=1, layer="1", number="2", drill=0)
        fp = _make_footprint(pads=[pad1, pad2])
        result = write_footprint(fp, "Test")
        # Extract all UUIDs
        import re

        uuids = re.findall(r'uuid "([^"]+)"', result)
        assert len(uuids) == len(set(uuids))  # All unique

    def test_back_copper_pad(self):
        pad = EEPad(shape="RECT", x=0, y=0, width=1, height=1, layer="2", number="1", drill=0)
        fp = _make_footprint(pads=[pad])
        result = write_footprint(fp, "Test")
        assert '"B.Cu"' in result
        assert '"B.Mask"' in result
        assert '"B.Paste"' in result
