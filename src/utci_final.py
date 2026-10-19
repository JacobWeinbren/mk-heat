"""The final UTCI per 1 m cell and hour on 13 Aug 2026 (models_plan.md, steps B4 and R3; Jacob, 18 Oct 2026: "yes to all
go ahead"): SOLWEIG's mean radiant temperature as utci.py stored it, with local air and local wind in place of each tile's
one Met Office UKV value. Nothing is rerun: wind enters SOLWEIG only through UTCI (solweig grid_accumulator.py 187, 331),
so UTCI can be recomputed from the stored Tmrt.
- Tmrt: utci/<tile>.npz (tmrt, degC x 10). Scenario files keep none (see Scenarios below).
- Hours: only those the map shows, the tile's shade/<tile>.npz hours (shade.py: 06-19 UTC, the sun above 3 degrees;
  package.py reads UTCI at those hours only), are computed and stored.
- Timing: hour h is the interval ending at h (UTC). SOLWEIG puts the sun at h - 30 min (solweig 0.1.0b96
  models/weather.py 150-151: "timestamps typically represent the end of an interval") and SUEWS's values are means over
  the hour ending at h (suews_run.py: the mean of its 12 five-minute steps). UKV's 2 m and 10 m values from Open-Meteo
  are instants at h (Open-Meteo Sources/App/UKMO/UkmoVariable.swift, interpolation: temperature_2m,
  relative_humidity_2m and wind_speed_10m .hermite, as instants; shortwave .solar_backwards_averaged and precipitation
  .backwards_sum, the preceding hour's), and utci.py gave SOLWEIG the instant at h. So every UKV value taken here (the
  reference of --stats, the fallbacks, --air ukv, --wind ukv and the 10 m speed that scales URock's ratio) is the hour's,
  formed as SUEWS forms its own from the same hourly instants: supy interpolates Tair, RH and U linearly between them
  (supy 2026.6.5 _load.py: dict_var_type_forcing "inst", resample_linear_inst) and the mean of the n = 3600 / 300 steps
  ending in (h-1, h] is (n-1)/(2n) = 11/24 of the instant at h-1 plus (n+1)/(2n) = 13/24 of the instant at h. Humidity
  enters as the vapour pressure of the hour's temperature and relative humidity, as the SUEWS store's does (below). The
  wind direction, which picks URock's sector, stays the instant at h: urock_run.py chose the sectors to run from those
  instants (sectors.json). Only --check takes UKV's instants at h, as utci.py gave SOLWEIG, to test against the stored
  UTCI.
- Air temperature and humidity (--air suews, the default): SUEWS's 2 m fields on its 100 m grid (B3 writes them; the
  store is described below), interpolated bilinearly between the 100 m cell centres to each 1 m cell centre. Humidity is
  interpolated as vapour pressure, the quantity UTCI takes (UMEP's utci_calculator: Pa = es(Ta) x RH / 100, in kPa),
  since relative humidity does not mix linearly with temperature. Where a centre has no value (outside the grid SUEWS
  ran) the bilinear weights of the others are renormalised; a 1 m cell with no valid centre round it takes the tile's
  UKV values for the hour and is counted. Beyond the outermost centres the edge value holds.
  --air ukv: the tile's UKV 2 m temperature and humidity for the hour (today's map took the instants at h).
- Wind (--wind urock, the default): URock's 1.5 m wind (B1 writes it; below), as a ratio to its 10 m inflow, from the
  nearest 4 m cell that is not a building (the 1 m cell's own 4 m cell when that is open), for the sector holding the
  hour's UKV 10 m direction, times the hour's UKV 10 m speed (URock's field scales with its inflow; plan, Gate 2), raised
  to UTCI's 10 m reference by (10/1.5)^0.2 as UMEP's SpatialTC does (vendored postprocessor/spatialtc_algorithm.py, lines
  289 and 534), then held at no less than 0.5 m/s, the lowest 10 m wind of the grid the UTCI regression was fitted on
  (Broede et al. 2012, Int J Biometeorol 56: 481-494, electronic supplement: 0.5-30.3 m/s). The cell-hours so held are
  counted. A 4 m cell URock did not run (for that sector) takes the store's inflow ratio for the tile being computed and the
  hour's sector (URock's own undisturbed 1.5 m value; urock_run.py store), scaled and raised alike, so open ground has no
  step where the runs end; with no inflow ratio for the tile, the tile's UKV 10 m speed. Both are counted.
  --wind ukv: the tile's UKV 10 m speed for the hour, held at the same 0.5 m/s.
- UTCI: Broede's 6th-order polynomial as UMEP vendors it (vendor/UMEP-processing/functions/SOLWEIGpython/
  UTCI_calculations.py: utci_polynomial and utci_calculator; UMEP-processing 3.0.3, commit a7798db). Its 210
  coefficients and the vapour-pressure coefficients are read from that file, not copied, and the polynomial is evaluated
  in NumPy by nested Horner sums (air innermost, so a uniform air costs only scalar work).
  Acceptance (plan, "UTCI code"): with each tile's uniform UKV inputs it must give the stored UTCI (solweig's Rust
  utci_grid) to the stored 0.1 C on every cell-hour; --check runs that test and times one tile. On SP8539_mk2021 (18 Oct
  2026) it did: 92.8% of cell-hours equal, the rest 0.1 C apart, as solweig's own utci_grid on the stored Tmrt is (the
  stored Tmrt is rounded to 0.1 C; solweig took UTCI from the unrounded value); 7.1 s a tile in one process.

Writes utci_final/<tile>.npz (utci_final_NAME/ with --scenario), only what the map needs: hours (UTC, end of interval,
the map's) and utci (degC x 10, int16) on the core, as utci.py's files hold them; the sources used (air, wind, tmrt);
per hour the cells whose wind was held at 0.5 m/s (clamped), the cells with no URock value (no_urock; they take the
inflow ratio), of those the cells that took the tile's UKV wind (ukv_wind: no inflow ratio either) and the cells with
no SUEWS value (no_suews); and inputs: RULES below, the path, size and modification time (ns) of each input file (the
Tmrt file, the shade file, the SUEWS store, every URock store file) and a digest of the tile's UKV series. A tile is
skipped only when its file's inputs equal the current ones (and, with --stats, its statistics' too), so a rewritten
Tmrt, store or series is computed again. Size (19 Oct 2026, the 5 tiles in before_borough/utci_city): 3.9-8.3 MB a
tile, 0.27 of utci.py's file for the tile (SP8539_mk2021: 7.8 MB; with all 24 hours 11.0 MB), so about 2.2-2.6 GB for
376 tiles (0.27 x utci/'s mean file then, 21.5 MB, or the 5 tiles' mean, 6.9 MB).
--stats also computes, on the footpath and bus stop cells only, UTCI with the tile's UKV air and wind for the hour (ukv:
the reference for the effects, recomputed here so that the stored Tmrt's 0.1 C rounding is in every mode alike), with
the local air only (UKV wind), with the local wind only (UKV air), and takes the stored UTCI (today's map, from UKV's
instants at h: ukv minus stored is the timing change and the rounding) and the final one (both), and writes
utci_final/stats/<tile>.json: for each mode, per hour the mean and the numbers at 32 C and 38 C or more (strong
and very strong heat stress on the UTCI assessment scale; Broede et al. 2012), the number that reach 38 C in some hour,
each stop's values (degC x 10), per hour the footpath cell-hours whose wind was held at 0.5 m/s, and its inputs (the
file's, and the footpath and stop sources'). A tile computed again without --stats loses its old statistics file.
Scenarios: utci.py --scenario NAME keeps UTCI only, no Tmrt, so a scenario's final UTCI is not made here from files and
nothing here assumes a scenario Tmrt. R3 (plan: "Stops and 10% scenarios: SOLWEIG rerun with --hours 0-19, with the
final UTCI computed in the run") reruns SOLWEIG for each scenario tile and, inside that run, takes each hour's Tmrt as
SOLWEIG holds it and calls this module: ukv = Ukv(H), air = Suews(suews/<NAME>/air_2m.npz) (B3's scenario store),
wind = Urock(urock/ratio_4m) (the baseline's wind serves every scenario, plan); per tile w_air = air.weights(core) and
idx = wind.nearest(bounds, core); per hour ta, pa, va, _, _ = hour_inputs(tile, h, ukv, air, w_air, wind, idx, shape)
and utci(ta, pa, tmrt, va), written as utci.py writes UTCI. That UTCI is from the unrounded Tmrt, the baseline's here
from the stored 0.1 C one (on SP8539_mk2021 the rounding alone moves 7.2% of cell-hours by 0.1 C: --check).
--scenario NAME here reads utci_NAME/<tile>.npz only for a rerun that kept its Tmrt; a file without one is reported
and skipped.
Footpath and stop cells are those package.py counts: 1 m samples of today's OSM walking ways (its tags and exclusions),
off 2021 building cells or on a bridge's deck; the 3 x 3 m round each active NaPTAN on-street stop off building cells,
the stop's value each hour being its coolest cell; both in the area (area.py) and not in an area built since the survey
(new_build.py). Unlike package.py, cells are counted once each rather than by 25 m piece, and a stop's 3 x 3 m is taken
within its own tile.

The stores (B1 and B3 write these; this script reads them):
  SUEWS  data/mk/heat/suews/<scenario>/air_2m.npz  (scenario "base", or NAME with --scenario; --suews FILE overrides;
                                                    a run.json beside it must give SUEWS's step as TSTEP_S)
           hours      int (H,)          UTC hour on 13 Aug 2026 at the end of each hourly interval, as utci.py's
           ta         float32 (H,ny,nx) 2 m air temperature, degC, the mean over the hour, NaN where SUEWS did not run
           rh         float32 (H,ny,nx) 2 m relative humidity, %, the mean over the hour
           transform  float64 (6,)      the 100 m grid's affine (a, b, c, d, e, f), British National Grid (EPSG:27700),
                                        rasterio's Affine order: a cell's corner x = c + a col, y = f + e row (b = d = 0,
                                        e < 0)
  URock  data/mk/heat/urock/ratio_4m/  (urock_run.py store writes it; --urock DIR overrides; the baseline's wind serves
                                        every scenario, plan)
           grid.json        {"transform": [a, b, c, d, e, f] (EPSG:27700, as above), "shape": [ny, nx],
                             "sectors": [centre directions, degrees, equally spaced; a sector holds the directions from
                             its centre - half a spacing (included) to its centre + half a spacing],
                             "z": the output height, m (1.5), "ref_height": the inflow's reference height, m (10),
                             "inflow_ratio": optional, URock's undisturbed z m wind over its 10 m inflow: one number,
                             or {tile id: {"DDD": ratio for the sector centred on DDD}} (a tile not listed: UKV)}
           building.npy     bool (ny, nx), URock's building cells
           sector_DDD.npy   float16 (ny, nx), the z m horizontal wind over the 10 m inflow speed for the sector centred
                            on DDD degrees (the direction the wind comes from), NaN where URock did not run; no file
                            for a sector URock ran nowhere
The wind direction is each tile's UKV 10 m direction at h (weather_ukv/ukv_wind_direction_2026-08-12_14.json,
ukv_fetch.py), its speed and the air the tile's series that utci.py used (weather_ukv/ukv_2km_2026-08-12_14.json), for
the hour as above.

usage: <heat venv python> -B -I utci_final.py <repo root> [--air suews|ukv] [--wind urock|ukv] [--stats]
                                          [--scenario NAME] [--suews FILE] [--urock DIR] [--out DIR] [tile ids...]
       <heat venv python> -B -I utci_final.py <repo root> --check TILE  (the acceptance test and timing; writes nothing)
"""
import ast, csv, datetime as dt, hashlib, importlib.util, io, json, os, sys, time
from pathlib import Path
import numpy as np
from scipy import ndimage as ndi

HERE = Path(__file__).resolve().parent
UTCI_PY = HERE / "vendor" / "UMEP-processing" / "functions" / "SOLWEIGpython" / "UTCI_calculations.py"
CLAMP = 0.5          # m/s at 10 m, the bottom of the UTCI regression's fitted range (Broede et al. 2012, supplement)
BANDS = (32.0, 38.0)  # where strong and very strong heat stress begin on the UTCI scale (Broede et al. 2012), as package.py
DAY = "2026-08-13"   # the modelled day (utci.py)
TSTEP_S = 300        # s, SUEWS's step (suews_run.py: the London benchmark's tstep, run.json settings.tstep_s)
_N = 3600 // TSTEP_S
W_END = (_N + 1) / (2 * _N)   # the hour's mean of the n steps linear between the instants: the share of the one at h
# what a stored output was made under; a file made under other rules is computed again
RULES = {"ukv_hour": f"{1 - W_END:.6f} x instant at h-1 + {W_END:.6f} x instant at h; direction the instant at h",
         "hours": "the tile's shade.py hours"}


# ---------------------------------------------------------------- UTCI, from UMEP's file
VARS = ("D_Tmrt", "va", "Pa", "Ta")      # Horner nesting, outermost first


def _fn(tree, name):
    return next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)


def read_umep(path=UTCI_PY):
    """the polynomial {(powers of D_Tmrt, va, Pa, Ta): coefficient} and the vapour-pressure coefficients g, from UMEP"""
    tree = ast.parse(path.read_text())
    expr = next(n.value for n in ast.walk(_fn(tree, "utci_polynomial")) if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", None) == "UTCI_approx")
    split = lambda e, op: split(e.left, op) + split(e.right, op) if isinstance(e, ast.BinOp) and isinstance(e.op, op) else [e]
    coef = {}
    for term in split(expr, ast.Add):
        c, p = 1.0, [0] * len(VARS)
        for f in split(term, ast.Mult):
            if isinstance(f, ast.Name):
                p[VARS.index(f.id)] += 1
            else:
                c *= float(ast.literal_eval(f))
        coef[tuple(p)] = coef.get(tuple(p), 0.0) + c          # the leading bare Ta joins the Ta term
    deg = max(map(sum, coef))
    # every monomial of degree 6 or less in 4 variables, C(10, 4) = 210 (Broede et al. 2012)
    if deg != 6 or len(coef) != 210:
        raise ValueError(f"{path}: {len(coef)} terms of degree up to {deg}, not 210 of degree 6")
    g = next(n.value for n in ast.walk(_fn(tree, "utci_calculator")) if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", None) == "g")
    return coef, np.array(ast.literal_eval(g.args[0]), dtype=np.float64), deg


COEF, G, DEG = read_umep()


def _nest(prefix=()):
    if len(prefix) == len(VARS):
        return COEF.get(prefix, 0.0)
    return [_nest(prefix + (e,)) for e in range(DEG + 1 - sum(prefix))]


TREE = _nest()


def _horner(node, xs, level=0):
    """sum of node's terms; scalars stay scalars until an array enters, arrays are updated in place"""
    if level == len(xs):
        return node
    x, acc = xs[level], None
    for sub in reversed(node):
        v = _horner(sub, xs, level + 1)
        if acc is None:
            acc = v
        elif isinstance(acc, np.ndarray):
            acc *= x; acc += v
        else:
            acc = acc * x + v
    return acc


def vapour_kpa(ta, rh):
    """vapour pressure, kPa, from air temperature (degC) and relative humidity (%), as UMEP's utci_calculator"""
    tk = ta + 273.15
    es = G[7] * np.log(tk)
    for i in range(7):
        es = es + G[i] * tk ** (i + 1 - 3.0)
    return np.exp(es) * 0.01 * rh / 100.0 / 10.0


def utci(ta, pa, tmrt, va):
    """UTCI, degC: Broede's polynomial; ta (degC), pa (kPa) and va (10 m, m/s) scalars or arrays shaped as tmrt"""
    tmrt = np.asarray(tmrt, dtype=np.float64)
    f = lambda a: np.array(a, dtype=np.float64) if isinstance(a, np.ndarray) else float(a)
    out = _horner(TREE, (tmrt - f(ta), f(va), f(pa), f(ta)))
    return out if isinstance(out, np.ndarray) and out.shape == tmrt.shape else np.broadcast_to(out, tmrt.shape).copy()


# ---------------------------------------------------------------- inputs
class Ukv:
    """each tile's UKV 2 km series, as utci.py used them, and its 10 m wind direction"""
    def __init__(self, H):
        W = H / "weather_ukv"
        self.s = {p[0]: u["hourly"] for p, u in zip(json.load(open(W / "tile_points.json")), json.load(open(W / "ukv_2km_2026-08-12_14.json")))}
        f = W / "ukv_wind_direction_2026-08-12_14.json"
        self.d = json.load(open(f)) if f.exists() else {}

    def at(self, tid, hour, key="s"):
        """UKV's instants at hour (UTC, 13 Aug): (2 m temperature, relative humidity, 10 m speed), or the direction"""
        src = self.s[tid] if key == "s" else self.d[tid]
        k = src["time"].index(f"{DAY}T{hour:02d}:00")
        if key == "s":
            return src["temperature_2m"][k], src["relative_humidity_2m"][k], src["wind_speed_10m"][k]
        return src["wind_direction_10m"][k]

    def hour(self, tid, hour):
        """(2 m temperature, relative humidity, 10 m speed) for the hour ending at hour, as SUEWS forms its hour means
        from hourly instants (the docstring's Timing)"""
        src = self.s[tid]; k = src["time"].index(f"{DAY}T{hour:02d}:00")
        if k < 1 or dt.datetime.fromisoformat(src["time"][k]) - dt.datetime.fromisoformat(src["time"][k - 1]) != dt.timedelta(hours=1):
            raise ValueError(f"{tid}: no UKV instant an hour before {DAY} {hour:02d}:00")
        return tuple((1 - W_END) * src[v][k - 1] + W_END * src[v][k]
                     for v in ("temperature_2m", "relative_humidity_2m", "wind_speed_10m"))

    def digest(self, tid):
        """the tile's series as read here, so a refetched series counts as a changed input"""
        return hashlib.sha256(json.dumps([self.s[tid], self.d.get(tid)], sort_keys=True).encode()).hexdigest()[:16]


class Suews:
    """SUEWS's 2 m air on its 100 m grid (the store above), interpolated to a tile's 1 m cell centres"""
    def __init__(self, f):
        z = np.load(f); self.name = str(f)
        self.hours = [int(h) for h in z["hours"]]; self.tr = [float(v) for v in z["transform"]]
        self.ta = z["ta"].astype(np.float64); self.pa = vapour_kpa(self.ta, z["rh"].astype(np.float64))
        if self.tr[1] or self.tr[3] or self.tr[4] >= 0 or min(self.ta.shape[1:]) < 2:
            raise ValueError(f"{f}: a north-up grid of at least 2 x 2 cells is needed")
        run = Path(f).parent / "run.json"            # suews_run.py's settings: the hour means' step must be TSTEP_S
        if run.exists() and json.load(open(run))["settings"].get("tstep_s", TSTEP_S) != TSTEP_S:
            raise ValueError(f"{f}: SUEWS's step is not {TSTEP_S} s, the step the UKV hour means here are formed with")

    def weights(self, core):
        a, _, c, _, e, f = self.tr; cx0, cy0, cx1, cy1 = core; ny, nx = self.ta.shape[1:]
        def axis(fi, n):
            fi = np.clip(fi, 0, n - 1)                     # beyond the outermost centres the edge value holds
            i0 = np.minimum(np.floor(fi).astype(int), n - 2)
            return i0, fi - i0
        cols = axis((cx0 + np.arange(cx1 - cx0) + 0.5 - c) / a - 0.5, nx)
        rows = axis((cy1 - np.arange(cy1 - cy0) - 0.5 - f) / e - 0.5, ny)
        return rows, cols

    def at(self, hour, w):
        """(ta, pa) on the core, NaN where no centre round a cell has a value"""
        if hour not in self.hours:
            raise ValueError(f"{self.name} has no hour {hour} (UTC, end of interval)")
        k = self.hours.index(hour); (r0, wr), (c0, wc) = w; out = []
        for fld in (self.ta[k], self.pa[k]):
            s = np.zeros((len(r0), len(c0))); ws = np.zeros_like(s)
            for dr, wR in ((0, 1 - wr), (1, wr)):
                for dc, wC in ((0, 1 - wc), (1, wc)):
                    v = fld[np.ix_(r0 + dr, c0 + dc)]; ww = wR[:, None] * wC[None, :] * np.isfinite(v)
                    s += np.where(np.isfinite(v), v, 0) * ww; ws += ww
            out.append(np.divide(s, ws, out=np.full_like(s, np.nan), where=ws > 0))
        return out


class Urock:
    """URock's 1.5 m wind ratios at 4 m (the store above)"""
    def __init__(self, d):
        g = json.load(open(d / "grid.json")); self.name = str(d)
        self.tr = [float(v) for v in g["transform"]]; self.shape = tuple(g["shape"])
        self.z, self.ref = float(g["z"]), float(g["ref_height"]); self.inflow = g.get("inflow_ratio")
        self.sectors = sorted(float(s) for s in g["sectors"])
        self.step = 360.0 / len(self.sectors)
        if not np.allclose(np.diff(self.sectors + [self.sectors[0] + 360]), self.step):
            raise ValueError(f"{d}: the sectors are not equally spaced")
        if self.ref != 10.0:
            raise ValueError(f"{d}: the ratio must be to the 10 m inflow, UKV's height")
        self.bld = np.load(d / "building.npy", mmap_mode="r")
        name = lambda s: f"{round(s) % 360:03d}"
        self.ratio = {s: np.load(d / f"sector_{name(s)}.npy", mmap_mode="r") if (d / f"sector_{name(s)}.npy").exists() else None
                      for s in self.sectors}         # None: URock ran this sector nowhere
        self.name_of = name
        self.lift = (10.0 / self.z) ** 0.2         # SpatialTC: WsUTCI = (10 / sensorheight) ** 0.2 * ws

    def inflow_for(self, tid, s):
        """the inflow ratio for the tile and the sector centred on s; None: none (the tile's UKV speed)"""
        if isinstance(self.inflow, dict):
            return self.inflow.get(tid, {}).get(self.name_of(s))
        return self.inflow

    def sector(self, deg):
        return self.sectors[int(((deg - self.sectors[0] + self.step / 2) % 360) // self.step)]

    def nearest(self, bounds, core):
        """for each 1 m core cell, the store's (row, col) of the nearest 4 m cell that is not a building, the search
        running over the tile's crop (pool.json bounds) at 1 m; -1 where that cell lies off the store"""
        a, _, c, _, e, f = self.tr; x0, y0, x1, y1 = bounds; cx0, cy0, cx1, cy1 = core
        col = np.floor((x0 + np.arange(x1 - x0) + 0.5 - c) / a).astype(int)
        row = np.floor((y1 - np.arange(y1 - y0) - 0.5 - f) / e).astype(int)
        okc, okr = (col >= 0) & (col < self.shape[1]), (row >= 0) & (row < self.shape[0])
        b = np.asarray(self.bld[np.ix_(np.where(okr, row, 0), np.where(okc, col, 0))]) & okr[:, None] & okc[None, :]
        if b.all():
            raise ValueError("every cell of the crop is a building in URock's grid")
        ir, ic = ndi.distance_transform_edt(b, return_distances=False, return_indices=True)
        sl = (slice(int(y1 - cy1), int(y1 - cy0)), slice(int(cx0 - x0), int(cx1 - x0)))
        rr, cc = ir[sl], ic[sl]
        off = ~(okr[rr] & okc[cc])
        return np.where(off, -1, row[rr]), np.where(off, -1, col[cc])

    def at(self, hour_dir, u10, idx, tid):
        """the 10 m wind for UTCI on tile tid's core, the cells with no URock value and those of them on UKV's speed"""
        rr, cc = idx; r = np.full(rr.shape, np.nan, np.float64); on = rr >= 0
        s = self.sector(hour_dir); R = self.ratio[s]
        if R is not None:
            r[on] = R[rr[on], cc[on]]
        miss = ~np.isfinite(r)
        inflow = self.inflow_for(tid, s)
        if inflow is not None:
            r[miss] = float(inflow)                   # URock's undisturbed profile, as on its own open ground
        va = r * u10 * self.lift
        if inflow is None:
            va[miss] = u10                            # the tile's UKV 10 m speed, as today
        return va, miss, (miss if inflow is None else np.zeros(miss.shape, bool))


# ---------------------------------------------------------------- footpaths and stops (as package.py counts them)
def people_cells(H, tiles, pool):
    """{tile: (footpath cells as flat indices, [(ATCO code, flat indices of the stop's open cells)])}"""
    import rasterio.features, rasterio.transform
    from pyproj import Transformer
    from shapely.geometry import Point
    from shapely.prepared import prep
    sys.path.insert(0, str(HERE))
    from area import area
    bua = area(H); bua_p = prep(bua)
    to_bng = Transformer.from_crs(4326, 27700, always_xy=True).transform
    grey = dict(np.load(H / "layers" / "newbuild_mask.npz")) if (H / "layers" / "newbuild_mask.npz").exists() else {}
    WALK = {"footway", "pedestrian", "path", "steps", "cycleway", "living_street", "bridleway"}      # package.py's
    px, py, pb = [], [], []
    for w in json.load(open(H / "osm" / "walk_now.json"))["elements"]:
        tg = w.get("tags", {})
        if w["type"] != "way" or tg.get("highway") not in WALK or tg.get("indoor", "no") != "no":
            continue
        if tg.get("covered") == "yes" or tg.get("tunnel", "no") != "no" or tg.get("location") == "underground" \
                or (tg.get("layer", "0").lstrip("-").isdigit() and int(tg.get("layer", "0")) < 0):
            continue                                   # under cover: no modelled value on the page
        ex, ny = to_bng(np.array([p["lon"] for p in w["geometry"]]), np.array([p["lat"] for p in w["geometry"]]))
        d = np.concatenate([[0], np.cumsum(np.hypot(np.diff(ex), np.diff(ny)))])
        if d[-1] < 1:
            continue
        s = np.r_[np.arange(0, d[-1], 1.0), d[-1]]     # every metre, as package.py samples a way
        px.append(np.interp(s, d, ex)); py.append(np.interp(s, d, ny)); pb.append(np.full(len(s), tg.get("bridge", "no") != "no"))
    px, py, pb = np.concatenate(px), np.concatenate(py), np.concatenate(pb)
    nap = []
    for row in csv.DictReader(open(H / "naptan" / "naptan_049.csv")):
        if row["StopType"] == "BCT" and row["Status"] == "active":
            try:
                nap.append((row["ATCOCode"], float(row["Easting"]), float(row["Northing"])))
            except ValueError:
                pass
    out = {}
    for t in tiles:
        cx0, cy0, cx1, cy1 = pool[t]["core"]; shp = (int(cy1 - cy0), int(cx1 - cx0))
        bld = np.load(H / "shade" / f"{t}.npz")["bld"].astype(bool)
        inb = rasterio.features.rasterize([(bua, 1)], out_shape=shp, transform=rasterio.transform.from_origin(cx0, cy1, 1, 1), fill=0, dtype="uint8").astype(bool)
        ok = inb & ~grey.get(t, np.zeros(shp, bool))
        m = (px >= cx0) & (px < cx1) & (py >= cy0) & (py < cy1)
        r, c = (cy1 - 1 - py[m]).astype(int), (px[m] - cx0).astype(int)        # package.py's sample()
        keep = ok[r, c] & (pb[m] | ~bld[r, c])
        paths = np.unique(r[keep] * shp[1] + c[keep])
        stops = []
        for atco, e, n in nap:
            if not (cx0 <= e < cx1 and cy0 <= n < cy1) or not bua_p.contains(Point(e, n)):
                continue
            rs, cs = (cy1 - 1 - (n + np.tile([-1, 0, 1], 3))).astype(int), (e + np.repeat([-1, 0, 1], 3) - cx0).astype(int)
            inside = (rs >= 0) & (rs < shp[0]) & (cs >= 0) & (cs < shp[1])
            rs, cs = rs[inside], cs[inside]
            kk = ~bld[rs, cs]
            if kk.any() and grey.get(t, np.zeros(shp, bool))[rs[kk], cs[kk]].mean() <= 0.5:     # package.py: grey when most are
                stops.append((atco, rs[kk] * shp[1] + cs[kk]))
        out[t] = (paths, stops)
    return out


def summarise(vals_paths, vals_stops):
    """vals_*: per hour arrays of UTCI (degC, 0.1 steps); the per-hour and per-day counts the page reads"""
    P = np.stack(vals_paths); S = np.stack([np.array([v.min() for v in h]) if len(h) else np.zeros(0) for h in vals_stops])
    f = lambda A: {"n": int(A.shape[1]), "mean": [round(float(a.mean()), 3) if a.size else None for a in A],
                   **{f"n_ge_{int(b)}": [int((a >= b).sum()) for a in A] for b in BANDS},
                   f"n_ge_{int(BANDS[1])}_some_hour": int((A >= BANDS[1]).any(axis=0).sum())}
    return f(P), f(S), S


# ---------------------------------------------------------------- one tile
def hour_inputs(tid, h, ukv, air, w_air, wind, idx, shape, when="hour", as_arrays=False):
    """for the hour ending at h on tile tid's core: air temperature (C), vapour pressure (kPa) and 10 m wind (m/s, held
    at CLAMP) as UTCI takes them; the tile's UKV reference (ta, pa, va held alike); and the cells counted (clamped,
    no_urock, ukv_wind, no_suews). w_air = air.weights(core), idx = wind.nearest(bounds, core). when "instant": UKV's
    values at h, as utci.py gave SOLWEIG (--check only). R3 calls this inside a scenario's SOLWEIG run (docstring)."""
    ta_u, rh_u, u10 = ukv.hour(tid, h) if when == "hour" else ukv.at(tid, h)
    pa_u = float(vapour_kpa(ta_u, rh_u))
    if air is not None:
        ta, pa = air.at(h, w_air); ns = ~np.isfinite(ta)
        ta[ns] = ta_u; pa[ns] = pa_u
    else:
        ta, pa, ns = ta_u, pa_u, np.zeros(shape, bool)
        if as_arrays:
            ta, pa = np.full(shape, ta_u), np.full(shape, pa_u)
    if wind is not None:
        va, nu, uw = wind.at(ukv.at(tid, h, "d"), u10, idx, tid)      # the sector from the direction at h (docstring)
    else:
        va, nu = (np.full(shape, float(u10)) if as_arrays else float(u10)), np.zeros(shape, bool); uw = nu
    cl = np.broadcast_to(np.asarray(va) < CLAMP, shape)
    return ta, pa, np.maximum(va, CLAMP), (ta_u, pa_u, max(float(u10), CLAMP)), \
        {"clamped": cl, "no_urock": nu, "ukv_wind": uw, "no_suews": ns}


def run_tile(tid, H, pool, ukv, air, wind, tmrt_file, cells=None, as_arrays=False, keep=None, when="hour"):
    """the final UTCI (degC x 10, int16) at the file's hours in keep (None: all), the per-hour counts and, with cells,
    the statistics"""
    t0 = time.time()
    z = np.load(tmrt_file); hours_all = [int(h) for h in z["hours"]]
    ks = [k for k, h in enumerate(hours_all) if keep is None or h in keep]; hours = [hours_all[k] for k in ks]
    tm = z["tmrt"]
    stored = z["utci"] if (cells is not None and "utci" in z.files) else None
    core, bounds = pool[tid]["core"], pool[tid]["bounds"]
    w_air = air.weights(core) if air is not None else None
    idx = wind.nearest(bounds, core) if wind is not None else None
    t1 = time.time()
    shape = tm.shape[1:]
    out = np.empty((len(ks),) + shape, np.int16); cnt = {k: [] for k in ("clamped", "no_urock", "ukv_wind", "no_suews")}
    sel = None
    if cells is not None:
        paths, stops = cells
        sel = np.unique(np.concatenate([paths] + [s for _, s in stops])) if len(paths) or stops else np.zeros(0, int)
        pos = lambda ix: np.searchsorted(sel, ix)
        modes = {m: ([], []) for m in ("stored", "ukv", "air", "wind", "both")}; clamped_paths = []
    for i, (k, h) in enumerate(zip(ks, hours)):
        T = tm[k].astype(np.float64) / 10
        ta, pa, va, (ta_u, pa_u, va_u), m = hour_inputs(tid, h, ukv, air, w_air, wind, idx, shape, when, as_arrays)
        both = utci(ta, pa, T, va)
        out[i] = np.round(both * 10).astype(np.int16)
        for key, v in m.items():
            cnt[key].append(int(v.sum()))
        if sel is not None:
            fl = lambda a: a.ravel()[sel] if isinstance(a, np.ndarray) else a
            Ts = T.ravel()[sel]
            vals = {"stored": stored[k].ravel()[sel] / 10 if stored is not None else np.full(len(sel), np.nan),
                    "ukv": np.round(utci(ta_u, pa_u, Ts, va_u) * 10) / 10,
                    "air": np.round(utci(fl(ta), fl(pa), Ts, va_u) * 10) / 10,
                    "wind": np.round(utci(ta_u, pa_u, Ts, fl(va)) * 10) / 10,
                    "both": out[i].ravel()[sel] / 10}
            for md, v in vals.items():
                modes[md][0].append(v[pos(paths)]); modes[md][1].append([v[pos(s)] for _, s in stops])
            clamped_paths.append(int(m["clamped"].ravel()[paths].sum()))
    t2 = time.time()
    stats = None
    if sel is not None:
        stats = {"tile": tid, "hours": hours, "clamp_ms": CLAMP, "ukv": when, "paths": {},
                 "stops": {"atco": [a for a, _ in stops]}, "paths_clamped_cell_hours": clamped_paths}
        for md, (vp, vs) in modes.items():
            p, s, S = summarise(vp, vs)
            stats["paths"][md] = p; stats["stops"][md] = {**s, "values": [[int(round(x * 10)) for x in S[:, j]] for j in range(S.shape[1])]}
    return hours, out, cnt, stats, (t1 - t0, t2 - t1)


# ---------------------------------------------------------------- the acceptance test
def check(ROOT, tid):
    """the plan's acceptance test on one tile with today's uniform inputs, and its timing; writes nothing"""
    os.environ.setdefault("SOLWEIG_NO_GPU", "1")
    from solweig.rustalgos import utci as rust
    H = ROOT / "data" / "mk" / "heat"; pool = {t["id"]: t for t in json.load(open(H / "rounds" / "pool.json"))["tiles"]}
    ukv = Ukv(H); f = H / "utci" / f"{tid}.npz"
    spec = importlib.util.spec_from_file_location("umep_utci", UTCI_PY); umep = importlib.util.module_from_spec(spec); spec.loader.exec_module(umep)
    z = np.load(f); hours = [int(h) for h in z["hours"]]; tm, su = z["tmrt"], z["utci"]
    # 1. the port against UMEP's own scalar code, on every distinct (hour, Tmrt) of the tile
    d1 = d2 = 0.0; n1 = 0; rs = {}; rr = np.empty_like(su)
    for k, h in enumerate(hours):
        ta, rh, ws = ukv.at(tid, h); T = np.unique(tm[k]) / 10
        mine = utci(ta, vapour_kpa(ta, rh), T, ws)
        ref = np.array([umep.utci_calculator(ta, rh, x, ws) for x in T])
        d1 = max(d1, float(np.abs(mine - ref).max())); n1 += len(T)
        # 2. against solweig's Rust utci_grid on the same Tmrt (float32, as solweig passes it)
        Tg = (tm[k] / 10).astype(np.float32)
        r = np.asarray(rust.utci_grid(float(ta), float(rh), Tg, np.full_like(Tg, ws)))
        d2 = max(d2, float(np.abs(utci(ta, vapour_kpa(ta, rh), Tg, ws) - r).max()))
        # solweig's own code on the stored (0.1 C) Tmrt against its stored UTCI: what the rounding of Tmrt alone does
        rr[k] = np.round(r * 10).astype(np.int16)
        for v, c in zip(*np.unique(rr[k].astype(np.int32) - su[k], return_counts=True)):
            rs[int(v)] = rs.get(int(v), 0) + int(c)
    print(f"port vs UMEP utci_calculator: {n1} distinct (hour, Tmrt) inputs, max |diff| {d1:.2e} C")
    print(f"port vs solweig Rust utci_grid on the stored Tmrt: max |diff| {d2:.2e} C")
    print("solweig Rust utci_grid on the stored Tmrt vs stored UTCI, tenths of a degree: " + ", ".join(f"{v:+d}: {c}" for v, c in sorted(rs.items())))
    # 3. the production path, uniform UKV air and wind given as full arrays (the work SUEWS and URock fields will cost),
    # UKV's instants at h as utci.py gave SOLWEIG, against the stored UTCI; then timed with the statistics on, as R3's
    # baseline step runs (over all the file's hours; a production run computes the map's only)
    cells = people_cells(H, [tid], pool)[tid]
    t0 = time.time()
    _, out, cnt, stats, (tl, tc) = run_tile(tid, H, pool, ukv, None, None, f, cells=cells, as_arrays=True, when="instant")
    t1 = time.time(); buf = io.BytesIO()
    np.savez_compressed(buf, hours=np.array(hours), utci=out); t2 = time.time()
    _, out_s, _, _, _ = run_tile(tid, H, pool, ukv, None, None, f, when="instant")
    diff = out.astype(np.int32) - su
    vals, cnts = np.unique(diff, return_counts=True)
    print(f"final (uniform UKV inputs) vs stored UTCI, tenths of a degree: " + ", ".join(f"{v:+d}: {c}" for v, c in zip(vals, cnts)))
    worst = np.unravel_index(np.abs(diff).argmax(), diff.shape)
    print(f"max |diff| {np.abs(diff).max() / 10:.1f} C at hour {hours[worst[0]]}, cell {worst[1:]} (stored {su[worst] / 10}, Tmrt {tm[worst] / 10})")
    print(f"final vs solweig Rust utci_grid on the same stored Tmrt, rounded alike: {int((out != rr).sum())} of {out.size} cell-hours differ, max {int(np.abs(out.astype(np.int32) - rr).max())} tenth(s)")
    print(f"scalar-air path equals the array path: {np.array_equal(out, out_s)}; clamped cell-hours {sum(cnt['clamped'])}")
    print(f"footpath cells {stats['paths']['both']['n']}, stops {stats['stops']['both']['n']}; footpath cell-hours held at "
          f"{CLAMP} m/s: {sum(stats['paths_clamped_cell_hours'])}")
    print(f"time, one process: load and set-up {tl:.1f} s, UTCI x {len(hours)} hours with statistics {tc:.1f} s, "
          f"compressed write {t2 - t1:.1f} s ({len(buf.getvalue()) / 1e6:.1f} MB); tile {t2 - t0:.1f} s")
    ok = np.abs(diff).max() <= 1
    print("ACCEPTED" if ok else "NOT ACCEPTED")
    return ok


# ---------------------------------------------------------------- main
def main(args):
    ROOT = Path(args.pop(0)); H = ROOT / "data" / "mk" / "heat"
    opt = lambda k, d=None: (args.pop(args.index(k) + 1), args.remove(k))[0] if k in args else d
    if "--check" in args:
        sys.exit(0 if check(ROOT, opt("--check")) else 1)
    stats = "--stats" in args; args = [a for a in args if a != "--stats"]
    scen = opt("--scenario"); air_src = opt("--air", "suews"); wind_src = opt("--wind", "urock")
    sfile = Path(opt("--suews", H / "suews" / (scen or "base") / "air_2m.npz"))
    udir = Path(opt("--urock", H / "urock" / "ratio_4m"))
    OUT = Path(opt("--out", H / ("utci_final" if not scen else f"utci_final_{scen}")))
    TM = H / ("utci" if not scen else f"utci_{scen}")
    if air_src not in ("suews", "ukv") or wind_src not in ("urock", "ukv"):
        sys.exit("--air suews|ukv, --wind urock|ukv")
    if air_src == "suews" and not sfile.exists():
        sys.exit(f"no SUEWS store at {sfile} (B3); give --air ukv to use each tile's UKV air")
    if wind_src == "urock" and not (udir / "grid.json").exists():
        sys.exit(f"no URock store at {udir} (B1); give --wind ukv to use each tile's UKV wind")
    air = Suews(sfile) if air_src == "suews" else None
    wind = Urock(udir) if wind_src == "urock" else None
    rel = lambda p: os.path.relpath(p, ROOT)
    def stamp(p):
        """an input as its path, size and modification time (ns; stat follows links): a rewritten file reads as changed"""
        s = Path(p).stat()
        return [rel(p), s.st_size, s.st_mtime_ns]
    src = {"air": f"suews:{rel(sfile)}" if air else "ukv_2km", "wind": f"urock:{rel(udir)}" if wind else "ukv_2km"}
    stores = {"air": stamp(sfile) if air else "ukv_2km",
              "wind": [stamp(p) for p in [udir / "grid.json", udir / "building.npy"] + sorted(udir.glob("sector_*.npy"))]
              if wind else "ukv_2km"}
    pool = {t["id"]: t for t in json.load(open(H / "rounds" / "pool.json"))["tiles"]}
    ukv = Ukv(H)
    if stats:                                     # the footpath and stop cells' sources (people_cells, area.py)
        grey = H / "layers" / "newbuild_mask.npz"
        ext = H.parent / "extent" / ("bua22_mk_area_27700.geojson" if os.environ.get("HEAT_AREA") == "bua22" else "lad24_milton_keynes_27700.geojson")
        cell_in = {"walk": stamp(H / "osm" / "walk_now.json"), "naptan": stamp(H / "naptan" / "naptan_049.csv"),
                   "newbuild": stamp(grey) if grey.exists() else "none", "area": stamp(ext)}
    ids = args or sorted(p.stem for p in TM.glob("*.npz"))
    todo = {}
    for t in ids:
        f = TM / f"{t}.npz"; sf = H / "shade" / f"{t}.npz"
        if not f.exists():
            continue
        with np.load(f) as z:
            if "tmrt" not in z.files:
                print(f"{t}: {rel(f)} holds no Tmrt (a scenario run of utci.py keeps UTCI only; see Scenarios): skipped", flush=True); continue
        if not sf.exists():
            print(f"{t}: no {rel(sf)}, so no hours the map shows: skipped", flush=True); continue
        inputs = {"rules": RULES, **stores, "tmrt": stamp(f), "shade": stamp(sf), "ukv": ukv.digest(t)}
        o, so = OUT / f"{t}.npz", OUT / "stats" / f"{t}.json"
        if o.exists():
            with np.load(o) as z:
                same = "inputs" in z.files and json.loads(str(z["inputs"])) == inputs
            if same and stats:
                same = so.exists() and json.load(open(so)).get("inputs") == {**inputs, **cell_in}
            if same:
                continue
        todo[t] = inputs
    OUT.mkdir(parents=True, exist_ok=True)
    if stats:
        (OUT / "stats").mkdir(exist_ok=True)
    cells = people_cells(H, list(todo), pool) if stats and todo else {}
    for t, inputs in todo.items():
        f = TM / f"{t}.npz"; t0 = time.time()
        with np.load(H / "shade" / f"{t}.npz") as z:
            keep = [int(h) for h in z["hours"]]
        hours, out, cnt, st, _ = run_tile(t, H, pool, ukv, air, wind, f, cells=cells.get(t), keep=keep)
        tmp = OUT / f"{t}.tmp.npz"
        np.savez_compressed(tmp, hours=np.array(hours), utci=out, tmrt=rel(f), clamp_ms=CLAMP, inputs=json.dumps(inputs),
                            **src, **{k: np.array(v, np.int64) for k, v in cnt.items()})
        tmp.replace(OUT / f"{t}.npz")
        so = OUT / "stats" / f"{t}.json"
        if st is not None:
            st["sources"] = {**src, "tmrt": rel(f)}; st["inputs"] = {**inputs, **cell_in}
            with open(so.with_suffix(".tmp"), "w") as fh:
                json.dump(st, fh)
            so.with_suffix(".tmp").replace(so)
        else:
            so.unlink(missing_ok=True)                # statistics of an earlier computation of the tile
        print(f"{t}: {time.time() - t0:.1f} s, utci {out.min() / 10:.1f}..{out.max() / 10:.1f}, held at {CLAMP} m/s "
              f"{sum(cnt['clamped'])} cell-hours, no URock {sum(cnt['no_urock'])} (of them UKV wind {sum(cnt['ukv_wind'])}), "
              f"no SUEWS {sum(cnt['no_suews'])}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
