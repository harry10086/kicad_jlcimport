#!/usr/bin/env python3
"""Fetch a JLCPCB part and display symbol/footprint SVGs."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kicad_jlcimport.easyeda.api import fetch_full_component
from kicad_jlcimport.easyeda.parser import parse_footprint_shapes, parse_symbol_shapes
from kicad_jlcimport.kicad.footprint_writer import write_footprint
from kicad_jlcimport.kicad.symbol_writer import write_symbol, write_symbol_library


def preview_part(part_id: str):
    """Fetch part and generate SVG previews."""
    print(f"Fetching {part_id}...")
    comp = fetch_full_component(part_id)

    title = comp.get("title", part_id)
    print(f"Component: {title}")

    output_dir = Path("/tmp/kicad_preview")
    output_dir.mkdir(exist_ok=True)

    svgs = []

    # Symbol
    sym_list = comp.get("symbol_data_list", [])
    if sym_list:
        sym_data = sym_list[0]
        ds = sym_data.get("dataStr", {})
        if isinstance(ds, str):
            ds = json.loads(ds)
        shapes = ds.get("shape", [])
        head = ds.get("head", {})
        origin_x = head.get("x", 0)
        origin_y = head.get("y", 0)

        if shapes:
            symbol = parse_symbol_shapes(shapes, origin_x, origin_y)
            sym_content = write_symbol(symbol, title)
            sym_lib = write_symbol_library([sym_content])

            kicad_sym = output_dir / f"{part_id}.kicad_sym"
            kicad_sym.write_text(sym_lib)

            svg_path = output_dir / f"{part_id}_symbol.svg"
            result = subprocess.run(
                [sys.executable, str(Path(__file__).parent / "kicad_sym_to_svg.py"), str(kicad_sym), str(svg_path)],
                capture_output=True,
            )
            if result.returncode == 0:
                svgs.append(svg_path)
            else:
                print(f"  Warning: Symbol SVG generation failed: {result.stderr.decode()}")
            print(
                f"  Symbol: {len(symbol.pins)} pins, {len(symbol.rectangles)} rects, "
                f"{len(symbol.polylines)} polylines, {len(symbol.arcs)} arcs"
            )
    else:
        print("  Symbol: none")

    # Footprint
    fp_data = comp.get("footprint_data", {})
    if fp_data:
        ds = fp_data.get("dataStr", {})
        if isinstance(ds, str):
            ds = json.loads(ds)
        shapes = ds.get("shape", [])
        head = ds.get("head", {})
        origin_x = head.get("x", 0)
        origin_y = head.get("y", 0)

        if shapes:
            footprint = parse_footprint_shapes(shapes, origin_x, origin_y)
            fp_content = write_footprint(footprint, title)

            kicad_mod = output_dir / f"{part_id}.kicad_mod"
            kicad_mod.write_text(fp_content)

            svg_path = output_dir / f"{part_id}_footprint.svg"
            result = subprocess.run(
                [sys.executable, str(Path(__file__).parent / "kicad_mod_to_svg.py"), str(kicad_mod), str(svg_path)],
                capture_output=True,
            )
            if result.returncode == 0:
                svgs.append(svg_path)
            else:
                print(f"  Warning: Footprint SVG generation failed: {result.stderr.decode()}")
            print(
                f"  Footprint: {len(footprint.pads)} pads, {len(footprint.tracks)} tracks, "
                f"{len(footprint.regions)} regions"
            )
    else:
        print("  Footprint: none")

    # Open SVGs
    if svgs:
        print(f"\nOpening {len(svgs)} SVG(s)...")
        for svg in svgs:
            subprocess.run(["open", str(svg)])

    return svgs


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <part_id>")
        print(f"Example: {sys.argv[0]} C558421")
        sys.exit(1)

    preview_part(sys.argv[1])
