#!/usr/bin/env python3
"""CLI tool for testing JLCImport search and import."""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from JLCImport.api import search_components, fetch_full_component, APIError, validate_lcsc_id
from JLCImport.parser import parse_footprint_shapes, parse_symbol_shapes
from JLCImport.footprint_writer import write_footprint
from JLCImport.symbol_writer import write_symbol
from JLCImport.library import sanitize_name
from JLCImport.model3d import compute_model_transform


def cmd_search(args):
    """Search for components."""
    part_type = None
    if args.type == "basic":
        part_type = "base"
    elif args.type == "extended":
        part_type = "expand"

    result = search_components(args.keyword, page_size=args.count, part_type=part_type)
    total = result["total"]
    results = result["results"]

    if args.in_stock:
        results = [r for r in results if r['stock'] and r['stock'] > 0]

    results.sort(key=lambda r: r['stock'] or 0, reverse=True)

    print(f"\n  {total} results for \"{args.keyword}\"", end="")
    if part_type:
        print(f" ({'Basic' if part_type == 'base' else 'Extended'} only)", end="")
    if args.in_stock:
        print(f" (in stock)", end="")
    print(f"\n")

    if not results:
        print("  No results found.")
        return

    # Header
    print(f"  {'#':<3} {'LCSC':<12} {'Type':<8} {'Price':>7} {'Stock':>8}  {'Part'}")
    print(f"  {'─'*3} {'─'*12} {'─'*8} {'─'*7} {'─'*8}  {'─'*30}")

    for i, r in enumerate(results, 1):
        price_str = f"${r['price']:.4f}" if r['price'] else "  N/A  "
        stock_str = f"{r['stock']:>8,}" if r['stock'] else "     N/A"
        print(f"  {i:<3} {r['lcsc']:<12} {r['type']:<8} {price_str:>7} {stock_str}  {r['model']}")
        print(f"      {r['description']}")
        print(f"      {r['package']}  {r['brand']}")

    print()


def cmd_import(args):
    """Import a component and show/save the output."""
    try:
        lcsc_id = validate_lcsc_id(args.part)
    except ValueError as e:
        print(f"  Error: {e}")
        return

    print(f"\n  Fetching {lcsc_id}...")

    try:
        comp = fetch_full_component(lcsc_id)
    except APIError as e:
        print(f"  Error: {e}")
        return

    title = comp["title"]
    name = sanitize_name(title)
    print(f"  Component: {title}")
    print(f"  Prefix: {comp['prefix']}, Name: {name}")

    # Parse footprint
    fp_shapes = comp["footprint_data"]["dataStr"]["shape"]
    footprint = parse_footprint_shapes(fp_shapes, comp["fp_origin_x"], comp["fp_origin_y"])
    print(f"  Footprint: {len(footprint.pads)} pads, {len(footprint.tracks)} tracks")

    has_tht = any(p.layer == "11" for p in footprint.pads)
    print(f"  Type: {'Through-hole' if has_tht else 'SMD'}")

    if footprint.model:
        print(f"  3D model: {footprint.model.uuid}")

    # Generate footprint
    model_path = ""
    model_offset = (0.0, 0.0, 0.0)
    model_rotation = (0.0, 0.0, 0.0)
    if footprint.model:
        model_path = f"${{KIPRJMOD}}/JLCImport.3dshapes/{name}.step"
        model_offset, model_rotation = compute_model_transform(
            footprint.model, comp["fp_origin_x"], comp["fp_origin_y"]
        )

    fp_content = write_footprint(
        footprint, name, lcsc_id=lcsc_id,
        description=comp.get("description", ""),
        datasheet=comp.get("datasheet", ""),
        model_path=model_path,
        model_offset=model_offset,
        model_rotation=model_rotation,
    )

    # Parse symbol
    sym_content = ""
    if comp["symbol_data_list"]:
        sym_data = comp["symbol_data_list"][0]
        sym_shapes = sym_data["dataStr"]["shape"]
        symbol = parse_symbol_shapes(sym_shapes, comp["sym_origin_x"], comp["sym_origin_y"])
        print(f"  Symbol: {len(symbol.pins)} pins, {len(symbol.rectangles)} rects")

        sym_content = write_symbol(
            symbol, name, prefix=comp["prefix"],
            footprint_ref=f"JLCImport:{name}",
            lcsc_id=lcsc_id,
            datasheet=comp.get("datasheet", ""),
            description=comp.get("description", ""),
            manufacturer=comp.get("manufacturer", ""),
            manufacturer_part=comp.get("manufacturer_part", ""),
        )

    # Output
    print()
    if args.output:
        out_dir = args.output
        os.makedirs(out_dir, exist_ok=True)
        fp_path = os.path.join(out_dir, f"{name}.kicad_mod")
        with open(fp_path, "w") as f:
            f.write(fp_content)
        print(f"  Saved: {fp_path}")

        if sym_content:
            sym_path = os.path.join(out_dir, f"{name}.kicad_sym_fragment")
            with open(sym_path, "w") as f:
                f.write(sym_content)
            print(f"  Saved: {sym_path}")
    else:
        if args.show == "footprint" or args.show == "both":
            print("  ── Footprint (.kicad_mod) ──")
            print(fp_content)
        if args.show == "symbol" or args.show == "both":
            if sym_content:
                print("  ── Symbol (.kicad_sym fragment) ──")
                print(sym_content)
            else:
                print("  (No symbol data)")
        if not args.show:
            print(f"  Footprint: {len(fp_content)} bytes")
            if sym_content:
                print(f"  Symbol: {len(sym_content)} bytes")
            print(f"\n  Use --show footprint|symbol|both to see output")
            print(f"  Use -o <dir> to save files")


def main():
    parser = argparse.ArgumentParser(
        description="JLCImport CLI - search and test LCSC component imports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  %(prog)s search "RP2350"
  %(prog)s search "100nF 0402" -t basic
  %(prog)s search "ESP32" -t extended -n 20 --in-stock
  %(prog)s import C42415655
  %(prog)s import C42415655 --show footprint
  %(prog)s import C427602 --show both
  %(prog)s import C427602 -o ./output
""")

    sub = parser.add_subparsers(dest="command")

    # Search subcommand
    sp = sub.add_parser("search", aliases=["s"], help="Search for components")
    sp.add_argument("keyword", help="Search term")
    sp.add_argument("-n", "--count", type=int, default=10, help="Number of results (default: 10)")
    sp.add_argument("-t", "--type", choices=["basic", "extended", "both"], default="both",
                    help="Part type filter (default: both)")
    sp.add_argument("--in-stock", action="store_true", help="Only show parts in stock")
    sp.set_defaults(func=cmd_search)

    # Import subcommand
    ip = sub.add_parser("import", aliases=["i"], help="Import a component by LCSC part number")
    ip.add_argument("part", help="LCSC part number (e.g. C427602)")
    ip.add_argument("--show", choices=["footprint", "symbol", "both"], help="Print generated output")
    ip.add_argument("-o", "--output", help="Directory to save output files")
    ip.set_defaults(func=cmd_import)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
