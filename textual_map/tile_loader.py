from __future__ import annotations

import io
import os
import math
import tempfile
from typing import Optional, Tuple
from urllib.request import urlopen, Request
from urllib.error import URLError
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed

from PIL import Image as PILImage
from PIL import ImageDraw

TILE_SIZE = 256
MAX_WORKERS = 6
CACHE_SUBDIR = "textual_map_tiles"
OSM_SERVERS = ("a", "b", "c")

_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
_cache_dir: Optional[str] = None
_PLACEHOLDER: Optional[PILImage.Image] = None


def _get_cache_dir() -> str:
    global _cache_dir
    if _cache_dir is None:
        _cache_dir = os.path.join(tempfile.gettempdir(), CACHE_SUBDIR)
        os.makedirs(_cache_dir, exist_ok=True)
    return _cache_dir


@lru_cache(maxsize=2048)
def _load_tile_from_disk(path: str) -> PILImage.Image:
    return PILImage.open(path).copy()


def _tile_cache_path(z: int, x: int, y: int) -> str:
    return os.path.join(_get_cache_dir(), f"{z}_{x}_{y}.png")


def deg2num(lat: float, lon: float, zoom: int) -> Tuple[int, int]:
    lat = max(min(lat, 85.05112878), -85.05112878)
    lat_rad = math.radians(lat)
    n = 2 ** zoom
    xtile = int((lon + 180.0) / 360.0 * n)
    ytile = int(
        (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    )
    return xtile, ytile


def _tile_url(x: int, y: int, z: int) -> str:
    server = OSM_SERVERS[(x + y) % len(OSM_SERVERS)]
    return f"https://{server}.tile.openstreetmap.org/{z}/{x}/{y}.png"


def _get_placeholder(tile_size: int) -> PILImage.Image:
    global _PLACEHOLDER
    if _PLACEHOLDER is None:
        img = PILImage.new("RGB", (tile_size, tile_size), (240, 240, 240))
        draw = ImageDraw.Draw(img)
        for i in range(0, tile_size, 32):
            draw.line([(i, 0), (i, tile_size)], fill=(220, 220, 220))
            draw.line([(0, i), (tile_size, i)], fill=(220, 220, 220))
        _PLACEHOLDER = img
    return _PLACEHOLDER


def download_tile(x: int, y: int, z: int, timeout: float = 5.0) -> Optional[PILImage.Image]:
    n = 2 ** z
    x = x % n
    if y < 0 or y >= n:
        return None

    cache_path = _tile_cache_path(z, x, y)

    if os.path.exists(cache_path):
        try:
            return _load_tile_from_disk(cache_path)
        except Exception:
            pass

    try:
        req = Request(_tile_url(x, y, z))
        req.add_header("User-Agent", "TextualMapWidget/1.0")
        req.add_header("Accept", "image/png")

        with urlopen(req, timeout=timeout) as resp:
            img = PILImage.open(io.BytesIO(resp.read()))
            img.save(cache_path)
            return img

    except (URLError, OSError, Exception):
        return None


def get_tiles_for_region(
    center_lat: float,
    center_lon: float,
    zoom: int,
    width_px: int,
    height_px: int,
    tile_size: int = TILE_SIZE,
) -> Tuple[PILImage.Image, int, int]:

    cx, cy = deg2num(center_lat, center_lon, zoom)

    tiles_x = max(1, (width_px + tile_size - 1) // tile_size + 1)
    tiles_y = max(1, (height_px + tile_size - 1) // tile_size + 1)

    start_x = cx - tiles_x // 2
    start_y = cy - tiles_y // 2

    composite = PILImage.new(
        "RGB",
        (tiles_x * tile_size, tiles_y * tile_size),
        (240, 240, 240),
    )

    futures = {}

    for ty in range(tiles_y):
        for tx in range(tiles_x):
            x = start_x + tx
            y = start_y + ty
            futures[_executor.submit(download_tile, x, y, zoom)] = (tx, ty)

    for future in as_completed(futures):
        tx, ty = futures[future]
        img = future.result()

        if img:
            if img.size != (tile_size, tile_size):
                img = img.resize((tile_size, tile_size),
                                 PILImage.Resampling.LANCZOS)
            composite.paste(img, (tx * tile_size, ty * tile_size))
        else:
            composite.paste(
                _get_placeholder(tile_size),
                (tx * tile_size, ty * tile_size),
            )

    composite = composite.crop((0, 0, width_px, height_px))
    return composite, tiles_x, tiles_y
