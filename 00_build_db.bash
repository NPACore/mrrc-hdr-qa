#!/usr/bin/bash
# quick pass at building minimal text database of dicom headers
# 20240907 WF - init
#
declare -A t
t[AcqTime]="0008,0032"       # Acquisition Time like 145446.685000
t[AcqDate]="0008,0022"       # like 20241004
t[SeriesNumber]="0020,0011"  # REL Series Number
t[SubID]="0010,0010"         # patient name
t[iPAT]="0051,1011"          # PATModeText (private field)
t[Comments]="0020,4000"      #REL Image Comments//Unaliased MB3/PE4/LB SENSE1
t[Operator]="0008,1070"
t[Project]="0008,1030"       # ID Study Description//Brain^wpc-8620
t[SequenceName]="0008,103e"  # series descripton
t[SequenceType]="0018,0024"  # ACQ Sequence Name
t[PED_major]="0018,1312"     #   ACQ Phase Encoding Direction, ROW or COL
t[TR]="0018,0080"
t[TE]="0018,0081"
t[Matrix]="0018,1310"     # ACQ Acquisition Matrix
t[PixelResol]="0028,0030" #  IMG Pixel Spacing//2.2978723049164\2.2978723049164
# https://neurostars.org/t/how-is-bandwidthperpixelphaseencode-calculated/26526 (0021,1153)
t[BWP]="0018,0095"        # ACQ Pixel Bandwidth (?)
t[BWPPE]="0019,1028"      # in matlab S.BandwidthPerPixelPhaseEncode;
t[FA]="0018,1314"        
t[TA]="0051,100a"
t[FoV]="0051,100c" # eg FoV 1617*1727; but actually cocaluated from matrix and spacing?

for d in  /Volumes/Hera/Raw/MRprojects/Habit/20*-*/1*_2*/dMRI_*/; do
       	find  $d -maxdepth 1 -type f -print -quit
done |
  xargs dicom_hinfo -sepstr $'\t' -last -full_entry $(printf " -tag %s" "${t[@]}") |
  tee db.txt
