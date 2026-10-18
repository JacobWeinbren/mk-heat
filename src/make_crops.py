"""Milton Keynes for the heat map: 1 km cores with the England pool's 100 m margin (pool.json's crops), cut from the
National Lidar Programme's 5 km zips (fetch_lidar.py: data/mk/nlp2021, survey P_10737, 15 Dec 2020 - 17 Jan 2021, and
data/mk/nlp2020, survey P_10738, 29 Jan - 6 Mar 2020, for the borough's north), for every core that meets the area
(area.py: the City of Milton Keynes) within that margin. Writes data/mk/heat/crops/<id>.laz and a pool.json in the
shape round_common expects, for a side rounds folder (ROUNDS_DIR) so the England pool is untouched. A crop's flight
is its core's survey (5 km squares are whole kilometres, so a core lies in one; its margin may reach the other's).

Until 18 Oct 2026 the city was the ONS 2022 built-up areas of Milton Keynes, Bletchley, Newport Pagnell, Wavendon and
Woburn Sands (Jacob, 18 Oct 2026: "bletchley has some tree-less areas"). A crop already made is kept, and pool.json
gains only the new ones; only the zips that reach a new crop are read.

usage: python -I make_crops.py <repo root>
"""
import json, sys, tempfile, zipfile
from pathlib import Path
import laspy
import numpy as np
from shapely.geometry import box, shape

ROOT = Path(sys.argv[1])
MK = ROOT / "data" / "mk"
OUT = MK / "heat" / "crops"; OUT.mkdir(parents=True, exist_ok=True)
RD = MK / "heat" / "rounds"; RD.mkdir(parents=True, exist_ok=True)
MARGIN = 100.0                                   # the England pool's crop margin (pool.json bounds - core)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from area import area  # noqa: E402
bua = area(MK / "heat")
SURVEY = {"nlp2021": ("P_10737", "2021", "2020-12-15", "survey P_10737 (15 Dec 2020 - 17 Jan 2021)"),
          "nlp2020": ("P_10738", "2020", "2020-01-29", "survey P_10738 (29 Jan - 6 Mar 2020)")}
old = {t["id"]: t for t in json.load(open(RD / "pool.json"))["tiles"]} if (RD / "pool.json").exists() else {}
zips = sorted(z for d in SURVEY for z in (MK / d).glob("SP*.zip"))
of_square = {z.stem: z.parent.name for z in zips}           # a 5 km square's survey folder
cover = [(int(z.stem[2:4]) * 1000 + 400000, int(z.stem[4:6]) * 1000 + 200000) for z in zips]   # SP8540 -> (480000, 240000)
cores = []
for x0, y0 in cover:
    for dx in range(0, 5000, 1000):
        for dy in range(0, 5000, 1000):
            c = (x0 + dx, y0 + dy, x0 + dx + 1000, y0 + dy + 1000)
            if box(*c).buffer(MARGIN).intersects(bua):
                cores.append(c)
cores = sorted(set(cores))
print(f"{len(cores)} cores meet the built-up area")
square = lambda c: f"SP{(c[0] - 400000) // 5000 * 5:02d}{(c[1] - 200000) // 5000 * 5:02d}"
ids = [f"SP{(c[0] - 400000) // 1000:02d}{(c[1] - 200000) // 1000:02d}_mk{SURVEY[of_square[square(c)]][1]}" for c in cores]
keep = [(i, c) for i, c in zip(ids, cores) if i not in old]
ids, cores = [i for i, _ in keep], [c for _, c in keep]
print(f"{len(ids)} new cores to cut ({len(old)} already in the pool)", flush=True)
need = [box(*c).buffer(MARGIN) for c in cores]
zips = [z for z in zips if any(box(x0, y0, x0 + 5000, y0 + 5000).intersects(n) for n in need
                               for x0, y0 in [(int(z.stem[2:4]) * 1000 + 400000, int(z.stem[4:6]) * 1000 + 200000)])]
print(f"reading {len(zips)} zips: {', '.join(z.parent.name + '/' + z.name for z in zips)}", flush=True)
writers, hdr0 = {}, None
stats = {i: {"n": 0, "core": 0, "first_core": 0, "t0": None, "t1": None} for i in ids}
with tempfile.TemporaryDirectory(dir=str(MK / "heat")) as tmp:
    for z in zips:
        with zipfile.ZipFile(z) as zf:
            name = [n for n in zf.namelist() if n.endswith(".laz")][0]
            zf.extract(name, tmp)
        src = Path(tmp) / name
        def chunks():
            # the parallel LAZ reader failed once mid-run on this survey ("no chunks available in chunk table");
            # the same file reads cleanly on retry, so a failed file is read again with the single-thread reader
            for backend in (laspy.LazBackend.LazrsParallel, laspy.LazBackend.Lazrs):
                done = 0
                try:
                    with laspy.open(src, laz_backend=backend) as rr:
                        for ch in rr.chunk_iterator(2_000_000):
                            done += 1
                            yield rr.header, ch
                    return
                except Exception as e:
                    if done:
                        raise
                    print("retry", z.name, backend, e, flush=True)
            raise RuntimeError(f"{z.name}: unreadable")
        if True:
            for rh, ch in chunks():
                r = type("R", (), {"header": rh})
                x, y = np.asarray(ch.x), np.asarray(ch.y)
                for i, c in zip(ids, cores):
                    m = (x >= c[0] - MARGIN) & (x < c[2] + MARGIN) & (y >= c[1] - MARGIN) & (y < c[3] + MARGIN)
                    if not m.any():
                        continue
                    if i not in writers:
                        h = laspy.LasHeader(point_format=r.header.point_format, version=r.header.version)
                        h.scales, h.offsets = r.header.scales, r.header.offsets
                        writers[i] = laspy.open(OUT / f"{i}.laz", mode="w", header=h)
                    sub = ch[m]
                    writers[i].write_points(sub)
                    s = stats[i]; s["n"] += int(m.sum())
                    k = (x[m] >= c[0]) & (x[m] < c[2]) & (y[m] >= c[1]) & (y[m] < c[3])
                    s["core"] += int(k.sum()); s["first_core"] += int((k & (np.asarray(sub.return_number) == 1)).sum())
        src.unlink()
        print("done", z.name, flush=True)
for w in writers.values():
    w.close()
tiles = []
for i, c in zip(ids, cores):
    if not (OUT / f"{i}.laz").exists() or stats[i]["core"] == 0:
        continue
    s = stats[i]; sv, yr, flown, flown_from = SURVEY[of_square[square(c)]]
    tiles.append({"bounds": [c[0] - MARGIN, c[1] - MARGIN, c[2] + MARGIN, c[3] + MARGIN], "context": [], "core": list(c),
                  "density_first_returns_per_m2": round(s["first_core"] / 1e6, 3), "file": str((OUT / f"{i}.laz").relative_to(ROOT)),
                  "flown": flown, "flown_from": flown_from, "grouping_gap_m": 1.25,
                  "id": i, "name": i, "origin": [float(c[0]), float(c[1]), 0.0], "place": "urban", "points_core": s["core"],
                  "set": "review", "size": [1000.0, 1000.0], "source": "mk_heat", "survey": sv, "year": yr})
tiles = list(old.values()) + tiles
json.dump({"version": 1, "made": "2026-10-18", "seed": 20260930, "sources": {"mk_heat": "data/mk/nlp2021 (NLP 2021, P_10737) and data/mk/nlp2020 (NLP 2020, P_10738)"},
           "tiles": tiles}, open(RD / "pool.json", "w"), indent=1)
print(f"{len(tiles)} crops, {sum(t['points_core'] for t in tiles):,} core points; pool at {RD / 'pool.json'}")
