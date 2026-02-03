# 3D Model Handling

## Model Format

EasyEDA provides 3D models in OBJ format. We convert these to both:
- **WRL (VRML 2.0)** - Used in KiCad footprint references
- **STEP** - Saved for compatibility but not referenced

### Why WRL instead of STEP?

Our offset calculations analyze the OBJ/WRL geometry (bounding box, center point). WRL files maintain the exact same geometry and coordinate system as the OBJ source. STEP files can have different origins/orientations after conversion, causing mismatches between calculated offsets and actual model placement.

Both files are saved, but KiCad footprints reference the WRL for consistency.

## Offset Calculation

The 3D model offset has two independent components:

### 1. Geometry Offset

Compensates for the 3D model's bounding box not being centered at the origin. Calculated in **model space**, so it rotates with the model:

```
geometry = (-cx, -cy_effective, z_offset)
```

Where:
- `cx, cy` = OBJ bounding box center
- `cy_effective` = cy only if significant (|cy|/height > 5%), else 0
- `z_offset = -z_min + (model.z / 3.937)` (universal formula)

The geometry offset is then rotated by the model's Z-axis rotation to transform from model space to footprint space.

### 2. Origin Offset

Compensates for EasyEDA's model origin differing from the footprint origin. Calculated in **footprint space**, so it's NOT rotated:

```
origin = (-diff_x, -diff_y, 0)
```

Where `diff_x`, `diff_y` are the differences between model origin and footprint origin in EasyEDA units, converted to mm.

**Spurious offset filtering:** Small offsets (<0.5mm), unreasonable offsets (>40% of height for parts <3mm tall), and outliers (>50mm) are treated as EasyEDA data errors and zeroed out.

### Final Offset

```
offset = (geometry_x + origin_x, geometry_y + origin_y, geometry_z)
```

## Unit Conversions

EasyEDA uses a coordinate system where **1 unit = 10 mils = 0.254mm**.

Conversion factors:
- `3.937 = 1/0.254` (EasyEDA units → mm)
- Both XY coordinates and Z offsets use the same unit system

## Implementation

See `src/kicad_jlcimport/kicad/model3d.py`:
- `compute_model_transform()` - Main offset/rotation calculation
- `save_models()` - Saves STEP and WRL files
- `convert_to_vrml()` - OBJ to VRML 2.0 conversion
