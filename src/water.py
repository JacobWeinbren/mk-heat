"""Water for the heat map (Jacob, 18 Oct 2026: "willen lake is a big red splotch. obviously people don't walk in lakes,
rivers, streams, ponds - can you account for this?"). The lidar sees little of still water: v1 labels most of a lake's
few returns Ground, and the land cover (landcover.py) made Willen Lake 73% paved. Water is therefore also taken from
OpenStreetMap's water areas as the Protomaps basemap holds them at zoom 15 (basemap_mk.pmtiles, a Planetiler build of
OSM as of 17 Oct 2026; tile precision about 0.2 m): every polygon of its water layer (lakes, ponds, reservoirs, river
and canal areas, basins, pools). Its lines (streams and rivers drawn as a line) have no width and are left out. Water
is stable, so today's map stands in for 2021's (the dated Overpass query for 17 Jan 2021 ran out of memory on the public
server, 18 Oct 2026).
polygons(H, bounds) gives the union in British National Grid over a BNG box.
"""
import gzip, math
from pathlib import Path


def polygons(H: Path, bounds, z: int = 15):
    """the basemap's water areas over the BNG box bounds = (x0, y0, x1, y1), as one shapely geometry in BNG"""
    import mapbox_vector_tile as mvt
    from pmtiles.reader import Reader, MmapSource
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform as stransform, unary_union
    from shapely.validation import make_valid
    to_wgs = Transformer.from_crs(27700, 4326, always_xy=True).transform
    to_bng = Transformer.from_crs(4326, 27700, always_xy=True).transform
    x0, y0, x1, y1 = bounds
    lons, lats = to_wgs([x0, x1, x0, x1], [y0, y0, y1, y1])
    n = 2 ** z
    tx = lambda lon: int((lon + 180) / 360 * n)
    ty = lambda lat: int((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n)
    parts = []
    with open(H / "basemap_mk.pmtiles", "rb") as f:
        rd = Reader(MmapSource(f))
        for x in range(tx(min(lons)), tx(max(lons)) + 1):
            for y in range(ty(max(lats)), ty(min(lats)) + 1):
                raw = rd.get(z, x, y)
                if not raw:
                    continue
                layer = mvt.decode(gzip.decompress(raw)).get("water")
                if not layer:
                    continue
                ext = layer.get("extent", 4096)

                def to_lonlat(px, py, *_):         # tile units, y up (the decoder's default) -> lon, lat
                    import numpy as np
                    mx = (x + np.asarray(px) / ext) / n
                    my = (y + (ext - np.asarray(py)) / ext) / n
                    return mx * 360 - 180, np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * my))))
                for ft in layer["features"]:
                    if ft["geometry"]["type"] not in ("Polygon", "MultiPolygon"):
                        continue
                    g = make_valid(shape(ft["geometry"]))
                    parts.append(stransform(lambda a, b, *_: to_bng(*to_lonlat(a, b)), g))
    u = unary_union([p for p in parts if not p.is_empty])
    return u.buffer(0)


if __name__ == "__main__":
    import sys, json
    ROOT = Path(sys.argv[1]); H = ROOT / "data" / "mk" / "heat"
    pool = json.load(open(H / "rounds" / "pool.json"))["tiles"]
    b = (min(t["core"][0] for t in pool), min(t["core"][1] for t in pool), max(t["core"][2] for t in pool), max(t["core"][3] for t in pool))
    w = polygons(H, b)
    print(f"water over the modelled tiles: {w.area / 1e6:.2f} km2 in {len(getattr(w, 'geoms', [w]))} parts")
