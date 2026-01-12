from __future__ import annotations
import asyncio
from rich.text import Text
from rich.console import RenderableType
from textual.widget import Widget
from textual.reactive import reactive
from textual import events
from geopy.geocoders import Nominatim
from .tile_loader import get_tiles_for_region
from textual_image.widget import SixelImage
from textual_image.widget import TGPImage
from textual_image.widget import Image
from textual_image.widget import HalfcellImage
from textual_image.widget import UnicodeImage
from PIL import ImageDraw, ImageFont
from functools import lru_cache
from textual.binding import Binding, BindingType
from enum import Enum
from typing import ClassVar


@lru_cache(maxsize=256)
def get_tiles_cached(lat, lon, zoom, w, h):
    return get_tiles_for_region(lat, lon, zoom, w, h)


class Tipo(Enum):
    HALFCELL = HalfcellImage
    SIXEL = SixelImage
    AUTO = Image
    UNICODE = UnicodeImage
    TGP = TGPImage


class MapWidget(Widget):

    DEFAULT_CSS = """
        .imagem {
            width: 100%;
            height: 100%;
        }
        MapWidget {
            height: 20; 
            width: 50;
            margin: 0;
            &:focus {
                border: tall $border 30%;
                background-tint: $foreground 5%;
            }
        }
   
    """

    marker = reactive(None)
    last_render_info = reactive("")
    zoom = reactive(10)

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("left", "go_left", "esquerda"),
        Binding("right", "go_right", "direita"),
        Binding("up", "go_up", "cima"),
        Binding("down", "go_down", "baixo"),
        Binding("enter", "center", "centro"),
        Binding("x", "zoom_out", "zoom-"),
        Binding("z", "zoom_in", "zoom+"),
    ]

    async def agendar_refresh(self):
        self._dirty = True
        self.agendar_refresh()

    def action_go_left(self):
        self._pan_by_keys(-1, 0)

    def action_go_right(self):
        self._pan_by_keys(+1, 0)
        self._dirty = True
        self.agendar_refresh()

    def action_go_up(self):
        self._pan_by_keys(0, +1)
        self._dirty = True
        self.agendar_refresh()

    def action_go_down(self):
        self._pan_by_keys(0, -1)
        self._dirty = True
        self.agendar_refresh()

    def action_zoom_in(self):
        self._set_zoom(self.zoom + 1)
        self._dirty = True
        self.agendar_refresh()

    def action_zoom_out(self):
        self._set_zoom(self.zoom - 1)
        self._dirty = True
        self.agendar_refresh()

    def action_center(self):
        if self.marker:
            lat, lon = self.marker
            self._center_on(lat, lon)
            self.agendar_refresh()

    def __init__(self, *, address: str | None = None, name: str | None = None, zoom=5, tipo=Tipo.AUTO):
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
        self.geolocator = Nominatim(user_agent="my_app")
        self.tipo = tipo
        self.zoom = zoom
        if address:
            self.location = self.geolocator.geocode(address)
            self.lat = self.location.latitude
            self.lon = self.location.longitude
        else:
            self.location = None
            self.lat = 31.95
            self.lon = 10.0

        self._center_lat = self.lat
        self._center_lon = self.lon
        self.marker = (self.lat, self.lon)

    def set_tipo(self, tipo):
        '''
        Tipo de Imagem 

        Tipo.HALFCELL 
        Tipo.SIXEL 
        Tipo.AUTO 
        Tipo.UNICODE 
        Tipo.TGP 
        '''
        self.tipo = tipo
        self.refresh()

    def set_zoom(self, zoom):
        self.zoom = zoom
        self.refresh()

    async def on_mount(self):
        if self._initial_address:
            await self.set_address(self._initial_address)

    def compose(self):
        imagem = self.tipo.value(classes="imagem")
        yield imagem

    def _pan_by_keys(self, dx: int, dy: int):
        PAN_PIXELS = 170

        if self.zoom not in self._ppd_cache:
            degrees_per_tile = 360.0 / (2 ** self.zoom)
            self._ppd_cache[self.zoom] = 256 / degrees_per_tile

        pixels_per_degree = self._ppd_cache[self.zoom]
        degrees_per_pixel = 1.0 / pixels_per_degree

        self._center_lon += dx * PAN_PIXELS * degrees_per_pixel
        self._center_lat += dy * PAN_PIXELS * degrees_per_pixel

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
        self.location = self.geolocator.geocode(address)
        self.lat = self.location.latitude
        self.lon = self.location.longitude
        self.marker = (self.lat, self.lon)
        self._center_on(self.lat, self.lon)
        self._dirty = True

    def _center_on(self, lat, lon):
        self._center_lat = lat
        self._center_lon = lon
        self._offset_x = 0
        self._offset_y = 0
        self._dirty = True

    async def on_mouse_down(self, event: events.MouseDown):
        btn = getattr(event, "button", None)
        is_left = False
        try:
            is_left = btn == 1 or str(btn).lower() == "left"
        except Exception:
            is_left = False
        if not is_left:
            return

        self._dragging = True
        sx = getattr(event, "screen_x", None)
        sy = getattr(event, "screen_y", None)
        if sx is None or sy is None:
            self._last_mouse = (event.x, event.y)
        else:
            self._last_mouse = (sx, sy)

    async def on_mouse_up(self, event: events.MouseUp):
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

    # Todo: Fix
    async def on_click(self, event: events.Click) -> None:
        if event.chain > 1:
            click_x, click_y = event.x, event.y

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

            degrees_per_tile = 360.0 / (2 ** self.zoom)
            pixels_per_degree = 256 / degrees_per_tile

            dx = click_x * 7.5 - px_w / 2
            dy = click_y * 16 - px_h / 2

            new_lon = center_lon + dx / pixels_per_degree
            new_lat = center_lat - dy / pixels_per_degree

            self.marker = (new_lat, new_lon)
            self._dirty = True

    # Todo: Fix
    def _set_zoom(self, value: int):
        new_zoom = max(0, min(18, value))
        if new_zoom == self.zoom:
            return

        if self.marker:
            mlat, mlon = self.marker
            old_zoom = self.zoom
            old_ppd = 256 / (360.0 / (2 ** old_zoom))
            center_lat = self._offset_y
            center_lon = self._offset_x
            old_dx = (mlon - center_lon) * old_ppd
            old_dy = -(mlat - center_lat) * old_ppd
            self.zoom = new_zoom
            new_ppd = 256 / (360.0 / (2 ** new_zoom))
            self._offset_x = mlon - (old_dx * new_ppd / old_ppd) / new_ppd
            self._offset_y = mlat + (old_dy * new_ppd / old_ppd) / new_ppd
        else:
            self.zoom = new_zoom

        self._dirty = True

    async def on_mouse_scroll(self, event: events.MouseScroll) -> None:
        event.stop()
        self._set_zoom(self.zoom + (1 if event.delta_y < 0 else -1))

    def _keyboard_pan_step(self):
        base = 5.0
        return base / (1 + self.zoom * 0.8)

    def render(self) -> RenderableType:
        if not self._dirty and self._last_image:
            return Text("")

        w = max(10, self.size.width or 80)
        h = max(4, self.size.height or 20)

        px_w = int(w * 7.5)
        px_h = int(h * 16)

        center_lat = getattr(self, "_center_lat", 0.0) + self._offset_y
        center_lon = getattr(self, "_center_lon", 0.0) + self._offset_x

        img, _, _ = get_tiles_cached(
            center_lat,
            center_lon,
            self.zoom,
            px_w,
            px_h,
        )
        draw = ImageDraw.Draw(img)

        if self.marker:
            mlat, mlon = self.marker
            if self.zoom not in self._ppd_cache:
                degrees_per_tile = 360.0 / (2 ** self.zoom)
                self._ppd_cache[self.zoom] = 256 / degrees_per_tile
            pixels_per_degree = self._ppd_cache[self.zoom]

            dx = (mlon - center_lon) * pixels_per_degree
            dy = -(mlat - center_lat) * pixels_per_degree

            mx = px_w // 2 + int(dx)
            my = px_h // 2 + int(dy)

            if not hasattr(self, "_marker_radius"):
                self._marker_radius = {}

            r = self._marker_radius.get(px_w)
            if r is None:
                r = max(5, int(min(px_w, px_h) * 0.02))
                self._marker_radius[px_w] = r

            draw.ellipse(
                (mx - r - 2, my - r - 2, mx + r + 2, my + r + 2),
                fill=(255, 255, 255),
            )
            draw.ellipse(
                (mx - r, my - r, mx + r, my + r),
                fill=(230, 60, 60),
            )
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

        widget_imagem = self.query_one(".imagem")
        if img is not self._last_sent_image:
            widget_imagem.image = img
            self._last_sent_image = img

        self._dirty = False
        self._last_image = img

        return Text("")
