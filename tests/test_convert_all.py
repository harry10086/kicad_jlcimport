"""Convert all testdata to SVGs for preview."""

import json
import subprocess
import sys
from pathlib import Path

from kicad_jlcimport.footprint_writer import write_footprint
from kicad_jlcimport.parser import parse_footprint_shapes, parse_symbol_shapes
from kicad_jlcimport.symbol_writer import write_symbol, write_symbol_library


def test_convert_all_testdata():
    """Convert all testdata JSON to KiCad files and SVGs."""
    testdata_dir = Path("testdata")
    output_dir = Path("/tmp/kicad_preview")
    output_dir.mkdir(exist_ok=True)

    # Find all unique part IDs
    part_ids = set()
    for f in testdata_dir.glob("C*_symbol.json"):
        part_ids.add(f.stem.replace("_symbol", ""))
    for f in testdata_dir.glob("C*_footprint.json"):
        part_ids.add(f.stem.replace("_footprint", ""))

    part_ids = sorted(part_ids)
    print(f"\nConverting {len(part_ids)} components: {', '.join(part_ids)}\n")

    all_svgs = []

    for part_id in part_ids:
        print(f"{part_id}:")

        sym_json = testdata_dir / f"{part_id}_symbol.json"
        fp_json = testdata_dir / f"{part_id}_footprint.json"

        # Symbol
        if sym_json.exists():
            with open(sym_json) as f:
                data = json.load(f)
            result = data.get("result", {})
            title = result.get("title", part_id)
            data_str = result.get("dataStr", {})
            shapes = data_str.get("shape", [])
            head = data_str.get("head", {})
            origin_x = head.get("x", 0)
            origin_y = head.get("y", 0)

            symbol = parse_symbol_shapes(shapes, origin_x, origin_y)
            sym_content = write_symbol(symbol, title)
            sym_lib = write_symbol_library([sym_content])

            kicad_sym = output_dir / f"{part_id}.kicad_sym"
            kicad_sym.write_text(sym_lib)

            svg_path = output_dir / f"{part_id}_symbol.svg"
            subprocess.run(
                [sys.executable, "kicad_sym_to_svg.py", str(kicad_sym), str(svg_path)],
                capture_output=True,
            )
            all_svgs.append(str(svg_path))
            print(
                f"  Symbol: {len(symbol.pins)} pins, {len(symbol.rectangles)} rects, "
                f"{len(symbol.arcs)} arcs, {len(symbol.polylines)} polylines, {len(symbol.circles)} circles"
            )

        # Footprint
        if fp_json.exists():
            with open(fp_json) as f:
                data = json.load(f)
            result = data.get("result", {})
            title = result.get("title", part_id)
            data_str = result.get("dataStr", {})
            shapes = data_str.get("shape", [])
            head = data_str.get("head", {})
            origin_x = head.get("x", 0)
            origin_y = head.get("y", 0)

            footprint = parse_footprint_shapes(shapes, origin_x, origin_y)
            fp_content = write_footprint(footprint, title)

            kicad_mod = output_dir / f"{part_id}.kicad_mod"
            kicad_mod.write_text(fp_content)

            svg_path = output_dir / f"{part_id}_footprint.svg"
            subprocess.run(
                [sys.executable, "kicad_mod_to_svg.py", str(kicad_mod), str(svg_path)],
                capture_output=True,
            )
            all_svgs.append(str(svg_path))
            print(
                f"  Footprint: {len(footprint.pads)} pads, {len(footprint.tracks)} tracks, "
                f"{len(footprint.circles)} circles, {len(footprint.arcs)} arcs"
            )
        print()

    # Also convert C442826 if data exists
    c442826_json = Path("/tmp/c442826_data.json")
    if c442826_json.exists():
        print("C442826:")
        with open(c442826_json) as f:
            data = json.load(f)

        # Symbol
        sym_data = data["symbol_data_list"][0]
        shapes = sym_data.get("dataStr", {}).get("shape", [])
        origin_x = data["sym_origin_x"]
        origin_y = data["sym_origin_y"]
        symbol = parse_symbol_shapes(shapes, origin_x, origin_y)
        sym_content = write_symbol(symbol, data["title"])
        sym_lib = write_symbol_library([sym_content])
        kicad_sym = output_dir / "C442826.kicad_sym"
        kicad_sym.write_text(sym_lib)
        svg_path = output_dir / "C442826_symbol.svg"
        subprocess.run([sys.executable, "kicad_sym_to_svg.py", str(kicad_sym), str(svg_path)], capture_output=True)
        all_svgs.append(str(svg_path))
        print(f"  Symbol: {len(symbol.pins)} pins, {len(symbol.arcs)} arcs")

        # Footprint
        fp_data = data["footprint_data"]
        fp_shapes = fp_data.get("dataStr", {}).get("shape", [])
        fp_origin_x = data["fp_origin_x"]
        fp_origin_y = data["fp_origin_y"]
        footprint = parse_footprint_shapes(fp_shapes, fp_origin_x, fp_origin_y)
        fp_content = write_footprint(footprint, data["title"])
        kicad_mod = output_dir / "C442826.kicad_mod"
        kicad_mod.write_text(fp_content)
        svg_path = output_dir / "C442826_footprint.svg"
        subprocess.run([sys.executable, "kicad_mod_to_svg.py", str(kicad_mod), str(svg_path)], capture_output=True)
        all_svgs.append(str(svg_path))
        print(f"  Footprint: {len(footprint.pads)} pads")
        print()

    print(f"Generated {len(all_svgs)} SVGs in {output_dir}")
    print("SVG files:", " ".join(all_svgs))
