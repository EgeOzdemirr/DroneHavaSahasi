from __future__ import annotations

import json
import math
import time
import urllib.request
from pathlib import Path


LEAFLET_BASE = "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist"
TILE_BASE = "https://tile.openstreetmap.org"
USER_AGENT = "HavaSahasiOfflineMapSeeder/1.0 (dev-use)"
DOWNLOAD_PAUSE_SECONDS = 0.01
ROOT = Path(__file__).resolve().parents[1]
VENDOR_DIR = ROOT / "app" / "ui" / "static" / "vendor" / "leaflet"
TILE_DIR = ROOT / "app" / "ui" / "static" / "maps" / "tiles"
MANIFEST_PATH = TILE_DIR / "manifest.json"

LAYERS = [
    {
        "id": "world",
        "label": "Dunya",
        "min_lat": -85.0,
        "min_lon": -180.0,
        "max_lat": 85.0,
        "max_lon": 180.0,
        "zooms": [2, 3, 4, 5],
        "home_center": [25.0, 15.0],
        "home_zoom": 3,
    },
    {
        "id": "turkiye",
        "label": "Turkiye",
        "min_lat": 35.8,
        "min_lon": 25.6,
        "max_lat": 42.2,
        "max_lon": 44.9,
        "zooms": [5, 6, 7, 8, 9, 10],
        "home_center": [39.0, 35.2],
        "home_zoom": 7,
    },
    {
        "id": "istanbul",
        "label": "Istanbul",
        "min_lat": 40.80,
        "min_lon": 28.45,
        "max_lat": 41.40,
        "max_lon": 29.80,
        "zooms": [9, 10, 11, 12, 13],
        "home_center": [41.05, 29.05],
        "home_zoom": 10,
    },
    {
        "id": "tuzla",
        "label": "Istanbul/Tuzla",
        "min_lat": 40.78,
        "min_lon": 29.20,
        "max_lat": 40.95,
        "max_lon": 29.50,
        "zooms": [12, 13, 14, 15, 16],
        "home_center": [40.83, 29.31],
        "home_zoom": 13,
    },
]

LEAFLET_FILES = {
    "leaflet.css": f"{LEAFLET_BASE}/leaflet.css",
    "leaflet.js": f"{LEAFLET_BASE}/leaflet.js",
    "images/layers.png": f"{LEAFLET_BASE}/images/layers.png",
    "images/layers-2x.png": f"{LEAFLET_BASE}/images/layers-2x.png",
    "images/marker-icon.png": f"{LEAFLET_BASE}/images/marker-icon.png",
    "images/marker-icon-2x.png": f"{LEAFLET_BASE}/images/marker-icon-2x.png",
    "images/marker-shadow.png": f"{LEAFLET_BASE}/images/marker-shadow.png",
}


def deg2tile(lat_deg: float, lon_deg: float, zoom: int) -> tuple[int, int]:
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    xtile = max(0, min(int(n - 1), xtile))
    ytile = max(0, min(int(n - 1), ytile))
    return xtile, ytile


def tile_ranges(layer: dict[str, object]) -> dict[int, tuple[range, range]]:
    min_lat = float(layer["min_lat"])
    min_lon = float(layer["min_lon"])
    max_lat = float(layer["max_lat"])
    max_lon = float(layer["max_lon"])
    ranges: dict[int, tuple[range, range]] = {}
    for zoom in layer["zooms"]:
        min_x, max_y = deg2tile(min_lat, min_lon, zoom)
        max_x, min_y = deg2tile(max_lat, max_lon, zoom)
        ranges[zoom] = (
            range(min(min_x, max_x), max(min_x, max_x) + 1),
            range(min(min_y, max_y), max(min_y, max_y) + 1),
        )
    return ranges


def download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        target.write_bytes(response.read())


def ensure_leaflet_assets() -> None:
    for relative_path, url in LEAFLET_FILES.items():
        target = VENDOR_DIR / relative_path
        if target.exists() and target.stat().st_size > 0:
            continue
        print(f"leaflet {relative_path}")
        download(url, target)
        time.sleep(DOWNLOAD_PAUSE_SECONDS)


def ensure_tiles_for_layer(layer: dict[str, object]) -> int:
    count = 0
    layer_id = str(layer["id"])
    for zoom, (x_range, y_range) in tile_ranges(layer).items():
        for x in x_range:
            for y in y_range:
                target = TILE_DIR / layer_id / str(zoom) / str(x) / f"{y}.png"
                if target.exists() and target.stat().st_size > 0:
                    count += 1
                    continue
                url = f"{TILE_BASE}/{zoom}/{x}/{y}.png"
                print(f"{layer_id} z{zoom}/{x}/{y}")
                download(url, target)
                count += 1
                time.sleep(DOWNLOAD_PAUSE_SECONDS)
    return count


def write_manifest(results: list[dict[str, object]]) -> None:
    payload = {
        "source": "OpenStreetMap Standard",
        "layers": results,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    ensure_leaflet_assets()
    manifest_layers: list[dict[str, object]] = []
    for layer in LAYERS:
        tile_count = ensure_tiles_for_layer(layer)
        manifest_layers.append(
            {
                "id": layer["id"],
                "label": layer["label"],
                "bbox": {
                    "min_lat": layer["min_lat"],
                    "min_lon": layer["min_lon"],
                    "max_lat": layer["max_lat"],
                    "max_lon": layer["max_lon"],
                },
                "zooms": layer["zooms"],
                "home_center": layer["home_center"],
                "home_zoom": layer["home_zoom"],
                "tile_count": tile_count,
            }
        )
    write_manifest(manifest_layers)
    total = sum(int(item["tile_count"]) for item in manifest_layers)
    print(f"done: {total} tiles ready across {len(manifest_layers)} layers")


if __name__ == "__main__":
    main()
