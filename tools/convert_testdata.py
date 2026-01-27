#!/usr/bin/env python3
"""Convert all testdata JSON files to KiCad and SVG for preview."""

import json
import subprocess
import sys
from pathlib import Path

# Add src/ to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kicad_jlcimport.easyeda.parser import parse_footprint_shapes, parse_symbol_shapes
from kicad_jlcimport.kicad.footprint_writer import write_footprint
from kicad_jlcimport.kicad.symbol_writer import write_symbol, write_symbol_library


def convert_component(part_id: str, testdata_dir: Path, output_dir: Path):
    """Convert a component from testdata JSON to KiCad and SVG."""
    sym_json = testdata_dir / f"{part_id}_symbol.json"
    fp_json = testdata_dir / f"{part_id}_footprint.json"

    results = {"id": part_id, "symbol_svg": None, "footprint_svg": None}

    # Convert symbol if exists
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
        c_para = head.get("c_para", {})
        prefix = c_para.get("pre", "U?").rstrip("?")

        symbol = parse_symbol_shapes(shapes, origin_x, origin_y)
        sym_content = write_symbol(symbol, title, prefix=prefix)
        sym_lib = write_symbol_library([sym_content])

        kicad_sym = output_dir / f"{part_id}.kicad_sym"
        kicad_sym.write_text(sym_lib)

        svg_path = output_dir / f"{part_id}_symbol.svg"
        subprocess.run(
            [sys.executable, "kicad_sym_to_svg.py", str(kicad_sym), str(svg_path)], check=True, capture_output=True
        )
        results["symbol_svg"] = svg_path
        print(
            f"  Symbol: {len(symbol.pins)} pins, {len(symbol.rectangles)} rects, "
            f"{len(symbol.arcs)} arcs, {len(symbol.circles)} circles"
        )

    # Convert footprint if exists
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
            [sys.executable, "kicad_mod_to_svg.py", str(kicad_mod), str(svg_path)], check=True, capture_output=True
        )
        results["footprint_svg"] = svg_path
        print(
            f"  Footprint: {len(footprint.pads)} pads, {len(footprint.tracks)} tracks, "
            f"{len(footprint.circles)} circles, {len(footprint.arcs)} arcs"
        )

    return results


def main():
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
    print(f"Converting {len(part_ids)} components: {', '.join(part_ids)}\n")

    all_svgs = []
    for part_id in part_ids:
        print(f"{part_id}:")
        results = convert_component(part_id, testdata_dir, output_dir)
        if results["symbol_svg"]:
            all_svgs.append(results["symbol_svg"])
        if results["footprint_svg"]:
            all_svgs.append(results["footprint_svg"])
        print()

    print(f"Generated {len(all_svgs)} SVG files in {output_dir}")

    # Return paths for opening
    return all_svgs


if __name__ == "__main__":
    svgs = main()
    # Print paths for opening
    print("\nSVG files:")
    for svg in svgs:
        print(f"  {svg}")
