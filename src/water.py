"""Water for the heat map (Jacob, 18 Oct 2026: "willen lake is a big red splotch. obviously people don't walk in lakes,
rivers, streams, ponds - can you account for this?"). The lidar sees little of still water, so v1 labels most of a
lake's few returns Ground and the land cover (landcover.py) made Willen Lake 73% paved. This adds OpenStreetMap's
water areas as on 17 Jan 2021 (the survey's month, as the roads and buildings), over the basemap's extent:
  natural=water, waterway=riverbank, landuse=reservoir or basin, leisure=swimming_pool (ways and multipolygon
  relations), and waterway=river, canal, stream, ditch or drain lines that carry an OSM width, at that width;
a line without a width is left out (its width is unknown); the land cover's own water (most returns Water) still counts.
fetch writes osm/water_2021-01-17.json (Overpass); polygons() gives the union in British National Grid.
usage: <heat venv python> -I water.py <repo root> fetch
"""
import json, sys, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(sys.argv[1]) if __name__ == "__main__" else None
DATE = "2021-01-17T00:00:00Z"
OVERPASS = "https://overpass-api.de/api/interpreter"
LINES = "river|canal|stream|ditch|drain"


def fetch(H):
    """water areas and wide waterways as on DATE over the basemap's bounds (pmtiles header)"""
    from pmtiles.reader import Reader, MmapSource
    with open(H / "basemap_mk.pmtiles", "rb") as f:
        hd = Reader(MmapSource(f)).header()
    s, w, n, e = hd["min_lat_e7"] / 1e7, hd["min_lon_e7"] / 1e7, hd["max_lat_e7"] / 1e7, hd["max_lon_e7"] / 1e7
    q = f"""[out:json][timeout:300][date:"{DATE}"][bbox:{s},{w},{n},{e}];
(
  way["natural"="water"]; relation["natural"="water"];
  way["waterway"="riverbank"]; relation["waterway"="riverbank"];
  way["landuse"~"^(reservoir|basin)$"]; relation["landuse"~"^(reservoir|basin)$"];
  way["leisure"="swimming_pool"];
  way["waterway"~"^({LINES})$"]["width"];
);
out geom;"""
    req = urllib.request.Request(OVERPASS, data=urllib.parse.urlencode({"data": q}).encode(),
                                 headers={"User-Agent": "mk-heat-map (lidar-review)"})
    d = json.load(urllib.request.urlopen(req, timeout=600))
    out = H / "osm" / "water_2021-01-17.json"
    json.dump(d, open(out, "w"))
    print(f"{len(d['elements'])} elements -> {out}")


def polygons(H, to_bng):
    """the union of the water areas and the wide waterways, in British National Grid (shapely)"""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import linemerge, polygonize, unary_union

    def num(v):
        try:
            return float(str(v).split(";")[0].replace("m", "").strip())
        except ValueError:
            return None
    parts = []
    for e in json.load(open(H / "osm" / "water_2021-01-17.json"))["elements"]:
        tg = e.get("tags", {})
        if e["type"] == "way" and e.get("geometry"):
            x, y = to_bng([q["lon"] for q in e["geometry"]], [q["lat"] for q in e["geometry"]])
            if tg.get("waterway") in LINES.split("|"):
                w = num(tg.get("width"))
                if w and len(x) >= 2:
                    parts.append(LineString(zip(x, y)).buffer(w / 2, cap_style=2))
            elif len(x) >= 4 and e["geometry"][0] == e["geometry"][-1]:
                parts.append(Polygon(zip(x, y)).buffer(0))
        elif e["type"] == "relation":
            rings = {"outer": [], "inner": []}
            for m in e.get("members", []):
                if m.get("type") == "way" and m.get("geometry") and m.get("role") in rings:
                    x, y = to_bng([q["lon"] for q in m["geometry"]], [q["lat"] for q in m["geometry"]])
                    rings[m["role"]].append(LineString(zip(x, y)))
            outer = unary_union(list(polygonize(linemerge(rings["outer"])))) if rings["outer"] else None
            if outer is not None and not outer.is_empty:
                inner = unary_union(list(polygonize(linemerge(rings["inner"])))) if rings["inner"] else None
                parts.append(outer.difference(inner) if inner is not None and not inner.is_empty else outer)
    return unary_union(parts)


if __name__ == "__main__" and sys.argv[2:3] == ["fetch"]:
    fetch(ROOT / "data" / "mk" / "heat")
