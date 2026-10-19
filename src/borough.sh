#!/bin/zsh
# The whole City of Milton Keynes (Jacob, 18 Oct 2026: "please do the full expansive greater MK definition"; he chose
# the borough, area.py), with water out of open ground and in the land cover, every stop judged by its coolest spot,
# and the fewest trees for the stops (treeplant --stops-exact): OSM and the basemap over the borough, the new crops
# (fetch_lidar.py's zips), their forcing, cut and v1's classification (v3 paused, as city_pause.sh), surfaces, land
# cover for every tile (OSM water; one Otsu threshold over all), shade for the new tiles, UTCI for every tile (the land
# cover changed everywhere), the map, then the two scenarios, then the site on a preview branch (borough) to be checked
# before it goes to production. Each step needs the one before; a failure stops the chain.
cd /Users/jacobweinbren/Desktop/lidar-review
export ROUNDS_DIR=$PWD/data/mk/heat/rounds
PY=pipeline/.venv/bin/python; HV=data/experiments/mk_heat/.venv/bin/python; M=data/experiments/mk_heat; HD=data/mk/heat
say() { echo "$(date '+%F %T') $*"; }
calm() { until [ "$(sysctl -n kern.memorystatus_vm_pressure_level)" = 1 ]; do say "waiting for memory pressure 1"; sleep 60; done; }
# a UTCI run waits until the disk holds what it will write: the tiles it runs times the mean size of the files already
# written (a baseline file holds Tmrt and UTCI, a scenario's UTCI only: half), and two of the training run's
# checkpoints, so a full disk can stop neither (18 Oct 2026: 14 GB free against about 30 GB the borough's run writes)
room() {
  until $PY -c "
import json, os, shutil, sys
from pathlib import Path
H = Path('$HD'); scen = '$1'
tiles = [t['id'] for t in json.load(open(H / 'rounds' / 'pool.json'))['tiles']]
out = H / ('utci_' + scen if scen else 'utci')
todo = [t for t in tiles if not (out / (t + '.npz')).exists() and (not scen or (H / 'layers' / (scen + '_cdsm') / (t + '.npy')).exists())]
sizes = [f.stat().st_size for d in ('utci', 'before_borough/utci_city') if (H / d).is_dir() for f in (H / d).glob('*.npz')]
per = (sum(sizes) / max(len(sizes), 1)) * (0.5 if scen else 1)
run = json.load(open('data/experiments/v3_lidar/config.json'))['run']
ck = Path('runs') / run / 'last.pt'
need = len(todo) * per + 2 * (ck.stat().st_size if ck.exists() else 0)
free = shutil.disk_usage('/').free
print(f'{len(todo)} tiles to run need {need / 1e9:.1f} GB with the checkpoints; {free / 1e9:.1f} GB free', flush=True)
sys.exit(0 if free >= need else 1)
"; do say "waiting for disk space (see the line above)"; sleep 600; done
}
say "osm and basemap"; $HV -I $M/osm_fetch.py $PWD || exit 1
calm; say "crops"; nice $PY -I $M/make_crops.py $PWD || exit 1
say "forcing"; $HV -I $M/ukv_fetch.py $PWD || exit 1
calm; say "cut"; $PY pipeline/round.py cut --workers 1 || exit 1
# v1's classification with v3 paused (city_pause.sh: beside the training it pushed swap up 2.4 GB in two minutes)
RUN=$($PY -c "import json; print(json.load(open('data/experiments/v3_lidar/config.json'))['run'])")
P=$(cat runs/$RUN/train.pid 2>/dev/null); PAUSED=
if [ -n "$P" ] && ps -p $P >/dev/null; then
  W=$(pgrep -f "^zsh data/rounds/queues/nz_v3_lidar.sh"); [ -n "$W" ] && kill -TERM ${(f)W}
  kill -TERM $P && say "pausing $RUN ($P)"; while ps -p $P >/dev/null; do sleep 5; done; PAUSED=1
fi
say "classify"; ROUNDS_GPU_HOLDER=$$ $PY pipeline/round.py predict --round mk --checkpoint runs/pointssm_nz_v1/best.pt --workers 1 --device mps
code=$?
if [ -n "$PAUSED" ]; then
  L=data/rounds/logs/nz_v3_lidar_resume_$(date +%Y%m%d-%H%M%S).log
  ( unset ROUNDS_DIR; nohup zsh data/rounds/queues/nz_v3_lidar.sh > $L 2>&1 & ); say "resumed $RUN, log $L"
fi
[ $code = 0 ] || { say "classification exited $code"; exit $code; }
calm; say "surfaces"; nice $PY -I $M/surfaces.py $PWD || exit 1
say "land cover"; $HV -I $M/landcover.py $PWD || exit 1
calm; say "shade"; $HV -I $M/shade.py $PWD || exit 1
say "shelters"; $HV -I $M/shelters.py $PWD existing || exit 1
# every tile's UTCI again: the land cover changed everywhere (water, the threshold over the borough); the city's kept
mkdir -p $HD/before_borough
for d in utci utci_stops utci_trees layers/stops_cdsm layers/trees_cdsm; do [ -e $HD/$d ] && mv $HD/$d $HD/before_borough/$(basename $d)_city; done
for f in stops.json trees.json; do [ -e $HD/layers/$f ] && mv $HD/layers/$f $HD/before_borough/${f%.json}_city.json; done
room; calm; say "utci"; $HV -I $M/utci.py $PWD --gpu || exit 1
say "new buildings"; $HV -I $M/new_build.py $PWD || exit 1
say "package"; $HV -I $M/package.py $PWD "Milton Keynes" || exit 1
say "tree count"; $HV -I $M/treecount.py $PWD > $HD/treecount_borough.log 2>&1 || exit 1
# the new trees' size: the median of the trees beside the borough's footpaths and stops (Jacob: "do it based on existing sizes")
say "tree size"; $HV -I $M/treesize.py $PWD > $HD/treesize_borough.log 2>&1 || exit 1; cat $HD/layers/treesize.json
say "trees at bus stops (fewest, exact)"; $HV -I $M/treeplant.py $PWD --stops-only --stops-exact --name stops || exit 1
room stops; calm; say "utci with the stop trees"; $HV -I $M/utci.py $PWD --gpu --scenario stops || exit 1
for round in 1 2 3; do                                   # shelters where no tree cools a stop, round by round
  out=$($HV -I $M/shelters.py $PWD add stops) || exit 1; say "shelters round $round: $out"
  echo "$out" | grep -q "; 0 new shelters" && break
  calm; $HV -I $M/utci.py $PWD --gpu --scenario stops || exit 1
done
say "package the stop trees"; $HV -I $M/package.py $PWD "Milton Keynes" --scenario stops || exit 1
N=$(python3 -c "import json;print(round(json.load(open('$HD/layers/treecount.json'))['treetops']/10))")
say "10% more trees: $N"; $HV -I $M/treeplant.py $PWD $N --plant $N --stops-first --stops-exact --name trees || exit 1
room trees; calm; say "utci with the trees"; $HV -I $M/utci.py $PWD --gpu --scenario trees || exit 1
# the 10% plan gets shelters too where no tree cools a stop, as the stop plan does (Jacob, 18 Oct 2026: "why 7 bus stops
# in heat for the 10% plan, shouldn't it also be 0?")
for round in 1 2 3; do
  out=$($HV -I $M/shelters.py $PWD add trees) || exit 1; say "the trees' shelters round $round: $out"
  echo "$out" | grep -q "; 0 new shelters" && break
  calm; $HV -I $M/utci.py $PWD --gpu --scenario trees || exit 1
done
say "package the trees"; $HV -I $M/package.py $PWD "Milton Keynes" --scenario trees || exit 1
say "site"; $HV -I $M/web/site.py $PWD || exit 1
( cd $M/web/site && CLOUDFLARE_ACCOUNT_ID=148ef3a765d15218b5651d5de86b92db wrangler pages deploy . --project-name mk-heat --branch borough --commit-dirty=true 2>&1 | grep -E "alias URL|ERROR" )
touch $HD/borough.done; say "all done (preview: https://borough.mk-heat.pages.dev)"
