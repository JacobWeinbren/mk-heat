#!/bin/zsh
# The heat map on v3 + England, stage 2 of 2: the map from the new classes (rebuild_en_1.sh). Every step after the
# classes skips what it has already made, so the outputs made from v1's classes are cleared first: strips/ (v1's classes
# by tile edge), surfaces/, shade/, utci/, utci_stops/, utci_trees/ and the plans' layers (stops_cdsm, trees_cdsm,
# shelters_cdsm, stops.json, trees.json). They are all made again from v1's kept classes (rounds/mk/pred_v1) if ever
# wanted, and the disk cannot hold both (about 20 GB). Then, in seams.sh's order with the borough chain's steps that
# depend on the classes: every flight line on one scale (intensity_lines.py; Jacob, 20 Oct 2026: "Option 1 sounds
# good"), surfaces, land cover, shade, existing shelters, UTCI (area-wide forcing), new buildings, the map, the tree
# count and size, the stop plan and the 10% plan with their shelter rounds, the site on the preview branch (en), to be
# checked before production.
cd /Users/jacobweinbren/Desktop/lidar-review
export ROUNDS_DIR=$PWD/data/mk/heat/rounds
PY=pipeline/.venv/bin/python; HV=data/experiments/mk_heat/.venv/bin/python; M=data/experiments/mk_heat; HD=data/mk/heat
say() { echo "$(date '+%F %T') $*"; }
# a step starts at memory pressure 1, or at 2 with the training's measured peak free (round.py memory-ok,
# round_common.memory_ok; Jacob, 13 Oct 2026): pressure 1 alone held the chain for hours beside the night's photo job
calm() { local w; until w=$($PY -u pipeline/round.py memory-ok 2>&1); do say "waiting for memory: $w"; sleep 60; done; [ -n "$w" ] && say "$w"; return 0; }
# the new classes, checked directly (stage 1's own count took the predictions' summary.json for a tile): one prediction
# for every tile of the pool, and the predictions' summary naming the model in use and a finished run
$PY - <<PYEOF || { say "the new classes are not complete; stopping"; exit 1; }
import json, sys
from pathlib import Path
H = Path("$HD"); pred = H / "rounds" / "mk" / "pred"
tiles = {t["id"] for t in json.load(open(H / "rounds" / "pool.json"))["tiles"]}
have = {f.stem for f in pred.glob("*.npz")}
ck = json.load(open("data/rounds/model.json"))["checkpoint"]
sp = pred / "summary.json"; txt = sp.read_text() if sp.exists() else ""
ok = tiles <= have and ck in txt
print(f"{len(have & tiles)} of {len(tiles)} tiles predicted; summary names {ck}: {ck in txt}", flush=True)
sys.exit(0 if ok else 1)
PYEOF
if pgrep -f "round.py (night|cut|predict|retrain|gate)|train.py train|utci.py" >/dev/null; then say "another heavy job runs; stopping"; exit 1; fi
# the mean size of a UTCI file before they are cleared, for the disk check (a plan's holds UTCI only: half); kept in a
# file, so a run started again after the clear has it
if [ ! -s $HD/rebuild_en_2.per ]; then
  $PY -c "
from pathlib import Path
s = [f.stat().st_size for f in Path('$HD/utci').glob('*.npz')]
print(int(sum(s) / len(s)) if s else 0)" > $HD/rebuild_en_2.per
fi
PER=$(cat $HD/rebuild_en_2.per)
[ "$PER" -gt 0 ] || { say "no UTCI files to size the disk check from; stopping"; exit 1; }
room() {
  until $PY -c "
import json, shutil, sys
from pathlib import Path
H = Path('$HD'); scen = '$1'
tiles = [t['id'] for t in json.load(open(H / 'rounds' / 'pool.json'))['tiles']]
out = H / ('utci_' + scen if scen else 'utci')
todo = [t for t in tiles if not (out / (t + '.npz')).exists() and (not scen or (H / 'layers' / (scen + '_cdsm') / (t + '.npy')).exists())]
need = len(todo) * $PER * (0.5 if scen else 1)
free = shutil.disk_usage('/').free
print(f'{len(todo)} tiles to run need {need / 1e9:.1f} GB; {free / 1e9:.1f} GB free', flush=True)
sys.exit(0 if free >= need else 1)
"; do say "waiting for disk space (see the line above)"; sleep 600; done
}
# the live (v1) page's outputs kept, so it can be built again without the v1 chain (235 MB)
[ -e $M/web/out_v1 ] || cp -a $M/web/out $M/web/out_v1 || exit 1
[ -e $M/web/tiles/index_v1.json ] || cp $M/web/tiles/index.json $M/web/tiles/index_v1.json || exit 1
# cleared once (the marker), so a run started again after a failure goes on from what the steps have made; the plans'
# outputs every time, since treeplant.py rewrites only the tiles it plants in and shelters.py adds to what is there
if [ ! -e $HD/rebuild_en_2.cleared ]; then
  say "clearing the outputs made from v1's classes"
  rm -rf $HD/strips $HD/surfaces $HD/shade $HD/utci $HD/layers/shelters_cdsm || exit 1
  touch $HD/rebuild_en_2.cleared
fi
rm -rf $HD/utci_stops $HD/utci_trees $HD/layers/stops_cdsm $HD/layers/trees_cdsm $HD/layers/stops.json $HD/layers/trees.json || exit 1
calm; say "flight lines"; nice $PY -I $M/intensity_lines.py $PWD || exit 1
calm; say "surfaces"; nice $PY -I $M/surfaces.py $PWD || exit 1
say "land cover"; $HV -I $M/landcover.py $PWD || exit 1
calm; say "shade"; $HV -I $M/shade.py $PWD || exit 1
say "shelters"; $HV -I $M/shelters.py $PWD existing || exit 1
room; calm; say "utci"; $HV -I $M/utci.py $PWD --gpu || exit 1
say "new buildings"; $HV -I $M/new_build.py $PWD || exit 1
calm; say "package"; $HV -I $M/package.py $PWD "Milton Keynes" || exit 1
# a preview of the day as it was, before the plans (Jacob, 20 Oct 2026: "can you upload the site with the line fixes
# maybe before you spend 10 hours remodelling?"): the new classes and the flight-line fix, the plans' buttons absent
# (a failure here is said and the chain goes on: the plans and the final site do not need it)
calm; say "site before the plans"
if $HV -I $M/web/site.py $PWD; then
  DEP=$(cd $M/web/site && CLOUDFLARE_ACCOUNT_ID=148ef3a765d15218b5651d5de86b92db wrangler pages deploy . --project-name mk-heat --branch en --commit-dirty=true 2>&1)
  echo "$DEP" | grep -E "alias URL|ERROR"
  echo "$DEP" | grep -q "alias URL" && say "preview before the plans: https://en.mk-heat.pages.dev" || say "the preview before the plans did not deploy; the chain goes on"
else
  say "the site before the plans could not be built; the chain goes on"
fi
say "tree count"; $HV -I $M/treecount.py $PWD > $HD/treecount_en.log 2>&1 || exit 1
say "tree size"; $HV -I $M/treesize.py $PWD > $HD/treesize_en.log 2>&1 || exit 1; cat $HD/layers/treesize.json
say "trees at bus stops (fewest, exact)"; $HV -I $M/treeplant.py $PWD --stops-only --stops-exact --name stops || exit 1
room stops; calm; say "utci with the stop trees"; $HV -I $M/utci.py $PWD --gpu --scenario stops || exit 1
for round in 1 2 3; do                                   # shelters where no tree cools a stop, round by round
  out=$($HV -I $M/shelters.py $PWD add stops) || exit 1; say "shelters round $round: $out"
  echo "$out" | grep -q "; 0 new shelters" && break
  calm; $HV -I $M/utci.py $PWD --gpu --scenario stops || exit 1
done
calm; say "package the stop trees"; $HV -I $M/package.py $PWD "Milton Keynes" --scenario stops || exit 1
N=$(python3 -c "import json;print(round(json.load(open('$HD/layers/treecount.json'))['treetops']/10))")
say "10% more trees: $N"; $HV -I $M/treeplant.py $PWD $N --plant $N --stops-first --stops-exact --name trees || exit 1
room trees; calm; say "utci with the trees"; $HV -I $M/utci.py $PWD --gpu --scenario trees || exit 1
for round in 1 2 3; do
  out=$($HV -I $M/shelters.py $PWD add trees) || exit 1; say "the trees' shelters round $round: $out"
  echo "$out" | grep -q "; 0 new shelters" && break
  calm; $HV -I $M/utci.py $PWD --gpu --scenario trees || exit 1
done
calm; say "package the trees"; $HV -I $M/package.py $PWD "Milton Keynes" --scenario trees || exit 1
calm; say "site"; $HV -I $M/web/site.py $PWD || exit 1
DEP=$(cd $M/web/site && CLOUDFLARE_ACCOUNT_ID=148ef3a765d15218b5651d5de86b92db wrangler pages deploy . --project-name mk-heat --branch en --commit-dirty=true 2>&1)
echo "$DEP" | grep -E "alias URL|ERROR"
echo "$DEP" | grep -q "alias URL" || { say "the preview deploy failed; stopping"; exit 1; }
say "all done (preview: https://en.mk-heat.pages.dev)"
