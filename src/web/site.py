"""The map's site build for Cloudflare Pages (Jacob, 18 Oct 2026: "can you do loads of cloudflare and site caching stuff
so the map loads and runs quicker"; "serve as much as you can via pmtiles"): every map layer as tiles from PMTiles
archives on R2 (bucket maps, at maps.weinbren.me), read in byte ranges, so a visitor fetches only the tiles in view;
Pages itself answers a byte-range request with the whole file (tested on mk-heat.pages.dev, 18 Oct 2026). The archives,
built in web/tiles/:
- basemap.pmtiles: out/basemap.txt's archive (basemap.py) as bytes;
- features.pmtiles: the footpaths, stops and greyed areas as vector tiles (tippecanoe), each with its day as
  the artifact's page builds it (v, a character an hour, value + 35; d, its hours at 38 °C or more; v_NAME and d_NAME
  where a scenario changes them) and a stop's name, place and shelter; every feature at every zoom from 8 (the page's
  least zoom on a phone) to 15, from which MapLibre draws the closer zooms;
- trees.pmtiles: the plans' new trees, from the zoom the page draws them at to 15;
- ground/<name>.pmtiles: each ground image (package.py's pieces, already Web Mercator) as 512 px PNG tiles, nearest, so
  the map keeps the classes the chart counts, from zoom 8 to the zoom whose pixel is nearest the image's own;
and on the site itself: glyphs/<face>_<range>.pbf (the faces and ranges the labels use), vendor/ (MapLibre GL JS 4.7.1 and PMTiles 3.2.1 as
  jsDelivr serves them), _headers: every file the page asks for by its content's hash is kept a year, the page itself
  is checked each time;
tiles/index.json records each archive's address; build.py then writes site/index.html with them.
usage: <heat venv python> -I site.py <repo root>
"""
import io, json, math, re, shutil, subprocess, sys, tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import Writer

ROOT = Path(sys.argv[1])
W = Path(__file__).resolve().parent
OUT, SITE, TILES = W / "out", W / "site", W / "tiles"
D = json.loads((OUT / "data.json").read_text())
SITE.mkdir(exist_ok=True)
(TILES / "ground").mkdir(parents=True, exist_ok=True)
R = 6378137.0
HALF = math.pi * R                                   # Web Mercator's half width, m
TILE = 512
ZMIN = 8                                             # the page's least zoom on a phone (fit less one) is 8.9


def lonlat(x, y):
    return x / R * 180 / math.pi, (2 * math.atan(math.exp(y / R)) - math.pi / 2) * 180 / math.pi


def merc(lon, lat):
    return lon * math.pi / 180 * R, R * math.log(math.tan(math.pi / 4 + lat * math.pi / 360))


def header(tile_type, compression, zmin, zmax, bounds):
    w, s, e, n = bounds
    return {"version": 3, "tile_type": tile_type, "tile_compression": compression, "min_zoom": zmin, "max_zoom": zmax,
            "min_lon_e7": int(w * 1e7), "min_lat_e7": int(s * 1e7), "max_lon_e7": int(e * 1e7), "max_lat_e7": int(n * 1e7),
            "center_zoom": (zmin + zmax) // 2, "center_lon_e7": int((w + e) / 2 * 1e7), "center_lat_e7": int((s + n) / 2 * 1e7)}


# the basemap and the label glyphs
import base64
(TILES / "basemap.pmtiles").write_bytes(base64.b64decode((OUT / "basemap.txt").read_text()))
faces = set(re.findall(r"'text-font': \['([^']+)'\]", (W / "template.html").read_text()))
ranges = set(json.loads((OUT / "glyph_ranges.json").read_text()))
shutil.rmtree(SITE / "glyphs", ignore_errors=True); (SITE / "glyphs").mkdir()
for f in sorted((ROOT / "data" / "mk" / "heat" / "glyphs").glob("*.pbf")):
    stack, rng = f.stem.rsplit("_", 1)
    if stack.replace("_", " ") in faces and rng in ranges:
        shutil.copyfile(f, SITE / "glyphs" / f.name)
(SITE / "vendor").mkdir(exist_ok=True)
for f in ("maplibre-gl-4.7.1.js", "pmtiles-3.2.1.js"):
    shutil.copyfile(W / "vendor" / f, SITE / "vendor" / f)

# the model's features as vector tiles
TREE_Z = int(re.search(r"id: 'trees'[^\n]*?minzoom: (\d+)", (W / "template.html").read_text()).group(1))
HOT = D["classes"][D["hot"]]["lo"]
enc = lambda v: "".join(chr(x + 35) for x in v)
hot = lambda v: sum(1 for x in v if x >= HOT)
SC = D.get("scenarios", {})


def day(vals, i, kind):
    """a feature's day as it was and, where a scenario changes it, the scenario's"""
    o = {"v": enc(vals), "d": hot(vals)}
    for nm, S in SC.items():
        w = S[kind].get(str(i))
        if w is not None and w != vals:
            o["v_" + nm], o["d_" + nm] = enc(w), hot(w)
    return o


with tempfile.TemporaryDirectory(dir=W) as tmp:
    tmp = Path(tmp)
    with open(tmp / "paths.geojsonl", "w") as f:
        for i, (c, vals, g) in enumerate(D["paths"]):
            pts, x, y = [], 0, 0
            for k in range(0, len(c), 2):
                x += c[k]; y += c[k + 1]; pts.append([x / 1e5, y / 1e5])
            f.write(json.dumps({"type": "Feature", "geometry": {"type": "LineString", "coordinates": pts},
                                "properties": {"g": g, **day(vals, i, "paths")}}, separators=(",", ":")) + "\n")
    with open(tmp / "stops.geojsonl", "w") as f:
        for i, s_ in enumerate(D["stops"]):
            pr = {"g": s_["g"], "n": s_["n"], "m": s_["m"], **({"sh": 1} if s_.get("sh") else {}), **day(s_["v"], i, "stops")}
            f.write(json.dumps({"type": "Feature", "geometry": {"type": "Point", "coordinates": [s_["x"], s_["y"]]}, "properties": pr},
                               separators=(",", ":")) + "\n")
    with open(tmp / "grey.geojsonl", "w") as f:
        for ft in D["grey"]["features"]:
            f.write(json.dumps({"type": "Feature", "geometry": ft["geometry"], "properties": {}}, separators=(",", ":")) + "\n")
    with open(tmp / "trees.geojsonl", "w") as f:
        for nm, S in SC.items():
            for lon, lat in S.get("trees", []):
                f.write(json.dumps({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": {"s": nm}},
                                   separators=(",", ":")) + "\n")
    # every feature at every zoom: no dropping (-r1), no feature or tile size limits
    subprocess.run(["tippecanoe", "-o", str(TILES / "features.pmtiles"), "--force", "--quiet", f"-Z{ZMIN}", "-z15", "-r1",
                    "--no-feature-limit", "--no-tile-size-limit", "--attribution", D.get("credits", ""),
                    *[a for nm in ("paths", "stops", "grey") for a in ("-L", f"{nm}:{tmp / (nm + '.geojsonl')}")]], check=True)
    # the plans' new trees in an archive of their own, from the zoom the page draws them at (its trees layer's minzoom):
    # in the footpaths' archive they were in every tile from zoom 8, half the features of the opening view's tiles
    # (49,652 of 96,458 in its largest, 19 Oct 2026), fetched by every visitor and never drawn below 15
    subprocess.run(["tippecanoe", "-o", str(TILES / "trees.pmtiles"), "--force", "--quiet", f"-Z{TREE_Z}", "-z15", "-r1",
                    "--no-feature-limit", "--no-tile-size-limit", "-L", f"trees:{tmp / 'trees.geojsonl'}"], check=True)
print("features", (TILES / "features.pmtiles").stat().st_size, "trees", (TILES / "trees.pmtiles").stat().st_size, flush=True)

# the ground images as raster tiles
pieces = {p["id"]: p for p in D["pieces"]}
names = sorted({f.stem.rsplit("_", 1)[0] for f in (OUT / "ground").glob("*.png")})
for old in (TILES / "ground").glob("*.pmtiles"):
    if old.stem not in names:
        old.unlink()
total, zooms = 0, set()
for name in names:
    ims = {pid: Image.open(OUT / "ground" / f"{name}_{pid}.png") for pid in pieces}
    pal = ims[min(ims)].getpalette()
    # the pieces on one grid: piece "ji" is row j, column i
    xl, yt = merc(*pieces[min(pieces)]["corners"][0]); xr, _ = merc(*pieces[min(pieces)]["corners"][1])
    res = (xr - xl) / ims[min(ims)].width
    widths = {i: ims[f"0{i}"].width for i in sorted({k[1] for k in pieces})}
    heights = {j: ims[f"{j}0"].height for j in sorted({k[0] for k in pieces})}
    canvas = np.full((sum(heights.values()), sum(widths.values())), 255, np.uint8)
    r0 = 0
    for j in sorted(heights):
        c0 = 0
        for i in sorted(widths):
            a = np.asarray(ims[f"{j}{i}"]); canvas[r0:r0 + a.shape[0], c0:c0 + a.shape[1]] = a; c0 += widths[i]
        r0 += heights[j]
    x0, y0 = xl, yt
    x1, y1 = x0 + canvas.shape[1] * res, y0 - canvas.shape[0] * res
    zmax = round(math.log2(2 * HALF / (TILE * res)))          # the zoom whose pixel is nearest the image's own
    zooms.add(zmax)
    path = TILES / "ground" / f"{name}.pmtiles"
    with open(path, "wb") as f:
        wr = Writer(f); n = 0
        for z in range(ZMIN, zmax + 1):
            span = 2 * HALF / 2 ** z; px = span / TILE
            tx0, tx1 = int((x0 + HALF) // span), int((x1 + HALF) // span)
            ty0, ty1 = int((HALF - y0) // span), int((HALF - y1) // span)
            for ty in range(ty0, ty1 + 1):
                ys = HALF - ty * span - (np.arange(TILE) + 0.5) * px
                rows = np.floor((y0 - ys) / res).astype(np.int64); rok = (rows >= 0) & (rows < canvas.shape[0])
                for tx in range(tx0, tx1 + 1):
                    xs = tx * span - HALF + (np.arange(TILE) + 0.5) * px
                    cols = np.floor((xs - x0) / res).astype(np.int64); cok = (cols >= 0) & (cols < canvas.shape[1])
                    if not rok.any() or not cok.any():
                        continue
                    t = np.full((TILE, TILE), 255, np.uint8)
                    t[np.ix_(rok, cok)] = canvas[np.ix_(rows[rok], cols[cok])]
                    if (t == 255).all():
                        continue
                    im = Image.fromarray(t, "P"); im.putpalette(pal)
                    b = io.BytesIO(); im.save(b, "PNG", transparency=255, compress_level=9)
                    wr.write_tile(zxy_to_tileid(z, tx, ty), b.getvalue()); n += 1
        w_, s_ = lonlat(x0, y1); e_, n_ = lonlat(x1, y0); ground_bounds = (w_, s_, e_, n_)
        wr.finalize(header(TileType.PNG, Compression.NONE, ZMIN, zmax, (w_, s_, e_, n_)), {"name": name})
    total += path.stat().st_size
    print(f"ground {name}: {n} tiles, zooms {ZMIN}-{zmax}, {path.stat().st_size:,} bytes", flush=True)
print(f"ground: {len(names)} archives, {total:,} bytes", flush=True)

# the archives on R2 (Jacob, 18 Oct 2026: "we can use a custom domain and r2!"; "I am already using r2 to serve pmtiles"):
# bucket maps, served with byte ranges at maps.weinbren.me (its CORS rules admit *.pages.dev and expose Content-Range
# and ETag), each object named by its archive's hash, so a year's caching is safe and a new build fetches only what
# changed; objects already there are not sent again, and an earlier build's are left in place
import hashlib
BUCKET, PREFIX, HOST = "maps", "mk-heat", "https://maps.weinbren.me"
ACCOUNT = "148ef3a765d15218b5651d5de86b92db"          # Jacob's own Cloudflare account (not the shared one)
sent_f = TILES / "uploaded.json"
sent = json.loads(sent_f.read_text()) if sent_f.exists() else {}
index = {}
for key, arc in [("basemap", TILES / "basemap.pmtiles"), ("features", TILES / "features.pmtiles"), ("trees", TILES / "trees.pmtiles"),
                 *[(f"ground/{f.stem}", f) for f in sorted((TILES / "ground").glob("*.pmtiles"))]]:
    obj = f"{PREFIX}/{key}.{hashlib.sha1(arc.read_bytes()).hexdigest()[:12]}.pmtiles"
    if obj not in sent:
        subprocess.run(["wrangler", "r2", "object", "put", f"{BUCKET}/{obj}", f"--file={arc}", "--remote",
                        "--content-type=application/octet-stream", "--cache-control=public, max-age=31536000, immutable"],
                       check=True, capture_output=True, env={**__import__("os").environ, "CLOUDFLARE_ACCOUNT_ID": ACCOUNT})
        sent[obj] = arc.stat().st_size; sent_f.write_text(json.dumps(sent, indent=1))
    index[key] = f"{HOST}/{obj}"
# the ground images' zooms, so the page can name their tiles without reading each archive's header first
assert len(zooms) == 1, f"the ground images' zooms differ: {zooms}"
index["_ground"] = {"minzoom": ZMIN, "maxzoom": zooms.pop(), "bounds": [round(v, 6) for v in ground_bounds]}
index["_trees"] = {"minzoom": TREE_Z, "maxzoom": 15}
(TILES / "index.json").write_text(json.dumps(index, indent=1))
print(f"tiles: {len(index)} archives on R2 ({BUCKET}/{PREFIX}/)", flush=True)
for old in ("basemap.pmtiles", "features.pmtiles"):        # the archives live on R2, not on the site
    (SITE / old).unlink(missing_ok=True)
for old in ("ground", "v", "r"):
    shutil.rmtree(SITE / old, ignore_errors=True)
# caching: a year for every file the page asks for by its hash, the page itself checked each time
YEAR = "Cache-Control: public, max-age=31536000, immutable"
(SITE / "_headers").write_text("\n".join([
    "/", "  Cache-Control: public, max-age=0, must-revalidate", "/index.html", "  Cache-Control: public, max-age=0, must-revalidate",
    *[ln for p in ("/meta.json", "/page.js", "/glyphs/*", "/vendor/*") for ln in (p, "  " + YEAR)],
    "/*", "  X-Content-Type-Options: nosniff", ""]))
subprocess.run(["python3", str(W / "build.py")], check=True)
