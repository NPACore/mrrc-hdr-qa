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
     dcmdirs="$@"
  for d in "${dcmdirs[@]}"; do
    echo "# $cnt $d" >&2
    # just one dicom
    find  $d -maxdepth 1 -type f -print -quit
    let ++cnt
    [ $maxcnt -gt 0 -a $cnt -gt $maxcnt ] && break
  done |
    xargs ./dcmmeta2tsv.py |
    #parallel -n1 dcmmeta2tsv |
    tee db.txt
 return 0
}

eval "$(iffmain build_dcm_db)"
