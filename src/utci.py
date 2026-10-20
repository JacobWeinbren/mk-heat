"""Mean radiant temperature (Tmrt) and UTCI per hour on 13 Aug 2026 for each Milton Keynes crop, with SOLWEIG
(the solweig package, UMEP: Lindberg et al. 2008; vegetation as Lindberg & Grimmond 2011) at its published defaults:
anisotropic sky, trunk zone 0.25 x canopy height, objects under 1 m flattened, a standing person, leaf-on in August.
Surfaces from surfaces.py (the model in use's classes, rounds/mk/pred; 2020 and 2021 surveys). Forcing (Jacob, 18 Oct 2026: "use the highest
resolution, most accurate, reliable data"): the Met Office UKV model at 2 km, hourly, at each tile's centre (Open-Meteo's
Historical Forecast API, weather_ukv/, Met Office data CC BY-SA 4.0): air temperature, humidity, 10 m wind, surface
pressure, global, direct normal and diffuse radiation (diffuse = global - direct); solweig takes each value as the hour
ending at its time stamp. Checked against Cranfield airport's reported 35 C maximum (about 10 km away).
How it enters (19 Oct 2026; Jacob, of straight lines across fields at tile edges: "can you fix these lines?"): SOLWEIG
takes one value of each a run, and each tile once took its own centre's, so UTCI stepped at every tile edge (12-13 UTC,
692 edges: 0.10 C median, 0.30 C p90; Tmrt too, 0.1 and 0.3 C, from the air and radiation SOLWEIG heats the ground
with), and a field near a class edge on the map changed colour along a straight line. Now (--forcing area, the default):
- SOLWEIG has one series for the whole area, each hour's mean over the tiles' series (every variable), as SOLWEIG is run
  from one station's record for a whole domain (Lindberg et al. 2008), so Tmrt has no seams;
- UTCI is computed here from SOLWEIG's Tmrt with each 1 m cell's own air temperature, vapour pressure and 10 m wind,
  interpolated bilinearly between the tile centres' values (humidity as vapour pressure, the quantity UTCI takes; beyond
  the outermost centres the edge value holds), by UMEP's UTCI polynomial as utci_final.py evaluates it (with uniform
  inputs it gives solweig's own UTCI to the stored 0.1 C), the wind held at no less than 0.5 m/s as there.
Tested at 12-13 UTC on the stored Tmrt: the air, humidity and wind alone cut the edge step to 0.03 C median, 0.07 C p90.
--forcing tile: each tile's own centre's series in SOLWEIG and its UTCI, as before 19 Oct 2026. A file made under the
other rule is computed again, not skipped.
The whole day 00-23 UTC is run so the ground and wall temperatures build up through the morning.
Land cover (landcover.py: paved, building, grass, water) sets each cell's albedo, emissivity and ground heating when
its file is there; without it solweig treats all ground as cobblestone.
Bus shelters (shelters.py existing) are added to the canopy in every run.
Saves utci/<tile>.npz: hours (UTC, end of interval), tmrt and utci (degC x 10, int16) on the core, one layer an hour
(a scenario's utci_NAME/<tile>.npz: utci only), and the forcing rule it was made under.

usage: <heat venv python> -I utci.py <repo root> [--gpu] [--hours a-b] [--scenario NAME] [--forcing area|tile]
                                       [--out DIR] [tile ids...]
--scenario trees adds layers/trees_cdsm/<tile>.npy (treeplant.py's new trees, height above ground) to the canopy and
writes utci_trees/ instead of utci/, for the tiles a new tree reaches that have a baseline (the others are unchanged).
"""
import datetime as dt, json, shutil, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
import rasterio
import solweig
from scipy.ndimage import distance_transform_edt
sys.path.insert(0, str(Path(__file__).resolve().parent))
import utci_final as uf  # noqa: E402  (UMEP's UTCI polynomial, vapour pressure and the 0.5 m/s wind floor)

args = sys.argv[1:]; ROOT = Path(args.pop(0))
gpu = "--gpu" in args; args = [a for a in args if a != "--gpu"]
hrs = range(0, 24)
scen = None
if "--scenario" in args:
    i = args.index("--scenario"); scen = args[i + 1]; del args[i:i + 2]
FORCING = "area"
if "--forcing" in args:
    i = args.index("--forcing"); FORCING = args[i + 1]; del args[i:i + 2]
    assert FORCING in ("area", "tile"), FORCING
out_dir = None
if "--out" in args:
    i = args.index("--out"); out_dir = Path(args[i + 1]); del args[i:i + 2]
if "--hours" in args:
    i = args.index("--hours"); a, b = map(int, args[i + 1].split("-")); hrs = range(a, b + 1); del args[i:i + 2]
H = ROOT / "data" / "mk" / "heat"; SURF = H / "surfaces"; OUT = out_dir or H / ("utci" if not scen else f"utci_{scen}"); OUT.mkdir(parents=True, exist_ok=True)
pool = {t["id"]: t for t in json.load(open(H / "rounds" / "pool.json"))["tiles"]}
ids = args or sorted(pool)
if not gpu:
    solweig.disable_gpu()
LOC = solweig.Location(latitude=52.04, longitude=-0.76, altitude=110.0, utc_offset=0)
UKV = H / "weather_ukv"
series = {p[0]: u["hourly"] for p, u in zip(json.load(open(UKV / "tile_points.json")), json.load(open(UKV / "ukv_2km_2026-08-12_14.json")))}
VARS = ("temperature_2m", "relative_humidity_2m", "shortwave_radiation", "wind_speed_10m", "surface_pressure",
        "direct_normal_irradiance", "diffuse_radiation")
TIMES = next(iter(series.values()))["time"]
assert all(s["time"] == TIMES for s in series.values()), "the tiles' series cover different hours"
# the area's series: each hour's mean over every tile's
series["_area"] = {"time": TIMES, **{v: np.mean([s[v] for k, s in series.items() if k != "_area"], axis=0).tolist() for v in VARS}}
RULE = ("area: SOLWEIG with each hour's mean of the tiles' UKV series; UTCI from its Tmrt with the air, vapour pressure "
        "and 10 m wind interpolated bilinearly between tile centres, wind >= 0.5 m/s" if FORCING == "area" else "tile: ukv_2km")


# the tile centres' air temperature, vapour pressure and 10 m wind each hour on their 1 km grid, every centre that has no
# tile taking its nearest tile's (outside the area)
_c = {k: ((pool[k]["core"][0] + pool[k]["core"][2]) / 2, (pool[k]["core"][1] + pool[k]["core"][3]) / 2) for k in series if k in pool}
GX = np.arange(min(x for x, _ in _c.values()), max(x for x, _ in _c.values()) + 1, 1000.0)
GY = np.arange(min(y for _, y in _c.values()), max(y for _, y in _c.values()) + 1, 1000.0)
_at = {k: (int(round((y - GY[0]) / 1000)), int(round((x - GX[0]) / 1000))) for k, (x, y) in _c.items()}
assert all(abs(GX[j] - _c[k][0]) < 1e-6 and abs(GY[i] - _c[k][1]) < 1e-6 for k, (i, j) in _at.items()), "tile centres off the 1 km grid"
GRID = {}
for name, f in (("ta", lambda s, k: s["temperature_2m"][k]), ("pa", lambda s, k: float(uf.vapour_kpa(s["temperature_2m"][k], s["relative_humidity_2m"][k]))),
                ("va", lambda s, k: s["wind_speed_10m"][k])):
    g = np.full((len(TIMES), len(GY), len(GX)), np.nan)
    for tid, (i, j) in _at.items():
        g[:, i, j] = [f(series[tid], k) for k in range(len(TIMES))]
    near = distance_transform_edt(np.isnan(g[0]), return_distances=False, return_indices=True)
    GRID[name] = g[:, near[0], near[1]]


def _axis(centres, g):
    """bilinear weights along one axis: the lower centre's index and the upper one's share"""
    pos = np.clip((centres - g[0]) / 1000.0, 0, len(g) - 1)
    i0 = np.minimum(np.floor(pos).astype(int), max(len(g) - 2, 0)); return i0, np.clip(pos - i0, 0, 1)


def local(core, k):
    """the 1 m cells' (rows north to south) air temperature, vapour pressure (kPa) and 10 m wind at the series' hour k"""
    cx0, cy0, cx1, cy1 = core
    iy, wy = _axis(cy1 - 0.5 - np.arange(int(cy1 - cy0)), GY); ix, wx = _axis(cx0 + 0.5 + np.arange(int(cx1 - cx0)), GX)
    out = []
    for name in ("ta", "pa", "va"):
        g = GRID[name][k]; i1, j1 = np.minimum(iy + 1, len(GY) - 1), np.minimum(ix + 1, len(GX) - 1)
        top = g[iy][:, ix] * (1 - wx) + g[iy][:, j1] * wx; bot = g[i1][:, ix] * (1 - wx) + g[i1][:, j1] * wx
        out.append(top * (1 - wy)[:, None] + bot * wy[:, None])
    return out


def utci_local(tmrt, core, ks):
    """UTCI (degC) from Tmrt (hours x core) with each cell's own air, vapour pressure and wind"""
    out = np.empty(tmrt.shape, np.float64)
    for n, k in enumerate(ks):
        ta, pa, va = local(core, k)
        out[n] = uf.utci(ta, pa, tmrt[n], np.maximum(va, uf.CLAMP))
    return out


def weather_for(tid):
    """the run's weather, and each hour's index in the series"""
    wx, out, ks = series["_area" if FORCING == "area" else tid], [], []
    for k, t in enumerate(wx["time"]):
        d = dt.datetime.fromisoformat(t)
        if d.date() == dt.date(2026, 8, 13) and d.hour in hrs:
            ks.append(k)
            out.append(solweig.Weather(datetime=d, ta=wx["temperature_2m"][k], rh=wx["relative_humidity_2m"][k],
                                       global_rad=wx["shortwave_radiation"][k], ws=wx["wind_speed_10m"][k],
                                       pressure=wx["surface_pressure"][k],
                                       measured_direct_rad=wx["direct_normal_irradiance"][k],
                                       measured_diffuse_rad=wx["diffuse_radiation"][k]))
    return out, ks


def finish(tid, core, stack, names, hours, ks, lc_ok, timing):
    """UTCI (area forcing: from the Tmrt with each cell's own air and wind), the tile's file and its line"""
    t2 = time.time()
    if FORCING == "area":
        stack["utci"] = utci_local(stack["tmrt"].astype(np.float64), core, ks)
    keep = ["utci"] if scen else ["tmrt", "utci"]
    np.savez_compressed(OUT / f"{tid}.npz", hours=hours, **{v: np.round(stack[v] * 10).astype(np.int16) for v in keep},
                        files=np.array(names), land_cover=lc_ok, forcing=RULE)
    print(f"{tid}: prepare {timing[0]:.0f} s, {len(hours)} hours {timing[1]:.0f} s, utci {time.time() - t2:.0f} s, "
          f"{np.nanmin(stack['utci']):.1f}..{np.nanmax(stack['utci']):.1f}", flush=True)


# tiles' UTCI on the CPU while SOLWEIG runs the next (19 Oct 2026: SOLWEIG 12-17 s a tile on the GPU, UTCI 17-25 s in
# one thread, so two at once), at most two tiles waiting
ex, pending = ThreadPoolExecutor(max_workers=2), []
for tid in ids:
    if not (SURF / f"{tid}_dsm.tif").exists():
        continue
    if (OUT / f"{tid}.npz").exists() and str(np.load(OUT / f"{tid}.npz")["forcing"]) == RULE:
        continue                                     # made under the current forcing rule
    if scen and not ((H / "layers" / f"{scen}_cdsm" / f"{tid}.npy").exists() and (H / "utci" / f"{tid}.npz").exists()):
        continue                                     # no new tree reaches it (the baseline stands), or no baseline
    rd = lambda n: rasterio.open(SURF / f"{tid}_{n}.tif").read(1).astype(np.float32)
    dsm, dem, cdsm = rd("dsm"), rd("dem"), rd("cdsm")
    sf = H / "layers" / "shelters_cdsm" / f"{tid}.npy"                  # the bus shelters OSM records (shelters.py)
    if sf.exists():
        cdsm = np.maximum(cdsm, np.load(sf))
    if scen:
        ef = H / "layers" / f"{scen}_cdsm" / f"{tid}.npy"
        if ef.exists():
            cdsm = np.maximum(cdsm, np.where(dsm > dem, 0, np.load(ef)))     # new crowns, never on a roof
    t = pool[tid]; x0, y0, x1, y1 = t["bounds"]; cx0, cy0, cx1, cy1 = t["core"]
    r0, r1, c0, c1 = int(y1 - cy1), int(y1 - cy0), int(cx0 - x0), int(cx1 - x0)
    weather, ks = weather_for(tid)
    t0 = time.time()
    lcf = SURF / f"{tid}_lc.tif"
    lc = rasterio.open(lcf).read(1).astype(np.int32) if lcf.exists() else None
    surface = solweig.SurfaceData.prepare(dsm=dsm, dem=dem, cdsm=cdsm, land_cover=lc, pixel_size=1.0, cdsm_relative=True)
    t1 = time.time()
    tmp = Path(tempfile.mkdtemp(dir=H))
    try:
        # a scenario keeps the UTCI only: its Tmrt is read by nothing (treeplant.py and landsat_check.py read the
        # baseline's), and the borough's scenarios with it would not fit on the disk (18 Oct 2026); with the area's
        # forcing SOLWEIG gives the Tmrt and UTCI is made from it here
        outs = ["tmrt"] if FORCING == "area" else (["utci"] if scen else ["tmrt", "utci"])
        solweig.calculate(surface, weather, LOC, output_dir=tmp, outputs=outs)
        t2 = time.time()
        files = {v: sorted((tmp / v).glob("*.tif")) if (tmp / v).is_dir() else sorted(tmp.rglob(f"*{v}*.tif")) for v in outs}
        stack = {v: np.stack([rasterio.open(f).read(1)[r0:r1, c0:c1] for f in fs]) for v, fs in files.items()}
        names = [f.name.replace("tmrt", "utci") for f in files[outs[-1]]]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    while len(pending) >= 2:
        pending.pop(0).result()
    pending.append(ex.submit(finish, tid, t["core"], stack, names, np.array([w.datetime.hour for w in weather]), ks,
                             lc is not None, (t1 - t0, t2 - t1)))
for f in pending:
    f.result()
ex.shutdown()
