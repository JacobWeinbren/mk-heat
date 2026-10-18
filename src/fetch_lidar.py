"""The National Lidar Programme point clouds for the City of Milton Keynes (Jacob, 18 Oct 2026: "please do the full
expansive greater MK definition"; he chose the whole borough, LAD E06000042, data/mk/extent/lad24_milton_keynes_27700.geojson).
Every 5 km OS square that meets the borough (with the crops' 100 m margin) and has borough land in it, from the survey
of winter 2020-21 the city already uses (P_10737, 15 Dec 2020 - 17 Jan 2021) where it flew, else from P_10738
(29 Jan - 6 Mar 2020, the borough's north: Olney, Lavendon, Sherington), both winter flights, read from the EA's survey
index (data/experiments/vom_compare/nlp_index.json). Zips go to data/mk/nlp<year>/<tile>.zip through fetch_ea.fetch_url
(one EA request a minute across every process); a zip already there is kept, and each is checked to hold its survey.
usage: pipeline/.venv/bin/python -I data/experiments/mk_heat/fetch_lidar.py <repo root> [--dry-run]
"""
import json, sys, zipfile
from pathlib import Path

ROOT = Path(sys.argv[1])
sys.path.insert(0, str(ROOT / "pipeline"))
from fetch_ea import fetch_url  # noqa: E402
from sample_ea import KEY, TILE_URL  # noqa: E402
from shapely.geometry import box, shape  # noqa: E402

SURVEYS = {"P_10737": 2021, "P_10738": 2020}            # in order of preference
lad = shape(json.load(open(ROOT / "data" / "mk" / "extent" / "lad24_milton_keynes_27700.geojson"))["features"][0]["geometry"])
rows = json.load(open(ROOT / "data" / "experiments" / "vom_compare" / "nlp_index.json"))
rows = rows["rows"] if isinstance(rows, dict) else rows
have = {(r["tilename"], r["polygon_id"]) for r in rows}
x0, y0, x1, y1 = (int(v // 5000 * 5000) for v in lad.bounds)
plan = []
for x in range(x0, x1 + 1, 5000):
    for y in range(y0, y1 + 1, 5000):
        b = box(x, y, x + 5000, y + 5000)
        if not b.buffer(100).intersects(lad) or b.intersection(lad).area == 0:
            continue
        tile = f"SP{(x - 400000) // 1000:02d}{(y - 200000) // 1000:02d}"
        survey = next((s for s in SURVEYS if (tile, s) in have), None)
        if survey is None:
            print(f"{tile}: no survey of {sorted(SURVEYS)} in the index", flush=True); continue
        plan.append((tile, survey, SURVEYS[survey]))
print(f"{len(plan)} squares: " + ", ".join(f"{t} ({s})" for t, s, _ in plan), flush=True)
if "--dry-run" in sys.argv:
    sys.exit(0)
# the catalogue's two download addresses (sample_ea's backend one, which served the 2021 zips, and download_ea's): the
# 2020 survey's zips answered 404 at the first on 18 Oct 2026 though the catalogue lists them
URLS = (TILE_URL, "https://environment.data.gov.uk/tiles/collections/survey/{product}/{year}/{res}/{tile}")
failed = []
for tile, survey, year in plan:
    dst = ROOT / "data" / "mk" / f"nlp{year}" / f"{tile}.zip"
    for base in URLS:
        if dst.exists():
            break
        try:
            fetch_url(base.format(product="national_lidar_programme_point_cloud", year=year, res="1", tile=tile) + f"?subscription-key={KEY}",
                      dst, attempts=3, timeout=1800)
        except Exception as e:                                  # noqa: BLE001 - the next address, then the next square
            print(f"{tile} {survey}: {base.split('/')[2]}{'/backend' if 'backend' in base else ''}: {e!r}"[:300], flush=True)
    if not dst.exists():
        failed.append(tile); continue
    with zipfile.ZipFile(dst) as zf:
        laz = [n for n in zf.namelist() if n.endswith(".laz")]
    ok = any(survey in n for n in laz)
    print(f"{tile} {survey}: {dst.stat().st_size:,} bytes, {laz}{'' if ok else '  NOT THIS SURVEY'}", flush=True)
print(f"done; {len(failed)} squares not fetched: {', '.join(failed) or 'none'}", flush=True)
