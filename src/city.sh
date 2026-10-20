#!/bin/zsh
# the whole city (Jacob, 18 Oct 2026: "yes add land cover, then do the whole city"): v1 on the remaining tiles, then
# surfaces, one land-cover threshold over all tiles, shade, UTCI (GPU, UKV 2 km per tile), new buildings, map files.
# Each step starts only at memory pressure 1 (the r005 photos run beside it).
cd /Users/jacobweinbren/Desktop/lidar-review
export ROUNDS_DIR=$PWD/data/mk/heat/rounds
say() { echo "$(date '+%F %T') $*"; }
calm() { until [ "$(sysctl -n kern.memorystatus_vm_pressure_level)" = 1 ]; do say "waiting for memory pressure 1"; sleep 60; done; }
PY=pipeline/.venv/bin/python; HV=data/experiments/mk_heat/.venv/bin/python
calm; say "cut"; $PY pipeline/round.py cut --workers 1 || exit 1
calm; say "predict"; ROUNDS_GPU_HOLDER=$$ $PY pipeline/round.py predict --round mk --checkpoint runs/pointssm_nz_v1/best.pt --workers 1 --device mps || exit 1
calm; say "flight lines"; $PY -I data/experiments/mk_heat/intensity_lines.py $PWD || exit 1
calm; say "surfaces"; $PY -I data/experiments/mk_heat/surfaces.py $PWD || exit 1
say "land cover"; $HV -I data/experiments/mk_heat/landcover.py $PWD || exit 1
calm; say "shade"; $HV -I data/experiments/mk_heat/shade.py $PWD || exit 1
say "shelters"; $HV -I data/experiments/mk_heat/shelters.py $PWD existing || exit 1
[ -d data/mk/heat/utci_cmk_threshold ] || { mkdir -p data/mk/heat/utci_cmk_threshold && mv data/mk/heat/utci/*.npz data/mk/heat/utci_cmk_threshold/ 2>/dev/null; }   # once: central MK's files of the old land-cover threshold
calm; say "utci"; $HV -I data/experiments/mk_heat/utci.py $PWD --gpu || exit 1
say "new buildings"; $HV -I data/experiments/mk_heat/new_build.py $PWD || exit 1
say "package"; $HV -I data/experiments/mk_heat/package.py $PWD "Milton Keynes" || exit 1
say "landsat"; $HV -I data/experiments/mk_heat/landsat_check.py $PWD check city > data/mk/heat/landsat_city.log 2>&1
say "tree count"; $HV -I data/experiments/mk_heat/treecount.py $PWD > data/mk/heat/treecount_city.log 2>&1
say "deprivation"; $HV -I data/experiments/mk_heat/deprivation.py $PWD > data/mk/heat/deprivation_city.log 2>&1 || exit 1
# two tree scenarios (Jacob, 18 Oct 2026): the trees for the bus stops alone ("Maybe we should just focus on that then"),
# and 10% more trees than the lidar counts in the modelled tiles ("10 percent more max. More is unrealistic"), the stops'
# trees first, then the footpaths' (treecount.py runs before); the curve is cut at that number, which leaves the trees exact
mkdir -p data/mk/heat/before_city
for d in utci_trees utci_stops layers/trees_cdsm layers/stops_cdsm; do [ -e data/mk/heat/$d ] && mv data/mk/heat/$d data/mk/heat/before_city/$(basename $d)_cmk; done
say "trees at bus stops"; $HV -I data/experiments/mk_heat/treeplant.py $PWD --stops-only --name stops || exit 1
calm; say "utci with the stop trees"; $HV -I data/experiments/mk_heat/utci.py $PWD --gpu --scenario stops || exit 1
for round in 1 2 3; do                                   # shelters where no tree cools a stop, round by round
  out=$($HV -I data/experiments/mk_heat/shelters.py $PWD add stops) || exit 1; say "shelters round $round: $out"
  echo "$out" | grep -q "; 0 new shelters" && break
  calm; $HV -I data/experiments/mk_heat/utci.py $PWD --gpu --scenario stops || exit 1
done
say "package the stop trees"; $HV -I data/experiments/mk_heat/package.py $PWD "Milton Keynes" --scenario stops || exit 1
N=$(python3 -c "import json;print(round(json.load(open('data/mk/heat/layers/treecount.json'))['treetops']/10))")
say "10% more trees: $N"; $HV -I data/experiments/mk_heat/treeplant.py $PWD $N --plant $N --stops-first --name trees || exit 1
calm; say "utci with the trees"; $HV -I data/experiments/mk_heat/utci.py $PWD --gpu --scenario trees || exit 1
say "package the trees"; $HV -I data/experiments/mk_heat/package.py $PWD "Milton Keynes" --scenario trees || exit 1
python3 data/experiments/mk_heat/web/build.py
touch data/mk/heat/city.done; say "all done"
