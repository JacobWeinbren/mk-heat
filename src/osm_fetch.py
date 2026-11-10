"""OpenStreetMap and the basemap for the area (area.py), as the city's were fetched on 18 Oct 2026 (the same queries, made
again over the borough; Jacob, 18 Oct 2026: "please do the full expansive greater MK definition"):
  osm/walk_now.json                 today's walking ways (footway, pedestrian, path, steps, cycleway, living_street,
                                    bridleway, and roads with a sidewalk tag)
  osm/walk_2021-01-17_body.json     the same as on 17 Jan 2021 (the survey's month)
  osm/roads_rail_2021-01-17.json    carriageways, railway land and railway lines on 17 Jan 2021
  osm/buildings_2021-01-17_geom.json, _ids.json   buildings on 17 Jan 2021 (outlines; ids)
  osm/bus_stops_now.json            today's bus stop nodes (their shelter tags, for shelters.py)
  basemap_mk.pmtiles                Protomaps' build of 17 Oct 2026, cut to the area and 45% round it, zooms up to 15
Over the area's box with 300 m round it (the crops' 100 m margin and more). A query the public Overpass server cannot
answer (a dated query can run out of its memory) is asked again in four quarters and the parts merged by id. One query
at a time, a minute apart. Earlier copies are kept in osm/before_borough/.
usage: <heat venv python> -I osm_fetch.py <repo root> [name ...]
"""
import json, shutil, subprocess, sys, time, urllib.parse, urllib.request
from pathlib import Path
from pyproj import Transformer

ROOT = Path(sys.argv[1]); H = ROOT / "data" / "mk" / "heat"; O = H / "osm"
sys.path.insert(0, str(Path(__file__).absolute().parent))
from area import area  # noqa: E402

OVERPASS = "https://overpass-api.de/api/interpreter"
UA = "lidar-review/1.0 (research; contact jacobweinbren)"
DATE = '[date:"2021-01-17T23:59:59Z"]'
WALK = 'way[highway~"^(footway|pedestrian|path|steps|cycleway|living_street|bridleway)$"]({bb});way[highway][sidewalk~"^(both|left|right|yes)$"]({bb});'
ROADS = ('way[highway~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|motorway_link|trunk_link|primary_link|'
         'secondary_link|tertiary_link|service|living_street|busway)$"]({bb});way[landuse=railway]({bb});way[railway~"^(rail|light_rail)$"]({bb});')
QUERIES = {
    "walk_now.json": ("[out:json][timeout:300];(" + WALK + ");out geom tags;"),
    "walk_2021-01-17_body.json": ("[out:json][timeout:300]" + DATE + ";(" + WALK + ");out geom tags;"),
    "roads_rail_2021-01-17.json": ("[out:json][timeout:300]" + DATE + ";(" + ROADS + ");out geom tags;"),
    "buildings_2021-01-17_geom.json": ("[out:json][timeout:300]" + DATE + ";(way[building]({bb});relation[building]({bb}););out geom;"),
    "buildings_2021-01-17_ids.json": ("[out:json][timeout:300]" + DATE + ";(way[building]({bb});relation[building]({bb}););out ids;"),
    "bus_stops_now.json": ('[out:json][timeout:120];(node["highway"="bus_stop"]({bb});node["public_transport"="platform"]["bus"="yes"]({bb}););out body;'),
}
x0, y0, x1, y1 = area(H).bounds
to_wgs = Transformer.from_crs(27700, 4326, always_xy=True).transform


def bbox(a, b, c, d, m=300):
    xs, ys = to_wgs([a - m, c + m, a - m, c + m], [b - m, b - m, d + m, d + m])
    return min(ys), min(xs), max(ys), max(xs)                  # south, west, north, east


def ask(q):
    req = urllib.request.Request(OVERPASS, data=urllib.parse.urlencode({"data": q}).encode(), headers={"User-Agent": UA, "Accept": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=420))
    if d.get("remark") and "error" in d["remark"].lower():
        raise RuntimeError(d["remark"][:200])
    return d


def fetch(name, q, box, depth=0):
    """the query over box; on failure, over its four quarters (to two levels), merged by type and id"""
    bb = "{:.5f},{:.5f},{:.5f},{:.5f}".format(*box)
    for wait in (0, 60, 120):
        time.sleep(wait)
        try:
            d = ask(q.format(bb=bb)); print(f"  {name} {bb}: {len(d['elements'])} elements", flush=True); return d
        except Exception as e:                                  # noqa: BLE001
            print(f"  {name} {bb}: {str(e)[:160]}", flush=True)
    if depth >= 2:
        raise SystemExit(f"{name}: no answer even in quarters")
    s, w, n, e = box; ms, mw = (s + n) / 2, (w + e) / 2
    parts = [fetch(name, q, b, depth + 1) for b in ((s, w, ms, mw), (s, mw, ms, e), (ms, w, n, mw), (ms, mw, n, e))]
    seen, els = set(), []
    for p in parts:
        for el in p["elements"]:
            if (el["type"], el["id"]) not in seen:
                seen.add((el["type"], el["id"])); els.append(el)
    return {**{k: v for k, v in parts[0].items() if k != "elements"}, "elements": els}


want = sys.argv[2:] or [*QUERIES, "basemap"]
(O / "before_borough").mkdir(exist_ok=True)
box = bbox(x0, y0, x1, y1)
for name in want:
    if name == "basemap":
        mx, my = (x1 - x0) * 0.45, (y1 - y0) * 0.45
        s, w, n, e = bbox(x0 - mx, y0 - my, x1 + mx, y1 + my, 0)
        if (H / "basemap_mk.pmtiles").exists() and not (O / "before_borough" / "basemap_mk.pmtiles").exists():
            shutil.copyfile(H / "basemap_mk.pmtiles", O / "before_borough" / "basemap_mk.pmtiles")
        subprocess.run(["pmtiles", "extract", "https://build.protomaps.com/20261017.pmtiles", str(H / "basemap_mk.pmtiles.part"),
                        f"--bbox={w:.6f},{s:.6f},{e:.6f},{n:.6f}", "--maxzoom=15"], check=True)
        (H / "basemap_mk.pmtiles.part").rename(H / "basemap_mk.pmtiles"); print("basemap", (H / "basemap_mk.pmtiles").stat().st_size, flush=True)
        continue
    if (O / name).exists() and not (O / "before_borough" / name).exists():
        shutil.copyfile(O / name, O / "before_borough" / name)
    d = fetch(name, QUERIES[name], box)
    (O / name).write_text(json.dumps(d))
    print(f"{name}: {len(d['elements'])} elements", flush=True)
    time.sleep(60)
