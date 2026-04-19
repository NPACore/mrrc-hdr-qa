#!/usr/bin/env bash
#
# build db
#

_project=${PROJECT:-all}
find_example_dcm(){
  # physio embedded dicoms dont have much in the way of header information
  # Phoenix Report is session summary pdf?
  [[ "$1" =~ PhysioLog|PhoenixZIPReport ]] && return
  [ ! -d "$1" ] && echo "ERROR acq dir '$1' is not a dir" >&2 && return
  # just one dicom form each acquisition
  find "$1" -maxdepth 1 -type f \( -iname '*.dcm' -or -iname 'MR.*' -or -iname '*.IMA' \) -print -quit
}

export -f find_example_dcm

# get python depends. TODO: should do more to ensure this exists?
test -r "$(dirname "$0")/.venv/bin/activate" && source "$_"

build_dcm_db(){
  #
  # dicoms like project/session_date/session_id/acquisition/


  # stop after $maxcnt sessions per project. 0 means all
  maxcnt=${MAXDCMCOUNT:-0}

  # default to scan_data, but variable to use archive
  # but can also just specify full path with glob
  PROJECT_ROOT=${PROJECT_ROOT:-/disk/mace2/scan_data}


  [[ $# -eq 0 || $* =~ ^-h ]] && echo "USAGE: $0 [all|WPC-8291 /disk/mace2/scan_data/WPC-*/]; set PROJECT_ROOT to use archives" && return 0
  [[ $1 == all ]] && mapfile -t PROJECTS < <(ls -d $PROJECT_ROOT/*/ |xargs -n1 basename) || PROJECTS=("$@")


  mkdir -p db/
  cnt=1
  for project in "$@"; do
     # convenient way to specify a project without having the full path
     [[ ! -d "$project" && ! "$project" =~ / && -d "$PROJECT_ROOT/$project" ]] &&
        project=$PROJECT_ROOT/$project

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
     time parallel -X -j 4 --bar python3 -m mrqart.dcmmeta2tsv > $outtxt 
  done
 return 0
}

eval "$(iffmain build_dcm_db)"
