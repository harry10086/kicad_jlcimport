# JLCImport

A KiCad 9 Action Plugin that imports symbols, footprints, and 3D models directly from LCSC/JLCPCB into your KiCad project or global library.

![Search and details](images/search_results.png)

![Gallery view](images/gallery.png)

## Features

- Search the JLCPCB parts catalog with filtering (Basic/Extended, minimum stock)
- Preview product images with full-screen gallery view
- Import symbols, footprints, and STEP/WRL 3D models
- Sortable results by price, stock, part number, etc.
- Checkmark (✓) indicator on parts already imported to your library
- Import to project folder or global 3rd-party library
- Links to datasheets and LCSC product pages
- CLI tool for scripted/batch imports

## Installation

### Find your KiCad plugins directory

| OS | Path |
|----|------|
| macOS | `~/Documents/KiCad/9.0/scripting/plugins/` |
| Linux | `~/.local/share/kicad/9.0/scripting/plugins/` |
| Windows | `%APPDATA%\kicad\9.0\scripting\plugins\` |

> Replace `9.0` with your KiCad version if different.

### Option 1: Symlink (recommended for development)

```bash
ln -s /path/to/kicad_jlcimport ~/Documents/KiCad/9.0/scripting/plugins/kicad_jlcimport
```

### Option 2: Copy

```bash
cp -r /path/to/kicad_jlcimport ~/Documents/KiCad/9.0/scripting/plugins/kicad_jlcimport
```

### Activate

1. Restart KiCad
2. Open the PCB Editor
3. The plugin appears in **Tools > External Plugins > JLCImport**

## Usage

### Plugin Dialog

1. Open the PCB Editor and launch **JLCImport** from the External Plugins menu
2. Type a search query (e.g. "100nF 0402", "ESP32", "RP2350")
3. Filter by type (Basic/Extended/Both) and minimum stock level
4. Parts already in your library are marked with ✓ in the results list
5. Click a result to see details, product image, and description
6. Click the thumbnail to open the full-screen gallery with arrow navigation
7. Choose a destination:
   - **Project** — saves to the current board's directory (`JLCImport.kicad_sym`, `JLCImport.pretty/`, `JLCImport.3dshapes/`)
   - **Global** — saves to KiCad's 3rd-party library folder
8. Click **Import** to download and save the symbol, footprint, and 3D model

> **Note:** If library tables (`sym-lib-table` / `fp-lib-table`) are newly created, reopen the project for them to take effect.

### CLI

The CLI tool can be used outside KiCad for testing or scripted imports:

```bash
# Search (default: --min-stock 1, only shows parts in stock)
python3 -m kicad_jlcimport.cli search "100nF 0402" -t basic
python3 -m kicad_jlcimport.cli search "ESP32" -n 20 --min-stock 100

# Search with CSV output
python3 -m kicad_jlcimport.cli search "RP2350" --csv > parts.csv

# Import (prints generated output)
python3 -m kicad_jlcimport.cli import C427602 --show both

# Import to directory (saves .kicad_sym, .kicad_mod, and 3D models)
python3 -m kicad_jlcimport.cli import C427602 -o ./output
```

### TUI

A terminal-based interface with image preview support (Sixel, Kitty, iTerm2, or halfcell fallback).

![TUI interface](images/tui.png)

```bash
# Install dependencies
pip install textual textual-image[textual] Pillow

# Run with project directory
python3 -m kicad_jlcimport.tui -p /path/to/kicad/project

# Run without project (global library only)
python3 -m kicad_jlcimport.tui
```

Requires Python 3.10+.

## How It Works

JLCImport fetches component data from the EasyEDA/LCSC API, parses the proprietary shape format, and converts it to KiCad 9 file formats:

- **Symbols** → `.kicad_sym` (version 20241209)
- **Footprints** → `.kicad_mod` (version 20241229)
- **3D Models** → `.step` and `.wrl`

The plugin automatically creates and updates `sym-lib-table` and `fp-lib-table` entries so imported parts are immediately available in your schematic and PCB editors.

## Requirements

- KiCad 9.0+
- Python 3 (bundled with KiCad)
- Internet connection

No additional Python packages are required — the plugin uses only the standard library (`urllib`, `json`, `ssl`, `io`, `threading`) and `wx` (bundled with KiCad).

## License

See [LICENSE](LICENSE) for details.
