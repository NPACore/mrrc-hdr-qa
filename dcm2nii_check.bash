# use dcm2niix to make bids sidecar json ('-b o' is json only, no nifti) files from dicom header
<<<<<<< HEAD
# want to check acq dir there in addition to dicom tag in case we're looking at the wrong one
=======
# want to check acq dir there in addition to dicom tag in case we're looking at the wrong one
>>>>>>> 48cf3dc (first commit for audit.py)
echo /Volumes/Hera/Raw/MRprojects/Habit/20*-*/1*_2*/dMRI_*/ |
    head -n 15 |
    xargs -I{} -n1 dcm2niix -o example_jsons/ -b o {}

jq -r '[.PhaseEncodingDirection, input_filename]|@tsv' example_jsons/*json > example_jsons.tsv

sed 's:example.*\(AP\|PA\).*json:\1:' < example_jsons.tsv|sort |uniq -c
#  8 j-      AP
#  7 j       PA

