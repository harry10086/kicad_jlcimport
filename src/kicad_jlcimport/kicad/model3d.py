"""3D model transforms, WRL conversion, and file saving."""

import math
import os
from typing import Optional, Tuple

from ..easyeda.ee_types import EE3DModel

# EasyEDA 3D coordinates use 100 units per mm
_EE_3D_UNITS_PER_MM = 100.0


def compute_model_transform(
    model: EE3DModel,
    fp_origin_x: float,
    fp_origin_y: float,
    obj_source: Optional[str] = None,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Compute 3D model offset and rotation from footprint model data.

    When *obj_source* is provided the XY bounding-box centre of the OBJ
    vertex data is used to correct the model origin.  The EasyEDA OBJ
    coordinates are in **mm** and the centre tells us how far the
    model's geometry is from (0, 0).  Negating the centre recentres the
    model on the footprint origin.

    For through-hole parts (detected when model origin differs from
    footprint origin), special offset calculations are applied to
    account for the model placement in EasyEDA.

    Returns (offset, rotation) tuples in mm.
    """
    cx, cy = 0.0, 0.0
    z_min, z_max = 0.0, 0.0

    if obj_source is not None:
        cx, cy, z_min, z_max = _obj_bounding_box(obj_source)

    # Check if model origin differs from footprint origin
    _MILS_TO_MM = 3.937
    model_origin_diff_y = (model.origin_y - fp_origin_y) / _MILS_TO_MM

    # Calculate height for relative thresholds
    height = z_max - z_min if obj_source else 0.0

    # Spurious offset detection - filter EasyEDA data errors
    is_spurious = False
    if abs(model_origin_diff_y) < 0.5:
        # Small offsets < 0.5mm are noise/measurement errors
        is_spurious = True
    elif height > 0 and height < 3.0 and abs(model_origin_diff_y) > 0.4 * height:
        # Physically unreasonable: offset > 40% of height for short parts
        is_spurious = True
    elif abs(model_origin_diff_y) > 50.0:
        # Outliers > 50mm are EasyEDA data errors
        is_spurious = True

    # Connector detection: cy/height > 5% AND has depth
    is_connector = False
    if obj_source and height > 0:
        cy_ratio = abs(cy) / height
        is_connector = cy_ratio > 0.05 and z_min < -0.001

    # Origin offset detection (after spurious filtering)
    has_origin_offset = not is_spurious and abs(model_origin_diff_y) > 0.5

    # Check if rotation transformation will be applied
    has_rotation_transform = abs(abs(model.rotation[2]) - 180.0) < 0.1

    if obj_source is not None:
        # Y offset calculation
        if is_connector:
            # Connector: use cy with optional model origin adjustment
            if abs(model_origin_diff_y) > 0.5 and abs(cy) < 0.5:
                y_offset = -model_origin_diff_y
            elif abs(model_origin_diff_y) > 0.5:
                y_offset = -cy - model_origin_diff_y
            else:
                y_offset = -cy
        elif has_origin_offset:
            # Origin offset: use model origin difference
            if abs(cy) < 0.5:
                # Sign depends on whether rotation transformation will be applied
                if has_rotation_transform:
                    y_offset = model_origin_diff_y
                else:
                    y_offset = -model_origin_diff_y
            else:
                y_offset = -cy - model_origin_diff_y
        else:
            # Regular: use cy only if significant (> 5% of height)
            if height > 0 and abs(cy) / height > 0.05:
                y_offset = -cy
            else:
                # cy is insignificant, likely modeling error
                y_offset = 0.0

        # Z offset calculation
        is_symmetric = z_min < 0 and abs(z_max - abs(z_min)) < 0.01

        if is_symmetric:
            # Distinguish THT from SMD using model.z (THT parts have non-zero z)
            if abs(model.z) < 0.01:
                # SMD part (model.z ≈ 0): place bottom on PCB
                z_offset = z_max
            else:
                # THT part (model.z ≠ 0, e.g., through-hole crystal): sit flat
                z_offset = 0.0
        elif z_min >= 0:
            # Flat parts on surface
            z_offset = model.z / _EE_3D_UNITS_PER_MM
        elif is_connector or has_origin_offset:
            # Connectors and parts with origin offset
            if z_max > 2 * abs(z_min):
                # Mainly extends above PCB
                z_offset = 0.0
            elif z_max < abs(z_min):
                # Extends mainly below PCB
                z_offset = z_max
            else:
                # Balanced
                z_offset = -z_min / 2
        else:
            # Regular SMD/THT parts
            if z_max < 0.5 * abs(z_min):
                # DIP packages extending far below
                z_offset = z_max
            elif z_max > 3 * abs(z_min):
                # Mainly extends above (e.g., horizontal TO-220)
                z_offset = 0.0
            elif z_max > 5.0 and abs(z_min) > 1.0:
                # Tall headers with depth
                z_offset = model.z / _EE_3D_UNITS_PER_MM
            else:
                # Normal THT parts
                z_offset = 0.0

        offset = (-cx, y_offset, z_offset)
    else:
        # No OBJ data: default z-offset to 0 (model.z is unreliable)
        offset = (-cx, -cy, 0.0)

    # Apply Z-rotation transformation for ±180° rotations
    rz = model.rotation[2]
    if abs(abs(rz) - 180.0) < 0.1:
        # Apply 2D rotation to XY offset
        rz_rad = math.radians(rz)
        cos_rz = math.cos(rz_rad)
        sin_rz = math.sin(rz_rad)
        offset_x_rot = offset[0] * cos_rz - offset[1] * sin_rz
        offset_y_rot = offset[0] * sin_rz + offset[1] * cos_rz
        offset = (offset_x_rot, offset_y_rot, offset[2])

    return offset, model.rotation


def _obj_bounding_box(obj_source: str) -> Tuple[float, float, float, float]:
    """Return XY center and Z range of OBJ vertex data (cx, cy, z_min, z_max in mm)."""
    min_x = min_y = min_z = float("inf")
    max_x = max_y = max_z = float("-inf")
    found = False

    for line in obj_source.split("\n"):
        line = line.strip()
        if not line.startswith("v ") or line.startswith("vn") or line.startswith("vt"):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
        except ValueError:
            continue
        min_x, max_x = min(min_x, x), max(max_x, x)
        min_y, max_y = min(min_y, y), max(max_y, y)
        min_z, max_z = min(min_z, z), max(max_z, z)
        found = True

    if not found:
        return 0.0, 0.0, 0.0, 0.0

    cx = (min_x + max_x) / 2
    cy = (min_y + max_y) / 2
    return cx, cy, min_z, max_z


def _obj_xy_center(obj_source: str) -> Tuple[float, float]:
    """Return the XY bounding-box centre of OBJ vertex data (in mm).

    Deprecated: Use _obj_bounding_box for new code.
    """
    cx, cy, _, _ = _obj_bounding_box(obj_source)
    return cx, cy


def save_models(
    output_dir: str,
    name: str,
    step_data: Optional[bytes] = None,
    wrl_source: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Save STEP and WRL model files to *output_dir*.

    *step_data* — raw STEP bytes (``None`` to skip saving).
    *wrl_source* — OBJ-like text to convert to VRML (``None`` to skip).

    Existing files on disk are returned even when new data is not provided.
    Returns *(step_path, wrl_path)* — either may be ``None``.
    """
    os.makedirs(output_dir, exist_ok=True)

    step_path = os.path.join(output_dir, f"{name}.step")
    wrl_path = os.path.join(output_dir, f"{name}.wrl")

    output_dir_abs = os.path.abspath(output_dir)
    if not os.path.abspath(step_path).startswith(output_dir_abs):
        raise ValueError(f"Invalid model name: {name}")
    if not os.path.abspath(wrl_path).startswith(output_dir_abs):
        raise ValueError(f"Invalid model name: {name}")

    # Save STEP
    if step_data is not None:
        with open(step_path, "wb") as f:
            f.write(step_data)
        step_out = step_path
    elif os.path.exists(step_path):
        step_out = step_path
    else:
        step_out = None

    # Convert and save WRL
    if wrl_source is not None:
        wrl_content = convert_to_vrml(wrl_source)
        if wrl_content:
            with open(wrl_path, "w", encoding="utf-8") as f:
                f.write(wrl_content)
            wrl_out = wrl_path
        elif os.path.exists(wrl_path):
            wrl_out = wrl_path
        else:
            wrl_out = None
    elif os.path.exists(wrl_path):
        wrl_out = wrl_path
    else:
        wrl_out = None

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
