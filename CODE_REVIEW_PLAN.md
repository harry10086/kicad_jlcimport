# Code Review: Remediation Plan

## Priority 1: Security Fixes

### S1. Fix SSL Certificate Verification (api.py)
**Risk**: MITM attacks on all network traffic
**Action**: Remove the unconditional `ssl._create_unverified_context()` on line 17. Implement a proper fallback strategy:
1. Try `ssl.create_default_context()` first (verified)
2. Only fall back to unverified if the verified context fails on an actual connection (not at module load)
3. Log a warning when falling back to unverified mode

```python
def _get_ssl_context():
    """Get SSL context with fallback for KiCad's bundled Python."""
    try:
        ctx = ssl.create_default_context()
        return ctx
    except Exception:
        import warnings
        warnings.warn("SSL certificate verification unavailable, using unverified context")
        return ssl._create_unverified_context()

_SSL_CTX = _get_ssl_context()
```

### S2. Validate LCSC IDs (api.py, dialog.py, cli.py)
**Risk**: URL injection via crafted part numbers
**Action**: Add a validation function and apply it at all entry points:

```python
import re

def validate_lcsc_id(lcsc_id: str) -> str:
    """Validate and normalize an LCSC part number. Raises ValueError if invalid."""
    lcsc_id = lcsc_id.strip().upper()
    if not lcsc_id.startswith("C"):
        lcsc_id = "C" + lcsc_id
    if not re.match(r'^C\d{1,12}$', lcsc_id):
        raise ValueError(f"Invalid LCSC part number: {lcsc_id}")
    return lcsc_id
```

Apply in `dialog.py:_on_import()`, `cli.py:cmd_import()`, and `api.py:fetch_full_component()`.

### S3. Harden File Path Construction (library.py)
**Risk**: Path traversal writing files to unexpected locations
**Action**: Enhance `sanitize_name()` to:
1. Strip all path separators (`/`, `\`, `..`)
2. Reject Windows reserved names (`CON`, `NUL`, `PRN`, etc.)
3. Validate the result is a non-empty base filename
4. Add an assertion that the final path stays within the target directory

```python
def sanitize_name(title: str) -> str:
    """Sanitize component name for KiCad file/symbol naming."""
    import re
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title)
    name = name.replace(' ', '_').replace('.', '_')
    while '__' in name:
        name = name.replace('__', '_')
    name = name.strip('_')
    # Reject reserved Windows names
    if re.match(r'^(CON|PRN|AUX|NUL|COM\d|LPT\d)$', name, re.I):
        name = '_' + name
    if not name:
        name = 'unnamed'
    return name
```

### S4. Validate Image URLs (api.py)
**Risk**: Fetching arbitrary URLs extracted from HTML
**Action**: Validate that extracted image URLs match the expected domain:

```python
if not img_url.startswith("https://assets.lcsc.com/"):
    return None
```

---

## Priority 2: Eliminate Duplicated Code

### D1-D3. Extract Shared Utilities
**Action**: Create a `_kicad_format.py` module with the shared functions:

```python
# _kicad_format.py
"""Shared formatting utilities for KiCad file output."""
import uuid as uuid_mod

def gen_uuid() -> str:
    return str(uuid_mod.uuid4())

def fmt_float(v: float) -> str:
    """Format float for KiCad output."""
    if v == int(v) and abs(v) < 1e10:
        return str(int(v))
    return f"{v:.6f}".rstrip("0").rstrip(".")

def escape_sexpr(s: str) -> str:
    """Escape special characters for S-expression strings."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
```

Update `footprint_writer.py` and `symbol_writer.py` to import from this module.

### D4. Unify SVG Arc Parsing
**Action**: Extract a shared `_parse_svg_arc_path(svg_path: str)` function in `parser.py` that returns the parsed arc parameters, used by both `_parse_fp_arc` and `_parse_sym_arc`.

### D5-D7. Refactor Dialog Image Handling
**Action**: Extract a generic image loader class or helper methods:

```python
def _draw_skeleton(self, width, height, phase):
    """Draw a shimmer skeleton frame of given dimensions."""
    ...

def _draw_no_image(self, width, height):
    """Draw a no-image placeholder of given dimensions."""
    ...

def _fetch_and_set_image(self, lcsc_url, setter_callback, request_attr):
    """Generic async image fetch pattern."""
    ...
```

### D8. Extract Model Offset Calculation
**Action**: Move the model offset calculation to a function in `parser.py` or a new `import_helpers.py`:

```python
def compute_model_offset(footprint_model, fp_origin_x, fp_origin_y):
    """Compute 3D model offset from footprint model data."""
    return (
        (footprint_model.origin_x - fp_origin_x) / 100.0,
        -(footprint_model.origin_y - fp_origin_y) / 100.0,
        footprint_model.z / 100.0,
    )
```

### D9. Unify Project Lib Table Updates
**Action**: Replace `_update_sym_lib_table` and `_update_fp_lib_table` with calls to the existing `_update_lib_table`:

```python
def update_project_lib_tables(project_dir: str, lib_name: str = "JLCImport") -> bool:
    sym_uri = f"${{KIPRJMOD}}/{lib_name}.kicad_sym"
    fp_uri = f"${{KIPRJMOD}}/{lib_name}.pretty"
    new_sym = _update_lib_table(
        os.path.join(project_dir, "sym-lib-table"),
        "sym_lib_table", lib_name, "KiCad", sym_uri
    )
    new_fp = _update_lib_table(
        os.path.join(project_dir, "fp-lib-table"),
        "fp_lib_table", lib_name, "KiCad", fp_uri
    )
    return new_sym or new_fp
```

---

## Priority 3: Best Practices

### B1. Remove Dead Code
- Remove `api.py:9-14` (the overridden try/except SSL block)
- Remove `sexpr.py` entirely (unused), or integrate it to replace string formatting in writers

### B2. Consistent Error Handling
- Make `download_step` and `download_wrl_source` raise `APIError` instead of returning `None`
- Handle errors explicitly at call sites with try/except
- Or document the contract clearly: return `None` for optional resources, raise for required ones

### B3. Add Named Constants
```python
# parser.py
MILS_PER_MM = 3.937  # EasyEDA uses 10-mil grid units
SKELETON_TIMER_MS = 30
SKELETON_PHASE_INCREMENT = 3
SKELETON_PHASE_WRAP = 200
```

### B4. Fix Thread Safety
Use a lock or unique request ID pattern:
```python
self._image_request_id += 1
request_id = self._image_request_id
# In callback:
if self._image_request_id == request_id:
    wx.CallAfter(...)
```

### B5. Add Package Configuration
Create `pyproject.toml`:
```toml
[project]
name = "kicad-jlcimport"
version = "1.0.0"
requires-python = ">=3.8"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

### B6. Fix sys.path Manipulation
Replace `cli.py:9` with proper package invocation via `-m` flag, supported by `pyproject.toml` entry points.

---

## Priority 4: Test Coverage

### Test Infrastructure Setup
1. Create `tests/` directory
2. Add `conftest.py` with shared fixtures (sample shape strings, mock API responses)
3. Add `pytest` as dev dependency

### Test Files to Create

| File | Covers | Priority |
|------|--------|----------|
| `tests/test_parser.py` | `parser.py` — pad, track, arc, pin parsing, coordinate conversion | High |
| `tests/test_footprint_writer.py` | `footprint_writer.py` — output format, edge cases | High |
| `tests/test_symbol_writer.py` | `symbol_writer.py` — output format, multi-unit | High |
| `tests/test_library.py` | `library.py` — file ops, overwrite, sanitize_name | High |
| `tests/test_api.py` | `api.py` — response parsing, error cases (mocked HTTP) | Medium |
| `tests/test_model3d.py` | `model3d.py` — VRML conversion | Medium |
| `tests/test_sexpr.py` | `sexpr.py` — rendering (if kept) | Low |
| `tests/test_cli.py` | `cli.py` — argument parsing, output | Low |

### Key Test Cases

**parser.py:**
- Parse PAD with each shape type (RECT, OVAL, ELLIPSE, POLYGON)
- Parse TRACK with valid/invalid points
- Parse ARC with various SVG path formats
- Verify `mil_to_mm` conversion accuracy
- Verify origin offset is applied correctly
- Parse PIN with various section counts
- Parse SVGNODE with valid/invalid JSON
- Edge: empty shapes list, malformed shape strings

**footprint_writer.py:**
- Generate footprint with SMD pads only
- Generate footprint with THT pads
- Generate footprint with 3D model reference
- Verify UUID uniqueness
- Verify proper escaping of special characters in properties

**library.py:**
- `sanitize_name`: special characters, unicode, empty string, reserved names
- `add_symbol_to_lib`: new file creation, append, overwrite
- `_remove_symbol`: correctly removes nested S-expressions
- `save_footprint`: overwrite flag behavior
- `update_project_lib_tables`: creates new, appends to existing

**api.py (mocked):**
- `search_components`: parse valid response, handle empty results
- `fetch_component_uuids`: success and error cases
- `validate_lcsc_id`: valid/invalid inputs
- Network error handling

---

## Implementation Order

1. **Week 1**: Security fixes (S1-S4) — highest risk
2. **Week 2**: Test infrastructure + parser tests (foundation for safe refactoring)
3. **Week 3**: Extract shared utilities (D1-D3), unify arc parsing (D4), unify lib tables (D9)
4. **Week 4**: Writer tests + library tests
5. **Week 5**: Dialog refactoring (D5-D8), best practices (B1-B6)
6. **Week 6**: API tests, CLI tests, remaining coverage

---

## Metrics Targets

| Metric | Current | Target |
|--------|---------|--------|
| Test coverage | 0% | >80% |
| Security issues | 4 critical | 0 |
| Duplicated functions | 9 instances | 0 |
| Linting warnings | N/A (no config) | 0 |
