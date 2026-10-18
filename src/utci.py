"""Mean radiant temperature (Tmrt) and UTCI per hour on 13 Aug 2026 for each Milton Keynes crop, with SOLWEIG
(the solweig package, UMEP: Lindberg et al. 2008; vegetation as Lindberg & Grimmond 2011) at its published defaults:
anisotropic sky, trunk zone 0.25 x canopy height, objects under 1 m flattened, a standing person, leaf-on in August.
Surfaces from surfaces.py (v1 classes on the 2021 survey). Forcing (Jacob, 18 Oct 2026: "use the highest
resolution, most accurate, reliable data"): the Met Office UKV model at 2 km, hourly, for each tile's own grid cell
(the cell nearest its centre; 35 cells over the 105 tiles), from Open-Meteo's Historical Forecast API
(weather_ukv/, Met Office data CC BY-SA 4.0): air temperature, humidity, 10 m wind, surface pressure, global, direct
normal and diffuse radiation (diffuse = global - direct); solweig takes each value as the hour ending at its time
stamp. Checked against Cranfield airport's reported 35 C maximum (about 10 km away).
The whole day 00-23 UTC is run so the ground and wall temperatures build up through the morning.
Land cover (landcover.py: paved, building, grass, water) sets each cell's albedo, emissivity and ground heating when
its file is there; without it solweig treats all ground as cobblestone.
Bus shelters (shelters.py existing) are added to the canopy in every run.
Saves utci/<tile>.npz: hours (UTC, end of interval), tmrt and utci (degC x 10, int16) on the core, one layer an hour.

usage: <heat venv python> -I utci.py <repo root> [--gpu] [--hours a-b] [--scenario NAME] [tile ids...]
--scenario trees adds layers/trees_cdsm/<tile>.npy (treeplant.py's new trees, height above ground) to the canopy and
writes utci_trees/ instead of utci/, for the tiles a new tree reaches that have a baseline (the others are unchanged).
"""
import datetime as dt, json, shutil, sys, tempfile, time
from pathlib import Path
import numpy as np
import rasterio
import solweig

args = sys.argv[1:]; ROOT = Path(args.pop(0))
gpu = "--gpu" in args; args = [a for a in args if a != "--gpu"]
hrs = range(0, 24)
scen = None
if "--scenario" in args:
    i = args.index("--scenario"); scen = args[i + 1]; del args[i:i + 2]
if "--hours" in args:
    i = args.index("--hours"); a, b = map(int, args[i + 1].split("-")); hrs = range(a, b + 1); del args[i:i + 2]
H = ROOT / "data" / "mk" / "heat"; SURF = H / "surfaces"; OUT = H / ("utci" if not scen else f"utci_{scen}"); OUT.mkdir(parents=True, exist_ok=True)
pool = {t["id"]: t for t in json.load(open(H / "rounds" / "pool.json"))["tiles"]}
ids = args or sorted(pool)
if not gpu:
    solweig.disable_gpu()
LOC = solweig.Location(latitude=52.04, longitude=-0.76, altitude=110.0, utc_offset=0)
UKV = H / "weather_ukv"
series = {p[0]: u["hourly"] for p, u in zip(json.load(open(UKV / "tile_points.json")), json.load(open(UKV / "ukv_2km_2026-08-12_14.json")))}


def weather_for(tid):
    wx, out = series[tid], []
    for k, t in enumerate(wx["time"]):
        d = dt.datetime.fromisoformat(t)
        if d.date() == dt.date(2026, 8, 13) and d.hour in hrs:
            out.append(solweig.Weather(datetime=d, ta=wx["temperature_2m"][k], rh=wx["relative_humidity_2m"][k],
                                       global_rad=wx["shortwave_radiation"][k], ws=wx["wind_speed_10m"][k],
                                       pressure=wx["surface_pressure"][k],
                                       measured_direct_rad=wx["direct_normal_irradiance"][k],
                                       measured_diffuse_rad=wx["diffuse_radiation"][k]))
    return out
for tid in ids:
    if not (SURF / f"{tid}_dsm.tif").exists() or (OUT / f"{tid}.npz").exists():
        continue
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
    weather = weather_for(tid)
    t0 = time.time()
    lcf = SURF / f"{tid}_lc.tif"
    lc = rasterio.open(lcf).read(1).astype(np.int32) if lcf.exists() else None
    surface = solweig.SurfaceData.prepare(dsm=dsm, dem=dem, cdsm=cdsm, land_cover=lc, pixel_size=1.0, cdsm_relative=True)
    t1 = time.time()
    tmp = Path(tempfile.mkdtemp(dir=H))
    try:
        solweig.calculate(surface, weather, LOC, output_dir=tmp, outputs=["tmrt", "utci"])
        t2 = time.time()
        files = {v: sorted((tmp / v).glob("*.tif")) if (tmp / v).is_dir() else sorted(tmp.rglob(f"*{v}*.tif")) for v in ("tmrt", "utci")}
        stack = {v: np.stack([rasterio.open(f).read(1)[r0:r1, c0:c1] for f in fs]) for v, fs in files.items()}
        np.savez_compressed(OUT / f"{tid}.npz", hours=np.array([w.datetime.hour for w in weather]),
                            **{v: np.round(a * 10).astype(np.int16) for v, a in stack.items()},
                            files=np.array([f.name for f in files["utci"]]), land_cover=lc is not None, forcing="ukv_2km")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"{tid}: prepare {t1 - t0:.0f} s, {len(weather)} hours {t2 - t1:.0f} s, utci {np.nanmin(stack['utci']):.1f}..{np.nanmax(stack['utci']):.1f}", flush=True)
