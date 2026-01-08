from __future__ import annotations
import asyncio
from typing import Tuple, Optional
from rich.text import Text
from rich.console import RenderableType
from textual.widget import Widget
from textual.reactive import reactive
from textual import events
from textual.app import ComposeResult
from .geocode import geocode
from .tile_loader import get_tiles_for_region
from textual.events import Key
from textual import on
from textual_image.widget import SixelImage
from PIL import ImageDraw, ImageFont
from functools import lru_cache
from textual.binding import Binding


@lru_cache(maxsize=256)
def get_tiles_cached(lat, lon, zoom, w, h):
    return get_tiles_for_region(lat, lon, zoom, w, h)


class MapWidget(Widget):

    zoom = reactive(4)
    marker = reactive(None)  # type: Optional[Tuple[float, float]]
    last_render_info = reactive("")

    BINDINGS = {
        Binding("left", "s", "esquerda"),
        Binding("right", "a", "direita"),
        Binding("up", "f", "cima"),
        Binding("down", "t", "baixo"),
        Binding("enter", "q", "centro"),
        Binding("x", "d", "zoom-"),
        Binding("z", "w", "zoom+"),
    }

    def __init__(self, *, address: str | None = None, name: str | None = None):
        super().__init__(name=name)
        self._offset_x = 0.0
        self._offset_y = 0.0
        self._dragging = False
        self._last_mouse = None
        self._initial_address = address
        self.can_focus = True
        self._last_marker = self.marker
        self._font = ImageFont.load_default()
        self._dirty = True
        self._last_image = None
        self._last_sent_image = None
        self._ppd_cache = {}
        self._pending_refresh = False

    def on_mount(self) -> None:
        """Handle widget mount - set initial address if provided."""
        if self._initial_address:
            self.set_address(self._initial_address)

    def compose(self) -> ComposeResult:
        """Compose child widgets."""
        # Mount SIXEL widget - it will be updated when image changes
        # Create a SixelImage that fills the available space
        sixel = SixelImage()
        # Set the widget to expand and fill available space
        sixel.styles.width = "100%"
        sixel.styles.height = "100%"
        yield sixel
        
    def _pan_by_keys(self, dx: float, dy: float) -> None:
        sens = self._pan_sensitivity()
        self._offset_x += dx * sens * 40
        self._offset_y += dy * sens * 40
        self._dirty = True
        self.refresh()


    def _pan_sensitivity(self):
        if not hasattr(self, "_pan_cache"):
            self._pan_cache = {}

        if self.size.width <= 0 or self.size.height <= 0:
            return Text("")

        key = (self.zoom, self.size.width)
        if key not in self._pan_cache:
            self._pan_cache[key] = 360.0 / (
                self.size.width * (1 + (self.zoom - 1) * 0.6)
            )
        return self._pan_cache[key]

    async def _schedule_refresh(self):
        if self._pending_refresh:
            return
        self._pending_refresh = True
        await asyncio.sleep(0.016)  # ~60 FPS
        self._pending_refresh = False
        self.refresh()

    async def set_address(self, address: str) -> None:
        lat, lon = await asyncio.to_thread(geocode, address)
        self.marker = (lat, lon)
        self._center_on(lat, lon)
        self._dirty = True

    # Coordinate transforms
    def _center_on(self, lat: float, lon: float) -> None:
        self._offset_x = -lon
        self._offset_y = -lat
        self._dirty = True

    # Event handlers for mouse interactivity

    async def on_mouse_down(self, event: events.MouseDown) -> None:
        # Start drag only on left-click so buttons and other clicks still work
        btn = getattr(event, "button", None)
        is_left = False
        try:
            is_left = btn == 1 or str(btn).lower() == "left"
        except Exception:
            is_left = False
        if not is_left:
            return

        self._dragging = True
        # Use screen coordinates so dragging works even when clicking child widgets
        sx = getattr(event, "screen_x", None)
        sy = getattr(event, "screen_y", None)
        if sx is None or sy is None:
            # fall back to local coords
            self._last_mouse = (event.x, event.y)
        else:
            self._last_mouse = (sx, sy)
        # Note: We don't need to explicitly capture mouse - Textual will send
        # mouse events to this widget when dragging

    async def on_mouse_up(self, event: events.MouseUp) -> None:
        # Only stop drag on left button release
        btn = getattr(event, "button", None)
        is_left = False
        try:
            is_left = btn == 1 or str(btn).lower() == "left"
        except Exception:
            is_left = False
        if not is_left:
            return

        self._dragging = False
        self._last_mouse = None

    async def on_mouse_move(self, event: events.MouseMove) -> None:
        # Only handle movement if we're in a drag operation
        if not self._dragging or self._last_mouse is None:
            return

        last_x, last_y = self._last_mouse
        sx = getattr(event, "screen_x", None)
        sy = getattr(event, "screen_y", None)
        if sx is None or sy is None:
            cur_x, cur_y = event.x, event.y
        else:
            cur_x, cur_y = sx, sy

        dx = cur_x - last_x
        dy = cur_y - last_y

        if abs(dx) > 0 or abs(dy) > 0:
            sens = self._pan_sensitivity()
            self._offset_x -= dx * sens
            self._offset_y -= dy * sens
            self._last_mouse = (cur_x, cur_y)
            self._dirty = True
            await self._schedule_refresh()

    def _set_zoom(self, value: int):
        new = max(0, min(18, value))
        if new != self.zoom:
            self.zoom = new
            self._dirty = True

    async def on_mouse_scroll(self, event: events.MouseScroll) -> None:
        event.stop()
        self._set_zoom(self.zoom + (1 if event.delta_y < 0 else -1))

    def watch_zoom(self, value):
        self._dirty = True

    def watch_marker(self, value):
        self._dirty = True

    def _keyboard_pan_step(self):
        # graus por tecla (menor = mais preciso)
        base = 5.0
        return base / (1 + self.zoom * 0.8)

    @on(Key)
    async def _on_key(self, event: events.Key):
        event.stop()

        step = self._keyboard_pan_step()

        if event.key == "left":
            self._pan_by_keys(-1, 0)
        elif event.key == "right":
            self._pan_by_keys(+1, 0)
        elif event.key == "up":
            self._pan_by_keys(0, +1)
        elif event.key == "down":
            self._pan_by_keys(0, -1)
        elif event.key == "enter" and self.marker:
            lat, lon = self.marker
            self._center_on(lat, lon)
            await self._schedule_refresh()

        elif event.key == "z":
            self._set_zoom(self.zoom + 1)
            return
        elif event.key == "x":
            self._set_zoom(self.zoom - 1)
            return
        else:
            return

        self._dirty = True
        await self._schedule_refresh()

    def render(self) -> RenderableType:
        """Render the map as a SIXEL image using PIL and textual-image.

        Creates a PIL image with the map tiles and marker, then renders it
        using textual-image's SIXEL renderable for terminals with SIXEL support.
        """
        if not self._dirty and self._last_image:
            return Text("")

        w = max(10, self.size.width or 80)
        h = max(4, self.size.height or 20)

        px_w = int(w * 7.5)
        px_h = int(h * 16)

        if self.marker:
            center_lat = self.marker[0] + self._offset_y
            center_lon = self.marker[1] + self._offset_x
        else:
            center_lat = self._offset_y
            center_lon = self._offset_x
        # Get real map tiles from OpenStreetMap
        img, _, _ = get_tiles_cached(
            center_lat,
            center_lon,
            self.zoom,
            px_w,
            px_h,
        )
        draw = ImageDraw.Draw(img)

        # Draw marker if present
        if self.marker:
            mlat, mlon = self.marker
            # Calculate marker position relative to center
            # At zoom level z, one tile covers 360/(2^z) degrees
            if self.zoom not in self._ppd_cache:
                degrees_per_tile = 360.0 / (2 ** self.zoom)
                self._ppd_cache[self.zoom] = 256 / degrees_per_tile
            pixels_per_degree = self._ppd_cache[self.zoom]

            # Marker offset from center
            dx = (mlon - center_lon) * pixels_per_degree
            # Negative because screen y increases downward
            dy = -(mlat - center_lat) * pixels_per_degree

            mx = px_w // 2 + int(dx)
            my = px_h // 2 + int(dy)

            if not hasattr(self, "_marker_radius"):
                self._marker_radius = {}

            r = self._marker_radius.get(px_w)
            if r is None:
                r = max(5, int(min(px_w, px_h) * 0.02))
                self._marker_radius[px_w] = r

            # desenha marcador
            draw.ellipse(
                (mx - r - 2, my - r - 2, mx + r + 2, my + r + 2),
                fill=(255, 255, 255),
            )
            draw.ellipse(
                (mx - r, my - r, mx + r, my + r),
                fill=(230, 60, 60),
            )
        # footer overlay with zoom/coords and attribution
        footer_h = max(16, int(px_h * 0.06))

        draw.rectangle(
            (0, px_h - footer_h, px_w, px_h),
            fill=(6, 6, 6),
        )

        footer_text = f" Zoom: {self.zoom}"
        if self.marker:
            footer_text += f" | Marker: {self.marker[0]:.3f},{self.marker[1]:.3f}"
        footer_text += " | © OpenStreetMap"

        draw.text(
            (4, px_h - footer_h + 2),
            footer_text,
            fill=(220, 220, 220),
            font=self._font,
        )

        # Use textual-image's SIXEL widget - update the image
        # Update the SIXEL widget's image (widget is mounted in compose())
        sixel = self.query_one(SixelImage)
        if img is not self._last_sent_image:
            sixel.image = img
            self._last_sent_image = img

        self._dirty = False
        self._last_image = img
        draw_marker = self.marker != self._last_marker
        self._last_marker = self.marker

        return Text("")
