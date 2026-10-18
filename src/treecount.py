"""Trees and tall shrubs in the modelled area, from the 2021 lidar's canopy height model (Jacob, 18 Oct 2026: "How
many trees are in mk atm roughly"): treetops are local maxima of the canopy model (smoothed by a 1 m Gaussian) taller
than 2.5 m (the VOM's floor), each sought in a window as wide as the crown a tree of that height has (Popescu & Wynne
2004, deciduous: crown width = 3.09632 + 0.00895 h^2 m), in five height bands. A leaf-off flight and dense shrub belts
make it a rough count. Over the built-up area (ONS 2022, holes filled) and in all; canopy over 2.5 m as a share too.
Writes layers/treecount.json.
usage: <heat venv python> -I treecount.py <repo root>
"""
import json, sys
from pathlib import Path
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from scipy import ndimage as ndi
from shapely.geometry import shape, Polygon
from shapely.ops import unary_union

ROOT = Path(sys.argv[1]); H = ROOT / "data" / "mk" / "heat"
pool = {t["id"]: t for t in json.load(open(H / "rounds" / "pool.json"))["tiles"]}
CITY = {"Milton Keynes", "Bletchley", "Newport Pagnell", "Wavendon", "Woburn Sands"}
g = json.load(open(H.parent / "extent" / "bua22_mk_area_27700.geojson"))
bua = unary_union([shape(f["geometry"]) for f in g["features"] if f["properties"]["BUA22NM"] in CITY])
bua = unary_union([Polygon(q.exterior) for q in (bua.geoms if hasattr(bua, "geoms") else [bua])])
tiles = sorted(p.stem for p in (H / "utci").glob("*.npz"))
BANDS = [(2.5, 5), (5, 10), (10, 15), (15, 20), (20, 60)]
n_all = n_bua = 0; a_all = a_bua = 0.0; c_all = c_bua = 0.0
for t in tiles:
    cx0, cy0, cx1, cy1 = pool[t]["core"]; bx0, by0, bx1, by1 = pool[t]["bounds"]
    cd = rasterio.open(H / "surfaces" / f"{t}_cdsm.tif").read(1).astype(np.float32)
    sm = ndi.gaussian_filter(cd, 1.0); tops = np.zeros(cd.shape, bool)
    for h0, h1 in BANDS:
        k = max(3, int(round(3.09632 + 0.00895 * ((h0 + h1) / 2) ** 2)) | 1)
        tops |= (sm == ndi.maximum_filter(sm, size=k)) & (sm >= h0) & (sm < h1) & (cd >= 2.5)
    sl = (slice(int(by1 - cy1), int(by1 - cy0)), slice(int(cx0 - bx0), int(cx1 - bx0)))
    tp, cc = tops[sl], cd[sl] >= 2.5
    inb = rasterize([(bua, 1)], out_shape=tp.shape, transform=from_origin(cx0, cy1, 1, 1), fill=0, dtype="uint8").astype(bool)
    n_all += int(tp.sum()); n_bua += int((tp & inb).sum()); a_all += tp.size / 1e6; a_bua += inb.sum() / 1e6
    c_all += float(cc.sum()) / 1e6; c_bua += float((cc & inb).sum()) / 1e6
res = {"tiles": len(tiles), "treetops": n_all, "area_km2": round(a_all, 2), "treetops_in_built_up_area": n_bua,
       "built_up_km2": round(a_bua, 2), "per_km2_built_up": round(n_bua / max(a_bua, 1e-9)),
       "canopy_over_2_5m_share": round(c_all / a_all, 4), "canopy_over_2_5m_share_built_up": round(c_bua / max(a_bua, 1e-9), 4),
       "rule": "local maxima over 2.5 m, window the Popescu & Wynne (2004) deciduous crown width for the height band"}
json.dump(res, open(H / "layers" / "treecount.json", "w"), indent=1)
print(json.dumps(res, indent=1))
