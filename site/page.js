
(async () => {
const css = getComputedStyle(document.documentElement), tok = k => css.getPropertyValue(k).trim();
// two builds of one page (build.py): 'site', for a host that serves byte ranges, reads every map layer from PMTiles
// (the basemap, the footpaths, stops, greyed areas and new trees as vector tiles, the ground as raster tiles), so a
// visitor fetches only the tiles in view (Jacob, 18 Oct 2026: "serve as much as you can via pmtiles"); 'artifact', for
// claude.ai, which serves no .pmtiles, carries the basemap and the label font as text and the footpaths as JSON.
// Every file is asked for with its own content's hash (V), so it can be kept a year and a new build fetches only what
// changed
const MODE = 'site', SITE = MODE === 'site', V = {"meta.json":"08e14a3d7b","glyphs/Noto_Sans_Italic_0-255.pbf":"087b2484de","glyphs/Noto_Sans_Italic_8192-8447.pbf":"8572c4bca4","glyphs/Noto_Sans_Medium_0-255.pbf":"e3a9b013c2","glyphs/Noto_Sans_Medium_8192-8447.pbf":"6331ce179e"};
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
const NAME = { ground: 'Open ground', paths: 'Footpaths', stops: 'Bus stops' };
// the page opens on open ground (Jacob, 19 Oct 2026: "open the heat map, by default, on "open ground" not "footpaths". it
// is visually clearer")
let view = 'ground', hi = D.start, mode = 'day', pop = null, ready = false;
// the alternative Thursdays (package.py --scenario NAME, one entry each): their own values, figures and images
const SCS = D.scenarios || {}; let scen = '';
const SC = () => scen ? SCS[scen] : null;
// where the figures are of (Jacob, 19 Oct 2026: "split the figures between the urban core and the greater extent"):
// the urban part, where most people live, first; the map shows the whole area either way, the rest of it paled while
// the urban part's figures show (the mask below)
let where = D.urban ? 'urban' : '';
const FIG = () => { const F = scen ? SCS[scen] : D; return where && F.urban ? F.urban : F; };
const ST = () => FIG().stats, DST = () => FIG().day_stats || D.day.stats;
const NSTOPS = () => where ? D.urban.n_stops : D.n_stops;
// a scenario holds only the pieces and stops it changes ({index: values}); the first pass's values stand elsewhere
const pathVals = (i, s = scen) => un((s && SCS[s].paths[i]) || D.paths[i][1]), stopVals = (i, s = scen) => un((s && SCS[s].stops[i]) || D.stops[i].v);
const DCOLS = D.day.colors.map(tok), HOT = D.classes[D.hot].lo;
const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;
// text from the data, written into the page's HTML
const esc = t => String(t).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// the page's state in its address, so a view can be sent to someone (9 Nov 2026):
// #v=paths&p=trees&h=14&a=all&m=14.20/52.0406/-0.7594 is the footpaths, the plan "trees", the hour from 14:00, the whole
// borough's figures, and the map's zoom and middle. What is as the page opens is left out, so the plain address stays
// plain. The site's only: the artifact has no address of its own
function readHash() {
  const q = new URLSearchParams(location.hash.slice(1)), o = {};
  if (VIEWS.includes(q.get('v'))) o.view = q.get('v');
  if (q.get('p') && SCS[q.get('p')]) o.scen = q.get('p');
  const k = q.get('h') ? D.hours.findIndex(H => +H.file === +q.get('h')) : -1; if (k >= 0) o.hi = k;
  if (q.get('a') === 'all' && D.urban) o.where = '';
  const m = (q.get('m') || '').split('/').map(Number); if (m.length === 3 && m.every(Number.isFinite)) o.m = m;
  return o;
}
const H0 = SITE ? readHash() : {};
if (H0.view) view = H0.view;
if (H0.scen) scen = H0.scen;
if (H0.hi !== undefined) { hi = H0.hi; mode = 'hour'; }
if (H0.where !== undefined) where = H0.where;
// the map follows the area the figures are of until the reader moves it (or the address says where to look)
let autoView = !H0.m;

// each piece of text is written only when it changes, so a screen reader hears a change and not every redraw
const shown = {};
const put = (id, t, html) => { if (shown[id] === t) return; shown[id] = t; const e = document.getElementById(id); if (html) e.innerHTML = t; else e.textContent = t; };
put('when', `${D.area}, Thursday 13 August 2026`);
document.getElementById('src').innerHTML = D.sources;
// the key: the day's four classes, each with the share of the view shown that had so many hours (the bar that drew
// those shares above the key was the key's four colours over again), or the hour's scale. The phone's copy, on the
// map, has the classes alone, the hour's numbers without their words
const scale = document.getElementById('scale'), lscale = document.getElementById('lscale');
function drawKey() {
  const day = mode === 'day', cols = day ? DCOLS : COLS, sw = cols.map(c => `<i style="background:${c}"></i>`).join('');
  const fine = !day && COLS.length > 6;
  put('keyh', day ? 'Hours that felt like 38 °C or more' : D.key); put('lkeyh', day ? 'Hours at 38 °C or more' : D.key);
  put('keyof', day ? `Share of ${NAME[view].toLowerCase()}` : '');
  for (const el of [scale, lscale]) { el.style.gridTemplateColumns = `repeat(${cols.length}, 1fr)`; el.classList.toggle('fine', fine); }
  const lab = day ? D.day.labels.map(l => `<span>${l}</span>`).join('') : D.classes.map(c => `<span>${c.label}</span>`).join('');
  put('scale', sw + lab + (day ? DST()[view].map(f => `<b>${Math.round(f * 100)}%</b>`).join('')
    : D.classes.map(c => `<span class="w${c.words ? ' edge' : ''}">${c.words || ''}</span>`).join('')), true);
  // on the phone a labelled step is its number alone ("30° or less" would run into "34°" in a key 230 px wide)
  const short = (c, k) => !c.label ? '' : D.mode !== 'utci' ? c.label : k === 0 ? `≤${D.classes[1].lo - 1}°` : k === D.classes.length - 1 ? `${c.lo}°+` : `${c.lo}°`;
  put('lscale', sw + (day ? D.day.labels.map(l => `<span>${l}</span>`).join('') : D.classes.map((c, k) => `<span>${short(c, k)}</span>`).join('')), true);
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
const TS = {"basemap": "https://maps.weinbren.me/mk-heat/basemap.e22c3d4dcf98.pmtiles", "features": "https://maps.weinbren.me/mk-heat/features.ad3779727416.pmtiles", "trees": "https://maps.weinbren.me/mk-heat/trees.f5df91ed8392.pmtiles", "ground/06-stops": "https://maps.weinbren.me/mk-heat/ground/06-stops.3654171a8e96.pmtiles", "ground/06-trees": "https://maps.weinbren.me/mk-heat/ground/06-trees.6a421974b907.pmtiles", "ground/06": "https://maps.weinbren.me/mk-heat/ground/06.06a2c6676231.pmtiles", "ground/07-stops": "https://maps.weinbren.me/mk-heat/ground/07-stops.3123709e68c6.pmtiles", "ground/07-trees": "https://maps.weinbren.me/mk-heat/ground/07-trees.42cee2478514.pmtiles", "ground/07": "https://maps.weinbren.me/mk-heat/ground/07.1320a155c4ab.pmtiles", "ground/08-stops": "https://maps.weinbren.me/mk-heat/ground/08-stops.240be07d6021.pmtiles", "ground/08-trees": "https://maps.weinbren.me/mk-heat/ground/08-trees.35e31f96426d.pmtiles", "ground/08": "https://maps.weinbren.me/mk-heat/ground/08.675178dfbf7a.pmtiles", "ground/09-stops": "https://maps.weinbren.me/mk-heat/ground/09-stops.e07f40528b4c.pmtiles", "ground/09-trees": "https://maps.weinbren.me/mk-heat/ground/09-trees.6e0fb2fcfac4.pmtiles", "ground/09": "https://maps.weinbren.me/mk-heat/ground/09.c6cbc2d134e0.pmtiles", "ground/10-stops": "https://maps.weinbren.me/mk-heat/ground/10-stops.dcaf7b1598a1.pmtiles", "ground/10-trees": "https://maps.weinbren.me/mk-heat/ground/10-trees.0244539e35f3.pmtiles", "ground/10": "https://maps.weinbren.me/mk-heat/ground/10.6f28b5ddcb78.pmtiles", "ground/11-stops": "https://maps.weinbren.me/mk-heat/ground/11-stops.414efeda5053.pmtiles", "ground/11-trees": "https://maps.weinbren.me/mk-heat/ground/11-trees.6091f2689ca6.pmtiles", "ground/11": "https://maps.weinbren.me/mk-heat/ground/11.9b5185d210f3.pmtiles", "ground/12-stops": "https://maps.weinbren.me/mk-heat/ground/12-stops.a9b0f133036e.pmtiles", "ground/12-trees": "https://maps.weinbren.me/mk-heat/ground/12-trees.7c644e72a0fc.pmtiles", "ground/12": "https://maps.weinbren.me/mk-heat/ground/12.beca898fd5b8.pmtiles", "ground/13-stops": "https://maps.weinbren.me/mk-heat/ground/13-stops.824de99b0e21.pmtiles", "ground/13-trees": "https://maps.weinbren.me/mk-heat/ground/13-trees.79b1d18ff423.pmtiles", "ground/13": "https://maps.weinbren.me/mk-heat/ground/13.2e10a1a610bb.pmtiles", "ground/14-stops": "https://maps.weinbren.me/mk-heat/ground/14-stops.bc26303066d6.pmtiles", "ground/14-trees": "https://maps.weinbren.me/mk-heat/ground/14-trees.9ecb50d5d5e0.pmtiles", "ground/14": "https://maps.weinbren.me/mk-heat/ground/14.92eb9ae27353.pmtiles", "ground/15-stops": "https://maps.weinbren.me/mk-heat/ground/15-stops.a3d74b03401a.pmtiles", "ground/15-trees": "https://maps.weinbren.me/mk-heat/ground/15-trees.1ba87382c346.pmtiles", "ground/15": "https://maps.weinbren.me/mk-heat/ground/15.b9cbc2f7a48d.pmtiles", "ground/16-stops": "https://maps.weinbren.me/mk-heat/ground/16-stops.ab7a0c8ab862.pmtiles", "ground/16-trees": "https://maps.weinbren.me/mk-heat/ground/16-trees.75cb3ef73358.pmtiles", "ground/16": "https://maps.weinbren.me/mk-heat/ground/16.09eecba55f9a.pmtiles", "ground/17-stops": "https://maps.weinbren.me/mk-heat/ground/17-stops.6b438e7d347d.pmtiles", "ground/17-trees": "https://maps.weinbren.me/mk-heat/ground/17-trees.407596738026.pmtiles", "ground/17": "https://maps.weinbren.me/mk-heat/ground/17.27f9dd9d232c.pmtiles", "ground/18-stops": "https://maps.weinbren.me/mk-heat/ground/18-stops.a8df129e1158.pmtiles", "ground/18-trees": "https://maps.weinbren.me/mk-heat/ground/18-trees.0c78c44baf8d.pmtiles", "ground/18": "https://maps.weinbren.me/mk-heat/ground/18.9ebacbb4b731.pmtiles", "ground/19-stops": "https://maps.weinbren.me/mk-heat/ground/19-stops.aa283278a260.pmtiles", "ground/19-trees": "https://maps.weinbren.me/mk-heat/ground/19-trees.64c0e14586c5.pmtiles", "ground/19": "https://maps.weinbren.me/mk-heat/ground/19.9ba27ffcbf09.pmtiles", "ground/bld": "https://maps.weinbren.me/mk-heat/ground/bld.71034d2cf835.pmtiles", "ground/day-stops": "https://maps.weinbren.me/mk-heat/ground/day-stops.ca1e2749db65.pmtiles", "ground/day-trees": "https://maps.weinbren.me/mk-heat/ground/day-trees.22dd893311da.pmtiles", "ground/day": "https://maps.weinbren.me/mk-heat/ground/day.036edd2e11f7.pmtiles", "_ground": {"minzoom": 8, "maxzoom": 14, "bounds": [-0.895274, 51.960044, -0.582032, 52.205995]}, "_trees": {"minzoom": 15, "maxzoom": 15}};                                // each archive's address (site.py: R2, at maps.weinbren.me)
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
const PIECES = D.pieces || [];
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
  HKEYS.forEach(k => { map.addLayer(pathLayer(`${k}.${hourN}`, cls(k)), 'trees'); map.addLayer(stopLayer(`${k}.${hourN}`, cls(k)), 'stops'); });
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
const PATH_W = ['interpolate', ['linear'], ['zoom'], 12, 1.6, 14, 3.2, 17, 7];
// a colour layer of the footpaths or the stops, hidden until shown
const pathLayer = (k, colour) => ({ id: 'paths:' + k, type: 'line', ...src('paths'), layout: LINE,
  paint: { 'line-color': colour, 'line-width': PATH_W, 'line-opacity': 0, 'line-opacity-transition': NOW } });
const stopLayer = (k, colour) => ({ id: 'stops:' + k, type: 'circle', ...src('stops'),
  paint: { 'circle-color': colour, 'circle-radius': STOP_R, 'circle-opacity': 0, 'circle-opacity-transition': NOW } });
const BLDG_PAINT = { 'raster-opacity': ['interpolate', ['linear'], ['zoom'], 12, 0.5, 14, 1], 'raster-resampling': 'nearest', 'raster-fade-duration': 0 };
// the urban part's outline: one ring, or one for each piece
const URINGS = D.urban ? (D.urban.outline.type === 'LineString' ? [D.urban.outline.coordinates] : D.urban.outline.coordinates) : [];
const UBOUNDS = URINGS.flat().reduce((b, [x, y]) => [[Math.min(b[0][0], x), Math.min(b[0][1], y)], [Math.max(b[1][0], x), Math.max(b[1][1], y)]], [[180, 90], [-180, -90]]);
const NONE = { type: 'FeatureCollection', features: [] };
const style = {
  version: 8,
  glyphs: 'glyphs://{fontstack}/{range}',
  sources: {
    b: { type: 'vector', url: SITE ? tiles('basemap') : 'pmtiles://mk', attribution: D.credits },
    ...(D.urban ? { urban: { type: 'geojson', data: D.urban.outline },
                    // everything but the urban part: a sheet over the whole map with the urban part cut out of it
                    umask: { type: 'geojson', data: { type: 'Feature', properties: {}, geometry: { type: 'Polygon',
                      coordinates: [[[w - 3, s - 3], [e + 3, s - 3], [e + 3, n + 3], [w - 3, n + 3], [w - 3, s - 3]], ...URINGS] } } } } : {}),
    sel: { type: 'geojson', data: NONE },
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
    // the stretch of path a popup is of, dark round its colour while the popup is open
    { id: 'sel-path', type: 'line', source: 'sel', filter: ['==', ['geometry-type'], 'LineString'], layout: LINE,
      paint: { 'line-color': tok('--ink'), 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 6, 14, 9, 17, 14] } },
    // the paths' white edge, also what a click on a path hits
    { id: 'paths-case', type: 'line', ...src('paths'), layout: LINE,
      paint: { 'line-color': '#ffffff', 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 3, 14, 5.5, 17, 10], 'line-opacity': view === 'paths' ? 1 : 0, 'line-opacity-transition': NOW } },
    ...SKEYS.map(s => pathLayer(dayKey(s), dayCls(s))),
    // the scenario's new trees, from zoom 15 only and half see-through, so the colours beneath show what they change
    // (Jacob, 18 Oct 2026: "the trees cover the map so it is hard to see their effect"); true size from zoom 17
    { id: 'trees', type: 'circle', ...(SITE && TS.trees ? { source: 't', 'source-layer': 'trees' } : src('trees')), minzoom: 15, layout: { visibility: 'none' },
      paint: { 'circle-color': '#2f5a2b', 'circle-opacity': 0.55, 'circle-radius': ['interpolate', ['exponential', 2], ['zoom'], 15, 1.5, 17, 3.4, 18, 6.8] } },
    ...SKEYS.map(s => stopLayer(dayKey(s), dayCls(s))),
    // the stops' rings over their colour, also what a click on a stop hits
    { id: 'stops', type: 'circle', ...src('stops'),
      paint: { 'circle-color': '#ffffff', 'circle-radius': STOP_R, 'circle-opacity': 0, 'circle-stroke-color': tok('--ink'),
               'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 12, 0.6, 16, 1.2], 'circle-stroke-opacity': 0, 'circle-stroke-opacity-transition': NOW } },
    // the stop a popup is of, ringed while the popup is open
    { id: 'sel-stop', type: 'circle', source: 'sel', filter: ['==', ['geometry-type'], 'Point'],
      paint: { 'circle-color': 'rgba(0,0,0,0)', 'circle-radius': ['interpolate', ['linear'], ['zoom'], 12, 7, 14, 9.5, 17, 14], 'circle-stroke-color': tok('--ink'), 'circle-stroke-width': 2 } },
    // while the urban part's figures show, the rest of the area is paled, so the eye goes to the part the figures are
    // of (9 Nov 2026: the fields north of the city, the darkest red on the page, were no part of the headline's 71%),
    // and its edge is drawn over the footpaths and stops (under them it was lost among them)
    ...(D.urban ? [{ id: 'umask', type: 'fill', source: 'umask', layout: { visibility: where ? 'visible' : 'none' },
                     paint: { 'fill-color': tok('--ground'), 'fill-opacity': 0.72, 'fill-antialias': false } },
                   { id: 'urban', type: 'line', source: 'urban', layout: { visibility: where ? 'visible' : 'none' },
                     paint: { 'line-color': tok('--ink'), 'line-width': 1.4, 'line-opacity': 0.85, 'line-dasharray': [3, 2] } }] : []),
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
// the part of the screen the card leaves to the map: beside it, or on a phone above it
const cardEl = document.getElementById('card'), phone = matchMedia('(max-width: 640px)');
const clear = () => { const r = cardEl.getBoundingClientRect();
  return phone.matches ? { left: 0, top: document.getElementById('legend').getBoundingClientRect().bottom, right: innerWidth, bottom: r.top } : { left: r.right, top: 0, right: innerWidth, bottom: innerHeight }; };
// an area fits in that part
const fitPad = () => { const c = clear(); return phone.matches ? { left: 10, right: 10, top: c.top + 8, bottom: innerHeight - c.bottom + 10 } : { left: c.left + 16, right: 30, top: 30, bottom: 30 }; };
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
// the limits are the whole area's, as above; the page then opens on the part its figures are of (the urban part, as
// the card opens on its figures), or where its address says
const fitArea = anim => map.fitBounds(where ? UBOUNDS : D.bounds, { padding: fitPad(), duration: anim && !REDUCED ? 600 : 0 });
if (H0.m) map.jumpTo({ zoom: H0.m[0], center: [H0.m[2], H0.m[1]] }); else if (where) fitArea(false);
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
// where the reader is, if they ask (the site's only: an artifact's frame is refused it)
if (SITE && navigator.geolocation) map.addControl(new maplibregl.GeolocateControl({ positionOptions: { enableHighAccuracy: true }, fitBoundsOptions: { maxZoom: 16 } }), 'top-right');
map.on('styleimagemissing', ev => {
  if (ev.id !== 'hatch') return;
  const z = 8, c = document.createElement('canvas'); c.width = c.height = z; const g = c.getContext('2d');
  g.fillStyle = 'rgba(245,245,243,0.85)'; g.fillRect(0, 0, z, z); g.strokeStyle = tok('--grey'); g.lineWidth = 1.2;
  g.beginPath(); g.moveTo(0, z); g.lineTo(z, 0); g.moveTo(-z / 2, z / 2); g.lineTo(z / 2, -z / 2); g.moveTo(z / 2, z * 1.5); g.lineTo(z * 1.5, z / 2); g.stroke();
  map.addImage('hatch', g.getImageData(0, 0, z, z));
});

// hour of day: a column an hour, the share of the view shown at 38 °C or more (the tiles' figure through the day),
// with the slider over the columns (the CSS: nothing of it is drawn, and its thumb is a column wide, so a click or a
// drag on a column chooses its hour; the keyboard and a screen reader have a slider as before). Until 9 Nov 2026 the
// columns were each hour's fifteen classes stacked, too small to read, with a slider under them that the day view greyed
const slider = document.getElementById('hour'); slider.max = NH - 1; slider.value = hi;
const dayEl = document.getElementById('day'), hoursEl = document.getElementById('hours'), bars = document.getElementById('bars');
dayEl.style.setProperty('--nh', NH);
// each label at the start of its hour's column, as far as the next label
put('ticks', D.ticks.map((t, k) => `<span style="grid-column:${k * 3 + 1}/span ${Math.min(3, NH - k * 3)}">${t}</span>`).join(''), true);
const sizeBars = () => hoursEl.style.setProperty('--bw', (hoursEl.clientWidth / NH).toFixed(2) + 'px');
const hotShare = sh => sh.slice(D.hot).reduce((a, b) => a + b, 0);
function drawBars() {
  // a plan's columns carry a line at the share as it was
  const st = ST()[view], was = scen ? (where && D.urban ? D.urban : D).stats[view] : null;
  put('bars', st.map((sh, k) => { const f = hotShare(sh), b = was ? hotShare(was[k]) : f;
    return `<i class="${mode === 'hour' && k === hi ? 'on' : ''}" style="--f:${(f * 100).toFixed(1)}%${Math.abs(b - f) >= 0.005 ? `;--b:${(b * 100).toFixed(1)}%" data-b="1` : ''}"></i>`; }).join(''), true);
  put('barcap', `${NAME[view]} ${D.mode === 'utci' ? 'at 38 °C or more' : 'in full sun'}, hour by hour${was ? '; the line is as it was' : ''}`);
}
// what the three tiles say, for the page and for a screen reader
const share = v => mode === 'day' ? 1 - DST()[v][0] : hotShare(ST()[v][hi]);
const num = v => v === 'stops' ? Math.round(share(v) * NSTOPS()).toLocaleString('en-GB') : `${Math.round(share(v) * 100)}%`;
const small = v => (where ? D.urban.view_small : mode === 'day' ? D.view_small_day : D.view_small)[v];
// a change is said once things have settled (the slider dragged across six hours says the last)
let sayT = 0, saidHead = null;
function say() {
  const head = document.getElementById('h1').textContent;
  const fig = `${document.getElementById('vh').textContent}: ` + VIEWS.map(v => `${NAME[v].toLowerCase()} ${num(v)}${small(v) ? ' ' + small(v) : ''}`).join(', ') + '.';
  if (saidHead === null) { saidHead = head; return; }                     // the page as it opens is read, not announced
  clearTimeout(sayT); sayT = setTimeout(() => { put('live', (head !== saidHead ? head + ' ' : '') + fig); saidHead = head; }, 600);
}
function render() {
  const H = D.hours[hi], F = FIG();
  put('h1', F.headline, true);
  put('deck', (scen ? F : D).deck);
  document.querySelectorAll('.view').forEach(b => b.setAttribute('aria-pressed', b.dataset.v === view));
  document.querySelectorAll('#scbtns button').forEach(b => b.setAttribute('aria-pressed', b.dataset.s === scen));
  document.querySelectorAll('#where button').forEach(b => b.setAttribute('aria-pressed', b.dataset.a === where));
  // a plan's own line, the urban part's where it has one
  const note = document.getElementById('scnote'); note.hidden = !scen; put('scnote', scen ? F.note || SCS[scen].note : '');
  put('gripp', scen ? SCS[scen].label : '');
  document.getElementById('m-day').setAttribute('aria-pressed', mode === 'day');
  document.getElementById('m-hour').setAttribute('aria-pressed', mode === 'hour');
  put('m-hour', H.label);
  dayEl.classList.toggle('all', mode === 'day');
  slider.value = hi; slider.setAttribute('aria-valuetext', mode === 'day' ? `Whole day (${H.label} if an hour is chosen)` : H.label);
  put('air', mode === 'day' ? `Air peaked at ${D.day.peak_ta.toFixed(0)} °C` : `Air ${H.ta.toFixed(0)} °C, ${H.rh}% humidity`);
  if (D.views_head) put('vh', mode === 'day' ? D.views_head.day : D.views_head.hour.replace('{h}', H.label));
  VIEWS.forEach(v => { put('n-' + v, num(v)); put('s-' + v, small(v)); });
  const hint = document.getElementById('hint'); hint.hidden = view === 'ground';
  put('hint', view === 'paths' ? 'Choose a stretch of footpath on the map to see its day.' : view === 'stops' ? 'Choose a bus stop on the map to see its day.' : '');
  if (ready) { showGround(); prefetch(); showLines(); }
  drawKey(); drawBars(); if (pop) pop.refresh();
  say(); writeHash();
}
// the hours played through, one a second, each shown only once its tiles are in, so a slow connection plays slower
// and never a patchwork; it stops at the day's end, at a press, or when an hour or the whole day is chosen by hand
const playBtn = document.getElementById('play'); let playing = 0;
const busy = () => !ready || !!hourNext || (SITE && groundWant !== groundShown) || !map.areTilesLoaded();
function play(on) {
  clearTimeout(playing); playing = 0;
  playBtn.classList.toggle('on', on); playBtn.setAttribute('aria-label', on ? 'Pause' : 'Play the day hour by hour');
  if (!on) return;
  if (mode === 'day' || hi === NH - 1) setHour(0, true);
  playing = setTimeout(step, 1100);
}
function step() {
  if (busy()) { playing = setTimeout(step, 150); return; }
  if (hi >= NH - 1) { play(false); return; }
  setHour(hi + 1, true); playing = setTimeout(step, 1100);
}
playBtn.onclick = () => play(!playing);
function setHour(k, played) { if (!played && playing) play(false); hi = k; mode = 'hour'; render(); if (ready) makeHours(); }
function setMode(m) { if (playing) play(false); mode = m; render(); if (ready) makeHours(); }
function showTrees() {
  map.setLayoutProperty('trees', 'visibility', scen ? 'visible' : 'none');
  if (SITE) { map.setFilter('trees', ['==', ['get', 's'], scen]); return; }
  map.getSource('trees').setData({ type: 'FeatureCollection', features: (scen ? SCS[scen].trees : []).map(c => ({ type: 'Feature', geometry: { type: 'Point', coordinates: c }, properties: {} })) });
}
function setScen(name) {
  scen = name;
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
    for (const [nm, S] of Object.entries(SCS)) box.insertAdjacentHTML('beforeend', `<button type="button" data-s="${nm}" aria-pressed="false">${esc(S.label)}</button>`);
  document.getElementById('scen').hidden = false;
  box.querySelectorAll('button').forEach(b => b.onclick = () => setScen(b.dataset.s));
}
// the map shows the part the figures are of: its edge and the paling of the rest, and, until the reader has moved the
// map themself, the part fitted to the screen
function showWhere() {
  if (!D.urban) return;
  for (const id of ['urban', 'umask']) map.setLayoutProperty(id, 'visibility', where ? 'visible' : 'none');
}
function setWhere(a) {
  where = a;
  if (ready) { showWhere(); if (autoView) fitArea(true); }
  render();
}
if (D.urban) {
  document.getElementById('where').hidden = false;
  document.querySelectorAll('#where button').forEach(b => b.onclick = () => setWhere(b.dataset.a));
}
function setView(v) {
  view = v;
  if (ready) {
    if (!SITE) PIECES.forEach(p => map.setPaintProperty('ground' + p.id, 'raster-opacity', v === 'ground' ? 1 : 0));
    map.setPaintProperty('paths-case', 'line-opacity', v === 'paths' ? 1 : 0);
    map.setPaintProperty('stops', 'circle-stroke-opacity', v === 'stops' ? 1 : 0);
  }
  if (pop) pop.remove();
  render();
}
slider.oninput = () => setHour(+slider.value);
// a press anywhere on the columns chooses the column under it, and a drag the columns it crosses: a slider says nothing
// when pressed where its thumb already is (from the whole day that must still choose the hour), and an iPhone moves a
// slider only by its thumb
const hourAt = ev => Math.max(0, Math.min(NH - 1, Math.floor((ev.clientX - hoursEl.getBoundingClientRect().left) / hoursEl.clientWidth * NH)));
let scrubbing = false;
slider.addEventListener('pointerdown', ev => { scrubbing = true; try { slider.setPointerCapture(ev.pointerId); } catch (err) {} setHour(hourAt(ev)); });
slider.addEventListener('pointermove', ev => { if (scrubbing && hourAt(ev) !== hi) setHour(hourAt(ev)); });
for (const t of ['pointerup', 'pointercancel']) slider.addEventListener(t, () => { scrubbing = false; });
document.getElementById('m-day').onclick = () => setMode('day');
document.getElementById('m-hour').onclick = () => setHour(hi);
document.querySelectorAll('.view').forEach(b => b.onclick = () => setView(b.dataset.v));
// keys: left and right step the hour (not while the map has them: it pans with the arrows; nor the slider, which
// steps with them itself), d the whole day, 1 to 3 the views; none while the method panel is open or a field is typed in
addEventListener('keydown', ev => {
  if (ev.defaultPrevented || ev.ctrlKey || ev.metaKey || ev.altKey || dlg.open) return;
  const at = sel => ev.target.closest && ev.target.closest(sel);
  if (at('input, textarea, select')) return;
  if ((ev.key === 'ArrowRight' || ev.key === 'ArrowLeft') && !at('#map')) setHour(Math.max(0, Math.min(NH - 1, hi + (ev.key === 'ArrowRight' ? 1 : -1))));
  if (ev.key === 'd') setMode('day');
  if (['1', '2', '3'].includes(ev.key)) setView(VIEWS[+ev.key - 1]);
});
// the window resized or the phone turned: the columns' width for the slider, and the area fitted again while the
// reader has not moved the map (a phone's address bar coming and going is not a new shape)
let rsT = 0, lastW = innerWidth, lastH = innerHeight;
addEventListener('resize', () => {
  sizeBars(); clearTimeout(rsT);
  rsT = setTimeout(() => { const turned = innerWidth !== lastW || Math.abs(innerHeight - lastH) > 120; lastW = innerWidth; lastH = innerHeight;
    if (turned && autoView && ready) fitArea(false); }, 250);
});
// the hours either side of the one shown, fetched ahead so the slider steps without a wait (the city's images are
// too many to fetch all at once)
const fetched = new Set();
function prefetch() {
  if (SITE || mode === 'day' || view !== 'ground') return;
  [hi - 1, hi + 1].filter(k => k >= 0 && k < NH).forEach(k => PIECES.forEach(p => {
    const u = groundUrl(p.id, k); if (!fetched.has(u)) { fetched.add(u); const im = new Image(); im.src = u; }
  }));
}
// the address follows the page (above), a moment after the last change, and the page a new address typed or pasted
let hashT = 0;
function writeHash() {
  if (!SITE) return;
  clearTimeout(hashT); hashT = setTimeout(() => {
    const q = [];
    if (view !== 'ground') q.push('v=' + view);
    if (scen) q.push('p=' + scen);
    if (mode === 'hour') q.push('h=' + +D.hours[hi].file);
    if (D.urban && !where) q.push('a=all');
    if (!autoView) { const c = map.getCenter(); q.push(`m=${map.getZoom().toFixed(2)}/${c.lat.toFixed(4)}/${c.lng.toFixed(4)}`); }
    try { history.replaceState(null, '', q.length ? '#' + q.join('&') : location.pathname + location.search); } catch (err) {}
  }, 200);
}
if (SITE) addEventListener('hashchange', () => {
  const o = readHash();
  view = o.view || 'ground'; scen = o.scen || ''; where = o.where !== undefined ? o.where : D.urban ? 'urban' : '';
  if (o.hi !== undefined) { hi = o.hi; mode = 'hour'; } else mode = 'day';
  if (o.m) { autoView = false; map.jumpTo({ zoom: o.m[0], center: [o.m[2], o.m[1]] }); }
  if (pop) pop.remove();
  if (ready) { setView(view); showWhere(); showTrees(); makeHours(); }
  render();
});
// a link to the page as it stands: the phone's own share sheet where there is one, else onto the clipboard
const shareBtn = document.getElementById('share');
if (SITE && (navigator.share || (navigator.clipboard && navigator.clipboard.writeText))) {
  shareBtn.hidden = false; if (navigator.share && phone.matches) shareBtn.textContent = 'Share';
  shareBtn.onclick = async () => {
    try {
      if (navigator.share && phone.matches) { await navigator.share({ title: document.title, url: location.href }); return; }
      await navigator.clipboard.writeText(location.href);
      shareBtn.textContent = 'Link copied'; setTimeout(() => { shareBtn.textContent = 'Copy link'; }, 2000);
    } catch (err) {}
  };
}

// a place's day: one cell an hour, like a row of a timetable; in a plan that changes the place, the day as it was
// under the plan's
const hot = vals => vals.filter(v => v >= HOT).length;
const note = (vals, was) => (mode === 'hour' ? D.now_fmt.replace('{v}', vals[hi]) + ' ' : '') + D.count_fmt.replace('{n}', hot(vals)).replace('{N}', NH)
  + (was ? ` As it was, ${hot(was)}.` : '');
function timetable(vals, title, sub, was) {
  const row = (vv, on) => vv.map((v, k) => `<i style="background:${COLS[classOf(v)]}" class="${on && mode === 'hour' && k === hi ? 'on' : ''}" title="${D.hours[k].label}: ${v}${D.unit}"></i>`).join('');
  const lab = D.hours.map((H, k) => `<span>${k % 3 === 0 ? H.short : ''}</span>`).join('');
  if (was && was.join() === vals.join()) was = null;
  return `<div class="pop"><h3>${esc(title)}</h3><p>${esc(sub)}</p>` + (was ? `<p class="rl">${esc(SC().label)}</p><div class="tt" style="--n:${NH}">${row(vals, 1)}</div><p class="rl">As it was</p>` : '')
    + `<div class="tt" style="--n:${NH}">${row(was || vals, !was)}${lab}</div><p class="sum">${note(vals, was)}</p></div>`;
}
const notModelled = t => `<div class="pop"><h3>${esc(t)}</h3><p class="sum">Built since the lidar survey, not modelled.</p></div>`;
// the popup opens above or below its place, whichever has the room in the part of the map the card leaves clear, and
// the map moves if it would still lie under the card or off the screen; the place itself is outlined while it is open
function openPop(lngLat, html, geom) {
  if (pop) pop.remove();
  if (phone.matches) fold(true);
  const c = clear(), box = map.getContainer().getBoundingClientRect(), p = map.project(lngLat), x = p.x + box.left, y = p.y + box.top;
  const anchor = (y - c.top > 250 || y - c.top > c.bottom - y ? 'bottom' : 'top') + (x - c.left < 175 ? '-left' : c.right - x < 175 ? '-right' : '');
  const me = pop = new maplibregl.Popup({ closeButton: true, maxWidth: '320px', focusAfterOpen: false, anchor, offset: 8 }).setLngLat(lngLat).setHTML(html()).addTo(map);
  map.getSource('sel').setData(geom ? { type: 'Feature', properties: {}, geometry: geom } : NONE);
  me.refresh = () => me.setHTML(html());
  me.on('close', () => { if (pop === me) { pop = null; map.getSource('sel').setData(NONE); } });
  requestAnimationFrame(() => {
    if (pop !== me) return;
    const b = me.getElement().getBoundingClientRect();
    const dx = b.left < c.left + 8 ? b.left - c.left - 8 : b.right > c.right - 8 ? b.right - c.right + 8 : 0;
    const dy = b.top < c.top + 8 ? b.top - c.top - 8 : b.bottom > c.bottom - 8 ? b.bottom - c.bottom + 8 : 0;
    if (dx || dy) map.panBy([dx, dy], { duration: REDUCED ? 0 : 250 });
  });
}
// a clicked feature's day, as it is shown or as it was: the site's from the tile's own properties, the artifact's from
// the JSON by index
const valsOf = (f, kind, s = scen) => SITE ? un(f.properties[s && f.properties['v_' + s] ? 'v_' + s : 'v'])
  : (kind === 'stops' ? stopVals : pathVals)(f.properties.i, s);
map.on('click', 'stops', ev => {
  if (view !== 'stops') return;
  const f = ev.features[0], st = SITE ? { ...f.properties, x: f.geometry.coordinates[0], y: f.geometry.coordinates[1] } : D.stops[f.properties.i];
  openPop([st.x, st.y], () => st.g === 2 ? `<div class="pop"><h3>${esc(st.n)}</h3><p>${esc(st.m)}</p><p class="sum">Under a canopy or overhang, so in shade all day. The lidar cannot see under it, so it is not modelled.</p></div>`
    : st.g ? notModelled(st.n) : timetable(valsOf(f, 'stops'), st.n, st.m + (st.sh ? ' · has a shelter' : ''), scen ? valsOf(f, 'stops', '') : null),
    { type: 'Point', coordinates: [st.x, st.y] });
});
map.on('click', 'paths-case', ev => {
  if (view !== 'paths') return;
  const f = ev.features[0], g = SITE ? f.properties.g : D.paths[f.properties.i][2];
  openPop(ev.lngLat, () => g === 2 ? `<div class="pop"><h3>Underpass or covered path</h3><p class="sum">Under a bridge or roof, so in shade all day. The lidar cannot see under it, so it is not modelled.</p></div>`
    : g ? notModelled('Footpath') : timetable(valsOf(f, 'paths'), 'This stretch of path', 'Up to 25 m of path', scen ? valsOf(f, 'paths', '') : null),
    f.geometry.type === 'LineString' ? f.geometry : null);
});
[['stops', 'stops'], ['paths', 'paths-case']].forEach(([v, l]) => {
  map.on('mouseenter', l, () => { if (view === v) map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', l, () => { map.getCanvas().style.cursor = ''; });
});
// the phone's sheet (the CSS): its grip folds it to the views and the hours and unfolds it, a swipe on the grip does
// the same, and it folds when the reader takes hold of the map
const grip = document.getElementById('grip');
function fold(min, byGrip) {
  if (cardEl.classList.contains('min') === min) return;
  cardEl.classList.toggle('min', min); grip.setAttribute('aria-expanded', !min); put('gripl', min ? 'More' : 'Less');
  if (byGrip && ready && autoView) fitArea(true);    // the area in the room the sheet now leaves
}
grip.onclick = () => fold(!cardEl.classList.contains('min'), true);
let gy = null;
grip.addEventListener('touchstart', ev => { gy = ev.touches[0].clientY; }, { passive: true });
grip.addEventListener('touchend', ev => { const dy = ev.changedTouches[0].clientY - gy; gy = null; if (Math.abs(dy) > 24) { fold(dy > 0, true); ev.preventDefault(); } });
// the sheet's height, for the map's corner controls to stand clear of it
const sheet = () => document.documentElement.style.setProperty('--sheet', phone.matches ? cardEl.offsetHeight + 'px' : '0px');
new ResizeObserver(() => { sheet(); sizeBars(); }).observe(cardEl);
map.on('movestart', ev => {
  if (!ev.originalEvent) return;                       // the page's own moves (a fit, a popup brought into view) are not the reader's
  autoView = false; if (phone.matches) fold(true);
});
map.on('moveend', () => { if (!autoView) writeHash(); });
// the controls work before the map has loaded (the card is drawn first); the map takes their state when it has
sizeBars(); sheet(); render();
window.mkmap = map;                          // for timing the page's interactions from outside (tests only read it)
window.mkstate = () => ({ view, scen, where, mode, hour: hi, auto: autoView, busy: busy() });
map.on('load', () => {
  ready = true; setView(view); showWhere(); showTrees(); makeHours(); render();
  if (SITE) map.on('render', swapGround);
  map.on('render', swapHours);
  document.querySelector('.maplibregl-ctrl-attrib')?.classList.remove('maplibregl-compact-show');   // credits fold behind the (i)
});
})().catch(err => { document.getElementById('h1').textContent = 'The map could not load. Reload the page to try again.'; console.error(err); });
