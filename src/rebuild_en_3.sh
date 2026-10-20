#!/bin/zsh
# The heat map on v3 + England, the end of stage 2 (rebuild_en_2.sh), run on its own: stage 2 had made the baseline, the stop
# plan and the 10% plan with its first round of shelters (37 new, 44 tiles to run again), then waited from 16:58 for memory
# pressure 1 or the training's 17.0 GB free (round.py memory-ok's default), which a UTCI run does not need. Measured on
# 20 Oct 2026: a UTCI run's peak physical footprint is 2.35 GB on one tile and 2.65 GB over four (utci.py's two tiles
# finishing beside the one running), so each step here starts at memory pressure 1, or at 2 with 2.65 GB free (round.py
# memory-ok --need-gb; Jacob, 13 Oct 2026: a job may start at level 2 when free memory covers its measured footprint).
# Nothing is cleared: utci.py skips every tile already made, and shelters.py removed the 44 tiles' outputs it changed.
# The package step's peak was measured as it ran (proc_pid_rusage's lifetime_max_phys_footprint): 4.88 GB.
cd /Users/jacobweinbren/Desktop/lidar-review
export ROUNDS_DIR=$PWD/data/mk/heat/rounds
PY=pipeline/.venv/bin/python; HV=data/experiments/mk_heat/.venv/bin/python; M=data/experiments/mk_heat; HD=data/mk/heat
NEED=2.65
say() { echo "$(date '+%F %T') $*"; }
calm() { local w; until w=$($PY -u pipeline/round.py memory-ok --need-gb $NEED 2>&1); do say "waiting for memory: $w"; sleep 60; done; [ -n "$w" ] && say "$w"; return 0; }
if pgrep -f "round.py (night|cut|predict|retrain|gate)|train.py train|utci.py" >/dev/null; then say "another heavy job runs; stopping"; exit 1; fi
calm; say "utci with the trees (the tiles the shelters changed)"; $HV -I $M/utci.py $PWD --gpu --scenario trees || exit 1
for round in 2 3; do
  out=$($HV -I $M/shelters.py $PWD add trees) || exit 1; say "the trees' shelters round $round: $out"
  echo "$out" | grep -q "; 0 new shelters" && break
  calm; $HV -I $M/utci.py $PWD --gpu --scenario trees || exit 1
done
calm; say "package the trees"; $HV -I $M/package.py $PWD "Milton Keynes" --scenario trees || exit 1   # its peak, measured: 4.88 GB
calm; say "site"; $HV -I $M/web/site.py $PWD || exit 1
DEP=$(cd $M/web/site && CLOUDFLARE_ACCOUNT_ID=148ef3a765d15218b5651d5de86b92db wrangler pages deploy . --project-name mk-heat --branch en --commit-dirty=true 2>&1)
echo "$DEP" | grep -E "alias URL|ERROR"
echo "$DEP" | grep -q "alias URL" || { say "the preview deploy failed; stopping"; exit 1; }
say "all done (preview: https://en.mk-heat.pages.dev)"
