"""The page's basemap (18 Oct 2026, from package.py): Protomaps' MK extract as base64 text (artifacts serve no .pmtiles), cut
to the map's reach (the page's maxBounds) from zoom 8, the page's least zoom on a phone (its fit less one: 8.9 for the
whole city at 375 px), holding only what the page's style draws (template.html: its layers' source-layers, kinds and
properties), which halves it (Lighthouse, 18 Oct 2026: the basemap was half of the page's 5.5 MB); and the label ranges
the font needs. package.py calls write(); run alone it rewrites the page's basemap from out/data.json's bounds.
usage: .venv/bin/python -I basemap.py <repo root>
"""
import base64, gzip, json, subprocess, sys
from pathlib import Path
from pmtiles.reader import Reader, MmapSource, all_tiles
from pmtiles.writer import Writer
from pmtiles.tile import zxy_to_tileid
from mapbox_vector_tile.Mapbox import vector_tile_pb2


def prune(data, drawn, named):
    """the tile with only the layers, kinds and properties the page draws, each kept feature's geometry copied as its
    bytes stand: decoding and encoding the shapes again turned some rings round, which MapLibre (taking a feature's first
    ring's winding as the outer) filled as wide bands of water (Jacob, 18 Oct 2026: "the zoomed out map's style is
    glitchy see the floating blu chunks")"""
    src = vector_tile_pb2.tile(); src.ParseFromString(data)
    out = vector_tile_pb2.tile()
    for L in src.layers:
        if L.name not in drawn:
            continue
        kinds, props = drawn[L.name]
        val = [v.ListFields()[0][1] if v.ListFields() else None for v in L.values]
        NL = out.layers.add(); NL.name = L.name; NL.version = L.version; NL.extent = L.extent
        kidx, vidx = {}, {}
        for f in L.features:
            p = {L.keys[k]: (k, v) for k, v in zip(f.tags[0::2], f.tags[1::2])}
            kind = val[p["kind"][1]] if "kind" in p else None
            if (kinds is not None and kind not in kinds) or (L.name == "pois" and "name" not in p):
                continue
            nf = NL.features.add()
            if f.HasField("id"):
                nf.id = f.id
            nf.type = f.type
            nf.geometry.extend(f.geometry)
            for k in props:
                if k in p:
                    ko, vo = p[k]
                    if ko not in kidx:
                        kidx[ko] = len(kidx); NL.keys.append(L.keys[ko])
                    if vo not in vidx:
                        vidx[vo] = len(vidx); NL.values.add().CopyFrom(L.values[vo])
                    nf.tags.extend([kidx[ko], vidx[vo]])
            if "name" in p:
                named.add(val[p["name"][1]])
        if not NL.features:
            del out.layers[-1]
    return out.SerializeToString()


def write(H, WEB, bounds):
    (w_, s_), (e_, n_) = bounds; pw, ph = (e_ - w_) * 0.4, (n_ - s_) * 0.4
    cut = WEB / "basemap_cut.pmtiles"; cut.unlink(missing_ok=True)
    subprocess.run(["pmtiles", "extract", str(H / "basemap_mk.pmtiles"), str(cut), f"--bbox={w_ - pw},{s_ - ph},{e_ + pw},{n_ + ph}", "--minzoom=8"],
                   check=True, capture_output=True)
    LANDMARK = {"mall", "station", "train_station", "hospital", "university", "museum", "theatre", "music_venue", "stadium", "marketplace",
                "retail", "cinema", "arts_centre", "theme_park"}
    GREEN_POI = {"park", "nature_reserve", "wood", "forest", "garden", "water", "lake", "reservoir"}
    DRAWN = {"landuse": ({"park", "recreation_ground", "golf_course", "cemetery", "garden", "pitch", "playground", "nature_reserve", "wood",
                          "forest", "grass", "village_green"}, ("kind",)),
             "water": (None, ("kind",)),
             "roads": ({"highway", "major_road", "minor_road", "rail"}, ("kind", "name")),
             "pois": (LANDMARK | GREEN_POI, ("kind", "name", "min_zoom")),
             "places": ({"locality", "neighbourhood"}, ("kind", "kind_detail", "name", "min_zoom"))}
    named = set()
    with open(cut, "rb") as f_in:
        rd = Reader(MmapSource(f_in)); bm_hdr, bm_meta = rd.header(), rd.metadata(); slim = []
        for (z_, x_, y_), raw in all_tiles(rd.get_bytes):
            slim.append((zxy_to_tileid(z_, x_, y_), gzip.compress(prune(gzip.decompress(raw), DRAWN, named), 9)))
    bm_meta["vector_layers"] = [l_ for l_ in bm_meta.get("vector_layers", []) if l_["id"] in DRAWN]
    small = WEB / "basemap_slim.pmtiles"
    with open(small, "wb") as f_out:
        wr = Writer(f_out)
        for tid_, b_ in sorted(slim):
            wr.write_tile(tid_, b_)
        wr.finalize(bm_hdr, bm_meta)
    (WEB / "basemap.txt").write_text(base64.b64encode(small.read_bytes()).decode())
    print(f"basemap {cut.stat().st_size:,} -> {small.stat().st_size:,} bytes", flush=True)
    cut.unlink(); small.unlink()
    rngs = sorted({ord(c) // 256 for nm in named for c in nm} | {0})
    json.dump([f"{r * 256}-{r * 256 + 255}" for r in rngs], open(WEB / "glyph_ranges.json", "w"))


if __name__ == "__main__":
    ROOT = Path(sys.argv[1]); WEB = ROOT / "data" / "experiments" / "mk_heat" / "web" / "out"
    write(ROOT / "data" / "mk" / "heat", WEB, json.load(open(WEB / "data.json"))["bounds"])
