#!/bin/zsh
# The heat map on night r010's model, stage 1 of 2 (Jacob, 23 Oct 2026: "when run 10 is done, if it is good, rerun the
# model on its segmentation"; r010 was kept at 17:51, mIoU 0.8231 against r009's 0.809): the borough classified by the
# model in use, model.json's pointssm_en_r010 (runs/rounds/r010/wise.pt). The cut stays: it follows the New Zealand
# model in use (v3, as for r006, re-cut on 20 Oct by rebuild_en_1.sh). r006's predictions are kept beside
# (rounds/mk/pred_r006), so the live map's classes can be made again. Waits for the morning charts' passes
# (post_r010.sh: dtm_check.py, fair_maps.py) to end. Stage 2 (rebuild_r010_2.sh) makes the map from the new classes.
cd /Users/jacobweinbren/Desktop/lidar-review
export ROUNDS_DIR=$PWD/data/mk/heat/rounds
PY=pipeline/.venv/bin/python; HD=data/mk/heat
say() { echo "$(date '+%F %T') $*"; }
calm() { local w; until w=$($PY -u pipeline/round.py memory-ok 2>&1); do say "waiting for memory: $w"; sleep 60; done; [ -n "$w" ] && say "$w"; return 0; }
CK=$($PY -c "import json; print(json.load(open('data/rounds/model.json'))['checkpoint'])")
[ "$CK" = runs/rounds/r010/wise.pt ] || { say "model.json names $CK, not r010's fine-tune; stopping"; exit 1; }
while pgrep -f "post_r010.sh|dtm_check.py|fair_maps.py|fair_score_maps.py" >/dev/null; do sleep 60; done
if pgrep -f "round.py (night|cut|predict|retrain|gate)|train.py train|utci.py" >/dev/null; then say "another heavy job runs; stopping"; exit 1; fi
if [ -d $HD/rounds/mk/pred ] && [ ! -e $HD/rounds/mk/pred_r006 ]; then mv $HD/rounds/mk/pred $HD/rounds/mk/pred_r006 || exit 1; fi
say "r006 kept: $(ls $HD/rounds/mk/pred_r006 | wc -l | tr -d ' ') predictions"
calm; say "classify with $CK"; ROUNDS_GPU_HOLDER=$$ $PY -u pipeline/round.py predict --round mk --checkpoint $CK --workers 1 --device mps || exit 1
$PY -c "import sys; sys.path.insert(0, 'pipeline'); import mps_temp; print('empty Metal temp folders removed:', mps_temp.clear())"
N=$(ls $HD/rounds/mk/pred/*.npz | wc -l | tr -d ' '); T=$($PY -c "import json; print(len(json.load(open('$HD/rounds/pool.json'))['tiles']))")
[ "$N" = "$T" ] || { say "$N predictions for $T tiles; stopping"; exit 1; }
say "stage 1 done: $N tiles classified by $CK"
