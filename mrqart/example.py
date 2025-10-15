#!/usr/bin/python3
from pydicom import read_file

dcm = read_file(
    "/Volumes/Hera/Raw/MRprojects/Habit/2022.09.13-14.46.09/11883_20220913/dMRI_dir98-1_PA_1400x1400.32/MR.1.3.12.2.1107.5.2.43.167046.2022091316113066401174819"
)
print(dcm.InPlanePhaseEncodingDirection)
