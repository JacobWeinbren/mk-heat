"""Parts of Milton Keynes built since the lidar survey (15 Dec 2020 - 17 Jan 2021), to grey out on the map.
A building of OS OpenMap Local (April 2026, the most complete open outlines here) is new only when two independent
checks agree (18 Oct 2026, after the first version greyed the 1979 shopping centre and Loughton):
- no OpenStreetMap building of 17 Jan 2021 (Overpass attic query with geometry) covers most of it, and
- the 2021 lidar shows little standing on its footprint: the share of its 1 m cells whose highest return of any class
  is at least 1 m (solweig's min_object_height) above the ground surface (surfaces.py hmax) is below Otsu's (1979)
  threshold on those shares, so the model's classes play no part.
An area is greyed when it is an OSM land-use area (Protomaps landuse: residential, commercial, industrial, retail,
construction and the like) whose modelled building footprint is mostly new, or a new building's own footprint;
construction sites in today's OSM are greyed too. Greying is judged on, and drawn over, the modelled tiles only.

Writes layers/newbuild.geojson (WGS84) and layers/newbuild_mask.npz (the greyed cells per tile, 1 m, core only).
usage: <heat venv python> -I new_build.py <repo root>
"""
import gzip, json, math, sys
from pathlib import Path
import numpy as np
from pmtiles.reader import Reader, MmapSource
import mapbox_vector_tile as mvt
from pyproj import Transformer
from rasterio.features import rasterize
from rasterio.transform import from_origin
from shapely.geometry import box, shape, mapping
from shapely.ops import transform as stransform, unary_union
from shapely.strtree import STRtree

ROOT = Path(sys.argv[1]); H = ROOT / "data" / "mk" / "heat"; OUT = H / "layers"; OUT.mkdir(parents=True, exist_ok=True)
pool = {t["id"]: t for t in json.load(open(H / "rounds" / "pool.json"))["tiles"]}
shade = {f.stem: f for f in sorted((H / "shade").glob("*.npz"))}
SURF = H / "surfaces"
MIN_OBJECT = 1.0

Z = 15
BUILT = {"residential", "commercial", "industrial", "retail", "construction", "school", "university", "college",
         "hospital", "military", "railway", "brownfield"}
to_bng = Transformer.from_crs(4326, 27700, always_xy=True).transform
to_wgs = Transformer.from_crs(27700, 4326, always_xy=True).transform


def tile_xy(lon, lat):
    n = 2 ** Z
    return int((lon + 180) / 360 * n), int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)


def lonlat(x, y, ext):
    def f(px, py, *_):
        n = 2 ** Z
        lon = (x + np.asarray(px) / ext) / n * 360 - 180
        lat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * (y + np.asarray(py) / ext) / n))))
        return lon, lat
    return f


# today's buildings and land-use areas from the basemap, over the tiles' cores
x0 = min(t["core"][0] for t in pool.values()); y0 = min(t["core"][1] for t in pool.values())
x1 = max(t["core"][2] for t in pool.values()); y1 = max(t["core"][3] for t in pool.values())
(lo0, lo1), (la0, la1) = [sorted(v) for v in to_wgs([x0, x1], [y0, y1])]
tx0, ty1 = tile_xy(lo0, la0); tx1, ty0 = tile_xy(lo1, la1)
src = open(H / "basemap_mk.pmtiles", "rb"); rd = Reader(MmapSource(src))
blds, lus = {}, {}   # by OSM id (Planetiler's feature id), so a feature cut across tiles is one again
for tx in range(tx0, tx1 + 1):
    for ty in range(ty0, ty1 + 1):
        d = rd.get(Z, tx, ty)
        if not d:
            continue
        d = gzip.decompress(d) if d[:2] == b"\x1f\x8b" else d
        m = mvt.decode(d, default_options={"y_coord_down": True})
        for name, keep in (("landuse", None),):
            lay = m.get(name)
            if not lay:
                continue
            for ft in lay["features"]:
                k = ft["properties"].get("kind")
                if (keep and k not in keep) or (not keep and k not in BUILT) or ft["geometry"]["type"] not in ("Polygon", "MultiPolygon"):
                    continue
                g = stransform(lonlat(tx, ty, lay["extent"]), shape(ft["geometry"]))
                g = stransform(lambda a, b, *_: to_bng(a, b), g).buffer(0)
                if g.is_empty:
                    continue
                (blds if name == "buildings" else lus).setdefault(ft.get("id") or id(ft), [k]).append(g)
src.close()
blds = [shape(f["geometry"]) for f in json.load(open(OUT / "os_buildings_27700.geojson"))["features"]]
# OSM's buildings on 17 Jan 2021 as shapes (ways, and the outer ways of multipolygon relations)
from shapely.geometry import Polygon as _Poly
old = []
for e in json.load(open(H / "osm" / "buildings_2021-01-17_geom.json"))["elements"]:
    rings = [e["geometry"]] if e["type"] == "way" and "geometry" in e else \
            [m["geometry"] for m in e.get("members", []) if m.get("role") == "outer" and "geometry" in m]
    for r in rings:
        if len(r) >= 4:
            xs, ys = to_bng([p["lon"] for p in r], [p["lat"] for p in r])
            g = _Poly(zip(xs, ys)).buffer(0)
            if not g.is_empty:
                old.append(g)
old_tree = STRtree(old)
lus = [(v[0], unary_union(v[1:])) for v in lus.values()]
print(f"{len(blds)} OS buildings, {len(old)} OSM buildings of Jan 2021 and {len(lus)} land-use areas", flush=True)

# each building's share of cells with something standing in 2021, from every modelled tile it touches
import rasterio
tree = STRtree(blds)
num = np.zeros(len(blds)); den = np.zeros(len(blds))
for tid, f in shade.items():
    t = pool[tid]; cx0, cy0, cx1, cy1 = t["core"]; bx0, by0, bx1, by1 = t["bounds"]
    hm = rasterio.open(SURF / f"{tid}_hmax.tif").read(1)
    bld = (hm[int(by1 - cy1):int(by1 - cy0), int(cx0 - bx0):int(cx1 - bx0)] >= MIN_OBJECT)
    tr = from_origin(cx0, cy1, 1.0, 1.0)
    ids = [(blds[i], i + 1) for i in tree.query(box(cx0, cy0, cx1, cy1))]
    if not ids:
        continue
    lab = rasterize(ids, out_shape=bld.shape, transform=tr, fill=0, dtype="int32", all_touched=False)
    k = lab > 0
    np.add.at(den, lab[k] - 1, 1); np.add.at(num, lab[k] - 1, bld[k])
seen = den > 0
share = np.where(seen, num / np.maximum(den, 1), np.nan)


def otsu(v, bins=100):
    h, e = np.histogram(v, bins=bins, range=(0, 1)); c = (e[:-1] + e[1:]) / 2
    w0 = np.cumsum(h); w1 = w0[-1] - w0; m0 = np.cumsum(h * c); mu0 = m0 / np.maximum(w0, 1); mu1 = (m0[-1] - m0) / np.maximum(w1, 1)
    return float(e[1:][np.argmax(w0 * w1 * (mu0 - mu1) ** 2)])


thr = otsu(share[seen])
low = seen & (share < thr)
def covered21(g):
    near = [old[j] for j in old_tree.query(g)]
    return bool(near) and unary_union(near).intersection(g).area > g.area / 2
in21 = np.array([covered21(g) if s_ else False for g, s_ in zip(blds, seen)])
new = low & ~in21
print(f"{seen.sum()} buildings over the tiles ({(seen & in21).sum()} already in OSM in Jan 2021); Otsu threshold on the share "
      f"standing in 2021 {thr:.2f}: {low.sum()} low, of which {(low & in21).sum()} were in OSM then; {new.sum()} new", flush=True)
done = unary_union([box(*pool[t]["core"]) for t in shade])

# greyed areas: land-use areas mostly built new, construction sites, new buildings elsewhere
area_new = [g.area if n else 0.0 for g, n in zip(blds, new)]
grey = []
for k, g in lus:
    g = g.intersection(done)
    if g.is_empty:
        continue
    if k == "construction":
        grey.append(g); continue
    hit = [i for i in tree.query(g, predicate="intersects") if seen[i]]
    a_all = sum(blds[i].area for i in hit); a_new = sum(area_new[i] for i in hit)
    if a_all > 0 and a_new > a_all / 2:
        grey.append(g)
gu = unary_union(grey)
grey += [b for b, n in zip(blds, new) if n and not gu.contains(b)]
gu = unary_union(grey)
print(f"greyed {gu.area / 1e6:.2f} km2", flush=True)
masks = {}
for tid in shade:
    cx0, cy0, cx1, cy1 = pool[tid]["core"]
    masks[tid] = rasterize([(gu, 1)], out_shape=(int(cy1 - cy0), int(cx1 - cx0)), transform=from_origin(cx0, cy1, 1.0, 1.0),
                           fill=0, dtype="uint8").astype(bool)
np.savez_compressed(OUT / "newbuild_mask.npz", **masks)
parts = list(gu.geoms) if hasattr(gu, "geoms") else [gu]
json.dump({"type": "FeatureCollection", "threshold": thr, "new_buildings": int(new.sum()), "buildings": int(seen.sum()),
           "features": [{"type": "Feature", "properties": {}, "geometry": mapping(stransform(lambda a, b, *_: to_wgs(a, b), p.simplify(0.5)))}
                        for p in parts]},
          open(OUT / "newbuild.geojson", "w"), separators=(",", ":"))
print("written", OUT / "newbuild.geojson")
