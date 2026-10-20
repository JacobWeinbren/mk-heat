
(async () => {
const css = getComputedStyle(document.documentElement), tok = k => css.getPropertyValue(k).trim();
// two builds of one page (build.py): 'site', for a host that serves byte ranges, reads every map layer from PMTiles
// (the basemap, the footpaths, stops, greyed areas and new trees as vector tiles, the ground as raster tiles), so a
// visitor fetches only the tiles in view (Jacob, 18 Oct 2026: "serve as much as you can via pmtiles"); 'artifact', for
// claude.ai, which serves no .pmtiles, carries the basemap and the label font as text and the footpaths as JSON.
// Every file is asked for with its own content's hash (V), so it can be kept a year and a new build fetches only what
// changed
const MODE = 'site', SITE = MODE === 'site', V = {"meta.json":"c20cdc7bac","glyphs/Noto_Sans_Italic_0-255.pbf":"087b2484de","glyphs/Noto_Sans_Italic_8192-8447.pbf":"8572c4bca4","glyphs/Noto_Sans_Medium_0-255.pbf":"e3a9b013c2","glyphs/Noto_Sans_Medium_8192-8447.pbf":"6331ce179e"};
const u = p => p + (V[p] ? '?v=' + V[p] : '');
// build.py's compact copy: an hourly value list is one character an hour (value + 35), kept so: the map reads an hour's
// character with a slice, which keeps each footpath to one property a day rather than one an hour (the scenarios' would
// cost a phone seconds to hand to the map); tree positions are steps of 1e-5 degrees
const un = t => Array.from(t, c => c.charCodeAt(0) - 35);
function decode(d) {
  for (const S of Object.values(d.scenarios || {})) {
    if (!S.trees) continue;                           // the site's scenarios hold no trees: they are vector tiles
    const t = S.trees, pts = []; let x = 0, y = 0;
    for (let i = 0; i < t.length; i += 2) { x += t[i]; y += t[i + 1]; pts.push([x / 1e5, y / 1e5]); }
    S.trees = pts;
  }
  return d;
}
const [D, basemap, GLYPHS] = await Promise.all([fetch(u(SITE ? 'meta.json' : 'data_web.json')).then(r => r.json()).then(decode),
  SITE ? null : fetch(u('basemap.txt')).then(r => r.text()).then(t => {   // a plain loop: Uint8Array.from calls its map function once a byte
    const b = atob(t.trim()), a = new Uint8Array(b.length); for (let i = 0; i < b.length; i++) a[i] = b.charCodeAt(i); return a.buffer; }),
  SITE ? null : fetch(u('glyphs.json')).then(r => r.json())]);
const COLS = D.colors.map(c => c.startsWith('--') ? tok(c) : c), NH = D.hours.length, VIEWS = ['ground', 'paths', 'stops'];
// the page opens on open ground (Jacob, 19 Oct 2026: "open the heat map, by default, on "open ground" not "footpaths". it
// is visually clearer")
let view = 'ground', hi = D.start, mode = 'day', pop = null, ready = false;
// the alternative Thursdays (package.py --scenario NAME, one entry each): their own values, figures and images
const SCS = D.scenarios || {}; let scen = '';
const SC = () => scen ? SCS[scen] : null;
// where the figures are of (Jacob, 19 Oct 2026: "split the figures between the urban core and the greater extent"):
// the urban part, where most people live, first; the map shows the whole area either way
let where = D.urban ? 'urban' : '';
const FIG = () => { const F = scen ? SCS[scen] : D; return where && F.urban ? F.urban : F; };
const ST = () => FIG().stats, DST = () => FIG().day_stats || D.day.stats;
const NSTOPS = () => where ? D.urban.n_stops : D.n_stops;
// a scenario holds only the pieces and stops it changes ({index: values}); the first pass's values stand elsewhere
const pathVals = i => un((scen && SCS[scen].paths[i]) || D.paths[i][1]), stopVals = i => un((scen && SCS[scen].stops[i]) || D.stops[i].v);
const DCOLS = D.day.colors.map(tok), HOT = D.classes[D.hot].lo;

document.getElementById('when').textContent = `${D.area}, Thursday 13 August 2026`;
document.getElementById('h1').innerHTML = FIG().headline;
document.getElementById('deck').textContent = D.deck;
document.getElementById('src').innerHTML = D.sources;
document.getElementById('keyh').textContent = D.key;
const scale = document.getElementById('scale');
function drawKey() {
  scale.classList.remove('fine');
  if (mode === 'day') {
    document.getElementById('keyh').textContent = 'Hours that felt like 38 °C or more';
    scale.style.gridTemplateColumns = `repeat(${DCOLS.length}, 1fr)`;
    scale.innerHTML = DCOLS.map(c => `<i style="background:${c}"></i>`).join('') + D.day.labels.map(l => `<span>${l}</span>`).join('');
  } else {
    document.getElementById('keyh').textContent = D.key;
    scale.style.gridTemplateColumns = `repeat(${COLS.length}, 1fr)`;
    scale.classList.toggle('fine', COLS.length > 6);
    scale.innerHTML = COLS.map(c => `<i style="background:${c}"></i>`).join('') + D.classes.map(c => `<span>${c.label}</span>`).join('')
      + D.classes.map(c => `<span class="w${c.words ? ' edge' : ''}">${c.words || ''}</span>`).join('');
  }
}
// the method panel closes on its button, Escape (the dialog's own) or a click outside it
const dlg = document.getElementById('method');
document.getElementById('cred').textContent = D.credits;
document.getElementById('more').onclick = () => dlg.showModal();
document.getElementById('close').onclick = () => dlg.close();
dlg.addEventListener('click', ev => { const r = dlg.getBoundingClientRect();
  if (ev.clientX < r.left || ev.clientX > r.right || ev.clientY < r.top || ev.clientY > r.bottom) dlg.close(); });

// PMTiles archives: on the site each read in byte ranges from its file, once registered; in the artifact the basemap
// from memory
const protocol = new pmtiles.Protocol();
// an image tile the archive lacks (open ground with nothing to draw) comes back as an empty image: PMTiles gives no data
// for it, and MapLibre waits for such a tile for ever, so the map never finished loading
const EMPTY = Uint8Array.from(atob('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGNgAAIAAAUAAXpeqz8AAAAASUVORK5CYII='), c => c.charCodeAt(0));
maplibregl.addProtocol('pmtiles', async (params, ac) => {
  const r = await protocol.tile(params, ac);
  return r && r.data === null && params.type !== 'json' ? { data: EMPTY.slice().buffer } : r;
});
const archives = {};
const TS = {"basemap": "https://maps.weinbren.me/mk-heat/basemap.a623e72bb571.pmtiles", "features": "https://maps.weinbren.me/mk-heat/features.fd6be8f83fa4.pmtiles", "trees": "https://maps.weinbren.me/mk-heat/trees.ac4d3216e1df.pmtiles", "ground/06-stops": "https://maps.weinbren.me/mk-heat/ground/06-stops.b3024abb0ffb.pmtiles", "ground/06-trees": "https://maps.weinbren.me/mk-heat/ground/06-trees.bf8a13ee654b.pmtiles", "ground/06": "https://maps.weinbren.me/mk-heat/ground/06.7d6f580c438a.pmtiles", "ground/07-stops": "https://maps.weinbren.me/mk-heat/ground/07-stops.7a4a4c7d088e.pmtiles", "ground/07-trees": "https://maps.weinbren.me/mk-heat/ground/07-trees.7b8314c109fd.pmtiles", "ground/07": "https://maps.weinbren.me/mk-heat/ground/07.3330cdcc10d2.pmtiles", "ground/08-stops": "https://maps.weinbren.me/mk-heat/ground/08-stops.87bb09552d11.pmtiles", "ground/08-trees": "https://maps.weinbren.me/mk-heat/ground/08-trees.6ff512bc9364.pmtiles", "ground/08": "https://maps.weinbren.me/mk-heat/ground/08.42bdd93f92bc.pmtiles", "ground/09-stops": "https://maps.weinbren.me/mk-heat/ground/09-stops.e8f4234c484f.pmtiles", "ground/09-trees": "https://maps.weinbren.me/mk-heat/ground/09-trees.6cf6499a2639.pmtiles", "ground/09": "https://maps.weinbren.me/mk-heat/ground/09.288322b13b69.pmtiles", "ground/10-stops": "https://maps.weinbren.me/mk-heat/ground/10-stops.d800c4a072be.pmtiles", "ground/10-trees": "https://maps.weinbren.me/mk-heat/ground/10-trees.cf2cfabd9708.pmtiles", "ground/10": "https://maps.weinbren.me/mk-heat/ground/10.ef356aa49d34.pmtiles", "ground/11-stops": "https://maps.weinbren.me/mk-heat/ground/11-stops.9afb3c6636dd.pmtiles", "ground/11-trees": "https://maps.weinbren.me/mk-heat/ground/11-trees.2f3ca0815581.pmtiles", "ground/11": "https://maps.weinbren.me/mk-heat/ground/11.95573e08c59a.pmtiles", "ground/12-stops": "https://maps.weinbren.me/mk-heat/ground/12-stops.4ef2d788fac0.pmtiles", "ground/12-trees": "https://maps.weinbren.me/mk-heat/ground/12-trees.cc53e4193af9.pmtiles", "ground/12": "https://maps.weinbren.me/mk-heat/ground/12.e6f299402f25.pmtiles", "ground/13-stops": "https://maps.weinbren.me/mk-heat/ground/13-stops.6d89a4e3b583.pmtiles", "ground/13-trees": "https://maps.weinbren.me/mk-heat/ground/13-trees.b5d448a7e8bf.pmtiles", "ground/13": "https://maps.weinbren.me/mk-heat/ground/13.8be056d53639.pmtiles", "ground/14-stops": "https://maps.weinbren.me/mk-heat/ground/14-stops.b7d321a30465.pmtiles", "ground/14-trees": "https://maps.weinbren.me/mk-heat/ground/14-trees.0a150636e125.pmtiles", "ground/14": "https://maps.weinbren.me/mk-heat/ground/14.343aabfb5e8f.pmtiles", "ground/15-stops": "https://maps.weinbren.me/mk-heat/ground/15-stops.3a7690b700e2.pmtiles", "ground/15-trees": "https://maps.weinbren.me/mk-heat/ground/15-trees.f93ed033c67b.pmtiles", "ground/15": "https://maps.weinbren.me/mk-heat/ground/15.50beedf0f74e.pmtiles", "ground/16-stops": "https://maps.weinbren.me/mk-heat/ground/16-stops.74b5ebfb3199.pmtiles", "ground/16-trees": "https://maps.weinbren.me/mk-heat/ground/16-trees.48f12156570e.pmtiles", "ground/16": "https://maps.weinbren.me/mk-heat/ground/16.7878741644f8.pmtiles", "ground/17-stops": "https://maps.weinbren.me/mk-heat/ground/17-stops.1e00eb9e3803.pmtiles", "ground/17-trees": "https://maps.weinbren.me/mk-heat/ground/17-trees.19eb1301a07f.pmtiles", "ground/17": "https://maps.weinbren.me/mk-heat/ground/17.caf2ecc07b46.pmtiles", "ground/18-stops": "https://maps.weinbren.me/mk-heat/ground/18-stops.9103b6538f00.pmtiles", "ground/18-trees": "https://maps.weinbren.me/mk-heat/ground/18-trees.40936822ad05.pmtiles", "ground/18": "https://maps.weinbren.me/mk-heat/ground/18.34037ca70097.pmtiles", "ground/19-stops": "https://maps.weinbren.me/mk-heat/ground/19-stops.bc12d6c90aa5.pmtiles", "ground/19-trees": "https://maps.weinbren.me/mk-heat/ground/19-trees.ff6651cb17e5.pmtiles", "ground/19": "https://maps.weinbren.me/mk-heat/ground/19.f0693224d301.pmtiles", "ground/bld": "https://maps.weinbren.me/mk-heat/ground/bld.ccc95a97c47e.pmtiles", "ground/day-stops": "https://maps.weinbren.me/mk-heat/ground/day-stops.fe781bc609d9.pmtiles", "ground/day-trees": "https://maps.weinbren.me/mk-heat/ground/day-trees.67a1d44f08ed.pmtiles", "ground/day": "https://maps.weinbren.me/mk-heat/ground/day.31ae813a3cb9.pmtiles", "_ground": {"minzoom": 8, "maxzoom": 14, "bounds": [-0.895274, 51.960044, -0.582032, 52.205995]}, "_trees": {"minzoom": 15, "maxzoom": 15}};                                // each archive's address (site.py: R2, at maps.weinbren.me)
const tiles = k => { if (!archives[k]) { const t = new pmtiles.PMTiles(TS[k]); protocol.add(t); archives[k] = 'pmtiles://' + t.source.getKey(); } return archives[k]; };
class Mem { getKey() { return 'mk'; } async getBytes(o, l) { return { data: basemap.slice(o, o + l) }; } }
if (!SITE) protocol.add(new pmtiles.PMTiles(new Mem()));
// the label font (Protomaps' Noto Sans glyphs): the site's one file a face and range, the artifact's one file of all;
// a range it lacks comes back empty
maplibregl.addProtocol('glyphs', async params => {
  const [stack, range] = decodeURIComponent(params.url.slice('glyphs://'.length)).split('/');
  const face = stack.split(',')[0];
  if (SITE) {
    const f = `glyphs/${face.replace(/ /g, '_')}_${range}.pbf`;
    const r = V[f] ? await fetch(u(f)) : null;
    return { data: r && r.ok ? await r.arrayBuffer() : new ArrayBuffer(0) };
  }
  const b64 = (GLYPHS[face] || {})[range];
  return { data: b64 ? Uint8Array.from(atob(b64), c => c.charCodeAt(0)).buffer : new ArrayBuffer(0) };
});
const HALO = { 'text-color': tok('--ink'), 'text-halo-color': '#ffffff', 'text-halo-width': 1.6, 'text-halo-blur': 0.4 };
const kind = (...k) => ['in', ['get', 'kind'], ['literal', k]];
const AREA = ['match', ['geometry-type'], ['Polygon', 'MultiPolygon'], true, false];

// footpath pieces and stops from the compact file
// a feature's properties: its day as it was (v, a character an hour) and each scenario's (v_NAME), with the hours at
// 38 °C or more of each (d, d_NAME), so choosing a scenario only changes the colour rule
const HOTC = String.fromCharCode(D.classes[D.hot].lo + 35);
const hotHours = t => { let n = 0; for (const c of t) if (c >= HOTC) n++; return n; };
function props(i, g, t, scs) {
  const o = { i, g, v: t, d: hotHours(t) };
  for (const nm in SCS) { const u = SCS[nm][scs][i] || t; o['v_' + nm] = u; o['d_' + nm] = u === t ? o.d : hotHours(u); }
  return o;
}
const paths = SITE ? null : { type: 'FeatureCollection', features: D.paths.map((p, i) => {
  const c = []; let x = 0, y = 0;
  for (let k = 0; k < p[0].length; k += 2) { x += p[0][k]; y += p[0][k + 1]; c.push([x / 1e5, y / 1e5]); }
  return { type: 'Feature', geometry: { type: 'LineString', coordinates: c }, properties: props(i, p[2], p[1], 'paths') };
}) };
const stops = SITE ? null : { type: 'FeatureCollection', features: D.stops.map((s, i) =>
  ({ type: 'Feature', geometry: { type: 'Point', coordinates: [s.x, s.y] }, properties: props(i, s.g, s.v, 'stops') })) };
// a scenario's value where it changes the feature (the site's tiles hold only those), else the day as it was
const pick = (k, s = scen) => s ? ['coalesce', ['get', k + '_' + s], ['get', k]] : ['get', k];
const dayCls = (s = scen) => { const e = ['step', pick('d', s), DCOLS[0]]; D.day.lo.slice(1).forEach((lo, k) => e.push(lo, DCOLS[k + 1])); return ['case', ['==', ['get', 'g'], 1], tok('--grey'), ['==', ['get', 'g'], 2], tok('--grey'), e]; };
// the footpaths and stops have a layer for the day and one for each hour: the slider shows one and hides the one
// before, which redraws in a frame. One layer recoloured at each step made MapLibre parse every tile again, and the
// tiles came back one by one, a patchwork of two hours (Jacob, 18 Oct 2026: "when I use the slider it still flashes
// weirdly between hours"). A colour that follows the features is set when MapLibre parses a tile, for every layer of
// the tile's source at once, so a recoloured layer showed the scenario before for seconds, then jumped (Jacob,
// 20 Oct 2026: "when I click 10 percent more trees, it shows as it was paths then it flashes to 10 percent more
// trees"). So the day's layer is one for each scenario, made with the map: a scenario's button shows its layer. The
// hours' layers are made when the hour view first shows, for the scenario shown (makeHours): the day view, where the
// page opens, parses its tiles for six colour layers, not thirty.
const SKEYS = ['', ...Object.keys(SCS)];
const dayKey = s => 'day' + (s ? '-' + s : '');
const HKEYS = D.hours.map((_, k) => k);
// an opacity changes at once: MapLibre fades paint changes over 300 ms by default, and two layers fading against each
// other let the map show through between hours
const NOW = { duration: 0, delay: 0 };
// the ground's image for the hour or the day: on the site one raster archive (ground/<name>.pmtiles), in the artifact
// pieces of at most 4,096 px a side (package.py), each piece its own image source and layer
const groundName = (k = hi) => `${mode === 'day' ? 'day' : D.hours[k].file}${scen ? '-' + scen : ''}`;
const groundUrl = (id, k = hi) => u(`ground/${groundName(k)}_${id}.png`);
const PIECES = D.pieces;
// the ground images load only while the ground view is shown (the city's are 3 MB an hour); else an empty pixel
const BLANK = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGNgAAIAAAUAAXpeqz8AAAAASUVORK5CYII=';
const groundNow = id => view === 'ground' ? groundUrl(id) : BLANK;
// an image is asked for only when it changes (asking again while one loads cancels that load)
const showing = Object.fromEntries(PIECES.map(p => [p.id, BLANK]));
// on the site each image (the day and every hour, as it was and in each scenario) is its own layer. The one on screen
// stays until every tile of the one asked for is in, then the two swap in one frame (swapGround), so the map never shows
// half of one hour over another; the hours either side load unseen, so a step of the slider usually swaps at once
// (Jacob, 18 Oct 2026: "dragging the slider causes the map to flash between loading different pmtiles"; "it still
// flashes weirdly between hours"); the rest stay hidden and fetch nothing
const GROUNDS = SITE ? Object.keys(TS).filter(k => k.startsWith('ground/') && k !== 'ground/bld').map(k => k.slice(7)) : [];
// an image's tiles named directly (its zooms from site.py), so a hidden image's archive is not read at all
const rasterOf = k => ({ type: 'raster', tiles: [tiles(k) + '/{z}/{x}/{y}'], tileSize: 512, minzoom: TS._ground.minzoom,
                         maxzoom: TS._ground.maxzoom, bounds: TS._ground.bounds });
let groundOn = new Set(), groundShown = '', groundWant = '';
const showGround = () => {
  if (SITE) {
    const want = new Map();
    groundWant = view === 'ground' ? groundName() : '';
    if (!groundWant || !groundShown) groundShown = groundWant;     // nothing on screen to keep: it shows as it loads
    if (groundWant) {
      want.set(groundShown, 1);
      if (groundWant !== groundShown) want.set(groundWant, 0);
      if (mode === 'hour') [hi - 1, hi + 1].filter(k => k >= 0 && k < NH).forEach(k => { if (!want.has(groundName(k))) want.set(groundName(k), 0); });
    }
    for (const g of GROUNDS) {
      const id = 'ground:' + g, on = want.has(g);
      if (on || groundOn.has(g)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
      if (on) map.setPaintProperty(id, 'raster-opacity', want.get(g));
    }
    groundOn = new Set(want.keys());
    return;
  }
  PIECES.forEach(p => { const v = groundNow(p.id); if (v !== showing[p.id]) { showing[p.id] = v; map.getSource('g' + p.id).updateImage({ url: v, coordinates: p.corners }); } });
};
// after each frame: once every tile the view needs of the image asked for is in, it takes the place of the one shown.
// Only after a frame: a source whose layers were all hidden counts as loaded until MapLibre has asked for its tiles
const swapGround = () => { if (groundWant && groundWant !== groundShown && map.isSourceLoaded('g:' + groundWant)) { groundShown = groundWant; showGround(); } };
// the day's or the hour's layer of the view shown (footpaths or stops), the one shown before hidden in the same frame
let linesOn = { paths: null, stops: null };
const showLines = () => {
  // in the hour view, the hours' set shown (that of the scenario before while the new one is parsed), else the day's
  const k = mode === 'day' || !hourSet ? dayKey(scen) : `${hi}.${hourSet.n}`;
  [['paths', 'line-opacity'], ['stops', 'circle-opacity']].forEach(([v, prop]) => {
    const want = view === v ? k : null;
    if (want === linesOn[v] || (want !== null && !map.getLayer(v + ':' + want))) return;   // (an hour of the set before)
    if (want !== null) map.setPaintProperty(v + ':' + want, prop, 1);
    if (linesOn[v] !== null) map.setPaintProperty(v + ':' + linesOn[v], prop, 0);
    linesOn[v] = want;
  });
};
// the hours' layers, a set for one scenario ({scen, n}; layer ids paths:<hour>.<n>): a new set is added hidden beside
// the one shown, and takes its place in one frame once every tile of the source has been parsed with it (swapHours,
// after each frame, as swapGround), so the map never shows a patchwork of two scenarios; the set before is then removed.
// Meanwhile the hour view shows the set before (a scenario switched in the hour view shows once, when ready), or the
// day's layer of the scenario when there is none of it (the hour view opened after a switch in the day view)
let hourSet = null, hourNext = null, hourN = 0;
// a set's layers, but those shown (the set before keeps its hour shown while the next is parsed: MapLibre parses a tile
// for every layer of its source, so the hours that cannot show then are removed first; the slider waits meanwhile)
const dropHours = (set, keep = []) => HKEYS.forEach(k => ['paths', 'stops'].forEach(v => {
  const id = `${v}:${k}.${set.n}`; if (map.getLayer(id) && !keep.includes(id)) map.removeLayer(id); }));
function makeHours() {
  if (hourNext && hourNext.scen !== scen) { dropHours(hourNext); hourNext = null; }
  if (hourSet && hourSet.scen !== scen && mode === 'day') { dropHours(hourSet); hourSet = null; }
  const have = hourNext || (hourSet && !hourSet.part ? hourSet : null);
  if (mode !== 'hour' || (have && have.scen === scen)) return;
  if (hourSet && !hourSet.part) { dropHours(hourSet, Object.entries(linesOn).filter(([, k]) => k !== null).map(([v, k]) => v + ':' + k)); hourSet.part = true; }
  hourNext = { scen, n: ++hourN };
  HKEYS.forEach(k => { map.addLayer(pathLayer(`${k}.${hourN}`, cls(k)), D.urban ? 'urban' : 'trees'); map.addLayer(stopLayer(`${k}.${hourN}`, cls(k)), 'stops'); });
}
// MapLibre sends the tiles to be parsed again at the start of the frame after a layer is added, so from the end of that
// frame (the render event) the source counts as loaded only once every tile has come back
const swapHours = () => {
  if (!hourNext || !['paths', 'stops'].every(v => map.isSourceLoaded(src(v).source))) return;
  const old = hourSet; hourSet = hourNext; hourNext = null;
  showLines(); if (old) dropHours(old);
};
// an hour's colour: the hour's character matched to its class (build.py's characters are values -34 to 56)
const cls = (h, s = scen) => {
  const e = ['match', ['slice', pick('v', s), h, h + 1]];
  D.classes.forEach((c, k) => { if (!k) return; const top = k + 1 < D.classes.length ? D.classes[k + 1].lo : 57, ch = [];
    for (let v = c.lo; v < top; v++) ch.push(String.fromCharCode(v + 35)); if (ch.length) e.push(ch, COLS[k]); });
  e.push(COLS[0]);
  return ['case', ['==', ['get', 'g'], 1], tok('--grey'), ['==', ['get', 'g'], 2], tok('--grey'), e];
};
const classOf = v => { let k = 0; D.classes.forEach((c, j) => { if (v >= c.lo) k = j; }); return k; };

const [[w, s], [e, n]] = D.bounds, pw = (e - w) * 0.35, ph = (n - s) * 0.35;
const BLDG_FADE = ['interpolate', ['linear'], ['zoom'], 15, 0, 16, 1];
// where a layer of the model's own reads from: the site's vector archive (features.pmtiles) or the artifact's JSON
const src = name => SITE ? { source: 'f', 'source-layer': name } : { source: name };
const GROUND_PAINT = { 'raster-resampling': 'nearest', 'raster-fade-duration': 0, 'raster-opacity-transition': NOW };
const LINE = { 'line-cap': 'round', 'line-join': 'round' };
const STOP_R = ['interpolate', ['linear'], ['zoom'], 12, 4, 14, 6.5, 17, 11];
// a colour layer of the footpaths or the stops, hidden until shown
const pathLayer = (k, colour) => ({ id: 'paths:' + k, type: 'line', ...src('paths'), layout: LINE,
  paint: { 'line-color': colour, 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 1.6, 14, 3.2, 17, 7], 'line-opacity': 0, 'line-opacity-transition': NOW } });
const stopLayer = (k, colour) => ({ id: 'stops:' + k, type: 'circle', ...src('stops'),
  paint: { 'circle-color': colour, 'circle-radius': STOP_R, 'circle-opacity': 0, 'circle-opacity-transition': NOW } });
const BLDG_PAINT = { 'raster-opacity': ['interpolate', ['linear'], ['zoom'], 12, 0.5, 14, 1], 'raster-resampling': 'nearest', 'raster-fade-duration': 0 };
const style = {
  version: 8,
  glyphs: 'glyphs://{fontstack}/{range}',
  sources: {
    b: { type: 'vector', url: SITE ? tiles('basemap') : 'pmtiles://mk', attribution: D.credits },
    ...(D.urban ? { urban: { type: 'geojson', data: D.urban.outline } } : {}),
    ...(SITE ? {
      f: { type: 'vector', url: tiles('features') },
      // the new trees in their own archive, from the zoom they are drawn at (site.py), named tile by tile so nothing of it
      // is read until a plan's trees show
      ...(TS.trees ? { t: { type: 'vector', tiles: [tiles('trees') + '/{z}/{x}/{y}'], minzoom: TS._trees.minzoom, maxzoom: TS._trees.maxzoom } } : {}),
      ...Object.fromEntries(GROUNDS.map(g => ['g:' + g, rasterOf('ground/' + g)])),
      bl: rasterOf('ground/bld'),
    } : {
      ...Object.fromEntries(PIECES.flatMap(p => [['g' + p.id, { type: 'image', url: BLANK, coordinates: p.corners }],
                                                  ['b' + p.id, { type: 'image', url: u(`ground/bld_${p.id}.png`), coordinates: p.corners }]])),
      // every piece at every zoom: MapLibre's default tolerance (0.375 px) drops a line shorter than about half a pixel,
      // so the city's 25 m pieces vanished below zoom 11 (the whole city on a phone opens at 9.9)
      paths: { type: 'geojson', data: paths, tolerance: 0 },
      stops: { type: 'geojson', data: stops },
      grey: { type: 'geojson', data: D.grey },
      trees: { type: 'geojson', data: { type: 'FeatureCollection', features: [] } },
    }),
  },
  layers: [
    { id: 'bg', type: 'background', paint: { 'background-color': tok('--ground') } },
    // fills take polygons only: a fill layer closes a line into a shape, and the water layer holds rivers and canals as
    // lines, which drew as wide blue wedges (Jacob, 18 Oct 2026: "the zoomed out map's style is glitchy see the floating
    // blu chunks"); the lines are drawn as lines
    { id: 'green', type: 'fill', source: 'b', 'source-layer': 'landuse', filter: ['all', AREA, kind('park', 'recreation_ground', 'golf_course', 'cemetery', 'garden', 'pitch', 'playground', 'nature_reserve', 'wood', 'forest', 'grass', 'village_green')], paint: { 'fill-color': '#edf0e9' } },
    { id: 'water', type: 'fill', source: 'b', 'source-layer': 'water', filter: AREA, paint: { 'fill-color': '#dce7ed' } },
    { id: 'water-line', type: 'line', source: 'b', 'source-layer': 'water', filter: ['!', AREA],
      paint: { 'line-color': '#c9dbe5', 'line-width': ['interpolate', ['linear'], ['zoom'], 10, 0.6, 15, 2] } },
    ...(SITE ? GROUNDS.map(g => ({ id: 'ground:' + g, type: 'raster', source: 'g:' + g, layout: { visibility: 'none' }, paint: { 'raster-opacity': 0, ...GROUND_PAINT } }))
      : PIECES.map(p => ({ id: 'ground' + p.id, type: 'raster', source: 'g' + p.id, paint: { 'raster-opacity': 0, ...GROUND_PAINT } }))),
    // minor roads from zoom 13, fading in over half a zoom: the basemap holds none at zoom 11, some at 12 and all from 13
    // (measured over central MK), so drawn from 12 they popped in and out as the zoom crossed 12 and 13 (Jacob,
    // 18 Oct 2026: "some roads/paths clip in and out when I zoom in and out")
    ...[['major', kind('highway', 'major_road'), 0, 1], ['minor', kind('minor_road'), 13, ['interpolate', ['linear'], ['zoom'], 13, 0, 13.5, 1]]].flatMap(([k, f, mz, op]) => [
      { id: 'road-case-' + k, type: 'line', source: 'b', 'source-layer': 'roads', filter: f, minzoom: mz,
        paint: { 'line-color': '#e6e4df', 'line-opacity': op, 'line-width': ['interpolate', ['exponential', 1.6], ['zoom'], 12, 1.2, 18, 16] } },
      { id: 'road-' + k, type: 'line', source: 'b', 'source-layer': 'roads', filter: f, minzoom: mz,
        paint: { 'line-color': '#ffffff', 'line-opacity': op, 'line-width': ['interpolate', ['exponential', 1.6], ['zoom'], 12, 0.6, 18, 13] } }]),
    { id: 'rail', type: 'line', source: 'b', 'source-layer': 'roads', filter: kind('rail'), paint: { 'line-color': '#bdb9b2', 'line-width': 1.2 } },
    // buildings fade in over zoom 15 to 16: the basemap holds them all only from its zoom 15 tiles
    // buildings as the model saw them (2021 lidar), in every view; OSM's outlines are incomplete here
    ...(SITE ? [{ id: 'bldg', type: 'raster', source: 'bl', paint: BLDG_PAINT }]
      : PIECES.map(p => ({ id: 'bldg' + p.id, type: 'raster', source: 'b' + p.id, paint: BLDG_PAINT }))),
    { id: 'grey', type: 'fill', ...src('grey'), paint: { 'fill-pattern': 'hatch', 'fill-opacity': 0.9 } },
    { id: 'grey-line', type: 'line', ...src('grey'), paint: { 'line-color': tok('--grey'), 'line-width': 0.8 } },
    // the paths' white edge, also what a click on a path hits
    { id: 'paths-case', type: 'line', ...src('paths'), layout: LINE,
      paint: { 'line-color': '#ffffff', 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 3, 14, 5.5, 17, 10], 'line-opacity': view === 'paths' ? 1 : 0, 'line-opacity-transition': NOW } },
    ...SKEYS.map(s => pathLayer(dayKey(s), dayCls(s))),
    // the urban part's edge while its figures show, over the footpaths (under them it was lost among them)
    ...(D.urban ? [{ id: 'urban', type: 'line', source: 'urban', layout: { visibility: where ? 'visible' : 'none' },
                     paint: { 'line-color': tok('--ink'), 'line-width': 1.6, 'line-opacity': 0.85, 'line-dasharray': [3, 2] } }] : []),
    // the scenario's new trees, from zoom 15 only and half see-through, so the colours beneath show what they change
    // (Jacob, 18 Oct 2026: "the trees cover the map so it is hard to see their effect"); true size from zoom 17
    { id: 'trees', type: 'circle', ...(SITE && TS.trees ? { source: 't', 'source-layer': 'trees' } : src('trees')), minzoom: 15, layout: { visibility: 'none' },
      paint: { 'circle-color': '#2f5a2b', 'circle-opacity': 0.55, 'circle-radius': ['interpolate', ['exponential', 2], ['zoom'], 15, 1.5, 17, 3.4, 18, 6.8] } },
    ...SKEYS.map(s => stopLayer(dayKey(s), dayCls(s))),
    // the stops' rings over their colour, also what a click on a stop hits
    { id: 'stops', type: 'circle', ...src('stops'),
      paint: { 'circle-color': '#ffffff', 'circle-radius': STOP_R, 'circle-opacity': 0, 'circle-stroke-color': tok('--ink'),
               'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 12, 0.6, 16, 1.2], 'circle-stroke-opacity': 0, 'circle-stroke-opacity-transition': NOW } },
    // names, all from the basemap (Protomaps' min_zoom ranks them: lower is more important and wins a clash); a higher
    // layer wins over a lower one: places, then parks and lakes, then landmarks, then roads
    ...['major_road', 'minor_road'].map((k, n) => ({ id: 'lab-' + k, type: 'symbol', source: 'b', 'source-layer': 'roads', minzoom: n ? 16 : 14,
      filter: ['all', ['has', 'name'], ['==', ['get', 'kind'], k]],
      layout: { 'symbol-placement': 'line', 'text-field': ['get', 'name'], 'text-font': ['Noto Sans Medium'], 'text-size': 13, 'symbol-spacing': 420, 'text-padding': 4 },
      paint: { ...HALO, 'text-color': '#4d4b46' } })),
    { id: 'lab-landmark', type: 'symbol', source: 'b', 'source-layer': 'pois', minzoom: 13,
      filter: ['all', ['has', 'name'], ['in', ['get', 'kind'], ['literal', ['mall', 'station', 'train_station', 'hospital', 'university', 'museum', 'theatre', 'music_venue', 'stadium', 'marketplace', 'retail', 'cinema', 'arts_centre', 'theme_park']]]],
      layout: { 'text-field': ['get', 'name'], 'text-font': ['Noto Sans Medium'], 'text-size': 13, 'text-padding': 6, 'text-max-width': 9, 'symbol-sort-key': ['get', 'min_zoom'] },
      paint: { ...HALO } },
    { id: 'lab-green', type: 'symbol', source: 'b', 'source-layer': 'pois', minzoom: 12,
      filter: ['all', ['has', 'name'], ['in', ['get', 'kind'], ['literal', ['park', 'nature_reserve', 'wood', 'forest', 'garden', 'water', 'lake', 'reservoir']]]],
      layout: { 'text-field': ['get', 'name'], 'text-font': ['Noto Sans Italic'], 'text-size': 13.5, 'text-padding': 6, 'text-max-width': 9, 'symbol-sort-key': ['get', 'min_zoom'] },
      paint: { ...HALO, 'text-color': ['match', ['get', 'kind'], ['water', 'lake', 'reservoir'], '#3f6a84', '#466041'] } },
    { id: 'lab-place', type: 'symbol', source: 'b', 'source-layer': 'places',
      filter: ['all', ['has', 'name'], ['in', ['get', 'kind'], ['literal', ['locality', 'neighbourhood']]], ['!=', ['get', 'name'], 'Milton Keynes']],
      layout: { 'text-field': ['get', 'name'], 'text-font': ['Noto Sans Medium'], 'text-padding': 8, 'text-max-width': 9, 'symbol-sort-key': ['get', 'min_zoom'],
                'text-size': ['match', ['get', 'kind_detail'], ['city', 'town'], 17, 14.5] },
      paint: { ...HALO } },
  ],
};
// on a phone the card covers the bottom of the screen: the city fits in the space above it
const fitPad = () => innerWidth > 640 ? { left: document.getElementById('card').offsetWidth + 32, right: 30, top: 30, bottom: 30 } : { left: 10, right: 10, top: 10, bottom: document.getElementById('card').offsetHeight + 10 };
// two threads parse the tiles where MapLibre's default outside Safari is one (Safari: up to three): measured on this page
// (20 Oct 2026, Chrome, the opening view), the first load to every tile 2.2 s with one, 1.6 s with two (three no
// faster), and the hour view's layers ready in 0.8 to 1.2 s, not 1.5
if (maplibregl.getWorkerCount() < 2 && (navigator.hardwareConcurrency || 1) >= 2) maplibregl.setWorkerCount(2);
const map = new maplibregl.Map({ container: 'map', style, bounds: D.bounds, fitBoundsOptions: { padding: fitPad() }, maxZoom: 18.5,
  attributionControl: false, dragRotate: false, pitchWithRotate: false, renderWorldCopies: false });
map.touchZoomRotate.disableRotation();
// panning stops a little beyond the city, and never inside the first view: on a tall phone screen that view is taller than
// the city with its margin, and a limit set first made the map zoom in past the fit, half the city behind the card
const vb = map.getBounds();
map.setMaxBounds([[Math.min(w - pw, vb.getWest()), Math.min(s - ph, vb.getSouth())], [Math.max(e + pw, vb.getEast()), Math.max(n + ph, vb.getNorth())]]);
map.setMinZoom(Math.max(0, map.getZoom() - 1));
map.addControl(new maplibregl.ScaleControl({ maxWidth: 110, unit: 'metric' }), 'bottom-right');
map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');
// the credits stay closed until asked for: MapLibre opens its compact credits across the screen when they first
// arrive and closes them at the first move, which moved the page as it loaded (Lighthouse, phone); the first opening it
// makes itself is undone before the next paint, and the "i" button still opens them
const attribEl = document.querySelector('.maplibregl-ctrl-attrib');
if (attribEl) {
  const shut = () => { if (attribEl.classList.contains('maplibregl-compact-show')) { attribEl.classList.remove('maplibregl-compact-show'); attribEl.removeAttribute('open'); mo.disconnect(); } };
  const mo = new MutationObserver(shut); mo.observe(attribEl, { attributes: true, attributeFilter: ['class'] }); shut();
}
map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
map.on('styleimagemissing', ev => {
  if (ev.id !== 'hatch') return;
  const z = 8, c = document.createElement('canvas'); c.width = c.height = z; const g = c.getContext('2d');
  g.fillStyle = 'rgba(245,245,243,0.85)'; g.fillRect(0, 0, z, z); g.strokeStyle = tok('--grey'); g.lineWidth = 1.2;
  g.beginPath(); g.moveTo(0, z); g.lineTo(z, 0); g.moveTo(-z / 2, z / 2); g.lineTo(z / 2, -z / 2); g.moveTo(z / 2, z * 1.5); g.lineTo(z * 1.5, z / 2); g.stroke();
  map.addImage('hatch', g.getImageData(0, 0, z, z));
});

// hour of day
const slider = document.getElementById('hour'); slider.max = NH - 1; slider.value = hi;
document.getElementById('ticks').innerHTML = D.ticks.map(t => `<span>${t}</span>`).join('');
const bars = document.getElementById('bars');
function drawBars() {
  const dpr = devicePixelRatio || 1, W = bars.clientWidth, H = bars.clientHeight; bars.width = W * dpr; bars.height = H * dpr;
  const g = bars.getContext('2d'); g.scale(dpr, dpr); g.clearRect(0, 0, W, H);
  if (mode === 'day') {
    // one bar: the view's share in each class of hours at 38 °C or more, as the key
    let x = 0; const y = 14, bh = 24;
    g.font = `600 12px ${tok('--font')}`; g.textBaseline = 'middle';
    DST()[view].forEach((f, c) => {
      const w = f * W; g.fillStyle = DCOLS[c]; g.fillRect(x, y, Math.max(0, w - 2), bh);
      if (w > 34) { g.fillStyle = c >= 2 ? '#ffffff' : tok('--ink'); g.fillText(`${Math.round(f * 100)}%`, x + 6, y + bh / 2); }
      x += w;
    });
    g.fillStyle = tok('--muted'); g.font = `400 11.5px ${tok('--font')}`; g.textBaseline = 'alphabetic';
    g.fillText(`${view === 'stops' ? 'Bus stops' : view === 'paths' ? 'Footpaths' : 'Open ground'} by hours at 38 °C or more`, 0, 9);
    return;
  }
  const bw = W / NH;
  ST()[view].forEach((sh, k) => {
    let y = H - 1;
    sh.forEach((f, c) => { const bh = f * (H - 4); g.fillStyle = COLS[c]; g.globalAlpha = mode === 'day' || k === hi ? 1 : 0.5; g.fillRect(k * bw + 1.5, y - bh, bw - 3, bh); y -= bh; });
  });
  g.globalAlpha = 1; if (mode === 'hour') { g.strokeStyle = tok('--ink'); g.lineWidth = 1.5; g.strokeRect(hi * bw + 0.75, 0.75, bw - 1.5, H - 1.5); }
}
function render() {
  const H = D.hours[hi];
  document.getElementById('h1').innerHTML = FIG().headline;
  document.getElementById('deck').textContent = (scen ? FIG() : D).deck;
  document.getElementById('m-day').setAttribute('aria-pressed', mode === 'day');
  document.getElementById('m-hour').setAttribute('aria-pressed', mode === 'hour');
  document.getElementById('m-hour').textContent = H.label;
  slider.classList.toggle('idle', mode === 'day');
  document.getElementById('air').textContent = mode === 'day' ? `Air peaked at ${D.day.peak_ta.toFixed(0)} °C` : `Air ${H.ta.toFixed(0)} °C, ${H.rh}% humidity`;
  if (D.views_head) document.getElementById('vh').textContent = mode === 'day' ? D.views_head.day : D.views_head.hour.replace('{h}', H.label);
  VIEWS.forEach(v => {
    const share = mode === 'day' ? 1 - DST()[v][0] : ST()[v][hi].slice(D.hot).reduce((a, b) => a + b, 0);
    document.getElementById('n-' + v).textContent = v === 'stops' ? Math.round(share * NSTOPS()).toLocaleString('en-GB') : `${Math.round(share * 100)}%`;
    document.getElementById('s-' + v).textContent = (where ? D.urban.view_small : mode === 'day' ? D.view_small_day : D.view_small)[v];
  });
  if (ready) { showGround(); prefetch(); showLines(); }
  drawKey(); drawBars(); if (pop) pop.refresh();
}
function setHour(k) { hi = k; mode = 'hour'; slider.value = k; render(); if (ready) makeHours(); }
function setMode(m) { mode = m; render(); if (ready) makeHours(); }
function showTrees() {
  map.setLayoutProperty('trees', 'visibility', scen ? 'visible' : 'none');
  if (SITE) { map.setFilter('trees', ['==', ['get', 's'], scen]); return; }
  map.getSource('trees').setData({ type: 'FeatureCollection', features: (scen ? SCS[scen].trees : []).map(c => ({ type: 'Feature', geometry: { type: 'Point', coordinates: c }, properties: {} })) });
  map.setLayoutProperty('trees', 'visibility', scen ? 'visible' : 'none');
}
function setScen(name) {
  scen = name;
  document.querySelectorAll('#scbtns button').forEach(b => b.setAttribute('aria-pressed', b.dataset.s === name));
  const note = document.getElementById('scnote'); note.hidden = !name; note.textContent = name ? SCS[name].note : '';
  if (name && SCS[name].view && SCS[name].view !== view) setView(SCS[name].view);   // the stop trees show on the stops
  render();                                  // the day's layer of the scenario shows at once (showLines)
  if (ready) {
    showTrees();
    makeHours();                             // the hours' layers of the scenario, when an hour is shown
  }
}
if (Object.keys(SCS).length) {
  const box = document.getElementById('scbtns');
  if (box.children.length === 1)                      // build.py writes the buttons into the page; else here
    for (const [nm, S] of Object.entries(SCS)) box.insertAdjacentHTML('beforeend', `<button type="button" data-s="${nm}" aria-pressed="false">${S.label}</button>`);
  document.getElementById('scen').hidden = false;
  box.querySelectorAll('button').forEach(b => b.onclick = () => setScen(b.dataset.s));
}
function setWhere(a) {
  where = a;
  document.querySelectorAll('#where button').forEach(b => b.setAttribute('aria-pressed', b.dataset.a === a));
  if (ready) map.setLayoutProperty('urban', 'visibility', a ? 'visible' : 'none');
  render();
}
if (D.urban) {
  document.getElementById('where').hidden = false;
  document.querySelectorAll('#where button').forEach(b => b.onclick = () => setWhere(b.dataset.a));
}
function setView(v) {
  view = v;
  document.querySelectorAll('.view').forEach(b => b.setAttribute('aria-pressed', b.dataset.v === v));
  if (ready) {
    if (!SITE) PIECES.forEach(p => map.setPaintProperty('ground' + p.id, 'raster-opacity', v === 'ground' ? 1 : 0));
    showGround();
    showLines();
    map.setPaintProperty('paths-case', 'line-opacity', v === 'paths' ? 1 : 0);
    map.setPaintProperty('stops', 'circle-stroke-opacity', v === 'stops' ? 1 : 0);
  }
  if (pop) pop.remove();
  drawBars(); prefetch();
}
slider.oninput = () => setHour(+slider.value);
document.getElementById('m-day').onclick = () => setMode('day');
document.getElementById('m-hour').onclick = () => setMode('hour');
bars.onclick = ev => setHour(Math.min(NH - 1, Math.floor(ev.offsetX / bars.clientWidth * NH)));
document.querySelectorAll('.view').forEach(b => b.onclick = () => setView(b.dataset.v));
addEventListener('keydown', ev => {
  if (ev.target.closest && ev.target.closest('input')) return;
  if (ev.key === 'ArrowRight' || ev.key === 'ArrowLeft') setHour(Math.max(0, Math.min(NH - 1, hi + (ev.key === 'ArrowRight' ? 1 : -1))));
  if (ev.key === 'd') setMode('day');
  if (['1', '2', '3'].includes(ev.key)) setView(VIEWS[+ev.key - 1]);
});
addEventListener('resize', drawBars);
// the hours either side of the one shown, fetched ahead so the slider steps without a wait (the city's images are
// too many to fetch all at once)
const fetched = new Set();
function prefetch() {
  if (SITE || mode === 'day' || view !== 'ground') return;
  [hi - 1, hi + 1].filter(k => k >= 0 && k < NH).forEach(k => PIECES.forEach(p => {
    const u = groundUrl(p.id, k); if (!fetched.has(u)) { fetched.add(u); const im = new Image(); im.src = u; }
  }));
}

// a place's day: one cell an hour, like a row of a timetable
const note = vals => (mode === 'hour' ? D.now_fmt.replace('{v}', vals[hi]) + ' ' : '') + D.count_fmt.replace('{n}', vals.filter(v => v >= HOT).length).replace('{N}', NH);
function timetable(vals, title, sub) {
  const cells = vals.map((v, k) => `<i style="background:${COLS[classOf(v)]}" class="${mode === 'hour' && k === hi ? 'on' : ''}" title="${D.hours[k].label}: ${v}${D.unit}"></i>`).join('');
  const lab = D.hours.map((H, k) => `<span>${k % 3 === 0 ? H.short : ''}</span>`).join('');
  return `<div class="pop"><h3>${title}</h3><p>${sub}</p><div class="tt" style="--n:${NH}">${cells}${lab}</div><p class="sum">${note(vals)}</p></div>`;
}
const notModelled = t => `<div class="pop"><h3>${t}</h3><p class="sum">Built since the lidar survey, not modelled.</p></div>`;
function openPop(lngLat, html) {
  if (pop) pop.remove();
  pop = new maplibregl.Popup({ closeButton: true, maxWidth: '320px', focusAfterOpen: false }).setLngLat(lngLat).setHTML(html()).addTo(map);
  pop.refresh = () => pop.setHTML(html()); pop.on('close', () => { pop = null; });
}
// a clicked feature's day: the site's from the tile's own properties, the artifact's from the JSON by index
const valsOf = (f, kind) => SITE ? un(f.properties[scen && f.properties['v_' + scen] ? 'v_' + scen : 'v'])
  : (kind === 'stops' ? stopVals : pathVals)(f.properties.i);
map.on('click', 'stops', ev => {
  if (view !== 'stops') return;
  const f = ev.features[0], st = SITE ? { ...f.properties, x: f.geometry.coordinates[0], y: f.geometry.coordinates[1] } : D.stops[f.properties.i];
  openPop([st.x, st.y], () => st.g === 2 ? `<div class="pop"><h3>${st.n}</h3><p>${st.m}</p><p class="sum">Under a canopy or overhang, so in shade all day. The lidar cannot see under it, so it is not modelled.</p></div>`
    : st.g ? notModelled(st.n) : timetable(valsOf(f, 'stops'), st.n, st.m + (st.sh ? ' · has a shelter' : '')));
});
map.on('click', 'paths-case', ev => {
  if (view !== 'paths') return;
  const f = ev.features[0], g = SITE ? f.properties.g : D.paths[f.properties.i][2];
  openPop(ev.lngLat, () => g === 2 ? `<div class="pop"><h3>Underpass or covered path</h3><p class="sum">Under a bridge or roof, so in shade all day. The lidar cannot see under it, so it is not modelled.</p></div>`
    : g ? notModelled('Footpath') : timetable(valsOf(f, 'paths'), 'This stretch of path', 'Up to 25 m of path'));
});
[['stops', 'stops'], ['paths', 'paths-case']].forEach(([v, l]) => {
  map.on('mouseenter', l, () => { if (view === v) map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', l, () => { map.getCanvas().style.cursor = ''; });
});
// the controls work before the map has loaded (the card is drawn first); the map takes their state when it has
render();
window.mkmap = map;                          // for timing the page's interactions from outside (tests only read it)
map.on('load', () => {
  ready = true; setView(view); showTrees(); makeHours(); render();
  if (SITE) map.on('render', swapGround);
  map.on('render', swapHours);
  document.querySelector('.maplibregl-ctrl-attrib')?.classList.remove('maplibregl-compact-show');   // credits fold behind the (i)
});
})().catch(err => { document.getElementById('h1').textContent = 'The map could not load. Reload the page to try again.'; console.error(err); });
