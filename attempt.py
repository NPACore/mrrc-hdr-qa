#!/usr/bin/python3
import os
import re

from pydicom import read_file

# Base directory
base_dir = "/Volumes/Hera/Raw/MRprojects/Habit/"

# Iterate through all date folders
for date_folder in os.listdir(base_dir):
    date_folder_path = os.path.join(base_dir, date_folder)
    if not os.path.isdir(date_folder_path):
        continue

    print(f"Processing date folder: {date_folder_path}")

    # Search for dMRI directories
    for root, dirs, files in os.walk(date_folder_path):
        for directory in dirs:
            # if 'dMRI_dir98-1_PA_1400x1400.*' in directory: # 'dMRI_dir98-1_PA_1400x1400.32' in directory or 'dMRI_dir98-1_PA_1400x1400.34' in directory:
            if re.search(r"dMRI_dir98-1_PA_1400x1400\.\d+", directory):
                dMRI_dir = os.path.join(root, directory)
                print(f"    Found dMRI directory: {dMRI_dir}")

                # Get the first file in the directory
                dcm_files = [f for f in os.listdir(dMRI_dir) if f.startswith("MR")]

                if not dcm_files:
                    print(f"    No DICOM files found in {dMRI_dir}")
                    continue

                # Read the first DICOM file
                dcm_path = os.path.join(dMRI_dir, dcm_files[0])
                try:
                    dcm = read_file(dcm_path)
                    if hasattr(dcm, "InPlanePhaseEncodingDirection"):
                        print(f"    {dcm_path}: {dcm.InPlanePhaseEncodingDirection}")
                    else:
                        print(
                            f"    {dcm_path}: InPlanePhaseEncodingDirection tag not found"
                        )
                except Exception as e:
                    print(f"    Error reading {dcm_path}: {str(e)}")
