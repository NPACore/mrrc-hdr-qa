#!/usr/bin/bash
#Copy the first two DICOM files from rest, task, and dwi folders
#
output_dir="$HOME/src/mrrc-hdr-qa/dicoms/"

mkdir -p "$output_dir"

copy_first_two() {
	local sessions=("$@")
	for session in "${sessions[@]}"; do
		# copy the first two dicoms in the session
		files=($(ls "$session" | head -n2))
		for file in "${files[@]}"; do
			cp "$session/$file" "$output_dir/$(basename "$file")"
		done
	done
}

rest_sessions=($(printf "%s\n" /Volumes/Hera/Raw/MRprojects/Habit/2*/1*/Resting-state_ME_4*/ | head -n2))
task_sessions=($(printf "%s\n" /Volumes/Hera/Raw/MRprojects/Habit/2*/1*/HabitTask_704*/ | head -n2))
dwi_sessions=($(printf "%s\n" /Volumes/Hera/Raw/MRprojects/Habit/2*/1*/dMRI_b0_AP_1*/ | head -n2))

copy_first_two "${rest_sessions[@]}"
copy_first_two "${task_sessions[@]}"
copy_first_two "${dwi_sessions[@]}"
