"""The size of the scenarios' new trees, from the trees standing now (Jacob, 18 Oct 2026: "8m trees by every bus stop seems
very tall, are you sure that's right"; "do it based on existing sizes. trees can grow. it's just 8m seems a lot"). Until
then the new tree was TreePlanter's medium tree (Wallenberg et al. 2022, Table 1: 8 m tall, 5 m crown, 2 m trunk zone).

The trees are found as treecount.py finds them: local maxima of the 2021 lidar's canopy height model (smoothed by a 1 m
Gaussian) over 2.5 m, each sought in a window as wide as the crown a tree of its height has (Popescu & Wynne 2004,
deciduous: crown width = 3.09632 + 0.00895 h^2 m). Kept are the trees inside the area (area.py) whose crown, by the same
rule, reaches a footpath (OpenStreetMap's walking ways as treeplant.py takes them) or a bus stop's 3 x 3 m waiting area
(NaPTAN): the trees beside the places the new ones are for. The new tree is their median height, with the crown that
rule gives it and the trunk zone solweig gives every tree (0.25 x height, Lindberg & Grimmond 2011).
Writes layers/treesize.json, which treeplant.py reads.
usage: <heat venv python> -I treesize.py <repo root>
"""
import csv, json, sys
from pathlib import Path
import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.features import rasterize
from rasterio.transform import from_origin
from scipy import ndimage as ndi
from shapely.geometry import LineString, box
from shapely.strtree import STRtree

ROOT = Path(sys.argv[1]); H = ROOT / "data" / "mk" / "heat"; L = H / "layers"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from area import area  # noqa: E402

pool = {t["id"]: t for t in json.load(open(H / "rounds" / "pool.json"))["tiles"]}
tiles = sorted(p.stem for p in (H / "utci").glob("*.npz"))
BANDS = [(2.5, 5), (5, 10), (10, 15), (15, 20), (20, 60)]          # treecount.py's
crown = lambda h: 3.09632 + 0.00895 * h ** 2                        # Popescu & Wynne (2004), deciduous, m
TRUNK = 0.25                                                       # solweig's trunk_ratio (shade.py, utci.py)
reg = area(H)
to_bng = Transformer.from_crs(4326, 27700, always_xy=True).transform

WALK = {"footway", "pedestrian", "path", "steps", "cycleway", "living_street", "bridleway"}     # as treeplant.py
ways = []
for w in json.load(open(H / "osm" / "walk_now.json"))["elements"]:
    tg = w.get("tags", {})
    if w["type"] != "way" or tg.get("highway") not in WALK or tg.get("indoor", "no") != "no":
        continue
    if tg.get("covered") == "yes" or tg.get("tunnel", "no") != "no" or (tg.get("layer", "0").lstrip("-").isdigit() and int(tg.get("layer", "0")) < 0):
        continue
    ex, ny = to_bng([p["lon"] for p in w["geometry"]], [p["lat"] for p in w["geometry"]])
    if len(ex) > 1:
        ways.append(LineString(zip(ex, ny)))
wtree = STRtree(ways)
stops = []
for row in csv.DictReader(open(H / "naptan" / "naptan_049.csv")):
    if row["StopType"] == "BCT" and row["Status"] == "active":
        try:
            stops.append((float(row["Easting"]), float(row["Northing"])))
        except ValueError:
            pass

heights = []
for t in tiles:
    cx0, cy0, cx1, cy1 = pool[t]["core"]; bx0, by0, bx1, by1 = pool[t]["bounds"]
    shp = (int(by1 - by0), int(bx1 - bx0)); tr = from_origin(bx0, by1, 1, 1)
    cd = rasterio.open(H / "surfaces" / f"{t}_cdsm.tif").read(1).astype(np.float32)
    sm = ndi.gaussian_filter(cd, 1.0); tops = np.zeros(cd.shape, bool)
    for h0, h1 in BANDS:
        k = max(3, int(round(crown((h0 + h1) / 2))) | 1)
        tops |= (sm == ndi.maximum_filter(sm, size=k)) & (sm >= h0) & (sm < h1) & (cd >= 2.5)
    # footpaths and stops over the whole crop (its margin too), so a tree near the core's edge sees a path beyond it
    near = [ways[i] for i in wtree.query(box(bx0, by0, bx1, by1))]
    ped = (rasterize([(g, 1) for g in near], out_shape=shp, transform=tr, fill=0, dtype="uint8", all_touched=True).astype(bool)
           if near else np.zeros(shp, bool))
    for e, nn in stops:
        if bx0 <= e < bx1 and by0 <= nn < by1:
            r0, c0 = int(by1 - 1 - nn), int(e - bx0); ped[max(r0 - 1, 0):r0 + 2, max(c0 - 1, 0):c0 + 2] = True
    if not ped.any():
        continue
    dist = ndi.distance_transform_edt(~ped)
    core = np.zeros(shp, bool); core[int(by1 - cy1):int(by1 - cy0), int(cx0 - bx0):int(cx1 - bx0)] = True
    inside = rasterize([(reg, 1)], out_shape=shp, transform=tr, fill=0, dtype="uint8").astype(bool)
    rr, cc = np.nonzero(tops & core & inside)
    h = cd[rr, cc]
    keep = dist[rr, cc] <= crown(h) / 2                              # the crown reaches a path or a stop
    heights += h[keep].tolist()

h = np.asarray(heights)
med = float(np.median(h))
res = {"height": round(med, 1), "crown": round(crown(med), 1), "trunk": round(TRUNK * med, 1),
       "n_trees": int(h.size), "p25": round(float(np.percentile(h, 25)), 1), "p75": round(float(np.percentile(h, 75)), 1),
       "tiles": len(tiles),
       "rule": "median height of the trees (treecount.py's treetops) inside the area whose Popescu & Wynne (2004) crown reaches "
               "a footpath or a bus stop's waiting area; crown by the same rule; trunk zone 0.25 x height (solweig)"}
json.dump(res, open(L / "treesize.json", "w"), indent=1)
print(json.dumps(res, indent=1), flush=True)
