#!/usr/bin/bash
# quick pass at building minimal text database of dicom headers
# 20240907 WF - init
#
export TAG_ARGS=$(cut -f2 taglist.txt | sed '1d;/#/d;s/^/-tag /;'|paste -sd' ')
dcmmeta2tsv(){
 declare -g TAG_ARGS
 #echo "# $1" >&2
 gdcmdump -dC "$1" |
   perl -ne 'BEGIN{%a=(Phase=>"NA", ucPAT=>"NA")}
   $a{substr($1,0,5)} = $2 if m/(PhaseEncodingDirectionPositive.*Data..|ucPATMode\s+=\s+)(\d+)/;
   END {print join("\t", @a{qw/Phase ucPAT/}), "\t"}'
 dicom_hinfo -sepstr $'\t' -last -full_entry $TAG_ARGS "$@"
}

eval "$(iffmain dcmmeta2tsv)"
