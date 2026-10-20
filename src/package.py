"""The map's files from the per-tile results, clipped to the area (area.py: the City of Milton Keynes):
web/out/data.json, web/out/ground/<hour>.png and web/out/basemap.pmtiles (a copy).
Metric: UTCI (degC) where utci.py has run for every tile, else the sunlit share from shade.py.
- Open ground: the metric per hour over the 1 m cells that are not 2021 building, shown at 2 m by taking one 1 m cell
  of each 2 x 2 block (no averaging, so the map shows the same classes the chart counts; Jacob, 18 Oct 2026), coloured
  by class and reprojected (nearest) to Web Mercator. Drawn over all the modelled tiles; the figures count only the
  area.
- Footpaths: today's OpenStreetMap walking ways (Overpass, 18 Oct 2026), minus road centrelines (a carriageway is not a
  pavement). Jacob left the time question to me (18 Oct 2026); OSM of 17 Jan 2021 held 1,243 km of these ways and today's
  1,499 km, most of the gain being paths that existed in 2021 and were mapped later, so today's network is used, and
  the time gap is handled where the ground changed: a piece in an area built since the survey (new_build.py) is drawn
  grey and left out of the figures, and a piece lying mostly on 2021 building cells (a demolished building, a covered
  walkway or a misplaced line) is left out: each way is drawn and modelled only along its runs out of doors in 2021
  (off building cells, or on a bridge's deck), cut into pieces of at most 25 m, each the mean of its 1 m samples. Ways
  tagged indoor (the shopping centre's malls) are left out. A way on a bridge takes the deck's own cells (it is on top of them). A way in a tunnel or
  underpass, below ground level or covered (but not indoors) is drawn as "under cover" with no modelled value and left
  out of the figures (the lidar cannot see under a deck or roof).
- Bus stops: NaPTAN on-street stops (BCT) in use today, each the coolest of the 3 x 3 m around the stop each hour, off building
  cells. The time gap is handled as for footpaths (Jacob left it to me, 18 Oct 2026, after first asking to drop the
  81 stops created since the survey): a stop added since on a road that was already there is modelled, since the
  2021 surfaces still describe its surroundings; a stop in an area built since the survey is drawn grey.
- Greyed: new_build.py's areas built since the survey; a piece is grey when most of its samples are.
Class limits are the UTCI assessment scale's (Broede et al. 2012; Jendritzky et al. 2012).
usage: <heat venv python> -I package.py <repo root> [area name, default "Milton Keynes"]
"""
import csv, gzip, io, json, math, shutil, sys
import shapely
from pathlib import Path
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import calculate_default_transform, reproject, Resampling
from PIL import Image
from pyproj import Transformer
from shapely.geometry import shape, mapping, Point, LineString
from shapely.ops import transform as stransform, unary_union
from shapely.prepared import prep
from pmtiles.reader import Reader, MmapSource
import mapbox_vector_tile as mvt

ROOT = Path(sys.argv[1]); H = ROOT / "data" / "mk" / "heat"
# --scenario NAME: a second pass over utci_<NAME>/ (utci.py --scenario; the baseline where a tile has none) that adds the
# scenario's values, figures and images to the data.json the first pass wrote (Jacob, 18 Oct 2026: "on the switch it
# could be modelling an alternative Thursday")
SCEN = None
if "--scenario" in sys.argv:
    _i = sys.argv.index("--scenario"); SCEN = sys.argv[_i + 1]; del sys.argv[_i:_i + 2]
AREA = sys.argv[2] if len(sys.argv) > 2 else "Milton Keynes"
WEB = ROOT / "data" / "experiments" / "mk_heat" / "web" / "out"; (WEB / "ground").mkdir(parents=True, exist_ok=True)
SURVEY_END = "2021-01-17T23:59:59"
pool = {t["id"]: t for t in json.load(open(H / "rounds" / "pool.json"))["tiles"]}
to_bng = Transformer.from_crs(4326, 27700, always_xy=True).transform
to_wgs = Transformer.from_crs(27700, 4326, always_xy=True).transform
# the area (area.py): the City of Milton Keynes, holes filled; until 18 Oct 2026 the ONS 2022 built-up areas of the
# city, whose outline left out the parks inside it (49 of central MK's 144 km of footpath; Jacob, 18 Oct 2026:
# "footpaths feel incomplete in CMK"). It bounds the figures; footpaths and stops are kept wherever tiles were modelled.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from area import area as _area, urban as _urban  # noqa: E402
from shapely.geometry import Polygon as _P, MultiPolygon as _MP
bua = _area(H); bua_p = prep(bua)
# the figures twice: the whole area's and its urban part's (area.urban; Jacob, 19 Oct 2026: "maybe split the figures
# between the urban core and the greater extent. because not many people live in the rural bits")
urb = _urban(H); urb_p = prep(urb)

# per-tile metric, hours, building and grey masks
# per-tile files are read when used and not held open: the city's 138 tiles hold about 8 GB of hourly values as
# float32, and keeping every file open passes macOS's limit of 256 open files
from functools import lru_cache
class _Files(dict):
    """{tile: npz path}; [tile] gives a dict of its arrays, the last four tiles kept"""
    def __getitem__(self, t):
        return _read(dict.__getitem__(self, t))
@lru_cache(maxsize=4)
def _read(path):
    with np.load(path) as z:
        return {k: z[k] for k in z.files}
shade = _Files({f.stem: f for f in sorted((H / "shade").glob("*.npz"))})
utci = _Files({f.stem: f for f in sorted((H / "utci").glob("*.npz"))}) if (H / "utci").is_dir() else {}
mode = "utci" if utci and set(utci) >= set(shade) else "sun"
grey_m = dict(np.load(H / "layers" / "newbuild_mask.npz"))
sh_hours = [int(h) for h in shade[next(iter(shade))]["hours"]]
if mode == "utci":
    u_hours = [int(h) for h in utci[next(iter(utci))]["hours"]]
    hours = [h for h in sh_hours if h in u_hours]
    _sel = [u_hours.index(h) for h in hours]
    @lru_cache(maxsize=4)
    def _utci_of(t):
        f = H / f"utci_{SCEN}" / f"{t}.npz" if SCEN else None
        if f is not None and f.exists():
            with np.load(f) as z:
                return z["utci"][[list(z["hours"]).index(h) for h in hours]].astype(np.float32) / 10
        return utci[t]["utci"][_sel].astype(np.float32) / 10
    class _Metric(dict):
        def __getitem__(self, t):
            return _utci_of(t)
    metric = _Metric(dict.fromkeys(utci))
    # 1 degree steps from 30 to 44 (Jacob, 18 Oct 2026: "40 to 34 by your scale is red to orange"), with the UTCI
    # assessment scale's band edges (Broede et al. 2012) at 32 (strong) and 38 (very strong) named on the key
    anchors = [(30, "#a9c3cc"), (32, "#e9e2c9"), (34, "#f3cf8f"), (36, "#eea55a"), (38, "#d9622f"), (40, "#c8321f"), (42, "#8f1d22"), (44, "#5a1426")]
    def ramp(v):
        for (v0, h0), (v1, h1) in zip(anchors[:-1], anchors[1:]):
            if v0 <= v <= v1:
                f = (v - v0) / (v1 - v0); c0 = [int(h0[i:i + 2], 16) for i in (1, 3, 5)]; c1 = [int(h1[i:i + 2], 16) for i in (1, 3, 5)]
                return "#" + "".join(f"{round(a_ + (b_ - a_) * f):02x}" for a_, b_ in zip(c0, c1))
        return anchors[-1][1]
    steps = list(range(30, 45))
    classes = [{"lo": -99 if v == 30 else v, "label": {30: "30° or less", 34: "34°", 38: "38°", 42: "42°", 44: "44°+"}.get(v, ""),
                "words": {32: "strong heat stress", 38: "very strong"}.get(v, "")} for v in steps]
    colors = [ramp(v) for v in steps]; hot = steps.index(38)
else:
    hours = sh_hours
    metric = {t: shade[t]["sun"].astype(np.float32) / 2 for t in shade}          # percent of the cell in sun (one area)
    classes = [{"lo": -1, "label": "Shade"}, {"lo": 20, "label": "Part shade"}, {"lo": 80, "label": "Full sun"}]
    colors = ["--c0", "--c2", "--c3"]; hot = 2
los = np.array([c["lo"] for c in classes[1:]])
klass = lambda v: np.searchsorted(los, v, side="right")
tiles = sorted(metric)
bld = {t: shade[t]["bld"] for t in tiles}
# the air shown with each hour: the mean over the modelled tiles of each tile's own UKV 2 km series (utci.py)
_ukv = {p[0]: u["hourly"] for p, u in zip(json.load(open(H / "weather_ukv" / "tile_points.json")),
                                          json.load(open(H / "weather_ukv" / "ukv_2km_2026-08-12_14.json")))}
_t0 = _ukv[tiles[0]]["time"]
wxi = {int(t[11:13]): k for k, t in enumerate(_t0) if t.startswith("2026-08-13")}
wx = {v: [float(np.mean([_ukv[t][v][k] for t in tiles])) for k in range(len(_t0))] for v in ("temperature_2m", "relative_humidity_2m")}


def ampm(h):
    return f"{(h - 1) % 12 + 1}{'am' if h < 12 else 'pm'}"


def sample(xs, ys):
    """metric per hour, building flag and grey flag at points (nan / -1 off the tiles)"""
    v = np.full((len(xs), len(hours)), np.nan, np.float32); b = np.full(len(xs), -1, np.int8); gr = np.zeros(len(xs), bool)
    for t in tiles:
        cx0, cy0, cx1, cy1 = pool[t]["core"]
        m = (xs >= cx0) & (xs < cx1) & (ys >= cy0) & (ys < cy1)
        if not m.any():
            continue
        c = (xs[m] - cx0).astype(int); r = (cy1 - 1 - ys[m]).astype(int)
        v[m] = metric[t][:, r, c].T; b[m] = bld[t][r, c]; gr[m] = grey_m[t][r, c]
    return v, b, gr


# BUA mask per tile (1 m)
inb = {}
for t in tiles:
    cx0, cy0, cx1, cy1 = pool[t]["core"]
    inb[t] = rasterize([(bua, 1)], out_shape=(int(cy1 - cy0), int(cx1 - cx0)), transform=from_origin(cx0, cy1, 1, 1), fill=0, dtype="uint8").astype(bool)
inu = {}
for t in tiles:
    cx0, cy0, cx1, cy1 = pool[t]["core"]
    inu[t] = rasterize([(urb, 1)], out_shape=(int(cy1 - cy0), int(cx1 - cx0)), transform=from_origin(cx0, cy1, 1, 1), fill=0, dtype="uint8").astype(bool)

# carriageways and railway land, left out of "open ground" (Jacob, 18 Oct 2026: "roads are unlikely to have people
# walking on them"): OSM as on 17 Jan 2021; a road's width is its OSM width, else its lanes x 3.65 m (the UK standard
# lane width, DMRB CD 127), else one lane each way (one lane if one-way); railway land as OSM landuse=railway.
# Service roads (driveways, car park aisles) stay in: people walk there.
from shapely.geometry import Polygon as _Poly
CAR = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "motorway_link", "trunk_link",
       "primary_link", "secondary_link", "tertiary_link", "living_street", "busway"}
LANE_M = 3.65
def _num(v):
    try:
        return float(str(v).split(";")[0].replace("m", "").strip())
    except ValueError:
        return None
nogo = []
for e in json.load(open(H / "osm" / "roads_rail_2021-01-17.json"))["elements"]:
    tg, geom = e.get("tags", {}), e.get("geometry")
    if e["type"] != "way" or not geom:
        continue
    ex, ny = to_bng([q["lon"] for q in geom], [q["lat"] for q in geom])
    if tg.get("landuse") == "railway" and len(ex) >= 4:
        nogo.append(_Poly(zip(ex, ny)).buffer(0))
    elif tg.get("highway") in CAR and len(ex) >= 2 and tg.get("tunnel", "no") == "no" and tg.get("bridge", "no") == "no":
        w = _num(tg.get("width")) or ((_num(tg.get("lanes")) or (1 if tg.get("oneway") == "yes" else 2)) * LANE_M)
        nogo.append(LineString(zip(ex, ny)).buffer(w / 2, cap_style=2))
nogo_u = unary_union(nogo)
road = {}
for t in tiles:
    cx0, cy0, cx1, cy1 = pool[t]["core"]
    road[t] = rasterize([(nogo_u, 1)], out_shape=(int(cy1 - cy0), int(cx1 - cx0)), transform=from_origin(cx0, cy1, 1, 1), fill=0, dtype="uint8").astype(bool)
print(f"carriageway and railway land: {np.mean([road[t].mean() for t in tiles]):.1%} of the modelled tiles", flush=True)
np.savez_compressed(H / "layers" / "road_mask.npz", **road)
# water, left out of "open ground" as the roads are (Jacob, 18 Oct 2026: "obviously people don't walk in lakes, rivers,
# streams, ponds"): OSM's water areas (water.py) and the cells the land cover makes water (most returns the model's Water)
import water as _water  # noqa: E402
import rasterio.windows  # noqa: E402
_cores = [pool[t]["core"] for t in tiles]
wat_u = _water.polygons(H, (min(c[0] for c in _cores), min(c[1] for c in _cores), max(c[2] for c in _cores), max(c[3] for c in _cores)))
off = {}
for t in tiles:
    cx0, cy0, cx1, cy1 = pool[t]["core"]
    w_ = (rasterize([(wat_u, 1)], out_shape=(int(cy1 - cy0), int(cx1 - cx0)), transform=from_origin(cx0, cy1, 1, 1), fill=0, dtype="uint8").astype(bool)
          if not wat_u.is_empty else np.zeros((int(cy1 - cy0), int(cx1 - cx0)), bool))
    lcf = H / "surfaces" / f"{t}_lc.tif"
    if lcf.exists():
        with rasterio.open(lcf) as r_:
            w_ |= r_.read(1, window=rasterio.windows.from_bounds(cx0, cy0, cx1, cy1, r_.transform), boundless=True, fill_value=0) == 7
    off[t] = road[t] | w_
print(f"water: {np.mean([(off[t] & ~road[t]).mean() for t in tiles]):.1%} of the modelled tiles", flush=True)

# open ground: stats over open, modelled cells in the BUA; images at 2 m
nk = len(classes); stats = {"ground": np.zeros((len(hours), nk)), "paths": np.zeros((len(hours), nk)), "stops": np.zeros((len(hours), nk))}
ustats = {v: np.zeros_like(a) for v, a in stats.items()}           # the urban part's
for t in tiles:
    ok = inb[t] & (bld[t] == 0) & ~grey_m[t] & ~off[t]; ok_u = ok & inu[t]
    for k in range(len(hours)):
        stats["ground"][k] += np.bincount(klass(metric[t][k][ok]), minlength=nk)
        ustats["ground"][k] += np.bincount(klass(metric[t][k][ok_u]), minlength=nk)
X0 = min(pool[t]["core"][0] for t in tiles); Y0 = min(pool[t]["core"][1] for t in tiles)
X1 = max(pool[t]["core"][2] for t in tiles); Y1 = max(pool[t]["core"][3] for t in tiles)
# the images' cell: 2 m (one 1 m cell of each 2 x 2 block) where the area fits one 4,096 px image (central MK), else 3 m
# (the city: its 2 m images and the two scenarios' came to about 200 MB, near the artifact's 256 MB, and slow to step
# through on a phone; footpaths and stops keep their own 1 m samples whatever the step)
STEP = 2 if max(X1 - X0, Y1 - Y0) / 2 <= 4096 else 3
W, Hh = -(-int(X1 - X0) // STEP), -(-int(Y1 - Y0) // STEP)
src_tr = from_origin(X0, Y1, STEP, STEP)
dst_tr, dw, dh = calculate_default_transform("EPSG:27700", "EPSG:3857", W, Hh, X0, Y0, X1, Y1)
l, b_, r_, t_ = rasterio.transform.array_bounds(dh, dw, dst_tr)
merc = Transformer.from_crs(3857, 4326, always_xy=True).transform
corners = [list(merc(l, t_)), list(merc(r_, t_)), list(merc(r_, b_)), list(merc(l, b_))]
pal_hex = {"--c0": "#9dbdca", "--c1": "#f2d58c", "--c2": "#eea55a", "--c3": "#c8321f", "--c4": "#66172a"}   # as the page's tokens
pal = [tuple(int((pal_hex.get(c) or c)[i:i + 2], 16) for i in (1, 3, 5)) for c in colors]
BLD_HEX = "#e6e3de"                     # the page's building fill: buildings in the images come from the 2021 lidar
BIDX = len(pal); pal = pal + [tuple(int(BLD_HEX[i:i + 2], 16) for i in (1, 3, 5))]
# each image in pieces of at most 4,096 px a side, the texture size WebGL devices support almost without exception
# (web3dsurvey.com, MAX_TEXTURE_SIZE); the city at 2 m is larger than that
PIECE = 4096
nx_, ny_ = -(-dw // PIECE), -(-dh // PIECE); pw_, ph_ = -(-dw // nx_), -(-dh // ny_)
pieces = []
for j in range(ny_):
    for i in range(nx_):
        r0_, c0_ = j * ph_, i * pw_; r1_, c1_ = min(dh, r0_ + ph_), min(dw, c0_ + pw_)
        xl, yt = dst_tr * (c0_, r0_); xr, yb = dst_tr * (c1_, r1_)
        pieces.append({"id": f"{j}{i}", "win": (r0_, r1_, c0_, c1_),
                       "corners": [list(merc(xl, yt)), list(merc(xr, yt)), list(merc(xr, yb)), list(merc(xl, yb))]})
SFX = f"-{SCEN}" if SCEN else ""                  # a scenario's images: <name>-<scenario>_<piece>.png
for f in (WEB / "ground").glob(f"*-{SCEN}_*.png" if SCEN else "*.png"):     # this script's own earlier images
    f.unlink()


def save(cl, name, palette):
    """reproject a 2 m class grid (27700) to Web Mercator (nearest) and write it as pieces, ground/<name>_<piece>.png"""
    dst = np.full((dh, dw), 255, np.uint8)
    reproject(cl, dst, src_transform=src_tr, src_crs="EPSG:27700", dst_transform=dst_tr, dst_crs="EPSG:3857",
              resampling=Resampling.nearest, src_nodata=255, dst_nodata=255)
    for pc in pieces:
        r0_, r1_, c0_, c1_ = pc["win"]
        im = Image.fromarray(dst[r0_:r1_, c0_:c1_], mode="P")
        im.putpalette(palette + [0, 0, 0] * (256 - len(palette) // 3))
        im.save(WEB / "ground" / f"{name}_{pc['id']}.png", optimize=True, transparency=255)


def grid_of(t):
    """the tile's 1 m cells that are samples of the one grid over the whole area (the middle cell of each STEP x STEP
    block from the area's north-west corner: a 1,000 m tile does not divide into 3 m blocks), and where they start"""
    cx0, cy0, cx1, cy1 = pool[t]["core"]
    ox, oy = int(cx0 - X0), int(Y1 - cy1)
    j0, i0 = (STEP // 2 - ox) % STEP, (STEP // 2 - oy) % STEP
    return (slice(i0, None, STEP), slice(j0, None, STEP)), ((oy + i0) // STEP, (ox + j0) // STEP)
cls_h = np.full((len(hours), Hh, W), 255, np.uint8)       # every hour's grid, filled one tile at a time
for t in tiles:
    S2, (r0, c0) = grid_of(t)
    keep = ((bld[t] == 0) & ~grey_m[t] & ~off[t] & inb[t])[S2]; b = ((bld[t] == 1) & ~grey_m[t] & inb[t])[S2]
    for k in range(len(hours)):
        v = metric[t][k][S2]
        c = np.where(keep & np.isfinite(v), klass(np.nan_to_num(v)), 255).astype(np.uint8)
        c[b] = BIDX
        cls_h[k, r0:r0 + c.shape[0], c0:c0 + c.shape[1]] = c
flat_pal = [x for p_ in pal for x in p_]
files = []
for k, h in enumerate(hours):
    save(cls_h[k], f"{h:02d}{SFX}", flat_pal); files.append(f"{h:02d}")
del cls_h
# the whole day: hours at the "hot" class or above per cell, in the day classes (0, 1-2, 3-4, 5 or more)
day_lo = [0, 1, 3, 5]
day_hex = ["#a9c3cc", "#f3cf8f", "#e2803d", "#a8281c"]   # as the page's --d0..--d3
hot_lo = classes[hot]["lo"]
cl = np.full((Hh, W), 255, np.uint8)
for t in tiles:
    S2, (r0, c0) = grid_of(t)
    n = (metric[t] >= hot_lo).sum(axis=0)[S2]
    c = np.where(((bld[t] == 0) & ~grey_m[t] & ~off[t] & inb[t])[S2], np.searchsorted(day_lo[1:], n, side="right"), 255).astype(np.uint8)
    c[((bld[t] == 1) & ~grey_m[t] & inb[t])[S2]] = len(day_hex)
    cl[r0:r0 + c.shape[0], c0:c0 + c.shape[1]] = c
save(cl, f"day{SFX}", [int(h_[i:i + 2], 16) for h_ in day_hex + [BLD_HEX] for i in (1, 3, 5)])
# the buildings as modelled (2021 lidar), drawn in every view: complete where OSM's outlines are not, and where the heat is
cl = np.full((Hh, W), 255, np.uint8)
for t in tiles:
    S2, (r0, c0) = grid_of(t)
    c = np.where(((bld[t] == 1) & ~grey_m[t] & inb[t])[S2], 0, 255).astype(np.uint8)
    cl[r0:r0 + c.shape[0], c0:c0 + c.shape[1]] = c
if not SCEN:                                       # the buildings are the same in a scenario
    save(cl, "bld", [int(BLD_HEX[i:i + 2], 16) for i in (1, 3, 5)])
del cl
dstats = {"ground": np.zeros(len(day_lo)), "paths": np.zeros(len(day_lo)), "stops": np.zeros(len(day_lo))}
udstats = {v: np.zeros_like(a) for v, a in dstats.items()}
dclass = lambda nh: int(np.searchsorted(day_lo[1:], nh, side="right"))
for t in tiles:
    ok = inb[t] & (bld[t] == 0) & ~grey_m[t] & ~off[t]
    nh_ = np.searchsorted(day_lo[1:], (metric[t] >= hot_lo).sum(axis=0), side="right")
    dstats["ground"] += np.bincount(nh_[ok], minlength=len(day_lo))
    udstats["ground"] += np.bincount(nh_[ok & inu[t]], minlength=len(day_lo))
print("ground images", dw, "x", dh, flush=True)

# footpaths, as on 17 Jan 2021
WALK = {"footway", "pedestrian", "path", "steps", "cycleway", "living_street", "bridleway"}
osm = json.load(open(H / "osm" / "walk_now.json"))
paths, plen = [], []; n_under = 0.0
inside_tiles = lambda ex, ny: any(pool[t]["core"][0] <= ex < pool[t]["core"][2] and pool[t]["core"][1] <= ny < pool[t]["core"][3] for t in tiles)
def piece(a, b, d, ex, ny):
    """the way's geometry from distance a to b, as page-ready deltas of 1e-5 degrees"""
    kk = np.unique(np.r_[a, d[(d > a) & (d < b)], b]); lon, lat = to_wgs(np.interp(kk, d, ex), np.interp(kk, d, ny))
    q = np.round(np.c_[lon, lat] * 1e5).astype(int)
    return np.diff(np.r_[[[0, 0]], q], axis=0).ravel().tolist()


for w in osm["elements"]:
    tg = w.get("tags", {})
    if w["type"] != "way" or tg.get("highway") not in WALK:
        continue
    if tg.get("indoor", "no") != "no":
        continue                         # inside a building (the shopping centre's malls): not outdoors at all
    under = tg.get("covered") == "yes" or tg.get("tunnel", "no") != "no" or tg.get("location") == "underground" \
        or (tg.get("layer", "0").lstrip("-").isdigit() and int(tg.get("layer", "0")) < 0)
    on_bridge = tg.get("bridge", "no") != "no"
    ex, ny = to_bng(np.array([p["lon"] for p in w["geometry"]]), np.array([p["lat"] for p in w["geometry"]]))
    d = np.concatenate([[0], np.cumsum(np.hypot(np.diff(ex), np.diff(ny)))])
    if d[-1] < 1:
        continue
    if under:
        cuts = np.arange(0, d[-1] + 25, 25.0); cuts[-1] = d[-1]
        for a, b in zip(cuts[:-1], cuts[1:]):
            m = (a + b) / 2
            if b - a >= 1 and inside_tiles(np.interp(m, d, ex), np.interp(m, d, ny)) and bua_p.contains(Point(np.interp(m, d, ex), np.interp(m, d, ny))):
                paths.append([piece(a, b, d, ex, ny), [], 2]); n_under += b - a
        continue
    # sample every metre; the way is drawn and modelled only where it is out of doors in 2021 (off building cells, or on
    # a bridge's deck), so a path never crosses a building on the map; each open run is cut into pieces of at most 25 m
    s_ = np.r_[np.arange(0, d[-1], 1.0), d[-1]]; px, py = np.interp(s_, d, ex), np.interp(s_, d, ny)
    v, bb, gr = sample(px, py)
    ok = (bb >= 0) if on_bridge else (bb == 0)
    # stretches under a 2021 roof (an overhang, colonnade or canopy: CMK's covered frontages; Jacob, 18 Oct 2026) are drawn
    # as under cover, in shade all day, not dropped: the lidar saw the roof above them, not the path
    if not on_bridge:
        cov = bb == 1
        ce = np.flatnonzero(np.diff(np.r_[0, cov.astype(int), 0]))
        for q0, q1 in zip(ce[::2], ce[1::2]):
            for c0 in range(q0, q1 - 1, 25):
                c1 = min(c0 + 25, q1 - 1)
                if c1 > c0 and bua_p.contains(Point(px[(c0 + c1) // 2], py[(c0 + c1) // 2])):
                    paths.append([piece(s_[c0], s_[c1], d, ex, ny), [], 2]); n_under += s_[c1] - s_[c0]
    edges = np.flatnonzero(np.diff(np.r_[0, ok.astype(int), 0]))
    for r0, r1 in zip(edges[::2], edges[1::2]):             # open runs [r0, r1)
        if r1 - r0 < 2:
            continue
        for c0 in range(r0, r1 - 1, 25):
            c1 = min(c0 + 25, r1 - 1)
            if c1 <= c0:
                continue
            a, b = s_[c0], s_[c1]
            val = np.nanmean(v[c0:c1 + 1], axis=0)
            if not np.isfinite(val).all():
                continue
            grey = int(gr[c0:c1 + 1].mean() > 0.5)
            in_city = bua_p.contains(Point(px[(c0 + c1) // 2], py[(c0 + c1) // 2]))     # counted in the figures
            if not in_city:
                continue                             # drawn only where counted (Jacob, 18 Oct 2026: a stop and paths
                                                     # outside the area showed on the map without counting)
            vals = [int(round(x)) for x in val]
            paths.append([piece(a, b, d, ex, ny), vals, grey]); plen.append(b - a)
            if not grey and in_city:
                in_urb = urb_p.contains(Point(px[(c0 + c1) // 2], py[(c0 + c1) // 2]))
                for S_, D_ in ((stats, dstats), *(((ustats, udstats),) if in_urb else ())):
                    for k in range(len(hours)):
                        S_["paths"][k, klass(val[k])] += b - a
                    D_["paths"][dclass(int((np.array(vals) >= hot_lo).sum()))] += b - a
print(len(paths), "path pieces,", f"{sum(plen) / 1000:.0f} km modelled, {n_under / 1000:.1f} km under cover", flush=True)

# bus stops
stops = []; URB_STOPS = set()                    # the counted stops in the urban part, by NaPTAN code
SHELTERED = set(json.load(open(H / "layers" / "shelters.json"))["atco"]) if (H / "layers" / "shelters.json").exists() else set()
if SCEN and (H / "layers" / f"{SCEN}.json").exists():           # the scenario's own new shelters (shelters.py add)
    SHELTERED |= {s_["atco"] for s_ in json.load(open(H / "layers" / f"{SCEN}.json")).get("new_shelters", [])}
for row in csv.DictReader(open(H / "naptan" / "naptan_049.csv")):
    if row["StopType"] != "BCT" or row["Status"] != "active":
        continue
    try:
        e, n = float(row["Easting"]), float(row["Northing"])
    except ValueError:
        continue
    in_city = bua_p.contains(Point(e, n))
    if not in_city:
        continue                                   # drawn only where counted, as the footpaths
    xs = e + np.repeat([-1, 0, 1], 3); ys = n + np.tile([-1, 0, 1], 3)
    v, bb, gr = sample(xs, ys)
    if (bb < 0).all():
        continue                                   # off the tiles
    keep = bb == 0
    grey = int(keep.any() and gr[keep].mean() > 0.5)
    if not keep.any() and not grey:
        # every cell round the stop is under a 2021 roof: a stop under a canopy or overhang, in shade all day
        lon, lat = to_wgs(e, n)
        stops.append({"x": round(lon, 6), "y": round(lat, 6), "n": row["CommonName"],
                      "m": ", ".join(x for x in [row["Indicator"], row["LocalityName"]] if x), "v": [], "g": 2})
        continue
    lon, lat = to_wgs(e, n)
    # a stop: the coolest of its 3 x 3 m each hour, where people waiting stand (Jacob, 18 Oct 2026: "yes judge every stop
    # by its coolest spot"); until then only a sheltered stop was judged so, the others by the mean of the nine cells
    val = np.nanmin(v[keep], axis=0) if keep.any() else np.full(len(hours), np.nan)
    vals = [] if grey or not np.isfinite(val).all() else [int(round(x)) for x in val]
    if not vals:
        grey = 1
    sub = ", ".join(x for x in [row["Indicator"], row["LocalityName"]] if x)   # NaPTAN's bearing is the buses' way, not the stop's face
    stops.append({"x": round(lon, 6), "y": round(lat, 6), "n": row["CommonName"], "m": sub, "v": vals, "g": grey,
                  **({"sh": 1} if row["ATCOCode"] in SHELTERED else {})})    # a shelter OSM records (shelters.py)
    if not grey and in_city:
        in_urb = urb_p.contains(Point(e, n))
        if in_urb:
            URB_STOPS.add(row["ATCOCode"])
        for S_, D_ in ((stats, dstats), *(((ustats, udstats),) if in_urb else ())):
            for k in range(len(hours)):
                S_["stops"][k, klass(val[k])] += 1
            D_["stops"][dclass(int((np.array(vals) >= hot_lo).sum()))] += 1
n_stops = int(round(stats["stops"][0].sum()))     # the stops counted in the figures
n_stops_u = int(round(ustats["stops"][0].sum()))
print(len(stops), "stops,", n_stops, "modelled", flush=True)

# grey areas clipped to the BUA
gj = json.load(open(H / "layers" / "newbuild.geojson"))
bua_w = stransform(lambda a, b, *_: to_wgs(a, b), bua)
grey_f = []
for f in gj["features"]:
    gg = shape(f["geometry"]).intersection(bua_w)
    if not gg.is_empty:
        grey_f.append({"type": "Feature", "properties": {}, "geometry": mapping(gg)})

# place labels from the basemap
rd = Reader(MmapSource(open(H / "basemap_mk.pmtiles", "rb"))); Z = 12; nz = 2 ** Z
labels = {}
(lo0, lo1), (la0, la1) = [sorted(v) for v in to_wgs([X0, X1], [Y0, Y1])]
tx = lambda lon: int((lon + 180) / 360 * nz); ty = lambda lat: int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * nz)
for x in range(tx(lo0), tx(lo1) + 1):
    for y in range(ty(la1), ty(la0) + 1):
        d = rd.get(Z, x, y)
        if not d:
            continue
        d = gzip.decompress(d) if d[:2] == b"\x1f\x8b" else d
        lay = mvt.decode(d, default_options={"y_coord_down": True}).get("places")
        for f in (lay or {}).get("features", []):
            p = f["properties"]; px, py = f["geometry"]["coordinates"]
            lon = (x + px / lay["extent"]) / nz * 360 - 180; lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + py / lay["extent"]) / nz))))
            big = p.get("kind_detail") in ("town", "city") or p.get("name") == "Central Milton Keynes"
            sub = p.get("kind") == "neighbourhood" and p.get("kind_detail") == "suburb"
            ex, ny = to_bng(lon, lat)
            if (big or sub) and p.get("name") != "Milton Keynes" and X0 <= ex < X1 and Y0 <= ny < Y1 and bua_p.contains(Point(ex, ny)):
                labels[p["name"]] = {"name": p["name"], "x": round(lon, 5), "y": round(lat, 5), "big": int(big)}

# road, park and landmark names from the basemap (zoom 14): each named road labelled along its length about every
# 700 m (a display spacing), turned to the road; parks at a point inside them; landmarks of a few kinds at their own
# minimum zoom. The page shows each from its zoom.
from shapely.geometry import shape as _shape, LineString as _LS, MultiLineString as _MLS
from shapely.ops import linemerge as _merge
Z2 = 14; nz2 = 2 ** Z2
tx2 = lambda lon: int((lon + 180) / 360 * nz2); ty2 = lambda lat: int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * nz2)
roads, parks, pois = {}, {}, {}
LANDMARK = {"mall", "station", "train_station", "museum", "theatre", "hospital", "university", "stadium", "marketplace", "cinema", "townhall"}
for x in range(tx2(lo0), tx2(lo1) + 1):
    for y in range(ty2(la1), ty2(la0) + 1):
        d = rd.get(Z2, x, y)
        if not d:
            continue
        d = gzip.decompress(d) if d[:2] == b"\x1f\x8b" else d
        m = mvt.decode(d, default_options={"y_coord_down": True})
        def to_b(px, py, ext):
            lon = (x + np.asarray(px) / ext) / nz2 * 360 - 180
            lat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * (y + np.asarray(py) / ext) / nz2))))
            return to_bng(lon, lat)
        lay = m.get("roads")
        for f in (lay or {}).get("features", []):
            pr = f["properties"]; nm = pr.get("name")
            if pr.get("kind") != "major_road" or not nm or "roundabout" in nm.lower() or f["geometry"]["type"] not in ("LineString", "MultiLineString"):
                continue
            g = stransform(lambda a_, b_, *_: to_b(a_, b_, lay["extent"]), _shape(f["geometry"]))
            roads.setdefault(nm, []).append(g)
        lay = m.get("landuse")
        for f in (lay or {}).get("features", []):
            pr = f["properties"]
            if pr.get("kind") in ("park", "recreation_ground") and pr.get("name") and f["geometry"]["type"] in ("Polygon", "MultiPolygon"):
                g = stransform(lambda a_, b_, *_: to_b(a_, b_, lay["extent"]), _shape(f["geometry"])).buffer(0)
                parks.setdefault(pr["name"], []).append(g)
        lay = m.get("pois")
        for f in (lay or {}).get("features", []):
            pr = f["properties"]
            if pr.get("kind") in LANDMARK and pr.get("name") and (pr.get("min_zoom") or 99) <= 14 and f["geometry"]["type"] == "Point":
                px, py = f["geometry"]["coordinates"]; ex, ny = to_b(px, py, lay["extent"])
                pois[pr["name"]] = (float(ex), float(ny), int(pr.get("min_zoom") or 14))
inside = lambda ex, ny: X0 <= ex < X1 and Y0 <= ny < Y1
extra = []
for nm, parts in roads.items():
    ln = _merge(_MLS([q for g in parts for q in (g.geoms if hasattr(g, "geoms") else [g])]))
    for L in (ln.geoms if hasattr(ln, "geoms") else [ln]):
        if L.length < 300:
            continue
        for dpos in np.arange(350, L.length, 700.0):
            p0, p1 = L.interpolate(dpos - 20), L.interpolate(dpos + 20); pm = L.interpolate(dpos)
            if not inside(pm.x, pm.y):
                continue
            ang = math.degrees(math.atan2(p1.y - p0.y, p1.x - p0.x)); rot = -ang
            rot = (rot + 90) % 180 - 90
            lon, lat = to_wgs(pm.x, pm.y)
            extra.append({"name": nm, "x": round(lon, 5), "y": round(lat, 5), "kind": "road", "rot": round(rot, 1), "minz": 14})
for nm, parts in parks.items():
    g = unary_union(parts) if len(parts) > 1 else parts[0]
    if g.area < 20000:
        continue
    pt = g.representative_point()
    if inside(pt.x, pt.y):
        lon, lat = to_wgs(pt.x, pt.y); extra.append({"name": nm, "x": round(lon, 5), "y": round(lat, 5), "kind": "park", "minz": 13.5})
for nm, (ex, ny, mz) in pois.items():
    if inside(ex, ny):
        lon, lat = to_wgs(ex, ny); extra.append({"name": nm, "x": round(lon, 5), "y": round(lat, 5), "kind": "poi", "minz": max(13, mz)})
# one label per road name within 400 m (dual carriageways and the basemap's tile buffers give near copies)
kept = []
for e_ in extra:
    if e_["kind"] == "road" and any(k["kind"] == "road" and k["name"] == e_["name"] and
                                    math.hypot((k["x"] - e_["x"]) * 68600, (k["y"] - e_["y"]) * 111300) < 400 for k in kept):
        continue
    kept.append(e_)
extra = kept
print(len(extra), "road, park and landmark labels", flush=True)

# text
frac = {v: stats[v] / np.maximum(stats[v].sum(axis=1, keepdims=True), 1) for v in stats}
ufrac = {v: ustats[v] / np.maximum(ustats[v].sum(axis=1, keepdims=True), 1) for v in ustats}
day_share = lambda ds: {v: (ds[v] / max(ds[v].sum(), 1)).round(4).tolist() for v in ds}
hotshare = {v: frac[v][:, hot:].sum(axis=1) for v in frac}
peak = int(np.argmax(hotshare["paths"]))
hp = hours[peak]
OF_AREA = AREA + ("'" if AREA.endswith("s") else "'s")      # Milton Keynes' footpaths
if mode == "utci":
    head = None   # set below, from the shade figures
    sun_v, shade_v = [], []
    for t in tiles:
        ok = inb[t] & (bld[t] == 0) & ~grey_m[t] & ~off[t]; lit = shade[t]["sun"][sh_hours.index(hp)] / 200
        sun_v.append(metric[t][peak][ok & (lit >= 0.8)]); shade_v.append(metric[t][peak][ok & (lit < 0.2)])
    ms, mh = float(np.median(np.concatenate(sun_v))), float(np.median(np.concatenate(shade_v)))
    # the headline says what the page opens on (footpaths over the whole day); the peak hour's sun and shade below it
    path_day = 1 - dstats["paths"][0] / max(dstats["paths"].sum(), 1)
    upath_day = 1 - udstats["paths"][0] / max(udstats["paths"].sum(), 1)
    # said plainly (Jacob, 18 Oct 2026: "these key sentences, can you make them clearer, more actionable and direct"):
    # a UTCI of 38 °C or more is the scale's "very strong heat stress" (38 to 46; Bröde et al. 2012), named once and
    # explained under it; the shade figures say what changes it
    # about the people using the place, as far as the model can say: who walks where is not known, so a share of footpath
    # (Jacob, 18 Oct 2026, suggesting "69% of Milton Keynes' pedestrians were exposed to very strong heat stress")
    HEAD = "On the hottest day of the summer, walkers on <em>{}%</em> of {} footpaths faced very strong heat stress."
    head, uhead = HEAD.format(round(path_day * 100), OF_AREA), HEAD.format(round(upath_day * 100), OF_AREA)
    never, unever = int(dstats["stops"][0]), int(udstats["stops"][0]); most = max(int((np.array(st["v"]) >= hot_lo).sum()) for st in stops if not st["g"])
    deck = "That is a feels-like temperature of 38 °C or more, for at least an hour."      # the definition only (Jacob: "you can cut this extra text out")
    key, unit = "Feels like (UTCI), °C", "°C"
    now_fmt, count_fmt = "Feels like {v} °C now.", "{n} of {N} hours at 38 °C or more."
else:
    head = f"From {ampm(hp)} to {ampm(hp + 1)}, <em>{round(hotshare['paths'][peak] * 100)}%</em> of the footpaths in {AREA} had no shade."
    uhead = head                                  # the sunlit share is not split
    deck = "Sun and shade on the hottest day of the summer, from buildings and trees measured by lidar."
    key, unit = "Sun on the ground, at the middle of each hour", "%"
    now_fmt, count_fmt = "{v}% in sun now.", "In full sun for {n} of {N} hours."
# a number never parts from its unit at a line end
head, uhead, deck = (x.replace(" °C", "\u00a0°C").replace(" hours", "\u00a0hours") for x in (head, uhead, deck))
if SCEN:
    base = json.load(open(WEB / "data.json"))
    assert len(base["paths"]) == len(paths) and all(a[0] == b[0] and a[2] == b[2] for a, b in zip(base["paths"], paths)), \
        "the scenario's footpath pieces differ from the first pass's: run the first pass again"
    assert [(a["x"], a["y"], a["g"]) for a in base["stops"]] == [(b["x"], b["y"], b["g"]) for b in stops], "the stops differ from the first pass's"
    tj = json.load(open(H / "layers" / f"{SCEN}.json")); new = tj["trees"][:tj.get("n_planted", tj["n_knee"])]
    scs = base.setdefault("scenarios", {}); base.pop("scenario", None)       # one entry a scenario, in the order run
    sc_ = scs[SCEN] = {
        "name": SCEN, "n": len(new), "stops_only": bool(tj.get("stops_only")),
        # the trees standing now in the same tiles (treecount.py, lidar treetops), so the new ones read as a share of them
        "existing": (json.load(open(H / "layers" / "treecount.json"))["treetops"] if (H / "layers" / "treecount.json").exists() else None),
        "trees": [[round(v, 6) for v in to_wgs(c["x"], c["y"])] for c in new],
        # only what the scenario changes: {index: hourly values}; the page takes the first pass's values elsewhere
        "paths": {i: p_[1] for i, (p_, b_) in enumerate(zip(paths, base["paths"])) if p_[1] != b_[1]},
        "stops": {i: s_["v"] for i, (s_, b_) in enumerate(zip(stops, base["stops"])) if s_["v"] != b_["v"]},
        "stats": {v: frac[v].round(4).tolist() for v in frac}, "day_stats": day_share(dstats),
        "path_day": round(float(path_day), 4), "never": never, "most": most,
        "urban": {"stats": {v: ufrac[v].round(4).tolist() for v in ufrac}, "day_stats": day_share(udstats),
                  "path_day": round(float(upath_day), 4), "never": unever}}
    # the headline and the line under it for the switch (Jacob, 18 Oct 2026: "the ... sentence doesn't update when I
    # plant the trees"): the same figures as the page's, the scenario's against the first pass's, for the whole area and
    # for its urban part (its own stops, and the trees and shelters planted in it)
    hrs_of = lambda st, v: sum(sum(sh[hot:]) for sh in st[v])      # each hour's share at 38 or more, summed: hours each
    pct_b = round((1 - base["day"]["stats"]["paths"][0]) * 100); never_b = round(base["day"]["stats"]["stops"][0] * base["n_stops"])
    BU = base["urban"]
    n_ = f"{len(new):,}"
    _h = tj["tree"]["height"]
    TREE_IS = (f"Each is {_h:g}\u00a0m tall, the median of the trees beside paths and stops now."
               if tj.get("tree_rule") else f"Each is {_h:g}\u00a0m tall.")
    sh_new = tj.get("new_shelters", [])
    # each area's (stops counted, of them never at 38 as it was, never at 38 with the plan, % of footpath at 38 as it was,
    # with the plan, new trees, new shelters); the whole area's text is the scenario's own, the urban part's under "urban"
    AREAS = {"": (base["n_stops"], never_b, never, pct_b, round(path_day * 100), len(new), len(sh_new)),
             "urban": (BU["n_stops"], round(BU["day_stats"]["stops"][0] * BU["n_stops"]), unever,
                       round((1 - BU["day_stats"]["paths"][0]) * 100), round(upath_day * 100),
                       sum(1 for c in new if urb_p.contains(Point(c["x"], c["y"]))), sum(1 for s_ in sh_new if s_["atco"] in URB_STOPS))}
    ns = len(sh_new); sc_["shelters"] = ns
    if sc_["stops_only"]:
        # the trees for the bus stops alone (Jacob: "Wait with 100 trees you deal with the bus problem? Maybe we should just
        # focus on that then")
        sc_["label"] = "Shade at bus stops"; sc_["view"] = "stops"      # short enough for one line; the headline says what
        # one fact a line (Jacob, 18 Oct 2026: "simplify some of the text ... so the message is clearer"): the headline the
        # plan's result, the line under it the stops as they were, the note what was planted
        for a, (N, nb, nv, _pb, _p, nt, nsh) in AREAS.items():
            tx = sc_[a] if a else sc_; what = f"{nt:,} trees" + (f" and {nsh} shelters" if nsh else "")
            tx["headline"] = (f"{what} would spare people waiting at " + (f"<em>all {N:,}</em> bus stops" if nv == N
                              else f"<em>{nv:,}</em> of the {N:,} bus stops") + " from very strong heat stress.")
            tx["deck"] = f"As it was, {N - nb:,} of them reached 38\u00a0°C."
        sc_["note"] = ((f"{n_} new trees, the fewest that shade every stop in each hour it would reach 38\u00a0°C" if tj.get("stops_exact") else
                        f"{n_} new trees, each where it shades the most of a bus stop in the hours it reaches 38\u00a0°C")
                       + (f", and a shelter at the {ns} stops no tree can shade. " if ns else ". ") + TREE_IS)
    else:
        more = f"{round(len(new) / sc_['existing'] * 100)}% more trees" if sc_.get("existing") else f"{n_} new trees"
        sc_["label"] = more[0].upper() + more[1:]; sc_["view"] = "paths"
        for a, (N, _nb, nv, pb, p_, _nt, nsh) in AREAS.items():      # the stops no tree cools get shelters, as in the stop plan
            tx = sc_[a] if a else sc_
            tx["headline"] = (f"{more[0].upper() + more[1:]} would " + ("halve" if 0.45 <= p_ / max(pb, 1) <= 0.55 else "cut")
                              + f" the footpaths where walkers face very strong heat stress, from {pb}% to <em>{p_}%</em>.")
            tx["deck"] = ((f"Every bus stop would stay below 38\u00a0°C too" + (f", with a shelter at each of the {nsh} that no tree can shade." if nsh else "."))
                          if nv == N else f"{nv:,} of the {N:,} bus stops would stay below 38\u00a0°C.")
        first = sum(1 for c in new if c.get("phase") == 1)
        sc_["note"] = (f"{n_} new trees" + (f", one for every {round(sc_['existing'] / len(new))} standing now" if sc_.get("existing") else "")
                       + (": first by the bus stops, then where they shade the most sunlit footpaths in the hottest hours. "
                          if first else ", each where it shades the most sunlit footpath and bus stop in the hottest hours. ") + TREE_IS)
    json.dump(base, open(WEB / "data.json", "w"), separators=(",", ":"), ensure_ascii=False)
    print(f"scenario {SCEN}: {len(new)} trees; footpaths at 38 or more for an hour {sc_['path_day']:.1%} "
          f"(today {1 - base['day']['stats']['paths'][0]:.1%}); stops never at 38 {never} (today {never_b})", flush=True)
    sys.exit(0)
labs = [{"label": f"{ampm(h)}–{ampm(h + 1)}", "short": ampm(h), "file": f, "ta": wx["temperature_2m"][wxi[h]], "rh": round(wx["relative_humidity_2m"][wxi[h]])}
        for h, f in zip(hours, files)]
# the winters the lidar was flown in, from the tiles' surveys (a winter is July to June: 2020-12-15 is winter 2020-21)
_w = sorted({(lambda d: d.year if d.month >= 7 else d.year - 1)(__import__("datetime").date.fromisoformat(pool[t]["flown"])) for t in tiles})
_w = [f"{y}–{str(y + 1)[2:]}" for y in _w]
WINTERS = f"in winter {_w[0]}" if len(_w) == 1 else f"in the winters of {', '.join(_w[:-1])} and {_w[-1]}"
# what 38 means (Jacob, 18 Oct 2026: "we have demarked 38 degrees with the significance of being between healthy / not
# healthy. check this is the case. if not, adjust"): not a line between healthy and not. It is where the UTCI scale's
# very strong heat stress begins, its physiology from Blazejczyk et al. 2013 (Geographia Polonica 86(1), Table 2: from 38,
# a rise in core temperature at 30 min; from 32, at 120 min). Death rates in much of Europe rise from 26 and 32 (Di
# Napoli et al. 2018, Int J Biometeorol 62), but on the day every footpath reached 32 (strong heat stress) at some hour,
# so 32 would mark everything; 38 is the band edge shade still decides. The page says only what 38 means (its 26 to 32
# sentence taken out: Jacob, 19 Oct 2026, asked for it to be removed)
STRESS = ("From a UTCI of 38\u00a0°C (very strong heat stress), a walker's core temperature starts to rise within half an hour "
          "(Błażejczyk et al. 2013)." if mode == "utci" else "")
# what the land cover cannot tell (19 Oct 2026, landcover_fields_method.md, Decision: not applied): winter's bare fields
# can read as paving. Said on the page until Jacob, 19 Oct 2026: "the bit about fields is unneeded, it is already stated
# it is flown in winter"
# h is the UTC end of solweig's hour, so the hour in BST (UTC + 1) runs from h to h + 1
data = {
    "mode": mode, "area": AREA[0].upper() + AREA[1:], "classes": classes, "colors": colors, "hot": hot, "unit": unit, "now_fmt": now_fmt, "count_fmt": count_fmt, "key": key,
    "headline": head, "deck": deck,
    # how the map was made, in plain steps (Jacob, 18 Oct 2026: "How this was made doesn't actually explain that this models
    # all the trees and buildings in MK using lidar segmentation and then uses heat modelling using like air temp, wind")
    # shorter (Jacob, 19 Oct 2026: "make this conciser")
    "sources": (f"Environment Agency lidar flown {WINTERS} gives the shape of the area; a custom deep-learning model sorts its points "
                "into ground, buildings, trees and water. SOLWEIG (Lindberg et al. 2008) follows the sun over them hour by hour on "
                "13 August 2026 and, with the Met Office's 2 km UKV air temperature, humidity and wind, gives the feels-like "
                "temperature (UTCI) on each 1 m square. Footpaths are from OpenStreetMap, bus stops from NaPTAN; places built since "
                "the flight are greyed. New trees are placed as TreePlanter does (Wallenberg et al. 2022). Urban means the census "
                "areas the ONS classes as urban (2021). " + STRESS),
    # every source the figures rest on, in its own requested words where it asks for some (the README's references, checked
    # 18 Oct 2026: OS OpenMap Local's outlines were used and not credited; Open-Meteo asks for "Weather data by Open-Meteo.com")
    "credits": ("© OpenStreetMap contributors · Protomaps · Lidar © Environment Agency · NaPTAN © DfT · Contains OS data © Crown "
                "copyright and database right 2026 · Boundaries and urban areas: ONS · Weather: Met Office UKV (CC BY-SA 4.0), weather data by "
                "Open-Meteo.com · MapLibre"),
    "hours": labs, "ticks": [ampm(h) for h in hours[::3]], "start": peak,
    "stats": {v: frac[v].round(4).tolist() for v in frac}, "n_stops": n_stops,
    # the urban part's figures (area.urban), which the page shows first, and its outline (to 1 m, the model's cell)
    "urban": {"stats": {v: ufrac[v].round(4).tolist() for v in ufrac}, "day_stats": day_share(udstats), "n_stops": n_stops_u,
              "headline": uhead, "view_small": {"ground": "", "paths": "", "stops": f"of {n_stops_u:,}"},
              "outline": mapping(shapely.set_precision(stransform(lambda a, b, *_: to_wgs(a, b), urb.boundary.simplify(1.0)), 1e-6))},
    "day": {"lo": day_lo, "colors": ["--d0", "--d1", "--d2", "--d3"], "labels": ["None", "1–2", "3–4", "5 or more"],
            "stats": day_share(dstats),
            "peak_ta": round(max(wx["temperature_2m"][wxi[h]] for h in hours), 1)},
    # the cards' condition said once, above them, and under a card only what its number is out of (Jacob, 18 Oct 2026:
    # "simplify some of the text"; each card said "of path length reached 38° at some hour" and the like)
    "view_small": {"ground": "", "paths": "", "stops": f"of {n_stops:,}"},
    "view_small_day": {"ground": "", "paths": "", "stops": f"of {n_stops:,}"},
    # the line under the headline defines 38 for at least an hour, so the day's line says no more than "reached"
    "views_head": ({"day": "Reached 38\u00a0°C during the day", "hour": "At 38\u00a0°C or more, {h}"} if mode == "utci"
                   else {"day": "In sun at some hour", "hour": "In sun, {h}"}),
    "pieces": [{"id": pc["id"], "corners": pc["corners"]} for pc in pieces],
    "ground_corners": corners, "bounds": [[min(c[0] for c in corners), min(c[1] for c in corners)], [max(c[0] for c in corners), max(c[1] for c in corners)]],
    "labels": [l | {"kind": "big" if l["big"] else "suburb", "minz": 0 if l["big"] else 13} for l in labels.values()] + extra, "paths": paths, "stops": stops, "grey": {"type": "FeatureCollection", "features": grey_f},
}
json.dump(data, open(WEB / "data.json", "w"), separators=(",", ":"), ensure_ascii=False)
# the basemap and the label ranges its font needs (basemap.py)
sys.path.insert(0, str(Path(__file__).parent))
import basemap  # noqa: E402
basemap.write(H, WEB, data["bounds"])
print("mode", mode, "| peak", labs[peak]["label"], {v: round(float(hotshare[v][peak]), 3) for v in hotshare}, flush=True)
