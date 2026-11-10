"""The Met Office UKV 2 km forcing for tiles that have none yet (the borough's, 18 Oct 2026), as the city's was fetched:
Open-Meteo's Historical Forecast API, model ukmo_uk_deterministic_2km, 12-14 Aug 2026, UTC, wind in m/s, at each tile's
core centre (weather_ukv/query.txt holds the city's query). New tiles' answers are appended to ukv_2km_2026-08-12_14.json
and their points to tile_points.json, in the same order, so the existing tiles' forcing stays as it was. The 10 m wind
direction, which URock needs and the first fetch did not ask for, is fetched for every tile into
ukv_wind_direction_2026-08-12_14.json ({tile: {time, wind_direction_10m, wind_speed_10m}}).
usage: <heat venv python> -I ukv_fetch.py <repo root>
"""
import json, sys, time, urllib.parse, urllib.request
from pathlib import Path
from pyproj import Transformer

ROOT = Path(sys.argv[1]); H = ROOT / "data" / "mk" / "heat"; W = H / "weather_ukv"
API = "https://historical-forecast-api.open-meteo.com/v1/forecast"
COMMON = {"start_date": "2026-08-12", "end_date": "2026-08-14", "models": "ukmo_uk_deterministic_2km", "timezone": "UTC", "wind_speed_unit": "ms"}
VARS = "temperature_2m,relative_humidity_2m,wind_speed_10m,surface_pressure,shortwave_radiation,direct_radiation,diffuse_radiation,direct_normal_irradiance"
to_wgs = Transformer.from_crs(27700, 4326, always_xy=True).transform
pool = json.load(open(H / "rounds" / "pool.json"))["tiles"]
centre = {}
for t in pool:
    x0, y0, x1, y1 = t["core"]; lon, lat = to_wgs((x0 + x1) / 2, (y0 + y1) / 2); centre[t["id"]] = (round(lat, 5), round(lon, 5))


def get(points, hourly):
    """Open-Meteo's answers for these (lat, lon) points, in their order, 50 a request"""
    out = []
    for i in range(0, len(points), 50):
        chunk = points[i:i + 50]
        q = {**COMMON, "latitude": ",".join(str(p[0]) for p in chunk), "longitude": ",".join(str(p[1]) for p in chunk), "hourly": hourly}
        req = urllib.request.Request(API + "?" + urllib.parse.urlencode(q), headers={"User-Agent": "lidar-review/1.0 (research)"})
        r = json.load(urllib.request.urlopen(req, timeout=300))
        out += r if isinstance(r, list) else [r]
        time.sleep(2)
    return out


points = json.load(open(W / "tile_points.json"))
have = {p[0] for p in points}
new = [t for t in sorted(centre) if t not in have]
if new:
    ans = get([centre[t] for t in new], VARS)
    u = json.load(open(W / "ukv_2km_2026-08-12_14.json"))
    assert len(u) == len(points), "the forcing file and its points differ in length"
    u += ans; points += [[t, *centre[t]] for t in new]
    json.dump(u, open(W / "ukv_2km_2026-08-12_14.json", "w")); json.dump(points, open(W / "tile_points.json", "w"))
print(f"{len(new)} new tiles' forcing added ({len(points)} tiles)", flush=True)
ids = [p[0] for p in points]
d = get([(p[1], p[2]) for p in points], "wind_direction_10m,wind_speed_10m")
json.dump({t: {"time": a["hourly"]["time"], "wind_direction_10m": a["hourly"]["wind_direction_10m"], "wind_speed_10m": a["hourly"]["wind_speed_10m"]}
           for t, a in zip(ids, d)}, open(W / "ukv_wind_direction_2026-08-12_14.json", "w"))
print(f"wind direction for {len(ids)} tiles", flush=True)
