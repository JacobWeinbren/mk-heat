"""Bus shelters as SOLWEIG sees them (Jacob, 18 Oct 2026: "Can we make it 0 bus stops"). Shelter roofs are too small
for the 2021 lidar to hold (about 1.5 x 3 m), so a stop OpenStreetMap tags shelter=yes was modelled in the open; 65 of
central MK's 146 modelled stops have one. A shelter is modelled as a roof over the stop's waiting area (the 3 x 3 m the
page's stop figures average; a shelter's own plan is smaller, about 2.5 x 1.6 m), as a 2.5 m canopy in the canopy model (solweig's vegetation shading, leaf-on transmissivity
0.03), never on a building cell.
  existing  the stops OSM tags shelter=yes today (bus_stops_now.json, Overpass 18 Oct 2026, joined to NaPTAN by ATCO
            code): writes layers/shelters_cdsm/<tile>.npy for every crop a roof falls in (utci.py adds it to every
            run) and layers/shelters.json (the ATCO codes, for the page)
  add NAME  a new shelter at every stop the scenario NAME still has at 38 C UTCI or more in some hour (utci_NAME/, the
            stop's 3 x 3 m mean as the page counts it) that has none: adds the roofs to layers/NAME_cdsm/<tile>.npy,
            deletes those tiles' utci_NAME files so utci.py runs them again, and records them in layers/NAME.json
usage: <heat venv python> -I shelters.py <repo root> existing|add NAME
"""
import csv, json, sys
from pathlib import Path
import numpy as np
import rasterio

ROOT = Path(sys.argv[1]); STEP = sys.argv[2]
H = ROOT / "data" / "mk" / "heat"; L = H / "layers"
pool = {t["id"]: t for t in json.load(open(H / "rounds" / "pool.json"))["tiles"]}
ROOF_H = 2.5                          # a shelter's overall height, m (Procity square post shelter 2,548 mm; Jersey's
                                      # Bagatelle Road and Midland Stores shelters 2,500 mm, as specified)
HOT = 38.0
nap = [r for r in csv.DictReader(open(H / "naptan" / "naptan_049.csv")) if r["StopType"] == "BCT" and r["Status"] == "active"]
osm = {e["tags"]["naptan:AtcoCode"]: e["tags"].get("shelter") for e in json.load(open(H / "osm" / "bus_stops_now.json"))["elements"]
       if e["tags"].get("naptan:AtcoCode")}


def put(stops, folder):
    """a roof over each stop's 3 x 3 m in every crop it falls in, kept where a crop's file already has more"""
    folder.mkdir(exist_ok=True); n = 0
    for t, pt in pool.items():
        bx0, by0, bx1, by1 = pt["bounds"]
        here = [(e, nn) for e, nn in stops if bx0 <= e < bx1 and by0 <= nn < by1]
        if not here or not (H / "surfaces" / f"{t}_dsm.tif").exists():
            continue
        f = folder / f"{t}.npy"
        a = np.load(f) if f.exists() else np.zeros((int(by1 - by0), int(bx1 - bx0)), np.float32)
        dsm = rasterio.open(H / "surfaces" / f"{t}_dsm.tif").read(1); dem = rasterio.open(H / "surfaces" / f"{t}_dem.tif").read(1)
        for e, nn in here:
            r0, c0 = int(by1 - 1 - nn), int(e - bx0)
            sl = (slice(max(r0 - 1, 0), r0 + 2), slice(max(c0 - 1, 0), c0 + 2))
            a[sl] = np.where(dsm[sl] > dem[sl], a[sl], np.maximum(a[sl], ROOF_H))     # never on a building cell
        np.save(f, a); n += 1
    return n


if STEP == "existing":
    have = [(float(r["Easting"]), float(r["Northing"]), r["ATCOCode"]) for r in nap if osm.get(r["ATCOCode"]) == "yes"]
    n = put([(e, nn) for e, nn, _ in have], L / "shelters_cdsm")
    json.dump({"source": "OpenStreetMap shelter=yes (Overpass, 18 Oct 2026), joined to NaPTAN by ATCO code", "roof_m": ROOF_H,
               "atco": sorted(a for _, _, a in have)}, open(L / "shelters.json", "w"))
    print(f"{len(have)} stops with a shelter in OSM; roofs in {n} crops")

elif STEP == "add":
    name = sys.argv[3]
    sheltered = set(json.load(open(L / "shelters.json"))["atco"])
    # the scenario's shelters placed in an earlier round (a later round adds to them)
    placed = {s_["atco"] for s_ in json.load(open(L / f"{name}.json")).get("new_shelters", [])}
    new, tiles_hit = [], set()
    for r in nap:
        if r["ATCOCode"] in sheltered or r["ATCOCode"] in placed:
            continue
        e, nn = float(r["Easting"]), float(r["Northing"])
        for t, pt in pool.items():
            cx0, cy0, cx1, cy1 = pt["core"]
            if not (cx0 <= e < cx1 and cy0 <= nn < cy1):
                continue
            f = H / f"utci_{name}" / f"{t}.npz"
            if not f.exists():
                f = H / "utci" / f"{t}.npz"           # no new tree reached this tile: the baseline stands
            if not f.exists():
                break
            with np.load(f) as z:
                u = z["utci"] / 10
            r0, c0 = int(cy1 - 1 - nn), int(e - cx0)
            mean = u[:, max(r0 - 1, 0):r0 + 2, max(c0 - 1, 0):c0 + 2].mean(axis=(1, 2))
            if (mean >= HOT).any():
                new.append((e, nn, r["ATCOCode"]))
            break
    n = put([(e, nn) for e, nn, _ in new], L / f"{name}_cdsm")
    for t, pt in pool.items():                         # their tiles run again with the roofs
        bx0, by0, bx1, by1 = pt["bounds"]
        if any(bx0 <= e < bx1 and by0 <= nn < by1 for e, nn, _ in new):
            (H / f"utci_{name}" / f"{t}.npz").unlink(missing_ok=True); tiles_hit.add(t)
    tj = json.load(open(L / f"{name}.json"))
    pos = {r["ATCOCode"]: (float(r["Easting"]), float(r["Northing"])) for r in nap}
    tj["new_shelters"] = [{"atco": a, "x": pos[a][0], "y": pos[a][1]} for a in sorted(placed)] + [{"atco": a, "x": e, "y": nn} for e, nn, a in new]
    json.dump(tj, open(L / f"{name}.json", "w"))
    print(f"{len(placed)} placed before; {len(new)} new shelters at stops still at {HOT:g} C or more; roofs in {n} crops; "
          f"{len(tiles_hit)} tiles to run again")
