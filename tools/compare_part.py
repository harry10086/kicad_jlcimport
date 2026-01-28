#!/usr/bin/env python3
"""Fetch JLCPCB parts, render EasyEDA and KiCad SVGs, and generate an HTML comparison page."""

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kicad_jlcimport.easyeda.api import fetch_component_uuids, fetch_full_component
from kicad_jlcimport.easyeda.parser import parse_footprint_shapes, parse_symbol_shapes
from kicad_jlcimport.kicad.footprint_writer import write_footprint
from kicad_jlcimport.kicad.library import sanitize_name
from kicad_jlcimport.kicad.symbol_writer import write_symbol, write_symbol_library

KICAD_CLI = shutil.which("kicad-cli") or "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"


def fetch_easyeda_svgs(lcsc_id: str) -> dict:
    """Fetch EasyEDA preview SVGs for a part.

    Returns dict with 'symbol_svg' and 'footprint_svg' strings (or None).
    """
    uuids = fetch_component_uuids(lcsc_id)
    symbol_svg = None
    footprint_svg = None
    for entry in uuids:
        doc_type = entry.get("docType")
        svg = entry.get("svg")
        if doc_type == 2 and symbol_svg is None:
            symbol_svg = svg
        elif doc_type == 4 and footprint_svg is None:
            footprint_svg = svg
    return {"symbol_svg": symbol_svg, "footprint_svg": footprint_svg}


def convert_to_kicad(comp: dict, tmp_dir: str) -> dict:
    """Convert component data to KiCad files.

    Returns dict with file paths, sanitized name, and metadata.
    """
    title = comp.get("title", comp["lcsc_id"])
    name = sanitize_name(title)
    lcsc_id = comp["lcsc_id"]

    result = {
        "name": name,
        "title": title,
        "lcsc_id": lcsc_id,
        "prefix": comp.get("prefix", ""),
        "manufacturer": comp.get("manufacturer", ""),
        "manufacturer_part": comp.get("manufacturer_part", ""),
        "datasheet": comp.get("datasheet", ""),
        "description": comp.get("description", ""),
        "sym_file": None,
        "fp_file": None,
    }

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
            sym_content = write_symbol(symbol, title, prefix=comp.get("prefix", "U"))
            sym_lib = write_symbol_library([sym_content])
            sym_file = Path(tmp_dir) / f"{lcsc_id}.kicad_sym"
            sym_file.write_text(sym_lib)
            result["sym_file"] = str(sym_file)

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
            # kicad-cli requires .kicad_mod inside a .pretty directory
            pretty_dir = Path(tmp_dir) / f"{lcsc_id}.pretty"
            pretty_dir.mkdir(exist_ok=True)
            fp_file = pretty_dir / f"{name}.kicad_mod"
            fp_file.write_text(fp_content)
            result["fp_file"] = str(fp_file)
            result["pretty_dir"] = str(pretty_dir)

    return result


def render_kicad_svgs(kicad_files: dict, tmp_dir: str) -> dict:
    """Render KiCad files to SVG using kicad-cli.

    Returns dict with 'symbol_svg' and 'footprint_svg' strings (or None).
    """
    result = {"symbol_svg": None, "footprint_svg": None}

    # Symbol SVG — kicad-cli sym export matches by the internal symbol name
    # (the raw title stored inside the .kicad_sym file).
    if kicad_files.get("sym_file"):
        sym_svg_dir = Path(tmp_dir) / "sym_svg"
        sym_svg_dir.mkdir(exist_ok=True)
        cmd = [
            KICAD_CLI,
            "sym",
            "export",
            "svg",
            "--symbol",
            kicad_files["title"],
            "--output",
            str(sym_svg_dir),
            kicad_files["sym_file"],
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            svg_files = list(sym_svg_dir.glob("*.svg"))
            if svg_files:
                result["symbol_svg"] = svg_files[0].read_text()
        if not result["symbol_svg"]:
            print(f"  Warning: kicad-cli sym export failed: {proc.stderr.strip()}")

    # Footprint SVG — kicad-cli fp export matches by filename, not the internal
    # name, so skip --footprint and let it export the single footprint in the dir.
    if kicad_files.get("fp_file"):
        fp_svg_dir = Path(tmp_dir) / "fp_svg"
        fp_svg_dir.mkdir(exist_ok=True)
        cmd = [
            KICAD_CLI,
            "fp",
            "export",
            "svg",
            "--output",
            str(fp_svg_dir),
            kicad_files["pretty_dir"],
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            svg_files = list(fp_svg_dir.glob("*.svg"))
            if svg_files:
                result["footprint_svg"] = svg_files[0].read_text()
        if not result["footprint_svg"]:
            print(f"  Warning: kicad-cli fp export failed: {proc.stderr.strip()}")

    return result


def strip_svg_dimensions(svg: str) -> str:
    """Remove width/height attributes from SVG, preserving viewBox for responsive sizing."""
    svg = re.sub(r'\s+width="[^"]*"', "", svg)
    svg = re.sub(r'\s+height="[^"]*"', "", svg)
    return svg


def generate_html(parts: list) -> str:
    """Build an HTML comparison page for all parts."""
    rows = []
    for part in parts:
        meta = part["metadata"]
        easyeda = part["easyeda_svgs"]
        kicad = part["kicad_svgs"]

        # Metadata header
        meta_parts = [f"LCSC: {html.escape(meta['lcsc_id'])}"]
        if meta.get("prefix"):
            meta_parts.append(f"Prefix: {html.escape(meta['prefix'])}")
        if meta.get("manufacturer"):
            meta_parts.append(f"Mfr: {html.escape(meta['manufacturer'])}")
        if meta.get("manufacturer_part"):
            meta_parts.append(html.escape(meta["manufacturer_part"]))
        datasheet_link = ""
        if meta.get("datasheet"):
            ds_url = html.escape(meta["datasheet"])
            datasheet_link = f' | <a href="{ds_url}" target="_blank">Datasheet</a>'

        title_text = html.escape(meta.get("title", meta["lcsc_id"]))
        meta_line = " | ".join(meta_parts) + datasheet_link

        # SVG cells
        def svg_cell(svg, label):
            if svg:
                return f'<div class="svg-cell">{strip_svg_dimensions(svg)}</div>'
            return f'<div class="svg-cell empty">{html.escape(label)}</div>'

        symbol_row = (
            f'<div class="compare-row">'
            f'<div class="row-label">Symbol</div>'
            f'<div class="row-pair">'
            f'<div class="col"><div class="col-label">EasyEDA</div>'
            f"{svg_cell(easyeda.get('symbol_svg'), 'No SVG')}</div>"
            f'<div class="col"><div class="col-label">KiCad</div>'
            f"{svg_cell(kicad.get('symbol_svg'), 'Render failed')}</div>"
            f"</div></div>"
        )

        footprint_row = (
            f'<div class="compare-row">'
            f'<div class="row-label">Footprint</div>'
            f'<div class="row-pair">'
            f'<div class="col"><div class="col-label">EasyEDA</div>'
            f"{svg_cell(easyeda.get('footprint_svg'), 'No SVG')}</div>"
            f'<div class="col"><div class="col-label">KiCad</div>'
            f"{svg_cell(kicad.get('footprint_svg'), 'Render failed')}</div>"
            f"</div></div>"
        )

        rows.append(
            f'<div class="part">'
            f"<h2>{title_text}</h2>"
            f'<div class="meta">{meta_line}</div>'
            f"{symbol_row}{footprint_row}"
            f"</div>"
        )

    parts_html = "\n".join(rows)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>EasyEDA vs KiCad Comparison</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         margin: 2em; background: #f5f5f5; color: #222; }}
  .part {{ background: #fff; border-radius: 8px; padding: 1.5em; margin-bottom: 2em;
           box-shadow: 0 1px 3px rgba(0,0,0,0.12); }}
  h2 {{ margin: 0 0 0.3em; }}
  .meta {{ color: #666; margin-bottom: 1em; font-size: 0.9em; }}
  .meta a {{ color: #0066cc; }}
  .compare-row {{ margin-bottom: 1.5em; }}
  .row-label {{ font-weight: 600; font-size: 1.1em; margin-bottom: 0.5em; }}
  .row-pair {{ display: flex; gap: 1em; }}
  .col {{ flex: 1; min-width: 0; }}
  .col-label {{ text-align: center; font-size: 0.85em; color: #888;
                margin-bottom: 0.3em; text-transform: uppercase; letter-spacing: 0.05em; }}
  .svg-cell {{ border: 1px solid #ddd; border-radius: 4px; padding: 1em;
               display: flex; align-items: center; justify-content: center;
               min-height: 150px; background: #fafafa; }}
  .svg-cell svg {{ max-width: 100%; max-height: 400px; }}
  .svg-cell.empty {{ color: #999; font-style: italic; }}
</style>
</head>
<body>
<h1>EasyEDA vs KiCad Comparison</h1>
{parts_html}
</body>
</html>"""


def compare_part(lcsc_id: str, tmp_dir: str) -> dict:
    """Fetch, convert, and render a single part for comparison."""
    print(f"\n--- {lcsc_id} ---")

    # Fetch EasyEDA preview SVGs
    print("  Fetching EasyEDA SVGs...")
    try:
        easyeda_svgs = fetch_easyeda_svgs(lcsc_id)
    except Exception as e:
        print(f"  Error fetching EasyEDA SVGs: {e}")
        easyeda_svgs = {"symbol_svg": None, "footprint_svg": None}

    # Fetch full component and convert to KiCad
    print("  Fetching component data...")
    try:
        comp = fetch_full_component(lcsc_id)
    except Exception as e:
        print(f"  Error fetching component: {e}")
        return {
            "metadata": {"lcsc_id": lcsc_id, "title": lcsc_id},
            "easyeda_svgs": easyeda_svgs,
            "kicad_svgs": {"symbol_svg": None, "footprint_svg": None},
        }

    part_dir = os.path.join(tmp_dir, lcsc_id)
    os.makedirs(part_dir, exist_ok=True)

    print("  Converting to KiCad...")
    kicad_files = convert_to_kicad(comp, part_dir)

    # Render KiCad SVGs
    print("  Rendering KiCad SVGs...")
    kicad_svgs = render_kicad_svgs(kicad_files, part_dir)

    metadata = {
        "lcsc_id": lcsc_id,
        "title": kicad_files["title"],
        "prefix": kicad_files["prefix"],
        "manufacturer": kicad_files["manufacturer"],
        "manufacturer_part": kicad_files["manufacturer_part"],
        "datasheet": kicad_files["datasheet"],
    }

    return {
        "metadata": metadata,
        "easyeda_svgs": easyeda_svgs,
        "kicad_svgs": kicad_svgs,
    }


def main():
    parser = argparse.ArgumentParser(description="Compare EasyEDA and KiCad renderings of JLCPCB parts")
    parser.add_argument("part_ids", nargs="+", help="LCSC part numbers (e.g. C427602)")
    parser.add_argument("--no-open", action="store_true", help="Don't open the HTML in a browser")
    parser.add_argument("--output-dir", help="Write HTML to this directory instead of a temp dir")
    args = parser.parse_args()

    # Check kicad-cli exists
    if not os.path.isfile(KICAD_CLI):
        print(f"Error: kicad-cli not found at {KICAD_CLI}")
        sys.exit(1)

    tmp_dir = tempfile.mkdtemp(prefix="kicad_compare_")
    print(f"Working directory: {tmp_dir}")

    parts = []
    for part_id in args.part_ids:
        result = compare_part(part_id, tmp_dir)
        parts.append(result)

    # Generate HTML
    html_content = generate_html(parts)

    if args.output_dir:
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        html_path = str(out_dir / "index.html")
    else:
        html_path = os.path.join(tmp_dir, "comparison.html")

    with open(html_path, "w") as f:
        f.write(html_content)

    print(f"\nHTML written to: {html_path}")

    if not args.output_dir and not args.no_open:
        webbrowser.open(f"file://{html_path}")


if __name__ == "__main__":
    main()
