#!/usr/bin/bash
# quick pass at building minimal text database of dicom headers
# 20240907 WF - init
#
for d in  /Volumes/Hera/Raw/MRprojects/Habit/20*-*/1*_2*/dMRI_*/; do
       	find  $d -maxdepth 1 -type f -print -quit
done |
  xargs dicom_hinfo -tag 0018,1312 |
  tee db.txt
