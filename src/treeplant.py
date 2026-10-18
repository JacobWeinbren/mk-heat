"""Where a few new trees would cool Milton Keynes' footpaths and bus stops most (Jacob, 18 Oct 2026: "model what would
happen if you put the fewest possible trees in the most strategic areas"; "on the switch it could be modelling an
alternative Thursday").

Method: the greedy variant of TreePlanter (Wallenberg, Lindberg & Rayner 2022, GMD 15:1107, Sect. 2.4), as published
except where stated:
- the tree is the paper's medium tree (Table 1): 8 m tall, 5 m crown diameter, 2 m trunk, shortwave transmissivity 0.03
  (SOLWEIG's leaf-on value); its shade for each hour is cast on flat ground with SOLWEIG's own shadow routine;
- a tree's benefit is the drop in mean radiant temperature over the cells its shade newly covers, summed over the hours:
  for each such cell and hour, the cell's SOLWEIG Tmrt in sun minus the Tmrt of tree shade at that hour. The paper takes
  the shaded Tmrt from a 1-D SOLWEIG run; here it is the median Tmrt of open cells under tree shade in the same tile and
  hour of our own SOLWEIG run (stated deviation);
- unlike the paper, which counts every sunlit ground cell, only the cells people use count: footpath centrelines (1 m
  samples of today's OSM walking ways, out of doors) and the 3 x 3 m around each bus stop (stated deviation, the question
  being about footpaths and stops);
- the hours are those in which any footpath felt like 38 C UTCI or more (from the run itself);
- a tree may stand on open ground that is not a building, carriageway, railway land, water or existing canopy, at least
  one crown radius from a building (the paper's rule), not within 1.5 m of a footpath's line (MK's redways are 3 m
  wide), and at least one crown diameter from another new tree (the paper's rule);
- greedy: place the tree with the largest benefit, mark the cells it shades as shaded for those hours, drop candidates
  within a crown diameter, recompute benefits nearby, repeat. Shade is counted within each tile's core (trees near a
  tile edge are slightly undervalued).
Writes layers/trees.json: the trees in order with each one's benefit and the running totals (the curve), and
layers/trees_cdsm/<tile>.npy, the added canopy (relative height) for the SOLWEIG rerun of the chosen number of trees.
usage: <heat venv python> -I treeplant.py <repo root> [max trees] [--plant N | --plant-round K]
The curve runs over every tree that still removes some heat (no cap) unless max trees is given; the knee is found on it.
--plant N: the scenario plants the first N trees of the greedy order instead of the knee's number (Jacob, 18 Oct 2026:
"Why not a round number like 1000 trees"); --plant-round K plants the knee rounded up to a multiple of K (1000 gave
central MK's 1,000 from its knee); the knee is still found and recorded
"""
import json, math, sys
from pathlib import Path
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from scipy import ndimage as ndi
from scipy.signal import fftconvolve
from pyproj import Transformer
from shapely.geometry import LineString
import solweig
from solweig.rustalgos import shadowing

ROOT = Path(sys.argv[1]); H = ROOT / "data" / "mk" / "heat"; L = H / "layers"
PLANT = ROUND = None
# --stops-first: bus stops get their trees before footpaths (Jacob, 18 Oct 2026: "Bus stops still quite high though, no?"):
# people wait at a stop, they pass along a path. First a greedy run whose benefit is the stop-hours a tree shades: a
# stop's waiting area (the 3 x 3 m the page's stop figures average) in an hour it is sunlit and at 38 C UTCI or more, a
# cell an hour, until no tree shades another; then
# the usual run on all of it. Every stop tree is planted; the footpath trees fill the rest of the number
STOPS_FIRST = "--stops-first" in sys.argv or "--stops-only" in sys.argv
STOPS_ONLY = "--stops-only" in sys.argv      # the stop trees alone (Jacob: "Maybe we should just focus on that then")
NAME = "trees"                                 # --name NAME: writes layers/NAME.json and layers/NAME_cdsm/ (one per scenario)
if "--name" in sys.argv:
    _i = sys.argv.index("--name"); NAME = sys.argv[_i + 1]; del sys.argv[_i:_i + 2]
sys.argv = [a_ for a_ in sys.argv if a_ not in ("--stops-first", "--stops-only")]
if "--plant" in sys.argv:
    _i = sys.argv.index("--plant"); PLANT = int(sys.argv[_i + 1]); del sys.argv[_i:_i + 2]
if "--plant-round" in sys.argv:
    _i = sys.argv.index("--plant-round"); ROUND = int(sys.argv[_i + 1]); del sys.argv[_i:_i + 2]
MAXN = int(sys.argv[2]) if len(sys.argv) > 2 else 10 ** 9      # no cap: every tree with some benefit
TREE_H, CROWN_D, TRUNK_H, TRANS = 8.0, 5.0, 2.0, 0.03        # TreePlanter Table 1 "medium"; SOLWEIG leaf-on transmissivity
HOT = 38.0
PATH_HALF = 1.5                                             # half the 3 m width of an MK redway
pool = {t["id"]: t for t in json.load(open(H / "rounds" / "pool.json"))["tiles"]}
tiles = sorted(p.stem for p in (H / "utci").glob("*.npz"))
roadm = dict(np.load(L / "road_mask.npz")); greym = dict(np.load(L / "newbuild_mask.npz"))
to_bng = Transformer.from_crs(4326, 27700, always_xy=True).transform
solweig.disable_gpu()

# hours: those in which some footpath reached the hot threshold (from the page's own data)
D = json.load(open(ROOT / "data" / "experiments" / "mk_heat" / "web" / "out" / "data.json"))
hot_k = sorted({k for p in D["paths"] if p[1] for k, v in enumerate(p[1]) if v >= HOT})
sh0 = np.load(H / "shade" / f"{tiles[0]}.npz")
sh_hours = [int(h) for h in sh0["hours"]]; suns = sh0["suns"]
hours = [sh_hours[k] for k in hot_k]
print("hours (UTC, end of interval):", hours, flush=True)

# the tree's shade on flat ground, one stamp per hour (offsets from the trunk cell)
R = int(math.ceil(TREE_H / math.tan(math.radians(min(suns[k][1] for k in hot_k))))) + 4
n = 2 * R + 1; yy, xx = np.mgrid[-R:R + 1, -R:R + 1]
disk = (xx ** 2 + yy ** 2) <= (CROWN_D / 2) ** 2
flat = np.zeros((n, n), np.float32)
canopy = np.where(disk, TREE_H, 0).astype(np.float32); trunk = np.where(disk, TRUNK_H, 0).astype(np.float32)
stamps = []
for k in hot_k:
    az, alt = suns[k]
    r = shadowing.calculate_shadows_wall_ht_25(float(az), float(alt), 1.0, TREE_H, flat, veg_canopy_dsm=canopy, veg_trunk_dsm=trunk, bush=np.zeros_like(flat))
    # the shade as solweig's own shadow routine gives it, the crown's footprint included only where it shades itself (the
    # crown's sunward edge is lit in solweig, so counting the whole footprint as shade put trees on the stops they were
    # to shade, 18 Oct 2026)
    stamps.append(np.asarray(r.veg_sh) < 0.5)
print("tree shade stamps", [int(s.sum()) for s in stamps], "cells", flush=True)


WALK = {"footway", "pedestrian", "path", "steps", "cycleway", "living_street", "bridleway"}
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
stops = []
import csv
for row in csv.DictReader(open(H / "naptan" / "naptan_049.csv")):
    if row["StopType"] == "BCT" and row["Status"] == "active":
        try:
            stops.append((float(row["Easting"]), float(row["Northing"])))
        except ValueError:
            pass

from shapely.strtree import STRtree
from shapely.geometry import box
wtree = STRtree(ways)
# Trees in different tiles do not interact here (shade is counted within each tile's core), and within a tile each
# tree's gain is no larger than the one before it (a tree only removes benefit), so the greedy run over all tiles at
# once picks the same trees in the same order as running it tile by tile and merging the tiles' picks by gain; done so,
# one tile's arrays are held at a time (the city's 138 tiles together would hold about 3.5 GB)
picks = []                                           # (gain, tile, row, col), every tile's greedy run
import heapq
top = []                                             # the MAXN largest gains so far: a tile stops once its next tree's
allB = 0.0                                           # gain is below the smallest of them (its later trees gain less)
for t in tiles:
    cx0, cy0, cx1, cy1 = pool[t]["core"]; bx0, by0, bx1, by1 = pool[t]["bounds"]
    shp = (int(cy1 - cy0), int(cx1 - cx0)); tr = from_origin(cx0, cy1, 1, 1)
    sl = (slice(int(by1 - cy1), int(by1 - cy0)), slice(int(cx0 - bx0), int(cx1 - bx0)))
    near = [ways[i] for i in wtree.query(box(cx0, cy0, cx1, cy1))]
    line = rasterize([(g, 1) for g in near], out_shape=shp, transform=tr, fill=0, dtype="uint8", all_touched=True).astype(bool) if near else np.zeros(shp, bool)
    band = rasterize([(g.buffer(PATH_HALF), 1) for g in near], out_shape=shp, transform=tr, fill=0, dtype="uint8").astype(bool) if near else np.zeros(shp, bool)
    ped = line.copy(); stopm = np.zeros(shp, bool)
    for e, nn in stops:
        if cx0 <= e < cx1 and cy0 <= nn < cy1:
            r0, c0 = int(cy1 - 1 - nn), int(e - cx0); stopm[max(r0 - 1, 0):r0 + 2, max(c0 - 1, 0):c0 + 2] = True
    ped |= stopm
    sh = np.load(H / "shade" / f"{t}.npz"); bld = sh["bld"].astype(bool)
    z = np.load(H / "utci" / f"{t}.npz"); uh = list(z["hours"])
    tm = np.stack([z["tmrt"][uh.index(h)] / 10 for h in hours]).astype(np.float32)
    ut = np.stack([z["utci"][uh.index(h)] / 10 for h in hours]).astype(np.float32)
    centre = np.zeros(shp, bool)
    for e, nn in stops:
        if cx0 <= e < cx1 and cy0 <= nn < cy1:
            centre[int(cy1 - 1 - nn), int(e - cx0)] = True
    lit = np.stack([sh["sun"][sh_hours.index(h)] / 200 for h in hours]).astype(np.float32)
    vsh = np.stack([sh["vshade"][sh_hours.index(h)] for h in hours]).astype(bool)
    cd = rasterio.open(H / "surfaces" / f"{t}_cdsm.tif").read(1)[sl]
    wat = rasterio.open(H / "surfaces" / f"{t}_wat.tif").read(1)[sl] > 0.5
    open_ = ~bld & ~roadm[t] & ~greym[t] & ~wat
    tshade = np.array([np.median(tm[k][open_ & vsh[k]]) if (open_ & vsh[k]).sum() > 50 else np.nan for k in range(len(hours))], np.float32)
    if not np.isfinite(tshade).all():
        tshade = np.where(np.isfinite(tshade), tshade, np.nanmedian(tshade))
    B = np.where(ped[None] & (lit >= 0.5) & ~bld[None], np.maximum(tm - tshade[:, None, None], 0), 0).astype(np.float32)
    B1 = (stopm[None] & (lit >= 0.5) & (ut >= HOT)).astype(np.float32)           # the hot stop cell-hours
    del tm, lit, vsh, z, sh, ut
    allB += float(B.sum())
    far = ndi.binary_dilation(bld, iterations=int(math.ceil(CROWN_D / 2)))       # one crown radius from buildings
    cand = open_ & ~far & (cd < 1.0) & ~band & ~stopm          # never on a stop's waiting area: people stand there
    def greedy(Bw, phase, cap):
        """the greedy run on the benefit Bw (B itself, or B1), planting into B, Bw and cand; its picks"""
        conv = lambda A: sum(fftconvolve(A[k], stamps[k][::-1, ::-1].astype(np.float32), mode="same") for k in range(len(hours)))
        gain = np.where(cand, np.maximum(conv(Bw), 0), 0).astype(np.float32)
        out = []
        while len(out) < cap:
            r, c = np.unravel_index(int(np.argmax(gain)), gain.shape); g = float(gain[r, c])
            if g < (0.5 if phase == 1 else 1e-9) or (phase == 2 and len(top) == MAXN and g < top[0]):
                break
            for k in range(len(hours)):              # the cells this tree shades are now shaded
                ys, xs = np.nonzero(stamps[k]); ys = ys - R + r; xs = xs - R + c
                ok = (ys >= 0) & (ys < B.shape[1]) & (xs >= 0) & (xs < B.shape[2])
                B[k, ys[ok], xs[ok]] = 0; Bw[k, ys[ok], xs[ok]] = 0
            D2 = int(math.ceil(CROWN_D))             # no other new tree within a crown diameter
            y0, y1, x0, x1 = max(r - D2, 0), r + D2 + 1, max(c - D2, 0), c + D2 + 1
            yy_, xx_ = np.mgrid[y0:min(y1, cand.shape[0]), x0:min(x1, cand.shape[1])]
            cand[yy_, xx_] &= ((yy_ - r) ** 2 + (xx_ - c) ** 2) > CROWN_D ** 2
            W = 2 * R + 1                             # recompute the gains the change can reach
            a0, a1, b0, b1 = max(r - 2 * W, 0), min(r + 2 * W + 1, B.shape[1]), max(c - 2 * W, 0), min(c + 2 * W + 1, B.shape[2])
            sub = conv(Bw[:, a0:a1, b0:b1])
            i0, i1, j0, j1 = r - W - a0, r + W + 1 - a0, c - W - b0, c + W + 1 - b0
            i0, j0 = max(i0, 0), max(j0, 0); i1, j1 = min(i1, sub.shape[0]), min(j1, sub.shape[1])
            gain[a0 + i0:a0 + i1, b0 + j0:b0 + j1] = np.where(cand[a0 + i0:a0 + i1, b0 + j0:b0 + j1], np.maximum(sub[i0:i1, j0:j1], 0), 0)
            out.append((g, t, int(r), int(c), phase))
            if phase == 2:
                heapq.heappush(top, g) if len(top) < MAXN else heapq.heappushpop(top, g)
        return out
    mine = greedy(B1, 1, MAXN) if STOPS_FIRST else []
    if not STOPS_ONLY:
        mine += greedy(B, 2, MAXN)
    picks += mine; n_t = len(mine)
    print(f"{t}: {n_t} trees, best gain {picks[-n_t][0] if n_t else 0:.0f}", flush=True)
    del B, cand
picks.sort(key=lambda p_: (p_[4], -p_[0]))         # the merged greedy order: stop trees first (all of them), then by gain
chosen, total = [], 0.0
for g, t, r, c, ph in picks[:MAXN]:
    total += g if ph == 2 else 0                     # a stop tree's gain is in stop-hours, not in the footpath unit
    cx0, cy0, cx1, cy1 = pool[t]["core"]
    chosen.append({"tile": t, "row": r, "col": c, "x": cx0 + c + 0.5, "y": cy1 - r - 0.5, "phase": ph, "gain": round(g, 1), "cum": round(total, 1),
                   "share": round(total / allB, 4)})
print(f"{len(chosen)} trees: {total / allB:.1%} of the footpath and stop Tmrt-hours above tree shade removed", flush=True)
# how many: the knee of the curve of cumulative benefit against trees (Kneedle, Satopaa et al. 2011): the point
# farthest above the straight line from the first tree to the last, both axes scaled to 0-1
cum = np.array([c["cum"] for c in chosen]); nn = np.arange(1, len(cum) + 1)
xn = (nn - 1) / max(len(cum) - 1, 1); yn = (cum - cum[0]) / max(cum[-1] - cum[0], 1e-9)
n_knee = int(np.argmax(yn - xn)) + 1
print(f"knee at {n_knee} trees: {chosen[n_knee - 1]['share']:.1%} of the removable footpath and stop heat", flush=True)
# the added canopy (height above ground) for the rerun, in every crop the tree's crown reaches
out = L / f"{NAME}_cdsm"; out.mkdir(exist_ok=True)
add = {}
n_plant = (len(chosen) if STOPS_ONLY else min(PLANT if PLANT else -(-n_knee // ROUND) * ROUND if ROUND else n_knee, len(chosen)))
print(f"planting {n_plant} trees: {chosen[n_plant - 1]['share']:.1%} of the removable footpath and stop heat", flush=True)
for c in chosen[:n_plant]:
    for t, pt in pool.items():
        bx0, by0, bx1, by1 = pt["bounds"]
        if bx0 - CROWN_D <= c["x"] < bx1 + CROWN_D and by0 - CROWN_D <= c["y"] < by1 + CROWN_D:
            a = add.setdefault(t, np.zeros((int(by1 - by0), int(bx1 - bx0)), np.float32))
            r0, c0 = int(by1 - c["y"]), int(c["x"] - bx0)
            for dy in range(-R, R + 1):
                for dx in range(-R, R + 1):
                    if dx * dx + dy * dy <= (CROWN_D / 2) ** 2 and 0 <= r0 + dy < a.shape[0] and 0 <= c0 + dx < a.shape[1]:
                        a[r0 + dy, c0 + dx] = TREE_H
for t, a in add.items():
    np.save(out / f"{t}.npy", a)
json.dump({"tree": {"height": TREE_H, "crown": CROWN_D, "trunk": TRUNK_H, "transmissivity": TRANS}, "hours": hours, "hot": HOT,
           "total_kh": round(allB, 1), "n_knee": n_knee, "n_planted": n_plant, "stops_first": STOPS_FIRST, "stops_only": STOPS_ONLY,
           "planted_rule": (f"the first {n_plant} of the greedy order, as asked" if PLANT else f"the knee rounded up to a multiple of {ROUND}"
                            if ROUND else "the knee (Kneedle)"), "trees": chosen}, open(L / f"{NAME}.json", "w"))
print(f"{len(chosen)} trees chosen; {total / allB:.1%} of the removable footpath and stop heat", flush=True)
