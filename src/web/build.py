"""The page from template.html with the map library's stylesheet inlined (the artifact allows no outside
stylesheets): out/page.html to publish, out/index.html with a document skeleton for the local preview.
The card's text is written into the page from out/data.json, so it shows at first paint and nothing moves when the
data arrive (Lighthouse, 18 Oct 2026: the card filling in was the page's layout shift and its largest paint); the
script sets the same text again. The label font carries only the faces the style names and the ranges the labels use."""
import base64, html, json, re
from pathlib import Path

W = Path(__file__).resolve().parent
D = json.loads((W / "out" / "data.json").read_text())
# Instrument Sans (SIL OFL), its Latin subset as Google Fonts serves it (one variable file, weights 400 to 700), inside
# the page: fetched afterwards, its arrival re-wrapped the card's text and moved it (Lighthouse, phone: layout shift 0.29)
FONT = base64.b64encode((W / "vendor" / "fonts" / "instrument_sans_latin.woff2").read_bytes()).decode()
FACE = ("@font-face { font-family: 'Instrument Sans'; font-style: normal; font-weight: 400 700; font-display: block; "
        f"src: url(data:font/woff2;base64,{FONT}) format('woff2'); unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, "
        "U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD; }")
page = (W / "template.html").read_text().replace("/*MAPLIBRE_CSS*/", (W / "vendor" / "maplibre-gl-4.7.1.css").read_text()).replace("/*FONT_FACE*/", FACE)


def fill(s, el_id, inner):
    """the inner HTML of the element with this id"""
    pat = re.compile(r'(<(\w+)\b[^>]*\bid="' + el_id + r'"[^>]*>)(.*?)(</\2>)', re.S)
    assert len(pat.findall(s)) == 1, el_id
    return pat.sub(lambda m: m.group(1) + inner + m.group(4), s)


share = {v: 1 - D["day"]["stats"][v][0] for v in ("ground", "paths", "stops")}
num = {v: f"{round(share[v] * D['n_stops']):,}" if v == "stops" else f"{round(share[v] * 100)}%" for v in share}
day_key = (f'<i style="background:var({c})"></i>' for c in D["day"]["colors"])
for el_id, inner in [("when", html.escape(f"{D['area']}, Thursday 13 August 2026")), ("h1", D["headline"]), ("deck", html.escape(D["deck"])),
                     ("src", D["sources"]), ("cred", html.escape(D["credits"])), ("keyh", "Hours that felt like 38 °C or more"),
                     ("air", f"Air peaked at {D['day']['peak_ta']:.0f} °C"), ("m-hour", D["hours"][D["start"]]["label"]),
                     ("ticks", "".join(f"<span>{t}</span>" for t in D["ticks"])),
                     ("scale", "".join(day_key) + "".join(f"<span>{l}</span>" for l in D["day"]["labels"])),
                     *[(f"n-{v}", num[v]) for v in share], *[(f"s-{v}", html.escape(D["view_small_day"][v])) for v in share]]:
    page = fill(page, el_id, inner)
if D.get("scenarios"):                                  # the switch shows from the first paint, one button a scenario
    page = page.replace('<div class="scen" id="scen" hidden>', '<div class="scen" id="scen">')
    page = fill(page, "scbtns", '<button type="button" data-s="" aria-pressed="true">As it was</button>' + "".join(
        f'<button type="button" data-s="{nm}" aria-pressed="false">{html.escape(S["label"])}</button>' for nm, S in D["scenarios"].items()))
page = page.replace('<div class="scale" id="scale">', f'<div class="scale" id="scale" style="grid-template-columns: repeat({len(D["day"]["colors"])}, 1fr)">')
# the page's own copy of the data, smaller to fetch and parse (the city's data.json is 9 MB): each hourly value list as
# one character an hour (value + 35, so no character needs escaping: 35 is '#', and values stay well under 57) and the
# scenarios' tree positions as whole-number steps of 1e-5 degrees from the one before; package.py's data.json stays as
# written, for the scripts that read it
def enc(v):
    assert all(-35 < x < 57 for x in v), "a value outside the one-character range"
    return "".join(chr(x + 35) for x in v)
def steps(pts):
    out, x0, y0 = [], 0, 0
    for lon, lat in pts:
        x, y = round(lon * 1e5), round(lat * 1e5); out += [x - x0, y - y0]; x0, y0 = x, y
    return out
web = dict(D, paths=[[p[0], enc(p[1]), p[2]] for p in D["paths"]], stops=[{**s_, "v": enc(s_["v"])} for s_ in D["stops"]])
if D.get("scenarios"):
    web["scenarios"] = {nm: dict(S, paths={k: enc(v) for k, v in S["paths"].items()}, stops={k: enc(v) for k, v in S["stops"].items()},
                                 trees=steps(S["trees"])) for nm, S in D["scenarios"].items()}
(W / "out" / "data_web.json").write_text(json.dumps(web, separators=(",", ":"), ensure_ascii=False))
# the label font (Protomaps' Noto Sans glyphs, SIL OFL), as base64 in one served file for the artifact: the page loads
# glyphs through its own protocol, since artifacts serve no .pbf files; a range it lacks comes back empty (site.py
# copies the same faces and ranges as .pbf files for the site)
G = W.parents[3] / "data" / "mk" / "heat" / "glyphs"
faces = set(re.findall(r"'text-font': \['([^']+)'\]", page))
ranges = set(json.loads((W / "out" / "glyph_ranges.json").read_text()))
glyphs = {}
for f in sorted(G.glob("*.pbf")):
    stack, rng = f.stem.rsplit("_", 1)
    if stack.replace("_", " ") in faces and rng in ranges:
        glyphs.setdefault(stack.replace("_", " "), {})[rng] = base64.b64encode(f.read_bytes()).decode()
(W / "out" / "glyphs.json").write_text(json.dumps(glyphs))
# each file the page asks for carries its own content's hash (the page's V), so it can be kept a year and a new build
# fetches only the files that changed
import hashlib
OUT, SITE = W / "out", W / "site"
vers = lambda root, files: {str(f.relative_to(root)): hashlib.sha1(f.read_bytes()).hexdigest()[:10] for f in files}
def made(mode, V, js, TS=None):
    return (page.replace("__MODE__", mode).replace("__VERS__", json.dumps(V, separators=(",", ":"))).replace("__TILES__", json.dumps(TS or {}))
            .replace("__MAPLIBRE_JS__", js[0]).replace("__PMTILES_JS__", js[1]))
desc = re.sub(r"<[^>]+>", "", D["headline"])
SUN = ("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><circle cx='16' cy='16' r='6.5' fill='%23b8361f'/>"
       "<path d='M16 2.5v4M16 25.5v4M2.5 16h4M25.5 16h4M6.5 6.5l2.8 2.8M22.7 22.7l2.8 2.8M6.5 25.5l2.8-2.8M22.7 9.3l2.8-2.8' "
       "stroke='%23b8361f' stroke-width='2.6' stroke-linecap='round'/></svg>")   # a plain sun in the heat colour (Jacob: "tree and or sun related. Not ai like")
head = lambda extra="": ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
                         '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
                         f'<meta name="description" content="{html.escape(desc)}"><link rel="icon" href="{SUN}">' + extra)
# the artifact (claude.ai serves no .pmtiles): page.html to publish, index.html beside it for the local preview
art = made("artifact", vers(OUT, [OUT / "data_web.json", OUT / "basemap.txt", OUT / "glyphs.json", *sorted((OUT / "ground").glob("*.png"))]),
           ("https://cdn.jsdelivr.net/npm/maplibre-gl@4.7.1/dist/maplibre-gl.js", "https://cdn.jsdelivr.net/npm/pmtiles@3.2.1/dist/pmtiles.js"))
(OUT / "page.html").write_text(art)
(OUT / "index.html").write_text(head() + art + "</html>")
# the site (site.py made its archives): the card's figures in meta.json, every map layer from PMTiles
TI = W / "tiles" / "index.json"
if TI.exists():
    meta = {k: v for k, v in web.items() if k not in ("paths", "stops", "grey")}
    meta["scenarios"] = {nm: {k: v for k, v in S.items() if k not in ("paths", "stops", "trees")} for nm, S in web.get("scenarios", {}).items()}
    (SITE / "meta.json").write_text(json.dumps(meta, separators=(",", ":"), ensure_ascii=False))
    V = vers(SITE, [SITE / "meta.json", *sorted((SITE / "glyphs").glob("*.pbf"))])
    TS = json.loads(TI.read_text())
    site = made("site", V, ("vendor/maplibre-gl-4.7.1.js", "vendor/pmtiles-3.2.1.js"), TS)
    # the card's figures are asked for while the page is read, before the scripts run; the tiles' host is connected early
    tile_host = "/".join(next(iter(TS.values())).split("/")[:3])
    (SITE / "index.html").write_text(head(f'<link rel="preload" href="meta.json?v={V["meta.json"]}" as="fetch" crossorigin>'
                                          f'<link rel="preconnect" href="{tile_host}" crossorigin>') + site + "</html>")
print("built", OUT, "| font", {k: sorted(v) for k, v in glyphs.items()}, "| site" if (SITE / "index.html").exists() else "")
