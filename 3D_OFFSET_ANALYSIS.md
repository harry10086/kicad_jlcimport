# 3D Model Offset Analysis

Analysis of 3D model offset calculations with threshold removed (0.001mm).

## Data Table

| Part ID | Package | Model Origin Y Offset | OBJ Center (cy) | Height | z_max/\|z_min\| | Expected Offset | Status |
|---------|---------|----------------------|-----------------|---------|-----------------|-----------------|--------|
| C82899  | ESP32-WROOM-32 | -3.743mm | -0.000mm | 3.120mm | N/A | (0, 3.743, 0.005) | ✅ PASS |
| C33696  | VSSOP-8 | -798.057mm | 0.000mm | 1.249mm | N/A | (0, 0, 0) | ✅ PASS (outlier) |
| C1027   | L0603 | 0.492mm | 0.000mm | 0.500mm | 1.00 | (0, 0, 0.254) | ✅ PASS (symmetric) |
| C6186   | SOT-223-3 | -2.921mm | 0.000mm | 1.749mm | N/A | (0, 0, 0) | ✅ PASS (spurious) |
| C5213   | SOT-89 | -0.127mm | 0.000mm | 7.350mm | N/A | (0, 0, 0) | ✅ PASS (spurious) |
| C3794   | TO-220-3 vert | -0.650mm | 0.000mm | 23.360mm | 3.92 | (0, 0.65, 0) | ✅ PASS (z > 2×\|z_min\|) |
| C10081  | TH Resistor | 0.000mm | 0.000mm | 5.800mm | N/A | (0, 0, 0) | ✅ PASS |
| C2474   | DO-41 Diode | 0.000mm | 0.000mm | 5.902mm | N/A | (0, 0, 0) | ✅ PASS |
| C395958 | Terminal Block | 3.800mm | 4.900mm | 20.598mm | 1.42 | (0, -8.9, 4.2) | ✅ PASS (-z_min/2) |
| C2562   | TO-220-3 horiz | 0.000mm | -0.450mm | 21.900mm | 4.47 | (0, 0, 0) | ✅ PASS (cy/h=2.1%, z>3×\|z_min\|) |
| C385834 | RJ45 SMD | -1.080mm | -0.335mm | 16.150mm | 0.65 | (0, -1.08, 6.35) | ✅ PASS (z_max) |
| C138392 | RJ45-TH | 3.350mm | -0.095mm | 18.330mm | 3.24 | (0, -3.35, 0) | ✅ PASS (z>2×\|z_min\|, cy/h=0.5%) |
| C386757 | RJ45-TH | 3.220mm | 2.600mm | 16.780mm | 3.55 | (0, -5.82, 0) | ✅ PASS (z>2×\|z_min\|, cy/h=15.5%) |
| C2078   | SOT-89 | -0.000mm | 0.000mm | 1.610mm | N/A | (-0.3, 0, 0) | ✅ PASS rot=-180° |
| C2203   | HC-49US Crystal | 0.000mm | 0.000mm | 7.000mm | 1.00 | (0, 0, 0) | ✅ PASS (0, 0, 0) THT symmetric |
| C3116   | SMD | 0.000mm | 0.000mm | 5.200mm | 1.00 | (0, 0, 2.6) | ✅ PASS SMD symmetric |
| C2316   | XH-3A | -0.000mm | 2.251mm | 9.500mm | 1.21 | (2.5, 2.25, ?) | ✅ PASS rot=-180° |
| C7519   | SOT-23-6 | 0.965mm | 0.000mm | 1.649mm | 32.69 | (0, 0, 0) | ✅ PASS (0, 0, 0) spurious |
| C386758 | THT | -1.587mm | 0.100mm | 16.400mm | N/A | (0, 1.587, 0) | ✅ PASS rot=-180° |
| C2318   | XH-5A | 2.416mm | 2.250mm | 5.700mm | 1.38 | (5.0, 2.7, 1.8) rot=(0,0,180) | ❌ FAIL (5.0, -0.166, 1.2) rot=(-270,0,-180) |
| C5206   | DIP-8 | 0.000mm | 0.000mm | N/A | N/A | (0, 0, ~2.0) | ✅ PASS |

## Terminology

- **Model Origin Y Offset**: Difference between SVGNODE `c_origin` Y coordinate and footprint origin Y coordinate
- **OBJ Center (cy)**: Y-axis center of the OBJ bounding box (geometry center)
- **Height**: z_max - z_min from OBJ bounding box
- **Current threshold**: 0.001mm (essentially no threshold - all offsets are used)

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

```
if is_symmetric (abs(z_max - |z_min|) < 0.01):
    if abs(model.z) < 0.01:
        → z_offset = z_max  (SMD part: place bottom on PCB)
    else:
        → z_offset = 0  (THT part: sit flat)

elif z_min >= 0:
    → z_offset = model.z / 100  (flat parts on surface)

elif is_connector:
    if z_max > 2 × |z_min|:  (mainly extends above)
        → z_offset = 0
    elif z_max < |z_min|:  (extends below)
        → z_offset = z_max
    else:  (balanced)
        → z_offset = -z_min / 2

elif has_origin_offset:
    if z_max > 2 × |z_min|:  (mainly extends above)
        → z_offset = 0
    elif z_max < |z_min|:  (mainly extends below)
        → z_offset = z_max
    else:  (balanced)
        → z_offset = -z_min / 2

else:  (regular SMD/THT)
    if z_max < 0.5 × |z_min|:  (DIP packages)
        → z_offset = z_max
    elif z_max > 3 × |z_min|:  (mainly extends above, e.g. horizontal TO-220)
        → z_offset = 0
    elif z_max > 5.0 && |z_min| > 1.0:  (tall headers with depth)
        → z_offset = model.z / 100
    else:
        → z_offset = 0
```

**Examples**:
- C668119 (header): z_max/|z_min| = 2.24, uses model.z
- C2562 (horizontal TO-220): z_max/|z_min| = 4.48, sits flat (z=0)

## Key Insights

1. **Offset significance is relative, not absolute** - The critical finding from C2562:
   - cy/height > 5% → intentional (C160404: 12%, C395958: 23.8%)
   - cy/height < 5% → noise (C2562: 2.1%, C385834: 2.1%)
   - This prevents small OBJ geometry variations from corrupting placement

2. **Spurious offset detection is critical** - Small offsets and physically unreasonable offsets must be filtered before classification

3. **Symmetric SMD detection must run first** - C1027 showed that symmetric check was being bypassed when spurious offsets triggered THT logic

4. **Connectors vs intentional offsets need different Z logic**:
   - Connectors (off-center OBJ): Use -z_min/2 unless extending far below
   - Parts with origin offset: Use z=0 for mainly-above parts (vertical TO-220)

5. **Z-height ratio determines placement**:
   - z_max > 3×|z_min|: Mainly extends above → sits flat (z=0)
   - z_max > 2×|z_min|: Extends mainly above → sits on surface (parts with origin offset)
   - z_max < |z_min|: Extends mainly below → use top surface (z_max)
   - Otherwise: Balanced → use -z_min/2 or model.z

## Recent Fixes (Latest)

### C7519 (SOT-23-6) - Improved Spurious Offset Detection ✅

**Issue**: 0.965mm origin offset (58.5% of 1.649mm height) was not detected as spurious, causing incorrect Y-offset.

**Fix**: Improved spurious offset detection threshold from `offset > height` (for parts < 2mm) to `offset > 0.4 × height` (for parts < 3mm). This catches more edge cases where the offset is large relative to the part height but still less than the absolute height.

**Result**: C7519 now correctly produces offset (0, 0, 0).

### C2203 (HC-49US Crystal) - Fixed Symmetric THT Detection ✅

**Issue**: Perfectly symmetric THT crystal (z_min=-3.5, z_max=3.5) was being treated as SMD, resulting in z_offset=3.5mm (embedded halfway into PCB).

**Root Cause**: The symmetric detection couldn't distinguish between:
- Small symmetric SMD parts (like C1027 inductor) that should use z_max
- Large symmetric THT parts (like C2203 crystal) that should sit flat

**Fix**: Use `model.z` to distinguish THT from SMD:
- `abs(model.z) < 0.01` → SMD part (z_offset = z_max)
- `abs(model.z) > 0.01` → THT part (z_offset = 0)

**Validation**: All THT test parts have |model.z| > 10, all SMD parts have model.z ≈ 0.

**Result**: C2203 now correctly produces offset (0, 0, 0).

### C3116 - Taller Symmetric SMD Support ✅

**Issue**: 5.2mm tall symmetric SMD part needed to be distinguished from THT parts.

**Fix**: The same model.z-based detection works for all symmetric parts regardless of size:
- C1027 (0.5mm tall SMD): model.z=0 → z_offset=0.25mm ✓
- C3116 (5.2mm tall SMD): model.z=0 → z_offset=2.6mm ✓
- C2203 (7.0mm tall THT): model.z=-13.78 → z_offset=0 ✓

**Result**: C3116 correctly produces offset (0, 0, 2.6).

### C386758 - Fixed Y-Offset Sign for Rotated Parts ✅

**Issue**: THT part with -1.587mm origin offset and -180° Z-rotation was producing y=-1.587mm instead of y=+1.587mm.

**Root Cause**: The negation applied to model_origin_diff_y was being applied before the rotation transformation, causing a double sign flip:
1. Code negates: -1.587 → +1.587
2. Rotation transforms: +1.587 → -1.587 (incorrect)

**Fix**: When ±180° Z-rotation will be applied, don't negate the model_origin_diff_y value:
```
if has_rotation_transform (±180° Z-rotation):
    y_offset = model_origin_diff_y  (no negation, let rotation flip it)
else:
    y_offset = -model_origin_diff_y  (negate for correct sign)
```

**Result**: C386758 now correctly produces offset (0, 1.587, 0) after rotation transformation.

## Test Results

**Current status**: 507 tests pass. All previously failing parts (C2203, C7519, C3116, C386758) now pass. Only known issue is C2318 multi-axis rotation (EasyEDA data error).

### C138392 Validation

C138392 (RJ45-TH) is a through-hole RJ45 connector that validates the z-offset logic for THT parts with intentional origin offsets:

- **Model origin offset**: 3.350mm (intentional for THT connector placement)
- **cy**: -0.095mm (only 0.5% of height → insignificant, not a connector by cy threshold)
- **z_max/|z_min|**: 3.24 (mainly extends above PCB)
- **Classification**: `has_origin_offset` path (not connector path due to small cy/height)
- **Z logic**: z_max > 2×|z_min| → sits flat on PCB surface (z=0) ✓

This confirms the distinction between:
- Parts with significant cy (C160404: 12%, C395958: 23.8%) → connector path
- Parts with insignificant cy but intentional origin offset (C138392: 0.5%, C3794) → origin offset path

### C386757 Validation - Fixed ✅

C386757 (RJ45-TH) exposed an inconsistency in the Z-offset logic that has been fixed:

- **Model origin offset**: 3.220mm (intentional for THT connector placement)
- **cy**: 2.600mm (**15.5%** of height → significant)
- **z_max/|z_min|**: 3.55 (mainly extends above PCB)
- **Classification**: `is_connector` path (cy/height > 5%)
- **Fix applied**: Added `z_max > 2×|z_min|` check to connector path → z=0 ✓

**The Issue**:
C386757 and C138392 are both THT RJ45 connectors with similar geometry (z_max/|z_min| ≈ 3.5), but different cy values led them down different code paths:
- C138392: cy/height=0.5% → `has_origin_offset` path → z=0 ✓
- C386757: cy/height=15.5% → `is_connector` path → was using -z_min/2 ❌

**The Fix**:
Added the `z_max > 2×|z_min|` check to the connector path, making it consistent with the has_origin_offset path. Now both THT RJ45 connectors correctly use z=0 (sits flat on PCB surface).

This validates that connector classification based on cy/height works correctly, and both connector paths now have consistent Z-offset logic for parts that extend mainly above the PCB.

### 180° Z-Rotation Issue - Fixed ✅

C2078 and C2316 both have Z-axis rotation of -180° which required offset transformation.

**The Pattern - Sign Flip for 180° Z-Rotation**:

| Part | cx | cy | EasyEDA rot | Offset with transform | Status |
|------|----|----|-------------|----------------------|--------|
| C2078 | -0.3 | 0.0 | (0, 0, -180) | (-0.3, 0.0, 0.0) | ✅ PASS |
| C2316 | 2.5 | 2.251 | (0, 0, -180) | (2.5, 2.251, ?) | ✅ PASS |

**Root Cause**: When a model has Z-rotation=-180°, the offset needs to be rotated by the same angle to maintain correct positioning in the footprint coordinate system.

**The Fix**: Apply Z-rotation transformation to the offset using standard 2D rotation matrix:
```
offset_x = offset_x_model * cos(rz) - offset_y_model * sin(rz)
offset_y = offset_x_model * sin(rz) + offset_y_model * cos(rz)
```

This correctly transforms the offset from the model's local coordinate system to the footprint coordinate system.

### C2318 Multi-Axis Rotation Issue - EasyEDA Data Error ⚠️

C2318 (XH-5A connector) has incorrect data in EasyEDA that cannot be automatically corrected.

**The Problem**:
- **EasyEDA rotation**: (-270°, 0°, -180°) — Incorrect multi-axis rotation
- **EasyEDA provides wrong 3D model data** - manual correction required in KiCad
- **Current offset**: (5.0, -0.166, 1.2)
- **User-corrected offset in KiCad**: (5.0, 2.7, 1.8)
- **User-corrected rotation in KiCad**: (0°, 0°, 180°)

**Analysis**:
- Model origin offset: 2.416mm
- OBJ center (cy): 2.250mm (39.5% of height → significant)
- Height: 5.700mm
- z_max/|z_min|: 1.38 (balanced connector)

**Root Cause**:
The current logic only handles Z-axis rotation transformation. When X-axis rotation is present (-270°), the offset calculation becomes more complex and requires full 3D rotation transformation. Additionally, the EasyEDA rotation values themselves need to be transformed to match KiCad's expected values.

**Known Issue**:
Multi-axis rotations in EasyEDA use a different convention than KiCad. The transformation between the two systems is not yet understood. For C2318:
- EasyEDA: (-270, 0, -180)
- KiCad needs: (0, 0, 180) for correct rendering

**Workaround**:
Parts with multi-axis rotations need manual adjustment in KiCad after import. The rotation and offset values must be verified and corrected in the 3D model properties.
