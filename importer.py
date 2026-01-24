"""Shared import logic for CLI, TUI, and plugin."""
import os
from typing import Callable

from .api import fetch_full_component
from .parser import parse_footprint_shapes, parse_symbol_shapes
from .footprint_writer import write_footprint
from .symbol_writer import write_symbol
from .model3d import compute_model_transform, download_and_save_models
from .library import (
    sanitize_name,
    ensure_lib_structure,
    add_symbol_to_lib,
    save_footprint,
    update_project_lib_tables,
    update_global_lib_tables,
)


def import_component(
    lcsc_id: str,
    lib_dir: str,
    lib_name: str,
    overwrite: bool = False,
    use_global: bool = False,
    export_only: bool = False,
    log: Callable[[str], None] = print,
) -> dict:
    """Import an LCSC component into a KiCad library or export raw files.

    Args:
        lcsc_id: Validated LCSC part number (e.g. "C427602").
        lib_dir: Destination directory (project dir, global lib dir, or export dir).
        lib_name: Library name (e.g. "JLCImport").
        overwrite: Whether to overwrite existing files.
        use_global: If True, use absolute model paths and update global lib tables.
        export_only: If True, write raw .kicad_mod/.kicad_sym/3D files to a flat directory.
        log: Callback for status messages.

    Returns:
        dict with keys: title, name, fp_content, sym_content
    """
    log(f"Fetching component {lcsc_id}...")

    comp = fetch_full_component(lcsc_id)
    title = comp["title"]
    name = sanitize_name(title)
    log(f"Component: {title}")
    log(f"Prefix: {comp['prefix']}, Name: {name}")

    # Parse footprint
    log("Parsing footprint...")
    fp_shapes = comp["footprint_data"]["dataStr"]["shape"]
    footprint = parse_footprint_shapes(fp_shapes, comp["fp_origin_x"], comp["fp_origin_y"])
    log(f"  {len(footprint.pads)} pads, {len(footprint.tracks)} tracks")

    # Determine 3D model UUID and transform
    model_offset = (0.0, 0.0, 0.0)
    model_rotation = (0.0, 0.0, 0.0)
    uuid_3d = ""
    if footprint.model:
        uuid_3d = footprint.model.uuid
        model_offset, model_rotation = compute_model_transform(
            footprint.model, comp["fp_origin_x"], comp["fp_origin_y"]
        )
    if not uuid_3d:
        uuid_3d = comp.get("uuid_3d", "")

    # Parse symbol
    sym_content = ""
    if comp["symbol_data_list"]:
        log("Parsing symbol...")
        sym_data = comp["symbol_data_list"][0]
        sym_shapes = sym_data["dataStr"]["shape"]
        symbol = parse_symbol_shapes(sym_shapes, comp["sym_origin_x"], comp["sym_origin_y"])
        log(f"  {len(symbol.pins)} pins, {len(symbol.rectangles)} rects")

        footprint_ref = f"{lib_name}:{name}"
        sym_content = write_symbol(
            symbol, name, prefix=comp["prefix"],
            footprint_ref=footprint_ref,
            lcsc_id=lcsc_id,
            datasheet=comp.get("datasheet", ""),
            description=comp.get("description", ""),
            manufacturer=comp.get("manufacturer", ""),
            manufacturer_part=comp.get("manufacturer_part", ""),
        )
    else:
        log("No symbol data available")

    if export_only:
        return _export_only(
            lib_dir, name, lcsc_id, comp, footprint,
            uuid_3d, model_offset, model_rotation, lib_name,
            sym_content, title, log,
        )

    return _import_to_library(
        lib_dir, lib_name, name, lcsc_id, comp, footprint,
        uuid_3d, model_offset, model_rotation,
        use_global, overwrite, sym_content, title, log,
    )


def _export_only(
    out_dir, name, lcsc_id, comp, footprint,
    uuid_3d, model_offset, model_rotation, lib_name,
    sym_content, title, log,
):
    """Write raw .kicad_mod, .kicad_sym, and 3D models to a flat directory."""
    os.makedirs(out_dir, exist_ok=True)

    # Model path for export is relative within the output dir
    model_path = f"3dmodels/{name}.step" if uuid_3d else ""

    fp_content = write_footprint(
        footprint, name, lcsc_id=lcsc_id,
        description=comp.get("description", ""),
        datasheet=comp.get("datasheet", ""),
        model_path=model_path,
        model_offset=model_offset,
        model_rotation=model_rotation,
    )

    fp_path = os.path.join(out_dir, f"{name}.kicad_mod")
    with open(fp_path, "w") as f:
        f.write(fp_content)
    log(f"  Saved: {fp_path}")

    if sym_content:
        sym_path = os.path.join(out_dir, f"{name}.kicad_sym")
        sym_lib = (
            '(kicad_symbol_lib\n'
            '  (version 20241209)\n'
            '  (generator "JLCImport")\n'
            '  (generator_version "1.0")\n'
            + sym_content +
            ')\n'
        )
        with open(sym_path, "w") as f:
            f.write(sym_lib)
        log(f"  Saved: {sym_path}")

    if uuid_3d:
        models_dir = os.path.join(out_dir, "3dmodels")
        step_path, wrl_path = download_and_save_models(
            uuid_3d, models_dir, name, overwrite=True
        )
        if step_path:
            log(f"  Saved: {step_path}")
        if wrl_path:
            log(f"  Saved: {wrl_path}")

    return {"title": title, "name": name, "fp_content": fp_content, "sym_content": sym_content}


def _import_to_library(
    lib_dir, lib_name, name, lcsc_id, comp, footprint,
    uuid_3d, model_offset, model_rotation,
    use_global, overwrite, sym_content, title, log,
):
    """Import into KiCad library structure with lib-table updates."""
    log(f"Destination: {lib_dir}")

    paths = ensure_lib_structure(lib_dir, lib_name)

    # Download 3D models
    model_path = ""
    if uuid_3d:
        step_dest = os.path.join(paths["models_dir"], f"{name}.step")
        wrl_dest = os.path.join(paths["models_dir"], f"{name}.wrl")
        step_existed = os.path.exists(step_dest)
        wrl_existed = os.path.exists(wrl_dest)

        log("Downloading 3D model...")
        step_path, wrl_path = download_and_save_models(
            uuid_3d, paths["models_dir"], name, overwrite=overwrite
        )
        if step_path:
            if use_global:
                model_path = os.path.join(paths["models_dir"], f"{name}.step")
            else:
                model_path = f"${{KIPRJMOD}}/{lib_name}.3dshapes/{name}.step"
            if step_existed and not overwrite:
                log(f"  STEP skipped: {step_path} (exists, overwrite=off)")
            else:
                log(f"  STEP saved: {step_path}")
        if wrl_path:
            if wrl_existed and not overwrite:
                log(f"  WRL skipped: {wrl_path} (exists, overwrite=off)")
            else:
                log(f"  WRL saved: {wrl_path}")
    else:
        log("No 3D model available")

    # Write footprint
    log("Writing footprint...")
    fp_content = write_footprint(
        footprint, name, lcsc_id=lcsc_id,
        description=comp.get("description", ""),
        datasheet=comp.get("datasheet", ""),
        model_path=model_path,
        model_offset=model_offset,
        model_rotation=model_rotation,
    )
    fp_path = os.path.join(paths["fp_dir"], f"{name}.kicad_mod")
    fp_saved = save_footprint(paths["fp_dir"], name, fp_content, overwrite)
    if fp_saved:
        log(f"  Saved: {fp_path}")
    else:
        log(f"  Skipped: {fp_path} (exists, overwrite=off)")

    # Write symbol
    if sym_content:
        sym_added = add_symbol_to_lib(paths["sym_path"], name, sym_content, overwrite)
        if sym_added:
            log(f"  Symbol added: {paths['sym_path']}")
        else:
            log(f"  Symbol skipped: {paths['sym_path']} (exists, overwrite=off)")

    # Update lib tables
    if use_global:
        update_global_lib_tables(lib_dir, lib_name)
        log("Global library tables updated.")
    else:
        newly_created = update_project_lib_tables(lib_dir, lib_name)
        log("Project library tables updated.")
        if newly_created:
            log("NOTE: Reopen project for new library tables to take effect.")

    return {"title": title, "name": name, "fp_content": fp_content, "sym_content": sym_content}
