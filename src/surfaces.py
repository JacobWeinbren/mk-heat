"""SOLWEIG inputs for each Milton Keynes crop from the v1 model's classes (crude prototype, 18 Oct 2026):
1 m rasters over the crop (core + the pool's 100 m margin, so shadows from neighbouring blocks fall in):
  dem   ground: median z of Ground and Water points per cell, gaps filled from the nearest cell
  dsm   ground + buildings and bridges: highest Building or Bridge point per cell over the dem (a bridge deck casts
        shade like a building; Jacob, 18 Oct 2026, on MK's underpasses); those cells closed by one cell
        (scipy binary_closing 3x3) so roofs with missing returns stay solid, their height from the nearest roof cell
  cdsm  vegetation height above the dem (highest Vegetation point), 0 elsewhere
  hmax  the highest point of any class above the project's ground surface (below), for new_build.py
  gint  the mean intensity of the cell's single-return Ground points (nan where none), and
  wat   the share of the cell's Ground and Water points that are Water, both for landcover.py
The trunk zone is solweig's default (TDSM = 0.25 x CDSM, Lindberg & Grimmond 2011) in this crude pass.
Roofs the model missed (the shopping centre's read as ground, the National Film and SciFi Museum's as bridge, 18 Oct
2026): any point other than Vegetation inside a building outline of OS OpenMap Local (April 2026) and at
least 1 m (solweig's min_object_height) above the project's ground surface (export_demo.ground_surface, the
progressive morphological filter of Zhang et al. 2003) counts as Building.
Classes come from the side round's predictions (rounds/mk/pred/<tile>.npz) mapped back to points as the cut
record defines them (round_common.point_cells), as data/experiments/mk_3d did for r001.

usage: <pipeline venv python> -I surfaces.py <repo root> [tile ids...]
"""
import json, os, sys
from pathlib import Path
import numpy as np
from scipy import ndimage as ndi

ROOT = Path(sys.argv[1])
os.environ.setdefault("ROUNDS_DIR", str(ROOT / "data" / "mk" / "heat" / "rounds"))
sys.path.insert(0, str(ROOT / "pipeline"))
import round_common as rc  # noqa: E402
import export_demo as ed  # noqa: E402
import rasterio  # noqa: E402
from rasterio.features import rasterize  # noqa: E402
from rasterio.transform import from_origin  # noqa: E402
from shapely.geometry import box, shape  # noqa: E402
from shapely.strtree import STRtree  # noqa: E402

RD = Path(os.environ["ROUNDS_DIR"])
OUT = ROOT / "data" / "mk" / "heat" / "surfaces"; OUT.mkdir(parents=True, exist_ok=True)
CELL = 1.0
MIN_OBJECT = 1.0                                               # solweig min_object_height (m)
GROUND, VEG, BUILDING, WATER, BRIDGE = 0, 1, 2, 3, 4          # classes.MODEL order
pool = {t["id"]: t for t in json.load(open(RD / "pool.json"))["tiles"]}
ids = sys.argv[2:] or sorted(pool)
# building outlines: OS OpenMap Local (April 2026, OGL; 50,451 in the MK box against OSM's 31,786, and in central MK
# 1.23 km2 of footprint against OSM's 0.86 and the lidar's own 1.26; Jacob, 18 Oct 2026: "are you using overturemaps or
# MK for building outlines? think on that")
osm = [shape(f["geometry"]) for f in json.load(open(ROOT / "data" / "mk" / "heat" / "layers" / "os_buildings_27700.geojson"))["features"]]
tree = STRtree(osm)


def fill_nearest(a):
    bad = ~np.isfinite(a)
    if not bad.any():
        return a
    idx = ndi.distance_transform_edt(bad, return_distances=False, return_indices=True)
    return a[tuple(idx)]


def per_cell(flat, z, n, how):
    out = np.full(n, np.nan)
    if not len(flat):
        return out
    order = np.lexsort((z, flat)); f, zz = flat[order], z[order]
    starts = np.r_[0, np.flatnonzero(np.diff(f)) + 1]; ends = np.r_[starts[1:], len(f)]
    if how == "max":
        out[f[starts]] = zz[ends - 1]
    else:
        out[f[starts]] = zz[(starts + ends - 1) // 2]
    return out


FIELDS = ("x", "y", "z", "intensity", "return_number", "number_of_returns")
STRIPS = RD.parent / "strips"; STRIPS.mkdir(exist_ok=True)


def classified_core(tid):
    """the tile's core points with v1's classes (v1 classified only the cores: the 100 m margin was unclassified, so
    the buildings and trees just across a tile edge cast no shade and every core's south and west edges came out
    hot; Jacob, 18 Oct 2026: "weird stripe on the map")"""
    t = pool[tid]
    cut = rc.read_json(RD / "cut" / f"{tid}.json")
    pts, _ = rc.read_points(rc.resolve(t["file"]))
    cell, kept = rc.point_cells(pts, t["origin"], rc.cut_cell(cut))
    assert rc.cells_sha256(kept) == cut["cells_sha256"], f"{tid}: cells differ from the cut record"
    p = np.load(RD / "mk" / "pred" / f"{tid}.npz", allow_pickle=True)
    cls = np.full(len(cell), 255, np.uint8); ok = cell >= 0; cls[ok] = p["cls"][cell[ok]]
    cx0, cy0, cx1, cy1 = t["core"]
    m = (pts["x"] >= cx0) & (pts["x"] < cx1) & (pts["y"] >= cy0) & (pts["y"] < cy1)
    return {k: pts[k][m] for k in FIELDS} | {"cls": cls[m]}


def strip_of(tid):
    """the classified points within one margin (100 m) of the core's edges, cached: what the neighbours' crops need"""
    f = STRIPS / f"{tid}.npz"
    if not f.exists():
        P = classified_core(tid); cx0, cy0, cx1, cy1 = pool[tid]["core"]; mg = pool[tid]["core"][0] - pool[tid]["bounds"][0]
        m = (P["x"] < cx0 + mg) | (P["x"] >= cx1 - mg) | (P["y"] < cy0 + mg) | (P["y"] >= cy1 - mg)
        np.savez_compressed(f, **{k: v[m] for k, v in P.items()})
    return dict(np.load(f))


have = {t for t in pool if (RD / "mk" / "pred" / f"{t}.npz").exists()}
for tid in ids:
    t = pool[tid]
    if tid not in have or (OUT / f"{tid}_gint.tif").exists():
        continue
    x0, y0, x1, y1 = t["bounds"]
    # the crop: the tile's own classified core and, in the margin, its neighbours' classified cores
    parts = [classified_core(tid)]
    for nb in have - {tid}:
        nx0, ny0, nx1, ny1 = pool[nb]["core"]
        if nx0 < x1 and nx1 > x0 and ny0 < y1 and ny1 > y0:
            S = strip_of(nb); m = (S["x"] >= x0) & (S["x"] < x1) & (S["y"] >= y0) & (S["y"] < y1)
            parts.append({k: v[m] for k, v in S.items()})
    pts = {k: np.concatenate([q[k] for q in parts]) for k in FIELDS}; cls = np.concatenate([q["cls"] for q in parts])
    nx, ny = int(round((x1 - x0) / CELL)), int(round((y1 - y0) / CELL))
    x, y, z = pts["x"], pts["y"], pts["z"]
    ix = np.clip(((x - x0) / CELL).astype(int), 0, nx - 1); iy = np.clip(ny - 1 - ((y - y0) / CELL).astype(int), 0, ny - 1)
    flat = iy * nx + ix
    rel = {"x": x - x0, "y": y - y0, "z": z}
    gs, gc = ed.ground_surface(rel, [x1 - x0, y1 - y0])
    hag = ed.height_above_ground(rel, gs, gc)
    fp = [(osm[i], 1) for i in tree.query(box(x0, y0, x1, y1))]
    inside = rasterize(fp, out_shape=(ny, nx), transform=from_origin(x0, y1, CELL, CELL), fill=0, dtype="uint8").astype(bool) if fp else np.zeros((ny, nx), bool)
    # inside an OSM building outline, anything standing 1 m or more above the ground that is not vegetation is building,
    # whatever the model called it: v1 read the shopping centre's roof as ground and the 6,600 m2 National Film and SciFi
    # Museum's roof as bridge (Jacob, 18 Oct 2026: "if you catch stuff like this, please find a way to fix")
    roofs = (cls != VEG) & (cls != BUILDING) & inside[iy, ix] & (hag >= MIN_OBJECT)
    cls[roofs] = BUILDING
    g = (cls == GROUND) | (cls == WATER)
    dem = fill_nearest(per_cell(flat[g], z[g], nx * ny, "median").reshape(ny, nx))
    b = (cls == BUILDING) | (cls == BRIDGE)
    roof = per_cell(flat[b], z[b], nx * ny, "max").reshape(ny, nx)
    bmask = ndi.binary_closing(np.isfinite(roof), structure=np.ones((3, 3), bool))
    roof = np.where(bmask, fill_nearest(roof), np.nan)
    dsm = np.where(bmask & (roof > dem), roof, dem)
    v = cls == VEG
    vtop = per_cell(flat[v], z[v], nx * ny, "max").reshape(ny, nx)
    cdsm = np.where(np.isfinite(vtop) & ~bmask, np.maximum(vtop - dem, 0), 0.0)
    tr = from_origin(x0, y1, CELL, CELL)
    hmax = per_cell(flat, hag, nx * ny, "max").reshape(ny, nx)
    single = (cls == GROUND) & (pts["return_number"] == 1) & (pts["number_of_returns"] == 1)
    cnt = np.bincount(flat[single], minlength=nx * ny)
    gint = np.where(cnt > 0, np.bincount(flat[single], weights=pts["intensity"][single].astype(float), minlength=nx * ny) / np.maximum(cnt, 1), np.nan)
    nw = np.bincount(flat[cls == WATER], minlength=nx * ny); ng = np.bincount(flat[cls == GROUND], minlength=nx * ny)
    wat = np.where(nw + ng > 0, nw / np.maximum(nw + ng, 1), 0.0)
    for name, arr in (("dem", dem), ("dsm", dsm), ("cdsm", cdsm), ("hmax", np.nan_to_num(hmax, nan=0.0)),
                      ("gint", gint.reshape(ny, nx)), ("wat", wat.reshape(ny, nx))):
        with rasterio.open(OUT / f"{tid}_{name}.tif", "w", driver="GTiff", height=ny, width=nx, count=1, dtype="float32",
                           crs="EPSG:27700", transform=tr, compress="deflate") as o:
            o.write(arr.astype(np.float32), 1)
    print(tid, f"buildings {bmask.mean():.1%} of cells, canopy over 1 m {np.mean(cdsm > 1):.1%}, {roofs.sum():,} ground points on roofs",
          flush=True)
