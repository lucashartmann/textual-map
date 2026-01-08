from typing import Tuple

# Map bounds used by the widget: longitude [-180, 180], latitude [-90, 90]


def geocode(address: str) -> Tuple[float, float]:
    """Return (lat, lon) for an address string.

    This is a deterministic stub: it hashes the address and maps it into
    plausible lat/lon ranges so multiple addresses get consistent but
    non-meaningful coordinates.
    """
    if not address:
        return 0.0, 0.0

    # Simple deterministic hash -> generate two numbers
    h = abs(hash(address))
    lon = (h % 360000) / 1000.0 - 180.0  # -180 .. 180
    lat = ((h // 360000) % 180000) / 1000.0 - 90.0  # -90 .. 90
    return float(lat), float(lon)
