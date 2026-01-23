#!/usr/bin/env python3
"""TUI (Text User Interface) for JLCImport using Textual."""
from __future__ import annotations

import io
import os
import sys
import traceback
import webbrowser

from PIL import Image as PILImage
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    RadioButton,
    RadioSet,
    RichLog,
    Select,
)
from textual_image.widget import Image as _AutoTIImage, HalfcellImage as _HalfcellTIImage, SixelImage as _SixelTIImage

# Warp terminal falsely reports Sixel support via device attributes query,
# so force half-cell rendering there.
# Rio supports Sixel but doesn't advertise it in DA1 response.
_term_program = os.environ.get("TERM_PROGRAM", "")
if _term_program == "WarpTerminal":
    TIImage = _HalfcellTIImage
elif _term_program == "rio":
    TIImage = _SixelTIImage
else:
    TIImage = _AutoTIImage

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kicad_jlcimport.api import (
    fetch_full_component,
    search_components,
    fetch_product_image,
    filter_by_min_stock,
    filter_by_type,
    APIError,
    validate_lcsc_id,
)
from kicad_jlcimport.parser import parse_footprint_shapes, parse_symbol_shapes
from kicad_jlcimport.footprint_writer import write_footprint
from kicad_jlcimport.symbol_writer import write_symbol
from kicad_jlcimport.model3d import download_and_save_models, compute_model_transform
from kicad_jlcimport.library import (
    ensure_lib_structure,
    add_symbol_to_lib,
    save_footprint,
    update_project_lib_tables,
    update_global_lib_tables,
    get_global_lib_dir,
    sanitize_name,
)


# --- Image Helpers ---


def _pil_from_bytes(data: bytes | None) -> PILImage.Image | None:
    """Convert raw image bytes to a PIL Image, or None."""
    if not data:
        return None
    try:
        return PILImage.open(io.BytesIO(data))
    except Exception:
        return None


def _make_skeleton_frame(width: int, height: int, phase: int) -> PILImage.Image:
    """Generate a skeleton shimmer frame as a PIL Image.

    Draws a dark gray rectangle with a lighter band sweeping left to right.
    """
    import math
    from PIL import ImageDraw
    img = PILImage.new("RGB", (width, height), (30, 30, 30))
    draw = ImageDraw.Draw(img)
    band_center = int(phase * (width + width // 2) / 100) - width // 4
    band_width = width // 3
    half_band = band_width // 2
    for x in range(max(0, band_center - half_band), min(width, band_center + half_band)):
        t = abs(x - band_center) / half_band
        boost = int(20 * (1 + math.cos(t * math.pi)) / 2)
        if boost > 0:
            c = 30 + boost
            draw.line([(x, 0), (x, height - 1)], fill=(c, c, c))
    return img


class GalleryScreen(Screen):
    """Full-screen gallery view for component images."""

    BINDINGS = [
        Binding("escape", "close", "Back"),
        Binding("left", "prev", "Previous"),
        Binding("right", "next", "Next"),
    ]

    CSS = """
    GalleryScreen {
        background: #0a0a0a;
    }
    #gallery-container {
        width: 100%;
        height: 100%;
        align: center middle;
    }
    #gallery-image-wrap {
        width: 100%;
        height: 1fr;
        align: center middle;
        padding: 1 2;
    }
    #gallery-image {
        width: auto;
        height: 100%;
    }
    #gallery-info {
        text-align: center;
        width: 100%;
        height: 1;
        color: #aaaaaa;
    }
    #gallery-desc {
        text-align: center;
        width: 100%;
        height: 1;
        color: #666666;
        margin-bottom: 1;
    }
    #gallery-nav {
        height: 1;
        width: 100%;
        align: center middle;
    }
    #gallery-nav Button {
        height: 1;
        min-height: 1;
        border: none;
        padding: 0 2;
        background: #1a1a1a;
        color: #33ff33;
        margin: 0 1;
    }
    """

    def __init__(self, results: list, index: int = 0):
        super().__init__()
        self._results = results
        self._index = index
        self._image_cache: dict[int, bytes | None] = {}
        self._skeleton_timer = None
        self._skeleton_phase: int = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="gallery-container"):
            with Horizontal(id="gallery-nav"):
                yield Button("\u25C0 Prev", id="gallery-prev", variant="default")
                yield Button("Back", id="gallery-back", variant="primary")
                yield Button("Next \u25B6", id="gallery-next", variant="default")
            with Container(id="gallery-image-wrap"):
                yield TIImage(id="gallery-image")
            yield Label("", id="gallery-info")
            yield Label("", id="gallery-desc")

    def on_mount(self):
        self._update_gallery()

    def _update_gallery(self):
        if not self._results:
            return
        r = self._results[self._index]

        # Update info
        price_str = f"${r['price']:.4f}" if r['price'] else "N/A"
        stock_str = f"{r['stock']:,}" if r['stock'] else "N/A"
        info = f"{r['lcsc']}  |  {r['model']}  |  {r['brand']}  |  {r['package']}  |  {price_str}  |  Stock: {stock_str}"
        self.query_one("#gallery-info", Label).update(info)
        self.query_one("#gallery-desc", Label).update(r.get("description", ""))

        # Update nav buttons
        self.query_one("#gallery-prev", Button).disabled = self._index <= 0
        self.query_one("#gallery-next", Button).disabled = self._index >= len(self._results) - 1

        # Load image
        img_widget = self.query_one("#gallery-image", TIImage)
        if self._index in self._image_cache:
            self._stop_skeleton()
            img_widget.image = _pil_from_bytes(self._image_cache[self._index])
        else:
            self._start_skeleton()
            self._fetch_image(self._index)

    @work(thread=True)
    def _fetch_image(self, index: int):
        """Fetch image in background thread."""
        r = self._results[index]
        lcsc_url = r.get("url", "")
        img_data = None
        if lcsc_url:
            try:
                img_data = fetch_product_image(lcsc_url)
            except Exception:
                pass
        self._image_cache[index] = img_data
        self.app.call_from_thread(self._set_image, index, img_data)

    def _set_image(self, index: int, img_data: bytes | None):
        if index == self._index:
            self._stop_skeleton()
            self.query_one("#gallery-image", TIImage).image = _pil_from_bytes(img_data)

    def _start_skeleton(self):
        self._stop_skeleton()
        self._skeleton_phase = 0
        img_widget = self.query_one("#gallery-image", TIImage)
        img_widget.image = _make_skeleton_frame(200, 200, 0)
        self._skeleton_timer = self.set_interval(1 / 15, self._on_skeleton_tick)

    def _on_skeleton_tick(self):
        self._skeleton_phase = (self._skeleton_phase + 5) % 100
        img_widget = self.query_one("#gallery-image", TIImage)
        img_widget.image = _make_skeleton_frame(200, 200, self._skeleton_phase)

    def _stop_skeleton(self):
        if self._skeleton_timer:
            self._skeleton_timer.stop()
            self._skeleton_timer = None

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "gallery-prev":
            self.action_prev()
        elif event.button.id == "gallery-next":
            self.action_next()
        elif event.button.id == "gallery-back":
            self.action_close()

    def action_close(self):
        self.app.pop_screen()

    def action_prev(self):
        if self._index > 0:
            self._index -= 1
            self._update_gallery()

    def action_next(self):
        if self._index < len(self._results) - 1:
            self._index += 1
            self._update_gallery()


class JLCImportTUI(App):
    """TUI application for JLCImport - search and import JLCPCB components."""

    TITLE = "JLCImport"
    SUB_TITLE = ""

    CSS = """
    Screen {
        background: #0a0a0a;
    }

    /* Compact all widgets globally */
    Button {
        height: 1;
        min-height: 1;
        border: none;
        padding: 0 1;
        background: #1a1a1a;
        color: #33ff33;
    }
    Button:hover { background: #2a2a2a; }
    Button:focus { background: #2a2a2a; text-style: bold; }
    Button.-primary { color: #33ff33; }
    Button.-success { color: #33ff33; text-style: bold; }
    Input {
        height: 1;
        border: none;
        padding: 0;
        background: #1a1a1a;
        color: #cccccc;
    }
    Input:focus { border: none; background: #222222; }
    Select {
        height: 1;
        border: none;
        padding: 0;
        background: #1a1a1a;
    }
    SelectCurrent {
        height: 1;
        border: none;
        padding: 0;
    }
    RadioButton {
        height: 1;
        padding: 0;
        background: transparent;
    }
    RadioSet {
        height: 1;
        layout: horizontal;
        background: transparent;
        border: none;
    }
    Checkbox {
        height: 1;
        border: none;
        padding: 0;
        background: transparent;
    }
    DataTable {
        background: #0a0a0a;
    }
    DataTable > .datatable--header { color: #33ff33; text-style: bold; background: #1a1a1a; }
    DataTable > .datatable--cursor { background: #1a3a1a; }
    Header { background: #1a1a1a; color: #33ff33; }
    Footer { background: #1a1a1a; }
    RichLog { background: #0a0a0a; }
    Label { color: #aaaaaa; }

    #main-container {
        width: 100%;
        height: 100%;
    }

    /* Search: single compact row */
    #search-section {
        height: auto;
        padding: 1 0 0 1;
    }
    #search-row {
        height: 1;
        width: 100%;
    }
    #search-input { width: 1fr; }
    #search-btn { margin-left: 1; }
    #filter-row {
        height: 1;
        width: 100%;
        margin-top: 1;
    }
    #type-filter RadioButton { width: auto; margin-right: 1; }
    #min-stock-select { width: 14; margin: 0 1; }
    #package-select { width: 18; margin: 0 1; }
    #results-count {
        height: 1;
        color: #666666;
        padding-left: 1;
    }

    /* Results */
    #results-section {
        height: 1fr;
        min-height: 6;
    }
    #results-table { height: 100%; }

    /* Detail: compact horizontal layout */
    #detail-section {
        height: auto;
        border-top: solid #333333;
        padding: 0;
    }
    #detail-content { height: auto; }
    #detail-image {
        width: 22;
        height: 10;
        margin-right: 1;
    }
    #detail-info { width: 1fr; height: 10; }
    .detail-field { height: 1; }
    #detail-desc { height: auto; max-height: 3; width: 100%; color: #666666; }
    #detail-buttons {
        dock: bottom;
        height: 1;
        margin-left: 1;
        margin-bottom: 1;
    }
    #detail-buttons Button { margin-right: 1; }

    /* Import: single compact row */
    #import-section {
        height: auto;
        border-top: solid #333333;
        padding: 0;
    }
    #dest-selector RadioButton { width: auto; margin-right: 2; }
    #import-options {
        height: auto;
        width: 100%;
    }
    #part-input { width: 16; }
    #overwrite-cb { margin: 0 1; width: auto; }
    #import-btn { margin-left: 1; }

    /* Status */
    #status-section {
        height: 6;
        min-height: 4;
        border-top: solid #333333;
    }
    #status-log { height: 100%; }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+g", "gallery", "Gallery", show=True),
        Binding("ctrl+s", "focus_search", "Search", show=True),
        Binding("f5", "do_search", "Search", show=False),
    ]

    _MIN_STOCK_OPTIONS = [
        ("Any", 0),
        ("1+", 1),
        ("10+", 10),
        ("100+", 100),
        ("1K+", 1000),
        ("10K+", 10000),
        ("100K+", 100000),
    ]

    def __init__(self, project_dir: str = ""):
        super().__init__()
        self._project_dir = project_dir
        try:
            self._global_lib_dir = get_global_lib_dir()
        except Exception:
            self._global_lib_dir = "(unavailable)"
        self._search_results: list = []
        self._raw_search_results: list = []
        self._sort_col: int = -1
        self._sort_ascending: bool = True
        self._imported_ids: set = set()
        self._selected_index: int = -1
        self._detail_image_data: bytes | None = None
        self._image_request_id: int = 0
        self._datasheet_url: str = ""
        self._lcsc_page_url: str = ""
        self._pulse_timer = None
        self._pulse_phase: int = 0
        self._skeleton_timer = None
        self._skeleton_phase: int = 0
        self._col_names = ["LCSC", "Type", "Price", "Stock", "Part", "Package", "Description"]

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="main-container"):
            with Vertical(id="search-section"):
                with Horizontal(id="search-row"):
                    yield Input(
                        placeholder="Search JLCPCB parts...",
                        id="search-input",
                    )
                    yield Button("Search", id="search-btn", variant="primary")
                with Horizontal(id="filter-row"):
                    with RadioSet(id="type-filter"):
                        yield RadioButton("Both", value=True, id="type-both")
                        yield RadioButton("Basic", id="type-basic")
                        yield RadioButton("Extended", id="type-extended")
                    yield Select(
                        [(label, val) for label, val in self._MIN_STOCK_OPTIONS],
                        value=1,
                        id="min-stock-select",
                        allow_blank=False,
                    )
                    yield Select(
                        [("All", "")],
                        value="",
                        id="package-select",
                        allow_blank=False,
                    )

            yield Label("", id="results-count")

            with Container(id="results-section"):
                yield DataTable(id="results-table", cursor_type="row")

            with Vertical(id="detail-section"):
                with Horizontal(id="detail-content"):
                    yield TIImage(id="detail-image")
                    with Vertical(id="detail-info"):
                        yield Label("", id="detail-part", classes="detail-field")
                        yield Label("", id="detail-lcsc", classes="detail-field")
                        yield Label("", id="detail-brand-pkg", classes="detail-field")
                        yield Label("", id="detail-price-stock", classes="detail-field")
                        yield Label("", id="detail-desc")
                        with Horizontal(id="detail-buttons"):
                            yield Button("Import", id="detail-import-btn", variant="success", disabled=True)
                            yield Button("Datasheet", id="detail-datasheet-btn", disabled=True)
                            yield Button("LCSC", id="detail-lcsc-btn", disabled=True)

            with Vertical(id="import-section"):
                with Horizontal(id="import-options"):
                    with RadioSet(id="dest-selector"):
                        yield RadioButton(
                            f"Proj:{self._project_dir or 'n/a'}",
                            value=bool(self._project_dir),
                            id="dest-project",
                        )
                        yield RadioButton(
                            "Global",
                            value=not bool(self._project_dir),
                            id="dest-global",
                        )
                    yield Input(placeholder="C427602", id="part-input")
                    yield Checkbox("Overwrite", id="overwrite-cb")
                    yield Button("Import", id="import-btn", variant="success")

            with Container(id="status-section"):
                yield RichLog(id="status-log", highlight=True, markup=True)

        yield Footer()

    def on_mount(self):
        """Set up the results table columns."""
        table = self.query_one("#results-table", DataTable)
        table.add_columns("LCSC", "Type", "Price", "Stock", "Part", "Package", "Description")
        if not self._project_dir:
            self.query_one("#dest-project", RadioButton).disabled = True
        self.query_one("#search-input", Input).focus()

    def _log(self, msg: str):
        """Write a message to the status log."""
        log = self.query_one("#status-log", RichLog)
        log.write(msg)

    # --- Search ---

    def on_input_submitted(self, event: Input.Submitted):
        """Handle Enter key in search input."""
        if event.input.id == "search-input":
            self._do_search()

    def on_button_pressed(self, event: Button.Pressed):
        """Handle button clicks."""
        button_id = event.button.id
        if button_id == "search-btn":
            self._do_search()
        elif button_id == "import-btn" or button_id == "detail-import-btn":
            self._do_import_action()
        elif button_id == "detail-datasheet-btn":
            if self._datasheet_url:
                webbrowser.open(self._datasheet_url)
        elif button_id == "detail-lcsc-btn":
            if self._lcsc_page_url:
                webbrowser.open(self._lcsc_page_url)

    def action_focus_search(self):
        """Focus the search input."""
        self.query_one("#search-input", Input).focus()

    def action_do_search(self):
        self._do_search()

    def action_gallery(self):
        """Open gallery view."""
        if self._search_results:
            idx = max(0, self._selected_index)
            self.push_screen(GalleryScreen(self._search_results, idx))

    def _start_search_pulse(self):
        """Animate dots on the search button."""
        self._pulse_phase = 0
        btn = self.query_one("#search-btn", Button)
        btn.label = "\u00b7"
        btn.disabled = True
        self._pulse_timer = self.set_interval(0.3, self._on_pulse_tick)

    def _on_pulse_tick(self):
        """Cycle through dot animation."""
        self._pulse_phase = (self._pulse_phase + 1) % 3
        self.query_one("#search-btn", Button).label = "\u00b7" * (self._pulse_phase + 1)

    def _stop_search_pulse(self):
        """Stop animation and restore button."""
        if self._pulse_timer:
            self._pulse_timer.stop()
            self._pulse_timer = None
        btn = self.query_one("#search-btn", Button)
        btn.label = "Search"
        btn.disabled = False

    def _start_skeleton(self):
        """Start skeleton shimmer on detail image."""
        self._stop_skeleton()
        self._skeleton_phase = 0
        img_widget = self.query_one("#detail-image", TIImage)
        img_widget.image = _make_skeleton_frame(100, 100, 0)
        self._skeleton_timer = self.set_interval(1 / 15, self._on_skeleton_tick)

    def _on_skeleton_tick(self):
        """Advance skeleton shimmer."""
        self._skeleton_phase = (self._skeleton_phase + 5) % 100
        img_widget = self.query_one("#detail-image", TIImage)
        img_widget.image = _make_skeleton_frame(100, 100, self._skeleton_phase)

    def _stop_skeleton(self):
        """Stop skeleton animation."""
        if self._skeleton_timer:
            self._skeleton_timer.stop()
            self._skeleton_timer = None

    @work(thread=True)
    def _do_search(self):
        """Perform the search in a background thread.

        Fetches up to 500 results and applies client-side filters.
        """
        search_input = self.query_one("#search-input", Input)
        keyword = search_input.value.strip()
        if not keyword:
            return

        self.app.call_from_thread(self._log, f"Searching for \"{keyword}\"...")
        self.app.call_from_thread(self._start_search_pulse)

        try:
            result = search_components(keyword, page_size=500)
            results = result["results"]

            results.sort(key=lambda r: r["stock"] or 0, reverse=True)

            self._raw_search_results = results
            self._sort_col = 3  # sorted by stock
            self._sort_ascending = False
            self._selected_index = -1

            self.app.call_from_thread(self._populate_package_choices)
            self.app.call_from_thread(self._apply_filters)
            self.app.call_from_thread(
                self._log,
                f"  {result['total']} total results, showing {len(self._search_results)}",
            )
            self.app.call_from_thread(self._refresh_imported_ids)
            self.app.call_from_thread(self._update_sort_indicators)
            self.app.call_from_thread(self._repopulate_results)

        except APIError as e:
            self.app.call_from_thread(self._log, f"[red]Search error: {e}[/red]")
        except Exception as e:
            self.app.call_from_thread(
                self._log, f"[red]Error: {type(e).__name__}: {e}[/red]"
            )
        finally:
            self.app.call_from_thread(self._stop_search_pulse)

    # --- Filtering ---

    def _get_type_filter(self) -> str:
        """Return the selected type filter value ('Basic', 'Extended', or '')."""
        type_filter = self.query_one("#type-filter", RadioSet)
        if type_filter.pressed_index == 1:
            return "Basic"
        elif type_filter.pressed_index == 2:
            return "Extended"
        return ""

    def _get_min_stock(self) -> int:
        """Return the minimum stock threshold from the dropdown."""
        select = self.query_one("#min-stock-select", Select)
        val = select.value
        return val if isinstance(val, int) else 0

    def _get_package_filter(self) -> str:
        """Return the selected package filter value."""
        select = self.query_one("#package-select", Select)
        val = select.value
        return val if isinstance(val, str) else ""

    def _populate_package_choices(self):
        """Populate the package dropdown from current raw results."""
        packages = sorted(set(
            r.get("package", "") for r in self._raw_search_results
            if r.get("package")
        ))
        options = [("All", "")] + [(p, p) for p in packages]
        select = self.query_one("#package-select", Select)
        select.set_options(options)

    def _apply_filters(self):
        """Apply type, stock, and package filters to _raw_search_results."""
        filtered = filter_by_type(self._raw_search_results, self._get_type_filter())
        filtered = filter_by_min_stock(filtered, self._get_min_stock())
        pkg = self._get_package_filter()
        if pkg:
            filtered = [r for r in filtered if r.get("package") == pkg]
        self._search_results = filtered

    def on_select_changed(self, event: Select.Changed):
        """Re-filter when min-stock or package selection changes."""
        if event.select.id in ("min-stock-select", "package-select"):
            if self._raw_search_results:
                self._apply_filters()
                self._repopulate_results()

    def on_radio_set_changed(self, event: RadioSet.Changed):
        """Re-filter when type filter changes."""
        if event.radio_set.id == "type-filter":
            if self._raw_search_results:
                self._apply_filters()
                self._repopulate_results()

    def _refresh_imported_ids(self):
        """Scan symbol libraries for already-imported LCSC IDs."""
        import re as _re

        self._imported_ids = set()
        paths = []
        if self._project_dir:
            paths.append(os.path.join(self._project_dir, "JLCImport.kicad_sym"))
        try:
            global_dir = get_global_lib_dir()
            paths.append(os.path.join(global_dir, "JLCImport.kicad_sym"))
        except Exception:
            pass
        for p in paths:
            try:
                if os.path.exists(p):
                    with open(p, "r", encoding="utf-8") as f:
                        for match in _re.finditer(
                            r'\(property "LCSC" "(C\d+)"', f.read()
                        ):
                            self._imported_ids.add(match.group(1))
            except (PermissionError, OSError):
                pass

    def _repopulate_results(self):
        """Repopulate the DataTable from search results."""
        table = self.query_one("#results-table", DataTable)
        table.clear()
        for r in self._search_results:
            lcsc = r["lcsc"]
            prefix = "\u2713 " if lcsc in self._imported_ids else ""
            price_str = f"${r['price']:.4f}" if r["price"] else "N/A"
            stock_str = f"{r['stock']:,}" if r["stock"] else "N/A"
            table.add_row(
                prefix + lcsc,
                r["type"],
                price_str,
                stock_str,
                r["model"],
                r.get("package", ""),
                r.get("description", ""),
            )
        self._update_results_count()

    def _update_results_count(self):
        """Update the results count label."""
        shown = len(self._search_results)
        total = len(self._raw_search_results)
        label = self.query_one("#results-count", Label)
        if total == 0:
            label.update("")
        elif shown == total:
            label.update(f"{total} results")
        else:
            label.update(f"{shown} of {total} results")

    # --- Sorting ---

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected):
        """Sort by clicked column."""
        col_idx = event.column_index
        if col_idx == self._sort_col:
            self._sort_ascending = not self._sort_ascending
        else:
            self._sort_col = col_idx
            self._sort_ascending = col_idx not in (2, 3)

        key_map = {
            0: lambda r: r.get("lcsc", ""),
            1: lambda r: r.get("type", ""),
            2: lambda r: r.get("price") or 0,
            3: lambda r: r.get("stock") or 0,
            4: lambda r: r.get("model", "").lower(),
            5: lambda r: r.get("package", "").lower(),
            6: lambda r: r.get("description", "").lower(),
        }
        key_fn = key_map.get(col_idx)
        if key_fn:
            self._search_results.sort(key=key_fn, reverse=not self._sort_ascending)
            self._update_sort_indicators()
            self._repopulate_results()

    def _update_sort_indicators(self):
        """Update column headers with sort direction arrows."""
        table = self.query_one("#results-table", DataTable)
        col_keys = list(table.columns.keys())
        for i, key in enumerate(col_keys):
            name = self._col_names[i]
            if i == self._sort_col:
                arrow = "\u25b2" if self._sort_ascending else "\u25bc"
                table.columns[key].label = f"{name} {arrow}"
            else:
                table.columns[key].label = name

    # --- Selection ---

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted):
        """Update detail when cursor moves."""
        self._show_detail(event.cursor_row)

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        """Handle row selection in results table."""
        self._show_detail(event.cursor_row)

    def _show_detail(self, row_idx: int):
        """Update the detail panel for the given row."""
        if row_idx < 0 or row_idx >= len(self._search_results):
            return
        if row_idx == self._selected_index:
            return
        self._selected_index = row_idx
        r = self._search_results[row_idx]

        # Update part input
        self.query_one("#part-input", Input).value = r["lcsc"]

        # Update detail fields
        self.query_one("#detail-part", Label).update(f"Part: {r['model']}")
        self.query_one("#detail-lcsc", Label).update(
            f"LCSC: {r['lcsc']}  ({r['type']})"
        )
        self.query_one("#detail-brand-pkg", Label).update(
            f"Brand: {r['brand']}  |  Package: {r['package']}"
        )
        price_str = f"${r['price']:.4f}" if r["price"] else "N/A"
        stock_str = f"{r['stock']:,}" if r["stock"] else "N/A"
        self.query_one("#detail-price-stock", Label).update(
            f"Price: {price_str}  |  Stock: {stock_str}"
        )
        self.query_one("#detail-desc", Label).update(r.get("description", ""))

        # URLs
        self._datasheet_url = r.get("datasheet", "")
        self._lcsc_page_url = r.get("url", "")
        self.query_one("#detail-datasheet-btn", Button).disabled = not self._datasheet_url
        self.query_one("#detail-lcsc-btn", Button).disabled = not self._lcsc_page_url
        self.query_one("#detail-import-btn", Button).disabled = False

        # Fetch image
        self._image_request_id += 1
        request_id = self._image_request_id
        lcsc_url = r.get("url", "")
        if lcsc_url:
            self._start_skeleton()
            self._fetch_detail_image(lcsc_url, request_id)
        else:
            self._stop_skeleton()
            self.query_one("#detail-image", TIImage).image = None

    @work(thread=True)
    def _fetch_detail_image(self, lcsc_url: str, request_id: int):
        """Fetch product image in background."""
        img_data = None
        try:
            img_data = fetch_product_image(lcsc_url)
        except Exception:
            pass
        if self._image_request_id == request_id:
            self._detail_image_data = img_data
            self.app.call_from_thread(self._set_detail_image, img_data, request_id)

    def _set_detail_image(self, img_data: bytes | None, request_id: int):
        """Set the detail image (called on main thread)."""
        if self._image_request_id != request_id:
            return
        self._stop_skeleton()
        self.query_one("#detail-image", TIImage).image = _pil_from_bytes(img_data)

    # --- Import ---

    def _do_import_action(self):
        """Start the import process."""
        part_input = self.query_one("#part-input", Input)
        raw_id = part_input.value.strip()
        if not raw_id:
            self._log("[red]Error: Enter an LCSC part number[/red]")
            return

        try:
            lcsc_id = validate_lcsc_id(raw_id)
        except ValueError as e:
            self._log(f"[red]Error: {e}[/red]")
            return

        dest_selector = self.query_one("#dest-selector", RadioSet)
        use_global = dest_selector.pressed_index == 1

        if use_global:
            lib_dir = get_global_lib_dir()
        else:
            lib_dir = self._project_dir
            if not lib_dir:
                self._log(
                    "[red]Error: No project directory. Use Global destination.[/red]"
                )
                return

        overwrite = self.query_one("#overwrite-cb", Checkbox).value

        self.query_one("#import-btn", Button).disabled = True
        self.query_one("#detail-import-btn", Button).disabled = True
        self._run_import(lcsc_id, lib_dir, overwrite, use_global)

    @work(thread=True)
    def _run_import(self, lcsc_id: str, lib_dir: str, overwrite: bool, use_global: bool):
        """Run the import in a background thread."""
        try:
            self._do_import(lcsc_id, lib_dir, overwrite, use_global)
        except APIError as e:
            self.app.call_from_thread(self._log, f"[red]API Error: {e}[/red]")
        except Exception as e:
            self.app.call_from_thread(self._log, f"[red]Error: {e}[/red]")
            self.app.call_from_thread(self._log, traceback.format_exc())
        finally:
            self.app.call_from_thread(
                self.query_one("#import-btn", Button).__setattr__, "disabled", False
            )
            self.app.call_from_thread(
                self.query_one("#detail-import-btn", Button).__setattr__, "disabled", False
            )

    def _do_import(self, lcsc_id: str, lib_dir: str, overwrite: bool, use_global: bool):
        """Execute the import process."""
        lib_name = "JLCImport"
        log = lambda msg: self.app.call_from_thread(self._log, msg)

        log(f"Fetching component {lcsc_id}...")
        log(f"Destination: {lib_dir}")

        comp = fetch_full_component(lcsc_id)
        title = comp["title"]
        name = sanitize_name(title)
        log(f"Component: {title}")
        log(f"Prefix: {comp['prefix']}, Name: {name}")

        # Set up library structure
        paths = ensure_lib_structure(lib_dir, lib_name)

        # Parse footprint
        log("Parsing footprint...")
        fp_shapes = comp["footprint_data"]["dataStr"]["shape"]
        footprint = parse_footprint_shapes(
            fp_shapes, comp["fp_origin_x"], comp["fp_origin_y"]
        )
        log(f"  {len(footprint.pads)} pads, {len(footprint.tracks)} tracks")

        # 3D model
        model_path = ""
        model_offset = (0.0, 0.0, 0.0)
        model_rotation = (0.0, 0.0, 0.0)

        uuid_3d = ""
        if footprint.model:
            uuid_3d = footprint.model.uuid
            model_offset, model_rotation = compute_model_transform(
                footprint.model, comp["fp_origin_x"], comp["fp_origin_y"]
            )

        if not uuid_3d:
            uuid_3d = comp.get("uuid_3d", "")

        if uuid_3d:
            log("Downloading 3D model...")
            step_path, wrl_path = download_and_save_models(
                uuid_3d, paths["models_dir"], name
            )
            if step_path:
                if use_global:
                    model_path = os.path.join(paths["models_dir"], f"{name}.step")
                else:
                    model_path = f"${{KIPRJMOD}}/{lib_name}.3dshapes/{name}.step"
                log("  STEP saved")
            if wrl_path:
                log("  WRL saved")
        else:
            log("No 3D model available")

        # Write footprint
        log("Writing footprint...")
        fp_content = write_footprint(
            footprint,
            name,
            lcsc_id=lcsc_id,
            description=comp.get("description", ""),
            datasheet=comp.get("datasheet", ""),
            model_path=model_path,
            model_offset=model_offset,
            model_rotation=model_rotation,
        )
        fp_saved = save_footprint(paths["fp_dir"], name, fp_content, overwrite)
        if fp_saved:
            log(f"  Saved: {name}.kicad_mod")
        else:
            log("  Skipped (exists, overwrite=off)")

        # Parse and write symbol
        if comp["symbol_data_list"]:
            log("Parsing symbol...")
            sym_data = comp["symbol_data_list"][0]
            sym_shapes = sym_data["dataStr"]["shape"]
            symbol = parse_symbol_shapes(
                sym_shapes, comp["sym_origin_x"], comp["sym_origin_y"]
            )
            log(f"  {len(symbol.pins)} pins, {len(symbol.rectangles)} rects")

            footprint_ref = f"{lib_name}:{name}"
            sym_content = write_symbol(
                symbol,
                name,
                prefix=comp["prefix"],
                footprint_ref=footprint_ref,
                lcsc_id=lcsc_id,
                datasheet=comp.get("datasheet", ""),
                description=comp.get("description", ""),
                manufacturer=comp.get("manufacturer", ""),
                manufacturer_part=comp.get("manufacturer_part", ""),
            )

            sym_added = add_symbol_to_lib(paths["sym_path"], name, sym_content, overwrite)
            if sym_added:
                log(f"  Symbol added to {lib_name}.kicad_sym")
            else:
                log("  Symbol skipped (exists, overwrite=off)")
        else:
            log("No symbol data available")

        # Update lib tables
        if use_global:
            update_global_lib_tables(lib_dir, lib_name)
            log("[green]Global library tables updated.[/green]")
        else:
            newly_created = update_project_lib_tables(lib_dir, lib_name)
            log("[green]Project library tables updated.[/green]")
            if newly_created:
                log("[yellow]NOTE: Reopen project for new library tables to take effect.[/yellow]")

        log(f"\n[green bold]Done! '{title}' imported as {lib_name}:{name}[/green bold]")
        self.app.call_from_thread(self._refresh_imported_ids)
        self.app.call_from_thread(self._repopulate_results)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="JLCImport TUI - interactive terminal interface for JLCPCB component import"
    )
    parser.add_argument(
        "-p", "--project",
        help="KiCad project directory (where .kicad_pro file is)",
        default="",
    )
    args = parser.parse_args()

    project_dir = args.project
    if project_dir:
        project_dir = os.path.abspath(project_dir)

    app = JLCImportTUI(project_dir=project_dir)
    app.run()


if __name__ == "__main__":
    main()
