"""SOLWEIG's land cover for each Milton Keynes crop (Jacob, 18 Oct 2026: "yes add land cover"), in UMEP's ids, which
set each cell's albedo, emissivity and ground-heating parameters (solweig SurfaceData.get_land_cover_properties,
Lindberg et al. 2008, 2016):
  2 building   where the dsm stands above the dem (surfaces.py's building cells)
  7 water      where most of the cell's Ground and Water points are Water (v1's class), or inside OpenStreetMap's
               water areas (water.py; Jacob, 18 Oct 2026: the lidar sees little of still water, and Willen Lake had
               come out 73% paved)
  5 grass      other ground whose single-return laser intensity is at or above the threshold
  1 paved      (UMEP's paved class, dark asphalt) other ground below it
At the laser's 1064 nm, grass returns far more than asphalt; the intensities of the survey's single-return ground
points split into two groups (paving about 75, grass about 260 on the CMK tiles), and the threshold is Otsu's (1979)
on all the tiles' cells together, so one survey has one threshold; OSM's water is left out of it (it is not ground). Pale concrete returns nearly as much as grass,
so some light paving reads as grass. A cell with no single-return ground point (under trees, mostly) takes the class
of the nearest cell that has one.
Writes surfaces/<tile>_lc.tif (uint8) and layers/landcover.json (the threshold and the shares).
usage: <heat venv python> -I landcover.py <repo root> [tile ids...]
"""
import json, sys
from pathlib import Path
import numpy as np
import rasterio
from scipy import ndimage as ndi

ROOT = Path(sys.argv[1]); H = ROOT / "data" / "mk" / "heat"; SURF = H / "surfaces"
ids = sys.argv[2:] or sorted(p.name[:-9] for p in SURF.glob("*_gint.tif"))
PAVED, BUILDING, GRASS, WATER = 1, 2, 5, 7
rd = lambda t, n: rasterio.open(SURF / f"{t}_{n}.tif").read(1)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import water  # noqa: E402
from rasterio.features import rasterize  # noqa: E402


def bounds_of(t):
    with rasterio.open(SURF / f"{t}_dsm.tif") as r:
        return tuple(r.bounds)


_b = [bounds_of(t) for t in ids]
WATER_U = water.polygons(H, (min(b[0] for b in _b), min(b[1] for b in _b), max(b[2] for b in _b), max(b[3] for b in _b)))


def osm_water(t):
    """the tile's cells inside OSM's water areas, on its own grid"""
    with rasterio.open(SURF / f"{t}_dsm.tif") as r:
        if WATER_U.is_empty:
            return np.zeros(r.shape, bool)
        return rasterize([(WATER_U, 1)], out_shape=r.shape, transform=r.transform, fill=0, dtype="uint8").astype(bool)

# one threshold for the survey: Otsu on every cell's intensity, all tiles together
hi = max(float(np.nanpercentile(rd(t, "gint"), 99.5)) for t in ids)
edges = np.linspace(0, hi, 257); hist = np.zeros(256)
for t in ids:
    g = rd(t, "gint"); hist += np.histogram(g[np.isfinite(g) & ~osm_water(t)], bins=edges)[0]
c = (edges[:-1] + edges[1:]) / 2; w0 = np.cumsum(hist); w1 = w0[-1] - w0; m0 = np.cumsum(hist * c)
thr = float(edges[1:][np.argmax(w0 * w1 * (m0 / np.maximum(w0, 1) - (m0[-1] - m0) / np.maximum(w1, 1)) ** 2)])
shares = {}
for t in ids:
    g, wat, dsm, dem = rd(t, "gint"), rd(t, "wat"), rd(t, "dsm"), rd(t, "dem")
    ground = np.where(np.isfinite(g), np.where(g >= thr, GRASS, PAVED), 0).astype(np.uint8)
    idx = ndi.distance_transform_edt(ground == 0, return_distances=False, return_indices=True)
    lc = ground[tuple(idx)]
    lc[(wat > 0.5) | osm_water(t)] = WATER
    lc[dsm > dem] = BUILDING
    src = rasterio.open(SURF / f"{t}_dsm.tif")
    prof = src.profile | {"dtype": "uint8", "nodata": None}
    with rasterio.open(SURF / f"{t}_lc.tif", "w", **prof) as o:
        o.write(lc, 1)
    shares[t] = {k: round(float(np.mean(lc == v)), 4) for k, v in (("paved", PAVED), ("building", BUILDING), ("grass", GRASS), ("water", WATER))}
json.dump({"threshold": thr, "tiles": shares}, open(H / "layers" / "landcover.json", "w"), indent=1)
tot = {k: round(float(np.mean([s[k] for s in shares.values()])), 3) for k in ("paved", "building", "grass", "water")}
print(f"Otsu threshold {thr:.0f} over {len(ids)} tiles; mean shares {tot}")
