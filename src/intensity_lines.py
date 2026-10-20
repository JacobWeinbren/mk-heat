"""Every flight line's intensity on one scale, for landcover.py's grass and paving (20 Oct 2026; Jacob chose this for the
line across the map along northing 250,000, where the survey P_10737 meets P_10738: "Option 1 sounds good").
The intensities of the crops' single-return Ground points (the model's own class, as surfaces.py takes them; the EA's
point classes are never used) are not on one scale from one flight line to the next: lines 511 and 611, flown on
16 Dec 2020 minutes apart, differ by a factor of 0.60 where they overlap, the same at every brightness (a change of
the sensor's gain), and lines flown on other days by 0.7 to 1.2. One threshold over them all made bands of the map
greener or greyer by the line they were flown on (the grass share of the ground went from about 25% to 55% across
northing 241,200, where line 611 begins). So:
- a line is a point source id flown on one day (GPS time); its points are those in the tile cores;
- within a survey, the lines are adjusted together from their overlaps, a gain each (radiometric block adjustment
  over strip overlaps: Ding et al. 2013, Teo & Wu 2015; here a gain without an offset, since the same-day pairs keep
  one ratio from the darkest to the brightest fifth of their shared cells): where two lines overlap, each 1 m cell
  they share gives the log ratio of their mean intensities, the median over the shared cells is the pair's ratio, and
  the gains (log) are solved by least squares from the pairs, each weighted by its shared cells, with the survey's
  largest line fixed at 1; every line must be joined to it through overlaps, else this stops;
- the two surveys do not overlap (each is delivered in whole 5 km squares), so they are joined where they meet by
  scaling (a level-2 normalisation, Kashani et al. 2015): the survey with the most tiles is the reference, and the
  other's factor is the median corrected intensity of the reference's tiles that touch it along an edge over that of
  its own tiles that touch the reference. No published method corrects lidar intensity for wet against dry flying
  days (Kashani et al. 2015), and asphalt alone, the usual invariant target (Schott et al. 1988; Vain et al. 2009),
  gave 0.69 where the ground as a whole gives 0.50: the December 2020 flights darkened fields and grass more than
  tarmac. Checked against ESA WorldCover 2021 (10 m; a check only, never an input): within 300 m of the line, its
  grassland reads as grass on 70% of cells south and 67% north with this join (90% north with asphalt's), and its
  cropland on 13% both sides (42% north with asphalt's).
Writes layers/intensity_lines.json: each line's survey, GPS time span, points and gain, the pairs, and the surveys'
factors; surfaces.py scales each point's intensity by its line's gain times its survey's factor, finding the line by
the point's GPS time. With --check, a second pass records the grass share of each 100 m band of northing with one Otsu
threshold over the raw and over the corrected intensities (20 Oct 2026, v1's classes: the step at the survey line
0.66 raw, 0.05 corrected; the largest step anywhere 0.66 raw, 0.13 corrected).
Known limits: a line's own fall-off towards its swath edge is not corrected (the 16 Dec line along the survey line
reads about a fifth darker at its edge than inside); the day-to-day pairs are not one ratio at every brightness
(17 Jan against 16 Dec: 0.82 in the darkest fifth, 0.55 to 0.64 above), and the gain follows the brighter ground,
where the threshold lies.
References: Ding Q, Chen W, King B, Liu Y, Liu G (2013) ISPRS J Photogramm Remote Sens 75:40-47,
doi:10.1016/j.isprsjprs.2012.09.015; Teo T-A, Wu H-M (2015) Remote Sens 7(12):16831-16848, doi:10.3390/rs71215856;
Kashani AG, Olsen MJ, Parrish CE, Wilson N (2015) Sensors 15(11):28099-28128, doi:10.3390/s151128099; Schott JR,
Salvaggio C, Volchok WJ (1988) Remote Sens Environ 26(1):1-16, doi:10.1016/0034-4257(88)90116-2; Vain A, Kaasalainen
S, Pyysalo U, Krooks A, Litkey P (2009) Sensors 9(4):2780-2796, doi:10.3390/s90402780.
usage: <pipeline venv python> -I intensity_lines.py <repo root> [--check]
"""
import json, os, sys, datetime as dt
from collections import defaultdict
from pathlib import Path
import numpy as np
import laspy

ROOT = Path(sys.argv[1]); CHECK = "--check" in sys.argv[2:]
os.environ.setdefault("ROUNDS_DIR", str(ROOT / "data" / "mk" / "heat" / "rounds"))
sys.path.insert(0, str(ROOT / "pipeline"))
import round_common as rc  # noqa: E402

RD = Path(os.environ["ROUNDS_DIR"]); H = ROOT / "data" / "mk" / "heat"
GROUND = 0                                                    # classes.MODEL order, as surfaces.py
UNIX_OF_GPS = 315964800 + 1e9                                 # adjusted standard GPS time (LAS global encoding bit 0) to Unix
pool = {t["id"]: t for t in json.load(open(RD / "pool.json"))["tiles"]}
LR = np.linspace(-4, 4, 8001)                                 # bins of a pair's log ratios (a median to 0.001)


def ground_points(tid):
    """the tile core's single-return Ground points (the model's class): x, y, intensity, GPS time and line name"""
    t = pool[tid]; cut = rc.read_json(RD / "cut" / f"{tid}.json")
    pts, hdr = rc.read_points(rc.resolve(t["file"]))
    cell, kept = rc.point_cells(pts, t["origin"], rc.cut_cell(cut))
    assert rc.cells_sha256(kept) == cut["cells_sha256"], f"{tid}: cells differ from the cut record"
    p = np.load(RD / "mk" / "pred" / f"{tid}.npz", allow_pickle=True)
    cls = np.full(len(cell), 255, np.uint8); ok = cell >= 0; cls[ok] = p["cls"][cell[ok]]
    psid = np.asarray(laspy.read(rc.resolve(t["file"])).point_source_id)          # file order, as read_points
    assert len(psid) == len(cls), f"{tid}: point counts differ"
    cx0, cy0, cx1, cy1 = t["core"]
    m = ((pts["x"] >= cx0) & (pts["x"] < cx1) & (pts["y"] >= cy0) & (pts["y"] < cy1) & (cls == GROUND)
         & (pts["return_number"] == 1) & (pts["number_of_returns"] == 1))
    gps = pts["gps_time"][m]
    # adjusted standard GPS time (seconds since the GPS epoch less 1e9; the crops' headers do not set the flag, but the
    # values tell: GPS week time stays under 604,800 s)
    assert not len(gps) or gps.min() > 604800, f"{tid}: GPS time looks like week time, not adjusted standard time"
    day = np.floor((gps + UNIX_OF_GPS) / 86400).astype(np.int64)
    key = psid[m].astype(np.int64) * 100000 + day
    names = {k: f"{k // 100000}@{dt.datetime.fromtimestamp(int(k % 100000) * 86400, dt.UTC):%Y-%m-%d}" for k in np.unique(key)}
    uk, inv = np.unique(key, return_inverse=True)
    return pts["x"][m], pts["y"][m], pts["intensity"][m].astype(float), gps, np.array([names[k] for k in uk])[inv]


def cell_means(tid, x, y, it, line):
    """each (1 m cell, line) of the core: the cell index, the line and the mean intensity"""
    cx0, cy0 = pool[tid]["core"][:2]
    c = np.floor(y - cy0).astype(np.int64) * 1000 + np.floor(x - cx0).astype(np.int64)
    ln, li = np.unique(line, return_inverse=True)
    u, inv, cnt = np.unique(c * len(ln) + li, return_inverse=True, return_counts=True)
    return u // len(ln), ln[u % len(ln)], np.bincount(inv, weights=it) / cnt


# pass 1: the lines and the pairs' log ratios
lines = defaultdict(lambda: {"points": 0, "gps": [np.inf, -np.inf], "surveys": set()})
pairs = defaultdict(lambda: np.zeros(len(LR) - 1))
for k, tid in enumerate(sorted(pool)):
    x, y, it, gps, line = ground_points(tid)
    for nm in np.unique(line):
        m = line == nm; L = lines[nm]
        L["points"] += int(m.sum()); L["gps"] = [min(L["gps"][0], float(gps[m].min())), max(L["gps"][1], float(gps[m].max()))]
        L["surveys"].add(pool[tid]["survey"])
    cell, ln, mean = cell_means(tid, x, y, it, line)
    o = np.argsort(cell, kind="stable"); cell, ln, mean = cell[o], ln[o], mean[o]
    starts = np.flatnonzero(np.r_[True, cell[1:] != cell[:-1]]); size = np.diff(np.r_[starts, len(cell)])
    grp = np.repeat(np.arange(len(starts)), size); pos = np.arange(len(cell)) - starts[grp]; gs = size[grp]
    for d in range(1, int(size.max()) if len(size) else 1):
        i = np.flatnonzero(pos + d < gs); j = i + d
        a, b, ia, ib = ln[i], ln[j], mean[i], mean[j]
        sw = a > b
        a, b, ia, ib = np.where(sw, b, a), np.where(sw, a, b), np.where(sw, ib, ia), np.where(sw, ia, ib)
        ok = (ia > 0) & (ib > 0)
        code = np.char.add(np.char.add(a[ok], "|"), b[ok]); lr = np.log(ia[ok] / ib[ok])
        for c in np.unique(code):
            pairs[tuple(c.split("|"))] += np.histogram(lr[code == c], bins=LR)[0]
    if k % 50 == 0:
        print(f"{k + 1}/{len(pool)} {tid}: {len(np.unique(line))} lines", flush=True)
for nm, L in lines.items():
    assert len(L["surveys"]) == 1, f"line {nm} lies in two surveys"
    L["survey"] = L.pop("surveys").pop()
spans = sorted((L["gps"][0], L["gps"][1], nm) for nm, L in lines.items())
for (a0, a1, an), (b0, b1, bn) in zip(spans, spans[1:]):
    assert a1 < b0, f"lines {an} and {bn} overlap in GPS time: a point's line could not be told from its time"


def median_of(h):
    c = np.cumsum(h); i = int(np.searchsorted(c, c[-1] / 2)); return float((LR[i] + LR[i + 1]) / 2)


# the gains: g_a - g_b = -median log(I_a / I_b) for each pair, weighted by its shared cells; the survey's largest line 0
names = sorted(lines); ix = {n: i for i, n in enumerate(names)}
P = [{"a": a, "b": b, "cells": int(h.sum()), "median_log_ratio": median_of(h)} for (a, b), h in sorted(pairs.items()) if h.sum() > 0]
rows, rhs, w = [], [], []
for p in P:
    assert lines[p["a"]]["survey"] == lines[p["b"]]["survey"]
    r = np.zeros(len(names)); r[ix[p["a"]]], r[ix[p["b"]]] = 1, -1
    rows.append(r); rhs.append(-p["median_log_ratio"]); w.append(np.sqrt(p["cells"]))
fixed = {}
for s in sorted({L["survey"] for L in lines.values()}):
    fixed[s] = max((n for n in names if lines[n]["survey"] == s), key=lambda n: lines[n]["points"])
    r = np.zeros(len(names)); r[ix[fixed[s]]] = 1; rows.append(r); rhs.append(0.0); w.append(1.0)
# every line joined to its survey's fixed line through overlaps
adj = defaultdict(set)
for p in P:
    adj[p["a"]].add(p["b"]); adj[p["b"]].add(p["a"])
for s, f0 in fixed.items():
    seen, todo = {f0}, [f0]
    while todo:
        for n in adj[todo.pop()] - seen:
            seen.add(n); todo.append(n)
    alone = [n for n in names if lines[n]["survey"] == s and n not in seen]
    assert not alone, f"lines of {s} with no overlap path to {f0}: {alone}"
A, b_, W = np.array(rows), np.array(rhs), np.array(w)
g = np.linalg.lstsq(A * W[:, None], b_ * W, rcond=None)[0]
for p in P:
    p["residual"] = float(g[ix[p["a"]]] - g[ix[p["b"]]] + p["median_log_ratio"])
for n in names:
    lines[n]["gain"] = float(np.exp(g[ix[n]]))
print("gains:", ", ".join(f"{n} {lines[n]['gain']:.3f}" for n in names), flush=True)
print(f"{len(P)} overlapping pairs; largest residual (log) {max(abs(p['residual']) for p in P):.4f}", flush=True)

# the surveys joined where they meet
sv = {t: p["survey"] for t, p in pool.items()}
core = {t: tuple(p["core"][:2]) for t, p in pool.items()}; at = {xy: t for t, xy in core.items()}
touch = lambda t: [at[(core[t][0] + dx, core[t][1] + dy)] for dx, dy in ((1000, 0), (-1000, 0), (0, 1000), (0, -1000)) if (core[t][0] + dx, core[t][1] + dy) in at]
REF = max(sorted(set(sv.values())), key=lambda s: sum(v == s for v in sv.values()))
gain = {n: lines[n]["gain"] for n in names}


def corrected(tid):
    x, y, it, gps, line = ground_points(tid)
    return cell_means(tid, x, y, it * np.array([gain[n] for n in line]), line), cell_means(tid, x, y, it, line)


link = {REF: {"factor": 1.0}}
for s in sorted(set(sv.values()) - {REF}):
    mine = sorted(t for t in pool if sv[t] == s and any(sv[n] == REF for n in touch(t)))
    theirs = sorted({n for t in mine for n in touch(t) if sv[n] == REF})
    med = {}
    for side, ts in (("reference", theirs), ("own", mine)):
        v = []
        for t in ts:
            (cell, ln, mean), _ = corrected(t)
            # one value a cell: the mean over its lines' corrected means
            u, inv = np.unique(cell, return_inverse=True); v.append(np.bincount(inv, weights=mean) / np.bincount(inv))
        med[side] = float(np.median(np.concatenate(v)))
    link[s] = {"factor": med["reference"] / med["own"], "tiles": len(mine), "reference_tiles": len(theirs),
               "median": med["own"], "reference_median": med["reference"]}
    print(f"{s} joined to {REF}: median corrected ground intensity {med['own']:.0f} on its {len(mine)} tiles along the edge, "
          f"{med['reference']:.0f} on {REF}'s {len(theirs)}: factor {link[s]['factor']:.3f}", flush=True)

out = {"made": dt.datetime.now().isoformat(timespec="seconds"), "reference_survey": REF, "link": link,
       "lines": {n: {"survey": lines[n]["survey"], "gps": lines[n]["gps"], "points": lines[n]["points"], "gain": lines[n]["gain"],
                     "fixed": fixed[lines[n]["survey"]] == n} for n in names},
       "pairs": P}

if CHECK:
    # pass 2: the grass share of each 100 m band of northing, one Otsu threshold over all, raw and corrected
    EDGES = np.linspace(0, 1000, 401); hist = {}
    for t in sorted(pool):
        (cell, ln, mean), (cell0, ln0, mean0) = corrected(t)
        f = link[sv[t]]["factor"]; cy0 = pool[t]["core"][1]
        for v, (c, m) in (("corrected", (cell, mean * f)), ("raw", (cell0, mean0))):
            u, inv = np.unique(c, return_inverse=True); val = np.bincount(inv, weights=m) / np.bincount(inv)
            band = cy0 + (u // 1000) // 100 * 100
            for n0 in np.unique(band):
                hist.setdefault((v, int(n0)), np.zeros(len(EDGES) - 1))[:] += np.histogram(np.clip(val[band == n0], 0, 999.9), bins=EDGES)[0]
    out["check"] = {}
    for v in ("raw", "corrected"):
        tot = sum(h for (vv, _), h in hist.items() if vv == v); c = (EDGES[:-1] + EDGES[1:]) / 2
        w0 = np.cumsum(tot); w1 = w0[-1] - w0; m0 = np.cumsum(tot * c)
        k = int(np.argmax(w0 * w1 * (m0 / np.maximum(w0, 1) - (m0[-1] - m0) / np.maximum(w1, 1)) ** 2)) + 1
        share = {n0: float(h[k:].sum() / max(h.sum(), 1)) for (vv, n0), h in sorted(hist.items()) if vv == v}
        jumps = sorted(((abs(share[b] - share[a]), a, b) for a, b in zip(sorted(share)[:-1], sorted(share)[1:]) if b - a == 100), reverse=True)[:5]
        out["check"][v] = {"threshold": float(EDGES[k]), "grass_share_by_band": share, "largest_jumps": [[a, b, round(j, 3)] for j, a, b in jumps]}
        print(f"{v}: threshold {EDGES[k]:.0f}; largest band-to-band jumps {[(a, b, round(j, 2)) for j, a, b in jumps]}", flush=True)
json.dump(out, open(H / "layers" / "intensity_lines.json", "w"), indent=1)
print(f"{len(names)} lines -> {H / 'layers' / 'intensity_lines.json'}", flush=True)
