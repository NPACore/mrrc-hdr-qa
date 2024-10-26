#!/usr/bin/env bash
#
# build db
#
source dcmmeta2tsv.bash
export -f dcmmeta2tsv

build_dcm_db(){
  cnt=1
  maxcnt=${MAXDCMCOUNT:-0}
  [[ $# -eq 0 || "${1}" == "all" ]] &&
     dcmdirs=(/Volumes/Hera/Raw/MRprojects/Habit/2022.08.23-14.24.18/11878_20220823/{HabitTask_704x752.19,dMRI_b0_AP_140x140.35,Resting-state_ME_476x504.14}/) ||
     dcmdirs=("$@")
  for d in "${dcmdirs[@]}"; do
    # physio embedded dicoms dont have much in the way of header information
    # Phoenix Report is session summary pdf?
    [[ $d =~ PhysioLog|PhoenixZIPReport ]] && continue

    # give some indication of progress every 100
    [ $(($cnt % 100)) -eq 0 ] && echo "# [$(date +%H:%M:%S.%N)] $cnt $d" >&2

    # just one dicom form each acquisition
    find "$d" -maxdepth 1 -type f -print -quit

    # maybe we want to quit early?
    let ++cnt
    # || true  so we don't end loop on an error
    [ $maxcnt -gt 0 -a $cnt -gt $maxcnt ] && break || true
  done |
    time xargs ./dcmmeta2tsv.py |
    #parallel -n1 dcmmeta2tsv |
    tee db.txt
 return 0
}

eval "$(iffmain build_dcm_db)"
