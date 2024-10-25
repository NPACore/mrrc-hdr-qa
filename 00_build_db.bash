#!/usr/bin/bash
# quick pass at building minimal text database of dicom headers
# 20240907 WF - init
#
export TAG_ARGS=$(cut -f2 taglist.txt | sed '1d;/#/d;s/^/-tag /;'|paste -sd' ')
dcminfo(){
 declare -g TAG_ARGS
 #echo "# $1" >&2
 gdcmdump -dC "$1" |
   perl -ne 'BEGIN{%a=(Phase=>"NA", ucPAT=>"NA")}
   $a{substr($1,0,5)} = $2 if m/(PhaseEncodingDirectionPositive.*Data..|ucPATMode\s+=\s+)(\d+)/;
   END {print join("\t", @a{qw/Phase ucPAT/}), "\t"}'
 dicom_hinfo -sepstr $'\t' -last -full_entry $TAG_ARGS "$@"
}

export -f dcminfo

cnt=0
#for d in /Volumes/Hera/Raw/MRprojects/Habit/20*-*/1*_2*/dMRI_*/; do
for d in  /Volumes/Hera/Raw/MRprojects/Habit/2022.08.23-14.24.18/11878_20220823/HabitTask_704x752.19/ /Volumes/Hera/Raw/MRprojects/Habit/2022.08.23-14.24.18/11878_20220823/dMRI_b0_AP_140x140.35/  /Volumes/Hera/Raw/MRprojects/Habit/2022.08.23-14.24.18/11878_20220823/Resting-state_ME_476x504.14/; do
  echo "# $d" >&2
  # just one dicom
  find  $d -maxdepth 1 -type f -print -quit
  let ++cnt
  [ $cnt -gt 2 ] && break
done |
  # TODO: use './dcmmeta2tsv.py' instead of dcminfo?
  #xargs ./dcm2nii_check.bash |
  parallel -n1 dcminfo |
  tee db.txt
