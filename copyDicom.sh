#!/usr/bin/bash
# Copy the first DICOM file from rest, task, and dwi folders

rest_folder_a=(/Volumes/Hera/Raw/MRprojects/Habit/*/*/Resting-state_ME_4*)
task_folder_a=(/Volumes/Hera/Raw/MRprojects/Habit/*/*/HabitTask_704*)
dwi_folder_a=(/Volumes/Hera/Raw/MRprojects/Habit/*/*/dMRI_b0_AP_1*)

rest_folder_b=(/Volumes/Hera/Raw/MRprojects/Habit/*/*/Resting-state_ME_repeat_4*)
task_folder_b=(/Volumes/Hera/Raw/MRprojects/Habit/*/*/H)
dwi_folder_b=(/Volumes/Hera/Raw/MRprojects/Habit/*/*/dMRI_dir98-1_PA_1*)

output_dir="$HOME/src/mrrc-hdr-qa/dicoms"

mkdir -p "$output_dir"

copy_first_dicom() {
    local folders=("$@")
    local count=0
    for d in "${folders[@]}"; do
	if [ "$count" -ge 2 ]; then
		break
	fi
        # Find and copy the first DICOM file to output directory
        find "$d" -maxdepth 1 -type f -print -quit |
        while read -r file; do
            cp "$file" "$output_dir/$(basename "$file")"
	    ((count++))
	
	    if [ "$count" -ge 2 ]; then
		    break
	    fi
    	done
    done
}

# Copy from rest, task and DWI folders
copy_first_dicom "${rest_folder_a[@]}"
copy_first_dicom "${rest_folder_b[@]}"
copy_first_dicom "${task_folder_a[@]}"
copy_first_dicom "${dwi_folder_a[@]}"
copy_first_dicom "${dwi_folder_b[@]}"
