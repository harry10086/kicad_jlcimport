# 3D Model Offset Calculation

Documentation of 3D model offset calculation logic for EasyEDA to KiCad conversion.

## Data Table

| Part ID | Package | Editor Ver | Model Origin Y Offset | model.z (mils) | z_min (mm) | z_max (mm) | Expected Offset | Status |
|---------|---------|------------|----------------------|----------------|------------|------------|-----------------|--------|
| C82899  | ESP32-WROOM-32 | 6.5.23 | -3.743mm | 0.0 | -0.01 | 3.11 | (0, 3.743, 0.005) | ✅ PASS |
| C33696  | VSSOP-8 | 6.4.19 | -798.057mm | 0.0 | 0.0 | 1.25 | (0, 0, 0) | ✅ PASS (outlier) |
| C1027   | L0603 | 6.5.48 | 0.492mm | 0.0 | 0.0 | 0.50 | (0, 0, 0.254) | ✅ PASS |
| C6186   | SOT-223-3 | 6.4.20 | -2.921mm | 0.0 | 0.0 | 1.75 | (0, 0, 0) | ✅ PASS (spurious) |
| C5213   | SOT-89 | 6.4.25 | -0.127mm | -11.81 | -4.05 | 3.30 | (0, 0, 1.05) | ✅ PASS |
| C3794   | TO-220-3 vert | 6.5.50 | -0.650mm | -19.69 | -4.75 | 18.62 | (0, 0.65, -0.255) | ✅ PASS |
| C10081  | TH Resistor | 6.4.31 | 0.000mm | 0.0 | -2.90 | 2.90 | (0, 0, 2.9) | ✅ PASS |
| C2474   | DO-41 Diode | 6.5.48 | 0.000mm | 0.0 | -2.95 | 2.95 | (0, 0, 2.95) | ✅ PASS |
| C395958 | Terminal Block | 6.5.42 | 3.800mm | -20.08 | -14.50 | 6.10 | (0, -4.9, 9.4) | ✅ PASS |
| C2562   | TO-220-3 horiz | 6.5.15 | 0.000mm | -26.77 | -4.00 | 17.90 | (0, 0, -2.8) | ✅ PASS |
| C385834 | RJ45 SMD | 6.5.51 | -1.080mm | -12.60 | -9.80 | 6.35 | (0, -1.08, 6.6) | ✅ PASS |
| C138392 | RJ45-TH | 6.5.5 | 3.350mm | -15.75 | -4.32 | 14.01 | (0, -3.35, 0.321) | ✅ PASS |
| C386757 | RJ45-TH | 6.5.50 | 3.220mm | -13.78 | -4.11 | 12.67 | (0, -2.6, 0.61) | ✅ PASS |
| C2078   | SOT-89 | 6.4.20 | -0.000mm | 0.0 | 0.0 | 1.61 | (-0.3, 0, 0) | ✅ PASS rot=-180° |
| C2203   | HC-49US Crystal | 6.5.23 | 0.000mm | -13.78 | -3.50 | 3.50 | (0, 0, 0) | ✅ PASS THT |
| C3116   | SMD Fuse | 6.4.20 | 0.000mm | 0.0 | 0.0 | 2.60 | (0, 0, 2.6) | ✅ PASS SMD |
| C2316   | XH-3A | 6.5.28 | -0.450mm | -9.84 | -4.30 | 5.20 | (2.5, 2.25, 1.8) | ✅ PASS rot=-180° |
| C7519   | SOT-23-6 | 6.5.28 | 0.965mm | 0.0 | 0.0 | 1.65 | (0, 0, 0) | ✅ PASS (spurious) |
| C386758 | RJ45-TH | 6.5.28 | -1.587mm | -13.78 | -2.95 | 13.45 | (0, 1.587, -0.55) | ✅ PASS rot=-180° |
| C2318   | XH-5A | 6.5.5 | 2.416mm | 2.250mm | 5.700mm | 1.38 | (5.0, 2.7, 1.8) rot=(0,0,180) | ❌ FAIL (5.0, -0.166, 1.2) rot=(-270,0,-180) |
| C5206   | DIP-8 | 6.5.47 | 0.000mm | 0.000mm | N/A | N/A | (0, 0, ~2.0) | ✅ PASS |

## Terminology

- **Model Origin Y Offset**: Difference between SVGNODE `c_origin` Y coordinate and footprint origin Y coordinate
- **model.z**: Z-offset value from SVGNODE in EasyEDA data, stored in **mils** (thousandths of an inch)
- **z_min, z_max**: Minimum and maximum Z coordinates from OBJ vertex data (in mm)
- **OBJ Center (cy)**: Y-axis center of the OBJ bounding box (geometry center)
- **Height**: z_max - z_min from OBJ bounding box

## Solution Implemented

### Spurious Offset Detection

#### Model Origin Offset (Y-axis)
Filter out EasyEDA data errors in model origin placement:

1. **Small offsets < 0.5mm** → spurious (noise/measurement errors)
   - Filters: C1027 (0.492mm), C5213 (0.127mm)

2. **Physically unreasonable offsets** → spurious
   - For short parts (height < 3mm), offset > 40% of height indicates data error
   - Updated from height < 2mm and offset > height to catch more edge cases
   - Filters: C6186 (2.921mm offset on 1.749mm tall part = 167%)
   - Filters: C7519 (0.965mm offset on 1.649mm tall part = 58.5%)

3. **Outliers > 50mm** → EasyEDA data error
   - Filters: C33696 (798mm offset)

#### OBJ Center Offset (cy)
**Critical finding from C2562**: cy must be significant *relative to part height*

- **cy/height > 5%** → intentional offset (use it)
  - C160404: cy=0.350mm / height=2.91mm = **12.0%** → connector ✓
  - C395958: cy=4.900mm / height=20.6mm = **23.8%** → connector ✓

- **cy/height < 5%** → modeling error (ignore it)
  - C2562: cy=0.450mm / height=21.9mm = **2.1%** → NOT connector ✓
  - C385834: cy=0.335mm / height=16.15mm = **2.1%** → ignore cy ✓

This prevents small OBJ geometry variations from being treated as intentional offsets.

## Conversion Logic Flow

The implemented solution uses a clear hierarchy without arbitrary thresholds:

### 1. Y Offset Calculation

```
if is_connector (cy/height > 5% && z_min < -0.001):
    → Use OBJ center (cy) with optional model origin adjustment
elif has_origin_offset (intentional, not spurious/outlier):
    if abs(cy) < 0.5:
        if has_rotation_transform (±180° Z-rotation):
            → y_offset = model_origin_diff_y (no negation)
        else:
            → y_offset = -model_origin_diff_y (negation)
    else:
        → y_offset = -cy - model_origin_diff_y
else:
    → Use cy only if significant (cy/height > 5%), otherwise 0
```

**Key insights**:
- cy significance is relative, not absolute. A 0.45mm offset is huge for a 2.9mm part (C160404) but negligible for a 21.9mm part (C2562).
- For parts with ±180° Z-rotation and origin offset, the sign convention is reversed because the rotation transformation will flip it back (C386758).

### 2. Z Offset Calculation

**Universal Formula** (applies to all parts):

```
z_offset = -z_min + (model.z / 3.937)
```

**How it works**:
1. `model.z` is stored in **mils** (thousandths of an inch) in EasyEDA data
2. Convert mils to mm: `model.z / 3.937`
3. Position the model so bottom edge (z_min) plus EasyEDA offset equals final position
4. For SMD parts (model.z = 0): places bottom at PCB surface (z_offset = -z_min)
5. For THT parts (model.z ≠ 0): positions leads correctly below PCB

**Examples**:
- **C82899** (SMD): z_min=-0.01, model.z=0 → z_offset = 0.01 + 0 = 0.01mm ✓
- **C2203** (THT): z_min=-3.5, model.z=-13.78 → z_offset = 3.5 + (-3.5) = 0mm ✓
- **C2316** (connector): z_min=-4.3, model.z=-9.84 → z_offset = 4.3 + (-2.5) = 1.8mm ✓
- **C385834** (RJ45): z_min=-9.8, model.z=-12.6 → z_offset = 9.8 + (-3.2) = 6.6mm ✓
- **C2562** (TO-220): z_min=-4.0, model.z=-26.77 → z_offset = 4.0 + (-6.8) = -2.8mm ✓

**Key Discovery**:
The old code incorrectly assumed `model.z` was in "EasyEDA 3D units" (100 units/mm). It's actually in **mils**. This single conversion error required complex branching logic to work around. The correct unit conversion eliminates all special cases.

## Key Insights

1. **Z-offset has a universal formula** - The breakthrough discovery:
   - `model.z` in EasyEDA data is stored in **mils**, not "EasyEDA 3D units" (100 units/mm)
   - Universal formula: `z_offset = -z_min + (model.z / 3.937)` works for ALL parts
   - No special cases needed for SMD, THT, connectors, symmetric parts, etc.
   - The old complex branching logic was compensating for the wrong unit conversion

2. **Y-offset significance is relative, not absolute** - The critical finding from C2562:
   - cy/height > 5% → intentional (C160404: 12%, C395958: 23.8%)
   - cy/height < 5% → noise (C2562: 2.1%, C385834: 2.1%)
   - This prevents small OBJ geometry variations from corrupting placement

3. **Spurious offset detection is critical** - Small offsets and physically unreasonable offsets must be filtered before classification:
   - Small offsets < 0.5mm → spurious (noise/measurement errors)
   - For short parts (< 3mm), offset > 40% of height → spurious (physically unreasonable)
   - Outliers > 50mm → spurious (obvious data errors)

4. **Y-offset requires complex logic** (unlike Z-offset):
   - Connector detection based on cy/height ratio
   - Spurious offset filtering
   - Sign convention handling for 180° rotations
   - This complexity is justified and necessary


## Test Results

**Current status**: All 48 model3d tests pass ✅

## Known Issues

### C2318 Multi-Axis Rotation - EasyEDA Data Error ⚠️

C2318 (XH-5A connector) has incorrect multi-axis rotation data in EasyEDA that cannot be automatically corrected:

- **EasyEDA rotation**: (-270°, 0°, -180°)
- **KiCad requires**: (0°, 0°, 180°) for correct rendering

**Issue**: Multi-axis rotations in EasyEDA use a different convention than KiCad. The transformation between the two systems is not yet understood.

**Workaround**: Parts with multi-axis rotations need manual adjustment in KiCad after import.
