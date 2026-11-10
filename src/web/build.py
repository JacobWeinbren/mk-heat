"""The page from template.html with the map library's stylesheet inlined (the artifact allows no outside
stylesheets): out/page.html to publish, out/index.html with a document skeleton for the local preview.
The card's text is written into the page from out/data.json, so it shows at first paint and nothing moves when the
data arrive (Lighthouse, 18 Oct 2026: the card filling in was the page's layout shift and its largest paint); the
script sets the same text again. The label font carries only the faces the style names and the ranges the labels use.
Once site.py has made the archives (tiles/index.json), the whole folder Cloudflare Pages serves too, site/: the page,
its script and figures, the label glyphs, the two libraries, the picture a shared link shows and the caching rules
(_headers). usage: python3 build.py"""
import base64, hashlib, html, json, re, shutil
from pathlib import Path

# the folder this script is run from, by the name it was run by: in the lidar project that name is a link to this file
# (10 Nov 2026: one copy of each script, here; Jacob: "Ensure there is only one folder"), and the page's inputs (out/,
# tiles/) lie beside the link, not beside the file it points to
W = Path(__file__).absolute().parent
D = json.loads((W / "out" / "data.json").read_text())
ORIGIN = "https://heat.weinbren.me"            # where the site is served (README): the tags a shared link is read by need whole addresses
# Instrument Sans (SIL OFL), its Latin subset as Google Fonts serves it (one variable file, weights 400 to 700), inside
# the page: fetched afterwards, its arrival re-wrapped the card's text and moved it (Lighthouse, phone: layout shift 0.29)
FONT = base64.b64encode((W / "vendor" / "fonts" / "instrument_sans_latin.woff2").read_bytes()).decode()
FACE = ("@font-face { font-family: 'Instrument Sans'; font-style: normal; font-weight: 400 700; font-display: block; "
        f"src: url(data:font/woff2;base64,{FONT}) format('woff2'); unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, "
        "U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD; }")


def rules(css):
    """a stylesheet's rules, each as (what it applies to, its body without the braces)"""
    out, i = [], 0
    while (j := css.find("{", i)) >= 0:
        depth, k = 1, j + 1
        while depth:
            depth += {"{": 1, "}": -1}.get(css[k], 0); k += 1
        out.append((css[i:j].strip(), css[j + 1:k - 1])); i = k
    return out


def without(css, drop):
    """the stylesheet without the rules whose selectors name any of drop (inside @media blocks too)"""
    out = []
    for pre, body in rules(css):
        if pre.startswith(("@media", "@supports")):
            body = without(body, drop)
        elif not pre.startswith("@"):
            pre = ",".join(sel for sel in pre.split(",") if not any(d in sel for d in drop))
        if pre and body:
            out.append(f"{pre}{{{body}}}")
    return "".join(out)


# MapLibre's stylesheet without the controls the page never adds (its logo, compass, full-screen, terrain and globe
# buttons and the two-finger notice, with their pictures for high-contrast screens): 65 kB of the page's 119 kB were
# this stylesheet, and 20 kB are the rules of what the page does add (10 Nov 2026)
UNUSED = ("ctrl-logo", "ctrl-compass", "ctrl-fullscreen", "ctrl-shrink", "ctrl-terrain", "ctrl-globe", "pseudo-fullscreen", "cooperative-gesture")
MAP_CSS = without((W / "vendor" / "maplibre-gl-4.7.1.css").read_text(), UNUSED)
assert all(k in MAP_CSS for k in (".maplibregl-map{", ".maplibregl-popup-content{", "ctrl-zoom-in", "ctrl-attrib", "ctrl-scale", "ctrl-geolocate")), "a rule the page needs is gone"
page = (W / "template.html").read_text().replace("/*MAPLIBRE_CSS*/", MAP_CSS).replace("/*FONT_FACE*/", FACE)


def fill(s, el_id, inner):
    """the inner HTML of the element with this id"""
    pat = re.compile(r'(<(\w+)\b[^>]*\bid="' + el_id + r'"[^>]*>)(.*?)(</\2>)', re.S)
    assert len(pat.findall(s)) == 1, el_id
    return pat.sub(lambda m: m.group(1) + inner + m.group(4), s)


# the page opens on the urban part's figures where package.py gave them (the switch's first state), on open ground and
# on the whole day: everything the script will write first is written here, in the script's own rounding (JavaScript's
# Math.round takes a half up, Python's round to the even number)
FIG = D.get("urban") or {}
rnd = lambda x: int(x + 0.5)
NH, HOT = len(D["hours"]), D["hot"]
day_stats, stats = FIG.get("day_stats", D["day"]["stats"]), FIG.get("stats", D["stats"])
share = {v: 1 - day_stats[v][0] for v in ("ground", "paths", "stops")}
num = {v: f"{rnd(share[v] * FIG.get('n_stops', D['n_stops'])):,}" if v == "stops" else f"{rnd(share[v] * 100)}%" for v in share}
day_key = "".join(f'<i style="background:var({c})"></i>' for c in D["day"]["colors"]) + "".join(f"<span>{l}</span>" for l in D["day"]["labels"])
for el_id, inner in [("when", html.escape(f"{D['area']}, Thursday 13 August 2026")), ("h1", FIG.get("headline", D["headline"])), ("deck", html.escape(D["deck"])),
                     ("src", D["sources"]), ("cred", html.escape(D["credits"])), ("keyh", "Hours that felt like 38 °C or more"),
                     ("keyof", "Share of open ground"), ("lkeyh", "Hours at 38 °C or more"),
                     ("air", f"Air peaked at {D['day']['peak_ta']:.0f} °C"), ("m-hour", D["hours"][D["start"]]["label"]),
                     ("ticks", "".join(f'<span style="grid-column:{3 * k + 1}/span {min(3, NH - 3 * k)}">{t}</span>' for k, t in enumerate(D["ticks"]))),
                     ("bars", "".join(f'<i class="" style="--f:{sum(sh[HOT:]) * 100:.1f}%"></i>' for sh in stats["ground"])),
                     ("barcap", "Open ground " + ("at 38 °C or more" if D["mode"] == "utci" else "in full sun") + ", hour by hour"),
                     ("scale", day_key + "".join(f"<b>{rnd(f * 100)}%</b>" for f in day_stats["ground"])), ("lscale", day_key),
                     *[(f"n-{v}", num[v]) for v in share], *[(f"s-{v}", html.escape(FIG.get("view_small", D["view_small_day"])[v])) for v in share],
                     ("vh", html.escape(D.get("views_head", {}).get("day", "")))]:
    page = fill(page, el_id, inner)
if FIG:                                                 # the switch of where the figures are of, from the first paint
    page = page.replace('id="where" hidden>', 'id="where">')
if D.get("scenarios"):                                  # the switch shows from the first paint, one button a scenario
    page = page.replace('<div class="scen" id="scen" hidden>', '<div class="scen" id="scen">')
    page = fill(page, "scbtns", '<button type="button" data-s="" aria-pressed="true">As it was</button>' + "".join(
        f'<button type="button" data-s="{nm}" aria-pressed="false">{html.escape(S["label"])}</button>' for nm, S in D["scenarios"].items()))
for el_id in ("scale", "lscale"):
    page = page.replace(f'<div class="scale" id="{el_id}">', f'<div class="scale" id="{el_id}" style="grid-template-columns: repeat({len(D["day"]["colors"])}, 1fr)">')
page = page.replace('<div class="day all" id="day">', f'<div class="day all" id="day" style="--nh:{NH}">')
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
# without what the page never reads: the place names package.py gathers (the page draws the basemap's own; they were
# half of meta.json) and the corners of the whole ground image (the pieces carry their own)
web = dict({k: v for k, v in D.items() if k not in ("labels", "ground_corners")},
           paths=[[p[0], enc(p[1]), p[2]] for p in D["paths"]], stops=[{**s_, "v": enc(s_["v"])} for s_ in D["stops"]])
if D.get("scenarios"):
    web["scenarios"] = {nm: dict(S, paths={k: enc(v) for k, v in S["paths"].items()}, stops={k: enc(v) for k, v in S["stops"].items()},
                                 trees=steps(S["trees"])) for nm, S in D["scenarios"].items()}
(W / "out" / "data_web.json").write_text(json.dumps(web, separators=(",", ":"), ensure_ascii=False))
# the label font (Protomaps' Noto Sans glyphs, SIL OFL), as base64 in one served file for the artifact: the page loads
# glyphs through its own protocol, since artifacts serve no .pbf files; a range it lacks comes back empty (the site has
# the same faces and ranges as .pbf files, below)
G = W.parents[3] / "data" / "mk" / "heat" / "glyphs"
faces = set(re.findall(r"'text-font': \['([^']+)'\]", page))
ranges = set(json.loads((W / "out" / "glyph_ranges.json").read_text()))
GLYPHS = [f for f in sorted(G.glob("*.pbf")) if f.stem.rsplit("_", 1)[0].replace("_", " ") in faces and f.stem.rsplit("_", 1)[1] in ranges]
glyphs = {}
for f in GLYPHS:
    stack, rng = f.stem.rsplit("_", 1)
    glyphs.setdefault(stack.replace("_", " "), {})[rng] = base64.b64encode(f.read_bytes()).decode()
(W / "out" / "glyphs.json").write_text(json.dumps(glyphs))
# each file the page asks for carries its own content's hash (the page's V), so it can be kept a year and a new build
# fetches only the files that changed
OUT, SITE = W / "out", W / "site"
vers = lambda root, files: {str(f.relative_to(root)): hashlib.sha1(f.read_bytes()).hexdigest()[:10] for f in files}
def made(mode, V, js, TS=None):
    return (page.replace("__MODE__", mode).replace("__VERS__", json.dumps(V, separators=(",", ":"))).replace("__TILES__", json.dumps(TS or {}))
            .replace("__MAPLIBRE_JS__", js[0]).replace("__PMTILES_JS__", js[1]))
# the page described by the headline it opens on (the urban part's; until 10 Nov 2026 the whole area's, 72% under a page
# that opened on 71%)
desc = re.sub(r"<[^>]+>", "", FIG.get("headline", D["headline"]))
SUN = ("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><circle cx='16' cy='16' r='6.5' fill='%23b8361f'/>"
       "<path d='M16 2.5v4M16 25.5v4M2.5 16h4M25.5 16h4M6.5 6.5l2.8 2.8M22.7 22.7l2.8 2.8M6.5 25.5l2.8-2.8M22.7 9.3l2.8-2.8' "
       "stroke='%23b8361f' stroke-width='2.6' stroke-linecap='round'/></svg>")   # a plain sun in the heat colour (Jacob: "tree and or sun related. Not ai like")
GROUND = re.search(r"--ground: (#[0-9a-f]{6})", page).group(1)         # the page's own ground colour, for a phone's browser bars
head = lambda extra="": ('<!doctype html><html lang="en-GB"><head><meta charset="utf-8">'
                         '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
                         f'<meta name="description" content="{html.escape(desc)}"><meta name="theme-color" content="{GROUND}">'
                         f'<link rel="icon" href="{SUN}">' + extra)


def document(extra, body):
    """a whole document from the page: its title and styles in the head, the rest in the body (the page as the artifact
    takes it has neither, its host adds them)"""
    cut = body.index('<div id="map"')
    return head(extra) + body[:cut].rstrip() + "</head><body>" + body[cut:].rstrip() + "</body></html>\n"


# the artifact (claude.ai serves no .pmtiles): page.html to publish, index.html beside it for the local preview
art = made("artifact", vers(OUT, [OUT / "data_web.json", OUT / "basemap.txt", OUT / "glyphs.json", *sorted((OUT / "ground").glob("*.png"))]),
           ("https://cdn.jsdelivr.net/npm/maplibre-gl@4.7.1/dist/maplibre-gl.js", "https://cdn.jsdelivr.net/npm/pmtiles@3.2.1/dist/pmtiles.js"))
(OUT / "page.html").write_text(art)
(OUT / "index.html").write_text(document("", art))
# the site (site.py made its archives): the card's figures in meta.json, every map layer from PMTiles
TI = W / "tiles" / "index.json"
if TI.exists():
    # the folder's other files (site.py copied these and wrote _headers until 10 Nov 2026; here, so the page can be
    # built again without the archives being made and sent again): the label glyphs, the two libraries as jsDelivr
    # serves them (kept beside this script; where they are not, the copies already on the site stand), the picture a
    # shared link shows, and the caching rules: every file the page asks for by its content's hash is kept a year, the
    # page itself is checked each time
    LIBS = ("vendor/maplibre-gl-4.7.1.js", "vendor/pmtiles-3.2.1.js")
    shutil.rmtree(SITE / "glyphs", ignore_errors=True); (SITE / "glyphs").mkdir(parents=True); (SITE / "vendor").mkdir(exist_ok=True)
    for f in GLYPHS:
        shutil.copyfile(f, SITE / "glyphs" / f.name)
    for f in LIBS:
        if (W / f).exists() and not ((SITE / f).exists() and (W / f).samefile(SITE / f)):     # (one may be a link to the other)
            shutil.copyfile(W / f, SITE / f)
        assert (SITE / f).exists(), f
    CARD = SITE / "card.jpg"
    if (W / "card.jpg").exists():
        shutil.copyfile(W / "card.jpg", CARD)
    YEAR = "Cache-Control: public, max-age=31536000, immutable"
    (SITE / "_headers").write_text("\n".join([
        "/", "  Cache-Control: public, max-age=0, must-revalidate", "/index.html", "  Cache-Control: public, max-age=0, must-revalidate",
        *[ln for p in ("/meta.json", "/page.js", "/card.jpg", "/glyphs/*", "/vendor/*") for ln in (p, "  " + YEAR)],
        "/*", "  X-Content-Type-Options: nosniff", ""]))
    # the site's figures: the page's data without the footpaths, stops and greyed areas (they are tiles) and without the
    # pieces of the ground images (the artifact's)
    meta = {k: v for k, v in web.items() if k not in ("paths", "stops", "grey", "pieces")}
    meta["scenarios"] = {nm: {k: v for k, v in S.items() if k not in ("paths", "stops", "trees")} for nm, S in web.get("scenarios", {}).items()}
    (SITE / "meta.json").write_text(json.dumps(meta, separators=(",", ":"), ensure_ascii=False))
    V = vers(SITE, [SITE / "meta.json", *sorted((SITE / "glyphs").glob("*.pbf"))])
    TS = json.loads(TI.read_text())
    site = made("site", V, LIBS, TS)
    # the page's own script in a file of its own named by its hash, kept a year: the page, which is fetched whole on
    # every visit (Pages sends it with no ETag to check against), keeps only the card's text and the font (inline so
    # the card's text does not move, above)
    i0 = site.rindex('<script data-cfasync="false">'); i1 = site.index("</script>", i0)
    js = site[i0 + len('<script data-cfasync="false">'):i1]
    (SITE / "page.js").write_text(js)
    jsv = hashlib.sha1(js.encode()).hexdigest()[:10]
    site = site[:i0] + f'<script data-cfasync="false" src="page.js?v={jsv}"></script>' + site[i1 + len("</script>"):]
    # the place names' glyphs (the labels the opening view shows; Latin, the 0-255 range) asked for with the page, not
    # after the first tiles are drawn (19 Oct 2026: asked at 0.8 s of a 1 s load)
    place_face = re.search(r"id: 'lab-place'.*?'text-font': \['([^']+)'\]", page, re.S).group(1)
    gl = f"glyphs/{place_face.replace(' ', '_')}_0-255.pbf"
    # the card's figures are asked for while the page is read, before the scripts run; the tiles' host is connected early
    tile_host = "/".join(next(iter(TS.values())).split("/")[:3])
    # what a shared link shows (a message, a search result, a post): the page's name, the headline it opens on and, where
    # the picture is there, the picture (card.jpg: the map of the urban part over the whole day, without a figure on it,
    # so a new run of the model cannot leave a stale one), each by its whole address
    title = re.search(r"<title>(.*?)</title>", page).group(1)
    share = (f'<link rel="canonical" href="{ORIGIN}/"><meta property="og:type" content="website"><meta property="og:url" content="{ORIGIN}/">'
             f'<meta property="og:title" content="{html.escape(title)}"><meta property="og:description" content="{html.escape(desc)}">'
             + (f'<meta property="og:image" content="{ORIGIN}/card.jpg?v={vers(SITE, [CARD])["card.jpg"]}"><meta property="og:image:width" content="1200">'
                '<meta property="og:image:height" content="630"><meta property="og:image:alt" content="A map of Milton Keynes coloured by the hours '
                'its open ground felt like 38 °C or more"><meta name="twitter:card" content="summary_large_image">' if CARD.exists() else ""))
    (SITE / "index.html").write_text(document(
        share + f'<link rel="preload" href="meta.json?v={V["meta.json"]}" as="fetch" crossorigin>'
        + (f'<link rel="preconnect" href="{tile_host}" crossorigin>' if tile_host.startswith("http") else "")
        + (f'<link rel="preload" href="{gl}?v={V[gl]}" as="fetch" crossorigin>' if gl in V else ""), site))
print("built", OUT, "| font", {k: sorted(v) for k, v in glyphs.items()}, "| site" if (SITE / "index.html").exists() else "")
