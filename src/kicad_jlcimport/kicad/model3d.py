"""3D model transforms, WRL conversion, and file saving."""

import math
import os
from typing import Optional, Tuple

from ..easyeda.ee_types import EE3DModel

# ============================================================================
# Unit Conversion Constants
# ============================================================================

# EasyEDA uses a coordinate system where 1 unit = 10 mils = 0.254mm
# Conversion factor: 1 / 0.254 = 3.937 (to convert EasyEDA units to mm)
# Note: 1 mil = 0.001 inch = 0.0254mm, so 10 mils = 0.254mm
_EE_UNITS_TO_MM = 3.937

# SVGNODE z field uses the same unit system (10 mils = 0.254mm per unit)
# This was discovered by comparing EasyEDA UI values with raw data
# Example: z=-13.7795 EasyEDA units = -13.7795 × 0.254mm = -3.5mm
_Z_EE_UNITS_TO_MM = 3.937

# ============================================================================
# Spurious Offset Detection Thresholds
# ============================================================================

# Model origin offsets smaller than this are likely noise/measurement errors
_SPURIOUS_OFFSET_MIN_MM = 0.5

# For parts shorter than this, apply relative offset threshold check
_SHORT_PART_HEIGHT_MM = 3.0

# For short parts, offsets greater than this fraction of height are unreasonable
# (e.g., 0.965mm offset on 1.649mm part = 58.5% is clearly wrong)
_SPURIOUS_OFFSET_HEIGHT_RATIO = 0.4

# Model origin offsets larger than this are EasyEDA data errors
_SPURIOUS_OFFSET_MAX_MM = 50.0

# ============================================================================
# Connector Detection Thresholds
# ============================================================================

# If OBJ center (cy) is more than this fraction of part height, it's a connector
# (Empirically derived: C160404 @ 12%, C395958 @ 23.8% are connectors,
#  C2562 @ 2.1%, C385834 @ 2.1% are not)
_CONNECTOR_CY_HEIGHT_RATIO = 0.05

# Minimum depth below PCB to be considered a connector (mm)
_CONNECTOR_MIN_DEPTH_MM = 0.001

# Threshold for "small" cy values that should be ignored (mm)
_SMALL_CY_THRESHOLD_MM = 0.5

# ============================================================================
# Symmetric Part Detection Thresholds
# ============================================================================

# If z_max and |z_min| differ by less than this, part is symmetric (mm)
_SYMMETRIC_Z_TOLERANCE_MM = 0.01

# If model.z is less than this, part is SMD (not THT)
# Note: model.z is in EasyEDA 3D units, so this is 0.01 * 100 = 1 unit
# Empirically: THT parts have |model.z| > 10 units, SMD have ~0 units
_SMD_MODEL_Z_THRESHOLD = 0.01

# ============================================================================
# Z-Offset Calculation Thresholds
# ============================================================================

# If z_max > this ratio × |z_min|, part mainly extends above PCB
_Z_MAINLY_ABOVE_RATIO_CONNECTOR = 2.0  # For connectors and origin offset parts
_Z_MAINLY_ABOVE_RATIO_REGULAR = 3.0  # For regular parts

# If z_max < this ratio × |z_min|, part mainly extends below PCB (DIP packages)
_Z_MAINLY_BELOW_RATIO = 0.5

# Tall headers: if z_max > this and |z_min| > min_depth, use model.z
_TALL_HEADER_MIN_HEIGHT_MM = 5.0
_TALL_HEADER_MIN_DEPTH_MM = 1.0

# ============================================================================
# Rotation Transformation Thresholds
# ============================================================================

# Tolerance for detecting ±180° Z-rotation (degrees)
_ROTATION_180_TOLERANCE_DEG = 0.1


# ============================================================================
# Helper Functions
# ============================================================================


def _is_spurious_offset(model_origin_diff_y: float, height: float) -> bool:
    """Check if model origin offset is spurious (EasyEDA data error).

    Three types of spurious offsets:
    1. Very small offsets (< 0.5mm) - noise/measurement errors
    2. Physically unreasonable offsets for short parts (offset > 40% of height)
    3. Absurdly large offsets (> 50mm) - obvious data errors

    These checks run in sequence; once an offset is flagged as spurious,
    no further checks are needed (hence the if/elif structure).

    Args:
        model_origin_diff_y: Y offset between model origin and footprint origin (mm)
        height: Part height from OBJ bounding box (z_max - z_min, mm)

    Returns:
        True if offset should be ignored as spurious
    """
    abs_offset = abs(model_origin_diff_y)

    # Check 1: Small offsets are noise
    if abs_offset < _SPURIOUS_OFFSET_MIN_MM:
        return True

    # Check 2: For short parts, offset > 40% of height is unreasonable
    # (e.g., 0.965mm offset on 1.649mm tall SOT-23-6 is 58.5% - clearly wrong)
    if height > 0 and height < _SHORT_PART_HEIGHT_MM:
        if abs_offset > _SPURIOUS_OFFSET_HEIGHT_RATIO * height:
            return True

    # Check 3: Absurdly large offsets are EasyEDA data errors
    # (e.g., 798mm offset on C33696)
    if abs_offset > _SPURIOUS_OFFSET_MAX_MM:
        return True

    return False


def _is_connector(cy: float, height: float, z_min: float) -> bool:
    """Check if part is a connector based on OBJ geometry.

    Connectors are identified by:
    1. Off-center geometry (cy/height > 5%)
    2. Depth below PCB (z_min < 0)

    Args:
        cy: Y-axis center of OBJ bounding box (mm)
        height: Part height (z_max - z_min, mm)
        z_min: Minimum Z coordinate from OBJ (mm)

    Returns:
        True if part should be classified as a connector
    """
    if height <= 0:
        return False

    cy_ratio = abs(cy) / height
    has_depth = z_min < -_CONNECTOR_MIN_DEPTH_MM

    return cy_ratio > _CONNECTOR_CY_HEIGHT_RATIO and has_depth


def _has_180_degree_rotation(rotation_z: float) -> bool:
    """Check if model has ±180° Z-rotation.

    Args:
        rotation_z: Z-axis rotation in degrees

    Returns:
        True if rotation is within tolerance of ±180°
    """
    return abs(abs(rotation_z) - 180.0) < _ROTATION_180_TOLERANCE_DEG


def _calculate_y_offset_connector(cy: float, model_origin_diff_y: float) -> float:
    """Calculate Y offset for connector parts.

    Connectors use OBJ center (cy) as the primary offset source,
    with optional model origin adjustment.

    Args:
        cy: Y-axis center of OBJ bounding box (mm)
        model_origin_diff_y: Y offset between model and footprint origins (mm)

    Returns:
        Y offset in mm
    """
    has_origin_offset = abs(model_origin_diff_y) > _SPURIOUS_OFFSET_MIN_MM
    cy_is_small = abs(cy) < _SMALL_CY_THRESHOLD_MM

    if has_origin_offset and cy_is_small:
        # Use model origin offset when cy is negligible
        return -model_origin_diff_y
    elif has_origin_offset:
        # Combine both offsets
        return -cy - model_origin_diff_y
    else:
        # Use cy only
        return -cy


def _calculate_y_offset_origin_offset(cy: float, model_origin_diff_y: float, has_180_rotation: bool) -> float:
    """Calculate Y offset for parts with intentional model origin offset.

    The sign convention depends on whether a ±180° rotation will be applied:
    - With rotation: use offset as-is (rotation will flip it)
    - Without rotation: negate offset (standard convention)

    This prevents double-negation when rotation transformation is applied later.

    Args:
        cy: Y-axis center of OBJ bounding box (mm)
        model_origin_diff_y: Y offset between model and footprint origins (mm)
        has_180_rotation: Whether model has ±180° Z-rotation

    Returns:
        Y offset in mm
    """
    cy_is_small = abs(cy) < _SMALL_CY_THRESHOLD_MM

    if cy_is_small:
        # cy is negligible, use model origin offset only
        # Sign convention: if ±180° rotation will be applied, don't negate
        # (the rotation matrix will handle the sign flip)
        if has_180_rotation:
            return model_origin_diff_y
        else:
            return -model_origin_diff_y
    else:
        # Combine cy and model origin offset
        return -cy - model_origin_diff_y


def _calculate_y_offset_regular(cy: float, height: float) -> float:
    """Calculate Y offset for regular parts (not connectors, no origin offset).

    Only use cy if it's significant (> 5% of height), otherwise treat as
    modeling error and ignore.

    Args:
        cy: Y-axis center of OBJ bounding box (mm)
        height: Part height (z_max - z_min, mm)

    Returns:
        Y offset in mm
    """
    if height > 0 and abs(cy) / height > _CONNECTOR_CY_HEIGHT_RATIO:
        return -cy
    else:
        # cy is insignificant relative to height, likely modeling error
        return 0.0


def _apply_rotation_transform(offset: Tuple[float, float, float], rotation_z: float) -> Tuple[float, float, float]:
    """Apply 2D rotation transformation to XY offset for ±180° rotations.

    When a model has Z-rotation of ±180°, the offset must be rotated by the
    same angle to maintain correct positioning in the footprint coordinate system.

    Uses standard 2D rotation matrix:
        x' = x*cos(θ) - y*sin(θ)
        y' = x*sin(θ) + y*cos(θ)

    Args:
        offset: (x, y, z) offset in mm
        rotation_z: Z-axis rotation in degrees

    Returns:
        Transformed (x, y, z) offset in mm
    """
    if not _has_180_degree_rotation(rotation_z):
        return offset

    rz_rad = math.radians(rotation_z)
    cos_rz = math.cos(rz_rad)
    sin_rz = math.sin(rz_rad)

    x_rot = offset[0] * cos_rz - offset[1] * sin_rz
    y_rot = offset[0] * sin_rz + offset[1] * cos_rz

    return (x_rot, y_rot, offset[2])


# ============================================================================
# Main Transform Function
# ============================================================================


def compute_model_transform(
    model: EE3DModel,
    fp_origin_x: float,
    fp_origin_y: float,
    obj_source: Optional[str] = None,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """Compute 3D model offset and rotation from footprint model data.

    This function calculates the translation offset and rotation needed to
    correctly position a 3D model in KiCad based on EasyEDA model data.

    The calculation involves:
    1. Parsing OBJ bounding box to determine model geometry
    2. Detecting spurious offsets (EasyEDA data errors)
    3. Classifying part type (connector, origin offset, symmetric, regular)
    4. Calculating Y and Z offsets based on classification
    5. Applying rotation transformation for ±180° rotations

    Args:
        model: EasyEDA 3D model data (contains origin, z-offset, rotation)
        fp_origin_x: Footprint origin X coordinate (in EasyEDA mils)
        fp_origin_y: Footprint origin Y coordinate (in EasyEDA mils)
        obj_source: Optional OBJ file content for geometry analysis

    Returns:
        Tuple of (offset, rotation) where:
        - offset: (x, y, z) translation in mm
        - rotation: (rx, ry, rz) rotation in degrees
    """
    # Parse OBJ geometry if available
    cx, cy = 0.0, 0.0
    z_min, z_max = 0.0, 0.0

    if obj_source is not None:
        cx, cy, z_min, z_max = _obj_bounding_box(obj_source)

    # Calculate model origin difference (convert from EasyEDA units to mm)
    model_origin_diff_y = (model.origin_y - fp_origin_y) / _EE_UNITS_TO_MM

    # Calculate part height for relative threshold checks
    height = z_max - z_min if obj_source else 0.0

    # Classify part and calculate offsets
    if obj_source is not None:
        # Detect spurious offsets (EasyEDA data errors)
        spurious = _is_spurious_offset(model_origin_diff_y, height)

        # Classify part type
        connector = _is_connector(cy, height, z_min)
        origin_offset = not spurious and abs(model_origin_diff_y) > _SPURIOUS_OFFSET_MIN_MM
        has_180_rot = _has_180_degree_rotation(model.rotation[2])

        # Calculate Y offset based on classification
        if connector:
            y_offset = _calculate_y_offset_connector(cy, model_origin_diff_y)
        elif origin_offset:
            y_offset = _calculate_y_offset_origin_offset(cy, model_origin_diff_y, has_180_rot)
        else:
            y_offset = _calculate_y_offset_regular(cy, height)

        # Calculate Z offset using universal formula
        # Places model so that: bottom of model (z_min) + EasyEDA offset = final position
        # For THT parts: positions leads correctly below PCB
        # For SMD parts (model.z=0): places bottom at PCB surface
        z_offset = -z_min + (model.z / _Z_EE_UNITS_TO_MM)

        # Combine X (from OBJ center), Y (calculated), and Z (calculated)
        offset = (-cx, y_offset, z_offset)
    else:
        # No OBJ data: use simple offset calculation
        # Note: z-offset defaults to 0 as model.z is unreliable without OBJ data
        offset = (-cx, -cy, 0.0)

    # Apply rotation transformation for ±180° Z-rotations
    offset = _apply_rotation_transform(offset, model.rotation[2])

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
