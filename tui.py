#!/usr/bin/env python3
"""TUI (Text User Interface) for JLCImport using Textual."""
from __future__ import annotations

import io
import os
import sys
import threading
import traceback
import webbrowser

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
    Static,
)
from textual.message import Message
from rich.text import Text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kicad_jlcimport.api import (
    fetch_full_component,
    search_components,
    fetch_product_image,
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


def image_to_halfblock(img_data: bytes, width: int = 40, height: int = 20) -> str:
    """Convert image bytes to half-block character art with ANSI colors.

    Uses the upper half block character (U+2580) where:
    - Foreground color = top pixel
    - Background color = bottom pixel

    This gives 2 vertical pixels per character cell.
    """
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(img_data))
        img = img.convert("RGB")
        # Height in pixels is 2x character rows (2 pixels per char)
        pixel_height = height * 2
        img = img.resize((width, pixel_height), Image.LANCZOS)

        lines = []
        for row in range(0, pixel_height, 2):
            line = ""
            for col in range(width):
                # Top pixel (foreground)
                r1, g1, b1 = img.getpixel((col, row))
                # Bottom pixel (background)
                if row + 1 < pixel_height:
                    r2, g2, b2 = img.getpixel((col, row + 1))
                else:
                    r2, g2, b2 = r1, g1, b1
                # Use Rich markup for colors
                line += (
                    f"[rgb({r1},{g1},{b1}) on rgb({r2},{g2},{b2})]\u2580[/]"
                )
            lines.append(line)
        return "\n".join(lines)
    except Exception:
        return "[dim]No image available[/dim]"


class ImageWidget(Static):
    """Widget that displays an image using half-block characters."""

    def __init__(self, width: int = 40, height: int = 20, **kwargs):
        super().__init__(**kwargs)
        self._img_width = width
        self._img_height = height

    def set_image(self, img_data: bytes | None):
        """Update the displayed image."""
        if img_data:
            markup = image_to_halfblock(img_data, self._img_width, self._img_height)
        else:
            markup = "[dim italic]No image[/dim italic]"
        self.update(markup)

    def set_loading(self):
        """Show a loading placeholder."""
        self.update("[dim italic]Loading image...[/dim italic]")


class GalleryScreen(Screen):
    """Full-screen gallery view for component images."""

    BINDINGS = [
        Binding("escape", "close", "Back"),
        Binding("left", "prev", "Previous"),
        Binding("right", "next", "Next"),
    ]

    CSS = """
    GalleryScreen {
        align: center middle;
        background: $surface;
    }
    #gallery-container {
        width: 100%;
        height: 100%;
        align: center middle;
    }
    #gallery-image {
        width: auto;
        height: auto;
        content-align: center middle;
        margin: 1 2;
    }
    #gallery-info {
        text-align: center;
        width: 100%;
        margin: 0 2;
        color: $text;
    }
    #gallery-desc {
        text-align: center;
        width: 100%;
        margin: 0 2;
        color: $text-muted;
    }
    #gallery-nav {
        align: center middle;
        height: 3;
        width: 100%;
    }
    #gallery-nav Button {
        margin: 0 2;
    }
    """

    def __init__(self, results: list, index: int = 0):
        super().__init__()
        self._results = results
        self._index = index
        self._image_cache: dict[int, bytes | None] = {}

    def compose(self) -> ComposeResult:
        with Vertical(id="gallery-container"):
            with Horizontal(id="gallery-nav"):
                yield Button("\u25C0 Prev", id="gallery-prev", variant="default")
                yield Button("Back", id="gallery-back", variant="primary")
                yield Button("Next \u25B6", id="gallery-next", variant="default")
            yield ImageWidget(width=80, height=35, id="gallery-image")
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
        img_widget = self.query_one("#gallery-image", ImageWidget)
        if self._index in self._image_cache:
            img_widget.set_image(self._image_cache[self._index])
        else:
            img_widget.set_loading()
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
            self.query_one("#gallery-image", ImageWidget).set_image(img_data)

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
    SUB_TITLE = "JLCPCB Component Importer"

    CSS = """
    Screen {
        background: $surface;
    }

    #main-container {
        width: 100%;
        height: 100%;
    }

    /* Search section */
    #search-section {
        height: auto;
        border: solid $primary;
        margin: 0 1;
        padding: 0 1;
    }
    #search-section Label.section-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    #search-row {
        height: 3;
        width: 100%;
    }
    #search-input {
        width: 1fr;
        margin-right: 1;
    }
    #search-btn {
        width: 12;
    }
    #filter-row {
        height: 3;
        width: 100%;
        margin-top: 0;
    }
    #type-filter {
        layout: horizontal;
        height: 3;
        width: auto;
    }
    #type-filter RadioButton {
        width: auto;
        margin-right: 1;
        height: 3;
    }
    #in-stock-cb {
        margin-left: 2;
        height: 3;
    }

    /* Results section */
    #results-section {
        height: 1fr;
        min-height: 8;
        margin: 0 1;
    }
    #results-table {
        height: 100%;
    }

    /* Content area (details + import) */
    #content-area {
        height: auto;
        max-height: 20;
    }

    /* Detail section */
    #detail-section {
        height: auto;
        border: solid $secondary;
        margin: 0 1;
        padding: 0 1;
    }
    #detail-section Label.section-title {
        text-style: bold;
        color: $secondary;
        margin-bottom: 1;
    }
    #detail-content {
        height: auto;
    }
    #detail-image {
        width: 22;
        height: 10;
        margin-right: 1;
    }
    #detail-info {
        width: 1fr;
        height: auto;
    }
    .detail-field {
        height: 1;
    }
    #detail-desc {
        height: 2;
        color: $text-muted;
    }
    #detail-buttons {
        height: 3;
        margin-top: 1;
    }
    #detail-buttons Button {
        margin-right: 1;
    }

    /* Import section */
    #import-section {
        height: auto;
        border: solid $success;
        margin: 0 1;
        padding: 0 1;
    }
    #import-section Label.section-title {
        text-style: bold;
        color: $success;
        margin-bottom: 1;
    }
    #import-content {
        height: auto;
    }
    #dest-selector {
        width: 1fr;
        height: auto;
        layout: horizontal;
    }
    #dest-selector RadioButton {
        width: auto;
        margin-right: 2;
        height: 3;
    }
    #import-options {
        height: 3;
        width: 100%;
    }
    #part-input {
        width: 20;
        margin-right: 1;
    }
    #overwrite-cb {
        margin-right: 1;
        height: 3;
    }
    #import-btn {
        width: 12;
    }

    /* Status section */
    #status-section {
        height: 8;
        min-height: 5;
        margin: 0 1;
        border: solid $accent;
    }
    #status-log {
        height: 100%;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+g", "gallery", "Gallery", show=True),
        Binding("ctrl+s", "focus_search", "Search", show=True),
        Binding("f5", "do_search", "Search", show=False),
    ]

    def __init__(self, project_dir: str = ""):
        super().__init__()
        self._project_dir = project_dir
        self._search_results: list = []
        self._sort_col: int = -1
        self._sort_ascending: bool = True
        self._imported_ids: set = set()
        self._selected_index: int = -1
        self._detail_image_data: bytes | None = None
        self._image_request_id: int = 0
        self._datasheet_url: str = ""
        self._lcsc_page_url: str = ""

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="main-container"):
            # Search section
            with Vertical(id="search-section"):
                yield Label("Search", classes="section-title")
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
                    yield Checkbox("In stock only", value=True, id="in-stock-cb")

            # Results table
            with Container(id="results-section"):
                yield DataTable(id="results-table", cursor_type="row")

            # Detail section
            with Vertical(id="detail-section"):
                yield Label("Details", classes="section-title")
                with Horizontal(id="detail-content"):
                    yield ImageWidget(width=20, height=10, id="detail-image")
                    with Vertical(id="detail-info"):
                        yield Label("", id="detail-part", classes="detail-field")
                        yield Label("", id="detail-lcsc", classes="detail-field")
                        yield Label("", id="detail-brand-pkg", classes="detail-field")
                        yield Label("", id="detail-price-stock", classes="detail-field")
                        yield Label("", id="detail-desc")
                        with Horizontal(id="detail-buttons"):
                            yield Button("Import", id="detail-import-btn", variant="success", disabled=True)
                            yield Button("Datasheet", id="detail-datasheet-btn", disabled=True)
                            yield Button("LCSC Page", id="detail-lcsc-btn", disabled=True)

            # Import section
            with Vertical(id="import-section"):
                yield Label("Import", classes="section-title")
                with Vertical(id="import-content"):
                    with RadioSet(id="dest-selector"):
                        yield RadioButton(
                            f"Project: {self._project_dir or '(no project)'}",
                            value=bool(self._project_dir),
                            id="dest-project",
                        )
                        yield RadioButton(
                            f"Global: {get_global_lib_dir()}",
                            value=not bool(self._project_dir),
                            id="dest-global",
                        )
                    with Horizontal(id="import-options"):
                        yield Input(placeholder="C427602", id="part-input")
                        yield Checkbox("Overwrite", id="overwrite-cb")
                        yield Button("Import", id="import-btn", variant="success")

            # Status log
            with Container(id="status-section"):
                yield RichLog(id="status-log", highlight=True, markup=True)

        yield Footer()

    def on_mount(self):
        """Set up the results table columns."""
        table = self.query_one("#results-table", DataTable)
        table.add_columns("LCSC", "Type", "Price", "Stock", "Part", "Package")
        # Disable project radio if no project dir
        if not self._project_dir:
            self.query_one("#dest-project", RadioButton).disabled = True

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

    @work(thread=True)
    def _do_search(self):
        """Perform the search in a background thread."""
        search_input = self.query_one("#search-input", Input)
        keyword = search_input.value.strip()
        if not keyword:
            return

        # Determine part type filter
        type_filter = self.query_one("#type-filter", RadioSet)
        part_type = None
        if type_filter.pressed_index == 1:
            part_type = "base"
        elif type_filter.pressed_index == 2:
            part_type = "expand"

        in_stock = self.query_one("#in-stock-cb", Checkbox).value

        self.app.call_from_thread(self._log, f"Searching for \"{keyword}\"...")
        self.app.call_from_thread(
            self.query_one("#search-btn", Button).__setattr__, "disabled", True
        )

        try:
            result = search_components(keyword, page_size=25, part_type=part_type)
            results = result["results"]

            if in_stock:
                results = [r for r in results if r["stock"] and r["stock"] > 0]

            results.sort(key=lambda r: r["stock"] or 0, reverse=True)

            self._search_results = results
            self._sort_col = 3  # sorted by stock
            self._sort_ascending = False
            self._selected_index = -1

            self.app.call_from_thread(
                self._log,
                f"  {result['total']} total results, showing {len(results)}",
            )
            self.app.call_from_thread(self._refresh_imported_ids)
            self.app.call_from_thread(self._repopulate_results)

        except APIError as e:
            self.app.call_from_thread(self._log, f"[red]Search error: {e}[/red]")
        except Exception as e:
            self.app.call_from_thread(
                self._log, f"[red]Error: {type(e).__name__}: {e}[/red]"
            )
        finally:
            self.app.call_from_thread(
                self.query_one("#search-btn", Button).__setattr__, "disabled", False
            )

    def _refresh_imported_ids(self):
        """Scan symbol libraries for already-imported LCSC IDs."""
        import re as _re

        self._imported_ids = set()
        paths = []
        if self._project_dir:
            paths.append(os.path.join(self._project_dir, "JLCImport.kicad_sym"))
        global_dir = get_global_lib_dir()
        paths.append(os.path.join(global_dir, "JLCImport.kicad_sym"))
        for p in paths:
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        for match in _re.finditer(
                            r'\(property "LCSC" "(C\d+)"', f.read()
                        ):
                            self._imported_ids.add(match.group(1))
                except Exception:
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
            )

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
        }
        key_fn = key_map.get(col_idx)
        if key_fn:
            self._search_results.sort(key=key_fn, reverse=not self._sort_ascending)
            self._repopulate_results()

    # --- Selection ---

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        """Handle row selection in results table."""
        row_idx = event.cursor_row
        if row_idx < 0 or row_idx >= len(self._search_results):
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
        img_widget = self.query_one("#detail-image", ImageWidget)
        lcsc_url = r.get("url", "")
        if lcsc_url:
            img_widget.set_loading()
            self._fetch_detail_image(lcsc_url, request_id)
        else:
            img_widget.set_image(None)

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
        self.query_one("#detail-image", ImageWidget).set_image(img_data)

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
