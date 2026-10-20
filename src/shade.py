"""Hourly shade on 13 Aug 2026 (the summer's hottest day) for each Milton Keynes crop, from the surfaces
(surfaces.py), with SOLWEIG's own shadow casting (solweig.rustalgos.shadowing.calculate_shadows_wall_ht_25,
UMEP's Ratti & Richens / Lindberg & Grimmond scheme) and its conventions: heights absolute; vegetation with a
trunk zone of 0.25 x canopy height (solweig's default, Lindberg & Grimmond 2011); vegetation lets 3% of the beam
through in leaf (SOLWEIG's leaf-on transmissivity; 13 Aug is in its leaf-on days); sunlit share =
bldg_sh - (1 - veg_sh)(1 - 0.03). Sun positions from solweig.Weather.compute_derived for Milton Keynes.
Hours 06:00-19:00 UTC on the hour, the sun above solweig's 3 degree floor. GPU off while v3 trains.
Saves per crop: shade/<tile>.npz with sun (sunlit share x 200, uint8), bshade (building shade) and
vshade (tree shade on ground the buildings leave in sun), core cells only, one layer per hour, and bld
(building cells, dsm above dem).

usage: <heat venv python> -I shade.py <repo root> [tile ids...]
"""
import datetime as dt, json, sys
from pathlib import Path
import numpy as np
import rasterio
import solweig
from solweig.rustalgos import shadowing

ROOT = Path(sys.argv[1])
SURF = ROOT / "data" / "mk" / "heat" / "surfaces"
OUT = ROOT / "data" / "mk" / "heat" / "shade"; OUT.mkdir(parents=True, exist_ok=True)
pool = {t["id"]: t for t in json.load(open(ROOT / "data" / "mk" / "heat" / "rounds" / "pool.json"))["tiles"]}
ids = sys.argv[2:] or sorted(pool)
solweig.disable_gpu()
LOC = solweig.Location(latitude=52.04, longitude=-0.76, altitude=110.0, utc_offset=0)
TRANS = 0.03            # SOLWEIG leaf-on transmissivity
TRUNK = 0.25            # solweig trunk_ratio default (Lindberg & Grimmond 2011)
MIN_VEG = 1.0           # solweig min_object_height
hours, suns = [], []
for h in range(6, 20):
    w = solweig.Weather(datetime=dt.datetime(2026, 8, 13, h, 0), ta=30.0, rh=30.0, global_rad=500.0)
    w.compute_derived(LOC)
    if w.sun_altitude > 3.0:
        hours.append(h); suns.append((float(w.sun_azimuth), float(w.sun_altitude)))
for tid in ids:
    if not (SURF / f"{tid}_dsm.tif").exists() or (OUT / f"{tid}.npz").exists():
        continue
    rd = lambda n: rasterio.open(SURF / f"{tid}_{n}.tif").read(1).astype(np.float32)
    dsm, dem, cdsm = rd("dsm"), rd("dem"), rd("cdsm")
    veg = cdsm >= MIN_VEG
    canopy = np.where(veg, dem + cdsm, 0).astype(np.float32)
    trunk = np.where(veg, dem + TRUNK * cdsm, 0).astype(np.float32)
    bush = np.zeros_like(dsm)
    hmax = float(np.nanmax(np.maximum(dsm, canopy)) - np.nanmin(dsm))
    t = pool[tid]; x0, y0, x1, y1 = t["bounds"]; cx0, cy0, cx1, cy1 = t["core"]
    r0, r1 = int(y1 - cy1), int(y1 - cy0); c0, c1 = int(cx0 - x0), int(cx1 - x0)   # core rows/cols (row 0 = north)
    sun, bsh, vsh = [], [], []
    for az, alt in suns:
        r = shadowing.calculate_shadows_wall_ht_25(az, alt, 1.0, hmax, dsm, veg_canopy_dsm=canopy, veg_trunk_dsm=trunk, bush=bush)
        b = np.asarray(r.bldg_sh, np.float32); v = np.asarray(r.veg_sh, np.float32)
        lit = np.clip(b - (1 - v) * (1 - TRANS), 0, 1)
        sun.append((lit[r0:r1, c0:c1] * 200).round().astype(np.uint8))
        bsh.append((1 - b[r0:r1, c0:c1]).round().astype(np.uint8))
        vsh.append(((1 - v[r0:r1, c0:c1]) * b[r0:r1, c0:c1]).round().astype(np.uint8))
    np.savez_compressed(OUT / f"{tid}.npz", hours=np.array(hours), sun=np.stack(sun), bshade=np.stack(bsh), vshade=np.stack(vsh),
                        core=np.array(t["core"]), suns=np.array(suns), bld=(dsm > dem)[r0:r1, c0:c1])
    print(tid, "done", flush=True)
