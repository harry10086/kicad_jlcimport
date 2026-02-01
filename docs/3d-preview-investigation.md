# Investigation: Adding 3D Model Snapshots to Visual Comparison Tool

## Current State

The visual comparison tool (`tools/compare_part.py`) currently shows:
- **Symbol**: EasyEDA SVG vs KiCad SVG (side-by-side)
- **Footprint**: EasyEDA SVG vs KiCad SVG (side-by-side)

Output: HTML page with embedded SVGs in iframes

## Goal

Add 3D model visualization to show:
- **3D Model**: EasyEDA view vs KiCad rendered 3D view

## Technical Investigation

### 1. KiCad 3D Rendering Capabilities

**Tool**: `kicad-cli pcb render`

**Key Features**:
```bash
kicad-cli pcb render INPUT.kicad_pcb \
  --output OUTPUT.png \
  --width 800 \
  --height 600 \
  --side top|bottom|left|right|front|back \
  --rotate X,Y,Z  # e.g., "-45,0,45" for isometric \
  --background transparent|opaque|default \
  --quality basic|high|user|job_settings \
  --zoom 1.5 \
  --floor  # adds shadows
```

**Supports**:
- Multiple viewing angles (6 sides + custom rotation)
- PNG/JPEG output
- Transparent backgrounds
- Adjustable quality, zoom, lighting

### 2. 3D Model Formats

The importer saves:
- **STEP files** (`.step`) - KiCad's preferred format
- **WRL files** (`.wrl`) - VRML 2.0 format

Workflow:
1. `download_step(uuid_3d)` - gets STEP binary data
2. `download_wrl_source(uuid_3d)` - gets OBJ-like text for VRML conversion
3. `save_models(dir, name, step_data, wrl_source)` - saves both formats

Footprint references:
```
(model "${KIPRJMOD}/LibName.3dshapes/PartName.step"
  (offset (xyz 0 0 0))
  (scale (xyz 1 1 1))
  (rotate (xyz 0 0 0))
)
```

### 3. EasyEDA 3D Preview

**Issue**: EasyEDA doesn't provide pre-rendered 3D SVGs/images like they do for symbols/footprints.

**Options**:
1. **Skip EasyEDA side** - only show KiCad 3D render
2. **Extract from EasyEDA web viewer** - scrape/screenshot (fragile)
3. **Render from OBJ data** - use python 3D rendering library (complex)

**Recommendation**: Start with option 1 (KiCad-only) for simplicity.

## Proposed Implementation

### Changes to `tools/compare_part.py`

#### 1. Extend `convert_to_kicad()` to handle 3D models:

```python
def convert_to_kicad(comp: dict, tmp_dir: str) -> dict:
    # ... existing code ...

    # Download and save 3D models
    uuid_3d = comp.get("uuid_3d", "")
    if uuid_3d:
        models_dir = Path(tmp_dir) / "3dmodels"
        models_dir.mkdir(exist_ok=True)

        step_data = download_step(uuid_3d)
        wrl_source = download_wrl_source(uuid_3d)
        step_path, wrl_path = save_models(str(models_dir), name, step_data, wrl_source)

        if step_path:
            result["step_file"] = step_path
            # Compute 3D model offsets
            offset, rotation = compute_model_transform(
                footprint.model,
                fp_origin_x,
                fp_origin_y,
                wrl_source
            )
            result["model_offset"] = offset
            result["model_rotation"] = rotation
```

#### 2. Create minimal PCB with 3D model:

```python
def _create_pcb_with_3d_model(footprint_content: str, model_path: str,
                               model_offset, model_rotation) -> str:
    """Create a minimal .kicad_pcb with footprint including 3D model reference."""
    # Update footprint content to include (model ...) section
    fp_lines = footprint_content.strip().split('\n')
    # Insert before closing )
    model_section = [
        f'  (model "{model_path}"',
        f'    (offset (xyz {model_offset[0]} {model_offset[1]} {model_offset[2]}))',
        f'    (scale (xyz 1 1 1))',
        f'    (rotate (xyz {model_rotation[0]} {model_rotation[1]} {model_rotation[2]}))',
        f'  )',
    ]
    fp_lines[-1:-1] = model_section
    updated_fp = '\n'.join(fp_lines)

    # Embed in minimal PCB
    return _create_minimal_pcb(updated_fp)
```

#### 3. Render 3D views:

```python
def render_3d_snapshot(pcb_file: str, output_dir: Path) -> dict:
    """Render 3D views from multiple angles."""
    views = {}

    # Top view (default)
    top_png = output_dir / "3d_top.png"
    subprocess.run([
        KICAD_CLI, "pcb", "render", str(pcb_file),
        "--output", str(top_png),
        "--side", "top",
        "--width", "800",
        "--height", "600",
        "--background", "transparent",
        "--quality", "high",
        "--floor",
    ])
    if top_png.exists():
        views["top"] = top_png.read_bytes()

    # Isometric view (optional)
    iso_png = output_dir / "3d_iso.png"
    subprocess.run([
        KICAD_CLI, "pcb", "render", str(pcb_file),
        "--output", str(iso_png),
        "--rotate", "-45,0,45",  # isometric angle
        "--width", "800",
        "--height", "600",
        "--background", "transparent",
        "--quality", "high",
        "--floor",
    ])
    if iso_png.exists():
        views["iso"] = iso_png.read_bytes()

    return views
```

#### 4. Update HTML generation:

```python
# Add to generate_html()
model_row = (
    '<div class="compare-row">'
    '<div class="row-label">3D Model</div>'
    '<div class="row-pair">'
    '<div class="col"><div class="col-label">KiCad Top</div>'
    f'<img src="data:image/png;base64,{base64_top}" alt="3D Top View"/>'
    '</div>'
    '<div class="col"><div class="col-label">KiCad Isometric</div>'
    f'<img src="data:image/png;base64,{base64_iso}" alt="3D Isometric View"/>'
    '</div>'
    '</div></div>'
)
```

## Challenges & Considerations

### 1. **Performance**
- 3D rendering is slow (several seconds per view)
- For 100 parts with 2 views each = ~5-10 minutes
- **Mitigation**: Add progress indicator, parallel rendering

### 2. **Model Availability**
- Not all parts have 3D models
- Need graceful fallback ("No 3D model available")

### 3. **View Selection**
- Which angles to show? Top? Isometric? Both?
- **Recommendation**: Show both top and isometric (common for datasheets)

### 4. **Image Format**
- PNG for transparency support
- Base64 embed vs separate files
- **Recommendation**: Base64 embed (simpler, single HTML file)

### 5. **CI/CD Impact**
- Visual comparison workflow will take longer
- Need to ensure KiCad has 3D rendering libs on Ubuntu
- **Test**: Verify `kicad-cli pcb render` works in GitHub Actions

## Next Steps

1. ✅ Investigation complete
2. Implement basic 3D rendering in `compare_part.py`
3. Test with parts that have 3D models (C5206, C385834, etc.)
4. Add error handling for missing models
5. Update HTML styling for 3D model row
6. Test in CI/CD environment
7. Add documentation

## Open Questions

1. Should we show EasyEDA 3D preview at all? (Currently: no, too complex)
2. Top + Isometric, or just one view? (Recommendation: both)
3. PNG size? (Recommendation: 800x600, good balance)
4. Quality setting? (Recommendation: high for final, basic for testing)
