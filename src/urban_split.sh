#!/bin/zsh
# The figures twice, for the urban part and the whole borough (area.urban; Jacob, 19 Oct 2026: "maybe split the figures
# between the urban core and the greater extent. because not many people live in the rural bits. but still keep it
# concise the text"), the method text shorter ("make this conciser. the bit about fields is unneeded") and the site
# quicker ("make the site speedy and cache friendly"; "the trees could also be pmtiles, no?": the trees in an archive
# of their own, the page's script cached a year, the place names' glyphs asked for with the page). The map's packaging
# again (package.py, then its two plans, as borough.sh ran them), the site, and a preview on the borough branch to be
# checked before production. A failure stops it.
cd /Users/jacobweinbren/Desktop/lidar-review
export ROUNDS_DIR=$PWD/data/mk/heat/rounds
HV=data/experiments/mk_heat/.venv/bin/python; M=data/experiments/mk_heat
say() { echo "$(date '+%F %T') $*"; }
calm() { until [ "$(sysctl -n kern.memorystatus_vm_pressure_level)" = 1 ]; do say "waiting for memory pressure 1"; sleep 60; done; }
cp $M/web/out/data.json $M/web/out/data_before_urban.json
calm; say "package"; $HV -I $M/package.py $PWD "Milton Keynes" || exit 1
calm; say "package the stop trees"; $HV -I $M/package.py $PWD "Milton Keynes" --scenario stops || exit 1
calm; say "package the trees"; $HV -I $M/package.py $PWD "Milton Keynes" --scenario trees || exit 1
calm; say "site"; $HV -I $M/web/site.py $PWD || exit 1
( cd $M/web/site && CLOUDFLARE_ACCOUNT_ID=148ef3a765d15218b5651d5de86b92db wrangler pages deploy . --project-name mk-heat --branch borough --commit-dirty=true 2>&1 | grep -E "alias URL|ERROR" )
say "all done (preview: https://borough.mk-heat.pages.dev)"
