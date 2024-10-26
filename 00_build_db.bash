#!/usr/bin/env bash
#
# build db
#
source dcmmeta2tsv.bash

_project=${PROJECT:-all}
find_example_dcm(){
  # physio embedded dicoms dont have much in the way of header information
  # Phoenix Report is session summary pdf?
  [[ "$1" =~ PhysioLog|PhoenixZIPReport ]] && return
  [ ! -d "$1" ] && echo "ERROR acq dir '$1' is not a dir" >&2 && return
  # just one dicom form each acquisition
  find "$1" -maxdepth 1 -type f \( -iname '*.dcm' -or -iname 'MR.*' -or -iname '*.IMA' \) -print -quit
}

export -f dcmmeta2tsv find_example_dcm

build_dcm_db(){
  #
  # dicoms like project/session_date/session_id/acquistion/


  maxcnt=${MAXDCMCOUNT:-0}
  cnt=1

  mkdir -p db/

  for project in "$@"; do
     [ ! -d $project ] && echo "ERROR: failed to find project directory '$project'" >&2 && continue
     pname=$(basename $project)
     outtxt=db/$pname.txt
     echo "# $pname into $outtxt" >&2
     for acq in $project/2*/*/*/; do

         # give some indication of progress: print line every 100
	 let ++cnt
	 [ $maxcnt -gt 0 -a $cnt -gt $maxcnt ] && break
         [ $(($cnt % 100)) -eq 0 ] && echo "# [$(date +%H:%M:%S.%N)] $cnt $acq" >&2

	 find_example_dcm "$acq"
     done |
     time parallel -X -j 4 --bar ./dcmmeta2tsv.py > $outtxt 
  done
 return 0
}

eval "$(iffmain build_dcm_db)"
