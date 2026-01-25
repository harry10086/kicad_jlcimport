"""3D model download and WRL conversion."""

import os
from typing import Optional, Tuple

from .api import download_step, download_wrl_source
from .ee_types import EE3DModel

# EasyEDA 3D coordinates use 100 units per mm
_EE_3D_UNITS_PER_MM = 100.0


def compute_model_transform(
    model: EE3DModel, fp_origin_x: float, fp_origin_y: float
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Compute 3D model offset and rotation from footprint model data.

    The c_origin in EasyEDA is just the canvas position - not relevant for KiCad.
    The footprint and 3D model are already aligned at their origins.
    Only Z offset needs to be applied.

    Returns (offset, rotation) tuples in mm.
    """
    offset = (
        0.0,
        0.0,
        model.z / _EE_3D_UNITS_PER_MM,
    )
    return offset, model.rotation


def download_and_save_models(
    uuid_3d: str,
    output_dir: str,
    name: str,
    overwrite: bool = False,
) -> Tuple[Optional[str], Optional[str]]:
    """Download STEP and WRL models, save to output_dir.

    If overwrite is False, existing files are kept and their paths are returned.
    Returns (step_path, wrl_path) - either may be None if unavailable.
    """
    os.makedirs(output_dir, exist_ok=True)

    step_path = os.path.join(output_dir, f"{name}.step")
    wrl_path = os.path.join(output_dir, f"{name}.wrl")

    output_dir_abs = os.path.abspath(output_dir)
    step_path_abs = os.path.abspath(step_path)
    wrl_path_abs = os.path.abspath(wrl_path)

    if not step_path_abs.startswith(output_dir_abs):
        raise ValueError(f"Invalid model name: {name}")
    if not wrl_path_abs.startswith(output_dir_abs):
        raise ValueError(f"Invalid model name: {name}")

    # Download STEP
    if os.path.exists(step_path) and not overwrite:
        step_out = step_path
    else:
        step_data = download_step(uuid_3d)
        if step_data:
            with open(step_path, "wb") as f:
                f.write(step_data)
            step_out = step_path
        else:
            step_out = step_path if os.path.exists(step_path) else None

    # Download and convert WRL
    if os.path.exists(wrl_path) and not overwrite:
        wrl_out = wrl_path
    else:
        wrl_source = download_wrl_source(uuid_3d)
        if wrl_source:
            wrl_content = convert_to_vrml(wrl_source)
            if wrl_content:
                with open(wrl_path, "w", encoding="utf-8") as f:
                    f.write(wrl_content)
                wrl_out = wrl_path
            else:
                wrl_out = wrl_path if os.path.exists(wrl_path) else None
        else:
            wrl_out = wrl_path if os.path.exists(wrl_path) else None

    return step_out, wrl_out


def convert_to_vrml(obj_source: str) -> Optional[str]:
    """Convert EasyEDA OBJ-like 3D text format to VRML 2.0."""
    materials = {}
    vertices = []
    shape_groups = []

    lines = obj_source.split("\n")

    # Parse materials
    current_mtl = None
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("newmtl "):
            current_mtl = {
                "name": line[7:].strip(),
                "Ka": (0.2, 0.2, 0.2),
                "Kd": (0.8, 0.8, 0.8),
                "Ks": (0, 0, 0),
                "d": 0,
            }
        elif line.startswith("Ka ") and current_mtl:
            parts = line.split()
            if len(parts) >= 4:
                current_mtl["Ka"] = (float(parts[1]), float(parts[2]), float(parts[3]))
        elif line.startswith("Kd ") and current_mtl:
            parts = line.split()
            if len(parts) >= 4:
                current_mtl["Kd"] = (float(parts[1]), float(parts[2]), float(parts[3]))
        elif line.startswith("Ks ") and current_mtl:
            parts = line.split()
            if len(parts) >= 4:
                current_mtl["Ks"] = (float(parts[1]), float(parts[2]), float(parts[3]))
        elif line.startswith("d ") and current_mtl:
            parts = line.split()
            if len(parts) >= 2:
                current_mtl["d"] = float(parts[1])
        elif line == "endmtl" and current_mtl:
            materials[current_mtl["name"]] = current_mtl
            current_mtl = None
        elif line.startswith("v ") and not line.startswith("vn") and not line.startswith("vt"):
            parts = line.split()
            if len(parts) >= 4:
                # Divide by 2.54 to convert from mils to VRML units
                x = float(parts[1]) / 2.54
                y = float(parts[2]) / 2.54
                z = float(parts[3]) / 2.54
                vertices.append((x, y, z))
        elif line.startswith("usemtl "):
            mtl_name = line[7:].strip()
            shape_groups.append({"material": mtl_name, "faces": []})
        elif line.startswith("f ") and shape_groups:
            # Parse face: f v1//n1 v2//n2 v3//n3
            parts = line.split()[1:]
            face_indices = []
            for p in parts:
                idx_str = p.split("//")[0].split("/")[0]
                try:
                    face_indices.append(int(idx_str) - 1)  # 1-based to 0-based
                except ValueError:
                    continue
            if len(face_indices) >= 3:
                shape_groups[-1]["faces"].append(face_indices)
        i += 1

    if not vertices or not shape_groups:
        return None

    # Generate VRML 2.0
    vrml_lines = ["#VRML V2.0 utf8", ""]

    for group in shape_groups:
        if not group["faces"]:
            continue

        mtl = materials.get(group["material"], {"Kd": (0.8, 0.8, 0.8), "Ks": (0, 0, 0), "d": 0})

        # Collect unique vertex indices used by this group
        used_indices = set()
        for face in group["faces"]:
            used_indices.update(face)

        # Build local index mapping
        sorted_indices = sorted(used_indices)
        global_to_local = {g: local_idx for local_idx, g in enumerate(sorted_indices)}

        # Build point array
        points = []
        for gi in sorted_indices:
            if gi < len(vertices):
                v = vertices[gi]
                points.append(f"{v[0]:.6f} {v[1]:.6f} {v[2]:.6f}")

        # Build coordIndex
        coord_indices = []
        for face in group["faces"]:
            local_face = [str(global_to_local[gi]) for gi in face if gi in global_to_local]
            if len(local_face) >= 3:
                coord_indices.append(", ".join(local_face) + ", -1")

        if not points or not coord_indices:
            continue

        kd = mtl.get("Kd", (0.8, 0.8, 0.8))
        ks = mtl.get("Ks", (0, 0, 0))
        transparency = mtl.get("d", 0)

        vrml_lines.append("Shape {")
        vrml_lines.append("  appearance Appearance {")
        vrml_lines.append("    material Material {")
        vrml_lines.append(f"      diffuseColor {kd[0]:.4f} {kd[1]:.4f} {kd[2]:.4f}")
        vrml_lines.append(f"      specularColor {ks[0]:.4f} {ks[1]:.4f} {ks[2]:.4f}")
        vrml_lines.append("      ambientIntensity 0.2")
        vrml_lines.append(f"      transparency {transparency:.4f}")
        vrml_lines.append("      shininess 0.5")
        vrml_lines.append("    }")
        vrml_lines.append("  }")
        vrml_lines.append("  geometry IndexedFaceSet {")
        vrml_lines.append("    ccw TRUE")
        vrml_lines.append("    solid FALSE")
        vrml_lines.append("    coord DEF co Coordinate {")
        vrml_lines.append("      point [")
        for pt in points:
            vrml_lines.append(f"        {pt},")
        vrml_lines.append("      ]")
        vrml_lines.append("    }")
        vrml_lines.append("    coordIndex [")
        for ci in coord_indices:
            vrml_lines.append(f"      {ci},")
        vrml_lines.append("    ]")
        vrml_lines.append("  }")
        vrml_lines.append("}")
        vrml_lines.append("")

    return "\n".join(vrml_lines)
