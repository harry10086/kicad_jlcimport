# Manual Testing

## Visual Comparison Testing

The `tools/compare_part.py` script fetches EasyEDA preview SVGs and renders the KiCad conversion output side-by-side in an HTML page. Use this before releases to verify that symbols and footprints convert correctly across a variety of real-world parts.

### Prerequisites

- KiCad installed at `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli`
- Virtual environment activated: `source install.sh`

### Running

```bash
source install.sh
python3 tools/compare_part.py <LCSC_ID> [<LCSC_ID> ...]
```

Options:
- `--no-open` — generate the HTML without opening it in a browser

The script writes an HTML comparison page to a temp directory and opens it in your default browser.

### What to check

For each part, compare the EasyEDA (source) and KiCad (output) renderings:

- **Symbols**: Pin count, pin numbers, pin names, pin placement, body shape
- **Footprints**: Pad count, pad shapes and sizes, silk screen markings (+/- polarity, pin 1 indicators), outline shape

### Pre-release regression suite

Run the full 100-part comparison across ICs, passives, LEDs, transistors, connectors, and other component types:

```bash
python3 tools/compare_part.py C82899 C7593 C5213 C5423 C7950 C9418 C33696 C71101 C6970 C21235 C23892 C6186 C6187 C6188 C12087 C14529 C347218 C347219 C3794 C5586 C5206 C5602 C8760 C8852 C13885 C15157 C18901 C20953 C10081 C94598 C94599 C138392 C385834 C386756 C386757 C386758 C52016391 C5177 C15134 C24112 C2957 C2960 C67528 C85181 C2102 C2135 C2474 C2476 C2478 C2479 C173573 C173580 C173602 C1027 C1034 C2286 C2288 C2290 C2295 C2297 C12889 C15331 C2078 C2560 C2561 C2562 C2564 C2566 C2079 C2173 C2914 C3795 C3797 C2040 C2316 C2318 C2319 C2320 C2321 C2322 C2202 C2203 C2213 C3099 C3105 C3116 C3117 C5419 C5612 C5613 C6203 C6205 C7519 C15999 C6179 C6855 C6912 C7063 C1002 C1035
```
