#!/bin/zsh
# The heat map on v3 + England, stage 1 of 2 (Jacob, 19 Oct 2026: "you will have to do v3 + the english answers for the
# heat map too"; 20 Oct: "Can you focus on both the heat map too yeah"): the borough's crops cut again by the rules of
# the model in use (model.json: night r006's pointssm_en_r006, fine-tuned from v3, so v3's 204,800-cell windows) and
# classified by it. v1's cut records and predictions are kept beside (rounds/cut_v1, rounds/mk/pred_v1), so the v1 map
# can be made again; nothing else is touched here. Stage 2 (rebuild_en_2.sh) makes the map from the new classes.
cd /Users/jacobweinbren/Desktop/lidar-review
export ROUNDS_DIR=$PWD/data/mk/heat/rounds
PY=pipeline/.venv/bin/python; HD=data/mk/heat
say() { echo "$(date '+%F %T') $*"; }
calm() { until [ "$(sysctl -n kern.memorystatus_vm_pressure_level)" = 1 ]; do say "waiting for memory pressure 1"; sleep 60; done; }
CK=$($PY -c "import json; print(json.load(open('data/rounds/model.json'))['checkpoint'])")
[ "$CK" = runs/rounds/r006/wise.pt ] || { say "model.json names $CK, not r006's fine-tune; stopping"; exit 1; }
if pgrep -f "round.py (night|cut|predict|retrain|gate)|train.py train|utci.py" >/dev/null; then say "another heavy job runs; stopping"; exit 1; fi
[ -e $HD/rounds/cut_v1 ] || cp -a $HD/rounds/cut $HD/rounds/cut_v1 || exit 1
if [ -d $HD/rounds/mk/pred ] && [ ! -e $HD/rounds/mk/pred_v1 ]; then mv $HD/rounds/mk/pred $HD/rounds/mk/pred_v1 || exit 1; fi
say "v1 kept: $(ls $HD/rounds/cut_v1 | wc -l | tr -d ' ') cut records, $(ls $HD/rounds/mk/pred_v1 | wc -l | tr -d ' ') predictions"
calm; say "cut by the model in use's rules"; $PY -u pipeline/round.py cut --force --workers 1 || exit 1
calm; say "classify with $CK"; ROUNDS_GPU_HOLDER=$$ $PY -u pipeline/round.py predict --round mk --checkpoint $CK --workers 1 --device mps || exit 1
N=$(ls $HD/rounds/mk/pred | wc -l | tr -d ' '); T=$($PY -c "import json; print(len(json.load(open('$HD/rounds/pool.json'))['tiles']))")
[ "$N" = "$T" ] || { say "$N predictions for $T tiles; stopping"; exit 1; }
say "stage 1 done: $N tiles classified by $CK"
