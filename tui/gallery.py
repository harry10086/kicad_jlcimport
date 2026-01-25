"""Full-screen gallery view for component images."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Label
from textual_image.widget import HalfcellImage

from kicad_jlcimport.api import fetch_product_image

from .helpers import TIImage, make_no_image, make_skeleton_frame, pil_from_bytes


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
    #gallery-skeleton {
        width: auto;
        height: 100%;
        display: none;
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
                yield Button("\u25c0 Prev", id="gallery-prev", variant="default")
                yield Button("Back", id="gallery-back", variant="primary")
                yield Button("Next \u25b6", id="gallery-next", variant="default")
            with Container(id="gallery-image-wrap"):
                yield HalfcellImage(id="gallery-skeleton")
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
        price_str = f"${r['price']:.4f}" if r["price"] else "N/A"
        stock_str = f"{r['stock']:,}" if r["stock"] else "N/A"
        info = (
            f"{r['lcsc']}  |  {r['model']}  |  {r['brand']}  |  {r['package']}  |  {price_str}  |  Stock: {stock_str}"
        )
        self.query_one("#gallery-info", Label).update(info)
        self.query_one("#gallery-desc", Label).update(r.get("description", ""))

        # Update nav buttons
        self.query_one("#gallery-prev", Button).disabled = self._index <= 0
        self.query_one("#gallery-next", Button).disabled = self._index >= len(self._results) - 1

        # Load image
        img_widget = self.query_one("#gallery-image", TIImage)
        if self._index in self._image_cache:
            self._stop_skeleton()
            img = pil_from_bytes(self._image_cache[self._index])
            if img is None:
                img = make_no_image(200, 200)
            img_widget.image = img
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
            img = pil_from_bytes(img_data)
            if img is None:
                img = make_no_image(200, 200)
            self.query_one("#gallery-image", TIImage).image = img

    def _start_skeleton(self):
        self._stop_skeleton()
        self._skeleton_phase = 0
        skeleton = self.query_one("#gallery-skeleton", HalfcellImage)
        skeleton.image = make_skeleton_frame(200, 200, 0)
        skeleton.display = True
        self.query_one("#gallery-image", TIImage).display = False
        self._skeleton_timer = self.set_interval(1 / 15, self._on_skeleton_tick)

    def _on_skeleton_tick(self):
        if not self._skeleton_timer:
            return
        self._skeleton_phase = (self._skeleton_phase + 5) % 100
        self.query_one("#gallery-skeleton", HalfcellImage).image = make_skeleton_frame(200, 200, self._skeleton_phase)

    def _stop_skeleton(self):
        if self._skeleton_timer:
            self._skeleton_timer.stop()
            self._skeleton_timer = None
        self.query_one("#gallery-skeleton", HalfcellImage).display = False
        self.query_one("#gallery-image", TIImage).display = True

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "gallery-prev":
            self.action_prev()
        elif event.button.id == "gallery-next":
            self.action_next()
        elif event.button.id == "gallery-back":
            self.action_close()

    def action_close(self):
        self.dismiss(self._index)

    def action_prev(self):
        if self._index > 0:
            self._index -= 1
            self._update_gallery()

    def action_next(self):
        if self._index < len(self._results) - 1:
            self._index += 1
            self._update_gallery()
