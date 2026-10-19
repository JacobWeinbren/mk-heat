#!/bin/zsh
# The map without tile seams (Jacob, 19 Oct 2026: "can you fix these lines?" of straight colour edges across fields;
# "the proper fix is rerunning SOLWEIG with a single area-wide weather series sounds a plan"): utci.py --forcing area
# (its default now: SOLWEIG with the tiles' mean UKV series, UTCI from its Tmrt with each 1 m cell's own air, humidity
# and wind interpolated between tile centres), then everything that reads UTCI, as borough.sh ran it: the map, the stop
# trees planted again on the new UTCI with their shelter rounds, the 10% trees and theirs, each plan's figures, the
# site and a preview on the borough branch to be checked before production. The earlier outputs are kept in
# before_seams/. It starts when urban_split.sh has finished (one heavy job beside v3). A failure stops it.
cd /Users/jacobweinbren/Desktop/lidar-review
export ROUNDS_DIR=$PWD/data/mk/heat/rounds
PY=pipeline/.venv/bin/python; HV=data/experiments/mk_heat/.venv/bin/python; M=data/experiments/mk_heat; HD=data/mk/heat
say() { echo "$(date '+%F %T') $*"; }
calm() { until [ "$(sysctl -n kern.memorystatus_vm_pressure_level)" = 1 ]; do say "waiting for memory pressure 1"; sleep 60; done; }
# the disk for a UTCI run: borough.sh's rule (the tiles still to run times the mean size of the files written, half for
# a scenario, and two of the training run's checkpoints)
room() {
  until $PY -c "
import json, shutil, sys
from pathlib import Path
H = Path('$HD'); scen = '$1'
tiles = [t['id'] for t in json.load(open(H / 'rounds' / 'pool.json'))['tiles']]
out = H / ('utci_' + scen if scen else 'utci')
todo = [t for t in tiles if not (out / (t + '.npz')).exists() and (not scen or (H / 'layers' / (scen + '_cdsm') / (t + '.npy')).exists())]
sizes = [f.stat().st_size for d in ('before_seams/utci',) if (H / d).is_dir() for f in (H / d).glob('*.npz')]
per = (sum(sizes) / max(len(sizes), 1)) * (0.5 if scen else 1)
run = json.load(open('data/experiments/v3_lidar/config.json'))['run']
ck = Path('runs') / run / 'last.pt'
need = len(todo) * per + 2 * (ck.stat().st_size if ck.exists() else 0)
free = shutil.disk_usage('/').free
print(f'{len(todo)} tiles, {need / 1e9:.1f} GB needed, {free / 1e9:.1f} GB free', file=sys.stderr)
sys.exit(0 if free > need else 1)
"; do say "waiting for disk space"; sleep 300; done
}
say "waiting for urban_split.sh"
while pgrep -f "urban_split.sh" > /dev/null; do sleep 60; done
grep -q "all done" $HD/urban_split.log || { say "urban_split.sh did not finish; stopping"; exit 1; }
mkdir -p $HD/before_seams
for d in utci utci_stops utci_trees layers/stops_cdsm layers/trees_cdsm; do [ -e $HD/$d ] && mv $HD/$d $HD/before_seams/$(basename $d); done
for f in stops.json trees.json; do [ -e $HD/layers/$f ] && mv $HD/layers/$f $HD/before_seams/$f; done
room; calm; say "utci"; $HV -I $M/utci.py $PWD --gpu || exit 1
calm; say "package"; $HV -I $M/package.py $PWD "Milton Keynes" || exit 1
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
( cd $M/web/site && CLOUDFLARE_ACCOUNT_ID=148ef3a765d15218b5651d5de86b92db wrangler pages deploy . --project-name mk-heat --branch borough --commit-dirty=true 2>&1 | grep -E "alias URL|ERROR" )
say "all done (preview: https://borough.mk-heat.pages.dev)"
